"""Check the stock 2.5 mm L-key at the right pitch coupling."""

from hashlib import sha256

import numpy as np
from shapely.geometry import Polygon
import trimesh as tr


def oem_head_approaches(source, cad_sha, world, screws):
    import FreeCAD as App

    from build_b21_fasteners import detached_shape
    from primitives import cylinder

    if source is None or sha256(source.read_bytes()).hexdigest() != cad_sha:
        return {'status': 'unknown', 'reason': 'The native horn must match the world export'}
    doc = App.openDocument(str(source.resolve()))
    try:
        horn, motor = (detached_shape(doc.getObject(name)) for name in ('Part016', 'Part018'))
        evidence = {}
        for screw in screws:
            size, length, seat, axis = world.screw(screw)
            if size != 2 or length != 8. or not np.allclose(axis, (-1., 0., 0.)):
                raise ValueError(f'{screw} must retain the stock M2×8 hardware')
            head_sweep = cylinder(1.93+.15, 2.+length+3., seat, (1., 0., 0.))
            tip_check = cylinder(.89, length+.25, seat, axis)
            evidence[screw] = {'head_sweep_overlap_mm3': horn.common(head_sweep).Volume,
                               'deeper_tip_overlap_mm3': motor.common(tip_check).Volume}
    finally:
        App.closeDocument(doc.Name)
    passed = len(evidence) == 4 and all(max(row.values()) <= 1e-7 for row in evidence.values())
    return {'status': 'pass' if passed else 'fail', 'cad_sha256': cad_sha, 'radial_head_reserve_mm': .15,
            'extra_tip_length_mm': .25, 'stations': evidence}


def key_approach(world, installed, screw):
    from check_b19_assembly import cylinder, sweep

    size, length, seat, axis = world.screw(screw)
    if size != 3 or not np.allclose(axis, (0., 0., -1.)) or length != 8.:
        return {'status': 'unknown', 'reason': 'Missing standard vertical M3×8 neck drive screw'}
    # Model a common L-key with a 15 mm short leg and 55 mm long leg.
    short, long, reserve = 15., 55., .15
    radius = 2.5/np.sqrt(3.) + reserve
    tip = np.asarray(seat) + (0., 0., 1.35)
    elbow = tip + (0., 0., short)
    shaft = cylinder(radius, short, tip, (0., 0., 1.))
    fixed = [name for name in installed if name != screw]
    fixture = 'PitchDriveHexGauge'
    failures = {}
    try:
        for orientation_deg in (-90., 90., 0., 180.):
            angle = np.radians(orientation_deg)
            outward = (np.cos(angle), np.sin(angle), 0.)
            handle = cylinder(radius, long, elbow, outward)
            world.cache[fixture] = tr.boolean.union((shaft, handle), engine='manifold')
            entry = sweep(world, [fixture], fixed, (0., 0., 22.))
            sweep_angle = np.radians(np.linspace(orientation_deg-30., orientation_deg+30., 13))
            end_arc = np.column_stack((np.cos(sweep_angle), np.sin(sweep_angle))) * long
            # Include the difference between each arc and its polygon chord.
            sagitta = long*(1.-np.cos(np.radians(2.5)))
            sector = Polygon(np.vstack(((0., 0.), end_arc))).buffer(radius+sagitta)
            turn = tr.creation.extrude_polygon(sector, 2.*radius)
            turn.apply_translation(elbow - (0., 0., radius))
            world.cache[fixture] = turn
            stroke = sweep(world, [fixture], fixed, (0., 0., 0.))
            if not entry and not stroke:
                return {'status': 'pass', 'key_across_flats_mm': 2.5, 'nearby_geometry_reserve_mm': reserve,
                        'short_leg_mm': short, 'long_leg_mm': long, 'entry_from_above_mm': 22.,
                        'elbow_mm': elbow.tolist(), 'handle_direction_deg': orientation_deg, 'swept_turn_deg': 60.}
            failures[str(orientation_deg)] = [dict(parts=list(pair), **hit) for pair, hit in (entry | stroke).items()]
    finally:
        world.cache.pop(fixture, None)
    return {'status': 'fail', 'clashes': failures}
