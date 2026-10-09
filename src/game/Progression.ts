import { events } from '../core/Events';
import { Data } from './Data';
import type { CharacterId, GameState } from './GameState';
import type { Inventory } from './Inventory';

// Ability unlocks, the Ability Matrix (skill tree) and derived character stats.

export interface CharStats {
  maxHealth: number;
  maxShield: number;
  shieldDelay: number;
  shieldRegen: number;
  maxEnergy: number;
  energyRegen: number;
  cooldownMul: number;
  pulseRadius: number;
  pulseDamage: number;
  pulseStagger: number;
  dashDistance: number;
  dashCooldown: number;
  dashCharges: number;
  dashIframes: number;
  echoRange: number;
  echoDuration: number;
  echoDetect: boolean;
  ultimates: boolean;
  lightDamage: number;
  heavyDamage: number;
  boltDamage: number;
}

export class Progression {
  constructor(private gs: () => GameState, private inv: Inventory) {}

  hasSkill(id: string) {
    return this.gs().d.skills.includes(id);
  }

  /** Spendable points: 1 per Aether Fragment, 3 per Aether Core. */
  points(): number {
    return this.inv.count('aether_fragment') + this.inv.count('aether_core') * 3;
  }

  canBuy(id: string): { ok: boolean; reason?: string } {
    const n = Data.skills[id];
    if (!n) return { ok: false, reason: 'Unknown node' };
    if (this.hasSkill(id)) return { ok: false, reason: 'Already unlocked' };
    if (!this.gs().hasAbility(n.ability)) return { ok: false, reason: `Requires ${Data.abilities[n.ability]?.name ?? n.ability}` };
    for (const r of n.requires) if (!this.hasSkill(r)) return { ok: false, reason: `Requires ${Data.skills[r]?.name ?? r}` };
    if (this.points() < n.cost) return { ok: false, reason: 'Not enough Aether' };
    return { ok: true };
  }

  buy(id: string): boolean {
    if (!this.canBuy(id).ok) return false;
    let cost = Data.skills[id].cost;
    while (cost > 0) {
      if (this.inv.count('aether_fragment') > 0) {
        this.inv.remove('aether_fragment', 1);
        cost--;
      } else if (this.inv.count('aether_core') > 0) {
        this.inv.remove('aether_core', 1);
        this.inv.add('aether_fragment', 3, true);
      } else return false;
    }
    this.gs().d.skills.push(id);
    events.emit('ui:toast', { text: `Ability Matrix: ${Data.skills[id].name}`, kind: 'item' });
    return true;
  }

  stats(char: CharacterId): CharStats {
    const has = (s: string) => this.hasSkill(s);
    const up = (id: string) => this.inv.has(id);
    const resonant = up('up_resonant_core');
    const kael = char === 'kael';
    return {
      maxHealth: (kael ? 110 : 95) + (resonant ? 15 : 0),
      maxShield: 50 + (up('up_shield_matrix') ? 40 : 0),
      shieldDelay: up('up_shield_matrix') ? 2.6 : 3.5,
      shieldRegen: up('up_shield_matrix') ? 24 : 16,
      maxEnergy: 100,
      energyRegen: 9,
      cooldownMul: resonant ? 0.8 : 1,
      pulseRadius: 5.5 * (has('pulse_radius') ? 1.4 : 1),
      pulseDamage: 32 * (has('pulse_damage') ? 1.5 : 1),
      pulseStagger: has('pulse_stagger') ? 2.2 : 1,
      dashDistance: kael ? 6.5 * (has('dash_distance') ? 1.4 : 1) : 4.6 * (has('step_distance') ? 1.4 : 1),
      dashCooldown: kael ? 1.4 * (has('dash_cooldown') ? 0.65 : 1) : 1.0 * (has('step_cooldown') ? 0.65 : 1),
      dashCharges: kael && has('dash_double') ? 2 : 1,
      dashIframes: kael ? 0.28 : 0.34 * (has('step_iframes') ? 2 : 1),
      echoRange: 28 * (has('echo_range') ? 1.5 : 1) * (up('up_echo_amplifier') ? 1.5 : 1),
      echoDuration: 10 + (has('echo_duration') ? 6 : 0) + (up('up_echo_amplifier') ? 4 : 0),
      echoDetect: has('echo_detect'),
      ultimates: up('up_core_attunement'),
      lightDamage: kael ? 15 : 11,
      heavyDamage: kael ? 38 : 28,
      boltDamage: kael ? 12 : 8,
    };
  }
}
