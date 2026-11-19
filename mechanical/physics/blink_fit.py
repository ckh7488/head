"""Check the installed blink pins and fasteners in FreeCAD."""

from argparse import ArgumentParser
from hashlib import sha256
from itertools import product
import json
from math import cos, radians, sin, sqrt
from pathlib import Path

import FreeCAD as App
import fcl
import Part
import trimesh as tr
from trimesh.collision import mesh_to_BVH

from export_cad import world_shape

V = App.Vector
X = V(1, 0, 0)
HINGE = V(0, -39, 119)
PINS = ('Part058', 'Part059', 'Part061', 'Part062')
LINKS = (
    (1.2, 7.15, 1, 'servo_yz_mm', 'radius_mm', True),
    (4.55, 10.25, 1, 'shaft_yz_mm', 'radius_mm', False),
    (-53.75, -47.95, 1, 'shaft_yz_mm', 'lid_radius_mm', True),
    (53.75, 47.95, -1, 'shaft_yz_mm', 'lid_radius_mm', True),
    (-53.5, -47.95, 1, 'hinge', 'lid_radius_mm', True),
    (53.5, 47.95, -1, 'hinge', 'lid_radius_mm', True),
)
FIXED = ('Part041', 'Part042', 'Part045', 'Part046', 'Part050', 'Part052', 'Part063',
         'Part064', 'Part048', 'Part025', 'Part027')
MESHES = ('Part073', 'Part074', 'Part076', 'Part077',
          'Jaw_36_left_jaw_servo_stay', 'Jaw_37_right_jaw_bearing_stay')


def fastener(joint, layout, angle):
    start, end, sense, center, arm, flush = joint
    y, z = (HINGE.y, HINGE.z) if center == 'hinge' else layout[center]
    phase = radians(layout['phase_deg'] + angle)
    y += layout[arm] * cos(phase)
    z += layout[arm] * sin(phase)
    axis = X * sense
    origin = V(start, y, z)
    head = (Part.makeCone(1.95, 1., .95, origin, axis) if flush else
            Part.makeCylinder(2., 1.4, origin, -axis))
    bolt = Part.makeCylinder(1., 10., origin, axis)
    nut = Part.makeCylinder(2.32, 2.70, V(end, y, z), axis)
    return head.fuse([bolt, nut]).removeSplitter()


def check(cad, meshes):
    doc = App.openDocument(str(cad))
    try:
        doc.recompute()
        rig = json.loads(doc.R5.MotionGeometry)['blink']
        cradle = world_shape(doc.Part024)
        shape_pairs = []
        slack = .25
        for name in PINS:
            pin = world_shape(doc.getObject(name))
            start = V(pin.BoundBox.XMin - slack, HINGE.y, HINGE.z)
            envelope = Part.makeCylinder(1. + sqrt(2) * slack, 9.5 + 2 * slack, start, X)
            shape_pairs.append((name, envelope, 'eye cradle', cradle))
        fixed = {name: world_shape(doc.getObject(name)) for name in FIXED}
        eye_parts = [world_shape(doc.getObject(name)) for name in ('Part029', 'Part033')]
        tilts = [cradle.copy().rotate(HINGE, X, pitch) for pitch in (-8., 0., 8.)]
        eyes = []
        for pitch, yaw, (eye, x) in product((-8., 0., 8.), (-20., 0., 20.), zip(eye_parts, (-34., 34.))):
            moved = eye.copy().rotate(V(x, HINGE.y, HINGE.z), V(0,0,1), yaw)
            eyes.append((x, moved.rotate(HINGE, X, pitch)))
        shell = {name: tr.load_mesh(meshes/'world'/f'{name}.stl') for name in MESHES}
        shell_objects = {name: fcl.CollisionObject(mesh_to_BVH(mesh)) for name, mesh in shell.items()}
        request = fcl.CollisionRequest(num_max_contacts=1)
        worst = {}

        def record(label, overlap):
            worst[label] = max(worst.get(label, 0.), overlap)

        for label, envelope, other, solid in shape_pairs:
            record(f'{label} / {other}', envelope.common(solid).Volume)

        frame = world_shape(doc.Part019)
        rail = fixed['Part063']
        ballast = world_shape(doc.BallastTray)
        rear = V(0, 1, 0)
        for x, z in rig['mount_xz_mm']:
            axis = f'rail mount {x:g},{z:g}'
            bolt = Part.makeCylinder(1.5, 8., V(x, 19.7, z), rear)
            head = Part.makeCylinder(2.8, 3., V(x, 27.7, z), rear)
            brass_seat = Part.makeCylinder(2.09, 4., V(x, 19., z), rear)
            tool = Part.makeCylinder(1.4, 20., V(x, 30.6, z), rear)
            for name, housing in (('frame', frame), ('rail', rail), ('ballast', ballast)):
                for solid in (bolt, head, brass_seat):
                    record(f'{axis} / {name}', solid.common(housing).Volume)
            record(f'{axis} / tool to frame', tool.common(frame).Volume)
        for z in (183.,189.):
            entry = V(.9,0,z)
            head = Part.makeCone(3.,1.5,1.5,entry,-X)
            bolt = Part.makeCylinder(1.5,18.,entry,-X)
            nut = Part.makeCylinder(3.2,4.,V(-12.4,0,z),-X)
            for name, housing in (('motor', fixed['Part045']), ('plate', fixed['Part046']), ('rail',rail)):
                for solid in (bolt, head, nut):
                    record(f'motor mount {z:g} / {name}', solid.common(housing).Volume)

        for angle in (-1, *range(0, 91, 3), 91):
            for index, joint in enumerate(LINKS):
                hardware = fastener(joint, rig, angle)
                name = f'link {index+1}'
                for other, solid in fixed.items():
                    if hardware.BoundBox.intersect(solid.BoundBox):
                        record(f'{name} / {other}', hardware.common(solid).Volume)
                for tilted_cradle in tilts:
                    record(f'{name} / eye cradle', hardware.common(tilted_cradle).Volume)
                for x, moved_eye in eyes:
                    if hardware.BoundBox.intersect(moved_eye.BoundBox):
                        record(f'{name} / eye {x:g}', hardware.common(moved_eye).Volume)
                vertices, faces = hardware.tessellate(.045)
                mesh = tr.Trimesh(vertices=[list(v) for v in vertices], faces=faces)
                obj = fcl.CollisionObject(mesh_to_BVH(mesh))
                for other, static in shell_objects.items():
                    if fcl.collide(obj, static, request, fcl.CollisionResult()):
                        overlap = tr.boolean.intersection([mesh, shell[other]], engine='manifold', check_volume=False)
                        record(f'{name} / {other}', max(0., overlap.volume))
        collisions = {name: volume for name, volume in worst.items() if volume > .01}
        return {'cad_sha256': sha256(cad.read_bytes()).hexdigest(),
                'pin_offset_per_axis_mm': slack,
                'maximum_overlap_mm3': max(worst.values()), 'collisions_mm3': collisions}
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('meshes', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    result = check(args.cad.resolve(), args.meshes)
    args.report.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if result['collisions_mm3']:
        raise SystemExit(1)
