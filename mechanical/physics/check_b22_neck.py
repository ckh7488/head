"""Check the neck pitch stops and non-stop clearance against the full CAD assembly."""

from argparse import ArgumentParser
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import re

import fcl
import manifold3d as md
import numpy as np
import trimesh as tr
from trimesh.collision import mesh_to_BVH

from check_head import AXES_BY_MOTION, pitch_link_pose, pose, rotation


NECK_PIVOT = (0., 0., 112.)
STOP_KEY = 'pitch_stop'
FIRMWARE = Path(__file__).resolve().parents[2] / 'control/openrb/R5B1/R5B1.ino'
SEARCH_STEP_DEG = .25
ANGLE_RESOLUTION_DEG = .005
GAP_SEARCH_MM = .65
# The bores/shafts are coaxial at X; mesh facet chords produce a small false overlap.
BEARING_MATES = {('Part012', 'Part013'), ('Part014', 'Part015')}
# Pitch servo output flange carries Part016. Its exported vendor case is an open mesh.
DRIVE_MATE = ('Part018', 'Part016')
BASE_MOTIONS = {'fixed', 'hatch'}
LINK_MOTION = 'pitch_link'
LINK_LOWER_MATE = ('PitchLimitLowerPin', 'PitchLimitLink')
LINK_UPPER_MATE = ('PitchLimitLink', 'PitchLimitUpperPin')
LOWER_PIVOT_GAP_MM = .02
SLOT_FINISH_TOLERANCE_MM = .10
B21_RELEASED_JAW_DEG = 11.175
# B21 native solid checks qualified only these unchanged bearing/drive meshes.
QUALIFIED_MATE_MESHES = {
    'Part012': '71527c4c627583f015e9f31cead375307bfa9ac8a2481aa7ee2a91e52955f7e8',
    'Part013': 'b8c70b2d1451f7dce2b5f01d9d381beeac73b2d43494f2b00ad45c10e1e9787b',
    'Part014': '763946fb5547ede08a81f64742275e409fb85c1bcd79080b3157dbd2793cdb82',
    'Part015': 'c8121cb9e1a471f17064392c48c088da1fb5897a3310884f2674fa7f69a1b99b',
    'Part016': '116eb5cad785925567fc8f341b5228be4e6069f73b50f4cad8bf77b646650848',
    'Part018': '25c67c5fc6d252638ca5efa21ce89432e506879d8855a6549cff300003dcd27f',
}


def rigid_group(kind):
    if kind in BASE_MOTIONS:
        return 'base'
    if kind == 'pan':
        return 'pan'
    if kind == LINK_MOTION:
        return LINK_MOTION
    return 'head'


def manifold(mesh):
    solid = md.Manifold(md.Mesh(vert_properties=np.array(mesh.vertices, dtype=np.float32),
                                tri_verts=np.array(mesh.faces, dtype=np.uint32)))
    if solid.status() != md.Error.NoError or solid.is_empty():
        raise ValueError('invalid stop actor solid')
    return solid


def encoder_feedback_limits():
    firmware = FIRMWARE.read_bytes()
    source = firmware.decode()

    def number(name):
        match = re.search(rf'\b{name}\s*=\s*(\d+(?:\.\d+)?)[fu]?\s*;', source)
        if match is None:
            raise ValueError(f'missing firmware literal {name}')
        return float(match[1])

    scale = 4096 / 360.
    negative = int(number('neckPitchMaxNegativeDegrees') * scale + .5)
    positive = int(number('neckPitchMaxDegrees') * scale)
    drift = int(number('positionTolerance'))
    guard = np.array([-negative - drift, positive + drift]) / scale
    return guard, [-negative, positive], drift, sha256(firmware).hexdigest()


def released_overshoot_by_sign(value):
    if isinstance(value, dict):
        if set(value) != {'back', 'forward'}:
            raise ValueError('released overshoot must specify back and forward')
        result = {-1: float(value['back']), 1: float(value['forward'])}
    else:
        result = dict.fromkeys((-1, 1), float(value))
    if any(not np.isfinite(angle) or angle < 0. for angle in result.values()):
        raise ValueError('invalid released overshoot angle')
    return result


class Neck:
    def __init__(self, cad):
        self.layout = json.loads((cad / 'cad_parts.json').read_text())
        self.cad_hash = self.layout['source_sha256']
        if not re.fullmatch('[0-9a-f]{64}', self.cad_hash):
            raise ValueError('invalid CAD source hash')
        self.spec = self.layout['motion_geometry'][STOP_KEY]
        self.link = self.spec.get('link')
        if self.link is not None:
            self.pan_pin = np.array(self.link['pan_pin_mm'], dtype=float)
            self.head_pin = np.array(self.link['head_pin_mm'], dtype=float)
            pins = np.array([self.pan_pin, self.head_pin])
            if pins.shape != (2, 3) or not np.isfinite(pins).all() or np.linalg.norm(np.diff(pins[:, 1:], axis=0)) <= 0:
                raise ValueError('invalid slotted-link pivot geometry')
            self.upper_pin_radius = float(np.linalg.norm(self.head_pin[1:] - NECK_PIVOT[1:]))
        names = set(self.layout['world_motion'])
        if names != set(self.layout['world_sha256']) or not {row['name'] for row in self.layout['parts']} <= names:
            raise ValueError('incomplete CAD export: missing moving part or matching mesh hash')
        for name, digest in QUALIFIED_MATE_MESHES.items():
            role = 'pan' if name in ('Part012', 'Part014', 'Part018') else 'head'
            if self.layout['world_sha256'][name] != digest or self.layout['world_motion'][name] != role:
                raise ValueError(f'{name}: neck bearing/drive mate exemption must be requalified')
        self.names = []
        self.meshes = []
        self.objects = []
        self.kinds = []
        for name, kind in self.layout['world_motion'].items():
            if name.startswith('Harness'):
                continue
            if kind not in AXES_BY_MOTION and kind not in ('hatch', LINK_MOTION):
                raise ValueError(f'{name}: unknown motion {kind}')
            if kind == LINK_MOTION and self.link is None:
                raise ValueError(f'{name}: missing slotted-link pivot metadata')
            path = cad / 'world' / f'{name}.stl'
            if sha256(path.read_bytes()).hexdigest() != self.layout['world_sha256'][name]:
                raise ValueError(f'{name}: stale CAD export')
            mesh = tr.load_mesh(path)
            if not isinstance(mesh, tr.Trimesh) or not len(mesh.faces) or not np.isfinite(mesh.vertices).all():
                raise ValueError(f'{name}: missing or invalid rigid CAD mesh')
            self.names.append(name)
            self.kinds.append(kind)
            self.meshes.append(mesh)
            self.objects.append(fcl.CollisionObject(mesh_to_BVH(mesh)))
        self.ids = {name: i for i, name in enumerate(self.names)}
        self.centers = np.array([mesh.bounds.mean(axis=0) for mesh in self.meshes])
        self.halves = np.array([mesh.extents / 2 for mesh in self.meshes])
        self.groups = [rigid_group(kind) for kind in self.kinds]
        self.distance = fcl.DistanceRequest()
        self.contact = fcl.CollisionRequest(num_max_contacts=32, enable_contact=True)

    def pin_vector(self, q):
        pitch = rotation(q, (1, 0, 0), NECK_PIVOT)
        upper = pitch[:3, :3] @ self.head_pin + pitch[:3, 3]
        return upper[1:] - self.pan_pin[1:]

    def transforms(self, q, local, neck_yaw):
        turn = rotation(neck_yaw, (0, 0, 1), NECK_PIVOT)
        head = turn @ rotation(q, (1, 0, 0), NECK_PIVOT)
        return {kind: (np.eye(4) if kind in BASE_MOTIONS else turn if kind == 'pan'
                       else turn @ pitch_link_pose(q, self.layout) if kind == LINK_MOTION
                       else head @ pose(kind, (q, *local), self.layout))
                for kind in set(self.kinds)}

    def set_transform(self, index, tx):
        self.objects[index].setTransform(fcl.Transform(tx[:3, :3].copy(), tx[:3, 3].copy()))

    def gap(self, i, j):
        return fcl.distance(self.objects[i], self.objects[j], self.distance, fcl.DistanceResult())

    def contacts(self, i, j):
        result = fcl.CollisionResult()
        fcl.collide(self.objects[i], self.objects[j], self.contact, result)
        return np.array([hit.pos for hit in result.contacts]).reshape((-1, 3))

    def stop_contact(self, row, q):
        fixed, moving = (self.ids[name] for name in row['actors'])
        _, tx = self.stop_transforms(row, q)
        self.set_transform(fixed, np.eye(4))
        self.set_transform(moving, tx)
        return self.contacts(fixed, moving)

    def stop_transforms(self, row, q):
        anchor = pitch_link_pose(q, self.layout) if self.kinds[self.ids[row['actors'][0]]] == LINK_MOTION else np.eye(4)
        head = rotation(q, (1, 0, 0), NECK_PIVOT)
        return anchor, np.linalg.solve(anchor, head)

    def cross_pair_groups(self, stops, direction):
        ignored = BEARING_MATES | {DRIVE_MATE} | {tuple(row['actors']) for row in stops if row['direction'] == direction}
        constituents = {}
        for index, group in enumerate(self.groups):
            constituents.setdefault(group, []).append(index)
        groups = {}
        for first, second in (('base', 'head'), ('pan', 'head'), ('base', LINK_MOTION),
                              ('pan', LINK_MOTION), (LINK_MOTION, 'head')):
            for i, j in product(constituents.get(first, ()), constituents.get(second, ())):
                if (self.names[i], self.names[j]) in ignored:
                    continue
                controls = tuple(sorted((set(AXES_BY_MOTION.get(self.kinds[i], ())) |
                                         set(AXES_BY_MOTION.get(self.kinds[j], ()))) - {0}))
                lower_mate = (self.names[i], self.names[j]) == LINK_LOWER_MATE
                key = first == 'base', controls, self.names[j].startswith('Ballast'), lower_mate
                groups.setdefault(key, []).append((i, j))
        return {key: np.array(pairs, dtype=int).T for key, pairs in groups.items()}

    def motion_tolerance(self, transforms, mid, half_angle, neck_yaw):
        # Swept radius is invariant about X. Undo the common yaw to get YZ distances.
        untwist = rotation(-neck_yaw, (0, 0, 1), NECK_PIVOT)
        local_tx = untwist @ transforms
        center = (local_tx[:, :3, :3] @ self.centers[:, :, None])[:, :, 0] + local_tx[:, :3, 3]
        half = (abs(local_tx[:, :3, :3]) @ self.halves[:, :, None])[:, :, 0]
        head_radius = np.linalg.norm((abs(center - NECK_PIVOT) + half)[:, 1:], axis=1)
        travel = np.where(np.array(self.groups) == 'head', head_radius * half_angle, 0.)
        if self.link is not None:
            # The angle of B→A can change by at most A's travel / its minimum distance to B.
            distance_lower = np.linalg.norm(self.pin_vector(mid)) - self.upper_pin_radius * half_angle
            turn = min(2., self.upper_pin_radius * half_angle / distance_lower) if distance_lower > 0. else 2.
            link_radius = np.linalg.norm((abs(center - self.pan_pin) + half)[:, 1:], axis=1)
            mask = np.array(self.groups) == LINK_MOTION
            travel[mask] = link_radius[mask] * turn
        return travel

    def pitch_interval(self, pairs, low, high, local, neck_yaw, required_mm, stats):
        i, j = pairs
        mid = (low + high) / 2
        mats = self.transforms(mid, local, neck_yaw)
        transforms = np.array([mats[kind] for kind in self.kinds])
        rot, off = transforms[:, :3, :3], transforms[:, :3, 3]
        center = (rot @ self.centers[:, :, None])[:, :, 0] + off
        half = (abs(rot) @ self.halves[:, :, None])[:, :, 0]
        motion = self.motion_tolerance(transforms, mid, np.radians((high - low) / 2), neck_yaw)
        travel = motion[i] + motion[j]
        aabb_gaps = np.linalg.norm(np.maximum(abs(center[i] - center[j]) - half[i] - half[j], 0.), axis=1)
        pending = np.flatnonzero(aabb_gaps < travel + max(required_mm, GAP_SEARCH_MM))
        stats['pitch_intervals'] += 1
        uncertain = False
        bound = min(GAP_SEARCH_MM, float(np.min(aabb_gaps - travel)) if not len(pending) else GAP_SEARCH_MM)
        for index in np.unique(np.concatenate([i[pending], j[pending]])):
            self.set_transform(index, transforms[index])
        for index in pending:
            a, b = i[index], j[index]
            records = {'actors': [self.names[a], self.names[b]], 'pitch_deg': mid, 'neck_yaw_deg': neck_yaw,
                       'local_deg': list(local), 'samples_interval_deg': [low, high]}
            gap = self.gap(a, b)
            if not np.isfinite(gap):
                return dict(records, status='unknown', reason='invalid rigid mesh clearance')
            if gap < stats['sampled_gap_mm']:
                stats['sampled_gap_mm'] = gap
                stats['closest'] = records
            lower = gap - travel[index]
            bound = min(bound, lower)
            if gap < required_mm + 1e-6:
                witness = self.contacts(a, b)
                return dict(records, gap_mm=gap, witnesses_mm=witness[:4].tolist())
            if lower < required_mm:
                uncertain = True
        if not uncertain:
            stats['continuous_lower_bound_mm'] = min(stats['continuous_lower_bound_mm'], bound)
            return None
        if high - low <= ANGLE_RESOLUTION_DEG:
            return {'status': 'unknown', 'reason': 'pitch interval below resolvable clearance',
                    'samples_interval_deg': [low, high], 'local_deg': list(local), 'neck_yaw_deg': neck_yaw}
        for new_low, new_high in ((low, mid), (mid, high)):
            failure = self.pitch_interval(pairs, new_low, new_high, local, neck_yaw, required_mm, stats)
            if failure:
                return failure
        return None


def validate_spec(rig, spec):
    powered = np.asarray(spec['powered_deg'], dtype=float)
    if powered.shape != (2,) or not np.isfinite(powered).all() or not powered[0] < 0 < powered[1]:
        raise ValueError('invalid powered pitch limits')
    travel = released_overshoot_by_sign(spec['released_overshoot_deg'])
    gap = float(spec['required_gap_mm'])
    if not np.isfinite(gap) or gap < 0:
        raise ValueError('invalid stop evaluation allowance')
    stops = spec['stops']
    if not stops or {row['direction'] for row in stops} != {-1, 1}:
        raise ValueError('both signed pitch stops are required')
    if len({row['id'] for row in stops}) != len(stops):
        raise ValueError('neck pitch stop ids must be unique')
    if rig.link is not None:
        lower_pin, link = LINK_LOWER_MATE
        roles = {lower_pin: 'pan', link: LINK_MOTION, LINK_UPPER_MATE[1]: 'head'}
        if any(rig.kinds[rig.ids[name]] != kind for name, kind in roles.items()):
            raise ValueError('slotted-link pin/body motion assignment differs from physical attachment')
        bore, pin, slot = (float(rig.link[key]) for key in ('bore_diameter_mm', 'pin_diameter_mm', 'slot_width_mm'))
        ends = np.asarray(rig.link['slot_centers_mm'], dtype=float)
        centered = np.linalg.norm(rig.pin_vector(0.))
        if (not np.isfinite([bore, pin, slot]).all() or not 0. < pin < min(bore, slot)
                or ends.shape != (2,) or not np.isfinite(ends).all() or not 0. < ends[0] < centered < ends[1]):
            raise ValueError('invalid lower bore or upper slot center dimensions')
        for row in stops:
            sign = row['direction']
            target_end = ends[(sign + 1) // 2] + sign * (slot - pin) / 2
            pin_distance = np.linalg.norm(rig.pin_vector(float(row['nominal_deg'])))
            if tuple(row['actors']) != LINK_UPPER_MATE or abs(pin_distance - target_end) > .01:
                raise ValueError('declared stop does not locate the upper pin at its signed slot end')
    for row in stops:
        fixed, moving = (rig.ids[name] for name in row['actors'])
        if rig.kinds[fixed] not in ('pan', LINK_MOTION) or rig.kinds[moving] != 'head':
            raise ValueError('stop actors must be in pan/link and head order')
        window = np.asarray(row['search_window_deg'], dtype=float) * row['direction']
        patch = np.asarray(row['patch_bounds_mm'], dtype=float)
        if (window.shape != (2,) or not np.isfinite(window).all()
                or window[0] <= abs(powered[(row['direction'] + 1) // 2]) or window[1] <= window[0]):
            raise ValueError('invalid signed stop window')
        if patch.shape != (2, 3) or not np.isfinite(patch).all() or np.any(patch[0] >= patch[1]):
            raise ValueError('invalid stationary stop contact patch')
    return powered, travel, gap


def witness_stop(rig, row, overtravel):
    sign = row['direction']
    begin, end = np.array(row['search_window_deg']) * sign
    pair = np.array([[rig.ids[name]] for name in row['actors']], dtype=int)
    stats = {'pitch_intervals': 0, 'sampled_gap_mm': GAP_SEARCH_MM, 'continuous_lower_bound_mm': GAP_SEARCH_MM}
    premature = rig.pitch_interval(pair, *sorted((0., sign * begin)), (0., 0., 0., 0.), 0., 0., stats)
    if premature:
        return dict(premature, status=premature.get('status', 'fail'), reason='contact before signed stop window')
    xs = np.linspace(begin, end, int(np.ceil((end - begin) / SEARCH_STEP_DEG)) + 1)
    for lo, hi in zip(xs, xs[1:]):
        if len(rig.stop_contact(row, sign * hi)):
            break
    else:
        return {'status': 'fail', 'reason': 'no solid contact seen in the signed stop window'}
    while hi - lo > ANGLE_RESOLUTION_DEG:
        mid = (lo + hi) / 2
        if len(rig.stop_contact(row, sign * mid)):
            hi = mid
        else:
            lo = mid
    patch = np.array(row['patch_bounds_mm'])
    fixed_mesh, moving_mesh = (rig.meshes[rig.ids[name]] for name in row['actors'])
    fixed, moving = manifold(fixed_mesh), manifold(moving_mesh)
    boundary = md.Manifold.cube(patch[1] - patch[0]).translate(patch[0])

    def penetration(q):
        _, tx = rig.stop_transforms(row, sign * q)
        return fixed ^ moving.transform(tx[:3, :])

    # Triangle collision witnesses can lie at the end of the long pin. Locate the
    # contacting solids just inside the crossing instead, in the anchor's neutral frame.
    probe = hi + .01
    first = penetration(probe)
    if first.is_empty() or first.volume() < 1e-6:
        return {'status': 'unknown', 'reason': 'no solid overlap immediately past the witnessed crossing',
                'pitch_deg': sign * hi}
    bounds = np.asarray(first.bounding_box()).reshape(2, 3)
    if np.any(bounds[0] < patch[0]) or np.any(bounds[1] > patch[1]):
        return {'status': 'fail', 'reason': 'first overlap outside the intended stop face',
                'pitch_deg': sign * hi, 'witness_bounds_mm': bounds.tolist()}
    for q in np.linspace(hi, hi + overtravel, int(np.ceil(overtravel / SEARCH_STEP_DEG)) + 1):
        overlap = penetration(q)
        outside = (overlap - boundary).volume()
        if outside > .005:
            return {'status': 'fail', 'reason': 'stop actor overlap outside the intended stop patch',
                    'pitch_deg': sign * q, 'overlap_outside_mm3': outside}
    fields = {key: row[key] for key in ('id', 'label', 'stage', 'actors')}
    head_transform = rotation(sign * hi, (1, 0, 0), NECK_PIVOT)
    anchor, _ = rig.stop_transforms(row, sign * hi)
    return dict(fields, status='pass', first_contact_deg=sign * hi, free_deg=sign * lo,
                center_mm=bounds.mean(axis=0).tolist(), witness_probe_deg=sign * probe,
                witness_bounds_mm=bounds.tolist(),
                head_from_neutral=head_transform.tolist(), anchor_from_neutral=anchor.tolist())


def local_cases(active_axes, jaw_open, jaw_released):
    samples = (tuple(np.arange(-8., 8.1, 2.)), (-20., 0., 20.), (0., 45., 90.),
               tuple(dict.fromkeys((0., jaw_open / 2, jaw_open, (jaw_open + jaw_released) / 2, jaw_released))))
    return product(*(axis if i in active_axes else (0.,) for i, axis in enumerate(samples, 1)))


def calibrated_link_stop_interval(rig, nominal, span_tolerance):
    """Convert a finished slot/pivot span error into pitch about the installed axes."""
    def span(pitch):
        return float(np.linalg.norm(rig.pin_vector(pitch)))

    target = span(nominal)
    interval = []
    for extent in (target - span_tolerance, target + span_tolerance):
        lo, hi = nominal - 2., nominal + 2.
        if not span(lo) < extent < span(hi):
            raise ValueError('cannot bracket calibrated stop tolerance over the pivot trajectory')
        while hi - lo > ANGLE_RESOLUTION_DEG / 4:
            mid = (lo + hi) / 2
            if span(mid) < extent:
                lo = mid
            else:
                hi = mid
        interval.append(lo if len(interval) == 0 else hi)
    return interval


def check(cad, jaw_released_deg=None):
    rig = Neck(cad)
    motion = rig.layout['motion_geometry']
    spec = rig.spec
    powered, overtravel, gap = validate_spec(rig, spec)
    guard, ticks, drift, firmware_sha = encoder_feedback_limits()
    if np.any(np.abs(powered - np.array(ticks) * 360 / 4096) > 360 / 4096):
        raise ValueError('CAD command pitch limits differ from the firmware encoder travel')
    span_tolerance = 0.
    if rig.link is not None:
        lower_play = (rig.link['bore_diameter_mm'] - rig.link['pin_diameter_mm']) / 2
        span_tolerance = SLOT_FINISH_TOLERANCE_MM + lower_play
    locations = []
    for row in spec['stops']:
        extra = 0.
        if span_tolerance:
            nominal_interval = calibrated_link_stop_interval(rig, row['nominal_deg'], span_tolerance)
            extra = max(abs(bound - row['nominal_deg']) for bound in nominal_interval)
        mark = witness_stop(rig, row, overtravel[row['direction']] + extra)
        locations.append(mark)
    for mark in locations:
        if mark['status'] == 'pass':
            sign = np.sign(mark['first_contact_deg'])
            index = 0 if sign < 0 else 1
            endpoint = powered[index]
            mark['margin_from_powered_limit_deg'] = sign * (mark['free_deg'] - endpoint)
            mark['margin_from_feedback_limit_deg'] = sign * (mark['free_deg'] - guard[index])
            if span_tolerance:
                bracket = sorted((mark['free_deg'], mark['first_contact_deg']))
                mark['calibrated_contact_interval_deg'] = [
                    calibrated_link_stop_interval(rig, angle, span_tolerance)[side]
                    for side, angle in enumerate(bracket)]
                earliest_end = mark['calibrated_contact_interval_deg'][1 - index]
                mark['calibrated_margin_from_feedback_limit_deg'] = sign * (earliest_end - guard[index])
    report = {'cad_sha256': rig.cad_hash, 'status': 'pass', 'powered_pitch_deg': powered.tolist(),
              'powered_feedback_pitch_deg': guard.tolist(), 'firmware_sha256': firmware_sha,
              'command_ticks': ticks, 'feedback_tolerance_ticks': drift,
              'required_nonstop_gap_mm': gap, 'released_overshoot_deg': spec['released_overshoot_deg'],
              'locations': locations,
              'pitch_bearing_mates': [list(pair) for pair in sorted(BEARING_MATES)],
              'pitch_drive_mate': list(DRIVE_MATE), 'coverage': 'rigid pitch with sampled yaw, gaze, blink and jaw',
              'local_pose_order': ['eye_pitch', 'eye_yaw', 'blink', 'jaw'],
              'issues': [row for row in locations if row['status'] != 'pass']}
    if rig.link is not None:
        report['lower_link_pivot'] = {'actors': list(LINK_LOWER_MATE), 'required_gap_mm': LOWER_PIVOT_GAP_MM,
                                      'nominal_radial_clearance_mm': lower_play}
        report['calibrated_span_tolerance_mm'] = {'finished_slot_end': SLOT_FINISH_TOLERANCE_MM,
                                                   'lower_pivot_radial_play': lower_play, 'combined': span_tolerance}
        report['calibrated_scope'] = 'Finish both slot ends to the spacing measured on the assembled pivots.'
    if report['issues']:
        report['status'] = 'fail' if any(row['status'] == 'fail' for row in report['issues']) else 'unknown'
        return report
    if any(mark.get('calibrated_margin_from_feedback_limit_deg', mark['margin_from_feedback_limit_deg']) <= 0
           for mark in locations):
        report['status'] = 'fail'
        report['issues'].append({'reason': 'physical stop is inside the permitted encoder feedback range'})
        return report

    released = [max(max(map(abs, row.get('calibrated_contact_interval_deg', [row['first_contact_deg']])))
                    for row in locations if np.sign(row['first_contact_deg']) == sign) + overtravel[sign]
                for sign in (-1, 1)]
    jaw = motion['jaw_stop']
    jaw_powered = float(jaw['software_open_deg'])
    recorded_jaw_release = float(jaw.get('released_clearance_deg', B21_RELEASED_JAW_DEG))
    jaw_released = recorded_jaw_release if jaw_released_deg is None else float(jaw_released_deg)
    if not np.isfinite([jaw_powered, jaw_released]).all() or not 0. < jaw_powered <= jaw_released:
        raise ValueError('invalid released jaw clearance angle')
    if jaw_released < recorded_jaw_release:
        raise ValueError('requested jaw angle would narrow the recorded released envelope')
    report['recorded_released_jaw_deg'] = recorded_jaw_release
    if jaw_released_deg is not None:
        report['requested_released_jaw_deg'] = jaw_released
    pair_groups = {sign: rig.cross_pair_groups(spec['stops'], sign) for sign in (-1, 1)}
    for phase, limits, jaw_range in (
        ('powered', guard, (jaw_powered, jaw_powered)),
        ('released', (-released[0], released[1]), (jaw_powered, jaw_released)),
    ):
        print(f'{phase}: checking rigid parts across {limits[0]:.3f}° to {limits[1]:.3f}°', flush=True)
        stats = {'pitch_intervals': 0, 'sampled_gap_mm': GAP_SEARCH_MM, 'cross_pair_signs': 0,
                 'continuous_lower_bound_mm': GAP_SEARCH_MM, 'joint_cases': 0, 'pitch_deg': list(limits),
                 'jaw_deg': [0., jaw_range[1]]}
        if rig.link is not None:
            stats['lower_link_pivot'] = {'pitch_intervals': 0, 'sampled_gap_mm': GAP_SEARCH_MM,
                                         'continuous_lower_bound_mm': GAP_SEARCH_MM}
        report[phase] = stats
        for sign, end in zip((-1, 1), limits, strict=True):
            for (check_base, active_axes, optional, lower_mate), pairs in pair_groups[sign].items():
                stats['cross_pair_signs'] += pairs.shape[1]
                yaws = (-60., -30., 0., 30., 60.) if check_base else (0.,)
                group_stats = stats['lower_link_pivot'] if lower_mate else stats
                threshold = LOWER_PIVOT_GAP_MM if lower_mate else gap
                for yaw, local in product(yaws, local_cases(active_axes, *jaw_range)):
                    stats['joint_cases'] += 1
                    for low, high in ((end, end), tuple(sorted((0., end)))):
                        failure = rig.pitch_interval(pairs, low, high, local, yaw, threshold, group_stats)
                        if failure:
                            report['issues'].append(dict(failure, phase=phase, optional_ballast=optional))
                            report['status'] = failure.get('status', 'fail')
                            return report
    return report


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--jaw-released-deg', type=float,
                        help='check an extended released jaw bound from the coupled load analysis')
    args = parser.parse_args()
    try:
        report = check(args.cad, args.jaw_released_deg)
    except (ValueError, KeyError, FileNotFoundError, TypeError, IndexError) as error:
        report = {'status': 'unknown', 'issues': [{'reason': str(error)}]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(report['status'], report['issues'])
    raise SystemExit(0 if report['status'] == 'pass' else 1)
