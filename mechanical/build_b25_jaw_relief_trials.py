"""Reproduce B25 fixed-guide and stay-corner trial geometries from the exact keeper fragment."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path

import FreeCAD as App
import Mesh  # Registers Mesh::Feature before opening the assembly.
import Part
import manifold3d as md
import numpy as np

from build_b19_review_fixes import add_part, replace
from build_b22_fused_skull import solid
from build_b25_jaw_retention import mesh_from_solid, replace_mesh
from check_b25_jaw_retention import geometry
from export_cad import world_shape

RIGHT_STAY = 'Jaw_37_right_jaw_bearing_stay'
LEFT_STAY = 'Jaw_36_left_jaw_servo_stay'
KEEPER_NAMES = frozenset((
    'JawExteriorScrewLeft', 'JawExteriorInsertLeft', 'JawExteriorScrewRight',
    'JawExteriorInsertRight', 'JawAntiRockScrew', 'JawAntiRockInsert',
))


def digest(path):
    with path.open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def saw_mesh(obj, boxes, keep_receivers):
    original = solid(geometry(obj))
    if original.status() != md.Error.NoError or original.is_empty():
        raise ValueError(f'{obj.Name} has an open source mesh')
    result = original
    for low, high in boxes:
        cutter = md.Manifold.cube(np.subtract(high, low)).translate(low)
        result -= cutter
    if keep_receivers and obj.Name in (LEFT_STAY, RIGHT_STAY):
        x, y = (-70.5, -32.5) if obj.Name == LEFT_STAY else (63., -8.75)
        sleeve = md.Manifold.cylinder(10., keep_receivers, circular_segments=72)
        sleeve = sleeve.rotate((0., 90., 0.)).translate((x, y, 103.5))
        result += original ^ sleeve
    mesh = mesh_from_solid(result)
    if not mesh.is_volume or mesh.body_count != 1:
        raise ValueError(f'{obj.Name} must remain one watertight printable solid')
    return mesh, float(original.volume() - result.volume())


def saw_solid(obj, boxes):
    original = world_shape(obj)
    result = original.copy()
    for low, high in boxes:
        cutter = Part.makeBox(*np.subtract(high, low), App.Vector(*low))
        result = result.cut(cutter).removeSplitter()
    if not result.isValid() or len(result.Solids) != 1:
        raise ValueError(f'{obj.Name} must remain one valid solid')
    return result, float(original.Volume - result.Volume)


def assemble(doc, review, options):
    cut_boxes = options['cut_boxes_world_mm']
    keep_receivers = options.get('receiver_keep_radius_mm')
    removed = {}
    for source in review.Objects:
        name = source.Name
        destination = doc.getObject(name)
        if destination is None:
            if name not in KEEPER_NAMES:
                raise ValueError(f'Unexpected fragment object {name}')
            add_part(doc, doc.Part019.getParentGeoFeatureGroup(), name, source.Label, world_shape(source), 'head')
        elif source.TypeId == 'Mesh::Feature':
            mesh, removal = saw_mesh(source, cut_boxes[name], keep_receivers) if name in cut_boxes else (geometry(source), 0.)
            replace_mesh(destination, mesh)
            removed[name] = removal
        else:
            shape, removal = saw_solid(source, cut_boxes[name]) if name in cut_boxes else (world_shape(source), 0.)
            replace(destination, shape)
            removed[name] = removal
    if 'Part011' in cut_boxes:
        yoke, removed['Part011'] = saw_solid(doc.Part011, cut_boxes['Part011'])
        replace(doc.Part011, yoke)
    doc.recompute()
    return removed


def build(source, review, output, options):
    if output.resolve() in (source.resolve(), review.resolve()):
        raise ValueError('Choose a separate trial output')
    doc = App.openDocument(str(source.resolve()))
    fragment = App.openDocument(str(review.resolve()))
    try:
        removed = assemble(doc, fragment, options)
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(output.resolve()))
    finally:
        App.closeDocument(fragment.Name)
        App.closeDocument(doc.Name)
    return {
        'source_cad_sha256': digest(source),
        'review_fragment_sha256': digest(review),
        'trial_cad_sha256': digest(output),
        'geometry': options,
        'removed_local_material_mm3': removed,
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for field in ('source', 'review', 'output', 'options'):
        parser.add_argument(field, type=Path)
    parser.add_argument('trial')
    args = parser.parse_args()
    options = json.loads(args.options.read_text())[args.trial]
    report = build(args.source, args.review, args.output, options)
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
