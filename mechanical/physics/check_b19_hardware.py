"""Sweep the B19 fasteners and pins through the eye, lid, neck and jaw poses.

Run export_cad.py --world on the B19 assembly first. Each fastener moves with the part
named in its spec; the parts it passes through are skipped. Pairs between the base
(fixed) and the yaw carrier are left out because check_head.pose models neck pitch,
not yaw; build_b19_review_fixes.py and the yaw check below cover those.
"""
from argparse import ArgumentParser
from itertools import product
from pathlib import Path
import json

import fcl
import numpy as np
from shapely.geometry import Polygon
import trimesh as tr
from trimesh.collision import mesh_to_BVH

from check_head import ANGLES, AXES_BY_MOTION, pose, sweep_angles


def cylinder(radius, height, start, axis):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    mesh = tr.creation.cylinder(radius=radius, height=height, sections=24)
    mesh.apply_transform(tr.geometry.align_vectors([0, 0, 1], axis))
    mesh.apply_translation(np.asarray(start) + axis*height/2)
    return mesh


def hexagon(width, height, start, axis):
    radius = width / np.sqrt(3)
    outline = Polygon([(radius*np.cos(a), radius*np.sin(a)) for a in np.arange(6)*np.pi/3 + np.pi/6])
    mesh = tr.creation.extrude_polygon(outline, height)
    mesh.apply_transform(tr.geometry.align_vectors([0, 0, 1], axis))
    mesh.apply_translation(start)
    return mesh


def shape(item):
    return tr.util.concatenate([cylinder(*s[1:]) if s[0] == 'cyl' else hexagon(*s[1:]) for s in item['shapes']])


def yaw_gaps(world, kinds, items):
    """Smallest gap between base-mounted fasteners and the yaw carrier over ±62° of neck yaw."""
    carrier = {}
    for name, kind in kinds.items():
        if kind not in ('fixed', 'hatch') and (world/f'{name}.stl').exists():
            mesh = tr.load_mesh(world/f'{name}.stl')
            if len(mesh.faces):
                carrier[name] = fcl.CollisionObject(mesh_to_BVH(mesh))
    gaps = {}
    for item in items:
        fastener = fcl.CollisionObject(mesh_to_BVH(shape(item)))
        best = float('inf')
        for angle in np.arange(-62, 63, 2):
            turn = tr.transformations.rotation_matrix(np.radians(angle), [0, 0, 1], [0, 0, 0])
            for obj in carrier.values():
                obj.setTransform(fcl.Transform(turn[:3, :3].copy(), turn[:3, 3].copy()))
                best = min(best, fcl.distance(fastener, obj, fcl.DistanceRequest(), fcl.DistanceResult()))
        gaps[item['name']] = round(float(best), 3)
    return gaps


def sweep(cad, spec):
    layout = json.loads((cad/'cad_parts.json').read_text())
    sampled_angles = sweep_angles(layout)
    kinds = layout['world_motion']
    world = cad/'world'
    meshes = {}
    for name in kinds:
        path = world/f'{name}.stl'
        if path.exists():
            mesh = tr.load_mesh(path)
            if len(mesh.faces):
                meshes[name] = (mesh, fcl.CollisionObject(mesh_to_BVH(mesh)))
    own = {item['name'] for item in spec} | {'EyeYawTieHornNut', 'EyeYawTieHornWasher', 'PitchPinDowelLeft', 'PitchPinDowelRight'}
    request = fcl.CollisionRequest()
    report = {}
    for item in spec:
        fastener = shape(item)
        moving = fcl.CollisionObject(mesh_to_BVH(fastener))
        mode = item['motion']
        low, high = fastener.bounds
        hits, near = [], {}
        for name, (mesh, other) in meshes.items():
            if name in item['skip'] or name in own:
                continue
            if {mode, kinds[name]} & {'fixed', 'hatch'} and mode != kinds[name]:
                continue
            lo, hi = mesh.bounds
            if np.any(high < lo-25) or np.any(low > hi+25):
                continue
            axes = sorted(set(AXES_BY_MOTION.get(mode, ())) | set(AXES_BY_MOTION.get(kinds[name], ()))) \
                if mode != kinds[name] else []
            best = float('inf')
            for values in product(*(sampled_angles[i] for i in axes)):
                angles = np.zeros(len(ANGLES))
                angles[axes] = values
                tx = np.linalg.solve(pose(kinds[name], angles, layout), pose(mode, angles, layout))
                moving.setTransform(fcl.Transform(tx[:3, :3].copy(), tx[:3, 3].copy()))
                other.setTransform(fcl.Transform())
                if fcl.collide(moving, other, request, fcl.CollisionResult()):
                    hits.append({'part': name, 'angles_deg': angles.tolist()})
                    break
                best = min(best, fcl.distance(moving, other, fcl.DistanceRequest(), fcl.DistanceResult()))
            if best < 1.:
                near[name] = round(float(best), 3)
        report[item['name']] = {'collisions': hits, 'under_1mm': near}
    base = [item for item in spec if item['motion'] == 'fixed']
    return {'fasteners': report, 'yaw_gap_mm': yaw_gaps(world, kinds, base),
            'joint_pairs': joint_pairs(meshes, kinds, layout)}


# Parts that meet at a joint and that check_head.py treats as mates. B19 trimmed the 19 horn
# and 21-2 crank where they overlapped the 22 drive link; this sweeps those pairs through
# the whole blink stroke.
JOINT_PAIRS = (('Part047', 'Part056'), ('Part054', 'Part056'), ('Part053', 'Part057'), ('Part055', 'Part060'))


def joint_pairs(meshes, kinds, layout):
    result = {}
    for a, b in JOINT_PAIRS:
        mesh_a, obj_a = meshes[a]
        mesh_b, obj_b = meshes[b]
        worst = 0.
        for blink in ANGLES[3]:
            angles = np.zeros(len(ANGLES))
            angles[3] = blink
            tx = np.linalg.solve(pose(kinds[b], angles, layout), pose(kinds[a], angles, layout))
            moved = mesh_a.copy().apply_transform(tx)
            volume = tr.boolean.intersection([moved, mesh_b], engine='manifold', check_volume=False).volume
            worst = max(worst, float(volume))
        result[f'{a} / {b}'] = round(worst, 3)
    return result


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path, help='export_cad.py --world output for the B19 assembly')
    parser.add_argument('spec', type=Path, help='hardware-spec.json written by build_b19_review_fixes.py')
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    result = sweep(args.cad, json.loads(args.spec.read_text()))
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    failed = [name for name, row in result['fasteners'].items() if row['collisions']]
    print(f"{len(result['fasteners'])} fasteners, {len(failed)} colliding", failed)
    print('yaw gaps', result['yaw_gap_mm'])
    print('joint overlap mm³', result['joint_pairs'])
    if failed or any(gap <= 0 for gap in result['yaw_gap_mm'].values()) or \
            any(volume > .05 for volume in result['joint_pairs'].values()):
        raise SystemExit(1)
