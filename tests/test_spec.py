"""Regression checks for the B22 acceptance verifier's evidence boundaries."""

import json
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

from spec.cad import check_cad
from spec.fasteners import check_fasteners
from spec.records_check import MECHANISMS, check_records


ROOT = Path(__file__).resolve().parents[1]
CAD_HASH = 'a' * 64
EXPECTED_ITEMS = (
    {'S01', 'S01b', 'S02', 'S03', 'S04', 'S05', 'S06'}
    | {f'C{i:02}' for i in range(1, 5)}
    | {f'M{i:02}' for i in range(1, 10)}
    | {f'P{i:02}' for i in range(1, 9)}
)


@pytest.mark.parametrize('old,new', [
    ('E6,나사,육각렌치 원통머리 M3', 'E6,나사,육각렌치 접시머리 M3'),
    ('E6,나사,육각렌치 원통머리 M3', 'E6,나사,육각렌치 원통머리 M30'),
    ('XL430 혼 8 · OpenRB 4 · 카메라 PCB 2', 'XL430 혼 8 · OpenRB 4 · OpenRB 주변 출력물 2'),
    ('M3 일반 육각너트,DIN 934', 'M3 일반 육각너트,ISO 4762'),
])
def test_fastener_changes_are_checked(tmp_path, old, new):
    with (ROOT / 'spec/criteria.toml').open('rb') as file:
        criteria = tomllib.load(file)
    assert check_fasteners(ROOT, criteria)[0] == 'PASS'
    source = (ROOT / 'mechanical/BOM.csv').read_text(encoding='utf-8')
    assert old in source
    (tmp_path / 'mechanical').mkdir()
    (tmp_path / 'mechanical/BOM.csv').write_text(source.replace(old, new, 1), encoding='utf-8')
    assert check_fasteners(tmp_path, criteria)[0] == 'FAIL'


def test_records_reject_partial_stale_and_contradictory_evidence(tmp_path):
    records = tmp_path / 'spec/records'
    records.mkdir(parents=True)
    record = {'revision': 'B22', 'cad_sha256': CAD_HASH, 'status': 'PASS'}
    physical = dict(record, tester='Bench operator', date='2026-01-01',
                    measurement='10 N in both directions for 30 s',
                    result='0.2 mm maximum slip without jacket damage')
    (records / 'P02.json').write_text(json.dumps(physical))
    (records / 'P01.json').write_text(json.dumps(dict(physical, revision='B21')))
    (records / 'P03.json').write_text(json.dumps(physical)[:-1] + ', "status": "FAIL"}')
    (records / 'M01.json').write_text(json.dumps(dict(record, cases={'blink': {'status': 'PASS'}})))
    rows = check_records(tmp_path, 'B22', CAD_HASH)
    assert rows['P02'][0] == 'PASS'
    assert all(rows[item][0] == 'UNVERIFIED' for item in ('P01', 'P03', 'P04', 'M01'))


def test_empty_cad_result_has_no_coverage(tmp_path):
    relative = Path('mechanical/revisions/b22')
    release = tmp_path / relative
    release.mkdir(parents=True)
    for name in ('R5-B22-Assembly.FCStd', 'verification.json'):
        (release / name).symlink_to(ROOT / relative / name)
    data = json.loads((ROOT / relative / 'cad-evidence.json').read_bytes())
    data['head_motion']['pose_samples'] = 0
    (release / 'cad-evidence.json').write_text(json.dumps(data))
    assert check_cad(tmp_path)['C01'][0] == 'UNVERIFIED'


def test_measured_thin_wall_can_fail_before_other_mechanisms_are_measured(tmp_path):
    records = tmp_path / 'spec/records'
    records.mkdir(parents=True)
    (tmp_path / 'spec/criteria.toml').write_text('[M09_print_wall]\nminimum_thickness_mm = 1.2\n')
    (tmp_path / 'wall.json').write_text('{"thickness_mm": 1.01449}')
    measurement = {'name': 'minimum_wall_thickness', 'value': 1.01449, 'unit': 'mm',
                   'source': 'wall.json', 'location': 'Part066 test witness'}
    case = {'status': 'FAIL', 'measurements': [measurement]}
    record = {'revision': 'B22', 'cad_sha256': CAD_HASH, 'status': 'FAIL',
              'cases': {'cable_retention': case}}
    path = records / 'M09.json'
    path.write_text(json.dumps(record))
    assert check_records(tmp_path, 'B22', CAD_HASH)['M09'][0] == 'FAIL'
    record['status'] = case['status'] = 'PASS'
    path.write_text(json.dumps(record))
    assert check_records(tmp_path, 'B22', CAD_HASH)['M09'][0] == 'UNVERIFIED'


def test_low_transmission_angle_needs_torque_budget_and_physical_blinks(tmp_path):
    records = tmp_path / 'spec/records'
    records.mkdir(parents=True)
    (tmp_path / 'spec/criteria.toml').write_text(
        '[M07_transmission]\nmin_angle_deg = 40.0\nmax_stall_fraction = 0.2\n'
    )
    (tmp_path / 'measured.json').write_text('{}')
    evidence = {'required_torque_Nm': .10, 'stall_torque_Nm': .52, 'source': 'measured.json'}
    measured = {'name': 'minimum_transmission_angle', 'value': 23., 'unit': 'deg',
                'source': 'measured.json', 'location': 'Drive crank minimum'}
    cases = {name: {'status': 'N/A', 'reason': 'Fixture has no other transmission linkage'}
             for name in MECHANISMS}
    cases['blink'] = {'status': 'UNVERIFIED', 'measurements': [measured], 'exception': evidence}
    identity = {'revision': 'B22', 'cad_sha256': CAD_HASH}
    mechanical = dict(identity, status='UNVERIFIED', cases=cases)
    (records / 'M07.json').write_text(json.dumps(mechanical))
    physical = dict(identity, status='PASS', tester='Bench operator', date='2026-01-01',
                    measurement='Continuous observation at full travel',
                    result='No binding', cycles=49, binding_events=0)
    (records / 'P03.json').write_text(json.dumps(physical))
    assert check_records(tmp_path, 'B22', CAD_HASH)['M07'][0] == 'UNVERIFIED'

    physical['cycles'] = 50
    (records / 'P03.json').write_text(json.dumps(physical))
    assert check_records(tmp_path, 'B22', CAD_HASH)['M07'][0] == 'PASS'

    evidence['required_torque_Nm'] = .105
    (records / 'M07.json').write_text(json.dumps(mechanical))
    assert check_records(tmp_path, 'B22', CAD_HASH)['M07'][0] == 'FAIL'


def test_p08_requires_full_assembly_without_rework_and_both_service_covers(tmp_path):
    records = tmp_path / 'spec/records'
    records.mkdir(parents=True)
    physical = {'revision': 'B22', 'cad_sha256': CAD_HASH, 'status': 'PASS',
                'tester': 'Bench operator', 'date': '2026-01-01',
                'measurement': 'Full assembly, then open the service covers',
                'result': 'Nuts stayed on the frame', 'full_assembly': True,
                'unplanned_rework_count': 0, 'retained_nut_covers': ['rear-cable']}
    path = records / 'P08.json'
    path.write_text(json.dumps(physical))
    assert check_records(tmp_path, 'B22', CAD_HASH)['P08'][0] == 'UNVERIFIED'
    physical['retained_nut_covers'].append('bottom-board')
    path.write_text(json.dumps(physical))
    assert check_records(tmp_path, 'B22', CAD_HASH)['P08'][0] == 'PASS'


def test_acceptance_command_reports_all_required_items():
    run = subprocess.run([sys.executable, str(ROOT / 'spec/verify.py')], cwd=ROOT,
                         text=True, capture_output=True, timeout=20)
    rows = {}
    for line in run.stdout.splitlines():
        fields = line.split(maxsplit=2)
        if fields and fields[0] in EXPECTED_ITEMS:
            rows[fields[0]] = fields[1]
    assert rows.keys() == EXPECTED_ITEMS, run.stderr + run.stdout
    assert set(rows.values()) <= {'PASS', 'FAIL', 'UNVERIFIED'}
    expected_code = 1 if 'FAIL' in rows.values() else 2 if 'UNVERIFIED' in rows.values() else 0
    assert run.returncode == expected_code
