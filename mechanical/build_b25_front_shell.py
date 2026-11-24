"""Rebuild B25 part 28 as the installed, printable front skull and camera tray.

Pass the pre-audit assembly (b19aada) and a B25 print project with the original
part 28 placement. Run under FreeCAD's Python with libigl's CGAL bindings.
The build emits the revised assembly and the replacement 3MF model member.
"""

from argparse import ArgumentParser
from hashlib import file_digest, sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import FreeCAD as App
import Mesh
from igl.copyleft import cgal
from lxml import etree
import numpy as np
from scipy.spatial import cKDTree
import trimesh

from build_b20_print import CORE, MODEL, MODEL_SETTINGS, PRODUCTION, serialize
from build_b22_fused_skull import solid
from build_b25_blink_fit import front_slicer_normals
from build_b25_jaw_retention import mesh_from_solid
from physics.export_cad import world_mesh


SHELL = 'Part073'
TRAY = 'Part065'
PRINT_NAME = '28_skull_front_with_camera_tray-B25'
ROTATION = np.array(((1., 0., 0.), (0., 0., 1.), (0., -1., 0.)))
CHEEK_SEAM = (75.15873718261719, 21.150001525878906, 99.30000305175781)
TRAY_JOIN_OFFSET_MM = .002
PROPERTY_UPDATES = {
    SHELL: ('EstimatedGrams', 'Label'),
    TRAY: ('EstimatedGrams', 'Label', 'Visibility', 'Printed'),
    'HubPCB': ('Label',),
    'HubBodyF1': ('Label',),
    'A4J2LeverKeeper': ('Label',),
}


def digest(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def native_geometry(obj):
    points, faces = world_mesh(obj).Topology
    return trimesh.Trimesh([tuple(point) for point in points], faces)


def valid(mesh):
    return (mesh.is_volume and mesh.body_count == 1 and mesh.area_faces.min() > 0.
            and len(mesh.vertices) == len(np.unique(mesh.vertices, axis=0)))


def canonical_faces(faces):
    rows = np.arange(len(faces))[:, None]
    first = faces.argmin(axis=1)[:, None]
    oriented = faces[rows, (first + np.arange(3)) % 3]
    return oriented[np.lexsort(oriented[:, ::-1].T)]


def geometry_signature(vertices, faces):
    # CGAL can emit equivalent triangles in a different sequence or with a
    # different starting corner. Hash the exact coordinates and oriented mesh.
    ordered = np.lexsort(vertices[:, ::-1].T)
    remap = np.argsort(ordered)
    stream = sha256(vertices[ordered].astype('<f8').tobytes())
    stream.update(canonical_faces(remap[faces]).astype('<i8').tobytes())
    return stream.hexdigest()


def verify_native(path, mesh):
    with_native = App.openDocument(str(path.resolve()))
    try:
        points, indices = world_mesh(with_native.getObject(SHELL)).Topology
        vertices = np.array([tuple(point) for point in points])
        signature = geometry_signature(vertices, np.asarray(indices))
        if signature != geometry_signature(mesh.vertices, mesh.faces):
            raise ValueError('FreeCAD did not preserve the exact oriented front shell geometry')
        return signature
    finally:
        App.closeDocument(with_native.Name)


def intersecting_pairs(vertices, faces):
    _, _, pairs, _, _ = cgal.remesh_self_intersections(
        np.asarray(vertices), np.asarray(faces, dtype=np.int64), detect_only=True)
    return len(pairs)


def normals(triangles):
    return np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])


def collapse_near_edges(vertices, faces, limit):
    """Contract only short manifold edges and keep the outer envelope."""
    vertices, faces = vertices.copy(), faces.copy()
    incident = [set() for _ in vertices]
    neighbors = [set() for _ in vertices]
    for index, (a, b, c) in enumerate(faces):
        incident[a].add(index)
        incident[b].add(index)
        incident[c].add(index)
        neighbors[a].update((b, c))
        neighbors[b].update((a, c))
        neighbors[c].update((a, b))
    live = np.ones(len(faces), dtype=bool)
    pairs = cKDTree(vertices).query_pairs(limit, output_type='ndarray')
    order = np.argsort(np.linalg.norm(vertices[pairs[:, 0]] - vertices[pairs[:, 1]], axis=1))
    parent = np.arange(len(vertices))
    extrema = set(np.r_[vertices.argmin(0), vertices.argmax(0)])

    def representative(index):
        while parent[index] != index:
            index = parent[index]
        return index

    for _ in range(2):
        for i, j in pairs[order]:
            a, b = representative(i), representative(j)
            if a == b:
                continue
            if b in extrema:
                a, b = b, a
            shared = incident[a] & incident[b]
            # The end vertices of a manifold link have two shared neighbors.
            if len(shared) != 2 or len(neighbors[a] & neighbors[b]) != 2 or b in extrema:
                continue
            before_a = vertices[a].copy()
            vertices[a] = before_a if a in extrema else (before_a + vertices[b]) / 2
            other = sorted((incident[a] | incident[b]) - shared)
            old = vertices[faces[other]].copy()
            old[faces[other] == a] = before_a
            new = old.copy()
            new[(faces[other] == a) | (faces[other] == b)] = vertices[a]
            if (np.einsum('ij,ij->i', normals(old), normals(new)) < 0.).any():
                vertices[a] = before_a
                continue
            parent[b] = a
            for index in shared:
                for vertex in faces[index]:
                    incident[vertex].discard(index)
                live[index] = False
            for index in incident[b]:
                faces[index, faces[index] == b] = a
                incident[a].add(index)
            incident[b].clear()
            for vertex in neighbors[a] | neighbors[b]:
                neighbors[vertex].discard(b)
                neighbors[vertex].discard(a)
                if incident[vertex] & incident[a]:
                    neighbors[vertex].add(a)
            neighbors[a] = set(np.unique(faces[list(incident[a])])) - {a}
            neighbors[b].clear()

    mesh = trimesh.Trimesh(vertices, faces[live], process=False)
    mesh.remove_unreferenced_vertices()
    return mesh


def repair_shell(shell):
    # Collapse the 1.91 µm edge shared by the two crossing cheek seam faces.
    pair = np.flatnonzero(np.linalg.norm(shell.vertices - CHEEK_SEAM, axis=1) < .000004)
    if len(pair) != 2:
        raise ValueError('The source no longer has the two expected cheek seam vertices')
    faces = shell.faces.copy()
    faces[faces == pair[1]] = pair[0]
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2])
                  & (faces[:, 2] != faces[:, 0])]
    repaired = trimesh.Trimesh(shell.vertices, faces, process=False)
    repaired.remove_unreferenced_vertices()
    if not valid(repaired) or intersecting_pairs(repaired.vertices, repaired.faces):
        raise ValueError('The cheek seam repair must leave a single closed surface')
    return repaired


def prepare_tray(tray):
    prepared = tray.copy()
    # Match both production Ø4.15 pilots. The Ø3.30 entry and outer seats stay intact.
    for x in (-12., 12.):
        center = np.array((x, -47.))
        radial = prepared.vertices[:, :2] - center
        radii = np.linalg.norm(radial, axis=1)
        z = prepared.vertices[:, 2]
        ring = (abs(radii - 2.) < .002) & (66.299 <= z) & (z <= 70.751)
        if not ring.any():
            raise ValueError(f'Cannot locate the camera pilot at X={x}')
        prepared.vertices[ring, :2] = center + radial[ring] * (2.075 / radii[ring])[:, None]
    # Keep the nearly coplanar junction out of the embedded shell surfaces.
    prepared.apply_translation((0., 0., -TRAY_JOIN_OFFSET_MM))
    return prepared


def fuse_shell(shell, tray):
    repaired = repair_shell(shell)
    prepared = prepare_tray(tray)
    fused = mesh_from_solid((solid(repaired.copy()) + solid(prepared.copy())).simplify(.001))
    if not fused.is_volume or fused.body_count != 1:
        raise ValueError('The skull and mounting tray must fuse into one solid')
    fused = fused.split(only_watertight=False, repair=False)[0]
    fused = collapse_near_edges(fused.vertices, fused.faces, .0001)

    # Exact intersection resolution introduces small edge splits. Weld those
    # splits and test the quantized coordinates that FreeCAD will store.
    for _ in range(6):
        vertices, faces, _ = cgal.mesh_boolean(
            np.asarray(fused.vertices), np.asarray(fused.faces, dtype=np.int64),
            np.empty((0, 3)), np.empty((0, 3), dtype=np.int64), 'union')
        fused = collapse_near_edges(vertices, faces, .00005)
        if fused.body_count != 1:
            raise ValueError('Intersection cleanup split the front shell')
        fused = fused.split(only_watertight=False, repair=False)[0]
        fused.vertices = fused.vertices.astype('float32').astype(float)
        if not valid(fused):
            raise ValueError('The CAD precision conversion damaged the fused shell')
        if not intersecting_pairs(fused.vertices, fused.faces):
            break
    else:
        raise ValueError('The fused shell still intersects itself at CAD precision')
    if not np.array_equal(shell.bounds, fused.bounds):
        raise ValueError('The front skull outer envelope changed')
    return fused


def print_member(project, mesh):
    with ZipFile(project) as archive:
        settings = etree.fromstring(archive.read(MODEL_SETTINGS))
        resources = etree.fromstring(archive.read(MODEL))
        obj, = settings.xpath('object[metadata[@key="name"][@value=$name]]', name=PRINT_NAME)
        part, = obj.findall('part')
        if part.get('subtype') != 'normal_part':
            raise ValueError('Expected one printed front skull resource')
        name = obj.get('id')
        component, = resources.findall(f".//{CORE}object[@id='{name}']//{CORE}component")
        member = component.get(PRODUCTION + 'path').lstrip('/')
        model = etree.fromstring(archive.read(member))
        original_data = archive.read(member)
    body = model.find(f".//{CORE}object[@id='{component.get('objectid')}']/{CORE}mesh")
    old_vertices, old_faces = (body.find(CORE + key) for key in ('vertices', 'triangles'))
    baseline = np.array([[float(v.get(axis)) for axis in 'xyz'] for v in old_vertices])
    baseline_faces = np.array([[int(f.get(f'v{i}')) for i in range(1, 4)] for f in old_faces])
    points = mesh.vertices @ ROTATION.T
    points += baseline.min(0) - points.min(0)
    if not np.allclose(np.ptp(points, axis=0), np.ptp(baseline, axis=0), atol=1e-8, rtol=0.):
        raise ValueError('The corrected shell has a different print envelope')
    encoded = np.array([[float(f'{coord:.14g}') for coord in point] for point in points])
    single = encoded.astype('float32')
    low, high = single.min(axis=0), single.max(axis=0)
    center = ((low.astype(float) + high) / 2).astype('float32')
    normals_by_precision = front_slicer_normals(encoded[mesh.faces], center, float(center[2] - low[2]))
    if np.any(np.all(normals_by_precision == 0., axis=-1)):
        raise ValueError('The print or centered-slice coordinates contain a collapsed triangle')
    for vertices in (encoded, single.astype(float)):
        printable = trimesh.Trimesh(vertices, mesh.faces, process=False)
        if not valid(printable) or intersecting_pairs(vertices, mesh.faces):
            raise ValueError('The 3MF or slicer-precision mesh has a topological defect')
    baseline_volume = trimesh.Trimesh(baseline, baseline_faces, process=False).volume
    if abs(mesh.volume - baseline_volume) > 1.:
        raise ValueError('The front skull cleanup changed more than 1 mm³ of material')
    old_vertices.clear()
    old_faces.clear()
    for x, y, z in points:
        etree.SubElement(old_vertices, CORE + 'vertex', x=f'{x:.14g}', y=f'{y:.14g}', z=f'{z:.14g}')
    for a, b, c in mesh.faces:
        etree.SubElement(old_faces, CORE + 'triangle', v1=str(a), v2=str(b), v3=str(c))
    return member, serialize(model), original_data, baseline_volume


def model_property(xml, actor, key):
    return xml.find(f"ObjectData/Object[@name='{actor}']/Properties/Property[@name='{key}']")


def write_native(source, regenerated, destination):
    # Retain original shape streams and metadata for all independent components.
    with ZipFile(source) as stock, ZipFile(regenerated) as fresh, ZipFile(destination, 'w') as output:
        old = etree.fromstring(stock.read('Document.xml'))
        new = etree.fromstring(fresh.read('Document.xml'))
        old_mesh = model_property(old, SHELL, 'Mesh')[0].get('file')
        new_mesh = model_property(new, SHELL, 'Mesh')[0].get('file')
        for actor, keys in PROPERTY_UPDATES.items():
            for key in keys:
                model_property(old, actor, key)[0].attrib.update(model_property(new, actor, key)[0].attrib)
        replacements = {'Document.xml': etree.tostring(old, xml_declaration=True, encoding='UTF-8'),
                        old_mesh: fresh.read(new_mesh)}
        for item in stock.infolist():
            data = replacements[item.filename] if item.filename in replacements else stock.read(item)
            output.writestr(item, data)


def build(source, print_project, directory):
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / 'R5-B25-Assembly.FCStd'
    if destination.resolve() == source.resolve():
        raise ValueError('Choose a separate output directory')
    doc = App.openDocument(str(source.resolve()))
    try:
        shell, tray = doc.getObject(SHELL), doc.getObject(TRAY)
        if not shell.getGlobalPlacement().isIdentity() or not tray.getGlobalPlacement().isIdentity():
            raise ValueError('Expected the assembly front skull and tray in the world frame')
        mesh = fuse_shell(native_geometry(shell), native_geometry(tray))
        member, data, original, old_volume = print_member(print_project, mesh)
        shell.Mesh = Mesh.Mesh(mesh.triangles.tolist())
        shell.Label = '28 front skull with integrated camera tray'
        shell.EstimatedGrams += tray.EstimatedGrams
        tray.Label = '25 nasal tray reference · integrated into 28'
        tray.Visibility = False
        tray.Printed = False
        tray.EstimatedGrams = 0.
        doc.HubPCB.Label = 'A5 PCB · 1.6 mm mechanical envelope'
        doc.HubBodyF1.Label = 'F1 · 7.5 A MINI'
        doc.A4J2LeverKeeper.Label = 'A5 J2 · plug keeper · KiCad H2 and H4'
        doc.recompute()
        with TemporaryDirectory(dir=directory) as temp:
            native = Path(temp) / destination.name
            doc.saveAs(str(native))
            write_native(source, native, destination)
    finally:
        App.closeDocument(doc.Name)

    # The 3MF project retains its existing pose. Replace this member and
    # update the matching object and part face counts in model_settings.config.
    signature = verify_native(destination, mesh)
    (directory / Path(member).name).write_bytes(data)
    report = {
        'source_cad_sha256': digest(source),
        'cad_sha256': digest(destination),
        'reference_project_sha256': digest(print_project),
        'print_member': member,
        'previous_mesh_sha256': sha256(original).hexdigest(),
        'print_mesh_sha256': sha256(data).hexdigest(),
        'geometry_signature_sha256': signature,
        'wall_geometry': {
            'cad_id': SHELL, 'hidden_datum_id': TRAY,
            'vertices': len(mesh.vertices), 'triangles': len(mesh.faces), 'closed_bodies': 1,
            'exact_self_intersection_pairs': 0, 'duplicate_vertices': 0, 'zero_area_triangles': 0,
            'camera_pilot_diameter_mm': 4.15, 'tray_join_offset_mm': TRAY_JOIN_OFFSET_MM,
            'bounds_mm': mesh.bounds.tolist(),
            'old_volume_mm3': old_volume, 'new_volume_mm3': mesh.volume,
            'print_geometry_rotation_world_to_component': ROTATION.tolist(),
        },
    }
    (directory / 'front-shell-sync.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for arg in ('source', 'print_project', 'directory'):
        parser.add_argument(arg, type=Path)
    build(**vars(parser.parse_args()))
