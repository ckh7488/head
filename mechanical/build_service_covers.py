"""Build a separate review assembly and print meshes for the two service covers."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path

import FreeCAD as App

from build_service_cable_nuts import apply as retain_cable_nuts
from build_service_hatch_nuts import apply as retain_hatch_nuts


BASE = Path(__file__).resolve().parent / 'revisions/b22/R5-B22-Assembly.FCStd'


def digest(path):
    with path.open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def build(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    print_dir = output / 'print'
    assembly = output / 'R5-B22-Service-Covers.FCStd'
    doc = App.openDocument(str(BASE))
    try:
        retain_cable_nuts(doc, print_dir)
        hatch = retain_hatch_nuts(doc, print_dir)
        doc.recompute()
        metadata = json.loads(doc.R5.MotionGeometry)
        doc.saveAs(str(assembly))
    finally:
        App.closeDocument(doc.Name)
    manifest = {
        'reference_cad_sha256': digest(BASE),
        'review_cad_sha256': digest(assembly),
        'rear_cable': metadata['rear_cable_service_nuts'],
        'bottom_board': hatch,
        'print_meshes_sha256': {path.name: digest(path) for path in sorted(print_dir.glob('*.stl'))},
    }
    (output / 'service-covers.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
