"""Export the physical check inputs from the B2 FreeCAD assembly, in mm.

Run with FreeCAD's Python modules available. The output directory is scratch data.
"""
from argparse import ArgumentParser
from hashlib import sha256
from math import cos, radians, sin
from pathlib import Path
import json

import FreeCAD as App
import MeshPart

HERE = Path(__file__).resolve().parent


def world_shape(obj):
    shape = obj.Shape.copy()
    shape.Placement = obj.getGlobalPlacement()
    return shape


def world_mesh(obj):
    mesh = obj.Mesh.copy()
    world_from_parent = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
    mesh.transform(world_from_parent.toMatrix())
    return mesh


def solid_properties(solid):
    moment = solid.MatrixOfInertia
    return {
        'volume': solid.Volume,
        'center': list(solid.CenterOfMass),
        'inertia': [[moment.A11, moment.A12, moment.A13],
                    [moment.A21, moment.A22, moment.A23],
                    [moment.A31, moment.A32, moment.A33]],
    }


def link_contact_sweep(link, motor):
    pitch_motor_solids = list(motor.Solids)
    cases = []
    for offset in (-.4, 0., .4):
        for angle in range(0, 91, 2):
            theta = radians(angle)
            moving = link.copy().translate(App.Vector(0, 8.25*(cos(theta)-1), 8.25*sin(theta)+offset))
            volume = sum(moving.common(part).Volume for part in pitch_motor_solids
                         if moving.BoundBox.intersect(part.BoundBox))
            cases.append({'angle_deg': angle, 'vertical_offset_mm': offset, 'overlap_mm3': round(volume, 5)})
    return cases


def extract(path, output):
    output.mkdir(parents=True, exist_ok=True)
    doc = App.openDocument(str(path))
    try:
        doc.recompute()
        records = []
        for obj in doc.Objects:
            group = getattr(obj, 'Motion', None)
            if not group or group == 'fixed':
                continue
            row = {'name': obj.Name, 'label': obj.Label, 'motion': group,
                   'printed': bool(getattr(obj, 'Printed', False)),
                   'reference_g': float(getattr(obj, 'EstimatedGrams', 0.))}
            if obj.TypeId == 'Part::Feature':
                row['solids'] = [solid_properties(s) for s in world_shape(obj).Solids if s.Volume > 1e-8]
            elif obj.TypeId == 'Mesh::Feature':
                mesh = world_mesh(obj)
                mesh.write(str(output/f'{obj.Name}.stl'))
                row['mesh'] = f'{obj.Name}.stl'
                row['mesh_volume_mm3'] = abs(mesh.Volume)
            else:
                continue
            records.append(row)
        hinge = doc.JawMotion.Placement.Base
        masses = {'source_sha256': sha256(path.read_bytes()).hexdigest(),
                  'jaw_pivot_mm': list(hinge), 'parts': records}
        (output/'cad_parts.json').write_text(json.dumps(masses, ensure_ascii=False, indent=2))
        doc.CableSaddle.Shape.exportStep(str(output/'cable_saddle.step'))
        for name in ('Part073', 'Part074'):
            world_mesh(doc.getObject(name)).write(str(output/f'{name}.stl'))
        motor = world_shape(doc.Part041)
        for i, solid in enumerate(motor.Solids):
            bound = solid.BoundBox
            if bound.XMin < 48.75 and bound.XMax > 45.85 and solid.Volume > 10:
                mesh = MeshPart.meshFromShape(Shape=solid, LinearDeflection=.045, AngularDeflection=.09, Relative=False)
                mesh.write(str(output/f'blink_motor_{i:02}.stl'))
        contacts = link_contact_sweep(world_shape(doc.Part060), motor)
        (output/'blink_cad_contact.json').write_text(json.dumps(contacts, indent=2))
        print(f'{len(records)} moving CAD parts and {len(contacts)} exact link positions exported')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--cad', type=Path, default=HERE.parent/'R5-B2-Assembly.FCStd')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    extract(args.cad.resolve(), args.output.resolve())
