from collections import namedtuple
import os
from pathlib import Path
from queue import Queue
import shlex
import shutil
import subprocess
import sys
from threading import Lock, Thread

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKETCH = ROOT / 'control' / 'openrb' / 'R5B1'
HARNESS = ROOT / 'tests' / 'firmware'
sys.path.insert(0, str(ROOT / 'control' / 'pc'))

CALIBRATED = (
    (1820, 2048, 2276),
    (2139, 2048, 1957),
    (2000, 2000, 3024),
    (1365, 2048, 2731),
    (2219, 2048, 1980),
    (2000, 2000, 1852),
)
Event = namedtuple('Event', 'direction id register value result time')


@pytest.fixture(scope='session')
def firmware_build(tmp_path_factory):
    compiler = shlex.split(os.environ.get('CXX', 'c++'))
    if not compiler or shutil.which(compiler[0]) is None:
        pytest.skip('A host C++ compiler is needed to run the sketch.')

    def build(rows):
        folder = tmp_path_factory.mktemp('openrb')
        shutil.copyfile(SKETCH / 'R5B1.ino', folder / 'R5B1.ino')
        header = (SKETCH / 'Calibration.h').read_text()
        calibration = ',\n'.join('  {' + ', '.join(map(str, row)) + '}' for row in rows)
        (folder / 'Calibration.h').write_text(header.split('constexpr Calibration ')[0] +
                                              f'constexpr Calibration calibration[] = {{\n{calibration}\n}};\n')
        executable = folder / ('openrb.exe' if os.name == 'nt' else 'openrb')
        subprocess.run([*compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-I', str(folder), '-I', str(HARNESS), str(HARNESS / 'main.cpp'),
                        '-o', str(executable)], check=True, timeout=30)
        return executable

    return build


@pytest.fixture(scope='session')
def calibrated_binary(firmware_build):
    return firmware_build(CALIBRATED)


@pytest.fixture(scope='session')
def unset_binary(firmware_build):
    return firmware_build(((-1, -1, -1),)*6)


class Firmware:
    def __init__(self, binary):
        self.child = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      text=True, encoding='ascii', bufsize=1)
        self.output = Queue()
        self.lock = Lock()
        self.reader = Thread(target=self.read_output, daemon=True)
        self.reader.start()

    def read_output(self):
        for line in self.child.stdout:
            self.output.put(line.rstrip('\n'))
        self.output.put(None)

    def exchange(self, instruction):
        with self.lock:
            self.child.stdin.write(instruction+'\n')
            self.child.stdin.flush()
            replies = []
            while (line := self.output.get(timeout=3)) != '@done':
                if line is None:
                    raise RuntimeError(f'Virtual OpenRB exited during {instruction}.')
                replies.append(line)
            return replies

    def receive(self, data):
        return self.exchange('receive '+data.hex(' '))

    def command(self, command):
        return self.receive(command.encode('ascii')+b'\n')

    def tick(self, milliseconds):
        return self.exchange(f'tick {milliseconds}')

    def fail(self, direction, servo, register, kind, times=1):
        self.exchange(f'fail {direction} {servo} {register} {kind} {times}')

    def set(self, servo, register, value):
        self.exchange(f'set {servo} {register} {value}')

    def trace(self):
        events = []
        for line in self.exchange('trace'):
            direction, servo, register, value, result, at = line.split()
            events.append(Event(direction, int(servo), int(register), int(value), result, int(at)))
        return events

    def close(self):
        self.child.stdin.close()
        try:
            self.child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.child.kill()
            self.child.wait()
        self.reader.join(timeout=2)
        self.child.stdout.close()


@pytest.fixture
def firmware(calibrated_binary):
    simulator = Firmware(calibrated_binary)
    try:
        yield simulator
    finally:
        simulator.close()


@pytest.fixture
def uncalibrated(unset_binary):
    simulator = Firmware(unset_binary)
    try:
        yield simulator
    finally:
        simulator.close()
