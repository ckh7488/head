"""Export assembly viewer poses from the checked camera-paths.npz archive."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path

import numpy as np


WIRE_DATA = Path(__file__).resolve().parents[1] / 'assets/wiring.json'
PRESETS = (('목 정면 배선', (0, 0, 0, 0)), ('왼쪽 끝 배선', (-60, 7.1, 8, 0)),
           ('오른쪽 끝 배선', (60, 7.1, 8, 0)))


def export(assembly, report, routes, output, layout=None):
    head = sha256(assembly.read_bytes()).hexdigest()
    checked = json.loads(report.read_text(encoding='utf-8'))
    route_hash = sha256(routes.read_bytes()).hexdigest()
    if checked['status'] != 'pass' or checked['cad_sha256'] != head or checked['routes_sha256'] != route_hash:
        raise ValueError('Camera report does not qualify these exact assemblies and routes')
    yaw_limits = None
    if layout is not None:
        layout = json.loads(layout.read_text(encoding='utf-8'))
        if layout['source_sha256'] != head:
            raise ValueError('CAD export and wire routes refer to different assemblies')
        yaw_limits = layout['motion_geometry'].get('yaw_limit', {}).get('nominal_stop_deg')
    profile = json.loads(WIRE_DATA.read_text(encoding='utf-8'))
    diameters = {wire['id']: wire['diameter'] for wire in profile['routes']}
    diameters['USB-Camera'] = checked['camera_diameter_mm']
    states = []
    with np.load(routes) as archive:
        if str(archive['cad_sha256']) != head:
            raise ValueError('Camera path archive refers to a different assembly')
        poses = archive['poses']
        selections = [(index, label, angles) for index, (label, angles) in enumerate(PRESETS)]
        if yaw_limits is not None:
            low, high = yaw_limits
            eligible = sorted((float(pose[0]), index) for index, pose in enumerate(poses)
                              if low < pose[0] < high and checked['samples'][index]['status'] == 'pass')
            if not eligible or not eligible[0][0] < 0 < eligible[-1][0]:
                raise ValueError('No checked wire comparison on both sides within the mechanical stops')
            selections = selections[:1] + [
                (index, f'목 좌우 {angle:+g}° 배선', poses[index, :4])
                for angle, index in (eligible[0], eligible[-1])
            ]
        for index, label, angles in selections:
            pose = poses[index]
            sample = checked['samples'][index]
            if (sample['status'] != 'pass' or not np.allclose(pose[:4], angles)
                    or not np.allclose(pose, sample['pose_deg'])):
                raise ValueError(f'Missing checked camera preset {label}')
            prefix = f'pose{index:03d}__'
            paths = {key.removeprefix(prefix): archive[key].tolist() for key in archive.files if key.startswith(prefix)}
            states.append({'id': f'camera-{index}', 'label': label, 'pose_deg': pose.tolist(),
                           'points': paths['USB-Camera'], 'wirePoints': paths})
    data = {'cad_sha256': head, 'checked_geometry_cad_sha256': head, 'routes_sha256': route_hash,
            'diameter_mm': diameters['USB-Camera'], 'wireDiametersMm': diameters, 'states': states}
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for name in ('assembly', 'report', 'routes', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--layout', type=Path, help='Matching CAD export with mechanical yaw limits')
    export(**vars(parser.parse_args()))
