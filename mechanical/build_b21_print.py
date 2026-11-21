"""Update the B20 P2S project with B21 geometry and retain its plate settings."""

from argparse import ArgumentParser
from copy import copy, deepcopy
from hashlib import sha256
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from zipfile import ZipFile, ZipInfo

from lxml import etree
import numpy as np
import trimesh

from build_b20_print import (
    CORE, PRODUCTION, MODEL, MODEL_RELS, MODEL_SETTINGS, REVISIONS, remove_part, replace_mesh, serialize, template_parts
)


BASE = REVISIONS / 'b20/R5-B20-P2S.3mf'
RELEASE_PARTS = {
    '06_neck_mast.stl': '06_neck_mast-B21.stl',
    '07-yoke-B18.stl': '07_yoke-B21.stl',
    'ID5-keeper-B19.stl': 'ID5-keeper-B21.stl',
    '27_radio_plate.stl': '27_c3_carrier-B21.stl',
    '15_eye_yaw_offset_tie_bar.stl': '15_eye_yaw_offset_tie_bar-B21.stl',
    '16_eye_yaw_horn_13p5_mm.stl': '16_eye_yaw_horn_13p5_mm-B21.stl',
    '18_eye_pitch_link_58p5mm.stl': '18_eye_pitch_link_58p5mm-B21.stl',
    '19_blink_servo_horn-B19.stl': '19_blink_servo_horn-B21.stl',
    '21_blink_shaft_crank_1.stl': '21_blink_shaft_crank_1-B21.stl',
    '21_blink_shaft_crank_2-B19.stl': '21_blink_shaft_crank_2-B21.stl',
    '21_blink_shaft_crank_3.stl': '21_blink_shaft_crank_3-B21.stl',
    '22_blink_drive_link.stl': '22_blink_drive_link-B21.stl',
    '23_left_short_lid_link.stl': '23_left_short_lid_link-B21.stl',
    '23_right_short_lid_link.stl': '23_right_short_lid_link-B21.stl',
    '32_left_upper_lid.stl': '32_left_eyelid-B21.stl',
    '32_right_upper_lid.stl': '32_right_eyelid-B21.stl',
    '37_right_cheek_bearing_stay.stl': '37_right_cheek_bearing_stay-B21.stl',
}
BOARD_CLIPS = ('51_c3_clamp_left-B21.stl', '51_c3_clamp_right-B21.stl')
BLINK_SUPPORT = (
    '19_blink_servo_horn-B19.stl', '22_blink_drive_link.stl',
    '23_left_short_lid_link.stl', '23_right_short_lid_link.stl',
)


def plate_signatures(bundle):
    model = etree.fromstring(bundle.read(MODEL))
    config = etree.fromstring(bundle.read(MODEL_SETTINGS))
    metadata = {node.get('id'): node for node in config.findall('object')}
    items = {node.get('objectid'): node for node in model.find(CORE + 'build')}
    resources = {node.get('id'): node for node in model.find(CORE + 'resources')}
    by_plate = {}
    for plate in config.findall('plate'):
        index = int(plate.find("metadata[@key='plater_id']").get('value'))
        members = []
        for slot in plate.findall('model_instance'):
            object_id = slot.find("metadata[@key='object_id']").get('value')
            component = resources[object_id].find('.//' + CORE + 'component')
            path = component.get(PRODUCTION + 'path').lstrip('/')
            members.append((object_id, sha256(bundle.read(path)).hexdigest(),
                            serialize(metadata[object_id]), serialize(items[object_id]), serialize(component)))
        by_plate[index] = members
    return by_plate


def plate_digest(parts):
    rows = [(object_id, mesh_hash, *(sha256(element).hexdigest() for element in xml))
            for object_id, mesh_hash, *xml in parts]
    return sha256(json.dumps(rows).encode('ascii')).hexdigest()


def name_part(obj, part, new_name, face_count):
    for item in (obj, part):
        item.find("metadata[@key='name']").set('value', Path(new_name).stem)
    part.find("metadata[@key='source_file']").set('value', new_name)
    obj.find('metadata[@face_count]').set('face_count', str(face_count))
    part.find('mesh_stat').set('face_count', str(face_count))


def add_board_clips(base, model, config, changes, names, clips):
    template, _ = template_parts(config)['27_radio_plate.stl']
    old_id = template.get('id')
    resources = model.find(CORE + 'resources')
    build_items = model.find(CORE + 'build')
    resource = resources.find(f"{CORE}object[@id='{old_id}']")
    item = build_items.find(f"{CORE}item[@objectid='{old_id}']")
    component = resource.find('.//' + CORE + 'component')
    old_target = component.get(PRODUCTION + 'path')
    source = base.read(old_target.lstrip('/'))
    relations = etree.fromstring(base.read(MODEL_RELS))
    relation = relations.find(f"*[@Target='{old_target}']")
    plate = config.xpath("./plate[metadata[@key='plater_id'][@value='3']]")[0]
    slot = plate.xpath(f"./model_instance[metadata[@key='object_id'][@value='{old_id}']]")[0]
    last = max(int(row.get('id')) for row in resources)
    identify = max(int(row.get('value')) for row in config.findall(".//metadata[@key='identify_id']"))
    additions = {}
    for index, path in enumerate(clips):
        child_id, object_id = str(last + index*2 + 1), str(last + index*2 + 2)
        target = f'/3D/Objects/b21_board_clip_{index+1}.model'
        mesh = trimesh.load_mesh(path)
        native = etree.fromstring(replace_mesh(source, mesh))
        native_object = native.find(f".//{CORE}object")
        native_object.set('id', child_id)
        native_object.set(PRODUCTION+'UUID', str(uuid5(NAMESPACE_URL, f'r5-b21/{path.name}/mesh')))
        new_resource, new_item, obj, new_slot = map(deepcopy, (resource, item, template, slot))
        new_component = new_resource.find('.//' + CORE + 'component')
        part = obj.find('part')
        part.set('id', child_id)
        new_component.set('objectid', child_id)
        new_component.set(PRODUCTION + 'path', target)
        new_resource.set('id', object_id)
        new_item.set('objectid', object_id)
        obj.set('id', object_id)
        new_slot.find("metadata[@key='object_id']").set('value', object_id)
        new_slot.find("metadata[@key='identify_id']").set('value', str(identify + index + 1))
        for label, element in (('resource', new_resource), ('component', new_component), ('item', new_item)):
            element.set(PRODUCTION+'UUID', str(uuid5(NAMESPACE_URL, f'r5-b21/{path.name}/{label}')))
        part.set('uuid', str(uuid5(NAMESPACE_URL, f'r5-b21/{path.name}/part')))
        name_part(obj, part, path.name, len(mesh.faces))
        matrix = part.find("metadata[@key='matrix']")
        local = np.fromstring(matrix.get('value'), sep=' ').reshape(4, 4)
        placed = np.fromstring(new_item.get('transform'), sep=' ')
        if not np.allclose(local[:3, :3], np.eye(3)) or not np.allclose(placed[:9], np.eye(3).reshape(-1)):
            raise ValueError('The B20 board-carrier template is rotated')
        xy = np.array([74. + index*16., 75.])
        placed[9:11] += xy - local[:2, 3]
        local[:2, 3] = xy
        matrix.set('value', ' '.join(f'{value:.9g}' for value in local.ravel()))
        new_item.set('transform', ' '.join(f'{value:.9g}' for value in placed))
        new_relation = deepcopy(relation)
        new_relation.set('Target', target)
        new_relation.set('Id', f'rel-b21-clip-{index+1}')
        relations.append(new_relation)
        resources.append(new_resource)
        build_items.append(new_item)
        config.insert(config.index(plate), obj)
        plate.append(new_slot)
        names[object_id] = path.name
        additions[target.lstrip('/')] = serialize(native)
    changes[MODEL_RELS] = serialize(relations)
    return additions


def remove_ballast_plate(base, model, config, changes):
    plate, = config.xpath("./plate[metadata[@key='plater_id'][@value='13']]")
    parts = template_parts(config)
    ballast = [parts[name][0] for name in ('43_neck_ballast_tray.stl', '44_ballast_cover.stl')]
    if {obj.get('id') for obj in ballast} != {
        slot.get('value') for slot in plate.findall("model_instance/metadata[@key='object_id']")
    }:
        raise ValueError('Optional plate contains unexpected parts')
    rels = etree.fromstring(changes.get(MODEL_RELS, base.read(MODEL_RELS)))
    deleted = set()
    for obj in ballast:
        remove_part(obj, model, config, rels, deleted)
    config.remove(plate)
    sequence_path = 'Metadata/filament_sequence.json'
    sequence = json.loads(base.read(sequence_path))
    del sequence['plate_13']
    cut_path = 'Metadata/cut_information.xml'
    cut = etree.fromstring(base.read(cut_path))
    for path in deleted:
        index = Path(path).stem.removeprefix('object_')
        cut.remove(cut.find(f"object[@id='{index}']"))
    changes.update({MODEL_RELS: serialize(rels), sequence_path: json.dumps(sequence, separators=(',', ':')).encode(),
                    cut_path: serialize(cut)})
    return deleted


def build(output, replacements, report, clips=(), support=(), *, source=BASE, revision='B21', without_ballast=False,
          normal_support=()):
    if output.resolve() == source.resolve():
        raise ValueError(f'Choose a separate {revision} project output')
    with ZipFile(source) as base:
        model = etree.fromstring(base.read(MODEL))
        config = etree.fromstring(base.read(MODEL_SETTINGS))
        old_parts = template_parts(config)
        changes = {}
        names = {}
        additions = add_board_clips(base, model, config, changes, names, clips) if clips else {}
        for old_name, (new_name, mesh) in replacements.items():
            obj, part = old_parts[old_name]
            object_id = obj.get('id')
            component = model.find(f".//{CORE}object[@id='{object_id}']//{CORE}component")
            path = component.get(PRODUCTION + 'path').lstrip('/')
            changes[path] = replace_mesh(base.read(path), mesh)
            name_part(obj, part, new_name, len(mesh.faces))
            if old_name in support:
                setting = obj.find("metadata[@key='enable_support']")
                if setting is None:
                    setting = etree.SubElement(obj, 'metadata', key='enable_support')
                setting.set('value', '1')
            if old_name in normal_support:
                setting = obj.find("metadata[@key='support_type']")
                if setting is None:
                    setting = etree.SubElement(obj, 'metadata', key='support_type')
                setting.set('value', 'normal(auto)')
            names[object_id] = new_name
        model.find(f"{CORE}metadata[@name='Title']").text = f'R5 {revision} P2S'
        deleted = remove_ballast_plate(base, model, config, changes) if without_ballast else set()
        changes[MODEL] = serialize(model)
        changes[MODEL_SETTINGS] = serialize(config)
        before = plate_signatures(base)
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, 'w') as package:
            for item in base.infolist():
                if item.filename not in deleted:
                    data = changes[item.filename] if item.filename in changes else base.read(item)
                    package.writestr(copy(item), data)
            for path, data in additions.items():
                template = base.getinfo(MODEL)
                item = ZipInfo(path, date_time=template.date_time)
                package.writestr(item, data, compress_type=template.compress_type)
        with ZipFile(output) as package:
            after = plate_signatures(package)
            profile_key = 'Metadata/project_settings.config'
            profile = package.read(profile_key)
            removed = {13} if without_ballast else set()
            if profile != base.read(profile_key) or before.keys() - removed != after.keys():
                raise ValueError('The source plate set or printer settings changed')
    changed = {number: [names[row[0]] for row in rows if row[0] in names]
               for number, rows in after.items() if before[number] != rows}
    if set(names.values()) != {name for parts in changed.values() for name in parts}:
        raise ValueError('One or more replacements did not change an installed print object')
    result = {'project_sha256': sha256(output.read_bytes()).hexdigest(),
              'profile_sha256': sha256(profile).hexdigest(),
              'plate_sha256': {number: plate_digest(rows) for number, rows in after.items()},
              'changed_plates': changed,
              f'identical_to_{source.parent.name}_plates': sorted(after.keys() - changed.keys())}
    if removed:
        result['removed_plates'] = sorted(removed)
    text = json.dumps(result, indent=2) + '\n'
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--print-dir', type=Path, help='The release directory with all B21 print meshes')
    parser.add_argument('--stl', action='append', default=[], metavar='B20_SOURCE=B21_FILE')
    parser.add_argument('--c3-clips', type=Path, nargs=2, metavar=('LEFT', 'RIGHT'))
    parser.add_argument('--with-support', action='append', default=[], metavar='B20_SOURCE')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    paths, clips, support = {}, args.c3_clips or (), set(args.with_support)
    if args.print_dir:
        if args.stl or args.c3_clips:
            parser.error('use either the release directory or individual changes')
        paths = {name: args.print_dir / target for name, target in RELEASE_PARTS.items()}
        clips = tuple(args.print_dir / name for name in BOARD_CLIPS)
        support.update(BLINK_SUPPORT)
    for pair in args.stl:
        old_name, sep, incoming = pair.partition('=')
        if not sep or old_name in paths or not incoming:
            parser.error(f'expected one replacement per source in {pair!r}')
        paths[old_name] = Path(incoming)
    if not paths and not clips:
        parser.error('supply at least one replacement')
    if support - paths.keys():
        parser.error('support overrides must target replacement parts')
    parts = {name: (path.name, trimesh.load_mesh(path)) for name, path in paths.items()}
    build(args.output, parts, args.report, clips, support)
