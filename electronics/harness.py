"""Selected harness wire sizes and terminal compatibility."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Wire:
    part: str
    awg: int
    copper_mm2: float
    od_in: tuple[float, float]
    ohms_per_1000ft: float
    bend_diameters: int

    @property
    def od_mm(self):
        return tuple(size * 25.4 for size in self.od_in)

    @property
    def hot_ohms_per_m(self):
        return self.ohms_per_1000ft / 304.8 * (1 + .00393 * (70 - 20))


SUPPLY_TAIL = Wire('Alpha Wire 6716', 16, 1.31, (.079, .083), 4.75, 5)
POWER_WIRE = Wire('Alpha Wire 3055', 18, .823, (.077, .081), 7., 10)
J2_SERVICE_WIRE = Wire('Alpha Wire EcoWire 6715', 18, .823, (.065, .069), 7., 5)
MOTOR_WIRE = Wire('Alpha Wire 6712', 24, .205, (.041, .045), 25., 5)
XT60_TAIL = Wire('Alpha Wire 6718', 12, 3.31, (.115, .119), 1.75, 5)
# SPD1168X in local-sense CV mode at 20–30 °C. Round up the service manual
# accuracy, line and load allowances (3 × (0.03% + 10 mV)) and 3 mV ripple.
SUPPLY_SETPOINT = 5.21
SUPPLY_ALLOWANCE = .04
SUPPLY_CURRENT = 7.50
INPUT_5V_LOADED = SUPPLY_SETPOINT - SUPPLY_ALLOWANCE
INPUT_5V_MAX = SUPPLY_SETPOINT + SUPPLY_ALLOWANCE
CUT_LIST = Path(__file__).resolve().parents[1] / 'mechanical/WIRING-CUT-LIST.csv'


def wire_resistance(*numbers, wire):
    with CUT_LIST.open(newline='', encoding='utf-8-sig') as stream:
        cuts = {row['번호']: row for row in csv.DictReader(stream)}
    length_mm = 0
    for number in numbers:
        cut = cuts[number]
        if cut['전선'] != f'{wire.awg} AWG':
            raise ValueError(f'{number} wire gauge differs from {wire.part}')
        length_mm += float(cut['재단 mm'])
    return length_mm / 1000 * wire.hot_ohms_per_m


def check_wire_sizes():
    for terminal, wire, copper, jacket in (
        ('XT30U supply pigtail', SUPPLY_TAIL, (1.0, 1.5), None),
        ('JST SPH-002T-P0.5S', MOTOR_WIRE, (.05, .22), (.8, 1.5)),
        ('JST SEH-001T-P0.6', MOTOR_WIRE, (.05, .33), (1., 1.9)),
        ('WAGO 221 power and signal', POWER_WIRE, (.14, 4.), None),
        ('WAGO 221 XT60 tail', XT60_TAIL, (.14, 4.), None),
        ('WAGO 221 signals', MOTOR_WIRE, (.14, 4.), None),
    ):
        if not copper[0] <= wire.copper_mm2 <= copper[1]:
            raise ValueError(f'{wire.part} is outside {terminal} conductor range')
        if jacket is not None:
            smallest, largest = wire.od_mm
            if not jacket[0] <= smallest <= largest <= jacket[1]:
                raise ValueError(f'{wire.part} is outside {terminal} insulation range')
        print(f'{terminal}: {wire.awg} AWG, {wire.od_mm[0]:.3f}–{wire.od_mm[1]:.3f} mm OD')
