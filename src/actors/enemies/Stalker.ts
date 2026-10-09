import * as THREE from 'three';
import { DEG, distXZ, dampAngle, yawTo } from '../../core/MathUtil';
import type { HitInfo } from '../../game/Combat';
import type { EnemyDef } from '../../game/Data';
import { Enemy, type EnemyEnv } from './Enemy';
import { robotClips } from './EnemyAnims';
import { buildStalkerBody, RobotModel, robotMaterials } from './RobotModel';

// Phase Stalker: fast melee hunter that phases out of reality to flank. Echo Sight reveals it.

export class Stalker extends Enemy {
  readonly model: RobotModel;
  private clips: ReturnType<typeof robotClips>;
  private attackCd = 1.5;
  private phaseCd = 5 + Math.random() * 3;
  private hitSet = new Set<number>();
  private hitActive = false;
  private phaseTarget = new THREE.Vector3();
  private recentHits = 0;
  private recentT = 0;
  private strafe = Math.random() < 0.5 ? -1 : 1;

  constructor(def: EnemyDef, env: EnemyEnv) {
    super(def, env);
    this.height = 2.0;
    this.radius = 0.42;
    this.model = new RobotModel(2.0, robotMaterials(0x2a2436, 0x141218, 0xb48cff, 3.2), 'robot', (m) => buildStalkerBody(m));
    this.root.add(this.model.root);
    this.clips = robotClips('stalker');
    this.model.animator.loco.combatIdle = this.clips.stance;
  }

  targetable() {
    if (!this.alive) return false;
    if (this.state === 'phase') return this.env.echoActive();
    return true;
  }

  protected damageTakenMul(): number {
    if (this.state === 'phase' && !this.env.echoActive()) return 0;
    return 1;
  }

  protected onHurt(h: HitInfo) {
    this.model.hitFlash(1);
    this.env.sfx('enemy_hit_metal', h.point);
    this.recentHits++;
    this.recentT = 1.2;
    // Evade sustained combos by phasing away.
    if (this.recentHits >= 3 && this.phaseCd < 3 && this.state !== 'stagger') this.startPhase(true);
  }

  protected stagger(h: HitInfo) {
    super.stagger(h);
    this.hitActive = false;
    this.model.telegraph = 0;
    this.model.opacity = 1;
    this.model.animator.play(this.clips.stagger, { fadeIn: 0.05 });
    this.env.sfx('enemy_stagger', this.position);
  }

  protected die(h: HitInfo | null) {
    super.die(h);
    this.model.opacity = 1;
    this.model.animator.stopActions(0.05);
    this.model.animator.setState(this.clips.death, 0.1);
    this.env.sfx('sentinel_death', this.position);
  }

  protected updateDead(dt: number) {
    if (this.deathT > 0.8 && this.deathT - dt <= 0.8) {
      this.env.vfx.explode(this.position.clone().setY(this.position.y + 0.4), 0.9, 0xb48cff);
      this.env.sfx('explosion', this.position);
    }
    if (this.deathT > 1.0) this.root.visible = false;
    if (this.deathT > 3) this.dispose();
  }

  private startPhase(evasive: boolean) {
    const p = this.env.player();
    if (!p) return;
    this.releaseToken();
    this.hitActive = false;
    this.enter('phase');
    this.phaseCd = 6 + Math.random() * 3;
    this.recentHits = 0;
    // Destination: behind or beside the player.
    const behind = new THREE.Vector3(Math.sin((p as unknown as { yaw?: number }).yaw ?? 0), 0, Math.cos((p as unknown as { yaw?: number }).yaw ?? 0)).multiplyScalar(evasive ? -6 : -2.6);
    const side = new THREE.Vector3(behind.z, 0, -behind.x).normalize().multiplyScalar((Math.random() - 0.5) * 3);
    this.phaseTarget.copy(p.position).add(behind).add(side);
    if (this.arena && distXZ(this.phaseTarget, this.arena.center) > this.arena.radius) this.phaseTarget.copy(p.position);
    this.env.vfx.embers(this.aimPoint(new THREE.Vector3()), 18, 0xb48cff, 0.8, 1);
    this.env.sfx('step', this.position);
  }

  private startAttack() {
    this.enter('attack');
    this.hitSet.clear();
    this.hitActive = false;
    this.model.animator.play(this.clips.slash, {
      fadeIn: 0.06,
      speed: Math.min(1.3, this.env.difficulty().aggression),
      onEvent: (e) => {
        if (e === 'telegraph') {
          this.model.telegraph = 1;
          this.env.sfx('enemy_telegraph', this.position, 0.6);
        } else if (e === 'hit_start') this.hitActive = true;
        else if (e === 'hit_end') {
          this.hitActive = false;
          this.model.telegraph = 0;
        }
      },
      onEnd: () => {
        this.hitActive = false;
        this.model.telegraph = 0;
        this.releaseToken();
        if (this.state === 'attack') this.enter('recover');
      },
    });
  }

  protected updateAI(dt: number) {
    const p = this.env.player();
    this.attackCd -= dt;
    this.phaseCd -= dt;
    this.recentT -= dt;
    if (this.recentT <= 0) this.recentHits = 0;
    this.model.animator.combatStance = this.aggro ? 1 : 0;
    // Visual phase state
    const wantOpacity = this.state === 'phase' ? (this.env.echoActive() ? 0.55 : 0.08) : 1;
    this.model.opacity += (wantOpacity - this.model.opacity) * Math.min(1, dt * 10);
    switch (this.state) {
      case 'idle':
      case 'patrol':
        this.velocity.multiplyScalar(Math.exp(-6 * dt));
        this.integrate(dt, this.velocity);
        this.yaw = dampAngle(this.yaw, this.homeYaw + Math.sin(this.stateT * 0.6) * 0.8, 2, dt);
        break;
      case 'alert':
        this.velocity.multiplyScalar(Math.exp(-6 * dt));
        this.integrate(dt, this.velocity);
        if (p) this.yaw = dampAngle(this.yaw, yawTo(this.position, p.position), 10, dt);
        if (this.stateT > 0.4) this.enter('pursue');
        break;
      case 'pursue': {
        if (!p || !p.alive) { this.enter('return'); break; }
        const d = distXZ(this.position, p.position) - p.radius - this.radius;
        if (this.phaseCd <= 0 && d > 3 && d < 18) {
          this.startPhase(false);
          break;
        }
        if (d <= this.def.attackRange && this.attackCd <= 0 && this.requestToken()) {
          this.startAttack();
          break;
        }
        if (!this.hasToken && d < 5) {
          const away = new THREE.Vector3().subVectors(this.position, p.position).setY(0).normalize();
          const side = new THREE.Vector3(away.z, 0, -away.x).multiplyScalar(this.strafe);
          this.steerTo(p.position.clone().addScaledVector(away, 4.5).addScaledVector(side, 3), 4.5, dt, 10, false);
          this.yaw = dampAngle(this.yaw, yawTo(this.position, p.position), 10, dt);
          if (Math.random() < dt * 0.4) this.strafe *= -1;
        } else this.steerTo(p.position, this.def.speed, dt, 10);
        break;
      }
      case 'phase': {
        // Glide to the flank position while phased (passes through the player's line of fire).
        const d = this.steerTo(this.phaseTarget, 11, dt, 14);
        if (Math.random() < 0.4) this.env.vfx.embers(this.aimPoint(new THREE.Vector3()), 1, 0xb48cff, 0.6, 0.3);
        if (d < 0.8 || this.stateT > 1.4) {
          this.env.vfx.flash(this.aimPoint(new THREE.Vector3()), 2, 0xb48cff, 0.15);
          if (p) this.yaw = yawTo(this.position, p.position);
          this.attackCd = 0;
          if (this.requestToken()) this.startAttack();
          else this.enter('pursue');
        }
        break;
      }
      case 'attack': {
        if (p && this.stateT < 0.25) this.yaw = dampAngle(this.yaw, yawTo(this.position, p.position), 10, dt);
        const lunge = this.hitActive ? 6 : 0;
        this.velocity.x = Math.sin(this.yaw) * lunge;
        this.velocity.z = Math.cos(this.yaw) * lunge;
        this.integrate(dt, this.velocity);
        if (this.hitActive) this.meleeArc(this.def.attackRange + 0.5, 70 * DEG, this.def.damage, 16, 3, this.hitSet);
        if (this.stateT > 2) this.enter('recover');
        break;
      }
      case 'recover':
        this.velocity.multiplyScalar(Math.exp(-8 * dt));
        this.integrate(dt, this.velocity);
        if (this.stateT > 0.4) {
          this.attackCd = (1.1 + Math.random() * 0.8) / this.env.difficulty().aggression;
          this.enter(this.aggro ? 'pursue' : 'return');
        }
        break;
      case 'stagger':
        this.velocity.multiplyScalar(Math.exp(-5 * dt));
        this.integrate(dt, this.velocity);
        if (this.stateT > 0.9) this.enter(this.aggro ? 'pursue' : 'idle');
        break;
      case 'return':
        this.updateReturn(dt, this.def.speed * 0.7);
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
    this.model.dispose();
  }
}
