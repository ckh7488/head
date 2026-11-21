"""Pitch stop impact-energy bounds from the installed R5 mass and motion."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from math import degrees, radians, sqrt
from pathlib import Path

import numpy as np
import trimesh

from b20_dynamics import GRAVITY, added_mass, load_bodies, x_rotation
from multibody import Mass, NECK_PIVOT, ballast_mass, cad_part_mass, combine, parallel_axis, pos


SHELL_PARTS = ('Part073', 'Part074', 'Jaw_30_moving_jaw')
TOUCH_N = 1.
TOUCH_SECONDS = .15
PITCH_PROFILE_SPEED = 19*.229*6
UNCERTAINTY_SPEED = 45.


def linear_impact(energy_j, lever_mm, compliance_mm_per_n, closing_torque_nm):
    """Convert incident energy to elastic stop travel and force."""
    if energy_j < 0 or min(lever_mm, compliance_mm_per_n) <= 0 or closing_torque_nm < 0:
        raise ValueError('Impact geometry, compliance and driving work must be physical')
    sustained = 1000.*closing_torque_nm/lever_mm
    force = sustained+sqrt(sustained**2+2000.*energy_j/compliance_mm_per_n)
    travel = force*compliance_mm_per_n
    return {'peak_contact_force_N': force, 'compression_mm': travel,
            'additional_rotation_deg': degrees(travel/lever_mm)}


def posed_jaw(jaw, pivot, angle):
    rotation = x_rotation(radians(angle))
    return Mass(jaw.mass, pivot+rotation@(jaw.center-pivot), rotation@jaw.inertia@rotation.T)


def outer_radius(cad, pivot, jaw_angle):
    sizes = {}
    witnesses = {}
    for name in SHELL_PARTS:
        verts = pos(trimesh.load_mesh(cad/'world'/f'{name}.stl').vertices)
        if name == SHELL_PARTS[-1]:
            verts = pivot+(verts-pivot)@x_rotation(radians(jaw_angle)).T
        radii = np.linalg.norm((verts-NECK_PIVOT)[:, 1:], axis=1)
        maximum = radii.argmax()
        sizes[name] = float(radii[maximum])
        witnesses[name] = (1000.*verts[maximum]).tolist()
    return sizes, witnesses


def pulse_trace(mass, center, inertia, release, target, other_stop, speed, touch_torque):
    direction = np.sign(target-other_stop)
    initial = np.linspace(*release, round(np.degrees(release[1]-release[0])/.125)+1)
    delays = np.array((0., .05, .10, .15, .20, .30)) if touch_torque else np.zeros(1)
    q = np.broadcast_to(initial, (len(delays), len(initial))).copy()
    v = np.full_like(q, direction*speed)
    best_energy, best_start = 0., None
    dt = .0005

    def acceleration(angle, torque):
        return (mass*GRAVITY[2]*(center[1]*np.cos(angle)-center[2]*np.sin(angle))+torque)/inertia

    active = np.ones(q.shape, dtype=bool)
    for step in range(round(1.20/dt)):
        if not active.any():
            break
        time = (step+.5)*dt
        torque = direction*touch_torque*((delays <= time)&(time < delays+TOUCH_SECONDS))[:, None]
        a = acceleration(q, torque)
        next_q = q+dt*v+.5*dt*dt*a
        next_v = v+.5*dt*(a+acceleration(next_q, torque))
        hit = active & (direction*(next_q-target) >= 0.)
        if hit.any():
            part_step = (target-q[hit])/(next_q[hit]-q[hit])
            hit_v = v[hit]+part_step*(next_v[hit]-v[hit])
            impacts = .5*inertia*hit_v**2
            best = impacts.argmax()
            if impacts[best] >= best_energy:
                impact_row, impact_column = np.argwhere(hit)[best]
                best_energy = float(impacts[best])
                best_start = {'release_deg': float(np.degrees(initial[impact_column])),
                              'touch_delay_s': float(delays[impact_row]) if touch_torque else None,
                              'impact_after_s': float((step+part_step[best])*dt)}
        active &= ~(hit | (direction*(next_q-other_stop) <= 0.))
        q = np.where(active, next_q, q)
        v = np.where(active, next_v, v)
    return {'peak_energy_J': best_energy, 'peak_start': best_start,
            'peak_angular_speed_deg_s': float(np.degrees(sqrt(2.*best_energy/inertia)))}


def moving_link(record, link, cad, sliced, limits):
    strap = cad_part_mass(record, cad, sliced)
    lower, upper = pos(link['pan_pin_mm']), pos(link['head_pin_mm'])
    pivot_to_pin = upper-NECK_PIVOT
    offset = strap.center-lower
    span = upper-lower
    neutral = np.arctan2(span[2], span[1])
    samples = np.linspace(*limits, 501)
    chords = [NECK_PIVOT+x_rotation(angle)@pivot_to_pin-lower for angle in samples]
    angles = [np.arctan2(chord[2], chord[1])-neutral for chord in chords]
    heights = np.array([(x_rotation(angle)@offset)[2] for angle in angles])
    step = samples[1]-samples[0]
    upper_speed = np.linalg.norm(pivot_to_pin[1:])
    min_span = min(np.linalg.norm(chord) for chord in chords)-upper_speed*step*.5
    velocity_ratio = upper_speed/min_span
    inertia = (strap.inertia+strap.mass*parallel_axis(offset))[0, 0]
    torque = -strap.mass*GRAVITY[2]*np.linalg.norm(offset[1:])*velocity_ratio
    return {'mass_kg': strap.mass, 'gravity_energy_upper_J': -strap.mass*GRAVITY[2]*np.ptp(heights)+torque*step,
            'gravity_torque_upper_Nm': torque, 'effective_pitch_inertia_upper_kg_m2': inertia*velocity_ratio**2}


def stop_cases(body, radius, release, stops, strap, include_traces):
    mass, center = body.mass, body.center-NECK_PIVOT
    inertia_tensor = body.inertia+mass*parallel_axis(center)
    inertia = inertia_tensor[0, 0]
    mg = -mass*GRAVITY[2]

    def potential(q):
        return mg*(center[1]*np.sin(q)+center[2]*np.cos(q))

    def torque(q):
        return -mg*(center[1]*np.cos(q)-center[2]*np.sin(q))

    touch_torque = TOUCH_N*radius
    domain = np.linspace(*stops, 181)
    stationary = np.arctan2(center[1], center[2])+np.pi*np.arange(-1, 2)
    peak_release_potential = max(potential(np.r_[release, stationary[(release[0] < stationary)&(stationary < release[1])]]))
    result = {'mass_kg': mass, 'center_relative_to_axis_mm': (1000.*center).tolist(),
              'axis_inertia_kg_m2': inertia, 'inertia_about_pivot_kg_m2': inertia_tensor.tolist(),
              'maximum_gravity_torque_Nm': max(abs(torque(domain))),
              'stops': {}}
    for label, target, opposite in (('negative', stops[0], stops[1]), ('positive', stops[1], stops[0])):
        direction = np.sign(target-opposite)
        cases = {}
        for condition, starting_speed in (('rest', 0.), ('profile_cutoff', PITCH_PROFILE_SPEED),
                                          ('speed_sensitivity', UNCERTAINTY_SPEED)):
            speed = radians(starting_speed)
            initial_energy = .5*inertia*speed*speed
            passive_energy = initial_energy+max(0., peak_release_potential-potential(target))
            if strap:
                passive_energy += strap['gravity_energy_upper_J']+.5*strap['effective_pitch_inertia_upper_kg_m2']*speed**2
            # The finite pulse cannot do more pitch work than its torque times the full physical stroke.
            touch_bound = passive_energy+touch_torque*(stops[1]-stops[0])
            case = {'initial_speed_deg_s': starting_speed,
                    'gravity_and_initial_energy_upper_J': passive_energy,
                    'with_touch_energy_upper_J': touch_bound}
            if include_traces:
                case['no_touch_simulation'] = pulse_trace(mass, center, inertia, release, target, opposite, speed, 0.)
                case['one_newton_simulation'] = pulse_trace(mass, center, inertia, release, target, opposite,
                                                           speed, touch_torque)
            cases[condition] = case
        result['stops'][label] = {'angle_deg': float(np.degrees(target)),
                                   'closing_gravity_torque_Nm': max(0., direction*torque(target)),
                                   'signed_gravity_torque_Nm': torque(target), 'cases': cases}
    return result


def peak_energy(rows):
    maxima = {}
    for direction in ('negative', 'positive'):
        maxima[direction] = {}
        for condition in ('rest', 'profile_cutoff', 'speed_sensitivity'):
            cases = [row['stops'][direction]['cases'][condition] for row in rows.values()]
            result = {
                'gravity_and_initial_energy_upper_J': max(case['gravity_and_initial_energy_upper_J']
                                                          for case in cases),
                'with_touch_energy_upper_J': max(case['with_touch_energy_upper_J'] for case in cases)}
            if 'one_newton_simulation' in cases[0]:
                result['with_touch_simulated_peak_J'] = max(case['one_newton_simulation']['peak_energy_J']
                                                            for case in cases)
            maxima[direction][condition] = result
    return maxima


def report(cad, grams_file, release_deg, stops_deg, include_traces=True):
    manifest = json.loads((cad/'cad_parts.json').read_text())
    sliced = json.loads(grams_file.read_text())
    release, stops = np.radians(release_deg), np.radians(stops_deg)
    if not stops[0] < release[0] < release[1] < stops[1]:
        raise ValueError('The powered pitch interval must fit inside the stop interval')
    strap_record = next((part for part in manifest['parts'] if part['name'] == 'PitchLimitLink'), None)
    strap = {}
    if strap_record:
        link = manifest['motion_geometry']['pitch_stop']['link']
        strap = moving_link(strap_record, link, cad, sliced, stops)
        manifest['parts'] = [part for part in manifest['parts'] if part is not strap_record]
    (_, head, jaw), tray, accounting = load_bodies(manifest, cad, sliced)
    jaw_pivot = pos(manifest['jaw_pivot_mm'])
    setup = manifest['motion_geometry'].get('ballast', {'maximum_plates': 0})
    max_plates = setup['maximum_plates'] if tray is not None else 0
    rows = {}
    exterior = {phase: outer_radius(cad, jaw_pivot, phase) for phase in (0., 8.)}
    perturbation = added_mass(.075, (0., -70., 45.))
    plate_counts = (0, max_plates) if max_plates else (0,)
    plates_to_simulate = ((plates, forward) for plates in plate_counts for forward in (False, True))
    for plates, forward in plates_to_simulate:
        key = f'plates-{plates}'+('-forward-75g' if forward else '')
        for angle, (radii, witnesses) in exterior.items():
            parts = [head, posed_jaw(jaw, jaw_pivot, angle)]
            if plates:
                parts.extend((tray, ballast_mass(setup, plates)))
            if forward:
                parts.append(perturbation)
            body = combine(parts)
            exposed_part = max(radii, key=radii.get)
            load = stop_cases(body, radii[exposed_part], release, stops, strap, include_traces)
            rows[f'{key}-jaw-{angle:g}'] = {**load, 'touch_point_mm': witnesses[exposed_part]}
    nominal = {name: row for name, row in rows.items() if name.startswith('plates-0-jaw-')}
    forward = {name: row for name, row in rows.items() if name.startswith('plates-0-forward-75g-')}
    return {
        'cad_sha256': manifest['source_sha256'], 'sliced_grams_sha256': sha256(grams_file.read_bytes()).hexdigest(),
        'command_pitch_deg': release_deg, 'mechanical_stop_pitch_deg': stops_deg,
        'pitch_axis_mm': (NECK_PIVOT*1000.).tolist(), 'touch_force_N': TOUCH_N,
        'touch_duration_s': TOUCH_SECONDS, 'moving_strap': strap,
        'installed_head_plus_jaw_g': 1000.*(head.mass+jaw.mass),
        'installed_stop_parts_g': {name: accounting[name]['mass_g']
                                   for name in ('Part011', 'Part019', 'PitchLimitLowerPin', 'PitchLimitUpperPin')
                                   if name in accounting},
        'exterior_levers_m_at_jaw_deg': {phase: radii for phase, (radii, _) in exterior.items()},
        'scope': 'One inertially fixed jaw at each end of its stroke, level fixed carrier, no hinge friction or damping. '
                 'Touch acts tangentially at the furthest exterior lever toward target. '
                 'Touch and power cutoff samples provide sensitivity. '
                 'Full-stroke force work and separate strap energy give upper bounds.',
        'cases': rows, 'maximum': peak_energy(rows),
        'nominal_no_ballast_maximum': peak_energy(nominal), 'forward_75g_sensitivity_maximum': peak_energy(forward),
        'maximum_fitted_ballast_plates': max_plates,
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('sliced_grams', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--command-angles', nargs=2, type=float, default=(-15., 6.))
    parser.add_argument('--stop-angles', nargs=2, type=float, default=(-16.7, 7.5))
    parser.add_argument('--bounds-only', action='store_true')
    args = parser.parse_args()
    result = report(args.cad, args.sliced_grams, args.command_angles, args.stop_angles, not args.bounds_only)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
