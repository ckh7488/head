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


def test_initializer_requires_six_integer_rows(tmp_path: Path):
    path = tmp_path/'Calibration.h'
    path.write_text('constexpr Calibration calibration[] = {{0, 10, 20}};')
    with pytest.raises(ValueError, match='six'):
        read_rows(path)
