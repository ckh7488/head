"""Verify ordinary socket head envelopes against motor plates and moving brackets."""

from argparse import ArgumentParser
from itertools import product
from pathlib import Path
import json
import sys

import fcl
import numpy as np
import trimesh as tr
from trimesh.collision import mesh_to_BVH

from check_head import ANGLES, AXES_BY_MOTION, PAIRS_BY_INTERFACE, pose

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor_seats import HEAD_SEATS

HEAD_R = {2: 1.93, 3: 2.78}
HEAD_H = {2: 2., 3: 3.}
SIDE_CLEARANCE = .10
HEIGHT_CLEARANCE = .10


def check(directory):
    layout = json.loads((directory / 'cad_parts.json').read_text())
    modes = layout['world_motion']
    names = set(HEAD_SEATS)
    names.update(p for groups in PAIRS_BY_INTERFACE.values() for group in groups for p in group)
    meshes = {part: tr.load_mesh(directory / 'world' / f'{part}.stl') for part in names}
    shapes = {part: mesh_to_BVH(mesh) for part, mesh in meshes.items()}
    request = fcl.CollisionRequest(num_max_contacts=1)
    count, minimum_seat = 0, float('inf')

    for plate, points in HEAD_SEATS.items():
        for size, face, outward, recess in points:
            normal = np.asarray(outward)
            seat = np.asarray(face) - recess * normal
            cap_bottom = seat + .004 * normal
            cap_top = cap_bottom + (HEAD_H[size] + HEIGHT_CLEARANCE) * normal
            cap = tr.creation.cylinder(
                radius=HEAD_R[size] + SIDE_CLEARANCE, segment=[cap_bottom, cap_top], sections=56,
            )
            obj = fcl.CollisionObject(mesh_to_BVH(cap))

            if recess:
                tangent = np.roll(normal, 1)
                other = np.cross(normal, tangent)
                angle = np.linspace(0, 2 * np.pi, 16, endpoint=False)
                ring = seat + .06 * normal + 1.46 * (
                    np.cos(angle)[:, None] * tangent + np.sin(angle)[:, None] * other
                )
                hits, ids, _ = meshes[plate].ray.intersects_location(ring, np.tile(-normal, (len(ring), 1)))
                for index, start in enumerate(ring):
                    depth = np.sort((start - hits[ids == index]) @ normal)
                    if len(depth) < 2 or abs(depth[0] - .06) > .025:
                        raise ValueError(f'{plate}, {face}: missing flat bearing land')
                    remaining = float(depth[1] - depth[0])
                    if remaining < .82:
                        raise ValueError(f'{plate}, {face}: only {remaining:.3f} mm under the head')
                    minimum_seat = min(minimum_seat, remaining)

            for part in sorted(shapes):
                target = fcl.CollisionObject(shapes[part])
                a, b = modes[plate], modes[part]
                axes = sorted(set(AXES_BY_MOTION[a]) | set(AXES_BY_MOTION[b])) if a != b else ()
                for values in product(*(ANGLES[i] for i in axes)):
                    angles = np.zeros(len(ANGLES))
                    angles[list(axes)] = values
                    motion = np.linalg.solve(pose(a, angles, layout), pose(b, angles, layout))
                    target.setTransform(fcl.Transform(motion[:3, :3].copy(), motion[:3, 3].copy()))
                    count += 1
                    if not fcl.collide(obj, target, request, fcl.CollisionResult()):
                        continue
                    if not meshes[part].is_volume:
                        raise ValueError(f'{plate}, {face}: head intersects {part} at {angles.tolist()}')
                    overlap = tr.boolean.intersection(
                        [cap, meshes[part].copy().apply_transform(motion)], engine='manifold', check_volume=False,
                    ).volume
                    if overlap > .01:
                        raise ValueError(f'{plate}, {face}: head intersects {part} by {overlap:.3f} mm³ at {angles.tolist()}')

    print(f'{sum(map(len, HEAD_SEATS.values()))} cap heads, {count:,} poses, no overlaps')
    print(f'Minimum material under recessed head: {minimum_seat:.3f} mm')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    check(parser.parse_args().directory)
