// In-page adapter for tools/audio/render.mjs.
//
// Runs the prototype's own synthesis code (src/audio/AudioEngine.ts, served as TS by Vite) inside an
// OfflineAudioContext. Nothing under src/ is modified; the adapter only:
//   - hands the engine an OfflineAudioContext (by temporarily replacing window.AudioContext during unlock),
//   - overrides the context's `currentTime`/`state` on the instance so the engine's real-time schedulers
//     (MusicPlayer.tick, Ambience timers, play()) can be driven ahead of time by a fake clock,
//   - seeds Math.random so renders are reproducible and loop seams can be made to repeat exactly,
//   - bypasses the master DynamicsCompressor (the Unity mix has no master compressor; its effect on the
//     balance is folded into the per-clip gain written to the manifest).
import { AudioEngine, SFX_IDS } from '/src/audio/AudioEngine.ts';

export const SR = 44100;
export { SFX_IDS };

const nativeRandom = Math.random;

// Click fix. The engine gates sources with `gain.setValueAtTime(0.0001, t)` on a fresh GainNode (default
// gain 1) and `source.start(t)` at the same t. Source start and param events are rounded to frames
// differently, so for some t the source's first frame renders at gain 1: a full-scale one-frame spike (very
// audible on noise hats/bursts). Starting every source 1.5 frames later guarantees the gate is already
// closed; ~31 us is inaudible and does not change timing. The odd fraction (1.37) keeps start times away from
// exact frame boundaries: tempos with exactly representable beat lengths (combat: 0.234375 s) would otherwise
// land on frame ties whose rounding flips between chord cycles and breaks loop periodicity.
const START_NUDGE = 1.37 / 44100;
for (const proto of [AudioScheduledSourceNode.prototype, AudioBufferSourceNode.prototype]) {
  const start = proto.start;
  if (start.__eoaNudged) continue;
  const nudged = function (when = 0, ...rest) {
    return start.call(this, when + START_NUDGE, ...rest);
  };
  nudged.__eoaNudged = true;
  proto.start = nudged;
}

function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** FNV-1a over the string form of the parts. */
export function hashSeed(...parts) {
  const s = parts.join('|');
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

function seed(s) {
  Math.random = mulberry32(s >>> 0);
}

/** Build an AudioEngine bound to an OfflineAudioContext with a controllable clock. */
function makeEngine(seconds) {
  const ctx = new OfflineAudioContext(1, Math.max(128, Math.ceil(seconds * SR)), SR);
  const clock = { now: 0 };
  Object.defineProperty(ctx, 'currentTime', { configurable: true, get: () => clock.now });
  Object.defineProperty(ctx, 'state', { configurable: true, get: () => 'running' });
  const engine = new AudioEngine();
  // Unity applies bus volumes at runtime: render at unity bus gain.
  engine.setVolumes({ master: 1, music: 1, sfx: 1, voice: 1, ui: 1, ambience: 1 });
  const NativeCtx = window.AudioContext;
  window.AudioContext = function () { return ctx; };
  try {
    engine.unlock();
  } finally {
    window.AudioContext = NativeCtx;
  }
  if (engine.ctx !== ctx) throw new Error('engine did not adopt the offline context');
  const master = engine.bus('master');
  master.disconnect();
  master.connect(ctx.destination);
  return { ctx, engine, clock };
}

async function finish(ctx) {
  const buf = await ctx.startRendering();
  Math.random = nativeRandom;
  return buf.getChannelData(0);
}

async function toBase64(f32) {
  const blob = new Blob([f32.buffer.slice(f32.byteOffset, f32.byteOffset + f32.byteLength)]);
  const url = await new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = () => rej(fr.error);
    fr.readAsDataURL(blob);
  });
  return String(url).slice(String(url).indexOf(',') + 1);
}

// ------------------------------------------------------------------------------------------- SFX
/** One take of an SFX recipe through AudioEngine.play() (non-positional, vol 1). */
export async function renderSfx(id, takeSeed, seconds = 3) {
  seed(takeSeed);
  const { ctx, engine } = makeEngine(seconds);
  const before = engine.stats.played;
  engine.play(id, undefined, 1);
  if (engine.stats.played !== before + 1) throw new Error(`engine refused to play ${id}`);
  const data = await finish(ctx);
  return { b64: await toBase64(data), samples: data.length };
}

// ------------------------------------------------------------------------------------------- Music
const BAR_LEN = 16; // eighths per chord, mirrors `barLen` in MusicPlayer.schedule

/** Read a mood definition from the engine (MOODS is module private, MusicPlayer exposes it after setMood). */
export function probeMusic(mood) {
  const { engine } = makeEngine(0.1);
  engine.setMusic(mood, true);
  const def = engine.music.def;
  Math.random = nativeRandom;
  if (!def) throw new Error('no mood definition for ' + mood);
  return { bpm: def.bpm, chords: def.chords.length, root: def.root, perc: def.perc };
}

/**
 * Render a mood as [pre-roll cycle][k loop cycles][crossfade tail]. Each chord cycle reseeds Math.random so
 * the random draws (arp choices, noise offsets) around the loop end are identical to those around the loop
 * start: pre-roll cycle uses the seed of cycle k, the tail cycle uses the seed of cycle 1.
 * Returns the window starting at the first loop beat, `loopSamples + tailSamples` long (the tail is the true
 * continuation after the loop end, used to build the seam).
 */
export async function renderMusic(mood, cycles, tailSec, baseSeed) {
  const p = probeMusic(mood);
  const spb = 60 / p.bpm / 2;
  const cycleBeats = BAR_LEN * p.chords;
  const cycleSec = cycleBeats * spb;
  const firstBeat = 0.1; // MusicPlayer.setMood: nextBeat = t + 0.1
  const P = firstBeat + cycleSec;
  const L = cycles * cycleSec;
  if (tailSec > cycleSec) throw new Error('tail longer than one chord cycle');
  const total = P + L + tailSec + 0.5;
  seed(baseSeed);
  const { ctx, engine, clock } = makeEngine(total);
  const music = engine.music;
  const schedule = music.schedule;
  let reseeds = 0;
  music.schedule = function (b, ...rest) {
    if (b % cycleBeats === 0) {
      const c = b / cycleBeats;
      const idx = c === 0 ? cycles : ((c - 1) % cycles) + 1;
      seed(hashSeed(baseSeed, 'cycle', idx));
      reseeds++;
    }
    return schedule.call(this, b, ...rest);
  };
  engine.setMusic(mood, true);
  const step = spb / 4;
  let maxPerTick = 0;
  for (let i = 0; clock.now < total; i++) {
    clock.now = i * step;
    const b0 = music.beat;
    engine.update();
    if (i > 0) maxPerTick = Math.max(maxPerTick, music.beat - b0);
  }
  if (maxPerTick > 1) throw new Error('scheduler advanced more than one beat per tick');
  const data = await finish(ctx);
  const start = Math.round(P * SR);
  const len = Math.round(L * SR) + Math.round(tailSec * SR);
  const win = data.slice(start, start + len);
  return {
    b64: await toBase64(win),
    samples: win.length,
    loopSamples: Math.round(L * SR),
    tailSamples: Math.round(tailSec * SR),
    bpm: p.bpm,
    cycleSec,
    cycles,
    reseeds,
  };
}

// ------------------------------------------------------------------------------------------- Ambience
/** Inspect an ambience bed: drone/LFO oscillator frequencies and the sporadic timer interval. */
export function probeAmbience(id) {
  const { engine } = makeEngine(0.1);
  const si = window.setInterval, ci = window.clearInterval;
  let intervalMs = 0;
  window.setInterval = (fn, ms) => { intervalMs = ms; return 1; };
  window.clearInterval = () => {};
  try {
    engine.setAmbience(id);
  } finally {
    window.setInterval = si;
    window.clearInterval = ci;
  }
  const oscs = engine.amb.nodes.filter((n) => n instanceof OscillatorNode).map((o) => o.frequency.value);
  const noises = engine.amb.nodes.filter((n) => n instanceof AudioBufferSourceNode).map((s) => s.buffer.duration);
  Math.random = nativeRandom;
  return {
    drones: oscs.filter((f) => f >= 20),
    lfos: oscs.filter((f) => f < 20),
    noisePeriods: noises,
    intervalMs,
  };
}

/**
 * Render an ambience bed as three identical windows of `loopSec` (pre-roll, loop body, seam tail). The
 * sporadic-event timer is driven by the fake clock and restarted with the same seed at every window, so the
 * events around the seam repeat exactly. Returns the body window plus `tailSec` of the following window.
 */
export async function renderAmbience(id, loopSec, tailSec, baseSeed) {
  if (tailSec > loopSec) throw new Error('tail longer than the loop');
  const total = 2 * loopSec + tailSec + 0.5;
  seed(baseSeed);
  const { ctx, engine, clock } = makeEngine(total);
  let timerFn = null, timerMs = 0;
  const si = window.setInterval, ci = window.clearInterval;
  window.setInterval = (fn, ms) => { timerFn = fn; timerMs = ms; return 1; };
  window.clearInterval = () => {};
  try {
    engine.setAmbience(id);
  } finally {
    window.setInterval = si;
    window.clearInterval = ci;
  }
  let events = 0;
  if (timerFn && timerMs > 0) {
    const iv = timerMs / 1000;
    for (let w = 0; w * loopSec < total; w++) {
      seed(hashSeed(baseSeed, 'sporadic'));
      const end = Math.min((w + 1) * loopSec, total);
      for (let n = 1; ; n++) {
        const tt = w * loopSec + n * iv;
        if (tt >= end) break;
        clock.now = tt;
        timerFn();
        events++;
      }
    }
  }
  const data = await finish(ctx);
  const start = Math.round(loopSec * SR);
  const len = Math.round(loopSec * SR) + Math.round(tailSec * SR);
  const win = data.slice(start, start + len);
  return {
    b64: await toBase64(win),
    samples: win.length,
    loopSamples: Math.round(loopSec * SR),
    tailSamples: Math.round(tailSec * SR),
    events,
  };
}

// ------------------------------------------------------------------------------------------- Thunder
/** One thunder clap through Ambience.thunder() routed to the ambience bus. */
export async function renderThunder(takeSeed, intensity = 1, seconds = 4.5) {
  seed(takeSeed);
  const { ctx, engine } = makeEngine(seconds);
  const amb = engine.amb;
  const g = ctx.createGain();
  g.connect(engine.bus('ambience'));
  amb.gain = g; // Ambience.thunder() plays into the active bed's gain node
  amb.thunder(intensity);
  const data = await finish(ctx);
  return { b64: await toBase64(data), samples: data.length };
}
