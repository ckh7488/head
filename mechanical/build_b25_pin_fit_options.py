"""Export full B25 parts for the P3, P4 and S4 fit gauges."""

from argparse import ArgumentParser
import csv
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from lxml import etree
import numpy as np
import trimesh

from build_b20_print import CORE, MODEL, MODEL_SETTINGS, PRODUCTION


B25 = Path(__file__).resolve().parent / 'revisions/b25'
PROJECT = B25 / 'R5-B25-P2S.3mf'


@dataclass(frozen=True)
class Bore:
    part: str
    object_id: str
    gauge: str
    axis: int
    center: tuple[float, float]
    diameter: float
    wall_vertices: int


# Centers are the B25 3MF coordinates after centering XY and zeroing the bed plane.
BORES = (
    Bore('12_eye_tilt_cradle', '42', 'P3', 0, (-.42500308, 11.20000075), 3.24, 504),
    Bore('21_blink_shaft_crank_1', '74', 'P4', 2, (-1.52168347, -2.21562433), 4.26, 192),
    Bore('21_blink_shaft_crank_2', '78', 'P4', 2, (-.17450015, -1.42529869), 4.26, 188),
    Bore('21_blink_shaft_crank_3', '76', 'P4', 2, (-1.52168338, -2.21564341), 4.26, 188),
    Bore('45_blink_shaft_spacer_left', '80', 'S4', 2, (0., 0.), 4.26, 255),
    Bore('45_blink_shaft_spacer_right', '82', 'S4', 2, (0., 0.), 4.26, 256),
)
SIZES = {
    'P3': (3.14, 3.19, 3.24, 3.29, 3.34),
    'P4': (4.16, 4.21, 4.26, 4.31, 4.36),
    'S4': (4.45, 4.50, 4.55, 4.60, 4.65),
}
READ_ME = '''# B25 핀·축 구멍 크기별 출력물

`P3` 게이지에 표시된 설계 지름을 기준으로 12번 파일을 하나 고릅니다.
Ø2.991 ±0.001 mm × 13 mm 핀이 접착제 없이 손으로 양쪽 구멍에 들어가는 크기인지 확인합니다.
최종 조립에서는 12번 크래들 안에서만 핀을 고정하고 13번 지지대의 베어링 내륜은 건식으로 둡니다.

`P4`에는 실물 Ø4 h7 공용축을 대 보고 각 21번 크랭크 파일을 고릅니다.
크랭크를 축 평면에 고정했을 때 움직임이 없는지 작업대에서 확인합니다.

`S4`로 양쪽 45번 간격통 파일을 고릅니다. 축에 걸림 없이 들어가며 구멍과 축의 실측 지름 차가 0.30–0.50 mm인 크기를 고릅니다.
금속 외경은 마이크로미터나 캘리퍼스로 재고, 구멍은 핀 게이지 등으로 양쪽 입구를 확인합니다.
최종 출력물도 조립 전에 건식으로 검사합니다. 파일명의 수치는 모델 지름입니다.

B25 기준판과 같은 자세로 P2S, PETG HF, 0.4 mm 노즐, 0.20 mm 층으로 출력합니다.
STL의 바닥은 Z=0입니다. 기존 프로젝트의 해당 부품을 바꾸고 원본의 서포트와 출력 설정을 적용합니다.
P3 구멍의 축은 베드와 평행하고 P4와 S4 구멍의 축은 베드에 수직입니다.

12번의 두 바깥 Ø3.24 핀 자리와 21·45번의 Ø4.26 공용축 자리만 크기 옵션에 포함합니다.
기존 Ø2.20 드릴 및 Ø2.08–2.10 리머 가공 구멍, 21번의 링크 핀 파일럿, 체결과 걸림턱은 해당 부품의 B25 조립 절차를 따릅니다.
형상 확인은 원본 출력 메시와 수정 메시를 비교했습니다. 실제 끼움 결과는 서울 출력과 작업대 측정에서 기록합니다.
'''


def load_print_mesh(project, model, config, bore):
    resource = model.find(f'.//{CORE}object[@id="{bore.object_id}"]')
    component, = resource.find(CORE + 'components')
    name = config.find(f'object[@id="{bore.object_id}"]/metadata[@key="name"]').get('value')
    if not name.startswith(bore.part):
        raise ValueError(f'Unexpected print object for {bore.part}: {name}')
    path = component.get(PRODUCTION + 'path').lstrip('/')
    native = etree.fromstring(project.read(path))
    part = native.find(f'.//{CORE}object[@id="{component.get("objectid")}"]/{CORE}mesh')
    vertices = np.array([[float(v.get(axis)) for axis in 'xyz'] for v in part.find(CORE + 'vertices')])
    faces = np.array([[int(f.get(key)) for key in ('v1', 'v2', 'v3')] for f in part.find(CORE + 'triangles')])
    default_transform = '1 0 0 0 1 0 0 0 1 0 0 0'
    for item in (component, model.find(f'.//{CORE}item[@objectid="{bore.object_id}"]')):
        transform = np.array(item.get('transform', default_transform).split(), dtype=float).reshape(4, 3)
        vertices = vertices @ transform[:3] + transform[3]
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    origin = (low + high) / 2
    origin[2] = low[2]
    return trimesh.Trimesh(vertices - origin, faces, process=False)


def fit_parts(original, bore):
    axes = [axis for axis in range(3) if axis != bore.axis]
    radial = original.vertices[:, axes] - bore.center
    radius = np.linalg.norm(radial, axis=1)
    wall = np.isclose(radius, bore.diameter / 2, atol=.00003, rtol=0)
    if bore.gauge == 'P3':
        # The two outside rings receive the short pins. Interior relief shares the axis.
        wall &= np.abs(original.vertices[:, bore.axis]) > 57.
    if np.count_nonzero(wall) != bore.wall_vertices:
        raise ValueError(f'Unexpected bore tessellation for {bore.part}')

    for diameter in SIZES[bore.gauge]:
        vertices = original.vertices.copy()
        if diameter != bore.diameter:
            vertices[np.ix_(wall, axes)] += radial[wall] * ((diameter - bore.diameter) / (2 * radius[wall, None]))
        mesh = trimesh.Trimesh(vertices, original.faces, process=False)
        if (not mesh.is_volume or mesh.body_count != 1 or not mesh.nondegenerate_faces().all()
                or not np.allclose(mesh.bounds, original.bounds, atol=.000001, rtol=0)
                or np.any(np.einsum('ij,ij->i', mesh.face_normals, original.face_normals) <= 0)
                or not np.allclose(np.linalg.norm(mesh.vertices[wall][:, axes] - bore.center, axis=1),
                                   diameter / 2, atol=.00003, rtol=0)):
            raise ValueError(f'Invalid {bore.part} mesh at Ø{diameter:.2f} mm')
        if diameter != bore.diameter and (mesh.volume - original.volume) * (diameter - bore.diameter) >= 0:
            raise ValueError(f'Geometry moved in the wrong direction for {bore.part}')
        yield diameter, mesh


def build(output):
    records = []
    with ZipFile(PROJECT) as project, ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        model = etree.fromstring(project.read(MODEL))
        config = etree.fromstring(project.read(MODEL_SETTINGS))
        for bore in BORES:
            original = load_print_mesh(project, model, config, bore)
            for diameter, mesh in fit_parts(original, bore):
                name = f'{bore.gauge}/{bore.part}-D{diameter:.2f}.stl'
                stl = trimesh.exchange.stl.export_stl(mesh)
                imported = trimesh.load_mesh(BytesIO(stl), file_type='stl')
                if not imported.is_volume or imported.body_count != 1 or not imported.nondegenerate_faces().all():
                    raise ValueError(f'STL round trip is not a closed solid for {name}')
                write_member(archive, name, stl)
                records.append({'file': name, 'gauge': bore.gauge, 'modeled_diameter_mm': f'{diameter:.2f}',
                                'axis_to_bed': 'parallel' if bore.axis == 0 else 'perpendicular',
                                'facets': len(mesh.faces), 'volume_mm3': f'{mesh.volume:.6f}',
                                'sha256': sha256(stl).hexdigest()})
        csv_text = StringIO()
        writer = csv.DictWriter(csv_text, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
        write_member(archive, 'README.md', READ_ME)
        write_member(archive, 'parts.csv', csv_text.getvalue().encode('utf-8-sig'))
        source = {'P2S_3MF_SHA256': sha256(PROJECT.read_bytes()).hexdigest()}
        write_member(archive, 'source.json', json.dumps(source, indent=2) + '\n')
    return len(records)


def write_member(archive, name, contents):
    archive.writestr(ZipInfo(name), contents, compress_type=ZIP_DEFLATED, compresslevel=9)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(f'{build(args.output)} full-part STL files')
