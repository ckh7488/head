"""Test a specified bend radius at the assembled ID 1 motor plug in 3D."""
from argparse import ArgumentParser
from itertools import product
import json
from pathlib import Path
import sys

import numpy as np
import trimesh as tr

from wiring_check import Cable, Scene
from wiring_motion import matrices, transform

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor_ports import EHR_PORTS


def exits(cad):
    layout = json.loads((cad/'cad_parts.json').read_text(encoding='utf-8'))
    scene = Scene.__new__(Scene)
    scene.groups = {}
    for name in ('Part010','Part011','Part018','Part019','Part024','Part038','Jaw_30_moving_jaw'):
        mesh = tr.load_mesh(cad/'world'/f'{name}.stl')
        scene.add(name, layout['world_motion'][name], mesh)
    _, terminal, row, direction = EHR_PORTS['ID1EH']
    across, tangent = np.array(row), np.array(direction)
    other = np.cross(across, tangent)
    diameter = 1.143
    radius = 5*diameter
    turn = np.linspace(0., np.pi/2, 20)
    along = radius*np.sin(turn[:,None])*tangent
    away = radius*(1.-np.cos(turn[:,None]))
    for pitch, eye in product((-15., 0., 6.), (-8., 0., 8.)):
        pose = matrices(layout, pitch=pitch, eye=eye)
        passed = []
        for pin in (-1, 0, 1):
            origin = np.array(terminal) + 2.5*pin*across
            count = 0
            for angle in np.radians(np.arange(0,360,5)):
                side = np.cos(angle)*across + np.sin(angle)*other
                points = transform(origin + along + away*side, pose['tilt'])
                lead = Cable('motor1-power',points,diameter,radius*np.pi/2,radius)
                count += not scene.hits(lead,pose)
            passed.append(count)
        print(f'neck {pitch:+g}°, eye {eye:+g}°: 72 tangent turns per terminal, clear {passed}',flush=True)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad',type=Path)
    exits(parser.parse_args().cad)
