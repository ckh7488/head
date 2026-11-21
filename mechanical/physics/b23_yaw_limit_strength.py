"""Screen the positive yaw stop under power loss from the configured profile."""

from argparse import ArgumentParser
from hashlib import file_digest
from itertools import product
import json
from math import degrees, radians
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import FreeCAD as App
import mujoco as mj
import numpy as np
import trimesh
from scipy.optimize import minimize
from scipy.sparse.linalg import splu
from skfem import Basis, ElementTetP1, ElementVector, asm, condense
from skfem.models.elasticity import lame_parameters, linear_elasticity

from b20_dynamics import load_bodies, x_rotation
from b22_drive import FIRMWARE
from b22_pitch_stop_load import linear_impact
from cable_fea import mesh_step, traction
from check_b22_neck import encoder_feedback_limits
from export_cad import world_shape
from multibody import NECK_PIVOT, gimbal_model, pos

YAW_RELEASE_OTHER_AXES_DEG = ((-17.21, 7.13), (0., 9.8))
INITIAL_AXIS_SPEED_SCREENS_DEG_S = (45., 145.)
PETG_REFERENCE_MPA = 1000.
MINIMUM_PETG_MPA = 500.
KEYED_PADS = {'YawStopPadRight': (-1, 30., 25.), 'YawStopPadLeft': (1, 150., 155.)}


def digest(path):
    with path.open('rb') as file:
        return file_digest(file, 'sha256').hexdigest()


def energy_bound(cad, layout, weights):
    bodies, _, _ = load_bodies(layout, cad, weights)
    model = mj.MjModel.from_xml_string(gimbal_model(bodies, pos(layout['jaw_pivot_mm']),
                                                   np.ones(3), np.zeros(3), .0005))
    data = mj.MjData(model)
    inertia = np.zeros((3, 3))

    def states(pitch, jaw):
        for p, j in product(np.linspace(*pitch, 113), np.linspace(*jaw, 43)):
            data.qpos[:] = np.radians([0., p, j])
            mj.mj_forward(model, data)
            mj.mj_energyPos(model, data)
            mj.mj_fullM(model, inertia, data.qM)
            yield inertia.copy(), float(data.energy[0])

    pitch_feedback = encoder_feedback_limits()[0]
    yaw_register = int(re.search(r'\bexhibitYawVelocity\s*=\s*(\d+)', FIRMWARE.read_text())[1])
    initial_omega = np.radians([yaw_register*.229*6., *INITIAL_AXIS_SPEED_SCREENS_DEG_S])
    initial = list(states(pitch_feedback, YAW_RELEASE_OTHER_AXES_DEG[1]))
    released = list(states(*YAW_RELEASE_OTHER_AXES_DEG))
    # P_yaw is conserved before the stop applies a reaction. Discard drag and use
    # both signs of every inertial coupling, including the already free jaw.
    angular_momentum = max(abs(matrix[0]) @ initial_omega for matrix, _ in initial)
    kinetic = (max(.5*initial_omega @ abs(matrix) @ initial_omega + potential for matrix, potential in initial)
               - min(potential for _, potential in released))
    peak_omega, peak_energy, max_cross_momentum, min_yaw_inertia = 0., 0., 0., np.inf
    for matrix, _ in released:
        w = matrix[0, 1:]
        inertial_conditional = matrix[1:, 1:] - np.outer(w, w)/matrix[0, 0]
        cross_momentum = np.sqrt(2.*kinetic*(w @ np.linalg.solve(inertial_conditional, w)))
        omega = (angular_momentum + cross_momentum)/matrix[0, 0]
        inertia_effective = 1./np.linalg.inv(matrix)[0, 0]
        peak_omega = max(peak_omega, omega)
        peak_energy = max(peak_energy, .5*inertia_effective*omega**2)
        max_cross_momentum = max(max_cross_momentum, cross_momentum)
        min_yaw_inertia = min(min_yaw_inertia, matrix[0, 0])
    # During first compression the stop decreases signed yaw momentum p.
    # Since dq/dt <= (p+cross_momentum)/I_min, integrating -dq/dt dp bounds
    # its stored energy even while pitch and jaw exchange kinetic energy.
    compression_energy = (angular_momentum + max_cross_momentum)**2/(2.*min_yaw_inertia)
    return {'initial_speed_deg_s': np.degrees(initial_omega).tolist(),
            'released_pitch_and_jaw_pose_grid': len(released), 'yaw_L_kg_m2_s': angular_momentum,
            'total_kinetic_bound_J': kinetic, 'contact_speed_deg_s': degrees(peak_omega),
            'max_cross_axis_momentum_kg_m2_s': max_cross_momentum,
            'minimum_yaw_inertia_kg_m2': min_yaw_inertia,
            'incident_contact_energy_J': peak_energy,
            'first_compression_energy_before_grid_allowance_J': compression_energy,
            'incident_screen_J': 1.02 * compression_energy}


def xy_direction(angle):
    theta = radians(angle)
    return np.array([np.cos(theta), np.sin(theta), 0.])


def one_newton_yaw_torque(cad, layout):
    center = pos(layout['jaw_pivot_mm'])
    shell = np.concatenate([pos(trimesh.load_mesh(cad/'world'/f'{name}.stl').vertices)
                            for name in ('Part073', 'Part074')])
    jaw = pos(trimesh.load_mesh(cad/'world/Jaw_30_moving_jaw.stl').vertices)
    pitch_range, jaw_range = YAW_RELEASE_OTHER_AXES_DEG
    pitch_poses = np.linspace(*pitch_range, 62)
    jaw_poses = np.linspace(*jaw_range, 27)
    jaw_shifts = [(jaw-center) @ x_rotation(radians(j)).T + center - NECK_PIVOT for j in jaw_poses]
    shell -= NECK_PIVOT
    bound = 0.
    for angle in pitch_poses:
        rotation = x_rotation(radians(angle))[:2]
        bound = max(bound, np.linalg.norm(shell @ rotation.T, axis=1).max())
        for jaw_pose in jaw_shifts:
            bound = max(bound, np.linalg.norm(jaw_pose @ rotation.T, axis=1).max())
    pitch_lipschitz = max(np.linalg.norm(body[:, 1:], axis=1).max() for body in [shell, *jaw_shifts])
    jaw_lipschitz = np.linalg.norm((jaw-center)[:, 1:], axis=1).max()
    interpolation_allowance = .5*(radians(pitch_poses[1]-pitch_poses[0])*pitch_lipschitz
                                 + radians(jaw_poses[1]-jaw_poses[0])*jaw_lipschitz)
    return float(bound+interpolation_allowance)


def keyed_fit(geometry):
    side = geometry['pad_side_clearance_mm']
    # Support function of the convex hull of the two circles, then the same
    # hull enlarged by the pocket's exact uniform clearance.
    anchor = 63.*xy_direction(30.)[:2]
    key_end = 53.2*xy_direction(25.)[:2]
    angle = np.linspace(0., 2.*np.pi, 1441)
    normal = np.column_stack((np.cos(angle), np.sin(angle)))
    support = np.maximum(normal @ anchor + 4., normal @ key_end + 2.45) + side
    tangent_angle = 90. - 4. - geometry['nominal_stop_deg'][1] - 90.
    direction = xy_direction(tangent_angle)[:2]

    def turn(point, theta):
        c, s = np.cos(theta), np.sin(theta)
        return np.array([[c, -s], [s, c]]) @ (point-anchor) + anchor

    def containment(pose):
        translation, theta = pose[:2], pose[-1]
        moved = np.maximum(normal @ (anchor+translation) + 4.,
                           normal @ (turn(key_end, theta)+translation) + 2.45)
        # Ø3 shank in the Ø3.5 printed pad hole also constrains translation.
        return np.r_[support-moved, .25-np.linalg.norm(translation)]

    values = {}
    for radius, sign in product(geometry['contact_radius_mm'], (-1, 1)):
        point = radius*xy_direction(tangent_angle+90.)[:2]

        def delta(pose):
            return direction @ (turn(point, pose[-1])+pose[:2]-point)

        fit = minimize(lambda pose: -sign*delta(pose), np.zeros(3), method='SLSQP',
                       bounds=[(-.3, .3), (-.3, .3), (-.05, .05)],
                       constraints=[{'type': 'ineq', 'fun': containment}],
                       options={'ftol': 1e-10, 'maxiter': 150})
        if not fit.success or min(containment(fit.x)) < -1e-6:
            raise ValueError('Could not resolve nominal rigid pad play')
        values[f'{radius:g}_{sign:+d}'] = float(delta(fit.x))
    return {'nominal_dry_tangential_witness_mm': values,
            'absolute_witness_mm': max(abs(delta) for delta in values.values()),
            'sampled_support_directions': len(normal)}


def support_patch(name, corners, centers):
    if name == 'Part007':
        return np.all(np.isclose(corners[2], -37.9, atol=1e-4), axis=0) & (np.linalg.norm(centers[:2], axis=0) < 11.)
    if name in KEYED_PADS:
        sign, anchor_angle, toe_angle = KEYED_PADS[name]
        anchor = 63.*xy_direction(anchor_angle)
        key_end = 53.2*xy_direction(toe_angle)
        vector = key_end-anchor
        lateral = np.cross([0.,0.,1.], vector)/np.linalg.norm(vector)
        along = vector @ (centers-anchor[:, None])/np.dot(vector, vector)
        across = lateral @ (centers-anchor[:, None])
        direction = sign*np.cross([0.,0.,1.], xy_direction(90.+sign*63.6))
        relative_side = np.sign(direction @ lateral)*across
        keyed = (centers[2] < -37.08) & (np.ptp(corners[2], axis=0) > 1e-5)
        toe_face = keyed & (along > .65) & (relative_side > 1.)
        anchor_face = keyed & (along < .3) & (relative_side < -1.)
        clamped_base = np.all(np.isclose(corners[2], -40.35, atol=1e-4), axis=0)
        clamped_base &= np.linalg.norm((centers-anchor[:, None])[:2], axis=0) < 3.9
        return toe_face | anchor_face | clamped_base
    holes = np.array([63.*xy_direction(a)[:2] for a in (30., 150., 270.)])
    distance = np.linalg.norm(holes[:, None, :] - centers[:2].T[None, :, :], axis=2).min(axis=0)
    return np.all(np.isclose(corners[2], -49., atol=1e-4), axis=0) & (distance < 5.5)


def contact_cases(path, name, mesh_mm, geometry):
    mesh = mesh_step(path, mesh_mm, volume_algorithm=10, minimum_edge_ratio=.4)
    surface = mesh.boundary_facets()
    points = mesh.p[:, mesh.facets[:, surface]]
    centers = points.mean(axis=1)
    element = ElementVector(ElementTetP1())
    basis = Basis(mesh, element)
    lame, shear = lame_parameters(PETG_REFERENCE_MPA, .37)
    stiffness = asm(linear_elasticity(lame, shear), basis)
    support = surface[support_patch(name, points, centers)]
    if len(support) < 10:
        raise ValueError(f'Mesh does not resolve {name} supports')
    fully_fixed = basis.get_dofs(facets=support).all()
    reduced, _, free = condense(stiffness, D=fully_fixed)
    solve = splu(reduced.tocsc()).solve
    element_centers = mesh.p[:, mesh.t].mean(axis=1)
    radii = geometry['contact_radius_mm']
    rows = {}
    signs = (KEYED_PADS[name][0],) if name in KEYED_PADS else (-1, 1)
    for sign, coverage in product(signs, ('full', 'outer_half')):
        role = 'back' if sign < 0 else 'forward'
        vertex_angle = 90. + sign * (4. if name == 'Part007' else 4. + geometry['nominal_stop_deg'][1])
        radial = xy_direction(vertex_angle)
        tangent = np.cross([0., 0., 1.], radial)
        force_direction = sign*tangent*(-1. if name == 'Part007' else 1.)
        low = radii[0] if coverage == 'full' else np.mean(radii)
        projection = radial @ centers
        planar = np.all(np.isclose(np.einsum('i,ijk->jk', tangent, points), 0., atol=2e-4), axis=0)
        contact = surface[planar & (projection >= low) & (projection <= radii[1])
                          & (centers[2] >= -36.8) & (centers[2] <= -33.)]
        if len(contact) < 3:
            raise ValueError(f'Mesh does not resolve {coverage} of {name} contact')
        rhs = traction(mesh, element, contact, force_direction)
        disp = np.zeros_like(rhs)
        disp[free] = solve(rhs[free])
        residual = stiffness @ disp - rhs
        balance = max(abs(residual[dofs].sum() + force_direction[i]) for i, dofs in enumerate(basis.split_indices()))
        if balance > 1e-5:
            raise ValueError(f'{name} equilibrium fails by {balance:g} N')
        gradient = basis.interpolate(disp).grad
        strain = .5*(gradient + gradient.swapaxes(0, 1))
        identity = np.eye(3)[:, :, None, None]
        stress = 2.*shear*strain + lame*identity*np.einsum('iikq->kq', strain)
        dev = stress - identity*np.einsum('iikq->kq', stress)/3.
        von_mises = np.sqrt(1.5*(dev**2).sum(axis=(0, 1))).mean(axis=1)
        local = (np.linalg.norm(element_centers[:2] - np.mean(radii)*radial[:2, None], axis=0) < 9.)
        local &= element_centers[2] > -40.
        normal = stress[2, 2].mean(axis=1)
        interlayer = np.linalg.norm(stress[:2, 2], axis=0).mean(axis=1)
        rows[f'{role}_{coverage}'] = {'contact_facets': int(len(contact)),
                                     'compliance_mm_per_N_at_1GPa': float(rhs @ disp),
                                     'local_peak_von_mises_MPa_per_N': float(von_mises[local].max()),
                                     'local_p99_von_mises_MPa_per_N': float(np.percentile(von_mises[local], 99)),
                                     'local_peak_layer_tension_MPa_per_N': float(max(0., normal[local].max())),
                                     'local_peak_layer_shear_MPa_per_N': float(interlayer[local].max())}
    return {'mesh_mm': mesh_mm, 'element_count': int(mesh.nelements), 'cases': rows}


def build_report(assembly, cad, grams, mesh_mm, reuse_elastic=None):
    layout = json.loads((cad/'cad_parts.json').read_text())
    cad_hash = digest(assembly)
    if layout['source_sha256'] != cad_hash:
        raise ValueError('The structure and dynamics must use the same CAD')
    geometry = layout['motion_geometry']['yaw_limit']
    energy = energy_bound(cad, layout, json.loads(grams.read_text()))
    firmware = FIRMWARE.read_text()
    yaw_ticks = int(re.search(r'\bneckYawCalibrationTicks\s*=\s*(\d+)', firmware)[1])
    feedback_ticks = int(re.search(r'\bpositionTolerance\s*=\s*(\d+)', firmware)[1])
    powered_feedback_abs = (yaw_ticks+feedback_ticks)*360./4096.
    pads = geometry.get('pad_actors', [])
    actors = ['Part007', 'Part001', *pads]
    meshes = {name: layout['world_sha256'][name] for name in actors}
    if any(digest(cad/'world'/f'{name}.stl') != sha for name, sha in meshes.items()):
        raise ValueError('A structural actor mesh differs from the native CAD export')
    levels = {}
    if reuse_elastic:
        prior = json.loads(reuse_elastic.read_text())
        if prior['cad_actor_sha256'] != meshes:
            raise ValueError('Cannot reuse elasticity from different structural actors')
        levels.update(prior['mesh_levels'])
    missing = [spacing for spacing in mesh_mm if str(spacing) not in levels]
    if missing:
        with TemporaryDirectory() as folder:
            doc = App.openDocument(str(assembly))
            try:
                for name in actors:
                    shape = world_shape(doc.getObject(name))
                    # Charge removable pad flex separately from the assembled seat model.
                    if name == 'Part001' and pads:
                        shape = shape.fuse([world_shape(doc.getObject(pad)) for pad in pads]).removeSplitter()
                        if not shape.isValid() or len(shape.Solids) != 1:
                            raise ValueError('Seat and keyed pad must have a common support datum')
                    shape.exportStep(str(Path(folder)/f'{name}.step'))
            finally:
                App.closeDocument(doc.Name)
            for spacing in missing:
                levels[str(spacing)] = {name: contact_cases(Path(folder)/f'{name}.step', name, spacing, geometry)
                                         for name in actors}
    tolerance = geometry['tangential_build_allowance_mm']
    fit = keyed_fit(geometry) if pads else None
    if fit and fit['absolute_witness_mm'] > tolerance:
        raise ValueError('Nominal dry pad play already exceeds the as-built stop allowance')
    lever = geometry['contact_radius_mm'][0]
    tolerance_deg = degrees(np.arctan(tolerance/lever))
    touch_torque = one_newton_yaw_torque(cad, layout)
    touch_force = 1000.*touch_torque/lever
    contacts = {}
    for index, direction in enumerate(('back', 'forward')):
        nominal = abs(geometry['nominal_stop_deg'][index])
        keys = [direction + '_' + case for case in ('full', 'outer_half')]
        samples = ([source['cases'][key] for source in row.values() if key in source['cases']]
                   for row in levels.values() for key in keys)
        values = []
        for cases in samples:
            c = sum(x['compliance_mm_per_N_at_1GPa'] for x in cases)*PETG_REFERENCE_MPA/MINIMUM_PETG_MPA
            impact = linear_impact(energy['incident_screen_J'], lever, c, 0.)
            F = impact['peak_contact_force_N']
            values.append({'compliance_mm_per_N': c, **impact,
                           'von_mises_peak_MPa': F*max(row['local_peak_von_mises_MPa_per_N'] for row in cases),
                           'von_mises_p99_MPa': F*max(row['local_p99_von_mises_MPa_per_N'] for row in cases),
                           'layer_tension_MPa': F*max(row['local_peak_layer_tension_MPa_per_N'] for row in cases),
                           'layer_shear_MPa': F*max(row['local_peak_layer_shear_MPa_per_N'] for row in cases),
                           'standalone_1N_touch_elastic_deg': degrees(c*touch_force/lever),
                           'standalone_1N_touch_layer_tension_MPa':
                               touch_force*max(row['local_peak_layer_tension_MPa_per_N'] for row in cases),
                           'standalone_1N_touch_layer_shear_MPa':
                               touch_force*max(row['local_peak_layer_shear_MPa_per_N'] for row in cases)})
        late = nominal + tolerance_deg + max(x['additional_rotation_deg'] for x in values)
        earliest = nominal-tolerance_deg
        contacts[direction] = {'late_abs_deg': late, 'earliest_geometric_deg': earliest,
                               'powered_feedback_margin_deg': earliest-powered_feedback_abs,
                               'samples': values, 'within_released_guard': late <= abs(geometry['released_guard_deg'][index]),
                               'powered_guard_separated': earliest > powered_feedback_abs}
    return {'cad_sha256': cad_hash, 'sliced_grams_sha256': digest(grams), 'solver_sha256': digest(Path(__file__)),
            'cad_actor_sha256': meshes, 'reused_elastic_source_sha256': digest(reuse_elastic) if reuse_elastic else None,
            'incident': energy, 'mesh_levels': levels, 'tangential_build_allowance_deg': tolerance_deg,
            'firmware_yaw_feedback_deg_abs': powered_feedback_abs, 'keyed_fit': fit,
            'minimum_PETG_model_MPa': MINIMUM_PETG_MPA, 'direction_results': contacts,
            'standalone_1N_touch': {'maximum_torque_Nm': touch_torque, 'static_stop_force_N': touch_force,
                                    'scope': 'Static direct 1 N held against the yaw stop. No concurrent '
                                             'powered motion or cut-off impact.'},
            'scope': 'First mechanical arrest after full power interruption on a level base, no external contact. '
                     'Full-face and eccentric outer-half loading of the exact printed solids. '
                     'Central rotor output fixture and three seat mount patches. The keyed pad is supported '
                     'at its mechanically loaded flanks and around the stock clamped M3. '
                     'Stop tolerance includes port clearance, assembly and print error. '
                     'Installed screw preload, PETG fatigue/creep and the as-built stop angle require hardware.'}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('assembly', type=Path)
    parser.add_argument('cad', type=Path)
    parser.add_argument('grams', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--mesh-mm', nargs='+', type=float, default=(2., 1.65))
    parser.add_argument('--reuse-elastic', type=Path, help='prior report only with identical structural actor meshes')
    args = parser.parse_args()
    report = build_report(args.assembly, args.cad, args.grams, args.mesh_mm, args.reuse_elastic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    passed = all(row['within_released_guard'] and row['powered_guard_separated']
                 for row in report['direction_results'].values())
    raise SystemExit(0 if passed else 1)
