"""Check the B23 camera saddle wall and installed tie in the moving head."""

from argparse import ArgumentParser
from hashlib import file_digest
from itertools import product
import json
from pathlib import Path

import FreeCAD as App
import Part
import fcl
import numpy as np
import trimesh as tr
from trimesh.collision import mesh_to_BVH

from export_cad import world_shape
from wiring_motion import matrices, transform


def wall_grid(assembly, roof):
    doc = App.openDocument(str(assembly.resolve()))
    try:
        shape = world_shape(doc.Part066)
        x, y, z = roof
        points = [(u, v) for v in np.linspace(y-1.45, y+1.45, 21) for u in np.linspace(x-1.65, x+1.65, 31)]
        rays = Part.Compound([Part.makeLine(App.Vector(u, v, z-.05), App.Vector(u, v, z+5.)) for u, v in points])
        witnesses = []
        for edge in shape.common(rays).Edges:
            bottom = min((vertex.Point for vertex in edge.Vertexes), key=lambda point: point.z)
            if abs(bottom.z-z) < .002:
                witnesses.append((edge.Length, list(bottom)))
        return len(points), len(witnesses), min(witnesses)
    finally:
        App.closeDocument(doc.Name)


def tie_mesh(roof, buckle_drop):
    x, y, z = roof
    center = np.array([x, y, z+3.97])
    points = [(-4.36,-4.495), (4.36,-4.495), (4.22,.76), (3.20,1.05), (2.44,1.43),
              (1.7,2.55), (-1.7,2.55), (-2.44,1.43), (-3.20,1.05), (-4.22,.76), (-4.36,-4.495)]
    parts = []
    for (a, h), (b, k) in zip(points, points[1:]):
        block = tr.creation.box([np.hypot(b-a,k-h)+.02, 2.5, 1.05])
        block.apply_transform(tr.transformations.rotation_matrix(-np.arctan2(k-h,b-a), [0.,1.,0.]))
        parts.append(block.apply_translation(center+[(a+b)/2,0.,(h+k)/2]))
    buckle = tr.creation.box([2.95,4.90,3.60]).apply_translation(center+[-5.4,0.,-1.7-buckle_drop])
    return tr.util.concatenate([*parts,buckle])


def clearance(cad, layout, roof):
    tie_fits = [(drop, fcl.CollisionObject(mesh_to_BVH(tie_mesh(roof, drop)))) for drop in (0., .25)]
    candidates = []
    for name, role in layout['world_motion'].items():
        if role in ('head', 'fixed', 'pan', 'hatch') or name.startswith(('RearLead','HarnessWire','HubRearClearance')):
            continue
        mesh = tr.load_mesh(cad / 'world' / f'{name}.stl')
        if (len(mesh.faces) and np.all(mesh.bounds.max(0)>[-18,-63,53])
                and np.all(mesh.bounds.min(0)<[29,-22,112])):
            candidates.append((name, role, tr.bounds.corners(mesh.bounds), fcl.CollisionObject(mesh_to_BVH(mesh))))
    normal = list(product((-15.,0.,4.5), np.linspace(-8.,8.,17), (0.,22.5,45.,67.5,90.), (0.,5.5)))
    cutoff = [(pitch,eye,blink,jaw) for pitch,jaw in
              ((-17.204,9.79),(-16.7,9.79),(0.,9.79),(6.5,9.79),(6.9,9.61),(7.,9.11),(7.122,8.87))
              for eye in np.linspace(-8.,8.,17) for blink in (0.,22.5,45.,67.5,90.)]
    shortest = {drop: (float('inf'), '', []) for drop, _ in tie_fits}
    contacts = []
    request = fcl.DistanceRequest()
    for pitch, eye, blink, jaw in normal + cutoff:
        motion = matrices(layout, 0., pitch, eye, 0., jaw, blink)
        head_inverse = np.linalg.inv(motion['head'])
        for name, role, bounds, part in candidates:
            matrix = head_inverse @ motion[role]
            corners = transform(bounds, matrix)
            if np.any(corners.max(0)<[-6,-49,63]) or np.any(corners.min(0)>[18,-32,95]):
                continue
            part.setTransform(fcl.Transform(matrix[:3,:3], matrix[:3,3]))
            for drop, tie in tie_fits:
                distance = float(fcl.distance(tie, part, request, fcl.DistanceResult()))
                row = (distance, name, [pitch, eye, blink, jaw])
                shortest[drop] = min(shortest[drop], row)
                if distance < 0:
                    contacts.append({'drop_mm': drop, 'part': name, 'pose_deg': row[2]})
    return {'pose_count': len(normal+cutoff), 'parts': sorted(part[0] for part in candidates),
            'minimum_by_buckle_drop_mm': shortest, 'contacts': contacts}


def check(assembly, cad, output):
    with assembly.open('rb') as source:
        digest = file_digest(source, 'sha256').hexdigest()
    layout = json.loads((cad/'cad_parts.json').read_text())
    if layout['source_sha256'] != digest:
        raise ValueError('CAD and world meshes must describe the same assembly')
    roof = layout['motion_geometry']['camera_cable_nose']['tie_notch_roof_center_mm']
    sampled, measured, witness = wall_grid(assembly, roof)
    sweep = clearance(cad, layout, roof)
    passed = sampled == measured and witness[0] >= 1.2 and not sweep['contacts']
    result = {'status': 'pass' if passed else 'fail', 'cad_sha256': digest,
              'wall_samples': measured, 'wall_minimum_mm': witness[0], 'wall_minimum_location_mm': witness[1],
              'tie_size_mm': [2.5,1.05], 'buckle_size_mm': [2.95,4.90,3.60], 'motion': sweep}
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(f"{measured} wall sections, minimum {witness[0]:.3f} mm; "
          f"{sweep['pose_count']} tie poses, {len(sweep['contacts'])} contacts", flush=True)
    return passed


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('assembly', type=Path)
    parser.add_argument('cad', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if check(args.assembly, args.cad, args.output) else 1)
