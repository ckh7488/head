"""Separate the bearing seat and lid fasteners so each can be reached from above."""

from math import cos, radians, sin

from FreeCAD import Vector as V

from primitives import box, cylinder

SUPPORT_ANGLES = (-90., 30., 150.)
KEEPER_ANGLES = (0., 120., 240.)
SEAT_RADIUS, LID_RADIUS, KEEPER_RADIUS = 63., 85., 56.4
SEAT_BOLT_Z, LID_BOLT_Z, KEEPER_BOLT_Z = -37., -25.8, -33.55
SEAT_NUT_Z, LID_NUT_Z, KEEPER_NUT_Z = -52.60, -33.38, -41.13
CARRIER_BOLT_Z, CARRIER_NUT_Z = -74.3, -81.90
CARRIER_MOUNTS = tuple((side*55.+x, y) for side in (-1, 1)
                       for x in (-13., 13.) for y in (-35., 7.))


def center(radius, angle):
    angle = radians(angle)
    return radius*cos(angle), radius*sin(angle)


def rotate(shape, angle):
    return shape.rotate(V(), V(0., 0., 1.), angle)


def capture(shape, radius, angle, seat, access, top, tip, hexagon):
    bottom = seat-.21
    roof = seat+2.43
    pocket = hexagon(5.94, roof-bottom, (radius, 0., bottom), flat_normal=(0., 1., 0.))
    lo, hi = sorted((access, radius+.04 if access < radius else radius-.04))
    slot = box(lo, hi, -2.97, 2.97, bottom, roof)
    pilot = cylinder(1.72, top-tip+.25, (radius, 0., tip-.14))
    return shape.cut([rotate(tool, angle) for tool in (pocket, slot, pilot)])


def mounting_stack(base, seat, lid, hexagon):
    for angle in SUPPORT_ANGLES:
        base = base.fuse(rotate(box(79.6, 92.1, -4.5, 4.5, -38.1, -29.), angle))
        base = capture(base, LID_RADIUS, angle, LID_NUT_Z, 79.2, -28.85, -34.0, hexagon)
        base = capture(base, SEAT_RADIUS, angle, SEAT_NUT_Z, 53.0, -48.9, -53.25, hexagon)
        lid = lid.fuse(cylinder(1.89, 3.2, (*center(SEAT_RADIUS, angle), -29.)))
        lid = lid.cut(cylinder(1.73, 3.8, (*center(LID_RADIUS, angle), -29.25)))

    for angle in KEEPER_ANGLES:
        seat = capture(seat, KEEPER_RADIUS, angle, KEEPER_NUT_Z, 69.5, -36.8, -41.85, hexagon)
    for x, y in CARRIER_MOUNTS:
        base = base.cut([
            hexagon(5.92, 3.72, (x, y, -83.18)),
            cylinder(1.72, 2.55, (x, y, -79.63)),
        ])
    return tuple(part.removeSplitter() for part in (base, seat, lid))
