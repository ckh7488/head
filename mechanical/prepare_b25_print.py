"""Update the B25 P2S print poses without modifying the part meshes."""

from argparse import ArgumentParser
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
import numpy as np

from build_b20_print import CORE, MODEL, MODEL_SETTINGS, PRODUCTION, serialize


FLIP_X = np.diag([1., -1., -1.])
LAY_FLAT = np.array([[1., 0., 0.], [0., 0., 1.], [0., -1., 0.]])
POSES = {
    '24_blink_rail_with_bearing_shoulders_1': (7, FLIP_X, 0.),
    '23_right_short_lid_link-B21': (8, FLIP_X, 88.9515),
    '45_blink_shaft_spacer_right-B19': (8, FLIP_X, 0.),
    'ID5-keeper-B21': (8, LAY_FLAT, 0.),
    '12_eye_tilt_cradle-B23': (14, FLIP_X, 0.),
}


def points_in_instance(archive, resource, instance):
    vertices = []
    for comp in resource.iter(CORE + 'component'):
        path = comp.get(PRODUCTION + 'path').lstrip('/')
        part_id = comp.get('objectid')
        model = etree.fromstring(archive.read(path))
        part = model.find(f".//{CORE}object[@id='{part_id}']")
        if part is None:
            raise ValueError(f'Missing object {part_id} in {path}')
        mesh = part.find(CORE + 'mesh')
        p = np.array([[float(v.get(axis)) for axis in 'xyz'] for v in mesh.find(CORE + 'vertices')])
        pose = np.fromstring(comp.get('transform', '1 0 0 0 1 0 0 0 1 0 0 0'), sep=' ').reshape(4, 3)
        vertices.append(p @ pose[:3] + pose[3])
    return np.concatenate(vertices) @ instance[:3] + instance[3]


def build(source, output):
    if source.resolve() == output.resolve():
        raise ValueError('Use a separate output path')
    with ZipFile(source) as archive:
        model = etree.fromstring(archive.read(MODEL))
        cfg = etree.fromstring(archive.read(MODEL_SETTINGS))
        locations = {
            slot.get('value'): int(plate.find("metadata[@key='plater_id']").get('value'))
            for plate in cfg.findall('plate')
            for slot in plate.findall("model_instance/metadata[@key='object_id']")
        }
        targets = [
            (obj, obj.find("metadata[@key='name']").get('value'))
            for obj in cfg.findall('object')
        ]
        if Counter(name for _, name in targets if name in POSES) != Counter(POSES.keys()):
            raise ValueError('The source is missing a B25 print target or contains a duplicate')
        for obj, name in targets:
            if name not in POSES:
                continue
            plate, rotation, x_move = POSES[name]
            object_id = obj.get('id')
            if locations[object_id] != plate:
                raise ValueError(f'{name} must be on plate {plate}')
            inst = model.find(f"{CORE}build/{CORE}item[@objectid='{object_id}']")
            resource = model.find(f"{CORE}resources/{CORE}object[@id='{object_id}']")
            pose = np.fromstring(inst.get('transform'), sep=' ').reshape(4, 3)
            if not np.allclose(pose[:3], np.eye(3)):
                raise ValueError(f'{name} must start with the original unrotated pose')
            current = points_in_instance(archive, resource, pose)
            rotated = current @ rotation
            center_before = (current.min(0) + current.max(0)) / 2
            center_after = (rotated.min(0) + rotated.max(0)) / 2
            shift = center_before - center_after + np.array([x_move, 0., 0.])
            shift[2] = -rotated[:, 2].min()
            pose = pose @ rotation
            pose[3] += shift
            inst.set('transform', ' '.join(f'{x:.11g}' for x in pose.ravel()))
        with ZipFile(output, 'w') as destination:
            for entry in archive.infolist():
                destination.writestr(entry, serialize(model) if entry.filename == MODEL else archive.read(entry))


if __name__ == '__main__':
    args = ArgumentParser(description=__doc__)
    args.add_argument('source', type=Path)
    args.add_argument('output', type=Path)
    build(**vars(args.parse_args()))
