"""Update the B25 P2S print layout and optionally apply its repaired front skull mesh."""

from argparse import ArgumentParser
from copy import deepcopy
import json
from math import ceil, sqrt
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
STANDALONE_PLATES = {
    '22_blink_drive_link-B21': (8, 'Blink drive link standalone'),
    '32_left_eyelid-B25': (9, 'Left eyelid standalone'),
    '32_right_eyelid-B21': (9, 'Right eyelid standalone'),
    '14_eyeball_2_1': (10, 'Right eyeball standalone'),
}
EYELID_RAFT = {
    'raft_layers': '2',
    'raft_first_layer_expansion': '6',
    'raft_expansion': '6',
    'brim_object_gap': '0',
}
FILAMENT_SEQUENCE = 'Metadata/filament_sequence.json'
FRONT_SKULL = '28_skull_front_with_camera_tray-B25'
BED_SIZE = 256
PLATE_STRIDE = BED_SIZE * 1.2  # Bambu Studio's plate grid includes a 20% gap.


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


def plate_origin(number, count):
    row, col = divmod(number - 1, ceil(sqrt(count)))
    return np.array([col * PLATE_STRIDE, -row * PLATE_STRIDE, 0.])


def isolate_small_parts(archive, model, config, objects, locations):
    plates = config.findall('plate')
    old_count = len(plates)
    if [p.find("metadata[@key='plater_id']").get('value') for p in plates] != list(map(str, range(1, 15))):
        raise ValueError('Expected the original 14 B25 plates in order')
    sequence = json.loads(archive.read(FILAMENT_SEQUENCE))
    new_locations = locations.copy()

    new_count = old_count + len(STANDALONE_PLATES)
    for number, (name, (old_number, title)) in enumerate(STANDALONE_PLATES.items(), old_count + 1):
        obj = objects[name]
        object_id = obj.get('id')
        if locations[object_id] != old_number:
            raise ValueError(f'{name} must be on plate {old_number}')
        old_plate = plates[old_number - 1]
        slot, = old_plate.xpath("model_instance[metadata[@key='object_id'][@value=$id]]", id=object_id)
        new_plate = etree.SubElement(config, 'plate')
        for field in old_plate.findall('metadata'):
            new_plate.append(deepcopy(field))
        new_plate.find("metadata[@key='plater_id']").set('value', str(number))
        new_plate.find("metadata[@key='plater_name']").set('value', title)
        new_plate.append(slot)
        new_locations[object_id] = number
        sequence[f'plate_{number}'] = sequence[f'plate_{old_number}']
        if name.startswith('32_'):
            # Tree supports consume the eyelids' separate brim paths. Use an expanded raft as their base.
            for key, value in EYELID_RAFT.items():
                obj.insert(obj.index(obj.find('part')), etree.Element('metadata', key=key, value=value))

    plates[9].find("metadata[@key='plater_name']").set('value', 'Left eyeball standalone')
    for item in model.findall(f'{CORE}build/{CORE}item'):
        object_id = item.get('objectid')
        from_plate, to_plate = locations[object_id], new_locations[object_id]
        old_origin, new_origin = plate_origin(from_plate, old_count), plate_origin(to_plate, new_count)
        if from_plate == to_plate and np.array_equal(old_origin, new_origin):
            continue
        pose = np.fromstring(item.get('transform'), sep=' ').reshape(4, 3)
        if from_plate == to_plate:
            pose[3] += new_origin - old_origin
        else:
            resource = model.find(f"{CORE}resources/{CORE}object[@id='{object_id}']")
            points = points_in_instance(archive, resource, pose)
            center = (points.min(0) + points.max(0)) / 2
            pose[3, :2] += new_origin[:2] + BED_SIZE / 2 - center[:2]
        item.set('transform', ' '.join(f'{value:.12g}' for value in pose.ravel()))

    return json.dumps(sequence, separators=(',', ':')).encode()


def front_skull_replacement(archive, model, obj, replacement):
    component, = model.findall(f".//{CORE}object[@id='{obj.get('id')}']//{CORE}component")
    path = component.get(PRODUCTION + 'path').lstrip('/')
    original = etree.fromstring(archive.read(path))
    data = replacement.read_bytes()
    revised = etree.fromstring(data)
    object_id = component.get('objectid')
    part_path = f"{CORE}resources/{CORE}object[@id='{object_id}']"
    old_part, new_part = original.find(part_path), revised.find(part_path)
    if new_part is None or old_part.attrib != new_part.attrib:
        raise ValueError('The replacement must preserve the front skull mesh object and UUID')
    triangles = new_part.find(f'{CORE}mesh/{CORE}triangles')
    if triangles is None or not len(triangles):
        raise ValueError('The front skull replacement contains no triangles')
    face_count = str(len(triangles))
    obj.find('metadata[@face_count]').set('face_count', face_count)
    obj.find('part/mesh_stat').set('face_count', face_count)
    return path, data


def build(source, output, *, isolate=False, front_model=None):
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
        required = set(POSES)
        if isolate:
            required.update(STANDALONE_PLATES)
        if front_model is not None:
            required.add(FRONT_SKULL)
        targets = {}
        for obj in cfg.findall('object'):
            name = obj.find("metadata[@key='name']").get('value')
            if name in required:
                if name in targets:
                    raise ValueError(f'Duplicate B25 print target {name}')
                targets[name] = obj
        if required - targets.keys():
            raise ValueError('The source is missing a B25 print target')
        for name, (plate, rotation, x_move) in POSES.items():
            object_id = targets[name].get('id')
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
        changes = {}
        if isolate:
            changes[FILAMENT_SEQUENCE] = isolate_small_parts(archive, model, cfg, targets, locations)
        if front_model is not None:
            path, data = front_skull_replacement(archive, model, targets[FRONT_SKULL], front_model)
            changes[path] = data
        if isolate or front_model is not None:
            changes[MODEL_SETTINGS] = serialize(cfg)
        changes[MODEL] = serialize(model)
        with ZipFile(output, 'w') as destination:
            for entry in archive.infolist():
                data = changes[entry.filename] if entry.filename in changes else archive.read(entry)
                destination.writestr(entry, data)


if __name__ == '__main__':
    args = ArgumentParser(description=__doc__)
    args.add_argument('source', type=Path)
    args.add_argument('output', type=Path)
    args.add_argument('--isolate', action='store_true', help='Move small-footprint parts to standalone plates')
    args.add_argument('--front-model', type=Path, help='Install the repaired front skull .model archive member')
    build(**vars(args.parse_args()))
