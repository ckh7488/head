"""Export B22 viewer poses from the checked camera-paths.npz archive."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path

import numpy as np


WIRE_DATA = Path(__file__).resolve().parents[1] / 'assets/wiring.json'
PRESETS = (('목 정면 배선', (0, 0, 0, 0)), ('왼쪽 끝 배선', (-60, 7.1, 8, 0)),
           ('오른쪽 끝 배선', (60, 7.1, 8, 0)))


def export(assembly, report, routes, output):
    head = sha256(assembly.read_bytes()).hexdigest()
    checked = json.loads(report.read_text(encoding='utf-8'))
    route_hash = sha256(routes.read_bytes()).hexdigest()
    if checked['status'] != 'pass' or checked['cad_sha256'] != head or checked['routes_sha256'] != route_hash:
        raise ValueError('Camera report does not qualify these exact assemblies and routes')
    profile = json.loads(WIRE_DATA.read_text(encoding='utf-8'))
    diameters = {wire['id']: wire['diameter'] for wire in profile['routes']}
    diameters['USB-Camera'] = checked['camera_diameter_mm']
    states = []
    with np.load(routes) as archive:
        if str(archive['cad_sha256']) != head:
            raise ValueError('Camera path archive refers to a different assembly')
        for index, (label, angles) in enumerate(PRESETS):
            pose = archive['poses'][index]
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
    export(**vars(parser.parse_args()))
