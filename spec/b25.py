"""Read B25 digital witnesses without borrowing verdicts from earlier releases."""

from math import isclose
from pathlib import Path

from cad import Blocked, digest, read, require, valid_number


RELEASE = Path('mechanical/revisions/b25')
CAD = RELEASE / 'R5-B25-Assembly.FCStd'
FIRMWARE = Path('control/openrb/R5B1/R5B1.ino')
JAW_PAIR = ['Jaw_37_right_jaw_bearing_stay', 'Jaw_39_right_jaw_pivot_arm']
JAW_TICKS = 62
JAW_STOP_RESERVE = 1.0
MOVING_CLEARANCE = .30


def checked(check, *args):
    try:
        return check(*args)
    except Blocked as error:
        return 'FAIL', str(error)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        return 'UNVERIFIED', f'B25 근거 확인 필요 ({error})'


def current_report(root, path, cad_hash, *, firmware=False):
    report = read(root / path)
    require(report['cad_sha256'] == cad_hash, f'{path.name} CAD 해시 불일치')
    if firmware:
        require(report['firmware_sha256'] == digest(root / FIRMWARE), f'{path.name} 펌웨어 해시 불일치')
    return report


def sightlines(root, criteria, cad_hash):
    report = current_report(root, RELEASE / 'sightlines.json', cad_hash, firmware=True)
    require(report['scene'] == criteria['S02_look_up'] and
            report['camera_hfov_deg'] == criteria['S01_walk_by']['camera_hfov_deg'],
            'S02 설치 조건 또는 수평 화각 불일치')
    pupils = report['pupils']
    require(len(pupils) == 2 and {row['part'] for row in pupils} == {'Part031', 'Part035'},
            '양쪽 동공 측정 근거 필요')
    contacts = [report['camera_opaque_contacts'], *(row['opaque_contacts'] for row in pupils)]
    require(all(isinstance(row, list) and all(isinstance(part, str) and part for part in row)
                for row in contacts) and type(report['camera_in_frame']) is bool, '광선 검사 기록 형식 오류')
    if any(contacts) or not report['camera_in_frame']:
        raise Blocked('현재 B25 CAD에서 카메라 또는 동공의 목표 광선이 가려지거나 화각을 벗어납니다.')
    margins = []
    for pupil in pupils:
        required, maximum = (pupil[key] for key in ('required_elevation_deg', 'max_elevation_deg'))
        require(all(valid_number(angle) for angle in (required, maximum)), '동공 상향각 미기록')
        if maximum < required:
            raise Blocked(f'{pupil["part"]} 최대 {maximum:.2f}° / 필요 {required:.2f}°')
        if pupil['eye_pitch_solution_deg'] is None and report['status'] == 'fail':
            raise Blocked(f'{pupil["part"]} 보정 범위에서 목표 동공 방향에 도달하지 못합니다.')
        require(valid_number(pupil['eye_pitch_solution_deg']), f'{pupil["part"]} 목표 각도 해 미기록')
        margins.append((maximum - required, maximum, required))
    require(report['status'] == 'pass', 'S02 수치와 판정 불일치')
    margin, maximum, required = min(margins)
    return 'PASS', f'양쪽 동공 상향각 최대 {maximum:.2f}° / 필요 {required:.2f}°, 최소 여유 {margin:.2f}° · 카메라와 동공 광선 통과'


def jaw_opening(root, cad_hash):
    report = current_report(root, Path('control/jaw-opening-check.json'), cad_hash, firmware=True)
    require(report['pair'] == JAW_PAIR and report['goal_span_max_ticks'] == JAW_TICKS and
            report['required_stop_reserve_deg'] == JAW_STOP_RESERVE, '턱 62틱·스토퍼 검사 조건 불일치')
    drop, reserve, endpoint, proof_end, contact = (report[key] for key in (
        'jaw_tip_drop_at_goal_mm', 'reserve_from_accepted_feedback_at_least_deg',
        'accepted_feedback_max_encoder_deg', 'contact_free_through_deg_in_relative_envelope',
        'earliest_sampled_contact_deg'))
    require(all(valid_number(value) for value in (drop, reserve, endpoint, proof_end, contact)), '턱 수치 근거 누락')
    if drop <= 0 or contact < endpoint + JAW_STOP_RESERVE:
        raise Blocked(f'턱 하강 {drop:.3f} mm · 피드백 끝점에서 실제 모형 접촉까지 {contact-endpoint:.3f}°')
    closing = report['closing']
    close_angle = closing['clear_through_cad_angle_deg']
    zero_ticks, feedback_ticks = report['closed_reference_from_cad_ticks'], report['feedback_opening_allowance_ticks']
    close_margin = closing['reserve_from_accepted_feedback_at_least_deg']
    require(closing['pair'] == ['Part073', 'Jaw_30_moving_jaw']
            and type(zero_ticks) is int and type(feedback_ticks) is int and feedback_ticks >= 0
            and valid_number(close_angle) and valid_number(close_margin) and close_margin >= 2
            and isclose((zero_ticks - feedback_ticks) * 360 / 4096 - close_angle, close_margin, abs_tol=1e-9)
            and valid_number(closing['continuous_lower_gap_mm']) and closing['continuous_lower_gap_mm'] > 0
            and type(closing['verified_cells']) is int and closing['verified_cells'] > 0,
            '같은 턱 보정 영점에서 닫힘 방향 2° 여유를 증명한 기록이 필요합니다.')
    powered = report['powered_clearance']
    require(isclose(reserve, proof_end - endpoint, abs_tol=1e-9) and reserve >= JAW_STOP_RESERVE and
            type(report['verified_cells']) is int and report['verified_cells'] > 0 and
            valid_number(report['continuous_lower_gap_mm']) and report['continuous_lower_gap_mm'] > 0 and
            powered['end_deg'] == endpoint and powered['required_mm'] == MOVING_CLEARANCE and
            valid_number(powered['minimum_mm']) and powered['minimum_mm'] >= MOVING_CLEARANCE and
            type(powered['verified_cells']) is int and powered['verified_cells'] > 0,
            '턱 가동 간극과 스토퍼 여유의 연속 증거 불완전')
    return ('PASS', f'62틱 CAD 하강 {drop:.3f} mm · 해당 스토퍼 쌍 가동 틈 하한 {powered["minimum_mm"]:.3f} mm · '
            f'피드백을 포함한 여유 하한 닫힘 {close_margin:.3f}°, 열림 {reserve:.3f}°')


def assembly_checks():
    return {
        'C01': ('UNVERIFIED', 'B25 실가동 범위의 강체·체결품·가동 배선 전 구간 증거 필요'),
        'C02': ('UNVERIFIED', 'B25 조립 순서대로 전체 삽입 경로와 안착을 검사한 증거 필요'),
        'C03': ('UNVERIFIED', 'B25 체결 위치별 L자 렌치·스패너 및 동시 진입 경로 증거 필요'),
        'C04': ('UNVERIFIED', 'B25 가동부 및 고정부 허용치별 최악 공차 증거 필요 · 오른쪽 턱 받침/요크는 P08에서 실측'),
        'S06': ('UNVERIFIED', 'B25 전체 체결 위치와 지정 구매품 나사·무두나사 예외를 대조한 기록 필요'),
    }
