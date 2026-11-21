"""Measure closure against the two adjustable stops in an exported head assembly."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path

import fcl
import numpy as np
import trimesh
from trimesh.collision import mesh_to_BVH

from check_head import pose


ARMS = {'left': 'Jaw_38_left_jaw_drive_arm', 'right': 'Jaw_39_right_jaw_pivot_arm'}


def check(directory):
    layout = json.loads((directory/'cad_parts.json').read_bytes())
    stops = layout['motion_geometry']['jaw_close_stop']['stations']
    names = {'Jaw_30_moving_jaw', *ARMS.values(), *(row['stop'] for row in stops.values())}
    meshes = {}
    for name in names:
        path = directory/'world'/f'{name}.stl'
        if sha256(path.read_bytes()).hexdigest() != layout['world_sha256'][name]:
            raise ValueError(f'Mesh export is inconsistent with its manifest: {name}')
        meshes[name] = trimesh.load_mesh(path)
    objects = {name: fcl.CollisionObject(mesh_to_BVH(mesh)) for name, mesh in meshes.items()}
    contact_request = fcl.CollisionRequest()
    distance_request = fcl.DistanceRequest()
    poses = np.linspace(-.26, 9.72, 201)
    results = {}
    for hand, station in stops.items():
        stop = objects[station['stop']]
        arm = ARMS[hand]

        def gap(name, angle):
            other = objects[name]
            transform = pose('jaw', (0., 0., 0., 0., angle), layout)
            other.setTransform(fcl.Transform(transform[:3,:3].copy(), transform[:3,3].copy()))
            if fcl.collide(stop, other, contact_request, fcl.CollisionResult()):
                return 0.
            return fcl.distance(stop, other, distance_request, fcl.DistanceResult())

        lower, upper = -.26, 0.
        if gap(arm, lower) != 0. or gap(arm, upper) <= 0.:
            raise ValueError(f'The {hand} adjustment screws do not stop the intended arm just past zero')
        for _ in range(24):
            angle = (lower+upper)/2.
            if gap(arm, angle) == 0.:
                lower = angle
            else:
                upper = angle
        others = ('Jaw_30_moving_jaw', *(name for name in ARMS.values() if name != arm))
        radii = [np.linalg.norm(meshes[name].vertices[:,1:]-np.array(layout['jaw_pivot_mm'][1:]),
                                axis=1).max() for name in others]
        sample_minimum = min(gap(name, angle) for name in others for angle in poses)
        between_sample_margin = max(radii)*np.radians((poses[1]-poses[0])/2.)
        reserve = sample_minimum-between_sample_margin
        if not -.25 <= upper <= -.15 or reserve <= 1.:
            raise ValueError(f'The {hand} close stop misses its angle or running clearance')
        results[hand] = {'first_arm_contact_deg': upper, 'clearance_to_arm_at_calibrated_zero_mm': gap(arm, 0.),
                         'unintended_jaw_contact_clearance_lower_bound_mm': reserve}
    return {'cad_sha256': layout['source_sha256'], 'stations': results,
            'scope': 'Rigid nominal stop and moving jaw envelope. Hardware adjustment, retained position and '
                     'tooth clearance under the applied closing force are measured on the bench.'}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = check(args.cad)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(report)
