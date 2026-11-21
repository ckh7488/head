"""Kinematic screening of the B22 scenes from the released control sources."""

from dataclasses import dataclass, field
from hashlib import file_digest
import json
import math
from pathlib import Path
import random
import re
import runpy


STEP_S = .005
CAMERA_FPS = 30
BLINK_OPEN_DEG = 5.
BLINK_SHUT_DEG = 85.
POSITION_TICK_DEG = 360. / 4096
VELOCITY_UNIT_DEG_S = .229 * 6


@dataclass(frozen=True)
class RateModel:
    speed: tuple[float, ...]
    goal_period: float
    report_period: float
    exhibit_neck_speed: tuple[float, float] | None = None
    return_neck_speed: tuple[float, float] | None = None

    @classmethod
    def read(cls, root):
        source = (root / 'control/openrb/R5B1/R5B1.ino').read_text(encoding='utf-8')
        speeds = re.search(r'\bvelocity\[count\]\s*=\s*\{([^}]+)\}', source)
        goal = re.search(r'\bgoalPeriodMs\s*=\s*(\d+)', source)
        report = re.search(r'\breportMs\s*=\s*(\d+)', source)
        if speeds is None or goal is None or report is None:
            raise ValueError('Could not read the OpenRB drive profile and communication periods.')
        # Profile Velocity uses 0.229 rpm per register unit. The sixth axis is the jaw.
        speed = tuple(float(value) * VELOCITY_UNIT_DEG_S for value in speeds[1].split(','))
        if len(speed) != 6 or min(speed) <= 0 or int(goal[1]) <= 0 or int(report[1]) <= 0:
            raise ValueError('Invalid OpenRB profile velocities or communication period.')
        profiles = []
        for name in ('exhibitYawVelocity', 'exhibitPitchVelocity', 'returnNeckVelocity'):
            match = re.search(rf'\b{name}\s*=\s*(\d+)\b', source)
            profiles.append(int(match[1]) * VELOCITY_UNIT_DEG_S if match else 0.)
        yaw, pitch, returning = profiles
        return cls(speed[:5], int(goal[1]) / 1000, int(report[1]) / 1000,
                   (yaw, pitch) if yaw and pitch else None, (returning, returning) if returning else None)


@dataclass(frozen=True)
class Frame:
    captured_at: float
    arrived_at: float
    detected: bool
    phase: str


@dataclass
class ExhibitTrace:
    frames: list[Frame] = field(default_factory=list)
    poses: list[tuple[float, tuple[float, ...]]] = field(default_factory=list)


def _camera_error(yaw, pitch, camera_pitch, hfov):
    yaw, pitch, tilt = map(math.radians, (yaw, pitch, camera_pitch))
    x = math.sin(yaw) * math.cos(pitch)
    y = math.sin(pitch) * math.cos(tilt) - math.cos(yaw) * math.cos(pitch) * math.sin(tilt)
    z = math.sin(pitch) * math.sin(tilt) + math.cos(yaw) * math.cos(pitch) * math.cos(tilt)
    edge = math.tan(math.radians(hfov / 2))
    if z <= 0. or abs(x) > z * edge or abs(y) > z * edge * 720 / 1280:
        return None
    return math.degrees(math.atan2(x, z)), math.degrees(math.atan2(y, math.hypot(x, z)))


def _simulate(model, planner, bearing, duration, latency, hfov, start, *,
              blink=False, target_pitch=0., hide_at=None):
    """Use ideal detections in the angular window and acceleration-free joints.

    A 30 Hz capture arrives after a fixed delay. Firmware goals are sampled every
    goal period, and feedback reflects the separate report period. Profile acceleration,
    encoder calibration, bus errors, load and camera detection are outside this model.
    """
    position = list(start)
    joint_speed = model.speed
    goal = feedback = tuple(start)
    pending = None
    frame_index = 0
    next_goal = next_report = 0.
    active = False
    history = []
    trace = ExhibitTrace()
    for tick in range(math.ceil(duration / STEP_S) + 1):
        t = min(tick * STEP_S, duration)
        history.append(tuple(position[3:5]))
        if t + 1e-9 >= next_report:
            feedback = tuple(position)
            next_report += model.report_period
        capture = frame_index / CAMERA_FPS
        if t + 1e-9 >= capture + latency:
            frame_index += 1
            sample = capture / STEP_S
            lower = min(int(sample), len(history) - 1)
            upper = min(lower + 1, len(history) - 1)
            capture_yaw, capture_pitch = (a + (sample - lower) * (b - a)
                                          for a, b in zip(history[lower], history[upper], strict=True))
            error = _camera_error(bearing(capture) - capture_yaw, target_pitch, capture_pitch, hfov)
            if hide_at is not None and capture >= hide_at:
                error = None
            decision = planner.step(error, feedback, t, blink_enabled=blink)
            trace.frames.append(Frame(capture, t, error is not None, decision.phase))
            if decision.active:
                pending = decision.goals, decision.phase
            elif active:
                goal, pending = tuple(position), None
            active = decision.active
        if t + 1e-9 >= next_goal:
            if pending is not None:
                goal, phase = pending
                pending = None
                neck_speed = model.return_neck_speed if phase == 'RETURN' else model.exhibit_neck_speed
                joint_speed = model.speed[:3] + neck_speed
            next_goal += model.goal_period
        trace.poses.append((t, tuple(position)))
        dt = min(STEP_S, duration - t)
        for axis, limit in enumerate(joint_speed):
            change = goal[axis] - position[axis]
            position[axis] += min(limit*dt, max(-limit*dt, change))
    return trace


def _neck_speed(poses, since=0.):
    speeds = (math.hypot(b[3] - a[3], b[4] - a[4]) / (t1 - t0)
              for (t0, a), (t1, b) in zip(poses, poses[1:]) if t0 >= since and t1 > t0)
    return max(speeds, default=0.)


def _walk_case(model, track, c, direction):
    distance, speed, scoring_range = c['distance_m'], c['walk_speed_mps'], c['scoring_range_deg']
    extent = distance * math.tan(math.radians((scoring_range + 90.) / 2))
    duration = 2 * extent / speed
    score_end = (extent + distance * math.tan(math.radians(scoring_range))) / speed

    def bearing(t):
        return direction * math.degrees(math.atan2(-extent + speed * t, distance))

    run = _simulate(model, track['Planner'](exhibit=True), bearing, duration,
                    c['camera_latency_s'], c['camera_hfov_deg'], track['ZERO'])
    first = next((frame for frame in run.frames if frame.detected and
                  abs(bearing(frame.captured_at)) <= scoring_range), None)
    label = '왼→오' if direction > 0 else '오→왼'
    if first is None:
        return False, f'{label}: 평가 구간에서 얼굴 검출 없음'
    peak = _neck_speed(run.poses)
    tracking = next((frame.arrived_at for frame in run.frames if first.captured_at <= frame.captured_at
                     and frame.detected and frame.phase == 'TRACK'), None)
    if tracking is None:
        return False, f'{label}: 추적에 들어가지 못함'
    error = [(t, abs(bearing(t) - pose[3] - pose[0])) for t, pose in run.poses if tracking <= t <= score_end]
    acquired = next((t for t, gap in error if gap <= c['gaze_ok_deg']), None)
    if acquired is None or acquired >= score_end:
        return False, f'{label}: 평가 구간에서 시선 {c["gaze_ok_deg"]:g}° 이내 포착 없음'

    acquisition = acquired - first.captured_at
    scored = [(t, gap) for t, gap in error if t >= acquired]
    # The person's geometric exit is the deadline even when detections cease.
    in_gaze = sum(min(STEP_S, score_end - t) for t, gap in scored if gap <= c['gaze_ok_deg'])
    ratio = min(1., in_gaze / (score_end - acquired))
    missing = sum(not frame.detected for frame in run.frames if acquired <= frame.captured_at <= score_end)
    passed = (acquisition <= c['acquisition_s'] and ratio >= c['min_ok_ratio']
              and peak <= c['max_neck_speed_deg_s'] + 1e-8)
    return (passed, f'{label}: 포착 {acquisition:.2f}초, 수평 시선 {ratio:.1%}, '
            f'평가 중 미검출 {missing}프레임, 목 최고 {peak:.2f}°/s')


def _loss_case(model, track, c, yaw, pitch):
    hide_at = 6.
    duration = hide_at + c['loss_hold_max_s'] + abs(yaw) / min(model.return_neck_speed) + 2.
    run = _simulate(model, track['Planner'](exhibit=True), lambda _: yaw, duration, c['camera_latency_s'],
                    c['camera_hfov_deg'], track['ZERO'], target_pitch=pitch, hide_at=hide_at)
    label = f'소실 {yaw:+g}°/{pitch:+g}°'
    missed = next((frame for frame in run.frames if frame.captured_at >= hide_at and not frame.detected), None)
    tracked = any(frame.phase == 'TRACK' and frame.detected for frame in run.frames if frame.captured_at < hide_at)
    if not tracked or missed is None:
        return False, f'{label}: 소실 전 추적 미성립'
    still = [(t, pose) for t, pose in run.poses if missed.arrived_at - .25 <= t <= missed.arrived_at]
    baseline = still[-1][1]
    stationary = all(math.dist(pose[3:5], baseline[3:5]) <= POSITION_TICK_DEG for _, pose in still)
    displaced = all(abs(angle) > POSITION_TICK_DEG for angle in baseline[3:5])
    if not stationary or not displaced:
        return False, f'{label}: 두 축이 돌아간 상태에서 정지한 뒤 소실시켜야 함'

    returning = next((frame for frame in run.frames if frame.arrived_at >= missed.arrived_at
                      and frame.phase == 'RETURN'), None)
    starts = next((t for t, pose in run.poses if t > missed.arrived_at and
                   math.dist(pose[3:5], baseline[3:5]) >= POSITION_TICK_DEG), None)
    if returning is None or starts is None:
        return False, f'{label}: 복귀 시작을 확인하지 못함'
    delay = starts - missed.arrived_at
    peak = _neck_speed(run.poses, missed.arrived_at)
    home = all(abs(angle) <= POSITION_TICK_DEG for angle in run.poses[-1][1])
    parked = run.frames[-1].phase == 'IDLE'
    passed = (c['loss_hold_min_s'] <= delay <= c['loss_hold_max_s']
              and peak <= c['max_return_speed_deg_s'] + 1e-8 and home and parked
              and _neck_speed(run.poses) <= c['max_neck_speed_deg_s'] + 1e-8)
    return passed, f'{label}: 유지 {delay:.2f}초, 복귀 최고 {peak:.2f}°/s, 중립 {"도달" if home and parked else "미도달"}'


def _walk(model, track, c):
    if model.exhibit_neck_speed is None or model.return_neck_speed is None:
        return 'UNVERIFIED', '전시 추적과 복귀에 각각 적용되는 펌웨어 속도 설정이 필요합니다.'
    walk = [_walk_case(model, track, c, direction) for direction in (1, -1)]
    losses = [_loss_case(model, track, c, yaw, pitch) for yaw, pitch in ((-35., -10.), (35., 8.))]
    measured = [case[1] for case in (*walk, *losses)]
    context = (f'정면 대기, 거리 {c["distance_m"]:g} m, 보행 {c["walk_speed_mps"]:g} m/s, '
               f'±{c["scoring_range_deg"]:g}°, 영상 {CAMERA_FPS} fps·지연 {c["camera_latency_s"]:g}초·'
               f'수평 화각 {c["camera_hfov_deg"]:g}°를 가정한 속도 제한 모델. 포착은 첫 가시 프레임의 '
               f'촬영 시각부터 시선 {c["gaze_ok_deg"]:g}° 이내까지 잽니다. 포착 후 반대쪽 '
               f'{c["scoring_range_deg"]:g}°까지 미검출 중에도 시선 오차를 계산합니다. '
               '소실 대기는 첫 미검출 도착부터 실제 목 이동까지 잽니다. '
               '목 속도는 좌우·상하 각속도의 합성값이고, 중립 허용은 엔코더 한 틱입니다.')
    return ('PASS' if all(case[0] for case in (*walk, *losses)) else 'FAIL', ' / '.join(measured) + '. ' + context)


def _turn(model, track, c, camera):
    if model.exhibit_neck_speed is None or model.return_neck_speed is None:
        return 'UNVERIFIED', '전시 추적에 적용되는 펌웨어 속도 설정이 필요합니다.'
    distance = abs(c['target_deg'])
    measured = []
    passed = True
    for direction in (-1, 1):
        target = direction * distance
        run = _simulate(model, track['Planner'](exhibit=True), lambda _: target, 4.,
                        camera['camera_latency_s'], camera['camera_hfov_deg'], track['ZERO'])
        over = max(0., max(direction * pose[3] for _, pose in run.poses) - distance)
        final = run.poses[-1][1]
        error = abs(target - final[3] - final[0])
        missed = sum(not frame.detected for frame in run.frames)
        tracked = any(frame.phase == 'TRACK' and frame.detected for frame in run.frames)
        passed &= tracked and over <= c['max_neck_overshoot_deg'] and error <= c['max_final_gaze_err_deg']
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


def _blink_cycles(poses):
    started = shut = left_shut = None
    cycles = []
    for (t0, pose0), (t1, pose1) in zip(poses, poses[1:]):
        a0, a1 = pose0[2], pose1[2]
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
            cycles.append((started, finished-started, shut-started, finished-left_shut))
            started = shut = left_shut = None
    return cycles


def _blink(model, track, c):
    if model.exhibit_neck_speed is None or model.return_neck_speed is None:
        return 'UNVERIFIED', '전시 추적에 적용되는 펌웨어 속도 설정이 필요합니다.'
    duration = 6 * c['max_interval_s'] + c['max_total_s']
    assumed_encoder_span_ticks = 1024
    shaft_span_deg = assumed_encoder_span_ticks * 360 / 4096
    shaft_travel_deg = (BLINK_SHUT_DEG - BLINK_OPEN_DEG) * shaft_span_deg / track['LIMITS'][2][1]
    bound = 2 * shaft_travel_deg / model.speed[2]
    context = (f'논리 90°에 엔코더 {assumed_encoder_span_ticks}틱(모터축 {shaft_span_deg:g}°)을 대응시킨 '
               f'명목 모델. 축 속도 상한 {model.speed[2]:.2f}°/s에서 5°↔85° 왕복 하한 {bound:.3f}초 '
               '(가속·정지 시간 제외). 실제 보정 폭, 눈꺼풀 닫힘과 링크 진동은 P03에서 확인.')
    cycles, intervals = [], []
    irregular = True
    for seed in (0, 22, 42):
        planner = track['Planner'](exhibit=True, rng=random.Random(seed))
        run = _simulate(model, planner, lambda _: 0., duration, 0., 106., track['ZERO'], blink=True)
        completed = _blink_cycles(run.poses)
        if not completed or len(completed) < 4:
            return 'FAIL', f'난수 시드 {seed}에서 완전한 깜빡임이 4회 미만입니다. ' + context
        gaps = [b[0] - a[0] for a, b in zip(completed, completed[1:])]
        irregular &= max(gaps) - min(gaps) > 2 * model.goal_period
        cycles.extend(completed)
        intervals.extend(gaps)
    durations = [cycle[1] for cycle in cycles]
    delta = max(close - reopen for _, _, close, reopen in cycles)
    passed = (all(c['min_total_s'] <= total <= c['max_total_s'] for total in durations)
              and bound <= c['max_total_s'] and irregular
              and all(c['min_interval_s'] <= gap <= c['max_interval_s'] for gap in intervals))
    return ('PASS' if passed else 'FAIL',
            f'난수 시드 3개에서 깜빡임 {len(cycles)}회, 길이 {min(durations):.3f}~{max(durations):.3f}초, '
            f'시작 간격 {min(intervals):.2f}~{max(intervals):.2f}초, 관측된 간격 {"변동" if irregular else "고정"}, '
            f'닫기−열기 시간 차 최대 {delta:+.3f}초. ' + context)


def check_scenes(root: Path, criteria: dict) -> dict[str, tuple[str, str]]:
    track = runpy.run_path(str(root / 'control/pc/track.py'))
    model = RateModel.read(root)
    walk = criteria['S01_walk_by']
    return {'S01': _walk(model, track, walk),
            'S01b': _turn(model, track, criteria['S01b_no_whip'], walk),
            'S02': _look_up(root, track, criteria['S02_look_up']),
            'S03': _blink(model, track, criteria['S03_blink'])}
