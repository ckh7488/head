"""Add and measure a passive opening stop on the right jaw bearing stay."""

from argparse import ArgumentParser
from dataclasses import dataclass
from hashlib import sha256
from itertools import product
import json
from math import cos, degrees, floor, radians, sin, sqrt
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import FreeCAD as App
import Mesh
import Part
import fcl
import numpy as np
import trimesh as tr
from trimesh.collision import mesh_to_BVH

from build_b21_fasteners import B20_CAD

sys.path.insert(0, str(Path(__file__).resolve().parent / 'physics'))
from check_head import ANGLES, AXES_BY_MOTION, pose
from export_cad import tessellate, world_mesh, world_shape


STAY = 'Jaw_37_right_jaw_bearing_stay'
PIVOT_ARM = 'Jaw_39_right_jaw_pivot_arm'
JAW_PARTS = ('Jaw_30_moving_jaw', PIVOT_ARM, 'Jaw_38_left_jaw_drive_arm',
             'Jaw_Pin_jaw_4x10', 'JawHornScrew0', 'JawHornScrew1')
BENCH = ('Jaw_36_left_jaw_servo_stay', 'Jaw_XL330_M288_Jaw')
NEIGHBORS = ('Jaw_MR104ZZ_jaw_right', *BENCH, 'Part011', 'Part015', 'Part016',
             'Part018', 'Part019', 'Part024', 'Part025', 'Part027', 'Part041', 'Part042',
             'Part044', 'Part057', 'Part060', 'Part063', 'Part066', 'Part073',
             'Part074', 'Part076', 'Part077', 'Part079')
SOFTWARE_OPEN_DEG = 8.0
CLEAR_TRAVEL_DEG = 8.75
FACE_TOLERANCE_MM = .20
FACE_SLOPE = .15
FACE_FRONT_Y = -10.427
STEM_DEPTH_MM = 10.8
STEM_TOP_Z = 86.8
TOE_LEADING_Z = 72.
TOE_TOP_Z = 75.3
COMPOUND_CLEAR_DEG = 8.60


@dataclass(frozen=True)
class JawStop:
    command_deg: float = SOFTWARE_OPEN_DEG
    clear_deg: float = CLEAR_TRAVEL_DEG
    compound_clear_deg: float = COMPOUND_CLEAR_DEG
    nominal_range_deg: tuple[float, float] = (9.3, 9.5)
    pitch_range_deg: tuple[float, float] = (-15., 6.)
    face_y: float = FACE_FRONT_Y
    stem_depth_mm: float = STEM_DEPTH_MM
    stem_end_x: float = 44.1
    rib_front_y: float = -10.7
    rib_depth_mm: float = 2.5
    impact_limit_deg: float | None = None
    initial_speed_deg_s: float = 0.
    bearing_entry_diameter_mm: float | None = None
    feedback_tolerance_ticks: int = 8


B21_STOP = JawStop()
B22_STOP = JawStop(command_deg=5.5, clear_deg=6.60, compound_clear_deg=6.60,
                   nominal_range_deg=(7.35, 7.70), pitch_range_deg=(-16.7, 7.1),
                   face_y=-11.095, stem_depth_mm=13.8, stem_end_x=44.40,
                   rib_front_y=-11.3, rib_depth_mm=3.1, impact_limit_deg=9.0,
                   initial_speed_deg_s=95.*.229*6., bearing_entry_diameter_mm=10.20,
                   feedback_tolerance_ticks=11)


def cad_mesh(obj):
    mesh = world_mesh(obj) if obj.isDerivedFrom('Mesh::Feature') else tessellate(world_shape(obj))
    return mesh_from_topology(mesh)


def mesh_from_topology(mesh):
    points, faces = mesh.Topology
    return tr.Trimesh(np.asarray([tuple(p) for p in points]), np.asarray(faces))


def stop_geometry(old, spec=B21_STOP):
    v = App.Vector
    x0 = old.bounds[0, 0]
    y1, z0, z1 = -4.5, TOE_LEADING_Z, STEM_TOP_Z
    y0 = y1-spec.stem_depth_mm
    stem = Part.makeBox(44.1-x0, y1-y0, z1-z0, v(x0, y0, z0))
    front = spec.face_y
    height = TOE_TOP_Z-TOE_LEADING_Z
    back = -8.2
    profile = [v(41.8, y, z) for y, z in ((front, z0), (back, z0), (back, z0+height),
                                         (front-FACE_SLOPE*height, z0+height))]
    toe = Part.Face(Part.makePolygon([*profile, profile[0]])).extrude(v(6.2, 0, 0))
    rib_profile = [v(x, spec.rib_front_y, z) for x, z in
                   ((41.8, 74.95), (48., 74.95), (48., 79.9), (47.4, 80.5), (41.8, 80.5))]
    rib = Part.Face(Part.makePolygon([*rib_profile, rib_profile[0]])).extrude(v(0., spec.rib_depth_mm, 0.))
    pieces = [toe, rib]
    if spec.stem_end_x > 44.1:
        pieces.append(Part.makeBox(spec.stem_end_x-44.06, spec.stem_depth_mm-.10,
                                   z1-z0, v(44.06, y0+.05, z0)))
    return stem.fuse(pieces).removeSplitter()


def collision_object(mesh):
    return fcl.CollisionObject(mesh_to_BVH(mesh))


def move(obj, matrix):
    obj.setTransform(fcl.Transform(matrix[:3, :3].copy(), matrix[:3, 3].copy()))


def jaw_transform(angle, pivot):
    return tr.transformations.rotation_matrix(radians(angle), (1., 0., 0.), pivot)


def contact_angles(extra, jaws, pivot, shifts, clear_angle):
    objects = {name: collision_object(mesh) for name, mesh in jaws.items()}
    radii = {name: np.linalg.norm(mesh.vertices[:, 1:]-pivot[1:], axis=1).max()
             for name, mesh in jaws.items()}
    samples = np.linspace(0., clear_angle, 181)
    half_step_rad = radians(float(samples[1]-samples[0])*.5)
    request = fcl.CollisionRequest()
    results = []
    for shift in shifts:
        fixed = collision_object(extra.copy().apply_translation(shift))

        def angle_hit(angle):
            matrix = jaw_transform(angle, pivot)
            for name, obj in objects.items():
                move(obj, matrix)
                if fcl.collide(fixed, obj, request, fcl.CollisionResult()):
                    return name
            return None

        closest = float('inf')
        between = float('inf')
        for angle in samples:
            matrix = jaw_transform(angle, pivot)
            for name, obj in objects.items():
                move(obj, matrix)
                if fcl.collide(fixed, obj, request, fcl.CollisionResult()):
                    raise ValueError(f'Stop touches {name} within the required travel at {angle:.2f}° and shift {shift} mm')
                distance = fcl.distance(fixed, obj, fcl.DistanceRequest(), fcl.DistanceResult())
                closest = min(closest, distance)
                between = min(between, distance - radii[name]*half_step_rad)
        if between <= 0.:
            raise ValueError(f'Cannot establish stop clearance between samples with shift {shift} mm')

        low = clear_angle
        for high in np.linspace(clear_angle, 10.25, 85)[1:]:
            if angle_hit(high):
                break
            low = high
        else:
            raise ValueError(f'Stop does not engage before 10.25° with shift {shift} mm')
        for _ in range(14):
            center = (low+high)/2.
            if angle_hit(center):
                high = center
            else:
                low = center
        name = angle_hit(high+.02)
        if name != PIVOT_ARM:
            raise ValueError('Stop must meet only the right pivot arm at the opening limit')
        arm = objects[PIVOT_ARM]
        move(arm, jaw_transform(low, pivot))
        distance = fcl.DistanceResult()
        fcl.distance(fixed, arm, fcl.DistanceRequest(enable_nearest_points=True), distance)
        witness = np.asarray(distance.nearest_points[0])
        toe_z = witness[2]-shift[2]
        if not np.isfinite(witness).all() or min(toe_z - TOE_LEADING_Z, TOE_TOP_Z-toe_z) < -.01:
            raise ValueError('The stop does not touch the intended toe face')
        results.append({'face_shift_mm': shift[1], 'rigid_translation_mm': list(shift), 'first_contact_deg': high,
                        'minimum_sampled_clearance_through_verified_travel_mm': closest,
                        'continuous_lower_bound_through_verified_travel_mm': between,
                        'contact_part': name, 'contact_point_mm': witness.tolist()})
    return results


def verify_neighbors(extra, other, layout, pitch_range=(-15., 6.)):
    fixed = collision_object(extra)
    count = 0
    clearances = {}
    for name, mesh, kind in other:
        moving = collision_object(mesh)
        axes = AXES_BY_MOTION.get(kind, ())
        dense = name in ('Part011', 'Part018')
        if dense:
            low, high = pitch_range
            pitches = np.linspace(low, high, int(np.ceil((high-low)/.25))+1)
            samples = (pitches,)
        else:
            samples = tuple(ANGLES[index] for index in axes)
        closest = float('inf')
        for values in product(*samples):
            angles = np.zeros(len(ANGLES))
            angles[list(axes)] = values
            move(moving, pose(kind, angles, layout))
            count += 1
            if fcl.collide(fixed, moving, fcl.CollisionRequest(), fcl.CollisionResult()):
                raise ValueError(f'Jaw stop touches {name} at {angles.tolist()}')
            if dense:
                distance = fcl.distance(fixed, moving, fcl.DistanceRequest(), fcl.DistanceResult())
                closest = min(closest, distance)
        if dense:
            radius = np.linalg.norm(mesh.vertices[:, 1:]-(0., 112.), axis=1).max()
            step = float(pitches[1]-pitches[0])
            lower_bound = max(0., closest-radius*radians(step/2.))
            if lower_bound <= 0.:
                raise ValueError(f'Cannot establish clearance to {name} between neck pitch samples')
            clearances[name] = {'sample_step_deg': step, 'sampled_minimum_mm': closest,
                                'continuous_lower_bound_mm': lower_bound}
    return count, clearances


def verify_bench(extra, bench):
    fixed = {name: collision_object(mesh) for name, mesh in bench.items()}
    offset = np.array((0., 12., 12.))
    moving = collision_object(extra)
    for shift in np.linspace(offset, np.zeros(3), 69):
        moving.setTransform(fcl.Transform(shift))
        for name, obj in fixed.items():
            if fcl.collide(moving, obj, fcl.CollisionRequest(), fcl.CollisionResult()):
                raise ValueError(f'Jaw stop cannot approach from the rear and above because of {name}')
    return offset.tolist()


def gravity_loading(trials, dynamics, pivot, spec=B21_STOP):
    body = dynamics['mass_properties']['jaw']
    mass = body['mass_kg']
    y, z = (np.asarray(body['com_mm'])-pivot)[1:]*.001
    angle = radians(max(trial['first_contact_deg'] for trial in trials))
    pitches = np.linspace(*map(radians, spec.pitch_range_deg), 97)
    energy = max(0., max(mass*9.81*(y*(sin(p)-sin(p+angle)) + z*(cos(p)-cos(p+angle)))
                         for p in pitches))
    normal = np.array((0., 1., FACE_SLOPE))/sqrt(1.+FACE_SLOPE**2)
    levers = [abs(np.cross(np.asarray(trial['contact_point_mm'])-pivot, normal)[0]) for trial in trials]
    lever = min(levers)
    gravity_torque = max(mass*9.81*abs(y*cos(p+angle)-z*sin(p+angle))
                         for p in pitches)
    result = {'jaw_mass_kg': mass, 'gravity_energy_from_closed_no_friction_J': energy,
              'minimum_contact_lever_mm': lever, 'gravity_tangential_force_N': gravity_torque*1000./lever,
              'latest_static_contact_deg': degrees(angle)}
    if spec.initial_speed_deg_s > 0.:
        pivot_inertia = body['inertia_kg_m2'][0][0] + mass*(y*y + z*z)
        result.update(initial_speed_deg_s=spec.initial_speed_deg_s, jaw_pivot_inertia_kg_m2=pivot_inertia,
                      initial_kinetic_energy_J=.5*pivot_inertia*radians(spec.initial_speed_deg_s)**2)
    return result


def deflected_contact(extra, arm_mesh, pivot, trials, displacement_mm):
    normal = np.array((0., 1., FACE_SLOPE))/sqrt(1.+FACE_SLOPE**2)
    stop, arm = collision_object(extra), collision_object(arm_mesh)
    request = fcl.CollisionRequest()

    def touches(angle):
        move(arm, jaw_transform(angle, pivot))
        return bool(fcl.collide(stop, arm, request, fcl.CollisionResult()))

    witnesses = []
    for trial in trials:
        shift = np.array(trial['rigid_translation_mm'])
        stop.setTranslation(shift + displacement_mm*normal)
        lower, upper = trial['first_contact_deg']-.001, 10.25
        if not touches(upper):
            raise ValueError('The deflected jaw stop does not catch the pivot arm')
        for _ in range(15):
            middle = (lower+upper)/2.
            if touches(middle):
                upper = middle
            else:
                lower = middle
        witnesses.append({'first_contact_deg': upper, 'rigid_translation_mm': shift.tolist()})
    return max(witnesses, key=lambda row: row['first_contact_deg'])


def bearing_entry(stay, stop, bearing, pivot, diameter):
    left, right = bearing.bounds[:, 0]
    start, end = right+.02, stay.bounds[1, 0]+1.
    section = tr.transformations.rotation_matrix(radians(90.), (0., 1., 0.))

    def tube(low, high, radius):
        mesh = tr.creation.cylinder(radius, height=high-low, sections=192)
        return mesh.apply_transform(section).apply_translation(((low+high)/2., *pivot[1:]))

    cut = tube(start, end, diameter/2.)
    if tr.boolean.intersection((stop, cut), engine='manifold').volume > 1.e-4:
        raise ValueError('The jaw bearing opening removes part of the stop')
    relieved = tr.boolean.difference((stay, cut), engine='manifold')
    if not relieved.is_volume or relieved.body_count != 1 or not relieved.nondegenerate_faces().all():
        raise ValueError('The jaw bearing entry must leave one closed stay')
    sweep = tube(left+.004, end, 5.02)
    obstruction = tr.boolean.intersection((relieved, sweep), engine='manifold').volume
    if obstruction > 1.e-4:
        raise ValueError('The Ø10.04 mm jaw bearing sweep is obstructed')
    shoulder = tube(left-.50, left-.01, diameter/2.)
    support = [tr.boolean.intersection((part, shoulder), engine='manifold').volume
               for part in (stay, relieved)]
    if abs(support[0]-support[1]) > 1.e-4 or support[1] <= 0.:
        raise ValueError('The jaw bearing opening changes the original rear shoulder')
    return relieved, {'diameter_mm': diameter, 'center_yz_mm': pivot[1:].tolist(),
                      'entry_axis': [1., 0., 0.], 'cut_depth_x_mm': [start, end],
                      'removed_volume_mm3': stay.volume-relieved.volume, 'sweep_diameter_mm': 10.04,
                      'sweep_obstruction_mm3': obstruction, 'retained_shoulder_volume_mm3': support[1]}


def elastic_stop(solid, trials, gravity, spec=B21_STOP):
    from scipy.sparse.linalg import splu
    from skfem import Basis, ElementTetP1, ElementVector, asm, condense
    from skfem.models.elasticity import lame_parameters, linear_elasticity

    from cable_fea import mesh_step, traction

    normal = np.array((0., 1., FACE_SLOPE))/sqrt(1.+FACE_SLOPE**2)
    local_contacts = np.array([np.asarray(trial['contact_point_mm'])-trial['rigid_translation_mm']
                               for trial in trials])
    revised = spec.impact_limit_deg is not None
    if revised:
        smallest, largest = local_contacts.min(axis=0), local_contacts.max(axis=0)
        patches = [(x, z) for x, z in product((smallest[0], largest[0]), (smallest[2], largest[2]))]
        sizes = (.68, .50, .38)
    else:
        contact_x, _, contact_z = max(local_contacts, key=lambda point: point[0])
        patches = [(contact_x, contact_z)]
        sizes = (.7, .5, .4)
    rows = []
    with TemporaryDirectory(prefix='r5-jaw-stop-') as folder:
        model = Path(folder) / 'stop.step'
        solid.exportStep(str(model))
        for size in sizes:
            mesh = mesh_step(model, size)
            boundary = mesh.boundary_facets()
            x, y, z = mesh.p[:, mesh.facets[:, boundary]]
            clamp = boundary[np.all(np.isclose(z, STEM_TOP_Z), axis=0)]
            on_face = np.all(np.isclose(y, spec.face_y-FACE_SLOPE*(z-TOE_LEADING_Z), atol=1e-5), axis=0)
            if len(clamp) < 3:
                raise RuntimeError(f'Cannot resolve the stem clamp with mesh step {size:g} mm')
            element = ElementVector(ElementTetP1())
            basis = Basis(mesh, element)
            lam, mu = lame_parameters(1000., .37)
            stiffness = asm(linear_elasticity(lam, mu), basis)
            reduced, _, free = condense(stiffness, D=basis.get_dofs(facets=clamp).all())
            solver = splu(reduced.tocsc())
            directions = basis.split_indices()
            patch_rows = []
            for contact_x, contact_z in patches:
                if revised:
                    near_z = abs(z.mean(axis=0)-contact_z) <= 1.15
                    near_x = abs(x.mean(axis=0)-contact_x) <= 1.05
                else:
                    near_z = (z.mean(axis=0) > contact_z-.15) & (z.mean(axis=0) < contact_z+1.3)
                    near_x = abs(x.mean(axis=0)-contact_x) < .85
                patch = boundary[on_face & near_z & near_x]
                if len(patch) < 3:
                    raise RuntimeError(f'Cannot resolve a stop load with mesh step {size:g} mm')
                rhs = traction(mesh, element, patch, normal)
                displacement = np.zeros(basis.N)
                displacement[free] = solver.solve(rhs[free])
                balance = stiffness@displacement
                if max(abs(balance[i].sum()) for i in directions) > 1e-6:
                    raise RuntimeError('Unbalanced elastic stop forces')
                contact_nodes = np.unique(mesh.facets[:, patch])
                delta = float((normal@np.array([displacement[i][contact_nodes] for i in directions])).max())
                patch_rows.append({'center_xz_mm': (contact_x, contact_z), 'facets': len(patch),
                                   'deflection_mm_per_N_at_1000_MPa': delta})
            worst = max(patch_rows, key=lambda row: row['deflection_mm_per_N_at_1000_MPa'])
            delta_per_newton = worst['deflection_mm_per_N_at_1000_MPa']
            cases = []
            for modulus in (500., 1000., 1800.):
                spring = modulus/(1000.*delta_per_newton)
                weight = gravity['gravity_tangential_force_N']
                energy_nmm = 1000.*(gravity['gravity_energy_from_closed_no_friction_J']
                                    + gravity.get('initial_kinetic_energy_J', 0.))
                delta = (weight+sqrt(weight*weight+2.*spring*energy_nmm))/spring
                added = degrees(delta/gravity['minimum_contact_lever_mm'])
                cases.append({'modulus_MPa': modulus, 'force_N': spring*delta, 'deflection_mm': delta,
                              'additional_opening_deg': added,
                              'opening_with_static_face_tolerance_and_impact_deg':
                                  gravity['latest_static_contact_deg']+added})
            row = {'mesh_mm': size, 'elements': int(mesh.nelements), 'contact_load_facets': worst['facets'],
                   'compliance_mm_per_N_at_1000_MPa': delta_per_newton, 'impact_cases': cases}
            if revised:
                row['load_patches'] = patch_rows
            rows.append(row)
    scope = 'Homogeneous elastic stop with a fixed upper stem. Gravity drop from closed, without friction, servo torque or hinge compliance.'
    if spec.initial_speed_deg_s > 0.:
        scope += ' The impact combines full closed-to-stop gravity energy and initial opening at the configured profile speed ceiling.'
    return {'scope': scope, 'meshes': rows}


def apply(doc, print_path, dynamics=None, fea=False, spec=B21_STOP):
    target = doc.getObject(STAY)
    old = cad_mesh(target)
    solid = stop_geometry(old, spec)
    if len(solid.Solids) != 1 or not solid.isValid():
        raise ValueError('The added jaw stop must form a single solid')
    extra = mesh_from_topology(tessellate(solid))
    fitted = tr.boolean.union([old, extra], engine='manifold')
    if not fitted.is_volume or fitted.body_count != 1:
        raise ValueError('The bearing stay and stop must be one closed positive solid')
    pivot = np.asarray(tuple(doc.JawMotion.Placement.Base))
    entry = None
    if spec.bearing_entry_diameter_mm is not None:
        bearing = cad_mesh(doc.getObject('Jaw_MR104ZZ_jaw_right'))
        fitted, entry = bearing_entry(fitted, extra, bearing, pivot, spec.bearing_entry_diameter_mm)
    jaws = {name: cad_mesh(doc.getObject(name)) for name in JAW_PARTS}
    shifts = (-FACE_TOLERANCE_MM, 0., FACE_TOLERANCE_MM)
    trials = contact_angles(extra, jaws, pivot, [(0., y, 0.) for y in shifts], spec.clear_deg)
    compound_trials = contact_angles(extra, jaws, pivot, product(shifts, repeat=3), spec.compound_clear_deg)
    nominal = trials[1]
    if not spec.nominal_range_deg[0] <= nominal['first_contact_deg'] <= spec.nominal_range_deg[1]:
        raise ValueError(f'Nominal jaw stop angle is {nominal["first_contact_deg"]:.3f}°')
    motion = json.loads(doc.R5.MotionGeometry)
    layout = {'motion_geometry': motion, 'jaw_pivot_mm': pivot.tolist()}
    neighbors = [(name, cad_mesh(doc.getObject(name)), doc.getObject(name).Motion) for name in NEIGHBORS]
    comparisons, neck_gaps = verify_neighbors(extra, neighbors, layout, spec.pitch_range_deg)
    rotating_neck = [row for row in neighbors if row[0] in ('Part011', 'Part018')]
    shifted_neck_gaps = {}
    for shift in product((-FACE_TOLERANCE_MM, FACE_TOLERANCE_MM), repeat=3):
        shifted = extra.copy().apply_translation(shift)
        _, clearance = verify_neighbors(shifted, rotating_neck, layout, spec.pitch_range_deg)
        shifted_neck_gaps[str(shift)] = clearance
    bench = {name: mesh for name, mesh in jaws.items() if name != 'Jaw_Pin_jaw_4x10'}
    bench.update({name: cad_mesh(doc.getObject(name)) for name in BENCH})
    offset = verify_bench(extra, bench)
    motion['jaw_stop'] = {'modified_part': STAY, 'software_open_deg': spec.command_deg,
                          'verified_clear_deg': spec.clear_deg, 'nominal_contact_deg': nominal['first_contact_deg'],
                          'compound_clear_travel_deg': spec.compound_clear_deg,
                          'bench_approach_offset_mm': offset}
    if spec.impact_limit_deg is not None:
        motion['jaw_stop']['released_clearance_deg'] = spec.impact_limit_deg
        tick_degrees = 360. / 4096
        max_feedback = (floor(spec.command_deg/tick_degrees)+spec.feedback_tolerance_ticks)*tick_degrees
        if max_feedback > spec.compound_clear_deg:
            raise ValueError('The jaw feedback tolerance exceeds its checked clear travel')
        motion['jaw_stop']['max_powered_feedback_deg'] = max_feedback
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)

    orientation = tr.transformations.rotation_matrix(-np.pi/2., (0., 1., 0.))
    old_print_bounds = old.copy().apply_transform(orientation).bounds
    printed = fitted.copy().apply_transform(orientation)
    printed.apply_translation(-np.r_[old_print_bounds.mean(axis=0)[:2], old_print_bounds[0, 2]])
    print_path.parent.mkdir(parents=True, exist_ok=True)
    printed.export(print_path)

    mesh = Mesh.Mesh([[tuple(p) for p in tri] for tri in fitted.triangles])
    parent = target.getParentGeoFeatureGroup()
    target.Mesh = mesh
    target.Placement = parent.getGlobalPlacement().inverse() if parent else App.Placement()
    if not np.allclose(cad_mesh(target).bounds, fitted.bounds, atol=1e-5):
        raise ValueError('Jaw stop changed world coordinates when inserted into the FreeCAD assembly')
    report = {**motion['jaw_stop'], 'contact_trials': trials, 'compound_contact_trials': compound_trials,
              'neighbor_pose_comparisons': comparisons,
              'neck_pitch_gaps': neck_gaps, 'neck_pitch_gaps_by_stop_shift_mm': shifted_neck_gaps,
              'print_sha256': sha256(print_path.read_bytes()).hexdigest(), 'added_volume_mm3': fitted.volume-old.volume}
    if entry is not None:
        report['bearing_entry'] = entry
    if spec == B22_STOP:
        report['reference_powered_model'] = {
            'source_cad_sha256': '9ed25081889f5846ff2d7c70c99e39580195da25de1857a4c046a16143fdfe02',
            'command_deg': 6., 'mujoco_peak_deg': 6.572205720574027,
            'external_closing_disturbances_N': [0., .25, .5, 1.],
        }
    if dynamics:
        report['gravity_drop'] = gravity_loading(compound_trials, dynamics, pivot, spec)
    if fea:
        if not dynamics:
            raise ValueError('Provide jaw mass properties for the stop FE impact estimate')
        report['local_FE'] = elastic_stop(solid, compound_trials, report['gravity_drop'], spec)
        if spec.impact_limit_deg is not None:
            for row in report['local_FE']['meshes']:
                for case in row['impact_cases']:
                    result = deflected_contact(extra, jaws[PIVOT_ARM], pivot, compound_trials, case['deflection_mm'])
                    previous = case['opening_with_static_face_tolerance_and_impact_deg']
                    case['independent_minimum_lever_upper_deg'] = previous
                    case['deflected_contact'] = result
                    case['opening_with_static_face_tolerance_and_impact_deg'] = result['first_contact_deg']
            report['local_FE']['scope'] += (' The largest calculated normal displacement is applied as a rigid retreat '
                                            'of the stop for each tolerance case, and the exact pivot-arm contact is measured again.')
            upper = max(case['opening_with_static_face_tolerance_and_impact_deg']
                        for row in report['local_FE']['meshes'] for case in row['impact_cases'])
            if upper > spec.impact_limit_deg:
                raise ValueError(f'Jaw impact reached {upper:.3f}°, above the checked harness angle')
            report['modeled_impact_max_deg'] = upper
    return report


def build(source, output, print_path, report, dynamics=None, fea=False, spec=B21_STOP):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate CAD output')
    doc = App.openDocument(str(source.resolve()))
    try:
        loads = json.loads(dynamics.read_text()) if dynamics else None
        result = apply(doc, print_path, loads, fea, spec)
        doc.recompute()
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(output.resolve()))
        result['source_sha256'] = sha256(source.read_bytes()).hexdigest()
        result['cad_sha256'] = sha256(output.read_bytes()).hexdigest()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=B20_CAD)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--print', type=Path, dest='print_path', required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--dynamics', type=Path)
    parser.add_argument('--fea', action='store_true')
    build(**vars(parser.parse_args()))
