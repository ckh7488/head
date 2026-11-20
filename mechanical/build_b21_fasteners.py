"""Update the ID5 keeper and optional C3 carrier to use existing M3×8 screws."""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App
import Part

from build_b17_service import SCREW_HEIGHTS, SCREW_SEAT, SCREW_X
from build_b19_review_fixes import add_part, replace, world_shape
from primitives import box, cylinder, print_mesh
from stock import nut, socket_screw


REVISIONS = Path(__file__).resolve().parent / 'revisions'
B16_CAD = REVISIONS / 'b16/R5-B16-Wiring.FCStd'
B20_CAD = REVISIONS / 'b20/R5-B20-Assembly.FCStd'
B19_HARDWARE = REVISIONS / 'b19/print/hardware-spec.json'
M3_LENGTH = 8.
M3_NUT_HEIGHT = 2.4
C3_CLAMPS = ((-74.65, -17.5, -71., -68., -28.8), (-33.35, -15.9, -37., -40., -15.9))
C3_NUT_TOP = -74.0
C3_NUT_BOTTOM = C3_NUT_TOP - M3_NUT_HEIGHT
C3_SCREW_SEAT = -68.7
C3_CLIP_BOTTOM = -70.75
C3_BOARD_TOP = -69.4


def check_solid(shape, name):
    cleaned = shape.removeSplitter()
    if len(cleaned.Solids) != 1 or not cleaned.isValid():
        raise ValueError(f'{name} must be a single valid solid')
    return cleaned


def detached_shape(obj):
    shape = Part.Shape()
    shape.importBrepFromString(world_shape(obj).exportBrepToString())
    return shape


def screw_spec(name, seat, axis, motion, hosts):
    start = [s - a*3.05 for s, a in zip(seat, axis)]
    shank = [s + a*.05 for s, a in zip(seat, axis)]
    return {'name': name, 'motion': motion, 'skip': list(hosts), 'shapes': [
        ['cyl', 2.78, 3., start, list(axis)],
        ['cyl', 1.35, M3_LENGTH-.1, shank, list(axis)],
    ]}


def id5_keeper(doc, unpocketed):
    yoke = detached_shape(doc.Part011)
    keeper = detached_shape(doc.ID5EHKeeper)
    hardware = []
    for index, z in enumerate(SCREW_HEIGHTS, 1):
        # Restore the original yoke material where the former M2 nut recess ran.
        original = unpocketed.common(cylinder(3.4, 4.6, (SCREW_X, 14.18, z), (0, 1, 0)))
        yoke = yoke.fuse(original).cut(cylinder(1.3, 4.6, (SCREW_X, 14.18, z), (0, 1, 0)))
        foot = cylinder(3.3, SCREW_SEAT-18.65, (SCREW_X, 18.65, z), (0, 1, 0))
        keeper = keeper.fuse(foot).cut(cylinder(1.7, 4.65, (SCREW_X, 18.55, z), (0, 1, 0)))
        seat, axis = (SCREW_X, SCREW_SEAT, z), (0, -1, 0)
        name = f'ID5KeeperScrew{index}'
        screw = doc.getObject(name)
        replace(screw, socket_screw(3, M3_LENGTH, seat, axis))
        screw.Label = 'M3 × 8 ID5 keeper-to-yoke screw'
        doc.removeObject(f'ID5KeeperNut{index}')
        hardware.append(screw_spec(name, seat, axis, 'pan', ('Part011', 'ID5EHKeeper')))
    changed = {'Part011': check_solid(yoke, '07 pitch yoke'),
               'ID5EHKeeper': check_solid(keeper, 'ID5 connector guard')}
    doc.ID5EHKeeper.Label = 'ID5 connector guard · two M3 keeper screws and two XL430 case screws'
    return changed, hardware


def c3_clip(x, y, board_edge):
    reach = board_edge + (1.8 if board_edge > x else -1.8)
    xmin, xmax = sorted((x, reach))
    arm = box(xmin, xmax, y-2.6, y+2.6, C3_BOARD_TOP, -67.3)
    head_space = cylinder(3.05, 2., (x, y, C3_SCREW_SEAT))
    foot = cylinder(3.45, C3_SCREW_SEAT-C3_CLIP_BOTTOM, (x, y, C3_CLIP_BOTTOM))
    return foot.fuse(arm.cut(head_space)).cut(cylinder(1.7, 4., (x, y, C3_CLIP_BOTTOM-.1)))


def c3_carrier(doc):
    tray = detached_shape(doc.Part071)
    group = doc.Part071.getParentGeoFeatureGroup()
    clips, hardware, nuts = {}, [], []
    for index, (x, y, edge, hole_x, hole_y) in enumerate(C3_CLAMPS):
        leg = cylinder(3.45, C3_CLIP_BOTTOM-C3_NUT_TOP, (x, y, C3_NUT_TOP))
        xmin, xmax = sorted((x, hole_x))
        bridge = box(xmin, xmax, y-2.4, y+2.4, C3_NUT_TOP-1.20, -71.04)
        socket_well = cylinder(4.85, 5., (x, y, C3_NUT_TOP-5.))
        shank = cylinder(1.7, 3.45, (x, y, C3_NUT_TOP-.1))
        tray = tray.fuse([leg, bridge]).cut([socket_well, shank])
        # The old A1 PCB drill stays the same. These slip-fit pins only locate it.
        pilot_seat = cylinder(1.5, 1., (hole_x, hole_y, -72.))
        pilot = cylinder(.90, 1.52, (hole_x, hole_y, -71.03))
        tray = tray.fuse([pilot_seat, pilot])
        name = f'C3Clamp{index}'
        clip = check_solid(c3_clip(x, y, edge), name)
        add_part(doc, group, name, 'C3 printed edge clamp', clip.copy(), 'fixed')
        clips[name] = clip
        screw_name, nut_name = f'c3Bolt{index}', f'c3Nut{index}'
        seat, axis = (x, y, C3_SCREW_SEAT), (0, 0, -1)
        add_part(doc, group, screw_name, 'M3 × 8 C3 edge clamp screw', socket_screw(3, M3_LENGTH, seat, axis), 'fixed')
        nut_seat = (x, y, C3_NUT_BOTTOM)
        n = nut(3, nut_seat).cut(cylinder(1.5, M3_NUT_HEIGHT, nut_seat))
        add_part(doc, group, nut_name, 'M3 C3 edge clamp hex nut', n, 'fixed')
        hardware.append(screw_spec(screw_name, seat, axis, 'fixed', (name, 'Part071')))
        nuts.append({'id': nut_name, 'type': 'nut', 'size': 3, 'seat': list(nut_seat),
                     'axis': [0, 0, 1], 'motion': 'fixed'})
    return {'Part071': check_solid(tray, 'C3 carrier'), **clips}, hardware, nuts


def build(source, output, folder, hardware_spec=B19_HARDWARE):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate CAD output')
    reference = App.openDocument(str(B16_CAD.resolve()))
    unpocketed = detached_shape(reference.Part011)
    App.closeDocument(reference.Name)
    doc = App.openDocument(str(source.resolve()))
    try:
        guard_parts, guard_hardware = id5_keeper(doc, unpocketed)
        c3_parts, c3_hardware, c3_nuts = c3_carrier(doc)
        changed = {**guard_parts, **c3_parts}
        names = {'Part011': '07_yoke-B21', 'ID5EHKeeper': 'ID5-keeper-B21',
                 'Part071': '27_c3_carrier-B21', 'C3Clamp0': '51_c3_clamp_left-B21',
                 'C3Clamp1': '51_c3_clamp_right-B21'}
        folder.mkdir(parents=True, exist_ok=True)
        for name, shape in changed.items():
            direction = 'y+' if name == 'Part011' else 'z-' if name.startswith('C3Clamp') else None
            print_mesh(shape, folder / (names[name]+'.stl'), direction)
            if name == 'Part011':
                # Model the tap-major envelope in the fitted assembly; keep the 2.6 mm print pilots.
                taps = [cylinder(1.52, 4.6, (SCREW_X, 14.18, z), (0, 1, 0)) for z in SCREW_HEIGHTS]
                shape = check_solid(shape.cut(taps), 'tapped 07 pitch yoke')
            replace(doc.getObject(name), shape)
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.Label = 'R5 B21 · M3 keeper and C3 board clamp mounts'
        doc.recompute()
        doc.saveAs(str(output.resolve()))
        spec = {item['name']: item for item in json.loads(hardware_spec.read_text())}
        spec.update({item['name']: item for item in (*guard_hardware, *c3_hardware)})
        (folder/'hardware-spec.json').write_text(json.dumps(list(spec.values()), indent=2)+'\n')
        (folder/'hardware-rows.json').write_text(json.dumps(c3_nuts, indent=2)+'\n')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=B20_CAD)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--print', type=Path, required=True, dest='folder')
    parser.add_argument('--hardware-spec', type=Path, default=B19_HARDWARE)
    build(**vars(parser.parse_args()))
