"""Evaluate gravity and firmware-profile loads routed through the neck and jaw."""

from argparse import ArgumentParser
from hashlib import file_digest
from itertools import product
import json
from math import sqrt
from pathlib import Path
import re

import FreeCAD as App
import numpy as np
from scipy.spatial import ConvexHull
import trimesh

from b20_dynamics import (GRAVITY, UPPER_FRICTION, capacity, load_bodies, motor_parameters,
                          wrench_summary, x_rotation)
from b20_neck_joint import dimensions, evaluate, section_properties
from b22_drive import FIRMWARE, jaw_config
from export_cad import world_mesh, world_shape
from multibody import NECK_PIVOT, YAW_PIVOT, pos

AXIS_X = np.array([1., 0., 0.])
AXIS_Z = np.array([0., 0., 1.])
DAMPING_NM_PER_RAD_S = np.array([.012, .009, .0011])


def digest(path):
    with path.open('rb') as file:
        return file_digest(file, 'sha256').hexdigest()


def datums(assembly, cad, grams, jaw_pivot):
    doc = App.openDocument(str(assembly.resolve()))

    def shape(name):
        return world_shape(doc.getObject(name))

    try:
        ring = shape('Part006')
        rotor = shape('Part007')
        motor = shape('Part017')
        jaw_bearing = shape('Jaw_MR104ZZ_jaw_right').BoundBox
        jaw_motor = shape('Jaw_XL330_M288_Jaw')
        jaw_pin = shape('Jaw_Pin_jaw_4x10').BoundBox
        jaw_arm = world_mesh(doc.getObject('Jaw_39_right_jaw_pivot_arm')).BoundBox
        jaw = world_mesh(doc.getObject('Jaw_30_moving_jaw'))
        rotor_pilot = max(f.Surface.Radius for f in rotor.Faces if f.Surface.__class__.__name__ == 'Cylinder'
                          and f.BoundBox.ZMin < -45. and 35. < f.Surface.Radius < 40.)
        jaw_output = jaw_motor.BoundBox.XMin
        jaw_lever = max(np.linalg.norm(np.array([v.Vector.y, v.Vector.z])*.001 - jaw_pivot[1:])
                        for v in jaw.Points)
        screw_centers = [shape(f'JawHornScrew{i}').BoundBox.Center for i in range(2)]
        screw_span = (screw_centers[1] - screw_centers[0]).Length
        shim = doc.getObject('YawInnerRaceShim')
        skull = [world_mesh(doc.getObject(name)) for name in ('Part073', 'Part074')]
        top_z = max(mesh.BoundBox.ZMax for mesh in skull)
        shell_yaw_lever = max(np.hypot(p.Vector.x, p.Vector.y)*.001 for mesh in skull for p in mesh.Points)
        shell_pitch_lever = max(np.hypot(p.Vector.y*.001-NECK_PIVOT[1], p.Vector.z*.001-NECK_PIVOT[2])
                               for mesh in skull for p in mesh.Points)
        yaw_horn_holes = [f.Surface.Center for f in motor.Faces if f.Surface.__class__.__name__ == 'Cylinder'
                          and abs(f.Surface.Axis.z) > .999 and abs(f.Surface.Radius-1.) < 1e-5
                          and abs(f.Surface.Center.z+37.9) < 1e-5 and abs(f.BoundBox.ZMin+41.4)<1e-5]
        radii = {round(np.hypot(point.x, point.y), 5) for point in yaw_horn_holes}
        if not yaw_horn_holes or radii != {8.}:
            raise ValueError('The force path must use the four Ø2 output screws on an 8 mm yaw radius')
        yaw = {
            'inner_ring_id_mm': 2.*min(f.Surface.Radius for f in ring.Faces
                                      if f.Surface.__class__.__name__ == 'Cylinder'),
            'rotor_pilot_od_mm': 2. * rotor_pilot,
            'direct_rotor_to_bearing_gap_mm': rotor.distToShape(ring)[0],
            'direct_rotor_to_motor_gap_mm': rotor.distToShape(motor)[0],
            'outer_capture_gap_mm': ring.distToShape(shape('YawBearingRetainer1'))[0],
            'horn_screw_arm_mm': min(radii),
            'has_modeled_inner_race_shim': shim is not None,
            'bearing_to_shim_gap_mm': ring.distToShape(world_shape(shim))[0] if shim else None,
            'rotor_to_shim_gap_mm': rotor.distToShape(world_shape(shim))[0] if shim else None,
        }
    finally:
        App.closeDocument(doc.Name)

    cup = trimesh.load_mesh(cad / 'world/Part000.stl')
    floor = cup.bounds[0, 2]
    contact = cup.vertices[np.isclose(cup.vertices[:, 2], floor, atol=2e-5), :2]
    hull = ConvexHull(contact)
    # Base cup only. Omitted fixed hardware is useful additional weight when inside this support hull.
    center = cup.center_mass[:2]
    support_radius = np.min(-hull.equations[:, 2])
    floor_faces = np.all(np.isclose(cup.triangles[:, :, 2], floor, atol=2e-5), axis=1)
    radius_mean = np.average(np.linalg.norm(cup.triangles_center[floor_faces, :2], axis=1),
                             weights=cup.area_faces[floor_faces])
    radius_max = np.linalg.norm(contact, axis=1).max()
    return {'yaw': yaw, 'head_top_z_mm': top_z, 'shell_touch_levers_m': [shell_yaw_lever, shell_pitch_lever], 'jaw': {
        'left_output_x_mm': jaw_output,
        'right_bearing_x_mm': jaw_bearing.Center.x,
        'bearing_width_mm': jaw_bearing.XLength,
        'steel_pin_diameter_mm': jaw_pin.YLength,
        'arm_axial_projected_overlap_mm': min(jaw_arm.XMax, jaw_pin.XMax) - max(jaw_arm.XMin, jaw_pin.XMin),
        'horn_screw_span_mm': screw_span,
        'maximum_touch_lever_m': jaw_lever,
    }, 'base': {
        'mass_g': grams['01_base_cup_b8'], 'plane_z_mm': floor,
        'inscribed_support_radius_about_yaw_axis_mm': support_radius, 'cup_com_xy_mm': center.tolist(),
        'support_area_mm2': hull.volume, 'floor_outer_radius_mm': radius_max,
        'floor_uniform_pressure_mean_radius_mm': radius_mean,
    }}


def joint_wrenches(bodies, jaw_pivot, pitch, jaw, velocity, acceleration):
    # All samples are expressed in the instantaneous pan orientation with Z vertical.
    # A different pan angle rotates each output by the same angle.
    yaw_omega = velocity[:, 0, None] * AXIS_Z
    yaw_alpha = acceleration[:, 0, None] * AXIS_Z
    axis_rate = velocity[:, 0, None] * np.cross(AXIS_Z, AXIS_X)
    head_rotate = x_rotation(pitch)
    head_omega = yaw_omega + velocity[:, 1, None] * AXIS_X
    head_alpha = yaw_alpha + acceleration[:, 1, None] * AXIS_X + velocity[:, 1, None] * axis_rate
    yaw_arm = NECK_PIVOT - YAW_PIVOT
    head_acceleration = np.cross(yaw_alpha, yaw_arm) + np.cross(yaw_omega, np.cross(yaw_omega, yaw_arm))
    jaw_arm = head_rotate @ (jaw_pivot - NECK_PIVOT)
    jaw_acceleration = head_acceleration + np.cross(head_alpha, jaw_arm) + np.cross(head_omega, np.cross(head_omega, jaw_arm))
    jaw_rotate = x_rotation(pitch + jaw)
    yaw_body, head_body, jaw_body = bodies

    def wrench(body, rotation, spin, angular_accel, local_center, pivot_accel):
        offset = rotation @ local_center
        center_accel = pivot_accel + np.cross(angular_accel, offset) + np.cross(spin, np.cross(spin, offset))
        force = body.mass * (center_accel - GRAVITY)
        inertia = rotation @ body.inertia @ rotation.T
        moment = angular_accel @ inertia.T + np.cross(spin, spin @ inertia.T) + np.cross(offset, force)
        return force, moment

    jaw_force, jaw_moment = wrench(
        jaw_body, jaw_rotate, head_omega + velocity[:, 2, None] * AXIS_X,
        head_alpha + acceleration[:, 2, None] * AXIS_X + velocity[:, 2, None] * axis_rate,
        jaw_body.center - jaw_pivot, jaw_acceleration)
    head_force, head_moment = wrench(
        head_body, head_rotate, head_omega, head_alpha, head_body.center - NECK_PIVOT, head_acceleration)
    head_force += jaw_force
    head_moment += jaw_moment + np.cross(jaw_arm, jaw_force)
    yaw_force, yaw_moment = wrench(
        yaw_body, np.eye(3), yaw_omega, yaw_alpha, yaw_body.center - YAW_PIVOT, np.zeros(3))
    yaw_force += head_force
    yaw_moment += head_moment + np.cross(yaw_arm, head_force)
    return np.stack((yaw_force, head_force, jaw_force), axis=1), np.stack((yaw_moment, head_moment, jaw_moment), axis=1)


def near_end_speed(q, low, high, vmax, amax):
    return min(vmax, sqrt(2. * amax * max(0., min(q - low, high - q))))


def checks_by_mode(bodies, jaw_pivot, model, geometry):
    source = FIRMWARE.read_text()
    normal_speed, acceleration = (
        [int(x) for x in re.search(rf'\b{field}\[count\]\s*=\s*\{{([^}}]+)\}}', source)[1].split(',')[-3:]]
        for field in ('velocity', 'acceleration'))
    exhibit_speed = [int(re.search(rf'exhibit{axis}Velocity\s*=\s*(\d+)', source)[1]) for axis in ('Yaw', 'Pitch')]
    jaw_limit = jaw_config()[0]
    pitch_limits = model['motion_geometry']['pitch_stop']['powered_deg']
    touch_levers = [*geometry['shell_touch_levers_m'], geometry['jaw']['maximum_touch_lever_m']]
    released_jaw_limit = model['motion_geometry']['jaw_stop']['released_clearance_deg']
    touch_height = .001*geometry['head_top_z_mm']
    cup = geometry['base']
    cup_weight = .00981 * cup['mass_g']
    cup_axial_moment = np.linalg.norm(cup['cup_com_xy_mm']) * .001 * cup_weight
    axes = np.array([AXIS_Z, AXIS_X, AXIS_X])
    positive_pitch_coupler = 'pitch_coupler' in model['motion_geometry']
    supply = (10.62, 10.62, 4.5) if positive_pitch_coupler else (11.1, 11.1, 5.)
    pwm = np.array([int(x) for x in re.search(r'\bpwm\[count\]\s*=\s*\{([^}]+)\}', source)[1].split(',')[-3:]]) / 885.
    warm = motor_parameters(supply, .55)
    results = {}
    for mode, speed_register, active in (
        ('exhibit_tracking', [*exhibit_speed, 0], [True, True, False]),
        ('commissioning_neck', [*normal_speed[:2], 0], [True, True, False]),
        ('jaw_demo_centered_neck', [0, 0, normal_speed[-1]], [False, False, True]),
    ):
        vmax = np.array(speed_register) * .229 * 6.
        amax = np.array(acceleration) * .1 * 214.577 * active
        peak = np.zeros((3, 4))
        peak_torque = np.zeros(3)
        min_margin = np.full(3, np.inf)
        signed_yaw_axial = [np.inf, -np.inf]
        ring_load_min = np.inf
        floor_friction = 0.
        floor_twist_friction = 0.
        floor_uniform_combined_friction = 0.
        floor_stability = np.inf
        floor_friction_touch = 0.
        ring_compression_touch = np.inf
        floor_moment = 0.
        sample_count = 0
        for pitch, jaw in product(np.linspace(*pitch_limits, 81) if active[1] else [0.],
                                  np.linspace(0., jaw_limit, 61) if active[2]
                                  else np.linspace(0., released_jaw_limit, 5)):
            speed_max = np.array([vmax[0],
                                  near_end_speed(pitch, *pitch_limits, vmax[1], amax[1]),
                                  near_end_speed(jaw, 0., jaw_limit, vmax[2], amax[2])])
            speeds = [(0.,) if v < 1e-12 else (-v, 0., v) for v in speed_max]
            acceleration_choices = [(-a, 0., a) if a else (0.,) for a in amax]
            velocities, accelerations = np.radians(np.array(
                list(product(product(*speeds), product(*acceleration_choices))))).transpose(1, 0, 2)
            forces, moments = joint_wrenches(bodies, jaw_pivot, *np.radians([pitch, jaw]), velocities, accelerations)
            axial = np.einsum('nij,ij->ni', forces, axes)
            drive = np.einsum('nij,ij->ni', moments, axes)
            radial = np.linalg.norm(forces - axial[:, :, None] * axes, axis=2)
            bend = np.linalg.norm(moments - drive[:, :, None] * axes, axis=2)
            peak = np.maximum(peak, np.stack((abs(drive), radial, abs(axial), bend), axis=2).max(axis=0))
            torque = drive + DAMPING_NM_PER_RAD_S * velocities
            demand = abs(torque) + UPPER_FRICTION * active
            peak_torque = np.maximum(peak_torque, demand.max(axis=0))
            min_margin = np.minimum(min_margin, (capacity(warm, velocities, torque, pwm=pwm) - demand).min(axis=0))
            yaw_axial, yaw_bend, yaw_radial = axial[:, 0], bend[:, 0], radial[:, 0]
            signed_yaw_axial = [min(signed_yaw_axial[0], yaw_axial.min()), max(signed_yaw_axial[1], yaw_axial.max())]
            ring_load_min = min(ring_load_min, (yaw_axial/2. - yaw_bend/.080).min())
            weight = yaw_axial + cup_weight
            sliding = yaw_radial / weight
            floor_friction = max(floor_friction, sliding.max())
            floor_twist_friction = max(floor_twist_friction,
                                       (abs(moments[:, 0, 2])/(weight*.001*cup['floor_outer_radius_mm'])).max())
            uniform_twist = abs(moments[:, 0, 2])/(weight*.001*cup['floor_uniform_pressure_mean_radius_mm'])
            floor_uniform_combined_friction = max(floor_uniform_combined_friction, (sliding+uniform_twist).max())
            floor_friction_touch = max(floor_friction_touch, ((yaw_radial+1.)/weight).max())
            ring_compression_touch = min(ring_compression_touch,
                                         (yaw_axial/2. - (yaw_bend+touch_height-YAW_PIVOT[2])/.080).min())
            floor_arm = YAW_PIVOT - np.array([0., 0., .001*cup['plane_z_mm']])
            rocking = np.linalg.norm((moments[:, 0] + np.cross(floor_arm, forces[:, 0]))[:, :2], axis=1)
            floor_moment = max(floor_moment, rocking.max())
            radial_limit = .001*cup['inscribed_support_radius_about_yaw_axis_mm']
            floor_stability = min(floor_stability, (weight * radial_limit - rocking - cup_axial_moment).min())
            sample_count += len(velocities)
        result = {
            'samples': sample_count, 'moving_motor_axes': active,
            'warm_supply_V_by_axis': supply, 'pwm_duty_by_axis_for_active_axes': pwm.tolist(),
            'velocity_cap_deg_s': vmax.tolist(), 'acceleration_cap_deg_s2': amax.tolist(),
            'joint_peaks': {name: dict(zip(('drive_Nm', 'radial_N', 'axial_N', 'cross_axis_bend_Nm'), rp.tolist()))
                            for name, rp in zip(('yaw', 'pitch', 'jaw'), peak, strict=True)},
            'warm_peak_motor_demand_Nm': peak_torque.tolist(),
            'warm_min_motor_margin_Nm': [float(m) if mode_enabled else None
                                        for m, mode_enabled in zip(min_margin, active, strict=True)],
            'yaw_signed_axial_N': signed_yaw_axial,
            'min_two_point_yaw_ring_compression_N': ring_load_min,
            'floor_peak_rocking_moment_Nm': floor_moment,
            'floor_min_flat_rocking_margin_Nm': floor_stability,
            'light_touch_min_flat_rocking_margin_Nm': floor_stability - (touch_height-.001*cup['plane_z_mm']),
            'floor_min_mu_for_translation': floor_friction,
            'floor_mu_necessary_for_twist': floor_twist_friction,
            'floor_mu_screen_with_uniform_pressure_and_combined_motion': floor_uniform_combined_friction,
            'light_touch_floor_min_mu_for_translation': floor_friction_touch,
            'light_touch_min_yaw_ring_compression_N': ring_compression_touch,
            'one_newton_external_torque_upper_Nm_by_axis': touch_levers,
            'one_newton_warm_margin_lower_Nm_by_axis': [float(m - lever) if enabled else None
                      for m, lever, enabled in zip(min_margin, touch_levers, active, strict=True)],
            'yaw_horn_equal_torque_share_N_per_screw':
                1000.*peak_torque[0]/(4.*geometry['yaw']['horn_screw_arm_mm']),
        }
        results[mode] = result
    return results


def audit(assembly, cad, grams):
    model = json.loads((cad/'cad_parts.json').read_text())
    cad_hash = digest(assembly)
    if model['source_sha256'] != cad_hash:
        raise ValueError('Native CAD and world export hashes disagree.')
    weights = json.loads(grams.read_text())
    bodies, _, _ = load_bodies(model, cad, weights)
    jaw_pivot = pos(model['jaw_pivot_mm'])
    geometry = datums(assembly, cad, weights, jaw_pivot)
    peak_modes = checks_by_mode(bodies, jaw_pivot, model, geometry)
    pitch = dimensions(assembly)
    positive_pitch_coupler = model['motion_geometry'].get('pitch_coupler')
    if positive_pitch_coupler:
        pitch['horn_axis_x_mm'] = positive_pitch_coupler['m3_seat_mm'][0]
    section = section_properties(pitch)
    pitch_load = {}
    for name, mode in peak_modes.items():
        rp = mode['joint_peaks']['pitch']
        loads = wrench_summary([tuple(rp.values())])
        # Upstream friction passes through the linkage. Use it as an upper load bound.
        loads['pitch_torque_Nm'] = mode['warm_peak_motor_demand_Nm'][1]
        pitch_load[name] = evaluate(pitch, section, loads)
        if positive_pitch_coupler:
            del pitch_load[name]['D_flat']
    if positive_pitch_coupler:
        del pitch['d_flat_interface']
        pitch['d_flat_insertion_length_mm'] = pitch.pop('d_flat_axial_bond_length_mm')
    geometry_jaw = geometry['jaw']
    jaw_fixture = {}
    span_mm = geometry_jaw['right_bearing_x_mm'] - geometry_jaw['left_output_x_mm']
    for mode, outcome in peak_modes.items():
        peak = outcome['joint_peaks']['jaw']
        # Jaw pivots about the common X axis. Allocate a separate resultant bending bound to each support.
        span = span_mm * .001
        right_force = -geometry_jaw['left_output_x_mm']/span_mm * peak['radial_N'] + peak['cross_axis_bend_Nm']/span
        left_force = geometry_jaw['right_bearing_x_mm']/span_mm * peak['radial_N'] + peak['cross_axis_bend_Nm']/span
        pin_d = geometry_jaw['steel_pin_diameter_mm']
        pin_length = geometry_jaw['arm_axial_projected_overlap_mm']
        jaw_fixture[mode] = {'support_span_mm': span_mm, 'left_radial_bound_N': left_force,
                             'right_radial_bound_N': right_force,
                             'right_pin_projected_bearing_MPa': right_force/(pin_d*pin_length),
                             'all_axial_to_one_support_bound_N': peak['axial_N'],
                             'horn_screw_pair_tangential_N_per_screw':
                                 outcome['warm_peak_motor_demand_Nm'][2]*1000./geometry_jaw['horn_screw_span_mm']}
    return {'cad_sha256': cad_hash, 'sliced_grams_sha256': digest(grams),
            'firmware_sha256': digest(FIRMWARE), 'moving_mass_g': [1000.*b.mass for b in bodies],
            'moving_com_mm': [list(b.center*1000.) for b in bodies],
            'geometry': geometry, 'pitch_geometry': pitch, 'pitch_loads': pitch_load,
            'pitch_coupling': 'positive_M3' if positive_pitch_coupler else 'bonded_D_flat',
            'modes': peak_modes, 'jaw_fixture': jaw_fixture,
            'scope': 'Gravity and firmware-profile load screen. Nominal axes use no external contact. '
                     'Sampled conservative velocity/acceleration sign combinations, not cycle certification. '
                     'Manufacturer stall model scaled to 55 percent with upper friction, unmeasured. '
                     'Light touch is a separate static load sensitivity. '
                     'Actual gear play, fit, thermal and screw preload require hardware. '
                     'For the positive pitch joint use the separate holder and drive screw strength report.'}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('assembly', type=Path)
    parser.add_argument('cad', type=Path)
    parser.add_argument('grams', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = audit(args.assembly, args.cad, args.grams)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
