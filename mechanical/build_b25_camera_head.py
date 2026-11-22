"""Add the Eaton head termination to the B25 nasal tray."""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App
import numpy as np
import Part
from scipy.optimize import brentq

from build_b19_review_fixes import add_part, replace
from build_b22_fused_skull import solid
from build_b25_jaw_retention import mesh_from_solid, replace_mesh
from check_b25_camera_upper import SPLICE, SPLICE_DIRECTION
from check_b25_jaw_retention import from_topology
from export_cad import tessellate, world_mesh


SHEATH_ENTRY = np.array((5.5, -47.05, 83.))
SHEATH_TANGENT = np.array((-.00451496, -.89826802, .43942482))
OEM_CONTROLS = (10.71387542, 5.56773890, 7.08884466, -37.69957892, 82.38478099,
                6.82653001, -37.57672185, 80.98518253)
SPLICE_START_MM = 3.5
SLEEVE_LENGTH_MM = 13.
SLEEVE_OD_MM = 4.6
JUNCTION_MM = SPLICE_START_MM + SLEEVE_LENGTH_MM / 2.
EATON_OD_MM = 3.
OEM_OD_MM = 4.


def vec(points):
    return App.Vector(*map(float, points))


def polygon(points):
    vectors = list(map(vec, points))
    return Part.Face(Part.makePolygon(vectors + vectors[:1]))


def saddle_stock():
    root = ((-31.6, 66.47), (-29.45, 66.47), (-24.7, 69.), (-23.3, 69.47523500099146),
            (-23.3, 71.27523500099146), (-29.95, 71.27523500099146), (-31.6, 70.58))
    foot = polygon((5.9, y, z) for y, z in root).extrude(App.Vector(3.6, 0., 0.))
    tangent = vec(SPLICE_DIRECTION)
    datum = vec(SPLICE)
    ring = Part.makeCylinder(3.1, 3.2, datum - 1.4 * tangent, tangent)
    rear_clip = Part.makeBox(30., 16.7, 40., App.Vector(-10., -40., 55.))
    bore = Part.makeCylinder(1.92, 11., datum - 5.5 * tangent, tangent)
    return foot.fuse(ring).common(rear_clip).cut(bore).removeSplitter()


def neck_tie_profile(height, edge):
    tangent = SPLICE_DIRECTION / np.linalg.norm(SPLICE_DIRECTION)
    side = np.cross((0., 1., 0.), tangent)
    side /= np.linalg.norm(side)
    back = np.cross(tangent, side)
    center = SPLICE - height * tangent
    stations = np.linspace(0., 2 * np.pi, 81, endpoint=False)
    y, x = np.cos(stations), np.sin(stations)
    inner = np.where(y > 0., 1.48 + (3.17 - 1.48) * (1. - y)**.85, 3.17)
    return polygon(center + (inner + edge)[:, None] * (x[:, None] * side + y[:, None] * back))


def saddle_and_tie():
    tangent = vec(SPLICE_DIRECTION)
    clearance = neck_tie_profile(1.20, .64).extrude(2.45 * tangent).cut(
        neck_tie_profile(1.25, -.13).extrude(2.55 * tangent))
    strap = neck_tie_profile(1.05, .47).extrude(2.10 * tangent).cut(
        neck_tie_profile(1.10, -.001).extrude(2.20 * tangent))
    tie_lock = Part.makeBox(2.65, 3.4, 2.65, App.Vector(2.0, -24.8, 70.16))
    saddle = saddle_stock().cut(clearance).removeSplitter()
    tie = strap.fuse(tie_lock).removeSplitter()
    for name, actor in (('saddle', saddle), ('tie', tie)):
        if not actor.isValid() or len(actor.Solids) != 1:
            raise ValueError(f'The camera clamp {name} must be one solid')
    return saddle, tie


def oem_curve():
    d0, d1, x1, y1, z1, x2, y2, z2 = OEM_CONTROLS
    control = (SPLICE, SPLICE + d0 * SPLICE_DIRECTION, (x1, y1, z1), (x2, y2, z2),
               SHEATH_ENTRY - d1 * SHEATH_TANGENT, SHEATH_ENTRY)
    curve = Part.BezierCurve()
    curve.setPoles(list(map(vec, control)))
    return curve


def pipe(curve, radius):
    edge = curve.toShape()
    start = curve.value(curve.FirstParameter)
    tangent, = curve.tangent(curve.FirstParameter)
    profile = Part.Wire([Part.makeCircle(radius, start, tangent)])
    return Part.Wire([edge]).makePipeShell([profile], True, False).removeSplitter()


def section(curve, start, end):
    cut = curve.copy()
    length = curve.length(0., 1.)
    endpoints = tuple(0. if s == 0. else 1. if s == length
                      else brentq(lambda t: curve.length(0., t) - s, 1.e-7, 1.) for s in (start, end))
    cut.segment(*endpoints)
    return cut


def fixed_legs(curve):
    return (pipe(section(curve, 0., JUNCTION_MM), EATON_OD_MM / 2),
            pipe(section(curve, JUNCTION_MM, curve.length(0., 1.)), OEM_OD_MM / 2))


def sleeve(curve):
    end = SPLICE_START_MM + SLEEVE_LENGTH_MM
    cut = section(curve, SPLICE_START_MM, end)
    shell = pipe(cut, SLEEVE_OD_MM / 2)
    return shell.cut([pipe(section(curve, SPLICE_START_MM, JUNCTION_MM), EATON_OD_MM / 2),
                      pipe(section(curve, JUNCTION_MM, end), OEM_OD_MM / 2)]).removeSplitter()


def apply(doc):
    """Install the printed clamp, modeled nylon tie, fixed splice and fixed OEM pigtail."""
    saddle, tie = saddle_and_tie()
    original = from_topology(world_mesh(doc.Part065))
    addition = from_topology(tessellate(saddle))
    stock, update = solid(original), solid(addition)
    overlap = (stock ^ update).volume()
    tray = mesh_from_solid((stock + update).simplify(.0002))
    if overlap < 10. or not tray.is_volume or tray.body_count != 1:
        raise ValueError('The nose clamp must be fused to the rear lip of a closed nasal tray')
    replace_mesh(doc.Part065, tray)
    parent = doc.Part065.getParentGeoFeatureGroup()
    curve = oem_curve()
    eaton, sheath = fixed_legs(curve)
    seal = sleeve(curve)
    for name, label, shape in (
        ('CameraEatonHeadTie', 'Camera Eaton head anchor · laced nylon tie', tie),
        ('CameraEatonHeadSplice', 'Camera Eaton fixed head splice · OD4.6 × 13 fitted envelope', seal),
        ('CameraEatonHeadFixedLeg', 'Camera Eaton fixed preparation leg · OD3', eaton),
        ('CameraOEMHeadTail', 'Camera OEM keyed plug pigtail · head frame', sheath),
    ):
        actor = add_part(doc, parent, name, label, shape, 'head')
        replace(actor, shape)
    motion = json.loads(doc.R5.MotionGeometry)
    motion['camera_eaton_head'] = {'head_anchor_mm': SPLICE.tolist(),
                                   'head_anchor_tangent': SPLICE_DIRECTION.tolist(),
                                   'saddle_parent': 'Part065', 'saddle_bore_mm': 3.84,
                                   'splice_start_after_anchor_mm': SPLICE_START_MM,
                                   'splice_length_mm': SLEEVE_LENGTH_MM, 'splice_od_mm': SLEEVE_OD_MM,
                                   'fixed_eaton_preparation_length_mm': JUNCTION_MM,
                                   'fixed_oem_pigtail_diameter_mm': OEM_OD_MM,
                                   'fixed_oem_pigtail_length_mm': curve.length(0., 1.) - JUNCTION_MM}
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)
    return addition, {'attachment_overlap_mm3': overlap, 'tray_added_volume_mm3': tray.volume-original.volume,
                      **motion['camera_eaton_head']}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('delta', type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('Use a separate output assembly')
    doc = App.openDocument(str(args.input.resolve()))
    try:
        mesh, report = apply(doc)
        doc.recompute()
        doc.saveAs(str(args.output.resolve()))
        mesh.export(args.delta)
        print(json.dumps(report, indent=2))
    finally:
        App.closeDocument(doc.Name)
