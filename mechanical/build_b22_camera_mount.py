"""Seat the camera bracket on two accessible M3 screws in the nasal tray."""


import FreeCAD as App
import Mesh
import trimesh

from build_b19_review_fixes import add_part, replace
from build_b21_fasteners import check_solid, detached_shape, screw_spec
from export_cad import world_mesh
from primitives import box, cylinder
from stock import socket_screw


SCREW_X = (-12., 12.)
SCREW_Y = -47.
SCREW_SEAT = 74.80
TRAY_TOP = 70.75
PILOT_BOTTOM = 66.60
TRAY_PRINT = '25_nasal_tray-B22.stl'


def right_screw_head_relief():
    return cylinder(3.10, 8., (SCREW_X[-1], SCREW_Y, SCREW_SEAT))


def mounting_tray(obj, output):
    points, triangles = world_mesh(obj).Topology
    original = trimesh.Trimesh([tuple(point) for point in points], triangles)

    def pilots(radius):
        height = TRAY_TOP + .15 - PILOT_BOTTOM
        return [trimesh.creation.cylinder(radius=radius, height=height, sections=96)
                .apply_translation((x, SCREW_Y, PILOT_BOTTOM + height/2)) for x in SCREW_X]

    fitted = trimesh.boolean.difference([original, *pilots(1.55)], engine='manifold')
    printed = trimesh.boolean.difference([original, *pilots(1.325)], engine='manifold')
    for mesh in (fitted, printed):
        if not mesh.is_volume or mesh.body_count != 1 or not mesh.nondegenerate_faces().all():
            raise ValueError('Camera tray must remain one printable solid')
    mesh = Mesh.Mesh(fitted.triangles.tolist())
    parent = obj.getParentGeoFeatureGroup()
    if parent:
        mesh.transform(parent.getGlobalPlacement().inverse().toMatrix())
    obj.Placement = App.Placement()
    obj.Mesh = mesh
    x, y, _ = printed.bounds.mean(axis=0)
    printed.apply_translation((-x, -y, -printed.bounds[0, 2])).export(output)


def apply(doc, print_dir):
    mounting_tray(doc.Part065, print_dir / TRAY_PRINT)
    stock = detached_shape(doc.Part066)
    feet = [cylinder(3.50, SCREW_SEAT-TRAY_TOP, (x, SCREW_Y, TRAY_TOP)) for x in SCREW_X]
    plugs = [cylinder(1.90, 4.00, (x, -50., 70.80)) for x in (-14., 14.)]
    clearance = [cylinder(1.70, 4.45, (x, SCREW_Y, 70.60)) for x in SCREW_X]
    pcb_seat = box(-16.30, 16.30, -53.55, -50.80, 72.75, 75.05)
    pcb_face = box(-16.35, 16.35, -53.52, -53.26, 72.75, 116.)
    lens_lift = cylinder(7.25, 4.2, (0., -57.2, 98.35), (0, 1, 0)).fuse(
        box(-7.25, 7.25, -57.2, -53.0, 89., 98.35))
    bracket = check_solid(stock.fuse(feet+plugs).cut(
        [pcb_seat, pcb_face, lens_lift, right_screw_head_relief(), *clearance]),
                          'B22 camera bracket feet and lens opening')
    replace(doc.Part066, bracket)
    motion = doc.Part066.Motion
    parent = doc.Part066.getParentGeoFeatureGroup()
    axis = (0., 0., -1.)
    hardware = []
    for side, x in zip(('Left', 'Right'), SCREW_X):
        name = f'CameraTrayScrew{side}'
        seat = (x, SCREW_Y, SCREW_SEAT)
        add_part(doc, parent, name, f'M3 × 8 camera bracket screw {side.lower()}',
                 socket_screw(3, 8., seat, axis), motion)
        hardware.append(screw_spec(name, seat, axis, motion, ('Part065', 'Part066')))
    return bracket, hardware
