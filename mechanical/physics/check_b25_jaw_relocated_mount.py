"""Build and measure the exploratory B25 rear jaw nut layout in native FreeCAD."""

from argparse import ArgumentParser
from dataclasses import dataclass
import json
from math import ceil
from pathlib import Path

import fcl
import FreeCAD as App
import numpy as np

from build_b19_review_fixes import add_part, replace
from build_b21_fasteners import check_solid, detached_shape
from build_b22_fused_skull import solid
from build_b25_jaw_retention import mesh_from_solid, replace_mesh
from check_b25_jaw_retention import collision, digest, from_topology, gap, geometry
from check_head import pose, translation
from export_cad import tessellate
from primitives import box, cylinder
from stock import hexagon, socket_screw
from tool_access import WRENCH_THICKNESS, wrench_profile, wrench_shape


Z = (0., 0., 1.)
REAR = (0., 1., 0.)
BORE = 1.73
NUT_HEIGHT = 2.4
CLAMP_RELIEF = .2
CLEARANCE = .15
NECK_LIMITS = (-17.21, 7.13)
JAW_LIMITS = (-.5, 9.71)
PITCH_OBSTACLES = ('Part011', 'Part012', 'Part013', 'Part014', 'Part015', 'Part016', 'Part018',
                   'PitchLimitLink', 'PitchLimitLowerPin', 'PitchLimitUpperPin')
HEAD_OBSTACLES = ('Part019', 'Part024', 'Part025', 'Part027', 'Part041', 'Part044', 'Part073', 'Part074')
JAW_OBSTACLES = ('Jaw_30_moving_jaw', 'Jaw_36_left_jaw_servo_stay', 'Jaw_37_right_jaw_bearing_stay',
                 'Jaw_38_left_jaw_drive_arm', 'Jaw_39_right_jaw_pivot_arm', 'Jaw_XL330_M288_Jaw',
                 'Jaw_MR104ZZ_jaw_right', 'HarnessID6EH')


@dataclass(frozen=True)
class Station:
    side: str
    stay: str
    x: float
    y: float
    nut_z: float
    shoe_bottom: float
    tab_half_width: float
    lower_arch: float

    @property
    def shoe_top(self):
        return self.nut_z - 4. - CLAMP_RELIEF


STATIONS = (
    Station('Left', 'Jaw_36_left_jaw_servo_stay', -36.8, -.65, 128.7, 119., 4., 7.3),
    Station('Right', 'Jaw_37_right_jaw_bearing_stay', 43.8, 16.5, 102., 93.3, 3., 5.),
)


def mesh(shape):
    return from_topology(tessellate(shape))


def frame_arm(station):
    x, y, z = station.x, station.y, station.nut_z
    edges = (x-station.tab_half_width, x+station.tab_half_width)
    underside = z + station.lower_arch
    roof = underside + 5.8
    foot = cylinder(4.35, 4., (x, y, z-4.))
    toe = box(*edges, y-4.95, y-3., z-4., z)
    riser = box(*edges, y-5.75, y-4.35, z-4., underside+.2)
    bridge = box(*edges, y-5.75, 26.8, underside, roof)
    anchor = box(*edges, 23.5, 26.8, roof-.3, max(140., roof+.3))
    bore = cylinder(BORE, 5., (x, y, z-4.5))
    return check_solid(foot.fuse([toe, riser, bridge, anchor]).cut(bore), station.side + ' frame arm')


def stay_extension(station):
    x, y, z = station.x, station.y, station.shoe_top
    low = station.shoe_bottom
    foot = cylinder(4.35, z-low, (x, y, low))
    if station.side == 'Left':
        foot = foot.common(box(x-5., x+5., y-5., 2.55, low-.2, z+.2))
        root = box(x-5.75, x+1.3, 1.15, 2.55, 117., 120.0)
        head_seat = hexagon(5.82, 2.28, (x, y, low-.18), Z)
        foot = foot.fuse(root).cut(head_seat)
    else:
        lead = box(x-3.8, x+3.45, -2.8, y, low, z)
        root = box(39.8, 44.3, -6.1, 1., 97.12, 97.85)
        foot = foot.fuse([lead, root])
    bore = cylinder(BORE, z-low+.6, (x, y, low-.3))
    return check_solid(foot.cut(bore), station.side + ' stay extension')


def hardware(station):
    x, y, bottom = station.x, station.y, station.shoe_bottom
    nut_seat = (x, y, station.nut_z)
    if station.side == 'Left':
        bolt = hexagon(5.5, 2., (x, y, bottom), Z).fuse(cylinder(1.5, 12., (x, y, bottom+2.)))
    else:
        bolt = socket_screw(3, 12., (x, y, bottom), Z)
    nut = hexagon(5.5, NUT_HEIGHT, nut_seat, Z).cut(cylinder(1.5, NUT_HEIGHT, nut_seat))
    shim_seat = (x, y, station.shoe_top)
    shim = cylinder(3.1, CLAMP_RELIEF, shim_seat).cut(cylinder(BORE, CLAMP_RELIEF, shim_seat))
    return {'Screw': bolt, 'Nut': nut, 'Shim': shim}


def add_hardware(doc, parent, station, items):
    length = 'M3 × 12 hex head' if station.side == 'Left' else 'M3 × 12 socket head'
    labels = {'Screw': length, 'Nut': 'M3 loose hex nut', 'Shim': 'Ø6.2 × 0.20 mm steel shim'}
    for key, shape in items.items():
        actor = add_part(doc, parent, f'JawRelocated{key}{station.side}', labels[key], shape, 'head')
        replace(actor, shape.copy())


def minimum_gap(fixed, moving, parameters, transform):
    fixed.setTransform(fcl.Transform())
    distance, parameter = min((gap(fixed, moving, transform(sample)), float(sample)) for sample in parameters)
    return {'sampled_mm': distance, 'at': parameter}


def linear(fixed, moving, start, direction, travel, step=.25):
    count = ceil(abs(travel)/step)
    limits = np.linspace(0., travel, count+1)
    result = minimum_gap(fixed, moving, limits, lambda value: translation(start+value*np.asarray(direction)))
    result['continuous_lower_bound_mm'] = max(0., result['sampled_mm'] - abs(travel)/(2*count))
    result['sample_step_mm'] = abs(travel)/count
    return result


def motion_gaps(layout, probe, actors, skip=()):
    limits_by_motion = {'pan': (0, NECK_LIMITS), 'pitch_link': (0, NECK_LIMITS),
                        'tilt': (1, (-8.4, 8.4)), 'tilt_link': (1, (-8.4, 8.4)), 'jaw': (4, JAW_LIMITS)}
    rows = {}
    for name, (actor, motion) in actors.items():
        if name in skip:
            continue
        if motion in limits_by_motion:
            axis, limits = limits_by_motion[motion]
            angles = np.zeros(5)

            def at(value):
                angles[axis] = value
                return pose(motion, angles, layout)

            samples = np.linspace(*limits, ceil((limits[1]-limits[0])/.4)+1)
            rows[name] = minimum_gap(probe, actor, samples, at)
        else:
            rows[name] = minimum_gap(probe, actor, [0.], lambda value: np.eye(4))
    return rows


def stage_clearance(station, arm, raw_extension, items, frame, actors, layout):
    x, y, z = station.x, station.y, station.nut_z
    branch, extension = (collision(mesh(item)) for item in (arm, raw_extension))
    base = np.zeros(3)
    working = {key: value for key, value in actors.items() if key != 'Part074'}
    working['ModifiedFrame'] = (collision(mesh(frame)), 'head')
    wrench = wrench_shape((x, y, z+.31), Z, REAR, wrench_profile(3), WRENCH_THICKNESS[3])
    wrench_test = collision(mesh(wrench))
    wrench_gaps = {name: linear(actor, wrench_test, base, REAR, 60.) for name, (actor, _) in working.items()
                   if name != 'Part019'}
    wrench_turn_overlaps = {}
    for angle in (-15, -10, -5, 5, 10, 15):
        turned = wrench.copy()
        turned.rotate(App.Vector(x, y, z), App.Vector(*Z), angle)
        wrench_turn_overlaps[str(angle)] = frame.common(turned).Volume
    tool_nut_overlap = wrench.common(items['Nut']).Volume
    lifted_nut = items['Nut'].copy()
    nut_lift = items['Screw'].BoundBox.ZMax-z+.25
    lifted_nut.translate(App.Vector(0., 0., nut_lift))
    nut_feed = collision(mesh(lifted_nut))
    nut_gaps = {name: linear(actor, nut_feed, base, REAR, 60.) for name, (actor, _) in working.items()
                if name != 'Part019'}
    nut_roll = (items['Nut'].common(arm).Volume, lifted_nut.common(arm).Volume)
    nut_descent = {name: linear(actor, nut_feed, base, Z, .025-nut_lift)
                   for name, (actor, _) in working.items() if name != 'Part019'}
    front_feed = linear(branch, actors['Part073'][0], base, REAR, -84.)
    jaw_feed = {name: linear(actor, extension, base, Z, -76.) for name, (actor, _) in actors.items()
                if name in (*PITCH_OBSTACLES, 'Part073', 'Part074')}
    driver = None
    if station.side == 'Right':
        driver_solid = cylinder(1.55, 50., (x, y, station.shoe_bottom-53.))
        driver_probe = collision(mesh(driver_solid))
        driver = motion_gaps(layout, driver_probe, working, skip=('Part019', station.stay))
    return {
        'front_shell_feed': front_feed,
        'added_stay_vertical_feed': jaw_feed,
        'added_frame_running': motion_gaps(layout, branch, actors, skip=('Part019',)),
        'added_stay_running': motion_gaps(layout, extension, actors, skip=(station.stay,)),
        'stock_bolt_running': motion_gaps(layout, collision(mesh(items['Screw'])), actors,
                                          skip=('Part019', station.stay)),
        'rear_cover_off_wrench_feed': wrench_gaps,
        'seated_wrench_frame_overlap_by_angle_mm3': wrench_turn_overlaps,
        'wrench_vs_seated_nut_overlap_mm3': tool_nut_overlap,
        'rear_cover_off_loose_nut_feed': nut_gaps,
        'loose_nut_descent_to_0_025_mm_above_seat': nut_descent,
        'loose_nut_lift_above_seat_mm': nut_lift,
        'seated_and_lifted_nut_overlap_with_arm_mm3': nut_roll,
        'right_driver_seated_envelope': driver,
    }


def strength_screen(station):
    force = 5.
    span = 23.5 - station.y
    width = 2*station.tab_half_width
    thickness = 5.8
    return {'single_stay_downward_load_N': force, 'horizontal_arm_span_mm': span,
            'rectangular_arm_width_mm': width, 'rectangular_arm_height_mm': thickness,
            'horizontal_arm_nominal_bending_MPa': 6*force*span/(width*thickness**2),
            'scope': 'Elastic rectangular arm section only. Root and stay joint, material anisotropy, local '
                     'notches, clamp preload and cyclic strength require separate verification.'}


def check(source, candidate=None):
    if candidate is not None and source.resolve() == candidate.resolve():
        raise ValueError('Choose a separate file for the trial assembly')
    doc = App.openDocument(str(source.resolve()))
    try:
        frame_object = doc.Part019
        original_frame = detached_shape(frame_object)
        frame = original_frame
        parent = frame_object.getParentGeoFeatureGroup()
        actors = {name: (collision(geometry(obj)), getattr(obj, 'Motion', 'head'))
                  for name in (*PITCH_OBSTACLES, *HEAD_OBSTACLES, *JAW_OBSTACLES)
                  if (obj := doc.getObject(name)) is not None}
        layout = {'jaw_pivot_mm': list(doc.JawMotion.Placement.Base),
                  'motion_geometry': json.loads(doc.R5.MotionGeometry)}
        stats, joints = {}, {}
        for station in STATIONS:
            arm, extension = frame_arm(station), stay_extension(station)
            frame_overlap = original_frame.common(arm).Volume
            frame = check_solid(frame.fuse(arm), 'relocated jaw frame')
            stay = doc.getObject(station.stay)
            original = solid(geometry(stay))
            added = solid(mesh(extension))
            updated = mesh_from_solid(original+added)
            if not updated.is_volume or updated.body_count != 1:
                raise ValueError(f'{station.stay} must be one closed solid')
            replace_mesh(stay, updated)
            items = hardware(station)
            add_hardware(doc, parent, station, items)
            side = station.side.lower()
            stats[side] = {
                'loose_nut_seat_mm': [station.x, station.y, station.nut_z],
                'frame_arm_root_overlap_mm3': frame_overlap,
                'added_stay_root_overlap_mm3': (original ^ added).volume(),
                'stay_closed_bodies': updated.body_count,
                'stock_bolt_projection_past_nut_mm': items['Screw'].BoundBox.ZMax - station.nut_z - NUT_HEIGHT,
                'strength_screen': strength_screen(station),
            }
            if station.side == 'Left':
                head = hexagon(5.5, 2., (station.x, station.y, station.shoe_bottom), Z)
                stats[side]['hex_head_pocket'] = {
                    'nominal_overlap_mm3': extension.common(head).Volume,
                    'overlap_mm3_after_15_deg': extension.common(head.rotated(
                        App.Vector(station.x, station.y, station.shoe_bottom), App.Vector(*Z), 15.)).Volume,
                }
            joints[side] = (station, arm.cut(original_frame), extension, items)
        replace(frame_object, frame.copy())
        for side, (station, branch, extension, items) in joints.items():
            stats[side]['checks'] = stage_clearance(station, branch, extension, items, frame, actors, layout)
        if candidate is not None:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            doc.recompute()
            doc.saveAs(str(candidate.resolve()))
        return {'status': 'blocked', 'source_cad_sha256': digest(source),
                'candidate_cad_sha256': digest(candidate) if candidate else None,
                'frame_valid_native_solid': frame.isValid() and len(frame.Solids) == 1,
                'wrench_width_and_thickness_mm': [16., WRENCH_THICKNESS[3]],
                'target_continuous_tool_reserve_mm': CLEARANCE, 'stations': stats}
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--cad', type=Path)
    args = parser.parse_args()
    outputs = [args.report.resolve()] + ([args.cad.resolve()] if args.cad else [])
    if args.source.resolve() in outputs or len(set(outputs)) != len(outputs):
        parser.error('Choose separate source, report and trial assembly paths')
    report = check(args.source, args.cad)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    raise SystemExit(2 if report['status'] == 'blocked' else 0)
