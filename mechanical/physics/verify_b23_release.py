"""Bind the B23 assembly, print project, and completed digital checks to one revision."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path

OVERLAP_LIMIT = .05
REFERENCE = Path(__file__).resolve().parents[1] / 'revisions/b22'
ROOT = REFERENCE.parents[2]


def digest(path):
    with path.open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def require(passed, item):
    if not passed:
        raise ValueError(f'B23 check failed: {item}')


def verify(output, print_inputs=None):
    cad_sha = digest(output/'R5-B23-Assembly.FCStd')
    print_sha = digest(output/'R5-B23-P2S.3mf')
    grams_sha = digest(output/'sliced-grams.json')
    firmware_sha = digest(ROOT / 'control/openrb/R5B1/R5B1.ino')
    tracker_sha = digest(ROOT / 'control/pc/track.py')
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
            require(digest(print_inputs/name) == fingerprint, f'{name} STL identity')
    slicing = report('slicing-check')
    require(slicing['project_sha256'] == print_sha and slicing['sliced_grams_sha256'] == grams_sha,
            'print project and masses')
    require(slicing['canonical_mesh_sha256'] == design['print_sha256'], 'print mesh identities')
    for plate, result in slicing['checks_by_plate'].items():
        require(not result['warnings'] and result['isolated_start_count'] == 0, f'plate {plate}')

    assembly = report('assembly')
    require(len(assembly) >= 141 and len({row['id'] for row in assembly}) == len(assembly)
            and assembly[-1]['id'] == 'rear-skull' and not any(row['issues'] for row in assembly),
            'full assembly and tool routes')
    require({'rear-cover-bolts', 'hatch-bolts'} <= {row['id'] for row in assembly if row.get('service_access')},
            'both service covers')
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
    blink = report('blink-loaded')
    blink_torque = max(row['max_requested_drive_Nm'] for row in blink['cases']['5V_twice_drag']['trials'])
    require(blink['print_mass_map_sha256'] == grams_sha
            and blink['firmware_sha256'] == firmware_sha and blink['tracking_sha256'] == tracker_sha
            and blink_torque <= .2*.52,
            'blink transmission-angle torque exception in the model')
    blink_load = report('blink-load')
    require(blink_load['blink']['load_cases']['bilateral_touch_0.25_N_each']['maximum_lid_difference_deg'] < 1.,
            'differential blink bending screen')
    report('blink-fem')
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
            and replay['solver_sha256'] == digest(ROOT/'mechanical/physics/b23_motion_replay.py')
            and replay['jaw_stop_sha256'] == digest(output/'jaw-stop.json')
            and len(walk) == 4 and all(row['acquisition_s'] <= 1 and row['horizontal_tracking_10deg_ratio'] >= .85
                                      and row['max_neck_combined_speed_deg_s'] <= 45
                                      and row['firmware_feedback_fault'] is None for row in walk),
            'S01 tracking at modeled 120 ms latency')
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
    yaw_strength = report('yaw-stop-strength')
    require(yaw_strength['sliced_grams_sha256'] == grams_sha
            and all(row['late_abs_deg'] <= 60.35 for row in yaw_strength['direction_results'].values()),
            'modeled yaw stop after impact')

    seated = report('seated-summary')
    require(seated['contact_report_sha256'] == digest(output/'static-pairs.json')
            and seated['regressions'] == [], 'seated overlaps relative to B22')

    result = {
        'revision': 'B23',
        'cad_sha256': cad_sha,
        'p2s_sha256': print_sha,
        'sliced_grams_sha256': grams_sha,
        'firmware_sha256': firmware_sha,
        'evidence_sha256': checks,
        'assembly_steps': len(assembly),
        'assembly_blockers': 0,
        'rigid_pose_samples': motion['pose_samples'],
        'fasteners_screened_for_motion': len(hardware['fasteners']),
        'unmeasurable_inherited_seated_pairs': seated['unmeasurable_pairs'],
        'camera_routes': len(camera['samples']),
        'camera_routes_at_yaw_limits': len(yaw_camera['samples']),
        'motor_cable_routes': len(harness['samples']),
        'minimum_camera_tie_wall_mm': nose['wall_minimum_mm'],
        'changed_plates': sorted(map(int, slicing['checks_by_plate'])),
        'pending_physical': ['P01 real fit', 'P02 cable pull', 'P03 50 blinks and duration',
                             'P04 reversal, friction and tracking', 'P05 installed sightline',
                             'P06 jaw motion', 'P07 camera latency', 'P08 full assembly'],
    }
    return result


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--print-inputs', type=Path, help='Also compare the unpacked generator STLs')
    parser.add_argument('--write', action='store_true', help='Save the regenerated evidence summary')
    args = parser.parse_args()
    rendered = json.dumps(verify(args.output, args.print_inputs), indent=2) + '\n'
    if args.write:
        (args.output/'verification.json').write_text(rendered, encoding='utf-8')
    print(rendered, end='')
