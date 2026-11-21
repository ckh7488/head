"""Elastic screening of the exact R5 pitch stop and its loaded frame."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from math import pi, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory

import FreeCAD as App
import numpy as np
from scipy.sparse.linalg import splu
from skfem import Basis, ElementTetP1, ElementVector, asm, condense
from skfem.models.elasticity import lame_parameters, linear_elasticity

from b20_dynamics import GRAVITY, x_rotation
from b22_pitch_stop_load import linear_impact
from cable_fea import mesh_step, traction
from export_cad import world_shape


MODULI_MPA = (500., 1000., 1800.)
CONTACT_POISSON = .37


def stop_loading(mesh, element, surface, vertices, centers, stop, part, pivot, clevis):
    normal = np.array(stop['contact_normal'])
    point = np.array(stop['contact_center_mm'])
    oppose = -stop['direction']*np.sign(np.cross(point-pivot, normal)[0])
    direction = oppose*normal if part == 'frame' else -oppose*normal
    if part == 'frame':
        turn = x_rotation(np.deg2rad(stop['nominal_deg'])).T
        point = pivot+turn@(point-pivot)
        normal, direction = turn@normal, turn@direction
    if clevis:
        center = np.array(clevis['center_mm'])
        radial = centers[1:].T-center[1:]
        radii = np.linalg.norm(vertices[:, :, 1:]-center[1:], axis=2)
        radius = clevis['bore_radius_mm']
        on_bore = np.all(np.isclose(radii, radius, atol=2e-3), axis=0)
        in_arc = (radial@direction[1:]) > radius*.45
        faces = []
        load = None
        for low, high in clevis['ear_spans_mm']:
            sector = surface[on_bore & in_arc & (centers[0] > low) & (centers[0] < high)]
            if len(sector) < 4:
                raise ValueError(f'Unresolved pin bearing pressure on {part} for {stop["id"]}')
            faces.extend(sector)
            traction_i = traction(mesh, element, sector, .5*direction)
            load = traction_i if load is None else load+traction_i
        return np.array(faces), load
    tangent = np.cross([1., 0., 0.], normal)
    planar = np.all(np.isclose((vertices-point)@normal, 0., atol=2e-4), axis=0)
    distances = centers.T-point
    patch = surface[planar & (abs(distances[:, 0]) < stop['contact_width_mm']/2.)
                    & (abs(distances@tangent) < stop['contact_height_mm']/2.)]
    if len(patch) < 6:
        raise ValueError(f'Unresolved contact face {stop["id"]} on {part}')
    return patch, traction(mesh, element, patch, direction)


def elastic_mesh(path, spacing, part, stops, pivot, coupled_body=None, bearings=None, clevis=None):
    mesh = mesh_step(path, spacing, volume_algorithm=10, minimum_edge_ratio=.4) if clevis else mesh_step(path, spacing)
    surface = mesh.boundary_facets()
    points = mesh.p[:, mesh.facets[:, surface]]
    centers = points.mean(axis=1)
    vertices = points.transpose(1, 2, 0)
    if part == 'yoke':
        support = np.all(np.isclose(points[2], mesh.p[2].min(), atol=1e-4), axis=0)
    else:
        radii = np.linalg.norm(vertices[:, :, 1:]-pivot[1:], axis=2)
        support = np.all(np.isclose(radii, 4.12, atol=2e-3), axis=0) & (abs(centers[0]) > 52.)
    constrained_faces = surface[support]
    if len(constrained_faces) < 6:
        raise ValueError(f'{part} fixture is unresolved')
    element = ElementVector(ElementTetP1())
    basis = Basis(mesh, element)
    lam, shear = lame_parameters(1000., CONTACT_POISSON)
    stiff = asm(linear_elasticity(lam, shear), basis)
    limits = basis.get_dofs(facets=constrained_faces).all()
    reduced, _, free = condense(stiff, D=limits)
    solve = splu(reduced.tocsc()).solve
    indices = basis.split_indices()
    rows = {}
    for stop in stops:
        patch, rhs = stop_loading(mesh, element, surface, vertices, centers, stop, part, pivot, clevis)

        def displacement(load):
            disp = np.zeros_like(load)
            disp[free] = solve(load[free])
            reaction = stiff@disp
            if max(abs(reaction[index].sum()) for index in indices) > 1e-5:
                raise ValueError(f'{part} elastic solve failed force equilibrium')
            return disp

        disp = displacement(rhs)
        faces = mesh.p[:, mesh.facets[:, patch]]
        normals = np.cross((faces[:, 1]-faces[:, 0]).T, (faces[:, 2]-faces[:, 0]).T)
        gradient = basis.interpolate(disp).grad
        strain = .5*(gradient+np.swapaxes(gradient, 0, 1))
        identity = np.eye(3)[:, :, None, None]
        stress = 2.*shear*strain+lam*identity*np.einsum('iikq->kq', strain)
        deviator = stress-identity*np.einsum('iikq->kq', stress)/3.
        von = np.sqrt(1.5*(deviator**2).sum(axis=(0, 1))).mean(axis=1)
        cut_near = np.isin(mesh.t, np.unique(mesh.facets[:, constrained_faces])).any(axis=0)
        rows[stop['id']] = {
            'facets': int(len(patch)), 'patch_area_mm2': float(.5*np.linalg.norm(normals, axis=1).sum()),
            'normal_compliance_mm_per_N_at_1GPa': float(rhs@disp),
            'maximum_unclamped_element_von_mises_MPa_per_N': float(max(von[~cut_near])),
            'p99_unclamped_element_von_mises_MPa_per_N': float(np.percentile(von[~cut_near], 99)),
        }
        if part == 'yoke' and coupled_body is not None:
            support_radii = np.linalg.norm(vertices[:, :, 1:]-pivot[1:], axis=2)
            radial = centers[1:].T-pivot[1:]
            bearing_seat = np.all(np.isclose(support_radii, 8.13, atol=3e-3), axis=0)
            shoulder_load = np.zeros_like(rhs)
            left, right, _ = bearing_vectors(stop, coupled_body, pivot, bearings, 0., 1., 0., False)
            for x, vector in zip(bearings, (-left, -right), strict=True):
                side = np.sign(x)
                bearing_faces = surface[bearing_seat & (centers[0]*side > 49.0)
                                        & (radial@vector > 4.*np.linalg.norm(vector))]
                if len(bearing_faces) < 4:
                    raise ValueError(f'Unresolved radial bearing traction on x={x:g}')
                shoulder_load += traction(mesh, element, bearing_faces, (0., *vector))
            complete = rhs+shoulder_load
            rows[stop['id']]['coupled_bearings_normal_compliance_mm_per_N_at_1GPa'] = float(
                complete@displacement(complete))
    return {'mesh_mm': spacing, 'elements': int(mesh.nelements), 'contact': rows}


def bearing_vectors(stop, body, pivot, x_bearings_mm, rotation_extra_deg, force, touch, with_gravity=True):
    axis = np.array([1., 0., 0.])
    orientation = x_rotation(np.deg2rad(stop['nominal_deg']+stop['direction']*rotation_extra_deg))
    center = orientation@np.array(body['center_relative_to_axis_mm'])*.001
    inertia = orientation@np.array(body['inertia_about_pivot_kg_m2'])@orientation.T
    normal = np.array(stop['contact_normal'])
    stop_offset = (np.array(stop['contact_center_mm'])-pivot)*.001
    stop_force = -stop['direction']*np.sign(np.cross(stop_offset, normal)[0])*force*normal
    gravity = body['mass_kg']*GRAVITY if with_gravity else np.zeros(3)
    touch_offset = orientation@(np.array(body['touch_point_mm'])-pivot)*.001
    tangent = np.cross(axis, touch_offset)
    touch_force = stop['direction']*touch*tangent/np.linalg.norm(tangent)
    moments = np.cross(center, gravity)+np.cross(stop_offset, stop_force)+np.cross(touch_offset, touch_force)
    alpha = moments[0]/inertia[0, 0]
    bearings = body['mass_kg']*np.cross(alpha*axis, center)-gravity-stop_force-touch_force
    perpendicular = np.cross(inertia@(alpha*axis)-moments, axis)
    x_left, x_right = .001*np.array(x_bearings_mm)
    right = (perpendicular[1:]-x_left*bearings[1:])/(x_right-x_left)
    left = bearings[1:]-right
    return left, right, bearings[0]


def bearing_reactions(stop, body, pivot, x_bearings_mm, rotation_extra_deg, force, touch):
    left, right, axial = bearing_vectors(stop, body, pivot, x_bearings_mm, rotation_extra_deg, force, touch)
    return {'left_radial_N': float(np.linalg.norm(left)), 'right_radial_N': float(np.linalg.norm(right)),
            'total_axial_N': float(abs(axial))}


def get_clevis(shape, center, pin_diameter, pin_length):
    spans = {-1: [], 1: []}
    radii = set()
    for face in shape.Faces:
        if face.Surface.__class__.__name__ != 'Cylinder':
            continue
        cylinder = face.Surface
        if abs(cylinder.Axis.x) < .999 or abs(cylinder.Radius-pin_diameter/2.) > .22:
            continue
        if np.linalg.norm(np.array(tuple(cylinder.Center))[1:]-center[1:]) > .005:
            continue
        bounds = face.BoundBox
        side = np.sign(bounds.Center.x-center[0])
        spans[side].append((bounds.XMin, bounds.XMax))
        radii.add(round(cylinder.Radius, 6))
    if not all(spans.values()) or len(radii) != 1:
        raise ValueError('Two cylindrical support ears are required at each link pin')
    ends = center[0]-pin_length/2., center[0]+pin_length/2.
    limit = [(max(ends[0], min(low for low, _ in entries)), min(ends[1], max(high for _, high in entries)))
             for entries in spans.values()]
    if not limit[0][0] < limit[0][1] < center[0] < limit[1][0] < limit[1][1]:
        raise ValueError('Link ears must have a clear center gap')
    return {'center_mm': list(center), 'bore_radius_mm': radii.pop(), 'ear_spans_mm': limit}


def link_stops(geometry, pivot):
    link = geometry['link']
    lower, upper = np.array(link['pan_pin_mm']), np.array(link['head_pin_mm'])
    result = []
    for stop in geometry['stops']:
        rotation = x_rotation(np.deg2rad(stop['nominal_deg']))
        center = pivot+rotation@(upper-pivot)
        vector = center-lower
        length = float(np.linalg.norm(vector))
        result.append({**stop, 'contact_center_mm': center.tolist(),
                       'contact_normal': (vector/length).tolist(), 'link_span_mm': length})
    return result


def steel_link(stop, link, clevises):
    diameter = link['pin_diameter_mm']
    plate = link['plate_thickness_mm']
    slot = link['slot_width_mm']
    net_width = link['plate_width_mm']-slot
    span = stop['link_span_mm']
    pin_I = pi*diameter**4/64.
    steel_modulus = 200000.
    compliance = span/(steel_modulus*net_width*plate)
    ears = {}
    for part, clevis in clevises.items():
        (l0, l1), (r0, r1) = clevis['ear_spans_mm']
        thickness = min(l1-l0, r1-r0)
        bearing_centres = (r0+r1-l0-l1)/2.
        compliance += bearing_centres**3/(48.*steel_modulus*pin_I)
        pin_bend = (bearing_centres/4.-plate/8.)/(2.*pin_I/diameter)
        pin_shear = 2./(pi*diameter**2)
        ears[part] = {'minimum_ear_axial_width_mm': thickness,
                      'minimum_bore_wall_MPa_per_N': 1./(2.*diameter*thickness),
                      'pin_von_mises_MPa_per_N': sqrt(pin_bend**2+3.*pin_shear**2)}
    return {'incremental_axes_compliance_mm_per_N': compliance,
            'strip_net_area_mm2': net_width*plate,
            'steel_slot_bearing_MPa_per_N': 1./(plate*diameter),
            'weak_axis_euler_buckling_N': pi*pi*steel_modulus*net_width*plate**3/(12.*span**2),
            'ears': ears}


def impact(stops, loads, results, pivot, bearings, link=None, clevises=None,
           energy_key='maximum', case_prefix=''):
    bodies = {name: row for name, row in loads['cases'].items() if name.startswith(case_prefix)}
    cases = {}
    for stop in stops:
        name = stop['id']
        end = 'positive' if stop['direction'] > 0 else 'negative'
        label = loads[energy_key][end]['speed_sensitivity']
        sources = [row['stops'][end]['closing_gravity_torque_Nm'] for row in bodies.values()]
        torque = max(sources)+loads.get('moving_strap', {}).get('gravity_torque_upper_Nm', 0.)
        assist = loads['touch_force_N']*max(radius for phases in loads['exterior_levers_m_at_jaw_deg'].values()
                                         for radius in phases.values())
        lever = abs(np.cross(np.array(stop['contact_center_mm'])-pivot, stop['contact_normal'])[0])
        traction_group = {part: min(rows, key=lambda row: row['mesh_mm'])['contact'][name]
                          for part, rows in results.items()}
        compliance = sum(row['normal_compliance_mm_per_N_at_1GPa'] for row in traction_group.values())
        coupled_compliance = (traction_group['yoke'].get('coupled_bearings_normal_compliance_mm_per_N_at_1GPa',
                                                        traction_group['yoke']['normal_compliance_mm_per_N_at_1GPa'])
                              + traction_group['frame']['normal_compliance_mm_per_N_at_1GPa'])
        metal = steel_link(stop, link, clevises) if link else None
        metal_compliance = metal['incremental_axes_compliance_mm_per_N'] if metal else 0.
        runs = {}
        for case, scenario, drive in (('gravity_only', 'gravity_and_initial_energy_upper_J', torque),
                                      ('gravity_and_pulse', 'with_touch_energy_upper_J', torque+assist)):
            runs[case] = {}
            for modulus in MODULI_MPA:
                bound = linear_impact(label[scenario], lever, compliance*1000./modulus+metal_compliance, drive)
                bound['with_coupled_unit_bearing_tractions'] = linear_impact(
                    label[scenario], lever, coupled_compliance*1000./modulus+metal_compliance, drive)
                force = bound['peak_contact_force_N']
                bound['parts'] = {
                    part: {'p99_elastic_stress_MPa': force*entry['p99_unclamped_element_von_mises_MPa_per_N'],
                           'maximum_unclamped_elastic_stress_MPa':
                               force*entry['maximum_unclamped_element_von_mises_MPa_per_N']}
                    for part, entry in traction_group.items()}
                if metal:
                    metal_force = max(force, bound['with_coupled_unit_bearing_tractions']['peak_contact_force_N'])
                    bound['steel_and_ears'] = {
                        'strip_gross_slot_edge_estimate_MPa': 3.*metal_force/metal['strip_net_area_mm2'],
                        'slot_projected_bearing_MPa': metal_force*metal['steel_slot_bearing_MPa_per_N'],
                        'pin_and_ear_ratings_needed_MPa': {
                            part: {'projected_polymer_bearing': metal_force*row['minimum_bore_wall_MPa_per_N'],
                                   'pin_von_mises': metal_force*row['pin_von_mises_MPa_per_N']}
                            for part, row in metal['ears'].items()},
                    }
                if all('inertia_about_pivot_kg_m2' in row for row in bodies.values()):
                    touch = loads['touch_force_N'] if case == 'gravity_and_pulse' else 0.
                    reactions = [bearing_reactions(stop, row, pivot, bearings,
                                                   bound['additional_rotation_deg'], force, touch)
                                 for row in bodies.values()]
                    bound['bearing_reaction_envelope'] = {
                        field: max(row[field] for row in reactions) for field in reactions[0]}
                runs[case][str(modulus)] = bound
        cases[name] = {'contact_lever_mm': float(lever), 'local_FEM_compliance_mm_per_N_at_1GPa': compliance,
                       'coupled_bearings_compliance_mm_per_N_at_1GPa': coupled_compliance,
                       'gravity_torque_Nm': torque, 'assistive_touch_torque_Nm': assist, 'elastic_impacts': runs}
        if metal:
            cases[name]['steel_link'] = metal
    return cases


def run(cad, loads_path, mesh_sizes):
    doc = App.openDocument(str(cad.resolve()))
    try:
        geometry = json.loads(doc.R5.MotionGeometry)['pitch_stop']
        link = geometry.get('link')
        pivot = np.array([0., 0., 112.])
        if link:
            stops = link_stops(geometry, pivot)
            parts = dict(zip(('yoke', 'frame'), geometry['modified_part_keys'][:2], strict=True))
        else:
            stops = geometry['stops']
            parts = dict(zip(('yoke', 'frame'), stops[0]['actors'], strict=True))
        bearings = [world_shape(doc.getObject(name)).BoundBox.Center.x for name in ('Part012', 'Part014')]
        loads = json.loads(loads_path.read_text())
        coupled_body = loads['cases'].get('plates-0-jaw-0')
        if not coupled_body or 'inertia_about_pivot_kg_m2' not in coupled_body:
            coupled_body = None
        results = {}
        clevises = {}
        with TemporaryDirectory(prefix='r5-pitch-fe-') as folder:
            for key, name in parts.items():
                path = Path(folder)/f'{key}.step'
                shape = world_shape(doc.getObject(name))
                if link:
                    center = link['pan_pin_mm'] if key == 'yoke' else link['head_pin_mm']
                    clevises[key] = get_clevis(shape, center, link['pin_diameter_mm'], link['pin_length_mm'])
                if len(shape.Solids) != 1:
                    raise ValueError(f'{name} must export as one connected solid')
                shape.exportStep(str(path))
                results[key] = []
                for spacing in mesh_sizes:
                    row = elastic_mesh(path, spacing, key, stops, pivot, coupled_body, bearings, clevises.get(key))
                    results[key].append(row)
                    compliance = [part['normal_compliance_mm_per_N_at_1GPa'] for part in row['contact'].values()]
                    print(key, spacing, row['elements'], np.round(compliance, 6).tolist(), flush=True)
        verified_key = 'nominal_no_ballast_maximum' if link and 'nominal_no_ballast_maximum' in loads else 'maximum'
        acceptance = impact(stops, loads, results, pivot, bearings, link, clevises,
                            verified_key, 'plates-0-jaw-' if verified_key != 'maximum' else '')
        sensitivity = {}
        if link and 'forward_75g_sensitivity_maximum' in loads:
            sensitivity = impact(stops, loads, results, pivot, bearings, link, clevises,
                                 'forward_75g_sensitivity_maximum', 'plates-0-forward-75g-')
        return {'cad_sha256': sha256(cad.read_bytes()).hexdigest(),
                'loads_sha256': sha256(loads_path.read_bytes()).hexdigest(),
                'load_cad_sha256': loads['cad_sha256'], 'mesh': results,
                'modeled_arrest_budget_deg': geometry['released_overshoot_deg'],
                'bounds': acceptance, 'forward_75g_sensitivity_bounds': sensitivity,
                'scope': 'Small-strain homogeneous polymer with the yoke underside and frame shaft bores fixed. '
                         'Pressure is spread over nominal contact faces or both pin ears. '
                         'Bearing reactions apply peak elastic force to the rigid head at zero rebound speed. '
                         'The coupled yoke sensitivity applies additional unit radial reactions at the seats. '
                         'Layer adhesion, imperfect first-edge contact, bearing clearance and collapse require separate evidence.'}
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('loads', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--mesh-mm', type=float, nargs='+', default=(1.8, 1.4))
    args = parser.parse_args()
    result = run(args.cad, args.loads, args.mesh_mm)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
