"""Export interference solids and fastener seats for the assembly walkthrough."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import sys

import FreeCAD as App
import Part
import trimesh

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'mechanical'))
sys.path.insert(0, str(ROOT / 'mechanical' / 'physics'))
from cable_assembly import check_paths
from export_cad import world_shape
from fixtures import (
    CAP_BOLT_LENGTH, CAP_BOLT_SEAT_Z, CAP_BOLT_Y, CAP_BOLTS, CAP_NUT_FLOOR_Z,
    CAP_NUT_ROOF_Z, CAP_NUT_TRAVEL, CAP_NUT_WIDTH, CAP_TRAVEL, SADDLE_BOLT_TRAVEL,
    SADDLE_INNER_TRAVEL, SADDLE_MOUNTS, SADDLE_NUT_Y, SADDLE_TRAVEL, SADDLE_WASHER_Y,
)
from motor_seats import HEAD_SEATS
from service_hatch import HATCH_MOUNTS, HATCH_NUT_SEAT, HATCH_SCREW_SEAT, HUB_MOUNTS, HUB_NUT_SEAT, HUB_SCREW_SEAT
from stock import socket_screw

V = App.Vector


def mesh(shape):
    vertices, faces = shape.tessellate(.06)
    return trimesh.Trimesh(vertices=[list(v) for v in vertices], faces=faces)


def export(cad, world, output):
    doc = App.openDocument(str(cad.resolve()))
    result = {
        'cad_sha256': sha256(cad.read_bytes()).hexdigest(), 'stops': {},
        'service_hatch': {
            'base_centers': HATCH_MOUNTS, 'base_nut_seat': HATCH_NUT_SEAT, 'base_screw_seat': HATCH_SCREW_SEAT,
            'board_centers': HUB_MOUNTS, 'board_nut_seat': HUB_NUT_SEAT, 'board_screw_seat': HUB_SCREW_SEAT,
        },
        'motor_caps': {
            part: [[size, list(V(*face) - depth * V(*outward)), list(-V(*outward))]
                   for size, face, outward, depth in seats]
            for part, seats in HEAD_SEATS.items()
        },
        'cable_assembly': {
            'x': CAP_BOLTS, 'y': CAP_BOLT_Y, 'nut_floor': CAP_NUT_FLOOR_Z, 'nut_roof': CAP_NUT_ROOF_Z,
            'nut_width': CAP_NUT_WIDTH, 'nut_travel': CAP_NUT_TRAVEL,
            'bolt_seat': CAP_BOLT_SEAT_Z, 'bolt_length': CAP_BOLT_LENGTH, 'cover_travel': CAP_TRAVEL,
            'tray_mounts': SADDLE_MOUNTS, 'tray_travel': SADDLE_TRAVEL, 'tray_bolt_travel': SADDLE_BOLT_TRAVEL,
            'tray_washer_y': SADDLE_WASHER_Y, 'tray_nut_y': SADDLE_NUT_Y, 'tray_inner_travel': SADDLE_INNER_TRAVEL,
        },
    }
    scene = trimesh.Scene()
    red = trimesh.visual.material.PBRMaterial(
        baseColorFactor=[255, 79, 71, 255], emissiveFactor=[.72, .055, .045], roughnessFactor=.65,
    )

    def shape(identifier):
        return world_shape(doc.getObject(identifier))

    def stl(identifier):
        return trimesh.load_mesh(world / f'{identifier}.stl')

    def put(name, geometry, material):
        geometry.visual = trimesh.visual.TextureVisuals(material=material)
        scene.add_geometry(geometry, node_name=name, geom_name=name)

    def record(name, remaining, pieces):
        keys, volume = [], 0.
        for raw in pieces:
            if isinstance(raw, Part.Shape):
                if raw.Volume < .001:
                    continue
                part, size = mesh(raw), raw.Volume
            else:
                part, size = raw, raw.volume
                if size < .001:
                    continue
            key = f'{name}-{len(keys) + 1}'
            put(key, part, red)
            keys.append(key)
            volume += size
        if not keys:
            raise ValueError(f'No modeled interference at {name}')
        result['stops'][name] = {'remaining': remaining, 'volume': round(volume, 2), 'nodes': keys}

    def overlap(moving_id, shift, fixed_ids):
        a = stl(moving_id).apply_translation(shift)
        return [trimesh.boolean.intersection([a, stl(identifier)], engine='manifold') for identifier in fixed_ids]

    try:
        check_paths(doc)
        motor = shape('Part017')
        rotor_offset = .5
        record('rotor', rotor_offset, [
            socket_screw(3, 10, (x, y, -37.9 + rotor_offset), (0, 0, 1)).common(motor)
            for x in (-12., 12.) for y in (11., 31.)
        ])

        mast_offset = .5
        stem = socket_screw(2, 6, (0., 8., -32.9), (0, 0, -1))
        record('mast', mast_offset, [stem.common(shape('Part010').translated(V(0, 0, mast_offset)))])

        pin_offset = 5.
        cradle = shape('Part024')
        pin = shape('Part028')
        record('eye-pin', pin_offset, [cradle.common(pin.translated(V(pin_offset, 0, 0)))])
        opened = cradle.cut(Part.makeCylinder(1.6, 11., V(56., -39., 119.), V(1, 0, 0)))
        assert opened.isValid() and len(opened.Solids) == 1
        for distance in range(25):
            assert opened.common(pin.translated(V(distance, 0, 0))).Volume < .0001
        put('cradle-reamed', mesh(opened), trimesh.visual.material.PBRMaterial(
            baseColorFactor=[93, 142, 130, 255], roughnessFactor=.58,
        ))

        record('front-shell', 15., overlap('Part073', (0, -15., 0), ('Part011', 'Part025', 'Part027')))
        record('front-orbit', 5., overlap('Part077', (0, -5., 0), ('Part073',)))
        record('rear-shell', .5, overlap('Part074', (0, .5, 0), ('Part021',)))
        output.mkdir(parents=True, exist_ok=True)
        (output / 'interference.glb').write_bytes(scene.export(file_type='glb'))
        (output / 'interference.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('world', type=Path, help='Directory of world-coordinate STL files from export_cad.py')
    parser.add_argument('--cad', type=Path, default=ROOT / 'mechanical' / 'R5-B10-Assembly.FCStd')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    export(args.cad, args.world, args.output)
