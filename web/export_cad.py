"""Export the current FreeCAD assembly as viewer geometry."""

from argparse import ArgumentParser
from pathlib import Path
import json

import numpy as np
import trimesh

ASSETS = Path(__file__).resolve().parent / 'assets'
COLORS = {
    'bone': (220, 204, 177), 'jaw': (214, 198, 169), 'graphite': (56, 66, 70),
    'shroud': (37, 44, 47), 'steel': (139, 153, 161), 'link': (164, 117, 65),
    'frame': (93, 142, 130), 'gear': (44, 50, 56), 'eye': (228, 232, 218),
    'iris': (77, 123, 103), 'pupil': (12, 17, 17), 'glass': (29, 41, 50),
    'pcb': (48, 106, 76), 'connector': (194, 196, 180), 'power': (225, 171, 51),
    'terminal': (85, 145, 107), 'fuse': (181, 92, 67), 'capacitor': (112, 114, 117),
}
TRIANGLE_LIMITS = {'bone': 35000, 'jaw': 11000, 'eye': 9000, 'gear': 9500}
ASSEMBLY_MATING_PARTS = {'Part000', 'HubHolder', 'Part019', 'Part073'}
ROBOTIS_MOTORS = {'Part017', 'Part018', 'Part038', 'Part041', 'Part045', 'Jaw_XL330_M288_Jaw'}


def export(cad, output, manifest_path):
    manifest = json.loads(manifest_path.read_text())
    layout = json.loads((cad / 'cad_parts.json').read_text())
    motions = layout['world_motion']
    manifest['cad_sha256'] = layout['source_sha256']
    if eye_pitch := layout.get('motion_geometry', {}).get('eye_pitch'):
        manifest['eye_pitch'] = eye_pitch
    else:
        manifest.pop('eye_pitch', None)
    materials = {
        name: trimesh.visual.material.PBRMaterial(
            name=name, baseColorFactor=np.array((*rgb, 255), dtype=np.uint8),
            roughnessFactor=.58, metallicFactor=.5 if name == 'steel' else 0.,
        )
        for name, rgb in COLORS.items()
    }
    scene = trimesh.Scene()
    for part in manifest['parts']:
        identifier = part['cad_id']
        mesh = trimesh.load_mesh(cad / 'world' / f'{identifier}.stl')
        limit = TRIANGLE_LIMITS.get(part['finish'], 5500)
        if identifier in ROBOTIS_MOTORS:
            mesh = mesh.smooth_shaded
        elif identifier not in ASSEMBLY_MATING_PARTS and len(mesh.faces) > limit:
            mesh = mesh.simplify_quadric_decimation(face_count=limit)
        mesh.visual = trimesh.visual.TextureVisuals(material=materials[part['finish']])
        part['motion'] = motions[identifier]
        part['bounds'] = mesh.bounds.round(3).tolist()
        scene.add_geometry(mesh, node_name=part['name'], geom_name=part['name'])
    output.mkdir(parents=True, exist_ok=True)
    (output / 'assembly.glb').write_bytes(trimesh.exchange.gltf.export_glb(scene, include_normals=True))
    (output / 'assembly.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--manifest', type=Path, default=ASSETS / 'assembly.json')
    args = parser.parse_args()
    export(args.cad, args.output, args.manifest)
