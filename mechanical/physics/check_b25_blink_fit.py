"""Check B25 blink fit against an export_cad.py --world directory."""

from argparse import ArgumentParser
from hashlib import sha256
from itertools import product
import json
from math import radians, sin
from pathlib import Path

import fcl
import numpy as np
import trimesh
from trimesh.collision import mesh_to_BVH

from blink_fea import elastic_linkage, measure
from check_b24_blink_shell import verify as verify_unloaded
from check_b24_loaded_blink_link import LIDS, LINKS, MODULUS_MPA, SHELL, digest, neutral_pins

POINT_LOAD_N = 1.
TOUCH_LEVER_MM = 16.6
DRAG_NM = .009
MESH_MM = .8
RADIAL_MM = .025
DIRECTIONS = 8
SHAFT_END_FLOAT_MM = .10
SHAFT_TILT_DEG = .48
UNLOADED_UPPER_DEG = (102., 96.4, 97.5)


def front_shell_clearance(cad, configuration, states):
    motion = configuration['motion_geometry']
    blink = motion['blink']
    hinge = np.array(motion['eye_pitch']['cradle_axis_mm'][1:])
    span = np.diff(blink['bearing_x_mm'])[0]
    rest = neutral_pins(configuration)
    rest_link = rest[1]-rest[0]
    rest_rotation = np.arctan2(rest_link[1], rest_link[0])

    actors, radius = {}, {}
    for name in (*LIDS, *LINKS, SHELL):
        mesh = trimesh.load_mesh(cad/'world'/f'{name}.stl')
        actors[name] = fcl.CollisionObject(mesh_to_BVH(mesh))
        if name != SHELL:
            anchor = hinge if name in LIDS else rest[0]
            radius[name] = np.linalg.norm(mesh.vertices[:, 1:]-anchor, axis=1).max()

    angles = 2*np.pi*np.arange(DIRECTIONS)/DIRECTIONS
    ring = np.column_stack((np.cos(angles), np.sin(angles)))
    options = RADIAL_MM*np.vstack((np.zeros((1, 2)), ring/2, ring))
    independent = np.array(list(product(options, repeat=2)))
    request = fcl.DistanceRequest(enable_nearest_points=True)
    witnesses = {}
    distance_queries = dict.fromkeys((*LIDS, *LINKS), 0)
    lid_min = np.full(2, np.inf)
    lid_max = np.full(2, -np.inf)
    shaft_tilt_max = 0.

    def distance(name, angle, anchor, delta):
        c, s = np.cos(angle), np.sin(angle)
        rotation = np.array([[1., 0., 0.], [0., c, -s], [0., s, c]])
        translation = np.r_[0., anchor-rotation[1:, 1:] @ anchor+delta]
        actors[name].setTransform(fcl.Transform(rotation, translation))
        result = fcl.DistanceResult()
        gap = fcl.distance(actors[name], actors[SHELL], request, result)
        distance_queries[name] += 1
        return gap, result

    # Sweeping from closure first gives a close witness for distance pruning.
    for state in reversed(states):
        force = np.array(state['loads'][:4]).reshape(2, 2)
        norm = np.linalg.norm(force, axis=1, keepdims=True)
        aligned = RADIAL_MM*np.divide(force, norm, out=np.zeros_like(force), where=norm > 0)
        # The independent grid starts with zero play at both bearings.
        offsets = np.concatenate((independent[:1], aligned[None], independent[1:]))
        centers = np.broadcast_to(state['centers'], (len(offsets), 4, 2)).copy()
        centers[:, :2] += offsets
        try:
            _, lids, pins = elastic_linkage(blink, hinge, state['angle'], centers)
        except ValueError as error:
            raise ValueError(f"Unreachable pose at {state['angle']}° with {state['torques']} N·m") from error
        lid_min = np.minimum(lid_min, lids.min(axis=0))
        lid_max = np.maximum(lid_max, lids.max(axis=0))
        tilt = np.arctan2(np.linalg.norm(centers[:, 1]-centers[:, 0], axis=1), span)
        shaft_tilt_max = max(shaft_tilt_max, float(np.degrees(tilt.max())))
        link_vector = pins[:, :, 1]-pins[:, :, 0]
        link_angles = np.arctan2(link_vector[:, :, 1], link_vector[:, :, 0])-rest_rotation

        for side, (lid, link) in enumerate(zip(LIDS, LINKS, strict=True)):
            poses = (
                (lid, np.radians(lids[:, side]), hinge, np.zeros((len(offsets), 2))),
                (link, link_angles[:, side], rest[0], pins[:, side, 0]-rest[0]),
            )
            for name, rotations, anchor, shifts in poses:
                best = witnesses.get(name, {'gap': np.inf})['gap']
                nominal, result = distance(name, rotations[0], anchor, shifts[0])
                if nominal < best:
                    best = nominal
                    witnesses[name] = witness(nominal, state, offsets[0], result)
                if best <= 0.:
                    continue

                # Point displacement bounds the distance change under a rigid transform.
                translation = np.linalg.norm(shifts-shifts[0], axis=1)
                rotation = 2*radius[name]*np.abs(np.sin((rotations-rotations[0])/2))
                displacement = translation+rotation
                order = np.argsort(-displacement[1:])+1
                for i in order:
                    if nominal-displacement[i] > best:
                        break
                    gap, result = distance(name, rotations[i], anchor, shifts[i])
                    if gap < best:
                        best = gap
                        witnesses[name] = witness(gap, state, offsets[i], result)

    return {
        'gaps': {f'{name}/{SHELL}': value for name, value in witnesses.items()},
        'q_range': dict(zip(LIDS, np.column_stack((lid_min, lid_max)).tolist(), strict=True)),
        'max_sampled_shaft_tilt_deg': shaft_tilt_max,
        'distance_queries': {f'{name}/{SHELL}': count for name, count in distance_queries.items()},
        'bearing_offset_pairs_per_load_and_angle': len(independent)+1,
    }


def witness(gap, state, offsets, result):
    return {'gap': gap, 'state': state, 'offsets': offsets.tolist(),
            'points': [None if p is None else p.tolist() for p in result.nearest_points]}


def verify(cad):
    configuration = json.loads((cad/'cad_parts.json').read_text())
    rig = configuration['motion_geometry']['blink']
    rail_step = cad/'blink_rail.step'
    step_data = rail_step.read_bytes().partition(b'\nDATA;\n')[2]
    if not step_data:
        raise ValueError('Could not identify the rail STEP data section')
    touch = DRAG_NM+POINT_LOAD_N*TOUCH_LEVER_MM/1000
    load_cases = [(sign*left, sign*right) for sign in (-1., 1.)
                  for left, right in ((touch, DRAG_NM), (DRAG_NM, touch), (DRAG_NM, DRAG_NM),
                                      (touch, 0.), (0., touch))]
    angles = np.r_[np.arange(0., 85., 2.), np.arange(850, 901)/10]
    _, states = measure(cad, rig, MESH_MM, modulus=MODULUS_MPA, link_angles=angles,
                        link_load_cases=load_cases, rail_states=True)
    loaded = front_shell_clearance(cad, configuration, states)
    print('Finished loaded front-shell samples. Checking unloaded clearances.', flush=True)
    unloaded = verify_unloaded(cad, *UNLOADED_UPPER_DEG)
    minimum = min(row['gap'] for row in loaded['gaps'].values())
    axial = SHAFT_END_FLOAT_MM+rig['lid_radius_mm']*sin(radians(SHAFT_TILT_DEG))
    residual = minimum-axial
    unloaded_minimum = min(row['continuous_min_mm'] for row in unloaded['rows'])
    passed = (residual > 0 and loaded['max_sampled_shaft_tilt_deg'] <= SHAFT_TILT_DEG
              and unloaded_minimum > 0)
    loaded.update({
        'command_samples_deg': angles.tolist(),
        'crank_torque_cases_Nm': load_cases,
        'point_load_N': POINT_LOAD_N,
        'point_load_lever_mm': TOUCH_LEVER_MM,
        'per_lid_drag_Nm': DRAG_NM,
        'rail_modulus_MPa': MODULUS_MPA,
        'mesh_mm': MESH_MM,
        'radial_mm': RADIAL_MM,
        'directional_samples': DIRECTIONS,
        'min_sampled_gap_mm': minimum,
        'shaft_end_float_mm': SHAFT_END_FLOAT_MM,
        'shaft_tilt_allowance_deg': SHAFT_TILT_DEG,
        'axial_pin_displacement_allowance_mm': axial,
        'sampled_residual_after_axial_allowance_mm': residual,
    })
    return {
        'passed': passed,
        'cad_sha256': configuration['source_sha256'],
        'rail_step_sha256': digest(rail_step),
        'rail_step_data_sha256': sha256(step_data).hexdigest(),
        'actor_sha256': {name: digest(cad/'world'/f'{name}.stl')
                         for name in (*LINKS, *LIDS, SHELL, 'Part074', 'Part076', 'Part077')},
        'full_stroke_loaded': loaded,
        'continuous_unloaded': unloaded,
        'model_scope': (
            'Loaded front-shell clearance is a finite sample in command angle, load and '
            'independent radial offset. Axial pin motion is accounted for by a distance '
            'allowance at the sampled poses. The unloaded check bounds motion between '
            'samples against both shells and the orbit frames. Print variation, warm '
            'running drag, other load cases and physical contact remain unverified.'
        ),
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    report = verify(args.cad)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    minimum = report['full_stroke_loaded']['min_sampled_gap_mm']
    residual = report['full_stroke_loaded']['sampled_residual_after_axial_allowance_mm']
    print(f'B25 sampled loaded gap {minimum:.3f} mm, {residual:.3f} mm after axial allowance.')
    if not report['passed']:
        raise SystemExit('B25 blink fit check failed. See the report for the limiting clearances.')
