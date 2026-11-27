"""Hardware and service operations for the two B23 covers."""

from argparse import ArgumentParser
from copy import deepcopy
from hashlib import sha256
from itertools import product
import json
from pathlib import Path

import numpy as np


HATCH_DROPS = (0, 5, 10, 15, 25, 30)
B22_NATIVE = Path(__file__).resolve().parents[1] / 'revisions/b22/R5-B22-Assembly.FCStd'

def service_metadata(layout):
    motion = layout['motion_geometry']
    rear = motion['rear_cable_service_nuts']
    # B26 replaces the two keeper plates with visible press-fit nut seats in the base.
    slots = motion.get('bottom_board_nut_seats')
    bottom = motion.get('bottom_board_service_nuts', [])
    if (len(rear['bolt_seats_mm']) != 5 or rear['bolt_length_mm'] != 16.
            or rear['service_orientation'] != 'upright' or len(bottom) != (0 if slots else 2)
            or (slots is not None and len(slots) != 4)):
        raise ValueError('Incomplete stock hardware for B23 service covers')
    for cap in bottom:
        for field in ('keeper', 'screw'):
            if layout['world_motion'].get(cap[field]) != 'fixed':
                raise ValueError(f'Missing fixed service part {cap[field]}')
    return rear, bottom


def prepare_hardware(layout, data, spec):
    """Update B22 hardware to the native B23 stations while preserving stock sizes."""
    rear, bottom = service_metadata(layout)
    data, spec = deepcopy(data), deepcopy(spec)
    if eye_pitch := layout['motion_geometry'].get('eye_pitch'):
        from build_b23_eye_pitch import PHASE, reindex_hardware

        if eye_pitch['phase_deg'] != PHASE:
            raise ValueError('The eye-pitch stock parts do not match the indexed CAD')
        spec = reindex_hardware(spec)
    rows = {row['id']: row for row in data['hardware']}
    for index, seat in enumerate(rear['bolt_seats_mm']):
        bolt = rows[f'cableBolt{index}']
        if bolt['size'] != 3 or bolt['length'] != 16 or bolt['axis'] != [0, 0, -1]:
            raise ValueError(f'Unexpected rear cover hardware {bolt}')
        bolt['seat'] = seat
    names = {item['name'] for item in spec}
    for cap in bottom:
        name = cap['screw']
        if name in rows or name in names:
            raise ValueError(f'Duplicate service hardware {name}')
        seat, axis = np.asarray(cap['seat_mm']), np.asarray(cap['axis'])
        data['hardware'].append({'id': name, 'type': 'bolt', 'size': 3, 'length': 8,
                                 'axis': axis.tolist(), 'seat': seat.tolist(), 'phase': 0})
        spec.append({'name': name, 'motion': 'fixed', 'skip': ['Part000', cap['keeper']],
                     'shapes': [['cyl', 2.78, 3., (seat-3.05*axis).tolist(), axis.tolist()],
                                ['cyl', 1.35, 7.9, (seat+.05*axis).tolist(), axis.tolist()]]})
    if coupler := layout['motion_geometry'].get('pitch_coupler'):
        if layout['world_motion'].get(coupler['actor']) != 'head' or coupler['m3_size_mm'] != 3.:
            raise ValueError('Missing removable stock M3 drive screw in the head CAD')
        rows[coupler['upper_horn_bolt']]['seat'] = coupler['upper_horn_seat_mm']
        data['hardware'].append({'id': coupler['actor'], 'type': 'bolt', 'size': 3,
                                 'length': coupler['m3_length_mm'], 'axis': coupler['m3_axis'],
                                 'seat': coupler['m3_seat_mm'], 'phase': 0})
        spec.append(coupler['hardware_spec'])
    return data, spec


def yaw_driver_adjustment(source, world):
    import FreeCAD as App

    from build_b21_fasteners import detached_shape
    from build_b23_yaw_shim import verify_access

    cad_sha = world.layout['source_sha256']
    if source is None or sha256(source.read_bytes()).hexdigest() != cad_sha:
        return {'status': 'unknown', 'reason': 'Missing exact native CAD inputs'}
    expected = world.layout['motion_geometry']['yaw_inner_race_shim']['driver_access']['tool_rows']
    doc = App.openDocument(str(source.resolve()))
    try:
        cup = detached_shape(doc.Part000)
        actual = verify_access(doc, cup, cup)
    finally:
        App.closeDocument(doc.Name)
    rows = actual['tool_rows']
    passed = len(rows) == len(expected) == 12 and all(row['minimum_driver_gap_mm'] >= .2 for row in rows)
    return {'status': 'pass' if passed else 'fail', 'cad_sha256': cad_sha,
            'tool_rows': rows, 'free_length_mm': actual['straight_tool_free_length_mm']}


def check_hatch_wires(world, inputs, native, added_base):
    """Test the measured-design wire centerlines at the six supported hatch positions."""
    import trimesh

    from check_b22_harness import CUT_LENGTHS, WIRE_DATA
    from wiring_check import Cable, Scene, discrete_bend, read
    from wiring_motion import matrices

    if inputs is None:
        return {'status': 'unknown', 'reason': 'Missing hatch service cable centerlines'}
    wiring = read(WIRE_DATA)
    diameters = {entry['id']: entry['diameter'] for entry in wiring['routes']}
    lengths = read(CUT_LENGTHS)
    required = {name for name in lengths if name.startswith('motor')} | {'J1+', 'J1-', 'J6-branch', 'fuse-in'}
    hatch_starts = {name for name in required if name.startswith(('motor1-', 'motor2-', 'motor3-', 'motor5-'))}
    hatch_starts |= {'J6-branch'}
    hatch_starts -= {'motor3-data'}
    hatch_ends = {'J1+', 'J1-'}
    scene = Scene.__new__(Scene)
    scene.groups = {}
    solids = {'added_base_cages': added_base}
    solids.update((key, shape) for key, shape in native.items() if key.startswith('ServiceHatchNutKeeper'))
    for name, shape in solids.items():
        vertices, faces = shape.tessellate(.045)
        scene.add(name, 'fixed', trimesh.Trimesh(np.array([list(point) for point in vertices]), faces))
    rows, neutral = [], {}
    for drop in HATCH_DROPS:
        path = inputs/f'wires-0-0-0-{drop}.npz'
        motion = matrices(world.layout, 0., 0., 0., float(drop), 0.)
        with np.load(path) as routes:
            if not required <= set(routes.files):
                raise ValueError(f'Incomplete hatch harness at {drop} mm')
            contacts = []
            endpoint_error = length_error = 0.
            for name in sorted(required):
                points = routes[name]
                if points.ndim != 2 or points.shape[1] != 3 or len(points) < 3 or not np.isfinite(points).all():
                    raise ValueError(f'Invalid cable path for {name} at {drop} mm')
                cable = Cable(name, points, diameters.get(name, 1.143), 0., *discrete_bend(points))
                endpoints = points[[0, -1]]
                if drop == 0:
                    neutral[name] = endpoints.copy()
                expected = neutral[name] - [[0, 0, drop*(name in hatch_starts)],
                                            [0, 0, drop*(name in hatch_ends)]]
                endpoint_error = max(endpoint_error, float(np.linalg.norm(endpoints-expected, axis=1).max()))
                if name in lengths:
                    length_error = max(length_error, abs(float(cable.arc[-1])-lengths[name]))
                contacts.extend(scene.hits(cable, motion, .25))
        rows.append({'drop_mm': drop, 'input_sha256': sha256(path.read_bytes()).hexdigest(),
                     'wire_count': len(required), 'contacts': contacts,
                     'max_endpoint_error_mm': endpoint_error, 'max_cut_length_error_mm': length_error})
    passed = all(not row['contacts'] and row['max_endpoint_error_mm'] < .01 and row['max_cut_length_error_mm'] < .01
                 for row in rows)
    return {'status': 'pass' if passed else 'fail', 'samples': rows,
            'solid_reserve_mm': .25, 'scope': 'Hatch-connected power/data centerlines against added cages and keepers. W31 stays on the base.'}


def check_service(source, world, installed, hardware, hatch_paths=None):
    """Replay service from the assembled CAD, leaving both sets of nuts installed."""
    import FreeCAD as App
    import Part
    from shapely.geometry import Polygon

    from build_b21_fasteners import detached_shape
    from build_service_hatch_nuts import CAGE_RADIUS_MM, KEEPER_OPENING_RADIUS_MM, KEEPER_PAD_RADIUS_MM, KEEPER_SEAT_Z, NUT_FLAT_MM
    from check_b19_assembly import sweep, sweep_shifted
    from check_b21_tools import translated_profile
    from primitives import cylinder
    from stock import hexagon

    if source is None or sha256(source.read_bytes()).hexdigest() != world.layout['source_sha256']:
        raise ValueError('B23 cover service requires the exact native source used for the world export')
    rear, bottom = service_metadata(world.layout)
    doc = App.openDocument(str(source.resolve()))
    try:
        # The tagged connector and wire representations are needed even though they are not rigid assembly pieces.
        cables = tuple(name for name in world.layout['world_motion']
                       if name.startswith(('HarnessWire', 'RearLead', 'CableTie', 'HubPlug', 'InputXT', 'SupplyXT')))
        names = tuple(dict.fromkeys((*installed, *cables)))
        native = {name: detached_shape(obj) for name in names if (obj := doc.getObject(name)) is not None
                  and obj.TypeId == 'Part::Feature'}

        up, down = (0., 0., 1.), (0., 0., -1.)
        parked_z = rear['parked_bottom_z_mm']
        rim_z = rear['parking_rim_z_mm']
        floor = native['CableSaddle']
        base = native['Part000']
        wrench = next(row for row in hardware if row['id'] == 'cableSpanner')
        profile = [[np.sign(x)*6.5 if abs(x) > 6.5 else x, y] for x, y in wrench['profile']]
        travel = 30.
        wrench_swept = translated_profile(Polygon(profile), travel)
        wrench_z = rim_z+.35
        epsilon = 1e-5

        def clashes(envelope):
            bounds = envelope.BoundBox
            return {name: amount for name, shape in native.items() if bounds.intersect(shape.BoundBox)
                    and (amount := envelope.common(shape).Volume) > epsilon}

        def extrusion(profile, xyz, height):
            x, y, z = xyz
            rim = [App.Vector(x+a, y+b, z) for a, b in profile.exterior.coords]
            return Part.Face(Part.makePolygon(rim)).extrude(App.Vector(0, 0, height))

        def bolt_envelope(name, lift, reserve=.10):
            _, length, seat, axis = world.neutral_screw(name)
            seat, axis = np.asarray(seat), np.asarray(axis)
            outer = seat-axis*lift
            head = cylinder(2.78+reserve, 3.+lift, outer-3.*axis, axis)
            shaft = cylinder(1.50+reserve, length+lift, outer, axis)
            return head.fuse(shaft), [seat.tolist(), outer.tolist()]

        def key_envelope(name, reach=35.):
            _, _, seat, axis = world.neutral_screw(name)
            seat, axis = np.asarray(seat), np.asarray(axis)
            return cylinder(1.50, reach, seat-3.*axis, -axis)

        def parked_barriers(x, y):
            nut = hexagon(5.25, 2.15, (x, y, parked_z))
            support = floor.common(nut.translated(App.Vector(0, 0, -.1))).Volume
            barriers = []
            for angle in np.arange(8)*np.pi/4:
                direction = App.Vector(float(np.cos(angle)), float(np.sin(angle)), 0)
                barriers.append(next((i*.05 for i in range(1, 17)
                                      if floor.common(nut.translated(direction*i*.05)).Volume > epsilon), None))
            return support, barriers

        rear_rows = []
        tool_routes = {}
        hexangles = np.arange(6)*np.pi/3 + np.pi/6
        large_nut = Polygon(np.column_stack((np.cos(hexangles), np.sin(hexangles)))*5.65/np.sqrt(3.))
        entry_profile = translated_profile(large_nut, 24.)
        for index, (x, y, z) in enumerate(rear['bolt_seats_mm']):
            name, nut = f'cableBolt{index}', f'cableNut{index}'
            _, _, stock_seat, axis = world.neutral_screw(name)
            nut_seat = np.asarray(world.rows[nut]['seat'])
            if not np.allclose(stock_seat, (x, y, z)) or axis != down or not np.allclose(nut_seat[:2], (x, y)):
                raise ValueError(f'{name} does not match the B23 native rear service station')
            wrench_seat = [x, y, wrench_z]
            blade = extrusion(wrench_swept, wrench_seat, wrench['thickness'])
            bolt, bolt_path = bolt_envelope(name, 20.)
            key = key_envelope(name)
            tight_nut = hexagon(5.5, 2.4, tuple(nut_seat))
            nut_lift = nut_seat[2]-parked_z
            nut_sweep = hexagon(5.5, 2.4+nut_lift, (x, y, parked_z))
            expanded_drop = hexagon(5.65, 2.5+nut_lift-.22, (x, y, parked_z))
            entry = extrusion(entry_profile, (x, y, parked_z+3.55), 2.50)
            entry_volume = floor.common(entry).Volume
            support, barriers = parked_barriers(x, y)
            shaft_engagement = parked_z+2.15-(z-rear['bolt_length_mm'])
            collisions = {'wrench': clashes(blade), 'bolt': clashes(bolt), 'key': clashes(key),
                          'nut': clashes(nut_sweep), 'nut_radial_reserve': clashes(expanded_drop)}
            wrench_nut = blade.common(tight_nut).Volume
            wrench_key = blade.common(key).Volume
            ok = (not any(collisions.values()) and max(entry_volume, wrench_nut, wrench_key) <= epsilon
                  and support >= .5 and all(barrier is not None for barrier in barriers) and shaft_engagement >= 1.5)
            rear_rows.append({'status': 'pass' if ok else 'fail', 'bolt': name, 'nut': nut,
                              'parked_offset_mm': [0., 0., -float(nut_lift)], 'bolt_path_mm': bolt_path,
                              'spanner_path_mm': [wrench_seat, [x, y+travel, wrench_z]], 'collisions_mm3': collisions,
                              'nut_entry_overlap_mm3': entry_volume, 'wrench_nut_overlap_mm3': wrench_nut,
                              'wrench_key_overlap_mm3': wrench_key, 'parking_support_sample_mm3': support,
                              'horizontal_barriers_mm': barriers, 'parked_start_engagement_mm': shaft_engagement})
            tool_routes[nut] = {'status': 'pass' if ok else 'fail', 'tool': 'spanner',
                                'axis': list(up), 'outward': [0., 1., 0.], 'seat_mm': wrench_seat,
                                'travel_mm': travel, 'head_width_mm': 13., 'thickness_mm': wrench['thickness'],
                                'profile_mm': profile}

        lower_rows = []
        for index in range(4):
            name, nut = f'hatchBolt{index}', f'hatchNut{index}'
            x, y, z = world.rows[nut]['seat']
            cap_name = min(bottom, key=lambda cap: abs(cap['seat_mm'][0]-x))['keeper']
            cap = native[cap_name]
            shell = cylinder(CAGE_RADIUS_MM, KEEPER_SEAT_Z-z, (x, y, z)).cut(
                hexagon(NUT_FLAT_MM, KEEPER_SEAT_Z-z, (x, y, z)))
            roof = cylinder(KEEPER_PAD_RADIUS_MM-.05, .14, (x, y, KEEPER_SEAT_Z+.02)).cut(
                cylinder(KEEPER_OPENING_RADIUS_MM, .2, (x, y, KEEPER_SEAT_Z)))
            floor_ring = cylinder(3.5, .15, (x, y, z-.18)).cut(cylinder(1.85, .20, (x, y, z-.2)))
            missing = {'nut_wall': shell.cut(base).Volume, 'roof_ring': roof.cut(cap).Volume,
                       'floor_ring': floor_ring.cut(base).Volume}
            fit = max(base.common(hexagon(5.5, 19.4, (x+dx, y+dy, z))).Volume
                      for dx, dy in product((-.10, 0., .10), repeat=2))
            bolt, bolt_path = bolt_envelope(name, 15.)
            hits = {'bolt': clashes(bolt), 'key': clashes(key_envelope(name))}
            ok = not any(hits.values()) and max(*missing.values(), fit) <= epsilon
            lower_rows.append({'status': 'pass' if ok else 'fail', 'bolt': name, 'nut': nut,
                               'keeper': cap_name, 'bolt_path_mm': bolt_path, 'collisions_mm3': hits,
                               'capture_missing_mm3': missing, 'max_nut_entry_overlap_mm3': fit,
                               'vertical_nut_float_mm': KEEPER_SEAT_Z-z-2.40,
                               'nut_entry_transverse_error_per_axis_mm': .10})

        rear_out = (0., 0., 25.)
        rear_names = {entry[key] for entry in rear_rows for key in ('bolt', 'nut')}
        rear_cover_hits = sweep(world, ['CableGate'], [name for name in names if name not in rear_names | {'CableGate'}], rear_out)
        lower_out = (0., 0., -30.)
        release_out = (0., 0., -65.)
        hatch = [name for name in names if world.layout['world_motion'].get(name) == 'hatch'
                 and not name.startswith('HubRearClearance')]
        hatch.extend(name for name in names if name.startswith(('hubNut', 'hubBolt')))
        lower_bolts = {entry['bolt'] for entry in lower_rows}
        lower_fixed = [name for name in names if name not in set(hatch) | lower_bolts
                       and not name.startswith(('HarnessWire', 'HubRearClearance'))]
        lower_cover_hits = sweep(world, hatch, lower_fixed, lower_out)
        hatch_after_unplug = [name for name in hatch if not name.startswith('HubPlug')]
        lower_cover_hits.update(sweep_shifted(world, hatch_after_unplug, lower_fixed, np.subtract(release_out, lower_out), lower_out))
        original = App.openDocument(str(B22_NATIVE))
        try:
            hatch_wires = check_hatch_wires(world, hatch_paths, native, base.cut(detached_shape(original.Part000)))
        finally:
            App.closeDocument(original.Name)
        result = {}
        for stage, cover, path, rows, hits, mode in (
                ('rear-cover-bolts', ['CableGate'], rear_out, rear_rows, rear_cover_hits, 'upright'),
                ('hatch-bolts', hatch, lower_out, lower_rows, lower_cover_hits, 'supported lowering')):
            passed = not hits and all(row['status'] == 'pass' for row in rows)
            result[stage] = {'status': 'pass' if passed else 'fail', 'orientation': mode,
                             'cad_sha256': world.layout['source_sha256'], 'bolt_radial_reserve_mm': .10,
                             'cover': cover, 'cover_path_mm': [[0., 0., 0.], list(path)], 'fasteners': rows,
                             'cover_collisions': [dict(parts=list(pair), **hit) for pair, hit in hits.items()],
                             'scope': 'Reversible CAD paths, stock hardware and nominal visible wires. '
                                      'P08 checks physical thread start, settling, access and the live harness.'}
        result['rear-cover-bolts']['tool_access'] = tool_routes
        hatch_result = result['hatch-bolts']
        hatch_result['wire_clearance'] = hatch_wires
        if hatch_result['status'] == 'pass' and hatch_wires['status'] != 'pass':
            hatch_result['status'] = hatch_wires['status']
        hatch_result['after_unplug_path_mm'] = [list(lower_out), list(release_out)]
        return result
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for name in ('layout', 'hardware', 'spec', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    data, spec = prepare_hardware(*(json.loads(path.read_text())
                                    for path in (args.layout, args.hardware, args.spec)))
    for name, payload in (('hardware.json', data), ('hardware-spec.json', spec)):
        (args.output/name).write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
