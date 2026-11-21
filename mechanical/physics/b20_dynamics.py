"""Rigid-body screening of the B20 neck and jaw using P2S extrusion masses."""

from argparse import ArgumentParser
import csv
from hashlib import sha256
import json
from math import cos, sin
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco as mj
import numpy as np

from multibody import (
    Mass, NECK_PIVOT, YAW_PIVOT, OPTIONAL_BALLAST, PRINT_NAMES, ballast_mass,
    cad_part_mass, combine, gimbal_model, motion_trace, pos, quintic,
)


PRINT_PARTS = {
    'Part011': '07-yoke-b18',
    'Part019': '09_head_frame-b19',
    'Part024': '12_eye_tilt_cradle-b20',
    'Part039': 'xl330_eye_yaw_front_plate-b19',
    'Part047': '19_blink_servo_horn-b19',
    'Part054': '21_blink_shaft_crank_2-b19',
    'Part066': '26_u20cam_slotted_bracket-b19',
    'BlinkCollarLeft': '45_blink_shaft_spacer_left-b19',
    'BlinkCollarRight': '45_blink_shaft_spacer_right-b19',
    'ID5EHKeeper': 'id5-keeper-b19',
    'Jaw_36_left_jaw_servo_stay': '36_left_cheek_servo_stay',
    'Jaw_37_right_jaw_bearing_stay': '37_right_cheek_bearing_stay',
}
JAW_PRINT = ('Jaw_30_moving_jaw', 'Jaw_38_left_jaw_drive_arm', 'Jaw_39_right_jaw_pivot_arm')
JAW_PRINT_KEY = '30_38_39_jaw_one_piece-b20'
DECORATIVE = {'Part030', 'Part031', 'Part034', 'Part035'}
JOINT_NAMES = ('neck yaw', 'neck pitch', 'jaw')
GRAVITY = np.array([0., 0., -9.81])
PWM = np.array([270., 300., 160.]) / 885.
PROPORTIONAL_GAIN = np.array([3.8, 4.0, .85])
DERIVATIVE_GAIN = np.array([.33, .29, .018])
NORMAL_FRICTION = np.array([.022, .020, .005])
UPPER_FRICTION = np.array([.045, .042, .012])
HIGH_PITCH_FRICTION = np.array([.022, .042, .005])
JAW_PROFILE_SPEED = 95. * .229 * 6.  # deg/s, Profile Velocity register
JAW_PROFILE_ACCELERATION = 40. * 214.577 * .1  # deg/s², Profile Acceleration register


def cad_volume(row):
    if 'solids' in row:
        return sum(solid['volume'] for solid in row['solids'])
    return row['mesh_volume_mm3']


def load_bodies(cad, directory, sliced_grams):
    bins = {name: [] for name in ('yaw', 'head', 'jaw', 'ballast_mount')}
    records = cad['parts']
    jaw_volume = sum(cad_volume(row) for row in records if row['name'] in JAW_PRINT)
    accounting = {}
    for row in records:
        name = row['name']
        if name == 'BallastStack' or name in DECORATIVE:
            continue
        weights = sliced_grams
        if name in JAW_PRINT or name in PRINT_PARTS:
            alias = PRINT_NAMES.get(name, row['label'].lower().replace(' ', '_'))
            grams = (sliced_grams[JAW_PRINT_KEY] * cad_volume(row) / jaw_volume
                     if name in JAW_PRINT else sliced_grams[PRINT_PARTS[name]])
            weights = {alias: grams}
            row = dict(row, printed=True)
        motion = row['motion']
        group = 'ballast_mount' if name in OPTIONAL_BALLAST else {'pan': 'yaw', 'jaw': 'jaw'}.get(motion, 'head')
        mass = cad_part_mass(row, directory, weights)
        accounting[name] = {'group': group, 'mass_g': 1000 * mass.mass}
        bins[group].append(mass)
    # Harness and smaller hardware absent from the CAD, separate from modeled fasteners.
    for name, mass, center in [('head', .020, (0., 8., 129.)), ('yaw', .012, (0., 5., 70.))]:
        bins[name].append(Mass(mass, pos(center), mass * np.diag((.001, .001, .0015))))
        accounting[f'{name}_additional_hardware'] = {'group': name, 'mass_g': 1000 * mass}
    bodies = tuple(combine(bins[key]) for key in ('yaw', 'head', 'jaw'))
    ballast_mount = combine(bins['ballast_mount']) if bins['ballast_mount'] else None
    return bodies, ballast_mount, accounting


def x_rotation(angle):
    c, s = cos(angle), sin(angle)
    return np.array([(1, 0, 0), (0, c, -s), (0, s, c)])


def z_rotation(angle):
    c, s = cos(angle), sin(angle)
    return np.array([(c, -s, 0), (s, c, 0), (0, 0, 1)])


def moving_wrench(part, rotation, omega, alpha, offset, pivot_acceleration):
    acceleration = pivot_acceleration + np.cross(alpha, offset) + np.cross(omega, np.cross(omega, offset))
    force = part.mass * (acceleration - GRAVITY)
    inertia = rotation @ part.inertia @ rotation.T
    moment = inertia @ alpha + np.cross(omega, inertia @ omega) + np.cross(offset, force)
    return force, moment


def pitch_joint_wrench(bodies, jaw_pivot, angles, velocity, acceleration):
    """Required reaction at the neck-pitch pivot, independent of the servo model."""
    yaw, pitch, jaw = angles
    yaw_rotation = z_rotation(yaw)
    head_rotation = yaw_rotation @ x_rotation(pitch)
    yaw_axis = np.array([0., 0., 1.])
    pitch_axis = yaw_rotation[:, 0]
    axis_rate = velocity[0] * np.cross(yaw_axis, pitch_axis)
    head_omega = velocity[0] * yaw_axis + velocity[1] * pitch_axis
    head_alpha = acceleration[0] * yaw_axis + acceleration[1] * pitch_axis + velocity[1] * axis_rate
    head, lower_jaw = bodies[1:]
    head_force, head_moment = moving_wrench(head, head_rotation, head_omega, head_alpha,
                                         head_rotation @ (head.center - NECK_PIVOT), np.zeros(3))
    jaw_offset = head_rotation @ (jaw_pivot - NECK_PIVOT)
    jaw_acceleration = np.cross(head_alpha, jaw_offset) + np.cross(head_omega, np.cross(head_omega, jaw_offset))
    jaw_rotation = head_rotation @ x_rotation(jaw)
    jaw_force, jaw_moment = moving_wrench(lower_jaw, jaw_rotation, head_omega + velocity[2] * pitch_axis,
                                        head_alpha + acceleration[2] * pitch_axis + velocity[2] * axis_rate,
                                        jaw_rotation @ (lower_jaw.center - jaw_pivot), jaw_acceleration)
    force = head_force + jaw_force
    moment = head_moment + jaw_moment + np.cross(jaw_offset, jaw_force)
    axial = force @ pitch_axis
    drive = moment @ pitch_axis
    return np.array([abs(drive), np.linalg.norm(force - axial * pitch_axis),
                     abs(axial), np.linalg.norm(moment - drive * pitch_axis)])


def wrench_summary(values):
    return dict(zip(('pitch_torque_Nm', 'radial_reaction_N', 'axial_reaction_N',
                     'non_drive_moment_Nm'), np.max(values, axis=0).tolist(), strict=True))


def static_wrenches(bodies, jaw_pivot):
    return np.array([pitch_joint_wrench(bodies, jaw_pivot, np.radians([0, pitch, jaw]),
                                         np.zeros(3), np.zeros(3))
                     for pitch in np.linspace(-15., 6., 43) for jaw in (0., 13.)])


def added_mass(mass, offset):
    return Mass(mass, NECK_PIVOT + pos(offset), np.eye(3) * mass * .00003)


def motor_parameters(volts, derating):
    # ROBOTIS publishes a brief stall test and no-load speed, not a continuous rating.
    stall = np.array([np.interp(v, [9., 11.1, 12.], [1., 1.4, 1.5]) for v in volts[:2]]
                     + [np.interp(volts[2], [3.7, 5., 6.], [.42, .52, .60])])
    free_rpm = np.array([np.interp(v, [9., 11.1, 12.], [47., 57., 61.]) for v in volts[:2]]
                        + [np.interp(volts[2], [3.7, 5., 6.], [76., 103., 123.])])
    return stall, free_rpm * np.pi / 30., derating


def capacity(parameters, speed, direction=1., pwm=PWM):
    stall, free_speed, derating = parameters
    # Back EMF reduces drive in the direction of travel. Cap braking at the zero-speed estimate.
    return stall * derating * np.clip(pwm - np.sign(direction) * speed / free_speed, 0., pwm)


def model_xml(bodies, jaw_pivot, motor, friction, pwm=PWM):
    xml = ET.fromstring(gimbal_model(bodies, jaw_pivot, capacity(motor, 0, pwm=pwm), friction, .001))
    for joint in xml.findall('.//joint'):
        # Let loss of control show up as overtravel instead of adding a fictitious brake.
        joint.set('limited', 'false')
    return ET.tostring(xml, encoding='unicode')


def jaw_profile_move(t, travel, speed_limit=JAW_PROFILE_SPEED, acceleration_limit=JAW_PROFILE_ACCELERATION):
    accel_time = min(speed_limit / acceleration_limit, np.sqrt(travel / acceleration_limit))
    peak_speed = accel_time * acceleration_limit
    cruise_time = max(0., (travel - peak_speed * accel_time) / peak_speed)
    duration = 2 * accel_time + cruise_time
    if t < accel_time:
        state = (.5 * acceleration_limit * t**2, acceleration_limit * t, acceleration_limit)
    elif t < accel_time + cruise_time:
        state = (peak_speed * (t - .5 * accel_time), peak_speed, 0.)
    elif t < duration:
        remaining = duration - t
        state = (travel - .5 * acceleration_limit * remaining**2,
                 acceleration_limit * remaining, -acceleration_limit)
    else:
        state = (travel, 0., 0.)
    return state, duration


def jaw_profile(t):
    for start, peak in ((2.75, 10.), (3.5, 13.), (7.05, 12.)):
        local = t - start
        if local < 0:
            continue
        opened, duration = jaw_profile_move(local, peak)
        if local < duration + .12:
            return opened
        if local < 2 * duration + .12:
            (angle, speed, acceleration), _ = jaw_profile_move(local - duration - .12, peak)
            return peak - angle, -speed, -acceleration
    return 0., 0., 0.


def request(t, rate, pitch_cut, firmware_profile):
    if pitch_cut:
        pitch, speed, accel = quintic(t, 1.25, 0., np.deg2rad(4.))
        return np.array([0., pitch, 0.]), np.array([0., speed, 0.]), np.array([0., accel, 0.])
    angles, speed, accel = motion_trace(t * rate, fast_pitch=True)
    if firmware_profile:
        angles[2], speed[2], accel[2] = np.radians(jaw_profile(t * rate))
    return angles, speed * rate, accel * rate**2


def trace_fields():
    yield 'time_s'
    for joint in ('yaw', 'pitch', 'jaw'):
        for field in ('goal_deg', 'angle_deg', 'speed_deg_s', 'torque_Nm', 'capacity_Nm', 'inverse_bound_Nm'):
            yield f'{joint}_{field}'


def run_trial(bodies, jaw_pivot, output, *, volts, derating, friction, backlash_deg,
              rate=1., pitch_cut=False, firmware_profile=False, amplitude=(1., 1., 1.),
              trajectory=request, pwm=PWM):
    motor = motor_parameters(volts, derating)
    xml = model_xml(bodies, jaw_pivot, motor, friction, pwm)
    output.with_suffix('.xml').write_text(xml)
    model = mj.MjModel.from_xml_string(xml)
    actual, ideal = mj.MjData(model), mj.MjData(model)
    backup_friction = model.dof_frictionloss.copy()
    dt = model.opt.timestep
    duration = 2.65 if pitch_cut else 10.2 / rate
    cutoff = 2. if pitch_cut else float('inf')
    trace, wrenches, deviations, saturated = [], [], [], []
    first_out_of_pitch_range = None
    max_inverse, max_actual, max_velocity = np.zeros((3, 3))
    min_angle, max_angle = np.full(3, np.inf), np.full(3, -np.inf)
    min_demand_margin = np.full(3, np.inf)
    static_agreement = 0.
    amplitude = np.asarray(amplitude)
    for i in range(round(duration / dt) + 1):
        t = i * dt
        goal, speed, accel = np.asarray(trajectory(t, rate, pitch_cut, firmware_profile)) * amplitude
        delta = goal - actual.qpos
        effective = np.sign(delta) * np.maximum(np.abs(delta) - np.deg2rad(backlash_deg) / 2, 0.)
        requested = PROPORTIONAL_GAIN * effective + DERIVATIVE_GAIN * (speed - actual.qvel)
        available = capacity(motor, actual.qvel, requested, pwm=pwm)
        actual.ctrl[:] = np.clip(requested, -available, available)
        if t >= cutoff:
            actual.ctrl[1] = 0.
        ideal.qpos[:], ideal.qvel[:], ideal.qacc[:] = goal, speed, accel
        model.dof_frictionloss[:] = 0.
        mj.mj_inverse(model, ideal)
        model.dof_frictionloss[:] = backup_friction
        inverse = np.abs(ideal.qfrc_inverse) + friction
        max_inverse = np.maximum(max_inverse, inverse)
        max_actual = np.maximum(max_actual, np.abs(actual.ctrl))
        max_velocity = np.maximum(max_velocity, np.abs(actual.qvel))
        min_angle = np.minimum(min_angle, actual.qpos)
        max_angle = np.maximum(max_angle, actual.qpos)
        min_demand_margin = np.minimum(min_demand_margin, capacity(motor, speed, ideal.qfrc_inverse, pwm=pwm) - inverse)
        deviations.append(np.degrees(np.abs(delta)))
        saturated.append(np.abs(requested) > available + 1e-10)
        pitch_deg = np.degrees(actual.qpos[1])
        if t >= cutoff and first_out_of_pitch_range is None and not -15. <= pitch_deg <= 6.:
            first_out_of_pitch_range = t - cutoff
        if i % 10 == 0 or first_out_of_pitch_range is not None:
            reaction = pitch_joint_wrench(bodies, jaw_pivot, goal, speed, accel)
            wrenches.append(reaction)
            if max(abs(speed)) < 1e-14 and max(abs(accel)) < 1e-14:
                static_agreement = max(static_agreement, abs(reaction[0] - abs(ideal.qfrc_inverse[1])))
            trace.append([t, *np.column_stack((np.degrees(goal), np.degrees(actual.qpos),
                                              np.degrees(actual.qvel), actual.ctrl, available, inverse)).ravel()])
        if first_out_of_pitch_range is not None:
            break
        mj.mj_step(model, actual)
    trace = np.asarray(trace)
    if not np.isfinite(trace).all() or static_agreement > 1e-8:
        raise ValueError(f'Invalid simulation or inconsistent static torque: {output.name}, {static_agreement}')
    fields = list(trace_fields())
    with output.with_suffix('.csv').open('w', newline='') as outf:
        writer = csv.writer(outf)
        writer.writerow(fields)
        writer.writerows(np.round(trace, 7))
    result = {
        'supply_V': volts, 'derating_factor': derating, 'friction_Nm': friction.tolist(),
        'controller_deadband_deg': backlash_deg, 'command_rate_scale': rate,
        'command_amplitude_scale': amplitude.tolist(),
        'uses_firmware_jaw_profile': firmware_profile,
        'torque_demand_bound_Nm': max_inverse.tolist(), 'applied_torque_peak_Nm': max_actual.tolist(),
        'shaft_speed_peak_deg_s': np.degrees(max_velocity).tolist(),
        'simulated_travel_deg': np.degrees(np.column_stack((min_angle, max_angle))).tolist(),
        'zero_speed_model_cap_Nm': capacity(motor, 0, pwm=pwm).tolist(),
        'minimum_planned_speed_margin_Nm': min_demand_margin.tolist(),
        'error_peak_deg': np.max(deviations, axis=0).tolist(),
        'error_p95_deg': np.percentile(deviations, 95, axis=0).tolist(),
        'saturated_percent': (100 * np.mean(saturated, axis=0)).tolist(),
        'pitch_joint_envelope': wrench_summary(wrenches),
        'static_inverse_torque_check_delta_Nm': static_agreement,
    }
    if pitch_cut:
        pitch_angle = trace[:, fields.index('pitch_angle_deg')]
        before = np.interp(cutoff, trace[:, 0], pitch_angle)
        result['pitch_power_cut'] = {
            'start_deg': before, 'torque_cut_at_s': cutoff,
            'first_outside_command_range_s_after_cut': first_out_of_pitch_range,
            'angle_change_deg_after_cut': {
                str(milliseconds): np.interp(cutoff + milliseconds / 1000., trace[:, 0], pitch_angle) - before
                for milliseconds in (20, 50, 100, 250, 500)
                if cutoff + milliseconds / 1000. <= trace[-1, 0]
            },
        }
    else:
        jaw_goal = trace[:, fields.index('jaw_goal_deg')]
        jaw_angle = trace[:, fields.index('jaw_angle_deg')]
        at_peak = np.argmax(jaw_goal)
        result['jaw_commanded_peak_deg'] = jaw_goal[at_peak]
        result['jaw_angle_at_peak_command_deg'] = jaw_angle[at_peak]
    return result


def summarize(part):
    return {'mass_kg': part.mass, 'com_mm': (part.center * 1000).tolist(), 'inertia_kg_m2': part.inertia.tolist()}


def simulate(cad_dir, grams_file, output):
    cad = json.loads((cad_dir / 'cad_parts.json').read_text())
    bodies, ballast_mount, accounting = load_bodies(cad, cad_dir, json.loads(grams_file.read_text()))
    jaw_pivot = pos(cad['jaw_pivot_mm'])
    nominal_static = static_wrenches(bodies, jaw_pivot)
    forward = (bodies[0], combine([bodies[1], added_mass(.075, (0, -70, 45))]), bodies[2])
    forward_static = static_wrenches(forward, jaw_pivot)
    ballast = cad['motion_geometry']['ballast'] if ballast_mount is not None else {'maximum_plates': 0}
    static_options = []
    balance = {}
    for plates in range(ballast['maximum_plates'] + 1):
        if plates:
            kit = combine([ballast_mount, ballast_mass(ballast, plates)])
            balanced = (forward[0], combine([forward[1], kit]), forward[2])
            nominal_balanced = (bodies[0], combine([bodies[1], kit]), bodies[2])
        else:
            balanced, nominal_balanced = forward, bodies
        nominal_reaction = wrench_summary(static_wrenches(nominal_balanced, jaw_pivot))
        forward_reaction = wrench_summary(static_wrenches(balanced, jaw_pivot))
        static_options.append({'plates': plates, 'nominal_pitch_gravity_Nm': nominal_reaction['pitch_torque_Nm'],
                               'forward_pitch_gravity_Nm': forward_reaction['pitch_torque_Nm']})
        balance[plates] = balanced
    forward_best = min(static_options, key=lambda row: row['forward_pitch_gravity_Nm'])['plates']
    options = {
        'nominal': (bodies, [12., 12., 5.], .85, NORMAL_FRICTION, .35, 1., False),
        'low_voltage': (bodies, [9., 9., 3.7], .85, NORMAL_FRICTION, .35, 1., False),
        'warm': (bodies, [12., 12., 5.], .55, UPPER_FRICTION, .75, 1., False),
        'forward_low_warm': (forward, [9., 9., 3.7], .55, UPPER_FRICTION, .75, 1., False),
        'forward_low_warm_slow': (forward, [9., 9., 3.7], .55, UPPER_FRICTION, .75, .5, False),
        'forward_low_warm_balanced': (balance[forward_best], [9., 9., 3.7], .55, UPPER_FRICTION, .75, 1., False),
        'power_cut_nominal': (bodies, [12., 12., 5.], .85, NORMAL_FRICTION, .35, 1., True),
        'power_cut_nominal_high_friction': (bodies, [12., 12., 5.], .85, HIGH_PITCH_FRICTION, .35, 1., True),
        'power_cut_forward': (forward, [12., 12., 5.], .85, NORMAL_FRICTION, .35, 1., True),
    }
    trials = {}
    for name, (load, volts, scale, drag, backlash, rate, cutoff) in options.items():
        trial = run_trial(load, jaw_pivot, output / name, volts=volts, derating=scale, friction=drag,
                          backlash_deg=backlash, rate=rate, pitch_cut=cutoff)
        trials[name] = trial
        print(name, 'peak requested', np.round(trial['torque_demand_bound_Nm'], 4),
              'peak tracking error', np.round(trial['error_peak_deg'], 2), flush=True)
    for name in ('nominal', 'forward_low_warm'):
        load, volts, scale, drag, backlash, rate, _ = options[name]
        trial_name = f'{name}_firmware_profile'
        trial = run_trial(load, jaw_pivot, output / trial_name, volts=volts, derating=scale, friction=drag,
                          backlash_deg=backlash, rate=rate, firmware_profile=True)
        trials[trial_name] = trial
        print(trial_name, 'peak requested', np.round(trial['torque_demand_bound_Nm'], 4),
              'peak tracking error', np.round(trial['error_peak_deg'], 2), flush=True)
    narrowed_motion = (1., .75, .90)
    for name in ('nominal', 'forward_low_warm'):
        load, volts, scale, drag, backlash, _, _ = options[name]
        trial_name = f'{name}_inward_slow_profile'
        trial = run_trial(load, jaw_pivot, output / trial_name, volts=volts, derating=scale, friction=drag,
                          backlash_deg=backlash, rate=.5, firmware_profile=True, amplitude=narrowed_motion)
        trials[trial_name] = trial
        print(trial_name, 'peak requested', np.round(trial['torque_demand_bound_Nm'], 4),
              'simulated travel', np.round(trial['simulated_travel_deg'], 2), flush=True)
    envelopes = {
        'nominal_static': wrench_summary(nominal_static), 'forward_static': wrench_summary(forward_static),
        'nominal_moving': trials['nominal']['pitch_joint_envelope'],
        'forward_moving': trials['forward_low_warm']['pitch_joint_envelope'],
    }
    aggregate = {field: max(case[field] for case in envelopes.values()) for field in envelopes['nominal_static']}
    pivoting = combine(bodies[1:])
    return {
        'source_sha256': cad['source_sha256'], 'sliced_grams_sha256': sha256(grams_file.read_bytes()).hexdigest(),
        'mujoco_version': mj.__version__, 'joint_order': JOINT_NAMES,
        'pivots_mm': {'neck_yaw': (YAW_PIVOT * 1000).tolist(), 'neck_pitch': (NECK_PIVOT * 1000).tolist(),
                      'jaw': cad['jaw_pivot_mm']},
        'mass_properties': dict(zip(('yaw_carrier', 'head', 'jaw'), map(summarize, bodies), strict=True)),
        'pitch_assembly': summarize(pivoting),
        'pitch_com_from_axis_mm': ((pivoting.center - NECK_PIVOT) * 1000).tolist(),
        'parts': accounting, 'torque_model': {
            'firmware_pwm_duty': PWM.tolist(), 'proportional_gain_Nm_rad': PROPORTIONAL_GAIN.tolist(),
            'derivative_gain_Nm_s_rad': DERIVATIVE_GAIN.tolist(),
            'firmware_jaw_profile_speed_deg_s': JAW_PROFILE_SPEED,
            'firmware_jaw_profile_acceleration_deg_s2': JAW_PROFILE_ACCELERATION,
            'manufacturer_sources': ['https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#specifications',
                                     'https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#specifications'],
            'scope': [
                'Rated stall and no-load speed are input points for a linear PWM/voltage/speed estimate. Derating is sensitivity, not a continuous motor rating.',
                'Controller is a PD approximation without perfect gravity compensation. Actual Dynamixel gains, stiction and stall endurance need measurement.',
                'Firmware-profile trials use the configured jaw velocity and acceleration setpoints, a triangle/trapezoid profile, and 120 ms at each opening. Other jaw traces are command stress cases.',
                'Rigid links and an idealized pivot are modeled. Cable contacts, tooth interference, deformation and printed joint slip are excluded.',
                'P2S slicer masses are applied to uniform CAD inertia. Decorative eye finishes are included in the eye allowance. Fused jaw mass is apportioned by the CAD volumes.',
                'Forward sensitivity adds 75 g at (0, -70, +45) mm from the pitch pivot.',
                'Power-cut traces stop at the first departure from the configured pitch range. The model does not predict the consequences of contact beyond that range.',
            ],
        },
        'pitch_joint_envelope': aggregate, 'pitch_joint_envelopes': envelopes,
        'ballast_static_options': static_options, 'forward_balanced_plates': forward_best, 'trials': trials,
    }


def simulate_jaw_touch(cad_dir, grams_file, output):
    cad = json.loads((cad_dir / 'cad_parts.json').read_text())
    stop = cad['motion_geometry'].get('jaw_stop')
    bodies, _, _ = load_bodies(cad, cad_dir, json.loads(grams_file.read_text()))
    motor = motor_parameters([12., 12., 5.], .85)
    xml = ET.fromstring(model_xml(bodies, pos(cad['jaw_pivot_mm']), motor, NORMAL_FRICTION))
    actuators = xml.find('actuator')
    for name in ('neck_yaw', 'neck_pitch'):
        body = xml.find(f'.//body[@name="{name}"]')
        body.remove(body.find('joint'))
        actuators.remove(actuators.find(f'motor[@joint="{name}"]'))
    if stop:
        stop_joint = xml.find('.//joint[@name="jaw"]')
        stop_joint.set('limited', 'true')
        stop_joint.set('range', f'{np.deg2rad(-10.)} {np.deg2rad(stop["nominal_contact_deg"])}')
    xml = ET.tostring(xml, encoding='unicode')
    (output / 'jaw-touch.xml').write_text(xml)
    model = mj.MjModel.from_xml_string(xml)
    dt = model.opt.timestep
    lever, cycle_start = .058, .2
    opening = stop['software_open_deg'] if stop else 10.
    _, travel_time = jaw_profile_move(0., opening)
    close_start = cycle_start + travel_time + .12
    touch_start = close_start + .075
    touch_time = .15
    columns = ('time_s', 'goal_deg', 'goal_speed_deg_s', 'angle_deg', 'speed_deg_s',
               'external_force_N', 'external_torque_Nm', 'applied_motor_torque_Nm',
               'estimated_motor_capacity_Nm', 'saturated')
    trials = {}
    baseline = None
    for force in (0., .25, .5, 1.):
        state = mj.MjData(model)
        rows = []
        for i in range(round(1.4 / dt) + 1):
            t = i * dt
            if t < cycle_start:
                goal, goal_speed = 0., 0.
            elif t < close_start:
                (goal, goal_speed, _), _ = jaw_profile_move(t - cycle_start, opening)
            else:
                (offset, closing_speed, _), _ = jaw_profile_move(t - close_start, opening)
                goal, goal_speed = opening - offset, -closing_speed
            pulse_time = (t - touch_start) / touch_time
            touch_force = force * sin(np.pi * pulse_time)**2 if 0. < pulse_time < 1. else 0.
            state.qfrc_applied[0] = touch_force * lever
            angle, speed = state.qpos[0], state.qvel[0]
            error = np.deg2rad(goal) - angle
            effective = np.sign(error) * max(abs(error) - np.deg2rad(.35) / 2, 0.)
            requested = PROPORTIONAL_GAIN[2] * effective + DERIVATIVE_GAIN[2] * (np.deg2rad(goal_speed) - speed)
            available = capacity(motor, speed, requested)[2]
            state.ctrl[0] = np.clip(requested, -available, available)
            rows.append((t, goal, goal_speed, np.rad2deg(angle), np.rad2deg(speed),
                         touch_force, state.qfrc_applied[0], state.ctrl[0], available, abs(requested) > available))
            mj.mj_step(model, state)
        trace = np.array(rows)
        if not np.isfinite(trace).all():
            raise ValueError(f'Jaw touch trace is nonfinite for {force:g} N')
        if baseline is None:
            baseline = trace[:, 3].copy()
        label = f'{force:g}N'
        with (output / f'jaw-touch-{label}.csv').open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(np.round(trace, 7))
        in_touch = (trace[:, 0] >= touch_start) & (trace[:, 0] < touch_start + touch_time)
        still_closing = in_touch & (trace[:, 2] < -1.)
        pause = still_closing & (trace[:, 4] >= -1.) & (trace[:, 5] > force * .1)
        trials[label] = {
            'external_peak_force_N': force,
            'external_peak_torque_Nm': force * lever,
            'maximum_opening_deg': float(trace[:, 3].max()),
            'maximum_angle_lag_vs_baseline_deg': float(max(trace[in_touch, 3] - baseline[in_touch])),
            'motor_torque_peak_during_touch_Nm': float(max(abs(trace[in_touch, 7]))),
            'motor_saturation_during_touch_percent': float(100 * np.mean(trace[in_touch, 9])),
            'pause_or_reversal_during_closing_ms': float(1000 * dt * np.sum(pause)),
            'angle_at_touch_release_deg': float(np.interp(touch_start + touch_time, trace[:, 0], trace[:, 3])),
            'angle_250_ms_after_release_deg': float(np.interp(touch_start + touch_time + .25, trace[:, 0], trace[:, 3])),
        }
    return {
        'source_sha256': cad['source_sha256'], 'sliced_grams_sha256': sha256(grams_file.read_bytes()).hexdigest(),
        'mujoco_version': mj.__version__, 'nominal_jaw_supply_V': 5., 'motor_derating_factor': .85,
        'lever_mm': lever * 1000, 'jaw_opening_command_deg': opening,
        'nominal_jaw_opening_stop_deg': stop['nominal_contact_deg'] if stop else None,
        'pulse_start_s': touch_start, 'pulse_duration_s': touch_time,
        'scope': ('Neck supported at neutral. A smooth opening torque resists closure and then releases. '
                  'The specified input force produces a modeled motion and motor demand. '
                  'Pinch force and automatic stopping require separate evidence.'),
        'trials': trials,
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--sliced-grams', type=Path, required=True)
    parser.add_argument('--jaw-touch', action='store_true', help='Run a separate jaw closing disturbance test')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    runner, filename = (simulate_jaw_touch, 'jaw-touch.json') if args.jaw_touch else (simulate, 'b20-dynamics.json')
    report = runner(args.cad, args.sliced_grams, args.output)
    (args.output / filename).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
