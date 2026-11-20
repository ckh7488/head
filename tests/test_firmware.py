import pytest


POSITION, GOAL, TORQUE = 132, 116, 64


def writes(events, register):
    return [event for event in events if event.direction == 'w' and event.register == register]


def arm(firmware, mask):
    replies = firmware.command(f'ARM {mask}')
    assert replies[0] == f'ARMED {mask}'
    assert replies[1].startswith(f'STATE {mask} ')
    firmware.trace()


def test_unset_calibration_keeps_all_axes_off(uncalibrated):
    assert uncalibrated.command('ARM 63') == ['LOCKED CALIBRATE ID1']
    for servo in range(1, 7):
        reply = uncalibrated.command(f'CHECK {servo}')
        assert reply[0].endswith(' 2048 0 0')
    assert not any(event.direction == 'w' for event in uncalibrated.trace())


@pytest.mark.parametrize(('register', 'value'), [
    (0, 1190), (10, 4), (10, 8), (11, 1), (64, 1), (68, 1),
    (POSITION, 1000), (POSITION, 4096), (POSITION, -1),
])
def test_arm_checks_every_axis_before_writing(firmware, register, value):
    firmware.set(5, register, value)
    assert firmware.command('ARM 24') == ['LOCKED SERVO_CHECK ID5']
    assert not any(event.direction == 'w' for event in firmware.trace())


def test_arm_reads_pwm_back_before_enabling_any_axis(firmware):
    firmware.fail('w', 5, 100, 'ignored')
    assert firmware.command('ARM 24') == ['LOCKED ARM_CONFIG ID5']
    assert not writes(firmware.trace(), TORQUE)


def test_arm_accepts_reverse_direction(firmware):
    firmware.set(4, 10, 1)
    arm(firmware, 8)


def test_unconfirmed_enable_latches_without_switching_off(firmware):
    firmware.fail('w', 5, TORQUE, 'lost')
    assert firmware.command('ARM 24') == ['ERROR ARM_ENABLE_UNCONFIRMED ID5']
    assert [(e.id, e.value) for e in writes(firmware.trace(), TORQUE)] == [(4, 1), (5, 1)]
    assert firmware.command('ARM 24') == ['LOCKED RELEASE_AFTER_FAULT']
    firmware.command('GO 0 0 0 45 3')
    assert not writes(firmware.trace(), GOAL)
    assert firmware.command('RELEASE') == ['RELEASED']
    assert [(e.id, e.value) for e in writes(firmware.trace(), TORQUE)] == [(4, 0), (5, 0)]


def test_goal_limits_cover_reversed_and_one_sided_axes(firmware):
    arm(firmware, 63)
    firmware.command('GO -1e9 1e9 1e9 1e9 -1e9 1e9')
    assert [(e.id, e.value) for e in writes(firmware.trace(), GOAL)] == [
        (1, 1820), (2, 1957), (3, 3024), (4, 2731), (5, 2219), (6, 1852),
    ]
    firmware.command('GO 0 0 0 0 0 0')
    firmware.tick(60)
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2048, 2048, 2000, 2048, 2048, 2000]


@pytest.mark.parametrize('message', [
    b'GO nan 0 0 0 0', b'GO 0 inf 0 0 0', b'GO 0 0 0 1e999 0', b'GO 0 0 0 5',
    b'GO 0 0 0 5 0 extra', b'GO 0 0 0 5.0.1 0', b'GO 0 0 0 5\x00 0',
    b'GO 0 0 0 5\r 0', b'GO 0 0 0 5 0' + b' '*130, b'RELEASE\x00junk',
])
def test_invalid_frame_does_not_refresh_watchdog(firmware, message):
    arm(firmware, 8)
    firmware.command('GO 0 0 0 5 0')
    firmware.trace()
    firmware.set(4, POSITION, 2050)
    firmware.tick(399)
    firmware.receive(message+b'\n')
    firmware.tick(1)
    firmware.tick(0)
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2050]


def test_crlf_and_fragmented_input(firmware):
    arm(firmware, 8)
    firmware.receive(b'GO 0 0 0 15')
    assert not writes(firmware.trace(), GOAL)
    firmware.receive(b' 0\r\n')
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2219]


def test_hold_discards_queued_setpoint(firmware):
    arm(firmware, 8)
    firmware.command('GO 0 0 0 15 0')
    firmware.command('GO 0 0 0 45 0')
    firmware.set(4, POSITION, 2100)
    firmware.command('HOLD')
    firmware.tick(60)
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2219, 2100]


@pytest.mark.parametrize(('mask', 'servo', 'measured', 'goal'), [
    (8, 4, 2734, 2731), (8, 4, 1362, 1365), (16, 5, 1977, 1980),
])
def test_hold_is_clamped_even_when_measured_tick_is_just_outside(firmware, mask, servo, measured, goal):
    arm(firmware, mask)
    firmware.set(servo, POSITION, measured)
    assert not firmware.command('HOLD')
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [goal]


@pytest.mark.parametrize('delta', [8, 9])
def test_report_limit_is_inclusive_at_eight_ticks(firmware, delta):
    arm(firmware, 8)
    firmware.set(4, POSITION, 2731+delta)
    reply = firmware.tick(120)
    if delta == 8:
        assert reply == ['STATE 8 0.000 0.000 0.000 60.000 0.000']
    else:
        assert reply == ['ERROR POSITION_LIMIT ID4', 'ERROR HOLD_UNCONFIRMED']
    assert not any(e.direction == 'w' for e in firmware.trace())


@pytest.mark.parametrize('kind', ['timeout', 'crc', 'instruction_crc', 'short'])
def test_transient_read_is_retried(firmware, kind):
    arm(firmware, 8)
    firmware.fail('r', 4, POSITION, kind)
    assert firmware.tick(120)[0].startswith('STATE 8 ')
    assert [(e.direction, e.result) for e in firmware.trace()] == [('r', kind), ('r', 'ok')]


@pytest.mark.parametrize('kind', ['timeout', 'crc', 'instruction_crc', 'lost'])
def test_transient_write_retries_the_same_tick(firmware, kind):
    arm(firmware, 8)
    firmware.fail('w', 4, GOAL, kind)
    assert not firmware.command('GO 0 0 0 30 0')
    assert [(e.id, e.value, e.result) for e in writes(firmware.trace(), GOAL)] == [
        (4, 2390, kind), (4, 2390, 'ok'),
    ]
    assert firmware.tick(120)[0].startswith('STATE 8 ')


@pytest.mark.parametrize(('kind', 'error', 'tries'), [
    ('timeout', 'WRITE_BUS', 2), ('denied', 'WRITE_STATUS', 1), ('alert', 'WRITE_STATUS', 1),
])
def test_persistent_write_or_valid_servo_error_latches(firmware, kind, error, tries):
    arm(firmware, 24)
    firmware.exchange('follow 5 0')
    firmware.fail('w', 5, GOAL, kind, tries)
    assert firmware.command('GO 0 0 0 25 4') == [f'ERROR {error} ID5']
    events = firmware.trace()
    assert not writes(events, TORQUE)
    assert sum(e.result == kind for e in writes(events, GOAL)) == tries
    assert writes(events, GOAL)[-1].value == 2048
    assert firmware.command('ARM 24') == ['LOCKED RELEASE_AFTER_FAULT']
    firmware.command('GO 0 0 0 0 0')
    firmware.tick(200)
    assert not writes(firmware.trace(), GOAL)


def test_persistent_read_still_holds_other_axes(firmware):
    arm(firmware, 24)
    firmware.set(5, POSITION, 2050)
    firmware.fail('r', 4, POSITION, 'timeout', 10)
    assert firmware.tick(120) == ['ERROR READ_BUS ID4', 'ERROR HOLD_UNCONFIRMED']
    events = firmware.trace()
    assert [(e.id, e.value) for e in writes(events, GOAL)] == [(5, 2050)]
    assert not writes(events, TORQUE)


def test_check_can_inspect_torque_without_releasing_after_a_fault(firmware):
    arm(firmware, 16)
    firmware.fail('w', 5, GOAL, 'timeout', 2)
    assert firmware.command('GO 0 0 0 0 4') == ['ERROR WRITE_BUS ID5']
    firmware.trace()
    assert firmware.command('CHECK 5') == ['CHECK 5 1060 3 0 2 1 2048 1 0']
    assert all(e.direction == 'r' for e in firmware.trace())


def test_release_retries_only_the_unconfirmed_axis(firmware):
    arm(firmware, 24)
    firmware.fail('w', 5, TORQUE, 'timeout', 2)
    assert firmware.command('RELEASE') == ['ERROR RELEASE_UNCONFIRMED']
    assert [(e.id, e.value) for e in writes(firmware.trace(), TORQUE)] == [(4, 0), (5, 0), (5, 0)]
    assert firmware.command('RELEASE') == ['RELEASED']
    assert [e.id for e in writes(firmware.trace(), TORQUE)] == [5]
    arm(firmware, 24)


def test_reboot_recovers_an_axis_that_latched_a_hardware_alert(firmware):
    arm(firmware, 24)
    firmware.fail('r', 5, POSITION, 'alert', 100)
    firmware.fail('r', 5, TORQUE, 'alert', 100)
    assert firmware.tick(120)[0] == 'ERROR READ_STATUS ID5'
    assert firmware.command('RELEASE') == ['ERROR RELEASE_UNCONFIRMED']
    assert firmware.command('ARM 24') == ['LOCKED RELEASE_AFTER_FAULT']
    firmware.trace()
    assert firmware.command('REBOOT 5') == ['REBOOTED 5']
    assert [(e.direction, e.id) for e in firmware.trace()] == [('b', 5)]
    assert firmware.command('RELEASE') == ['RELEASED']
    arm(firmware, 24)


def test_reboot_is_refused_on_a_healthy_armed_axis(firmware):
    arm(firmware, 24)
    assert firmware.command('REBOOT 4') == ['ERROR REBOOT_WHILE_ARMED ID4']
    assert firmware.command('REBOOT 7') == ['ERROR REBOOT_ID']
    assert not any(e.direction == 'b' for e in firmware.trace())
    assert firmware.command('REBOOT 6') == ['REBOOTED 6']


def test_pacing_applies_latest_goal_as_reports_continue(firmware):
    _, period, report, _ = map(int, firmware.exchange('timing')[0].split())
    arm(firmware, 8)
    firmware.command('GO 0 0 0 5 0')
    firmware.command('GO 0 0 0 10 0')
    firmware.command('GO 0 0 0 25 0')
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2105]
    firmware.tick(period-1)
    assert not writes(firmware.trace(), GOAL)
    firmware.tick(1)
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2333]
    assert firmware.tick(report-period)[0].startswith('STATE 8 ')


def test_slow_usb_read_requests_do_not_flush_stale_goal_before_watchdog(firmware):
    arm(firmware, 8)
    firmware.command('GO 0 0 0 10 0')
    firmware.command('GO 0 0 0 40 0')
    firmware.tick(20)
    firmware.set(4, POSITION, 2100)
    firmware.fail('r', 4, POSITION, 'timeout', 32)
    firmware.receive(b'READ 4\n'*16)
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2162, 2100]


def test_all_six_axes_have_bus_headroom(firmware):
    baud, period, report, _ = map(int, firmware.exchange('timing')[0].split())
    return_delay = .508
    write_ms = 27*10*1000/baud + return_delay
    read_ms = 29*10*1000/baud + return_delay
    assert 6*(write_ms/period + read_ms/report) < .82
    assert 5*(write_ms/33.333 + read_ms/90) > 1


def test_six_axis_flood_keeps_both_pacing_and_telemetry(firmware):
    _, period, report, _ = map(int, firmware.exchange('timing')[0].split())
    arm(firmware, 63)
    states = []
    for frame in range(100):
        direction = 1 if (frame//6)%2 else -1
        firmware.command(f'GO {direction*10} {direction*5} {15+direction*5} '
                         f'{direction*30} {direction*5} {8+direction*4}')
        states.extend(firmware.tick(10))
    goals = writes(firmware.trace(), GOAL)
    for servo in range(1, 7):
        times = [e.time for e in goals if e.id==servo]
        assert len(times) >= 15
        assert all(b-a >= period for a,b in zip(times,times[1:]))
    assert sum(line.startswith('STATE 63 ') for line in states) == 1000//report
