"""Linear elastic screen of the hatch-nut seats of the base cup (B25 and B26 compared).

Region from cut_b26_hatch_region.py, its cut faces fixed. Each of the two right-side hatch bolts
pulls its nut down onto the seat with F (default 600 N, about 0.35 N m on an M3 with K = 0.2);
in 'clamped' mode the hatch pushes back up with the same F on the base's down-facing seat faces
(z -78.66 and -76.66) within 8 mm of the bolt. PETG E = 1800 MPa, nu = 0.37.

    python mechanical/physics/check_b26_hatch_bar_fea.py b26.step -73.18 600 clamped
    python mechanical/physics/check_b26_hatch_bar_fea.py b25.step -74.78 600 clamped
"""
import sys, numpy as np, gmsh
from cable_fea import mesh_step
from skfem import Basis, ElementTetP1, ElementVector, asm, FacetBasis, LinearForm, condense, solve
from skfem.models.elasticity import lame_parameters, linear_elasticity
from skfem.helpers import dot
from pathlib import Path
E, NU, F = 1800., .37, float(sys.argv[3]) if len(sys.argv)>3 else 600.
name, seat = sys.argv[1], float(sys.argv[2])
MODE = sys.argv[4] if len(sys.argv)>4 else 'cantilever'
m = mesh_step(Path(name), .7)
name = Path(name).stem
e = ElementVector(ElementTetP1()); ib = Basis(m, e)
K = asm(linear_elasticity(*lame_parameters(E, NU)), ib)
bf = m.boundary_facets(); c = m.p[:, m.facets[:, bf]].mean(axis=1)
tol=1e-3
fixed_f = bf[(np.abs(c[0]-30)<tol)|(np.abs(c[0]-60)<tol)|(np.abs(c[1]-40)<tol)|(np.abs(c[1]-82)<tol)|(np.abs(c[2]+62)<tol)]
fdofs = ib.get_dofs(facets=fixed_f).all()
f = np.zeros(ib.N)
for y in (51., 71.):
    r = np.hypot(c[0]-41.2, c[1]-y)
    sel = bf[(np.abs(c[2]-seat)<.02)&(r>1.9)&(r<2.75)]
    fb = FacetBasis(m, e, facets=sel); area = fb.dx.sum()
    load = np.array([0,0,-F/area])
    @LinearForm
    def work(v,w): return dot(load[:,None,None]*np.ones_like(v), v) if False else v[2]*load[2]
    f += asm(work, fb)
    print(name,'nut at y',y,'contact area %.1f mm2'%area,'bearing %.1f MPa'%(F/area))
    if MODE == 'clamped':
        # The hatch, pulled up by the same bolt, bears on the base's down-facing seat faces
        # (z -78.66 and -76.66, 0.2-0.3 mm nominal gap) inside an 8 mm clamp radius.
        nz = m.facets  # placeholder
        seatsel = bf[((np.abs(c[2]+78.66)<.05)|(np.abs(c[2]+76.66)<.05))&(r<8.)&(r>1.9)]
        sb = FacetBasis(m, e, facets=seatsel); sa = sb.dx.sum()
        up = F/sa
        @LinearForm
        def react(v,w): return v[2]*up
        f += asm(react, sb)
        print(name,'  hatch seat area %.1f mm2, %.1f MPa'%(sa, up))
u = solve(*condense(K, f, D=fdofs))
# stress per element
from skfem import ElementTetP0
dg=Basis(m, ElementVector(ElementTetP0()))
lam,mu=lame_parameters(E,NU)
uu=ib.interpolate(u)
G=uu.grad  # (3,3,nelem,nqp)
eps=.5*(G+np.transpose(G,(1,0,2,3)))
tr=eps[0,0]+eps[1,1]+eps[2,2]
S=2*mu*eps; 
for i in range(3): S[i,i]+=lam*tr
vm=np.sqrt(.5*((S[0,0]-S[1,1])**2+(S[1,1]-S[2,2])**2+(S[2,2]-S[0,0])**2)+3*(S[0,1]**2+S[1,2]**2+S[2,0]**2)).mean(axis=1)
mid=m.p[:,m.t].mean(axis=1)
# ignore elements touching the loaded ring edges (contact singularity): report percentiles
print(name,'elements',m.t.shape[1],'vm max %.1f p99.9 %.1f p99 %.1f MPa'%(vm.max(),np.percentile(vm,99.9),np.percentile(vm,99)))
disp=u.reshape(-1,3) if False else u[ib.nodal_dofs].T
nod=m.p.T
for y in (51.,71.):
    k=np.argmin(np.hypot(nod[:,0]-41.2-2.3,nod[:,1]-y)+np.abs(nod[:,2]-seat)*3)
    print(name,'deflection under nut y=%g: %.3f mm'%(y,disp[k,2]))
top=np.argsort(vm)[-8:]
for i in top[::-1]: print('  hot', np.round(mid[:,i],1), round(vm[i],1))
