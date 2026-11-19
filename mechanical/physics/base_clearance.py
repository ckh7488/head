"""Sweep the base, board trays, and service hatch for solid intersections."""

from argparse import ArgumentParser
from itertools import product
from math import cos, pi, radians, sin
from pathlib import Path
import json

import FreeCAD as App
import Part

V = App.Vector
CAD = Path(__file__).resolve().parents[1] / "R5-B3-Assembly.FCStd"


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
    for name in ("Part069", "Part070", "Part071", "Part072"):
        for static in (base, doc.Part001.Shape):
            yield doc.getObject(name).Shape, static, "Board placement"
    for depth in (0, 1, 3, 6, 10, 15, 22, 30):
        for part in doc.HubInstalled.Group:
            moving = part.Shape.copy().translate(V(0, 0, -depth))
            for static in (base, saddle, *fasteners):
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
        for name, pairs in [('Base', check_pairs(doc)), ('Actuators', actuator_pairs(doc))]:
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
