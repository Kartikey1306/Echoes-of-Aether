import * as THREE from 'three';
import { Animator, SpringChain } from './Animator';
import { getAnimLib, type AnimLib, type AnimStyle } from './Anims';
import { buildHuman, MAT_KEYS, type Look, type MatKey } from './HumanBuilder';
import { createHumanMaterials, type HumanMaterials } from './HumanMaterials';
import { createRig, type Rig } from './HumanRig';

export interface HumanModelOptions {
  /** Number of LOD levels to build (1-3). */
  lods?: number;
  castShadow?: boolean;
  faceSize?: number;
  style?: AnimStyle;
  /** LOD switch distances. */
  lodDistances?: [number, number];
}

/** Runtime character: skeleton + LOD skinned meshes + sockets + animator + secondary motion. */
export class HumanModel {
  readonly root = new THREE.Group();
  readonly rig: Rig;
  readonly look: Look;
  readonly materials: HumanMaterials;
  readonly lod: THREE.LOD;
  readonly meshes: THREE.SkinnedMesh[] = [];
  readonly sockets: Record<string, THREE.Object3D> = {};
  readonly animator: Animator;
  readonly anims: AnimLib;
  private hair: SpringChain | null = null;
  private eyeMeshes: { mesh: THREE.SkinnedMesh; base: Float32Array; centers: THREE.Vector3[] }[] = [];
  private blinkT = 2 + Math.random() * 3;
  private blinkPhase = 0;
  private flash = 0;
  private flashColor = new THREE.Color(1, 1, 1);
  glowBoost = 0;
  private glowBase = 2.6;
  stats = { triangles: [0, 0, 0] as number[], vertices: 0 };

  constructor(look: Look, opts: HumanModelOptions = {}) {
    this.look = look;
    this.rig = createRig(look.body);
    this.materials = createHumanMaterials(look, opts.faceSize ?? 512);
    this.root.name = 'human:' + look.id;
    this.root.add(this.rig.root);
    this.lod = new THREE.LOD();
    this.lod.autoUpdate = true;
    this.root.add(this.lod);
    const levels = Math.max(1, Math.min(3, opts.lods ?? 3));
    const dists = opts.lodDistances ?? [9, 22];
    this.root.updateMatrixWorld(true);
    let sockets: Record<string, { bone: string; pos: THREE.Vector3 }> = {};
    for (let l = 0; l < levels; l++) {
      const res = buildHuman(look, this.rig, l);
      if (l === 0) sockets = res.sockets;
      const group = new THREE.Group();
      group.name = 'lod' + l;
      let tris = 0;
      for (const key of MAT_KEYS) {
        const b = res.buckets.get(key);
        if (!b || b.count === 0) continue;
        const geo = b.toGeometry();
        geo.computeBoundingBox();
        const mesh = new THREE.SkinnedMesh(geo, this.materials[key]);
        mesh.name = `${look.id}_${key}_lod${l}`;
        mesh.castShadow = opts.castShadow ?? true;
        mesh.receiveShadow = key !== 'glow' && key !== 'eye';
        if (key === 'glow' || key === 'eye') mesh.castShadow = false;
        mesh.bind(this.rig.skeleton, new THREE.Matrix4());
        mesh.frustumCulled = true;
        // Generous bounds so animated poses never get culled.
        mesh.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, look.body.height * 0.5, 0), look.body.height * 1.1);
        mesh.boundingBox = new THREE.Box3(new THREE.Vector3(-1.2, -0.5, -1.2).multiplyScalar(look.body.height), new THREE.Vector3(1.2, 1.6, 1.2).multiplyScalar(look.body.height));
        group.add(mesh);
        this.meshes.push(mesh);
        tris += (geo.index?.count ?? 0) / 3;
        if (key === 'eye' && l === 0) {
          const pos = geo.getAttribute('position') as THREE.BufferAttribute;
          this.eyeMeshes.push({ mesh, base: new Float32Array(pos.array as Float32Array), centers: res.eyes });
        }
      }
      this.stats.triangles[l] = tris;
      this.lod.addLevel(group, l === 0 ? 0 : dists[l - 1]);
    }
    // Sockets as children of bones.
    for (const [name, s] of Object.entries(sockets)) {
      const bone = this.rig.byName[s.bone];
      const o = new THREE.Object3D();
      o.name = 'socket:' + name;
      bone.updateMatrixWorld(true);
      o.position.copy(bone.worldToLocal(s.pos.clone()));
      bone.add(o);
      this.sockets[name] = o;
    }
    this.anims = getAnimLib(opts.style ?? (look.body.build === 'female' ? 'female' : 'male'));
    this.animator = new Animator(this.rig.byName, this.anims.loco, this.rig.s);
    const hairBones: THREE.Bone[] = [];
    for (let i = 0; i < (this.rig.spec.hairBones ?? 0); i++) hairBones.push(this.rig.byName['hair_' + i]);
    if (hairBones.length) this.hair = new SpringChain(hairBones, this.rig.byName.head);
    this.glowBase = (this.materials.glow as THREE.MeshBasicMaterial).color.r;
  }

  get height() {
    return this.look.body.height;
  }

  socketWorld(name: string, out = new THREE.Vector3()): THREE.Vector3 {
    const s = this.sockets[name];
    if (!s) return this.root.getWorldPosition(out);
    return s.getWorldPosition(out);
  }

  /** Brief emissive flash (hit feedback). */
  hitFlash(color = 0xffffff, amount = 1) {
    this.flash = amount;
    this.flashColor.set(color);
  }

  setVisible(v: boolean) {
    this.root.visible = v;
  }

  update(dt: number) {
    this.animator.update(dt);
    this.hair?.update(dt * this.animator.timeScale);
    // Blinking
    this.blinkT -= dt;
    if (this.blinkT <= 0) {
      this.blinkPhase = 0.14;
      this.blinkT = 2.5 + Math.random() * 4;
    }
    if (this.blinkPhase > 0 || this.eyeMeshes.length) {
      this.blinkPhase = Math.max(0, this.blinkPhase - dt);
      const closed = this.blinkPhase > 0 ? Math.sin((this.blinkPhase / 0.14) * Math.PI) : 0;
      for (const e of this.eyeMeshes) {
        const pos = e.mesh.geometry.getAttribute('position') as THREE.BufferAttribute;
        const arr = pos.array as Float32Array;
        const half = arr.length / 2;
        for (let i = 0; i < arr.length; i += 3) {
          const c = e.centers[i < half ? 0 : 1] ?? e.centers[0];
          arr[i + 1] = c.y + (e.base[i + 1] - c.y) * (1 - closed * 0.92);
        }
        pos.needsUpdate = true;
      }
    }
    // Hit flash and glow boost
    if (this.flash > 0) this.flash = Math.max(0, this.flash - dt * 6);
    const fl = this.flash;
    for (const key of ['cloth', 'armor', 'skin', 'face'] as MatKey[]) {
      const m = this.materials[key] as THREE.MeshStandardMaterial;
      m.emissive.copy(this.flashColor).multiplyScalar(fl * 0.6);
    }
    const g = this.materials.glow as THREE.MeshBasicMaterial;
    g.color.setScalar(this.glowBase * (1 + this.glowBoost));
  }

  dispose() {
    for (const m of this.meshes) m.geometry.dispose();
    for (const k of MAT_KEYS) {
      const m = this.materials[k] as THREE.MeshStandardMaterial;
      m.map?.dispose();
      m.dispose();
    }
    this.root.removeFromParent();
  }
}
