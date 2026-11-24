"""Check both B25 jaw stop reserves from one closed reference."""

from argparse import ArgumentParser
from hashlib import sha256
from itertools import product
import json
from math import atan2, ceil, cos, floor, pi, radians, sin
from pathlib import Path
import re

import FreeCAD as App
import Mesh  # Registers Mesh::Feature when FreeCAD opens the file.
import fcl
import numpy as np
import trimesh
from trimesh.collision import mesh_to_BVH


CONTROL = Path(__file__).resolve().parents[1]
CAD = CONTROL.parent / 'mechanical/revisions/b25/R5-B25-Assembly.FCStd'
SKETCH = CONTROL / 'openrb/R5B1/R5B1.ino'
STAY = 'Jaw_37_right_jaw_bearing_stay'
ARM = 'Jaw_39_right_jaw_pivot_arm'
JAW = 'Jaw_30_moving_jaw'
SHELL = 'Part073'
CLOSED_REFERENCE_TICKS = 11
CLOSED_RESERVE = 2.
TICK_DEGREES = 360 / 4096
RESERVE = 1.  # Section 6's Goal PWM-limited direct-drive jaw exception.


def installed_mesh(doc, name):
    obj = doc.getObject(name)
    mesh = obj.Mesh.copy()
    mesh.Placement = obj.getGlobalPlacement()
    points, faces = mesh.Topology
    return trimesh.Trimesh([tuple(point) for point in points], faces, process=False)


def relative_bounds(stay, arm, pivot, phase, limit_deg=6.):
    # Print 37 is rotated about Y so its bed normal is world X. The one-piece jaw
    # is printed in part 30's frame, whose X axis stays the opening axis.
    fixed_warp = .002 * np.linalg.norm(stay.vertices[:, 1:] - pivot[1:], axis=1).max()
    print_rotation = trimesh.transformations.rotation_matrix(phase, (1., 0., 0.))[:3, :3]
    pin_datum = np.array([arm.bounds[0, 0], *pivot[1:]])
    print_plane = ((arm.vertices - pin_datum) @ print_rotation)[:, :2]
    arm_warp = .002 * np.linalg.norm(print_plane, axis=1).max()
    # ISO 8734 m6 Ø4 pin lower limit, the largest J4 model and the fixed print bias.
    glued_pin_offset = (4.25 - .15 - 4.004) / 2
    bearing_pocket_offset = .05 / 2
    bearing_radial_play = .010  # Full standard miniature MC3 travel.
    radial_play = glued_pin_offset + bearing_pocket_offset + bearing_radial_play
    upper_angle = phase + radians(limit_deg)
    if not 0. <= phase <= upper_angle <= pi/2:
        raise ValueError('The tolerance projection requires the opening arc in the first quadrant')

    def projected(cosine, sine):
        angle = max(phase, min(upper_angle, atan2(sine, cosine)))
        return cosine*cos(angle) + sine*sin(angle)

    box = (.30 + fixed_warp,
           .2 + projected(.2, .1+arm_warp) + radial_play,
           .2 + projected(.1+arm_warp, .2) + radial_play)
    return np.asarray(box), {
        'fixed_warp_span_mm': fixed_warp / .002,
        'moving_warp_span_mm': arm_warp / .002,
        'projected_through_jaw_deg': limit_deg,
        'radial_fit_terms_mm': {'glued_pin': glued_pin_offset, 'bearing_pocket': bearing_pocket_offset,
                                'bearing_internal': bearing_radial_play},
        'relative_world_half_box_mm': list(box),
    }


def placement(fixed, moving, pivot, angle, translation):
    matrix = trimesh.transformations.rotation_matrix(radians(angle), (1., 0., 0.), pivot)
    moving.setTransform(fcl.Transform(matrix[:3, :3].copy(), matrix[:3, 3].copy()))
    fixed.setTranslation(np.asarray(translation, dtype=float))


def contact(fixed, moving, pivot, shift):
    request = fcl.CollisionRequest()

    def hit(angle):
        placement(fixed, moving, pivot, angle, shift)
        return fcl.collide(fixed, moving, request, fcl.CollisionResult()) != 0

    low = 0.
    for high in np.linspace(0., 10., 201):
        if hit(high):
            break
        low = high
    else:
        return None
    while high-low > 1e-5:
        mid = (low+high)/2
        if hit(mid):
            high = mid
        else:
            low = mid
    return high


def verify_continuous_clearance(fixed, moving, pivot, rotation_radius, box, angle, minimum=0.):
    stack = [(np.array([min(0., angle), *-box]), np.array([max(0., angle), *box]))]
    scale = np.array([rotation_radius*radians(1.), 1., 1., 1.])
    request = fcl.DistanceRequest()
    lower_gap = float('inf')
    cells = 0
    while stack:
        low, high = stack.pop()
        mid = (low + high) / 2
        placement(fixed, moving, pivot, mid[0], mid[1:])
        gap = fcl.distance(fixed, moving, request, fcl.DistanceResult())
        widths = (high-low)*scale
        # The maximum surface displacement across the cell is bounded by its
        # translation half-diagonal plus the largest arc distance of the moving part.
        lower = gap - (widths[0] + np.linalg.norm(widths[1:])) / 2
        cells += 1
        if lower >= minimum and lower > 0.:
            lower_gap = min(lower_gap, lower)
            continue
        if gap < minimum or gap <= 0. or widths.max() < 1e-7:
            raise ValueError(f'Cannot establish clearance near {mid.tolist()}')
        split = widths.argmax()
        upper_left, lower_right = high.copy(), low.copy()
        upper_left[split] = lower_right[split] = mid[split]
        stack.extend(((low, upper_left), (lower_right, high)))
    return lower_gap, cells


def check(cad=CAD, powered_minimum=None):
    firmware = SKETCH.read_text()
    wire_limit = float(re.search(r'jawMaxDegrees = ([\d.]+)f;', firmware)[1])
    tolerance = int(re.search(r'jawPositionTolerance = (\d+);', firmware)[1])
    span = floor(wire_limit / TICK_DEGREES)
    accepted = (span + tolerance) * TICK_DEGREES
    zero = CLOSED_REFERENCE_TICKS * TICK_DEGREES
    open_feedback = zero + accepted
    open_proof = ceil((open_feedback + RESERVE) * 100) / 100
    close_proof = zero - tolerance * TICK_DEGREES - CLOSED_RESERVE
    doc = App.openDocument(str(cad.resolve()))
    try:
        pivot = np.array(tuple(doc.JawMotion.Placement.Base))
        phase = doc.getObject(JAW).getGlobalPlacement().Rotation.Angle
        stay, arm = (installed_mesh(doc, name) for name in (STAY, ARM))
        jaw, shell = (installed_mesh(doc, name) for name in (JAW, SHELL))
    finally:
        App.closeDocument(doc.Name)
    box, inputs = relative_bounds(stay, arm, pivot, phase, open_proof)
    tip = jaw.vertices[jaw.vertices[:, 1].argmin()]
    axis = (1., 0., 0.)
    at_zero = trimesh.transformations.rotation_matrix(radians(zero), axis, pivot)
    at_goal = trimesh.transformations.rotation_matrix(radians(zero + span*TICK_DEGREES), axis, pivot)
    jaw_tip_drop = trimesh.transform_points([tip], at_zero)[0, 2] - trimesh.transform_points([tip], at_goal)[0, 2]
    closing_box = np.full(3, .40)
    closing_pair = [fcl.CollisionObject(mesh_to_BVH(mesh)) for mesh in (shell, jaw)]
    jaw_radius = np.linalg.norm(jaw.vertices[:, 1:] - pivot[1:], axis=1).max()
    closing_gap, closing_cells = verify_continuous_clearance(
        *closing_pair, pivot, jaw_radius, closing_box, close_proof)
    closing = {'pair': [SHELL, JAW], 'relative_translation_half_box_mm': closing_box.tolist(),
               'clear_through_cad_angle_deg': close_proof, 'reserve_from_accepted_feedback_at_least_deg': CLOSED_RESERVE,
               'continuous_lower_gap_mm': closing_gap, 'verified_cells': closing_cells}
    fixed, moving = (fcl.CollisionObject(mesh_to_BVH(mesh)) for mesh in (stay, arm))
    radius = np.linalg.norm(arm.vertices[:, 1:] - pivot[1:], axis=1).max()
    clearance, cells = verify_continuous_clearance(fixed, moving, pivot, radius, box, open_proof)
    powered = None
    if powered_minimum is not None:
        gap, count = verify_continuous_clearance(fixed, moving, pivot, radius, box, open_feedback, powered_minimum)
        powered = {'end_deg': accepted, 'minimum_mm': gap, 'required_mm': powered_minimum, 'verified_cells': count}
    witnesses = [(contact(fixed, moving, pivot, shift), shift) for shift in product(*[(-b, 0., b) for b in box])]
    contacts = [(angle, shift) for angle, shift in witnesses if angle is not None]
    if not contacts:
        raise ValueError('The right jaw stop did not contact within the inspected range')
    first, shift = min(contacts)
    return {
        'cad_sha256': sha256(cad.read_bytes()).hexdigest(),
        'firmware_sha256': sha256(SKETCH.read_bytes()).hexdigest(),
        'pair': [STAY, ARM],
        'closed_reference_from_cad_ticks': CLOSED_REFERENCE_TICKS,
        'closing': closing,
        'pivot_mm': pivot.tolist(),
        'tolerance_model': inputs,
        'wire_goal_max_deg': wire_limit,
        'goal_span_max_ticks': span,
        'goal_span_max_encoder_deg': span * TICK_DEGREES,
        'closed_front_tip_point_mm': tip.tolist(),
        'jaw_tip_drop_at_goal_mm': float(jaw_tip_drop),
        'feedback_opening_allowance_ticks': tolerance,
        'accepted_feedback_max_encoder_deg': accepted,
        'contact_free_through_deg_in_relative_envelope': open_proof - zero,
        'required_stop_reserve_deg': RESERVE,
        'continuous_lower_gap_mm': clearance,
        'verified_cells': cells,
        'reserve_from_goal_at_least_deg': open_proof - zero - span * TICK_DEGREES,
        'reserve_from_accepted_feedback_at_least_deg': open_proof - open_feedback,
        'earliest_sampled_contact_deg': first - zero,
        'sampled_contact_shift_mm': list(shift),
        'powered_clearance': powered,
        'scope': 'Rigid installed CAD, with the same closed reference for both stop checks. Measure first contacts, mounted fit and real closed reference on each assembly.',
        'references': {
            'conditions': '../spec/conditions.md',
            'pin_m6': 'https://www.pinstructure.com/ProductGrp/ISO8734-C1_Stainless_Hardened_Dowel_Pins',
            'bearing_MR104': 'https://www.nsk.com/eu-en/engineering/mr104bzzmc3-apn.html',
            'standard_MC3_clearance': 'https://www.nsk.com/common/data/ctrgPdf/bearings/e126h.pdf',
        },
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--cad', type=Path, default=CAD)
    parser.add_argument('--powered-minimum', type=float, help='Also verify a clearance in mm over the powered interval')
    print(json.dumps(check(**vars(parser.parse_args())), indent=2))
