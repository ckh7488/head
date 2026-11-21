"""Build the printed clevises for the B22 steel pitch-limit link."""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App
import Part

from build_b17_service import SCREW_HEIGHTS, SCREW_X
from build_b19_review_fixes import add_part, replace
from build_b21_fasteners import B16_CAD, check_solid, detached_shape
from primitives import box, cylinder, print_mesh


LOWER_CENTER = (-44., 26., 87.)
UPPER_CENTER = (-44., 37., 113.)
PIN_LENGTH = 20.
PIN_RADIUS = 2.
INLET_HOUSING = 14.5
STOP_HOUSING = 11.9
STOP_RADIUS = 3.6
EJECT_BORE = 2.6
PIN_BORE = 4.10
PRINT_PIN_BORE = 3.90
GAP = 3.80
EAR_RADIUS = 6.00
RETENTION_LENGTH = 3.
RETENTION_OFFSET_X = 11.9
RETENTION_ENTRY_Y = 4.50
RETENTION_AXIS = (0., -1., 0.)
PIN_AXIS = (-1., 0., 0.)

ANCHORS = (
    ('Lower', LOWER_CENTER, 'Part011', 'pan'),
    ('Upper', UPPER_CENTER, 'Part019', 'head'),
)

LOWER_BASE = (
    (13.0, -55.5, -31.5, 69.2, 94.0),
    (17.4, -53.2, -30.0, 69.5, 93.8),
    (21.5, -52.5, -29.5, 71.0, 93.0),
    (27.0, -51.6, -29.5, 72.5, 92.5),
    (30.0, -48.5, -30.5, 76.5, 90.3),
)
UPPER_BASE = (
    (-64.10, -4.20, 29.50, 108.20, 126.30),
    (-62.00, -4.20, 33.20, 108.20, 133.00),
    (-57.00, -4.10, 34.50, 108.20, 133.50),
    (-54.00, 19.90, 39.80, 108.20, 132.00),
    (-49.00, 21.00, 43.00, 106.40, 130.00),
    (-39.00, 21.50, 43.00, 106.00, 126.30),
    (-31.00, 23.50, 40.00, 107.00, 122.00),
)


def wire(vertices):
    points = [App.Vector(*point) for point in vertices]
    return Part.makePolygon(points + [points[0]])


def loft(sections, along_x):
    profiles = []
    for station, first, last, low, high in sections:
        cross = [(first, low), (last, low), (last, high), (first, high)]
        coordinates = ([(station, y, z) for y, z in cross] if along_x else
                       [(x, station, z) for x, z in cross])
        profiles.append(wire(coordinates))
    return Part.makeLoft(profiles, True, True)


def slot_opening(center, upper):
    x, y, z = center
    front, bottom = (y-13., z-23.) if upper else (y-11., z-11.9)
    return box(x-GAP/2, x+GAP/2, front, y+17., bottom, z+25.)


def clevis_blank(center, upper):
    x, y, z = center
    barrel = cylinder(EAR_RADIUS, INLET_HOUSING+PIN_LENGTH/2,
                      (x+INLET_HOUSING, y, z), PIN_AXIS)
    end = cylinder(STOP_RADIUS, STOP_HOUSING-PIN_LENGTH/2+.25,
                   (x-PIN_LENGTH/2+.25, y, z), PIN_AXIS)
    foundation = loft(UPPER_BASE if upper else LOWER_BASE, along_x=upper)
    anchor = foundation.fuse([barrel, end])
    if upper:
        anchor = anchor.cut(box(-56.08, -27.5, -8., 19.7, 99., 132.))
    return check_solid(anchor, 'pitch link clevis blank')


def shaft_clearance():
    return (cylinder(4.12, 24., (-43., 0., 112.), PIN_AXIS),
            cylinder(1.55, 36., (-60.5, 0., 99.)))

def machining(center, printed):
    x, y, z = center
    bore = (PRINT_PIN_BORE if printed else PIN_BORE)/2
    pin_end = x - PIN_LENGTH/2
    bore_path = cylinder(bore, INLET_HOUSING+PIN_LENGTH/2+.2,
                         (x+INLET_HOUSING+.2, y, z), PIN_AXIS)
    eject = cylinder(EJECT_BORE/2, 14.2,
                     (pin_end+.2, y, z), PIN_AXIS)
    retain_start = (x+RETENTION_OFFSET_X, y+RETENTION_ENTRY_Y+.04, z)
    access = cylinder(1.86, EAR_RADIUS-RETENTION_ENTRY_Y+.18, retain_start, (0., 1., 0.))
    tap_radius = 1.30 if printed else 1.52
    tap = cylinder(tap_radius, RETENTION_LENGTH+.23, retain_start, RETENTION_AXIS)
    return (bore_path, eject, tap, access)


def bearing_crown():
    sections = ((102., -55.44, -46.6, -3.6, 15.8),
                (112., -55.44, -46.0, -8.1, 15.85),
                (120., -55.44, -46.0, -10.8, 15.85),
                (123., -55.44, -46.0, -10.7, 14.00),
                (126., -55.44, -46.0, -10.45, 11.70),
                (129., -55.44, -46.0, -10.2, 7.90))
    profiles = [wire([(xmin, ymin, z), (xmax, ymin, z), (xmax, ymax, z), (xmin, ymax, z)])
                for z, xmin, xmax, ymin, ymax in sections]
    crown = Part.makeLoft(profiles, True, True)
    return crown.cut(cylinder(8.13, 12., (-45., 0., 112.), PIN_AXIS))


def relief():
    # Sweep clearance for the existing right jaw-stop toe before the skull becomes the limit.
    return box(46.9, 48.7, -4.6, -1.75, 70.3, 80.2)


def released_travel_reliefs():
    profile = wire([(-55.65, -11.5, 124.), (-55.65, -10.72, 124.),
                    (-55.65, -10.20, 125.2), (-55.65, -9.85, 129.3),
                    (-55.65, -11.5, 129.3)])
    cradle = Part.Face(profile).extrude(App.Vector(9.85, 0., 0.))
    jaw_arm = box(-50.3, -47.4, -3.8, -3.2, 81.65, 86.85)
    return cradle, jaw_arm


def geometry(original, center, upper, printed):
    blank = clevis_blank(center, upper)
    cuts = (slot_opening(center, upper), *machining(center, printed))
    additions = [blank] if upper else [blank, bearing_crown()]
    final = original.fuse(additions).cut(list(cuts))
    if upper:
        final = final.cut(list(shaft_clearance()))
    else:
        final = final.cut([relief(), *released_travel_reliefs()])
    return check_solid(final, 'pitch link clevis'), blank


def printable_yoke(yoke):
    ref = App.openDocument(str(B16_CAD.resolve()))
    try:
        unpocketed = detached_shape(ref.Part011)
    finally:
        App.closeDocument(ref.Name)
    # Restore the B21 Ø2.6 tap pilots in the print. CAD retains the fitted major diameters.
    sleeves, pilots = [], []
    for z in SCREW_HEIGHTS:
        base = (SCREW_X, 14.18, z)
        sleeves.append(unpocketed.common(cylinder(1.65, 4.6, base, (0, 1, 0))))
        pilots.append(cylinder(1.30, 4.6, base, (0, 1, 0)))
    return check_solid(yoke.fuse(sleeves).cut(pilots), 'B22 printable pitch yoke')


def hardware(doc):
    rows = []
    group = doc.Part019.getParentGeoFeatureGroup()
    for end, (x, y, z), base, motion in ANCHORS:
        pin_id = f'PitchLimit{end}Pin'
        retainer_id = f'PitchLimit{end}Retainer'
        pin = ('pin', pin_id, 'Ground Ø4 × 20 pitch-link pin', PIN_RADIUS,
               PIN_LENGTH, (x+PIN_LENGTH/2, y, z), PIN_AXIS, {})
        retainer = ('set_screw', retainer_id, 'M3 × 3 flat-point socket set screw',
                    1.5, RETENTION_LENGTH,
                    (x+RETENTION_OFFSET_X, y+RETENTION_ENTRY_Y-RETENTION_LENGTH, z),
                    (0., 1., 0.), {'key_af_mm': 1.5})
        for kind, name, label, radius, length, start, axis, fields in (pin, retainer):
            add_part(doc, group, name, label, cylinder(radius, length, start, axis), motion)
            rows.append(dict(name=name, motion=motion, kind=kind, **fields,
                             skip=[base, 'PitchLimitLink', pin_id, retainer_id],
                             shapes=[['cyl', radius, length, start, axis]]))
    return rows


def build(source, output, print_dir):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate CAD output')
    doc = App.openDocument(str(source.resolve()))
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        print_dir.mkdir(parents=True, exist_ok=True)
        for (end, center, name, _), filename in zip(ANCHORS, ('07_yoke-B22', '09_head_frame-B22')):
            original = detached_shape(doc.getObject(name))
            upper = end == 'Upper'
            assembly, blank = geometry(original, center, upper, printed=False)
            printable, _ = geometry(original, center, upper, printed=True)
            if not upper:
                printable = printable_yoke(printable)
            replace(doc.getObject(name), assembly)
            print_mesh(printable, print_dir/f'{filename}.stl', 'y+')
            blank.exportStep(str(print_dir/f'pitch-clevis-{end.lower()}.step'))
        rows = hardware(doc)
        motion = json.loads(doc.R5.MotionGeometry)
        motion['pitch_clevises'] = dict(lower=list(LOWER_CENTER), upper=list(UPPER_CENTER),
                                       slot_width_mm=GAP, ear_width_mm=(PIN_LENGTH-GAP)/2,
                                       pilot_bore_mm=PRINT_PIN_BORE, target_bore_mm=PIN_BORE,
                                       eject_bore_mm=EJECT_BORE,
                                       nominal_axial_float_mm=.40)
        doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)
        (print_dir/'pitch-hardware.json').write_text(json.dumps(rows, indent=2)+'\n')
        doc.recompute()
        doc.saveAs(str(output.resolve()))
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('print_dir', type=Path)
    build(**vars(parser.parse_args()))
