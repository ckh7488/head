"""Export a servo hub revision and its order files as one offline HTML viewer."""

import argparse
import base64
import csv
import hashlib
import io
import json
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


def model_references(glb):
    length = int.from_bytes(glb[12:16], "little")
    document = json.loads(glb[20:20 + length])
    return sorted({node["name"] for node in document.get("nodes", ()) if "mesh" in node and "name" in node})


def placement_diagram(parts):
    """Show the real bottom footprint orientations from the board pad coordinates."""
    elements = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 510 170">',
                '<rect width="510" height="170" rx="10" fill="#102b20"/>']
    for index, ref in enumerate(("U1", "U2", "U3")):
        part = parts[ref]
        cx, cy = part["xy"]
        x0, y0 = 85 + index * 170, 70
        elements.append(f'<rect x="{x0 - 39}" y="{y0 - 39}" width="78" height="78" rx="4" '
                        'fill="#1e2c25" stroke="#7b9185"/>')
        for pad in part["pads"]:
            if pad["id"] not in {"1", "2", "3", "4", "5", "6", "7", "8"}:
                continue
            x, y = pad["xy"]
            px, py = x0 - (x - cx) * 25, y0 + (y - cy) * 25
            color = "#f6c165" if pad["id"] == "1" else "#bacfc2"
            elements.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="6" fill="{color}"/>')
        elements.append(f'<text x="{x0}" y="134" fill="white" text-anchor="middle" font-size="18">{ref}</text>')
    elements.append('<text x="255" y="157" fill="#f6c165" font-size="13" text-anchor="middle">밑면에서 본 방향 · 금색 점 = 1번 핀</text></svg>')
    return b64("".join(elements).encode())


def build(args):
    hub = FAB.parent / ("servo-hub-a5" if args.hub_revision == "A5" else "servo-hub")
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
            run("kicad-cli", "pcb", "export", "glb", "-o", model,
                "--user-origin", "100x80mm", "--include-pads", "--include-silkscreen", "--include-soldermask", board)
        glb = model.read_bytes()
        details["modeled"] = list(set(model_references(glb)) & details["parts"].keys())
        details["modeled"].sort()
        details["drawings"] = drawings
        details["model"] = b64(glb)
        details["toolVersion"] = version
        details["placementImage"] = placement_diagram(details["parts"])
        details["downloads"] = {
            name: b64((FAB / name).read_bytes()) for name in (
                prefix + "-Gerbers.zip", prefix + "-JLCPCB-BOM.csv", prefix + "-JLCPCB-CPL.csv", prefix + "-Stencil.zip",
            )
        }
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
    parser.add_argument("--hub-revision", choices=("A4", "A5"), default="A4")
    parser.add_argument("--glb", type=Path, help="Optional KiCad GLB exported with origin 100x80mm")
    build(parser.parse_args())
