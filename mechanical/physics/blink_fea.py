"""Estimate PETG rail deflection with the head-frame screws clamped."""

from argparse import ArgumentParser
from itertools import product
import json
from math import cos, radians, sin
from pathlib import Path

import numpy as np
from scipy.sparse.linalg import splu
from skfem import Basis, ElementTetP1, ElementVector, asm, condense
from skfem.models.elasticity import lame_parameters, linear_elasticity

from blink import linkage_forces
from cable_fea import mesh_step, traction


def measure(directory, layout, size_mm):
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
    stiffness=asm(linear_elasticity(*lame_parameters(1000.,.37)),basis)
    reduced,_,free=condense(stiffness,D=basis.get_dofs(facets=fixed).all())
    solve=splu(reduced.tocsc()).solve
    nodes=[np.unique(mesh.facets[:,p]) for p in patches]
    indices=np.array(basis.split_indices())
    responses=[]
    for patch in patches:
        for direction in ((0.,1.,0.),(0.,0.,1.)):
            unit=np.zeros(basis.N)
            unit[free]=solve(traction(mesh,element,patch,direction)[free])
            responses.append(unit[indices])
    responses=np.array(responses)
    rows=[]
    for torque in (.04,.12):
        maximum=np.zeros(len(nodes))
        for end,angle in product(layout['crank_x_mm'][::2],range(0,91,5)):
            input_force,_,left,right=-linkage_forces(layout,torque,angle,end)
            phase=radians(angle+layout['phase_deg'])
            crank=layout['radius_mm']*np.array([cos(phase),sin(phase)])
            y,z=np.array(layout['servo_yz_mm'])+crank-[mount_y,np.mean(pads)]
            couple=(y*input_force[1]-z*input_force[0])/(pads[1]-pads[0])
            offset=np.array([couple,0.])
            loads=np.r_[left,right,input_force/2+offset,input_force/2-offset]
            displacement=np.einsum('i,ijk->jk',loads,responses)
            maximum=np.maximum(maximum,[np.linalg.norm(displacement[:,n],axis=0).max() for n in nodes])
        rows.append({'torque_Nm':torque,'mesh_mm':size_mm,'left_bearing_mm':float(maximum[0]),
                     'right_bearing_mm':float(maximum[1]),'motor_mount_mm':float(maximum[2:].max())})
    return rows


if __name__ == '__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('cad',type=Path)
    parser.add_argument('report',type=Path)
    args=parser.parse_args()
    cad=json.loads((args.cad/'cad_parts.json').read_text())
    results=[row for h in (1.45,1.10) for row in measure(args.cad,cad['motion_geometry']['blink'],h)]
    report={'cad_sha256':cad['source_sha256'],'modulus_MPa':1000,'trials':results}
    args.report.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
