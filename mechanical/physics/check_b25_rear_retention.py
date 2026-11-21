"""Check rear skull insertion, tools and retention against the native assembly."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path

import FreeCAD as App
import MeshPart
import numpy as np
import trimesh

from build_b22_fused_skull import solid
from build_b25_rear_retention import (
    FRAME_FACE, LENGTH, NUT_FLATS, POCKET_INNER, POCKET_OUTER, SHELL_FACE, STATIONS, Y, Z,
    mesh_cylinder, nut_channel,
)
from check_b19_assembly import sweep
from export_cad import world_mesh, world_shape


GEOMETRIC_VOLUME = 1e-4
TRAVEL = (0., 68., 0.)


def mesh_for(obj):
    if obj.TypeId == 'Mesh::Feature':
        body = world_mesh(obj)
    else:
        body = MeshPart.meshFromShape(Shape=world_shape(obj), LinearDeflection=.045, AngularDeflection=.12,
                                      Relative=False)
    points, triangles = body.Topology
    if not triangles:
        return None
    return trimesh.Trimesh([tuple(point) for point in points], triangles)


class InstalledHead:
    limit = .05

    def __init__(self, doc):
        self.parts = {obj.Name: obj for obj in doc.Objects if obj.TypeId in ('Part::Feature', 'Mesh::Feature')}
        self.cache = {}

    def mesh(self, name):
        if name not in self.cache:
            self.cache[name] = mesh_for(self.parts[name])
        return self.cache[name]

    def sweep_collisions(self, omitted):
        shell = self.mesh('Part074')
        ranged = shell.bounds[1] + TRAVEL
        actors = []
        for name, obj in self.parts.items():
            if name in omitted:
                continue
            bounds = world_shape(obj).BoundBox if obj.TypeId == 'Part::Feature' else world_mesh(obj).BoundBox
            lo, hi = np.array([bounds.XMin, bounds.YMin, bounds.ZMin]), np.array([bounds.XMax, bounds.YMax, bounds.ZMax])
            if bounds.isValid() and np.all(ranged >= lo) and np.all(shell.bounds[0] <= hi):
                actors.append(name)
        return [{'parts': list(pair), **hit} for pair, hit in sweep(self, ['Part074'], actors, TRAVEL).items()]


def station_checks(doc, world, shell, hand, side, seat):
    frame = world_shape(doc.Part019)
    # Straight socket screw translation plus 0.10 mm radius allowance on shank and head.
    shank = mesh_cylinder(side, 1.6, seat-LENGTH, seat + 25.)
    head = mesh_cylinder(side, 2.88, seat+.000001, seat + 25.)
    driver = mesh_cylinder(side, 1.50, seat+3., seat + 40.)
    screw_path = shank + head
    nut_path = nut_channel(side, POCKET_INNER+.1, POCKET_OUTER-.01, NUT_FLATS+.18, 62.)
    bound = nut_path.BoundBox
    nut_blockers = {}
    for name, obj in world.parts.items():
        if obj.TypeId != 'Part::Feature' or name.startswith('RearSkull'):
            continue
        shape = world_shape(obj)
        if bound.intersect(shape.BoundBox) and (overlap := nut_path.common(shape).Volume) > GEOMETRIC_VOLUME:
            nut_blockers[name] = overlap
    # 15 degree turns in either direction must hit the hex cage before the nut can spin.
    nut = world_shape(doc.getObject('RearSkullNut'+hand))
    interference = []
    for angle in (-15., 15.):
        turned = nut.copy()
        turned.rotate(App.Vector(0., Y, Z), App.Vector(side, 0., 0.), angle)
        interference.append(frame.common(turned).Volume)
    installed_shaft = mesh_cylinder(side, 1.5, seat-LENGTH, seat)
    blocked_with_screw = (shell.translate((0., .75, 0.)) ^ installed_shaft).volume()
    clearance = {
        'screw_to_shell_mm3': (screw_path ^ shell).volume(),
        'driver_to_shell_mm3': (driver ^ shell).volume(),
    }
    # Probe against the other actors, including the frame and stock connector solids.
    # Narrow prefilter avoids re-tessellating remote actors.
    hardware = ('RearSkullScrew'+hand, 'RearSkullNut'+hand, 'Part074')
    lower = (min(side*(seat-LENGTH), side*(seat+40.)), Y-3., Z-3.)
    upper = (max(side*(seat-LENGTH), side*(seat+40.)), Y+3., Z+3.)
    for name, obj in world.parts.items():
        if name in hardware:
            continue
        bounds = world_shape(obj).BoundBox if obj.TypeId == 'Part::Feature' else world_mesh(obj).BoundBox
        lo, hi = (bounds.XMin, bounds.YMin, bounds.ZMin), (bounds.XMax, bounds.YMax, bounds.ZMax)
        if not bounds.isValid() or np.any(np.greater(lo, upper)) or np.any(np.less(hi, lower)):
            continue
        mesh = world.mesh(name)
        if mesh is None:
            continue
        if not mesh.is_volume:
            raise ValueError(f'{name} is in a new tool corridor and needs a closed mesh')
        obstacle = solid(mesh)
        for kind, probe in (('screw', screw_path), ('driver', driver)):
            if (overlap := (probe ^ obstacle).volume()) > GEOMETRIC_VOLUME:
                clearance[f'{kind}_to_{name}_mm3'] = overlap
    full_engagement = POCKET_OUTER-(seat-LENGTH)
    passed = (not nut_blockers and max(clearance.values()) <= GEOMETRIC_VOLUME
              and min(interference) > .2 and blocked_with_screw > .5 and full_engagement >= 2.90)
    return {'status': 'pass' if passed else 'fail', 'nut_entry_obstructions_mm3': nut_blockers,
            'tool_intersections_mm3': clearance, 'nut_antirotation_overlap_mm3_at_15_deg': interference,
            'overlap_if_withdrawn_0.75_mm_with_screw_mm3': blocked_with_screw,
            'screw_through_nut_mm': full_engagement}


def check(source):
    doc = App.openDocument(str(source))
    try:
        world = InstalledHead(doc)
        shell = solid(world.mesh('Part074'))
        stations = {hand.lower(): station_checks(doc, world, shell, hand, side, seat)
                    for hand, side, seat in STATIONS}
        blockers = world.sweep_collisions({'Part074', *(f'RearSkullScrew{hand}' for hand, _, _ in STATIONS)})
        passed = not blockers and all(row['status'] == 'pass' for row in stations.values())
        return {'status': 'pass' if passed else 'fail', 'cad_sha256': sha256(source.read_bytes()).hexdigest(),
                'bolt_radial_reserve_mm': .1, 'hex_driver_reach_mm': 37.,
                'rear_insertion_travel_mm': list(TRAVEL), 'rear_insertion_sample_mm': .5,
                'radial_face_relief_mm': SHELL_FACE-FRAME_FACE, 'stations': stations,
                'rear_insertion_collisions': blockers}
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = check(args.cad)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    raise SystemExit(report['status'] != 'pass')
