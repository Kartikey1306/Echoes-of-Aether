import RAPIER from '@dimforge/rapier3d-compat';
import * as THREE from 'three';

// Collision membership bits.
export const G_WORLD = 1 << 0;
export const G_PLAYER = 1 << 1;
export const G_ENEMY = 1 << 2;
export const G_NPC = 1 << 3;
export const G_INVISIBLE = 1 << 4; // blocks characters, ignored by camera and projectiles
export const G_COMPANION = 1 << 5;
export const G_ALL = 0xffff;

export const groups = (membership: number, filter: number) => ((membership & 0xffff) << 16) | (filter & 0xffff);

export interface RayHit {
  point: THREE.Vector3;
  normal: THREE.Vector3;
  distance: number;
  collider: RAPIER.Collider;
}

let initialized = false;

export class Physics {
  world!: RAPIER.World;
  readonly gravity = -22;
  private ray!: RAPIER.Ray;
  /** Number of static colliders in the current zone (debug overlay). */
  staticCount = 0;

  static async init() {
    if (initialized) return;
    await RAPIER.init();
    initialized = true;
  }

  constructor() {
    this.reset();
  }

  reset() {
    if (this.world) this.world.free();
    this.world = new RAPIER.World({ x: 0, y: this.gravity, z: 0 });
    this.ray = new RAPIER.Ray({ x: 0, y: 0, z: 0 }, { x: 0, y: -1, z: 0 });
    this.staticCount = 0;
  }

  step(dt: number) {
    this.world.timestep = Math.min(dt, 1 / 30);
    this.world.step();
  }

  /** Static oriented box. Center and half extents in world units. */
  addBox(cx: number, cy: number, cz: number, hx: number, hy: number, hz: number, rotY = 0, membership = G_WORLD): RAPIER.Collider {
    const desc = RAPIER.ColliderDesc.cuboid(Math.max(0.01, hx), Math.max(0.01, hy), Math.max(0.01, hz))
      .setTranslation(cx, cy, cz)
      .setCollisionGroups(groups(membership, G_ALL));
    if (rotY !== 0) {
      const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), rotY);
      desc.setRotation({ x: q.x, y: q.y, z: q.z, w: q.w });
    }
    this.staticCount++;
    return this.world.createCollider(desc);
  }

  addBoxQ(center: THREE.Vector3, half: THREE.Vector3, quat: THREE.Quaternion, membership = G_WORLD): RAPIER.Collider {
    const desc = RAPIER.ColliderDesc.cuboid(Math.max(0.01, half.x), Math.max(0.01, half.y), Math.max(0.01, half.z))
      .setTranslation(center.x, center.y, center.z)
      .setRotation({ x: quat.x, y: quat.y, z: quat.z, w: quat.w })
      .setCollisionGroups(groups(membership, G_ALL));
    this.staticCount++;
    return this.world.createCollider(desc);
  }

  addCylinder(cx: number, cy: number, cz: number, radius: number, halfHeight: number, membership = G_WORLD) {
    const desc = RAPIER.ColliderDesc.cylinder(halfHeight, radius).setTranslation(cx, cy, cz).setCollisionGroups(groups(membership, G_ALL));
    this.staticCount++;
    return this.world.createCollider(desc);
  }

  /** Static triangle mesh collider from a (non-indexed or indexed) geometry already in world space. */
  addTrimesh(geom: THREE.BufferGeometry, membership = G_WORLD) {
    const pos = geom.getAttribute('position') as THREE.BufferAttribute;
    const verts = new Float32Array(pos.count * 3);
    for (let i = 0; i < pos.count; i++) {
      verts[i * 3] = pos.getX(i);
      verts[i * 3 + 1] = pos.getY(i);
      verts[i * 3 + 2] = pos.getZ(i);
    }
    let idx: Uint32Array;
    if (geom.index) idx = new Uint32Array(geom.index.array);
    else {
      idx = new Uint32Array(pos.count);
      for (let i = 0; i < pos.count; i++) idx[i] = i;
    }
    const desc = RAPIER.ColliderDesc.trimesh(verts, idx).setCollisionGroups(groups(membership, G_ALL));
    this.staticCount++;
    return this.world.createCollider(desc);
  }

  removeCollider(c: RAPIER.Collider) {
    this.world.removeCollider(c, false);
  }

  createCharacter(pos: THREE.Vector3, radius: number, height: number, membership: number, collideWith: number) {
    return new CharacterBody(this, pos, radius, height, membership, collideWith);
  }

  /** Raycast against the given membership mask (default: solid world). */
  raycast(origin: THREE.Vector3, dir: THREE.Vector3, maxDist: number, mask = G_WORLD | G_INVISIBLE, exclude?: RAPIER.Collider): RayHit | null {
    this.ray.origin = { x: origin.x, y: origin.y, z: origin.z };
    this.ray.dir = { x: dir.x, y: dir.y, z: dir.z };
    const hit = this.world.castRayAndGetNormal(this.ray, maxDist, true, undefined, groups(G_ALL, mask), exclude);
    if (!hit) return null;
    const t = hit.timeOfImpact;
    return {
      point: new THREE.Vector3(origin.x + dir.x * t, origin.y + dir.y * t, origin.z + dir.z * t),
      normal: new THREE.Vector3(hit.normal.x, hit.normal.y, hit.normal.z),
      distance: t,
      collider: hit.collider,
    };
  }

  /** Cheap line-of-sight test against the solid world only. */
  lineOfSight(a: THREE.Vector3, b: THREE.Vector3): boolean {
    const d = new THREE.Vector3().subVectors(b, a);
    const len = d.length();
    if (len < 0.01) return true;
    d.divideScalar(len);
    this.ray.origin = { x: a.x, y: a.y, z: a.z };
    this.ray.dir = { x: d.x, y: d.y, z: d.z };
    const hit = this.world.castRay(this.ray, len, true, undefined, groups(G_ALL, G_WORLD));
    return !hit;
  }

  /** Ground height below a point (or null when nothing within range). */
  groundAt(x: number, y: number, z: number, range = 30): number | null {
    this.ray.origin = { x, y, z };
    this.ray.dir = { x: 0, y: -1, z: 0 };
    const hit = this.world.castRay(this.ray, range, true, undefined, groups(G_ALL, G_WORLD));
    return hit ? y - hit.timeOfImpact : null;
  }
}

export class CharacterBody {
  readonly body: RAPIER.RigidBody;
  readonly collider: RAPIER.Collider;
  readonly controller: RAPIER.KinematicCharacterController;
  /** Feet position. */
  readonly position = new THREE.Vector3();
  readonly velocity = new THREE.Vector3();
  grounded = false;
  readonly radius: number;
  readonly height: number;
  private physics: Physics;
  private filterGroups: number;
  private halfSeg: number;
  /** Colliders that this body should not be blocked by (e.g. companion for the player). */
  ignore = new Set<number>();
  enabled = true;

  constructor(physics: Physics, pos: THREE.Vector3, radius: number, height: number, membership: number, collideWith: number) {
    this.physics = physics;
    this.radius = radius;
    this.height = height;
    this.halfSeg = Math.max(0.05, height / 2 - radius);
    const w = physics.world;
    this.body = w.createRigidBody(RAPIER.RigidBodyDesc.kinematicPositionBased().setTranslation(pos.x, pos.y + height / 2, pos.z));
    this.collider = w.createCollider(
      RAPIER.ColliderDesc.capsule(this.halfSeg, radius).setCollisionGroups(groups(membership, collideWith)),
      this.body,
    );
    this.filterGroups = groups(membership, collideWith);
    this.controller = w.createCharacterController(0.02);
    this.controller.setUp({ x: 0, y: 1, z: 0 });
    this.controller.enableAutostep(0.42, 0.18, false);
    this.controller.enableSnapToGround(0.35);
    this.controller.setMaxSlopeClimbAngle((52 * Math.PI) / 180);
    this.controller.setMinSlopeSlideAngle((40 * Math.PI) / 180);
    this.controller.setSlideEnabled(true);
    this.controller.setApplyImpulsesToDynamicBodies(false);
    this.position.copy(pos);
  }

  /** Move by the desired displacement, resolving collisions. Returns the actual displacement. */
  move(delta: THREE.Vector3, out = new THREE.Vector3()): THREE.Vector3 {
    if (!this.enabled) return out.set(0, 0, 0);
    const ign = this.ignore;
    const pred = ign.size ? (c: RAPIER.Collider) => !ign.has(c.handle) : undefined;
    this.controller.computeColliderMovement(this.collider, { x: delta.x, y: delta.y, z: delta.z }, RAPIER.QueryFilterFlags.EXCLUDE_SENSORS, this.filterGroups, pred);
    const m = this.controller.computedMovement();
    this.grounded = this.controller.computedGrounded();
    const t = this.body.translation();
    const nx = t.x + m.x, ny = t.y + m.y, nz = t.z + m.z;
    this.body.setNextKinematicTranslation({ x: nx, y: ny, z: nz });
    // Also move immediately so queries made later in this frame see the new position.
    this.body.setTranslation({ x: nx, y: ny, z: nz }, true);
    this.position.set(nx, ny - this.height / 2, nz);
    return out.set(m.x, m.y, m.z);
  }

  teleport(p: THREE.Vector3) {
    this.body.setTranslation({ x: p.x, y: p.y + this.height / 2, z: p.z }, true);
    this.body.setNextKinematicTranslation({ x: p.x, y: p.y + this.height / 2, z: p.z });
    this.position.copy(p);
    this.velocity.set(0, 0, 0);
    this.physics.world.propagateModifiedBodyPositionsToColliders();
  }

  dispose() {
    try {
      this.physics.world.removeCharacterController(this.controller);
      this.physics.world.removeRigidBody(this.body);
    } catch {
      /* world already freed */
    }
  }
}
