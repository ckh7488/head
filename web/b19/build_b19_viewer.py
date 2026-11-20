"""Build the assembly walkthrough (model.glb + steps.json) from the checked assembly plan.

Every step, part, offset and note comes from mechanical/physics/check_b19_assembly.py and its report,
so the viewer shows exactly the order that was checked and written into mechanical/ASSEMBLY.md.

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
}
FACE_LIMIT = {'bone': 30000, 'jaw': 12000, 'eye': 8000}
BLOCKED = re.compile(r'(.+): stated approach \((.+?)\) is blocked; \((.+?)\) is clear')
REAR_WIRING = ('RearLead', 'CableTie', 'InputXT', 'SupplyXT30', 'CameraUSB', 'ControlUSB')


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
            mesh = trimesh.creation.extrude_polygon(Polygon(profile['profile']), profile['thickness'])
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
    return choices


def build(cad, hardware, spec, report, output, revision='B19', assembly_cad=None):
    data = json.loads(hardware.read_text())
    world = C.World(cad, data['hardware'], json.loads(spec.read_text()))
    checked = json.loads(report.read_text())
    plan = C.PLANS[revision.lower()]
    if [(row['id'], row['context'], row['text']) for row in checked] != [
            (step['id'], step['ctx'], step['text']) for step in plan]:
        raise ValueError('Assembly report does not match the current assembly plan')
    manifest = {p['cad_id']: p['finish'] for p in json.loads((ROOT/'web/assets/assembly.json').read_text())['parts']}
    layout = json.loads((cad/'cad_parts.json').read_text())
    world.layout = layout
    if revision != 'B19' and checked[0].get('cad_sha256') != layout['source_sha256']:
        raise ValueError('Assembly report and CAD export use different revisions')
    if revision == 'B21' and checked[0].get('plan_sha256') != C.plan_hash(plan):
        raise ValueError('B21 assembly plan differs from the one checked')
    labels = {p['name']: p.get('label') or '' for p in layout.get('parts', [])}
    b19_names = {item['name'] for item in json.loads(spec.read_text())} | {'PitchPinDowelLeft', 'PitchPinDowelRight'}
    rear_wiring = [name for name in layout['world_motion'] if name.startswith(REAR_WIRING)]
    hub_plugs = [name for name in layout['world_motion'] if name.startswith('HubPlug')]
    wires = load_wires(assembly_cad, layout['source_sha256'])

    installed, used, steps = {}, set(), []
    tools, phases = {}, {}
    number, last_text, sub = 0, '', 0
    for st, row in zip(plan, checked, strict=True):
        if st.get('blink_deg') != row.get('blink_deg'):
            raise ValueError(f'Assembly pose differs from the checked pose for {st["id"]}')
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
        if row['text']:
            number += 1
            label, last_text, sub = str(number), row['text'], 0
        else:
            sub += 1
            label = f'{number}-{sub + 1}'
        names = fixed + [name for move in moves for name in move['ids']]
        if len(names) != len(set(names)):
            raise ValueError(f'Duplicate parts in {st["id"]}')
        used.update(names)
        tool_paths = checked_tools(row, world, data['hardware'], tools, phases) if revision == 'B21' else []
        poses = {name: matrix.tolist() for name in names if (matrix := world.blink_transform(name)) is not None}
        steps.append({
            'id': st['id'], 'label': label, 'section': SECTIONS[st['ctx']], 'bench': st['ctx'] in BENCH,
            'text': row['text'] or last_text, 'continued': not row['text'],
            'notes': list(dict.fromkeys(note_text(n) for n in row['notes'])),
            'issues': row['issues'], 'fixed': fixed, 'moves': moves,
            'closedLids': bool(st.get('closed_lids')),
            'showWires': st['id'] == 'rear-skull',
            **({'toolPaths': tool_paths} if tool_paths else {}),
            **({'actorPoses': poses, 'blinkDegrees': st['blink_deg']} if poses else {}),
            **({'insertionClearance': row['insertion_clearance']} if 'insertion_clearance' in row else {}),
        })

    scene = trimesh.Scene()
    world.blink_pose = None
    materials = {name: trimesh.visual.material.PBRMaterial(
        name=name, baseColorFactor=np.array((*rgb, 255), dtype=np.uint8), roughnessFactor=.6,
        metallicFactor=.45 if name == 'steel' else 0.) for name, rgb in COLORS.items()}
    parts = {}
    for name in sorted(used):
        mesh = world.mesh(name)
        if mesh is None:
            raise ValueError(f'Empty assembly mesh: {name}')
        mesh = mesh.copy()
        if phases.get(name):
            nut = world.rows[name]
            mesh.apply_transform(trimesh.transformations.rotation_matrix(
                np.radians(phases[name]), nut['axis'], nut['seat']))
        finish = ('b19' if name in b19_names else 'power' if name.startswith('RearLead')
                  else 'connector' if name in rear_wiring or name in hub_plugs else finish_of(name, manifest))
        limit = FACE_LIMIT.get(finish, 4000)
        if len(mesh.faces) > limit:
            # Decimation can tear closed parts; torn faces render as black patches.
            for target in [t for t in (limit, 2*limit) if t < len(mesh.faces)]:
                reduced = mesh.simplify_quadric_decimation(face_count=target)
                if reduced.is_watertight or not mesh.is_watertight:
                    break
            if reduced.is_watertight or not mesh.is_watertight or len(mesh.faces) > 40000:
                mesh = reduced
        mesh.visual = trimesh.visual.TextureVisuals(material=materials[finish])
        scene.add_geometry(mesh, node_name=name, geom_name=name)
        parts[name] = {'label': labels.get(name, ''), 'b19': name in b19_names,
                       'center': mesh.bounds.mean(axis=0).round(2).tolist(),
                       'size': float(np.linalg.norm(mesh.extents).round(2))}
    for name, mesh in tools.items():
        mesh.visual = trimesh.visual.TextureVisuals(material=materials['tool'])
        scene.add_geometry(mesh, node_name=name, geom_name=name)
    output.mkdir(parents=True, exist_ok=True)
    model = trimesh.exchange.gltf.export_glb(scene, include_normals=True)
    (output/'model.glb').write_bytes(model)
    (output/'steps.json').write_text(json.dumps({
        'source': report.name, 'revision': revision, 'cadSha256': layout['source_sha256'],
        'modelSha256': sha256(model).hexdigest(), 'planSha256': checked[0].get('plan_sha256'),
        'parts': parts, 'steps': steps, 'wires': wires,
    }, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{len(steps)} steps, {len(parts)} parts, model {(output/"model.glb").stat().st_size/1e6:.1f} MB')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path, help='mechanical/physics/export_cad.py --world output')
    parser.add_argument('hardware', type=Path, help='web/assembly/steps.js hardware as JSON')
    parser.add_argument('spec', type=Path, help='hardware-spec.json from build_b19_review_fixes.py')
    parser.add_argument('report', type=Path, help='assembly-check.json from check_b19_assembly.py')
    parser.add_argument('--output', type=Path, default=HERE)
    parser.add_argument('--revision', choices=[key.upper() for key in C.PLANS], default='B19')
    parser.add_argument('--assembly-cad', type=Path, help='Matching FCStd for internal cable paths')
    args = parser.parse_args()
    build(args.cad, args.hardware, args.spec, args.report, args.output, args.revision, args.assembly_cad)
