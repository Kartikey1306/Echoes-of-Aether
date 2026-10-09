import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { getMaterial, glowTexture, type MatName } from '../../render/Materials';
import { G_INVISIBLE, G_WORLD, type Physics } from '../../physics/Physics';
export type { Physics };

// Static level construction: world-scale UVs, per-material/per-cell merging, colliders, lights, decals.

export interface PieceOpts {
  rotY?: number;
  collide?: boolean;
  shadow?: boolean;
  receive?: boolean;
  /** UV offset seed so neighbouring pieces don't repeat identically. */
  uvSeed?: number;
  /** Additional euler rotation (x,z) for tilted debris. */
  rotX?: number;
  rotZ?: number;
}

interface Bucket {
  mat: THREE.Material;
  geos: THREE.BufferGeometry[];
  shadow: boolean;
  receive: boolean;
}

const CELL = 32;
const tmpM = new THREE.Matrix4();
const tmpQ = new THREE.Quaternion();
const tmpE = new THREE.Euler();

export class LevelBuilder {
  readonly root: THREE.Group;
  private buckets = new Map<string, Bucket>();
  private lightCount = 0;
  lightBudget = 14;
  readonly colliders: number[] = [];
  /** Axis-aligned bounds of everything built (for maps / bounds). */
  readonly bounds = new THREE.Box3();
  stats = { pieces: 0, meshes: 0, triangles: 0, lights: 0 };

  /** World offset of `root`; colliders are placed at local + offset. */
  readonly offset: THREE.Vector3;
  private physicsLocal: Physics;

  constructor(root: THREE.Group, physics: Physics, offset?: THREE.Vector3) {
    this.root = root;
    this.offset = offset?.clone() ?? new THREE.Vector3();
    this.root.position.copy(this.offset);
    this.physicsLocal = physics;
    // Wrap the physics API so every collider gets the builder offset.
    const o = this.offset;
    this.physics = o.lengthSq() === 0 ? physics : (new Proxy(physics, {
      get(target, prop, recv) {
        if (prop === 'addBox') return (cx: number, cy: number, cz: number, hx: number, hy: number, hz: number, rotY?: number, m?: number) => target.addBox(cx + o.x, cy + o.y, cz + o.z, hx, hy, hz, rotY, m);
        if (prop === 'addBoxQ') return (c: THREE.Vector3, h: THREE.Vector3, q: THREE.Quaternion, m?: number) => target.addBoxQ(c.clone().add(o), h, q, m);
        if (prop === 'addCylinder') return (cx: number, cy: number, cz: number, r: number, hh: number, m?: number) => target.addCylinder(cx + o.x, cy + o.y, cz + o.z, r, hh, m);
        return Reflect.get(target, prop, recv);
      },
    }) as Physics);
  }
  readonly physics: Physics;

  private bucket(mat: THREE.Material, cx: number, cz: number, shadow: boolean, receive: boolean): Bucket {
    const key = `${mat.uuid}|${Math.floor(cx / CELL)}|${Math.floor(cz / CELL)}|${shadow ? 1 : 0}`;
    let b = this.buckets.get(key);
    if (!b) {
      b = { mat, geos: [], shadow, receive };
      this.buckets.set(key, b);
    }
    return b;
  }

  private add(geo: THREE.BufferGeometry, mat: THREE.Material, center: THREE.Vector3, o: PieceOpts) {
    const b = this.bucket(mat, center.x, center.z, o.shadow ?? true, o.receive ?? true);
    // Ensure identical attribute sets for merging.
    if (!geo.getAttribute('uv')) geo.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array((geo.getAttribute('position').count) * 2), 2));
    if (!geo.index) {
      const n = geo.getAttribute('position').count;
      const idx = new Array(n);
      for (let i = 0; i < n; i++) idx[i] = i;
      geo.setIndex(idx);
    }
    for (const name of Object.keys(geo.attributes)) if (name !== 'position' && name !== 'normal' && name !== 'uv') geo.deleteAttribute(name);
    b.geos.push(geo);
    this.stats.pieces++;
    geo.computeBoundingBox();
    this.bounds.union(geo.boundingBox!);
  }

  private mat(m: MatName | THREE.Material): THREE.Material {
    return typeof m === 'string' ? getMaterial(m) : m;
  }

  /** Axis-aligned (optionally Y-rotated) box with world-scale UVs. Center + full size. */
  box(cx: number, cy: number, cz: number, sx: number, sy: number, sz: number, m: MatName | THREE.Material, o: PieceOpts = {}) {
    const g = new THREE.BoxGeometry(sx, sy, sz);
    const uv = g.getAttribute('uv') as THREE.BufferAttribute;
    const seed = o.uvSeed ?? (cx * 0.37 + cz * 0.61 + cy * 0.13);
    const dims = [[sz, sy], [sz, sy], [sx, sz], [sx, sz], [sx, sy], [sx, sy]];
    for (let f = 0; f < 6; f++) {
      for (let k = 0; k < 4; k++) {
        const i = f * 4 + k;
        uv.setXY(i, uv.getX(i) * dims[f][0] + seed, uv.getY(i) * dims[f][1] + seed * 0.7);
      }
    }
    tmpE.set(o.rotX ?? 0, o.rotY ?? 0, o.rotZ ?? 0);
    tmpQ.setFromEuler(tmpE);
    tmpM.compose(new THREE.Vector3(cx, cy, cz), tmpQ, new THREE.Vector3(1, 1, 1));
    g.applyMatrix4(tmpM);
    this.add(g, this.mat(m), new THREE.Vector3(cx, cy, cz), o);
    if (o.collide !== false) {
      if (!o.rotX && !o.rotZ) this.physics.addBox(cx, cy, cz, sx / 2, sy / 2, sz / 2, o.rotY ?? 0);
      else this.physics.addBoxQ(new THREE.Vector3(cx, cy, cz), new THREE.Vector3(sx / 2, sy / 2, sz / 2), tmpQ.clone());
    }
    return this;
  }

  /** Box from min corner + size (convenient for floor plans). */
  boxMin(x: number, y: number, z: number, sx: number, sy: number, sz: number, m: MatName | THREE.Material, o: PieceOpts = {}) {
    return this.box(x + sx / 2, y + sy / 2, z + sz / 2, sx, sy, sz, m, o);
  }

  cyl(cx: number, cy: number, cz: number, rTop: number, rBot: number, h: number, m: MatName | THREE.Material, seg = 12, o: PieceOpts & { open?: boolean } = {}) {
    const g = new THREE.CylinderGeometry(rTop, rBot, h, seg, 1, o.open ?? false);
    const uv = g.getAttribute('uv') as THREE.BufferAttribute;
    const circ = Math.PI * 2 * Math.max(rTop, rBot);
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * circ, uv.getY(i) * h);
    tmpE.set(o.rotX ?? 0, o.rotY ?? 0, o.rotZ ?? 0);
    tmpQ.setFromEuler(tmpE);
    tmpM.compose(new THREE.Vector3(cx, cy, cz), tmpQ, new THREE.Vector3(1, 1, 1));
    g.applyMatrix4(tmpM);
    this.add(g, this.mat(m), new THREE.Vector3(cx, cy, cz), o);
    if (o.collide !== false && !o.rotX && !o.rotZ) this.physics.addCylinder(cx, cy, cz, Math.max(rTop, rBot), h / 2);
    else if (o.collide !== false) this.physics.addBoxQ(new THREE.Vector3(cx, cy, cz), new THREE.Vector3(Math.max(rTop, rBot) * 0.8, h / 2, Math.max(rTop, rBot) * 0.8), tmpQ.clone());
    return this;
  }

  /** Arbitrary geometry (already authored in local space) placed by a matrix. Optional box collider. */
  geo(g: THREE.BufferGeometry, m: MatName | THREE.Material, matrix: THREE.Matrix4, o: PieceOpts & { colliderBox?: THREE.Box3 } = {}) {
    const gg = g.clone();
    gg.applyMatrix4(matrix);
    const c = new THREE.Vector3().setFromMatrixPosition(matrix);
    this.add(gg, this.mat(m), c, o);
    if (o.colliderBox) {
      const b = o.colliderBox.clone().applyMatrix4(matrix);
      const ctr = b.getCenter(new THREE.Vector3());
      const half = b.getSize(new THREE.Vector3()).multiplyScalar(0.5);
      this.physics.addBox(ctr.x, ctr.y, ctr.z, half.x, half.y, half.z);
    }
    return this;
  }

  /** Straight staircase rising along `dir` (unit XZ). Each step gets a collider; a hidden ramp smooths movement. */
  stairs(x: number, y: number, z: number, yaw: number, width: number, steps: number, rise: number, run: number, m: MatName) {
    const dx = Math.sin(yaw), dz = Math.cos(yaw);
    for (let i = 0; i < steps; i++) {
      const h = rise * (i + 1);
      const cx = x + dx * run * (i + 0.5), cz = z + dz * run * (i + 0.5);
      this.box(cx, y + h / 2, cz, width, h, run, m, { rotY: yaw, collide: false });
    }
    // Ramp collider for smooth traversal.
    const len = run * steps, height = rise * steps;
    const ang = Math.atan2(height, len);
    const hyp = Math.hypot(len, height);
    const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(-ang, yaw, 0, 'YXZ'));
    const c = new THREE.Vector3(x + dx * len / 2, y + height / 2 - 0.12, z + dz * len / 2);
    this.physics.addBoxQ(c, new THREE.Vector3(width / 2, 0.1, hyp / 2), q);
    return this;
  }

  /** Sloped slab (ramp) from (x,y,z) rising `height` over `len` along yaw. */
  ramp(x: number, y: number, z: number, yaw: number, width: number, len: number, height: number, thick: number, m: MatName) {
    const ang = Math.atan2(height, len);
    const hyp = Math.hypot(len, height);
    const dx = Math.sin(yaw), dz = Math.cos(yaw);
    const c = new THREE.Vector3(x + dx * len / 2, y + height / 2, z + dz * len / 2);
    const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(-ang, yaw, 0, 'YXZ'));
    const g = new THREE.BoxGeometry(width, thick, hyp);
    const uv = g.getAttribute('uv') as THREE.BufferAttribute;
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * width, uv.getY(i) * hyp);
    g.applyMatrix4(new THREE.Matrix4().compose(c, q, new THREE.Vector3(1, 1, 1)));
    this.add(g, this.mat(m), c, {});
    this.physics.addBoxQ(c, new THREE.Vector3(width / 2, thick / 2, hyp / 2), q);
    return this;
  }

  /** Invisible blocking wall (characters only; camera ignores). */
  wall(cx: number, cy: number, cz: number, sx: number, sy: number, sz: number, rotY = 0) {
    this.physics.addBox(cx, cy, cz, sx / 2, sy / 2, sz / 2, rotY, G_INVISIBLE);
    return this;
  }

  /** Collider without visuals that blocks camera too. */
  solidCollider(cx: number, cy: number, cz: number, sx: number, sy: number, sz: number, rotY = 0) {
    this.physics.addBox(cx, cy, cz, sx / 2, sy / 2, sz / 2, rotY, G_WORLD);
    return this;
  }

  /** Unmerged object (animated, interactive or unique). */
  object(o: THREE.Object3D, shadow = true) {
    o.traverse((c) => {
      const m = c as THREE.Mesh;
      if (m.isMesh) {
        m.castShadow = shadow && !(m.material as THREE.Material).transparent;
        m.receiveShadow = true;
      }
    });
    this.root.add(o);
    return o;
  }

  pointLight(x: number, y: number, z: number, color: number, intensity: number, distance: number, decay = 2): THREE.PointLight | null {
    if (this.lightCount >= this.lightBudget) return null;
    const l = new THREE.PointLight(color, intensity, distance, decay);
    l.position.set(x, y, z);
    this.root.add(l);
    this.lightCount++;
    this.stats.lights = this.lightCount;
    return l;
  }

  spotLight(x: number, y: number, z: number, tx: number, ty: number, tz: number, color: number, intensity: number, distance: number, angle: number): THREE.SpotLight | null {
    if (this.lightCount >= this.lightBudget) return null;
    const l = new THREE.SpotLight(color, intensity, distance, angle, 0.5, 1.6);
    l.position.set(x, y, z);
    l.target.position.set(tx, ty, tz);
    this.root.add(l, l.target);
    this.lightCount++;
    this.stats.lights = this.lightCount;
    return l;
  }

  /** Additive glow decal on a surface (fake light pool). */
  glowDecal(x: number, y: number, z: number, size: number, color: number, intensity = 1, normal: 'up' | 'x' | 'z' = 'up') {
    const g = new THREE.PlaneGeometry(size, size);
    if (normal === 'up') g.rotateX(-Math.PI / 2);
    else if (normal === 'x') g.rotateY(Math.PI / 2);
    const m = new THREE.MeshBasicMaterial({ map: glowTexture(), color: new THREE.Color(color).multiplyScalar(intensity), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 });
    const mesh = new THREE.Mesh(g, m);
    mesh.position.set(x, y, z);
    mesh.renderOrder = 2;
    this.root.add(mesh);
    return mesh;
  }

  /** Billboard-ish additive glow sprite (lamp halos, distant lights). */
  glowSprite(x: number, y: number, z: number, size: number, color: number, intensity = 1) {
    const m = new THREE.SpriteMaterial({ map: glowTexture(), color: new THREE.Color(color).multiplyScalar(intensity), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true });
    const s = new THREE.Sprite(m);
    s.position.set(x, y, z);
    s.scale.setScalar(size);
    s.renderOrder = 3;
    this.root.add(s);
    return s;
  }

  /** Instanced mesh for repeated props. */
  instanced(geo: THREE.BufferGeometry, m: MatName | THREE.Material, matrices: THREE.Matrix4[], shadow = true) {
    const im = new THREE.InstancedMesh(geo, this.mat(m), matrices.length);
    matrices.forEach((mm, i) => im.setMatrixAt(i, mm));
    im.instanceMatrix.needsUpdate = true;
    im.castShadow = shadow;
    im.receiveShadow = true;
    im.computeBoundingSphere();
    this.root.add(im);
    return im;
  }

  /** Merge all buckets into meshes. Call once after building. */
  finalize() {
    for (const b of this.buckets.values()) {
      if (!b.geos.length) continue;
      const merged = b.geos.length === 1 ? b.geos[0] : mergeGeometries(b.geos, false);
      if (!merged) continue;
      merged.computeBoundingSphere();
      merged.computeBoundingBox();
      const mesh = new THREE.Mesh(merged, b.mat);
      mesh.castShadow = b.shadow && !(b.mat as THREE.Material).transparent && !(b.mat instanceof THREE.MeshBasicMaterial);
      mesh.receiveShadow = b.receive && !(b.mat instanceof THREE.MeshBasicMaterial);
      mesh.matrixAutoUpdate = false;
      mesh.updateMatrix();
      if ((b.mat as THREE.Material).transparent) mesh.renderOrder = 1;
      this.root.add(mesh);
      this.stats.meshes++;
      this.stats.triangles += (merged.index?.count ?? merged.getAttribute('position').count) / 3;
      for (const g of b.geos) if (g !== merged) g.dispose();
    }
    this.buckets.clear();
  }
}
