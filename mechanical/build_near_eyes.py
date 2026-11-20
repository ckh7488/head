"""Place both painted irises on the existing globes for a 300 mm front target."""
from argparse import ArgumentParser
from math import atan2, degrees
from pathlib import Path
import sys

import FreeCAD as App
from FreeCAD import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'physics'))
from export_cad import world_shape

REFERENCE_DISTANCE = 300.
EYES = ((-34., ('Part030', 'Part031')), (34., ('Part034', 'Part035')))


def align_finishes(doc, distance=REFERENCE_DISTANCE):
    camera = world_shape(doc.Part068).BoundBox
    target = Vector(camera.Center.x, camera.YMin - distance, camera.Center.z)
    result = {'distance_from_lens_mm': distance, 'target_mm': list(target), 'eyes': []}
    for x, names in EYES:
        pivot = Vector(x, -39., 119.)
        forward = Vector(0., -1., 0.)
        direction = (target - pivot).normalize()
        axis = forward.cross(direction)
        angle = degrees(forward.getAngle(direction))
        for name in names:
            obj = doc.getObject(name)
            shape = world_shape(obj)
            shape.rotate(pivot, axis, angle)
            parent = obj.getParentGeoFeatureGroup()
            shape.Placement = parent.getGlobalPlacement().inverse().multiply(shape.Placement)
            obj.Shape = shape
        result['eyes'].append({
            'center_mm': list(pivot), 'axis': list(direction),
            'inward_deg': abs(degrees(atan2(direction.x, -direction.y))),
            'downward_deg': degrees(atan2(-direction.z, (direction.x**2+direction.y**2)**.5)),
            'paint_center_mm': list(pivot + 14.*direction),
        })
    return result


def make(source, output):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate CAD output')
    doc = App.openDocument(str(source.resolve()))
    try:
        align_finishes(doc)
        doc.Label = 'R5 · 300 mm gaze reference'
        doc.recompute()
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(output.resolve()))
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=HERE / 'revisions/b16/R5-B16-Wiring.FCStd')
    parser.add_argument('--output', type=Path, required=True)
    make(**vars(parser.parse_args()))
