"""Bench-installed mast studs with accessible nuts above the rotor."""

from FreeCAD import Vector
import Part

from primitives import box, cylinder

MOUNTS = tuple((x, y) for x in (-23., 23.) for y in (13., 26.))
HORN = ((-8., 0.), (0., -8.), (8., 0.), (0., 8.))
ROTOR_TOP = -32.9
ROTOR_BOTTOM = -37.9
STUD_BOLT_SEAT = -36.20
MAST_SEAT = -25.60
HORN_SEAT = ROTOR_TOP
MAST_LENGTH = 16.
HORN_LENGTH = 8.
PITCH_HORN = ((8., 112.), (-8., 112.), (0., 120.), (0., 104.))
PITCH_HORN_SEAT = 41.20


def yaw_connector_opening():
    x = -29.
    outline = [(8.7, -64.75), (19.5, -64.75), (19.5, -59.45),
               (15.9, -55.85), (12.3, -55.85), (8.7, -59.45)]
    wire = Part.makePolygon([Vector(x, y, z) for y, z in outline + outline[:1]])
    return Part.Face(wire).extrude(Vector(17.1, 0, 0))


def pitch_connector_opening():
    return box(9.05, 14.65, 11.8, 34., 92.35, 103.45)


def eye_connector_clearance():
    return box(-3.25, 9.70, -25., -14.20, 86.75, 103.25)


def neck_base(rotor, mast):
    for x in (-12., 12.):
        for y in (11., 31.):
            rotor = rotor.fuse(cylinder(1.77, 5., (x, y, ROTOR_BOTTOM)))
    rotor = rotor.cut([
        cylinder(1.20, 9., (x, y, ROTOR_BOTTOM-.1)) for x, y in HORN
    ])

    wings = [box(left, right, 8.3, 34.5, ROTOR_TOP, MAST_SEAT)
             for left, right in ((-27.65, -13.0), (13., 27.65))]
    rim_limit = cylinder(41.7, 8.5, (0., 0., -33.8))
    braces = [box(left, right, 9., 33., MAST_SEAT-.45, -23.2)
              for left, right in ((-19.70, -15.8), (15.8, 19.70))]
    mast = mast.fuse([wing.common(rim_limit) for wing in wings] + braces)
    mast = mast.cut(cylinder(3.43, 4.53, (0., 8., ROTOR_TOP-.12)))
    for x, y in MOUNTS:
        pad = cylinder(4.52, ROTOR_TOP - ROTOR_BOTTOM, (x, y, ROTOR_BOTTOM))
        rotor = rotor.fuse(pad).cut([
            cylinder(3.05, STUD_BOLT_SEAT - ROTOR_BOTTOM + 1., (x, y, ROTOR_BOTTOM-1.)),
            cylinder(1.80, ROTOR_TOP - STUD_BOLT_SEAT + .5, (x, y, STUD_BOLT_SEAT-.22)),
        ])
        left,right = (x-20., x+5.0) if x < 0 else (x-5.0,x+20.)
        mast = mast.cut([
            box(left,right,y-8.9,y+8.9,ROTOR_TOP-.18,-28.15),
            cylinder(1.80, 8., (x, y, ROTOR_TOP-.18)),
            cylinder(5.30, 7.5, (x, y, MAST_SEAT)),
        ])

    return rotor.removeSplitter(), mast.removeSplitter()
