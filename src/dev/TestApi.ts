import * as THREE from 'three';
import type { Game } from '../game/Game';
import { Data } from '../game/Data';
import { Log } from '../core/Log';
import { events } from '../core/Events';

// Automation hooks used by the Playwright test suite and capture tools.
// Exposed as window.__eoa in development builds (or with ?test=1).

export function installTestApi(g: Game) {
  const evLog: string[] = [];
  for (const k of ['quest:started', 'quest:stage', 'quest:completed', 'encounter:cleared', 'zone:entered', 'save:written', 'player:died', 'cinematic:ended', 'collectible:found', 'ability:unlocked'] as const) {
    events.on(k, (p) => evLog.push(`${k} ${JSON.stringify(p)}`));
  }
  const api = {
    game: g,
    events: evLog,
    errors: () => Log.recent.filter((e) => e.level === 'error').map((e) => `[${e.tag}] ${e.msg}`),
    warnings: () => Log.recent.filter((e) => e.level === 'warn').map((e) => `[${e.tag}] ${e.msg}`),
    state: () => ({
      mode: g.mode,
      paused: g.paused,
      zone: g.world.zone?.id ?? null,
      character: g.gs.d.character,
      pos: g.player?.position.toArray() ?? null,
      hp: g.player?.health ?? null,
      quests: g.gs.d.quests,
      flags: g.gs.d.flags,
      inventory: g.gs.d.inventory,
      enemies: g.world.enemies.filter((e) => e.alive).map((e) => ({ type: e.def.id, state: e.state, hp: Math.round(e.health), pos: e.position.toArray().map((v) => +v.toFixed(1)), enc: e.encounterId })),
      cinematic: g.cinematics.active,
      dialogue: g.dialogue.active,
      fps: g.fps,
      stats: g.rs.stats,
      candidate: g.world.candidate?.id ?? null,
    }),
    teleport: (x: number, y: number, z: number) => {
      const p = g.player;
      if (!p?.body) return false;
      p.body.teleport(new THREE.Vector3(x, y, z));
      p.position.set(x, y, z);
      return true;
    },
    face: (yaw: number) => {
      if (g.player) g.player.yaw = yaw;
      g.cam.heading = yaw;
    },
    interact: () => g.world.interact(),
    interactWith: (id: string) => {
      const i = g.world.zone?.findInteractable(id);
      if (!i) return false;
      void i.onInteract();
      return true;
    },
    setFlag: (f: string) => g.gs.setFlag(f),
    give: (item: string, qty = 1) => g.inventory.add(item, qty),
    startQuest: (id: string) => g.quests.start(id),
    completeStage: (id: string) => g.quests.debugCompleteStage(id),
    killEncounter: (id?: string) => {
      for (const e of g.world.enemies) if (e.alive && (!id || e.encounterId === id)) e.receiveHit({ damage: 99999, poise: 999, knock: new THREE.Vector3(), kind: 'heavy', point: e.position.clone(), source: null });
    },
    killAll: () => api.killEncounter(),
    damagePlayer: (n: number) => g.player?.receiveHit({ damage: n, poise: 0, knock: new THREE.Vector3(), kind: 'enemy', point: g.player.position.clone(), source: null, pierce: true }),
    loadZone: (z: string, entry = 'start') => g.loadZone(z, entry, {}),
    skipCinematic: () => g.cinematics.stop(),
    advanceDialogue: () => g.ui.dialogue.forceAdvance(),
    pickChoice: (i: number) => {
      const b = g.ui.dialogue.el.querySelectorAll<HTMLElement>('.ch .btn')[i];
      b?.click();
      return !!b;
    },
    press: (action: string) => {
      // Simulate one frame of a gameplay action press via a synthetic key.
      const code = g.input.bindings[action as keyof typeof g.input.bindings]?.kb[0];
      if (!code) return false;
      window.dispatchEvent(new KeyboardEvent('keydown', { code }));
      setTimeout(() => window.dispatchEvent(new KeyboardEvent('keyup', { code })), 60);
      return true;
    },
    save: (slot: number) => g.manualSave(slot),
    autosave: () => g.autosave('auto'),
    data: Data,
    idleQuests: () => g.quests.idle(),
    snapshot: () => g.rs.snapshot(640, 0.8),
  };
  (window as unknown as { __eoa: typeof api }).__eoa = api;
}
