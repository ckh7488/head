"""Elastic displacement of the captured cable parts and rear ballast tray."""

from argparse import ArgumentParser
from pathlib import Path
import json

import gmsh
import numpy as np
from scipy.sparse.linalg import splu
from skfem import Basis, ElementTetP1, ElementVector, FacetBasis, LinearForm, MeshTet, asm, condense
from skfem.helpers import dot
from skfem.models.elasticity import lame_parameters, linear_elasticity

ELASTIC_MODULUS = 1450.
POISSON = .37


def mesh_step(path, edge_size, *, volume_algorithm=1, minimum_edge_ratio=.53):
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal',0)
        gmsh.option.setNumber('General.NumThreads',4)
        gmsh.option.setNumber('Mesh.Algorithm3D', volume_algorithm)
        gmsh.model.add(path.stem)
        gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        assert len(gmsh.model.getEntities(3))==1
        gmsh.option.setNumber('Mesh.MeshSizeMin',edge_size*minimum_edge_ratio)
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


def traction(mesh, element, faces, load):
    surface=FacetBasis(mesh,element,facets=faces)
    density=np.array(load)[:,None,None]/surface.dx.sum()

    @LinearForm
    def work(v,w):
        return dot(density,v)

    return asm(work,surface)


def patches(mesh, name, specs):
    boundary = mesh.boundary_facets()
    vertices = mesh.p[:, mesh.facets[:, boundary]]
    x, y, z = vertices.mean(axis=1)

    def plane(axis, value):
        return np.all(abs(vertices[axis]-value) < 1e-4, axis=0)

    if name == 'ballast_tray':
        mount = np.logical_or.reduce([np.hypot(x-a, z-b)<3.6 for a, b in specs['mount_xz_mm']])
        fixed = boundary[plane(1, 31.) & mount]
        loaded = boundary[plane(2, specs['floor_z_mm']) & (abs(x)<19.8) & (y>40.) & (y<65.)]
        return fixed, {'stack': loaded}

    centers = specs['cap_bolts_x_mm']
    if name == 'cable_saddle':
        mount = np.logical_or.reduce([np.hypot(x-a, z+71.)<4.2 for a in (-28.5,28.5)])
        fixed = boundary[plane(1, 93.6) & mount]
    else:
        screw = np.logical_or.reduce([np.hypot(x-a, y-specs['cap_bolt_y_mm'])<3.05 for a in centers])
        keys = np.logical_or.reduce([abs(x-a)<specs['cap_key_cut_half_width_mm']+.025
                                     for a in specs['cap_keys_x_mm']])
        fixed = boundary[(plane(2, -49.1) & screw) | (plane(1, 106.37) & keys & (z<-54.85))]
    shoulders = {}
    for lane in specs['lanes']:
        width, height = lane['minimum_shoulder_mm']
        zone = (abs(x-lane['x_mm'])<width/2) & (abs(z-specs['center_z_mm'])<height/2)
        shoulders[lane['name']] = boundary[plane(1, specs['stop_y_mm']) & zone]
    return fixed, shoulders


def solve_cases(mesh, name, specs, h):
    supports, patches_by_load = patches(mesh, name, specs)
    if len(supports)<6 or any(len(patch)<3 for patch in patches_by_load.values()):
        raise RuntimeError(f'{name} has an unresolved bolt or load region at h={h}')
    element = ElementVector(ElementTetP1())
    basis = Basis(mesh, element)
    lam, shear = lame_parameters(ELASTIC_MODULUS, POISSON)
    stiffness = asm(linear_elasticity(lam, shear), basis)
    constrained = basis.get_dofs(facets=supports).all()
    reduced, _, free = condense(stiffness, D=constrained)
    solve_free = splu(reduced.tocsc()).solve
    indices = basis.split_indices()
    if name == 'ballast_tray':
        directions = ((0., 0., -12.), (0., 8.49, -8.49))
    else:
        directions = ((0., 10., 0.), (7.071, 7.071, 0.), (0., 14.14, 14.14))
    rows = []
    for target, patch in patches_by_load.items():
        nodes = np.unique(mesh.facets[:, patch])
        for vector in directions:
            rhs = traction(mesh, element, patch, vector)
            disp = np.zeros_like(rhs)
            disp[free] = solve_free(rhs[free])
            react = stiffness@disp-rhs
            error = max(abs(react[i].sum()+rhs[i].sum()) for i in indices)
            if error > 1e-4:
                raise RuntimeError(f'{name} failed reaction equilibrium')
            response = np.array([disp[i] for i in indices])
            deflection = float(np.linalg.norm(response[:, nodes], axis=0).max())
            gradient = basis.interpolate(disp).grad
            strain = .5*(gradient+np.swapaxes(gradient, 0, 1))
            sigma = 2*shear*strain+lam*np.eye(3)[:,:,None,None]*np.einsum('iijk->jk', strain)
            deviator = sigma-np.eye(3)[:,:,None,None]*np.einsum('iijk->jk', sigma)/3
            von = np.sqrt(1.5*(deviator**2).sum(axis=(0,1))).mean(axis=1)
            rows.append({'part': name, 'mesh_mm': h, 'elements': int(mesh.nelements),
                         'load_at': target, 'force_xyz_N': list(vector), 'elastic_mm': deflection,
                         'at_1_GPa_mm': deflection*ELASTIC_MODULUS/1000,
                         'stress_p99_MPa': float(np.percentile(von,99))})
    print(name, h, len(rows), 'maximum deflection at 1 GPa',
          round(max(row['at_1_GPa_mm'] for row in rows),4), flush=True)
    return rows


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    source = json.loads((args.cad/'cad_parts.json').read_text())
    rig = source['motion_geometry']
    rows = []
    for part, key in [('cable_saddle', 'cables'), ('cable_gate', 'cables'), ('ballast_tray', 'ballast')]:
        for h in (1.95, 1.45):
            mesh = mesh_step(args.cad/f'{part}.step', h)
            rows.extend(solve_cases(mesh, part, rig[key], h))
    args.output.mkdir(parents=True, exist_ok=True)
    data = {'cad_sha256': source['source_sha256'], 'modulus_MPa': ELASTIC_MODULUS,
            'poisson_ratio': POISSON, 'trials': rows}
    (args.output/'fea_results.json').write_text(json.dumps(data, indent=2))
