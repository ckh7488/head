from primitives import box, cylinder, holes

C3_ORIGIN = (-71.0, 22.0)
C3_HOLES = ((3.0, 50.8), (31.0, 37.9))
C3_BOTTOM = -71.0
C3_TOP = C3_BOTTOM + 1.6


def board_xy(x, y):
    return C3_ORIGIN[0]+x, C3_ORIGIN[1]-y


def board_box(x0, x1, y0, y1, z0, z1):
    a, b = board_xy(x0, y1)
    c, d = board_xy(x1, y0)
    return box(a, c, b, d, z0, z1)


def c3_mount(tray):
    centers = [board_xy(x, y) for x, y in C3_HOLES]
    tray = tray.fuse([cylinder(2.60, 3.40, (x, y, C3_BOTTOM-3.40)) for x, y in centers])
    tray = holes(tray, .83, 3.5, [(x, y, C3_BOTTOM-3.45) for x, y in centers])
    pcb = board_box(0., 34., 0., 53., C3_BOTTOM, C3_TOP)
    pcb = holes(pcb, 1.10, 2., [(x, y, C3_BOTTOM-.1) for x, y in centers])
    bodies = [
        board_box(16.65, 25.15, 46.6, 53.70, C3_TOP, C3_TOP+3.26),
        board_box(28.8, 32.9, 24.2, 33.0, C3_TOP, C3_TOP+8.7),
        board_box(2.2, 11.5, 28.7, 35.3, C3_TOP, C3_TOP+3.9),
        board_box(2.2, 11.5, 36.2, 42.8, C3_TOP, C3_TOP+3.9),
        board_box(6.0, 13.7, 44.1, 51.0, C3_TOP, C3_TOP+2.1),
        board_box(8., 24., 12., 27.7, C3_TOP, C3_TOP+1.1),
    ]
    return pcb.fuse(bodies).removeSplitter(), tray.removeSplitter()


def usb_plug():
    return board_box(14.5, 27.3, 53.70, 76.0, C3_TOP-1.55, C3_TOP+4.65)
