"""Read revision-bound mechanical and physical acceptance records."""

from datetime import date
import json
import math
from pathlib import Path
import re
import tomllib


MECHANISMS = ('neck_yaw', 'neck_pitch', 'jaw', 'blink', 'eye_yaw', 'eye_pitch', 'cable_retention')
RECORD_IDS = tuple(f'P{i:02d}' for i in range(1, 9)) + tuple(f'M{i:02d}' for i in range(1, 10))
VERDICTS = {'PASS', 'FAIL'}
SERVICE_COVERS = {'rear-cable', 'bottom-board'}
TICK_DEGREES = 360 / 4096
B25_NECK_FEEDBACK_DEG = 8 * TICK_DEGREES
B25_YAW_MAX_TICKS = 640
B25_JAW_FEEDBACK_TICKS = 5
B25_JAW_COMMAND_TICKS = 62
PLACEHOLDERS = {'-', 'n/a', 'todo', 'tbd', '미측정', '해당 없음', '해당없음'}
REQUIRED_CASES = {
    'M02': {'neck_pitch', 'jaw', 'blink', 'eye_yaw', 'eye_pitch'},
    'M05': {'blink', 'jaw', 'eye_yaw', 'eye_pitch'},
    'M07': {'blink'},
    'M09': set(MECHANISMS),
}
MEASUREMENT_LIMITS = {
    'M02': ('M02_support', 'minimum_span_to_diameter', 'support_span_to_shaft_diameter', 'ratio', math.inf),
    'M07': ('M07_transmission', 'min_angle_deg', 'minimum_transmission_angle', 'deg', 90.0),
    'M09': ('M09_print_wall', 'minimum_thickness_mm', 'minimum_wall_thickness', 'mm', math.inf),
}


def unique_fields(pairs):
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError(f'중복 필드 {key}')
        fields[key] = value
    return fields


def required_text(value, label):
    if not isinstance(value, str) or not value.strip() or value.strip().lower() in PLACEHOLDERS:
        raise ValueError(f'{label}에 실제 기록이 필요합니다.')
    return value.strip()


def minimum_measurement_verdict(root, item, measurements, mechanism):
    section, key, metric, unit, ceiling = MEASUREMENT_LIMITS[item]
    criteria_path = root / 'spec' / 'criteria.toml'
    if not criteria_path.is_file():
        raise ValueError(f'{item} 측정 기준 파일이 없습니다.')
    criteria = tomllib.loads(criteria_path.read_text(encoding='utf-8'))
    minimum = criteria[section][key]
    if type(minimum) not in (int, float) or not (0 < minimum <= ceiling and minimum < math.inf):
        raise ValueError(f'{item} 최소 측정 기준을 올바르게 적어야 합니다.')
    values = [measurement['value'] for measurement in measurements if measurement['name'] == metric]
    wrong_unit = any(measurement['name'] == metric and measurement['unit'] != unit
                     for measurement in measurements)
    if not values or wrong_unit or not all(0 <= value <= ceiling for value in values):
        raise ValueError(f'{mechanism}에 {metric} ({unit}) 측정값이 필요합니다.')
    measured = min(values)
    return ('PASS' if measured >= minimum else 'FAIL'), measured, unit


def check_source(root, value, label):
    source = Path(required_text(value, label))
    resolved = (root / source).resolve()
    if source.is_absolute() or not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f'{label}을 찾을 수 없습니다. {source}')


def transmission_exception(root, mechanism, case, physical):
    evidence = case.get('exception')
    if mechanism != 'blink':
        return 'UNVERIFIED', f'{mechanism} 전달각 예외 근거 대기'
    if evidence is None:
        status = 'FAIL' if physical == 'FAIL' else 'UNVERIFIED'
        return status, f'눈꺼풀 전달각 예외 토크 근거 대기 · P03 {physical}'
    check_source(root, evidence['source'], '토크 근거 파일')
    required, stall = (evidence[key] for key in ('required_torque_Nm', 'stall_torque_Nm'))
    if (any(type(value) not in (float, int) or not math.isfinite(value) for value in (required, stall))
            or required < 0 or stall <= 0):
        raise ValueError('요구 토크와 정지 토크가 유효해야 합니다.')
    with (root / 'spec/criteria.toml').open('rb') as file:
        limit = tomllib.load(file)['M07_transmission']['max_stall_fraction']
    if not 0 < limit < 1:
        raise ValueError('정지 토크 대비 상한은 0과 1 사이여야 합니다.')
    ratio = required / stall
    status = 'FAIL' if ratio > limit else physical
    return status, f'눈꺼풀 토크 {required:.4f} N·m / 정지 토크 {stall:g} N·m ({ratio:.1%}, 상한 {limit:.0%}) · P03 {physical}'


def mechanical_record(root, item, record, physical):
    cases = record['cases']
    if not isinstance(cases, dict) or not cases or not set(cases).issubset(MECHANISMS):
        raise ValueError('지정된 7개 기구에서 판정할 항목을 기록해야 합니다.')
    if record['status'] == 'PASS' and set(cases) != set(MECHANISMS):
        raise ValueError('지정된 7개 기구 항목을 모두 기록해야 합니다.')
    measured, minima, exceptions = [], [], []
    for name, case in cases.items():
        status = case['status']
        if status == 'N/A':
            if name in REQUIRED_CASES.get(item, ()):
                raise ValueError(f'{name}은 이 항목에서 측정이 필요합니다.')
            required_text(case['reason'], f'{name} 적용 제외 이유')
            if 'measurements' in case:
                raise ValueError(f'{name} 적용 제외와 측정 기록이 함께 있습니다.')
            continue
        if status not in VERDICTS and (item != 'M07' or status != 'UNVERIFIED'):
            raise ValueError(f'{name} 판정은 PASS, FAIL, N/A 중 하나여야 합니다.')
        measurements = case['measurements']
        if not isinstance(measurements, list) or not measurements:
            raise ValueError(f'{name} 측정값이 없습니다.')
        for measurement in measurements:
            required_text(measurement['name'], f'{name} 측정 항목')
            required_text(measurement['unit'], f'{name} 단위')
            required_text(measurement['location'], f'{name} 측정 위치')
            value = measurement['value']
            if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
                raise ValueError(f'{name} 측정값은 유한한 수여야 합니다.')
            check_source(root, measurement['source'], f'{name} 근거 파일')
        if item in MEASUREMENT_LIMITS:
            verdict, value, unit = minimum_measurement_verdict(root, item, measurements, name)
            if item == 'M07' and verdict == 'FAIL':
                verdict, detail = transmission_exception(root, name, case, physical)
                exceptions.append(detail)
            if verdict != status and (item != 'M07' or status != 'UNVERIFIED'):
                raise ValueError(f'{name} 최소 측정값과 판정이 일치하지 않습니다.')
            minima.append(value)
            status = verdict
        measured.append(status)
    if not measured:
        raise ValueError('판정할 측정 항목이 없습니다.')
    status = 'FAIL' if 'FAIL' in measured else 'PASS'
    if item == 'M07' and status == 'PASS' and ('UNVERIFIED' in measured or set(cases) != set(MECHANISMS)):
        status = 'UNVERIFIED'
    if record['status'] != status and (item != 'M07' or record['status'] != 'UNVERIFIED'):
        raise ValueError('전체 판정과 기구별 판정이 일치하지 않습니다.')
    detail = f'기구 {len(measured)}개 측정, {len(cases) - len(measured)}개 적용 제외'
    if len(cases) < len(MECHANISMS):
        detail += f', {len(MECHANISMS) - len(cases)}개 미검증'
    if minima:
        suffix = '배' if unit == 'ratio' else f' {unit}'
        detail += f' · 최소 {min(minima):.3f}{suffix}'
    if exceptions:
        detail += ' · ' + ' · '.join(exceptions)
    return status, detail


def signed_angles(angles, label):
    if (not isinstance(angles, list) or len(angles) != 2
            or any(type(angle) not in (int, float) or not math.isfinite(angle) for angle in angles)
            or not angles[0] < 0 < angles[1]):
        raise ValueError(f'{label}은 같은 중립을 기준으로 음수 쪽과 양수 쪽 각도를 기록해야 합니다.')
    return angles


def check_b25_neck_stops(record):
    measurements = record['neck_stop_angles_deg']
    for axis, label in (('yaw', '목 좌우'), ('pitch', '목 상하')):
        values = measurements[axis]
        endpoints = signed_angles(values['endpoints'], f'{label} 설정 끝점')
        contacts = signed_angles(values['first_contacts'], f'{label} 첫 접촉각')
        if any(abs(contact) - abs(endpoint) - B25_NECK_FEEDBACK_DEG < 2
               for endpoint, contact in zip(endpoints, contacts)):
            raise ValueError(f'{label} 양쪽의 첫 접촉 여유는 피드백 허용치를 빼고 2° 이상이어야 합니다.')


def check_b25_camera_endpoints(record):
    endpoints = signed_angles(record.get('camera_yaw_endpoints_deg'), 'P07 실측 왕복 끝점')
    row = record.get('camera_yaw_calibration_ticks')
    if (not isinstance(row, list) or len(row) != 3
            or any(type(tick) is not int or not 0 <= tick <= 4095 for tick in row)
            or not min(row[0], row[2]) < row[1] < max(row[0], row[2])):
        raise ValueError('P07에는 시험한 펌웨어의 ID4 왼쪽, 중립, 오른쪽 보정 틱이 필요합니다.')
    spans = (abs(row[0] - row[1]), abs(row[2] - row[1]))
    if any(span > B25_YAW_MAX_TICKS for span in spans):
        raise ValueError('P07의 ID4 보정 끝점은 중립에서 각각 640틱 이내여야 합니다.')
    if any(abs(abs(endpoint) - span * TICK_DEGREES) > B25_NECK_FEEDBACK_DEG
           for endpoint, span in zip(endpoints, spans)):
        raise ValueError('P07 실측 왕복 끝점과 ID4 보정 끝점의 차이는 8틱(0.703125°) 이내여야 합니다.')


def physical_record(item, record):
    tester = required_text(record['tester'], '시험자')
    when = required_text(record['date'], '시험 날짜')
    observed = date.fromisoformat(when)
    if observed.isoformat() != when or observed > date.today():
        raise ValueError('시험 날짜를 실제 시험한 날의 YYYY-MM-DD로 적어야 합니다.')
    required_text(record['measurement'], '시험 방법')
    required_text(record['result'], '시험 결과')
    if item == 'P03':
        cycles, binds = record['cycles'], record['binding_events']
        if type(cycles) is not int or type(binds) is not int or not 0 <= binds <= cycles:
            raise ValueError('실제 깜빡임 횟수와 걸린 횟수를 기록해야 합니다.')
        if record['status'] == 'PASS' and (cycles < 50 or binds):
            raise ValueError('P03 합격에는 50회 이상 구동과 걸림 0회가 필요합니다.')
    if record.get('revision') == 'B25' and item == 'P04' and record['status'] == 'PASS':
        check_b25_neck_stops(record)
    if record.get('revision') == 'B25' and item == 'P06':
        drop, reserve = (record[key] for key in ('jaw_tip_drop_mm', 'jaw_stop_reserve_deg'))
        visible, limited = (record[key] for key in ('jaw_visible_drop', 'jaw_goal_pwm_verified'))
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (drop, reserve)):
            raise ValueError('턱 끝의 하강량(mm)과 스토퍼 여유(°)를 기록해야 합니다.')
        if type(visible) is not bool or type(limited) is not bool:
            raise ValueError('턱 끝이 눈에 보이게 내려갔는지와 Goal PWM 제한 확인 여부를 기록해야 합니다.')
        minimum_reserve = 1 if limited else 2
        if record['status'] == 'PASS':
            command = record.get('jaw_command_ticks')
            if type(command) is not int or command != B25_JAW_COMMAND_TICKS:
                raise ValueError('P06 합격에는 62틱 턱 열림 명령에서 잰 하강량이 필요합니다.')
            clear_ticks = record.get('jaw_last_clear_ticks')
            if (not isinstance(clear_ticks, list) or len(clear_ticks) != 2
                    or any(type(tick) is not int for tick in clear_ticks)
                    or not -4095 <= clear_ticks[0] < 0 < clear_ticks[1] <= 4095):
                raise ValueError('P06에는 같은 턱 영점에서 닫힘·열림 방향에서 닿지 않은 마지막 틱을 부호와 함께 기록해야 합니다.')
            closed_reserve = (-clear_ticks[0] - B25_JAW_FEEDBACK_TICKS) * TICK_DEGREES
            open_reserve = (clear_ticks[1] - command - B25_JAW_FEEDBACK_TICKS) * TICK_DEGREES
            if closed_reserve < 2 or open_reserve < minimum_reserve:
                raise ValueError('P06의 공통 영점에서 피드백을 빼고도 양쪽 스토퍼 여유를 확보해야 합니다.')
            if not visible or drop <= 0 or reserve < minimum_reserve:
                raise ValueError(f'P06 합격에는 눈에 보이는 턱 끝 하강과 스토퍼 여유 {minimum_reserve}° 이상이 필요합니다.')
    if record.get('revision') == 'B25' and item == 'P07':
        cycles, disconnects, reenumerations = (record[key] for key in (
            'camera_yaw_cycles', 'camera_usb_disconnects', 'camera_usb_reenumerations'))
        recognized = record['camera_recognized_after']
        if (any(type(count) is not int or count < 0 for count in (cycles, disconnects, reenumerations))
                or type(recognized) is not bool):
            raise ValueError('왕복·끊김·재인식 횟수와 시험 후 USB 인식을 기록해야 합니다.')
        if record['status'] == 'PASS':
            check_b25_camera_endpoints(record)
            if cycles < 100 or disconnects or reenumerations or not recognized:
                raise ValueError('P07 합격에는 100회 이상 왕복, USB 연속 인식과 시험 후 인식이 필요합니다.')
    if item == 'P08' and record['status'] == 'PASS':
        rework = record['unplanned_rework_count']
        covers = record['retained_nut_covers']
        if record['full_assembly'] is not True or type(rework) is not int or rework != 0 or (
                not isinstance(covers, list) or len(covers) != 2 or set(covers) != SERVICE_COVERS):
            raise ValueError('P08 합격에는 완성품 한 번 조립과 두 덮개 너트 보존 확인이 필요합니다.')
    return f'{when} {tester} 실물 기록'


def check_records(root: Path, rev: str, cad_hash: str) -> dict[str, tuple[str, str]]:
    root = root.resolve()
    if not rev or not re.fullmatch(r'[0-9a-f]{64}', cad_hash or ''):
        return {item: ('UNVERIFIED', '선택한 리비전과 CAD SHA-256이 필요합니다.') for item in RECORD_IDS}

    results = {}
    for item in RECORD_IDS:
        path = root / 'spec' / 'records' / f'{item}.json'
        try:
            record = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_fields)
            if record['revision'] != rev or record['cad_sha256'] != cad_hash:
                raise ValueError('리비전 또는 CAD SHA-256이 현재 조립본과 다릅니다.')
            status = record['status']
            if status not in VERDICTS and (item != 'M07' or status != 'UNVERIFIED'):
                raise ValueError('판정은 PASS 또는 FAIL이어야 합니다.')
            if item.startswith('M'):
                status, detail = mechanical_record(root, item, record, results['P03'][0])
            else:
                detail = physical_record(item, record)
        except FileNotFoundError:
            results[item] = ('UNVERIFIED', f'spec/records/{item}.json 없음')
        except (OSError, TypeError, ValueError, KeyError, OverflowError) as error:
            results[item] = ('UNVERIFIED', f'{item} 기록 확인 필요 · {error}')
        else:
            results[item] = (status, detail)
    return results
