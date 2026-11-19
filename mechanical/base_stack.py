"""Separate the bearing seat and lid fasteners so each can be reached from above."""

from math import cos, radians, sin

from FreeCAD import Vector as V

from primitives import box, cylinder

SUPPORT_ANGLES = (-90., 30., 150.)
KEEPER_ANGLES = (0., 120., 240.)
SEAT_RADIUS, LID_RADIUS, KEEPER_RADIUS = 63., 85., 56.4
SEAT_BOLT_Z, LID_BOLT_Z, KEEPER_BOLT_Z = -50.15, -31.05, -38.75
SEAT_NUT_Z, LID_NUT_Z, KEEPER_NUT_Z = -37., -25.8, -33.55
CARRIER_BOLT_Z, CARRIER_NUT_Z = -79.45, -74.3
CARRIER_MOUNTS = tuple((x, y) for x in (-76., -32., 35., 70.) for y in (-28., 7.))
M3_HEAD_BORE = 3.56


def center(radius, angle):
    angle = radians(angle)
    return radius*cos(angle), radius*sin(angle)


def rotate(shape, angle):
    return shape.rotate(V(), V(0., 0., 1.), angle)


def lower_head(shape, x, y, seat, through):
    return shape.cut([
        cylinder(M3_HEAD_BORE, seat + 84., (x, y, -84.)),
        cylinder(1.80, through-seat+.22, (x, y, seat-.18)),
    ])


def mounting_stack(base, seat, lid):
    for angle in SUPPORT_ANGLES:
        base = base.fuse(rotate(box(79.6, 92.1, -4.5, 4.5, -38.1, -29.), angle))
        base = lower_head(base, *center(LID_RADIUS, angle), LID_BOLT_Z, -28.85)
        base = lower_head(base, *center(SEAT_RADIUS, angle), SEAT_BOLT_Z, -48.9)
        seat = seat.cut(cylinder(1.80, 15., (*center(SEAT_RADIUS, angle), -49.8)))
        lid = lid.fuse(cylinder(1.89, 3.2, (*center(SEAT_RADIUS, angle), -29.)))
        lid = lid.cut(cylinder(1.73, 3.8, (*center(LID_RADIUS, angle), -29.25)))

    for angle in KEEPER_ANGLES:
        seat = lower_head(seat, *center(KEEPER_RADIUS, angle), KEEPER_BOLT_Z, -36.8)
    for x, y in CARRIER_MOUNTS:
        base = lower_head(base, x, y, CARRIER_BOLT_Z, -77.22)
    return tuple(part.removeSplitter() for part in (base, seat, lid))
