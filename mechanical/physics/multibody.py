"""MuJoCo screening of the loaded B2 neck/jaw and the right blink linkage."""
from argparse import ArgumentParser
from dataclasses import dataclass
from math import atan2, cos, hypot, pi, radians, sin
from pathlib import Path
import json
import xml.etree.ElementTree as ET

import mujoco as mj
import numpy as np
import trimesh

DT = .001
CONTACT_DT = .0005
NECK_PIVOT = np.array([0., 0., .112])
YAW_PIVOT = np.array([0., 0., -.0379])


def fmt(items):
    return ' '.join(f'{x:.10g}' for x in items)


def pos(array):
    return np.asarray(array, dtype=float) * .001


def parallel_axis(offset):
    return (offset @ offset) * np.eye(3) - np.outer(offset, offset)


@dataclass
class Mass:
    mass: float
    center: np.ndarray
    inertia: np.ndarray


def combine(items):
    total = sum(p.mass for p in items)
    center = sum(p.mass*p.center for p in items) / total
    inertia = sum(p.inertia + p.mass*parallel_axis(p.center-center) for p in items)
    return Mass(total, center, inertia)


def cad_part_mass(row, directory, fraction):
    if row.get('solids'):
        solids = row['solids']
        volume = sum(s['volume'] for s in solids)
        centers = [pos(s['center']) for s in solids]
        inertia = [np.array(s['inertia'])*1e-6/s['volume'] for s in solids]
        weights = np.array([s['volume'] for s in solids]) / volume
    else:
        mesh = trimesh.load_mesh(directory/row['mesh'])
        if mesh.volume < 0:
            mesh.invert()
        if mesh.volume <= 0 or abs(mesh.volume/row['mesh_volume_mm3']-1) > .015:
            raise ValueError(f"Invalid mass properties on {row['name']}")
        volume = mesh.volume
        centers = [pos(mesh.center_mass)]
        inertia = [mesh.moment_inertia*1e-6/volume]
        weights = np.ones(1)
    if row['printed']:
        shell = row['name'] in {'Part073','Part074','Jaw_30_moving_jaw','Part076','Part077','Part078','Part079'}
        effective_fraction = .92 if shell else fraction
        m = volume * 1.27e-6 * effective_fraction
    else:
        name = row['label']
        nominal_g = 57.2 if name.startswith('XL430') else 18. if name.startswith('XL330') else row['reference_g']
        m = nominal_g*.001 if nominal_g > .01 else volume*7.8e-6
    return combine([Mass(m*w, c, m*w*i) for w,c,i in zip(weights,centers,inertia)])


def inertial(node, values, pivot):
    tensor = values.inertia
    diagonal = np.linalg.eigvalsh(tensor)
    if diagonal[0] <= 0 or diagonal[0]+diagonal[1] <= diagonal[2]:
        raise ValueError(f'Invalid inertia on {node.get("name")}: {diagonal}')
    ET.SubElement(node, 'inertial', pos=fmt(values.center-pivot), mass=f'{values.mass:.10g}',
                  fullinertia=fmt([tensor[0,0],tensor[1,1],tensor[2,2],tensor[0,1],tensor[0,2],tensor[1,2]]))


def model_root(name, step=DT):
    root = ET.Element('mujoco', model=name)
    ET.SubElement(root,'compiler',angle='radian',inertiafromgeom='false',autolimits='true')
    ET.SubElement(root,'option',timestep=str(step), gravity='0 0 -9.81',integrator='implicitfast',
                  solver='Newton',iterations='80',tolerance='1e-10',cone='elliptic',noslip_iterations='12')
    return root


def gimbal_model(masses, pivot, budget, friction, dt):
    root = model_root('R5 B2 loaded yaw pitch and jaw', dt)
    world = ET.SubElement(root,'worldbody')
    parent = world
    previous = np.zeros(3)
    names = ('neck_yaw','neck_pitch','jaw')
    limits = ((-60,60),(-15,6),(0,14))
    pivots = (YAW_PIVOT,NECK_PIVOT,pivot)
    for k,(name,center,norm,angles) in enumerate(zip(names,pivots,('0 0 1','1 0 0','1 0 0'),limits)):
        parent = ET.SubElement(parent,'body',name=name,pos=fmt(center-previous))
        inertial(parent,masses[k],center)
        ET.SubElement(parent,'joint',name=name,type='hinge',axis=norm,range=fmt(np.radians(angles)),
                      damping=f'{(0.012,0.009,0.0011)[k]}',frictionloss=str(friction[k]),solreflimit='.006 1')
        previous = center
    drives = ET.SubElement(root,'actuator')
    for name,limit in zip(names,budget):
        ET.SubElement(drives,'motor',name=name+'_motor',joint=name,ctrlrange=fmt((-limit,limit)))
    ET.indent(root)
    return ET.tostring(root, encoding='unicode')


def quintic(t, duration, start, goal):
    x = np.clip(t/duration, 0, 1)
    q = start + (goal-start)*(10*x**3-15*x**4+6*x**5)
    v = (goal-start)/duration*(30*x**2-60*x**3+30*x**4)
    a = (goal-start)/duration**2*(60*x-180*x**2+120*x**3)
    return q,v,a


def motion_trace(t):
    if t<3.5:
        q,v,a = quintic(t,3.0,np.zeros(2),np.radians([55.,-14.]))
    else:
        q,v,a = quintic(t-3.5,5.8,np.radians([55.,-14.]),np.radians([-55.,5.]))
    jaw_q = jaw_v = jaw_a = 0.
    for start,peak in ((2.75,10.),(3.21,13.),(7.05,12.)):
        local=t-start
        if 0 <= local < .44:
            if local < .20:
                jaw_q,jaw_v,jaw_a = quintic(local,.20,0.,radians(peak))
            else:
                jaw_q,jaw_v,jaw_a = quintic(local-.20,.24,radians(peak),0.)
    return np.r_[q,jaw_q],np.r_[v,jaw_v],np.r_[a,jaw_a]


def dynamic_trial(xml, budget, friction, backlash_deg):
    model = mj.MjModel.from_xml_string(xml)
    actual = mj.MjData(model)
    reference = mj.MjData(model)
    no_friction = np.array(model.dof_frictionloss)
    errors=[]
    peaks=np.zeros(3)
    saturation=np.zeros(3, int)
    speed=np.zeros(3)
    step=model.opt.timestep
    for i in range(round(10.2/step)):
        t=i*step
        goal,velocity,accel=motion_trace(t)
        reference.qpos[:] = goal
        reference.qvel[:] = velocity
        reference.qacc[:] = accel
        model.dof_frictionloss[:] = 0
        mj.mj_inverse(model,reference)
        model.dof_frictionloss[:] = no_friction
        demand = np.abs(reference.qfrc_inverse) + friction
        peaks=np.maximum(peaks,demand)
        speed=np.maximum(speed,abs(velocity))
        error=goal-actual.qpos
        gap=radians(backlash_deg)/2
        effective=np.sign(error)*np.maximum(np.abs(error)-gap,0)
        correction=np.array([3.8,4.0,.85])*effective + np.array([.33,.29,.018])*(velocity-actual.qvel)
        requested=reference.qfrc_inverse + correction
        saturation+=abs(requested)>budget
        actual.ctrl[:]=np.clip(requested,-np.asarray(budget),budget)
        mj.mj_step(model,actual)
        errors.append(np.degrees(abs(goal-actual.qpos)))
    errors=np.array(errors)
    assert np.isfinite(errors).all()
    return {'torque_demand_bound_Nm':peaks.tolist(), 'max_error_deg':np.max(errors,axis=0).tolist(),
            'error_p95_deg':np.percentile(errors,95,axis=0).tolist(),
            'saturated_percent':(100*saturation/len(errors)).tolist(),
            'command_max_speed_deg_s':np.degrees(speed).tolist()}


def shifted_mass(part, pivot, new_mass, offset):
    return Mass(new_mass, pivot+np.array(offset),part.inertia*new_mass/part.mass)


def run_gimbal(cad_data, input_dir, output):
    bins = {'yaw':[], 'head':[], 'jaw':[]}
    records = cad_data['parts']
    for row in records:
        group = {'pan':'yaw','jaw':'jaw'}.get(row['motion'],'head')
        bins[group].append(cad_part_mass(row,input_dir,.72))
    masses=[combine(bins[k]) for k in ('yaw','head','jaw')]
    pivot=pos(cad_data['jaw_pivot_mm'])
    center=NECK_PIVOT+np.array([0,-.030,.026])
    weighted_head_mass=.75-masses[2].mass
    weighted_head_center=(.75*center-masses[2].mass*masses[2].center)/weighted_head_mass
    heavy=[masses[0], shifted_mass(masses[1],NECK_PIVOT,weighted_head_mass,weighted_head_center-NECK_PIVOT), masses[2]]
    scenarios=[
        ('cad_mid', masses, [.40,.30,.070], [.022,.020,.005], .35),
        ('cad_low_torque', masses, [.28,.20,.040], [.045,.042,.012], .75),
        ('forward_heavy', heavy, [.40,.30,.070], [.032,.032,.009], .6),
        ('forward_heavy_low_torque', heavy, [.28,.20,.040], [.045,.042,.012], .75),
    ]
    runs={}
    for name,bodies,budget,drag,backlash in scenarios:
        xml=gimbal_model(bodies,pivot,budget,drag,DT)
        if name in ('cad_mid','forward_heavy_low_torque'):
            (output/f'{name}.xml').write_text(xml)
        result=dynamic_trial(xml,np.array(budget),np.array(drag),backlash)
        result.update({'torque_cap_Nm':budget,'coulomb_friction_Nm':drag,'backlash_deg':backlash,
                       'head_plus_jaw_mass_kg':bodies[1].mass+bodies[2].mass})
        runs[name]=result
        print(name, np.round(result['torque_demand_bound_Nm'],3), np.round(result['max_error_deg'],2),flush=True)
    summary={name:{'mass_kg':part.mass,'com_mm':(part.center*1000).tolist(),
                   'inertia_kg_m2':part.inertia.tolist()}
             for name,part in zip(('yaw_carrier','head','jaw'),masses)}
    return {'mass_properties':summary,'joint_order':['neck yaw','neck pitch','jaw'],'trials':runs}


LINK_PATH = [(-30.75,119.),(-25.2,112.7),(-18.8,112.7),(-10.5,123.5),
             (17.8,123.5),(25.7,104.5),(33.25,101.)]


def mesh_assets(directory, output):
    assets=[]
    for path in sorted(directory.glob('blink_motor_*.stl')):
        solid=trimesh.load_mesh(path).convex_hull
        name=path.stem
        obj=''.join(f'v {fmt(v)}\n' for v in solid.vertices*.001)
        obj+=''.join(f'f {a+1} {b+1} {c+1}\n' for a,b,c in solid.faces)
        stored=output/f'{name}.obj'
        stored.write_text(obj)
        assets.append(stored)
    if not assets:
        raise RuntimeError('No pitch motor collision mesh')
    return assets


def blink_model(meshes, collide, torque_cap, offset=0., step=DT):
    root=model_root('B2 right blink link under pitch motor',step)
    world=ET.SubElement(root,'worldbody')
    asset=ET.SubElement(root,'asset')
    for path in meshes:
        ET.SubElement(asset,'mesh',name=path.stem,file=path.name)
        ET.SubElement(world,'geom',name=path.stem+'_case',type='mesh',mesh=path.stem,
                      pos=fmt((0,0,-offset)),contype='2' if collide else '0',conaffinity='1' if collide else '0',
                      solref='.0012 1',solimp='.985 .999 .00025')
    shaft=ET.SubElement(world,'body',name='shaft',pos='0 .025 .101')
    ET.SubElement(shaft,'inertial',pos='0 0 0',mass='.009',diaginertia='2e-7 2e-6 2e-6')
    ET.SubElement(shaft,'joint',name='shaft_joint',type='hinge',axis='1 0 0',range=fmt((-.03,pi/2+.03)),
                  damping='.004',frictionloss='.004')
    link=ET.SubElement(shaft,'body',name='right_link',pos='.0473 .00825 0')
    ET.SubElement(link,'inertial',pos='0 -.032 .015',mass='.002',diaginertia='1.2e-6 2.7e-7 1.15e-6')
    ET.SubElement(link,'joint',name='shaft_pin',type='hinge',axis='1 0 0',damping='.0002')
    ET.SubElement(link,'site',name='link_eye_pin',pos='0 -.064 .018',size='.001')
    mask={'contype':'1','conaffinity':'2','solref':'.0012 1','solimp':'.985 .999 .00025','friction':'.38 .005 .0001'}
    local=[((y-33.25)*.001,(z-101)*.001) for y,z in LINK_PATH]
    for i,(y,z) in enumerate(local):
        ET.SubElement(link,'geom',name=f'joint_round_{i}',type='cylinder',pos=fmt((0,y,z)),
                      quat='.7071067812 0 .7071067812 0',size='.00285 .0013',**mask)
    for i,((y,z),(t,w)) in enumerate(zip(local,local[1:])):
        angle=atan2(w-z,t-y)
        ET.SubElement(link,'geom',name=f'link_web_{i}',type='box',pos=fmt((0,(y+t)/2,(z+w)/2)),
                      quat=fmt((cos(angle/2),sin(angle/2),0,0)),size=fmt((.0013,hypot(t-y,w-z)/2,.00285)),**mask)
    lid=ET.SubElement(world,'body',name='lid',pos='.0473 -.039 .119')
    ET.SubElement(lid,'inertial',pos='0 -.008 .003',mass='.006',diaginertia='2e-6 1.6e-6 1.2e-6')
    ET.SubElement(lid,'joint',name='lid_joint',type='hinge',axis='1 0 0',damping='.001',frictionloss='.002')
    ET.SubElement(lid,'site',name='lid_pin',pos='0 .00825 0',size='.001')
    equals=ET.SubElement(root,'equality')
    ET.SubElement(equals,'connect',site1='link_eye_pin',site2='lid_pin',solref='.0012 1',solimp='.99 .999 .00025')
    actuator=ET.SubElement(root,'actuator')
    ET.SubElement(actuator,'motor',name='blink',joint='shaft_joint',ctrlrange=fmt((-torque_cap,torque_cap)))
    ET.indent(root)
    return ET.tostring(root, encoding='unicode')


def contact_onset(model):
    data=mj.MjData(model)
    for deg in np.arange(0,90.01,.25):
        angle=radians(deg)
        data.qpos[:]=[angle,-angle,angle]
        mj.mj_forward(model,data)
        if any(contact.dist < -0.00001 for contact in data.contact):
            return float(deg)
    return None


def blink_trial(xml, meshes, cap):
    model=mj.MjModel.from_xml_string(xml,assets={p.name:p.read_bytes() for p in meshes})
    data=mj.MjData(model)
    i_shaft=model.joint('shaft_joint').qposadr[0]
    i_lid=model.joint('lid_joint').qposadr[0]
    i_link=model.site('link_eye_pin').id
    i_eye=model.site('lid_pin').id
    max_force=0.
    max_pin_error=0.
    min_dist=0.
    contact_at=None
    trace=[]
    time_step=model.opt.timestep
    for i in range(round(2.4/time_step)):
        time=i*time_step
        desired,velocity,_=quintic(time,1.15,0.,pi/2)
        move=.7*(desired-data.qpos[i_shaft])+.023*(velocity-data.qvel[i_shaft])
        data.ctrl[0]=np.clip(move,-cap,cap)
        mj.mj_step(model,data)
        max_pin_error=max(max_pin_error,np.linalg.norm(data.site_xpos[i_link]-data.site_xpos[i_eye]))
        normal=0.
        for c,contact in enumerate(data.contact):
            result=np.zeros(6)
            mj.mj_contactForce(model,data,c,result)
            normal+=result[0]
            min_dist=min(contact.dist,min_dist)
        max_force=max(max_force,normal)
        if normal>.08 and contact_at is None:
            contact_at=float(np.degrees(data.qpos[i_shaft]))
        if i%20==0:
            trace.append([time,float(np.degrees(desired)),float(np.degrees(data.qpos[i_lid])),normal])
    result={'kinematic_contact_onset_deg':contact_onset(model),'dynamic_contact_onset_deg':contact_at,
            'final_shaft_deg':float(np.degrees(data.qpos[i_shaft])), 'final_lid_deg':float(np.degrees(data.qpos[i_lid])),
            'max_cumulative_normal_N':max_force,'max_solver_penetration_mm':-1000*min_dist,
            'max_loop_closure_error_mm':max_pin_error*1000}
    return result,trace


def run_blink(input_dir,output):
    assets=mesh_assets(input_dir,output)
    exact=json.loads((input_dir/'blink_cad_contact.json').read_text())
    first={str(offset):next((v['angle_deg'] for v in exact if v['vertical_offset_mm']==offset and v['overlap_mm3']>.01),None)
           for offset in (-.4,0.,.4)}
    runs={}
    for name,case,cap,offset,step in [('no_contact_control',False,.10,0,CONTACT_DT),('b2',True,.10,0,CONTACT_DT),
                                     ('lower_torque',True,.065,0,CONTACT_DT),('raised_link',True,.10,.0004,CONTACT_DT),
                                     ('lowered_link',True,.10,-.0004,CONTACT_DT),('half_step',True,.10,0,CONTACT_DT/2)]:
        xml=blink_model(assets,case,cap,offset,step)
        result,raw=blink_trial(xml,assets,cap)
        result['torque_cap_Nm']=cap
        result['offset_mm']=offset*1000
        if name in ('b2','no_contact_control'):
            (output/f'blink_{name}.xml').write_text(xml)
            (output/f'blink_{name}_trace.json').write_text(json.dumps(raw))
        runs[name]=result
        print('blink',name,round(result['final_shaft_deg'],2),result['kinematic_contact_onset_deg'],flush=True)
    assert runs['no_contact_control']['final_lid_deg']>88
    assert runs['b2']['final_lid_deg']<60 and runs['b2']['kinematic_contact_onset_deg'] is not None
    assert abs(runs['b2']['final_shaft_deg']-runs['half_step']['final_shaft_deg'])<.2
    assert abs(runs['b2']['kinematic_contact_onset_deg']-first['0.0'])<2
    return {'trials':runs,'BRep_first_sample_deg':first,'BRep_overlap_samples':exact}


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('cad',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    cad=json.loads((args.cad/'cad_parts.json').read_text())
    gimbal=run_gimbal(cad,args.cad,args.output)
    blink=run_blink(args.cad,args.output)
    (args.output/'motion_results.json').write_text(json.dumps({'source_sha256':cad['source_sha256'],
        'mujoco_version':mj.__version__,'gimbal':gimbal,'blink':blink},indent=2))
