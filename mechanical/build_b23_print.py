"""Build the B23 print meshes into the native P2S project."""

from argparse import ArgumentParser
from pathlib import Path

import trimesh

from build_b21_print import REVISIONS, build
from build_b22_fused_skull import FUSED_SKULL, fuse


BASE = REVISIONS / 'b22/R5-B22-P2S.3mf'
CAMERA = '26_u20cam_slotted_bracket-B22.stl'
KEEPER = '35_hatch_two_nut_keeper.stl'
SERVICE_REPLACEMENTS = {
    '01_base_cup-B22.stl': '01_base_cup-hatch-capture.stl',
    '40-rear-cable-guide-B18.stl': '40-rear-cable-guide-service.stl',
    '42-rear-cable-cover-B18.stl': '42-rear-cable-cover-service.stl',
}
EYE_REPLACEMENTS = {
    '12_eye_tilt_cradle-B20.stl': '12_eye_tilt_cradle-B23.stl',
    '17_eye_pitch_horn_10mm.stl': '17_eye_pitch_horn_10mm-B23.stl',
    '18_eye_pitch_link_58p5mm-B21.stl': '18_eye_pitch_link_58p5mm-B23.stl',
}
YAW_REPLACEMENTS = {
    '05_yaw_servo_jaw_1.stl': '05_yaw_servo_jaw_1-B23.stl',
    '05_yaw_servo_jaw_2.stl': '05_yaw_servo_jaw_2-B23.stl',
}
LIMIT_REPLACEMENTS = {
    '02_outer_bearing_seat.stl': '02_outer_bearing_seat-B23.stl',
    '04_yaw_rotor-B22.stl': '04_yaw_rotor-B23.stl',
}
STOP_PADS = ('YawStopPadLeft.stl', 'YawStopPadRight.stl')


def build_project(output, service_prints, nose, report, source=BASE, front_shell=None):
    names = SERVICE_REPLACEMENTS.copy()
    for group in (EYE_REPLACEMENTS, YAW_REPLACEMENTS, LIMIT_REPLACEMENTS):
        present = [name for name in group.values() if (service_prints / name).is_file()]
        if present and len(present) != len(group):
            raise ValueError(f'Incomplete B23 print inputs: {sorted(set(group.values()) - set(present))}')
        if present:
            names.update(group)
    replacements = {original: (name, trimesh.load_mesh(service_prints / name))
                    for original, name in names.items()}
    replacements[CAMERA] = '26_u20cam_slotted_bracket-B23.stl', trimesh.load_mesh(nose)
    if front_shell:
        replacements[FUSED_SKULL] = '28_skull_front_with_camera_tray-B23.stl', fuse(*front_shell)
    keepers = [(service_prints / KEEPER, f'35_hatch_nut_keeper_{side}-B23.stl', xy)
               for side, xy in (('left', (128., 120.)), ('right', (148., 120.)))]
    extras = [{
        'placements': keepers,
        'template_name': CAMERA,
        'plate_number': 12,
        'prefix': 'b23_hatch_keeper',
        'relation_prefix': 'rel-b23-hatch-keeper',
        'uuid_prefix': 'r5-b23',
        'support_enabled': False,
    }]
    pad_paths = [service_prints / name for name in STOP_PADS]
    if any(path.is_file() for path in pad_paths):
        if not all(path.is_file() for path in pad_paths):
            raise ValueError('Both keyed yaw stop pads are required')
        extras.append({
            'placements': [(path, path.name, (181. + 39.*i, 104.)) for i, path in enumerate(pad_paths)],
            'template_name': '02_outer_bearing_seat.stl',
            'plate_number': 6,
            'prefix': 'b23_yaw_stop_pad',
            'relation_prefix': 'rel-b23-yaw-stop-pad',
            'uuid_prefix': 'r5-b23',
            'support_enabled': True,
        })
    build(output, replacements, report, source=source, revision='B23', extra_parts=extras,
          indexed_parts=(FUSED_SKULL,))


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--service-prints', type=Path, required=True)
    parser.add_argument('--nose', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--source', type=Path, default=BASE)
    parser.add_argument('--front-shell', nargs=3, type=Path, metavar=('SKULL_WORLD', 'TRAY_WORLD', 'TRAY_PRINT'))
    build_project(**vars(parser.parse_args()))
