"""Run assembly checks against one immutable set of CAD, hardware and rule inputs."""

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from hashlib import file_digest
from itertools import product
import json
from math import isfinite, radians
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    with path.open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def inputs(assembly, cad, hardware, spec, baseline, bom):
    layout_path = cad / 'cad_parts.json'
    layout = json.loads(layout_path.read_text())
    assembly_digest = digest(assembly)
    if layout['source_sha256'] != assembly_digest:
        raise ValueError('World export does not match the assembly file')
    meshes = {path.stem: path for path in (cad / 'world').glob('*.stl')}
    expected = set(layout['world_motion'])
    if not expected or meshes.keys() != expected:
        raise ValueError(f'World meshes missing {sorted(expected - meshes.keys())} '
                         f'or stale {sorted(meshes.keys() - expected)}')
    world_hashes = {name: digest(path) for name, path in sorted(meshes.items())}
    if world_hashes != layout.get('world_sha256'):
        raise ValueError('World mesh contents do not match the CAD export manifest')
    return {
        'assembly_sha256': assembly_digest,
        'layout_sha256': digest(layout_path),
        'plan_hardware_sha256': digest(hardware),
        'hardware_spec_sha256': digest(spec),
        'baseline_sha256': digest(baseline),
        'bom_sha256': digest(bom),
        'wire_geometry_sha256': digest(ROOT / 'web/assets/wiring.json'),
        'wire_lengths_sha256': digest(ROOT / 'mechanical/revisions/b20/physics/harness-cut-lengths.json'),
        'wire_cut_list_sha256': digest(ROOT / 'mechanical/WIRING-CUT-LIST.csv'),
        'world_meshes_sha256': world_hashes,
        'checker_sources_sha256': {path.name: digest(path) for path in sorted(HERE.glob('*.py'))},
    }


def steps(assembly, cad, hardware, spec, baseline, bom, run, revision='b21', reference_cad=None, sliced_grams=None,
          camera_routes=None):
    checks = [
        ('seated', 'check_static_pairs.py', cad, run / 'seated.json', '--baseline', baseline),
        ('assembly', 'check_b19_assembly.py', '--revision', revision,
         cad, hardware, spec, run / 'assembly.json'),
        ('head_motion', 'check_head.py', cad, run / 'head_motion.json'),
        ('hardware_motion', 'check_b19_hardware.py', cad, spec, run / 'hardware_motion.json'),
        ('jaw_wiring', 'b21_harness.py', cad, run / 'jaw_wiring.json'),
        ('touch', 'b20_blink_load.py', '--dynamics', cad, run / 'touch.json'),
    ]
    if revision == 'b22':
        from check_b22_neck import released_overshoot_by_sign

        checks[0] += ('--exact-cad', assembly)
        checks[1] += ('--source', assembly)
        layout = json.loads((cad / 'cad_parts.json').read_text())
        stop = layout['motion_geometry']['pitch_stop']
        extra = released_overshoot_by_sign(stop['released_overshoot_deg'])
        endpoints = {row['direction']: row['search_window_deg'][-1] for row in stop['stops']}
        jaw_limit = layout['motion_geometry']['jaw_stop'].get('released_clearance_deg', 11.175)
        changed = stop.get('modified_part_keys') or sorted({name for row in stop['stops'] for name in row['actors']})
        checks.extend([
            ('drive', 'b22_drive.py', cad, sliced_grams, run),
            ('neck_stop', 'check_b22_neck.py', cad, run / 'neck_stop.json', '--jaw-released-deg', 9.80),
            ('neck_harness', 'check_b22_harness.py', cad, run / 'neck_harness.json',
             '--baseline', reference_cad, '--powered', *stop['powered_deg'],
             '--arrest', endpoints[-1]-extra[-1], endpoints[1]+extra[1],
             '--jaw', jaw_limit, '--coupled-cutoff',
             '--motors-only' if camera_routes else '--require-camera-bend', '--changed', *changed),
        ])
        if camera_routes:
            checks.append(('camera_routes', 'check_b22_camera_routes.py', cad, camera_routes, run/'camera_routes.json'))
    checks.append(('contract', 'check_b21_contract.py', '--revision', revision,
                   '--cad', cad, '--source', assembly, '--hardware', hardware, '--spec', spec,
                   '--bom', bom, '--assembly', run / 'assembly.json', '--head', run / 'head_motion.json',
                   '--touch', run / 'touch.json', '--report', run / 'contract.json'))
    return checks


def run_step(run, step):
    name, filename, *arguments = step
    print(f'{name}: checking', flush=True)
    log = run / f'{name}.log'
    with log.open('w', encoding='utf-8') as out:
        script = HERE / filename
        completed = subprocess.run([sys.executable, str(script), *map(str, arguments)],
                                   cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, check=False)
    output = run / f'{name}.json'
    if completed.returncode or not output.is_file():
        return {'name': name, 'result': 'fail', 'log': log.name}
    return {'name': name, 'result': 'pass', 'sha256': digest(output)}


def jaw_envelope(stop, wiring, cad_sha, revision='b21'):
    if stop['cad_sha256'] != cad_sha or wiring['cad_sha256'] != cad_sha:
        raise ValueError('Jaw stop and wiring must describe the checked assembly')
    witnesses = stop['contact_trials']
    if {row['face_shift_mm'] for row in witnesses} != {-.2, 0., .2}:
        raise ValueError('Jaw stop needs measurements at both machining limits')
    static_start = min(row['first_contact_deg'] for row in witnesses)
    static_end = max(row['first_contact_deg'] for row in witnesses)
    compound = stop['compound_contact_trials']
    if {tuple(row['rigid_translation_mm']) for row in compound} != set(product((-.2, 0., .2), repeat=3)):
        raise ValueError('Jaw stop needs all 27 compound assembly offsets')
    compound_start = min(row['first_contact_deg'] for row in compound)
    compound_end = max(row['first_contact_deg'] for row in compound)
    meshes = stop['local_FE']['meshes']
    scales = {row['mesh_mm'] for row in meshes}
    if (revision == 'b21' and scales != {.4, .5, .7} or revision == 'b22'
            and (len(scales) < 3 or min(scales) > .45 or max(scales) < .60)):
        raise ValueError('Jaw stop needs all three elastic mesh sizes')
    if any({case['modulus_MPa'] for case in row['impact_cases']} != {500., 1000., 1800.} for row in meshes):
        raise ValueError('Jaw stop needs the complete modulus sensitivity')
    impact_end = max(case['opening_with_static_face_tolerance_and_impact_deg']
                     for row in meshes for case in row['impact_cases'])
    bands = wiring['clearance_bands']
    normal, impact = bands[0], bands[-1]
    poses = wiring['poses']
    if revision == 'b22':
        from b22_drive import jaw_config

        command, max_feedback, _, _ = jaw_config()
        qualified = (0. < command <= stop['software_open_deg']
                     and max_feedback <= stop['max_powered_feedback_deg'] + .002
                     and stop['reference_powered_model']['mujoco_peak_deg'] < compound_start
                     and stop['released_clearance_deg'] == impact['up_to_deg'])
        straight_limit = compound_limit = max_feedback
    else:
        qualified = stop['software_open_deg'] == 8.
        straight_limit, compound_limit = 8.75, 8.60
    within = (isfinite(impact_end) and qualified
              and straight_limit <= static_start <= static_end <= normal['up_to_deg']
              and compound_limit <= compound_start <= compound_end <= normal['up_to_deg']
              and impact_end <= impact['up_to_deg']
              and len({tuple(row['fixed_pose']) for row in poses}) == 39
              and not any(row['contacts'] for row in poses))
    return {'status': 'pass' if within else 'fail', 'cad_sha256': cad_sha,
            'modeled_static_contact_deg': [static_start, static_end],
            'modeled_compound_contact_deg': [compound_start, compound_end],
            'modeled_gravity_drop_upper_deg': impact_end,
            'tested_wire_angles_deg': [band['up_to_deg'] for band in bands]}


def verify_guard(cad, report, cad_sha):
    proof = json.loads(report.read_text())
    if (proof['head_cad_sha256'] != cad_sha or proof['guard_cad_sha256'] != digest(cad)
            or proof['status'] != 'pass'):
        raise ValueError('Cover proof does not qualify this head and cover CAD')
    if (proof['touch_force_N'] != 1. or not 0. <= proof['max_opening_mm'] <= 6.
            or not isfinite(proof['min_leftover_clearance_after_touch_mm'])
            or proof['min_leftover_clearance_after_touch_mm'] < 10.
            or not proof['cover_and_roof_positively_retained']
            or not proof['fastener_and_tool_paths_pass']):
        raise ValueError('Cover does not isolate the moving parts during a light touch')
    return proof


def impact_values(cases):
    return {
        'deflection_deg': max(max(row['additional_rotation_deg'],
                                 row['with_coupled_unit_bearing_tractions']['additional_rotation_deg']) for row in cases),
        'strip_notch_mpa': max(row['steel_and_ears']['strip_gross_slot_edge_estimate_MPa'] for row in cases),
        'pin_mpa': max(part['pin_von_mises'] for row in cases
                       for part in row['steel_and_ears']['pin_and_ear_ratings_needed_MPa'].values()),
        'ear_bearing_mpa': max(part['projected_polymer_bearing'] for row in cases
                              for part in row['steel_and_ears']['pin_and_ear_ratings_needed_MPa'].values()),
        'printed_p99_mpa': max(part['p99_elastic_stress_MPa'] for row in cases for part in row['parts'].values()),
        'bearing_radial_N': max(row['bearing_reaction_envelope'][which] for row in cases
                                for which in ('left_radial_N', 'right_radial_N')),
    }


def coupled_release(path, loads, strength, jaw_stop, neck, cad_sha):
    from check_b22_harness import cutoff_jaw

    report = json.loads(path.read_text())
    if (report['cad_sha256'] != cad_sha or report['load_sha256'] != digest(loads)
            or report['neck_strength_sha256'] != digest(strength) or report['jaw_stop_sha256'] != digest(jaw_stop)):
        raise ValueError('Coupled cutoff report differs from the checked CAD, mass or stops')
    contact = sorted(neck['locations'], key=lambda row: row['first_contact_deg'])
    late = report['late_pitch_contact_deg']
    if (len(contact) != 2 or late[0] > contact[0]['calibrated_contact_interval_deg'][0]
            or late[1] < contact[1]['calibrated_contact_interval_deg'][1]):
        raise ValueError('Coupled cutoff started before the late physical contact limits')
    pitch_min, pitch_max = neck['released']['pitch_deg']
    for row in report['energy_bounded_jaw_by_pitch_bin']:
        low, high = row['pitch_range_deg']
        low = pitch_min if low is None else low
        high = pitch_max if high is None else high
        if high < pitch_min or low > pitch_max:
            continue
        jaw = row['jaw_cad_calibration']['first_contact_deg']
        if not 0. <= jaw <= min(neck['released']['jaw_deg'][1], cutoff_jaw(min(high, pitch_max))):
            raise ValueError('Coupled jaw exceeds the tested rigid and wiring envelope')
    return {side: max(report['coupled_maximum_extra_deg'][side], report['energy_bounded_pitch_extra_deg'][side])
            for side in ('back', 'forward')}


def neck_envelope(strength, loads_path, neck, cad_sha, cutoffs, guard=None):
    from check_b22_neck import released_overshoot_by_sign

    if (strength['cad_sha256'] != cad_sha or strength['load_cad_sha256'] != cad_sha
            or strength['loads_sha256'] != digest(loads_path) or neck['cad_sha256'] != cad_sha):
        raise ValueError('Pitch strength, loads and clearance must describe the checked assembly')
    loads = json.loads(loads_path.read_text())
    if not loads['nominal_no_ballast_maximum'] or loads['touch_force_N'] != 1.:
        raise ValueError('Pitch proof needs the stock, unballasted 1 N case')
    if any(len({row['mesh_mm'] for row in strength['mesh'][part]}) < 2 for part in ('yoke', 'frame')):
        raise ValueError('Both clevises need an elastic mesh refinement run')
    allowances = released_overshoot_by_sign(neck['released_overshoot_deg'])
    limits = {'strip_notch_mpa': 235/1.5, 'pin_mpa': 300., 'ear_bearing_mpa': 15.,
              'printed_p99_mpa': 20., 'bearing_radial_N': 710/1.5}
    rows = {}
    for side, sign in (('back', -1), ('forward', 1)):
        stop = strength['bounds'][f'pitch-stop-{side}']
        impacts = stop['elastic_impacts']
        if set(impacts) != {'gravity_only', 'gravity_and_pulse'} or any(len(rows) != 3 for rows in impacts.values()):
            raise ValueError('Each pitch direction needs six nominal impact cases')
        accepted = [trial for model, trials in impacts.items()
                    if guard is None or model == 'gravity_only' for trial in trials.values()]
        values = impact_values(accepted)
        compliance = 2.*stop['coupled_bearings_compliance_mm_per_N_at_1GPa']
        compliance += stop['steel_link']['incremental_axes_compliance_mm_per_N']
        cutoff_force = radians(cutoffs[side])*stop['contact_lever_mm']/compliance
        screened_force = max(row['peak_contact_force_N'] for row in accepted)
        force_scale = max(1., cutoff_force/screened_force)
        values = {key: value*force_scale for key, value in values.items() if key != 'deflection_deg'} | {
            'deflection_deg': max(values['deflection_deg'], cutoffs[side])}
        cap = {**limits, 'deflection_deg': allowances[sign]}
        rows[side] = {'modeled': values, 'limits': cap,
                      'coupled_cutoff_deflection_deg': cutoffs[side], 'coupled_cutoff_force_N': cutoff_force,
                      'pass': all(isfinite(value) and 0. <= value <= cap[key] for key, value in values.items())}
        if guard is not None:
            rows[side]['uncovered_touch_sensitivity'] = impact_values(impacts['gravity_and_pulse'].values())
    return {'status': 'pass' if neck['status'] == 'pass' and all(row['pass'] for row in rows.values()) else 'fail',
            'installed_guard_required': guard is not None,
            'cad_sha256': cad_sha, 'checks': rows,
            'scope': 'Nominal unballasted impact screens. Printed values are engineering limits, not measured part strengths.'}


def run_checks(args):
    from check_b21_contract import installed_fasteners
    from check_b19_assembly import World, assembly_plan

    stop_file = args.assembly.with_name('jaw-stop.json')

    def snapshot():
        recorded = inputs(args.assembly, args.cad, args.hardware, args.spec, args.baseline, args.bom)
        recorded['jaw_stop_sha256'] = digest(stop_file)
        if args.revision == 'b22':
            reference = args.reference_cad
            layout_file = reference / 'cad_parts.json'
            layout = json.loads(layout_file.read_text())
            b21 = ROOT / 'mechanical/revisions/b21/R5-B21-Assembly.FCStd'
            if layout['source_sha256'] != digest(b21):
                raise ValueError('Neck harness comparison must use the released B21 CAD')
            hashes = {name: digest(reference / 'world' / f'{name}.stl') for name in layout['world_motion']}
            if hashes != layout['world_sha256']:
                raise ValueError('Neck harness reference meshes do not match their manifest')
            recorded['neck_reference_export_sha256'] = digest(layout_file)
            recorded['pitch_loads_sha256'] = digest(args.pitch_loads)
            recorded['pitch_strength_sha256'] = digest(args.pitch_strength)
            recorded['pitch_release_sha256'] = digest(args.pitch_release)
            recorded['sliced_grams_sha256'] = digest(args.sliced_grams)
            if args.camera_routes:
                recorded['camera_routes_sha256'] = digest(args.camera_routes)
            if json.loads(args.pitch_loads.read_text())['sliced_grams_sha256'] != recorded['sliced_grams_sha256']:
                raise ValueError('Actuator and cutoff models must share the same sliced masses')
            recorded['firmware_sha256'] = digest(ROOT / 'control/openrb/R5B1/R5B1.ino')
            if args.guard_report:
                recorded['guard_sha256'] = digest(args.guard)
                recorded['guard_report_sha256'] = digest(args.guard_report)
        return recorded

    captured = snapshot()
    args.output.mkdir(parents=True, exist_ok=True)
    run = Path(mkdtemp(prefix=f'{args.revision}-', dir=args.output.resolve()))
    reports = run / 'summary.json'
    summary = {'inputs': captured, 'checks': [], 'result': 'incomplete'}
    reports.write_text(json.dumps(summary, indent=2) + '\n')
    hardware = json.loads(args.hardware.read_text())['hardware']
    spec = json.loads(args.spec.read_text())
    layout = json.loads((args.cad / 'cad_parts.json').read_text())
    plan = assembly_plan(args.revision, layout)
    print('fasteners: checking', flush=True)
    stock = installed_fasteners(plan, World(args.cad, hardware, spec), layout, spec, args.bom)
    stock_report = run / 'fasteners.json'
    stock_report.write_text(json.dumps(stock, indent=2, ensure_ascii=False) + '\n')
    summary['checks'].append({'name': 'fasteners', 'result': stock['status'], 'sha256': digest(stock_report)})
    scheduled = steps(args.assembly, args.cad, args.hardware, args.spec, args.baseline, args.bom,
                      run, args.revision, args.reference_cad, args.sliced_grams, args.camera_routes)
    if stock['status'] == 'pass' or args.keep_going:
        check = partial(run_step, run)
        with ThreadPoolExecutor(max_workers=3) as pool:
            summary['checks'].extend(pool.map(check, scheduled[:-1]))
        stop_result = run / 'jaw_envelope.json'
        try:
            envelope = jaw_envelope(json.loads(stop_file.read_text()), json.loads((run / 'jaw_wiring.json').read_text()),
                                    captured['assembly_sha256'], args.revision)
        except (OSError, KeyError, TypeError, ValueError) as error:
            envelope = {'status': 'fail', 'error': str(error)}
        stop_result.write_text(json.dumps(envelope, indent=2) + '\n')
        summary['checks'].append({'name': 'jaw_envelope', 'result': envelope['status'], 'sha256': digest(stop_result)})
        if args.revision == 'b22':
            impact_report = run / 'neck_envelope.json'
            try:
                guard = verify_guard(args.guard, args.guard_report, captured['assembly_sha256']) if args.guard_report else None
                neck = json.loads((run / 'neck_stop.json').read_text())
                cutoffs = coupled_release(args.pitch_release, args.pitch_loads, args.pitch_strength, stop_file,
                                          neck, captured['assembly_sha256'])
                impact = neck_envelope(json.loads(args.pitch_strength.read_text()), args.pitch_loads,
                                       neck, captured['assembly_sha256'], cutoffs, guard)
            except (OSError, KeyError, TypeError, ValueError) as error:
                impact = {'status': 'fail', 'error': str(error)}
            impact_report.write_text(json.dumps(impact, indent=2) + '\n')
            summary['checks'].append({'name': 'neck_envelope', 'result': impact['status'],
                                      'sha256': digest(impact_report)})
        if args.keep_going or all(row['result'] == 'pass' for row in summary['checks']):
            summary['checks'].append(check(scheduled[-1]))

    after = snapshot()
    if captured != after:
        summary['result'] = 'inputs_changed'
    elif len(summary['checks']) == len(scheduled) + (3 if args.revision == 'b22' else 2) and all(
            row['result'] == 'pass' for row in summary['checks']):
        summary['result'] = 'model_checks_pass'
    else:
        summary['result'] = 'fail'
    reports.write_text(json.dumps(summary, indent=2) + '\n')
    print(reports, summary['result'])
    return summary['result'] == 'model_checks_pass'


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('assembly', type=Path)
    parser.add_argument('cad', type=Path)
    parser.add_argument('hardware', type=Path)
    parser.add_argument('spec', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--revision', default='b21', choices=('b21', 'b22'))
    parser.add_argument('--reference-cad', type=Path, help='Released B21 world export for B22 harness comparison')
    parser.add_argument('--pitch-loads', type=Path)
    parser.add_argument('--pitch-strength', type=Path)
    parser.add_argument('--pitch-release', type=Path)
    parser.add_argument('--sliced-grams', type=Path)
    parser.add_argument('--camera-routes', type=Path, help='Sampled fixed-length camera routes for B22')
    parser.add_argument('--guard', type=Path, help='Closed cover CAD for a protected B22 setup')
    parser.add_argument('--guard-report', type=Path, help='Matching cover fit and touch verification')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--bom', type=Path, default=ROOT / 'mechanical/BOM.csv')
    parser.add_argument('--keep-going', action='store_true')
    args = parser.parse_args()
    if args.revision == 'b22' and not all((args.reference_cad, args.pitch_loads, args.pitch_strength,
                                          args.pitch_release, args.sliced_grams)):
        parser.error('B22 requires the reference CAD, sliced masses and all three pitch reports')
    if bool(args.guard) != bool(args.guard_report) or args.guard and args.revision != 'b22':
        parser.error('--guard and --guard-report are a B22 pair')
    if args.camera_routes and args.revision != 'b22':
        parser.error('--camera-routes requires B22')
    if args.revision == 'b22' and not args.camera_routes:
        layout = json.loads((args.cad/'cad_parts.json').read_text())
        if layout.get('motion_geometry', {}).get('camera_cable'):
            parser.error('Provide the routed B22 camera samples with --camera-routes')
    if args.reference_cad:
        args.reference_cad = args.reference_cad.resolve()
    if args.camera_routes:
        args.camera_routes = args.camera_routes.resolve()
    if args.baseline is None:
        prior = 'b21' if args.revision == 'b22' else 'b20'
        args.baseline = ROOT / 'mechanical/revisions' / prior / 'static-pairs.json'
    for name in ('assembly', 'cad', 'hardware', 'spec', 'output', 'baseline', 'bom'):
        setattr(args, name, getattr(args, name).resolve())
    if not run_checks(args):
        raise SystemExit(1)
