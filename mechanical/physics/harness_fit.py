"""Check the selected connector envelopes in the assembled base."""

from argparse import ArgumentParser
from itertools import chain, combinations, product
from pathlib import Path
import sys

import FreeCAD as App

from base_clearance import check_pass
from export_cad import world_shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixtures import (
    CABLE_CENTER_Z, CABLE_LANES, CABLE_SAMPLES, CABLE_STOP_Y, cable_sample, xt60_inner_sample,
)
from primitives import box, cylinder

V = App.Vector


def cable_fit(doc):
    base, tray, cover = map(world_shape, (doc.Part000, doc.CableSaddle, doc.CableGate))
    for lane, sample in zip(CABLE_LANES, CABLE_SAMPLES, strict=True):
        name, x, _, _, (width, height), _, _, _ = lane
        plug = cable_sample(lane, sample)
        insertions = (0., 2., 4., 8., 12., 18., 25.)
        paths = (
            (plug.translated(V(dx, 0, dz + rise)), fixed, f'{name}, lowering into its tray')
            for dx, dz, rise, fixed in product((-.15, .15), (0., .15), insertions, (base, tray))
        )
        seats = (
            (plug.translated(V(dx, 0, dz)), fixed, f'{name}, with the lid installed')
            for dx, dz, fixed in product((-.15, .15), (-.15,.15), (base, tray, cover))
        )
        a, _ = check_pass(paths)
        b, _ = check_pass(seats)
        z, y = CABLE_CENTER_Z, CABLE_STOP_Y
        stop = box(x-width/2, x+width/2, y+.01, y+.21, z-height/2, z+height/2)
        area = min(stop.translated(V(dx, 0, dz)).common(part).Volume / .20
                   for dx, dz, part in product((-.15, .15), (-.15, .15), (tray, cover)))
        if area < 5.:
            raise ValueError(f'{name} has less than 5 mm² of shoulder on one half')
        print(f'{name}: {a+b} fits, minimum shoulder area {area:.2f} mm² per half.', flush=True)
    inner = xt60_inner_sample()
    outer = cable_sample(CABLE_LANES[1], CABLE_SAMPLES[1])
    positions = (
        (inner.translated(V(dx, -advance, dz)), solid, 'XT60U-M from inside the open base')
        for dx, dz, advance, solid in product((-.15, .15), (-.15,.15), range(0, 17, 2), (base, tray, cover, outer))
    )
    n, _ = check_pass(positions)
    print(f'XT60U-M: {n} inside insertion fits.', flush=True)


def hub_fit(doc):
    board_top = world_shape(doc.HubPCB).BoundBox.ZMax
    fixed = [world_shape(doc.getObject(n)) for n in
             ('Part000', 'CableSaddle', 'CableGate', 'Part001', 'Part002', 'Part069', 'Part072')]
    board_parts = {o.Name: world_shape(o) for o in doc.HubInstalled.Group if o.Name.startswith('HubBody')}
    # JST envelope plus a 6 mm straight section and an allowance for the first wire bend.
    for port in range(3, 9):
        name = f'HubBodyJ{port}'
        c = board_parts[name].BoundBox.Center
        width = 6.3 if port == 3 else (8.3 if port <= 6 else 10.5)
        depth = 5.1 if port <= 6 else 4.5
        plug = box(c.x-width/2, c.x+width/2, c.y-depth/2, c.y+depth/2, board_top+6.15, board_top+16.)
        neighbors = [s for key,s in board_parts.items() if key != name]
        checks = (
            (plug.translated(V(dx, dy, -travel)), solid, f'J{port}, hatch at {travel:g} mm')
            for dx, dy, travel, solid in product((-.12, .12), (-.12,.12),
                                                (0., 5., 15., 25., 30.), fixed)
        )
        beside = ((plug, solid, f'J{port}, adjacent PCB part') for solid in neighbors)
        n, _ = check_pass(chain(checks, beside))
        print(f'J{port}: {n} populated connector poses.', flush=True)


def yaw_passage(doc):
    bore = cylinder(4.5, 38., (0.,-26.,-59.))
    moving = [world_shape(doc.getObject(n)) for n in ('Part007','Part010')]
    fixed = [world_shape(doc.getObject(n)) for n in
             ('Part000','Part001','Part002','Part006','Part008','Part009','Part017','Part069','Part070','HubPCB')]
    rotor = ((bore, solid, 'rotor cable passage') for solid in moving)
    sweep = ((bore.copy().rotate(V(), V(0,0,1), angle), solid, f'9 mm guide at yaw {angle:g}°')
             for angle, solid in product(range(-60,61,5), fixed))
    n, _ = check_pass(chain(rotor, sweep))
    print(f'9 mm cable guide through the neck rotor: {n} checks at yaw ±60°.', flush=True)


def splices_fit(doc):
    locations = (
        ('5 V WAGO', -42., 46., -64.5, 19., 19., 8.5),
        ('5 V return WAGO', -50., 57., -74.5, 19., 19., 8.5),
        ('DATA WAGO', 36., 27., -66.5, 19., 19., 8.5),
        ('12 V WAGO', 52., 44., -64.5, 19., 13.5, 8.5),
        ('12 V return WAGO', 53., 55., -74.5, 13.5, 19., 8.5),
        ('ID6 fuse', 0., -46., -76.5, 58., 23., 19.),
    )
    parts = [(name, box(x-w/2, x+w/2, y-d/2, y+d/2, z, z+h)) for name,x,y,z,w,d,h in locations]
    names = ('Part000','Part001','Part002','Part006','Part007','Part008','Part009','Part010','Part017',
             'Part069','Part070','Part071','Part072','CableSaddle','CableGate','InputXT60Mate','HubHolder')
    fixed = [world_shape(doc.getObject(n)) for n in names]
    fixed.extend(world_shape(o) for group in (doc.HubInstalled, doc.HubCableSpace) for o in group.Group
                 if o.TypeId == 'Part::Feature')
    body = ((shape, solid, name) for (name, shape), solid in product(parts, fixed))
    neighbors = ((shape, other, f'{name} beside {other_name}')
                 for (name,shape), (other_name,other) in combinations(parts,2))
    n, _ = check_pass(chain(body, neighbors))
    print(f'Five WAGO positions and the ID6 fuse: {n} parked housing checks.', flush=True)


def main(cad):
    doc = App.openDocument(str(cad.resolve()))
    try:
        cable_fit(doc)
        hub_fit(doc)
        yaw_passage(doc)
        splices_fit(doc)
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    main(parser.parse_args().cad)
