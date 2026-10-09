// Minimal 16-bit PCM WAV encode/decode and level helpers (no dependencies).
import fs from 'node:fs';

export function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** FNV-1a over the string form of the parts (same as tools/audio/adapter.js). */
export function hashSeed(...parts) {
  const s = parts.join('|');
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export const db = (x) => (x > 0 ? 20 * Math.log10(x) : -Infinity);
export const undb = (d) => Math.pow(10, d / 20);

export function peakOf(f) {
  let p = 0;
  for (let i = 0; i < f.length; i++) {
    const a = Math.abs(f[i]);
    if (a > p) p = a;
  }
  return p;
}

export function rmsOf(f, from = 0, to = f.length) {
  let s = 0;
  for (let i = from; i < to; i++) s += f[i] * f[i];
  return Math.sqrt(s / Math.max(1, to - from));
}

/** Float [-1,1] -> Int16 with seeded TPDF dither (deterministic output). */
export function toInt16(f, ditherSeed = 1) {
  const rnd = mulberry32(ditherSeed);
  const out = new Int16Array(f.length);
  for (let i = 0; i < f.length; i++) {
    const d = (rnd() - rnd()) / 32768; // triangular, +-1 LSB
    let v = Math.round((f[i] + d) * 32767);
    if (v > 32767) v = 32767;
    else if (v < -32768) v = -32768;
    out[i] = v;
  }
  return out;
}

export function encodeWav(int16, sampleRate = 44100, channels = 1) {
  const dataBytes = int16.length * 2;
  const buf = Buffer.alloc(44 + dataBytes);
  buf.write('RIFF', 0, 'ascii');
  buf.writeUInt32LE(36 + dataBytes, 4);
  buf.write('WAVE', 8, 'ascii');
  buf.write('fmt ', 12, 'ascii');
  buf.writeUInt32LE(16, 16); // fmt chunk size
  buf.writeUInt16LE(1, 20); // PCM
  buf.writeUInt16LE(channels, 22);
  buf.writeUInt32LE(sampleRate, 24);
  buf.writeUInt32LE(sampleRate * channels * 2, 28);
  buf.writeUInt16LE(channels * 2, 32);
  buf.writeUInt16LE(16, 34);
  buf.write('data', 36, 'ascii');
  buf.writeUInt32LE(dataBytes, 40);
  for (let i = 0; i < int16.length; i++) buf.writeInt16LE(int16[i], 44 + i * 2);
  return buf;
}

/** Parse a PCM WAV (any chunk order). Returns { sampleRate, channels, bits, format, samples: Float32Array (ch 0) }. */
export function decodeWav(buf) {
  if (buf.toString('ascii', 0, 4) !== 'RIFF' || buf.toString('ascii', 8, 12) !== 'WAVE') throw new Error('not a RIFF/WAVE file');
  let off = 12;
  let fmt = null;
  let data = null;
  while (off + 8 <= buf.length) {
    const id = buf.toString('ascii', off, off + 4);
    const size = buf.readUInt32LE(off + 4);
    const body = off + 8;
    if (body + size > buf.length) throw new Error(`chunk ${id} overruns file`);
    if (id === 'fmt ') {
      fmt = {
        format: buf.readUInt16LE(body),
        channels: buf.readUInt16LE(body + 2),
        sampleRate: buf.readUInt32LE(body + 4),
        byteRate: buf.readUInt32LE(body + 8),
        blockAlign: buf.readUInt16LE(body + 12),
        bits: buf.readUInt16LE(body + 14),
      };
    } else if (id === 'data') {
      data = { off: body, size };
    }
    off = body + size + (size & 1);
  }
  if (!fmt) throw new Error('missing fmt chunk');
  if (!data) throw new Error('missing data chunk');
  if (fmt.format !== 1 || fmt.bits !== 16) throw new Error(`unsupported format ${fmt.format}/${fmt.bits}`);
  if (fmt.blockAlign !== fmt.channels * 2 || fmt.byteRate !== fmt.sampleRate * fmt.blockAlign) throw new Error('inconsistent fmt chunk');
  if (data.size % fmt.blockAlign !== 0) throw new Error('data size not a whole number of frames');
  const frames = data.size / fmt.blockAlign;
  const samples = new Float32Array(frames);
  for (let i = 0; i < frames; i++) samples[i] = buf.readInt16LE(data.off + i * fmt.blockAlign) / 32768;
  return { ...fmt, frames, samples };
}

export function writeWav(path, f, sampleRate, ditherSeed) {
  const pcm = toInt16(f, ditherSeed);
  fs.writeFileSync(path, encodeWav(pcm, sampleRate, 1));
  return pcm;
}
