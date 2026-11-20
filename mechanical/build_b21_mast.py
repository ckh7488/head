"""Open the side entry for the upper mast nuts without cutting their bearing faces."""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App
from FreeCAD import Vector
import Part

from build_b19_review_fixes import replace, world_shape
from primitives import box, print_mesh


def spanner_relief(side):
    y = 8.4
    outline = [(18.55, -25.52), (31., -25.52), (31., -19.65),
               (22., -19.65), (18.55, -23.10)]
    points = [Vector(side*x, y, z) for x, z in outline]
    return Part.Face(Part.makePolygon(points + points[:1])).extrude(Vector(0., 25.2, 0.))


def build(source, output, print_dir):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate mast assembly output')
    doc = App.openDocument(str(source.resolve()))
    try:
        original = world_shape(doc.Part010)
        revised = original.cut([spanner_relief(side) for side in (-1, 1)]).removeSplitter()
        if not revised.isValid() or len(revised.Solids) != 1:
            raise ValueError('Mast tool relief must retain a single valid solid')
        seat_region = box(-35., 35., 4., 40., -35., -25.58)
        seat_loss = original.cut(revised).common(seat_region).Volume
        if seat_loss > 1.e-6:
            raise ValueError('Mast tool relief removed material from the nut bearing faces')
        replace(doc.Part010, revised)
        doc.Label = 'R5 B21'
        doc.recompute()
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(output.resolve()))
        print_dir.mkdir(parents=True, exist_ok=True)
        print_mesh(world_shape(doc.Part010), print_dir / '06_neck_mast-B21.stl')
        report = {'part': 'Part010', 'removed_mm3': original.Volume-revised.Volume,
                  'seating_region_removed_mm3': seat_loss}
        (print_dir / 'mast-relief.json').write_text(json.dumps(report, indent=2) + '\n')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--print-dir', type=Path, required=True)
    build(**vars(parser.parse_args()))
