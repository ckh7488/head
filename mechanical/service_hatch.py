"""Removable service hatch with through bolts and side tool access."""

from math import hypot

from FreeCAD import Vector as V
import Part

from primitives import box, cylinder, print_mesh

HATCH_MOUNTS = tuple((x, y) for x in (-41.2, 41.2) for y in (51., 71.))
HUB_MOUNTS = tuple((x, y) for x in (-30.8, 30.8) for y in (46.2, 72.8))
HATCH_BOTTOM = -82.90
HATCH_SCREW_SEAT = -79.65
HATCH_NUT_SEAT = -74.78
HUB_NUT_SEAT = -80.05
HUB_SCREW_SEAT = -72.50
HATCH_WRENCH_WIDTH = 18.
HATCH_WRENCH_HEIGHT = 7.2
HATCH_WINDOW_CENTER_Y = 61.
HATCH_WINDOW_EDGE_X = 95.
HATCH_WINDOW_ROOF = 4.5
LEGACY_HATCH_MOUNTS = ((-41.85, 55.), (41.85, 55.), (-26.9, 82.25), (26.9, 82.25))
OPENING = [
    (-37., 39.5), (37., 39.5), (37., 73.7), (32., 79.4), (19.4, 79.4), (19.4, 86.5),
    (-19.4, 86.5), (-19.4, 79.4), (-32., 79.4), (-37., 73.7),
]
FLANGE = [
    (-41., 36.8), (41., 36.8), (41., 44.8), (47.8, 44.8), (47.8, 74.),
    (33., 85.9), (22.7, 85.9), (21.8, 89.1), (-21.8, 89.1), (-22.7, 85.9),
    (-33., 85.9), (-47.8, 74.), (-47.8, 44.8), (-41., 44.8),
]


def inset(vertices, clearance):
    def normal(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = hypot(dx, dy)
        return -dy / length, dx / length

    result = []
    for i, (x, y) in enumerate(vertices):
        before = normal(vertices[i - 1], vertices[i])
        after = normal(vertices[i], vertices[(i + 1) % len(vertices)])
        scale = clearance / (1 + before[0] * after[0] + before[1] * after[1])
        result.append((x + scale * (before[0] + after[0]), y + scale * (before[1] + after[1])))
    return result


def wire(points, z):
    return Part.makePolygon([V(x, y, z) for x, y in points + points[:1]])


def prism(points, bottom, top):
    return Part.Face(wire(points, bottom)).extrude(V(0, 0, top - bottom))


def wrench_window(x, y):
    sense = 1 if x > 0 else -1
    z = HATCH_NUT_SEAT
    shoulder = z + HATCH_WRENCH_HEIGHT
    half_width = HATCH_WRENCH_WIDTH / 2
    sections = []
    for at, half in ((x - sense*6.1, half_width), (x+sense*14., half_width),
                     (sense*HATCH_WINDOW_EDGE_X, 18.5)):
        low = y - (half if y < HATCH_WINDOW_CENTER_Y else half_width)
        high = y + (half_width if y < HATCH_WINDOW_CENTER_Y else half)
        section = [(low, z), (high, z), (high, shoulder),
                   (high-HATCH_WINDOW_ROOF, shoulder+HATCH_WINDOW_ROOF),
                   (low+HATCH_WINDOW_ROOF, shoulder+HATCH_WINDOW_ROOF), (low, shoulder)]
        sections.append(Part.makePolygon([V(at,a,b) for a,b in section + section[:1]]))
    return Part.makeLoft(sections, True, True)


def wrench_window_mouth(side):
    shoulder = HATCH_NUT_SEAT + HATCH_WRENCH_HEIGHT
    taper_start = -70.05
    sections = []
    # Keep the outer entries open around the wrench and grow the web at 45° above it.
    for z in (HATCH_NUT_SEAT, taper_start, shoulder, shoulder+HATCH_WINDOW_ROOF):
        inner_x = 62. + max(0., z-taper_start)
        lo, hi = sorted((side*inner_x, side*HATCH_WINDOW_EDGE_X))
        half_width = 1.24 + max(0., z-shoulder)
        y_lo, y_hi = HATCH_WINDOW_CENTER_Y-half_width, HATCH_WINDOW_CENTER_Y+half_width
        sections.append(wire([(lo, y_lo), (hi, y_lo), (hi, y_hi), (lo, y_hi)], z))
    return Part.makeLoft(sections, True, True)


def revise_service(base):
    healed = [cylinder(4.08, 4.3, (x, y, -80.30)) for x, y in LEGACY_HATCH_MOUNTS]
    band = prism(inset(FLANGE, -2.7), -79.5, -76.0).common(cylinder(90.6, 3.8, (0, 0, -79.65)))
    bosses = [cylinder(5.7, 6.98, (x, y, -78.38)) for x, y in HATCH_MOUNTS]
    cable_fastener_reliefs = [
        cutter for x in (-28.5, 28.5) for cutter in (
            cylinder(1.82, 16.4, (x, 93.8, -71.), (0, -1, 0)),
            cylinder(5.30, 15., (x, 84.05, -71.), (0, -1, 0)),
        )
    ]
    base = base.fuse([band, *healed, *bosses]).cut([
        prism(FLANGE, -83.4, -78.66),
        prism(OPENING, -83.4, -73.4),
        box(-14.1, -.7, 82., 88.1, -83.2, -69.0),
        *cable_fastener_reliefs,
    ])
    for x, y in HATCH_MOUNTS:
        base = base.cut([
            cylinder(5.4, 3.0, (x, y, -79.66)),
            cylinder(1.85, 4.5, (x, y, -78.8)),
            wrench_window(x, y),
        ])
    base = base.cut([wrench_window_mouth(-1), wrench_window_mouth(1)])

    flange = prism(inset(FLANGE, .55), HATCH_BOTTOM + .34, -78.9)
    chamfer = Part.makeLoft([
        wire(inset(FLANGE, .89), HATCH_BOTTOM),
        wire(inset(FLANGE, .55), HATCH_BOTTOM + .36),
    ], True, True)
    center = prism(inset(OPENING, .58), -79.02, -77.90)
    hatch = flange.fuse([chamfer, center])
    for x, y in HATCH_MOUNTS:
        hatch = hatch.fuse(cylinder(4.65, 2.1, (x, y, -79.0))).cut([
            cylinder(3.15, 3.4, (x, y, HATCH_SCREW_SEAT - 3.4)),
            cylinder(1.85, 7., (x, y, HATCH_SCREW_SEAT - .1)),
        ])
    for x, y in HUB_MOUNTS:
        foot = cylinder(4.9, 2.8, (x, y, -77.96))
        crown = Part.makeCone(4.9, 4.38, 1.12, V(x, y, -75.22))
        collar = cylinder(6.85, 2.2, (x, y, -79.12)).common(prism(inset(OPENING, .58), -79.4, -76.8))
        face = HUB_NUT_SEAT + 2.4
        hatch = hatch.fuse([foot, crown, collar]).cut([
            cylinder(5.30, face + 83.2, (x, y, -83.2)),
            cylinder(1.80, 4.1, (x, y, face-.12)),
        ])
    return base.removeSplitter(), hatch.removeSplitter()


def service_coupon(base, output):
    coupon = base.common(box(-53., 53., 33.7, 93.3, -83.1, -69.5)).removeSplitter()
    if len(coupon.Solids) != 1 or not coupon.isValid():
        raise ValueError('Service fit coupon must be one printable solid')
    print_mesh(coupon, output / '46_service_fit_coupon.stl')
