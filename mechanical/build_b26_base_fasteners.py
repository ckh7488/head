"""B26 base cup: no heat-set inserts, every nut visible.

* Bottom-hatch nuts sit in a shallow loose hex recess (5.9 mm across flats, 1.2 mm deep) on
  one bar per side, over a plain 3.7 mm through hole. The recess is a clearance fit, so print
  error does not matter; it stops the nut turning while the M3 x 10 is driven from below and
  keeps the nut on the bar when the base lies on its side. The nut stands 1.2 mm proud and is
  visible. The two keeper plates, their screws and their inserts go.
* The neck-yaw bracket feet are bolted from below: an M3 x 18 in a counterbore under
  the base, and a plain M3 nut on top of the bracket foot, held from above with a 5.5 mm
  socket (an open-end spanner has no room to swing inside the cup there). The four
  inserts go.

The same solid edits are applied to the native CAD solid and to the print mesh,
so the print-only details already in the B25 print file are kept.
"""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App
import MeshPart
import Part
from FreeCAD import Vector as V

from build_b19_review_fixes import add_part, replace
from build_b21_fasteners import check_solid, detached_shape
from primitives import box, cylinder
from service_hatch import HATCH_MOUNTS
from stock import hexagon, socket_screw

UP = (0., 0., 1.)
DOWN = (0., 0., -1.)

# M3 hex nut: 5.5 mm across flats, 2.4 mm thick (ISO 4032).
NUT_AF = 5.5
NUT_HEIGHT = 2.4
CLEARANCE_RADIUS = 1.85          # matches the existing hatch bolt hole (3.7 mm)

# Hatch nuts: in a shallow loose hex recess on top of one bar per side, over a plain through hole.
# The recess is a clearance fit (5.9 mm across flats for a 5.5 mm nut, so +-0.2 mm print error
# still drops the nut in by hand); it stops the nut turning (about 14 deg of play) and keeps it on
# the bar when the base lies on its side with the hatch off: the rim is 1.8 mm of the 2.4 mm nut,
# so its centre of mass sits 0.6 mm below the rim edge and it cannot tip out. The nut stands 0.6 mm proud.
BAR_BOTTOM = -76.0                # 0.9 mm above the hatch (-76.9); the bar cannot grow downward
SEAT = -73.18                     # nut seat: 2.82 mm of bar under the nut
RIM = 1.8                         # recess depth = rim height around the nut
BAR_TOP = SEAT + RIM              # -71.38 (B25 bar top was -69.8)
RECESS_AF = 5.9
OLD_TOP = -69.8                   # B25 cages, keeper boss and keeper plates reached -69.98
BAR_HALF_U = 5.05                 # same inner face as the B25 cage, keeps 1.15 mm to the hub PCB
BAR_Y = (45.6, 76.4)              # one bar per side ties both nut seats together
ANCHOR_Y = 61.                    # the B25 keeper-screw boss between the two seats
NUT_PHASE_DEG = 0.                # flats face +-X: the recess corners run along the bar, rim walls 2.1 mm

# Yaw bracket feet: posts r4.5 from the floor top (-78.0) to the bracket seat (-68.4).
FEET = [(-22.8, 5.), (-22.8, 26.), (22.8, 5.), (22.8, 26.)]
FOOT_TOP = -64.4                  # top of the bracket foot: the nut sits here
FOOT_SCREW = 18.
FOOT_HEAD_SEAT = -79.0            # screw head seat in the counterbore under the base
BASE_BOTTOM = -83.0
FLOOR_TOP = -78.0
FOOT_HOLE_RADIUS = 1.70           # 3.4 mm clearance (+0.4, F08)
HEAD_BORE_RADIUS = 3.15           # 6.3 mm for a 5.5 mm socket head (+0.8)
# The counterbore ceiling is a full ring under the M3 head (about 15 mm2, 40 MPa at 600 N).
# Bridge layers (a 3.4 mm slot and square) were tried and dropped: they halved the head seat and
# the slicer still built support. The print project puts a support blocker in each counterbore;
# the 1.45 mm ring prints as a short overhang from the counterbore wall.
FOOT_SUPPORT_BLOCKER = (3.6, BASE_BOTTOM - .5, FOOT_HEAD_SEAT + .6)   # radius, z from, z to
FOOT_NUT_FLATS = (0., 1., 0.)     # flats face +-Y (the socket does not care; kept square to the base axes)

# Wall fixes: every wall of the base that was under 2 mm and has free space next to it.
SEAT_POSTS = [(54.559600438419636, 31.5), (-54.559600438419636, 31.5), (0., -63.)]
POST_Z = (-78.0, -49.0)          # bearing-seat posts, r 5.5 outside, r 3.56 bore
POST_OUTER = 6.1                  # wall 1.94 -> 2.54 mm
LEFT_POST_KEEP_X = -57.5          # the left post keeps its open slot side (x < -57.5) as it is
CAP_TOP = -49.0
CAP_UNDERSIDE = -51.0             # cap under the seat bolt head: 1.15 -> 2.0 mm
SEAT_BOLT = 18.                   # M3 x 16 -> M3 x 18 keeps the bolt end above its nut
SEAT_BOLT_HOLE = 1.8
LID_TUNNELS = [(0., -85.), (73.6121593216773, 42.5), (-73.6121593216773, 42.5)]
TUNNEL_BORE = 3.56                # deck bolt tunnels, z -38.0 to -31.05 (bolt head seat)
TUNNEL_OUTER = 5.8                # side walls 1.0 -> 2.24 mm
TUNNEL_Z = (-38.15, -31.05)
HATCH_SEAT_FACE = -76.66          # the hatch bears on this face; nothing below it is cut

# A5 J2 keeper (A4J2LeverKeeper): the two M3 x 12 hub-bolt heads (5.5 mm) overlapped its side rail
# (0.35 mm) and its rear arm (0.58 mm) in B25. The rail and arm are widened outward into free space
# (keeping 0.4 mm inside the hatch opening, which the keeper passes when the hatch is lifted in) and
# notched around each head with 0.2 mm radial clearance.
KEEPER_BOLTS = [(30.8, 46.2), (30.8, 72.8)]
KEEPER_SEAT = -70.5
KEEPER_NOTCH = 3.15               # 0.4 mm over a 5.5 mm head: more than the 0.25 mm the keeper can float on its bolts


def keeper_fills():
    # Outer limits keep the keeper (also shifted 0.25 mm) clear of the hatch opening and the
    # rear-guide bolt while the hatch is lifted in.
    return [box(33.9, 35.6, 43.0, 73.0, -72.5, -68.4),        # rail, beside the straight opening edge
            box(33.9, 34.4, 73.0, 75.8, -72.5, -68.4),        # rail, beside the diagonal opening edge
            box(27.7, 33.0, 76.85, 77.15, -70.1, -65.8)]      # rear arm behind the second head


def keeper_cuts():
    return [cylinder(KEEPER_NOTCH, 5.0, (x, y, KEEPER_SEAT)) for x, y in KEEPER_BOLTS]


REMOVED = (
    'ServiceHatchNutKeeperLeft', 'ServiceHatchNutKeeperRight',
    'ServiceHatchNutKeeperLeftScrew', 'ServiceHatchNutKeeperRightScrew',
    'ServiceHatchNutKeeperLeftScrewInsert', 'ServiceHatchNutKeeperRightScrewInsert',
    *[f'YawBracketFoot{i}Insert' for i in range(4)],
)


def sides():
    return sorted({x for x, _ in HATCH_MOUNTS})


def bar_x(x):
    return x - BAR_HALF_U, x + BAR_HALF_U


def hatch_fills():
    shapes = []
    for x in sides():
        sense = 1. if x > 0 else -1.
        shapes.append(box(*bar_x(x), *BAR_Y, BAR_BOTTOM, BAR_TOP))
        # Close the old insert and tap bores in the keeper boss (r2.0-2.08 and r1.55) from below
        # their bottom, so no sealed void is left in the solid.
        shapes.append(cylinder(2.3, BAR_BOTTOM - (-78.4) + .1, (x, ANCHOR_Y, -78.4)))
        # A 0.2 mm3 pocket between the inner seat boss and the keeper boss becomes sealed under
        # the bar; fill it so the solid has no inner shell.
        x0, x1 = sorted((x + sense*-.6, x + sense*2.37))
        shapes.append(box(x0, x1, 56.16, 57.11, -76.05, -75.71))
    return shapes


def hatch_cuts():
    shapes = []
    for x in sides():
        # Clear the B25 cages and keeper boss above the bar, so the nuts stand in the open.
        shapes.append(box(*bar_x(x), *BAR_Y, BAR_TOP, OLD_TOP))
    for x, y in HATCH_MOUNTS:
        shapes.append(hexagon(RECESS_AF, RIM + .3, (x, y, SEAT), UP, flat_normal=(1, 0, 0)))
        # Plain clearance hole through the bar under the nut.
        shapes.append(cylinder(CLEARANCE_RADIUS, SEAT - BAR_BOTTOM + .4, (x, y, BAR_BOTTOM - .2)))
    return shapes


def foot_fills():
    # Close the insert bore inside the r4.5 post (r2.0 in CAD, r2.08 in the print mesh).
    return [cylinder(2.3, -68.4 - (-75.6), (x, y, -75.6)) for x, y in FEET]


def foot_cuts():
    shapes = []
    for x, y in FEET:
        shapes.append(cylinder(FOOT_HOLE_RADIUS, FOOT_TOP - FOOT_HEAD_SEAT + .3, (x, y, FOOT_HEAD_SEAT - .1)))
        shapes.append(cylinder(HEAD_BORE_RADIUS, FOOT_HEAD_SEAT - BASE_BOTTOM + .1, (x, y, BASE_BOTTOM - .1)))
        # 0.4 mm entry chamfer against first-layer squish.
        shapes.append(Part.makeCone(HEAD_BORE_RADIUS + .5, HEAD_BORE_RADIUS, .5, V(x, y, BASE_BOTTOM - .1), V(*UP), 360))
    return shapes


def foot_support_blockers():
    """Support-blocker volumes for the print project (not part of the CAD solid)."""
    radius, z0, z1 = FOOT_SUPPORT_BLOCKER
    return [cylinder(radius, z1 - z0, (x, y, z0)) for x, y in FEET]


def mirrored(x0, x1, sense):
    return (x0, x1) if sense > 0 else (-x1, -x0)


def wall_fills():
    shapes = []
    for x, y in SEAT_POSTS:
        ring = cylinder(POST_OUTER, POST_Z[1] - POST_Z[0], (x, y, POST_Z[0])).cut(
            cylinder(5.45, POST_Z[1] - POST_Z[0] + .2, (x, y, POST_Z[0] - .1)))
        if x < 0:
            ring = ring.cut(box(x - 10., LEFT_POST_KEEP_X, y - 10., y + 10., POST_Z[0] - 1., POST_Z[1] + 1.))
        shapes.append(ring)
        # Thicker cap under the seat bolt head (the bore is filled 0.85 mm deeper).
        shapes.append(cylinder(TUNNEL_BORE + .05, CAP_TOP - CAP_UNDERSIDE - .2, (x, y, CAP_UNDERSIDE)))
    for x, y in LID_TUNNELS:
        shapes.append(cylinder(TUNNEL_OUTER, TUNNEL_Z[1] - TUNNEL_Z[0], (x, y, TUNNEL_Z[0])).cut(
            cylinder(TUNNEL_BORE + .02, TUNNEL_Z[1] - TUNNEL_Z[0] + .2, (x, y, TUNNEL_Z[0] - .1))))
    for sense in (1., -1.):
        # 1.1 mm shell between the rear-guide socket relief (r 5.3 about y at x +-28.5, z -71)
        # and open space: thickened on the open side only, the relief stays as it is.
        relief = cylinder(5.35, 20., (sense*28.5, 90., -71.), (0., -1., 0.))
        shapes.append(box(*mirrored(21.0, 26.8, sense), 79.4, 83.85, -76.0, -73.0).cut(relief))
    # Flat underside under the knife-edge tip of the right window roof (2 mm instead of 0.1).
    shapes.append(box(40.8, 45.5, 75.4, 77.6, -65.0, -62.95))
    return shapes


def wall_cuts():
    shapes = []
    for x, y in SEAT_POSTS:
        shapes.append(cylinder(SEAT_BOLT_HOLE, CAP_TOP - CAP_UNDERSIDE + .4, (x, y, CAP_UNDERSIDE - .2)))
    for sense in (1., -1.):
        # 0.5 mm pillar left where the two side-window cuts meet, and the knife-edge end of the
        # window at y 80: removed (they only narrow the spanner room).
        shapes.append(box(*mirrored(60.3, 65.0, sense), 59.6, 63.4, -74.75, -67.55))
        shapes.append(box(*mirrored(42.5, 48.0, sense), 79.9, 84.0, -74.75, -67.55))
        # 0.1-0.4 mm horns where the hatch-boss clearance circles meet the opening lip.
        shapes.append(box(*mirrored(36.5, 41.2, sense), 46.4, 55.6, -79.0, HATCH_SEAT_FACE))
        shapes.append(box(*mirrored(36.5, 41.2, sense), 66.4, 71.0, -79.0, HATCH_SEAT_FACE))
    return shapes


def fills():
    return hatch_fills() + foot_fills() + wall_fills()


def cuts():
    return hatch_cuts() + foot_cuts() + wall_cuts()


def edit(shape):
    return check_solid(shape.fuse(fills()).cut(cuts()).removeSplitter(), 'B26 base cup')


def nut(seat, flat_normal=None):
    outline = hexagon(NUT_AF, NUT_HEIGHT, seat, UP, flat_normal=flat_normal)
    return outline.cut(cylinder(1.5, NUT_HEIGHT + .2, (seat[0], seat[1], seat[2] - .1)))


def mesh_of(shapes, path):
    solid = shapes[0].fuse(shapes[1:]) if len(shapes) > 1 else shapes[0]
    mesh = MeshPart.meshFromShape(Shape=solid, LinearDeflection=.02, AngularDeflection=.1, Relative=False)
    mesh.write(str(path))


def update_motion_geometry(doc):
    motion = json.loads(doc.R5.MotionGeometry)
    if len(motion.pop('bottom_board_service_nuts', [])) != 2:
        raise ValueError('B25 keeper metadata not found')
    motion['bottom_board_nut_seats'] = [
        {'nut_seat_mm': [x, y, SEAT], 'entry_mm': [0., 0., 17.], 'nut_phase_deg': NUT_PHASE_DEG,
         'seat': 'loose hex recess', 'recess_af_mm': RECESS_AF, 'recess_depth_mm': RIM,
         'hole_diameter_mm': 2*CLEARANCE_RADIUS} for x, y in HATCH_MOUNTS]
    motion['yaw_feet_through_bolts'] = [
        {'screw': f'YawBracketFoot{i}', 'nut': f'YawBracketFootNut{i}', 'length_mm': FOOT_SCREW,
         'seat_mm': [x, y, FOOT_HEAD_SEAT], 'axis': list(UP), 'nut_entry_mm': [0., 0., 12.]}
        for i, (x, y) in enumerate(FEET)]
    motion['bearing_seat_bolts'] = [
        {'bolt': f'seatBolt{i}', 'length_mm': SEAT_BOLT, 'seat_mm': [x, y, CAP_UNDERSIDE]}
        for i, (x, y) in enumerate([(0., -63.), (54.559600438419636, 31.5), (-54.559600438419636, 31.5)])]
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)


def apply(doc):
    update_motion_geometry(doc)
    base = doc.Part000
    replace(base, edit(detached_shape(base)))
    keeper = doc.A4J2LeverKeeper
    replace(keeper, check_solid(detached_shape(keeper).fuse(keeper_fills()).cut(keeper_cuts()).removeSplitter(),
                                'A5 J2 keeper'))
    for name in REMOVED:
        if doc.getObject(name) is None:
            raise ValueError(f'B25 object to retire is missing: {name}')
        doc.removeObject(name)
    group = doc.YawBracketFoot0.getParentGeoFeatureGroup()
    rows = []
    for i, (x, y) in enumerate(FEET):
        screw = doc.getObject(f'YawBracketFoot{i}')
        replace(screw, socket_screw(3, FOOT_SCREW, (x, y, FOOT_HEAD_SEAT), UP))
        screw.Label = f'M3 × {FOOT_SCREW:g} socket head cap screw · yaw bracket foot {i} · from below'
        seat = (x, y, FOOT_TOP)
        add_part(doc, group, f'YawBracketFootNut{i}', f'M3 hex nut · yaw bracket foot {i} · on top of the foot',
                 nut(seat, FOOT_NUT_FLATS), 'fixed')
        rows.append({'screw': screw.Name, 'nut': f'YawBracketFootNut{i}', 'screw_mm': FOOT_SCREW,
                     'head_seat_mm': [x, y, FOOT_HEAD_SEAT], 'nut_seat_mm': list(seat), 'axis': list(UP)})
    # The four loose hatch nuts on the bar tops, as CAD parts named like their hardware rows.
    hatch_group = doc.hatchBolt0.getParentGeoFeatureGroup()
    for i, (x, y) in enumerate(HATCH_MOUNTS):
        add_part(doc, hatch_group, f'hatchNut{i}', f'M3 hex nut · bottom hatch {i} · loose on the bar top',
                 nut((x, y, SEAT), (1., 0., 0.)), 'fixed')
    return rows


def geometry():
    return {
        'hatch_nut_seats': {'seat': 'loose hex recess (clearance) on the bar, plain through hole', 'seat_z_mm': SEAT,
                            'recess_af_mm': RECESS_AF, 'recess_depth_mm': RIM,
                            'bar_mm': [BAR_BOTTOM, BAR_TOP], 'hole_diameter_mm': 2*CLEARANCE_RADIUS,
                            'nut_phase_deg': NUT_PHASE_DEG, 'mounts': [list(m) for m in HATCH_MOUNTS]},
        'yaw_feet': {'screw_mm': FOOT_SCREW, 'head_seat_z_mm': FOOT_HEAD_SEAT, 'nut_seat_z_mm': FOOT_TOP,
                     'hole_diameter_mm': 2*FOOT_HOLE_RADIUS, 'head_bore_diameter_mm': 2*HEAD_BORE_RADIUS,
                     'screw_proud_of_nut_mm': round(FOOT_HEAD_SEAT + FOOT_SCREW - (FOOT_TOP + NUT_HEIGHT), 2),
                     'feet': [list(f) for f in FEET]},
        'wall_fixes': {'post_outer_radius_mm': POST_OUTER, 'post_cap_mm': round(CAP_TOP - CAP_UNDERSIDE, 2),
                       'seat_bolt_mm': SEAT_BOLT, 'deck_tunnel_outer_radius_mm': TUNNEL_OUTER,
                       'removed': ['side-window pillar', 'side-window end tips', 'hatch-lip horns'],
                       'filled': ['shell beside the rear-guide socket relief', 'right window roof tip']},
        'yaw_foot_counterbore_support_blocker': {'radius_mm': FOOT_SUPPORT_BLOCKER[0], 'z_mm': list(FOOT_SUPPORT_BLOCKER[1:]),
                                                 'centres_mm': [list(f) for f in FEET]},
        'j2_keeper': {'rail_outer_x_mm': [35.6, 34.4], 'arm_outer_y_mm': 77.15, 'head_notch_radius_mm': KEEPER_NOTCH,
                      'bolts': [list(b) for b in KEEPER_BOLTS]},
        'retired': list(REMOVED),
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--edits', type=Path, help='Write the fill and cut solids as STL for the print mesh')
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('Choose a separate output assembly')
    doc = App.openDocument(str(args.source.resolve()))
    try:
        hardware = apply(doc)
        doc.recompute()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(args.output.resolve()))
        args.output.with_suffix('.json').write_text(json.dumps(
            {'hardware': hardware, 'geometry': geometry()}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        if args.edits:
            args.edits.mkdir(parents=True, exist_ok=True)
            mesh_of(fills(), args.edits/'fills.stl')
            mesh_of(cuts(), args.edits/'cuts.stl')
            mesh_of(keeper_fills(), args.edits/'keeper_fills.stl')
            mesh_of(keeper_cuts(), args.edits/'keeper_cuts.stl')
            mesh_of(foot_support_blockers(), args.edits/'support_blockers.stl')
    finally:
        App.closeDocument(doc.Name)
