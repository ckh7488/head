"""Verify the released B22 cable centerlines against the changed B23 geometry."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path

import numpy as np

from check_b22_camera_routes import check
from wiring_motion import matrices


ROOT = Path(__file__).resolve().parents[2]
B22 = ROOT / 'mechanical/revisions/b22'


def digest(path):
    with path.open('rb') as file:
        return file_digest(file, 'sha256').hexdigest()


def motion_contract(path):
    layout = json.loads((path / 'cad_parts.json').read_text())
    geometry = layout['motion_geometry'].copy()
    for key in ('bottom_board_service_nuts', 'rear_cable_service_nuts', 'yaw_inner_race_shim', 'yaw_limit', 'eye_pitch'):
        geometry.pop(key, None)
    nose = geometry['camera_cable_nose'].copy()
    nose.pop('tie_notch_roof_center_mm')
    geometry['camera_cable_nose'] = nose
    blink = geometry['blink'].copy()
    blink.pop('obstacles')
    geometry['blink'] = blink
    return layout, (layout['jaw_pivot_mm'], geometry)


def replay(reference, cad, output):
    original, original_motion = motion_contract(reference)
    revised, revised_motion = motion_contract(cad)
    record = json.loads((B22 / 'camera-check.json').read_text())
    routes = B22 / 'camera-paths.npz'
    if (original['source_sha256'] != digest(B22 / 'R5-B22-Assembly.FCStd')
            or original['source_sha256'] != record['cad_sha256']
            or record['status'] != 'pass'
            or digest(routes) != record['routes_sha256']
            or original_motion != revised_motion):
        raise ValueError('The verified B22 centerlines require unchanged attachment points and motion')
    output.mkdir(parents=True, exist_ok=True)
    variant = output / 'camera-paths.npz'
    with np.load(routes) as source:
        if source['cad_sha256'].item() != original['source_sha256']:
            raise ValueError('Centerlines do not match the reference CAD')
        points = {name: source[name] for name in source.files}
    for pose in points['poses']:
        before = matrices(original, *pose)
        after = matrices(revised, *pose)
        for role in ('fixed', 'pan', 'head', 'tilt', 'jaw', 'hatch'):
            if role in before and not np.allclose(before[role], after[role], atol=1e-9, rtol=0.):
                raise ValueError(f'{role} attachment moved; solve the cable route again')
    points['cad_sha256'] = np.asarray(revised['source_sha256'])
    np.savez_compressed(variant, **points)
    report_path = output / 'camera-check.json'
    passed = check(cad, variant, report_path)
    report = json.loads(report_path.read_text())
    report['reference_routes_sha256'] = record['routes_sha256']
    report['reference_cad_sha256'] = original['source_sha256']
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    return passed


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('cad', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if replay(args.reference, args.cad, args.output) else 1)
