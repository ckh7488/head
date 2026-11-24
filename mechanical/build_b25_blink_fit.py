"""Restore B24's skull wall and clear the outboard left eyelid pin stop."""

from contextlib import contextmanager
from hashlib import file_digest
from itertools import product
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import FreeCAD as App
import Mesh
import manifold3d as md
import numpy as np
import trimesh

from build_b21_links import LOWER, SOURCE as LID_PILOT_SOURCE, change_mesh, edits, from_mesh
from build_b22_fused_skull import solid
from build_b24 import BASE as STOCK_SHELL_SOURCE, TRAY_PRINT, write_front_skull
from export_cad import world_mesh


LID_PRINT = '32_left_eyelid-B25.stl'
SKULL_PRINT = '28_skull_front_with_camera_tray-B25.npz'
LID_REPLACE = '32_left_eyelid-B21.stl'
SKULL_REPLACE = '28_skull_front_with_camera_tray-B24.stl'
RELIEF_LOW = (-55.10, -35., 106.)
RELIEF_HIGH = (-54.20, -27., 111.50)
RETAINED_PIN_CAP_RADIUS_MM = 1.35
MAX_RADIAL_CENTER_DEVIATION_MM = .025
LOCATING_BAND_WIDTH_MM = 1.20
LOCATING_BAND_DIAMETRAL_CLEARANCE_MM = .030
BEARING_END_FLOAT_MM = .10
FRONT_PRECISION_LIMIT_MM = .00002


@contextmanager
def source_document(path):
    doc = App.openDocument(str(path))
    try:
        yield doc
    finally:
        App.closeDocument(doc.Name)


def shape_to_mesh(solid_shape):
    native = solid_shape.to_mesh64()
    return trimesh.Trimesh(vertices=native.vert_properties[:, :3], faces=native.tri_verts, process=False)


def triangle_normals(triangles):
    return np.cross(triangles[..., 1, :] - triangles[..., 0, :],
                    triangles[..., 2, :] - triangles[..., 0, :])


def front_slicer_normals(triangles, center, height):
    """Model Bambu's float32 import and the centered, unrotated plate-4 slice."""
    single = triangles.astype(np.float32)
    scale = np.array([1e5, 1e5, 1.], dtype=np.float32)
    shift = np.array([0., 0., height], dtype=np.float32)
    plane = (single - center) * scale + shift
    normal_scale = np.array([1e5, 1e5, 1e10])
    return np.stack((triangle_normals(single), triangle_normals(plane) / normal_scale))


def front_print_precision(vertices, faces):
    """Separate rounded seam vertices without removing faces or changing topology."""
    points = vertices.copy()
    single = vertices.astype(np.float32)
    minimum, maximum = single.min(axis=0), single.max(axis=0)
    center = ((minimum.astype(float) + maximum) / 2).astype(np.float32)
    height = float(center[2] - minimum[2])
    reference = triangle_normals(vertices[faces])
    original = front_slicer_normals(vertices[faces], center, height)
    originally_reversed = np.sum(original * reference, axis=-1) < 0.
    distances = np.array((0., .25, -.25, .5, -.5, 1., -1., 2., -2., 4., -4., 8., -8.)) * 1e-6
    offsets = np.array(list(product(distances, repeat=3)))
    steps = np.linalg.norm(offsets, axis=1)
    offsets = offsets[np.argsort(steps, kind='stable')]

    while True:
        bad = np.all(front_slicer_normals(points[faces], center, height) == 0., axis=-1)
        if not bad.any():
            break
        best = None
        for vertex in np.unique(faces[bad.any(axis=0)]):
            indices = np.flatnonzero((faces == vertex).any(axis=1))
            nearby_faces = faces[indices]
            candidates = vertices[vertex] + offsets
            triangles = np.broadcast_to(points[nearby_faces], (len(candidates), *nearby_faces.shape, 3)).copy()
            triangles[:, nearby_faces == vertex] = candidates[:, None]
            facing = np.sum(triangle_normals(triangles) * reference[indices], axis=-1)
            rounded = front_slicer_normals(triangles, center, height)
            flips = (np.sum(rounded * reference[indices], axis=-1) < 0.) & ~originally_reversed[:, None, indices]
            benefit = bad[:, indices].sum() - np.all(rounded == 0., axis=-1).sum(axis=(0, 2))
            benefit[(facing <= 0.).any(axis=1) | flips.any(axis=(0, 2))] = 0
            choice = int(benefit.argmax())
            if benefit[choice] > 0 and (best is None or benefit[choice] > best[0]):
                best = benefit[choice], vertex, candidates[choice]
        if best is None:
            raise ValueError('The front print seam cannot be resolved within the precision limit')
        _, vertex, point = best
        points[vertex] = point

    source = trimesh.Trimesh(vertices, faces, process=False)
    repaired = trimesh.Trimesh(points, faces, process=False)
    if (not repaired.is_volume or repaired.body_count != 1
            or not np.array_equal(repaired.bounds, source.bounds)
            or np.linalg.norm(points-vertices, axis=1).max() > FRONT_PRECISION_LIMIT_MM
            or abs(repaired.volume-source.volume) > .001):
        raise ValueError('The front print seam adjustment exceeded its geometry limits')
    return points, faces


def relieve_lid(stock):
    block = md.Manifold.cube(np.subtract(RELIEF_HIGH, RELIEF_LOW)).translate(RELIEF_LOW)
    # The ground pin's Ø2.09 seat starts inboard of the entire cut. Preserve
    # a continuous cap outside the Ø1.55 pin access hole as well.
    keep = (md.Manifold.cylinder(4., RETAINED_PIN_CAP_RADIUS_MM, circular_segments=96)
            .rotate((0., 90., 0.)).translate((-56., *LOWER[1:])))
    before = solid(stock)
    after = before - (block - keep)
    result = shape_to_mesh(after)
    if (after.status() != md.Error.NoError or not result.is_volume or result.body_count != 1
            or not np.allclose(stock.bounds, result.bounds, atol=1e-5, rtol=0.)
            or before.volume() <= after.volume()):
        raise ValueError('The left lid relief must leave one closed body with the original print bounds')
    return result


def install_world_mesh(obj, replacement):
    native = Mesh.Mesh(replacement.triangles.tolist())
    native.transform(obj.getGlobalPlacement().inverse().toMatrix())
    obj.Mesh = native


def apply(doc, print_dir):
    print_dir = Path(print_dir)
    print_dir.mkdir(parents=True, exist_ok=True)

    with source_document(STOCK_SHELL_SOURCE) as stock_doc:
        old_shell = from_mesh(world_mesh(stock_doc.Part073))
    shell = doc.Part073
    shell_before = from_mesh(world_mesh(shell))
    if not np.allclose(old_shell.bounds, shell_before.bounds, atol=1e-5, rtol=0.):
        raise ValueError('The intact source shell has a different outer envelope')
    install_world_mesh(shell, old_shell)

    lid = doc.Part078
    before = from_mesh(world_mesh(lid))
    after = relieve_lid(before)
    install_world_mesh(lid, after)
    with source_document(LID_PILOT_SOURCE) as original:
        pilot_adds, pilot_cuts = edits(False)
        rebuilt_pilot = change_mesh(from_mesh(world_mesh(original.Part078)),
                                    pilot_adds[lid.Name], pilot_cuts[lid.Name])
    printable = relieve_lid(rebuilt_pilot)
    printable.apply_translation(-printable.bounds.mean(axis=0)*[1, 1, 0]
                                -[0, 0, printable.bounds[0, 2]])
    printable.export(print_dir/LID_PRINT)

    with TemporaryDirectory() as directory:
        shell_path = Path(directory)/'shell.stl'
        tray_path = Path(directory)/'tray.stl'
        world_mesh(shell).write(str(shell_path))
        world_mesh(doc.Part065).write(str(tray_path))
        write_front_skull(shell_path, tray_path, print_dir/SKULL_PRINT)

    geometry = json.loads(doc.R5.MotionGeometry)
    original_relief = geometry.pop('blink_shell_relief')
    with Path(STOCK_SHELL_SOURCE).open('rb') as source:
        source_hash = file_digest(source, 'sha256').hexdigest()
    report = {
        'shell': {'part': shell.Name, 'source_cad_sha256': source_hash,
                  'reinstated_mm3': old_shell.volume-shell_before.volume,
                  'restored_bounds_mm': original_relief['regions'][0]['world_bounds_mm']},
        'left_lid': {'part': lid.Name, 'relief_bounds_mm': [RELIEF_LOW, RELIEF_HIGH],
                     'removed_mm3': before.volume-after.volume,
                     'retained_pin_cap_radius_mm': RETAINED_PIN_CAP_RADIUS_MM,
                     'bearing_bore_and_axial_pin_stop_unchanged': True},
        'maximum_radial_bearing_center_deviation_mm': MAX_RADIAL_CENTER_DEVIATION_MM,
        'bearing_fit': {'finished_relieved_pocket_diameter_mm': 10.24,
                        'retained_outboard_shoulder_diameter_mm': 9.36,
                        'centred_locating_band_width_mm': LOCATING_BAND_WIDTH_MM,
                        'nominal_band_ID_minus_measured_bearing_OD_mm': LOCATING_BAND_DIAMETRAL_CLEARANCE_MM,
                        'inboard_axial_end_float_per_bearing_mm': BEARING_END_FLOAT_MM},
        'prints': {SKULL_REPLACE: SKULL_PRINT, LID_REPLACE: LID_PRINT},
    }
    geometry['blink_fit'] = report
    doc.R5.MotionGeometry = json.dumps(geometry, ensure_ascii=False)
    return report


def print_replacements(directory):
    directory = Path(directory)
    with np.load(directory/SKULL_PRINT) as data:
        skull = trimesh.Trimesh(vertices=data['vertices'], faces=data['faces'], process=False)
    lid = trimesh.load_mesh(directory/LID_PRINT)
    return {SKULL_REPLACE: (Path(SKULL_PRINT).with_suffix('.stl').name, skull),
            LID_REPLACE: (LID_PRINT, lid)}
