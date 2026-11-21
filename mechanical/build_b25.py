"""Build the B25 design candidate from the archived B24 assembly and P2S project."""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App
import numpy as np
import trimesh

from build_b21_print import build as pack_prints
from build_b24 import digest
from build_b25_blink_fit import SKULL_REPLACE, apply as fit_blink, print_replacements
from build_b25_hatch_envelope import apply as fit_terminal
from build_b25_rear_retention import FRAME_PRINT, REAR_PRINT, apply as retain_rear


BASE = Path(__file__).resolve().parent / 'revisions/b24'
ASSEMBLY = BASE / 'R5-B24-Assembly.FCStd'
PROJECT = BASE / 'R5-B24-P2S.3mf'
REAR_SOURCE = '29_skull_rear.stl'
FRAME_SOURCE = '09_head_frame-B22.stl'


def build(output):
    output = output.resolve()
    prints = output / 'print'
    prints.mkdir(parents=True, exist_ok=True)
    assembly = output / 'R5-B25-Assembly.FCStd'
    project = output / 'R5-B25-P2S.3mf'
    doc = App.openDocument(str(ASSEMBLY))
    try:
        doc.Label = 'R5 B25'
        geometry = {
            'rear_skull_retention': retain_rear(doc, prints),
            'blink_fit': fit_blink(doc, prints),
            'hatch_terminal': fit_terminal(doc),
        }
        doc.recompute()
        doc.saveAs(str(assembly))
    finally:
        App.closeDocument(doc.Name)

    replacements = print_replacements(prints)
    with np.load(prints / REAR_PRINT) as data:
        rear = trimesh.Trimesh(vertices=data['vertices'], faces=data['faces'], process=False)
    replacements[REAR_SOURCE] = Path(REAR_PRINT).with_suffix('.stl').name, rear
    replacements[FRAME_SOURCE] = FRAME_PRINT, trimesh.load_mesh(prints / FRAME_PRINT)
    pack_prints(project, replacements, output / 'print-build.json', source=PROJECT, revision='B25',
                indexed_parts=(SKULL_REPLACE, REAR_SOURCE))
    report = {
        'source_cad_sha256': digest(ASSEMBLY),
        'cad_sha256': digest(assembly),
        'p2s_sha256': digest(project),
        'geometry': geometry,
        'print_inputs_sha256': {path.name: digest(path) for path in sorted(prints.iterdir()) if path.is_file()},
    }
    (output / 'design.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
