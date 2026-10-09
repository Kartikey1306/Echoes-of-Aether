import { events } from '../core/Events';
import { Data } from './Data';

// Timed powerup effects.

export interface Buffs {
  damageMul: number;
  attackSpeed: number;
  dashMul: number;
  reveal: boolean;
}

export class Powerups {
  active = new Map<string, { remaining: number; duration: number }>();

  activate(id: string): { shieldRestore: boolean } {
    const def = Data.powerups[id];
    if (!def) return { shieldRestore: false };
    if (def.duration > 0) {
      this.active.set(id, { remaining: def.duration, duration: def.duration });
      events.emit('powerup:activated', { id, duration: def.duration });
    } else events.emit('powerup:activated', { id, duration: 0 });
    return { shieldRestore: def.stat === 'shieldRestore' };
  }

  update(dt: number) {
    for (const [id, s] of this.active) {
      s.remaining -= dt;
      if (s.remaining <= 0) {
        this.active.delete(id);
        events.emit('powerup:expired', { id });
      }
    }
  }

  buffs(): Buffs {
    const a = this.active;
    return {
      damageMul: a.has('aether_shard') ? 1 + Data.powerups.aether_shard.value : 1,
      attackSpeed: a.has('overcharge') ? 1 + Data.powerups.overcharge.value : 1,
      dashMul: a.has('phase_core') ? 1 + Data.powerups.phase_core.value : 1,
      reveal: a.has('echo_fragment'),
    };
  }

  clear() {
    this.active.clear();
  }
}
