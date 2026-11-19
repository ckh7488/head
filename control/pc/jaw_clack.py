"""Exercise a calibrated R5 B1 jaw with two open-close cycles."""

from argparse import ArgumentParser
import time

from track import AXES, UsbController


def move(controller, target):
    deadline = time.monotonic() + 1.45
    goal = 'GO ' + '0 ' * len(AXES) + str(target)
    while (now := time.monotonic()) < deadline:
        controller.read()
        if controller.last_state is None or now - controller.last_state > .35:
            raise RuntimeError('Jaw feedback timed out.')
        if abs(controller.pose[-1] - target) <= .5:
            return
        controller.send(goal)
        time.sleep(.035)
    raise RuntimeError(f'Jaw did not reach {target} degrees.')


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--drive', action='store_true', required=True)
    args = parser.parse_args()
    controller = UsbController(args.serial, 1 << len(AXES))
    ready = False
    try:
        controller.start()
        ready = True
        for angle in (0, 10, 0, 13, 0):
            move(controller, angle)
    finally:
        if ready:
            controller.close()
        else:
            controller.link.close()


if __name__ == '__main__':
    main()
