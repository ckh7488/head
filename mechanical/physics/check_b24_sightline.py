"""Check the direct-drive eye height scene at the firmware pitch endpoints."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from math import atan2, degrees, radians, tan
from pathlib import Path
import re
import tomllib

import numpy as np
import trimesh
from scipy.optimize import brentq

from check_b22_neck import FIRMWARE, NECK_PIVOT, encoder_feedback_limits
from check_head import rotation


ROOT = Path(__file__).resolve().parents[2]
PUPILS = {'Part031': (-34., -39., 119.), 'Part035': (34., -39., 119.)}
OPAQUE = ('Part066', 'Part073', 'Part076', 'Part077', 'Part078', 'Part079', 'Part080')


def elevation(vector):
    return degrees(atan2(vector[2], np.linalg.norm(vector[:2])))


def xyz(transform, point):
    return transform[:3, :3]@point + transform[:3, 3]


def check(cad):
    layout = json.loads((cad/'cad_parts.json').read_text())
    with (ROOT/'spec/criteria.toml').open('rb') as source:
        specs = tomllib.load(source)
    scene = specs['S02_look_up']
    if scene['base_tilt_deg'] != 0.:
        raise ValueError('This witness requires the agreed level pedestal')
    _, pitch_ticks, drift, firmware = encoder_feedback_limits()
    neck = pitch_ticks[0] * 360/4096
    calibration = re.search(r'eyeCalibrationTicks\[\]\s*=\s*\{[^,]+,\s*4096u\*(\d+)u/360u-positionTolerance',
                            FIRMWARE.read_text())
    if calibration is None:
        raise ValueError('Missing firmware eye-pitch calibration limit')
    eye_ticks = 4096 * int(calibration[1]) // 360 - drift
    eye_deg = eye_ticks * 360/4096
    horizon = np.array(layout['motion_geometry']['eye_pitch']['cradle_axis_mm'])
    target = horizon + (0., -1000*scene['distance_m'],
                        1000*(scene['person_eye_height_m']-scene['head_height_m']))
    pose = rotation(neck, (1., 0., 0.), NECK_PIVOT)
    local_target = xyz(np.linalg.inv(pose), target)
    shapes = {}
    for name in (*PUPILS, 'Part068', *OPAQUE):
        path = cad/'world'/f'{name}.stl'
        if sha256(path.read_bytes()).hexdigest() != layout['world_sha256'][name]:
            raise ValueError(f'Unexpected world STL for {name}')
        shapes[name] = trimesh.load_mesh(path)

    def obstruction(origin, goal):
        ray = goal-origin
        length = np.linalg.norm(ray)
        direction = ray/length
        hits = []
        for name in OPAQUE:
            points, _, _ = shapes[name].ray.intersects_location([origin], [direction])
            if any(0.01 < t < length for t in (points-origin)@direction):
                hits.append(name)
        return hits

    eyes = {name: np.asarray([row['center'] for row in layout['parts']
                              if row['name'] == name for row in row['solids']]).mean(axis=0)
            for name in PUPILS}
    lens = shapes['Part068'].bounds
    camera = (lens[0]+lens[1])/2
    camera[1] = lens[0, 1]
    camera_direction = local_target-camera
    camera_hfov = specs['S01_walk_by']['camera_hfov_deg']
    camera_edge = -camera_direction[1]*tan(radians(camera_hfov/2))
    camera_in_frame = abs(camera_direction[0]) < camera_edge and abs(camera_direction[2]) < camera_edge*720/1280

    def iris(name, gaze):
        r = rotation(gaze, (1., 0., 0.), horizon)
        pupil = xyz(pose@r, eyes[name])
        forward = (pose@r)[:3, :3] @ (eyes[name]-PUPILS[name])
        required = elevation(target-pupil)
        return pupil, required, elevation(forward)

    rows = []
    for name in PUPILS:
        _, required, maximum = iris(name, -eye_deg)

        def sight_error(angle):
            _, target_elevation, iris_elevation = iris(name, angle)
            return iris_elevation - target_elevation

        solution, contacts = None, []
        if sight_error(-eye_deg) * sight_error(eye_deg) <= 0:
            solution = brentq(sight_error, -eye_deg, eye_deg)
            pupil, _, _ = iris(name, solution)
            contacts = obstruction(xyz(np.linalg.inv(pose), pupil), local_target)
        rows.append(dict(part=name, required_elevation_deg=required, max_elevation_deg=maximum,
                         eye_pitch_solution_deg=solution,
                         opaque_contacts=contacts))
    camera_contacts = obstruction(camera, local_target)
    passed = camera_in_frame and not camera_contacts and all(
        row['eye_pitch_solution_deg'] is not None and not row['opaque_contacts'] for row in rows)
    return {'cad_sha256': layout['source_sha256'], 'firmware_sha256': firmware,
            'status': 'pass' if passed else 'fail', 'scene': scene, 'camera_hfov_deg': camera_hfov,
            'neck_pitch_deg': neck,
            'eye_pitch_limit_deg': eye_deg, 'target_mm': target.tolist(),
            'camera_in_frame': bool(camera_in_frame), 'camera_opaque_contacts': camera_contacts,
            'pupils': rows, 'scope': 'Direct sightlines and vertical optical alignment. Installation remains P05.'}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    result = check(args.cad)
    args.report.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(result['status'], result['pupils'])
    raise SystemExit(0 if result['status'] == 'pass' else 1)
