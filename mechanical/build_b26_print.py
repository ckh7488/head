"""Make the B26 P2S project from the B25 project.

The base cup mesh is replaced by the B26 print mesh and gets a support blocker in each of
the four bracket-foot counterbores; the J2 keeper mesh is replaced; the two hatch-nut keeper
plates leave plate 12. Every other object, plate and setting is copied byte for byte.

The base edit is the same fill-and-cut set that build_b26_base_fasteners.py applies to the
CAD solid (written with --edits), applied to the B25 print mesh so its print-only details stay.

    python mechanical/build_b26_print.py mechanical/revisions/b25/R5-B25-P2S.3mf \
        build/b26/edits mechanical/revisions/b26/R5-B26-P2S.3mf
"""

from argparse import ArgumentParser
from pathlib import Path
import re
import uuid
from zipfile import ZIP_DEFLATED, ZipFile

import manifold3d as md
import numpy as np
import trimesh

BASE_MODEL = '3D/Objects/object_1.model'
BASE_OBJECT = '2'
KEEPERS = {'120': '3D/Objects/b23_hatch_keeper_1.model', '122': '3D/Objects/b23_hatch_keeper_2.model'}
PRINT_FRAME_Z = 56.   # the base is stored centred: assembly z = print z - 56


def solid(mesh):
    return md.Manifold(md.Mesh(np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.uint32)))


def base_mesh(model_xml):
    vertices = np.array(re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"/>', model_xml), float)
    faces = np.array(re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"', model_xml), int)
    return trimesh.Trimesh(vertices, faces, process=True)


def revised_base(model_xml, edits):
    old = base_mesh(model_xml)
    fills = trimesh.load(edits/'fills.stl', force='mesh').apply_translation((0, 0, PRINT_FRAME_Z))
    cuts = trimesh.load(edits/'cuts.stl', force='mesh').apply_translation((0, 0, PRINT_FRAME_Z))
    result = ((solid(old) + solid(fills)) - solid(cuts)).to_mesh()
    mesh = trimesh.Trimesh(result.vert_properties[:, :3], result.tri_verts, process=True)
    mesh.merge_vertices()
    return old, mesh


KEEPER_MODEL = '3D/Objects/b25_j2_keeper_1.model'
KEEPER_WORLD_MIN = np.array([6.65, 43.0, -72.5])     # A4J2LeverKeeper in the assembly frame (B25)


def object_mesh(model_xml):
    vertices = np.array(re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', model_xml), float)
    faces = np.array(re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"', model_xml), int)
    return trimesh.Trimesh(vertices, faces, process=False)


def revised_keeper(model_xml, edits):
    """Same keeper edits as the CAD, in the keeper object's own (centred) frame."""
    old = object_mesh(model_xml)
    shift = old.bounds[0] - KEEPER_WORLD_MIN
    fills = trimesh.load(edits/'keeper_fills.stl', force='mesh').apply_translation(shift)
    cuts = trimesh.load(edits/'keeper_cuts.stl', force='mesh').apply_translation(shift)
    result = ((solid(old) + solid(fills)) - solid(cuts)).to_mesh()
    mesh = trimesh.Trimesh(result.vert_properties[:, :3], result.tri_verts, process=True)
    mesh.merge_vertices()
    if not mesh.is_volume or mesh.body_count != 1:
        raise ValueError('B26 J2 keeper print mesh must be one closed body')
    return mesh


def mesh_xml(mesh):
    vertices = ''.join(f'<vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in mesh.vertices)
    triangles = ''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.faces)
    return f'<vertices>{vertices}</vertices><triangles>{triangles}</triangles>'


def drop_block(text, pattern, expected=1):
    result, count = re.subn(pattern, '', text, flags=re.S)
    if count != expected:
        raise ValueError(f'Expected {expected} match(es) for {pattern[:60]}, found {count}')
    return result


def build(source, edits, output, base_stl=None):
    with ZipFile(source) as old:
        names = old.namelist()
        for path in KEEPERS.values():
            if path not in names:
                raise ValueError(f'{path} not in the B25 project')
        files = {name: old.read(name) for name in names if name not in KEEPERS.values()}

    model = files[BASE_MODEL].decode('utf-8')
    old, mesh = revised_base(model, edits)
    if not mesh.is_volume or mesh.body_count != 1:
        raise ValueError('B26 base print mesh must be one closed body')
    if np.abs(old.bounds - mesh.bounds).max() > .01:
        raise ValueError('The B26 base edit changed the outer envelope of the print')
    if base_stl:
        mesh.export(base_stl)
    model, count = re.subn(r'<vertices>.*?</triangles>', lambda _: mesh_xml(mesh), model, flags=re.S)
    if count != 1:
        raise ValueError('Base object mesh not found')
    blocker = trimesh.load(edits/'support_blockers.stl', force='mesh').apply_translation((0, 0, PRINT_FRAME_Z))
    used = {int(i) for f in files.values() if isinstance(f, bytes)
            for i in re.findall(rb'<object id="(\d+)"', f)}
    blocker_id = str(max(used) + 1)
    object_uuid, component_uuid, part_uuid = (uuid.uuid5(uuid.NAMESPACE_URL, f'r5-b26/support-blocker/{k}')
                                              for k in ('object', 'component', 'part'))
    model = model.replace('</resources>', f' <object id="{blocker_id}" p:UUID="{object_uuid}" type="other">\n   <mesh>'
                          + mesh_xml(blocker) + '</mesh>\n  </object>\n </resources>', 1)
    files[BASE_MODEL] = model.encode('utf-8')

    keeper_model = files[KEEPER_MODEL].decode('utf-8')
    keeper = revised_keeper(keeper_model, edits)
    keeper_model, count = re.subn(r'<vertices>.*?</triangles>', lambda _: mesh_xml(keeper), keeper_model, flags=re.S)
    if count != 1:
        raise ValueError('Keeper object mesh not found')
    files[KEEPER_MODEL] = keeper_model.encode('utf-8')

    root = files['3D/3dmodel.model'].decode('utf-8')
    for ident in KEEPERS:
        root = drop_block(root, rf'\s*<object id="{ident}" [^>]*>.*?</object>')
        root = drop_block(root, rf'\s*<item objectid="{ident}" [^>]*/>')
    root = root.replace('<metadata name="Title">R5 B25 P2S</metadata>', '<metadata name="Title">R5 B26 P2S</metadata>')
    base_root = re.search(rf'<object id="{BASE_OBJECT}" [^>]*>.*?</object>', root, re.S).group(0)
    component = (f'<component p:path="/{BASE_MODEL}" objectid="{blocker_id}" p:UUID="{component_uuid}" '
                 'transform="1 0 0 0 1 0 0 0 1 0 0 0"/>')
    root = root.replace(base_root, base_root.replace('</components>', f' {component}\n   </components>', 1))
    files['3D/3dmodel.model'] = root.encode('utf-8')

    rels = files['3D/_rels/3dmodel.model.rels'].decode('utf-8')
    for path in KEEPERS.values():
        rels = drop_block(rels, rf'\s*<Relationship Target="/{re.escape(path)}"[^>]*/>')
    files['3D/_rels/3dmodel.model.rels'] = rels.encode('utf-8')

    settings = files['Metadata/model_settings.config'].decode('utf-8')
    for ident in KEEPERS:
        settings = drop_block(settings, rf'\s*<object id="{ident}">.*?</object>')
        settings = drop_block(settings, rf'\s*<model_instance>\s*<metadata key="object_id" value="{ident}"/>.*?</model_instance>')
    base = re.search(rf'<object id="{BASE_OBJECT}">.*?</object>', settings, re.S).group(0)
    revised = re.sub(r'face_count="\d+"', f'face_count="{len(mesh.faces)}"', base)
    revised = revised.replace('01_base_cup-hatch-capture', '01_base_cup-B26')
    matrix = re.search(r'<metadata key="matrix" value="([^"]+)"/>', base).group(1)
    part = (f'<part id="{blocker_id}" subtype="support_blocker" uuid="{part_uuid}">\n'
            '      <metadata key="name" value="counterbore support blocker"/>\n'
            f'      <metadata key="matrix" value="{matrix}"/>\n'
            f'      <mesh_stat face_count="{len(blocker.faces)}" edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n'
            '    </part>\n  ')
    revised = revised.replace('</object>', part + '</object>', 1)
    settings = settings.replace(base, revised)
    keeper_block = re.search(r'<object id="128">.*?</object>', settings, re.S).group(0)
    settings = settings.replace(keeper_block, re.sub(r'face_count="\d+"', f'face_count="{len(keeper.faces)}"', keeper_block))
    files['Metadata/model_settings.config'] = settings.encode('utf-8')

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as new:
        for name in names:
            if name in files:
                new.writestr(name, files[name])


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for name in ('source', 'edits', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--base-stl', type=Path, help='Also write the revised base print mesh')
    build(**vars(parser.parse_args()))
