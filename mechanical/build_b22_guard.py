"""Build the transparent B22 enclosure and its externally serviceable roof stop."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path

import FreeCAD as App
import Part

from build_b18_external_connections import LANES, Z
from primitives import box, cylinder, print_mesh
from stock import hexagon, nut, socket_screw


FACE = 150.
INNER = 147.
BOTTOM = -83.
TOP = 262.
BASE_THICKNESS = 10.
HOLE = 1.70
BOLT_LENGTH = 16.
NUT_HEIGHT = 2.4
RAIL_ROWS = (-73., 246.)
VENT_X = tuple(range(-90, 91, 10))
VENT_Y = (-116., 116.)
VENT_LENGTH = 34.
PANEL_SHADE = (.76, .87, .91)
ANGLE_SHADE = (.71, .72, .72)
CLIP_SHADE = (.24, .31, .34)


def flipped(lo, hi, sign):
    return (lo, hi) if sign > 0 else (-hi, -lo)


def bounds(data, axis, limits):
    out = list(data)
    out[axis] = limits
    return out


def rectangular(ranges):
    return box(*(value for interval in ranges for value in interval))


def hole(start, axis, depth):
    return cylinder(HOLE, depth, start, axis)


def add(doc, name, shape, color=CLIP_SHADE, transparency=0):
    solid = shape.removeSplitter()
    if not solid.isValid() or len(solid.Solids) != 1:
        raise ValueError(f'{name} is not one valid solid')
    obj = doc.addObject('Part::Feature', name)
    obj.Shape = solid
    if obj.ViewObject:
        obj.ViewObject.ShapeColor = color
        obj.ViewObject.Transparency = transparency
    return obj


def delta(point, axis, distance):
    return tuple(x + a * distance for x, a in zip(point, axis))


def bolt(doc, report, name, seat, axis, grip, mates):
    if grip + NUT_HEIGHT + .49 > BOLT_LENGTH:
        raise ValueError(f'M3×16 lacks exposed thread at {name}')
    socket = hexagon(2.54, 2.1, delta(seat, axis, -3.01), axis)
    screw = socket_screw(3, BOLT_LENGTH, seat, axis).cut(socket)
    nut_face = delta(seat, axis, grip)
    hexnut = nut(3, nut_face, axis).cut(
        cylinder(1.52, NUT_HEIGHT+.2, delta(nut_face, axis, -.1), axis))
    add(doc, name+'Screw', screw, ANGLE_SHADE)
    add(doc, name+'Nut', hexnut, ANGLE_SHADE)
    report.append(dict(id=name, seat_mm=seat, axis=axis, grip_mm=grip, connects=mates,
                       screw='ISO 4762 M3×16', nut='ISO 4032 M3', key_af_mm=2.5, spanner_af_mm=5.5))


def outside_rail(sx, sy, height):
    side = rectangular([flipped(150., 152., sx), flipped(132., 152., sy), height])
    facing = rectangular([flipped(132., 152., sx), flipped(150., 152., sy), height])
    return side.fuse(facing)


def inside_rail(sx, sy, height):
    # The removable rear panels occupy the 3.60 mm track behind the rear stop lip.
    offset = .60 if sy > 0 else 0.
    side = rectangular([flipped(145., 147., sx), flipped(132.-offset, 147.-offset, sy), height])
    facing = rectangular([flipped(132., 147., sx), flipped(145.-offset, 147.-offset, sy), height])
    return side.fuse(facing)


def corner_rails(doc, report):
    panel_holes = {'GuardFront': [], 'GuardLeft': [], 'GuardRight': []}
    for sx, side_label in ((-1, 'Left'), (1, 'Right')):
        for sy, face_label in ((-1, 'Front'), (1, 'Rear')):
            segments = (('Low', (BOTTOM, BOTTOM+30.), RAIL_ROWS[:1]),
                        ('High', (TOP-30., TOP), RAIL_ROWS[1:])) if sy < 0 else (
                            ('', (BOTTOM, TOP), RAIL_ROWS),)
            for end, height, rows in segments:
                tag = f'Guard{face_label}{side_label}{end}'
                outer = outside_rail(sx, sy, height)
                inner = inside_rail(sx, sy, height)
                cutters = []
                for row, z in enumerate(rows, 1):
                    mount = [(sx*152., sy*138., z, (-sx, 0., 0.), 'Guard'+side_label)]
                    if sy < 0:
                        mount.append((sx*139., -152., z+10., (0., 1., 0.), 'GuardFront'))
                    for leg, (x, y, z, axis, panel) in enumerate(mount, 1):
                        seat = (x, y, z)
                        cuts = hole(delta(seat, axis, -.1), axis, 7.2)
                        panel_holes[panel].append(cuts)
                        cutters.append(cuts)
                        bolt(doc, report, f'{tag}{row}{leg}', seat, axis, 7.,
                             (tag+'Outside', panel, tag+'Inside'))
                add(doc, tag+'Outside', outer.cut(cutters), ANGLE_SHADE)
                add(doc, tag+'Inside', inner.cut(cutters), ANGLE_SHADE)
    return panel_holes


def floor_clips(doc, report, panel_holes, base_holes):
    for sx, tag in ((-1, 'Left'), (1, 'Right')):
        for label, y0 in (('Front', -120.), ('Rear', 120.)):
            name = f'GuardFloor{tag}{label}'
            leg = rectangular([flipped(145., 147., sx), (y0-10., y0+10.), (BOTTOM, BOTTOM+15.)])
            foot = rectangular([flipped(132., 147., sx), (y0-10., y0+10.), (BOTTOM, BOTTOM+2.)])
            top_hole = hole((sx*137., y0, BOTTOM-BASE_THICKNESS-.1), (0., 0., 1.), BASE_THICKNESS+2.2)
            side_axis = (-sx, 0., 0.)
            side_hole = hole((sx*150.1, y0, BOTTOM+9.), side_axis, 5.2)
            base_holes.append(top_hole)
            panel_holes['Guard'+tag].append(side_hole)
            add(doc, name, leg.fuse(foot).cut([top_hole, side_hole]), ANGLE_SHADE)
            bolt(doc, report, name+'Base', (sx*137., y0, BOTTOM-BASE_THICKNESS),
                 (0., 0., 1.), BASE_THICKNESS+2., ('GuardBase', name))
            bolt(doc, report, name+'Side', (sx*150., y0, BOTTOM+9.), side_axis, 5., ('Guard'+tag, name))


def footing(doc, report, base_holes):
    # Three chocks restrain the outer Ø186 mm fixed base against horizontal motion.
    for index, angle in enumerate((-90., 30., 150.), 1):
        local = box(93.6, 110., -9., 9., BOTTOM, BOTTOM+3.)
        shoulder = box(93.6, 99.0, -9., 9., BOTTOM, BOTTOM+8.)
        offset = App.Rotation(App.Vector(0., 0., 1.), angle)
        c = offset.multVec(App.Vector(104.5, 0., BOTTOM-BASE_THICKNESS))
        axis = (0., 0., 1.)
        cut = hole(delta(tuple(c), axis, -.1), axis, BASE_THICKNESS+3.2)
        part = local.fuse(shoulder)
        part.rotate(App.Vector(0., 0., 0.), App.Vector(0., 0., 1.), angle)
        name = f'GuardBaseChock{index}'
        add(doc, name, part.cut(cut))
        base_holes.append(cut)
        bolt(doc, report, name, tuple(c), axis, BASE_THICKNESS+3., ('GuardBase', name))
    for sx in (-1, 1):
        for sy in (-1, 1):
            name = f'GuardFoot{sx+2}{sy+2}'
            start = (sx*140., sy*140., BOTTOM-BASE_THICKNESS-6.)
            add(doc, name, cylinder(7., 6., start))


def keeper_clip(doc, report, panel_holes, name, side, centre, sign):
    other = 1-side
    limits = bounds([(0., 1.)]*3, other, (centre-8., centre+8.))
    limits[2] = (TOP-16., TOP+6.8)
    leg = rectangular(bounds(limits, side, flipped(150., 155., sign)))
    limits[2] = (TOP+3.75, TOP+6.8)
    tongue = rectangular(bounds(limits, side, flipped(142., 155., sign)))
    mount = [0., 0., TOP-8.5]
    mount[side], mount[other] = sign*155., centre
    axis = [0., 0., 0.]
    axis[side] = -sign
    cut = hole(delta(mount, axis, -.1), axis, 8.2)
    panel = 'GuardFront' if side == 1 else 'GuardRight' if sign > 0 else 'GuardLeft'
    panel_holes[panel].append(cut)
    add(doc, name, leg.fuse(tongue).cut(cut))
    bolt(doc, report, name, tuple(mount), tuple(axis), 8., (panel, name))


def roof_stop(doc, report):
    # The only fastener needed after the roof slides home is entirely outside the box.
    foot = box(-10., 10., 150., 156., TOP-18., TOP-2.)
    ledge = box(-10., 10., 155., 166.2, TOP-6., TOP-2.)
    tab = box(-9., 9., 150.35, 166.2, TOP-2., TOP+6.5)
    wall_seat, wall_axis = (0., 156., TOP-15.), (0., -1., 0.)
    latch_seat, latch_axis = (0., 161.7, TOP+6.5), (0., 0., -1.)
    wall_hole = hole(delta(wall_seat, wall_axis, -.1), wall_axis, 9.2)
    lock_hole = hole(delta(latch_seat, latch_axis, -.1), latch_axis, 12.7)
    add(doc, 'GuardRoofStopBracket', foot.fuse(ledge).cut([wall_hole, lock_hole]))
    add(doc, 'GuardRoofStopTab', tab.cut(lock_hole))
    bolt(doc, report, 'GuardRoofStopBracket', wall_seat, wall_axis, 9., ('GuardRearTop', 'GuardRoofStopBracket'))
    bolt(doc, report, 'GuardRoofStopTab', latch_seat, latch_axis, 12.5, ('GuardRoofStopTab', 'GuardRoofStopBracket'))
    return wall_hole


def rear_seam(doc, report):
    top_drills, bottom_drills = [], []
    for side, x in (('Left', -75.), ('Right', 75.)):
        axis = (0., -1., 0.)
        clamp_axis = (0., 0., -1.)
        clamp_seat = (x, 159.5, Z+2.)
        clamp = hole(delta(clamp_seat, clamp_axis, -.1), clamp_axis, 4.2)
        for label, sign, drills in (('Bottom', -1., bottom_drills), ('Top', 1., top_drills)):
            name = 'GuardSeam'+side+label
            wall_z = sorted((Z, Z+sign*15.))
            lip_z = sorted((Z, Z+sign*2.))
            wall = box(x-9., x+9., 150., 152., *wall_z)
            lip = box(x-9., x+9., 150., 165., *lip_z)
            seat = (x+(4.7 if x < 0. else -4.7), 152., Z+sign*8.)
            through = hole(delta(seat, axis, -.1), axis, 5.2)
            drills.append(through)
            add(doc, name, wall.fuse(lip).cut([clamp, through]), ANGLE_SHADE)
            bolt(doc, report, name, seat, axis, 5., ('GuardRear'+label, name))
        bolt(doc, report, 'GuardSeam'+side+'Join', clamp_seat, clamp_axis, 4.,
             ('GuardSeam'+side+'Top', 'GuardSeam'+side+'Bottom'))
    return top_drills, bottom_drills


def printed_clips(doc, folder):
    folder.mkdir(parents=True, exist_ok=True)
    for key, name, orientation in (
        ('GuardBaseChock1', 'guard-base-chock', None),
        ('GuardRoofSideRight', 'guard-roof-keeper', 'z-'),
        ('GuardRoofStopBracket', 'guard-roof-stop-bracket', 'y+'),
        ('GuardRoofStopTab', 'guard-roof-stop-tab', None),
    ):
        print_mesh(doc.getObject(key).Shape, folder/f'{name}.stl', orientation)


def vents():
    cap = VENT_LENGTH/2.-2.
    for x in VENT_X:
        for y in VENT_Y:
            web = box(x-2., x+2., y-cap, y+cap, TOP-.1, TOP+3.1)
            yield web.fuse([cylinder(2., 3.2, (x, y+offset, TOP-.1)) for offset in (-cap, cap)])



def acrylic_corner_bevel(sx, sy):
    z = BOTTOM-.1
    pts = [App.Vector(sx*x, sy*y, z) for x, y in ((150., 150.), (148., 150.), (150., 148.))]
    return Part.Face(Part.makePolygon(pts + pts[:1])).extrude(App.Vector(0., 0., TOP-BOTTOM+.2))


def panels(doc, holes, floor, rear_hole, rear_seam_drills):
    panels = {
        'GuardFront': box(-INNER, INNER, -FACE, -INNER, BOTTOM, TOP),
        'GuardLeft': box(-FACE, -INNER, -FACE, FACE, BOTTOM, TOP).cut([acrylic_corner_bevel(-1, sy) for sy in (-1, 1)]),
        'GuardRight': box(INNER, FACE, -FACE, FACE, BOTTOM, TOP).cut([acrylic_corner_bevel(1, sy) for sy in (-1, 1)]),
        'GuardRoof': box(-149.6, 149.6, -FACE, 149.6, TOP, TOP+3.).cut(list(vents())),
        'GuardBase': box(-FACE, FACE, -FACE, FACE, BOTTOM-BASE_THICKNESS, BOTTOM).cut(floor),
    }
    motion = json.loads(doc.R5.MotionGeometry)
    camera_port = motion.get('camera_cable', {}).get('case_exit_mm')
    if camera_port is not None and (camera_port[1:] != [INNER, Z] or not 0. < camera_port[0] < 65.):
        raise ValueError('The camera cable exit must fit the rear split panel and seam hardware')
    ports = []
    for lane in LANES:
        centers = (camera_port[0],) if camera_port is not None and lane.name == 'camera USB-A' else lane.cable_centers
        ports.extend(dict(x_mm=x, z_mm=Z, u_mm=x+146.7, lead_od_mm=lane.diameter, aperture_mm=lane.diameter+.9)
                     for x in centers)
    cable_bores = [cylinder(port['aperture_mm']/2., 3.2, (port['x_mm'], INNER-.1, Z), (0., 1., 0.))
                   for port in ports]
    top_drills, bottom_drills = rear_seam_drills
    panels['GuardRearTop'] = box(-146.7, 146.7, INNER, FACE, Z, TOP).cut([*cable_bores, rear_hole, *top_drills])
    panels['GuardRearBottom'] = box(-146.7, 146.7, INNER, FACE, BOTTOM, Z).cut([*cable_bores, *bottom_drills])
    for name, shape in panels.items():
        fitted = shape.cut(holes[name]) if name in holes else shape
        acrylic = name != 'GuardBase'
        add(doc, name, fitted, PANEL_SHADE if acrylic else CLIP_SHADE, 87 if acrylic else 0)
    return ports


def panel_drills(rows):
    origins = {'GuardFront': ((0, 2), (-147., BOTTOM)),
               'GuardLeft': ((1, 2), (-150., BOTTOM)),
               'GuardRight': ((1, 2), (-150., BOTTOM)),
               'GuardRearTop': ((0, 2), (-146.7, Z)),
               'GuardRearBottom': ((0, 2), (-146.7, BOTTOM)),
               'GuardBase': ((0, 1), (-150., -150.))}
    return {part: [dict(uv_mm=[row['seat_mm'][index]-offset for index, offset in zip(axes, origin)],
                       diameter_mm=2*HOLE) for row in rows if part in row['connects']]
            for part, (axes, origin) in origins.items()}


def build(source, output, print_dir=None):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate guard CAD output')
    doc = App.openDocument(str(source.resolve()))
    try:
        hardware, base_holes = [], []
        panel_holes = corner_rails(doc, hardware)
        floor_clips(doc, hardware, panel_holes, base_holes)
        footing(doc, hardware, base_holes)
        for tag, sx in (('Left', -1), ('Right', 1)):
            keeper_clip(doc, hardware, panel_holes, 'GuardRoofFront'+tag, 1, sx*112., -1)
            keeper_clip(doc, hardware, panel_holes, 'GuardRoofSide'+tag, 0, 108., sx)
        rear_hole = roof_stop(doc, hardware)
        seam_drills = rear_seam(doc, hardware)
        ports = panels(doc, panel_holes, base_holes, rear_hole, seam_drills)
        if print_dir is not None:
            printed_clips(doc, print_dir)
        doc.Label = 'R5 B22 · fastened transparent guard'
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.recompute()
        doc.saveAs(str(output.resolve()))
        report = {
            'source_sha256': sha256(source.read_bytes()).hexdigest(),
            'guard_cad_sha256': sha256(output.read_bytes()).hexdigest(),
            'acrylic_panels_mm': {'front': [294., 345., 3.], 'sides_each': [300., 345., 3.],
                                  'rear_top': [293.4, TOP-Z, 3.], 'rear_bottom': [293.4, Z-BOTTOM, 3.],
                                  'roof': [299.2, 299.6, 3.]},
            'plywood_base_mm': [300., 300., BASE_THICKNESS],
            'corner_angle_stock_mm': {'outer_section': [20., 20., 2.], 'inner_section': [15., 15., 2.],
                                      'rear_length_mm': 345., 'rear_quantity_each': 2,
                                      'front_length_mm': 30., 'front_quantity_each': 4},
            'front_vertical_seams': 'Continuous clear PMMA edge bonds. Bond front and side panels as a U before closing the rear.',
            'acrylic_spec': '3 mm clear PMMA with elastic modulus at least 2.5 GPa',
            'acrylic_reference': 'https://www.plexiglas.de/en/products/plexiglas/plexiglas-gs-xt',
            'edge_bond_reference': 'https://www.plexiglas.de/en/service/processing/bonding-plexiglas',
            'panel_drill_axes': 'Millimetres from lower edge and the negative world axis edge. Forward view has world +X to the right.',
            'floor_clips': {'stock_mm': [15., 15., 2.], 'cut_length_mm': 20., 'quantity': 4},
            'rear_seam_clips': {'stock_mm': [15., 15., 2.], 'cut_length_mm': 18., 'quantity': 4,
                                'join_x_mm': [-75., 75.]},
            'printed_clips': {'guard-base-chock': 3, 'guard-roof-keeper': 4,
                              'guard-roof-stop-bracket': 1, 'guard-roof-stop-tab': 1},
            'base_chocks': 3,
                'base_feet_mm': {'diameter': 14., 'height': 6., 'quantity': 4},
                'guard_fitting_extents_mm': [[-158., -158., -99.], [158., 166.2, 271.5]],
            'rear_panel_slot_mm': 3.6, 'roof_lift_slack_mm': .75, 'roof_pullout_slack_mm': .75,
            'side_panel_outer_corner_bevel_mm': 2.,
            'inside_min_mm': [-INNER, -INNER, BOTTOM], 'inside_max_mm': [INNER, INNER, TOP],
            'rear_cable_ports': ports,
            'roof_vents': {'width_mm': 4., 'length_mm': VENT_LENGTH, 'count': len(VENT_X)*len(VENT_Y),
                           'centers_uv_mm': [[x+149.6, y+150.] for x in VENT_X for y in VENT_Y]},
            'panel_through_drills_uv_mm': panel_drills(hardware),
            'stock_fasteners': {'M3×16 ISO 4762': len(hardware), 'M3 ISO 4032': len(hardware)},
            'fasteners': hardware,
        }
        output.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--print-dir', type=Path)
    build(**vars(parser.parse_args()))
