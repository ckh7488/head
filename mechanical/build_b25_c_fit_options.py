"""Export complete small-pin fit trials from the frozen P2S print meshes."""

from argparse import ArgumentParser
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from lxml import etree
import manifold3d
import numpy as np
import trimesh

from build_b20_print import CORE, MODEL_RELS, PRODUCTION, replace_mesh, serialize
from build_b25_pin_fit_options import Bore, MODEL, MODEL_SETTINGS, PROJECT, load_print_mesh


@dataclass(frozen=True)
class PartFit:
    name: str
    object_id: str
    center_yz_mm: tuple[float, float]
    diameter_mm: float
    diameters_mm: tuple[float, ...]
    sections_x_mm: tuple[float, ...]
    wall_vertices: int
    entry_diameter_mm: float | None = None
    entry_section_x_mm: float | None = None
    entry_wall_vertices: int = 0
    blind_end_x_mm: float | None = None


ORBIT_SIZES = (2.30, 2.35, 2.40, 2.45, 2.50)
LID_SIZES = (2.45, 2.50, 2.55, 2.60, 2.65)
JAW_SIZES = (4.05, 4.10, 4.15, 4.20, 4.25)
ORBIT_SECTIONS = (-22.96, -21.70, -20.49, 20.49, 21.70, 22.96)
LEFT_LID_SECTIONS = (-18.20, -16.15, -14.10, 15.85, 17.90, 19.95)
PARTS = (
    PartFit('31_left_black_orbit', '86', (0., 19.1), 2.36, ORBIT_SIZES, ORBIT_SECTIONS, 560),
    PartFit('31_right_black_orbit', '88', (0., 19.1), 2.36, ORBIT_SIZES, ORBIT_SECTIONS, 560),
    PartFit('32_left_eyelid', '90', (-1.090911, 12.383362), 2.24, LID_SIZES, LEFT_LID_SECTIONS,
            504, 2.40, -18.45, 253),
    PartFit('32_right_eyelid', '92', (-1.090911, 12.383362), 2.24, LID_SIZES,
            tuple(-x for x in LEFT_LID_SECTIONS), 504, 2.40, 18.45, 253),
    PartFit('30_38_39_jaw_one_piece', '18', (24.900906, 94.770613), 4.14, JAW_SIZES,
            (46.30, 47.35, 48.45, 49.55, 50.60), 209, blind_end_x_mm=51.3522),
)

README = '''# B25 소형 핀 맞춤용 전체 부품

고정한 B25 P2S 프로젝트에서 소형 핀 구멍만 바꾼 시험 출력물입니다.
눈틀과 눈꺼풀 STL은 원본 출력 방향을 따르고 바닥이 Z=0입니다. 턱은 원본 이음부의
메시 인덱스를 보존하는 Bambu 3MF로 열 수 있습니다. P2S, PETG HF, 0.4 mm 노즐과
0.20 mm 레이어로 원본 판의 출력 및 서포트 설정을 사용합니다.

- 31번 좌우 안와의 두 Ø2 자리에는 힌지 핀을 고정합니다. 실제 핀으로 건식
  끼움을 확인한 뒤 고정 쪽에만 접착제를 사용합니다.
- 32번 좌우 눈꺼풀의 두 조인트는 실제 Ø2 핀이 힘을 주지 않아도 회전해야
  합니다. 바깥쪽 입구는 본 구멍보다 0.16 mm 넓고, 원본과 같은 깊이 0.35 mm입니다.
- 30·38·39 일체형 턱에서 변형하는 부분은 39번 쪽의 Ø4 핀 막힌 자리입니다.
  입구 쪽 직선 자리 깊이는 4.40 mm입니다. 안쪽 Ø3.96 단차와 막힌 바닥을 유지했습니다.
  턱의 핀은 이 자리에서 고정하고 맞은편 베어링에서 회전시킵니다.

파일명의 숫자는 모델 지름입니다. 게이지와 실물 부품을 건식으로 확인하고
실제 금속 치수와 인쇄된 구멍의 양쪽 치수를 기록한 뒤 최종 파일을 선택합니다.
완성 부품도 조립하기 전에 확인하며 시험 파일은 고정 조립본과 별도로 관리합니다.
'''


def cross_2d(first, second):
    return first[..., 0] * second[..., 1] - first[..., 1] * second[..., 0]


def section_ligament(mesh, center, x, radius):
    segments = trimesh.intersections.mesh_plane(mesh, [1, 0, 0], [x, 0, 0])[:, :, 1:] - center
    starts = segments[:, 0]
    edges = segments[:, 1] - starts
    angles = np.arange(720) * np.pi / 360 + .001
    rays = np.column_stack((np.cos(angles), np.sin(angles)))[:, None, :]
    denominator = cross_2d(rays, edges)
    with np.errstate(divide='ignore', invalid='ignore'):
        distance = cross_2d(starts, edges) / denominator
        fraction = cross_2d(starts, rays) / denominator
    distance[(fraction < 0) | (fraction > 1) | (distance < 0) | (abs(denominator) < 1e-10)] = np.inf
    distance.sort(axis=1)
    inner, outer = distance[:, 0], distance[:, 1]
    if not np.all(np.isfinite(outer)) or np.any(abs(inner - radius) > .004):
        raise ValueError(f'Incomplete cylindrical support at X={x:.2f} mm')
    return float(np.min(outer - inner))


def wall_masks(original, part):
    radial = original.vertices[:, 1:] - part.center_yz_mm
    radii = np.linalg.norm(radial, axis=1)
    wall = np.isclose(radii, part.diameter_mm / 2, atol=.00004, rtol=0)
    if part.blind_end_x_mm is not None:
        wall &= (original.vertices[:, 0] >= 46.2521) & (original.vertices[:, 0] <= part.blind_end_x_mm)
    if np.count_nonzero(wall) != part.wall_vertices:
        raise ValueError(f'Unexpected cylindrical wall in {part.name}: {np.count_nonzero(wall)} vertices')
    entry = np.zeros(len(radii), dtype=bool)
    if part.entry_diameter_mm is not None:
        entry = np.isclose(radii, part.entry_diameter_mm / 2, atol=.00004, rtol=0)
        if np.count_nonzero(entry) != part.entry_wall_vertices:
            raise ValueError(f'Unexpected stepped entrance in {part.name}')
    return radial, radii, wall, entry


def checked_variant(original, part, diameter, base_sections, masks):
    radial, radii, wall, entry = masks
    delta = (diameter - part.diameter_mm) / 2
    selected = wall | entry
    points = original.vertices.copy()
    points[selected, 1:] += radial[selected] * (delta / radii[selected, None])
    faces = original.faces.copy()
    if part.object_id == '86' and delta > 0:
        # The source diagonal crosses the enlarged circular rim on the +X face.
        # Use the other diagonal of the same coplanar quadrilateral.
        inlet_faces = [1910, 2018]
        expected_inlet = [[1040, 1038, 839], [1040, 1058, 1038]]
        if not np.array_equal(faces[inlet_faces], expected_inlet):
            raise ValueError('Left orbit inlet triangulation has changed')
        faces[inlet_faces] = [[1040, 1058, 839], [1058, 1038, 839]]
    mesh = trimesh.Trimesh(points, faces, process=False)
    if (not mesh.is_volume or mesh.body_count != 1 or not mesh.nondegenerate_faces().all()
            or not np.array_equal(mesh.bounds, original.bounds)
            or np.any(np.einsum('ij,ij->i', mesh.face_normals, original.face_normals) <= 0.)):
        raise ValueError('Mesh topology, orientation or exterior extent changed')
    if delta and (mesh.volume - original.volume) * delta >= 0:
        raise ValueError('The mesh volume changed in the wrong direction')
    checks = [section_ligament(mesh, part.center_yz_mm, x, radius + delta)
              for x, radius in base_sections]
    stl = trimesh.exchange.stl.export_stl(mesh)
    imported = trimesh.load_mesh(BytesIO(stl), file_type='stl')
    if not imported.is_volume or imported.body_count != 1 or not imported.nondegenerate_faces().all():
        raise ValueError('STL round trip did not retain a single closed solid')
    return stl, min(checks)


def jaw_variant(original, part, diameter, base_sections, wall):
    start, shoulder, *_ = np.unique(original.vertices[wall, 0])
    if not np.isclose(shoulder - start, 4.40, atol=.00002, rtol=0):
        raise ValueError('The original jaw socket depth has changed')
    radius = diameter / 2
    source = manifold3d.Manifold(manifold3d.Mesh64(original.vertices, original.faces.astype(np.uint64)))

    def tool(tool_radius, first, last):
        return (manifold3d.Manifold.cylinder(last - first, tool_radius, tool_radius, circular_segments=126)
                .rotate((0, 90, 0)).translate((first, *part.center_yz_mm)))

    if diameter < part.diameter_mm:
        fill = tool(2.095, start, shoulder) - tool(radius, start - .01, shoulder + .01)
        solid = source + fill
    else:
        solid = source - tool(radius, start - .01, shoulder)
    if solid.status() != manifold3d.Error.NoError:
        raise ValueError('Jaw socket boolean operation failed')
    indexed = solid.to_mesh64()
    mesh = trimesh.Trimesh(indexed.vert_properties[:, :3], indexed.tri_verts, process=False)
    if (not mesh.is_volume or mesh.body_count != 1 or not np.array_equal(mesh.bounds, original.bounds)
            or (mesh.volume - original.volume) * (diameter - part.diameter_mm) >= 0):
        raise ValueError('Jaw variant is not one closed solid with the original extent')

    def remote_triangles(part_mesh):
        triangles = part_mesh.triangles
        x = triangles[:, :, 0]
        radii = np.linalg.norm(triangles[:, :, 1:] - part.center_yz_mm, axis=-1)
        remote = ((x < start - .05).all(axis=1) | (x > shoulder + .05).all(axis=1)
                  | (radii > 2.20).all(axis=1))
        return Counter(tuple(sorted(map(tuple, face))) for face in np.round(triangles[remote], 7))

    if remote_triangles(original) != remote_triangles(mesh):
        raise ValueError('Jaw triangles outside the straight pin socket changed')
    ligament = min(section_ligament(mesh, part.center_yz_mm, x, radius) for x, _ in base_sections)
    return mesh, ligament


def jaw_project(source, part, name, mesh):
    model = etree.fromstring(source.read(MODEL))
    config = etree.fromstring(source.read(MODEL_SETTINGS))
    relations = etree.fromstring(source.read(MODEL_RELS))
    package = etree.fromstring(source.read('_rels/.rels'))
    obj = config.find(f'object[@id="{part.object_id}"]')
    resource = model.find(f'.//{CORE}object[@id="{part.object_id}"]')
    item = model.find(f'.//{CORE}item[@objectid="{part.object_id}"]')
    component, = resource.find(CORE + 'components')
    target = component.get(PRODUCTION + 'path')
    plate, = (candidate for candidate in config.findall('plate') if candidate.find(
        f'model_instance/metadata[@key="object_id"][@value="{part.object_id}"]') is not None)
    instance, = (candidate for candidate in plate.findall('model_instance') if candidate.find(
        f'metadata[@key="object_id"][@value="{part.object_id}"]') is not None)
    for parent, keep in ((resource.getparent(), resource), (item.getparent(), item)):
        for child in list(parent):
            if child is not keep:
                parent.remove(child)
    for child in list(config):
        if child is not obj and child is not plate:
            config.remove(child)
    for other in plate.findall('model_instance'):
        if other is not instance:
            plate.remove(other)
    for metadata in plate.findall('metadata'):
        if metadata.get('key') not in ('plater_id', 'plater_name', 'locked'):
            plate.remove(metadata)
    plate.find('metadata[@key="plater_id"]').set('value', '1')
    plate.find('metadata[@key="plater_name"]').set('value', 'B25 jaw fit')
    for parent, path in ((relations, target), (package, '/' + MODEL)):
        for relationship in list(parent):
            if relationship.get('Target') != path:
                parent.remove(relationship)
    part_config = obj.find('part')
    transform = item.get('transform').split()
    transform[9:11] = ['128', '128']
    item.set('transform', ' '.join(transform))
    matrix = part_config.find('metadata[@key="matrix"]')
    numbers = matrix.get('value').split()
    numbers[3] = numbers[7] = '128'
    matrix.set('value', ' '.join(numbers))
    for node in (obj, part_config):
        node.find('metadata[@key="name"]').set('value', Path(name).stem)
    obj.find('metadata[@face_count]').set('face_count', str(len(mesh.faces)))
    part_config.find('mesh_stat').set('face_count', str(len(mesh.faces)))
    native = target.lstrip('/')
    output = BytesIO()
    with ZipFile(output, 'w') as archive:
        for path, xml in ((MODEL, model), (MODEL_SETTINGS, config), (MODEL_RELS, relations),
                          ('_rels/.rels', package)):
            write_entry(archive, path, serialize(xml))
        for path in ('[Content_Types].xml', 'Metadata/project_settings.config'):
            write_entry(archive, path, source.read(path))
        write_entry(archive, native, replace_mesh(source.read(native), mesh, indexed=True))
    return output.getvalue()


def write_entry(archive, name, data):
    archive.writestr(ZipInfo(name), data, compress_type=ZIP_DEFLATED, compresslevel=9)


def build(project, output, include_jaw=True):
    report = {'source_project': project.name, 'source_project_sha256': sha256(project.read_bytes()).hexdigest(),
              'units': 'mm', 'bore_axis_in_print': 'X', 'parts': {}}
    with ZipFile(project) as source, ZipFile(output, 'w') as archive:
        model = etree.fromstring(source.read(MODEL))
        config = etree.fromstring(source.read(MODEL_SETTINGS))
        for part in PARTS:
            if part.blind_end_x_mm is not None and not include_jaw:
                continue
            original = load_print_mesh(source, model, config,
                                       Bore(part.name, part.object_id, 'C', 0, part.center_yz_mm,
                                            part.diameter_mm, part.wall_vertices))
            masks = wall_masks(original, part)
            samples = [(x, part.diameter_mm / 2) for x in part.sections_x_mm]
            if part.entry_section_x_mm is not None:
                samples.append((part.entry_section_x_mm, part.entry_diameter_mm / 2))
            baseline_minimum_wall = min(section_ligament(original, part.center_yz_mm, x, radius)
                                        for x, radius in samples)
            part_row = {'source_object_id': part.object_id, 'source_diameter_mm': part.diameter_mm,
                        'source_minimum_sampled_ligament_mm': round(baseline_minimum_wall, 4),
                        'sampled_sections_x_mm': [x for x, _ in samples], 'options': []}
            for diameter in part.diameters_mm:
                row = {'diameter_mm': diameter}
                if part.entry_diameter_mm is not None:
                    row['entry_diameter_mm'] = round(diameter + part.entry_diameter_mm - part.diameter_mm, 2)
                try:
                    if part.blind_end_x_mm is None:
                        name = f'{part.name}-D{diameter:.2f}.stl'
                        data, ligament = checked_variant(original, part, diameter, samples, masks)
                    else:
                        name = f'{part.name}-D{diameter:.2f}.3mf'
                        mesh, ligament = jaw_variant(original, part, diameter, samples, masks[2])
                        data = jaw_project(source, part, name, mesh)
                except ValueError as error:
                    row['omission'] = str(error)
                else:
                    write_entry(archive, name, data)
                    row.update(file=name, sha256=sha256(data).hexdigest(), minimum_sampled_ligament_mm=round(ligament, 4))
                part_row['options'].append(row)
            report['parts'][part.name] = part_row
        write_entry(archive, 'README.md', README)
        write_entry(archive, 'fit-c-variants.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--project', type=Path, default=PROJECT)
    parser.add_argument('--orbits-and-lids-only', action='store_true')
    args = parser.parse_args()
    parts = build(args.project, args.output, not args.orbits_and_lids_only)['parts']
    for name, part in parts.items():
        entries = part['options']
        print(name, sum('file' in row for row in entries), 'files',
              [row for row in entries if 'omission' in row])
