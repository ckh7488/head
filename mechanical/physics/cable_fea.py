"""Linear-elastic screening of the exact B2 cable saddle STEP.

Coordinates in mm, forces in N, elastic modulus and stress in MPa. The fixture
and the washers are held rigid. Jacket slip is treated in grip.py.
"""
from argparse import ArgumentParser
from math import cos, radians, sin
from pathlib import Path
import json

import gmsh
import numpy as np
from skfem import Basis, ElementTetP1, ElementVector, FacetBasis, LinearForm, MeshTet, asm, condense, solve
from skfem.helpers import dot
from skfem.models.elasticity import lame_parameters, linear_elasticity

ELASTIC_MODULUS = 1450.
POISSON = .37
BAND_CENTERS = (99.4,111.7)
RIGHT_LANE = 15.75


def mesh_step(path, edge_size):
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal',0)
        gmsh.option.setNumber('General.NumThreads',4)
        gmsh.model.add('R5 B2 saddle')
        gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        assert len(gmsh.model.getEntities(3))==1
        gmsh.option.setNumber('Mesh.MeshSizeMin',edge_size*.53)
        gmsh.option.setNumber('Mesh.MeshSizeMax',edge_size)
        gmsh.option.setNumber('Mesh.MinimumCirclePoints',16)
        gmsh.model.mesh.generate(3)
        tags,xyz,_=gmsh.model.mesh.getNodes()
        kinds,_,data=gmsh.model.mesh.getElements(3)
        assert list(kinds)==[4]
        order=np.argsort(tags)
        elements=np.searchsorted(tags[order],data[0].reshape(-1,4))
        return MeshTet(xyz.reshape(-1,3)[order].T,elements.T)
    finally:
        gmsh.finalize()


def surface_patches(mesh):
    boundary=mesh.boundary_facets()
    points=mesh.p[:,mesh.facets[:,boundary]]
    x,y,z=points.mean(axis=1)
    washes=[]
    for xc in (-28.5,28.5):
        on_seat=np.all(abs(points[1]-93.6)<1e-4,axis=0)
        washes.append(boundary[on_seat & (np.hypot(x-xc,z+71)<3.75)])
    grooves=[]
    returns=[]
    for band in BAND_CENTERS:
        strip=abs(y-band)<2.7
        radial=np.hypot(x-RIGHT_LANE,z+67)
        grooves.append(boundary[strip & (abs(radial-4.18)<.22) & (z<-67.3)])
        returns.append(boundary[strip & (abs(x-RIGHT_LANE)<5.5) & np.all(abs(points[2]+77.7)<1e-4,axis=0)])
    if any(len(facets)<6 for facets in washes+grooves+returns):
        raise RuntimeError(f'Missing load or washer mesh patches: {[len(f) for f in washes+grooves+returns]}')
    return washes,grooves,returns


def traction(mesh, element, faces, load):
    surface=FacetBasis(mesh,element,facets=faces)
    density=np.array(load)[:,None,None]/surface.dx.sum()

    @LinearForm
    def work(v,w):
        return dot(density,v)

    return asm(work,surface)


def norm(v):
    return np.linalg.norm(v,axis=0)


def simulation(mesh, label):
    washes,grooves,returns=surface_patches(mesh)
    element=ElementVector(ElementTetP1())
    basis=Basis(mesh,element)
    lam,shear=lame_parameters(ELASTIC_MODULUS,POISSON)
    stiff=asm(linear_elasticity(lam,shear),basis)
    cases=[
        ('10N_straight',10.,0.,[.5,.5],[12,12],(0,1)),
        ('10N_45deg',10.,45.,[.5,.5],[12,12],(0,1)),
        ('10N_one_strap',10.,45.,[0,1],[0,24],(0,1)),
        ('20N_overload',20.,45.,[0,1],[0,24],(0,1)),
        ('10N_one_mount',10.,45.,[.5,.5],[12,12],(0,)),
    ]
    data={}
    for name,force,angle,fractions,preload,support_id in cases:
        direction=np.array([sin(radians(angle)),cos(radians(angle)),0.])
        rhs=np.zeros(basis.N)
        for i in range(2):
            rhs+=traction(mesh,element,grooves[i],force*fractions[i]*direction+[0,0,-preload[i]])
            rhs+=traction(mesh,element,returns[i],[0,0,preload[i]])
        pads=[basis.get_dofs(facets=washes[i]).all() for i in support_id]
        held=np.unique(np.concatenate(pads))
        disp=solve(*condense(stiff,rhs,D=held))
        nodal=basis.split_indices()
        vectors=np.array([disp[ids] for ids in nodal])
        reaction=stiff@disp-rhs
        equilibrium=np.array([reaction[ids].sum()+rhs[ids].sum() for ids in nodal])
        assert max(abs(equilibrium))<1e-4,(label,name,equilibrium)

        gradient=basis.interpolate(disp).grad
        strain=.5*(gradient+np.swapaxes(gradient,0,1))
        sigma=2*shear*strain+lam*np.eye(3)[:,:,None,None]*np.einsum('iijk->jk',strain)
        deviator=sigma-np.eye(3)[:,:,None,None]*np.einsum('iijk->jk',sigma)/3
        von=np.sqrt(1.5*(deviator**2).sum(axis=(0,1))).mean(axis=1)
        volume=basis.dx.sum(axis=1)
        order=np.argsort(von)
        cdf=np.cumsum(volume[order])/volume.sum()
        gnodes=np.unique(mesh.facets[:,np.concatenate(grooves)])
        largest=float(norm(vectors[:,gnodes]).max())
        row={'force_N':force,'pull_deg':angle,'band_preload_N':preload,'washer_count':len(pads),
             'max_groove_displacement_mm':largest,'displacement_range_mm_for_1_to_2p2_GPa':
             [largest*ELASTIC_MODULUS/2200,largest*ELASTIC_MODULUS/1000],
             'von_mises_p99_MPa':float(np.interp(.99,cdf,von[order])),
             'peak_local_MPa_mesh_sensitive':float(von.max()),
             'reaction_each_washer_N':[[float(reaction[np.intersect1d(pad,ids)].sum()) for ids in nodal] for pad in pads]}
        data[name]=row
        print(label,name,round(largest,5),round(row['von_mises_p99_MPa'],3),flush=True)
    return {'tetrahedra':int(mesh.nelements),'mesh_nodes':int(mesh.nvertices),
            'surface_facets':{'washer':[len(p) for p in washes],'groove':[len(p) for p in grooves]},'cases':data}


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('cad',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    data={'cad_sha256':json.loads((args.cad/'cad_parts.json').read_text())['source_sha256'],
          'modulus_MPa':ELASTIC_MODULUS,'poisson_ratio':POISSON,'gmsh':gmsh.__version__,'trials':{}}
    for h in (1.55,1.08):
        data['trials'][str(h)]=simulation(mesh_step(args.cad/'cable_saddle.step',h),h)
    (args.output/'fea_results.json').write_text(json.dumps(data,indent=2))
