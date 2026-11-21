"""Export B25 motor-mount parts with selectable M2 shank clearance."""

from argparse import ArgumentParser
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from lxml import etree
from manifold3d import Error, Manifold
import numpy as np
import trimesh

from build_b20_print import MODEL, MODEL_SETTINGS
from build_b22_fused_skull import solid
from build_b25_pin_fit_options import PROJECT, load_print_mesh


@dataclass(frozen=True)
class Mount:
    part: str
    object_id: str
    plate: int
    motor_id: int
    bore: float
    # XY center, lowest and highest shank elevations, and mesh vertex count.
    seats: tuple[tuple[float, float, float, float, int], ...]


MOUNTS = (
    Mount('xl330_eye_yaw_front_plate', '50', 7, 1, 2.24, (
        (-14.3, -5.6, 0., 2.70, 252), (-14.3, 10.4, 0., .85, 252),
        (15.7, -5.6, 0., 2.70, 252), (15.7, 10.4, 0., 2.70, 252))),
    Mount('xl330_m077_eye_pitch_front_plate', '46', 7, 2, 2.24, (
        (17.5, -7.3, 0., 2.70, 252), (-12.5, -7.3, 0., 2.70, 252),
        (17.5, 8.7, 0., 2.70, 252), (-12.5, 8.7, 0., 2.70, 252))),
    Mount('xl330_m288_blink_front_plate', '44', 7, 3, 2.24, (
        (15., -11.4, 0., 1.00, 252), (-15., -11.4, 0., 2.70, 255),
        (15., 4.6, 0., .85, 252), (-15., 4.6, 0., 2.70, 252))),
    Mount('36_left_cheek_servo_stay', '84', 9, 6, 2.20, (
        (15., -.35, 24.35, 25.20, 274), (-15., -.35, 22.50, 25.20, 274),
        (15., 15.65, 22.50, 25.20, 274), (-15., 15.65, 24.10, 25.20, 274))),
)
DIAMETERS = (2.15, 2.20, 2.25, 2.30, 2.35)
TOLERANCE = .0001
READ_ME = '''# B25 XL330 M2 나사 통과홀 옵션

맞춤 게이지의 M2 행에 동봉한 PHS M2 TAP 나사를 대 봅니다. 나사가 출력물의
통과홀을 손으로 지나가고, 실제 부품과 모터 케이스의 네 구멍이 함께 맞는
크기를 선택합니다. 파일명 D 뒤의 값은 게이지와 같은 설계 지름(mm)입니다.
부품마다 고른 크기의 STL 한 개를 사용합니다.

| 원본 판 | 모터 ID와 부품 |
| --- | --- |
| 7 | ID1 모터판 39, ID2 모터판 42, ID3 모터판 46 |
| 9 | ID6 왼쪽 턱 모터 받침 36 |

STL은 B25 P2S 프로젝트에 놓인 방향으로 바닥을 Z=0에 맞췄습니다. 같은 판의
원본 부품을 바꾸고 PETG HF, 0.4 mm 노즐, 0.20 mm 층 및 원본 부품의 출력 설정을
적용합니다. 네 M2 통과홀의 지름만 달라집니다. 머리 자리와 깊이, 모터 접촉면 및
기준 나사의 배정은 B25 조립 자료를 따릅니다. 출력 뒤 작업대에서 동봉 나사로
통과홀과 머리 밀착을 확인합니다.
'''


def seat_masks(vertices, mount):
    for x, y, low, high, count in mount.seats:
        radial = vertices[:, :2] - (x, y)
        on_wall = np.isclose(np.linalg.norm(radial, axis=1), mount.bore / 2, rtol=0, atol=TOLERANCE)
        mask = on_wall & (vertices[:, 2] >= low - TOLERANCE) & (vertices[:, 2] <= high + TOLERANCE)
        if np.count_nonzero(mask) != count or not np.allclose(
                [vertices[mask, 2].min(), vertices[mask, 2].max()], [low, high], rtol=0, atol=TOLERANCE):
            raise ValueError(f'Unexpected shank geometry on ID{mount.motor_id} at {x, y}')
        yield (x, y), radial[mask], mask


def cut_expanded_bores(original, mount, diameter):
    # The enlarged bore edge can meet a shallow shelf. Cutting its cylinder
    # retriangulates the local surface without reusing a folded triangle.
    body = solid(original)
    for x, y, low, high, _ in mount.seats:
        bore = Manifold.cylinder(high-low+.02, diameter/2, circular_segments=126)
        body -= bore.translate((x, y, low-.01))
    if body.status() != Error.NoError or body.volume() >= original.volume:
        raise ValueError(f'The ID{mount.motor_id} bore cut did not produce a smaller solid')
    data = body.to_mesh64()
    return trimesh.Trimesh(data.vert_properties[:, :3], data.tri_verts, process=False)


def cross_2d(first, second):
    return first[..., 0]*second[..., 1] - first[..., 1]*second[..., 0]


def bore_radii(mesh, x, y, height):
    segments = trimesh.intersections.mesh_plane(mesh, (0, 0, 1), (0., 0., height))
    start, end = (segments[:, i, :2] - (x, y) for i in range(2))
    span = end - start
    angles = np.arange(180)*np.pi/90 + .001
    rays = np.column_stack((np.cos(angles), np.sin(angles)))[:, None, :]
    determinant = cross_2d(rays, span)
    with np.errstate(divide='ignore', invalid='ignore'):
        distance = cross_2d(start, span) / determinant
        fraction = cross_2d(start, rays) / determinant
    distance[(fraction < 0.) | (fraction > 1.) | (distance < 0.) | (abs(determinant) < 1e-10)] = np.inf
    return distance.min(axis=1)


def variants(original, mount):
    seats = tuple(seat_masks(original.vertices, mount))
    sections = []
    for x, y, low, high, _ in mount.seats:
        for height in np.linspace(low, high, 5)[1:-1]:
            source_radii = bore_radii(original, x, y, height)
            closed_ring = np.allclose(source_radii, mount.bore/2, rtol=0, atol=.001)
            sections.append((x, y, height, closed_ring))
    for diameter in DIAMETERS:
        vertices = original.vertices.copy()
        for center, radial, mask in seats:
            vertices[mask, :2] = center + radial * (diameter / mount.bore)
            if not np.allclose(np.linalg.norm(vertices[mask, :2] - center, axis=1),
                               diameter / 2, rtol=0, atol=TOLERANCE):
                raise ValueError(f'Incorrect shank diameter on ID{mount.motor_id}')
        mesh = trimesh.Trimesh(vertices, original.faces, process=False)
        if not np.all(np.einsum('ij,ij->i', mesh.face_normals, original.face_normals) > 0.):
            if diameter <= mount.bore:
                raise ValueError(f'A face changed direction at ID{mount.motor_id} Ø{diameter:.2f}')
            mesh = cut_expanded_bores(original, mount, diameter)
        if not np.array_equal(mesh.bounds, original.bounds) or not mesh.nondegenerate_faces().all():
            raise ValueError(f'Invalid mesh at ID{mount.motor_id} Ø{diameter:.2f}')
        stl = mesh.export(file_type='stl')
        imported = trimesh.load_mesh(BytesIO(stl), file_type='stl')
        if not imported.is_volume or imported.body_count != 1 or not imported.nondegenerate_faces().all():
            raise ValueError(f'Invalid exported STL at ID{mount.motor_id} Ø{diameter:.2f}')
        for x, y, height, closed_ring in sections:
            radii = bore_radii(imported, x, y, height)
            # ID3 already opens onto an edge above one shank. There, the
            # radius is limited by the bore wall wherever material remains.
            measured = radii if closed_ring else radii.min()
            if not np.allclose(measured, diameter/2, rtol=0, atol=.001):
                raise ValueError(f'Unexpected STL bore at ID{mount.motor_id} Ø{diameter:.2f}')
        yield diameter, len(mesh.faces), stl


def build(output):
    records = []
    with ZipFile(PROJECT) as source, ZipFile(output, 'w') as archive:
        model = etree.fromstring(source.read(MODEL))
        config = etree.fromstring(source.read(MODEL_SETTINGS))
        for mount in MOUNTS:
            plate, = config.xpath(f"plate[metadata[@key='plater_id'][@value='{mount.plate}']]")
            if plate.find(f"model_instance/metadata[@key='object_id'][@value='{mount.object_id}']") is None:
                raise ValueError(f'ID{mount.motor_id} is no longer on the expected B25 plate')
            mesh = load_print_mesh(source, model, config, mount)
            for diameter, facets, stl in variants(mesh, mount):
                name = f'plate-{mount.plate}/ID{mount.motor_id}-{mount.part}-D{diameter:.2f}.stl'
                archive.writestr(ZipInfo(name), stl, compress_type=ZIP_DEFLATED, compresslevel=9)
                records.append({'file': name, 'diameter_mm': diameter, 'facets': facets,
                                'sha256': sha256(stl).hexdigest()})
        archive.writestr(ZipInfo('README.md'), READ_ME, compress_type=ZIP_DEFLATED)
        manifest = {'source_3mf_sha256': sha256(PROJECT.read_bytes()).hexdigest(), 'parts': records}
        archive.writestr(ZipInfo('parts.json'), json.dumps(manifest, indent=2) + '\n', compress_type=ZIP_DEFLATED)
    return len(records)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(f'{build(args.output)} full-part STL files')
