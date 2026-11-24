"""Estimate PETG rail deflection with the head-frame screws clamped."""

from argparse import ArgumentParser
from itertools import product
import json
from math import atan2, cos, degrees, pi, radians, sin
from pathlib import Path

import numpy as np
from scipy.sparse.linalg import splu
from skfem import Basis, ElementTetP1, ElementVector, asm, condense
from skfem.models.elasticity import lame_parameters, linear_elasticity

from blink import linkage_forces
from cable_fea import mesh_step, traction


def stress_bounds(basis, field, lame, shear):
    gradient = basis.interpolate(field).grad
    strain = (gradient + gradient.swapaxes(0, 1))/2
    trace = np.einsum('iijk->jk', strain)
    identity = np.eye(3)[:, :, None, None]
    stress = 2*shear*strain + lame*identity*trace
    deviator = 2*shear*(strain-identity*trace/3)
    von_mises = np.sqrt(1.5*(deviator**2).sum(axis=(0, 1))).mean(axis=1)
    # The production plate rotates the rail +90° about CAD X. Build Z is CAD Y.
    layer_normal = stress[1, 1]
    layer_shear = np.linalg.norm(stress[1, [0, 2]], axis=0)
    return np.array([np.percentile(von_mises, 99), von_mises.max(),
                     max(0., layer_normal.max()), max(0., -layer_normal.min()), layer_shear.max()])


def link_angle(pivot, from_pin, arm, length, reference):
    delta = from_pin-pivot
    distance = np.linalg.norm(delta, axis=-1)
    cosine = (distance**2+arm**2-length**2)/(2*distance*arm)
    if not np.all(np.abs(cosine) <= 1.):
        raise ValueError('An elastically displaced blink link cannot reach its other pin')
    line = np.arctan2(delta[..., 1], delta[..., 0])
    bend = np.arccos(cosine)
    first = (line-bend-reference+pi) % (2*pi)-pi
    second = (line+bend-reference+pi) % (2*pi)-pi
    return reference+np.where(np.abs(first) <= np.abs(second), first, second)


def elastic_linkage(layout, lid, angle, centers):
    """Solve the planar linkage for one or more sets of rail-centre displacements."""
    left, right, motor_low, motor_high = np.moveaxis(centers, -2, 0)
    span = np.diff(layout['bearing_x_mm'])[0]
    pivot = np.array(layout['shaft_yz_mm'])
    motor = np.array(layout['servo_yz_mm'])
    motor_z = layout['motor_mount_z_mm']
    mount = np.array([layout['motor_mount_y_mm'], np.mean(motor_z)])
    motor_tilt = np.arctan2(motor_low[..., 0]-motor_high[..., 0], motor_z[1]-motor_z[0])
    c, s = np.cos(motor_tilt), np.sin(motor_tilt)
    y, z = motor-mount
    moved_motor = mount+(motor_low+motor_high)/2+np.stack((c*y-s*z, s*y+c*z), axis=-1)
    _, drive, _ = layout['crank_x_mm']
    drive_side = (drive-layout['bearing_x_mm'][0])/span
    drive_pivot = pivot+left+drive_side*(right-left)
    phase = radians(layout['phase_deg']+angle)
    horn_phase = phase+motor_tilt
    r = layout['radius_mm']
    horn_pin = moved_motor+r*np.stack((np.cos(horn_phase), np.sin(horn_phase)), axis=-1)
    shaft_phase = link_angle(drive_pivot, horn_pin, r, np.linalg.norm(motor-pivot), phase)
    r = layout['lid_radius_mm']
    shaft_arm = r*np.stack((np.cos(shaft_phase), np.sin(shaft_phase)), axis=-1)
    lid_phases, link_pins = [], []
    for lid_x in layout['crank_x_mm'][::2]:
        at = (lid_x-layout['bearing_x_mm'][0])/span
        pin = pivot+left+at*(right-left)+shaft_arm
        lid_phase = link_angle(lid, pin, r, np.linalg.norm(lid-pivot), phase)
        lid_phases.append(lid_phase)
        lid_pin = lid+r*np.stack((np.cos(lid_phase), np.sin(lid_phase)), axis=-1)
        link_pins.append(np.stack((lid_pin, pin), axis=-2))
    return (angle+np.degrees(shaft_phase-phase),
            angle+np.degrees(np.stack(lid_phases, axis=-1)-phase),
            np.stack(link_pins, axis=-3))


def elastic_lid_angles(layout, angle, end, torque, centers, include_link_pins=False):
    shaft_angle, lid_angles, link_pins = elastic_linkage(layout, np.array([-39., 119.]), angle, centers)
    left, right = centers[:2]
    span = np.diff(layout['bearing_x_mm'])[0]
    result = {'command_deg': angle, 'torque_Nm': torque, 'resisting_crank_x_mm': end,
              'lid_deg': lid_angles.tolist(), 'shaft_deg': float(shaft_angle),
              'bearing_center_slope_deg': degrees(atan2(np.linalg.norm(right-left), span))}
    if include_link_pins:
        result['link_pins_yz_mm'] = link_pins.tolist()
    return result


def measure(directory, layout, size_mm, torques=(.04,.12), modulus=1000., stress=False,
            replay_torque=None, *, link_load_cases=(), link_angles=(), rail_states=False):
    """Return rail results and link replay rows, or the mixed-load rail states for offset replay."""
    mesh=mesh_step(directory/'blink_rail.step',size_mm)
    boundary=mesh.boundary_facets()
    vertices=mesh.p[:,mesh.facets[:,boundary]]
    x,y,z=vertices.mean(axis=1)

    def on(axis,position):
        return np.all(abs(vertices[axis]-position)<1e-4,axis=0)

    fastening=np.logical_or.reduce([np.hypot(x-a,z-b)<3.35 for a,b in layout['mount_xz_mm']])
    fixed=boundary[on(1,23.) & fastening]
    shaft_y,shaft_z=layout['shaft_yz_mm']
    ring=np.hypot(vertices[1]-shaft_y,vertices[2]-shaft_z)
    bore=np.all(abs(ring-5.12)<.015,axis=0)
    patches=[boundary[bore & (abs(x-a)<2.01)] for a in layout['bearing_x_mm']]
    pads=layout.get('motor_mount_z_mm',(183.,189.))
    mount_y=layout.get('motor_mount_y_mm',0.)
    patches.extend(boundary[on(0,-1.8) & (np.hypot(y-mount_y,z-a)<2.9)] for a in pads)
    if len(fixed)<6 or any(len(p)<6 for p in patches):
        raise RuntimeError('Unresolved blink rail screw or bearing patch')

    element=ElementVector(ElementTetP1())
    basis=Basis(mesh,element)
    lame, shear = lame_parameters(modulus,.37)
    stiffness=asm(linear_elasticity(lame,shear),basis)
    reduced,_,free=condense(stiffness,D=basis.get_dofs(facets=fixed).all())
    solve=splu(reduced.tocsc()).solve
    nodes=[np.unique(mesh.facets[:,p]) for p in patches]
    indices=np.array(basis.split_indices())
    responses=[]
    for patch in patches:
        for direction in ((0.,1.,0.),(0.,0.,1.)):
            unit=np.zeros(basis.N)
            unit[free]=solve(traction(mesh,element,patch,direction)[free])
            responses.append(unit)
    responses=np.array(responses)
    maximum = np.zeros(len(nodes))
    stresses = np.zeros(5)
    differential = 0.
    deflected = []

    def unit_loads(end, angle):
        input_force, _, left, right = -linkage_forces(layout, 1., angle, end)
        phase = radians(angle+layout['phase_deg'])
        crank = layout['radius_mm']*np.array([cos(phase), sin(phase)])
        y, z = np.array(layout['servo_yz_mm'])+crank-[mount_y, np.mean(pads)]
        couple = (y*input_force[1]-z*input_force[0])/(pads[1]-pads[0])
        offset = np.array([couple, 0.])
        return np.r_[left, right, input_force/2+offset, input_force/2-offset]

    ends = layout['crank_x_mm'][::2]
    for end, angle in product(ends, range(0, 91, 5)):
        field = unit_loads(end, angle) @ responses
        displacement = field[indices]
        maximum = np.maximum(maximum, [np.linalg.norm(displacement[:, n], axis=0).max() for n in nodes])
        centers = [displacement[:, n].mean(axis=1) for n in nodes[:2]]
        differential = max(differential, np.linalg.norm(centers[1]-centers[0]))
        if replay_torque is not None:
            centers_yz = np.asarray([displacement[1:, n].mean(axis=1) for n in nodes])
            for torque in (-replay_torque, replay_torque):
                deflected.append(elastic_lid_angles(layout, angle, end, torque, torque*centers_yz))
        if stress:
            stresses = np.maximum(stresses, stress_bounds(basis, field, lame, shear))
    for angle in link_angles:
        left_load, right_load = (unit_loads(end, angle) for end in ends)
        for left_torque, right_torque in link_load_cases:
            loads = left_torque*left_load + right_torque*right_load
            displacement = (loads @ responses)[indices]
            centers_yz = np.asarray([displacement[1:, n].mean(axis=1) for n in nodes])
            if rail_states:
                # Patches are the left and right bearings, then the low and high motor pads.
                row = {'angle': float(angle), 'torques': [left_torque, right_torque],
                       'centers': centers_yz.tolist(), 'loads': loads.tolist()}
            else:
                row = elastic_lid_angles(layout, angle, None, left_torque+right_torque, centers_yz,
                                         include_link_pins=True)
                row['crank_torques_Nm'] = [left_torque, right_torque]
            deflected.append(row)
    rows = []
    for torque in torques:
        row = {'torque_Nm': torque, 'mesh_mm': size_mm,
               'left_bearing_mm': float(torque*maximum[0]),
               'right_bearing_mm': float(torque*maximum[1]),
               'motor_mount_mm': float(torque*maximum[2:].max()),
               'bearing_center_differential_mm': float(torque*differential)}
        if stress:
            labels = ('vm_p99_MPa', 'vm_max_MPa', 'layer_y_tension_max_MPa',
                      'layer_y_compression_max_MPa', 'layer_y_shear_max_MPa')
            row.update(zip(labels, map(float, torque*stresses), strict=True))
        rows.append(row)
    return rows, deflected


if __name__ == '__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('cad',type=Path)
    parser.add_argument('report',type=Path)
    parser.add_argument('--torques', type=float, nargs='+', default=(.04,.12))
    parser.add_argument('--modulus', type=float, default=1000.)
    parser.add_argument('--mesh-mm', type=float, nargs='+', default=(1.45, 1.10))
    parser.add_argument('--replay-torque', type=float)
    parser.add_argument('--stress', action='store_true')
    args=parser.parse_args()
    if not all(np.isfinite(x) and x>0 for x in (args.modulus,*args.torques,*args.mesh_mm)):
        parser.error('Torque, modulus and mesh size must be positive and finite')
    if args.replay_torque is not None and not (np.isfinite(args.replay_torque) and args.replay_torque > 0):
        parser.error('Replay torque must be positive and finite')
    cad=json.loads((args.cad/'cad_parts.json').read_text())
    results, replay = [], {}
    for h in args.mesh_mm:
        rows, deflected = measure(args.cad,cad['motion_geometry']['blink'],h,args.torques,
                                  args.modulus,args.stress,args.replay_torque)
        results.extend(rows)
        if deflected:
            replay[str(h)] = deflected
    report = {'cad_sha256': cad['source_sha256'], 'modulus_MPa': args.modulus,
              'print_layer_normal_cad': [0., 1., 0.], 'trials': results}
    if replay:
        report['deflected_lid_replay'] = replay
    args.report.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
