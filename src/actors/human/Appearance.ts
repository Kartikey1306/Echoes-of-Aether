import type { HairStyle, Look } from './HumanBuilder';
import { KAEL, LYRA } from './Looks';

// Player-editable appearance for the two protagonists. An Appearance is applied on top of the
// authored base look, so every trait can be changed and reset independently.

export type HeroId = 'kael' | 'lyra';

export interface Appearance {
  // Body
  height: number;
  shoulders: number;
  hips: number;
  build: number;
  // Face
  skin: string;
  eyes: string;
  jaw: number;
  chin: number;
  nose: number;
  brow: number;
  cheek: number;
  lips: number;
  scar: boolean;
  stubble: number;
  beard: number;
  freckles: number;
  age: number;
  // Hair
  hairStyle: HairStyle;
  hairColor: string;
  // Outfit
  outfit: string;
  accent: string;
  pants: string;
  boots: string;
  armor: string;
  glow: string;
  glow2: string;
  shoulderPads: boolean;
  chestPlate: boolean;
  kneePads: boolean;
  gloves: boolean;
  backpack: boolean;
}

export const SKIN_TONES = ['#f2d0b8', '#e8b998', '#d7a07c', '#c79878', '#b98a6e', '#a8785a', '#8c6248', '#73503b', '#5a3d2c', '#432c20'];
export const HAIR_COLORS = ['#0f0d0c', '#1d1714', '#2b1b14', '#3a2416', '#5a3a22', '#7a5230', '#a8763e', '#c9a46a', '#d8d0c4', '#8d8a86', '#6b2a24', '#2c3a5a'];
export const EYE_COLORS = ['#3a2616', '#5b3a22', '#7a5a2a', '#4f6a3a', '#3c6a7a', '#4a5a80', '#6a6a72'];
export const OUTFIT_COLORS = ['#33363c', '#25272c', '#3a3d44', '#2b2f36', '#3d4436', '#4a4237', '#2e3a4a', '#4a2f2f', '#3b2858', '#5a4430', '#6a6e74', '#1a1c20'];
export const ACCENT_COLORS = ['#3b2858', '#25272c', '#2a4a5a', '#5a2a2a', '#5a4a2a', '#2a5a3a', '#7a2f2a', '#46484e'];
export const ARMOR_COLORS = ['#4b4e54', '#4d5058', '#2a2c30', '#6a6e76', '#5a4a3a', '#3a4a5a', '#7a6a4a', '#3a2e30'];
export const GLOW_COLORS = ['#56b8ff', '#62dcff', '#a77bff', '#5fffc8', '#ffb45e', '#ff6a8a', '#e8f2ff', '#8aff6a'];

export function appearanceFrom(look: Look): Appearance {
  return {
    height: look.body.height,
    shoulders: look.body.shoulderWidth ?? 1,
    hips: look.body.hipWidth ?? 1,
    build: look.body.bulk ?? 1,
    skin: look.skin,
    eyes: look.eyes,
    jaw: look.face.jaw ?? 1,
    chin: look.face.chin ?? 1,
    nose: look.face.nose ?? 1,
    brow: look.face.brow ?? (look.face.female ? 0.6 : 1),
    cheek: look.face.cheek ?? 1,
    lips: look.face.lips ?? 1,
    scar: !!look.face.scar,
    stubble: look.face.stubble ?? 0,
    beard: look.face.beard ?? 0,
    freckles: look.face.freckles ?? 0,
    age: look.face.age ?? 0,
    hairStyle: look.hairStyle,
    hairColor: look.hair,
    outfit: look.top.color,
    accent: look.top.color2,
    pants: look.legs.color,
    boots: look.boots.color,
    armor: look.armor?.color ?? '#4b4e54',
    glow: look.glow?.color ?? '#56b8ff',
    glow2: look.glow?.color2 ?? look.glow?.color ?? '#56b8ff',
    shoulderPads: !!(look.armor?.shoulderL || look.armor?.shoulderR),
    chestPlate: !!look.armor?.chest,
    kneePads: !!look.armor?.knees,
    gloves: !!look.gloves,
    backpack: !!look.backpack,
  };
}

const BASE: Record<HeroId, Look> = { kael: KAEL, lyra: LYRA };

export function baseLook(id: HeroId): Look {
  return BASE[id];
}

const darken = (hex: string, k: number) => {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.round(((n >> 16) & 255) * k), g = Math.round(((n >> 8) & 255) * k), b = Math.round((n & 255) * k);
  return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
};

/** Apply an appearance to a base look, producing the look used to build the model. */
export function applyAppearance(base: Look, a: Appearance): Look {
  const L: Look = structuredClone(base);
  L.body.height = clampN(a.height, 1.5, 2.0);
  L.body.shoulderWidth = clampN(a.shoulders, 0.85, 1.2);
  L.body.hipWidth = clampN(a.hips, 0.85, 1.2);
  L.body.bulk = clampN(a.build, 0.85, 1.2);
  L.body.hairBones = a.hairStyle === 'tied' ? 4 : 0;
  L.skin = a.skin;
  L.eyes = a.eyes;
  L.face = {
    ...L.face,
    jaw: a.jaw,
    chin: a.chin,
    nose: a.nose,
    brow: a.brow,
    cheek: a.cheek,
    lips: a.lips,
    scar: a.scar,
    stubble: a.stubble,
    beard: a.beard,
    freckles: a.freckles,
    age: a.age,
    browColor: darken(a.hairColor, 0.85),
  };
  L.hairStyle = a.hairStyle;
  L.hair = a.hairColor;
  L.top = { ...L.top, color: a.outfit, color2: a.accent };
  L.legs = { ...L.legs, color: a.pants, color2: a.accent };
  L.boots = { ...L.boots, color: a.boots };
  const baseArmor = base.armor ?? { color: a.armor };
  L.armor = {
    ...baseArmor,
    color: a.armor,
    shoulderL: a.shoulderPads ? baseArmor.shoulderL ?? (base.id === 'lyra' ? 0 : 0.9) : 0,
    shoulderR: a.shoulderPads ? baseArmor.shoulderR ?? 0.75 : 0,
    chest: a.chestPlate ? baseArmor.chest ?? (base.id === 'lyra' ? 'R' : 'L') : undefined,
    knees: a.kneePads,
  };
  L.gloves = a.gloves ? { color: base.gloves?.color ?? '#26272a' } : null;
  L.glow = { ...(L.glow ?? { pattern: 'kael' }), color: a.glow, color2: a.glow2 };
  L.backpack = a.backpack;
  return L;
}

function clampN(v: number, lo: number, hi: number) {
  return typeof v === 'number' && isFinite(v) ? Math.max(lo, Math.min(hi, v)) : (lo + hi) / 2;
}

/** Repair untrusted appearance data (from storage or saves). */
export function sanitizeAppearance(id: HeroId, raw: unknown): Appearance {
  const d = appearanceFrom(BASE[id]);
  if (!raw || typeof raw !== 'object') return d;
  const r = raw as Record<string, unknown>;
  const out = { ...d };
  for (const k of Object.keys(d) as (keyof Appearance)[]) {
    const v = r[k];
    const dv = d[k];
    if (typeof dv === 'number' && typeof v === 'number' && isFinite(v)) (out as Record<string, unknown>)[k] = Math.max(0, Math.min(2.5, v));
    else if (typeof dv === 'boolean' && typeof v === 'boolean') (out as Record<string, unknown>)[k] = v;
    else if (typeof dv === 'string' && typeof v === 'string' && (k === 'hairStyle' ? HAIR_OK.has(v) : /^#[0-9a-f]{6}$/i.test(v))) (out as Record<string, unknown>)[k] = v;
  }
  return out;
}
const HAIR_OK = new Set(['short', 'tied', 'buzz', 'swept', 'bob', 'none', 'long', 'bun', 'undercut', 'curly']);

export interface Preset { name: string; a: Partial<Appearance> }

export const PRESETS: Record<HeroId, Preset[]> = {
  kael: [
    { name: 'Survey Lead (default)', a: {} },
    { name: 'Night Shift', a: { outfit: '#1a1c20', accent: '#25272c', armor: '#2a2c30', glow: '#62dcff', hairStyle: 'undercut', stubble: 0.4 } },
    { name: 'Field Veteran', a: { hairStyle: 'buzz', hairColor: '#5a3a22', beard: 0.6, stubble: 0, age: 0.4, outfit: '#3d4436', accent: '#4a4237', armor: '#5a4a3a', glow: '#ffb45e' } },
    { name: 'Long Watch', a: { hairStyle: 'long', hairColor: '#3a2416', stubble: 0.6, outfit: '#2e3a4a', armor: '#3a4a5a', glow: '#56b8ff' } },
  ],
  lyra: [
    { name: 'Systems Engineer (default)', a: {} },
    { name: 'Phase Runner', a: { hairStyle: 'bun', hairColor: '#0f0d0c', outfit: '#2b2f36', accent: '#2a4a5a', glow: '#5fffc8', glow2: '#62dcff' } },
    { name: 'Copper', a: { hairStyle: 'long', hairColor: '#a8763e', freckles: 0.7, skin: '#e8b998', eyes: '#4f6a3a', accent: '#5a2a2a', glow2: '#ff6a8a' } },
    { name: 'Short Cut', a: { hairStyle: 'bob', hairColor: '#2c3a5a', outfit: '#3a3d44', accent: '#3b2858', glow: '#a77bff', glow2: '#62dcff' } },
  ],
};

export function randomAppearance(id: HeroId): Appearance {
  const d = appearanceFrom(BASE[id]);
  const pick = <T>(a: T[]) => a[Math.floor(Math.random() * a.length)];
  const r = (lo: number, hi: number) => lo + Math.random() * (hi - lo);
  const fem = BASE[id].body.build === 'female';
  return {
    ...d,
    height: fem ? r(1.6, 1.8) : r(1.72, 1.92),
    shoulders: r(0.92, 1.1),
    hips: r(0.92, 1.08),
    build: r(0.92, 1.1),
    skin: pick(SKIN_TONES),
    eyes: pick(EYE_COLORS),
    jaw: r(0.85, 1.12),
    chin: r(0.8, 1.2),
    nose: r(0.8, 1.2),
    brow: fem ? r(0.4, 0.8) : r(0.8, 1.3),
    cheek: r(0.8, 1.3),
    lips: r(0.8, 1.3),
    scar: Math.random() < 0.3,
    stubble: fem ? 0 : r(0, 1),
    beard: fem ? 0 : Math.random() < 0.3 ? r(0.3, 0.9) : 0,
    freckles: Math.random() < 0.35 ? r(0.3, 0.9) : 0,
    age: r(0, 0.4),
    hairStyle: pick(['short', 'swept', 'undercut', 'buzz', 'curly', 'bob', 'tied', 'bun', 'long'] as HairStyle[]),
    hairColor: pick(HAIR_COLORS),
    outfit: pick(OUTFIT_COLORS),
    accent: pick(ACCENT_COLORS),
    pants: pick(OUTFIT_COLORS),
    armor: pick(ARMOR_COLORS),
    glow: pick(GLOW_COLORS),
    glow2: pick(GLOW_COLORS),
    shoulderPads: Math.random() < 0.8,
    chestPlate: Math.random() < 0.6,
    kneePads: Math.random() < 0.6,
    gloves: Math.random() < 0.85,
    backpack: Math.random() < 0.5,
  };
}

const KEY = 'eoa.appearance';

/** Global appearance preferences (copied into each new save). */
export class AppearanceStore {
  private data: Partial<Record<HeroId, Appearance>> = {};
  constructor() {
    try {
      const raw = JSON.parse(localStorage.getItem(KEY) ?? '{}');
      for (const id of ['kael', 'lyra'] as HeroId[]) if (raw[id]) this.data[id] = sanitizeAppearance(id, raw[id]);
    } catch {
      this.data = {};
    }
  }
  get(id: HeroId): Appearance {
    return this.data[id] ? { ...this.data[id]! } : appearanceFrom(BASE[id]);
  }
  set(id: HeroId, a: Appearance) {
    this.data[id] = sanitizeAppearance(id, a);
    this.persist();
  }
  reset(id: HeroId) {
    delete this.data[id];
    this.persist();
  }
  all(): Record<HeroId, Appearance> {
    return { kael: this.get('kael'), lyra: this.get('lyra') };
  }
  private persist() {
    try {
      localStorage.setItem(KEY, JSON.stringify(this.data));
    } catch {
      /* storage unavailable: appearance lasts for this session */
    }
  }
}
