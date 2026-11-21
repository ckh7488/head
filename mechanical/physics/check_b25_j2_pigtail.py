"""Check an alternate B25 XT60 key orientation and two full-length hatch pigtails."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from math import atan2, ceil, cos, sin
from pathlib import Path
import sys

import FreeCAD as App
import numpy as np
import Part
from scipy.optimize import brentq

from check_b23_service import HATCH_DROPS
from check_b25_j2_disconnect import (
    AXIS_Y, BEND_RADIUS, DROP, PARK, PLUG_DRAWING, WITHDRAW, WIRE_RADIUS, WIRE_RESERVE,
    X, Y, Z, collision_volumes, evaluate, local_lead_edges,
)
from export_cad import world_shape
from primitives import box, cylinder


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from electronics.harness import J2_SERVICE_WIRE, POWER_WIRE


ARCHIVES = ROOT / 'mechanical/revisions/b23/hatch-paths'
WIRING = ROOT / 'web/assets/wiring.json'
CUT_LENGTHS = ROOT / 'mechanical/revisions/b20/physics/harness-cut-lengths.json'
WIRE_DATASHEETS = {
    POWER_WIRE.part: 'https://www.alphawire.com/en/products/wire/hook-up-wire/premium/3055.aspx',
    J2_SERVICE_WIRE.part: 'https://www.alphawire.com/products/wire/ecogen/ecowire/6715',
}
J2_STRANDED_RANGE_MM2 = (.14, 1.5)
NECK_LOAD_A = 2.80
LEADS = {'J2+': (15.30, X+3.60), 'J2-': (10.22, X-3.60)}
TAIL_REACH = 17.2
TAIL_STRAIGHT = 5.
TAIL_INSULATION_RADIUS = 2.
SOCKET_REAR_OFFSET = 6.
FREE_LENGTH = 140.
SPLIT_FRACTION = .30
FIXTURE_CLEARANCE = 90.
POSE_STEP = 2.
SWEEP_PANEL_LENGTH = .5
V = App.Vector


def s_turn_geometry(start, end):
    """Two opposed circular arcs with +Y tangent at both ends."""
    delta = end-start
    run = delta[1]
    delta[1] = 0.
    offset = np.linalg.norm(delta)
    if run <= 0. or offset <= 0.:
        raise ValueError('S-turn requires positive axial run and nonzero transverse offset')
    angle = 2.*atan2(offset, run)
    radius = (run**2+offset**2)/(4.*offset)
    return radius, angle, delta/offset


def s_turn_edges(start, end):
    radius, angle, transverse = s_turn_geometry(start, end)

    def from_start(t):
        return radius*(sin(t)*np.array(AXIS_Y)+(1.-cos(t))*transverse)

    middle = start+from_start(angle)
    edges = [
        Part.Arc(V(*start), V(*(start+from_start(angle/2.))), V(*middle)).toShape(),
        Part.Arc(V(*middle), V(*(end-from_start(angle/2.))), V(*end)).toShape(),
    ]
    return edges, radius


def lead_route(x_board, x_plug, terminal_y, withdrawal, parking, drop):
    """Solve the common lower tangent's depth for an inextensible service loop."""
    near_edges = local_lead_edges(x_board, terminal_y)
    near_edges = [edge.translated(V(0., 0., -drop)) for edge in near_edges]
    start = np.array([x_board, 100., Z-drop])
    tail = np.array([x_plug, Y+SOCKET_REAR_OFFSET-TAIL_REACH-withdrawal, Z-parking-drop])
    finish = tail-TAIL_STRAIGHT*np.array(AXIS_Y)
    tangent_y = start[1] + SPLIT_FRACTION*(finish[1]-start[1])

    def at_depth(z):
        return np.array([x_board, tangent_y, z])

    def residual(z):
        bend_origin = at_depth(z)
        turns = (s_turn_geometry(start, bend_origin), s_turn_geometry(bend_origin, finish))
        return sum(2.*radius*angle for radius, angle, _ in turns)-FREE_LENGTH

    depth = brentq(residual, finish[2]-FREE_LENGTH, finish[2]-.001, xtol=1.e-10)
    midpoint = at_depth(depth)
    down, down_radius = s_turn_edges(start, midpoint)
    up, up_radius = s_turn_edges(midpoint, finish)
    tail_edge = Part.makeLine(V(*finish), V(*tail))
    return near_edges+down+up+[tail_edge], min(BEND_RADIUS, down_radius, up_radius), tail


def tube(edges, radius):
    path = Part.Wire(edges)
    profile = Part.Wire([Part.makeCircle(radius, edges[0].Vertexes[0].Point, V(*AXIS_Y))])
    result = path.makePipeShell([profile], True, False)
    if not result.isValid() or len(result.Solids) != 1:
        raise ValueError('Expected one valid, reserved cable solid')
    return result


def cable_ids():
    lengths = json.loads(CUT_LENGTHS.read_text())
    routes = json.loads(WIRING.read_text())['routes']
    diameters = {row['id']: row['diameter'] for row in routes}
    diameters.update({'fuse-in': 1.143})
    required = {name for name in lengths if name.startswith('motor')}
    required.update(('J1+', 'J1-', 'J6-branch', 'fuse-in'))
    return {name: diameters[name] for name in required}


def archive_neighbors(path, diameters, conductors):
    """Compare the full J2 tube to the 19 B23 hatch wire centerlines at a shared pose."""
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != set(diameters) or len(diameters) != 19:
            raise ValueError(f'Expected all 19 B23 wire routes in {path}')
        overlaps = []
        for name, diameter in sorted(diameters.items()):
            points = archive[name]
            if points.ndim != 2 or points.shape[1] != 3 or len(points) < 2 or not np.isfinite(points).all():
                raise ValueError(f'Invalid {name} in {path}')
            reserve = diameter/2.+WIRE_RESERVE
            lower = points.min(axis=0)-reserve
            upper = points.max(axis=0)+reserve
            bounds = App.BoundBox(*lower, *upper)
            nearby = {lead: shape for lead, shape in conductors.items() if bounds.intersect(shape.BoundBox)}
            if nearby:
                polyline = Part.makePolygon([V(*point) for point in points])
                for lead, conductor in nearby.items():
                    gap = conductor.distToShape(polyline)[0]-reserve
                    if gap <= 0.:
                        overlaps.append({'lead': lead, 'neighbor': name, 'reserved_gap_mm': gap})
    return {'sha256': sha256(path.read_bytes()).hexdigest(), 'checked_conductors': len(diameters),
            'interferences': overlaps}


def native_targets(doc, rigid):
    moving = {obj.Name for obj in (*doc.HubInstalled.Group, *doc.HubCableSpace.Group)}
    moving.update(obj.Name for obj in doc.Objects if obj.Name.startswith('HubBolt'))
    # The camera wire stays fixed during hatch service. The other native
    # harness wires are drawings of one pose, superseded by the B23 archives.
    objects = {obj.Name: world_shape(obj) for obj in doc.Objects if obj.TypeId == 'Part::Feature'
               and (not obj.Name.startswith(('HubRearClearance', 'HarnessWire'))
                    or obj.Label.startswith('USB-Camera'))}
    objects.update(Part000=rigid['base'], CableSaddle=rigid['saddle'], FixedStationSocket=rigid['socket'])
    objects.update({name: solid for name, solid in rigid.items() if name.startswith('M3 ')})
    fixed = {name: shape for name, shape in objects.items() if name not in moving}
    hatch = {name: shape for name, shape in objects.items() if name in moving}
    return fixed, hatch


def check_pose(fixed, hatch, plug, withdrawal, parking, drop):
    lowered = V(0., 0., -drop)
    shifted = {**fixed, **{name: shape.translated(lowered) for name, shape in hatch.items()},
               'XT60U-M plug': plug.translated(V(0., -withdrawal, -parking-drop))}
    terminal_y = hatch['HubBodyJ2'].BoundBox.YMax+.001
    radius = WIRE_RADIUS+WIRE_RESERVE
    wires, cups, evidence = {}, {}, {}
    for name, (x_board, x_plug) in LEADS.items():
        edges, minimum_radius, tail = lead_route(x_board, x_plug, terminal_y, withdrawal, parking, drop)
        wires[name] = cable = tube(edges, radius)
        # 4 mm finished Ø is a geometric allowance for the solder tail
        # covering. Qualify the solder fill and insulation on real parts.
        cups[name] = cup = cylinder(TAIL_INSULATION_RADIUS+WIRE_RESERVE, TAIL_STRAIGHT,
                                    tuple(tail-TAIL_STRAIGHT*np.array(AXIS_Y)), AXIS_Y)
        path = Part.Wire(edges)
        self_gap = min(left.distToShape(right)[0] - radius
                       - (TAIL_INSULATION_RADIUS+WIRE_RESERVE if right is edges[-1] else radius)
                       for i, left in enumerate(edges) for right in edges[i+2:])
        evidence[name] = {
            'conductor_centerline_mm': path.Length,
            'minimum_radius_mm': minimum_radius,
            'minimum_nonadjacent_centerline_gap_with_reserve_mm': self_gap,
            'base_clearance_required_mm': fixed['Part000'].BoundBox.ZMin
                                          - min(cable.BoundBox.ZMin, cup.BoundBox.ZMin),
            'native_hits_mm3': collision_volumes(cable, shifted),
            'tail_insulation_hits_mm3': collision_volumes(cup, shifted),
        }
    combined = {name: Part.Compound([wires[name], cups[name]]) for name in wires}
    gap = combined['J2+'].distToShape(combined['J2-'])[0]
    return evidence, gap, combined


def poses():
    def steps(limit):
        return np.linspace(0., limit, ceil(limit/POSE_STEP)+1)
    return list(dict.fromkeys([*(('withdrawal', value, 0., 0.) for value in steps(WITHDRAW)),
                               *(('parking', WITHDRAW, value, 0.) for value in steps(PARK)[1:]),
                               *(('hatch', WITHDRAW, PARK, value)
                                 for value in sorted(set(steps(DROP)) | set(HATCH_DROPS)))]))


def lowering_sweep(fixed, terminal_y):
    """Bound every point of the parked wires throughout the rigid hatch translation."""
    results = {}
    for name, (x_board, x_plug) in LEADS.items():
        edges, _, _ = lead_route(x_board, x_plug, terminal_y, WITHDRAW, PARK, 0.)
        hits = {}
        checked = 0
        for index, edge in enumerate(edges):
            panels = ceil(edge.Length/SWEEP_PANEL_LENGTH)
            checked += panels
            wire_radius = TAIL_INSULATION_RADIUS if index == len(edges)-1 else WIRE_RADIUS
            # These edges are lines or circular arcs with uniform arclength
            # per parameter unit. Each half-panel lies within its arclength
            # from the midpoint. Expand again to contain the insulated tube.
            pad = wire_radius+WIRE_RESERVE+edge.Length/(2.*panels)
            start, end = edge.FirstParameter, edge.LastParameter
            for panel in range(panels):
                x, y, z = edge.valueAt(start+(end-start)*(panel+.5)/panels)
                envelope = box(x-pad, x+pad, y-pad, y+pad, z-pad-DROP, z+pad)
                for part, volume in collision_volumes(envelope, fixed).items():
                    hits[part] = max(hits.get(part, 0.), volume)
        results[name] = {'panels': checked, 'max_panel_intersection_mm3': hits}
    return results


def wire_material_screen(wire, centerline_radius, lengths):
    max_diameter = max(wire.od_mm)
    # Apply the sheet's bend limit to the inner jacket as a conservative
    # screen. Keep the clearance runs at the larger geometric design OD.
    inner_radius = centerline_radius-max_diameter/2.
    required_radius = wire.bend_diameters*max_diameter
    copper_low, copper_high = J2_STRANDED_RANGE_MM2
    resistance = sum(lengths.values())/1000.*wire.hot_ohms_per_m
    checks = {
        'bend_limit': inner_radius >= required_radius,
        'contained_in_checked_wire_envelope': max_diameter <= 2.*WIRE_RADIUS,
        'phoenix_1715721_stranded_conductor_range': copper_low <= wire.copper_mm2 <= copper_high,
    }
    return {
        'status': 'pass' if all(checks.values()) else 'fail',
        'datasheet': WIRE_DATASHEETS[wire.part],
        'awg': wire.awg,
        'conductor_area_mm2': wire.copper_mm2,
        'outer_diameter_range_mm': wire.od_mm,
        'minimum_bend_radius_diameters': wire.bend_diameters,
        'minimum_manufacturer_bend_radius_mm': required_radius,
        'minimum_modeled_inside_jacket_radius_mm': inner_radius,
        'two_conductor_free_length_loop_resistance_at_70_C_mohm': resistance*1000.,
        'two_conductor_free_length_loss_at_2_8_A_70_C_W': NECK_LOAD_A**2*resistance,
        'checks': checks,
    }


def run(source, archive_dir):
    doc = App.openDocument(str(source.resolve()))
    try:
        rigid_report, rigid = evaluate(doc, reverse_key=True, rear_offset=SOCKET_REAR_OFFSET)
        fixed, hatch = native_targets(doc, rigid)
        lowering = lowering_sweep(fixed, hatch['HubBodyJ2'].BoundBox.YMax+.001)
        diameters = cable_ids()
        samples = []
        for phase, withdrawal, parking, drop in poses():
            evidence, gap, combined = check_pose(fixed, hatch, rigid['plug'], withdrawal, parking, drop)
            row = {'phase': phase, 'withdrawal_mm': withdrawal, 'parking_mm': parking, 'hatch_drop_mm': drop,
                   'conductors': evidence, 'minimum_reserved_conductor_gap_mm': gap}
            if drop in HATCH_DROPS:
                archive = archive_dir/f'wires-0-0-0-{int(drop)}.npz'
                row['neighboring_B23_wires'] = archive_neighbors(archive, diameters, combined)
            samples.append(row)
    finally:
        App.closeDocument(doc.Name)
    values = [wire for row in samples for wire in row['conductors'].values()]
    lengths = {name: samples[0]['conductors'][name]['conductor_centerline_mm'] for name in LEADS}
    max_length_error = max(abs(wire['conductor_centerline_mm']-lengths[name])
                           for row in samples for name, wire in row['conductors'].items())
    minimum_radius = min(wire['minimum_radius_mm'] for wire in values)
    minimum_gap = min(row['minimum_reserved_conductor_gap_mm'] for row in samples)
    minimum_self_gap = min(wire['minimum_nonadjacent_centerline_gap_with_reserve_mm'] for wire in values)
    required_clearance = max(wire['base_clearance_required_mm'] for wire in values)
    materials = {wire.part: wire_material_screen(wire, minimum_radius, lengths)
                 for wire in (POWER_WIRE, J2_SERVICE_WIRE)}
    checks = {
        'rotated_rigid_station': rigid_report['status'] == 'pass_rigid_and_local_lead',
        'length_error_below_0_001_mm': max_length_error < .001,
        'at_least_R12_centerline': minimum_radius >= BEND_RADIUS-1.e-8,
        'conductors_and_nonadjacent_segments_clear': min(minimum_gap, minimum_self_gap) > 0.,
        'no_reserved_overlap_with_native_parts': not any(wire['native_hits_mm3']
                                                         or wire['tail_insulation_hits_mm3'] for wire in values),
        'continuous_hatch_lowering_clear_against_fixed_solids': not any(
            wire['max_panel_intersection_mm3'] for wire in lowering.values()),
        'shared_pose_B23_harness_clear': not any(row.get('neighboring_B23_wires', {}).get('interferences')
                                                for row in samples),
        'fixture_clearance': required_clearance <= FIXTURE_CLEARANCE,
        'service_candidate_bend_limit_and_J2_wire_size': materials[J2_SERVICE_WIRE.part]['status'] == 'pass',
    }
    return {
        'status': 'blocked' if all(checks.values()) else 'fail',
        'sampled_two_conductor_pigtail_status': 'pass' if all(checks.values()) else 'fail',
        'cad_sha256': sha256(source.read_bytes()).hexdigest(),
        'socket_key_rotation_deg_about_Y': 180.,
        'socket_rear_offset_mm': SOCKET_REAR_OFFSET,
        'polarity_terminal_x_mm': LEADS,
        'plug_pin_spacing_mm': 7.20,
        'plug_drawing': PLUG_DRAWING,
        'wire_outer_diameter_mm': 2.*WIRE_RADIUS,
        'service_pigtail_wire_candidate': J2_SERVICE_WIRE.part,
        'wire_material_screen': materials,
        'j2_manufacturer_stranded_conductor_range_mm2': J2_STRANDED_RANGE_MM2,
        'centerline_length_outside_connector_cups_mm': lengths,
        'fixed_length_error_max_mm': max_length_error,
        'minimum_radius_mm': minimum_radius,
        'minimum_reserved_conductor_gap_mm': minimum_gap,
        'minimum_reserved_nonadjacent_segment_gap_mm': minimum_self_gap,
        'under_base_clearance_required_mm': required_clearance,
        'under_base_clearance_for_trial_fixture_mm': FIXTURE_CLEARANCE,
        'radial_reserve_mm': WIRE_RESERVE,
        'pose_step_max_mm': POSE_STEP,
        'hatch_sweep_panel_max_centerline_mm': SWEEP_PANEL_LENGTH,
        'continuous_hatch_lowering': lowering,
        'checks': checks,
        'rotated_key_rigid_check': rigid_report,
        'samples': samples,
        'pending': [
            'Continuous clearance during plug withdrawal and parking, controlled parking and wire support.',
            'Fixed 12 V supply leads and all five J3/J7 conductors alongside the moving J2 pigtail.',
            'Real XT60 solder tails, 18 AWG attachment, insulation, grip, and strain relief.',
            'Service flex cycling and installed wire current/temperature check with the 6715 candidate.',
        ],
    }


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--archives', type=Path, default=ARCHIVES)
    args = parser.parse_args()
    if args.cad.resolve() == args.output.resolve():
        parser.error('source CAD and report must be separate paths')
    result = run(args.cad, args.archives)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(result['sampled_two_conductor_pigtail_status'], result['status'], result['checks'])
    return 1 if result['status'] == 'fail' else 2


if __name__ == '__main__':
    raise SystemExit(main())
