"""Screen the measured B20 pitch joint under rigid-body reaction loads."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from math import acos, degrees, hypot, pi, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory

import FreeCAD as App
import numpy as np
import Part
from scipy.integrate import quad
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from export_cad import world_shape


LOAD_KEYS = ('pitch_torque_Nm', 'radial_reaction_N', 'axial_reaction_N', 'non_drive_moment_Nm')
SCREENING_LOADS = dict(zip(LOAD_KEYS, (.15, 8., 1., .05)))


def cylinders(shape, axis, predicate):
    return [face.Surface for face in shape.Faces
            if face.Surface.__class__.__name__ == 'Cylinder'
            and abs(getattr(face.Surface.Axis, axis)) > .999 and predicate(face.Surface)]


def flat_height(shape, axis_z, x):
    return min(face.BoundBox.Center.z - axis_z for face in shape.Faces
               if face.BoundBox.ZLength < 1e-5 and face.BoundBox.XMin < x
               and face.BoundBox.XMax > x and 2.5 < face.BoundBox.Center.z - axis_z < 3.5)


def dimensions(assembly, step_path=None):
    doc = App.openDocument(str(assembly.resolve()))
    try:
        shaft, horn, frame = [world_shape(doc.getObject(n)) for n in ('Part015', 'Part016', 'Part019')]
        dowel = world_shape(doc.getObject('PitchPinDowelRight')).BoundBox
        bearings = [world_shape(doc.getObject(n)).BoundBox for n in ('Part012', 'Part014')]
        shaft_cylinder = cylinders(shaft, 'x', lambda c: 3.9 < c.Radius < 4.1)[0]
        axis_z = shaft_cylinder.Center.z
        bore = max(c.Radius for c in cylinders(horn, 'x', lambda c: 4.0 < c.Radius < 4.2))
        inner = max(c.Radius for c in cylinders(frame, 'x', lambda c: 4.0 < c.Radius < 4.3))
        outer = max(c.Radius for c in cylinders(frame, 'x', lambda c: 6.3 < c.Radius < 6.5))
        frame_hole = cylinders(frame, 'z', lambda c: abs(c.Center.x - dowel.Center.x) < .1)[0].Radius
        shaft_hole = cylinders(shaft, 'z', lambda c: abs(c.Center.x - dowel.Center.x) < .1)[0].Radius
        hub_face = next(f for f in frame.Faces if f.Surface.__class__.__name__ == 'Cylinder'
                        and abs(f.Surface.Radius-inner) < 1e-6 and f.BoundBox.Center.x > 0)
        screws = cylinders(horn, 'x', lambda c: abs(c.Radius-1.18) < 1e-6)
        screw_arm = min(hypot(c.Center.y, c.Center.z-axis_z) for c in screws)
        insertion = min(horn.BoundBox.XMax, shaft.BoundBox.XMax) - shaft.BoundBox.XMin
        if step_path:
            bounds = hub_face.BoundBox
            local = frame.common(Part.makeBox(bounds.XLength+.4, 19., 14.,
                                               App.Vector(bounds.XMin-.2, -6.5, axis_z-7.)))
            if not local.isValid() or len(local.Solids) != 1:
                raise RuntimeError('Local right hub did not export as one solid')
            local.exportStep(str(step_path))
        return {'shaft_radius_mm': shaft_cylinder.Radius, 'cross_hole_radius_mm': shaft_hole,
                'dowel_diameter_mm': dowel.XLength, 'dowel_length_mm': dowel.ZLength,
                'dowel_x_mm': dowel.Center.x, 'shaft_axis_z_mm': axis_z,
                'bearing_x_mm': [b.Center.x for b in bearings], 'bearing_width_mm': bearings[1].XLength,
                'hub_x_mm': [hub_face.BoundBox.XMin, hub_face.BoundBox.XMax],
                'hub_outer_radius_mm': outer, 'hub_inner_radius_mm': inner,
                'hub_dowel_hole_radius_mm': frame_hole, 'horn_axis_x_mm': shaft.BoundBox.XMin+insertion/2,
                'd_flat_axial_bond_length_mm': insertion, 'horn_bore_radius_mm': bore,
                'shaft_flat_z_mm': flat_height(shaft, axis_z, shaft.BoundBox.XMin+1.),
                'horn_flat_z_mm': flat_height(horn, axis_z, shaft.BoundBox.XMin+1.),
                'horn_mounting_screw_count': len(screws), 'horn_mounting_screw_radius_mm': screw_arm}
    finally:
        App.closeDocument(doc.Name)


def torsion_section(radius, slot, step):
    """Solve the Prandtl stress function on the split section at the hole center."""
    samples = np.arange(-radius-step, radius+1.5*step, step)
    y, z = np.meshgrid(samples, samples, indexing='ij')
    solid = (y*y + z*z < radius*radius) & (np.abs(y) > slot)
    ids = np.full(solid.shape, -1)
    count = int(solid.sum())
    ids[solid] = np.arange(count)
    i, j = np.where(solid)
    diagonal = np.arange(count)
    rows, cols, values = [diagonal], [diagonal], [np.full(count, 4.)]
    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        neighbor = ids[i+di, j+dj]
        keep = neighbor >= 0
        rows.append(diagonal[keep])
        cols.append(neighbor[keep])
        values.append(-np.ones(keep.sum()))
    matrix = coo_matrix((np.concatenate(values), (np.concatenate(rows), np.concatenate(cols))),
                        shape=(count, count)).tocsc()
    phi = np.zeros(solid.shape)
    phi[solid] = spsolve(matrix, np.full(count, 2.*step*step))
    torsion = 2.*phi.sum()*step*step
    gy, gz = np.gradient(phi, step)
    shear = max(np.hypot(gy[solid], gz[solid]).max(), phi[solid &
                ~(np.roll(solid, 1, 0) & np.roll(solid, -1, 0) & np.roll(solid, 1, 1) & np.roll(solid, -1, 1))].max()/step)
    return {'sample_mm': step, 'torsion_constant_mm4': float(torsion),
            'peak_shear_MPa_per_Nmm': float(shear/torsion)}


def section_properties(g):
    r, hole = g['shaft_radius_mm'], g['cross_hole_radius_mm']
    def half_height(y):
        return sqrt(max(0., r*r-y*y))
    area = quad(lambda y: 4.*half_height(y), hole, r)[0]
    iy = quad(lambda y: 4./3.*half_height(y)**3, hole, r)[0]
    iz = quad(lambda y: 4.*y*y*half_height(y), hole, r)[0]
    return {'shaft_gross_area_mm2': pi*r*r, 'cross_drilled_section_area_mm2': area,
            'weak_bending_modulus_mm3': min(iy/half_height(hole), iz/r),
            'split_section_torsion': [torsion_section(r, hole, s) for s in (.08, .04)]}


def decompose(g, loads):
    m = abs(loads['non_drive_moment_Nm'])*1000.
    torque = abs(loads['pitch_torque_Nm'])*1000.
    radial = abs(loads['radial_reaction_N'])
    axial = abs(loads['axial_reaction_N'])
    lb, rb = g['bearing_x_mm']
    overhang = g['dowel_x_mm']-rb
    head_reaction = radial/2 + m/(rb-lb)
    clamp_radial = head_reaction*overhang/(rb-g['horn_axis_x_mm'])
    return dict(torque=torque, axial=axial, radial=head_reaction,
                overhang=overhang, clamp_radial=clamp_radial)


def evaluate(g, section, loads):
    case = decompose(g, loads)
    r, d, torque = g['shaft_radius_mm'], g['dowel_diameter_mm'], case['torque']
    axial, radial = case['axial'], case['radial']
    lever = r/2.
    cheek_depth = g['dowel_length_mm']/2.-g['hub_inner_radius_mm']
    hub_lever = g['hub_inner_radius_mm']+cheek_depth/2.
    cheek_arm = hub_lever-lever
    shaft_force = torque/(2.*lever)
    frame_force = torque/(2.*hub_lever)
    conservative_frame_force = torque/(2.*g['hub_inner_radius_mm'])
    # Unilateral axial reaction is deliberately assigned entirely to the highly loaded ear.
    ear_force = hypot(conservative_frame_force, axial)
    pin_area = pi*d*d/4.
    pin_bending = hypot(frame_force, axial)*cheek_arm/(pi*d**3/32.)
    pin_shear = 4.*hypot(shaft_force, axial)/(3.*pin_area)
    outer = g['hub_outer_radius_mm']
    fit = g['hub_dowel_hole_radius_mm']
    def edge(z):
        return sqrt(max(0., outer*outer-z*z))-fit
    start, end = g['hub_inner_radius_mm'], g['dowel_length_mm']/2.
    tear_y = 2.*quad(edge, start, end)[0]
    x0, x1 = g['hub_x_mm']
    tear_x = 2.*cheek_depth*(min(g['dowel_x_mm']-x0, x1-g['dowel_x_mm'])-fit)
    shaft_shear = torque*max(row['peak_shear_MPa_per_Nmm'] for row in section['split_section_torsion'])
    shaft_normal = axial/section['cross_drilled_section_area_mm2'] + radial*case['overhang']/section['weak_bending_modulus_mm3']
    fastener_arm, screws = g['horn_mounting_screw_radius_mm'], g['horn_mounting_screw_count']

    flat = g['shaft_flat_z_mm']
    length = g['d_flat_axial_bond_length_mm']
    half_chord = sqrt(r*r-flat*flat)
    round_length = 2.*r*(pi-acos(flat/r))
    full_area = (round_length+2.*half_chord)*length
    flat_area = 2.*half_chord*length
    flat_moment = length*(2.*half_chord*flat*flat+2.*half_chord**3/3.)
    full_moment = round_length*length*r*r+flat_moment
    bond = []
    for fraction in (.1, .25, .5, 1.):
        area = full_area*fraction
        polar = full_moment*fraction
        shear = hypot(torque*r/polar, axial/area)
        rotation = {str(mod): degrees(torque*.15/(mod*polar)) for mod in (15., 50., 200., 1000.)}
        bond.append({'coverage_fraction': fraction, 'required_nominal_peak_shear_MPa': shear,
                     'required_MPa_at_edge_amplification_2': 2.*shear,
                     'elastic_twist_deg_at_0p15mm_by_shear_modulus_MPa': rotation})
    shaft_turn = acos(flat/r)-acos(g['horn_flat_z_mm']/r)
    contact_arm = sqrt(r*r-g['horn_flat_z_mm']**2)
    return {
        'input_peak_magnitudes': loads,
        'load_transfer': {'largest_head_side_radial_N': radial, 'drive_688_radial_N': radial+case['clamp_radial'],
                          'clamp_radial_N': case['clamp_radial'], 'shaft_bending_envelope_Nmm': radial*case['overhang'],
                          'shaft_to_dowel_force_per_side_N': shaft_force, 'dowel_to_frame_force_per_cheek_N': frame_force,
                          'dowel_combined_ear_force_bound_N': ear_force},
        'cross_drilled_shaft': {'axial_plus_bending_MPa': shaft_normal, 'split_torsion_shear_MPa': shaft_shear,
                                'equivalent_MPa_before_cross_hole_3D_effects': hypot(shaft_normal, sqrt(3)*shaft_shear)},
        'steel_dowel': {'bending_MPa': pin_bending, 'shear_MPa': pin_shear,
                        'equivalent_MPa': hypot(pin_bending, sqrt(3)*pin_shear)},
        'printed_hub': {'projected_bearing_MPa': ear_force/(d*cheek_depth),
                        'projected_bearing_if_radial_load_enters_same_cheek_MPa':
                            hypot(conservative_frame_force+radial, axial)/(d*cheek_depth),
                        'cheek_axial_retention_tearout_MPa': axial/tear_x,
                        'cheek_torque_tearout_MPa': conservative_frame_force/tear_y,
                        'shaft_radial_bearing_MPa': radial/(2.*r*(x1-x0-d)),
                        'minimum_dowel_engagement_mm': cheek_depth, 'minimum_front_edge_ligament_mm': edge(end)},
        'horn_fasteners': {'four_screw_in_plane_N_per_screw': (torque/fastener_arm+case['clamp_radial'])/screws,
                           'two_screw_in_plane_N_per_screw': (torque/fastener_arm+case['clamp_radial'])/2.,
                           'minimum_N_per_screw_for_no_friction_slip':
                               {str(mu): (torque/fastener_arm+case['clamp_radial'])/(screws*mu) for mu in (.15,.25,.35)}},
        'D_flat': {'centered_free_play_deg_peak_to_peak': 2.*degrees(shaft_turn),
                   'radial_gap_mm': g['horn_bore_radius_mm']-r,
                   'flat_gap_mm': g['horn_flat_z_mm']-flat,
                   'clamp_radial_force_over_full_projected_shaft_contact_MPa': case['clamp_radial']/(2.*r*length),
                   'mechanical_edge_force_after_unbonded_slip_N': torque/contact_arm,
                   'edge_bearing_MPa_by_contact_width_mm':
                       {str(w): torque/(contact_arm*length*w) for w in (.2,.5,1.)},
                   'full_bond_area_mm2': full_area, 'flat_only_area_mm2': flat_area,
                   'flat_only_required_shear_MPa': hypot(torque*r/flat_moment, axial/flat_area),
                   'bond_sensitivity': bond}}


def local_hub_elasticity(step_path, g, cases, size):
    """Elastic cheek/pad deformation of the exact CAD, with the frame stub clamped."""
    from skfem import Basis, ElementTetP1, ElementVector, asm, condense
    from skfem.models.elasticity import lame_parameters, linear_elasticity
    from scipy.sparse.linalg import splu

    from cable_fea import mesh_step, traction

    mesh = mesh_step(step_path, size)
    boundary = mesh.boundary_facets()
    points = mesh.p[:, mesh.facets[:, boundary]]
    x, y, z = points
    x0 = g['dowel_x_mm']
    z0 = g['shaft_axis_z_mm']
    on = lambda a, b: np.all(abs(a-b) < 1e-4, axis=0)
    fixed = boundary[on(y, 12.5)]
    centers = points.mean(axis=1)
    dowel = on(np.hypot(x-x0, y), g['hub_dowel_hole_radius_mm'])
    main_bore = on(np.hypot(y, z-z0), g['hub_inner_radius_mm'])
    medial = g['hub_dowel_hole_radius_mm']*.25
    upper = centers[2] > z0
    positive_y = centers[1] > medial
    negative_y = centers[1] < -medial
    patches = {
        'upper_forward': boundary[dowel & upper & negative_y],
        'upper_rearward': boundary[dowel & upper & positive_y],
        'lower_forward': boundary[dowel & ~upper & negative_y],
        'lower_rearward': boundary[dowel & ~upper & positive_y],
        'axial': boundary[dowel & upper & (centers[0]-x0 > medial)],
        'radial': boundary[main_bore & (centers[2]-z0 < -g['hub_inner_radius_mm']*.7)],
    }
    if len(fixed) < 3 or any(len(zone) < 3 for zone in patches.values()):
        raise RuntimeError(f'Local hub load or support patch was not resolved at {size:g} mm')
    axes = [(0., -1., 0.), (0., 1., 0.), (0., -1., 0.), (0., 1., 0.), (1., 0., 0.), (0., 0., -1.)]
    element = ElementVector(ElementTetP1())
    basis = Basis(mesh, element)
    modulus, nu = 1000., .37
    lam, shear = lame_parameters(modulus, nu)
    stiffness = asm(linear_elasticity(lam, shear), basis)
    reduced, _, free = condense(stiffness, D=basis.get_dofs(facets=fixed).all())
    solve = splu(reduced.tocsc()).solve
    responses = np.stack([traction(mesh, element, patch, vector)
                          for patch, vector in zip(patches.values(), axes)])
    heights = []
    for patch in patches.values():
        triangles = mesh.p[:, mesh.facets[:, patch]].transpose(2, 1, 0)
        areas = .5*np.linalg.norm(np.cross(triangles[:, 1]-triangles[:, 0],
                                          triangles[:, 2]-triangles[:, 0]), axis=1)
        heights.append(float(np.average(triangles[:, :, 2].mean(axis=1), weights=areas)))
    loaded_nodes = np.unique(mesh.facets[:, np.concatenate(list(patches.values()))])
    elements = mesh.p[:, mesh.t].mean(axis=1)
    near = (np.hypot(elements[0]-x0, elements[1]) < 3.2) & (abs(elements[2]-z0) > 3.5)
    if not near.any():
        raise RuntimeError('Local hub mesh has no cheek stress elements')
    sections = []
    for name, case in cases.items():
        state = decompose(g, case['input_peak_magnitudes'])
        axial, radial = state['axial'], state['radial']
        for reversing in (False, True):
            upper, lower = (1, 2) if reversing else (0, 3)
            torque_force = state['torque']/(heights[upper]-heights[lower])
            patch_forces = np.zeros(4)
            patch_forces[[upper, lower]] = torque_force
            rhs = np.r_[patch_forces, axial, radial] @ responses
            displacement = np.zeros(basis.N)
            displacement[free] = solve(rhs[free])
            react = stiffness@displacement-rhs
            components = basis.split_indices()
            error = max(abs(react[i].sum()+rhs[i].sum()) for i in components)
            if error > 1e-6:
                raise RuntimeError('Local hub FE reaction did not balance the traction')
            u = np.array([displacement[i] for i in components])
            gradient = basis.interpolate(displacement).grad
            strain = .5*(gradient+np.swapaxes(gradient, 0, 1))
            eye = np.eye(3)[:, :, None, None]
            sigma = 2*shear*strain + lam*eye*np.einsum('iijk->jk', strain)
            dev = sigma-eye*np.einsum('iijk->jk', sigma)/3
            von = np.sqrt(1.5*(dev**2).sum(axis=(0, 1))).mean(axis=1)
            sections.append({'case': name, 'reversed_torque': reversing, 'torque_force_per_cheek_N': torque_force,
                             'load_patch_max_elastic_mm': float(np.linalg.norm(u[:, loaded_nodes], axis=0).max()),
                             'near_dowel_stress_p95_MPa': float(np.percentile(von[near], 95)),
                             'near_dowel_stress_p99_MPa': float(np.percentile(von[near], 99))})
    return {'mesh_mm': size, 'elements': int(mesh.nelements), 'modulus_MPa': modulus,
            'poisson_ratio': nu, 'fixed_y_cut_mm': 12.5, 'rows': sections}


def evaluate_assembly(assembly, load_file, stall_torque, hub_step=None):
    cad_hash = sha256(assembly.read_bytes()).hexdigest()
    geometry = dimensions(assembly, hub_step)
    sections = section_properties(geometry)
    if load_file:
        source = json.loads(load_file.read_text())
        if source['source_sha256'] != cad_hash:
            raise ValueError('Rigid-body loads were exported from a different CAD file')
        scenarios = {'rigid_body_envelope': source['pitch_joint_envelope']}
        scenarios.update({name: case for name, case in source.get('pitch_joint_envelopes', {}).items()
                          if isinstance(case, dict) and all(key in case for key in LOAD_KEYS)})
        if source.get('trials'):
            pitch_index = source['joint_order'].index('neck pitch')
            motion_torque = max(row['applied_torque_peak_Nm'][pitch_index] for row in source['trials'].values())
            jam_torque = max(row['zero_speed_model_cap_Nm'][pitch_index] for row in source['trials'].values())
            source_loads = {key: max(float(case[key]) for case in scenarios.values()) for key in LOAD_KEYS}
            scenarios['applied_controller_motion_envelope'] = dict(source_loads, pitch_torque_Nm=motion_torque)
            scenarios['modeled_pwm_limited_jam'] = dict(source_loads, pitch_torque_Nm=jam_torque)
    else:
        scenarios = {'illustrative_loads_only': SCREENING_LOADS}
    clean = {}
    for name, case in scenarios.items():
        clean[name] = {key: float(case[key]) for key in LOAD_KEYS}
        if not all(np.isfinite(value) and value >= 0 for value in clean[name].values()):
            raise ValueError(f'Invalid peak load magnitude in {name}')
    largest = {key: max(case[key] for case in clean.values()) for key in LOAD_KEYS}
    clean['stall_sensitivity_not_a_motion_prediction'] = dict(largest, pitch_torque_Nm=stall_torque)
    cases = {name: evaluate(geometry, sections, case) for name, case in clean.items()}
    report = {'source_sha256': cad_hash, 'load_source': str(load_file) if load_file else 'explicit screening assumptions',
            'geometry_mm': geometry, 'shaft_sections': sections,
            'assumptions': [
                'Peak torque and reactions are applied simultaneously to form an envelope, even if they peak at different times.',
                'The forward right shaft transmits all pitch torque into one dowel. The bearings carry radial force; all axial force may reach the right dowel.',
                'The dowel fit has less radial clearance than the main shaft fit, so a second projected hub result places all one-side radial force in the same cheek.',
                'Uniform projected bearing and tear-out stresses omit local contact, layer anisotropy, print voids, fatigue and creep.',
                'Split 2D steel section carries the full torque as a conservative load allocation; three-dimensional concentration is not solved here.',
                'Adhesive area and modulus are sensitivity parameters, not material strength or a qualification of the bond.',
                'Simple support reactions distribute the non-drive bending moment over the separation of the two bearings.'
            ], 'cases': cases}
    if hub_step:
        report['hub_elastic_FE'] = {
            'scope': 'Homogeneous linear elastic CAD stub, prescribed projected loads. No FDM interlayer, contact slip, adhesive, or lifetime model.',
            'mesh_cases': [local_hub_elasticity(hub_step, geometry, cases, size) for size in (.75, .5)],
        }
    return report


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('assembly', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--loads', type=Path, help='B20 rigid-body load envelope JSON')
    parser.add_argument('--fea', action='store_true', help='Run a local elastic FE screen of the exact right hub')
    parser.add_argument('--stall-torque', type=float, default=1.5, help='Abuse screening torque in N·m')
    args = parser.parse_args()
    if not np.isfinite(args.stall_torque) or args.stall_torque <= 0:
        parser.error('--stall-torque must be finite and positive')
    with TemporaryDirectory(prefix='r5-neck-hub-') as folder:
        hub_step = Path(folder)/'right_hub.step' if args.fea else None
        report = evaluate_assembly(args.assembly, args.loads, args.stall_torque, hub_step)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
