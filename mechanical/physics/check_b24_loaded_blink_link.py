"""Check the B24 front-shell gaps using both elastically displaced link pins."""

from argparse import ArgumentParser
from hashlib import file_digest
from itertools import product
import json
from math import atan2, degrees, pi, radians
from pathlib import Path

import fcl
import manifold3d as md
import numpy as np
import trimesh
from trimesh.collision import mesh_to_BVH

from blink_fea import measure
from check_b19_assembly import solid
from check_head import pose, rotation


ENVELOPE_NM = {'mixed': ((.0256, .009), (.009, .0256)),
               'full_unilateral': ((.036, 0.), (0., .036))}
LINKS = ('Part057', 'Part060')
LIDS = ('Part078', 'Part079')
SHELL = 'Part073'
MODULUS_MPA = 500.


def digest(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def neutral_pins(configuration):
    blink = configuration['motion_geometry']['blink']
    lid = configuration['motion_geometry']['eye_pitch']['cradle_axis_mm'][1:]
    pivots = np.array([lid, blink['shaft_yz_mm']])
    phase = radians(blink['phase_deg'])
    return pivots + blink['lid_radius_mm']*np.array([np.cos(phase), np.sin(phase)])


def link_transform(rest, loaded):
    reference = rest[1]-rest[0]
    displaced = loaded[1]-loaded[0]
    angle = degrees(atan2(displaced[1], displaced[0])-atan2(reference[1], reference[0]))
    transform = rotation(angle, (1., 0., 0.), (0., *rest[0]))
    transform[1:3, 3] += loaded[0]-rest[0]
    return transform


def clearances(configuration, meshes, rows):
    actors = {name: fcl.CollisionObject(mesh_to_BVH(mesh)) for name, mesh in meshes.items()}
    rest = neutral_pins(configuration)
    request = fcl.DistanceRequest(enable_nearest_points=True)
    minima = {kind: {} for kind in ENVELOPE_NM}
    overlaps = {kind: [] for kind in ENVELOPE_NM}
    shell = solid(meshes[SHELL])
    for row in rows:
        crank_torques = tuple(abs(torque) for torque in row['crank_torques_Nm'])
        kind = 'mixed' if crank_torques in ENVELOPE_NM['mixed'] else 'full_unilateral'
        for side, (link, lid) in enumerate(zip(LINKS, LIDS, strict=True)):
            link_matrix = link_transform(rest, np.asarray(row['link_pins_yz_mm'][side]))
            lid_angles = (0., 0., 0., row['lid_deg'][side], 0.)
            lid_matrix = pose(configuration['world_motion'][lid], lid_angles, configuration)
            for name, transform in ((link, link_matrix), (lid, lid_matrix)):
                actor = actors[name]
                actor.setTransform(fcl.Transform(transform[:3, :3].copy(), transform[:3, 3].copy()))
                result = fcl.DistanceResult()
                gap = fcl.distance(actor, actors[SHELL], request, result)
                if name not in minima[kind] or gap < minima[kind][name]['gap_mm']:
                    minima[kind][name] = {'gap_mm': gap, 'command_deg': row['command_deg'],
                                          'lid_deg': row['lid_deg'], 'shaft_deg': row['shaft_deg'],
                                          'crank_torques_Nm': row['crank_torques_Nm']}
                if gap <= 0.:
                    intersection = shell ^ solid(meshes[name].copy().apply_transform(transform))
                    overlaps[kind].append({'part': name, 'command_deg': row['command_deg'],
                                           'crank_torques_Nm': row['crank_torques_Nm'],
                                           'volume_mm3': intersection.volume()})
    return minima, overlaps


def web_strength(stock, modified, configuration):
    lower_pin, upper_pin = neutral_pins(configuration)
    link_vector = upper_pin-lower_pin
    link_angle = degrees(atan2(*link_vector))
    thickness = 2.60
    plate = md.Manifold.cube((thickness, 60., 60.)).translate((-50.55, -50., 100.))
    web = (solid(modified) ^ plate).translate((0., *(-lower_pin))).rotate((link_angle, 0., 0.))
    sections = []
    for station in np.arange(2., 34., .1):
        slab = md.Manifold.cube((20., 35., .05)).translate((-60., -17.5, station-.025))
        sections.append(((web ^ slab).volume()/.05, float(station)))
    area, station = min(sections)
    inertia = area*thickness**2/12.
    euler = pi**2*MODULUS_MPA*inertia/(link_vector@link_vector)
    boss = md.Manifold.cylinder(15., 2.5, circular_segments=120).rotate((0., 90., 0.))
    boss = boss.translate((-54., *lower_pin))
    removed_from_boss = ((solid(stock)-solid(modified)) ^ boss).volume()
    return {'min_net_web_mm2': area, 'weakest_web_station_mm': station,
            'min_pinned_Euler_N': euler, 'removed_from_lower_pin_boss_mm3': removed_from_boss}


def verify(cad, stock_link, size, samples):
    configuration = json.loads((cad/'cad_parts.json').read_text())
    rig = configuration['motion_geometry']
    mesh_paths = {name: cad/'world'/f'{name}.stl' for name in (*LINKS, *LIDS, SHELL)}
    meshes = {name: trimesh.load_mesh(path) for name, path in mesh_paths.items()}
    cases = [(sign*left, sign*right) for sign, options in product((-1., 1.), ENVELOPE_NM.values())
             for left, right in options]
    _, rows = measure(cad, rig['blink'], size, modulus=MODULUS_MPA,
                      link_load_cases=cases, link_angles=samples)
    minima, overlaps = clearances(configuration, meshes, rows)
    mixed = minima['mixed']
    return {
        'cad_sha256': configuration['source_sha256'],
        'point_load_N': 1.,
        'point_load_converted_to_input_torque_Nm': .0166,
        'modeled_bilateral_drag_torque_Nm': [.009, .009],
        'rail_mesh_mm': size,
        'modulus_MPa': MODULUS_MPA,
        'command_angle_samples_deg': samples.tolist(),
        'actor_mesh_sha256': {name: digest(path) for name, path in mesh_paths.items()},
        'rail_step_sha256': digest(cad/'blink_rail.step'),
        'baseline_left_link_sha256': digest(stock_link),
        'mixed_E500_min_link_clearance_mm': min(mixed[name]['gap_mm'] for name in LINKS),
        'mixed_E500_min_lid_clearance_mm': min(mixed[name]['gap_mm'] for name in LIDS),
        'mixed_E500': {'witnesses': mixed, 'contacts': overlaps['mixed']},
        'full_unilateral_E500': {'witnesses': minima['full_unilateral'], 'contacts': overlaps['full_unilateral']},
        'rim_removed_mm3': rig['blink_link_relief']['removed_mm3'],
        **web_strength(trimesh.load_mesh(stock_link), meshes[LINKS[0]], configuration),
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('stock_link', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--mesh-mm', type=float, default=1.45)
    args = parser.parse_args()
    if not np.isfinite(args.mesh_mm) or args.mesh_mm <= 0.:
        parser.error('FE mesh size must be positive and finite')
    q = np.r_[np.arange(0., 87., 3.), np.arange(87., 90.01, .25)]
    data = verify(args.cad, args.stock_link, args.mesh_mm, q)
    args.report.write_text(json.dumps(data, indent=2)+'\n')
