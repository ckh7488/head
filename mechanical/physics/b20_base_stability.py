"""Quasi-static slip and tipping thresholds on a flat workbench."""

from argparse import ArgumentParser
from itertools import product
import json
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull
import trimesh


GRAVITY = 9.81
PITCH_AXIS_MM = (0., 0., 112.)
PULL_HEIGHTS_MM = (35, 290)
FRICTION_COEFFICIENTS = (.15, .30, .50)


def rotate(point, angle, direction, pivot):
    transform = trimesh.transformations.rotation_matrix(np.radians(angle), direction, pivot)
    return transform[:3, :3] @ point + transform[:3, 3]


def bench_limits(cad, dynamics, base_mass_g):
    layout = json.loads((cad / 'cad_parts.json').read_text())
    if dynamics['source_sha256'] != layout['source_sha256']:
        raise ValueError('The dynamic masses came from a different CAD export')

    cup = trimesh.load_mesh(cad / 'world/Part000.stl')
    if not cup.is_volume:
        raise ValueError('Need a closed base mesh for support and mass properties')
    base_center = cup.center_mass[:2]
    base_mass = base_mass_g / 1000.
    floor = cup.bounds[0, 2]
    contact = cup.vertices[cup.vertices[:, 2] <= floor + .12, :2]
    hull = ConvexHull(contact)
    normal = hull.equations[:, :2]
    edge_offset = hull.equations[:, 2]

    properties = dynamics['mass_properties']
    groups = ('yaw_carrier', 'head', 'jaw')
    masses = np.array([properties[g]['mass_kg'] for g in groups])
    carrier, head, jaw = (np.array(properties[g]['com_mm']) for g in groups)
    total = float(base_mass + masses.sum())
    axis_x, axis_z = (1, 0, 0), (0, 0, 1)
    lowest = float('inf')
    limiting_pose = None
    sampled = 0
    for yaw, pitch, opening in product(range(-60, 61, 3), range(-15, 7), range(14)):
        jaw_center = rotate(jaw, opening, axis_x, layout['jaw_pivot_mm'])
        moving = [carrier, rotate(head, pitch, axis_x, PITCH_AXIS_MM),
                  rotate(jaw_center, pitch, axis_x, PITCH_AXIS_MM)]
        points = np.array([rotate(p, yaw, axis_z, (0, 0, 0))[:2] for p in moving])
        center = (base_mass * base_center + masses @ points) / total
        margin = float((-edge_offset - normal @ center).min())
        if margin < lowest:
            lowest, limiting_pose = margin, (yaw, pitch, opening)
        sampled += 1

    weight = total * GRAVITY
    moment = weight * lowest / 1000.
    pulls = [{'height_mm': h, 'tip_force_N': moment / (h / 1000.),
              'first_motion_N_by_friction': {str(mu): min(weight * mu, moment / (h / 1000.))
                                             for mu in FRICTION_COEFFICIENTS}}
             for h in PULL_HEIGHTS_MM]
    return {'source_sha256': layout['source_sha256'], 'support_plane_mm': float(floor),
            'support_area_mm2': float(hull.volume), 'base_cup_g': base_mass_g,
            'included_mass_kg': total, 'pose_samples': sampled, 'limiting_pose_deg': limiting_pose,
            'minimum_edge_margin_mm': lowest, 'minimum_restoring_moment_Nm': moment,
            'horizontal_pull': pulls}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('dynamics', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--base-mass-g', type=float, required=True)
    args = parser.parse_args()
    if args.base_mass_g <= 0:
        parser.error('The sliced base mass must be positive')
    result = bench_limits(args.cad, json.loads(args.dynamics.read_text()), args.base_mass_g)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['pose_samples']} poses, min edge margin {result['minimum_edge_margin_mm']:.1f} mm")
