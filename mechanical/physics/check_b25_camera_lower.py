"""Replay the B25 Eaton lower span, rear U-return and length reserve."""

from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
import json

import numpy as np
import trimesh
from scipy.optimize import brentq

from check_b25_camera_upper import PITCH_RANGE, TICK_DEG, YAW_LIMIT, upper_at
from wiring_check import Cable, Scene
from wiring_motion import matrices, transform

RADIUS = 18.25
REAR_RADIUS = 19.
CUT_LENGTH = 550.
DATA = Path(__file__).resolve().parents[1] / 'revisions/b25/camera-r18-lower-controls.json'
REAR_ANCHOR_Y = 103.
MIN_U_STATION_Y = 106.
POSE_COUNT = 513

def lower_bight(anchor, datum, entry_radius=RADIUS):
    """Return a tangent lateral arc, straight segment and vertical quarter-turn."""
    dx, dy, rise = datum - anchor
    if rise < 18.1 or dy <= 0.:
        return None
    lateral = abs(dx)
    side = -1. if dx < 0. else 1.

    def tangent_error(angle):
        return (np.sin(angle) * (dy - entry_radius * np.sin(angle))
                - np.cos(angle) * (lateral - entry_radius * (1. - np.cos(angle))))

    if lateral > 1.e-9 and tangent_error(np.pi / 2.) <= 0.:
        return None
    angle = brentq(tangent_error, 0., np.pi / 2.) if lateral > 1.e-9 else 0.
    tangent = np.array((side * np.sin(angle), np.cos(angle), 0.))
    entry_angles = np.linspace(0., angle, max(2, int(np.ceil(entry_radius * angle / .75))))
    entry = anchor + entry_radius * np.c_[side * (1. - np.cos(entry_angles)),
                                          np.sin(entry_angles), np.zeros(len(entry_angles))]
    quarter_start = datum - rise * tangent - (0., 0., rise)
    straight_length = float(np.dot(tangent, quarter_start - entry[-1]))
    if straight_length < -1.e-7:
        return None
    straight = np.linspace(entry[-1], quarter_start, max(2, int(np.ceil(straight_length / .75))))
    t = np.linspace(0., np.pi / 2., int(np.ceil(rise * np.pi / 2. / .75)) + 1)
    vertical = quarter_start + rise * (np.sin(t[:, None]) * tangent
                                       + (1. - np.cos(t[:, None])) * np.array((0., 0., 1.)))
    points = np.vstack((entry[:-1], straight[:-1], vertical))
    unique = np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > 1.e-7]
    length = entry_radius * angle + straight_length + rise * np.pi / 2.
    return points[unique], length


def reserve_loop(at_y):
    top = np.array((58., REAR_ANCHOR_Y, -28.91788776547))
    bottom = top - (0., 0., 2*REAR_RADIUS)
    first, end = top.copy(), bottom.copy()
    first[1] = end[1] = at_y
    angles = np.linspace(0., np.pi, 110)
    arc = first + REAR_RADIUS*np.c_[np.zeros(len(angles)), np.sin(angles), np.cos(angles)-1.]
    return np.vstack((top, arc, bottom))


def scene(cad, layout):
    result = Scene.__new__(Scene)
    result.groups = {}
    excluded = ('Harness', 'HubRearClearance', 'Ballast', 'RearLead3', 'Camera', 'Eaton')
    for name, mode in layout['world_motion'].items():
        if name.startswith(excluded) or name in ('A4W8', 'A4W9') or mode not in ('fixed', 'pan', 'hatch'):
            continue
        path = cad/'world'/f'{name}.stl'
        if path.stat().st_size <= 84:
            continue
        if sha256(path.read_bytes()).hexdigest() != layout['world_sha256'][name]:
            raise ValueError(f'Mesh changed after CAD export: {name}')
        mesh = trimesh.load_mesh(path, process=False)
        if mesh.bounds[1, 2] >= -85. and mesh.bounds[0, 2] <= -44.:
            result.add(name,mode,mesh)
    return result


def check(cad, controls, yaw_limit=YAW_LIMIT):
    layout = json.loads((cad/'cad_parts.json').read_text())
    shells = scene(cad, layout)
    fixed = set(shells.groups['fixed']) | set(shells.groups.get('hatch', {}))
    pan = set(shells.groups['pan'])
    fixed_path = np.asarray(controls['fixed']['curve_mm'])
    angles = np.linspace(-yaw_limit, yaw_limit, POSE_COUNT)
    anchor = np.array(controls['anchor_mm'])
    heading = np.radians(controls['fixed']['heading_deg'])
    rotate = np.array(((np.cos(heading), np.sin(heading), 0.),
                       (-np.sin(heading), np.cos(heading), 0.), (0., 0., 1.)))
    lengths = []
    failed = []
    for yaw in angles:
        motion = matrices(layout, yaw)
        datum = transform([0., -36.75, controls['rotor_entry_z_mm']], motion['pan'])
        route = lower_bight(anchor @ rotate, datum @ rotate)
        if route is None:
            raise ValueError(f'No tangent bight at yaw {yaw:g}°')
        points, length = route
        wire = Cable('USB-Camera', points@rotate.T, 3., 0., 0.)
        stationary = Cable('USB-Camera', fixed_path, 3., 0., 0.)
        hits = (shells.hits(wire, motion, .23, only=fixed)
                + shells.hits(wire, motion, 1.42, only=pan)
                + shells.hits(stationary, motion, 1.42, only=pan))
        if hits:
            failed.append({'yaw_deg': float(yaw), 'contacts': hits})
        lengths.append(length)
    upper = [upper_at(p, 0.)[0] for p in np.linspace(*PITCH_RANGE, 129)]
    upper_lengths = [np.linalg.norm(np.diff(path, axis=0),axis=1).sum() for path in upper]
    fixed_length = np.linalg.norm(np.diff(fixed_path, axis=0),axis=1).sum()
    min_inner = fixed_length + min(lengths) + min(upper_lengths) - .2
    max_inner = fixed_length + max(lengths) + max(upper_lengths) + .2
    turn = np.pi*REAR_RADIUS
    reference = max_inner + turn + 2*(MIN_U_STATION_Y-REAR_ANCHOR_Y)
    return_y = [REAR_ANCHOR_Y+(CUT_LENGTH-len_ - turn)/2 for len_ in (max_inner,min_inner)]
    reserved = []
    for at_y in np.linspace(*return_y, 73):
        cable = Cable('USB-Camera', reserve_loop(at_y), 3., 0., 0.)
        reserved.extend(shells.hits(cable, matrices(layout), .23, only=fixed))
    return {
        'source_cad_sha256': layout['source_sha256'], 'yaw_samples': len(angles),
        'rear_return_samples': 73, 'length_allowance_mm': .2,
        'radii_mm': [controls['fixed']['radius_mm'],RADIUS,controls['vertical_radius_mm'],REAR_RADIUS],
        'cut_between_anchors_mm': CUT_LENGTH,'longest_reference_mm': reference,
        'reserve_percent': 100*(CUT_LENGTH/reference-1), 'return_center_y_mm': return_y,
        'max_rear_outer_y_mm': return_y[-1]+REAR_RADIUS+1.5,
        'moving_contacts': failed, 'rear_contacts': reserved,
        'fixed_contacts': shells.hits(stationary, matrices(layout), .23, only=fixed),
    }


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('exported_cad', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--controls',type=Path,default=DATA)
    parser.add_argument('--yaw-feedback-ticks', type=int, default=round(YAW_LIMIT/TICK_DEG))
    args=parser.parse_args()
    report=check(args.exported_cad,json.loads(args.controls.read_text()),args.yaw_feedback_ticks*TICK_DEG)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(bool(report['moving_contacts'] or report['rear_contacts'] or report['fixed_contacts']
                          or report['reserve_percent'] < 10))
