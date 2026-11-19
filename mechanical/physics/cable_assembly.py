"""Check the paths shown in the cable clamp assembly walkthrough."""

from argparse import ArgumentParser
from itertools import product
from pathlib import Path
import sys

import FreeCAD as App
import Part

from base_clearance import check_pass
from export_cad import world_shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixtures import (
    CAP_BOLT_LENGTH, CAP_BOLT_SEAT_Z, CAP_BOLT_Y, CAP_BOLTS, CAP_NUT_FACE_Z,
    CAP_WRENCH_TRAVEL, CAP_TRAVEL, SADDLE_BOLT_TRAVEL,
    SADDLE_INNER_TRAVEL, SADDLE_MOUNTS, SADDLE_NUT_Y, SADDLE_TRAVEL, SADDLE_WASHER_Y,
)
from primitives import cylinder
from stock import hexagon
from tool_access import NUT_HEIGHT, WRENCH_THICKNESS, wrench_profile, wrench_shape

V = App.Vector
Y, Z = (0, 1, 0), (0, 0, 1)
NUT_THICKNESS = NUT_HEIGHT[3]


def fastener_sweep(seat, length, outward, travel):
    axis = V(*outward)
    shank = cylinder(1.50, length + travel, tuple(V(*seat) - length * axis), outward)
    head = cylinder(2.78, 3. + travel, seat, outward)
    return shank.fuse(head)


def check_paths(doc):
    base, tray, cover = map(world_shape, (doc.Part000, doc.CableSaddle, doc.CableGate))
    def wrench_paths():
        thickness = WRENCH_THICKNESS[3]
        for x, angle, dx, dz in product(CAP_BOLTS, (-15., 0., 15.), (-.24, .24), (-.15, .15)):
            tool = wrench_shape((x+dx, CAP_BOLT_Y, CAP_NUT_FACE_Z-thickness-.26+dz),
                                Z, Y, wrench_profile(3, angle), thickness)
            for travel in range(int(CAP_WRENCH_TRAVEL)+1):
                placed = tool.translated(V(0, travel, 0))
                for fixed in (tray, cover, base):
                    yield placed, fixed, f'5.5 mm cable spanner at x={x:g}, y+{travel:g}, {angle:g}°'

    results = {'wrench_paths': check_pass(wrench_paths())}
    if CAP_BOLT_SEAT_Z - CAP_BOLT_LENGTH > CAP_NUT_FACE_Z - NUT_THICKNESS - .45:
        raise ValueError('Cover screw has insufficient engagement in the nut')
    bearing_areas = []
    for x in CAP_BOLTS:
        center = x, CAP_BOLT_Y, CAP_NUT_FACE_Z
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
    results['nut_paths'] = check_pass(
        (hexagon(5.50, NUT_THICKNESS+12., (x, CAP_BOLT_Y, CAP_NUT_FACE_Z-NUT_THICKNESS-12.)),
         tray, f'Hand-started M3 nut from below at x={x:g}')
        for x in CAP_BOLTS
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
