import * as THREE from 'three';
import { clamp01, lerp, smoothstep } from '../../core/MathUtil';

// Procedural skinned-mesh construction kit.
// Parts are generated directly in bind-pose world space (bones have identity rest rotation),
// with per-vertex skin weights derived from the bone chain each part follows.

export type RGB = [number, number, number];

export interface SkinInfluence { bone: number; w: number }

/** Accumulates vertices for one material. */
export class MeshBucket {
  pos: number[] = [];
  nrm: number[] = [];
  uv: number[] = [];
  col: number[] = [];
  si: number[] = [];
  sw: number[] = [];
  idx: number[] = [];
  get count() {
    return this.pos.length / 3;
  }

  addVertex(p: THREE.Vector3, n: THREE.Vector3, u: number, v: number, c: RGB, inf: SkinInfluence[]) {
    this.pos.push(p.x, p.y, p.z);
    this.nrm.push(n.x, n.y, n.z);
    this.uv.push(u, v);
    this.col.push(c[0], c[1], c[2]);
    const sorted = inf.filter((i) => i.w > 0.001).sort((a, b) => b.w - a.w).slice(0, 4);
    let total = 0;
    for (const s of sorted) total += s.w;
    for (let k = 0; k < 4; k++) {
      const s = sorted[k];
      this.si.push(s ? s.bone : 0);
      this.sw.push(s && total > 0 ? s.w / total : k === 0 && !sorted.length ? 1 : 0);
    }
  }

  toGeometry(): THREE.BufferGeometry {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.nrm, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    g.setAttribute('color', new THREE.Float32BufferAttribute(this.col, 3));
    g.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(this.si, 4));
    g.setAttribute('skinWeight', new THREE.Float32BufferAttribute(this.sw, 4));
    g.setIndex(this.idx);
    return g;
  }
}

/** Profile key for a loft: radii are in metres. */
export interface ProfileKey {
  t: number;
  rx: number; // half width (lateral)
  rzF: number; // front depth
  rzB?: number; // back depth (defaults to rzF)
  ox?: number; // lateral offset of the ring center
  oz?: number; // forward offset of the ring center
  n?: number; // superellipse exponent (2 = ellipse, higher = boxier)
  rxL?: number; // optional separate half width toward +side
}

export interface SampledProfile { rx: number; rxL: number; rzF: number; rzB: number; ox: number; oz: number; n: number }

/** Smooth (Catmull-Rom) interpolation of profile keys. */
export function sampleProfile(keys: ProfileKey[], t: number): SampledProfile {
  t = clamp01(t);
  let i = 0;
  while (i < keys.length - 2 && keys[i + 1].t < t) i++;
  const k1 = keys[i], k2 = keys[Math.min(i + 1, keys.length - 1)];
  const k0 = keys[Math.max(0, i - 1)], k3 = keys[Math.min(keys.length - 1, i + 2)];
  const span = k2.t - k1.t;
  const u = span > 1e-6 ? (t - k1.t) / span : 0;
  const cr = (a: number, b: number, c: number, d: number) => {
    const u2 = u * u, u3 = u2 * u;
    const v = 0.5 * (2 * b + (-a + c) * u + (2 * a - 5 * b + 4 * c - d) * u2 + (-a + 3 * b - 3 * c + d) * u3);
    // Clamp overshoot between neighbouring keys to keep silhouettes clean.
    const lo = Math.min(b, c) - Math.abs(c - b) * 0.15, hi = Math.max(b, c) + Math.abs(c - b) * 0.15;
    return Math.min(hi, Math.max(lo, v));
  };
  const f = (get: (k: ProfileKey) => number) => cr(get(k0), get(k1), get(k2), get(k3));
  return {
    rx: f((k) => k.rx),
    rxL: f((k) => k.rxL ?? k.rx),
    rzF: f((k) => k.rzF),
    rzB: f((k) => k.rzB ?? k.rzF),
    ox: f((k) => k.ox ?? 0),
    oz: f((k) => k.oz ?? 0),
    n: f((k) => k.n ?? 2),
  };
}

/** A polyline the loft follows, with the bone owning each segment. */
export interface Chain {
  points: THREE.Vector3[];
  bones: number[]; // bones[i] owns segment points[i] -> points[i+1]
  /** Blend half-width (metres) around interior joints. */
  blend?: number;
  /** Optional extra influence evaluated per vertex (e.g. torso -> shoulders). */
  extra?: (p: THREE.Vector3, t: number) => SkinInfluence[];
}

export interface LoftOptions {
  chain: Chain;
  profile: ProfileKey[];
  rings: number;
  radial: number;
  /** Reference forward and side directions used to orient cross-sections. */
  fwd?: THREE.Vector3;
  side?: THREE.Vector3;
  capStart?: boolean;
  capEnd?: boolean;
  color: RGB | ((t: number, phi: number, p: THREE.Vector3) => RGB);
  /** Portion of the ring to generate (radians); default full circle. Partial rings are open strips. */
  phiStart?: number;
  phiEnd?: number;
  /** Outward offset applied after profile evaluation (for clothing layers / shells). */
  inflate?: number;
  /** Per-vertex radial displacement (metres). */
  displace?: (t: number, phi: number) => number;
  uvScale?: number;
  t0?: number;
  t1?: number;
  flip?: boolean;
}

interface Frame { c: THREE.Vector3; T: THREE.Vector3; S: THREE.Vector3; F: THREE.Vector3; s: number; seg: number; segT: number }

/** Builds a queryable lofted surface along a chain. */
export class LoftSurface {
  readonly length: number;
  private cum: number[] = [];
  readonly opts: LoftOptions;
  constructor(opts: LoftOptions) {
    this.opts = opts;
    const pts = opts.chain.points;
    let L = 0;
    this.cum.push(0);
    for (let i = 1; i < pts.length; i++) {
      L += pts[i].distanceTo(pts[i - 1]);
      this.cum.push(L);
    }
    this.length = L;
  }

  frameAt(t: number): Frame {
    const pts = this.opts.chain.points;
    const s = clamp01(t) * this.length;
    let seg = 0;
    while (seg < pts.length - 2 && this.cum[seg + 1] < s) seg++;
    const segLen = this.cum[seg + 1] - this.cum[seg];
    const segT = segLen > 1e-6 ? (s - this.cum[seg]) / segLen : 0;
    const c = new THREE.Vector3().lerpVectors(pts[seg], pts[seg + 1], segT);
    // Smooth tangent: blend neighbouring segment directions near joints.
    const dir = (k: number) => new THREE.Vector3().subVectors(pts[Math.min(k + 1, pts.length - 1)], pts[Math.max(k, 0)]).normalize();
    const T = dir(seg);
    if (segT < 0.25 && seg > 0) T.lerp(dir(seg - 1), 0.5 * (1 - segT / 0.25)).normalize();
    if (segT > 0.75 && seg < pts.length - 2) T.lerp(dir(seg + 1), 0.5 * ((segT - 0.75) / 0.25)).normalize();
    const fwdRef = this.opts.fwd ?? new THREE.Vector3(0, 0, 1);
    const sideRef = this.opts.side ?? new THREE.Vector3(1, 0, 0);
    const F = fwdRef.clone().addScaledVector(T, -fwdRef.dot(T));
    if (F.lengthSq() < 1e-6) F.copy(sideRef).cross(T);
    F.normalize();
    const S = sideRef.clone().addScaledVector(T, -sideRef.dot(T)).addScaledVector(F, -sideRef.dot(F));
    if (S.lengthSq() < 1e-6) S.crossVectors(T, F);
    S.normalize();
    return { c, T, S, F, s, seg, segT };
  }

  /** Surface point at (t, phi) with optional outward offset. phi=0 is +side, phi=PI/2 is front. */
  point(t: number, phi: number, offset = 0, out = new THREE.Vector3()): THREE.Vector3 {
    const fr = this.frameAt(t);
    const pr = sampleProfile(this.opts.profile, t);
    return this.pointFromFrame(fr, pr, t, phi, offset, out);
  }

  pointFromFrame(fr: Frame, pr: SampledProfile, t: number, phi: number, offset: number, out: THREE.Vector3) {
    const c = Math.cos(phi), s = Math.sin(phi);
    const e = 2 / pr.n;
    const rx = c >= 0 ? pr.rxL : pr.rx;
    const rz = s >= 0 ? pr.rzF : pr.rzB;
    const inflate = (this.opts.inflate ?? 0) + offset + (this.opts.displace ? this.opts.displace(t, phi) : 0);
    const x = Math.sign(c) * Math.pow(Math.abs(c), e) * (rx + inflate);
    const z = Math.sign(s) * Math.pow(Math.abs(s), e) * (rz + inflate);
    return out.copy(fr.c).addScaledVector(fr.S, x + pr.ox).addScaledVector(fr.F, z + pr.oz);
  }

  /** Skin influences for a parameter along the chain. */
  influences(t: number, p: THREE.Vector3): SkinInfluence[] {
    const ch = this.opts.chain;
    const s = clamp01(t) * this.length;
    const blend = ch.blend ?? 0.04;
    const inf = new Map<number, number>();
    const add = (b: number, w: number) => inf.set(b, (inf.get(b) ?? 0) + w);
    if (ch.bones.length === 1) add(ch.bones[0], 1);
    else {
      // Find the segment, then blend with neighbours near interior joints.
      let seg = 0;
      while (seg < ch.points.length - 2 && this.cum[seg + 1] < s) seg++;
      const b = ch.bones[Math.min(seg, ch.bones.length - 1)];
      const distStart = s - this.cum[seg];
      const distEnd = this.cum[seg + 1] - s;
      let w = 1;
      if (seg > 0 && distStart < blend) {
        const k = 0.5 + 0.5 * smoothstep(0, 1, distStart / blend);
        add(ch.bones[seg - 1], 1 - k);
        w = k;
      }
      if (seg < ch.bones.length - 1 && distEnd < blend) {
        const k = 0.5 + 0.5 * smoothstep(0, 1, distEnd / blend);
        add(ch.bones[seg + 1], w * (1 - k));
        w = w * k;
      }
      add(b, w);
    }
    let list = [...inf.entries()].map(([bone, w]) => ({ bone, w }));
    if (ch.extra) {
      const ex = ch.extra(p, t);
      const exTotal = ex.reduce((a, e) => a + e.w, 0);
      if (exTotal > 0) {
        const keep = Math.max(0, 1 - exTotal);
        list = list.map((l) => ({ bone: l.bone, w: l.w * keep })).concat(ex);
      }
    }
    return list;
  }

  build(bucket: MeshBucket) {
    const o = this.opts;
    const rings = Math.max(2, o.rings);
    const radial = Math.max(3, o.radial);
    const p0 = o.phiStart ?? 0;
    const p1 = o.phiEnd ?? Math.PI * 2;
    const full = Math.abs(p1 - p0 - Math.PI * 2) < 1e-4;
    const cols = full ? radial + 1 : radial + 1;
    const t0 = o.t0 ?? 0, t1 = o.t1 ?? 1;
    const base = bucket.count;
    const tmp = new THREE.Vector3();
    const uvs = o.uvScale ?? 4;
    const grid: THREE.Vector3[][] = [];
    for (let r = 0; r <= rings; r++) {
      const t = lerp(t0, t1, r / rings);
      const fr = this.frameAt(t);
      const pr = sampleProfile(o.profile, t);
      const row: THREE.Vector3[] = [];
      for (let k = 0; k < cols; k++) {
        const phi = lerp(p0, p1, k / radial);
        row.push(this.pointFromFrame(fr, pr, t, phi, 0, new THREE.Vector3()));
      }
      grid.push(row);
    }
    // Normals by central differences on the grid (seam-aware for full rings).
    for (let r = 0; r <= rings; r++) {
      const t = lerp(t0, t1, r / rings);
      for (let k = 0; k < cols; k++) {
        const p = grid[r][k];
        const kPrev = full ? (k === 0 ? radial - 1 : k - 1) : Math.max(0, k - 1);
        const kNext = full ? (k === radial ? 1 : k + 1) : Math.min(cols - 1, k + 1);
        const du = new THREE.Vector3().subVectors(grid[r][kNext], grid[r][kPrev]);
        const rPrev = Math.max(0, r - 1), rNext = Math.min(rings, r + 1);
        const dv = new THREE.Vector3().subVectors(grid[rNext][k], grid[rPrev][k]);
        const n = new THREE.Vector3().crossVectors(du, dv);
        if (o.flip) n.negate();
        if (n.lengthSq() < 1e-12) {
          const fr = this.frameAt(t);
          n.subVectors(p, fr.c);
        }
        n.normalize();
        // Ensure outward orientation.
        const fr = this.frameAt(t);
        tmp.subVectors(p, fr.c);
        if (tmp.dot(n) < 0 && !o.flip) n.negate();
        const phi = lerp(p0, p1, k / radial);
        const col = typeof o.color === 'function' ? o.color(t, phi, p) : o.color;
        const circ = 2 * Math.PI * 0.08;
        bucket.addVertex(p, n, (k / radial) * circ * uvs, t * this.length * uvs, col, this.influences(t, p));
      }
    }
    // Pick winding so faces point outward regardless of chain direction.
    const midR = Math.floor(rings / 2), midK = Math.floor(radial / 4);
    const pa = grid[midR][midK], pc = grid[midR + 1 <= rings ? midR + 1 : midR - 1][midK], pb = grid[midR][midK + 1];
    const triN = new THREE.Vector3().crossVectors(new THREE.Vector3().subVectors(pc, pa), new THREE.Vector3().subVectors(pb, pa));
    if (midR + 1 > rings) triN.negate();
    const outward = new THREE.Vector3().subVectors(pa, this.frameAt(lerp(t0, t1, midR / rings)).c);
    let acb = triN.dot(outward) > 0;
    if (o.flip) acb = !acb;
    for (let r = 0; r < rings; r++) {
      for (let k = 0; k < radial; k++) {
        const a = base + r * cols + k;
        const b = a + 1;
        const c = a + cols;
        const d = c + 1;
        if (acb) bucket.idx.push(a, c, b, b, c, d);
        else bucket.idx.push(a, b, c, b, d, c);
      }
    }
    if (full) {
      if (o.capStart) this.cap(bucket, t0, grid[0], -1);
      if (o.capEnd) this.cap(bucket, t1, grid[rings], 1);
    }
  }

  private cap(bucket: MeshBucket, t: number, ring: THREE.Vector3[], dirSign: number) {
    const fr = this.frameAt(t);
    const center = new THREE.Vector3();
    for (let i = 0; i < ring.length - 1; i++) center.add(ring[i]);
    center.divideScalar(ring.length - 1);
    const n = fr.T.clone().multiplyScalar(dirSign);
    // Slight dome so caps don't look perfectly flat.
    center.addScaledVector(n, 0.004);
    const col = typeof this.opts.color === 'function' ? this.opts.color(t, 0, center) : this.opts.color;
    const ci = bucket.count;
    bucket.addVertex(center, n, 0.5, 0.5, col, this.influences(t, center));
    const start = bucket.count;
    for (let i = 0; i < ring.length; i++) bucket.addVertex(ring[i], n, 0, 0, col, this.influences(t, ring[i]));
    const q = Math.floor(ring.length / 4);
    const tn = new THREE.Vector3().crossVectors(new THREE.Vector3().subVectors(ring[q], center), new THREE.Vector3().subVectors(ring[q + 1], center));
    const forward = tn.dot(n) > 0;
    for (let i = 0; i < ring.length - 1; i++) {
      if (forward) bucket.idx.push(ci, start + i, start + i + 1);
      else bucket.idx.push(ci, start + i + 1, start + i);
    }
  }
}

/**
 * A shell patch conforming to a loft surface over a (t, phi) rectangle, extruded by `thickness`.
 * Used for armor plates, straps, collars, panels and conduits.
 */
export function addPatch(
  bucket: MeshBucket,
  surf: LoftSurface,
  o: {
    t0: number; t1: number; phi0: number; phi1: number;
    offset: number; thickness: number; color: RGB;
    segT?: number; segPhi?: number;
    /** Bevel inset of the top face (fraction of the patch size). */
    bevel?: number;
    /** Extra outward bulge at the patch centre. */
    bulge?: number;
  },
) {
  const nt = o.segT ?? 6, np = o.segPhi ?? 8;
  const bev = o.bevel ?? 0.12;
  const bul = o.bulge ?? 0;
  const top: THREE.Vector3[][] = [];
  const bot: THREE.Vector3[][] = [];
  const infl: SkinInfluence[][][] = [];
  for (let i = 0; i <= nt; i++) {
    const a = i / nt;
    const t = lerp(o.t0, o.t1, a);
    const rowT: THREE.Vector3[] = [], rowB: THREE.Vector3[] = [], rowI: SkinInfluence[][] = [];
    for (let j = 0; j <= np; j++) {
      const b = j / np;
      const phi = lerp(o.phi0, o.phi1, b);
      // Bevel: edges of the top face sit lower than the centre.
      const edge = Math.min(a, 1 - a, b, 1 - b);
      const lift = smoothstep(0, bev, edge);
      const cb = Math.sin(a * Math.PI) * Math.sin(b * Math.PI);
      const pB = surf.point(t, phi, o.offset);
      const pT = surf.point(t, phi, o.offset + o.thickness * (0.35 + 0.65 * lift) + bul * cb);
      rowT.push(pT);
      rowB.push(pB);
      rowI.push(surf.influences(t, pB));
    }
    top.push(rowT);
    bot.push(rowB);
    infl.push(rowI);
  }
  const emitGrid = (g: THREE.Vector3[][], flip: boolean) => {
    const base = bucket.count;
    for (let i = 0; i <= nt; i++) {
      for (let j = 0; j <= np; j++) {
        const p = g[i][j];
        const du = new THREE.Vector3().subVectors(g[i][Math.min(np, j + 1)], g[i][Math.max(0, j - 1)]);
        const dv = new THREE.Vector3().subVectors(g[Math.min(nt, i + 1)][j], g[Math.max(0, i - 1)][j]);
        const n = new THREE.Vector3().crossVectors(du, dv).normalize();
        const center = surf.frameAt(lerp(o.t0, o.t1, i / nt)).c;
        if (new THREE.Vector3().subVectors(p, center).dot(n) < 0) n.negate();
        if (flip) n.negate();
        bucket.addVertex(p, n, j / np, i / nt, o.color, infl[i][j]);
      }
    }
    for (let i = 0; i < nt; i++) {
      for (let j = 0; j < np; j++) {
        const a = base + i * (np + 1) + j, b = a + 1, c = a + np + 1, d = c + 1;
        // Winding chosen so the face normal matches the outward normal; flipped for the underside.
        const triN = new THREE.Vector3().crossVectors(
          new THREE.Vector3().subVectors(g[i + 1][j], g[i][j]),
          new THREE.Vector3().subVectors(g[i][j + 1], g[i][j]),
        );
        const nn = new THREE.Vector3(bucket.nrm[a * 3], bucket.nrm[a * 3 + 1], bucket.nrm[a * 3 + 2]);
        if (triN.dot(nn) > 0) bucket.idx.push(a, c, b, b, c, d);
        else bucket.idx.push(a, b, c, b, d, c);
      }
    }
  };
  emitGrid(top, false);
  if (o.thickness > 0.004) {
    // Side walls around the perimeter.
    const ring: { t: THREE.Vector3; b: THREE.Vector3; inf: SkinInfluence[] }[] = [];
    for (let j = 0; j <= np; j++) ring.push({ t: top[0][j], b: bot[0][j], inf: infl[0][j] });
    for (let i = 1; i <= nt; i++) ring.push({ t: top[i][np], b: bot[i][np], inf: infl[i][np] });
    for (let j = np - 1; j >= 0; j--) ring.push({ t: top[nt][j], b: bot[nt][j], inf: infl[nt][j] });
    for (let i = nt - 1; i >= 0; i--) ring.push({ t: top[i][0], b: bot[i][0], inf: infl[i][0] });
    const centerAll = new THREE.Vector3();
    for (const r of ring) centerAll.add(r.t);
    centerAll.divideScalar(ring.length);
    for (let k = 0; k < ring.length - 1; k++) {
      const r0 = ring[k], r1 = ring[k + 1];
      const e = new THREE.Vector3().subVectors(r1.t, r0.t);
      const up = new THREE.Vector3().subVectors(r0.t, r0.b);
      const n = new THREE.Vector3().crossVectors(e, up).normalize();
      const mid = new THREE.Vector3().addVectors(r0.t, r1.t).multiplyScalar(0.5);
      if (n.dot(new THREE.Vector3().subVectors(mid, centerAll)) < 0) n.negate();
      const base = bucket.count;
      bucket.addVertex(r0.b, n, 0, 0, o.color, r0.inf);
      bucket.addVertex(r1.b, n, 1, 0, o.color, r1.inf);
      bucket.addVertex(r0.t, n, 0, 1, o.color, r0.inf);
      bucket.addVertex(r1.t, n, 1, 1, o.color, r1.inf);
      const triN = new THREE.Vector3().crossVectors(new THREE.Vector3().subVectors(r1.b, r0.b), new THREE.Vector3().subVectors(r0.t, r0.b));
      if (triN.dot(n) > 0) bucket.idx.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
      else bucket.idx.push(base, base + 2, base + 1, base + 1, base + 2, base + 3);
    }
  }
}

/** A thin tube following points (conduits, straps, cables). Influences per point. */
export function addTube(
  bucket: MeshBucket,
  pts: THREE.Vector3[],
  radius: number | ((i: number) => number),
  radial: number,
  color: RGB,
  inf: (i: number, p: THREE.Vector3) => SkinInfluence[],
  flatten = 1,
) {
  if (pts.length < 2) return;
  const base = bucket.count;
  const up = new THREE.Vector3(0, 1, 0);
  let prevN: THREE.Vector3 | null = null;
  for (let i = 0; i < pts.length; i++) {
    const T = new THREE.Vector3().subVectors(pts[Math.min(i + 1, pts.length - 1)], pts[Math.max(i - 1, 0)]).normalize();
    let N: THREE.Vector3;
    if (prevN) N = prevN.clone().addScaledVector(T, -prevN.dot(T)).normalize();
    else {
      N = Math.abs(T.dot(up)) > 0.9 ? new THREE.Vector3(1, 0, 0) : up.clone();
      N.addScaledVector(T, -N.dot(T)).normalize();
    }
    prevN = N;
    const B = new THREE.Vector3().crossVectors(T, N).normalize();
    const r = typeof radius === 'function' ? radius(i) : radius;
    const infl = inf(i, pts[i]);
    for (let k = 0; k <= radial; k++) {
      const a = (k / radial) * Math.PI * 2;
      const dir = N.clone().multiplyScalar(Math.cos(a)).addScaledVector(B, Math.sin(a) * flatten);
      const p = pts[i].clone().addScaledVector(dir, r);
      bucket.addVertex(p, dir.normalize(), k / radial, i / (pts.length - 1), color, infl);
    }
  }
  const cols = radial + 1;
  for (let i = 0; i < pts.length - 1; i++) {
    for (let k = 0; k < radial; k++) {
      const a = base + i * cols + k, b = a + 1, c = a + cols, d = c + 1;
      bucket.idx.push(a, b, c, b, d, c);
    }
  }
}

/** Rounded box (pouches, devices, buckles) bound rigidly to one bone. */
export function addRoundBox(
  bucket: MeshBucket,
  center: THREE.Vector3,
  size: THREE.Vector3,
  quat: THREE.Quaternion,
  color: RGB,
  inf: SkinInfluence[],
  radius = 0.25,
  seg = 3,
) {
  const g = new THREE.BoxGeometry(size.x, size.y, size.z, seg, seg, seg);
  const pos = g.getAttribute('position') as THREE.BufferAttribute;
  const half = size.clone().multiplyScalar(0.5);
  const r = Math.min(half.x, half.y, half.z) * radius * 2;
  const inner = half.clone().subScalar(r);
  const p = new THREE.Vector3(), q = new THREE.Vector3(), n = new THREE.Vector3();
  const base = bucket.count;
  const tmpN: THREE.Vector3[] = [];
  const tmpP: THREE.Vector3[] = [];
  for (let i = 0; i < pos.count; i++) {
    p.fromBufferAttribute(pos, i);
    q.set(Math.max(-inner.x, Math.min(inner.x, p.x)), Math.max(-inner.y, Math.min(inner.y, p.y)), Math.max(-inner.z, Math.min(inner.z, p.z)));
    n.subVectors(p, q);
    if (n.lengthSq() < 1e-10) n.set(0, 1, 0);
    n.normalize();
    const out = q.clone().addScaledVector(n, r);
    tmpP.push(out.applyQuaternion(quat).add(center));
    tmpN.push(n.clone().applyQuaternion(quat));
  }
  const uv = g.getAttribute('uv') as THREE.BufferAttribute;
  for (let i = 0; i < pos.count; i++) bucket.addVertex(tmpP[i], tmpN[i], uv.getX(i), uv.getY(i), color, inf);
  const idx = g.getIndex()!;
  for (let i = 0; i < idx.count; i++) bucket.idx.push(base + idx.getX(i));
  g.dispose();
}

/** Ellipsoid with optional displacement; returns nothing, writes to bucket. */
export function addEllipsoid(
  bucket: MeshBucket,
  center: THREE.Vector3,
  radii: THREE.Vector3,
  quat: THREE.Quaternion,
  color: RGB,
  inf: SkinInfluence[] | ((p: THREE.Vector3) => SkinInfluence[]),
  wSeg = 12,
  hSeg = 8,
  displace?: (dir: THREE.Vector3) => number,
  uvMode: 'sphere' | 'front' = 'sphere',
) {
  const base = bucket.count;
  const pts: THREE.Vector3[][] = [];
  for (let iy = 0; iy <= hSeg; iy++) {
    const v = iy / hSeg;
    const theta = v * Math.PI; // 0 top .. PI bottom
    const row: THREE.Vector3[] = [];
    for (let ix = 0; ix <= wSeg; ix++) {
      const u = ix / wSeg;
      const phi = u * Math.PI * 2 - Math.PI; // -PI..PI with 0 at front (+Z)
      const dir = new THREE.Vector3(Math.sin(theta) * Math.sin(phi), Math.cos(theta), Math.sin(theta) * Math.cos(phi));
      const d = displace ? displace(dir) : 0;
      const p = new THREE.Vector3(dir.x * radii.x, dir.y * radii.y, dir.z * radii.z);
      const len = p.length();
      if (len > 0) p.multiplyScalar((len + d) / len);
      row.push(p);
    }
    pts.push(row);
  }
  for (let iy = 0; iy <= hSeg; iy++) {
    for (let ix = 0; ix <= wSeg; ix++) {
      const p = pts[iy][ix];
      const du = new THREE.Vector3().subVectors(pts[iy][ix === wSeg ? 1 : ix + 1], pts[iy][ix === 0 ? wSeg - 1 : ix - 1]);
      const dv = new THREE.Vector3().subVectors(pts[Math.min(hSeg, iy + 1)][ix], pts[Math.max(0, iy - 1)][ix]);
      let n = new THREE.Vector3().crossVectors(du, dv);
      if (n.lengthSq() < 1e-14) n = p.clone();
      n.normalize();
      if (n.dot(p) < 0) n.negate();
      const wp = p.clone().applyQuaternion(quat).add(center);
      const wn = n.applyQuaternion(quat);
      const u = uvMode === 'sphere' ? ix / wSeg : 0.5 + p.x / (radii.x * 2.2);
      const v = uvMode === 'sphere' ? 1 - iy / hSeg : 0.5 + p.y / (radii.y * 2.2);
      bucket.addVertex(wp, wn, u, v, color, typeof inf === 'function' ? inf(wp) : inf);
    }
  }
  const cols = wSeg + 1;
  for (let iy = 0; iy < hSeg; iy++) {
    for (let ix = 0; ix < wSeg; ix++) {
      const a = base + iy * cols + ix, b = a + 1, c = a + cols, d = c + 1;
      if (iy !== 0) bucket.idx.push(a, c, b);
      if (iy !== hSeg - 1) bucket.idx.push(b, c, d);
    }
  }
}

export const one = (bone: number): SkinInfluence[] => [{ bone, w: 1 }];
export const mix2 = (a: number, b: number, t: number): SkinInfluence[] => [{ bone: a, w: 1 - t }, { bone: b, w: t }];

/** Partial sphere (theta from the +Y pole), e.g. eyelids. `edge` tints the rim row at theta0 or theta1 (lash line). */
export function addSphereCap(bucket: MeshBucket, center: THREE.Vector3, radius: number, theta0: number, theta1: number, quat: THREE.Quaternion, color: RGB, inf: SkinInfluence[], wSeg = 14, hSeg = 5, phiRange = Math.PI * 2, edge?: { color: RGB; at: 0 | 1 }) {
  const base = bucket.count;
  for (let iy = 0; iy <= hSeg; iy++) {
    const th = theta0 + ((theta1 - theta0) * iy) / hSeg;
    const col = edge && iy === (edge.at ? hSeg : 0) ? edge.color : color;
    for (let ix = 0; ix <= wSeg; ix++) {
      const ph = -phiRange / 2 + (phiRange * ix) / wSeg;
      const n = new THREE.Vector3(Math.sin(th) * Math.sin(ph), Math.cos(th), Math.sin(th) * Math.cos(ph)).applyQuaternion(quat);
      bucket.addVertex(center.clone().addScaledVector(n, radius), n, ix / wSeg, iy / hSeg, col, inf);
    }
  }
  const cols = wSeg + 1;
  for (let iy = 0; iy < hSeg; iy++) {
    for (let ix = 0; ix < wSeg; ix++) {
      const a = base + iy * cols + ix, b = a + 1, c = a + cols, d = c + 1;
      bucket.idx.push(a, c, b, b, c, d);
    }
  }
}
