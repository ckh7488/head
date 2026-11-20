"""Build B19: key the pitch pins to the head frame and give the blink cranks clamp travel.

B19 changes only purchased parts and adds stock fasteners, so the B16 print plates
and the B18 replacement STLs stay valid:

* Both Ø8 pitch pins get a Ø3 cross hole under the existing Ø3.1 vertical holes of
  the 09 head frame. A Ø3 × 12 steel dowel, set with retaining compound, keys each
  pin to the frame, so pitch torque reaches the head and the pins cannot walk out
  axially. A through bolt does not fit: the 28 skull front sits about 1 mm under the
  frame hubs, where a nut or screw head would have to go.
* The three flats of the Ø4 blink shaft are 0.30 mm deep instead of 0.45 mm, so the
  M3 × 8 crank screws meet the flat with 0.36 mm of head clearance instead of 0.21 mm.
"""
from argparse import ArgumentParser
import json
from math import radians
from pathlib import Path
import sys

import FreeCAD as App
import Part

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'physics'))
from primitives import box, cylinder
from stock import BLINK_CLAMPS, BLINK_CLAMP_LENGTH
from export_cad import world_shape

V = App.Vector
X, Z = (1, 0, 0), (0, 0, 1)
PITCH_AXIS = (V(0, 0, 112), V(1, 0, 0))
PITCH_RANGE_DEG = (-15, 6)
PIN_RADIUS = 4.
CROSS_HOLE_RADIUS = 1.5
FRAME_HOLE_RADIUS = 1.55
DOWEL_RADIUS = 1.5
DOWEL_LENGTH = 12.
BLINK_SHAFT_YZ = (-24., 154.)
BLINK_FLAT_DEPTH = .30
NOMINAL_FLAT_DEPTH = .45
B15_HEAD_CLEARANCE = .21


def frame_holes(frame):
    """Return (x, bottom z, top z) of the vertical Ø3.1 holes across the pin bores."""
    holes = {}
    for face in frame.Faces:
        surface = face.Surface
        if (surface.__class__.__name__ == 'Cylinder' and abs(surface.Radius-FRAME_HOLE_RADIUS) < .01
                and abs(abs(surface.Axis.z)-1) < 1e-6 and abs(surface.Center.y) < 1e-6
                and 50 < abs(surface.Center.x) < 70):
            x = round(surface.Center.x, 3)
            lo, hi = holes.get(x, (1e9, -1e9))
            holes[x] = (min(lo, face.BoundBox.ZMin), max(hi, face.BoundBox.ZMax))
    if sorted(holes) != [-60.5, 60.5]:
        raise ValueError(f'Expected frame holes at x = ±60.5 mm, found {sorted(holes)}')
    return [(x, lo, hi) for x, (lo, hi) in sorted(holes.items())]


def blink_shaft():
    y, z = BLINK_SHAFT_YZ
    shaft = cylinder(2., 112., (-56., y, z), X)
    for x, _, _, _ in BLINK_CLAMPS:
        shaft = shaft.cut(box(x-1.8, x+1.8, y-3, y+3, z+2.-BLINK_FLAT_DEPTH, z+3))
    return shaft


def replace(obj, shape):
    parent = obj.getParentGeoFeatureGroup()
    if parent:
        shape.Placement = parent.getGlobalPlacement().inverse().multiply(shape.Placement)
    obj.Shape = shape


def add_part(doc, group, name, label, shape, motion):
    part = group.newObject('Part::Feature', name)
    part.Label = label
    part.Shape = shape
    part.addProperty('App::PropertyString', 'Motion', 'Wiring')
    part.Motion = motion
    if part.ViewObject:
        part.ViewObject.ShapeColor = (.93, .68, .39)
    return part


def apply(doc):
    frame = world_shape(doc.Part019)
    holes = frame_holes(frame)
    pins = {'Part013': world_shape(doc.Part013), 'Part015': world_shape(doc.Part015)}
    hardware = []
    for x, bottom, top in holes:
        name = 'Part015' if x > 0 else 'Part013'
        pin = pins[name]
        hole = cylinder(CROSS_HOLE_RADIUS, 2*PIN_RADIUS+2, (x, 0, 112-PIN_RADIUS-1), Z)
        if not pin.BoundBox.isInside(V(x, 0, 112)):
            raise ValueError(f'{name} does not reach the frame hole at x = {x}')
        pins[name] = pin.cut(hole)
        outer_end = pin.BoundBox.XMax if x > 0 else pin.BoundBox.XMin
        hub = top - bottom
        if DOWEL_LENGTH > hub:
            raise ValueError(f'Ø3 × {DOWEL_LENGTH:g} dowel is longer than the {hub:.2f} mm frame hub')
        recess = (hub - DOWEL_LENGTH) / 2
        dowel = cylinder(DOWEL_RADIUS, DOWEL_LENGTH, (x, 0, bottom+recess), Z)
        hardware.append({'x_mm': x, 'pin': name, 'from_outer_end_mm': round(abs(outer_end-x), 3),
                         'frame_hub_mm': round(hub, 3), 'dowel_recess_each_end_mm': round(recess, 3),
                         'dowel': dowel})
    for name, shape in pins.items():
        if not shape.isValid() or len(shape.Solids) != 1:
            raise ValueError(f'{name} became invalid')
        replace(doc.getObject(name), shape)
    doc.Part015.Label = 'Right pitch pin · Ø8 × 27.3, 1 mm D-flat, Ø3.2 cross hole'
    doc.Part013.Label = 'Left pitch pin · Ø8 × 21.5, Ø3.2 cross hole'
    shaft = blink_shaft()
    replace(doc.Part048, shaft)
    doc.Part048.Label = f'4 mm blink shaft 112 mm with three {BLINK_FLAT_DEPTH:.2f} mm flats'
    group = doc.Part019.getParentGeoFeatureGroup()
    for item in hardware:
        side = 'Right' if item['x_mm'] > 0 else 'Left'
        add_part(doc, group, f'PitchPinDowel{side}', f'{side} pitch pin Ø3 × 12 dowel', item['dowel'], 'head')
    return hardware


def check(doc, hardware):
    """Static overlap with every other solid, gap to the meshes, and pitch sweep against the yaw carrier."""
    import numpy as np
    import trimesh

    ignore = {'Part013', 'Part015', 'Part019'}
    new = {f"PitchPinDowel{'Right' if h['x_mm'] > 0 else 'Left'}": h['dowel'] for h in hardware}
    solids, meshes = [], []
    for obj in doc.Objects:
        if obj.Name in ignore or obj.Name in new:
            continue
        if obj.TypeId == 'Part::Feature' and obj.Shape.Solids:
            solids.append((obj, world_shape(obj)))
        elif obj.TypeId == 'Mesh::Feature':
            meshes.append(obj)
    report = {'static_overlap_mm3': {}, 'mesh_min_gap_mm': {}, 'sweep_overlap_mm3': {}, 'sweep_min_gap_mm': None}
    for name, shape in new.items():
        for obj, other in solids:
            if other.BoundBox.intersect(shape.BoundBox):
                volume = shape.common(other).Volume
                if volume > 1e-3:
                    report['static_overlap_mm3'][f'{name} / {obj.Label}'] = round(volume, 4)
        samples = np.array([tuple(v) for v in shape.tessellate(.1)[0]])
        reach = shape.BoundBox
        reach.enlarge(3)
        for obj in meshes:
            mesh = obj.Mesh.copy()
            mesh.Placement = obj.getGlobalPlacement()
            if not mesh.BoundBox.intersect(reach):
                continue
            points, facets = mesh.Topology
            near = trimesh.Trimesh(np.array([tuple(p) for p in points]), np.array(facets), process=False)
            keep = np.all((near.triangles_center > np.array([reach.XMin, reach.YMin, reach.ZMin])) &
                          (near.triangles_center < np.array([reach.XMax, reach.YMax, reach.ZMax])), axis=1)
            if not keep.any():
                continue
            near = near.submesh([np.flatnonzero(keep)], append=True)
            inside = [shape.isInside(V(*p), 1e-4, True) for p in near.vertices]
            distance = trimesh.proximity.closest_point(near, samples)[1].min()
            report['mesh_min_gap_mm'][f'{name} / {obj.Label}'] = round(-1. if any(inside) else float(distance), 3)
    carrier = [(obj, shape) for obj, shape in solids if getattr(obj, 'Motion', '') in ('pan', 'fixed')]
    nearest = 1e9
    for angle in range(PITCH_RANGE_DEG[0], PITCH_RANGE_DEG[1]+1):
        for name, shape in new.items():
            moved = shape.copy()
            moved.rotate(*PITCH_AXIS, angle)
            for obj, other in carrier:
                probe = moved.BoundBox
                probe.enlarge(5)
                if not other.BoundBox.intersect(probe):
                    continue
                volume = moved.common(other).Volume
                if volume > 1e-3:
                    report['sweep_overlap_mm3'][f'{name} / {obj.Label} @ {angle}°'] = round(volume, 4)
                nearest = min(nearest, moved.distToShape(other)[0])
    report['sweep_min_gap_mm'] = round(nearest, 3)
    return report


def make(source, output, report):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate CAD output')
    doc = App.openDocument(str(source.resolve()))
    try:
        hardware = apply(doc)
        doc.Label = 'R5 B19 · pitch pin dowels and blink clamp travel'
        doc.recompute()
        result = check(doc, hardware)
        result['pitch_pins'] = [{k: v for k, v in h.items() if k != 'dowel'} for h in hardware]
        result['blink_flat_depth_mm'] = BLINK_FLAT_DEPTH
        result['blink_screw_head_clearance_mm'] = round(B15_HEAD_CLEARANCE + NOMINAL_FLAT_DEPTH - BLINK_FLAT_DEPTH, 3)
        result['blink_screw_length_mm'] = BLINK_CLAMP_LENGTH
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(output.resolve()))
    finally:
        App.closeDocument(doc.Name)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if report:
        report.write_text(text + '\n')
    print(text)
    if result['static_overlap_mm3'] or result['sweep_overlap_mm3'] or \
            any(gap < 0 for gap in result['mesh_min_gap_mm'].values()):
        raise SystemExit('B19 pitch dowels overlap the assembly')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=HERE / 'revisions/b18/R5-B18-external-connections.FCStd')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    make(**vars(parser.parse_args()))
