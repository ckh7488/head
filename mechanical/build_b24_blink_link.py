"""Clear the front shell at the lower end of the left blink link."""

import json

import FreeCAD as App
import Part

from build_b19_review_fixes import replace
from build_b21_links import SOURCE, change_shape, edits
from export_cad import world_shape
from primitives import print_mesh


PART = 'Part057'
PRINT = '23_left_short_lid_link-B24.stl'
PROFILE_YZ = (
    (-40., 111.33),
    (-35.5, 111.33),
    (-34.13, 111.60),
    (-33.68, 111.80),
    (-33.12, 112.05),
    (-32.34, 114.90),
    (-34.3, 115.75),
    (-40., 115.75),
)


def cut_link(shape):
    points = [App.Vector(-51.3, y, z) for y, z in PROFILE_YZ]
    cutter = Part.Face(Part.makePolygon(points + points[:1])).extrude(App.Vector(4., 0., 0.))
    result = shape.cut(cutter).removeSplitter()
    if not result.isValid() or len(result.Solids) != 1 or result.Volume >= shape.Volume:
        raise ValueError('The blink link bevel must remove material from one solid')
    return result


def apply(doc, prints):
    obj = doc.getObject(PART)
    fitted = world_shape(obj)
    modified = cut_link(fitted)

    stock_doc = App.openDocument(str(SOURCE))
    try:
        adds, cuts = edits(False)
        print_shape = change_shape(world_shape(stock_doc.getObject(PART)), adds[PART], cuts[PART])
        print_mesh(cut_link(print_shape), prints / PRINT, 'x+')
    finally:
        App.closeDocument(stock_doc.Name)

    replace(obj, modified)
    geometry = json.loads(doc.R5.MotionGeometry)
    report = {'part': PART, 'profile_yz_mm': PROFILE_YZ, 'removed_mm3': fitted.Volume - modified.Volume}
    geometry['blink_link_relief'] = report
    doc.R5.MotionGeometry = json.dumps(geometry, ensure_ascii=False)
    return report
