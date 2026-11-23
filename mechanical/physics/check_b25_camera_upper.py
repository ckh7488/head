"""Reconstruct the B25 rotor-to-nasal Eaton span and replay its installed envelopes."""

from argparse import ArgumentParser
from hashlib import sha256
from itertools import product
import json
from math import ceil, radians
from pathlib import Path

import numpy as np
from scipy.special import comb
import trimesh

from wiring_check import Cable, Scene
from wiring_motion import arc_lengths, matrices, rotation, transform


TICK_DEG = 360. / 4096.
YAW_LIMIT = 648 * TICK_DEG
PITCH_RANGE = (-157 * TICK_DEG, 38 * TICK_DEG)
JAW_LIMIT = 78 * TICK_DEG
ENTRY = np.array((0., -36.75, -49.))
SPLICE = np.array((8.079443669120934, -23.7902088750033, 71.57523500099146))
SPLICE_DIRECTION = np.array((-.024480298769616667, -.3396116383167135, .940247121820635))
PITCH_PIVOT = (0., 0., 112.)
JAW_CAPSULE = 1.50 + 1.00 + .40
WITNESS_PAN_Z = -9.17
# The printed saddle bore begins 5.5 mm before the datum. The rounded
# clearance capsule can still reach into that fixed contact zone from outside it.
HEAD_ANCHOR_CONTACT_MM = 5.5 + JAW_CAPSULE
HEAD_ANCHOR_PARTS = {'Part065', 'CameraEatonHeadTie', 'CameraEatonHeadFixedLeg'}


def bezier(controls, samples):
    order = len(controls) - 1
    powers = np.arange(order + 1)
    t = samples[:, None]
    return (comb(order, powers) * t**powers * (1. - t)**powers[::-1]) @ controls


def rise(start, tangent, radius, angle_deg, step):
    angle = radians(angle_deg)
    angles = np.linspace(tangent, angle, ceil((angle - tangent) * radius / step) + 1)
    return start + np.c_[np.zeros(len(angles)), radius * (np.cos(tangent) - np.cos(angles)),
                        radius * (np.sin(angles) - np.sin(tangent))]


def crossing(step=.30):
    first = np.array((0., -36.75, -39.))
    line = np.linspace(ENTRY, first, ceil((first[2] - ENTRY[2]) / step) + 1)
    r40 = rise(first, 0., 40., 10., step)
    tangent = np.array((0., np.sin(radians(10.)), np.cos(radians(10.))))
    station = r40[-1] + (-30. - r40[-1, 2]) / tangent[2] * tangent
    line2 = np.linspace(r40[-1], station, ceil(np.linalg.norm(station - r40[-1]) / step) + 1)
    r18 = rise(station, radians(10.), 18.2, 20., step)
    return np.vstack((line[:-1], r40[:-1], line2[:-1], r18))


def upper_at(pitch, yaw, samples=401):
    """Return world centerline and sampled analytic bend radius at a neck pose, in mm."""
    pan = rotation(-yaw, (0., 0., 1.))
    head = pan @ rotation(pitch, (1., 0., 0.), PITCH_PIVOT)
    fixed = crossing()
    v = np.array((0., np.sin(radians(20.)), np.cos(radians(20.))))
    # Move the free span below and behind the jaw, keeping both fixed tangents.
    controls = np.array((fixed[-1], fixed[-1] + 24.173551855119346 * v,
                         (-1.3548701091919026, -2.828198991121784, 9.656740080636677),
                         (18.031151637023566, -18.649956698043063, 46.13767295367745)))
    terminal_controls = np.array((SPLICE - 28.06823152062983 * SPLICE_DIRECTION, SPLICE))
    controls = np.vstack((transform(controls, pan), transform(terminal_controls, head)))
    sample = np.linspace(0., 1., samples)
    points = bezier(controls, sample)
    tangent = bezier(5. * np.diff(controls, axis=0), sample)
    normal = bezier(20. * np.diff(controls, n=2, axis=0), sample)
    radii = np.linalg.norm(tangent, axis=1)**3 / np.maximum(np.linalg.norm(np.cross(tangent, normal), axis=1), 1.e-16)
    return np.vstack((transform(fixed[:-1], pan), points)), min(18.2, float(radii.min()))


def create_scene(cad, layout):
    scene = Scene.__new__(Scene)
    scene.groups = {}
    for name, mode in layout['world_motion'].items():
        if name.startswith(('Harness', 'HubRearClearance')) or name in ('RearLead3_1', 'EatonCableNeutral'):
            continue
        path = cad / 'world' / f'{name}.stl'
        if path.stat().st_size <= 84:
            continue
        if sha256(path.read_bytes()).hexdigest() != layout['world_sha256'][name]:
            raise ValueError(f'Unexpected mesh contents for {name}')
        mesh = trimesh.load_mesh(path, process=False)
        if mesh.bounds[0, 2] > 97. or mesh.bounds[1, 2] < -60.:
            continue
        scene.add(name, mode, mesh)
    return scene


def hits(scene, points, motion, radius, only):
    cable = Cable('USB-Camera', points, 3., 0., 0.)
    return scene.hits(cable, motion, radius - 1.5, only=only)


def moving_contacts(scene, points, motion, parts):
    free = hits(scene, points, motion, JAW_CAPSULE, parts - HEAD_ANCHOR_PARTS)
    # The cable, saddle and tie meet where the active span enters the fixed anchor.
    # Check these parts along the rest of the cable as ordinary solid obstacles.
    arc = arc_lengths(points)
    last = arc[-1] - HEAD_ANCHOR_CONTACT_MM
    index = np.searchsorted(arc, last, side='left')
    fraction = (last - arc[index-1]) / (arc[index] - arc[index-1])
    endpoint = points[index-1] + fraction * (points[index] - points[index-1])
    before_anchor = np.vstack((points[:index], endpoint))
    return free + hits(scene, before_anchor, motion, JAW_CAPSULE, parts & HEAD_ANCHOR_PARTS)


def continuous_jaw(scene, layout):
    jaw = set(scene.groups['jaw'])
    base_radius = JAW_CAPSULE + .045 + .005
    # The maximum distance from either joint axis to each control is under 170 mm.
    # Bezier convexity and the two angular half-steps bound every centerline displacement.
    lever = 170.
    stack = [(*PITCH_RANGE, 0., JAW_LIMIT)]
    certified, unresolved = [], []
    while stack:
        p0, p1, j0, j1 = stack.pop()
        p, j = (p0 + p1) / 2, (j0 + j1) / 2
        motion = matrices(layout, 0., p, 0., 0., j, 90.)
        points, _ = upper_at(p, 0.)
        pad = lever * radians((p1 - p0 + j1 - j0) / 2)
        contact = hits(scene, points, motion, base_radius + pad, jaw)
        if not contact:
            certified.append({'limits_deg': [p0, p1, j0, j1], 'motion_pad_mm': pad})
        elif max(p1 - p0, j1 - j0) < .0075:
            unresolved.append({'limits_deg': [p0, p1, j0, j1], 'contact': contact})
            if len(unresolved) >= 25:
                break
        elif p1 - p0 > j1 - j0:
            stack.extend(((p0, p, j0, j1), (p, p1, j0, j1)))
        else:
            stack.extend(((p0, p1, j0, j), (p0, p1, j, j1)))
    return {'base_capsule_mm': base_radius, 'rotation_lever_bound_mm': lever,
            'cells': certified, 'unresolved': unresolved, 'pending': len(stack)}


def jaw_endpoint_witness(scene, layout):
    pitch, yaw = PITCH_RANGE[-1], 0.
    motion = matrices(layout, yaw, pitch, 0., 0., JAW_LIMIT, 90.)
    points, _ = upper_at(pitch, yaw)
    lo, hi = 0., 7.
    for _ in range(16):
        mid = (lo + hi) / 2.
        if hits(scene, points, motion, mid, set(scene.groups['jaw'])):
            hi = mid
        else:
            lo = mid
    y = float(np.interp(WITNESS_PAN_Z, points[:, 2], points[:, 1]))
    return {'head_pitch_deg': pitch, 'jaw_from_cad_zero_ticks': round(JAW_LIMIT / TICK_DEG), 'centerline_gap_bracket_mm': [lo, hi],
            'worst_surface_gap_lower_mm': lo - 1.5 - .4 - .05,
            'centerline_y_at_pan_z_minus_9p17_mm': y}


def check(cad, report, paths, yaw_limit=YAW_LIMIT):
    layout = json.loads((cad / 'cad_parts.json').read_text())
    scene = create_scene(cad, layout)
    yaw_angles = np.linspace(-yaw_limit, yaw_limit, 17)
    pitch_angles = np.linspace(*PITCH_RANGE, 17)
    static = set(scene.groups.get('fixed', {})) | set(scene.groups.get('hatch', {}))
    co_rotating = set(name for mode, meshes in scene.groups.items() if mode not in ('fixed', 'hatch', 'jaw') for name in meshes)
    replay = []
    centers = {}
    for index, (yaw, pitch) in enumerate(product(yaw_angles, pitch_angles)):
        points, radius = upper_at(pitch, yaw)
        motion = matrices(layout, yaw, pitch, 0., 0., JAW_LIMIT, 90.)
        fixed_contacts = hits(scene, points, motion, JAW_CAPSULE, static)
        co_rotating_contacts = moving_contacts(scene, points, motion, co_rotating) if yaw == 0. else []
        replay.append({'pose_deg': [yaw, pitch], 'minimum_radius_mm': radius, 'fixed_contacts': fixed_contacts,
                       'co_rotating_contacts': co_rotating_contacts,
                       'length_mm': float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())})
        centers[f'case{index:03d}'] = points
    result = {'source_cad_sha256': layout['source_sha256'], 'od_mm': 3.0, 'sample_capsule_mm': JAW_CAPSULE,
              'head_anchor_contact_mm': HEAD_ANCHOR_CONTACT_MM,
              'rotor_datum_mm': ENTRY.tolist(), 'head_datum_mm': SPLICE.tolist(),
              'head_tangent_in_local_coordinates': SPLICE_DIRECTION.tolist(),
              'jaw_endpoint_witness': jaw_endpoint_witness(scene, layout),
              'jaw_continuous': continuous_jaw(scene, layout), 'neck_cases': replay}
    report.write_text(json.dumps(result, indent=2) + '\n')
    if paths:
        np.savez_compressed(paths, yaw_deg=yaw_angles, pitch_deg=pitch_angles, **centers)
    return result


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--paths', type=Path)
    parser.add_argument('--yaw-feedback-ticks', type=int, default=round(YAW_LIMIT/TICK_DEG))
    args = parser.parse_args()
    check(args.cad, args.report, args.paths, args.yaw_feedback_ticks*TICK_DEG)
