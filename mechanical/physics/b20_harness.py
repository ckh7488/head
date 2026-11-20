"""Replay a retained B20 harness while only the jaw moves.

The centerline at each fixed neck/eye/hatch setting comes from wiring_check at jaw
zero. The jaw sweep does not refit a centerline. Separate neck settings still
use separate references, so this is a jaw-motion interference diagnostic, not
an elastic or frictional simulation of the full harness.
"""

from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from itertools import product
import json
from pathlib import Path

import numpy as np
import trimesh

from clearance_routes import bell
from cable_spacing import restore_length
from wiring_check import Cable, Scene, bundle, discrete_bend, radius_target, read, segment_gap
from wiring_motion import arc_lengths, matrices, transform


ROOT = Path(__file__).resolve().parents[2]
CHIN = 'Jaw_30_moving_jaw'
JAW_STEP_DEG = .25
POSES = (
    (0, 0, 0, 0, 0),
    (0, 6, -8, 0, 0),
    (45, 6, -8, 0, 0),
    (60, 6, -8, 0, 0),
    (60, 6, -8, 30, 0),
    (-60, -15, 8, 0, 0),
)
RELIEFS = (
    ((-39.5, -23.5, 20.), (11., 7., 8.)),
    ((29., -31., 12.), (14., 9., 8.5)),
)


def capture(layout, wiring, lengths, pose):
    """Generate one starting configuration for the fixed-axis jaw replay."""
    _, pitch, eye, drop, _ = pose
    cables = bundle(wiring, lengths, matrices(layout, *pose), drop, packed=True, pitch=pitch, eye=eye)
    return [cable for cable in cables if cable.name.startswith(('motor3-', 'motor5-'))
            or cable.name == 'USB-Camera']


def endpoint_frames(name):
    base = 'fixed' if name in ('motor3-data', 'USB-Camera') else 'hatch'
    terminal = 'pan' if name.startswith('motor5-') else 'head'
    return base, terminal


def endpoint_error(reference, cable, motion):
    a, b = endpoint_frames(cable.name)
    expected = np.stack((transform(reference.points[0], motion[a]), transform(reference.points[-1], motion[b])))
    return float(np.linalg.norm(cable.points[[0, -1]] - expected, axis=1).max())


def minimum_sampled_radius(cable):
    """Report sensitivity to spacing and keep the last 3 mm of terminations explicit."""
    values = {}
    for spacing in (.5, 1., 2.):
        s = np.r_[0., np.arange(spacing, cable.arc[-1], spacing), cable.arc[-1]]
        points = np.column_stack([np.interp(s, cable.arc, axis) for axis in cable.points.T])
        radius, bend_point = discrete_bend(points)
        values[str(spacing)] = {'radius_mm': round(radius, 3), 'point': bend_point}
    radius, point = discrete_bend(cable.points[(cable.arc >= 3.) & (cable.arc <= cable.arc[-1]-3.)])
    return {'raw_mm': round(cable.radius, 3), 'raw_point': cable.bend_point,
            'outside_terminal_3mm': {'radius_mm': round(radius, 3), 'point': point},
            'resampled': values, 'target_mm': round(radius_target(cable.name, cable.diameter), 3)}


def replay(scene, layout, pose, cables):
    result = {c.name: {'first_contact_deg': None, 'first_within_0_25mm_deg': None} for c in cables}
    for angle in np.arange(0., 13. + JAW_STEP_DEG, JAW_STEP_DEG):
        motion = matrices(layout, *pose[:4], angle)
        for cable in cables:
            row = result[cable.name]
            if row['first_within_0_25mm_deg'] is None:
                if not scene.hits(cable, motion, .25, only={CHIN}):
                    continue
                row['first_within_0_25mm_deg'] = float(angle)
            if row['first_contact_deg'] is None:
                hits = scene.hits(cable, motion, 0., only={CHIN})
                if hits:
                    row['first_contact_deg'] = float(angle)
                    row['contact_point_mm'] = hits[0]['point']
    return result


def sample_point(cable, station):
    return np.array([np.interp(station, cable.arc, axis) for axis in cable.points.T])


def station_at_z(cable, height):
    upper = int(np.flatnonzero(cable.points[:, 2] >= height)[0])
    return float(np.interp(height, cable.points[upper-1:upper+1, 2], cable.arc[upper-1:upper+1]))


def guide_spans(cable, station):
    index = int(np.searchsorted(cable.arc, station))
    if abs(cable.arc[index]-station) < 1.e-8:
        return cable.points[:index+1], cable.points[index:]
    guide = sample_point(cable, station)
    return np.vstack((cable.points[:index], guide)), np.vstack((guide, cable.points[index:]))


def chord_slack(start, guide, end, before, after):
    """Lower-bound unavoidable axial strain from endpoint distance alone."""
    nominal = min(before - np.linalg.norm(guide-start), after - np.linalg.norm(end-guide))
    corners = guide + np.array(tuple(product((-.75, .75), repeat=3)))
    side_a = before - .5 - np.linalg.norm(corners-start, axis=1).max()
    side_b = after - .5 - np.linalg.norm(corners-end, axis=1).max()
    return {'nominal_mm': round(float(nominal), 3),
            'corner_and_cut_error_mm': round(float(min(side_a, side_b)), 3)}


def fit_span(points, stations, length, direction):
    """Test modest analytic slack redistribution with both ends still fixed."""
    modes = [bell(stations-length*.56, length*.37)[:, None]*direction]
    for start, stop in ((6., length-8.), (18., length-18.), (length*.55, length-12.)):
        if stop-start < 12.:
            continue
        phase = np.clip((stations-start)/(stop-start), 0., 1.)[:, None]
        first, last = points[np.searchsorted(stations, (start, stop))]
        toward_chord = (1.-phase)*first + phase*last - points
        shift = np.sin(np.pi*phase)**2*toward_chord
        maximum = np.linalg.norm(shift, axis=1).max()
        if maximum > 1.e-7:
            modes.append(-shift/maximum)
    candidates = []
    for mode in modes:
        try:
            fitted = restore_length(points, mode, length)
        except ValueError:
            continue
        if fitted is not None:
            movement = float(np.linalg.norm(fitted-points, axis=1).max())
            if movement <= 23.:
                candidates.append((movement, fitted))
    return min(candidates, key=lambda row: row[0])[1] if candidates else None


def try_guide(cable, station, guide, motion):
    """Capture the same material point at a proposed carrier-mounted guide."""
    before, after = guide_spans(cable, station)
    a, b = arc_lengths(before), arc_lengths(after)
    shift = guide-before[-1]
    toward_rear = motion['pan'][:3, :3] @ np.array([0., 1., 0.])
    front = fit_span(before + bell(a-a[-1], 28.)[:, None]*shift, a, a[-1], toward_rear)
    rear = fit_span(after + bell(b, 28.)[:, None]*shift, b, b[-1], toward_rear)
    if front is None or rear is None:
        return None
    points = np.vstack((front, rear[1:]))
    if not np.allclose(points[[0, len(front)-1, -1]], [cable.points[0], guide, cable.points[-1]], atol=1.e-6):
        raise ValueError(f'{cable.name} moved a terminal or captured point')
    return Cable(cable.name, points, cable.diameter, cable.length, *discrete_bend(points))


def guide_trial(scene, layout, pose, cables, specs):
    motion = matrices(layout, *pose)
    extreme = matrices(layout, *pose[:4], 13.)
    rows, fitted = {}, []
    for cable in cables:
        station, local_guide = specs[cable.name]
        guide = transform(local_guide, motion['pan'])
        before, after = guide_spans(cable, station)
        slack = chord_slack(cable.points[0], guide, cable.points[-1],
                           arc_lengths(before)[-1], arc_lengths(after)[-1])
        shifted = try_guide(cable, station, guide, motion)
        row = {'chord_slack_mm': slack, 'length_fit': shifted is not None}
        rows[cable.name] = row
        if shifted is None:
            continue
        fitted.append(shifted)
        row['guide_shift_mm'] = round(float(np.linalg.norm(guide-sample_point(cable, station))), 3)
        row['span_length_error_mm'] = round(float(shifted.arc[-1]-cable.arc[-1]), 7)
        row['bend'] = minimum_sampled_radius(shifted)
        reported = scene.hits(shifted, extreme, .25)
        baseline_contacts = {hit['part'] for hit in scene.hits(cable, extreme, 0.)}
        nominal = scene.hits(shifted, extreme, 0., only={hit['part'] for hit in reported})
        row['within_0_25mm'] = reported
        row['new_nominal_contacts'] = [hit for hit in nominal if hit['part'] not in baseline_contacts]
    pairs = [hit for index, cable in enumerate(fitted) for other in fitted[index+1:]
             if (hit := segment_gap(cable, other)) is not None]
    return {'wires': rows, 'pair_contacts_among_fitted_paths': pairs}


def outer_surface(mesh, starts, direction):
    directions = np.broadcast_to(direction, starts.shape)
    points, rays, _ = mesh.ray.intersects_location(starts, directions)
    first = np.full(len(starts), np.inf)
    np.minimum.at(first, rays, np.einsum('ij,j->i', points-starts[rays], direction))
    return first


def exterior_check(before, after):
    reports = {}
    for name, axis, sign in (('front', 1, 1), ('left', 0, 1), ('right', 0, -1)):
        width = 0 if axis == 1 else 1
        across = np.arange(-54., 47.) if width == 0 else np.arange(-42., -16.)
        u, z = np.meshgrid(across, np.arange(2., 30.))
        origins = np.zeros((u.size, 3))
        origins[:, axis], origins[:, width], origins[:, 2] = -100.*sign, u.ravel(), z.ravel()
        direction = np.eye(3)[axis]*sign
        first = outer_surface(before, origins, direction)
        second = outer_surface(after, origins, direction)
        shared = np.isfinite(first) & np.isfinite(second)
        delta = abs(first[shared]-second[shared])
        reports[name] = {'shared_rays': int(shared.sum()), 'changed_over_0_1mm': int((delta > .1).sum()),
                         'lost_surface_rays': int((np.isfinite(first) & ~np.isfinite(second)).sum()),
                         'maximum_difference_mm': round(float(delta.max()), 3)}
    return reports


def retained_wall(original, altered, center, radii):
    centers = altered.triangles_center
    local = (centers-center)/radii
    faces = np.flatnonzero((np.abs(np.linalg.norm(local, axis=1)-1.) < .025)
                           & (np.einsum('ij,ij->i', altered.face_normals, local/radii) < 0.))
    # Leave the tapered rim out of the thickness statistic.
    inside = trimesh.proximity.signed_distance(original, centers[faces]) > .5
    samples, directions = centers[faces[inside]], -altered.face_normals[faces[inside]]
    start = samples + .03*directions
    points, rays, _ = altered.ray.intersects_location(start, directions)
    thickness = np.full(len(samples), np.inf)
    np.minimum.at(thickness, rays, np.linalg.norm(points-samples[rays], axis=1))
    if not len(thickness) or not np.all(np.isfinite(thickness)):
        raise ValueError('Some internal relief surfaces have no measured retained wall')
    return {'samples': len(thickness), 'inward_ray_min_mm': round(float(thickness.min()), 3),
            'inward_ray_p05_mm': round(float(np.quantile(thickness, .05)), 3)}


def relief_probe(scene, layout, jaw, baseline, destination):
    cutters = []
    for center, radii in RELIEFS:
        cutter = trimesh.creation.icosphere(subdivisions=3)
        cutters.append(cutter.apply_scale(radii).apply_translation(center))
    altered = trimesh.boolean.difference((jaw, *cutters), engine='manifold')
    if not altered.is_volume or altered.body_count != 1:
        raise ValueError('The relief probe must leave a single closed jaw mesh')
    altered.export(destination)
    scene.add(CHIN, 'jaw', altered)
    rows = [replay(scene, layout, pose, cables) for pose, cables in zip(POSES, baseline, strict=True)]
    exterior = exterior_check(jaw, altered)
    preserved = all(row['changed_over_0_1mm'] == 0 and row['lost_surface_rays'] == 0 for row in exterior.values())
    return {'ellipsoids_center_and_radii_mm': RELIEFS,
            'removed_mm3': round(float(jaw.volume-altered.volume), 3),
            'sampled_exterior_preserved': preserved,
            'frontal_and_side_rays': exterior,
            'remaining_wall_on_sampled_cut_faces': [retained_wall(jaw, altered, np.array(center), np.array(radii))
                                                      for center, radii in RELIEFS],
            'frozen_replays': [dict(fixed_pose=pose, wires=wires) for pose, wires in zip(POSES, rows, strict=True)]}


def main(args):
    layout = read(args.cad/'cad_parts.json')
    wiring = read(ROOT/'web/assets/wiring.json')
    lengths = read(args.cut_lengths)
    assembly = read(ROOT/'web/assets/assembly.json')
    scene = Scene(args.cad, layout, assembly, wiring, read(args.hardware))
    if CHIN not in scene.groups['jaw']:
        raise ValueError('Exact B20 jaw surface missing from the collision scene')
    solve = partial(capture, layout, wiring, lengths)
    with ProcessPoolExecutor(args.workers) as pool:
        baseline = list(pool.map(solve, POSES))
    nominal = {cable.name: cable for cable in baseline[0]}
    order = sorted((cable for cable in baseline[0] if cable.name != 'USB-Camera'),
                   key=lambda cable: sample_point(cable, station_at_z(cable, 17.5))[0])
    specs = {c.name: (station_at_z(c, 17.5), [-43. + index*2.25, 14., 17.5])
             for index, c in enumerate(order)}
    camera = nominal['USB-Camera']
    specs[camera.name] = station_at_z(camera, 6.), [35., 8., 6.]
    rows = []
    for pose, cables in zip(POSES, baseline, strict=True):
        motion = matrices(layout, *pose)
        endpoints = {cable.name: round(endpoint_error(nominal[cable.name], cable, motion), 6) for cable in cables}
        if max(endpoints.values()) > .01:
            raise ValueError(f'{pose}: terminal path drift {endpoints}')
        report = {'fixed_pose': pose, 'endpoint_transform_error_mm': endpoints,
                  'frozen_wire_jaw_replay': replay(scene, layout, pose, cables),
                  'bend': {cable.name: minimum_sampled_radius(cable) for cable in cables},
                  'guide_trial': guide_trial(scene, layout, pose, cables, specs)}
        rows.append(report)
        print(pose, {name: row['first_contact_deg'] for name, row in report['frozen_wire_jaw_replay'].items()
                     if row['first_contact_deg'] is not None}, flush=True)
    chin_path = args.cad/'world'/f'{CHIN}.stl'
    chin_mesh = trimesh.load_mesh(chin_path)
    pivot = np.asarray(layout['jaw_pivot_mm'])
    lever = np.linalg.norm(chin_mesh.vertices[:, 1:] - pivot[1:], axis=1).max()
    gap_motion = 2. * lever * np.sin(np.radians(JAW_STEP_DEG)/4.)
    results = {
        'cad_sha256': layout['source_sha256'],
        'jaw_angle_step_deg': JAW_STEP_DEG,
        'maximum_chin_displacement_to_nearest_sample_mm': round(float(gap_motion), 4),
        'guide_pan_frame_station_and_center_mm': specs,
        'guide_sensitivity': 'Capture position ±0.75 mm per axis and each span length 0.5 mm short. '
                             'Chord slack only bounds extension; it cannot predict wire pull or friction.',
        'rows': rows,
    }
    if args.chin_relief_stl is not None:
        if args.chin_relief_stl.resolve() == chin_path.resolve():
            raise ValueError('Use a separate STL path for the scratch relief')
        results['chin_relief_probe'] = relief_probe(scene, layout, chin_mesh, baseline, args.chin_relief_stl)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path, help='B20 CAD export with world meshes')
    parser.add_argument('cut_lengths', type=Path)
    parser.add_argument('hardware', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--chin-relief-stl', type=Path, help='Test and export the scratch relief mesh')
    main(parser.parse_args())
