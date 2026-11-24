"""Export a servo hub revision and its order files as one offline HTML viewer."""

import argparse
import base64
import csv
import hashlib
import io
import json
from math import atan2, cos, hypot, sin
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FAB = ROOT / "electronics/fabrication"
PLOT_OFFSET = 0.025
XT30_MODEL = "AMASS_XT30PW-M_1x02_P2.50mm_Horizontal.step"


def run(*args):
    return subprocess.run([str(arg) for arg in args], check=True, text=True, capture_output=True, cwd=ROOT)


def svg(path, name):
    content = path.read_text().split("<svg", 1)[1]
    return '<svg id="' + name + '"' + re.sub(r'\s(width|height)="[^"]+"', "", content, count=2)


def b64(content):
    return base64.b64encode(content).decode("ascii")


def mm(raw):
    return round(pcbnew.ToMM(raw), 5)


def point(position, origin):
    return [round(mm(position.x - origin.x), 5), round(mm(position.y - origin.y), 5)]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def source_zip(hub):
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for path in sorted(hub.rglob("*")):
            if path.is_file() and (path.suffix in {".kicad_pcb", ".kicad_sch", ".kicad_pro", ".kicad_mod", ".kicad_sym", ".csv"}
                                   or path.name in {"fp-lib-table", "sym-lib-table"}):
                archive.write(path, path.relative_to(hub))
    return stream.getvalue()


def inspect_board(board_path, prefix):
    board = pcbnew.LoadBoard(str(board_path))
    copper_layers = {layer: board.GetLayerName(layer).removesuffix(".Cu")
                     for layer in board.GetEnabledLayers().CuStack()}
    hub = board_path.parent
    edge = board.GetBoardEdgesBoundingBox()
    origin = pcbnew.VECTOR2I(edge.GetLeft() + pcbnew.FromMM(PLOT_OFFSET),
                            edge.GetTop() + pcbnew.FromMM(PLOT_OFFSET))
    bom = {row["Ref"]: row for row in read_csv(hub / "BOM.csv")}
    hand_assembled = board.GetTitleBlock().GetRevision() == "A6"
    pcba = {}
    placements = {}
    if not hand_assembled:
        pcba = {ref: row["JLCPCB Part #"]
                for row in read_csv(FAB / (prefix + "-JLCPCB-BOM.csv"))
                for ref in row["Designator"].split(",")}
        placements = {row["Designator"]: row for row in read_csv(FAB / (prefix + "-JLCPCB-CPL.csv"))}
    if set(pcba) != set(placements) or any(row["Layer"] != "Bottom" for row in placements.values()):
        raise ValueError("The order BOM and bottom CPL differ.")

    parts = {}
    rings = []
    no_plating = []
    for fp in sorted(board.GetFootprints(), key=lambda item: item.GetReference()):
        ref = fp.GetReference()
        if ref not in bom or fp.GetValue() != bom[ref]["Value"]:
            raise ValueError(f"Mismatch between board and BOM for {ref}")
        pads = []
        for pad in fp.Pads():
            size = pad.GetSize()
            drill = pad.GetDrillSize()
            pads.append(dict(
                id=pad.GetNumber(), net=pad.GetNetname(), xy=point(pad.GetPosition(), origin),
                size=[mm(size.x), mm(size.y)], drill=[mm(drill.x), mm(drill.y)],
                layers=[name for layer, name in copper_layers.items()
                        if pad.GetLayerSet().Contains(layer)],
            ))
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and drill.x:
                rings.append(mm(min(size.x - drill.x, size.y - drill.y) // 2))
            elif pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH and drill.x:
                no_plating.append(mm(drill.x))
        parts[ref] = dict(
            value=fp.GetValue(), side="B" if fp.IsFlipped() else "F", xy=point(fp.GetPosition(), origin),
            pads=sorted(pads, key=lambda pad: (not pad["id"].isdigit(), int(pad["id"]) if pad["id"].isdigit() else pad["id"])),
            mpn=bom[ref]["Part or buying specification"], notes=bom[ref]["Notes"],
            footprint=bom[ref]["Footprint"], populate=bom[ref]["Populate"],
            jlc=pcba.get(ref), placement=placements.get(ref),
        )
    if set(parts) != set(bom) or any(parts[ref]["side"] != "B" for ref in pcba):
        raise ValueError("Board/BOM/placement reference mismatch.")
    tracks = []
    vias = []
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            vias.append([item.GetNetname(), point(item.GetPosition(), origin), mm(item.GetWidth(pcbnew.F_Cu)), mm(item.GetDrillValue())])
        else:
            tracks.append([item.GetNetname(), copper_layers[item.GetLayer()],
                           point(item.GetStart(), origin), point(item.GetEnd(), origin), mm(item.GetWidth())])
    with ZipFile(FAB / (prefix + "-Gerbers.zip")) as archive:
        job = json.loads(archive.read(next(name for name in archive.namelist() if name.endswith(".gbrjob"))))
    dim = [round(mm(edge.GetWidth()) - 2 * PLOT_OFFSET, 3), round(mm(edge.GetHeight()) - 2 * PLOT_OFFSET, 3)]
    return dict(
        parts=parts, tracks=tracks, vias=vias, dim=dim, origin=[mm(origin.x), mm(origin.y)],
        minTrack=min(t[-1] for t in tracks), pthCount=len(rings), minRing=min(rings), mountingHoles=no_plating,
        pcbaCount=len(pcba), layers=list(copper_layers.values()), stack=job["MaterialStackup"],
        hubRevision=board.GetTitleBlock().GetRevision(),
        clearance=json.loads(board_path.with_suffix(".kicad_pro").read_text())["board"]["design_settings"]["rules"]["min_clearance"],
        sha={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in (board_path, board_path.with_suffix(".kicad_sch"))},
        revision=run("git", "rev-parse", "HEAD").stdout.strip(),
    )


def model_document(glb):
    length = int.from_bytes(glb[12:16], "little")
    return json.loads(glb[20:20 + length])


def check_xt30_registration(document, parts):
    """Match the exported XT30 pin cylinders to the four drilled holes at each connector."""
    components = {node.get("name"): node for node in document["nodes"] if "mesh" in node}
    for ref in ("J1", "J2"):
        node = components.get(ref)
        if node is None:
            raise ValueError(f"{ref}: XT30 model missing from the GLB")
        x, top, z = node["translation"]
        qx, qy, qz, qw = node.get("rotation", [0, 0, 0, 1])
        if abs(qx) + abs(qz) > 1e-6 or not .0014 <= top <= .0018:
            raise ValueError(f"{ref}: unexpected connector axis or seating plane in the GLB")
        angle = 2 * atan2(qy, qw)
        c, s = cos(angle), sin(angle)
        pads = parts[ref]["pads"]
        pin_bounds = [[] for _ in pads]
        for face in document["meshes"][node["mesh"]]["primitives"]:
            accessor = document["accessors"][face["attributes"]["POSITION"]]
            u0, y0, v0 = accessor["min"]
            u1, y1, v1 = accessor["max"]
            if not y0 < -top / 2 < y1:
                continue
            # Each pin cylinder is exported as two half faces. Combine their
            # projected bounds after applying the KiCad node's placement.
            bounds = [(1000 * (x + c*u + s*v), 1000 * (z - s*u + c*v))
                      for u in (u0, u1) for v in (v0, v1)]
            center = (sum(a for a, _ in bounds) / 4, sum(b for _, b in bounds) / 4)
            nearest = min(range(len(pads)), key=lambda i: hypot(center[0] - pads[i]["xy"][0],
                                                                center[1] - pads[i]["xy"][1]))
            pad = pads[nearest]
            px, py = pad["xy"]
            radius = pad["drill"][0] / 2
            if any(max(abs(a-px), abs(b-py)) > radius + .01 for a, b in bounds):
                raise ValueError(f"{ref}: model pin lies outside the hole at {px:.3f}, {py:.3f} mm")
            pin_bounds[nearest].extend(bounds)
        for pad, bounds in zip(pads, pin_bounds):
            if not bounds:
                raise ValueError(f"{ref}: no model pin at board hole {pad['xy']}")
            u, v = zip(*bounds)
            center = ((min(u) + max(u)) / 2, (min(v) + max(v)) / 2)
            if hypot(center[0] - pad["xy"][0], center[1] - pad["xy"][1]) > .05:
                raise ValueError(f"{ref}: model pin is off-center at board hole {pad['xy']}")


def export_model(board, output, args):
    render_board = board
    if args.models or args.xt30_step:
        contents = board.read_text()
        if args.models:
            contents = contents.replace("${KICAD9_3DMODEL_DIR}", args.models.resolve().as_posix())
        if args.xt30_step:
            model_path = args.xt30_step.resolve()
            if not model_path.is_file():
                raise ValueError(f"Missing XT30PW-M STEP: {model_path}")
            pattern = (rf'\(model "[^"]*/{re.escape(XT30_MODEL)}"'
                       r'(\s+\(offset\s+\(xyz )0 0 0'
                       r'(\s*\)\s*\)\s*\(scale\s*\(xyz 1 1 1\)\s*\)\s*\(rotate\s*\(xyz )0 0 0')
            def register(match):
                return f'(model "{model_path.as_posix()}"{match[1]}-2.5 8.5 0{match[2]}0 0 180'

            contents, count = re.subn(pattern, register, contents)
            if count != 2:
                raise ValueError("Expected two XT30PW-M model placements")
        # The render board is a temporary copy. The routing, drills and
        # published fabrication files stay tied to the native board.
        render_board = output.with_suffix(".kicad_pcb")
        render_board.write_text(contents)
    run("kicad-cli", "pcb", "export", "glb", "-o", output,
        "--user-origin", "100x80mm", "--include-pads", "--include-silkscreen", "--include-soldermask", render_board)


def placement_diagram(parts):
    """Show the real bottom footprint orientations from the board pad coordinates."""
    elements = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 510 190">',
                '<rect width="510" height="190" rx="10" fill="#102b20"/>']
    refs = ("U1", "U2", "U3")
    hand_assembled = parts["U1"]["value"] == "TPS25221"
    if hand_assembled:
        refs = refs[::-1]
    for index, ref in enumerate(refs):
        part = parts[ref]
        cx, cy = part["xy"]
        x0, y0 = 85 + index * 170, 70
        half_width = 20 if hand_assembled else 39
        elements.append(f'<rect x="{x0 - half_width}" y="{y0 - 37}" width="{half_width * 2}" height="74" rx="4" '
                        'fill="#1e2c25" stroke="#7b9185"/>')
        for pad in part["pads"]:
            if pad["id"] not in {"1", "2", "3", "4", "5", "6", "7", "8"}:
                continue
            x, y = pad["xy"]
            px, py = x0 - (x - cx) * 25, y0 + (y - cy) * 25
            color = "#f6c165" if pad["id"] == "1" else "#bacfc2"
            elements.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="6" fill="{color}"/>')
        label = ref
        if part["placement"]:
            label += f' · CPL {float(part["placement"]["Rotation"]):g}°'
        pin_x, pin_y = next(pad["xy"] for pad in part["pads"] if pad["id"] == "1")
        horizontal = "오른쪽" if pin_x < cx else "왼쪽"
        vertical = "아래" if pin_y > cy else "위"
        elements.append(f'<text x="{x0}" y="133" fill="white" text-anchor="middle" font-size="17">'
                        f'{label}</text>')
        elements.append(f'<text x="{x0}" y="153" fill="#f6c165" text-anchor="middle" font-size="14">'
                        f'1번 핀 {horizontal} {vertical}</text>')
    elements.append('<text x="255" y="177" fill="#bacfc2" font-size="13" text-anchor="middle">'
                    '밑면 기준 · 금색 점은 1번 핀</text></svg>')
    return b64("".join(elements).encode())


def build(args):
    hub = FAB.parent / ("servo-hub" if args.hub_revision == "A4" else f"servo-hub-{args.hub_revision.lower()}")
    board = hub / "R5_Servo_Hub.kicad_pcb"
    schematic = board.with_suffix(".kicad_sch")
    prefix = f"R5_Servo_Hub_{args.hub_revision}"
    with TemporaryDirectory(prefix="hub-html-") as temp:
        work = Path(temp)
        version = run("kicad-cli", "--version").stdout.strip()
        run("kicad-cli", "sch", "erc", "--exit-code-violations", "-o", work / "erc.rpt", schematic)
        run("kicad-cli", "pcb", "drc", "--schematic-parity", "--all-track-errors",
            "--exit-code-violations", "-o", work / "drc.rpt", board)
        run("kicad-cli", "sch", "export", "svg", "--exclude-drawing-sheet", "--no-background-color", "-o", work, schematic)
        details = inspect_board(board, prefix)
        plots = [(side, "copper", f"{side}.Cu") for side in details["layers"]]
        plots.extend((side, "silk", f"{side}.Silkscreen") for side in ("F", "B"))
        plots.append(("F", "edge", "Edge.Cuts"))
        drawings = {}
        for side, kind, layer in plots:
            output = work / f"{side}-{kind}.svg"
            run("kicad-cli", "pcb", "export", "svg", "--mode-single", "--fit-page-to-board", "--page-size-mode", "2",
                "--exclude-drawing-sheet", "--drill-shape-opt", "0", "--layers", layer, "-o", output, board)
            drawings[f"{side}-{kind}"] = svg(output, f"{side}-{kind}")
        model = args.glb
        if model is None:
            model = work / "board.glb"
            export_model(board, model, args)
        glb = model.read_bytes()
        document = model_document(glb)
        if args.hub_revision in {"A5", "A6"}:
            check_xt30_registration(document, details["parts"])
        details["modeled"] = sorted({node.get("name") for node in document["nodes"] if "mesh" in node}
                                    & details["parts"].keys())
        details["drawings"] = drawings
        details["model"] = b64(glb)
        details["toolVersion"] = version
        details["placementImage"] = placement_diagram(details["parts"])
        order_files = ["Gerbers.zip"]
        if args.hub_revision != "A6":
            order_files += ["JLCPCB-BOM.csv", "JLCPCB-CPL.csv", "Stencil.zip"]
        details["downloads"] = {f"{prefix}-{name}": b64((FAB / f"{prefix}-{name}").read_bytes())
                                for name in order_files}
        details["downloads"][prefix + "-BOM.csv"] = b64((hub / "BOM.csv").read_bytes())
        details["downloads"][prefix + "-KiCad.zip"] = b64(source_zip(hub))
        bundle = run("npx", "--yes", "esbuild@0.25.12", HERE / "viewer.js", "--bundle", "--minify", "--format=iife").stdout
        html = (HERE / "index.html").read_text()
        html = html.replace("__CSS__", (HERE / "style.css").read_text())
        html = html.replace("__REVISION__", args.hub_revision)
        html = html.replace("__SCHEMATIC__", svg(work / (schematic.stem + ".svg"), "schematic"))
        html = html.replace("__DATA__", json.dumps(details, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c"))
        html = html.replace("__SCRIPT__", bundle.replace("</script", "<\\/script"))
        license_text = (ROOT / "web/node_modules/three/LICENSE").read_text()
        html += "\n<!-- Three.js\n" + license_text + "\n-->\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(re.sub(r"[ \t]+(?=\n|\Z)", "", html), encoding="utf-8")
        print(f"{args.output}: {len(details['parts'])} footprints, {len(details['modeled'])} 3D component models")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--hub-revision", choices=("A4", "A5", "A6"), default="A4")
    parser.add_argument("--glb", type=Path, help="Optional KiCad GLB exported with origin 100x80mm")
    parser.add_argument("--models", type=Path, help="Override KICAD9_3DMODEL_DIR for export")
    parser.add_argument("--xt30-step", type=Path,
                        help="Unaligned XT30PW-M STEP with contact pins at x ±2.5, y 8.5 mm")
    build(parser.parse_args())
