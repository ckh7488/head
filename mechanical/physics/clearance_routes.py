"""Clearance revisions to the fixed-length B16 harness."""

import numpy as np
from scipy.optimize import brentq

from cable_spacing import restore_length
from wiring_motion import arc_lengths, round_corners, slack_displacement, transform

FUSE_LENGTH = 141.83809321882086
ID1_EXIT = np.array([3.2,-27.8,86.85])
ID1_LEADS = ('motor1-return','motor1-power','motor1-data')
ID5_LEADS = ('motor5-return','motor5-power','motor5-data')


def wiring_blocks(wiring):
    # The rear B3B-EH header in Part038 mates towards -Z. The 8.1 mm
    # mated height is measured from the header's PCB plane at Z94.95.
    revised = {
        'ID1EH': dict(center=(ID1_EXIT+[0.,0.,3.25]).tolist(),size=[9.5,3.8,6.5]),
        'ID6EH': dict(center=[-22.05,-1.3,101.],size=[6.5,3.8,9.5]),
    }
    return [dict(block,**revised[block['id']]) if block['id'] in revised else block for block in wiring['blocks']]


def fuse_input():
    """Keep the original cut length and take the left lane past the neck harness."""
    x = -57.15088007571491
    guides = [
        [-46.,55.5,-61.7], [-46.,64.5,-61.7], [x+2.2,63.,-61.7],
        [x,39.,-61.], [x+.5,-27.,-62.], [-45.,-44.,-67.],
        [-37.,-46.,-67.], [-29.,-46.,-67.],
    ]
    return round_corners(np.asarray(guides),15.)


def fuse_passage():
    """The span of the input lead across the internal base rib."""
    points = fuse_input()
    return points[(points[:,0]<-51.) & (points[:,1]>=20.) & (points[:,1]<=49.)]


def resize_bow(name, points, motion, target):
    direction = slack_displacement({'id':name},points,motion)
    result = restore_length(points,direction,target)
    if result is None:
        raise ValueError(f'{name} cannot retain its cut length in the revised route')
    return result


def bell(distance, width):
    return .5+.5*np.cos(np.pi*np.clip(abs(distance)/width,0.,1.))


def id5_run(name, points, motion, length):
    """Lift the ID5 branch above the moving J7 leads next to the hub."""
    x,y,z = points.T
    ramp = np.clip((arc_lengths(points)-1.7)/4.5,0.,1.)
    lift = bell(x-3.,21.)*bell(y-43.,10.)*ramp
    path = points+lift[:,None]*[0.,-1.7,2.5]
    base = bell(x+33.,20.)*bell(y-25.,28.)*np.clip((-48.-z)/6.,0.,1.)
    # Share length take-up between the turn in the base and the neck bow.
    direction = .58*base[:,None]*[0.,1.,0.]+.42*slack_displacement({'id':name},path,motion)
    result = restore_length(path,direction,length)
    if result is None:
        raise ValueError(f'{name} cannot clear J7 at its cut length')
    return result


def id5_jaw_clearance(points, motion, length, yaw, pitch, jaw):
    """Keep the upper ID5 power bow away from the open chin at the right limit."""
    travel = np.clip((yaw-45.)/15.,0.,1.)*np.clip(pitch/6.,0.,1.)*np.clip(jaw/13.,0.,1.)
    if travel==0.:
        return points
    direction = np.array([.26,.15,0.]) @ motion['pan'][:3,:3].T
    path = points+travel*bell(points[:,2]-19.5,11.)[:,None]*direction
    return resize_bow('motor5-power',path,motion,length)


def camera_run(points, motion, length, pitch, eye=0.):
    """Take the camera lead behind the hub and away from the open jaw."""
    seam = int(np.flatnonzero(points[:,1]<31.)[0])
    guides = [
        points[0], [9.5,74.3,-57.5], [13.,72.51,-55.5],
        [22.99,73.5,-50.62], [35.4,72.68,-50.42], [40.2,54.,-51.68],
        points[seam-8], points[seam],
    ]
    path = np.vstack((round_corners(np.asarray(guides),13.),points[seam+1:]))
    distance = np.clip(abs(path[:,2]-8.)/28.5,0.,1.)
    bow = 3.*(1.+np.cos(np.pi*distance))*np.clip(pitch/6.,0.,1.)
    direction = np.array([1.,1.,0.])/np.sqrt(2.)
    path += bow[:,None]*(direction @ motion['pan'][:3,:3].T)
    path = resize_bow('USB-Camera',path,motion,length)
    if eye < 0.:
        # The upper run passes the outside ID1 pin as the eye module tilts down.
        distance = arc_lengths(path)
        height = transform(path,np.linalg.inv(motion['head']))[:,2]
        window = bell(height-82.5,16.)
        gate = np.clip((distance[-1]-distance)/9.,0.,1.)
        taper = .5-.5*np.cos(np.pi*gate)
        away = np.array([1.1,-.35,0.]) @ motion['head'][:3,:3].T
        path = resize_bow('USB-Camera',path+(window*taper*(-eye/8.))[:,None]*away,motion,length)
    return path


def camera_lead_in(points):
    """Keep the exit tangent and length when rounding the turn at the base USB plug."""
    seam = int(np.flatnonzero(points[:,0]>=31.496)[0])
    length = arc_lengths(points[:seam+1])[-1]
    start,end = points[[0,seam]]
    tangent = points[seam+1]-end
    before_end = end-4.602*tangent/np.linalg.norm(tangent)
    t = np.linspace(0.,1.,81)[:,None]
    rise = 16.*t**2*(1.-t)**2*np.array([0.,.109,.168])

    def curve(handle):
        after_start = start+[0.,-handle,0.]
        return ((1.-t)**3*start + 3.*t*(1.-t)**2*after_start +
                3.*t**2*(1.-t)*before_end + t**3*end + rise)

    handle = brentq(lambda h: arc_lengths(curve(h))[-1]-length,1.,16.,xtol=1e-8)
    return np.vstack((curve(handle),points[seam+1:]))


def id1_run(name, points, motion, length, pitch, eye):
    """Enter the moving eye module from below the rear EH connector."""
    lane = ID1_LEADS.index(name)-1
    rearward = np.clip((pitch+15.)/21.,0.,1.)*np.clip((eye+8.)/16.,0.,1.)**1.7
    low = np.array([69.,2.3,-18.,-3.,1.75,8.])
    high = np.array([64.,2.45,-26.,-3.4,.6,7.5])
    z, spacing, y, x, stagger, lead = low+rearward*(high-low)
    height = transform(points,np.linalg.inv(motion['head']))[:,2]
    seam = int(np.flatnonzero(height>=z)[0])
    guide = transform([x+lane*spacing,y+lane*stagger,z+9.],motion['head'])
    terminal = ID1_EXIT+[2.5*lane,0.,0.]
    pre = transform(terminal-[0.,0.,lead],motion['tilt'])
    end = transform(terminal,motion['tilt'])
    tail = round_corners(np.vstack((points[seam-5],points[seam],guide,pre,end)),11.)
    return resize_bow(name,np.vstack((points[:seam-5],tail)),motion,length)
