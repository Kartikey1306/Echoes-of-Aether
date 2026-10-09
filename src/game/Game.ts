import * as THREE from 'three';
import { events } from '../core/Events';
import { Input, type Action as InputAction } from '../core/Input';
import { Log } from '../core/Log';
import { clamp, distXZ } from '../core/MathUtil';
import { Physics } from '../physics/Physics';
import { RenderSystem } from '../render/Renderer';
import { TexQuality } from '../render/TexGen';
import { AudioEngine, type MusicMood } from '../audio/AudioEngine';
import { Voice } from '../audio/Voice';
import { CameraRig } from '../actors/CameraRig';
import { Hero, type HeroEnv } from '../actors/Hero';
import type { Npc } from '../actors/Npc';
import type { Enemy, EnemyEnv } from '../actors/enemies/Enemy';
import { VFX } from '../vfx/VFX';
import { World, type WorldPickup } from '../world/World';
import type { Zone } from '../world/Zone';
import { Combat } from './Combat';
import { Data, type Action } from './Data';
import { DialogueSystem } from './Dialogue';
import { GameState, newGameState, type CharacterId, type GameStateData } from './GameState';
import { Inventory } from './Inventory';
import { Powerups } from './Powerups';
import { Progression } from './Progression';
import { QuestSystem } from './Quests';
import { SaveSystem, type SaveEnvelope, type SaveKind } from './SaveSystem';
import { Settings } from './Settings';
import { Cinematics } from './Cinematics';
import { UI } from '../ui/UI';
import { MenuScene } from '../world/MenuScene';
import { AppearanceStore, applyAppearance, baseLook, sanitizeAppearance, type Appearance } from '../actors/human/Appearance';
import type { Look } from '../actors/human/HumanBuilder';

export type Mode = 'boot' | 'menu' | 'charselect' | 'loading' | 'play' | 'credits';

const QUICK: Record<string, string> = { quick1: 'pu_aether_shard', quick2: 'pu_phase_core', quick3: 'pu_overcharge', quick4: 'pu_shield_fragment', quick5: 'pu_echo_fragment' };

export class Game {
  readonly rs: RenderSystem;
  readonly input: Input;
  physics: Physics;
  readonly audio = new AudioEngine();
  readonly voice = new Voice();
  readonly settings = new Settings();
  readonly saves = new SaveSystem();
  readonly appearance = new AppearanceStore();
  /** True while the Character Designer is open (renders the menu stage). */
  designerActive = false;
  gs: GameState = new GameState(newGameState('kael'));
  readonly inventory: Inventory;
  readonly progression: Progression;
  readonly powerups = new Powerups();
  readonly quests: QuestSystem;
  readonly dialogue: DialogueSystem;
  readonly vfx = new VFX();
  readonly combat: Combat;
  readonly cam: CameraRig;
  readonly world: World;
  readonly ui: UI;
  readonly cinematics: Cinematics;
  menu: MenuScene | null = null;
  mode: Mode = 'boot';
  heroes: Partial<Record<CharacterId, Hero>> = {};
  /** Overlays that pause gameplay (pause menu, panels, save screen, death screen). */
  paused = false;
  inDialogue = false;
  private timeScale = 1;
  private hitstopT = 0;
  private time = 0;
  private lastFrame = performance.now();
  private inCombat = false;
  private combatT = 0;
  private bossActive = false;
  private swapCd = 0;
  private dying = false;
  private frameAcc = 0;
  private lastChar: CharacterId = 'kael';
  fps = 60;
  frameMs = 16;
  private fpsAcc = 0;
  private fpsFrames = 0;
  debugVisible = false;
  private enemyEnv: EnemyEnv;
  private heroEnv: HeroEnv;
  /** Entry used when the current zone was entered (respawn point). */
  private currentEntry = 'start';
  /** Soft camera-side fill light that keeps the protagonist readable in dark scenes. */
  private fill = new THREE.PointLight(0xc8d6ea, 9, 9, 1.6);

  constructor(container: HTMLElement) {
    const s = this.settings.data;
    TexQuality.size = s.graphics.textures === 'high' ? 512 : s.graphics.textures === 'medium' ? 512 : 256;
    this.rs = new RenderSystem(container, s.graphics);
    this.input = new Input(this.rs.canvas);
    this.physics = new Physics();
    this.inventory = new Inventory(() => this.gs);
    this.progression = new Progression(() => this.gs, this.inventory);
    this.combat = new Combat(() => this.physics, this.vfx);
    this.cam = new CameraRig(this.rs.camera);
    this.ui = new UI(this, container);
    this.dialogue = new DialogueSystem(() => this.gs, () => this.ui.dialogue, (a) => this.runActions(a));
    this.quests = new QuestSystem(() => this.gs, {
      runActions: (a, ctx) => this.runActions(a, ctx),
      currentZone: () => this.world.zone?.id ?? '',
      partnerName: () => (this.gs.d.character === 'kael' ? 'Lyra' : 'Kael'),
    });
    this.cinematics = new Cinematics(this);
    this.enemyEnv = {
      physics: () => this.physics,
      combat: this.combat,
      vfx: this.vfx,
      scene: () => this.world.zone?.scene ?? this.rs.scene,
      player: () => this.player,
      sfx: (id, pos, vol) => this.audio.play(id, pos, vol),
      difficulty: () => this.settings.difficultyMods,
      echoActive: () => this.world.echoActive,
      onKilled: (e) => this.onEnemyKilled(e),
      onAggro: (e) => this.onEnemyAggro(e),
      shake: (a) => this.shake(a),
      requestToken: (e) => this.world.requestToken(e),
      releaseToken: (e) => this.world.releaseToken(e),
      cameraSees: (p) => this.cameraSees(p),
      dropItem: (item, pos) => this.dropItem(item, pos),
      spawnMinion: (type: string, pos: THREE.Vector3, enc: string | null) => this.world.spawnMinion(type, pos, enc),
      setBoss: (on: boolean) => this.setBoss(on),
    } as EnemyEnv;
    this.heroEnv = {
      input: this.input,
      cam: this.cam,
      physics: () => this.physics,
      combat: this.combat,
      vfx: this.vfx,
      stats: (c) => this.progression.stats(c),
      buffs: () => this.powerups.buffs(),
      hasAbility: (id) => this.gs.hasAbility(id),
      sfx: (id, pos, vol) => this.audio.play(id, pos, vol),
      hitstop: (s) => this.hitstop(s),
      shake: (a) => this.shake(a),
      rumble: (i, ms) => {
        if (this.settings.data.controls.vibration) this.input.rumble(i, ms);
      },
      echo: (c, r, d) => this.world.echoReveal(c, r, d),
      difficulty: () => this.settings.difficultyMods,
      killY: () => this.world.zone?.killY ?? -50,
      inCombat: () => this.inCombat,
      onDied: (h) => this.onPlayerDied(h),
      onDamaged: (a) => {
        this.gs.d.stats.damageTaken += a;
        this.ui.hud.damagePulse(a);
      },
      onDealtDamage: (a) => (this.gs.d.stats.damageDealt += a),
      controllable: () => this.mode === 'play' && !this.paused && !this.inDialogue && !this.cinematics.active,
    };
    this.world = new World({
      physics: () => this.physics,
      rs: this.rs,
      combat: this.combat,
      vfx: this.vfx,
      gs: () => this.gs,
      enemyEnv: this.enemyEnv,
      playerPos: () => this.player?.position ?? null,
      playerVel: () => this.player?.velocity ?? null,
      collectPickup: (p) => this.onPickup(p),
      talkTo: (n) => void this.talkTo(n),
      openSave: () => this.ui.openSaveScreen('save', true),
      useExit: (t, e) => void this.changeZone(t, e),
      toast: (t, k) => this.ui.toast(t, k),
      sfx: (id, pos, vol) => this.audio.play(id, pos, vol),
      shake: (a) => this.shake(a),
      damagePlayer: (amount, source, from) => {
        const p = this.player;
        if (!p) return;
        const knock = from ? new THREE.Vector3().subVectors(p.position, from).setY(0).normalize().multiplyScalar(5) : new THREE.Vector3();
        p.receiveHit({ damage: amount, poise: 20, knock, kind: 'hazard', point: p.position.clone(), source: null });
      },
      quality: () => ({ effects: this.settings.data.graphics.effects, textures: this.settings.data.graphics.textures }),
      giveItem: (id, qty) => {
        const n = this.inventory.add(id, qty);
        if (n > 0) this.ui.toast(`${Data.items[id]?.category === 'lore' ? 'Log recovered' : 'Received'}: ${Data.items[id]?.name ?? id}`, Data.items[id]?.category === 'lore' ? 'lore' : 'item');
      },
      playDialogue: (id) => void this.playDialogue(id, 'radio'),
      traverse: (pts, clip, dur, yaw) => this.traverse(pts, clip, dur, yaw),
    });
    this.combat.onHit = (h, target) => {
      if (target.team === 'enemy') this.ui.hud.hitMarker();
    };
    this.input.onUnlock = () => {
      if (this.mode === 'play' && !this.paused && !this.inDialogue && !this.cinematics.active && !this.dying) this.ui.openPause();
    };
    this.wireEvents();
    this.applySettings();
    events.on('settings:changed', () => this.applySettings());
    // Unlock audio on the first gesture.
    const unlock = () => {
      this.audio.unlock();
      if (this.audio.unlocked) {
        window.removeEventListener('pointerdown', unlock);
        window.removeEventListener('keydown', unlock);
      }
    };
    window.addEventListener('pointerdown', unlock);
    window.addEventListener('keydown', unlock);
    window.addEventListener('blur', () => {
      if (this.mode === 'play' && !this.paused && !this.cinematics.active && !this.inDialogue) this.ui.openPause();
    });
  }

  /** Appearance in effect: the save's own when playing, otherwise the global preference. */
  appearanceFor(c: CharacterId): Appearance {
    const fromSave = this.mode !== 'menu' && this.mode !== 'charselect' ? this.gs.d.appearance?.[c] : undefined;
    return fromSave ? sanitizeAppearance(c, fromSave) : this.appearance.get(c);
  }

  lookFor(c: CharacterId): Look {
    return applyAppearance(baseLook(c), this.appearanceFor(c));
  }

  /** Apply an edited appearance everywhere it is shown. */
  async setAppearance(c: CharacterId, a: Appearance) {
    this.appearance.set(c, a);
    if (this.mode === 'play' || this.mode === 'loading') {
      this.gs.d.appearance = { ...(this.gs.d.appearance ?? {}), [c]: a };
    }
  }

  /** Rebuild visuals after appearance edits (heroes in the world, portraits). */
  async refreshAppearanceVisuals() {
    const { buildPortraits } = await import('../ui/Portraits');
    await buildPortraits(this.rs.renderer, ['kael', 'lyra'], (id) => (id === 'kael' || id === 'lyra' ? this.lookFor(id) : null), true);
    for (const c of ['kael', 'lyra'] as CharacterId[]) {
      const h = this.heroes[c];
      if (h) h.rebuildModel(this.lookFor(c), this.mode === 'play' ? this.physics : null);
    }
    this.ui.hud.characterChanged();
  }

  get player(): Hero | null {
    return this.heroes[this.gs.d.character] ?? null;
  }
  get companion(): Hero | null {
    const other: CharacterId = this.gs.d.character === 'kael' ? 'lyra' : 'kael';
    return this.gs.flag('swap_unlocked') ? this.heroes[other] ?? null : null;
  }

  // ------------------------------------------------------------------ Boot / menu
  async boot() {
    this.menu = new MenuScene(this);
    await this.menu.build();
    this.showMenu();
    requestAnimationFrame(this.loop);
  }

  showMenu() {
    this.mode = 'menu';
    this.paused = false;
    this.input.releaseLock();
    this.input.gameplayEnabled = false;
    this.cinematics.stop();
    if (this.menu) {
      this.menu.enter('menu');
      this.rs.setScene(this.menu.scene);
      this.rs.setGrade(this.menu.grade);
    }
    this.ui.showMainMenu();
    this.audio.setMusic('menu');
    this.audio.setAmbience('rain_city');
  }

  showCharSelect() {
    this.mode = 'charselect';
    this.menu?.enter('charselect');
    this.ui.showCharSelect();
  }

  async newGame(character: CharacterId, slot: number) {
    this.gs = new GameState(newGameState(character));
    this.gs.d.appearance = this.appearance.all();
    this.saves.activeSlot = slot;
    this.powerups.clear();
    this.disposeHeroes();
    this.lastChar = character;
    await this.loadZone('plaza', 'start', { intro: true });
  }

  async continueGame(env?: SaveEnvelope | null) {
    const e = env ?? (await this.saves.latest());
    if (!e) {
      this.ui.toast('No save found', 'warn');
      return;
    }
    await this.loadFromEnvelope(e);
  }

  async loadFromEnvelope(env: SaveEnvelope) {
    this.gs = new GameState(JSON.parse(JSON.stringify(env.state)) as GameStateData);
    this.saves.activeSlot = env.slot;
    this.powerups.clear();
    this.disposeHeroes();
    this.audio.play('load');
    const entry = this.gs.d.position ? '__saved' : this.gs.d.entry;
    await this.loadZone(this.gs.d.zone, entry, {});
  }

  // ------------------------------------------------------------------ Zones
  async loadZone(zoneId: string, entry: string, opts: { intro?: boolean; respawn?: boolean; cinematic?: boolean }) {
    this.mode = 'loading';
    this.paused = false;
    this.inDialogue = false;
    this.dying = false;
    this.input.gameplayEnabled = false;
    this.input.releaseLock();
    if (!opts.cinematic) this.cinematics.stop();
    this.dialogue.cancel();
    this.voice.stop();
    const meta = Data.zones[zoneId];
    this.ui.hideAllScreens();
    if (!opts.cinematic) this.ui.loading.show(meta);
    this.audio.setMusic('silence');
    const t0 = performance.now();
    const progress = async (f: number, label: string) => {
      this.ui.loading.progress(f, label);
      // Yield a frame so the progress bar actually renders.
      await new Promise((r) => requestAnimationFrame(() => r(null)));
    };
    try {
      await progress(0, 'Preparing');
      // Fresh physics world for the zone.
      for (const h of Object.values(this.heroes)) if (h) { h.body?.dispose(); h.body = null; }
      this.world.unload();
      this.physics.reset();
      TexQuality.size = this.settings.data.graphics.textures === 'low' ? 256 : 512;
      const zone = await this.world.load(zoneId, progress);
      await progress(0.9, 'Placing characters');
      zone.scene.add(this.fill);
      this.placeHeroes(zone, entry);
      this.gs.d.zone = zoneId;
      if (entry !== '__saved') this.gs.d.entry = entry;
      this.currentEntry = entry === '__saved' ? this.gs.d.entry : entry;
      this.gs.d.checkpoint = { zone: zoneId, pos: this.player!.position.toArray() as [number, number, number], yaw: this.player!.yaw };
      this.restoreStageWorldActions();
      // Compile shaders for the actors placed in the zone.
      await this.rs.compile(zone.scene, this.rs.camera);
      await progress(1, 'Ready');
      Log.info('game', `zone ${zoneId} loaded in ${Math.round(performance.now() - t0)} ms`);
    } catch (err) {
      Log.error('game', 'zone load failed', err);
      this.ui.loading.error(String((err as Error)?.message ?? err));
      return;
    }
    this.ui.loading.hide();
    this.mode = 'play';
    this.input.gameplayEnabled = true;
    this.ui.showHud();
    this.audio.setAmbience((this.world.zone?.ambience ?? 'none') as never);
    this.updateMusic(true);
    this.cam.indoor = !!this.world.zone?.indoor;
    this.cam.snapBehind(this.player!.yaw);
    events.emit('zone:entered', { zone: zoneId, entry });
    this.quests.refresh();
    this.world.zone?.onEnter(this.world.runtime);
    if (opts.cinematic) {
      this.input.gameplayEnabled = false;
      return;
    }
    if (opts.intro) {
      await this.cinematics.play('cin_intro');
      if (!this.gs.d.quests.m1_awakening) void this.quests.start('m1_awakening');
    } else if (!opts.respawn && entry !== '__saved') {
      void this.autosave('auto');
    }
    if (this.mode === 'play' && !this.paused) this.input.requestLock();
  }

  async changeZone(target: string, entry: string) {
    if (this.mode !== 'play' || this.world.loading) return;
    events.emit('zone:leaving', { zone: this.world.zone?.id ?? '' });
    this.audio.play('cinematic_whoosh');
    await this.ui.fade(true, 0.35);
    await this.loadZone(target, entry, {});
    await this.ui.fade(false, 0.4);
  }

  private placeHeroes(zone: Zone, entry: string) {
    const d = this.gs.d;
    let pos: THREE.Vector3, yaw: number;
    if (entry === '__saved' && d.position) {
      pos = new THREE.Vector3(...d.position);
      yaw = d.yaw;
    } else if (entry === '__checkpoint' && d.checkpoint && d.checkpoint.zone === zone.id) {
      pos = new THREE.Vector3(...d.checkpoint.pos);
      yaw = d.checkpoint.yaw;
    } else {
      const sp = zone.spawns[entry] ?? zone.spawns.start ?? Object.values(zone.spawns)[0];
      pos = sp.pos.clone();
      yaw = sp.yaw;
    }
    // Make sure the spawn is on solid ground.
    const g = this.physics.groundAt(pos.x, pos.y + 1.5, pos.z, 6);
    if (g !== null) pos.y = g + 0.02;
    for (const c of ['kael', 'lyra'] as CharacterId[]) {
      if (!this.heroes[c]) this.heroes[c] = new Hero(c, this.heroEnv, this.lookFor(c));
    }
    const active = this.player!;
    active.isPlayer = true;
    active.spawn(this.physics, pos, yaw);
    active.restore();
    zone.scene.add(active.model.root);
    const other = this.heroes[d.character === 'kael' ? 'lyra' : 'kael']!;
    other.isPlayer = false;
    other.followLeader = active;
    if (this.gs.flag('swap_unlocked')) {
      const back = pos.clone().add(new THREE.Vector3(-Math.sin(yaw) * 2 + Math.cos(yaw) * 1.2, 0, -Math.cos(yaw) * 2 - Math.sin(yaw) * 1.2));
      const gb = this.physics.groundAt(back.x, pos.y + 1.5, back.z, 4);
      other.spawn(this.physics, gb !== null && Math.abs(gb - pos.y) < 1 ? back.setY(gb + 0.02) : pos.clone(), yaw);
      other.restore();
      other.setScripted(false);
      zone.scene.add(other.model.root);
      other.model.setVisible(true);
    } else if (zone.id === 'plaza' && zone.markers.partner_wait) {
      // Before the meeting, the partner waits at the survivors' camp.
      const wp = zone.markers.partner_wait;
      other.spawn(this.physics, wp, Math.PI * 1.1);
      other.setScripted(true);
      other.playClip('npc_crossed', { hold: true });
      zone.scene.add(other.model.root);
      other.model.setVisible(true);
    } else {
      other.model.setVisible(false);
    }
    this.combat.register(active);
    this.combat.unregister(other);
  }

  /** Re-run idempotent world actions (encounters, pickups) for the current stage of every active quest. */
  private restoreStageWorldActions() {
    for (const q of this.quests.active()) {
      const st = this.gs.d.quests[q.id];
      const stage = q.stages[st.stage];
      if (!stage?.onStart) continue;
      const world = stage.onStart.filter((a) => a.do === 'encounter' || a.do === 'spawnPickup');
      if (world.length) void this.runActions(world);
    }
  }

  async respawnAtCheckpoint() {
    this.gs.d.stats.deaths++;
    const z = this.gs.d.checkpoint?.zone ?? this.gs.d.zone;
    for (const h of Object.values(this.heroes)) h?.restore();
    events.emit('player:respawned', { zone: z });
    await this.loadZone(z, '__checkpoint', { respawn: true });
  }

  // ------------------------------------------------------------------ Actions (quests/dialogue)
  async runActions(actions: Action[] | undefined, _ctx?: { quest?: string }): Promise<void> {
    if (!actions) return;
    for (const a of actions) {
      try {
        await this.runAction(a);
      } catch (e) {
        Log.error('actions', `action ${a.do} failed`, e);
      }
    }
  }

  private async runAction(a: Action) {
    switch (a.do) {
      case 'dialogue': {
        const id = a.id as string;
        const def = Data.dialogues[id];
        const interactive = !!def?.nodes.some((n) => n.choices?.length);
        await this.playDialogue(id, interactive ? 'interactive' : 'radio');
        break;
      }
      case 'cinematic':
        await this.cinematics.play(a.id as string);
        break;
      case 'encounter':
        this.gs.setFlag('enc_' + (a.id as string));
        this.world.spawnEncounter(a.id as string);
        break;
      case 'despawn':
        this.world.despawnEncounter(a.id as string);
        this.gs.markDefeated(a.id as string);
        break;
      case 'spawnPickup': {
        const id = a.id as string;
        if (this.gs.isCollected(id) || this.world.pickups.some((p) => p.id === id)) break;
        const at = this.world.zone?.markers[a.at as string] ?? this.player?.position.clone().add(new THREE.Vector3(0, 1, 2));
        if (!at) break;
        this.world.addPickup({ id, kind: a.powerup ? 'powerup' : 'quest', pos: at.clone().setY(at.y + 1), powerup: a.powerup as string | undefined, item: a.item as string | undefined, auto: !!a.powerup, hidden: false, persist: true });
        break;
      }
      case 'hint':
        this.ui.hint(a.id as string);
        break;
      case 'give': {
        const n = this.inventory.add(a.item as string, (a.qty as number) ?? 1);
        if (n > 0) this.ui.toast(`+${n} ${Data.items[a.item as string]?.name}`, 'item');
        break;
      }
      case 'take':
        this.inventory.remove(a.item as string, (a.qty as number) ?? 1);
        break;
      case 'setFlag':
        this.gs.setFlag(a.flag as string, (a.value as boolean) ?? true);
        break;
      case 'startQuest':
        void this.quests.start(a.id as string); // not awaited (queue ordering)
        this.audio.play('quest_accept');
        break;
      case 'unlock':
        this.gs.unlock(a.ability as string);
        this.ui.toast(`Ability unlocked: ${Data.abilities[a.ability as string]?.name}`, 'quest');
        break;
      case 'autosave':
        await this.autosave('checkpoint');
        break;
      case 'credits':
        await this.rollCredits();
        break;
      default:
        Log.warn('actions', 'unknown action', a.do);
    }
  }

  async playDialogue(id: string, mode: 'interactive' | 'radio' | 'cinematic') {
    const interactive = mode === 'interactive';
    if (interactive) {
      this.inDialogue = true;
      this.input.gameplayEnabled = false;
      this.player?.cancelActions();
    }
    this.ui.dialogue.mode = mode;
    this.audio.duck(true);
    try {
      await this.dialogue.play(id, interactive ? 'interactive' : 'auto');
    } finally {
      this.audio.duck(false);
      if (interactive) {
        this.inDialogue = false;
        if (this.mode === 'play' && !this.paused && !this.cinematics.active) {
          this.input.gameplayEnabled = true;
          this.input.requestLock();
        }
      }
    }
  }

  /** Move the player along points (ladder climbs, hatch drops) with an animation, then hand control back. */
  async traverse(points: THREE.Vector3[], clip: string, duration: number, endYaw?: number) {
    const p = this.player;
    if (!p || !p.body || points.length < 2) return;
    p.setScripted(true);
    p.cancelActions();
    if (clip) p.playClip(clip, { hold: true });
    const seg = duration / (points.length - 1);
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1], b = points[i];
      const t0 = performance.now();
      await new Promise<void>((resolve) => {
        const step = () => {
          const k = Math.min(1, (performance.now() - t0) / 1000 / seg);
          const pos = a.clone().lerp(b, k);
          p.body!.teleport(pos);
          p.position.copy(pos);
          if (k < 1 && this.mode === 'play') requestAnimationFrame(step);
          else resolve();
        };
        step();
      });
    }
    if (endYaw !== undefined) p.yaw = endYaw;
    p.model.animator.stopActions(0.2);
    p.lastSafe.copy(p.position);
    p.setScripted(false);
    // The companion catches up.
    const c = this.companion;
    if (c?.body) {
      c.body.teleport(p.position.clone().add(new THREE.Vector3(1, 0, 1)));
      c.position.copy(p.position).add(new THREE.Vector3(1, 0, 1));
    }
  }

  async talkTo(npc: Npc) {
    if (this.inDialogue || this.cinematics.active) return;
    const p = this.player;
    if (!p) return;
    npc.startTalk(p.position);
    p.yaw = Math.atan2(npc.position.x - p.position.x, npc.position.z - p.position.z);
    p.velocity.set(0, 0, 0);
    this.cinematics.frameConversation(p, npc);
    try {
      await this.playDialogue(npc.place.dialogue, 'interactive');
    } finally {
      npc.endTalk();
      this.cinematics.releaseFraming();
    }
  }

  // ------------------------------------------------------------------ Gameplay events
  private wireEvents() {
    events.on('quest:completed', (p) => {
      this.audio.play('quest_complete');
      this.ui.questComplete(p.id);
    });
    events.on('quest:started', () => this.audio.play('quest_accept'));
    events.on('item:added', (p) => {
      const def = Data.items[p.id];
      if (def?.category === 'upgrades') this.ui.toast(`Upgrade: ${def.name}`, 'quest');
    });
    events.on('ability:unlocked', () => this.audio.play('quest_complete'));
    events.on('lightning', (p) => {
      const delay = 0.6 + Math.random() * 2.2;
      this.audio.thunder(p.intensity, delay);
    });
    events.on('save:written', (p) => this.ui.saveIndicator(p.kind));
    events.on('save:failed', (p) => this.ui.toast('Save failed: ' + p.reason, 'warn'));
    events.on('enemy:killed', () => this.gs.d.stats.kills++);
    events.on('trigger:enter', (p) => {
      // Movement tutorial flag for M1.
      if (p.id === 't_plaza_camp' && this.gs.flag('swap_unlocked')) return;
    });
  }

  private onEnemyKilled(e: Enemy) {
    events.emit('enemy:killed', { id: e.id, type: e.def.id, tags: e.def.tags, spawnId: e.encounterId ?? undefined, zone: this.world.zone?.id ?? '' });
    this.world.onEnemyKilled(e);
    this.ui.hud.killMarker();
  }

  private onEnemyAggro(e: Enemy) {
    // Share aggro within the encounter.
    if (!e.encounterId) return;
    for (const x of this.world.enemies) if (x.encounterId === e.encounterId && x !== e && x.alive && !x.aggro) x.setAggro();
    events.emit('enemy:aggro', { id: e.id, type: e.def.id });
  }

  private onPlayerDied(_h: Hero) {
    if (this.dying) return;
    this.dying = true;
    this.cam.lockTarget = null;
    events.emit('player:died', { zone: this.world.zone?.id ?? '' });
    this.audio.setMusic('silence');
    setTimeout(() => {
      if (this.mode === 'play') {
        this.input.releaseLock();
        this.ui.showDeath();
      }
    }, 2400);
  }

  private onPickup(p: WorldPickup) {
    const def = Data.collectibles[p.id];
    if (def) {
      for (const [item, qty] of Object.entries(def.give)) this.inventory.add(item, qty, true);
      const label = def.kind === 'fragment' ? 'Aether Fragment' : def.kind === 'recording' ? Data.items[Object.keys(def.give)[0]]?.name ?? 'Recording' : 'Hidden cache';
      this.ui.toast(`${label} found`, def.kind === 'recording' ? 'lore' : 'item');
      this.audio.play(def.kind === 'recording' ? 'lore' : 'pickup', p.pos);
      events.emit('collectible:found', { id: p.id, kind: def.kind });
      if (def.kind === 'cache') for (const [item, qty] of Object.entries(def.give)) this.ui.toast(`+${qty} ${Data.items[item]?.name}`, 'item');
      if (def.kind === 'recording') {
        const lore = Object.keys(def.give)[0];
        if (Data.dialogues[lore]) void this.playDialogue(lore, 'radio');
      }
      this.player?.playClip('pickup');
      return;
    }
    if (p.powerup) {
      this.activatePowerup(p.powerup);
      return;
    }
    if (p.item) {
      const item = Data.items[p.item];
      if (item?.effect.type === 'powerup' && p.id.startsWith('drop_')) {
        this.activatePowerup(item.effect.powerup as string);
        return;
      }
      this.inventory.add(p.item, 1);
      this.ui.toast(`Picked up ${item?.name ?? p.item}`, 'item');
      this.audio.play('item', p.pos);
      this.player?.playClip('pickup');
    }
  }

  activatePowerup(id: string) {
    const def = Data.powerups[id];
    if (!def) return;
    const r = this.powerups.activate(id);
    const p = this.player;
    if (r.shieldRestore && p) p.shield = p.stats.maxShield;
    if (id === 'echo_fragment' && p) this.world.echoReveal(p.position.clone(), 30, def.duration);
    this.audio.play(def.sfx, p?.position);
    this.ui.toast(`${def.name}: ${def.description}`, 'item');
    if (p) {
      const col = new THREE.Color(def.color).getHex();
      this.vfx.shockwave(p.position, 2.4, col, 0.45);
      this.vfx.embers(p.chest(), 24, col, 0.8, 1.6);
      p.model.hitFlash(col, 0.6);
    }
  }

  usePowerupItem(itemId: string): boolean {
    const def = Data.items[itemId];
    if (!def || def.effect.type !== 'powerup') return false;
    if (!this.inventory.has(itemId)) {
      this.audio.play('error_ui');
      return false;
    }
    this.inventory.remove(itemId, 1);
    this.activatePowerup(def.effect.powerup as string);
    return true;
  }

  private dropItem(item: string, pos: THREE.Vector3) {
    const def = Data.items[item];
    if (!def) return;
    const isPu = def.effect.type === 'powerup';
    this.world.addPickup({ id: 'drop_' + Math.random().toString(36).slice(2, 8), kind: isPu ? 'powerup' : 'item', pos, item, powerup: isPu ? (def.effect.powerup as string) : undefined, auto: true, hidden: false, persist: false });
  }

  swapCharacter() {
    if (!this.gs.flag('swap_unlocked') || this.swapCd > 0) return;
    const cur = this.player, next = this.companion;
    if (!cur || !next || !cur.alive) return;
    if (cur.state !== 'move' && cur.state !== 'aim') return;
    this.swapCd = 1.2;
    cur.cancelActions();
    const nextChar = next.character;
    this.gs.d.character = nextChar;
    cur.setRole(false, this.physics);
    cur.followLeader = next;
    next.setRole(true, this.physics);
    next.followLeader = null;
    next.lockTarget = cur.lockTarget;
    this.combat.unregister(cur);
    this.combat.register(next);
    this.cam.snapBehind(this.cam.heading);
    for (const h of [cur, next]) {
      this.vfx.flash(h.chest(), 2.2, h.character === 'kael' ? 0x5fb8ff : 0xa47dff, 0.25);
      this.vfx.embers(h.chest(), 16, h.character === 'kael' ? 0x5fb8ff : 0xa47dff, 0.8, 1);
    }
    this.audio.play('step', next.position);
    events.emit('character:swapped', { character: nextChar });
    this.ui.hud.characterChanged();
  }

  // ------------------------------------------------------------------ Save
  async autosave(kind: SaveKind) {
    if (this.mode !== 'play' && this.mode !== 'loading') return;
    if (this.dying || !this.player?.alive) return;
    this.capturePosition();
    await this.saves.write(this.saves.activeSlot, kind, this.gs.d, this.settings.data, this.thumbnail());
  }

  /** Manual save is only allowed when safe (not in combat, cinematic or mid-air). */
  canSaveNow(): { ok: boolean; reason?: string } {
    if (this.mode !== 'play') return { ok: false, reason: 'Not in game' };
    if (this.inCombat) return { ok: false, reason: 'Cannot save during combat' };
    if (this.cinematics.active) return { ok: false, reason: 'Cannot save during a cinematic' };
    if (this.dying || !this.player?.alive) return { ok: false, reason: 'Cannot save now' };
    if (this.player && !this.player.body?.grounded) return { ok: false, reason: 'Cannot save while airborne' };
    return { ok: true };
  }

  async manualSave(slot: number): Promise<boolean> {
    const c = this.canSaveNow();
    if (!c.ok) {
      this.ui.toast(c.reason!, 'warn');
      return false;
    }
    this.capturePosition();
    this.saves.activeSlot = slot;
    const ok = await this.saves.write(slot, 'manual', this.gs.d, this.settings.data, this.thumbnail());
    if (ok) this.audio.play('save');
    return ok;
  }

  private capturePosition() {
    const p = this.player;
    if (!p) return;
    this.gs.d.position = [p.position.x, p.position.y, p.position.z];
    this.gs.d.yaw = p.yaw;
  }

  private thumbnail(): string {
    try {
      return this.rs.snapshot(240, 0.6);
    } catch {
      return '';
    }
  }

  // ------------------------------------------------------------------ Credits
  async rollCredits() {
    this.mode = 'credits';
    this.input.gameplayEnabled = false;
    this.input.releaseLock();
    this.audio.setMusic('ending');
    await this.saves.write(this.saves.activeSlot, 'checkpoint', this.gs.d, this.settings.data, this.thumbnail());
    await this.ui.showCredits();
    this.showMenu();
  }

  // ------------------------------------------------------------------ Feedback helpers
  hitstop(sec: number) {
    this.hitstopT = Math.max(this.hitstopT, sec);
  }
  shake(a: number) {
    this.cam.addTrauma(a);
  }
  private cameraSees(p: THREE.Vector3): boolean {
    const cam = this.rs.camera;
    const v = p.clone().project(cam);
    return Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1 && v.z < 1 && cam.position.distanceTo(p) < 60;
  }

  // ------------------------------------------------------------------ Settings
  applySettings() {
    const s = this.settings.data;
    this.rs.applyOptions(s.graphics);
    this.input.bindings = s.controls.bindings;
    this.input.sensitivity = s.gameplay.cameraSensitivity;
    this.input.aimSensitivity = s.gameplay.aimSensitivity;
    this.input.invertY = s.gameplay.invertY;
    this.input.padLookSpeed = s.controls.padLookSpeed;
    this.audio.setVolumes({ master: s.audio.master, music: s.audio.music, sfx: s.audio.sfx, voice: s.audio.voice, ambience: s.audio.ambience, ui: s.audio.ui });
    // Spoken dialogue is switched off for this build; lines are subtitle-only.
    this.voice.enabled = false;
    this.voice.volume = s.audio.voice * s.audio.master;
    this.cam.shakeScale = this.settings.shakeScale;
    this.vfx.quality = s.graphics.effects;
    this.world.maxTokens = s.gameplay.difficulty === 'story' ? 1 : s.gameplay.difficulty === 'hard' ? 3 : 2;
    if (this.world.zone?.weather) this.world.zone.weather.flashScale = s.accessibility.flashIntensity;
    this.ui.applySettings(s);
    const fs = !!document.fullscreenElement;
    if (s.graphics.fullscreen && !fs) document.documentElement.requestFullscreen?.().catch(() => undefined);
    else if (!s.graphics.fullscreen && fs) document.exitFullscreen?.().catch(() => undefined);
    this.vfx.setViewportHeight(window.innerHeight * this.rs.pixelRatio());
  }

  // ------------------------------------------------------------------ Music
  private updateMusic(force = false) {
    const z = this.world.zone;
    if (!z || this.mode !== 'play') return;
    let mood: MusicMood = (z.music as MusicMood) ?? 'explore';
    if (this.bossActive) mood = 'boss';
    else if (this.inCombat) mood = 'combat';
    else if (this.quests.tracked()?.type === 'side' && z.id === 'rooftops') mood = 'sidequest';
    if (this.dying) mood = 'silence';
    if (force || this.audio.stats.mood !== mood) this.audio.setMusic(mood);
  }

  setBoss(active: boolean) {
    this.bossActive = active;
    this.updateMusic();
  }

  // ------------------------------------------------------------------ Loop
  private loop = (now: number) => {
    requestAnimationFrame(this.loop);
    let dtReal = (now - this.lastFrame) / 1000;
    // Frame limiter (30 FPS option)
    if (this.settings.data.graphics.frameLimit === '30') {
      this.frameAcc += dtReal;
      this.lastFrame = now;
      if (this.frameAcc < 1 / 30 - 0.002) return;
      dtReal = this.frameAcc;
      this.frameAcc = 0;
    } else this.lastFrame = now;
    dtReal = Math.min(dtReal, 0.1);
    this.fpsAcc += dtReal;
    this.fpsFrames++;
    if (this.fpsAcc >= 0.5) {
      this.fps = this.fpsFrames / this.fpsAcc;
      this.frameMs = (this.fpsAcc / this.fpsFrames) * 1000;
      this.fpsAcc = 0;
      this.fpsFrames = 0;
    }
    const dt = Math.min(dtReal, 1 / 20);
    this.time += dt;
    this.input.update(dt);
    if (this.input.uiPressed('debug') && __DEV_TOOLS__) {
      this.debugVisible = !this.debugVisible;
      this.ui.setDebug(this.debugVisible);
    }
    try {
      this.frame(dt);
    } catch (err) {
      Log.error('loop', err);
    }
    this.ui.update(dt);
    this.audio.update();
  };

  private frame(dt: number) {
    if (this.mode === 'menu' || this.mode === 'charselect' || this.mode === 'credits') {
      this.menu?.update(dt);
      this.rs.render(this.time);
      return;
    }
    if (this.mode === 'loading') {
      return;
    }
    // ---- Play mode
    const z = this.world.zone;
    if (!z) return;
    const p = this.player;
    // Pause toggling and panels
    if (!this.cinematics.active && !this.dying) {
      if (this.input.uiPressed('pause') && !this.ui.consumedBack()) {
        if (this.paused) this.ui.closeOverlays();
        else if (!this.inDialogue) this.ui.openPause();
      }
      if (!this.inDialogue && !this.paused) {
        if (this.input.uiPressed('inventory')) this.ui.openPanel('inventory');
        else if (this.input.uiPressed('map')) this.ui.openPanel('map');
        else if (this.input.uiPressed('journal')) this.ui.openPanel('journal');
        else if (this.input.uiPressed('skills')) this.ui.openPanel('skills');
      }
    }
    const gameplay = !this.paused && !this.inDialogue;
    this.input.gameplayEnabled = gameplay && !this.cinematics.active && !this.dying;
    if (this.paused) {
      // Keep rendering the frozen frame behind menus (or the designer stage).
      if (this.designerActive) this.menu?.update(dt);
      this.rs.render(this.time);
      return;
    }
    // Hit-stop / time scale
    if (this.hitstopT > 0) {
      this.hitstopT -= dt;
      this.timeScale = 0.06;
    } else this.timeScale += (1 - this.timeScale) * Math.min(1, dt * 20);
    const gdt = dt * this.timeScale;
    this.gs.d.stats.playtime += dt;
    this.swapCd = Math.max(0, this.swapCd - dt);
    this.powerups.update(gdt);
    // Input-driven game actions
    if (this.input.gameplayEnabled && p && p.alive) {
      if (this.input.pressed('interact')) {
        if (this.world.interact()) this.audio.play('interact');
      }
      if (this.input.pressed('swap')) this.swapCharacter();
      for (const [k, item] of Object.entries(QUICK)) if (this.input.pressed(k as InputAction)) this.usePowerupItem(item);
      if (!this.input.locked && this.input.lastDevice === 'kbm' && (this.input.pressed('light') || this.input.pressed('heavy'))) this.input.requestLock();
      if (distXZ(p.position, p.lastSafe) > 4 && !this.gs.flag('tut_moved')) this.gs.setFlag('tut_moved');
    }
    // Actors
    for (const h of Object.values(this.heroes)) if (h && h.model.root.visible) h.update(gdt);
    this.world.update(gdt, p?.position ?? null, this.input.gameplayEnabled, this.powerups.buffs().reveal);
    this.combat.update(gdt);
    this.vfx.update(gdt);
    this.cinematics.update(dt);
    // Combat state & music
    if (p) {
      const aggro = this.world.aggroCount(p.position);
      const was = this.inCombat;
      if (aggro > 0) {
        this.inCombat = true;
        this.combatT = 4;
      } else {
        this.combatT -= dt;
        if (this.combatT <= 0) this.inCombat = false;
      }
      if (was !== this.inCombat) {
        events.emit('combat:state', { inCombat: this.inCombat });
        this.updateMusic();
      }
      this.cam.combatZoom = this.inCombat ? 0.6 : 0;
    }
    // Camera
    if (p) {
      this.cam.update(dt, this.input.look, p.position, this.physics);
      this.rs.updateShadowFocus(p.position);
      const cp = this.rs.camera.position;
      this.fill.position.set(cp.x * 0.6 + p.position.x * 0.4, p.position.y + 2.2, cp.z * 0.6 + p.position.z * 0.4);
    }
    const camDir = this.rs.camera.getWorldDirection(new THREE.Vector3());
    this.audio.setListener(this.rs.camera.position, camDir, this.rs.camera.up);
    this.physics.step(gdt);
    // Post effects
    const hp = p ? p.health / p.stats.maxHealth : 1;
    const flashScale = this.settings.data.accessibility.flashIntensity;
    this.rs.setPost({
      damage: clamp(this.ui.hud.damageAmount() + (hp < 0.3 ? (0.3 - hp) * 1.2 : 0), 0, 0.9),
      echo: this.world.echoActive ? Math.min(1, this.world.echoT * 2) * 0.85 : 0,
      flash: (z.weather?.flash ?? 0) * 0.35 * flashScale,
    });
    this.rs.render(this.time);
  }

  disposeHeroes() {
    for (const h of Object.values(this.heroes)) h?.dispose();
    this.heroes = {};
  }

  /** Character the player last selected (for menu staging). */
  get selectedCharacter() {
    return this.lastChar;
  }
}
