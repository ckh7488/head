"""Check board pin assignments and bound the servo supply drop at stall current."""

from heapq import heappop, heappush
from pathlib import Path

import pcbnew

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


def check_hub():
    board, parts = load('servo-hub', 'R5_Servo_Hub')
    check_net(parts, 'J1', {1: 'GND', 2: '5V_IN'})
    check_net(parts, 'J2', {1: '12V_IN', 2: 'GND'})
    check_net(parts, 'J3', {1: 'GND', 2: 'DXL_CTL'})
    model = (
        ('5V_IN', '5V_EYES', ('J1', 2), 'F1', range(4, 7), 1.47, 5.88, 4.90),
        ('12V_IN', '12V_NECK', ('J2', 1), 'F2', range(7, 9), 1.40, 2.80, 11.10),
    )
    for upstream, rail, entry, fuse, outputs, stall, trunk_current, supply in model:
        check_net(parts, fuse, {1: upstream, 2: rail})
        current = len(outputs)*stall
        trunk_loss = trunk_current*(.60*.025 + .005)
        wire_and_contacts = stall*(1.0*.100 + .080)
        lead = copper_path(board, parts, upstream, entry, (fuse, 1))
        for output in outputs:
            part = f'J{output}'
            check_net(parts, part, {1: 'GND', 2: rail, 3: 'DXL_BUS'})
            branch = copper_path(board, parts, rail, (fuse, 2), (part, 2))
            voltage = supply-trunk_loss-current*(lead+branch+.038+.015)-wire_and_contacts
            if voltage < (4.25 if supply < 6 else 10.50):
                raise ValueError(f'{part} has insufficient supply headroom')
            print(f'{part}: {1000*(lead+branch):.2f} mΩ positive PCB path, {voltage:.2f} V at the motor')
    jaw = 4.90-5.88*(.60*.025+.005)-1.47*(1.0*.100+.080+.090)
    print(f'ID6 fused branch: {jaw:.2f} V at the motor')


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
    check_hub()
    check_radio()
