"""Build the inboard temple fit candidate from the B26 assembly."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from math import cos, radians, sin
from pathlib import Path

import FreeCAD as App
import manifold3d as md
import numpy as np
import Part

from build_b19_review_fixes import replace, screw_shape
from build_b21_fasteners import check_solid, detached_shape
from build_b21_links import from_mesh
from build_b24_eye_bearings import ABUTMENT_DIAMETER, POCKET_DIAMETER, PIVOT_YZ, SUPPORTS
from build_b25_blink_fit import install_world_mesh, shape_to_mesh
from export_cad import tessellate, world_mesh
from primitives import box, cylinder
from revise import clearance_tool, yz_prism


BASE_SHA256 = '2a50f5a128e886066cbee5a17bb285c53e91470169ff114774c941640e6bced0'
PITCH_LINK_SHIFT = -2.85
PITCH_LINK_PIN_SHIFT = -2.7
SADDLE_INBOARD = 58.30
BEARING_SEAT = 58.38
BEARING_WIDTH = 2.5
PITCH_PIN_INBOARD = 55.6
PITCH_PIN_OUTBOARD = 61.6
FORK_INBOARD, FORK_OUTBOARD = 55.58, 57.93
LID_END = 52.35
LID_COLLAR_OD = 8.65
LID_COLLAR_TRIM = 4.2
LID_PIN_START, LID_PIN_END = 49.25, 55.20
LID_LUG_FACE = 52.74
LID_LUG_END = 55.21
BEAM_INBOARD, BEAM_OUTBOARD = 58.48, 61.72
BOLT_YZ = (4.0, 120.75)
FRAME_FACE = 62.84
BRACKET_FACE, SCREW_SEAT = 62.88, 65.88
LUG_STATION = (-29.437, 116.076)
BEAMS = {
    -1: (3.35, (PIVOT_YZ, (-22.0, 118.6), (-9.1, 119.2))),
    1: (2.38, (PIVOT_YZ, (-36.65, 113.6), (-33.05, 108.85),
               (-24.2, 108.85), (-20.95, 111.95), (-13.15, 114.35), (-9.0, 118.9))),
}


def side_box(side, a, b, y0, y1, z0, z1):
    return box(*sorted((side*a, side*b)), y0, y1, z0, z1)


def axial_cylinder(side, radius, x0, x1, centre=PIVOT_YZ):
    return cylinder(radius, x1-x0, (side*x0, *centre), (side, 0., 0.))


def as_manifold(mesh):
    result = md.Manifold(md.Mesh64(np.asarray(mesh.vertices, dtype=np.float64),
                                  np.asarray(mesh.faces, dtype=np.uint64)))
    if result.status() != md.Error.NoError or result.is_empty():
        raise ValueError(f'Invalid closed mesh: {result.status()}')
    return result


def mesh_tool(shape):
    return as_manifold(from_mesh(tessellate(shape)))


def install_solid_mesh(obj, solid):
    mesh = shape_to_mesh(solid)
    if solid.status() != md.Error.NoError or not mesh.is_volume or mesh.body_count != 1:
        raise ValueError(f'{obj.Name} must remain one closed printed body')
    install_world_mesh(obj, mesh)


def saddle_step(side, allowance=0.):
    profiles = []
    for y, x0, x1 in ((-10.6, BEAM_INBOARD, BEAM_OUTBOARD), (2.4, BRACKET_FACE, SCREW_SEAT)):
        lo, hi = x0-allowance, x1+allowance
        bottom, top = 117.2-allowance, 121.85+allowance
        points = [App.Vector(side*x, y, z) for x, z in
                  ((lo, bottom), (hi, bottom), (hi, top), (lo, top))]
        profiles.append(Part.makePolygon([*points, points[0]]))
    return Part.makeLoft(profiles, True, True)


def fit_lid(doc, index, side):
    """Shorten the outer rotating collar and put its fixed lug behind the visible rim."""
    orbit = doc.getObject(f'Part0{76+index}')
    lid = doc.getObject(f'Part0{78+index}')
    orbit_stock = as_manifold(from_mesh(world_mesh(orbit)))
    lid_stock = as_manifold(from_mesh(world_mesh(lid)))
    # Stop the axial trim well before the lower crank's pin and pin stop.
    dy, dz = cos(radians(-56)), sin(radians(-56))
    y, z = PIVOT_YZ
    edge = [(LID_END, -12.), (55.75, -12.),
            (55.75, LID_COLLAR_TRIM), (LID_END, LID_COLLAR_TRIM)]
    contour = [App.Vector(side*x, y+t*dy+15*dz, z+t*dz-15*dy) for x, t in edge]
    collar = Part.Face(Part.makePolygon([*contour, contour[0]])).extrude(
        App.Vector(0, -30*dz, 30*dy))
    lid_after = lid_stock - mesh_tool(collar)

    # Keep the stock dome. Reinforce the short hinge collar on its hidden face.
    collar_body = axial_cylinder(side, LID_COLLAR_OD/2, 49.92, LID_END)
    collar_bore = axial_cylinder(side, 1.125, 49.87, LID_END+.08)
    lid_after = lid_after + mesh_tool(collar_body.cut(collar_bore))

    old_rear_end = side_box(side, 52.5, 57.3, -44.1, -35.8, 113.5, 124.8)
    bridge_outline = [
        (side*52.74, -41.25), (side*52.74, -46.5), (side*55.68, -49.2),
        (side*56.99, -48.8), (side*56.99, -45.1), (side*55.21, -43.85),
        (side*55.21, -41.25),
    ]
    base = [App.Vector(x, yy, 115.63) for x, yy in bridge_outline]
    bridge = Part.Face(Part.makePolygon([*base, base[0]])).extrude(App.Vector(0, 0, 6.74))
    lug = axial_cylinder(side, 3.58, LID_LUG_FACE, LID_LUG_END)
    bore = axial_cylinder(side, 1.125, LID_LUG_FACE-.15, LID_LUG_END+.45)
    lug_geometry = check_solid(lug.fuse(bridge).cut(bore), f'{orbit.Name} inner hinge lug')
    orbit_after = (orbit_stock - mesh_tool(old_rear_end)) + mesh_tool(lug_geometry)
    install_solid_mesh(lid, lid_after)
    install_solid_mesh(orbit, orbit_after)
    pin = doc.Part058 if side < 0 else doc.Part062
    replace(pin, axial_cylinder(side, 1., LID_PIN_START, LID_PIN_END))
    pin.Label = 'Ø2 × 5.95 · outer lid hinge pin'
    return {
        'orbit': orbit.Name, 'lid': lid.Name, 'pin': pin.Name,
        'orbit_volume_change_mm3': round(orbit_after.volume()-orbit_stock.volume(), 4),
        'lid_volume_change_mm3': round(lid_after.volume()-lid_stock.volume(), 4),
        'lid_collar_diameter_mm': LID_COLLAR_OD,
        'lid_collar_abs_x_mm': [49.92, LID_END],
        'lug_abs_x_mm': [LID_LUG_FACE, LID_LUG_END],
        'pin_abs_x_mm': [LID_PIN_START, LID_PIN_END],
    }


def fit_eye_pitch(doc, frame):
    cradle = detached_shape(doc.Part024).common(box(
        -FORK_OUTBOARD, FORK_OUTBOARD, -55, -12, 104, 132))
    # Remove the complete old fork material, including the skin of the
    # original arm that would otherwise remain outboard of the new arm.
    cradle = cradle.cut([side_box(side, FORK_INBOARD-.14, 62.6, -51., -17.33, 108., 130.)
                         for side in (-1, 1)])
    supports = []
    for _, side, bracket, pin, bearing, bolt, _ in SUPPORTS:
        # Seat the MR63 from the inside before fitting the saddle from the front.
        boss = axial_cylinder(side, 5.28, SADDLE_INBOARD, 61.76)
        # A radial slot clears the inside corner of the skull and leaves
        # 275 degrees of the original, uniform bearing-seat wall.
        slot_points = [PIVOT_YZ, *((PIVOT_YZ[0]+18*cos(radians(a)), PIVOT_YZ[1]+18*sin(radians(a)))
                                   for a in (-177.5, -92.5))]
        clip = yz_prism(slot_points, -65.0, 130.0)
        radius, path = BEAMS[side]
        rails = [clearance_tool(side*(BEAM_INBOARD+BEAM_OUTBOARD)/2., start, end,
                                radius, BEAM_OUTBOARD-BEAM_INBOARD)
                 for start, end in zip(path, path[1:])]
        seat = axial_cylinder(side, 4.32, BRACKET_FACE, SCREW_SEAT, BOLT_YZ)
        joiner = saddle_step(side)
        pocket = axial_cylinder(side, POCKET_DIAMETER/2, SADDLE_INBOARD-.05,
                                BEARING_SEAT+BEARING_WIDTH)
        shoulder = axial_cylinder(side, ABUTMENT_DIAMETER/2, SADDLE_INBOARD-.05, 62.1)
        fastener_hole = axial_cylinder(side, 1.72, BRACKET_FACE-.1, SCREW_SEAT+.1, BOLT_YZ)
        blank = check_solid(boss.fuse([*rails, seat, joiner]).cut(clip), bracket)
        insert_clearance = axial_cylinder(side, 2.46, 62.34, BRACKET_FACE+.01, BOLT_YZ)
        mount = check_solid(blank.cut([pocket, shoulder, fastener_hole, insert_clearance]), bracket)
        replace(doc.getObject(bracket), mount)

        start_x = sorted((side*FORK_INBOARD, side*FORK_OUTBOARD))[0]
        web = yz_prism([(-41.5, 116.1), (-42., 120.3), (-39.8, 122.7), (-35.4, 121.5),
                        (-23.9, 121.9), (-18.0, 124.8), (-16.2, 124.7), (-16.2, 121.1),
                        (-36.6, 116.7)], start_x, FORK_OUTBOARD-FORK_INBOARD)
        pivot = axial_cylinder(side, 3.7, FORK_INBOARD, FORK_OUTBOARD)
        bore = axial_cylinder(side, 1.62, FORK_INBOARD-.08, FORK_OUTBOARD+.08)
        root = side_box(side, 53.9, FORK_OUTBOARD, -17.50, -15.15, 120.5, 124.8)
        cradle = cradle.fuse(web.fuse([root, pivot]).cut(bore))
        replace(doc.getObject(pin),
                axial_cylinder(side, 1.5, PITCH_PIN_INBOARD, PITCH_PIN_OUTBOARD))
        doc.getObject(pin).Label = 'Ø3 × 6 · eye pitch pin'
        replace(doc.getObject(bearing), detached_shape(doc.getObject(bearing)).translate(
            App.Vector(side*(BEARING_SEAT-66.67), 0, 0)))

        y, z = BOLT_YZ
        new_lug = axial_cylinder(side, 4.7, FRAME_FACE-3.18, FRAME_FACE, BOLT_YZ)
        dowel = cylinder(1.58, 18., (side*60.5, 0., 103.5))
        insert = doc.getObject(bolt+'Insert')
        body = axial_cylinder(side, 2.3, FRAME_FACE-3.03, FRAME_FACE-.03, BOLT_YZ)
        bore = axial_cylinder(side, 1.50, FRAME_FACE-3.10, FRAME_FACE+.1, BOLT_YZ)
        replace(insert, body.cut(bore))
        insert_bore = axial_cylinder(side, 2.34, FRAME_FACE-3.08, FRAME_FACE+.07, BOLT_YZ)
        unused_seat = side_box(side, 58.77, 77., 8.9, 36., 137.8, 166.)
        pad_clearance = axial_cylinder(side, 4.42, BRACKET_FACE-.10, SCREW_SEAT+.10, BOLT_YZ)
        relief = saddle_step(side, .10).fuse(pad_clearance)
        frame = (frame.cut(unused_seat).fuse(new_lug.cut(dowel))
                 .cut(relief).cut(insert_bore))
        screw = doc.getObject(bolt)
        x = side*SCREW_SEAT
        replace(screw, screw_shape(3, 6., (x, y, z), (-side, 0., 0.)))
        screw.Label = 'M3 × 6 · eye bearing saddle'
        supports.append({
            'bracket': bracket, 'pin': pin, 'bearing': bearing, 'bolt': bolt,
            'insert': insert.Name, 'bearing_seat_x_mm': side*BEARING_SEAT,
            'bearing_inward_mm': round(66.67-BEARING_SEAT, 3),
            'pin_abs_x_mm': [PITCH_PIN_INBOARD, PITCH_PIN_OUTBOARD],
            'screw_seat_mm': [x, y, z],
            'screw_axis': [-side, 0., 0.],
            'insertion_mm': [-side*9., 0., 0.],
            'rail_yz_mm': path,
            'screw_length_mm': 6.,
        })

    # The new inboard pitch-drive lug is separate from the radial bearing arm.
    start = 55.26
    end = 61.+PITCH_LINK_SHIFT
    output_boss = axial_cylinder(1, 2.8, start, end, LUG_STATION)
    wing = yz_prism([(-31.8, 115.8), (-29.6, 113.5), (-27.1, 114.7),
                     (-19.0, 120.9), (-16.15, 121.3), (-16.15, 124.75),
                     (-19.0, 124.55), (-23.8, 121.4), (-28.9, 118.85)],
                    start, end-start)
    bore = axial_cylinder(1, 1.18, start-.08, end+.08, LUG_STATION)
    cradle = cradle.fuse(wing.fuse(output_boss)).cut(bore)
    replace(doc.Part024, check_solid(cradle, '12 eye tilt cradle'))
    return frame, supports


def fit_pitch_drive(doc):
    # The motor and upper joint keep their stock planes. A dogleg in the
    # middle of the web moves only the lower joint into the available space.
    link = detached_shape(doc.Part044)
    y, z = LUG_STATION
    ay, az = np.array((49., 32.))/np.hypot(49., 32.)
    first, last = 17.0, 37.0

    def band(a, b):
        contour = [(y+s*ay-t*az, z+s*az+t*ay)
                   for s, t in ((a, -10.), (b, -10.), (b, 10.), (a, 10.))]
        return yz_prism(contour, 58., 8.)

    lower = link.common(band(-10., first))
    lower.translate(App.Vector(PITCH_LINK_SHIFT, 0., 0.))
    transition = link.common(band(first, last))
    shear = App.Matrix()
    slope = -PITCH_LINK_SHIFT/(last-first)
    shear.A12, shear.A13 = slope*ay, slope*az
    shear.A14 = PITCH_LINK_SHIFT-slope*(first+y*ay+z*az)
    transition = transition.transformGeometry(shear)
    upper = link.common(band(last, 68.))
    replace(doc.Part044, check_solid(lower.fuse([transition, upper]), '18 eye pitch link'))
    pin = doc.EyePitchLinkCradlePin
    replace(pin, detached_shape(pin).translate(App.Vector(PITCH_LINK_PIN_SHIFT, 0., 0.)))
    return {'lower_shift_mm': PITCH_LINK_SHIFT, 'transition_from_lower_pivot_mm': [first, last],
            'link': doc.Part044.Name, 'lower_pin': pin.Name, 'lower_pin_shift_mm': PITCH_LINK_PIN_SHIFT}


def build(source, output, report, lids_only=False):
    with source.open('rb') as cad:
        source_hash = file_digest(cad, 'sha256').hexdigest()
    if source_hash != BASE_SHA256:
        raise ValueError('This build requires the reviewed B26 assembly')
    doc = App.openDocument(str(source))
    try:
        geometry = json.loads(doc.R5.MotionGeometry)
        lids = [fit_lid(doc, index, side) for index, side in enumerate((-1, 1))]
        design = {'source_sha256': source_hash, 'pitch_axis_yz_mm': PIVOT_YZ, 'orbit_and_lid': lids}
        if lids_only:
            design['design_status'] = 'orbit and lid subassembly candidate'
        else:
            frame, supports = fit_eye_pitch(doc, detached_shape(doc.Part019))
            drive = fit_pitch_drive(doc)
            replace(doc.Part019, check_solid(frame, '09 head frame'))
            for existing, moved in zip(geometry['eye_pitch_bearings']['supports'], supports, strict=True):
                existing.update(moved)
            design.update(design_status='stage 1 candidate', bearing_saddles=supports,
                          pitch_drive=drive)
        geometry['b27_temple'] = design
        doc.R5.MotionGeometry = json.dumps(geometry, ensure_ascii=False)
        doc.recompute()
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(output))
        with output.open('rb') as cad:
            design['candidate_sha256'] = file_digest(cad, 'sha256').hexdigest()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(design, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--lids-only', action='store_true',
                        help='build the 31 and 32 revision on the existing B26 mechanism')
    args = parser.parse_args()
    build(args.source.resolve(), args.output.resolve(), args.report.resolve(), args.lids_only)
