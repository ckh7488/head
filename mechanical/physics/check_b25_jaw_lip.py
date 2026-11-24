"""Measure the B25 part 37 relief lip and the independent M3 mounting walls."""

from argparse import ArgumentParser
import json
from pathlib import Path
import re

import FreeCAD as App
import numpy as np

from check_b25_jaw_retention import digest, geometry


STAY = 'Jaw_37_right_jaw_bearing_stay'
LIP_SECTIONS = (
    ((46., -8., 104.), 0),
    ((46., -11.5, 105.), 0),
    ((48.5, -7.25, 96.), 2),
)
BED_OFFSET = (114.9999962, 200.7989406, -38.4002876)
FILAMENT_FEATURES = {'Inner wall', 'Outer wall', 'Bottom surface', 'Top surface', 'Internal solid infill'}


def relief_sections(stay):
    report = []
    for origin, axis in LIP_SECTIONS:
        hits, _, _ = stay.ray.intersects_location([origin], [np.eye(3)[axis]])
        entry, exit = np.sort(hits[:, axis])[:2]
        center = list(origin)
        center[axis] = (entry + exit) / 2
        report.append({'axis': 'XYZ'[axis], 'center_world_mm': center, 'surface_coordinates_mm': [entry, exit],
                       'thickness_mm': exit - entry})
    return report


def wall_minimum(mesh, x_bounds, insert_diameter=None):
    center = np.array((-8.75, 103.5))
    angles = np.deg2rad(np.arange(0., 360., .25))
    rays = np.c_[np.zeros(len(angles)), np.cos(angles), np.sin(angles)]
    minimum = float('inf')
    for station in np.linspace(*x_bounds, 20):
        start = np.tile([station, *center], (len(angles), 1))
        locations, indices, _ = mesh.ray.intersects_location(start, rays, multiple_hits=True)
        radii = np.linalg.norm(locations[:, 1:] - center, axis=1)
        for lane in range(len(angles)):
            hits = np.sort(radii[indices == lane])
            hits = hits[np.r_[True, np.diff(hits) > .0001]]
            if len(hits) < 2:
                raise ValueError(f'Incomplete M3 wall at X={station:.3f} mm, angle {angles[lane]:.4f} rad')
            inner = hits[0] if insert_diameter is None else insert_diameter / 2
            minimum = min(minimum, hits[1] - inner)
    return {'axis_center_yz_mm': center.tolist(), 'x_station_range_mm': x_bounds, 'station_count': 20,
            'rays_per_station': len(angles), 'minimum_sampled_wall_mm': minimum,
            'wall_with_0p20_mm_outline_loss_mm': minimum - .20, 'insert_diameter_mm': insert_diameter}


def printed_lip(gcode, sections):
    """Locate model extrusion at the narrow lip on the released plate-9 pose."""
    xyz = np.array([item['center_world_mm'] for item in sections])
    witnesses = xyz[:, (2, 1, 0)] * [-1., 1., 1.] + BED_OFFSET
    nearest = np.full(len(witnesses), np.inf)
    evidence = {}
    point = np.zeros(2)
    layer = 0.
    printing = False
    feature = ''
    words = re.compile(r'([XYE])(-?[\d.]+)')
    with gcode.open() as source:
        for line in source:
            if line.startswith('; Z_HEIGHT: '):
                layer = float(line.split()[-1])
            elif line.startswith('; start printing object, unique label id: '):
                printing = True
            elif line.startswith('; stop printing object, unique label id: '):
                printing = False
            elif line.startswith('; FEATURE: '):
                feature = line.removeprefix('; FEATURE: ').strip()
            elif line.startswith(('G0 ', 'G1 ')):
                changes = dict(words.findall(line.split(';', 1)[0]))
                next_point = np.array([float(changes.get(k, last)) for k, last in zip('XY', point)])
                delta = next_point - point
                length_squared = delta @ delta
                if printing and feature in FILAMENT_FEATURES and float(changes.get('E', 0.)) > 0. and length_squared > 0.:
                    for index in np.flatnonzero(abs(witnesses[:, 2] - (layer - .1)) <= .301):
                        xy = witnesses[index, :2]
                        fraction = np.clip((xy-point) @ delta / length_squared, 0., 1.)
                        distance = np.linalg.norm(point + fraction * delta - xy)
                        if distance < nearest[index]:
                            nearest[index] = distance
                            evidence[index] = {'layer_top_mm': layer, 'extrusion_feature': feature,
                                               'xy_path_distance_mm': distance, 'xy_mm': xy.tolist()}
                point = next_point
    if np.any(nearest > .20):
        raise ValueError('One or more clearance lip witnesses have no adjacent model extrusion')
    return {'gcode_sha256': digest(gcode), 'witnesses': [evidence[index] for index in range(len(sections))]}


def check(path, gcode):
    doc = App.openDocument(str(path.resolve()))
    try:
        stay = geometry(doc.getObject(STAY))
        frame = geometry(doc.Part019)
        sections = relief_sections(stay)
        through_hole = wall_minimum(stay, (62.56, 68.99))
        insert = wall_minimum(frame, (71.56, 74.54), 4.6)
        if through_hole['wall_with_0p20_mm_outline_loss_mm'] < 1.2 or insert['wall_with_0p20_mm_outline_loss_mm'] < 1.5:
            raise ValueError('A structural M3 mounting wall lost the required thickness')
        evidence = printed_lip(gcode, sections)
        return {
            'cad_sha256': digest(path), 'part': STAY,
            'relief_lip': {'purpose': 'Residual edge of the yoke-clearance recess',
                           'world_sections': sections, 'plate_9_arachne': evidence},
            'mounting_through_hole': through_hole,
            'frame_insert': insert,
            'bearing': {'center_yz_mm': [-9., 92.], 'axial_seat_x_mm': [40., 44.],
                        'part': 'Jaw_MR104ZZ_jaw_right', 'diameter_mm': 10.15,
                        'separate_from_clearance_lip': True},
        }
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for argument in ('cad', 'gcode', 'output'):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(check(args.cad, args.gcode), indent=2) + '\n')
