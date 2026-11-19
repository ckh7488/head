"""Clearance bounds under small relative assembly offsets at sampled poses."""

from argparse import ArgumentParser
from itertools import product
from pathlib import Path
import json
from math import sqrt

import fcl
import numpy as np
import trimesh as tr
from trimesh.collision import mesh_to_BVH

from check_head import pose

RELATIVE_ERROR_MM = .25


def pairs():
    for side in (0, 1):
        lid = f'Part{78+side:03}'
        orbit = f'Part{76+side:03}'
        link = ('Part057', 'Part060')[side]
        eye = ('Part029', 'Part033')[side]
        yield lid, orbit, (0,), (0,), 'lid and hinge carrier'
        yield lid, 'Part073', (0,), (0,), 'lid and front shell'
        yield lid, eye, (-8, -4, 0, 4, 8), (-20, -10, 0, 10, 20), 'lid and eyeball'
        yield link, 'Part024', range(-8, 9, 2), (0,), 'link and eye cradle'


def bounds(directory):
    cad = json.loads((directory/'cad_parts.json').read_text())
    motion = cad['world_motion']
    entries = list(pairs())
    names = {name for entry in entries for name in entry[:2]}
    bodies = {name: fcl.CollisionObject(mesh_to_BVH(tr.load_mesh(directory/'world'/f'{name}.stl')))
              for name in names}
    request = fcl.DistanceRequest()
    cases = []
    offset_bound = sqrt(3) * RELATIVE_ERROR_MM
    for moved, target, pitch, yaw, label in entries:
        grid = list(product(range(-1, 92), pitch, yaw))
        a, b = bodies[moved], bodies[target]
        a.setTransform(fcl.Transform())
        gap, angle_set = float('inf'), None
        for blink, look_up, look_side in grid:
            angles = (0., look_up, look_side, blink, 0.)
            relative = np.linalg.solve(pose(motion[moved], angles, cad), pose(motion[target], angles, cad))
            b.setTransform(fcl.Transform(relative[:3, :3].copy(), relative[:3, 3].copy()))
            distance = float(fcl.distance(a, b, request, fcl.DistanceResult()))
            if distance < gap:
                gap, angle_set = distance, angles
        cases.append({'parts': [moved, target], 'interface': label, 'samples': len(grid),
                      'nominal_min_mm': gap, 'assembly_bound_mm': gap-offset_bound,
                      'angles_deg': angle_set})
        print(label, moved, f'{gap:.3f} mm nominal, {gap-offset_bound:.3f} mm with offset', flush=True)
    return {'cad_sha256': cad['source_sha256'], 'relative_offset_each_axis_mm': RELATIVE_ERROR_MM,
            'interfaces': cases}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    result = bounds(args.cad)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2))
    if any(row['assembly_bound_mm']<=0 for row in result['interfaces']):
        raise SystemExit('An assembly offset can consume the available gap')
