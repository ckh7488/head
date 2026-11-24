"""Map B25 jaw candidate extrusion masses onto the loaded replay model."""

from argparse import ArgumentParser
import json
from pathlib import Path


PRINT_TO_REPLAY = {
    '09_head_frame-b25': '09_head_frame-b19',
    '36_left_cheek_servo_stay-b25': '36_left_cheek_servo_stay',
    '37_right_cheek_bearing_stay-b25': '37_right_cheek_bearing_stay',
    '32_left_eyelid-b25': '32_left_upper_lid',
}


def combine(baseline, sliced):
    old = json.loads(baseline.read_text())
    parts = {}
    for path in sliced:
        parts.update(json.loads(path.read_text()))
    weights = old | {name: mass for name, mass in parts.items() if name in old}
    for part, key in PRINT_TO_REPLAY.items():
        weights[key] = parts[part]
    weights['28_skull_front'] = parts['28_skull_front_with_camera_tray-b25']-old['25_nasal_tray']
    if weights['28_skull_front'] <= 0.:
        raise ValueError('The fused front shell must exceed the mass of the unchanged nasal tray')
    if '29_skull_rear-b25' in parts:
        weights['29_skull_rear'] = parts['29_skull_rear-b25']
    return weights, '29_skull_rear-b25' in parts


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('sliced', type=Path, nargs='+')
    args = parser.parse_args()
    masses, has_rear = combine(args.baseline, args.sliced)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(masses, indent=2)+'\n')
    print('Matched rear-shell extrusion mass' if has_rear else 'Carried B24 rear-shell extrusion mass into the replay')
