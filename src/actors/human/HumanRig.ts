import * as THREE from 'three';

// Humanoid skeleton. All bones have identity rest rotation (world-aligned axes), which keeps
// procedural mesh generation and pose authoring simple. The character faces +Z; its right side is -X.

export const BONE_NAMES = [
  'root', 'hips', 'spine', 'chest', 'neck', 'head',
  'clavicle_L', 'upperarm_L', 'forearm_L', 'hand_L',
  'clavicle_R', 'upperarm_R', 'forearm_R', 'hand_R',
  'thigh_L', 'shin_L', 'foot_L',
  'thigh_R', 'shin_R', 'foot_R',
] as const;
export type BoneName = (typeof BONE_NAMES)[number];

const PARENT: Record<BoneName, BoneName | null> = {
  root: null, hips: 'root', spine: 'hips', chest: 'spine', neck: 'chest', head: 'neck',
  clavicle_L: 'chest', upperarm_L: 'clavicle_L', forearm_L: 'upperarm_L', hand_L: 'forearm_L',
  clavicle_R: 'chest', upperarm_R: 'clavicle_R', forearm_R: 'upperarm_R', hand_R: 'forearm_R',
  thigh_L: 'hips', shin_L: 'thigh_L', foot_L: 'shin_L',
  thigh_R: 'hips', shin_R: 'thigh_R', foot_R: 'shin_R',
};

export interface BodySpec {
  /** Standing height in metres. */
  height: number;
  /** Proportion variant. */
  build: 'male' | 'female' | 'robot' | 'child';
  /** Multipliers on reference widths (1 = average). */
  shoulderWidth?: number;
  hipWidth?: number;
  /** Bulk multiplier for limb/torso girth. */
  bulk?: number;
  headScale?: number;
  /** A-pose arm angle from vertical in degrees. */
  armAngle?: number;
  /** Number of hair chain bones (ponytail), 0 for none. */
  hairBones?: number;
}

export interface Rig {
  root: THREE.Bone;
  bones: THREE.Bone[];
  byName: Record<string, THREE.Bone>;
  index: Record<string, number>;
  /** Bind-pose world positions for joints and helper points. */
  j: Record<string, THREE.Vector3>;
  skeleton: THREE.Skeleton;
  spec: Required<BodySpec>;
  /** Uniform scale relative to the 1.8 m reference body. */
  s: number;
}

export function resolveSpec(spec: BodySpec): Required<BodySpec> {
  return {
    height: spec.height,
    build: spec.build,
    shoulderWidth: spec.shoulderWidth ?? 1,
    hipWidth: spec.hipWidth ?? 1,
    bulk: spec.bulk ?? 1,
    headScale: spec.headScale ?? 1,
    armAngle: spec.armAngle ?? 16,
    hairBones: spec.hairBones ?? 0,
  };
}

/** Compute bind-pose joint positions for a body spec (reference body is 1.8 m). */
export function computeJoints(specIn: BodySpec): { j: Record<string, THREE.Vector3>; s: number; spec: Required<BodySpec> } {
  const spec = resolveSpec(specIn);
  const s = spec.height / 1.8;
  const fem = spec.build === 'female';
  const child = spec.build === 'child';
  const sw = (fem ? 0.168 : 0.186) * spec.shoulderWidth;
  const hw = (fem ? 0.098 : 0.094) * spec.hipWidth;
  const v = (x: number, y: number, z: number) => new THREE.Vector3(x * s, y * s, z * s);
  const j: Record<string, THREE.Vector3> = {};
  const legScale = child ? 0.94 : 1;
  j.root = v(0, 0, 0);
  j.hips = v(0, 0.955 * legScale, 0);
  j.spine = v(0, 1.075 * (child ? 0.97 : 1), -0.012);
  j.chest = v(0, 1.245 * (child ? 0.97 : 1), -0.022);
  j.neck = v(0, 1.47 * (child ? 0.96 : 1), -0.026);
  const headY = (fem ? 1.548 : 1.56) * (child ? 0.955 : 1);
  j.head = v(0, headY, -0.012);
  const hs = spec.headScale * (fem ? 0.985 : 1) * (child ? 1.12 : 1);
  j.headCenter = v(0, headY + 0.103 * hs, 0.014);
  j.headTop = v(0, headY + 0.103 * hs + 0.118 * hs, 0.01);

  const a = (spec.armAngle * Math.PI) / 180;
  const armY = (fem ? 1.445 : 1.458) * (child ? 0.96 : 1);
  const up = (fem ? 0.292 : 0.305) * (child ? 0.9 : 1);
  const fo = (fem ? 0.252 : 0.262) * (child ? 0.9 : 1);
  const hand = fem ? 0.172 : 0.185;
  for (const side of ['L', 'R'] as const) {
    const sx = side === 'L' ? 1 : -1;
    j['clavicle_' + side] = v(sx * 0.028, armY - 0.005, -0.006);
    const sh = v(sx * sw, armY, -0.022);
    j['upperarm_' + side] = sh;
    const el = sh.clone().add(v(sx * Math.sin(a) * up, -Math.cos(a) * up, -0.012));
    j['forearm_' + side] = el;
    const a2 = a - 0.04;
    const wr = el.clone().add(v(sx * Math.sin(a2) * fo, -Math.cos(a2) * fo, 0.022));
    j['hand_' + side] = wr;
    j['handEnd_' + side] = wr.clone().add(v(sx * Math.sin(a2) * hand, -Math.cos(a2) * hand, 0.008));
    j['thigh_' + side] = v(sx * hw, 0.93 * legScale, 0.0);
    j['shin_' + side] = v(sx * (hw + 0.008), 0.515 * legScale, 0.016);
    j['foot_' + side] = v(sx * (hw + 0.012), 0.088, -0.022);
    j['toe_' + side] = v(sx * (hw + 0.02), 0.03, 0.165 * (fem ? 0.93 : 1));
    j['heel_' + side] = v(sx * (hw + 0.012), 0.03, -0.075);
  }
  return { j, s, spec };
}

export function createRig(specIn: BodySpec): Rig {
  const { j, s, spec } = computeJoints(specIn);
  const bones: THREE.Bone[] = [];
  const byName: Record<string, THREE.Bone> = {};
  const index: Record<string, number> = {};
  for (const name of BONE_NAMES) {
    const b = new THREE.Bone();
    b.name = name;
    const parent = PARENT[name];
    const p = j[name];
    if (parent) {
      b.position.copy(p).sub(j[parent]);
      byName[parent].add(b);
    } else b.position.copy(p);
    index[name] = bones.length;
    bones.push(b);
    byName[name] = b;
  }
  // Optional hair chain hanging from the back of the head.
  if (spec.hairBones > 0) {
    let parent = byName.head;
    let prevPos = j.head;
    const start = j.headCenter.clone().add(new THREE.Vector3(0, 0.06 * s, -0.085 * s));
    for (let i = 0; i < spec.hairBones; i++) {
      const name = 'hair_' + i;
      const pos = i === 0 ? start : j['hair_' + (i - 1)].clone().add(new THREE.Vector3(0, -0.075 * s, -0.012 * s));
      j[name] = pos;
      const b = new THREE.Bone();
      b.name = name;
      b.position.copy(pos).sub(prevPos);
      parent.add(b);
      index[name] = bones.length;
      bones.push(b);
      byName[name] = b;
      parent = b;
      prevPos = pos;
    }
    j.hairEnd = j['hair_' + (spec.hairBones - 1)].clone().add(new THREE.Vector3(0, -0.07 * s, -0.008 * s));
  }
  const root = byName.root;
  root.updateMatrixWorld(true);
  const skeleton = new THREE.Skeleton(bones);
  return { root, bones, byName, index, j, skeleton, spec, s };
}
