"""Fit the stop coupon's removable sleeve geometry to the native B25 clevises."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from math import ceil, degrees, hypot, radians, sqrt
from pathlib import Path

import FreeCAD as App
import numpy as np
import Part

from build_b25_pitch_stop_coupon import (
    BORE_DIAMETER, GEOMETRIC_TEST_TRAVEL, LINK_GAP, PIN_DIAMETER, PIN_LENGTH, VOLUME_TOL,
    check_clear, load_cases, shape_at, verify_b25,
)
from primitives import box, cylinder
from stock import socket_screw


PIN_END = PIN_LENGTH / 2
END_LENGTH = 4.5
KEEPER_START = PIN_END + .10
KEEPER_END = PIN_END + 3.2
KEEPER_RADIUS = BORE_DIAMETER / 2 - .025
RETAINER_SHIFT = 1.90
RETAINER_SEAT = 5.80
RETAINER_LENGTH = 4.
RETAINER_Y = (0., 1., 0.)
DRIVER_RADIUS = 1.48  # 2.5 mm hex key corner radius
PULL_SCREW_LENGTH = 6.
PULL_SCREW_ENGAGEMENT = 3.
CLEVIS_INBOARD_END = PIN_END + END_LENGTH
PITCH_INTERVAL = (-17.204140625, 7.12171875)
PITCH_PIVOT = App.Vector(0., 0., 112.)
AXIS_X = App.Vector(1., 0., 0.)
IN_SERVICE_GAP = .10
SHELL_SERVICE = {'Part074', 'RearSkullScrewLeft', 'RearSkullScrewRight',
                 'RearSkullNutLeft', 'RearSkullNutRight'}


def offset(center, side, axial, lateral=0., vertical=0.):
    x, y, z = center
    return (x + side * axial, y + lateral, z + vertical)


def axial_cylinder(center, side, radius, low, high):
    return cylinder(radius, high - low, offset(center, side, low), (side, 0., 0.))


def retainer(center):
    # Use a standard socket head screw. For CAD, the body tap is represented at
    # the major diameter, and the keeper has a clearance scallop.
    return socket_screw(3, RETAINER_LENGTH, offset(center, 1, PIN_END + RETAINER_SHIFT,
                                                   RETAINER_SEAT), (0., -1., 0.))


def make_shim_station(original, center):
    # Open both sleeve seats from +X and leave the stock -X exterior and
    # Ø2.6 eject throat in place. Restore the +X screw's original counterbore
    # locally for the shallower M3 keeper.
    restored = cylinder(1.86, 1.7, offset(center, 1, PIN_END + RETAINER_SHIFT, 4.43), RETAINER_Y)
    restore_pad = axial_cylinder(center, 1, 6., PIN_END - .3, CLEVIS_INBOARD_END)
    fill = restored.common(restore_pad)
    spot = offset(center, 1, PIN_END + RETAINER_SHIFT, RETAINER_SEAT)
    body = original.fuse(fill).cut([
        axial_cylinder(center, -1, BORE_DIAMETER/2, LINK_GAP/2-.025, PIN_END),
        axial_cylinder(center, 1, BORE_DIAMETER/2, LINK_GAP/2-.025, CLEVIS_INBOARD_END+.1),
        cylinder(1.55, RETAINER_LENGTH + .1, spot, (0., -1., 0.)),
        cylinder(2.83, 1.1, spot, RETAINER_Y),
    ]).removeSplitter()
    scallop = cylinder(1.60, RETAINER_LENGTH + .2,
                        offset(center, 1, PIN_END + RETAINER_SHIFT, RETAINER_SEAT + .1),
                        (0., -1., 0.))
    keeper = axial_cylinder(center, 1, KEEPER_RADIUS, KEEPER_START, KEEPER_END).cut([
        axial_cylinder(center, 1, 1.25, KEEPER_START - .1, KEEPER_END + .1), scallop,
    ]).removeSplitter()
    shims = [
        axial_cylinder(center, side, 4., 1.50, 1.80).cut(
            axial_cylinder(center, side, 2.025, 1.49, 1.81))
        for side in (-1, 1)
    ]
    for name, shape in [('clevis', body), ('keeper', keeper), *[('shim', shim) for shim in shims]]:
        if not shape.isValid() or len(shape.Solids) != 1:
            raise ValueError(f'Invalid ordinary-M3 {name}')
    screw = retainer(center)
    return body, keeper, screw, Part.Compound([fill, screw, *shims]), shims


def proximity(name, shape, obstacles):
    # Exact solid intersection for the paths. The broad phase is conservative.
    near = [(label, solid) for label, solid in obstacles if shape.BoundBox.intersect(solid.BoundBox)]
    check_clear(name, shape, near)


def check_inboard(name, center, keeper, screw, pin, service):
    seated = service + [('stock pin', pin), ('keeper', keeper)]
    proximity(f'{name} seated M3 screw', screw, seated)
    tap_start_y = RETAINER_SEAT - RETAINER_LENGTH
    m3_shaft = cylinder(1.5, 27., offset(center, 1, PIN_END + RETAINER_SHIFT, tap_start_y), RETAINER_Y)
    m3_head = cylinder(2.78, 24., offset(center, 1, PIN_END + RETAINER_SHIFT, RETAINER_SEAT), RETAINER_Y)
    driver_start = offset(center, 1, PIN_END + RETAINER_SHIFT, RETAINER_SEAT + 3.)
    driver = cylinder(DRIVER_RADIUS, 20., driver_start, RETAINER_Y)
    holder = cylinder(3.85, 20., offset(center, 1, PIN_END + RETAINER_SHIFT, RETAINER_SEAT + 23.),
                      RETAINER_Y)
    for label, shape in [('M3 shaft entry', m3_shaft), ('M3 head entry', m3_head),
                         ('2.5 mm hex driver', driver), ('driver holder', holder)]:
        proximity(f'{name} {label}', shape, seated)

    keeper_sweep = axial_cylinder(center, 1, KEEPER_RADIUS, KEEPER_START, 27.)
    proximity(f'{name} keeper installation', keeper_sweep, service)
    retained = keeper.copy().translate(App.Vector(.35, 0., 0.))
    if retained.common(screw).Volume <= VOLUME_TOL:
        raise ValueError(f'{name} keeper can walk over its M3 retainer')


def check_keeper_pull(name, center, body, keeper, pin, service):
    # After removing the radial retainer, engage the pull screw by a measured
    # depth. The under-head face must never reach the mouth of the keeper.
    tip = KEEPER_END - PULL_SCREW_ENGAGEMENT
    under_head = tip + PULL_SCREW_LENGTH
    pull_screw = socket_screw(3, PULL_SCREW_LENGTH, offset(center, 1, under_head), (-1., 0., 0.))
    stem_path = axial_cylinder(center, 1, 1.50, tip, 29.)
    head_path = axial_cylinder(center, 1, 2.78, under_head, 32.)
    pull_path = pull_screw.fuse([stem_path, head_path])
    proximity(f'{name} M3 × 6 pull and withdrawal', pull_path, service + [('stock pin', pin)])
    tap_wall = axial_cylinder(center, 1, 1.6, tip, KEEPER_END).cut(
        axial_cylinder(center, 1, 1.25, tip, KEEPER_END))
    if tap_wall.cut(keeper).Volume > 1e-5:
        raise ValueError(f'{name} keeper lacks the planned full pull thread section')
    flush_head = axial_cylinder(center, 1, 2.78, KEEPER_END, KEEPER_END + 3.)
    clash = flush_head.common(body).Volume
    if clash <= VOLUME_TOL:
        raise ValueError(f'{name} expected flush pull screw to collide with the clevis')
    return {'nominal_screw_length_mm': PULL_SCREW_LENGTH,
            'minimum_under_head_to_keeper_face_mm': round(CLEVIS_INBOARD_END - KEEPER_END, 2),
            'checked_under_head_to_keeper_face_mm': round(under_head - KEEPER_END, 2),
            'checked_under_head_to_clevis_mouth_mm': round(under_head - CLEVIS_INBOARD_END, 2),
            'checked_engagement_mm': PULL_SCREW_ENGAGEMENT,
            'nominal_tip_to_pin_gap_mm': round(tip - PIN_END, 2),
            'flush_head_overlap_mm3': clash}


def check_shim_station(name, center, body, keeper, screw, shims, eye, obstacles, rows):
    pin = axial_cylinder(center, -1, PIN_DIAMETER/2, -PIN_END, PIN_END)
    service = [('body', body), *obstacles]
    sleeve_sweep = axial_cylinder(center, 1, BORE_DIAMETER/2, -PIN_END, 34.)
    proximity(f'{name} one-sided sleeve installation', sleeve_sweep, service)
    pin_sweep = axial_cylinder(center, 1, PIN_DIAMETER/2, -PIN_END, 32.)
    proximity(f'{name} pin insertion', pin_sweep, service + [('steel link', eye)])
    drift = axial_cylinder(center, -1, 1.15, PIN_END, 35.)
    proximity(f'{name} Ø2.3 eject drift', drift, service)
    service_with_link = service + [('steel link', eye)]
    check_inboard(name, center, keeper, screw, pin, service_with_link)
    pull = check_keeper_pull(name, center, body, keeper, pin, service_with_link)
    for side, shim in zip((-1, 1), shims, strict=True):
        prefix = f'{name} {side:+}'
        y, z = center[1:]
        # The swept solid encloses all axial positions of each washer
        # inserted from +Y during neutral service, with the pin absent.
        plate_path = box(*sorted((center[0]+side*1.50, center[0]+side*1.80)),
                        y, y+12., z-4., z+4.)
        washer_path = axial_cylinder(center, side, 4., 1.50, 1.80).fuse(plate_path)
        proximity(f'{prefix} rear shim entry', washer_path, service + [('steel link', eye)])
        # The shim must overlap both the sleeve face and the outer face of
        # the steel link. X clearance allows the link and shims to float.
        sample_ring = positioned_sleeve(center, side)
        moving_shim = shim.copy().translate(App.Vector(side*.55, 0., 0.))
        if moving_shim.common(sample_ring).Volume <= VOLUME_TOL:
            raise ValueError(f'{prefix} sleeve can leave through the shim')
        moving_shim = shim.copy().translate(App.Vector(-side*.10, 0., 0.))
        if moving_shim.common(eye).Volume <= VOLUME_TOL:
            raise ValueError(f'{prefix} shim is unsupported by the steel link')
        ligament = axial_cylinder(center, side, BORE_DIAMETER/2 + 1., LINK_GAP/2, PIN_END).cut(
            axial_cylinder(center, side, BORE_DIAMETER/2, LINK_GAP/2, PIN_END))
        if ligament.cut(body).Volume > 1e-5:
            raise ValueError(f'{prefix} does not retain 1 mm of material around sleeve')
    pin_probe = pin.copy().translate(App.Vector(-.1, 0., 0.))
    if pin_probe.common(body).Volume <= VOLUME_TOL:
        raise ValueError(f'{name} outboard pin can escape through the stock throat')
    for row in rows:
        y, z = row['force_unit_yz']
        for step in range(9):
            shift = GEOMETRIC_TEST_TRAVEL * step / 8
            offset_vector = App.Vector(0., shift*y, shift*z)
            deflect = pin.copy().translate(offset_vector)
            proximity(f'{name} pin deflection', deflect, [('body', body), ('keeper', keeper)])
            for shim in shims:
                moved = shim.copy().translate(offset_vector)
                proximity(f'{name} pin and shim deflection', moved, [('body', body), ('steel link', eye)])
    return {'sleeve_support_width_mm': [8.10, 8.10], 'max_checked_pin_radial_displacement_mm': GEOMETRIC_TEST_TRAVEL,
            'shim_nominal_dimensions_mm': [4., 8., .30], 'free_axial_link_and_shim_stack_mm': .20,
            'shim_rear_entry_length_mm': 12., 'fastener_and_service_sweeps': 11,
            'keeper_pull': pull, 'shim_model': 'radial co-motion with pin, fixed axial position, rigid and frictionless'}


def positioned_sleeve(center, side):
    start = LINK_GAP / 2 + .05
    end = start + 8.
    return axial_cylinder(center, side, BORE_DIAMETER / 2, start, end).cut(
        axial_cylinder(center, side, PIN_DIAMETER / 2, start - .01, end + .01))


def shell_faces(obj, x_low, x_high):
    mesh = obj.Mesh.copy()
    mesh.Placement = obj.getGlobalPlacement()
    points, topology = mesh.Topology
    coordinates = np.array([list(point) for point in points])
    topology = np.array(topology)
    x = coordinates[topology, 0]
    near = (x.min(axis=1) < x_high) & (x.max(axis=1) > x_low)
    triangles = coordinates[topology[near]]
    return triangles, triangles.min(axis=1), triangles.max(axis=1)


def pitch_gap(shape, geometry, angle, required):
    posed = shape.copy()
    posed.rotate(PITCH_PIVOT, AXIS_X, angle)
    bounds = posed.BoundBox
    lower = np.array([bounds.XMin, bounds.YMin, bounds.ZMin])
    upper = np.array([bounds.XMax, bounds.YMax, bounds.ZMax])
    triangles, min_vertex, max_vertex = geometry
    overlap = np.all((min_vertex < upper + required) & (max_vertex > lower - required), axis=1)
    smallest = required
    for triangle in triangles[overlap]:
        points = [App.Vector(*point) for point in triangle]
        face = Part.Face(Part.makePolygon(points + points[:1]))
        gap = posed.distToShape(face)[0]
        smallest = min(smallest, gap)
        if smallest <= 1e-8:
            return 0.
    return smallest


def check_shell(doc, parts):
    # Check the changed M3 keeper hardware and shims. The outboard boss is stock.
    hulls = {name: shell_faces(doc.getObject(name), -61., -27.) for name in ('Part073', 'Part074')}
    angles = np.linspace(*PITCH_INTERVAL, ceil((PITCH_INTERVAL[1] - PITCH_INTERVAL[0]) / .5) + 1)
    count = 0
    for root, moving, _ in parts:
        bounds = moving.BoundBox
        radius = max(hypot(y, z - PITCH_PIVOT.z)
                     for y in (bounds.YMin, bounds.YMax) for z in (bounds.ZMin, bounds.ZMax))
        positions = angles if root == 'Lower' else [0.]
        # A point cannot move further than radius × half the angle step
        # between a sample and its closest adjacent position.
        required = IN_SERVICE_GAP + radius*radians(float(angles[1] - angles[0])/2) if root == 'Lower' else IN_SERVICE_GAP
        for angle in positions:
            for name, hull in hulls.items():
                if pitch_gap(moving, hull, -float(angle), required) < required:
                    raise ValueError(f'{root} keeper hardware too close to {name} at pitch {angle:.4f}°')
                count += 1
    # Negative control. A solid around a protruding outboard
    # yoke bore interferes with the rear shell at the released forward end.
    lower_center = parts[0][2]
    protrusion = axial_cylinder(lower_center, -1, 5.9, PIN_END - .35, PIN_END + END_LENGTH)
    rejected_gap = pitch_gap(protrusion, hulls['Part074'], -PITCH_INTERVAL[1], IN_SERVICE_GAP)
    if rejected_gap > 1e-6:
        raise ValueError('Expected shell collision witness for an extended lower outboard boss')
    return {'pitch_limits_deg': PITCH_INTERVAL, 'shell_pair_samples': count,
            'continuous_new_hardware_shell_gap_floor_mm': IN_SERVICE_GAP,
            'rejected_extended_lower_boss_gap_mm': rejected_gap}


def load_targets():
    # Carry over the B25 neck study inputs for the fully bonded reinforcement
    # material hypothesis. These values screen an assembled stop curve; they
    # do not compute new stresses for drilled or mechanically fastened parts.
    cases = (
        ('back', .05044, .13473, 35.310, .76, .001110, .000601),
        ('forward', .05409, .15073, 32.947, 1.16, .000944, .000514),
    )
    bearing_limit = 710. / 1.5
    results = []
    for direction, energy, closing, lever, overshoot_limit, soft, stiff in cases:
        sustainable = 1000. * closing / lever
        displacement_limit = lever * radians(overshoot_limit)
        permitted_force = (bearing_limit - 8.) / 1.15
        use_soft_limit = .00040
        use_stiff_limit = .00025
        variants = {}
        for label, compliance in (
            ('soft_with_sleeves', soft + use_soft_limit),
            ('stiff_with_sleeves', stiff + use_stiff_limit),
            ('stiff_without_sleeves', stiff),
        ):
            force = sustainable + sqrt(sustainable**2 + 2000. * energy / compliance)
            angle = degrees(force * compliance / lever)
            bearing = 1.15 * force + 8.
            variants[label] = {'arrest_angle_deg': angle, 'peak_stop_force_N': force,
                               'bearing_screen_N': bearing,
                               'passes_angle_and_bearing': angle <= overshoot_limit and bearing <= bearing_limit}
        if not all(variants[k]['passes_angle_and_bearing'] for k in ('soft_with_sleeves', 'stiff_with_sleeves')):
            raise ValueError(f'{direction} coupon range fails the study screen')
        if variants['stiff_without_sleeves']['passes_angle_and_bearing']:
            raise ValueError(f'{direction} rigid insert unexpectedly passes the study bearing limit')
        results.append({'direction': direction, 'incident_energy_J': energy, 'closing_force_along_stop_N': sustainable,
                        'travel_limit_mm': displacement_limit, 'stop_force_limit_N': permitted_force, 'cases': variants})
    return {'status': 'B25 neck study material hypotheses, no assembled force curve measured',
            'bearing_screen_limit_N': bearing_limit,
            'left_shaft_radial_proof': {'minimum_N': 446., 'slope_on_observed_peak_stop_force': 1.15,
                                        'offset_N': 8., 'maximum_N': bearing_limit,
                                        'rule': 'Prove max(minimum_N, 1.15 × observed peak stop force + 8 N). Reject if it exceeds maximum_N.'},
            'separate_pitch_coupler_torsion_proof_Nm': [-.65, .65],
            'results': results}


def save_part(doc, host, name, label, shape):
    group = host.getParentGeoFeatureGroup()
    obj = group.newObject('Part::Feature', name)
    obj.Label = label
    obj.Shape = shape
    obj.Placement = group.getGlobalPlacement().inverse().multiply(obj.Placement)
    obj.addProperty('App::PropertyString', 'Motion', 'Wiring')
    obj.Motion = host.Motion


def build(source, output):
    candidate = output / 'B25-pitch-stop-seats-m3.FCStd'
    if source.resolve() == candidate.resolve():
        raise ValueError('Choose a separate CAD output')
    with source.open('rb') as stream:
        source_hash = file_digest(stream, 'sha256').hexdigest()
    doc = App.openDocument(str(source.resolve()))
    try:
        anchors, link = verify_b25(doc)
        rows = load_cases(link)
        eye = shape_at(doc.PitchLimitLink)
        removed = {'PitchLimitLowerRetainer', 'PitchLimitUpperRetainer'}
        solids = [(obj.Name, shape_at(obj)) for obj in doc.Objects
                  if obj.TypeId == 'Part::Feature' and obj.Name not in removed]
        parts = []
        motion_witnesses = []
        for root, clevis, anchor in zip(('Lower', 'Upper'), ('yoke', 'frame'), anchors, strict=True):
            host = doc.getObject(anchor['part'])
            center = anchor['pin_center_mm']
            obstacles = [(name, solid) for name, solid in solids if name not in
                         {host.Name, f'PitchLimit{root}Pin', 'PitchLimitLink', *SHELL_SERVICE}]
            reactions = [row for row in rows if row['clevis'] == clevis]
            body, keeper, screw, witness, shims = make_shim_station(shape_at(host), center)
            data = check_shim_station(root, center, body, keeper, screw, shims, eye, obstacles, reactions)
            parts.append((root, host, body, keeper, screw, shims, anchor | data))
            motion_witnesses.append((root, witness, center))

        motion = check_shell(doc, motion_witnesses)
        for name in removed:
            doc.removeObject(name)
        for root, host, body, keeper, screw, shims, row in parts:
            parent = host.getParentGeoFeatureGroup()
            body.Placement = parent.getGlobalPlacement().inverse().multiply(body.Placement)
            host.Shape = body
            save_part(doc, host, f'PitchLimit{root}InboardKeeper', 'Steel sleeve keeper · M3 pull thread', keeper)
            for side, axis, shim in zip(('Outboard', 'Inboard'), (-1, 1), shims, strict=True):
                sleeve = positioned_sleeve(row['pin_center_mm'], axis)
                save_part(doc, host, f'PitchLimit{root}{side}Sleeve', 'Ø5.10 × Ø4.00 as-seated test sleeve', sleeve)
                save_part(doc, host, f'PitchLimit{root}{side}Shim', 'DIN 988 · 4 × 8 × 0.3 mm shim', shim)
            save_part(doc, host, f'PitchLimit{root}InboardScrew', 'M3 × 4 socket-head keeper screw', screw)

        output.mkdir(parents=True, exist_ok=True)
        doc.recompute()
        doc.saveAs(str(candidate.resolve()))
        report = {'status': 'neutral solid service and pitch shell checks passed',
                  'source_cad_sha256': source_hash,
                  'retention': 'inboard M3 and DIN 988 shims',
                  'stations': [data for _, _, _, _, _, _, data in parts],
                  'installed_shell_clearance': motion,
                  'inherited_load_screen': load_targets(),
                  'scope': 'B25 native solid checks at neutral with rear skull removed for repair. Sleeves and actual material properties are unmeasured.'}
        (output / 'neck-stop-seats-m3.json').write_text(json.dumps(report, indent=2) + '\n')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    build(**vars(parser.parse_args()))
