"""Length-constrained cable centerlines for the B16 routing revision (all units mm)."""
from dataclasses import dataclass
from math import atan2, ceil, cos, pi

import numpy as np
from scipy.optimize import brentq
import trimesh as tr

from check_head import pose as upper_pose


HATCH_TRAVEL = 30.
SAMPLE_STEP = 1.25
CAMERA_BORE_Y = -36.
CAMERA_BORE_RADIUS = 3.2
MOTOR_BORE_Y = -26.
MOTOR_BORE_RADIUS = 4.5
POWER_DIAMETER = 2.057


@dataclass(frozen=True)
class PowerLead:
    splice: tuple[float, float, float]
    fixed_guide: tuple[float, float, float]
    hatch_guide: tuple[float, float, float]
    terminal: tuple[float, float, float]
    cut_length: float


POWER_LEADS = {
    # J1 contacts in assembly coordinates: pad 2 /5V_IN at X=-10, pad 1 /GND at X=-5.
    'J1+': PowerLead((-42., 55.5, -61.7), (-55., 98., -76.5),
                    (-9.89, 117.11, -74.17), (-10., 86.5, -68.1), 186.507533392),
    'J1-': PowerLead((-54.5, 57.5, -70.95), (-52., 98., -81.),
                    (-9.30, 115.76, -78.93), (-5., 86.5, -68.1), 172.482996155),
}

# Preserve the cut lengths of the B16 harness when changing its routing.
NECK_CUT_LENGTHS = {
    'motor1-return': 351, 'motor1-power': 352, 'motor1-data': 355,
    'motor2-return': 437, 'motor2-power': 437, 'motor2-data': 441,
    'motor3-return': 438, 'motor3-power': 444, 'motor3-data': 451,
    'motor5-return': 401, 'motor5-power': 403, 'motor5-data': 407,
    'motor6-return': 399, 'motor6-power': 315, 'motor6-data': 416,
    'USB-Camera': 365,
}
J6_CUT_LENGTH = 52.


def rotation(angle, axis, center=(0, 0, 0)):
    return tr.transformations.rotation_matrix(np.radians(angle), axis, center)


def matrices(layout, yaw=0., pitch=0., eye=0., drop=0., jaw=0., blink=0.):
    """World transforms in the same joint convention used by the assembly viewer."""
    identity = np.eye(4)
    hatch = identity.copy()
    hatch[2, 3] = -drop
    pan = rotation(-yaw, (0, 0, 1))
    head = pan @ rotation(pitch, (1, 0, 0), (0, 0, 112))
    angles = (0., eye, 0., blink, jaw)
    transforms = dict(fixed=identity, hatch=hatch, pan=pan, head=head)
    for mode in set(layout['world_motion'].values()) - transforms.keys():
        transforms[mode] = head @ upper_pose(mode, angles, layout)
    return transforms


def transform(points, matrix):
    return np.asarray(points) @ matrix[:3, :3].T + matrix[:3, 3]


def arc_lengths(points):
    return np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]


def segment(a, b, step=SAMPLE_STEP):
    return np.linspace(a, b, max(2, ceil(np.linalg.norm(b-a)/step)+1))


def s_turn(a, b):
    """Two tangent circular arcs with parallel tangents in the +Y direction."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    offset = b - a
    run = float(offset[1])
    offset[1] = 0.
    span = np.linalg.norm(offset)
    if span < 1e-9:
        return segment(a, b), float('inf'), run
    theta = 2 * atan2(span, run)
    radius = (run*run + span*span) / (4*span)
    axis = offset / span
    angle = np.linspace(0., theta, max(3, ceil(radius*theta/SAMPLE_STEP)+1))
    arc = radius * ((1.-np.cos(angle[:, None])) * axis
                    + np.sin(angle[:, None]) * np.array([0., 1., 0.]))
    return np.vstack((a+arc, b-arc[-2::-1])), radius, 2*theta*radius


def service_return(a, b, cable_length):
    """Return along a half circle with two straight legs whose total length varies."""
    axis = b - a
    axis[1] = 0.
    width = np.linalg.norm(axis)
    radius = width / 2
    axis /= width
    tangent = np.array([0., 1., 0.])
    y = (cable_length - pi*radius + a[1] + b[1]) / 2
    if y < max(a[1], b[1]):
        raise ValueError('The 5 V loop is shorter than its two end tangents allow')
    start = a + (y-a[1])*tangent
    end = b + (y-b[1])*tangent
    angle = np.linspace(0., pi, max(3, ceil(pi*radius/SAMPLE_STEP)+1))
    arc = start + radius*((1.-np.cos(angle[:, None]))*axis + np.sin(angle[:, None])*tangent)
    return np.vstack((segment(a, start), arc[1:], segment(end, b)[1:])), radius


def power_lead(spec, drop):
    fixed, fixed_radius, fixed_length = s_turn(spec.splice, spec.fixed_guide)
    moving, moving_radius, moving_length = s_turn(spec.terminal, spec.hatch_guide)
    shift = np.array([0., 0., drop])
    loop, loop_radius = service_return(moving[-1]-shift, fixed[-1], spec.cut_length-fixed_length-moving_length)
    return (
        np.vstack((fixed, loop[-2::-1], moving[-2::-1]-shift)),
        spec.cut_length,
        min(fixed_radius, loop_radius, moving_radius),
    )


def j6_lead(drop, length):
    """A fixed-length jumper from the moving PH pin to the fixed WAGO."""
    start = np.array([-1.,46.45,-56.5-drop])
    end = np.array([31.,36.5,-63.7])
    t = np.linspace(0.,1.,97)[:,None]
    # Clear F2 and J8 in the first 10 mm of cover travel. The middle term
    # vanishes at both ends without changing either connector tangent.
    weight = (1.+cos(pi*min(1.,drop/10.62)))/2.
    bow = 6.*(1.-t)**2*t*t*weight*np.array([6.28,-19.82,6.33])

    def curve(extra):
        rise = start + [0.,0.,13.42+.17*drop-4.24*weight+extra]
        approach = end + [0.,10.68+4.87*extra,0.]
        return (1.-t)**3*start + 3.*t*(1.-t)**2*rise + 3.*t*t*(1.-t)*approach + t**3*end + bow

    def residual(extra):
        return arc_lengths(curve(extra))[-1]-length

    return curve(brentq(residual,-1.8,70.,xtol=1e-8))


def neck_routes(wiring):
    """Use the original harness terminations and move the camera out of the servo bore."""
    for route in wiring['routes']:
        if not (route['id'].startswith('motor') or route['id'] == 'USB-Camera'):
            continue
        route = dict(route)
        route['points'] = [list(p) for p in route['points']]
        name=route['id']
        if name == 'USB-Camera':
            route['points'][6:12] = [
                [40., 9., -51.8], [37., -13., -58.5], [29., -22., -60.],
                [19., -28., -57., 'fixed', 'pan', .32],
                [7., -34., -53.5, 'fixed', 'pan', .76],
                [0., -36., -52.6, 'pan'],
            ]
            for point in route['points']:
                z = point[2]
                if len(point) == 4 and point[3] == 'pan' and z > -51.:
                    point[1] -= float(np.interp(z, [-35., 34., 52., 64.], [10., 10., 7., 6.]))
                    point[0] += float(np.interp(z, [34., 52., 64.], [0., 8., 9.]))
                if 68. < z < 80. and len(point) > 3:
                    point[0] += 12.
                    point[1] -= 4.
            route['points'][-6:-3]=[
                [8.,-23.,64.,'pan'],[8.,-23.,72.,'pan'],[7.,-25.6,80.5,'head'],
            ]
            route['points'][-3][2]=82.5
            lead_radius=10.5
            route['points'][:4]=[
                [9.5+lead_radius*(1.-np.cos(t)),75.12-lead_radius*np.sin(t),-57.5]
                for t in np.linspace(0.,pi/2,13)
            ]+[[27.,64.62,-57.],[37.,64.62,-56.]]
            yield route
            continue

        motor,lead=name.split('-')
        lane=['return','power','data'].index(lead)-1
        # Stack the five branches in the free space behind the jaw-fuse block.
        lanes={'motor1':-62.5,'motor2':-65.2,'motor3':-67.9,'motor5':-70.6,'motor6':-73.3}
        for point in route['points']:
            if point[0] < -28. and -24. < point[1] < 6. and point[2] < -49.:
                point[0]=max(point[0],-34.)
            if len(point)==6 and point[3]=='fixed' and point[4]=='pan':
                blend=point[5]
                point[2]=lanes[motor] if blend < .6 else .44*lanes[motor]+.56*(-60.)
        if motor == 'motor1':
            terminal=route['points'][-1]
            x,y,z,_=terminal
            route['points'][-3:-1]=[[x,y-2.4,z-8.2,'tilt'],[x,y+2.6,z,'tilt']]
        elif motor == 'motor2':
            for index,point in enumerate(route['points']):
                if len(point)==4 and point[3]=='head' and point[0] in (-10.,4.) and 110. < point[2] < 133.:
                    point[0],point[1]=-10.+1.5*lane,-10.7
                    if point[2] > 125.:
                        point[2]=129.+lane
                        route['points'].insert(index+1,[4.,-13.,135.+lane,'head'])
                        break
        elif motor == 'motor6':
            route['points'][-5:-2]=[
                [-10.+1.55*lane,-12.,88.+1.6*lane,'head'],
                [-10.+1.55*lane,4.7,94.+2.5*lane,'head'],
                [-19.5+lane*.6,10.9,99.+2.5*lane,'head'],
            ]
            if lead == 'power':
                route['points'][4:7]=[[10.,-28.2,-75.2]]
                route['points'][5][:3]=[-8.2,-27.8,-73.2]
            elif lead == 'data':
                route['points'][1:3]=[[36.,41.55,-61.16],[30.37,42.66,-54.79]]
                route['points'][7][1:3]=[-12.5,-71.9]
                route['points'][8][1:3]=[-23.9,-71.]
                route['points'][9][1:3]=[-23.,-69.1]
        if motor in ('motor1','motor2','motor3','motor5'):
            port_x={'motor1':-22.66,'motor2':-12.71,'motor3':-3.,'motor5':21.39}[motor]
            x=port_x+lane*(2.5 if motor=='motor5' else 2.)
            first=route['points'][0]
            first[0]=x
            route['points'].insert(1,[x,first[1],first[2]+4.0,'hatch'])
        if name == 'motor3-data':
            # The third outlet of the fixed WAGO carries the signal to ID3.
            route['points'][:8]=[
                [41.,36.5,-63.7],[41.,41.5,-63.7],[40.7,44.44,-58.02],
                [40.,43.,-53.09],[37.,28.5,-51.],[34.17,11.,-59.78],
                [33.83,-13.,-67.38],[16.,-23.,-66.],
            ]
        yield route


def round_corners(points, trim):
    """Tangent quadratic turns with arc-length samples for the collision capsules."""
    samples = [points[0]]
    for a, b, c in zip(points, points[1:], points[2:]):
        prev = a-b
        next_ = c-b
        q, r = np.linalg.norm(prev), np.linalg.norm(next_)
        if min(q, r) < 1e-8:
            continue
        cut = min(.43*q, .43*r, trim)
        start, end = b+cut*prev/q, b+cut*next_/r
        samples.extend(segment(samples[-1], start)[1:])
        t = np.linspace(0., 1., max(5, ceil(cut*2/SAMPLE_STEP)+1))[1:,None]
        samples.extend((1-t)**2*start + 2*t*(1-t)*b + t*t*end)
    samples.extend(segment(samples[-1], points[-1])[1:])
    points = np.asarray(samples)
    keep = np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > 1e-7]
    return points[keep]


def round_route(route, transforms):
    transformed = []
    for x, y, z, *spec in route['points']:
        coord = np.array([x, y, z])
        p = transform(coord, transforms[spec[0] if spec else 'fixed'])
        if len(spec) > 1:
            p += spec[2] * (transform(coord, transforms[spec[1]]) - p)
        transformed.append(p)
    return round_corners(np.array(transformed), 11.)


def slack_displacement(route, points, transforms):
    """A bow above the plate takes up spare length without moving either terminal."""
    z = points[:, 2]
    camera = route['id'] == 'USB-Camera'
    phase = np.clip((z+31.) / (64. if camera else 73.), 0., 1.)
    shape = np.sin(pi*phase)**2
    angle = 23. if camera else 165.
    angle = np.radians(angle)
    vector = np.array([np.cos(angle), np.sin(angle), 0.]) @ transforms['pan'][:3, :3].T
    return shape[:, None] * vector


def neck_lead(route, transforms, cable_length):
    points = round_route(route, transforms)
    direction = slack_displacement(route, points, transforms)

    def error(amplitude):
        return arc_lengths(points + amplitude*direction)[-1] - cable_length

    if error(0.) > 1e-6 or error(130.) < 0.:
        raise ValueError(f"{route['id']} cannot take up its fixed length at this pose")
    return points + brentq(error, 0., 130., xtol=1e-8)*direction
