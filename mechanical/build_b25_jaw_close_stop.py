"""Add a matched pair of adjustable, lockable stops for closing the jaw."""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App
import Mesh
import manifold3d as md
import numpy as np
import trimesh

from build_b19_review_fixes import add_part, replace
from build_b22_fused_skull import solid
from export_cad import world_mesh
from primitives import cylinder


STATIONS = (
    ('Left', -52., -20., 82.657, 97., 'Jaw_36_left_jaw_servo_stay', '36_left_cheek_servo_stay-B25.stl'),
    ('Right', 53., -19., 84.7665, 102., 'Jaw_37_right_jaw_bearing_stay', '37_right_cheek_bearing_stay-B25.stl'),
)
STOP_LENGTH = 12.
JAM_LENGTH = 3.
FREE_LENGTH = 4.8
BOSS_RADIUS = 3.1
THREAD_RADIUS = 1.50
PILOT_RADIUS = 1.25


def mesh_from_solid(shape, name):
    data = shape.to_mesh64()
    mesh = trimesh.Trimesh(data.vert_properties[:, :3], data.tri_verts, process=False)
    if shape.status() != md.Error.NoError or not mesh.is_volume or mesh.body_count != 1:
        raise ValueError(f'Closing-stop boss must create a single closed stay: {name}')
    return mesh


def modify(stay, x, y, tip, anchor, bore_radius):
    boss_bottom = tip + FREE_LENGTH
    boss = md.Manifold.cylinder(anchor-boss_bottom, BOSS_RADIUS, circular_segments=64).translate((x, y, boss_bottom))
    if (stay ^ boss).volume() < 60.:
        raise ValueError('The closing-stop boss does not reach the original stay')
    drill = md.Manifold.cylinder(120.-boss_bottom, bore_radius, circular_segments=64).translate((x, y, boss_bottom))
    return (stay+boss)-drill


def apply(doc, print_dir=None):
    spec = {'intended_nominal_close_stop_deg': -.20, 'stations': {}}
    if print_dir:
        print_dir.mkdir(parents=True, exist_ok=True)
    for hand, x, y, tip, anchor, name, filename in STATIONS:
        obj = doc.getObject(name)
        points, facets = world_mesh(obj).Topology
        stock = trimesh.Trimesh([tuple(p) for p in points], facets)
        shape = solid(stock)
        finished = mesh_from_solid(modify(shape, x, y, tip, anchor, THREAD_RADIUS), name)
        parent = obj.getParentGeoFeatureGroup()
        native = Mesh.Mesh(finished.triangles.tolist())
        if parent:
            native.transform(parent.getGlobalPlacement().inverse().toMatrix())
        obj.Placement = App.Placement()
        obj.Mesh = native
        if print_dir:
            pilot = mesh_from_solid(modify(shape, x, y, tip, anchor, PILOT_RADIUS), name)
            orient = trimesh.transformations.rotation_matrix(np.radians(-90.), (0., 1., 0.))
            bounds = stock.apply_transform(orient).bounds
            pilot.apply_transform(orient)
            pilot.apply_translation(-np.r_[bounds.mean(axis=0)[:2], bounds[0, 2]])
            pilot.export(print_dir/filename)

        screw_name, jam_name = (f'JawClose{kind}{hand}' for kind in ('Stop', 'Jam'))
        for actor, length, z in ((screw_name, STOP_LENGTH, tip), (jam_name, JAM_LENGTH, tip+STOP_LENGTH)):
            # Cylinder is the occupied steel envelope of the ISO 4026 flat-point screw.
            part = cylinder(1.499, length, (x, y, z))
            added = add_part(doc, parent, actor, f'M3 × {length:g} flat point jaw close stop hardware', part, 'head')
            replace(added, part)
        spec['stations'][hand.lower()] = {
            'stay': name, 'stop': screw_name, 'jam': jam_name, 'stop_tip_mm': [x, y, tip],
            'adjustment_thread': 'M3 × 0.5', 'tap_drill_mm': 2*PILOT_RADIUS,
            'boss_anchor_z_mm': anchor, 'minimum_engaged_length_mm': STOP_LENGTH-FREE_LENGTH-.5,
        }

    geometry = json.loads(doc.R5.MotionGeometry)
    geometry['jaw_close_stop'] = spec
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
        print(json.dumps(apply(document, args.prints), indent=2))
        document.recompute()
        document.saveAs(str(args.output.resolve()))
    finally:
        App.closeDocument(document.Name)
