"""Check the recessed yaw bolts and installed neck JST connections."""

from argparse import ArgumentParser
from itertools import product
from pathlib import Path
import sys

import FreeCAD as App
from FreeCAD import Vector

from export_cad import world_shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor_ports import EHR_HEIGHT, EHR_LENGTH, EHR_PORTS, EHR_WIDTH
from neck_joint import MAST_LENGTH, MOUNTS, ROTOR_TOP, STUD_BOLT_SEAT
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


def socket_envelope(name, allowance=.20):
    _, terminal, row, pull = EHR_PORTS[name]
    center = Vector(*terminal) - Vector(*pull) * EHR_LENGTH / 2
    thickness = EHR_HEIGHT + .64
    half_extents = [
        (abs(a) * EHR_WIDTH + abs(b) * EHR_LENGTH + (not (a or b)) * thickness) / 2 + allowance
        for a, b in zip(row, pull, strict=True)
    ]
    return box(*(edge for c, half in zip(center, half_extents, strict=True) for edge in (c-half, c+half)))


def port_clearance(doc):
    blocked = False
    passages = {
        'ID4EH': ('Part008', 'Part000', 'Part001'),
        'ID5EH': ('Part011', 'Part010', 'Part019'),
        'ID1EH': ('Part024', 'Part039'),
    }
    for name, obstacles in passages.items():
        probe = socket_envelope(name)
        direction = Vector(*EHR_PORTS[name][3])
        shapes = [world_shape(doc.getObject(n)) for n in obstacles]
        maximum = max(probe.translated(direction * (i / 2)).common(shape).Volume
                      for i in range(25) for shape in shapes)
        print(f'{name}: 12 mm plug travel, worst overlap {maximum:.3f} mm³.', flush=True)
        blocked |= maximum > .01

    probe = socket_envelope('ID1EH')
    obstacles = {n: world_shape(doc.getObject(n)) for n in ('Part011', 'Part018')}
    minimum, overlap = float('inf'), 0.
    for neck, eye in product(range(-15, 7, 3), range(-8, 9, 2)):
        moved = probe.copy().rotate(Vector(0, -39, 119), Vector(1, 0, 0), eye)
        moved.rotate(Vector(0, 0, 112), Vector(1, 0, 0), neck)
        for shape in obstacles.values():
            gap = moved.distToShape(shape)[0]
            minimum = min(gap, minimum)
            if gap < .01:
                overlap = max(overlap, moved.common(shape).Volume)
    print(f'ID1EH: 72 neck and eye poses, gap {minimum:.2f} mm, overlap {overlap:.3f} mm³.', flush=True)
    return blocked or overlap > .01


def check(cad, candidate_seat):
    doc = App.openDocument(str(cad.resolve()))
    try:
        motor = world_shape(doc.Part017)
        overlap, angle, gap = yaw_clearance(motor, STUD_BOLT_SEAT)
        print(f'Yaw studs at {STUD_BOLT_SEAT:.2f} mm: {overlap:.2f} mm³ at {angle:+d}°, minimum gap {gap:.2f} mm.', flush=True)
        if candidate_seat is not None:
            _, _, candidate_gap = yaw_clearance(motor, candidate_seat)
            print(f'Candidate seat at {candidate_seat:.2f} mm: {candidate_gap:.2f} mm to the motor.', flush=True)
        rotor = world_shape(doc.Part007)
        rotor_overlap = max(socket_screw(3, MAST_LENGTH, (x, y, STUD_BOLT_SEAT), (0, 0, 1)).common(rotor).Volume
                            for x, y in MOUNTS)
        print(f'Rotor: {ROTOR_TOP-STUD_BOLT_SEAT:.2f} mm under the seating face, screw overlap {rotor_overlap:.3f} mm³.', flush=True)
        ports_blocked = port_clearance(doc)
        return overlap > .01 or rotor_overlap > .01 or ports_blocked
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('--candidate-seat', type=float)
    args = parser.parse_args()
    raise SystemExit(int(check(args.cad, args.candidate_seat)))
