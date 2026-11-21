"""Bind a head assembly, its print project, and completed digital checks to one revision."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from math import isfinite
from pathlib import Path

OVERLAP_LIMIT = .05
REFERENCE = Path(__file__).resolve().parents[1] / 'revisions/b22'
ROOT = REFERENCE.parents[2]
B23_PLAN_SHA = 'befbcb175b77b4dfe294620fc10f1828b89f385a5d69096871be641ea4c9ff83'
B24_PLAN_SHA = '3dfebcd647b31a2bbc756b843de1ac8af27ba0806d44160c2d2a9c3138bd15e8'


def digest(path):
    with path.open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def require(passed, item):
    if not passed:
        raise ValueError(f'Release check failed: {item}')


def verify(output, print_inputs=None, source=ROOT, revision='B23'):
    modern = revision == 'B24'
    cad_sha = digest(output/f'R5-{revision}-Assembly.FCStd')
    print_sha = digest(output/f'R5-{revision}-P2S.3mf')
    grams_sha = digest(output/'sliced-grams.json')
    firmware_sha = digest(source / 'control/openrb/R5B1/R5B1.ino')
    tracker_sha = digest(source / 'control/pc/track.py')
    checks = {}

    def report(name):
        path = output/f'{name}.json'
        data = json.loads(path.read_text())
        root = data[0] if isinstance(data, list) else data
        require(root['cad_sha256'] == cad_sha, f'{name} CAD identity')
        checks[path.name] = digest(path)
        return data

    design = report('design')
    if print_inputs is not None:
        for name, fingerprint in design['print_sha256'].items():
            require(digest(print_inputs/name) == fingerprint, f'{name} print mesh identity')
    slicing = report('slicing-check')
    require(slicing['project_sha256'] == print_sha and slicing['sliced_grams_sha256'] == grams_sha,
            'print project and masses')
    require(slicing['canonical_mesh_sha256'] == design['print_sha256'], 'print mesh identities')
    for plate, result in slicing['checks_by_plate'].items():
        require(not result['warnings'] and result['isolated_start_count'] == 0, f'plate {plate}')
    if modern:
        plate_names = set(map(str, range(1, 13)))
        changed = {'4', '6', '7', '8'}
        require(set(slicing['plate_sha256']) == plate_names
                and set(slicing['all_12_plates']['plates']) == plate_names
                and set(slicing['checks_by_plate']) == changed
                and set(map(str, slicing['identical_to_b23_plates'])) == plate_names-changed,
                'all twelve P2S plates accounted for')
        local = slicing['local_gcode_checks']
        pocket = local['P7']['bearing_wells']
        require(local['P7']['profile_binding']['p7_plate_sha256'] == slicing['plate_sha256']['7']
                and set(pocket) == {'left', 'right'}
                and all(row['minimum_pocket_diameter_mm'] >= 6.2
                        and row['planned_clear_counterbore_depth_mm'] >= 2.5
                        and row['support_crossings_through_OD6p1'] == 0 for row in pocket.values()),
                'sliced eye bearing pockets')
        socket = local['P6']['head_clearance_at_axial_seat_and_radial_wall']['D5.76_floor_117.75']
        require(socket['model_hits'] == socket['support_hits'] == 0
                and socket['minimum_model_bead_margin_mm'] >= .2, 'sliced pitch screw entry')
        relief = design['blink_shell_relief']
        require(relief['part'] == 'Part073' and 0 < relief['removed_mm3'] < 2
                and [row['side'] for row in relief['regions']] == ['left'], 'local inside-shell blink relief')
        link_relief = design['blink_link_relief']
        require(link_relief['part'] == 'Part057' and 0 < link_relief['removed_mm3'] < 12,
                'local left blink link bevel')
        skull_recess = local['P4']['left_blink_relief_and_carried_eye_link_relief']['test_inset_mm']['blink_left']
        require(local['P4']['indexed_front_with_camera_tray']['physical_bodies'] == 1
                and len(skull_recess) >= 5
                and all(row['permanent_intrusions'] == row['support_intrusions'] == 0
                        for row in skull_recess.values()), 'sliced front shell and blink recess')
        printed_link = local['P8']['left_blink_link_reworked_web_and_stock_pilots']
        require(printed_link['gcode_sha256'] == slicing['checks_by_plate']['8']['gcode_sha256']
                and printed_link['mesh_components'] == 1
                and printed_link['cut_0p06mm_inset_extrusion_hits'] == {'model': 0, 'support': 0}
                and printed_link['minimum_contiguous_polymer_span_at_2p20_mm_station_mm'] >= 2.6,
                'sliced left blink link bevel and continuous web')
        blink_seats = report('blink-seat-print-check')
        require(blink_seats['project_sha256'] == print_sha
                and blink_seats['plate7_sha256'] == slicing['plate_sha256']['7']
                and blink_seats['nominal_counterbore_depth_mm'] >= 5
                and set(blink_seats['seats']) == {'left', 'right'}
                and all(row['slip_model_required_finished_OD_mm'] == 10.24
                        for row in blink_seats['seats'].values())
                and all(row['nominal_finish_probe_overlap_mm3'] == row['D4_support_punch_from_outside_overlap_mm3'] == 0
                        for row in blink_seats['nominal_CAD_bench_cleanup_and_tool_routes'].values()),
                'printed blink bearing seat and dry-fit finishing routes')

    assembly = report('assembly')
    expected_plan = B24_PLAN_SHA if modern else B23_PLAN_SHA
    require(assembly[0]['plan_sha256'] == expected_plan
            and len(assembly) == (150 if modern else 142)
            and len({row['id'] for row in assembly}) == len(assembly)
            and assembly[-1]['id'] == 'rear-skull' and not any(row['issues'] for row in assembly),
            'full assembly and tool routes')
    service = {row['id']: row['service_access'] for row in assembly if 'service_access' in row}
    for name, count in (('rear-cover-bolts', 5), ('hatch-bolts', 4)):
        row = service.get(name, {})
        require(row.get('status') == 'pass' and row['cad_sha256'] == cad_sha and not row['cover_collisions']
                and len(row['fasteners']) == count
                and all(fastener['status'] == 'pass' for fastener in row['fasteners']), name)
    if modern:
        stages = {row['id']: row for row in assembly}
        require(stages['eye-bearing-align']['eye_bearing_alignment']['status'] == 'pass'
                and stages['pitch-drive-lock']['pitch_drive_key']['status'] == 'pass'
                and stages['pitch-horn-bolts']['pitch_horn_head_approaches']['status'] == 'pass',
                'aligned eye bearings and removable pitch screw')
        front = stages['front-shell']['front_link_clearance']
        require(front['continuous_lower_bound_mm'] >= front['required_mm'], 'straight front shell path')
    else:
        front = report('front-841')
        require(front['status'] == 'pass' and front['positions'] >= 841
                and min(row['continuous_lower_bound_mm'] for row in front['rows']) >= front['required_mm'],
                'straight front shell path with eye rod and pin installed')
    motion = report('head-motion')
    require(motion['pose_samples'] >= 26000 and not motion['collisions'], 'rigid pose screen')
    hardware = report('hardware-motion')
    require(hardware['hardware_spec_sha256'] == digest(output/'hardware-spec.json')
            and not any(row['collisions'] for row in hardware['fasteners'].values())
            and all(gap > 0 for gap in hardware['yaw_gap_mm'].values())
            and all(volume <= OVERLAP_LIMIT for volume in hardware['joint_pairs'].values()),
            'moving screws and retained pins')

    camera = report('camera-check')
    require(camera['status'] == 'pass' and len(camera['samples']) >= 21
            and camera['routes_sha256'] == digest(output/'camera-paths.npz'), 'camera cable routes')
    harness = report('neck-harness')
    require(harness['status'] == 'pass' and len(harness['samples']) >= 100, 'motor cable routes')
    jaw = report('jaw-wiring')
    require(jaw['poses'] and not any(row['contacts'] for row in jaw['poses']), 'jaw cable routes')
    yaw_camera = report('yaw-camera-continuation')
    require(yaw_camera['status'] == 'pass' and len(yaw_camera['samples']) >= 64
            and yaw_camera['minimum_wire_gap_mm'] >= .15
            and yaw_camera['routes_sha256'] == digest(output/'yaw-camera-paths.npz'), 'camera at yaw limits')
    nose = report('nose-check')
    require(nose['status'] == 'pass' and nose['wall_minimum_mm'] >= 1.2, 'camera tie saddle')
    eye = report('eye-pitch')
    require(eye['pass'] is True, 'eye-pitch clearance and leverage')
    if modern:
        bearing_shell = report('eye-bearing-shell')
        require({row['side'] for row in bearing_shell['rows']} == {'L', 'R'}
                and all(row['continuous_min_mm'] >= .2 for row in bearing_shell['rows']),
                'front shell clears toleranced eye bearings')
        require(max(eye['force_path']['with_bearing_support_max_reversal_deg']) <= 2.,
                'modeled eye reversal excluding servo play')
        sight = report('sightlines')
        require(sight['status'] == 'pass' and sight['firmware_sha256'] == firmware_sha
                and sight['camera_in_frame'] and not sight['camera_opaque_contacts']
                and len(sight['pupils']) == 2
                and all(row['max_elevation_deg'] >= row['required_elevation_deg']
                        and not row['opaque_contacts'] for row in sight['pupils']), 'S02 look-up sightline')
    blink = report('blink-loaded')
    if modern:
        require(blink['actuator_data'].endswith('/xl330-m077/')
                and sum(row['trial_count'] for row in blink['cases'].values()) == 4320
                and all(row['all_cycles_within_S03_timing'] for row in blink['cases'].values())
                and blink['solver_sha256'] == digest(source/'mechanical/physics/b23_blink_loaded.py'),
                'S03 blink timing throughout the modeled envelope')
        blink_torque = max(row['max_requested_drive_Nm'] for row in blink['cases'].values())
    else:
        blink_torque = max(row['max_requested_drive_Nm'] for row in blink['cases']['5V_twice_drag']['trials'])
    require(blink['print_mass_map_sha256'] == grams_sha
            and blink['firmware_sha256'] == firmware_sha and blink['tracking_sha256'] == tracker_sha
            and blink_torque <= .2*(.215 if modern else .52),
            'blink transmission-angle torque exception in the model')
    blink_load = report('blink-load')
    require(blink_load['blink']['load_cases']['bilateral_touch_0.25_N_each']['maximum_lid_difference_deg'] < 1.,
            'differential blink bending screen')
    rail = report('blink-rail' if modern else 'blink-fem')
    if modern:
        fine_rail = [row for row in rail['trials'] if row['mesh_mm'] <= .8 and row['torque_Nm'] >= .060]
        require(rail['modulus_MPa'] <= 700 and rail['print_layer_normal_cad'] == [0., 1., 0.]
                and fine_rail and all(row['layer_y_tension_max_MPa'] > 0 for row in fine_rail),
                'blink rail stall-load screen')
        soft_rail = report('blink-soft')
        shell = report('blink-shell')
        rows = shell['rows']
        require(len(rows) == 16 and len({tuple(row['pair']) for row in rows}) == len(rows)
                and shell['between_lids_axial_gap_mm'] >= .25
                and all(row['continuous_min_mm'] >= (.25 if row['pair'][0] in ('Part078', 'Part079') else .15)
                        for row in rows),
                'elastic blink travel remains clear of shell and orbit frames')
        dynamic = max(max(-row['overall_angle_deg'][0], row['overall_angle_deg'][1]-90.)
                      for row in blink['cases'].values())
        require(soft_rail['modulus_MPa'] <= 500, 'softer printed rail sensitivity')
        for trial in (rail, soft_rail):
            elastic = trial['deflected_lid_replay']['0.8']
            require(len(elastic) == 76 and all(abs(row['torque_Nm']) >= blink_torque for row in elastic),
                    'both signs and lids loaded through the blink cycle')
            for actor, values in (
                ('Part078', [row['lid_deg'][0] for row in elastic]),
                ('Part079', [row['lid_deg'][1] for row in elastic]),
                ('Part057', [row['shaft_deg'] for row in elastic]),
                ('Part060', [row['shaft_deg'] for row in elastic]),
            ):
                low, high = shell['angle_range_deg'][actor]
                require(low <= min(values)-dynamic and max(values)+dynamic <= high,
                        f'loaded blink travel for {actor} lies within swept clearance')
        linked = report('blink-loaded-link')
        require(linked['point_load_N'] == 1
                and linked['mixed_E500_min_link_clearance_mm'] >= .15
                and linked['mixed_E500_min_lid_clearance_mm'] >= .15
                and not linked['mixed_E500']['contacts']
                and linked['min_net_web_mm2'] >= 11
                and linked['min_pinned_Euler_N'] >= 17.4
                and linked['removed_from_lower_pin_boss_mm3'] <= .01,
                'contact-free late touch with both link pins coupled and the pin boss intact')
    report('eye-cradle-strength')
    pin_fit = report('eye-yaw-pin-fit')
    cutback = (pin_fit['eye_hole_diameter_mm']-2.20)/2
    require(all(row['trials']['0.25']['worst']['minimum_radial_margin_mm'] > cutback
                for row in pin_fit['trials']), 'loaded eye yaw pins after Ø2.20 finishing')
    drive = report('drive')
    require(drive['status'] == 'pass' and drive['sliced_grams_sha256'] == grams_sha
            and drive['firmware_sha256'] == firmware_sha, 'powered drive torque')
    replay = report('motion-replay')
    walk = [row for name, row in replay['cases'].items() if '-walk-' in name and row['latency_s'] == .12]
    require(replay['sliced_grams_sha256'] == grams_sha and replay['firmware_sha256'] == firmware_sha
            and replay['tracker_sha256'] == tracker_sha
            and replay['solver_sha256'] == digest(source/'mechanical/physics/b23_motion_replay.py')
            and replay['jaw_stop_sha256'] == digest(output/'jaw-stop.json')
            and len(walk) == (6 if modern else 4)
            and all(row['acquisition_s'] <= 1 and row['horizontal_tracking_10deg_ratio'] >= .85
                                      and row['max_neck_combined_speed_deg_s'] <= 45
                                      and row['firmware_feedback_fault'] is None for row in walk),
            'S01 tracking at modeled 120 ms latency')
    if modern:
        delayed = [row for name, row in replay['cases'].items() if '-walk-' in name and row['latency_s'] == .20]
        require(len(delayed) == 3 and all(row['acquisition_s'] <= 1
                                        and row['horizontal_tracking_10deg_ratio'] >= .85
                                        and row['max_neck_combined_speed_deg_s'] <= 45
                                        and row['firmware_feedback_fault'] is None for row in delayed),
                'S01 sensitivity at 200 ms latency')
        turns = [row for name, row in replay['cases'].items() if '-turn-' in name]
        require(len(turns) == 6 and all(row['firmware_feedback_fault'] is None
                                       and row['overshoot_deg'] <= 12
                                       and row['horizontal_error_at_4s_deg'] <= 10
                                       and row['max_neck_combined_speed_deg_s'] <= 45 for row in turns),
                'S01b settled sightline and neck overshoot')
        returns = [row for name, row in replay['cases'].items() if '-loss-' in name]
        recoveries = [row for name, row in replay['cases'].items() if '-cold-close-exhibit' in name]
        require(len(returns) == 8 and all(row['parked'] and not row['return_failed']
                                          and 2 <= row['hold_command_s'] <= 3
                                          and row['return_peak_speed_deg_s'] <= 15
                                          and max(map(abs, row['final_neck_jaw_deg'][:2])) <= .5
                                          and row['firmware_feedback_fault'] is None
                                          for row in returns), 'settled calibrated neck return')
        require(len(recoveries) == 4 and all(row['exhibit_tracking_frames'] > 0
                                            and row['firmware_feedback_fault'] is None for row in recoveries),
                'cold jaw recovery through active tracking')
        jaw_hold = report('jaw-hold')
        require(jaw_hold['firmware_sha256'] == firmware_sha, 'jaw hold firmware identity')
    stops = report('neck-stop')
    require(stops['status'] == 'pass' and stops['firmware_sha256'] == firmware_sha,
            'pitch and jaw power-off clearances')
    cutoff = report('coupled-release')
    pitch_low, pitch_high = stops['released']['pitch_deg']
    require(cutoff['grams_sha256'] == grams_sha
            and all(pitch_low <= row['absolute_deg'] <= pitch_high
                    for row in cutoff['energy_bounded_pitch_by_sign'].values())
            and all(row['jaw_cad_calibration']['first_contact_deg'] <= stops['requested_released_jaw_deg']
                    for row in cutoff['energy_bounded_jaw_by_pitch_bin']),
            'pitch and jaw power-off bounds inside checked geometry')
    force = report('force-path')
    require(force['sliced_grams_sha256'] == grams_sha and force['firmware_sha256'] == firmware_sha and
            all(margin > 0 for row in force['modes'].values()
                for margin, active in zip(row['warm_min_motor_margin_Nm'], row['moving_motor_axes'], strict=True)
                if active), 'warm force-path margins')
    if modern:
        coupling = report('pitch-drive-strength')
        flex = coupling['seated_angle_screen']['max_modeled_elastic_angle_deg']
        require(coupling['force_path_sha256'] == checks['force-path.json']
                and coupling['operating_torque_within_reversal_proof']
                and len(stops['locations']) == 2
                and all(row['calibrated_margin_from_feedback_limit_deg'] > flex for row in stops['locations']),
                'pitch coupling deflection fits calibrated stop reserve')
        starts = report('pitch-loads')
        strength = report('pitch-strength')
        guard = starts['initial_encoder_guard_deg']
        offset = starts['initial_body_offset_deg']
        require(starts['sliced_grams_sha256'] == grams_sha and strength['cad_sha256'] == cad_sha
                and cutoff['load_sha256'] == checks['pitch-loads.json']
                and cutoff['neck_strength_sha256'] == checks['pitch-strength.json']
                and cutoff['jaw_stop_sha256'] == replay['jaw_stop_sha256']
                and guard == stops['powered_feedback_pitch_deg'] and offset >= flex
                and cutoff['command_pitch_deg'] == starts['command_pitch_deg']
                and starts['command_pitch_deg'][0] <= guard[0]-offset+1e-9
                and starts['command_pitch_deg'][1] >= guard[1]+offset-1e-9,
                'power-off starts cover encoder guard and coupling elasticity')
    yaw_strength = report('yaw-stop-strength')
    require(yaw_strength['sliced_grams_sha256'] == grams_sha
            and all(row['late_abs_deg'] <= 60.35 for row in yaw_strength['direction_results'].values()),
            'modeled yaw stop after impact')

    seated = report('seated-summary')
    require(seated['contact_report_sha256'] == digest(output/'static-pairs.json')
            and seated['regressions'] == [], 'seated overlaps relative to the preceding model')
    if modern:
        mates = report('seated-mates')
        contacts = json.loads((output/'static-pairs.json').read_text())
        unresolved = {(row['a'], row['b']) for row in contacts if row['mm3'] is None}
        require(seated['baseline_sha256'] == digest(REFERENCE.parent/'b23/static-pairs.json')
                and mates['contact_report_sha256'] == seated['contact_report_sha256']
                and mates['baseline_cad_sha256'] == design['reference_cad_sha256']
                and len(mates['pairs']) == len(unresolved) == seated['unmeasurable_pairs']
                and {tuple(row['pair']) for row in mates['pairs']} == unresolved,
                'all seated mesh contacts checked against the individual motor solids')
        for row in mates['pairs']:
            volume = row['overlap_mm3']
            require(isfinite(volume) and (0 <= volume <= OVERLAP_LIMIT if row['status'] == 'clear' else
                    row['status'] in ('stock_thread', 'stock_connector_envelope')
                    and abs(volume-row['b23_overlap_mm3']) <= OVERLAP_LIMIT),
                    f'seated motor mate {row["pair"]}')

    result = {
        'revision': revision,
        'cad_sha256': cad_sha,
        'p2s_sha256': print_sha,
        'sliced_grams_sha256': grams_sha,
        'firmware_sha256': firmware_sha,
        'evidence_sha256': checks,
        'assembly_steps': len(assembly),
        'assembly_blockers': 0,
        'rigid_pose_samples': motion['pose_samples'],
        'fasteners_screened_for_motion': len(hardware['fasteners']),
        'unmeasurable_inherited_seated_pairs': 0 if modern else seated['unmeasurable_pairs'],
        'camera_routes': len(camera['samples']),
        'camera_routes_at_yaw_limits': len(yaw_camera['samples']),
        'motor_cable_routes': len(harness['samples']),
        'minimum_camera_tie_wall_mm': nose['wall_minimum_mm'],
        'changed_plates': sorted(map(int, slicing['checks_by_plate'])),
        'pending_physical': ['P01 real fit', 'P02 cable pull', 'P03 50 blinks and duration',
                             'P04 reversal, friction and tracking', 'P05 installed sightline',
                             'P06 jaw motion', 'P07 camera latency', 'P08 full assembly'],
    }
    if modern:
        result['seated_motor_mates_checked'] = len(mates['pairs'])
        result['pending_physical'][3] = 'P04 tracking, friction and neck motion'
        result['pending_mechanism_measurements'] = ['M05 assembled reversal', 'M07 P03 blink exception']
    return result


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--print-inputs', type=Path, help='Also compare the unpacked generator STLs')
    parser.add_argument('--source', type=Path, default=ROOT,
                        help='Archive of the matching controller and replay source tree')
    parser.add_argument('--revision', choices=('B23', 'B24'), default='B23')
    parser.add_argument('--write', action='store_true', help='Save the regenerated evidence summary')
    args = parser.parse_args()
    rendered = json.dumps(verify(args.output, args.print_inputs, args.source, args.revision),
                          indent=2) + '\n'
    if args.write:
        (args.output/'verification.json').write_text(rendered, encoding='utf-8')
    print(rendered, end='')
