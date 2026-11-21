"""Check seated mesh contacts against the native commercial motor solids."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import FreeCAD as App
import numpy as np
import trimesh

from export_cad import tessellate, world_shape


THREADS = {
    **{f'BlinkHornScrew{i}': 'Part045' for i in range(2)},
    **{f'EyePitchHornScrew{i}': 'Part041' for i in range(2)},
    **{f'EyeYawHornScrew{i}': 'Part038' for i in range(3)},
    **{f'JawHornScrew{i}': 'Jaw_XL330_M288_Jaw' for i in range(2)},
    **{f'XL430YawSide{side}{i}': 'Part017' for side in 'LR' for i in range(2)},
    **{f'XL430Pitch{kind}{i}': 'Part018' for kind in ('Keeper', 'Side') for i in range(2)},
}
PORTS = {'HarnessID1EH': 'Part038', 'HarnessID6EH': 'Jaw_XL330_M288_Jaw'}


def digest(path):
    with path.open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def jaw_mesh_volume(cad, name, motor, temporary):
    path = cad/'world'/f'{name}.stl'
    printed = trimesh.load_mesh(path)
    if not printed.is_volume:
        raise ValueError(f'Unclosed printed mesh: {name}')
    volume = 0.
    for solid in motor.Solids:
        box = solid.BoundBox
        low = (box.XMin, box.YMin, box.ZMin)
        high = (box.XMax, box.YMax, box.ZMax)
        if np.any(printed.bounds[1] < low) or np.any(printed.bounds[0] > high):
            continue
        tessellate(solid).write(str(temporary))
        component = trimesh.load_mesh(temporary)
        if not component.is_volume:
            raise ValueError(f'Unclosed motor component for {name}')
        volume += abs(printed.intersection(component, engine='manifold').volume)
    return float(volume)


def native_volume(first, second):
    shapes = [world_shape(obj) for obj in (first, second)]
    if any(not shape.Solids or not shape.isValid() for shape in shapes):
        raise ValueError(f'Unresolved native solid: {first.Name} / {second.Name}')
    overlap = shapes[0].common(shapes[1])
    if not (overlap.isNull() or overlap.isValid()):
        raise ValueError(f'Unresolved native intersection: {first.Name} / {second.Name}')
    return float(overlap.Volume)


def check(assembly, baseline, cad, contacts):
    cad_sha = digest(assembly)
    manifest = json.loads((cad/'cad_parts.json').read_text())
    if cad_sha != manifest['source_sha256']:
        raise ValueError('CAD mesh and assembly identity differ')
    pairs = [row for row in json.loads(contacts.read_text()) if row['mm3'] is None]
    thread_pairs = {frozenset((screw, motor)) for screw, motor in THREADS.items()}
    port_pairs = {frozenset((plug, motor)) for plug, motor in PORTS.items()}
    current = App.openDocument(str(assembly.resolve()))
    reference = App.openDocument(str(baseline.resolve()))
    result = []
    try:
        with TemporaryDirectory() as tmp:
            for row in pairs:
                names = (row['a'], row['b'])
                pair = frozenset(names)
                a, b = (current.getObject(name) for name in names)
                if a.isDerivedFrom('Mesh::Feature'):
                    volume = jaw_mesh_volume(cad, a.Name, world_shape(b), Path(tmp)/'motor.stl')
                else:
                    volume = native_volume(a, b)
                if pair in thread_pairs or pair in port_pairs:
                    old = native_volume(*(reference.getObject(name) for name in names))
                    status = 'stock_thread' if pair in thread_pairs else 'stock_connector_envelope'
                    if abs(volume-old) > .05:
                        raise ValueError(f'Changed stock mate: {names}')
                    result.append(dict(pair=names, status=status, overlap_mm3=volume, b23_overlap_mm3=old))
                elif volume <= .05:
                    result.append(dict(pair=names, status='clear', overlap_mm3=volume))
                else:
                    raise ValueError(f'Seated interference: {names} ({volume:.3f} mm³)')
    finally:
        App.closeDocument(reference.Name)
        App.closeDocument(current.Name)
    return {'cad_sha256': cad_sha, 'baseline_cad_sha256': digest(baseline),
            'contact_report_sha256': digest(contacts), 'pairs': result,
            'scope': 'Printed parts and stock motor solids are checked separately. Threads and JST plug boxes '
                     'model their occupied envelopes at the catalog mating interface.'}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('assembly', type=Path)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('cad', type=Path)
    parser.add_argument('contacts', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    report = check(args.assembly, args.baseline, args.cad, args.contacts)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
