// Verify the rendered audio set: node tools/audio/verify.mjs
// Checks every WAV listed in Assets/Resources/Audio/manifest.json decodes (PCM16 mono 44.1 kHz), matches the
// manifest, is not silent, does not clip, and that loops wrap continuously. Also checks coverage against the
// SFX recipe names in src/audio/AudioEngine.ts and that no stray WAVs exist.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodeWav, db, peakOf, rmsOf } from './wav.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const GAME = path.resolve(HERE, '../..');
const ROOT = path.join(GAME, 'unity/EchoesOfAether/Assets/Resources/Audio');
const SR = 44100;

const failures = [];
const fail = (msg) => failures.push(msg);

const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'manifest.json'), 'utf8'));
const src = fs.readFileSync(path.join(GAME, 'src/audio/AudioEngine.ts'), 'utf8');
const recipeBlock = src.slice(src.indexOf('const RECIPES'), src.indexOf('export const SFX_IDS'));
const recipeIds = [...recipeBlock.matchAll(/^\s{2}([a-z_0-9]+): \(a, o, t, v\)/gm)].map((m) => m[1]);

const kinds = { sfx: [], music: [], ambience: [], thunder: [] };
for (const c of manifest.clips) (kinds[c.kind] ??= []).push(c);

// ---------------------------------------------------------------- coverage
const sfxIds = new Set(kinds.sfx.map((c) => c.id));
for (const id of recipeIds) if (!sfxIds.has(id)) fail(`sfx recipe ${id} has no clip`);
for (const id of sfxIds) if (!recipeIds.includes(id)) fail(`sfx clip ${id} has no recipe`);
for (const m of ['menu', 'explore', 'combat', 'boss', 'sidequest', 'tension', 'ending']) if (!kinds.music.some((c) => c.id === m)) fail(`music ${m} missing`);
for (const a of ['rain_city', 'metro_drip', 'facility_hum', 'vault_hum', 'wind_roof', 'core_drone']) if (!kinds.ambience.some((c) => c.id === a)) fail(`ambience ${a} missing`);
if ((kinds.thunder[0]?.files.length ?? 0) !== 3) fail('expected 3 thunder variants');

const listed = new Set(manifest.clips.flatMap((c) => c.files.map((f) => f.path + '.wav')));
for (const d of ['SFX', 'Music', 'Ambience', 'Thunder']) {
  for (const n of fs.readdirSync(path.join(ROOT, d))) if (n.endsWith('.wav') && !listed.has(`${d}/${n}`)) fail(`stray file ${d}/${n}`);
}
if (fs.existsSync(path.join(ROOT, 'Voice'))) fail('voice audio present (voice is disabled)');

// ---------------------------------------------------------------- per file
function seam(s) {
  const n = s.length;
  const jump = Math.abs(s[0] - s[n - 1]);
  const diffs = new Float32Array(n - 1);
  for (let i = 1; i < n; i++) diffs[i - 1] = Math.abs(s[i] - s[i - 1]);
  const sorted = Float32Array.from(diffs).sort();
  const p999 = sorted[Math.floor(sorted.length * 0.999)];
  let local = 0; // largest step within 64 samples either side of the seam (natural motion of the material there)
  for (let i = 0; i < 64; i++) local = Math.max(local, diffs[i], diffs[n - 2 - i]);
  const w = Math.round(0.05 * SR);
  const headTail = db(rmsOf(s, 0, w)) - db(rmsOf(s, n - w, n));
  return { jump, p999, local, headTail };
}

const rows = [];
let totalBytes = 0;
for (const c of manifest.clips) {
  for (const f of c.files) {
    const file = path.join(ROOT, f.path + '.wav');
    let w;
    try {
      const buf = fs.readFileSync(file);
      totalBytes += buf.length;
      w = decodeWav(buf);
    } catch (e) {
      fail(`${f.path}: ${e.message}`);
      continue;
    }
    const s = w.samples;
    const tag = f.path;
    if (w.sampleRate !== SR) fail(`${tag}: sample rate ${w.sampleRate}`);
    if (w.channels !== 1) fail(`${tag}: ${w.channels} channels`);
    if (w.frames !== f.samples) fail(`${tag}: ${w.frames} frames, manifest says ${f.samples}`);
    if (Math.abs(w.frames / SR - f.duration) > 1e-3) fail(`${tag}: duration mismatch`);
    const peak = peakOf(s);
    const rms = rmsOf(s);
    let clipped = 0;
    for (let i = 0; i < s.length; i++) if (s[i] >= 32767 / 32768 || s[i] <= -1) clipped++;
    if (clipped) fail(`${tag}: ${clipped} clipped samples`);
    if (db(peak) > -0.5) fail(`${tag}: peak ${db(peak).toFixed(2)} dBFS above -0.5`);
    if (Math.abs(db(peak) - f.peakDb) > 0.05 || Math.abs(db(rms) - f.rmsDb) > 0.05) fail(`${tag}: level differs from manifest`);
    const minRms = c.kind === 'sfx' || c.kind === 'thunder' ? -40 : -30;
    if (!(db(rms) > minRms)) fail(`${tag}: RMS ${db(rms).toFixed(1)} dBFS below ${minRms} (silent?)`);
    if (!(f.gain > 0 && f.gain <= 1)) fail(`${tag}: gain ${f.gain} outside (0,1]`);
    const row = { kind: c.kind, path: tag, dur: w.frames / SR, peak: db(peak), rms: db(rms), gain: f.gain };
    if (c.loop) {
      const st = seam(s);
      Object.assign(row, st);
      row.residual = f.seamResidualDb;
      if (c.kind === 'music' && c.cycleSec) {
        // The wrap must look like the chord-cycle boundaries inside the loop (same head/tail level step).
        const w = Math.round(0.05 * SR);
        const inner = [];
        for (let k = 1; k < c.cycles; k++) {
          const b = Math.round(k * c.cycleSec * SR);
          inner.push(db(rmsOf(s, b, b + w)) - db(rmsOf(s, b - w, b)));
        }
        row.innerHeadTail = inner.reduce((a, b) => a + b, 0) / inner.length;
        if (Math.abs(st.headTail - row.innerHeadTail) > 3) fail(`${tag}: seam level step ${st.headTail.toFixed(1)} dB differs from inner cycle boundaries ${row.innerHeadTail.toFixed(1)} dB`);
      }
      if (st.jump > st.p999) fail(`${tag}: loop seam jump ${st.jump.toFixed(4)} > p99.9 step ${st.p999.toFixed(4)}`);
      if (st.jump > Math.max(3 * st.local, 2 / 32768)) fail(`${tag}: loop seam jump ${st.jump.toFixed(4)} > 3x local step ${st.local.toFixed(4)}`);
      const [lo, hi] = c.kind === 'music' ? [60, 120] : [40, 60];
      if (row.dur < lo - 0.01 || row.dur > hi + 0.01) fail(`${tag}: loop length ${row.dur.toFixed(2)} s outside ${lo}-${hi}`);
    } else {
      // One-shots must end quietly (trimmed tail with fade) and start at once (no leading silence).
      const end = Math.abs(s[s.length - 1]);
      if (end > 4 / 32768) fail(`${tag}: does not end at silence (${end.toFixed(5)})`);
      let lead = 0;
      while (lead < s.length && Math.abs(s[lead]) < 2 / 32768) lead++;
      if (lead / SR > 0.003) fail(`${tag}: ${(lead / SR * 1000).toFixed(1)} ms leading silence`);
    }
    rows.push(row);
  }
}

// ---------------------------------------------------------------- report
const fmt = (v, d = 1) => (Number.isFinite(v) ? v.toFixed(d) : String(v));
console.log(`checked ${rows.length} files (${(totalBytes / 1048576).toFixed(1)} MB), ${recipeIds.length} recipes in AudioEngine.ts`);
for (const k of ['sfx', 'thunder', 'music', 'ambience']) {
  const r = rows.filter((x) => x.kind === k);
  if (!r.length) continue;
  const range = (key, d = 1) => `${fmt(Math.min(...r.map((x) => x[key])), d)}..${fmt(Math.max(...r.map((x) => x[key])), d)}`;
  console.log(`  ${k.padEnd(8)} ${String(r.length).padStart(3)} files  dur ${range('dur', 2)} s  peak ${range('peak')} dBFS  rms ${range('rms')} dBFS  gain ${range('gain', 3)}`);
}
console.log('  loops (seam jump vs p99.9 step / local step, 50 ms head-tail RMS, continuation-vs-start residual before crossfade):');
for (const r of rows.filter((x) => x.jump !== undefined)) {
  console.log(`    ${r.path.padEnd(22)} ${fmt(r.dur, 2).padStart(6)} s  rms ${fmt(r.rms)}  jump ${r.jump.toFixed(5)}  p99.9 ${r.p999.toFixed(5)}  local ${r.local.toFixed(5)}  head-tail ${fmt(r.headTail, 2)} dB${r.innerHeadTail !== undefined ? ` (inner cycle boundaries ${fmt(r.innerHeadTail, 2)} dB)` : ''}  pre-xfade residual ${fmt(r.residual)} dB`);
}
if (failures.length) {
  console.log(`FAIL (${failures.length})`);
  for (const f of failures) console.log('  - ' + f);
  process.exit(1);
}
console.log('PASS');
