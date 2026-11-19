"""Common open-end wrench and socket envelopes in assembly millimetres."""

from math import cos, radians, sin

from FreeCAD import Vector as V
import Part

NUT_HEIGHT = {2: 1.60, 3: 2.40}
SOCKET_BORE = {2: 4.35, 3: 5.30}
SOCKET_RADIUS = {2: 3.70, 3: 4.65}
KEY_RADIUS = {2: .89, 3: 1.48}
WRENCH_THICKNESS = {2: 3.0, 3: 4.2}


def wrench_profile(size, angle=0.):
    jaw, width, nose, shoulder = {2: (2.06, 5.3, 3.2, 5.5), 3: (2.81, 8., 4.0, 7.7)}[size]
    a = radians(angle)
    profile = [
        (-width, -nose), (-width, 2.1), (-3., shoulder),
        (-3., 56.), (3., 56.), (3., shoulder), (width, 2.1),
        (width, -nose), (jaw, -nose), (jaw, jaw + .43), (-jaw, jaw + .43), (-jaw, -nose),
    ]
    return tuple((x*cos(a)-y*sin(a), x*sin(a)+y*cos(a)) for x,y in profile)


def wrench_shape(seat, axis, outward, profile, depth):
    normal, handle = V(*axis), V(*outward)
    cross = handle.cross(normal)
    path = [V(*seat) + x*cross + y*handle for x,y in profile]
    return Part.Face(Part.makePolygon(path + path[:1])).extrude(depth*normal)
