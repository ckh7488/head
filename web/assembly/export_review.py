"""Export fastener seats and insertion distances for the assembly walkthrough."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import sys

import FreeCAD as App

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'mechanical'))
sys.path.insert(0, str(ROOT / 'mechanical' / 'physics'))
from cable_assembly import check_paths
from base_stack import (
    CARRIER_BOLT_Z, CARRIER_MOUNTS, CARRIER_NUT_Z, KEEPER_ANGLES, KEEPER_BOLT_Z,
    KEEPER_NUT_Z, KEEPER_RADIUS, LID_BOLT_Z, LID_NUT_Z, LID_RADIUS,
    SEAT_BOLT_Z, SEAT_NUT_Z, SEAT_RADIUS, SUPPORT_ANGLES, center,
)
from fixtures import (
    CAP_BOLT_LENGTH, CAP_BOLT_SEAT_Z, CAP_BOLT_Y, CAP_BOLTS, CAP_NUT_FLOOR_Z,
    CAP_NUT_ROOF_Z, CAP_NUT_TRAVEL, CAP_NUT_WIDTH, CAP_TRAVEL, SADDLE_BOLT_TRAVEL,
    SADDLE_INNER_TRAVEL, SADDLE_MOUNTS, SADDLE_NUT_Y, SADDLE_TRAVEL, SADDLE_WASHER_Y,
)
from motor_seats import HEAD_SEATS
from service_hatch import HATCH_MOUNTS, HATCH_NUT_SEAT, HATCH_SCREW_SEAT, HUB_MOUNTS, HUB_NUT_SEAT, HUB_SCREW_SEAT
from neck_joint import (
    HORN, HORN_LENGTH, HORN_SEAT, MAST_LENGTH, MAST_SEAT, MOUNTS, NUT_ROOF,
    PITCH_HORN, PITCH_HORN_SEAT,
)
from outer_fit import CAMERA_TRAVEL, FRONT_TRAVEL, JAW_TRAVEL, ORBIT_TRAVEL
from stock import (
    BLINK_CLAMPS, BLINK_CLAMP_NUT_Z, BLINK_MOUNTS, BLINK_RAIL_LENGTH, BLINK_RAIL_NUT_Y, BLINK_RAIL_SEAT_Y,
)

V = App.Vector


def export(cad, output):
    doc = App.openDocument(str(cad.resolve()))
    result = {
        'cad_sha256': sha256(cad.read_bytes()).hexdigest(), 'stops': {},
        'service_hatch': {
            'base_centers': HATCH_MOUNTS, 'base_nut_seat': HATCH_NUT_SEAT, 'base_screw_seat': HATCH_SCREW_SEAT,
            'board_centers': HUB_MOUNTS, 'board_nut_seat': HUB_NUT_SEAT, 'board_screw_seat': HUB_SCREW_SEAT,
        },
        'motor_caps': {
            part: [[size, list(V(*face) - depth * V(*outward)), list(-V(*outward))]
                   for size, face, outward, depth in seats]
            for part, seats in HEAD_SEATS.items()
        },
        'cable_assembly': {
            'x': CAP_BOLTS, 'y': CAP_BOLT_Y, 'nut_floor': CAP_NUT_FLOOR_Z, 'nut_roof': CAP_NUT_ROOF_Z,
            'nut_width': CAP_NUT_WIDTH, 'nut_travel': CAP_NUT_TRAVEL,
            'bolt_seat': CAP_BOLT_SEAT_Z, 'bolt_length': CAP_BOLT_LENGTH, 'cover_travel': CAP_TRAVEL,
            'tray_mounts': SADDLE_MOUNTS, 'tray_travel': SADDLE_TRAVEL, 'tray_bolt_travel': SADDLE_BOLT_TRAVEL,
            'tray_washer_y': SADDLE_WASHER_Y, 'tray_nut_y': SADDLE_NUT_Y, 'tray_inner_travel': SADDLE_INNER_TRAVEL,
        },
    }
    result['neck'] = {
        'mast_mounts': MOUNTS, 'horn_mounts': HORN, 'mast_seat': MAST_SEAT,
        'horn_seat': HORN_SEAT, 'mast_length': MAST_LENGTH, 'horn_length': HORN_LENGTH, 'nut_roof': NUT_ROOF,
        'pitch_horn_mounts': PITCH_HORN, 'pitch_horn_seat': PITCH_HORN_SEAT,
    }
    result['blink_mounts'] = {
        'rail_xz': BLINK_MOUNTS, 'rail_screw_y': BLINK_RAIL_SEAT_Y, 'rail_nut_y': BLINK_RAIL_NUT_Y,
        'rail_length': BLINK_RAIL_LENGTH, 'crank_x': [x for x, _, _, _ in BLINK_CLAMPS],
        'crank_nut_z': BLINK_CLAMP_NUT_Z,
    }
    result['outer_loading'] = {'front': FRONT_TRAVEL, 'orbit': ORBIT_TRAVEL, 'camera': CAMERA_TRAVEL, 'jaw': JAW_TRAVEL}
    result['base_stack'] = {
        name: {'centers': [(*center(radius, angle), angle) for angle in angles],
               'nut_z': nut_z, 'bolt_z': bolt_z, 'length': length, 'nut_stroke': stroke}
        for name, radius, angles, nut_z, bolt_z, length, stroke in (
            ('seat', SEAT_RADIUS, SUPPORT_ANGLES, SEAT_NUT_Z, SEAT_BOLT_Z, 16., -12.),
            ('lid', LID_RADIUS, SUPPORT_ANGLES, LID_NUT_Z, LID_BOLT_Z, 8., -14.),
            ('keepers', KEEPER_RADIUS, KEEPER_ANGLES, KEEPER_NUT_Z, KEEPER_BOLT_Z, 8., 16.),
        )
    }
    result['base_stack']['carriers'] = {'centers': CARRIER_MOUNTS, 'nut_z': CARRIER_NUT_Z, 'bolt_z': CARRIER_BOLT_Z}
    try:
        check_paths(doc)
        output.mkdir(parents=True, exist_ok=True)
        (output / 'interference.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--cad', type=Path, default=ROOT / 'mechanical' / 'R5-B11-Assembly.FCStd')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    export(args.cad, args.output)
