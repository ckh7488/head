"""Coupled neck-pitch and jaw power loss with elastic end stops."""

from argparse import ArgumentParser
from hashlib import sha256
from itertools import product
import json
from math import radians
from pathlib import Path
import sys

import numpy as np

from b20_dynamics import JAW_PROFILE_SPEED, load_bodies
from multibody import NECK_PIVOT, pos


STEP_S = .0004
DURATION_S = .75
MAX_ENERGY_DRIFT_J = .00008
PITCH_BINS_DEG = (None, 0., 4.5, 5.5, 6.5, 6.9, 7., None)


def jaw_parameters(report):
    trials = report.get('compound_contact_trials') or report['contact_trials']
    first_contact = max(row['first_contact_deg'] for row in trials)
    lever = report['gravity_drop']['minimum_contact_lever_mm']
    compliance = max(row['compliance_mm_per_N_at_1000_MPa'] for row in report['local_FE']['meshes'])
    return float(first_contact), float(lever*lever/(2000.*compliance))


def jaw_clearance_at_deflection(report, deflection):
    verified = [case for row in report.get('local_FE', {}).get('meshes', []) for case in row['impact_cases']
                if 'deflected_contact' in case and case['deflection_mm'] >= deflection]
    if not verified:
        return None
    chosen = min(verified, key=lambda case: case['deflection_mm'])
    return {'tested_retreat_mm': chosen['deflection_mm'],
            'latest_contact_deg': chosen['deflected_contact']['first_contact_deg']}


def measure_jaw_retreats(assembly, report, retreats):
    import FreeCAD as App

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from build_b21_jaw_stop import (B22_STOP, PIVOT_ARM, STAY, cad_mesh,
                                    deflected_contact, mesh_from_topology, stop_geometry, tessellate)

    document = App.openDocument(str(assembly.resolve()))
    try:
        stop_solid = stop_geometry(cad_mesh(document.getObject(STAY)), B22_STOP)
        stop = mesh_from_topology(tessellate(stop_solid))
        arm = cad_mesh(document.getObject(PIVOT_ARM))
        pivot = np.asarray(tuple(document.JawMotion.Placement.Base))
        trials = report['compound_contact_trials']
        neutral = deflected_contact(stop, arm, pivot, trials, 0.)
        expected = max(row['first_contact_deg'] for row in trials)
        if abs(neutral['first_contact_deg']-expected) > .004:
            raise ValueError('Assembled jaw geometry and measured stop pose disagree')
        return [{'normal_retreat_mm': retreat, **deflected_contact(stop, arm, pivot, trials, retreat)}
                for retreat in retreats]
    finally:
        App.closeDocument(document.Name)


def stop_parameters(layout, strength):
    contact = sorted(layout['motion_geometry']['pitch_stop']['stops'], key=lambda stop: stop['direction'])
    bounds = strength.get('bounds') or strength['structural']['nominal_no_ballast_maximum']
    linear = []
    for stop in contact:
        item = bounds[stop['id']]
        polymer = 2.*item['coupled_bearings_compliance_mm_per_N_at_1GPa']
        metal = item.get('steel_link', {}).get('incremental_axes_compliance_mm_per_N', 0.)
        linear.append(item['contact_lever_mm']**2/(1000.*(polymer+metal)))
    return np.asarray(linear)


def cutoff_state_grid(command, jaw_command, pitch_speed, jaw_speed):
    return np.asarray(list(product(np.linspace(*command, 81), np.linspace(0., jaw_command, 7),
                                   np.radians((-pitch_speed, 0., pitch_speed)),
                                   np.radians((-jaw_speed, 0., jaw_speed)))))


def passive_jaw_starts(command, jaw_limit, pitch_speed, jaw, jaw_axis):
    initial = np.asarray(list(product(np.linspace(*command, 81), np.linspace(0., jaw_limit, 7),
                                      np.radians((-pitch_speed, 0., pitch_speed)), (0.,))))
    pitch, opened = initial[:, :2].T
    y, z = (jaw.center-jaw_axis)[1:]
    inertia = jaw.inertia[0, 0]+jaw.mass*(y*y+z*z)
    drop = 9.81*jaw.mass*(y*(np.sin(pitch)-np.sin(pitch+opened))
                          +z*(np.cos(pitch)-np.cos(pitch+opened)))
    # This one-stroke envelope also allows 0.15 mJ of coupling work from powered pitch motion.
    speed = np.sqrt(2.*np.maximum(0., drop+.00015)/inertia)
    negative, positive = initial.copy(), initial.copy()
    negative[:, 3], positive[:, 3] = -speed, speed
    return np.concatenate((negative, initial, positive))


def sinusoid_max(moment, limits):
    angle = np.arctan2(moment[0], moment[1])+2.*np.pi*np.arange(-1, 2)
    sample = np.r_[limits, angle[(limits[0] < angle) & (angle < limits[1])]]
    return float(max(moment[0]*np.sin(sample)+moment[1]*np.cos(sample)))


def energy_jaw_bounds(potential_energy, head_moment, jaw_moment, pitch_limits, pitch_stiffness, jaw_limit,
                      jaw_stiffness, initial_energy, strap):
    outer = np.radians(90.)
    strap_torque = strap.get('gravity_torque_upper_Nm', 0.)
    available = initial_energy+strap.get('gravity_energy_upper_J', 0.)
    gravity_bound = 9.81*(np.linalg.norm(head_moment)+np.linalg.norm(jaw_moment))
    outer_travel = np.abs(np.asarray((-outer, outer))-pitch_limits)
    if np.min(.5*pitch_stiffness*outer_travel**2-strap_torque*outer_travel) <= available+gravity_bound:
        raise ValueError('The energy projection needs a wider pitch search range')
    curvature = gravity_bound+max(pitch_stiffness)
    bounds = []
    for a, b in zip(PITCH_BINS_DEG[:-1], PITCH_BINS_DEG[1:], strict=True):
        low = -outer if a is None else radians(a)
        high = outer if b is None else radians(b)
        pitch = np.linspace(low, high, int(np.ceil(np.degrees(high-low)/.025))+1)
        pitch = np.unique(np.r_[pitch, pitch_limits[(low < pitch_limits) & (pitch_limits < high)]])
        pitch_work = strap_torque*(np.maximum(0., pitch_limits[0]-pitch)+np.maximum(0., pitch-pitch_limits[1]))
        discretization = curvature*np.diff(pitch).max()**2/8.
        stopped = np.zeros(len(pitch))

        def lower_energy(jaw):
            poses = np.column_stack((pitch, np.full(len(pitch), jaw), stopped, stopped))
            return float(min(potential_energy(poses)-pitch_work))-discretization

        lo = jaw_limit+9.81*np.linalg.norm(jaw_moment)/jaw_stiffness
        hi = max(lo, radians(20.))
        if lower_energy(hi) <= available:
            raise ValueError('The energy projection needs a wider jaw search range')
        for _ in range(25):
            middle = .5*(lo+hi)
            if lower_energy(middle) > available:
                hi = middle
            else:
                lo = middle
        bounds.append({'pitch_range_deg': [a, b], 'energy_linear_jaw_bound_deg': float(np.degrees(hi))})
    return bounds


def energy_pitch_bounds(potential_energy, head_moment, jaw_moment, pitch_limits, pitch_stiffness, jaw_limit,
                        jaw_stiffness, initial_energy, strap):
    outer = radians(45.)
    strap_torque = strap.get('gravity_torque_upper_Nm', 0.)
    available = initial_energy+strap.get('gravity_energy_upper_J', 0.)
    gravity_bound = 9.81*(np.linalg.norm(head_moment)+np.linalg.norm(jaw_moment))
    if .5*jaw_stiffness*(outer-jaw_limit)**2 <= available+gravity_bound:
        raise ValueError('The energy projection needs a wider jaw search range')
    jaw = np.unique(np.r_[np.linspace(-outer, outer, 3601), 0., jaw_limit])
    curvature = 9.81*np.linalg.norm(jaw_moment)+jaw_stiffness
    discretization = curvature*np.diff(jaw).max()**2/8.
    stopped = np.zeros(len(jaw))
    result = {}
    for label, sign, limit, stiffness in zip(('back', 'forward'), (-1., 1.), pitch_limits, pitch_stiffness,
                                             strict=True):
        def lower_energy(extra):
            poses = np.column_stack((np.full(len(jaw), limit+sign*extra), jaw, stopped, stopped))
            return float(min(potential_energy(poses)))-discretization-strap_torque*extra

        lo, hi = (gravity_bound+strap_torque)/stiffness, radians(20.)
        if lo > hi or lower_energy(hi) <= available:
            raise ValueError('The energy projection needs a wider pitch search range')
        for _ in range(25):
            mid = .5*(lo+hi)
            if lower_energy(mid) > available:
                hi = mid
            else:
                lo = mid
        result[label] = {'extra_deg': float(np.degrees(hi)), 'absolute_deg': float(np.degrees(limit+sign*hi))}
    return result


def simulate(head, jaw, jaw_axis, strap, pitch_limits, pitch_stiffness, jaw_limit, jaw_stiffness,
             initial, powered_starts, step=STEP_S, duration=DURATION_S):
    gravity = 9.81
    head_center = (head.center-NECK_PIVOT)[1:]
    jaw_offset = (jaw_axis-NECK_PIVOT)[1:]
    jaw_center = (jaw.center-jaw_axis)[1:]
    head_moment = head.mass*head_center+jaw.mass*jaw_offset
    jaw_moment = jaw.mass*jaw_center
    head_inertia = (head.inertia[0, 0]+head.mass*(head_center@head_center)
                    +strap.get('effective_pitch_inertia_upper_kg_m2', 0.))
    jaw_inertia = jaw.inertia[0, 0]+jaw.mass*(jaw_center@jaw_center)
    base_inertia = head_inertia+jaw_inertia+jaw.mass*(jaw_offset@jaw_offset)

    def mass_terms(jaw_pitch):
        s, c = np.sin(jaw_pitch), np.cos(jaw_pitch)
        y = c*jaw_center[0]-s*jaw_center[1]
        z = s*jaw_center[0]+c*jaw_center[1]
        cross_term = jaw.mass*(jaw_offset[0]*y+jaw_offset[1]*z)
        rate = jaw.mass*(-jaw_offset[0]*z+jaw_offset[1]*y)
        return base_inertia+2.*cross_term, jaw_inertia+cross_term, rate

    def spring(pitch, jaw_pitch):
        pitch_delta = np.vstack((np.minimum(0., pitch-pitch_limits[0]), np.maximum(0., pitch-pitch_limits[1])))
        jaw_delta = np.vstack((np.minimum(0., jaw_pitch), np.maximum(0., jaw_pitch-jaw_limit)))
        return pitch_delta, jaw_delta

    def derivative(states):
        pitch, jaw_pitch, v, w = states.T
        pitch_inertia, joint_cross, rate = mass_terms(jaw_pitch)
        jaw_drive = -gravity*(jaw_moment[0]*np.cos(pitch+jaw_pitch)-jaw_moment[1]*np.sin(pitch+jaw_pitch))
        head_drive = -gravity*(head_moment[0]*np.cos(pitch)-head_moment[1]*np.sin(pitch))
        pitch_delta, jaw_delta = spring(pitch, jaw_pitch)
        pitch_spring_torque = pitch_stiffness[0]*pitch_delta[0]+pitch_stiffness[1]*pitch_delta[1]
        torque_pitch = head_drive+jaw_drive-pitch_spring_torque-rate*(2.*v*w+w*w)
        torque_jaw = jaw_drive-jaw_stiffness*jaw_delta.sum(axis=0)+rate*v*v
        det = pitch_inertia*jaw_inertia-joint_cross**2
        return np.stack((v, w, (jaw_inertia*torque_pitch-joint_cross*torque_jaw)/det,
                         (pitch_inertia*torque_jaw-joint_cross*torque_pitch)/det), axis=-1)

    def energy(states):
        pitch, jaw_pitch, v, w = states.T
        inertia, joint_cross, _ = mass_terms(jaw_pitch)
        kinetic = .5*inertia*v*v+joint_cross*v*w+.5*jaw_inertia*w*w
        potential = gravity*(head_moment[0]*np.sin(pitch)+head_moment[1]*np.cos(pitch)
                             +jaw_moment[0]*np.sin(pitch+jaw_pitch)+jaw_moment[1]*np.cos(pitch+jaw_pitch))
        pitch_delta, jaw_delta = spring(pitch, jaw_pitch)
        elastic = .5*(pitch_stiffness@(pitch_delta**2)+jaw_stiffness*(jaw_delta**2).sum(axis=0))
        return kinetic+potential+elastic

    state = initial.copy()
    base_energy = energy(state)
    initial_pitch_limits = initial[:, 0].min(), initial[:, 0].max()
    combined_angles = initial_pitch_limits[0], initial_pitch_limits[1]+jaw_limit
    maximum_closed_potential = 9.81*sinusoid_max(head_moment+jaw_moment, initial_pitch_limits)
    if sinusoid_max((-jaw_moment[1], jaw_moment[0]), combined_angles) <= 0.:
        turn = np.array([[np.cos(jaw_limit), -np.sin(jaw_limit)], [np.sin(jaw_limit), np.cos(jaw_limit)]])
        jaw_drop_ceiling = 9.81*sinusoid_max(jaw_moment-turn@jaw_moment, initial_pitch_limits)
        maximum_potential = maximum_closed_potential
    else:
        maximum_potential = 9.81*(sinusoid_max(head_moment, initial_pitch_limits)
                                  +sinusoid_max(jaw_moment, combined_angles))
        jaw_drop_ceiling = maximum_potential+gravity*(np.linalg.norm(head_moment)+np.linalg.norm(jaw_moment))
    cross_ceiling = jaw.mass*np.linalg.norm(jaw_offset)*np.linalg.norm(jaw_center)
    pitch_speed = float(max(abs(initial[:, 2])))
    jaw_powered_speed = float(max(abs(initial[:powered_starts, 3])))
    pitch_kinetic = .5*(base_inertia+2.*cross_ceiling)*pitch_speed**2
    coupling = (jaw_inertia+cross_ceiling)*pitch_speed
    powered_energy = maximum_potential+pitch_kinetic+coupling*jaw_powered_speed+.5*jaw_inertia*jaw_powered_speed**2
    passive_speed = np.sqrt(2.*max(0., jaw_drop_ceiling+.00015)/jaw_inertia)
    passive_energy = maximum_potential+.00015+pitch_kinetic+coupling*passive_speed
    energy_ceiling = float(max(max(base_energy), powered_energy, passive_energy))
    jaw_energy_by_pitch = energy_jaw_bounds(energy, head_moment, jaw_moment, pitch_limits, pitch_stiffness,
                                         jaw_limit, jaw_stiffness, energy_ceiling, strap)
    pitch_energy_bound = energy_pitch_bounds(energy, head_moment, jaw_moment, pitch_limits, pitch_stiffness,
                                             jaw_limit, jaw_stiffness, energy_ceiling, strap)
    worst = {sign: {'extra_rad': 0.} for sign in (-1, 1)}
    bin_edges = np.radians(PITCH_BINS_DEG[1:-1])
    bin_peaks = np.full(len(PITCH_BINS_DEG)-1, -np.inf)
    bin_witnesses = [None]*len(bin_peaks)
    drift = 0.
    maximum_jaw = 0.
    maximum_jaw_witness = None

    def witness(index, time):
        return {'time_s': time, 'initial_jaw_mode': 'powered' if index < powered_starts else 'passive',
                'initial_angle_and_speed_deg': np.degrees(initial[index]).tolist(),
                'peak_angle_and_speed_deg': np.degrees(state[index]).tolist()}

    for index in range(round(duration/step)):
        k1 = derivative(state)
        k2 = derivative(state+.5*step*k1)
        k3 = derivative(state+.5*step*k2)
        k4 = derivative(state+step*k3)
        state += step/6.*(k1+2.*k2+2.*k3+k4)
        time = (index+1)*step
        jaw_index = state[:, 1].argmax()
        if state[jaw_index, 1] > maximum_jaw:
            maximum_jaw = float(state[jaw_index, 1])
            maximum_jaw_witness = witness(jaw_index, time)
        pitch_bin = np.searchsorted(bin_edges, state[:, 0], side='right')
        gained = np.flatnonzero(state[:, 1] > bin_peaks[pitch_bin])
        for band in np.unique(pitch_bin[gained]):
            candidates = gained[pitch_bin[gained] == band]
            at = candidates[state[candidates, 1].argmax()]
            bin_peaks[band] = state[at, 1]
            bin_witnesses[band] = witness(at, time)
        if index % 32 == 0:
            drift = max(drift, float(np.max(np.abs(energy(state)-base_energy))))
        for sign, limit in zip((-1, 1), pitch_limits, strict=True):
            extra = sign*(state[:, 0]-limit)
            at = extra.argmax()
            if extra[at] > worst[sign]['extra_rad']:
                worst[sign] = {'extra_rad': float(extra[at]), **witness(at, time)}
    drift = max(drift, float(np.max(np.abs(energy(state)-base_energy))))
    regions = {}
    for label, sign, stiffness in zip(('back', 'forward'), (-1, 1), pitch_stiffness, strict=True):
        row = worst[sign]
        extra = row.pop('extra_rad')
        remaining_strap = (strap.get('gravity_energy_upper_J', 0.)+extra*strap.get('gravity_torque_upper_Nm', 0.))
        regions[label] = {**row,
                          'extra_deg': float(np.degrees(extra)),
                          'extra_with_strap_energy_and_integration_margin_deg':
                              float(np.degrees(np.sqrt(extra**2+2.*(remaining_strap+drift)/stiffness)))}
    jaw_margin = strap.get('gravity_energy_upper_J', 0.)+drift

    def marginal_jaw_travel(angle):
        return np.sqrt(max(0., angle-jaw_limit)**2+2.*jaw_margin/jaw_stiffness)

    jaw_arm_with_margin = marginal_jaw_travel(maximum_jaw)
    jaw_by_pitch = []
    for low, high, peak, row in zip(PITCH_BINS_DEG[:-1], PITCH_BINS_DEG[1:], bin_peaks, bin_witnesses, strict=True):
        jaw_by_pitch.append({'pitch_range_deg': [low, high], 'witness': row,
                             'raw_jaw_deg': float(np.degrees(peak)) if row else None,
                             'linear_jaw_with_margin_deg': float(np.degrees(jaw_limit+marginal_jaw_travel(peak)))
                             if row else None})
    return {'maximum_energy_drift_J': drift, 'arrest_directions': regions,
            'initial_energy_upper_J': energy_ceiling, 'energy_jaw_by_pitch_bin': jaw_energy_by_pitch,
            'energy_pitch_bound': pitch_energy_bound,
            'peak_linear_jaw_open_deg': float(np.degrees(maximum_jaw)),
            'peak_linear_jaw_open_with_margin_deg': float(np.degrees(jaw_limit+jaw_arm_with_margin)),
            'peak_jaw_elastic_travel_with_margin_deg': float(np.degrees(jaw_arm_with_margin)),
            'peak_jaw_witness': maximum_jaw_witness, 'jaw_by_pitch_bin': jaw_by_pitch}


def run(cad, grams, load_path, strength_path, jaw_path, jaw_contact=None, jaw_stiffness=None,
        jaw_assembly=None, jaw_powered_speed=JAW_PROFILE_SPEED):
    layout = json.loads((cad/'cad_parts.json').read_text())
    loads = json.loads(load_path.read_text())
    strength = json.loads(strength_path.read_text())
    jaw_stop = json.loads(jaw_path.read_text())
    digest = lambda path: sha256(path.read_bytes()).hexdigest()
    if layout['source_sha256'] != loads['cad_sha256'] or layout['source_sha256'] != strength['cad_sha256']:
        raise ValueError('Cutoff geometry, mass/load report and strength report must share the same CAD')
    if loads['sliced_grams_sha256'] != digest(grams):
        raise ValueError('The cutoff model must use the weighed parts from the load report')
    layout['parts'] = [record for record in layout['parts'] if record['name'] != 'PitchLimitLink']
    (_, head, jaw), _, _ = load_bodies(layout, cad, json.loads(grams.read_text()))
    command = np.radians(loads['command_pitch_deg'])
    limits = np.radians(loads['mechanical_stop_pitch_deg'])
    actual_jaw_command = float(layout['motion_geometry']['jaw_stop']['software_open_deg'])
    if jaw_contact is None or jaw_stiffness is None:
        first_contact, stiffness = jaw_parameters(jaw_stop)
        jaw_contact = first_contact if jaw_contact is None else jaw_contact
        jaw_stiffness = stiffness if jaw_stiffness is None else jaw_stiffness
    if not 0. < actual_jaw_command < jaw_contact or jaw_stiffness <= 0.:
        raise ValueError('The jaw command must stop before the first contact of its positive stiffness limit')
    jaw_pivot = pos(layout['jaw_pivot_mm'])
    passive = passive_jaw_starts(command, radians(jaw_contact), 45., jaw, jaw_pivot)
    if not 0. < jaw_powered_speed <= JAW_PROFILE_SPEED:
        raise ValueError('Powered jaw speed must be within the configured profile')
    powered = cutoff_state_grid(command, radians(actual_jaw_command), 45., jaw_powered_speed)
    initial = np.concatenate((powered, passive))
    stiffness_pitch = stop_parameters(layout, strength)
    strap = loads.get('moving_strap', {})
    lever = jaw_stop.get('gravity_drop', {}).get('minimum_contact_lever_mm')
    cases = []
    for jaw_scale in (1., 2., 3.6):
        for step in (STEP_S, STEP_S/2., STEP_S/4.):
            scale_result = simulate(head, jaw, jaw_pivot, strap, limits, stiffness_pitch,
                                    radians(jaw_contact), jaw_stiffness*jaw_scale, initial, len(powered), step)
            if scale_result['maximum_energy_drift_J'] <= MAX_ENERGY_DRIFT_J:
                break
        else:
            raise ValueError('The cutoff integration did not conserve energy within the specified tolerance')
        case = {'jaw_stiffness_Nm_rad': jaw_stiffness*jaw_scale, 'step_s': step, **scale_result}
        if lever is not None:
            retreat = lever*radians(case['peak_jaw_elastic_travel_with_margin_deg'])
            case['peak_jaw_stop_normal_retreat_mm'] = retreat
            case['jaw_geometry_calibration'] = jaw_clearance_at_deflection(jaw_stop, retreat)
        cases.append(case)
    maxima = {direction: max(case['arrest_directions'][direction]['extra_with_strap_energy_and_integration_margin_deg']
                             for case in cases) for direction in ('back', 'forward')}
    jaw_by_pitch = [max(band, key=lambda row: row['linear_jaw_with_margin_deg']
                        if row['linear_jaw_with_margin_deg'] is not None else -np.inf)
                    for band in zip(*(case['jaw_by_pitch_bin'] for case in cases), strict=True)]
    energy_by_pitch = [max(band, key=lambda row: row['energy_linear_jaw_bound_deg'])
                       for band in zip(*(case['energy_jaw_by_pitch_bin'] for case in cases), strict=True)]
    pitch_energy_bound = {direction: max((case['energy_pitch_bound'][direction] for case in cases),
                                         key=lambda row: row['extra_deg']) for direction in ('back', 'forward')}
    retest = None
    if jaw_assembly is not None:
        if digest(jaw_assembly) != layout['source_sha256']:
            raise ValueError('The deflection retest must use the same CAD assembly')
        if lever is None:
            raise ValueError('The deflection retest needs a measured jaw stop lever')
        retreat = max(case['peak_jaw_stop_normal_retreat_mm'] for case in cases)
        populated = [row for row in jaw_by_pitch if row['linear_jaw_with_margin_deg'] is not None]
        bin_retreats = [lever*radians(row['linear_jaw_with_margin_deg']-jaw_contact) for row in populated]
        energy_retreats = [lever*radians(row['energy_linear_jaw_bound_deg']-jaw_contact) for row in energy_by_pitch]
        retest, *bin_calibration = measure_jaw_retreats(jaw_assembly, jaw_stop,
                                                     [retreat, *bin_retreats, *energy_retreats])
        for row, calibration in zip(populated+energy_by_pitch, bin_calibration, strict=True):
            row['jaw_cad_calibration'] = calibration
    calibrated = (retest['first_contact_deg'] if retest else
                  max(case['jaw_geometry_calibration']['latest_contact_deg'] for case in cases)
                  if all(case.get('jaw_geometry_calibration') for case in cases) else None)
    frozen = strength.get('bounds') or strength['structural']['nominal_no_ballast_maximum']
    stops = sorted(layout['motion_geometry']['pitch_stop']['stops'], key=lambda stop: stop['direction'])
    reference = {label: frozen[stop['id']]['elastic_impacts']['gravity_only']['500.0']
                 ['with_coupled_unit_bearing_tractions']['additional_rotation_deg']
                 for label, stop in zip(('back', 'forward'), stops, strict=True)}
    return {'cad_sha256': layout['source_sha256'], 'grams_sha256': digest(grams),
            'load_sha256': digest(load_path), 'neck_strength_sha256': digest(strength_path),
            'jaw_stop_sha256': digest(jaw_path), 'solver_sha256': digest(Path(__file__)),
            'command_pitch_deg': loads['command_pitch_deg'],
            'late_pitch_contact_deg': loads['mechanical_stop_pitch_deg'],
            'jaw_powered_open_deg': actual_jaw_command, 'jaw_latest_contact_deg': jaw_contact,
            'joint_initial_speed_limits_deg_s': {'pitch': 45., 'jaw_powered': jaw_powered_speed},
            'starts_per_approximation': {'powered_jaw': len(powered), 'passive_jaw': len(passive)},
            'duration_s': DURATION_S,
            'frozen_jaw_reference_extra_deg': reference, 'coupled_maximum_extra_deg': maxima,
            'coupled_maximum_linear_jaw_open_deg': max(case['peak_linear_jaw_open_with_margin_deg'] for case in cases),
            'coupled_maximum_jaw_with_cad_calibration_deg': calibrated,
            'coupled_jaw_retreat_retest': retest,
            'coupled_jaw_maximum_by_pitch_bin': jaw_by_pitch,
            'energy_bounded_jaw_by_pitch_bin': energy_by_pitch,
            'energy_bounded_pitch_by_sign': pitch_energy_bound,
            'energy_bounded_pitch_extra_deg': {direction: row['extra_deg']
                                              for direction, row in pitch_energy_bound.items()},
            'cases': cases,
            'scope': 'Concurrent cutoff with no external contact and both modeled stops elastic. '
                     'The jaw closes against a spring with the same stiffness as its opening limit. '
                     'Yaw is held level and fixed. The sampled grid includes independent maximal powered axis speeds '
                     'and the free jaw speed available in one gravity stroke with additional pitch drive work. '
                     'The full bounded gravitational strap energy and integration drift are added as margin. '
                     'The all-time bounds project a continuous-initial-angle energy ceiling onto both '
                     'elastic joints, using a 0.025° minimum search and a curvature correction between samples. '
                     'The linear jaw angle uses the minimum measured lever. A calibrated angle uses the next '
                     'greater checked retreat of the exact jaw stop geometry when that evidence is available.'}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('grams', type=Path)
    parser.add_argument('loads', type=Path)
    parser.add_argument('strength', type=Path)
    parser.add_argument('jaw_stop', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--jaw-contact-deg', type=float)
    parser.add_argument('--jaw-stiffness-nm-rad', type=float)
    parser.add_argument('--jaw-assembly', type=Path)
    parser.add_argument('--jaw-powered-speed-deg-s', type=float, default=JAW_PROFILE_SPEED)
    args = parser.parse_args()
    result = run(args.cad, args.grams, args.loads, args.strength, args.jaw_stop,
                 args.jaw_contact_deg, args.jaw_stiffness_nm_rad, args.jaw_assembly, args.jaw_powered_speed_deg_s)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
