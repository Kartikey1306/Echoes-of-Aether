import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { Animator } from '../human/Animator';
import { getAnimLib, type AnimLib, type AnimStyle } from '../human/Anims';
import { createRig, type Rig } from '../human/HumanRig';

// Rigid-part robots built on the humanoid rig: each part is a mesh parented to a bone.

export interface RobotMats {
  shell: THREE.MeshStandardMaterial;
  frame: THREE.MeshStandardMaterial;
  joint: THREE.MeshStandardMaterial;
  glow: THREE.MeshBasicMaterial;
}

export function robotMaterials(shell: number, frame: number, glow: number, glowIntensity = 3): RobotMats {
  return {
    shell: new THREE.MeshStandardMaterial({ color: shell, roughness: 0.42, metalness: 0.65, name: 'robot_shell' }),
    frame: new THREE.MeshStandardMaterial({ color: frame, roughness: 0.55, metalness: 0.75, name: 'robot_frame' }),
    joint: new THREE.MeshStandardMaterial({ color: 0x15171a, roughness: 0.6, metalness: 0.6, name: 'robot_joint' }),
    glow: new THREE.MeshBasicMaterial({ color: new THREE.Color(glow).multiplyScalar(glowIntensity), name: 'robot_glow' }),
  };
}

const rboxCache = new Map<string, THREE.BufferGeometry>();
export function rbox(w: number, h: number, d: number, r = 0.05): THREE.BufferGeometry {
  const k = `${w.toFixed(3)}|${h.toFixed(3)}|${d.toFixed(3)}|${r}`;
  let g = rboxCache.get(k);
  if (!g) {
    g = new RoundedBoxGeometry(w, h, d, 2, Math.min(r, w / 2.1, h / 2.1, d / 2.1));
    rboxCache.set(k, g);
  }
  return g;
}

export class RobotModel {
  readonly root = new THREE.Group();
  readonly rig: Rig;
  readonly animator: Animator;
  readonly anims: AnimLib;
  readonly mats: RobotMats;
  readonly parts: THREE.Mesh[] = [];
  readonly glowParts: THREE.Mesh[] = [];
  private flash = 0;
  private baseGlow: THREE.Color;
  telegraph = 0;
  opacity = 1;

  constructor(height: number, mats: RobotMats, style: AnimStyle, build: (m: RobotModel) => void) {
    this.rig = createRig({ height, build: 'male', shoulderWidth: style === 'heavy' ? 1.35 : 1.15, armAngle: 14 });
    this.mats = mats;
    this.root.add(this.rig.root);
    this.anims = getAnimLib(style);
    this.animator = new Animator(this.rig.byName, this.anims.loco, this.rig.s);
    this.baseGlow = mats.glow.color.clone();
    build(this);
  }

  /** Attach a mesh to a bone at a bind-pose world position. */
  attach(bone: string, geo: THREE.BufferGeometry, mat: THREE.Material, worldPos: THREE.Vector3, quat?: THREE.Quaternion, scale?: THREE.Vector3): THREE.Mesh {
    const b = this.rig.byName[bone];
    const m = new THREE.Mesh(geo, mat);
    b.updateMatrixWorld(true);
    m.position.copy(b.worldToLocal(worldPos.clone()));
    if (quat) m.quaternion.copy(quat);
    if (scale) m.scale.copy(scale);
    m.castShadow = mat !== this.mats.glow;
    m.receiveShadow = true;
    b.add(m);
    this.parts.push(m);
    if (mat === this.mats.glow) this.glowParts.push(m);
    return m;
  }

  /** A limb segment between two joints. */
  segment(bone: string, from: string, to: string, w: number, d: number, mat: THREE.Material, inset = 0.08, shape: 'box' | 'cyl' = 'box') {
    const a = this.rig.j[from], b = this.rig.j[to];
    const len = a.distanceTo(b);
    const mid = a.clone().lerp(b, 0.5);
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
    const L = Math.max(0.05, len * (1 - inset * 2));
    const geo = shape === 'box' ? rbox(w, L, d, Math.min(w, d) * 0.25) : new THREE.CylinderGeometry(w / 2, d / 2, L, 10);
    return this.attach(bone, geo, mat, mid, q);
  }

  sphere(bone: string, at: THREE.Vector3, r: number, mat: THREE.Material) {
    return this.attach(bone, new THREE.SphereGeometry(r, 12, 8), mat, at);
  }

  hitFlash(amount = 1) {
    this.flash = amount;
  }

  update(dt: number) {
    this.animator.update(dt);
    if (this.flash > 0) this.flash = Math.max(0, this.flash - dt * 7);
    const f = this.flash;
    this.mats.shell.emissive.setRGB(f * 0.9, f * 0.9, f * 0.9);
    this.mats.frame.emissive.setRGB(f * 0.5, f * 0.5, f * 0.5);
    // Telegraph: glow brightens toward an attack.
    const t = this.telegraph;
    this.mats.glow.color.copy(this.baseGlow).multiplyScalar(1 + t * 1.6);
    if (this.opacity < 0.999) {
      for (const m of [this.mats.shell, this.mats.frame, this.mats.joint]) {
        m.transparent = true;
        m.opacity = this.opacity;
        m.depthWrite = this.opacity > 0.6;
      }
      (this.mats.glow as THREE.MeshBasicMaterial).transparent = true;
      (this.mats.glow as THREE.MeshBasicMaterial).opacity = Math.max(0.2, this.opacity);
    } else if (this.mats.shell.transparent) {
      for (const m of [this.mats.shell, this.mats.frame, this.mats.joint]) {
        m.transparent = false;
        m.opacity = 1;
        m.depthWrite = true;
      }
      (this.mats.glow as THREE.MeshBasicMaterial).transparent = false;
    }
  }

  dispose() {
    this.root.removeFromParent();
    const cached = new Set(rboxCache.values());
    for (const p of this.parts) if (!cached.has(p.geometry)) p.geometry.dispose();
    for (const m of Object.values(this.mats)) m.dispose();
  }
}

/** Corrupted Sentinel / Warden body. */
export function buildSentinelBody(m: RobotModel, elite: boolean) {
  const J = m.rig.j, s = m.rig.s;
  const M = m.mats;
  const v = (x: number, y: number, z: number) => new THREE.Vector3(x * s, y * s, z * s);
  // Pelvis & abdomen
  m.attach('hips', rbox(0.44 * s, 0.22 * s, 0.3 * s, 0.05 * s), M.frame, J.hips.clone().add(v(0, -0.02, 0)));
  m.attach('spine', new THREE.CylinderGeometry(0.13 * s, 0.16 * s, 0.24 * s, 10), M.joint, J.spine.clone().add(v(0, 0.06, 0)));
  // Chest with core
  m.attach('chest', rbox(0.62 * s, 0.46 * s, 0.4 * s, 0.08 * s), M.shell, J.chest.clone().add(v(0, 0.13, 0.01)));
  m.attach('chest', rbox(0.5 * s, 0.18 * s, 0.34 * s, 0.05 * s), M.frame, J.chest.clone().add(v(0, -0.06, 0)));
  m.attach('chest', new THREE.CylinderGeometry(0.075 * s, 0.075 * s, 0.05 * s, 16).rotateX(Math.PI / 2), M.glow, J.chest.clone().add(v(0, 0.16, 0.215)));
  // Back vents
  m.attach('chest', rbox(0.36 * s, 0.3 * s, 0.14 * s, 0.04 * s), M.frame, J.chest.clone().add(v(0, 0.16, -0.24)));
  // Head with visor
  m.attach('neck', new THREE.CylinderGeometry(0.06 * s, 0.07 * s, 0.12 * s, 8), M.joint, J.neck.clone().add(v(0, 0.05, 0)));
  m.attach('head', rbox(0.22 * s, 0.24 * s, 0.26 * s, 0.06 * s), M.shell, J.headCenter.clone().add(v(0, -0.02, 0)));
  m.attach('head', rbox(0.18 * s, 0.035 * s, 0.02 * s, 0.01 * s), M.glow, J.headCenter.clone().add(v(0, 0.0, 0.135)));
  // Arms
  for (const sd of ['L', 'R'] as const) {
    const sx = sd === 'L' ? 1 : -1;
    m.attach('clavicle_' + sd, rbox(0.3 * s, 0.22 * s, 0.34 * s, 0.07 * s), M.shell, J['upperarm_' + sd].clone().add(v(sx * 0.04, 0.08, 0)), new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, sx * -0.25)));
    m.sphere('upperarm_' + sd, J['upperarm_' + sd].clone(), 0.09 * s, M.joint);
    m.segment('upperarm_' + sd, 'upperarm_' + sd, 'forearm_' + sd, 0.13 * s, 0.13 * s, M.frame, 0.1, 'cyl');
    m.sphere('forearm_' + sd, J['forearm_' + sd].clone(), 0.08 * s, M.joint);
    m.segment('forearm_' + sd, 'forearm_' + sd, 'hand_' + sd, 0.2 * s, 0.2 * s, M.shell, 0.04);
    m.attach('hand_' + sd, rbox(0.14 * s, 0.16 * s, 0.14 * s, 0.03 * s), M.frame, J['hand_' + sd].clone().lerp(J['handEnd_' + sd], 0.4));
    // Glowing seam on forearms (telegraph)
    const fa = J['forearm_' + sd].clone().lerp(J['hand_' + sd], 0.5);
    m.attach('forearm_' + sd, rbox(0.03 * s, 0.16 * s, 0.21 * s, 0.01 * s), M.glow, fa.add(v(sx * 0.1, 0, 0)));
  }
  // Blade on the right forearm
  const bladeBase = J.hand_R.clone();
  m.attach('forearm_R', rbox(0.03 * s, 0.6 * s, 0.1 * s, 0.01 * s), M.glow, bladeBase.add(v(-0.05, -0.18, 0.06)), new THREE.Quaternion().setFromEuler(new THREE.Euler(0.15, 0, 0)));
  // Legs
  for (const sd of ['L', 'R'] as const) {
    m.sphere('thigh_' + sd, J['thigh_' + sd].clone(), 0.1 * s, M.joint);
    m.segment('thigh_' + sd, 'thigh_' + sd, 'shin_' + sd, 0.17 * s, 0.19 * s, M.frame, 0.08);
    m.attach('shin_' + sd, rbox(0.16 * s, 0.16 * s, 0.2 * s, 0.05 * s), M.shell, J['shin_' + sd].clone().add(v(0, 0.02, 0.06)));
    m.segment('shin_' + sd, 'shin_' + sd, 'foot_' + sd, 0.16 * s, 0.18 * s, M.shell, 0.1);
    m.attach('foot_' + sd, rbox(0.16 * s, 0.1 * s, 0.32 * s, 0.03 * s), M.frame, J['foot_' + sd].clone().add(v(0, -0.04, 0.08)));
  }
  if (elite) {
    // Warden: crest, extra plating and a shield emitter on the left arm.
    m.attach('head', rbox(0.05 * s, 0.12 * s, 0.3 * s, 0.02 * s), M.glow, J.headCenter.clone().add(v(0, 0.15, -0.02)));
    m.attach('chest', rbox(0.7 * s, 0.12 * s, 0.44 * s, 0.04 * s), M.shell, J.chest.clone().add(v(0, 0.38, 0)));
    m.attach('forearm_L', rbox(0.06 * s, 0.5 * s, 0.4 * s, 0.03 * s), M.shell, J.forearm_L.clone().lerp(J.hand_L, 0.5).add(v(0.13, 0, 0)));
  }
}

/** Phase Stalker body: slim, long blades. */
export function buildStalkerBody(m: RobotModel) {
  const J = m.rig.j, s = m.rig.s;
  const M = m.mats;
  const v = (x: number, y: number, z: number) => new THREE.Vector3(x * s, y * s, z * s);
  m.attach('hips', rbox(0.3 * s, 0.16 * s, 0.22 * s, 0.05 * s), M.frame, J.hips.clone());
  m.attach('spine', new THREE.CylinderGeometry(0.07 * s, 0.1 * s, 0.26 * s, 8), M.joint, J.spine.clone().add(v(0, 0.08, 0)));
  m.attach('chest', rbox(0.42 * s, 0.38 * s, 0.26 * s, 0.1 * s), M.shell, J.chest.clone().add(v(0, 0.12, 0)));
  m.attach('chest', new THREE.SphereGeometry(0.06 * s, 12, 8), M.glow, J.chest.clone().add(v(0, 0.14, 0.13)));
  m.attach('head', new THREE.ConeGeometry(0.11 * s, 0.34 * s, 6).rotateX(Math.PI / 2), M.shell, J.headCenter.clone().add(v(0, 0, 0.04)));
  m.attach('head', rbox(0.16 * s, 0.025 * s, 0.02 * s, 0.01 * s), M.glow, J.headCenter.clone().add(v(0, 0.01, 0.12)));
  for (const sd of ['L', 'R'] as const) {
    const sx = sd === 'L' ? 1 : -1;
    m.attach('clavicle_' + sd, rbox(0.16 * s, 0.1 * s, 0.2 * s, 0.04 * s), M.shell, J['upperarm_' + sd].clone().add(v(sx * 0.02, 0.05, 0)));
    m.segment('upperarm_' + sd, 'upperarm_' + sd, 'forearm_' + sd, 0.08 * s, 0.08 * s, M.frame, 0.08, 'cyl');
    m.segment('forearm_' + sd, 'forearm_' + sd, 'hand_' + sd, 0.1 * s, 0.1 * s, M.shell, 0.06);
    // Long blade extending past the hand
    const a = J['hand_' + sd], b = J['handEnd_' + sd];
    const dir = b.clone().sub(a).normalize();
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
    m.attach('hand_' + sd, rbox(0.025 * s, 0.75 * s, 0.07 * s, 0.01 * s), M.glow, a.clone().addScaledVector(dir, 0.42 * s), q);
    m.segment('thigh_' + sd, 'thigh_' + sd, 'shin_' + sd, 0.11 * s, 0.12 * s, M.frame, 0.06);
    m.segment('shin_' + sd, 'shin_' + sd, 'foot_' + sd, 0.09 * s, 0.11 * s, M.shell, 0.06);
    m.attach('foot_' + sd, rbox(0.1 * s, 0.06 * s, 0.26 * s, 0.02 * s), M.frame, J['foot_' + sd].clone().add(v(0, -0.05, 0.08)));
  }
}

/** Aether Guardian: massive biped with an armoured core. Returns the core mesh and core plates. */
export function buildGuardianBody(m: RobotModel): { core: THREE.Mesh; plates: THREE.Mesh[] } {
  const J = m.rig.j, s = m.rig.s;
  const M = m.mats;
  const v = (x: number, y: number, z: number) => new THREE.Vector3(x * s, y * s, z * s);
  m.attach('hips', rbox(0.6 * s, 0.3 * s, 0.4 * s, 0.08 * s), M.frame, J.hips.clone());
  m.attach('spine', new THREE.CylinderGeometry(0.17 * s, 0.22 * s, 0.3 * s, 10), M.joint, J.spine.clone().add(v(0, 0.08, 0)));
  m.attach('chest', rbox(0.9 * s, 0.6 * s, 0.56 * s, 0.12 * s), M.shell, J.chest.clone().add(v(0, 0.14, -0.04)));
  const core = m.attach('chest', new THREE.IcosahedronGeometry(0.13 * s, 2), M.glow, J.chest.clone().add(v(0, 0.14, 0.26)));
  const plates: THREE.Mesh[] = [];
  for (const sx of [1, -1]) {
    const p = m.attach('chest', rbox(0.22 * s, 0.4 * s, 0.08 * s, 0.03 * s), M.shell, J.chest.clone().add(v(sx * 0.12, 0.14, 0.3)));
    plates.push(p);
  }
  m.attach('chest', rbox(0.5 * s, 0.4 * s, 0.24 * s, 0.06 * s), M.frame, J.chest.clone().add(v(0, 0.2, -0.36)));
  for (let i = 0; i < 3; i++) m.attach('chest', new THREE.CylinderGeometry(0.04 * s, 0.04 * s, 0.5 * s, 8), M.glow, J.chest.clone().add(v(-0.15 + i * 0.15, 0.45, -0.42)));
  m.attach('neck', new THREE.CylinderGeometry(0.1 * s, 0.12 * s, 0.14 * s, 10), M.joint, J.neck.clone().add(v(0, 0.05, 0)));
  m.attach('head', rbox(0.26 * s, 0.2 * s, 0.3 * s, 0.07 * s), M.shell, J.headCenter.clone().add(v(0, -0.04, 0.02)));
  m.attach('head', rbox(0.2 * s, 0.03 * s, 0.02 * s, 0.01 * s), M.glow, J.headCenter.clone().add(v(0, -0.03, 0.18)));
  for (const sd of ['L', 'R'] as const) {
    const sx = sd === 'L' ? 1 : -1;
    m.attach('clavicle_' + sd, rbox(0.42 * s, 0.32 * s, 0.46 * s, 0.1 * s), M.shell, J['upperarm_' + sd].clone().add(v(sx * 0.08, 0.12, 0)), new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, sx * -0.3)));
    m.attach('clavicle_' + sd, rbox(0.06 * s, 0.25 * s, 0.4 * s, 0.02 * s), M.glow, J['upperarm_' + sd].clone().add(v(sx * 0.3, 0.12, 0)));
    m.segment('upperarm_' + sd, 'upperarm_' + sd, 'forearm_' + sd, 0.2 * s, 0.2 * s, M.frame, 0.08, 'cyl');
    m.segment('forearm_' + sd, 'forearm_' + sd, 'hand_' + sd, 0.32 * s, 0.32 * s, M.shell, 0.02);
    m.attach('hand_' + sd, rbox(0.3 * s, 0.26 * s, 0.3 * s, 0.06 * s), M.frame, J['hand_' + sd].clone().lerp(J['handEnd_' + sd], 0.35));
    m.attach('forearm_' + sd, rbox(0.04 * s, 0.22 * s, 0.33 * s, 0.01 * s), M.glow, J['forearm_' + sd].clone().lerp(J['hand_' + sd], 0.5).add(v(sx * 0.165, 0, 0)));
    m.segment('thigh_' + sd, 'thigh_' + sd, 'shin_' + sd, 0.26 * s, 0.28 * s, M.frame, 0.06);
    m.segment('shin_' + sd, 'shin_' + sd, 'foot_' + sd, 0.26 * s, 0.3 * s, M.shell, 0.06);
    m.attach('shin_' + sd, rbox(0.24 * s, 0.24 * s, 0.26 * s, 0.06 * s), M.shell, J['shin_' + sd].clone().add(v(0, 0.02, 0.09)));
    m.attach('foot_' + sd, rbox(0.28 * s, 0.14 * s, 0.46 * s, 0.04 * s), M.frame, J['foot_' + sd].clone().add(v(0, -0.06, 0.1)));
  }
  return { core, plates };
}
