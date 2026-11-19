"""Export Gerber, Excellon, and C3 placement files with KiCad 9."""

from argparse import ArgumentParser
import csv
from pathlib import Path
from shutil import copyfile
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

HERE = Path(__file__).resolve().parent
PROJECTS = {"servo-hub": "R5_Servo_Hub", "c3-rf": "C3_Antenna"}


def kicad(*args):
    subprocess.run(["kicad-cli", *map(str, args)], check=True)


def prepare_c3(board_file, work, output):
    import pcbnew

    with (board_file.parent / "BOM.csv").open(encoding="utf-8-sig", newline="") as stream:
        bom = list(csv.DictReader(stream))
    dnp = {row["Ref"] for row in bom if row["Populate"] == "DNP"}
    placements = {row["Ref"] for row in bom if row["Populate"] == "YES"} - {"J2"}

    board = pcbnew.LoadBoard(str(board_file))
    omitted = {footprint.GetReference(): footprint for footprint in board.GetFootprints() if footprint.IsDNP()}
    if set(omitted) != dnp:
        raise ValueError("KiCad and BOM DNP references differ")
    for footprint in omitted.values():
        for pad in footprint.Pads():
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
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return stencil_board


def export(project):
    name = PROJECTS[project]
    board = HERE / project / f"{name}.kicad_pcb"
    output = HERE.parent / "build" / "electronics" / project
    output.mkdir(parents=True, exist_ok=True)
    layers = ["F.Cu", "B.Cu", "F.Mask", "B.Mask", "F.Silkscreen", "B.Silkscreen", "Edge.Cuts"]
    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        plot_board = board
        if project == "c3-rf":
            layers += ["In1.Cu", "In2.Cu", "F.Paste"]
            plot_board = prepare_c3(board, work, output)
        plots = work / "gerbers"
        plots.mkdir()
        kicad("pcb", "export", "gerbers", "--no-protel-ext", "--subtract-soldermask",
              "-l", ",".join(layers), "-o", plots, plot_board)
        kicad("pcb", "export", "drill", "--excellon-separate-th", "--excellon-units", "mm",
              "--excellon-zeros-format", "decimal", "-o", plots, board)
        with ZipFile(output / f"{name}-Gerbers.zip", "w", ZIP_DEFLATED) as archive:
            for plot in sorted(plots.iterdir()):
                archive.write(plot, plot.name)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("project", choices=PROJECTS)
    export(parser.parse_args().project)
