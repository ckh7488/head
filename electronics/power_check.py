"""Check board pin assignments and bound the servo supply drop at stall current."""

from argparse import ArgumentParser
from heapq import heappop, heappush
from math import isfinite, pi
from pathlib import Path

import pcbnew

from harness import (
    INPUT_5V_LOADED, INPUT_5V_MAX, J2_SERVICE_WIRE, MOTOR_WIRE, POWER_WIRE, SUPPLY_CURRENT, SUPPLY_TAIL,
    XT60_TAIL, check_wire_sizes, wire_resistance,
)

HERE = Path(__file__).resolve().parent
HOT_COPPER_OHM_MM = 2.06e-5
HUB_COPPER_MM = .060
HUB_THICKNESS_MM = 1.6
VIA_PLATING_MM = .020
# Thicknesses in the hot-resistance estimate, below the nominal A5 stackup.
A5_COPPER_MM = {pcbnew.F_Cu: .030, pcbnew.In1_Cu: .015,
                pcbnew.In2_Cu: .015, pcbnew.B_Cu: .030}
A5_COPPER_DEPTH = {pcbnew.F_Cu: 0., pcbnew.In1_Cu: .24,
                   pcbnew.In2_Cu: 1.33, pcbnew.B_Cu: 1.57}
XL330_NOMINAL_STALL_A = 1.47
XL330_STALL_A = 1.55
XL430_STALL_A = 1.40
HUB_IDLE_A = .010
PH_RATING_A = 2.0
PH_LIMIT_OHMS = 61.9
PH_LIMIT_TOLERANCE = .003
PH_SWITCH_HOT_OHM = .035
XL330_MIN_V = 4.27
XL330_MAX_V = 5.25
NECK_NORMAL_A = 2 * XL430_STALL_A
# Fuse and contact limits include installation and ageing allowances. Verify them hot on the bench.
SOURCE_CONTACT_OHM = .012
HUB_XT30_CONTACT_OHM = .004
HUB_FUSE_OHM = .035
JAW_FUSE_OHM = .110
JAW_HOLDER_LEAD_M = .127
PH_EH_CONTACT_OHM = .090
JAW_EH_CONTACT_OHM = .045
# A4 adds two WAGO terminals and a service XT60 pair to the input XT60 and J2.
# This added contact allowance is an estimate. Measure the completed harness hot.
NECK_INPUT_CONTACT_OHM = .012
A4_SERVICE_CONTACT_OHM = .012
NECK_FUSE_OHM = .038
NECK_RETURN_OHM = .015
NECK_BRANCH_CONTACT_OHM = .090
# Preserve the A3 pre-service reference for the archived protection study.
LEGACY_NECK_TRUNK_OHM = (.212 * XT60_TAIL.hot_ohms_per_m + .210 * POWER_WIRE.hot_ohms_per_m
                         + NECK_INPUT_CONTACT_OHM + HUB_XT30_CONTACT_OHM)


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
    """Bound path resistance using routed traces and barrels, omitting pours."""
    graph = {}
    layers = list(board.GetEnabledLayers().CuStack())
    four_layer = len(layers) == 4
    thickness = A5_COPPER_MM if four_layer else dict.fromkeys(layers, HUB_COPPER_MM)
    depth = A5_COPPER_DEPTH if four_layer else {pcbnew.F_Cu: 0., pcbnew.B_Cu: HUB_THICKNESS_MM}
    plating = .015 if four_layer else VIA_PLATING_MM

    def edge(a, b, ohms):
        graph.setdefault(a, []).append((b, ohms))
        graph.setdefault(b, []).append((a, ohms))

    def barrel(position, drill, touched_layers):
        area = pi * plating * (pcbnew.ToMM(drill) + plating)
        for top, bottom in zip(touched_layers, touched_layers[1:]):
            ohms = HOT_COPPER_OHM_MM * (depth[bottom] - depth[top]) / area
            edge((*position, top), (*position, bottom), ohms)

    for item in board.GetTracks():
        if item.GetNetname() != f'/{net}':
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            barrel(node(item.GetPosition()), item.GetDrillValue(),
                   [layer for layer in layers if item.IsOnLayer(layer)])
        else:
            a, b, layer = node(item.GetStart()), node(item.GetEnd()), item.GetLayer()
            ohms = HOT_COPPER_OHM_MM * item.GetLength() / item.GetWidth() / thickness[layer]
            edge((*a, layer), (*b, layer), ohms)

    def at(part, pin):
        return {(*node(pad.GetPosition()), layer) for pad in parts[part].Pads()
                if pad.GetNumber() == str(pin) for layer in layers
                if pad.IsOnLayer(layer)}

    for part in parts:
        for pad in parts[part].Pads():
            if pad.GetNetname() == f'/{net}' and pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                barrel(node(pad.GetPosition()), pad.GetDrillSize().x,
                       [layer for layer in layers if pad.IsOnLayer(layer)])

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


def hub_5v_current(ph_fault=False, *, servo_a=XL330_STALL_A):
    branch_a = ph_current_limits()[2] if ph_fault else servo_a
    return 2 * servo_a + branch_a + HUB_IDLE_A


def neck_paths(board, parts):
    check_net(parts, 'J2', {1: 'GND', 2: '12V_IN'})
    check_net(parts, 'F2', {1: '12V_IN', 2: '12V_NECK'})
    if parts['F2'].GetValue() != '4A MINI':
        raise ValueError('12 V hub fuse must match the 4 A MINI protection')
    lead = copper_path(board, parts, '12V_IN', ('J2', 2), ('F2', 1))
    for output, wires in (('J7', ('W22', 'W23')), ('J8', ('W25', 'W26'))):
        check_net(parts, output, {1: 'GND', 2: '12V_NECK', 3: 'DXL_BUS'})
        branch = copper_path(board, parts, '12V_NECK', ('F2', 2), (output, 2))
        yield output, wires, lead + branch


def neck_voltages(board, parts, *, source_v, trunk_ohm, trunk_a=NECK_NORMAL_A):
    for output, wires, positive in neck_paths(board, parts):
        voltage = (source_v - trunk_a * (trunk_ohm + positive + NECK_FUSE_OHM + NECK_RETURN_OHM)
                   - XL430_STALL_A * (wire_resistance(*wires, wire=MOTOR_WIRE) + NECK_BRANCH_CONTACT_OHM))
        yield output, positive, voltage


def a4_neck_trunk():
    # W6/W7/W35/W36 have four 11 mm WAGO insertions. Cups and final lengths
    # are fitted on the bench. Bound the wire estimate with the stock lengths
    # in the B25 list: 0.30 m per colour of 12 AWG and 0.25 m of 18 AWG.
    fixed = wire_resistance('W6', 'W7', 'W35', 'W36', wire=XT60_TAIL,
                            column='모델 중심선 mm', terminal_mm=4 * 11)
    service = wire_resistance('W8', 'W9', wire=J2_SERVICE_WIRE, column='모델 중심선 mm')
    fixed_stock = .60 * XT60_TAIL.hot_ohms_per_m
    service_stock = .50 * J2_SERVICE_WIRE.hot_ohms_per_m
    if fixed > fixed_stock or service > service_stock:
        raise ValueError('A4 neck routes exceed the modeled stock wire lengths')
    stock_wire = fixed_stock + service_stock
    print(f'A4 12 V trunk wire: {1000*(fixed + service):.2f} mΩ before cup lengths, '
          f'{1000*stock_wire:.2f} mΩ using all listed stock wire; '
          f'{1000*A4_SERVICE_CONTACT_OHM:.0f} mΩ assumed for added service contacts')
    return stock_wire + NECK_INPUT_CONTACT_OHM + HUB_XT30_CONTACT_OHM + A4_SERVICE_CONTACT_OHM


def check_hub(input_5v, *, ph_fault=False, tail_mm=None, nominal=False, hub_revision='A4'):
    project = 'servo-hub-a5' if hub_revision == 'A5' else 'servo-hub'
    board, parts = load(project, 'R5_Servo_Hub')
    check_net(parts, 'J1', {1: 'GND', 2: '5V_IN'})
    check_net(parts, 'J3', {1: 'GND', 2: 'DXL_CTL'})
    check_net(parts, 'F1', {1: '5V_IN', 2: '5V_EYES'})
    if parts['F1'].GetValue() != '7.5A MINI':
        raise ValueError('5 V hub fuse must match the 7.5 A thermal and resistance budget')
    xl330_a = XL330_NOMINAL_STALL_A if nominal else XL330_STALL_A
    total_hub_a = hub_5v_current(ph_fault, servo_a=xl330_a)
    total_source_a = total_hub_a + xl330_a
    if nominal:
        print(f'B25 {hub_revision} model at nominal 5.000 V and 12.000 V. Motor catalogue currents: '
              f'{total_source_a:.2f} A on 5 V ({total_hub_a:.2f} A at the hub), '
              f'{NECK_NORMAL_A:.2f} A on 12 V.')
    else:
        lo_limit, curve_min, hi_limit = ph_current_limits()
        if not XL330_STALL_A < lo_limit <= hi_limit < PH_RATING_A:
            raise ValueError('PH branch current limit must pass a normal stall and protect the 2 A contact')
        if hub_5v_current(ph_fault=True) + XL330_STALL_A >= SUPPLY_CURRENT:
            raise ValueError('The 5 V source cannot supply simultaneous stalls plus one limited PH fault')
        load_case = ' with one PH branch in current limit' if ph_fault else ''
        print(f'Bench stress model: {input_5v:.3f} V loaded 5 V source, {INPUT_5V_MAX:.3f} V bench ceiling, '
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
                   - (total_hub_a + NECK_NORMAL_A) * ground - xl330_a * branch_loop)
        copper_drop = total_hub_a * (lead + feed) + xl330_a * branch
        print(f'{output}: {1000*(lead+feed+branch):.2f} mΩ positive PCB path ({1000*copper_drop:.2f} mV), '
              f'{1000*ground:.2f} mΩ return, {voltage:.3f} V at the motor')
        voltages[output] = voltage

    # Only W1–W2 and the supply leads carry the combined current. W5 and
    # the two holder pigtails carry only ID6 current before the motor cable.
    jaw_loop = (wire_resistance('W5', wire=POWER_WIRE) + 2 * JAW_HOLDER_LEAD_M * POWER_WIRE.hot_ohms_per_m
                + JAW_FUSE_OHM + wire_resistance('W28', 'W29', wire=MOTOR_WIRE) + JAW_EH_CONTACT_OHM + .004)
    voltages['ID6'] = junction_v - xl330_a * jaw_loop
    print(f'ID6 fused branch: {voltages["ID6"]:.3f} V at the motor')

    if nominal:
        for output, positive, voltage in neck_voltages(board, parts, source_v=12., trunk_ohm=a4_neck_trunk()):
            print(f'{output}: {1000*positive:.2f} mΩ positive PCB path ({1000*NECK_NORMAL_A*positive:.2f} mV), '
                  f'{voltage:.3f} V at the motor')
        print('Model estimates at catalogue stall currents. Measure adapter and motor terminals during B25 motion.')
        return []

    required_5v = input_5v - min(voltages.values()) + XL330_MIN_V
    print(f'Minimum 5 V source terminal voltage for the {XL330_MIN_V:.2f} V bench reference: {required_5v:.4f} V')
    failures = [output for output, voltage in voltages.items() if voltage < XL330_MIN_V]
    if INPUT_5V_MAX > XL330_MAX_V:
        failures.append('5 V source ceiling')

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
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--nominal', action='store_true',
                        help='B25 sizing and voltage estimate at nominal 5 V and 12 V (default)')
    source.add_argument('--bench', action='store_true',
                        help='Legacy SPD1168X 5 V stress screen at a loaded 5.17 V')
    source.add_argument('--input-5v', type=float,
                        help='Run the 5 V stress screen at this loaded source voltage')
    source.add_argument('--radio', action='store_true', help='Check the separate C3 board connections')
    parser.add_argument('--ph-fault', action='store_true',
                        help='Check each healthy motor while another PH branch is in current limit')
    parser.add_argument('--hub-revision', choices=('A4', 'A5'), default='A4',
                        help='Select the A4 reference or the 4-layer A5 hub')
    parser.add_argument('--tail-mm', type=float,
                        help='Length of each 16 AWG 5 V pigtail, overriding W33 and W34 in the cut list')
    options = parser.parse_args()
    if options.input_5v is not None and not 0 < options.input_5v <= INPUT_5V_MAX:
        parser.error(f'--input-5v must be greater than 0 and at most {INPUT_5V_MAX} V')
    if options.tail_mm is not None and (not isfinite(options.tail_mm) or options.tail_mm <= 0):
        parser.error('--tail-mm must be a finite positive length')
    bench = options.bench or options.input_5v is not None
    if not bench and (options.ph_fault or options.tail_mm is not None):
        parser.error('--ph-fault and --tail-mm require --bench or --input-5v')
    if options.radio:
        check_radio()
        raise SystemExit(0)
    check_wire_sizes()
    input_5v = options.input_5v
    if input_5v is None:
        input_5v = INPUT_5V_LOADED if bench else 5.
    failed = check_hub(input_5v, ph_fault=options.ph_fault, tail_mm=options.tail_mm, nominal=not bench,
                       hub_revision=options.hub_revision)
    if failed:
        raise SystemExit('Insufficient modeled voltage at ' + ', '.join(failed))
