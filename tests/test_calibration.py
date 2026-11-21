from pathlib import Path

import pytest

from check_calibration import HEADER, UNSET, issues, read_rows
from conftest import CALIBRATED


def replaced_axis(index, row):
    rows = list(CALIBRATED)
    rows[index] = row
    return rows


def test_repository_calibration_rows_are_valid_or_unset():
    rows = read_rows(HEADER)
    assert len(rows) == 6
    assert not list(issues(rows))


def test_unset_and_nominal_calibrations_are_valid():
    assert not list(issues((UNSET,)*6, nominal_neck=True))
    assert not list(issues(CALIBRATED, nominal_neck=True))


@pytest.mark.parametrize(('axis', 'row'), [
    (0, (-1, 2048, 2200)), (1, (2200, 2048, 4096)), (3, (2050, 2048, 2100)),
    (2, (1900, 2000, 3000)), (5, (2000, 2000, 1997)),
])
def test_rejects_bad_tick_rows(axis, row):
    assert len(list(issues(replaced_axis(axis, row)))) == 1


def test_nominal_check_flags_31_degrees_when_57_9_was_expected():
    shorter = replaced_axis(3, (1695, 2048, 2707))
    assert not list(issues(shorter))
    assert list(issues(shorter, nominal_neck=True)) == [
        'ID 4 neck-yaw low is 31.0°, expected about 57.9°.',
    ]

@pytest.mark.parametrize(('axis', 'row', 'name', 'ticks'), [
    (0, (1828, 2048, 2267), 'eye-yaw', 219), (1, (2131, 2048, 1964), 'eye-pitch', 83),
    (3, (1389, 2048, 2708), 'neck-yaw', 659),
    (3, (2707, 2048, 1388), 'neck-yaw', 659),
    (3, (1374, 2048, 2722), 'neck-yaw', 659),
])
def test_calibration_leaves_eight_ticks_inside_cad_range(axis, row, name, ticks):
    assert list(issues(replaced_axis(axis, row))) == [
        f'ID {axis+1} {name} needs both endpoints within {ticks} ticks of zero.',
    ]


@pytest.mark.parametrize('opening_tick', [1977, 1938, 2023])
def test_jaw_calibration_rejects_more_than_22_ticks(opening_tick):
    assert list(issues(replaced_axis(5, (2000, 2000, opening_tick)))) == [
        'ID 6 jaw opening exceeds 2.0° (22 ticks). Recalibrate the jaw.',
    ]


@pytest.mark.parametrize('closed_tick', [975, 3025])
def test_blink_calibration_rejects_more_than_1024_ticks(closed_tick):
    assert list(issues(replaced_axis(2, (2000, 2000, closed_tick)))) == [
        'ID 3 blink closing exceeds 90° (1024 ticks). Recalibrate the eyelids.',
    ]


@pytest.mark.parametrize('row', [(2203, 2048, 2013), (1893, 2048, 2083),
                                 (2203, 2048, 1980), (1893, 2048, 2116)])
def test_pitch_calibration_rejects_more_than_34_ticks_of_positive_travel(row):
    assert list(issues(replaced_axis(4, row))) == [
        'ID 5 neck-pitch positive travel exceeds 2.99° (34 ticks). Recalibrate the positive endpoint.',
    ]


@pytest.mark.parametrize('row', [(2203, 2048, 2014), (1893, 2048, 2082)])
def test_pitch_calibration_accepts_nominal_155_tick_negative_travel(row):
    assert not list(issues(replaced_axis(4, row), nominal_neck=True))


@pytest.mark.parametrize('row', [(2204, 2048, 2014), (1892, 2048, 2082),
                                 (2248, 2048, 2014), (1848, 2048, 2082)])
def test_pitch_calibration_rejects_more_than_155_ticks_of_negative_travel(row):
    assert list(issues(replaced_axis(4, row))) == [
        'ID 5 neck-pitch negative travel exceeds the 13.62° endpoint (155 ticks). Recalibrate the negative endpoint.',
    ]


def test_initializer_requires_six_integer_rows(tmp_path: Path):
    path = tmp_path/'Calibration.h'
    path.write_text('constexpr Calibration calibration[] = {{0, 10, 20}};')
    with pytest.raises(ValueError, match='six'):
        read_rows(path)
