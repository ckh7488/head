"""Retain the five rear-cover nuts during upright service with the ordinary M3 stack."""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App

from build_b19_review_fixes import replace
from build_b21_fasteners import check_solid, detached_shape
from fixtures import CAP_BOLT_LENGTH, CAP_BOLT_SEAT_Z, CAP_BOLT_Y, CAP_BOLTS
from primitives import box, cylinder, print_mesh
from stock import hexagon


NUT_FLOOR_Z = -68.30
NUT_RIM_Z = -66.90
NUT_POCKET_AF = 6.22
COVER_SEAT_DEPTH = 3.


def geometry(guide, cover):
    pockets = []
    seats = []
    for x in CAP_BOLTS:
        body = box(x - 4.62, x + 4.62, 114.4, CAP_BOLT_Y + 4.92, NUT_FLOOR_Z - 1.70, NUT_RIM_Z)
        parking = hexagon(NUT_POCKET_AF, NUT_RIM_Z - NUT_FLOOR_Z + .20, (x, CAP_BOLT_Y, NUT_FLOOR_Z))
        screw_tip = cylinder(1.85, 3., (x, CAP_BOLT_Y, NUT_FLOOR_Z - 1.85))
        pockets.append(body.cut([parking, screw_tip]))
        seats.append(cylinder(3.20, COVER_SEAT_DEPTH + .13, (x, CAP_BOLT_Y, CAP_BOLT_SEAT_Z - COVER_SEAT_DEPTH)))
    return (check_solid(guide.fuse(pockets), 'rear guide with nut pockets'),
            check_solid(cover.cut(seats), 'rear cover with socket-head seats'))


def apply(doc, print_dir):
    guide, cover = geometry(detached_shape(doc.CableSaddle), detached_shape(doc.CableGate))
    replace(doc.CableSaddle, guide)
    replace(doc.CableGate, cover)
    motion = json.loads(doc.R5.MotionGeometry)
    motion['rear_cable_service_nuts'] = {
        'bolt_seats_mm': [[x, CAP_BOLT_Y, CAP_BOLT_SEAT_Z - COVER_SEAT_DEPTH] for x in CAP_BOLTS],
        'bolt_length_mm': CAP_BOLT_LENGTH,
        'parked_bottom_z_mm': NUT_FLOOR_Z,
        'parking_rim_z_mm': NUT_RIM_Z,
        'parking_pocket_across_flats_mm': NUT_POCKET_AF,
        'service_orientation': 'upright',
    }
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)
    print_dir.mkdir(parents=True, exist_ok=True)
    print_mesh(guide, print_dir / '40-rear-cable-guide-service.stl')
    print_mesh(cover, print_dir / '42-rear-cable-cover-service.stl', 'z-')


def build(source, output, print_dir):
    if source.resolve() == output.resolve():
        raise ValueError('Write to a separate assembly from the source')
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = App.openDocument(str(source.resolve()))
    try:
        apply(doc, print_dir)
        doc.recompute()
        doc.saveAs(str(output.resolve()))
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'print_dir'):
        parser.add_argument(name, type=Path)
    build(**vars(parser.parse_args()))
