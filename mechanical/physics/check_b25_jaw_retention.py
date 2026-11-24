"""Verify stock-fastener jaw retention, access, and translation clearances in native CAD."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from math import ceil, radians
from pathlib import Path

import FreeCAD as App
import fcl
import numpy as np
import trimesh
from trimesh.collision import mesh_to_BVH

from build_b21_fasteners import detached_shape
from build_b25_jaw_retention import NUT_THICKNESS, PASS_RADIUS, STATIONS, WASHER_RADIUS, frame_boss
from check_head import pose, rotation, translation
from export_cad import tessellate, world_mesh, world_shape
from primitives import cylinder


JAW_PARTS = ('Jaw_30_moving_jaw', 'Jaw_38_left_jaw_drive_arm', 'Jaw_39_right_jaw_pivot_arm',
             'Jaw_36_left_jaw_servo_stay', 'Jaw_37_right_jaw_bearing_stay')
EYE_PARTS = ('Part024', 'Part025', 'Part027')


def digest(path):
    with path.open('rb') as file:
        return file_digest(file, 'sha256').hexdigest()


def geometry(obj):
    mesh = world_mesh(obj) if obj.isDerivedFrom('Mesh::Feature') else tessellate(world_shape(obj))
    return from_topology(mesh)


def from_topology(mesh):
    vertices, triangles = mesh.Topology
    return trimesh.Trimesh([tuple(point) for point in vertices], triangles)


def collision(mesh):
    return fcl.CollisionObject(mesh_to_BVH(mesh))


def gap(first, second, transform):
    second.setTransform(fcl.Transform(transform[:3, :3].copy(), transform[:3, 3].copy()))
    if fcl.collide(first, second, fcl.CollisionRequest(), fcl.CollisionResult()):
        return 0.
    return fcl.distance(first, second, fcl.DistanceRequest(), fcl.DistanceResult())


def verified_gap(minimum, unsampled, label):
    if not np.isfinite(minimum) or minimum <= unsampled:
        raise ValueError(f'Cannot verify continuous clearance for {label}: {minimum:g} mm')
    return {'sampled_mm': float(minimum), 'continuous_lower_bound_mm': float(minimum-unsampled)}


def approach(first, second, extent, label):
    extent = np.asarray(extent, dtype=float)
    length = np.linalg.norm(extent)
    intervals = ceil(length/.20)
    minimum = min(gap(first, second, translation(step*extent)) for step in np.linspace(0., 1., intervals+1))
    return verified_gap(minimum, length/(2*intervals), label)


def sweep(first, second, kind, frame, axis, limits, radius, label):
    angle = np.zeros(5)
    samples = np.linspace(*limits, ceil((limits[1]-limits[0])/.04)+1)
    minimum = np.inf
    for at in samples:
        angle[axis] = at
        minimum = min(minimum, gap(first, second, pose(kind, angle, frame)))
    return verified_gap(minimum, radius*radians((samples[1]-samples[0])/2), label)


def verify_washer_support(frame, stay, nut, station, x, y):
    base = (x, y, station['frame_facing_z_mm']+.005)
    support_depth = station['minimum_nut_floor_mm']-.01
    annulus = cylinder(WASHER_RADIUS, support_depth, base).cut(cylinder(PASS_RADIUS, support_depth, base))
    column_support = frame.common(annulus).Volume/annulus.Volume
    seat = tuple(station['nut_seat_mm'])
    usable_nut = world_shape(nut).cut(cylinder(PASS_RADIUS, NUT_THICKNESS, seat))
    supported_area = usable_nut.common(cylinder(WASHER_RADIUS, NUT_THICKNESS, seat)).Volume/NUT_THICKNESS
    nut_fraction = supported_area/(usable_nut.Volume/NUT_THICKNESS)
    angles = np.linspace(0., 2*np.pi, 72, endpoint=False)
    sample = np.array([(x+r*np.cos(angle), y+r*np.sin(angle), station['shim_seat_mm'][2]-.025)
                       for r in np.linspace(PASS_RADIUS+.05, WASHER_RADIUS-.05, 4) for angle in angles])
    if min(column_support, nut_fraction) < .95 or not stay.contains(sample).all():
        raise ValueError('The steel washer must support the captured nut footprint on both clamp faces')
    return {'frame_column_fraction': column_support, 'supported_nut_bearing_fraction': nut_fraction,
            'supported_bearing_area_mm2': supported_area,
            'stay_material_samples': len(sample), 'minimum_tab_floor_mm': station['minimum_nut_floor_mm']}



def check(reference, assembly):
    before = App.openDocument(str(reference.resolve()))
    current = App.openDocument(str(assembly.resolve()))
    try:
        return check_document(before, current, reference, assembly)
    finally:
        App.closeDocument(current.Name)
        App.closeDocument(before.Name)


def check_document(before, current, reference, assembly):
    raw_frame = detached_shape(before.Part019)
    held_frame = detached_shape(current.Part019)
    frame = {'motion_geometry': json.loads(current.R5.MotionGeometry),
             'jaw_pivot_mm': list(current.JawMotion.Placement.Base)}
    spec = frame['motion_geometry']['jaw_retention']['stations']
    names = ('Part073', 'Part011', 'Part018', 'Part015', 'Part013', 'Part044', *EYE_PARTS, *JAW_PARTS)
    actors = {name: geometry(current.getObject(name)) for name in names}
    objects = {name: collision(item) for name, item in actors.items()}
    results = {}
    for hand, x, y, z, stay, _ in STATIONS:
        branch_shape = held_frame.common(frame_boss(x, y, z)).cut(raw_frame)
        branch = collision(from_topology(tessellate(branch_shape)))
        data = {'shell_feed': approach(branch, objects['Part073'], (0., -84., 0.), f'{hand} shell feed'),
                'eye_feed': {name: approach(branch, objects[name], (0., -64., 0.), f'{hand} {name} feed')
                             for name in EYE_PARTS},
                'jaw_feed': {name: approach(branch, objects[name], (0., 0., -76.), f'{hand} {name} feed')
                             for name in JAW_PARTS}}
        motions = (('Part024', 1, (-8.4, 8.4), (0., -39., 119.)), ('Part044', 1, (-8.4, 8.4), (0., -39., 119.)),
                   ('Part011', 0, (-17.21, 7.13), (0., 0., 112.)), ('Part018', 0, (-17.21, 7.13), (0., 0., 112.)))
        data['motion'] = {}
        for name, axis, limits, pivot in motions:
            radius = np.linalg.norm(actors[name].vertices-np.array(pivot), axis=1).max()
            data['motion'][name] = sweep(branch, objects[name], current.getObject(name).Motion, frame,
                                         axis, limits, radius, f'{hand} {name} running clearance')
        shaft = 'Part013' if hand == 'Left' else 'Part015'
        data['drive_shaft_gap_mm'] = gap(branch, objects[shaft], np.eye(4))
        if data['drive_shaft_gap_mm'] < .15:
            raise ValueError(f'{hand} tab interferes with the drive shaft')
        station = spec[hand.lower()]
        nut_obj = current.getObject(station['nut'])
        data['washer_support'] = verify_washer_support(held_frame, actors[stay], nut_obj, station, x, y)
        nut = collision(geometry(nut_obj))
        complete_frame = collision(from_topology(tessellate(held_frame)))
        # Slide through the full corners at the midpoint of the 0.25 mm axial pocket play.
        offsets = np.linspace(0., 20.*np.sign(x), 401)
        entry_gap = min(gap(complete_frame, nut, translation((dx, 0., -.125))) for dx in offsets)
        data['nut_feed'] = verified_gap(entry_gap, .025, f'{hand} captured nut feed')
        pocket_spin = translation((0., 0., -.125)) @ rotation(30., (0., 0., 1.), station['nut_seat_mm'])
        if gap(complete_frame, nut, pocket_spin) > 0.:
            raise ValueError(f'The {hand} captive nut can spin in its pocket')
        data['nut_spin_blocked_by_deg'] = 30.
        screw_mesh = geometry(current.getObject(station['screw']))
        screw = collision(screw_mesh)
        if gap(screw, objects[stay], translation((0., 0., -.25))) > 0.:
            raise ValueError(f'{hand} stay can descend past its captured screw head')
        data['screw_head_blocks_drop_by_mm'] = .25
        seat = station['screw_seat_mm'][2]
        tool = collision(from_topology(tessellate(cylinder(1.52, 58., (x, y, seat-59.)))))
        arm = JAW_PARTS[1] if x < 0 else JAW_PARTS[2]
        radius = np.linalg.norm(actors[arm].vertices-np.array(frame['jaw_pivot_mm']), axis=1).max()
        data['seated_driver'] = sweep(tool, objects[arm], 'jaw', frame, 4, (-.5, 9.71), radius, f'{hand} arm/driver')
        # The nut loses thread overlap before 4 mm of downward screw travel.
        # Sample both that travel and all powered jaw angles around the screw head.
        gap_during_release = np.inf
        jaw_angles = np.linspace(-.5, 9.71, 205)
        for retract in np.linspace(0., 4., 21):
            backing_out = translation((0., 0., retract))
            for opening in jaw_angles:
                arm_pose = pose('jaw', (0., 0., 0., 0., opening), frame)
                gap_during_release = min(gap_during_release, gap(screw, objects[arm], backing_out @ arm_pose))
        reserve = .10 + radius*radians((jaw_angles[1]-jaw_angles[0])/2.)
        data['screw_four_mm_backout'] = verified_gap(gap_during_release, reserve, f'{hand} retained screw release')
        results[hand.lower()] = data
    return {
        'source_cad_sha256': digest(reference), 'cad_sha256': digest(assembly), 'stations': results,
        'scope': 'Rigid native geometry with independently swept added tabs. Both screws are preloaded into the '
                 'stays before the arms are assembled. The driver sweep is for inserting and releasing those '
                 'preloaded screws. Print fit, retention strength, and electrical commissioning require bench checks.',
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for key in ('reference', 'assembly', 'output'):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    report = check(args.reference, args.assembly)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(args.output)
