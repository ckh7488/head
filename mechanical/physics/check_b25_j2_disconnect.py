"""Build and check the B25 rear XT60 service-disconnect motion study."""

from argparse import ArgumentParser
from collections import defaultdict
from hashlib import sha256
import json
from math import acos, cos, sin
from pathlib import Path

import FreeCAD as App
import Part

from build_b21_fasteners import detached_shape
from build_b25_hatch_envelope import J2_INSTALLED_HEIGHT
from check_b18_external_connections import TIP_TRAVEL, fingers
from export_cad import world_shape
from primitives import box, cylinder
from stock import nut, socket_screw


SOCKET = 'https://www.hestore.hu/prod_getfile.php?id=17911'
SOCKET_DRAWING = 'https://pliki.aksotronik.pl/pdf/012682.pdf'
PLUG_DRAWING = 'https://images.100y.com.tw/pdf_file/AMASS-XT60U.pdf'
X, Y, Z = 12.76, 168., -74.6
PANEL = Y + 4.1  # rear face of the 4.1 mm XT60E-F flange
PANEL_DEPTH = 3.
MOUNT_X = (X-12.5, X+12.5)
REAR_WASHER_FRONT = Y+20.5
WASHER_THICKNESS = .5
NUT_SEAT = REAR_WASHER_FRONT+WASHER_THICKNESS
SCREW_LENGTH = 25.
SOCKET_INSTALL_TRAVEL = 25.
AXIS_Y = (0., 1., 0.)
BASE_RELIEF = (-2.6, 17.6, 85.5, 94., -83.3, -70.0)
DROP = 30.
RESERVE = .15
CONTACT_TOL = 1.e-5
WITHDRAW = 20.
PARK = 18.
GRIP_APPROACH = 30.
WIRE_RADIUS = 2.057 / 2.
WIRE_RESERVE = .25
BEND_RADIUS = 12.
V = App.Vector


def collision_volumes(envelope, targets, omitted=()):
    return {name: volume for name, shape in targets.items()
            if name not in omitted and envelope.BoundBox.intersect(shape.BoundBox)
            and (volume := envelope.common(shape).Volume) > CONTACT_TOL}


def sweep(shape, axis, distance, reserve=RESERVE):
    b = shape.BoundBox
    low = [b.XMin-reserve, b.YMin-reserve, b.ZMin-reserve]
    high = [b.XMax+reserve, b.YMax+reserve, b.ZMax+reserve]
    low[axis] += min(0., distance)+reserve
    high[axis] += max(0., distance)-reserve
    return box(low[0], high[0], low[1], high[1], low[2], high[2])


def keyed_profile(y0, y1, width, height, radius, reverse_key=False):
    """D-shaped XT60E-F section, optionally rotated 180 degrees about +Y."""
    half_width, half_height = width / 2., height / 2.
    corner_x = X + half_width - radius
    shape = box(X-half_width, corner_x, y0, y1, Z-half_height, Z+half_height)
    middle = box(corner_x, X+half_width, y0, y1, Z-half_height+radius, Z+half_height-radius)
    curves = [cylinder(radius, y1-y0, (corner_x, y0, Z+side*(half_height-radius)), AXIS_Y)
              for side in (-1, 1)]
    profile = shape.fuse([middle, *curves]).removeSplitter()
    return profile.rotated(V(X, y0, Z), V(*AXIS_Y), 180.) if reverse_key else profile


def fixed_station(saddle, reverse_key=False, rear_offset=0.):
    panel = PANEL+rear_offset
    rear_washer = REAR_WASHER_FRONT+rear_offset
    panel_back = panel+PANEL_DEPTH
    opening = keyed_profile(panel-.1, panel_back+.2, 19.50, 12.05, 3.90, reverse_key)
    screw_holes = [cylinder(1.55, rear_washer-panel+.2, (x, panel-.1, Z), AXIS_Y)
                   for x in MOUNT_X]
    mount = box(X-19., X+19., panel, panel_back, Z-8., -66.10)
    # The flange passes the full web during installation from the mating side.
    web = box(X-19., X+19., 123., panel_back, -66.45, -63.40)
    # Put the loose nuts and wrench plane aft of the complete 20.2 mm socket body.
    ears = []
    for side in (-1, 1):
        x0, x1 = sorted((X+side*9.85, X+side*17.9))
        ears.append(box(x0, x1, panel_back-.35, rear_washer, Z-4.5, Z+4.5))
    station = mount.fuse([web, *ears]).cut([opening, *screw_holes]).removeSplitter()
    revised_saddle = saddle.fuse(station).removeSplitter()
    if not revised_saddle.isValid() or len(revised_saddle.Solids) != 1:
        raise ValueError('The new XT60 station must fuse to the rear cable guide')
    return station, revised_saddle


def local_lead_edges(x, y_start):
    """Return the near-terminal centerline through Y=100 mm as exact tangent arcs."""
    # Two opposite bends lead below the rear cable guide before its forward edge.
    y0, z0 = 79., -67.4
    angle = acos(1.-(z0-Z)/(2.*BEND_RADIUS))
    arc_y = y0 + BEND_RADIUS*sin(angle)
    arc_z = z0 - BEND_RADIUS*(1.-cos(angle))

    def down_arc(t):
        return V(x, y0+BEND_RADIUS*sin(t), z0-BEND_RADIUS*(1.-cos(t)))

    def level_arc(t):
        return V(x, arc_y+BEND_RADIUS*(sin(angle)-sin(angle-t)),
                 arc_z-BEND_RADIUS*(cos(angle-t)-cos(angle)))

    start = V(x, y_start, z0)
    end = V(x, 100., Z)
    return [Part.makeLine(start, down_arc(0.)),
            Part.Arc(down_arc(0.), down_arc(angle/2.), down_arc(angle)).toShape(),
            Part.Arc(level_arc(0.), level_arc(angle/2.), level_arc(angle)).toShape(),
            Part.makeLine(level_arc(angle), end)]


def local_lead(x, y_start):
    """Return the reserved lead solid from the terminal to Y=100 mm."""
    edges = local_lead_edges(x, y_start)
    profile = Part.Wire([Part.makeCircle(WIRE_RADIUS+WIRE_RESERVE, edges[0].Vertexes[0].Point, V(*AXIS_Y))])
    return Part.Wire(edges).makePipeShell([profile], True, False)


def camera_usb_service(camera, targets):
    # B25 places the camera connector on the right. Get the working axis
    # from its native world solid rather than the B18 guide-lane center.
    bound = camera.BoundBox
    x, z = bound.Center.x, bound.Center.z
    receiver = box(x-8.5, x+8.5, bound.YMax-11.8, bound.YMax+25., z-4.9, z+4.9)
    return {
        'stationary_connector_grip': collision_volumes(fingers(camera, x), targets, ('CameraUSB',)),
        'external_receiver_body': collision_volumes(sweep(receiver, 1, TIP_TRAVEL), targets, ('CameraUSB',)),
        'external_receiver_grip': collision_volumes(sweep(fingers(receiver, x), 1, TIP_TRAVEL),
                                                    targets, ('CameraUSB',)),
    }


def evaluate(doc, reverse_key=False, rear_offset=0.):
    socket_y = Y+rear_offset
    panel = PANEL+rear_offset
    rear_washer = REAR_WASHER_FRONT+rear_offset
    nut_seat = NUT_SEAT+rear_offset
    moving = {obj.Name for obj in (*doc.HubInstalled.Group, *doc.HubCableSpace.Group)}
    moving.update(obj.Name for obj in doc.Objects if obj.Name.startswith('HubBolt'))
    shapes = {obj.Name: world_shape(obj) for obj in doc.Objects if obj.TypeId == 'Part::Feature'
              and not obj.Name.startswith('HubRearClearance')}
    hatch = {name: shape for name, shape in shapes.items() if name in moving}
    fixed = {name: shape for name, shape in shapes.items() if name not in moving}
    native_base = detached_shape(doc.Part000)
    revised_base = native_base.cut(box(*BASE_RELIEF)).removeSplitter()
    if not revised_base.isValid() or len(revised_base.Solids) != 1:
        raise ValueError('Rear wire relief must leave the base a single valid solid')
    base_relief_volume = native_base.Volume - revised_base.Volume
    station, revised_saddle = fixed_station(detached_shape(doc.CableSaddle), reverse_key, rear_offset)
    station_targets = {name: shape for name, shape in fixed.items() if name != 'CableSaddle'}
    fixed.update(Part000=revised_base, CableSaddle=revised_saddle)
    # Solder cups are included. Flange and keyed body sweep independently along Y.
    flange = box(X-17., X+17., socket_y, panel, Z-7.9, Z+7.9)
    shell = keyed_profile(panel, socket_y+20.2, 19.10, 11.65, 3.90, reverse_key)
    flange_holes = [cylinder(1.55, 4.3, (x, socket_y-.1, Z), AXIS_Y) for x in MOUNT_X]
    socket = flange.cut(flange_holes).fuse(shell).removeSplitter()
    shell_install = keyed_profile(panel-SOCKET_INSTALL_TRAVEL, socket_y+20.2,
                                  19.10+2.*RESERVE, 11.65+2.*RESERVE, 3.90+RESERVE, reverse_key)
    mount_hardware, tool_paths = {}, {}
    for i, x in enumerate(MOUNT_X, start=1):
        head_seat = (x, socket_y-WASHER_THICKNESS, Z)
        mount_hardware[f'M3 screw {i}'] = socket_screw(3, SCREW_LENGTH, head_seat, AXIS_Y)
        for side, start_y in (('front', head_seat[1]), ('rear', rear_washer)):
            washer_seat = (x, start_y, Z)
            ring = cylinder(3.5, WASHER_THICKNESS, washer_seat, AXIS_Y)
            bore = cylinder(1.6, WASHER_THICKNESS, washer_seat, AXIS_Y)
            mount_hardware[f'M3 {side} washer {i}'] = ring.cut(bore)
        mount_hardware[f'M3 nut {i}'] = nut(3, (x, nut_seat, Z), AXIS_Y, (1., 0., 0.))
        tool_paths[f'2.5 mm hex driver {i}'] = cylinder(2.8, 35., (x, head_seat[1]-3.-35., Z), AXIS_Y)
        # Envelope of the stock 13 × 4.2 mm open-end wrench from below.
        # The open 5.5 mm jaw contains the nut and M3 shank.
        spanner = box(x-6.5, x+6.5, nut_seat, nut_seat+4.2, Z-35., Z+3.)
        jaw = box(x-2.78, x+2.78, nut_seat-.1, nut_seat+4.3, Z-3.25, Z+3.1)
        tool_paths[f'5.5 mm open-end wrench {i}'] = spanner.cut(jaw)
    plug = box(X-15.55/2., X+15.55/2., socket_y-17.2, socket_y, Z-8.3/2., Z+8.3/2.)
    plug_withdrawn = plug.translated(V(0., -WITHDRAW, 0.))
    plug_parked = plug_withdrawn.translated(V(0., 0., -PARK))
    # Side approach gauges cover 7 mm of the nominal 13.5 mm plastic length.
    # Confirm the available contact land with an actual mated connector pair.
    grip_pads = [box(x0, x1, socket_y-13.5, socket_y-6.5, Z-7., Z+7.)
                 for x0, x1 in ((X-16.5, X-15.55/2.), (X+15.55/2., X+16.5))]
    j2 = hatch['HubBodyJ2'].BoundBox
    if abs(j2.ZLength-J2_INSTALLED_HEIGHT) > .01 or abs(j2.YMax-74.15) > .1:
        raise ValueError('Expected the actual B25 Phoenix 1715721 envelope on the A3 PCB')
    local_wires = {name: local_lead(x, j2.YMax+.001)
                   for name, x in (('J2+ lead', 15.30), ('J2 GND lead', 10.22))}
    fixed_with_socket = {**fixed, 'J2 fixed socket': socket}
    mounted_station = {**fixed_with_socket, **mount_hardware}
    lowered = plug_parked.translated(V(0., 0., -DROP))
    camera = fixed['CameraUSB']
    clashes = {
        'camera_usb_service': camera_usb_service(camera, {**mounted_station, 'J2 moving plug': plug}),
        'station_installation': collision_volumes(station, station_targets),
        'socket_installed': collision_volumes(socket, fixed),
        'socket_flange_insertion': collision_volumes(sweep(flange, 1, -SOCKET_INSTALL_TRAVEL), fixed),
        'socket_keyed_body_insertion': collision_volumes(shell_install, fixed),
        'ordinary_M3_socket_mount': {name: collision_volumes(shape, fixed_with_socket)
                                     for name, shape in mount_hardware.items()},
        'stock_driver_and_wrench_approach': {name: collision_volumes(shape, mounted_station)
                                            for name, shape in tool_paths.items()},
        'plug_withdrawal': collision_volumes(sweep(plug, 1, -WITHDRAW), mounted_station,
                                             ('J2 fixed socket',)),
        'plug_down_to_park': collision_volumes(sweep(plug_withdrawn, 2, -PARK), mounted_station),
        'parked_plug_lowering': collision_volumes(sweep(plug_parked, 2, -DROP), mounted_station),
        'side_grip_approach': [collision_volumes(sweep(pad, 2, -GRIP_APPROACH), mounted_station)
                               for pad in grip_pads],
        'side_grip_withdrawal': [collision_volumes(sweep(pad, 1, -WITHDRAW), mounted_station)
                                 for pad in grip_pads],
        'side_grip_lower_to_park': [collision_volumes(sweep(pad.translated(V(0., -WITHDRAW, 0.)),
                                                           2, -PARK), mounted_station)
                                   for pad in grip_pads],
        'hatch_relative_j2_exit': {name: collision_volumes(wire, hatch) for name, wire in local_wires.items()},
        'full_local_lead_lowering_sweep': {},
    }
    native_clashes = {}
    for name, wire in local_wires.items():
        # A union of 1 mm-long rectangular columns conservatively covers the
        # swept solid through the whole 0–30 mm hatch drop.
        revised_hits, baseline_hits = defaultdict(float), defaultdict(float)
        for y in range(74, 100):
            segment = wire.common(box(8., 17.6, float(y), y+1., -80., -63.))
            envelope = sweep(segment, 2, -DROP, reserve=0.)
            for targets, totals in ((fixed_with_socket, revised_hits), ({'Part000': native_base}, baseline_hits)):
                for part, volume in collision_volumes(envelope, targets).items():
                    totals[part] += volume
        clashes['full_local_lead_lowering_sweep'][name] = dict(revised_hits)
        native_clashes[name] = dict(baseline_hits)
    clearance_rows = [clashes[key] for key in ('station_installation', 'socket_installed', 'socket_flange_insertion',
                                               'socket_keyed_body_insertion', 'plug_withdrawal',
                                               'plug_down_to_park', 'parked_plug_lowering')]
    clearance_rows.extend(clashes['side_grip_approach'] + clashes['side_grip_withdrawal']
                          + clashes['side_grip_lower_to_park'])
    clearance_rows.extend(clashes['camera_usb_service'].values())
    clearance_rows.extend(clashes['ordinary_M3_socket_mount'].values())
    clearance_rows.extend(clashes['stock_driver_and_wrench_approach'].values())
    clearance_rows.extend(clashes['hatch_relative_j2_exit'].values())
    clearance_rows.extend(clashes['full_local_lead_lowering_sweep'].values())
    plus, ground = local_wires.values()
    local_wire_gap = plus.distToShape(ground)[0]
    results = {
        'status': 'fail' if any(clearance_rows) or local_wire_gap <= 0. else 'pass_rigid_and_local_lead',
        'components': {'fixed_supply_socket': 'AMASS XT60E-F', 'hatch_pigtail': 'AMASS XT60U-M',
                       'sources': [SOCKET, SOCKET_DRAWING, PLUG_DRAWING]},
        'pin_map': {'+': 'A3 J2 pad 1 (/12V_IN)', '-': 'A3 J2 pad 2 (/GND)'},
        'socket_face_center_mm': [X, socket_y, Z], 'unplug_axis': [0., -1., 0.],
        'socket_insertion_from_mating_side_mm': SOCKET_INSTALL_TRAVEL,
        'socket_mount_hardware': '2 M3 × 25 socket head screws, 4 M3 flat washers, 2 loose M3 plain hex nuts',
        'mount_wrench_underneath': '5.5 mm open-end, 13.0 mm max head width, 4.2 mm max head thickness',
        'nominal_panel_ligament_mm': 1.20,
        'plug_withdrawal_mm': WITHDRAW, 'park_drop_mm': PARK, 'hatch_drop_mm': DROP,
        'minimum_local_lead_radius_mm': BEND_RADIUS, 'design_target_radius_mm': 5.*2.*WIRE_RADIUS,
        'reserved_local_lead_gap_mm': local_wire_gap,
        'wire_envelope_reserve_mm': WIRE_RESERVE, 'plug_envelope_reserve_mm': RESERVE,
        'collision_volume_tolerance_mm3': CONTACT_TOL,
        'camera_usb_world_x_mm': camera.BoundBox.Center.x,
        'camera_usb_axial_withdrawal_mm': TIP_TRAVEL,
        'grip_approach_from_below_mm': GRIP_APPROACH,
        'grip_nominal_axial_envelope_mm': 7.,
        'actual_mated_grip_length_verified': False,
        'base_slot_cutter_mm': BASE_RELIEF, 'base_material_removed_mm3': base_relief_volume,
        'socket_bottom_above_native_base_bottom_mm': socket.BoundBox.ZMin-revised_base.BoundBox.ZMin,
        'lowered_plug_below_base_bottom_mm': revised_base.BoundBox.ZMin-lowered.BoundBox.ZMin,
        'intersections_mm3': clashes,
        'unmodified_base_lead_sweep_intersections_mm3': native_clashes,
        'pending': ['Full-length pigtail routing, inextensible unplug/park motion, and fixed 12 V lead routing',
                    'Actual mated grip land, disconnection force, trial fit, strain relief, guard, and print strength',
                    'Protection upstream of either XT60 mating path and remaining J3/J7 harness clearance'],
    }
    features = {'base': revised_base, 'saddle': revised_saddle, 'socket': socket, 'plug': plug,
                'withdrawn': plug_withdrawn, 'parked': plug_parked, 'lowered': lowered, **local_wires, **mount_hardware}
    return results, features


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--study-cad', type=Path, help='Write a separate pose-study FCStd')
    args = parser.parse_args()
    paths = [path.resolve() for path in (args.cad, args.output, args.study_cad) if path]
    if len(paths) != len(set(paths)):
        parser.error('the input CAD, report and study CAD must have separate paths')
    doc = App.openDocument(str(args.cad.resolve()))
    try:
        report, features = evaluate(doc)
        report['cad_sha256'] = sha256(args.cad.read_bytes()).hexdigest()
        args.output.write_text(json.dumps(report, indent=2)+'\n')
        if args.study_cad:
            from build_b19_review_fixes import replace

            replace(doc.Part000, features.pop('base'))
            replace(doc.CableSaddle, features.pop('saddle'))
            study = doc.addObject('App::DocumentObjectGroup', 'J2DisconnectStudy')
            study.Label = 'J2 study · assembled + alternate plug poses'
            for name, shape in features.items():
                part = doc.addObject('Part::Feature', 'J2Disconnect'+name.title().replace(' ', ''))
                part.Label = 'J2 disconnect study · '+name
                part.Shape = shape
                study.addObject(part)
            doc.recompute()
            doc.saveAs(str(args.study_cad.resolve()))
    finally:
        App.closeDocument(doc.Name)
    return report['status'].startswith('fail')


if __name__ == '__main__':
    raise SystemExit(main())
