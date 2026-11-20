"""Measure B16 cable length, bend radius and contacts along the CAD joint sweeps."""
from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import combinations, product
import json
from pathlib import Path

import fcl
import numpy as np
from scipy.spatial import cKDTree
import trimesh as tr
from trimesh.collision import mesh_to_BVH

from assembly_sweeps import fastener
from cable_spacing import arrange
from clearance_routes import (
    FUSE_LENGTH, ID1_LEADS, ID5_LEADS, camera_lead_in, camera_run, fuse_input,
    id1_run, id5_jaw_clearance, id5_run, wiring_blocks,
)
from jaw_routing import JAW_DATA, JAW_RADIUS, JAW_SUPPLY, base_run, data_centerline, data_guides, data_length, data_profiles, supply_tail
from wiring_motion import (
    POWER_DIAMETER, POWER_LEADS, arc_lengths, j6_lead, matrices, neck_lead, neck_routes, power_lead, round_route, transform,
)


ROOT = Path(__file__).resolve().parents[2]
CABLE_CLEARANCE = .25
HUB_CONNECTION = {
    'motor1': ('HubPlugJ4','HubBodyJ4','ID1EH','Part038'),
    'motor2': ('HubPlugJ5','HubBodyJ5','ID2EH','Part041'),
    'motor3': ('HubPlugJ6','HubBodyJ6','ID3EH','Part045'),
    'motor3-data': ('Wdata','ID3EH','Part045'),
    'motor5': ('HubPlugJ8','HubBodyJ8','ID5EH','Part018'),
    'motor6': ('Wdata','W5g','FuseID6','ID6EH','Jaw_XL330_M288_Jaw'),
    'USB-Camera': ('CameraUSB','CameraMate','Part067'),
    'J1+': ('W5p','J1Mate','HubBodyJ1'),
    'J1-': ('W5g','J1Mate','HubBodyJ1'),
    'J6-branch': ('HubPlugJ6','HubBodyJ6','Wdata'),
    'fuse-in': ('W5p','FuseID6'),
}
DATA_KEEPOUTS = {'J2+','J3-G','J3-D'}


@dataclass
class Cable:
    name: str
    points: np.ndarray
    diameter: float
    length: float
    radius: float
    bend_point: list[float] | None = None

    def __post_init__(self):
        self.arc = arc_lengths(self.points)
        self.start, self.end = self.points[:-1],self.points[1:]
        self.midpoints = (self.start+self.end)/2
        self.half_step = float(np.diff(self.arc).max())/2
        self.tree = cKDTree(self.midpoints)


def discrete_bend(points):
    """Local circumradius of the sampled centerline, including the route transitions."""
    u,v = np.diff(points,axis=0)[:-1],np.diff(points,axis=0)[1:]
    twice_area = np.linalg.norm(np.cross(u,v),axis=1)
    valid = twice_area > 1e-10
    u,v = u[valid],v[valid]
    radii = np.linalg.norm(u,axis=1)*np.linalg.norm(v,axis=1)*np.linalg.norm(u+v,axis=1)/(2*twice_area[valid])
    if not len(radii):
        return float('inf'),None
    k=int(np.argmin(radii))
    return float(radii[k]),points[np.flatnonzero(valid)[k]+1].round(2).tolist()


def radius_target(name, diameter):
    if name in POWER_LEADS:
        return 21.
    if name == 'USB-Camera':
        return 12.
    return 5*diameter


def bundle(wiring, cut_lengths, motion, drop, packed=False, pitch=0., eye=0.):
    result=[]
    routes=tuple(neck_routes(wiring))
    for wire in routes:
        length=float(cut_lengths[wire['id']])
        points=neck_lead(wire,motion,length)
        result.append(Cable(wire['id'],points,wire['diameter'],length,*discrete_bend(points)))
    result.extend(power_cables(drop))
    length=float(cut_lengths['J6-branch'])
    jumper=j6_lead(drop,length)
    diameter=next(r['diameter'] for r in wiring['routes'] if r['id']=='J6-branch')
    result.append(Cable('J6-branch',jumper,diameter,length,*discrete_bend(jumper)))
    keepouts=[Cable(route['id'],round_route(route,motion),route['diameter'],0.,0.)
              for route in wiring['routes'] if route['id'] in DATA_KEEPOUTS]
    if packed:
        refined=packed_cables(result,routes,motion,keepouts,110)
        if any(segment_gap(a,b) for a,b in combinations(refined,2)):
            # A few dense poses need longer to converge with the same spacing target.
            retry=packed_cables(result,routes,motion,keepouts,180)
            if not any(segment_gap(a,b) for a,b in combinations(retry,2)):
                refined=retry
        result=refined
    revised=revised_cables(result,motion,pitch,eye,cut_lengths)
    if not packed:
        return finish_camera(revised)
    movable=[route for route in routes if route['id']!='USB-Camera']
    neck_only={route['id'] for route in movable}-set(ID1_LEADS)
    revised=packed_cables(revised,movable,motion,keepouts,135,neck_only)
    neighbors=reference_cables(wiring,motion,revised)
    pitch_routes=[route for route in routes if route['id'] in ID5_LEADS]
    # Treat the surrounding harness as fixed while settling the lifted ID5 branch.
    settled=packed_cables([*revised,*neighbors],pitch_routes,motion,(),130,hold_head=True)
    return finish_camera(settled[:len(revised)])


def revised_cables(cables, motion, pitch, eye, cut_lengths):
    revised=[]
    for cable in cables:
        if cable.name=='USB-Camera':
            points=camera_run(cable.points,motion,cable.length,pitch,eye)
        elif cable.name in ID1_LEADS:
            points=id1_run(cable.name,cable.points,motion,cable.length,pitch,eye)
        elif cable.name in ID5_LEADS:
            points=id5_run(cable.name,cable.points,motion,cable.length)
        else:
            points=cable.points
        revised.append(routed_cable(cable,points))
    points=fuse_input()
    revised.append(Cable('fuse-in',points,1.143,cut_lengths.get('fuse-in',FUSE_LENGTH),*discrete_bend(points)))
    return revised


def routed_cable(cable, points):
    return cable if cable.points is points else Cable(
        cable.name,points,cable.diameter,cable.length,*discrete_bend(points))


def finish_camera(cables):
    return [routed_cable(c, camera_lead_in(c.points)) if c.name=='USB-Camera' else c for c in cables]


def reference_cables(wiring, motion, cables):
    active={cable.name for cable in cables}
    return [Cable(route['id'],round_route(route,motion),route['diameter'],0.,0.)
            for route in wiring['routes'] if route['id'] not in active]


def packed_cables(cables, routes, motion, keepouts, iterations, neck_only=(), hold_head=False):
    paths=arrange(cables,routes,motion,iterations=iterations,keepouts=keepouts,
                  neck_only=neck_only,hold_head=hold_head)
    return [routed_cable(cable,points) for cable,points in zip(cables,paths,strict=True)]


def power_cables(drop):
    result=[]
    for name,lead in POWER_LEADS.items():
        points,length,radius=power_lead(lead,drop)
        result.append(Cable(name,points,POWER_DIAMETER,length,radius))
    return result


def closest_segments(first, second, i, j):
    """Closest points on each pair of finite segments, including both endpoints."""
    a, c = first.start[i], second.start[j]
    u, v = first.end[i]-a, second.end[j]-c
    w = a-c
    dot = lambda x,y: np.einsum('ij,ij->i',x,y)
    uu, uv, vv, uw, vw = dot(u,u), dot(u,v), dot(v,v), dot(u,w), dot(v,w)
    den = uu*vv-uv**2
    nz = den>1e-10
    s = np.divide(uv*vw-vv*uw,den,out=np.zeros_like(den),where=nz)
    t = np.divide(uu*vw-uv*uw,den,out=np.zeros_like(den),where=nz)
    interior = nz & (s>=0.) & (s<=1.) & (t>=0.) & (t<=1.)
    zero, one = np.zeros_like(s), np.ones_like(s)
    ss = np.stack((zero,one,np.clip(-uw/uu,0.,1.),np.clip((uv-uw)/uu,0.,1.),s))
    tt = np.stack((np.clip(vw/vv,0.,1.),np.clip((vw+uv)/vv,0.,1.),zero,one,t))
    dist = np.linalg.norm(w + ss[:,:,None]*u - tt[:,:,None]*v,axis=2)
    dist[-1,~interior] = np.inf
    best = np.argmin(dist,axis=0)
    col = np.arange(len(i))
    return dist[best,col], ss[best,col], tt[best,col]


def segment_gap(first, second):
    """Minimum surface distance for the piecewise-linear cables, including between nodes."""
    radii=(first.diameter+second.diameter)/2
    candidates=first.tree.query_ball_tree(second.tree,radii+first.half_step+second.half_step)
    i=np.repeat(np.arange(len(candidates)),[len(row) for row in candidates])
    if not len(i):
        return None
    j=np.concatenate(candidates).astype(int)
    gap, s, t = closest_segments(first,second,i,j)
    k=int(np.argmin(gap))
    clearance=float(gap[k]-radii)
    if clearance < -.06:
        a=first.start[i[k]]+s[k]*(first.end[i[k]]-first.start[i[k]])
        b=second.start[j[k]]+t[k]*(second.end[j[k]]-second.start[j[k]])
        return {'wire':first.name,'other':second.name,'point':((a+b)/2).round(2).tolist(),
                'overlap_mm':round(-clearance,3)}
    return None


def self_gap(cable):
    """Ignore the continuous sheath at nearby arc positions on the same wire."""
    threshold=max(3.,2*cable.diameter)
    i,j=cable.tree.query_pairs(cable.diameter+2*cable.half_step,output_type='ndarray').T
    valid=(cable.arc[j+1]-cable.arc[i])>threshold
    i,j=i[valid],j[valid]
    if not len(i):
        return None
    gap,s,t=closest_segments(cable,cable,i,j)
    steps=np.diff(cable.arc)
    separation=cable.arc[j]+t*steps[j]-(cable.arc[i]+s*steps[i])
    valid=(separation>threshold) & (gap<cable.diameter-.06)
    if not valid.any():
        return None
    k=int(np.argmin(np.where(valid,gap,np.inf)))
    a=cable.start[i[k]]+s[k]*(cable.end[i[k]]-cable.start[i[k]])
    b=cable.start[j[k]]+t[k]*(cable.end[j[k]]-cable.start[j[k]])
    return {'wire':cable.name,'other':cable.name,'point':((a+b)/2).round(2).tolist(),
            'overlap_mm':round(cable.diameter-float(gap[k]),3),
            'arc_separation_mm':round(float(separation[k]),3)}


def jaw_routing(cables, neighbors, motion, yaw=0., pitch=0., jaw=0., scene=None):
    """Fit each loose jaw lead at the measured pose, keeping its cut and terminals fixed."""
    active={c.name:c for c in cables}
    original=active[JAW_DATA]
    refs=[c for c in (*cables,*neighbors) if c.name not in (*JAW_SUPPLY,JAW_DATA)]

    def cost(cable, other):
        if scene is None:
            return 0.
        solids=scene.hits(cable,motion)
        gaps=[hit for ref in other if (hit:=segment_gap(cable,ref))]
        return 20.*len(solids)+sum(4.+10.*hit['overlap_mm'] for hit in gaps)+20.*bool(self_gap(cable))

    best=None
    tail_guides=((91.,-9.,-2.),(90.,-9.,-2.),(87.,-8.,-2.),
                 (89.,-10.,-2.),(92.,-7.,-3.),(88.,-6.,-2.))
    for guide in tail_guides:
        tails=[]
        for name in JAW_SUPPLY:
            wire=active[name]
            points=supply_tail(name,wire.points,motion,wire.length,guide)
            if points is None:
                break
            tails.append(routed_cable(wire,points))
        if len(tails)!=len(JAW_SUPPLY):
            continue
        score=cost(tails[0],refs)+cost(tails[1],[*refs,tails[0]])
        if best is None or score<best[0]:
            best=(score,tails)
        if score==0.:
            break
    if best is None:
        raise ValueError('The jaw supply leads cannot reach the new plug at their cut lengths')
    for wire in best[1]:
        active[wire.name]=wire
        refs.append(wire)

    offsets=((0.,0.,0.),(0.,-1.,0.),(0.,1.,0.),(0.,-1.6,0.),(0.,-2.,0.),
             (0.,2.,0.),(0.,0.,-1.),(0.,0.,1.),(-1.,0.,0.),(1.,0.,0.))
    scores=[]
    for offset in offsets:
        run=routed_cable(original,base_run(motion,offset))
        score=cost(run,refs)+30.*max(JAW_RADIUS-run.radius,0.)
        scores.append((score,run.points))
        if score==0.:
            break
    entry=min(scores,key=lambda row:row[0])[1]

    best=None
    profiles=data_profiles(yaw,pitch)
    centerlines=[]
    for guide in data_guides(yaw,pitch,jaw):
        try:
            centerlines.append(data_centerline(motion,guide,entry))
        except ValueError:
            continue
    for group in (profiles[:10],profiles[10:]):
        for centerline,profile in product(centerlines,group):
            points=data_length(centerline,motion,original.length,profile)
            if points is None:
                continue
            wire=routed_cable(original,points)
            penalty=40.*max(JAW_RADIUS-wire.radius,0.)
            if best is not None and penalty>=best[0]:
                continue
            score=cost(wire,refs)+penalty
            if best is None or score<best[0]:
                best=(score,wire)
            if score==0.:
                break
        if best is not None and best[0]==0.:
            break
    if best is None:
        raise ValueError('The jaw DATA lead cannot reach the plug at its cut length')
    active[JAW_DATA]=best[1]
    return [active[cable.name] for cable in cables]


class Scene:
    def __init__(self, cad, layout, assembly, wiring, hardware):
        self.groups={}
        for part in assembly['parts']:
            name=part['cad_id']
            if name.startswith(('Ballast','HubRearClearance')):
                continue
            model=cad/'world'/f'{name}.stl'
            if model.exists():
                self.add(name,part['motion'],tr.load_mesh(model))
        for row in hardware:
            if not row['id'].startswith('ballast'):
                self.add(row['id'],row['motion'],fastener(row))
        for row in wiring_blocks(wiring):
            shape=tr.creation.box(row['size'])
            shape.apply_translation(row['center'])
            self.add(row['id'],row.get('motion','fixed'),shape)
        for n in range(3,9):
            name=f'HubPlugJ{n}'
            path=cad/'world'/f'{name}.stl'
            if path.exists():
                self.add(name,'hatch',tr.load_mesh(path))

    def add(self,name,mode,shape):
        if mode not in self.groups:
            self.groups[mode]={}
        self.groups[mode][name]=(shape.bounds,fcl.CollisionObject(mesh_to_BVH(shape)))

    def hits(self,cable,motion,clearance=CABLE_CLEARANCE,only=None):
        radius=cable.diameter/2+clearance
        result=[]
        valid=np.diff(cable.arc)>1e-8
        root=cable.name if cable.name in HUB_CONNECTION else cable.name.split('-',1)[0]
        end_parts=HUB_CONNECTION[root]
        request=fcl.CollisionRequest(num_max_contacts=1)
        for mode,solids in self.groups.items():
            transform_=motion.get(mode,motion['head'])
            points=transform(cable.points,np.linalg.inv(transform_))
            low=np.minimum(points[:-1],points[1:])-radius
            high=np.maximum(points[:-1],points[1:])+radius
            for name,(bounds,solid) in solids.items():
                if only is not None and name not in only:
                    continue
                mask=valid & ((high>=bounds[0]) & (low<=bounds[1])).all(axis=1)
                if name in end_parts:
                    # The sheath terminates at the recorded connector or body interface.
                    mask &= (cable.arc[:-1]>=2.6) & (cable.arc[1:]<=cable.arc[-1]-2.6)
                for index in np.flatnonzero(mask):
                    a,b=points[index:index+2]
                    direction=b-a
                    segment_length=np.linalg.norm(direction)
                    direction/=segment_length
                    q=np.array([1+direction[2],-direction[1],direction[0],0.])
                    q_len=np.linalg.norm(q)
                    q=q/q_len if q_len>1e-8 else np.array([0.,1.,0.,0.])
                    capsule=fcl.CollisionObject(fcl.Capsule(radius,segment_length),fcl.Transform(q,(a+b)/2))
                    if fcl.collide(solid,capsule,request,fcl.CollisionResult()):
                        result.append({'wire':cable.name,'part':name,'point':cable.midpoints[index].round(2).tolist()})
                        break
        return result


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def setup(cad, wiring, packed, only_power, preview):
    global _state
    layout=read(cad/'cad_parts.json')
    assembly=read(ROOT/'web/assets/assembly.json')
    wire_data=read(wiring)
    design=read(cad/'cut-lengths.json')
    hardware=read(cad/'hardware.json')
    scene=Scene(cad,layout,assembly,wire_data,hardware)
    _state=(layout,wire_data,design,scene,packed,only_power,preview)


def measure(pose):
    layout,wire_data,design,scene,packed,only_power,preview=_state
    yaw,pitch,eye,drop,jaw=pose
    motion=matrices(layout,yaw,pitch,eye,drop,jaw)
    if only_power:
        cables=power_cables(drop)
    else:
        cables=bundle(wire_data,design,motion,drop,packed=packed,pitch=pitch,eye=eye)
        cables=[routed_cable(c,id5_jaw_clearance(c.points,motion,c.length,yaw,pitch,jaw))
                if c.name=='motor5-power' else c for c in cables]
        cables=jaw_routing(cables,reference_cables(wire_data,motion,cables),motion,yaw,pitch,jaw,scene)
    solids=[]
    for cable in cables:
        within_margin=scene.hits(cable,motion)
        if within_margin:
            nominal={x['part']:x for x in scene.hits(cable,motion,0.,only={h['part'] for h in within_margin})}
            solids.extend(dict(nominal.get(h['part'],h),contact=h['part'] in nominal) for h in within_margin)
    pairs=[hit for a,b in combinations(cables,2) if (hit:=segment_gap(a,b))]
    self_pairs=[hit for c in cables if (hit:=self_gap(c))]
    measurements={c.name:{'length_mm':round(c.length,3),
                          'centerline_error_mm':round(float(c.arc[-1]-c.length),5),
                          'minimum_bend_radius_mm':round(c.radius,3),
                          'bend_target_mm':round(radius_target(c.name,c.diameter),3),
                          'bend_point':c.bend_point} for c in cables}
    frame=dict(pose=pose,paths=[dict(id=c.name,d=c.diameter,points=c.points.round(4).tolist()) for c in cables]) if preview else None
    return dict(pose=pose,lengths=measurements,solids=solids,pairs=pairs,self_pairs=self_pairs), frame


def sweep(cad, wiring, output, quick=False, preview=False, only_power=False, packed=False, workers=1):
    neck=[(y,p,0,0,0) for y,p in product(range(-60,61,5),range(-15,7,3))]
    cover=[(0,0,0,d,0) for d in range(31)]
    open_corners=[(y,p,0,30,0) for y,p in product((-60,60),(-15,6))]
    corners=[(y,p,e,d,j) for y,p,e,d,j in product((-60,60),(-15,6),(-8,8),(0,30),(0,13))]
    if only_power:
        cases=cover
    elif quick:
        cases=[(0,0,0,0,0),(0,0,0,15,0),(0,0,0,30,0),
               *[(y,p,0,0,0) for y,p in product((-60,60),(-15,6))],
               *open_corners,
               (-60,-15,8,30,13),(60,6,-8,30,13)]
    else:
        cases=list(dict.fromkeys(neck+cover+open_corners+corners))
    def collect(samples):
        records,frames=[],[]
        for index,(record,frame) in enumerate(samples):
            records.append(record)
            if frame:
                frames.append(frame)
            if quick or index%20==0 or index==len(cases)-1:
                print(record['pose'],f"{len(record['solids'])} solid contacts, {len(record['pairs'])} wire pairs, "
                      f"{len(record['self_pairs'])} self contacts",flush=True)
        return records,frames

    args=(cad,wiring,packed,only_power,preview or quick)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers,initializer=setup,initargs=args) as pool:
            records,frames=collect(pool.map(measure,cases,chunksize=2))
    else:
        setup(*args)
        records,frames=collect(map(measure,cases))
    output.mkdir(parents=True,exist_ok=True)
    layout=read(cad/'cad_parts.json')
    report={'cad_sha256':layout['source_sha256'],'solid_clearance_mm':CABLE_CLEARANCE,'records':records}
    (output/'wiring-check.json').write_text(json.dumps(report,separators=(',',':'))+'\n',encoding='utf-8')
    if frames:
        (output/'wiring-frames.json').write_text(json.dumps(frames,separators=(',',':'))+'\n',encoding='utf-8')


if __name__=='__main__':
    p=ArgumentParser(description=__doc__)
    p.add_argument('cad',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--wiring',type=Path,default=ROOT/'web/assets/wiring.json')
    p.add_argument('--quick',action='store_true')
    p.add_argument('--preview',action='store_true')
    p.add_argument('--only-power',action='store_true')
    p.add_argument('--packed',action='store_true')
    p.add_argument('--workers',type=int,default=1)
    sweep(**vars(p.parse_args()))
