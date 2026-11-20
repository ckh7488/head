"""Screen the B20 printed jaw's drive-side arm under a slipping horn joint."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
import numpy as np
from scipy.sparse.linalg import splu
from scipy.spatial.transform import Rotation
from skfem import Basis, BilinearForm, ElementHex1, ElementVector, FacetBasis, LinearForm, MeshHex, asm
import trimesh


REVISIONS = Path(__file__).resolve().parents[1] / 'revisions'
CORE = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
PRODUCTION = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'
JAW = ('Jaw_30_moving_jaw', 'Jaw_38_left_jaw_drive_arm', 'Jaw_39_right_jaw_pivot_arm')
STALL_NM = .52  # ROBOTIS XL330-M288 at 5 V.
DRIVE_AXIS = np.array([1., 0., 0.])
CROP = np.array([[-72.5, -42., 57.], [-35., 2., 104.]])
# Effective secant moduli used for screening. No claim is made for brand-specific strength.
E_PLANE, E_LAYER, G_LAYER = 1300., 650., 235.
REFERENCE_LAYER_TENSION, REFERENCE_LAYER_SHEAR = 8., 5.
ROBOTIS = 'https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/'
PETG_HF = 'https://store.bblcdn.com/s6/default/20423d7f839c4a66b9712508549c68b4/Bambu_PETG_HF_TDS.pdf'


def load_printed_jaw(project, assembly, source_parts):
    with ZipFile(assembly) as cad:
        doc = etree.fromstring(cad.read('Document.xml'))

    def rotation(name):
        item = doc.find(f".//ObjectData/Object[@name='{name}']/Properties/Property[@name='Placement']/PropertyPlacement")
        return Rotation.from_quat([float(item.get(f'Q{i}')) for i in range(4)]).as_matrix()

    printed_to_world = rotation('JawMotion') @ rotation(JAW[0])
    with ZipFile(project) as bundle:
        config = etree.fromstring(bundle.read('Metadata/model_settings.config'))
        obj = config.xpath("./object[metadata[@key='name'][@value='30_38_39_jaw_one_piece-B20']]")[0]
        object_id = obj.get('id')
        project_model = etree.fromstring(bundle.read('3D/3dmodel.model'))
        component = project_model.find(f".//{CORE}object[@id='{object_id}']//{CORE}component")
        build = project_model.find(f".//{CORE}item[@objectid='{object_id}']")
        identity = np.eye(3).reshape(-1)
        for item in (component, build):
            matrix = np.fromstring(item.get('transform'), sep=' ')
            if not np.allclose(matrix[:9], identity):
                raise ValueError('The jaw print orientation changed; update the layer model')
        mesh_path = component.get(PRODUCTION + 'path').lstrip('/')
        geometry = etree.fromstring(bundle.read(mesh_path))
        vertices = np.array([[float(v.get(i)) for i in 'xyz'] for v in geometry.findall('.//' + CORE + 'vertex')])
        triangles = np.array([[int(t.get(i)) for i in ('v1', 'v2', 'v3')]
                              for t in geometry.findall('.//' + CORE + 'triangle')])
        profile = json.loads(bundle.read('Metadata/project_settings.config'))
    before = trimesh.boolean.union(source_parts, engine='manifold')
    aligned = before.vertices @ printed_to_world
    origin = (aligned.max(axis=0) + aligned.min(axis=0) - vertices.max(axis=0) - vertices.min(axis=0)) / 2
    result = trimesh.Trimesh((vertices + origin) @ printed_to_world.T, triangles, process=False)
    if (not result.is_volume or result.body_count != 1 or
            not np.allclose(result.bounds, before.bounds, atol=.01, rtol=0) or abs(result.volume - before.volume) > .05):
        raise ValueError('The packaged jaw must be one closed solid that matches the B20 world CAD')
    return result, printed_to_world, {k: profile[k] for k in (
        'printer_settings_id', 'layer_height', 'filament_settings_id', 'wall_loops', 'sparse_infill_density')}


def voxel_mesh(shape, requested_step):
    axes = [np.linspace(a, b, int(np.ceil((b - a) / requested_step)) + 1) for a, b in zip(*CROP)]
    centers = [(x[:-1] + x[1:]) / 2 for x in axes]
    x, y, z = centers
    keep = np.zeros((len(x), len(y), len(z)), dtype=bool)
    for k, level in enumerate(z):
        segments = trimesh.intersections.mesh_plane(shape, [0., 0., 1.], [0., 0., level])[:, :, :2]
        first, second = segments[:, 0], segments[:, 1]
        for j, line in enumerate(y):
            crosses = (first[:, 1] > line) != (second[:, 1] > line)
            a, b = first[crosses], second[crosses]
            crossing = np.sort(a[:, 0] + (line - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1]))
            if len(crossing) % 2:
                raise ValueError(f'The jaw outline is open at z={level:g}, y={line:g}')
            keep[:, j, k] = np.searchsorted(crossing, x) % 2
    lattice = MeshHex.init_tensor(*axes)
    midpoint = lattice.p[:, lattice.t].mean(axis=1)
    indices = tuple(np.searchsorted(edge, value) - 1 for edge, value in zip(axes, midpoint))
    return lattice.restrict(np.flatnonzero(keep[indices])), [float(axis[1] - axis[0]) for axis in axes]


def elasticity():
    nu_plane, nu_through = .37, .24
    compliance = np.diag([1/E_PLANE, 1/E_PLANE, 1/E_LAYER, 1/G_LAYER, 1/G_LAYER,
                          2*(1+nu_plane)/E_PLANE])
    compliance[0, 1] = compliance[1, 0] = -nu_plane/E_PLANE
    compliance[:2, 2] = compliance[2, :2] = -nu_through/E_PLANE
    return np.linalg.inv(compliance)


def strain_components(gradient, print_frame):
    local = np.einsum('ai,ab...,bj->ij...', print_frame, gradient, print_frame)
    return np.array([local[0, 0], local[1, 1], local[2, 2], local[1, 2] + local[2, 1],
                     local[0, 2] + local[2, 0], local[0, 1] + local[1, 0]])


def traction(facets, direction, weight):
    # Normalizing by the cosine-weighted bearing surface gives the specified resultant.
    weight = weight[:, None] / np.sum(weight[:, None] * facets.dx)

    @LinearForm
    def load(v, _):
        return np.einsum('i,i...->...', direction, v) * weight

    integrated = weight * facets.dx
    center = np.einsum('ijk,jk->i', facets.global_coordinates(), integrated)
    return asm(load, facets), center


def solve_drive(printed, print_frame, screw_centers, reference_pivot, step):
    mesh, edges = voxel_mesh(printed, step)
    element = ElementVector(ElementHex1())
    basis = Basis(mesh, element, intorder=2)
    material = elasticity()

    @BilinearForm
    def stiffness(u, v, _):
        a = strain_components(u.grad, print_frame)
        b = strain_components(v.grad, print_frame)
        return np.einsum('i...,ij,j...->...', a, material, b)

    matrix = asm(stiffness, basis).tocsc()
    boundary = mesh.boundary_facets()
    corners = mesh.p[:, mesh.facets[:, boundary]]
    facets = corners.mean(axis=1).T
    clamped = np.all(np.isclose(corners[0], CROP[1, 0]), axis=0)
    clamped |= np.all(np.isclose(corners[1], CROP[0, 1]), axis=0)
    clamped |= np.all(np.isclose(corners[2], CROP[0, 2]), axis=0)
    restraint = basis.get_dofs(facets=boundary[clamped]).all()
    free = np.setdiff1d(np.arange(basis.N), restraint)
    factor = splu(matrix[free][:, free].tocsc(), permc_spec='MMD_AT_PLUS_A', options={'SymmetricMode': True})
    separation = screw_centers[1] - screw_centers[0]
    lever = np.linalg.norm(separation)
    tangent = np.cross(DRIVE_AXIS, separation) / lever
    dofs = basis.split_indices()
    cell_center = mesh.p[:, mesh.t].mean(axis=1).T
    arm = (cell_center[:, 0] < -43.8) & (cell_center[:, 0] > -54)
    arm &= (cell_center[:, 2] > 78) & (cell_center[:, 2] < 88.5)
    horn = (cell_center[:, 0] > -47.) & (cell_center[:, 0] < -43.8) & (cell_center[:, 2] > 89.)
    results = []
    for sign in (-1, 1):
        forces = []
        patches = []
        areas = []
        centers = []
        for sense, center in zip((-1., 1.), screw_centers):
            direction = tangent * sense * sign
            offset = facets - center
            offset[:, 0] = 0.
            radial = np.linalg.norm(offset, axis=1)
            toward = offset @ direction
            side = np.ptp(corners[0], axis=0) > 1e-8
            bore = side & (radial > .6) & (radial < 1.8) & (toward > .2)
            bore &= (facets[:, 0] > -47.) & (facets[:, 0] < -43.8)
            if np.count_nonzero(bore) < 4:
                raise ValueError('Mesh did not resolve both screw-bearing patches')
            surface = FacetBasis(mesh, element, facets=boundary[bore], intorder=2)
            force, loaded_center = traction(surface, direction, toward[bore] / radial[bore])
            forces.append(force)
            centers.append(loaded_center)
            patches.append(np.unique(mesh.facets[:, boundary[bore]]))
            areas.append(float(np.sum(surface.dx)))
        moment = np.cross(centers[1] - centers[0], tangent)[0]
        if moment < lever * .8:
            raise ValueError('The bearing couple missed the horn axis')
        force_N = STALL_NM * 1000 / moment
        rhs = force_N * (forces[0] + forces[1])
        u = np.zeros(basis.N)
        u[free] = factor.solve(rhs[free])
        react = matrix @ u - rhs
        points = mesh.p.T - reference_pivot
        total = np.array(dofs)
        reaction = react[total].T
        reaction_force = np.linalg.norm(reaction.sum(axis=0))
        reaction_moment = np.cross(points, reaction).sum(axis=0)
        commanded_moment = np.cross(centers[1]-centers[0], tangent) * force_N * sign
        if reaction_force > .001 or np.linalg.norm(reaction_moment + commanded_moment) > .001:
            raise ValueError('Drive arm fixture failed force or torque equilibrium')
        response = u[np.array(dofs)]
        average = [response[:, nodes].mean(axis=1) for nodes in patches]
        strain = strain_components(basis.interpolate(u).grad, print_frame)
        stress = np.einsum('ij,j...->i...', material, strain).mean(axis=-1)
        layer_tension = np.maximum(stress[2], 0.)
        layer_shear = np.hypot(stress[3], stress[4])
        interaction = np.hypot(layer_tension / REFERENCE_LAYER_TENSION, layer_shear / REFERENCE_LAYER_SHEAR)
        results.append({
            'torque_Nm': STALL_NM * sign,
            'force_N_per_screw': float(force_N),
            'bearing_patch_area_mm2': areas,
            'reaction_force_residual_N': float(reaction_force),
            'reaction_torque_residual_Nmm': float(np.linalg.norm(reaction_moment+commanded_moment)),
            'relative_twist_deg': float(np.degrees(abs((average[1] - average[0]) @ tangent) / lever)),
            'horn_patch_max_displacement_mm': float(max(np.linalg.norm(response[:, n], axis=0).max() for n in patches)),
            'drive_arm_layer_tension_p95_MPa': float(np.percentile(layer_tension[arm], 95)),
            'drive_arm_layer_shear_p95_MPa': float(np.percentile(layer_shear[arm], 95)),
            'drive_arm_screening_utilization_p95': float(np.percentile(interaction[arm], 95)),
            'horn_layer_tension_p95_MPa': float(np.percentile(layer_tension[horn], 95)),
            'horn_layer_shear_p95_MPa': float(np.percentile(layer_shear[horn], 95)),
            'horn_screening_utilization_p95': float(np.percentile(interaction[horn], 95)),
        })
    return {'cell_edges_mm': edges, 'cells': int(mesh.nelements), 'cases': results}


def torque_budget(mesh, screw_centers, pivot, mass):
    props = mesh.mass_properties
    center = np.asarray(props.center_mass)
    dy, dz = (center - pivot)[1:]
    inclination = np.radians(np.arange(-15, 20))
    gravity = mass * 9.80665 * max(abs(dy*np.cos(inclination) - dz*np.sin(inclination))) / 1000
    inertia = (np.asarray(props.inertia)[0, 0] / props.mass + dy*dy + dz*dz) * mass * 1e-6
    acceleration = 40 * 214.577 * 2*np.pi / 3600
    incisors = mesh.triangles_center
    near = (abs(incisors[:,0]) < 20) & (incisors[:,1] < -57) & (incisors[:,2] > 29) & (incisors[:,2] < 49)
    tooth = incisors[near]
    if not len(tooth):
        raise ValueError('Selected tooth contact is missing')
    vertical_lever = np.max(abs(tooth[:,1]-pivot[1])) / 1000
    tangential_lever = np.max(np.linalg.norm((tooth-pivot)[:, 1:], axis=1)) / 1000
    couple_force = STALL_NM * 1000 / np.linalg.norm(screw_centers[1] - screw_centers[0])
    return {
        'mass_g': mass*1000, 'max_gravity_Nm': float(gravity), 'drive_acceleration_rad_s2': float(acceleration),
        'inertia_about_hinge_kg_m2': float(inertia), 'max_inertial_Nm': float(inertia*acceleration),
        'unloaded_acceleration_plus_gravity_Nm': float(gravity+inertia*acceleration),
        'teeth_vertical_lever_mm': float(vertical_lever*1000),
        'teeth_max_tangential_lever_mm': float(tangential_lever*1000),
        'jam_force_N_per_horn_screw': couple_force,
        'horn_nominal_bearing_pressure_MPa': couple_force/(2.*3.1),
        'stall_equivalent_vertical_force_N_at_tooth': float(STALL_NM/vertical_lever),
        '10_N_vertical_contact_torque_Nm': float(10*vertical_lever),
        '20_N_vertical_contact_torque_Nm': float(20*vertical_lever),
    }


def neck_sections(arm):
    origin, root = np.array([-45.35, -9., 92.]), np.array([-54., -20., 73.5])
    normal = (root-origin)/np.linalg.norm(root-origin)
    offsets = np.arange(8.25, 13, .25)
    areas = []
    for distance in offsets:
        section = arm.section(normal, origin + normal*distance)
        if section is None:
            raise ValueError('A cross-section in the drive neck is empty')
        path, _ = section.to_2D()
        polygons = path.polygons_full
        if len(polygons) != 1:
            raise ValueError('The drive neck is not continuous through the measured stations')
        areas.append(float(polygons[0].area))
    radius = np.sqrt(min(areas)/np.pi)
    moment = 1000*STALL_NM
    bending = moment*np.sqrt(1-normal[0]**2)
    torsion = moment*abs(normal[0])
    return {'centroid_axis_world': normal.tolist(), 'minimum_mm2': min(areas), 'stations': len(areas),
            'equivalent_circular_diameter_mm': float(2*radius),
            'circular_nominal_bending_stress_MPa': float(4*bending/(np.pi*radius**3)),
            'circular_nominal_torsion_shear_MPa': float(2*torsion/(np.pi*radius**3))}


def motion_crosscheck(path, cad_sha256, load_without_friction):
    dynamic = json.loads(path.read_text())
    if dynamic['source_sha256'] != cad_sha256:
        raise ValueError('The dynamics results are from another CAD export')
    jaw_id = dynamic['joint_order'].index('jaw')
    nominal = dynamic['trials']['nominal_firmware_profile']
    friction = nominal['friction_Nm'][jaw_id]
    return {
        'firmware_profile_demand_with_friction_Nm': nominal['torque_demand_bound_Nm'][jaw_id],
        'firmware_profile_joint_friction_assumption_Nm': friction,
        'analytical_sum_without_friction_Nm': load_without_friction,
        'aggressive_quintic_with_friction_Nm': dynamic['trials']['nominal']['torque_demand_bound_Nm'][jaw_id],
        'warm_firmware_profile_with_friction_Nm':
            dynamic['trials']['forward_low_warm_firmware_profile']['torque_demand_bound_Nm'][jaw_id],
    }


def use_cases(lever_mm, trials, routine_Nm):
    finest = min(trials, key=lambda trial: np.prod(trial['cell_edges_mm']))
    cases = finest['cases']
    lever_m = lever_mm/1000
    quantities = {
        'horn_patch_local_deflection_mm': 'horn_patch_max_displacement_mm',
        'relative_twist_deg': 'relative_twist_deg',
        'arm_layer_utilization_p95': 'drive_arm_screening_utilization_p95',
        'horn_layer_utilization_p95': 'horn_screening_utilization_p95',
    }
    per_Nm = {label: max(row[key] for row in cases)/STALL_NM for label, key in quantities.items()}
    rows = []
    for force in (0., .25, .5, 1.):
        added = force*lever_m
        torque = routine_Nm + added
        rows.append({'opposing_touch_N': force, 'touch_moment_Nm': added, 'combined_moment_Nm': torque,
                     **{label: slope*torque for label, slope in per_Nm.items()}})
    return rows


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--assembly', type=Path, default=REVISIONS/'b20/R5-B20-Assembly.FCStd')
    parser.add_argument('--print-project', type=Path, default=REVISIONS/'b20/R5-B20-P2S.3mf')
    parser.add_argument('--mass-g', type=float, default=45.961)
    parser.add_argument('--step', type=float, nargs='+', default=(.95, .7))
    parser.add_argument('--dynamics', type=Path, help='Optional independent B20 MuJoCo report from the same CAD')
    args = parser.parse_args()
    source = json.loads((args.cad/'cad_parts.json').read_text())
    if sha256(args.assembly.read_bytes()).hexdigest() != source['source_sha256']:
        raise ValueError('B20 world export does not match the assembly')
    meshes = [trimesh.load_mesh(args.cad/'world'/f'{name}.stl') for name in JAW]
    jaw, layers, profile = load_printed_jaw(args.print_project, args.assembly, meshes)
    screws = np.array([trimesh.load_mesh(args.cad/'world'/f'JawHornScrew{i}.stl').center_mass for i in (0, 1)])
    pivot = np.array(source['jaw_pivot_mm'])
    loads = torque_budget(jaw, screws, pivot, args.mass_g/1000)
    result = {
        'cad_sha256': source['source_sha256'],
        'project_sha256': sha256(args.print_project.read_bytes()).hexdigest(),
        'sources': {'servo': ROBOTIS, 'filament_coupons': PETG_HF},
        'layer_normal_world': layers[:,2].tolist(), 'print_profile': profile,
        'catalog_tensile_strength_MPa': {'XY': [34., 4.], 'Z': [23., 4.]},
        'moduli_MPa': {'in_plane': E_PLANE, 'layer_normal': E_LAYER, 'layer_shear': G_LAYER},
        'screening_strength_MPa': {'layer_tension': REFERENCE_LAYER_TENSION, 'layer_shear': REFERENCE_LAYER_SHEAR},
        'fixture_cut_bounds_mm': CROP.tolist(),
        'model_assumptions': [
            'The cropped mandible fixes three cut faces. Compliance of the rest of the jaw and the horn is excluded.',
            'Opposite bearing tractions model both torque directions after clamp friction is lost.',
            '20% infill is homogenized using assumed effective moduli. Beads, bonds and notches are not resolved.',
            'Layer screening stresses are engineering assumptions, with no coupon qualification for this print.',
            'Light touch adds its opposing moment to routine torque. The local linear estimates omit radial force and impact.',
        ],
        'drive_neck_sections': neck_sections(meshes[1]),
        'loads': loads,
        'local_arm_trials': [solve_drive(jaw, layers, screws, pivot, step) for step in args.step],
    }
    if args.dynamics:
        result['motion_crosscheck'] = motion_crosscheck(
            args.dynamics, source['source_sha256'], loads['unloaded_acceleration_plus_gravity_Nm'])
        routine = result['motion_crosscheck']['warm_firmware_profile_with_friction_Nm']
        result['linear_use_cases'] = use_cases(loads['teeth_vertical_lever_mm'], result['local_arm_trials'], routine)
        result['linear_use_cases_any_tangent'] = use_cases(
            loads['teeth_max_tangential_lever_mm'], result['local_arm_trials'], routine)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
