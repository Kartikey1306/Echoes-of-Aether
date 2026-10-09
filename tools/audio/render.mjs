// Offline render of the prototype's procedural audio to WAV for the Unity port.
//
//   node tools/audio/render.mjs            (from /Users/kartikey/Desktop/Game)
//
// Runs src/audio/AudioEngine.ts unmodified inside headless Chromium (served by the Vite dev server on
// :5173, started here if it is not running) through tools/audio/adapter.js, then post-processes in Node:
//   SFX       mono 44.1 kHz, leading/trailing silence trimmed, peak -1 dBFS, 3 takes (_v1.._v3) when the
//             recipe is randomized (rnd() pitches or noise), a single file otherwise.
//   Music     one file per mood, an integer number of chord cycles (60-120 s), seamless loop.
//   Ambience  one file per bed, 40-60 s chosen so drones/noise loops are phase-aligned, seamless loop.
//   Thunder   3 variants, peak -1 dBFS.
// Loops: random draws are reseeded so the material after the loop end repeats the loop start; the file begins
// with that real continuation (so the last sample flows into the first) and crossfades back into the loop body
// where the two match best (see makeLoop). Music/ambience are RMS-normalized (-16 / -18 dBFS) with a -1 dBFS
// peak ceiling; manifest files[].gain restores the prototype's relative mix.
// Writes Assets/Resources/Audio/{SFX,Music,Ambience,Thunder}/*.wav and Assets/Resources/Audio/manifest.json.
// Voice is intentionally not rendered (disabled in the port). Check the output with tools/audio/verify.mjs.
import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { db, undb, hashSeed, peakOf, rmsOf, writeWav } from './wav.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const GAME = path.resolve(HERE, '../..');
const OUT = path.join(GAME, 'unity/EchoesOfAether/Assets/Resources/Audio');
const BASE = process.env.EOA_URL ?? 'http://localhost:5173/';
const SR = 44100;

const MOODS = ['menu', 'explore', 'combat', 'boss', 'sidequest', 'tension', 'ending']; // 'silence' = no clip
const AMBIENCES = ['rain_city', 'metro_drip', 'facility_hum', 'vault_hum', 'wind_roof', 'core_drone']; // 'none' = no clip
// Mirrors UI_SOUNDS in AudioEngine.ts (routed to the ui bus).
const UI_SOUNDS = new Set(['ui_hover', 'ui_click', 'ui_back', 'quest_accept', 'quest_complete', 'save', 'load', 'error_ui', 'checkpoint', 'item', 'lore', 'toast']);

const SFX_PEAK_DB = -1;
const MUSIC_RMS_DB = -16;
const AMB_RMS_DB = -18;
const CEILING_DB = -1;
const MUSIC_TARGET_SEC = 80; // loop length aim, clamped to 60..120 in whole chord cycles
const MUSIC_XFADE = 0.3; // seam crossfade, placed by search where loop start and continuation match best
const MUSIC_TAIL = 8.0; // rendered continuation after the loop end (capped at one chord cycle)
const AMB_XFADE = 5.0;
const AMB_TAIL = 15.0;
const SFX_TAKES = 3;
const THUNDER_TAKES = 3;

// Prototype mix (AudioEngine defaults): bus gain = v*v, master DynamicsCompressor.
const BUS_DEFAULT = { master: 0.85, music: 0.6, sfx: 0.8, voice: 0.9, ui: 0.6, ambience: 0.7 };
const COMP = { threshold: -14, knee: 10, ratio: 4 };

// ------------------------------------------------------------------------------------ dev server
async function serverUp() {
  try {
    const r = await fetch(BASE, { signal: AbortSignal.timeout(2000) });
    return r.ok;
  } catch {
    return false;
  }
}

async function ensureServer() {
  if (await serverUp()) return null;
  console.log('[render] Vite dev server not running; starting it on :5173');
  const child = spawn('npx', ['vite', '--port', '5173'], { cwd: GAME, stdio: 'ignore', detached: false });
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 500));
    if (await serverUp()) return child;
  }
  child.kill();
  throw new Error('could not start the Vite dev server');
}

// ------------------------------------------------------------------------------------ helpers
const f32 = (b64) => {
  const b = Buffer.from(b64, 'base64');
  return new Float32Array(b.buffer, b.byteOffset, b.byteLength / 4).slice();
};

function trimSfx(f) {
  const peak = peakOf(f);
  let s = 0;
  while (s < f.length && Math.abs(f[s]) < 1e-6) s++;
  const thr = peak * undb(-70);
  let e = f.length - 1;
  while (e > s && Math.abs(f[e]) < thr) e--;
  e = Math.min(f.length, e + 1 + Math.round(0.01 * SR));
  const out = f.slice(s, e);
  // Short raised-cosine fade so the cut never clicks.
  const nf = Math.min(Math.round(0.015 * SR), Math.floor(out.length * 0.1));
  for (let i = 0; i < nf; i++) out[out.length - 1 - i] *= 0.5 - 0.5 * Math.cos((Math.PI * i) / nf);
  return out;
}

/**
 * Build a seamless loop from `win` = loop body (loopN) + true continuation after the loop end (tailN).
 * The continuation should equal the loop start (same seeds, phase-aligned drones/noise) but can differ in places
 * (e.g. Chrome renders the kick's frequency glide slightly differently later in the timeline, LFO phases in
 * ambience). Search the offset d where loop start and continuation differ least over xN samples, then:
 *   out[0..d)       = continuation  -> the wrap out[last] -> out[0] is the real rendered signal,
 *   out[d..d+xN)    = linear crossfade continuation -> loop start,
 *   out[d+xN..)     = loop body.
 */
function makeLoop(win, loopN, tailN, xN) {
  const step = 441;
  let best = { d: 0, e: Infinity, r: 1 };
  for (let d = 0; d + xN <= tailN; d += step) {
    let e = 0, r = 0;
    for (let i = d; i < d + xN; i++) {
      const x = win[i] - win[loopN + i];
      e += x * x;
      r += win[i] * win[i];
    }
    if (e < best.e) best = { d, e, r };
  }
  const out = win.slice(0, loopN);
  const d = best.d;
  for (let i = 0; i < d; i++) out[i] = win[loopN + i];
  for (let i = 0; i < xN; i++) {
    const a = i / xN; // 0 -> 1
    out[d + i] = win[d + i] * a + win[loopN + d + i] * (1 - a);
  }
  return { out, seamAt: d / SR, residualDb: +db(Math.sqrt(best.e / Math.max(best.r, 1e-20))).toFixed(1) };
}

function scale(f, g) {
  for (let i = 0; i < f.length; i++) f[i] *= g;
  return f;
}

/** Static curve of the prototype's master compressor (soft knee), in dB. */
function compCurve(x) {
  const { threshold: T, knee: W, ratio: R } = COMP;
  if (2 * (x - T) < -W) return x;
  if (2 * Math.abs(x - T) <= W) return x + ((1 / R - 1) * Math.pow(x - T + W / 2, 2)) / (2 * W);
  return T + (x - T) / R;
}

function fracDist(x) {
  return Math.abs(x - Math.round(x));
}

/** Pick an even loop length in [40, 60] s that phase-aligns drones (strongly) and LFOs (weakly). */
function chooseAmbLoop(probe) {
  let best = null;
  for (let L = 40; L <= 60; L += 2) {
    const drone = probe.drones.reduce((s, f) => s + fracDist(f * L), 0);
    const lfo = probe.lfos.reduce((s, f) => s + fracDist(f * L), 0);
    const noiseOk = probe.noisePeriods.every((p) => fracDist(L / p) < 1e-9);
    const score = 10 * drone + lfo + (noiseOk ? 0 : 5) - 0.001 * L;
    if (!best || score < best.score) best = { L, score, drone, lfo };
  }
  return best;
}

function seamStats(f) {
  // Sample jump across the loop point vs the clip's own sample-to-sample motion.
  const jump = Math.abs(f[0] - f[f.length - 1]);
  let maxD = 0;
  const diffs = [];
  for (let i = 1; i < f.length; i++) {
    const d = Math.abs(f[i] - f[i - 1]);
    if (d > maxD) maxD = d;
    if (i % 7 === 0) diffs.push(d);
  }
  diffs.sort((a, b) => a - b);
  const p99 = diffs[Math.floor(diffs.length * 0.99)];
  const w = Math.round(0.1 * SR);
  const head = rmsOf(f, 0, w), tail = rmsOf(f, f.length - w, f.length);
  return { jump, p99, maxD, headTailDb: db(head) - db(tail) };
}

function fileStats(pcm, extra = {}) {
  const f = Float32Array.from(pcm, (v) => v / 32768);
  return {
    samples: pcm.length,
    duration: +(pcm.length / SR).toFixed(4),
    peakDb: +db(peakOf(f)).toFixed(2),
    rmsDb: +db(rmsOf(f)).toFixed(2),
    ...extra,
  };
}

function cleanStale(dir, keep) {
  for (const name of fs.readdirSync(dir)) {
    const base = name.replace(/\.meta$/, '');
    if (!base.endsWith('.wav')) continue;
    if (!keep.has(base)) {
      fs.rmSync(path.join(dir, name));
      console.log('[render] removed stale', path.join(path.basename(dir), name));
    }
  }
}

// ------------------------------------------------------------------------------------ main
const server = await ensureServer();
const browser = await chromium.launch({ headless: true, args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--mute-audio'] });
const page = await browser.newPage();
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(e.message));
page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') pageErrors.push(`[${m.type()}] ${m.text()}`); });

const t0 = Date.now();
const clips = []; // manifest entries
let exitCode = 0;
try {
  await page.goto(new URL('tools/audio/render.html', BASE).href, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
  for (const d of ['SFX', 'Music', 'Ambience', 'Thunder']) fs.mkdirSync(path.join(OUT, d), { recursive: true });
  const produced = { SFX: new Set(), Music: new Set(), Ambience: new Set(), Thunder: new Set() };

  // ---------------------------------------------------------------- SFX
  const ids = await page.evaluate(() => window.R.SFX_IDS);
  console.log(`[render] ${ids.length} SFX recipes`);
  for (const id of ids) {
    const takes = [];
    const raw = async (k) => f32((await page.evaluate(([i, s]) => window.R.renderSfx(i, s), [id, hashSeed('sfx', id, k)])).b64);
    takes.push(await raw(1));
    takes.push(await raw(2));
    let diff = 0;
    for (let i = 0; i < takes[0].length; i++) diff = Math.max(diff, Math.abs(takes[0][i] - takes[1][i]));
    const randomized = diff > 1e-5;
    if (randomized) for (let k = 3; k <= SFX_TAKES; k++) takes.push(await raw(k));
    else takes.length = 1;
    const files = [];
    takes.forEach((take, k) => {
      const srcPeak = peakOf(take);
      if (!(srcPeak > 1e-5)) throw new Error(`${id}: silent render`);
      const t = trimSfx(take);
      const g = undb(SFX_PEAK_DB) / srcPeak;
      scale(t, g);
      const name = randomized ? `${id}_v${k + 1}` : id;
      const pcm = writeWav(path.join(OUT, 'SFX', name + '.wav'), t, SR, hashSeed('dither', name));
      produced.SFX.add(name + '.wav');
      files.push({ path: 'SFX/' + name, ...fileStats(pcm), srcPeak: +srcPeak.toFixed(5), normGain: g });
    });
    clips.push({ id, kind: 'sfx', bus: UI_SOUNDS.has(id) ? 'ui' : 'sfx', loop: false, randomized, files });
    process.stdout.write(`  ${id}${randomized ? ` x${takes.length}` : ''}`);
  }
  process.stdout.write('\n');

  // ---------------------------------------------------------------- Music
  for (const mood of MOODS) {
    const p = await page.evaluate((m) => window.R.probeMusic(m), mood);
    const cycleSec = (16 * p.chords * 60) / p.bpm / 2;
    // Whole chord cycles within 60..120 s. Prefer loop lengths that are (nearly) a whole number of samples so
    // the material after the loop end is sample-identical to the loop start, then lengths near the target.
    let k = 0, bestScore = Infinity;
    for (let c = 1; c * cycleSec <= 120; c++) {
      if (c * cycleSec < 60) continue;
      const score = fracDist(c * cycleSec * SR) * 100 + Math.abs(c * cycleSec - MUSIC_TARGET_SEC) / 100;
      if (score < bestScore) { bestScore = score; k = c; }
    }
    if (!k) throw new Error(`${mood}: no whole-cycle loop length in 60..120 s`);
    const r = await page.evaluate(([m, c, x, s]) => window.R.renderMusic(m, c, x, s), [mood, k, Math.min(MUSIC_TAIL, cycleSec), hashSeed('music', mood)]);
    const win = f32(r.b64);
    const srcPeak = peakOf(win.subarray(0, r.loopSamples));
    const seamLoop = makeLoop(win, r.loopSamples, r.tailSamples, Math.round(MUSIC_XFADE * SR));
    const loop = seamLoop.out;
    const residual = seamLoop.residualDb;
    const rms = rmsOf(loop);
    const g = Math.min(undb(MUSIC_RMS_DB) / rms, undb(CEILING_DB) / peakOf(loop));
    scale(loop, g);
    const pcm = writeWav(path.join(OUT, 'Music', mood + '.wav'), loop, SR, hashSeed('dither', mood));
    produced.Music.add(mood + '.wav');
    const seam = seamStats(loop);
    clips.push({
      id: mood, kind: 'music', bus: 'music', loop: true, bpm: p.bpm, cycles: k, cycleSec: +cycleSec.toFixed(4),
      files: [{ path: 'Music/' + mood, ...fileStats(pcm), srcPeak: +srcPeak.toFixed(5), srcRmsDb: +db(rms).toFixed(2), normGain: g, peakLimited: g < undb(MUSIC_RMS_DB) / rms - 1e-9, seamJump: +seam.jump.toFixed(5), seamResidualDb: residual, seamAt: +seamLoop.seamAt.toFixed(3) }],
    });
    console.log(`[render] music ${mood}: ${p.bpm} bpm, ${k} x ${cycleSec.toFixed(2)} s = ${(r.loopSamples / SR).toFixed(2)} s, src rms ${db(rms).toFixed(1)} dBFS, seam residual ${residual} dB @ ${seamLoop.seamAt.toFixed(2)} s`);
  }

  // ---------------------------------------------------------------- Ambience
  for (const id of AMBIENCES) {
    const probe = await page.evaluate((a) => window.R.probeAmbience(a), id);
    const pick = chooseAmbLoop(probe);
    const r = await page.evaluate(([a, L, x, s]) => window.R.renderAmbience(a, L, x, s), [id, pick.L, AMB_TAIL, hashSeed('amb', id)]);
    const win = f32(r.b64);
    const srcPeak = peakOf(win.subarray(0, r.loopSamples));
    const seamLoop = makeLoop(win, r.loopSamples, r.tailSamples, Math.round(AMB_XFADE * SR));
    const loop = seamLoop.out;
    const residual = seamLoop.residualDb;
    const rms = rmsOf(loop);
    const g = Math.min(undb(AMB_RMS_DB) / rms, undb(CEILING_DB) / peakOf(loop));
    scale(loop, g);
    const pcm = writeWav(path.join(OUT, 'Ambience', id + '.wav'), loop, SR, hashSeed('dither', id));
    produced.Ambience.add(id + '.wav');
    const seam = seamStats(loop);
    clips.push({
      id, kind: 'ambience', bus: 'ambience', loop: true, drones: probe.drones.map((f) => +f.toFixed(2)), lfos: probe.lfos.map((f) => +f.toFixed(3)), sporadicMs: probe.intervalMs, sporadicEvents: r.events,
      files: [{ path: 'Ambience/' + id, ...fileStats(pcm), srcPeak: +srcPeak.toFixed(5), srcRmsDb: +db(rms).toFixed(2), normGain: g, peakLimited: g < undb(AMB_RMS_DB) / rms - 1e-9, seamJump: +seam.jump.toFixed(5), seamResidualDb: residual, seamAt: +seamLoop.seamAt.toFixed(3), droneAlign: +pick.drone.toFixed(4), lfoAlign: +pick.lfo.toFixed(4) }],
    });
    console.log(`[render] ambience ${id}: ${pick.L} s (drone phase err ${pick.drone.toFixed(3)} cyc, lfo ${pick.lfo.toFixed(3)} cyc), src rms ${db(rms).toFixed(1)} dBFS, seam residual ${residual} dB @ ${seamLoop.seamAt.toFixed(2)} s`);
  }

  // ---------------------------------------------------------------- Thunder
  {
    const files = [];
    for (let k = 1; k <= THUNDER_TAKES; k++) {
      const r = await page.evaluate((s) => window.R.renderThunder(s, 1), hashSeed('thunder', k));
      const take = f32(r.b64);
      const srcPeak = peakOf(take);
      const t = trimSfx(take);
      const g = undb(SFX_PEAK_DB) / srcPeak;
      scale(t, g);
      const name = `thunder_${k}`;
      const pcm = writeWav(path.join(OUT, 'Thunder', name + '.wav'), t, SR, hashSeed('dither', name));
      produced.Thunder.add(name + '.wav');
      files.push({ path: 'Thunder/' + name, ...fileStats(pcm), srcPeak: +srcPeak.toFixed(5), normGain: g });
    }
    clips.push({ id: 'thunder', kind: 'thunder', bus: 'ambience', loop: false, randomized: true, files });
  }

  for (const [d, keep] of Object.entries(produced)) cleanStale(path.join(OUT, d), keep);

  // ---------------------------------------------------------------- Playback gains
  // Normalization flattened the prototype's relative levels. gain = (1 / normGain) restores the recipe's
  // original level; the prototype's master compressor (evaluated on the clip peak at default bus volumes)
  // is folded in; one global factor makes the largest gain 1.0 (Unity's AudioSource volume ceiling).
  // Runtime: AudioSource.volume = gain * busCurve(bus) * busCurve(master) * caller volume.
  for (const c of clips) {
    const busV = BUS_DEFAULT[c.bus] ?? 1;
    for (const f of c.files) {
      const x = db(f.srcPeak * busV * busV * BUS_DEFAULT.master * BUS_DEFAULT.master);
      f.compDb = +(compCurve(x) - x).toFixed(2);
      f.rawGain = undb(f.compDb) / f.normGain;
    }
  }
  const maxRaw = Math.max(...clips.flatMap((c) => c.files.map((f) => f.rawGain)));
  for (const c of clips) {
    for (const f of c.files) {
      f.gain = +Math.min(1, f.rawGain / maxRaw).toFixed(4);
      f.normGain = +f.normGain.toFixed(5);
      delete f.rawGain;
    }
  }

  const manifest = {
    version: 1,
    generator: 'tools/audio/render.mjs',
    source: 'src/audio/AudioEngine.ts',
    sampleRate: SR,
    channels: 1,
    mix: {
      gainNote: 'files[].gain is the playback volume that restores the prototype balance (relative recipe levels plus its master compressor at default settings); bus volumes are applied at runtime as v*v like the prototype.',
      busDefaults: BUS_DEFAULT,
      compressor: COMP,
      sfxPeakDb: SFX_PEAK_DB,
      musicRmsDb: MUSIC_RMS_DB,
      ambienceRmsDb: AMB_RMS_DB,
      ceilingDb: CEILING_DB,
      globalGainRef: +maxRaw.toFixed(5),
    },
    clips,
  };
  fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify(manifest, null, 1) + '\n');

  // ---------------------------------------------------------------- report
  const all = clips.flatMap((c) => c.files.map((f) => ({ ...f, kind: c.kind, id: c.id })));
  const bytes = all.reduce((s, f) => s + 44 + f.samples * 2, 0);
  const byKind = (k) => all.filter((f) => f.kind === k);
  console.log(`[render] ${all.length} files, ${(bytes / 1048576).toFixed(1)} MB, ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  for (const k of ['sfx', 'music', 'ambience', 'thunder']) {
    const fs_ = byKind(k);
    const dur = fs_.reduce((s, f) => s + f.duration, 0);
    console.log(`  ${k.padEnd(8)} ${String(fs_.length).padStart(3)} files  ${dur.toFixed(1).padStart(6)} s  peak ${Math.min(...fs_.map((f) => f.peakDb)).toFixed(1)}..${Math.max(...fs_.map((f) => f.peakDb)).toFixed(1)} dBFS  rms ${Math.min(...fs_.map((f) => f.rmsDb)).toFixed(1)}..${Math.max(...fs_.map((f) => f.rmsDb)).toFixed(1)} dBFS  gain ${Math.min(...fs_.map((f) => f.gain)).toFixed(3)}..${Math.max(...fs_.map((f) => f.gain)).toFixed(3)}`);
  }
  if (pageErrors.length) {
    console.log('[render] page errors/warnings:');
    for (const e of pageErrors.slice(0, 20)) console.log('  ' + e);
  }
} catch (e) {
  console.error('[render] FAILED:', e?.stack ?? e);
  for (const pe of pageErrors.slice(0, 20)) console.error('  ' + pe);
  exitCode = 1;
} finally {
  await browser.close();
  if (server) server.kill();
}
process.exit(exitCode);
