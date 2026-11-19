"""Check B8 service hardware insertion, seating and cover removal in millimetres."""

from argparse import ArgumentParser
from itertools import product
from pathlib import Path
import sys

import FreeCAD as App
import Part

from base_clearance import check_pass
from export_cad import world_shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service_hatch import (
    HATCH_BOTTOM, HATCH_MOUNTS, HATCH_NUT_SEAT, HATCH_SCREW_SEAT,
    HUB_MOUNTS, HUB_NUT_SEAT, HUB_SCREW_SEAT,
)
from stock import hexagon, socket_screw

V = App.Vector


def thickness(shape, x, y, from_z, to_z):
    ray = Part.makeLine(V(x, y, from_z), V(x, y, to_z))
    return ray.common(shape).Length


def insertion_pairs(doc):
    for receiver, mounts, seat in [
        (doc.Part000, HATCH_MOUNTS, HATCH_NUT_SEAT),
        (doc.HubHolder, HUB_MOUNTS, HUB_NUT_SEAT),
    ]:
        body = world_shape(receiver)
        for x, y in mounts:
            # An extruded nut profile covers the full straight insertion stroke.
            path = hexagon(5.5, 24.4, (x, y, seat + .01))
            for dx, dy, angle in product((-.12, 0, .12), (-.12, 0, .12), (-2., 0., 2.)):
                swept = path.copy().rotate(V(x, y, 0), V(0, 0, 1), angle).translate(V(dx, dy, 0))
                yield swept, body, f'{receiver.Label}: nut insertion at {x}, {y}, shift {dx}, {dy}, {angle}°'
            smallest = hexagon(5.32, 2.4, (x, y, seat + .01)).rotate(V(x, y, 0), V(0, 0, 1), 30.)
            if smallest.common(body).Volume < .05:
                raise ValueError(f'{receiver.Label}: nut can turn through the pocket')


def travel_pairs(doc):
    fixed = [world_shape(obj) for obj in (doc.Part000, doc.CableSaddle, doc.CableGate)]
    installed = [world_shape(obj) for obj in doc.HubInstalled.Group]
    installed += [world_shape(obj) for obj in doc.HubCableSpace.Group if obj.Name.startswith('HubPlug')]
    package = Part.Compound(installed)
    for depth, dx, dy, angle in product((0., .23, -1., -4., -12., -30.), (-.20, 0, .20), (-.20, 0, .20), (-.22, .22)):
        moved = package.copy().rotate(V(0, 62, 0), V(0, 0, 1), angle).translate(V(dx, dy, depth))
        for other in fixed:
            yield moved, other, f'service cover at {depth} mm, shift {dx}, {dy}, {angle}°'


def check(cad):
    doc = App.openDocument(str(cad.resolve()))
    try:
        base, cover = map(world_shape, (doc.Part000, doc.HubHolder))
        flange = thickness(cover, 45., 60., -83.2, -76.)
        middle = thickness(cover, 0., 60., -83.2, -76.)
        if min(flange, middle - 1.) < 3.99:
            raise ValueError('The service cover lost its 4 mm perimeter or 5 mm web')
        heads = []
        cover_seats = []
        base_seats = []
        for x, y in HATCH_MOUNTS:
            screw = socket_screw(3, 8, (x, y, HATCH_SCREW_SEAT), (0, 0, 1))
            heads.append(screw.BoundBox.ZMin - HATCH_BOTTOM)
            cover_seats.append(thickness(cover, x + 2.5, y, HATCH_SCREW_SEAT, -76.9))
            base_seats.append(thickness(base, x + 2.5, y, -76.66, HATCH_NUT_SEAT))
        if min(heads) < .20 or min(cover_seats) < 2.7 or min(base_seats) < 1.8:
            raise ValueError('Countersocket or nut seat has insufficient depth')
        for x, y in HUB_MOUNTS:
            if thickness(cover, x, y, HATCH_BOTTOM, -80.5) < 1.6:
                raise ValueError('Board bolt pocket broke the underside of the cover')
        for label, pairs in [('Straight nut paths', insertion_pairs(doc)), ('Closed and withdrawing hatch', travel_pairs(doc))]:
            count, maximum = check_pass(pairs)
            print(f'{label}: {count} pairs, max overlap {maximum:.6f} mm³', flush=True)
        print(f'Cover: {flange:.2f} mm edge, {middle:.2f} mm center, {cover.Volume/1000:.2f} cm³')
        print(f'Fastener lands: {min(cover_seats):.2f} mm cover, {min(base_seats):.2f} mm base, {min(heads):.2f} mm below cover face')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    check(parser.parse_args().cad)
