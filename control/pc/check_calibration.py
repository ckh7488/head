"""Check encoder ticks in Calibration.h without connecting to the OpenRB."""

from argparse import ArgumentParser
from pathlib import Path
import re

from track import AXES, JAW_MAX_DEGREES, LIMITS

HEADER = Path(__file__).resolve().parents[1] / 'openrb' / 'R5B1' / 'Calibration.h'
NAMES = (*AXES, 'jaw')
UNSET = (-1, -1, -1)
JAW_MAX_TICKS = int(JAW_MAX_DEGREES * 4096 / 360)
NECK_YAW_AXIS = AXES.index('neck-yaw')
NECK_YAW_LIMIT_TICKS = 659
NECK_YAW_LIMIT_DEGREES = NECK_YAW_LIMIT_TICKS * 360 / 4096
NECK_PITCH_AXIS = AXES.index('neck-pitch')
PITCH_MAX_DEGREES = LIMITS[NECK_PITCH_AXIS][1]
PITCH_MAX_TICKS = int(PITCH_MAX_DEGREES * 4096 // 360)
PITCH_NEGATIVE_DEGREES = abs(LIMITS[NECK_PITCH_AXIS][0])
PITCH_NEGATIVE_TICKS = int((PITCH_NEGATIVE_DEGREES * 4096 + 180) // 360)
EYE_LIMITS_TICKS = tuple(int(top * 4096 // 360) - 8 for _, top in LIMITS[:2])
ROW = re.compile(r'\{\s*(-?[0-9]+)\s*,\s*(-?[0-9]+)\s*,\s*(-?[0-9]+)\s*\}')


def read_rows(path):
    text = re.sub(r'//[^\n]*|/\*.*?\*/', '', path.read_text(), flags=re.S)
    table = re.search(r'\bcalibration\s*\[\s*[0-9]*\s*\]\s*=\s*\{(.*?)\};', text, re.S)
    if table is None or not re.fullmatch(r'(?:\s*'+ROW.pattern+r'\s*,){5}\s*'+ROW.pattern+r'\s*,?\s*', table[1]):
        raise ValueError('Expected six low, zero, high rows in the calibration array.')
    return tuple(tuple(map(int, row)) for row in ROW.findall(table[1]))


def issues(rows, nominal_neck=False):
    for i, (name, (low, zero, high)) in enumerate(zip(NAMES, rows, strict=True)):
        if (low, zero, high) == UNSET:
            continue
        prefix = f'ID {i+1} {name}'
        if not all(0 <= tick <= 4095 for tick in (low, zero, high)):
            yield f'{prefix} needs three ticks in 0–4095.'
        elif i in (2, 5):
            if low != zero or abs(high-zero) < 4:
                yield f'{prefix} needs low equal to zero and a high at least 4 ticks away.'
            elif i == 5 and abs(high-zero) > JAW_MAX_TICKS:
                yield f'{prefix} opening exceeds {JAW_MAX_DEGREES}° ({JAW_MAX_TICKS} ticks). Recalibrate the jaw.'
        elif not min(low, high) < zero < max(low, high):
            yield f'{prefix} needs zero between its two endpoints.'
        elif i < len(EYE_LIMITS_TICKS) and max(abs(low-zero), abs(high-zero)) > EYE_LIMITS_TICKS[i]:
            yield f'{prefix} needs both endpoints within {EYE_LIMITS_TICKS[i]} ticks of zero.'
        elif i == NECK_YAW_AXIS and max(abs(low-zero), abs(high-zero)) > NECK_YAW_LIMIT_TICKS:
            yield f'{prefix} needs both endpoints within {NECK_YAW_LIMIT_TICKS} ticks of zero.'
        elif i == NECK_PITCH_AXIS and abs(high-zero) > PITCH_MAX_TICKS:
            yield (f'{prefix} positive travel exceeds {PITCH_MAX_DEGREES:g}° '
                   f'({PITCH_MAX_TICKS} ticks). Recalibrate the positive endpoint.')
        elif i == NECK_PITCH_AXIS and abs(low-zero) > PITCH_NEGATIVE_TICKS:
            yield (f'{prefix} negative travel exceeds the {PITCH_NEGATIVE_DEGREES:g}° endpoint '
                   f'({PITCH_NEGATIVE_TICKS} ticks). Recalibrate the negative endpoint.')
        elif nominal_neck and i in (NECK_YAW_AXIS, NECK_PITCH_AXIS):
            limits = (NECK_YAW_LIMIT_DEGREES,)*2 if i == NECK_YAW_AXIS else LIMITS[i]
            for end, span, expected in zip(('low', 'high'), (abs(low-zero), abs(high-zero)), limits, strict=True):
                measured = span * 360 / 4096
                if abs(measured-abs(expected)) > max(2., abs(expected)*.1):
                    yield f'{prefix} {end} is {measured:.1f}°, expected about {abs(expected):.3g}°.'


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('header', nargs='?', type=Path, default=HEADER)
    parser.add_argument('--nominal-neck', action='store_true',
                        help='Compare the direct-drive neck with its full nominal angles')
    args = parser.parse_args()
    try:
        rows = read_rows(args.header)
        errors = list(issues(rows, args.nominal_neck))
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    if errors:
        parser.exit(1, '\n'.join(errors)+'\n')
    print(f'{len(rows)-rows.count(UNSET)} of {len(rows)} axes calibrated. Unset axes stay locked.')


if __name__ == '__main__':
    main()
