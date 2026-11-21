"""Pack the B20 printing geometry into the existing 13-plate P2S project."""

from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
import manifold3d
import numpy as np
import trimesh


REVISIONS = Path(__file__).resolve().parent / "revisions"
CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
PRODUCTION = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"
MODEL = "3D/3dmodel.model"
MODEL_SETTINGS = "Metadata/model_settings.config"
MODEL_RELS = "3D/_rels/3dmodel.model.rels"
REMOVED = "39_right_jaw_pivot_arm.stl"
GUARD_SLOT = "38_left_jaw_drive_arm.stl"
YOKE_ARCHIVE = REVISIONS / "b18/study/R5-B18-yoke-and-ID5-keeper.zip"
JAW_ARCHIVE = REVISIONS / "b19/print/30_38_39_jaw_one_piece-B19.3mf"
B19_PRINT = REVISIONS / "b19/print"
REPLACEMENTS = {
    "09_head_frame.stl": B19_PRINT / "09_head_frame-B19.stl",
    "xl330_eye_yaw_front_plate.stl": B19_PRINT / "xl330_eye_yaw_front_plate-B19.stl",
    GUARD_SLOT: B19_PRINT / "ID5-keeper-B19.stl",
    "19_blink_servo_horn.stl": B19_PRINT / "19_blink_servo_horn-B19.stl",
    "21_blink_shaft_crank_2.stl": B19_PRINT / "21_blink_shaft_crank_2-B19.stl",
    "45_blink_shaft_spacer_left.stl": B19_PRINT / "45_blink_shaft_spacer_left-B19.stl",
    "45_blink_shaft_spacer_right.stl": B19_PRINT / "45_blink_shaft_spacer_right-B19.stl",
    "B16_40_captive_cable_tray.stl": REVISIONS / "b18/40-rear-cable-guide-B18.stl",
    "42_captive_cable_cover.stl": REVISIONS / "b18/42-rear-cable-cover-B18.stl",
    "26_u20cam_slotted_bracket.stl": B19_PRINT / "26_u20cam_slotted_bracket-B19.stl",
}


def serialize(element):
    return etree.tostring(element, encoding="UTF-8", xml_declaration=True)


def template_parts(config):
    items = {}
    for obj in config.findall("object"):
        parts = obj.findall("part")
        if len(parts) == 1:
            source = parts[0].find("metadata[@key='source_file']")
            if source is not None and source.get("value") not in items:
                items[source.get("value")] = (obj, parts[0])
    return items


def load_jaw():
    with ZipFile(JAW_ARCHIVE) as source:
        mesh = etree.fromstring(source.read(MODEL)).find(".//" + CORE + "mesh")
    vertices = np.array([[float(v.get(axis)) for axis in "xyz"] for v in mesh.find(CORE + "vertices")])
    triangles = np.array([[int(t.get(k)) for k in ("v1", "v2", "v3")]
                          for t in mesh.find(CORE + "triangles")], dtype=np.uint64)
    original = trimesh.Trimesh(vertices, triangles, process=False)
    # The B19 archive rounds some seam vertices to the same coordinate.
    body = manifold3d.Manifold(manifold3d.Mesh64(vertices, triangles))
    simplified = body.simplify(0.0003).to_mesh64()
    jaw = trimesh.Trimesh(simplified.vert_properties[:, :3], simplified.tri_verts, process=False)
    if not np.allclose(original.bounds, jaw.bounds, rtol=0, atol=0.001) or abs(original.volume - jaw.volume) > 0.01:
        raise ValueError("Jaw cleanup moved the printing geometry")
    return jaw


def has_one_printed_body(mesh):
    if mesh.body_count == 1:
        return True
    shells = mesh.split(only_watertight=False)
    material = [shell for shell in shells if shell.volume > 0.]
    if len(material) != 1 or any(not shell.is_watertight or shell.volume == 0. for shell in shells):
        return False
    outer, = material
    return all(outer.contains(shell.vertices).all() for shell in shells if shell.volume < 0.)


def replace_mesh(data, replacement):
    if not replacement.is_volume or not has_one_printed_body(replacement) or not replacement.nondegenerate_faces().all():
        raise ValueError("The replacement must be one closed solid with nondegenerate faces")
    model = etree.fromstring(data)
    mesh = model.find(".//" + CORE + "mesh")
    vertices = mesh.find(CORE + "vertices")
    triangles = mesh.find(CORE + "triangles")
    original = np.array([[float(v.get(axis)) for axis in "xyz"] for v in vertices])
    old_min, old_max = original.min(axis=0), original.max(axis=0)
    offset = (old_min + old_max) / 2 - replacement.bounds.mean(axis=0)
    offset[2] = old_min[2] - replacement.bounds[0, 2]
    vertices.clear()
    triangles.clear()
    for x, y, z in replacement.vertices + offset:
        etree.SubElement(vertices, CORE + "vertex", x=f"{x:.9g}", y=f"{y:.9g}", z=f"{z:.9g}")
    for a, b, c in replacement.faces:
        etree.SubElement(triangles, CORE + "triangle", v1=str(a), v2=str(b), v3=str(c))
    return serialize(model)


def remove_part(obj, model, config, relationships, deleted):
    object_id = obj.get("id")
    component = model.find(f".//{CORE}object[@id='{object_id}']//{CORE}component")
    target = component.get(PRODUCTION + "path")
    deleted.add(target.lstrip("/"))
    for element in (model.find(f".//{CORE}object[@id='{object_id}']"),
                    model.find(f".//{CORE}item[@objectid='{object_id}']"), obj,
                    config.xpath(f".//model_instance[metadata[@key='object_id'][@value='{object_id}']]")[0],
                    relationships.find(f"*[@Target='{target}']")):
        element.getparent().remove(element)


def build(output, cradle):
    source = REVISIONS / "b16/R5-B16-P2S.3mf"
    replacements = {name: (path.name, trimesh.load_mesh(path)) for name, path in REPLACEMENTS.items()}
    replacements["12_eye_tilt_cradle.stl"] = (cradle.name, trimesh.load_mesh(cradle))
    with ZipFile(YOKE_ARCHIVE) as yoke:
        replacements["07_pitch_yoke.stl"] = (
            "07-yoke-B18.stl", trimesh.load_mesh(BytesIO(yoke.read("07-yoke-B18.stl")), file_type="stl")
        )
    replacements["30_moving_jaw.stl"] = ("30_38_39_jaw_one_piece-B20.3mf", load_jaw())
    changes, deleted = {}, set()
    with ZipFile(source) as base:
        model = etree.fromstring(base.read(MODEL))
        config = etree.fromstring(base.read(MODEL_SETTINGS))
        relationships = etree.fromstring(base.read(MODEL_RELS))
        index = template_parts(config)
        for old_name, (new_name, mesh) in replacements.items():
            obj, part = index[old_name]
            object_id = obj.get("id")
            component = model.find(f".//{CORE}object[@id='{object_id}']//{CORE}component")
            path = component.get(PRODUCTION + "path").lstrip("/")
            changes[path] = replace_mesh(base.read(path), mesh)
            for element in (obj, part):
                element.find("metadata[@key='name']").set("value", Path(new_name).stem)
            part.find("metadata[@key='source_file']").set("value", new_name)
            obj.find("metadata[@face_count]").set("face_count", str(len(mesh.faces)))
            part.find("mesh_stat").set("face_count", str(len(mesh.faces)))
            if old_name == GUARD_SLOT:
                etree.SubElement(obj, "metadata", key="brim_type", value="outer_only")
                etree.SubElement(obj, "metadata", key="brim_width", value="6")
        remove_part(index[REMOVED][0], model, config, relationships, deleted)
        model.find(f"{CORE}metadata[@name='Title']").text = "R5 B20 P2S"
        changes.update({MODEL: serialize(model), MODEL_SETTINGS: serialize(config),
                        MODEL_RELS: serialize(relationships)})
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, "w") as package:
            for item in base.infolist():
                if item.filename not in deleted:
                    data = changes[item.filename] if item.filename in changes else base.read(item)
                    package.writestr(item, data)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cradle", type=Path,
                        default=REVISIONS / "b20/print/12_eye_tilt_cradle-B20.stl")
    args = parser.parse_args()
    build(args.output, args.cradle)
