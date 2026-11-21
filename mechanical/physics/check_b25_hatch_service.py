"""Check rigid plug service and identify the complementary hatch wire routing inputs."""

from argparse import ArgumentParser
from hashlib import sha256
from math import cos, radians, sin
import json
from pathlib import Path

import FreeCAD as App
import numpy as np

from build_b25_hatch_envelope import J2_INSTALLED_HEIGHT, J2_SPEC, j2_envelope
from check_b23_service import HATCH_DROPS
from export_cad import world_shape
from primitives import box, cylinder
from wiring_check import discrete_bend
from wiring_motion import arc_lengths, round_route


WIRING = Path(__file__).resolve().parents[2]/'web/assets/wiring.json'
DROP = 30.
XT30_TRAVEL = 25.
PH_EH_TRAVEL = 12.
RESERVE = .15
WIRE_NAMES = ('J2+', 'J2-', 'J3-G', 'J3-D', 'J7-return', 'J7-power', 'J7-data')
VOLUME_TOLERANCE = 1.e-5


def collision_volumes(envelope, targets, omitted=()):
    bounds = envelope.BoundBox
    return {name: volume for name, shape in targets.items()
            if name not in omitted and bounds.intersect(shape.BoundBox)
            and (volume := envelope.common(shape).Volume) > VOLUME_TOLERANCE}


def bounds_box(bounds, shift=(0., 0., 0.), travel_axis=2, travel=0., reserve=0.):
    low, high = np.asarray(bounds, dtype=float) + shift
    allowance = np.full(3, reserve)
    allowance[travel_axis] = 0.
    low -= allowance
    high += allowance
    low[travel_axis] += min(0., travel)
    high[travel_axis] += max(0., travel)
    return box(low[0], high[0], low[1], high[1], low[2], high[2])


def rigid_plug_checks(doc, wiring):
    moving_names = {obj.Name for obj in (*doc.HubInstalled.Group, *doc.HubCableSpace.Group)}
    moving_names.update(obj.Name for obj in doc.Objects if obj.Name.startswith('HubBolt'))
    shapes = {obj.Name: world_shape(obj) for obj in doc.Objects if obj.TypeId == 'Part::Feature'
              and not obj.Name.startswith(('HubRearClearance', 'HarnessWire'))}
    native_j2_height = shapes['HubBodyJ2'].BoundBox.ZLength
    shapes['HubBodyJ2'] = j2_envelope(doc)
    lowered = App.Vector(0., 0., -DROP)
    fixed = {name: shape for name, shape in shapes.items() if name not in moving_names}
    hatch = {name: shapes[name] for name in moving_names if name in shapes}
    after_lowering = {**fixed, **{name: shape.translated(lowered) for name, shape in hatch.items()}}
    plug = next(row for row in wiring['blocks'] if row['id'] == 'J1Mate')
    center, half = np.array(plug['center']), np.array(plug['size'])/2.
    xt30 = [center-half, center+half]
    service_plug = bounds_box(xt30, travel=-DROP, reserve=RESERVE)
    seated_plug = bounds_box(xt30)
    extraction = bounds_box(xt30, list(lowered), travel_axis=1, travel=XT30_TRAVEL, reserve=RESERVE)
    rows = {
        'J1': {'drop_mm': DROP, 'movement_mm': [0., XT30_TRAVEL, 0.],
               'moving_plug_size_mm': plug['size'],
               'lowering_intersections_mm3': collision_volumes(service_plug, fixed),
               'seated_hatch_intersections_mm3': collision_volumes(seated_plug, hatch),
               'withdrawal_intersections_mm3': collision_volumes(extraction, after_lowering)},
    }
    after_lowering['J1Mate'] = seated_plug.translated(lowered)
    terminals = {}
    rigid_tool_details = {}
    # The KiCad J2 F.Fab screw circles are concentric with pads 1/2.
    # The 70 x 35 PCB spans X=-35..35 and Y=42..77 in the native assembly.
    # PCB datums map X to x-135, and Y to 157-y.
    screw_y = 157.-87.50
    j2 = hatch['HubBodyJ2'].BoundBox
    terminal_lowering = bounds_box([(j2.XMin, j2.YMin, j2.ZMin), (j2.XMax, j2.YMax, j2.ZMax)],
                                   travel=-DROP, reserve=RESERVE)
    for pin, x in ((1, 150.30-135.), (2, 145.22-135.)):
        # The native component is a rectangular envelope. The blade starts above
        # it. The blade radius represents Phoenix's listed 3.5 mm flat blade.
        driver_start = (x, screw_y, j2.ZMax-DROP+.001)
        driver = cylinder(1.75, 40., driver_start)
        exit_start = (x, j2.YMax+.001, -67.4-DROP)
        lead_exit = cylinder(2.057/2.+RESERVE, 10., exit_start, (0., 1., 0.))
        catalog_driver = cylinder(1.75, 100., driver_start)
        handle = cylinder(6., 90., (x, screw_y, j2.ZMax-DROP+40.))
        # A conventional inline handle hits the base. An L-shaped bare shaft
        # can reach the same screwdriver axis from the lower rear opening.
        jog_z = j2.ZMax-DROP+5.5
        horizontal_arm = {str(angle): collision_volumes(
            cylinder(1.7, 55., (x, screw_y, jog_z), (sin(radians(angle)), cos(radians(angle)), 0.)),
            after_lowering) for angle in (-15., 0., 15.)}
        offset_shaft_entry = box(x-1.7, x+1.7, screw_y-1.7, screw_y+55.0, driver_start[2]+1.3, jog_z+2.7)
        rigid_tool_details[str(pin)] = {
                                        'catalog_3_5_mm_blade_100_mm_shaft_blockers_mm3': collision_volumes(
                                            catalog_driver, after_lowering),
                                        'short_inline_handle_blockers_mm3': collision_volumes(handle, after_lowering),
                                        'offset_axis_z_mm': jog_z,
                                        'offset_arm_rotation_blockers_mm3': horizontal_arm,
                                        'offset_route_entry_blockers_mm3': collision_volumes(
                                            offset_shaft_entry, after_lowering)}
        terminals[str(pin)] = {'screw_axis_mm': list(driver_start), 'straight_blade_reach_mm': 40.,
                               'terminal_lead_exit_travel_mm': 10.,
                               'driver_intersections_mm3': collision_volumes(driver, after_lowering),
                               'lead_exit_intersections_mm3': collision_volumes(lead_exit, after_lowering)}
    for index in range(3, 9):
        name = f'HubPlugJ{index}'
        bound = shapes[name].BoundBox
        bounds = [(bound.XMin, bound.YMin, bound.ZMin), (bound.XMax, bound.YMax, bound.ZMax)]
        path = bounds_box(bounds, list(lowered), travel=PH_EH_TRAVEL, reserve=RESERVE)
        rows[f'J{index}'] = {'drop_mm': DROP, 'movement_mm': [0., 0., PH_EH_TRAVEL],
                            'withdrawal_intersections_mm3': collision_volumes(
                                path, after_lowering, (name, f'HubBodyJ{index}'))}
    incompatible = [name for name, row in {**rows, **terminals}.items()
                    if any(value for key, value in row.items() if key.endswith('intersections_mm3'))]
    terminal_lowering_hits = collision_volumes(terminal_lowering, fixed)
    return {'status': 'fail' if incompatible or terminal_lowering_hits else 'pass',
            'orthogonal_envelope_reserve_mm': RESERVE,
            'plugs': rows, 'j2_terminal_opening': terminals, 'j2_tool_body_candidates': rigid_tool_details,
            'j2_service_envelope': {'native_height_mm': native_j2_height,
                                    'datasheet_installed_height_mm': J2_INSTALLED_HEIGHT,
                                    'datasheet': J2_SPEC,
                                    'lowering_intersections_mm3': terminal_lowering_hits}}


def unresolved_wires(wiring, paths):
    routes = {route['id']: route for route in wiring['routes']}
    hatch_motion = np.eye(4)
    hatch_motion[2, 3] = -DROP
    installed = dict(fixed=np.eye(4), hatch=np.eye(4))
    lowered = dict(fixed=np.eye(4), hatch=hatch_motion)
    archives = {}
    for drop in HATCH_DROPS:
        with np.load(paths/f'wires-0-0-0-{drop}.npz') as archive:
            archives[drop] = set(archive.files)
    # The drawing polylines are useful as a diagnostic. Simply lowering their
    # tagged endpoints changes their lengths and can produce tight bends.
    rows = {}
    for name in WIRE_NAMES:
        route = routes[name]
        points = (round_route(route, installed), round_route(route, lowered))
        rows[name] = {
            'missing_from_B23_archive_drops_mm': [drop for drop, names in archives.items() if name not in names],
            'nominal_closed_length_mm': float(arc_lengths(points[0])[-1]),
            'nominal_lowered_length_mm': float(arc_lengths(points[1])[-1]),
            'nominal_closed_minimum_bend_radius_mm': discrete_bend(points[0])[0],
            'nominal_lowered_minimum_bend_radius_mm': discrete_bend(points[1])[0],
            'minimum_bend_radius_target_mm': 5.*route['diameter'],
        }
    return rows


def check(source, wiring_path, paths):
    raw_wiring = wiring_path.read_bytes()
    wiring = json.loads(raw_wiring)
    doc = App.openDocument(str(source.resolve()))
    try:
        rigid = rigid_plug_checks(doc, wiring)
    finally:
        App.closeDocument(doc.Name)
    return {'status': 'blocked' if rigid['status'] == 'pass' else 'fail',
            'cad_sha256': sha256(source.read_bytes()).hexdigest(),
            'wiring_definition_sha256': sha256(raw_wiring).hexdigest(),
            'rigid_plug_paths': rigid,
            'unresolved_conductors': unresolved_wires(wiring, paths),
            'remaining_checks': ['Length-constrained routes for all seven conductors throughout supported lowering',
                                 'J2 tool-body approach, tightening and hand support at the specified 0.5–0.6 N·m',
                                 'Physical plug grip, tool clearance, and strain relief with the real harness']}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('wires', type=Path, help='Directory of the released B23 hatch wire centerlines')
    parser.add_argument('output', type=Path)
    parser.add_argument('--wiring', type=Path, default=WIRING)
    args = parser.parse_args()
    report = check(args.cad, args.wiring, args.wires)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    raise SystemExit(report['status'] != 'pass')
