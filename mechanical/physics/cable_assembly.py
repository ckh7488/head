"""Check the paths shown in the cable clamp assembly walkthrough."""

from argparse import ArgumentParser
from itertools import product
from pathlib import Path
import sys

import FreeCAD as App
import Part
from scipy.spatial import ConvexHull

from base_clearance import check_pass
from export_cad import world_shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixtures import (
    CAP_BOLT_LENGTH, CAP_BOLT_SEAT_Z, CAP_BOLT_Y, CAP_BOLTS, CAP_NUT_FLOOR_Z,
    CAP_NUT_ROOF_Z, CAP_NUT_TRAVEL, CAP_TRAVEL, SADDLE_BOLT_TRAVEL,
    SADDLE_INNER_TRAVEL, SADDLE_MOUNTS, SADDLE_NUT_Y, SADDLE_TRAVEL, SADDLE_WASHER_Y,
)
from primitives import cylinder
from stock import hexagon, nut

V = App.Vector
Y, Z = (0, 1, 0), (0, 0, 1)
NUT_THICKNESS = 2.4


def nut_sweep(x, dx, dy, lift, angle):
    z = CAP_NUT_FLOOR_Z + lift
    tail = nut(3, (x + dx, CAP_BOLT_Y + dy, z))
    tail.rotate(V(x + dx, CAP_BOLT_Y + dy, z), V(*Z), angle)
    points = [(v.Point.x, v.Point.y) for v in tail.Vertexes if abs(v.Point.z - z) < 1e-6]
    points += [(px, py + CAP_NUT_TRAVEL) for px, py in points]
    perimeter = [V(*points[i], z) for i in ConvexHull(points).vertices]
    return Part.Face(Part.makePolygon(perimeter + perimeter[:1])).extrude(V(0, 0, NUT_THICKNESS))


def fastener_sweep(seat, length, outward, travel):
    axis = V(*outward)
    shank = cylinder(1.50, length + travel, tuple(V(*seat) - length * axis), outward)
    head = cylinder(2.78, 3. + travel, seat, outward)
    return shank.fuse(head)


def check_paths(doc):
    base, tray, cover = map(world_shape, (doc.Part000, doc.CableSaddle, doc.CableGate))
    nut_paths = (
        (nut_sweep(x, dx, dy, lift, angle), tray,
         f'M3 nut at x={x:g}, offset ({dx:g}, {dy:g}, {lift:g}) and angle {angle:g}°')
        for x, dx, dy, lift, angle in product(CAP_BOLTS, (-.12, 0., .12), (-.12, 0., .12),
                                              (.015, .22, .58), (-2., 0., 2.))
    )
    results = {'nut_paths': check_pass(nut_paths)}
    for x, dy, z in product(CAP_BOLTS, (-.18, 0., .18), (CAP_NUT_FLOOR_Z+.02, CAP_NUT_ROOF_Z-2.19)):
        smallest = hexagon(5.32, 2.15, (x, CAP_BOLT_Y + dy, z))
        smallest.rotate(V(x, CAP_BOLT_Y + dy, z), V(*Z), 30.)
        if smallest.common(tray).Volume <= .015:
            raise ValueError(f'M3 nut at x={x:g} can spin while tightening')

    if CAP_BOLT_SEAT_Z - CAP_BOLT_LENGTH > CAP_NUT_ROOF_Z - NUT_THICKNESS - .45:
        raise ValueError('Cover screw has insufficient engagement in the nut')
    bearing_areas = []
    for x in CAP_BOLTS:
        center = x, CAP_BOLT_Y, CAP_NUT_ROOF_Z
        footprint = hexagon(5.32, .08, center)
        bearing_areas.append(footprint.common(tray).Volume / .08)
    if min(bearing_areas) < 14.:
        raise ValueError('Insufficient flat material above the cover nut')

    results['tray_positions'] = check_pass(
        (tray.translated(V(0, i / 2, 0)), base, f'Tray at {i/2:g} mm')
        for i in range(round(SADDLE_TRAVEL * 2) + 1)
    )
    results['cover_positions'] = check_pass(
        (cover.translated(V(0, 0, i / 2)), fixed, f'Cover at {i/2:g} mm')
        for i, fixed in product(range(round(CAP_TRAVEL * 2) + 1), (tray, base))
    )
    results['fastener_paths'] = check_pass(
        (fastener_sweep((x, CAP_BOLT_Y, CAP_BOLT_SEAT_Z), CAP_BOLT_LENGTH, Z, CAP_TRAVEL),
         fixed, f'Cover screw at x={x:g}')
        for x, fixed in product(CAP_BOLTS, (tray, cover, base))
    )
    for seat in SADDLE_MOUNTS:
        x, _, z = seat
        inside = NUT_THICKNESS + SADDLE_INNER_TRAVEL
        washer = cylinder(3.55, .8 + SADDLE_INNER_TRAVEL, (x, SADDLE_WASHER_Y, z), (0, -1, 0))
        tail = hexagon(5.5, inside, (x, SADDLE_NUT_Y, z), (0, -1, 0))
        screw = fastener_sweep(seat, 16., Y, SADDLE_BOLT_TRAVEL)
        check_pass((part, fixed, f'Tray bolt and inside hardware at x={x:g}')
                   for part, fixed in product((screw, washer, tail), (base, tray)))
    return results, min(bearing_areas)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    args = parser.parse_args()
    doc = App.openDocument(str(args.cad.resolve()))
    try:
        checks, area = check_paths(doc)
        for name, (count, overlap) in checks.items():
            print(f'{name}: {count} pairs, maximum overlap {overlap:.6f} mm³')
        print(f'Tray hardware paths clear, minimum nut bearing area {area:.2f} mm²')
    finally:
        App.closeDocument(doc.Name)
