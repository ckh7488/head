"""Build the standalone B25 jaw-retention and closing-stop candidate."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path

import FreeCAD as App
import numpy as np
import trimesh

from build_b21_print import build as package
from build_b25_jaw_close_stop import apply as install_stops
from build_b25_jaw_retention import FRAME_PRINT, SHELL_PRINT, STATIONS, apply as retain_jaw


B25 = Path(__file__).resolve().parent / 'revisions/b25'
SOURCE_STAYS = ('36_left_cheek_servo_stay.stl', '37_right_cheek_bearing_stay-B22.stl')


def digest(path):
    with path.open('rb') as file:
        return file_digest(file, 'sha256').hexdigest()


def build(source, output):
    source = source.resolve()
    output = output.resolve()
    native = source/'R5-B25-Assembly.FCStd'
    source_project = source/'R5-B25-P2S.3mf'
    assembly = output/'R5-B25-Jaw-Assembly.FCStd'
    project = output/'R5-B25-Jaw-P2S.3mf'
    prints = output/'print'
    if source == output:
        raise ValueError('Choose an output directory separate from the original B25 files')
    prints.mkdir(parents=True, exist_ok=True)
    doc = App.openDocument(str(native))
    try:
        design = {'retention': retain_jaw(doc, prints), 'closing_stops': install_stops(doc, prints)}
        doc.recompute()
        doc.saveAs(str(assembly))
    finally:
        App.closeDocument(doc.Name)

    parts = {FRAME_PRINT: FRAME_PRINT}
    parts.update(zip(SOURCE_STAYS, (station[-1] for station in STATIONS), strict=True))
    replacements = {old: (new, trimesh.load_mesh(prints/new)) for old, new in parts.items()}
    skull = Path(SHELL_PRINT).with_suffix('.stl').name
    with np.load(prints/SHELL_PRINT) as data:
        replacements[skull] = skull, trimesh.Trimesh(data['vertices'], data['faces'], process=False)
    package(project, replacements, output/'print-build.json', support=parts, normal_support=parts,
            source=source_project, revision='B25', indexed_parts=(skull,))
    report = {
        'reference_cad_sha256': digest(native),
        'reference_project_sha256': digest(source_project),
        'cad_sha256': digest(assembly),
        'project_sha256': digest(project),
        'design': design,
    }
    (output/'design.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source', type=Path, default=B25)
    build(**vars(parser.parse_args()))
