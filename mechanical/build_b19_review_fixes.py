"""Build B19: define every fastener the head needs and repair the joints that could not be assembled.

* Both Ø8 pitch pins get a Ø3 cross hole under the existing Ø3.1 vertical holes of
  the 09 head frame. A Ø3 × 12 steel dowel, set with retaining compound, keys each
  pin to the frame, so pitch torque reaches the head and the pins cannot walk out
  axially. A through bolt does not fit: the 28 skull front sits about 1 mm under the
  frame hubs, where a nut or screw head would have to go.
* The three flats of the Ø4 blink shaft are 0.30 mm deep instead of 0.45 mm, so the
  M3 × 8 crank screws meet the flat with 0.36 mm of head clearance instead of 0.21 mm.
* The five eye linkage joints get pins or a screw. Below the eyeball cranks the
  cradle is 1.1 mm away and beside the pitch link the eye pitch plate and the cradle
  mount are 0.3 and 0.65 mm away, so no nut fits there; pins are trapped by those
  same faces instead.
* The eye yaw plate feet were to be screwed into the cradle from below, where the
  eye yaw motor fills the space under the feet. The cradle now takes a counterbored
  M3 × 16 from above into a Ø2.6 tap hole in each plate foot.
* The B17 ID5 plug keeper covered two of the four pitch-motor mounting holes. The
  keeper gets two through holes and an M2.5 × 10 passes through it into the motor; a
  head-clearance hole instead would cut through the keeper rail.
* The eye pitch stay was to be bolted to the frame with the nut on the motor side,
  where the motor case sits 0.8 mm from the frame. The frame hole becomes a Ø2.6 tap
  hole for an M3 × 8.
* Motor case, horn and bracket screws that the earlier revisions only showed as heads
  get lengths from the measured hole depths.
"""
from argparse import ArgumentParser
import json
from math import radians
from pathlib import Path
import sys

import FreeCAD as App
import Part

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'physics'))
from primitives import box, cylinder, print_mesh
from stock import BLINK_CLAMPS, BLINK_CLAMP_LENGTH, hexagon
from export_cad import world_shape

V = App.Vector
X, Z = (1, 0, 0), (0, 0, 1)
PITCH_AXIS = (V(0, 0, 112), V(1, 0, 0))
PITCH_RANGE_DEG = (-15, 6)
PIN_RADIUS = 4.
CROSS_HOLE_RADIUS = 1.5
FRAME_HOLE_RADIUS = 1.55
DOWEL_RADIUS = 1.5
DOWEL_LENGTH = 12.
BLINK_SHAFT_YZ = (-24., 154.)
BLINK_FLAT_DEPTH = .30
NOMINAL_FLAT_DEPTH = .45
B15_HEAD_CLEARANCE = .21
M3_TAP_RADIUS = 1.3
EYE_YAW_FEET = ((-8., -47.6), (8., -47.6))
EYE_YAW_FOOT_Z = (108.85, 111.55)
CRADLE_FOOT_TOP = 125.
CRADLE_COUNTERBORE = (3.1, 121.5)
TIE_PIN_X = (-34., 34.)
TIE_PIN_Y = -25.5
TIE_PIN_HOLE_RADIUS = 1.1
KEEPER_MOTOR_HOLES = ((11., 84.), (11., 108.))
STAY_FRAME_HOLES = ((53., 142.), (53., 151.))
STAY_FRAME_SPAN_Y = (20.8, 31.)
HEAD = {2: (1.93, 2.), 2.5: (2.25, 2.5), 3: (2.78, 3.)}
NUT = {2: (4., 1.6), 2.5: (5., 2.), 3: (5.5, 2.4)}

# (name, size, length, seat, axis from head into the stack, host parts, motion, note)
SCREWS = [
    # Only the upper side holes: a screw head bound for a lower hole has to pass over the
    # bracket's own foot pad and hits it 0.75 mm deep.
    *[(f'XL430YawSide{"LR"[s>0]}{i}', 2.5, 8., (s*18.55, y, -50.9), (-s, 0, 0), ('Part008' if s < 0 else 'Part009', 'Part017'),
       'fixed', 'XL430 ID4 to 05 bracket; case hole Ø2.1 × 4.0 deep under a 4.25 mm wall')
      for s in (-1, 1) for i, y in enumerate((4., 28.))],
    *[(f'YawBracketFoot{i}', 3, 8., (x, y, -64.4), (0, 0, -1), ('Part008' if x < 0 else 'Part009', 'Part000'),
       'fixed', '05 bracket foot into the Ø2.7 tap hole of the 01 base cup')
      for i, (x, y) in enumerate((x, y) for x in (-22.8, 22.8) for y in (5., 26.))],
    ('XL430PitchSide0', 2.5, 8., (23., 18.65, 84.), (0, -1, 0), ('Part011', 'Part018'), 'pan', 'XL430 ID5 to 07 yoke'),
    ('XL430PitchSide1', 2.5, 8., (23., 18.65, 108.), (0, -1, 0), ('Part011', 'Part018'), 'pan', 'XL430 ID5 to 07 yoke'),
    *[(f'XL430PitchKeeper{i}', 2.5, 10., (x, 22.25, z), (0, -1, 0), ('ID5EHKeeper', 'Part011', 'Part018'), 'pan',
       'XL430 ID5 to 07 yoke through the ID5 keeper')
      for i, (x, z) in enumerate(KEEPER_MOTOR_HOLES)],
    *[(f'EyeYawFoot{i}', 3, 16., (x, y, CRADLE_COUNTERBORE[1]), (0, 0, -1), ('Part024', 'Part039'), 'tilt',
       '12 cradle into the tapped foot of the eye yaw plate')
      for i, (x, y) in enumerate(EYE_YAW_FEET)],
    *[(f'EyePitchStayFrame{i}', 3, 8., (x, 34.6, z), (0, -1, 0), ('Part064', 'Part019'), 'head',
       '34 stay into the tapped 09 frame')
      for i, (x, z) in enumerate(STAY_FRAME_HOLES)],
    *[(f'CradleMountFrame{"LR"[s>0]}', 3, 16., (s*69.2, 27., 146.), (-s, 0, 0), ('Part025' if s < 0 else 'Part027', 'Part019'),
       'head', '13 cradle mount into the 2.5 mm channel of the 09 frame')
      for s in (-1, 1)],
    # Head under the horn: from above the 12 cradle leaves 3 mm, too little to drive an 8 mm screw.
    ('EyeYawTieHorn', 2, 8., (-5.8, -22., 111.8), (0, 0, 1), ('Part037', 'Part040'), 'look_link',
     'tie bar to eye yaw horn joint, nut and washer on the tie bar'),
    # Printed horns on XL330 horns. Holes whose screw head would hit a moving part are left empty.
    *[(f'EyeYawHornScrew{i}', 2, 5., (x, y, 114.25), (0, 0, -1), ('Part040', 'Part038'), 'look_horn',
       '16 eye yaw horn to the XL330 horn')
      for i, (x, y) in enumerate(((-5.8, -41.5), (-5.8, -29.5), (.2, -35.5)))],
    *[(f'EyePitchHornScrew{i}', 2, 5., (61.2, y, z), (-1, 0, 0), ('Part043', 'Part041'), 'tilt_horn',
       '17 eye pitch horn to the XL330 horn')
      for i, (y, z) in enumerate(((4., 151.), (10., 157.)))],
    *[(f'BlinkHornScrew{i}', 2, 6., (4.3, y, z), (-1, 0, 0), ('Part047', 'Part045'), 'blink_motor_horn',
       '19 blink horn to the XL330 horn')
      for i, (y, z) in enumerate(((-17.4, 175.), (-9., 173.4)))],
    *[(f'JawHornScrew{i}', 2, 6., (-46.9, y, z), (1, 0, 0),
       ('Jaw_38_left_jaw_drive_arm', 'Jaw_XL330_M288_Jaw', 'Jaw_30_moving_jaw'), 'jaw',
       '38 jaw drive arm to the XL330 horn')
      for i, (y, z) in enumerate(((-15., 92.), (-9., 98.)))],
]
# Horn holes left empty because an ISO 4762 head there would strike a moving part.
EMPTY_HORN_HOLES = {
    '16 eye yaw horn (-11.8, -35.5)': '31 left orbit at eye pitch -8°',
    '17 eye pitch horn (10, 145) and (16, 151)': '18 eye pitch link',
    '19 blink horn (-19.0, 166.6) and (-10.6, 165.0)': '21 centre crank and 22 drive link',
    '38 jaw drive arm (-9, 86)': '07 pitch yoke at neck +6° with the jaw open',
    '38 jaw drive arm (-3, 92)': '07 pitch yoke while the jaw is lifted into the head',
}
# (name, radius, length, start, axis, host parts, motion, note)
PINS = [
    # 6 mm, not longer: the tie bar has to clear the pin tips under the cradle bridge to drop on.
    ('EyeYawTiePinL', 1., 6., (-34., -25.5, 111.8), (0, 0, 1), ('Part029', 'Part037'), 'look_link', 'glued in the left eyeball crank'),
    ('EyeYawTiePinR', 1., 6., (34., -25.5, 111.8), (0, 0, 1), ('Part033', 'Part037'), 'look_link', 'glued in the right eyeball crank'),
    ('EyePitchLinkHornPin', 1., 6., (58.65, 20., 151.), (1, 0, 0), ('Part043', 'Part044'), 'tilt_link', 'glued in the 17 horn'),
    ('EyePitchLinkCradlePin', 1., 6., (58., -29., 119.), (1, 0, 0), ('Part024', 'Part044'), 'tilt', 'glued in the 12 cradle lug'),
]
# Screws that only need a length because the earlier revisions already model their heads.
HEAD_ONLY = {
    'XL330 case, through 39·42·46 plates and the 36 jaw stay': ('M2 × 6', 16),
    '42 eye pitch plate into the 34 stay (Ø2.7 tap)': ('M3 × 8', 2),
}


def frame_holes(frame):
    """Return (x, bottom z, top z) of the vertical Ø3.1 holes across the pin bores."""
    holes = {}
    for face in frame.Faces:
        surface = face.Surface
        if (surface.__class__.__name__ == 'Cylinder' and abs(surface.Radius-FRAME_HOLE_RADIUS) < .01
                and abs(abs(surface.Axis.z)-1) < 1e-6 and abs(surface.Center.y) < 1e-6
                and 50 < abs(surface.Center.x) < 70):
            x = round(surface.Center.x, 3)
            lo, hi = holes.get(x, (1e9, -1e9))
            holes[x] = (min(lo, face.BoundBox.ZMin), max(hi, face.BoundBox.ZMax))
    if sorted(holes) != [-60.5, 60.5]:
        raise ValueError(f'Expected frame holes at x = ±60.5 mm, found {sorted(holes)}')
    return [(x, lo, hi) for x, (lo, hi) in sorted(holes.items())]


def blink_shaft():
    y, z = BLINK_SHAFT_YZ
    shaft = cylinder(2., 112., (-56., y, z), X)
    for x, _, _, _ in BLINK_CLAMPS:
        shaft = shaft.cut(box(x-1.8, x+1.8, y-3, y+3, z+2.-BLINK_FLAT_DEPTH, z+3))
    return shaft


def replace(obj, shape):
    parent = obj.getParentGeoFeatureGroup()
    if parent:
        shape.Placement = parent.getGlobalPlacement().inverse().multiply(shape.Placement)
    obj.Shape = shape


def add_part(doc, group, name, label, shape, motion):
    part = group.newObject('Part::Feature', name)
    part.Label = label
    part.Shape = shape
    part.addProperty('App::PropertyString', 'Motion', 'Wiring')
    part.Motion = motion
    if part.ViewObject:
        part.ViewObject.ShapeColor = (.93, .68, .39)
    return part


def apply(doc):
    frame = world_shape(doc.Part019)
    holes = frame_holes(frame)
    pins = {'Part013': world_shape(doc.Part013), 'Part015': world_shape(doc.Part015)}
    hardware = []
    for x, bottom, top in holes:
        name = 'Part015' if x > 0 else 'Part013'
        pin = pins[name]
        hole = cylinder(CROSS_HOLE_RADIUS, 2*PIN_RADIUS+2, (x, 0, 112-PIN_RADIUS-1), Z)
        if not pin.BoundBox.isInside(V(x, 0, 112)):
            raise ValueError(f'{name} does not reach the frame hole at x = {x}')
        pins[name] = pin.cut(hole)
        outer_end = pin.BoundBox.XMax if x > 0 else pin.BoundBox.XMin
        hub = top - bottom
        if DOWEL_LENGTH > hub:
            raise ValueError(f'Ø3 × {DOWEL_LENGTH:g} dowel is longer than the {hub:.2f} mm frame hub')
        recess = (hub - DOWEL_LENGTH) / 2
        dowel = cylinder(DOWEL_RADIUS, DOWEL_LENGTH, (x, 0, bottom+recess), Z)
        hardware.append({'x_mm': x, 'pin': name, 'from_outer_end_mm': round(abs(outer_end-x), 3),
                         'frame_hub_mm': round(hub, 3), 'dowel_recess_each_end_mm': round(recess, 3),
                         'dowel': dowel})
    for name, shape in pins.items():
        if not shape.isValid() or len(shape.Solids) != 1:
            raise ValueError(f'{name} became invalid')
        replace(doc.getObject(name), shape)
    doc.Part015.Label = 'Right pitch pin · Ø8 × 27.3, 1 mm D-flat, Ø3.0 cross hole'
    doc.Part013.Label = 'Left pitch pin · Ø8 × 21.5, Ø3.0 cross hole'
    shaft = blink_shaft()
    replace(doc.Part048, shaft)
    doc.Part048.Label = f'4 mm blink shaft 112 mm with three {BLINK_FLAT_DEPTH:.2f} mm flats'
    printed = repair_printed_parts(doc)
    group = doc.Part019.getParentGeoFeatureGroup()
    add_fasteners(doc, group)
    for item in hardware:
        side = 'Right' if item['x_mm'] > 0 else 'Left'
        add_part(doc, group, f'PitchPinDowel{side}', f'{side} pitch pin Ø3 × 12 dowel', item['dowel'], 'head')
    return hardware, printed


def repair_printed_parts(doc):
    """Return {object name: (slug, print direction)} for the printed parts that change."""
    cradle = world_shape(doc.Part024)
    for x, y in EYE_YAW_FEET:
        cradle = cradle.cut([cylinder(1.7, CRADLE_FOOT_TOP-EYE_YAW_FOOT_Z[1]+.4, (x, y, EYE_YAW_FOOT_Z[1]-.2)),
                             cylinder(CRADLE_COUNTERBORE[0], CRADLE_FOOT_TOP-CRADLE_COUNTERBORE[1]+.2,
                                      (x, y, CRADLE_COUNTERBORE[1]))])
    # The 15 tie bar cannot reach its pins: they stand 3.25 mm proud of the bar and the cradle
    # bridges leave 3.55 mm above it, but the bar can only come in sideways at seat height. Let it
    # slide in without pins and push each Ø2×6 pin down afterwards through a hole in the bridge.
    cradle = cradle.cut([cylinder(TIE_PIN_HOLE_RADIUS, 4., (x, TIE_PIN_Y, 120.)) for x in TIE_PIN_X])
    plate = world_shape(doc.Part039)
    feet = [cylinder(1.6, EYE_YAW_FOOT_Z[1]-EYE_YAW_FOOT_Z[0], (x, y, EYE_YAW_FOOT_Z[0])) for x, y in EYE_YAW_FEET]
    plate = plate.fuse([f.common(box(x-3., x+3., y-2.7, y+2.7, *EYE_YAW_FOOT_Z)) for f, (x, y) in zip(feet, EYE_YAW_FEET)])
    plate = plate.cut([cylinder(M3_TAP_RADIUS, 4., (x, y, EYE_YAW_FOOT_Z[0]-.5)) for x, y in EYE_YAW_FEET])
    keeper = world_shape(doc.ID5EHKeeper).cut(
        [cylinder(1.5, 4., (x, 19., z), (0, 1, 0)) for x, z in KEEPER_MOTOR_HOLES])
    frame = world_shape(doc.Part019)
    lo, hi = STAY_FRAME_SPAN_Y
    span = box(-100, 100, lo, hi, -1000, 1000)
    frame = frame.fuse([cylinder(1.78, hi-lo, (x, lo, z), (0, 1, 0)).common(span) for x, z in STAY_FRAME_HOLES])
    frame = frame.cut([cylinder(M3_TAP_RADIUS, hi-lo+.4, (x, lo-.2, z), (0, 1, 0)) for x, z in STAY_FRAME_HOLES])
    # The 19 horn's screw boss reaches 2 mm into the 22 drive link and the 21-2 crank's clamp
    # pad 0.8 mm into the same link (44 and 2.2 mm³ of solid overlap in B15-B18; the pairs were
    # listed as mates, so the motion sweeps skipped them). Trim both back to the link faces.
    horn = world_shape(doc.Part047)
    link = world_shape(doc.Part056)
    face = link.BoundBox.XMin - .1
    horn = horn.cut(box(face, horn.BoundBox.XMax+1, -40, 10, 140, 200))
    crank = world_shape(doc.Part054)
    crank = crank.cut(box(crank.BoundBox.XMin-1, 7.25, -21., -15.5, 150., 160.))
    # The 21-2 crank's clamp boss overhangs its hub by 1.05 mm (left) and 0.8 mm (right) above the
    # shaft, so both 45 spacers sat 0.6-0.8 mm³ inside it.
    # Both spacers' bearing ends also sit 1 mm inside the rail's bearing shoulders, which leaves no
    # way to drop them in once the crank and link are in place. Stop them 0.1 mm short of the boss
    # and 1.2 mm short of the bearings; the M3 clamp on the shaft flat holds the crank axially.
    left = world_shape(doc.BlinkCollarLeft).common(box(-28.8, 6.25, -40, -10, 140, 170))
    right = world_shape(doc.BlinkCollarRight).common(box(14.15, 22.8, -40, -10, 140, 170))
    # The U20CAM board's bottom edge sits 1.8 mm inside the bracket's front ledge (114 mm³; both
    # parts move with the head, so the motion checks skipped the pair). Cut the slot the board
    # stands in so it seats where the lens opening was aligned.
    camera = world_shape(doc.Part066).cut(box(-16.2, 16.2, -53.5, -51.2, 72.9, 75.))
    changed = {'Part024': (cradle, '12_eye_tilt_cradle-B19', 'y+'),
               'Part066': (camera, '26_u20cam_slotted_bracket-B19', None),
               'BlinkCollarLeft': (left, '45_blink_shaft_spacer_left-B19', 'x+'),
               'BlinkCollarRight': (right, '45_blink_shaft_spacer_right-B19', 'x+'),
               'Part047': (horn, '19_blink_servo_horn-B19', 'x+'),
               'Part054': (crank, '21_blink_shaft_crank_2-B19', 'x+'),
               'Part039': (plate, 'xl330_eye_yaw_front_plate-B19', None),
               'ID5EHKeeper': (keeper, 'ID5-keeper-B19', None),
               'Part019': (frame, '09_head_frame-B19', 'y+')}
    for name, (shape, _, _) in changed.items():
        shape = shape.removeSplitter()
        if not shape.isValid() or len(shape.Solids) != 1:
            raise ValueError(f'{name} became invalid')
        replace(doc.getObject(name), shape)
    return {name: (slug, direction) for name, (_, slug, direction) in changed.items()}


def screw_shape(size, length, seat, axis):
    seat, axis = V(*seat), V(*axis)
    radius, height = HEAD[size]
    head = Part.makeCylinder(radius, height, seat - axis*height, axis)
    return head.fuse(Part.makeCylinder(size/2., length, seat, axis))


def add_fasteners(doc, group):
    for name, size, length, seat, axis, _, motion, note in SCREWS:
        add_part(doc, group, name, f'M{size:g} × {length:g} · {note}', screw_shape(size, length, seat, axis), motion)
        if name == 'EyeYawTieHorn':
            width, height = NUT[size]
            start = (seat[0], seat[1], 117.45+.35)
            add_part(doc, group, 'EyeYawTieHornNut', 'M2 plain nut on the tie bar',
                     hexagon(width, height, start, Z).cut(cylinder(1., height, start)), motion)
            add_part(doc, group, 'EyeYawTieHornWasher', 'M2 washer under the nut',
                     cylinder(2.5, .3, (seat[0], seat[1], 117.45+.02)).cut(cylinder(1.1, .3, (seat[0], seat[1], 117.47))), motion)
    for name, radius, length, start, axis, _, motion, note in PINS:
        add_part(doc, group, name, f'Ø{2*radius:g} × {length:g} pin · {note}', cylinder(radius, length, start, axis), motion)


def hardware_spec():
    """Shapes for the motion sweep in physics/check_b19_hardware.py."""
    spec = []
    for name, size, length, seat, axis, hosts, motion, _ in SCREWS:
        radius, height = HEAD[size]
        head_start = [s - a*(height+.05) for s, a in zip(seat, axis)]
        shank_start = [s + a*.05 for s, a in zip(seat, axis)]
        shapes = [['cyl', radius, height, head_start, list(axis)], ['cyl', size/2.*.9, length-.1, shank_start, list(axis)]]
        if name == 'EyeYawTieHorn':
            shapes.append(['hex', NUT[2][0], NUT[2][1], [seat[0], seat[1], 117.8], [0, 0, 1]])
        spec.append({'name': name, 'motion': motion, 'skip': list(hosts), 'shapes': shapes})
    for name, radius, length, start, axis, hosts, motion, _ in PINS:
        spec.append({'name': name, 'motion': motion, 'skip': list(hosts),
                     'shapes': [['cyl', radius, length, list(start), list(axis)]]})
    return spec


def check(doc, hardware):
    """Static overlap with every other solid, gap to the meshes, and pitch sweep against the yaw carrier."""
    import numpy as np
    import trimesh

    ignore = {'Part013', 'Part015', 'Part019'}
    new = {f"PitchPinDowel{'Right' if h['x_mm'] > 0 else 'Left'}": h['dowel'] for h in hardware}
    hosts = {name: set(item[5]) for item in SCREWS + PINS for name in (item[0],)}
    hosts['EyeYawTieHornNut'] = hosts['EyeYawTieHornWasher'] = hosts['EyeYawTieHorn']
    for name in hosts:
        new[name] = world_shape(doc.getObject(name))
    solids, meshes = [], []
    for obj in doc.Objects:
        if obj.Name in new:
            continue
        if obj.TypeId == 'Part::Feature' and obj.Shape.Solids:
            solids.append((obj, world_shape(obj)))
        elif obj.TypeId == 'Mesh::Feature':
            meshes.append(obj)
    report = {'static_overlap_mm3': {}, 'mesh_min_gap_mm': {}, 'sweep_overlap_mm3': {}, 'sweep_min_gap_mm': None}
    for name, shape in new.items():
        skip = hosts.get(name, ignore) | ({'EyeYawTieHornNut', 'EyeYawTieHornWasher', 'EyeYawTieHorn'} if name.startswith('EyeYawTieHorn') else set())
        for obj, other in solids:
            if obj.Name in skip:
                continue
            if other.BoundBox.intersect(shape.BoundBox):
                volume = shape.common(other).Volume
                if volume > 1e-3:
                    report['static_overlap_mm3'][f'{name} / {obj.Label}'] = round(volume, 4)
        samples = np.array([tuple(v) for v in shape.tessellate(.1)[0]])
        reach = shape.BoundBox
        reach.enlarge(3)
        for obj in meshes:
            if obj.Name in skip:
                continue
            mesh = obj.Mesh.copy()
            mesh.Placement = obj.getGlobalPlacement()
            if not mesh.BoundBox.intersect(reach):
                continue
            points, facets = mesh.Topology
            near = trimesh.Trimesh(np.array([tuple(p) for p in points]), np.array(facets), process=False)
            keep = np.all((near.triangles_center > np.array([reach.XMin, reach.YMin, reach.ZMin])) &
                          (near.triangles_center < np.array([reach.XMax, reach.YMax, reach.ZMax])), axis=1)
            if not keep.any():
                continue
            near = near.submesh([np.flatnonzero(keep)], append=True)
            inside = [shape.isInside(V(*p), 1e-4, True) for p in near.vertices]
            distance = trimesh.proximity.closest_point(near, samples)[1].min()
            report['mesh_min_gap_mm'][f'{name} / {obj.Label}'] = round(-1. if any(inside) else float(distance), 3)
    carrier = [(obj, shape) for obj, shape in solids if getattr(obj, 'Motion', '') in ('pan', 'fixed')
               and obj.Name not in ignore]
    nearest = 1e9
    for angle in range(PITCH_RANGE_DEG[0], PITCH_RANGE_DEG[1]+1):
        for name, shape in new.items():
            if not name.startswith('PitchPinDowel'):
                continue
            moved = shape.copy()
            moved.rotate(*PITCH_AXIS, angle)
            for obj, other in carrier:
                probe = moved.BoundBox
                probe.enlarge(5)
                if not other.BoundBox.intersect(probe):
                    continue
                volume = moved.common(other).Volume
                if volume > 1e-3:
                    report['sweep_overlap_mm3'][f'{name} / {obj.Label} @ {angle}°'] = round(volume, 4)
                nearest = min(nearest, moved.distToShape(other)[0])
    report['sweep_min_gap_mm'] = round(nearest, 3)
    return report


def jaw_one_piece(doc, path):
    """30 jaw, 38 drive arm and 39 pin arm fused into one print in the jaw's own frame.

    The jaw's arm pockets are closed on every side, so separately printed arms cannot be fitted.
    """
    import numpy as np
    import trimesh
    jaw = doc.getObject('Jaw_30_moving_jaw')
    meshes = []
    for name in ('Jaw_30_moving_jaw', 'Jaw_38_left_jaw_drive_arm', 'Jaw_39_right_jaw_pivot_arm'):
        mesh = doc.getObject(name).Mesh.copy()
        mesh.Placement = doc.getObject(name).getGlobalPlacement()
        points, facets = mesh.Topology
        part = trimesh.Trimesh(np.array([tuple(p) for p in points]), np.array(facets))
        meshes.append(part)
    fused = trimesh.boolean.union(meshes, engine='manifold')
    local = jaw.getGlobalPlacement().inverse().toMatrix()
    fused.apply_transform(np.array(local.A).reshape(4, 4))
    fused.apply_translation(-np.array([*fused.bounds.mean(axis=0)[:2], fused.bounds[0][2]]))
    if not fused.is_volume or fused.body_count != 1:
        raise ValueError('jaw one-piece print is not a single closed body')
    write_3mf(fused.vertices, fused.faces, path)


def write_3mf(vertices, faces, path):
    """Minimal 3MF. Unlike STL it keeps vertex indices, so the seams where the arms only touch
    their pockets stay closed instead of being welded into non-manifold edges on import."""
    import zipfile
    v = ''.join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in vertices)
    t = ''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
    model = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             f'<resources><object id="1" type="model"><mesh><vertices>{v}</vertices><triangles>{t}</triangles>'
             '</mesh></object></resources><build><item objectid="1"/></build></model>')
    types = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', types)
        archive.writestr('_rels/.rels', rels)
        archive.writestr('3D/3dmodel.model', model)


def make(source, output, report, stl=None):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate CAD output')
    doc = App.openDocument(str(source.resolve()))
    try:
        hardware, printed = apply(doc)
        doc.Label = 'R5 B19 · pitch pin dowels and blink clamp travel'
        doc.recompute()
        result = check(doc, hardware)
        result['pitch_pins'] = [{k: v for k, v in h.items() if k != 'dowel'} for h in hardware]
        result['blink_flat_depth_mm'] = BLINK_FLAT_DEPTH
        result['blink_screw_head_clearance_mm'] = round(B15_HEAD_CLEARANCE + NOMINAL_FLAT_DEPTH - BLINK_FLAT_DEPTH, 3)
        result['blink_screw_length_mm'] = BLINK_CLAMP_LENGTH
        result['fasteners'] = {name: f'M{size:g} × {length:g}' for name, size, length, *_ in SCREWS}
        result['pins'] = {name: f'Ø{2*r:g} × {length:g}' for name, r, length, *_ in PINS}
        result['head_only_screws'] = {k: f'{v[0]} × {v[1]}' for k, v in HEAD_ONLY.items()}
        result['empty_horn_holes'] = EMPTY_HORN_HOLES
        result['printed_parts_changed'] = {name: slug for name, (slug, _) in printed.items()}
        result['printed_parts_changed']['Jaw_30_moving_jaw + Jaw_38 + Jaw_39'] = '30_38_39_jaw_one_piece-B19'
        if stl:
            stl.mkdir(parents=True, exist_ok=True)
            for name, (slug, direction) in printed.items():
                print_mesh(world_shape(doc.getObject(name)), stl/f'{slug}.stl', direction)
            jaw_one_piece(doc, stl/'30_38_39_jaw_one_piece-B19.3mf')
            (stl/'hardware-spec.json').write_text(json.dumps(hardware_spec(), indent=1) + '\n')
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(output.resolve()))
    finally:
        App.closeDocument(doc.Name)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if report:
        report.write_text(text + '\n')
    print(text)
    if result['static_overlap_mm3'] or result['sweep_overlap_mm3'] or \
            any(gap < 0 for gap in result['mesh_min_gap_mm'].values()):
        raise SystemExit('B19 pitch dowels overlap the assembly')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=HERE / 'revisions/b18/R5-B18-external-connections.FCStd')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--stl', type=Path, help='Folder for the changed printed parts and the sweep spec')
    make(**vars(parser.parse_args()))
