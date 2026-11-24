"""Route the existing eye yaw tie bar behind the swept rear rims of both eyes."""

import FreeCAD as App
import numpy as np
import Part
import trimesh

from build_b19_review_fixes import replace, world_shape
from export_cad import tessellate
from primitives import box, cylinder
from revise import flat_xy

PART = 'Part037'
PRINT = '15_eye_yaw_offset_tie_bar-B21.stl'
CRADLE = 'Part024'
CRADLE_PRINT = '12_eye_tilt_cradle-B23.stl'
ENTRY_PATH = ((-110., -3.15, .69), (0., -3.15, .69), (0., 0., 0.))
RIB_X = (-39.2, -28.8)
RIB_WIDTH_Y_MM = 1.37
RIB_REAR_YZ = (
    (-20.59, 111.8), (-20.42, 113.5), (-20.15, 114.3), (-19.87, 114.9),
    (-19.67, 115.8), (-19.40, 116.6), (-19.40, 119.5), (-19.35, 120.75),
)
RIB_YZ = (*RIB_REAR_YZ, *((y-RIB_WIDTH_Y_MM, z) for y, z in reversed(RIB_REAR_YZ)))
EYES = ((-34., -25.5), (34., -25.5))
DRIVE = (-5.8, -22.)
BOTTOM_Z = 114.55
BAR_TOP_Z = 117.45
PIN_STOP_Z = 117.05
BOSS_TOP_Z = 118.35
BAR_RADIUS = 2.35
END_RADIUS = 2.30
BOSS_RADIUS = 3.17
DRIVE_PILOT_RADIUS = .775
FINISHED_RADIUS = 1.045
EYE_PRINT_PILOT_RADIUS = .96
DRIVE_PRINT_RADIUS = 1.12
SLOT_HALF_TRAVEL = .30
CENTRELINE = (
    (-27., -25.5), (-19., -22.), (19., -22.), (27., -25.5),
)


def shape(printable=False):
    """Build the tie bar in its installed frame with original pin coordinates."""
    height = BAR_TOP_Z - BOTTOM_Z
    wings = flat_xy(CENTRELINE, height, BOTTOM_Z, 2 * BAR_RADIUS)
    ends = []
    for eye, wing, limits in ((EYES[0], CENTRELINE[0], (-40., -27.5)),
                              (EYES[1], CENTRELINE[-1], (27.5, 40.))):
        end = flat_xy((eye, wing), height, BOTTOM_Z, 2 * END_RADIUS)
        ends.append(end.common(box(*limits, -32., -15., BOTTOM_Z-.1, BAR_TOP_Z+.1)))
    body = wings.fuse(ends)
    x, y = DRIVE
    boss = flat_xy(((x, y-SLOT_HALF_TRAVEL), (x, y+SLOT_HALF_TRAVEL)),
                   BOSS_TOP_Z - BOTTOM_Z, BOTTOM_Z, 2 * BOSS_RADIUS)
    start = BOTTOM_Z - .10
    slot_r = DRIVE_PRINT_RADIUS if printable else FINISHED_RADIUS
    bore_r = EYE_PRINT_PILOT_RADIUS if printable else FINISHED_RADIUS
    pitch = SLOT_HALF_TRAVEL
    drive_seat = box(x-slot_r, x+slot_r, y-pitch, y+pitch, start, PIN_STOP_Z).fuse([
        cylinder(slot_r, PIN_STOP_Z-start, (x, y-pitch, start)),
        cylinder(slot_r, PIN_STOP_Z-start, (x, y+pitch, start)),
    ])
    bores = [cylinder(bore_r, BAR_TOP_Z-start+.1, (*centre, start)) for centre in EYES]
    vent = cylinder(DRIVE_PILOT_RADIUS, BOSS_TOP_Z-PIN_STOP_Z+.1, (x, y, PIN_STOP_Z))
    result = body.fuse(boss).cut([drive_seat, vent, *bores]).removeSplitter()
    if not result.isValid() or len(result.Solids) != 1:
        raise ValueError('The eye yaw tie bar must be one valid solid')
    return result


def cradle_shape(stock):
    """Shift the existing left cradle rib away from the original side feed."""
    x0, x1 = RIB_X
    contour = [App.Vector(x0, y, z) for y, z in RIB_YZ]
    rib = Part.Face(Part.makePolygon([*contour, contour[0]])).extrude(App.Vector(x1-x0, 0., 0.))
    clearance = box(x0, x1, -22.3, -20.4, 112.2, 120.0)
    revised = stock.cut(clearance).fuse(rib).removeSplitter()
    if not revised.isValid() or len(revised.Solids) != 1:
        raise ValueError('The eye cradle must remain one valid solid')
    added, removed = revised.cut(stock), stock.cut(revised)
    region = box(x0-.01, x1+.01, -22.31, -18.69, 111.79, 120.76)
    if added.cut(region).Volume > 1e-6 or removed.cut(region).Volume > 1e-6:
        raise ValueError('Eye cradle material changed outside the left rib')
    return revised, {'rib_profile_yz_mm': RIB_YZ, 'rib_span_x_mm': RIB_X,
                     'rib_width_y_mm': RIB_WIDTH_Y_MM,
                     'added_mm3': added.Volume, 'removed_mm3': removed.Volume}


def print_mesh(model):
    """Return one closed mesh, centered in XY and sitting on Z=0."""
    points, faces = tessellate(model).Topology
    mesh = trimesh.Trimesh(vertices=[tuple(point) for point in points], faces=faces, process=False)
    target = mesh.bounds.mean(axis=0)
    target[2] = mesh.bounds[0, 2]
    mesh.apply_translation(-target)
    if not mesh.is_volume or mesh.body_count != 1 or not mesh.nondegenerate_faces().all():
        raise ValueError('The eye yaw part must be watertight and printable')
    return mesh


def apply(doc):
    """Update the assembled tie bar and cradle, plus their existing P2S placements."""
    source = world_shape(doc.getObject(PART))
    tie = shape()
    # Both full-depth eye bore stations must keep their original material.
    end_zones = (box(-40., -29., -33., -15., BOTTOM_Z-.1, BAR_TOP_Z+.1),
                 box(29., 40., -33., -15., BOTTOM_Z-.1, BAR_TOP_Z+.1))
    for zone in end_zones:
        initial, revised = source.common(zone), tie.common(zone)
        if initial.cut(revised).Volume > 1e-6 or revised.cut(initial).Volume > 1e-6:
            raise ValueError('The existing eye bore end station changed')
    cradle, rib = cradle_shape(world_shape(doc.getObject(CRADLE)))
    printable = print_mesh(shape(printable=True))
    cradle_print = cradle.copy()
    cradle_print.rotate(App.Vector(), App.Vector(1., 0., 0.), 90.)
    replacements = {PRINT: (PRINT, printable), CRADLE_PRINT: (CRADLE_PRINT, print_mesh(cradle_print))}
    replace(doc.getObject(PART), tie)
    replace(doc.getObject(CRADLE), cradle)
    return replacements, {
        'part': PART,
        'cradle': rib,
        'insertion_offsets_mm': ENTRY_PATH,
        'centreline_xy_mm': (EYES[0], *CENTRELINE, EYES[1]),
        'eye_bores_xy_mm': EYES,
        'eye_bore_diameter_mm': 2 * FINISHED_RADIUS,
        'eye_print_pilot_diameter_mm': 2 * EYE_PRINT_PILOT_RADIUS,
        'drive_slot_center_xy_mm': DRIVE,
        'drive_slot_finished_xy_mm': [2 * FINISHED_RADIUS, 2 * (FINISHED_RADIUS + SLOT_HALF_TRAVEL)],
        'drive_slot_print_xy_mm': [2 * DRIVE_PRINT_RADIUS, 2 * (DRIVE_PRINT_RADIUS + SLOT_HALF_TRAVEL)],
        'drive_pin_stop_z_mm': PIN_STOP_Z,
        'drive_boss_print_wall_mm': BOSS_RADIUS - DRIVE_PRINT_RADIUS,
        'bar_thickness_mm': BAR_TOP_Z - BOTTOM_Z,
        'drive_stop_roof_thickness_mm': BOSS_TOP_Z - PIN_STOP_Z,
        'eye_bore_finished_radial_wall_mm': END_RADIUS-FINISHED_RADIUS,
        'eye_bore_span_z_mm': [BOTTOM_Z, BAR_TOP_Z],
        'mesh_bounds_mm': printable.bounds.tolist(),
        'base_volume_mm3': source.Volume,
        'revised_volume_mm3': tie.Volume,
    }
