"""Re-index the two eye-pitch arms and retain clearance around the right frame."""

from copy import deepcopy
import json
from math import cos, radians, sin

import FreeCAD as App
import Part

from build_b19_review_fixes import replace
from build_b21_fasteners import check_solid, detached_shape
from primitives import box, cylinder, print_mesh


PHASE = -17.
RADIUS = 10.
SERVO_AXIS = (58.65, 10., 151.)
CRADLE_AXIS = (0., -39., 119.)
FINISHED_BORE = 2.09
PILOT_BORE = 1.92
X = (1., 0., 0.)
HORN_HARDWARE = ('EyePitchHornScrew0', 'EyePitchHornScrew1', 'EyePitchLinkHornPin')
CRADLE_PIN = 'EyePitchLinkCradlePin'
PRINTS = {
    '12_eye_tilt_cradle-B20.stl': '12_eye_tilt_cradle-B23.stl',
    '17_eye_pitch_horn_10mm.stl': '17_eye_pitch_horn_10mm-B23.stl',
    '18_eye_pitch_link_58p5mm-B21.stl': '18_eye_pitch_link_58p5mm-B23.stl',
}


def pickup_shift():
    phase = radians(PHASE)
    return App.Vector(0., RADIUS*(cos(phase)-1.), RADIUS*sin(phase))


def reindex_hardware(rows):
    """Place the existing screw and pin envelopes on their indexed CAD axes."""
    updated = deepcopy(rows)
    horn_center = App.Vector(*SERVO_AXIS)
    rotation = App.Rotation(App.Vector(*X), PHASE)
    delta = pickup_shift()
    for row in updated:
        name = row['name']
        if name in HORN_HARDWARE:
            for envelope in row['shapes']:
                start = App.Vector(*envelope[3])
                envelope[3] = list(horn_center + rotation.multVec(start-horn_center))
        if name == CRADLE_PIN:
            for envelope in row['shapes']:
                envelope[3] = list(App.Vector(*envelope[3]) + delta)
    return updated


def rotate_horn(shape, angle=PHASE):
    shape.rotate(App.Vector(*SERVO_AXIS), App.Vector(*X), angle)
    return shape


def apply(doc, prints):
    motion = json.loads(doc.R5.MotionGeometry)
    if 'eye_pitch' in motion:
        raise ValueError('The eye-pitch geometry is already indexed')
    delta = pickup_shift()
    horn = check_solid(detached_shape(doc.Part043).cut(box(57.9, 62., 22.70, 30., 143., 159.)),
                       '17 eye-pitch horn')
    print_mesh(horn.copy(), prints / PRINTS['17_eye_pitch_horn_10mm.stl'], 'x+')
    replace(doc.Part043, rotate_horn(horn))
    for name in HORN_HARDWARE:
        actor = doc.getObject(name)
        replace(actor, rotate_horn(detached_shape(actor)))

    motor = detached_shape(doc.Part041)
    flanges = [solid for solid in motor.Solids if 560. < solid.Volume < 600. and 55. < solid.CenterOfMass.x < 59.]
    if len(flanges) != 1:
        raise ValueError('Cannot identify the XL330 eye-pitch output flange')
    flange = flanges[0]
    body = [solid for solid in motor.Solids if not solid.isSame(flange)]
    replace(doc.Part041, Part.Compound([*body, rotate_horn(flange)]))

    rear_pickup = App.Vector(0., 20., 151.) + delta
    front_pickup = App.Vector(0., -29., 119.) + delta
    rod = detached_shape(doc.Part044)
    rod.translate(delta)
    relief = box(60., 67., 2.58, 9., -8., 8.)
    relief.rotate(App.Vector(), App.Vector(*X), -26.)
    relief.translate(rear_pickup)
    rod = check_solid(rod.cut(relief), '18 eye-pitch link')
    filled, drills = [], []
    for center in (front_pickup, rear_pickup):
        filled.append(cylinder(FINISHED_BORE/2+.055, 2.6, (61.55, center.y, center.z), X))
        drills.append(cylinder(PILOT_BORE/2, 2.8, (61.45, center.y, center.z), X))
    pilot_rod = check_solid(rod.fuse(filled).cut(drills), '18 eye-pitch link with drill pilots')
    print_mesh(pilot_rod, prints / PRINTS['18_eye_pitch_link_58p5mm-B21.stl'], 'x+')
    replace(doc.Part044, rod)
    pin = detached_shape(doc.getObject(CRADLE_PIN))
    pin.translate(delta)
    replace(doc.getObject(CRADLE_PIN), pin)

    cradle = detached_shape(doc.Part024)
    support = cylinder(2.80, 3.35, (57.65, front_pickup.y, front_pickup.z), X)
    fill = cylinder(1.23, 3.35, (57.65, -29., 119.), X)
    bore = cylinder(1.18, 6.5, (56., front_pickup.y, front_pickup.z), X)
    cradle = check_solid(cradle.fuse([support, fill]).cut(bore), '12 eye-pitch cradle')
    print_mesh(cradle.copy(), prints / PRINTS['12_eye_tilt_cradle-B20.stl'], 'y+')
    replace(doc.Part024, cradle)

    geometry = {'phase_deg': PHASE, 'crank_radius_mm': RADIUS,
                'servo_axis_mm': SERVO_AXIS, 'cradle_axis_mm': CRADLE_AXIS}
    motion['eye_pitch'] = geometry
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)
    return geometry
