"""Apply the B25 eye-yaw drive slot to the assembly and its P2S plate."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path
from zipfile import ZipFile

import FreeCAD as App
import manifold3d as md
import Mesh  # Register Mesh::Feature before opening the assembly.
import numpy as np
import Part

from build_b19_review_fixes import replace, world_shape
from build_b21_print import build as pack, plate_signatures
from build_b22_fused_skull import solid
from build_b25_bearing_fit import archived_mesh
from build_b25_jaw_retention import mesh_from_solid

PART = "Part037"
PRINT = "15_eye_yaw_offset_tie_bar-B21.stl"
PLATE = 8
X, Y = -5.8, -22.
Z_MIN, Z_MAX = 114.55, 117.45
STOP_Z = 117.05
WIDTH, TRAVEL, BOSS = 2.09, .6, 7.2
PRINT_ALLOWANCE = .15
SEGMENTS = 180


def digest(path):
    with path.open("rb") as source:
        return file_digest(source, "sha256").hexdigest()


def native_cylinder(x, y, z, radius, height):
    return Part.makeCylinder(radius, height, App.Vector(x, y, z))


def native_cut(shape):
    margin = .1
    boss = native_cylinder(X, Y, Z_MIN, BOSS/2, Z_MAX-Z_MIN).cut(
        native_cylinder(X, Y, Z_MIN-margin, WIDTH/2+.01, Z_MAX-Z_MIN+2*margin)
    )
    r, half = WIDTH/2, TRAVEL/2
    z, height = Z_MIN-margin, STOP_Z-Z_MIN+margin
    slot = native_cylinder(X, Y-half, z, r, height).fuse([
        Part.makeBox(WIDTH, TRAVEL, height, App.Vector(X-r, Y-half, z)),
        native_cylinder(X, Y+half, z, r, height),
    ])
    result = shape.fuse(boss).cut(slot).removeSplitter()
    if not result.isValid() or len(result.Solids) != 1:
        raise ValueError("Part 15 must remain one valid solid")

    # Limit the entire edit to the drive boss, outside the two eye stations.
    zone = native_cylinder(X, Y, Z_MIN-margin, BOSS/2+.001, Z_MAX-Z_MIN+2*margin)
    added, removed = result.cut(shape), shape.cut(result)
    if added.Volume < 1. or removed.Volume < 1.:
        raise ValueError("The boss and slot must each change material")
    if added.cut(zone).Volume > 1e-6 or removed.cut(zone).Volume > 1e-6:
        raise ValueError("Material changed outside the drive station")
    relief = native_cylinder(X, Y, STOP_Z+.02, .77, Z_MAX-STOP_Z-.04)
    if relief.common(result).Volume > 1e-6:
        raise ValueError("The pilot above the drive pin is blocked")
    return result


def printable(raw):
    # The archive uses the centered print frame, with the same XY orientation.
    offset = raw.bounds.mean(axis=0) - np.array((0., -23.75, 116.))
    x, y = np.array((X, Y)) + offset[:2]
    roof = STOP_Z + offset[2]
    full_height = np.ptp(raw.bounds[:, 2])
    floor = raw.bounds[0, 2]
    r, half = (WIDTH+PRINT_ALLOWANCE)/2, TRAVEL/2

    def cylinder(cx, cy, z, radius, height):
        return md.Manifold.cylinder(height, radius, circular_segments=SEGMENTS).translate((cx, cy, z))

    boss = (cylinder(x, y, floor, BOSS/2, full_height)
            - cylinder(x, y, floor-.1, WIDTH/2+.01, full_height+.2))
    height = roof-floor+.1
    lip = md.Manifold.cube((2*r, TRAVEL, height)).translate((x-r, y-half, floor-.1))
    slot = cylinder(x, y-half, floor-.1, r, height) + lip + cylinder(x, y+half, floor-.1, r, height)
    body = solid(raw)
    fitted = ((body + boss) - slot).simplify(.00002)
    result = mesh_from_solid(fitted)
    if not result.is_volume or result.body_count != 1 or not result.nondegenerate_faces().all():
        raise ValueError("The updated print mesh must remain one closed printable body")
    return result


def build(source_cad, source_print, output):
    output.mkdir(parents=True, exist_ok=True)
    cad = output / source_cad.name
    project = output / source_print.name
    if cad.resolve() == source_cad.resolve() or project.resolve() == source_print.resolve():
        raise ValueError("Choose a separate output directory")

    doc = App.openDocument(str(source_cad.resolve()))
    try:
        tie_bar = doc.getObject(PART)
        replace(tie_bar, native_cut(world_shape(tie_bar)))
        doc.recompute()
        doc.saveAs(str(cad.resolve()))
    finally:
        App.closeDocument(doc.Name)

    with ZipFile(source_print) as archive:
        mesh, _ = archived_mesh(archive, PRINT, PLATE)
    pack(project, {PRINT: (PRINT, printable(mesh))}, output / "print-build.json",
         source=source_print, revision="B25")
    with ZipFile(source_print) as before, ZipFile(project) as after:
        initial, final = map(plate_signatures, (before, after))
        if {plate for plate in initial if initial[plate] != final[plate]} != {PLATE}:
            raise ValueError("Only plate 8 should change")
        changed = {old[0] for old, new in zip(initial[PLATE], final[PLATE], strict=True) if old != new}
        if changed != {"64"}:
            raise ValueError("Only the tie bar should change on plate 8")

    report = {
        "source_cad_sha256": digest(source_cad),
        "cad_sha256": digest(cad),
        "source_p2s_sha256": digest(source_print),
        "p2s_sha256": digest(project),
        "center_xy_mm": [X, Y],
        "finished_slot_xy_mm": [WIDTH, WIDTH+TRAVEL],
        "p2s_slot_xy_mm": [round(WIDTH+PRINT_ALLOWANCE, 2), round(WIDTH+PRINT_ALLOWANCE+TRAVEL, 2)],
        "local_boss_diameter_mm": BOSS,
        "minimum_finished_wall_mm": BOSS/2-(WIDTH+TRAVEL)/2,
        "minimum_p2s_model_wall_mm": BOSS/2-(WIDTH+PRINT_ALLOWANCE+TRAVEL)/2,
        "pin_stop_plane_z_mm": STOP_Z,
    }
    (output/"eye-yaw-slot.json").write_text(json.dumps(report, indent=2)+"\n")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    for name in ("source_cad", "source_print", "output"):
        parser.add_argument(name, type=Path)
    build(**vars(parser.parse_args()))
