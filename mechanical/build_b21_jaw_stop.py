"""Add and measure a passive opening stop on the right jaw bearing stay."""

from argparse import ArgumentParser
from hashlib import sha256
from itertools import product
import json
from math import cos, degrees, radians, sin, sqrt
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


def cad_mesh(obj):
    mesh = world_mesh(obj) if obj.isDerivedFrom('Mesh::Feature') else tessellate(world_shape(obj))
    return mesh_from_topology(mesh)


def mesh_from_topology(mesh):
    points, faces = mesh.Topology
    return tr.Trimesh(np.asarray([tuple(p) for p in points]), np.asarray(faces))


def stop_geometry(old):
    v = App.Vector
    x0 = old.bounds[0, 0]
    y1, z0, z1 = -4.5, TOE_LEADING_Z, STEM_TOP_Z
    y0 = y1-STEM_DEPTH_MM
    stem = Part.makeBox(44.1-x0, y1-y0, z1-z0, v(x0, y0, z0))
    front = FACE_FRONT_Y
    height = TOE_TOP_Z-TOE_LEADING_Z
    back = -8.2
    profile = [v(41.8, y, z) for y, z in ((front, z0), (back, z0), (back, z0+height),
                                         (front-FACE_SLOPE*height, z0+height))]
    toe = Part.Face(Part.makePolygon([*profile, profile[0]])).extrude(v(6.2, 0, 0))
    rib_profile = [v(x, -10.7, z) for x, z in
                   ((41.8, 74.95), (48., 74.95), (48., 79.9), (47.4, 80.5), (41.8, 80.5))]
    rib = Part.Face(Part.makePolygon([*rib_profile, rib_profile[0]])).extrude(v(0., 2.5, 0.))
    return stem.fuse([toe, rib]).removeSplitter()


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


def verify_neighbors(extra, other, layout):
    fixed = collision_object(extra)
    count = 0
    clearances = {}
    for name, mesh, kind in other:
        moving = collision_object(mesh)
        axes = AXES_BY_MOTION.get(kind, ())
        dense = name in ('Part011', 'Part018')
        samples = (np.arange(-15., 6.01, .25),) if dense else tuple(ANGLES[index] for index in axes)
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
            lower_bound = max(0., closest-radius*radians(.125))
            if lower_bound <= 0.:
                raise ValueError(f'Cannot establish clearance to {name} between neck pitch samples')
            clearances[name] = {'sample_step_deg': .25, 'sampled_minimum_mm': closest,
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


def gravity_loading(trials, dynamics, pivot):
    body = dynamics['mass_properties']['jaw']
    mass = body['mass_kg']
    y, z = (np.asarray(body['com_mm'])-pivot)[1:]*.001
    angle = radians(max(trial['first_contact_deg'] for trial in trials))
    energy = max(0., max(mass*9.81*(y*(sin(p)-sin(p+angle)) + z*(cos(p)-cos(p+angle)))
                         for p in np.linspace(radians(-15), radians(6), 43)))
    normal = np.array((0., 1., FACE_SLOPE))/sqrt(1.+FACE_SLOPE**2)
    levers = [abs(np.cross(np.asarray(trial['contact_point_mm'])-pivot, normal)[0]) for trial in trials]
    lever = min(levers)
    gravity_torque = max(mass*9.81*abs(y*cos(p+angle)-z*sin(p+angle))
                         for p in np.linspace(radians(-15), radians(6), 43))
    return {'jaw_mass_kg': mass, 'gravity_energy_from_closed_no_friction_J': energy,
            'minimum_contact_lever_mm': lever, 'gravity_tangential_force_N': gravity_torque*1000./lever,
            'latest_static_contact_deg': degrees(angle)}


def elastic_stop(solid, trials, gravity):
    from scipy.sparse.linalg import splu
    from skfem import Basis, ElementTetP1, ElementVector, asm, condense
    from skfem.models.elasticity import lame_parameters, linear_elasticity

    from cable_fea import mesh_step, traction

    normal = np.array((0., 1., FACE_SLOPE))/sqrt(1.+FACE_SLOPE**2)
    local_contacts = [np.asarray(trial['contact_point_mm'])-trial['rigid_translation_mm'] for trial in trials]
    contact_x, _, contact_z = max(local_contacts, key=lambda point: point[0])
    rows = []
    with TemporaryDirectory(prefix='r5-jaw-stop-') as folder:
        model = Path(folder) / 'stop.step'
        solid.exportStep(str(model))
        for size in (.7, .5, .4):
            mesh = mesh_step(model, size)
            boundary = mesh.boundary_facets()
            x, y, z = mesh.p[:, mesh.facets[:, boundary]]
            clamp = boundary[np.all(np.isclose(z, STEM_TOP_Z), axis=0)]
            on_face = np.all(np.isclose(y, FACE_FRONT_Y-FACE_SLOPE*(z-TOE_LEADING_Z), atol=1e-5), axis=0)
            patch = boundary[on_face & (abs(x.mean(axis=0)-contact_x) < .85)
                             & (z.mean(axis=0) > contact_z-.15) & (z.mean(axis=0) < contact_z+1.3)]
            if len(clamp) < 3 or len(patch) < 3:
                raise RuntimeError(f'Cannot resolve a stop load or clamp surface with mesh step {size:g} mm')
            element = ElementVector(ElementTetP1())
            basis = Basis(mesh, element)
            lam, mu = lame_parameters(1000., .37)
            stiffness = asm(linear_elasticity(lam, mu), basis)
            reduced, _, free = condense(stiffness, D=basis.get_dofs(facets=clamp).all())
            rhs = traction(mesh, element, patch, normal)
            u = np.zeros(basis.N)
            u[free] = splu(reduced.tocsc()).solve(rhs[free])
            directions = basis.split_indices()
            balance = stiffness@u
            if max(abs(balance[i].sum()) for i in directions) > 1e-6:
                raise RuntimeError('Unbalanced elastic stop forces')
            contact_nodes = np.unique(mesh.facets[:, patch])
            delta_per_newton = float((normal@np.array([u[i][contact_nodes] for i in directions])).max())
            cases = []
            for modulus in (500., 1000., 1800.):
                spring = modulus/(1000.*delta_per_newton)
                weight = gravity['gravity_tangential_force_N']
                energy_nmm = gravity['gravity_energy_from_closed_no_friction_J']*1000.
                delta = (weight+sqrt(weight*weight+2.*spring*energy_nmm))/spring
                added = degrees(delta/gravity['minimum_contact_lever_mm'])
                cases.append({'modulus_MPa': modulus, 'force_N': spring*delta, 'deflection_mm': delta,
                              'additional_opening_deg': added,
                              'opening_with_static_face_tolerance_and_impact_deg':
                                  gravity['latest_static_contact_deg']+added})
            rows.append({'mesh_mm': size, 'elements': int(mesh.nelements), 'contact_load_facets': len(patch),
                         'compliance_mm_per_N_at_1000_MPa': delta_per_newton, 'impact_cases': cases})
    return {'scope': 'Homogeneous elastic stop with a fixed upper stem. Gravity drop from closed, no friction, no servo torque or hinge compliance.',
            'meshes': rows}


def apply(doc, print_path, dynamics=None, fea=False):
    target = doc.getObject(STAY)
    old = cad_mesh(target)
    solid = stop_geometry(old)
    if len(solid.Solids) != 1 or not solid.isValid():
        raise ValueError('The added jaw stop must form a single solid')
    extra = mesh_from_topology(tessellate(solid))
    fitted = tr.boolean.union([old, extra], engine='manifold')
    if not fitted.is_volume or fitted.body_count != 1:
        raise ValueError('The bearing stay and stop must be one closed positive solid')
    pivot = np.asarray(tuple(doc.JawMotion.Placement.Base))
    jaws = {name: cad_mesh(doc.getObject(name)) for name in JAW_PARTS}
    shifts = (-FACE_TOLERANCE_MM, 0., FACE_TOLERANCE_MM)
    trials = contact_angles(extra, jaws, pivot, [(0., y, 0.) for y in shifts], CLEAR_TRAVEL_DEG)
    compound_trials = contact_angles(extra, jaws, pivot, product(shifts, repeat=3), COMPOUND_CLEAR_DEG)
    nominal = trials[1]
    if not 9.3 <= nominal['first_contact_deg'] <= 9.5:
        raise ValueError(f'Nominal jaw stop angle is {nominal["first_contact_deg"]:.3f}°')
    motion = json.loads(doc.R5.MotionGeometry)
    layout = {'motion_geometry': motion, 'jaw_pivot_mm': pivot.tolist()}
    neighbors = [(name, cad_mesh(doc.getObject(name)), doc.getObject(name).Motion) for name in NEIGHBORS]
    comparisons, neck_gaps = verify_neighbors(extra, neighbors, layout)
    rotating_neck = [row for row in neighbors if row[0] in ('Part011', 'Part018')]
    shifted_neck_gaps = {}
    for shift in product((-FACE_TOLERANCE_MM, FACE_TOLERANCE_MM), repeat=3):
        shifted = extra.copy().apply_translation(shift)
        _, clearance = verify_neighbors(shifted, rotating_neck, layout)
        shifted_neck_gaps[str(shift)] = clearance
    bench = {name: mesh for name, mesh in jaws.items() if name != 'Jaw_Pin_jaw_4x10'}
    bench.update({name: cad_mesh(doc.getObject(name)) for name in BENCH})
    offset = verify_bench(extra, bench)
    motion['jaw_stop'] = {'modified_part': STAY, 'software_open_deg': SOFTWARE_OPEN_DEG,
                          'verified_clear_deg': CLEAR_TRAVEL_DEG, 'nominal_contact_deg': nominal['first_contact_deg'],
                          'compound_clear_travel_deg': COMPOUND_CLEAR_DEG,
                          'bench_approach_offset_mm': offset}
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
    if dynamics:
        report['gravity_drop'] = gravity_loading(compound_trials, dynamics, pivot)
    if fea:
        if not dynamics:
            raise ValueError('Provide jaw mass properties for the stop FE impact estimate')
        report['local_FE'] = elastic_stop(solid, compound_trials, report['gravity_drop'])
    return report


def build(source, output, print_path, report, dynamics=None, fea=False):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate CAD output')
    doc = App.openDocument(str(source.resolve()))
    try:
        loads = json.loads(dynamics.read_text()) if dynamics else None
        result = apply(doc, print_path, loads, fea)
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
