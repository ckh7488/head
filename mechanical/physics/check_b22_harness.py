"""Replay fixed-length harness routes while pitch, gaze, yaw and jaw change together."""

from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
from itertools import product
import json
from pathlib import Path

import numpy as np
import trimesh

from b20_harness import CHIN
from clearance_routes import id5_jaw_clearance
from wiring_check import Scene, bundle, radius_target, read, routed_cable, segment_gap
from wiring_motion import matrices


ROOT = Path(__file__).resolve().parents[2]
WIRE_DATA = ROOT / 'web/assets/wiring.json'
CUT_LENGTHS = ROOT / 'mechanical/revisions/b20/physics/harness-cut-lengths.json'
CAMERA_ROUTE = 'USB-Camera'
CAMERA_INTERNAL_RUN_MM = 368.
CAMERA_REAR_RUN_MM = 83.
CAMERA_SUPPLIED_MM = 1000.
EMERGENCY_JAW_PROFILE = ((6.50, 9.79), (6.90, 9.61), (7.00, 9.11), (7.15, 8.87))


def cutoff_jaw(pitch):
    for limit, opening in EMERGENCY_JAW_PROFILE:
        if pitch <= limit:
            return opening
    raise ValueError('Pitch leaves the qualified combined cutoff profile')


def trajectories(powered, arrest, jaw, coupled=False):
    low, high = powered
    minimum, maximum = arrest
    for side in (-1, 1):
        start = (-60.*side, low, 8.*side, 0., 0.)
        end = (60.*side, high, -8.*side, 0., 0.)
        yield f'tracking_{side:+}', np.linspace(start, end, 13)
    for yaw, direction in product((-60., 0., 60.), (-1, 1)):
        limit = minimum if direction < 0 else maximum
        start = (yaw, low+3. if direction < 0 else high-3., -8.*direction, 0., 0.)
        end = (yaw, limit, 8.*direction, 0., jaw)
        path = np.linspace(start, end, 7)
        if coupled:
            path[:, 4] = [cutoff_jaw(pitch) for pitch in path[:, 1]]
        yield f'power_loss_{yaw:+g}_{direction:+}', path
    if coupled:
        endpoints = [min(maximum, pitch) for pitch, _ in EMERGENCY_JAW_PROFILE]
        for pitch in dict.fromkeys(endpoints):
            yield f'cutoff_wire_clearance_{pitch:+.2f}', [
                (yaw, pitch, gaze, 0., cutoff_jaw(pitch))
                for yaw, gaze in product((-60., 0., 60.), (-8., 0., 8.))]


def build_scene(cad, layout, baseline, changed, full_shapes):
    scene = Scene.__new__(Scene)
    scene.groups = {}
    world = cad / 'world'
    scene.add(CHIN, layout['world_motion'][CHIN], trimesh.load_mesh(world/f'{CHIN}.stl'))
    for name in changed:
        solid = trimesh.load_mesh(world/f'{name}.stl')
        old = baseline / 'world' / f'{name}.stl'
        if old.exists() and name not in full_shapes:
            solid = solid.difference(trimesh.load_mesh(old), engine='manifold')
        if len(solid.faces):
            scene.add(name, layout['world_motion'][name], solid)
    return scene


def setup(cad, layout, baseline, changed, full_shapes, camera_run_mm, motors_only):
    global STATE
    lengths = read(CUT_LENGTHS)
    lengths[CAMERA_ROUTE] = camera_run_mm
    STATE = layout, read(WIRE_DATA), lengths, build_scene(cad, layout, baseline, changed, full_shapes), motors_only


def check_sample(pose):
    layout, wiring, lengths, scene, motors_only = STATE
    motion = matrices(layout, *pose)
    changed_power = None
    try:
        cables = [c for c in bundle(wiring, lengths, motion, pose[3], packed=True, pitch=pose[1], eye=pose[2])
                  if c.name.startswith('motor') or not motors_only and c.name == CAMERA_ROUTE]
        expected = {name for name in lengths if name.startswith('motor') or not motors_only and name == CAMERA_ROUTE}
        if {c.name for c in cables} != expected:
            raise ValueError('Incomplete moving harness')
        for index, cable in enumerate(cables):
            if cable.name != 'motor5-power':
                continue
            points = id5_jaw_clearance(cable.points, motion, cable.length, pose[0], pose[1], pose[4])
            if points is not cable.points:
                changed_power = cables[index] = routed_cable(cable, points)
    except ValueError as error:
        return {'pose_deg': pose, 'checked_cables': 0, 'contacts': [], 'route_error': str(error)}
    camera = next((c for c in cables if c.name == CAMERA_ROUTE), None)
    if camera is not None:
        camera_error = float(camera.arc[-1]) - lengths[CAMERA_ROUTE]
        if abs(camera_error) > .01:
            return {'pose_deg': pose, 'checked_cables': 0, 'contacts': [],
                    'route_error': f'{CAMERA_ROUTE} centerline length error {camera_error:.3f} mm'}
    # Use the already qualified jaw-only clearance bands at the same opening angles.
    if 6.50 < pose[1] <= 6.90 and 9. < pose[4] <= 9.61:
        chin_margin = .75
    else:
        chin_margin = 1. if pose[4] <= 10.25 else .25 if pose[4] <= 11.0 else .125
    stops = {name for operands in scene.groups.values() for name in operands} - {CHIN}
    contacts = [hit for cable in cables for hit in scene.hits(cable, motion, chin_margin, only={CHIN})]
    contacts.extend(hit for cable in cables for hit in scene.hits(cable, motion, .25, only=stops))
    if changed_power is not None:
        contacts.extend(hit for cable in cables
                        if cable is not changed_power and (hit := segment_gap(changed_power, cable)))
    row = {'pose_deg': pose, 'checked_cables': len(cables), 'contacts': contacts,
           'chin_reserve_mm': chin_margin}
    if camera is not None:
        row['camera'] = {'centerline_mm': round(float(camera.arc[-1]), 5),
                         'centerline_error_mm': round(camera_error, 5),
                         'sampled_minimum_bend_radius_mm': round(camera.radius, 3),
                         'bend_target_mm': radius_target(camera.name, camera.diameter),
                         'bend_point_mm': camera.bend_point}
    return row


def check(cad, output, baseline, powered, arrest, jaw, changed, jobs, camera_run_mm=CAMERA_INTERNAL_RUN_MM,
          coupled=False, require_camera_bend=False, motors_only=False, full_shapes=()):
    layout = read(cad/'cad_parts.json')
    original = read(baseline/'cad_parts.json')
    for name in changed:
        if name not in layout['world_motion']:
            raise ValueError(f'Missing changed neck part {name}')
    if not set(full_shapes) <= set(changed):
        raise ValueError('Every whole-part screen must also be listed among the changed parts')
    cases = {name: [tuple(row) for row in positions]
             for name, positions in trajectories(powered, arrest, jaw, coupled)}
    poses = tuple(dict.fromkeys(pose for path in cases.values() for pose in path))
    with ProcessPoolExecutor(jobs, initializer=setup,
                             initargs=(cad, layout, baseline, changed, full_shapes, camera_run_mm, motors_only)) as pool:
        evidence = list(pool.map(check_sample, poses))
    indexes = {pose: n for n, pose in enumerate(poses)}
    contacts = sum(bool(row['contacts']) for row in evidence)
    unresolved_routes = sum('route_error' in row for row in evidence)
    bends = [row['camera'] for row in evidence if 'camera' in row]
    bend_failures = sum(row['sampled_minimum_bend_radius_mm'] < row['bend_target_mm'] for row in bends)
    passed = not contacts and not unresolved_routes and (not require_camera_bend or not bend_failures)
    report = {'status': 'pass' if passed else 'fail', 'cad_sha256': layout['source_sha256'],
              'reference_cad_sha256': original['source_sha256'], 'added_part_keys': list(changed),
              'coupled_cutoff_jaw_profile': EMERGENCY_JAW_PROFILE if coupled else None,
              'camera_internal_run_mm': None if motors_only else camera_run_mm,
              'camera_bend': {'required_for_pass': require_camera_bend, 'checked_poses': len(bends),
                              'below_target': bend_failures,
                              'smallest_radius_mm': min((row['sampled_minimum_bend_radius_mm']
                                                        for row in bends), default=None)},
              'camera_cable_allocation': None if motors_only else {
                  'supplied_mm': CAMERA_SUPPLIED_MM, 'rear_run_mm': CAMERA_REAR_RUN_MM,
                  'parked_mm': CAMERA_SUPPLIED_MM - CAMERA_REAR_RUN_MM - camera_run_mm},
              'scope': 'Sampled pose-fitted cable polylines with fixed cut-length inputs. '
                       'Includes simultaneous axis motion and geometric reserves. Excludes elastic and friction forces.',
              'trajectories': {name: [indexes[pose] for pose in path] for name, path in cases.items()},
              'samples': evidence}
    if full_shapes:
        report['whole_part_mesh_keys'] = list(full_shapes)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    camera_summary = '' if motors_only else f', {bend_failures} camera bends below target'
    print(f'{len(evidence)} harness poses, {contacts} with contacts, '
          f'{unresolved_routes} unresolved routes{camera_summary}', flush=True)
    return passed


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--powered', type=float, nargs=2, default=(-15., 6.))
    parser.add_argument('--arrest', type=float, nargs=2, required=True)
    parser.add_argument('--jaw', type=float, default=11.175)
    parser.add_argument('--camera-run-mm', type=float, default=CAMERA_INTERNAL_RUN_MM)
    parser.add_argument('--changed', nargs='*', default=())
    parser.add_argument('--full-shapes', nargs='*', default=(),
                        help='Check these changed parts whole, including OEM meshes without closed volumes')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--coupled-cutoff', action='store_true')
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument('--require-camera-bend', action='store_true')
    scope.add_argument('--motors-only', action='store_true')
    args = parser.parse_args()
    if not 0 < args.camera_run_mm <= CAMERA_SUPPLIED_MM - CAMERA_REAR_RUN_MM:
        parser.error('--camera-run-mm must fit the supplied cable and rear run')
    if not check(args.cad, args.report, args.baseline, args.powered, args.arrest, args.jaw, args.changed, args.jobs,
                 args.camera_run_mm, args.coupled_cutoff, args.require_camera_bend, args.motors_only, args.full_shapes):
        raise SystemExit(1)
