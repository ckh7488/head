"""Build the B21 assembly, printable parts and matching hardware data."""

from argparse import ArgumentParser
import json
from pathlib import Path
import subprocess

import build_b21_fasteners as fasteners
import build_b21_jaw_stop as jaw_stop
import build_b21_links as links
import build_b21_mast as mast


ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def build_base(source, output):
    prints = output / 'print'
    stage = output / 'stages'
    fastener_cad = stage / 'fasteners.FCStd'
    link_cad = stage / 'links.FCStd'
    mast_cad = stage / 'mast.FCStd'
    fasteners.build(source, fastener_cad, prints)
    links.build(fastener_cad, link_cad, prints)
    mast.build(link_cad, mast_cad, prints)
    return mast_cad


def build_hardware(output):
    prints = output / 'print'
    initial = {row['name']: row for row in read_json(fasteners.B19_HARDWARE)}
    combined = {row['name']: row for row in read_json(prints / 'hardware-spec.json')}
    for name in links.RETIRED_CAD:
        combined.pop(name, None)
    for row in read_json(prints / 'link-hardware.json'):
        name = row['name']
        if row != initial.get(name):
            if name in combined and combined[name] != initial.get(name):
                raise ValueError(f'Conflicting fastener and linkage changes for {name}')
            combined[name] = row
    write_json(output / 'hardware-spec.json', list(combined.values()))

    script = ('import {steps,hardware} from "./web/assembly/steps.js"; '
              'process.stdout.write(JSON.stringify({steps,hardware}));')
    raw = subprocess.check_output(['node', '--input-type=module', '-e', script], cwd=ROOT)
    hardware = json.loads(raw)
    hardware['hardware'].extend(read_json(prints / 'hardware-rows.json'))
    write_json(output / 'hardware.json', hardware)


def build(source, output):
    assembly = output / 'R5-B21-Assembly.FCStd'
    mast_cad = build_base(source, output)
    jaw_stop.build(mast_cad, assembly, output / 'print/37_right_cheek_bearing_stay-B21.stl',
                   output / 'jaw-stop.json', ROOT / 'mechanical/revisions/b20/physics/dynamics.json', fea=True)
    build_hardware(output)
    print(assembly)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=fasteners.B20_CAD)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(args.source.resolve(), args.output.resolve())
