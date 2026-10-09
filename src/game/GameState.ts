import { events } from '../core/Events';
import { Data } from './Data';

// The complete serializable progression state of one playthrough.

export type CharacterId = 'kael' | 'lyra';

export interface QuestState {
  status: 'active' | 'done';
  stage: number;
  progress: Record<string, number>;
}

export interface GameStateData {
  schema: number;
  character: CharacterId;
  startCharacter: CharacterId;
  zone: string;
  entry: string;
  position: [number, number, number] | null;
  yaw: number;
  checkpoint: { zone: string; pos: [number, number, number]; yaw: number } | null;
  quests: Record<string, QuestState>;
  tracked: string | null;
  flags: Record<string, boolean | number | string>;
  inventory: Record<string, number>;
  unlocked: string[];
  skills: string[];
  collected: string[];
  defeated: string[];
  revealed: string[];
  lore: string[];
  stats: { playtime: number; kills: number; deaths: number; damageDealt: number; damageTaken: number };
  /** Player-customised appearance of the protagonists for this playthrough. */
  appearance?: Partial<Record<CharacterId, unknown>>;
}

export const STATE_SCHEMA = 1;

export function newGameState(character: CharacterId): GameStateData {
  return {
    schema: STATE_SCHEMA,
    character,
    startCharacter: character,
    zone: 'plaza',
    entry: 'start',
    position: null,
    yaw: 0,
    checkpoint: null,
    quests: {},
    tracked: null,
    flags: {},
    inventory: {},
    unlocked: character === 'kael' ? ['pulse'] : ['pulse'],
    skills: [],
    collected: [],
    defeated: [],
    revealed: [],
    lore: [],
    stats: { playtime: 0, kills: 0, deaths: 0, damageDealt: 0, damageTaken: 0 },
  };
}

/** Structural validation for loaded saves. Returns an error string or null. */
export function validateState(s: unknown): string | null {
  if (!s || typeof s !== 'object') return 'state is not an object';
  const d = s as Partial<GameStateData>;
  if (d.schema !== STATE_SCHEMA) return `unsupported schema ${d.schema}`;
  if (d.character !== 'kael' && d.character !== 'lyra') return 'invalid character';
  if (typeof d.zone !== 'string' || !Data.zones[d.zone]) return `unknown zone ${d.zone}`;
  if (typeof d.quests !== 'object' || !d.quests) return 'quests missing';
  for (const [id, q] of Object.entries(d.quests)) {
    if (!Data.quests[id]) return `unknown quest ${id}`;
    if (!q || (q.status !== 'active' && q.status !== 'done') || typeof q.stage !== 'number') return `bad quest state ${id}`;
  }
  if (typeof d.inventory !== 'object' || !d.inventory) return 'inventory missing';
  for (const [id, n] of Object.entries(d.inventory)) {
    if (!Data.items[id]) return `unknown item ${id}`;
    if (typeof n !== 'number' || n < 0 || !isFinite(n)) return `bad item count ${id}`;
  }
  for (const k of ['unlocked', 'skills', 'collected', 'defeated', 'revealed', 'lore'] as const) {
    if (!Array.isArray(d[k])) return `${k} missing`;
  }
  if (!d.stats || typeof d.stats.playtime !== 'number') return 'stats missing';
  if (d.position !== null && (!Array.isArray(d.position) || d.position.length !== 3 || d.position.some((v) => typeof v !== 'number' || !isFinite(v)))) return 'bad position';
  return null;
}

export class GameState {
  d: GameStateData;
  constructor(d: GameStateData) {
    this.d = d;
    // Saves from before lore ids matched their dialogue ids stored 'rec_01' etc.
    const legacy: Record<string, string> = { log_testament: 'lore_hidden_vault' };
    d.lore = [...new Set(d.lore.map((id) => (Data.dialogues[id] ? id : legacy[id] ?? 'lore_' + id)))].filter((id) => Data.dialogues[id]);
  }

  flag(name: string): boolean {
    return !!this.d.flags[name];
  }
  setFlag(name: string, value: boolean | number | string = true) {
    if (this.d.flags[name] === value) return;
    this.d.flags[name] = value;
    events.emit('flag:set', { flag: name, value });
  }

  hasAbility(id: string) {
    return this.d.unlocked.includes(id);
  }
  unlock(id: string) {
    if (this.hasAbility(id)) return;
    this.d.unlocked.push(id);
    events.emit('ability:unlocked', { ability: id });
  }

  isCollected(id: string) {
    return this.d.collected.includes(id);
  }
  markCollected(id: string) {
    if (!this.isCollected(id)) this.d.collected.push(id);
  }

  isRevealed(id: string) {
    return this.d.revealed.includes(id);
  }
  reveal(id: string) {
    if (!this.isRevealed(id)) this.d.revealed.push(id);
  }

  isDefeated(id: string) {
    return this.d.defeated.includes(id);
  }
  markDefeated(id: string) {
    if (!this.isDefeated(id)) this.d.defeated.push(id);
  }

  questStatus(id: string): 'none' | 'active' | 'done' {
    return this.d.quests[id]?.status ?? 'none';
  }

  /** Evaluate a dialogue/quest condition string. */
  check(cond: string): boolean {
    const neg = cond.startsWith('!');
    const c = neg ? cond.slice(1) : cond;
    const parts = c.split(':');
    let r = false;
    switch (parts[0]) {
      case 'flag': r = this.flag(parts[1]); break;
      case 'quest': r = this.questStatus(parts[1]) === parts[2]; break;
      case 'stage': {
        const q = this.d.quests[parts[1]];
        const def = Data.quests[parts[1]];
        r = !!q && q.status === 'active' && def?.stages[q.stage]?.id === parts[2];
        break;
      }
      case 'item': {
        const m = parts[1].match(/^([a-z0-9_]+)(>=(\d+))?$/);
        if (m) r = (this.d.inventory[m[1]] ?? 0) >= (m[3] ? parseInt(m[3]) : 1);
        break;
      }
      case 'char': r = this.d.character === parts[1]; break;
      case 'ability': r = this.hasAbility(parts[1]); break;
      case 'revealed': r = this.isRevealed(parts[1]); break;
      case 'collected': r = this.isCollected(parts[1]); break;
      default: r = false;
    }
    return neg ? !r : r;
  }

  checkAll(conds?: string[]): boolean {
    return !conds || conds.every((c) => this.check(c));
  }
}
