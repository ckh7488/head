"""Fit a straight Ø2 yaw pin through both loaded bore surfaces of the B23 cradle."""

from argparse import ArgumentParser
from hashlib import file_digest
from itertools import product
import json
from math import cos, radians, sin
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from scipy.optimize import linprog
from scipy.sparse.linalg import splu
from skfem import Basis, ElementTetP1, ElementVector, asm
from skfem.models.elasticity import lame_parameters, linear_elasticity

from b20_eye_cradle_fea import (
    EYE_X, EYE_Y, POISSON, SUPPORT_CASES, load_cases, mesh_step, regions, spring_matrix, traction,
)


BORE_RADIUS_MM = 1.13
PIN_RADIUS_MM = 1.
MIN_INPUT_ARM_MM = 12.
MAX_REGULAR_YAW_TORQUE_NM = .003024
TOUCH_ARM_MM = 14.
TOUCH_LOADS_N = (0., .1, .25, 1.)
SUPPORT_Z_MM = (109.35, 127.875)
CORNER_DIRECTIONS = tuple(product((-1., 1.), repeat=3))


def bore_constraints(mesh, patches, pin_x):
    nodes = np.unique(mesh.facets[:, np.concatenate(patches)])
    position = mesh.p[:, nodes].T
    normal = (position[:, :2]-[pin_x, EYE_Y])/BORE_RADIUS_MM
    height = position[:, 2]-119.
    return nodes, normal, np.column_stack((normal, normal*height[:, None], np.ones(len(nodes))))


def residual(field, constraints):
    nodes, normal, matrix = constraints
    radial = np.einsum('nj,nj->n', field[:2, nodes].T, normal)
    result = linprog([0., 0., 0., 0., -1.], A_ub=matrix,
                     b_ub=BORE_RADIUS_MM-PIN_RADIUS_MM+radial,
                     bounds=[(None, None)]*5, method='highs')
    if not result.success:
        raise RuntimeError(f'Cannot solve the straight-pin fit: {result.message}')
    return float(result.x[-1])


def unit_touch_load(side, angle, force, pads, indices, size):
    phase = radians(angle)
    arm = TOUCH_ARM_MM * np.array([sin(phase), -cos(phase), 0.])
    moment = np.cross(arm, force)
    height = SUPPORT_Z_MM[1]-SUPPORT_Z_MM[0]
    share = (119.-SUPPORT_Z_MM[0])/height
    couple = np.array([moment[1], -moment[0], 0.])/height
    lower, upper = pads[side]
    load = np.zeros(size)
    load[indices] = np.outer((1.-share)*force-couple, lower) + np.outer(share*force+couple, upper)
    return load


def fit(mesh, size, lug):
    left, right, traction_lug, yaw, feet = regions(mesh, lug)
    element = ElementVector(ElementTetP1())
    basis = Basis(mesh, element)
    indices = np.asarray(basis.split_indices())
    cases = list(load_cases(mesh, basis, yaw, feet, indices))
    pads = {side: [traction(mesh, element, patch, (1., 0., 0.))[indices[0]] for patch in patches]
            for side, patches in yaw.items()}
    local_geometry = [bore_constraints(mesh, yaw[side], pin_x) for side, pin_x in zip(yaw, EYE_X, strict=True)]
    sites = sorted({(case['load_split'], case['horn_deg']) for case, _ in cases if case['load_split'] != 'balanced'})
    touch_offsets = {site: len(cases)+3*slot for slot, site in enumerate(sites)}
    loads = [load for _, load in cases]
    loads.extend(unit_touch_load(side, angle, force, pads, indices, basis.N)
                 for side, angle in sites for force in np.eye(3))
    rhs = np.column_stack(loads)

    for support_name in ('compliant', 'stiff'):
        modulus, support, _ = SUPPORT_CASES[support_name]
        lam, shear = lame_parameters(modulus, POISSON)
        stiffness = asm(linear_elasticity(lam, shear), basis)
        anchors = spring_matrix(mesh, element, (left, right, traction_lug), support)
        solved = splu((stiffness+anchors).tocsc()).solve(rhs)
        if np.max(abs((stiffness+anchors)@solved-rhs)) > 1e-6:
            raise RuntimeError('Loaded cradle does not reach static equilibrium')
        case_trials = {}
        for load in TOUCH_LOADS_N:
            records = []
            driver = (MAX_REGULAR_YAW_TORQUE_NM*1000+load*TOUCH_ARM_MM)/MIN_INPUT_ARM_MM
            for index, (case, _) in enumerate(cases):
                translations = solved[:, index]*driver
                site = (case['load_split'], case['horn_deg'])
                if not load:
                    fields = [((0., 0., 0.), translations)]
                elif site in touch_offsets:
                    start = touch_offsets[site]
                    direct = solved[:, start:start+3]
                    fields = [(corner, translations+load*(direct@corner)) for corner in CORNER_DIRECTIONS]
                else:
                    continue
                for force, field in fields:
                    margins = [residual(field[indices], region) for region in local_geometry]
                    records.append(dict(case, force_components_per_N=force,
                                        two_pin_radial_margins_mm=margins, minimum_radial_margin_mm=min(margins)))
            case_trials[f'{load:g}'] = {
                'cases': len(records), 'direct_load_bound_N': load,
                'rod_force_bound_N': driver, 'worst': min(records, key=lambda row: row['minimum_radial_margin_mm']),
            }
        yield {'mesh_mm': size, 'elements': mesh.nelements, 'support': support_name,
               'modulus_MPa': modulus, 'support_N_per_mm': support, 'trials': case_trials}


def verify(cad, sizes):
    from export_cad import App, world_shape

    with TemporaryDirectory() as temporary:
        step = Path(temporary)/'cradle.step'
        doc = App.openDocument(str(cad))
        try:
            world_shape(doc.Part024).exportStep(str(step))
            center = world_shape(doc.EyePitchLinkCradlePin).CenterOfMass
            lug = (center.y, center.z)
        finally:
            App.closeDocument(doc.Name)
        trials = []
        for size in sizes:
            for row in fit(mesh_step(step, size), size, lug):
                trials.append(row)
                print(size, row['support'], {k: round(v['worst']['minimum_radial_margin_mm'], 5)
                                             for k, v in row['trials'].items()}, flush=True)
    with cad.open('rb') as stream:
        digest = file_digest(stream, 'sha256').hexdigest()
    return {
        'cad_sha256': digest, 'eye_hole_diameter_mm': 2*BORE_RADIUS_MM,
        'steel_pin_diameter_mm': 2*PIN_RADIUS_MM, 'minimum_input_lever_mm': MIN_INPUT_ARM_MM,
        'regular_yaw_torque_bound_Nm': MAX_REGULAR_YAW_TORQUE_NM,
        'method': 'Linear elastic fitted shaft with free center and tilt; direct-force box encloses all unit directions.',
        'limits': 'Nominal machined diameters; static three-angle load cases. Fit excludes friction, printed dimensional drift and loaded link constraints.',
        'trials': trials,
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--mesh-mm', type=float, nargs='+', default=[1.25, 1.05])
    args = parser.parse_args()
    result = verify(args.cad.resolve(), args.mesh_mm)
    args.report.write_text(json.dumps(result, indent=2)+'\n')
