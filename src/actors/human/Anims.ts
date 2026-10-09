import { FnClip, KeyClip, mirrorPose, sym, type Clip, type LocoSet, type PoseBuf, type PoseSpec, BI } from './Animator';

// Procedural animation library for the humanoid rig.
// Conventions (rest = A-pose, bones world-aligned, character faces +Z, left = +X):
//  thigh/upperarm x<0 swings forward; shin x>0 bends knee; forearm x<0 bends elbow;
//  spine/chest x>0 bends forward, y>0 twists left; head x>0 looks down;
//  upperarm_L z>0 raises arm out to the side (mirrored for R via `sym`).

export type AnimStyle = 'male' | 'female' | 'robot' | 'heavy';

interface CycleParams {
  stance: number; thighFwd: number; thighBack: number; kneeStance: number; kneeSwing: number;
  footStrike: number; footPush: number; bob: number; bobBase: number; bobOffset: number;
  hipYaw: number; hipRoll: number; spineLean: number; chestTwist: number;
  armMid: number; armSwing: number; elbowBase: number; elbowSwing: number; armZ: number; headComp: number;
}

const bump = (q: number, c: number, w: number) => {
  let d = Math.abs(q - c);
  d = Math.min(d, 1 - d);
  return Math.exp(-(d / w) * (d / w));
};

function setE(out: PoseBuf, bone: keyof typeof BI, x: number, y: number, z: number) {
  const i = BI[bone] * 3;
  out.e[i] = x; out.e[i + 1] = y; out.e[i + 2] = z;
}

function gait(p: CycleParams) {
  return (ph: number, out: PoseBuf) => {
    const C = Math.cos, TAU = Math.PI * 2;
    for (const side of ['L', 'R'] as const) {
      const q = side === 'L' ? ph : (ph + 0.5) % 1;
      // Stance occupies `stance` of the cycle; warp so the thigh moves back slowly in stance and forward fast in swing.
      const qw = q < p.stance ? (q / p.stance) * 0.5 : 0.5 + ((q - p.stance) / (1 - p.stance)) * 0.5;
      const mid = (p.thighBack - p.thighFwd) / 2, amp = (p.thighFwd + p.thighBack) / 2;
      const thigh = mid - amp * C(TAU * qw);
      const knee = 4 + p.kneeStance * bump(q, p.stance * 0.22, 0.09) + p.kneeSwing * bump(q, p.stance + (1 - p.stance) * 0.38, 0.13);
      const foot = -p.footStrike * bump(q, 0.0, 0.06) + p.footPush * bump(q, p.stance - 0.03, 0.07) - 8 * bump(q, p.stance + (1 - p.stance) * 0.55, 0.1);
      const sgn = side === 'L' ? 1 : -1;
      setE(out, `thigh_${side}`, thigh, 0, sgn * 1.5);
      setE(out, `shin_${side}`, knee, 0, 0);
      setE(out, `foot_${side}`, foot, 0, 0);
      // Arms swing opposite to the same-side leg.
      const aq = side === 'L' ? ph : (ph + 0.5) % 1;
      const arm = p.armMid + p.armSwing * C(TAU * aq);
      const fwd = Math.max(0, -C(TAU * aq));
      setE(out, `upperarm_${side}`, arm, sgn * 4, sgn * p.armZ);
      setE(out, `forearm_${side}`, -(p.elbowBase + p.elbowSwing * fwd), sgn * -6, 0);
      setE(out, `hand_${side}`, -6, 0, sgn * -4);
      setE(out, `clavicle_${side}`, 0, 0, sgn * -2);
    }
    const hipYaw = -p.hipYaw * C(TAU * ph);
    const chestTwist = p.chestTwist * C(TAU * ph);
    setE(out, 'hips', 0, hipYaw, p.hipRoll * Math.sin(TAU * ph));
    setE(out, 'spine', p.spineLean * 0.6, chestTwist * 0.4, 0);
    setE(out, 'chest', p.spineLean * 0.4, chestTwist * 0.6, -p.hipRoll * 0.5 * Math.sin(TAU * ph));
    setE(out, 'neck', -p.spineLean * 0.4, 0, 0);
    setE(out, 'head', -p.spineLean * 0.3 + 2, -(hipYaw + chestTwist) * p.headComp, 0);
    out.p[1] = p.bobBase - p.bob * C(2 * TAU * (ph - p.bobOffset));
  };
}

const WALK: Record<AnimStyle, CycleParams> = {
  male: { stance: 0.6, thighFwd: 24, thighBack: 15, kneeStance: 14, kneeSwing: 58, footStrike: 12, footPush: 18, bob: 0.016, bobBase: -0.012, bobOffset: 0.0, hipYaw: 6, hipRoll: 3, spineLean: 3, chestTwist: 7, armMid: 2, armSwing: 15, elbowBase: 14, elbowSwing: 12, armZ: -9, headComp: 0.5 },
  female: { stance: 0.6, thighFwd: 22, thighBack: 15, kneeStance: 12, kneeSwing: 56, footStrike: 12, footPush: 18, bob: 0.014, bobBase: -0.01, bobOffset: 0.0, hipYaw: 8, hipRoll: 4.5, spineLean: 2, chestTwist: 6, armMid: 2, armSwing: 13, elbowBase: 16, elbowSwing: 10, armZ: -11, headComp: 0.6 },
  robot: { stance: 0.62, thighFwd: 22, thighBack: 14, kneeStance: 16, kneeSwing: 50, footStrike: 6, footPush: 10, bob: 0.03, bobBase: -0.04, bobOffset: 0.0, hipYaw: 4, hipRoll: 5, spineLean: 8, chestTwist: 4, armMid: 0, armSwing: 10, elbowBase: 24, elbowSwing: 6, armZ: -4, headComp: 0.3 },
  heavy: { stance: 0.64, thighFwd: 20, thighBack: 12, kneeStance: 18, kneeSwing: 44, footStrike: 4, footPush: 8, bob: 0.05, bobBase: -0.06, bobOffset: 0.0, hipYaw: 5, hipRoll: 6, spineLean: 12, chestTwist: 5, armMid: -5, armSwing: 9, elbowBase: 30, elbowSwing: 5, armZ: 2, headComp: 0.3 },
};
const RUN: Record<AnimStyle, CycleParams> = {
  male: { stance: 0.38, thighFwd: 48, thighBack: 26, kneeStance: 30, kneeSwing: 105, footStrike: 6, footPush: 28, bob: 0.034, bobBase: -0.035, bobOffset: 0.12, hipYaw: 10, hipRoll: 4, spineLean: 11, chestTwist: 12, armMid: -4, armSwing: 34, elbowBase: 74, elbowSwing: 16, armZ: -6, headComp: 0.6 },
  female: { stance: 0.38, thighFwd: 46, thighBack: 26, kneeStance: 28, kneeSwing: 108, footStrike: 6, footPush: 28, bob: 0.03, bobBase: -0.03, bobOffset: 0.12, hipYaw: 11, hipRoll: 5, spineLean: 9, chestTwist: 11, armMid: -4, armSwing: 32, elbowBase: 78, elbowSwing: 14, armZ: -8, headComp: 0.6 },
  robot: { stance: 0.42, thighFwd: 40, thighBack: 22, kneeStance: 26, kneeSwing: 85, footStrike: 4, footPush: 18, bob: 0.05, bobBase: -0.06, bobOffset: 0.12, hipYaw: 6, hipRoll: 6, spineLean: 16, chestTwist: 6, armMid: 6, armSwing: 22, elbowBase: 50, elbowSwing: 8, armZ: -2, headComp: 0.4 },
  heavy: { stance: 0.45, thighFwd: 34, thighBack: 20, kneeStance: 26, kneeSwing: 70, footStrike: 2, footPush: 12, bob: 0.08, bobBase: -0.08, bobOffset: 0.12, hipYaw: 6, hipRoll: 7, spineLean: 18, chestTwist: 6, armMid: 0, armSwing: 18, elbowBase: 40, elbowSwing: 6, armZ: 3, headComp: 0.3 },
};
const SPRINT: Record<AnimStyle, CycleParams> = {
  male: { ...RUN.male, stance: 0.33, thighFwd: 62, thighBack: 30, kneeSwing: 125, kneeStance: 34, footPush: 32, bob: 0.04, bobBase: -0.05, hipYaw: 12, spineLean: 18, chestTwist: 14, armSwing: 46, elbowBase: 84, elbowSwing: 10 },
  female: { ...RUN.female, stance: 0.33, thighFwd: 60, thighBack: 30, kneeSwing: 128, kneeStance: 32, footPush: 32, bob: 0.036, bobBase: -0.045, hipYaw: 13, spineLean: 16, chestTwist: 13, armSwing: 44, elbowBase: 86, elbowSwing: 10 },
  robot: { ...RUN.robot },
  heavy: { ...RUN.heavy },
};

// ------------------------------------------------------------------ Static poses

const LEGS_STANCE: PoseSpec = { thigh_L: [-26, 6, 6], shin_L: [30, 0, 0], foot_L: [-4, -6, 0], thigh_R: [14, -8, -8], shin_R: [24, 0, 0], foot_R: [-14, 8, 0] };

function idlePose(style: AnimStyle, shift: number): PoseSpec {
  const fem = style === 'female';
  return {
    hipsPos: [shift * 0.012, -0.006 - Math.abs(shift) * 0.004, 0],
    hips: [0, shift * 2, shift * 2.2],
    spine: [2, 0, -shift * 1.2],
    chest: [-1.5, 0, -shift * 1],
    neck: [-3, 0, 0],
    head: [3, -shift * 3, shift * 1.5],
    ...sym({
      clavicle_S: [0, 0, -2],
      upperarm_S: [-1, 6, fem ? -12 : -10],
      forearm_S: [fem ? -16 : -13, -8, 0],
      hand_S: [-6, 0, -4],
      foot_S: [-1, fem ? 5 : 4, 0],
    }),
    thigh_L: [-1 + (shift > 0 ? 0 : -3), 0, fem ? -1 : 0.5 + shift * 1.5],
    shin_L: [shift > 0 ? 2 : 7, 0, 0],
    thigh_R: [-1 + (shift > 0 ? -3 : 0), 0, fem ? 1 : -0.5 + shift * 1.5],
    shin_R: [shift > 0 ? 7 : 2, 0, 0],
  };
}

function combatIdle(style: AnimStyle): PoseSpec {
  if (style === 'female') {
    return {
      hipsPos: [0, -0.05, 0],
      hips: [0, -8, 0],
      spine: [7, 4, 0],
      chest: [3, 6, 0],
      neck: [-4, 0, 0],
      head: [-3, -2, 0],
      upperarm_L: [-34, -30, 2], forearm_L: [-70, 0, 0], hand_L: [-8, 0, 0],
      upperarm_R: [-22, 34, -6], forearm_R: [-76, 0, 0], hand_R: [-10, 0, 0],
      ...LEGS_STANCE,
    };
  }
  return {
    hipsPos: [0, -0.06, 0],
    hips: [0, -10, 0],
    spine: [8, 5, 0],
    chest: [4, 8, 0],
    neck: [-4, 0, 0],
    head: [-3, -3, 0],
    upperarm_L: [-30, -34, 0], forearm_L: [-88, 0, 0], hand_L: [-10, 0, 0],
    upperarm_R: [-16, 26, -10], forearm_R: [-62, 0, 0], hand_R: [-6, 0, -8],
    ...LEGS_STANCE,
  };
}

const merge = (...ps: PoseSpec[]): PoseSpec => Object.assign({}, ...ps);

// ------------------------------------------------------------------ Library

export interface AnimLib {
  loco: LocoSet;
  clips: Record<string, Clip>;
}

const cache = new Map<AnimStyle, AnimLib>();

export function getAnimLib(style: AnimStyle): AnimLib {
  const hit = cache.get(style);
  if (hit) return hit;
  const lib = build(style);
  cache.set(style, lib);
  return lib;
}

function build(style: AnimStyle): AnimLib {
  const fem = style === 'female';
  const idle = new KeyClip('idle', [
    { t: 0, pose: idlePose(style, 1) },
    { t: 2.2, pose: idlePose(style, 0.85) },
    { t: 4.0, pose: idlePose(style, -0.9) },
    { t: 6.2, pose: idlePose(style, -1) },
  ], 8, true);
  const cIdle = combatIdle(style);
  const combat = new KeyClip('combat_idle', [
    { t: 0, pose: cIdle },
    { t: 0.9, pose: merge(cIdle, { hipsPos: [0, -0.07, 0], spine: [9, 5, 0] }) },
  ], 1.8, true);

  const walk = new FnClip('walk', 1, true, gait(WALK[style]));
  const run = new FnClip('run', 1, true, gait(RUN[style]));
  const sprint = new FnClip('sprint', 1, true, gait(SPRINT[style]));

  const jumpPose: PoseSpec = merge(
    { spine: [6, 0, 0], chest: [-4, 0, 0], head: [-4, 0, 0] },
    sym({ upperarm_S: [-34, 0, 14], forearm_S: [-44, 0, 0] }),
    { thigh_L: [-52, 0, 4], shin_L: [72, 0, 0], foot_L: [22, 0, 0], thigh_R: [6, 0, -4], shin_R: [46, 0, 0], foot_R: [32, 0, 0] },
  );
  const fallA: PoseSpec = merge(
    { spine: [-2, 0, 0], chest: [-4, 0, 0], head: [6, 0, 0] },
    sym({ upperarm_S: [-18, 0, 30], forearm_S: [-36, 0, 0], hand_S: [0, 0, 10] }),
    { thigh_L: [-28, 0, 4], shin_L: [36, 0, 0], foot_L: [10, 0, 0], thigh_R: [-10, 0, -4], shin_R: [52, 0, 0], foot_R: [16, 0, 0] },
  );
  const fallB: PoseSpec = merge(fallA, sym({ upperarm_S: [-24, 0, 36] }), { thigh_L: [-22, 0, 4], thigh_R: [-16, 0, -4] });
  const jump = new KeyClip('jump', [{ t: 0, pose: jumpPose }], 1, true);
  const fall = new KeyClip('fall', [{ t: 0, pose: fallA }, { t: 0.4, pose: fallB }], 0.8, true);

  const loco: LocoSet = {
    idle,
    walk,
    run,
    sprint,
    jump,
    fall,
    combatIdle: combat,
    strideWalk: style === 'heavy' ? 1.9 : fem ? 1.5 : 1.6,
    strideRun: style === 'heavy' ? 3.4 : fem ? 3.2 : 3.4,
    strideSprint: fem ? 4.3 : 4.6,
  };

  const clips: Record<string, Clip> = {};
  const add = (c: Clip) => (clips[c.name] = c);
  const stanceLunge = (fwd: number): PoseSpec => ({
    hipsPos: [0, -0.06, fwd],
    thigh_L: [-34, 4, 6], shin_L: [36, 0, 0], foot_L: [-2, -4, 0],
    thigh_R: [18, -6, -8], shin_R: [26, 0, 0], foot_R: [-16, 6, 0],
  });

  add(new KeyClip('land', [
    { t: 0, pose: merge(sym({ thigh_S: [-30, 0, 4], shin_S: [50, 0, 0], foot_S: [-18, 0, 0], upperarm_S: [-20, 0, 24], forearm_S: [-30, 0, 0] }), { hipsPos: [0, -0.08, 0], spine: [10, 0, 0] }) },
    { t: 0.1, pose: merge(sym({ thigh_S: [-46, 0, 5], shin_S: [82, 0, 0], foot_S: [-34, 0, 0], upperarm_S: [-26, 0, 26], forearm_S: [-36, 0, 0] }), { hipsPos: [0, -0.16, 0], spine: [20, 0, 0], head: [-10, 0, 0] }) },
    { t: 0.38, pose: merge(idlePose(style, 0), {}) },
  ], 0.38, false));

  // ---- Kael: Light combo (L1, L2, L3) and heavy finisher; blade projected from the right forearm.
  const guardL: PoseSpec = { upperarm_L: [-32, -34, 0], forearm_L: [-90, 0, 0], hand_L: [-10, 0, 0] };
  add(new KeyClip('k_light1', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.09, pose: merge(stanceLunge(0.0), guardL, { hips: [0, -14, 0], spine: [6, -14, 0], chest: [4, -34, 2], head: [0, 30, 0], upperarm_R: [0, -24, -70], forearm_R: [-52, 0, 0], hand_R: [0, 0, -12] }) },
    { t: 0.17, pose: merge(stanceLunge(0.1), guardL, { hips: [0, 6, 0], spine: [9, 4, 0], chest: [8, 8, 0], head: [-2, -8, 0], upperarm_R: [0, 82, -74], forearm_R: [-14, 0, 0], hand_R: [0, 0, 0] }) },
    { t: 0.26, pose: merge(stanceLunge(0.12), guardL, { hips: [0, 16, 0], spine: [9, 14, 0], chest: [10, 36, -3], head: [-2, -40, 0], upperarm_R: [0, 138, -70], forearm_R: [-28, 0, 0], hand_R: [0, 0, 10] }) },
    { t: 0.52, pose: merge(cIdle) },
  ], 0.52, false, [{ t: 0.12, name: 'hit_start' }, { t: 0.25, name: 'hit_end' }, { t: 0.2, name: 'combo' }]));
  add(new KeyClip('k_light2', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.09, pose: merge(stanceLunge(0.02), guardL, { hips: [0, 12, 0], spine: [6, 10, 0], chest: [5, 30, 0], head: [0, -28, 0], upperarm_R: [0, 152, -62], forearm_R: [-72, 0, 0], hand_R: [0, 0, 14] }) },
    { t: 0.17, pose: merge(stanceLunge(0.12), guardL, { hips: [0, -4, 0], spine: [8, -4, 0], chest: [8, -8, 0], upperarm_R: [0, 72, -76], forearm_R: [-10, 0, 0] }) },
    { t: 0.27, pose: merge(stanceLunge(0.14), guardL, { hips: [0, -16, 0], spine: [8, -14, 0], chest: [6, -38, 0], head: [0, 34, 0], upperarm_R: [0, -14, -72], forearm_R: [-22, 0, 0], hand_R: [0, 0, -12] }) },
    { t: 0.54, pose: merge(cIdle) },
  ], 0.54, false, [{ t: 0.12, name: 'hit_start' }, { t: 0.26, name: 'hit_end' }, { t: 0.21, name: 'combo' }]));
  add(new KeyClip('k_light3', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.13, pose: merge(stanceLunge(-0.02), guardL, { hipsPos: [0, -0.15, 0], spine: [22, -12, 0], chest: [8, -18, 0], upperarm_R: [24, 30, -34], forearm_R: [-34, 0, 0] }) },
    { t: 0.23, pose: merge(stanceLunge(0.16), guardL, { hipsPos: [0, 0.03, 0.16], spine: [-6, 10, 0], chest: [-10, 16, 0], head: [-6, -10, 0], upperarm_R: [-150, 30, -26], forearm_R: [-12, 0, 0] }) },
    { t: 0.33, pose: merge(stanceLunge(0.18), guardL, { hipsPos: [0, 0.0, 0.18], spine: [4, 10, 0], chest: [2, 14, 0], upperarm_R: [-172, 10, -16], forearm_R: [-20, 0, 0] }) },
    { t: 0.62, pose: merge(cIdle) },
  ], 0.62, false, [{ t: 0.16, name: 'hit_start' }, { t: 0.32, name: 'hit_end' }, { t: 0.28, name: 'combo' }]));
  add(new KeyClip('k_heavy', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.16, pose: merge(sym({ thigh_S: [-48, 0, 6], shin_S: [86, 0, 0], foot_S: [-30, 0, 0], upperarm_S: [34, 0, 22], forearm_S: [-40, 0, 0] }), { hipsPos: [0, -0.2, -0.04], spine: [28, 0, 0], chest: [10, 0, 0], head: [-18, 0, 0] }) },
    { t: 0.32, pose: merge(sym({ thigh_S: [-30, 0, 4], shin_S: [40, 0, 0], foot_S: [20, 0, 0], upperarm_S: [-165, 0, 8], forearm_S: [-32, 0, 0] }), { hipsPos: [0, 0.28, 0.12], spine: [-12, 0, 0], chest: [-8, 0, 0], head: [-8, 0, 0] }) },
    { t: 0.43, pose: merge({ thigh_L: [-70, 0, 6], shin_L: [92, 0, 0], foot_L: [-20, 0, 0], thigh_R: [14, 0, -6], shin_R: [104, 0, 0], foot_R: [30, 0, 0] }, sym({ upperarm_S: [-62, 0, 8], forearm_S: [-8, 0, 0] }), { hipsPos: [0, -0.3, 0.2], spine: [34, 0, 0], chest: [16, 0, 0], head: [-26, 0, 0] }) },
    { t: 0.62, pose: merge({ thigh_L: [-64, 0, 6], shin_L: [88, 0, 0], foot_L: [-20, 0, 0], thigh_R: [10, 0, -6], shin_R: [100, 0, 0], foot_R: [30, 0, 0] }, sym({ upperarm_S: [-58, 0, 10], forearm_S: [-12, 0, 0] }), { hipsPos: [0, -0.28, 0.2], spine: [30, 0, 0], chest: [14, 0, 0], head: [-24, 0, 0] }) },
    { t: 0.92, pose: merge(cIdle) },
  ], 0.92, false, [{ t: 0.36, name: 'hit_start' }, { t: 0.43, name: 'impact' }, { t: 0.5, name: 'hit_end' }]));

  // ---- Lyra: Quick combo (Q1, Q2) and heavy spin; twin phase-blades from both gloves.
  const guardR: PoseSpec = { upperarm_R: [-26, 32, -4], forearm_R: [-82, 0, 0], hand_R: [-10, 0, 0] };
  add(new KeyClip('l_quick1', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.06, pose: merge(stanceLunge(0.0), guardR, { hips: [0, 10, 0], chest: [4, 24, 0], head: [0, -24, 0], upperarm_L: [12, 0, 22], forearm_L: [-96, 0, 0] }) },
    { t: 0.13, pose: merge(stanceLunge(0.14), guardR, { hips: [0, -12, 0], spine: [8, -10, 0], chest: [6, -24, 0], head: [0, 26, 0], upperarm_L: [-86, 0, 4], forearm_L: [-4, 0, 0], hand_L: [0, 0, 0] }) },
    { t: 0.21, pose: merge(stanceLunge(0.16), guardR, { hips: [0, -14, 0], chest: [6, -30, 0], upperarm_L: [0, -72, 74], forearm_L: [-14, 0, 0] }) },
    { t: 0.38, pose: merge(cIdle) },
  ], 0.38, false, [{ t: 0.08, name: 'hit_start' }, { t: 0.2, name: 'hit_end' }, { t: 0.16, name: 'combo' }]));
  add(new KeyClip('l_quick2', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.07, pose: merge(stanceLunge(0.02), { upperarm_L: [-30, -8, 8], forearm_L: [-80, 0, 0] }, { hips: [0, -12, 0], chest: [4, -30, 0], head: [0, 28, 0], upperarm_R: [0, -24, -70], forearm_R: [-48, 0, 0] }) },
    { t: 0.14, pose: merge(stanceLunge(0.14), { upperarm_L: [-30, -8, 8], forearm_L: [-80, 0, 0] }, { hips: [0, 8, 0], chest: [8, 10, 0], upperarm_R: [0, 84, -74], forearm_R: [-12, 0, 0] }) },
    { t: 0.22, pose: merge(stanceLunge(0.16), { upperarm_L: [-30, -8, 8], forearm_L: [-80, 0, 0] }, { hips: [0, 18, 0], chest: [10, 38, -3], head: [0, -36, 0], upperarm_R: [0, 140, -70], forearm_R: [-26, 0, 0] }) },
    { t: 0.4, pose: merge(cIdle) },
  ], 0.4, false, [{ t: 0.09, name: 'hit_start' }, { t: 0.21, name: 'hit_end' }, { t: 0.17, name: 'combo' }]));
  const spinArms = sym({ upperarm_S: [-4, 0, 72], forearm_S: [-10, 0, 0], hand_S: [0, 0, 0] });
  add(new KeyClip('l_heavy', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.12, pose: merge(stanceLunge(-0.02), sym({ upperarm_S: [20, 0, 30], forearm_S: [-80, 0, 0] }), { hipsPos: [0, -0.12, 0], root: [0, 30, 0], spine: [16, 0, 0], chest: [8, 30, 0] }) },
    { t: 0.22, pose: merge(spinArms, sym({ thigh_S: [-20, 0, 6], shin_S: [30, 0, 0] }), { hipsPos: [0, -0.05, 0.1], root: [0, -60, 0], spine: [8, 0, 0] }) },
    { t: 0.32, pose: merge(spinArms, sym({ thigh_S: [-20, 0, 6], shin_S: [30, 0, 0] }), { hipsPos: [0, -0.04, 0.15], root: [0, -180, 0], spine: [8, 0, 0] }) },
    { t: 0.42, pose: merge(spinArms, sym({ thigh_S: [-24, 0, 6], shin_S: [34, 0, 0] }), { hipsPos: [0, -0.05, 0.18], root: [0, -300, 0], spine: [10, 0, 0] }) },
    { t: 0.5, pose: merge(stanceLunge(0.18), sym({ upperarm_S: [-40, 0, 40], forearm_S: [-20, 0, 0] }), { root: [0, -360, 0], spine: [14, 0, 0] }) },
    { t: 0.78, pose: merge(cIdle, { root: [0, -360, 0] }) },
  ], 0.78, false, [{ t: 0.16, name: 'hit_start' }, { t: 0.32, name: 'impact' }, { t: 0.46, name: 'hit_end' }]));

  // ---- Movement abilities
  add(new KeyClip('dash', [
    { t: 0, pose: merge(sym({ upperarm_S: [40, 0, 14], forearm_S: [-30, 0, 0] }), { spine: [26, 0, 0], chest: [8, 0, 0], head: [-22, 0, 0], thigh_L: [-34, 0, 4], shin_L: [44, 0, 0], thigh_R: [30, 0, -4], shin_R: [60, 0, 0], foot_R: [30, 0, 0], hipsPos: [0, -0.1, 0] }) },
    { t: 0.22, pose: merge(sym({ upperarm_S: [44, 0, 18], forearm_S: [-24, 0, 0] }), { spine: [22, 0, 0], head: [-20, 0, 0], thigh_L: [-40, 0, 4], shin_L: [50, 0, 0], thigh_R: [34, 0, -4], shin_R: [64, 0, 0], foot_R: [30, 0, 0], hipsPos: [0, -0.12, 0] }) },
    { t: 0.36, pose: merge(cIdle) },
  ], 0.36, false));
  add(new KeyClip('phase_step', [
    { t: 0, pose: merge(sym({ upperarm_S: [-10, 0, 40], forearm_S: [-40, 0, 0], thigh_S: [-40, 0, 10], shin_S: [70, 0, 0], foot_S: [-20, 0, 0] }), { spine: [16, 0, 0], hipsPos: [0, -0.2, 0] }) },
    { t: 0.18, pose: merge(sym({ upperarm_S: [-14, 0, 44], forearm_S: [-36, 0, 0], thigh_S: [-36, 0, 10], shin_S: [62, 0, 0], foot_S: [-20, 0, 0] }), { spine: [14, 0, 0], hipsPos: [0, -0.16, 0] }) },
    { t: 0.3, pose: merge(cIdle) },
  ], 0.3, false));

  // ---- Kael: Aether Pulse (ground strike) and Core Break (ultimate leap slam)
  const kneel: PoseSpec = { thigh_L: [-74, 0, 8], shin_L: [96, 0, 0], foot_L: [-22, 0, 0], thigh_R: [8, 0, -8], shin_R: [104, 0, 0], foot_R: [40, 0, 0] };
  add(new KeyClip('k_pulse', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.16, pose: merge(LEGS_STANCE, { hipsPos: [0, -0.08, 0], spine: [-4, 0, 0], chest: [-8, -10, 0], upperarm_R: [-62, 34, -16], forearm_R: [-118, 0, 0], hand_R: [-20, 0, 0], upperarm_L: [-20, 0, 26], forearm_L: [-30, 0, 0] }) },
    { t: 0.3, pose: merge(kneel, { hipsPos: [0, -0.34, 0.06], spine: [32, 0, 0], chest: [12, 0, 0], head: [-26, 0, 0], upperarm_R: [-46, 0, -12], forearm_R: [-6, 0, 0], upperarm_L: [-10, 0, 40], forearm_L: [-20, 0, 0] }) },
    { t: 0.55, pose: merge(kneel, { hipsPos: [0, -0.33, 0.06], spine: [28, 0, 0], chest: [10, 0, 0], head: [-24, 0, 0], upperarm_R: [-44, 0, -12], forearm_R: [-8, 0, 0], upperarm_L: [-12, 0, 40], forearm_L: [-22, 0, 0] }) },
    { t: 0.85, pose: merge(cIdle) },
  ], 0.85, false, [{ t: 0.3, name: 'pulse' }]));
  add(new KeyClip('k_ult', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.28, pose: merge(sym({ thigh_S: [-56, 0, 6], shin_S: [96, 0, 0], foot_S: [-30, 0, 0], upperarm_S: [-30, 60, -6], forearm_S: [-120, 0, 0] }), { hipsPos: [0, -0.26, 0], spine: [20, 0, 0], head: [-10, 0, 0] }) },
    { t: 0.55, pose: merge(sym({ thigh_S: [-20, 0, 4], shin_S: [36, 0, 0], foot_S: [30, 0, 0], upperarm_S: [-170, 0, 14], forearm_S: [-20, 0, 0] }), { hipsPos: [0, 0.9, 0.2], spine: [-14, 0, 0], chest: [-10, 0, 0], head: [-14, 0, 0] }) },
    { t: 0.78, pose: merge(sym({ thigh_S: [-20, 0, 4], shin_S: [40, 0, 0], foot_S: [20, 0, 0], upperarm_S: [-175, 0, 10], forearm_S: [-30, 0, 0] }), { hipsPos: [0, 0.8, 0.3], spine: [-10, 0, 0], head: [-10, 0, 0] }) },
    { t: 0.9, pose: merge(kneel, { hipsPos: [0, -0.34, 0.35], spine: [36, 0, 0], chest: [14, 0, 0], head: [-26, 0, 0], upperarm_R: [-50, 0, -10], forearm_R: [-4, 0, 0], upperarm_L: [-50, 0, 10], forearm_L: [-4, 0, 0] }) },
    { t: 1.25, pose: merge(kneel, { hipsPos: [0, -0.33, 0.35], spine: [32, 0, 0], head: [-20, 0, 0], upperarm_R: [-48, 0, -14], upperarm_L: [-48, 0, 14] }) },
    { t: 1.6, pose: merge(cIdle) },
  ], 1.6, false, [{ t: 0.9, name: 'impact' }]));

  // ---- Lyra: Echo Sight (touch harness) and Resonance Burst (ultimate)
  add(new KeyClip('l_echo', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.22, pose: merge(idlePose(style, 0), { spine: [-2, 0, 0], chest: [-6, 0, 0], head: [-12, 0, 0], upperarm_R: [-48, 66, -4], forearm_R: [-118, 0, 0], hand_R: [-20, 0, 0], upperarm_L: [-46, 0, 34], forearm_L: [-18, 0, 0], hand_L: [-30, 0, 0] }) },
    { t: 0.5, pose: merge(idlePose(style, 0), { spine: [-2, 0, 0], chest: [-6, 0, 0], head: [-10, 20, 0], upperarm_R: [-48, 66, -4], forearm_R: [-118, 0, 0], hand_R: [-20, 0, 0], upperarm_L: [-50, 0, 40], forearm_L: [-16, 0, 0], hand_L: [-30, 0, 0] }) },
    { t: 0.75, pose: merge(cIdle) },
  ], 0.75, false, [{ t: 0.24, name: 'echo' }]));
  add(new KeyClip('l_ult', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.3, pose: merge(sym({ upperarm_S: [-60, -70, -14], forearm_S: [-110, 0, 0], thigh_S: [-40, 0, 8], shin_S: [70, 0, 0], foot_S: [-22, 0, 0] }), { hipsPos: [0, -0.18, 0], spine: [20, 0, 0], chest: [10, 0, 0], head: [-14, 0, 0] }) },
    { t: 0.6, pose: merge(sym({ upperarm_S: [-30, 0, 86], forearm_S: [-4, 0, 0], hand_S: [0, 0, 20], thigh_S: [-12, 0, 8], shin_S: [12, 0, 0] }), { hipsPos: [0, 0.05, 0], spine: [-10, 0, 0], chest: [-14, 0, 0], head: [-24, 0, 0] }) },
    { t: 0.8, pose: merge(sym({ upperarm_S: [-20, 0, 80], forearm_S: [-6, 0, 0], thigh_S: [-12, 0, 8], shin_S: [14, 0, 0] }), { hipsPos: [0, 0.02, 0], root: [0, -180, 0], spine: [-6, 0, 0], chest: [-8, 0, 0], head: [-14, 0, 0] }) },
    { t: 1.0, pose: merge(sym({ upperarm_S: [-20, 0, 78], forearm_S: [-6, 0, 0], thigh_S: [-12, 0, 8], shin_S: [14, 0, 0] }), { root: [0, -360, 0], spine: [-4, 0, 0], head: [-8, 0, 0] }) },
    { t: 1.35, pose: merge(cIdle, { root: [0, -360, 0] }) },
  ], 1.35, false, [{ t: 0.6, name: 'impact' }]));

  // ---- Aether bolt (ranged): Kael fires from the right forearm, Lyra from the left harness.
  const aimR: PoseSpec = merge(idlePose(style, 0), { hipsPos: [0, -0.03, 0], spine: [4, -10, 0], chest: [2, -16, 0], head: [0, 24, 0], upperarm_R: [0, 102, -78], forearm_R: [-4, 0, 0], hand_R: [-6, 0, 0], upperarm_L: [-40, -10, 6], forearm_L: [-92, 0, 0], thigh_L: [-12, 0, 4], shin_L: [12, 0, 0], thigh_R: [10, 0, -4], shin_R: [10, 0, 0] });
  add(new KeyClip('aim_r', [{ t: 0, pose: aimR }], 1, true));
  add(new KeyClip('fire_r', [
    { t: 0, pose: aimR },
    { t: 0.05, pose: merge(aimR, { chest: [-6, -14, 0], upperarm_R: [-10, 100, -80], forearm_R: [-18, 0, 0] }) },
    { t: 0.3, pose: aimR },
  ], 0.3, false, [{ t: 0.02, name: 'fire' }]));
  const aimL = mirrorPose(aimR);
  add(new KeyClip('aim_l', [{ t: 0, pose: aimL }], 1, true));
  add(new KeyClip('fire_l', [
    { t: 0, pose: aimL },
    { t: 0.05, pose: merge(aimL, mirrorPose({ chest: [-6, -14, 0], upperarm_R: [-10, 100, -80], forearm_R: [-18, 0, 0] })) },
    { t: 0.3, pose: aimL },
  ], 0.3, false, [{ t: 0.02, name: 'fire' }]));

  // ---- Reactions
  add(new KeyClip('hit', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.06, pose: merge(cIdle, { hipsPos: [0, -0.05, -0.06], spine: [-10, 6, 0], chest: [-14, 10, 0], head: [-16, 0, 0] }, sym({ upperarm_S: [-20, 0, 26], forearm_S: [-50, 0, 0] })) },
    { t: 0.3, pose: merge(cIdle) },
  ], 0.3, false));
  add(new KeyClip('stagger', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.1, pose: merge({ hipsPos: [0, -0.1, -0.16], spine: [-22, 0, 4], chest: [-12, -8, 0], head: [-18, 0, 0], thigh_L: [-30, 0, 6], shin_L: [40, 0, 0], thigh_R: [24, 0, -6], shin_R: [30, 0, 0] }, sym({ upperarm_S: [-30, 0, 40], forearm_S: [-30, 0, 0] })) },
    { t: 0.42, pose: merge({ hipsPos: [0, -0.16, -0.12], spine: [24, 0, 0], chest: [10, 0, 0], head: [-10, 0, 0], thigh_L: [-40, 0, 6], shin_L: [64, 0, 0], thigh_R: [6, 0, -6], shin_R: [60, 0, 0], foot_R: [20, 0, 0] }, sym({ upperarm_S: [-20, 0, 24], forearm_S: [-60, 0, 0] })) },
    { t: 0.8, pose: merge(cIdle) },
  ], 0.8, false));
  add(new KeyClip('death', [
    { t: 0, pose: merge(cIdle) },
    { t: 0.3, pose: merge(sym({ thigh_S: [-60, 0, 6], shin_S: [70, 0, 0], upperarm_S: [-10, 0, 30], forearm_S: [-30, 0, 0] }), { hipsPos: [0, -0.22, 0], spine: [-14, 0, 0], head: [-20, 0, 0] }) },
    { t: 0.7, pose: merge(sym({ thigh_S: [-88, 0, 6], shin_S: [122, 0, 0], foot_S: [44, 0, 0], upperarm_S: [-6, 0, 18], forearm_S: [-20, 0, 0] }), { hipsPos: [0, -0.48, 0.02], spine: [24, 0, 0], chest: [10, 0, 0], head: [16, 0, 0] }) },
    { t: 1.15, pose: merge(sym({ thigh_S: [-80, 0, 6], shin_S: [110, 0, 0], foot_S: [40, 0, 0], upperarm_S: [-40, 0, 30], forearm_S: [-10, 0, 0] }), { root: [0, 0, -84], hipsPos: [0, -0.46, 0.02], spine: [20, 0, 0], head: [10, 0, -10] }) },
  ], 1.15, false));
  add(new KeyClip('interact', [
    { t: 0, pose: idlePose(style, 0) },
    { t: 0.25, pose: merge(idlePose(style, 0), { spine: [10, 0, 0], head: [12, 0, 0], upperarm_R: [-62, 22, -8], forearm_R: [-28, 0, 0], hand_R: [-10, 0, 0] }) },
    { t: 0.55, pose: merge(idlePose(style, 0), { spine: [10, 0, 0], head: [12, 0, 0], upperarm_R: [-60, 22, -8], forearm_R: [-30, 0, 0], hand_R: [-14, 0, 0] }) },
    { t: 0.8, pose: idlePose(style, 0) },
  ], 0.8, false, [{ t: 0.3, name: 'use' }]));
  add(new KeyClip('pickup', [
    { t: 0, pose: idlePose(style, 0) },
    { t: 0.25, pose: merge(sym({ thigh_S: [-60, 0, 8], shin_S: [90, 0, 0], foot_S: [-28, 0, 0] }), { hipsPos: [0, -0.3, 0], spine: [34, 0, 0], head: [10, 0, 0], upperarm_R: [-50, 10, -6], forearm_R: [-10, 0, 0] }) },
    { t: 0.55, pose: idlePose(style, 0) },
  ], 0.55, false, [{ t: 0.25, name: 'use' }]));
  add(new KeyClip('climb', [
    { t: 0, pose: merge({ upperarm_L: [-160, 0, 10], forearm_L: [-30, 0, 0], upperarm_R: [-120, 0, -10], forearm_R: [-70, 0, 0], thigh_L: [-20, 0, 4], shin_L: [30, 0, 0], thigh_R: [-60, 0, -4], shin_R: [80, 0, 0] }, { spine: [8, 0, 0], head: [-14, 0, 0] }) },
    { t: 0.45, pose: merge({ upperarm_L: [-120, 0, 10], forearm_L: [-70, 0, 0], upperarm_R: [-160, 0, -10], forearm_R: [-30, 0, 0], thigh_L: [-60, 0, 4], shin_L: [80, 0, 0], thigh_R: [-20, 0, -4], shin_R: [30, 0, 0] }, { spine: [8, 0, 0], head: [-14, 0, 0] }) },
  ], 0.9, true));

  // ---- Conversation and NPC behaviour
  const talkBase = idlePose(style, 0.3);
  add(new KeyClip('talk', [
    { t: 0, pose: talkBase },
    { t: 0.8, pose: merge(talkBase, { upperarm_R: [-26, 20, -8], forearm_R: [-70, 0, 0], hand_R: [-10, 0, -20], head: [2, 6, 0] }) },
    { t: 1.6, pose: merge(talkBase, { upperarm_R: [-20, 26, -8], forearm_R: [-62, 0, 0], hand_R: [-10, 0, -30], head: [0, -4, 0] }) },
    { t: 2.4, pose: merge(talkBase, { upperarm_L: [-24, -20, 8], forearm_L: [-60, 0, 0], hand_L: [-10, 0, 20], head: [3, 0, 2] }) },
    { t: 3.2, pose: talkBase },
  ], 3.2, true));
  add(new KeyClip('npc_crossed', [
    { t: 0, pose: merge(idlePose(style, 0.6), sym({ upperarm_S: [-26, -72, -18], forearm_S: [-104, 0, 0], hand_S: [0, 0, 0] })) },
    { t: 3, pose: merge(idlePose(style, 0.5), sym({ upperarm_S: [-24, -70, -18], forearm_S: [-106, 0, 0] }), { head: [4, 10, 0] }) },
  ], 6, true));
  add(new KeyClip('npc_hips', [
    { t: 0, pose: merge(idlePose(style, -0.8), sym({ upperarm_S: [6, 30, 22], forearm_S: [-92, 0, 0], hand_S: [-20, 0, 30] })) },
    { t: 3.5, pose: merge(idlePose(style, -0.7), sym({ upperarm_S: [6, 30, 22], forearm_S: [-92, 0, 0], hand_S: [-20, 0, 30] }), { head: [6, -14, 0] }) },
  ], 7, true));
  add(new KeyClip('npc_work', [
    { t: 0, pose: merge(idlePose(style, 0), { spine: [16, 0, 0], head: [16, 0, 0] }, sym({ upperarm_S: [-46, -14, -4], forearm_S: [-52, 0, 0], hand_S: [-20, 0, 0] })) },
    { t: 0.5, pose: merge(idlePose(style, 0), { spine: [16, 0, 0], head: [18, 4, 0] }, { upperarm_L: [-50, -14, 4], forearm_L: [-48, 0, 0], upperarm_R: [-44, 14, -4], forearm_R: [-56, 0, 0] }) },
    { t: 1.0, pose: merge(idlePose(style, 0), { spine: [16, 0, 0], head: [16, -4, 0] }, { upperarm_L: [-44, -14, 4], forearm_L: [-56, 0, 0], upperarm_R: [-50, 14, -4], forearm_R: [-48, 0, 0] }) },
  ], 1.5, true));
  add(new KeyClip('npc_look', [
    { t: 0, pose: idlePose(style, 0.5) },
    { t: 1.2, pose: merge(idlePose(style, 0.5), { head: [-4, 40, 0], chest: [0, 10, 0] }) },
    { t: 2.6, pose: merge(idlePose(style, 0.4), { head: [-6, 38, 0], chest: [0, 10, 0] }) },
    { t: 3.8, pose: merge(idlePose(style, 0.2), { head: [0, -36, 0], chest: [0, -8, 0] }) },
    { t: 5.4, pose: merge(idlePose(style, 0.2), { head: [2, -32, 0], chest: [0, -8, 0] }) },
    { t: 6.6, pose: idlePose(style, 0.5) },
  ], 7.2, true));
  add(new KeyClip('npc_react', [
    { t: 0, pose: idlePose(style, 0) },
    { t: 0.12, pose: merge(idlePose(style, 0), { hipsPos: [0, -0.04, -0.05], spine: [-8, 0, 0], head: [-10, 0, 0] }, sym({ upperarm_S: [-40, -20, 10], forearm_S: [-100, 0, 0] })) },
    { t: 0.8, pose: merge(idlePose(style, 0), { head: [-4, 0, 0] }, sym({ upperarm_S: [-30, -20, 6], forearm_S: [-80, 0, 0] })) },
    { t: 1.3, pose: idlePose(style, 0) },
  ], 1.3, false));
  add(new KeyClip('wave', [
    { t: 0, pose: idlePose(style, 0) },
    { t: 0.3, pose: merge(idlePose(style, 0), { upperarm_R: [-20, 0, -110], forearm_R: [-60, 0, 0], hand_R: [0, 0, -10] }) },
    { t: 0.55, pose: merge(idlePose(style, 0), { upperarm_R: [-20, 0, -110], forearm_R: [-40, 0, 0], hand_R: [0, 0, 20] }) },
    { t: 0.8, pose: merge(idlePose(style, 0), { upperarm_R: [-20, 0, -110], forearm_R: [-60, 0, 0], hand_R: [0, 0, -10] }) },
    { t: 1.3, pose: idlePose(style, 0) },
  ], 1.3, false));
  add(new KeyClip('sit', [
    { t: 0, pose: merge(sym({ thigh_S: [-88, 0, 6], shin_S: [86, 0, 0], foot_S: [-4, 0, 0], upperarm_S: [-30, -10, -8], forearm_S: [-60, 0, 0] }), { hipsPos: [0, -0.46, -0.05], spine: [10, 0, 0], head: [6, 0, 0] }) },
    { t: 3, pose: merge(sym({ thigh_S: [-88, 0, 6], shin_S: [86, 0, 0], foot_S: [-4, 0, 0], upperarm_S: [-30, -10, -8], forearm_S: [-62, 0, 0] }), { hipsPos: [0, -0.46, -0.05], spine: [12, 0, 0], head: [10, 8, 0] }) },
  ], 6, true));
  add(new KeyClip('kneel_work', [
    { t: 0, pose: merge(kneel, { hipsPos: [0, -0.36, 0], spine: [28, 0, 0], head: [20, 0, 0] }, sym({ upperarm_S: [-50, -10, -4], forearm_S: [-40, 0, 0] })) },
    { t: 1.2, pose: merge(kneel, { hipsPos: [0, -0.36, 0], spine: [30, 0, 0], head: [24, 6, 0] }, { upperarm_L: [-56, -10, 4], forearm_L: [-30, 0, 0], upperarm_R: [-44, 10, -4], forearm_R: [-52, 0, 0] }) },
  ], 2.4, true));
  add(new KeyClip('lie', [
    { t: 0, pose: merge(sym({ thigh_S: [-10, 0, 4], shin_S: [20, 0, 0], upperarm_S: [-30, 0, 30], forearm_S: [-30, 0, 0] }), { root: [-88, 0, 0], hipsPos: [0, 0.0, 0] }) },
  ], 1, true));
  // Wake-up from lying (intro)
  add(new KeyClip('wake', [
    { t: 0, pose: merge(sym({ thigh_S: [-10, 0, 4], shin_S: [20, 0, 0], upperarm_S: [-30, 0, 30], forearm_S: [-30, 0, 0] }), { root: [-88, 0, 0] }) },
    { t: 1.2, pose: merge(sym({ thigh_S: [-60, 0, 6], shin_S: [100, 0, 0], foot_S: [30, 0, 0], upperarm_S: [-10, 0, 20], forearm_S: [-30, 0, 0] }), { root: [-40, 0, 0], spine: [30, 0, 0], head: [10, 0, 0], hipsPos: [0, -0.3, 0] }) },
    { t: 2.2, pose: merge(kneel, { hipsPos: [0, -0.36, 0], spine: [26, 0, 0], head: [6, 0, 0], upperarm_L: [-30, 0, 20], forearm_L: [-40, 0, 0], upperarm_R: [-60, 10, -10], forearm_R: [-20, 0, 0] }) },
    { t: 3.4, pose: merge(idlePose(style, 0), { spine: [8, 0, 0], head: [10, 0, 0] }) },
  ], 3.4, false));
  return { loco, clips };
}
