import * as THREE from 'three';
import { clamp, damp, dampAngle, DEG, distXZ, wrapAngle, yawTo } from '../core/MathUtil';
import { events } from '../core/Events';
import type { Input } from '../core/Input';
import type { CameraRig } from './CameraRig';
import { G_ENEMY, G_NPC, G_PLAYER, G_WORLD, G_INVISIBLE, G_COMPANION, type CharacterBody, type Physics } from '../physics/Physics';
import { newCombatId, type Combat, type Combatant, type HitInfo } from '../game/Combat';
import type { VFX } from '../vfx/VFX';
import type { CharStats } from '../game/Progression';
import type { Buffs } from '../game/Powerups';
import type { CharacterId } from '../game/GameState';
import { HumanModel } from './human/HumanModel';
import type { Look } from './human/HumanBuilder';
import type { Clip } from './human/Animator';

// Playable protagonist (Kael or Lyra). The same class runs as the player or as the AI companion.

export interface HeroEnv {
  input: Input;
  cam: CameraRig;
  physics: () => Physics;
  combat: Combat;
  vfx: VFX;
  stats: (c: CharacterId) => CharStats;
  buffs: () => Buffs;
  hasAbility: (id: string) => boolean;
  sfx: (id: string, pos?: THREE.Vector3, vol?: number) => void;
  hitstop: (sec: number) => void;
  shake: (amount: number) => void;
  rumble: (i: number, ms: number) => void;
  echo: (center: THREE.Vector3, range: number, duration: number) => void;
  difficulty: () => { enemyDamage: number; playerRegen: number };
  killY: () => number;
  inCombat: () => boolean;
  onDied: (h: Hero) => void;
  onDamaged: (amount: number) => void;
  onDealtDamage: (amount: number) => void;
  /** True while gameplay input should drive this hero. */
  controllable: () => boolean;
}

type State = 'move' | 'attack' | 'dash' | 'ability' | 'hit' | 'dead' | 'scripted' | 'aim' | 'ult';

const KAEL_CHAIN = ['k_light1', 'k_light2', 'k_light3'];
const LYRA_CHAIN = ['l_quick1', 'l_quick2'];

export class Hero implements Combatant {
  readonly id = newCombatId();
  readonly team = 'player' as const;
  readonly character: CharacterId;
  readonly name: string;
  model: HumanModel;
  body: CharacterBody | null = null;
  alive = true;
  readonly position = new THREE.Vector3();
  readonly radius = 0.36;
  height = 1.8;
  yaw = 0;
  readonly velocity = new THREE.Vector3();
  health = 100;
  shield = 50;
  energy = 100;
  ult = 0;
  state: State = 'move';
  isPlayer = false;
  private env: HeroEnv;
  private stateT = 0;
  private coyote = 0;
  private jumpBuffer = 0;
  private wasGrounded = true;
  private comboIndex = -1;
  private comboOpen = false;
  private queued: 'light' | 'heavy' | null = null;
  private queuedT = 0;
  private hitActive = false;
  private hitSet = new Set<number>();
  private currentAttack: { clip: string; damage: number; poise: number; knock: number; range: number; arc: number; finisher: boolean } | null = null;
  private lungeTarget: Combatant | null = null;
  private lungeT = 0;
  invuln = 0;
  private hurtCooldown = 0;
  private shieldDelay = 0;
  cdAbility = 0;
  cdDash = 0;
  dashCharges = 1;
  private cdBolt = 0;
  private dashDir = new THREE.Vector3();
  private dashSpeed = 0;
  private boltHeld = false;
  private aimClip: string;
  lastSafe = new THREE.Vector3();
  private safeT = 0;
  lockTarget: Combatant | null = null;
  // Companion AI
  private trail: THREE.Vector3[] = [];
  private stuckT = 0;
  private supportT = 2;
  private lastPos = new THREE.Vector3();
  scriptedMove: { target: THREE.Vector3; speed: number; done: () => void } | null = null;
  private tmp = new THREE.Vector3();
  private tmp2 = new THREE.Vector3();
  private airTime = 0;
  footstepT = 0;

  constructor(character: CharacterId, env: HeroEnv, look: Look) {
    this.character = character;
    this.name = character === 'kael' ? 'Kael Voss' : 'Lyra Vale';
    this.env = env;
    this.model = new HumanModel(look, { lods: 2, faceSize: 512, lodDistances: [14, 40] });
    this.height = this.model.height;
    this.aimClip = character === 'kael' ? 'aim_r' : 'aim_l';
    const st = env.stats(character);
    this.health = st.maxHealth;
    this.shield = st.maxShield;
    this.dashCharges = st.dashCharges;
  }

  /** Replace the visual model (appearance changed). Physics body is re-created to match the new height. */
  rebuildModel(look: Look, physics: Physics | null) {
    const parent = this.model.root.parent;
    const visible = this.model.root.visible;
    this.model.dispose();
    this.model = new HumanModel(look, { lods: 2, faceSize: 512, lodDistances: [14, 40] });
    this.height = this.model.height;
    this.model.root.visible = visible;
    this.model.root.position.copy(this.position);
    this.model.root.rotation.y = this.yaw;
    parent?.add(this.model.root);
    if (physics && this.body) this.spawn(physics, this.position.clone(), this.yaw);
  }

  get stats() {
    return this.env.stats(this.character);
  }

  spawn(physics: Physics, pos: THREE.Vector3, yaw: number) {
    this.body?.dispose();
    // The player collides with world, enemies, NPCs; the companion ignores the player.
    this.body = physics.createCharacter(pos, this.radius, this.height - 0.05, this.isPlayer ? G_PLAYER : G_COMPANION, G_WORLD | G_INVISIBLE | G_ENEMY | G_NPC | (this.isPlayer ? 0 : 0));
    this.position.copy(pos);
    this.yaw = yaw;
    this.velocity.set(0, 0, 0);
    this.lastSafe.copy(pos);
    this.model.root.position.copy(pos);
    this.model.root.rotation.y = yaw;
    this.trail = [];
  }

  /** Re-create the physics body with player/companion collision groups. */
  setRole(isPlayer: boolean, physics: Physics) {
    this.isPlayer = isPlayer;
    this.spawn(physics, this.position.clone(), this.yaw);
    if (!isPlayer) this.cancelActions();
  }

  targetable() {
    return this.isPlayer && this.alive && this.state !== 'scripted';
  }

  aimPoint(out: THREE.Vector3) {
    return out.copy(this.position).setY(this.position.y + this.height * 0.62);
  }

  chest(out = new THREE.Vector3()) {
    return out.copy(this.position).setY(this.position.y + this.height * 0.72);
  }

  facingDir(out = new THREE.Vector3()) {
    return out.set(Math.sin(this.yaw), 0, Math.cos(this.yaw));
  }

  /** Restore to full (respawn / load). */
  restore() {
    const st = this.stats;
    this.health = st.maxHealth;
    this.shield = st.maxShield;
    this.energy = 100;
    this.alive = true;
    this.state = 'move';
    this.invuln = 1.5;
    this.model.animator.setState(null, 0.2);
    this.model.animator.stopActions(0.1);
  }

  cancelActions() {
    this.model.animator.stopActions(0.12);
    this.state = this.alive ? 'move' : 'dead';
    this.comboIndex = -1;
    this.comboOpen = false;
    this.queued = null;
    this.hitActive = false;
    this.boltHeld = false;
    this.env.cam.aiming = false;
    this.model.animator.aimW = 0;
  }

  // ------------------------------------------------------------------ Damage
  receiveHit(h: HitInfo): number {
    if (!this.alive || !this.isPlayer) return 0;
    if (this.invuln > 0 || this.state === 'ult' || this.state === 'scripted') {
      if (this.state === 'dash' && this.character === 'lyra' && this.env.stats('lyra').dashIframes > 0.5) {
        // Perfect dodge refund (Ghost Step).
        this.energy = Math.min(100, this.energy + 15);
        this.env.vfx.flash(this.chest(), 1.4, 0xa47dff, 0.15);
      }
      return 0;
    }
    if (this.hurtCooldown > 0) return 0;
    const dmg = h.damage * this.env.difficulty().enemyDamage;
    let rem = dmg;
    if (!h.pierce && this.shield > 0) {
      const absorbed = Math.min(this.shield, rem);
      this.shield -= absorbed;
      rem -= absorbed;
      if (this.shield <= 0) this.env.sfx('shield_break', this.position);
    }
    this.health -= rem;
    this.shieldDelay = this.stats.shieldDelay;
    this.hurtCooldown = 0.22;
    this.ult = Math.min(100, this.ult + dmg * 0.5);
    this.env.onDamaged(dmg);
    events.emit('player:damaged', { amount: dmg, source: h.kind });
    this.model.hitFlash(rem > 0 ? 0xff6050 : 0x6fd8ff, 0.8);
    this.env.shake(Math.min(0.5, 0.15 + dmg / 60));
    this.env.rumble(Math.min(1, dmg / 30), 160);
    this.env.sfx(rem > 0 ? 'player_hurt' : 'shield_hit', this.position);
    if (this.health <= 0) {
      this.die();
      return dmg;
    }
    // Knockback and reactions
    this.velocity.x += h.knock.x;
    this.velocity.z += h.knock.z;
    const heavy = h.poise >= 35;
    if (heavy && this.state !== 'ability') {
      this.cancelActions();
      this.state = 'hit';
      this.stateT = 0;
      this.model.animator.play(this.model.anims.clips.stagger, { fadeIn: 0.05, onEnd: () => { if (this.state === 'hit') this.state = 'move'; } });
    } else {
      const side = Math.sign(wrapAngle(yawTo(this.position, h.point) - this.yaw)) || 1;
      this.model.animator.jolt(side, 1);
    }
    return dmg;
  }

  private die() {
    this.health = 0;
    this.alive = false;
    this.cancelActions();
    this.state = 'dead';
    this.model.animator.setState(this.model.anims.clips.death, 0.15);
    this.env.sfx('player_death', this.position);
    this.env.onDied(this);
  }

  // ------------------------------------------------------------------ Update
  update(dt: number) {
    const st = this.stats;
    this.stateT += dt;
    this.invuln = Math.max(0, this.invuln - dt);
    this.hurtCooldown = Math.max(0, this.hurtCooldown - dt);
    this.cdAbility = Math.max(0, this.cdAbility - dt);
    this.cdBolt = Math.max(0, this.cdBolt - dt);
    if (this.dashCharges < st.dashCharges) {
      this.cdDash -= dt;
      if (this.cdDash <= 0) {
        this.dashCharges++;
        this.cdDash = this.dashCharges < st.dashCharges ? st.dashCooldown * st.cooldownMul : 0;
      }
    }
    // Regeneration
    const regen = this.env.difficulty().playerRegen;
    this.shieldDelay -= dt;
    if (this.shieldDelay <= 0 && this.shield < st.maxShield) this.shield = Math.min(st.maxShield, this.shield + st.shieldRegen * regen * dt);
    this.energy = Math.min(st.maxEnergy, this.energy + st.energyRegen * dt);
    if (!this.isPlayer) {
      this.health = Math.min(st.maxHealth, this.health + 4 * dt);
      this.shield = Math.min(st.maxShield, this.shield + 10 * dt);
    }
    this.health = Math.min(this.health, st.maxHealth);

    if (this.isPlayer && this.env.controllable() && this.state !== 'scripted') this.updatePlayer(dt);
    else if (this.state === 'scripted') this.updateScripted(dt);
    else if (!this.isPlayer) this.updateCompanion(dt);
    else this.updatePhysicsOnly(dt);

    // Model sync
    this.model.root.position.copy(this.position);
    this.model.root.rotation.y = this.yaw;
    const a = this.model.animator;
    a.speed = Math.hypot(this.velocity.x, this.velocity.z) * (this.state === 'move' || this.state === 'aim' || this.state === 'scripted' ? 1 : 0.2);
    a.grounded = this.body?.grounded ?? true;
    a.vy = this.velocity.y;
    a.combatStance = this.isPlayer && this.env.inCombat() ? 1 : 0;
    this.model.glowBoost = Math.max(0, this.model.glowBoost - dt * 3);
    this.model.update(dt);
  }

  private moveBody(dt: number, horizontal: THREE.Vector3) {
    const body = this.body;
    if (!body) return;
    const g = this.env.physics().gravity;
    if (this.state !== 'dash') this.velocity.y += g * dt;
    else this.velocity.y = 0;
    const delta = this.tmp.set(horizontal.x * dt, this.velocity.y * dt, horizontal.z * dt);
    const moved = body.move(delta, this.tmp2);
    this.position.copy(body.position);
    if (body.grounded) {
      if (!this.wasGrounded && this.airTime > 0.25) this.onLand(-this.velocity.y);
      if (this.velocity.y < 0) this.velocity.y = -1.5;
      this.coyote = 0.12;
      this.airTime = 0;
    } else {
      this.coyote -= dt;
      this.airTime += dt;
      // Hit a ceiling
      if (this.velocity.y > 0 && moved.y < delta.y * 0.5) this.velocity.y = 0;
    }
    this.wasGrounded = body.grounded;
  }

  private onLand(speed: number) {
    if (speed > 9 && this.isPlayer) {
      this.env.shake(Math.min(0.4, speed / 50));
      if (this.state === 'move') this.model.animator.play(this.model.anims.clips.land, { fadeIn: 0.04, fadeOut: 0.15, mask: 'full' });
    }
    this.env.sfx('land', this.position, Math.min(1, speed / 12));
    events.emit('player:landed', { speed });
  }

  private updatePhysicsOnly(dt: number) {
    const k = Math.exp(-10 * dt);
    this.velocity.x *= k;
    this.velocity.z *= k;
    this.moveBody(dt, this.velocity);
  }

  private updatePlayer(dt: number) {
    const inp = this.env.input;
    const cam = this.env.cam;
    const st = this.stats;
    const buffs = this.env.buffs();
    // Desired direction relative to camera
    const fwd = cam.forward(new THREE.Vector3());
    const right = cam.right(new THREE.Vector3());
    const wish = new THREE.Vector3().addScaledVector(fwd, inp.move.y).addScaledVector(right, inp.move.x);
    const mag = Math.min(1, wish.length());
    if (mag > 0.001) wish.divideScalar(Math.max(mag, 1e-6));

    if (this.state === 'dead') {
      this.updatePhysicsOnly(dt);
      return;
    }

    // ---- Queued input buffer
    if (this.queuedT > 0) this.queuedT -= dt;
    else this.queued = null;

    const lightP = inp.pressed('light');
    const heavyP = inp.pressed('heavy');
    if (lightP) { this.queued = 'light'; this.queuedT = 0.35; }
    if (heavyP) { this.queued = 'heavy'; this.queuedT = 0.35; }

    // ---- Bolt: tap to fire, hold to aim
    if (inp.pressed('bolt') && (this.state === 'move' || this.state === 'aim')) this.boltHeld = true;
    if (this.boltHeld) {
      if (inp.held('bolt')) {
        if (inp.holdTime('bolt') > 0.2 && this.state === 'move') this.enterAim();
      } else {
        this.boltHeld = false;
        this.fireBolt(this.state === 'aim');
        if (this.state === 'aim') this.exitAim();
      }
    }

    // ---- Actions from move/aim state
    if (this.state === 'move' || this.state === 'aim') {
      if (this.queued === 'light' && this.state === 'move') this.startAttack(0, false);
      else if (this.queued === 'heavy' && this.state === 'move') this.startHeavy(false);
      else if (inp.pressed('ability')) this.useAbility();
      else if (inp.pressed('ultimate')) this.useUltimate();
      else if (inp.pressed('jump') && this.state === 'move') this.jumpBuffer = 0.15;
    } else if (this.state === 'attack' && this.comboOpen && this.queued) {
      const chain = this.character === 'kael' ? KAEL_CHAIN : LYRA_CHAIN;
      if (this.queued === 'light' && this.comboIndex < chain.length - 1) this.startAttack(this.comboIndex + 1, true);
      else if (this.queued === 'heavy' || (this.queued === 'light' && this.comboIndex >= chain.length - 1)) this.startHeavy(this.comboIndex >= chain.length - 1);
    }
    // Dash: available from move, aim, attack (cancel) when unlocked.
    if (inp.pressed('dash') && this.state !== 'dash' && this.state !== 'hit' && this.state !== 'ult' && this.state !== 'ability') {
      const id = this.character === 'kael' ? 'dash' : 'step';
      if (this.env.hasAbility(id) && this.dashCharges > 0) this.startDash(wish.lengthSq() > 0.01 ? wish : null);
    }

    // ---- Locomotion
    const sprint = inp.held('dash') && this.state === 'move' && mag > 0.5;
    let targetSpeed = 0;
    if (this.state === 'move') targetSpeed = mag < 0.55 ? 2.2 * (mag / 0.55) : sprint ? 7.6 : 5.2;
    else if (this.state === 'aim') targetSpeed = 2.6 * mag;
    cam.sprinting = sprint && mag > 0.5;

    if (this.state === 'move' || this.state === 'aim') {
      const grounded = this.body?.grounded ?? true;
      const accel = grounded ? (targetSpeed > Math.hypot(this.velocity.x, this.velocity.z) ? 30 : 24) : 8;
      const want = wish.clone().multiplyScalar(targetSpeed);
      this.velocity.x = damp(this.velocity.x, want.x, accel / 4, dt);
      this.velocity.z = damp(this.velocity.z, want.z, accel / 4, dt);
      if (this.state === 'aim') this.yaw = dampAngle(this.yaw, cam.heading, 20, dt);
      else if (mag > 0.05) {
        const turn = grounded ? 14 : 6;
        const prev = this.yaw;
        this.yaw = dampAngle(this.yaw, Math.atan2(wish.x, wish.z), turn, dt);
        this.model.animator.lean = clamp(wrapAngle(this.yaw - prev) / Math.max(dt, 1e-3) * 0.06 * (targetSpeed / 5), -1, 1);
      } else this.model.animator.lean = 0;
      // Jump
      if (this.jumpBuffer > 0) {
        this.jumpBuffer -= dt;
        if (this.coyote > 0 && this.state === 'move') {
          this.velocity.y = 7.6;
          this.coyote = 0;
          this.jumpBuffer = 0;
          this.env.sfx('jump', this.position);
        }
      }
    } else if (this.state === 'attack' || this.state === 'ability' || this.state === 'ult') {
      // Attack lunge toward the magnetised target.
      let lunge = 0;
      if (this.lungeT > 0) {
        this.lungeT -= dt;
        if (this.lungeTarget && this.lungeTarget.alive) {
          const d = distXZ(this.position, this.lungeTarget.position) - this.lungeTarget.radius - this.radius;
          lunge = clamp((d - 0.9) * 8, 0, 9);
          this.yaw = dampAngle(this.yaw, yawTo(this.position, this.lungeTarget.position), 18, dt);
        } else lunge = 2.5;
      }
      const f = this.facingDir(this.tmp);
      this.velocity.x = damp(this.velocity.x, f.x * lunge, 14, dt);
      this.velocity.z = damp(this.velocity.z, f.z * lunge, 14, dt);
      if (this.hitActive) this.sweepHits();
    } else if (this.state === 'dash') {
      this.velocity.x = this.dashDir.x * this.dashSpeed;
      this.velocity.z = this.dashDir.z * this.dashSpeed;
      if (this.stateT > (this.character === 'kael' ? 0.17 : 0.15)) {
        this.state = 'move';
        this.velocity.multiplyScalar(0.35);
      }
      if (Math.random() < 0.8) this.env.vfx.embers(this.chest(), 2, this.character === 'kael' ? 0x5fb8ff : 0xa47dff, 0.6, 0.2);
    } else if (this.state === 'hit') {
      const k = Math.exp(-6 * dt);
      this.velocity.x *= k;
      this.velocity.z *= k;
      if (this.stateT > 0.9) this.state = 'move';
    }

    this.moveBody(dt, this.velocity);
    this.trackSafety(dt);
    this.footsteps(dt);
    // Lock-on target maintenance
    if (this.lockTarget && (!this.lockTarget.alive || !this.lockTarget.targetable() || this.lockTarget.position.distanceTo(this.position) > 30)) this.lockTarget = null;
    cam.lockTarget = this.lockTarget ? this.lockTarget.aimPoint(new THREE.Vector3()) : null;
    if (inp.pressed('lockon')) {
      if (this.lockTarget) this.lockTarget = null;
      else this.lockTarget = this.env.combat.bestTarget('player', this.chest(), cam.lookDir(), 25, 0.9, true);
    }
    // Interact & swap handled by Game.
  }

  private footsteps(dt: number) {
    const sp = Math.hypot(this.velocity.x, this.velocity.z);
    if (!(this.body?.grounded) || sp < 1.2 || this.state === 'dash') return;
    this.footstepT -= dt * sp;
    if (this.footstepT <= 0) {
      this.footstepT = sp > 6 ? 2.25 : sp > 3.5 ? 1.75 : 0.82;
      this.env.sfx('footstep', this.position, Math.min(1, sp / 6));
    }
  }

  private trackSafety(dt: number) {
    const killY = this.env.killY();
    if (this.position.y < killY) {
      // Fell out of the world: back to the last safe ground with a small penalty.
      this.body?.teleport(this.lastSafe);
      this.position.copy(this.lastSafe);
      this.velocity.set(0, 0, 0);
      this.receiveHit({ damage: 10, poise: 0, knock: new THREE.Vector3(), kind: 'fall', point: this.position.clone(), source: null, pierce: true });
      this.invuln = 1.0;
      this.env.sfx('respawn', this.position);
      return;
    }
    this.safeT -= dt;
    if (this.safeT <= 0 && this.body?.grounded && this.state === 'move') {
      this.safeT = 0.5;
      // Only record if solid ground is under a small neighbourhood (avoid edges).
      const ph = this.env.physics();
      let ok = true;
      for (const [ox, oz] of [[0.5, 0], [-0.5, 0], [0, 0.5], [0, -0.5]]) {
        const g = ph.groundAt(this.position.x + ox, this.position.y + 0.5, this.position.z + oz, 1.2);
        if (g === null) { ok = false; break; }
      }
      if (ok) this.lastSafe.copy(this.position);
    }
  }

  // ------------------------------------------------------------------ Combat actions
  private findMagnetTarget(range = 5): Combatant | null {
    const inp = this.env.input;
    const dir = new THREE.Vector3();
    if (Math.abs(inp.move.x) + Math.abs(inp.move.y) > 0.1) {
      dir.copy(this.env.cam.forward()).multiplyScalar(inp.move.y).addScaledVector(this.env.cam.right(), inp.move.x).normalize();
    } else this.facingDir(dir);
    if (this.lockTarget && this.lockTarget.alive) return this.lockTarget;
    return this.env.combat.bestTarget('player', this.chest(), dir, range, 70 * DEG, false) ?? this.env.combat.bestTarget('player', this.chest(), this.env.cam.forward(), range, 60 * DEG, false);
  }

  private startAttack(index: number, chained: boolean) {
    const chain = this.character === 'kael' ? KAEL_CHAIN : LYRA_CHAIN;
    const clipName = chain[index];
    const clip = this.model.anims.clips[clipName];
    const st = this.stats;
    this.state = 'attack';
    this.stateT = 0;
    this.comboIndex = index;
    this.comboOpen = false;
    this.queued = null;
    this.hitActive = false;
    this.hitSet.clear();
    const kael = this.character === 'kael';
    this.currentAttack = {
      clip: clipName,
      damage: st.lightDamage * (index === 2 ? 1.25 : 1),
      poise: kael ? 14 : 10,
      knock: kael ? 2.5 : 1.6,
      range: kael ? 2.5 : 2.2,
      arc: 75 * DEG,
      finisher: false,
    };
    this.lungeTarget = this.findMagnetTarget(5.5);
    this.lungeT = 0.16;
    if (this.lungeTarget) this.yaw = yawTo(this.position, this.lungeTarget.position);
    const speed = this.env.buffs().attackSpeed * (kael ? 1 : 1.12);
    this.model.animator.play(clip, {
      fadeIn: chained ? 0.05 : 0.07,
      fadeOut: 0.18,
      speed,
      onEvent: (e) => this.onAttackEvent(e),
      onEnd: () => {
        if (this.state === 'attack') {
          this.state = 'move';
          this.comboIndex = -1;
        }
      },
    });
    this.env.sfx(kael ? 'swing_heavy' : 'swing_light', this.position);
  }

  private startHeavy(finisher: boolean) {
    const kael = this.character === 'kael';
    const clip = this.model.anims.clips[kael ? 'k_heavy' : 'l_heavy'];
    const st = this.stats;
    this.state = 'attack';
    this.stateT = 0;
    this.comboIndex = 99;
    this.comboOpen = false;
    this.queued = null;
    this.hitActive = false;
    this.hitSet.clear();
    this.currentAttack = {
      clip: clip.name,
      damage: st.heavyDamage * (finisher ? 1.4 : 1),
      poise: kael ? 45 : 36,
      knock: kael ? 7 : 5,
      range: kael ? 3.4 : 3.0,
      arc: kael ? 100 * DEG : 180 * DEG,
      finisher,
    };
    this.lungeTarget = this.findMagnetTarget(6);
    this.lungeT = kael ? 0.4 : 0.3;
    if (this.lungeTarget) this.yaw = yawTo(this.position, this.lungeTarget.position);
    this.model.animator.play(clip, {
      fadeIn: 0.06,
      fadeOut: 0.2,
      speed: this.env.buffs().attackSpeed,
      onEvent: (e) => this.onAttackEvent(e),
      onEnd: () => {
        if (this.state === 'attack') {
          this.state = 'move';
          this.comboIndex = -1;
        }
      },
    });
    this.model.glowBoost = 1.5;
    this.env.sfx('charge', this.position);
  }

  private onAttackEvent(e: string) {
    if (!this.currentAttack) return;
    const kael = this.character === 'kael';
    const color = kael ? 0x6fc8ff : (this.comboIndex % 2 === 0 ? 0xb48cff : 0x6fe0ff);
    if (e === 'hit_start') {
      this.hitActive = true;
      const isHeavy = this.comboIndex === 99;
      if (!isHeavy || !kael) {
        const p = this.chest().addScaledVector(this.facingDir(), 0.3);
        const tilt = this.comboIndex === 2 ? 1.2 : this.comboIndex === 1 ? -0.25 : 0.2;
        this.env.vfx.slash(p, this.yaw, this.currentAttack.range * 0.95, color, tilt, this.comboIndex === 1, 0.2);
      }
      this.sweepHits();
    } else if (e === 'hit_end') {
      this.hitActive = false;
    } else if (e === 'combo') {
      this.comboOpen = true;
    } else if (e === 'impact') {
      // Heavy AoE
      const center = this.position.clone().addScaledVector(this.facingDir(), kael ? 1.4 : 0);
      const radius = kael ? 3.4 : 3.2;
      this.aoe(center, radius, this.currentAttack.damage, this.currentAttack.poise, this.currentAttack.knock, 'heavy');
      this.env.vfx.shockwave(center, radius * 1.2, kael ? 0x6fc8ff : 0xb48cff);
      if (kael) this.env.vfx.sparks(center.clone().setY(this.position.y + 0.2), new THREE.Vector3(0, 1, 0), 30, 0x9fe0ff, 8);
      else this.env.vfx.slash(this.chest(), this.yaw, 3, 0xb48cff, 0, false, 0.25);
      this.env.shake(0.35);
      this.env.rumble(0.6, 200);
      this.env.sfx('slam', center);
    }
  }

  private sweepHits() {
    const a = this.currentAttack;
    if (!a) return;
    const origin = this.chest();
    this.env.combat.arc('player', origin, this.yaw, a.range, a.arc, -1.6, 2.4, (c, point) => {
      if (this.hitSet.has(c.id)) return;
      this.hitSet.add(c.id);
      this.applyHit(c, point, a.damage, a.poise, a.knock, this.comboIndex === 99 ? 'heavy' : 'light');
    });
  }

  private applyHit(c: Combatant, point: THREE.Vector3, damage: number, poise: number, knock: number, kind: HitInfo['kind'], stun?: number) {
    const b = this.env.buffs();
    const dir = new THREE.Vector3().subVectors(c.position, this.position).setY(0).normalize();
    const dmg = damage * b.damageMul;
    const applied = c.receiveHit({ damage: dmg, poise, knock: dir.multiplyScalar(knock), kind, point, source: this, stun });
    if (applied > 0) {
      this.ult = Math.min(100, this.ult + applied * 0.35);
      this.energy = Math.min(100, this.energy + (kind === 'light' ? 3 : 1));
      this.env.onDealtDamage(applied);
      this.env.hitstop(kind === 'heavy' || kind === 'ult' ? 0.085 : 0.045);
      this.env.shake(kind === 'heavy' ? 0.25 : 0.1);
      this.env.vfx.sparks(point, dir.clone().normalize(), kind === 'heavy' ? 22 : 12, this.character === 'kael' ? 0x9fe0ff : 0xc8a8ff, 7);
      this.env.vfx.flash(point, kind === 'heavy' ? 2.2 : 1.3, 0xffffff, 0.08);
      this.env.vfx.light(point, this.character === 'kael' ? 0x7fd0ff : 0xb48cff, 18, 0.12);
      this.env.sfx(kind === 'heavy' ? 'hit_heavy' : 'hit', point);
    }
    return applied;
  }

  private aoe(center: THREE.Vector3, radius: number, damage: number, poise: number, knock: number, kind: HitInfo['kind'], stun?: number) {
    let hits = 0;
    this.env.combat.radial('player', center, radius, (c, dist, point) => {
      const falloff = 1 - (dist / radius) * 0.4;
      if (this.applyHit(c, point, damage * falloff, poise, knock, kind, stun) > 0) hits++;
    });
    return hits;
  }

  private useAbility() {
    const st = this.stats;
    if (this.cdAbility > 0) {
      this.env.sfx('error', this.position);
      return;
    }
    if (this.character === 'kael') {
      if (!this.env.hasAbility('pulse')) return;
      if (this.energy < 35) {
        this.env.sfx('error', this.position);
        return;
      }
      this.energy -= 35;
      this.cdAbility = 6 * st.cooldownMul;
      this.state = 'ability';
      this.stateT = 0;
      this.velocity.set(0, this.velocity.y, 0);
      this.model.glowBoost = 2;
      events.emit('ability:used', { ability: 'pulse', character: 'kael' });
      this.env.sfx('charge', this.position);
      this.model.animator.play(this.model.anims.clips.k_pulse, {
        fadeIn: 0.06,
        onEvent: (e) => {
          if (e !== 'pulse') return;
          const center = this.position.clone();
          const r = st.pulseRadius;
          this.aoe(center, r, st.pulseDamage, 30 * st.pulseStagger + 30, 8 * st.pulseStagger, 'pulse');
          this.env.vfx.shockwave(center, r, 0x5fd8ff, 0.5);
          this.env.vfx.shockwave(center, r * 0.6, 0xffffff, 0.3);
          this.env.vfx.sparks(center.clone().setY(center.y + 0.3), new THREE.Vector3(0, 1, 0), 40, 0x7fd8ff, 9);
          this.env.vfx.light(center.clone().setY(center.y + 1), 0x5fd8ff, 60, 0.4);
          this.env.shake(0.45);
          this.env.rumble(0.8, 260);
          this.env.sfx('pulse', center);
        },
        onEnd: () => { if (this.state === 'ability') this.state = 'move'; },
      });
    } else {
      if (!this.env.hasAbility('echo')) {
        this.env.sfx('error', this.position);
        return;
      }
      if (this.energy < 25) {
        this.env.sfx('error', this.position);
        return;
      }
      this.energy -= 25;
      this.cdAbility = 4 * st.cooldownMul;
      this.state = 'ability';
      this.stateT = 0;
      this.model.glowBoost = 2;
      events.emit('ability:used', { ability: 'echo', character: 'lyra' });
      this.model.animator.play(this.model.anims.clips.l_echo, {
        fadeIn: 0.08,
        onEvent: (e) => {
          if (e !== 'echo') return;
          this.env.echo(this.position.clone(), st.echoRange, st.echoDuration);
          this.env.sfx('echo', this.position);
        },
        onEnd: () => { if (this.state === 'ability') this.state = 'move'; },
      });
    }
  }

  private useUltimate() {
    const st = this.stats;
    if (!st.ultimates) return;
    if (this.ult < 100) {
      this.env.sfx('error', this.position);
      return;
    }
    this.ult = 0;
    this.state = 'ult';
    this.stateT = 0;
    this.invuln = 1.8;
    this.model.glowBoost = 3;
    const kael = this.character === 'kael';
    events.emit('ability:used', { ability: kael ? 'core_break' : 'resonance', character: this.character });
    this.env.sfx('ult_charge', this.position);
    this.lungeTarget = this.findMagnetTarget(8);
    this.lungeT = kael ? 0.85 : 0;
    this.model.animator.play(this.model.anims.clips[kael ? 'k_ult' : 'l_ult'], {
      fadeIn: 0.08,
      onEvent: (e) => {
        if (e !== 'impact') return;
        const center = this.position.clone();
        const r = kael ? 9 : 8;
        this.aoe(center, r, kael ? 150 : 115, 200, kael ? 12 : 6, 'ult', kael ? 0 : 3);
        const col = kael ? 0x5fd8ff : 0xb48cff;
        this.env.vfx.shockwave(center, r, col, 0.7);
        this.env.vfx.shockwave(center, r * 0.7, 0xffffff, 0.45);
        this.env.vfx.shockwave(center.clone().setY(center.y + 1.2), r * 0.5, col, 0.6);
        this.env.vfx.sparks(center.clone().setY(center.y + 0.5), new THREE.Vector3(0, 1, 0), 80, col, 14);
        this.env.vfx.flash(center.clone().setY(center.y + 1), 8, col, 0.3);
        this.env.vfx.light(center.clone().setY(center.y + 2), col, 120, 0.6);
        this.env.shake(0.8);
        this.env.rumble(1, 500);
        this.env.hitstop(0.12);
        this.env.sfx('ult_impact', center);
      },
      onEnd: () => { if (this.state === 'ult') this.state = 'move'; },
    });
  }

  private startDash(wish: THREE.Vector3 | null) {
    const st = this.stats;
    const kael = this.character === 'kael';
    this.cancelActions();
    if (wish) this.dashDir.copy(wish).setY(0).normalize();
    else if (kael) this.facingDir(this.dashDir);
    else this.facingDir(this.dashDir).negate();
    const dist = st.dashDistance * this.env.buffs().dashMul;
    const dur = kael ? 0.17 : 0.15;
    this.dashSpeed = dist / dur;
    this.state = 'dash';
    this.stateT = 0;
    this.invuln = Math.max(this.invuln, st.dashIframes);
    this.dashCharges--;
    if (this.cdDash <= 0) this.cdDash = st.dashCooldown * st.cooldownMul;
    if (wish) this.yaw = Math.atan2(this.dashDir.x, this.dashDir.z);
    this.model.animator.play(this.model.anims.clips[kael ? 'dash' : 'phase_step'], { fadeIn: 0.03, fadeOut: 0.12, mask: 'full' });
    const col = kael ? 0x5fb8ff : 0xa47dff;
    this.env.vfx.flash(this.chest(), 2, col, 0.12);
    this.env.vfx.embers(this.chest(), 14, col, 0.8, 0.5);
    this.env.sfx(kael ? 'dash' : 'step', this.position);
    events.emit('ability:used', { ability: kael ? 'dash' : 'step', character: this.character });
  }

  private enterAim() {
    this.state = 'aim';
    this.stateT = 0;
    this.env.cam.aiming = true;
    this.env.input.aiming = true;
    this.model.animator.play(this.model.anims.clips[this.aimClip], { fadeIn: 0.1, hold: true, mask: 'upper' });
  }

  private exitAim() {
    this.state = 'move';
    this.env.cam.aiming = false;
    this.env.input.aiming = false;
    this.model.animator.stopActions(0.2);
  }

  private fireBolt(aimed: boolean) {
    if (this.cdBolt > 0) return;
    if (this.energy < 6) {
      this.env.sfx('error', this.position);
      return;
    }
    this.energy -= 6;
    this.cdBolt = 0.28;
    const kael = this.character === 'kael';
    const from = this.model.socketWorld(kael ? 'hand_R' : 'harness', new THREE.Vector3());
    if (!kael) from.add(this.facingDir().multiplyScalar(0.25));
    let target: Combatant | null = null;
    let dir: THREE.Vector3;
    const ph = this.env.physics();
    if (aimed) {
      const p = this.env.cam.aimPoint(ph);
      dir = p.sub(from).normalize();
      target = this.env.combat.bestTarget('player', this.env.cam.camera.position, this.env.cam.camera.getWorldDirection(new THREE.Vector3()), 60, 4 * DEG, true);
    } else {
      target = this.lockTarget ?? this.env.combat.bestTarget('player', this.chest(), this.env.cam.lookDir(), 40, 28 * DEG, true) ?? this.env.combat.bestTarget('player', this.chest(), this.facingDir(), 25, 40 * DEG, true);
      if (target) dir = target.aimPoint(new THREE.Vector3()).sub(from).normalize();
      else {
        const p = this.env.cam.aimPoint(ph);
        dir = p.sub(from).normalize();
      }
      // Face the shot
      this.yaw = Math.atan2(dir.x, dir.z);
    }
    const st = this.stats;
    const color = kael ? 0x6fd0ff : 0xb48cff;
    const shots = kael ? 1 : 2;
    for (let i = 0; i < shots; i++) {
      const d = dir.clone();
      if (i > 0) d.applyAxisAngle(new THREE.Vector3(0, 1, 0), 0.04);
      this.env.combat.fire({ from, dir: d, speed: 42, damage: st.boltDamage * this.env.buffs().damageMul, team: 'player', color, homing: target, turn: aimed ? 2 : 6, source: this, kind: 'bolt', poise: 6, size: kael ? 0.13 : 0.1 });
    }
    if (!aimed && this.state === 'move') this.model.animator.play(this.model.anims.clips[kael ? 'fire_r' : 'fire_l'], { fadeIn: 0.04, fadeOut: 0.18, mask: 'upper' });
    else if (aimed) this.model.animator.play(this.model.anims.clips[kael ? 'fire_r' : 'fire_l'], { fadeIn: 0.02, fadeOut: 0.1, mask: 'upper', layer: 'add' });
    this.env.sfx('bolt', from);
  }

  // ------------------------------------------------------------------ Scripted & companion
  private updateScripted(dt: number) {
    const sm = this.scriptedMove;
    if (sm) {
      const d = distXZ(this.position, sm.target);
      if (d < 0.25) {
        this.scriptedMove = null;
        this.velocity.set(0, this.velocity.y, 0);
        sm.done();
      } else {
        const dir = this.tmp.subVectors(sm.target, this.position).setY(0).normalize();
        this.velocity.x = damp(this.velocity.x, dir.x * sm.speed, 8, dt);
        this.velocity.z = damp(this.velocity.z, dir.z * sm.speed, 8, dt);
        this.yaw = dampAngle(this.yaw, Math.atan2(dir.x, dir.z), 8, dt);
      }
    } else {
      const k = Math.exp(-10 * dt);
      this.velocity.x *= k;
      this.velocity.z *= k;
    }
    this.moveBody(dt, this.velocity);
  }

  /** Follow the leader; occasionally support with bolts. */
  followLeader: Hero | null = null;
  private updateCompanion(dt: number) {
    const leader = this.followLeader;
    if (!leader || !this.body) {
      this.updatePhysicsOnly(dt);
      return;
    }
    // Breadcrumbs
    const last = this.trail[this.trail.length - 1];
    if (!last || last.distanceTo(leader.position) > 0.8) {
      this.trail.push(leader.position.clone());
      if (this.trail.length > 40) this.trail.shift();
    }
    const lf = leader.facingDir(this.tmp2);
    const side = new THREE.Vector3(lf.z, 0, -lf.x);
    const slot = leader.position.clone().addScaledVector(lf, -2.0).addScaledVector(side, 1.3);
    const dist = distXZ(this.position, leader.position);
    let goal = slot;
    if (dist > 6 && this.trail.length) {
      // Follow the trail when far, so we take the same route around obstacles.
      while (this.trail.length > 1 && distXZ(this.trail[0], this.position) < 1.2) this.trail.shift();
      goal = this.trail[0];
    }
    const toGoal = this.tmp.subVectors(goal, this.position).setY(0);
    const dGoal = toGoal.length();
    let speed = 0;
    if (dGoal > 0.6) speed = dist > 9 ? 7.4 : dist > 4 ? 5.2 : 2.6;
    const want = dGoal > 0.01 ? toGoal.normalize().multiplyScalar(speed) : toGoal.set(0, 0, 0);
    this.velocity.x = damp(this.velocity.x, want.x, 7, dt);
    this.velocity.z = damp(this.velocity.z, want.z, 7, dt);
    if (speed > 0.5) this.yaw = dampAngle(this.yaw, Math.atan2(want.x, want.z), 9, dt);
    else this.yaw = dampAngle(this.yaw, yawTo(this.position, leader.position) * 0.3 + leader.yaw * 0.7, 3, dt);
    // Jump if the leader is well above us and we're blocked.
    if (leader.position.y - this.position.y > 0.6 && this.body.grounded && dGoal < 3) this.velocity.y = 7.6;
    this.moveBody(dt, this.velocity);
    // Stuck / far: teleport behind the leader out of sight.
    const moved = this.position.distanceTo(this.lastPos);
    this.lastPos.copy(this.position);
    if (speed > 2 && moved < speed * dt * 0.2) this.stuckT += dt;
    else this.stuckT = Math.max(0, this.stuckT - dt);
    if (dist > 28 || this.stuckT > 1.6 || Math.abs(leader.position.y - this.position.y) > 6) {
      const behind = leader.position.clone().addScaledVector(lf, -2.5);
      const g = this.env.physics().groundAt(behind.x, leader.position.y + 1.5, behind.z, 4);
      const target = g !== null && Math.abs(g - leader.position.y) < 1.5 ? behind.setY(g + 0.05) : leader.position.clone();
      this.body.teleport(target);
      this.position.copy(target);
      this.stuckT = 0;
      this.trail = [];
      this.env.vfx.embers(this.chest(), 10, this.character === 'kael' ? 0x5fb8ff : 0xa47dff, 0.6, 0.6);
    }
    // Support fire
    this.supportT -= dt;
    if (this.supportT <= 0 && this.env.inCombat()) {
      this.supportT = 2.2 + Math.random() * 1.5;
      const t = this.env.combat.bestTarget('player', this.chest(), this.facingDir(), 22, Math.PI, true);
      if (t) {
        const from = this.chest();
        const dir = t.aimPoint(new THREE.Vector3()).sub(from).normalize();
        this.yaw = Math.atan2(dir.x, dir.z);
        this.env.combat.fire({ from, dir, speed: 36, damage: this.stats.boltDamage * 0.6, team: 'player', color: this.character === 'kael' ? 0x6fd0ff : 0xb48cff, homing: t, turn: 4, source: this, kind: 'bolt', poise: 4, size: 0.09 });
        this.model.animator.play(this.model.anims.clips[this.character === 'kael' ? 'fire_r' : 'fire_l'], { fadeIn: 0.05, fadeOut: 0.2, mask: 'upper' });
        this.env.sfx('bolt', from, 0.5);
      }
    }
    this.model.animator.lookYaw = 0;
  }

  /** Walk to a point (cinematics/scripted). */
  walkTo(target: THREE.Vector3, speed = 1.6): Promise<void> {
    return new Promise((resolve) => {
      this.state = 'scripted';
      this.scriptedMove = { target: target.clone(), speed, done: resolve };
    });
  }

  setScripted(on: boolean) {
    if (on) {
      this.cancelActions();
      this.state = 'scripted';
      this.velocity.set(0, 0, 0);
    } else {
      this.scriptedMove = null;
      if (this.state === 'scripted') this.state = this.alive ? 'move' : 'dead';
    }
  }

  playClip(name: string, opts: { hold?: boolean } = {}): Clip | null {
    const c = this.model.anims.clips[name];
    if (c) this.model.animator.play(c, { fadeIn: 0.2, fadeOut: 0.3, hold: opts.hold });
    return c ?? null;
  }

  dispose() {
    this.body?.dispose();
    this.body = null;
    this.model.dispose();
  }
}
