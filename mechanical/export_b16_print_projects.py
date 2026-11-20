"""Refresh Bambu print projects from the B16 solids, keeping the B15 P2S layout."""
from argparse import ArgumentParser
from pathlib import Path
import re
import sys
from xml.etree import ElementTree as XML
from zipfile import ZIP_DEFLATED, ZipFile

import FreeCAD as App
import MeshPart
import numpy as np
import trimesh

from fixtures import cable_wall_fixture

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'physics'))
from export_cad import world_shape

MODEL = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
PATH = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}path'
IDENTITY = '1 0 0 0 1 0 0 0 1 0 0 0'
SETTINGS = 'Metadata/model_settings.config'
PROFILE = 'Metadata/project_settings.config'
LABELS = {
    '01_base_cup_B8_1': 'Part000',
    '04_yaw_rotor_1': 'Part007',
    '40_captive_cable_tray_1': 'CableSaddle',
    'Cable_lock_wall_fixture_1': 'wall-fixture',
}


def meshes(cad):
    doc = App.openDocument(str(cad.resolve()))
    try:
        shapes = {name: world_shape(doc.getObject(name)) for name in LABELS.values()
                  if name != 'wall-fixture'}
        shapes['wall-fixture'] = cable_wall_fixture(shapes['Part000'])
        result = {}
        for key, shape in shapes.items():
            mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=.075,
                                          AngularDeflection=.10, Relative=False)
            vertices, faces = mesh.Topology
            result[key] = trimesh.Trimesh(vertices=[tuple(v) for v in vertices], faces=faces)
        return result
    finally:
        App.closeDocument(doc.Name)


def metadata(node, key):
    return node.find(f"metadata[@key='{key}']")


def mesh_xml(vertices, faces):
    text = ['<mesh>', ' <vertices>']
    text.extend(f'  <vertex x="{x:.9g}" y="{y:.9g}" z="{z:.9g}"/>' for x, y, z in vertices)
    text.extend((' </vertices>', ' <triangles>'))
    text.extend(f'  <triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
    text.extend((' </triangles>', '</mesh>'))
    return '\n'.join(text).encode('ascii')


def replace_parts(archive, baseline, revised, wanted):
    model = XML.fromstring(archive.read('3D/3dmodel.model'))
    settings = XML.fromstring(archive.read(SETTINGS))
    outputs = {}
    updated = set()
    for row in settings.findall('object'):
        label = metadata(row, 'name').get('value')
        if label not in wanted:
            continue
        key = LABELS[label]
        obj = model.find(f"{MODEL}resources/{MODEL}object[@id='{row.get('id')}']")
        component, = obj.findall(f'{MODEL}components/{MODEL}component')
        transform = np.fromstring(component.get('transform', IDENTITY), sep=' ')
        if len(transform) != 12 or not np.allclose(transform[:9], np.eye(3).ravel()):
            raise ValueError(f'{label} has a rotated component')
        path = component.get(PATH).lstrip('/')
        original = archive.read(path)
        embedded = XML.fromstring(original)
        m, = embedded.iter(f'{MODEL}mesh')
        triangles = m.findall(f'{MODEL}triangles/{MODEL}triangle')
        if any(set(t.attrib) != {'v1', 'v2', 'v3'} for t in triangles):
            raise ValueError(f'{label} has painted facets that require remapping')
        old_vertices = np.array([[float(v.get(axis)) for axis in 'xyz']
                                 for v in m.findall(f'{MODEL}vertices/{MODEL}vertex')])
        old_bounds = np.array([old_vertices.min(axis=0), old_vertices.max(axis=0)])
        old_cad = baseline[key]
        new_cad = revised[key]
        # Align to the existing component origin so the plate transforms stay valid.
        if (not np.allclose(old_bounds[1]-old_bounds[0], old_cad.extents, atol=.04)
                or not new_cad.is_volume):
            raise ValueError(f'{label} has a different print orientation or an invalid B16 mesh')
        offset = old_cad.bounds.mean(axis=0) - old_bounds.mean(axis=0)
        rewritten, count = re.subn(rb'<mesh>.*?</mesh>', lambda _: mesh_xml(
            new_cad.vertices-offset, new_cad.faces), original, flags=re.S)
        if count != 1 or path in outputs:
            raise ValueError(f'{label} has an unexpected mesh structure')
        outputs[path] = rewritten
        face_count = str(len(new_cad.faces))
        row.find('metadata[@face_count]').set('face_count', face_count)
        part, = row.findall('part')
        part.find('mesh_stat').set('face_count', face_count)
        source = metadata(part, 'source_file')
        source.set('value', 'B16_' + source.get('value'))
        updated.add(label)
    if updated != wanted:
        raise ValueError(f'Missing print parts {wanted-updated}')
    outputs[SETTINGS] = XML.tostring(settings, encoding='utf-8', xml_declaration=True)
    return outputs


def export(cad, output):
    baseline = meshes(HERE / 'R5-B15-Assembly.FCStd')
    revised = meshes(cad)
    output.mkdir(parents=True, exist_ok=True)
    for group in ('', 'Fit-'):
        wanted = {label for label, key in LABELS.items() if (
            key in ('CableSaddle', 'wall-fixture') if group else key != 'wall-fixture')}
        with ZipFile(HERE / f'R5-B15-{group}P2S.3mf') as layout:
            changed = replace_parts(layout, baseline, revised, wanted)
            for printer in ('P1S', 'P2S'):
                name = f'R5-B16-{group}{printer}.3mf'
                with ZipFile(HERE / f'R5-B15-{group}{printer}.3mf') as template:
                    changed[PROFILE] = template.read(PROFILE)
                pending = output / f'{name}.pending'
                with ZipFile(pending, 'w', compression=ZIP_DEFLATED, compresslevel=6) as result:
                    for filename in layout.namelist():
                        result.writestr(filename, changed[filename] if filename in changed
                                        else layout.read(filename))
                pending.replace(output / name)
                print(output / name, flush=True)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--cad', type=Path, default=HERE / 'revisions/b16/R5-B16-Wiring.FCStd')
    parser.add_argument('--output', type=Path, required=True)
    export(**vars(parser.parse_args()))
