"""Thicken the B25 right pitch drive pin ligament and relieve the nearby internal skull rib."""

from argparse import ArgumentParser
from hashlib import sha256
from io import BytesIO
from itertools import product
import json
from pathlib import Path
from zipfile import ZipFile

import FreeCAD as App
import Mesh
import MeshPart
import numpy as np
import Part
import trimesh

from build_b19_review_fixes import replace, world_shape
from build_b20_print import replace_mesh
from build_b22_fused_skull import solid
from build_b25_bearing_fit import archived_mesh
from build_b25_jaw_retention import mesh_from_solid, replace_mesh as replace_native_mesh
from build_b25_large_bearing_variants import write_entry
from export_cad import world_mesh

FRAME_PRINT = '09_head_frame-B25.stl'
FRONT_PRINT = '28_skull_front_with_camera_tray-B25.stl'
V = App.Vector
PIN_X, PIVOT_Z = 60.5, 112.
COLLAR_OUTER, COLLAR_INNER = 6.8, 6.16
COLLAR_X = (58.10, 62.90)
COLLAR_Z = ((105.50, 106.30), (117.70, 118.50))
PIN_RADIUS = 1.55
FRAME_PRINT_OFFSET = (.75, 127.725, 16.8509941)
FRAME_VARIANT_OFFSET = (1.195, 133.05, 36.5)
FRONT_PRINT_OFFSET = (1.31108093, -126.50938225, -30.78463747)
RELIEF_X = (57.65, 63.35)
RELIEF_Z = (105.18, 106.62)
RELIEF_RADIUS = 7.13


def cylinder_between_x(radius, ends):
    return Part.makeCylinder(radius, ends[1]-ends[0], V(ends[0], 0, PIVOT_Z), V(1, 0, 0))


def collar_stock():
    inner = cylinder_between_x(COLLAR_INNER, (COLLAR_X[0]-.1, COLLAR_X[1]+.1))
    pin = Part.makeCylinder(PIN_RADIUS, 18., V(PIN_X, 0, 103.))
    annulus = cylinder_between_x(COLLAR_OUTER, COLLAR_X).cut(inner).cut(pin)
    return Part.Compound([
        annulus.common(Part.makeBox(6., 10., upper-lower, V(57.5, -10., lower)))
        for lower, upper in COLLAR_Z
    ])


def shell_relief():
    lower, upper = RELIEF_Z
    clip = Part.makeBox(6., 4.27, upper-lower, V(57.5, -4.27, lower))
    front = cylinder_between_x(RELIEF_RADIUS, RELIEF_X).common(clip)
    # The front shell moves from front to back onto the frame.
    back = Part.makeBox(RELIEF_X[1]-RELIEF_X[0], 24.05, upper-lower, V(RELIEF_X[0], -.05, lower))
    return front.fuse(back).removeSplitter()


def mesh_stock(shape, angle=0., offset=(0., 0., 0.)):
    # Tessellate analytic stock in the exact mounting frame used by each build mesh.
    part = shape.copy()
    part.rotate(V(), V(1, 0, 0), angle)
    part.translate(V(*offset))
    points, facets = MeshPart.meshFromShape(Shape=part, LinearDeflection=.003,
                                           AngularDeflection=.045, Relative=False).Topology
    return solid(trimesh.Trimesh(np.array([tuple(v) for v in points]), facets))


def has_degenerate_faces(mesh):
    left, right, top = mesh.triangles.transpose(1, 0, 2)
    return np.any(np.all(np.cross(right-left, top-left) == 0., axis=1))


def checked_boolean(raw, edit, add, tolerance=0.):
    source = solid(raw)
    if source.is_empty():
        raise ValueError('Source mesh is not a closed solid')
    if tolerance:
        source, edit = source.set_tolerance(tolerance), edit.set_tolerance(tolerance)
    edited = source + edit if add else source - edit
    if tolerance:
        edited = edited.simplify(tolerance)
    result = mesh_from_solid(edited)
    if (not result.is_volume or result.body_count != 1 or
            has_degenerate_faces(result) or
            not np.allclose(raw.bounds, result.bounds, atol=.00002, rtol=0.)):
        raise ValueError('Local pitch reinforcement changed mesh validity or bounds')
    return result


def right_ligament(shape, z):
    ray = Part.makeLine(V(PIN_X, 0., z), V(PIN_X, -9., z))
    return shape.common(ray).Length


def apply(doc):
    frame = doc.getObject('Part019')
    original = world_shape(frame)
    stock = collar_stock()
    changed = original.fuse(stock.Solids, .0001)
    if not changed.isValid() or len(changed.Solids) != 1:
        raise ValueError('The reinforced head frame must remain a valid single solid')
    witness_z = (106., 106.3001, 117.6999, 118.)
    measured = [right_ligament(changed, z) for z in witness_z]
    if min(measured) < 1.2:
        raise ValueError(f'Right pitch pin ligament remains below 1.20 mm: {measured}')
    shell = doc.getObject('Part073')
    points, facets = world_mesh(shell).Topology
    original_shell = trimesh.Trimesh([tuple(p) for p in points], facets)
    revised_shell = checked_boolean(original_shell, mesh_stock(shell_relief()), False)
    replace(frame, changed)
    replace_native_mesh(shell, revised_shell)
    return {
        'original_pin_end_ligament_mm': [right_ligament(original, z) for z in (106., 118.)],
        'reinforced_pin_end_and_band_boundary_ligament_mm': dict(zip(map(str, witness_z), measured, strict=True)),
        'reinforcement_volume_mm3': changed.Volume-original.Volume,
        'internal_shell_relief_volume_mm3': original_shell.volume-revised_shell.volume,
    }



def print_precision(mesh):
    """Resolve micron-scale CSG slivers before Studio stores coordinates as float32."""
    vertices, faces = mesh.vertices.copy(), mesh.faces
    lower, upper = mesh.bounds
    center = (lower+upper)/2
    shift = np.array((0., 0., center[2]-lower[2]), dtype=np.float32)
    scale = np.array((1e5, 1e5, 1.), dtype=np.float32)

    def normals(points):
        return np.cross(points[..., 1, :]-points[..., 0, :], points[..., 2, :]-points[..., 0, :])

    def collapsed(points):
        direct = points.astype(np.float32)
        centered = (points-center).astype(np.float32)
        slicer = (direct-center.astype(np.float32))*scale + shift
        forms = (points, direct.astype(float), centered.astype(float), slicer.astype(float))
        return np.stack([np.all(normals(form) == 0., axis=-1) for form in forms])

    offsets = np.array(list(product((0., -.5, .5, -1., 1., -2., 2., -4., 4., -8., 8.), repeat=3))) * 1e-6
    offsets = offsets[np.argsort(np.linalg.norm(offsets, axis=1), kind='stable')]
    for _ in range(4):
        rejected = collapsed(vertices[faces]).any(axis=0)
        if not rejected.any():
            break
        for index in np.unique(faces[rejected]):
            nearby = faces[(faces == index).any(axis=1)]
            triangles = vertices[nearby]
            before = collapsed(triangles).sum()
            if not before:
                continue
            position = vertices[index]
            proposals = position + offsets
            keep = ((proposals >= lower) & (proposals <= upper)).all(axis=1)
            boundaries = (position == lower) | (position == upper)
            keep &= (proposals[:, boundaries] == position[boundaries]).all(axis=1)
            proposals = proposals[keep]
            edited = np.broadcast_to(triangles, (len(proposals), *triangles.shape)).copy()
            edited[:, nearby == index] = proposals[:, None]
            original = normals(triangles)
            substantive = np.linalg.norm(original, axis=1) > 1e-6
            orientation = np.einsum('nij,ij->ni', normals(edited), original)
            scores = before - collapsed(edited).sum(axis=(0, 2))
            scores[(orientation[:, substantive] <= 0.).any(axis=1)] = -1
            best = int(scores.argmax())
            if scores[best] > 0:
                vertices[index] = proposals[best]
    result = trimesh.Trimesh(vertices, faces, process=False)
    if collapsed(vertices[faces]).any() or not result.is_volume or result.body_count != 1:
        raise ValueError('Studio precision introduces collapsed facets')
    if np.linalg.norm(vertices-mesh.vertices, axis=1).max() > .00002:
        raise ValueError('Studio precision repair moved a vertex by over 0.02 µm')
    return result

def frame_print_mesh(raw, *, variant=False):
    offset = FRAME_VARIANT_OFFSET if variant else FRAME_PRINT_OFFSET
    tolerance = .001 if variant else .0003
    result = checked_boolean(raw, mesh_stock(collar_stock(), 90., offset), True, tolerance)
    return result if variant else print_precision(result)


def front_print_mesh(raw):
    result = checked_boolean(raw, mesh_stock(shell_relief(), -90., FRONT_PRINT_OFFSET), False)
    return print_precision(result)


def update_project(project, output, repaired_front):
    with ZipFile(project) as before, ZipFile(output, 'w') as after:
        frame, frame_ref = archived_mesh(before, FRAME_PRINT, 6)
        front, front_ref = archived_mesh(before, FRONT_PRINT, 4)
        if repaired_front:
            data = np.load(repaired_front)
            front = trimesh.Trimesh(data['v'], data['f'], process=False)
        replacements = {
            frame_ref['object_path']: frame_print_mesh(frame),
            front_ref['object_path']: front_print_mesh(front),
        }
        for name in before.namelist():
            contents = before.read(name)
            if name in replacements:
                contents = replace_mesh(contents, replacements[name], indexed=True)
            write_entry(after, name, contents)


def update_variants(source, output, final_project):
    with ZipFile(final_project) as project:
        _, frame_ref = archived_mesh(project, FRAME_PRINT, 6)
    with ZipFile(source) as before, ZipFile(output, 'w') as after:
        report = json.loads(before.read('shaft-fit.json'))
        report['parts']['09']['production_frame_mesh_sha256'] = frame_ref['source_mesh_sha256']
        report['source_project_sha256'] = sha256(final_project.read_bytes()).hexdigest()
        report['parts']['09']['pin_cheek_reinforcement_outer_radius_mm'] = COLLAR_OUTER
        report['parts']['09']['pin_cheek_minimum_design_ligament_mm'] = 1.2
        for name in before.namelist():
            if name == 'shaft-fit.json':
                continue
            contents = before.read(name)
            if name.startswith('P8/'):
                raw = trimesh.load_mesh(BytesIO(contents), file_type='stl')
                mesh = frame_print_mesh(raw, variant=True)
                contents = mesh.export(file_type='stl')
                exported = trimesh.load_mesh(BytesIO(contents), file_type='stl')
                if not exported.is_volume or exported.body_count != 1 or has_degenerate_faces(exported):
                    raise ValueError(f'{name} is invalid after STL export')
                row, = (row for row in report['parts']['09']['variants'] if row['file'] == name)
                row['sha256'] = sha256(contents).hexdigest()
            write_entry(after, name, contents)
        data = json.dumps(report, indent=2)+'\n'
        write_entry(after, 'shaft-fit.json', data)
        output.with_name('shaft-fit.json').write_text(data)


def build(cad, project, fit_zip, output, repaired_front=None):
    output.mkdir(parents=True, exist_ok=True)
    if any(p.resolve().parent == output.resolve() for p in (cad, project, fit_zip)):
        raise ValueError('Choose a separate output directory')
    doc = App.openDocument(str(cad.resolve()))
    try:
        report = apply(doc)
        doc.recompute()
        doc.saveAs(str((output/cad.name).resolve()))
    finally:
        App.closeDocument(doc.Name)
    (output/'pitch-pin-ligament.json').write_text(json.dumps(report, indent=2)+'\n')
    update_project(project, output/project.name, repaired_front)
    update_variants(fit_zip, output/fit_zip.name, output/project.name)
    print(json.dumps(report))


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for name in ('cad', 'project', 'fit_zip', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--repaired-front', type=Path)
    build(**vars(parser.parse_args()))
