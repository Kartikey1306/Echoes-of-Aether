import * as THREE from 'three';

// Procedural texture primitives: tileable noise, FBM, height->normal, canvas helpers.

export class TileNoise {
  private perm: Uint8Array;
  private grad: Float32Array;
  constructor(seed = 1) {
    this.perm = new Uint8Array(512);
    this.grad = new Float32Array(256);
    let s = seed >>> 0 || 1;
    const rnd = () => {
      s ^= s << 13; s >>>= 0;
      s ^= s >>> 17;
      s ^= s << 5; s >>>= 0;
      return s / 4294967296;
    };
    const p = new Uint8Array(256);
    for (let i = 0; i < 256; i++) { p[i] = i; this.grad[i] = rnd() * 2 - 1; }
    for (let i = 255; i > 0; i--) {
      const j = Math.floor(rnd() * (i + 1));
      const t = p[i]; p[i] = p[j]; p[j] = t;
    }
    for (let i = 0; i < 512; i++) this.perm[i] = p[i & 255];
  }
  /** Value noise in [-1,1], tileable with integer period (px, py). */
  value(x: number, y: number, px = 256, py = 256): number {
    const xi = Math.floor(x), yi = Math.floor(y);
    const xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const P = this.perm, G = this.grad;
    const x0 = ((xi % px) + px) % px, x1 = (x0 + 1) % px;
    const y0 = ((yi % py) + py) % py, y1 = (y0 + 1) % py;
    const a = G[P[P[x0 & 255] + (y0 & 255)]];
    const b = G[P[P[x1 & 255] + (y0 & 255)]];
    const c = G[P[P[x0 & 255] + (y1 & 255)]];
    const d = G[P[P[x1 & 255] + (y1 & 255)]];
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  }
  /** Tileable fbm over [0,1)^2 with base frequency `freq` cells. */
  fbm(u: number, v: number, freq: number, octaves = 5, gain = 0.5): number {
    let sum = 0, amp = 1, norm = 0, f = freq;
    for (let o = 0; o < octaves; o++) {
      sum += amp * this.value(u * f, v * f, f, f);
      norm += amp;
      amp *= gain;
      f *= 2;
    }
    return sum / norm;
  }
  /** Ridged variant for cracks/veins. */
  ridged(u: number, v: number, freq: number, octaves = 4): number {
    let sum = 0, amp = 1, norm = 0, f = freq;
    for (let o = 0; o < octaves; o++) {
      sum += amp * (1 - Math.abs(this.value(u * f, v * f, f, f)));
      norm += amp;
      amp *= 0.5;
      f *= 2;
    }
    return sum / norm;
  }
}

export function makeCanvas(w: number, h = w): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  const ctx = c.getContext('2d', { willReadFrequently: true })!;
  return [c, ctx];
}

/** Fill a float field via callback (u,v in [0,1)). */
export function field(size: number, fn: (u: number, v: number, x: number, y: number) => number): Float32Array {
  const f = new Float32Array(size * size);
  for (let y = 0; y < size; y++) {
    const v = y / size;
    for (let x = 0; x < size; x++) f[y * size + x] = fn(x / size, v, x, y);
  }
  return f;
}

/** Convert a tileable height field to a tangent-space normal map canvas. */
export function heightToNormal(h: Float32Array, size: number, strength: number): HTMLCanvasElement {
  const [c, ctx] = makeCanvas(size);
  const img = ctx.createImageData(size, size);
  const d = img.data;
  const at = (x: number, y: number) => h[((y + size) % size) * size + ((x + size) % size)];
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = (at(x + 1, y) - at(x - 1, y)) * strength;
      const dy = (at(x, y + 1) - at(x, y - 1)) * strength;
      let nx = -dx, ny = dy, nz = 1;
      const l = Math.hypot(nx, ny, nz);
      nx /= l; ny /= l; nz /= l;
      const i = (y * size + x) * 4;
      d[i] = (nx * 0.5 + 0.5) * 255;
      d[i + 1] = (ny * 0.5 + 0.5) * 255;
      d[i + 2] = (nz * 0.5 + 0.5) * 255;
      d[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return c;
}

/** Write a grayscale/colour field into a canvas. fn returns [r,g,b] in 0..1 (sRGB). */
export function paint(size: number, fn: (u: number, v: number, x: number, y: number) => [number, number, number], h = size): HTMLCanvasElement {
  const [c, ctx] = makeCanvas(size, h);
  const img = ctx.createImageData(size, h);
  const d = img.data;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < size; x++) {
      const [r, g, b] = fn(x / size, y / h, x, y);
      const i = (y * size + x) * 4;
      d[i] = Math.max(0, Math.min(255, r * 255));
      d[i + 1] = Math.max(0, Math.min(255, g * 255));
      d[i + 2] = Math.max(0, Math.min(255, b * 255));
      d[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return c;
}

export function tex(canvas: HTMLCanvasElement, opts: { srgb?: boolean; repeat?: number | [number, number]; aniso?: number } = {}): THREE.CanvasTexture {
  const t = new THREE.CanvasTexture(canvas);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  if (opts.repeat !== undefined) {
    const r = Array.isArray(opts.repeat) ? opts.repeat : [opts.repeat, opts.repeat];
    t.repeat.set(r[0], r[1]);
  }
  t.colorSpace = opts.srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  t.anisotropy = opts.aniso ?? 8;
  t.generateMipmaps = true;
  t.minFilter = THREE.LinearMipmapLinearFilter;
  t.needsUpdate = true;
  return t;
}

/** Linear-space RGB triple from a hex string (for vertex colours). */
export function lin(hex: string): [number, number, number] {
  const c = new THREE.Color(hex);
  return [c.r, c.g, c.b];
}

export function mixRGB(a: [number, number, number], b: [number, number, number], t: number): [number, number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

export function scaleRGB(a: [number, number, number], k: number): [number, number, number] {
  return [a[0] * k, a[1] * k, a[2] * k];
}

/** Global texture quality (size multiplier) set from graphics settings before zone builds. */
export const TexQuality = { size: 512 as 256 | 512 | 1024, aniso: 8 };
