"""Relieve the right jaw side faces while retaining the pivot and opening stop."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

import FreeCAD as App
import manifold3d as md
import numpy as np

from build_b21_print import build as pack_prints
from build_b22_fused_skull import solid
from build_b25_bearing_fit import JAW as STAY_FILE, archived_mesh
from build_b25_jaw_retention import mesh_from_solid, replace_mesh
from check_b25_jaw_retention import geometry


ARM = 'Jaw_39_right_jaw_pivot_arm'
STAY = 'Jaw_37_right_jaw_bearing_stay'
JAW_PARTS = ('Jaw_30_moving_jaw', 'Jaw_38_left_jaw_drive_arm', ARM)
JAW_FILE = '30_38_39_jaw_one_piece-B20.3mf'
STAY_ROTATION = np.array(((0., 0., -1.), (0., 1., 0.), (1., 0., 0.)))


def box(low, high):
    return md.Manifold.cube(np.subtract(high, low)).translate(low)


def reliefs():
    collar = md.Manifold.cylinder(4., 4., circular_segments=96).rotate((0., 90., 0.)).translate((42.5, -9., 92.))
    arm = box((43.5, -28., 76.), (45.3, -1., 99.)) - collar
    stay = box((47.1, -11.8, 79.60), (49., -10.45, 81.28))
    return arm, stay, collar


def trimmed(mesh, cutter, label):
    source = solid(mesh)
    body = source - cutter
    result = mesh_from_solid(body)
    if (not result.is_volume or result.body_count != 1
            or not np.allclose(mesh.bounds, result.bounds, atol=1e-6, rtol=0.)):
        raise ValueError(f'{label} must remain one closed body with the original extent')
    return result, (source-body).volume()


def print_cutter(installed, archived, rotation, cutter):
    points = np.concatenate([mesh.vertices for mesh in installed]) @ rotation.T
    low, high = points.min(axis=0), points.max(axis=0)
    if not np.allclose(high-low, archived.extents, atol=.003, rtol=0.):
        raise ValueError('Installed jaw bounds do not match the original print orientation')
    return cutter.transform(np.column_stack((rotation, archived.bounds[0]-low)))


def apply(doc, project):
    arm_cut, stay_cut, collar = reliefs()
    stay_obj, arm_obj = doc.getObject(STAY), doc.getObject(ARM)
    stock_stay = geometry(stay_obj)
    moving = [geometry(doc.getObject(name)) for name in JAW_PARTS]
    new_arm, arm_removed = trimmed(moving[-1], arm_cut, ARM)
    new_stay, stay_removed = trimmed(stock_stay, stay_cut, STAY)
    if abs((solid(moving[-1]) ^ collar).volume()-(solid(new_arm.copy()) ^ collar).volume()) > 1e-6:
        raise ValueError('The right pivot bore or bearing collar changed')

    rotation = np.array(doc.Jaw_30_moving_jaw.getGlobalPlacement().inverse().toMatrix().A).reshape(4, 4)[:3, :3]
    replacements = {}
    with ZipFile(project) as archive:
        for name, plate, meshes, axes, cutter in (
            (JAW_FILE, 5, moving, rotation, arm_cut),
            (STAY_FILE, 9, [stock_stay], STAY_ROTATION, stay_cut),
        ):
            old, _ = archived_mesh(archive, name, plate)
            printable, _ = trimmed(old, print_cutter(meshes, old, axes, cutter), name)
            replacements[name] = (name, printable)
    replace_mesh(arm_obj, new_arm)
    replace_mesh(stay_obj, new_stay)
    return replacements, {'right_arm_removed_mm3': arm_removed, 'right_stay_removed_mm3': stay_removed}


def build(source, project, output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if output in (source.resolve().parent, project.resolve().parent):
        raise ValueError('Choose a separate output directory')
    doc = App.openDocument(str(source.resolve()))
    try:
        replacements, details = apply(doc, project)
        doc.recompute()
        doc.saveAs(str(output / source.name))
    finally:
        App.closeDocument(doc.Name)
    pack_prints(output / project.name, replacements, output / 'print-build.json',
                source=project, revision='B25', indexed_parts=replacements)
    details['source_cad_sha256'] = sha256(source.read_bytes()).hexdigest()
    details['cad_sha256'] = sha256((output / source.name).read_bytes()).hexdigest()
    (output / 'jaw-side-design.json').write_text(json.dumps(details, indent=2) + '\n')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for name in ('source', 'project', 'output'):
        parser.add_argument(name, type=Path)
    build(**vars(parser.parse_args()))
