"""Open a straight approach for the eye tie bar in the B19 assembly."""
from argparse import ArgumentParser
from pathlib import Path

import FreeCAD as App
import Part

from build_b19_review_fixes import replace, world_shape
from primitives import box, print_mesh


SOURCE = Path(__file__).resolve().parent / 'revisions/b19/R5-B19-review-fixes.FCStd'


def cradle_for_side_insertion(cradle):
    # The mark on the outer rim lines up with the incoming pin hole during the raised slide.
    cradle = cradle.cut([box(-63., -57.5, -31.55, -18.5, 113., 119.7),
                         box(-63., -61.45, -28.8, -27.8, 119.69, 121.15)])
    # Offset and widen the left rib where the middle of the tie bar crosses it.
    section = [(-22.2, 109.6), (-20.85, 109.6), (-20.5, 113.75), (-20.5, 120.75),
               (-21.95, 121.1), (-21.55, 119.35), (-21.55, 113.15), (-22.2, 110.65)]
    old_rib_middle = box(-36.41, -31.59, -22.3, -20.75, 110.7, 120.4)
    left, right = -39.2, -28.8
    profile = [App.Vector(left, y, z) for y, z in section]
    rib = Part.Face(Part.makePolygon([*profile, profile[0]])).extrude(App.Vector(right - left, 0, 0))
    cradle = cradle.cut(old_rib_middle).fuse(rib)
    return cradle.removeSplitter()


def make(source, output, stl):
    if len({source.resolve(), output.resolve(), stl.resolve()}) != 3:
        raise ValueError('Choose distinct input, CAD output and print output paths')
    doc = App.openDocument(str(source.resolve()))
    try:
        cradle = cradle_for_side_insertion(world_shape(doc.Part024))
        if not cradle.isValid() or len(cradle.Solids) != 1:
            raise ValueError('The revised eye cradle must be a single valid solid')
        replace(doc.Part024, cradle)
        doc.Label = 'R5 B20 · eye tie-bar assembly clearance'
        doc.recompute()
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(output.resolve()))
        stl.parent.mkdir(parents=True, exist_ok=True)
        print_mesh(world_shape(doc.Part024), stl, 'y+')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stl', type=Path, required=True)
    make(**vars(parser.parse_args()))
