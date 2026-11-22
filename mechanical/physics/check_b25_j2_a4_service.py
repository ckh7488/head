"""Reconstruct W8/W9 and check A4 service against arbitrary candidate station solids."""
from argparse import ArgumentParser
from hashlib import sha256
import json
from math import acos, ceil, sin
from pathlib import Path
import sys

import FreeCAD as App
import numpy as np
import Part
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'mechanical/physics'), str(ROOT/'mechanical')]
from check_b25_j2_disconnect import AXIS_Y, DROP, PARK, WITHDRAW, WIRE_RADIUS, WIRE_RESERVE, collision_volumes, sweep
from check_b25_j2_pigtail import (ARCHIVES, HATCH_DROPS, SWEEP_PANEL_LENGTH, TAIL_INSULATION_RADIUS,
                                 archive_neighbors, cable_ids, poses, s_turn_edges, s_turn_geometry, tube)
from export_cad import world_shape
from primitives import box, cylinder

V = App.Vector
LEADS = {'A4W8': (9.5, 9.16), 'A4W9': (14.5, 16.36)}
OUTER_START_Y = 75.4
TAIL_END_Y = 156.8
TAIL_STRAIGHT = 5.
Y_BEND_START = 76.6
HUB_BEND_RADIUS = 12.
HUB_RUN_Y = 100.
HUB_WIRE_START_Z = -70.
SOCKET_Z = -74.6
LOOP_LENGTH = 140.
LOOP_SPLIT = .30
LEGACY_12V = {'RearLead2_1', 'RearLead2_2', 'CableTie2'}


def service_route(x_board, x_plug, withdrawal, parking, drop):
    theta = acos(1. - (HUB_WIRE_START_Z-SOCKET_Z)/(2.*HUB_BEND_RADIUS))
    end_of_bend_y = Y_BEND_START + 2.*HUB_BEND_RADIUS*sin(theta)
    start = np.array([x_board, OUTER_START_Y, HUB_WIRE_START_Z-drop])
    initial = np.array([x_board, Y_BEND_START, HUB_WIRE_START_Z-drop])
    after_bend = np.array([x_board, end_of_bend_y, SOCKET_Z-drop])
    loop_start = np.array([x_board, HUB_RUN_Y, SOCKET_Z-drop])
    local_turns, initial_radius = s_turn_edges(initial, after_bend)
    near = [Part.makeLine(V(*start), V(*initial)), *local_turns,
            Part.makeLine(V(*after_bend), V(*loop_start))]
    tail = np.array([x_plug, TAIL_END_Y-withdrawal, SOCKET_Z-parking-drop])
    loop_end = tail - [0., TAIL_STRAIGHT, 0.]
    midpoint_y = HUB_RUN_Y + LOOP_SPLIT*(loop_end[1]-HUB_RUN_Y)

    def midpoint(z):
        return np.array([x_board, midpoint_y, z])

    def length_difference(z):
        lower = midpoint(z)
        arcs = (s_turn_geometry(loop_start, lower), s_turn_geometry(lower, loop_end))
        return sum(2.*radius*angle for radius, angle, _ in arcs)-LOOP_LENGTH

    lower = midpoint(brentq(length_difference, loop_end[2]-LOOP_LENGTH, loop_end[2]-.001, xtol=1.e-10))
    down, r_down = s_turn_edges(loop_start, lower)
    up, r_up = s_turn_edges(lower, loop_end)
    return [*near, *down, *up, Part.makeLine(V(*loop_end), V(*tail))], min(initial_radius, r_down, r_up)


def native_targets(doc, replace=None, additional_fixed=None, omit=()):
    moving = {obj.Name for obj in (*doc.HubInstalled.Group, *doc.HubCableSpace.Group)}
    moving.update(obj.Name for obj in doc.Objects if obj.Name.startswith(('ServiceHatchScrew',)))
    omit = set(omit) | set(LEADS) | {'A4XT60ExternalMate'}
    objects = {obj.Name: world_shape(obj) for obj in doc.Objects
               if obj.TypeId == 'Part::Feature' and obj.Name not in omit
               and not obj.Name.startswith(('HarnessWire', 'HubRearClearance'))
               and hasattr(obj, 'Shape') and not obj.Shape.isNull()}
    objects.update(replace or {})
    fixed = {name: shape for name, shape in objects.items() if name not in moving}
    fixed.update(additional_fixed or {})
    hatch = {name: shape for name, shape in objects.items() if name in moving}
    return fixed, hatch


def continuous_lowering(fixed):
    report = {}
    for name, (x_board, x_plug) in LEADS.items():
        edges, _ = service_route(x_board, x_plug, WITHDRAW, PARK, 0.)
        checked = 0
        maxima = {}
        for index, edge in enumerate(edges):
            panels = ceil(edge.Length/SWEEP_PANEL_LENGTH)
            checked += panels
            radius = TAIL_INSULATION_RADIUS if index == len(edges)-1 else WIRE_RADIUS
            pad = radius + WIRE_RESERVE + edge.Length/(2.*panels)
            start, end = edge.FirstParameter, edge.LastParameter
            for panel in range(panels):
                x, y, z = edge.valueAt(start+(end-start)*(panel+.5)/panels)
                envelope = box(x-pad, x+pad, y-pad, y+pad, z-pad-DROP, z+pad)
                for part, volume in collision_volumes(envelope, fixed).items():
                    maxima[part] = max(maxima.get(part, 0.), volume)
        report[name] = {'panels': checked, 'max_intersection_mm3': maxima}
    return report


def service_report(doc, replace=None, additional_fixed=None, omit=(), check_archives=True):
    fixed, hatch = native_targets(doc, replace, additional_fixed, omit)
    plug = world_shape(doc.A4XT60ExternalMate)
    diameters = cable_ids() if check_archives else None
    samples = []
    for phase, withdrawal, parking, drop in poses():
        shift = V(0., 0., -drop)
        plug_shifted = plug.translated(V(0., -withdrawal, -parking-drop))
        plug_targets = {**fixed, **{name: shape.translated(shift) for name, shape in hatch.items()}}
        targets = {**plug_targets, 'A4XT60ExternalMate': plug_shifted}
        evidence, combined = {}, {}
        for name, (x_board, x_plug) in LEADS.items():
            edges, minimum_radius = service_route(x_board, x_plug, withdrawal, parking, drop)
            wire = tube(edges, WIRE_RADIUS+WIRE_RESERVE)
            boot = cylinder(TAIL_INSULATION_RADIUS+WIRE_RESERVE, TAIL_STRAIGHT,
                            tuple(edges[-1].Vertexes[0].Point), AXIS_Y)
            combined[name] = Part.Compound([wire, boot])
            self_gap = min(left.distToShape(right)[0] - (WIRE_RADIUS+WIRE_RESERVE)
                           - ((TAIL_INSULATION_RADIUS if right is edges[-1] else WIRE_RADIUS) + WIRE_RESERVE)
                           for i, left in enumerate(edges) for right in edges[i+2:])
            evidence[name] = {'centerline_mm': Part.Wire(edges).Length, 'min_radius_mm': minimum_radius,
                              'nonadjacent_self_gap_mm': self_gap, 'wire_hits_mm3': collision_volumes(wire, targets),
                              'boot_hits_mm3': collision_volumes(boot, targets),
                              'outermost_z_mm': combined[name].BoundBox.ZMin}
        row = {'phase': phase, 'withdrawal_mm': withdrawal, 'parking_mm': parking, 'drop_mm': drop,
               'evidence': evidence, 'plug_hits_mm3': collision_volumes(plug_shifted, plug_targets),
               'pair_gap_mm': combined['A4W8'].distToShape(combined['A4W9'])[0]}
        if diameters is not None and (phase == 'hatch' and drop in HATCH_DROPS or withdrawal == 0.):
            archive = ARCHIVES/f'wires-0-0-0-{int(drop)}.npz'
            row['B23_reference_neighbors'] = archive_neighbors(archive, diameters, combined)
        samples.append(row)
    parked_plug = plug.translated(V(0., -WITHDRAW, -PARK))
    rigid_sweeps = {
        'withdraw': collision_volumes(sweep(plug, 1, -WITHDRAW), fixed, ('A4XT60ExternalSocket',)),
        'park': collision_volumes(sweep(plug.translated(V(0., -WITHDRAW, 0.)), 2, -PARK), fixed),
        'hatch': collision_volumes(sweep(parked_plug, 2, -DROP), fixed),
    }
    rows = [row for sample in samples for row in sample['evidence'].values()]
    return {'sample_count': len(samples), 'lowest_wire_z_mm': min(row['outermost_z_mm'] for row in rows),
            'min_reserved_pair_gap_mm': min(row['pair_gap_mm'] for row in samples),
            'length_bounds_mm': [min(row['centerline_mm'] for row in rows), max(row['centerline_mm'] for row in rows)],
            'minimum_nonadjacent_self_gap_mm': min(row['nonadjacent_self_gap_mm'] for row in rows),
            'minimum_centerline_radius_mm': min(row['min_radius_mm'] for row in rows),
            'rigid_plug_sweeps': rigid_sweeps, 'continuous_lowering': continuous_lowering(fixed),
            'samples': samples}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--exclude-old-12v', action='store_true')
    parser.add_argument('--exclude-archives', action='store_true')
    args = parser.parse_args()
    doc = App.openDocument(str(args.cad))
    try:
        report = service_report(doc, omit=LEGACY_12V if args.exclude_old_12v else (),
                                check_archives=not args.exclude_archives)
        report['cad_sha256'] = sha256(args.cad.read_bytes()).hexdigest()
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    main()
