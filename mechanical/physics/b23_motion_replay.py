"""Replay loaded B23 exhibit tracking and power-hold scenarios in MuJoCo."""
from argparse import ArgumentParser
from dataclasses import dataclass
from hashlib import sha256
import json
from math import atan2, degrees, hypot, radians, tan
from pathlib import Path
from random import Random
import re
import runpy

import mujoco as mj
import numpy as np

from b20_dynamics import (DERIVATIVE_GAIN, NORMAL_FRICTION, PROPORTIONAL_GAIN, UPPER_FRICTION,
                          capacity, load_bodies, model_xml, motor_parameters, x_rotation, z_rotation)
from b22_pitch_stop_release import jaw_parameters
from multibody import NECK_PIVOT, YAW_PIVOT, pos

ROOT = Path(__file__).resolve().parents[2]

ENCODER_DEG = 360 / 4096
VEL_UNIT = .229 * 6
ACC_UNIT = 214.577 * .1
NECK_JAW = [3, 4, 5]


@dataclass
class Firmware:
    limits: np.ndarray
    commanded: np.ndarray
    feedback_limits: np.ndarray
    speeds: dict
    accel: np.ndarray
    pwm: np.ndarray
    goal: float
    report: float
    watchdog: float
    jaw_hold_pwm: float
    jaw_recovery_pwm: float
    jaw_recovery_rate: float
    jaw_recovery_end_deg: float
    jaw_ready_deg: float
    jaw_recovery_limit_deg: float
    jaw_entry_neck_deg: float
    jaw_trim_deg: float
    jaw_trim_from_deg: float
    jaw_trim_delay: float
    jaw_recovery_timeout: float
    jaw_lag_deg: float
    jaw_position_gain: float
    exhibit_jaw_position_gain: float
    sha: str

    @classmethod
    def load(cls, root, track):
        content = (root/'control/openrb/R5B1/R5B1.ino').read_bytes()
        source = content.decode()

        def val(key, default=None):
            match = re.search(rf'\b{key}\s*=\s*(\d+(?:\.\d+)?)', source)
            if match is not None:
                return float(match[1])
            if default is not None:
                return default
            raise ValueError(f'Firmware constant {key} is missing')

        def ar(key):
            return np.array([int(x) for x in re.search(rf'\b{key}\[count\]\s*=\s*\{{([^}}]+)\}}', source)[1].split(',')])

        logical = np.array((*track['LIMITS'], (0., track['JAW_MAX_DEGREES'])))
        ticks = np.floor(logical[:, 1] / ENCODER_DEG).astype(int)
        neg = np.floor(-logical[:, 0]/ENCODER_DEG).astype(int)
        tolerance = int(val('positionTolerance'))
        independent = [0, 1, 3]
        ticks[independent] -= tolerance
        neg[independent] -= tolerance
        # ID3 has a separate real mechanism calibration; this model uses nominal 90°.
        ticks[2] = 1024
        neg[4] = int(val('neckPitchMaxNegativeTicks'))
        ticks[4] = int(val('neckPitchMaxPositiveTicks'))
        neg[3] = ticks[3] = int(val('neckYawCalibrationTicks'))
        commanded = np.column_stack((-neg, ticks))*ENCODER_DEG
        drift = np.array([tolerance]*5 + [val('jawPositionTolerance')])*ENCODER_DEG
        feedback_bounds = commanded + np.column_stack((-drift, drift))
        jaw_closing_tolerance = val('jawClosingTolerance', val('jawPositionTolerance'))
        feedback_bounds[5, 0] = -jaw_closing_tolerance * ENCODER_DEG
        normal = ar('velocity')*VEL_UNIT
        exhibit, returning = normal.copy(), normal.copy()
        exhibit[3:5] = [val('exhibitYawVelocity')*VEL_UNIT, val('exhibitPitchVelocity')*VEL_UNIT]
        returning[3:5] = val('returnNeckVelocity')*VEL_UNIT
        speeds = {'normal': normal, 'TRACK': exhibit, 'HOLD': exhibit, 'RETURN': returning}
        return cls(logical, commanded, feedback_bounds, speeds, ar('acceleration')*ACC_UNIT, ar('pwm')[-3:],
                   val('goalPeriodMs')/1000, val('reportMs')/1000, val('timeoutMs')/1000,
                   val('exhibitJawPwm'), val('exhibitJawRecoveryPwm'), val('exhibitJawVelocity') * VEL_UNIT,
                   val('jawClosingTolerance', val('exhibitJawStartTicks')) * ENCODER_DEG,
                   val('exhibitJawReadyTicks') * ENCODER_DEG,
                   val('exhibitJawRecoveryTicks') * ENCODER_DEG, val('exhibitJawEntryNeckTicks') * ENCODER_DEG,
                   val('exhibitJawTrimTicks', 0.) * ENCODER_DEG, val('exhibitJawTrimOpenTicks', 0.) * ENCODER_DEG,
                   val('exhibitJawTrimAfterMs', 0.) / 1000,
                   val('exhibitJawRecoveryMs') / 1000, val('exhibitJawLagTicks') * ENCODER_DEG,
                   val('jawPositionGain', 400.), val('exhibitJawPositionGain', 400.),
                   sha256(content).hexdigest())

    def motor_target(self, command):
        cols = (command >= 0).astype(int)
        n = np.arange(len(command))
        ratio = np.divide(command, self.limits[n, cols], out=np.zeros(len(command)), where=self.limits[n, cols]!=0)
        travel = self.commanded[n, cols]*ratio
        return np.sign(travel)*np.floor(np.abs(travel)/ENCODER_DEG+.5)*ENCODER_DEG

    def reports(self, shaft):
        cols = (shaft >= 0).astype(int)
        n = np.arange(len(shaft))
        raw = np.sign(shaft)*np.floor(np.abs(shaft)/ENCODER_DEG+.5)*ENCODER_DEG
        ratio = np.divide(raw, self.commanded[n, cols], out=np.zeros(len(raw)), where=self.commanded[n, cols]!=0)
        return raw, np.clip(ratio*self.limits[n, cols], self.limits[:,0], self.limits[:,1])


def camera(capture, center, target, hfov):
    turn, tilt = z_rotation(radians(capture[3])), x_rotation(radians(capture[4]))
    optical_center = YAW_PIVOT + turn@(NECK_PIVOT + tilt@(center - NECK_PIVOT) - YAW_PIVOT)
    x, y, z = (turn@tilt).T@(target - optical_center)
    edge = -y*tan(radians(hfov/2))
    if y>=0 or abs(x)>edge or abs(z)>edge*720/1280:
        return None
    return degrees(atan2(x, -y)), degrees(atan2(-z, hypot(x, y)))


def profile_step(p, v, goal, vmax, accel, dt):
    change = goal-p
    desired = np.sign(change)*np.minimum(vmax, np.sqrt(2*accel*np.abs(change)))
    # Integrate actual acceleration through reversals. Round only when the last sub-tick
    # displacement can physically stop within one integration step.
    new_v = v + np.clip(desired-v, -accel*dt, accel*dt)
    new_p = p + .5*(v+new_v)*dt
    settled = (abs(change)<accel*dt*dt) & (abs(v)<=accel*dt)
    return np.where(settled, goal, new_p), np.where(settled, 0, new_v)


def direct_input(label, t):
    if label.startswith('watchdog'):
        cutoff_s = float(label.partition('-')[2] or '1.035')
        if t >= cutoff_s:
            return None
        goals = (0, 0, 0, 59.8, 4.5, 0)
    elif label == 'reversal':
        goals = (0, 0, 0, 60, 4.5, 5.5) if 0.3 <= t < .92 or 2.15 <= t < 3.85 else (0, 0, 0, -60, -15, 0)
    elif label == 'jaw-demo':
        goals = (0, 0, 0, 0, 0, 5.5 if .30 <= t < .82 or 1.58 <= t < 2.08 else 0)
    else:
        raise ValueError(label)
    return np.asarray(goals), 'normal'


def motion(name, d, angle_sign=1):
    if name.startswith('cold-close-exhibit'):
        def target(t):
            side = angle_sign * np.sign(np.cos(t * 1.3))
            return np.array((side * d * tan(radians(43.)), -d - .039, .285))
        return 10., target, None
    if name.startswith('cold-close'):
        return 3.2, None, None
    if name == 'walk':
        extent = d*tan(radians(85.))
        xt = lambda t: angle_sign*(-extent+.8*t)
        target = lambda t: np.array((xt(t), -d-.039, .119+.2))
        return (extent+d*tan(radians(80.)))/.8 + .5, target, None
    if name == 'turn':
        target = lambda _: np.array((angle_sign*d*tan(radians(40)), -d-.039, .119+.15))
        return 5., target, None
    if name in ('loss', 'reacquire'):
        target = lambda t: np.array((angle_sign*d*tan(radians(35)) if t < 9.3 else -angle_sign*d*tan(radians(35)),
                                      -d-.039, .119+(angle_sign*.20)))
        hidden = lambda t: t >= 6. if name == 'loss' else 6. <= t < 9.3
        return 15., target, hidden
    duration = 2.8 if name.startswith('watchdog') else {'reversal': 5., 'jaw-demo': 2.65}[name]
    return duration, None, None


def replay(cad, fw, track, model, motor, dead, case, scenario, direction, trace, jaw_mech,
           latency=.12, force=0.):
    # Externally fixed, calibrated neutral. The visual sensing here is a synthetic target projected
    # through the exact nominal lens center rather than measured MediaPipe video.
    state = mj.MjData(model)
    ideal = mj.MjData(model)
    obj = next(r for r in cad['parts'] if r['name']=='Part068')
    center = pos(obj['solids'][0]['center'])
    duration, target, hidden = motion(scenario, 1.5, direction)
    planner = track['Planner'](exhibit=True, rng=Random(7))
    dt = model.opt.timestep
    goal = np.zeros(6)
    ref_p = np.zeros(6)
    ref_v = np.zeros(6)
    ideal_eyes = np.zeros(3)
    measured = np.zeros(6)
    next_goal = next_report = frame_index = 0
    goal_ticks = round(fw.goal / dt)
    report_ticks = round(fw.report / dt)
    latency_ticks = round(latency/dt)
    phase = 'normal'
    pending = None
    last_command = last_transmitted = None
    previous_active = False
    fault = None
    freeze_witness = []
    samples = []
    states = []
    frames = []
    min_margin = np.full(3,np.inf)
    max_tau = np.zeros(3)
    old_friction = model.dof_frictionloss.copy()
    active_mask = np.array([1,1,1,1,1,0], dtype=bool) if target else np.array([0,0,0,1,1,1],dtype=bool)
    cold_close = scenario.startswith('cold-close')
    holding_jaw = target is not None or cold_close
    proportional_gain = PROPORTIONAL_GAIN.copy()
    # Scale the fitted factory-gain jaw stiffness by the documented register ratio.
    # The resulting response still needs measurement on the installed mechanism.
    proportional_gain[2] *= (fw.exhibit_jaw_position_gain if holding_jaw else fw.jaw_position_gain) / 400.
    active_mask[5] = True
    recovering_jaw = cold_close
    recovered_at = None
    jaw_trimmed_at = None
    jaw_follow_reports = 0
    feedback_at = 0.
    pwm_duty = fw.pwm / 885.
    if cold_close:
        initial = fw.jaw_recovery_limit_deg if scenario.endswith('limit') else 8.5
        state.qpos[1] = radians(direction * fw.jaw_entry_neck_deg)
        state.qpos[2] = radians(initial)
        goal[4] = ref_p[4] = degrees(state.qpos[1])
        ref_p[5] = initial

    def hold(t, why):
        nonlocal pending, last_command
        physical = np.r_[ideal_eyes, np.degrees(state.qpos)]
        raw, _ = fw.reports(physical)
        legal = (active_mask & (raw >= fw.feedback_limits[:, 0] - 1e-9)
                 & (raw <= fw.feedback_limits[:, 1] + 1e-9))
        if holding_jaw:
            legal[5] = False
        old = goal.copy()
        goal[legal] = np.clip(raw[legal], fw.commanded[legal,0], fw.commanded[legal,1])
        pending = None
        last_command = None
        freeze_witness.append({'at_s': t, 'cause': why, 'pre_freeze_angle_deg': physical[3:].tolist(),
                               'pre_freeze_speed_deg_s': np.degrees(state.qvel).tolist(),
                               'goal_before_deg': old[3:].tolist(), 'hold_goal_deg': goal[3:].tolist(),
                               'unconfirmed_ids': (np.flatnonzero(active_mask & ~legal)+1).tolist()})

    for i in range(round(duration / dt) + 1):
        t=i*dt
        physical = np.r_[ideal_eyes, np.degrees(state.qpos)]
        states.append(physical)
        if last_command is not None and t-last_command>=fw.watchdog-1e-9:
            hold(t,'watchdog')
        if i>=next_report:
            raw, measured = fw.reports(physical)
            feedback_at = t
            next_report+=report_ticks
            outside = active_mask & ((raw<fw.feedback_limits[:,0]-1e-9) | (raw>fw.feedback_limits[:,1]+1e-9))
            if recovering_jaw and fault is None:
                close_limit = fw.jaw_trim_deg if jaw_trimmed_at is not None else fw.jaw_recovery_end_deg
                outside[5] = not -close_limit <= raw[5] <= fw.jaw_recovery_limit_deg
                if max(abs(raw[3:5])) > 22 * ENCODER_DEG:
                    fault = {'at_s': t, 'ids': [5], 'reason': 'neck moved during jaw recovery'}
                    active_mask[5] = False
                    hold(t, 'jaw-recovery-neck-position')
                elif abs(raw[5]) <= fw.jaw_ready_deg and not outside[5]:
                    recovering_jaw = False
                    goal[5] = 0.
                    recovered_at = t
                    if target is not None:
                        planner.start_centering(measured[:5])
                elif t >= fw.jaw_recovery_timeout:
                    fault = {'at_s': t, 'ids': [6], 'reason': 'jaw recovery timeout'}
                    active_mask[5] = False
                    hold(t, 'jaw-recovery-timeout')
                elif (fw.jaw_trim_deg > 0 and jaw_trimmed_at is None and t >= fw.jaw_trim_delay
                      and fw.jaw_ready_deg < raw[5] <= fw.jaw_trim_from_deg):
                    jaw_trimmed_at = t
                    goal[5] = -fw.jaw_trim_deg
            elif holding_jaw and t >= (recovered_at or 0.) + .6:
                jaw_follow_reports = jaw_follow_reports + 1 if abs(raw[5]) > fw.jaw_lag_deg else 0
                if jaw_follow_reports >= 2:
                    outside[5] = True
            if fault is None and np.any(outside):
                ids = (np.flatnonzero(outside)+1).tolist()
                fault={'at_s':t, 'ids':ids,'raw_relative_deg':raw.tolist()}
                if 6 in ids or holding_jaw:
                    active_mask[5]=False
                hold(t,'feedback-position-limit')
        cap_tick=round(frame_index*dt**-1/30)
        if i>=cap_tick + (latency_ticks if target else 0) and fault is None:
            frame_index += 1
            if target and not recovering_jaw:
                picture_time=cap_tick*dt
                picture_target=target(picture_time)
                error=None if hidden and hidden(picture_time) else camera(states[min(cap_tick,i)], center, picture_target, 106.)
                decision=planner.step(error, measured[:5], t, blink_enabled=False, feedback_at=feedback_at)
                frames.append((t,picture_time,error is not None,decision.phase))
                if decision.active or decision.keep_neutral:
                    command = np.r_[decision.goals, 0.]
                    desired_phase = 'RETURN' if decision.keep_neutral else decision.phase
                else:
                    if previous_active:
                        hold(t,'planner-idle')
                    command = desired_phase = None
                previous_active = decision.active or decision.keep_neutral
            elif not cold_close:
                incoming = direct_input(scenario,t)
                command, desired_phase = incoming if incoming is not None else (None,None)
            else:
                command = desired_phase = None
            send_period = .12 if target and not recovering_jaw and decision.keep_neutral else .032
            if command is not None and (last_transmitted is None or t-last_transmitted>=send_period-1e-9):
                pending = fw.motor_target(command), desired_phase
                last_command=last_transmitted=t
        if i>=next_goal:
            next_goal+=goal_ticks
            if pending is not None:
                g, phase = pending
                goal[:] = g
                pending=None
        maxspeed = fw.speeds[phase]
        if holding_jaw:
            maxspeed = maxspeed.copy()
            maxspeed[5] = fw.jaw_recovery_rate
        stamp = float(np.hypot(*np.degrees(state.qvel[:2])))
        next_ref, next_v = profile_step(ref_p, ref_v, goal, maxspeed, fw.accel, dt)
        reference_acceleration = (next_v-ref_v)/dt
        ideal_eyes = next_ref[:3]
        ref_p, ref_v = next_ref, next_v
        converter = np.pi / 180
        request = (proportional_gain*np.sign(ref_p[NECK_JAW]*converter-state.qpos)*
                   np.maximum(abs(ref_p[NECK_JAW]*converter-state.qpos)-radians(dead)/2,0.)
                   +DERIVATIVE_GAIN*(ref_v[NECK_JAW]*converter-state.qvel))
        if holding_jaw:
            pwm_duty[2] = (fw.jaw_recovery_pwm if recovering_jaw else fw.jaw_hold_pwm) / 885.
        avail = capacity(motor, state.qvel, request, pwm=pwm_duty)
        state.ctrl[:] = np.where(active_mask[3:], np.clip(request, -avail, avail), 0.)
        jaw_limit, jaw_stiffness = jaw_mech
        jaw_contact = min(0., state.qpos[2] - radians(-1.5)) + max(0., state.qpos[2]-jaw_limit)
        touch = force*.058*np.sin(np.pi*(t-.88)/.15)**2 if .88<t<1.03 else 0.
        state.qfrc_applied[2]=touch-jaw_contact*jaw_stiffness
        max_tau=np.maximum(abs(state.ctrl),max_tau)
        if i%10==0:
            ideal.qpos[:],ideal.qvel[:],ideal.qacc[:]=ref_p[NECK_JAW]*converter,ref_v[NECK_JAW]*converter,reference_acceleration[NECK_JAW]*converter
            model.dof_frictionloss[:]=0
            mj.mj_inverse(model,ideal)
            model.dof_frictionloss[:]=old_friction
            demand=np.abs(ideal.qfrc_inverse)+old_friction
            min_margin=np.minimum(min_margin,capacity(motor,ideal.qvel,ideal.qfrc_inverse,pwm=pwm_duty)-demand)
        samples.append((t, *physical, *np.degrees(state.qvel), stamp, *state.ctrl, *goal[3:], *ref_p[3:], *ref_v[3:]))
        mj.mj_step(model,state)
    matrix = np.asarray(samples)
    if not np.isfinite(matrix).all():
        raise ValueError('nonfinite dynamics')
    if trace is not None:
        cols = ('time_s,eye_yaw_deg,eye_pitch_deg,blink_deg,neck_yaw_deg,neck_pitch_deg,jaw_deg,'
                'yaw_speed_deg_s,pitch_speed_deg_s,jaw_speed_deg_s,neck_combined_speed_deg_s,'
                'yaw_tau_nm,pitch_tau_nm,jaw_tau_nm,yaw_goal_deg,pitch_goal_deg,jaw_goal_deg,'
                'yaw_profile_deg,pitch_profile_deg,jaw_profile_deg,'
                'yaw_profile_speed_deg_s,pitch_profile_speed_deg_s,jaw_profile_speed_deg_s')
        filename = f'{case}-{scenario}-{direction:+d}-{latency:.2f}-{force:.2f}.csv'
        np.savetxt(trace/filename, matrix[::5], delimiter=',', header=cols, comments='', fmt='%.6f')
    result={'latency_s':latency,'force_N':force,'max_neck_combined_speed_deg_s':float(matrix[:,10].max()),
            'shaft_max_abs_speed_deg_s':np.max(abs(matrix[:,7:10]),axis=0).tolist(),
            'range_deg':np.column_stack((matrix[:,4:7].min(0),matrix[:,4:7].max(0))).tolist(),
            'min_profile_reference_torque_margin_Nm':min_margin.tolist(),'max_applied_torque_Nm':max_tau.tolist(),
            'firmware_feedback_fault':fault,'freeze_events':freeze_witness,
            'final_neck_jaw_deg':matrix[-1,4:7].tolist()}
    if scenario=='walk':
        visible=next((f for f in frames if f[2]),None)
        theta=np.array([degrees(atan2(target(t)[0],1.5)) for t in matrix[:,0]])
        gaze=abs(theta-matrix[:,4]-matrix[:,1]); stop=duration-.5
        if visible:
            hits=np.flatnonzero((matrix[:,0]>=visible[0])&(gaze<=10.))
            if len(hits):
                k=hits[0]; final_t=matrix[k,0]; portion=(final_t<=matrix[:,0])&(matrix[:,0]<=stop)
                result.update(first_visible_capture_s=visible[1],first_inside_10deg_s=final_t,
                              acquisition_s=float(final_t-visible[1]), horizontal_tracking_10deg_ratio=float(np.mean(gaze[portion]<=10.)),
                              missed_after_acquiring=sum(not f[2] for f in frames if final_t<=f[1]<=stop),
                              final_80deg_error=float(gaze[round(stop/dt)]),
                              final_80deg_head_yaw=float(matrix[round(stop/dt),4]),
                              final_80deg_eye_yaw=float(matrix[round(stop/dt),1]))
    if scenario=='turn':
        bearing=direction*40.
        result.update(overshoot_deg=float(max(0,np.max(direction*matrix[:,4])-40)),
                      horizontal_error_at_4s_deg=float(abs(bearing-matrix[round(4/dt),4]-matrix[round(4/dt),1])))
    if scenario in ('loss','reacquire'):
        first=next((f[0] for f in frames if f[1]>=6. and not f[2]),None)
        move=next((f[0] for f in frames if f[3]=='RETURN'),None)
        if move and first:
            at=round(move/dt); first_i=round(first/dt)
            resume=next((f[0] for f in frames if f[0]>move and f[3]=='TRACK'),duration)
            result.update(hold_command_s=float(move-first),
                      maximum_hold_drift_deg=float(np.max(np.linalg.norm(matrix[first_i:at,4:6]-matrix[first_i,4:6],axis=1))),
                      return_peak_speed_deg_s=float(matrix[at:round(resume/dt)+1,10].max()),
                      parked=frames[-1][3]=='IDLE', return_failed=any(f[3]=='RETURN_FAILED' for f in frames))
    if force:
        selecting=(matrix[:,0]>=.88)&(matrix[:,0]<=1.03)
        result.update(jaw_pause_s=float(dt*np.sum(matrix[selecting,9]>=-1.)),
                      jaw_angle_at_touch_release_deg=float(matrix[round(1.03/dt),6]))
    if cold_close:
        result['jaw_recovered_at_s'] = recovered_at
        result['jaw_trimmed_at_s'] = jaw_trimmed_at
        if recovered_at is not None:
            post_recovery = matrix[round(recovered_at / dt):, 6]
            result['jaw_after_recovery_range_deg'] = [float(post_recovery.min()), float(post_recovery.max())]
            if target is not None:
                result['exhibit_tracking_frames'] = sum(frame[3] == 'TRACK' for frame in frames)
    return result


def main(cad, grams, jaw_stop, output, root=ROOT, trace=False, jaw_minimum_voltage=4.27):
    track=runpy.run_path(str(root/'control/pc/track.py'))
    firmware=Firmware.load(root,track)
    scene=json.loads((cad/'cad_parts.json').read_bytes())
    bodies,_,_ = load_bodies(scene, cad,json.loads(grams.read_bytes()))
    output.mkdir(parents=True,exist_ok=True)
    warm_jaw_case = f'warm_{jaw_minimum_voltage:g}V_jaw'.replace('.', 'p')
    supply={'nominal':((12.,12.,5.),.85,NORMAL_FRICTION,.35),
            'warm_low':((11.1,11.1,5.),.55,UPPER_FRICTION,.75),
            'warm_minimum_rails':((10.62,10.62,jaw_minimum_voltage),.55,UPPER_FRICTION,.75),
            'warm_4p5V_jaw':((11.1,11.1,4.5),.55,UPPER_FRICTION,.75),
            warm_jaw_case:((11.1,11.1,jaw_minimum_voltage),.55,UPPER_FRICTION,.75)}
    jaw_stop_bytes = jaw_stop.read_bytes()
    stop, stiffness = jaw_parameters(json.loads(jaw_stop_bytes))
    jaw_mech=(radians(stop),stiffness)
    cases={}
    cold = [(scenario, sign, .12, 0.) for scenario in ('cold-close', 'cold-close-limit') for sign in (-1, 1)]
    for case, (volts,derating,friction,dead) in supply.items():
        motor=motor_parameters(volts,derating)
        xml=model_xml(bodies,pos(scene['jaw_pivot_mm']),motor,friction,firmware.pwm/885.)
        if trace:
            (output/f'{case}.xml').write_text(xml)
        model=mj.MjModel.from_xml_string(xml)
        if case=='warm_4p5V_jaw':
            scenarios=[('jaw-demo',1,.12,force) for force in (0.,.25,.5,1.)]
        elif case==warm_jaw_case:
            cold_exhibit = [(scenario, sign, .12, 0.) for scenario in
                            ('cold-close-exhibit', 'cold-close-exhibit-limit') for sign in (-1, 1)]
            scenarios = cold + cold_exhibit + [('loss', 1, .12, 0.), ('loss', -1, .12, 0.)]
        else:
            scenarios=[(name,1,.12,0.) for name in ('walk','turn','loss','reacquire','reversal','watchdog','jaw-demo')]
            scenarios += [(n,-1,.12,0.) for n in ('walk','turn','loss')] \
                + [('walk',1,.20,0.)] + [(f'watchdog-{delay}',1,.12,0.) for delay in (1.12,1.2,1.28)]
            if case == 'nominal':
                scenarios += cold
        for scenario,direction,latency,force in scenarios:
            result=replay(scene, firmware, track, model, motor, dead, case, scenario, direction,
                            output if trace else None, jaw_mech, latency, force)
            key=f'{case}-{scenario}-{direction:+d}-{latency:.2f}-{force:.2f}'
            cases[key]=result
            print(key, 'max speed', round(result['max_neck_combined_speed_deg_s'],3),'range', np.round(result['range_deg'],3).tolist(),
                  'fault',result['firmware_feedback_fault'],'tracking score',result.get('horizontal_tracking_10deg_ratio'),
                  'return speed',result.get('return_peak_speed_deg_s'),flush=True)
    report={'cad_sha256':scene['source_sha256'],'sliced_grams_sha256':sha256(grams.read_bytes()).hexdigest(),
            'solver_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
            'jaw_stop_sha256':sha256(jaw_stop_bytes).hexdigest(),
            'firmware_sha256':firmware.sha,'tracker_sha256':sha256((root/'control/pc/track.py').read_bytes()).hexdigest(),
            'mujoco_version':mj.__version__,'commanded_shaft_range_deg':firmware.commanded.tolist(),
            'feedback_guard_deg':firmware.feedback_limits.tolist(),
            'neck_yaw_pitch_jaw_pwm_registers':firmware.pwm.tolist(),
            'axis_speed_caps_deg_s':{k:v.tolist() for k,v in firmware.speeds.items()},'axis_profile_accel_deg_s2':firmware.accel.tolist(),
            'installed_masses_g':[b.mass*1000 for b in bodies],
            'exhibit_jaw_hold': {'pwm_limit': firmware.jaw_hold_pwm, 'recovery_pwm_limit': firmware.jaw_recovery_pwm,
                                 'recovery_velocity_deg_s': firmware.jaw_recovery_rate,
                                 'position_p_gain_register': firmware.exhibit_jaw_position_gain,
                                 'reference_position_p_gain_register': 400,
                                 'position_p_gain_model_Nm_per_rad':
                                     PROPORTIONAL_GAIN[2] * firmware.exhibit_jaw_position_gain / 400.,
                                 'recovery_closing_guard_deg': -firmware.jaw_recovery_end_deg,
                                 'ready_opening_deg': firmware.jaw_ready_deg,
                                 'minimum_jaw_supply_V': jaw_minimum_voltage,
                                 'recovery_limit_deg': firmware.jaw_recovery_limit_deg},
            'passive_jaw_model':{'positive_pitch_stop_deg':stop,'stop_stiffness_Nm_rad':stiffness,
                                    'negative_pitch_stop_deg':-1.5,'assumption':'Elastic opening stop and conservative lower tooth contact angle. Powered exhibit commands calibrated closed zero.'},
            'scope':('Rigid coupled neck and jaw, fitted approximate torque-limited position dynamics. Live Planner with sampled camera geometry, '
                     'encoder and bus model. No actual MediaPipe video, wiring loads, current/temperature measurement, gear flex, no physical cycles. '
                     'Eye trajectory uses the position profile and encoder model. Direct reversal is a separate engineering stress case. '
                     'Actual servo tuning, calibrated spans and thermal limits need bench measurements.'),'cases':cases}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for key in ('cad', 'grams', 'jaw_stop', 'output'):
        parser.add_argument(key, type=Path)
    parser.add_argument('--trace', action='store_true', help='Store the simulated trajectories and MuJoCo models.')
    parser.add_argument('--jaw-minimum-voltage', type=float, default=4.27,
                        help='Jaw voltage for the warm minimum-rail and cold-recovery cases.')
    main(**vars(parser.parse_args()))
