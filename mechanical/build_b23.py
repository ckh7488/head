"""Build the B23 head with revised force paths and captive service nuts."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path

import FreeCAD as App
import Part

from build_b19_review_fixes import replace
from build_b21_fasteners import check_solid
from build_b22_camera_guides import nose_cradle
from build_b23_eye_pitch import apply as index_eye_pitch
from build_b23_skull_relief import apply as relieve_front_shell
from build_b23_yaw_limit import apply as limit_yaw
from build_b23_yaw_shim import apply as seat_yaw_bearing
from build_service_cable_nuts import apply as retain_rear_nuts
from build_service_covers import BASE
from build_service_hatch_nuts import apply as retain_hatch_nuts
from export_cad import world_shape
from primitives import print_mesh


TIE_ROOF_DROP = .25
BRACKET_PRINT = '26_u20cam_slotted_bracket-B23.stl'


def digest(path):
    with path.open('rb') as file:
        return file_digest(file, 'sha256').hexdigest()


def thicken_tie_saddle(doc, prints):
    old_saddle, _ = nose_cradle()
    saddle, roof = nose_cradle(TIE_ROOF_DROP)
    added = saddle.cut(old_saddle)
    bracket = check_solid(world_shape(doc.Part066).fuse(added).removeSplitter(), 'camera saddle with thicker roof')
    replace(doc.Part066, bracket)
    print_mesh(bracket, prints / BRACKET_PRINT)

    x, y = 6.387737626531255, -40.450607273288774
    measure = bracket.common(Part.makeLine(App.Vector(x, y, 76.), App.Vector(x, y, 80.)))
    walls = [edge.Length for edge in measure.Edges
             if abs(min(vertex.Point.z for vertex in edge.Vertexes) - roof[2]) <= .015]
    if not walls or min(walls) < 1.2:
        raise ValueError('Camera saddle wall witness is under 1.2 mm')
    tie = Part.makeBox(9.2, 2.5, 1.05, App.Vector(roof[0]-4.6, roof[1]-1.25, 76.5-.525))
    if bracket.common(tie).Volume > 1e-7:
        raise ValueError('Stock cable tie does not clear the thickened saddle')

    motion = json.loads(doc.R5.MotionGeometry)
    motion['camera_cable_nose']['tie_notch_roof_center_mm'] = roof
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)
    return {'wall_mm': min(walls), 'witness_xy_mm': [x, y], 'tie_roof_center_mm': roof,
            'tie_gauge_mm': [9.2, 2.5, 1.05], 'tie_gauge_center_z_mm': 76.5}


def build(output):
    output = output.resolve()
    prints = output / 'print'
    prints.mkdir(parents=True, exist_ok=True)
    assembly = output / 'R5-B23-Assembly.FCStd'
    doc = App.openDocument(str(BASE))
    try:
        doc.Label = 'R5 B23'
        yaw = seat_yaw_bearing(doc, prints)
        yaw_limit = limit_yaw(doc, prints)
        world_shape(doc.YawInnerRaceShim).exportStep(str(output / 'yaw-shim.step'))
        eye_pitch = index_eye_pitch(doc, prints)
        eye_pitch['front_shell_relief'] = relieve_front_shell(doc)
        retain_rear_nuts(doc, prints)
        hatch = retain_hatch_nuts(doc, prints)
        witness = thicken_tie_saddle(doc, prints)
        metadata = json.loads(doc.R5.MotionGeometry)
        metadata['bottom_board_service_nuts'] = hatch
        doc.R5.MotionGeometry = json.dumps(metadata, ensure_ascii=False)
        doc.recompute()
        doc.saveAs(str(assembly))
    finally:
        App.closeDocument(doc.Name)

    report = {'reference_cad_sha256': digest(BASE), 'cad_sha256': digest(assembly), 'camera_saddle': witness,
              'yaw_inner_race_shim': yaw, 'eye_pitch': eye_pitch,
              'yaw_limit': yaw_limit,
              'rear_cable_service_nuts': metadata['rear_cable_service_nuts'], 'bottom_board_service_nuts': hatch,
              'print_sha256': {path.name: digest(path) for path in sorted(prints.glob('*.stl'))}}
    (output / 'design.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(assembly)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
