import * as THREE from 'three';
import { clamp, damp, dampAngle, distXZ, yawTo } from '../../core/MathUtil';
import { G_ENEMY, G_INVISIBLE, G_NPC, G_PLAYER, G_WORLD, type CharacterBody, type Physics } from '../../physics/Physics';
import { newCombatId, type Combat, type Combatant, type HitInfo } from '../../game/Combat';
import type { EnemyDef } from '../../game/Data';
import type { VFX } from '../../vfx/VFX';

// Common enemy behaviour: perception, alert sharing, leash/return, stuck recovery, poise & stagger, death.

export interface EnemyEnv {
  physics: () => Physics;
  combat: Combat;
  vfx: VFX;
  scene: () => THREE.Scene;
  player: () => (Combatant & { velocity: THREE.Vector3 }) | null;
  sfx: (id: string, pos?: THREE.Vector3, vol?: number) => void;
  difficulty: () => { enemyDamage: number; enemyHealth: number; aggression: number };
  echoActive: () => boolean;
  onKilled: (e: Enemy) => void;
  onAggro: (e: Enemy) => void;
  shake: (a: number) => void;
  /** Attack tokens limit how many enemies commit to attacks at once. */
  requestToken: (e: Enemy) => boolean;
  releaseToken: (e: Enemy) => void;
  cameraSees: (p: THREE.Vector3) => boolean;
  dropItem: (item: string, pos: THREE.Vector3) => void;
}

export type EnemyState = 'idle' | 'patrol' | 'alert' | 'pursue' | 'attack' | 'recover' | 'stagger' | 'return' | 'dead' | 'phase' | 'special';

export abstract class Enemy implements Combatant {
  readonly id = newCombatId();
  readonly team = 'enemy' as const;
  readonly def: EnemyDef;
  readonly name: string;
  alive = true;
  readonly position = new THREE.Vector3();
  radius = 0.5;
  height = 2;
  flying = false;
  yaw = 0;
  readonly velocity = new THREE.Vector3();
  health: number;
  maxHealth: number;
  poise: number;
  maxPoise: number;
  state: EnemyState = 'idle';
  stateT = 0;
  readonly home = new THREE.Vector3();
  homeYaw = 0;
  leash: number;
  arena: { center: THREE.Vector3; radius: number } | null = null;
  encounterId: string | null = null;
  readonly root = new THREE.Group();
  body: CharacterBody | null = null;
  aggro = false;
  lastSeen = 0;
  private seeT = Math.random() * 0.25;
  canSeePlayer = false;
  protected env: EnemyEnv;
  protected hasToken = false;
  private stuckT = 0;
  private lastPos = new THREE.Vector3();
  private sideStepT = 0;
  private sideStepDir = 1;
  deathT = 0;
  /** Time since last damage (for health bar visibility). */
  sinceHit = 99;
  invulnerable = false;
  stunT = 0;
  protected tmp = new THREE.Vector3();
  protected tmp2 = new THREE.Vector3();
  disposed = false;

  constructor(def: EnemyDef, env: EnemyEnv) {
    this.def = def;
    this.name = def.name;
    this.env = env;
    const d = env.difficulty();
    this.maxHealth = def.health * d.enemyHealth;
    this.health = this.maxHealth;
    this.maxPoise = def.poise;
    this.poise = def.poise;
    this.leash = def.leash;
    this.root.name = 'enemy:' + def.id;
  }

  spawn(pos: THREE.Vector3, yaw: number) {
    this.position.copy(pos);
    this.home.copy(pos);
    this.yaw = yaw;
    this.homeYaw = yaw;
    this.lastPos.copy(pos);
    if (!this.flying) {
      this.body = this.env.physics().createCharacter(pos, this.radius, this.height, G_ENEMY, G_WORLD | G_INVISIBLE | G_PLAYER | G_ENEMY | G_NPC);
    }
    this.env.scene().add(this.root);
    this.env.combat.register(this);
    this.syncModel();
  }

  targetable() {
    return this.alive && !this.invulnerable;
  }

  aimPoint(out: THREE.Vector3) {
    return out.copy(this.position).setY(this.position.y + this.height * 0.6);
  }

  // ------------------------------------------------------------------ Damage
  receiveHit(h: HitInfo): number {
    if (!this.alive || this.invulnerable) return 0;
    const staggerBonus = this.state === 'stagger' ? 1.25 : 1;
    const dmg = h.damage * staggerBonus * this.damageTakenMul(h);
    if (dmg <= 0) return 0;
    this.health -= dmg;
    this.sinceHit = 0;
    this.onHurt(h, dmg);
    if (!this.aggro) this.setAggro();
    if (this.health <= 0) {
      this.die(h);
      return dmg;
    }
    this.poise -= h.poise;
    if (h.stun) this.stunT = Math.max(this.stunT, h.stun);
    if (this.poise <= 0) {
      this.poise = this.maxPoise;
      this.stagger(h);
    } else {
      this.knock(h.knock.clone().multiplyScalar(0.35));
    }
    return dmg;
  }

  /** Multiplier for incoming damage (shields, armour). */
  protected damageTakenMul(_h: HitInfo): number {
    return 1;
  }

  protected onHurt(_h: HitInfo, _dmg: number) {}

  protected knock(v: THREE.Vector3) {
    this.velocity.x += v.x;
    this.velocity.z += v.z;
  }

  protected stagger(h: HitInfo) {
    this.knock(h.knock);
    this.releaseToken();
    this.enter('stagger');
  }

  protected die(h: HitInfo | null) {
    this.alive = false;
    this.health = 0;
    this.releaseToken();
    this.enter('dead');
    this.env.combat.unregister(this);
    this.body?.dispose();
    this.body = null;
    if (h) this.knock(h.knock.clone().multiplyScalar(0.6));
    for (const d of this.def.drops) if (Math.random() < d.chance) this.env.dropItem(d.item, this.position.clone().setY(this.position.y + 0.6));
    this.env.onKilled(this);
  }

  setAggro() {
    if (this.aggro || !this.alive) return;
    this.aggro = true;
    this.env.onAggro(this);
    if (this.state === 'idle' || this.state === 'patrol' || this.state === 'return') this.enter('alert');
  }

  enter(s: EnemyState) {
    this.state = s;
    this.stateT = 0;
  }

  protected requestToken(): boolean {
    if (this.hasToken) return true;
    this.hasToken = this.env.requestToken(this);
    return this.hasToken;
  }
  protected releaseToken() {
    if (this.hasToken) this.env.releaseToken(this);
    this.hasToken = false;
  }

  // ------------------------------------------------------------------ Perception
  protected eye(out: THREE.Vector3) {
    return out.copy(this.position).setY(this.position.y + this.height * 0.85);
  }

  private perceive(dt: number) {
    this.seeT -= dt;
    if (this.seeT > 0) return;
    this.seeT = 0.22;
    const p = this.env.player();
    if (!p || !p.alive || !p.targetable()) {
      this.canSeePlayer = false;
      return;
    }
    const d = this.position.distanceTo(p.position);
    if (d > this.def.sight * (this.aggro ? 1.5 : 1)) {
      this.canSeePlayer = false;
      return;
    }
    // Non-alert enemies only see in a forward cone (unless very close).
    if (!this.aggro && d > 6) {
      const ang = Math.abs(Math.atan2(Math.sin(yawTo(this.position, p.position) - this.yaw), Math.cos(yawTo(this.position, p.position) - this.yaw)));
      if (ang > 1.4 && !this.flying) {
        this.canSeePlayer = false;
        return;
      }
    }
    this.canSeePlayer = this.env.physics().lineOfSight(this.eye(this.tmp), p.aimPoint(this.tmp2));
    if (this.canSeePlayer) this.lastSeen = 0;
  }

  // ------------------------------------------------------------------ Update
  update(dt: number) {
    this.stateT += dt;
    this.sinceHit += dt;
    this.lastSeen += dt;
    if (this.state === 'dead') {
      this.deathT += dt;
      this.updateDead(dt);
      this.syncModel();
      return;
    }
    if (this.stunT > 0) {
      this.stunT -= dt;
      this.velocity.multiplyScalar(Math.exp(-6 * dt));
      this.integrate(dt, this.velocity);
      this.syncModel();
      this.updateModel(dt);
      return;
    }
    this.perceive(dt);
    if (this.canSeePlayer && !this.aggro) this.setAggro();
    // Leash: lose interest when the player leaves the area for a while.
    const p = this.env.player();
    if (this.aggro && p) {
      const fromHome = distXZ(p.position, this.arena?.center ?? this.home);
      const limit = this.arena ? this.arena.radius + 8 : this.leash;
      if ((fromHome > limit && this.lastSeen > 2.5) || (!p.alive) || this.lastSeen > 14) {
        this.aggro = false;
        this.releaseToken();
        this.enter('return');
      }
    }
    // Poise regen
    if (this.state !== 'stagger') this.poise = Math.min(this.maxPoise, this.poise + this.maxPoise * 0.12 * dt);
    this.updateAI(dt);
    this.syncModel();
    this.updateModel(dt);
  }

  /** Ground movement toward a goal with simple obstacle avoidance and stuck recovery. Returns remaining distance. */
  protected steerTo(goal: THREE.Vector3, speed: number, dt: number, accel = 8, face = true): number {
    const to = this.tmp.subVectors(goal, this.position).setY(0);
    const dist = to.length();
    let dir = dist > 0.001 ? to.divideScalar(dist) : to.set(0, 0, 0);
    if (dist > 0.3 && !this.flying) {
      // Feelers
      const ph = this.env.physics();
      const origin = this.tmp2.copy(this.position).setY(this.position.y + this.height * 0.4);
      const ahead = ph.raycast(origin, dir, 1.6, G_WORLD);
      if (ahead) {
        const left = dir.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), 0.8);
        const right = dir.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), -0.8);
        const hl = ph.raycast(origin, left, 2.2, G_WORLD);
        const hr = ph.raycast(origin, right, 2.2, G_WORLD);
        dir = (!hl ? left : !hr ? right : (hl.distance > hr.distance ? left : right)).normalize();
      }
      // Separation from other enemies
      for (const c of this.env.combat.list) {
        if (c === this || c.team !== 'enemy' || !c.alive) continue;
        const d = distXZ(c.position, this.position);
        if (d < 1.6 && d > 0.01) {
          dir.x += ((this.position.x - c.position.x) / d) * (1.6 - d) * 0.8;
          dir.z += ((this.position.z - c.position.z) / d) * (1.6 - d) * 0.8;
        }
      }
      if (this.sideStepT > 0) {
        this.sideStepT -= dt;
        dir.applyAxisAngle(new THREE.Vector3(0, 1, 0), this.sideStepDir * 1.2);
      }
      dir.normalize();
    }
    const want = dist > 0.25 ? speed : 0;
    this.velocity.x = damp(this.velocity.x, dir.x * want, accel, dt);
    this.velocity.z = damp(this.velocity.z, dir.z * want, accel, dt);
    if (face && want > 0.2) this.yaw = dampAngle(this.yaw, Math.atan2(dir.x, dir.z), 8, dt);
    this.integrate(dt, this.velocity);
    // Stuck detection
    const moved = distXZ(this.position, this.lastPos);
    this.lastPos.copy(this.position);
    if (want > 0.5 && moved < want * dt * 0.15) {
      this.stuckT += dt;
      if (this.stuckT > 1.0 && this.sideStepT <= 0) {
        this.sideStepT = 0.8;
        this.sideStepDir = Math.random() < 0.5 ? -1 : 1;
      }
      if (this.stuckT > 4 && !this.env.cameraSees(this.position)) {
        this.teleportHome();
      }
    } else this.stuckT = Math.max(0, this.stuckT - dt * 2);
    return dist;
  }

  protected integrate(dt: number, v: THREE.Vector3) {
    if (this.flying) {
      this.position.addScaledVector(v, dt);
      return;
    }
    if (!this.body) return;
    this.velocity.y += this.env.physics().gravity * dt;
    const m = this.body.move(this.tmp2.set(v.x * dt, this.velocity.y * dt, v.z * dt), new THREE.Vector3());
    if (this.body.grounded && this.velocity.y < 0) this.velocity.y = -1;
    this.position.copy(this.body.position);
    if (this.position.y < -50) this.teleportHome();
    return m;
  }

  teleportHome() {
    this.stuckT = 0;
    this.position.copy(this.home);
    this.velocity.set(0, 0, 0);
    this.body?.teleport(this.home);
    this.yaw = this.homeYaw;
  }

  /** Return-home behaviour shared by all enemies. */
  protected updateReturn(dt: number, speed: number) {
    const d = this.steerTo(this.home, speed, dt);
    this.health = Math.min(this.maxHealth, this.health + this.maxHealth * 0.2 * dt);
    if (d < 1 || this.stateT > 10) {
      if (d >= 1) this.teleportHome();
      this.enter('idle');
    }
    if (this.canSeePlayer) this.setAggro();
  }

  /** Visual-only vertical offset (cinematic staging). */
  visualOffsetY = 0;

  protected syncModel() {
    this.root.position.copy(this.position);
    this.root.position.y += this.visualOffsetY;
    this.root.rotation.y = this.yaw;
  }

  protected abstract updateAI(dt: number): void;
  protected abstract updateModel(dt: number): void;
  protected updateDead(dt: number) {
    if (this.deathT > 4 && !this.disposed) this.dispose();
  }

  /** Animate without thinking (cinematics). */
  updateModelOnly(dt: number) {
    this.syncModel();
    this.updateModel(dt);
  }

  facingTo(p: THREE.Vector3) {
    return Math.abs(Math.atan2(Math.sin(yawTo(this.position, p) - this.yaw), Math.cos(yawTo(this.position, p) - this.yaw)));
  }

  /** Deal damage to the player in an arc in front of this enemy. */
  protected meleeArc(range: number, halfAngle: number, damage: number, poise: number, knock: number, hitSet: Set<number>) {
    const origin = this.position.clone().setY(this.position.y + this.height * 0.5);
    this.env.combat.arc('enemy', origin, this.yaw, range, halfAngle, -2, 2.5, (c, point) => {
      if (hitSet.has(c.id)) return;
      hitSet.add(c.id);
      const dir = new THREE.Vector3().subVectors(c.position, this.position).setY(0).normalize();
      const applied = c.receiveHit({ damage, poise, knock: dir.multiplyScalar(knock), kind: 'enemy', point, source: this });
      if (applied > 0) {
        this.env.vfx.sparks(point, dir, 10, 0xff6a4a, 6);
        this.env.sfx('enemy_hit_player', point);
      }
    });
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.releaseToken();
    this.env.combat.unregister(this);
    this.body?.dispose();
    this.body = null;
    this.root.removeFromParent();
  }

  /** Health fraction for UI. */
  get hpFrac() {
    return clamp(this.health / this.maxHealth, 0, 1);
  }
}
