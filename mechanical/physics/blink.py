"""Torque-limited MuJoCo model of the drive, shaft and both pin-linked lids."""
from math import atan2, cos, degrees, hypot, pi, radians, sin
import xml.etree.ElementTree as ET

import mujoco as mj
import numpy as np

MM=.001


def vector(values):
    return ' '.join(f'{v:.9g}' for v in values)


def build(layout, cap, extra_drag, dt):
    rad=radians(layout['phase_deg'])
    radius=.001*layout['radius_mm']
    shaft_yz=np.array(layout['shaft_yz_mm'])*MM
    servo_yz=np.array(layout['servo_yz_mm'])*MM
    eye_yz=np.array([-39.,119.])*MM
    drive_arm=np.array([radius*cos(rad),radius*sin(rad)])
    lid_arm=drive_arm*(layout['lid_radius_mm']/layout['radius_mm'])
    side=layout['link_x_mm']*MM
    center=.00585
    root=ET.Element('mujoco',model='R5 closed loop blink')
    ET.SubElement(root,'compiler',angle='radian',inertiafromgeom='false')
    ET.SubElement(root,'option',timestep=str(dt),gravity='0 0 -9.81',integrator='implicit',iterations='70')
    world=ET.SubElement(root,'worldbody')
    equal=ET.SubElement(root,'equality')
    for name, xyz, half in layout['obstacles']:
        ET.SubElement(world,'geom',name=name,type='box',pos=vector(np.array(xyz)*MM),size=vector(np.array(half)*MM),
                      contype='2',conaffinity='1',solref='.0012 1')

    def body(parent, name, pos, mass, inertia, drag, damping, center=(0,0,0)):
        b=ET.SubElement(parent,'body',name=name,pos=vector(pos))
        ET.SubElement(b,'inertial',pos=vector(center),mass=str(mass),diaginertia=vector(inertia))
        ET.SubElement(b,'joint',name=name,type='hinge',axis='1 0 0',damping=str(damping),frictionloss=str(drag))
        return b

    def site(parent,name,x,yz):
        ET.SubElement(parent,'site',name=name,pos=vector((x,*yz)),size='.001')

    def rod(parent,name,x,start,end,mass,arm):
        delta=end-start
        length=np.linalg.norm(delta)
        inertia=mass*(length**2+(.0057)**2)/12
        rod=body(parent,name,(x,*arm),mass,(inertia, inertia,.25*inertia),0,.00002,(0,*(.5*delta)))
        site(rod,name+'_tip',0,delta)
        ET.SubElement(rod,'geom',name=name+'_contact',type='capsule',fromto=vector((0,0,0,0,*delta)),
                      size='.00285',contype='1',conaffinity='2',solref='.0012 1')
        return rod

    motor=body(world,'motor',(0,*servo_yz),.004,(.0000003,.00000035,.00000035),.001*extra_drag,.00025)
    shaft=body(world,'shaft',(0,*shaft_yz),.016,(.0000006,.000023,.000023),.002*extra_drag,.0003)
    site(shaft,'shaft_center',center,drive_arm)
    rod(motor,'drive_rod',center,servo_yz,shaft_yz,.00085,drive_arm)
    ET.SubElement(equal,'connect',site1='drive_rod_tip',site2='shaft_center',solref='.0014 1')
    for name,x in [('left',-side),('right',side)]:
        lid=body(world,name+'_lid',(x,*eye_yz),.0033,(.00000043,.0000006,.00000062),.003*extra_drag,.00035,(0,-.005,.007))
        site(lid,name+'_eye_pin',0,lid_arm)
        rod(shaft,name+'_rod',x,shaft_yz,eye_yz,.001,lid_arm)
        ET.SubElement(equal,'connect',site1=name+'_rod_tip',site2=name+'_eye_pin',solref='.0014 1')
    motor_actuator=ET.SubElement(root,'actuator')
    ET.SubElement(motor_actuator,'motor',name='blink',joint='motor',ctrlrange=vector((-cap,cap)),ctrllimited='true')
    ET.indent(root)
    return ET.tostring(root,encoding='unicode')


def requested(t,stroke):
    end=2*stroke+.24
    t=t%end
    if t < stroke:
        f=t/stroke
        return .5*pi*f*f*(3-2*f),3*pi*f*(1-f)/stroke
    if t<stroke+.12:
        return .5*pi,0.
    if t<2*stroke+.12:
        f=(t-stroke-.12)/stroke
        return .5*pi*(1-f*f*(3-2*f)),-3*pi*f*(1-f)/stroke
    return 0.,0.


def run(xml, cap, stroke, cycles=20):
    model=mj.MjModel.from_xml_string(xml)
    data=mj.MjData(model)
    indexes=[model.joint(n).qposadr[0] for n in ('motor','shaft','left_lid','right_lid')]
    sites=[(model.site(a).id,model.site(b).id) for a,b in (('drive_rod_tip','shaft_center'),
                ('left_rod_tip','left_eye_pin'),('right_rod_tip','right_eye_pin'))]
    dt=model.opt.timestep
    length=2*stroke+.24
    closed=[[] for _ in range(cycles)]
    opened=[[] for _ in range(cycles)]
    max_joint_error=0.
    max_close_force=0.
    max_error=0.
    max_torque=0.
    contact_count=0
    for i in range(round(cycles*length/dt)):
        t=i*dt
        target, speed=requested(t,stroke)
        now=data.qpos[indexes]
        requested_torque=.85*(target-now[0])+.018*(speed-data.qvel[indexes[0]])
        data.ctrl[0]=np.clip(requested_torque,-cap,cap)
        mj.mj_step(model,data)
        phase=t%length
        current=min(int(t//length),cycles-1)
        if stroke+.07 < phase < stroke+.12:
            closed[current].append(float(np.min(np.degrees(now[2:]))))
        if length-.045 < phase < length:
            opened[current].append(float(np.max(np.abs(np.degrees(now[2:])))))
        max_error=max(max_error,float(np.max(abs(target-now[2:]))))
        max_joint_error=max(max_joint_error,max(float(np.linalg.norm(data.site_xpos[a]-data.site_xpos[b])) for a,b in sites))
        max_torque=max(max_torque,float(abs(data.ctrl[0])))
        contact_count+=data.ncon
        for j in range(data.ncon):
            force=np.zeros(6)
            mj.mj_contactForce(model,data,j,force)
            max_close_force=max(max_close_force,force[0])
    return {'cycles':cycles,'stroke_seconds':stroke,'torque_cap_Nm':cap,'min_closed_deg':min(max(a) for a in closed),
            'max_return_error_deg':max(min(a) for a in opened),'max_tracking_error_deg':degrees(max_error),
            'max_loop_gap_mm':max_joint_error*1000,'max_drive_torque_Nm':max_torque,
            'contact_count':contact_count,'max_contact_force_N':max_close_force}


def run_blink(layout, out):
    out.mkdir(parents=True, exist_ok=True)
    report={}
    for name, cap, drag, step in [('nominal',.12,1.,.00025),('higher_drag',.085,2.0,.00025),('half_step',.12,1.,.000125)]:
        xml=build(layout,cap,drag,step)
        stats=run(xml,cap,.68)
        report[name]=stats
        (out/f'{name}.xml').write_text(xml)
        print(name,stats,flush=True)
    if any(r['min_closed_deg']<87.5 or r['max_return_error_deg']>2.5 or r['max_loop_gap_mm']>.2 or r['contact_count'] for r in report.values()):
        raise RuntimeError('Blink did not meet travel, contact or pin-closure criteria')

    dy, dz = np.asarray(layout['shaft_yz_mm']) - np.array([-39., 119.])
    rod_direction = atan2(dz, dy)
    start = radians(layout['phase_deg'])
    end = start + pi/2
    start_lever = sin(rod_direction-start)
    end_lever = sin(rod_direction-end)
    if start_lever*end_lever <= 0:
        raise RuntimeError('Lid crank passes through dead centre')
    lever_mm = layout['lid_radius_mm'] * min(abs(start_lever), abs(end_lever))
    stalled_load = .12 / (lever_mm * MM)
    weak_axis_mm4 = 5.7 * 2.6**3 / 12
    buckling_load = pi**2 * 1450 * weak_axis_mm4 / hypot(dy, dz)**2
    load_screen = {'minimum_lever_mm': lever_mm, 'single_link_stalled_load_N': stalled_load,
                   'pinned_link_buckling_N': buckling_load, 'assumed_modulus_MPa': 1450}
    if stalled_load >= buckling_load:
        raise RuntimeError('Estimated lid link buckling under the modelled stall load')
    print('Lid link load estimate', load_screen, flush=True)
    return {'trials': report, 'load_screen': load_screen}
