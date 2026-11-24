"""Export the B25 Ø8 frame hubs and D-flat clamp in their original print orientations."""

from argparse import ArgumentParser
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import trimesh

from build_b25_large_bearing_variants import PROJECT, checked_stl, radial_section, source_mesh, write_entry


FRAME = '09_head_frame-B25.stl'
CLAMP = '08_pitch_horn_to_8mm_clamp-B24.stl'
SIZES = (8.10, 8.15, 8.20, 8.25, 8.30)
FRAME_CENTER = (21.05, -13.250995)
CLAMP_CENTER = (0., 0.)
PIN_X = (-59.305, 61.695)
FRAME_PROBES = (-62., -57., 59.5, 64.)
CLAMP_PROBES = (4., 6., 7.8)


def within(values, target):
    return np.isclose(values, target, rtol=0., atol=.00004)


def resized(vertices, radius, frame):
    axes, center = ((1, 2), FRAME_CENTER) if frame else ((0, 1), CLAMP_CENTER)
    radial = vertices[:, axes] - center
    rings = np.linalg.norm(radial, axis=1)
    points = vertices.copy()
    source_groups = ((4.12, 1236),) if frame else ((4.12, 205), (4.11, 152))
    for old_radius, count in source_groups:
        ring = within(rings, old_radius)
        if np.count_nonzero(ring) != count:
            raise ValueError('The source shaft bore tessellation changed')
        target = radius + (old_radius - 4.12)
        points[np.ix_(ring, axes)] = radial[ring] * (target / rings[ring, None]) + center
        if frame:
            # Preserve the transverse drill's XZ coordinates, including at the shared bore seam.
            for pin_x in PIN_X:
                pin = np.linalg.norm(vertices[:, (0, 2)] - [pin_x, center[1]], axis=1)
                seam = ring & within(pin, 1.55)
                if np.count_nonzero(seam) != 363:
                    raise ValueError('The hub and cross-pin bore intersection changed')
                points[seam, 2] = vertices[seam, 2]
                points[seam, 1] = center[0] + np.copysign(
                    np.sqrt(target**2 - radial[seam, 1]**2), radial[seam, 0])
        else:
            # Keep both flat planes and the stepped transition at their existing X coordinates.
            x, _, z = vertices.T
            step = within(z, 3.70) & (x >= -3.151) & (x <= -3.079)
            seam = ring & (within(x, -3.08) | within(x, -3.15) | step)
            if np.count_nonzero(seam) != (12 if old_radius == 4.12 else 4):
                raise ValueError('The clamp D-flat seam changed')
            points[seam, 0] = vertices[seam, 0]
            points[seam, 1] = np.copysign(np.sqrt(target**2 - points[seam, 0]**2), vertices[seam, 1])
        if not within(np.linalg.norm(points[np.ix_(ring, axes)] - center, axis=1), target).all():
            raise ValueError('The circular bore left its target radius')
    return points


def wall_probes(stock, frame, line_width):
    if frame:
        axis, center, probes = 0, FRAME_CENTER, FRAME_PROBES
        angles = np.arange(720) * np.pi / 360. + .001
    else:
        axis, center, probes = 2, CLAMP_CENTER, CLAMP_PROBES
        angles = np.linspace(-np.pi/3, np.pi/3, 241) + .001
    stations = []
    for probe in probes:
        reference = radial_section(stock, axis, probe, center, angles)
        # The original openings and tangencies at the left frame hub interrupt some rays.
        solid = (np.abs(reference[:, 0]-4.12) < .025) & np.isfinite(reference[:, 1])
        solid &= reference[:, 1] >= reference[:, 0] + line_width
        if not solid.any():
            raise ValueError('No bearing support wall was found in the source mesh')
        stations.append((probe, angles[solid], reference[solid, 1]-reference[solid, 0]))
    return axis, center, stations


def measured_wall(mesh, radius, probes, line_width):
    axis, center, stations = probes
    wall = []
    for station, angles, original in stations:
        radial = radial_section(mesh, axis, station, center, angles)
        if np.any(np.abs(radial[:, 0]-radius) >= .025) or not np.isfinite(radial[:, 1]).all():
            raise ValueError('The shaft bore has lost source wall support')
        measured = radial[:, 1] - radial[:, 0]
        if np.any(measured < line_width) or np.any(measured < original + 4.12 - radius - .01):
            raise ValueError('The shaft bore thinned the supported boss wall')
        wall.append(float(measured.min()))
    return round(min(wall), 3)


def build(output, project):
    if output.resolve() == project.resolve():
        raise ValueError('Choose a ZIP output separate from the original P2S project')
    report = {'source_project': project.name, 'source_project_sha256': sha256(project.read_bytes()).hexdigest(),
              'units': 'mm', 'stl_origin': 'Source orientation with lowest Z at the build plate', 'parts': {}}
    archive = BytesIO()
    with ZipFile(project) as source, ZipFile(archive, 'w') as destination:
        for part, name in (('08', CLAMP), ('09', FRAME)):
            frame = name == FRAME
            vertices, faces, info = source_mesh(source, name)
            gauge = 'P8' if frame else 'V8'
            line_width = float(info['p2s_settings']['outer_wall_line_width'])
            probes = wall_probes(trimesh.Trimesh(vertices, faces, process=False), frame, line_width)
            info.update(fit_gauge=gauge, stock_min_sampled_boss_wall_mm=round(min(wall.min() for _, _, wall in probes[2]), 3),
                        wall_samples_per_section=[len(angles) for _, angles, _ in probes[2]])
            if frame:
                info.update(bore_axis='X (horizontal)', stock_diameter_mm=8.24, boss_diameter_mm=12.80,
                            boss_depth_mm=[8.67, 8.50], boss_axial_sections_x_mm=FRAME_PROBES,
                            cross_pins_axis='Y (horizontal)', cross_pins_diameter_mm=3.10,
                            cross_pin_boss_axial_ligament_mm=2.70,
                            bore_center_yz_from_bed_mm=[FRAME_CENTER[0], FRAME_CENTER[1]-vertices[:, 2].min()])
            else:
                info.update(bore_axis='Z (vertical)', stock_diameter_mm=8.24, boss_diameter_mm=13.10,
                            bore_depth_mm=9.80, d_flat_heights_from_axis_mm=[3.08, 3.15],
                            upper_relief_arc_offset_from_main_diameter_mm=-.02,
                            drive_screw_pilot_mm=3., d_flat_min_web_to_screw_seat_mm=2.42,
                            boss_axial_sections_z_from_bed_mm=[z-vertices[:, 2].min() for z in CLAMP_PROBES],
                            boss_wall_sampled_arc_deg=[-60., 60.])
            info['variants'] = []
            for diameter in SIZES:
                radius = diameter / 2.
                points = resized(vertices, radius, frame)
                mesh, stl = checked_stl(vertices, points, faces)
                min_wall = measured_wall(mesh, radius, probes, line_width)
                stem = '09_head-frame_shaft-bore' if frame else '08_pitch-horn-clamp_D-bore'
                file = f'{gauge}/{stem}_ID{diameter:.2f}mm.stl'
                write_entry(destination, file, stl)
                info['variants'].append(dict(file=file, bore_diameter_mm=diameter, sha256=sha256(stl).hexdigest(),
                                             min_sampled_boss_wall_mm=min_wall))
            report['parts'][part] = info
        data = json.dumps(report, indent=2)+'\n'
        write_entry(destination, 'shaft-fit.json', data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(archive.getbuffer())
    output.with_name('shaft-fit.json').write_text(data, encoding='utf-8')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--project', type=Path, default=PROJECT)
    args = parser.parse_args()
    build(args.output, args.project)
