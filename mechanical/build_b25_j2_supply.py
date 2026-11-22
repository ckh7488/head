"""Implement the B25 A4 12 V inlet and relocate the existing WAGO pair."""
from dataclasses import dataclass
from itertools import combinations
from math import pi
from pathlib import Path

import FreeCAD as App
import Part
import numpy as np

from build_b19_review_fixes import replace
from check_b25_j2_disconnect import collision_volumes, sweep
from check_b25_j2_pigtail import s_turn_edges, tube
from export_cad import world_shape
from primitives import box, cylinder
from stock import socket_screw

V = App.Vector
AXIS_Y = (0., 1., 0.)
Z_INLET = -57.5
Y_INLET_REAR = 171.2
X_INLET = -15.5
Y_WAGO = 230.
Z_WAGO_PORT = -74.6
TRAY_TRANSLATION = 23.
COLLAR_BOLTS = ((-25.5, 174.7), (-1.5, 172.))
WAGO_PITCH = 5.6
WIRE_RAD = .119 * 25.4 / 2.
RESERVE = .25
STOCK_CAD = Path(__file__).resolve().parents[1] / 'build/connector-cad'
SUBTRACT = (-7., 33., 204., 227., -83., -65.)
NATIVE_LEGACY_LEADS = ('CableTie2', 'RearLead2_1', 'RearLead2_2')
OLD_ROUTING = ('A4WagoPositive', 'A4WagoGround', 'A4WagoLinkPositive', 'A4WagoLinkGround')
STOCK_PARTS = {
    'WAGO 221-412': 'https://www.wago.com/global/installation-terminal-blocks-and-connectors/compact-splicing-connector/p/221-412',
    'AMASS XT60U-M/F': 'https://images.100y.com.tw/pdf_file/AMASS-XT60U.pdf',
    'XT60U-M ext supplier STEP': 'https://www.lcsc.com/product-detail/C129184.html',
    'XT60U-F ext supplier STEP': 'https://www.lcsc.com/product-detail/C19191801.html',
    'WAGO pitch corroboration': 'https://mods.vorondesign.com/mods/deepfriedheroin/v0_bed_wagos',
    'Alpha Wire EcoWire 6718': 'https://www.alphawire.com/products/wire/ecogen/ecowire/6718',
}


@dataclass(frozen=True)
class Branch:
    polarity: str
    inlet_x: float
    wago_inlet_x: float
    socket_x: float
    wago_socket_x: float
    upstream_id: str
    link_id: str


BRANCHES = (
    Branch('Positive', X_INLET-3.6, 5.26-WAGO_PITCH/2., 9.16, 5.26+WAGO_PITCH/2., 'A4W6', 'A4W35'),
    Branch('Ground', X_INLET+3.6, 20.26-WAGO_PITCH/2., 16.36, 20.26+WAGO_PITCH/2., 'A4W7', 'A4W36'),
)


def line(start, end):
    return Part.makeLine(V(*start), V(*end))


def finite_box(shape):
    b = shape.BoundBox
    return [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax]


def reserve_tube(edges):
    return tube(edges, WIRE_RAD+RESERVE)


def stock_geometry(parts):
    """Rotate supplier STEP around the actual connector axes; retain mating plane."""
    male = Part.read(str(parts/'XT60U-M.step'))
    female = Part.read(str(parts/'XT60U-F.step'))
    for shape in (male, female):
        b=shape.BoundBox
        if max(abs(b.XLength-15.3), abs(b.YLength-7.9), abs(b.ZMax-13.5)) > .02:
            raise ValueError('The STEP must depict the 15.3 × 7.9 × 13.5 mm XT60U body.')
    # Supplier STEP + is the square end on local +X. Flip both halves together
    # around their mating axis so the original left position is the red lead.
    for shape in (male, female):
        shape.rotate(V(), V(0., 0., 1.), 180.)
    male.rotate(V(), V(1., 0., 0.), -90.).translate(V(X_INLET, Y_INLET_REAR, Z_INLET))
    female.rotate(V(), V(1., 0., 0.), 90.).translate(V(X_INLET, 190.5, Z_INLET))
    return male, female


def lead_edges(branch, z_port=Z_WAGO_PORT):
    x = branch.inlet_x
    z = Z_INLET
    y_bend = Y_INLET_REAR-3.65-6.
    radius = 18.4
    y_rear_turn = 196.
    y_lead_end = Y_WAGO-6.
    z_return = z+2.*radius
    tail = line((x, y_bend+6., z), (x, y_bend, z))
    reverse = Part.Arc(V(x, y_bend, z), V(x, y_bend-radius, z+radius), V(x, y_bend, z_return)).toShape()
    shift_start = np.array((x, y_bend, z_return))
    shift_end = np.array((branch.wago_inlet_x, y_rear_turn, z_return))
    shift, r_shift = s_turn_edges(shift_start, shift_end)
    turns, r = s_turn_edges(shift_end, np.array((branch.wago_inlet_x, y_lead_end, z_port)))
    aim = line((branch.wago_inlet_x, y_lead_end, z_port),
               (branch.wago_inlet_x, Y_WAGO, z_port))
    return [tail, reverse, *shift, *turns, aim], min(radius, r_shift, r)


def socket_link_edges(branch, z_port=Z_WAGO_PORT):
    lead_end = (branch.wago_socket_x, Y_WAGO-6., z_port)
    turns, radius = s_turn_edges(np.array((branch.socket_x, 196.2, Z_WAGO_PORT)),
                                 np.array(lead_end))
    turns.append(line(lead_end, (branch.wago_socket_x, Y_WAGO, z_port)))
    return turns, radius


def collar_hardware():
    hardware, lower_bores, upper_bores = {}, [], []
    for index, center in enumerate(COLLAR_BOLTS, 1):
        hardware[f'A4InletBolt{index}'] = socket_screw(3, 12., (*center, -50.), (0., 0., -1.))
        insert = cylinder(1.99, 3., (*center, -60.5)).cut(cylinder(1.52, 3., (*center, -60.5)))
        hardware[f'A4InletInsert{index}'] = insert
        lower_bores.append(cylinder(2.075, 4.51, (*center, -62.)))
        upper_bores.append(cylinder(1.725, 7.51, (*center, -57.51)))
    return hardware, lower_bores, upper_bores


def fixed_tray(old_guide):
    cut = box(*SUBTRACT)
    old_wago = old_guide.common(box(-7., 33., 205.2, 226.81, -83., -65.))
    if len(old_wago.Solids) != 1:
        raise ValueError('Expected the existing A4 WAGO cage to be one printed solid.')
    cage = old_wago.translated(V(0., TRAY_TRANSLATION, 0.))
    # Upper side frames leave the Y-facing wire ports and the wrench withdrawal open.
    left = box(-5.2, -2.9, 199., 229., -70.5, -67.)
    right = box(28.5, 30.3, 199., 229., -70.5, -67.)
    return cut, cage.fuse([left, right]).removeSplitter()


def loop_support():
    # Reuse the supply lane's 2.5 mm strap around the high return and this shelf.
    # The lower tunnel is open at both ends so it can be re-laced from behind.
    y0, y1 = 164., 169.
    root = box(-26., -22.55, y0, y1, -64., -59.5)
    spine = box(-24.3, -22.55, y0, y1, -63.5, -24.5)
    ledge = box(-24.3, -7.2, y0, y1, -26.7, -22.5)
    section = [V(x, y0, z) for x, z in ((-24.3, -42.), (-8.5, -26.5),
                                       (-24.3, -26.5), (-24.3, -42.))]
    brace = Part.Face(Part.makePolygon(section)).extrude(V(0., y1-y0, 0.))
    tunnel = box(-24.4, -7.1, 164.7, 168.3, -26.3, -24.8)
    return root.fuse([spine, ledge, brace]).cut(tunnel).removeSplitter()


def inlet_collar():
    # Lower half bears the body on four nearly-flat land strips. The upper
    # half can drop vertically over the stock rim before the two bolts are added.
    lower_plate = box(-29., 2., 169.6, 178., -64., -61.60)
    upper_plate = box(-29., 2., 169.6, 178., -53.40, -50.)
    lower_tooth = box(X_INLET-4.7, X_INLET+4.7, 173.05, 174.15, -61.65, -61.025)
    upper_tooth = box(X_INLET-4.7, X_INLET+4.7, 173.05, 174.15, -53.975, -53.35)
    lower_pillars, upper_pillars = [], []
    for x, y in COLLAR_BOLTS:
        lower_pillars.append(box(x-3.5, x+3.5, y-3.5, y+3.5, -63., -57.5))
        upper_pillars.append(box(x-3.5, x+3.5, y-3.5, y+3.5, -57.5, -50.))
    lower_root = box(-29., -25., 121., 177., -64., -58.)
    lower_bridge = box(-28., -5.9, 174., 179., -66.4, -63.55)
    upper_root = box(-29., -25., 121., 171.8, -52., -49.45)
    # A 15.60 mm lower pocket leaves 0.15 mm per side at the nominal
    # 15.30 mm body; set final play with thin stock shims at assembly.
    lower_notch = box(-23.30, -7.70, 169.5, 179.1, -61.59, -57.49)
    upper_notch = box(-23.30, -7.70, 169.5, 179.1, -57.51, -53.41)
    adapter_mouth_relief = box(-23.8, -7.2, 176.5, 179.1, -62.1, -52.9)
    hardware, lower_bores, upper_bores = collar_hardware()
    lower = lower_plate.fuse([lower_root, lower_bridge, loop_support(), *lower_pillars]).cut([lower_notch, adapter_mouth_relief, *lower_bores])
    upper = upper_plate.fuse([upper_root, *upper_pillars]).cut([upper_notch, adapter_mouth_relief, *upper_bores])
    return (lower.fuse(lower_tooth).removeSplitter(),
            upper.fuse(upper_tooth).removeSplitter(), hardware)


def printable_deltas(doc):
    lower, upper, hardware = inlet_collar()
    old_guide = world_shape(doc.CableSaddle)
    old_cover = world_shape(doc.CableGate)
    cutter, extension = fixed_tray(old_guide)
    guide = old_guide.cut(cutter).fuse([extension, lower]).removeSplitter()
    cover = old_cover.fuse(upper).removeSplitter()
    for name, result in [('CableSaddle', guide), ('CableGate', cover)]:
        if not result.isValid() or len(result.Solids) != 1:
            raise ValueError(f'{name} must remain one valid printed solid.')
    return guide, cover, [
        ('CableSaddle', 'subtract', cutter),
        ('CableSaddle', 'add', extension),
        ('CableSaddle', 'add', lower),
        ('CableGate', 'add', upper),
    ], hardware


def build_plan(doc, stock):
    guide, cover, deltas, hardware = printable_deltas(doc)
    male, female = stock_geometry(stock)
    changed = dict(CableSaddle=guide, CableGate=cover, InputXT60Mate=male, InputXT60=female)
    added = {**hardware}
    rows = {}
    for branch in BRANCHES:
        id_wago = f'A4Wago{branch.polarity}'
        stock_bounds = world_shape(doc.getObject(id_wago)).BoundBox
        # The current diagram's maximum is 13.2 × 8.4 × 18.6 mm.
        changed[id_wago] = box(stock_bounds.XMin-.05, stock_bounds.XMax+.05,
                               stock_bounds.YMin+TRAY_TRANSLATION, stock_bounds.YMax+TRAY_TRANSLATION,
                               stock_bounds.ZMin, stock_bounds.ZMax+.10)
        for name, route in ((branch.upstream_id, lead_edges), (branch.link_id, socket_link_edges)):
            edges, radius = route(branch)
            added[name] = reserve_tube(edges)
            rows[name] = {
                'jacket_route_mm': Part.Wire(edges).Length,
                'min_bend_centerline_radius_mm': radius,
                'start_mm': list(edges[0].Vertexes[0].Point),
                'end_mm': list(edges[-1].Vertexes[-1].Point),
                'WAGO_strip_mm': 11.,
            }
            if name == branch.upstream_id:
                start = tuple(edges[0].Vertexes[1].Point)
                added[name+'SupplyCup'] = cylinder(3.05, Y_INLET_REAR-start[1], start, AXIS_Y)
            else:
                start = (branch.socket_x, 192.2, Z_WAGO_PORT)
                added[name+'SocketCup'] = cylinder(3.05, 4., start, AXIS_Y)
    return changed, added, deltas, rows


def apply(doc, stock=STOCK_CAD):
    changed, added, deltas, rows = build_plan(doc, stock)
    for name, shape in changed.items():
        replace(doc.getObject(name), shape)
    for name in (*NATIVE_LEGACY_LEADS, 'A4WagoLinkPositive', 'A4WagoLinkGround'):
        doc.removeObject(name)
    group = doc.addObject('App::DocumentObjectGroup', 'A4J2Supply')
    group.Label = 'A4 fixed 12 V supply leads and inlet fasteners'
    for name, shape in added.items():
        obj = group.newObject('Part::Feature', name)
        obj.Label = name
        obj.addProperty('App::PropertyString', 'Motion', 'Wiring')
        obj.Motion = 'fixed'
        obj.Shape = shape
    doc.recompute()
    return rows


def route_report(doc, stock):
    changed, added, deltas, rows = build_plan(doc, stock)
    targets = {obj.Name: world_shape(obj) for obj in doc.Objects if obj.TypeId == 'Part::Feature'
               and not obj.Name.startswith(('HarnessWire', 'HubRearClearance'))
               and obj.Name not in (*NATIVE_LEGACY_LEADS, *OLD_ROUTING) and not obj.Shape.isNull()}
    targets.update(changed)
    routes = [branch.upstream_id for branch in BRANCHES]+[branch.link_id for branch in BRANCHES]
    targets.update((name, solid) for name, solid in added.items() if name not in routes and not name.endswith('Cup'))
    for name, row in rows.items():
        row['solid_hits_mm3'] = collision_volumes(added[name], targets, ('InputXT60Mate',))
    min_gap = min(added[a].distToShape(added[b])[0] for a, b in combinations(routes, 2))
    all_shapes = {**targets, **added}
    adapter_grip = box(X_INLET-9., X_INLET+9., 185., 190.2, Z_INLET-16., Z_INLET+16.)
    adapter_omit = ('InputXT60Mate', 'InputXT60')
    adapter_checks = {
        'axial_0_to_16_mm': collision_volumes(sweep(changed['InputXT60'], 1, 16.), all_shapes, adapter_omit),
        'grip_exit_0_to_16_mm': collision_volumes(sweep(adapter_grip, 1, 16.), all_shapes, adapter_omit),
    }
    tools = {}
    for index, (x, y) in enumerate(COLLAR_BOLTS, 1):
        shaft = cylinder(2.8, 35., (x, y, -47.))
        tools[f'driver_{index}_hits_mm3'] = collision_volumes(shaft, all_shapes)
    stock_format = {}
    for branch in BRANCHES:
        wago_id = f'A4Wago{branch.polarity}'
        b = changed[wago_id].BoundBox
        lever = box(b.XMin, b.XMax, b.YMin+.3, b.YMax-.3, b.ZMax, b.ZMax+15.)
        stock_format[wago_id] = {
            'external_bounds_mm': finite_box(changed[wago_id]),
            'lever_and_finger_hits_mm3': collision_volumes(lever, all_shapes, (wago_id,)),
        }
    return {
        'stock_source': STOCK_PARTS,
        'WAGO_rear_translation_mm': TRAY_TRANSLATION,
        'new_printable_bounds_mm': {name: finite_box(changed[name]) for name in ('CableSaddle', 'CableGate')},
        'inlet_housing_and_adapter': finite_box(changed['InputXT60Mate']),
        'route_checks': rows,
        'min_wire_to_wire_gap_mm_with_reserve': min_gap,
        'wire_solid_bounds_mm': {name: finite_box(added[name]) for name in routes},
        'lowest_fixed_wire_reserved_z_mm': min(added[name].BoundBox.ZMin for name in routes),
        'table_plane_mm': world_shape(doc.Part000).BoundBox.ZMin,
        'connector_release_checks': adapter_checks,
        'collar_driver_checks': tools,
        'WAGO_use_envelopes': stock_format,
        'min_manufacturer_bend_mm': 5.*2.*WIRE_RAD,
        'min_wire_outside_radius_mm': min(row['min_bend_centerline_radius_mm'] for row in rows.values())-WIRE_RAD,
        'boot_hits_mm3': {
            name: collision_volumes(solid, targets,
                                    ('InputXT60Mate',) if name.endswith('SupplyCup')
                                    else ('A4XT60ExternalSocket',))
            for name, solid in added.items() if name.endswith('Cup')
        },
        'inlet_housing_fit_mm3': {name: changed['InputXT60Mate'].common(changed[name]).Volume
                                  for name in ('CableSaddle', 'CableGate')},
        'inlet_mated_male_female_overlap_mm3': changed['InputXT60Mate'].common(changed['InputXT60']).Volume,
    }
