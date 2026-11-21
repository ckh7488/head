"""Seat the yaw shoulder on a stock PET shim and align ID4 on that datum."""

from argparse import ArgumentParser
import json
from math import cos, radians, sin
from pathlib import Path

import FreeCAD as App
from build_b19_review_fixes import add_part, replace
from build_b21_fasteners import check_solid
from export_cad import world_shape
from primitives import box, cylinder, print_mesh

SHIM_ID = 80.10
SHIM_OD = 84.50
SHIM_THICKNESS = .10
SHIM_Z = -38.
SLOT_HALF_TRAVEL = .35
SLOT_RADIUS = 1.55
TOOL_RADIUS = 1.18
PORT_RADIUS = 1.75
REAR_PORT_DEG = 10.
DRIVER_REACH = 91.
SCREW_Z = -50.9
SCREW_ROWS = (4., 28.)
BRACKETS = ('Part008', 'Part009')


def slot_tools(side):
    x = -18.57 if side == -1 else 14.20
    x_end = -14.20 if side == -1 else 18.57
    slots = []
    for y in SCREW_ROWS:
        z0, z1 = SCREW_Z-SLOT_HALF_TRAVEL, SCREW_Z+SLOT_HALF_TRAVEL
        slots.append(box(x, x_end, y-SLOT_RADIUS, y+SLOT_RADIUS, z0, z1).fuse(
            [cylinder(SLOT_RADIUS, x_end-x, (x, y, z), (1, 0, 0)) for z in (z0, z1)]))
    return slots


def side_driver_axes():
    for side in (-1, 1):
        for y in SCREW_ROWS:
            angle = radians(REAR_PORT_DEG if y > 10. else 0.)
            yield side, y, App.Vector(side*cos(angle), -sin(angle), 0.)


def with_driver_ports(cup):
    ports = []
    for side, y, direction in side_driver_axes():
        # Overlapping bores leave clearance at both ends of the motor adjustment.
        # The angled rear ports start outside the bearing pylons.
        start = App.Vector(side*18.55, y, SCREW_Z) + 60.*direction
        for dz in (-SLOT_HALF_TRAVEL, 0., SLOT_HALF_TRAVEL):
            ports.append(cylinder(PORT_RADIUS, 28., tuple(start + App.Vector(0, 0, dz)), tuple(direction)))
    return check_solid(cup.cut(ports).removeSplitter(), 'base with 2 mm ball driver access')


def verify_access(doc, original_cup, cup):
    seat = world_shape(doc.Part001)
    bearing = world_shape(doc.Part006)
    motor = world_shape(doc.Part017)
    fixed = {n: world_shape(doc.getObject(n))
             for n in ('Part001', 'Part002', 'Part006', 'Part069', 'Part070', 'Part071', 'Part072')}
    positions = (-SLOT_HALF_TRAVEL, 0., SLOT_HALF_TRAVEL)
    pylon_gauge = cylinder(75., 44., (0., 0., -83.))
    pylon_volume = original_cup.common(pylon_gauge).Volume - cup.common(pylon_gauge).Volume
    if abs(pylon_volume) > 1e-5:
        raise ValueError('Driver ports removed material in the base support region')
    checks = []
    for side, y, direction in side_driver_axes():
        bracket = world_shape(doc.Part008 if side == -1 else doc.Part009)
        neighboring = dict(fixed, Part000=cup)
        # The stock M2.5 socket entry is at x=21.05. The black-box tool
        # shank begins beyond that face. A 2 mm hex key has 2.31 mm corners.
        for dz in positions:
            point = App.Vector(side*18.55, y, SCREW_Z+dz)
            outside = point + direction * (2.50 / abs(direction.x) + .025)
            rod = cylinder(TOOL_RADIUS, DRIVER_REACH, tuple(outside), tuple(direction))
            gaps = {k: rod.distToShape(shape)[0] for k, shape in neighboring.items()}
            if min(gaps.values()) < .20:
                raise ValueError(f'Ball driver route reaches {min(gaps, key=gaps.get)} at {side}, {y}, {dz}: {gaps}')
            shank_start = App.Vector(side*18.59, y, SCREW_Z+dz)
            shank = cylinder(1.25, 4.39, tuple(shank_start), (-side, 0., 0.))
            if shank.common(bracket).Volume > 1e-5:
                raise ValueError('OEM screw shank blocked during adjustment')
            checks.append({'side': side, 'y_mm': y, 'z_adjustment_mm': dz,
                           'seat_mm': list(outside), 'outward': list(direction), 'radius_mm': TOOL_RADIUS,
                           'minimum_driver_gap_mm': min(gaps.values()), 'nearest_actor': min(gaps, key=gaps.get)})
    for dz in positions:
        moved = motor.copy().translate(App.Vector(0, 0, dz))
        for part in (cup, world_shape(doc.Part008), world_shape(doc.Part009)):
            if moved.common(part).Volume > 1e-6:
                raise ValueError('ID4 cannot move to the edge of its adjustment slots')
    shim = world_shape(doc.YawInnerRaceShim)
    rotor = world_shape(doc.Part007)
    for n in (4., 1.5, .35):
        raised_shim = shim.copy().translate(App.Vector(0., 0., n))
        if raised_shim.common(seat).Volume > 1e-7 or raised_shim.common(bearing).Volume > 1e-7:
            raise ValueError('The PET shim cannot be lowered to the inner ring')
    for shift in (0., .1, .22):
        shifted = shim.copy().translate(App.Vector(shift, 0., 0.))
        if shifted.distToShape(rotor)[0] > 1e-6 or shifted.common(rotor).Volume > 1e-6:
            raise ValueError('A radial shim shift can foul the rotor')
    return {'tool_rows': checks, 'base_removed_mm3': original_cup.Volume-cup.Volume,
            'removed_inside_r75_mm3': pylon_volume, 'straight_tool_free_length_mm': DRIVER_REACH}


def apply(doc, prints=None, *, export_base=False):
    rotor = world_shape(doc.Part007)
    bearing = world_shape(doc.Part006)
    shim = cylinder(SHIM_OD/2., SHIM_THICKNESS, (0., 0., SHIM_Z)).cut(
        cylinder(SHIM_ID/2., SHIM_THICKNESS, (0., 0., SHIM_Z)))
    if rotor.distToShape(shim)[0] > 1e-6 or bearing.distToShape(shim)[0] > 1e-6:
        raise ValueError('Yaw shim misses a load-bearing face')
    if rotor.common(shim).Volume > 1e-6 or bearing.common(shim).Volume > 1e-6:
        raise ValueError('Yaw shim intersects its mating solids')
    obj = add_part(doc, doc.Part007.getParentGeoFeatureGroup(), 'YawInnerRaceShim',
                   'K5 PET shim · Ø80.10–84.50 × 0.10', shim, 'pan')
    # Do not apply a steel density to the hand-cut PET ring in the mass model.
    obj.addProperty('App::PropertyFloat', 'EstimatedGrams', 'Hardware')
    obj.EstimatedGrams = shim.Volume * .00138

    slots = {}
    for i, name in enumerate(BRACKETS, 1):
        obj = doc.getObject(name)
        side = 2*i-3
        original = world_shape(obj)
        slotted = check_solid(original.cut(slot_tools(side)).removeSplitter(), name + ' yaw adjustment')
        replace(obj, slotted)
        slots[name] = original.Volume - slotted.Volume
        if prints is not None:
            prints.mkdir(parents=True, exist_ok=True)
            print_mesh(slotted, prints/f'05_yaw_servo_jaw_{i}-B23.stl')

    report = {
        'actor': 'YawInnerRaceShim', 'id_mm': SHIM_ID, 'od_mm': SHIM_OD,
        'thickness_mm': SHIM_THICKNESS, 'z_mm': SHIM_Z,
        'shim_insert_offset_mm': [0., 0., 12.],
        'stock': 'K5 · cut one continuous 0.1 mm PET annulus',
        'motor_slot_travel_mm': [-SLOT_HALF_TRAVEL, SLOT_HALF_TRAVEL],
        'removed_bracket_mm3': slots,
    }
    original_cup = world_shape(doc.Part000)
    cup = with_driver_ports(original_cup)
    replace(doc.Part000, cup)
    if export_base and prints is not None:
        print_mesh(cup, prints/'01_base_cup-yaw-access.stl')
    report['driver_access'] = verify_access(doc, original_cup, cup)
    motion = json.loads(doc.R5.MotionGeometry)
    motion['yaw_inner_race_shim'] = report
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)
    return report


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
        evidence = apply(doc, args.prints, export_base=True)
        doc.recompute()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(args.output.resolve()))
        args.output.with_suffix('.json').write_text(json.dumps(evidence, indent=2)+'\n')
    finally:
        App.closeDocument(doc.Name)
