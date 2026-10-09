import { events } from '../core/Events';
import { Data, type ItemCategory, type ItemDef } from './Data';
import type { GameState } from './GameState';

// Data-driven inventory backed by GameState.inventory.

export class Inventory {
  constructor(private gs: () => GameState) {}

  count(id: string): number {
    return this.gs().d.inventory[id] ?? 0;
  }

  has(id: string, n = 1) {
    return this.count(id) >= n;
  }

  /** Adds up to the stack limit. Returns the number actually added. */
  add(id: string, qty = 1, silent = false): number {
    const def = Data.items[id];
    if (!def) {
      console.warn('[inventory] unknown item', id);
      return 0;
    }
    const inv = this.gs().d.inventory;
    const cur = inv[id] ?? 0;
    const added = Math.max(0, Math.min(qty, def.stack - cur));
    if (added <= 0) {
      if (!silent) events.emit('ui:toast', { text: `${def.name}: inventory full`, kind: 'warn' });
      return 0;
    }
    inv[id] = cur + added;
    if (def.effect.type === 'lore') {
      const lore = def.effect.lore as string;
      const l = this.gs().d.lore;
      if (!l.includes(lore)) l.push(lore);
    }
    events.emit('item:added', { id, qty: added, total: inv[id] });
    return added;
  }

  remove(id: string, qty = 1): boolean {
    const inv = this.gs().d.inventory;
    const cur = inv[id] ?? 0;
    if (cur < qty) return false;
    inv[id] = cur - qty;
    if (inv[id] <= 0) delete inv[id];
    events.emit('item:removed', { id, qty, total: inv[id] ?? 0 });
    return true;
  }

  list(category?: ItemCategory): { def: ItemDef; qty: number }[] {
    const inv = this.gs().d.inventory;
    return Object.entries(inv)
      .filter(([id, n]) => n > 0 && Data.items[id] && (!category || Data.items[id].category === category))
      .map(([id, qty]) => ({ def: Data.items[id], qty }))
      .sort((a, b) => a.def.name.localeCompare(b.def.name));
  }
}
