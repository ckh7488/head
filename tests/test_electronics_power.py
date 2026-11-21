"""Exercise the built hub netlist and source voltage calculations at the CLI boundary."""

from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PYTHON = Path('/usr/bin/python3')
CHECKER = ROOT / 'electronics' / 'power_check.py'


@pytest.fixture(scope='module')
def power_checker():
    if not SYSTEM_PYTHON.is_file() or subprocess.run(
            [SYSTEM_PYTHON, '-c', 'import pcbnew'], capture_output=True).returncode:
        pytest.skip('KiCad Python bindings unavailable')
    return [SYSTEM_PYTHON, CHECKER]


def test_a3_model_load_and_branch_limits(power_checker):
    result = subprocess.run(power_checker, capture_output=True, text=True, check=True)
    limits = re.search(r'PH current estimate: ([\d.]+)–([\d.]+) A', result.stdout)
    assert limits is not None
    lower, upper = map(float, limits.groups())
    assert 1.55 < lower <= upper < 2.0
    assert 'PH current qualification required: fitted lower limit 1.539 A' in result.stdout
    voltages = [float(value) for value in re.findall(r'([\d.]+) V at the motor', result.stdout)]
    assert len(voltages) == 6
    eye_yaw, eye_pitch, blink, jaw, neck_yaw, neck_pitch = voltages
    assert 4.30 <= min(eye_yaw, eye_pitch, blink, jaw) <= max(eye_yaw, eye_pitch, blink, jaw) <= 5.25
    assert min(neck_yaw, neck_pitch) >= 10.50


def test_former_adapter_floor_fails_5v_branches(power_checker):
    result = subprocess.run([*power_checker, '--input-5v', '4.75'], capture_output=True, text=True)
    assert result.returncode == 1
    assert 'Insufficient modeled voltage at J4, J5, J6, ID6' in result.stderr


def test_short_source_tail_preserves_healthy_ph_branches_during_one_fault(power_checker):
    command = [*power_checker, '--ph-fault', '--input-5v', '5.14']
    long_tail = subprocess.run(command, capture_output=True, text=True)
    assert long_tail.returncode == 1
    assert '5.1572 V' in long_tail.stdout
    assert 'Insufficient modeled voltage at J4, J5, J6' in long_tail.stderr

    short_tail = subprocess.run([*command, '--tail-mm', '100'], capture_output=True, text=True, check=True)
    assert '6.66 A concurrent load with one PH branch in current limit' in short_tail.stdout
    assert '5.1200 V' in short_tail.stdout
