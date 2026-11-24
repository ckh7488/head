"""Check the B25 internal J2 keeper and its unpowered bench installation."""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import sys

import FreeCAD as App
import Part

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_b25_j2_a4_service import native_targets
from check_b25_j2_disconnect import DROP, collision_volumes
from export_cad import world_shape
from primitives import cylinder

KEEPER = 'A4J2LeverKeeper'
MOUNTING_SCREWS = ('HubBolt3', 'HubBolt4')
MATING_DEPTH = 5.9  # A4 assembly report and AMASS plug drawing
BENCH_LIFT = 12.
DRIVER_RADIUS = 2.8
DRIVER_LENGTH = 35.
V = App.Vector


def vertical_sweep_hits(keeper, travel, obstacles, omitted=()):
    offset = V(0., 0., travel)
    sweep = [keeper, keeper.translated(offset)]
    for face in keeper.Faces:
        surface = face.Surface
        if isinstance(surface, Part.Plane):
            if abs(surface.Axis.z) > 1.e-6:
                sweep.append(face.extrude(offset))
        elif not isinstance(surface, Part.Cylinder) or abs(surface.Axis.z) < 1. - 1.e-6:
            raise ValueError('The keeper sweep requires planar faces and vertical bores.')
    results = {}
    for solid in sweep:
        for name, volume in collision_volumes(solid, obstacles, omitted).items():
            results[name] = max(volume, results.get(name, 0.))
    return results


def check(document):
    fixed, hatch = native_targets(document)
    hatch.update((name, world_shape(document.getObject(name))) for name in ('A4W8', 'A4W9'))
    keeper = hatch[KEEPER]
    plug = hatch['A4J2FemaleEnvelope']
    remove_for_install = (KEEPER, *MOUNTING_SCREWS)
    collisions = {
        'seated': collision_volumes(keeper, {**fixed, **hatch}, remove_for_install),
        'bench_installation': vertical_sweep_hits(keeper, BENCH_LIFT, hatch, remove_for_install),
        'hatch_lowering': vertical_sweep_hits(keeper, -DROP, fixed),
    }
    drivers = {}
    for screw in MOUNTING_SCREWS:
        bounds = hatch[screw].BoundBox
        origin = (bounds.Center.x, bounds.Center.y, bounds.ZMax)
        driver = cylinder(DRIVER_RADIUS, DRIVER_LENGTH, origin)
        drivers[screw] = {'origin_mm': origin, 'intersections_mm3': collision_volumes(driver, hatch, (screw,))}
    plug_overlaps = {
        str(withdrawal): keeper.common(plug.translated(V(0., withdrawal, 0.))).Volume
        for withdrawal in (0., .25, .30, 1.50, MATING_DEPTH)
    }
    if (any(collisions.values()) or any(driver['intersections_mm3'] for driver in drivers.values())
            or plug_overlaps[str(MATING_DEPTH)] <= 1.e-5):
        raise ValueError('The J2 keeper failed the CAD clearance or retention witness.')
    return {
        'scope': 'Rigid keeper and expanded XT30U-F envelope. Confirm shoulder engagement and retention on hardware.',
        'bench_lift_mm': BENCH_LIFT,
        'hatch_drop_mm': DROP,
        'driver_radius_mm': DRIVER_RADIUS,
        'driver_length_mm': DRIVER_LENGTH,
        'keeper_intersections_mm3': collisions,
        'driver_approach': drivers,
        'expanded_plug_overlap_mm3_by_axial_withdrawal_mm': plug_overlaps,
    }


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    args = parser.parse_args()
    document = App.openDocument(str(args.cad))
    try:
        result = {'cad_sha256': sha256(args.cad.read_bytes()).hexdigest(), **check(document)}
        print(json.dumps(result, indent=2))
    finally:
        App.closeDocument(document.Name)


if __name__ == '__main__':
    main()
