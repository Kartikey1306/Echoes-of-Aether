import * as THREE from 'three';
import { DEG, distXZ, dampAngle, yawTo } from '../../core/MathUtil';
import { events } from '../../core/Events';
import type { HitInfo } from '../../game/Combat';
import type { EnemyDef } from '../../game/Data';
import { getMaterial } from '../../render/Materials';
import { Enemy, type EnemyEnv } from './Enemy';
import { robotClips } from './EnemyAnims';
import { buildGuardianBody, RobotModel, robotMaterials } from './RobotModel';

// Aether Guardian. Armoured everywhere except its core, which opens after slams.
// Phase 1: slams + sweeps. Phase 2: chest laser, summons drones. Phase 3: faster, shockwave roars, summons stalkers.
// The 'vault' variant cannot be harmed: the player must survive until the blast door opens.

export interface GuardianEnv extends EnemyEnv {
  spawnMinion: (type: string, pos: THREE.Vector3, encounter: string | null) => void;
  setBoss: (on: boolean) => void;
}

interface Wave { r: number; maxR: number; speed: number; hit: boolean; mesh: THREE.Mesh; center: THREE.Vector3 }

export class Guardian extends Enemy {
  readonly model: RobotModel;
  private clips: ReturnType<typeof robotClips>;
  private core!: THREE.Mesh;
  private plates: THREE.Mesh[] = [];
  readonly vaultMode: boolean;
  phase = 1;
  private attackCd = 2.5;
  private hitSet = new Set<number>();
  private hitActive = false;
  private current: 'slam' | 'sweep' | 'laser' | 'roar' | null = null;
  private exposedT = 0;
  private waves: Wave[] = [];
  private laser: THREE.Mesh;
  private laserOn = false;
  private laserTick = 0;
  private summoned = { p2: false, p3: false };
  private announced = false;
  private noEffectT = 0;
  private genv: GuardianEnv;

  constructor(def: EnemyDef, env: GuardianEnv, vault: boolean) {
    super(def, env);
    this.genv = env;
    this.vaultMode = vault;
    this.height = 5.2;
    this.radius = 1.3;
    this.leash = 200;
    this.model = new RobotModel(5.2, robotMaterials(0x3a3f48, 0x1c1f24, vault ? 0xff5a3a : 0x5fd8ff, 3.6), 'heavy', (m) => {
      const r = buildGuardianBody(m);
      this.core = r.core;
      this.plates = r.plates;
    });
    this.root.add(this.model.root);
    this.clips = robotClips('guardian');
    this.model.animator.loco.combatIdle = this.clips.stance;
    this.laser = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 1, 10, 1, true).rotateX(Math.PI / 2).translate(0, 0, 0.5), getMaterial('emit_red'));
    this.laser.visible = false;
    if (vault) {
      this.maxHealth = 99999;
      this.health = 99999;
    }
  }

  spawn(pos: THREE.Vector3, yaw: number) {
    super.spawn(pos, yaw);
    this.env.scene().add(this.laser);
    this.setAggro();
  }

  aimPoint(out: THREE.Vector3) {
    return this.core.getWorldPosition(out);
  }

  protected damageTakenMul(h: HitInfo): number {
    if (this.vaultMode) {
      if (this.noEffectT <= 0) {
        this.noEffectT = 4;
        events.emit('ui:toast', { text: 'It shrugs it off. Survive until the blast door opens!', kind: 'warn' });
      }
      return 0;
    }
    const corePos = this.core.getWorldPosition(new THREE.Vector3());
    const nearCore = h.point.distanceTo(corePos) < 1.6 || h.kind === 'bolt';
    if (this.exposedT > 0) return nearCore || h.kind === 'pulse' || h.kind === 'ult' ? 2.4 : 1.2;
    // Armoured: light hits barely scratch it, ultimates and heavies do more.
    return h.kind === 'ult' ? 0.7 : h.kind === 'heavy' || h.kind === 'pulse' ? 0.35 : 0.18;
  }

  protected onHurt(h: HitInfo, dmg: number) {
    this.model.hitFlash(this.exposedT > 0 ? 1 : 0.35);
    this.env.sfx(this.exposedT > 0 ? 'hit_heavy' : 'shield_block', h.point);
    if (this.exposedT <= 0) this.env.vfx.sparks(h.point, null, 6, 0xffd0a0, 4);
    void dmg;
    const f = this.health / this.maxHealth;
    const newPhase = f < 0.33 ? 3 : f < 0.66 ? 2 : 1;
    if (newPhase > this.phase) {
      this.phase = newPhase;
      events.emit('boss:phase', { id: 'guardian', phase: newPhase });
      this.attackCd = 0.5;
      this.queueRoar();
    }
  }

  // Bosses don't stagger from poise; they are only exposed after slams.
  protected stagger() {
    this.poise = this.maxPoise;
  }

  protected die(h: HitInfo | null) {
    super.die(h);
    this.laserOn = false;
    this.laser.visible = false;
    this.model.animator.stopActions(0.1);
    this.model.animator.setState(this.clips.death, 0.2);
    this.env.sfx('sentinel_death', this.position);
    this.genv.setBoss(false);
  }

  protected updateDead(dt: number) {
    if (Math.random() < 0.35 && this.deathT < 2.4) this.env.vfx.explode(this.position.clone().add(new THREE.Vector3((Math.random() - 0.5) * 3, 1 + Math.random() * 3, (Math.random() - 0.5) * 3)), 0.6, 0x5fd8ff);
    if (this.deathT > 2.4 && this.deathT - dt <= 2.4) {
      this.env.vfx.explode(this.position.clone().setY(this.position.y + 2), 3, 0x5fd8ff);
      this.env.sfx('ult_impact', this.position);
      this.env.shake(0.9);
    }
    if (this.deathT > 3) this.root.position.y = this.position.y - (this.deathT - 3) * 1.2;
    if (this.deathT > 6) this.dispose();
  }

  private queueRoar() {
    if (this.current || this.state === 'dead') return;
    this.startAttack('roar');
  }

  private startAttack(kind: 'slam' | 'sweep' | 'laser' | 'roar') {
    this.current = kind;
    this.enter('attack');
    this.hitSet.clear();
    this.hitActive = false;
    const speed = (this.phase === 3 ? 1.25 : this.phase === 2 ? 1.1 : 1) * Math.min(1.2, this.env.difficulty().aggression);
    this.model.animator.play(this.clips[kind], {
      fadeIn: 0.15,
      speed,
      onEvent: (e) => this.onEvent(e),
      onEnd: () => {
        this.hitActive = false;
        this.model.telegraph = 0;
        this.laserOn = false;
        this.laser.visible = false;
        const was = this.current;
        this.current = null;
        if (this.state === 'dead') return;
        if (was === 'slam' && !this.vaultMode) {
          // Exposed window.
          this.exposedT = 3.4;
          this.enter('special');
          this.model.animator.play(this.clips.exposed, { fadeIn: 0.15 });
          this.env.sfx('door', this.position);
        } else this.enter('recover');
      },
    });
  }

  private onEvent(e: string) {
    if (e === 'telegraph') {
      this.model.telegraph = 1;
      this.env.sfx('enemy_telegraph', this.position);
    } else if (e === 'hit_start') this.hitActive = true;
    else if (e === 'hit_end') {
      this.hitActive = false;
      this.model.telegraph = 0;
    } else if (e === 'impact') {
      const center = this.position.clone().add(new THREE.Vector3(Math.sin(this.yaw) * 2.8, 0.1, Math.cos(this.yaw) * 2.8));
      // Close-range impact
      this.env.combat.radial('enemy', center, 3.6, (c) => {
        const dir = new THREE.Vector3().subVectors(c.position, center).setY(0).normalize();
        c.receiveHit({ damage: this.def.damage * 1.2, poise: 60, knock: dir.multiplyScalar(10), kind: 'slam', point: c.position.clone(), source: this });
      }, 2);
      this.spawnWave(center, this.phase >= 2 ? 16 : 13);
      this.env.vfx.sparks(center, new THREE.Vector3(0, 1, 0), 50, 0xffc080, 10);
      this.env.vfx.light(center.clone().setY(center.y + 1), 0xff9a50, 80, 0.4);
      this.env.shake(0.6);
      this.env.sfx('slam', center);
    } else if (e === 'laser_on') {
      this.laserOn = true;
      this.laser.visible = true;
      this.env.sfx('ult_charge', this.position);
    } else if (e === 'laser_off') {
      this.laserOn = false;
      this.laser.visible = false;
    } else if (e === 'roar') {
      this.env.sfx('ult_charge', this.position);
      this.env.shake(0.4);
      this.spawnWave(this.position.clone().setY(this.position.y + 0.1), 18);
      if (!this.vaultMode) {
        if (this.phase >= 2 && !this.summoned.p2) {
          this.summoned.p2 = true;
          for (const a of [-1, 1]) this.genv.spawnMinion('drone', this.position.clone().add(new THREE.Vector3(a * 8, 6, 0)), this.encounterId);
        } else if (this.phase >= 3 && !this.summoned.p3) {
          this.summoned.p3 = true;
          for (const a of [-1, 1]) this.genv.spawnMinion('stalker', this.position.clone().add(new THREE.Vector3(a * 9, 0, 4)), this.encounterId);
        }
      }
    }
  }

  private spawnWave(center: THREE.Vector3, maxR: number) {
    const mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(this.vaultMode ? 0xff5a3a : 0x5fd8ff).multiplyScalar(2.2), transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(new THREE.TorusGeometry(1, 0.08, 6, 64).rotateX(Math.PI / 2), mat);
    mesh.position.copy(center).setY(center.y + 0.25);
    this.env.scene().add(mesh);
    this.waves.push({ r: 1, maxR, speed: 11, hit: false, mesh, center: center.clone() });
  }

  private updateWaves(dt: number) {
    const p = this.env.player();
    for (const w of this.waves) {
      w.r += w.speed * dt;
      w.mesh.scale.set(w.r, 1, w.r);
      (w.mesh.material as THREE.MeshBasicMaterial).opacity = Math.max(0, 1 - w.r / w.maxR);
      if (p && !w.hit) {
        const d = distXZ(p.position, w.center);
        // Jump or phase over the ring to avoid it.
        const airborne = p.position.y > w.center.y + 0.55;
        if (Math.abs(d - w.r) < 0.7 && !airborne) {
          w.hit = true;
          const dir = new THREE.Vector3().subVectors(p.position, w.center).setY(0).normalize();
          p.receiveHit({ damage: this.def.damage * 0.6, poise: 40, knock: dir.multiplyScalar(6), kind: 'slam', point: p.position.clone(), source: this });
        }
      }
    }
    for (const w of this.waves.filter((x) => x.r >= x.maxR)) {
      w.mesh.removeFromParent();
      w.mesh.geometry.dispose();
      (w.mesh.material as THREE.Material).dispose();
    }
    this.waves = this.waves.filter((x) => x.r < x.maxR);
  }

  private updateLaser(dt: number) {
    if (!this.laserOn) return;
    const from = this.core.getWorldPosition(new THREE.Vector3());
    const dir = new THREE.Vector3(Math.sin(this.yaw + this.model.rig.byName.hips.rotation.y), -0.18, Math.cos(this.yaw + this.model.rig.byName.hips.rotation.y)).normalize();
    const hit = this.env.physics().raycast(from, dir, 40);
    const len = hit ? hit.distance : 40;
    this.laser.position.copy(from);
    this.laser.lookAt(from.clone().add(dir));
    this.laser.scale.set(1, 1, len);
    if (hit) this.env.vfx.sparks(hit.point, hit.normal, 2, 0xff6a4a, 3);
    this.laserTick -= dt;
    const p = this.env.player();
    if (p && this.laserTick <= 0) {
      const toP = p.aimPoint(new THREE.Vector3()).sub(from);
      const along = toP.dot(dir);
      if (along > 0 && along < len) {
        const perp = toP.clone().addScaledVector(dir, -along).length();
        if (perp < 0.9) {
          this.laserTick = 0.15;
          p.receiveHit({ damage: this.def.damage * 0.22, poise: 5, knock: new THREE.Vector3(), kind: 'laser', point: p.position.clone(), source: this });
        }
      }
    }
  }

  protected updateAI(dt: number) {
    const p = this.env.player();
    this.attackCd -= dt;
    this.noEffectT -= dt;
    this.exposedT = Math.max(0, this.exposedT - dt);
    this.model.animator.combatStance = 1;
    if (!this.announced && this.aggro) {
      this.announced = true;
      if (!this.vaultMode) this.genv.setBoss(true);
    }
    // Core plates open while exposed.
    const open = this.exposedT > 0 ? 1 : 0;
    this.plates.forEach((pl, i) => {
      const target = (i === 0 ? 1 : -1) * open * 0.16 * this.model.rig.s;
      pl.position.x += (target + (pl.userData.baseX ?? (pl.userData.baseX = pl.position.x)) - pl.position.x) * Math.min(1, dt * 8);
    });
    (this.core.material as THREE.MeshBasicMaterial).color.set(this.exposedT > 0 ? 0xffe0a0 : this.vaultMode ? 0xff5a3a : 0x5fd8ff).multiplyScalar(this.exposedT > 0 ? 4 + Math.sin(this.stateT * 20) : 3);
    this.updateWaves(dt);
    this.updateLaser(dt);
    if (!p || !p.alive) {
      this.velocity.multiplyScalar(Math.exp(-4 * dt));
      this.integrate(dt, this.velocity);
      return;
    }
    switch (this.state) {
      case 'idle':
      case 'alert':
      case 'patrol':
      case 'return':
        this.enter('pursue');
        break;
      case 'pursue': {
        const d = distXZ(this.position, p.position) - this.radius - p.radius;
        this.yaw = dampAngle(this.yaw, yawTo(this.position, p.position), 2.2, dt);
        if (this.attackCd <= 0 && this.facingTo(p.position) < 0.5) {
          let kind: 'slam' | 'sweep' | 'laser';
          if (d < 4.5) kind = Math.random() < 0.55 ? 'slam' : 'sweep';
          else if (this.phase >= 2 && d < 26 && Math.random() < 0.55) kind = 'laser';
          else kind = d < 8 ? 'slam' : 'sweep';
          if (kind !== 'laser' && d > 7) {
            this.steerTo(p.position, this.def.speed * (this.phase === 3 ? 1.3 : 1), dt, 4, false);
            break;
          }
          this.startAttack(kind);
          break;
        }
        if (d > 4) this.steerTo(p.position, this.def.speed * (this.phase === 3 ? 1.3 : 1), dt, 4, false);
        else {
          this.velocity.multiplyScalar(Math.exp(-6 * dt));
          this.integrate(dt, this.velocity);
        }
        break;
      }
      case 'attack': {
        if (this.current !== 'laser' && this.stateT < 0.5) this.yaw = dampAngle(this.yaw, yawTo(this.position, p.position), 3, dt);
        this.velocity.multiplyScalar(Math.exp(-6 * dt));
        this.integrate(dt, this.velocity);
        if (this.hitActive && this.current === 'sweep') this.meleeArc(this.def.attackRange, 70 * DEG, this.def.damage, 50, 9, this.hitSet);
        if (this.stateT > 5) {
          this.current = null;
          this.enter('recover');
        }
        break;
      }
      case 'special':
        this.velocity.multiplyScalar(Math.exp(-8 * dt));
        this.integrate(dt, this.velocity);
        if (this.exposedT <= 0) {
          this.attackCd = this.phase === 3 ? 0.8 : 1.6;
          this.enter('pursue');
        }
        break;
      case 'recover':
        this.velocity.multiplyScalar(Math.exp(-8 * dt));
        this.integrate(dt, this.velocity);
        if (this.stateT > (this.phase === 3 ? 0.4 : 0.9)) {
          this.attackCd = (this.phase === 3 ? 0.9 : 1.6) / this.env.difficulty().aggression;
          this.enter('pursue');
        }
        break;
      default:
        this.integrate(dt, this.velocity);
    }
    this.model.animator.speed = Math.hypot(this.velocity.x, this.velocity.z);
  }

  protected updateModel(dt: number) {
    this.model.update(dt);
  }

  dispose() {
    super.dispose();
    for (const w of this.waves) w.mesh.removeFromParent();
    this.waves = [];
    this.laser.removeFromParent();
    this.model.dispose();
    this.genv.setBoss(false);
  }
}
