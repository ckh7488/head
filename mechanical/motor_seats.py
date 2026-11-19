"""Motor mounting faces for cylindrical hex-socket heads, in assembly millimetres."""

from itertools import product

from FreeCAD import Vector as V

from primitives import cylinder

JAW_STAY = 'Jaw_36_left_jaw_servo_stay'

# Each entry is (diameter, original face point, outward normal, recess depth).
HEAD_SEATS = {
    'Part039': [
        (2, (x, y, 111.55), (0, 0, 1), 1.85 if (x, y) == (-13.3, -27.5) else 0.)
        for x, y in product((-13.3, 16.7), (-43.5, -27.5))
    ],
    'Part042': [
        (2, (58.35, y, z), (1, 0, 0), 0.)
        for y, z in product((2., 18.), (128.5, 158.5))
    ] + [
        (3, (58.35, y, 164.3), (1, 0, 0), 0.) for y in (4.6, 15.4)
    ],
    'Part046': [
        (2, (.9, y, z), (1, 0, 0), 1.85 if (y, z) == (-6., 162.5) else 0.)
        for y, z in product((-22., -6.), (162.5, 192.5))
    ],
    JAW_STAY: [
        (2, (-43.5, y, z), (-1, 0, 0), {(-17., 84.5): 1.85, (-1., 114.5): 1.60}.get((y, z), 0.))
        for y, z in product((-17., -1.), (84.5, 114.5))
    ],
}


def head_pockets(part):
    return [
        cylinder(2.15, depth + .06, tuple(V(*face) + .06 * V(*outward)), tuple(-V(*outward)))
        for _, face, outward, depth in HEAD_SEATS[part] if depth
    ]
