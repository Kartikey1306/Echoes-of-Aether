import * as THREE from 'three';
import { clamp, clamp01, DEG, smoothstep } from '../../core/MathUtil';
import { BONE_NAMES, type BoneName } from './HumanRig';

// Layered procedural animator for the humanoid rig.
// Poses are Euler angles (degrees, XYZ order) relative to the identity rest pose, plus a hips offset (metres, reference scale).

export const NB = BONE_NAMES.length;
export const BI: Record<BoneName, number> = Object.fromEntries(BONE_NAMES.map((n, i) => [n, i])) as Record<BoneName, number>;

export type PoseSpec = Partial<Record<BoneName, [number, number, number]>> & { hipsPos?: [number, number, number] };

export class PoseBuf {
  e = new Float32Array(NB * 3);
  p = new Float32Array(3);
  clear() {
    this.e.fill(0);
    this.p.fill(0);
    return this;
  }
  set(spec: PoseSpec) {
    this.clear();
    for (const k in spec) {
      if (k === 'hipsPos') continue;
      const i = BI[k as BoneName];
      const v = spec[k as BoneName]!;
      this.e[i * 3] = v[0]; this.e[i * 3 + 1] = v[1]; this.e[i * 3 + 2] = v[2];
    }
    if (spec.hipsPos) this.p.set(spec.hipsPos);
    return this;
  }
}

/** Expand a pose spec with mirrored entries: keys ending in `_S` apply to L as-is and to R mirrored. */
export function sym(spec: Record<string, [number, number, number]> & { hipsPos?: [number, number, number] }): PoseSpec {
  const out: Record<string, [number, number, number]> = {};
  for (const k in spec) {
    const v = spec[k] as [number, number, number];
    if (k.endsWith('_S')) {
      const b = k.slice(0, -2);
      out[b + '_L'] = [v[0], v[1], v[2]];
      out[b + '_R'] = [v[0], -v[1], -v[2]];
    } else out[k] = v;
  }
  return out as PoseSpec;
}

/** Mirror a whole pose left<->right (for mirrored attack variants). */
export function mirrorPose(spec: PoseSpec): PoseSpec {
  const out: Record<string, [number, number, number]> = {};
  for (const k in spec) {
    const v = (spec as Record<string, [number, number, number]>)[k];
    if (k === 'hipsPos') { out[k] = [-v[0], v[1], v[2]]; continue; }
    let name = k;
    if (k.endsWith('_L')) name = k.slice(0, -2) + '_R';
    else if (k.endsWith('_R')) name = k.slice(0, -2) + '_L';
    out[name] = [v[0], -v[1], -v[2]];
  }
  return out as PoseSpec;
}

export interface ClipEvent { t: number; name: string }

export interface Clip {
  name: string;
  duration: number;
  loop: boolean;
  events?: ClipEvent[];
  sample(t: number, out: PoseBuf): void;
}

/** Keyframed clip with Catmull-Rom interpolation of Euler channels. */
export class KeyClip implements Clip {
  private times: number[];
  private poses: PoseBuf[];
  constructor(public name: string, keys: { t: number; pose: PoseSpec }[], public duration: number, public loop = false, public events: ClipEvent[] = []) {
    this.times = keys.map((k) => k.t);
    this.poses = keys.map((k) => new PoseBuf().set(k.pose));
  }
  sample(t: number, out: PoseBuf) {
    const n = this.times.length;
    if (n === 1) {
      out.e.set(this.poses[0].e);
      out.p.set(this.poses[0].p);
      return;
    }
    if (this.loop) t = ((t % this.duration) + this.duration) % this.duration;
    else t = clamp(t, 0, this.duration);
    let i = 0;
    while (i < n - 1 && this.times[i + 1] <= t) i++;
    if (i >= n - 1) {
      if (!this.loop) {
        out.e.set(this.poses[n - 1].e);
        out.p.set(this.poses[n - 1].p);
        return;
      }
    }
    const i1 = i, i2 = this.loop ? (i + 1) % n : Math.min(i + 1, n - 1);
    const i0 = this.loop ? (i - 1 + n) % n : Math.max(0, i - 1);
    const i3 = this.loop ? (i + 2) % n : Math.min(n - 1, i + 2);
    const t1 = this.times[i1];
    let t2 = this.times[i2];
    if (t2 <= t1) t2 = this.duration + (this.loop ? this.times[i2] : 0);
    const span = Math.max(1e-5, t2 - t1);
    const u = clamp01((t - t1) / span);
    const P0 = this.poses[i0], P1 = this.poses[i1], P2 = this.poses[i2], P3 = this.poses[i3];
    const u2 = u * u, u3 = u2 * u;
    const cr = (a: number, b: number, c: number, d: number) => 0.5 * (2 * b + (-a + c) * u + (2 * a - 5 * b + 4 * c - d) * u2 + (-a + 3 * b - 3 * c + d) * u3);
    for (let k = 0; k < NB * 3; k++) out.e[k] = cr(P0.e[k], P1.e[k], P2.e[k], P3.e[k]);
    for (let k = 0; k < 3; k++) out.p[k] = cr(P0.p[k], P1.p[k], P2.p[k], P3.p[k]);
  }
}

/** Clip defined by a function of normalised phase. */
export class FnClip implements Clip {
  constructor(public name: string, public duration: number, public loop: boolean, private fn: (phase: number, out: PoseBuf) => void, public events: ClipEvent[] = []) {}
  sample(t: number, out: PoseBuf) {
    const ph = this.loop ? (((t / this.duration) % 1) + 1) % 1 : clamp01(t / this.duration);
    out.clear();
    this.fn(ph, out);
  }
}

// Per-bone masks.
const UPPER = new Float32Array(NB);
const LOWER = new Float32Array(NB);
for (const n of BONE_NAMES) {
  const i = BI[n];
  const up = /spine|chest|neck|head|clavicle|upperarm|forearm|hand/.test(n);
  UPPER[i] = n === 'spine' ? 0.6 : up ? 1 : 0;
  LOWER[i] = up ? (n === 'spine' ? 0.4 : 0) : 1;
}
const FULL = new Float32Array(NB).fill(1);
export const MASKS = { full: FULL, upper: UPPER, lower: LOWER };

const _q = new THREE.Quaternion();
const _q2 = new THREE.Quaternion();
const _e = new THREE.Euler();

function poseToQuats(p: PoseBuf, out: Float32Array) {
  for (let i = 0; i < NB; i++) {
    _e.set(p.e[i * 3] * DEG, p.e[i * 3 + 1] * DEG, p.e[i * 3 + 2] * DEG, 'XYZ');
    _q.setFromEuler(_e);
    out[i * 4] = _q.x; out[i * 4 + 1] = _q.y; out[i * 4 + 2] = _q.z; out[i * 4 + 3] = _q.w;
  }
}

function slerpInto(a: Float32Array, b: Float32Array, w: number, mask: Float32Array, out: Float32Array) {
  for (let i = 0; i < NB; i++) {
    const k = w * mask[i];
    if (k <= 0.0001) {
      if (out !== a) for (let j = 0; j < 4; j++) out[i * 4 + j] = a[i * 4 + j];
      continue;
    }
    _q.set(a[i * 4], a[i * 4 + 1], a[i * 4 + 2], a[i * 4 + 3]);
    _q2.set(b[i * 4], b[i * 4 + 1], b[i * 4 + 2], b[i * 4 + 3]);
    _q.slerp(_q2, Math.min(1, k));
    out[i * 4] = _q.x; out[i * 4 + 1] = _q.y; out[i * 4 + 2] = _q.z; out[i * 4 + 3] = _q.w;
  }
}

interface ActionState {
  clip: Clip;
  time: number;
  speed: number;
  weight: number;
  fadeIn: number;
  fadeOut: number;
  mask: Float32Array;
  firedEvents: Set<number>;
  onEvent?: (name: string) => void;
  onEnd?: () => void;
  ending: boolean;
  hold: boolean;
}

export interface LocoSet {
  idle: Clip;
  walk: Clip;
  run: Clip;
  sprint: Clip;
  jump: Clip;
  fall: Clip;
  combatIdle?: Clip;
  strideWalk: number;
  strideRun: number;
  strideSprint: number;
}

/** Drives a rig's bones from layered clips plus procedural additive layers. */
export class Animator {
  readonly bones: THREE.Bone[];
  private restPos: THREE.Vector3[];
  private scale: number;

  loco: LocoSet;
  /** Ground speed (m/s), set by the controller. */
  speed = 0;
  grounded = true;
  vy = 0;
  combatStance = 0;
  private stanceW = 0;
  private phase = 0;
  private airW = 0;
  /** A full-body state clip (death, knockdown, climb...) overriding locomotion. */
  private state: { clip: Clip; time: number; w: number; target: number; fade: number } | null = null;
  private actions: ActionState[] = [];

  // Additive controls
  lookYaw = 0;
  lookPitch = 0;
  private lookYawS = 0;
  private lookPitchS = 0;
  aimPitch = 0;
  aimYaw = 0;
  aimW = 0;
  private aimWS = 0;
  lean = 0;
  private leanS = 0;
  breathe = 1;
  time = 0;
  hitJolt = 0;
  private hitDir = 1;
  /** Global time scale (hit stop, slow motion). */
  timeScale = 1;

  private bufA = new PoseBuf();
  private bufB = new PoseBuf();
  private qBase = new Float32Array(NB * 4);
  private qTmp = new Float32Array(NB * 4);
  private qOut = new Float32Array(NB * 4);
  private hipsOff = new THREE.Vector3();
  private hipsTmp = new THREE.Vector3();

  constructor(bones: Record<string, THREE.Bone>, loco: LocoSet, scale: number) {
    this.bones = BONE_NAMES.map((n) => bones[n]);
    this.restPos = this.bones.map((b) => b.position.clone());
    this.scale = scale;
    this.loco = loco;
  }

  /** Play a one-shot (or held) action layered over locomotion. */
  play(clip: Clip, opts: { fadeIn?: number; fadeOut?: number; speed?: number; mask?: keyof typeof MASKS | Float32Array; onEvent?: (name: string) => void; onEnd?: () => void; hold?: boolean; layer?: 'replace' | 'add' } = {}) {
    const mask = opts.mask instanceof Float32Array ? opts.mask : MASKS[opts.mask ?? 'full'];
    if (opts.layer !== 'add') {
      // Cross-fade out current actions.
      for (const a of this.actions) {
        if (!a.ending) {
          a.ending = true;
          a.fadeOut = Math.min(a.fadeOut, opts.fadeIn ?? 0.08);
          a.onEnd = undefined;
        }
      }
    }
    const st: ActionState = {
      clip,
      time: 0,
      speed: opts.speed ?? 1,
      weight: (opts.fadeIn ?? 0.08) <= 0 ? 1 : 0,
      fadeIn: opts.fadeIn ?? 0.08,
      fadeOut: opts.fadeOut ?? 0.15,
      mask,
      firedEvents: new Set(),
      onEvent: opts.onEvent,
      onEnd: opts.onEnd,
      ending: false,
      hold: !!opts.hold,
    };
    this.actions.push(st);
    return st;
  }

  stopActions(fade = 0.15) {
    for (const a of this.actions) {
      a.ending = true;
      a.fadeOut = fade;
      a.onEnd = undefined;
      a.onEvent = undefined;
    }
  }

  get actionActive(): boolean {
    return this.actions.some((a) => !a.ending);
  }

  currentAction(): string | null {
    const a = this.actions.find((x) => !x.ending);
    return a ? a.clip.name : null;
  }

  setState(clip: Clip | null, fade = 0.2) {
    if (clip) this.state = { clip, time: 0, w: this.state ? this.state.w : 0, target: 1, fade };
    else if (this.state) {
      this.state.target = 0;
      this.state.fade = fade;
    }
  }

  stateName(): string | null {
    return this.state && this.state.target > 0 ? this.state.clip.name : null;
  }

  jolt(dir = 1, amount = 1) {
    this.hitJolt = amount;
    this.hitDir = dir;
  }

  update(dtIn: number) {
    const dt = dtIn * this.timeScale;
    this.time += dt;
    const L = this.loco;

    // ---- Locomotion base
    const sp = this.speed;
    this.airW += ((this.grounded ? 0 : 1) - this.airW) * Math.min(1, dt * 12);
    this.stanceW += (this.combatStance - this.stanceW) * Math.min(1, dt * 4);
    // Phase advance from stride length so feet roughly match ground speed.
    let stride: number;
    if (sp < 2.2) stride = L.strideWalk;
    else if (sp < 5.5) stride = L.strideWalk + (L.strideRun - L.strideWalk) * smoothstep(2.2, 5.0, sp);
    else stride = L.strideRun + (L.strideSprint - L.strideRun) * smoothstep(5.5, 7.5, sp);
    this.phase = (this.phase + (sp / (stride * this.scale)) * dt) % 1;

    const base = this.bufA;
    const tmp = this.bufB;
    const idleClip = this.stanceW > 0.5 && L.combatIdle ? L.combatIdle : L.idle;
    idleClip.sample(this.time, base);
    poseToQuats(base, this.qBase);
    this.hipsOff.set(base.p[0], base.p[1], base.p[2]);
    if (this.stanceW > 0.01 && this.stanceW < 0.99 && L.combatIdle) {
      // Blend idle and combat idle.
      const other = idleClip === L.idle ? L.combatIdle : L.idle;
      other.sample(this.time, tmp);
      poseToQuats(tmp, this.qTmp);
      const w = idleClip === L.idle ? this.stanceW : 1 - this.stanceW;
      slerpInto(this.qBase, this.qTmp, w, FULL, this.qBase);
      this.hipsOff.lerp(this.hipsTmp.set(tmp.p[0], tmp.p[1], tmp.p[2]), w);
    }
    const blendClip = (clip: Clip, w: number) => {
      if (w <= 0.001) return;
      clip.sample(this.phase * clip.duration, tmp);
      poseToQuats(tmp, this.qTmp);
      slerpInto(this.qBase, this.qTmp, w, FULL, this.qBase);
      this.hipsOff.lerp(this.hipsTmp.set(tmp.p[0], tmp.p[1], tmp.p[2]), w);
    };
    const wWalk = smoothstep(0.15, 1.4, sp);
    blendClip(L.walk, wWalk);
    blendClip(L.run, smoothstep(2.2, 4.6, sp));
    blendClip(L.sprint, smoothstep(5.6, 7.4, sp));

    // ---- Airborne
    if (this.airW > 0.01) {
      const rising = clamp01(this.vy / 4);
      const clip = rising > 0.5 ? L.jump : L.fall;
      clip.sample(this.time, tmp);
      poseToQuats(tmp, this.qTmp);
      slerpInto(this.qBase, this.qTmp, this.airW, FULL, this.qBase);
      this.hipsOff.lerp(this.hipsTmp.set(tmp.p[0], tmp.p[1], tmp.p[2]), this.airW);
    }

    // ---- State override
    if (this.state) {
      const s = this.state;
      s.time += dt;
      s.w += Math.sign(s.target - s.w) * (dt / Math.max(0.01, s.fade));
      s.w = clamp01(s.w);
      if (s.w > 0.001) {
        s.clip.sample(s.time, tmp);
        poseToQuats(tmp, this.qTmp);
        slerpInto(this.qBase, this.qTmp, s.w, FULL, this.qBase);
        this.hipsOff.lerp(this.hipsTmp.set(tmp.p[0], tmp.p[1], tmp.p[2]), s.w);
      }
      if (s.target === 0 && s.w <= 0.001) this.state = null;
    }

    // ---- Actions
    this.qOut.set(this.qBase);
    for (let ai = 0; ai < this.actions.length; ai++) {
      const a = this.actions[ai];
      const prev = a.time;
      a.time += dt * a.speed;
      if (a.ending) a.weight -= dt / Math.max(0.01, a.fadeOut);
      else a.weight = Math.min(1, a.weight + dt / Math.max(0.01, a.fadeIn));
      // Events
      if (a.clip.events && a.onEvent) {
        for (let k = 0; k < a.clip.events.length; k++) {
          const ev = a.clip.events[k];
          if (!a.firedEvents.has(k) && prev <= ev.t && a.time >= ev.t) {
            a.firedEvents.add(k);
            a.onEvent(ev.name);
          }
        }
      }
      if (!a.clip.loop && !a.hold && !a.ending && a.time >= a.clip.duration) {
        a.ending = true;
        const cb = a.onEnd;
        a.onEnd = undefined;
        cb?.();
      }
      if (a.weight <= 0) continue;
      a.clip.sample(a.time, tmp);
      poseToQuats(tmp, this.qTmp);
      // Lower body follows locomotion when moving.
      const mask = a.mask === FULL && sp > 1.2 ? UPPER : a.mask;
      slerpInto(this.qOut, this.qTmp, a.weight, mask, this.qOut);
      const hw = a.weight * mask[BI.hips];
      if (hw > 0) this.hipsOff.lerp(this.hipsTmp.set(tmp.p[0], tmp.p[1], tmp.p[2]), hw);
    }
    this.actions = this.actions.filter((a) => !(a.ending && a.weight <= 0));

    // ---- Apply to bones with additive layers
    const k = Math.min(1, dt * 10);
    this.lookYawS += (clamp(this.lookYaw, -1.2, 1.2) - this.lookYawS) * k;
    this.lookPitchS += (clamp(this.lookPitch, -0.6, 0.6) - this.lookPitchS) * k;
    this.aimWS += (this.aimW - this.aimWS) * Math.min(1, dt * 12);
    this.leanS += (clamp(this.lean, -1, 1) - this.leanS) * Math.min(1, dt * 6);
    this.hitJolt = Math.max(0, this.hitJolt - dt * 5);
    const breath = Math.sin(this.time * 1.7) * this.breathe;

    for (let i = 0; i < NB; i++) {
      _q.set(this.qOut[i * 4], this.qOut[i * 4 + 1], this.qOut[i * 4 + 2], this.qOut[i * 4 + 3]);
      const name = BONE_NAMES[i];
      let ax = 0, ay = 0, az = 0;
      if (name === 'head') { ay += this.lookYawS * 0.6; ax += this.lookPitchS * 0.6; }
      else if (name === 'neck') { ay += this.lookYawS * 0.3; ax += this.lookPitchS * 0.3; }
      else if (name === 'chest') {
        ax += breath * 0.012 - this.hitJolt * 0.22;
        ay += this.aimWS * this.aimYaw * 0.55 + this.hitJolt * 0.1 * this.hitDir;
        ax += this.aimWS * this.aimPitch * 0.5;
        az += this.leanS * 0.06;
      } else if (name === 'spine') {
        ay += this.aimWS * this.aimYaw * 0.35;
        ax += this.aimWS * this.aimPitch * 0.3 - this.hitJolt * 0.1;
        az += this.leanS * 0.08;
      } else if (name === 'hips') az += this.leanS * 0.05;
      else if (name === 'clavicle_L' || name === 'clavicle_R') az += (name.endsWith('L') ? 1 : -1) * breath * 0.01;
      if (ax || ay || az) {
        _e.set(ax, ay, az, 'XYZ');
        _q2.setFromEuler(_e);
        _q.premultiply(_q2);
      }
      this.bones[i].quaternion.copy(_q);
    }
    const hips = this.bones[BI.hips];
    hips.position.copy(this.restPos[BI.hips]).addScaledVector(this.hipsOff, this.scale);
  }

  resetPhase() {
    this.phase = 0;
  }
}

/** Spring-driven secondary motion for a chain of bones (ponytail, cables). */
export class SpringChain {
  private bones: THREE.Bone[];
  private ang: THREE.Vector2[];
  private vel: THREE.Vector2[];
  private lastWorld = new THREE.Vector3();
  private lastVel = new THREE.Vector3();
  private head: THREE.Object3D;
  private init = false;
  constructor(bones: THREE.Bone[], head: THREE.Object3D) {
    this.bones = bones;
    this.head = head;
    this.ang = bones.map(() => new THREE.Vector2());
    this.vel = bones.map(() => new THREE.Vector2());
  }
  update(dt: number) {
    if (dt <= 0) return;
    const wp = new THREE.Vector3();
    this.head.getWorldPosition(wp);
    if (!this.init) {
      this.lastWorld.copy(wp);
      this.init = true;
    }
    const v = new THREE.Vector3().subVectors(wp, this.lastWorld).divideScalar(Math.max(dt, 1e-3));
    const acc = new THREE.Vector3().subVectors(v, this.lastVel).divideScalar(Math.max(dt, 1e-3));
    acc.clampLength(0, 60);
    this.lastWorld.copy(wp);
    this.lastVel.copy(v);
    // Into head-local space
    const q = new THREE.Quaternion();
    this.head.getWorldQuaternion(q);
    const local = acc.clone().applyQuaternion(q.invert());
    const lv = v.clone().applyQuaternion(this.head.getWorldQuaternion(new THREE.Quaternion()).invert());
    for (let i = 0; i < this.bones.length; i++) {
      const a = this.ang[i], vv = this.vel[i];
      const stiff = 60 - i * 10, damp = 6;
      // Hair swings opposite to acceleration and trails velocity.
      const tx = clamp(local.z * 0.012 + lv.z * 0.05, -0.9, 0.9);
      const tz = clamp(-local.x * 0.012 - lv.x * 0.04, -0.7, 0.7);
      vv.x += (stiff * (tx - a.x) - damp * vv.x) * dt;
      vv.y += (stiff * (tz - a.y) - damp * vv.y) * dt;
      a.x += vv.x * dt;
      a.y += vv.y * dt;
      this.bones[i].rotation.set(a.x * (0.5 + i * 0.2), 0, a.y * (0.5 + i * 0.2));
    }
  }
}
