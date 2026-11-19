"""Check service hardware, tool access and hatch removal in millimetres."""

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
from stock import nut, socket_screw
from primitives import cylinder
from tool_access import WRENCH_THICKNESS, wrench_profile, wrench_shape

V = App.Vector


def thickness(shape, x, y, from_z, to_z):
    ray = Part.makeLine(V(x, y, from_z), V(x, y, to_z))
    return ray.common(shape).Length


def tool_pairs(doc):
    base = [world_shape(doc.getObject(name)) for name in ('Part000','Part001','Part002','CableSaddle','CableGate')]
    hatch, board = map(world_shape, (doc.HubHolder, doc.HubPCB))
    bodies = [world_shape(obj) for obj in doc.HubInstalled.Group if obj.Name.startswith('HubBody')]
    for x, y in HATCH_MOUNTS:
        sense = 1 if x > 0 else -1
        for angle, offset in product((-15.,0.,15.), (-.2,.2)):
            wrench = wrench_shape((x,y+offset,HATCH_NUT_SEAT+.24), (0,0,1), (sense,0,0),
                                  wrench_profile(3, angle), WRENCH_THICKNESS[3])
            for travel in range(0, 49, 2):
                for fixed in (*base, hatch, board, *bodies):
                    yield wrench.translated(V(sense*travel,0,0)), fixed, f'Hatch spanner ({x},{y}), {angle:g}°'
        driver = cylinder(1.48, 50., (x,y,HATCH_SCREW_SEAT-3.), (0,0,-1))
        for fixed in (hatch, *base):
            yield driver, fixed, f'Hatch hex key at ({x},{y})'
    for x, y in HUB_MOUNTS:
        socket = cylinder(4.65, 40., (x,y,HUB_NUT_SEAT+2.33), (0,0,-1))
        driver = cylinder(1.48, 40., (x,y,HUB_SCREW_SEAT+3.))
        for tool, fixed in product((socket, driver), (hatch, board, *bodies)):
            yield tool, fixed, f'Hub bench tools at ({x},{y})'


def travel_pairs(doc):
    fixed = [world_shape(obj) for obj in (doc.Part000, doc.CableSaddle, doc.CableGate)]
    installed = [world_shape(obj) for obj in doc.HubInstalled.Group]
    installed += [nut(3, (x, y, HUB_NUT_SEAT)) for x, y in HUB_MOUNTS]
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
            bolt = socket_screw(3, 8., (x,y,HUB_SCREW_SEAT), (0,0,-1))
            land = thickness(cover, x+2.5, y, HUB_NUT_SEAT+2.4, -74.0)
            if bolt.BoundBox.ZMin < HATCH_BOTTOM + .3 or bolt.BoundBox.ZMin > HUB_NUT_SEAT - .35 or land < 3.1:
                raise ValueError('Hub screw needs a full nut and a solid land beneath the PCB')
        for label, pairs in [('Assembly tools', tool_pairs(doc)), ('Closed and withdrawing hatch', travel_pairs(doc))]:
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
