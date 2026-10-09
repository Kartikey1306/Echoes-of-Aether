import * as THREE from 'three';
import { distXZ } from '../core/MathUtil';
import { events } from '../core/Events';
import { Log } from '../core/Log';
import type { Physics } from '../physics/Physics';
import type { RenderSystem } from '../render/Renderer';
import { materialTime, setWetness } from '../render/Materials';
import { Data } from '../game/Data';
import type { GameState } from '../game/GameState';
import type { Combat } from '../game/Combat';
import type { VFX } from '../vfx/VFX';
import type { Enemy, EnemyEnv } from '../actors/enemies/Enemy';
import { Drone } from '../actors/enemies/Drone';
import { Sentinel } from '../actors/enemies/Sentinel';
import { Stalker } from '../actors/enemies/Stalker';
import { Guardian, type GuardianEnv } from '../actors/enemies/Guardian';
import { Npc } from '../actors/Npc';
import { buildPickupVisual, type PickupKind } from './Pickups';
import type { EncounterDef, Interactable, Zone, ZoneRuntime } from './Zone';

// Zone streaming, gameplay objects, encounters, pickups, NPCs and Echo Sight reveals.

export type ZoneFactory = () => Zone;
const registry: Record<string, () => Promise<ZoneFactory>> = {
  plaza: async () => (await import('./zones/PlazaZone')).PlazaZone as unknown as ZoneFactory,
  metro: async () => (await import('./zones/MetroZone')).MetroZone as unknown as ZoneFactory,
  facility: async () => (await import('./zones/FacilityZone')).FacilityZone as unknown as ZoneFactory,
  vault: async () => (await import('./zones/VaultZone')).VaultZone as unknown as ZoneFactory,
  rooftops: async () => (await import('./zones/RooftopsZone')).RooftopsZone as unknown as ZoneFactory,
  core: async () => (await import('./zones/CoreZone')).CoreZone as unknown as ZoneFactory,
};
export function registerZone(id: string, loader: () => Promise<ZoneFactory>) {
  registry[id] = loader;
}
export function zoneIds() {
  return Object.keys(registry);
}

/** Extra enemy classes registered by later modules (stalker, guardian). */
export const enemyFactories: Record<string, (env: EnemyEnv, type: string) => Enemy> = {
  drone: (env) => new Drone(Data.enemies.drone, env),
  sentinel: (env) => new Sentinel(Data.enemies.sentinel, env),
  warden: (env) => new Sentinel(Data.enemies.warden, env),
  stalker: (env) => new Stalker(Data.enemies.stalker, env),
  guardian: (env) => new Guardian(Data.enemies.guardian, env as GuardianEnv, false),
  guardian_vault: (env) => new Guardian(Data.enemies.guardian, env as GuardianEnv, true),
};

export interface WorldPickup {
  id: string;
  kind: PickupKind;
  pos: THREE.Vector3;
  base: THREE.Vector3;
  visual: ReturnType<typeof buildPickupVisual>;
  item?: string;
  powerup?: string;
  auto: boolean;
  hidden: boolean;
  collected: boolean;
  persist: boolean;
  cond?: string[];
  t: number;
}

export interface WorldHost {
  physics: () => Physics;
  rs: RenderSystem;
  combat: Combat;
  vfx: VFX;
  gs: () => GameState;
  enemyEnv: EnemyEnv;
  playerPos: () => THREE.Vector3 | null;
  playerVel: () => THREE.Vector3 | null;
  collectPickup: (p: WorldPickup) => void;
  talkTo: (npc: Npc) => void;
  openSave: () => void;
  useExit: (target: string, entry: string) => void;
  toast: (text: string, kind?: 'info' | 'warn') => void;
  sfx: (id: string, pos?: THREE.Vector3, vol?: number) => void;
  shake: (a: number) => void;
  damagePlayer: (amount: number, source: string, from?: THREE.Vector3) => void;
  quality: () => { effects: 'low' | 'medium' | 'high'; textures: 'low' | 'medium' | 'high' };
  giveItem: (id: string, qty: number) => void;
  playDialogue: (id: string) => void;
  traverse: (points: THREE.Vector3[], clip: string, duration: number, endYaw?: number) => Promise<void>;
}

interface ActiveEncounter {
  def: EncounterDef;
  wave: number;
  enemies: Enemy[];
}

export class World {
  zone: Zone | null = null;
  npcs: Npc[] = [];
  enemies: Enemy[] = [];
  pickups: WorldPickup[] = [];
  encounters = new Map<string, ActiveEncounter>();
  echoT = 0;
  echoRange = 0;
  echoCenter = new THREE.Vector3();
  echoTotal = 0;
  candidate: Interactable | null = null;
  candidateLocked: string | null = null;
  private exitCooldown = 0;
  loading = false;
  private tokens = new Set<number>();
  /** Enemies hold still during cinematics. */
  freezeEnemies = false;
  maxTokens = 2;
  readonly runtime: ZoneRuntime;

  constructor(private host: WorldHost) {
    const self = this;
    this.runtime = {
      get playerPos() { return host.playerPos() ?? new THREE.Vector3(); },
      check: (c) => host.gs().check(c),
      revealed: (id) => host.gs().isRevealed(id),
      flag: (n) => host.gs().flag(n),
      setFlag: (n, v = true) => host.gs().setFlag(n, v),
      emitInteract: (id) => events.emit('interact', { id, kind: 'inspect' }),
      toast: (t) => host.toast(t),
      sfx: (id, pos) => host.sfx(id, pos),
      damagePlayer: (a, s, f) => host.damagePlayer(a, s, f),
      get echoActive() { return self.echoT > 0; },
      shake: (a) => host.shake(a),
      vfx: host.vfx,
      removeCollider: (c) => host.physics().removeCollider(c),
      get playerVelocity() { return host.playerVel() ?? new THREE.Vector3(); },
      spawnEncounter: (id) => self.spawnEncounter(id),
      isDefeated: (id) => host.gs().isDefeated(id),
      hint: (t) => host.toast(t, 'info'),
      giveItem: (id, qty = 1) => host.giveItem(id, qty),
      playDialogue: (id) => host.playDialogue(id),
      traverse: (pts, clip, dur, yaw) => host.traverse(pts, clip, dur, yaw),
    };
  }

  get echoActive() {
    return this.echoT > 0;
  }

  // ------------------------------------------------------------------ Loading
  async load(zoneId: string, progress: (f: number, label: string) => Promise<void>): Promise<Zone> {
    this.loading = true;
    try {
      this.unload();
      const loader = registry[zoneId];
      if (!loader) throw new Error('Unknown zone ' + zoneId);
      await progress(0.02, 'Loading zone module');
      const Factory = await loader();
      const zone = new (Factory as unknown as new () => Zone)();
      zone.bindRuntime(this.runtime);
      const gs = this.host.gs();
      await zone.build({
        physics: this.host.physics(),
        rs: this.host.rs,
        progress: (f, l) => progress(0.05 + f * 0.65, l),
        quality: this.host.quality(),
        flag: (n) => gs.flag(n),
      });
      this.zone = zone;
      await progress(0.72, 'Placing survivors');
      for (const n of zone.npcs) {
        const npc = new Npc(n, this.host.physics());
        if (n.id === 'bolt') {
          npc.boltActive = gs.flag('bolt_repaired');
          npc.applyBehaviour();
        }
        zone.scene.add(npc.root);
        this.npcs.push(npc);
        zone.addInteractable({
          id: 'npc_' + n.id,
          kind: 'npc',
          pos: n.pos.clone().setY(n.pos.y + 1.2),
          radius: 2.4,
          prompt: () => `Talk to ${Data.speakers[n.id]?.name ?? n.id}`,
          available: () => (n.id === 'bolt' ? true : !n.echoOnly || this.echoActive) && (n.available ? n.available() : true),
          onInteract: () => this.host.talkTo(npc),
        });
      }
      await progress(0.78, 'Placing collectibles');
      for (const c of zone.collectibles) {
        const def = Data.collectibles[c.id];
        if (!def) {
          Log.error('world', 'unknown collectible', c.id);
          continue;
        }
        if (gs.isCollected(c.id)) continue;
        this.addPickup({ id: c.id, kind: def.kind, pos: c.pos, auto: def.kind !== 'cache', hidden: def.hidden && !gs.isRevealed(c.id), persist: true });
      }
      for (const p of zone.itemPickups) {
        if (gs.isCollected(p.id)) continue;
        this.addPickup({ id: p.id, kind: 'quest', pos: p.pos, item: p.item, auto: false, hidden: false, persist: true, cond: p.cond });
      }
      await progress(0.84, 'Waking enemies');
      for (const e of zone.encounters) {
        const requested = gs.flag('enc_' + e.id);
        const defeated = gs.isDefeated(e.id) && !e.respawn;
        if (defeated) continue;
        if (e.spawn === 'auto' || (e.spawn === 'quest' && requested)) this.spawnEncounter(e.id);
      }
      // Shared groups live in every zone scene.
      zone.scene.add(this.host.vfx.group, this.host.combat.group);
      await progress(0.88, 'Compiling shaders');
      this.host.rs.setScene(zone.scene);
      this.host.rs.setGrade(zone.grade);
      await this.host.rs.compile(zone.scene, this.host.rs.camera);
      await progress(0.98, 'Finalising');
      return zone;
    } finally {
      this.loading = false;
    }
  }

  unload() {
    for (const e of this.enemies) e.dispose();
    this.enemies = [];
    this.encounters.clear();
    this.tokens.clear();
    for (const n of this.npcs) n.dispose();
    this.npcs = [];
    for (const p of this.pickups) p.visual.group.removeFromParent();
    this.pickups = [];
    this.host.vfx.clear();
    this.host.combat.clearProjectiles();
    if (this.zone) {
      this.zone.dispose();
      this.zone = null;
    }
    this.echoT = 0;
    this.candidate = null;
    // Physics world is reset by the game before the next build.
  }

  // ------------------------------------------------------------------ Pickups
  addPickup(o: { id: string; kind: PickupKind; pos: THREE.Vector3; item?: string; powerup?: string; auto: boolean; hidden: boolean; persist: boolean; cond?: string[] }) {
    if (!this.zone) return null;
    const visual = buildPickupVisual(o.kind, o.powerup);
    visual.group.position.copy(o.pos);
    this.zone.scene.add(visual.group);
    const p: WorldPickup = { ...o, base: o.pos.clone(), visual, collected: false, t: Math.random() * 6 };
    visual.group.visible = !o.hidden;
    this.pickups.push(p);
    if (!o.auto) {
      const label = o.kind === 'cache' ? 'Open hidden cache' : o.item ? `Take ${Data.items[o.item]?.name ?? o.item}` : 'Pick up';
      this.zone.addInteractable({
        id: o.id,
        kind: o.kind === 'cache' ? 'cache' : 'pickup',
        pos: o.pos.clone(),
        radius: 2,
        prompt: label,
        hidden: o.hidden,
        available: () => !p.collected && (!o.cond || this.host.gs().checkAll(o.cond)),
        onInteract: () => this.collect(p),
      });
    }
    return p;
  }

  collect(p: WorldPickup) {
    if (p.collected) return;
    p.collected = true;
    if (p.persist) this.host.gs().markCollected(p.id);
    const i = this.zone?.findInteractable(p.id);
    if (i) i.consumed = true;
    if (p.kind === 'cache') {
      const lid = p.visual.group.getObjectByName('lid');
      if (lid) lid.rotation.x = -1.6;
      p.visual.halo.visible = false;
    } else p.visual.group.visible = false;
    this.host.vfx.flash(p.pos, 1.6, p.visual.light, 0.2);
    this.host.vfx.embers(p.pos, 18, p.visual.light, 0.4, 2.2);
    this.host.vfx.shockwave(p.pos.clone().setY(p.pos.y - 0.5), 1.6, p.visual.light, 0.4);
    this.host.collectPickup(p);
    events.emit('pickup', { id: p.id });
  }

  // ------------------------------------------------------------------ Encounters
  spawnEncounter(id: string) {
    const z = this.zone;
    if (!z) return;
    const def = z.encounters.find((e) => e.id === id);
    if (!def) {
      Log.warn('world', `encounter ${id} not in zone ${z.id}`);
      return;
    }
    if (this.encounters.has(id)) return;
    if (this.host.gs().isDefeated(id) && !def.respawn) return;
    const enc: ActiveEncounter = { def, wave: 0, enemies: [] };
    this.encounters.set(id, enc);
    this.spawnWave(enc);
    events.emit('encounter:started', { id });
  }

  private spawnWave(enc: ActiveEncounter) {
    const wave = enc.def.waves[enc.wave];
    if (!wave) return;
    for (const pl of wave) {
      const f = enemyFactories[pl.type];
      if (!f) {
        Log.error('world', 'no enemy factory for', pl.type);
        continue;
      }
      const e = f(this.host.enemyEnv, pl.type);
      e.encounterId = enc.def.id;
      e.arena = enc.def.arena ?? null;
      e.spawn(pl.pos, pl.yaw ?? Math.PI);
      enc.enemies.push(e);
      this.enemies.push(e);
      if (enc.wave > 0 || enc.def.spawn === 'quest') e.setAggro();
      this.host.vfx.flash(pl.pos.clone().setY(pl.pos.y + 1), 2, 0xff5a3a, 0.2);
    }
  }

  /** Extra enemy joining an active encounter (boss summons). */
  spawnMinion(type: string, pos: THREE.Vector3, encounterId: string | null) {
    const f = enemyFactories[type];
    if (!f || !this.zone) return;
    const g = this.host.physics().groundAt(pos.x, pos.y + 2, pos.z, 12);
    const at = type === 'drone' ? pos.clone() : pos.clone().setY((g ?? pos.y) + 0.05);
    const e = f(this.host.enemyEnv, type);
    e.encounterId = encounterId;
    const enc = encounterId ? this.encounters.get(encounterId) : null;
    e.arena = enc?.def.arena ?? null;
    e.spawn(at, 0);
    e.setAggro();
    this.enemies.push(e);
    enc?.enemies.push(e);
    this.host.vfx.flash(at.clone().setY(at.y + 1), 2.4, 0xff5a3a, 0.25);
    this.host.vfx.embers(at.clone().setY(at.y + 1), 20, 0xff5a3a, 1, 1);
  }

  despawnEncounter(id: string) {
    const enc = this.encounters.get(id);
    if (!enc) return;
    for (const e of enc.enemies) {
      e.dispose();
      this.enemies = this.enemies.filter((x) => x !== e);
    }
    this.encounters.delete(id);
  }

  onEnemyKilled(e: Enemy) {
    const id = e.encounterId;
    if (!id) return;
    const enc = this.encounters.get(id);
    if (!enc) return;
    if (enc.enemies.some((x) => x.alive)) return;
    if (enc.wave < enc.def.waves.length - 1) {
      enc.wave++;
      setTimeout(() => {
        if (this.encounters.get(id) === enc) this.spawnWave(enc);
      }, 1500);
      return;
    }
    this.encounters.delete(id);
    if (!enc.def.respawn) this.host.gs().markDefeated(id);
    enc.def.onCleared?.();
    events.emit('encounter:cleared', { id });
  }

  // ------------------------------------------------------------------ Attack tokens
  requestToken(e: Enemy) {
    if (this.tokens.has(e.id)) return true;
    // Drop tokens held by dead/disposed enemies.
    for (const id of this.tokens) if (!this.enemies.some((x) => x.id === id && x.alive)) this.tokens.delete(id);
    if (this.tokens.size >= this.maxTokens) return false;
    this.tokens.add(e.id);
    return true;
  }
  releaseToken(e: Enemy) {
    this.tokens.delete(e.id);
  }

  // ------------------------------------------------------------------ Echo Sight
  echoReveal(center: THREE.Vector3, range: number, duration: number) {
    this.echoT = Math.max(this.echoT, duration);
    this.echoTotal = Math.max(this.echoT, duration);
    this.echoRange = range;
    this.echoCenter.copy(center);
    this.host.vfx.echoReveal(center, range);
  }

  private updateEcho(dt: number, playerPos: THREE.Vector3 | null) {
    if (this.echoT <= 0 || !this.zone) return;
    this.echoT -= dt;
    const gs = this.host.gs();
    const center = playerPos ?? this.echoCenter;
    for (const i of this.zone.interactables) {
      if (!i.hidden || gs.isRevealed(i.id)) continue;
      if (i.pos.distanceTo(center) <= this.echoRange) {
        gs.reveal(i.id);
        i.onReveal?.();
        if (i.revealObject) i.revealObject.visible = true;
        this.host.vfx.flash(i.pos, 2, 0xa47dff, 0.4);
        this.host.vfx.embers(i.pos, 20, 0xa47dff, 1, 1.2);
        this.host.sfx('reveal', i.pos);
        this.host.toast('Echo revealed something hidden', 'info');
      }
    }
    for (const p of this.pickups) {
      if (!p.hidden || p.collected) continue;
      if (p.pos.distanceTo(center) <= this.echoRange) {
        p.hidden = false;
        gs.reveal(p.id);
        p.visual.group.visible = true;
        const ii = this.zone.findInteractable(p.id);
        if (ii) ii.hidden = false;
        this.host.vfx.flash(p.pos, 1.6, 0xa47dff, 0.4);
        this.host.sfx('reveal', p.pos);
      }
    }
  }

  // ------------------------------------------------------------------ Per frame
  update(dt: number, playerPos: THREE.Vector3 | null, canInteract: boolean, revealBuff: boolean) {
    const z = this.zone;
    if (!z) return;
    materialTime(z.time);
    setWetness(z.weather && z.weather.cfg.rain > 0 && !z.indoor ? 1 : 0);
    if (revealBuff && this.echoT < 0.2) this.echoReveal(playerPos ?? new THREE.Vector3(), 24, 0.6);
    this.updateEcho(dt, playerPos);
    z.update(dt, this.runtime);
    if (z.weather) z.weather.update(dt, this.host.rs.camera);
    for (const n of this.npcs) n.update(dt, playerPos, this.echoActive);
    if (!this.freezeEnemies) for (const e of this.enemies) e.update(dt);
    else for (const e of this.enemies) (e as unknown as { updateModelOnly?: (d: number) => void }).updateModelOnly?.(dt);
    this.enemies = this.enemies.filter((e) => !e.disposed);
    // Pickups: bob/spin, auto collection
    for (const p of this.pickups) {
      if (p.collected) continue;
      p.t += dt;
      const g = p.visual.group;
      if (p.kind !== 'cache') {
        g.position.y = p.base.y + Math.sin(p.t * 2) * 0.08;
        p.visual.spin.rotation.y += dt * 1.6;
      }
      p.visual.halo.material.opacity = 0.75 + Math.sin(p.t * 3) * 0.25;
      if (p.auto && !p.hidden && playerPos && canInteract) {
        const near = p.pos.distanceTo(playerPos.clone().setY(playerPos.y + 0.9));
        if (near < 1.5 && (!p.cond || this.host.gs().checkAll(p.cond))) this.collect(p);
      }
    }
    if (!playerPos) {
      this.candidate = null;
      return;
    }
    // Triggers
    for (const t of z.triggers) {
      const inside = t.box.containsPoint(playerPos.clone().setY(playerPos.y + 0.5));
      if (inside && !t.inside && (!t.available || t.available())) {
        t.inside = true;
        if (!t.once || !t.fired) {
          t.fired = true;
          t.onEnter?.();
          events.emit('trigger:enter', { id: t.id });
          for (const e of z.encounters) if (e.spawn === `trigger:${t.id}`) this.spawnEncounter(e.id);
        }
      } else if (!inside && t.inside) {
        t.inside = false;
        events.emit('trigger:exit', { id: t.id });
      }
    }
    // Exits
    this.exitCooldown = Math.max(0, this.exitCooldown - dt);
    let exitCandidate: Interactable | null = null;
    for (const x of z.exits) {
      const d = x.pos.distanceTo(playerPos);
      if (d > x.radius) continue;
      const ok = !x.requires || x.requires();
      if (x.auto && ok && this.exitCooldown <= 0 && canInteract) {
        this.exitCooldown = 3;
        this.host.useExit(x.target, x.entry);
        return;
      }
      exitCandidate = {
        id: x.id,
        kind: 'exit',
        pos: x.pos,
        radius: x.radius,
        prompt: x.prompt,
        available: () => !x.requires || x.requires(),
        lockedReason: () => (x.requires && !x.requires() ? x.lockedText ?? 'Locked' : null),
        onInteract: () => {
          if (this.exitCooldown > 0) return;
          this.exitCooldown = 3;
          this.host.useExit(x.target, x.entry);
        },
      };
    }
    // Interaction candidate: nearest available within radius.
    let best: Interactable | null = exitCandidate;
    let bestD = exitCandidate ? exitCandidate.pos.distanceTo(playerPos) : Infinity;
    let locked: string | null = exitCandidate?.lockedReason?.() ?? null;
    for (const i of z.interactables) {
      if (i.consumed) continue;
      if (i.hidden && !this.host.gs().isRevealed(i.id)) continue;
      const d = distXZ(i.pos, playerPos) + Math.abs(i.pos.y - (playerPos.y + 1)) * 0.5;
      if (d > i.radius || d >= bestD) continue;
      const avail = !i.available || i.available();
      const reason = !avail && i.lockedReason ? i.lockedReason() : null;
      if (!avail && !reason) continue;
      best = i;
      bestD = d;
      locked = avail ? null : reason;
    }
    this.candidate = best;
    this.candidateLocked = locked;
  }

  interact() {
    const c = this.candidate;
    if (!c || this.candidateLocked) {
      if (this.candidateLocked) this.host.toast(this.candidateLocked, 'warn');
      return false;
    }
    if (c.kind === 'save') {
      this.host.openSave();
      return true;
    }
    void c.onInteract();
    return true;
  }

  aggroCount(near: THREE.Vector3, radius = 35) {
    return this.enemies.filter((e) => e.alive && e.aggro && e.position.distanceTo(near) < radius).length;
  }

  findNpc(id: string) {
    return this.npcs.find((n) => n.id === id) ?? null;
  }
}
