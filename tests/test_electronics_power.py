"""Exercise the built hub netlist and source voltage calculations at the CLI boundary."""

from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PYTHON = Path('/usr/bin/python3')
CHECKER = ROOT / 'electronics' / 'power_check.py'
PROTECTION_CHECKER = ROOT / 'electronics' / 'protection_check.py'


@pytest.fixture(scope='module')
def power_checker():
    if not SYSTEM_PYTHON.is_file() or subprocess.run(
            [SYSTEM_PYTHON, '-c', 'import pcbnew'], capture_output=True).returncode:
        pytest.skip('KiCad Python bindings unavailable')
    return [SYSTEM_PYTHON, CHECKER]


def motor_voltages(output):
    return [float(value) for value in re.findall(r'([\d.]+) V at the motor', output)]


def test_default_uses_b25_nominal_voltage_and_the_a4_service_wires(power_checker):
    result = subprocess.run(power_checker, capture_output=True, text=True, check=True)
    nominal = subprocess.run([*power_checker, '--nominal'], capture_output=True, text=True, check=True)
    assert result.stdout == nominal.stdout
    assert '5.89 A on 5 V (4.42 A at the hub), 2.80 A on 12 V' in result.stdout
    assert '12.77 mΩ before cup lengths, 17.86 mΩ using all listed stock wire' in result.stdout
    assert motor_voltages(result.stdout) == pytest.approx(
        [4.205, 4.197, 4.213, 4.480, 11.553, 11.472], abs=.001)
    assert 'Measure adapter and motor terminals' in result.stdout


def test_bench_model_load_and_branch_limits(power_checker):
    result = subprocess.run([*power_checker, '--bench'], capture_output=True, text=True, check=True)
    limits = re.search(r'PH current estimate: ([\d.]+)–([\d.]+) A', result.stdout)
    assert limits is not None
    lower, upper = map(float, limits.groups())
    assert 1.55 < lower <= upper < 2.0
    assert 'PH current qualification required: fitted lower limit 1.539 A' in result.stdout
    assert motor_voltages(result.stdout) == pytest.approx([4.334, 4.325, 4.341, 4.621], abs=.001)


def test_nominal_5v_input_fails_the_historical_stress_screen(power_checker):
    result = subprocess.run([*power_checker, '--input-5v', '5.0'], capture_output=True, text=True)
    assert result.returncode == 1
    assert '5.1148 V' in result.stdout
    assert 'Insufficient modeled voltage at J4, J5, J6' in result.stderr


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


def test_source_protection_screen_keeps_j8_above_floor_at_20_milliohms(power_checker):
    command = [power_checker[0], PROTECTION_CHECKER, '--neck-service-loop-mohm']
    result = subprocess.run([*command, '20'], capture_output=True, text=True, check=True)
    for pattern in (
        r'5 V INA301A2 trip estimate: ([\d.]+)–([\d.]+) A; required window ([\d.]+)–([\d.]+) A',
        r'Neck source TPS259470L trip estimate: ([\d.]+)–([\d.]+) A; required window ([\d.]+)–([\d.]+) A',
        r'J7/J8 TPS259470L trip estimate: ([\d.]+)–([\d.]+) A per header; '
        r'screening window ([\d.]+)–([\d.]+) A \(catalog upper reference at 22 AWG\)',
    ):
        values = re.search(pattern, result.stdout)
        assert values is not None
        min_trip, max_trip, normal_load, max_allowed = map(float, values.groups())
        assert normal_load < min_trip <= max_trip < max_allowed
    assert 'first tabulated maximum opening time is at 5.40 A' in result.stdout
    normal = re.search(r'J8: ([\d.]+) V at the motor; ([\d.]+) mΩ maximum', result.stdout)
    assert normal is not None
    voltage, service_budget = map(float, normal.groups())
    assert voltage == pytest.approx(10.516, abs=.001)
    assert service_budget == pytest.approx(25.70, abs=.02)
    fault = re.search(r'J8 while the other neck branch limits: ([\d.]+) V; '
                      r'([\d.]+) V minimum after the common protector', result.stdout)
    assert fault is not None
    voltage, source_floor = map(float, fault.groups())
    assert voltage == pytest.approx(10.435, abs=.001)
    assert source_floor == pytest.approx(11.165, abs=.001)
    assert 'Bench qualification pending' in result.stdout

    result = subprocess.run([*command, '26'], capture_output=True, text=True)
    assert result.returncode == 1
    assert 'J8: 10.4992 V at the motor' in result.stdout
    assert 'Source protection static screen failed' in result.stderr


@pytest.mark.parametrize('value', ['nan', 'inf', '-1'])
def test_source_protection_screen_rejects_invalid_resistance(power_checker, value):
    result = subprocess.run([power_checker[0], PROTECTION_CHECKER, '--neck-service-loop-mohm', value],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert 'must be finite and nonnegative' in result.stderr
