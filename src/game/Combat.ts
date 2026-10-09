import * as THREE from 'three';
import { closestOnSegment, wrapAngle } from '../core/MathUtil';
import type { Physics } from '../physics/Physics';
import { getMaterial, glowTexture } from '../render/Materials';
import type { VFX } from '../vfx/VFX';

// Combat core: combatant registry, hit queries, projectiles.

export type Team = 'player' | 'enemy';
export type HitKind = 'light' | 'heavy' | 'bolt' | 'pulse' | 'ult' | 'hazard' | 'enemy' | 'fall' | 'slam' | 'laser';

export interface HitInfo {
  damage: number;
  poise: number;
  knock: THREE.Vector3;
  kind: HitKind;
  point: THREE.Vector3;
  source: Combatant | null;
  stun?: number;
  /** Ignores shields (some boss attacks). */
  pierce?: boolean;
}

export interface Combatant {
  id: number;
  team: Team;
  name: string;
  alive: boolean;
  /** Feet position. */
  position: THREE.Vector3;
  radius: number;
  height: number;
  flying?: boolean;
  targetable(): boolean;
  /** Returns applied damage (0 when invulnerable or blocked). */
  receiveHit(h: HitInfo): number;
  aimPoint(out: THREE.Vector3): THREE.Vector3;
}

let nextId = 1;
export const newCombatId = () => nextId++;

interface Projectile {
  active: boolean;
  pos: THREE.Vector3;
  vel: THREE.Vector3;
  life: number;
  damage: number;
  team: Team;
  radius: number;
  color: number;
  homing: Combatant | null;
  turn: number;
  source: Combatant | null;
  mesh: THREE.Mesh;
  trail: THREE.Sprite;
  kind: HitKind;
  poise: number;
}

const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _c = new THREE.Vector3(), _d = new THREE.Vector3();

export class Combat {
  readonly list: Combatant[] = [];
  readonly group = new THREE.Group();
  private projectiles: Projectile[] = [];
  /** Called for every applied hit (hit-stop, camera shake, sound). */
  onHit: ((h: HitInfo, target: Combatant, applied: number) => void) | null = null;

  constructor(private physics: () => Physics, private vfx: VFX) {
    this.group.name = 'combat';
    const geo = new THREE.SphereGeometry(1, 10, 8);
    for (let i = 0; i < 48; i++) {
      const mesh = new THREE.Mesh(geo, getMaterial('emit_cyan'));
      mesh.visible = false;
      const trail = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, color: 0x5fd8ff }));
      trail.visible = false;
      this.group.add(mesh, trail);
      this.projectiles.push({ active: false, pos: new THREE.Vector3(), vel: new THREE.Vector3(), life: 0, damage: 0, team: 'player', radius: 0.2, color: 0, homing: null, turn: 0, source: null, mesh, trail, kind: 'bolt', poise: 5 });
    }
  }

  register(c: Combatant) {
    if (!this.list.includes(c)) this.list.push(c);
  }
  unregister(c: Combatant) {
    const i = this.list.indexOf(c);
    if (i >= 0) this.list.splice(i, 1);
  }

  enemiesOf(team: Team): Combatant[] {
    return this.list.filter((c) => c.team !== team && c.alive);
  }

  /** Distance from a point to a combatant's capsule surface (negative = inside). */
  capsuleDist(c: Combatant, p: THREE.Vector3): number {
    const r = c.radius;
    _a.copy(c.position).setY(c.position.y + r);
    _b.copy(c.position).setY(c.position.y + Math.max(r, c.height - r));
    closestOnSegment(p, _a, _b, _c);
    return _c.distanceTo(p) - r;
  }

  /** Closest point on the combatant's capsule axis to p. */
  closestPoint(c: Combatant, p: THREE.Vector3, out: THREE.Vector3) {
    _a.copy(c.position).setY(c.position.y + c.radius);
    _b.copy(c.position).setY(c.position.y + Math.max(c.radius, c.height - c.radius));
    return closestOnSegment(p, _a, _b, out);
  }

  /** Melee arc query. Calls `fn` for each opposing combatant inside the arc. */
  arc(team: Team, origin: THREE.Vector3, yaw: number, range: number, halfAngle: number, yMin: number, yMax: number, fn: (c: Combatant, point: THREE.Vector3) => void) {
    for (const c of this.list) {
      if (c.team === team || !c.alive || !c.targetable()) continue;
      // Horizontal check using closest point on capsule
      this.closestPoint(c, _d.copy(origin).setY(Math.min(Math.max(origin.y, c.position.y), c.position.y + c.height)), _c);
      const dx = _c.x - origin.x, dz = _c.z - origin.z;
      const dist = Math.hypot(dx, dz) - c.radius;
      if (dist > range) continue;
      const relY = c.position.y + c.height * 0.5 - origin.y;
      if (relY < yMin - c.height * 0.5 || relY > yMax + c.height * 0.5) continue;
      if (dist > 0.6) {
        const ang = Math.abs(wrapAngle(Math.atan2(dx, dz) - yaw));
        if (ang > halfAngle) continue;
      }
      const point = _c.clone();
      fn(c, point);
    }
  }

  radial(team: Team, center: THREE.Vector3, radius: number, fn: (c: Combatant, dist: number, point: THREE.Vector3) => void, yRange = 4) {
    for (const c of this.list) {
      if (c.team === team || !c.alive) continue;
      const d = this.capsuleDist(c, center);
      if (d > radius) continue;
      if (Math.abs(c.position.y + c.height / 2 - center.y) > yRange + c.height / 2) continue;
      fn(c, Math.max(0, d), this.closestPoint(c, center, new THREE.Vector3()));
    }
  }

  /** Best target in front of `from` along `dir` (soft lock / auto aim). */
  bestTarget(team: Team, from: THREE.Vector3, dir: THREE.Vector3, maxDist: number, maxAngle: number, needLos = true): Combatant | null {
    let best: Combatant | null = null;
    let bestScore = Infinity;
    for (const c of this.list) {
      if (c.team === team || !c.alive || !c.targetable()) continue;
      c.aimPoint(_a);
      _b.subVectors(_a, from);
      const d = _b.length();
      if (d > maxDist || d < 0.01) continue;
      const ang = _b.angleTo(dir);
      if (ang > maxAngle) continue;
      if (needLos && !this.physics().lineOfSight(from, _a)) continue;
      const score = d * (1 + ang * 2.2);
      if (score < bestScore) {
        bestScore = score;
        best = c;
      }
    }
    return best;
  }

  fire(o: { from: THREE.Vector3; dir: THREE.Vector3; speed: number; damage: number; team: Team; color: number; radius?: number; life?: number; homing?: Combatant | null; turn?: number; source?: Combatant | null; kind?: HitKind; poise?: number; size?: number }) {
    let p = this.projectiles.find((x) => !x.active);
    if (!p) p = this.projectiles[0];
    p.active = true;
    p.pos.copy(o.from);
    p.vel.copy(o.dir).normalize().multiplyScalar(o.speed);
    p.life = o.life ?? 2.5;
    p.damage = o.damage;
    p.team = o.team;
    p.radius = o.radius ?? 0.25;
    p.color = o.color;
    p.homing = o.homing ?? null;
    p.turn = o.turn ?? 0;
    p.source = o.source ?? null;
    p.kind = o.kind ?? 'bolt';
    p.poise = o.poise ?? 6;
    const size = o.size ?? 0.12;
    p.mesh.visible = true;
    p.mesh.scale.setScalar(size);
    p.mesh.material = getMaterial(o.color === 0xff5a4a || o.team === 'enemy' ? 'emit_red' : 'emit_cyan');
    p.trail.visible = true;
    p.trail.scale.setScalar(size * 8);
    (p.trail.material as THREE.SpriteMaterial).color.set(o.color);
    p.mesh.position.copy(p.pos);
    p.trail.position.copy(p.pos);
    this.vfx.flash(o.from, 0.8, o.color, 0.08);
  }

  update(dt: number) {
    const phys = this.physics();
    for (const p of this.projectiles) {
      if (!p.active) continue;
      p.life -= dt;
      if (p.life <= 0) {
        this.kill(p);
        continue;
      }
      if (p.homing && p.homing.alive && p.turn > 0) {
        p.homing.aimPoint(_a);
        _b.subVectors(_a, p.pos).normalize().multiplyScalar(p.vel.length());
        p.vel.lerp(_b, Math.min(1, p.turn * dt)).setLength(_b.length());
      }
      const step = p.vel.length() * dt;
      _d.copy(p.vel).normalize();
      // World collision
      const hit = phys.raycast(p.pos, _d, step + p.radius);
      // Combatant collision (swept: sample along the step)
      let struck: Combatant | null = null;
      const samples = Math.max(1, Math.ceil(step / 0.4));
      outer: for (let s = 1; s <= samples; s++) {
        _c.copy(p.pos).addScaledVector(_d, (step * s) / samples);
        for (const c of this.list) {
          if (c.team === p.team || !c.alive || !c.targetable()) continue;
          if (this.capsuleDist(c, _c) <= p.radius) {
            struck = c;
            break outer;
          }
        }
      }
      if (struck && (!hit || struck.position.distanceTo(p.pos) <= hit.distance + 1)) {
        const point = _c.clone();
        const applied = struck.receiveHit({ damage: p.damage, poise: p.poise, knock: _d.clone().multiplyScalar(2), kind: p.kind, point, source: p.source });
        if (applied > 0) this.onHit?.({ damage: applied, poise: p.poise, knock: _d.clone(), kind: p.kind, point, source: p.source }, struck, applied);
        this.vfx.sparks(point, _d.clone().negate(), 12, p.color, 5);
        this.vfx.flash(point, 1.2, p.color, 0.1);
        this.kill(p);
        continue;
      }
      if (hit) {
        this.vfx.sparks(hit.point, hit.normal, 10, p.color, 4);
        this.vfx.flash(hit.point, 0.9, p.color, 0.08);
        this.kill(p);
        continue;
      }
      p.pos.addScaledVector(p.vel, dt);
      p.mesh.position.copy(p.pos);
      p.trail.position.copy(p.pos).addScaledVector(_d, -0.15);
    }
  }

  private kill(p: Projectile) {
    p.active = false;
    p.mesh.visible = false;
    p.trail.visible = false;
  }

  clearProjectiles() {
    for (const p of this.projectiles) this.kill(p);
  }

  activeProjectiles() {
    return this.projectiles.filter((p) => p.active).length;
  }
}
