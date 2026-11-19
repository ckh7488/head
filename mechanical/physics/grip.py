"""MuJoCo Coulomb contact sensitivity for the B2 two-band cable restraint.

The pad faces stand for the upper strap and lower liner at each CAD strap
station. The jacket has flattened contact faces. Clamp force and friction
are prescribed because they need measurement.
"""
from argparse import ArgumentParser
from itertools import product
from math import cos, radians, sin
from pathlib import Path
import json

import mujoco as mj
import numpy as np

RADIUS=.00275
WIDTH=.0048
SPACING=.0123
TARGET_N=10.
SLIP_LIMIT_MM=.5


def grip_model(liner_mu,strap_mu,dt):
    geoms=[]
    pairs=[]
    for i,y in enumerate((-SPACING/2, SPACING/2),start=1):
        geoms.append(f'''<geom name="liner_{i}" type="box" size=".006 {WIDTH/2} .0015" pos="0 {y} -.0015"/>
        <body name="strap_{i}" pos="0 {y} {2*RADIUS+.0015}">
          <inertial mass=".10" pos="0 0 0" diaginertia="3e-6 3e-6 3e-6"/>
          <joint type="slide" axis="0 0 1" damping="4.0"/>
          <geom name="top_{i}" type="box" size=".006 {WIDTH/2} .0015"/>
        </body>''')
        for geom, friction in [(f'liner_{i}',liner_mu),(f'top_{i}',strap_mu)]:
            pairs.append(f'<pair geom1="{geom}" geom2="jacket" condim="3" margin=".00003" friction="{friction} {friction} .001 .0001 .0001" solref=".008 1" solimp=".97 .999 .0003"/>')
    return f'''<mujoco model="B2 cable grip sensitivity">
      <compiler angle="radian" inertiafromgeom="false"/>
      <option timestep="{dt}" gravity="0 0 0" integrator="implicitfast" cone="elliptic" solver="Newton" tolerance="1e-9" iterations="70" noslip_iterations="40"/>
      <default><geom contype="0" conaffinity="0"/></default>
      <worldbody>
        {''.join(geoms)}
        <body name="cable" pos="0 0 {RADIUS}">
          <inertial pos="0 0 0" mass=".022" diaginertia="2e-6 2e-6 2e-6"/>
          <joint name="slide_x" type="slide" axis="1 0 0" damping=".001"/>
          <joint name="slide_y" type="slide" axis="0 1 0" damping=".001"/>
          <joint name="lift_z" type="slide" axis="0 0 1" damping=".01"/>
          <geom name="jacket" type="box" size=".0022 .022 {RADIUS}"/>
        </body>
      </worldbody>
      <contact>{''.join(pairs)}</contact>
    </mujoco>'''


def pull_case(model,forces,angle,hold=30.):
    data=mj.MjData(model)
    strap=[model.body(f'strap_{i}').id for i in (1,2)]
    jacket_id=model.body('cable').id
    start_ids=[model.joint(s).qposadr[0] for s in ('slide_x','slide_y')]
    direction=np.array([sin(radians(angle)),cos(radians(angle))])
    dt=model.opt.timestep
    for i in range(round(.28/dt)):
        scale=min(1.,i*dt/.14)
        for body,force in zip(strap,forces):
            data.xfrc_applied[body,2]=-force*scale
        mj.mj_step(model,data)
    origin=np.copy(data.qpos[start_ids])
    crossed=None
    limit=0.
    settle_normals=[]
    for i in range(round((1.3+hold)/dt)):
        scale=min(1.,i*dt/1.3)
        force=TARGET_N*scale
        data.xfrc_applied[jacket_id,:2]=force*direction
        mj.mj_step(model,data)
        slip=1000*float(np.linalg.norm(data.qpos[start_ids]-origin))
        limit=max(limit,slip)
        if not np.isfinite(slip):
            raise RuntimeError('Invalid grip model state')
        if slip>SLIP_LIMIT_MM:
            crossed=force
            break
        if i==round(.1/dt):
            by_strap=[0.,0.]
            for j,con in enumerate(data.contact):
                names=[model.geom(int(k)).name for k in con.geom]
                magnitudes=np.zeros(6)
                mj.mj_contactForce(model,data,j,magnitudes)
                for k in (0,1):
                    if f'top_{k+1}' in names:
                        by_strap[k]+=magnitudes[0]
            settle_normals=by_strap
    if settle_normals and max(abs(np.asarray(settle_normals)-forces))>.8:
        raise RuntimeError(f'Clamp reactions {settle_normals} did not match {forces}')
    return {'max_slip_mm':limit,'threshold_exceeded':crossed is not None,
            'force_at_threshold_N':crossed,'trial_seconds':float((i+1)*dt),
            'computed_top_reactions_N':settle_normals}


def main(output):
    tests=[]
    friction_cases=(('low',.20,.15),('mid',.40,.20),('high',.55,.25))
    nominal_forces=((4.,4.),(8.,8.),(12.,12.),(16.,16.),(12.,0.),(4.,12.))
    for name,liner,strap in friction_cases:
        xml=grip_model(liner,strap,.002)
        engine=mj.MjModel.from_xml_string(xml)
        if name=='mid':
            (output/'grip_moderate.xml').write_text(xml)
        for force,pull in product(nominal_forces,(0,45)):
            row=pull_case(engine,force,pull)
            capacity=(liner+strap)*sum(force)
            assert row['threshold_exceeded']==(capacity<TARGET_N)
            if row['threshold_exceeded']:
                assert capacity-.1 < row['force_at_threshold_N'] < capacity+.6
            row.update({'friction_case':name,'liner_mu':liner,'strap_mu':strap,'normal_each_N':force,'pull_deg':pull,
                        'coulomb_capacity_N':capacity})
            tests.append(row)
            print(name,force,pull,row['threshold_exceeded'],round(row['force_at_threshold_N'] or 10.,2),flush=True)
    faster=mj.MjModel.from_xml_string(grip_model(.40,.20,.001))
    repeat=[]
    for force in ((8.,8.),(12.,12.)):
        trial=pull_case(faster,force,45)
        baseline=next(r for r in tests if r['friction_case']=='mid' and r['pull_deg']==45 and r['normal_each_N']==force)
        assert trial['threshold_exceeded']==baseline['threshold_exceeded']
        repeat.append({'normal_each_N':force,**trial})
    (output/'grip_results.json').write_text(json.dumps({'mujoco_version':mj.__version__,'target_N':TARGET_N,
        'hold_sec':30,'displacement_limit_mm':SLIP_LIMIT_MM,'trials':tests,'verification_at_1ms':repeat},indent=2))


if __name__=='__main__':
    p=ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    main(args.output)
