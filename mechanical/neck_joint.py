"""Captive rotor nuts and top-access mast fasteners."""

from primitives import box, cylinder

MOUNTS = tuple((x, y) for x in (-23., 23.) for y in (13., 26.))
HORN = ((-8., 0.), (0., -8.), (8., 0.), (0., 8.))
ROTOR_TOP = -32.9
ROTOR_BOTTOM = -37.9
NUT_ROOF = -35.10
MAST_SEAT = -29.80
HORN_SEAT = ROTOR_TOP
MAST_LENGTH = 8.
HORN_LENGTH = 8.
PITCH_HORN = ((8., 112.), (-8., 112.), (0., 120.), (0., 104.))
PITCH_HORN_SEAT = 41.20


def neck_base(rotor, mast, hexagon):
    for x in (-12., 12.):
        for y in (11., 31.):
            rotor = rotor.fuse(cylinder(1.77, 5., (x, y, ROTOR_BOTTOM)))
    rotor = rotor.cut([
        cylinder(1.20, 9., (x, y, ROTOR_BOTTOM-.1)) for x, y in HORN
    ])

    wings = [box(left, right, 8.3, 34.5, ROTOR_TOP, MAST_SEAT)
             for left, right in ((-27.65, -13.0), (13., 27.65))]
    rim_limit = cylinder(41.7, 5., (0., 0., -33.8))
    braces = [box(left, right, 9., 33., MAST_SEAT-.45, -23.2)
              for left, right in ((-19.70, -15.8), (15.8, 19.70))]
    mast = mast.fuse([wing.common(rim_limit) for wing in wings] + braces)
    mast = mast.cut(cylinder(3.43, 4.53, (0., 8., ROTOR_TOP-.12)))
    for x, y in MOUNTS:
        rotor = rotor.cut([
            hexagon(5.93, NUT_ROOF - ROTOR_BOTTOM + .12, (x, y, ROTOR_BOTTOM-.12)),
            cylinder(1.70, 2.40, (x, y, NUT_ROOF-.1)),
        ])
        mast = mast.cut(cylinder(1.70, 3.5, (x, y, ROTOR_TOP-.18)))

    return rotor.removeSplitter(), mast.removeSplitter()
