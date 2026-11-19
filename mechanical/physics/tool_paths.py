"""Check straight drivers, sockets and the open-end wrench at the actual assembly steps."""

from argparse import ArgumentParser
from functools import cache
from itertools import product
import json
from pathlib import Path

import fcl
import FreeCAD as App
import trimesh as tr
from trimesh.collision import mesh_to_BVH

from assembly_sweeps import exact_fastener, manifold, MESH_VOLUME_LIMIT
from export_cad import world_shape
from primitives import cylinder
from tool_access import KEY_RADIUS, NUT_HEIGHT, SOCKET_RADIUS, WRENCH_THICKNESS, wrench_profile, wrench_shape

V = App.Vector
Z = (0., 0., 1.)
# A plus or minus chooses which end of a round socket is presented to the nut.
JOINTS = (
    ('cable-tray-fasteners', 'clipBolt', 'clipNut', '+'),
    ('cable-cover-bolts', 'cableBolt', 'cableNut', 'rear'),
    ('hub-bolts', 'hubBolt', 'hubNut', '-'),
    ('hatch-bolts', 'hatchBolt', 'hatchNut', 'side'),
    ('c3-bolts', 'c3Bolt', 'c3Nut', '-'),
    ('carrier-bolts', 'carrierBolt', 'carrierNut', '+'),
    ('openrb-bolts', 'openrbBolt', 'openrbNut', '-'),
    ('openrb-carrier-bolts', 'carrierBolt', 'carrierNut', '+'),
    ('keeper-nuts', 'keeperBolt', 'keeperNut', '+'),
    ('bearing-seat-bolts', 'seatBolt', 'seatNut', '+'),
    ('rotor-nuts', 'mastStud', 'rotorNut', '+'),
    ('base-deck-bolts', 'lidBolt', 'lidNut', '+'),
    ('yoke-bolts', 'yokeBolt', 'yokeNut', 'under-side'),
    ('blink-rail-bolts', 'railBolt', 'railNut', '-'),
    ('blink-clamp-bolts', 'crankBolt', 'crankNut', 'front'),
    ('blink-horn-nut', 'middleServo', 'middleNut', '+'),
    ('blink-motor-fasteners', 'blinkPlateBolt', 'blinkPlateNut', '+'),
    ('mast-bolts', 'mastStud', 'mastNut', '+'),
)
LINKS = (
    ('blink-center-link', 'centerLink0', 'linkNutPos0'),
    ('blink-upper-links', 'centerLink1', 'linkNutPos1'),
    ('blink-upper-links', 'rightLink0', 'linkNutNeg0'),
    ('blink-links', 'centerLower0', 'linkLeftLowerNut0'),
    ('blink-links', 'rightLower0', 'linkRightLowerNut0'),
)


def present(step):
    return set(step['base'].split()).union(name for move in step['moves'] for name in move['ids'])


def straight_key(row, length):
    axis = V(*row['axis'])
    height = {2: 2., 3: 3.}[row['size']]
    face = V(*row['seat']) - (height + .02)*axis
    return cylinder(KEY_RADIUS[row['size']], length, tuple(face), tuple(-axis))


def socket_gauge(row, mode, radius, length=45.):
    axis = V(*row['axis'])
    face = V(*row['seat'])
    if mode == '-':
        face += (NUT_HEIGHT[row['size']] - .06) * axis
        axis = -axis
    else:
        face += .07 * axis
    return cylinder(radius, length, tuple(face), tuple(axis))


def around(axis):
    normal = V(*axis)
    start = V(0, -1, 0) if abs(normal.y) < .5 else V(0, 0, 1)
    return [App.Rotation(normal, a).multVec(start) for a in (0, 45, -45, 90, -90, 135, -135, 180)]


def link_wrenches(row):
    axis = V(*row['axis'])
    for offset in (.12, -.75):
        seat = V(*row['seat']) + offset*axis
        for outward in around(row['axis']):
            tool = wrench_shape(tuple(seat), row['axis'], tuple(outward), wrench_profile(2), WRENCH_THICKNESS[2])
            yield [tool.translated(i*outward) for i in range(0, 39, 2)], outward


def bent_key(row):
    axis = -V(*row['axis'])
    face = V(*row['seat']) + 2.02*axis
    knee = face + 13.*axis
    short = straight_key(row, 13.10)
    for outward in around(row['axis']):
        tool = short.fuse(cylinder(.89, 40., tuple(knee), tuple(outward)))
        yield [tool.translated(i*axis) for i in range(0, 17, 2)], outward


def wrench_gauges(row, mode, angle=0., rise=0.):
    size = row['size']
    depth = WRENCH_THICKNESS[size]
    side = -1 if row['seat'][0] < 0 else 1
    outward = V(*(dict(rear=(0,1,0), front=(0,-1,0)).get(mode, (side,0,0))))
    distance = {'rear': 23, 'front': 18, 'side': 51, 'under-side': 20, 'mast': 75}[mode]
    seat = V(*row['seat'])
    if mode in ('rear', 'front', 'under-side'):
        seat.z += NUT_HEIGHT[size] - depth - .17
    else:
        seat.z += .24
    seat.z += rise
    shape = wrench_shape(tuple(seat), Z, tuple(outward), wrench_profile(size, angle), depth)
    return [shape.translated(outward * (distance*i/round(distance/2))) for i in range(round(distance/2)+1)]


def trimesh_of(solid):
    points, faces = solid.tessellate(.03)
    return tr.Trimesh(vertices=[tuple(point) for point in points], faces=faces)


def check(doc, directory, plan, selected):
    steps = {step['id']: step for step in plan['steps']}
    hardware = {row['id']: row for row in plan['hardware'] if not row.get('tool')}
    tools = {row['id'] for row in plan['hardware'] if row.get('tool')}
    request = fcl.CollisionRequest(num_max_contacts=1)

    @cache
    def geometry(name):
        if name in hardware:
            return exact_fastener(hardware[name]), None, None
        obj = doc.getObject(name)
        if obj.TypeId == 'Part::Feature':
            return world_shape(obj), None, None
        mesh = tr.load_mesh(directory / f'{name}.stl')
        return None, fcl.CollisionObject(mesh_to_BVH(mesh)), manifold(mesh)

    def hit(shape, step, skip):
        mesh = None
        for name in sorted(present(step) - skip - tools):
            other, obj, solid = geometry(name)
            limit = shape.BoundBox
            if other is not None:
                if not limit.intersect(other.BoundBox):
                    continue
                overlap = shape.common(other).Volume
            else:
                if mesh is None:
                    mesh = trimesh_of(shape)
                    moving = fcl.CollisionObject(mesh_to_BVH(mesh))
                    moving_solid = manifold(mesh)
                if not fcl.collide(moving, obj, request, fcl.CollisionResult()):
                    continue
                if solid.is_empty():
                    return name
                overlap = (moving_solid ^ solid).volume()
            if overlap > MESH_VOLUME_LIMIT:
                return name
        return None

    def joints():
        groups = (*JOINTS, *((stage, bolt, tail, '+') for stage, bolt, tail in LINKS))
        for stage, bolt, tail, mode in groups:
            actors = present(steps[stage])
            tails = sorted(name for name in actors if name.startswith(tail) and name in hardware)
            if stage == 'carrier-bolts':
                tails = [name for name in tails if int(name[len(tail):]) < 4]
            if stage == 'openrb-carrier-bolts':
                tails = [name for name in tails if int(name[len(tail):]) >= 4]
            for name in tails:
                suffix = name[len(tail):]
                yield stage, hardware[bolt+suffix], hardware[name], mode

    results = {}
    for stage, bolt, nut, mode in joints():
        if selected and stage not in selected:
            continue
        step = steps[stage]
        skip = {bolt['id'], nut['id']}
        length = 77. if stage in ('base-deck-bolts', 'bearing-seat-bolts') else 40.
        key = straight_key(bolt, length) if stage != 'mast-bolts' else None
        key_direction = None
        head_hit = hit(key, step, skip) if key is not None else None
        if head_hit and stage in ('blink-links', 'blink-upper-links'):
            for poses, outward in bent_key(bolt):
                if all(hit(shape, step, skip) is None for shape in poses):
                    key, head_hit, key_direction = poses[0], None, tuple(outward)
                    break
        nut_direction = None
        if mode in ('+', '-'):
            nut_tool = socket_gauge(nut, mode, SOCKET_RADIUS[nut['size']])
            tail_hit = hit(nut_tool, step, skip)
            if tail_hit and stage in ('blink-links', 'blink-upper-links'):
                for poses, outward in link_wrenches(nut):
                    if all(hit(shape, step, skip) is None for shape in poses):
                        nut_tool, tail_hit, nut_direction = poses[0], None, tuple(outward)
                        break
        else:
            poses = wrench_gauges(nut, mode)
            nut_tool = poses[0]
            if mode == 'front':
                poses += [shape for angle, rise in product((-15., 0., 15.), (-.12, .12))
                          for shape in wrench_gauges(nut, mode, angle, rise)]
            tail_hit = next((obstacle for shape in poses if (obstacle := hit(shape, step, skip))), None)
        if stage == 'mast-bolts' and tail_hit is None:
            lower = hardware[nut['id'].replace('mastNut', 'rotorNut')]
            poses = wrench_gauges(lower, 'mast')
            key = poses[0]
            tail_hit = next((obstacle for shape in poses
                             if (obstacle := hit(shape, step, skip | {lower['id']}))), None)
        if key and not (head_hit or tail_hit) and key.common(nut_tool).Volume > MESH_VOLUME_LIMIT:
            tail_hit = 'other tool'
        results[nut['id']] = {'step': stage, 'hex_key': head_hit, 'nut_tool': tail_hit,
                              'bent_key_toward': key_direction, 'side_wrench_from': nut_direction}
    for stage, prefix in (('rotor-horn','hornBolt'), ('pitch-horn','pitchHornBolt')):
        if selected and stage not in selected:
            continue
        for bolt in hardware.values():
            if bolt['id'].startswith(prefix):
                obstacle = hit(straight_key(bolt, 28.), steps[stage], {bolt['id']})
                results[bolt['id']] = {'step': stage, 'hex_key': obstacle, 'nut_tool': None}
    return results


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('directory', type=Path)
    parser.add_argument('plan', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('steps', nargs='*')
    args = parser.parse_args()
    doc = App.openDocument(str(args.cad.resolve()))
    try:
        report = check(doc, args.directory, json.loads(args.plan.read_text()), args.steps)
    finally:
        App.closeDocument(doc.Name)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    failed = {name: entry for name, entry in report.items() if entry['hex_key'] or entry['nut_tool']}
    print(f'{len(report)} joints checked, {len(failed)} obstructed tool paths')
    for name, entry in failed.items():
        print(name, entry)
    raise SystemExit(bool(failed))
