"""Run loaded neck and jaw moves with sliced masses and compare actuator margins."""

from argparse import ArgumentParser
from functools import partial
from hashlib import file_digest
import json
from pathlib import Path
import re

import numpy as np

from b20_dynamics import NORMAL_FRICTION, PWM, UPPER_FRICTION, jaw_profile_move, load_bodies, run_trial
from multibody import pos, quintic

FIRMWARE = Path(__file__).resolve().parents[2] / 'control/openrb/R5B1/R5B1.ino'


def jaw_config():
    source = FIRMWARE.read_text()
    jaw = float(re.search(r'\bjawMaxDegrees\s*=\s*([\d.]+)f;', source)[1])
    tolerance = int(re.search(r'\bjawPositionTolerance\s*=\s*(\d+)\s*;', source)[1])
    speed, acceleration = (int(re.search(rf'\b{field}\[count\]\s*=\s*\{{([^}}]+)\}}', source)[1].split(',')[-1])
                           for field in ('velocity', 'acceleration'))
    guard = (int(jaw*4096/360)+tolerance)*360/4096
    return jaw, guard, speed, acceleration


def command(t, rate, _cutoff, _profile, pitch_limits, jaw_limit, jaw_speed, jaw_acceleration, yaw_limit=60.):
    t *= rate
    lowest, highest = pitch_limits
    if t < 3.2:
        yaw = quintic(t, 3.15, 0., yaw_limit)
    else:
        yaw = quintic(t - 3.2, 6.1, yaw_limit, -yaw_limit)
    if t < 2.3:
        pitch = quintic(t, 1.4, 0., lowest)
    elif t < 5.3:
        pitch = quintic(t - 2.3, 1.7, lowest, highest)
    else:
        pitch = quintic(t - 5.3, .8, highest, 0.)
    jaw = (0., 0., 0.)
    for start in (.85, 3.2, 6.15):
        local = t - start
        if local < 0.:
            continue
        opened, duration = jaw_profile_move(local, jaw_limit, jaw_speed, jaw_acceleration)
        if local <= duration + .12:
            jaw = opened
            break
        if local <= 2 * duration + .12:
            angle, speed, acceleration = jaw_profile_move(local - duration - .12, jaw_limit,
                                                         jaw_speed, jaw_acceleration)[0]
            jaw = (jaw_limit-angle, -speed, -acceleration)
            break
    return np.radians(np.array((yaw, pitch, jaw)).T * np.array((1., rate, rate*rate))[:, None])


def audit(cad, grams, output):
    model = json.loads((cad/'cad_parts.json').read_text())
    weights = json.loads(grams.read_text())
    bodies, _, accounting = load_bodies(model, cad, weights)
    motion = model['motion_geometry']
    jaw, jaw_feedback, speed, acceleration = jaw_config()
    if not 0. < jaw <= motion['jaw_stop']['software_open_deg']:
        raise ValueError('The firmware jaw command exceeds the CAD operating range')
    from check_b22_neck import encoder_feedback_limits

    pitch_feedback, pitch_ticks, _, firmware_hash = encoder_feedback_limits()
    yaw_limit, yaw_feedback = 60., None
    duty = PWM
    low_supply = (11.1, 11.1, 5.)
    pitch_command = motion['pitch_stop']['powered_deg']
    if 'pitch_coupler' in motion:
        raw = FIRMWARE.read_text()
        duty = np.array([float(reg) for reg in re.search(r'\bpwm\[count\]\s*=\s*\{([^}]+)\}', raw)[1].split(',')[-3:]])/885.
        low_supply = (10.62, 10.62, 4.27)
        pitch_command = tuple(ticks * 360 / 4096 for ticks in pitch_ticks)
    if 'yaw_limit' in motion:
        source = FIRMWARE.read_text()
        yaw_ticks = int(re.search(r'\bneckYawCalibrationTicks\s*=\s*(\d+)\s*;', source)[1])
        tolerance = int(re.search(r'\bpositionTolerance\s*=\s*(\d+)\s*;', source)[1])
        yaw_limit = yaw_ticks * 360 / 4096
        yaw_feedback = (yaw_ticks + tolerance) * 360 / 4096
        left, right = motion['yaw_limit']['nominal_stop_deg']
        if not left < -yaw_feedback < 0 < yaw_feedback < right:
            raise ValueError('The guarded yaw travel must stay inside both CAD yaw stops')
    trajectory = partial(command, pitch_limits=pitch_command, yaw_limit=yaw_limit,
                         jaw_limit=jaw, jaw_speed=speed*.229*6., jaw_acceleration=acceleration*214.577*.1)
    output.mkdir(parents=True, exist_ok=True)
    trials = {}
    for name, volts, derating, friction, backlash in (
        ('nominal', (12., 12., 5.), .85, NORMAL_FRICTION, .35),
        ('low_supply_warm', low_supply, .55, UPPER_FRICTION, .75),
    ):
        row = run_trial(bodies, pos(model['jaw_pivot_mm']), output / name, volts=volts,
                        derating=derating, friction=friction, backlash_deg=backlash,
                        firmware_profile=True, trajectory=trajectory, pwm=duty)
        yaw, pitch, jaw_range = row['simulated_travel_deg']
        row['operating_envelope_pass'] = bool(min(row['minimum_planned_speed_margin_Nm']) > 0.
                                              and (yaw_feedback is None or -yaw_feedback <= yaw[0] <= yaw[1] <= yaw_feedback)
                                              and pitch_feedback[0] <= pitch[0] <= pitch[1] <= pitch_feedback[1]
                                              and jaw_range[1] < jaw_feedback)
        trials[name] = row
        print(name, 'motor torque N·m', np.round(row['torque_demand_bound_Nm'], 4).tolist(),
              'minimum estimated margin N·m', np.round(row['minimum_planned_speed_margin_Nm'], 4).tolist(),
              'motion ranges °', np.round(row['simulated_travel_deg'], 3).tolist(), flush=True)
    with grams.open('rb') as source:
        grams_hash = file_digest(source, 'sha256').hexdigest()
    passed = all(row['operating_envelope_pass'] for row in trials.values())
    report = {'cad_sha256': model['source_sha256'], 'sliced_grams_sha256': grams_hash,
              'firmware_sha256': firmware_hash, 'status': 'pass' if passed else 'fail',
              'jaw_command_deg': jaw, 'jaw_feedback_limit_deg': jaw_feedback,
              'jaw_profile_velocity_reg': speed, 'jaw_profile_acceleration_reg': acceleration,
              'joint_order': ['neck_yaw', 'neck_pitch', 'jaw'], 'trials': trials,
              'pitch_assembly_g': 1000.*(bodies[1].mass+bodies[2].mass),
              'pitch_link_g': accounting['PitchLimitLink']['mass_g'],
              'scope': 'Installed masses, conservative actuator derating and supplied friction cases. '
                       'Small steel link treated as a rigid part of the head for normal drive screening. '
                       'Servo control is a fitted PD model without wiring load or continuous temperature validation.'}
    if yaw_feedback is not None:
        report.update(yaw_command_limit_deg=yaw_limit, yaw_feedback_limit_deg=yaw_feedback)
    (output / 'drive.json').write_text(json.dumps(report, indent=2)+'\n')
    return passed


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('grams', type=Path)
    parser.add_argument('output', type=Path)
    raise SystemExit(0 if audit(**vars(parser.parse_args())) else 1)
