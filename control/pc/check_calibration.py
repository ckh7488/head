"""Check encoder ticks in Calibration.h without connecting to the OpenRB."""

from argparse import ArgumentParser
from pathlib import Path
import re

from track import AXES, LIMITS

HEADER = Path(__file__).resolve().parents[1] / 'openrb' / 'R5B1' / 'Calibration.h'
NAMES = (*AXES, 'jaw')
UNSET = (-1, -1, -1)
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
        elif not min(low, high) < zero < max(low, high):
            yield f'{prefix} needs zero between its two endpoints.'
        elif nominal_neck and i in (3, 4):
            for end, span, expected in zip(('low', 'high'), (abs(low-zero), abs(high-zero)), LIMITS[i], strict=True):
                measured = span * 360 / 4096
                if abs(measured-abs(expected)) > max(2., abs(expected)*.1):
                    yield f'{prefix} {end} is {measured:.1f}°, expected about {abs(expected):g}°.'


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
