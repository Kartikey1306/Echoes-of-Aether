import * as THREE from 'three';
import { DEG, distXZ, yawTo, dampAngle } from '../../core/MathUtil';
import type { HitInfo } from '../../game/Combat';
import type { EnemyDef } from '../../game/Data';
import { Enemy, type EnemyEnv } from './Enemy';
import { robotClips } from './EnemyAnims';
import { buildSentinelBody, RobotModel, robotMaterials } from './RobotModel';

// Corrupted Sentinel (melee) and The Warden (elite variant with a frontal shield and shockwave slam).

export class Sentinel extends Enemy {
  readonly model: RobotModel;
  private clips: ReturnType<typeof robotClips>;
  private attackCd = 1 + Math.random();
  private hitSet = new Set<number>();
  private hitActive = false;
  private currentAttack: 'slam' | 'sweep' = 'sweep';
  private strafeDir = Math.random() < 0.5 ? -1 : 1;
  private patrolT = 0;
  readonly elite: boolean;
  private shieldUp = true;
  private shieldMesh: THREE.Mesh | null = null;
  private chargeCd = 6;

  constructor(def: EnemyDef, env: EnemyEnv) {
    super(def, env);
    this.elite = def.id === 'warden';
    this.height = this.elite ? 2.6 : 2.15;
    this.radius = this.elite ? 0.62 : 0.5;
    const mats = this.elite ? robotMaterials(0x3a2e30, 0x1f1c1e, 0xff3b30, 3.4) : robotMaterials(0x4a4f56, 0x24272c, 0xff5a3a, 3);
    this.model = new RobotModel(this.height, mats, 'robot', (m) => buildSentinelBody(m, this.elite));
    this.root.add(this.model.root);
    this.clips = robotClips('sentinel');
    this.model.animator.loco.combatIdle = this.clips.stance;
    if (this.elite) {
      const g = new THREE.Mesh(
        new THREE.SphereGeometry(1.25, 24, 12, -Math.PI * 0.42, Math.PI * 0.84, Math.PI * 0.2, Math.PI * 0.55),
        new THREE.MeshBasicMaterial({ color: new THREE.Color(0xff5a3a).multiplyScalar(0.9), transparent: true, opacity: 0.22, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false }),
      );
      g.position.set(0, 1.4, 0.2);
      this.root.add(g);
      this.shieldMesh = g;
    }
  }

  protected damageTakenMul(h: HitInfo): number {
    if (!this.elite || !this.shieldUp || this.state === 'stagger') return 1;
    // Frontal shield blocks most damage from the front; flank or stagger to break through.
    const src = h.source?.position ?? h.point;
    const ang = this.facingTo(src);
    if (ang < 70 * DEG && h.kind !== 'pulse' && h.kind !== 'ult') {
      this.env.vfx.sparks(h.point, null, 8, 0xff6a4a, 5);
      this.env.sfx('shield_block', h.point);
      return h.kind === 'heavy' ? 0.45 : 0.15;
    }
    return 1;
  }

  protected onHurt(h: HitInfo) {
    this.model.hitFlash(1);
    this.env.sfx('enemy_hit_metal', h.point);
    this.model.animator.jolt(Math.random() < 0.5 ? -1 : 1, 0.6);
  }

  protected stagger(h: HitInfo) {
    super.stagger(h);
    this.hitActive = false;
    this.model.telegraph = 0;
    this.model.animator.play(this.clips.stagger, { fadeIn: 0.05 });
    this.env.sfx('enemy_stagger', this.position);
    if (this.elite) this.shieldUp = false;
  }

  protected die(h: HitInfo | null) {
    super.die(h);
    this.hitActive = false;
    this.model.telegraph = 0;
    this.model.animator.stopActions(0.05);
    this.model.animator.setState(this.clips.death, 0.1);
    this.env.sfx('sentinel_death', this.position);
    this.env.vfx.sparks(this.aimPoint(new THREE.Vector3()), null, 24, 0xffb060, 7);
    if (this.shieldMesh) this.shieldMesh.visible = false;
  }

  protected updateDead(dt: number) {
    if (this.deathT > 1.3 && this.deathT - dt <= 1.3) {
      this.env.vfx.explode(this.position.clone().setY(this.position.y + 0.5), this.elite ? 1.6 : 1.1, 0xff6a4a);
      this.env.sfx('explosion', this.position);
      this.env.shake(this.elite ? 0.4 : 0.2);
    }
    if (this.deathT > 1.5) this.root.position.y = this.position.y - (this.deathT - 1.5) * 0.6;
    if (this.deathT > 3.5) this.dispose();
  }

  private startAttack(kind: 'slam' | 'sweep') {
    this.currentAttack = kind;
    this.enter('attack');
    this.hitSet.clear();
    this.hitActive = false;
    const speed = (this.elite ? 1.05 : 1) * Math.min(1.25, this.env.difficulty().aggression);
    this.model.animator.play(this.clips[kind], {
      fadeIn: 0.1,
      speed,
      onEvent: (e) => {
        if (e === 'telegraph') {
          this.model.telegraph = 1;
          this.env.sfx('enemy_telegraph', this.position);
        } else if (e === 'hit_start') this.hitActive = true;
        else if (e === 'hit_end') {
          this.hitActive = false;
          this.model.telegraph = 0;
        } else if (e === 'impact') {
          const center = this.position.clone().add(new THREE.Vector3(Math.sin(this.yaw) * 1.6, 0, Math.cos(this.yaw) * 1.6));
          this.env.vfx.shockwave(center, this.elite ? 5 : 2.6, 0xff5a3a, 0.4);
          this.env.vfx.sparks(center.clone().setY(center.y + 0.2), new THREE.Vector3(0, 1, 0), 18, 0xffa060, 6);
          this.env.shake(this.elite ? 0.35 : 0.18);
          this.env.sfx('slam', center);
          if (this.elite) {
            // Shockwave reaches further than the fists.
            this.env.combat.radial('enemy', center, 5, (c, d) => {
              if (this.hitSet.has(c.id)) return;
              this.hitSet.add(c.id);
              const dir = new THREE.Vector3().subVectors(c.position, center).setY(0).normalize();
              c.receiveHit({ damage: this.def.damage * 0.8, poise: 40, knock: dir.multiplyScalar(7), kind: 'slam', point: c.position.clone(), source: this });
            }, 1.2);
          }
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
    this.chargeCd -= dt;
    if (this.shieldMesh) {
      if (!this.shieldUp && this.state !== 'stagger' && this.stateT > 2) this.shieldUp = true;
      this.shieldMesh.visible = this.shieldUp && this.aggro;
      (this.shieldMesh.material as THREE.MeshBasicMaterial).opacity = 0.16 + Math.sin(this.stateT * 6) * 0.05;
    }
    const anim = this.model.animator;
    anim.combatStance = this.aggro ? 1 : 0;
    switch (this.state) {
      case 'idle': {
        this.velocity.multiplyScalar(Math.exp(-6 * dt));
        this.integrate(dt, this.velocity);
        this.yaw = dampAngle(this.yaw, this.homeYaw + Math.sin(this.stateT * 0.4) * 0.6, 1.5, dt);
        this.patrolT += dt;
        if (this.patrolT > 6) {
          this.patrolT = 0;
          this.enter('patrol');
        }
        break;
      }
      case 'patrol': {
        const goal = this.home.clone().add(new THREE.Vector3(Math.sin(this.id * 3.1) * 3, 0, Math.cos(this.id * 3.1) * 3));
        const d = this.steerTo(this.stateT < 4 ? goal : this.home, 1.4, dt);
        if (this.stateT > 8 && d < 0.6) this.enter('idle');
        break;
      }
      case 'alert':
        this.velocity.multiplyScalar(Math.exp(-6 * dt));
        this.integrate(dt, this.velocity);
        if (p) this.yaw = dampAngle(this.yaw, yawTo(this.position, p.position), 8, dt);
        if (this.stateT > 0.6) this.enter('pursue');
        break;
      case 'pursue': {
        if (!p || !p.alive) { this.enter('return'); break; }
        const d = distXZ(this.position, p.position) - p.radius - this.radius;
        const range = this.def.attackRange * (this.elite ? 1.1 : 1);
        if (d <= range && this.attackCd <= 0 && this.facingTo(p.position) < 0.6) {
          if (this.requestToken()) {
            const slam = this.elite ? Math.random() < 0.55 : Math.random() < 0.35;
            this.startAttack(slam ? 'slam' : 'sweep');
            break;
          }
        }
        if (d > range * 0.8 || this.attackCd > 0.8) {
          // Close in, or circle at medium range while waiting for an attack token.
          let goal: THREE.Vector3;
          if (!this.hasToken && d < 5) {
            const away = new THREE.Vector3().subVectors(this.position, p.position).setY(0).normalize();
            const side = new THREE.Vector3(away.z, 0, -away.x).multiplyScalar(this.strafeDir);
            goal = p.position.clone().addScaledVector(away, 4.2).addScaledVector(side, 2);
            if (Math.random() < dt * 0.3) this.strafeDir *= -1;
            this.steerTo(goal, 2.2, dt, 8, false);
            this.yaw = dampAngle(this.yaw, yawTo(this.position, p.position), 8, dt);
          } else {
            const speed = d > 8 ? this.def.speed * 1.35 : this.def.speed;
            this.steerTo(p.position, speed, dt);
          }
        } else {
          this.velocity.multiplyScalar(Math.exp(-8 * dt));
          this.integrate(dt, this.velocity);
          this.yaw = dampAngle(this.yaw, yawTo(this.position, p.position), 9, dt);
        }
        break;
      }
      case 'attack': {
        // Slight tracking during wind-up, committed during the swing.
        if (p && this.stateT < 0.35) this.yaw = dampAngle(this.yaw, yawTo(this.position, p.position), 6, dt);
        const lunge = this.hitActive ? 3.5 : 0;
        this.velocity.x = Math.sin(this.yaw) * lunge;
        this.velocity.z = Math.cos(this.yaw) * lunge;
        this.integrate(dt, this.velocity);
        if (this.hitActive) {
          const dmg = this.def.damage * (this.currentAttack === 'slam' ? 1.5 : 1);
          this.meleeArc(this.def.attackRange + 0.6, this.currentAttack === 'slam' ? 50 * DEG : 80 * DEG, dmg, this.currentAttack === 'slam' ? 45 : 22, this.currentAttack === 'slam' ? 6 : 4, this.hitSet);
        }
        if (this.stateT > 3) this.enter('recover');
        break;
      }
      case 'recover':
        this.velocity.multiplyScalar(Math.exp(-8 * dt));
        this.integrate(dt, this.velocity);
        if (this.stateT > (this.elite ? 0.5 : 0.7)) {
          this.attackCd = (this.elite ? 1.2 : 1.6 + Math.random()) / this.env.difficulty().aggression;
          this.enter(this.aggro ? 'pursue' : 'return');
        }
        break;
      case 'stagger':
        this.velocity.multiplyScalar(Math.exp(-5 * dt));
        this.integrate(dt, this.velocity);
        if (this.stateT > 1.3) this.enter(this.aggro ? 'pursue' : 'idle');
        break;
      case 'return':
        this.updateReturn(dt, this.def.speed);
        break;
      default:
        this.integrate(dt, this.velocity);
    }
    anim.speed = Math.hypot(this.velocity.x, this.velocity.z);
    anim.grounded = true;
  }

  protected updateModel(dt: number) {
    this.model.update(dt);
  }

  dispose() {
    super.dispose();
    this.model.dispose();
  }
}
