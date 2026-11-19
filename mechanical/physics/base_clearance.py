"""Sweep the base, board trays, and service hatch for solid intersections."""

from argparse import ArgumentParser
from itertools import product
from math import cos, pi, radians, sin
from pathlib import Path
import json

import FreeCAD as App
import Part

V = App.Vector
CAD = Path(__file__).resolve().parents[1] / "R5-B5-Assembly.FCStd"


def check_pairs(doc):
    rotors = [doc.Part007.Shape, doc.Part010.Shape]
    keepers = [doc.getObject(f"YawBearingRetainer{i}").Shape for i in range(1, 4)]
    fixed = [doc.getObject(name).Shape for name in ("Part000", "Part001", "Part002", "Part006")]
    for angle in range(-60, 61, 5):
        for rotor in rotors:
            moving = rotor.copy().rotate(V(), V(0, 0, 1), angle)
            for static in fixed + keepers:
                yield moving, static, f"Yaw at {angle} degrees"
    for keeper in keepers:
        for static in fixed:
            yield keeper, static, "Outer-race keeper"
    for column in (doc.Part003, doc.Part004, doc.Part005):
        yield column.Shape, doc.Part002.Shape, "Top cap on standoffs"

    saddle = doc.CableSaddle.Shape
    base = doc.Part000.Shape
    yield saddle, base, "Saddle to base"
    gate = doc.CableGate.Shape
    yield gate, saddle, "Cable cover to keyed tray"
    yield gate, base, "Cable cover to base"
    along = V(0, -1, 0)
    fasteners = []
    for x in (-28.5, 28.5):
        screw = Part.makeCylinder(1.5, 18, V(x, 93.6, -71), along)
        washer = Part.makeCylinder(3.55, .8, V(x, 83.75, -71), along)
        washer = washer.cut(Part.makeCylinder(1.64, 1., V(x, 83.85, -71), along))
        nut = Part.makeCylinder(3.25, 4., V(x, 82.95, -71), along)
        nut = nut.cut(Part.makeCylinder(1.62, 4.2, V(x, 83.05, -71), along))
        fasteners.extend((screw, washer, nut))
    for fastener in fasteners:
        for static in (base, saddle, doc.Part001.Shape, doc.Part069.Shape, doc.Part070.Shape):
            yield fastener, static, "Saddle fastener envelope"
    cables = json.loads(doc.R5.MotionGeometry)['cables']
    for x in cables['cap_bolts_x_mm']:
        stem = Part.makeCylinder(1.5, 13., V(x,121.6,-49.1), V(0,0,-1))
        for static in (base, saddle, gate):
            yield stem, static, "Cable cover screw clearance"
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
        stem = Part.makeCylinder(1.5, 8., V(x, 35.3, z), -behind)
        tool = Part.makeCylinder(3.9, 28., V(x, 35.3, z), behind)
        seat = Part.makeCylinder(2.09, 4., V(x, 27., z), behind)
        for hardware in (stem, tool, seat):
            for static in (frame, tray, *front_fixtures):
                yield hardware, static, f'Ballast mount hardware at {x}, {z} mm'
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
