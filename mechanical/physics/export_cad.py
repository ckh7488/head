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
    # Setting the copy's placement re-expresses its points in world coordinates. The earlier
    # transform by parent × own⁻¹ left meshes that carry their own placement inside a moving
    # group (the 30 jaw and 38 drive arm under JawMotion) about 2 mm off the motor axis.
    mesh = obj.Mesh.copy()
    mesh.Placement = obj.getGlobalPlacement()
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
        world_hashes = {}
        if include_world:
            world.mkdir(exist_ok=True)
        hub_parts = {part.Name for part in doc.HubInstalled.Group + doc.HubCableSpace.Group}
        records = []
        for obj in doc.Objects:
            group = getattr(obj, 'Motion', None)
            shape = world_shape(obj) if obj.TypeId == 'Part::Feature' else None
            mesh = world_mesh(obj) if obj.TypeId == 'Mesh::Feature' else None
            if include_world and (shape is not None or mesh is not None):
                motion_by_part[obj.Name] = group or ('hatch' if obj.Name in hub_parts else 'fixed')
                part_file = world/f'{obj.Name}.stl'
                (mesh if mesh is not None else tessellate(shape)).write(str(part_file))
                world_hashes[obj.Name] = sha256(part_file.read_bytes()).hexdigest()
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
                  'world_motion': motion_by_part, 'world_sha256': world_hashes, 'parts': records}
        (output/'cad_parts.json').write_text(json.dumps(masses, ensure_ascii=False, indent=2))
        doc.Part063.Shape.exportStep(str(output/'blink_rail.step'))
        doc.CableSaddle.Shape.exportStep(str(output/'cable_saddle.step'))
        if doc.getObject('CableGate'):
            doc.CableGate.Shape.exportStep(str(output/'cable_gate.step'))
        if doc.getObject('BallastTray'):
            doc.BallastTray.Shape.exportStep(str(output/'ballast_tray.step'))
        for name in ('Part073', 'Part074'):
            world_mesh(doc.getObject(name)).write(str(output/f'{name}.stl'))
        print(f'{len(records)} moving CAD parts and {len(motion_by_part)} world meshes exported')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--cad', type=Path, default=HERE.parent/'R5-B15-Assembly.FCStd')
    parser.add_argument('--world', action='store_true', help='Export world meshes for the clearance sweep')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    extract(args.cad.resolve(), args.output.resolve(), args.world)
