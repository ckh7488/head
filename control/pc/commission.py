"""Check or read servos without enabling torque, check and release all six expected drives, or reboot one servo."""
from argparse import ArgumentParser
import time

import serial


def request(port, command, expected):
    port.write((command+'\n').encode('ascii'))
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        line=port.readline().decode('ascii',errors='replace').strip()
        if expected(line):
            return line
        if line.startswith('ERROR'):
            raise RuntimeError(line)
    raise RuntimeError(f'No reply to {command}.')


def check_axes(port):
    failures=0
    for axis in range(1,7):
        try:
            reply=request(port,f'CHECK {axis}',lambda line: line.startswith(f'CHECK {axis} '))
            model,mode,drive,return_level,torque,ticks,calibrated,ready=map(int,reply.split()[2:])
        except (ValueError,RuntimeError) as error:
            print(f'ID {axis}  {error}')
            failures+=1
            continue
        result='OK' if ready==1 else 'CHECK'
        print(f'ID {axis}  {result}  model={model} mode={mode} drive={drive} '
              f'return={return_level} torque={torque} ticks={ticks} calibrated={calibrated}')
        failures+=ready!=1
    if failures:
        raise SystemExit(f'{failures} of 6 axes need attention.')


def main():
    argument=ArgumentParser(description=__doc__)
    argument.add_argument('--serial',required=True)
    action=argument.add_mutually_exclusive_group(required=True)
    action.add_argument('--read',type=int,choices=range(1,7))
    action.add_argument('--check',action='store_true',help='Read readiness and torque status for all six servos')
    action.add_argument('--release',action='store_true',help='Support the head and confirm torque off on IDs 1–6')
    action.add_argument('--reboot',type=int,choices=range(1,7),
                        help='Reboot one servo after its torque is verified off. Support the head first.')
    args=argument.parse_args()
    with serial.Serial(args.serial,115200,timeout=.2,write_timeout=.3) as port:
        until=time.monotonic()+4
        while time.monotonic()<until:
            port.write(b'PING\n')
            if port.readline().strip()==b'R5B1 1':
                break
        else:
            raise SystemExit('R5 B1 OpenRB firmware did not answer.')
        try:
            if args.check:
                check_axes(port)
            elif args.read:
                print(request(port,f'READ {args.read}',lambda line: line.startswith(f'RAW {args.read} ')))
            elif args.reboot:
                print(request(port,f'REBOOT {args.reboot}',lambda line: line==f'REBOOTED {args.reboot}'))
            else:
                print(request(port,'RELEASE',lambda line: line=='RELEASED'))
        except RuntimeError as error:
            raise SystemExit(str(error)) from error


if __name__=='__main__':
    main()
