"""MuJoCo screening of the loaded neck/jaw and both lids."""
from argparse import ArgumentParser
from dataclasses import dataclass
from itertools import product
from math import radians
from pathlib import Path
import json
import xml.etree.ElementTree as ET

import mujoco as mj
import numpy as np
import trimesh

from blink import run_blink

DT = .001
NECK_PIVOT = np.array([0., 0., .112])
YAW_PIVOT = np.array([0., 0., -.0379])
OPTIONAL_BALLAST = {'BallastTray', 'BallastCover', 'BallastLeftStud', 'BallastRightStud'}
PRINT_NAMES = {
    'Part042': 'xl330_m077_eye_pitch_front_plate',
    'Jaw_30_moving_jaw': '30_moving_jaw',
    'Jaw_38_left_jaw_drive_arm': '38_left_jaw_drive_arm',
    'Jaw_39_right_jaw_pivot_arm': '39_right_jaw_pivot_arm',
}


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


def cad_part_mass(row, directory, sliced_g):
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
        print_name = PRINT_NAMES.get(row['name'], row['label'].lower().replace(' ', '_'))
        m = sliced_g[print_name] / 1000.
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
    root = model_root('R5 loaded yaw pitch and jaw', dt)
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


def motion_trace(t, fast_pitch=False):
    if t<3.5:
        q,v,a = quintic(t,3.0,np.zeros(2),np.radians([55.,-14.]))
    else:
        q,v,a = quintic(t-3.5,5.8,np.radians([55.,-14.]),np.radians([-55.,5.]))
    if fast_pitch:
        if t < 2.8:
            pitch = quintic(t, 1.6, 0., radians(-15.))
        elif t < 6.1:
            pitch = quintic(t-2.8, 1.66, radians(-15.), radians(6.))
        else:
            pitch = quintic(t-6.1, .8, radians(6.), 0.)
        q[1], v[1], a[1] = pitch
    jaw_q = jaw_v = jaw_a = 0.
    for start,peak in ((2.75,10.),(3.21,13.),(7.05,12.)):
        local=t-start
        if 0 <= local < .44:
            if local < .20:
                jaw_q,jaw_v,jaw_a = quintic(local,.20,0.,radians(peak))
            else:
                jaw_q,jaw_v,jaw_a = quintic(local-.20,.24,radians(peak),0.)
    return np.r_[q,jaw_q],np.r_[v,jaw_v],np.r_[a,jaw_a]


def dynamic_trial(xml, budget, friction, backlash_deg, fast_pitch=False):
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
        goal,velocity,accel=motion_trace(t, fast_pitch)
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


def ballast_mass(layout, plates):
    size = pos(layout['plate_mm'])
    size[2] *= plates
    mass = plates * layout['plate_mass_kg']
    center = np.array([0., layout['center_y_mm']*.001, layout['floor_z_mm']*.001+size[2]/2])
    inertia = np.diag(mass/12*(np.sum(size**2)-size**2))
    return Mass(mass, center, inertia)


def worst_gravity(assembly, ballast, angles):
    moment = assembly.mass*(assembly.center-NECK_PIVOT) + ballast.mass*(ballast.center-NECK_PIVOT)
    torque = 9.81*(moment[1]*np.cos(angles)-moment[2]*np.sin(angles))
    return float(np.max(np.abs(torque)))


def balance_trials(layout, masses, ballast_kit, hinge, output):
    pitch_range = np.radians(np.linspace(-15, 6, 211))
    budget, friction = np.array([.28,.20,.050]), np.array([.045,.042,.012])
    nominal = combine(masses[1:])
    groups = {
        'cad': (nominal.mass, nominal.center-NECK_PIVOT),
        'forward': (.75, np.array([0., -.030, .026])),
    }
    reports = {}
    for name, (mass, center) in groups.items():
        loads = [(mass, center)]
        loads.extend((mass+dm, center+np.array([0.,dy,dz]))
                     for dm,dy,dz in product((-.025,.025),(-.003,.003),(-.006,.006)))
        assemblies = [shifted_mass(nominal, NECK_PIVOT, m, c) for m,c in loads]
        settings = range(layout['maximum_plates']+1)
        weights = [combine([ballast_kit,ballast_mass(layout,n)]) if n else ballast_mass(layout,0)
                   for n in settings]
        options = [max(worst_gravity(body, weight, pitch_range) for body in assemblies) for weight in weights]
        selected = 0 if options[0] <= .105 else int(np.argmin(options))
        weight = weights[selected]
        results = []
        for i, assembly in enumerate(assemblies):
            head_mass = assembly.mass-masses[2].mass
            head_center = (assembly.mass*assembly.center-masses[2].mass*masses[2].center)/head_mass
            shifted = shifted_mass(masses[1], NECK_PIVOT, head_mass, head_center-NECK_PIVOT)
            balanced = [masses[0], combine([shifted, weight]), masses[2]]
            xml = gimbal_model(balanced, hinge, budget, friction, DT)
            result = dynamic_trial(xml, budget, friction, .75, fast_pitch=True)
            results.append(result)
            if i == 0:
                (output/f'balanced_{name}.xml').write_text(xml)
        peak = max(row['torque_demand_bound_Nm'][1] for row in results)
        error = max(row['max_error_deg'][1] for row in results)
        print(f'Ballast {name}: {selected} plates, {len(results)} load cases, {peak:.3f} N·m peak, '
              f'{error:.2f}° maximum pitch error', flush=True)
        reports[name] = {'plate_count': selected, 'ballast_with_mount_kg': weight.mass,
                         'worst_gravity_Nm': options[selected], 'worst_unbalanced_gravity_Nm': options[0],
                         'max_pitch_demand_Nm': peak, 'max_pitch_error_deg': error, 'trials': results}
    return reports


def run_gimbal(cad_data, input_dir, output, sliced_g):
    bins = {'yaw':[], 'head':[], 'jaw':[], 'optional':[]}
    records = cad_data['parts']
    for row in records:
        if row['name'] == 'BallastStack':
            continue
        group = 'optional' if row['name'] in OPTIONAL_BALLAST else {'pan':'yaw','jaw':'jaw'}.get(row['motion'],'head')
        bins[group].append(cad_part_mass(row,input_dir,sliced_g))
    # Fasteners and harness are distributed over the frame and descend through the pitch yoke.
    head_allowance = .040
    yaw_allowance = .012
    bins['head'].append(Mass(head_allowance,pos((0.,8.,129.)),head_allowance*np.diag((.001,.001,.0015))))
    bins['yaw'].append(Mass(yaw_allowance,pos((0.,5.,70.)),yaw_allowance*np.diag((.001,.001,.0015))))
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
    layout = cad_data['motion_geometry'].get('ballast')
    balanced = balance_trials(layout, masses, combine(bins['optional']), pivot, output)
    pitching = combine(masses[1:])
    turning = combine(masses)
    total = {'pitch_mass_kg': pitching.mass, 'yaw_mass_kg': turning.mass,
             'pitch_com_from_axis_mm': ((pitching.center-NECK_PIVOT)*1000).tolist(),
             'yaw_com_from_axis_mm': ((turning.center-YAW_PIVOT)*1000).tolist(),
             'pitch_hardware_allowance_g':head_allowance*1000, 'yaw_hardware_allowance_g':yaw_allowance*1000}
    return {'mass_properties':summary,'joint_order':['neck yaw','neck pitch','jaw'],
            'trials':runs,'balanced':balanced,'assembled':total}


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('cad',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--sliced-grams',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    cad=json.loads((args.cad/'cad_parts.json').read_text())
    gimbal=run_gimbal(cad,args.cad,args.output,json.loads(args.sliced_grams.read_text()))
    blink=run_blink(cad['motion_geometry']['blink'],args.output/'blink')
    (args.output/'motion_results.json').write_text(json.dumps({'source_sha256':cad['source_sha256'],
        'mujoco_version':mj.__version__,'gimbal':gimbal,'blink':blink},indent=2))
