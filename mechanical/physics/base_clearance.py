"""Sweep the base, board trays, and service hatch for solid intersections."""

from argparse import ArgumentParser
from itertools import product
from math import cos, pi, radians, sin
from pathlib import Path
import json
import sys

import FreeCAD as App
import Part
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixtures import (
    CAP_BOLT_LENGTH, CAP_BOLT_SEAT_Z, CAP_BOLT_Y, CAP_NUT_FACE_Z,
    SADDLE_MOUNTS, SADDLE_NUT_Y, SADDLE_WASHER_Y,
)
from stock import YOKE_MOUNTS, nut, socket_screw
from neck_joint import MOUNTS, ROTOR_TOP, STUD_BOLT_SEAT, MAST_LENGTH
from service_hatch import HATCH_MOUNTS, HATCH_NUT_SEAT, HATCH_SCREW_SEAT, HUB_MOUNTS, HUB_NUT_SEAT, HUB_SCREW_SEAT

V = App.Vector
CAD = Path(__file__).resolve().parents[1] / "R5-B14-Assembly.FCStd"


def check_pairs(doc):
    rotors = [doc.Part007.Shape, doc.Part010.Shape]
    studs = [socket_screw(3, MAST_LENGTH, (x,y,STUD_BOLT_SEAT), (0,0,1)).fuse(nut(3,(x,y,ROTOR_TOP)))
             for x,y in MOUNTS]
    keepers = [doc.getObject(f"YawBearingRetainer{i}").Shape for i in range(1, 4)]
    fixed = [doc.getObject(name).Shape for name in ("Part000", "Part001", "Part002", "Part006")]
    for angle in range(-60, 61, 5):
        for rotor in (*rotors, *studs):
            moving = rotor.copy().rotate(V(), V(0, 0, 1), angle)
            for static in fixed + keepers:
                yield moving, static, f"Yaw at {angle} degrees"
    for keeper in keepers:
        for static in fixed:
            yield keeper, static, "Outer-race keeper"
    saddle = doc.CableSaddle.Shape
    base = doc.Part000.Shape
    yield saddle, base, "Saddle to base"
    gate = doc.CableGate.Shape
    yield gate, saddle, "Cable cover to keyed tray"
    yield gate, base, "Cable cover to base"
    along = V(0, -1, 0)
    fasteners = []
    for seat in SADDLE_MOUNTS:
        x, _, z = seat
        screw = socket_screw(3,16.,seat,(0,-1,0))
        washer = Part.makeCylinder(3.55, .8, V(x, SADDLE_WASHER_Y, z), along)
        washer = washer.cut(Part.makeCylinder(1.64, 1., V(x, SADDLE_WASHER_Y+.10, z), along))
        tail = nut(3,(x,SADDLE_NUT_Y,z),(0,-1,0))
        fasteners.extend((screw, washer, tail))
    for fastener in fasteners:
        for static in (base, saddle, doc.Part001.Shape, doc.Part069.Shape, doc.Part070.Shape):
            yield fastener, static, "Saddle fastener envelope"
    cables = json.loads(doc.R5.MotionGeometry)['cables']
    for x in cables['cap_bolts_x_mm']:
        screw = socket_screw(3,CAP_BOLT_LENGTH,(x,CAP_BOLT_Y,CAP_BOLT_SEAT_Z),(0,0,-1))
        tail = nut(3,(x,CAP_BOLT_Y,CAP_NUT_FACE_Z-2.4))
        for static, tool in product((base,saddle,gate),(screw,tail)):
            yield tool, static, f"Cable cover {x:g} screw and nut"
    for x,y in HATCH_MOUNTS:
        screw = socket_screw(3,8.,(x,y,HATCH_SCREW_SEAT),(0,0,1))
        tail = nut(3,(x,y,HATCH_NUT_SEAT))
        for tool, static in product((screw, tail),(base,doc.HubHolder.Shape,saddle,gate)):
            yield tool, static, "M3 service hatch fasteners"
    for x,y in HUB_MOUNTS:
        screw = socket_screw(3,8.,(x,y,HUB_SCREW_SEAT),(0,0,-1))
        tail = nut(3,(x,y,HUB_NUT_SEAT))
        for tool, static in product((screw,tail),(doc.HubHolder.Shape,doc.HubPCB.Shape)):
            yield tool, static, "M3 hub PCB fasteners"
    stop, center_z = cables['stop_y_mm'], cables['center_z_mm']
    for lane in cables['lanes']:
        name, x = lane['name'], lane['x_mm']
        width, height = (size-.24 for size in lane['pocket_mm'])
        length = lane['minimum_body_length_mm']
        plug = Part.makeBox(width, length, height, V(x-width/2, stop-length-.1, center_z-height/2))
        width, height = (size-.4 for size in lane['slot_mm'])
        cord = Part.makeBox(width, 7.6, height, V(x-width/2, stop-.1, center_z-height/2))
        for static in (saddle, gate, base):
            yield plug, static, f'{name} body in pocket'
            yield cord, static, f'{name} cord at outlet'
        width, height = lane['minimum_shoulder_mm']
        shoulder = Part.makeBox(width, length, height, V(x-width/2, stop-length+.4, center_z-height/2))
        if min(shoulder.common(part).Volume for part in (saddle, gate)) < .1:
            raise RuntimeError(f'{name} shoulder has no backing on both halves')
    for name in ("Part069", "Part070", "Part071", "Part072"):
        for static in (base, doc.Part001.Shape):
            yield doc.getObject(name).Shape, static, "Board placement"
    for depth in (0, 1, 3, 6, 10, 15, 22, 30):
        for part in doc.HubInstalled.Group:
            moving = part.Shape.copy().translate(V(0, 0, -depth))
            for static in (base, saddle, gate, *fasteners):
                yield moving, static, f"Hatch at {depth} mm, {part.Label}"


def actuator_pairs(doc):
    for x,y in YOKE_MOUNTS:
        bolt=socket_screw(3,16.,(x,y,75.),(0,0,-1))
        tail=nut(3,(x,y,59.64),flat_normal=(0,1,0))
        tool=Part.makeCylinder(1.45,25.,V(x,y,77.8))
        for hardware, part in product((bolt,tail,tool),(doc.Part010,doc.Part011,doc.Part018)):
            yield hardware, part.Shape, f"Neck mast fastener {x:g},{y:g} / {part.Name}"
        for offset in range(1,10):
            translated=tail.copy().translate(V(offset if x>0 else -offset,0,0))
            yield translated, doc.Part010.Shape, "Plain nut insertion into neck mast"

    yaw_motor = doc.Part038.Shape
    yoke = doc.Part011.Shape
    x_axis = V(1, 0, 0)
    for neck, eye in product((-15.25, -10., -5., 0., 3., 6.25), (-8.25, -4., 0., 4., 8.25)):
        motor = yaw_motor.copy().rotate(V(0, -39, 119), x_axis, eye).rotate(V(0, 0, 112), x_axis, neck)
        for body in motor.Solids:
            yield body, yoke, f"Eye yaw motor at neck {neck}, eye pitch {eye}"

    blink = json.loads(doc.R5.MotionGeometry)['blink']
    phase = radians(blink['phase_deg'])
    radius = blink['lid_radius_mm']
    motor = doc.Part041.Shape
    for angle, vertical in product(range(-1, 92, 2), (-.4, 0., .4)):
        moved = radians(angle) + phase
        offset = V(0, radius*(cos(moved)-cos(phase)), radius*(sin(moved)-sin(phase))+vertical)
        link = doc.Part060.Shape.copy().translate(offset)
        for body in motor.Solids:
            yield link, body, f"Right lid link at {angle} degrees and vertical offset {vertical} mm"


def ballast_pairs(doc):
    specs = json.loads(doc.R5.MotionGeometry)['ballast']
    tray, cover, stack = (doc.getObject(name).Shape for name in ('BallastTray', 'BallastCover', 'BallastStack'))
    frame = doc.Part019.Shape
    yield tray, frame, 'Ballast tray on head frame'
    yield tray, stack, 'Ballast stack in tray'
    behind = V(0, 1, 0)
    front_fixtures = [doc.getObject(name).Shape for name in ('Part041', 'Part045', 'Part063', 'Part064')]
    for x, z in specs['mount_xz_mm']:
        stem = socket_screw(3,16.,(x,35.3,z),(0,-1,0))
        tool = Part.makeCylinder(3.9, 28., V(x, 35.3, z), behind)
        seat = nut(3,(x,23.6,z),(0,1,0))
        for hardware in (stem, tool, seat):
            for static in (frame, tray, *front_fixtures):
                yield hardware, static, f'Ballast mount hardware at {x}, {z} mm'
        socket = Part.makeCylinder(4.65, 35., V(x,25.9,z), -behind)
        yield socket, frame, f'Ballast bench nut driver at {x}, {z} mm'
    for static in front_fixtures:
        yield frame, static, 'Head frame and actuator fixtures'
    for count, dx, dy in product(range(specs['maximum_plates']+1), (-.2, 0., .2), (-.2, 0., .2)):
        height = (count-specs['maximum_plates'])*specs['plate_mm'][2]
        moved = cover.copy().translate(V(dx, dy, height))
        yield moved, tray, f'Ballast cover at {count} plates, offset {dx}, {dy} mm'
    for name in ('BallastLeftStud', 'BallastRightStud'):
        stud = doc.getObject(name).Shape
        for solid in (tray, cover, stack):
            yield stud, solid, f'{name} clearance'


def check_pass(pairs):
    count = 0
    peak = 0.
    for count, (moving, static, label) in enumerate(pairs, start=1):
        if moving.BoundBox.intersect(static.BoundBox):
            volume = moving.common(static).Volume
            if volume > .003:
                raise RuntimeError(f"{label}: {volume:.4f} mm³ overlap")
            peak = max(volume, peak)
    return count, peak


def check(cad):
    doc = App.openDocument(str(cad))
    try:
        doc.recompute()
        for name, pairs in [('Base', check_pairs(doc)), ('Actuators', actuator_pairs(doc)),
                            ('Ballast', ballast_pairs(doc))]:
            count, peak = check_pass(pairs)
            print(f"{name}: {count} solid pairs, max residual volume {peak:.6f} mm³")
        print(f"Rotor lift clearance: {-32.45 - doc.Part007.Shape.BoundBox.ZMax:.3f} mm")
        print(f"Cable path from neutral to 60 degrees: {25 * pi / 3:.3f} mm")
    finally:
        App.closeDocument(doc.Name)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--cad", type=Path, default=CAD)
    check(parser.parse_args().cad.resolve())
