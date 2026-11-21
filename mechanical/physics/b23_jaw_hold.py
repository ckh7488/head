"""Screen a closed jaw motor hold and alternative passive return torques for the B23 CAD."""

from argparse import ArgumentParser
from itertools import product
import json
from pathlib import Path
import re

import numpy as np

from b20_dynamics import GRAVITY, UPPER_FRICTION, jaw_profile_move, load_bodies, motor_parameters, x_rotation
from b22_drive import FIRMWARE, jaw_config
from b23_force_path import DAMPING_NM_PER_RAD_S, digest, joint_wrenches
from check_b22_neck import encoder_feedback_limits
from multibody import pos

ROBOTIS = 'https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/'
WARM_SCALE = .55
MINIMUM_VOLTS = 4.5
REQUIRED_OPENING_RESERVE = .007
TOUCH_N = .25
DEMO_PWM = 160.
HOLD_PWM_EXAMPLE = 100.
PWM_SCALE = 885.


def static_gravity(jaw, anchor, pitch_angles, jaw_angles):
    offset = jaw.center-anchor
    return np.array([[-jaw.mass*GRAVITY[2]*(x_rotation(np.radians(p+q)) @ offset)[1]
                      for q in jaw_angles] for p in pitch_angles])


def servo_curves():
    stall_current = np.interp(MINIMUM_VOLTS, [3.7, 5., 6.], [1.11, 1.47, 1.74])
    static_stall = motor_parameters((11.1, 11.1, MINIMUM_VOLTS), WARM_SCALE)[0][2]
    return static_stall / stall_current


def motor_capacity(speed, torque, volts, pwm=DEMO_PWM):
    stall, free_speed, derating = motor_parameters((11.1, 11.1, volts), WARM_SCALE)
    limit = pwm/PWM_SCALE
    available = np.clip(limit-np.sign(torque)*speed/free_speed[2], 0., limit)
    return stall[2]*derating*available


def jaw_profile(jaw, pivot, opening_deg, speed_reg, accel_reg, pitch_angles):
    velocity = speed_reg * .229 * 6.
    acceleration = accel_reg * .1 * 214.577
    _, duration = jaw_profile_move(0., opening_deg, velocity, acceleration)
    # Take time samples on both sides of the acceleration change.
    states = np.array([jaw_profile_move(t, opening_deg, velocity, acceleration)[0]
                       for t in np.linspace(0., duration, 1001)])
    inertia = jaw.inertia[0, 0] + jaw.mass*np.sum((jaw.center-pivot)[1:]**2)
    results = {}
    for name, direction in (('opening', 1), ('closing', -1)):
        q, speed, accel = np.radians(states).T
        if direction < 0:
            q = np.radians(opening_deg)-q
        speed, accel = direction*speed, direction*accel
        gravity = np.array([static_gravity(jaw, pivot, [pitch], np.degrees(q))[0]
                            for pitch in pitch_angles])
        load = inertia*accel+DAMPING_NM_PER_RAD_S[2]*speed+gravity
        results[name] = q, speed, load, direction, pitch_angles
    return results, {'duration_s_one_way': duration, 'travel_deg': opening_deg,
                     'max_profile_speed_deg_s': states[:, 1].max(), 'pivot_inertia_kg_m2': inertia}


def powered_margin(profiles, preload, rate, volts, pwm=DEMO_PWM):
    result = {}
    for name, (angle, speed, load, direction, pitches) in profiles.items():
        candidates = []
        for friction in (0., UPPER_FRICTION[2]):
            torque = load + preload + rate*angle + friction*direction
            margin = np.array([motor_capacity(speed, row, volts, pwm) - abs(row) for row in torque])
            index = np.unravel_index(np.argmin(margin), margin.shape)
            candidates.append({'minimum_margin_Nm': float(margin[index]), 'demand_signed_Nm': float(torque[index]),
                               'at_jaw_deg': float(np.degrees(angle[index[1]])),
                               'at_speed_deg_s': float(np.degrees(speed[index[1]])),
                               'at_friction_Nm': float(friction), 'at_neck_pitch_deg': float(pitches[index[0]])})
        result[name] = min(candidates, key=lambda row: row['minimum_margin_Nm'])
    return result


def track_closed_wrench(bodies, pivot, pitch_limits):
    source = FIRMWARE.read_text()
    vmax = [int(re.search(rf'\bexhibit{axis}Velocity\s*=\s*(\d+)', source)[1])*.229*6
            for axis in ('Yaw', 'Pitch')]
    a_field = re.search(r'\bacceleration\[count\]\s*=\s*\{([^}]+)\}', source)[1]
    amax = [int(x)*.1*214.577 for x in a_field.split(',')[-3:-1]]
    yaws = (-vmax[0], 0., vmax[0])
    a = [(-limit, 0., limit) for limit in amax] + [(0.,)]
    extreme = []
    forces = []
    for p in np.linspace(*pitch_limits, 91):
        vel = list(product(yaws, (-vmax[1], 0., vmax[1]), (0.,)))
        speed, accel = np.radians(list(product(vel, product(*a)))).transpose(1, 0, 2)
        F, M = joint_wrenches(bodies, pivot, np.radians(p), 0., speed, accel)
        extreme.extend(M[:, 2, 0])
        forces.extend(F[:, 2, 0])
    return {'opening_torque_Nm': [-float(max(extreme)), -float(min(extreme))],
            'maximum_axial_load_N': float(np.max(np.abs(forces)))}


def audit(native, cad, grams, force_json):
    layout = json.loads((cad/'cad_parts.json').read_text())
    force = json.loads(force_json.read_text())
    if layout['source_sha256'] != digest(native) or force['cad_sha256'] != digest(native):
        raise ValueError('Force and geometry must come from the same CAD')
    if force['sliced_grams_sha256'] != digest(grams):
        raise ValueError('Use the sliced mass map from the archived force analysis')
    bodies, _, _ = load_bodies(layout, cad, json.loads(grams.read_text()))
    pivot = pos(layout['jaw_pivot_mm'])
    jaw = bodies[-1]
    opening_deg, _, speed_reg, accel_reg = jaw_config()
    profile, motion = jaw_profile(jaw, pivot, opening_deg, speed_reg, accel_reg, (-2., 0., 2.))
    pitch_guard = encoder_feedback_limits()[0]
    recovery = {}
    for name, pitch_angles in (('centered_neck', (-2., 0., 2.)),
                               ('neck_at_feedback_limits', np.linspace(*pitch_guard, 13))):
        recovery[name] = {}
        for velocity_reg in (7, speed_reg):
            approach, travel = jaw_profile(jaw, pivot, 9.8, velocity_reg, accel_reg, pitch_angles)
            for pwm in (100., 120., 160.):
                outcome = powered_margin({'closing': approach['closing']}, 0., 0., MINIMUM_VOLTS, pwm)['closing']
                recovery[name][f'PWM{int(pwm)}_velocity{velocity_reg}'] = {**outcome, 'profile': travel}
    static = -static_gravity(jaw, pivot, np.linspace(-17.21, 7.13, 501), np.linspace(0., 9.8, 98))
    source = FIRMWARE.read_text()
    closure = {}
    for key in ('exhibitJawPwm', 'exhibitJawRecoveryPwm', 'exhibitJawVelocity',
                'exhibitJawRecoveryTicks', 'exhibitJawEntryNeckTicks'):
        found = re.search(rf'\b{key}\s*=\s*(\d+)', source)
        if found:
            closure[key] = int(found[1])
    if len(closure) == 5:
        travel = closure['exhibitJawRecoveryTicks']*360./4096.
        approach, metadata = jaw_profile(jaw, pivot, travel, closure['exhibitJawVelocity'],
                                        accel_reg, (-2., 0., 2.))
        outcome = powered_margin({'closing': approach['closing']}, 0., 0., MINIMUM_VOLTS,
                                 closure['exhibitJawRecoveryPwm'])['closing']
        closure['recovery'] = {**outcome, 'profile': metadata}
    moving = track_closed_wrench(bodies, pivot, pitch_guard)
    torque_grav = max(static.max(), moving['opening_torque_Nm'][1])
    if 'exhibitJawPwm' in closure:
        cap = motor_capacity(0., 1., MINIMUM_VOLTS, closure['exhibitJawPwm'])
        closure['stationary_hold_cap_Nm'] = float(cap)
        closure['stationary_nominal_hold_margin_Nm'] = float(cap-torque_grav)
    lever = force['geometry']['jaw']['maximum_touch_lever_m']
    force_torque = TOUCH_N*lever
    stall_at_zero = motor_capacity(np.zeros(1), np.ones(1), MINIMUM_VOLTS)[0]
    torque_per_amp = servo_curves()
    current_scale = (1./torque_per_amp, 1./(torque_per_amp*WARM_SCALE))
    stand_by_a = .017
    duty = DEMO_PWM/PWM_SCALE
    linkage = force['geometry']['jaw']
    cases = {
        'free_jaw': powered_margin(profile, 0., 0., MINIMUM_VOLTS),
        'bias_over_gravity_no_breakaway': powered_margin(profile, torque_grav, .02, MINIMUM_VOLTS),
        'bias_with_0p005_return_loss': powered_margin(profile, torque_grav+.005, .02, MINIMUM_VOLTS),
        'bias_with_0p012_return_loss': powered_margin(profile, torque_grav+.012, .02, MINIMUM_VOLTS),
        'bias_against_standalone_0p25N': powered_margin(profile, torque_grav+force_torque, .02, MINIMUM_VOLTS),
    }

    def bias_budget(rate):
        # Maximum opening preload that still keeps the nominated running reserve.
        # Inspect both directions below for the selected endpoints.
        a, s, load, _, _ = profile['opening']
        cap = motor_capacity(s, np.ones_like(s), MINIMUM_VOLTS)
        return np.min(cap - REQUIRED_OPENING_RESERVE - UPPER_FRICTION[2] - load - rate*a)

    hold = {}
    for name, torque in (('nominal', torque_grav), ('incidental_0p25N', torque_grav+force_torque), ('PWM_limited_jam', stall_at_zero)):
        estimates = [stand_by_a+torque*f for f in current_scale]
        hold[name] = {'torque_Nm': float(torque), 'modeled_static_margin_Nm': float(stall_at_zero-torque),
                      'required_goal_pwm_equivalent_units': float(torque/stall_at_zero*DEMO_PWM),
                      'current_illustrative_equivalent_mA': [1000.*estimate for estimate in estimates],
                      'voltage_times_current_W': [MINIMUM_VOLTS*estimate for estimate in estimates],
                      'horn_pair_equal_shear_force_N_per_screw': float(torque*1000./linkage['horn_screw_span_mm'])}
    low_hold = {}
    for volts in (3.7, 4., 4.5, 5.):
        maximum = motor_capacity(0., 1., volts, HOLD_PWM_EXAMPLE)
        low_hold[str(volts)] = {'cap_Nm': float(maximum), 'nominal_gravity_margin_Nm': float(maximum-torque_grav),
                                'with_0p25N_margin_Nm': float(maximum-torque_grav-force_torque)}
    return {
        'cad_sha256' : digest(native), 'sliced_grams_sha256': digest(grams),'firmware_sha256': digest(FIRMWARE),
        'jaw_mass_g': jaw.mass*1000.,
        'jaw_COM_relative_to_hinge_mm': ((jaw.center-pivot)*1000.).tolist(),
        'centered_closed_static_opening_torque_Nm': -static_gravity(jaw, pivot, [0.], [0.])[0,0],
        'worst_released_pose_static_opening_torque_Nm': static.max(),
        'tracking_closed_wrench': moving, 'worst_closed_opening_budget_Nm': torque_grav,
        'incidental_force_N': TOUCH_N, 'outer_jaw_lever_m': lever, 'incidental_torque_Nm': force_torque,
        'assumed_min_voltage_V_at_actuator': MINIMUM_VOLTS, 'warm_derating': WARM_SCALE,
        'nominal_PWM_cap_fraction': duty, 'static_PWM_model_cap_Nm': stall_at_zero,
        'low_hold_PWM_example': HOLD_PWM_EXAMPLE, 'low_hold_voltage_sweep': low_hold,
        'slow_recovery_from_released_jaw': recovery, 'configured_exhibit_closure': closure,
        'electrical_hold': hold,
        'required_demo_reserve_Nm': REQUIRED_OPENING_RESERVE, 'firmware_full_jaw_profile': motion,
        'signed_neutral_jaw_demo': cases,
        'maximum_bias_preload_Nm_by_torsional_rate': {str(k): bias_budget(k) for k in (0., .01, .02, .03)},
        'motor_source': ROBOTIS,
        'scope': 'Sliced masses and nominal pivot, level base, warm DC torque/speed model. The commanded jaw demo includes '
                 '±2 degrees of centered-neck tolerance and the full existing trajectory. External contact is a separate '
                 'static disturbance. Current values are torque-equivalent estimates from manufacturer stall ratios and '
                 'standby consumption, with uncertain gear losses and PWM current ripple. No continuous thermal rating inferred.'
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('native', type=Path)
    parser.add_argument('cad', type=Path)
    parser.add_argument('grams', type=Path)
    parser.add_argument('force_json', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = audit(args.native, args.cad, args.grams, args.force_json)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
