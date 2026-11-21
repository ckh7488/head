"""Check board pin assignments and bound the servo supply drop at stall current."""

from argparse import ArgumentParser
from heapq import heappop, heappush
from pathlib import Path

import pcbnew

from harness import (
    INPUT_5V_LOADED, MOTOR_LENGTH, MOTOR_WIRE, POWER_LENGTH, POWER_WIRE,
    XT60_TAIL, XT60_TAIL_LENGTH, check_wire_sizes,
)

HERE = Path(__file__).resolve().parent
HOT_COPPER_OHM_MM = 2.06e-5
HUB_COPPER_MM = .070


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
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA) or item.GetNetname() != f'/{net}':
            continue
        a, b = node(item.GetStart()), node(item.GetEnd())
        ohms = HOT_COPPER_OHM_MM * item.GetLength() / item.GetWidth() / HUB_COPPER_MM
        graph.setdefault(a, []).append((b, ohms))
        graph.setdefault(b, []).append((a, ohms))

    def at(part, pin):
        return {node(pad.GetPosition()) for pad in parts[part].Pads() if pad.GetNumber() == str(pin)}

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


def check_hub(input_5v=INPUT_5V_LOADED):
    board, parts = load('servo-hub', 'R5_Servo_Hub')
    check_net(parts, 'J1', {1: 'GND', 2: '5V_IN'})
    check_net(parts, 'J2', {1: '12V_IN', 2: 'GND'})
    check_net(parts, 'J3', {1: 'GND', 2: 'DXL_CTL'})
    model = (
        ('5V_IN', '5V_EYES', ('J1', 2), 'F1', range(4, 7), 1.47, 5.88, input_5v),
        ('12V_IN', '12V_NECK', ('J2', 1), 'F2', range(7, 9), 1.40, 2.80, 11.10),
    )
    failures = []
    for upstream, rail, entry, fuse, outputs, stall, trunk_current, supply in model:
        check_net(parts, fuse, {1: upstream, 2: rail})
        current = len(outputs)*stall
        tail = XT60_TAIL_LENGTH if upstream == '12V_IN' else 0.
        trunk_wire = 2*((POWER_LENGTH-tail)*POWER_WIRE.hot_ohms_per_m + tail*XT60_TAIL.hot_ohms_per_m)
        trunk_loss = trunk_current*(trunk_wire + .012)
        wire_and_contacts = stall*(2*MOTOR_LENGTH*MOTOR_WIRE.hot_ohms_per_m + .080)
        lead = copper_path(board, parts, upstream, entry, (fuse, 1))
        for output in outputs:
            part = f'J{output}'
            check_net(parts, part, {1: 'GND', 2: rail, 3: 'DXL_BUS'})
            branch = copper_path(board, parts, rail, (fuse, 2), (part, 2))
            voltage = supply-trunk_loss-current*(lead+branch+.038+.015)-wire_and_contacts
            if voltage < (4.25 if upstream == '5V_IN' else 10.50):
                failures.append(part)
            print(f'{part}: {1000*(lead+branch):.2f} mΩ positive PCB path, {voltage:.2f} V at the motor')
    jaw = (input_5v - 5.88*(2*POWER_LENGTH*POWER_WIRE.hot_ohms_per_m+.012)
           - 1.47*(2*MOTOR_LENGTH*MOTOR_WIRE.hot_ohms_per_m+.080+.090))
    if jaw < 4.25:
        failures.append('ID6')
    print(f'ID6 fused branch: {jaw:.2f} V at the motor')
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
    options = parser.parse_args()
    if not 0 < options.input_5v <= 6.0:
        parser.error('--input-5v must be greater than 0 and at most 6 V')
    check_wire_sizes()
    failed = check_hub(options.input_5v)
    check_radio()
    if failed:
        raise SystemExit('Insufficient modeled voltage at ' + ', '.join(failed))
