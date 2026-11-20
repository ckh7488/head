"""Run B21 checks against one immutable set of CAD, hardware and rule inputs."""

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from hashlib import file_digest
from itertools import product
import json
from math import isfinite
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
        'world_meshes_sha256': world_hashes,
        'checker_sources_sha256': {path.name: digest(path) for path in sorted(HERE.glob('*.py'))},
    }


def steps(assembly, cad, hardware, spec, baseline, bom, run):
    return [
        ('seated', 'check_static_pairs.py', cad, run / 'seated.json', '--baseline', baseline),
        ('assembly', 'check_b19_assembly.py', '--revision', 'b21',
         cad, hardware, spec, run / 'assembly.json'),
        ('head_motion', 'check_head.py', cad, run / 'head_motion.json'),
        ('hardware_motion', 'check_b19_hardware.py', cad, spec, run / 'hardware_motion.json'),
        ('jaw_wiring', 'b21_harness.py', cad, run / 'jaw_wiring.json'),
        ('touch', 'b20_blink_load.py', '--dynamics', cad, run / 'touch.json'),
        ('contract', 'check_b21_contract.py', '--cad', cad, '--source', assembly, '--hardware', hardware,
         '--spec', spec, '--bom', bom, '--assembly', run / 'assembly.json',
         '--head', run / 'head_motion.json', '--touch', run / 'touch.json', '--report', run / 'contract.json'),
    ]


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


def jaw_envelope(stop, wiring, cad_sha):
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
    if {row['mesh_mm'] for row in meshes} != {.4, .5, .7}:
        raise ValueError('Jaw stop needs all three elastic mesh sizes')
    if any({case['modulus_MPa'] for case in row['impact_cases']} != {500., 1000., 1800.} for row in meshes):
        raise ValueError('Jaw stop needs the complete modulus sensitivity')
    impact_end = max(case['opening_with_static_face_tolerance_and_impact_deg']
                     for row in meshes for case in row['impact_cases'])
    bands = wiring['clearance_bands']
    normal, impact = bands[0], bands[-1]
    poses = wiring['poses']
    within = (isfinite(impact_end) and stop['software_open_deg'] == 8.
              and 8.75 <= static_start <= static_end <= normal['up_to_deg']
              and 8.60 <= compound_start <= compound_end <= normal['up_to_deg']
              and impact_end <= impact['up_to_deg']
              and len({tuple(row['fixed_pose']) for row in poses}) == 39
              and not any(row['contacts'] for row in poses))
    return {'status': 'pass' if within else 'fail', 'cad_sha256': cad_sha,
            'modeled_static_contact_deg': [static_start, static_end],
            'modeled_compound_contact_deg': [compound_start, compound_end],
            'modeled_gravity_drop_upper_deg': impact_end,
            'tested_wire_angles_deg': [band['up_to_deg'] for band in bands]}


def run_checks(args):
    from check_b21_contract import installed_fasteners
    from check_b19_assembly import PLANS, World

    captured = inputs(args.assembly, args.cad, args.hardware, args.spec, args.baseline, args.bom)
    stop_file = args.assembly.with_name('jaw-stop.json')
    captured['jaw_stop_sha256'] = digest(stop_file)
    args.output.mkdir(parents=True, exist_ok=True)
    run = Path(mkdtemp(prefix='b21-', dir=args.output.resolve()))
    reports = run / 'summary.json'
    summary = {'inputs': captured, 'checks': [], 'result': 'incomplete'}
    reports.write_text(json.dumps(summary, indent=2) + '\n')
    plan = PLANS['b21']
    hardware = json.loads(args.hardware.read_text())['hardware']
    spec = json.loads(args.spec.read_text())
    layout = json.loads((args.cad / 'cad_parts.json').read_text())
    print('fasteners: checking', flush=True)
    stock = installed_fasteners(plan, World(args.cad, hardware, spec), layout, spec, args.bom)
    stock_report = run / 'fasteners.json'
    stock_report.write_text(json.dumps(stock, indent=2, ensure_ascii=False) + '\n')
    summary['checks'].append({'name': 'fasteners', 'result': stock['status'], 'sha256': digest(stock_report)})
    scheduled = steps(args.assembly, args.cad, args.hardware, args.spec, args.baseline, args.bom, run)
    if stock['status'] == 'pass' or args.keep_going:
        check = partial(run_step, run)
        with ThreadPoolExecutor(max_workers=3) as pool:
            summary['checks'].extend(pool.map(check, scheduled[:-1]))
        stop_result = run / 'jaw_envelope.json'
        try:
            envelope = jaw_envelope(json.loads(stop_file.read_text()), json.loads((run / 'jaw_wiring.json').read_text()),
                                    captured['assembly_sha256'])
        except (OSError, KeyError, TypeError, ValueError) as error:
            envelope = {'status': 'fail', 'error': str(error)}
        stop_result.write_text(json.dumps(envelope, indent=2) + '\n')
        summary['checks'].append({'name': 'jaw_envelope', 'result': envelope['status'], 'sha256': digest(stop_result)})
        if args.keep_going or all(row['result'] == 'pass' for row in summary['checks']):
            summary['checks'].append(check(scheduled[-1]))

    after = inputs(args.assembly, args.cad, args.hardware, args.spec, args.baseline, args.bom)
    after['jaw_stop_sha256'] = digest(stop_file)
    if captured != after:
        summary['result'] = 'inputs_changed'
    elif len(summary['checks']) == len(scheduled) + 2 and all(
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
    parser.add_argument('--baseline', type=Path, default=ROOT / 'mechanical/revisions/b20/static-pairs.json')
    parser.add_argument('--bom', type=Path, default=ROOT / 'mechanical/BOM.csv')
    parser.add_argument('--keep-going', action='store_true')
    args = parser.parse_args()
    for name in ('assembly', 'cad', 'hardware', 'spec', 'output', 'baseline', 'bom'):
        setattr(args, name, getattr(args, name).resolve())
    if not run_checks(args):
        raise SystemExit(1)
