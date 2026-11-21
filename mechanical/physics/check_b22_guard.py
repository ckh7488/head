"""Check the fitted B22 guard's hardware, tool paths and touch clearance."""

from argparse import ArgumentParser
from hashlib import sha256
from itertools import combinations, product
from pathlib import Path
import json

import FreeCAD as App
import numpy as np
import Part
import trimesh as tr

from check_head import AXES_BY_MOTION, pose, rotation
from export_cad import world_shape
from primitives import box, cylinder


PIVOT = (0., 0., 112.)
PITCH_LIMITS = (-17.2, 7.15)
LOCAL = ((), np.arange(-8., 8.01, 2.), np.arange(-20., 20.01, 5.),
         np.arange(-1., 92., 5.), np.arange(0., 11.51, .5))
SHELLS = {'Part073', 'Part074', 'Jaw_30_moving_jaw'}
PANELS = {'GuardFront', 'GuardLeft', 'GuardRight', 'GuardRearTop', 'GuardRearBottom', 'GuardRoof'}
Z_AXIS = (0., 0., 1.)
TOLERANCE = .00005


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def offset(center, direction, distance):
    return np.asarray(center, dtype=float) + distance*np.asarray(direction, dtype=float)


def volume(left, right):
    if not left.BoundBox.intersect(right.BoundBox):
        return 0.
    return max(0., float(left.common(right).Volume))


def fittings(doc):
    return {obj.Name: world_shape(obj) for obj in doc.Objects
            if obj.Name.startswith('Guard') and obj.TypeId == 'Part::Feature'}


def fixed_hardware(parts, metadata):
    collisions = [[a, b, overlap] for (a, one), (b, two) in combinations(parts.items(), 2)
                  if (overlap := volume(one, two)) > TOLERANCE]
    paths = []
    for row in metadata['fasteners']:
        name, seat, shaft = (row[key] for key in ('id', 'seat_mm', 'axis'))
        own = (name+'Screw', name+'Nut')
        other = {key: shape for key, shape in parts.items() if key not in own}
        entry = offset(seat, shaft, -3.)
        driver = cylinder(1.49, 32., tuple(entry), tuple(-np.asarray(shaft)))
        grip = offset(seat, shaft, row['grip_mm']+.10)
        head = cylinder(5.45, 2.20, tuple(grip), tuple(shaft))
        axis = np.asarray(shaft)
        conflicts = lambda tool: [key for key, shape in other.items() if volume(tool, shape) > TOLERANCE]
        candidates = []
        directions = [np.eye(3)[j]*sign for j in np.flatnonzero(axis == 0.) for sign in (-1., 1.)]
        for radial in directions:
            cross = np.cross(axis, radial)
            points = [App.Vector(*(grip + radial*a + cross*b))
                      for a, b in ((4., -2.5), (51., -2.5), (51., 2.5), (4., 2.5))]
            handle = Part.Face(Part.makePolygon(points+points[:1])).extrude(App.Vector(*(axis*2.2)))
            # Include radial approach into the open end of the wrench.
            approach = head.fuse([head.translated(App.Vector(*(radial*step))) for step in (2., 4., 6.)])
            blockers = sorted(set(conflicts(handle)+conflicts(approach)))
            candidates.append((blockers, radial.tolist()))
            if not blockers:
                break
        hits, access = min(candidates, key=lambda result: len(result[0]))
        paths.append(dict(id=name, hex_blockers=conflicts(driver), spanner_blockers=hits, spanner_direction=access))
    passed = not collisions and all(not row['hex_blockers'] and not row['spanner_blockers'] for row in paths)
    return dict(passed=passed, seating_overlaps=collisions, tools=paths)


def fixed_assembly_clearance(doc, layout, guard):
    occupied = []
    for name, motion in layout['world_motion'].items():
        obj = doc.getObject(name)
        if motion not in ('fixed', 'hatch') or not obj or obj.TypeId != 'Part::Feature':
            continue
        shape = world_shape(obj)
        for key, fitting in guard.items():
            if (overlap := volume(fitting, shape)) > TOLERANCE:
                occupied.append([key, name, overlap])
    return occupied


def rectangle(x0, x1, y0, y1, z0, z1):
    return box(x0, x1, y0, y1, z0, z1)


def panel_motion(parts):
    blank = {name: shape for name, shape in parts.items()
             if name not in ('GuardRoof', 'GuardRoofStopTab', 'GuardRoofStopTabNut', 'GuardRoofStopTabScrew')}
    roof = rectangle(-149.6, 149.6, -150., 450., 262., 265.)
    roof_obstructions = [key for key, shape in blank.items() if volume(roof, shape) > TOLERANCE]
    obstacles = {name: shape for name, shape in blank.items() if name not in ('GuardRearTop', 'GuardRearBottom')
                 and not name.startswith(('GuardRoofStopBracket', 'GuardSeam'))}
    rear = rectangle(-146.7, 146.7, 147., 150., -83., 590.)
    rear_obstructions = [key for key, shape in obstacles.items() if volume(rear, shape) > TOLERANCE]
    for side, x in (('Left', -75.), ('Right', 75.)):
        # Both clips are drilled onto loose panels; the outside join is fitted last.
        for stage, seat_height in (('Bottom', -72.5), ('Top', -57.5)):
            sweep = rectangle(x-9., x+9., 150., 165., seat_height, 590.)
            retain = () if stage == 'Bottom' else (f'GuardSeam{side}Bottom',)
            fixtures = {key: shape for key, shape in obstacles.items() if key not in retain}
            rear_obstructions.extend(key for key, shape in fixtures.items() if volume(sweep, shape) > TOLERANCE)

    up = parts['GuardRoof'].translated(App.Vector(0., 0., .9))
    out = parts['GuardRoof'].translated(App.Vector(0., .9, 0.))
    rear_lift = parts['GuardRearTop'].translated(App.Vector(0., 0., .1))
    front = parts['GuardRoof'].translated(App.Vector(0., -.1, 0.))
    witness = {'roof_lift': [key for key, shape in parts.items() if 'GuardRoof' in key and
                             key != 'GuardRoof' and volume(up, shape) > TOLERANCE],
               'roof_rear_withdrawal': [key for key, shape in parts.items()
                                        if 'GuardRoofStopTab' in key and volume(out, shape) > TOLERANCE],
               'roof_front_sliding': [key for key, shape in parts.items()
                                      if 'GuardRoofFront' in key and volume(front, shape) > TOLERANCE],
               'rear_panel_lift': volume(rear_lift, parts['GuardRoof'])}
    retained = all(witness.values())
    return dict(passed=not roof_obstructions and not rear_obstructions and retained,
                positive_retention=retained, roof_slide_obstructions=roof_obstructions,
                rear_insertion_obstructions=rear_obstructions, retention_witness=witness)


def opaque_camera_check(doc, guard):
    lens = world_shape(doc.Part068).BoundBox
    eye = np.array([(lens.XMin+lens.XMax)*.5, lens.YMin, (lens.ZMin+lens.ZMax)*.5, 1.])
    opaque = {key: shape.BoundBox for key, shape in guard.items() if key not in PANELS}
    yaw = [rotation(i, Z_AXIS, (0., 0., 0.)) for i in np.linspace(-60., 60., 241)]
    joins = []
    for q in np.linspace(*PITCH_LIMITS, 51):
        turn = rotation(q, (1., 0., 0.), PIVOT)
        matrices = np.asarray(yaw) @ turn
        eyes = (matrices @ eye)[:, :3]
        rays = -matrices[:, :3, 1]
        for name, bb in opaque.items():
            lo = np.array([bb.XMin, bb.YMin, bb.ZMin])
            hi = np.array([bb.XMax, bb.YMax, bb.ZMax])
            # Expansion covers between-sample pose motion at the enclosure boundary.
            with np.errstate(divide='ignore', invalid='ignore'):
                lower, upper = ((edge-eyes)/rays for edge in (lo-2., hi+2.))
            enters = np.maximum(0., np.nanmax(np.minimum(lower, upper), axis=1))
            leaves = np.minimum(260., np.nanmin(np.maximum(lower, upper), axis=1))
            if np.any(enters < leaves):
                joins.append([name, float(q), np.flatnonzero(enters < leaves).tolist()])
    return dict(passed=not joins, yaw_deg=[-60., 60.], pitch_deg=PITCH_LIMITS,
                samples=51*len(yaw), opaque_intersections=joins,
                scope='Padded straight center-ray geometry; clear-sheet optical reflections require bench inspection.')


def swept_room(layout, folder):
    rows = {}
    coarse_pitch = np.linspace(*PITCH_LIMITS, 51)
    for name, motion in layout['world_motion'].items():
        if motion in ('fixed', 'hatch'):
            continue
        mesh = tr.load_mesh(folder/'world'/f'{name}.stl', process=name in SHELLS)
        if not len(mesh.faces):
            continue
        vertices = mesh.convex_hull.vertices if name in SHELLS else tr.bounds.corners(mesh.bounds)
        axes = tuple(i for i in AXES_BY_MOTION[motion] if i != 0)
        local = []
        for values in product(*(LOCAL[i] for i in axes)):
            angles = np.zeros(5)
            angles[list(axes)] = values
            local.append(angles)
        points = []
        for q in coarse_pitch:
            frame = rotation(q, (1., 0., 0.), PIVOT)
            for angles in local:
                args = angles.copy()
                args[0] = q
                points.append(tr.transform_points(vertices, frame@pose(motion, args, layout)))
        all_points = np.vstack(points)
        margin = 4. if axes else 2.5 if motion == 'pitch_link' else 1.
        radius = np.linalg.norm(all_points[:, :2], axis=1).max()+margin
        low = all_points[:, 2].min()-margin
        high = all_points[:, 2].max()+margin
        # Chocks reach no higher than z=-75 and occupy only radii >=93.6 mm.
        nearest_chock = np.hypot(max(0., low+75.), max(0., 93.6-radius))
        rows[name] = {'side_clearance_mm': float(147.-radius), 'roof_clearance_mm': float(262.-high),
                      'floor_clearance_mm': float(low+83.), 'chock_clearance_mm': float(nearest_chock)}
    return rows


def touch_bound(meta, room):
    # Simply supported PMMA strips, E=2500 MPa, using the 294 mm inner span.
    # The roof slots leave 6 mm nominal continuous webs between vent columns.
    inertia = lambda width: width*3.**3/12.
    deflect = lambda width, span=294.: span**3/(48.*2500.*inertia(width))
    wall, roof = deflect(10.)+.60, deflect(5.8)+.40
    seam_span = max(np.diff([-132., *meta['rear_seam_clips']['join_x_mm'], 132.]))
    seam_overlap = 3. - (deflect(10., seam_span)+.60)
    residual = {name: min(row['side_clearance_mm']-wall, row['roof_clearance_mm']-roof,
                          row['floor_clearance_mm']-.6, row['chock_clearance_mm']-.6)
                for name, row in room.items()}
    critical = min(residual, key=residual.get)
    return dict(wall_deflection_mm=wall, roof_deflection_mm=roof, rear_seam_overlap_after_touch_mm=seam_overlap,
                min_rigid_clearance_mm=min(min(row.values()) for row in room.values()),
                min_leftover_clearance_after_touch_mm=residual[critical], nearest_actor=critical,
                maximum_opening_mm=max(max(port['aperture_mm'] for port in meta['rear_cable_ports']),
                                       meta['roof_vents']['width_mm']))


def run(guard, cad, output):
    metadata = json.loads(guard.with_suffix('.json').read_bytes())
    layout = json.loads((cad/'cad_parts.json').read_bytes())
    if metadata['source_sha256'] != layout['source_sha256'] or metadata['guard_cad_sha256'] != sha(guard):
        raise ValueError('The guard and head motion input digests differ')
    doc = App.openDocument(str(guard.resolve()))
    try:
        parts = fittings(doc)
        hard = fixed_hardware(parts, metadata)
        assembly = panel_motion(parts)
        optic = opaque_camera_check(doc, parts)
        fixed = fixed_assembly_clearance(doc, layout, parts)
    finally:
        App.closeDocument(doc.Name)
    room = swept_room(layout, cad)
    touch = touch_bound(metadata, room)
    ok = hard['passed'] and assembly['passed'] and optic['passed'] and not fixed \
        and touch['min_rigid_clearance_mm'] >= 25. and touch['min_leftover_clearance_after_touch_mm'] >= 10. \
        and touch['maximum_opening_mm'] <= 6. and touch['rear_seam_overlap_after_touch_mm'] > 0.
    report = dict(head_cad_sha256=layout['source_sha256'], guard_cad_sha256=sha(guard),
                  status='pass' if ok else 'fail', touch_force_N=1.,
                  max_opening_mm=touch['maximum_opening_mm'],
                  min_leftover_clearance_after_touch_mm=touch['min_leftover_clearance_after_touch_mm'],
                  cover_and_roof_positively_retained=assembly['positive_retention'],
                  fastener_and_tool_paths_pass=hard['passed'], optics=optic,
                  assembly=assembly, hardware=hard, clearance=touch, moving_clearance=room,
                  fixed_assembly_overlaps=fixed,
                  scope='Rigid CAD, tool/cover paths and conservative static 1 N PMMA deflection calculation.')
    output.write_text(json.dumps(report, indent=2)+'\n')
    return ok


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('guard', type=Path)
    parser.add_argument('cad', type=Path)
    parser.add_argument('output', type=Path)
    raise SystemExit(0 if run(**vars(parser.parse_args())) else 1)
