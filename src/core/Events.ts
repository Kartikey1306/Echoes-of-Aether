// Typed global event bus. Gameplay systems (quests, achievements, audio, UI) subscribe here
// instead of referencing each other directly.

export interface GameEvents {
  'enemy:killed': { id: number; type: string; tags: string[]; spawnId?: string; zone: string };
  'enemy:damaged': { id: number; type: string; amount: number };
  'enemy:aggro': { id: number; type: string };
  'player:damaged': { amount: number; source: string };
  'player:died': { zone: string };
  'player:respawned': { zone: string };
  'player:landed': { speed: number };
  'ability:used': { ability: string; character: string };
  'ability:unlocked': { ability: string };
  'item:added': { id: string; qty: number; total: number };
  'item:removed': { id: string; qty: number; total: number };
  'powerup:activated': { id: string; duration: number };
  'powerup:expired': { id: string };
  'collectible:found': { id: string; kind: string };
  'interact': { id: string; kind: string };
  'trigger:enter': { id: string };
  'trigger:exit': { id: string };
  'zone:entered': { zone: string; entry: string };
  'zone:leaving': { zone: string };
  'flag:set': { flag: string; value: unknown };
  'quest:started': { id: string };
  'quest:stage': { id: string; stage: string };
  'quest:objective': { id: string; objective: string; progress: number; required: number };
  'quest:completed': { id: string };
  'dialogue:started': { id: string };
  'dialogue:ended': { id: string };
  'dialogue:choice': { id: string; node: string; choice: string };
  'cinematic:started': { id: string };
  'cinematic:ended': { id: string; skipped: boolean };
  'puzzle:solved': { id: string };
  'encounter:started': { id: string };
  'encounter:cleared': { id: string };
  'talk': { npc: string };
  'pickup': { id: string };
  'character:swapped': { character: string };
  'save:written': { slot: number; kind: string };
  'save:failed': { slot: number; reason: string };
  'checkpoint': { id: string };
  'combat:state': { inCombat: boolean };
  'boss:phase': { id: string; phase: number };
  'settings:changed': { section: string };
  'ui:toast': { text: string; kind?: 'info' | 'quest' | 'item' | 'warn' | 'lore' };
  'lightning': { intensity: number };
}

type Handler<T> = (payload: T) => void;

export class EventBus<M extends object> {
  private handlers = new Map<keyof M, Set<Handler<never>>>();

  on<K extends keyof M>(key: K, handler: Handler<M[K]>): () => void {
    let set = this.handlers.get(key);
    if (!set) {
      set = new Set();
      this.handlers.set(key, set);
    }
    set.add(handler as Handler<never>);
    return () => this.off(key, handler);
  }

  once<K extends keyof M>(key: K, handler: Handler<M[K]>): () => void {
    const off = this.on(key, (p) => {
      off();
      handler(p);
    });
    return off;
  }

  off<K extends keyof M>(key: K, handler: Handler<M[K]>): void {
    this.handlers.get(key)?.delete(handler as Handler<never>);
  }

  emit<K extends keyof M>(key: K, payload: M[K]): void {
    const set = this.handlers.get(key);
    if (!set) return;
    // Copy so handlers may unsubscribe while being dispatched.
    for (const h of [...set]) {
      try {
        (h as Handler<M[K]>)(payload);
      } catch (err) {
        console.error(`[events] handler for ${String(key)} failed`, err);
      }
    }
  }
}

export const events = new EventBus<GameEvents>();
