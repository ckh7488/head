"""Bound the front-shell insertion clearance to both B24 eye-pitch bearings."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from math import cos, pi
from pathlib import Path

import fcl
import numpy as np
import trimesh
from trimesh.collision import mesh_to_BVH

from check_head import rotation


def verify(cad):
    manifest = json.loads((cad/'cad_parts.json').read_text())
    shell_path = cad/'world/Part073.stl'
    shell = fcl.CollisionObject(mesh_to_BVH(trimesh.load_mesh(shell_path)))
    request = fcl.DistanceRequest()
    x_inner, x_outer = 66.55, 69.20
    radius = 3.15
    spacing = .05
    interval_count = round(84/spacing)
    insertion = np.linspace(0., 84., interval_count+1)
    rows = []
    for side, sign in (('L', -1), ('R', 1)):
        # Enclose the full outer race over the pocket-depth and ±0.10 mm Y/Z ranges.
        sections = 128
        witness = trimesh.creation.cylinder(radius=radius/cos(pi/sections),
                                           height=x_outer-x_inner, sections=sections)
        witness.apply_transform(rotation(90., (0, 1, 0), (0, 0, 0)))
        witness.apply_translation((sign*(x_inner+x_outer)/2, -39., 119.))
        bearing = fcl.CollisionObject(mesh_to_BVH(witness))
        gaps = []
        for feed in insertion:
            shell.setTransform(fcl.Transform(np.array((0., -feed, 0.))))
            gaps.append(fcl.distance(shell, bearing, request, fcl.DistanceResult()))
        nearest = int(np.argmin(gaps))
        rows.append({'side': side, 'sampled_min_mm': gaps[nearest],
                     'continuous_min_mm': gaps[nearest]-spacing/2,
                     'nearest_feed_at_mm': float(insertion[nearest]), 'samples': len(insertion)})
    with shell_path.open('rb') as source:
        shell_sha = file_digest(source, 'sha256').hexdigest()
    return {'cad_sha256': manifest['source_sha256'], 'shell_mesh_sha256': shell_sha,
            'signed_absolute_x_range_mm': [x_inner, x_outer], 'radial_axis_relative_yz_mm': .10,
            'witness_circumscribed_radius_mm': radius, 'sample_spacing_mm': spacing, 'rows': rows}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    args.report.write_text(json.dumps(verify(args.cad), indent=2)+'\n')
