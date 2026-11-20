"""Add the XL430 plug-retention prototypes to a copy of the B16 assembly."""
from argparse import ArgumentParser
from pathlib import Path

import FreeCAD as App
from FreeCAD import Vector

from primitives import box, cylinder


def yaw_keeper(bracket):
    back = box(-28.3, -26.15, 1.25, 30.75, -65.1, -59.55)
    stop = box(-26.2, -20.05, 9.25, 18.95, -64.35, -60.)
    feet = [cylinder(2.60, 9.71, (-28.3, y, -62.9), (1, 0, 0)) for y in (4., 28.)]
    screws = [cylinder(1.52, 10.3, (-28.5, y, -62.9), (1, 0, 0)) for y in (4., 28.)]
    feed = box(-29., -19.95, 10.25, 17.95, -63.3, -60.9)
    outer = back.fuse([stop, *feet]).cut([*screws, feed])
    # Match the irregular screw recesses in the released yaw bracket.
    offsets = ((.18, 0, 0), (-.18, 0, 0), (0, .18, 0),
               (0, -.18, 0), (0, 0, .18), (0, 0, -.18))
    relief = [bracket, *[bracket.translated(Vector(*offset)) for offset in offsets]]
    return outer.cut(relief).removeSplitter()


def pitch_keeper():
    rail = box(9.3, 14.3, 20.05, 22.25, 81., 111.)
    feet = [cylinder(2.75, 3.60, (11., 18.65, z), (0, 1, 0)) for z in (84., 108.)]
    screws = [cylinder(1.53, 4.6, (11., 18.3, z), (0, 1, 0)) for z in (84., 108.)]
    feed = box(10.5, 13.1, 19.85, 22.45, 94.15, 101.65)
    # The wires turn left immediately after the retaining face.
    exit_relief = box(8.8, 10.56, 20.78, 22.45, 94.05, 101.75)
    return rail.fuse(feet).cut([*screws, feed, exit_relief]).removeSplitter()


def make(source, output):
    if source.resolve() == output.resolve():
        raise ValueError('The prototype needs its own output CAD file')
    doc = App.openDocument(str(source.resolve()))
    try:
        bracket = doc.Part008.Shape.copy()
        bracket.Placement = doc.Part008.getGlobalPlacement()
        variants = (('ID4', 'fixed', yaw_keeper(bracket)), ('ID5', 'pan', pitch_keeper()))
        for servo, motion, shape in variants:
            if not shape.isValid() or len(shape.Solids) != 1:
                raise ValueError(f'{servo} keeper needs one valid solid')
            feature = doc.Base_and_neck.newObject('Part::Feature', servo + 'EHKeeper')
            feature.Shape = shape
            feature.Label = f'{servo} EH plug keeper prototype'
            feature.addProperty('App::PropertyString', 'Motion', 'Wiring')
            feature.Motion = motion
            if feature.ViewObject:
                feature.ViewObject.ShapeColor = (.96, .60, .20)
        doc.Label = 'R5 B16 neck plug keeper prototype'
        doc.recompute()
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(output.resolve()))
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path,
                        default=Path(__file__).resolve().parent / 'revisions/b16/R5-B16-Wiring.FCStd')
    parser.add_argument('--output', type=Path, required=True)
    make(**vars(parser.parse_args()))
