"""Relax the centerlines around adjacent cables while retaining their cut lengths."""
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import brentq
from scipy.spatial import cKDTree
import numpy as np

from wiring_motion import arc_lengths, slack_displacement


def restore_length(points, direction, target):
    def residual(offset):
        return arc_lengths(points + offset*direction)[-1] - target

    lo,hi = -35.,35.
    middle = residual(0.)
    if abs(middle) < 1e-7:
        return points
    if middle < 0.:
        change = brentq(residual,0.,hi,xtol=1e-8)
    elif residual(lo) < 0.:
        change = brentq(residual,lo,0.,xtol=1e-8)
    else:
        # The length of a displaced polyline is convex. Locate its minimum
        # before looking for the shorter root near the current working shape.
        from scipy.optimize import minimize_scalar
        least = minimize_scalar(residual,bounds=(lo,0.),method='bounded')
        if least.fun > 0.:
            return None
        change = brentq(residual,least.x,0.,xtol=1e-8)
    return points+change*direction


def soften_bends(points, radius):
    before=np.linalg.norm(np.diff(points,axis=0),axis=1)
    left,right=before[:-1],before[1:]
    fraction=left/np.maximum(left+right,1e-8)
    chord=points[:-2]+fraction[:,None]*(points[2:]-points[:-2])
    deflection=points[1:-1]-chord
    magnitude=np.linalg.norm(deflection,axis=1)
    fraction=np.clip(1.-left*right/(2*radius*np.maximum(magnitude,1e-8)),0.,1.)
    return -deflection*fraction[:,None]


def even_steps(points, target_step):
    edges=np.diff(points,axis=0)
    run=np.linalg.norm(edges,axis=1)
    shift=np.clip(run-target_step,-.45,.45)[:,None]*edges/np.maximum(run[:,None],1e-8)
    return shift[1:]-shift[:-1]


def arrange(cables, routes, motion, iterations=110, keepouts=(), neck_only=(), hold_head=False):
    """Allow the loose runs to spread, holding the plugs and rotor section in place."""
    by_id={route['id']:route for route in routes}
    wires=[]
    mobile=[]
    diameters=[]
    directions=[]
    for cable in (*cables,*keepouts):
        source=cable.points
        if cable.name in by_id:
            arc=arc_lengths(source)
            s=np.linspace(0.,arc[-1],int(np.ceil(arc[-1]/.9))+1)
            source=np.stack([np.interp(s,arc,source[:,j]) for j in range(3)],axis=1)
            weight=np.clip((np.minimum(s,s[-1]-s)-2.3)/6.,0.,1.)
            z=source[:,2]
            weight *= np.maximum(np.clip((-48.-z)/5.,0.,1.),np.clip((z+32.)/4.,0.,1.))
            if cable.name in neck_only:
                weight *= np.clip((44.-z)/12.,0.,1.)*np.clip((z+31.)/10.,0.,1.)
            if hold_head:
                weight *= np.clip((50.-z)/10.,0.,1.)
            direction=slack_displacement(by_id[cable.name],source,motion)
            eased=gaussian_filter1d(source,sigma=2.25,axis=0)
            smooth=source+.70*weight[:,None]*(eased-source)
            solved=restore_length(smooth,direction,cable.length)
            if solved is not None:
                source=solved
        else:
            weight=np.zeros(len(source))
            direction=None
        wires.append(source)
        mobile.extend(weight)
        diameters.extend([cable.diameter]*len(weight))
        directions.append(direction)

    points=np.concatenate(wires)
    initial=points.copy()
    indexes=np.cumsum([0]+[len(w) for w in wires])
    spans=[slice(i,j) for i,j in zip(indexes,indexes[1:])]
    labels=np.repeat(np.arange(len(wires)),np.diff(indexes))
    reference=labels>=len(cables)
    respects_reference=np.repeat(
        [c.name in ('motor3-data','motor6-data') for c in (*cables,*keepouts)],np.diff(indexes)
    )
    mobile=np.asarray(mobile)
    radii=np.asarray(diameters)/2
    for iteration in range(iterations):
        pairs=cKDTree(points).query_pairs(4.4,output_type='ndarray')
        a,b=pairs.T
        mask=(labels[a]!=labels[b]) & ((mobile[a]+mobile[b])>0)
        mask &= (~reference[a] | respects_reference[b]) & (~reference[b] | respects_reference[a])
        a,b=a[mask],b[mask]
        direction=points[a]-points[b]
        distance=np.linalg.norm(direction,axis=1)
        gap=radii[a]+radii[b]+.28-distance
        hit=gap>0
        if not hit.any():
            break
        a,b=a[hit],b[hit]
        direction,gap,distance=direction[hit],gap[hit],distance[hit]
        direction=np.divide(direction,distance[:,None],out=np.zeros_like(direction),where=distance[:,None]>1e-7)
        direction[distance<1e-7,0]=1.
        force=gap[:,None]*direction
        delta=np.zeros_like(points)
        np.add.at(delta,a,force)
        np.add.at(delta,b,-force)
        for span,preferred,cable in zip(spans,directions,cables):
            if preferred is None:
                continue
            offset=gaussian_filter1d(delta[span],sigma=2.4,axis=0)
            offset=np.clip(offset,-.65,.65)*mobile[span,None]*.53
            radius=12. if cable.name=='USB-Camera' else 5*cable.diameter
            bend=soften_bends(points[span],radius)
            spacing=even_steps(points[span],cable.length/(len(points[span])-1))
            offset[1:-1] += (.38*bend+.45*spacing)*mobile[span,None][1:-1]
            points[span] += offset-.0015*(points[span]-initial[span])
            if (iteration+1)%5==0 or iteration==iterations-1:
                solved=restore_length(points[span],preferred,cable.length)
                if solved is not None:
                    points[span]=solved

    result=[]
    for span,preferred,cable in zip(spans,directions,cables):
        if preferred is None:
            result.append(cable.points)
        else:
            solved=restore_length(points[span],preferred,cable.length)
            result.append(solved if solved is not None else cable.points)
    return result
