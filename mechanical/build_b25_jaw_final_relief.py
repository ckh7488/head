"""Apply the two B25 shell spot reliefs and the yoke-facing stay relief to V5."""

from argparse import ArgumentParser
from dataclasses import dataclass
from hashlib import file_digest
import json
from pathlib import Path

import FreeCAD as App
import Mesh  # Registers Mesh::Feature before opening the assembly.
import manifold3d as md
import numpy as np
from shapely import box, make_valid, union_all
from shapely.geometry import Polygon

from build_b22_fused_skull import solid
from build_b25_jaw_retention import mesh_from_solid, replace_mesh
from check_b25_jaw_retention import geometry


@dataclass(frozen=True)
class Relief:
    actor: str
    label: str
    face_y: float
    into_part: int
    depth: float
    footprint_xz: tuple[float, float, float, float]
    measurement_xz: tuple[float, float]


RELIEFS = (
    Relief('Part073', 'front-shell-left', -18.219999313354492, 1, .20,
           (-64.50, 104.50, -56.90, 114.00), (-61.063, 108.4026)),
    Relief('Part073', 'front-shell-right', -5.71999979019165, 1, .20,
           (60.20, 98.40, 67.20, 106.40), (63.285, 101.9794)),
    Relief('Jaw_37_right_jaw_bearing_stay', 'right-stay-yoke-face', -10.119999885559082, -1, .05,
           (47.60, 98.25, 57.20, 110.25), (51.56, 106.10)),
)
PLANE_TOLERANCE = 2e-5
OUTSIDE_LEAD = .01


def digest(path):
    with path.open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def planar_footprint(mesh, relief):
    coplanar = np.all(np.abs(mesh.triangles[:, :, 1] - relief.face_y) <= PLANE_TOLERANCE, axis=1)
    facing = mesh.face_normals[:, 1] * relief.into_part < -.9999
    xz = mesh.triangles[coplanar & facing][:, :, (0, 2)]
    available = union_all([Polygon(triangle) for triangle in xz])
    region = make_valid(available.intersection(box(*relief.footprint_xz)))
    if region.is_empty or region.area < 1.:
        raise ValueError(f'Missing facing plane for {relief.label}')
    return region


def cutting_tool(relief):
    x0, z0, x1, z1 = relief.footprint_xz
    face = relief.face_y
    entrance = face - relief.into_part * OUTSIDE_LEAD
    floor = face + relief.into_part * relief.depth
    y0, y1 = sorted((entrance, floor))
    return md.Manifold.cube((x1-x0, y1-y0, z1-z0)).translate((x0, y0, z0))


def native_bounds(body):
    return np.asarray(body.bounding_box()).reshape(2, 3)


def save_mesh(path, body):
    mesh = mesh_from_solid(body)
    np.savez_compressed(path, vertices=mesh.vertices, faces=mesh.faces)


def apply(doc, export_dir=None):
    if export_dir:
        export_dir.mkdir(parents=True, exist_ok=True)
    sources = {name: geometry(doc.getObject(name)) for name in sorted({item.actor for item in RELIEFS})}
    bodies = {name: solid(mesh) for name, mesh in sources.items()}
    rows = []
    operations = []
    for relief in RELIEFS:
        source = sources[relief.actor]
        region = planar_footprint(source, relief)
        tool = cutting_tool(relief)
        body = bodies[relief.actor]
        removed = body ^ tool
        if removed.volume() <= 0.:
            raise ValueError(f'Invalid relief tool for {relief.label}')
        bodies[relief.actor] = body - tool
        if export_dir:
            path = export_dir / f'{relief.label}-tool.npz'
            save_mesh(path, tool)
            operations.append({'actor': relief.actor, 'operation': 'subtract', 'world_mesh': str(path.resolve())})
        rows.append({
            'actor': relief.actor,
            'label': relief.label,
            'original_face_y_mm': relief.face_y,
            'new_face_y_mm': relief.face_y + relief.into_part * relief.depth,
            'depth_mm': relief.depth,
            'direction_world': [0, relief.into_part, 0],
            'window_xz_mm': list(relief.footprint_xz),
            'old_planar_face_area_inside_window_mm2': region.area,
            'outside_lead_mm': OUTSIDE_LEAD,
            'tool_world_bounds_mm': native_bounds(tool).tolist(),
            'removed_world_bounds_mm': native_bounds(removed).tolist(),
            'removed_volume_mm3': removed.volume(),
        })
    for name, body in bodies.items():
        result = mesh_from_solid(body)
        if not result.is_volume or result.body_count != 1 or not np.allclose(result.bounds, sources[name].bounds, atol=1e-6, rtol=0.):
            raise ValueError(f'{name} must retain one watertight body and its original bounds')
        for relief, row in zip(RELIEFS, rows, strict=True):
            if name != relief.actor:
                continue
            x, z = relief.measurement_xz
            point = (x, row['new_face_y_mm'], z)
            nearest, distance, _ = result.nearest.on_surface([point])
            if distance[0] > 1e-6:
                raise ValueError(f'Cannot locate the new planar surface on {relief.label}')
            row['new_face_measured_world_mm'] = nearest[0].tolist()
        replace_mesh(doc.getObject(name), result)
    if export_dir:
        (export_dir / 'operations.json').write_text(json.dumps(operations, indent=2) + '\n')
    return rows


def build(source, output, export_dir):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate native output')
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = App.openDocument(str(source.resolve()))
    try:
        measurements = apply(doc, export_dir)
        doc.recompute()
        doc.saveAs(str(output.resolve()))
    finally:
        App.closeDocument(doc.Name)
    report = {
        'source_v5_cad_sha256': digest(source),
        'candidate_cad_sha256': digest(output),
        'reliefs': measurements,
    }
    output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--export-dir', type=Path)
    build(**vars(parser.parse_args()))
