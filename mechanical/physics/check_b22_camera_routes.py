"""Verify sampled camera cable routes at fixed developed length against B22 CAD."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

import numpy as np
import trimesh

from check_b22_harness import CUT_LENGTHS, WIRE_DATA
from wiring_check import Cable, Scene, discrete_bend, read, reference_cables, segment_gap, self_gap
from wiring_motion import matrices, transform


CAMERA = 'USB-Camera'
LENGTH = 337.290
DIAMETER = 4.
RADIUS = 12.
SOLID_RESERVE = .25
CAMERA_MATE_MM = (5.5, -47.05, 83.)


def load_scene(cad, layout):
    scene = Scene.__new__(Scene)
    scene.groups = {}
    for name, role in layout['world_motion'].items():
        if name.startswith(('Harness', 'HubRearClearance', 'Ballast')) or name == 'RearLead3_1':
            continue
        mesh = cad/'world'/f'{name}.stl'
        if sha256(mesh.read_bytes()).hexdigest() != layout['world_sha256'][name]:
            raise ValueError(f'Unexpected mesh contents for {name}')
        shape = trimesh.load_mesh(mesh)
        if len(shape.faces):
            scene.add(name, role, shape)
    return scene


def measure(pose, paths, layout, wiring, scene, minimum_wire_gap=-.06):
    motion = matrices(layout, *pose)
    dimensions = {wire['id']: wire['diameter'] for wire in wiring['routes']}
    route = paths.pop(CAMERA)
    cable = Cable(CAMERA, route, DIAMETER, LENGTH, *discrete_bend(route))
    others = [Cable(name, points, dimensions.get(name, 1.143), 0., 0.) for name, points in paths.items()]
    others.extend(reference_cables(wiring, motion, [cable, *others]))
    endpoints = np.array([layout['motion_geometry']['camera_cable']['base_cable_entry_mm'],
                          transform(CAMERA_MATE_MM, motion['head'])])
    endpoints_error = float(np.linalg.norm(route[[0, -1]]-endpoints, axis=1).max())
    length_error = float(cable.arc[-1])-LENGTH
    objects = scene.hits(cable, motion, SOLID_RESERVE)
    wires = [hit for other in others if (hit := segment_gap(cable, other, minimum_wire_gap))]
    own = self_gap(cable)
    passed = abs(length_error) < .01 and endpoints_error < .01 and cable.radius >= RADIUS
    return {'pose_deg': pose, 'status': 'pass' if passed and not (objects or wires or own) else 'fail',
            'length_error_mm': length_error, 'maximum_endpoint_error_mm': endpoints_error,
            'minimum_radius_mm': cable.radius, 'bend_point_mm': cable.bend_point,
            'solid_contacts': objects, 'wire_contacts': wires, 'self_contact': own}


def check(cad, file, output, minimum_wire_gap=None):
    if minimum_wire_gap is not None and (not isfinite(minimum_wire_gap) or minimum_wire_gap < 0):
        raise ValueError('The minimum wire gap must be finite and nonnegative')
    measure_args = {} if minimum_wire_gap is None else {'minimum_wire_gap': minimum_wire_gap}
    layout = read(cad/'cad_parts.json')
    wiring = read(WIRE_DATA)
    scene = load_scene(cad, layout)
    required = {name for name in read(CUT_LENGTHS) if name.startswith('motor')} | {CAMERA}
    rows = []
    with np.load(file) as value:
        poses = value['poses']
        if (value['cad_sha256'].item() != layout['source_sha256'] or poses.ndim != 2 or poses.shape[1] != 5
                or not len(poses) or not np.isfinite(poses).all()):
            raise ValueError('Camera routes must describe the exact CAD and an explicit set of poses')
        for index, pose in enumerate(poses):
            prefix = f'pose{index:03d}__'
            paths = {name[len(prefix):]: value[name] for name in value.files if name.startswith(prefix)}
            if (not required <= paths.keys()
                    or any(points.ndim != 2 or points.shape[1] != 3 or len(points) < 3
                           or not np.isfinite(points).all() for points in paths.values())):
                raise ValueError(f'Incomplete cable pose {index}')
            rows.append(measure(pose.tolist(), paths, layout, wiring, scene, **measure_args))
    passed = all(row['status'] == 'pass' for row in rows)
    result = {'status': 'pass' if passed else 'fail', 'cad_sha256': layout['source_sha256'],
              'routes_sha256': sha256(file.read_bytes()).hexdigest(),
              'camera_diameter_mm': DIAMETER, 'internal_length_mm': LENGTH,
              'solid_reserve_mm': SOLID_RESERVE, 'target_min_radius_mm': RADIUS,
              'scope': 'Fixed length geometry at the listed poses. No friction, wear, or fatigue model.',
              'samples': rows}
    if minimum_wire_gap is not None:
        result['minimum_wire_gap_mm'] = minimum_wire_gap
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(f'{len(rows)} camera routes, {sum(r["status"] == "pass" for r in rows)} pass', flush=True)
    return passed


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('paths', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--minimum-wire-gap', type=float, metavar='MM',
                        help='Require a nonnegative surface gap to every neighboring cable.')
    args = parser.parse_args()
    if args.minimum_wire_gap is not None and (not isfinite(args.minimum_wire_gap) or args.minimum_wire_gap < 0):
        parser.error('the minimum wire gap must be finite and nonnegative')
    if not check(args.cad, args.paths, args.report, args.minimum_wire_gap):
        raise SystemExit(1)
