"""Open the B25 yaw rotor guide locally for the thinner camera cable."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from math import cos, radians, sin
from pathlib import Path
from zipfile import ZipFile

import FreeCAD as App
import numpy as np
import Part

from build_b19_review_fixes import replace
from build_b21_print import build as pack_prints
from build_b22_fused_skull import solid
from build_b25_bearing_fit import archived_mesh
from build_b25_jaw_retention import mesh_from_solid
from check_b25_jaw_retention import from_topology
from export_cad import tessellate, world_shape


ROTOR_PRINT = '04_yaw_rotor-B23.stl'
CLEARANCE_MM = 3.05


def camera_crossing():
    start = App.Vector(0., -36.75, -50.)
    turn = radians(10.)

    def on_arc(angle):
        return App.Vector(0., -36.75 + 40.*(1.-cos(angle)), -39. + 40.*sin(angle))

    exit_point = on_arc(turn)
    tangent = App.Vector(0., sin(turn), cos(turn))
    end = exit_point + tangent*((-20.-exit_point.z)/tangent.z)
    return Part.Wire((Part.makeLine(start, on_arc(0.)),
                      Part.Arc(on_arc(0.), on_arc(turn/2.), exit_point).toShape(),
                      Part.makeLine(exit_point, end))), start


def apply(doc, project):
    original = world_shape(doc.Part007)
    path, start = camera_crossing()
    profile = Part.Wire([Part.makeCircle(CLEARANCE_MM, start, App.Vector(0., 0., 1.))])
    relief = path.makePipeShell([profile], True, False)
    cropped = original.cut(relief).removeSplitter()
    loss = original.Volume - cropped.Volume
    trial_gap = path.distToShape(cropped)[0]
    if (not cropped.isValid() or len(cropped.Solids) != 1
            or not 0. < loss < 4. or trial_gap < CLEARANCE_MM - .005):
        raise ValueError('The rotor relief must reproduce the local clearance and leave one valid solid')

    native = from_topology(tessellate(original))
    with ZipFile(project) as archive:
        stock, _ = archived_mesh(archive, ROTOR_PRINT, 8)
    if not np.allclose(native.extents, stock.extents, atol=.01, rtol=0.):
        raise ValueError('Native rotor and print do not share the expected orientation')
    tool = from_topology(tessellate(relief))
    tool.apply_translation(stock.bounds[0]-native.bounds[0])
    raw = solid(stock) - solid(tool)
    printable = mesh_from_solid(raw.simplify(.0002))
    if (not printable.is_volume or printable.body_count != 1
            or not np.allclose(stock.bounds, printable.bounds, atol=1e-6, rtol=0.)):
        raise ValueError('Relieved rotor must retain the existing print extent and one closed solid')
    replace(doc.Part007, cropped)
    return printable, {
        'path_radius_mm': 40.0, 'centerline_gap_before_mm': path.distToShape(original)[0],
        'centerline_gap_after_mm': trial_gap, 'removed_volume_mm3': loss,
        'removed_print_volume_mm3': float(stock.volume-printable.volume),
    }


def build(source, project, output):
    output = output.resolve()
    if output in (source.resolve().parent, project.resolve().parent):
        raise ValueError('Choose a separate output directory')
    output.mkdir(parents=True, exist_ok=True)
    doc = App.openDocument(str(source.resolve()))
    try:
        printable, details = apply(doc, project)
        doc.recompute()
        doc.saveAs(str(output / source.name))
    finally:
        App.closeDocument(doc.Name)
    pack_prints(output / project.name, {ROTOR_PRINT: (ROTOR_PRINT, printable)},
                output / 'print-build.json', source=project, revision='B25', indexed_parts=(ROTOR_PRINT,))
    details['source_cad_sha256'] = sha256(source.read_bytes()).hexdigest()
    details['cad_sha256'] = sha256((output / source.name).read_bytes()).hexdigest()
    (output / 'camera-rotor-relief.json').write_text(json.dumps(details, indent=2) + '\n')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for name in ('source', 'project', 'output'):
        parser.add_argument(name, type=Path)
    build(**vars(parser.parse_args()))
