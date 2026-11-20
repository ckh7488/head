"""Build the B19 assembly walkthrough (model.glb + steps.json) from the checked assembly plan.

Every step, part, offset and note comes from mechanical/physics/check_b19_assembly.py and its report,
so the viewer shows exactly the order that was checked and written into mechanical/ASSEMBLY.md.

    python web/b19/build_b19_viewer.py build/b19-cad build/hardware.json \
        mechanical/revisions/b19/print/hardware-spec.json mechanical/revisions/b19/assembly-check.json
"""
from argparse import ArgumentParser
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
    'b19': (226, 92, 60),
}
FACE_LIMIT = {'bone': 30000, 'jaw': 12000, 'eye': 8000}
BLOCKED = re.compile(r'(.+): stated approach \((.+?)\) is blocked; \((.+?)\) is clear')


def numbers(text):
    return [float(v) for v in text.split(',')]


def finish_of(name, manifest):
    if name in manifest:
        return manifest[name]
    return 'steel'


def build(cad, hardware, spec, report, output):
    data = json.loads(hardware.read_text())
    world = C.World(cad, data['hardware'], json.loads(spec.read_text()))
    checked = {row['id']: row for row in json.loads(report.read_text())}
    manifest = {p['cad_id']: p['finish'] for p in json.loads((ROOT/'web/assets/assembly.json').read_text())['parts']}
    layout = json.loads((cad/'cad_parts.json').read_text())
    labels = {p['name']: p.get('label') or '' for p in layout.get('parts', [])}
    b19_names = {item['name'] for item in json.loads(spec.read_text())} | {'PitchPinDowelLeft', 'PitchPinDowelRight'}

    installed, used, steps = {}, set(), []
    number, last_text, sub = 0, '', 0
    for st in C.PLAN:
        row = checked[st['id']]
        ctx = installed.setdefault(st['ctx'], [])
        alternatives = {}
        for note in row['notes']:
            match = BLOCKED.match(note)
            if match:
                alternatives[match.group(1).replace(' assembly', '')] = numbers(match.group(3))
        fixed = list(ctx)
        moves = []
        for key in ('merge', 'merge2'):
            if key in st:
                other, offset = st[key]
                parts = installed.pop(other)
                offset = alternatives.get(other, offset)
                moves.append({'ids': parts, 'path': [list(map(float, offset)), [0, 0, 0]]})
                ctx.extend(parts)
        for key in ('place', 'place2', 'pins', 'pins2', 'nuts', 'nuts2'):
            if key in st:
                parts, offset = st[key]
                offset = alternatives.get(', '.join(parts), offset)
                moves.append({'ids': list(parts), 'path': [list(map(float, offset)), [0, 0, 0]]})
                ctx.extend(parts)
        if 'path' in st:
            parts, points = st['path']
            moves.append({'ids': list(parts), 'path': [list(map(float, p)) for p in points]})
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
        moving = [i for m in moves for i in m['ids']]
        used.update(fixed + moving)
        steps.append({
            'id': st['id'], 'label': label, 'section': SECTIONS[st['ctx']], 'bench': st['ctx'] in BENCH,
            'text': row['text'] or last_text, 'continued': not row['text'],
            'notes': list(dict.fromkeys(note_text(n) for n in row['notes'])),
            'issues': row['issues'], 'fixed': [i for i in fixed if world.mesh(i) is not None],
            'moves': [m for m in ({**m, 'ids': [i for i in m['ids'] if world.mesh(i) is not None]} for m in moves) if m['ids']],
            'closedLids': bool(st.get('closed_lids')),
        })

    scene = trimesh.Scene()
    materials = {name: trimesh.visual.material.PBRMaterial(
        name=name, baseColorFactor=np.array((*rgb, 255), dtype=np.uint8), roughnessFactor=.6,
        metallicFactor=.45 if name == 'steel' else 0.) for name, rgb in COLORS.items()}
    parts = {}
    for name in sorted(used):
        mesh = world.mesh(name)
        if mesh is None:
            continue
        mesh = mesh.copy()
        finish = 'b19' if name in b19_names else finish_of(name, manifest)
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
    output.mkdir(parents=True, exist_ok=True)
    (output/'model.glb').write_bytes(trimesh.exchange.gltf.export_glb(scene, include_normals=True))
    (output/'steps.json').write_text(json.dumps({'source': report.name, 'parts': parts, 'steps': steps},
                                                ensure_ascii=False, separators=(',', ':')))
    print(f'{len(steps)} steps, {len(parts)} parts, model {(output/"model.glb").stat().st_size/1e6:.1f} MB')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path, help='mechanical/physics/export_cad.py --world output for B19')
    parser.add_argument('hardware', type=Path, help='web/assembly/steps.js hardware as JSON')
    parser.add_argument('spec', type=Path, help='hardware-spec.json from build_b19_review_fixes.py')
    parser.add_argument('report', type=Path, help='assembly-check.json from check_b19_assembly.py')
    parser.add_argument('--output', type=Path, default=HERE)
    args = parser.parse_args()
    build(args.cad, args.hardware, args.spec, args.report, args.output)
