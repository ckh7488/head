"""Read revision-bound mechanical and physical acceptance records."""

from datetime import date
import json
import math
from pathlib import Path
import re
import tomllib


MECHANISMS = ('neck_yaw', 'neck_pitch', 'jaw', 'blink', 'eye_yaw', 'eye_pitch', 'cable_retention')
RECORD_IDS = tuple(f'M{i:02d}' for i in range(1, 10)) + tuple(f'P{i:02d}' for i in range(1, 8))
VERDICTS = {'PASS', 'FAIL'}
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


def mechanical_record(root, item, record):
    cases = record['cases']
    if not isinstance(cases, dict) or not cases or not set(cases).issubset(MECHANISMS):
        raise ValueError('지정된 7개 기구에서 판정할 항목을 기록해야 합니다.')
    if record['status'] == 'PASS' and set(cases) != set(MECHANISMS):
        raise ValueError('지정된 7개 기구 항목을 모두 기록해야 합니다.')
    measured, minima = [], []
    for name, case in cases.items():
        status = case['status']
        if status == 'N/A':
            if name in REQUIRED_CASES.get(item, ()):
                raise ValueError(f'{name}은 이 항목에서 측정이 필요합니다.')
            required_text(case['reason'], f'{name} 적용 제외 이유')
            if 'measurements' in case:
                raise ValueError(f'{name} 적용 제외와 측정 기록이 함께 있습니다.')
            continue
        if status not in VERDICTS:
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
            source = Path(required_text(measurement['source'], f'{name} 근거 파일'))
            resolved = (root / source).resolve()
            if source.is_absolute() or not resolved.is_relative_to(root) or not resolved.is_file():
                raise ValueError(f'{name} 근거 파일을 찾을 수 없습니다. {source}')
        if item in MEASUREMENT_LIMITS:
            verdict, value, unit = minimum_measurement_verdict(root, item, measurements, name)
            if verdict != status:
                raise ValueError(f'{name} 최소 측정값과 판정이 일치하지 않습니다.')
            minima.append(value)
        measured.append(status)
    if not measured:
        raise ValueError('판정할 측정 항목이 없습니다.')
    if record['status'] != ('FAIL' if 'FAIL' in measured else 'PASS'):
        raise ValueError('전체 판정과 기구별 판정이 일치하지 않습니다.')
    detail = f'기구 {len(measured)}개 측정, {len(cases) - len(measured)}개 적용 제외'
    if len(cases) < len(MECHANISMS):
        detail += f', {len(MECHANISMS) - len(cases)}개 미검증'
    if minima:
        suffix = '배' if unit == 'ratio' else f' {unit}'
        detail += f' · 최소 {min(minima):.3f}{suffix}'
    return detail


def physical_record(record):
    tester = required_text(record['tester'], '시험자')
    when = required_text(record['date'], '시험 날짜')
    observed = date.fromisoformat(when)
    if observed.isoformat() != when or observed > date.today():
        raise ValueError('시험 날짜를 실제 시험한 날의 YYYY-MM-DD로 적어야 합니다.')
    required_text(record['measurement'], '시험 방법')
    required_text(record['result'], '시험 결과')
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
            if record['status'] not in VERDICTS:
                raise ValueError('판정은 PASS 또는 FAIL이어야 합니다.')
            detail = mechanical_record(root, item, record) if item.startswith('M') else physical_record(record)
        except FileNotFoundError:
            results[item] = ('UNVERIFIED', f'spec/records/{item}.json 없음')
        except (OSError, TypeError, ValueError, KeyError) as error:
            results[item] = ('UNVERIFIED', f'{item} 기록 확인 필요 · {error}')
        else:
            results[item] = (record['status'], detail)
    return results
