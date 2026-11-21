"""Check eye-pitch linkage clearance, force direction and finished pin play in B23 CAD."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from math import asin, atan2, cos, degrees, hypot, radians, sin, sqrt
from pathlib import Path

import FreeCAD as App
import Part

from export_cad import world_shape


POSE_LIMIT_DEG = 8.4
ANGLE_STEP_DEG = .2
TRANSLATION_TOLERANCE_MM = .2
PIN_DIAMETER_MM = 2.
FINISHED_BORES_MM = (2.08, 2.10)


def clearance(horn, rod, frame, pivot, phase, radius):
    # Distance to a rigid body is Lipschitz continuous with respect to its displacement.
    # These bounds cover the gaps between angular samples and the full 3D tolerance box.
    bounds = horn.BoundBox
    horn_radius = hypot(max(abs(bounds.YMin-pivot.y), abs(bounds.YMax-pivot.y)),
                        max(abs(bounds.ZMin-pivot.z), abs(bounds.ZMax-pivot.z)))
    backoff = TRANSLATION_TOLERANCE_MM*sqrt(3)
    pairs = (('horn_to_frame', horn_radius), ('rod_to_frame', radius))
    result = {name: {'sampled_min_mm': float('inf')} for name, _ in pairs}
    count = round(2*POSE_LIMIT_DEG/ANGLE_STEP_DEG)
    axis = App.Vector(1., 0., 0.)
    for tick in range(count+1):
        angle = -POSE_LIMIT_DEG + tick*ANGLE_STEP_DEG
        a, b = radians(phase), radians(phase+angle)
        moved_horn, moved_rod = horn.copy(), rod.copy()
        moved_horn.rotate(pivot, axis, angle)
        moved_rod.translate(App.Vector(0., radius*(cos(b)-cos(a)), radius*(sin(b)-sin(a))))
        for (name, _), moving in zip(pairs, (moved_horn, moved_rod), strict=True):
            gap = moving.distToShape(frame)[0]
            if gap < result[name]['sampled_min_mm']:
                result[name] = {'sampled_min_mm': gap, 'angle_deg': angle}
    for name, motion_radius in pairs:
        row = result[name]
        row['continuous_min_bound_mm'] = row['sampled_min_mm'] - motion_radius*radians(ANGLE_STEP_DEG/2)
        row['toleranced_min_bound_mm'] = row['continuous_min_bound_mm'] - backoff
    return result, count+1


def signed_arm(angle, pickup, rod_direction):
    y, z = pickup
    arm_y, arm_z = y*cos(angle)-z*sin(angle), y*sin(angle)+z*cos(angle)
    return arm_y*rod_direction[1] - arm_z*rod_direction[0]


def reverse_play(span, pickup, angle, diametral_clearance):
    phase = atan2(pickup[1], pickup[0])
    radius = hypot(*pickup)
    theta = phase+angle
    y, z = radius*cos(theta), radius*sin(theta)
    length = hypot(*span)
    total = 0.
    # With both fixed pins at Ø2, the sum of the two radial gaps equals one
    # diametral clearance. Find both sides of the reversal about the native pose.
    for sense in (-1., 1.):
        near, far = 0., radians(5.)
        for _ in range(28):
            half = (near+far)/2
            next_theta = theta+sense*half
            moved = hypot(span[0]+radius*cos(next_theta)-y, span[1]+radius*sin(next_theta)-z)
            if abs(moved-length) > diametral_clearance:
                far = half
            else:
                near = half
        total += far
    return degrees(total)


def bore_at(shape, axis):
    diameters = [2*face.Surface.Radius for face in shape.Faces
                 if isinstance(face.Surface, Part.Cylinder)
                 and hypot(face.Surface.Center.y-axis.y, face.Surface.Center.z-axis.z) < 1e-5
                 and abs(face.Surface.Axis.x) > .999]
    return min(diameters)


def force_path(horn_center, cradle_center, horn_pin, cradle_pin, cradle_play):
    px = (horn_pin.y-horn_center.y, horn_pin.z-horn_center.z)
    py = (cradle_pin.y-cradle_center.y, cradle_pin.z-cradle_center.z)
    if hypot(px[0]-py[0], px[1]-py[1]) > 1e-5:
        raise ValueError('Motor and cradle eye-pitch arms do not form a parallelogram')
    span = (horn_pin.y-cradle_pin.y, horn_pin.z-cradle_pin.z)
    length = hypot(*span)
    direction = tuple(coord/length for coord in span)
    radius = hypot(*px)
    poses = tuple(radians(index*.1) for index in range(-80, 81))
    arms = tuple((signed_arm(theta, px, direction), signed_arm(theta, py, direction)) for theta in poses)
    min_arm = min(min(arm) for arm in arms)
    max_arm = max(max(arm) for arm in arms)
    if min_arm <= 0.:
        raise ValueError('Eye-pitch force path crosses a dead center')
    return {
        'rod_axis_span_mm': length, 'two_arm_radius_mm': [radius, hypot(*py)],
        'min_signed_effective_arm_mm': min_arm, 'max_signed_effective_arm_mm': max_arm,
        'min_transmission_angle_deg': degrees(asin(min_arm/radius)),
        'endpoint_signed_arms_mm': [arms[0], arms[-1]],
        'input_to_output_torque_ratio': [min(a/b for a, b in arms), max(a/b for a, b in arms)],
        'finished_bore_mm': FINISHED_BORES_MM,
        'link_bore_only_max_reversal_deg': [
            max(reverse_play(span, px, theta, bore-PIN_DIAMETER_MM) for theta in poses)
            for bore in FINISHED_BORES_MM],
        'with_unseated_cradle_support_max_reversal_deg': [
            max(reverse_play(span, px, theta, bore-PIN_DIAMETER_MM+cradle_play/2) for theta in poses)
            for bore in FINISHED_BORES_MM],
        'link_force_N_at_5p32mNm_nominal': 5.32/min_arm,
        'link_force_N_at_19p32mNm_with_1N_touch': 19.32/min_arm,
    }


def verify(cad):
    doc = App.openDocument(str(cad))
    try:
        geometry = json.loads(doc.R5.MotionGeometry)
        motion = geometry['eye_pitch']
        phase, radius = motion['phase_deg'], motion['crank_radius_mm']
        motor = App.Vector(*motion['servo_axis_mm'])
        cradle = App.Vector(*motion['cradle_axis_mm'])
        horn, rod, carrier = map(world_shape, (doc.Part043, doc.Part044, doc.Part024))
        gaps, samples = clearance(horn, rod, world_shape(doc.Part019), motor, phase, radius)
        # Rotation about X leaves the axial seat gaps invariant at every eye-pitch angle.
        axial = {
            'horn_to_motor_plate': horn.BoundBox.XMin-world_shape(doc.Part042).BoundBox.XMax,
            'rod_to_horn': rod.BoundBox.XMin-horn.BoundBox.XMax,
            'rod_to_cradle': rod.BoundBox.XMin-carrier.BoundBox.XMax,
        }
        for name, gap in axial.items():
            gaps[name] = {'continuous_min_bound_mm': gap,
                          'toleranced_min_bound_mm': gap-TRANSLATION_TOLERANCE_MM}
        cradle_bore = bore_at(carrier, cradle)
        cradle_pin = world_shape(doc.Part028).BoundBox.YLength
        fitted_bearings = geometry.get('eye_pitch_bearings')
        support_play = cradle_bore-cradle_pin
        if fitted_bearings:
            # MC3 internal travel plus the upper limit required of the measured shaft fit.
            support_play = .010 + .010
        linkage = force_path(motor, cradle, world_shape(doc.EyePitchLinkHornPin).CenterOfMass,
                             world_shape(doc.EyePitchLinkCradlePin).CenterOfMass, support_play)
        if fitted_bearings:
            linkage['with_bearing_support_max_reversal_deg'] = linkage.pop(
                'with_unseated_cradle_support_max_reversal_deg')
            linkage['bearing_support_play_mm'] = {
                'vendor_mc3_internal_radial_travel_max_mm': .010,
                'conditional_measured_shaft_fit_travel_max_mm': .010,
                'total_assumed_travel_mm': support_play,
            }
            linkage['bonded_cradle_bore_and_pin_mm'] = [cradle_bore, cradle_pin]
        else:
            linkage['cradle_support_bore_and_pin_mm'] = [cradle_bore, cradle_pin]
    finally:
        App.closeDocument(doc.Name)
    with cad.open('rb') as stream:
        digest = file_digest(stream, 'sha256').hexdigest()
    passed = (all(gap['toleranced_min_bound_mm'] > 0 for gap in gaps.values())
              and linkage['min_transmission_angle_deg'] >= 40.
              and max(linkage['link_bore_only_max_reversal_deg']) <= 2.)
    return {
        'cad_sha256': digest, 'pass': passed, 'eye_pitch_phase_deg': phase,
        'scope': 'Frame clearance and link force path. P04 checks assembled backlash with support seating and gear play.',
        'shape_sample_count': samples, 'clearance_pose_limit_deg': POSE_LIMIT_DEG,
        'relative_offset_each_axis_mm': TRANSLATION_TOLERANCE_MM,
        'clearance': gaps, 'force_path': linkage,
    }


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    result = verify(args.cad.resolve())
    args.report.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['pass'] else 1)
