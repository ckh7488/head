import pytest

from conftest import CALIBRATED, Firmware
from test_firmware import GOAL, POSITION, TORQUE, writes


PWM = 100
NEUTRAL_STATE = 'STATE 31 0.000 0.000 0.000 0.000 0.000'


def jaw_writes(firmware, register):
    return [event.value for event in writes(firmware.trace(), register) if event.id == 6]


def test_tracking_latches_only_closed_jaw_and_preserves_watchdog(firmware):
    assert firmware.command('EXHIBIT_HOLD?') == ['R5B1_EXHIBIT_HOLD 1']
    assert not firmware.trace()
    assert firmware.command('ARM_EXHIBIT') == ['ARMED_EXHIBIT 31', NEUTRAL_STATE]
    events = firmware.trace()
    assert [(event.register, event.value) for event in events if event.direction == 'w' and event.id == 6] == [
        (PWM, 100), (112, 6), (108, 10), (GOAL, 2000), (TORQUE, 1),
    ]
    assert firmware.command('GO 0 0 0 0 0') == ['ERROR EXHIBIT_PROFILE']
    assert not firmware.command('GO_EXHIBIT 0 0 0 0 0 5.5')
    assert not firmware.command('GO_EXHIBIT 0 0 0 15 -2')
    assert not firmware.command('HOLD')
    assert not jaw_writes(firmware, GOAL)
    assert not firmware.command('GO_RETURN 0 0 0 0 0')
    firmware.tick(400)
    assert not jaw_writes(firmware, GOAL)
    assert firmware.command('ARM_JAW_DEMO') == ['ERROR RELEASE_BEFORE_JAW_DEMO_CHANGE']
    assert firmware.command('RELEASE') == ['RELEASED']
    assert jaw_writes(firmware, TORQUE) == [0]


def test_cold_jaw_closes_before_tracking_is_enabled(firmware):
    firmware.set(6, POSITION, 1890)
    assert firmware.command('ARM_EXHIBIT') == [NEUTRAL_STATE]
    events = firmware.trace()
    assert [event.value for event in writes(events, PWM) if event.id == 6] == [100, 120]
    assert [event.value for event in writes(events, GOAL) if event.id == 6] == [2000]
    assert firmware.command('GO_EXHIBIT 0 0 0 40 0') == ['ERROR EXHIBIT_JAW_CLOSING']
    for _ in range(9):
        assert firmware.tick(120) == [NEUTRAL_STATE]
    assert not writes(firmware.trace(), GOAL)
    firmware.set(6, POSITION, 1992)
    assert firmware.tick(120) == ['ARMED_EXHIBIT 31', NEUTRAL_STATE]
    assert jaw_writes(firmware, PWM) == [100]
    assert not firmware.command('GO_RETURN 0 0 0 0 0')
    assert not jaw_writes(firmware, GOAL)


@pytest.mark.parametrize(('jaw_raw', 'neck_raw', 'reason'), [
    (1889, 2048, 'LOCKED EXHIBIT_JAW_RANGE ID6'),
    (2009, 2048, 'LOCKED EXHIBIT_JAW_RANGE ID6'),
    (1904, 2060, 'ERROR NECK_NOT_NEUTRAL ID5'),
])
def test_cold_start_rejects_unqualified_gap_or_neck(firmware, jaw_raw, neck_raw, reason):
    firmware.set(6, POSITION, jaw_raw)
    firmware.set(5, POSITION, neck_raw)
    assert firmware.command('ARM_EXHIBIT') == [reason]
    assert not any(event.direction == 'w' for event in firmware.trace())


@pytest.mark.parametrize('failure', ['torque', 'position', 'timeout', 'pwm', 'hold'])
def test_bad_cold_recovery_releases_only_jaw(firmware, failure):
    firmware.set(6, POSITION, 1904)
    assert firmware.command('ARM_EXHIBIT') == [NEUTRAL_STATE]
    firmware.trace()
    if failure == 'torque':
        firmware.set(5, TORQUE, 0)
        reply = firmware.tick(120)
        expected = 'EXHIBIT_JAW_NECK_TORQUE ID5'
    elif failure == 'position':
        firmware.set(6, POSITION, 1889)
        reply = firmware.tick(120)
        expected = 'POSITION_LIMIT ID6'
    elif failure == 'pwm':
        firmware.set(6, POSITION, 1999)
        firmware.fail('w', 6, PWM, 'ignored')
        reply = firmware.tick(120)
        expected = 'EXHIBIT_JAW_PWM ID6'
    elif failure == 'hold':
        reply = firmware.command('HOLD')
        expected = 'EXHIBIT_JAW_CLOSE_CANCELLED ID6'
    else:
        reply = firmware.tick(2400)
        expected = 'EXHIBIT_JAW_CLOSE_TIMEOUT ID6'
    assert reply == [f'ERROR {expected}']
    events = firmware.trace()
    assert [(event.id, event.value) for event in writes(events, TORQUE)] == [(6, 0)]
    assert {event.id for event in writes(events, GOAL)} == {1, 2, 3, 4, 5}
    assert firmware.command('ARM_EXHIBIT') == ['LOCKED RELEASE_AFTER_FAULT']


def test_sustained_exhibit_jaw_error_releases_without_pulsing(firmware):
    assert firmware.command('ARM_EXHIBIT')[0] == 'ARMED_EXHIBIT 31'
    firmware.trace()
    firmware.set(6, POSITION, 1981)
    assert firmware.tick(600) == [NEUTRAL_STATE]
    assert firmware.tick(120) == ['ERROR JAW_FOLLOW_TIMEOUT ID6']
    events = firmware.trace()
    assert [(event.id, event.value) for event in writes(events, TORQUE)] == [(6, 0)]
    assert 6 not in {event.id for event in writes(events, GOAL)}


def test_exhibit_keeps_five_axes_when_jaw_calibration_is_unset(firmware_build):
    simulator = Firmware(firmware_build((*CALIBRATED[:-1], (-1, -1, -1))))
    try:
        assert simulator.command('ARM_EXHIBIT') == ['ARMED_EXHIBIT 31', 'EXHIBIT_JAW_UNCALIBRATED', NEUTRAL_STATE]
        assert all(event.id != 6 for event in simulator.trace())
        assert not simulator.command('GO_EXHIBIT 0 0 0 14 -4')
        assert {event.id for event in writes(simulator.trace(), GOAL)} == {4, 5}
    finally:
        simulator.close()


@pytest.mark.parametrize('close_feedback', [1988, 2011])
def test_cold_trim_is_once_and_restores_zero_before_arming(firmware, close_feedback):
    firmware.set(6, POSITION, 1904)
    firmware.exchange('follow 6 0')
    assert firmware.command('ARM_EXHIBIT') == [NEUTRAL_STATE]
    firmware.trace()
    firmware.set(6, POSITION, 1980)
    assert firmware.tick(1540) == [NEUTRAL_STATE]
    assert not jaw_writes(firmware, GOAL)
    assert firmware.tick(120) == [NEUTRAL_STATE]
    assert jaw_writes(firmware, GOAL) == [2011]
    assert firmware.tick(120) == [NEUTRAL_STATE]
    assert not jaw_writes(firmware, GOAL)

    firmware.set(6, POSITION, close_feedback)
    assert firmware.tick(120) == ['ARMED_EXHIBIT 31', NEUTRAL_STATE]
    events = firmware.trace()
    assert [(e.register, e.value) for e in events if e.direction == 'w' and e.id == 6] == [
        (GOAL, 2000), (PWM, 100),
    ]


def test_ignored_restore_cannot_leave_the_cold_trim_in_tracking(firmware):
    firmware.set(6, POSITION, 1904)
    firmware.exchange('follow 6 0')
    assert firmware.command('ARM_EXHIBIT') == [NEUTRAL_STATE]
    firmware.trace()
    firmware.set(6, POSITION, 1981)
    assert firmware.tick(1560) == [NEUTRAL_STATE]
    assert jaw_writes(firmware, GOAL) == [2011]
    firmware.set(6, POSITION, 1989)
    firmware.fail('w', 6, GOAL, 'ignored')
    assert firmware.tick(120) == ['ERROR EXHIBIT_JAW_TARGET ID6']
    events = firmware.trace()
    assert [(e.id, e.value) for e in writes(events, TORQUE)] == [(6, 0)]
    assert not [e for e in writes(events, PWM) if e.id == 6]
