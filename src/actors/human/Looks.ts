import type { Look } from './HumanBuilder';

// Visual definitions for the protagonists and NPCs.

export const KAEL: Look = {
  id: 'kael',
  body: { height: 1.82, build: 'male', shoulderWidth: 1.04, bulk: 1.02, armAngle: 16 },
  skin: '#b98a6e',
  hair: '#1d1714',
  eyes: '#5b3a22',
  face: { female: false, jaw: 1.04, chin: 1.1, brow: 1.15, nose: 1.05, cheek: 1.1, lips: 0.9, scar: true, stubble: 0.85, browColor: '#1f1611' },
  hairStyle: 'short',
  top: { kind: 'jacket', color: '#33363c', color2: '#25272c', hem: 0.8, collar: 'high', pattern: 'kael', zip: 'diag' },
  legs: { color: '#2b2d32', pattern: 'cargo' },
  boots: { color: '#2e2722', top: 0.3, sole: '#141210' },
  gloves: { color: '#26272a' },
  armor: { color: '#4b4e54', shoulderL: 1.15, shoulderR: 0.8, chest: 'L', forearmR: true, knees: true },
  belt: { color: '#3b3530', pouches: 4 },
  iface: 'R',
  glow: { color: '#56b8ff', pattern: 'kael' },
  backpack: true,
};

export const LYRA: Look = {
  id: 'lyra',
  body: { height: 1.7, build: 'female', shoulderWidth: 1.0, hipWidth: 1.0, bulk: 0.98, armAngle: 17, hairBones: 4 },
  skin: '#c79878',
  hair: '#2b1b14',
  eyes: '#5a3920',
  face: { female: true, jaw: 0.96, chin: 0.9, brow: 0.6, nose: 0.88, cheek: 1.25, lips: 1.2, makeup: 0.4, browColor: '#2a1a12' },
  hairStyle: 'tied',
  top: { kind: 'suit', color: '#383b42', color2: '#3b2858', hem: 0.86, collar: 'low', pattern: 'lyra', zip: 'none' },
  legs: { color: '#33363d', color2: '#3b2858', pattern: 'lyra' },
  boots: { color: '#26252a', top: 0.47, sole: '#121114' },
  gloves: { color: '#25262b' },
  armor: { color: '#4d5058', shoulderR: 0.75, forearmL: true },
  harness: { color: '#24252b' },
  glow: { color: '#62dcff', color2: '#a77bff', pattern: 'lyra' },
};

// ---- Central Plaza survivors

export const OREN: Look = {
  id: 'oren',
  body: { height: 1.76, build: 'male', bulk: 1.1, shoulderWidth: 1.02 },
  skin: '#a87a5e',
  hair: '#8d8a86',
  eyes: '#4a3b2c',
  face: { female: false, jaw: 1.08, age: 0.9, beard: 0.7, brow: 1.1, nose: 1.15, browColor: '#77736e' },
  hairStyle: 'swept',
  top: { kind: 'coat', color: '#4a4237', color2: '#38322a', hem: 0.62, collar: 'high', pattern: 'plain', zip: 'center' },
  legs: { color: '#33312e', pattern: 'cargo' },
  boots: { color: '#3a2e24', top: 0.26, sole: '#191512' },
  gloves: { color: '#3a332b' },
  belt: { color: '#2e2a25', pouches: 3 },
};

export const MIRA: Look = {
  id: 'mira',
  body: { height: 1.64, build: 'female', bulk: 0.94 },
  skin: '#d3a685',
  hair: '#3a2416',
  eyes: '#3c2b1d',
  face: { female: true, jaw: 0.94, lips: 1.1, cheek: 1.1, browColor: '#3a2416' },
  hairStyle: 'bob',
  top: { kind: 'jacket', color: '#5a4430', color2: '#7a2f2a', hem: 0.78, collar: 'high', pattern: 'stripe', zip: 'center' },
  legs: { color: '#2f3238' },
  boots: { color: '#2c2724', top: 0.36, sole: '#141210' },
  gloves: null,
  extras: ['headset', 'satchel'],
};

export const TOMAS: Look = {
  id: 'tomas',
  body: { height: 1.78, build: 'male', bulk: 0.95 },
  skin: '#8c6248',
  hair: '#141414',
  eyes: '#33241a',
  face: { female: false, jaw: 1.0, stubble: 0.5, brow: 1.0, browColor: '#141414' },
  hairStyle: 'hood',
  top: { kind: 'poncho', color: '#3d4436', color2: '#2d3229', hem: 0.72, collar: 'none', pattern: 'plain', zip: 'none' },
  legs: { color: '#2d2b29', pattern: 'cargo' },
  boots: { color: '#2b241f', top: 0.3, sole: '#151210' },
  gloves: { color: '#2d2a26' },
  belt: { color: '#2d2925', pouches: 5 },
  extras: ['scarf', 'backpack', 'goggles'],
};

/** Nia: an Aether echo of a child, rendered translucent by the NPC system. */
export const NIA: Look = {
  id: 'nia',
  body: { height: 1.22, build: 'child', bulk: 0.9 },
  skin: '#c8d8ff',
  hair: '#9fb6ff',
  eyes: '#e8f4ff',
  face: { female: true, jaw: 0.9, browColor: '#a8bbee' },
  hairStyle: 'bob',
  top: { kind: 'jacket', color: '#9fb2e8', color2: '#8aa0dd', hem: 0.84, collar: 'low', pattern: 'plain', zip: 'none' },
  legs: { color: '#8ea2d8' },
  boots: { color: '#8396cc', top: 0.24, sole: '#7083b8' },
  gloves: null,
};

/** Dr. Ilse Maren, seen only as an Aether echo. */
export const MAREN: Look = {
  id: 'maren',
  body: { height: 1.68, build: 'female', bulk: 0.96 },
  skin: '#c8d8ff',
  hair: '#a8bbee',
  eyes: '#e8f4ff',
  face: { female: true, jaw: 0.98, age: 0.5, cheek: 1.1, browColor: '#a8bbee' },
  hairStyle: 'bun',
  top: { kind: 'coat', color: '#b8c8f0', color2: '#9fb2e8', hem: 0.58, collar: 'high', pattern: 'plain', zip: 'center' },
  legs: { color: '#8ea2d8' },
  boots: { color: '#8396cc', top: 0.26, sole: '#7083b8' },
  gloves: null,
};

export const LOOKS: Record<string, Look> = { kael: KAEL, lyra: LYRA, oren: OREN, mira: MIRA, tomas: TOMAS, nia: NIA, maren: MAREN };
