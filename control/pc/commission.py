"""Read a servo encoder without enabling torque, or explicitly release armed axes."""
from argparse import ArgumentParser
import time

import serial


def main():
    argument=ArgumentParser(description=__doc__)
    argument.add_argument('--serial',required=True)
    action=argument.add_mutually_exclusive_group(required=True)
    action.add_argument('--read',type=int,choices=range(1,7))
    action.add_argument('--release',action='store_true')
    args=argument.parse_args()
    with serial.Serial(args.serial,115200,timeout=.2,write_timeout=.3) as port:
        until=time.monotonic()+4
        while time.monotonic()<until:
            port.write(b'PING\n')
            if port.readline().strip()==b'R5B1 1':
                break
        else:
            raise SystemExit('R5 B1 OpenRB firmware did not answer.')
        port.write((f'READ {args.read}\n' if args.read else 'RELEASE\n').encode('ascii'))
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            line=port.readline().decode('ascii',errors='replace').strip()
            if line.startswith(('RAW ','RELEASED')):
                print(line)
                return
            if line.startswith('ERROR'):
                raise SystemExit(line)
        raise SystemExit('No reply from OpenRB.')


if __name__=='__main__':
    main()
