"""MediaPipe eye-midpoint tracking and the R5 B1 USB control bridge."""
from argparse import ArgumentParser
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import time
from urllib.request import urlopen

MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
MODEL_HASH = '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'
AXES = ('eye-yaw', 'eye-pitch', 'blink', 'neck-yaw', 'neck-pitch')
LIMITS = ((-20., 20.), (-8., 8.), (0., 90.), (-60., 60.), (-15., 6.))
RATES = (160., 105., 950., 36., 22.)
ZERO = (0.,) * 5


def clamp(value, low, high):
    return min(high, max(low, value))


def bounded_goal(goal):
    return tuple(clamp(v, *limit) for v, limit in zip(goal, LIMITS, strict=True))


def parse_axes(text):
    names = set(text.lower().split(','))
    if names == {'all'}:
        return 31
    if not names or names.difference(AXES):
        raise ValueError('Use all or comma-separated axis names: ' + ', '.join(AXES))
    return sum(1 << AXES.index(name) for name in names)


@dataclass(frozen=True)
class Tracking:
    active: bool
    goals: tuple[float, ...]


class Planner:
    def __init__(self):
        self.command = ZERO
        self.last_time = None
        self.filtered = (0., 0.)
        self.active = False
        self.next_blink = None

    def step(self, error, feedback, seconds, blink_enabled=True, fixed_camera=False):
        dt = 1/30 if self.last_time is None else clamp(seconds - self.last_time, 0., .1)
        self.last_time = seconds
        if error is None:
            if self.active:
                self.command = bounded_goal(feedback)
            self.active = False
            self.filtered = (0., 0.)
            self.next_blink = None
            return Tracking(False, self.command)

        if not self.active:
            self.command = bounded_goal(feedback)
            self.next_blink = seconds + 3.8
        self.active = True

        blend = 1 - math.exp(-dt / .08)
        self.filtered = tuple(a+blend*(b-a) for a,b in zip(self.filtered,error,strict=True))
        yaw,pitch = self.filtered
        head_error = tuple(0. if abs(v)<2.4 else v-math.copysign(2.4,v) for v in (yaw,pitch))
        blink = self.blink_goal(seconds) if blink_enabled else 0.
        head_yaw,head_pitch = (0.,0.) if fixed_camera else feedback[3:5]
        desired = bounded_goal((
            0. if abs(yaw)<.45 else yaw,
            0. if abs(pitch)<.45 else pitch,
            blink,
            head_yaw+.85*head_error[0],
            head_pitch+.78*head_error[1],
        ))
        self.command = tuple(a+clamp(b-a,-v*dt,v*dt) for a,b,v in zip(self.command,desired,RATES,strict=True))
        return Tracking(True, self.command)

    def blink_goal(self, seconds):
        u = seconds-self.next_blink
        if u < 0:
            return 0.
        if u < .68:
            v = u/.68
        elif u < .80:
            return 90.
        elif u < 1.48:
            v = 1-(u-.80)/.68
        else:
            self.next_blink = seconds+4.15
            return 0.
        return 90*v*v*(3-2*v)


class CameraAngles:
    def __init__(self,hfov,calibration):
        self.hfov = hfov
        self.calibration = json.loads(calibration.read_text()) if calibration else None

    def error(self,point,width,height):
        if self.calibration:
            import cv2
            import numpy as np
            data=self.calibration
            matrix=np.array(data['camera_matrix'],dtype=np.float64)
            matrix[0,:]*=width/data['width']
            matrix[1,:]*=height/data['height']
            direction = cv2.undistortPoints(
                np.array([[point]],dtype=np.float64),matrix,np.array(data['dist_coeffs'],dtype=np.float64)
            )[0,0]
            x,y=direction
        else:
            focal=(width/2)/math.tan(math.radians(self.hfov/2))
            x,y=(point[0]-(width-1)/2)/focal,(point[1]-(height-1)/2)/focal
        return math.degrees(math.atan(x)),math.degrees(math.atan2(y,math.hypot(1,x)))


class UsbController:
    def __init__(self,device,mask):
        import serial
        self.link=serial.Serial(device,115200,timeout=.04,write_timeout=.30)
        self.mask=mask
        self.pose=ZERO
        self.last_state=None
        self.buffer=bytearray()

    def send(self,command):
        self.link.write((command+'\n').encode('ascii'))

    def lines(self):
        if b'\n' not in self.buffer or self.link.in_waiting:
            self.buffer.extend(self.link.read(min(1024,self.link.in_waiting or 1)))
        while b'\n' in self.buffer:
            raw, _, remainder=self.buffer.partition(b'\n')
            self.buffer=bytearray(remainder)
            if len(raw)<160:
                yield raw.decode('ascii',errors='replace').strip()
        if len(self.buffer)>512:
            self.buffer.clear()

    def start(self):
        deadline=time.monotonic()+6.
        next_ping=0.
        while time.monotonic()<deadline:
            now=time.monotonic()
            if now>=next_ping:
                self.send('PING')
                next_ping=now+.45
            if 'R5B1 1' in list(self.lines()):
                break
        else:
            raise RuntimeError('OpenRB R5 B1 firmware did not respond to PING.')
        self.send(f'ARM {self.mask}')
        deadline=time.monotonic()+3.
        acknowledged=False
        while time.monotonic()<deadline:
            for line in self.lines():
                if line.startswith(('LOCKED','ERROR')):
                    raise RuntimeError(line)
                if line==f'ARMED {self.mask}':
                    acknowledged=True
                self.handle_state(line)
                if acknowledged and self.last_state is not None:
                    return
        raise RuntimeError('OpenRB did not send ARM acknowledgement and position.')

    def handle_state(self,line):
        fields=line.split()
        axis_count=len(AXES)+(1 if self.mask&(1<<len(AXES)) else 0)
        if len(fields)!=axis_count+2 or fields[0]!='STATE':
            return
        try:
            mask=int(fields[1])
            pose=tuple(float(x) for x in fields[2:])
        except ValueError:
            return
        if mask==self.mask and all(math.isfinite(x) for x in pose):
            self.pose=pose
            self.last_state=time.monotonic()

    def read(self):
        if not self.link.in_waiting and b'\n' not in self.buffer:
            return
        for line in self.lines():
            if line.startswith('ERROR'):
                raise RuntimeError(line)
            self.handle_state(line)

    def close(self):
        try:
            self.send('HOLD')
        finally:
            self.link.close()


def ensure_model(path):
    if path.exists() and sha256(path.read_bytes()).hexdigest()==MODEL_HASH:
        return
    if path.exists():
        raise RuntimeError(f'Face Landmarker model hash does not match: {path}')
    with urlopen(MODEL_URL,timeout=25) as stream:
        data=stream.read()
    if sha256(data).hexdigest()!=MODEL_HASH:
        raise RuntimeError('Downloaded Face Landmarker model hash does not match.')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)


def eye_midpoint(result,width,height):
    if not result.face_landmarks or len(result.face_landmarks[0]) <= 362:
        return None
    face = result.face_landmarks[0]
    corners = [face[i] for i in (33,133,362,263)]
    pixels = [(p.x*(width-1),p.y*(height-1)) for p in corners]
    if not all(0<=x<width and 0<=y<height for x,y in pixels):
        return None
    if math.dist(pixels[0],pixels[1])<2.0 or math.dist(pixels[2],pixels[3])<2.0:
        return None
    return tuple(sum(p[i] for p in pixels)/4 for i in (0,1))


def annotate(cv2,frame,point,decision,drive):
    h,w = frame.shape[:2]
    center=(w//2,h//2)
    cv2.drawMarker(frame,center,(228,214,191),cv2.MARKER_CROSS,16,1,cv2.LINE_AA)
    if point is not None:
        xy=tuple(round(a) for a in point)
        cv2.line(frame,center,xy,(180,230,124),1,cv2.LINE_AA)
        cv2.circle(frame,xy,7,(170,240,116),-1,cv2.LINE_AA)
    cv2.rectangle(frame,(0,0),(w,51),(24,37,33),-1)
    status='TRACK' if decision.active else 'HOLD'
    title=f"{status}  /  {'OpenRB USB' if drive else 'camera preview'}"
    cv2.putText(frame,title,(14,22),cv2.FONT_HERSHEY_SIMPLEX,.57,(235,242,229),1,cv2.LINE_AA)
    q=decision.goals
    info=f'Eyes {q[0]:+.1f}, {q[1]:+.1f}    Neck {q[3]:+.1f}, {q[4]:+.1f} deg'
    cv2.putText(frame,info,(14,42),cv2.FONT_HERSHEY_SIMPLEX,.43,(200,218,207),1,cv2.LINE_AA)


def run(args):
    import cv2
    import mediapipe as mp

    if args.drive and not args.serial:
        raise ValueError('--drive needs --serial PORT. Camera preview is the default.')
    if args.serial and not args.drive:
        raise ValueError('Use --drive explicitly to connect to the controller.')
    is_live=args.source.isdecimal()
    if args.drive and not is_live:
        raise ValueError('Use a live camera source for the USB drive mode.')
    camera=CameraAngles(args.hfov,args.calibration)
    mask=parse_axes(args.axes)
    ensure_model(args.model)
    capture=cv2.VideoCapture(int(args.source) if is_live else args.source)
    if not capture.isOpened():
        raise RuntimeError(f'Cannot open camera or video {args.source}.')
    if is_live:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH,args.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT,args.height)
    fps=capture.get(cv2.CAP_PROP_FPS)
    if not math.isfinite(fps) or fps<=0:
        fps=30.
    options=mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(args.model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_faces=1,
        min_face_detection_confidence=.55,
        min_face_presence_confidence=.55,
        min_tracking_confidence=.55,
    )
    planner=Planner()
    controller=None
    output_video=None
    stats={'frames':0,'tracking_frames':0,'hold_frames':0,'losses':0,'reacquired':0}
    previous_ms=-1
    last_sent_time=0.
    last_active=False
    seen=False
    logical_pose=ZERO
    start=time.monotonic()

    try:
        if args.drive:
            controller=UsbController(args.serial,mask)
            controller.start()
            controller.send('HOLD')
        with mp.tasks.vision.FaceLandmarker.create_from_options(options) as detector:
            while True:
                ok,frame=capture.read()
                if not ok:
                    break
                if args.rotate_180:
                    frame=cv2.rotate(frame,cv2.ROTATE_180)
                height,width=frame.shape[:2]
                elapsed=time.monotonic()-start if is_live else stats['frames']/fps
                timestamp=max(previous_ms+1,round(elapsed*1000))
                previous_ms=timestamp
                rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                result=detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb),timestamp)
                point=eye_midpoint(result,width,height)
                if controller:
                    controller.read()
                    now=time.monotonic()
                    if controller.last_state is None or now-controller.last_state>.42:
                        point=None
                    feedback=controller.pose
                else:
                    feedback=logical_pose
                err=None if point is None else camera.error(point,width,height)
                decision=planner.step(err,feedback,elapsed,not args.no_blink,fixed_camera=not controller)
                if decision.active:
                    if seen and not last_active:
                        stats['reacquired']+=1
                    seen=True
                elif last_active:
                    stats['losses']+=1

                if controller:
                    if not decision.active and last_active:
                        controller.send('HOLD')
                    elif decision.active and now-last_sent_time>=.032:
                        controller.send('GO '+' '.join(f'{x:.3f}' for x in decision.goals))
                        last_sent_time=now
                else:
                    logical_pose=decision.goals
                last_active=decision.active
                stats['frames']+=1
                stats['tracking_frames' if decision.active else 'hold_frames']+=1
                if args.output or not args.headless:
                    annotate(cv2,frame,point,decision,bool(controller))
                if args.output:
                    if output_video is None:
                        output_video=cv2.VideoWriter(str(args.output),cv2.VideoWriter_fourcc(*'mp4v'),fps,(width,height))
                        if not output_video.isOpened():
                            raise RuntimeError(f'Cannot write {args.output}.')
                    output_video.write(frame)
                if not args.headless:
                    cv2.imshow('R5 B1 - Eye Tracking',frame)
                    if cv2.waitKey(1)&255 in (27,ord('q')):
                        break
    except KeyboardInterrupt:
        pass
    finally:
        if controller:
            controller.close()
        capture.release()
        if output_video:
            output_video.release()
        if not args.headless:
            cv2.destroyAllWindows()

    if stats['frames']==0:
        raise RuntimeError('No usable frames arrived.')
    print(json.dumps(stats,ensure_ascii=False))
    if args.report:
        args.report.write_text(json.dumps(stats,indent=2)+'\n')


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--source',default='0',help='USB camera index, or a video in preview mode')
    parser.add_argument('--model',type=Path,default=Path(__file__).parent/'model'/'face_landmarker.task')
    parser.add_argument('--hfov',type=float,default=106.)
    parser.add_argument('--calibration',type=Path,help='JSON with width,height,camera_matrix,dist_coeffs')
    parser.add_argument('--width',type=int,default=1280)
    parser.add_argument('--height',type=int,default=720)
    parser.add_argument('--serial')
    parser.add_argument('--drive',action='store_true')
    parser.add_argument('--axes',default='all',help=', '.join(AXES))
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--no-blink',action='store_true')
    parser.add_argument('--rotate-180',action='store_true')
    parser.add_argument('--output',type=Path,help='Write annotated MP4 locally')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    if not math.isfinite(args.hfov) or not 0<args.hfov<179:
        parser.error('hfov must be between 0 and 179 degrees')
    try:
        run(args)
    except (ValueError,RuntimeError,OSError) as error:
        parser.exit(1,f'{error}\n')


if __name__=='__main__':
    main()
