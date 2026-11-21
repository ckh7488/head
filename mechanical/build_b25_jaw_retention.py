"""Retain each jaw bearing stay on the moving frame with a removable stock M3 screw."""

from argparse import ArgumentParser
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import FreeCAD as App
import Mesh
import manifold3d as md
import numpy as np
import trimesh

from build_b19_review_fixes import add_part, replace
from build_b21_fasteners import check_solid, detached_shape
from build_b22_fused_skull import solid
from build_b24 import write_front_skull
from export_cad import world_mesh
from primitives import box, cylinder, print_mesh
from stock import hexagon, socket_screw


FRAME_PRINT = '09_head_frame-B25.stl'
SHELL_PRINT = '28_skull_front_with_camera_tray-B25.npz'
FEED_RELIEF_MM = .24
STATIONS = (
    ('Left', -61.7, -30., 112.5, 'Jaw_36_left_jaw_servo_stay', '36_left_cheek_servo_stay-B25.stl'),
    ('Right', 63., -16., 109.5, 'Jaw_37_right_jaw_bearing_stay', '37_right_cheek_bearing_stay-B25.stl'),
)
LENGTH = 16.
AXIS = (0., 0., 1.)
FACE_RELIEF = .20
HEAD_DEPTH = 9.25


def dimensions(x):
    return (12.30, .55, 3.20) if x < 0 else (HEAD_DEPTH, 3.20, 5.85)

PASS_RADIUS = 1.68
COUNTERBORE = 3.10
NUT_FLATS = 5.5
POCKET_FLATS = 5.85
NUT_THICKNESS = 2.40
WASHER_RADIUS = 3.00
COLLAR_RADIUS = 3.12
WASHER_POCKET_DEPTH = .60
WASHER_POCKET_RADIUS = 3.43
SIDE_CHANNEL_HALF_WIDTH = 3.40


def frame_boss(x, y, z):
    if x < 0:
        bridge = box(-62.74, -57., y-.3, -4.13, 112.7, 116.30)
        root = box(-62.74, -57., -6.05, -4.13, 109.7, 116.30)
        column = box(-64.52, -57.65, y-3.60, y+3.60, z+FACE_RELIEF, 116.30)
        relief = box(-62.40, -56., -35., -31.45, 115.25, 116.5)
        shoe = cylinder(COLLAR_RADIUS, 1.60+WASHER_POCKET_DEPTH,
                        (x, y, z-WASHER_POCKET_DEPTH+FACE_RELIEF))
        return bridge.fuse([root, column.cut(relief), shoe]).removeSplitter()
    bridge = box(x-1.55, x+3.25, y-.25, -4.13, 113.65, 116.80)
    root = box(x-1.55, x+3.25, -6.05, -3.50, 114.45, 116.80)
    upper = cylinder(4., 4.65, (x, y, 112.15))
    lower = cylinder(COLLAR_RADIUS, 2.65+WASHER_POCKET_DEPTH,
                     (x, y, z-WASHER_POCKET_DEPTH+FACE_RELIEF))
    return bridge.fuse([root, upper, lower]).removeSplitter()


def frame_station(frame, x, y, z):
    boss = frame_boss(x, y, z)
    if frame.common(boss).Volume < 10.:
        raise ValueError(f'Forward retention bridge at {x:g} must join the head frame')
    head_depth, pocket_bottom, pocket_top = dimensions(x)
    seat = (x, y, z+pocket_bottom)
    hex_seat = hexagon(POCKET_FLATS, pocket_top-pocket_bottom, seat, AXIS)
    x_min, x_max = sorted((x, x+5.*np.sign(x)))
    # The side-loaded nut presents its corners to the Y walls of the slot.
    slot = box(x_min, x_max, y-SIDE_CHANNEL_HALF_WIDTH, y+SIDE_CHANNEL_HALF_WIDTH,
               z+pocket_bottom, z+pocket_top)
    bore = cylinder(PASS_RADIUS, LENGTH-head_depth+.60+WASHER_POCKET_DEPTH,
                    (x, y, z-WASHER_POCKET_DEPTH))
    return check_solid(frame.fuse(boss).cut([bore, hex_seat.fuse(slot)]), 'Jaw retention bridge and pockets')


def mesh_from_solid(shape):
    mesh = shape.to_mesh64()
    return trimesh.Trimesh(mesh.vert_properties[:, :3], mesh.tri_verts, process=False)


def cut_stay(obj, x, y, z):
    points, facets = world_mesh(obj).Topology
    original = trimesh.Trimesh([tuple(p) for p in points], facets)
    head_depth, _, _ = dimensions(x)
    seat = z - head_depth
    cuts = (
        md.Manifold.cylinder(65., COUNTERBORE, circular_segments=64).translate((x, y, seat-65.)),
        md.Manifold.cylinder(head_depth + .20, PASS_RADIUS, circular_segments=64).translate((x, y, seat-.10)),
        md.Manifold.cylinder(WASHER_POCKET_DEPTH+.10, WASHER_POCKET_RADIUS,
                              circular_segments=64).translate((x, y, z-WASHER_POCKET_DEPTH)),
    )
    result = solid(original)
    for cut in cuts:
        result -= cut
    cut = mesh_from_solid(result)
    if (result.status() != md.Error.NoError or not cut.is_volume or cut.body_count != 1
            or abs(original.volume-cut.volume) < 70.):
        raise ValueError(f'Cannot form one closed counterbored stay: {obj.Name}')
    return original, cut


def replace_mesh(obj, cut):
    mesh = Mesh.Mesh(cut.triangles.tolist())
    parent = obj.getParentGeoFeatureGroup()
    if parent:
        mesh.transform(parent.getGlobalPlacement().inverse().toMatrix())
    obj.Placement = App.Placement()
    obj.Mesh = mesh


def stock_station(doc, parent, hand, x, y, z, stay):
    screw_name = f'JawRetentionScrew{hand}'
    head_depth, _, pocket_top = dimensions(x)
    screw_seat = (x, y, z-head_depth)
    screw = socket_screw(3, LENGTH, screw_seat, AXIS)
    actor = add_part(doc, parent, screw_name, 'M3 × 16 jaw stay socket screw', screw, 'head')
    replace(actor, screw)

    nut_name = f'JawRetentionNut{hand}'
    nut_seat = (x, y, z+pocket_top-NUT_THICKNESS)
    nut = hexagon(NUT_FLATS, NUT_THICKNESS, nut_seat, AXIS).cut(
        cylinder(1.5, NUT_THICKNESS, nut_seat))
    actor = add_part(doc, parent, nut_name, 'M3 jaw stay hex nut', nut, 'head')
    replace(actor, nut)
    shim_name = f'JawRetentionShim{hand}'
    shim_seat = (x, y, z-WASHER_POCKET_DEPTH)
    shim = cylinder(WASHER_RADIUS, FACE_RELIEF, shim_seat).cut(cylinder(PASS_RADIUS, FACE_RELIEF, shim_seat))
    actor = add_part(doc, parent, shim_name, '3.4 × 6.0 × 0.2 mm steel jaw shim washer', shim, 'head')
    replace(actor, shim)
    return {
        'shim': shim_name, 'shim_seat_mm': list(shim_seat), 'shim_od_mm': 2*WASHER_RADIUS,
        'stay': stay, 'screw': screw_name, 'nut': nut_name,
        'axis': list(AXIS), 'screw_seat_mm': list(screw_seat), 'nut_seat_mm': list(nut_seat),
        'length_mm': LENGTH, 'thread_past_nut_mm': LENGTH-head_depth-pocket_top,
        'clearance_diameter_mm': 2*PASS_RADIUS, 'counterbore_diameter_mm': 2*COUNTERBORE,
        'frame_facing_z_mm': z-WASHER_POCKET_DEPTH+FACE_RELIEF,
        'washer_recess_depth_mm': WASHER_POCKET_DEPTH,
        'washer_recess_diameter_mm': 2*WASHER_POCKET_RADIUS,
        'nut_feed_y_width_mm': 2*SIDE_CHANNEL_HALF_WIDTH,
        'nut_thickness_mm': NUT_THICKNESS,
        'minimum_nut_floor_mm': dimensions(x)[1]-FACE_RELIEF+WASHER_POCKET_DEPTH,
    }


def front_shell_feed_relief(doc, print_dir):
    obj = doc.Part073
    points, triangles = world_mesh(obj).Topology
    stock = trimesh.Trimesh([tuple(p) for p in points], triangles)
    before = solid(stock)
    body = before
    # The rigid front shell is fed along +Y. Open only the channels swept by the
    # new frame tabs in shell coordinates, with clearance at their XZ edges.
    right_boxes = ((61.45, 66.25, -16.25, 113.65, 116.80),
                   (61.45, 66.25, -6.05, 114.45, 116.80),
                   (59.88, 66.12, -19.12, 109.10, 112.35),
                   (59., 67., -20., 112.15, 116.80))
    left_boxes = ((-62.74, -57., -30.30, 112.70, 116.30),
                  (-62.74, -57., -6.05, 109.70, 116.30),
                  (-64.52, -57.65, -33.60, 112.70, 116.30),
                  (-64.82, -58.58, -33.12, 112.10, 114.30))
    reserve = FEED_RELIEF_MM
    for x0, x1, y0, z0, z1 in (*left_boxes, *right_boxes):
        low = (x0-reserve, y0-reserve, z0-reserve)
        high = (x1+reserve, 22.5, z1+reserve)
        body -= md.Manifold.cube(np.subtract(high, low)).translate(low)
    body, *detached = sorted(body.decompose(), key=lambda piece: piece.volume(), reverse=True)
    fragments = [{'volume_mm3': p.volume(), 'bounds_mm': mesh_from_solid(p).bounds.tolist()} for p in detached]
    if sum(p['volume_mm3'] for p in fragments) > 35.:
        raise ValueError(f'Unexpected split shell components: {fragments}')
    mesh = mesh_from_solid(body)
    if (not mesh.is_volume or mesh.body_count != 1 or body.status() != md.Error.NoError
            or not np.allclose(mesh.bounds, stock.bounds, atol=1e-5, rtol=0)):
        raise ValueError('Jaw retainer entry channels must preserve the front shell')
    replace_mesh(obj, mesh)
    if print_dir:
        with TemporaryDirectory() as temporary:
            shell, tray = (Path(temporary)/name for name in ('shell.stl', 'tray.stl'))
            world_mesh(obj).write(str(shell))
            world_mesh(doc.Part065).write(str(tray))
            write_front_skull(shell, tray, print_dir/SHELL_PRINT)
    return {'part': obj.Name, 'feed_axis': [0., 1., 0.], 'reserve_mm': reserve,
            'removed_volume_mm3': before.volume()-body.volume(), 'detached_internal_fragments': fragments}


def apply(doc, print_dir=None):
    frame_obj = doc.Part019
    frame = detached_shape(frame_obj)
    parent = frame_obj.getParentGeoFeatureGroup()
    spec = {'frame': frame_obj.Name, 'frame_to_stay_relief_mm': FACE_RELIEF, 'stations': {}}
    if print_dir:
        print_dir.mkdir(parents=True, exist_ok=True)
    for hand, x, y, z, stay, file in STATIONS:
        frame = frame_station(frame, x, y, z)
        obj = doc.getObject(stay)
        original, cut = cut_stay(obj, x, y, z)
        replace_mesh(obj, cut)
        spec['stations'][hand.lower()] = stock_station(doc, parent, hand, x, y, z, stay)
        if print_dir:
            rotation = trimesh.transformations.rotation_matrix(np.radians(-90.), (0., 1., 0.))
            bounds = original.apply_transform(rotation).bounds
            cutting = cut.copy().apply_transform(rotation)
            cutting.apply_translation(-np.r_[bounds.mean(axis=0)[:2], bounds[0, 2]])
            cutting.export(print_dir/file)
    if print_dir:
        print_mesh(frame, print_dir/FRAME_PRINT, 'y+')
    replace(frame_obj, frame)
    geometry = json.loads(doc.R5.MotionGeometry)
    spec['front_shell_feed'] = front_shell_feed_relief(doc, print_dir)
    geometry['jaw_retention'] = spec
    doc.R5.MotionGeometry = json.dumps(geometry, ensure_ascii=False)
    return spec


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--prints', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('Choose a separate native assembly output')
    document = App.openDocument(str(args.source.resolve()))
    try:
        report = apply(document, args.prints)
        document.recompute()
        document.saveAs(str(args.output.resolve()))
        print(json.dumps(report, indent=2), flush=True)
    finally:
        App.closeDocument(document.Name)
