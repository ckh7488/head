"""Elastic screen of the eye cradle with the eye-yaw drivetrain loaded."""

from argparse import ArgumentParser
from hashlib import sha256
from itertools import product
import json
from math import cos, radians, sin
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import splu
from skfem import Basis, ElementTetP1, ElementVector, asm
from skfem.models.elasticity import lame_parameters, linear_elasticity

from cable_fea import mesh_step, traction


EYE_RADIUS_MM = 13.5
STALL_NM = .215  # XL330-M077 at 5 V (ROBOTIS e-Manual).
EYE_X = (-34., 34.)
EYE_Y = -39.
PIVOT_Z = 119.
POISSON = .37
SUPPORT_CASES = {'compliant': (700., 100., False), 'stiff': (1800., 2000., False),
                 'stiff_bridges': (1800., 2000., True)}
TORQUES_NM = (.04, .08, STALL_NM)


def regions(mesh, lug_yz):
    faces = mesh.boundary_facets()
    vertices = mesh.p[:, mesh.facets[:, faces]]
    x, y, z = vertices.mean(axis=1)

    def bore(radius, axis, first, second):
        a, b = [i for i in range(3) if i != axis]
        radial = np.hypot(vertices[a]-first, vertices[b]-second)
        return np.all(np.abs(radial-radius)<.002, axis=0)

    outer = bore(1.62, 0, EYE_Y, PIVOT_Z)
    left, right = faces[outer & (x<-57.)], faces[outer & (x>57.)]
    lug = faces[bore(1.18, 0, *lug_yz) & (x>57.)]
    yaw = {}
    for side, px in zip(('left', 'right'), EYE_X):
        wall = bore(1.13, 2, px, EYE_Y)
        yaw[side] = [faces[wall & (z<111.)], faces[wall & (z>126.)]]
    feet = faces[np.all(np.abs(vertices[2]-111.55)<.002, axis=0) &
                 (np.abs(np.abs(x)-8.)<2.81) & (y<-44.7) & (y>-50.3)]
    if any(len(patch)<6 for patch in [left, right, lug, feet, *yaw['left'], *yaw['right']]):
        raise ValueError('The CAD mesh does not resolve a bearing or motor-foot surface')
    return left, right, lug, yaw, feet


def rigid_patch(mesh, weights, centre):
    nodes = np.flatnonzero(weights)
    offsets = mesh.p[:, nodes].T - centre
    impulse = np.broadcast_to(np.eye(3), (len(nodes), 3, 3))
    moments = np.cross(offsets[:, None, :], impulse)
    balance = np.vstack((impulse.reshape(-1, 3).T, moments.reshape(-1, 3).T))
    weights = np.repeat(weights[nodes], 3)
    weighted = balance * weights
    fit = np.linalg.solve(balance @ weighted.T, weighted)
    return nodes, weights, weighted, fit


def load_cases(mesh, basis, yaw, feet, indices):
    element = basis.elem
    node_indices = indices[0]
    weights = {side: [traction(mesh, element, patch, (1., 0., 0.))[node_indices]
                      for patch in regions] for side, regions in yaw.items()}
    foot_weights = traction(mesh, element, feet, (1., 0., 0.))[node_indices]
    motor_nodes, _, _, fit = rigid_patch(mesh, foot_weights, [0., -47.6, 111.55])
    for angle, sign, jam, eccentric in product((-20., 0., 20.), (-1., 1.),
                                                ('left', 'right', 'balanced'), (False, True)):
        if eccentric and jam=='balanced':
            continue
        theta = radians(angle)
        force = sign*np.array([cos(theta), sin(theta), .20 if eccentric else 0.])
        contact = np.array([-5.8-EYE_RADIUS_MM*sin(theta), -35.5+EYE_RADIUS_MM*cos(theta), 116.])
        motor_force = -force
        motor_moment = np.cross(contact-[0., -47.6, 111.55], motor_force)
        applied = np.zeros((3, mesh.nvertices))
        applied[:, motor_nodes] = (fit.T @ np.r_[motor_force, motor_moment]).reshape(-1, 3).T
        shares = {'left': 1. if jam=='left' else .5 if jam=='balanced' else 0.,
                  'right': 1. if jam=='right' else .5 if jam=='balanced' else 0.}
        for side, share in shares.items():
            upper_share = (113.-109.35)/(127.875-109.35)
            if eccentric:
                upper_share = (111.-109.35)/(127.875-109.35)
            lower, upper = weights[side]
            applied += share*force[:, None]*((1-upper_share)*lower+upper_share*upper)
        rhs = np.zeros(basis.N)
        rhs[indices] = applied
        yield {'horn_deg': angle, 'direction': int(sign), 'load_split': jam,
               'eccentric': eccentric}, rhs


def spring_matrix(mesh, element, supports, stiffness):
    left, right, lug = supports
    link = np.array([0., 49., 32.])
    link /= np.linalg.norm(link)
    directions = [(left, vector) for vector in np.eye(3)]
    directions += [(right, vector) for vector in np.eye(3)[1:]]
    directions += [(lug, link)]
    lifts = [csc_matrix(traction(mesh, element, faces, direction)[:, None])
             for faces, direction in directions]
    return sum(stiffness*(weight @ weight.T) for weight in lifts)


def seated_bridge(mesh, weights, centre, indices, stiffness):
    nodes, area, weighted, fit = rigid_patch(mesh, weights, centre)
    # Suppress only the deformation left after fitting a free rigid body to the mount.
    dofs = indices[:, nodes].T.ravel()
    matrix = stiffness*(np.diag(area)-weighted.T@fit)
    return csc_matrix((matrix.ravel(), (np.repeat(dofs, len(dofs)), np.tile(dofs, len(dofs)))),
                      shape=(mesh.nvertices*3,)*2)


def measurements(mesh, basis, displacement, indices, yaw, weight, feet, lam, shear):
    field = displacement[indices]
    motor = field @ weight(feet)
    deflection = tilt = ovalization = 0.
    for side, bore_x in zip(('left', 'right'), EYE_X):
        lower, upper = yaw[side]
        lower_mean, upper_mean = field @ weight(lower), field @ weight(upper)
        deflection = max(deflection, np.linalg.norm((lower_mean-motor)[:2]))
        tilt = max(tilt, np.linalg.norm((upper_mean-lower_mean)[:2]))
        for patch, mean in ((lower, lower_mean), (upper, upper_mean)):
            nodes = np.unique(mesh.facets[:, patch])
            radial = (mesh.p[:2, nodes]-[[bore_x], [EYE_Y]])/1.13
            local = ((field[:2, nodes]-mean[:2, None])*radial).sum(axis=0)
            ovalization = max(ovalization, np.abs(local).max())

    gradient = basis.interpolate(displacement).grad
    strain = .5*(gradient+gradient.swapaxes(0, 1))
    eye = np.eye(3)[:, :, None, None]
    trace = np.einsum('iijk->jk', strain)
    deviator = 2*shear*(strain-eye*trace/3)
    stress = 2*shear*strain+lam*eye*trace
    von = np.sqrt(1.5*(deviator**2).sum(axis=(0, 1))).mean(axis=1)
    centers = mesh.p[:, mesh.t].mean(axis=1)
    rib = (np.abs(centers[0]+34.)<5.21) & (centers[1]>-22.3) & (centers[2]>110.6) & (centers[2]<121.2)
    principal = np.linalg.eigvalsh(stress.mean(axis=-1).transpose(2, 0, 1))[:, -1]
    return np.array([np.linalg.norm(field, axis=0).max(), deflection, tilt, ovalization,
                     np.percentile(von, 99), np.percentile(principal[rib], 95),
                     np.percentile(principal[rib], 99)])


def first_contacts(mesh, fields, cases, pin_weights, directory):
    import fcl
    import trimesh
    from trimesh.collision import mesh_to_BVH
    from check_head import rotation

    faces = mesh.facets[:, mesh.boundary_facets()].T
    names = ('Part029', 'Part033', 'Part057', 'Part060')
    fixed = {name: fcl.CollisionObject(mesh_to_BVH(trimesh.load_mesh(directory/'world'/f'{name}.stl')))
             for name in names}
    request = fcl.CollisionRequest()
    for (case, _), field in zip(cases, fields):
        if not ((case['load_split']=='balanced' and case['horn_deg']==0.) or
                (case['load_split']=='left' and case['eccentric'] and case['horn_deg']==-20.) or
                (case['load_split']=='right' and case['eccentric'] and case['horn_deg']==0.)):
            continue

        def hits(torque):
            shift = field*(torque*1000/EYE_RADIUS_MM)
            for side, x, name in zip(('left', 'right'), EYE_X, names):
                lower, upper = pin_weights[side]@shift.T
                base = np.array([x, EYE_Y, 109.35])
                axis = upper-lower+[0, 0, 127.875-109.35]
                tip = trimesh.geometry.align_vectors([0, 0, 1], axis/np.linalg.norm(axis))
                tip[:3, 3] = base+lower-tip[:3, :3]@base
                pose = tip@rotation(case['horn_deg'], (0, 0, 1), (x, EYE_Y, PIVOT_Z))
                fixed[name].setTransform(fcl.Transform(pose[:3, :3].copy(), pose[:3, 3].copy()))
            moved = trimesh.Trimesh(vertices=mesh.p.T+shift.T, faces=faces, process=False)
            cradle = fcl.CollisionObject(mesh_to_BVH(moved))
            return [name for name, obj in fixed.items()
                    if fcl.collide(cradle, obj, request, fcl.CollisionResult())]

        if hits(0.):
            raise ValueError('The CAD mesh starts in contact in the load check')
        low, intersection = 0., None
        for high in (.001, .002, .004, .008, .016, .032, .048, .08):
            if not hits(high):
                low = high
                continue
            for _ in range(8):
                mid = (low+high)/2
                if hits(mid):
                    high = mid
                else:
                    low = mid
            intersection = {'torque_range_Nm': [low, high], 'parts': hits(high)}
            break
        yield {**case, 'first_detected_contact': intersection, 'upper_trial_Nm': .08}


METRICS = ('absolute_displacement_mm', 'lower_bearing_to_motor_xy_mm', 'eye_pin_end_shift_xy_mm',
           'bearing_wall_radial_change_mm', 'von_mises_p99_MPa', 'left_rib_tension_p95_MPa',
           'left_rib_tension_p99_MPa')


def solve_mesh(mesh, size, fixtures, directory, lug_yz):
    left, right, lug, yaw, feet = regions(mesh, lug_yz)
    element = ElementVector(ElementTetP1())
    basis = Basis(mesh, element)
    indices = np.asarray(basis.split_indices())
    cases = list(load_cases(mesh, basis, yaw, feet, indices))
    rhs = np.column_stack([row[1] for row in cases])
    pads = {id(patch): traction(mesh, element, patch, (1., 0., 0.))[indices[0]]
            for patch in (feet, *yaw['left'], *yaw['right'])}

    def weights(faces):
        return pads[id(faces)]

    for model in fixtures:
        modulus, support, bridges = SUPPORT_CASES[model]
        lam, shear = lame_parameters(modulus, POISSON)
        elasticity = asm(linear_elasticity(lam, shear), basis)
        springs = spring_matrix(mesh, element, (left, right, lug), support)
        if bridges:
            elasticity += seated_bridge(mesh, weights(feet), [0., -47.6, 111.55], indices, 5000.)
            for side, x in zip(('left', 'right'), EYE_X):
                bearing_weights = (weights(yaw[side][0])+weights(yaw[side][1]))/2
                elasticity += seated_bridge(mesh, bearing_weights, [x, EYE_Y, PIVOT_Z], indices, 5000.)
        displacement = splu((elasticity+springs).tocsc()).solve(rhs)
        residual = elasticity@displacement + springs@displacement - rhs
        if np.max(np.abs(residual))>1e-6:
            raise RuntimeError('Eye cradle FEM did not reach force equilibrium')
        values = np.array([measurements(mesh, basis, column, indices, yaw, weights, feet, lam, shear)
                           for column in displacement.T])
        subsets = {'both_eyes': [i for i, (row, _) in enumerate(cases) if row['load_split']=='balanced'],
                   'single_eye': [i for i, (row, _) in enumerate(cases) if row['load_split']!='balanced' and not row['eccentric']],
                   'all': list(range(len(cases)))}
        peaks = {name: values[selected].max(axis=0) for name, selected in subsets.items()}
        worst = {name: cases[i][0] for name, i in zip(METRICS, values.argmax(axis=0))}
        result = [{'torque_Nm': torque, 'tangential_force_N': torque*1000/EYE_RADIUS_MM,
                   **dict(zip(METRICS, torque*1000/EYE_RADIUS_MM*peaks['all']))}
                  for torque in TORQUES_NM]
        record = {'mesh_mm': size, 'elements': mesh.nelements, 'fixture': model, 'modulus_MPa': modulus,
                  'bearing_and_link_spring_N_per_mm': support, 'cases': len(cases), 'worst_case': worst,
                  'case_groups_at_0p04_Nm': {label: dict(zip(METRICS, .04*1000/EYE_RADIUS_MM*value))
                                            for label, value in peaks.items()},
                  'results': result}
        if directory is not None:
            pin_weights = {side: np.stack([weights(patch) for patch in pair]) for side, pair in yaw.items()}
            record['first_contact_trials'] = list(first_contacts(mesh, (u[indices] for u in displacement.T),
                                                                 cases, pin_weights, directory))
        yield record


def run(cad, sizes, fixtures, directory):
    from export_cad import App, world_shape

    with TemporaryDirectory() as path:
        step = Path(path)/'eye_cradle.step'
        doc = App.openDocument(str(cad.resolve()))
        try:
            world_shape(doc.Part024).exportStep(str(step))
            pin = doc.getObject('EyePitchLinkCradlePin')
            center = world_shape(pin).CenterOfMass if pin else None
            lug_yz = (center.y, center.z) if center else (-29., PIVOT_Z)
        finally:
            App.closeDocument(doc.Name)
        for size in sizes:
            mesh = mesh_step(step, size)
            for row in solve_mesh(mesh, size, fixtures, directory, lug_yz):
                print(f"Eye cradle h={size:g} mm, {mesh.nelements} tets, {row['fixture']}: "
                      f"stall relative bearing travel {row['results'][-1]['lower_bearing_to_motor_xy_mm']:.3f} mm", flush=True)
                yield row


if __name__=='__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--mesh-mm', type=float, nargs='+', default=[1.1, .8])
    parser.add_argument('--fixtures', choices=tuple(SUPPORT_CASES), nargs='+', default=list(SUPPORT_CASES))
    parser.add_argument('--world-cad', type=Path, help='Matching export_cad.py --world directory for loaded contact checks')
    args = parser.parse_args()
    if any(not np.isfinite(size) or size<=0 for size in args.mesh_mm):
        parser.error('Mesh sizes must be positive and finite')
    digest = sha256(args.cad.read_bytes()).hexdigest()
    if args.world_cad and json.loads((args.world_cad/'cad_parts.json').read_text())['source_sha256']!=digest:
        parser.error('World export belongs to a different CAD revision')
    report = {'cad_sha256': digest, 'horn_radius_mm': EYE_RADIUS_MM,
              'poisson_ratio': POISSON, 'nominal_yaw_bore_radial_clearance_mm': .13,
              'material_and_support_are_sensitivity_cases': True,
              'rigid_bridge_spring_N_per_mm': 5000.,
              'trials': list(run(args.cad, args.mesh_mm, args.fixtures, args.world_cad))}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
