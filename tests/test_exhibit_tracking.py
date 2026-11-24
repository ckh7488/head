from math import dist
from types import SimpleNamespace

import pytest

from track import LIMITS, RATES, ZERO, Planner, select_face


FPS = 20
FIRST_MISSING = FPS + 1
HOLD_FRAMES = int(2.5 * FPS)
DISPLACED_FEEDBACK = (-14., 6., 0., -42., 4.)


def frame(planner, index, error=None, feedback=ZERO):
    return planner.step(error, feedback, index / FPS, blink_enabled=False)


def gaze(decision):
    return decision.goals[:2] + decision.goals[3:]


def off_center():
    planner = Planner(exhibit=True)
    feedback = ZERO
    for index in range(FIRST_MISSING):
        decision = frame(planner, index, (28., -12.), feedback)
        feedback = decision.goals
    assert decision.active
    assert all(abs(angle) > .5 for angle in gaze(decision))
    return planner, decision


def test_exhibit_starts_neutral_and_inactive_without_a_face():
    planner = Planner(exhibit=True)
    for index in range(4 * FPS):
        decision = frame(planner, index, feedback=DISPLACED_FEEDBACK)
        assert not decision.active
        assert decision.goals == ZERO


def test_loss_timer_starts_at_first_processed_missing_face():
    planner, emitted = off_center()
    first_missing = FIRST_MISSING + FPS
    for index in range(first_missing, first_missing + HOLD_FRAMES):
        decision = frame(planner, index, feedback=DISPLACED_FEEDBACK)
        assert decision.active
        assert gaze(decision) == gaze(emitted)

    for index in range(first_missing + HOLD_FRAMES, first_missing + HOLD_FRAMES + FPS // 2):
        decision = frame(planner, index, feedback=DISPLACED_FEEDBACK)
    assert decision.active
    assert dist(decision.goals[3:], ZERO[3:]) < dist(emitted.goals[3:], ZERO[3:])


def test_neutral_return_does_not_restart_on_repeated_missing_frames():
    planner, previous = off_center()
    for index in range(FIRST_MISSING, FIRST_MISSING + 12 * FPS):
        decision = frame(planner, index, feedback=DISPLACED_FEEDBACK)
        assert dist(decision.goals[3:], previous.goals[3:]) <= 10 / FPS + 1e-9
        for old, new, rate in zip(previous.goals, decision.goals, RATES, strict=True):
            assert abs(new - old) <= rate / FPS + 1e-9
            assert abs(new) <= abs(old) + 1e-9
        if decision.goals == ZERO:
            assert decision.active
            assert decision.goals == ZERO
            assert index >= FIRST_MISSING + HOLD_FRAMES
            break
        previous = decision
    else:
        pytest.fail('Repeated missing frames prevented the return to neutral.')

    assert frame(planner, index + 1).active
    at_home = frame(planner, index + 2)
    assert not at_home.active
    assert at_home.keep_neutral
    assert at_home.goals == ZERO


def test_park_confirms_fresh_feedback_and_keeps_the_load_offset():
    planner = Planner(exhibit=True)
    planner.start_centering(ZERO)
    powered_offset = (1.05, -1.27)
    now = .0
    goal = ZERO
    for index in range(51):
        now = index * .12
        measured = ZERO[:3] + tuple(e + g for e, g in zip(powered_offset, goal[3:], strict=True))
        decision = planner.step(None, measured, now, feedback_at=now)
        assert dist(decision.goals[3:], goal[3:]) <= 1.75 * .12 + 1e-9
        goal = decision.goals
        if decision.keep_neutral:
            assert max(abs(x) for x in measured[3:]) <= .5
            break
    else:
        pytest.fail('A small loaded error prevented parking.')

    assert goal != ZERO
    repeated = planner.step(None, measured, now + .033, feedback_at=now)
    assert repeated.keep_neutral and repeated.goals == goal
    feedback = ZERO[:3] + (1.1, 0.)
    drift = planner.step(None, feedback, now + .12, feedback_at=now + .12)
    assert drift.active and not drift.keep_neutral
    reused = planner.step(None, feedback, now + .153, feedback_at=now + .12)
    assert reused.goals == drift.goals


def test_eye_offset_does_not_block_a_centered_neck():
    planner = Planner(exhibit=True)
    planner.start_centering(ZERO)
    feedback = (.6, 0., 0., 0., 0.)
    assert planner.step((8., 0.), feedback, 0.).phase == 'RETURN'
    assert planner.step((8., 0.), feedback, .12).keep_neutral
    assert planner.step((8., 0.), feedback, .24).phase == 'TRACK'


def test_blocked_return_does_not_claim_park_or_keep_applying_trim():
    planner = Planner(exhibit=True)
    planner.start_centering(ZERO)
    for index in range(61):
        now = .1 * index
        result = planner.step(None, ZERO[:3] + (4., 0.), now, feedback_at=now)
        if result.phase == 'RETURN_FAILED':
            assert not result.active and not result.keep_neutral
            assert result.goals == ZERO
            break
    else:
        pytest.fail('A blocked return continued past the timeout.')


def test_visible_new_face_ends_hold_and_the_eyes_lead():
    planner, previous = off_center()
    missing = frame(planner, FIRST_MISSING, feedback=previous.goals)
    assert missing.phase == 'HOLD'
    feedback = missing.goals
    for offset in (1, 2, 3):
        decision = frame(planner, FIRST_MISSING + offset, (-24., 12.), feedback)
        assert decision.phase == 'TRACK'
        assert decision.goals[3:] == missing.goals[3:]
        feedback = decision.goals
    assert decision.goals[0] < missing.goals[0]
    decision = frame(planner, FIRST_MISSING + 4, (-24., 12.), feedback)
    assert decision.goals[3] < missing.goals[3]


def test_face_selection_preserves_visible_target_and_switches_on_loss():
    def face(x):
        parts = [None] * 363
        for key, delta in zip((33, 133, 362, 263), (-.04, -.02, .02, .04), strict=True):
            parts[key] = SimpleNamespace(x=x + delta, y=.5)
        return parts

    current = (200., 250.)
    first = SimpleNamespace(face_landmarks=[face(.7), face(.2)])
    point, switched = select_face(first, 1001, 501, current)
    assert point == pytest.approx(current)
    assert not switched
    second = SimpleNamespace(face_landmarks=[face(.7)])
    point, switched = select_face(second, 1001, 501, point)
    assert point == pytest.approx((700., 250.))
    assert switched


def test_exhibit_eventually_opens_the_lids_if_the_face_is_lost_mid_blink():
    planner = Planner(exhibit=True)
    feedback = ZERO
    for index in range(12 * FPS):
        decision = planner.step((8., -5.), feedback, index / FPS)
        feedback = decision.goals
        if decision.goals[2] > 5.:
            break
    else:
        pytest.fail('No blink was emitted during continuous tracking.')

    for index in range(index + 1, index + 1 + 12 * FPS):
        decision = planner.step(None, feedback, index / FPS)
        assert abs(decision.goals[2] - feedback[2]) <= RATES[2] / FPS + 1e-9
        if not decision.active:
            assert decision.goals == ZERO
            return
        feedback = decision.goals
    pytest.fail('The interrupted blink prevented the return to neutral.')


@pytest.mark.parametrize('lost_frames', [FPS, 3 * FPS], ids=['during-hold', 'during-return'])
def test_reacquisition_resumes_from_the_emitted_pose(lost_frames):
    planner, previous = off_center()
    reacquired = FIRST_MISSING + lost_frames
    for index in range(FIRST_MISSING, reacquired):
        previous = frame(planner, index, feedback=DISPLACED_FEEDBACK)
    assert previous.active

    decision = frame(planner, reacquired, (-24., 12.), DISPLACED_FEEDBACK)
    assert decision.active
    for old, new, (low, high), rate in zip(previous.goals, decision.goals, LIMITS, RATES, strict=True):
        assert low <= new <= high
        assert abs(new - old) <= rate / FPS + 1e-9

    first_new_loss = reacquired + FPS
    for index in range(reacquired + 1, first_new_loss):
        decision = frame(planner, index, (-24., 12.), decision.goals)
        assert decision.active
    assert decision.goals[0] < 0.

    for index in range(first_new_loss, first_new_loss + HOLD_FRAMES):
        held = frame(planner, index, feedback=DISPLACED_FEEDBACK)
        assert held.active
        assert gaze(held) == gaze(decision)


def test_default_planner_still_holds_reported_feedback_immediately_after_loss():
    planner = Planner()
    assert frame(planner, 0, (28., -12.)).active
    decision = frame(planner, 1, feedback=DISPLACED_FEEDBACK)
    assert not decision.active
    assert decision.goals == DISPLACED_FEEDBACK
