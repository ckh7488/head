"""Kinematic screening of the B22 scenes from the released control sources."""

from dataclasses import dataclass
from hashlib import file_digest
import json
import math
from pathlib import Path
import re
import runpy


STEP_S = .005
CAMERA_FPS = 30
BLINK_OPEN_DEG = 5.
BLINK_SHUT_DEG = 85.


@dataclass(frozen=True)
class RateModel:
    speed: tuple[float, ...]
    goal_period: float
    report_period: float

    @classmethod
    def read(cls, root):
        source = (root / 'control/openrb/R5B1/R5B1.ino').read_text(encoding='utf-8')
        speeds = re.search(r'\bvelocity\[count\]\s*=\s*\{([^}]+)\}', source)
        goal = re.search(r'\bgoalPeriodMs\s*=\s*(\d+)', source)
        report = re.search(r'\breportMs\s*=\s*(\d+)', source)
        if speeds is None or goal is None or report is None:
            raise ValueError('Could not read the OpenRB drive profile and communication periods.')
        # Profile Velocity uses 0.229 rpm per register unit. The sixth axis is the jaw.
        speed = tuple(float(value) * .229 * 6 for value in speeds[1].split(','))
        if len(speed) != 6 or min(speed) <= 0 or int(goal[1]) <= 0 or int(report[1]) <= 0:
            raise ValueError('Invalid OpenRB profile velocities or communication period.')
        return cls(speed[:5], int(goal[1]) / 1000, int(report[1]) / 1000)


def _simulate(model, planner, bearing, duration, latency, hfov, start, blink=False):
    """Use ideal detections in the angular window and acceleration-free joints.

    A 30 Hz capture arrives after a fixed delay. Firmware goals are sampled every
    goal period, and feedback reflects the separate report period. Profile acceleration,
    encoder calibration, bus errors, load and camera detection are outside this model.
    """
    position = list(start)
    goal = feedback = tuple(start)
    pending = None
    frame_index = 0
    next_goal = next_report = 0.
    active = False
    missed = losses = 0
    first_seen = None
    history, samples = [], []
    for tick in range(math.ceil(duration / STEP_S) + 1):
        t = min(tick * STEP_S, duration)
        history.append(position[3])
        if t + 1e-9 >= next_report:
            feedback = tuple(position)
            next_report += model.report_period
        capture = frame_index / CAMERA_FPS
        if t + 1e-9 >= capture + latency:
            frame_index += 1
            sample = capture / STEP_S
            lower = min(int(sample), len(history) - 1)
            upper = min(lower + 1, len(history) - 1)
            capture_neck = history[lower] + (sample - lower) * (history[upper] - history[lower])
            relative = bearing(capture) - capture_neck
            error = (relative, 0.) if abs(relative) <= hfov / 2 else None
            if error is None:
                missed += 1
            elif first_seen is None:
                first_seen = t
            decision = planner.step(error, feedback, t, blink_enabled=blink)
            if decision.active:
                pending = decision.goals
            elif active:
                losses += 1
                goal, pending = tuple(position), None
            active = decision.active
        if t + 1e-9 >= next_goal:
            if pending is not None:
                goal, pending = pending, None
            next_goal += model.goal_period
        samples.append((t, bearing(t), position[3], position[0], position[2]))
        dt = min(STEP_S, duration - t)
        for axis, limit in enumerate(model.speed):
            change = goal[axis] - position[axis]
            position[axis] += min(limit*dt, max(-limit*dt, change))
    return samples, missed, losses, first_seen


def _walk(model, track, c):
    distance, speed = c['distance_m'], c['walk_speed_mps']

    def bearing(t):
        return math.degrees(math.atan2(-4. + speed*t, distance))

    zero, limits = track['ZERO'], track['LIMITS']
    start_neck = track['clamp'](bearing(0), *limits[3])
    pre_acquired = (0., 0., 0., start_neck, 0.)
    measured = []
    passed = False
    for primary, name, pose in ((True, '평가: 카메라를 시작 쪽에 미리 둠', pre_acquired),
                                (False, '참고: 정면 시작', zero)):
        trace, missed, losses, first = _simulate(model, track['Planner'](), bearing, 8/speed,
                                                 c['camera_latency_s'], c['camera_hfov_deg'], pose)
        inside = [item for item in trace if abs(item[1]) <= 80.]
        ratio = sum(abs(target - neck - eye) <= c['gaze_ok_deg']
                    for _, target, neck, eye, _ in inside) / len(inside)
        if primary:
            passed = ratio >= c['min_ok_ratio'] and not missed
        acquired = f'첫 포착 {first:.2f}초' if first is not None else '포착 없음'
        measured.append(f'{name} {ratio:.1%}, {acquired}, 화각 이탈 프레임 {missed}개, 재이탈 {losses}회')
    start_bearing = abs(bearing(0.))
    context = (f'{distance:g} m 앞을 {speed:g} m/s로 좌우 4 m씩 이동, ±80° 구간 기준. '
               f'30 fps, 지연 {c["camera_latency_s"]:g}초, 수평 화각 {c["camera_hfov_deg"]:g}°를 '
               f'가정한 속도 제한 모델. 목표 갱신 {model.goal_period*1000:g} ms, '
               f'위치 보고 {model.report_period*1000:g} ms. 정면 시작에서는 대상의 첫 방향 {start_bearing:.1f}°가 '
               f'카메라 반화각 {c["camera_hfov_deg"]/2:g}°보다 커 최초 검출까지 정지. '
               '실제 영상 검출과 모터 하중은 실물에서 확인.')
    return ('PASS' if passed else 'FAIL', ' / '.join(measured) + '. ' + context)


def _turn(model, track, c, camera):
    distance = abs(c['target_deg'])
    measured = []
    passed = True
    for direction in (-1, 1):
        target = direction * distance
        trace, missed, _, _ = _simulate(model, track['Planner'](), lambda _: target, 4.,
                                         camera['camera_latency_s'], camera['camera_hfov_deg'], track['ZERO'])
        over = max(0., max(direction*neck for _, _, neck, _, _ in trace) - distance)
        _, _, neck, eye, _ = trace[-1]
        error = abs(target - neck - eye)
        passed &= over <= c['max_neck_overshoot_deg'] and error <= c['max_final_gaze_err_deg']
        measured.append(f'{target:+g}° 목 넘침 {over:.2f}°, 4초 모형 수평 시선 오차 {error:.2f}°, 화각 이탈 {missed}프레임')
    return ('PASS' if passed else 'FAIL', ' / '.join(measured) + '. 속도 제한 모델에서의 결과.')


def _rotate_x(point, angle, pivot=(0., 0., 0.)):
    x, y, z = point
    _, y0, z0 = pivot
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return x, y0 + (y-y0)*cosine - (z-z0)*sine, z0 + (y-y0)*sine + (z-z0)*cosine


def _elevation(vector):
    return math.degrees(math.atan2(vector[2], math.hypot(*vector[:2])))


def _look_up(root, track, c):
    release = root / 'mechanical/revisions/b22'
    try:
        sightlines = json.loads((release / 'sightlines.json').read_text(encoding='utf-8'))
        with (release / 'R5-B22-Assembly.FCStd').open('rb') as file:
            cad_hash = file_digest(file, 'sha256').hexdigest()
    except FileNotFoundError:
        return 'UNVERIFIED', '릴리스 CAD와 중립 동공 방향의 추출 기록이 필요합니다.'
    if cad_hash != sightlines['cad_sha256']:
        return 'UNVERIFIED', '중립 동공 방향 기록의 CAD 해시가 현재 릴리스와 다릅니다.'

    neck, eye = (-track['LIMITS'][axis][0] for axis in (4, 1))
    base = c['base_tilt_deg']
    chain = tuple((-angle, sightlines[f'{axis}_pitch_pivot_mm'])
                  for angle, axis in ((eye, 'eye'), (neck, 'neck'), (base, 'base')))
    x, y, z = _rotate_x(sightlines['eye_pitch_pivot_mm'], *chain[-1])
    height = c['person_eye_height_m'] - c['head_height_m']
    target = x, y - 1000*c['distance_m'], z + 1000*height
    bounds = []
    for pupil in sightlines['pupils']:
        center = pupil['center_mm']
        for angle, pivot in chain:
            center = _rotate_x(center, angle, pivot)
        required = _elevation(tuple(t-p for t, p in zip(target, center, strict=True)))
        limit = _elevation(_rotate_x(pupil['axis_unit'], -(base+neck+eye)))
        bounds.append((required-limit, required, limit, -_elevation(pupil['axis_unit'])))
    shortage, required, limit, downward = max(bounds)
    return ('FAIL' if shortage > 0. else 'PASS',
            f'정면 CAD 동공 기준 최대 {limit:.2f}° / 필요 {required:.2f}°, '
            f'{"부족" if shortage > 0. else "여유"} {abs(shortage):.2f}°. '
            f'눈 중심 높이는 설치 후 중립 기준이며, 중립 동공은 아래로 {downward:.2f}°를 향함. '
            f'받침 {base:g}°의 실제 고정·안정성과 시선은 P05에서 확인.')


def _first_blink(trace):
    started = shut = left_shut = None
    for (t0, _, _, _, a0), (t1, _, _, _, a1) in zip(trace, trace[1:]):
        if a0 == a1:
            continue
        if started is None and a0 <= BLINK_OPEN_DEG < a1:
            started = t0 + (t1-t0) * (BLINK_OPEN_DEG-a0)/(a1-a0)
        if started is not None and shut is None and a0 < BLINK_SHUT_DEG <= a1:
            shut = t0 + (t1-t0) * (BLINK_SHUT_DEG-a0)/(a1-a0)
        if shut is not None and a0 >= BLINK_SHUT_DEG > a1:
            left_shut = t0 + (t1-t0) * (BLINK_SHUT_DEG-a0)/(a1-a0)
        if started is not None and a0 > BLINK_OPEN_DEG >= a1:
            if shut is None or left_shut is None:
                return None
            finished = t0 + (t1-t0) * (BLINK_OPEN_DEG-a0)/(a1-a0)
            return finished-started, shut-started, finished-left_shut
    return None


def _blink(model, track, c):
    planner = track['Planner']()
    planner.step((0., 0.), track['ZERO'], -1.)
    planner.next_blink = 0.
    trace, _, _, _ = _simulate(model, planner, lambda _: 0., 3., 0., 106., track['ZERO'], blink=True)
    cycle = _first_blink(trace)
    assumed_encoder_span_ticks = 1024
    shaft_span_deg = assumed_encoder_span_ticks * 360 / 4096
    shaft_travel_deg = (BLINK_SHUT_DEG - BLINK_OPEN_DEG) * shaft_span_deg / track['LIMITS'][2][1]
    bound = 2 * shaft_travel_deg / model.speed[2]
    context = (f'논리 90°에 엔코더 {assumed_encoder_span_ticks}틱(모터축 {shaft_span_deg:g}°)을 대응시킨 '
               f'명목 모델. 축 속도 상한 {model.speed[2]:.2f}°/s에서 5°↔85° 왕복 하한 {bound:.3f}초 '
               '(가속·정지 시간 제외). 실제 보정 폭, 눈꺼풀 닫힘과 링크 진동은 P03에서 확인.')
    if cycle is None:
        return 'FAIL', '모델의 첫 깜빡임이 5°에서 85°를 지나 다시 5°까지 돌아오지 않음. ' + context
    total, close, reopen = cycle
    passed = (c['min_total_s'] <= total <= c['max_total_s'] and bound <= c['max_total_s']
              and (not c['close_not_slower_than_open'] or close <= reopen))
    return ('PASS' if passed else 'FAIL',
            f'첫 깜빡임 모델 전체 {total:.3f}초, 닫기 {close:.3f}초, 뜨기 {reopen:.3f}초. ' + context)


def check_scenes(root: Path, criteria: dict) -> dict[str, tuple[str, str]]:
    track = runpy.run_path(str(root / 'control/pc/track.py'))
    model = RateModel.read(root)
    walk = criteria['S01_walk_by']
    return {'S01': _walk(model, track, walk),
            'S01b': _turn(model, track, criteria['S01b_no_whip'], walk),
            'S02': _look_up(root, track, criteria['S02_look_up']),
            'S03': _blink(model, track, criteria['S03_blink'])}
