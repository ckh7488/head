"""Load screen for the B20 blink and eye links, using exported world meshes in mm."""

from argparse import ArgumentParser
from itertools import product
import json
from math import acos, cos, degrees, pi, radians, sin, sqrt
from pathlib import Path

import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.optimize import brentq
from shapely.geometry import Point, Polygon
from shapely.geometry.polygon import orient
import trimesh as tr


CLAMPS_X_MM = np.array([-53.9, 10.2, 54.15])
LID_PIVOT_YZ_MM = np.array([-39., 119.])
STEEL_E_MPA = 195_000.
STEEL_G_MPA = 77_000.
LID_TOUCH_LEVER_M = .014
MODELED_LID_DRAG_NM = .003


def unit(vector):
    return vector / np.linalg.norm(vector)


def section(mesh, origin, direction):
    cut = mesh.section(plane_origin=origin, plane_normal=direction)
    if cut is None:
        raise ValueError(f'No section at {origin}')
    planar, to_world = cut.to_2D()
    return planar.polygons_full, to_world


def second_moment(polygon):
    """Smallest centroidal second moment of a planar polygon in mm⁴."""
    polygon = orient(polygon)
    area = ix = iy = ixy = 0.
    center = np.asarray(polygon.centroid.coords[0])
    for ring in (polygon.exterior, *polygon.interiors):
        x, y = (np.asarray(ring.coords) - center).T
        w = x[:-1]*y[1:] - x[1:]*y[:-1]
        area += w.sum()/2
        ix += ((y[:-1]**2 + y[:-1]*y[1:] + y[1:]**2)*w).sum()/12
        iy += ((x[:-1]**2 + x[:-1]*x[1:] + x[1:]**2)*w).sum()/12
        ixy += ((2*x[:-1]*y[:-1] + x[:-1]*y[1:] + x[1:]*y[:-1] + 2*x[1:]*y[1:])*w).sum()/24
    if area <= 0:
        raise ValueError('Non-positive link section')
    return float(np.linalg.eigvalsh([[ix, -ixy], [-ixy, iy]])[0])


def bore_diameter(mesh, center, axis):
    polygons, to_world = section(mesh, center, axis)
    local = tr.transformations.transform_points([center], np.linalg.inv(to_world))[0]
    point = Point(local[:2])
    for polygon in polygons:
        for ring in polygon.interiors:
            if Polygon(ring).covers(point):
                return 2*ring.distance(point)
    raise ValueError(f'No bore at {center}')


def link(mesh, start, end, modulus, pin_axis=(1, 0, 0)):
    start, end = np.asarray(start), np.asarray(end)
    direction = unit(end-start)
    length = float(np.linalg.norm(end-start))
    # Sample the web outside the pin holes; the local pin fit is a separate input.
    sections = []
    for fraction in np.linspace(.18, .82, 9):
        polygons, to_world = section(mesh, start + fraction*(end-start), direction)
        if len(polygons) != 1:
            raise ValueError(f'Expected one connected link web at {fraction:g}')
        profile = polygons[0]
        center = tr.transformations.transform_points([[*profile.centroid.coords[0], 0.]], to_world)[0]
        eccentricity = np.linalg.norm(np.cross(center-start, direction))
        sections.append((profile.area, second_moment(profile), eccentricity))
    area, inertia = np.min(sections, axis=0)[:2]
    eccentricity = max(row[2] for row in sections)
    bores = [bore_diameter(mesh, center, pin_axis) for center in (start, end)]
    return {'length_mm': length, 'sampled_web_area_mm2': float(area), 'sampled_minor_inertia_mm4': float(inertia),
            'sampled_centroid_offset_mm': float(eccentricity),
            'sampled_bore_min_diameters_mm': bores,
            'one_sided_clearance_on_2mm_pin_mm': sum(max(0., (d-2.)/2) for d in bores),
            'compliance_mm_per_N': float(length/modulus*(1/area + eccentricity**2/inertia)),
            'pinned_Euler_load_N': float(pi*pi*modulus*inertia/length**2)}


def levers(angles, radius, phase, direction):
    rad = np.radians(np.asarray(angles) + phase)
    return radius*(np.cos(rad)*direction[1] - np.sin(rad)*direction[0])


def pin_takeup(span, radius, phase, limits, clearance):
    """Worst one-sided rotation to take up a specified unforced rod-end clearance."""
    span = np.asarray(span)
    length = np.linalg.norm(span)
    candidates = np.linspace(0, 45., 181)
    worst = 0.
    for angle in np.arange(limits[0], limits[1]+.25, .5):
        start = radians(angle+phase)
        tip = radius*np.array([cos(start), sin(start)])
        for sign in (-1, 1):
            def free_motion(delta):
                theta = start+np.radians(sign*delta)
                next_tip = radius*np.stack((np.cos(theta), np.sin(theta)), axis=-1)
                change = np.linalg.norm(span+next_tip-tip, axis=-1)-length
                return abs(change)-clearance

            crossed = np.flatnonzero(free_motion(candidates) >= 0)
            if not len(crossed):
                raise ValueError(f'No closure of pin clearance within the search at {angle:g}°')
            first = crossed[0]
            if first:
                delta = brentq(free_motion, candidates[first-1], candidates[first])
                worst = max(worst, delta)
    return worst


def pin_fit_alternative(span, radius, phase, limits, profile):
    # Two finished bores at Ø2.08–2.10 mm plus actual Ø2.00 mm bearing shanks.
    return {
        'modeled_link_only_one_sided_angle_deg': pin_takeup(
            span, radius, phase, limits, profile['one_sided_clearance_on_2mm_pin_mm']),
        'finished_2p08_to_2p10_mm_bores_angular_range_deg': [
            pin_takeup(span, radius, phase, limits, clearance) for clearance in (.08, .10)
        ],
    }


def flat_section(radius, depth):
    """Centroidal moments of a circle clipped at z=radius-depth, and torsion bounds."""
    nodes, weights = np.polynomial.legendre.leggauss(96)
    height = radius - depth
    z = (nodes+1)*(radius+height)/2-radius
    y = np.sqrt(radius**2-z*z)
    weights = weights*(radius+height)/2
    area = weights @ (2*y)
    centroid_z = weights @ (2*y*z)/area
    iy = weights @ (2*y*(z-centroid_z)**2)
    iz = weights @ (2*y**3/3)
    return np.array([iz, iy]), pi*(radius-depth/2)**4/2, iy+iz


def shaft_response(layout, rod_directions, levers_mm, torques_Nmm, angle, radius, flat_geometry):
    """Elastic shaft on two simple supports, with overhung blink links and rotating flats."""
    bearing_left, bearing_right = layout['bearing_x_mm']
    stations = np.array([5.85, -layout['link_x_mm'], layout['link_x_mm'], bearing_left, bearing_right])
    link_forces = rod_directions * (torques_Nmm/levers_mm)[:, None]
    bearing_right_force = -(stations[:3]-bearing_left) @ link_forces/(bearing_right-bearing_left)
    bearing_left_force = -link_forces.sum(axis=0)-bearing_right_force
    forces = np.vstack((link_forces, bearing_left_force, bearing_right_force))
    x = np.linspace(-56, 56, 449)
    flat = np.min(np.abs(x[:, None]-CLAMPS_X_MM), axis=1) <= 1.8
    bending_moment = np.maximum(x[:, None]-stations, 0.) @ forces
    full_i = pi*radius**4/4
    clipped_i, clipped_j_low, clipped_j_high = flat_geometry
    a = radians(angle)
    rotate = np.array([[cos(a), -sin(a)], [sin(a), cos(a)]])
    curvature = bending_moment/(STEEL_E_MPA*full_i)
    curvature[flat] = ((bending_moment[flat] @ rotate)/clipped_i) @ rotate.T/STEEL_E_MPA
    movement = cumulative_trapezoid(cumulative_trapezoid(curvature, x, axis=0, initial=0),
                                   x, axis=0, initial=0)
    at = lambda location: np.array([np.interp(location, x, axis) for axis in movement.T]).T
    left, right = at(bearing_left), at(bearing_right)
    pin_displacement = at(stations[:3]) - (
        left + (stations[:3]-bearing_left)[:, None]*(right-left)/(bearing_right-bearing_left))
    twist_bounds = []
    for end, torque in zip(CLAMPS_X_MM[::2], abs(torques_Nmm[1:]), strict=True):
        span = abs(end-CLAMPS_X_MM[1])
        # Half of each end flat lies inside this torque path.
        twist_bounds.append([torque/STEEL_G_MPA*((span-3.6)/(2*full_i)+3.6/j)
                             for j in (clipped_j_high, clipped_j_low)])
    moment_mpa = np.linalg.norm(bending_moment, axis=1)*radius / np.where(flat, min(clipped_i), full_i)
    return link_forces, pin_displacement, np.array(twist_bounds), float(moment_mpa.max()), float(
        np.linalg.norm(forces[-2:], axis=1).max())


def blink_cases(layout, links, diameter, flat_depth):
    radii = np.array([layout['radius_mm'], layout['lid_radius_mm'], layout['lid_radius_mm']])
    direction = [unit(np.asarray(layout['servo_yz_mm'])-layout['shaft_yz_mm']),
                 unit(LID_PIVOT_YZ_MM-layout['shaft_yz_mm'])]
    direction = np.array([direction[0], direction[1], direction[1]])
    routine = {'nominal_intrinsic_drag': (MODELED_LID_DRAG_NM, MODELED_LID_DRAG_NM)}
    for touch in (.25, .50, 1.00):
        loaded = MODELED_LID_DRAG_NM + LID_TOUCH_LEVER_M*touch
        routine[f'left_touch_{touch:g}_N'] = loaded, MODELED_LID_DRAG_NM
        routine[f'right_touch_{touch:g}_N'] = MODELED_LID_DRAG_NM, loaded
    both_touch = MODELED_LID_DRAG_NM + LID_TOUCH_LEVER_M*.25
    routine['bilateral_touch_0.25_N_each'] = both_touch, both_touch
    overload = {'left_resistance': (.04, 0.), 'right_resistance': (0., .04),
                'both_resist': (.04, .04), 'left_jam_0p12': (.12, 0.), 'right_jam_0p12': (0., .12),
                'rated_stall_5V_left_jam': (.52, 0.), 'rated_stall_5V_right_jam': (0., .52)}
    # Paired effective levers at both ends of each parallelogram are equal.
    compliance = np.array([profile['compliance_mm_per_N'] for profile in links])
    flat_geometry = flat_section(diameter/2, flat_depth)
    data = {}
    angles = np.linspace(0., 91., 183)
    for name, (left, right) in {**routine, **overload}.items():
        peak = []
        for angle in angles:
            arms = np.array([levers(angle, r, layout['phase_deg'], d) for r, d in zip(radii, direction, strict=True)])
            loads = 1000*np.array([left+right, -left, -right])
            force, bend, twist, stress, bearings = shaft_response(
                layout, direction, arms, loads, angle, diameter/2, flat_geometry)
            extension = (force*direction).sum(axis=1)*compliance
            projection = np.einsum('ij,ij->i', bend, direction)
            drive_lag = -(extension[0]+projection[0])/arms[0]
            lid_lag = drive_lag - twist[:, 1] + (extension[1:]+projection[1:])/arms[1:]
            peak.append([*np.linalg.norm(force, axis=1), *np.linalg.norm(bend, axis=1),
                         *np.degrees(twist[:, 1]), abs(degrees(lid_lag[0]-lid_lag[1])),
                         np.max(np.abs(np.degrees(lid_lag))), stress, bearings])
        peak = np.max(peak, axis=0).tolist()
        data[name] = {'scenario': 'normal_or_gentle_touch' if name in routine else 'overload_sensitivity',
                      'load_per_lid_Nm': [left, right],
                      'drive_left_right_force_N': peak[:3], 'drive_left_right_shaft_bend_mm': peak[3:6],
                      'left_right_shaft_twist_upper_deg': peak[6:8], 'maximum_lid_difference_deg': peak[8],
                      'maximum_lid_lag_deg': peak[9], 'maximum_nominal_shaft_bending_MPa': peak[10],
                      'maximum_bearing_reaction_N': peak[11]}
    return data


def clamp_screen(cranks, shaft_y, shaft_top_z, radius, depth):
    seating = []
    # The plain nut is pulled up against the roof of its wrench slot.
    for x, crank in zip(CLAMPS_X_MM, cranks, strict=True):
        polygons, matrix = section(crank, [x, shaft_y, 161.02], [0, 0, 1])
        world = lambda ring: tr.transformations.transform_points(
            np.column_stack((np.asarray(ring.coords), np.zeros(len(ring.coords)))), matrix)[:, :2]
        hex_radius = 5.5/sqrt(3.)
        angles = np.arange(6)*pi/3 + pi/6
        nut = Polygon(np.column_stack((x+hex_radius*np.cos(angles), shaft_y+hex_radius*np.sin(angles))))
        area = sum(Polygon(world(p.exterior), [world(r) for r in p.interiors]).intersection(nut).area for p in polygons)
        seating.append(area)
    height = radius-depth
    half_width = sqrt(radius**2-height**2)
    onset = {}
    for gap in (.02, .05, .10, .20):
        onset[str(gap)] = degrees(acos(height/radius)-acos((height+gap)/radius))
    conditions = []
    for install, factor, retention, friction in product((.10, .20, .30), (.16, .25), (.3, 1.), (.10, .25)):
        initial = 1000*install/(3*factor)
        retained = retention*initial
        conditions.append({'installation_Nm': install, 'nut_factor': factor, 'retention_fraction': retention,
                           'friction': friction, 'retained_preload_N': retained,
                           'tip_only_first_slip_Nm': friction*retained*height/1000,
                           'tip_and_bore_first_slip_Nm': friction*retained*(height+radius)/1000,
                           'initial_roof_pressure_MPa': initial/min(seating)})
    return {'roof_areas_mm2': seating, 'flat_half_width_mm': half_width, 'flat_top_mm': shaft_top_z,
            'screw_gap_to_flat_contact_deg': onset, 'optimistic_edge_normal_at_0p12_N': 120/half_width,
            'sensitivity_cases': conditions}


def eye_cases(meshes, layout, modulus):
    pitch_layout = layout.get('eye_pitch', {})
    pitch_radius = pitch_layout.get('crank_radius_mm', 10.)
    pitch_phase = pitch_layout.get('phase_deg', 0.)
    pickup = pitch_radius*np.array([cos(radians(pitch_phase)), sin(radians(pitch_phase))])
    motor_yz = np.asarray(pitch_layout.get('servo_axis_mm', (58.65, 10., 151.))[1:])
    cradle_yz = np.asarray(pitch_layout.get('cradle_axis_mm', (0., -39., 119.))[1:])
    pitch = link(meshes['Part044'], (62.85, *(motor_yz+pickup)), (62.85, *(cradle_yz+pickup)), modulus)
    center = layout['eye_yaw']['pivot_mm'][:2]
    yaw_z = 116.
    pin_x = center[0]
    yaw_y = center[1] + layout['eye_yaw']['radius_mm']
    mean_angles = ((-8, 8), (-20, 20), (-20, 20))
    rows = {}
    for name, profile, radius, phase, span, (start, end) in zip(
        ('pitch', 'yaw_left', 'yaw_right'),
        (pitch, *(link(meshes['Part037'], (pin_x, yaw_y, yaw_z), (x, -25.5, yaw_z), modulus, (0, 0, 1))
                  for x in (-34, 34))),
        (pitch_radius, layout['eye_yaw']['radius_mm'], layout['eye_yaw']['radius_mm']), (pitch_phase, 90., 90.),
        (cradle_yz-motor_yz, *((x-pin_x, -25.5-yaw_y) for x in (-34, 34))),
        mean_angles, strict=True,
    ):
        arm = float(np.min(abs(levers(np.linspace(start, end, 161), radius, phase, unit(np.asarray(span))))))
        force = 40/arm
        rows[name] = {**profile, 'minimum_lever_mm': arm, 'force_at_0p04_Nm_N': force,
                      'compression_Euler_torque_Nm': arm*profile['pinned_Euler_load_N']/1000,
                      'elastic_error_deg_at_0p04_Nm': degrees(force*profile['compliance_mm_per_N']/arm),
                      'link_only_one_sided_lash_linearized_deg': degrees(profile['one_sided_clearance_on_2mm_pin_mm']/arm),
                      'pin_fit_alternative': pin_fit_alternative(span, radius, phase, (start, end), profile)}
    return rows


def assess(directory):
    data = json.loads((directory/'cad_parts.json').read_text())
    motion = data['motion_geometry']
    layout = motion['blink']
    shaft_y, shaft_z = layout['shaft_yz_mm']
    meshes = {name: tr.load_mesh(directory/'world'/f'{name}.stl') for name in (
        'Part037', 'Part044', 'Part048', 'Part053', 'Part054', 'Part055', 'Part056', 'Part057', 'Part060')}
    radius = float(meshes['Part048'].extents[1]/2)
    flat_top = []
    for x in CLAMPS_X_MM:
        polygons, matrix = section(meshes['Part048'], (x, shaft_y, shaft_z), (1, 0, 0))
        outline = np.asarray(polygons[0].exterior.coords)
        world = tr.transformations.transform_points(np.column_stack((outline, np.zeros(len(outline)))), matrix)
        flat_top.append(world[:, 2].max())
    flat_depth = radius + shaft_z - float(min(flat_top))
    servo_yz = np.array(layout['servo_yz_mm'])
    shaft_yz = np.array(layout['shaft_yz_mm'])
    phase = radians(layout['phase_deg'])
    arm = np.array([cos(phase), sin(phase)])
    ends = [(5.85, servo_yz, shaft_yz, layout['radius_mm']),
            *[(s*layout['link_x_mm'], LID_PIVOT_YZ_MM, shaft_yz, layout['lid_radius_mm']) for s in (-1, 1)]]
    modulus = 1450.
    profiles = [link(meshes[name], (x, *(a+r*arm)), (x, *(b+r*arm)), modulus)
                for name, (x, a, b, r) in zip(('Part056', 'Part057', 'Part060'), ends, strict=True)]
    angles = np.linspace(0., 91., 183)
    drive_arm, lid_arm = [min(abs(levers(angles, r, layout['phase_deg'], unit(a-b)))) for _, a, b, r in ends[:2]]
    return {'cad_sha256': data['source_sha256'], 'PETG_model_MPa': modulus, 'steel_model_E_G_MPa': [STEEL_E_MPA, STEEL_G_MPA],
            'scope': 'Quasi-static longitudinal link and shaft elasticity with fixed shaft bearings. Pin clearance is screened separately.',
            'shaft': {'diameter_mm': 2*radius, 'flat_depth_mm': flat_depth},
            'blink': {'drive_lid_minimum_lever_mm': [drive_arm, lid_arm], 'links': profiles,
                      'link_only_one_sided_lash_linearized_deg': [
                          degrees(profile['one_sided_clearance_on_2mm_pin_mm']/arm)
                          for profile, arm in zip(profiles, [drive_arm, lid_arm, lid_arm], strict=True)],
                      'pin_fit_alternative': [pin_fit_alternative(
                          a-b, r, layout['phase_deg'], (0., 91.), profile)
                          for (_, a, b, r), profile in zip(ends, profiles, strict=True)],
                      'one_sided_lash_deg_by_total_link_slack_mm': {
                          str(g): [degrees(g/drive_arm), degrees(g/lid_arm)] for g in (.2, .4, .8)},
                      'load_cases': blink_cases(layout, profiles, 2*radius, flat_depth),
                      'max_drive_compression_before_Euler_Nm': profiles[0]['pinned_Euler_load_N']*drive_arm/1000,
                      'max_lid_compression_before_Euler_Nm': min(
                          link['pinned_Euler_load_N'] for link in profiles[1:])*lid_arm/1000},
            'blink_flat_clamp': clamp_screen([meshes[f'Part05{i}'] for i in (3, 4, 5)], shaft_y,
                                             min(flat_top), radius, flat_depth),
            'eye_links': eye_cases(meshes, motion, modulus)}


def check_drag(layout):
    from blink import build, run

    cap, stroke, step = .085, .68, .000125
    nominal_xml = build(layout, cap, 1., step)
    result = []
    cases = [(0., 0.), (.25, .25)]
    for force in (.25, .5, 1.):
        cases.extend(((force, 0.), (0., force)))
    for force_left, force_right in cases:
        forces = [force_left, force_right]
        torques = np.array(forces)*LID_TOUCH_LEVER_M
        for mode in ('closing_touch', 'speed_dependent_drag') if any(forces) else ('intrinsic_drag_only',):
            impact = mode == 'closing_touch'
            window = (stroke-.14, stroke+.12, torques) if impact else None
            load = (0., 0.) if impact else torques
            outcome = run(nominal_xml, cap, stroke, cycles=4, lid_loads=load, closing_touch=window)
            result.append({'mode': mode, 'contact_force_per_lid_N': forces, 'equivalent_torque_per_lid_Nm': torques.tolist(),
                           'constant_torque_window_s': list(window[:2]) if impact else None,
                           'nominal_contact_lever_mm': LID_TOUCH_LEVER_M*1000, 'solver_step_s': step,
                           'torque_saturated': outcome['max_drive_torque_Nm'] >= cap, **outcome})
    # Legacy heavy-load sensitivity, separate from the routine-load cases.
    for dt in (step, step/2):
        stats = run(build(layout, cap, 1., dt), cap, stroke, cycles=4, lid_loads=(.04, .04))
        result.append({'mode': 'bilateral_overload_sensitivity', 'extra_drag_per_lid_Nm': [.04, .04], 'solver_step_s': dt,
                       'torque_saturated': stats['max_drive_torque_Nm'] >= cap, **stats})
    return result


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--dynamics', action='store_true', help='Also run the rigid-link MuJoCo drag sensitivity')
    args = parser.parse_args()
    report = assess(args.cad)
    if args.dynamics:
        layout = json.loads((args.cad/'cad_parts.json').read_text())['motion_geometry']['blink']
        report['rigid_pin_drag_cases'] = check_drag(layout)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
