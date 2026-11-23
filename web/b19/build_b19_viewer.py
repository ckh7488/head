"""Build the checked assembly walkthrough or the illustrated B25 preview.

Checked walkthroughs use the assembly checker and its report. The B25 preview
uses its illustration plan and shows indicative tool positions.

    python web/b19/build_b19_viewer.py build/b19-cad build/hardware.json \
        mechanical/revisions/b19/print/hardware-spec.json mechanical/revisions/b19/assembly-check.json
"""
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
import json
import re
import sys

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / 'mechanical' / 'physics'))
import check_b19_assembly as C  # noqa: E402
from render_b19_assembly import BENCH, SECTIONS, note_text  # noqa: E402

COLORS = {
    'bone': (220, 204, 177), 'jaw': (214, 198, 169), 'graphite': (56, 66, 70),
    'shroud': (37, 44, 47), 'steel': (150, 162, 170), 'link': (164, 117, 65),
    'frame': (93, 142, 130), 'gear': (44, 50, 56), 'eye': (228, 232, 218),
    'iris': (77, 123, 103), 'pupil': (12, 17, 17), 'glass': (29, 41, 50),
    'pcb': (48, 106, 76), 'connector': (194, 196, 180), 'power': (225, 171, 51),
    'terminal': (85, 145, 107), 'fuse': (181, 92, 67), 'capacitor': (112, 114, 117),
    'b19': (226, 92, 60), 'tool': (16, 144, 125),
    'feed-wire': (198, 57, 48), 'return-wire': (52, 56, 68), 'camera-wire': (43, 157, 179),
}
FACE_LIMIT = {'bone': 30000, 'jaw': 12000, 'eye': 8000}
BLOCKED = re.compile(r'(.+): stated approach \((.+?)\) is blocked; \((.+?)\) is clear')
REAR_WIRING = ('RearLead', 'CableTie', 'InputXT', 'SupplyXT30', 'CameraUSB', 'ControlUSB')
GUARD_PANELS = {'GuardFront', 'GuardLeft', 'GuardRight', 'GuardRearTop', 'GuardRearBottom', 'GuardRoof'}
FASTENER_OWNERS = {
    'rear-guide-bolts': 'CableSaddle', 'rear-cover-service-nuts': 'CableSaddle',
    'rear-cover-bolts': 'CableGate', 'hub-bolts': 'HubHolder',
    'hatch-service-nuts': 'Part000', 'hatch-bolts': 'Part000',
    'c3-carrier-bolts': 'Part071', 'openrb-bolts': 'Part072', 'openrb-carrier-bolts': 'Part072',
    'keeper-bolts': 'Part001', 'bearing-seat-bolts': 'Part001',
    'rotor-studs': 'Part007', 'rotor-horn': 'Part007', 'base-deck-bolts': 'Part002',
    'yoke-bolts': 'Part011', 'pitch-horn-bolts': 'Part016', 'blink-rail-bolts': 'Part063',
    'eye-pitch-case-screws': 'Part041', 'eye-pitch-plate-screws': 'Part042',
    'blink-case-screws': 'Part045', 'blink-motor-bolts': 'Part046', 'blink-clamps': 'Part054',
    'eye-yaw-case-screws': 'Part038', 'jaw-motor-screws': 'Jaw_XL330_M288_Jaw', 'mast-nuts': 'Part010',
}
B23_PREPARATION = {
    'eye-cradle': '안구를 넣기 전에 서포트를 빼고 긴 Ø2.2 mm 드릴을 손으로 돌려 위·아래 홀 한 쌍씩을 같은 축으로 마감합니다.',
    'yaw-stop-pads': '회전판 돌기가 닿을 면을 손끝으로 밀어 왼쪽은 앞 왼쪽, 오른쪽은 앞 오른쪽 키 벽에 댄 채 공용 M3 너트를 조입니다.',
}
B24_ASSEMBLY_VIEWS = [
    {'id': 'eye-pitch-bearings', 'label': '눈 상하 베어링 정렬', 'stage': 'eye-bearing-align'},
    {'id': 'neck-pitch-coupling', 'label': '목 상하 축 체결', 'stage': 'pitch-drive-lock'},
]


def numbers(text):
    return [float(v) for v in text.split(',')]


def finish_of(name, manifest):
    if name in manifest:
        return manifest[name]
    return 'steel'


def load_wires(source, cad_hash):
    if source is None:
        return []
    if sha256(source.read_bytes()).hexdigest() != cad_hash:
        raise ValueError('Cable paths and CAD export use different revisions')

    import FreeCAD as App

    doc = App.openDocument(str(source.resolve()))
    try:
        wires = []
        for obj in doc.Objects:
            if not obj.Name.startswith('HarnessWire') or not hasattr(obj, 'JacketDiameter'):
                continue
            shape = obj.Shape.copy()
            shape.Placement = obj.getGlobalPlacement()
            points = [[round(float(coord), 3) for coord in vertex.Point] for vertex in shape.Vertexes]
            diameter = float(obj.JacketDiameter)
            if len(points) < 2 or diameter <= 0:
                raise ValueError(f'{obj.Label} must have a path and a positive diameter')
            name = obj.Label.split('  ·  ', 1)[0]
            color = 0x5cdef1 if name.startswith('USB') else 0xf0e5b0
            if name == 'fuse-in' or name.endswith(('-power', '+')):
                color = 0xef5447
            elif name.endswith(('-return', '-')):
                color = 0x485463
            wires.append({'id': obj.Name, 'label': obj.Label, 'diameter': diameter,
                          'points': points, 'color': color})
        if not wires:
            raise ValueError('Source CAD has no internal cable paths')
        return wires
    finally:
        App.closeDocument(doc.Name)


def load_guard(source, report, cad_hash):
    if source is None and report is None:
        return {}, None
    if source is None or report is None:
        raise ValueError('Supply both the guard CAD and its check report')
    checks = json.loads(report.read_text(encoding='utf-8'))
    guard_hash = sha256(source.read_bytes()).hexdigest()
    if (checks.get('status') != 'pass' or checks.get('head_cad_sha256') != cad_hash
            or checks.get('guard_cad_sha256') != guard_hash):
        raise ValueError('Guard report does not qualify this head and guard CAD pair')

    import FreeCAD as App
    from export_cad import tessellate, world_shape

    parts = {}
    doc = App.openDocument(str(source.resolve()))
    try:
        for obj in doc.Objects:
            if obj.TypeId != 'Part::Feature' or not obj.Name.startswith('Guard'):
                continue
            vertices, faces = tessellate(world_shape(obj)).Topology
            mesh = trimesh.Trimesh(vertices=[list(v) for v in vertices], faces=faces)
            if not len(mesh.faces):
                raise ValueError(f'Guard part has no visible mesh: {obj.Name}')
            parts[obj.Name] = mesh
    finally:
        App.closeDocument(doc.Name)
    if not GUARD_PANELS <= parts.keys():
        raise ValueError('Guard CAD is missing an installed panel')
    return parts, guard_hash


def assembly_motion(layout, hardware, stock, steps, revision):
    motion = {row['id']: row['motion'] for row in hardware if 'motion' in row and not row.get('tool')}
    motion.update({row['name']: row['motion'] for row in stock})
    motion.update(layout['world_motion'])
    if revision in ('B22', 'B23', 'B24', 'B25'):
        for step in steps:
            owner = FASTENER_OWNERS.get(step['id'])
            if owner is None:
                continue
            for move in step['moves']:
                for actor in move['ids']:
                    motion.setdefault(actor, motion[owner])
    return motion


def load_wire_states(report, layout, actors, world_motion, wires):
    if report is None:
        return []
    from wiring_motion import matrices

    data = json.loads(report.read_text(encoding='utf-8'))
    if (data.get('cad_sha256') != layout['source_sha256']
            or data.get('checked_geometry_cad_sha256') != layout['source_sha256']):
        raise ValueError('Camera wire states and assembly use different CAD revisions')
    if not re.fullmatch(r'[0-9a-f]{64}', data.get('routes_sha256', '')):
        raise ValueError('Camera wire states do not identify the checked route archive')
    (wire,) = [wire for wire in wires if wire['label'].split('  ·  ', 1)[0] == 'USB-Camera']
    if not np.isclose(data['diameter_mm'], wire['diameter'], atol=.001, rtol=0):
        raise ValueError('Camera wire states use a different jacket diameter from CAD')
    missing = set(actors) - world_motion.keys()
    if missing:
        raise ValueError(f'Installed actors without a motion group: {sorted(missing)}')
    wire_names = {wire['label'].split('  ·  ', 1)[0]: wire for wire in wires}
    diameters = data.get('wireDiametersMm', {})
    states = []
    rig = layout['motion_geometry']
    yaw_limits = rig.get('yaw_limit', {}).get('nominal_stop_deg')
    pitch_stops = sorted(stop['nominal_deg'] for stop in rig['pitch_stop']['stops']) if 'pitch_coupler' in rig else None
    for row in data['states']:
        degrees, points = np.asarray(row['pose_deg'], float), np.asarray(row['points'], float)
        if (degrees.shape != (5,) or points.ndim != 2 or points.shape[1] != 3 or len(points) < 2
                or not np.isfinite(degrees).all() or not np.isfinite(points).all()):
            raise ValueError(f'Invalid camera geometry in {row["id"]}')
        if yaw_limits is not None and not yaw_limits[0] < degrees[0] < yaw_limits[1]:
            raise ValueError(f'Wire comparison is past a mechanical yaw stop: {row["id"]}')
        if pitch_stops and not pitch_stops[0] < degrees[1] < pitch_stops[-1]:
            raise ValueError(f'Wire comparison is past a mechanical pitch stop: {row["id"]}')
        recorded = row.get('wirePoints', {})
        show_all = (len(wire_names) == len(wires) and wire_names.keys() <= recorded.keys()
                    and all(np.isclose(diameters.get(name, 0), model['diameter'], atol=.001, rtol=0)
                            for name, model in wire_names.items()))
        paths = {wire['id']: points.tolist()}
        if show_all:
            for name, model in wire_names.items():
                path = np.asarray(recorded[name], float)
                if path.ndim != 2 or path.shape[1] != 3 or len(path) < 2 or not np.isfinite(path).all():
                    raise ValueError(f'Invalid wire geometry for {name} in {row["id"]}')
                paths[model['id']] = path.tolist()
        transforms = matrices(layout, *degrees)
        poses = {}
        for actor in actors:
            pose = transforms[world_motion[actor]]
            if not np.allclose(pose, np.eye(4)):
                poses[actor] = pose.tolist()
        states.append({'id': row['id'], 'label': row['label'], 'poseDegrees': degrees.tolist(),
                       'actorPoses': poses, 'wirePoints': paths, 'fullHarness': show_all})
    if not states or len({state['id'] for state in states}) != len(states):
        raise ValueError('Camera wire state IDs must be unique')
    return states


def checked_tools(row, world, hardware, tools, phases):
    from shapely.geometry import Polygon

    from check_b21_tools import SOCKET_DEPTH_MM, SOCKET_RADII, arm_frame

    choices, by_nut = [], {}
    for name, route in row.get('tool_access', {}).items():
        if route['status'] != 'pass':
            continue
        stock = world.rows[name]
        axis, outward, seat = [np.asarray(route[key], float) for key in ('axis', 'outward', 'seat_mm')]
        phase = route.get('nut_rotation_deg')
        if phase is not None and phases.setdefault(name, phase) != phase:
            raise ValueError(f'Conflicting installed orientations for {name}')
        if route['tool'] == 'spanner':
            profile = next(value for value in hardware if value.get('tool') and value['type'] == 'spanner'
                           and value['size'] == stock['size'])
            polygon = Polygon(route.get('profile_mm', profile['profile']))
            mesh = trimesh.creation.extrude_polygon(polygon, route.get('thickness_mm', profile['thickness']))
            mesh.apply_transform(arm_frame(axis, outward, seat))
        elif route['tool'] == 'socket':
            outer, inner = SOCKET_RADII[stock['size']]
            length = route['body_length_mm']
            mesh = trimesh.creation.revolve([(inner, 0), (outer, 0), (outer, length), (0, length),
                                               (0, SOCKET_DEPTH_MM), (inner, SOCKET_DEPTH_MM),
                                               (inner, 0)], sections=48)
            mesh.apply_transform(trimesh.geometry.align_vectors([0., 0., 1.], outward))
            mesh.apply_translation(seat)
        else:
            raise ValueError(f'Unsupported qualified tool: {route["tool"]}')
        native_path = route.get('waypoints_mm')
        points = np.asarray(native_path if native_path else [seat + outward*route['travel_mm'], seat])
        if not np.allclose(points[-1], seat, atol=.001):
            raise ValueError(f'Tool path ends outside the reported seat for {name}')
        mesh_id = f'tool-{row["id"]}-{name}'
        tools[mesh_id] = mesh
        by_nut[name] = {'id': mesh_id, 'nut': name, 'kind': route['tool'], 'size': stock['size'],
                        'seat': seat.tolist(), 'path': (points-seat).round(3).tolist()}
        choices.append([by_nut[name]])
    for route in row.get('paired_tool_access', {}).values():
        if route['status'] == 'pass':
            choices.append([by_nut[name] for name in route['insertion_order']])
    for pair, route in row.get('paired_driver_access', {}).items():
        if route['status'] != 'pass':
            continue
        nut, bolt = pair.split('/')
        reach = row['driver_access'][bolt]['straight_key_reach_mm']
        size, _, seat, axis = world.screw(bolt)
        axis = np.asarray(axis, float)
        tip = np.asarray(seat)-axis*(C.HEAD[size][1]+.05)
        mesh_id = f'tool-{row["id"]}-{bolt}-axis'
        tools[mesh_id] = C.cylinder(C.B21_KEY_RADII[size], reach, tip, -axis)
        choices.append([by_nut[nut], {'id': mesh_id, 'nut': bolt, 'kind': 'driver-axis', 'size': size,
                                      'seat': tip.tolist(), 'path': [[0, 0, 0], [0, 0, 0]]}])
    if (yaw := row.get('yaw_driver_adjustment')) and yaw['status'] == 'pass':
        front = min(route['y_mm'] for route in yaw['tool_rows'])
        for route in yaw['tool_rows']:
            if route['z_adjustment_mm'] != 0:
                continue
            left = route['side'] < 0
            near = route['y_mm'] == front
            side = '왼쪽' if left else '오른쪽'
            station = '앞' if near else '뒤'
            tip = route['seat_mm']
            name = f'tool-yaw-{"left" if left else "right"}-{"front" if near else "rear"}'
            tools[name] = C.cylinder(route['radius_mm'], yaw['free_length_mm'], tip, route['outward'])
            choices.append([{'id': name, 'nut': f'{side} {station} · 2 mm 볼 육각렌치',
                             'kind': 'driver-axis', 'size': 2, 'seat': tip,
                             'path': [[0, 0, 0], [0, 0, 0]]}])
    if (key := row.get('pitch_drive_key')) and key['status'] == 'pass':
        elbow = np.asarray(key['elbow_mm'], float)
        tip = elbow - [0., 0., key['short_leg_mm']]
        radius = key['key_across_flats_mm'] / np.sqrt(3.)
        angle = np.radians(key['handle_direction_deg'])
        name = 'tool-neck-pitch-key'
        tools[name] = trimesh.util.concatenate([
            C.cylinder(radius, key['short_leg_mm'], tip, (0., 0., 1.)),
            C.cylinder(radius, key['long_leg_mm'], elbow, (np.cos(angle), np.sin(angle), 0.)),
        ])
        choices.append([{'id': name, 'nut': '목 축 M3 · 2.5 mm 육각렌치',
                         'kind': 'driver-axis', 'size': key['key_across_flats_mm'], 'seat': tip.tolist(),
                         'path': [[0., 0., key['entry_from_above_mm']], [0., 0., 0.]]}])
    return choices


def load_stop_locations(report, cad_hash, steps, world_motion):
    if report is None:
        return []
    data = json.loads(report.read_text(encoding='utf-8'))
    if data.get('cad_sha256') != cad_hash:
        raise ValueError('Stop locations and assembly use different CAD revisions')
    if data.get('status') != 'pass' or data.get('issues') or not data.get('locations'):
        raise ValueError('Stop-location report did not pass')
    visible = {step['id']: set(step['fixed']) | {part for move in step['moves'] for part in move['ids']}
               for step in steps}
    locations, seen = [], set()
    for row in data['locations']:
        sid, label, actors = row['id'], row['label'], row['actors']
        if (row.get('status') != 'pass' or not sid or sid in seen or not label
                or len(actors) != 2 or actors[0] == actors[1]):
            raise ValueError(f'Invalid stop location {sid!r}')
        seen.add(sid)
        center = np.asarray(row['center_mm'], float)
        if center.shape != (3,) or not np.isfinite(center).all():
            raise ValueError(f'Invalid stop center for {sid}')
        stage = row.get('stage')
        if stage is None:
            stage = next((name for name, ids in visible.items() if set(actors) <= ids), None)
        if not set(actors) <= visible.get(stage, set()):
            raise ValueError(f'Stop {sid} has hidden contact parts in {stage!r}')
        angle = row['first_contact_deg']
        if type(angle) not in (int, float) or not np.isfinite(angle):
            raise ValueError(f'Invalid measured stop angle for {sid}')
        location = {'id': sid, 'label': label, 'stage': stage, 'actors': actors,
                    'center': center.tolist(), 'firstContactDegrees': angle}
        if 'head_from_neutral' in row:
            from check_b22_neck import rigid_group

            groups = {name: rigid_group(world_motion[name]) for name in visible[stage] if name in world_motion}
            moving = sorted(name for name, group in groups.items() if group == 'head')
            if actors[0] not in groups or actors[0] in moving or actors[1] not in moving:
                raise ValueError(f'Stop {sid} contact actors are assigned to the wrong motion groups')
            contact_pose = {'head': {'matrix': row['head_from_neutral'], 'parts': moving}}
            if 'anchor_from_neutral' in row:
                anchor_group = groups[actors[0]]
                anchor = sorted(name for name, group in groups.items() if group == anchor_group)
                contact_pose['anchor'] = {'matrix': row['anchor_from_neutral'], 'parts': anchor}
            for pose in contact_pose.values():
                matrix = np.asarray(pose['matrix'], float)
                if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
                    raise ValueError(f'Invalid witnessed pose for {sid}')
                pose['matrix'] = matrix.tolist()
            location['contactPose'] = contact_pose
        locations.append(location)
    return locations


def build(cad, hardware, spec, report, output, revision='B19', assembly_cad=None, stop_report=None,
          guard_cad=None, guard_report=None, wire_states=None, preview=False):
    data = json.loads(hardware.read_text())
    stock = json.loads(spec.read_text())
    world = C.World(cad, data['hardware'], stock)
    layout = json.loads((cad/'cad_parts.json').read_text())
    service_covers = revision in ('B23', 'B24', 'B25')
    rig = layout['motion_geometry']
    if revision in ('B24', 'B25') and (not rig.get('pitch_coupler') or not rig.get('eye_pitch_bearings')):
        raise ValueError('Current CAD must include both revised pitch axes')
    world.layout = layout
    illustration = report is None
    if illustration:
        if revision != 'B25' or not preview or assembly_cad is None:
            raise ValueError('Report-free rendering requires B25 --preview and the exact --assembly-cad')
        import b25_preview as B25

        catalog, heat_screws, heat_retainers = B25.setup(layout, world)
        plan = B25.plan(layout, heat_screws, heat_retainers, world)
        checked = [dict(id=step['id'], context=step['ctx'], text=step['text'], notes=[], issues=[],
                        **{key: step[key] for key in ('actor_offsets', 'blink_deg') if key in step}) for step in plan]
        checked[0].update(cad_sha256=layout['source_sha256'], plan_sha256=C.plan_hash(plan))
    else:
        plan = C.assembly_plan(revision.lower(), layout)
        checked = json.loads(report.read_text())
    if [(row['id'], row['context'], row['text']) for row in checked] != [
            (step['id'], step['ctx'], step['text']) for step in plan]:
        raise ValueError('Assembly report does not match the current assembly plan')
    manifest = {p['cad_id']: p['finish'] for p in json.loads((ROOT/'web/assets/assembly.json').read_text())['parts']}
    if revision != 'B19' and checked[0].get('cad_sha256') != layout['source_sha256']:
        raise ValueError('Assembly report and CAD export use different revisions')
    if service_covers:
        if layout['world_sha256'].keys() != layout['world_motion'].keys():
            raise ValueError('CAD world export has incomplete mesh provenance')
        for name, digest in layout['world_sha256'].items():
            if sha256((cad/'world'/f'{name}.stl').read_bytes()).hexdigest() != digest:
                raise ValueError(f'CAD world export mesh changed after validation: {name}')
    has_qualified_tools = revision in ('B21', 'B22') or service_covers
    if has_qualified_tools and checked[0].get('plan_sha256') != C.plan_hash(plan):
        raise ValueError(f'{revision} assembly plan differs from the one checked')
    labels = {p['name']: p.get('label') or '' for p in layout.get('parts', [])}
    keeper_names = set()
    native_screws = set()
    if service_covers:
        for cap in rig['bottom_board_service_nuts']:
            keeper_names.add(cap['keeper'])
            native_screws.add(cap['screw'])
    if revision in ('B24', 'B25'):
        native_screws.add(rig['pitch_coupler']['actor'])
    b19_names = {item['name'] for item in stock} | {'PitchPinDowelLeft', 'PitchPinDowelRight'}
    rear_wiring = [name for name in layout['world_motion'] if name.startswith(REAR_WIRING)]
    hub_plugs = [name for name in layout['world_motion'] if name.startswith('HubPlug')]
    wires = load_wires(assembly_cad, layout['source_sha256'])
    if illustration:
        rear_wiring = [name for name in rear_wiring if name not in ('InputXT60', 'InputXT60Mate')]
        wires = [wire for wire in wires if not wire['label'].startswith('Archived camera route')]
        native_screws.update(layout['world_motion'])
        b19_names.update(name for name in native_screws if name.endswith('Insert') or 'Screw' in name
                         or name.startswith(('HubBolt', 'A4InletBolt', 'A4StationFastener')))
    camera_wires = [wire['id'] for wire in wires if wire['label'].startswith('USB-Camera  ·  ')]

    installed, used, steps = {}, set(), []
    tools, phases, feed_models = {}, {}, {}
    number, last_text, sub = 0, '', 0
    for st, row in zip(plan, checked, strict=True):
        if st.get('blink_deg') != row.get('blink_deg'):
            raise ValueError(f'Assembly pose differs from the checked pose for {st["id"]}')
        offsets = st.get('actor_offsets', {})
        if json.dumps(offsets, sort_keys=True) != json.dumps(row.get('actor_offsets', {}), sort_keys=True):
            raise ValueError(f'Assembly offsets differ from the checked offsets for {st["id"]}')
        world.blink_pose = st.get('blink_deg')
        for name, phase in st.get('set_nut_phases', {}).items():
            if phases.setdefault(name, phase) != phase:
                raise ValueError(f'Conflicting assembly orientation for {name}')
        ctx = installed.setdefault(st['ctx'], [])
        if st['id'] == 'rear-cover':
            ctx.extend(rear_wiring)
        elif st['id'] == 'head-on-base':
            ctx.extend(hub_plugs)
        alternatives = {}
        for note in row['notes']:
            match = BLOCKED.match(note)
            if match:
                alternatives[match.group(1).removesuffix(' assembly')] = numbers(match.group(3))
        fixed = list(ctx)
        moves = []
        for key in ('merge', 'merge2'):
            if key in st:
                other, offset = st[key]
                parts = installed.pop(other)
                offset = alternatives.get(other, offset)
                moves.append({'ids': parts, 'path': [list(map(float, offset)), [0, 0, 0]]})
                ctx.extend(parts)
        for key in ('place', 'place2', 'pins', 'pins2'):
            if key in st:
                parts, offset = st[key]
                offset = alternatives.get(', '.join(parts), offset)
                moves.append({'ids': list(parts), 'path': [list(map(float, offset)), [0, 0, 0]]})
                ctx.extend(parts)
        if 'path' in st:
            parts, points = st['path']
            moves.append({'ids': list(parts), 'path': [list(map(float, p)) for p in points]})
            ctx.extend(parts)
        for name,offset in st.get('insert_moves', []):
            moves.append({'ids': [name], 'path': [offset, [0, 0, 0]]})
            ctx.append(name)
        for key in ('nuts', 'nuts2'):
            if key in st:
                parts, offset = st[key]
                offset = alternatives.get(', '.join(parts), offset)
                moves.append({'ids': list(parts), 'path': [list(map(float, offset)), [0, 0, 0]]})
                ctx.extend(parts)
        for name in st.get('bolts', []):
            size, length, seat, axis = world.screw(name)
            moves.append({'ids': [name], 'path': [(-np.asarray(axis, float)*(length+3.)).round(2).tolist(), [0, 0, 0]]})
            ctx.append(name)
        notes = list(dict.fromkeys(note_text(n) for n in row['notes']))
        if service_covers and st['id'] in B23_PREPARATION:
            notes.insert(0, B23_PREPARATION[st['id']])
        if (key := row.get('pitch_drive_key')) and key['status'] == 'pass':
            notes.append(f'착좌한 2.5 mm 육각렌치의 회전 {key["swept_turn_deg"]:g}° 범위를 CAD에서 확인했습니다.')
        if (yaw := row.get('yaw_driver_adjustment')) and yaw['status'] == 'pass':
            closest = min(record['minimum_driver_gap_mm'] for record in yaw['tool_rows'])
            notes.append(f'네 공구 자리와 모터 높이 세 위치의 CAD 최소 여유 · {closest:.3f} mm')
        if front := row.get('front_link_clearance'):
            notes.append(f'앞 외장을 정면에서 넣을 때 링크 주변 CAD 여유 하한 · {front["continuous_lower_bound_mm"]:.3f} mm')
        service = row.get('service_access')
        if service and service['status'] != 'pass':
            if not preview:
                raise ValueError(f'Unqualified cover service path for {st["id"]}')
            notes.append('덮개를 내리는 경로의 배선과 공구 여유는 아직 검증 중입니다.')
            service = None
        if service:
            for fastener in service['fasteners']:
                nut, bolt = fastener['nut'], fastener['bolt']
                if nut not in fixed:
                    raise ValueError(f'Cover nut is missing before its screw is inserted: {nut}')
                screw_move = next(i for i, move in enumerate(moves) if move['ids'] == [bolt])
                positions = np.asarray(fastener['bolt_path_mm'], float)
                _, _, seat, _ = world.screw(bolt)
                if not np.allclose(positions[0], seat, atol=.001):
                    raise ValueError(f'Service path starts at the wrong screw seat: {bolt}')
                moves[screw_move]['path'] = (positions[::-1]-seat).round(3).tolist()
                parked = np.asarray(fastener.get('parked_offset_mm', [0, 0, 0]), float).round(3).tolist()
                if any(parked):
                    moves.insert(screw_move + 1, {'ids': [nut], 'path': [parked, [0, 0, 0]], 'mounted': True})
            notes.append('나사를 뺀 뒤 너트가 남는 덮개 경로를 CAD에서 확인했습니다.')
        if feed := st.get('camera_feed'):
            route = row['camera_feed']
            if any(route[key] != value for key, value in feed.items()):
                raise ValueError(f'Camera connector feed differs from the checked approach for {st["id"]}')
            actor = f'checked-plug-{st["id"]}'
            points = [route['start_mm'], route['end_mm']]
            if 'pull_end_mm' in route:
                points.append(route['pull_end_mm'])
            path = np.asarray(points, float)
            feed_models[actor] = trimesh.creation.box(extents=route['body_mm']).apply_translation(path[-1])
            moves.append({'ids': [actor], 'path': (path-path[-1]).tolist()})
            notes.append('작은 플러그의 검사 외곽을 표시합니다.')
            if route['status'] == 'pass':
                notes.append(f'공차 포함 CAD 최소 여유 · {route["minimum_clearance_mm"]:.3f} mm')
        if jig := st.get('eye_bearing_alignment'):
            diameter, length = jig['diameter_mm'], jig['length_mm']
            alignment = (dict(tool_diameter_mm=diameter, tool_length_mm=length,
                              route_offset_mm=jig['feed_offset_mm'], status='illustration') if illustration
                         else row['eye_bearing_alignment'])
            if ((alignment['tool_diameter_mm'], alignment['tool_length_mm']) != (diameter, length)
                    or not np.allclose(alignment['route_offset_mm'], jig['feed_offset_mm'])):
                raise ValueError('Eye-bearing alignment gauge does not match the checked route')
            if alignment['status'] in ('pass', 'illustration'):
                actor = 'checked-eye-bearing-alignment-gauge'
                y, z = jig['axis_yz_mm']
                feed_models[actor] = C.cylinder(diameter/2, length, (-length/2, y, z), (1., 0., 0.))
                offset = alignment['route_offset_mm']
                moves.append({'ids': [actor], 'path': [offset, [0., 0., 0.], offset], 'temporary': True})
                label = '정렬봉 위치' if illustration else '검사한 정렬봉'
                notes.append(f'{label} · 지름 {diameter:g} mm · 길이 {length:g} mm')
        if row['text']:
            number += 1
            label, last_text, sub = str(number), row['text'], 0
        else:
            sub += 1
            label = f'{number}-{sub + 1}'
        names = fixed + [name for move in moves if not move.get('mounted') for name in move['ids']]
        if len(names) != len(set(names)):
            raise ValueError(f'Duplicate parts in {st["id"]}')
        used.update(names)
        tool_paths = (B25.tools_for(st, world, tools, catalog) if illustration
                      else checked_tools(row, world, data['hardware'], tools, phases) if has_qualified_tools else [])
        poses = {name: matrix.tolist() for name in names if (matrix := world.blink_transform(name)) is not None}
        for name, offset in offsets.items():
            if name not in names or name in poses:
                raise ValueError(f'Invalid checked assembly offset for {name} in {st["id"]}')
            pose = np.eye(4)
            pose[:3, 3] = offset
            poses[name] = pose.tolist()
        guide_bench = illustration and st['ctx'] == B25.CABLE_GUIDE_BENCH
        steps.append({
            'id': st['id'], 'label': label,
            'section': '뒤 케이블 가이드' if guide_bench else SECTIONS[st['ctx']],
            'bench': guide_bench or st['ctx'] in BENCH,
            'text': st.get('preview_text') or row['text'] or last_text, 'continued': not row['text'],
            'notes': notes,
            'issues': row['issues'], 'fixed': fixed, 'moves': moves,
            'closedLids': bool(st.get('closed_lids')),
            'showWires': st['id'] == 'rear-skull' or (st['id'] == 'camera-route-set' and not illustration),
            **({'wireIds': camera_wires} if st['id'] == 'camera-route-set' and not illustration else {}),
            **({'toolPaths': tool_paths} if tool_paths else {}),
            **({'actorPoses': poses} if poses else {}),
            **({'blinkDegrees': st['blink_deg']} if 'blink_deg' in st else {}),
            **({'serviceChecked': True} if service else {}),
            **({'insertionClearance': row['insertion_clearance']} if 'insertion_clearance' in row else {}),
        })

    scene = trimesh.Scene()
    motion = assembly_motion(layout, data['hardware'], stock, steps, revision)
    stop_locations = load_stop_locations(stop_report, layout['source_sha256'], steps, motion)
    stop_actors = {actor for location in stop_locations for actor in location['actors']}
    guard, guard_hash = load_guard(guard_cad, guard_report, layout['source_sha256'])
    review = None
    states = []
    if guard or wire_states or service_covers:
        complete = steps[-1] if revision == 'B25' else next(step for step in steps if step['id'] == 'rear-skull')
        fixed = complete['fixed'] + [name for move in complete['moves'] for name in move['ids']] + sorted(guard)
        if len(fixed) != len(set(fixed)):
            raise ValueError('Duplicate part in the final view')
        review = dict(id='final-view', label='완료', section='조립 완료', fixed=fixed,
                      text='체결품과 배선이 있는 조립 상태입니다.', notes=[], issues=[], moves=[], showWires=True)
        if illustration:
            review.update(text='B25 완성 상태입니다. 외장을 숨기면 내부 체결품과 배선을 볼 수 있습니다.',
                          notes=['조립 움직임과 공구는 CAD 위치를 설명합니다. 출력 공차와 실물 조립은 가조립에서 확인합니다.'])
        motion.update(dict.fromkeys(guard, 'fixed'))
        states = load_wire_states(wire_states, layout, fixed, motion, wires)
    world.blink_pose = None
    materials = {name: trimesh.visual.material.PBRMaterial(
        name=name, baseColorFactor=np.array((*rgb, 255), dtype=np.uint8), roughnessFactor=.6,
        metallicFactor=.45 if name == 'steel' else 0.) for name, rgb in COLORS.items()}
    parts = {}
    for name in sorted(used):
        if illustration and name in catalog:
            mesh = B25.screw_model(*world.neutral_screw(name))
        elif name in native_screws:
            mesh = trimesh.load_mesh(world.world/f'{name}.stl')
        else:
            mesh = feed_models[name] if name in feed_models else world.mesh(name)
        if mesh is None:
            raise ValueError(f'Empty assembly mesh: {name}')
        mesh = mesh.copy()
        if phases.get(name):
            nut = world.rows[name]
            mesh.apply_transform(trimesh.transformations.rotation_matrix(
                np.radians(phases[name]), nut['axis'], nut['seat']))
        finish = ('frame' if name in keeper_names else 'b19' if name in b19_names else 'power' if name.startswith('RearLead')
                  else 'connector' if name in rear_wiring or name in hub_plugs else finish_of(name, manifest))
        if illustration:
            finish = B25.finish(name) or finish
        limit = FACE_LIMIT.get(finish, 4000)
        if name not in stop_actors and len(mesh.faces) > limit:
            # Decimation can tear closed parts; torn faces render as black patches.
            for target in [t for t in (limit, 2*limit) if t < len(mesh.faces)]:
                reduced = mesh.simplify_quadric_decimation(face_count=target)
                if reduced.is_watertight or not mesh.is_watertight:
                    break
            if reduced.is_watertight or not mesh.is_watertight or len(mesh.faces) > 40000:
                mesh = reduced
        mesh.visual = trimesh.visual.TextureVisuals(material=materials[finish])
        scene.add_geometry(mesh, node_name=name, geom_name=name)
        parts[name] = {'label': (B25.LABELS.get(name) if illustration else None) or labels.get(name, '') or name,
                       'b19': name in b19_names,
                       'center': mesh.bounds.mean(axis=0).round(2).tolist(),
                       'size': float(np.linalg.norm(mesh.extents).round(2))}
    for name, mesh in tools.items():
        mesh.visual = trimesh.visual.TextureVisuals(material=materials['tool'])
        scene.add_geometry(mesh, node_name=name, geom_name=name)
    guard_glass = trimesh.visual.material.PBRMaterial(name='clear PMMA', baseColorFactor=[194, 222, 232, 33],
                                                      roughnessFactor=.32, metallicFactor=0., alphaMode='BLEND')
    guard_base = trimesh.visual.material.PBRMaterial(name='guard plywood', baseColorFactor=[182, 155, 116, 255],
                                                     roughnessFactor=.8, metallicFactor=0.)
    for name, mesh in guard.items():
        panel = name in GUARD_PANELS
        material = guard_glass if panel else guard_base if name == 'GuardBase' else materials['steel']
        mesh.visual = trimesh.visual.TextureVisuals(material=material)
        scene.add_geometry(mesh, node_name=name, geom_name=name)
        parts[name] = {'center': mesh.bounds.mean(axis=0).round(2).tolist(),
                       'size': float(np.linalg.norm(mesh.extents).round(2)), 'guardPanel': panel}
    output.mkdir(parents=True, exist_ok=True)
    model = trimesh.exchange.gltf.export_glb(scene, include_normals=True)
    (output/'model.glb').write_bytes(model)
    (output/'steps.json').write_text(json.dumps({
        'source': assembly_cad.name if illustration else report.name, 'revision': revision,
        'cadSha256': layout['source_sha256'],
        'modelSha256': sha256(model).hexdigest(), 'planSha256': checked[0].get('plan_sha256'),
        'parts': parts, 'steps': steps, 'wires': wires,
        **({'stops': stop_locations} if stop_locations else {}),
        **({'illustration': True,
            'assemblyViews': [{'id': k, 'label': label, 'stage': step} for k,label,step in B25.VIEWS],
            'inspectionParts': [name for name in B25.LABELS if name in review['fixed']]}
           if illustration else {'assemblyViews': B24_ASSEMBLY_VIEWS} if revision in ('B24', 'B25') else {}),
        **({'finalView': review} if review else {}),
        **({'guardSha256': guard_hash} if guard_hash else {}),
        **({'wireStates': states, 'wireStatesSha256': sha256(wire_states.read_bytes()).hexdigest()} if states else {}),
    }, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{len(steps)} steps, {len(parts)} parts, model {(output/"model.glb").stat().st_size/1e6:.1f} MB')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path, help='mechanical/physics/export_cad.py --world output')
    parser.add_argument('hardware', type=Path, help='web/assembly/steps.js hardware as JSON')
    parser.add_argument('spec', type=Path, help='hardware-spec.json from build_b19_review_fixes.py')
    parser.add_argument('report', type=Path, nargs='?', help='Assembly check report, or omit for B25 --preview')
    parser.add_argument('--output', type=Path, default=HERE)
    parser.add_argument('--revision', choices=[key.upper() for key in C.PLANS], default='B19')
    parser.add_argument('--assembly-cad', type=Path, help='Matching FCStd for internal cable paths')
    parser.add_argument('--stop-report', type=Path, help='Checked stop locations with the same CAD digest')
    parser.add_argument('--guard-cad', type=Path, help='Guard assembly FCStd for the final view')
    parser.add_argument('--guard-report', type=Path, help='Passing guard report pairing the exact head and guard')
    parser.add_argument('--wire-states', type=Path, help='Exact camera centerlines and poses for comparison')
    parser.add_argument('--preview', action='store_true', help='Display unresolved cover service without certifying it')
    args = parser.parse_args()
    build(args.cad, args.hardware, args.spec, args.report, args.output, args.revision, args.assembly_cad,
          args.stop_report, args.guard_cad, args.guard_report, args.wire_states, args.preview)
