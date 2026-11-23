"""Run the selected R5 acceptance checks. Exit 0 on PASS, 1 on FAIL, 2 on UNVERIFIED."""
from argparse import ArgumentParser
from hashlib import file_digest
from pathlib import Path
import tomllib

import b25
from cad import check_cad, digest
from fasteners import check_fasteners
from records_check import check_records
from scenes import check_scenes

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'B22'
STATUSES = ('PASS', 'FAIL', 'UNVERIFIED')


def combined(results, *items):
    statuses = {results[item][0] for item in items}
    status = 'FAIL' if 'FAIL' in statuses else 'UNVERIFIED' if 'UNVERIFIED' in statuses else 'PASS'
    return status, ' · '.join(f'{item} {results[item][0]}' for item in items)


def checks(root=ROOT):
    with (root / 'spec/criteria.toml').open('rb') as file:
        criteria = tomllib.load(file)
    cad = root / f'mechanical/revisions/{REVISION.lower()}/R5-{REVISION}-Assembly.FCStd'
    with cad.open('rb') as file:
        cad_hash = file_digest(file, 'sha256').hexdigest()

    scenes = check_scenes(root, criteria)
    details = {**check_cad(root), **check_records(root, REVISION, cad_hash)}
    results = {**scenes, **details}
    for scene, physical in (('S02', 'P05'), ('S03', 'P03')):
        status, detail = scenes[scene]
        if status != 'FAIL':
            status, _ = combined(results, scene, physical)
        results[scene] = status, f'{detail} · 실물 {physical} {details[physical][0]}'
    results['S04'] = combined(results, 'P06')
    results['S05'] = combined(results, 'C01', 'C02', 'C03', 'C04', 'P01', 'P08')
    results['S06'] = check_fasteners(root, criteria)
    return dict(sorted(results.items(), key=lambda item: ('SCMP'.index(item[0][0]), item[0])))


def b25_checks(root=ROOT):
    with (root / 'spec/criteria.toml').open('rb') as file:
        criteria = tomllib.load(file)
    cad_hash = digest(root / b25.CAD)

    def check_current_sightlines(*_):
        return b25.checked(b25.sightlines, root, criteria, cad_hash)

    scenes = check_scenes(root, criteria, look_up=check_current_sightlines, calibrated=True)
    physical = check_records(root, 'B25', cad_hash)
    results = {**scenes, **b25.assembly_checks(), **physical}
    jaw = b25.checked(b25.jaw_opening, root, cad_hash)
    results['S04'] = jaw
    for scene, bench in (('S02', 'P05'), ('S03', 'P03'), ('S04', 'P06')):
        _, detail = results[scene]
        status, _ = combined(results, scene, bench)
        results[scene] = status, f'{detail} · 실물 {bench} {physical[bench][0]}'
    results['S05'] = combined(results, 'C01', 'C02', 'C03', 'C04', 'P01', 'P08')
    return dict(sorted(results.items(), key=lambda item: ('SCMP'.index(item[0][0]), item[0])))


def main():
    parser = ArgumentParser(description=__doc__)
    routes = parser.add_mutually_exclusive_group()
    routes.add_argument('--revision', choices=('B22', 'B25'), default=REVISION)
    routes.add_argument('--b25-physical', action='store_true', help='Check B25 P06 and P07 bench records')
    args = parser.parse_args()
    if args.b25_physical:
        revision = 'B25'
        cad = ROOT / 'mechanical/revisions/b25/R5-B25-Assembly.FCStd'
        with cad.open('rb') as file:
            cad_hash = file_digest(file, 'sha256').hexdigest()
        records = check_records(ROOT, revision, cad_hash)
        results = {item: records[item] for item in ('P06', 'P07')}
    else:
        revision = args.revision
        results = b25_checks() if revision == 'B25' else checks()
    counts = dict.fromkeys(STATUSES, 0)
    print(f'R5 {revision} 인수 검사')
    for item, (status, detail) in results.items():
        counts[status] += 1
        print(f'{item:5} {status:10} {detail}')
    print('\n' + ' · '.join(f'{status} {counts[status]}' for status in STATUSES))
    return 1 if counts['FAIL'] else 2 if counts['UNVERIFIED'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
