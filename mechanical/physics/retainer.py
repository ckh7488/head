"""Pull the captured plug shoulders against the B4 stop with zero friction."""

from argparse import ArgumentParser
from itertools import product
from pathlib import Path
import json
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

MM = .001
FACE_GAP_MM = .10
GUIDE_GAP_MM = .12
SLOT_WORST_OVERSIZE_MM = .40


def model(lane, dt):
    width, height = np.array(lane['minimum_shoulder_mm']) * MM
    slot_x, slot_z = (np.array(lane['slot_mm']) + SLOT_WORST_OVERSIZE_MM) * MM
    if width <= slot_x or height <= slot_z:
        raise ValueError(f"{lane['name']} has insufficient shoulder engagement")

    root = ET.Element('mujoco', model=lane['name'])
    ET.SubElement(root, 'option', timestep=str(dt), gravity='0 0 0',
                  integrator='implicitfast', iterations='60', tolerance='1e-10')
    default = ET.SubElement(root, 'default')
    ET.SubElement(default, 'geom', friction='0 0 0', condim='1',
                  solref='.005 1', solimp='.985 .999 .0002')
    world = ET.SubElement(root, 'worldbody')
    gap = GUIDE_GAP_MM * MM
    sleeve_x, sleeve_z = width/2 + gap, height/2 + gap
    block_thickness = .002

    def block(parent, name, center, size):
        ET.SubElement(parent, 'geom', name=name, type='box',
                      pos=' '.join(str(x) for x in center),
                      size=' '.join(str(x/2) for x in size))

    for side in (-1, 1):
        block(world, f'guide_x_{side}', (side*(sleeve_x+.001), -.011, 0.),
              (block_thickness, .022, 2*sleeve_z+.004))
        block(world, f'guide_z_{side}', (0., -.011, side*(sleeve_z+.001)),
              (2*sleeve_x, .022, block_thickness))
        stop_x = sleeve_x + .001 - slot_x/2
        stop_z = sleeve_z + .001 - slot_z/2
        block(world, f'stop_x_{side}', (side*(slot_x/2+stop_x/2), .00325, 0.),
              (stop_x, .0065, 2*sleeve_z+.002))
        block(world, f'stop_z_{side}', (0., .00325, side*(slot_z/2+stop_z/2)),
              (slot_x, .0065, stop_z))

    length = .015
    body = ET.SubElement(world, 'body', name='plug', pos=f'0 {-length/2-FACE_GAP_MM*MM} 0')
    ET.SubElement(body, 'freejoint')
    block(body, 'shoulder', (0., 0., 0.), (width, length, height))
    return mujoco.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'))


def pull(lane, force, direction, hold, dt=.001):
    machine = model(lane, dt)
    data = mujoco.MjData(machine)
    initial = data.qpos[:3].copy()
    body = machine.body('plug').id
    local_arm = np.array([0., .0075, 0.])
    vector = force * np.asarray(direction, dtype=float)
    peak = np.zeros(3)
    max_advance = 0.
    for step in range(round((hold+1)/dt)):
        strength = min(step*dt, 1.)
        data.xfrc_applied[body, :3] = strength * vector
        arm = data.xmat[body].reshape(3,3) @ local_arm
        data.xfrc_applied[body, 3:] = np.cross(arm, strength*vector)
        mujoco.mj_step(machine, data)
        displacement = (data.qpos[:3]-initial)/MM
        peak = np.maximum(peak, abs(displacement))
        max_advance = max(max_advance, float(displacement[1]))
    if not np.all(np.isfinite(peak)) or max_advance > .35 or peak.max() > .5:
        raise RuntimeError(f"{lane['name']} escaped or shifted excessively: {peak} mm")
    return {'lane': lane['name'], 'load_N': force, 'direction': list(direction),
            'hold_sec': hold, 'axial_advance_mm': max_advance,
            'peak_component_mm': peak.tolist()}


def verify(layout):
    d = math.sqrt(.5)
    directions = ((0., 1., 0.), (d, d, 0.), (-d, d, 0.), (0., d, d), (0., d, -d))
    trials = [pull(lane, 10., direction, 30.) for lane, direction in product(layout['lanes'], directions)]
    trials.extend(pull(lane, 20., (0., d, d), 6.) for lane in layout['lanes'])
    return {'friction': 0., 'shoulder_face_gap_mm': FACE_GAP_MM,
            'guide_gap_each_side_mm': GUIDE_GAP_MM, 'slot_oversize_mm': SLOT_WORST_OVERSIZE_MM,
            'trials': trials}


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    source = json.loads((args.cad/'cad_parts.json').read_text())
    result = verify(source['motion_geometry']['cables'])
    result['cad_sha256'] = source['source_sha256']
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2))
    print(f"{len(result['trials'])} pulls, maximum axial advance "
          f"{max(row['axial_advance_mm'] for row in result['trials']):.3f} mm")
