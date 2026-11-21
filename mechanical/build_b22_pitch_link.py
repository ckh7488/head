"""Build the steel pitch limit link and its two captured Ø4 pins."""

from hashlib import sha256
import json
from math import cos, dist, radians, sin

import FreeCAD as App
import Part

from build_b19_review_fixes import add_part


PIVOT = (0., 0., 112.)
STOP_PITCH_DEG = (-16.20, 5.70)
POWERED_PITCH_DEG = (-15., 4.5)
THICKNESS = 3.
WIDTH = 12.
PIN_DIAMETER = 4.
PIN_LENGTH = 20.
SLOT_WIDTH = 4.2
PIVOT_BORE = 4.1
END_LIGAMENT = 8.


def rotate_head(point, pitch):
    x, y, z = point
    angle = radians(pitch)
    height = z - PIVOT[2]
    return x, y*cos(angle)-height*sin(angle), PIVOT[2]+y*sin(angle)+height*cos(angle)


def link_geometry(lower, upper):
    axis = App.Vector(upper) - App.Vector(lower)
    neutral_length = axis.Length
    axis.normalize()
    transverse = axis.cross(App.Vector(1., 0., 0.))
    centers = [dist(lower, rotate_head(upper, pitch)) for pitch in STOP_PITCH_DEG]
    play = (SLOT_WIDTH-PIN_DIAMETER)/2
    centers[0] += play
    centers[1] -= play
    if not 0. < centers[0] < neutral_length < centers[1]:
        raise ValueError('Pitch link slot must cross the neutral pin position')

    start = App.Vector(lower) + App.Vector(-THICKNESS/2, 0., 0.)
    x = App.Vector(1., 0., 0.)

    def prism(edge, depth):
        vertices = [start + axis*a + transverse*b for a, b in edge]
        return Part.Face(Part.makePolygon(vertices+[vertices[0]])).extrude(x*depth)

    def hole(radius, location):
        return Part.makeCylinder(radius, THICKNESS+.2, start + axis*location - x*.1, x)

    half = WIDTH/2
    end = centers[1]+END_LIGAMENT
    outline = [(-END_LIGAMENT, -half+1), (-END_LIGAMENT+1, -half), (end-1, -half),
               (end, -half+1), (end, half-1), (end-1, half), (-END_LIGAMENT+1, half), (-END_LIGAMENT, half-1)]
    low, high = centers
    radius = SLOT_WIDTH/2
    slot = prism([(low, -radius), (high, -radius), (high, radius), (low, radius)], THICKNESS)
    cutters = [slot.fuse([hole(radius, low), hole(radius, high)]), hole(PIVOT_BORE/2, 0.)]
    steel = prism(outline, THICKNESS).cut(cutters).removeSplitter()
    if not steel.isValid() or len(steel.Solids) != 1:
        raise ValueError('The plate and slot must yield one valid solid')
    return steel, tuple(centers), axis


def stop_locations(lower, slot_centers, axis):
    for side, pitch, center in zip((-1, 1), STOP_PITCH_DEG, slot_centers, strict=True):
        contact = list(App.Vector(lower) + axis*(center + side*SLOT_WIDTH/2))
        patch = [[contact[0]-2., contact[1]-3.4, contact[2]-3.4],
                 [contact[0]+2., contact[1]+3.4, contact[2]+3.4]]
        yield {'id': 'pitch-stop-forward' if side > 0 else 'pitch-stop-back',
               'label': '목 상하 · 앞으로' if side > 0 else '목 상하 · 뒤로',
               'stage': 'pitch-stop-pins', 'direction': side,
               'actors': ['PitchLimitLink', 'PitchLimitUpperPin'], 'nominal_deg': pitch,
               'search_window_deg': [pitch-side*.3, pitch+side*.3], 'patch_bounds_mm': patch}


def fit(doc, output, lower, upper):
    steel, centers, axis = link_geometry(lower, upper)
    link = add_part(doc, doc.R5, 'PitchLimitLink', '목 상하 제한 강철판 12 × 3', steel, 'pitch_link')
    motion = json.loads(doc.R5.MotionGeometry)
    clevises = motion['pitch_clevises']
    link_meta = {'pan_pin_mm': list(lower), 'head_pin_mm': list(upper), 'slot_centers_mm': list(centers),
                 'pin_diameter_mm': PIN_DIAMETER, 'slot_width_mm': SLOT_WIDTH, 'bore_diameter_mm': PIVOT_BORE,
                 'plate_thickness_mm': THICKNESS, 'plate_width_mm': WIDTH, 'pin_length_mm': PIN_LENGTH,
                 'minimum_end_distance_mm': END_LIGAMENT, 'clevis_gap_mm': clevises['slot_width_mm'],
                 'clevis_bore_diameter_mm': clevises['target_bore_mm']}
    motion['pitch_stop'] = {'powered_deg': list(POWERED_PITCH_DEG), 'required_gap_mm': .10,
                            'released_overshoot_deg': {'back': .76, 'forward': 1.16},
                            'stops': list(stop_locations(lower, centers, axis)),
                            'link': link_meta,
                            'modified_part_keys': ['Part011', 'Part019', 'PitchLimitLink',
                                                   'PitchLimitLowerPin', 'PitchLimitUpperPin']}
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)
    model = output / 'pitch-strap.step'
    output.mkdir(parents=True, exist_ok=True)
    link.Shape.exportStep(str(model))
    record = {**link_meta, 'plate_length_mm': centers[1]+2*END_LIGAMENT,
              'nominal_stop_pitch_deg': list(STOP_PITCH_DEG),
              'step_sha256': sha256(model.read_bytes()).hexdigest()}
    (output/'pitch-strap.json').write_text(json.dumps(record, indent=2)+'\n')
