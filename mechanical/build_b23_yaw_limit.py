"""Add mechanical end stops to the existing yaw rotor and bearing seat."""

from math import cos, radians, sin, sqrt
import json

import FreeCAD as App
import Part

from build_b19_review_fixes import add_part, replace
from build_b21_fasteners import check_solid
from export_cad import world_shape
from primitives import cylinder, print_mesh

NOMINAL_STOP_DEG = 59.6
RELEASE_GUARD_DEG = 60.35
TANGENTIAL_BUILD_ALLOWANCE_MM = .40
LUG_TIP_MM = 48.45
PAD_INNER_MM = 45.35
ROTOR_OUTER_MM = 44.80
LUG_HALF_DEG = 4.
LUG_Z = (-36.8, -32.9)
PAD_Z = (-37., -33.)
KEY_DEPTH_Z = -40.35
PAD_INSERT_MM = 12.
KEY_SIDE_CLEARANCE_MM = .14
PAD_IDS = ('YawStopPadRight', 'YawStopPadLeft')
ORIGIN = App.Vector()
AXIS = App.Vector(0., 0., 1.)
FIXED_NEARBY = ('Part000', 'Part002', 'Part006', 'Part008', 'Part009', 'Part017', 'YawInnerRaceShim',
                'YawBearingRetainer1', 'YawBearingRetainer2', 'YawBearingRetainer3')


def sector(inner, outer, start_deg, end_deg, bottom, top):
    points = [App.Vector(0., 0., bottom)]
    for angle in (start_deg, end_deg):
        phi = radians(angle)
        points.append(App.Vector(2.*outer*cos(phi), 2.*outer*sin(phi), bottom))
    wedge = Part.Face(Part.makePolygon(points+[points[0]])).extrude(App.Vector(0., 0., top-bottom))
    ring = cylinder(outer, top-bottom, (0., 0., bottom)).cut(cylinder(inner, top-bottom, (0., 0., bottom)))
    return ring.common(wedge)


def shapes():
    end_low = 90.-LUG_HALF_DEG-NOMINAL_STOP_DEG
    end_high = 90.+LUG_HALF_DEG+NOMINAL_STOP_DEG
    lug = sector(41.5, LUG_TIP_MM, 90.-LUG_HALF_DEG, 90.+LUG_HALF_DEG, *LUG_Z)
    pads = (sector(PAD_INNER_MM, 58.9, 14., end_low, *PAD_Z),
            sector(PAD_INNER_MM, 58.9, end_high, 166., *PAD_Z))
    # Union of the new outward portion of the lug over the entire nominal arc.
    swept = sector(ROTOR_OUTER_MM, LUG_TIP_MM, end_low, end_high, *LUG_Z)
    return lug, pads, swept


def pad_socket_gaps(pads):
    sockets = [cylinder(4.5, 20., (63.*cos(radians(angle)), 63.*sin(radians(angle)), -37.))
               for angle in (30., 150., 270.)]
    return [min(pad.distToShape(socket)[0] for socket in sockets) for pad in pads]


def verify(doc, rotor, seat, lug, pads, swept):
    fixed = {name: world_shape(doc.getObject(name)) for name in FIXED_NEARBY}
    original_rotor_band = cylinder(ROTOR_OUTER_MM, 4.5, (0., 0., -37.41))
    if rotor.common(cylinder(62., 4.5, (0., 0., -37.41)).cut(original_rotor_band)).Volume > 1e-6:
        raise ValueError('The original rotor extends outside the radius used to qualify the stop pads')
    swept_gaps = {name: swept.distToShape(shape)[0] for name, shape in {**fixed, 'Part001': seat}.items()}
    pad_gaps = {name: min(pad.distToShape(shape)[0] for pad in pads) for name, shape in fixed.items()}
    if min(swept_gaps.values()) < .40 or min(pad_gaps.values()) < .40:
        raise ValueError(f'Yaw stop stock fouls a neighboring actor: sweep {swept_gaps}, pads {pad_gaps}')
    socket = pad_socket_gaps(pads)
    if min(socket) < 1.:
        raise ValueError('Yaw stops block the existing bearing-seat M3 socket access')
    assembly_gap = min(pad.distToShape(original_rotor_band)[0] for pad in pads)
    if assembly_gap < .50:
        raise ValueError('Yaw stop pads prevent lowering the original rotor')
    measured = []
    for sign, pad in zip((-1., 1.), pads, strict=True):
        at = lug.copy().rotate(ORIGIN, AXIS, sign*NOMINAL_STOP_DEG)
        before = lug.copy().rotate(ORIGIN, AXIS, sign*(NOMINAL_STOP_DEG-.1))
        after = lug.copy().rotate(ORIGIN, AXIS, sign*(NOMINAL_STOP_DEG+.1))
        first = at.distToShape(pad)[0]
        if first > 1e-6 or at.common(pad).Volume > 1e-6 or before.distToShape(pad)[0] < .07 or after.common(pad).Volume < .7:
            raise ValueError('Yaw stop contact order or face area regressed')
        measured.append({'side': int(sign), 'first_touch_deg': sign*NOMINAL_STOP_DEG,
                         'clearance_0p1_deg_before_mm': before.distToShape(pad)[0],
                         'overlap_0p1_deg_after_mm3': after.common(pad).Volume})
    return {'swept_addition_gap_mm': swept_gaps, 'fixed_addition_gap_mm': pad_gaps,
            'seat_socket_gap_mm': socket, 'neutral_rotor_radial_insert_gap_mm': assembly_gap,
            'stops': measured}


def station(angle, radius):
    return App.Vector(radius*cos(radians(angle)), radius*sin(radians(angle)), 0.)


def tapered_key(anchor, terminal, radii, z0, z1):
    first, last = radii
    delta = terminal-anchor
    direction = delta/delta.Length
    lateral = App.Vector(-direction.y, direction.x, 0.)
    tilt = (first-last)/delta.Length
    fore = tilt*direction
    flank = sqrt(1.-tilt**2)*lateral
    z = App.Vector(0., 0., z0)
    outline = [anchor+first*(fore-flank)+z, terminal+last*(fore-flank)+z,
               terminal+last*(fore+flank)+z, anchor+first*(fore+flank)+z]
    thickness = z1-z0
    bridge = Part.Face(Part.makePolygon(outline+[outline[0]])).extrude(App.Vector(0., 0., thickness))
    rounds = [cylinder(radius, thickness, (point.x, point.y, z0))
              for point, radius in zip((anchor, terminal), radii, strict=True)]
    return bridge.fuse(rounds).removeSplitter()


def keyed_pads(toes):
    pads, pockets = [], []
    for start, end, toe in zip((30., 150.), (25., 155.), toes, strict=True):
        anchor, terminal = station(start, 63.), station(end, 53.2)
        radii = (4., 2.45)
        key = tapered_key(anchor, terminal, radii, KEY_DEPTH_Z, PAD_Z[0])
        pocket_radii = [radius+KEY_SIDE_CLEARANCE_MM for radius in radii]
        pocket = tapered_key(anchor, terminal, pocket_radii, KEY_DEPTH_Z, -36.85)
        clearance = cylinder(1.75, 5., (anchor.x, anchor.y, -40.8))
        pads.append(check_solid(toe.fuse(key).cut(clearance).removeSplitter(), 'indexed yaw pad'))
        pockets.append(pocket)
    return pads, pockets


def verify_installation(doc, seat, pads):
    # Keep the full bearing gage available until after the bearing is seated.
    bearing_drop = cylinder(50., 38., (0., 0., -48.)).cut(cylinder(40., 38., (0., 0., -48.)))
    overlap = bearing_drop.common(seat).Volume
    if overlap > 1e-6:
        raise ValueError(f'Bearing now fouls the bare seat during top installation: {overlap:g} mm³')
    obstacles = [seat, *(world_shape(doc.getObject(name)) for name in
                        ('Part006', 'YawBearingRetainer1', 'YawBearingRetainer2', 'YawBearingRetainer3'))]
    for i, pad in enumerate(pads):
        for lift in (0., .2, 1., 2., 4., 8., PAD_INSERT_MM):
            moving = pad.copy().translate(App.Vector(0., 0., lift))
            if any(moving.common(fixed).Volume > 1e-6 for fixed in [*obstacles, pads[1-i]]):
                raise ValueError(f'Yaw stop pad {i} cannot travel vertically at {lift:g} mm')
        if pad.distToShape(seat)[0] > 1e-6:
            raise ValueError('Stop pad has lost its positive seat datum')
    return {'bearing_top_installation_overlap_mm3': overlap,
            'pad_actors': list(reversed(PAD_IDS)), 'pad_insert_offset_mm': [0., 0., PAD_INSERT_MM],
            'pad_stock_seat_nuts': ['seatNut2', 'seatNut1'],
            'pad_stock_seat_bolts': ['seatBolt2', 'seatBolt1'],
            'pad_side_clearance_mm': KEY_SIDE_CLEARANCE_MM, 'pad_positive_key_depth_mm': PAD_Z[0]-KEY_DEPTH_Z}


def apply(doc, prints=None):
    rotor = world_shape(doc.Part007)
    original_seat = world_shape(doc.Part001)
    lug, toes, swept = shapes()
    pads, pockets = keyed_pads(toes)
    seat = check_solid(original_seat.cut(pockets).removeSplitter(), 'outer seat with keyed yaw pad sockets')
    report = verify(doc, rotor, seat, lug, toes, swept)
    report.update(verify_installation(doc, seat, pads))

    driven = check_solid(rotor.fuse(lug).removeSplitter(), 'yaw rotor with positive stop lug')
    replace(doc.Part007, driven)
    replace(doc.Part001, seat)
    for name, pad in zip(PAD_IDS, pads, strict=True):
        obj = add_part(doc, doc.Part001.getParentGeoFeatureGroup(), name, '02 yaw stop pad · '+name[10:].lower(), pad, 'fixed')
        obj.addProperty('App::PropertyBool', 'Printed', 'Hardware')
        obj.Printed = True
    if prints is not None:
        for shape, name in ((seat, '02_outer_bearing_seat-B23'), (driven, '04_yaw_rotor-B23'),
                            *zip(pads, PAD_IDS, strict=True)):
            print_mesh(shape, prints/f'{name}.stl')
    report.update({'nominal_stop_deg': [-NOMINAL_STOP_DEG, NOMINAL_STOP_DEG],
                   'released_guard_deg': [-RELEASE_GUARD_DEG, RELEASE_GUARD_DEG],
                   'added_rotor_mm3': driven.Volume-rotor.Volume,
                   'seat_pocket_removed_mm3': original_seat.Volume-seat.Volume,
                   'contact_radius_mm': [PAD_INNER_MM, LUG_TIP_MM],
                   'tangential_build_allowance_mm': TANGENTIAL_BUILD_ALLOWANCE_MM})
    geometry = json.loads(doc.R5.MotionGeometry)
    geometry['yaw_limit'] = report
    doc.R5.MotionGeometry = json.dumps(geometry, ensure_ascii=False)
    return report
