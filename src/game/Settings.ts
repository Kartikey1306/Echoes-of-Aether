import { events } from '../core/Events';
import { ACTIONS, defaultBindings, type Bindings } from '../core/Input';
import { Log } from '../core/Log';
import type { GraphicsOptions } from '../render/Renderer';

export type Difficulty = 'story' | 'normal' | 'hard';

export interface SettingsData {
  version: number;
  gameplay: { difficulty: Difficulty; cameraSensitivity: number; invertY: boolean; aimSensitivity: number; cameraShake: number; autoLock: boolean };
  graphics: GraphicsOptions & { fullscreen: boolean; preset: 'low' | 'medium' | 'high' | 'ultra' | 'custom' };
  audio: { master: number; music: number; sfx: number; voice: number; ambience: number; ui: number; voiceSynthesis: boolean };
  controls: { bindings: Bindings; padLookSpeed: number; vibration: boolean };
  accessibility: { subtitles: boolean; subtitleSize: 'small' | 'medium' | 'large' | 'xl'; subtitleBackground: number; flashIntensity: number; cameraShake: number; uiScale: number; speakerNames: boolean; holdToSkip: boolean };
  language: { locale: string };
}

export const SETTINGS_VERSION = 1;

export function defaultSettings(): SettingsData {
  return {
    version: SETTINGS_VERSION,
    gameplay: { difficulty: 'normal', cameraSensitivity: 1, invertY: false, aimSensitivity: 0.6, cameraShake: 1, autoLock: true },
    graphics: {
      preset: 'high',
      resolution: 'balanced',
      fullscreen: false,
      frameLimit: 'vsync',
      shadows: 'high',
      effects: 'high',
      textures: 'high',
      viewDistance: 'high',
      antialiasing: 'fxaa',
    },
    audio: { master: 0.85, music: 0.6, sfx: 0.8, voice: 0.9, ambience: 0.7, ui: 0.6, voiceSynthesis: false },
    controls: { bindings: defaultBindings(), padLookSpeed: 1, vibration: true },
    accessibility: { subtitles: true, subtitleSize: 'medium', subtitleBackground: 0.55, flashIntensity: 1, cameraShake: 1, uiScale: 1, speakerNames: true, holdToSkip: true },
    language: { locale: 'en' },
  };
}

export const GRAPHICS_PRESETS: Record<'low' | 'medium' | 'high' | 'ultra', Omit<GraphicsOptions, 'frameLimit'>> = {
  low: { resolution: 'performance', shadows: 'off', effects: 'low', textures: 'low', viewDistance: 'low', antialiasing: 'fxaa' },
  medium: { resolution: 'balanced', shadows: 'low', effects: 'medium', textures: 'medium', viewDistance: 'medium', antialiasing: 'fxaa' },
  high: { resolution: 'balanced', shadows: 'high', effects: 'high', textures: 'high', viewDistance: 'high', antialiasing: 'fxaa' },
  ultra: { resolution: 'native', shadows: 'high', effects: 'high', textures: 'high', viewDistance: 'high', antialiasing: 'msaa' },
};

const KEY = 'eoa.settings';

const num = (v: unknown, lo: number, hi: number, d: number) => (typeof v === 'number' && isFinite(v) ? Math.max(lo, Math.min(hi, v)) : d);
const pick = <T extends string>(v: unknown, opts: readonly T[], d: T): T => (opts.includes(v as T) ? (v as T) : d);
const bool = (v: unknown, d: boolean) => (typeof v === 'boolean' ? v : d);

/** Validate and repair untrusted settings data, filling any missing or invalid fields with defaults. */
export function sanitizeSettings(raw: unknown): SettingsData {
  const d = defaultSettings();
  if (!raw || typeof raw !== 'object') return d;
  const r = raw as Partial<SettingsData> & Record<string, unknown>;
  const g = (r.gameplay ?? {}) as Partial<SettingsData['gameplay']>;
  const gr = (r.graphics ?? {}) as Partial<SettingsData['graphics']>;
  const a = (r.audio ?? {}) as Partial<SettingsData['audio']>;
  const c = (r.controls ?? {}) as Partial<SettingsData['controls']>;
  const ac = (r.accessibility ?? {}) as Partial<SettingsData['accessibility']>;
  const q3 = ['low', 'medium', 'high'] as const;
  const bindings = defaultBindings();
  if (c.bindings && typeof c.bindings === 'object') {
    for (const act of ACTIONS) {
      const b = (c.bindings as Partial<Bindings>)[act];
      if (b && Array.isArray(b.kb) && Array.isArray(b.pad)) {
        bindings[act] = { kb: b.kb.filter((x) => typeof x === 'string').slice(0, 3), pad: b.pad.filter((x) => typeof x === 'string').slice(0, 2) };
      }
    }
  }
  return {
    version: SETTINGS_VERSION,
    gameplay: {
      difficulty: pick(g.difficulty, ['story', 'normal', 'hard'] as const, d.gameplay.difficulty),
      cameraSensitivity: num(g.cameraSensitivity, 0.1, 3, d.gameplay.cameraSensitivity),
      invertY: bool(g.invertY, d.gameplay.invertY),
      aimSensitivity: num(g.aimSensitivity, 0.1, 3, d.gameplay.aimSensitivity),
      cameraShake: num(g.cameraShake, 0, 1.5, d.gameplay.cameraShake),
      autoLock: bool(g.autoLock, d.gameplay.autoLock),
    },
    graphics: {
      preset: pick(gr.preset, ['low', 'medium', 'high', 'ultra', 'custom'] as const, d.graphics.preset),
      resolution: pick(gr.resolution, ['performance', 'balanced', 'quality', 'native'] as const, d.graphics.resolution),
      fullscreen: bool(gr.fullscreen, d.graphics.fullscreen),
      frameLimit: pick(gr.frameLimit, ['vsync', '30'] as const, d.graphics.frameLimit),
      shadows: pick(gr.shadows, ['off', 'low', 'medium', 'high'] as const, d.graphics.shadows),
      effects: pick(gr.effects, q3, d.graphics.effects),
      textures: pick(gr.textures, q3, d.graphics.textures),
      viewDistance: pick(gr.viewDistance, q3, d.graphics.viewDistance),
      antialiasing: pick(gr.antialiasing, ['off', 'fxaa', 'msaa'] as const, d.graphics.antialiasing),
    },
    audio: {
      master: num(a.master, 0, 1, d.audio.master),
      music: num(a.music, 0, 1, d.audio.music),
      sfx: num(a.sfx, 0, 1, d.audio.sfx),
      voice: num(a.voice, 0, 1, d.audio.voice),
      ambience: num(a.ambience, 0, 1, d.audio.ambience),
      ui: num(a.ui, 0, 1, d.audio.ui),
      voiceSynthesis: false,
    },
    controls: { bindings, padLookSpeed: num(c.padLookSpeed, 0.2, 3, d.controls.padLookSpeed), vibration: bool(c.vibration, d.controls.vibration) },
    accessibility: {
      subtitles: bool(ac.subtitles, d.accessibility.subtitles),
      subtitleSize: pick(ac.subtitleSize, ['small', 'medium', 'large', 'xl'] as const, d.accessibility.subtitleSize),
      subtitleBackground: num(ac.subtitleBackground, 0, 1, d.accessibility.subtitleBackground),
      flashIntensity: num(ac.flashIntensity, 0, 1, d.accessibility.flashIntensity),
      cameraShake: num(ac.cameraShake, 0, 1, d.accessibility.cameraShake),
      uiScale: num(ac.uiScale, 0.75, 1.5, d.accessibility.uiScale),
      speakerNames: bool(ac.speakerNames, d.accessibility.speakerNames),
      holdToSkip: bool(ac.holdToSkip, d.accessibility.holdToSkip),
    },
    language: { locale: typeof r.language?.locale === 'string' ? r.language.locale : 'en' },
  };
}

export class Settings {
  data: SettingsData;
  constructor() {
    this.data = this.load();
  }

  private load(): SettingsData {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return defaultSettings();
      return sanitizeSettings(JSON.parse(raw));
    } catch (err) {
      Log.warn('settings', 'stored settings unreadable, using defaults', err);
      return defaultSettings();
    }
  }

  save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(this.data));
    } catch (err) {
      Log.warn('settings', 'failed to persist settings', err);
    }
  }

  update(section: keyof SettingsData, patch: Record<string, unknown>) {
    const sec = this.data[section] as unknown as Record<string, unknown>;
    Object.assign(sec, patch);
    this.data = sanitizeSettings(this.data);
    this.save();
    events.emit('settings:changed', { section });
  }

  applyPreset(p: 'low' | 'medium' | 'high' | 'ultra') {
    Object.assign(this.data.graphics, GRAPHICS_PRESETS[p], { preset: p });
    this.save();
    events.emit('settings:changed', { section: 'graphics' });
  }

  resetSection(section: keyof SettingsData) {
    const d = defaultSettings();
    (this.data as unknown as Record<string, unknown>)[section] = (d as unknown as Record<string, unknown>)[section];
    this.save();
    events.emit('settings:changed', { section });
  }

  /** Effective camera-shake scale (gameplay setting x accessibility cap). */
  get shakeScale() {
    return this.data.gameplay.cameraShake * this.data.accessibility.cameraShake;
  }

  get difficultyMods() {
    switch (this.data.gameplay.difficulty) {
      case 'story': return { enemyDamage: 0.5, enemyHealth: 0.75, playerRegen: 1.5, aggression: 0.75 };
      case 'hard': return { enemyDamage: 1.45, enemyHealth: 1.3, playerRegen: 0.8, aggression: 1.3 };
      default: return { enemyDamage: 1, enemyHealth: 1, playerRegen: 1, aggression: 1 };
    }
  }
}
