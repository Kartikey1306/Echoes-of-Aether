import * as THREE from 'three';
import { easeInOutCubic, clamp } from '../core/MathUtil';
import { events } from '../core/Events';
import { Log } from '../core/Log';
import type { Hero } from '../actors/Hero';
import type { Npc } from '../actors/Npc';
import type { Game } from './Game';
import type { MusicMood } from '../audio/AudioEngine';
import { HumanModel } from '../actors/human/HumanModel';
import { MAREN } from '../actors/human/Looks';

// Cinematic runner: camera shots, actor staging, subtitled/voiced lines, letterbox, hold-to-skip.

export class SkipSignal extends Error {}

export interface CineCtx {
  g: Game;
  /** Move the camera from (posA, lookA) to (posB, lookB) over `dur` seconds. */
  shot(posA: THREE.Vector3, lookA: THREE.Vector3, posB: THREE.Vector3, lookB: THREE.Vector3, dur: number, fov?: number): Promise<void>;
  /** Hold the camera while a promise runs (e.g. dialogue lines). */
  cut(pos: THREE.Vector3, look: THREE.Vector3, fov?: number): void;
  drift(posB: THREE.Vector3, lookB: THREE.Vector3, dur: number): void;
  wait(sec: number): Promise<void>;
  /** Play specific nodes (or all) of a dialogue as cinematic subtitles+voice. */
  lines(dialogueId: string, from?: string, to?: string): Promise<void>;
  fade(toBlack: boolean, sec: number): Promise<void>;
  music(m: MusicMood): void;
  sfx(id: string, pos?: THREE.Vector3): void;
  skipped(): boolean;
}

type Script = (c: CineCtx) => Promise<void>;
type Finalize = (g: Game) => void;

const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

export class Cinematics {
  active: string | null = null;
  private skipFlag = false;
  private skipHold = 0;
  private camFrom = { pos: new THREE.Vector3(), look: new THREE.Vector3() };
  private camTo = { pos: new THREE.Vector3(), look: new THREE.Vector3() };
  private camT = 0;
  private camDur = 0;
  private fov = 50;
  private framing: { pos: THREE.Vector3; look: THREE.Vector3 } | null = null;
  private scripts: Record<string, { script: Script; finalize?: Finalize }> = {};

  constructor(private g: Game) {
    this.register('cin_intro', introScript, introFinalize);
    this.register('cin_meeting', meetingScript, meetingFinalize);
    this.register('cin_guardian_reveal', guardianScript, guardianFinalize);
    this.register('cin_ending', endingScript, endingFinalize);
    this.register('cin_hidden_vault', hiddenVaultScript);
  }

  register(id: string, script: Script, finalize?: Finalize) {
    this.scripts[id] = { script, finalize };
  }

  has(id: string) {
    return !!this.scripts[id];
  }

  stop() {
    if (this.active) this.skipFlag = true;
    this.g.cam.cinematic = null;
    this.g.ui.cinematicBars(false);
  }

  async play(id: string): Promise<void> {
    const entry = this.scripts[id];
    if (!entry) {
      Log.warn('cine', 'no script for', id, '- playing its lines only');
      const lines = id + '_lines';
      if (this.g.dialogue && (await import('./Data')).Data.dialogues[lines]) await this.g.playDialogue(lines, 'cinematic');
      return;
    }
    if (this.active) return;
    this.active = id;
    this.skipFlag = false;
    this.skipHold = 0;
    events.emit('cinematic:started', { id });
    const g = this.g;
    g.input.gameplayEnabled = false;
    g.input.releaseLock();
    g.player?.setScripted(true);
    g.ui.cinematicBars(true);
    g.ui.dialogue.mode = 'cinematic';
    g.audio.duck(true);
    this.camFrom.pos.copy(g.rs.camera.position);
    this.camFrom.look.copy(g.rs.camera.position).add(g.rs.camera.getWorldDirection(new THREE.Vector3()));
    this.camTo.pos.copy(this.camFrom.pos);
    this.camTo.look.copy(this.camFrom.look);
    this.camT = 1;
    this.camDur = 1;
    g.world.freezeEnemies = true;
    const ctx = this.makeCtx();
    let skipped = false;
    try {
      await entry.script(ctx);
    } catch (e) {
      if (e instanceof SkipSignal) skipped = true;
      else Log.error('cine', id, e);
    }
    skipped = skipped || this.skipFlag;
    g.voice.stop();
    g.world.freezeEnemies = false;
    this.g.dialogue.cancel();
    try {
      entry.finalize?.(g);
    } catch (e) {
      Log.error('cine', 'finalize failed', e);
    }
    g.ui.fadeInstant(false);
    g.ui.cinematicBars(false);
    g.audio.duck(false);
    g.cam.cinematic = null;
    if (g.player) {
      g.player.setScripted(false);
      g.cam.snapBehind(g.player.yaw);
    }
    this.active = null;
    events.emit('cinematic:ended', { id, skipped });
    if (g.mode === 'play' && !g.paused) {
      g.input.gameplayEnabled = true;
      g.input.requestLock();
    }
  }

  private makeCtx(): CineCtx {
    const self = this;
    const g = this.g;
    const guard = () => {
      if (self.skipFlag) throw new SkipSignal();
    };
    const until = (cond: () => boolean) =>
      new Promise<void>((resolve, reject) => {
        const tick = () => {
          if (self.skipFlag) return reject(new SkipSignal());
          if (cond()) return resolve();
          requestAnimationFrame(tick);
        };
        tick();
      });
    // Resolves with the promise, or rejects with SkipSignal as soon as a skip is requested.
    const skipRace = (pr: Promise<unknown>) =>
      new Promise<void>((resolve, reject) => {
        let done = false;
        pr.then(() => { done = true; resolve(); }, () => { done = true; resolve(); });
        const tick = () => {
          if (done) return;
          if (self.skipFlag) {
            done = true;
            reject(new SkipSignal());
            return;
          }
          requestAnimationFrame(tick);
        };
        tick();
      });
    return {
      g,
      shot: async (pa, la, pb, lb, dur, fov) => {
        guard();
        self.camFrom.pos.copy(pa);
        self.camFrom.look.copy(la);
        self.camTo.pos.copy(pb);
        self.camTo.look.copy(lb);
        self.camT = 0;
        self.camDur = dur;
        if (fov) self.fov = fov;
        await until(() => self.camT >= self.camDur);
      },
      cut: (p, l, fov) => {
        self.camFrom.pos.copy(p);
        self.camFrom.look.copy(l);
        self.camTo.pos.copy(p);
        self.camTo.look.copy(l);
        self.camT = 1;
        self.camDur = 1;
        if (fov) self.fov = fov;
      },
      drift: (pb, lb, dur) => {
        self.camFrom.pos.copy(g.rs.camera.position);
        self.camFrom.look.copy(self.camTo.look);
        self.camTo.pos.copy(pb);
        self.camTo.look.copy(lb);
        self.camT = 0;
        self.camDur = dur;
      },
      wait: async (sec) => {
        guard();
        const end = performance.now() + sec * 1000;
        await until(() => performance.now() >= end);
      },
      lines: async (id, from, to) => {
        guard();
        const all = g.dialogue.linearLines(id);
        let started = !from;
        for (const l of all) {
          if (!started && l.node === from) started = true;
          if (!started) continue;
          guard();
          await skipRace(g.ui.dialogue.line(l, 'auto'));
          guard();
          if (to && l.node === to) break;
        }
        g.ui.dialogue.end();
      },
      fade: async (toBlack, sec) => {
        guard();
        await g.ui.fade(toBlack, sec);
      },
      music: (m) => g.audio.setMusic(m),
      sfx: (id, pos) => g.audio.play(id, pos),
      skipped: () => self.skipFlag,
    };
  }

  /** Over-the-shoulder framing for conversations. */
  frameConversation(p: Hero, npc: Npc) {
    const a = p.position.clone().setY(p.position.y + 1.6);
    const b = npc.position.clone().setY(npc.position.y + (npc.id === 'nia' ? 1.1 : 1.55));
    const dir = b.clone().sub(a).setY(0).normalize();
    const side = new THREE.Vector3(dir.z, 0, -dir.x);
    const pos = a.clone().addScaledVector(dir, -1.6).addScaledVector(side, 0.9).setY(a.y + 0.15);
    this.framing = { pos, look: b.clone().lerp(a, 0.25) };
    this.g.cam.cinematic = { pos: pos.clone(), look: this.framing.look.clone(), fov: 42 };
  }

  releaseFraming() {
    this.framing = null;
    if (!this.active) this.g.cam.cinematic = null;
  }

  update(dt: number) {
    if (this.framing && !this.active) {
      const c = this.g.cam.cinematic;
      if (c) {
        c.pos.lerp(this.framing.pos, 1 - Math.exp(-4 * dt));
        c.look.lerp(this.framing.look, 1 - Math.exp(-4 * dt));
      }
    }
    if (!this.active) return;
    // Hold to skip (or press once if hold-to-skip is disabled in accessibility).
    const hold = this.g.settings.data.accessibility.holdToSkip;
    const inp = this.g.input;
    const pressing = inp.codeHeld('Space') || inp.codeHeld('Enter') || inp.codeHeld('Escape') || inp.codeHeld('B0') || inp.codeHeld('B9');
    if (pressing) this.skipHold += dt;
    else this.skipHold = Math.max(0, this.skipHold - dt * 2);
    const need = hold ? 1.0 : 0.05;
    this.g.ui.skipPrompt(clamp(this.skipHold / need, 0, 1), pressing || this.skipHold > 0);
    if (this.skipHold >= need && !this.skipFlag) {
      this.skipFlag = true;
      this.g.voice.stop();
      this.g.ui.dialogue.forceAdvance();
    }
    this.camT = Math.min(this.camDur, this.camT + dt);
    const k = easeInOutCubic(this.camDur > 0 ? this.camT / this.camDur : 1);
    const pos = this.camFrom.pos.clone().lerp(this.camTo.pos, k);
    const look = this.camFrom.look.clone().lerp(this.camTo.look, k);
    this.g.cam.cinematic = { pos, look, fov: this.fov };
  }
}

// ---------------------------------------------------------------------------- Intro (~90 s)

async function introScript(c: CineCtx) {
  const g = c.g;
  const p = g.player!;
  const partner = g.heroes[p.character === 'kael' ? 'lyra' : 'kael'];
  await g.ui.fade(true, 0.01);
  c.music('menu');
  p.playClip('lie', { hold: true });
  c.cut(v(-60, 42, 70), v(0, 6, 0), 50);
  await c.fade(false, 2.5);
  // Aerial push over the district toward the monument.
  void c.shot(v(-60, 42, 70), v(0, 6, 0), v(-30, 26, 36), v(0, 8, 0), 14, 50);
  await c.lines('cin_intro_lines', 'n1', 'n1');
  await c.wait(1.5);
  // Street-level glide past abandoned cars on the ring road.
  void c.shot(v(-38, 1.6, 40), v(-38, 1.4, 0), v(-36, 1.9, 4), v(-20, 2.5, -20), 13, 55);
  await c.lines('cin_intro_lines', 'n2', 'n2');
  await c.wait(2);
  // Rise up the monument to the core.
  void c.shot(v(8, 1.2, 10), v(0, 3.5, 0), v(5.5, 8.6, 6.5), v(0, 7.45, 0), 12, 45);
  await c.lines('cin_intro_lines', 'n3', 'n3');
  await c.wait(1);
  g.world.zone?.weather?.triggerLightning(1);
  g.shake(0.4);
  c.sfx('pulse', v(0, 7.45, 0));
  await c.lines('cin_intro_lines', 'n4', 'n4');
  await c.wait(2);
  await c.fade(true, 1.2);
  // The protagonist lying in the rain beside the monument.
  const pp = p.position.clone();
  c.cut(pp.clone().add(v(2.4, 0.6, 1.4)), pp.clone().add(v(0, 0.3, 0)), 40);
  await c.fade(false, 1.5);
  c.drift(pp.clone().add(v(1.6, 0.9, 0.9)), pp.clone().add(v(0, 0.3, 0)), 10);
  await c.lines('cin_intro_lines', 'n5', 'n5');
  // Partner far away at the camp.
  if (partner && partner.model.root.visible) {
    const pt = partner.position.clone();
    c.cut(pt.clone().add(v(-2.5, 1.7, 3.2)), pt.clone().add(v(0, 1.4, 0)), 40);
  }
  await c.lines('cin_intro_lines', 'n6', 'n6');
  c.cut(pp.clone().add(v(1.8, 1.0, 2.2)), pp.clone().add(v(0, 0.6, 0)), 42);
  p.playClip('wake');
  await c.lines('cin_intro_lines', 'n7', 'n7');
  await c.lines('cin_intro_lines', 'n8', 'n8');
  void c.shot(pp.clone().add(v(1.8, 1.0, 2.2)), pp.clone().add(v(0, 0.8, 0)), pp.clone().add(v(-1.2, 1.9, 3.4)), pp.clone().add(v(0, 1.5, -6)), 4, 50);
  await c.lines('cin_intro_lines', 'n9', 'n9');
  await c.wait(1.5);
}

function introFinalize(g: Game) {
  const p = g.player;
  if (!p) return;
  p.model.animator.stopActions(0.3);
  p.model.animator.setState(null, 0.2);
  g.audio.setMusic('explore');
}

// ---------------------------------------------------------------------------- Meeting (~45 s)

async function meetingScript(c: CineCtx) {
  const g = c.g;
  const p = g.player!;
  const partner = g.heroes[p.character === 'kael' ? 'lyra' : 'kael']!;
  const oren = g.world.findNpc('oren');
  const camp = g.world.zone?.markers.fire ?? p.position.clone();
  await c.fade(true, 0.6);
  // Stage: player stands near the fire, partner turns to them.
  const meetA = camp.clone().add(v(-3.2, 0, 1.6)).setY(p.position.y);
  const meetB = camp.clone().add(v(-1.6, 0, 0.2)).setY(partner.position.y);
  p.body?.teleport(meetA);
  p.position.copy(meetA);
  p.yaw = Math.atan2(meetB.x - meetA.x, meetB.z - meetA.z);
  partner.model.animator.stopActions(0.2);
  partner.body?.teleport(meetB);
  partner.position.copy(meetB);
  partner.yaw = Math.atan2(meetA.x - meetB.x, meetA.z - meetB.z);
  partner.setScripted(true);
  const mid = meetA.clone().lerp(meetB, 0.5).setY(meetA.y + 1.55);
  const side = new THREE.Vector3(meetB.z - meetA.z, 0, -(meetB.x - meetA.x)).normalize();
  c.cut(mid.clone().addScaledVector(side, 3.4).setY(mid.y + 0.2), mid, 42);
  await c.fade(false, 1);
  c.music('sidequest');
  // Shot / reverse shot between the two protagonists.
  const overP = meetA.clone().add(meetA.clone().sub(meetB).setY(0).normalize().multiplyScalar(1.3)).addScaledVector(side, 0.6).setY(meetA.y + 1.7);
  const overQ = meetB.clone().add(meetB.clone().sub(meetA).setY(0).normalize().multiplyScalar(1.3)).addScaledVector(side, -0.6).setY(meetB.y + 1.7);
  const chest = (h: Hero) => h.position.clone().setY(h.position.y + 1.55);
  const char = p.character;
  const first = char === 'kael' ? ['k1', 'k4'] : ['l1', 'l3'];
  c.cut(overP, chest(partner), 38);
  partner.playClip('talk');
  await c.lines('cin_meeting_lines', first[0], first[0]);
  c.cut(overQ, chest(p), 38);
  p.playClip('talk');
  await c.lines('cin_meeting_lines', char === 'kael' ? 'k2' : 'l2', char === 'kael' ? 'k2' : 'l2');
  c.cut(overP, chest(partner), 38);
  await c.lines('cin_meeting_lines', char === 'kael' ? 'k3' : 'l3', first[1]);
  // Oren joins.
  if (oren) {
    oren.startTalk(mid);
    c.cut(mid.clone().addScaledVector(side, -2.6).setY(mid.y + 0.3), oren.position.clone().setY(oren.position.y + 1.5), 40);
  }
  await c.lines('cin_meeting_lines', 'c1', 'c1');
  c.cut(overQ, chest(partner).lerp(chest(p), 0.5), 44);
  await c.lines('cin_meeting_lines', 'c2', 'c2');
  if (oren) c.cut(mid.clone().addScaledVector(side, -2.6).setY(mid.y + 0.3), oren.position.clone().setY(oren.position.y + 1.5), 40);
  await c.lines('cin_meeting_lines', 'c3', 'c3');
  c.cut(overQ, chest(p), 38);
  await c.lines('cin_meeting_lines', 'c4', 'c4');
  if (oren) c.cut(mid.clone().addScaledVector(side, -2.6).setY(mid.y + 0.3), oren.position.clone().setY(oren.position.y + 1.5), 40);
  await c.lines('cin_meeting_lines', 'c5', 'c5');
  // Wide shot: the two of them look toward the metro entrance.
  const metro = new THREE.Vector3(-27, 1, 11);
  c.drift(mid.clone().addScaledVector(side, 4.5).setY(mid.y + 1.2), metro, 6);
  await c.lines('cin_meeting_lines', 'c6', 'c6');
  await c.wait(2.5);
  oren?.endTalk();
}

function meetingFinalize(g: Game) {
  const p = g.player;
  const partner = p ? g.heroes[p.character === 'kael' ? 'lyra' : 'kael'] : null;
  g.gs.setFlag('swap_unlocked');
  if (p && partner) {
    partner.model.animator.stopActions(0.2);
    partner.model.animator.setState(null, 0.3);
    partner.setScripted(false);
    partner.followLeader = p;
    partner.setRole(false, g.physics);
  }
  g.world.findNpc('oren')?.endTalk();
}

// ---------------------------------------------------------------------------- Guardian reveal (~30 s)

async function guardianScript(c: CineCtx) {
  const g = c.g;
  const p = g.player!;
  const guardian = g.world.enemies.find((e) => e.def.id === 'guardian');
  const rise = g.world.zone?.markers.guardian_rise ?? new THREE.Vector3(0, 0, 78);
  if (guardian) {
    guardian.visualOffsetY = -6;
    guardian.yaw = Math.atan2(p.position.x - rise.x, p.position.z - rise.z);
  }
  c.music('boss');
  c.sfx('door', rise);
  g.shake(0.3);
  const pp = p.position.clone();
  c.cut(pp.clone().add(v(2.2, 1.7, 2.5)), rise.clone().add(v(0, 1.5, 0)), 45);
  await c.lines('cin_guardian_lines', 'n1', 'n1');
  // The Guardian rises out of the containment pit.
  const t0 = performance.now();
  const lift = () => {
    if (!guardian) return;
    const k = Math.min(1, (performance.now() - t0) / 4500);
    guardian.visualOffsetY = -6 * (1 - k * (2 - k));
    if (k < 1 && g.cinematics.active) requestAnimationFrame(lift);
  };
  lift();
  void c.shot(rise.clone().add(v(-5, 1.2, 9)), rise.clone().add(v(0, 3, 0)), rise.clone().add(v(-3.5, 2.2, 7)), rise.clone().add(v(0, 4.4, 0)), 5, 40);
  for (let i = 0; i < 4; i++) {
    g.vfx.sparks(rise.clone().add(v((Math.random() - 0.5) * 5, 0.3, (Math.random() - 0.5) * 5)), v(0, 1, 0), 24, 0xff8a5a, 7);
    g.shake(0.25);
    await c.wait(0.9);
  }
  await c.lines('cin_guardian_lines', 'n2', 'n2');
  c.cut(rise.clone().add(v(1.5, 2.2, 5.5)), rise.clone().add(v(0, 4.3, 0)), 34);
  if (guardian) (guardian as unknown as { model: { animator: { play: (c: unknown, o: unknown) => void }; anims: unknown } }).model.animator.play((await import('../actors/enemies/EnemyAnims')).robotClips('guardian').roar, { fadeIn: 0.2 });
  g.shake(0.6);
  await c.lines('cin_guardian_lines', 'n3', 'n3');
  c.cut(pp.clone().add(v(-1.2, 1.8, -2.2)), pp.clone().add(v(0, 1.6, 0)), 40);
  await c.lines('cin_guardian_lines', 'n4', 'n5');
}

function guardianFinalize(g: Game) {
  const guardian = g.world.enemies.find((e) => e.def.id === 'guardian');
  if (guardian) guardian.visualOffsetY = 0;
  g.setBoss(true);
}

// ---------------------------------------------------------------------------- Echo helper

function spawnEcho(g: Game, pos: THREE.Vector3, yaw: number): HumanModel {
  const m = new HumanModel(MAREN, { lods: 1, faceSize: 256 });
  const mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(0x8fc8ff).multiplyScalar(0.7), transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
  for (const mesh of m.meshes) {
    mesh.material = mat;
    mesh.castShadow = false;
  }
  m.root.position.copy(pos);
  m.root.rotation.y = yaw;
  g.world.zone?.scene.add(m.root);
  const t0 = performance.now();
  const fade = () => {
    const k = Math.min(1, (performance.now() - t0) / 1500);
    mat.opacity = 0.65 * k;
    m.update(1 / 60);
    if (m.root.parent) requestAnimationFrame(fade);
  };
  fade();
  g.vfx.embers(pos.clone().setY(pos.y + 1), 40, 0x8fd8ff, 1.2, 1.2);
  return m;
}

// ---------------------------------------------------------------------------- Hidden Vault (~25 s)

async function hiddenVaultScript(c: CineCtx) {
  const g = c.g;
  const relic = g.world.zone?.markers.relic ?? g.player!.position.clone();
  const p = g.player!;
  const echoPos = relic.clone().add(v(1.4, -1.65, 1.2));
  const echo = spawnEcho(g, echoPos, Math.atan2(p.position.x - echoPos.x, p.position.z - echoPos.z));
  try {
    c.cut(p.position.clone().add(v(-1.2, 1.8, -1.6)), echoPos.clone().add(v(0, 1.5, 0)), 38);
    c.sfx('reveal', echoPos);
    await c.wait(1.2);
    await c.lines('cin_hidden_vault_lines', 'n1', 'n1');
    c.cut(echoPos.clone().add(v(1.4, 1.6, 1.8)), echoPos.clone().add(v(0, 1.5, 0)), 32);
    await c.lines('cin_hidden_vault_lines', 'n2', 'n2');
    c.cut(p.position.clone().add(v(1.5, 1.7, 1.2)), p.position.clone().add(v(0, 1.5, 0)), 36);
    await c.lines('cin_hidden_vault_lines', 'n3', 'n3');
    await c.wait(1);
  } finally {
    g.vfx.embers(echoPos.clone().setY(echoPos.y + 1), 50, 0x8fd8ff, 1.2, 2);
    echo.dispose();
  }
}

// ---------------------------------------------------------------------------- Ending (~90 s)

async function endingScript(c: CineCtx) {
  const g = c.g;
  const p = g.player!;
  const zone = g.world.zone as unknown as { released?: boolean; markers: Record<string, THREE.Vector3> };
  const heart = zone.markers.heart ?? v(0, 1.25, 0);
  const core = zone.markers.core ?? v(0, 15, 0);
  c.music('ending');
  const echo = spawnEcho(g, heart.clone().add(v(0, -1.2, -1.5)), Math.PI * 0 + 0);
  let echoAlive = true;
  try {
    c.cut(heart.clone().add(v(4.5, 2.2, 6)), heart.clone().add(v(0, 1.4, -1)), 38);
    await c.wait(1);
    await c.lines('cin_ending_lines', 'n1', 'n1');
    c.cut(p.position.clone().add(v(1.4, 1.8, 2)), p.position.clone().add(v(0, 1.5, -1)), 36);
    await c.lines('cin_ending_lines', 'n2', 'n2');
    await c.lines('cin_ending_lines', 'n3', 'n3');
    // Release: the Core flares and the echoes rise.
    zone.released = true;
    echo.dispose();
    echoAlive = false;
    g.vfx.addEmitter(core.clone().setY(2), 'aether', 120, 6);
    for (let i = 0; i < 6; i++) g.vfx.addEmitter(v(Math.sin(i) * 12, 0.5, Math.cos(i) * 12), 'aether', 30, 8);
    g.shake(0.4);
    c.sfx('ult_impact', core);
    void c.shot(heart.clone().add(v(10, 3, 16)), core.clone().add(v(0, -6, 0)), v(3, 24, 14), core.clone().add(v(0, 10, 0)), 9, 50);
    await c.wait(3);
    g.rs.setPost({ flash: 0.6 });
    await c.wait(4);
    await c.fade(true, 1.8);
  } finally {
    if (echoAlive) echo.dispose();
  }
  // Dawn over Aether-9.
  await g.loadZone('plaza', 'camp', { cinematic: true });
  g.input.gameplayEnabled = false;
  const pz = g.player!;
  pz.setScripted(true);
  c.cut(v(-26, 14, 30), v(0, 6, 0), 50);
  await c.fade(false, 2.5);
  void c.shot(v(-26, 14, 30), v(0, 6, 0), v(-14, 8, 22), v(0, 8, -10), 16, 48);
  await c.lines('cin_ending_lines', 'n4', 'n4');
  await c.lines('cin_ending_lines', 'n5', 'n5');
  const camp = g.world.zone?.markers.fire ?? v(22, 1, -22);
  c.cut(camp.clone().add(v(-6, 2.2, 7)), camp.clone().add(v(0, 1.6, 0)), 40);
  await c.wait(3.5);
  const hp = pz.position.clone();
  c.cut(hp.clone().add(v(2.2, 1.7, 3.2)), hp.clone().add(v(0, 1.5, 0)), 36);
  await c.lines('cin_ending_lines', 'n6', 'n6');
  await c.lines('cin_ending_lines', 'n7', 'n7');
  void c.shot(hp.clone().add(v(2.2, 1.7, 3.2)), hp.clone().add(v(0, 1.5, 0)), hp.clone().add(v(6, 10, 14)), v(0, 12, -40), 6, 50);
  await c.wait(5);
  await c.fade(true, 2.5);
}

function endingFinalize(g: Game) {
  g.rs.setPost({ flash: 0 });
}
