"""Build the B21 eye and blink linkage pivots from the B20 CAD."""

from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass
import json
from math import cos, radians, sin
from pathlib import Path
from tempfile import TemporaryDirectory

import FreeCAD as App
import Mesh
import numpy as np
import Part
import trimesh

from build_b19_review_fixes import add_part, hardware_spec, replace, screw_shape, world_shape
from export_cad import tessellate, world_mesh
from primitives import cylinder, print_mesh


SOURCE = Path(__file__).resolve().parent / 'revisions/b20/R5-B20-Assembly.FCStd'
FINISHED_BORE = 2.09
PILOT_BORE = 1.92
RETAINER_LENGTH = 3.
PIN_FLOAT = .20
RETIRED_CAD = ('EyeYawTieHorn', 'EyeYawTieHornNut', 'EyeYawTieHornWasher')


@dataclass(frozen=True)
class Pivot:
    name: str
    centre: tuple
    axis: tuple
    first: tuple
    second: tuple
    motion: str
    legacy: tuple
    pin_length: float = 6.

    def point(self, station):
        return tuple(p+station*a for p, a in zip(self.centre, self.axis, strict=True))

    @property
    def stop(self):
        return self.second[-1]-self.pin_length-PIN_FLOAT


UPPER = (0., -17.569281610086414, 144.46606791561703)
LOWER = (0., -32.56928161008641, 109.46606791561702)
BLINK_SERVO = (0., -9.386658546366338, 163.1604400264209)
BLINK_DRIVE = (0., -19.386658546366338, 147.1604400264209)
FORWARD, REVERSE, DOWN = (1, 0, 0), (-1, 0, 0), (0, 0, -1)
PIVOTS = (
    Pivot('BlinkPivotServo', BLINK_SERVO, FORWARD, ('Part047', 3.42, 4.45), ('Part056', 4.55, 9.15),
          'blink_drive_link', ('middleServo0', 'middleNut0', 'middleWasher0')),
    Pivot('BlinkPivotDrive', BLINK_DRIVE, FORWARD, ('Part056', 4.55, 7.15), ('Part054', 7.65, 10.25),
          'blink_shaft_crank', ('centerLink0', 'linkNutPos0', 'linkWasherPos0')),
    Pivot('BlinkPivotUpperL', UPPER, FORWARD, ('Part053', -53.75, -50.90), ('Part057', -50.55, -47.95),
          'blink_lid_link', ('centerLink1', 'linkNutPos1', 'linkWasherPos1')),
    Pivot('BlinkPivotUpperR', UPPER, REVERSE, ('Part055', -53.75, -51.15), ('Part060', -50.55, -47.95),
          'blink_lid_link', ('rightLink0', 'linkNutNeg0', 'linkWasherNeg0')),
    Pivot('BlinkPivotLowerL', LOWER, FORWARD, ('Part078', -53.50, -50.90), ('Part057', -50.55, -47.95),
          'blink_lid_link', ('centerLower0', 'linkLeftLowerNut0', 'linkWasherPos2')),
    Pivot('BlinkPivotLowerR', LOWER, REVERSE, ('Part079', -53.50, -50.90), ('Part060', -50.55, -47.95),
          'blink_lid_link', ('rightLower0', 'linkRightLowerNut0', 'linkWasherNeg1')),
    Pivot('EyeYawDrivePivot', (-5.8, -22., 0.), DOWN, ('Part037', -117.45, -114.55),
          ('Part040', -114.25, -111.85), 'look_horn', RETIRED_CAD, 5.),
)
PRINTS = {
    'Part037': ('15_eye_yaw_offset_tie_bar', None), 'Part040': ('16_eye_yaw_horn_13p5_mm', 'z-'),
    'Part044': ('18_eye_pitch_link_58p5mm', 'x+'), 'Part047': ('19_blink_servo_horn', 'x+'),
    'Part053': ('21_blink_shaft_crank_1', 'x+'), 'Part054': ('21_blink_shaft_crank_2', 'x+'),
    'Part055': ('21_blink_shaft_crank_3', 'x+'), 'Part056': ('22_blink_drive_link', 'x+'),
    'Part057': ('23_left_short_lid_link', 'x+'), 'Part060': ('23_right_short_lid_link', 'x+'),
    'Part078': ('32_left_eyelid', None), 'Part079': ('32_right_eyelid', None),
}


def round_span(radius, start, end, centre, axis):
    point = tuple(c+start*a for c, a in zip(centre, axis, strict=True))
    return cylinder(radius, end-start, point, axis)


def edits(finished):
    adds, cuts = defaultdict(list), defaultdict(list)
    bearing = (FINISHED_BORE if finished else PILOT_BORE)/2
    for joint in PIVOTS:
        first, low, first_end = joint.first
        second, second_start, high = joint.second
        stop_front = low if joint.axis == DOWN else min(low, joint.stop-.75)

        def tool(radius, start, end):
            return round_span(radius, start, end, joint.centre, joint.axis)

        adds[first].append(tool(1.4, low, first_end))
        if stop_front < low:
            adds[first].append(tool(1.92, stop_front, low+.18))
        cuts[first].extend((tool(.775, stop_front-.06, joint.stop+.01),
                            tool(bearing, joint.stop, first_end+.1)))

        adds[second].extend((tool(1.4, second_start, high), tool(2.50, high-.20, high+RETAINER_LENGTH)))
        cuts[second].extend((tool(bearing, second_start-.1, high+.01),
                             tool(1.525 if finished else 1.25, high, high+RETAINER_LENGTH+.06)))
    for name, axis, start, end, centres in (
        ('Part037', (0, 0, 1), 114.55, 117.45, [(-34., -25.5, 0.), (34., -25.5, 0.)]),
        ('Part044', FORWARD, 61.55, 64.15, [(0., -29., 119.), (0., 20., 151.)]),
    ):
        for centre in centres:
            adds[name].append(round_span(1.4, start, end, centre, axis))
            cuts[name].append(round_span(bearing, start-.1, end+.1, centre, axis))
    return adds, cuts


def from_mesh(mesh):
    points, facets = mesh.Topology
    return trimesh.Trimesh(np.array([tuple(p) for p in points]), np.asarray(facets))


def change_shape(shape, adds, cuts):
    shape = shape.fuse(adds).cut(cuts).removeSplitter()
    if not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError('A pivot modification did not form one solid')
    return shape


def change_mesh(shape, adds, cuts):
    fused = trimesh.boolean.union([shape, *(from_mesh(tessellate(s)) for s in adds)], engine='manifold')
    result = trimesh.boolean.difference([fused, *(from_mesh(tessellate(s)) for s in cuts)], engine='manifold')
    if not result.is_volume or result.body_count != 1:
        raise ValueError('A pivot modification did not form one closed lid mesh')
    return result


def build_geometry(doc, prints):
    with TemporaryDirectory() as scratch:
        path = Path(scratch)/'lid.stl'
        finished_adds, finished_cuts = edits(True)
        pilot_adds, pilot_cuts = edits(False)
        for name, (stem, orientation) in PRINTS.items():
            obj = doc.getObject(name)
            output = prints/f'{stem}-B21.stl'
            if obj.TypeId == 'Mesh::Feature':
                initial = from_mesh(world_mesh(obj))
                printable = change_mesh(initial, pilot_adds[name], pilot_cuts[name])
                printable.apply_translation(-printable.bounds.mean(axis=0)*[1, 1, 0]-[0, 0, printable.bounds[0, 2]])
                printable.export(output)
                fitted = change_mesh(initial, finished_adds[name], finished_cuts[name])
                fitted.apply_transform(np.array(obj.getGlobalPlacement().inverse().toMatrix().A).reshape(4, 4))
                fitted.export(path)
                obj.Mesh = Mesh.Mesh(str(path))
            else:
                initial = world_shape(obj)
                print_mesh(change_shape(initial, pilot_adds[name], pilot_cuts[name]), output, orientation)
                replace(obj, change_shape(initial, finished_adds[name], finished_cuts[name]))


def index_blink_flange(doc):
    servo = doc.Part045
    solids = world_shape(servo).Solids
    flange = [solid for solid in solids if solid.BoundBox.XMax > 1.19]
    if len(flange) != 1:
        raise ValueError('The blink servo flange is not identifiable in the vendor shape')
    flange[0].rotate(App.Vector(0., -14., 170.), App.Vector(1, 0, 0), 34.)
    replace(servo, Part.Compound(solids))
    phase = radians(34.)
    yz = [(-14.-6*sin(phase), 170.+6*cos(phase)), (-14.+6*cos(phase), 170.+6*sin(phase))]
    seats = {f'BlinkHornScrew{i}': (4.3, y, z) for i, (y, z) in enumerate(yz)}
    for name, seat in seats.items():
        replace(doc.getObject(name), screw_shape(2., 6., seat, REVERSE))
    return seats


def hardware(doc):
    group = doc.Part019.getParentGeoFeatureGroup()
    for name in RETIRED_CAD:
        doc.removeObject(name)
    spec = [item for item in hardware_spec() if item['name'] not in RETIRED_CAD]
    seats = index_blink_flange(doc)
    for row in spec:
        if row['name'] in seats:
            _, y, z = seats[row['name']]
            for shape in row['shapes']:
                shape[3][1:] = [y, z]
    for joint in PIVOTS:
        pin_id, cap_id = joint.name, joint.name+'Retainer'
        high = joint.second[-1]
        hosts = [joint.first[0], joint.second[0], pin_id, cap_id]
        for name, label, radius, length, at, details in (
            (pin_id, f'Ø2 × {joint.pin_length:g} ground pivot', 1., joint.pin_length, joint.stop+PIN_FLOAT/2,
             {'kind': 'pin'}),
            (cap_id, 'M3 × 3 flat-point socket set screw', 1.5, RETAINER_LENGTH, high,
             {'kind': 'set_screw', 'key_af_mm': 1.5}),
        ):
            start = joint.point(at)
            add_part(doc, group, name, label, cylinder(radius, length, start, joint.axis), joint.motion)
            spec.append({'name': name, 'motion': joint.motion, 'skip': hosts, **details,
                         'shapes': [['cyl', radius, length, start, joint.axis]]})
    return spec


def build(source, output, prints):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate output assembly')
    doc = App.openDocument(str(source.resolve()))
    try:
        prints.mkdir(parents=True, exist_ok=True)
        build_geometry(doc, prints)
        spec = hardware(doc)
        doc.Label = 'R5 B21 · smooth linkage pivots'
        doc.recompute()
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(output.resolve()))
        (prints/'link-hardware.json').write_text(json.dumps(spec, indent=2)+'\n')
        (prints/'link-pivots.json').write_text(json.dumps({
            'finished_bore_mm': [2.08, 2.10], 'pilot_bore_mm': PILOT_BORE, 'axial_float_mm': PIN_FLOAT,
            'pivots': [vars(joint) for joint in PIVOTS],
        }, indent=2)+'\n')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prints', type=Path, required=True)
    build(**vars(parser.parse_args()))
