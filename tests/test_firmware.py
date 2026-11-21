import pytest

from conftest import CALIBRATED, Firmware


POSITION, GOAL, TORQUE, STARTUP = 132, 116, 64, 60


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
    firmware.command('GO -1e9 1e9 1e9 1e9 -1e9 5.5')
    assert [(e.id, e.value) for e in writes(firmware.trace(), GOAL)] == [
        (1, 1829), (2, 1965), (3, 3024), (4, 2707), (5, 2219), (6, 1938),
    ]
    firmware.command('GO 0 0 0 0 0 0')
    firmware.tick(60)
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2048, 2048, 2000, 2048, 2048, 2000]


@pytest.mark.parametrize('goal', ['13', '6', '-1'])
def test_jaw_rejects_commands_outside_calibrated_demo_range(firmware, goal):
    arm(firmware, 32)
    assert firmware.command('GO 0 0 0 0 0 ' + goal) == ['ERROR JAW_GOAL_RANGE ID6']
    assert not writes(firmware.trace(), GOAL)


@pytest.mark.parametrize('opening_tick', [1937, 1852])
def test_jaw_arming_rejects_overlong_calibration(firmware_build, opening_tick):
    rows = (*CALIBRATED[:-1], (2000, 2000, opening_tick))
    simulator = Firmware(firmware_build(rows))
    try:
        for command in ('ARM 56', 'ARM_JAW_DEMO'):
            assert simulator.command(command) == ['LOCKED JAW_CALIBRATION_RANGE ID6']
        assert not writes(simulator.trace(), TORQUE)
    finally:
        simulator.close()

@pytest.mark.parametrize(('axis', 'row', 'name'), [
    (0, (1828, 2048, 2267), 'EYE'), (1, (2131, 2048, 1964), 'EYE'),
    (3, (1389, 2048, 2708), 'YAW'), (3, (2707, 2048, 1388), 'YAW'),
    (3, (1374, 2048, 2722), 'YAW'),
])
def test_arming_keeps_feedback_inside_cad_travel(firmware_build, axis, row, name):
    rows = list(CALIBRATED)
    rows[axis] = row
    simulator = Firmware(firmware_build(rows))
    try:
        assert simulator.command(f'ARM {1<<axis}') == [f'LOCKED {name}_CALIBRATION_RANGE ID{axis+1}']
        assert not writes(simulator.trace(), TORQUE)
    finally:
        simulator.close()


def test_jaw_position_report_limits_overtravel_to_eleven_ticks(firmware):
    arm(firmware, 32)
    firmware.set(6, POSITION, 1938 - 11)
    assert firmware.tick(120)[0].endswith(' 5.500')
    firmware.set(6, POSITION, 1938 - 12)
    assert firmware.tick(120) == ['ERROR POSITION_LIMIT ID6']
    assert [(e.id, e.value) for e in writes(firmware.trace(), TORQUE)] == [(6, 0)]


@pytest.mark.parametrize('row', [(2219, 2048, 1996), (1877, 2048, 2100),
                                 (2219, 2048, 1980), (1877, 2048, 2116)])
def test_pitch_arming_rejects_more_than_51_ticks_of_positive_travel(firmware_build, row):
    rows = (*CALIBRATED[:4], row, CALIBRATED[5])
    simulator = Firmware(firmware_build(rows))
    try:
        for command in ('ARM 16', 'ARM_JAW_DEMO'):
            assert simulator.command(command) == ['LOCKED PITCH_CALIBRATION_RANGE ID5']
        assert not writes(simulator.trace(), TORQUE)
    finally:
        simulator.close()


def test_positive_pitch_limits_the_goal_to_4_5_degrees_and_keeps_eight_tick_allowance(firmware):
    arm(firmware, 16)
    assert not firmware.command('GO 0 0 0 0 12')
    assert [(e.id, e.value) for e in writes(firmware.trace(), GOAL)] == [(5, 1997)]
    firmware.set(5, POSITION, 1997 - 8)
    assert firmware.tick(120)[0].endswith(' 4.500')
    firmware.set(5, POSITION, 1997 - 9)
    assert firmware.tick(120) == ['ERROR POSITION_LIMIT ID5', 'ERROR HOLD_UNCONFIRMED']
    assert not writes(firmware.trace(), TORQUE)


@pytest.mark.parametrize('row', [(2248, 2048, 1997), (1848, 2048, 2099)])
def test_pitch_arming_rejects_200_ticks_of_negative_travel(firmware_build, row):
    rows = (*CALIBRATED[:4], row, CALIBRATED[5])
    simulator = Firmware(firmware_build(rows))
    try:
        assert simulator.command('ARM 16') == ['LOCKED PITCH_CALIBRATION_RANGE ID5']
        assert not writes(simulator.trace(), TORQUE)
    finally:
        simulator.close()


@pytest.mark.parametrize('direction', [-1, 1])
def test_pitch_recovers_after_supported_return_from_a_negative_stop(firmware_build, direction):
    zero = 2048
    lower = zero + direction * 171
    row = (lower, zero, zero - direction * 51)
    rows = (*CALIBRATED[:4], row, CALIBRATED[5])
    simulator = Firmware(firmware_build(rows))
    try:
        arm(simulator, 16)
        assert not simulator.command('GO 0 0 0 0 -999')
        assert [e.value for e in writes(simulator.trace(), GOAL)] == [lower]
        simulator.set(5, POSITION, zero + direction * 186)
        assert simulator.tick(120) == ['ERROR POSITION_LIMIT ID5', 'ERROR HOLD_UNCONFIRMED']
        assert not writes(simulator.trace(), TORQUE)
        assert simulator.command('RELEASE') == ['RELEASED']
        simulator.trace()
        assert simulator.command('ARM 16') == ['LOCKED SERVO_CHECK ID5']
        assert simulator.command('REBOOT 5') == ['REBOOTED 5']
        assert simulator.command('ARM 16') == ['LOCKED SERVO_CHECK ID5']
        assert not writes(simulator.trace(), TORQUE)
        simulator.set(5, POSITION, zero)
        arm(simulator, 16)
    finally:
        simulator.close()


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
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2213]


def test_hold_discards_queued_setpoint(firmware):
    arm(firmware, 8)
    firmware.command('GO 0 0 0 15 0')
    firmware.command('GO 0 0 0 45 0')
    firmware.set(4, POSITION, 2100)
    firmware.command('HOLD')
    firmware.tick(60)
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2213, 2100]


@pytest.mark.parametrize(('mask', 'servo', 'measured', 'goal'), [
    (8, 4, 2710, 2707), (8, 4, 1386, 1389), (16, 5, 1994, 1997),
])
def test_hold_is_clamped_even_when_measured_tick_is_just_outside(firmware, mask, servo, measured, goal):
    arm(firmware, mask)
    firmware.set(servo, POSITION, measured)
    assert not firmware.command('HOLD')
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [goal]


@pytest.mark.parametrize(('endpoint', 'direction'), [(1389, -1), (2707, 1)])
@pytest.mark.parametrize('delta', [8, 9])
def test_report_limit_is_inclusive_at_eight_ticks(firmware, endpoint, direction, delta):
    arm(firmware, 8)
    firmware.set(4, POSITION, endpoint+direction*delta)
    reply = firmware.tick(120)
    if delta == 8:
        assert reply == [f'STATE 8 0.000 0.000 0.000 {60*direction:.3f} 0.000']
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
        (4, 2378, kind), (4, 2378, 'ok'),
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
    assert [(e.direction, e.id, e.register) for e in firmware.trace()] == [
        ('r', 5, 0), ('r', 5, STARTUP), ('r', 5, TORQUE), ('b', 5, 0),
    ]
    assert firmware.command('ARM 24') == ['LOCKED RELEASE_AFTER_FAULT']
    assert firmware.command('RELEASE') == ['RELEASED']
    arm(firmware, 24)


def test_reboot_is_refused_on_a_healthy_armed_axis(firmware):
    arm(firmware, 24)
    assert firmware.command('REBOOT 4') == ['ERROR REBOOT_WHILE_ARMED ID4']
    assert firmware.command('REBOOT 7') == ['ERROR REBOOT_ID']
    assert not any(e.direction == 'b' for e in firmware.trace())
    assert firmware.command('REBOOT 6') == ['REBOOTED 6']


def test_another_axis_fault_does_not_authorize_rebooting_healthy_pitch(firmware):
    arm(firmware, 24)
    firmware.fail('r', 4, POSITION, 'alert', 100)
    assert firmware.tick(120)[0] == 'ERROR READ_STATUS ID4'
    firmware.trace()
    assert firmware.command('REBOOT 5') == ['ERROR REBOOT_WHILE_ARMED ID5']
    assert all(e.direction == 'r' for e in firmware.trace())
    assert firmware.command('CHECK 5') == ['CHECK 5 1060 3 0 2 1 2048 1 0']


def test_cleared_alert_does_not_authorize_reboot_for_same_axis(firmware):
    arm(firmware, 16)
    firmware.fail('r', 5, POSITION, 'alert')
    assert firmware.tick(120)[0] == 'ERROR READ_STATUS ID5'
    firmware.set(5, TORQUE, 0)
    firmware.trace()
    assert firmware.command('REBOOT 5') == ['ERROR REBOOT_WHILE_ARMED ID5']
    assert all(e.direction == 'r' for e in firmware.trace())


def test_live_alert_with_torque_still_enabled_does_not_authorize_reboot(firmware):
    arm(firmware, 16)
    firmware.fail('r', 5, POSITION, 'alert', 100)
    firmware.fail('r', 5, TORQUE, 'alert', 100)
    assert firmware.tick(120)[0] == 'ERROR READ_STATUS ID5'
    firmware.trace()
    assert firmware.command('REBOOT 5') == ['ERROR REBOOT_TORQUE_ON ID5']
    assert all(e.direction == 'r' for e in firmware.trace())
    firmware.set(5, TORQUE, 0)
    assert firmware.command('REBOOT 5') == ['REBOOTED 5']


@pytest.mark.parametrize('kind', ['timeout', 'short', 'crc', 'instruction_crc', 'alert_denied', 'wrong_id'])
def test_reboot_refuses_an_unconfirmed_torque_read(firmware, kind):
    firmware.fail('r', 5, TORQUE, kind)
    assert firmware.command('REBOOT 5') == ['ERROR REBOOT_CHECK ID5']
    assert all(e.direction == 'r' for e in firmware.trace())


@pytest.mark.parametrize(('register', 'value', 'error'), [
    (0, 1190, 'REBOOT_CHECK'), (TORQUE, 1, 'REBOOT_TORQUE_ON'),
    (STARTUP, 1, 'REBOOT_STARTUP_CONFIG'), (STARTUP, 2, 'REBOOT_STARTUP_CONFIG'),
])
def test_reboot_checks_physical_state_even_when_not_armed(firmware, register, value, error):
    firmware.set(5, register, value)
    assert firmware.command('REBOOT 5') == [f'ERROR {error} ID5']
    assert all(e.direction == 'r' for e in firmware.trace())


def test_reboot_is_never_retried_when_acknowledgement_is_lost(firmware):
    firmware.fail('b', 5, 0, 'lost')
    assert firmware.command('REBOOT 5') == ['ERROR REBOOT ID5']
    assert [(e.id, e.result) for e in firmware.trace() if e.direction == 'b'] == [(5, 'lost')]


@pytest.mark.parametrize(('servo', 'delta'), [(4, 22), (4, -22), (5, 22), (5, -22)])
def test_neck_neutral_guard_accepts_at_most_two_degrees(firmware, servo, delta):
    firmware.set(servo, POSITION, 2048 + delta)
    assert firmware.command('CHECK_NECK') == ['NECK_NEUTRAL']
    firmware.set(servo, POSITION, 2048 + delta + (1 if delta > 0 else -1))
    assert firmware.command('CHECK_NECK') == [f'ERROR NECK_NOT_NEUTRAL ID{servo}']
    assert all(e.direction == 'r' for e in firmware.trace())


@pytest.mark.parametrize('closing', [False, True])
def test_persistent_jaw_lag_releases_only_the_jaw(firmware, closing):
    if closing:
        firmware.set(6, POSITION, 1938)
    arm(firmware, 56)
    firmware.exchange('follow 6 0')
    goal = 'GO 0 0 0 0 0 ' + ('0' if closing else '5.5')
    for _ in range(5):
        firmware.command(goal)
        assert firmware.tick(120)[0].startswith('STATE 56 ')
    firmware.command(goal)
    assert firmware.tick(120) == ['ERROR JAW_FOLLOW_TIMEOUT ID6']
    events = firmware.trace()
    assert [(e.id, e.value) for e in writes(events, TORQUE)] == [(6, 0)]
    assert {e.id for e in writes(events, GOAL)[-2:]} == {4, 5}
    assert firmware.command('CHECK 5') == ['CHECK 5 1060 3 0 2 1 2048 1 0']
    assert firmware.command('ARM 56') == ['LOCKED RELEASE_AFTER_FAULT']
    assert not firmware.command(goal)
    assert not writes(firmware.trace(), GOAL)


def test_jaw_settling_and_a_single_late_lag_sample_do_not_trip(firmware):
    arm(firmware, 32)
    firmware.exchange('follow 6 0')
    goal = 'GO 0 0 0 0 0 5.5'
    for _ in range(5):
        firmware.command(goal)
        assert firmware.tick(120)[0].startswith('STATE 32 ')
    firmware.set(6, POSITION, 1938 + 34)
    firmware.command(goal)
    assert firmware.tick(120)[0].startswith('STATE 32 ')
    firmware.set(6, POSITION, 1938 + 35)
    firmware.command(goal)
    assert firmware.tick(120)[0].startswith('STATE 32 ')
    assert not writes(firmware.trace(), TORQUE)


def test_jaw_lag_monitor_restarts_after_a_new_goal(firmware):
    arm(firmware, 32)
    firmware.exchange('follow 6 0')
    for _ in range(5):
        firmware.command('GO 0 0 0 0 0 5.5')
        assert firmware.tick(120)[0].startswith('STATE 32 ')
    firmware.command('GO 0 0 0 0 0 4')
    assert firmware.tick(120)[0].startswith('STATE 32 ')
    assert not writes(firmware.trace(), TORQUE)


def test_jaw_bus_fault_does_not_claim_unconfirmed_torque_release(firmware):
    arm(firmware, 56)
    firmware.fail('r', 6, POSITION, 'timeout', 2)
    firmware.fail('w', 6, TORQUE, 'timeout', 2)
    assert firmware.tick(120) == ['ERROR READ_BUS ID6', 'ERROR JAW_RELEASE_UNCONFIRMED ID6']
    events = firmware.trace()
    assert [(e.id, e.value) for e in writes(events, TORQUE)] == [(6, 0), (6, 0)]
    assert {e.id for e in writes(events, GOAL)} == {4, 5}
    assert firmware.command('CHECK 6')[0].split()[6] == '1'


def arm_jaw_demo(firmware):
    assert firmware.command('ARM_JAW_DEMO') == [
        'ARMED_JAW_DEMO 56', 'STATE 56 0.000 0.000 0.000 0.000 0.000 0.000',
    ]


def test_jaw_demo_drives_to_flashed_neutral_and_cannot_switch_into_tracking(firmware):
    firmware.set(4, POSITION, 2048 + 20)
    firmware.set(5, POSITION, 2048 - 20)
    arm_jaw_demo(firmware)
    assert [(e.id, e.value) for e in writes(firmware.trace(), GOAL)] == [
        (4, 2068), (5, 2028), (6, 2000), (4, 2048), (5, 2048),
    ]
    assert firmware.command('ARM 56') == ['ERROR RELEASE_BEFORE_JAW_DEMO_CHANGE']
    assert not writes(firmware.trace(), TORQUE)


def test_jaw_demo_rechecks_physical_neutral_before_a_new_jaw_goal(firmware):
    arm_jaw_demo(firmware)
    firmware.tick(240)
    firmware.trace()
    firmware.set(5, POSITION, 2048 + 23)
    assert firmware.command('GO 0 0 0 0 0 4') == ['ERROR NECK_NOT_NEUTRAL ID5']
    events = firmware.trace()
    assert [e.id for e in writes(events, GOAL)] == [4, 5]
    assert [(e.id, e.value) for e in writes(events, TORQUE)] == [(6, 0)]


def test_jaw_demo_stops_if_neck_is_no_longer_holding(firmware):
    arm_jaw_demo(firmware)
    firmware.tick(240)
    firmware.command('GO 0 0 0 0 0 4')
    firmware.trace()
    firmware.set(5, TORQUE, 0)
    assert firmware.tick(120) == ['ERROR JAW_DEMO_NECK_TORQUE ID5']
    events = firmware.trace()
    assert set(e.id for e in writes(events, GOAL)) == {4, 5}
    assert [(e.id, e.value) for e in writes(events, TORQUE)] == [(6, 0)]


def test_jaw_demo_waits_for_the_neck_centering_interval(firmware):
    arm_jaw_demo(firmware)
    firmware.trace()
    firmware.command('GO 0 0 0 0 0 4')
    firmware.tick(120)
    assert not writes(firmware.trace(), GOAL)
    firmware.tick(120)
    assert [(e.id, e.value) for e in writes(firmware.trace(), GOAL)] == [(6, 1955)]


def test_jaw_demo_refuses_a_non_neutral_neck_command(firmware):
    arm_jaw_demo(firmware)
    firmware.trace()
    assert firmware.command('GO 0 0 0 -1 0 4') == ['ERROR JAW_DEMO_NECK_GOAL']
    events = firmware.trace()
    assert {(e.id, e.value) for e in writes(events, GOAL)} == {(4, 2048), (5, 2048)}
    assert [(e.id, e.value) for e in writes(events, TORQUE)] == [(6, 0)]


def test_jaw_demo_neck_check_retries_one_bad_reply_and_rejects_wrong_id(firmware):
    arm_jaw_demo(firmware)
    firmware.fail('r', 4, POSITION, 'crc')
    assert firmware.tick(120)[0].startswith('STATE 56 ')
    firmware.fail('r', 5, TORQUE, 'wrong_id', 2)
    assert firmware.tick(120) == ['ERROR JAW_DEMO_NECK_READ ID5']
    assert [(e.id, e.value) for e in writes(firmware.trace(), TORQUE)[-1:]] == [(6, 0)]


def test_pacing_applies_latest_goal_as_reports_continue(firmware):
    _, period, report, _ = map(int, firmware.exchange('timing')[0].split())
    arm(firmware, 8)
    firmware.command('GO 0 0 0 5 0')
    firmware.command('GO 0 0 0 10 0')
    firmware.command('GO 0 0 0 25 0')
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2103]
    firmware.tick(period-1)
    assert not writes(firmware.trace(), GOAL)
    firmware.tick(1)
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2323]
    assert firmware.tick(report-period)[0].startswith('STATE 8 ')


def test_slow_usb_read_requests_do_not_flush_stale_goal_before_watchdog(firmware):
    arm(firmware, 8)
    firmware.command('GO 0 0 0 10 0')
    firmware.command('GO 0 0 0 40 0')
    firmware.tick(20)
    firmware.set(4, POSITION, 2100)
    firmware.fail('r', 4, POSITION, 'timeout', 32)
    firmware.receive(b'READ 4\n'*16)
    assert [e.value for e in writes(firmware.trace(), GOAL)] == [2158, 2100]


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
                         f'{direction*30} {direction*5} {3+direction*2}')
        states.extend(firmware.tick(10))
    goals = writes(firmware.trace(), GOAL)
    for servo in range(1, 7):
        times = [e.time for e in goals if e.id==servo]
        assert len(times) >= 15
        assert all(b-a >= period for a,b in zip(times,times[1:]))
    assert sum(line.startswith('STATE 63 ') for line in states) == 1000//report
