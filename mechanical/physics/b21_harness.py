"""Check retained harness crossings around the B21 jaw in representative poses."""

from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from itertools import product
import json
from math import ceil
from pathlib import Path

import numpy as np
import trimesh

from b20_harness import CHIN, JAW_STEP_DEG, POSES as B20_POSES, capture
from wiring_check import Scene, read
from wiring_motion import matrices

ROOT = Path(__file__).resolve().parents[2]
CLEARANCE_BANDS = ((10.25, 1., JAW_STEP_DEG), (11., .25, .0625), (11.175, .125, .025))
WIRE_NAMES = {'USB-Camera', *(f'motor{axis}-{line}' for axis in (3, 5) for line in ('power', 'return', 'data'))}
POSES = B20_POSES + (
    (-60, 6, -8, 0, 0), (-60, 6, -8, 30, 0), (-45, 6, 8, 0, 0), (-20, 6, -8, 0, 0),
    (20, 6, -8, 0, 0), (50, 6, -8, 0, 0), (55, 6, -8, 30, 0), (60, 6, 8, 0, 0),
    (60, 6, 8, 30, 0), (60, -15, -8, 30, 0), (-60, -15, 8, 30, 0), (0, 6, 8, 30, 0),
    (0, 0, 8, 0, 0), (-55, 6, 4, 0, 0), (-30, 6, -4, 30, 0), (-10, 6, 0, 0, 0),
    (5, 6, 0, 30, 0), (37, 6, -4, 0, 0), (57, 6, 4, 30, 0), (-60, 3, 8, 0, 0),
    (60, 3, -8, 30, 0), (0, 3, 8, 30, 0), (40, -3, 4, 0, 0), (-45, -8, -4, 30, 0),
    (60, 0, -8, 0, 0),
) + tuple((yaw, pitch, eye, 0, 0) for yaw, pitch, eye in product((-2, 2), (-2, 2), (-8, 8)))


class ChinScene(Scene):
    def __init__(self, mesh):
        self.groups = {}
        self.add(CHIN, 'jaw', mesh)


def test_angles(bands=CLEARANCE_BANDS):
    yield 0., bands[0][1]
    start = 0.
    for limit, allowance, step in bands:
        for angle in np.linspace(start, limit, ceil((limit-start)/step)+1)[1:]:
            yield float(angle), allowance
        start = limit


def check_pose(cad, layout, wiring, lengths, bands, pose):
    scene = ChinScene(trimesh.load_mesh(cad/'world'/f'{CHIN}.stl'))
    cables = capture(layout, wiring, lengths, pose)
    if {wire.name for wire in cables} != WIRE_NAMES:
        raise ValueError(f'Incomplete jaw wiring capture at {pose}')
    stop = layout['motion_geometry'].get('jaw_stop')
    if stop:
        name = stop['modified_part']
        scene.add(name, layout['world_motion'][name], trimesh.load_mesh(cad/'world'/f'{name}.stl'))
    for angle, allowance in test_angles(bands):
        motion = matrices(layout, *pose[:4], angle)
        contacts = [hit for wire in cables for hit in scene.hits(wire, motion, allowance)]
        if contacts:
            return {'fixed_pose': pose, 'first_angle_deg': angle, 'contacts': contacts}
    return {'fixed_pose': pose, 'first_angle_deg': None, 'contacts': []}


def run(cad, jobs):
    layout = read(cad/'cad_parts.json')
    wiring = read(ROOT/'web/assets/wiring.json')
    lengths = read(ROOT/'mechanical/revisions/b20/physics/harness-cut-lengths.json')
    mesh = trimesh.load_mesh(cad/'world'/f'{CHIN}.stl')
    radius = np.linalg.norm(mesh.vertices[:, 1:] - np.asarray(layout['jaw_pivot_mm'])[1:], axis=1).max()
    limit = layout['motion_geometry'].get('jaw_stop', {}).get('released_clearance_deg')
    bands = CLEARANCE_BANDS
    if limit is not None:
        from check_b22_harness import CAMERA_INTERNAL_RUN_MM

        if not 0. < limit <= CLEARANCE_BANDS[0][0]:
            raise ValueError('B22 jaw must remain within the 1 mm wire reserve band')
        lengths['USB-Camera'] = CAMERA_INTERNAL_RUN_MM
        bands = ((limit, 1., JAW_STEP_DEG),)
    check = partial(check_pose, cad, layout, wiring, lengths, bands)
    with ProcessPoolExecutor(jobs) as pool:
        rows = list(pool.map(check, POSES))
    return {'cad_sha256': layout['source_sha256'],
            'clearance_bands': [{'up_to_deg': limit, 'sheath_inflation_mm': gap, 'max_sample_spacing_deg': step,
                                 'maximum_chin_displacement_to_nearest_sample_mm': float(
                                     2*radius*np.sin(np.deg2rad(step/4)))}
                                for limit, gap, step in bands],
            'scope': 'fixed neck, eye and hatch pose per captured wire path; jaw-only sweep', 'poses': rows}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    result = run(args.cad, args.jobs)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    failed = [row for row in result['poses'] if row['contacts']]
    print(f'{len(result["poses"])} fixed-pose jaw sweeps, {len(failed)} with wire contacts')
    if failed:
        raise SystemExit(1)
