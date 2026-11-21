"""Screen the commanded blink with CAD masses and a voltage-limited motor model."""

from argparse import ArgumentParser
from dataclasses import dataclass
from hashlib import sha256
import json
from itertools import product
from math import cos, degrees, floor, hypot, pi, radians, sin, sqrt
from pathlib import Path
import re
import runpy
import sys

import numpy as np

from multibody import cad_part_mass


ROOT = Path(__file__).resolve().parents[2]
CAMERA_FRAME_RATE_HZ = 30
STEP_S = .0004
LID_TOUCH_RADIUS_M = .01660
FACE_OPEN_DEG, FACE_SHUT_DEG = 5., 85.
ACTUATORS = {
    'm288': ((.42, .52, .60), (76., 103., 123.)),
    'm077': ((.180, .215, .228), (278., 383., 456.)),
}


@dataclass(frozen=True)
class Blink:
    inertia: float
    gravity_y: float
    gravity_z: float
    pwm: int
    speed: float
    acceleration: float
    write_period: float


def cad_parameters(cad, layout, weights):
    blink = layout['motion_geometry']['blink']
    pivots = {
        'blink_motor_horn': blink['servo_yz_mm'], 'blink_shaft_crank': blink['shaft_yz_mm'],
        'lid1': (-39., 119.), 'lid2': (-39., 119.),
    }
    radii = {'blink_drive_link': blink['radius_mm'], 'blink_lid_link': blink['lid_radius_mm']}
    phase = radians(blink['phase_deg'])
    for name in ('19_blink_servo_horn', '21_blink_shaft_crank_2',
                 '45_blink_shaft_spacer_left', '45_blink_shaft_spacer_right'):
        weights[name] = weights[name+'-b19']
    results = []
    for row in layout['parts']:
        name = row['name']
        mode = layout['world_motion'][name]
        if mode not in pivots and mode not in radii:
            continue
        body = cad_part_mass(row, cad, weights)
        if mode in pivots:
            dy, dz = body.center[1:]-np.asarray(pivots[mode])*.001
            inertia = body.inertia[0, 0]+body.mass*(dy*dy+dz*dz)
        else:
            radius = radii[mode]*.001
            dy, dz = radius*cos(phase), radius*sin(phase)
            inertia = body.mass*radius*radius
        results.append((name, body.mass, float(inertia), float(9.81*body.mass*dy), float(9.81*body.mass*dz)))
    return results


def clip(value, lo, hi):
    return min(max(value, lo), hi)


def evaluate(model, planner, volts, warm, friction, viscous, touch, delay, extra_inertia=0.,
             actuator='m288', frame_rate=CAMERA_FRAME_RATE_HZ, start_phase=0.):
    rated_stall, rated_speed = ACTUATORS[actuator]
    stall = float(np.interp(volts, (3.7, 5., 6.), rated_stall))
    no_load_speed = float(np.interp(volts, (3.7, 5., 6.), rated_speed))*pi/30
    tau = stall*warm
    pwm_limit = model.pwm/885
    inertia = model.inertia+extra_inertia
    first_write = round(delay/STEP_S)
    write_ticks = round(model.write_period/STEP_S)
    planner.next_blink = start_phase
    angle = goal = speed = 0.
    opening, shut = radians(FACE_OPEN_DEG), radians(FACE_SHUT_DEG)
    started = closed = ended = None
    min_angle = max_angle = max_demand = max_motor = max_speed = 0.
    for tick in range(round(2.2/STEP_S)):
        t = tick*STEP_S
        if tick >= first_write and (tick-first_write) % write_ticks == 0:
            frame = floor(t*frame_rate+1e-9)/frame_rate
            goal = radians(planner.blink_goal(frame))
        error = goal-angle
        ideal_speed = min(model.speed, sqrt(2*model.acceleration*abs(error)))
        if error < 0.:
            ideal_speed = -ideal_speed
        gravity = model.gravity_y*cos(angle)-model.gravity_z*sin(angle)
        pulse = touch*LID_TOUCH_RADIUS_M if .35 <= t-start_phase <= .50 else 0.
        direction = speed if abs(speed) > 1e-8 else ideal_speed
        drag = (friction+pulse)*(float(direction > 0.)-float(direction < 0.))
        resistance = drag+viscous*speed+gravity
        acceleration = clip((ideal_speed-speed)/STEP_S, -model.acceleration, model.acceleration)
        demand = inertia*acceleration+resistance
        load_factor = speed/no_load_speed
        motor = clip(demand, tau*(-pwm_limit-load_factor), tau*(pwm_limit-load_factor))
        obtained = clip((motor-resistance)/inertia, -model.acceleration, model.acceleration)
        speed = clip(speed+obtained*STEP_S, -model.speed, model.speed)
        angle += speed*STEP_S
        max_demand, max_motor = max(max_demand, abs(demand)), max(max_motor, abs(motor))
        max_speed = max(max_speed, abs(speed))
        min_angle, max_angle = min(min_angle, angle), max(max_angle, angle)
        if started is None and angle >= opening:
            started = t
        if closed is None and angle >= shut:
            closed = t
        if closed is not None and ended is None and angle <= opening:
            ended = t
    return {
        'terminal_V': volts, 'warm_stall_factor': warm, 'coulomb_drag_Nm': friction,
        'viscous_drag_Nms': viscous, 'reflected_inertia_kgm2': extra_inertia,
        'touch_N': touch, 'first_write_delay_s': delay,
        'rated_stall_Nm': stall, 'warm_pwm_zero_speed_torque_Nm': tau*pwm_limit,
        'zero_load_pwm_speed_deg_s': degrees(no_load_speed*pwm_limit),
        'lid_motion_deg': [degrees(min_angle), degrees(max_angle)],
        'open_close_open_time_s': ended-started if ended is not None else None,
        'max_speed_deg_s': degrees(max_speed), 'max_requested_drive_Nm': max_demand,
        'max_output_Nm': max_motor,
    }


def report(cad, sliced_grams, actuator='m288', extended=False, summarize=False):
    layout = json.loads((cad/'cad_parts.json').read_bytes())
    weights = sliced_grams.read_bytes()
    parts = cad_parameters(cad, layout, json.loads(weights))
    mass, inertia, gy, gz = np.asarray([row[1:] for row in parts]).sum(axis=0)
    firmware_path = ROOT/'control/openrb/R5B1/R5B1.ino'
    firmware = firmware_path.read_text()
    track_path = ROOT/'control/pc/track.py'
    sys.path.insert(0, str(track_path.parent))
    try:
        planner = runpy.run_path(str(track_path))['Planner']()
    finally:
        sys.path.pop(0)

    def register(name):
        return int(re.search(rf'{name}\[count\]\s*=\s*\{{([^}}]+)\}}', firmware)[1].split(',')[2])

    period = int(re.search(r'\bgoalPeriodMs\s*=\s*(\d+)', firmware)[1])/1000
    actuator_pwm = int(re.search(r'\bblinkFastPwm\s*=\s*(\d+)', firmware)[1]) if actuator == 'm077' else register('pwm')
    model = Blink(inertia, gy, gz, actuator_pwm, radians(register('velocity')*.229*6),
                  radians(register('acceleration')*214.577*.1), period)
    regimes = [
        ('lossless', .8, 0., 0., 0., 0.),
        ('low_drag', .8, .003, .0005, 0., 0.),
        ('nominal_drag', .8, .009, .00125, 0., 0.),
        ('twice_drag', .8, .018, .00250, 0., 0.),
        ('one_lid_touch', .8, .009, .00125, 1., 0.),
        ('warmer_with_inertia', .65, .009, .00125, 0., inertia),
    ]
    voltages = (4.5, 5.)
    trials_to_run = [(CAMERA_FRAME_RATE_HZ, 0., phase) for phase in (0., .28, .42, .56, .70, .84, .995)]
    if extended:
        voltages = (4.27, 4.5, 5., 5.25)
        regimes.extend([('bilateral_light_touch', .65, .009, .00125, .50, inertia),
                        ('warm_twice_drag', .65, .018, .00250, 0., inertia)])
        trials_to_run = list(product((24, 25, 30), (0., .2, .4, .6, .8), (0., .08, .22, .36, .50, .64, .78, .92, .995)))
    cases = {}
    for volts in voltages:
        for label, warm, dry, viscous, touch, reflected in regimes:
            durations = []
            trials = []
            for fps, phase, fraction in trials_to_run:
                case = evaluate(model, planner, volts, warm, dry, viscous, touch, fraction*period,
                                reflected, actuator, fps, phase/fps)
                if case['open_close_open_time_s'] is not None:
                    durations.append(case['open_close_open_time_s'])
                if extended:
                    case.update(camera_frame_rate_Hz=fps, blink_start_phase_s=phase/fps)
                trials.append(case)
            row = {
                'complete_cycles': len(durations),
                'duration_range_s': [min(durations), max(durations)] if durations else None,
                'all_cycles_within_S03_timing': len(durations) == len(trials) and
                    all(.8 <= duration <= 1.5 for duration in durations),
                'max_requested_drive_Nm': max(case['max_requested_drive_Nm'] for case in trials),
            }
            if summarize:
                row['trial_count'] = len(trials)
                row['min_peak_closure_deg'] = min(case['lid_motion_deg'][1] for case in trials)
                row['overall_angle_deg'] = [min(case['lid_motion_deg'][0] for case in trials),
                                            max(case['lid_motion_deg'][1] for case in trials)]
                row['max_torque_witness'] = max(trials, key=lambda case: case['max_requested_drive_Nm'])
                row['longest_or_incomplete_witness'] = max(
                    trials, key=lambda case: case['open_close_open_time_s'] or float('inf'))
            else:
                row['trials'] = trials
            cases[f'{volts:g}V_{label}'] = row
    return {
        'cad_sha256': layout['source_sha256'], 'print_mass_map_sha256': sha256(weights).hexdigest(),
        'firmware_sha256': sha256(firmware_path.read_bytes()).hexdigest(),
        'tracking_sha256': sha256(track_path.read_bytes()).hexdigest(),
        'solver_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'actuator_data': f'https://emanual.robotis.com/docs/en/dxl/x/xl330-{actuator}/',
        'method': 'Ideal position tracker with firmware acceleration/profile limits and a linear DC torque-speed envelope at Goal PWM.',
        'limits': 'Rigid linked motion, fixed end-state calibration, assumed drag and warm derate, no measured motor PID, compliance or bus voltage.',
        'camera_frame_rate_Hz': sorted(set(row[0] for row in trials_to_run)) if extended else CAMERA_FRAME_RATE_HZ,
        'goal_period_s': period, 'step_s': STEP_S,
        'velocity_profile_deg_s': degrees(model.speed), 'acceleration_profile_deg_s2': degrees(model.acceleration),
        'goal_pwm': model.pwm, 'nominal_5V_cold_static_pwm_torque_Nm': ACTUATORS[actuator][0][1]*model.pwm/885,
        'moving_mass_kg': mass, 'rigid_inertia_kgm2': inertia, 'gravity_amplitude_Nm': hypot(gy,gz),
        'touch_sensitivity_s': [.35, .50], 'touch_lever_mm': 1000*LID_TOUCH_RADIUS_M,
        'cases': cases,
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path, help='Exported CAD directory with cad_parts.json')
    parser.add_argument('sliced_grams', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--actuator', choices=ACTUATORS, default='m288')
    parser.add_argument('--extended', action='store_true', help='Scan device voltages and relative camera/write timing')
    parser.add_argument('--summary', action='store_true', help='Preserve counts, extrema and limiting trials')
    args = parser.parse_args()
    result = report(args.cad, args.sliced_grams, args.actuator, args.extended, args.summary)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    for name, row in result['cases'].items():
        print(name, row['complete_cycles'], row['duration_range_s'])
