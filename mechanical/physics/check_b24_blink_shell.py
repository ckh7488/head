"""Check continuous B24 lid and link clearance to the shell and orbit frames."""

from argparse import ArgumentParser
import json
from math import radians
from pathlib import Path

import fcl
import numpy as np
import trimesh
from trimesh.collision import mesh_to_BVH

from check_head import pose


def verify(cad, left_max, right_max, link_max):
    layout = json.loads((cad/'cad_parts.json').read_text())
    lids = ('Part078', 'Part079')
    links = ('Part057', 'Part060')
    fixed = ('Part073', 'Part074', 'Part076', 'Part077')
    upper_limits = dict(zip(lids+links, (left_max, right_max, link_max, link_max), strict=True))
    meshes = {name: trimesh.load_mesh(cad/'world'/f'{name}.stl') for name in lids+links+fixed}
    actors = {name: fcl.CollisionObject(mesh_to_BVH(mesh)) for name, mesh in meshes.items()}
    lower = -3.
    request = fcl.DistanceRequest(enable_nearest_points=True)
    pivot = np.array(layout['motion_geometry']['eye_pitch']['cradle_axis_mm'])
    link_radius = layout['motion_geometry']['blink']['lid_radius_mm']
    rows = []
    for moving in lids+links:
        upper = upper_limits[moving]
        angles = np.linspace(lower, upper, int(np.ceil((upper-lower)/.1))+1)
        radius = (link_radius if moving in links else
                  np.linalg.norm(meshes[moving].vertices[:, 1:]-pivot[1:], axis=1).max())
        motion_per_half_step = radius*radians((angles[1]-angles[0])/2)
        closest = {name: (float('inf'), None, None) for name in fixed}
        for angle in angles:
            transform = pose(layout['world_motion'][moving], (0., 0., 0., float(angle), 0.), layout)
            actor = actors[moving]
            actor.setTransform(fcl.Transform(transform[:3, :3].copy(), transform[:3, 3].copy()))
            for name in fixed:
                result = fcl.DistanceResult()
                gap = fcl.distance(actor, actors[name], request, result)
                if gap < closest[name][0]:
                    points = [point.tolist() for point in result.nearest_points] if gap > 0 else None
                    closest[name] = gap, float(angle), points
        for name, (gap, angle, points) in closest.items():
            rows.append({'pair': [moving, name], 'nearest_deg': angle, 'sampled_gap_mm': gap,
                         'continuous_min_mm': float(gap-motion_per_half_step),
                         'angle_samples': len(angles), 'points_mm': points})
    between = meshes[lids[1]].bounds[0][0]-meshes[lids[0]].bounds[1][0]
    return {'cad_sha256': layout['source_sha256'],
            'angle_range_deg': {name: [lower, upper] for name, upper in upper_limits.items()},
            'between_lids_axial_gap_mm': between, 'rows': rows}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--left-max', type=float, default=102.)
    parser.add_argument('--right-max', type=float, default=96.4)
    parser.add_argument('--link-max', type=float, default=97.5)
    args = parser.parse_args()
    if not all(np.isfinite(angle) and angle >= 90 for angle in (args.left_max, args.right_max, args.link_max)):
        parser.error('Tested travel must include the nominal 90-degree closure')
    result = verify(args.cad, args.left_max, args.right_max, args.link_max)
    args.report.write_text(json.dumps(result, indent=2)+'\n')
