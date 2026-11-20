"""Fixed-length jaw leads through the side of the B16 neck rotor."""

from itertools import product

import numpy as np
from scipy.optimize import brentq

from wiring_motion import arc_lengths, round_corners, segment, transform


JAW_PORT = (8.8,-21.)
JAW_EXIT = (-18.8,-1.3)
JAW_DATA = 'motor6-data'
JAW_SUPPLY = ('motor6-return','motor6-power')
JAW_RADIUS = 5.715
DATA_TURN_RADIUS = 6.7
T = np.linspace(0.,1.,90)[:,None]
BASE_BUMP = 16.*T**2*(1.-T)**2


def circular_fillets(points, radius):
    """Join straight guide spans with tangent arcs at the specified radius."""
    points = np.asarray(points,dtype=float)
    edges = np.diff(points,axis=0)
    lengths = np.linalg.norm(edges,axis=1)
    unit = edges/lengths[:,None]
    angles = np.arccos(np.clip(np.einsum('ij,ij->i',unit[:-1],unit[1:]),-1.,1.))
    trim = np.r_[0.,radius*np.tan(angles/2.),0.]
    if np.any(trim[:-1]+trim[1:]>lengths):
        raise ValueError('Adjacent jaw turns exceed their guide span')
    sections = [points[:1]]
    for i, angle in enumerate(angles):
        if angle < 1e-7:
            continue
        u,v = unit[i:i+2]
        origin = points[i+1]-trim[i+1]*u
        normal = (v-np.cos(angle)*u)/np.sin(angle)
        theta = np.linspace(0.,angle,int(np.ceil(angle*radius/.72))+1)[:,None]
        turn = origin+radius*(np.sin(theta)*u+(1.-np.cos(theta))*normal)
        sections.extend((segment(sections[-1][-1],turn[0],.72)[1:-1],turn))
    sections.append(segment(sections[-1][-1],points[-1],.72)[1:])
    path = np.vstack(sections)
    return path[np.r_[True,np.linalg.norm(np.diff(path,axis=0),axis=1)>1e-7]]


def base_run(motion, offset=(0.,0.,0.)):
    """Make the low service turn and enter the rotor vertically."""
    x,y,z = -24.397,-8.786,-76.945
    fixed = circular_fillets([
        [36.,36.5,-63.7], [36.,48.,-63.7], [28.,42.,-52.6], [26.5,20.,-53.2],
        [28.,-7.,-66.], [18.,-15.778,z], [9.,y,z], [x,y,z],
    ],DATA_TURN_RADIUS)
    theta = np.linspace(0.,np.pi,50)
    turn = np.column_stack((x-7.703*np.sin(theta),y+7.703*(np.cos(theta)-1.),np.full(len(theta),z)))
    start = turn[-1]
    end = transform([*JAW_PORT,-53.],motion['pan'])
    along_base = start+[max(6.5,.699*(end[0]-start[0])),0.,0.]
    up_to_rotor = end-[0.,0.,17.469]
    approach = ((1.-T)**3*start + 3.*T*(1.-T)**2*along_base +
                3.*T**2*(1.-T)*up_to_rotor + T**3*end + BASE_BUMP*offset)
    return np.vstack((fixed,turn[1:],approach[1:]))


def data_centerline(motion, guides, entry):
    x2,y2,y3,xh,yh = guides
    pan,head = motion['pan'],motion['head']
    changeover = [xh,yh,83.]
    upper = np.vstack((transform([
        [*JAW_PORT,-53.], [*JAW_PORT,-24.], [x2,y2,-10.], [3.,y3,13.], [-9.,-20.,55.],
    ],pan),.39*transform(changeover,pan)+.61*transform(changeover,head),transform([
        [-6.2,-16.5,96.5], [-5.5,JAW_EXIT[1],103.5], [*JAW_EXIT,103.5],
    ],head)))
    return np.vstack((entry,circular_fillets(upper,6.75)[1:]))


def data_length(path, motion, length, profile):
    angle, z0, span = profile
    phase = np.sin(np.pi*np.clip((path[:,2]-z0)/span,0.,1.))**2
    theta = np.radians(angle)
    direction = np.array([np.cos(theta),np.sin(theta),0.]) @ motion['pan'][:3,:3].T
    delta = phase[:,None]*direction

    def error(amplitude):
        return arc_lengths(path+amplitude*delta)[-1]-length

    if error(0.)>0. or error(120.)<0.:
        return None
    return path+brentq(error,0.,120.,xtol=1e-8)*delta


def data_guides(yaw, pitch, jaw):
    default = (9.,-18.,-19.)
    rear = (9.,-13.,-19.)
    wide = (13.,-5.,-13.)
    choices = (rear,wide,default) if jaw and pitch==6. and yaw<0. else (default,rear,wide)
    sides = (-13.6,-12.) if pitch>=0. and yaw>=40. else (-12.,-13.6)
    # Separate the leads near the moving head before trying a larger neck bow.
    upper=((sides[0],-20.),(sides[0],-22.4),(sides[0],-17.8),(sides[1],-20.),
           (-14.8,-22.4),(-9.8,-20.),(sides[1],-17.8),(-9.8,-22.4))
    for guide, (xh,yh) in product((*choices,(9.,-12.,-8.),(9.,-18.,-7.)),upper):
        yield (*guide,xh,yh)


def data_profiles(yaw, pitch):
    left = (0.,3.,106.)
    rear = (290.,-21.,88.)
    neutral = (165.,-21.,106.)
    if pitch<=-9.:
        first = (left,(0.,-2.,106.),(15.,3.,106.),neutral,rear)
    elif yaw>=45.:
        first = (rear,(285.,-21.,101.),(135.,-21.,101.),neutral,left)
    else:
        first = (neutral,(150.,-21.,101.),(135.,-21.,101.),left,rear)
    grid = product(range(0,360,30),(-21.,-10.,3.),(101.,106.))
    return tuple(dict.fromkeys((*first,(15.,3.,99.),(315.,-12.,99.),(350.,-2.,106.),
                               (195.,-12.,106.),(245.,3.,106.),(0.,3.,99.),*grid)))


def supply_tail(name, points, motion, length, guide):
    """Close the old cut length within the free tail next to the EH plug."""
    join, x, stagger = guide
    lane = JAW_SUPPLY.index(name)
    height = 98.5+2.5*lane
    head = motion['head']
    local = transform(points,np.linalg.inv(head))
    k = int(np.flatnonzero(local[:,2]>=join)[0])

    def shaped(y):
        tail = transform([[x+lane*stagger,y+2.*lane,height-8.],
                          [-7.,JAW_EXIT[1],height],[*JAW_EXIT,height]],head)
        return np.vstack((points[:k-5],round_corners(np.vstack((points[k-5],points[k],tail)),11.)))

    def error(y):
        return arc_lengths(shaped(y))[-1]-length

    for bound in (22.,-29.):
        if error(-1.)*error(bound)<=0.:
            return shaped(brentq(error,min(-1.,bound),max(-1.,bound),xtol=1e-8))
    return None
