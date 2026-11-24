"""Register the B25 one-shot print reinforcements in the native assembly."""

from argparse import ArgumentParser
from pathlib import Path
from zipfile import ZipFile

import FreeCAD as App
import Mesh
import numpy as np
import Part
import trimesh

from build_b19_review_fixes import replace
from build_b25_large_bearing_variants import source_mesh


# These are the original centered print frames, before the local reinforcements.
PRINT_FRAMES = {
    "Part001": ("02_outer_bearing_seat-B23.stl", (0., 0., -43.), (1, 1, 1)),
    "YawStopPadLeft": ("YawStopPadLeft.stl", (-49.58996, 23.23555, -34.35), (1, 1, 1)),
    "YawStopPadRight": ("YawStopPadRight.stl", (49.58995, 23.23555, -34.35), (1, 1, 1)),
    "YawBearingRetainer1": ("41_outer_race_keeper.stl", (54.75, 0., -35.675), (1, -1, -1)),
    "ID5EHKeeper": ("ID5-keeper-B21.stl", (14.800513, 20.875, 89.3), (1, 1, 1)),
}
C3_EXCLUDED = ('Part070', 'Part071', 'C3Clamp0', 'C3Clamp1', 'c3Bolt0', 'c3Bolt1', 'c3Nut0', 'c3Nut1')


def solid_from_print(archive, filename, offset, axes):
    vertices, faces, _ = source_mesh(archive, filename)
    mesh = trimesh.Trimesh(vertices * axes + offset, faces, process=True)
    if not mesh.is_volume or mesh.body_count != 1 or not mesh.nondegenerate_faces().all():
        raise ValueError(f"{filename} must be one closed print body")
    native = Mesh.Mesh(mesh.triangles.tolist())
    skin = Part.Shape()
    skin.makeShapeFromMesh(native.Topology, 1e-6)
    result = Part.makeSolid(skin).removeSplitter()
    if not result.isValid() or len(result.Solids) != 1 or result.Volume <= 0.:
        raise ValueError(f"{filename} did not form a valid assembly solid")
    return result


def build(cad, project, output):
    if cad.resolve() == output.resolve():
        raise ValueError("Write the candidate assembly to a separate file")
    doc = App.openDocument(str(cad.resolve()))
    try:
        with ZipFile(project) as archive:
            shapes = {part: solid_from_print(archive, *frame) for part, frame in PRINT_FRAMES.items()}
        keeper = shapes['YawBearingRetainer1']
        for index in (2, 3):
            shapes[f'YawBearingRetainer{index}'] = keeper.copy().rotate(
                App.Vector(), App.Vector(0., 0., 1.), 120. * (index - 1))
        for part, shape in shapes.items():
            replace(doc.getObject(part), shape)
        for part in C3_EXCLUDED:
            if doc.getObject(part) is not None:
                doc.removeObject(part)
        doc.recompute()
        doc.saveAs(str(output.resolve()))
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for name in ('cad', 'project', 'output'):
        parser.add_argument(name, type=Path)
    build(**vars(parser.parse_args()))
