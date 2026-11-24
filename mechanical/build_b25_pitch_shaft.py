"""Export and check the B25 shaft STEP at the pre-tapping machining state."""

from argparse import ArgumentParser
from math import isclose
from pathlib import Path

import FreeCAD as App
import Part

from build_b21_fasteners import detached_shape
from build_b24_pitch_coupler import DRIVE_HOLE_MM, DRIVE_SEAT, M3_FROM_INBOARD_MM
from build_b24_pitch_coupler import SHAFT_INBOARD_X, TAP_DRILL_MM, drive_shaft


REVISIONS = Path(__file__).resolve().parent / 'revisions'
SHAFT_BLANK = REVISIONS / 'b23/R5-B23-Assembly.FCStd'
B25_CAD = REVISIONS / 'b25/R5-B25-Assembly.FCStd'


def require_same_solid(actual, expected, label):
    if len(actual.Solids) != 1 or not actual.isValid():
        raise ValueError(f'{label} must be a single valid solid')
    if max(actual.cut(expected).Volume, expected.cut(actual).Volume) > 1e-7:
        raise ValueError(f'{label} differs from the expected geometry')


def radial_hole_diameter(shape, x):
    # At the clamp this selects the passage below the larger screw head pocket.
    return min(2. * surface.Radius for surface in (face.Surface for face in shape.Faces)
               if isinstance(surface, Part.Cylinder)
               and isclose(abs(surface.Axis.z), 1., abs_tol=1e-7)
               and isclose(surface.Center.x, x, abs_tol=1e-7)
               and isclose(surface.Center.y, 0., abs_tol=1e-7))


def export(cad, output):
    blank_doc = App.openDocument(str(SHAFT_BLANK))
    try:
        blank = detached_shape(blank_doc.Part015)
    finally:
        App.closeDocument(blank_doc.Name)

    doc = App.openDocument(str(cad.resolve()))
    try:
        shaft = detached_shape(doc.Part015)
        clamp = detached_shape(doc.Part016)
    finally:
        App.closeDocument(doc.Name)

    require_same_solid(shaft, drive_shaft(blank, DRIVE_HOLE_MM), 'B25 assembly shaft')
    clamp_diameter = radial_hole_diameter(clamp, DRIVE_SEAT[0])
    if not isclose(clamp_diameter, DRIVE_HOLE_MM, abs_tol=1e-7):
        raise ValueError(f'Unexpected clamp passage diameter {clamp_diameter:.2f} mm')

    machining = drive_shaft(blank, TAP_DRILL_MM)
    machining.translate(App.Vector(-SHAFT_INBOARD_X, 0., -112.))
    output.parent.mkdir(parents=True, exist_ok=True)
    machining.exportStep(str(output.resolve()))
    reread = Part.read(str(output.resolve()))
    require_same_solid(reread, machining, 'B25 fabrication STEP')
    diameter = radial_hole_diameter(reread, M3_FROM_INBOARD_MM)
    if not isclose(diameter, TAP_DRILL_MM, abs_tol=1e-7):
        raise ValueError(f'Unexpected STEP tap drill diameter {diameter:.2f} mm')
    print(f'B25 shaft STEP: Ø{diameter:.2f} mm tap drill. '
          f'Part016: Ø{clamp_diameter:.2f} mm clearance.')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cad', type=Path, default=B25_CAD)
    args = parser.parse_args()
    export(args.cad, args.output)
