"""Check the installed blink pins and fasteners in FreeCAD."""

from argparse import ArgumentParser
from hashlib import sha256
from itertools import product
import json
from math import cos, radians, sin, sqrt
from pathlib import Path
import sys

import FreeCAD as App
import fcl
import Part
import trimesh as tr
from trimesh.collision import mesh_to_BVH

from export_cad import world_shape
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stock import BLINK_CLAMPS, BLINK_CLAMP_LENGTH, nut, socket_screw

V = App.Vector
X = V(1, 0, 0)
HINGE = V(0, -39, 119)
PINS = ('Part058', 'Part059', 'Part061', 'Part062')
LINKS = (
    (7.45, 1.25, -1, 'servo_yz_mm', 'radius_mm', 6.),
    (4.55, 10.55, 1, 'shaft_yz_mm', 'radius_mm', 8.),
    (-53.75, -47.65, 1, 'shaft_yz_mm', 'lid_radius_mm', 8.),
    (53.75, 47.65, -1, 'shaft_yz_mm', 'lid_radius_mm', 8.),
    (-53.5, -47.65, 1, 'hinge', 'lid_radius_mm', 8.),
    (53.5, 47.65, -1, 'hinge', 'lid_radius_mm', 8.),
)
FIXED = ('Part041', 'Part042', 'Part045', 'Part046', 'Part050', 'Part052', 'Part063',
         'Part064', 'Part048', 'Part025', 'Part027')
MESHES = ('Part073', 'Part074', 'Part076', 'Part077',
          'Jaw_36_left_jaw_servo_stay', 'Jaw_37_right_jaw_bearing_stay')


def fastener(joint, layout, angle):
    start, nut_x, sense, center, arm, length = joint
    y, z = (HINGE.y, HINGE.z) if center == 'hinge' else layout[center]
    phase = radians(layout['phase_deg'] + angle)
    y += layout[arm] * cos(phase)
    z += layout[arm] * sin(phase)
    axis = (sense,0,0)
    bolt = socket_screw(2,length,(start,y,z),axis)
    tail = nut(2,(nut_x,y,z),(1,0,0) if length == 6. else axis)
    if length == 6.:
        washer = Part.makeCylinder(2.50,.3,V(start,y,z),-X)
    else:
        washer = Part.makeCylinder(2.50,.3,V(nut_x,y,z),-V(*axis))
    return bolt.fuse([washer,tail]).removeSplitter()


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
            bolt = socket_screw(3,20.,(x,27.7,z),(0,-1,0))
            trapped = nut(3,(x,8.74,z),(0,1,0))
            tool = Part.makeCylinder(1.4, 20., V(x, 30.6, z), rear)
            for name, housing in (('frame', frame), ('rail', rail), ('ballast', ballast)):
                for solid in (bolt,trapped):
                    record(f'{axis} / {name}', solid.common(housing).Volume)
            record(f'{axis} / tool to frame', tool.common(frame).Volume)
        for z in (183.,189.):
            bolt = socket_screw(3,20.,(.9,0,z),(-1,0,0))
            tail = nut(3,(-12.4,0,z),(-1,0,0))
            for name, housing in (('motor', fixed['Part045']), ('plate', fixed['Part046']), ('rail',rail)):
                for solid in (bolt,tail):
                    record(f'motor mount {z:g} / {name}', solid.common(housing).Volume)

        y, z = rig['shaft_yz_mm']
        inserted = Part.makeCylinder(2.,116.,V(-58.,y,z),X)
        shaft_parts = ('Part050','Part052','Part053','Part054','Part055','BlinkCollarLeft','BlinkCollarRight')
        for name in shaft_parts:
            record(f'axial shaft insertion / {name}', inserted.common(world_shape(doc.getObject(name))).Volume)
        radial = [socket_screw(2,BLINK_CLAMP_LENGTH,(x,y,z+1.55+BLINK_CLAMP_LENGTH),(0,0,-1)).fuse(nut(2,(x,y,z+2.60),(0,0,1),(0,1,0)))
                  for x,_,_,_ in BLINK_CLAMPS]
        for part, hardware, (x,_,_,side) in zip(('Part053','Part054','Part055'),radial,BLINK_CLAMPS):
            crank = world_shape(doc.getObject(part))
            record(f'clamp screw / {part}',hardware.common(crank).Volume)
            shaft = fixed['Part048']
            record(f'clamp screw / shaft at {part}',hardware.common(shaft).Volume)
            if any(hardware.common(shaft.copy().rotate(V(0,y,z),X,a)).Volume < .005 for a in (-5.,5.)):
                raise RuntimeError(f'{part} screw failed to capture the shaft flat')
            for travel in (0.,.5,1.,1.5,2.,2.5,3.,3.5,4.,4.5,5.):
                sliding = nut(2,(x+side*travel,y,z+2.60),(0,0,1),(0,1,0))
                record(f'installing nut / {part}',sliding.common(crank).Volume)

        for angle in (-1, *range(0, 91, 3), 91):
            links = [(f'link {i}',fastener(joint,rig,angle)) for i,joint in enumerate(LINKS,start=1)]
            clamps = [(f'clamp {i}',shape.copy().rotate(V(0,y,z),X,angle)) for i,shape in enumerate(radial,start=1)]
            for name, hardware in links+clamps:
                for other, solid in fixed.items():
                    if name.startswith('clamp') and other == 'Part048':
                        continue
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
