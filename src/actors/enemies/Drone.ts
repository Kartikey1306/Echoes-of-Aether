import * as THREE from 'three';
import { clamp, damp, dampAngle, distXZ, yawTo } from '../../core/MathUtil';
import { G_WORLD } from '../../physics/Physics';
import type { HitInfo } from '../../game/Combat';
import type { EnemyDef } from '../../game/Data';
import { Enemy, type EnemyEnv } from './Enemy';

// Aether Drone: flying ranged enemy.
// idle -> patrol -> (detect) alert -> pursue <-> attack (charge + burst) / dive; damaged/stagger; destroyed.

export class Drone extends Enemy {
  private body3 = new THREE.Group();
  private rotors: THREE.Object3D[] = [];
  private eyeMat: THREE.MeshBasicMaterial;
  private shellMat: THREE.MeshStandardMaterial;
  private altitude = 4.5;
  private orbitDir = Math.random() < 0.5 ? -1 : 1;
  private fireCd = 1.5 + Math.random();
  private burstLeft = 0;
  private burstT = 0;
  private flashT = 0;
  private patrolA = Math.random() * Math.PI * 2;
  private diveCd = 6 + Math.random() * 4;
  private diving = 0;
  private spin = 0;
  private falling = false;
  private vy = 0;
  private pitch = 0;
  private roll = 0;
  ceiling = 999;
  hum = 0;

  constructor(def: EnemyDef, env: EnemyEnv) {
    super(def, env);
    this.flying = true;
    this.radius = 0.55;
    this.height = 0.9;
    this.shellMat = new THREE.MeshStandardMaterial({ color: 0x2b3036, roughness: 0.35, metalness: 0.8 });
    const frame = new THREE.MeshStandardMaterial({ color: 0x5a6068, roughness: 0.4, metalness: 0.85 });
    this.eyeMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(0x5fd8ff).multiplyScalar(3) });
    const core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.42, 2).scale(1, 0.62, 1.1), this.shellMat);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.58, 0.06, 8, 32), frame);
    ring.rotation.x = Math.PI / 2;
    const eye = new THREE.Mesh(new THREE.SphereGeometry(0.13, 16, 10), this.eyeMat);
    eye.position.set(0, 0.02, 0.42);
    const visor = new THREE.Mesh(new THREE.TorusGeometry(0.16, 0.03, 6, 20), frame);
    visor.position.set(0, 0.02, 0.43);
    const gun = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.055, 0.42, 8).rotateX(Math.PI / 2), frame);
    gun.position.set(0, -0.2, 0.32);
    const under = new THREE.Mesh(new THREE.CircleGeometry(0.16, 16).rotateX(Math.PI / 2), this.eyeMat);
    under.position.y = -0.27;
    this.body3.add(core, ring, eye, visor, gun, under);
    for (let i = 0; i < 4; i++) {
      const a = (i / 4) * Math.PI * 2 + Math.PI / 4;
      const arm = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.05, 0.5), frame);
      arm.position.set(Math.sin(a) * 0.55, 0.05, Math.cos(a) * 0.55);
      arm.rotation.y = a;
      const rotor = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.02, 16), new THREE.MeshBasicMaterial({ color: 0x202428, transparent: true, opacity: 0.55, depthWrite: false }));
      rotor.position.set(Math.sin(a) * 0.82, 0.1, Math.cos(a) * 0.82);
      this.body3.add(arm, rotor);
      this.rotors.push(rotor);
    }
    this.body3.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh) m.castShadow = true;
    });
    this.root.add(this.body3);
  }

  spawn(pos: THREE.Vector3, yaw: number) {
    super.spawn(pos, yaw);
    this.altitude = clamp(pos.y - (this.env.physics().groundAt(pos.x, pos.y, pos.z, 20) ?? 0), 3, 7);
    // Indoor ceiling
    const up = this.env.physics().raycast(pos, new THREE.Vector3(0, 1, 0), 30, G_WORLD);
    this.ceiling = up ? up.point.y - 0.8 : 999;
  }

  aimPoint(out: THREE.Vector3) {
    return out.copy(this.position);
  }

  protected eye(out: THREE.Vector3) {
    return out.copy(this.position);
  }

  protected onHurt(h: HitInfo) {
    this.flashT = 0.12;
    this.env.vfx.sparks(h.point, null, 6, 0xffc070, 4);
    this.env.sfx('enemy_hit_metal', this.position);
    this.knock(h.knock.clone().multiplyScalar(1.3));
    this.roll += (Math.random() - 0.5) * 0.8;
  }

  protected stagger(h: HitInfo) {
    super.stagger(h);
    this.spin = 9;
    this.burstLeft = 0;
  }

  protected die(h: HitInfo | null) {
    super.die(h);
    this.falling = true;
    this.vy = 1.5;
    this.spin = 10;
    this.env.sfx('drone_death', this.position);
    this.env.vfx.sparks(this.position, null, 18, 0xffb060, 6);
  }

  private groundBelow(): number {
    const g = this.env.physics().groundAt(this.position.x, this.position.y + 0.5, this.position.z, 30);
    return g ?? this.home.y - this.altitude;
  }

  protected updateAI(dt: number) {
    const p = this.env.player();
    const ground = this.groundBelow();
    let goal = this.tmp.copy(this.home);
    let speed = this.def.speed;
    let wantAlt = this.altitude;
    this.fireCd -= dt;
    this.diveCd -= dt;
    switch (this.state) {
      case 'idle':
        if (this.stateT > 2) this.enter('patrol');
        goal.copy(this.home);
        speed = 1.5;
        break;
      case 'patrol': {
        this.patrolA += dt * 0.35;
        goal.set(this.home.x + Math.cos(this.patrolA) * 5, 0, this.home.z + Math.sin(this.patrolA) * 5);
        speed = 2.2;
        break;
      }
      case 'alert':
        this.velocity.multiplyScalar(Math.exp(-4 * dt));
        if (p) this.yaw = dampAngle(this.yaw, yawTo(this.position, p.position), 10, dt);
        if (this.stateT > 0.5) this.enter('pursue');
        this.move(dt, this.position, 0, wantAlt, ground);
        return;
      case 'pursue':
      case 'attack': {
        if (!p) { this.enter('return'); break; }
        const d = distXZ(this.position, p.position);
        const toward = this.tmp2.subVectors(p.position, this.position).setY(0).normalize();
        const side = new THREE.Vector3(toward.z, 0, -toward.x).multiplyScalar(this.orbitDir);
        const ideal = this.diving > 0 ? 2.2 : 9;
        goal.copy(this.position).addScaledVector(toward, (d - ideal) * 0.9).addScaledVector(side, 4);
        speed = this.diving > 0 ? 8 : this.def.speed;
        wantAlt = this.diving > 0 ? 1.9 : this.altitude;
        if (Math.random() < dt * 0.2) this.orbitDir *= -1;
        this.yaw = dampAngle(this.yaw, yawTo(this.position, p.position), 8, dt);
        // Dive: swoop low near the player (opens a melee window), then climb.
        if (this.diving > 0) {
          this.diving -= dt;
          if (d < 3.2 && this.diving > 0.4) {
            this.meleeTouch();
          }
        } else if (this.diveCd <= 0 && d < 14 && this.canSeePlayer) {
          this.diving = 2.2;
          this.diveCd = 8 + Math.random() * 5;
          this.env.sfx('drone_dive', this.position);
        }
        // Firing
        if (this.burstLeft > 0) {
          this.burstT -= dt;
          if (this.burstT <= 0) {
            this.burstLeft--;
            this.burstT = 0.22;
            this.shoot(p);
            if (this.burstLeft === 0) {
              this.releaseToken();
              this.fireCd = (1.8 + Math.random() * 1.2) / this.env.difficulty().aggression;
            }
          }
        } else if (this.fireCd <= 0 && this.canSeePlayer && d < this.def.attackRange + 4 && this.diving <= 0) {
          if (this.requestToken()) {
            this.burstLeft = 2;
            this.burstT = 0.55; // charge time (telegraph)
            this.flashT = 0.55;
            this.env.sfx('drone_charge', this.position);
          } else this.fireCd = 0.6;
        }
        break;
      }
      case 'stagger':
        this.velocity.multiplyScalar(Math.exp(-3 * dt));
        if (this.stateT > 0.9) this.enter(this.aggro ? 'pursue' : 'idle');
        this.move(dt, this.position, 0, wantAlt - 0.8, ground);
        return;
      case 'return':
        goal.copy(this.home);
        speed = 3.5;
        this.health = Math.min(this.maxHealth, this.health + this.maxHealth * 0.25 * dt);
        if (distXZ(this.position, this.home) < 1.5 || this.stateT > 12) {
          if (this.stateT > 12) this.position.copy(this.home);
          this.enter('idle');
        }
        if (this.canSeePlayer) this.setAggro();
        break;
    }
    // Stay inside the arena
    if (this.arena) {
      const dc = distXZ(goal, this.arena.center);
      if (dc > this.arena.radius) {
        goal.sub(this.arena.center).setY(0).setLength(this.arena.radius).add(this.arena.center);
      }
    }
    this.move(dt, goal, speed, wantAlt, ground);
  }

  private meleeTouch() {
    // Diving drones ram the player if they get very close.
    const p = this.env.player();
    if (!p) return;
    if (this.position.distanceTo(p.aimPoint(this.tmp2)) < 1.4) {
      const dir = this.tmp2.subVectors(p.position, this.position).setY(0).normalize();
      const applied = p.receiveHit({ damage: this.def.damage * 0.8, poise: 10, knock: dir.multiplyScalar(4), kind: 'enemy', point: this.position.clone(), source: this });
      if (applied > 0) this.diving = Math.min(this.diving, 0.3);
    }
  }

  private shoot(p: { position: THREE.Vector3; velocity: THREE.Vector3; aimPoint: (o: THREE.Vector3) => THREE.Vector3 }) {
    const from = this.position.clone().add(new THREE.Vector3(Math.sin(this.yaw) * 0.6, -0.2, Math.cos(this.yaw) * 0.6));
    const target = p.aimPoint(new THREE.Vector3());
    // Lead the target slightly (imperfect so strafing works).
    const t = from.distanceTo(target) / 24;
    target.addScaledVector(p.velocity, t * 0.55);
    target.x += (Math.random() - 0.5) * 0.8;
    target.z += (Math.random() - 0.5) * 0.8;
    const dir = target.sub(from).normalize();
    this.env.combat.fire({ from, dir, speed: 24, damage: this.def.damage, team: 'enemy', color: 0xff5a4a, source: this, kind: 'enemy', poise: 8, size: 0.12, life: 3 });
    this.env.sfx('drone_shot', from);
  }

  private move(dt: number, goal: THREE.Vector3, speed: number, wantAlt: number, ground: number) {
    const ph = this.env.physics();
    const to = this.tmp2.subVectors(goal, this.position).setY(0);
    const d = to.length();
    if (d > 0.3 && speed > 0) to.multiplyScalar(Math.min(speed, d * 2) / d);
    else to.set(0, 0, 0);
    // Obstacle avoidance
    if (to.lengthSq() > 0.01) {
      const dir = to.clone().normalize();
      const hit = ph.raycast(this.position, dir, 2.5, G_WORLD);
      if (hit) {
        to.addScaledVector(hit.normal, speed * 1.2);
        wantAlt += 1.5;
      }
    }
    this.velocity.x = damp(this.velocity.x, to.x, 3, dt);
    this.velocity.z = damp(this.velocity.z, to.z, 3, dt);
    const targetY = Math.min(ground + wantAlt + Math.sin(this.stateT * 2 + this.id) * 0.25, this.ceiling);
    this.velocity.y = damp(this.velocity.y, (targetY - this.position.y) * 2.2, 4, dt);
    this.position.addScaledVector(this.velocity, dt);
    // Never clip into the ground
    if (this.position.y < ground + 0.8) {
      this.position.y = ground + 0.8;
      this.velocity.y = Math.max(0, this.velocity.y);
    }
    // Tilt in the direction of travel
    const local = this.velocity.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), -this.yaw);
    this.pitch = damp(this.pitch, clamp(local.z * 0.06, -0.4, 0.4), 6, dt);
    this.roll = damp(this.roll, clamp(-local.x * 0.06, -0.4, 0.4), 6, dt);
  }

  protected updateDead(dt: number) {
    if (this.falling) {
      this.vy -= 18 * dt;
      this.position.y += this.vy * dt;
      this.position.addScaledVector(this.velocity, dt);
      this.velocity.multiplyScalar(Math.exp(-1 * dt));
      this.spin = Math.max(2, this.spin - dt * 3);
      this.yaw += this.spin * dt;
      if (Math.random() < 0.5) this.env.vfx.smokePuff(this.position, 1, 0x15171a, 0.5);
      const g = this.env.physics().groundAt(this.position.x, this.position.y + 0.5, this.position.z, 3);
      if ((g !== null && this.position.y <= g + 0.3) || this.deathT > 2.5) {
        this.falling = false;
        this.env.vfx.explode(this.position.clone().setY((g ?? this.position.y) + 0.4), 0.9, 0x5fd8ff);
        this.env.sfx('explosion', this.position);
        this.env.shake(0.15);
        this.root.visible = false;
      }
    }
    if (this.deathT > 3) this.dispose();
  }

  protected updateModel(dt: number) {
    this.spin = Math.max(0, this.spin - dt * 6);
    for (const r of this.rotors) r.rotation.y += dt * 40;
    this.body3.rotation.set(this.pitch, this.state === 'stagger' ? this.stateT * this.spin : 0, this.roll);
    const hostile = this.aggro;
    const base = hostile ? 0xff4a3a : 0x5fd8ff;
    this.flashT = Math.max(0, this.flashT - dt);
    const charge = this.burstLeft > 0 && this.burstT > 0.25 ? 1 + Math.sin(this.stateT * 40) * 0.5 + 1.5 : 1;
    this.eyeMat.color.set(base).multiplyScalar(3 * charge);
    this.shellMat.emissive.setRGB(this.flashT > 0 && this.burstLeft === 0 ? 0.8 : 0, this.flashT > 0 && this.burstLeft === 0 ? 0.8 : 0, this.flashT > 0 && this.burstLeft === 0 ? 0.8 : 0);
  }

  dispose() {
    super.dispose();
    this.body3.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh) m.geometry.dispose();
    });
    this.shellMat.dispose();
    this.eyeMat.dispose();
  }
}
