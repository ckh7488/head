"""Capture the four stock bottom-hatch nuts while keeping the external screws removable."""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App

from build_b19_review_fixes import add_part, replace
from build_b21_fasteners import check_solid, detached_shape
from primitives import box, cylinder, print_mesh
from service_hatch import HATCH_MOUNTS, HATCH_NUT_SEAT
from stock import hexagon, socket_screw


_UP = (0., 0., 1.)
_DOWN = (0., 0., -1.)
NUT_FLAT_MM = 5.80
CAGE_RADIUS_MM = 5.05
KEEPER_PAD_RADIUS_MM = 4.65
KEEPER_WEB_HALF_WIDTH_MM = 2.05
KEEPER_ANCHOR_PAD_RADIUS_MM = 3.45
KEEPER_SEAT_Z = -71.98
KEEPER_TOP_Z = -69.98
KEEPER_ANCHOR_Y = 61.
KEEPER_OPENING_RADIUS_MM = 1.90


def keeper_halves(x):
    stations = [y for u, y in HATCH_MOUNTS if u == x]
    lo, hi = min(stations), max(stations)
    thickness = KEEPER_TOP_Z - KEEPER_SEAT_Z
    side = [cylinder(KEEPER_PAD_RADIUS_MM, thickness, (x, y, KEEPER_SEAT_Z)) for y in stations]
    side.append(cylinder(KEEPER_ANCHOR_PAD_RADIUS_MM, thickness, (x, KEEPER_ANCHOR_Y, KEEPER_SEAT_Z)))
    width = KEEPER_WEB_HALF_WIDTH_MM
    bridge = box(x-width, x+width, lo, hi, KEEPER_SEAT_Z, KEEPER_TOP_Z)
    return check_solid(bridge.fuse(side).cut([
        cylinder(KEEPER_OPENING_RADIUS_MM, thickness+.20, (x, y, KEEPER_SEAT_Z-.10))
        for y in (*stations, KEEPER_ANCHOR_Y)
    ]).removeSplitter(), 'two-nut hatch keeper')


def cages(stock, tap_radius):
    additions = [cylinder(CAGE_RADIUS_MM, KEEPER_SEAT_Z-HATCH_NUT_SEAT+.20,
                          (x, y, HATCH_NUT_SEAT-.20)) for x, y in HATCH_MOUNTS]
    cuts = []
    for x, y in HATCH_MOUNTS:
        cuts.extend((
            hexagon(NUT_FLAT_MM, KEEPER_SEAT_Z-HATCH_NUT_SEAT+.10,
                    (x, y, HATCH_NUT_SEAT), _UP),
            cylinder(1.85, 2.55, (x, y, HATCH_NUT_SEAT-2.45)),
        ))
    for x in sorted({x for x, _ in HATCH_MOUNTS}):
        additions.append(cylinder(3.65, KEEPER_SEAT_Z+77.75, (x, KEEPER_ANCHOR_Y, -77.75)))
        cuts.append(cylinder(tap_radius, KEEPER_SEAT_Z+78.25, (x, KEEPER_ANCHOR_Y, -78.15)))

    return check_solid(stock.fuse(additions).cut(cuts).removeSplitter(), 'base with captive hatch nuts')


def apply(doc, prints=None):
    base = doc.Part000
    stock = detached_shape(base)
    replace(base, cages(stock, 1.55))
    if prints is not None:
        prints.mkdir(parents=True, exist_ok=True)
        print_mesh(cages(stock, 1.25), prints/'01_base_cup-hatch-capture.stl')

    parent = base.getParentGeoFeatureGroup()
    rows = []
    for side, x in zip(('Left', 'Right'), sorted({x for x, _ in HATCH_MOUNTS}), strict=True):
        name = 'ServiceHatchNutKeeper'+side
        shape = keeper_halves(x)
        add_part(doc, parent, name, 'bottom hatch two-nut keeper '+side.lower(), shape, 'fixed')
        seat = (x, KEEPER_ANCHOR_Y, KEEPER_TOP_Z)
        add_part(doc, parent, name+'Screw', 'M3 × 8 hatch keeper screw '+side.lower(),
                 socket_screw(3, 8., seat, _DOWN), 'fixed')
        rows.append({'keeper': name, 'screw': name+'Screw', 'seat_mm': seat, 'axis': _DOWN})
        if prints is not None and side == 'Right':
            print_mesh(shape, prints/'35_hatch_two_nut_keeper.stl')
    return rows


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--prints', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('Choose a separate output assembly')
    doc = App.openDocument(str(args.source.resolve()))
    try:
        hardware = apply(doc, args.prints)
        doc.recompute()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(args.output.resolve()))
        args.output.with_suffix('.json').write_text(json.dumps(hardware, indent=2)+'\n')
    finally:
        App.closeDocument(doc.Name)
