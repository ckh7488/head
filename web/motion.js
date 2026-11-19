import { Matrix4 } from "three";

export const axes = {
  neckYaw:   { label: "좌우", lower: -60, upper: 60, rate: 42 },
  neckPitch: { label: "상하", lower: -15, upper: 6, rate: 24 },
  eyeYaw:    { label: "좌우", lower: -20, upper: 20, rate: 128 },
  eyePitch:  { label: "상하", lower: -8, upper: 8, rate: 90 },
  blink:     { label: "눈꺼풀", lower: 0, upper: 90, rate: 900 },
  jaw:       { label: "턱 열림", lower: 0, upper: 14, rate: 190 }
};
export const jawPivot = [0, -9, 92];
export const neutral = Object.freeze(Object.fromEntries(Object.keys(axes).map(key => [key, 0])));
const rad = Math.PI / 180;
export const clamp = (value, lower, upper) => Math.min(upper, Math.max(lower, value));
export const ease = x => { const t = clamp(x, 0, 1); return t * t * (3 - 2 * t); };
const toPose = (part, value) => clamp(value, axes[part].lower, axes[part].upper);

export function advancePose(pose, target, dt) {
  const next = {};
  for (const [key, axis] of Object.entries(axes)) {
    const goal = toPose(key, target[key]);
    const step = axis.rate * dt;
    next[key] = Math.abs(goal - pose[key]) <= step ? goal : pose[key] + Math.sign(goal - pose[key]) * step;
  }
  return next;
}

export function blinkAt(time) {
  if (time < 0 || time >= .34) return 0;
  if (time < .105) return 90 * ease(time / .105);
  if (time < .155) return 90;
  return 90 * (1 - ease((time - .155) / .185));
}

export const clackDuration = .68;
export function clackAt(time) {
  if (time < 0 || time >= clackDuration) return 0;
  const cycle = clackDuration / 2;
  const phase = time % cycle;
  const peak = time < cycle ? 10 : 13;
  if (phase < .10) return peak * ease(phase / .10);
  if (phase < .14) return peak;
  return peak * (1 - ease((phase - .14) / .16));
}

export function demonstration(time) {
  const t = time % 8.2;
  const cue = (time + .36) % 3.91 - 1.44;
  return {
    neckYaw: 30 * Math.sin(t * Math.PI / 4.1),
    neckPitch: -4 + 6 * Math.sin(t * Math.PI / 4.1 + .4),
    eyeYaw: 13 * Math.sin(t * Math.PI / 4.1 + .82),
    eyePitch: 5 * Math.sin(t * Math.PI / 4.1 + 1.5),
    blink: blinkAt(cue),
    jaw: clackAt(t - 3.48),
  };
}

export class TargetFollower {
  constructor() { this.filtered = [0, 0]; }

  reset() { this.filtered = [0, 0]; }

  goals(target, pose, dt) {
    if (!target) return pose;
    const blend = 1 - Math.exp(-dt / .08);
    this.filtered[0] += blend * (target.yaw - pose.neckYaw - this.filtered[0]);
    this.filtered[1] += blend * (target.pitch - pose.neckPitch - this.filtered[1]);
    const [yaw, pitch] = this.filtered;
    const deadband = v => Math.abs(v) < 2.4 ? 0 : v - Math.sign(v) * 2.4;
    return {
      eyeYaw: yaw, eyePitch: pitch, blink: 0, jaw: pose.jaw,
      neckYaw: pose.neckYaw + .85 * deadband(yaw),
      neckPitch: pose.neckPitch + .78 * deadband(pitch),
    };
  }
}

function pivot(axis, degrees, x, y, z) {
  const rotate = new Matrix4();
  if (axis === "x") rotate.makeRotationX(degrees * rad);
  else rotate.makeRotationZ(degrees * rad);
  return new Matrix4().makeTranslation(x, y, z)
    .multiply(rotate).multiply(new Matrix4().makeTranslation(-x, -y, -z));
}

export function motionMatrix(kind, pose, drop = 0) {
  const result = new Matrix4();
  if (kind === "fixed") return result;
  if (kind === "hatch") return result.makeTranslation(0, 0, -clamp(drop, 0, 30));
  if (kind === "jaw") result.premultiply(pivot("x", toPose("jaw", pose.jaw), ...jawPivot));
  const yaw = -pose.eyeYaw;
  const pitch = pose.eyePitch;
  const blink = pose.blink;
  const eyeX = { look1: -34, look2: 34, look_horn: 0 };
  if (kind in eyeX) {
    result.premultiply(pivot("z", yaw, eyeX[kind], -39, 113));
  } else if (kind === "look_link") {
    result.premultiply(new Matrix4().makeTranslation(-16 * Math.sin(yaw * rad), 16 * (Math.cos(yaw * rad) - 1), 0));
  }
  if (kind === "tilt_horn") {
    result.premultiply(pivot("x", pitch, 58.65, 10, 151));
  } else if (kind === "tilt_link") {
    result.premultiply(new Matrix4().makeTranslation(0, 10 * (Math.cos(pitch * rad) - 1), 10 * Math.sin(pitch * rad)));
  } else if (kind === "tilt" || kind === "look_link" || kind in eyeX) {
    result.premultiply(pivot("x", pitch, 0, -39, 119));
  }
  const lids = { lid1: [-34, -39, 119], lid2: [34, -39, 119], blink_motor_horn: [1.2, 43, 88], blink_shaft_crank: [0, 25, 101] };
  if (kind in lids) {
    result.premultiply(pivot("x", blink, ...lids[kind]));
  } else if (kind === "blink_lid_link" || kind === "blink_drive_link") {
    result.premultiply(new Matrix4().makeTranslation(0, 8.25 * (Math.cos(blink * rad) - 1), 8.25 * Math.sin(blink * rad)));
  }
  if (kind !== "pan") result.premultiply(pivot("x", pose.neckPitch, 0, 0, 112));
  result.premultiply(pivot("z", -pose.neckYaw, 0, 0, 0));
  return result;
}
