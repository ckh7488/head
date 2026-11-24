"""Check the sixteen B25 XL330 case screw seats against the native FreeCAD assembly."""

from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from math import cos, pi, sin
from pathlib import Path

import FreeCAD as App
import Part

from export_cad import world_mesh, world_shape


MOUNTS = (
    ('eyeYawHead', 'Part038', 'Part039', (8, 6, 8, 8)),
    ('eyePitchHead', 'Part041', 'Part042', (8, 8, 8, 8)),
    ('blinkMotorHead', 'Part045', 'Part046', (6, 8, 6, 8)),
    ('jawMotorHead', 'Jaw_XL330_M288_Jaw', 'Jaw_36_left_jaw_servo_stay', (6, 8, 8, 6)),
)
EPS = .001
HEAD_DIAMETER = 4.
HEAD_HEIGHT = 2.
DRIVER_DIAMETER = 3.
DRIVER_LENGTH = 30.


def station_value(value):
    return round(value, 4) + 0.0


def mount_plate(obj):
    if hasattr(obj, 'Shape'):
        return world_shape(obj)
    # The jaw stay is stored as a closed mesh in the native assembly.
    shape = Part.Shape()
    shape.makeShapeFromMesh(world_mesh(obj).Topology, EPS)
    if len(shape.Shells) != 1 or not shape.Shells[0].isClosed():
        raise ValueError(f'{obj.Name}: expected one closed mounting-plate shell')
    return Part.makeSolid(shape.Shells[0])


def coaxial_bores(host, seat, axis):
    spans = set()
    for face in host.Faces:
        surface = face.Surface
        if not isinstance(surface, Part.Cylinder):
            continue
        if (surface.Center - seat).cross(axis).Length > EPS or abs(abs(surface.Axis.dot(axis)) - 1.) > EPS:
            continue
        limits = [(vertex.Point - seat).dot(axis) for vertex in face.Vertexes]
        spans.add((station_value(2 * surface.Radius), station_value(min(limits)), station_value(max(limits))))
    return sorted(spans, key=lambda row: row[1])


def obstructed_volume(gauge, bodies):
    return sum(body.common(gauge).Volume for body in bodies if gauge.BoundBox.intersect(body.BoundBox))


def seat_samples(plate, seat, axis, stack):
    side = axis.cross(App.Vector(0, 1, 0))
    side.normalize()
    across = axis.cross(side)
    support = 0
    plate_stack = 0.
    for i in range(8):
        radial = side * cos(i * pi / 4) + across * sin(i * pi / 4)
        for radius in (1.30, 1.70, 1.90):
            point = seat + radial * radius
            if plate.isInside(point + axis * .03, EPS, False):
                support += 1
                if abs(plate_stack - stack) > EPS:
                    ray = Part.makeLine(point - axis * .05, point + axis * (stack + .05))
                    plate_stack = max(plate_stack, sum(edge.Length for edge in plate.common(ray).Edges))
    return support, station_value(plate_stack)


def station(row, length, motor, plate):
    seat, axis = App.Vector(*row['seat']), App.Vector(*row['axis'])
    if abs(axis.Length - 1.) > EPS:
        raise ValueError(f'{row["id"]}: expected a unit screw axis')
    bores = coaxial_bores(motor, seat, axis)
    if len(bores) != 3:
        raise ValueError(f'{row["id"]}: expected an entrance, pilot, and exit')
    (entry_diameter, stack, pilot_start), (pilot_diameter, start, end), (exit_diameter, exit_start, case_exit) = bores
    bore_matches_detail_a = (
        (entry_diameter, pilot_diameter, exit_diameter) == (2., 1.6, 2.)
        and abs(pilot_start - stack - 3.5) <= EPS
        and pilot_start == start and end == exit_start
    )
    centerline = Part.makeLine(seat, seat + axis * (case_exit + .1))
    axis_clear = not motor.common(centerline).Edges
    tip_reach = station_value(length - start)
    support_samples, plate_stack = seat_samples(plate, seat, axis, stack)
    head_travel = length + HEAD_HEIGHT
    head = Part.makeCylinder(HEAD_DIAMETER / 2, head_travel, seat - axis * (head_travel + EPS), axis)
    driver = Part.makeCylinder(DRIVER_DIAMETER / 2, DRIVER_LENGTH, seat - axis * (DRIVER_LENGTH + EPS), axis)
    shank = Part.makeCylinder(1., start - EPS, seat, axis)
    overlaps = {
        'head_insertion_mm3': obstructed_volume(head, (plate, motor)),
        'driver_approach_mm3': obstructed_volume(driver, (plate, motor)),
        'shank_before_pilot_mm3': obstructed_volume(shank, (plate, motor)),
    }
    geometry_passes = (
        bore_matches_detail_a and axis_clear and 0 < tip_reach < end - start
        and support_samples > 0 and abs(plate_stack - stack) <= EPS
        and all(overlap <= EPS for overlap in overlaps.values())
    )
    return {
        'seat_mm': row['seat'], 'axis': row['axis'], 'oem_tapping_screw_length_mm': length,
        'printed_stack_mm': stack, 'measured_print_stack_mm': plate_stack,
        'case_entry_diameter_mm': entry_diameter, 'case_entry_length_mm': station_value(pilot_start - stack),
        'pilot_diameter_mm': pilot_diameter, 'pilot_length_mm': station_value(end - start),
        'original_m2x6_tip_reach_mm': station_value(6. - start),
        'pilot_start_mm': start, 'pilot_end_mm': end, 'case_exit_mm': case_exit,
        'nominal_tip_reach_into_pilot_mm': tip_reach, 'tip_to_end_of_pilot_mm': station_value(end - length),
        'case_centerline_open': axis_clear, 'head_seat_support_samples_of_24': support_samples,
        'bench_overlaps': {name: station_value(volume) for name, volume in overlaps.items()},
        'geometry_passes': geometry_passes,
    }


def check(cad, hardware):
    rows = {row['id']: row for row in json.loads(hardware.read_text(encoding='utf-8'))['hardware']}
    doc = App.openDocument(str(cad))
    try:
        seats = {}
        for prefix, motor_name, plate_name, lengths in MOUNTS:
            motor = world_shape(doc.getObject(motor_name))
            plate = mount_plate(doc.getObject(plate_name))
            for index, length in enumerate(lengths):
                name = f'{prefix}{index}'
                row = rows[name]
                if row['type'] != 'head' or row['size'] != 2:
                    raise ValueError(f'{name}: expected an M2 head in the seat manifest')
                seats[name] = {'motor': motor_name, 'plate': plate_name, **station(row, length, motor, plate)}
    finally:
        App.closeDocument(doc.Name)
    counts = Counter(row['oem_tapping_screw_length_mm'] for row in seats.values())
    return {
        'cad_sha256': sha256(cad.read_bytes()).hexdigest(),
        'seat_manifest_sha256': sha256(hardware.read_bytes()).hexdigest(),
        'geometry_passes': all(row['geometry_passes'] for row in seats.values()),
        'oem_phs_m2_tap_counts': {f'x{length}': count for length, count in sorted(counts.items())},
        'bench_gauge_mm': {
            'head_diameter': HEAD_DIAMETER, 'head_height': HEAD_HEIGHT,
            'driver_shaft_diameter': DRIVER_DIAMETER, 'driver_axial_path': DRIVER_LENGTH,
        },
        'as_built_thread_form_and_clamp': 'pending', 'seats': seats,
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('seat_manifest', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = check(args.cad, args.seat_manifest)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result['geometry_passes'] else 1)
