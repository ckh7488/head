"""Build the service revision with an independently fastened ID5 plug keeper."""
from argparse import ArgumentParser
from pathlib import Path
import sys

import FreeCAD as App

from build_near_eyes import align_finishes
from primitives import box, cylinder
from stock import hexagon, socket_screw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'physics'))
from export_cad import tessellate, world_shape

SCREW_X = 17.
SCREW_HEIGHTS = (84., 108.)
SCREW_SEAT = 23.10
SCREW_LENGTH = 8.
NUT_INNER_FACE = 15.20


def pitch_guard():
    rail = box(9.3, 14.3, 20.05, 22.25, 81., 111.)
    arms = [box(11.9, 16.1, 20.05, 22.25, z-2.35, z+2.35) for z in SCREW_HEIGHTS]
    feet = [cylinder(2.70, SCREW_SEAT-18.65, (SCREW_X, 18.65, z), (0, 1, 0)) for z in SCREW_HEIGHTS]
    screws = [cylinder(1.17, 5.3, (SCREW_X, 18.3, z), (0, 1, 0)) for z in SCREW_HEIGHTS]
    feed = box(10.5, 13.1, 19.85, 22.45, 94.15, 101.65)
    exit_relief = box(8.8, 10.56, 20.78, 22.45, 94.05, 101.75)
    return rail.fuse([*arms, *feet]).cut([feed, exit_relief, *screws]).removeSplitter()


def yoke_with_nuts(yoke):
    tools = []
    for z in SCREW_HEIGHTS:
        start = (SCREW_X, 14.16, z)
        tools.append(cylinder(1.16, 5., start, (0, 1, 0)))
        tools.append(hexagon(4.22, 2.64, start, (0, 1, 0), (1, 0, 0)))
    return yoke.cut(tools).removeSplitter()


def assembly(doc):
    yoke = doc.Part011
    revised = yoke_with_nuts(world_shape(yoke))
    parent = yoke.getParentGeoFeatureGroup()
    revised.Placement = parent.getGlobalPlacement().inverse().multiply(revised.Placement)
    keeper = pitch_guard()
    for shape in (revised, keeper):
        if not shape.isValid() or len(shape.Solids) != 1:
            raise ValueError('Yoke and plug keeper must each be one valid solid')
    yoke.Shape = revised
    item = parent.newObject('Part::Feature', 'ID5EHKeeper')
    item.Shape = keeper
    item.Label = 'ID5 EH plug keeper · independent M2 fasteners'
    item.addProperty('App::PropertyString', 'Motion', 'Wiring')
    item.Motion = 'pan'
    if item.ViewObject:
        item.ViewObject.ShapeColor = (.96, .60, .20)
    for index, z in enumerate(SCREW_HEIGHTS, 1):
        bolt = socket_screw(2, SCREW_LENGTH, (SCREW_X, SCREW_SEAT, z), (0, -1, 0))
        nut_start = (SCREW_X, NUT_INNER_FACE, z)
        nut = hexagon(4., 1.60, nut_start, (0, 1, 0), (1, 0, 0)).cut(
            cylinder(1.02, 1.60, nut_start, (0, 1, 0)))
        for name, label, shape in (('Screw', 'M2 × 8 keeper screw', bolt), ('Nut', 'M2 captive nut', nut)):
            part = parent.newObject('Part::Feature', f'ID5Keeper{name}{index}')
            part.Label = label
            part.Shape = shape
            part.addProperty('App::PropertyString', 'Motion', 'Wiring')
            part.Motion = 'pan'
    return align_finishes(doc)


def make(source, output, world=None):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate CAD output')
    doc = App.openDocument(str(source.resolve()))
    try:
        assembly(doc)
        doc.Label = 'R5 B17 · service and 300 mm gaze'
        doc.recompute()
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(output.resolve()))
        if world:
            world.mkdir(parents=True, exist_ok=True)
            for name in ('Part011', 'ID5EHKeeper', 'Part030', 'Part031', 'Part034', 'Part035'):
                tessellate(world_shape(doc.getObject(name))).write(str(world / f'{name}.stl'))
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=HERE / 'revisions/b16/R5-B16-Wiring.FCStd')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--world', type=Path)
    make(**vars(parser.parse_args()))
