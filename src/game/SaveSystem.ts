import { events } from '../core/Events';
import { Log } from '../core/Log';
import { Data } from './Data';
import { validateState, type GameStateData } from './GameState';
import type { SettingsData } from './Settings';

// Three-slot save system with atomic writes, checksums, corruption detection and backup recovery.

export const SLOT_COUNT = 3;
const MAGIC = 'EOA-SAVE';
const VERSION = 1;

export type SaveKind = 'manual' | 'auto' | 'checkpoint';

export interface SaveEnvelope {
  magic: string;
  version: number;
  slot: number;
  kind: SaveKind;
  timestamp: string;
  playtime: number;
  zone: string;
  character: string;
  mission: string;
  thumbnail: string;
  checksum: string;
  state: GameStateData;
  settings: SettingsData | null;
}

export interface SlotInfo {
  slot: number;
  status: 'empty' | 'ok' | 'corrupt' | 'recovered';
  envelope: SaveEnvelope | null;
  backup: SaveEnvelope | null;
  error?: string;
}

/** Storage backend. The browser uses localStorage; the desktop build provides a native file backend. */
export interface SaveBackend {
  name: string;
  read(key: string): Promise<string | null>;
  /** Must not leave a partially-written value under `key` if interrupted. */
  writeAtomic(key: string, data: string): Promise<void>;
  remove(key: string): Promise<void>;
}

interface NativeSaveApi {
  read(name: string): Promise<string | null>;
  writeAtomic(name: string, data: string): Promise<void>;
  remove(name: string): Promise<void>;
}

class LocalStorageBackend implements SaveBackend {
  name = 'localStorage';
  async read(key: string) {
    return localStorage.getItem('eoa.' + key);
  }
  async writeAtomic(key: string, data: string) {
    // Stage to a temp key, verify the round trip, then commit. localStorage.setItem is atomic per key,
    // so the committed key always holds either the old or the new complete value.
    const tmp = 'eoa.' + key + '.tmp';
    localStorage.setItem(tmp, data);
    const back = localStorage.getItem(tmp);
    if (back !== data) {
      localStorage.removeItem(tmp);
      throw new Error('verification of staged save failed');
    }
    localStorage.setItem('eoa.' + key, data);
    localStorage.removeItem(tmp);
  }
  async remove(key: string) {
    localStorage.removeItem('eoa.' + key);
  }
}

class NativeBackend implements SaveBackend {
  name = 'native-fs';
  constructor(private api: NativeSaveApi) {}
  read(key: string) {
    return this.api.read(key + '.json');
  }
  writeAtomic(key: string, data: string) {
    return this.api.writeAtomic(key + '.json', data);
  }
  remove(key: string) {
    return this.api.remove(key + '.json');
  }
}

// CRC32 for integrity checking.
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
export function crc32(str: string): string {
  let c = 0xffffffff;
  for (let i = 0; i < str.length; i++) {
    const code = str.charCodeAt(i);
    c = CRC_TABLE[(c ^ (code & 0xff)) & 0xff] ^ (c >>> 8);
    c = CRC_TABLE[(c ^ (code >>> 8)) & 0xff] ^ (c >>> 8);
  }
  return ((c ^ 0xffffffff) >>> 0).toString(16).padStart(8, '0');
}

export function parseEnvelope(raw: string | null): { env: SaveEnvelope | null; error?: string } {
  if (raw === null) return { env: null };
  let env: SaveEnvelope;
  try {
    env = JSON.parse(raw);
  } catch {
    return { env: null, error: 'File is not valid JSON' };
  }
  if (!env || env.magic !== MAGIC) return { env: null, error: 'Not an Echoes of Aether save' };
  if (env.version !== VERSION) return { env: null, error: `Unsupported save version ${env.version}` };
  if (!env.state) return { env: null, error: 'Missing state' };
  const sum = crc32(JSON.stringify(env.state));
  if (sum !== env.checksum) return { env: null, error: 'Checksum mismatch (file damaged)' };
  const err = validateState(env.state);
  if (err) return { env: null, error: 'Invalid state: ' + err };
  return { env };
}

export class SaveSystem {
  backend: SaveBackend;
  /** Slot used by the current playthrough (autosaves go here). */
  activeSlot = 1;
  lastSaveAt = 0;
  writing = false;

  constructor() {
    const native = (window as unknown as { eoaNative?: { saves?: NativeSaveApi } }).eoaNative?.saves;
    this.backend = native ? new NativeBackend(native) : new LocalStorageBackend();
    Log.info('save', 'backend', this.backend.name);
  }

  private key(slot: number) {
    return `slot${slot}`;
  }
  private bakKey(slot: number) {
    return `slot${slot}.bak`;
  }

  async info(slot: number): Promise<SlotInfo> {
    const main = parseEnvelope(await this.backend.read(this.key(slot)));
    const bak = parseEnvelope(await this.backend.read(this.bakKey(slot)));
    if (main.env) return { slot, status: 'ok', envelope: main.env, backup: bak.env };
    if (main.error) return { slot, status: bak.env ? 'recovered' : 'corrupt', envelope: null, backup: bak.env, error: main.error };
    return { slot, status: bak.env ? 'recovered' : 'empty', envelope: null, backup: bak.env };
  }

  async allInfo(): Promise<SlotInfo[]> {
    const out: SlotInfo[] = [];
    for (let s = 1; s <= SLOT_COUNT; s++) out.push(await this.info(s));
    return out;
  }

  /** Most recent loadable save across all slots (main file, or backup if the main file is damaged). */
  async latest(): Promise<SaveEnvelope | null> {
    let best: SaveEnvelope | null = null;
    for (const i of await this.allInfo()) {
      const env = i.envelope ?? i.backup;
      if (env && (!best || env.timestamp > best.timestamp)) best = env;
    }
    return best;
  }

  async write(slot: number, kind: SaveKind, state: GameStateData, settings: SettingsData | null, thumbnail = ''): Promise<boolean> {
    if (this.writing) {
      Log.warn('save', 'write skipped: another write in progress');
      return false;
    }
    this.writing = true;
    try {
      const stateCopy = JSON.parse(JSON.stringify(state)) as GameStateData;
      const err = validateState(stateCopy);
      if (err) throw new Error('refusing to write invalid state: ' + err);
      const mission = Object.entries(stateCopy.quests).filter(([, q]) => q.status === 'active').map(([id]) => Data.quests[id]).filter((q) => q?.type === 'main')[0]?.title ?? (stateCopy.flags.game_complete ? 'Epilogue' : 'Aether-9');
      const env: SaveEnvelope = {
        magic: MAGIC,
        version: VERSION,
        slot,
        kind,
        timestamp: new Date().toISOString(),
        playtime: stateCopy.stats.playtime,
        zone: stateCopy.zone,
        character: stateCopy.character,
        mission,
        thumbnail,
        checksum: crc32(JSON.stringify(stateCopy)),
        state: stateCopy,
        settings,
      };
      const data = JSON.stringify(env);
      // Keep the previous valid save as a backup before committing the new one.
      const prev = await this.backend.read(this.key(slot));
      if (prev && parseEnvelope(prev).env) await this.backend.writeAtomic(this.bakKey(slot), prev);
      await this.backend.writeAtomic(this.key(slot), data);
      // Verify the committed file.
      const check = parseEnvelope(await this.backend.read(this.key(slot)));
      if (!check.env) throw new Error('post-write verification failed: ' + check.error);
      this.lastSaveAt = performance.now();
      events.emit('save:written', { slot, kind });
      return true;
    } catch (e) {
      Log.error('save', 'write failed', e);
      events.emit('save:failed', { slot, reason: (e as Error).message });
      return false;
    } finally {
      this.writing = false;
    }
  }

  async load(slot: number, preferBackup = false): Promise<SaveEnvelope | null> {
    const i = await this.info(slot);
    if (preferBackup) return i.backup;
    return i.envelope ?? i.backup;
  }

  /** Replace a damaged main file with its backup. */
  async recover(slot: number): Promise<boolean> {
    const i = await this.info(slot);
    if (!i.backup) return false;
    await this.backend.writeAtomic(this.key(slot), JSON.stringify(i.backup));
    return true;
  }

  async delete(slot: number) {
    await this.backend.remove(this.key(slot));
    await this.backend.remove(this.bakKey(slot));
  }
}
