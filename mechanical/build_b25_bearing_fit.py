"""Export B25 full-part bearing-fit STL variants in their archived print directions."""

from argparse import ArgumentParser
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from lxml import etree
import manifold3d as md
import numpy as np
import trimesh

from build_b20_print import CORE, MODEL, MODEL_SETTINGS, PRODUCTION, template_parts


SOURCE = Path(__file__).resolve().parent / 'revisions/b25/R5-B25-P2S.3mf'
EYE_SIZES = (6.05, 6.10, 6.15, 6.20, 6.25)
JAW_SIZES = (10.05, 10.10, 10.15, 10.20, 10.25)
EYES = (
    ('13_left_eye_cradle_mount-B24.stl', '13L', 'Part025', (-13.5, -33.)),
    ('13_right_eye_cradle_mount-B24.stl', '13R', 'Part027', (13.5, -33.)),
)
JAW = '37_right_cheek_bearing_stay-B22.stl'
JAW_CENTER = (-1.25, 5.49964)
JAW_BOTTOM = -13.7001438
JAW_ENTRY = -9.68014337
RAIL = '24_blink_rail_with_bearing_shoulders.stl'
RAIL_CENTER = (12.55, -19.850004)
IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1]


def archived_mesh(project, name, plate):
    settings = etree.fromstring(project.read(MODEL_SETTINGS))
    model = etree.fromstring(project.read(MODEL))
    obj, _ = template_parts(settings)[name]
    object_id = obj.get('id')
    plates = settings.findall('plate')
    ids = plates[plate - 1].xpath('model_instance/metadata[@key="object_id"]/@value')
    component, = model.findall(f".//{CORE}object[@id='{object_id}']//{CORE}component")
    item, = model.findall(f".//{CORE}item[@objectid='{object_id}']")
    if object_id not in ids or any(
        list(map(float, node.get('transform').split()[:9])) != IDENTITY for node in (component, item)
    ):
        raise ValueError(f'Plate or orientation changed for {name}')
    path = component.get(PRODUCTION + 'path').lstrip('/')
    data = project.read(path)
    mesh = etree.fromstring(data).find('.//' + CORE + 'mesh')
    vertices = np.array([[float(vertex.get(k)) for k in 'xyz'] for vertex in mesh.find(CORE + 'vertices')])
    faces = np.array([[int(face.get(k)) for k in ('v1', 'v2', 'v3')] for face in mesh.find(CORE + 'triangles')])
    return trimesh.Trimesh(vertices, faces, process=False), {
        'source_file': name, 'plate': plate, 'object_id': int(object_id), 'object_path': path,
        'source_mesh_sha256': sha256(data).hexdigest(),
    }


def section(mesh, axis, station, center, diameter):
    basis = np.eye(3)[axis]
    plane = trimesh.intersections.mesh_plane(mesh, plane_normal=basis, plane_origin=basis * station)
    points = np.delete(plane, axis, axis=2) - center
    radii = np.linalg.norm(points, axis=2)
    on_ring = (np.abs(radii - diameter / 2) < .004).all(axis=1)
    start, end = points[on_ring].transpose(1, 0, 2)
    cross = start[:, 0] * end[:, 1] - start[:, 1] * end[:, 0]
    dot = np.einsum('ij,ij->i', start, end)
    angle = np.abs(np.arctan2(cross, dot)).sum()
    if abs(angle - 2 * np.pi) > .001:
        raise ValueError(f'Incomplete Ø{diameter} circular section at {station}')
    step = end - start
    fraction = -np.einsum('ij,ij->i', start, step) / np.einsum('ij,ij->i', step, step)
    nearest = start + step * np.clip(fraction, 0, 1)[:, None]
    return {'nominal_diameter_mm': diameter,
            'mesh_diameter_mm': [round(2 * float(np.linalg.norm(nearest, axis=1).min()), 6),
                                 round(2 * float(radii[on_ring].max()), 6)]}


def move_ring(stock, center, radius, count, delta):
    vertices = stock.vertices.copy()
    rays = vertices[:, :2] - center
    radii = np.linalg.norm(rays, axis=1)
    ring = np.abs(radii - radius) < .0001
    if np.count_nonzero(ring) != count:
        raise ValueError(f'Unexpected Ø{2 * radius} vertex ring')
    vertices[ring, :2] += rays[ring] * (delta / radius)
    mesh = trimesh.Trimesh(vertices, stock.faces, process=False)
    if (np.einsum('ij,ij->i', mesh.face_normals, stock.face_normals) <= 0).any():
        raise ValueError('The ring edit inverted source triangles')
    return mesh


def enlarge_jaw(stock, diameter):
    body = md.Manifold(md.Mesh64(np.asarray(stock.vertices), stock.faces.astype(np.uint64)))
    # The cutter phase avoids near-coincident facets at the original lead-in diameter.
    for low, high, size in (
        (JAW_BOTTOM, JAW_ENTRY + .001, diameter),
        (JAW_ENTRY, -8.8, diameter + .10),
    ):
        cutter = md.Manifold.cylinder(high - low, size / 2, circular_segments=192)
        body = body - cutter.rotate((0, 0, .6)).translate((*JAW_CENTER, low))
    if body.status() != md.Error.NoError:
        raise ValueError('Jaw bearing cut did not produce a manifold')
    geometry = body.to_mesh64()
    return trimesh.Trimesh(geometry.vert_properties[:, :3], geometry.tri_verts, process=False)


def stl_variant(stock, mesh, archive, name, center, checks):
    if not np.allclose(stock.bounds, mesh.bounds, atol=1e-6, rtol=0):
        raise ValueError(f'Print envelope changed for {name}')
    translation = -stock.bounds[0, 2]
    mesh.apply_translation((0, 0, translation))
    data = mesh.export(file_type='stl')
    export = trimesh.load_mesh(BytesIO(data), file_type='stl')
    vertices = export.vertices.astype(np.float32)
    centered = vertices - export.bounds.mean(axis=0).astype(np.float32)
    triangles = (centered * np.array((1e5, 1e5, 1.), dtype=np.float32))[export.faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    if (not export.is_volume or export.body_count != 1 or not export.nondegenerate_faces().all()
            or (normals == 0).all(axis=1).any()):
        raise ValueError(f'{name} needs one closed solid with nondegenerate slicer-scale facets')
    row = {label: section(export, 2, station + translation, center, diameter)
           for label, station, diameter in checks}
    archive.writestr(ZipInfo(name), data, compress_type=ZIP_DEFLATED)
    return dict(file=name, sha256=sha256(data).hexdigest(), facets=len(export.faces),
                print_dimensions_mm=np.round(export.extents, 6).tolist(),
                min_triangle_area_mm2=float(export.area_faces.min()),
                volume_delta_mm3=round(float(export.volume - stock.volume), 6), sections=row)


def build(output, evidence):
    with ZipFile(SOURCE) as project, ZipFile(output, 'w') as archive:
        rows = []
        for source, label, cad_id, center in EYES:
            stock, record = archived_mesh(project, source, 7)
            row = dict(record, part=label, cad_id=cad_id, print_axis='Z', bearing='NSK MR63ZZMC3P6',
                       source_pocket_mm=6.24, source_depth_mm=2.53, shoulder_mm=5.20, variants=[])
            for diameter in EYE_SIZES:
                mesh = move_ring(stock, center, 3.12, 252, (diameter - 6.24) / 2)
                name = f'p7-{label}-bearing-pocket-D{diameter:.2f}.stl'
                checks = (('pocket', .94, diameter), ('shoulder', -.60, 5.20))
                row['variants'].append(stl_variant(stock, mesh, archive, name, center, checks))
            rows.append(row)

        stock, record = archived_mesh(project, JAW, 9)
        jaw = dict(record, part='37', cad_id='Jaw_37_right_jaw_bearing_stay', print_axis='Z',
                   bearing='MR104ZZ', source_pocket_mm=10.10, source_depth_mm=4.02,
                   source_lead_in_mm=10.20, shoulder_mm=7.10, variants=[])
        for diameter in JAW_SIZES:
            mesh = (enlarge_jaw(stock, diameter) if diameter > 10.10 else
                    move_ring(stock, JAW_CENTER, 5.05, 274, (diameter - 10.10) / 2))
            name = f'p9-37-bearing-pocket-D{diameter:.2f}.stl'
            checks = (('pocket', -11.5, diameter), ('lead_in', -9.60, max(10.20, round(diameter + .10, 2))),
                      ('shoulder', -14.10, 7.10))
            jaw['variants'].append(stl_variant(stock, mesh, archive, name, JAW_CENTER, checks))
        rows.append(jaw)

        stock, record = archived_mesh(project, RAIL, 7)
        rail = dict(record, part='24', cad_id='Part063', print_axis='X', bearing='MR104ZZ',
                    source_pocket_mm=10.24, source_depth_mm=5.0, shoulder_mm=9.36,
                    variants=[], use='Use the source rail, finish to Ø10.24 and fit the B25 locating-band shims.')
        rail['source_sections'] = {
            label: section(stock, 0, station, RAIL_CENTER, diameter)
            for label, station, diameter in (('left_pocket', -31., 10.24), ('left_shoulder', -34., 9.36),
                                             ('right_pocket', 27., 10.24), ('right_shoulder', 29., 9.36))
        }
        rows.append(rail)

    report = {'source_project': SOURCE.name, 'source_sha256': sha256(SOURCE.read_bytes()).hexdigest(),
              'archive': output.name, 'archive_sha256': sha256(output.read_bytes()).hexdigest(),
              'parts': rows}
    evidence.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('evidence', type=Path)
    build(**vars(parser.parse_args()))
