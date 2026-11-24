"""Export full 6816 seat and 688 yoke fit variants from the B25 print meshes."""

from argparse import ArgumentParser
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from lxml import etree
import numpy as np
import trimesh

from build_b20_print import CORE, MODEL, MODEL_SETTINGS, PRODUCTION, REVISIONS, template_parts


PROJECT = REVISIONS / 'b25/R5-B25-P2S.3mf'
SEAT_SOURCE = '02_outer_bearing_seat-B23.stl'
YOKE_SOURCE = '07_yoke-B22.stl'
KEY_POCKET_INNER_RADIUS_MM = 51.61
YAW_FIT_DIAMETERS_MM = (100.10, 100.20, 100.30)
MINIMUM_LOAD_WALL_MM = 1.20
YOKE_FULL_SUPPORT_X = (-53.99, -52., -50., -49.55, 49.55, 52., 53.99)
YOKE_CROWN_X = (-49.50, -49.25, -49.01)


def source_mesh(bundle, name):
    config = etree.fromstring(bundle.read(MODEL_SETTINGS))
    model = etree.fromstring(bundle.read(MODEL))
    obj, _ = template_parts(config)[name]
    object_id = obj.get('id')
    component = model.find(f".//{CORE}object[@id='{object_id}']//{CORE}component")
    item = model.find(f".//{CORE}item[@objectid='{object_id}']")
    for node in (component, item):
        transform = np.fromstring(node.get('transform'), sep=' ')
        if not np.array_equal(transform[:9], np.eye(3).ravel()):
            raise ValueError(f'{name} print orientation has changed')
    plate, = [plate for plate in config.findall('plate') if plate.find(
        f"model_instance/metadata[@key='object_id'][@value='{object_id}']") is not None]
    number = int(plate.find("metadata[@key='plater_id']").get('value'))
    project = json.loads(bundle.read('Metadata/project_settings.config'))
    settings = {key: node.get('value') if (node := obj.find(f"metadata[@key='{key}']")) is not None
                else project[key] for key in ('layer_height', 'nozzle_diameter', 'filament_settings_id',
                                               'wall_generator', 'detect_thin_wall', 'outer_wall_line_width',
                                               'wall_loops', 'sparse_infill_density', 'enable_support',
                                               'support_type', 'xy_hole_compensation')}
    raw_mesh = bundle.read(component.get(PRODUCTION+'path').lstrip('/'))
    mesh = etree.fromstring(raw_mesh).find('.//' + CORE + 'mesh')
    vertices = np.array([[float(node.get(axis)) for axis in 'xyz'] for node in mesh.find(CORE+'vertices')])
    faces = np.array([[int(node.get(key)) for key in ('v1', 'v2', 'v3')] for node in mesh.find(CORE+'triangles')])
    return vertices, faces, {'source_part': name, 'source_mesh_sha256': sha256(raw_mesh).hexdigest(),
                             'p2s_plate': number, 'p2s_settings': settings}


def resize_bore(vertices, axes, center, original_radius, diameter, count):
    radial = vertices[:, axes] - center
    radii = np.linalg.norm(radial, axis=1)
    on_bore = np.isclose(radii, original_radius, rtol=0., atol=.0001)
    if np.count_nonzero(on_bore) != count:
        raise ValueError('Expected bearing bore vertices were not found')
    points = vertices.copy()
    radius = diameter / 2.
    points[np.ix_(on_bore, axes)] = radial[on_bore] * (radius / radii[on_bore, None]) + center
    if axes == (0, 1):
        # Keep the sides of the rear cable slot at X = ±12 mm.
        ends = on_bore & np.isclose(np.abs(vertices[:, 0]), 12., rtol=0., atol=.0001)
        if np.count_nonzero(ends) != 4 or np.any(vertices[ends, 1] >= 0):
            raise ValueError('The rear cable slot endpoints have changed')
        points[ends, 0] = vertices[ends, 0]
        points[ends, 1] = -np.sqrt(radius**2 - points[ends, 0]**2)
    return points


def cross_2d(a, b):
    return a[..., 0]*b[..., 1] - a[..., 1]*b[..., 0]


def radial_section(mesh, axis, position, center, angles):
    """Find the first two radial mesh intersections in one transverse section."""
    normal = np.eye(3)[axis]
    axes = [index for index in range(3) if index != axis]
    section = trimesh.intersections.mesh_plane(mesh, normal, normal*position)[:, :, axes] - center
    start = section[:, 0]
    edge = section[:, 1] - start
    direction = np.column_stack((np.cos(angles), np.sin(angles)))[:, None, :]
    denominator = cross_2d(direction, edge)
    with np.errstate(divide='ignore', invalid='ignore'):
        radial = cross_2d(start, edge) / denominator
        along_edge = cross_2d(start, direction) / denominator
    radial[(along_edge < 0.) | (along_edge > 1.) | (radial < 0.) | (np.abs(denominator) < 1e-9)] = np.inf
    radial.sort(axis=1)
    return radial[:, :2]


def radial_support(mesh, axis, position, center, radius, angles):
    """Sample material thickness outward from a circular bore in one transverse section."""
    radial = radial_section(mesh, axis, position, center, angles)
    supported = (np.abs(radial[:, 0]-radius) < .015) & np.isfinite(radial[:, 1])
    if not supported.any():
        raise ValueError(f'No radial support found at section {position:.2f} mm')
    wall = radial[supported, 1] - radial[supported, 0]
    bore = radial[supported, 0]
    return int(supported.sum()), float(wall.min()), [float(2.*bore.min()), float(2.*bore.max())]


def yoke_radial_support(mesh, x, radius):
    return radial_support(mesh, 0, x, [-14., -5.945], radius, np.arange(720)*np.pi/360. + .001)


def checked_stl(vertices, points, faces):
    mesh = trimesh.Trimesh(points, faces, process=False)
    if not mesh.is_volume or mesh.body_count != 1 or not mesh.nondegenerate_faces().all():
        raise ValueError('A variant is not one closed solid with nondegenerate faces')
    if not np.array_equal([vertices.min(axis=0), vertices.max(axis=0)], mesh.bounds):
        raise ValueError('A variant changed the envelope of its source part')
    source = vertices[faces]
    normal = np.cross(source[:, 1]-source[:, 0], source[:, 2]-source[:, 0])
    if not (np.einsum('ij,ij->i', mesh.face_normals, normal) > 0).all():
        raise ValueError('A variant changed the orientation of a source triangle')
    stl = mesh.copy().apply_translation([0., 0., -mesh.bounds[0, 2]]).export(file_type='stl')
    check = trimesh.load_mesh(BytesIO(stl), file_type='stl')
    if not check.is_volume or check.body_count != 1 or not check.nondegenerate_faces().all():
        raise ValueError('An exported STL lost its closed geometry')
    return mesh, stl


def variant_rows(vertices, faces, yaw):
    sizes = YAW_FIT_DIAMETERS_MM if yaw else [round(16. + step/10., 2) for step in range(1, 6)]
    source = trimesh.Trimesh(vertices, faces, process=False)
    original_crown = [yoke_radial_support(source, x, 8.13)[0] for x in YOKE_CROWN_X] if not yaw else []
    for diameter in sizes:
        radius = diameter / 2.
        row = {'nominal_bore_diameter_mm': diameter}
        if yaw:
            ligament = round(KEY_POCKET_INNER_RADIUS_MM - radius, 2)
            row['key_pocket_min_radial_ligament_mm'] = ligament
            if ligament < MINIMUM_LOAD_WALL_MM:
                raise ValueError('The yaw key pocket does not meet the load-bearing wall minimum')
            points = resize_bore(vertices, (0, 1), (0., 0.), 50.16, diameter, 236)
            stem = '02_outer-bearing-seat_6816'
        else:
            points = resize_bore(vertices, (1, 2), (-14., -5.945), 8.13, diameter, 535)
            stem = '07_pitch-yoke_688'

        mesh, stl = checked_stl(vertices, points, faces)
        if not yaw:
            full = [yoke_radial_support(mesh, x, radius) for x in YOKE_FULL_SUPPORT_X]
            crown = [yoke_radial_support(mesh, x, radius) for x in YOKE_CROWN_X]
            min_wall = min(sample[1] for sample in full)
            if (min(sample[0] for sample in full) != 720 or min_wall < 2.70
                    or [sample[0] for sample in crown] != original_crown):
                raise ValueError(f'Yoke support changed at Ø{diameter:.2f} mm')
            row['sampled_full_boss_min_wall_mm'] = round(min_wall, 3)
            row['sampled_full_boss_bore_range_mm'] = [round(min(sample[2][0] for sample in full), 4),
                                                     round(max(sample[2][1] for sample in full), 4)]
            row['crown_supported_directions_out_of_720'] = original_crown
        row.update(file=f'{stem}_ID{diameter:.2f}mm.stl', bytes=len(stl), sha256=sha256(stl).hexdigest())
        yield row, stl


def write_entry(bundle, name, data):
    bundle.writestr(ZipInfo(name), data, compress_type=ZIP_DEFLATED, compresslevel=9)


def build(output, project):
    if output.resolve() == project.resolve():
        raise ValueError('Choose a ZIP output separate from the original P2S project')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'source_project': project.name, 'source_project_sha256': sha256(project.read_bytes()).hexdigest(),
              'units': 'mm', 'stl_origin': 'Source orientation with lowest Z at the build plate', 'parts': {}}
    archive = BytesIO()
    with ZipFile(project) as source, ZipFile(archive, 'w') as destination:
        for name in (SEAT_SOURCE, YOKE_SOURCE):
            vertices, faces, part = source_mesh(source, name)
            yaw = name == SEAT_SOURCE
            if yaw:
                part.update(bearing='6816-2RS', bearing_od_mm=100., bearing_width_mm=10.,
                            bore_print_axis='Z (vertical)', source_bore_mm=100.32,
                            bore_xy_center_mm=[0., 0.], bore_depth_mm=11.,
                            outer_body_diameter_mm=138., shoulder_id_mm=97.2, shoulder_depth_mm=1.,
                            cable_slot_width_mm=24., key_pocket_inner_radius_mm=KEY_POCKET_INNER_RADIUS_MM)
            else:
                part.update(bearing='688-2RS, both sides', bearing_od_mm=16., bearing_width_mm=5.,
                            bore_print_axis='X (horizontal)', source_bore_mm=16.26,
                            bore_yz_center_from_print_base_mm=[-14., 18.61], boss_od_mm=22.,
                            bore_span_x_mm=[[-55.50, -46.00], [49.52, 55.50]],
                            bore_depth_mm=[9.50, 5.98], installed_bearing_x_mm=[[-54., -49.], [49., 54.]],
                            sampled_full_boss_x_mm=YOKE_FULL_SUPPORT_X, sampled_crown_x_mm=YOKE_CROWN_X,
                            crown_note='The left inboard 0.52 mm meets the existing partial crown. '
                                       'The right inboard 0.52 mm extends past the boss.')
            part['variants'] = []
            for row, stl in variant_rows(vertices, faces, yaw):
                part['variants'].append(row)
                write_entry(destination, row['file'], stl)
            report['parts']['02' if yaw else '07'] = part
        data = json.dumps(report, ensure_ascii=False, indent=2)+'\n'
        write_entry(destination, 'fit-large-bearings.json', data)
    output.write_bytes(archive.getbuffer())
    output.with_suffix('.json').write_text(data, encoding='utf-8')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--project', type=Path, default=PROJECT)
    args = parser.parse_args()
    build(args.output, args.project)
