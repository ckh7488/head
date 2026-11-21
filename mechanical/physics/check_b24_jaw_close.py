"""Bound jaw clearance during the signed encoder feedback and recovery envelope."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from math import ceil, radians
from pathlib import Path
import re

import fcl
import numpy as np
from trimesh.collision import mesh_to_BVH
from trimesh.transformations import rotation_matrix

from jaw_clearance import tooth_mesh


ENCODER_DEG = 360 / 4096
ANGLE_ERROR_DEG = .7
VERTICAL_ERROR_MM = .4
MINIMUM_GAP_MM = .5


def inspect(cad, firmware):
    scene = json.loads((cad/'cad_parts.json').read_text())
    source = firmware.read_bytes()

    def ticks(name):
        return int(re.search(rf'\b{name}\s*=\s*(\d+)', source.decode())[1])

    # The closest actual shaft pose can be half a tick beyond the last accepted reading.
    feedback_min = -(ticks('jawClosingTolerance') + .5) * ENCODER_DEG
    feedback_max = (ticks('exhibitJawRecoveryTicks') + .5) * ENCODER_DEG
    pivot = np.array(scene['jaw_pivot_mm'])
    paths = [cad/'world'/f'{part}.stl' for part in ('Part073', 'Jaw_30_moving_jaw')]
    if any(sha256(path.read_bytes()).hexdigest() != scene['world_sha256'][path.stem] for path in paths):
        raise ValueError('Jaw and skull mesh identity must match the CAD export')
    upper, lower = (tooth_mesh(path) for path in paths)
    fixed, moving = [fcl.CollisionObject(mesh_to_BVH(mesh)) for mesh in (upper, lower)]
    radius = np.linalg.norm(lower.vertices[:, 1:] - pivot[1:], axis=1).max()
    low, high = feedback_min - ANGLE_ERROR_DEG, feedback_max + ANGLE_ERROR_DEG
    angles = np.linspace(low, high, ceil((high - low) / .04) + 1)
    offsets = np.linspace(-VERTICAL_ERROR_MM, VERTICAL_ERROR_MM, 17)
    # The Hausdorff displacement from any pose to its nearest sample bounds the loss in gap.
    unsampled = radius * radians((angles[1] - angles[0]) / 2) + (offsets[1] - offsets[0]) / 2
    witness = {'sampled_gap_mm': float('inf')}
    request = fcl.DistanceRequest(enable_nearest_points=True)
    collision = fcl.CollisionRequest()
    for angle in angles:
        matrix = rotation_matrix(radians(angle), (1., 0., 0.), pivot)
        for vertical in offsets:
            origin = matrix[:3, 3].copy()
            origin[2] += vertical
            moving.setTransform(fcl.Transform(matrix[:3, :3].copy(), origin))
            result = fcl.DistanceResult()
            gap = fcl.distance(fixed, moving, request, result)
            if not np.isfinite(gap) or fcl.collide(fixed, moving, collision, fcl.CollisionResult()):
                raise ValueError(f'Upper shell and jaw touch at {angle:.4f}°, vertical offset {vertical:.3f} mm')
            if gap < witness['sampled_gap_mm']:
                witness = dict(sampled_gap_mm=float(gap), angle_deg=float(angle), vertical_error_mm=float(vertical),
                               witness_points_mm=[point.tolist() for point in result.nearest_points])
    lower_bound = witness['sampled_gap_mm'] - unsampled
    return {
        'cad_sha256': scene['source_sha256'],
        'firmware_sha256': sha256(source).hexdigest(),
        'required_clearance_mm': MINIMUM_GAP_MM,
        'relative_angle_error_deg': ANGLE_ERROR_DEG,
        'relative_vertical_error_mm': VERTICAL_ERROR_MM,
        'accepted_encoder_envelope_with_quantization_deg': [feedback_min, feedback_max],
        'maximum_between_sample_displacement_mm': float(unsampled),
        'minimum_clearance_lower_bound_mm': float(lower_bound),
        'worst_sample': witness,
        'sample_count': int(len(angles) * len(offsets)),
        'pass': bool(lower_bound >= MINIMUM_GAP_MM),
        'scope': 'Full upper shell and jaw surface separation over accepted encoder feedback with half-tick '
                 'quantization, hinge vertical offset and calibrated neutral error. Does not bound external '
                 'forces or excursions after the firmware reports an out-of-range position.',
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for key in ('cad', 'firmware', 'output'):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    report = inspect(args.cad, args.firmware)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{report['sample_count']} poses, jaw clearance lower bound {report['minimum_clearance_lower_bound_mm']:.3f} mm")
    if not report['pass']:
        raise SystemExit('Jaw clearance must be at least 0.5 mm')
