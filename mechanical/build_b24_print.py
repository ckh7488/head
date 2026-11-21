"""Put the B24 front shell, neck coupling and eye-bearing mounts into the B23 P2S project."""

from argparse import ArgumentParser
from pathlib import Path

import numpy as np
import trimesh

from build_b21_print import REVISIONS, build


BASE = REVISIONS / 'b23/R5-B23-P2S.3mf'
FUSED_SKULL = '28_skull_front_with_camera_tray'
PARTS = (
    '08_pitch_horn_to_8mm_clamp',
    '13_left_eye_cradle_mount',
    '13_right_eye_cradle_mount',
)


def build_project(output, print_dir, report):
    replacements = {}
    for part in PARTS:
        path = print_dir / f'{part}-B24.stl'
        replacements[part + '.stl'] = path.name, trimesh.load_mesh(path)
    rod = print_dir/'23_left_short_lid_link-B24.stl'
    replacements['23_left_short_lid_link-B21.stl'] = rod.name, trimesh.load_mesh(rod)
    shell = print_dir/f'{FUSED_SKULL}-B24.npz'
    old_shell = f'{FUSED_SKULL}-B23.stl'
    with np.load(shell) as data:
        mesh = trimesh.Trimesh(vertices=data['vertices'], faces=data['faces'], process=False)
    replacements[old_shell] = f'{FUSED_SKULL}-B24.stl', mesh
    build(output, replacements, report, source=BASE, revision='B24', indexed_parts=(old_shell,))


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--print-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    build_project(**vars(parser.parse_args()))
