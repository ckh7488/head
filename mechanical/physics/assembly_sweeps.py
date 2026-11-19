"""Check the actual walkthrough paths against the current FreeCAD solids."""

from argparse import ArgumentParser
from itertools import combinations
import json
from math import acos, cos, pi, sin
from pathlib import Path
import sys

import fcl
import FreeCAD as App
import manifold3d as md
import numpy as np
import trimesh as tr
from trimesh.collision import mesh_to_BVH

from export_cad import world_shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from primitives import cylinder
from stock import hexagon, socket_screw

WORLD_Z = np.array((0., 0., 1.))
MESH_VOLUME_LIMIT = .035


def manifold(mesh):
    return md.Manifold(md.Mesh(np.asarray(mesh.vertices, dtype=np.float32),
                               np.asarray(mesh.faces, dtype=np.uint32)))


def fastener(row):
    kind, size = row['type'], row['size']
    length = row.get('length', 0)
    if kind in ('nut', 'washer'):
        radius = {2: 4., 3: 5.5}[size] / np.sqrt(3) if kind == 'nut' else 3.5
        height = {2: 1.6, 3: 2.4}[size] if kind == 'nut' else .5
        stem = tr.creation.cylinder(radius=radius, height=height, sections=6 if kind == 'nut' else 30)
        hole = tr.creation.cylinder(radius=size/2+.006, height=height+.08, sections=48)
        stem = tr.boolean.difference([stem, hole], engine='manifold')
        stem.apply_transform(tr.transformations.rotation_matrix(row.get('phase', 0), WORLD_Z))
        stem.apply_translation((0, 0, height/2))
    else:
        radius, height = {2: (1.93, 2.), 3: (2.78, 3.)}[size]
        stem = tr.creation.cylinder(radius=radius, height=height, sections=32)
        stem.apply_translation((0, 0, -height/2))
        if kind == 'bolt':
            pin = tr.creation.cylinder(radius=size/2, height=length+.02, sections=32)
            pin.apply_translation((0, 0, length/2-.01))
            stem = tr.boolean.union([stem, pin], engine='manifold')
    axis = np.asarray(row['axis'])
    cosine = float(WORLD_Z @ axis)
    if cosine < 1.-1e-10:
        cross = np.cross(WORLD_Z, axis) if cosine > -1.+1e-10 else (0, -1, 0)
        stem.apply_transform(tr.transformations.rotation_matrix(acos(cosine), cross))
    return stem.apply_translation(row['seat'])


def exact_fastener(row):
    axis, seat, size = row['axis'], row['seat'], row['size']
    if row['type'] == 'head':
        radius, height = {2: (1.93, 2.), 3: (2.78, 3.)}[size]
        return cylinder(radius, height, seat, tuple(-App.Vector(*axis)))
    if row['type'] == 'bolt':
        return socket_screw(size, row['length'], seat, axis)
    shift = App.Vector(*seat) - .045*App.Vector(*axis)
    if row['type'] == 'washer':
        blank = cylinder(3.50, .5, seat, axis)
        return blank.cut(cylinder(1.60, .59, tuple(shift), axis))
    height = {2: 1.6, 3: 2.4}[size]
    phase = row.get('phase', 0)-pi/6
    normal = App.Rotation(App.Vector(*WORLD_Z), App.Vector(*axis)).multVec(App.Vector(cos(phase), sin(phase), 0))
    blank = hexagon({2: 4., 3: 5.5}[size], height, seat, axis, tuple(normal))
    return blank.cut(cylinder(size/2, height+.09, tuple(shift), axis))


def crop(solid, bounds, shift):
    lo = np.minimum(bounds[0], bounds[0]+shift) - .10
    hi = np.maximum(bounds[1], bounds[1]+shift) + .10
    return solid ^ md.Manifold.cube(hi-lo).translate(lo)


def check_paths(doc, directory, plan, selected):
    request = fcl.CollisionRequest(num_max_contacts=1)
    hardware = {row['id']: row for row in plan['hardware']}
    cache, exact = {}, {}

    def element(name, closed=False):
        closed = closed and name in ('Part078', 'Part079')
        key = name, closed
        if key not in cache:
            mesh = fastener(hardware[name]) if name in hardware else tr.load_mesh(directory/f'{name}.stl')
            if closed:
                mesh.apply_transform(tr.transformations.rotation_matrix(np.pi/2, (1, 0, 0), (0, -39, 119)))
            solid = manifold(mesh)
            if solid.is_empty():
                solid = None
            cache[key] = mesh, fcl.CollisionObject(mesh_to_BVH(mesh)), solid
        return cache[key]

    def brep(name):
        if name not in exact:
            if name in hardware:
                exact[name] = exact_fastener(hardware[name])
            else:
                obj = doc.getObject(name)
                exact[name] = world_shape(obj) if obj and obj.TypeId == 'Part::Feature' else None
        return exact[name]

    zero = np.zeros(3)
    problems, samples = {}, 0
    for step in plan['steps']:
        identifier = step['id']
        if selected and identifier not in selected:
            continue
        closed = step.get('closedLids', False)
        moving = {part: np.asarray(move['offset']) for move in step['moves'] for part in move['ids']}
        parts = dict.fromkeys(step['base'].split() + list(moving))
        issues = []
        for first, second in combinations(parts, 2):
            shift = moving.get(first, zero) - moving.get(second, zero)
            distance = np.linalg.norm(shift)
            if distance < 1e-8:
                continue
            m1, o1, solid1 = element(first, closed)
            m2, o2, solid2 = element(second, closed)
            if np.any(np.maximum(m1.bounds[1], m1.bounds[1]+shift) < m2.bounds[0]):
                continue
            if np.any(np.minimum(m1.bounds[0], m1.bounds[0]+shift) > m2.bounds[1]):
                continue
            if solid1 is not None and solid2 is not None:
                if len(m1.faces) > 25000:
                    solid1 = crop(solid1, m2.bounds, -shift)
                if len(m2.faces) > 25000:
                    solid2 = crop(solid2, m1.bounds, shift)
            hits = []
            o2.setTransform(fcl.Transform())
            for fraction in np.linspace(0., 1., max(2, int(np.ceil(distance))+1)):
                offset = shift*fraction
                samples += 1
                o1.setTransform(fcl.Transform(offset))
                if not fcl.collide(o1, o2, request, fcl.CollisionResult()):
                    continue
                if solid1 is not None and solid2 is not None:
                    overlap = (solid1.translate(offset) ^ solid2).volume()
                elif brep(first) is not None and brep(second) is not None:
                    overlap = brep(first).translated(App.Vector(*offset)).common(brep(second)).Volume
                else:
                    overlap = None
                if overlap is None or overlap > MESH_VOLUME_LIMIT:
                    hits.append((float(fraction), overlap))
            if hits:
                fraction, volume = max(hits, key=lambda p: -1 if p[1] is None else p[1])
                issues.append({'parts': [first, second], 'fraction': round(fraction, 3),
                               'overlap_mm3': None if volume is None else round(volume, 4)})
        problems[identifier] = issues
        print(identifier, issues or 'clear', flush=True)
    return {'placements': samples, 'steps': problems}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('directory', type=Path)
    parser.add_argument('plan', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('steps', nargs='*')
    args = parser.parse_args()
    doc = App.openDocument(str(args.cad.resolve()))
    try:
        report = check_paths(doc, args.directory, json.loads(args.plan.read_text()), args.steps)
    finally:
        App.closeDocument(doc.Name)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(f'{report["placements"]:,} placement pairs evaluated', flush=True)
    sys.exit(any(report['steps'].values()))
