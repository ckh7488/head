"""Seat the eye pitch on two miniature bearings in the fixed cradle mounts."""

import json

from build_b19_review_fixes import add_part, replace
from build_b21_fasteners import check_solid, detached_shape
from primitives import cylinder, print_mesh


VENDOR = 'NSK MR63ZZMC3P6'
REFERENCE = 'https://www.nsk.com/eu-en/engineering/products/bearings/ball-bearings/deep-groove-ball-bearings/extra-small-ball-bearings-and-miniature-ball-bearings-metric-series/mr63zzmc3p6-apn.html'
PIVOT_YZ = (-39., 119.)
DIAMETERS = (3., 6.)
WIDTH = 2.5
POCKET_DIAMETER = 6.24
ABUTMENT_DIAMETER = 5.20
SEAT_X = 66.67
SUPPORTS = (
    ('left', -1, 'Part025', 'Part026', 'EyePitchBearingL', 'CradleMountFrameL', 'x-'),
    ('right', 1, 'Part027', 'Part028', 'EyePitchBearingR', 'CradleMountFrameR', 'x+'),
)
PRINTS = {f'13_{side}_eye_cradle_mount.stl': f'13_{side}_eye_cradle_mount-B24.stl'
          for side, *_ in SUPPORTS}


def apply(doc, prints):
    geometry = json.loads(doc.R5.MotionGeometry)
    if 'eye_pitch_bearings' in geometry:
        raise ValueError('The eye-pitch bearings are already seated')
    fitted = []
    for side, sign, bracket, pin, bearing, bolt, orientation in SUPPORTS:
        axis = (sign, 0, 0)
        mount = doc.getObject(bracket)
        stock = detached_shape(mount)
        through = cylinder(ABUTMENT_DIAMETER/2, 4.52, (sign*64.74, *PIVOT_YZ), axis)
        pocket = cylinder(POCKET_DIAMETER/2, 2.62, (sign*SEAT_X, *PIVOT_YZ), axis)
        support = check_solid(stock.cut([through, pocket]), f'{side} eye-pitch bearing bracket')
        replace(mount, support)
        print_mesh(support.copy(), prints / PRINTS[f'13_{side}_eye_cradle_mount.stl'], orientation)

        outer = cylinder(DIAMETERS[1]/2, WIDTH, (sign*SEAT_X, *PIVOT_YZ), axis)
        inner = cylinder(DIAMETERS[0]/2, WIDTH+.02, (sign*(SEAT_X-.01), *PIVOT_YZ), axis)
        ring = add_part(doc, mount.getParentGeoFeatureGroup(), bearing, f'{VENDOR} · eye-pitch bearing',
                        outer.cut(inner), 'head')
        ring.addProperty('App::PropertyFloat', 'EstimatedGrams', 'Mechanical')
        ring.EstimatedGrams = .27
        doc.getObject(pin).Motion = 'tilt'
        fitted.append({'side': side, 'bracket': bracket, 'pin': pin, 'bearing': bearing, 'bolt': bolt,
                       'insertion_mm': [sign*10., 0., 0.], 'bearing_seat_x_mm': sign*SEAT_X,
                       'print_orientation': orientation, 'removed_material_mm3': stock.Volume-support.Volume})

    specification = {
        'vendor_model': VENDOR, 'reference': REFERENCE, 'dimensions_mm': [*DIAMETERS, WIDTH],
        'pocket_diameter_mm': POCKET_DIAMETER, 'abutment_diameter_mm': ABUTMENT_DIAMETER,
        'frame_alignment_jig': {'diameter_mm': 2.98, 'length_mm': 150., 'axis_yz_mm': PIVOT_YZ,
                                'feed_offset_mm': [-162., 0., 0.]},
        'supports': fitted,
    }
    geometry['eye_pitch_bearings'] = specification
    doc.R5.MotionGeometry = json.dumps(geometry, ensure_ascii=False)
    return specification
