import { KeyClip, sym, type Clip, type PoseSpec } from '../human/Animator';

// Attack/reaction clips for robot enemies (sentinel, warden, stalker, guardian).
// Events: 'telegraph' (start glow), 'hit_start'/'hit_end' (active window), 'impact' (AoE moment), 'fire'.

const merge = (...p: PoseSpec[]): PoseSpec => Object.assign({}, ...p);

const robotStance: PoseSpec = merge(
  { hipsPos: [0, -0.06, 0], spine: [10, 0, 0], chest: [6, 0, 0], head: [-10, 0, 0] },
  sym({ upperarm_S: [-20, -10, 6], forearm_S: [-50, 0, 0], thigh_S: [-16, 0, 4], shin_S: [26, 0, 0], foot_S: [-8, 0, 0] }),
);

const cache: Record<string, Record<string, Clip>> = {};

export function robotClips(kind: 'sentinel' | 'stalker' | 'guardian'): Record<string, Clip> {
  if (cache[kind]) return cache[kind];
  const c: Record<string, Clip> = {};
  const add = (k: KeyClip) => (c[k.name] = k);
  add(new KeyClip('stance', [{ t: 0, pose: robotStance }, { t: 1, pose: merge(robotStance, { hipsPos: [0, -0.08, 0] }) }], 2, true));

  if (kind === 'sentinel' || kind === 'guardian') {
    const big = kind === 'guardian';
    // Overhead two-handed slam
    add(new KeyClip('slam', [
      { t: 0, pose: robotStance },
      { t: big ? 0.8 : 0.55, pose: merge(sym({ upperarm_S: [-170, 0, 12], forearm_S: [-40, 0, 0], thigh_S: [-20, 0, 6], shin_S: [30, 0, 0] }), { hipsPos: [0, 0.02, -0.06], spine: [-14, 0, 0], chest: [-12, 0, 0], head: [-14, 0, 0] }) },
      { t: big ? 1.05 : 0.72, pose: merge(sym({ upperarm_S: [-60, 0, 8], forearm_S: [-6, 0, 0], thigh_S: [-50, 0, 6], shin_S: [80, 0, 0], foot_S: [-26, 0, 0] }), { hipsPos: [0, -0.32, 0.12], spine: [40, 0, 0], chest: [18, 0, 0], head: [-26, 0, 0] }) },
      { t: big ? 1.6 : 1.1, pose: merge(sym({ upperarm_S: [-56, 0, 10], forearm_S: [-10, 0, 0], thigh_S: [-46, 0, 6], shin_S: [76, 0, 0], foot_S: [-26, 0, 0] }), { hipsPos: [0, -0.3, 0.12], spine: [36, 0, 0], chest: [16, 0, 0], head: [-24, 0, 0] }) },
      { t: big ? 2.2 : 1.5, pose: robotStance },
    ], big ? 2.2 : 1.5, false, [{ t: 0.05, name: 'telegraph' }, { t: big ? 1.0 : 0.68, name: 'hit_start' }, { t: big ? 1.05 : 0.72, name: 'impact' }, { t: big ? 1.15 : 0.82, name: 'hit_end' }]));
    // Horizontal sweep (right arm)
    add(new KeyClip('sweep', [
      { t: 0, pose: robotStance },
      { t: big ? 0.65 : 0.42, pose: merge(robotStance, { hips: [0, -20, 0], chest: [4, -40, 0], upperarm_R: [0, -30, -74], forearm_R: [-40, 0, 0] }) },
      { t: big ? 0.85 : 0.56, pose: merge(robotStance, { hips: [0, 10, 0], chest: [8, 10, 0], upperarm_R: [0, 85, -76], forearm_R: [-10, 0, 0] }) },
      { t: big ? 1.0 : 0.68, pose: merge(robotStance, { hips: [0, 24, 0], chest: [8, 40, 0], upperarm_R: [0, 150, -70], forearm_R: [-20, 0, 0] }) },
      { t: big ? 1.6 : 1.1, pose: robotStance },
    ], big ? 1.6 : 1.1, false, [{ t: 0.05, name: 'telegraph' }, { t: big ? 0.74 : 0.48, name: 'hit_start' }, { t: big ? 1.0 : 0.68, name: 'hit_end' }]));
    add(new KeyClip('stagger', [
      { t: 0, pose: robotStance },
      { t: 0.15, pose: merge(robotStance, { hipsPos: [0, -0.1, -0.15], spine: [-20, 10, 0], chest: [-14, 0, 0], head: [-20, 0, 0] }, sym({ upperarm_S: [-10, 0, 40], forearm_S: [-20, 0, 0] })) },
      { t: 0.7, pose: merge(robotStance, { hipsPos: [0, -0.2, -0.05], spine: [30, 0, 0], head: [10, 0, 0] }, sym({ upperarm_S: [0, 0, 10], forearm_S: [-30, 0, 0] })) },
      { t: 1.3, pose: robotStance },
    ], 1.3, false));
    add(new KeyClip('death', [
      { t: 0, pose: robotStance },
      { t: 0.4, pose: merge(sym({ thigh_S: [-70, 0, 8], shin_S: [100, 0, 0], foot_S: [30, 0, 0], upperarm_S: [0, 0, 20], forearm_S: [-10, 0, 0] }), { hipsPos: [0, -0.42, 0], spine: [30, 0, 10], head: [30, 0, 0] }) },
      { t: 1.1, pose: merge(sym({ thigh_S: [-80, 0, 8], shin_S: [110, 0, 0], foot_S: [30, 0, 0], upperarm_S: [-20, 0, 40], forearm_S: [0, 0, 0] }), { root: [70, 0, 10], hipsPos: [0, -0.5, 0], spine: [20, 0, 0], head: [20, 0, 0] }) },
    ], 1.1, false));
    if (big) {
      add(new KeyClip('roar', [
        { t: 0, pose: robotStance },
        { t: 0.6, pose: merge(sym({ upperarm_S: [-20, 0, 70], forearm_S: [-60, 0, 0], thigh_S: [-20, 0, 8], shin_S: [30, 0, 0] }), { hipsPos: [0, -0.04, 0], spine: [-16, 0, 0], chest: [-18, 0, 0], head: [-30, 0, 0] }) },
        { t: 1.8, pose: merge(sym({ upperarm_S: [-24, 0, 74], forearm_S: [-56, 0, 0], thigh_S: [-20, 0, 8], shin_S: [30, 0, 0] }), { hipsPos: [0, -0.04, 0], spine: [-18, 0, 0], chest: [-20, 0, 0], head: [-34, 0, 0] }) },
        { t: 2.4, pose: robotStance },
      ], 2.4, false, [{ t: 0.6, name: 'roar' }]));
      add(new KeyClip('laser', [
        { t: 0, pose: robotStance },
        { t: 0.8, pose: merge(robotStance, { hips: [0, -40, 0], spine: [0, -10, 0], chest: [-6, -10, 0], head: [-10, 0, 0] }, sym({ upperarm_S: [-10, 0, 40], forearm_S: [-80, 0, 0] })) },
        { t: 2.8, pose: merge(robotStance, { hips: [0, 40, 0], spine: [0, 10, 0], chest: [-6, 10, 0], head: [-10, 0, 0] }, sym({ upperarm_S: [-10, 0, 40], forearm_S: [-80, 0, 0] })) },
        { t: 3.4, pose: robotStance },
      ], 3.4, false, [{ t: 0.05, name: 'telegraph' }, { t: 0.8, name: 'laser_on' }, { t: 2.8, name: 'laser_off' }]));
      add(new KeyClip('exposed', [
        { t: 0, pose: robotStance },
        { t: 0.3, pose: merge(sym({ upperarm_S: [-10, 0, 50], forearm_S: [-20, 0, 0], thigh_S: [-60, 0, 8], shin_S: [90, 0, 0], foot_S: [-30, 0, 0] }), { hipsPos: [0, -0.36, 0], spine: [-24, 0, 0], chest: [-20, 0, 0], head: [-24, 0, 0] }) },
        { t: 3.2, pose: merge(sym({ upperarm_S: [-12, 0, 48], forearm_S: [-24, 0, 0], thigh_S: [-60, 0, 8], shin_S: [90, 0, 0], foot_S: [-30, 0, 0] }), { hipsPos: [0, -0.37, 0], spine: [-22, 0, 0], chest: [-18, 0, 0], head: [-20, 0, 0] }) },
        { t: 3.8, pose: robotStance },
      ], 3.8, false));
    }
  }
  if (kind === 'stalker') {
    const crouch = merge(sym({ upperarm_S: [-10, 0, 30], forearm_S: [-30, 0, 0], thigh_S: [-40, 0, 8], shin_S: [60, 0, 0], foot_S: [-18, 0, 0] }), { hipsPos: [0, -0.22, 0], spine: [26, 0, 0], head: [-24, 0, 0] });
    add(new KeyClip('stance', [{ t: 0, pose: crouch }, { t: 0.8, pose: merge(crouch, { hipsPos: [0, -0.24, 0] }) }], 1.6, true));
    add(new KeyClip('slash', [
      { t: 0, pose: crouch },
      { t: 0.22, pose: merge(crouch, { chest: [0, 30, 0], upperarm_L: [10, 0, 70], forearm_L: [-60, 0, 0], upperarm_R: [-60, 40, -30], forearm_R: [-90, 0, 0] }) },
      { t: 0.34, pose: merge(crouch, { hipsPos: [0, -0.16, 0.3], chest: [10, -30, 0], upperarm_L: [-80, -60, 40], forearm_L: [-10, 0, 0] }) },
      { t: 0.48, pose: merge(crouch, { hipsPos: [0, -0.16, 0.35], chest: [10, 30, 0], upperarm_R: [-80, 60, -40], forearm_R: [-10, 0, 0], upperarm_L: [-40, -60, 40], forearm_L: [-40, 0, 0] }) },
      { t: 0.9, pose: crouch },
    ], 0.9, false, [{ t: 0.04, name: 'telegraph' }, { t: 0.28, name: 'hit_start' }, { t: 0.5, name: 'hit_end' }]));
    add(new KeyClip('stagger', [
      { t: 0, pose: crouch },
      { t: 0.15, pose: merge(crouch, { hipsPos: [0, -0.2, -0.2], spine: [-10, 0, 0] }) },
      { t: 0.8, pose: crouch },
    ], 0.8, false));
    add(new KeyClip('death', [
      { t: 0, pose: crouch },
      { t: 0.8, pose: merge(crouch, { root: [80, 0, 0], hipsPos: [0, -0.3, 0] }) },
    ], 0.8, false));
  }
  cache[kind] = c;
  return c;
}
