"""Export the A4 KiCad project and order files as one offline HTML viewer."""

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
HUB = ROOT / "electronics/servo-hub"
FAB = HUB.parent / "fabrication"
BOARD = HUB / "R5_Servo_Hub.kicad_pcb"
SCHEMATIC = BOARD.with_suffix(".kicad_sch")
PREFIX = "R5_Servo_Hub_A4"
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


def source_zip():
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for path in sorted(HUB.rglob("*")):
            if path.is_file() and (path.suffix in {".kicad_pcb", ".kicad_sch", ".kicad_pro", ".kicad_mod", ".kicad_sym", ".csv"}
                                   or path.name in {"fp-lib-table", "sym-lib-table"}):
                archive.write(path, path.relative_to(HUB))
    return stream.getvalue()


def inspect_board():
    board = pcbnew.LoadBoard(str(BOARD))
    edge = board.GetBoardEdgesBoundingBox()
    origin = pcbnew.VECTOR2I(edge.GetLeft() + pcbnew.FromMM(PLOT_OFFSET),
                            edge.GetTop() + pcbnew.FromMM(PLOT_OFFSET))
    bom = {row["Ref"]: row for row in read_csv(HUB / "BOM.csv")}
    pcba = {ref: row["JLCPCB Part #"]
            for row in read_csv(FAB / (PREFIX + "-JLCPCB-BOM.csv"))
            for ref in row["Designator"].split(",")}
    placements = {row["Designator"]: row for row in read_csv(FAB / (PREFIX + "-JLCPCB-CPL.csv"))}
    if set(pcba) != set(placements) or any(row["Layer"] != "Bottom" for row in placements.values()):
        raise ValueError("The A4 order BOM and bottom CPL differ.")

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
                layers=["F" if layer == pcbnew.F_Cu else "B" for layer in (pcbnew.F_Cu, pcbnew.B_Cu)
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
            tracks.append([item.GetNetname(), "F" if item.GetLayer() == pcbnew.F_Cu else "B",
                           point(item.GetStart(), origin), point(item.GetEnd(), origin), mm(item.GetWidth())])
    with ZipFile(FAB / (PREFIX + "-Gerbers.zip")) as archive:
        job = json.loads(archive.read(next(name for name in archive.namelist() if name.endswith(".gbrjob"))))
    dim = [round(mm(edge.GetWidth()) - 2 * PLOT_OFFSET, 3), round(mm(edge.GetHeight()) - 2 * PLOT_OFFSET, 3)]
    return dict(
        parts=parts, tracks=tracks, vias=vias, dim=dim, origin=[mm(origin.x), mm(origin.y)],
        minTrack=min(t[-1] for t in tracks), pthCount=len(rings), minRing=min(rings), mountingHoles=no_plating,
        pcbaCount=len(pcba), layers=board.GetCopperLayerCount(), stack=job["MaterialStackup"],
        clearance=json.loads(BOARD.with_suffix(".kicad_pro").read_text())["board"]["design_settings"]["rules"]["min_clearance"],
        sha={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (BOARD, SCHEMATIC)},
        revision=run("git", "rev-parse", "HEAD").stdout.strip(),
    )


def model_references(glb):
    length = int.from_bytes(glb[12:16], "little")
    document = json.loads(glb[20:20 + length])
    return sorted({node["name"] for node in document.get("nodes", ()) if "mesh" in node and "name" in node})


def build(args):
    with TemporaryDirectory(prefix="a4-html-") as temp:
        work = Path(temp)
        version = run("kicad-cli", "--version").stdout.strip()
        run("kicad-cli", "sch", "erc", "--exit-code-violations", "-o", work / "erc.rpt", SCHEMATIC)
        run("kicad-cli", "pcb", "drc", "--schematic-parity", "--all-track-errors",
            "--exit-code-violations", "-o", work / "drc.rpt", BOARD)
        run("kicad-cli", "sch", "export", "svg", "--exclude-drawing-sheet", "--no-background-color", "-o", work, SCHEMATIC)
        drawings = {}
        for side in ("F", "B"):
            for kind, layers in (("copper", f"{side}.Cu"), ("silk", f"{side}.Silkscreen"), ("edge", "Edge.Cuts")):
                if kind == "edge" and side == "B":
                    continue
                output = work / f"{side}-{kind}.svg"
                run("kicad-cli", "pcb", "export", "svg", "--mode-single", "--fit-page-to-board", "--page-size-mode", "2",
                    "--exclude-drawing-sheet", "--drill-shape-opt", "0", "--layers", layers, "-o", output, BOARD)
                drawings[f"{side}-{kind}"] = svg(output, f"{side}-{kind}")
        details = inspect_board()
        model = args.glb
        if model is None:
            model = work / "board.glb"
            run("kicad-cli", "pcb", "export", "glb", "-o", model,
                "--user-origin", "100x80mm", "--include-pads", "--include-silkscreen", "--include-soldermask", BOARD)
        glb = model.read_bytes()
        details["modeled"] = list(set(model_references(glb)) & details["parts"].keys())
        details["modeled"].sort()
        details["drawings"] = drawings
        details["model"] = b64(glb)
        details["toolVersion"] = version
        details["placementImage"] = b64((FAB / (PREFIX + "-bottom-placement.png")).read_bytes())
        details["downloads"] = {
            name: b64((FAB / name).read_bytes()) for name in (
                PREFIX + "-Gerbers.zip", PREFIX + "-JLCPCB-BOM.csv", PREFIX + "-JLCPCB-CPL.csv", PREFIX + "-Stencil.zip",
            )
        }
        details["downloads"][PREFIX + "-BOM.csv"] = b64((HUB / "BOM.csv").read_bytes())
        details["downloads"][PREFIX + "-KiCad.zip"] = b64(source_zip())
        bundle = run("npx", "--yes", "esbuild@0.25.12", HERE / "viewer.js", "--bundle", "--minify", "--format=iife").stdout
        html = (HERE / "index.html").read_text()
        html = html.replace("__CSS__", (HERE / "style.css").read_text())
        html = html.replace("__SCHEMATIC__", svg(work / (SCHEMATIC.stem + ".svg"), "schematic"))
        html = html.replace("__DATA__", json.dumps(details, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c"))
        html = html.replace("__SCRIPT__", bundle.replace("</script", "<\\/script"))
        license_text = (ROOT / "web/node_modules/three/LICENSE").read_text()
        html += "\n<!-- Three.js\n" + license_text + "\n-->\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(html, encoding="utf-8")
        print(f"{args.output}: {len(details['parts'])} footprints, {len(details['modeled'])} 3D component models")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--glb", type=Path, help="Optional A4 KiCad GLB exported with origin 100x80mm")
    build(parser.parse_args())
