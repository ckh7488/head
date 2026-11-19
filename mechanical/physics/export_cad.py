"""Export the physical check inputs from the FreeCAD assembly, in millimetres.

Run with FreeCAD's Python modules available. The output directory is scratch data.
"""
from argparse import ArgumentParser
from hashlib import sha256
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


def tessellate(shape):
    return MeshPart.meshFromShape(Shape=shape, LinearDeflection=.045, AngularDeflection=.12, Relative=False)


def extract(path, output, include_world):
    output.mkdir(parents=True, exist_ok=True)
    doc = App.openDocument(str(path))
    try:
        doc.recompute()
        motion_geometry = json.loads(doc.R5.MotionGeometry)
        case = world_shape(doc.Part041).BoundBox
        motion_geometry['blink']['obstacles'] = [
            ['eye_pitch_motor', list(case.Center), [case.XLength/2, case.YLength/2, case.ZLength/2]],
            ['rear_frame', [0., 27., 146.], [63., 4., 9.]],
        ]
        world = output/'world'
        motion_by_part = {}
        if include_world:
            world.mkdir(exist_ok=True)
        records = []
        for obj in doc.Objects:
            group = getattr(obj, 'Motion', None)
            shape = world_shape(obj) if obj.TypeId == 'Part::Feature' else None
            mesh = world_mesh(obj) if obj.TypeId == 'Mesh::Feature' else None
            if include_world and (shape is not None or mesh is not None):
                motion_by_part[obj.Name] = group or ('hatch' if obj in doc.HubInstalled.Group else 'fixed')
                (mesh if mesh is not None else tessellate(shape)).write(str(world/f'{obj.Name}.stl'))
            if not group or group == 'fixed':
                continue
            row = {'name': obj.Name, 'label': obj.Label, 'motion': group,
                   'printed': bool(getattr(obj, 'Printed', False)),
                   'reference_g': float(getattr(obj, 'EstimatedGrams', 0.))}
            if shape is not None:
                row['solids'] = [solid_properties(s) for s in shape.Solids if s.Volume > 1e-8]
            elif mesh is not None:
                mesh.write(str(output/f'{obj.Name}.stl'))
                row['mesh'] = f'{obj.Name}.stl'
                row['mesh_volume_mm3'] = abs(mesh.Volume)
            else:
                continue
            records.append(row)
        hinge = doc.JawMotion.Placement.Base
        masses = {'source_sha256': sha256(path.read_bytes()).hexdigest(),
                  'jaw_pivot_mm': list(hinge), 'motion_geometry': motion_geometry,
                  'world_motion': motion_by_part, 'parts': records}
        (output/'cad_parts.json').write_text(json.dumps(masses, ensure_ascii=False, indent=2))
        doc.CableSaddle.Shape.exportStep(str(output/'cable_saddle.step'))
        for name in ('Part073', 'Part074'):
            world_mesh(doc.getObject(name)).write(str(output/f'{name}.stl'))
        print(f'{len(records)} moving CAD parts and {len(motion_by_part)} world meshes exported')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--cad', type=Path, default=HERE.parent/'R5-B3-Assembly.FCStd')
    parser.add_argument('--world', action='store_true', help='Export world meshes for the clearance sweep')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    extract(args.cad.resolve(), args.output.resolve(), args.world)
