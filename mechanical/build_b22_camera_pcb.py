"""Attach the camera module to its removable bracket with existing stock hardware."""

import json

import FreeCAD as App

from build_b19_review_fixes import add_part, replace
from build_b21_fasteners import check_solid, detached_shape
from primitives import box, cylinder
from stock import nut, socket_screw


BOARD_FRONT_Y = -53.50
BOARD_REAR_Y = BOARD_FRONT_Y + 2.20
BRACKET_FRONT_Y = -56.60
NUT_FACE_Y = BRACKET_FRONT_Y - .50
NUT_OUTER_Y = NUT_FACE_Y - 1.60
MOUNT_X = (-14., 14.)
BOARD_HOLES_Z = (75., 103.)
SCREW_AXIS = (0., -1., 0.)


def apply(doc):
    camera = doc.Part067
    lens = doc.Part068
    parent = camera.getParentGeoFeatureGroup()
    motion = camera.Motion
    physical = detached_shape(camera)
    bounds = physical.BoundBox
    z_top = bounds.ZMax
    z_bottom = bounds.ZMin
    holes = [cylinder(1.10, 2.40, (x, BOARD_REAR_Y+.1, z), SCREW_AXIS)
             for x in MOUNT_X for z in BOARD_HOLES_Z]
    pcb = box(bounds.XMin, bounds.XMax, BOARD_FRONT_Y, BOARD_REAR_Y, z_bottom, z_top)
    replace(camera, check_solid(pcb.cut(holes), 'camera PCB with four mounting bores'))
    mounted_lens = detached_shape(lens)
    mounted_lens.translate(App.Vector(0., BOARD_FRONT_Y-bounds.YMin, 0.))
    replace(lens, mounted_lens)

    rows = []
    actors = []
    z = BOARD_HOLES_Z[-1]
    for side, x in zip(('Left', 'Right'), MOUNT_X):
        screw_name, washer_name, nut_name = ('CameraPCB'+kind+side for kind in ('Screw', 'Washer', 'Nut'))
        seat = (x, BOARD_REAR_Y, z)
        washer_seat = (x, BRACKET_FRONT_Y, z)
        nut_seat = (x, NUT_FACE_Y, z)
        bolt = socket_screw(2, 8., seat, SCREW_AXIS)
        washer = cylinder(3.50, .50, washer_seat, SCREW_AXIS).cut(
            cylinder(1.60, .60, (x, BRACKET_FRONT_Y+.05, z), SCREW_AXIS))
        nut_shape = nut(2, nut_seat, SCREW_AXIS).cut(
            cylinder(1., 1.70, (x, NUT_FACE_Y+.05, z), SCREW_AXIS))
        for name, label, shape in ((screw_name, 'M2 × 8 camera PCB screw', bolt),
                                   (washer_name, 'M3 flat camera PCB washer', washer),
                                   (nut_name, 'M2 hex camera PCB nut', nut_shape)):
            add_part(doc, parent, name, f'{label} {side.lower()}', shape, motion)
            actors.append(name)
        rows.append(dict(name=screw_name, motion=motion, skip=['Part066', 'Part067', washer_name, nut_name],
                         shapes=[['cyl', 1.93, 2., [x, BOARD_REAR_Y+2.05, z], SCREW_AXIS],
                                 ['cyl', 1., 7.90, [x, BOARD_REAR_Y-.05, z], SCREW_AXIS]]))
        rows.append(dict(name=washer_name, kind='washer', motion=motion, skip=['Part066', screw_name, nut_name],
                         shapes=[['cyl', 3.50, .50, washer_seat, SCREW_AXIS]]))
        rows.append(dict(name=nut_name, kind='nut', motion=motion, skip=[screw_name, washer_name],
                         shapes=[['hex', 4., 1.60, nut_seat, SCREW_AXIS]]))

    geometry = json.loads(doc.R5.MotionGeometry)
    geometry['camera_pcb_mount'] = {
        'actors': actors, 'pcb_bore_mm': 2.20, 'hole_pitch_mm': 28.,
        'board_front_y_mm': BOARD_FRONT_Y, 'board_thickness_mm': 2.20,
        'm2_thread_protrusion_mm': NUT_OUTER_Y-(BOARD_REAR_Y-8.),
    }
    doc.R5.MotionGeometry = json.dumps(geometry, ensure_ascii=False)
    return rows
