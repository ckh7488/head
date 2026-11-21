"""Print the front skull and nose tray as one part while retaining both CAD references."""

from argparse import ArgumentParser
from copy import copy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
import manifold3d
import numpy as np
import trimesh

from build_b21_print import (
    CORE, MODEL, MODEL_RELS, MODEL_SETTINGS, PRODUCTION, name_part, plate_signatures,
    remove_part, serialize, template_parts,
)


FUSED_SKULL = '28_skull_front_with_camera_tray-B22.stl'
TRAY = '25_nasal_tray-B22.stl'


def solid(mesh):
    return manifold3d.Manifold(manifold3d.Mesh64(
        np.ascontiguousarray(mesh.vertices, dtype=np.float64),
        np.ascontiguousarray(mesh.faces, dtype=np.uint64)))


def fuse(skull_world, tray_world, tray_print):
    shell = trimesh.load_mesh(skull_world)
    pieces = sorted(shell.split(only_watertight=False), key=lambda piece: len(piece.faces), reverse=True)
    shell, *discarded = pieces
    if not shell.is_volume or sum(abs(piece.volume) for piece in discarded) > .001:
        raise ValueError('The front skull has material outside its main closed shell')
    shell = trimesh.load_mesh(BytesIO(shell.export(file_type='stl')), file_type='stl')
    tray = trimesh.load_mesh(tray_print)
    positioned = trimesh.load_mesh(tray_world)
    x, y = positioned.bounds.mean(axis=0)[:2]
    tray.apply_translation((x, y, positioned.bounds[0, 2]))
    if not tray.is_volume or not np.allclose(tray.bounds, positioned.bounds, atol=.00002, rtol=0.):
        raise ValueError('The printable tray does not match its assembled CAD position')

    joined = (solid(shell) + solid(tray)).rotate((-90., 0., 0.)).simplify(.0003)
    ordered = sorted(joined.decompose(), key=lambda item: item.volume(), reverse=True)
    joined, *discarded = ordered
    if joined.status() != manifold3d.Error.NoError or sum(abs(item.volume()) for item in discarded) > .001:
        raise ValueError('The skull and tray did not fuse into one printed body')
    native = joined.to_mesh64()
    mesh = trimesh.Trimesh(native.vert_properties[:, :3], native.tri_verts, process=False)
    if not mesh.is_volume or mesh.body_count != 1:
        raise ValueError('The fused indexed mesh must bound one positive solid')
    return mesh


def build(source, skull_world, tray_world, tray_print, output):
    if source.resolve() == output.resolve():
        raise ValueError('Write to a different project from the source')
    mesh = fuse(skull_world, tray_world, tray_print)
    with ZipFile(source) as project:
        model = etree.fromstring(project.read(MODEL))
        config = etree.fromstring(project.read(MODEL_SETTINGS))
        relationships = etree.fromstring(project.read(MODEL_RELS))
        parts = template_parts(config)
        shell, part = parts['28_skull_front.stl']
        component = model.find(f".//{CORE}object[@id='{shell.get('id')}']//{CORE}component")
        slot = component.get(PRODUCTION + 'path').lstrip('/')
        replacement = etree.fromstring(project.read(slot))
        body = replacement.find('.//' + CORE + 'mesh')
        vertices = body.find(CORE + 'vertices')
        triangles = body.find(CORE + 'triangles')
        previous = np.array([[float(point.get(axis)) for axis in 'xyz'] for point in vertices])
        if not np.allclose(np.ptp(previous, axis=0), mesh.extents, atol=.035, rtol=0.):
            raise ValueError('Fusing the tray moved the front skull print bounds')
        offset = (previous.max(axis=0) + previous.min(axis=0)) / 2 - mesh.bounds.mean(axis=0)
        offset[2] = previous[:, 2].min() - mesh.bounds[0, 2]
        vertices.clear()
        triangles.clear()
        # Preserve the indexed seam directly in 3MF at higher precision than binary STL.
        for x, y, z in mesh.vertices + offset:
            etree.SubElement(vertices, CORE + 'vertex', x=f'{x:.14g}', y=f'{y:.14g}', z=f'{z:.14g}')
        for a, b, c in mesh.faces:
            etree.SubElement(triangles, CORE + 'triangle', v1=str(a), v2=str(b), v3=str(c))
        name_part(shell, part, FUSED_SKULL, len(mesh.faces))
        removed = set()
        remove_part(parts[TRAY][0], model, config, relationships, removed)

        cut_path = 'Metadata/cut_information.xml'
        cuts = etree.fromstring(project.read(cut_path))
        for path in removed:
            index = Path(path).stem.removeprefix('object_')
            note = cuts.find(f"object[@id='{index}']")
            if note is not None:
                cuts.remove(note)
        updates = {slot: serialize(replacement), MODEL: serialize(model), MODEL_SETTINGS: serialize(config),
                   MODEL_RELS: serialize(relationships), cut_path: serialize(cuts)}
        before = plate_signatures(project)
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, 'w') as revised:
            for item in project.infolist():
                if item.filename not in removed:
                    data = updates[item.filename] if item.filename in updates else project.read(item)
                    revised.writestr(copy(item), data)
    with ZipFile(output) as revised:
        after = plate_signatures(revised)
    if before.keys() != after.keys() or [plate for plate in before if before[plate] != after[plate]] != [4, 12]:
        raise ValueError('The fused skull changed unexpected print plates')
    print(sha256(output.read_bytes()).hexdigest(), output)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for name in ('source', 'skull_world', 'tray_world', 'tray_print', 'output'):
        parser.add_argument(name, type=Path)
    build(**vars(parser.parse_args()))
