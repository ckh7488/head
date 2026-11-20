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


def test_nominal_check_flags_31_degrees_when_60_was_expected():
    shorter = replaced_axis(3, (1695, 2048, 2731))
    assert not list(issues(shorter))
    assert list(issues(shorter, nominal_neck=True)) == [
        'ID 4 neck-yaw low is 31.0°, expected about 60°.',
    ]


@pytest.mark.parametrize('opening_tick', [1908, 1852, 2092])
def test_jaw_calibration_rejects_more_than_91_ticks(opening_tick):
    assert list(issues(replaced_axis(5, (2000, 2000, opening_tick)))) == [
        'ID 6 jaw opening exceeds 8° (91 ticks). Recalibrate the jaw.',
    ]


@pytest.mark.parametrize('row', [(2219, 2048, 1979), (1877, 2048, 2117)])
def test_pitch_calibration_rejects_more_than_68_ticks_of_positive_travel(row):
    assert list(issues(replaced_axis(4, row))) == [
        'ID 5 neck-pitch positive travel exceeds 6° (68 ticks). Recalibrate the positive endpoint.',
    ]


def test_pitch_positive_limit_does_not_change_negative_travel():
    assert not list(issues(replaced_axis(4, (2276, 2048, 1980))))


def test_initializer_requires_six_integer_rows(tmp_path: Path):
    path = tmp_path/'Calibration.h'
    path.write_text('constexpr Calibration calibration[] = {{0, 10, 20}};')
    with pytest.raises(ValueError, match='six'):
        read_rows(path)
