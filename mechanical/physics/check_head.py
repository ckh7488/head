"""Sweep the upper assembly through relative eye, lid, neck and jaw poses."""

from argparse import ArgumentParser
from itertools import product
from math import atan2, cos, radians, sin
from pathlib import Path
import json

import fcl
import numpy as np
import trimesh as tr
from trimesh.collision import mesh_to_BVH

AXES_BY_MOTION = {'fixed':(), 'head':(), 'pan':(0,), 'tilt':(1,), 'tilt_link':(1,), 'tilt_horn':(1,), 'look1':(1,2),
       'look2':(1,2), 'look_link':(1,2), 'look_horn':(1,2), 'lid1':(3,), 'lid2':(3,),
       'blink_motor_horn':(3,), 'blink_shaft_crank':(3,), 'blink_drive_link':(3,), 'blink_lid_link':(3,), 'jaw':(4,),
       'pitch_link':(0,)}

PAIRS_BY_INTERFACE = {
    'links':(['Part057','Part060'],['Part011','Part012','Part013','Part014','Part015','Part016','Part019','Part024','Part025','Part027','Part029','Part033','Part041','Part042','Part044','Part048','Part063','Part064','Part073','Part074','Part076','Part077','Part078','Part079','Jaw_36_left_jaw_servo_stay','Jaw_37_right_jaw_bearing_stay','Jaw_38_left_jaw_drive_arm','Jaw_39_right_jaw_pivot_arm','Jaw_30_moving_jaw']),
    'blink':(['Part045','Part046','Part047','Part048','Part053','Part054','Part055','Part056','Part063'],
             ['Part019','Part041','Part042','Part043','Part044','Part045','Part046','Part047','Part048','Part053','Part054','Part055','Part056','Part063','Part064','Part073','Part074']),
    'lids':(['Part078','Part079'],['Part025','Part027','Part029','Part030','Part031','Part033','Part034','Part035','Part037','Part073','Part074','Part076','Part077']),
    'gaze':(['Part024','Part029','Part033','Part037','Part038','Part039','Part040','Part041','Part042','Part043','Part044','Part064'],
            ['Part010','Part011','Part013','Part015','Part016','Part018','Part019','Part024','Part025','Part027','Part029','Part033','Part037','Part038','Part039','Part040','Part041','Part042','Part043','Part044','Part045','Part057','Part060','Part063','Part064','Part066','Part067','Part073','Part074','Part076','Part077','Part078','Part079','Jaw_36_left_jaw_servo_stay','Jaw_37_right_jaw_bearing_stay','Jaw_XL330_M288_Jaw']),
    'jaw':(['Jaw_30_moving_jaw','Jaw_38_left_jaw_drive_arm','Jaw_39_right_jaw_pivot_arm'],['Part011','Part013','Part015','Part016','Part018','Part024','Part025','Part027','Part045','Part073','Part074','Jaw_36_left_jaw_servo_stay','Jaw_37_right_jaw_bearing_stay','Jaw_XL330_M288_Jaw']),
    'neck':(['Part010','Part011','Part018'],['Part019','Part024','Part045','Part048','Part063','Part065','Part066','Part067','Part073','Part074','Jaw_30_moving_jaw','Jaw_36_left_jaw_servo_stay','Jaw_37_right_jaw_bearing_stay','Jaw_XL330_M288_Jaw'])
}
BALLAST_PAIRS = (
    ['BallastTray', 'BallastCover', 'BallastStack', 'BallastLeftStud', 'BallastRightStud'],
    ['Part011', 'Part012', 'Part014', 'Part016', 'Part018', 'Part019',
     'Part024', 'Part041', 'Part045', 'Part063', 'Part073', 'Part074', 'Jaw_30_moving_jaw',
     'BallastTray', 'BallastCover', 'BallastStack', 'BallastLeftStud', 'BallastRightStud'],
)

MATES = set(tuple(sorted(a.split('/'))) for a in '''Part045/Part046 Part046/Part063 Part047/Part045 Part047/Part056 Part048/Part050 Part048/Part052 Part048/Part053 Part048/Part054 Part048/Part055 Part048/Part063 Part063/Part050 Part063/Part052 Part053/Part057 Part054/Part056 Part055/Part060 Part057/Part078 Part060/Part079 Part038/Part039 Part041/Part042 Part038/Part040 Part041/Part043 Part024/Part039 Part042/Part064 Part043/Part044 Part019/Part064 Part019/Part025 Part019/Part027 Part019/Part013 Part019/Part015 Part010/Part011 Part011/Part018 Part015/Part016 Part016/Part018 Part029/Part037 Part033/Part037 Part037/Part040 Jaw_30_moving_jaw/Jaw_38_left_jaw_drive_arm Jaw_30_moving_jaw/Jaw_39_right_jaw_pivot_arm Jaw_38_left_jaw_drive_arm/Jaw_XL330_M288_Jaw'''.split())
MATES.update({('BallastTray', 'Part019'), ('BallastStack', 'BallastTray'), ('BallastCover', 'BallastStack')})
ANGLES = (
    (-15., -10., -5., 0., 3., 6.),
    (-8., -4., 0., 4., 8.),
    (-20., -10., 0., 10., 20.),
    (-1., *range(0, 91, 5), 91.),
    (0., 3., 7., 10., 13.),
)

MEASURE_GAP = {
    ('Part024', 'Part057'), ('Part024', 'Part060'),
    ('Part041', 'Part060'), ('Part057', 'Part073'), ('Part060', 'Part073'),
    ('Part073', 'Part078'), ('Part073', 'Part079'), ('Part076', 'Part078'), ('Part077', 'Part079'),
    ('BallastTray', 'Part074'), ('BallastCover', 'Part074'), ('BallastStack', 'Part074'),
}


def sweep_angles(layout, jaw_limit=None, pitch_range=None):
    geometry = layout['motion_geometry']
    angles = list(ANGLES)
    stop = geometry.get('jaw_stop')
    if jaw_limit is None and stop is not None:
        jaw_limit = float(stop['verified_clear_deg'])
    if jaw_limit is not None:
        angles[-1] = tuple(np.linspace(0., jaw_limit, len(ANGLES[-1])))
    pitch_stop = geometry.get('pitch_stop')
    if pitch_range is None and pitch_stop is not None:
        pitch_range = pitch_stop['powered_deg']
    if pitch_range is not None:
        low, high = pitch_range
        angles[0] = (low, *ANGLES[0][1:-1], high)
    return angles


def translation(offset):
    matrix = np.eye(4)
    matrix[:3, 3] = offset
    return matrix


def rotation(angle, axis, pivot):
    return tr.transformations.rotation_matrix(radians(angle), axis, pivot)


def pitch_link_pose(pitch, layout):
    """Rotate the steel link about its fixed pivot so the head pin stays on its slot axis."""
    link = layout['motion_geometry']['pitch_stop']['link']
    lower = np.asarray(link['pan_pin_mm'])
    upper = np.asarray(link['head_pin_mm'])
    moved = tr.transform_points([upper], rotation(pitch, (1, 0, 0), (0, 0, 112)))[0]
    y0, z0 = (upper-lower)[1:]
    y1, z1 = (moved-lower)[1:]
    angle = atan2(y0*z1-z0*y1, y0*y1+z0*z1)
    return tr.transformations.rotation_matrix(angle, (1, 0, 0), lower)


def offset(angle, phase, radius):
    start = radians(phase)
    end = radians(angle+phase)
    return radius*(cos(end)-cos(start)), radius*(sin(end)-sin(start))


def pose(kind, angles, layout):
    neck, eye_pitch, eye_yaw, blink, jaw = angles
    x_axis, z_axis = (1, 0, 0), (0, 0, 1)
    rig = layout['motion_geometry']
    eye_yaw_rig = rig['eye_yaw']
    eye_pitch_rig = rig.get('eye_pitch', {})
    eye_pivot = eye_pitch_rig.get('cradle_axis_mm', (0, -39, 119))
    if kind == 'pan':
        return rotation(-neck, x_axis, (0, 0, 112))
    if kind == 'pitch_link':
        return rotation(-neck, x_axis, (0, 0, 112)) @ pitch_link_pose(neck, layout)
    if kind == 'jaw':
        return rotation(jaw, x_axis, layout['jaw_pivot_mm'])
    if kind in ('look1', 'look2', 'look_horn'):
        pivot = {'look1': (-34, -39, 119), 'look2': (34, -39, 119),
                 'look_horn': eye_yaw_rig['pivot_mm']}[kind]
        return rotation(eye_pitch, x_axis, eye_pivot) @ rotation(eye_yaw, z_axis, pivot)
    if kind == 'look_link':
        dy, dx = offset(eye_yaw, 0., eye_yaw_rig['radius_mm'])
        return rotation(eye_pitch, x_axis, eye_pivot) @ translation((-dx, dy, 0.))
    if kind == 'tilt':
        return rotation(eye_pitch, x_axis, eye_pivot)
    if kind == 'tilt_horn':
        pivot = eye_pitch_rig.get('servo_axis_mm', (58.65, 10., 151.))
        return rotation(eye_pitch, x_axis, pivot)
    if kind == 'tilt_link':
        phase = eye_pitch_rig.get('phase_deg', 0.)
        radius = eye_pitch_rig.get('crank_radius_mm', 10.)
        return translation((0., *offset(eye_pitch, phase, radius)))
    mechanism = rig['blink']
    pivots = {'lid1': eye_pivot, 'lid2': eye_pivot,
              'blink_motor_horn': (0., *mechanism['servo_yz_mm']),
              'blink_shaft_crank': (0., *mechanism['shaft_yz_mm'])}
    if kind in pivots:
        return rotation(blink, x_axis, pivots[kind])
    if kind in ('blink_lid_link', 'blink_drive_link'):
        radius = mechanism['lid_radius_mm' if kind == 'blink_lid_link' else 'radius_mm']
        return translation((0., *offset(blink, mechanism['phase_deg'], radius)))
    return np.eye(4)


def sweep(directory, *, jaw_limit=None, pitch_range=None):
    layout = json.loads((directory/'cad_parts.json').read_text())
    sampled_angles = sweep_angles(layout, jaw_limit, pitch_range)
    kinds = layout['world_motion']
    pairs = dict(PAIRS_BY_INTERFACE)
    if 'BallastTray' in kinds:
        pairs['ballast'] = BALLAST_PAIRS
    names = set(name for pair_lists in pairs.values() for names in pair_lists for name in names)
    meshes = {name: tr.load_mesh(directory/'world'/f'{name}.stl') for name in names}
    objects = {name: fcl.CollisionObject(mesh_to_BVH(mesh)) for name, mesh in meshes.items()}
    request = fcl.CollisionRequest(num_max_contacts=1)
    visited = set()
    clearances = {}
    collisions = []
    samples = 0
    for interface, (first, second) in pairs.items():
        for a, b in product(first, second):
            pair = tuple(sorted((a, b)))
            if a == b or pair in MATES or pair in visited:
                continue
            visited.add(pair)
            mode_a, mode_b = kinds[a], kinds[b]
            if interface in ('gaze', 'neck') and mode_a == mode_b != 'head':
                continue
            axes = sorted(set(AXES_BY_MOTION[mode_a]) | set(AXES_BY_MOTION[mode_b])) if mode_a != mode_b else []
            x, y = objects[a], objects[b]
            x.setTransform(fcl.Transform())
            measure = pair in MEASURE_GAP
            best = float('inf')
            for values in product(*(sampled_angles[i] for i in axes)):
                angles = np.zeros(len(ANGLES))
                angles[axes] = values
                tx = np.linalg.solve(pose(mode_a, angles, layout), pose(mode_b, angles, layout))
                y.setTransform(fcl.Transform(tx[:3, :3].copy(), tx[:3, 3].copy()))
                samples += 1
                hit = fcl.collide(x, y, request, fcl.CollisionResult())
                if not hit:
                    if measure:
                        best = min(best, fcl.distance(x, y, fcl.DistanceRequest(), fcl.DistanceResult()))
                    continue
                mesh_a, mesh_b = meshes[a], meshes[b]
                if mesh_a.is_volume and mesh_b.is_volume:
                    cut = tr.boolean.intersection([mesh_a, mesh_b.copy().apply_transform(tx)],
                                                   engine='manifold', check_volume=False)
                    overlap = float(max(0., cut.volume))
                    if overlap <= .01:
                        continue
                else:
                    overlap = None
                collisions.append({'parts': [a, b], 'angles_deg': angles.tolist(), 'overlap_mm3': overlap})
                break
            if measure and best < float('inf'):
                clearances[' / '.join(pair)] = round(float(best), 3)
    return {'cad_sha256': layout['source_sha256'], 'pose_samples': samples, 'pairs': len(visited),
            'clearance_mm': clearances, 'collisions': collisions}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--jaw-limit', type=float)
    parser.add_argument('--pitch-range', type=float, nargs=2, metavar=('LOW', 'HIGH'))
    args = parser.parse_args()
    result = sweep(args.cad, jaw_limit=args.jaw_limit, pitch_range=args.pitch_range)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2))
    print(f"{result['pose_samples']} pose samples, {len(result['collisions'])} colliding pairs")
    for case in result['collisions']:
        print(case)
    if result['collisions']:
        raise SystemExit(1)
