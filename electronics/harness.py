"""Selected harness wire sizes and terminal compatibility."""

from dataclasses import dataclass


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


POWER_WIRE = Wire('Alpha Wire 3055', 18, .823, (.077, .081), 7., 10)
MOTOR_WIRE = Wire('Alpha Wire 6712', 24, .205, (.041, .045), 25., 5)
XT60_TAIL = Wire('Alpha Wire 6718', 12, 3.31, (.115, .119), 1.75, 5)
POWER_LENGTH = .30
MOTOR_LENGTH = .50
XT60_TAIL_LENGTH = .10
INPUT_5V_LOADED = 4.95


def check_wire_sizes():
    for terminal, wire, copper, jacket in (
        ('JST SPH-002T-P0.5S', MOTOR_WIRE, (.05, .22), (.8, 1.5)),
        ('JST SEH-001T-P0.6', MOTOR_WIRE, (.05, .33), (1., 1.9)),
        ('Phoenix 1715721 stranded', POWER_WIRE, (.14, 1.5), None),
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
