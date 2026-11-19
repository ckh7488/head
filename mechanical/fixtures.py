from FreeCAD import Vector as V
import Part

from primitives import box, cylinder, holes

CABLE_CENTER_Z = -57.5
CABLE_STOP_Y = 118.5
CABLE_LANES = (
    ('5V XT30', -38., 13.4, 7.2, 7.4, 4.4, 10.5, 5.8),
    ('neck XT60', -15.5, 19.6, 10.4, 11.5, 5.4, 16.0, 8.1),
    ('camera USB-A', 9.5, 18.8, 10.6, 6.8, 5.6, 12.4, 7.0),
    ('OpenRB USB-A', 34.5, 18.8, 10.6, 6.8, 5.6, 12.4, 7.0),
)
CAP_BOLTS = (-47., -28.3, -3., 22., 47.)
CAP_KEYS = (-47.35, *CAP_BOLTS[1:])
KEY_HALF_WIDTH = 1.60
BALLAST_CENTER_Y = 52.5
BALLAST_FLOOR_Z = 115.0
BALLAST_STUD_Y = 61.0
BALLAST_STUD_X = (-24.2, 24.2)
BALLAST_MOUNT_XZ = tuple((x, z) for x in (-28., 28.) for z in (143., 150.))
PLATE_MM = (40., 25., 3.)
PLATE_COUNT = 12
STEEL_KG_MM3 = 7.85e-6


def captive_cables(base):
    seam = CABLE_CENTER_Z
    stop = CABLE_STOP_Y
    lower = box(-50.5, 50.5, 77., 125., -68.5, seam)
    lower = lower.fuse([box(x-7.4, x+7.4, 77., 125., -78., -65.8) for x in (-28.5, 28.5)])
    lower = lower.cut(cylinder(93.14, 36., (0., 0., -83.)))
    cap = box(-50.5, 50.5, 99., 125., seam, -49.1)
    for _, x, width, height, opening_x, opening_z, _, _ in CABLE_LANES:
        pocket = box(x-width/2, x+width/2, 76., stop, seam-height/2, seam+height/2)
        exit_slot = box(x-opening_x/2, x+opening_x/2, stop-.1, 126.,
                        seam-opening_z/2, seam+opening_z/2)
        lower = lower.cut([pocket, exit_slot])
        cap = cap.cut([pocket, exit_slot])
        base = base.cut(box(x-width/2-.2, x+width/2+.2, 74., 96.,
                            seam-height/2-.2, seam+height/2+.2))

    keys = [box(x-KEY_HALF_WIDTH, x+KEY_HALF_WIDTH, 106.5, 111.5, seam-.35, seam+2.6) for x in CAP_KEYS]
    lower = lower.fuse(keys)
    key_cut = KEY_HALF_WIDTH+.13
    cap = cap.cut([box(x-key_cut, x+key_cut, 106.37, 111.63, seam-.1, seam+2.73) for x in CAP_KEYS])
    cap = holes(cap, 1.68, 10., [(x, 121.6, seam-.6) for x in CAP_BOLTS])
    lower = holes(lower, 2.10, 4.25, [(x, 121.6, seam-4.20) for x in CAP_BOLTS])
    lower = holes(lower, 1.68, 7.4, [(x, 121.6, seam-7.35) for x in CAP_BOLTS])

    seats = [(x, 93.6, -71.) for x in (-28.5, 28.5)]
    lower = holes(lower, 1.74, 19., [(x, 81.5, z) for x, _, z in seats], (0, 1, 0))
    lower = holes(lower, 4.35, 33., seats, (0, 1, 0))
    base = holes(base, 1.74, 19., [(x, 77.5, z) for x, _, z in seats], (0, 1, 0))
    base = holes(base, 4.35, 6.25, [(x, 77.5, z) for x, _, z in seats], (0, 1, 0))
    return base.removeSplitter(), lower.removeSplitter(), cap.removeSplitter()


def cable_wall_fixture(base):
    wall = base.common(box(-51., 51., 77.5, 94., -83., -48.))
    footprint = box(-51., 51., 75.5, 93.1, -86.3, -81.9)
    return wall.fuse(footprint).removeSplitter()


def ballast_mount(frame):
    bosses = [(x, 26.6, z) for x, z in BALLAST_MOUNT_XZ]
    frame = frame.fuse([cylinder(3.45, 4.4, p, (0, 1, 0)) for p in bosses])
    return holes(frame, 2.10, 4.3, [(x, 26.8, z) for x, z in BALLAST_MOUNT_XZ], (0, 1, 0)).removeSplitter()


def rear_ballast():
    mount = box(-34.5, 34.5, 31., 35.3, 137.8, 155.0)
    floor = box(-26.3, 26.3, 37.5, 67.4, BALLAST_FLOOR_Z-3.7, BALLAST_FLOOR_Z)
    top = BALLAST_FLOOR_Z+PLATE_COUNT*PLATE_MM[2]
    wall_height = top-.2
    cheeks = [
        box(x0, x1, y0, y1, 114.5, wall_height)
        for x0, x1 in ((-22.9, -20.35), (20.35, 22.9))
        for y0, y1 in ((37.5, 55.7), (65.35, 67.4))
    ] + [
        box(-21., 21., 37.5, 39.65, 114.5, wall_height),
        box(-21., 21., 65.35, 67.4, 114.5, wall_height),
    ]
    ribs = []
    for x in (-26.2, 22.):
        points = [V(x, y, z) for y, z in ((31.6, 147.), (35.2, 150.), (47., 137.),
                                            (57., 114.4), (39.4, 112.4), (31.8, 136.5))]
        ribs.append(Part.Face(Part.makePolygon(points + points[:1])).extrude(V(4.2, 0., 0.)))
    ears = [cylinder(3.8, 3.7, (x, BALLAST_STUD_Y, BALLAST_FLOOR_Z-3.7))
            for x in BALLAST_STUD_X]
    tray = mount.fuse([floor, *cheeks, *ribs, *ears])
    tray = holes(tray, 1.67, 5.2, [(x, 30.5, z) for x, z in BALLAST_MOUNT_XZ], (0, 1, 0))
    tray = holes(tray, 4.1, 28., [(x, 35.3, z) for x, z in BALLAST_MOUNT_XZ], (0, 1, 0))
    stems = [(x, BALLAST_STUD_Y, 110.9) for x in BALLAST_STUD_X]
    tray = holes(tray, 1.68, 6., stems)
    cover = box(-19.85, 19.85, 43.4, 61.6, top, top+3.).fuse([
        box(-24.7, -19., 58.6, 63.4, top, top+3.),
        box(19., 24.7, 58.6, 63.4, top, top+3.),
        *[cylinder(3.8, 3., (x, BALLAST_STUD_Y, top)) for x in BALLAST_STUD_X],
    ])
    cover = holes(cover, 1.68, 5., [(x, y, top-.5) for x, y, _ in stems])
    stack = box(-20., 20., 40., 65., BALLAST_FLOOR_Z, BALLAST_FLOOR_Z+PLATE_COUNT*PLATE_MM[2])
    return tray.removeSplitter(), cover.removeSplitter(), stack


def ballast_stud(x):
    y = BALLAST_STUD_Y
    floor = BALLAST_FLOOR_Z-3.7
    nut = BALLAST_FLOOR_Z+PLATE_COUNT*PLATE_MM[2]+3.
    return cylinder(1.50, 50., (x, y, floor)).fuse([
        cylinder(3.25, 3.0, (x, y, floor-3.0)),
        cylinder(3.25, 3.25, (x, y, nut)),
    ]).removeSplitter()


def fixture_parameters():
    lanes = []
    for name, x, width, height, slot_x, slot_z, shoulder_x, shoulder_z in CABLE_LANES:
        lanes.append({'name': name, 'x_mm': x, 'pocket_mm': [width, height],
                      'slot_mm': [slot_x, slot_z], 'minimum_shoulder_mm': [shoulder_x, shoulder_z]})
    return {
        'cables': {'lanes': lanes, 'stop_y_mm': CABLE_STOP_Y, 'center_z_mm': CABLE_CENTER_Z,
                   'cap_bolts_x_mm': list(CAP_BOLTS), 'cap_bolt_y_mm': 121.6,
                   'cap_keys_x_mm': list(CAP_KEYS), 'cap_key_cut_half_width_mm': KEY_HALF_WIDTH+.13},
        'ballast': {'plate_mm': list(PLATE_MM), 'maximum_plates': PLATE_COUNT,
                    'plate_mass_kg': PLATE_MM[0]*PLATE_MM[1]*PLATE_MM[2]*STEEL_KG_MM3,
                    'floor_z_mm': BALLAST_FLOOR_Z, 'center_y_mm': BALLAST_CENTER_Y,
                    'mount_xz_mm': list(BALLAST_MOUNT_XZ)},
    }
