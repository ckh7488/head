"""Check the assembled yaw bolts and both possible XL430 ports in B15."""

from argparse import ArgumentParser
from pathlib import Path
import sys

import FreeCAD as App
from FreeCAD import Vector

from export_cad import world_shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from neck_joint import MAST_LENGTH, MOUNTS, STUD_BOLT_SEAT
from primitives import box
from stock import socket_screw


def yaw_clearance(motor, seat):
    overlap = 0.
    minimum = float('inf')
    worst_angle = 0
    for x, y in MOUNTS:
        bolt = socket_screw(3, MAST_LENGTH, (x, y, seat), (0, 0, 1))
        for angle in range(-60, 61, 3):
            posed = bolt.copy().rotate(Vector(), Vector(0, 0, 1), -angle)
            if posed.BoundBox.intersect(motor.BoundBox):
                volume = posed.common(motor).Volume
                if volume > overlap:
                    overlap, worst_angle = volume, angle
            minimum = min(minimum, posed.distToShape(motor)[0])
    return overlap, worst_angle, minimum


def check(cad, candidate_seat):
    doc = App.openDocument(str(cad.resolve()))
    try:
        motor = world_shape(doc.Part017)
        overlap, angle, gap = yaw_clearance(motor, STUD_BOLT_SEAT)
        print(f'Yaw studs at {STUD_BOLT_SEAT:.2f} mm: {overlap:.2f} mm³ at {angle:+d}°, minimum gap {gap:.2f} mm.', flush=True)
        if candidate_seat is not None:
            _, _, candidate_gap = yaw_clearance(motor, candidate_seat)
            print(f'Candidate seat at {candidate_seat:.2f} mm: {candidate_gap:.2f} mm to the motor.', flush=True)
        ports = (
            ('ID4 left', 'Part008', (-14.25, 14.1, -62.1), (5.2, 10., 4.)),
            ('ID4 right', 'Part009', (14.25, 14.1, -62.1), (5.2, 10., 4.)),
            ('ID5 front', 'Part011', (11.8, -14.25, 97.9), (4., 5.2, 10.)),
            ('ID5 rear', 'Part011', (11.8, 14.25, 97.9), (4., 5.2, 10.)),
        )
        blocked = overlap > .01
        for label, bracket, center, size in ports:
            probe = box(*(edge for c, d in zip(center, size, strict=True) for edge in (c - d / 2, c + d / 2)))
            volume = probe.common(world_shape(doc.getObject(bracket))).Volume
            blocked |= volume > .01
            print(f'{label}: {volume:.2f} mm³ between the JST plug envelope and the bracket.')
        return blocked
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('--candidate-seat', type=float)
    args = parser.parse_args()
    raise SystemExit(int(check(args.cad, args.candidate_seat)))
