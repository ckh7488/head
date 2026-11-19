"""Check the production PCB drill geometry and connector access against FreeCAD."""

from argparse import ArgumentParser
from pathlib import Path
import sys

import FreeCAD as App
import Part

from base_clearance import check_pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from primitives import box, cylinder
from base_stack import CARRIER_BOLT_Z, CARRIER_MOUNTS
from openrb import BOTTOM as RB_BOTTOM, HOLES as RB_HOLES, NUT_SEAT as RB_NUT_SEAT, TOP as RB_TOP
from openrb import board_xy as rb_xy
from radio import C3_BOTTOM, C3_HOLES, C3_NUT_SEAT, C3_ORIGIN, C3_TOP, board_xy, usb_plug
from stock import nut, socket_screw

V = App.Vector


def centers(shape, radius):
    return {(face.Surface.Center.x, face.Surface.Center.y) for face in shape.Faces
            if isinstance(face.Surface, Part.Cylinder) and abs(face.Surface.Radius-radius) < .01}


def same_centers(actual, expected):
    return len(actual) == len(expected) and all(
        any(abs(x-u) < .025 and abs(y-v) < .025 for u, v in actual) for x, y in expected
    )


def pcb(path, origin, size):
    body = Part.read(str(path))
    limits = body.BoundBox
    if abs(limits.XLength-size[0]) > .025 or abs(limits.YLength-size[1]) > .025:
        raise ValueError(f'{path.name} has different board dimensions')
    return body.translate(V(*origin))


def clearance_pairs(doc, c3, hub):
    fixed = [doc.getObject(name).Shape for name in ('Part000', 'Part001', 'Part002', 'Part006',
                                                   'Part010', 'Part069', 'Part072', 'CableSaddle', 'CableGate')]
    tray = doc.Part071.Shape
    ports = [part.Shape for part in doc.HubCableSpace.Group if part.Name.startswith('HubPlug')]
    ports += [box(-13.55, -1.4, 75.15, 87.85, -71.5, -64.7),
              box(7.8, 17.9, 74.15, 81.15, -68.6, -63.0)]
    for depth in range(31):
        for offset, port in enumerate(ports):
            moved = port.copy().translate(V(0, 0, -depth))
            for obstacle in fixed:
                yield moved, obstacle, f'Hub connector {offset+1}, hatch {depth} mm'
    for obstacle in (*fixed, tray):
        yield c3, obstacle, 'C3 board in its tray'
        for depth in (0., 4., 8.):
            moved = usb_plug().translate(V(0, -depth, 0))
            yield moved, obstacle, f'C3 USB-C insertion, {depth} mm from seated'
    for x,y in (board_xy(*corner) for corner in C3_HOLES):
        screw = socket_screw(2,8.,(x,y,C3_BOTTOM+1.6),(0,0,-1))
        tail = nut(2,(x,y,C3_NUT_SEAT))
        for hardware in (screw,tail):
            for obstacle in (*fixed,tray,c3,usb_plug()):
                yield hardware, obstacle, 'C3 M2 screw and plain hex nut'
    for obstacle in (*fixed, doc.HubHolder.Shape):
        yield hub, obstacle, 'Hub PCB at its four mounting points'


def board_support(tray, board, x, y, bottom):
    bearing = cylinder(2.50, .10, (x, y, bottom-.055))
    seat = tray.common(bearing).common(board.translated(V(0, 0, -.05)))
    return seat.Volume / .05


def carrier_checks(doc, c3):
    cup, c3_tray, rb_tray = doc.Part000.Shape, doc.Part071.Shape, doc.Part072.Shape
    openrb = doc.Part069.Shape
    anchors = [socket_screw(3, 8., (x, y, CARRIER_BOLT_Z), (0, 0, -1)) for x, y in CARRIER_MOUNTS]
    for tray, board, other, centers, bottom, top, nut_z, mount_points in (
        (c3_tray, c3, rb_tray, [board_xy(*p) for p in C3_HOLES], C3_BOTTOM, C3_TOP, C3_NUT_SEAT,
         CARRIER_MOUNTS[:4]),
        (rb_tray, openrb, c3_tray, [rb_xy(*p) for p in RB_HOLES], RB_BOTTOM, RB_TOP, RB_NUT_SEAT,
         CARRIER_MOUNTS[4:]),
    ):
        for x, y in centers:
            area = board_support(tray, board, x, y, bottom)
            if area < 10.:
                raise ValueError(f'PCB is unsupported near ({x:g}, {y:g}): {area:.2f} mm²')
            if top - 8. > nut_z:
                raise ValueError(f'M2×8 does not engage the full nut at ({x:g}, {y:g})')
            bolt = socket_screw(2, 8., (x, y, top), (0, 0, -1))
            driver = cylinder(.87, 30., (x, y, top+2.))
            for fixed in (cup, tray, board, other, *anchors):
                yield bolt, fixed, 'PCB M2×8 screw'
                yield driver, fixed, '1.5 mm hex driver at PCB'
        for x, y in mount_points:
            driver = cylinder(1.45, 30., (x, y, CARRIER_BOLT_Z+3.))
            for fixed in (cup, tray, other):
                yield driver, fixed, '2.5 mm hex driver at empty carrier'
        for bolt in anchors:
            yield board, bolt, 'PCB underside above installed M3 heads'
    plug = doc.OpenRBUSB.Shape
    for height in range(0, 27, 2):
        for fixed in (cup, rb_tray, *anchors):
            yield plug.translated(V(0, 0, height)), fixed, f'OpenRB with USB-C preconnected, {height} mm above seat'


def check(cad, c3_step, hub_step):
    c3 = pcb(c3_step, (*C3_ORIGIN, C3_BOTTOM), (34., 53.))
    hub = pcb(hub_step, (-35., 77., -74.1), (70., 35.))
    doc = App.openDocument(str(cad.resolve()))
    try:
        expected = [board_xy(x, y) for x, y in C3_HOLES]
        if not same_centers(centers(c3, 1.10), expected) or not same_centers(centers(doc.Part071.Shape, 1.13), expected):
            raise ValueError('C3 KiCad drill does not match the two new through holes')
        expected = [rb_xy(x, y) for x, y in RB_HOLES]
        if not same_centers(centers(doc.Part069.Shape, 1.20), expected) or not same_centers(centers(doc.Part072.Shape, 1.13), expected):
            raise ValueError('Four modeled OpenRB mounting holes do not match the carrier')
        expected = [(x, y) for x in (-30.8, 30.8) for y in (46.2, 72.8)]
        if not same_centers(centers(hub, 1.60), expected):
            raise ValueError('Hub KiCad drill does not match the four hatch positions')
        for name in ('HubBolt1', 'HubBolt2', 'HubBolt3', 'HubBolt4'):
            bolt = doc.getObject(name).Shape.BoundBox
            if not any(abs(bolt.Center.x-x) < .025 and abs(bolt.Center.y-y) < .025 for x, y in expected):
                raise ValueError(f'{name} does not sit over a hub mounting hole')
        count, overlap = check_pass(clearance_pairs(doc, c3, hub))
        mounts, mount_overlap = check_pass(carrier_checks(doc, c3))
        print(f'6 KiCad PCB holes and 4 modeled OpenRB holes match. {count + mounts} clearance pairs, '
              f'{max(overlap, mount_overlap):.6f} mm³ maximum overlap.')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('c3_step', type=Path)
    parser.add_argument('hub_step', type=Path)
    check(**vars(parser.parse_args()))
