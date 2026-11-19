"""B8 removable service hatch with top-loaded standard M3 nuts."""

from math import hypot

from FreeCAD import Vector as V
import Part

from primitives import box, cylinder, print_mesh

HATCH_MOUNTS = tuple((x, y) for x in (-41.2, 41.2) for y in (51., 71.))
HUB_MOUNTS = tuple((x, y) for x in (-30.8, 30.8) for y in (46.2, 72.8))
HATCH_BOTTOM = -82.90
HATCH_SCREW_SEAT = -79.65
HATCH_NUT_SEAT = -74.78
HUB_NUT_SEAT = -76.80
HUB_SCREW_SEAT = -72.50
NUT_WIDTH = 5.95
NUT_MOUTH = 6.65
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


def nut_pocket(x, y, bottom, top, hexagon, mouth=NUT_MOUTH):
    flat = hexagon(NUT_WIDTH, top - bottom + .10, (x, y, bottom))
    entry_wires = []
    for size, z in ((NUT_WIDTH, top - .5), (mouth, top), (mouth, top + .16)):
        faces = hexagon(size, .2, (x, y, z)).Faces
        face = next(f for f in faces if abs(f.BoundBox.ZMax - z) < .0001)
        entry_wires.append(face.OuterWire)
    entry = Part.makeLoft(entry_wires, True, True)
    return flat.fuse(entry)


def revise_service(base, hexagon):
    healed = [cylinder(4.08, 4.3, (x, y, -80.30)) for x, y in LEGACY_HATCH_MOUNTS]
    band = prism(inset(FLANGE, -2.7), -79.5, -76.0).common(cylinder(90.6, 3.8, (0, 0, -79.65)))
    bosses = [cylinder(5.7, 6.98, (x, y, -78.38)) for x, y in HATCH_MOUNTS]
    cable_fastener_reliefs = [
        cutter for x in (-28.5, 28.5) for cutter in (
            cylinder(1.82, 16.4, (x, 93.8, -71.), (0, -1, 0)),
            cylinder(3.8, 3.75, (x, 84.05, -71.), (0, -1, 0)),
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
            nut_pocket(x, y, HATCH_NUT_SEAT, -71.4, hexagon),
        ])

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
        hatch = hatch.fuse([foot, crown]).cut([
            cylinder(1.85, 5.2, (x, y, -81.25)),
            nut_pocket(x, y, HUB_NUT_SEAT, -74.10, hexagon, 6.35),
        ])
    return base.removeSplitter(), hatch.removeSplitter()


def service_coupon(base, output):
    coupon = base.common(box(-53., 53., 33.7, 93.3, -83.1, -69.5)).removeSplitter()
    if len(coupon.Solids) != 1 or not coupon.isValid():
        raise ValueError('Service fit coupon must be one printable solid')
    print_mesh(coupon, output / '46_service_fit_coupon.stl')
