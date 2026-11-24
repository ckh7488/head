"""Regression checks for the B25 acceptance route and bound witnesses."""

import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_b25_acceptance_lists_all_criteria():
    run = subprocess.run([sys.executable, 'spec/verify.py', '--revision', 'B25'], cwd=ROOT,
                         capture_output=True, text=True, timeout=20)
    assert run.stdout.startswith('R5 B25 인수 검사'), run.stderr + run.stdout
    rows = {fields[0]: fields[1] for line in run.stdout.splitlines()[1:] if len(fields := line.split()) >= 2}
    expected = {'S01', 'S01b', 'S02', 'S03', 'S04', 'S05', 'S06'}
    expected.update(f'{prefix}{i:02}' for prefix, count in (('C', 4), ('M', 9), ('P', 8))
                    for i in range(1, count + 1))
    assert (expected <= rows.keys())
    assert run.returncode == (1 if 'FAIL' in rows.values() else 2 if 'UNVERIFIED' in rows.values() else 0)


def test_b25_sightline_requires_current_inputs_to_report_failure(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'spec'))
    b25 = importlib.import_module('b25')
    criteria = {'S02_look_up': {'head_height_m': 1.4}, 'S01_walk_by': {'camera_hfov_deg': 106.}}
    firmware = tmp_path / b25.FIRMWARE
    firmware.parent.mkdir(parents=True)
    firmware.write_bytes(b'firmware fixture')
    path = tmp_path / b25.RELEASE / 'sightlines.json'
    path.parent.mkdir(parents=True)
    cad_hash = 'a' * 64
    report = {'cad_sha256': cad_hash, 'firmware_sha256': hashlib.sha256(firmware.read_bytes()).hexdigest(),
              'scene': criteria['S02_look_up'], 'camera_hfov_deg': 106., 'camera_in_frame': True,
              'camera_opaque_contacts': [], 'status': 'pass', 'pupils': [
                  {'part': part, 'required_elevation_deg': 10., 'max_elevation_deg': 15.,
                   'eye_pitch_solution_deg': -2., 'opaque_contacts': []} for part in ('Part031', 'Part035')]}
    path.write_text(json.dumps(report))
    check = lambda: b25.checked(b25.sightlines, tmp_path, criteria, cad_hash)[0]
    assert check() == 'PASS'

    report['pupils'][0]['opaque_contacts'].append('Part073')
    path.write_text(json.dumps(report))
    assert check() == 'FAIL'

    firmware.write_bytes(b'updated firmware fixture')
    assert check() == 'UNVERIFIED'
