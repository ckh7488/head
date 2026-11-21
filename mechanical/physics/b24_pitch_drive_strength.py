"""Screen the positive B24 pitch coupler using its native shaft and holder solids."""

from argparse import ArgumentParser
from hashlib import file_digest, sha256
from inspect import getsource
import json
from math import degrees, hypot, pi, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory

import FreeCAD as App
import numpy as np
import Part
from scipy.sparse.linalg import splu
from skfem import Basis, ElementTetP1, ElementVector, FacetBasis, LinearForm, asm, condense
from skfem.models.elasticity import lame_parameters, linear_elasticity

from cable_fea import mesh_step, traction
from export_cad import world_shape


def digest(path):
    with path.open('rb') as file:
        return file_digest(file, 'sha256').hexdigest()


def support_faces(mesh):
    boundary = mesh.boundary_facets()
    points = mesh.p[:, mesh.facets[:, boundary]]
    return boundary, points, points.mean(axis=1)


def constitutive(field, basis, lam, shear):
    gradient = basis.interpolate(field).grad
    strain = .5*(gradient+gradient.swapaxes(0, 1))
    trace = np.einsum('iikq->kq', strain)
    identity = np.eye(3)[:, :, None, None]
    stress = 2.*shear*strain+lam*identity*trace
    deviator = 2.*shear*(strain-identity*trace/3.)
    von_mises = np.sqrt(1.5*(deviator*deviator).sum(axis=(0, 1))).mean(axis=1)
    return stress, von_mises


def solve_system(mesh, fixed, modulus, poisson):
    element = ElementVector(ElementTetP1())
    basis = Basis(mesh, element)
    lam, shear = lame_parameters(modulus, poisson)
    stiffness = asm(linear_elasticity(lam, shear), basis)
    reduced, _, free = condense(stiffness, D=basis.get_dofs(facets=fixed).all())
    solve = splu(reduced.tocsc()).solve

    def displacement(load):
        u = np.zeros(basis.N)
        u[free] = solve(load[free])
        return u

    return basis, element, (lam, shear), displacement


def section_torque(path, mesh_mm):
    mesh = mesh_step(path, mesh_mm, volume_algorithm=10, minimum_edge_ratio=.40)
    boundary, points, _ = support_faces(mesh)
    front = boundary[np.all(np.isclose(points[0], 38.7, atol=1e-5), axis=0)]
    outboard = boundary[np.all(np.isclose(points[0], 66., atol=1e-5), axis=0)]
    if min(len(front), len(outboard)) < 6:
        raise ValueError('Both ends of the exact drive shaft must resolve')
    basis, element, material, solve = solve_system(mesh, outboard, 205000., .29)
    surface = FacetBasis(mesh, element, facets=front)
    coords = surface.global_coordinates()
    polar = np.sum((coords[1]**2+(coords[2]-112.)**2)*surface.dx)

    @LinearForm
    def torque(v, w):
        return (v[2]*w.x[1]-v[1]*(w.x[2]-112.))/polar

    u = solve(asm(torque, surface))
    _, vm = constitutive(u, basis, *material)
    x = mesh.p[0, mesh.t].mean(axis=0)
    regions = {'new_tap': abs(x-45.9)<2., 'outboard_dowel': abs(x-60.5)<2.}
    return {'mesh_mm': mesh_mm, 'elements': int(mesh.nelements),
            'local_vm_max_MPa_per_Nmm': {name: float(vm[region].max()) for name, region in regions.items()},
            'local_vm_p99_MPa_per_Nmm': {name: float(np.percentile(vm[region],99)) for name, region in regions.items()}}


def layer_metrics(stress, vm, region):
    axial = stress[0, 0, region]
    shear = np.linalg.norm(stress[0, 1:][:, region], axis=0)
    return {'local_vm_MPa': float(vm[region].max()), 'local_layer_tension_MPa': float(max(0., axial.max())),
            'local_layer_compression_MPa': float(max(0., -axial.min())), 'local_layer_shear_MPa': float(shear.max())}


def holder_responses(path, mesh_mm, cases):
    mesh = mesh_step(path, mesh_mm, volume_algorithm=10, minimum_edge_ratio=.4)
    boundary, points, center = support_faces(mesh)

    def on(axis, value):
        return np.all(np.isclose(points[axis], value, atol=1e-5), axis=0)

    y, z = center[1:]
    mounting = np.logical_or.reduce([np.hypot(y-a,z-b) < 2.85
                                     for a,b in ((-8.,112.),(8.,112.),(0.,104.),(0.,120.))])
    fixed = boundary[on(0,36.) & mounting]
    cap_center = np.hypot(center[0]-45.9, center[1])
    cap = boundary[on(2,117.5) & (cap_center<2.78)]
    flat = boundary[on(2,115.08) & (np.abs(center[1])<sqrt(7.))]
    radius = np.hypot(points[0]-45.9, points[1])
    hole = np.all(abs(radius-1.55)<.006, axis=0) & (z>115.08) & (z<117.5)
    patches = [boundary[hole & (s*y>.22)] for s in (-1.,1.)]
    if min(map(len, (fixed, cap, flat, *patches))) < 5:
        raise ValueError('The printed clamp support or contact patch did not resolve')
    basis, element, material, solve = solve_system(mesh, fixed, 700., .37)
    precontact = traction(mesh, element, cap, (0., 0., -1.))
    seated = precontact + traction(mesh, element, flat, (0., 0., 1.))
    flat_nodes = np.unique(mesh.facets[:, flat])
    closure_compliance = -np.mean(solve(precontact)[basis.split_indices()[2][flat_nodes]])
    flat_surface = FacetBasis(mesh, element, facets=flat)
    polar = np.sum(flat_surface.global_coordinates()[1]**2*flat_surface.dx)

    @LinearForm
    def flat_rocking(v, w):
        return w.x[1]*v[2]/polar

    rocking_load = asm(flat_rocking, flat_surface)
    # A Y force on the top face creates the same signed moment as the pressure couple.
    flat_shear_load = traction(mesh, element, flat, (0., -1./3.08, 0.))
    rocking_displacement, shear_displacement = [solve(load) for load in (rocking_load, flat_shear_load)]
    normal = float(rocking_load @ rocking_displacement)
    shear = float(flat_shear_load @ shear_displacement)
    cross = float(rocking_load @ shear_displacement)
    variation = normal+shear-2.*cross
    fraction_normal = float(np.clip((shear-cross)/variation, 0., 1.))
    mixed = fraction_normal**2*normal + (1.-fraction_normal)**2*shear + 2.*fraction_normal*(1.-fraction_normal)*cross
    preload = solve(seated)
    side_load = [traction(mesh, element, patch, (0., s, 0.)) for s, patch in zip((-1.,1.), patches, strict=True)]
    u_shear = [solve(load) for load in side_load]
    side_compliance = max(float(load @ u) for load, u in zip(side_load, u_shear, strict=True))
    element_center = mesh.p[:, mesh.t].mean(axis=1)
    collar = element_center[0] > 40.95
    rows = {}
    for torque in cases:
        force = torque*1000./3.
        cases_by_preload = {}
        for P in (0., 150., 250.):
            cases_by_preload[str(P)] = [layer_metrics(*constitutive(force*u+P*preload,basis,*material),collar)
                                        for u in u_shear]
        rows[str(torque)] = {'drive_hole_transverse_load_N': force, 'by_preload_N': cases_by_preload}
    return {'mesh_mm': mesh_mm, 'elements': int(mesh.nelements),
            'drive_bore_selected_faces': list(map(len, patches)),
            'flat_gap_closing_compliance_at_E700_mm_per_N': float(closure_compliance),
            'nominal_gap_closing_force_at_E700_N': float(.08/closure_compliance),
            'seated_deg_per_Nm_at_E700': {name: degrees(1000.*compliance) for name, compliance in
                                         (('pressure_couple', normal), ('friction_force', shear), ('minimum_of_both', mixed))},
            'normal_pressure_share_at_minimum': fraction_normal,
            'fallback_hole_compliance_mm_per_N_at_E700': side_compliance,
            'loads': rows}


def planar_contact_areas(horn):
    seat = App.Vector(45.9, 0., 117.5)
    cap = Part.Face(Part.Wire([Part.makeCircle(2.78, seat)]))
    flat_clip = Part.makePlane(5.0, 2.*sqrt(7.), App.Vector(44., -sqrt(7.), 115.08))
    cap_faces = [f for f in horn.Faces if abs(f.BoundBox.ZMin-117.5)<1e-6 and f.BoundBox.ZLength<1e-6]
    flat_faces = [f for f in horn.Faces if abs(f.BoundBox.ZMin-115.08)<1e-6 and f.BoundBox.ZLength<1e-6]
    flat_patches = [subface for face in flat_faces for subface in face.common(flat_clip).Faces]
    flat_area = sum(face.Area for face in flat_patches)
    flat_second_moment = sum(face.MatrixOfInertia.A11 + face.Area*face.CenterOfMass.y**2
                             for face in flat_patches)
    if flat_area <= 0. or flat_second_moment <= 0.:
        raise ValueError('The exact D flat has no resolvable contact')
    return {'cap_projected_area_mm2': sum(f.common(cap).Area for f in cap_faces),
            'first_D_flat_overlap_mm2': flat_area,
            'first_D_flat_centred_second_moment_about_x_mm4': flat_second_moment}


def mechanical_bounds(torques, areas):
    rows = {}
    for torque in torques:
        force = torque*1000./3.
        minor = 2.45
        area = pi*minor**2/4.
        section = pi*minor**3/32.
        bending = force*2.42/section
        shear = force/area
        rows[str(torque)] = {
            'positive_fastener_force_N': force,
            'screw_root_bending_MPa_at_full_stack_lever': bending,
            'screw_root_shear_MPa': shear,
            'screw_root_vm_with_250N_preload_MPa': hypot(bending+250./area, sqrt(3.)*shear),
            'projected_PETG_bore_pressure_MPa': force/(2.42*3.),
            'preload_N_for_D_face_friction_only': {str(mu): force/mu for mu in (.1,.2,.3)},
        }
    tightening = (.07, .08)
    screw_diameter_m = .003
    nut_factor = (.16, .30)
    preload = (tightening[0]/(nut_factor[1]*screw_diameter_m), tightening[1]/(nut_factor[0]*screw_diameter_m))
    cap_area = areas['cap_projected_area_mm2']
    flat_area = areas['first_D_flat_overlap_mm2']
    flat_moment = areas['first_D_flat_centred_second_moment_about_x_mm4']
    flat_full_contact_arm = flat_moment/(flat_area*sqrt(7.))
    return {'torques': rows,
            'average_cap_pressure_at_150_and_250N_MPa': [P/cap_area for P in (150.,250.)],
            'average_flat_pressure_at_150_and_250N_MPa': [P/flat_area for P in (150.,250.)],
            'first_seating_torque_setting_Nm': tightening, 'unmeasured_nut_factor_sensitivity': nut_factor,
            'preload_from_tightening_sensitivity_N': preload,
            'average_cap_pressure_from_tightening_sensitivity_MPa': [P/cap_area for P in preload],
            'full_contact_first_lift_Nm_sensitivity': [P*flat_full_contact_arm/1000. for P in preload],
            'nominal_clearance_potential_lash_peak_to_peak_deg': degrees(2.*np.arcsin(.10/(2.*5.5))),
            'bench_reversal': {'proof_torque_Nm_each_sign': .12, 'dial_arm_mm': 50., 'force_N_each_sign': 2.4,
                               'neutral_after_unloading_limit_deg': .10,
                               'neutral_after_unloading_dial_limit_mm': 50.*np.sin(np.radians(.10)),
                               'scope': 'Fixture the four OEM mounts and measure the shaft without gearbox play. '
                                        'Check seating, installed elastic travel and residual motion after unloading. '
                                        'Bench is pending.'}}


def audit(assembly, source_cad, output, torque_cases, mesh_mm, force_path=None, reuse_elastic=None):
    native_hash = digest(assembly)
    manifest = json.loads((source_cad/'cad_parts.json').read_text())
    if native_hash != manifest['source_sha256']:
        raise ValueError('Use the same native assembly and exported world layout')
    geometry = manifest['motion_geometry']['pitch_coupler']
    if any(abs(actual-expected)>1e-7 for actual, expected in zip(geometry['m3_seat_mm'], (45.9,0.,117.5),strict=True)):
        raise ValueError('Audit preload/contact face selections for the revised coupling geometry')
    actor_hashes = {name: manifest['world_sha256'][name] for name in ('Part015','Part016','PitchDriveScrew')}
    if any(digest(source_cad/'world'/f'{name}.stl') != expected for name, expected in actor_hashes.items()):
        raise ValueError('Positive pitch actor mesh differs from the native CAD export')
    force = None
    operating_torque = None
    if force_path:
        force = json.loads(force_path.read_text())
        if force['cad_sha256'] != native_hash or force['pitch_coupling'] != 'positive_M3':
            raise ValueError('The force envelope must apply to this positive pitch coupling')
        operating_torque = max(mode['warm_peak_motor_demand_Nm'][1] for mode in force['modes'].values())
    elastic_source = sha256(''.join(getsource(f) for f in
        (support_faces, constitutive, solve_system, section_torque, layer_metrics, holder_responses)).encode()).hexdigest()
    if reuse_elastic:
        previous = json.loads(reuse_elastic.read_text())
        elastic_steel = previous['elastic_steel']
        elastic_holder = previous['elastic_PETG_holder']
        if (previous['actor_sha256'] != actor_hashes or previous['elastic_equations_sha256'] != elastic_source
                or [row['mesh_mm'] for row in elastic_holder] != list(mesh_mm)
                or any(set(row['loads']) != {str(t) for t in torque_cases} for row in elastic_holder)):
            raise ValueError('Reused elasticity must match the structural actors, solver, mesh size and cases')
        areas = previous['measured_areas']
    else:
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            doc = App.openDocument(str(assembly.resolve()))
            try:
                shaft, horn = [world_shape(doc.getObject(name)) for name in ('Part015','Part016')]
                areas = planar_contact_areas(horn)
                shaft.exportStep(str(directory/'shaft.step'))
                horn.exportStep(str(directory/'holder.step'))
            finally:
                App.closeDocument(doc.Name)
            elastic_steel = [section_torque(directory/'shaft.step', step) for step in mesh_mm]
            elastic_holder = [holder_responses(directory/'holder.step', step, torque_cases) for step in mesh_mm]
    low_modulus_MPa = 500.
    seated_max = max(max(row['seated_deg_per_Nm_at_E700'].values()) for row in elastic_holder)
    report = {'cad_sha256': native_hash, 'solver_sha256': digest(Path(__file__)),
              'elastic_equations_sha256': elastic_source,
              'actor_sha256': actor_hashes,
              'reused_elastic_sha256': digest(reuse_elastic) if reuse_elastic else None,
              'force_path_sha256': digest(force_path) if force_path else None,
              'max_modeled_operating_torque_Nm': operating_torque,
              'operating_torque_within_reversal_proof': operating_torque <= .12 if force else None,
              'seated_angle_screen': {'lower_modulus_MPa': low_modulus_MPa,
                                      'max_seated_deg_per_Nm_at_E700': seated_max,
                                      'max_modeled_elastic_angle_deg': seated_max * operating_torque * 700./low_modulus_MPa
                                                                       if operating_torque is not None else None},
              'measured_areas': areas, 'mechanical_bounds': mechanical_bounds(torque_cases, areas),
              'elastic_steel': elastic_steel, 'elastic_PETG_holder': elastic_holder,
              'scope': 'Steel is screened with a torsional couple across the open major-size tap and dowel bores. '
                       'The PETG holder is clamped at four OEM flange patches, then loaded through the positive M3 bore '
                       'with a conservative 3 mm torque lever. Tightening preload after the D-flat seats and prior gap '
                       'closure are screened separately. Flat-pressure first lift is an ideal fully seated, '
                       'uniform-foundation estimate distinct from backup side-load screening. Printed layer '
                       'normal is CAD X. No thread-notch, fatigue, dynamic impact, or as-built preload claim.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('assembly', type=Path)
    parser.add_argument('source_cad', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--torque-cases', type=float, nargs='+', default=(.07844,.12,.30,.5085))
    parser.add_argument('--mesh-mm', type=float, nargs='+', default=(.65,.50))
    parser.add_argument('--force-path', type=Path)
    parser.add_argument('--reuse-elastic', type=Path)
    args = parser.parse_args()
    audit(**vars(args))
