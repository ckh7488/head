"""Check the KiCad projects and export fabrication and assembly files."""

from argparse import ArgumentParser
import csv
import json
import re
from pathlib import Path
from shutil import copyfile
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

HERE = Path(__file__).resolve().parent
PROJECTS = {"servo-hub": "R5_Servo_Hub", "c3-rf": "C3_Antenna"}
REVISIONS = {"servo-hub": "A2", "c3-rf": "A1"}
COMMON_LAYERS = ["F.Cu", "B.Cu", "F.Mask", "B.Mask", "F.Silkscreen", "B.Silkscreen", "Edge.Cuts"]


def kicad(*args):
    subprocess.run(["kicad-cli", *map(str, args)], check=True)


def bom_rows(board_file):
    import pcbnew

    with (board_file.parent / "BOM.csv").open(encoding="utf-8-sig", newline="") as stream:
        bom = list(csv.DictReader(stream))
    board = pcbnew.LoadBoard(str(board_file))
    footprints = {part.GetReference(): part for part in board.GetFootprints()}
    if len(bom) != len(footprints) or {row["Ref"] for row in bom} != set(footprints):
        raise ValueError("KiCad and BOM references differ")
    omitted = {ref for ref, part in footprints.items() if part.IsDNP()}
    if omitted != {row["Ref"] for row in bom if row["Populate"] == "DNP"}:
        raise ValueError("KiCad and BOM DNP references differ")
    for row in bom:
        part = footprints[row["Ref"]]
        identifier = part.GetFPID()
        if f"{identifier.GetLibNickname()}:{identifier.GetLibItemName()}" != row["Footprint"]:
            raise ValueError(f'{part.GetReference()} has a different footprint in the BOM')
        if part.GetValue() != row["Value"]:
            raise ValueError(f'{part.GetReference()} has a different value in the BOM')
    return board, bom, footprints, omitted


def prepare_c3(board_file, work, output):
    import pcbnew

    board, bom, footprints, omitted = bom_rows(board_file)
    placements = {
        row["Ref"] for row in bom
        if row["Populate"] == "YES"
        and not footprints[row["Ref"]].GetAttributes() & pcbnew.FP_THROUGH_HOLE
    }
    for ref in omitted:
        for pad in footprints[ref].Pads():
            layers = pad.GetLayerSet()
            layers.RemoveLayer(pcbnew.F_Paste)
            pad.SetLayerSet(layers)
    stencil_board = work / board_file.name
    copyfile(board_file.with_suffix(".kicad_pro"), stencil_board.with_suffix(".kicad_pro"))
    pcbnew.SaveBoard(str(stencil_board), board)

    candidate = work / "positions.csv"
    kicad("pcb", "export", "pos", "--side", "front", "--format", "csv", "--units", "mm", "--exclude-dnp",
          "-o", candidate, board_file)
    with candidate.open(newline="") as stream:
        reader = csv.DictReader(stream)
        rows = [row for row in reader if row["Ref"] in placements]
        fields = reader.fieldnames
    if len(rows) != len(placements) or {row["Ref"] for row in rows} != placements:
        raise ValueError("C3 positions do not match the assembly BOM")
    with (output / "C3-front-positions-mm.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return stencil_board


def plot(board, layers, output):
    output.mkdir()
    kicad("pcb", "export", "gerbers", "--no-protel-ext", "--subtract-soldermask",
          "-l", ",".join(layers), "-o", output, board)


def align_copper_layer_numbers(job_file, layers):
    job = json.loads(job_file.read_text())
    copper = []
    for entry in job["FilesAttributes"]:
        if not entry["FileFunction"].startswith("Copper,"):
            continue
        gerber = (job_file.parent / entry["Path"]).read_text()
        header = re.search(r"^%TF\.FileFunction,(Copper,L\d+,(?:Top|Inr|Bot))\*%$", gerber, re.MULTILINE)
        if header is None:
            raise ValueError(f'Missing copper layer header in {entry["Path"]}')
        entry["FileFunction"] = header[1]
        copper.append(int(header[1].split(",")[1][1:]))
    if job["GeneralSpecs"]["LayerNumber"] != layers or copper != list(range(1, layers+1)):
        raise ValueError(f'{job_file.name} has an invalid copper stack: {copper}')
    job_file.write_text(json.dumps(job, indent=2) + "\n")


def check_hub_annular_rings(board):
    import pcbnew

    minimum_ring = pcbnew.FromMM(.254)
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
                continue
            size, drill = pad.GetSize(), pad.GetDrillSize()
            if min(size.x-drill.x, size.y-drill.y) < 2*minimum_ring:
                raise ValueError(f'{footprint.GetReference()} pin {pad.GetNumber()} lacks the 2 oz annular ring')


def archive(source, output):
    with ZipFile(output, "w", ZIP_DEFLATED) as file:
        for entry in sorted(source.iterdir()):
            file.write(entry, entry.name)


def export(project, output_root):
    name = PROJECTS[project]
    board = HERE / project / f"{name}.kicad_pcb"
    output = output_root / project
    output.mkdir(parents=True, exist_ok=True)
    kicad("sch", "erc", "--exit-code-violations", "-o", output / "erc.rpt", board.with_suffix(".kicad_sch"))
    kicad("pcb", "drc", "--schematic-parity", "--all-track-errors", "--exit-code-violations",
          "-o", output / "drc.rpt", board)
    prefix = f"{name}_{REVISIONS[project]}"
    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        layers = COMMON_LAYERS.copy()
        if project == "c3-rf":
            layers += ["In1.Cu", "In2.Cu"]
            stencil = work / "stencil"
            plot(prepare_c3(board, work, output), ["F.Paste", "Edge.Cuts"], stencil)
            for job in stencil.glob("*.gbrjob"):
                job.unlink()
            archive(stencil, output / f"{prefix}-Stencil.zip")
        else:
            hub, _, _, _ = bom_rows(board)
            check_hub_annular_rings(hub)
        plots = work / "gerbers"
        plot(board, layers, plots)
        if project == "c3-rf":
            align_copper_layer_numbers(plots / f"{name}-job.gbrjob", 4)
        kicad("pcb", "export", "drill", "--excellon-separate-th", "--excellon-units", "mm",
              "--excellon-zeros-format", "decimal", "-o", plots, board)
        archive(plots, output / f"{prefix}-Gerbers.zip")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("project", choices=PROJECTS)
    parser.add_argument("--output", type=Path, default=HERE.parent / "build" / "electronics")
    options = parser.parse_args()
    export(options.project, options.output)
