"""Build the B24 eye bearings, pitch coupling and front shell from B23."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import FreeCAD as App
import numpy as np

from build_b22_fused_skull import fuse
from build_b24_blink_link import PRINT as LINK_PRINT
from build_b24_blink_link import apply as relieve_blink_link
from build_b24_blink_relief import apply as relieve_blink_shell
from build_b24_eye_bearings import PRINTS as EYE_PRINTS
from build_b24_eye_bearings import apply as install_eye_bearings
from build_b24_pitch_coupler import PRINT_NAME as CLAMP_PRINT
from build_b24_pitch_coupler import apply as install_pitch_coupler
from export_cad import world_mesh


BASE = Path(__file__).resolve().parent / 'revisions/b23/R5-B23-Assembly.FCStd'
TRAY_PRINT = BASE.parent/'printing/nasal-tray-with-pilots.stl'
FRONT_SKULL_PRINT = '28_skull_front_with_camera_tray-B24.npz'


def digest(path):
    with path.open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def write_front_skull(shell, tray, output):
    mesh = fuse(shell, tray, TRAY_PRINT)
    np.savez_compressed(output, vertices=mesh.vertices, faces=mesh.faces)


def build(output):
    output = output.resolve()
    prints = output/'print'
    prints.mkdir(parents=True, exist_ok=True)
    assembly = output/'R5-B24-Assembly.FCStd'
    doc = App.openDocument(str(BASE))
    try:
        doc.Label = 'R5 B24'
        doc.Part045.Label = 'XL330 M077 blink · ID 3'
        eye = install_eye_bearings(doc, prints)
        pitch = install_pitch_coupler(doc, prints)
        blink_shell = relieve_blink_shell(doc)
        blink_link = relieve_blink_link(doc, prints)
        doc.recompute()
        with TemporaryDirectory() as temporary:
            shell, tray = (Path(temporary)/name for name in ('shell.stl', 'tray.stl'))
            world_mesh(doc.Part073).write(str(shell))
            world_mesh(doc.Part065).write(str(tray))
            write_front_skull(shell, tray, prints/FRONT_SKULL_PRINT)
        doc.saveAs(str(assembly))
    finally:
        App.closeDocument(doc.Name)
    report = {
        'reference_cad_sha256': digest(BASE),
        'cad_sha256': digest(assembly),
        'blink_actuator': 'XL330-M077-T',
        'eye_pitch_bearings': eye,
        'pitch_coupler': pitch,
        'blink_shell_relief': blink_shell,
        'blink_link_relief': blink_link,
        'print_sha256': {name: digest(prints/name) for name in sorted(
            (FRONT_SKULL_PRINT, CLAMP_PRINT, LINK_PRINT, *EYE_PRINTS.values()))},
    }
    (output/'design.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(assembly)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
