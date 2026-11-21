"""Build the B22 camera cable relief, sliding guide, and rear exit."""

from argparse import ArgumentParser
import json
from math import acos, cos, radians, sin
from pathlib import Path

import FreeCAD as App
import numpy as np
import Part

from build_b19_review_fixes import replace
from build_b21_fasteners import check_solid
from build_b22_camera_mount import apply as fit_camera_mount
from build_b22_camera_pcb import apply as fit_camera_pcb
from build_wiring_revision import pipe
from export_cad import world_shape
from primitives import print_mesh


NOSE_GUIDE_START = (6.8, -39.079214546577546, 80.66784546342967)
NOSE_GUIDE_SLOPE = (-.23617145779151538, .06992681194351034)
CAMERA_SHEATH_END = (5.5, -47.05, 83.)
NOSE_GUIDE_PRINT = '26_u20cam_slotted_bracket-B22.stl'


def rotor_saddle():
    y, z, radius = -36., -37.4, 14.
    turn = radians(36.)
    stations = np.linspace(0., turn, 34)
    curve = np.c_[np.zeros(len(stations)), y+radius*(1-np.cos(stations)), z+radius*np.sin(stations)]
    tangent = np.array((0., sin(turn), cos(turn)))
    cavity = pipe(np.vstack(([0., y, z-6.], [0., y, z-3.], curve, curve[-1]+5.*tangent)), 2.33)
    angle = np.linspace(0., turn, 41)
    band = [(10.3, t) for t in angle] + [(14.25, t) for t in angle[::-1]]
    points = [App.Vector(-4.1, y+radius-r*cos(t), z+r*sin(t)) for r, t in band]
    guide = Part.Face(Part.makePolygon(points+[points[0]])).extrude(App.Vector(8.2, 0., 0.))
    plug_access = Part.makeBox(25., 9., 27., App.Vector(-12.5, -42.7, -46.))
    return guide.cut([cavity, plug_access]).removeSplitter()


def rotor_plug_passage():
    # The 9.2 × 5.3 mm plug gauge needs 0.3 mm per side and ends at the existing saddle backing.
    return Part.makeBox(9.80, 5.90, 42., App.Vector(-4.90, -39.60, -61.50))


def rear_lead(mouth, exit_port):
    radius = 14.
    start = App.Vector(*mouth)
    a = App.Vector(round(mouth[0], 3), 106., round(mouth[2], 3))
    offset = App.Vector(exit_port[0]-a.x, 0., exit_port[2]-a.z)
    direction = offset / offset.Length
    turn = acos(1.-offset.Length/(2.*radius))
    forward = App.Vector(0., 1., 0.)

    def first(angle):
        return a + forward*(radius*sin(angle)) + direction*(radius*(1-cos(angle)))

    def second(angle):
        return first(turn) + forward*(radius*(sin(turn)-sin(turn-angle))) + direction*(
            radius*(cos(turn-angle)-cos(turn)))

    b, c = first(turn), second(turn)
    end = App.Vector(exit_port[0], 158., exit_port[2])
    path = Part.Wire([Part.makeLine(start, a), Part.Arc(a, first(turn/2.), b).toShape(),
                      Part.Arc(b, second(turn/2.), c).toShape(), Part.makeLine(c, end)])
    cross = Part.Wire([Part.makeCircle(2., start, forward)])
    return check_solid(path.makePipeShell([cross], True, False), 'rear camera lead')


def relief_cutter(points):
    radius = 2.75
    positions = [App.Vector(*row) for row in points]
    spheres = [Part.makeSphere(radius, point) for point in positions]
    strokes = []
    for start, end in zip(positions, positions[1:]):
        delta = end - start
        strokes.append(Part.makeCylinder(radius, delta.Length, start, delta))
    return spheres[0].multiFuse(spheres[1:] + strokes).removeSplitter()


def nose_cradle(tie_roof_drop=0.):
    start_x, start_y, start_z = NOSE_GUIDE_START
    end_x, end_y, end_z = CAMERA_SHEATH_END
    t = np.linspace(0., 1., 51)[:, None]
    length = start_y - end_y
    center = ((2*t**3 - 3*t**2 + 1)*[start_x, start_z]
              + (t**3 - 2*t**2 + t)*(np.array(NOSE_GUIDE_SLOPE)*length)
              + (-2*t**3 + 3*t**2)*[end_x, end_z]
              + (t**3 - t**2)*np.array([0., .442/.897])*length)
    stations = start_y - length*t[:, 0]

    def at(y):
        return [float(np.interp(y, stations[::-1], values[::-1])) for values in center.T]

    def profile(y, outline):
        rim = [App.Vector(x, y, z) for x, z in outline]
        return Part.makePolygon(rim + rim[:1])

    def rectangle(y, x, bottom, top):
        return profile(y, [(x-3.6, bottom), (x+3.6, bottom), (x+3.6, top), (x-3.6, top)])

    root = Part.makeLoft([rectangle(y, 5.7, bottom, top) for y, bottom, top in
                         ((-49., 71.9, 74.4), (-47.4, 72.4, 75.8),
                          (-46.2, 73.3, 76.8), (-44.25, 75.2, 78.5))], True, True)
    front, rear = -44.55, start_y - .25
    track = np.linspace(front, rear, 21)
    walls = []
    for y in track:
        x, z = at(y)
        taper = min((y-front)/1.25, (rear-y)/1.25, 1.)
        walls.append(rectangle(y, x, 75.1 + .46*(y-front), z + .53 - .67*(1. - taper)))

    groove = []
    for y in np.r_[front-.12, track, rear+.12]:
        x, z = at(y)
        taper = max(0., min((y-front)/1.28, (rear-y)/1.28, 1.))
        radius = 2.39 + .24*(1. - taper)
        arc = [(x+radius*cos(a), z+radius*sin(a)) for a in np.linspace(np.pi, 2*np.pi, 32)]
        groove.append(profile(y, arc + [(x+radius, z+4.), (x-radius, z+4.)]))

    y = (front + rear) / 2.
    x, z = at(y)
    roof = z - 3.72 - tie_roof_drop
    opening = [App.Vector(x-4.6, y+dy, height) for dy, height in
               ((-1.49, roof), (1.49, roof), (2.04, roof-1.6),
                (2.04, 68.), (-2.04, 68.), (-2.04, roof-1.6))]
    tie = Part.Face(Part.makePolygon(opening + opening[:1])).extrude(App.Vector(9.2, 0., 0.))
    saddle = root.fuse(Part.makeLoft(walls, True, False)).cut(tie)
    saddle = saddle.cut(Part.makeLoft(groove, True, False)).removeSplitter()
    return check_solid(saddle, 'camera bracket cable saddle'), (x, y, roof)


def apply_nose(doc, print_dir):
    saddle, tie_roof = nose_cradle()
    stock = world_shape(doc.Part066)
    if stock.common(saddle).Volume < 9.:
        raise ValueError('Nose saddle does not overlap the existing camera bracket flange')
    bracket = check_solid(stock.fuse(saddle).removeSplitter(), 'camera bracket with nose saddle')
    replace(doc.Part066, bracket)
    print_mesh(bracket, print_dir/NOSE_GUIDE_PRINT)
    motion = json.loads(doc.R5.MotionGeometry)
    motion['camera_cable_nose'] = {'parent': 'Part066', 'groove_start_mm': NOSE_GUIDE_START,
                                   'tie_notch_roof_center_mm': tie_roof, 'tie_notch_roof_width_mm': 2.98,
                                   'tie_open_axis': '-Z', 'cable_open_axis': '+Z', 'stock_tie_width_mm': 2.5}
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)


def update_path(doc, routing):
    motion = json.loads(doc.R5.MotionGeometry)
    cable, = [obj for obj in doc.WiringRouting.Group if obj.Label.startswith('USB-Camera ')]
    cable.Shape = Part.makePolygon([App.Vector(*row) for row in routing['neutral_inner_points_mm']])
    cable.CableLength = cable.Shape.Length
    cable.JacketDiameter = 4.
    cable.MinimumBend = routing['neutral_minimum_radius_mm']
    cable.Label = f'USB-Camera  ·  {cable.Shape.Length:.1f} mm'
    motion['camera_cable'] = {'case_exit_mm': routing['case_exit_mm'],
                              'base_cable_entry_mm': routing['base_entry_mm'],
                              'stock_od_mm': 4., 'guide_bend_radius_mm': 14., 'outside_bend_radius_mm': 14.,
                              'plug_feed': {
                                  'base': {'start_mm': [54.625, 100., -70.], 'end_mm': [54.625, 55., -70.],
                                           'pull_end_mm': [54.625, 55., -26.],
                                           'body_mm': [9.2, 7., 5.3], 'cross_tolerance_mm': .2},
                                  'rotor': {'start_mm': [0., -36.65, -57.], 'end_mm': [0., -36.65, -24.],
                                            'body_mm': [9.2, 5.3, 7.], 'cross_tolerance_mm': .2},
                              }}
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)


def apply_mounts(doc, print_dir):
    bracket, hardware = fit_camera_mount(doc, print_dir)
    hardware.extend(fit_camera_pcb(doc))
    motion = json.loads(doc.R5.MotionGeometry)
    motion['camera_pcb_mount']['insertion_offsets_mm'] = [
        [0., 24., 9.35], [0., .24, 9.35], [0., .24, 0.], [0., 0., 0.]]
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)
    print_mesh(bracket, print_dir / NOSE_GUIDE_PRINT)
    (print_dir / 'camera-hardware.json').write_text(json.dumps(hardware, indent=2) + '\n')
    return hardware


def apply(doc, routing, print_dir):
    base = world_shape(doc.Part000).cut(relief_cutter(routing['base_relief_points_mm'])).removeSplitter()
    rotor = world_shape(doc.Part007).cut(rotor_plug_passage()).fuse(rotor_saddle()).removeSplitter()
    for name, shape, filename in (('Part000', base, '01_base_cup-B22.stl'),
                                  ('Part007', rotor, '04_yaw_rotor-B22.stl')):
        fitted = check_solid(shape, name)
        replace(doc.getObject(name), fitted)
        print_mesh(fitted, print_dir/filename)
    exit_port = routing['case_exit_mm']
    replace(doc.RearLead3_1, rear_lead(routing['base_entry_mm'], exit_port))
    connector = world_shape(doc.CameraUSB)
    connector.translate(App.Vector(exit_port[0]-9.5, 0., 0.))
    replace(doc.CameraUSB, connector)
    update_path(doc, routing)
    apply_nose(doc, print_dir)
    apply_mounts(doc, print_dir)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('routing', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('print_dir', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('Use a separate output assembly')
    args.print_dir.mkdir(parents=True, exist_ok=True)
    doc = App.openDocument(str(args.source.resolve()))
    try:
        apply(doc, json.loads(args.routing.read_text()), args.print_dir)
        doc.recompute()
        doc.saveAs(str(args.output.resolve()))
    finally:
        App.closeDocument(doc.Name)
