"""Build R5 B9 from the six-axis R5 B1 FreeCAD assembly.

Run with FreeCAD's Python modules available. Coordinates are millimetres.
"""
from pathlib import Path
from math import cos, hypot, pi, radians, sin
import sys
import json
from tempfile import TemporaryDirectory

import FreeCAD as App
import Mesh
import MeshPart
import Part
import trimesh as tr

from primitives import box, cylinder, holes, print_mesh
from fixtures import ballast_mount, ballast_stud, cable_wall_fixture, captive_cables, fixture_parameters, rear_ballast
from motor_seats import JAW_STAY, head_pockets
from radio import c3_mount
from stock import ballast_stock, blink_stock, cable_stock, hatch_stock, neck_stock, radio_board_stock

V = App.Vector
HERE = Path(__file__).resolve().parent
BUILD = HERE.parent / 'build' / 'mechanical'
SOURCE = HERE / 'inputs' / 'R5-B1-Jaw-Assembly.FCStd'


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
    for x, y in extra_drills:
        plate = plate.cut(cylinder(1.70, 5, (x, y, -4)))
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
    radio, radio_base = c3_mount(doc.Part071.Shape.copy().translated(V(0, -14, 0)))
    doc.Part070.Label = 'ESP32-C3 board · front-facing USB-C'

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


BLINK_SHAFT_YZ=(-24.,154.)
BLINK_SERVO=(1.2,-14.,170.)
BLINK_PHASE=-56.
DRIVE_THROW=8.25
LID_THROW=11.5
HINGE_YZ=(-39.,119.)
HINGE_PINS={58:-58.75,59:9.25,61:-18.75,62:49.25}
BLINK_MOUNT_XZ=tuple((x,z) for x in (-20.,20.) for z in (143.,150.))
DRIVE_ARM=(DRIVE_THROW*cos(radians(BLINK_PHASE)),DRIVE_THROW*sin(radians(BLINK_PHASE)))
LID_ARM=(LID_THROW*cos(radians(BLINK_PHASE)),LID_THROW*sin(radians(BLINK_PHASE)))

def yz_prism(polygon, x, thickness):
    pt=[V(x,y,z) for y,z in polygon]
    return Part.Face(Part.makePolygon(pt+[pt[0]])).extrude(V(thickness,0,0))

def blink_link(x,yz1,yz2):
    return lid_link(x, [yz1,yz2])

def pin_tip(pivot, arm):
    return tuple(center+offset for center,offset in zip(pivot,arm))

def blink_crank(x, arm):
    yz=BLINK_SHAFT_YZ
    y,z=yz
    tip=pin_tip(yz,arm)
    solid=blink_link(x,yz,tip)
    hub=cylinder(4.85,2.85,(x-1.3,y,z),(1,0,0))
    joined=solid.fuse(hub)
    bore=cylinder(2.13,6.,(x-3,y,z),(1,0,0))
    bore=bore.common(box(x-3.1,x+3.1,y-3,y+3,z-3,z+1.67))
    cuts=[bore,cylinder(1.14,5,(x,y,z-5),(0,0,1))]
    return joined.cut(cuts).removeSplitter()

def eyelid(side):
    x=34.*side
    shell=Part.makeSphere(16.6).cut(Part.makeSphere(15.12))
    poly=[(0,0)]+[(-40*cos(radians(a)),40*sin(radians(a))) for a in (42,67,96,125,151)]
    shell=shell.common(yz_prism(poly,-24.,48.))
    ring1=cylinder(3.55,4.25,(-19.15,0,0),(1,0,0))
    ring2=cylinder(3.55,4.25,(14.9,0,0),(1,0,0))
    horn=blink_link(18.2,(0,0),LID_ARM)
    body=shell.fuse([ring1,ring2,horn]).cut(
        cylinder(1.12,42.,(-21,0,0),(1,0,0))).removeSplitter()
    if side<0:
        body=body.mirror(V(),V(1,0,0))
    return body.translate(V(x,-39,119))

def blink_bearing_arm(x):
    y,z=BLINK_SHAFT_YZ
    sleeve=cylinder(7.3,6.,(x-3,y,z),(1,0,0))
    arm=yz_prism([(y-4,z+5.8),(y+1,z+10.8),(8.,z+10.8),(18.,z+7.5),(23.,z+2.),
           (23.,z-14.5),(9.,z-12.),(y-1.5,z-6.4),(y-4.,z-4.)],x-3,6)
    sign=1 if x>0 else -1
    return sleeve.fuse(arm).cut([
        cylinder(5.12,5.1,(x-3.1*sign,y,z),(sign,0,0)),
        cylinder(4.68,8.,(x-4,y,z),(1,0,0)),
    ]).removeSplitter()

def support_cradle():
    body=box(-61.,61.,-22.5,-18.5,120.5,125.2)
    for inner,outer in [(-62.15,-57.65),(57.65,61.)]:
        rim=yz_prism([(-42.9,116),(-42.5,122),(-22.,127),(-18.5,124),(-18.5,120.6),(-39.,115.2)],inner,outer-inner)
        body=body.fuse(rim)
        body=body.cut(cylinder(1.62,outer-inner+.3,(inner-.15,-39,119),(1,0,0)))
    body=body.fuse(box(57.65,61.,-39.,-25.2,116.6,121.4))
    body=body.cut(cylinder(1.18,6.,(56,-29,119),(1,0,0)))
    for x in (-34.,34.):
        top=box(x-2.4,x+2.4,-41.4,-33.4,126.6,129.15)
        upper_root=box(x-2.4,x+2.4,-35.6,-32.7,120.9,128.3)
        bottom=box(x-2.4,x+2.4,-41.4,-20.9,108.0,110.7)
        spine=box(x-2.4,x+2.4,-22.2,-20.85,109.3,123.3)
        bridge=box(x-2.4,x+2.4,-35.3,-19.7,121.0,123.1)
        body=body.fuse([top,upper_root,bottom,spine,bridge]).cut(cylinder(1.13,25.2,(x,-39,106.5)))
    for x in (-8.,8.):
        foot=box(x-2.8,x+2.8,-50.2,-44.8,111.55,125.0)
        rib=yz_prism([(-50.0,120.8),(-45.2,119.2),(-18.8,121.3),(-18.8,125.3),(-48,123.9)],x-2.65,5.3)
        body=body.fuse([foot,rib]).cut(cylinder(1.30,9.5,(x,-47.6,111.3)))
    return body.removeSplitter()


def flat_xy(points, thickness, z, width):
    rods=[]
    for (x,y),(a,b) in zip(points,points[1:]):
        delta=V(a-x,b-y,0)
        n=V(-delta.y,delta.x,0)*(width/(2*delta.Length))
        start=V(x,y,z)
        end=V(a,b,z)
        border=[start+n,end+n,end-n,start-n,start+n]
        rods.append(Part.Face(Part.makePolygon(border)).extrude(V(0,0,thickness)))
    rods.extend(cylinder(width/2,thickness,(x,y,z)) for x,y in points)
    return rods[0].fuse(rods[1:]).removeSplitter()


def gaze_yaw_parts(doc):
    lift=V(-5.8,3.5,.4)
    body=doc.Part038.Shape.copy().translate(lift)
    source=doc.Part039.Shape.copy().translate(lift)
    plate=source.common(box(-20,22,-53,-25.6,108,113))
    feet=[box(x-3.0,x+3.0,-50.2,-44.8,108.85,111.55) for x in (-8.,8.)]
    plate=plate.fuse(feet)
    plate=holes(plate,1.56,5.,[(x,-47.6,108.) for x in (-8.,8.)]).removeSplitter()
    mx,yaw=-5.8,-35.5
    throw=13.5
    horn=cylinder(8.8,2.4,(mx,yaw,111.85)).fuse(flat_xy([(mx,yaw),(mx,yaw+throw)],2.4,111.85,6.0))
    horn=holes(horn,1.20,6.,[(mx+6*cos(radians(v)),yaw+6*sin(radians(v)),111.0) for v in range(0,360,90)])
    horn=horn.cut([cylinder(2.8,5,(mx,yaw,111.0)),cylinder(1.12,9.,(mx,yaw+throw,111.5))]).removeSplitter()
    points=[(-34,-25.5),(-18,-25.5),(-11,-22.),(0.,-22.),(16,-25.5),(34,-25.5)]
    tie=flat_xy(points,2.9,114.55,4.6)
    tie=holes(tie,1.17,6.,[(x,y,113.) for x,y in (points[0],(mx,yaw+throw),points[-1])]).removeSplitter()
    return {'Part024':support_cradle(),'Part038':body,'Part039':plate,'Part040':horn,'Part037':tie}


def eyeball(x):
    y,z=-39.,119.
    origin=V(x,y,z)
    outer=Part.makeSphere(14.,origin)
    inner=Part.makeSphere(12.35,origin)
    shell=outer.cut([inner,box(x-20,x+20,y+7.5,y+35,z-20,z+20)])
    ribs=[box(x-2.7,x+2.7,y-12.25,y+2.05,z+h-.95,z+h+.95).common(outer) for h in (-5.9,5.9)]
    crank=flat_xy([(x,y),(x,y+13.5)],2.4,z-7.2,5.4)
    cut=[cylinder(1.13,32.,(x,y,z-16)),cylinder(1.16,7.,(x,y+13.5,z-10))]
    cut.extend(box(x-8,x+8,y+2.8,y+14,z+lo,z+hi) for lo,hi in [(-11.65,-7.4),(7.1,11.0)])
    return shell.fuse([*ribs,crank]).cut(cut).removeSplitter()

def clearance_tool(x, a, b, radius, depth):
    left=x-depth/2.
    dy,dz=b[0]-a[0],b[1]-a[1]
    d=(dy**2+dz**2)**.5
    ny,nz=-dz*radius/d,dy*radius/d
    points=[(a[0]+ny,a[1]+nz),(b[0]+ny,b[1]+nz),(b[0]-ny,b[1]-nz),(a[0]-ny,a[1]-nz)]
    bridge=yz_prism(points,left,depth)
    return bridge.fuse([
        cylinder(radius,depth,(left,*a),(1,0,0)),
        cylinder(radius,depth,(left,*b),(1,0,0)),
    ]).removeSplitter()


def cut_running_clearance(doc):
    targets = {'Part073': [], 'Jaw_36_left_jaw_servo_stay': [],
               'Jaw_37_right_jaw_bearing_stay': [], 'Part076': [], 'Part077': []}
    with TemporaryDirectory() as temp:
        path=Path(temp)/'shape.stl'

        def mesh(solid):
            MeshPart.meshFromShape(Shape=solid,LinearDeflection=.045,AngularDeflection=.12,Relative=False).write(str(path))
            return tr.load_mesh(path)

        targets[JAW_STAY].extend(mesh(pocket) for pocket in head_pockets(JAW_STAY))

        for side in (-1,1):
            blade=[]
            for degrees in range(-1,93,3):
                a=radians(BLINK_PHASE+degrees)
                dy,dz=LID_THROW*cos(a),LID_THROW*sin(a)
                start=(-39.+dy,119.+dz)
                end=(BLINK_SHAFT_YZ[0]+dy,BLINK_SHAFT_YZ[1]+dz)
                blade.append(mesh(clearance_tool(side*49.25,start,end,4.0,4.5)))
                ear=clearance_tool(side*52.2,(-39.,119.),start,4.1,4.8)
                blade.append(mesh(ear.common(box(-60,60,-36.7,-20.5,103.2,134.0))))
                axis=(-side,0,0)
                blade.append(mesh(cylinder(3.05,3.2,(side*48.2,*start),axis)))
                blade.append(mesh(cylinder(1.75,5.,(side*48.2,*start),axis)))
                blade.append(mesh(cylinder(2.68,2.85,(side*53.20,*start),(side,0,0))))
            cutter=tr.boolean.union(blade,engine='manifold')
            x=34.*side
            targets['Part076' if side<0 else 'Part077']=[
                mesh(box(x+19.04,x+20.43,-55.,-36.,112.8,125.2)),
                mesh(box(x-20.43,x-19.04,-55.,-36.,112.8,125.2)),
            ]
            targets['Part073'].append(cutter)
            if side<0:
                targets['Jaw_36_left_jaw_servo_stay'].append(cutter)
        targets['Part076'].append(mesh(box(-15.4,-10.,-53.,-35.5,113.9,116.0)))
        targets['Part073'].append(mesh(box(60.85,64.85,-20.0,-10.3,127.7,135.2)))
        targets['Part073'].append(mesh(box(-10.,24.3,-36.4,-20.5,76.2,92.8)))
        for inside, outside in [(-69., -56.7), (56.7, 69.)]:
            targets['Part073'].append(mesh(box(inside, outside, -13.5, -5.7, 89.35, 96.9)))
        targets['Jaw_37_right_jaw_bearing_stay'].append(mesh(box(44.18, 46.6, -15.2, -11.1, 90.9, 96.6)))
        for inner,outer in [(-56.8,-53.2),(53.2,56.8)]:
            strip=box(inner,outer,-23.1,-17.9,119.75,125.95)
            moving=tr.boolean.union([mesh(strip.copy().rotate(V(0,-39,119),V(1,0,0),a))
                                     for a in (-9,-6,-3,0,3,6,9)],engine='manifold')
            targets['Part073'].append(moving)
        for name,cutters in targets.items():
            o=doc.getObject(name)
            o.Mesh.write(str(path))
            original=tr.load_mesh(path)
            after=tr.boolean.difference([original,*cutters],engine='manifold')
            lumps=after.split(only_watertight=True)
            primary=max(lumps,key=lambda m:m.volume)
            removed_ribs=after.volume-primary.volume
            if not primary.is_volume or removed_ribs>min(.00035*original.volume,40.):
                raise ValueError(f'{name} clearance cut detached a structural region')
            primary.export(path)
            o.Mesh=Mesh.Mesh(str(path))


def revise_head(doc, output):
    dy,dz=BLINK_SERVO[1]-43.,BLINK_SERVO[2]-88.
    horn=doc.Part047.Shape.copy().rotate(V(1.2,43,88),V(1,0,0),BLINK_PHASE).translate(V(0,dy,dz))
    parts={
        'Part045':doc.Part045.Shape.copy().translate(V(0,dy,dz)),
        'Part046':doc.Part046.Shape.copy().translate(V(0,dy,dz)),
        'Part047':horn,
        'Part053':blink_crank(-52.45,LID_ARM),
        'Part054':blink_crank(8.95,DRIVE_ARM),
        'Part055':blink_crank(52.45,LID_ARM),
        'Part056':blink_link(5.85,(BLINK_SERVO[1]+DRIVE_ARM[0],BLINK_SERVO[2]+DRIVE_ARM[1]),(BLINK_SHAFT_YZ[0]+DRIVE_ARM[0],BLINK_SHAFT_YZ[1]+DRIVE_ARM[1])),
        'Part057':blink_link(-49.25,(-39.+LID_ARM[0],119.+LID_ARM[1]),(BLINK_SHAFT_YZ[0]+LID_ARM[0],BLINK_SHAFT_YZ[1]+LID_ARM[1])),
        'Part060':blink_link(49.25,(-39.+LID_ARM[0],119.+LID_ARM[1]),(BLINK_SHAFT_YZ[0]+LID_ARM[0],BLINK_SHAFT_YZ[1]+LID_ARM[1])),
    }
    y,z=BLINK_SHAFT_YZ
    shaft=cylinder(2.,112,(-56,y,z),(1,0,0))
    for x in (-52.45,8.95,52.45):
        shaft=shaft.cut(box(x-1.8,x+1.8,y-3,y+3,z+1.55,z+3))
    parts['Part048']=shaft
    parts.update(gaze_yaw_parts(doc))
    for x in (-49.25,49.25):
        rib=box(x-5.5,x+5.5,-20.8,-14.8,120.5,125.2)
        parts['Part024']=parts['Part024'].fuse(rib).cut(box(x-2.87,x+2.87,-27.5,-17.30,114.,131.))
    cradle=parts['Part024'].cut(box(-44.4,-39.7,-22.8,-18.0,118.8,122.55))
    parts['Part024']=cradle.cut([cylinder(1.62,10.5,(x-.5,*HINGE_YZ),(1,0,0))
                               for x in HINGE_PINS.values()]).removeSplitter()
    for name,x in [('Part029',-34.),('Part033',34.)]:
        parts[name]=eyeball(x)
    for name,x in [('Part032',-34.),('Part036',34.)]:
        parts[name]=cylinder(1.,24.,(x,-39,107.))
    parts['Part043']=doc.Part043.Shape.common(box(58.5,61.2,-50,40,130,170))
    parts['Part044']=doc.Part044.Shape.copy().translate(V(-1.05,0,0)).common(box(61.55,64.15,-45,29,100,161))
    frame=ballast_mount(doc.Part019.Shape.cut(box(57.9,65.1,20.2,25.0,145.3,155.9)))
    frame=holes(frame,1.65,8.5,[(x,22.8,z) for x,z in BLINK_MOUNT_XZ],(0,1,0))
    parts['Part019']=holes(frame,3.15,4.,[(x,27.7,z) for x,z in BLINK_MOUNT_XZ],(0,1,0)).removeSplitter()
    tab=doc.Part021.Shape.cut([box(57.9,66.0,18.1,25.0,124.1,157.4),box(49.8,58.8,16.,20.8,126.,158.)])
    parts['Part021']=tab.fuse([
        box(54.9,57.7,21.8,23.7,153.3,160.5),
        box(66.2,71.7,17.9,23.0,153.3,160.5),
        box(55.6,69.7,21.8,23.10,157.05,160.5),
    ]).removeSplitter()
    parts['Part011']=doc.Part011.Shape.cut([box(-14,24,-22.5,-16.5,100.0,115.9),box(5.2,14.8,-20.0,-16.75,84.,96.),box(14.4,19.8,-20.0,-17.5,83.,91.5)])
    doc.Part048.Motion='blink_shaft_crank'
    for plate in ('Part039', 'Part046'):
        parts[plate] = parts[plate].cut(head_pockets(plate)).removeSplitter()
    for x,bracket,bearing in [(-32,'Part049','Part050'),(26,'Part051','Part052')]:
        parts[bracket]=blink_bearing_arm(x)
        parts[bearing]=cylinder(5.,4.,(x-2,y,z),(1,0,0)).cut(cylinder(2.,4.,(x-2,y,z),(1,0,0)))
    rail=box(-34,34,18.5,23,139,154.5).cut(box(29.5,35.,17.4,21.25,135.,157.))
    rail=rail.fuse(box(-34.,29.,5.,18.7,139.5,153.8))
    rail=rail.fuse([parts.pop('Part049'),parts.pop('Part051')])
    rail=rail.fuse([cylinder(3.4,1.9,(x,16.7,z),(0,1,0)) for x,z in BLINK_MOUNT_XZ])
    rail=holes(rail,2.10,4.25,[(x,18.8,z) for x,z in BLINK_MOUNT_XZ],(0,1,0))
    doc.removeObject('Part049')
    doc.removeObject('Part051')
    stay=yz_prism([(18,151),(23,151),(23,155),(6,192),(4,195),(-4.8,195),(-4.8,182),(1.5,181)],
           -6.4,4.6)
    stay=stay.cut([parts['Part046'],box(-7.,2.,-8.,-3.1,158.,202.)])
    stay=stay.cut(box(-7.,2.,-3.2,4.7,158.,180.))
    brace=yz_prism([(1.5,147.),(22.98,145.),(22.98,156.),(14.,174.),(4.2,194.5),
                    (-2.9,194.5),(-2.9,180.8),(-2.7,156.)],-12.4,8.4)
    stay=stay.fuse(brace)
    stay=holes(stay,1.65,12.,[(-13.3,57.+dy,a+dz) for a in (101.,107.)],(1,0,0))
    parts['Part063']=rail.fuse(stay).removeSplitter()
    for name,shape in parts.items():
        check=shape.isValid() and (not doc.getObject(name).Printed or len(shape.Solids)==1)
        if not check:
            raise ValueError(f'{name} must contain one valid printed solid')
        doc.getObject(name).Shape=shape
    for side,name in [(-1,'Part078'),(1,'Part079')]:
        brace=eyelid(side)
        assert brace.isValid() and len(brace.Solids)==1, name
        doc.getObject(name).Mesh=MeshPart.meshFromShape(Shape=brace,LinearDeflection=.075,AngularDeflection=.1,Relative=False)
    for side,x in [(-1,-32.),(1,26.)]:
        start=x-2*side
        direction=(-side,0,0)
        norm=V(*direction)
        shim=cylinder(2.8,.5,(start,y,z),direction)
        collar=cylinder(4.,4.5,tuple(V(start,y,z)+.5*norm),direction)
        solid=shim.fuse(collar).cut(cylinder(2.03,5.2,(start,y,z),direction)).removeSplitter()
        name='BlinkCollarLeft' if side<0 else 'BlinkCollarRight'
        obj=doc.addObject('Part::Feature',name)
        obj.Shape=solid
        obj.Label='4 mm shaft collar and inner-race shim'
        obj.addProperty('App::PropertyString','Motion','Design')
        obj.Motion='blink_shaft_crank'
        doc.Synchronised_eyelids.addObject(obj)
    for index,x in HINGE_PINS.items():
        pin = doc.getObject(f'Part{index:03}')
        pin.Shape = cylinder(1., 9.5, (x,*HINGE_YZ), (1,0,0))
    cut_running_clearance(doc)
    doc.JawMotion.setExpression('Placement','create(<<placement>>;vector(0mm;-9mm;92mm);create(<<rotation>>;vector(1;0;0);1.25deg+max(0deg;min(13deg;Opening))))')
    doc.JawMotion.Label = 'Jaw — Opening 0 to 13 degrees above the closed position'
    doc.R5.addProperty('App::PropertyString', 'MotionGeometry', 'Design')
    doc.R5.MotionGeometry = json.dumps({
        'eye_yaw': {'pivot_mm': [-5.8, -35.5, 111.85], 'radius_mm': 13.5},
        'blink': {'servo_yz_mm': list(BLINK_SERVO[1:]), 'shaft_yz_mm': list(BLINK_SHAFT_YZ),
                  'phase_deg': BLINK_PHASE, 'radius_mm': DRIVE_THROW, 'lid_radius_mm': LID_THROW,
                  'link_x_mm': 49.25, 'crank_x_mm': [-52.45,8.95,52.45], 'bearing_x_mm': [-32.,26.],
                  'mount_xz_mm': BLINK_MOUNT_XZ},
        'jaw_travel_deg': 13., **fixture_parameters(),
    }, separators=(',', ':'))
    labels = {
        'Part024': '12 eye tilt cradle',
        'Part037': '15 eye yaw offset tie bar',
        'Part039': 'XL330 eye yaw front plate',
        'Part040': '16 eye yaw horn 13p5 mm',
        'Part048': '4 mm blink shaft 112 mm with three flats',
        'Part056': '22 blink drive link',
        'Part057': '23 left short lid link',
        'Part060': '23 right short lid link',
        'Part063': '24 blink rail with bearing shoulders',
    }
    print_axes = {
        'Part019': 'y+', 'Part024': 'y+', 'Part039': None, 'Part042': 'x+',
        'Part043': 'x+', 'Part044': 'x+', 'Part046': 'x+', 'Part047': 'x+',
        'Part053': 'x+', 'Part054': 'x+', 'Part055': 'x+', 'Part056': 'x+',
        'Part057': 'x+', 'Part060': 'x+', 'Part063': 'y+',
        'Part011': 'y+', 'Part021': None, 'Part040': None,
        'Part016': 'x+', 'Part020': None, 'Part025': 'x+', 'Part027': 'x+',
        'Part029': 'y+', 'Part033': 'y+', 'Part037': None, 'Part064': 'x+', 'Part066': None,
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, label in labels.items():
        doc.getObject(name).Label = label
    for name, rotation in print_axes.items():
        obj = doc.getObject(name)
        if obj.Printed:
            stem = obj.Label.lower().replace(' ', '_')
            print_mesh(obj.Shape, output/f'{stem}.stl', rotation)
    mesh_exports = {
        'Part065': (None, (0., 0., 0.)),
        'Part073': (None, (-.5*pi, 0., 0.)),
        'Part074': (None, (-.5*pi, 0., 0.)),
        'Part076': (None, (.5*pi, 0., 0.)),
        'Part077': (None, (.5*pi, 0., 0.)),
        'Part078': (None, (0., 0., 0.)),
        'Part079': (None, (0., 0., 0.)),
        'Part080': (None, (-.5*pi, 0., 0.)),
        'Jaw_30_moving_jaw': ('30_moving_jaw', (0., 0., 0.)),
        'Jaw_36_left_jaw_servo_stay': (None, (0., -.5*pi, 0.)),
        'Jaw_37_right_jaw_bearing_stay': (None, (0., -.5*pi, 0.)),
        'Jaw_38_left_jaw_drive_arm': ('38_left_jaw_drive_arm', (0., -.5*pi, 0.)),
        'Jaw_39_right_jaw_pivot_arm': ('39_right_jaw_pivot_arm', (0., -.5*pi, 0.)),
    }
    for name, (stem, rotation) in mesh_exports.items():
        obj = doc.getObject(name)
        mesh = obj.Mesh.copy()
        mesh.rotate(*rotation)
        frame = mesh.BoundBox
        mesh.translate(-frame.Center.x, -frame.Center.y, -frame.ZMin)
        stem = stem or obj.Label.lower().replace(' ', '_')
        mesh.write(str(output/f'{stem}.stl'))


def add_fixture(doc, group, name, label, shape, motion, printed):
    if not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError(f'{label} is not one solid')
    obj = doc.getObject(name) or doc.addObject('Part::Feature', name)
    obj.Label = label
    obj.Shape = shape
    for key, kind, value in [('Motion', 'String', motion), ('Printed', 'Bool', printed)]:
        if key not in obj.PropertiesList:
            obj.addProperty(f'App::Property{kind}', key, 'Design')
        setattr(obj, key, value)
    group.addObject(obj)
    return obj


def main(output=BUILD):
    doc = App.openDocument(str(SOURCE))
    repairs, pitch_pin, yaw_case = fix_motors(doc)
    doc.Part015.Shape = pitch_pin
    doc.Part038.Shape = yaw_case
    doc.Part015.Label = 'Right pitch pin · Ø8 × 27.3 with 1 mm D-flat'
    base, saddle, gate = captive_cables(doc.Part000.Shape)
    base = base.cut(box(-14.1, -.7, 82., 88.1, -83.2, -69.0)).removeSplitter()
    base, board_trays = board_mounts(doc, base)
    repairs.update(board_trays)
    bearing_seat, bearing_top, bearer = yaw_bearing_retention(doc)
    repairs['Part001'] = ('02_outer_bearing_seat', bearing_seat, None)
    repairs['Part002'] = ('03_base_top', bearing_top, 'z-')
    repairs['Part000'] = ('01_base_cup_B5', base, None)
    repairs['CableSaddle'] = ('40_captive_cable_tray', saddle, None)
    apply_repairs(doc, repairs, output/'STL')
    print_mesh(bearer, output/'STL'/'41_outer_race_keeper.stl', 'z-')
    base_group = doc.Base_and_neck
    add_fixture(doc, base_group, 'CableSaddle', '40 captive cable tray', saddle, 'fixed', True)
    add_fixture(doc, base_group, 'CableGate', '42 interlocking cable cover', gate, 'fixed', True)
    print_mesh(gate, output/'STL'/'42_captive_cable_cover.stl', 'z-')
    print_mesh(cable_wall_fixture(base), output/'STL'/'Cable_lock_wall_fixture.stl')
    doc.Part000.Label = '01 Base cup B8 · reinforced hatch and top-loaded nuts'
    revise_head(doc, output/'STL')
    tray, cover, stack = rear_ballast()
    for name, label, shape in (
        ('BallastTray', '43 neck ballast tray', tray),
        ('BallastCover', '44 ballast cover', cover),
        ('BallastStack', 'Steel plate capacity · 12 plates', stack),
        ('BallastLeftStud', 'Ballast M3 threaded stud left', ballast_stud(-24.2)),
        ('BallastRightStud', 'Ballast M3 threaded stud right', ballast_stud(24.2)),
    ):
        printed = name in ('BallastTray', 'BallastCover')
        add_fixture(doc, doc.Head_frame, name, label, shape, 'head', printed)
        if printed:
            print_mesh(shape, output/'STL'/f'{label.replace(" ", "_")}.stl', 'y+' if name == 'BallastTray' else None)
    rig = json.loads(doc.R5.MotionGeometry)
    blink_stock(doc, output/'STL', rig['blink'])
    cable_stock(doc, output/'STL', rig['cables'])
    hatch_stock(doc, output/'STL')
    ballast_stock(doc, output/'STL')
    radio_board_stock(doc, output/'STL')
    neck_stock(doc, output/'STL')
    print_mesh(cable_wall_fixture(doc.Part000.Shape), output/'STL'/'Cable_lock_wall_fixture.stl')
    doc.R5.Label = 'R5 B9 · prototype'
    doc.R5.Status = 'Cylindrical hex-socket heads only. DYNAMIXEL case thread fit pending.'
    doc.recompute()
    doc.saveAs(str(output/'R5-B9-Assembly.FCStd'))
    App.closeDocument(doc.Name)


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BUILD)
