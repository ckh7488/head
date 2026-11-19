"""Stock metric socket screws and plain hex nuts for the printed assembly."""

from math import cos, pi, sin

from FreeCAD import Vector as V
import Part

from fixtures import (
    CAP_BOLT_LENGTH, CAP_BOLT_SEAT_Z, CAP_BOLT_Y, CAP_BOLTS,
    CAP_NUT_FLOOR_Z, CAP_NUT_ROOF_Z, CAP_NUT_WIDTH,
)
from neck_joint import neck_base
from primitives import box, cylinder, print_mesh
from service_hatch import HUB_MOUNTS, HUB_SCREW_SEAT, revise_service, service_coupon

X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
BLINK_MOUNTS = tuple((x, z) for x in (-20., 20.) for z in (143., 150.))
BLINK_RAIL_NUT_Y = 12.80
BLINK_RAIL_SEAT_Y = 27.70
BLINK_RAIL_LENGTH = 16.
BLINK_CLAMPS = ((-53.9, -56., -50.9, -1), (10.2, 7.65, 13., 1), (54.15, 51.15, 56.25, 1))
BLINK_CLAMP_LENGTH = 8.
BLINK_CLAMP_NUT_Z = 156.63
BALLAST_MOUNTS = tuple((x, z) for x in (-28., 28.) for z in (143., 150.))
YOKE_MOUNTS = ((-12.,17.),(-12.,27.3),(12.,24.3))


def hexagon(flat, length, start, axis=Z, flat_normal=None):
    direction = V(*axis)
    normal = V(*(flat_normal or (X if abs(direction.z) > .5 else Z)))
    cross = direction.cross(normal)
    radius = flat / (3. ** .5)
    center = V(*start)
    points = [center + radius * (cos(a) * normal + sin(a) * cross)
              for a in (pi / 6 + i * pi / 3 for i in range(6))]
    return Part.Face(Part.makePolygon(points + points[:1])).extrude(direction * length)


def socket_screw(size, length, seat, axis):
    direction = V(*axis)
    head_r, head_h = {2: (1.93, 2.), 3: (2.78, 3.)}[size]
    bore = cylinder(size / 2., length, seat, axis)
    head = cylinder(head_r, head_h, seat, tuple(-direction))
    return bore.fuse(head)


def nut(size, start, axis=Z, flat_normal=None):
    width, thickness = {2: (4., 1.6), 3: (5.5, 2.4)}[size]
    return hexagon(width, thickness, start, axis, flat_normal)


def printed(doc, name, shape, path, direction=None):
    part = doc.getObject(name)
    part.Shape = shape.removeSplitter()
    if not part.Shape.isValid() or len(part.Shape.Solids) != 1:
        raise ValueError(f'{name} became a disconnected printed part')
    print_mesh(part.Shape, path, direction)


def crank_landing_face(crank):
    pad = crank.common(box(-51.55,-51.10,-35.,2.,129.,153.85)).translate(V(.25,0,0))
    return crank.fuse(pad).removeSplitter()


def blink_stock(doc, folder, layout):
    shaft_y, shaft_z = layout['shaft_yz_mm']
    angle = layout['phase_deg'] * pi / 180.
    shaft = cylinder(2., 112., (-56., shaft_y, shaft_z), X)
    for x, _, _, _ in BLINK_CLAMPS:
        shaft = shaft.cut(box(x-1.8,x+1.8,shaft_y-3,shaft_y+3,shaft_z+1.55,shaft_z+3))
    doc.Part048.Shape = shaft

    yc, zc = layout['servo_yz_mm']
    arm = layout['radius_mm']
    tip_y, tip_z = yc + arm * cos(angle), zc + arm * sin(angle)
    horn = doc.Part047.Shape
    horn = horn.fuse(cylinder(2.08, .95, (1.2,tip_y,tip_z), X))
    horn = horn.cut(hexagon(4.24, 1.78, (1.17,tip_y,tip_z), X))
    horn = horn.cut(cylinder(1.20, 3.4, (1.08,tip_y,tip_z), X))
    printed(doc,'Part047',horn,folder/'19_blink_servo_horn.stl','x+')
    drive = doc.Part056.Shape.fuse(cylinder(2.83, 2.15, (7.,tip_y,tip_z), X))
    drive = drive.cut(cylinder(1.19, 2.45, (6.90,tip_y,tip_z), X))
    printed(doc,'Part056',drive,folder/'22_blink_drive_link.stl','x+')

    for i, (part, crank_x, (screw_x, lo, hi, side)) in enumerate(zip(
            ('Part053','Part054','Part055'), layout['crank_x_mm'], BLINK_CLAMPS), start=1):
        crank = doc.getObject(part).Shape.copy()
        arm = layout['radius_mm' if i == 2 else 'lid_radius_mm']
        if i != 2:
            y, z = shaft_y + arm * cos(angle), shaft_z + arm * sin(angle)
            outer = crank_x + side * 1.3
            crank = crank.fuse(cylinder(2.08, .95, (outer,y,z), (-side,0,0)))
            crank = crank.cut(cylinder(1.20, 2.9, (outer+side*.12,y,z), (-side,0,0)))
        hub = cylinder(4.85, hi-lo, (lo,shaft_y,shaft_z), X)
        pad_lo, pad_hi = min(lo, screw_x-3.85), max(hi, screw_x+3.85)
        pad = box(pad_lo,pad_hi,shaft_y-4.2,shaft_y+4.2,shaft_z+2.35,shaft_z+6.40)
        crank = crank.fuse([hub,pad])
        lead = (pad_lo-.15,screw_x+.06) if side < 0 else (screw_x-.06,pad_hi+.15)
        slot = box(*lead,shaft_y-2.96,shaft_y+2.96,shaft_z+2.48,shaft_z+5.13)
        cavity = hexagon(5.94, 2.65, (screw_x,shaft_y,shaft_z+2.48), Z, Y)
        tools = [cylinder(2.13, hi-lo+.45, (lo-.2,shaft_y,shaft_z), X),
                 cylinder(1.69, 5.15, (screw_x,shaft_y,shaft_z+1.52)), slot, cavity]
        crank = crank.cut(tools)
        if i == 1:
            crank = crank_landing_face(crank)
        printed(doc,part,crank,folder/f'21_blink_shaft_crank_{i}.stl','x-' if i == 1 else 'x+')

    for label, x, length, side in (('Left',-30.,37.4,1), ('Right',24.,10.75,-1)):
        axis = (side,0,0)
        shoulder = cylinder(2.72, .7, (x,shaft_y,shaft_z), axis)
        sleeve = cylinder(3.55, length-.65, (x+.65*side,shaft_y,shaft_z), axis)
        bore = cylinder(2.13, length+.12, (x-.06*side,shaft_y,shaft_z), axis)
        part = doc.getObject(f'BlinkCollar{label}')
        part.Label = f'45 blink shaft spacer {label.lower()}'
        part.addProperty('App::PropertyBool','Printed','Design')
        part.Printed = True
        collar = shoulder.fuse(sleeve).cut(bore)
        if label == 'Left':
            collar = collar.cut(box(6.82, 7.62, shaft_y-4.2, shaft_y+4.2, shaft_z+2.42, shaft_z+4.0))
        printed(doc,part.Name,collar,
                folder/f'45_blink_shaft_spacer_{label.lower()}.stl','x+')

    plate = doc.Part046.Shape
    for z in (183.,189.):
        plate = plate.fuse(cylinder(3.17, 1.5, (.9,0,z), (-1,0,0)))
        plate = plate.cut(cylinder(1.7, 3., (1.0,0,z), (-1,0,0)))
    printed(doc,'Part046',plate,folder/'xl330_m288_blink_front_plate.stl','x+')

    rail = doc.Part063.Shape
    for x,z in BLINK_MOUNTS:
        rail = rail.fuse(cylinder(2.12, 4.23, (x,18.77,z), Y))
        rail = rail.cut(hexagon(5.87, BLINK_RAIL_NUT_Y+2.43+6.70, (x,-6.70,z), Y))
        rail = rail.cut(cylinder(1.70, 8.1, (x,BLINK_RAIL_NUT_Y+2.30,z), Y))
    rail = rail.cut([cylinder(1.73, 4.45, (x,18.95,z), Y) for x,z in BALLAST_MOUNTS])
    printed(doc,'Part063',rail,folder/'24_blink_rail_with_bearing_shoulders.stl','y+')


def cable_stock(doc, folder):
    floor, roof = CAP_NUT_FLOOR_Z, CAP_NUT_ROOF_Z
    saddle = doc.CableSaddle.Shape.fuse([
        box(lo, hi, 116.8, 125., -68.5, -57.5) for lo, hi in [(-52.25, -50.), (50., 52.25)]
    ])

    def mouth(x, y, half, clearance):
        points = [V(x + dx, y, z) for dx, z in [
            (-half, floor - clearance), (half, floor - clearance),
            (half, roof + clearance), (-half, roof + clearance),
        ]]
        return Part.makePolygon(points + points[:1])

    half = CAP_NUT_WIDTH / 2
    tip = CAP_BOLT_SEAT_Z - CAP_BOLT_LENGTH
    cuts = []
    for x in CAP_BOLTS:
        nose = hexagon(CAP_NUT_WIDTH+.12, roof - floor, (x, CAP_BOLT_Y, floor))
        nose = nose.common(box(x-half, x+half, CAP_BOLT_Y-3.6, CAP_BOLT_Y+.1, floor, roof))
        cuts.extend([
            nose,
            box(x-half, x+half, CAP_BOLT_Y, 125.2, floor, roof),
            Part.makeLoft([mouth(x, 124.1, half, 0.), mouth(x, 125.2, half+.4, .25)], True, True),
            cylinder(1.70, -57.35 - (tip-.7), (x, CAP_BOLT_Y, tip-.7)),
        ])
    saddle = saddle.cut(cuts)
    printed(doc,'CableSaddle',saddle,folder/'40_captive_cable_tray.stl')


def hatch_stock(doc, folder):
    base, hatch = revise_service(doc.Part000.Shape, hexagon)
    printed(doc, 'Part000', base, folder/'01_base_cup_B8.stl')
    printed(doc, 'HubHolder', hatch, folder/'35_hub_service_hatch_B8.stl')
    service_coupon(base, folder)
    for number, (x, y) in enumerate(HUB_MOUNTS, start=1):
        present = doc.getObject(f'HubBolt{number}')
        present.Shape = socket_screw(3, 8., (x, y, HUB_SCREW_SEAT), (0, 0, -1))
        present.Label = f'H{number} M3 × 8 socket screw'
    doc.HubHolder.Label = '35 B8 removable hub hatch · 4–5 mm plate'
    doc.HubHolder.Fasteners = 'Eight ISO 4762 M3 × 8 socket screws and top-loaded M3 hex nuts.'


def ballast_stock(doc, folder):
    frame = doc.Part019.Shape
    for x,z in BALLAST_MOUNTS:
        frame = frame.fuse(cylinder(2.12, 4.26, (x,26.74,z), Y))
        frame = frame.cut(hexagon(5.80, 3.27, (x,22.8,z),Y))
        frame = frame.cut(cylinder(1.73, 12.3, (x,18.95,z),Y))
    printed(doc,'Part019',frame,folder/'09_head_frame.stl','y+')


def radio_board_stock(doc, folder):
    from openrb import HOLES, NUT_SEAT, TOP, board_xy as rb_xy
    from radio import C3_HOLES, C3_NUT_SEAT, C3_TOP, board_xy

    for name, slug, centers, nut_seat, top in (
        ('Part071', '27_radio_plate', [board_xy(*corner) for corner in C3_HOLES], C3_NUT_SEAT, C3_TOP),
        ('Part072', '27_openrb_plate', [rb_xy(*corner) for corner in HOLES], NUT_SEAT, TOP),
    ):
        tray = doc.getObject(name).Shape
        for x, y in centers:
            roof = nut_seat + 1.61
            tray = tray.cut(hexagon(4.30, roof + 77.45, (x, y, -77.45)))
            tray = tray.cut(cylinder(1.13, top - 1.35 - roof, (x, y, roof - .20)))
        printed(doc, name, tray, folder/f'{slug}.stl')


def neck_stock(doc, folder):
    mast = doc.Part010.Shape
    yoke = doc.Part011.Shape
    for x in (-12.,12.):
        for y in (11.,31.):
            depth = 3.6 if (x,y) == (12.,11.) else 8.
            restored = cylinder(1.72,depth,(x,y,67.)).common(box(-18,18,2.5,30.5,67.,75.))
            yoke = yoke.fuse(restored)
    for x,y in YOKE_MOUNTS:
        entrance = (-18.3,x+.1) if x < 0 else (x-.1,18.3)
        slot=box(*entrance,y-2.9,y+2.9,59.4,62.1)
        pocket=hexagon(5.8,2.7,(x,y,59.4),Z,Y)
        mast=mast.cut([slot,pocket,cylinder(1.7,8.6,(x,y,58.7))])
        yoke=yoke.cut(cylinder(1.7,8.25,(x,y,66.9)))
    rotor, mast = neck_base(doc.Part007.Shape, mast, hexagon)
    printed(doc,'Part007',rotor,folder/'04_yaw_rotor.stl')
    printed(doc,'Part010',mast,folder/'06_neck_mast.stl')
    printed(doc,'Part011',yoke,folder/'07_pitch_yoke.stl','y+')
