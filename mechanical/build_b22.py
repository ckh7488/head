"""Build and check the B22 neck and jaw limiters."""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App

from build_b21 import ROOT, build_base, build_hardware, read_json, write_json
from build_b21_fasteners import B20_CAD
from build_b21_jaw_stop import B22_STOP, build as build_jaw_stop
from build_b22_camera_guides import apply as fit_camera_guides
from build_b22_neck_stop import build as build_neck_stop
from build_b22_pitch_link import fit as fit_pitch_link


def install_link(source, output, prints, camera_routing=None):
    doc = App.openDocument(str(source))
    try:
        label = 'R5 B22'
        doc.Label = label
        motion = json.loads(doc.R5.MotionGeometry)
        clevises = motion['pitch_clevises']
        fit_pitch_link(doc, prints, clevises['lower'], clevises['upper'])
        for name in ('BallastTray', 'BallastCover', 'BallastStack', 'BallastLeftStud', 'BallastRightStud'):
            doc.removeObject(name)
        motion = json.loads(doc.R5.MotionGeometry)
        motion['ballast']['supported'] = False
        doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)
        if camera_routing is not None:
            fit_camera_guides(doc, camera_routing, prints)
        doc.recompute()
        doc.saveAs(str(output))
    finally:
        App.closeDocument(doc.Name)


def record_camera_hardware(path, rows):
    document = read_json(path)
    for row in rows:
        kind = row.get('kind')
        if kind in ('nut', 'washer'):
            shape = row['shapes'][0]
            document['hardware'].append({
                'id': row['name'], 'type': kind, 'size': 2 if kind == 'nut' else 3,
                'seat': shape[3], 'axis': shape[4], 'exact_cad': True,
            })
    write_json(path, document)


def build(source, output, camera_routing=None):
    prints = output / 'print'
    base = build_base(source, output)
    neck = output / 'stages/neck.FCStd'
    linked = output / 'stages/pitch-link.FCStd'
    assembly = output / 'R5-B22-Assembly.FCStd'
    build_neck_stop(base, neck, prints)
    install_link(neck, linked, prints, camera_routing)
    build_jaw_stop(linked, assembly, prints / '37_right_cheek_bearing_stay-B22.stl',
                   output / 'jaw-stop.json', ROOT / 'mechanical/revisions/b20/physics/dynamics.json',
                   fea=True, spec=B22_STOP)
    build_hardware(output)
    spec = output / 'hardware-spec.json'
    hardware = read_json(spec) + read_json(prints / 'pitch-hardware.json')
    if camera_routing is not None:
        camera_hardware = read_json(prints / 'camera-hardware.json')
        hardware.extend(camera_hardware)
        record_camera_hardware(output / 'hardware.json', camera_hardware)
    write_json(spec, hardware)
    print(assembly)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source', type=Path, default=B20_CAD)
    parser.add_argument('--camera-routing', type=Path, help='B22 camera guide and centerline dimensions')
    args = parser.parse_args()
    build(args.source.resolve(), args.output.resolve(), read_json(args.camera_routing) if args.camera_routing else None)
