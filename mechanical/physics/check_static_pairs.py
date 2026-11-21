"""Check seated world meshes, including parts that move together."""

from argparse import ArgumentParser
from hashlib import file_digest
from itertools import combinations
import json
from pathlib import Path

import fcl
import numpy as np
import trimesh
from trimesh.collision import mesh_to_BVH

OVERLAP_LIMIT = .05


def check(cad):
    info = json.loads((cad / 'cad_parts.json').read_text())
    parts = {p['name']: p for p in info['parts']}
    meshes = {f.stem: trimesh.load_mesh(f) for f in sorted((cad / 'world').glob('*.stl'))}
    missing = info['world_motion'].keys() - meshes.keys()
    if missing:
        raise ValueError(f'Missing seated exports: {", ".join(sorted(missing))}')
    meshes = {name: mesh for name, mesh in meshes.items() if len(mesh.faces)}
    if not meshes:
        raise ValueError('No seated meshes exported')
    objects = {name: fcl.CollisionObject(mesh_to_BVH(mesh)) for name, mesh in meshes.items()}
    request = fcl.CollisionRequest()
    print(f'{len(meshes)} seated meshes', flush=True)
    out = []
    for a, b in combinations(meshes, 2):
        first, second = meshes[a], meshes[b]
        if np.any(first.bounds[1] < second.bounds[0]) or np.any(second.bounds[1] < first.bounds[0]):
            continue
        if not fcl.collide(objects[a], objects[b], request, fcl.CollisionResult()):
            continue
        if first.is_volume and second.is_volume:
            cut = first.intersection(second, engine='manifold')
            volume = 0. if cut.is_empty else float(cut.volume)
            if volume <= OVERLAP_LIMIT:
                continue
            bounds = cut.bounds.round(2).tolist()
        else:
            volume = None
            bounds = 'Not all meshes are volumes!'
        out.append({'a': a, 'b': b, 'la': parts.get(a, {}).get('label'),
                    'lb': parts.get(b, {}).get('label'), 'ma': parts.get(a, {}).get('motion'),
                    'mb': parts.get(b, {}).get('motion'), 'mm3': volume, 'bounds': bounds})
    return out


def regressions(rows, baseline):
    previous = {(row['a'], row['b']): row['mm3'] for row in baseline}
    for row in rows:
        pair = (row['a'], row['b'])
        current = row['mm3']
        if pair not in previous:
            yield pair, 'new contact', current
            continue
        old = previous[pair]
        if old is None and current is not None:
            yield pair, 'previously unmeasurable overlap is now measurable', current
        if old is not None and (current is None or current > old + OVERLAP_LIMIT):
            yield pair, 'worse or no longer measurable', current


def resolve_native(rows, baseline, assembly, manifest):
    with assembly.open('rb') as source:
        if file_digest(source, 'sha256').hexdigest() != manifest['source_sha256']:
            raise ValueError('Native assembly differs from the seated world export')
    candidates = {pair for pair, _, _ in regressions(rows, baseline)}
    if not candidates:
        return rows

    import FreeCAD as App
    from export_cad import world_shape

    doc = App.openDocument(str(assembly.resolve()))
    try:
        qualified = []
        for row in rows:
            a, b = row['a'], row['b']
            objects = [doc.getObject(name) for name in (a, b)]
            if (a, b) not in candidates or not all(obj and obj.isDerivedFrom('Part::Feature') for obj in objects):
                qualified.append(row)
                continue
            first, second = map(world_shape, objects)
            if not first.Solids or not second.Solids:
                qualified.append(row)
                continue
            exact = first.common(second)
            volume = float(exact.Volume)
            if not np.isfinite(volume) or (not exact.isNull() and not exact.isValid()):
                raise ValueError(f'Unresolved native seated overlap for {a} and {b}')
            print(f'{a} / {b}: native solid overlap {volume:.6f} mm³')
            if volume > OVERLAP_LIMIT:
                bounds = exact.BoundBox
                qualified.append(dict(row, mm3=volume, bounds=[
                    [bounds.XMin, bounds.YMin, bounds.ZMin], [bounds.XMax, bounds.YMax, bounds.ZMax]],
                    measured_with='native_solids'))
        return qualified
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--baseline', type=Path, help='Fail on new or worse seated contacts')
    parser.add_argument('--exact-cad', type=Path, help='Use native solids to resolve new mesh overlap measurements')
    parser.add_argument('--summary', type=Path, help='Write input hashes and baseline comparison')
    args = parser.parse_args()
    rows = check(args.cad)
    baseline = json.loads(args.baseline.read_text()) if args.baseline else None
    manifest = json.loads((args.cad / 'cad_parts.json').read_text())
    if args.exact_cad:
        if baseline is None:
            parser.error('--exact-cad requires --baseline')
        rows = resolve_native(rows, baseline, args.exact_cad, manifest)
    args.report.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + '\n')
    unresolved = sum(row['mm3'] is None for row in rows)
    failures = list(regressions(rows, baseline)) if baseline is not None else None
    if args.summary:
        def digest(path):
            with path.open('rb') as source:
                return file_digest(source, 'sha256').hexdigest()

        evidence = dict(cad_sha256=manifest['source_sha256'], contact_report_sha256=digest(args.report),
                        baseline_sha256=digest(args.baseline) if args.baseline else None,
                        seated_pairs=len(rows), unmeasurable_pairs=unresolved, regressions=failures)
        args.summary.write_text(json.dumps(evidence, indent=2) + '\n')
    print(f'{len(rows)} contacts, {unresolved} with unmeasurable volume')
    for failure in failures or ():
        print(*failure)
    if failures:
        raise SystemExit(1)
