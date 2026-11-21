"""Check board pin assignments and bound the servo supply drop at stall current."""

from argparse import ArgumentParser
from heapq import heappop, heappush
from math import isfinite, pi
from pathlib import Path

import pcbnew

from harness import (
    INPUT_5V_LOADED, INPUT_5V_MAX, MOTOR_WIRE, POWER_WIRE, SUPPLY_CURRENT, SUPPLY_TAIL,
    XT60_TAIL, check_wire_sizes, wire_resistance,
)

HERE = Path(__file__).resolve().parent
HOT_COPPER_OHM_MM = 2.06e-5
HUB_COPPER_MM = .060
HUB_THICKNESS_MM = 1.6
VIA_PLATING_MM = .020
XL330_STALL_A = 1.55
XL430_STALL_A = 1.40
HUB_IDLE_A = .010
PH_RATING_A = 2.0
PH_LIMIT_OHMS = 61.9
PH_LIMIT_TOLERANCE = .003
PH_SWITCH_HOT_OHM = .035
XL330_MIN_V = 4.27
XL330_MAX_V = 5.25
# Fuse and contact limits include installation and ageing allowances. Verify them hot on the bench.
SOURCE_CONTACT_OHM = .012
HUB_XT30_CONTACT_OHM = .004
HUB_FUSE_OHM = .035
JAW_FUSE_OHM = .110
JAW_HOLDER_LEAD_M = .127
PH_EH_CONTACT_OHM = .090
JAW_EH_CONTACT_OHM = .045


def load(project, board):
    pcb = pcbnew.LoadBoard(str(HERE / project / f'{board}.kicad_pcb'))
    return pcb, {f.GetReference(): f for f in pcb.GetFootprints()}


def check_net(parts, reference, expected):
    for pin, net in expected.items():
        actual = {pad.GetNetname() for pad in parts[reference].Pads() if pad.GetNumber() == str(pin)}
        if actual != {f'/{net}'}:
            raise ValueError(f'{reference} pin {pin}: expected {net}, found {actual}')


def node(vector):
    return vector.x, vector.y


def copper_path(board, parts, net, start, end):
    graph = {}

    def edge(a, b, ohms):
        graph.setdefault(a, []).append((b, ohms))
        graph.setdefault(b, []).append((a, ohms))

    for item in board.GetTracks():
        if item.GetNetname() != f'/{net}':
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            a = node(item.GetPosition())
            area = pi * VIA_PLATING_MM * (pcbnew.ToMM(item.GetDrillValue()) + VIA_PLATING_MM)
            edge((*a, pcbnew.F_Cu), (*a, pcbnew.B_Cu), HOT_COPPER_OHM_MM * HUB_THICKNESS_MM / area)
        else:
            a, b, layer = node(item.GetStart()), node(item.GetEnd()), item.GetLayer()
            ohms = HOT_COPPER_OHM_MM * item.GetLength() / item.GetWidth() / HUB_COPPER_MM
            edge((*a, layer), (*b, layer), ohms)

    def at(part, pin):
        return {(*node(pad.GetPosition()), layer) for pad in parts[part].Pads()
                if pad.GetNumber() == str(pin) for layer in (pcbnew.F_Cu, pcbnew.B_Cu)
                if pad.IsOnLayer(layer)}

    for part in parts:
        for pad in parts[part].Pads():
            if pad.GetNetname() == f'/{net}' and pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                a = node(pad.GetPosition())
                area = pi * VIA_PLATING_MM * (pcbnew.ToMM(pad.GetDrillSize().x) + VIA_PLATING_MM)
                edge((*a, pcbnew.F_Cu), (*a, pcbnew.B_Cu), HOT_COPPER_OHM_MM * HUB_THICKNESS_MM / area)

    targets = at(*end)
    queue = [(0., a) for a in at(*start)]
    visited = set()
    while queue:
        distance, a = heappop(queue)
        if a in targets:
            return distance
        if a in visited:
            continue
        visited.add(a)
        for b, ohms in graph.get(a, []):
            if b not in visited:
                heappush(queue, (distance+ohms, b))
    raise ValueError(f'{net} copper path is missing from {start} to {end}')


def ph_current_limits():
    # TPS2557 §7.5 specifies 1.590–1.960 A at exactly 61.9 kΩ. Apply the
    # local resistor sensitivity from §10.2.1.2.2, including temperature drift
    # of the 0.1% / 25 ppm/°C resistor. Check the broader fitted upper curve too.
    lo_r = PH_LIMIT_OHMS * (1 - PH_LIMIT_TOLERANCE)
    hi_r = PH_LIMIT_OHMS * (1 + PH_LIMIT_TOLERANCE)
    nominal_anchored_min = 1.590 * (PH_LIMIT_OHMS / hi_r)**1.0708
    curve_min = 127.981 / hi_r**1.0708
    curve_max = 99.038 / lo_r**.947
    return nominal_anchored_min, curve_min, max(1.960 * (PH_LIMIT_OHMS / lo_r)**.947, curve_max)


def check_hub(input_5v=INPUT_5V_LOADED, *, ph_fault=False, tail_mm=None):
    board, parts = load('servo-hub', 'R5_Servo_Hub')
    check_net(parts, 'J1', {1: 'GND', 2: '5V_IN'})
    check_net(parts, 'J2', {1: '12V_IN', 2: 'GND'})
    check_net(parts, 'J3', {1: 'GND', 2: 'DXL_CTL'})
    check_net(parts, 'F1', {1: '5V_IN', 2: '5V_EYES'})
    check_net(parts, 'F2', {1: '12V_IN', 2: '12V_NECK'})
    if parts['F1'].GetValue() != '7.5A MINI':
        raise ValueError('5 V hub fuse must match the 7.5 A thermal and resistance budget')
    lo_limit, curve_min, hi_limit = ph_current_limits()
    if not XL330_STALL_A < lo_limit <= hi_limit < PH_RATING_A:
        raise ValueError('PH branch current limit must pass a normal stall and protect the 2 A contact')
    total_hub_a = 3 * XL330_STALL_A + HUB_IDLE_A
    fault_hub_a = total_hub_a - XL330_STALL_A + hi_limit
    if fault_hub_a + XL330_STALL_A >= SUPPLY_CURRENT:
        raise ValueError('The 5 V source cannot supply simultaneous stalls plus one limited PH fault')
    if ph_fault:
        total_hub_a = fault_hub_a
    total_source_a = total_hub_a + XL330_STALL_A
    load_case = ' with one PH branch in current limit' if ph_fault else ''
    print(f'5 V source: {input_5v:.3f} V loaded floor, {INPUT_5V_MAX:.3f} V ceiling, '
          f'{total_source_a:.2f} A concurrent load{load_case}')
    print(f'PH current estimate: {lo_limit:.3f}–{hi_limit:.3f} A per channel')
    if curve_min < XL330_STALL_A:
        print(f'PH current qualification required: fitted lower limit {curve_min:.3f} A '
              f'is below modeled {XL330_STALL_A:.2f} A load')
    if tail_mm is None:
        tail_ohms = wire_resistance('W33', 'W34', wire=SUPPLY_TAIL)
    else:
        tail_ohms = 2 * tail_mm / 1000 * SUPPLY_TAIL.hot_ohms_per_m
    source_loop = wire_resistance('W1', 'W2', wire=POWER_WIRE) + tail_ohms
    junction_v = input_5v - total_source_a * (source_loop + SOURCE_CONTACT_OHM)
    hub_loop = wire_resistance('W3', 'W4', wire=POWER_WIRE) + HUB_XT30_CONTACT_OHM + HUB_FUSE_OHM
    lead = copper_path(board, parts, '5V_IN', ('J1', 2), ('F1', 1))
    neck_a = 2 * XL430_STALL_A
    voltages = {}
    for i, wires in enumerate((('W13', 'W14'), ('W16', 'W17'), ('W19', 'W20')), 1):
        switch, resistor, cap, output = f'U{i}', f'R{i+3}', f'C{i+2}', f'J{i+3}'
        ilim, rail = f'ILIM{i}', f'5V_ID{i}'
        check_net(parts, switch, {1: 'GND', 2: '5V_EYES', 3: '5V_EYES', 4: '5V_EYES',
                                  5: ilim, 6: rail, 7: rail, 9: 'GND'})
        check_net(parts, resistor, {1: ilim, 2: 'GND'})
        check_net(parts, cap, {1: '5V_EYES', 2: 'GND'})
        if parts[switch].GetValue() != 'TPS2557' or parts[resistor].GetValue() != '61.9k 0.1%':
            raise ValueError(f'{output} limiter does not match the modeled part and tolerance')
        check_net(parts, output, {1: 'GND', 2: rail, 3: 'DXL_BUS'})
        feed = max(copper_path(board, parts, '5V_EYES', ('F1', 2), (switch, pin)) for pin in (2, 3))
        branch = max(copper_path(board, parts, rail, (switch, pin), (output, 2)) for pin in (6, 7))
        ground = copper_path(board, parts, 'GND', (output, 1), ('J1', 1))
        branch_loop = branch + PH_SWITCH_HOT_OHM + wire_resistance(*wires, wire=MOTOR_WIRE) + PH_EH_CONTACT_OHM
        # Charge the whole hub current to the entire positive feed and both rails
        # to the explicit ground return. With one fault, place it on a different
        # branch from the healthy branch whose motor voltage is being checked.
        voltage = (junction_v - total_hub_a * (hub_loop + lead + feed)
                   - (total_hub_a + neck_a) * ground - XL330_STALL_A * branch_loop)
        print(f'{output}: {1000*(lead+feed+branch):.2f} mΩ positive PCB path, '
              f'{1000*ground:.2f} mΩ return, {voltage:.3f} V at the motor')
        voltages[output] = voltage

    # Only W1–W2 and the supply leads carry the combined current. W5 and
    # the two holder pigtails carry only ID6 current before the motor cable.
    jaw_loop = (wire_resistance('W5', wire=POWER_WIRE) + 2 * JAW_HOLDER_LEAD_M * POWER_WIRE.hot_ohms_per_m
                + JAW_FUSE_OHM + wire_resistance('W28', 'W29', wire=MOTOR_WIRE) + JAW_EH_CONTACT_OHM + .004)
    voltages['ID6'] = junction_v - XL330_STALL_A * jaw_loop
    print(f'ID6 fused branch: {voltages["ID6"]:.3f} V at the motor')
    required_5v = input_5v - min(voltages.values()) + XL330_MIN_V
    print(f'Minimum 5 V source terminal voltage for this load: {required_5v:.4f} V')
    failures = [output for output, voltage in voltages.items() if voltage < XL330_MIN_V]
    if INPUT_5V_MAX > XL330_MAX_V:
        failures.append('5 V source ceiling')

    neck_trunk = (wire_resistance('W6', 'W7', wire=XT60_TAIL)
                  + wire_resistance('W8', 'W9', wire=POWER_WIRE) + .012)
    lead = copper_path(board, parts, '12V_IN', ('J2', 1), ('F2', 1))
    for output, wires in (('J7', ('W22', 'W23')), ('J8', ('W25', 'W26'))):
        check_net(parts, output, {1: 'GND', 2: '12V_NECK', 3: 'DXL_BUS'})
        branch = copper_path(board, parts, '12V_NECK', ('F2', 2), (output, 2))
        voltage = (11.10 - neck_a * (neck_trunk + lead + branch + .038 + .015)
                   - XL430_STALL_A * (wire_resistance(*wires, wire=MOTOR_WIRE) + .090))
        print(f'{output}: {1000*(lead+branch):.2f} mΩ positive PCB path, {voltage:.3f} V at the motor')
        if voltage < 10.50:
            failures.append(output)
    return failures


def check_radio():
    _, parts = load('c3-rf', 'C3_Antenna')
    check_net(parts, 'U2', {1: 'VBUS', 2: 'GND', 3: '3V3'})
    check_net(parts, 'U1', {7: 'CHIP_EN', 17: '3V3', 18: 'VDD_SPI', 25: 'D_N', 26: 'D_P', 33: 'GND'})
    check_net(parts, 'J1', {'A5': 'CC1', 'B5': 'CC2', 'A6': 'USB_DP', 'B6': 'USB_DP',
                           'A7': 'USB_DM', 'B7': 'USB_DM'})
    check_net(parts, 'R3', {1: 'D_N', 2: 'USB_DM'})
    check_net(parts, 'R4', {1: 'D_P', 2: 'USB_DP'})
    print('C3 regulator, USB-C and chip connections match.')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--input-5v', type=float, default=INPUT_5V_LOADED,
                        help='Loaded voltage before the modeled 5 V harness, in volts')
    parser.add_argument('--ph-fault', action='store_true',
                        help='Check each healthy motor while another PH branch is in current limit')
    parser.add_argument('--tail-mm', type=float,
                        help='Length of each 16 AWG 5 V pigtail, overriding W33 and W34 in the cut list')
    options = parser.parse_args()
    if not 0 < options.input_5v <= INPUT_5V_MAX:
        parser.error(f'--input-5v must be greater than 0 and at most {INPUT_5V_MAX} V')
    if options.tail_mm is not None and (not isfinite(options.tail_mm) or options.tail_mm <= 0):
        parser.error('--tail-mm must be a finite positive length')
    check_wire_sizes()
    failed = check_hub(options.input_5v, ph_fault=options.ph_fault, tail_mm=options.tail_mm)
    check_radio()
    if failed:
        raise SystemExit('Insufficient modeled voltage at ' + ', '.join(failed))
