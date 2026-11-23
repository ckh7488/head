"""Screen external protection and a possible current limit at each neck header."""

from argparse import ArgumentParser
from math import isfinite

from power_check import (
    LEGACY_NECK_TRUNK_OHM, NECK_NORMAL_A, SUPPLY_CURRENT, XL330_STALL_A, XL430_STALL_A,
    check_net, hub_5v_current, load, neck_voltages,
)

COMPACT_5V_FLOOR = 5.14
NECK_SOURCE_LIMIT = 5.00
NECK_SOURCE_MIN_V = 11.10
XL430_MIN_V = 10.50
EH_22_AWG_CATALOG_A = 3.00
F2_NOMINAL_A = 4.00

# TI INA301A2 Electrical Characteristics and Vishay WSLP2512, 5 mΩ, 1%.
# Use a 100 °C excursion from the 25 °C reference for specified drift terms.
SHUNT_OHM = .005
SHUNT_MIN_OHM = SHUNT_OHM * .99 * (1 - 110e-6 * 100)
SHUNT_MAX_OHM = SHUNT_OHM * 1.01 * (1 + 110e-6 * 100)
LOAD_SWITCH_HOT_BUDGET_OHM = .006  # Provisional drop budget at actual load and bias.
EFUSE_HOT_OHM = .045  # TPS259470L, SLVSFC9C §6.5 at 3 A.


def five_volt_trip_range():
    setting_ohm = 22_100
    setting_tolerance = .001 + 10e-6 * 100  # 0.1%, 10 ppm/°C resistor.
    gain = 50
    gain_tolerance = .0015 + 10e-6 * 100 + .0001  # Includes nonlinearity.
    input_offset_v = (50e-6 + .5e-6 * 100 + 7 / 10**(106 / 20) + .27 * 10e-6)
    offset_v = .004 + gain * (1 + gain_tolerance) * input_offset_v
    lower = ((setting_ohm * (1 - setting_tolerance) * 79.2e-6 - offset_v)
             / (gain * (1 + gain_tolerance) * SHUNT_MAX_OHM))
    upper = ((setting_ohm * (1 + setting_tolerance) * 80.8e-6 + offset_v)
             / (gain * (1 - gain_tolerance) * SHUNT_MIN_OHM))
    return lower, upper


def efuse_trip_range(tabulated_min, tabulated_max):
    # §6.5 tabulated at VIN = 12 V and exact RILM. Apply Eq. (7) sensitivity
    # for a 0.1%, 25 ppm/°C resistor and up to 100 °C from the reference.
    resistor_tolerance = .001 + 25e-6 * 100
    return tabulated_min / (1 + resistor_tolerance), tabulated_max / (1 - resistor_tolerance)


def check_protection(service_loop_ohm):
    if not isfinite(service_loop_ohm) or service_loop_ohm < 0:
        raise ValueError('service loop resistance must be finite and nonnegative')
    board, parts = load('servo-hub', 'R5_Servo_Hub')
    check_net(parts, 'J1', {1: 'GND', 2: '5V_IN'})
    check_net(parts, 'J2', {1: 'GND', 2: '12V_IN'})
    if parts['F2'].GetValue() != '4A MINI':
        raise ValueError('F2 no longer matches the 4 A MINI fuse model')
    for output in ('J7', 'J8'):
        if str(parts[output].GetFPID().GetLibItemName()) != 'JST_EH_B3B-EH-A_1x03_P2.50mm_Vertical':
            raise ValueError(f'{output} no longer matches the modeled JST EH header')

    five_load = hub_5v_current(ph_fault=True) + XL330_STALL_A
    five_min, five_max = five_volt_trip_range()
    neck_min, neck_max = efuse_trip_range(3.960, 4.840)  # 750 Ω, ahead of XT60.
    eh_min, eh_max = efuse_trip_range(1.800, 2.200)  # 1.65 kΩ, per header.
    print(f'5 V INA301A2 trip estimate: {five_min:.3f}–{five_max:.3f} A; '
          f'required window {five_load:.3f}–{SUPPLY_CURRENT:.2f} A')
    print(f'Neck source TPS259470L trip estimate: {neck_min:.3f}–{neck_max:.3f} A; '
          f'required window {NECK_NORMAL_A:.2f}–{NECK_SOURCE_LIMIT:.2f} A')
    print(f'J7/J8 TPS259470L trip estimate: {eh_min:.3f}–{eh_max:.3f} A per header; '
          f'screening window {XL430_STALL_A:.2f}–{EH_22_AWG_CATALOG_A:.2f} A '
          '(catalog upper reference at 22 AWG)')
    # Littelfuse specifies a maximum opening time at 135%, with no maximum
    # at 110%. Do not interpolate a maximum opening time at the source cap.
    print(f'F2 at the source cap: {NECK_SOURCE_LIMIT / F2_NOMINAL_A:.0%} of rating; '
          f'first tabulated maximum opening time is at {1.35 * F2_NOMINAL_A:.2f} A')

    five_upstream = COMPACT_5V_FLOOR + five_load * (SHUNT_MAX_OHM + LOAD_SWITCH_HOT_BUDGET_OHM)
    neck_upstream = NECK_SOURCE_MIN_V + NECK_NORMAL_A * EFUSE_HOT_OHM
    print(f'Loaded converter floors before the protection components: '
          f'{five_upstream:.3f} V (5 V rail), {neck_upstream:.3f} V (neck rail)')

    trip_windows_fit = (
        five_load < five_min <= five_max <= SUPPLY_CURRENT
        and XL430_STALL_A + eh_max < neck_min <= neck_max <= NECK_SOURCE_LIMIT
        and XL430_STALL_A < eh_min <= eh_max < EH_22_AWG_CATALOG_A
    )
    motor_voltages = []
    branch_drop = XL430_STALL_A * EFUSE_HOT_OHM
    for output, _, baseline in neck_voltages(board, parts, source_v=NECK_SOURCE_MIN_V,
                                             trunk_ohm=LEGACY_NECK_TRUNK_OHM):
        allowed_ohm = (baseline - XL430_MIN_V - branch_drop) / NECK_NORMAL_A
        voltage = baseline - branch_drop - NECK_NORMAL_A * service_loop_ohm
        motor_voltages.append(voltage)
        print(f'{output}: {voltage:.4f} V at the motor; '
              f'{1000 * allowed_ohm:.2f} mΩ maximum additional service loop resistance')
    fault_trunk_a = XL430_STALL_A + eh_max
    for output, _, baseline in neck_voltages(board, parts, source_v=NECK_SOURCE_MIN_V,
                                             trunk_ohm=LEGACY_NECK_TRUNK_OHM, trunk_a=fault_trunk_a):
        voltage = baseline - branch_drop - fault_trunk_a * service_loop_ohm
        source_floor = NECK_SOURCE_MIN_V + XL430_MIN_V - voltage
        print(f'{output} while the other neck branch limits: {voltage:.4f} V; '
              f'{source_floor:.4f} V minimum after the common protector')
    print('Bench qualification pending for trigger accuracy, short-circuit peaks, heating and regeneration.')
    return trip_windows_fit and min(motor_voltages) >= XL430_MIN_V


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--neck-service-loop-mohm', required=True, type=float,
                        help='Additional hot loop resistance above the historical A3-length baseline')
    args = parser.parse_args()
    if not isfinite(args.neck_service_loop_mohm) or args.neck_service_loop_mohm < 0:
        parser.error('--neck-service-loop-mohm must be finite and nonnegative')
    if not check_protection(args.neck_service_loop_mohm / 1000):
        raise SystemExit('Source protection static screen failed')


if __name__ == '__main__':
    main()
