"""Couple the neck horn to the steel shaft with a removable stock M3 screw."""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App

from build_b19_review_fixes import add_part, replace
from build_b21_fasteners import check_solid, detached_shape, screw_spec
from primitives import box, cylinder, print_mesh
from stock import socket_screw


SHAFT_INBOARD_X = 38.70
M3_FROM_INBOARD_MM = 7.20
D_FLAT_LENGTH_MM = 9.95
DRIVE_SCREW = 'PitchDriveScrew'
DRIVE_SEAT = (SHAFT_INBOARD_X+M3_FROM_INBOARD_MM, 0., 117.5)
UPPER_HORN_SEAT = (40.90, 0., 120.)
HEAD_BOLT_LENGTH = 8.
DRIVE_AXIS = (0., 0., -1.)
DRIVE_HOLE_MM = 3.10
DRIVE_PILOT_MM = 3.00
HEAD_POCKET_RADIUS_MM = 3.22
PRINT_NAME = '08_pitch_horn_to_8mm_clamp-B24.stl'


def holder(horn, screw_bore_mm):
    lateral = (1., 0., 0.)
    body = horn.fuse(cylinder(6.55, 4.25, (44.20, 0., 112.), lateral))
    d_bore = cylinder(4.12, 4.66, (44.04, 0., 112.), lateral).common(
        box(43.95, 48.96, -6., 6., 107., 115.08))
    head_passages = [cylinder(2.16, 8.0, (x, y, z), lateral) for x, y, z in (
        UPPER_HORN_SEAT, (41.2, 8., 112.), (41.2, -8., 112.), (41.2, 0., 104.))]
    return check_solid(body.cut([
        *head_passages,
        d_bore,
        cylinder(HEAD_POCKET_RADIUS_MM, 8., DRIVE_SEAT),
        cylinder(.5*screw_bore_mm, 5.5, DRIVE_SEAT, DRIVE_AXIS),
    ]).removeSplitter(), 'M3 neck-coupling holder')


def apply(doc, print_dir=None):
    shaft = detached_shape(doc.Part015)
    shaft = check_solid(shaft.cut([
        box(44.9, SHAFT_INBOARD_X+D_FLAT_LENGTH_MM, -6., 6., 115., 117.),
        cylinder(1.55, 8.2, (DRIVE_SEAT[0], 0., 115.1), DRIVE_AXIS),
    ]).removeSplitter(), 'M3 tapped steel drive shaft')
    horn = detached_shape(doc.Part016)
    finished = holder(horn, DRIVE_HOLE_MM)
    screw = socket_screw(3, HEAD_BOLT_LENGTH, DRIVE_SEAT, DRIVE_AXIS)
    if max(finished.common(shaft).Volume, finished.common(screw).Volume, shaft.common(screw).Volume) > 1e-7:
        raise ValueError('The neck coupling has overlapping stock at the installed position')
    replace(doc.Part015, shaft)
    replace(doc.Part016, finished)
    doc.Part015.Label = 'Right pitch shaft · Ø8 × 27.3, 9.95 D-flat and M3 radial tap'
    drive = add_part(doc, doc.Part016.getParentGeoFeatureGroup(), DRIVE_SCREW,
                     'M3×8 removable neck drive screw', screw, 'head')
    replace(drive, screw)

    if print_dir is not None:
        print_dir.mkdir(parents=True, exist_ok=True)
        print_mesh(holder(horn, DRIVE_PILOT_MM), print_dir/PRINT_NAME, 'x+')
        machining = shaft.copy().translate(App.Vector(-SHAFT_INBOARD_X, 0., -112.))
        machining.exportStep(str(print_dir/'pitch-drive-shaft-B24.step'))
    report = {
        'actor': DRIVE_SCREW, 'm3_size_mm': 3., 'm3_length_mm': HEAD_BOLT_LENGTH,
        'm3_seat_mm': DRIVE_SEAT, 'm3_axis': DRIVE_AXIS,
        'upper_horn_bolt': 'pitchHornBolt2', 'upper_horn_seat_mm': UPPER_HORN_SEAT,
        'shaft_diameter_mm': 8., 'shaft_length_mm': 27.30,
        'd_flat_depth_mm': 1., 'd_flat_length_from_motor_end_mm': D_FLAT_LENGTH_MM,
        'm3_from_motor_end_mm': M3_FROM_INBOARD_MM, 'shaft_m3_tap_drill_mm': 2.50,
        'original_frame_cross_hole_from_outer_end_mm': 5.50, 'original_frame_cross_hole_mm': 3.,
        'bore_pilot_mm': DRIVE_PILOT_MM, 'bore_finish_mm': DRIVE_HOLE_MM,
        'head_pocket_diameter_mm': 2.*HEAD_POCKET_RADIUS_MM,
        'hardware_spec': screw_spec(DRIVE_SCREW, DRIVE_SEAT, DRIVE_AXIS, 'head', ('Part015', 'Part016')),
    }
    motion = json.loads(doc.R5.MotionGeometry)
    motion['pitch_coupler'] = report
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)
    return report


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--prints', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('Choose a separate native assembly output')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    document = App.openDocument(str(args.source.resolve()))
    try:
        apply(document, args.prints)
        document.recompute()
        document.saveAs(str(args.output.resolve()))
    finally:
        App.closeDocument(document.Name)
