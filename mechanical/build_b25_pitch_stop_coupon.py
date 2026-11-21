"""Make and check a removable pitch-stop sleeve coupon against the B25 dimensions."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from math import atan2, copysign, cos, degrees, radians, sin
from pathlib import Path

import FreeCAD as App
import Part

from primitives import box, cylinder
from stock import nut, socket_screw
from tool_access import KEY_RADIUS, WRENCH_THICKNESS, wrench_profile, wrench_shape


X = (1., 0., 0.)
NX = (-1., 0., 0.)
PIN_LENGTH = 20.
PIN_DIAMETER = 4.
EAR_WIDTH = 8.10
LINK_GAP = 3.80
BORE_DIAMETER = 5.10
THROAT_DIAMETER = 4.70
LIP_WIDTH = .50
SLEEVE_LENGTH = 7.50
SLEEVE_OD = 5.12
SLEEVE_ID = 3.98
KEEPER_WIDTH = 2.
KEEPER_RECESS = .10
SCREW_LATERAL = (-6., 6.)
SCREW_Z = -14.
LOAD_EYE_SPAN = 21.
LOAD_EYE_HOLE_DIAMETER = 4.10
GEOMETRIC_TEST_TRAVEL = .16
JAW_POSITION = -23.
VOLUME_TOL = 1e-7
SOURCES = ('Part011', 'Part019')
PICK_RADIUS = .35
PICK_REACH = 1.
PICK_INSERT_Y = .55
PICK_SPREAD = .37
SLEEVE_WITHDRAWAL = 8.


def shape_at(obj):
    shape = obj.Shape.copy()
    shape.Placement = obj.getGlobalPlacement()
    return shape


def verify_b25(doc):
    geometry = json.loads(doc.R5.MotionGeometry)
    link = geometry['pitch_stop']['link']
    dimensions = (
        (link['pin_length_mm'], PIN_LENGTH),
        (link['pin_diameter_mm'], PIN_DIAMETER),
        (link['clevis_gap_mm'], LINK_GAP),
        (link['plate_thickness_mm'], 3.),
        (link['plate_width_mm'], 12.),
    )
    if any(abs(actual - expected) > 1e-7 for actual, expected in dimensions):
        raise ValueError('The fixture dimensions no longer match the B25 pitch stop')
    references = []
    for part_name, pin_key in zip(SOURCES, ('pan_pin_mm', 'head_pin_mm'), strict=True):
        center = link[pin_key]
        part = shape_at(doc.getObject(part_name))
        spans = []
        for face in part.Faces:
            surface = face.Surface
            if not isinstance(surface, Part.Cylinder) or abs(surface.Axis.x) < .999:
                continue
            if abs(surface.Radius - link['clevis_bore_diameter_mm'] / 2) > 1e-6:
                continue
            if max(abs(surface.Center.y-center[1]), abs(surface.Center.z-center[2])) > 1e-6:
                continue
            bounds = face.BoundBox
            spans.append([max(bounds.XMin, center[0] - PIN_LENGTH/2),
                          min(bounds.XMax, center[0] + PIN_LENGTH/2)])
        spans.sort()
        if len(spans) != 2 or any(abs(hi - lo - EAR_WIDTH) > 1e-6 for lo, hi in spans):
            raise ValueError(f'{part_name} no longer has the expected ear support spans')
        references.append({'part': part_name, 'pin_center_mm': center, 'ear_x_spans_mm': spans})
    return references, link


def make_body():
    block = box(-10., 10., -10., 10., -30., 8.)
    cuts = [
        box(-LINK_GAP/2, LINK_GAP/2, -10.1, 10.1, -9., 8.1),
        cylinder(THROAT_DIAMETER/2, 20.2, (-10.1, 0., 0.), X),
    ]
    for side in (-1, 1):
        cuts.append(cylinder(BORE_DIAMETER/2, EAR_WIDTH-LIP_WIDTH+.10,
                             (side*10.10, 0., 0.), (-side, 0., 0.)))
    for y in SCREW_LATERAL:
        cuts.append(cylinder(1.70, 20.2, (-10.1, y, SCREW_Z), X))
    return block.cut(cuts).removeSplitter()


def make_keeper(side):
    inner_x = side * PIN_LENGTH/2
    outer_x = inner_x + side * KEEPER_WIDTH
    slab = box(*sorted((inner_x, outer_x)), -10., 10., -18., 5.5)
    cuts = [
        cylinder(2.70, KEEPER_RECESS+.01, (inner_x-side*.01, 0., 0.), (side, 0., 0.)),
        cylinder(1.30, KEEPER_WIDTH+.02, (inner_x-side*.01, 0., 0.), (side, 0., 0.)),
    ]
    for y in SCREW_LATERAL:
        cuts.append(cylinder(1.70, KEEPER_WIDTH+.02,
                             (inner_x-side*.01, y, SCREW_Z), (side, 0., 0.)))
    return slab.cut(cuts).removeSplitter()


def make_sleeve(side, installed):
    outer = BORE_DIAMETER if installed else SLEEVE_OD
    inner = PIN_DIAMETER if installed else SLEEVE_ID
    start = side * (LINK_GAP / 2 + LIP_WIDTH)
    bore = cylinder(inner/2, SLEEVE_LENGTH+.02, (start-side*.01, 0., 0.), (side, 0., 0.))
    return cylinder(outer/2, SLEEVE_LENGTH, (start, 0., 0.), (side, 0., 0.)).cut(bore)


def make_load_eye():
    x = -1.5
    ends = (0., LOAD_EYE_SPAN)
    round_ends = [cylinder(6., 3., (x, 0., z), X) for z in ends]
    holes = [cylinder(LOAD_EYE_HOLE_DIAMETER/2, 3.2, (x-.1, 0., z), X) for z in ends]
    strip = box(-1.5, 1.5, -6., 6., *ends)
    return strip.fuse(round_ends).cut(holes).removeSplitter()


def stock_hardware():
    screws, nuts = [], []
    for y in SCREW_LATERAL:
        screws.append(socket_screw(3, 30., (12., y, SCREW_Z), NX))
        blank = nut(3, (-12., y, SCREW_Z), NX)
        nuts.append(blank.cut(cylinder(1.5, 2.6, (-11.9, y, SCREW_Z), NX)))
    return screws, nuts


def load_cases(link):
    # Reaction directions follow the contact pressure applied in b22_pitch_stop_strength.py.
    lower, upper = link['pan_pin_mm'], link['head_pin_mm']
    pivot_z = 112.
    rows = []
    for stop, angle, sign in (('back', -16.46, -1), ('forward', 5.97, 1)):
        pitch = radians(angle)
        y = upper[1]*cos(pitch) - (upper[2]-pivot_z)*sin(pitch)
        z = upper[1]*sin(pitch) + (upper[2]-pivot_z)*cos(pitch) + pivot_z
        world_line = atan2(y - lower[1], z - lower[2])
        moment_sign = copysign(1., y*cos(world_line) - (z-pivot_z)*sin(world_line))
        for clevis, reaction, line in (('yoke', sign*moment_sign, world_line),
                                       ('frame', -sign*moment_sign, world_line + pitch)):
            rows.append({
                'stop': stop, 'neck_pitch_deg': angle, 'clevis': clevis,
                'eye_angle_from_positive_z_toward_positive_y_deg': degrees(line),
                'load_along_eye': 'pull' if reaction > 0 else 'push',
                'force_unit_yz': [reaction*sin(line), reaction*cos(line)],
            })
    return rows


def rotated(shape, yz_angle, offset=0.):
    turn = shape.copy()
    turn.rotate(App.Vector(), App.Vector(*X), -degrees(yz_angle))
    turn.translate(App.Vector(0., offset*sin(yz_angle), offset*cos(yz_angle)))
    return turn


def check_clear(name, moving, obstacles):
    for other_name, other in obstacles:
        if moving.common(other).Volume > VOLUME_TOL:
            raise ValueError(f'{name} collides with {other_name}')


def check_tools(body, keepers, screws, nuts):
    vise = box(-12., 12., -12., 12., -30., JAW_POSITION)
    fixtures = [('body', body), ('vise envelope', vise)]
    fixtures.extend((f'keeper {i}', plate) for i, plate in enumerate(keepers))
    count = 0
    for index, y in enumerate(SCREW_LATERAL):
        other = 1-index
        # The full straight insertion sweep is the final shaft extended to the socket.
        screw_sweep = cylinder(1.5, 33., (-18., y, SCREW_Z), X)
        screw_head_sweep = cylinder(2.78, 33., (12., y, SCREW_Z), X)
        hex_key = cylinder(KEY_RADIUS[3], 20., (15., y, SCREW_Z), X)
        handle = cylinder(3.85, 24., (32., y, SCREW_Z), X)
        for name, swept in (('M3 entry sweep', screw_sweep.fuse(screw_head_sweep)),
                            ('2.5 mm driver shaft', hex_key), ('driver holder', handle)):
            check_clear(name, swept, fixtures + [('other M3 screw', screws[other])])
            count += 1
        nut_path = box(-30., -12., y-3.25, y+3.25, SCREW_Z-3.25, SCREW_Z+3.25)
        check_clear('nut seating', nut_path, fixtures + [('other M3 nut', nuts[other])])
        outward = App.Vector(0., copysign(1., y), 0.)
        head = wrench_shape(App.Vector(-12., y, SCREW_Z), App.Vector(*NX), outward,
                            wrench_profile(3), WRENCH_THICKNESS[3])
        obstructing = fixtures + [('M3 nut', hardware) for hardware in nuts]
        obstructing += [('M3 screw', hardware) for hardware in screws]
        for step in range(41):
            shifted = head.copy()
            shifted.translate(outward*(20. - step*.5))
            check_clear('5.5 mm wrench insertion', shifted, obstructing)
        count += 2
    return count, fixtures


def check_axial(body, keepers, pin, sleeves, eye):
    # Analytic swept cylinders cover the full insertion before either keeper is fitted.
    for side, sleeve, keeper in zip((-1, 1), sleeves, keepers, strict=True):
        start = side * (LINK_GAP/2 + LIP_WIDTH)
        swept = cylinder(BORE_DIAMETER/2, 19., (start, 0., 0.), (side, 0., 0.))
        check_clear('seated sleeve insertion sweep', swept, [('body', body), ('eye', eye)])
        outward = App.Vector(side*(.01 + KEEPER_RECESS), 0., 0.)
        for name, stationary in (('sleeve', sleeve), ('pin', pin)):
            moved = stationary.copy()
            moved.translate(outward + (App.Vector(side*.10, 0., 0.) if name == 'sleeve'
                                       else App.Vector()))
            if moved.common(keeper).Volume <= VOLUME_TOL:
                raise ValueError(f'{name} is not positively retained at x={side:+}')
        drift = cylinder(1.25, 11., (side*21., 0., 0.), (-side, 0., 0.))
        check_clear('Ø2.5 drift access', drift, [('keeper', keeper), ('body', body)])
    for side in (-1, 1):
        sweep = cylinder(PIN_DIAMETER/2, 35., (-side*10., 0., 0.), (side, 0., 0.))
        check_clear('pin insertion sweep', sweep, [('body', body), ('eye', eye)])
    return {
        'sleeve_axial_envelope_to_keeper_mm': round(EAR_WIDTH-LIP_WIDTH-SLEEVE_LENGTH+KEEPER_RECESS, 3),
        'centered_pin_axial_envelope_to_each_keeper_mm': KEEPER_RECESS,
        'hard_radial_clearance_at_throat_mm': round((THROAT_DIAMETER-PIN_DIAMETER)/2, 3),
        'sleeve_clear_of_central_link_slot': True,
        'drift_clear': True,
    }


def sleeve_pick(side, jaw):
    tip_x = side*(LINK_GAP/2 + LIP_WIDTH - PICK_RADIUS)
    shank_y = jaw*PICK_INSERT_Y
    start = (tip_x, shank_y, 0.)
    axial = cylinder(PICK_RADIUS, 24., start, (side, 0., 0.))
    hook = cylinder(PICK_RADIUS, PICK_REACH, start, (0., jaw, 0.))
    corner = Part.makeSphere(PICK_RADIUS, App.Vector(*start))
    end = Part.makeSphere(PICK_RADIUS, App.Vector(tip_x, shank_y + jaw*PICK_REACH, 0.))
    return axial.fuse([hook, corner, end]).removeSplitter()


def check_sleeve_removal(body):
    # With the pin, eye and keepers removed, opposed picks spread behind the
    # sleeve at the Ø4.70 throat. Each hook moves only inside the original bore.
    for side in (-1, 1):
        # Use the free ID for a conservative path once the sample is unloaded.
        inner_x = side*(LINK_GAP/2 + LIP_WIDTH)
        relaxed_bore = cylinder(SLEEVE_ID/2, SLEEVE_LENGTH+.02,
                                (inner_x-side*.01, 0., 0.), (side, 0., 0.))
        sleeve = cylinder(BORE_DIAMETER/2, SLEEVE_LENGTH, (inner_x, 0., 0.),
                          (side, 0., 0.)).cut(relaxed_bore)
        picks = [sleeve_pick(side, jaw) for jaw in (-1, 1)]
        check_clear('opposed picks at minimum spacing', picks[0], [('opposing pick', picks[1])])
        for jaw, pick in zip((-1, 1), picks, strict=True):
            for step in range(33):
                offset = SLEEVE_WITHDRAWAL*(32-step)/32
                insertion = pick.copy().translate(App.Vector(side*offset, 0., 0.))
                check_clear('sleeve pick insertion', insertion, [('body', body), ('sleeve', sleeve)])

            for step in range(5):
                lateral = PICK_SPREAD*step/4
                spread = pick.copy().translate(App.Vector(0., jaw*lateral, 0.))
                check_clear('sleeve pick spreading', spread, [('body', body), ('sleeve', sleeve)])
            engaged = spread.copy().translate(App.Vector(side*.02, 0., 0.))
            if engaged.common(sleeve).Volume <= VOLUME_TOL:
                raise ValueError('Sleeve pick does not catch the inner sleeve face')

            for step in range(33):
                offset = SLEEVE_WITHDRAWAL*step/32
                translation = App.Vector(side*offset, 0., 0.)
                withdrawal = spread.copy().translate(translation)
                withdrawn = sleeve.copy().translate(translation)
                check_clear('hooked sleeve withdrawal', withdrawal, [('body', body)])
                check_clear('sleeve withdrawal', withdrawn, [('body', body)])
    return {
        'opposed_picks_per_sleeve': 2,
        'pick_wire_diameter_mm': 2*PICK_RADIUS,
        'pick_radial_arm_center_to_center_mm': PICK_REACH,
        'pick_hook_center_depth_from_outer_ear_face_mm': round(PIN_LENGTH/2 - LINK_GAP/2 - LIP_WIDTH + PICK_RADIUS, 3),
        'pick_shank_initial_offset_each_side_mm': PICK_INSERT_Y,
        'pick_spread_each_side_mm': PICK_SPREAD,
        'required_sleeve_pull_mm': SLEEVE_WITHDRAWAL,
        'insertion_and_withdrawal_increment_mm': SLEEVE_WITHDRAWAL/32,
        'reached_inner_face_on_both_ears': True,
        'verified_scope': 'rigid tool reach and engagement geometry',
    }


def check_load_cases(body, eye, pin, keepers, screws, cases, fixture):
    obstacles = fixture + [(f'M3 screw {i}', screw) for i, screw in enumerate(screws)]
    pin_obstacles = [('body', body)] + [(f'keeper {i}', keeper) for i, keeper in enumerate(keepers)]
    for row in cases:
        eye_angle = radians(row['eye_angle_from_positive_z_toward_positive_y_deg'])
        load_sign = 1 if row['load_along_eye'] == 'pull' else -1
        for index in range(9):
            travel = GEOMETRIC_TEST_TRAVEL*index/8
            moved_eye = rotated(eye, eye_angle, load_sign*travel)
            moved_pin = rotated(pin, eye_angle, load_sign*travel)
            check_clear('load eye', moved_eye, obstacles)
            check_clear('stop pin travel', moved_pin, pin_obstacles + [('load eye', moved_eye)])
        row['checked_radial_travel_mm'] = GEOMETRIC_TEST_TRAVEL
        row['radial_positions_checked'] = 9


def add_solid(doc, name, label, shape):
    if not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError(f'Invalid solid for {label}')
    obj = doc.addObject('Part::Feature', name)
    obj.Label = label
    obj.Shape = shape


def export_fixture(path, body, keepers, pin, sleeves, eye, screws, nuts, cases):
    doc = App.newDocument('B25StopCoupon')
    try:
        items = [
            ('Body', 'Coupon · 6061-T6 body', body),
            ('KeeperLeft', 'Left keeper', keepers[0]),
            ('KeeperRight', 'Right keeper', keepers[1]),
            ('StopPin', 'B25 ground Ø4 × 20 pin', pin),
            ('SleeveLeft', 'Specimen · left as seated', sleeves[0]),
            ('SleeveRight', 'Specimen · right as seated', sleeves[1]),
            ('LoadEye', '3 × 12 steel load eye', rotated(eye, radians(cases[0][
                'eye_angle_from_positive_z_toward_positive_y_deg']))),
        ]
        for i, (screw, hex_nut) in enumerate(zip(screws, nuts, strict=True), 1):
            items += [(f'Screw{i}', f'M3×30 socket screw {i}', screw),
                      (f'Nut{i}', f'M3 hex nut {i}', hex_nut)]
        for name, label, shape in items:
            add_solid(doc, name, label, shape)
        doc.recompute()
        doc.saveAs(str(path/'B25-pitch-stop-coupon.FCStd'))
    finally:
        App.closeDocument(doc.Name)
    for name, shape in {
        'body': body, 'keeper-left': keepers[0], 'keeper-right': keepers[1],
        'load-eye': eye, 'sleeve-specimen': make_sleeve(1, installed=False),
    }.items():
        shape.exportStep(str(path / f'{name}.step'))


def build(source, output):
    source_hash = sha256(source.read_bytes()).hexdigest()
    doc = App.openDocument(str(source.resolve()))
    try:
        refs, link = verify_b25(doc)
    finally:
        App.closeDocument(doc.Name)

    body = make_body()
    keepers = [make_keeper(side) for side in (-1, 1)]
    sleeves = [make_sleeve(side, installed=True) for side in (-1, 1)]
    pin = cylinder(PIN_DIAMETER/2, PIN_LENGTH, (-PIN_LENGTH/2, 0., 0.), X)
    eye = make_load_eye()
    screws, nuts = stock_hardware()
    cases = load_cases(link)
    retention = check_axial(body, keepers, pin, sleeves, eye)
    sleeve_removal = check_sleeve_removal(body)
    paths_checked, fixture = check_tools(body, keepers, screws, nuts)
    check_load_cases(body, eye, pin, keepers, screws, cases, fixture)

    values = {
        'status': 'coupon geometry checked, physical sleeve properties unmeasured',
        'source_cad_sha256': source_hash, 'source_anchors': refs, 'load_cases': cases,
        'retention': retention, 'sleeve_removal': sleeve_removal,
        'fastener_and_tool_paths_checked': paths_checked,
        'dimensions_mm': {
            'loaded_ear_width': EAR_WIDTH, 'central_gap': LINK_GAP, 'bore': BORE_DIAMETER,
            'inner_throat': THROAT_DIAMETER, 'inner_throat_axial_width': LIP_WIDTH,
            'uncompressed_sleeve_od': SLEEVE_OD, 'uncompressed_sleeve_id': SLEEVE_ID,
            'sleeve_length': SLEEVE_LENGTH, 'load_eye_pin_span': LOAD_EYE_SPAN,
            'load_eye_diametral_play_at_stop_pin': round(LOAD_EYE_HOLE_DIAMETER-PIN_DIAMETER, 3),
        },
        'bench_targets': {
            'screening_loads_N': [262., 381.],
            'series_compliance_mm_per_N': [.00025, .00040],
            'half_budget_per_clevis_mm_per_N': [.000125, .00020],
            'total_displacement_at_262_N_mm': [.0655, .1048],
            'total_displacement_at_381_N_mm': [.09525, .1524],
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    export_fixture(output, body, keepers, pin, sleeves, eye, screws, nuts, cases)
    (output/'neck-stop-coupon.json').write_text(json.dumps(values, indent=2)+'\n')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    build(**vars(parser.parse_args()))
