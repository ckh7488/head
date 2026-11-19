"""Read the mass of each printed part from Bambu's labelled G-code."""

from argparse import ArgumentParser
from collections import defaultdict
from math import pi
from pathlib import Path
import json
import re


MOVE = re.compile(r'^G[0123] (?=[^;]*[XY])[^;]*? E([-+.0-9]+)(?=[ ;\n])')
NOT_ON_PART = {
    'Custom', 'Skirt', 'Brim', 'Support', 'Support interface', 'Support transition',
    'Prime tower', 'Wipe tower',
}


def part_weights(gcode):
    labels = [0]
    extruded = defaultdict(float)
    object_id = 0
    feature = 'Custom'
    total = 0.
    with gcode.open() as source:
        for line in source:
            if line.startswith('; model label id: '):
                labels = [int(i) for i in line.split(':')[1].split(',')]
                object_id = None
            elif line.startswith('; total filament weight [g] : '):
                total = float(line.split(':')[1])
            elif line.startswith('; filament_density: '):
                density = float(line.split(':')[1])
            elif line.startswith('; filament_diameter: '):
                diameter = float(line.split(':')[1])
            elif line.startswith('; start printing object, unique label id: '):
                object_id = int(line.split(':')[1])
            elif line.startswith('; stop printing object, unique label id: '):
                object_id = None
            elif line.startswith('; FEATURE: '):
                feature = line[11:].strip()
            elif object_id is not None and feature not in NOT_ON_PART:
                if line.startswith('M82'):
                    raise ValueError(f'{gcode} switched to absolute extrusion inside an object')
                move = MOVE.match(line)
                if move:
                    extruded[object_id] += max(0., float(move[1]))
    grams_per_mm = density * pi * diameter**2 / 4000.
    masses = [grams_per_mm * extruded[label] for label in labels]
    if not masses or min(masses) <= 0. or sum(masses) > total * 1.002:
        raise ValueError(f'{gcode} has incomplete or inconsistent extrusion labels')
    return masses


def read_plates(paths):
    output = defaultdict(float)
    for gcode in paths:
        number = int(gcode.stem.rsplit('_', 1)[1])
        result = json.loads((gcode.parent/'result.json').read_text())
        plate = next(p for p in result['sliced_plates'] if p['id'] == number)
        objects = plate['objects']
        for settings, mass in zip(objects, part_weights(gcode), strict=True):
            output[settings['name'].removesuffix('_1').lower()] += mass
    return dict(output)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('gcode', type=Path, nargs='+')
    args = parser.parse_args()
    args.output.write_text(json.dumps(read_plates(args.gcode), indent=2))
