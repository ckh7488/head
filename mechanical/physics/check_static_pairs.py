"""Check seated world meshes, including parts that move together."""

from argparse import ArgumentParser
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


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--baseline', type=Path, help='Fail on new or worse seated contacts')
    args = parser.parse_args()
    rows = check(args.cad)
    args.report.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + '\n')
    print(f'{len(rows)} contacts, {sum(row["mm3"] is None for row in rows)} with unmeasurable volume')
    if args.baseline:
        failures = list(regressions(rows, json.loads(args.baseline.read_text())))
        for failure in failures:
            print(*failure)
        if failures:
            raise SystemExit(1)
