"""Look for a continuous downward jaw release path with the rear shell installed."""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App
import numpy as np
import Part

from check_b25_jaw_retention import collision, digest, from_topology, gap, geometry
from check_head import translation
from export_cad import tessellate


TRAVEL_MM = 76.
INTERVALS = 760
CASE_SEATS = Path(__file__).resolve().parents[1] / 'revisions/b25/xl330-case-screws.json'
ASSEMBLY_OBSTACLES = (
    'Part010', 'Part011', 'Part012', 'Part013', 'Part014', 'Part015', 'Part016',
    'Part018', 'Part019', 'Part024', 'Part025', 'Part027', 'Part073', 'Part074',
    'PitchLimitLink', 'PitchLimitUpperPin', 'PitchLimitLowerPin',
    'RearSkullScrewLeft', 'RearSkullScrewRight', 'RearSkullNutLeft', 'RearSkullNutRight',
)


def module_parts(doc):
    return tuple(obj.Name for obj in doc.Objects
                 if obj.Name.startswith(('Jaw_', 'JawHornScrew', 'jawMotorHead'))
                 and obj.TypeId in ('Mesh::Feature', 'Part::Feature'))


def case_screws(seat_manifest):
    seats = json.loads(seat_manifest.read_text(encoding='utf-8'))
    gauge = seats['bench_gauge_mm']
    result = {}
    for index in range(4):
        name = f'jawMotorHead{index}'
        row = seats['seats'][name]
        seat, axis = App.Vector(*row['seat_mm']), App.Vector(*row['axis'])
        height = gauge['head_height']
        head = Part.makeCylinder(gauge['head_diameter']/2, height, seat - axis*height, axis)
        shank = Part.makeCylinder(1., row['oem_tapping_screw_length_mm'], seat, axis)
        result[name] = from_topology(tessellate(head.fuse(shank)))
    return result


def pass_pair(obstacle, jaw, motion):
    fixed_bound, fixed = obstacle
    jaw_bound, moving = jaw
    swept_bound = jaw_bound.copy()
    swept_bound[0, 2] -= TRAVEL_MM
    separated = np.maximum(fixed_bound[0] - swept_bound[1], swept_bound[0] - fixed_bound[1])
    if separated.max() > 0.:
        return {'bounds_lower_bound_mm': float(np.linalg.norm(np.maximum(separated, 0.)))}
    minimum = min(gap(fixed, moving, transform) for transform in motion)
    return {'minimum_sampled_mesh_gap_mm': minimum,
            'mesh_path_lower_bound_mm': minimum - TRAVEL_MM / (2 * INTERVALS)}


def check(path, seat_manifest):
    doc = App.openDocument(str(path.resolve()))
    try:
        meshes = {name: geometry(doc.getObject(name)) for name in (*module_parts(doc), *ASSEMBLY_OBSTACLES)}
        screws = case_screws(seat_manifest)
        meshes.update(screws)
        names = tuple(name for name in meshes if name not in ASSEMBLY_OBSTACLES)
        parts = {name: (mesh.bounds, collision(mesh)) for name, mesh in meshes.items()}
        motion = [translation((0., 0., -distance)) for distance in np.linspace(0., TRAVEL_MM, INTERVALS + 1)]
        obstacles = {obstacle: {name: pass_pair(parts[obstacle], parts[name], motion) for name in names}
                     for obstacle in ASSEMBLY_OBSTACLES}
        lower_bounds = [result.get('mesh_path_lower_bound_mm', result.get('bounds_lower_bound_mm'))
                        for obstacle in obstacles.values() for result in obstacle.values()]
        return {
            'source_cad_sha256': digest(path), 'case_seats_sha256': digest(seat_manifest),
            'module_parts': names, 'case_screw_envelopes': tuple(screws),
            'nominal_head_pose_deg': 0., 'direction': [0, 0, -1], 'travel_mm': TRAVEL_MM,
            'sample_step_mm': TRAVEL_MM / INTERVALS, 'neighboring_parts': obstacles,
            'witness_mesh_lower_bound_mm': min(lower_bounds),
            'status': 'release path found' if min(lower_bounds) > 0. else 'path unverified',
            'scope': 'Rigid module at the nominal CAD pose and the installed rigid neighbors of its service path. '
                     'The jaw harness is omitted as a structural retainer. The continuous lower bound uses '
                     'mesh distances and the maximum travel from a sample to its nearest neighbor.',
        }
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--case-seats', type=Path, default=CASE_SEATS)
    args = parser.parse_args()
    report = check(args.source, args.case_seats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'])
