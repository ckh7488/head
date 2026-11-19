"""Build the manufacturing-review parts from the six-axis R5 B1 FreeCAD assembly.

Run with FreeCAD's Python modules available. Coordinates are millimetres.
"""
from pathlib import Path
from math import cos, hypot, sin, radians
import sys

import FreeCAD as App
import MeshPart
import Part

V = App.Vector
HERE = Path(__file__).resolve().parent
BUILD = HERE.parent / 'build' / 'mechanical'
SOURCE = HERE / 'inputs' / 'R5-B1-Jaw-Assembly.FCStd'


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1-x0, y1-y0, z1-z0, V(x0, y0, z0))


def cylinder(radius, height, start, direction=(0, 0, 1)):
    return Part.makeCylinder(radius, height, V(*start), V(*direction))


def holes(shape, radius, depth, centres, direction=(0, 0, 1)):
    return shape.cut([cylinder(radius, depth, point, direction) for point in centres])


def rounded_beam(a, b, radius):
    start, finish = V(*a), V(*b)
    ray = finish-start
    return Part.makeCylinder(radius, ray.Length, start, ray).fuse([
        Part.makeSphere(radius, start), Part.makeSphere(radius, finish),
    ]).removeSplitter()


def centred_frame(shape, origin, right, normal):
    x, z = V(*right), V(*normal)
    rotation = App.Rotation(x, z.cross(x), z, 'ZXY')
    shape = shape.copy()
    shape.Placement = App.Placement(V(*origin), rotation).multiply(shape.Placement)
    return shape


def lid_link(x, path):
    half_width = 2.85
    thick = 2.6
    xi = x-thick/2
    sections = [cylinder(half_width, thick, (xi, y, z), (1, 0, 0)) for y, z in path]
    for (y0,z0),(y1,z1) in zip(path, path[1:]):
        dx, dy = y1-y0, z1-z0
        d = hypot(dx,dy)
        ny, nz = -dy*half_width/d, dx*half_width/d
        line = [V(xi,y0+ny,z0+nz),V(xi,y1+ny,z1+nz),V(xi,y1-ny,z1-nz),V(xi,y0-ny,z0-nz)]
        sections.append(Part.Face(Part.makePolygon(line+[line[0]])).extrude(V(thick, 0, 0)))
    solid = sections[0].fuse(sections[1:])
    return holes(solid, 1.2, 5., [(xi-1, y, z) for y,z in (path[0], path[-1])], (1, 0, 0)).removeSplitter()


def xl330_face(extra=None, extra_drills=(), half_width=13., far_edge=27.):
    plate = box(-half_width, half_width, -12, far_edge, -3, -.3)
    if extra:
        plate = plate.fuse(extra)
    plate = plate.cut(cylinder(8.72, 5, (0, 0, -4)))
    for x in (-8, 8):
        for y in (-7.5, 22.5):
            plate = plate.cut(cylinder(1.12, 4, (x, y, -3.5)))
            plate = plate.cut(Part.makeCone(1.12, 2.20, 1.08, V(x, y, -1.38)))
    for x, y in extra_drills:
        plate = plate.cut(cylinder(1.70, 5, (x, y, -4)))
        plate = plate.cut(Part.makeCone(1.70, 3.15, 1.45, V(x, y, -1.75)))
    return plate.removeSplitter()


def fix_motors(doc):
    repaired = {}
    for name, slug, side in [
        ('Part008', '05_yaw_servo_jaw_1', -1), ('Part009', '05_yaw_servo_jaw_2', 1),
    ]:
        seat = doc.getObject(name).Shape
        side_clear = box(-14.55, 0, -6, 36, -72, -63.6) if side < 0 else box(0, 14.55, -6, 36, -72, -63.6)
        repaired[name] = (slug, seat.cut(side_clear), None)
    yaw = doc.Part007.Shape.cut(cylinder(4.35, 9, (0, 0, -39)))
    yaw = yaw.cut(cylinder(46, .95, (0, 0, -38.0)).cut(cylinder(42.55, 1.1, (0, 0, -38.05))))
    pitch = doc.Part016.Shape.cut(box(45.0, 50, -15, 15, 98, 126))
    pitch = pitch.cut(cylinder(4.35, 2.45, (35.7, 0, 112), (1, 0, 0)))
    d_bore = cylinder(4.12, 7., (38.65, 0, 112), (1, 0, 0)).common(box(38.6, 46, -5, 5, 107, 115.15))
    pitch = pitch.cut(d_bore).cut(cylinder(1.34, 7., (43.3, 0, 113.7)))
    pitch_pin = cylinder(4., 27.3, (38.7, 0, 112), (1, 0, 0)).cut(box(38.5, 45.35, -5, 5, 115, 117))
    repaired['Part007'] = ('04_yaw_rotor', yaw, None)
    repaired['Part016'] = ('08_pitch_horn_to_8mm_clamp', pitch, 'x+')
    repaired['Part010'] = ('06_neck_mast', doc.Part010.Shape.cut(box(-20, 20, 6, 38, -34, -32.9)), None)

    yaw_origin = (0, -39, 111.45)
    yaw_case = doc.Part038.Shape.copy().rotate(V(*yaw_origin), V(0, 0, 1), -90)
    yaw_feet = [(-9., -24.), (15., -24.)]
    yaw_shape = xl330_face([
        box(-19.0, -10.4, -12.95, -5.05, -3, -.3),
        box(-19.0, -10.4, 11.05, 18.95, -3, -.3),
    ], [(-y-39, x) for x, y in yaw_feet], half_width=11.35, far_edge=25.6)
    cradle = doc.Part024.Shape.fuse([
        box(-12.7, -5.3, -27.65, -20.35, 103.5, 108.45),
        box(-13.4, -9.5, -24.9, -13.2, 103.5, 109.0),
        box(10.75, 18.7, -27.65, -20.35, 103.5, 108.45),
        box(12.1, 17.9, -27.45, -21.15, 106.6, 122.6),
    ])
    cradle = cradle.cut(box(-10.0, 25.0, -49.45, -28.54, 81.5, 108.44))
    cradle = holes(cradle, 1.34, 8., [(x, y, 101) for x, y in yaw_feet])
    for x in (-34., 34.):
        cradle = cradle.cut(box(x-3.1, x+3.1, -35.0, -31.4, 111.34, 115.0))
        rails = [box(x-8.35, x-5.55, -34.7, -31.7, 109.6, 128.0),
                 box(x+5.55, x+8.35, -34.7, -31.7, 109.6, 128.0),
                 box(x-8.35, x+8.35, -34.25, -31.8, 109.6, 111.3),
                 box(x-8.35, x+8.35, -33.7, -31.6, 120.1, 123.45)]
        cradle = cradle.fuse(rails)
    cradle = cradle.cut(box(30.9, 34.6, -14.9, -10.9, 118.6, 124.0))
    yaw_plate = centred_frame(yaw_shape, yaw_origin, (0, -1, 0), (0, 0, 1))
    cradle = cradle.cut(yaw_plate)
    repaired['Part024'] = ('12_eye_pitch_cradle', cradle, 'y+')
    repaired['Part039'] = ('XL330_M077_eye_yaw_front_plate', yaw_plate, None)

    pitch_feet_y = (4.6, 15.4)
    pitch_local_drills = [(10-y, 151-164.3) for y in pitch_feet_y]
    pitch_plate = xl330_face(box(-11., 11., -17.0, -9.5, -3, -.3), pitch_local_drills)
    pitch_plate = centred_frame(pitch_plate, (58.65, 10, 151), (0, -1, 0), (1, 0, 0))
    pitch_plate = pitch_plate.cut(box(54, 60, 18.80, 32, 137., 156.1))
    pitch_plate = pitch_plate.cut(box(54, 60, 21.60, 32, 121., 154.9))
    pitch_plate = pitch_plate.cut(box(54, 60, 21.5, 32, 156.1, 165.))
    repaired['Part042'] = ('XL330_M077_eye_pitch_front_plate', pitch_plate, 'y+')
    eye_stay = box(51.0, 55.65, .7, 32.8, 161.1, 167.5).fuse([
        box(48.8, 58.8, 31.0, 34.6, 138., 164.4),
    ])
    eye_stay = holes(eye_stay, 1.34, 7.1, [(49.2, y, 164.3) for y in pitch_feet_y], (1, 0, 0))
    eye_stay = holes(eye_stay, 1.70, 7.5, [(53., 29., z) for z in (142., 151.)], (0, 1, 0))
    repaired['Part064'] = ('34_eye_pitch_motor_stay', eye_stay, 'x+')

    blink_feet_z = (101., 107.0)
    blink_plate = xl330_face(box(11.7, 18.5, 8.5, 23.0, -3, -.3),
                            [(14., z-88) for z in blink_feet_z])
    blink_plate = centred_frame(blink_plate, (1.2, 43, 88), (0, 1, 0), (1, 0, 0))
    blink_plate = blink_plate.cut(cylinder(12.7, 1.2, (-.08, 25, 101), (1, 0, 0)))
    repaired['Part046'] = ('XL330_M288_blink_front_plate', blink_plate, 'y+')
    blink_backbone = doc.Part063.Shape.cut(box(-13.3, -2.1, 30.9, 65, 94, 132.5))
    blink_stay = blink_backbone.fuse([
        box(-7.7, -1.8, 53.6, 60.25, 97.3, 128.0),
        rounded_beam((-5.3, 55.4, 124.9), (-5.3, 27.5, 133.2), 3.4),
    ])
    blink_stay = holes(blink_stay, 1.34, 8.1, [(-8.7, 57., z) for z in blink_feet_z], (1, 0, 0))
    blink_stay = blink_stay.cut(box(-40, 40, 23, 45, 137., 156))
    blink_stay = blink_stay.cut(box(28.7, 50, 17.4, 20.55, 124, 162))
    repaired['Part063'] = ('24_blink_support_rail', blink_stay, 'y+')
    path = [(-30.75,119.0), (-25.2,112.7), (-18.8,112.7), (-10.5,123.5),
            (17.8,123.5), (25.7,104.5), (33.25,101.0)]
    repaired['Part057'] = ('23_left_lid_link_66p5mm', lid_link(-47.3,path), 'x+')
    repaired['Part060'] = ('23_right_lid_link_66p5mm', lid_link(47.3,path), 'x+')
    yoke = doc.Part011.Shape.cut([box(45.65,49.52,-20,37,85.3,132.6),box(-49.52,-45.65,-20,37,85.3,132.6)])
    repaired['Part011'] = ('07_pitch_yoke', yoke, 'y+')
    return repaired, pitch_pin, yaw_case


def cable_restraint(base):
    saddle = box(-34, 34, 93.12, 118, -77.7, -67.0).fuse([
        box(-34, -22.8, 83.0, 97.2, -77.7, -62.4),
        box(22.8, 34, 83.0, 97.2, -77.7, -62.4),
    ]).cut(cylinder(93.12, 24., (0, 0, -82)))
    saddle = saddle.cut(box(-3.85, 7.8, 92., 119., -73.7, -62.))
    for x in (-11.5, 15.75):
        saddle = saddle.cut(cylinder(4.18, 27., (x, 92., -67.0), (0, 1, 0)))
        saddle = saddle.cut(Part.makeCone(5.15, 4.18, 2.6, V(x, 93.12, -67.), V(0, 1, 0)))
        saddle = saddle.cut(Part.makeCone(4.18, 5.15, 2.6, V(x, 115.4, -67.), V(0, 1, 0)))
        for y in (99.4, 111.7):
            for x_slot in (x-5.75, x+5.75):
                saddle = saddle.cut(box(x_slot-1.38, x_slot+1.38, y-2.85, y+2.85, -78.2, -62.5))
    for x in (-2.55, 6.55):
        for y in (99.4, 111.7):
            saddle = saddle.cut(box(x-1.18, x+1.18, y-2.85, y+2.85, -78.2, -73.0))

    head_seats = [(-28.5, 93.6, -71.), (28.5, 93.6, -71.)]
    saddle = holes(saddle, 1.74, 18., [(x, 81.5, z) for x,y,z in head_seats], (0, 1, 0))
    saddle = holes(saddle, 4.35, 8., head_seats, (0, 1, 0))

    base = holes(base, 1.74, 19., [(x, 77.5, z) for x,y,z in head_seats], (0, 1, 0))
    base = holes(base, 4.35, 6.25, [(x, 77.5, z) for x,y,z in head_seats], (0, 1, 0))
    return base.removeSplitter(), saddle.removeSplitter()


def yaw_bearing_retention(doc):
    seat = doc.Part001.Shape.cut(cylinder(48.60, 1.15, (0, 0, -49.1)))
    pad = box(49.15, 51.10, -4.15, 4.15, -37.80, -36.8).common(cylinder(49.96, 2., (0, 0, -38.)))
    tab = box(49.15, 60.35, -4.7, 4.7, -37.0, -33.55).fuse(pad)
    tab = holes(tab, 1.72, 5.25, [(56.4, 0, -38.0)]).removeSplitter()
    tab = tab.cut(cylinder(49.16, 7., (0, 0, -39.0)))
    for i, angle in enumerate((0, 120, 240), start=1):
        x, y = 56.4*cos(radians(angle)), 56.4*sin(radians(angle))
        seat = seat.cut(cylinder(1.35, 8.2, (x, y, -44.9)))
        placed = tab.copy()
        placed.rotate(V(0, 0, 0), V(0, 0, 1), angle)
        obj = doc.addObject('Part::Feature', f'YawBearingRetainer{i}')
        obj.Shape = placed
        obj.Label = f'41 Outer-race keeper {i}'
        doc.Base_and_neck.addObject(obj)
    anti_lift = cylinder(47.15, 3.5, (0, 0, -32.45)).cut(cylinder(43.35, 4., (0, 0, -32.65)))
    top = doc.Part002.Shape.copy().translated(V(0, 0, .2)).fuse(anti_lift)
    return seat, top, tab


def board_mounts(doc, base):
    """Move both boards clear of the three vertical bearing supports."""
    tray_holes = {side: [(side*55+x, y-14.) for x in (-13, 13) for y in (-21, 21)] for side in (-1, 1)}
    for side in (-1, 1):
        for x in (side*55-13, side*55+13):
            for y in (-21, 21):
                base = base.cut(cylinder(4.08, 3.1, (x, y, -78.0)))
                base = base.fuse(cylinder(1.35, 4.4, (x, y, -82.4)))
        for x, y in tray_holes[side]:
            base = base.fuse(cylinder(4., 2.7, (x, y, -80.0)))
            base = base.cut(cylinder(1.35, 5.2, (x, y, -82.2)))
    radio = doc.Part070.Shape.copy().translated(V(0, -14, 0))
    radio_posts = [(-68., 9.3), (-40., -3.6)]
    radio_base = doc.Part071.Shape.copy().translated(V(0, -14, 0))
    for x,y in radio_posts:
        radio_base = radio_base.fuse(cylinder(2.85, 3.4, (x, y, -74.4)))
        radio_base = radio_base.cut(cylinder(.83, 4., (x, y, -74.4)))

    openrb = doc.Part069.Shape.copy().translated(V(0, -14, 3.2))
    rb_base = box(37, 73, -46.5, 24.5, -77.3, -74.3).common(cylinder(85.85, 5., (0,0,-78)))
    rb_base = holes(rb_base, 1.7, 5., [(x,y,-78.2) for x,y in tray_holes[1]])
    rb_base = rb_base.cut(box(44.0, 59.0, -37.2, 17.5, -78, -73.7))
    for x in (41.7, 61.3):
        for y in (-39.5, 19.5):
            rb_base = rb_base.cut(box(x-2.55, x+2.55, y-2.65, y+2.65, -78, -73.7))
    for o, shape in ((doc.Part069, openrb), (doc.Part070, radio)):
        o.Shape = shape
    return base, {
        'Part071': ('27_radio_plate', radio_base, None),
        'Part072': ('27_openrb_plate', rb_base, None),
    }


def print_mesh(shape, path, direction=None):
    model = shape.copy()
    if direction == 'x+':
        model.rotate(V(0, 0, 0), V(0, 1, 0), -90)
    elif direction == 'y+':
        model.rotate(V(0, 0, 0), V(1, 0, 0), 90)
    elif direction == 'z-':
        model.rotate(V(0, 0, 0), V(1, 0, 0), 180)
    mesh = MeshPart.meshFromShape(Shape=model, LinearDeflection=.075, AngularDeflection=.10, Relative=False)
    bound = mesh.BoundBox
    mesh.translate(-bound.Center.x, -bound.Center.y, -bound.ZMin)
    mesh.write(str(path))


def apply_repairs(doc, repairs, folder):
    folder.mkdir(exist_ok=True, parents=True)
    base_parts = {'CableSaddle', 'Part000', 'Part001', 'Part002', 'Part007', 'Part008',
                  'Part009', 'Part010', 'Part071', 'Part072'}
    for name, (slug, solid, direction) in repairs.items():
        solid = solid.removeSplitter()
        if not solid.isValid() or len(solid.Solids) != 1 or solid.Volume < 10:
            raise RuntimeError(f'{slug} is not one valid solid')
        if doc.getObject(name) is None:
            obj = doc.addObject('Part::Feature', name)
            obj.Label = slug.replace('_', ' ')
        else:
            obj = doc.getObject(name)
        obj.Shape = solid
        if name in base_parts:
            print_mesh(solid, folder/f'{slug}.stl', direction)
        print(f'{slug} · volume {solid.Volume:.1f} mm³', flush=True)


def main(output=BUILD):
    doc = App.openDocument(str(SOURCE))
    repairs, pitch_pin, yaw_case = fix_motors(doc)
    doc.Part015.Shape = pitch_pin
    doc.Part038.Shape = yaw_case
    doc.Part015.Label = 'Right pitch pin · Ø8 × 27.3 with 1 mm D-flat'
    base, saddle = cable_restraint(doc.Part000.Shape)
    base, board_trays = board_mounts(doc, base)
    repairs.update(board_trays)
    bearing_seat, bearing_top, bearer = yaw_bearing_retention(doc)
    repairs['Part001'] = ('02_outer_bearing_seat', bearing_seat, None)
    repairs['Part002'] = ('03_base_top', bearing_top, 'z-')
    repairs['Part000'] = ('01_base_cup_B2', base, None)
    repairs['CableSaddle'] = ('40_rear_cable_saddle', saddle, None)
    apply_repairs(doc, repairs, output/'STL')
    print_mesh(bearer, output/'STL'/'41_outer_race_keeper.stl', 'z-')
    section = base.common(box(-34.3, 34.3, 77.7, 94.0, -83., -61.5))
    fixture = box(-34.3, 34.3, 75.5, 92.4, -86.2, -81.8)
    fixture = section.fuse(fixture).removeSplitter()
    assert fixture.isValid() and len(fixture.Solids)==1
    print_mesh(fixture, output/'STL'/'Cable_saddle_test_fixture.stl')
    doc.Base_and_neck.addObject(doc.CableSaddle)
    doc.CableSaddle.addProperty('App::PropertyString', 'Mounting', 'Design')
    doc.CableSaddle.Mounting = 'Two power lanes and a recessed USB lane. Two straps per lead over a full-length liner. M3 screws transfer pull to the fixed base.'
    doc.Part000.Label = '01 Base cup B2 · rear saddle with flat washer seats'
    doc.R5.Label = 'R5 B2 · manufacturing review'
    doc.R5.Status = 'Fit review. Do not release head: blink links need clearance and hardware load tests.'
    doc.recompute()
    doc.saveAs(str(output/'R5-B2-Assembly.FCStd'))
    App.closeDocument(doc.Name)


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BUILD)
