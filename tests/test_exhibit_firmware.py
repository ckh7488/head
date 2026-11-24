import pytest

from test_firmware import GOAL, POSITION, TORQUE, arm, arm_jaw_demo, writes


PROFILE_VELOCITY = 112


def profile_events(events):
    return [(e.direction, e.id, e.value) for e in events if e.register == PROFILE_VELOCITY]


def neck_goals(events):
    return [(e.id, e.value) for e in writes(events, GOAL) if e.id in (4, 5)]


@pytest.fixture
def tracking(firmware):
    arm(firmware, 31)
    return firmware


def test_exhibit_capability_is_read_only(firmware):
    assert firmware.command('PING') == ['R5B1 1']
    assert firmware.command('EXHIBIT?') == ['R5B1_EXHIBIT 1']
    assert not firmware.command('GO_EXHIBIT 0 0 0 15 -6')
    assert not firmware.trace()


def test_profile_is_verified_before_motion_and_restores_plain_go(tracking):
    _, period, _, _ = map(int, tracking.exchange('timing')[0].split())
    assert not tracking.command('GO_EXHIBIT 0 0 0 15 -6')
    events = tracking.trace()
    assert profile_events(events[:3]) == [('r', 4, 29), ('w', 5, 15), ('r', 5, 15)]
    assert neck_goals(events[3:]) == [(4, 2208), (5, 2108)]

    assert not tracking.command('GO_RETURN 0 0 0 15 -6')
    assert not tracking.trace()
    tracking.tick(period)
    events = tracking.trace()
    assert profile_events(events[:4]) == [('w', 4, 7), ('r', 4, 7), ('w', 5, 7), ('r', 5, 7)]
    assert neck_goals(events[4:]) == [(4, 2208), (5, 2108)]

    assert not tracking.command('GO_RETURN 0 0 0 14 -5')
    tracking.tick(period)
    events = tracking.trace()
    assert not profile_events(events)
    assert neck_goals(events) == [(4, 2197), (5, 2098)]

    assert not tracking.command('GO 0 0 0 13 -4')
    tracking.tick(period)
    events = tracking.trace()
    assert profile_events(events[:4]) == [('w', 4, 29), ('r', 4, 29), ('w', 5, 19), ('r', 5, 19)]
    assert neck_goals(events[4:]) == [(4, 2187), (5, 2088)]
    assert not writes(events, TORQUE)


def test_latest_profile_and_goal_share_the_existing_write_period(tracking):
    _, period, _, _ = map(int, tracking.exchange('timing')[0].split())
    tracking.command('GO 0 0 0 15 -6')
    tracking.trace()
    tracking.command('GO_RETURN 0 0 0 4 -2')
    tracking.command('GO_EXHIBIT 0 0 0 12 -3')
    tracking.tick(period-1)
    assert not tracking.trace()
    tracking.tick(1)
    events = tracking.trace()
    assert profile_events(events) == [('r', 4, 29), ('w', 5, 15), ('r', 5, 15)]
    assert neck_goals(events) == [(4, 2176), (5, 2078)]


def test_exhibit_heartbeat_survives_hold_then_watchdog_freezes(tracking):
    _, _, _, timeout = map(int, tracking.exchange('timing')[0].split())
    goal = 'GO_EXHIBIT 0 0 0 24 -3'
    tracking.command(goal)
    tracking.trace()
    tracking.set(4, POSITION, 2090)
    for _ in range(25):
        tracking.tick(100)
        assert not tracking.command(goal)
    events = tracking.trace()
    assert not profile_events(events)
    assert not writes(events, GOAL)
    tracking.tick(timeout-1)
    assert tracking.command('EXHIBIT?') == ['R5B1_EXHIBIT 1']
    assert not writes(tracking.trace(), GOAL)
    tracking.tick(1)
    events = tracking.trace()
    assert (4, 2090) in neck_goals(events)
    assert not (profile_events(events) or writes(events, TORQUE))


@pytest.mark.parametrize('bad', ['GO_RETURN nan 0 0 0 0', 'GO_RETURN 0 0 0 0',
                                  'GO_EXHIBIT 0 0 0 0 0 0', 'GO_RETURN 0 0 0 0 inf'])
def test_bad_motion_frame_changes_neither_profile_nor_watchdog(tracking, bad):
    _, _, _, timeout = map(int, tracking.exchange('timing')[0].split())
    tracking.command('GO 0 0 0 15 -6')
    tracking.trace()
    tracking.set(4, POSITION, 2090)
    tracking.tick(timeout-1)
    assert not tracking.command(bad)
    tracking.tick(1)
    events = tracking.trace()
    assert (4, 2090) in neck_goals(events)
    assert not profile_events(events)


@pytest.mark.parametrize('mode', [8, 56, 63, 'jaw-demo'])
def test_exhibit_needs_exact_tracking_mask(firmware, mode):
    if mode == 'jaw-demo':
        arm_jaw_demo(firmware)
        firmware.trace()
    else:
        arm(firmware, mode)
    for prefix in ('GO_EXHIBIT', 'GO_RETURN'):
        assert firmware.command(f'{prefix} 0 0 0 15 -6') == ['ERROR EXHIBIT_MASK']
    assert not firmware.trace()


@pytest.mark.parametrize(('direction', 'servo', 'kind', 'times'), [
    ('r', 4, 'wrong_id', 2), ('r', 5, 'timeout', 2), ('w', 5, 'ignored', 1),
])
def test_unconfirmed_profile_faults_before_new_goal(tracking, direction, servo, kind, times):
    tracking.fail(direction, servo, PROFILE_VELOCITY, kind, times)
    assert tracking.command('GO_EXHIBIT 12 4 30 15 -6') == [f'ERROR NECK_PROFILE ID{servo}']
    events = tracking.trace()
    assert [(e.id, e.value) for e in writes(events, GOAL)] == [
        (1, 2048), (2, 2048), (3, 2000), (4, 2048), (5, 2048),
    ]
    assert not writes(events, TORQUE)
    assert tracking.command('ARM 31') == ['LOCKED RELEASE_AFTER_FAULT']
    assert not tracking.command('GO_RETURN 0 0 0 0 0')
    assert not tracking.trace()


def test_hold_cancels_paced_profile_change_and_fresh_arm_uses_normal(tracking):
    _, period, _, _ = map(int, tracking.exchange('timing')[0].split())
    tracking.command('GO_EXHIBIT 0 0 0 15 -6')
    tracking.trace()
    tracking.command('GO_RETURN 0 0 0 0 0')
    tracking.command('HOLD')
    tracking.tick(period)
    events = tracking.trace()
    assert not profile_events(events)
    assert neck_goals(events) == [(4, 2208), (5, 2108)]

    assert tracking.command('RELEASE') == ['RELEASED']
    tracking.trace()
    assert tracking.command('ARM 31')[0] == 'ARMED 31'
    profiles = profile_events(tracking.trace())
    assert profiles[-2:] == [('w', 4, 29), ('w', 5, 19)]
