"""Read the B22 CAD evidence without requiring the geometry toolchain."""

import csv
from hashlib import file_digest, sha256
import json
from math import isclose, isfinite, sqrt
from pathlib import Path


REVISION = 'mechanical/revisions/b22'
PATH_CLEARANCE = {
    'head-frame': ('head_frame_clearance', 0.),
    'pitch-stop-link': ('pitch_link_clearance', 0.),
    'lid-left': ('lid_insertion_clearance', .20),
    'lid-right': ('lid_insertion_clearance', .20),
}
CAMERA_PATHS = {
    'camera-pcb-fit': ('camera_pcb_clearance', (.20, .20, 0.)),
    'camera-bezel': ('bezel_insertion_clearance', (.30,) * 6),
}
TOLERANCE_PAIRS = {
    pair: samples
    for lid, frame, eye, link in (
        ('Part078', 'Part076', 'Part029', 'Part057'),
        ('Part079', 'Part077', 'Part033', 'Part060'),
    )
    for pair, samples in (
        ((lid, frame), 93), ((lid, 'Part073'), 93), ((lid, eye), 2325), ((link, 'Part024'), 837)
    )
}


class Blocked(ValueError):
    """A named CAD witness recorded an actual obstruction."""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open('rb') as file:
        return file_digest(file, 'sha256').hexdigest()


def read(path):
    def unique(pairs):
        obj = dict(pairs)
        require(len(obj) == len(pairs), f'{path.name} 중복 항목')
        return obj

    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)


def reviewed(release, evidence, filename):
    path = release / filename
    require(digest(path) == evidence['reviewed_files_sha256'][filename], f'{filename} 근거 해시 불일치')
    return read(path)


def valid_number(value):
    return type(value) in (int, float) and isfinite(value)


def clear_list(value, label):
    require(isinstance(value, list), f'{label} 결과 목록 형식 오류')
    if value:
        raise Blocked(f'{label} {len(value)}건')


def clearance(value, required, label):
    require(valid_number(value), f'{label} 여유 미기록')
    if value <= 0 or value < required:
        raise Blocked(f'{label} {value:.3f} mm')


def witness(row, label):
    status = row['status']
    if status == 'fail':
        raise Blocked(label)
    require(status == 'pass', f'{label} 증거 없음')


def swept_solid(row, label, verify_envelope=False):
    witness(row, label)
    volume = row['swept_overlap_mm3']
    require(valid_number(volume) and volume >= 0, f'{label} 겹침량 미기록')
    if volume > 1e-7:
        raise Blocked(f'{label} 겹침 {volume:.3g} mm³')
    if verify_envelope:
        outside = row['material_outside_mm3']
        require(valid_number(outside) and 0 <= outside <= 1e-7, f'{label} 전체 외곽 경로 미확인')


def motion(evidence, verification, cad_hash):
    report = evidence['head_motion']
    require(report['cad_sha256'] == cad_hash, '구동 보고서 CAD 불일치')
    clear_list(report['collisions'], '구동 간섭')
    samples = report['pose_samples']
    require(type(samples) is int and samples > 0 and samples == verification['motion']['rigid_pose_samples']
            and type(report['pairs']) is int and report['pairs'] > 0, '구동 검사 범위 미기록')
    return 'UNVERIFIED', f'강체 부품·자세 조합 {samples:,}개에서 보고 간섭 0건 · 전 구간과 전체 배선 조합 미확인'


def tolerances(evidence, cad_hash):
    report = evidence['selected_tolerances']
    offset = report['relative_offset_each_axis_mm']
    require(report['cad_sha256'] == cad_hash and offset == .25, '공차 검사 CAD·조건 불일치')
    rows = report['interfaces']
    counts = {tuple(row['parts']): row['samples'] for row in rows}
    require(len(rows) == len(TOLERANCE_PAIRS) and counts == TOLERANCE_PAIRS, '눈꺼풀 공차 검사 범위 불완전')
    minima = []
    for row in rows:
        nominal, residual = row['nominal_min_mm'], row['assembly_bound_mm']
        require(valid_number(nominal) and valid_number(residual) and
                isclose(residual, nominal - sqrt(3) * offset, abs_tol=1e-9), '공차 계산 불일치')
        clearance(residual, 0., ' / '.join(row['parts']))
        minima.append(residual)
    return ('UNVERIFIED', f'눈꺼풀·링크 8쌍의 표본 자세, 상대 XYZ 각각 ±{offset:.2f} mm에서 최소 여유 '
            f'{min(minima):.3f} mm · 나머지 조인트와 복합 공차 미확인')


def stages(release, evidence, verification, cad_hash):
    plan = evidence['assembly_plan']
    rows = reviewed(release, evidence, 'assembly-check.json')
    plan_hash = sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    names = [step['id'] for step in plan]
    require(len(names) == len(set(names)) == verification['assembly']['steps'] == 136
            and plan_hash == verification['assembly']['plan_sha256'] == rows[0]['plan_sha256']
            and rows[0]['cad_sha256'] == cad_hash
            and names == [row['id'] for row in rows], '조립 순서·범위·CAD 불일치')
    for step, row in zip(plan, rows, strict=True):
        require(row['text'] == step['text'] and row['context'] == step['ctx']
                and isinstance(row['issues'], list), f'{step["id"]} 단계 기록 불일치')
    return list(zip(plan, rows, strict=True))


def guard(release, evidence, cad_hash):
    layout = reviewed(release, evidence, 'guard-layout.json')
    report = reviewed(release, evidence, 'guard-check.json')
    require(layout['source_sha256'] == report['head_cad_sha256'] == cad_hash
            and layout['guard_cad_sha256'] == report['guard_cad_sha256'], '보호 케이스 CAD 불일치')
    return layout, report


def assembly(operations, guard_report, cad_hash):
    for step, row in operations:
        name = step['id']
        issues = row['issues']
        require(all(isinstance(issue, str) for issue in issues), f'{name} 간섭 목록 형식 오류')
        clear_list([issue for issue in issues if not issue.endswith(' route unknown')], name)
        require(not issues, f'{name} 조립 경로 미확인')
        if name in PATH_CLEARANCE:
            field, reserve = PATH_CLEARANCE[name]
            clearance(row[field]['continuous_lower_bound_mm'], reserve, name)
        if name in CAMERA_PATHS:
            field, reserves = CAMERA_PATHS[name]
            points = step['path'][1]
            legs = row[field]
            require([(leg['start_mm'], leg['end_mm']) for leg in legs] == list(zip(points, points[1:])),
                    f'{name} 삽입 구간 불일치')
            for leg, reserve in zip(legs, reserves, strict=True):
                clearance(leg['continuous_lower_bound_mm'], reserve, name)
        if name == 'eye-tie':
            for key, offset in (('slide', .50), ('lower', .15)):
                leg = row['insertion_clearance'][key]
                require(leg['required_transverse_error_per_axis_mm'] == offset, f'{name} 조립 여유 조건 불일치')
                clearance(leg['continuous_lower_bound_mm'], sqrt(2) * offset, name)
        if 'camera_feed' in step:
            feed = row['camera_feed']
            require(all(feed[key] == value for key, value in step['camera_feed'].items()), f'{name} 플러그 경로 불일치')
            witness(feed, name)
            clearance(feed['minimum_clearance_mm'], 0., name)
        if 'integral_print' in step:
            require(row['integral_print'] == step['integral_print'], f'{name} 일체 출력 근거 없음')
        if name in ('neck-pins', 'neck-dowels'):
            trials = row['native_pin_passages']
            require(isinstance(trials, list) and bool(trials), f'{name} 정밀 핀 삽입 근거 없음')
            for trial in trials:
                require(trial['cad_sha256'] == cad_hash, f'{name} 핀 삽입 CAD 불일치')
                swept_solid(trial, name, verify_envelope=True)
        if name == 'jaw-bearing-fit':
            swept_solid(row['bearing_insertion'], name, verify_envelope=True)
        if name == 'camera-tray-bolts':
            for bolt in step['bolts']:
                swept_solid(row['camera_tray_head_passage'][bolt], bolt)
    roof = guard_report['assembly']
    clear_list(roof['roof_slide_obstructions'], '케이스 상판 삽입 간섭')
    clear_list(roof['rear_insertion_obstructions'], '케이스 뒷판 삽입 간섭')
    require(roof['passed'] is True and roof['positive_retention'] is True, '케이스 조립 근거 불완전')
    return 'PASS', 'B22 조립 136단계와 케이스 경로에서 막힘 0건 · 명목 CAD 표본과 별도 연속 삽입 증거'


def fused_skull(release, evidence, verification, cad_hash):
    slicing = reviewed(release, evidence, 'slicing-check.json')
    project = digest(release / 'R5-B22-P2S.3mf')
    fused = slicing['fused_front_skull']
    require(slicing['cad_sha256'] == cad_hash and slicing['project_sha256'] == project
            == verification['slicer']['project_sha256'] and fused['logical_cad_bodies'] == ['Part073', 'Part065']
            and fused['physical_plate4_parts'] == fused['positive_closed_print_bodies'] == 1,
            '4번 판 앞 외장·코받침 일체 출력 증거 불일치')


def tools(root, operations, hardware, spec, guard_layout, guard_report):
    # The final hardware overrides the two legacy C3 nut rows in the same order
    # as the CAD assembly generator.
    inventory = {row['id']: row['type'] for row in hardware['hardware'] if not row.get('tool')}
    modeled_screws = {row['name'] for row in spec if row.get('kind') in (None, 'set_screw')}
    with (root / 'mechanical/BOM.csv').open(encoding='utf-8-sig', newline='') as file:
        bom = list(csv.DictReader(file))
    nuts, held, bolts = set(), set(), set()
    for step, row in operations:
        stage = step['id']
        for role in ('nuts', 'nuts2'):
            if role in step:
                nuts.update(name for name in step[role][0] if inventory[name] == 'nut')
        drivers = step.get('bolts', ())
        holders = step.get('hold_nuts', {})
        bolts.update(drivers)
        held.update(holders)
        paired_tools = {'/'.join(pair): set(pair) for pair in step.get('paired_nuts', ())}
        paired_drivers = {'/'.join(pair) for pair in step.get('paired_drivers', ())}
        for field, keys in (
            ('driver_access', drivers), ('tool_access', holders),
            ('paired_tool_access', paired_tools), ('paired_driver_access', paired_drivers),
        ):
            actual = row.get(field, {})
            require(set(actual) == set(keys), f'{stage} {field} 검사 위치 불일치')
            for name, access in actual.items():
                witness(access, f'{stage}/{name} 공구 접근')
                if field == 'driver_access':
                    reach = access['straight_key_reach_mm']
                    require(valid_number(reach) and reach >= 12., f'{name} 렌치 진입 길이 미확인')
                elif field == 'tool_access':
                    require(access['tool'] in holders[name] and valid_number(access['travel_mm'])
                            and access['travel_mm'] > 0, f'{name} 너트 공구 경로 미확인')
                elif field == 'paired_tool_access':
                    require(set(access['insertion_order']) == paired_tools[name], f'{name} 두 공구 순서 불일치')
                else:
                    require(access['driver_axis_independent'] is True, f'{name} 동시 공구 접근 미확인')
        expected_angles = set(step.get('blink_access_checks_deg', ()))
        actual_angles = {case['blink_deg']: case for case in row.get('blink_access_cases', ())}
        require(actual_angles.keys() == expected_angles, f'{stage} 눈꺼풀 공구 자세 누락')
        for case in actual_angles.values():
            witness(case, f'{stage} 눈꺼풀 자세별 공구 접근')
            clear_list(case['blocking_pairs'], f'{stage} 자세별 공구 간섭')
    require(nuts == held and len(nuts) == sum(int(row['필요 수량']) for row in bom if row['구분'] == '너트')
            and len(bolts) == sum(int(row['필요 수량']) for row in bom if row['구분'] == '나사'),
            '조립 체결품 공구 검사와 BOM 수량 불일치')
    require(all(name in modeled_screws or inventory.get(name) in ('bolt', 'head') for name in bolts),
            '나사 형상 항목 누락')
    enclosure = guard_report['hardware']
    expected_guard = {row['id'] for row in guard_layout['fasteners']}
    guard_tools = enclosure['tools']
    require(len(expected_guard) == len(guard_tools) == 35
            and expected_guard == {row['id'] for row in guard_tools}, '케이스 체결 위치 확인 불완전')
    for row in guard_tools:
        clear_list(row['hex_blockers'], f'{row["id"]} 육각렌치 간섭')
        clear_list(row['spanner_blockers'], f'{row["id"]} 스패너 간섭')
        direction = row['spanner_direction']
        require(len(direction) == 3 and all(valid_number(v) for v in direction)
                and isclose(sum(v**2 for v in direction), 1., abs_tol=1e-6), f'{row["id"]} 스패너 방향 미기록')
    require(enclosure['passed'] is True, '케이스 공구 경로 근거 불완전')
    return ('PASS', f'본체 나사 {len(bolts)}곳, 너트 {len(nuts)}곳, 케이스 {len(guard_tools)}곳과 '
            '지정된 동시 공구 경로 확인')


def check_cad(root: Path) -> dict[str, tuple[str, str]]:
    def checked(function, *args):
        try:
            return function(*args)
        except Blocked as error:
            return 'FAIL', str(error)
        except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
            return 'UNVERIFIED', f'검사 근거 불완전 ({error})'

    release = root / REVISION
    try:
        verification = read(release / 'verification.json')
        evidence = read(release / 'cad-evidence.json')
        cad_hash = digest(release / 'R5-B22-Assembly.FCStd')
        require(evidence['revision'] == 'B22' and cad_hash == verification['cad_sha256'] == evidence['cad_sha256'],
                'B22 CAD 원본과 검사 기록 해시 불일치')
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {item: ('UNVERIFIED', f'B22 CAD 근거 불완전 ({error})')
                for item in ('C01', 'C02', 'C03', 'C04')}

    def assembly_or_tools(check):
        require(digest(root / 'mechanical/BOM.csv') == evidence['reviewed_bom_sha256'],
                '검증에 사용한 BOM과 현재 BOM의 해시 불일치')
        operations = stages(release, evidence, verification, cad_hash)
        layout, report = guard(release, evidence, cad_hash)
        if check == 'C02':
            fused_skull(release, evidence, verification, cad_hash)
            return assembly(operations, report, cad_hash)
        return tools(root, operations, reviewed(release, evidence, 'hardware.json'),
                     reviewed(release, evidence, 'hardware-spec.json'), layout, report)

    return {
        'C01': checked(motion, evidence, verification, cad_hash),
        'C02': checked(assembly_or_tools, 'C02'),
        'C03': checked(assembly_or_tools, 'C03'),
        'C04': checked(tolerances, evidence, cad_hash),
    }
