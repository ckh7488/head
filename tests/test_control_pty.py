from contextlib import contextmanager
import os
from pathlib import Path
import select
import subprocess
import sys
from threading import Event, Thread
import time

import pytest

from track import Planner, UsbController

PC = Path(__file__).resolve().parents[1] / 'control' / 'pc'


@contextmanager
def terminal(firmware):
    pty = pytest.importorskip('pty')
    tty = pytest.importorskip('tty')
    pytest.importorskip('serial')
    master, slave = pty.openpty()
    tty.setraw(slave)
    stop = Event()
    errors = []

    def bridge():
        previous = time.monotonic()
        try:
            while not stop.is_set():
                ready, _, _ = select.select([master], [], [], .008)
                now = time.monotonic()
                elapsed = int((now-previous)*1000)
                replies = []
                if elapsed:
                    replies.extend(firmware.tick(elapsed))
                    previous += elapsed/1000
                if ready:
                    replies.extend(firmware.receive(os.read(master, 1024)))
                if replies:
                    os.write(master, ('\n'.join(replies)+'\n').encode('ascii'))
        except Exception as error:
            errors.append(error)

    worker = Thread(target=bridge, daemon=True)
    worker.start()
    try:
        yield os.ttyname(slave)
    finally:
        stop.set()
        worker.join(timeout=4)
        os.close(master)
        os.close(slave)
        assert not worker.is_alive()
        assert not errors


def pc(script, path, *args):
    return subprocess.run([sys.executable, str(PC/script), '--serial', path, *args],
                          text=True, capture_output=True, timeout=10)


def test_commission_reads_and_checks_six_axes_over_usb(firmware):
    with terminal(firmware) as port:
        raw = pc('commission.py', port, '--read', '3')
        check = pc('commission.py', port, '--check')
    assert raw.returncode == 0, raw.stderr
    assert raw.stdout.strip() == 'RAW 3 2000'
    assert check.returncode == 0, check.stderr
    assert len(check.stdout.splitlines()) == 6
    assert all('OK' in line and 'torque=0' in line for line in check.stdout.splitlines())
    assert all(e.direction == 'r' for e in firmware.trace())


def test_commission_preflight_reports_missing_board_and_unset_calibration(uncalibrated):
    uncalibrated.fail('r', 3, 0, 'timeout', 2)
    with terminal(uncalibrated) as port:
        check = pc('commission.py', port, '--check')
    assert check.returncode == 1
    assert 'ID 3  ERROR CHECK_BUS_OR_STATUS ID3' in check.stdout
    assert 'calibrated=0' in check.stdout
    assert '6 of 6 axes need attention' in check.stderr
    assert all(e.direction == 'r' for e in uncalibrated.trace())


def test_commission_does_not_report_a_failed_release_as_complete(firmware):
    firmware.command('ARM 16')
    firmware.fail('w', 5, 64, 'timeout', 2)
    with terminal(firmware) as port:
        failed = pc('commission.py', port, '--release')
        released = pc('commission.py', port, '--release')
    assert failed.returncode == 1
    assert 'RELEASE_UNCONFIRMED' in failed.stderr
    assert released.returncode == 0, released.stderr
    assert released.stdout.strip() == 'RELEASED'


def test_commission_reboots_only_the_confirmed_torque_off_faulted_axis(firmware):
    firmware.command('ARM 24')
    firmware.fail('r', 4, 132, 'alert', 100)
    firmware.fail('r', 4, 64, 'alert', 100)
    assert firmware.tick(120)[0] == 'ERROR READ_STATUS ID4'
    firmware.trace()
    with terminal(firmware) as port:
        unrelated = pc('commission.py', port, '--reboot', '5')
        still_energized = pc('commission.py', port, '--reboot', '4')
        firmware.set(4, 64, 0)
        recovered = pc('commission.py', port, '--reboot', '4')
    assert unrelated.returncode == 1 and 'REBOOT_WHILE_ARMED ID5' in unrelated.stderr
    assert still_energized.returncode == 1 and 'REBOOT_TORQUE_ON ID4' in still_energized.stderr
    assert recovered.returncode == 0, recovered.stderr
    assert recovered.stdout.strip() == 'REBOOTED 4'
    assert [e.id for e in firmware.trace() if e.direction == 'b'] == [4]


def test_jaw_clack_runs_through_the_compiled_sketch(firmware):
    with terminal(firmware) as port:
        result = pc('jaw_clack.py', port, '--drive')
    assert result.returncode == 0, result.stderr
    events = firmware.trace()
    commands = [e for e in events if e.direction == 'w' and e.register == 116]
    assert {(e.id, e.value) for e in commands if e.id in (4, 5)} == {(4, 2048), (5, 2048)}
    assert [e.value for e in commands if e.id == 6][:5] == [2000, 1955, 2000, 1938, 2000]
    assert [(e.id, e.value) for e in events if e.direction == 'w' and e.register == 64] == [
        (4, 1), (5, 1), (6, 1),
    ]


def test_jaw_clack_stops_on_a_stalled_servo(firmware):
    firmware.exchange('follow 6 0')
    with terminal(firmware) as port:
        result = pc('jaw_clack.py', port, '--drive')
    assert result.returncode == 1
    assert result.stderr.strip() == 'ERROR JAW_FOLLOW_TIMEOUT ID6'
    events = firmware.trace()
    assert [(e.id, e.value) for e in events if e.direction == 'w' and e.register == 64] == [
        (4, 1), (5, 1), (6, 1), (6, 0),
    ]


@pytest.mark.parametrize(('failure', 'message'), [
    ('off_center', 'NECK_NOT_NEUTRAL'), ('no_position', 'NECK_CHECK'),
])
def test_jaw_clack_refuses_to_arm_without_neutral_neck_confirmation(firmware, failure, message):
    if failure == 'off_center':
        firmware.set(5, 132, 1997)
    else:
        firmware.fail('r', 5, 132, 'timeout', 2)
    with terminal(firmware) as port:
        result = pc('jaw_clack.py', port, '--drive')
    assert result.returncode == 1 and f'{message} ID5' in result.stderr
    assert all(e.direction == 'r' for e in firmware.trace())


def test_tracking_usb_receives_feedback_and_propagates_bus_fault(firmware):
    with terminal(firmware) as port:
        controller = UsbController(port, 8)
        try:
            controller.start()
            planner = Planner()
            move = planner.step((12., 0.), controller.pose, 0.)
            assert move.active
            controller.send('GO '+' '.join(f'{angle:.3f}' for angle in move.goals))
            deadline = time.monotonic()+2.
            while controller.pose[3] == 0 and time.monotonic()<deadline:
                controller.read()
                time.sleep(.006)
            assert controller.pose[3] > 0
            firmware.fail('r', 4, 132, 'timeout', 8)
            deadline = time.monotonic()+2.
            with pytest.raises(RuntimeError, match='READ_BUS ID4'):
                while time.monotonic()<deadline:
                    controller.read()
                    time.sleep(.006)
        finally:
            controller.close()
    assert not any(e.direction == 'w' and e.register == 64 and e.value == 0 for e in firmware.trace())


def test_exhibit_host_keeps_five_feedback_fields_with_closed_jaw_torque(firmware):
    with terminal(firmware) as port:
        controller = UsbController(port, 31)
        try:
            controller.start(exhibit=True)
            assert controller.jaw_hold is True
            assert controller.pose == (0.,) * 5
            controller.send('GO_EXHIBIT 0 0 0 5 0')
            deadline = time.monotonic() + 2.
            while controller.pose[3] == 0 and time.monotonic() < deadline:
                controller.read()
                time.sleep(.006)
            assert controller.pose[3] > 0
        finally:
            controller.close()
    jaw = [e for e in firmware.trace() if e.id == 6 and e.direction == 'w']
    assert [e.value for e in jaw if e.register == 116] == [2000]
    assert [e.value for e in jaw if e.register == 64] == [1]
