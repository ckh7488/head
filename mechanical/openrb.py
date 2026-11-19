from primitives import box, cylinder, holes

WIDTH = 25.
LENGTH = 66.
ORIGIN = (40., -44.25)
# Orthographic pinout in the ROBOTIS manual, scaled to the stated 25 × 66 mm board.
HOLES = tuple((x, y) for x in (2.25, 22.75) for y in (2.25, 63.75))
BOTTOM = -68.5
TOP = BOTTOM + 1.6
NUT_SEAT = BOTTOM - 5.86
HEADER_PINS = ((1.2, 3.4), (21.6, 23.8))


def board_xy(x, y):
    return ORIGIN[0] + x, ORIGIN[1] + y


def board_box(x0, x1, y0, y1, height, z=TOP):
    a, b = board_xy(x0, y0)
    c, d = board_xy(x1, y1)
    return box(a, c, b, d, z, z + height)


def usb_plug():
    return board_box(6.35, 18.75, -18.0, -.25, 6.2, TOP - 1.45)


def board_model():
    pcb = board_box(0., WIDTH, 0., LENGTH, TOP - BOTTOM, BOTTOM)
    pcb = holes(pcb, 1.20, 2., [(*board_xy(x, y), BOTTOM - .2) for x, y in HOLES])
    bodies = [
        board_box(7.9, 17.2, -.25, 7.9, 3.35),
        board_box(-.2, 6., 14.2, 24.4, 6.45),
        board_box(19., 25.2, 14.2, 24.4, 6.45),
        board_box(8.1, 12.1, 14.2, 24.4, 8.5),
        board_box(12.7, 17.1, 14.2, 24.4, 8.5),
        board_box(.95, 3.65, 25.6, 61.0, 8.6),
        board_box(21.35, 24.05, 25.6, 61.0, 8.6),
        board_box(8.7, 16.65, 59., 66.75, 10.25),
        board_box(14.2, 20., 53., 58.6, 6.1),
        board_box(8.15, 16.9, 37.5, 46.1, 1.5),
        board_box(9.4, 15.95, 60.6, 64.9, 2.2, BOTTOM - 2.2),
    ]
    bodies.extend(board_box(lo, hi, 26.3, 60.7, 1.9, BOTTOM - 1.9) for lo, hi in HEADER_PINS)
    return pcb.fuse(bodies).removeSplitter()


def carrier(tray):
    centers = [board_xy(x, y) for x, y in HOLES]
    support = tray.fuse([cylinder(3.30, BOTTOM + 74.6, (x, y, -74.6)) for x, y in centers])
    pin_space = [board_box(lo - .35, hi + .35, 25.95, 61.05, 2.30, BOTTOM - 2.25)
                 for lo, hi in HEADER_PINS]
    return support.cut(pin_space)
