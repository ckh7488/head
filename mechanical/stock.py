"""Stock metric socket screws and plain hex nuts for the printed assembly."""

from math import cos, pi, sin

from FreeCAD import Vector as V
import Part

from primitives import box, cylinder, print_mesh

X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
BLINK_MOUNTS = tuple((x, z) for x in (-20., 20.) for z in (143., 150.))
BLINK_CLAMPS = ((-53.9, -56., -50.9, -1), (10.2, 7.65, 13., 1), (54.15, 51.15, 56.25, 1))
HATCH_MOUNTS = ((-41.85,55.), (41.85,55.), (-26.9,82.25), (26.9,82.25))
HUB_MOUNTS = tuple((x, y) for x in (-30.8, 30.8) for y in (46.2, 72.8))
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
        pad = box(lo,hi,shaft_y-3.0,shaft_y+3.0,shaft_z+2.8,shaft_z+5.3)
        crank = crank.fuse([hub,pad])
        lead = (lo-.15,screw_x+.30) if side < 0 else (screw_x-.30,hi+.15)
        slot = box(*lead,shaft_y-2.13,shaft_y+2.13,shaft_z+2.55,shaft_z+4.30)
        cavity = hexagon(4.26, 1.75, (screw_x,shaft_y,shaft_z+2.55), Z, Y)
        tools = [cylinder(2.13, hi-lo+.45, (lo-.2,shaft_y,shaft_z), X),
                 cylinder(1.13, 4., (screw_x,shaft_y,shaft_z+1.52)), slot, cavity]
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
        printed(doc,part.Name,shoulder.fuse(sleeve).cut(bore),
                folder/f'45_blink_shaft_spacer_{label.lower()}.stl','x+')

    plate = doc.Part046.Shape
    for z in (183.,189.):
        plate = plate.fuse(cylinder(3.17, 1.5, (.9,0,z), (-1,0,0)))
        plate = plate.cut(cylinder(1.7, 3., (1.0,0,z), (-1,0,0)))
    printed(doc,'Part046',plate,folder/'xl330_m288_blink_front_plate.stl','x+')

    rail = doc.Part063.Shape
    for x,z in BLINK_MOUNTS:
        rail = rail.fuse(cylinder(2.12, 4.23, (x,18.77,z), Y))
        rail = rail.cut(hexagon(5.80, 6.4, (x,4.85,z), Y))
        rail = rail.cut(cylinder(1.70, 13., (x,10.8,z), Y))
    printed(doc,'Part063',rail,folder/'24_blink_rail_with_bearing_shoulders.stl','y+')


def cable_stock(doc, folder, layout):
    saddle = doc.CableSaddle.Shape
    for x in layout['cap_bolts_x_mm']:
        y = layout['cap_bolt_y_mm']
        plug = cylinder(2.12, 4.22, (x,y,-61.72))
        saddle = saddle.fuse(plug)
        saddle = saddle.cut(hexagon(5.8, 6.65, (x,y,-68.65), Z, Y))
        saddle = saddle.cut(cylinder(1.70, 4.75, (x,y,-62.20)))
    printed(doc,'CableSaddle',saddle,folder/'40_captive_cable_tray.stl')


def hatch_stock(doc, folder):
    base = doc.Part000.Shape
    for x,y in HATCH_MOUNTS:
        base = base.fuse(cylinder(2.35, 4.66, (x,y,-80.29)))
        base = base.cut(hexagon(5.8, 3.95, (x,y,-76.62)))
        base = base.cut(cylinder(1.73, 4.2, (x,y,-80.6)))
    printed(doc,'Part000',base,folder/'01_base_cup_B5.stl')

    hatch = doc.HubHolder.Shape
    for x,y in HUB_MOUNTS:
        hatch = hatch.cut(hexagon(5.8, 4.80, (x,y,-83.10)))
        hatch = hatch.cut(cylinder(1.7, 4.55, (x,y,-78.50)))
    printed(doc,'HubHolder',hatch,folder/'35_hub_service_hatch_B1.stl')
    for number in range(1,5):
        present = doc.getObject(f'HubBolt{number}')
        center = present.Shape.BoundBox.Center
        present.Shape = socket_screw(3,10.,(center.x,center.y,-72.5),(0,0,-1))
        present.Label = f'H{number} M3 × 10 socket screw'
    doc.HubHolder.Fasteners = 'Hatch ISO 10642 M3 × 10. PCB ISO 4762 M3 × 10. Plain M3 hex nuts.'


def ballast_stock(doc, folder):
    frame = doc.Part019.Shape
    for x,z in BALLAST_MOUNTS:
        frame = frame.fuse(cylinder(2.12, 4.26, (x,26.74,z), Y))
        frame = frame.cut(hexagon(5.80, 3.27, (x,22.8,z),Y))
        frame = frame.cut(cylinder(1.70, 5.30, (x,25.85,z),Y))
    printed(doc,'Part019',frame,folder/'09_head_frame.stl','y+')


def radio_board_stock(doc, folder):
    from radio import C3_HOLES, board_xy

    tray = doc.Part071.Shape
    for x,y in (board_xy(*corner) for corner in C3_HOLES):
        tray = tray.cut(hexagon(4.30, 2.20, (x,y,-77.45)))
        tray = tray.cut(cylinder(1.13, 4.5, (x,y,-75.45)))
    printed(doc,'Part071',tray,folder/'27_radio_plate.stl')


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
    printed(doc,'Part010',mast,folder/'06_neck_mast.stl')
    printed(doc,'Part011',yoke,folder/'07_pitch_yoke.stl','y+')
