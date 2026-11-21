"""Retain rear skull 29 on frame 09 with two removable transverse M3 screws."""

import json

import FreeCAD as App
import Mesh
import manifold3d as md
import numpy as np
import trimesh

from build_b19_review_fixes import add_part, replace
from build_b21_fasteners import check_solid, detached_shape
from build_b22_fused_skull import solid
from export_cad import world_mesh
from primitives import box, cylinder, print_mesh
from stock import hexagon, socket_screw


FRAME_PRINT = '09_head_frame-B25.stl'
REAR_PRINT = '29_skull_rear-B25.npz'
STATIONS = (('Left', -1, 77.65), ('Right', 1, 75.30))
Y, Z = 27.70, 117.75
LENGTH = 16.
FRAME_FACE = 67.20
SHELL_FACE = 67.55
NUT_FLATS = 5.5
NUT_LENGTH = 2.4
POCKET_FLATS = 5.8
POCKET_INNER, POCKET_OUTER = 61.95, 64.61
HOLE = 1.76
COUNTERBORE = 3.15


def radial_point(side, radius):
    return (side*radius, Y, Z)


def radial_cylinder(side, radius, inner, outer):
    return cylinder(radius, outer-inner, radial_point(side, inner), (side, 0, 0))


def mesh_cylinder(side, radius, inner, outer):
    return (md.Manifold.cylinder(outer-inner, radius, circular_segments=64)
            .rotate((0., 90.*side, 0.)).translate(radial_point(side, inner)))


def mesh_from_solid(shape):
    data = shape.to_mesh64()
    return trimesh.Trimesh(data.vert_properties[:, :3], data.tri_verts, process=False)


def nut_channel(side, inner, outer, flats, rear_y):
    """Swept hex profile from its seated point towards the open rear."""
    hex_seat = hexagon(flats, outer-inner, radial_point(side, inner), (side, 0, 0))
    x0, x1 = sorted((side*inner, side*outer))
    return hex_seat.fuse(box(x0, x1, Y, rear_y, Z-flats/2., Z+flats/2.)).removeSplitter()


def frame_station(frame, side, screw_seat):
    pad = radial_cylinder(side, 4.90, 62., FRAME_FACE)
    cutting = [
        radial_cylinder(side, HOLE, screw_seat-LENGTH-.35, FRAME_FACE+.04),
        nut_channel(side, POCKET_INNER, POCKET_OUTER, POCKET_FLATS, 62.),
    ]
    if pad.common(frame).Volume < 180.:
        raise ValueError('Rear retainer pad does not join the original head frame')
    return check_solid(frame.fuse(pad).cut(cutting), 'Rear skull frame pads')


def shell_station(shell, side, screw_seat):
    boss = mesh_cylinder(side, 4.65, SHELL_FACE, screw_seat+.80)
    cutting = [
        mesh_cylinder(side, COUNTERBORE, screw_seat, 99.),
        mesh_cylinder(side, HOLE, SHELL_FACE-.05, screw_seat+.10),
    ]
    if (shell ^ boss).volume() < 360.:
        raise ValueError('Rear screw boss does not join the original skull')
    for cut in cutting:
        boss = boss - cut
        shell = shell - cut
    return shell + boss


def stock_station(doc, parent, side, hand, seat):
    axis = (-side, 0, 0)
    screw_name = f'RearSkullScrew{hand}'
    screw_seat = radial_point(side, seat)
    screw = socket_screw(3, LENGTH, screw_seat, axis)
    add_part(doc, parent, screw_name, 'M3 × 16 rear skull socket screw', screw, 'head')
    replace(doc.getObject(screw_name), screw)

    nut_name = f'RearSkullNut{hand}'
    nut_inner = POCKET_OUTER-NUT_LENGTH
    nut_seat = radial_point(side, nut_inner)
    nut = hexagon(NUT_FLATS, NUT_LENGTH, nut_seat, (side, 0, 0)).cut(
        radial_cylinder(side, 1.5, nut_inner, POCKET_OUTER)
    )
    add_part(doc, parent, nut_name, 'M3 rear skull hex nut', nut, 'head')
    replace(doc.getObject(nut_name), nut)
    return {'screw': screw_name, 'nut': nut_name, 'axis': list(axis), 'seat_mm': list(screw_seat),
            'nut_axis': [side, 0, 0], 'nut_seat_mm': list(nut_seat),
            'length_mm': LENGTH, 'thread_past_nut_mm': nut_inner-seat+LENGTH}


def apply(doc, print_dir):
    """Update the native B24 frame and rear mesh, preserving the B24 part IDs."""
    shell_obj = doc.Part074
    points, triangles = world_mesh(shell_obj).Topology
    stock = trimesh.Trimesh([tuple(point) for point in points], triangles)
    frame = detached_shape(doc.Part019)
    shell = solid(stock)
    stations = {}
    parent = doc.Part019.getParentGeoFeatureGroup()
    for hand, side, seat in STATIONS:
        frame = frame_station(frame, side, seat)
        shell = shell_station(shell, side, seat)
        stations[hand.lower()] = stock_station(doc, parent, side, hand, seat)
    mesh = mesh_from_solid(shell)
    if (shell.status() != md.Error.NoError or not mesh.is_volume or mesh.body_count != 1
            or not np.allclose(stock.bounds, mesh.bounds, atol=1e-5, rtol=0.)):
        raise ValueError('Rear retainer must preserve one closed shell and the original bounds')

    print_dir.mkdir(parents=True, exist_ok=True)
    print_mesh(frame, print_dir/FRAME_PRINT, 'y+')
    # The +Y direction from the seam is up on the original rear-skull plate.
    print_body = mesh_from_solid(shell.rotate((90., 0., 0.)))
    np.savez_compressed(print_dir/REAR_PRINT, vertices=print_body.vertices, faces=print_body.faces)

    replace(doc.Part019, frame)
    native = Mesh.Mesh(mesh.triangles.tolist())
    shell_parent = shell_obj.getParentGeoFeatureGroup()
    if shell_parent:
        native.transform(shell_parent.getGlobalPlacement().inverse().toMatrix())
    shell_obj.Placement = App.Placement()
    shell_obj.Mesh = native

    spec = {'parts': ['Part019', 'Part074'], 'stations': stations,
            'shell_removal_offset_mm': [0., 68., 0.], 'radial_face_relief_mm': SHELL_FACE-FRAME_FACE}
    geometry = json.loads(doc.R5.MotionGeometry)
    geometry['rear_skull_retention'] = spec
    doc.R5.MotionGeometry = json.dumps(geometry, ensure_ascii=False)
    return spec
