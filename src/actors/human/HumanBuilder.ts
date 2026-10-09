import * as THREE from 'three';
import { lerp, smoothstep } from '../../core/MathUtil';
import { lin, mixRGB, scaleRGB } from '../../render/TexGen';
import { EYE, HeadShape, type FaceSpec } from './HeadShape';
import type { BodySpec, Rig } from './HumanRig';
import { addEllipsoid, addPatch, addRoundBox, addSphereCap, addTube, LoftSurface, MeshBucket, mix2, one, type ProfileKey, type RGB, type SkinInfluence } from './MeshKit';

export type MatKey = 'skin' | 'face' | 'cloth' | 'armor' | 'metal' | 'glow' | 'hair' | 'hairfx' | 'eye';
export const MAT_KEYS: MatKey[] = ['skin', 'face', 'cloth', 'armor', 'metal', 'glow', 'hair', 'hairfx', 'eye'];

export type HairStyle = 'short' | 'tied' | 'buzz' | 'swept' | 'bob' | 'hood' | 'none' | 'long' | 'bun' | 'undercut' | 'curly';
export const HAIR_STYLES: HairStyle[] = ['short', 'swept', 'undercut', 'buzz', 'curly', 'bob', 'tied', 'bun', 'long', 'none'];
export type Extra = 'headset' | 'scarf' | 'backpack' | 'satchel' | 'goggles';

export interface Look {
  id: string;
  body: BodySpec;
  skin: string;
  hair: string;
  eyes: string;
  face: FaceSpec;
  hairStyle: HairStyle;
  top: {
    kind: 'jacket' | 'suit' | 'coat' | 'poncho';
    color: string;
    color2: string;
    /** Hem height on the 1.8 m reference body. */
    hem: number;
    collar: 'high' | 'low' | 'none';
    pattern: 'kael' | 'lyra' | 'plain' | 'stripe';
    zip: 'diag' | 'center' | 'none';
  };
  legs: { color: string; color2?: string; pattern?: 'lyra' | 'plain' | 'cargo' };
  boots: { color: string; top: number; sole: string };
  gloves: { color: string } | null;
  armor?: {
    color: string;
    shoulderL?: number;
    shoulderR?: number;
    chest?: 'L' | 'R' | 'both';
    forearmL?: boolean;
    forearmR?: boolean;
    knees?: boolean;
  };
  belt?: { color: string; pouches: number };
  harness?: { color: string };
  iface?: 'R' | 'L';
  glow?: { color: string; color2?: string; pattern: 'kael' | 'lyra' | 'none' };
  backpack?: boolean;
  extras?: Extra[];
}

interface Detail { radial: number; ringMul: number; head: [number, number]; details: number }

const DETAIL: Detail[] = [
  { radial: 22, ringMul: 1, head: [44, 32], details: 2 },
  { radial: 12, ringMul: 0.5, head: [22, 16], details: 1 },
  { radial: 7, ringMul: 0.28, head: [12, 9], details: 0 },
];

/** Profile keys authored by reference-body height (y) are converted to loft parameter t. */
function keysY(y0: number, y1: number, ks: (Omit<ProfileKey, 't'> & { y: number })[], s: number, wx = 1, wz = 1): ProfileKey[] {
  return ks.map((k) => ({
    t: (k.y - y0) / (y1 - y0),
    rx: k.rx * s * wx,
    rxL: k.rxL !== undefined ? k.rxL * s * wx : undefined,
    rzF: k.rzF * s * wz,
    rzB: (k.rzB ?? k.rzF) * s * wz,
    ox: (k.ox ?? 0) * s,
    oz: (k.oz ?? 0) * s,
    n: k.n,
  }));
}
function keysT(ks: ProfileKey[], s: number, wx = 1, wz = wx): ProfileKey[] {
  return ks.map((k) => ({
    t: k.t,
    rx: k.rx * s * wx,
    rxL: k.rxL !== undefined ? k.rxL * s * wx : undefined,
    rzF: k.rzF * s * wz,
    rzB: (k.rzB ?? k.rzF) * s * wz,
    ox: (k.ox ?? 0) * s,
    oz: (k.oz ?? 0) * s,
    n: k.n,
  }));
}

/** Outward surface normal of a loft at (t, phi). */
function surfNormal(surf: LoftSurface, t: number, phi: number): THREE.Vector3 {
  const p0 = surf.point(t, phi);
  const p1 = surf.point(t, phi + 0.02);
  const p2 = surf.point(Math.min(1, t + 0.01), phi);
  const p3 = surf.point(Math.max(0, t - 0.01), phi);
  const n = new THREE.Vector3().crossVectors(new THREE.Vector3().subVectors(p1, p0), new THREE.Vector3().subVectors(p2, p3)).normalize();
  const c = surf.frameAt(t).c;
  if (n.dot(new THREE.Vector3().subVectors(p0, c)) < 0) n.negate();
  return n;
}

/** Quaternion that points local +Z along `n` with local +Y as close to world up as possible. */
function faceQuat(n: THREE.Vector3, up = new THREE.Vector3(0, 1, 0)): THREE.Quaternion {
  const z = n.clone().normalize();
  const x = new THREE.Vector3().crossVectors(up, z);
  if (x.lengthSq() < 1e-6) x.set(1, 0, 0);
  x.normalize();
  const y = new THREE.Vector3().crossVectors(z, x).normalize();
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z));
}

/** Points sampled along a path on a surface (for straps and conduits). */
function surfPath(surf: LoftSurface, a: [number, number], b: [number, number], n: number, offset: number): { p: THREE.Vector3; t: number }[] {
  const out: { p: THREE.Vector3; t: number }[] = [];
  for (let i = 0; i <= n; i++) {
    const k = i / n;
    const t = lerp(a[0], b[0], k);
    const phi = lerp(a[1], b[1], k);
    out.push({ p: surf.point(t, phi, offset), t });
  }
  return out;
}

export interface BuildResult {
  buckets: Map<MatKey, MeshBucket>;
  /** Named attachment points (bone + local offset) for sockets. */
  sockets: Record<string, { bone: string; pos: THREE.Vector3 }>;
  /** Eye mesh centres (for blinking). */
  eyes: THREE.Vector3[];
}

export function buildHuman(look: Look, rig: Rig, lod: number): BuildResult {
  const det = DETAIL[Math.min(2, Math.max(0, lod))];
  const buckets = new Map<MatKey, MeshBucket>();
  const bk = (k: MatKey) => {
    let b = buckets.get(k);
    if (!b) {
      b = new MeshBucket();
      buckets.set(k, b);
    }
    return b;
  };
  const s = rig.s;
  const J = rig.j;
  const I = rig.index;
  const spec = rig.spec;
  const fem = spec.build === 'female';
  const bulk = spec.bulk;
  const V = (x: number, y: number, z: number) => new THREE.Vector3(x * s, y * s, z * s);
  const R = (n: number) => Math.max(2, Math.round(n * det.ringMul));
  const sockets: BuildResult['sockets'] = {};
  const eyes: THREE.Vector3[] = [];

  const C = {
    skin: lin(look.skin),
    top: lin(look.top.color),
    top2: lin(look.top.color2),
    legs: lin(look.legs.color),
    legs2: lin(look.legs.color2 ?? look.legs.color),
    boots: lin(look.boots.color),
    sole: lin(look.boots.sole),
    glove: look.gloves ? lin(look.gloves.color) : lin(look.skin),
    armor: lin(look.armor?.color ?? '#45484d'),
    belt: lin(look.belt?.color ?? '#3a3530'),
    harness: lin(look.harness?.color ?? '#2a2b30'),
    hair: lin(look.hair),
    glow: lin(look.glow?.color ?? '#4fb4ff'),
    glow2: lin(look.glow?.color2 ?? look.glow?.color ?? '#4fb4ff'),
    metal: lin('#8a8f96'),
    white: [1, 1, 1] as RGB,
  };
  const gloveMat: MatKey = look.gloves ? 'cloth' : 'skin';

  // ---------------------------------------------------------------- Head
  const hs = spec.headScale * (fem ? 0.985 : 1) * (spec.build === 'child' ? 1.12 : 1) * s;
  const shape = new HeadShape(look.face, hs);
  const hc = J.headCenter;
  {
    const [wSeg, hSeg] = det.head;
    const b = bk('face');
    const base = b.count;
    const grid: THREE.Vector3[][] = [];
    // Normals come from the surface without the hidden eye recess, so shading around the eyelid patches
    // matches the patches exactly.
    const ngrid: THREE.Vector3[][] = [];
    const dir = new THREE.Vector3();
    for (let iy = 0; iy <= hSeg; iy++) {
      const theta = (iy / hSeg) * Math.PI;
      const row: THREE.Vector3[] = [];
      const nrow: THREE.Vector3[] = [];
      for (let ix = 0; ix <= wSeg; ix++) {
        const phi = (ix / wSeg) * Math.PI * 2 - Math.PI;
        dir.set(Math.sin(theta) * Math.sin(phi), Math.cos(theta), Math.sin(theta) * Math.cos(phi));
        row.push(shape.sculpt(dir).add(hc));
        nrow.push(shape.sculpt(dir, new THREE.Vector3(), true).add(hc));
      }
      grid.push(row);
      ngrid.push(nrow);
    }
    for (let iy = 0; iy <= hSeg; iy++) {
      for (let ix = 0; ix <= wSeg; ix++) {
        const p = grid[iy][ix];
        const du = new THREE.Vector3().subVectors(ngrid[iy][ix === wSeg ? 1 : ix + 1], ngrid[iy][ix === 0 ? wSeg - 1 : ix - 1]);
        const dv = new THREE.Vector3().subVectors(ngrid[Math.min(hSeg, iy + 1)][ix], ngrid[Math.max(0, iy - 1)][ix]);
        const n = new THREE.Vector3().crossVectors(du, dv);
        if (n.lengthSq() < 1e-14) n.subVectors(p, hc);
        n.normalize();
        if (n.dot(new THREE.Vector3().subVectors(p, hc)) < 0) n.negate();
        const low = smoothstep(hc.y - 0.06 * s, hc.y - 0.12 * s, p.y);
        const inf = low > 0 ? mix2(I.head, I.neck, low * 0.5) : one(I.head);
        b.addVertex(p, n, ix / wSeg, 1 - iy / hSeg, C.white, inf);
      }
    }
    const cols = wSeg + 1;
    for (let iy = 0; iy < hSeg; iy++) {
      for (let ix = 0; ix < wSeg; ix++) {
        const a = base + iy * cols + ix, bb = a + 1, c = a + cols, d = c + 1;
        if (iy !== 0) b.idx.push(a, c, bb);
        if (iy !== hSeg - 1) b.idx.push(bb, c, d);
      }
    }
    // Eyes: an eyeball plus an eyelid patch with an almond opening. The patch wraps the eyeball near
    // the opening and blends into the face further out; it samples the face texture with the head's own
    // UV mapping so there is no seam, and the head surface behind it is recessed out of sight.
    if (det.details >= 1 || lod === 0) {
      const eyeR = 0.0118 * hs * (fem ? 1.03 : 1);
      const lidR = eyeR + 0.0008 * hs;
      const N = lod === 0 ? 14 : 8; // samples along each lid
      const K = lod === 0 ? 8 : 4; // rings from the opening out to the blend edge
      const lash: RGB = [C.hair[0] * 0.35 + 0.01, C.hair[1] * 0.35 + 0.01, C.hair[2] * 0.35 + 0.012];
      const uvOf = (d: THREE.Vector3): [number, number] => [(Math.atan2(d.x, d.z) + Math.PI) / (Math.PI * 2), 1 - Math.acos(Math.max(-1, Math.min(1, d.y))) / Math.PI];
      const nd = new THREE.Vector3();
      for (const sx of [1, -1]) {
        const np = shape.frontPoint(sx * EYE.x, EYE.y, true);
        const C0 = np.clone().add(new THREE.Vector3(0, 0, -(eyeR - 0.0038 * hs)));
        // Almond opening (offsets from the eye centre); t runs from the inner corner (-1) to the outer (+1).
        const w = 0.0113 * hs, hu = 0.0058 * hs, hl = 0.0049 * hs, tilt = 0.0009 * hs;
        const rim: [number, number][] = [];
        for (let i = 0; i <= N; i++) {
          const t = -1 + (2 * i) / N;
          rim.push([sx * t * w, hu * Math.pow(1 - t * t, 0.7) * (1 - 0.12 * t) + tilt * t]);
        }
        for (let i = N - 1; i >= 1; i--) {
          const t = -1 + (2 * i) / N;
          rim.push([sx * t * w, -hl * Math.pow(1 - t * t, 0.85) * (1 + 0.1 * t) + tilt * t]);
        }
        const M = rim.length;
        const rxo = 0.022 * hs, ryo = 0.0172 * hs, oy = 0.0015 * hs;
        const ne = 0.0005 * hs;
        const natNormal = (X: number, Y: number) => {
          const px0 = shape.frontPoint((X - ne) / hs, Y / hs, true), px1 = shape.frontPoint((X + ne) / hs, Y / hs, true);
          const py0 = shape.frontPoint(X / hs, (Y - ne) / hs, true), py1 = shape.frontPoint(X / hs, (Y + ne) / hs, true);
          return new THREE.Vector3().crossVectors(px1.sub(px0), py1.sub(py0)).normalize();
        };
        // Ring -1 tucks the lid margin onto the eyeball; rings 0..K run from the margin to the blend edge.
        const grid: { p: THREE.Vector3; uv: [number, number]; u: number; nn: THREE.Vector3 | null }[][] = [];
        for (let k = -1; k <= K; k++) {
          const row: { p: THREE.Vector3; uv: [number, number]; u: number; nn: THREE.Vector3 | null }[] = [];
          for (let i = 0; i < M; i++) {
            const [bx, by] = rim[i];
            const a = Math.atan2(by - oy, bx);
            const ox = Math.cos(a) * rxo, oyy = oy + Math.sin(a) * ryo;
            const f = k < 0 ? 0 : Math.pow(k / K, 1.25);
            let dx = lerp(bx, ox, f), dy = lerp(by, oyy, f);
            if (k < 0) { const l = Math.hypot(dx, dy); dx *= 1 - 0.0005 * hs / l; dy *= 1 - 0.0005 * hs / l; }
            const X = C0.x + dx, Y = C0.y + dy;
            const rho = Math.hypot(dx, dy);
            const nat = shape.frontPoint(X / hs, Y / hs, true, nd);
            let z: number;
            let u = 0;
            if (k < 0) z = C0.z + Math.sqrt(Math.max(0, eyeR * eyeR - rho * rho)) + 0.0002 * hs;
            else {
              // The outer rings lie on the natural face surface (a hair in front of the coarser head mesh).
              const zLid = C0.z + Math.sqrt(Math.max(0, lidR * lidR - rho * rho));
              u = Math.max(smoothstep(0, 0.62, k / K), smoothstep(lidR * 0.82, lidR, rho));
              // Never sink behind the (possibly recessed) head surface, so the head can't poke through.
              const floor = shape.frontPoint(X / hs, Y / hs).z + lerp(0.0004, 0.00025, k / K) * hs;
              const a0 = lerp(zLid, nat.z + 0.00025 * hs, u), kk = 0.0012 * hs;
              z = 0.5 * (a0 + floor + Math.sqrt((a0 - floor) ** 2 + kk * kk));
              u = smoothstep(0.7, 1, k / K);
            }
            row.push({ p: new THREE.Vector3(X, Y, z).add(hc), uv: uvOf(nd), u, nn: u > 0 ? natNormal(X, Y) : null });
          }
          grid.push(row);
        }
        const b = bk('face');
        const base = b.count;
        const centerW = C0.clone().add(hc);
        for (let k = 0; k < grid.length; k++) {
          for (let i = 0; i < M; i++) {
            const p = grid[k][i].p;
            const du = new THREE.Vector3().subVectors(grid[k][(i + 1) % M].p, grid[k][(i - 1 + M) % M].p);
            const dv = new THREE.Vector3().subVectors(grid[Math.min(grid.length - 1, k + 1)][i].p, grid[Math.max(0, k - 1)][i].p);
            const n = new THREE.Vector3().crossVectors(du, dv).normalize();
            if (n.z < 0 && n.dot(new THREE.Vector3().subVectors(p, centerW)) < 0) n.negate();
            if (n.z < -0.2) n.negate();
            const g = grid[k][i];
            if (g.nn) n.lerp(g.nn, g.u).normalize();
            b.addVertex(p, n, g.uv[0], g.uv[1], C.white, one(I.head));
          }
        }
        for (let k = 0; k < grid.length - 1; k++) {
          for (let i = 0; i < M; i++) {
            const a = base + k * M + i, bb = base + k * M + ((i + 1) % M), c = a + M, d = bb + M;
            // Winding: the rim loop runs counter-clockwise seen from the front for sx=+1, clockwise for sx=-1.
            if (sx > 0) b.idx.push(a, bb, c, bb, d, c);
            else b.idx.push(a, c, bb, bb, c, d);
          }
        }
        // Upper lash line: a thin dark ribbon over the lid margin.
        const sk = bk('skin');
        const lbase = sk.count;
        for (let i = 0; i <= N; i++) {
          const p0 = grid[0][i].p, p1 = grid[1][i].p;
          const out = new THREE.Vector3().subVectors(p1, p0).normalize();
          const nrm = new THREE.Vector3().subVectors(p0, centerW).normalize();
          const edgeT = Math.abs(-1 + (2 * i) / N);
          const thick = 0.0011 * hs * (1 - edgeT * edgeT * 0.7);
          sk.addVertex(p0.clone().addScaledVector(nrm, 0.0002 * hs), nrm, 0, 0, lash, one(I.head));
          sk.addVertex(p0.clone().addScaledVector(out, thick).addScaledVector(nrm, 0.00035 * hs), nrm, 0, 1, lash, one(I.head));
        }
        for (let i = 0; i < N; i++) {
          const a = lbase + i * 2, c = a + 2;
          if (sx > 0) sk.idx.push(a, c, a + 1, a + 1, c, c + 1);
          else sk.idx.push(a, a + 1, c, a + 1, c + 1, c);
        }
        eyes.push(centerW.clone());
        addEllipsoid(bk('eye'), centerW, new THREE.Vector3(eyeR, eyeR, eyeR), new THREE.Quaternion(), C.white, one(I.head), lod === 0 ? 18 : 10, lod === 0 ? 14 : 8);
      }
    }
    // Ears
    if (det.details >= 1) {
      for (const sx of [1, -1]) {
        const c = hc.clone().add(new THREE.Vector3(sx * (shape.r.x - 0.0035 * s), -0.008 * s, -0.012 * s));
        const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(0.1, sx * 0.35, sx * 0.08));
        addEllipsoid(bk('skin'), c, new THREE.Vector3(0.0085, 0.026, 0.016).multiplyScalar(hs / s), q, C.skin, one(I.head), 10, 8);
      }
    }
    sockets.head = { bone: 'head', pos: hc.clone() };
    sockets.eyes = { bone: 'head', pos: hc.clone().add(new THREE.Vector3(0, 0.008 * s, 0.08 * s)) };
  }

  // ---------------------------------------------------------------- Neck
  {
    const nw = fem ? 0.86 : 1;
    const surf = new LoftSurface({
      chain: { points: [V(0, 1.4, -0.032), J.head.clone(), hc.clone().add(V(0, -0.02, -0.022))], bones: [I.neck, I.head], blend: 0.03 * s },
      profile: keysT([
        { t: 0, rx: 0.068, rzF: 0.066, rzB: 0.068 },
        { t: 0.55, rx: 0.06, rzF: 0.056, rzB: 0.062 },
        { t: 1, rx: 0.056, rzF: 0.05, rzB: 0.06 },
      ], s, nw * bulk),
      rings: R(6),
      radial: det.radial,
      color: C.skin,
    });
    surf.build(bk('skin'));
  }

  // ---------------------------------------------------------------- Torso / top garment
  const hemY = look.top.hem;
  const torsoTop = fem ? 1.502 : 1.515;
  const torsoBottom = Math.min(hemY, fem ? 0.86 : 0.9);
  const sw = spec.shoulderWidth, hw = spec.hipWidth;
  const torsoKeysMale = [
    { y: 0.74, rx: 0.176, rzF: 0.125, rzB: 0.132, n: 2.3 },
    { y: 0.82, rx: 0.172, rzF: 0.121, rzB: 0.128, n: 2.3 },
    { y: 0.92, rx: 0.166, rzF: 0.117, rzB: 0.122 },
    { y: 1.0, rx: 0.156, rzF: 0.112, rzB: 0.112 },
    { y: 1.1, rx: 0.16, rzF: 0.118, rzB: 0.106 },
    { y: 1.22, rx: 0.176 * (0.85 + 0.15 * sw), rzF: 0.132, rzB: 0.114, oz: 0.008 },
    { y: 1.33, rx: 0.188 * sw, rzF: 0.128, rzB: 0.118 },
    { y: 1.418, rx: 0.2 * sw, rzF: 0.112, rzB: 0.114, n: 2.7 },
    { y: 1.468, rx: 0.182 * sw, rzF: 0.092, rzB: 0.098, n: 3.0 },
    { y: 1.497, rx: 0.105, rzF: 0.068, rzB: 0.074, n: 2.4 },
    { y: 1.515, rx: 0.07, rzF: 0.06, rzB: 0.064 },
  ];
  const torsoKeysFemale = [
    { y: 0.74, rx: 0.168, rzF: 0.112, rzB: 0.13, n: 2.3 },
    { y: 0.86, rx: 0.158, rzF: 0.104, rzB: 0.122 },
    { y: 0.95, rx: 0.16 * hw, rzF: 0.102, rzB: 0.118 },
    { y: 1.04, rx: 0.128, rzF: 0.09, rzB: 0.09 },
    { y: 1.12, rx: 0.132, rzF: 0.096, rzB: 0.09 },
    { y: 1.2, rx: 0.144, rzF: 0.114, rzB: 0.096, oz: 0.006 },
    { y: 1.255, rx: 0.15, rzF: 0.128, rzB: 0.1, oz: 0.004 },
    { y: 1.32, rx: 0.158 * sw, rzF: 0.116, rzB: 0.104 },
    { y: 1.408, rx: 0.176 * sw, rzF: 0.097, rzB: 0.101, n: 2.6 },
    { y: 1.455, rx: 0.162 * sw, rzF: 0.082, rzB: 0.088, n: 2.9 },
    { y: 1.484, rx: 0.092, rzF: 0.06, rzB: 0.065, n: 2.4 },
    { y: 1.502, rx: 0.06, rzF: 0.053, rzB: 0.057 },
  ];
  const tk = (fem ? torsoKeysFemale : torsoKeysMale).filter((k) => k.y >= torsoBottom - 0.06 || k === (fem ? torsoKeysFemale : torsoKeysMale)[0]);
  const coatExtra = look.top.kind === 'coat' ? 1.08 : look.top.kind === 'poncho' ? 1.12 : look.top.kind === 'jacket' ? 1.03 : 1;
  // Clamp the first key to the hem height.
  const torsoKeys = keysY(torsoBottom, torsoTop, tk.map((k, i) => (i === 0 ? { ...k, y: Math.min(k.y, torsoBottom) } : k)), s, bulk * coatExtra, bulk * coatExtra);
  const torsoChain = [V(0, torsoBottom, 0.0), J.hips.clone(), J.spine.clone(), J.chest.clone(), V(0, torsoTop, J.neck.z / s)];
  const shoulderInfl = (p: THREE.Vector3): SkinInfluence[] => {
    const ax = Math.abs(p.x);
    const side = p.x > 0 ? 'L' : 'R';
    const w = smoothstep(0.1 * s, 0.19 * s, ax) * smoothstep(1.32 * s, 1.455 * s, p.y) * 0.75;
    const res: SkinInfluence[] = [];
    if (w > 0) {
      res.push({ bone: I['clavicle_' + side], w: w * 0.45 }, { bone: I['upperarm_' + side], w: w * 0.55 });
    }
    // Hem follows the thighs a little so legs don't punch through when walking.
    if (p.y < 0.93 * s) {
      const wl = smoothstep(0.93 * s, 0.78 * s, p.y) * 0.6 * smoothstep(0.0, 0.07 * s, ax);
      if (wl > 0) res.push({ bone: I['thigh_' + side], w: wl });
    }
    const wn = smoothstep(1.485 * s, 1.515 * s, p.y) * 0.6;
    if (wn > 0) res.push({ bone: I.neck, w: wn });
    return res;
  };
  const torsoColor = (t: number, phi: number, p: THREE.Vector3): RGB => {
    const pat = look.top.pattern;
    const y = p.y / s;
    const cphi = Math.cos(phi), sphi = Math.sin(phi);
    if (pat === 'kael') {
      // Darker side panels and a subtle yoke across the shoulders.
      const sidePanel = smoothstep(0.75, 0.92, Math.abs(cphi)) * smoothstep(1.34, 1.3, y);
      const yoke = smoothstep(1.33, 1.37, y);
      let c = mixRGB(C.top, C.top2, sidePanel * 0.9);
      c = mixRGB(c, scaleRGB(C.top, 1.18), yoke * 0.6);
      return c;
    }
    if (pat === 'lyra') {
      // Asymmetric: violet panel down the left flank and across the right shoulder blade.
      const leftFlank = smoothstep(0.35, 0.7, cphi) * smoothstep(0.95, 1.02, y) * smoothstep(1.38, 1.3, y);
      const rightBack = smoothstep(0.2, 0.55, -cphi) * smoothstep(0.1, 0.5, -sphi) * smoothstep(1.24, 1.3, y);
      const waist = smoothstep(1.06, 1.04, y) * smoothstep(0.98, 1.0, y);
      return mixRGB(mixRGB(C.top, C.top2, Math.max(leftFlank, rightBack) * 0.95), scaleRGB(C.top, 0.7), waist);
    }
    if (pat === 'stripe') {
      const stripe = smoothstep(0.08, 0.0, Math.abs(y - 1.2)) * 0.9;
      return mixRGB(C.top, C.top2, stripe);
    }
    return C.top;
  };
  const torso = new LoftSurface({
    chain: { points: torsoChain, bones: [I.hips, I.hips, I.spine, I.chest], blend: 0.07 * s, extra: shoulderInfl },
    profile: torsoKeys,
    rings: R(28),
    radial: det.radial + 6,
    color: torsoColor,
    uvScale: 5,
  });
  torso.build(bk('cloth'));
  const torsoT = (y: number) => (y - torsoBottom) / (torsoTop - torsoBottom);

  // ---------------------------------------------------------------- Pelvis
  const pelvisKeys = fem
    ? [
        { y: 0.82, rx: 0.12, rzF: 0.085, rzB: 0.1 },
        { y: 0.88, rx: 0.152 * hw, rzF: 0.1, rzB: 0.124 },
        { y: 0.955, rx: 0.168 * hw, rzF: 0.103, rzB: 0.126 },
        { y: 1.02, rx: 0.148, rzF: 0.094, rzB: 0.106 },
        { y: 1.08, rx: 0.13, rzF: 0.09, rzB: 0.092 },
      ]
    : [
        { y: 0.8, rx: 0.13, rzF: 0.09, rzB: 0.1 },
        { y: 0.86, rx: 0.156 * hw, rzF: 0.101, rzB: 0.116 },
        { y: 0.95, rx: 0.164 * hw, rzF: 0.107, rzB: 0.12 },
        { y: 1.02, rx: 0.157, rzF: 0.108, rzB: 0.112 },
        { y: 1.08, rx: 0.153, rzF: 0.11, rzB: 0.106 },
      ];
  const pY0 = pelvisKeys[0].y, pY1 = pelvisKeys[pelvisKeys.length - 1].y;
  const pelvis = new LoftSurface({
    chain: {
      points: [V(0, pY0, 0), J.hips.clone(), V(0, pY1, -0.008)],
      bones: [I.hips, I.hips],
      extra: (p) => {
        const w = smoothstep(0.94 * s, 0.82 * s, p.y) * 0.85 * smoothstep(0.0, 0.05 * s, Math.abs(p.x));
        return w > 0 ? [{ bone: I[p.x > 0 ? 'thigh_L' : 'thigh_R'], w }] : [];
      },
    },
    profile: keysY(pY0, pY1, pelvisKeys, s, bulk, bulk),
    rings: R(10),
    radial: det.radial + 4,
    capStart: true,
    color: (t, phi, p) => {
      if (look.legs.pattern === 'lyra') return C.legs;
      return C.legs;
    },
    uvScale: 5,
  });
  pelvis.build(bk('cloth'));

  // ---------------------------------------------------------------- Legs
  const legSurf: Record<string, LoftSurface> = {};
  for (const side of ['L', 'R'] as const) {
    const sx = side === 'L' ? 1 : -1;
    const top = J['thigh_' + side].clone().add(V(-sx * 0.004, 0.065, 0.004));
    const keys = fem
      ? [
          { t: 0, rx: 0.094, rzF: 0.092, rzB: 0.106 },
          { t: 0.15, rx: 0.087, rzF: 0.086, rzB: 0.096 },
          { t: 0.33, rx: 0.073, rzF: 0.073, rzB: 0.074 },
          { t: 0.5, rx: 0.056, rzF: 0.058, rzB: 0.056 },
          { t: 0.56, rx: 0.053, rzF: 0.056, rzB: 0.054 },
          { t: 0.65, rx: 0.055, rzF: 0.051, rzB: 0.066 },
          { t: 0.78, rx: 0.048, rzF: 0.045, rzB: 0.054 },
          { t: 0.92, rx: 0.04, rzF: 0.039, rzB: 0.041 },
          { t: 1, rx: 0.039, rzF: 0.038, rzB: 0.04 },
        ]
      : [
          { t: 0, rx: 0.093, rzF: 0.096, rzB: 0.104 },
          { t: 0.15, rx: 0.089, rzF: 0.089, rzB: 0.095 },
          { t: 0.33, rx: 0.078, rzF: 0.078, rzB: 0.077 },
          { t: 0.5, rx: 0.062, rzF: 0.064, rzB: 0.06 },
          { t: 0.56, rx: 0.058, rzF: 0.062, rzB: 0.058 },
          { t: 0.65, rx: 0.06, rzF: 0.056, rzB: 0.07 },
          { t: 0.78, rx: 0.054, rzF: 0.05, rzB: 0.06 },
          { t: 0.92, rx: 0.046, rzF: 0.044, rzB: 0.046 },
          { t: 1, rx: 0.044, rzF: 0.043, rzB: 0.044 },
        ];
    const cargo = look.legs.pattern === 'cargo';
    const surf = new LoftSurface({
      chain: { points: [top, J['shin_' + side].clone(), J['foot_' + side].clone().add(V(0, 0.02, 0))], bones: [I['thigh_' + side], I['shin_' + side]], blend: 0.06 * s },
      profile: keysT(keys, s, bulk),
      rings: R(26),
      radial: det.radial,
      color: (t, phi) => {
        const c = Math.cos(phi);
        if (look.legs.pattern === 'lyra' && side === 'R') {
          const stripe = smoothstep(0.82, 0.95, -c);
          return mixRGB(C.legs, C.legs2, stripe);
        }
        if (look.legs.pattern === 'lyra' && side === 'L') {
          const panel = smoothstep(0.45, 0.62, t) * smoothstep(0.62, 0.45, t) * 0 + smoothstep(0.7, 0.9, Math.sin(phi)) * smoothstep(0.42, 0.46, t) * smoothstep(0.62, 0.58, t);
          return mixRGB(C.legs, C.legs2, panel);
        }
        return C.legs;
      },
      displace: cargo ? (t, phi) => (Math.abs(Math.cos(phi) * sx - 1) < 0.35 && t > 0.22 && t < 0.38 ? 0.012 * s : 0) : undefined,
      uvScale: 5,
    });
    surf.build(bk('cloth'));
    legSurf[side] = surf;
  }

  // ---------------------------------------------------------------- Boots
  for (const side of ['L', 'R'] as const) {
    const sx = side === 'L' ? 1 : -1;
    const hx = J['foot_' + side].x;
    const foot = new LoftSurface({
      chain: { points: [V(hx / s, 0.042, -0.082), V(hx / s + sx * 0.002, 0.042, 0.06), V(hx / s + sx * 0.006, 0.04, 0.172 * (fem ? 0.93 : 1))], bones: [I['foot_' + side], I['foot_' + side]] },
      fwd: new THREE.Vector3(0, 1, 0),
      side: new THREE.Vector3(1, 0, 0),
      profile: keysT([
        { t: 0, rx: 0.04, rzF: 0.055, rzB: 0.042, n: 2.6 },
        { t: 0.12, rx: 0.046, rzF: 0.066, rzB: 0.042, n: 3.0 },
        { t: 0.42, rx: 0.051, rzF: 0.058, rzB: 0.042, n: 3.2 },
        { t: 0.7, rx: 0.05, rzF: 0.04, rzB: 0.042, n: 3.0 },
        { t: 0.9, rx: 0.042, rzF: 0.03, rzB: 0.041, n: 2.6 },
        { t: 1, rx: 0.022, rzF: 0.016, rzB: 0.03, n: 2.2 },
      ], s, fem ? 0.9 : 1),
      rings: R(12),
      radial: det.radial,
      capStart: true,
      capEnd: true,
      color: (t, phi, p) => (p.y < 0.016 * s ? C.sole : t > 0.78 && Math.sin(phi) > -0.2 ? scaleRGB(C.boots, 1.15) : C.boots),
    });
    foot.build(bk('cloth'));
    const topY = look.boots.top;
    const shaftKeys = topY > 0.35
      ? [
          { t: 0, rx: 0.054, rzF: 0.056, rzB: 0.062 },
          { t: 0.45, rx: 0.059, rzF: 0.055, rzB: 0.072 },
          { t: 0.85, rx: 0.062, rzF: 0.062, rzB: 0.068 },
          { t: 1, rx: 0.066, rzF: 0.066, rzB: 0.07 },
        ]
      : [
          { t: 0, rx: 0.054, rzF: 0.056, rzB: 0.062 },
          { t: 0.8, rx: 0.056, rzF: 0.056, rzB: 0.064 },
          { t: 1, rx: 0.06, rzF: 0.06, rzB: 0.066 },
        ];
    const ankle = J['foot_' + side];
    const shaft = new LoftSurface({
      chain: {
        points: [V(ankle.x / s, 0.045, -0.024), V(ankle.x / s - sx * 0.004, topY, 0.004)],
        bones: [I['shin_' + side]],
        extra: (p) => {
          const w = smoothstep(0.13 * s, 0.05 * s, p.y) * 0.75;
          return w > 0 ? [{ bone: I['foot_' + side], w }] : [];
        },
      },
      profile: keysT(shaftKeys, s, fem ? 0.92 : 1),
      rings: R(10),
      radial: det.radial,
      capStart: false,
      color: (t) => (t > 0.94 ? scaleRGB(C.boots, 0.7) : C.boots),
    });
    shaft.build(bk('cloth'));
    if (det.details >= 1) {
      // Strap across the shaft.
      addPatch(bk('cloth'), shaft, { t0: 0.3, t1: 0.42, phi0: 0, phi1: Math.PI * 2, offset: 0.002 * s, thickness: 0.006 * s, color: scaleRGB(C.boots, 0.6), segT: 2, segPhi: det.radial });
      addRoundBox(bk('metal'), shaft.point(0.36, sx > 0 ? 0 : Math.PI, 0.008 * s), V(0.012, 0.02, 0.022), faceQuat(surfNormal(shaft, 0.36, sx > 0 ? 0 : Math.PI)), C.metal, one(I['shin_' + side]));
    }
  }

  // ---------------------------------------------------------------- Arms and hands
  const sleeveSurf: Record<string, LoftSurface> = {};
  for (const side of ['L', 'R'] as const) {
    const sx = side === 'L' ? 1 : -1;
    const sh = J['upperarm_' + side];
    const inner = sh.clone().add(V(-sx * 0.045, 0.016, 0.0));
    const sleeveInflate = look.top.kind === 'suit' ? 0 : look.top.kind === 'coat' ? 0.012 * s : 0.007 * s;
    const fs = fem ? 0.85 : 1;
    const keys: ProfileKey[] = [
      { t: 0, rx: 0.066, rzF: 0.066, rzB: 0.068 },
      { t: 0.07, rx: 0.066, rzF: 0.068, rzB: 0.07 },
      { t: 0.2, rx: 0.058, rzF: 0.06, rzB: 0.058 },
      { t: 0.36, rx: 0.052, rzF: 0.054, rzB: 0.05 },
      { t: 0.52, rx: 0.046, rzF: 0.046, rzB: 0.046 },
      { t: 0.58, rx: 0.045, rzF: 0.045, rzB: 0.048 },
      { t: 0.68, rx: 0.048, rzF: 0.049, rzB: 0.046 },
      { t: 0.85, rx: 0.041, rzF: 0.04, rzB: 0.038 },
      { t: 1, rx: 0.037, rzF: 0.034, rzB: 0.034 },
    ];
    const surf = new LoftSurface({
      chain: {
        points: [inner, sh.clone(), J['forearm_' + side].clone(), J['hand_' + side].clone()],
        bones: [I['upperarm_' + side], I['upperarm_' + side], I['forearm_' + side]],
        blend: 0.05 * s,
        extra: (p, t) => {
          const w = smoothstep(0.1, 0.0, t) * 0.4;
          return w > 0 ? [{ bone: I['clavicle_' + side], w }] : [];
        },
      },
      profile: keysT(keys, s, fs * bulk),
      rings: R(24),
      radial: det.radial,
      inflate: sleeveInflate,
      color: (t, phi) => {
        if (look.top.pattern === 'lyra' && side === 'R') {
          return mixRGB(C.top, C.top2, smoothstep(0.1, 0.0, Math.abs(t - 0.3)) * 0.0 + smoothstep(0.6, 0.85, -Math.sin(phi)) * smoothstep(0.08, 0.12, t) * smoothstep(0.5, 0.46, t));
        }
        if (look.top.pattern === 'kael') return t > 0.94 ? scaleRGB(C.top, 0.75) : C.top;
        return C.top;
      },
      uvScale: 5,
    });
    surf.build(bk('cloth'));
    sleeveSurf[side] = surf;

    // Hand: palm plus four curled fingers and an opposed thumb.
    const wr = J['hand_' + side], he = J['handEnd_' + side];
    const handDir = new THREE.Vector3().subVectors(he, wr).normalize();
    const hs2 = fem ? 0.88 : 1;
    const handLen = wr.distanceTo(he);
    const inward = new THREE.Vector3(-sx, 0, 0);
    const fwdZ = new THREE.Vector3(0, 0, 1);
    const knuckle = wr.clone().addScaledVector(handDir, handLen * 0.52);
    const palm = new LoftSurface({
      chain: { points: [wr.clone().addScaledVector(handDir, -0.012 * s), wr.clone().addScaledVector(handDir, handLen * 0.26), knuckle.clone()], bones: [I['hand_' + side], I['hand_' + side]] },
      fwd: new THREE.Vector3(sx, 0, 0),
      side: fwdZ,
      profile: keysT([
        { t: 0, rx: 0.033, rzF: 0.023, rzB: 0.023, n: 2.4 },
        { t: 0.35, rx: 0.043, rzF: 0.019, rzB: 0.022, n: 3.2 },
        { t: 0.8, rx: 0.046, rzF: 0.017, rzB: 0.019, n: 3.4 },
        { t: 1, rx: 0.044, rzF: 0.014, rzB: 0.016, n: 3.0 },
      ], s, hs2),
      rings: R(8),
      radial: Math.max(6, det.radial - 4),
      capStart: true,
      capEnd: true,
      color: C.glove,
    });
    palm.build(bk(gloveMat));
    const fingerRadial = det.details >= 2 ? 7 : det.details >= 1 ? 5 : 4;
    const fingers: [number, number, number][] = [
      // z offset across the knuckles (front = index), length, radius
      [0.03, 0.074, 0.0098], [0.01, 0.082, 0.0101], [-0.01, 0.077, 0.0096], [-0.029, 0.061, 0.0086],
    ];
    if (det.details === 0) {
      // Distant LOD: a single rounded block for the fingers.
      addRoundBox(bk(gloveMat), knuckle.clone().addScaledVector(handDir, 0.035 * s).addScaledVector(inward, 0.01 * s), V(0.024, 0.07, 0.085).multiply(new THREE.Vector3(hs2, hs2, hs2)), new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), handDir.clone().negate()), C.glove, one(I['hand_' + side]), 0.35, 1);
    } else {
      fingers.forEach(([zo, len, rad], fi) => {
        const pts: THREE.Vector3[] = [];
        let p = knuckle.clone().addScaledVector(fwdZ, zo * s * hs2).addScaledVector(inward, 0.003 * s);
        pts.push(p.clone().addScaledVector(handDir, -0.008 * s));
        pts.push(p.clone());
        let ang = 0.12 + fi * 0.03;
        const segs = [0.45, 0.3, 0.25];
        for (const k of segs) {
          ang += 0.42;
          const d = handDir.clone().multiplyScalar(Math.cos(ang)).addScaledVector(inward, Math.sin(ang)).normalize();
          p = p.clone().addScaledVector(d, len * k * s * hs2);
          pts.push(p);
        }
        addTube(bk(gloveMat), pts, (i) => rad * s * hs2 * (i >= pts.length - 1 ? 0.78 : 1 - i * 0.05), fingerRadial, C.glove, () => one(I['hand_' + side]));
        // Fingertip cap
        addEllipsoid(bk(gloveMat), pts[pts.length - 1], new THREE.Vector3(rad * 0.78, rad * 0.78, rad * 0.78).multiplyScalar(s * hs2), new THREE.Quaternion(), C.glove, one(I['hand_' + side]), 6, 4);
      });
    }
    // Thumb: from the base of the palm, opposed toward the fingers.
    const thumbBase = wr.clone().addScaledVector(handDir, handLen * 0.12).addScaledVector(fwdZ, 0.026 * s * hs2).addScaledVector(inward, 0.006 * s);
    const tDir1 = handDir.clone().multiplyScalar(0.55).addScaledVector(fwdZ, 0.6).addScaledVector(inward, 0.35).normalize();
    const tDir2 = handDir.clone().multiplyScalar(0.75).addScaledVector(fwdZ, 0.15).addScaledVector(inward, 0.55).normalize();
    const t1 = thumbBase.clone().addScaledVector(tDir1, 0.034 * s * hs2);
    const t2 = t1.clone().addScaledVector(tDir2, 0.03 * s * hs2);
    const t3 = t2.clone().addScaledVector(tDir2.clone().addScaledVector(inward, 0.4).normalize(), 0.024 * s * hs2);
    addTube(bk(gloveMat), [thumbBase, t1, t2, t3], (i) => [0.014, 0.012, 0.0108, 0.0088][i] * s * hs2, Math.max(5, fingerRadial), C.glove, () => one(I['hand_' + side]));
    addEllipsoid(bk(gloveMat), t3, new THREE.Vector3(0.0085, 0.0085, 0.0085).multiplyScalar(s * hs2), new THREE.Quaternion(), C.glove, one(I['hand_' + side]), 6, 4);
    // Glove cuff
    if (look.gloves) {
      const cuff = new LoftSurface({
        chain: { points: [wr.clone().addScaledVector(handDir, -0.045 * s), wr.clone().addScaledVector(handDir, 0.012 * s)], bones: [I['forearm_' + side]], extra: (p, t) => [{ bone: I['hand_' + side], w: t * 0.6 }] },
        profile: keysT([{ t: 0, rx: 0.041, rzF: 0.039, rzB: 0.039 }, { t: 1, rx: 0.039, rzF: 0.037, rzB: 0.037 }], s, fem ? 0.88 : 1),
        rings: 2,
        radial: det.radial,
        color: scaleRGB(C.glove, 0.85),
      });
      cuff.build(bk('cloth'));
    }
    sockets['hand_' + side] = { bone: 'hand_' + side, pos: wr.clone().lerp(he, 0.55) };
    sockets['forearm_' + side] = { bone: 'forearm_' + side, pos: J['forearm_' + side].clone().lerp(wr, 0.6) };
  }

  // ---------------------------------------------------------------- Collar
  if (look.top.collar !== 'none') {
    const high = look.top.collar === 'high';
    const collar = new LoftSurface({
      chain: { points: [V(0, 1.468, -0.034), V(0, high ? 1.575 : 1.52, -0.026)], bones: [I.chest], extra: (p, t) => [{ bone: I.neck, w: t * 0.7 }] },
      profile: keysT([
        { t: 0, rx: 0.088, rzF: 0.086, rzB: 0.09 },
        { t: 1, rx: 0.074, rzF: 0.074, rzB: 0.08 },
      ], s, (fem ? 0.88 : 1) * bulk),
      rings: 3,
      radial: det.radial,
      color: scaleRGB(C.top, 0.9),
    });
    const gap = look.top.zip === 'diag' ? 0.5 : 0.36;
    addPatch(bk('cloth'), collar, {
      t0: 0, t1: 1,
      phi0: Math.PI / 2 + gap, phi1: Math.PI / 2 + Math.PI * 2 - gap * (look.top.zip === 'diag' ? 0.4 : 1),
      offset: 0, thickness: 0.009 * s, color: scaleRGB(C.top, 0.85),
      segT: 3, segPhi: det.radial, bevel: 0.2,
    });
  }

  // ---------------------------------------------------------------- Zip / closure
  if (det.details >= 1 && look.top.zip !== 'none') {
    const a: [number, number] = look.top.zip === 'diag' ? [torsoT(1.44), Math.PI / 2 + 0.42] : [torsoT(1.44), Math.PI / 2];
    const b: [number, number] = look.top.zip === 'diag' ? [torsoT(Math.max(torsoBottom + 0.02, 0.84)), Math.PI / 2 - 0.3] : [torsoT(torsoBottom + 0.02), Math.PI / 2];
    const path = surfPath(torso, a, b, 16, 0.003 * s);
    addTube(bk('metal'), path.map((q) => q.p), 0.0055 * s, 4, scaleRGB(C.metal, 0.35), (i, p) => torso.influences(path[i].t, p), 0.45);
  }

  // ---------------------------------------------------------------- Armor
  const ar = look.armor;
  if (ar) {
    for (const side of ['L', 'R'] as const) {
      const size = side === 'L' ? ar.shoulderL : ar.shoulderR;
      if (!size) continue;
      const pc = side === 'L' ? 0 : Math.PI;
      // Plate over the deltoid (on the sleeve) and a cap over the top of the shoulder (on the torso).
      addPatch(bk('armor'), sleeveSurf[side], {
        t0: 0.02, t1: 0.2 + 0.08 * size, phi0: pc - 1.25 - 0.2 * size, phi1: pc + 1.25 + 0.2 * size,
        offset: 0.006 * s, thickness: 0.013 * s * size, bulge: 0.008 * s * size, color: C.armor, segT: 5, segPhi: 10, bevel: 0.18,
      });
      addPatch(bk('armor'), torso, {
        t0: torsoT(1.4), t1: torsoT(1.492), phi0: pc - 0.5 * size, phi1: pc + 0.5 * size,
        offset: 0.005 * s, thickness: 0.012 * s * size, bulge: 0.006 * s, color: scaleRGB(C.armor, 0.9), segT: 4, segPhi: 6, bevel: 0.25,
      });
      if (det.details >= 1) {
        // Second overlapping lamella for a layered look.
        addPatch(bk('armor'), sleeveSurf[side], {
          t0: 0.17 + 0.08 * size, t1: 0.27 + 0.1 * size, phi0: pc - 1.0, phi1: pc + 1.0,
          offset: 0.007 * s, thickness: 0.009 * s, color: scaleRGB(C.armor, 0.82), segT: 3, segPhi: 8, bevel: 0.25,
        });
      }
    }
    const chestSides = ar.chest === 'both' ? ['L', 'R'] : ar.chest ? [ar.chest] : [];
    for (const side of chestSides) {
      const [p0, p1] = side === 'L' ? [0.5, 1.42] : [1.72, 2.64];
      addPatch(bk('armor'), torso, {
        t0: torsoT(fem ? 1.27 : 1.17), t1: torsoT(fem ? 1.4 : 1.37), phi0: p0, phi1: p1,
        offset: 0.004 * s, thickness: 0.012 * s, bulge: 0.004 * s, color: C.armor, segT: 6, segPhi: 8, bevel: 0.15,
      });
      if (det.details >= 1) {
        addPatch(bk('armor'), torso, {
          t0: torsoT(fem ? 1.2 : 1.1), t1: torsoT(fem ? 1.255 : 1.16), phi0: p0 + 0.1, phi1: p1 - 0.1,
          offset: 0.004 * s, thickness: 0.009 * s, color: scaleRGB(C.armor, 0.85), segT: 3, segPhi: 6, bevel: 0.2,
        });
      }
    }
    for (const side of ['L', 'R'] as const) {
      if (!(side === 'L' ? ar.forearmL : ar.forearmR)) continue;
      addPatch(bk('armor'), sleeveSurf[side], {
        t0: 0.63, t1: 0.95, phi0: 0, phi1: Math.PI * 2, offset: 0.004 * s, thickness: 0.011 * s, color: C.armor, segT: 6, segPhi: det.radial, bevel: 0.08,
      });
      if (det.details >= 1) {
        addPatch(bk('armor'), sleeveSurf[side], {
          t0: 0.6, t1: 0.66, phi0: 0, phi1: Math.PI * 2, offset: 0.012 * s, thickness: 0.006 * s, color: scaleRGB(C.armor, 0.75), segT: 2, segPhi: det.radial, bevel: 0.2,
        });
      }
    }
    if (ar.knees) {
      for (const side of ['L', 'R'] as const) {
        addPatch(bk('armor'), legSurf[side], {
          t0: 0.47, t1: 0.6, phi0: Math.PI / 2 - 0.85, phi1: Math.PI / 2 + 0.85, offset: 0.004 * s, thickness: 0.012 * s, bulge: 0.006 * s, color: C.armor, segT: 4, segPhi: 6, bevel: 0.2,
        });
      }
    }
  }

  // ---------------------------------------------------------------- Aether forearm interface
  if (look.iface) {
    const side = look.iface;
    const sl = sleeveSurf[side];
    const pc = side === 'R' ? Math.PI * 0.72 : Math.PI * 0.28;
    addPatch(bk('glow'), sl, { t0: 0.7, t1: 0.86, phi0: pc - 0.42, phi1: pc + 0.42, offset: 0.0165 * s, thickness: 0.0015 * s, color: C.glow, segT: 3, segPhi: 4, bevel: 0.3 });
    if (det.details >= 1) {
      // Frame around the display, and the emitter ring at the wrist.
      addPatch(bk('metal'), sl, { t0: 0.68, t1: 0.7, phi0: pc - 0.5, phi1: pc + 0.5, offset: 0.015 * s, thickness: 0.003 * s, color: scaleRGB(C.metal, 0.4), segT: 1, segPhi: 4 });
      addPatch(bk('metal'), sl, { t0: 0.86, t1: 0.88, phi0: pc - 0.5, phi1: pc + 0.5, offset: 0.015 * s, thickness: 0.003 * s, color: scaleRGB(C.metal, 0.4), segT: 1, segPhi: 4 });
      addPatch(bk('glow'), sl, { t0: 0.935, t1: 0.948, phi0: 0, phi1: Math.PI * 2, offset: 0.0155 * s, thickness: 0.001 * s, color: scaleRGB(C.glow, 0.8), segT: 1, segPhi: det.radial });
    }
    sockets.iface = { bone: 'forearm_' + side, pos: sl.point(0.78, pc, 0.02 * s) };
  }

  // ---------------------------------------------------------------- Belt and pouches
  if (look.belt) {
    addPatch(bk('cloth'), pelvis, {
      t0: (0.975 - pY0) / (pY1 - pY0), t1: (1.03 - pY0) / (pY1 - pY0), phi0: 0, phi1: Math.PI * 2,
      offset: (look.top.hem < 0.98 ? 0.03 : 0.004) * s * coatExtra, thickness: 0.012 * s, color: C.belt, segT: 2, segPhi: det.radial + 4, bevel: 0.25,
    });
    if (det.details >= 1) {
      const by = (1.0 - pY0) / (pY1 - pY0);
      const off = (look.top.hem < 0.98 ? 0.03 : 0.004) * s * coatExtra;
      const spots = [Math.PI * 0.95, Math.PI * 1.22, Math.PI * 1.78, Math.PI * 0.12, Math.PI * 0.4].slice(0, look.belt.pouches);
      for (const phi of spots) {
        const n = surfNormal(pelvis, by, phi);
        const p = pelvis.point(by - 0.06, phi, off + 0.028 * s);
        addRoundBox(bk('cloth'), p, V(0.072, 0.085, 0.038), faceQuat(n), scaleRGB(C.belt, 0.92), pelvis.influences(by, p), 0.3, lod === 0 ? 3 : 1);
      }
      // Buckle
      const n = surfNormal(pelvis, by, Math.PI / 2);
      addRoundBox(bk('metal'), pelvis.point(by, Math.PI / 2 - 0.08, off + 0.014 * s), V(0.05, 0.036, 0.012), faceQuat(n), scaleRGB(C.metal, 0.6), one(I.hips), 0.2, 1);
    }
  }

  // ---------------------------------------------------------------- Lyra's harness
  if (look.harness) {
    const strap = (a: [number, number], b: [number, number], seg: number) => {
      const path = surfPath(torso, a, b, seg, 0.006 * s);
      addTube(bk('cloth'), path.map((q) => q.p), 0.016 * s, 6, lin(look.harness!.color), (i, p) => torso.influences(path[i].t, p), 0.28);
    };
    strap([torsoT(1.474), Math.PI * 0.86], [torsoT(1.0), Math.PI * 0.08], 20); // front diagonal
    strap([torsoT(1.474), Math.PI * 1.14], [torsoT(1.0), -Math.PI * 0.08 + Math.PI * 2], 20); // back diagonal
    strap([torsoT(1.02), 0], [torsoT(1.02), Math.PI * 2], 28); // waist band
    // Energy unit on the left chest.
    const ut = torsoT(fem ? 1.31 : 1.27), up = Math.PI * 0.3;
    const n = surfNormal(torso, ut, up);
    const q = faceQuat(n);
    const center = torso.point(ut, up, 0.016 * s);
    addEllipsoid(bk('armor'), center, V(0.046, 0.046, 0.018), q, C.armor, one(I.chest), 16, 8);
    addEllipsoid(bk('glow'), center.clone().addScaledVector(n, 0.012 * s), V(0.022, 0.022, 0.008), q, mixRGB(C.glow, C.glow2, 0.3), one(I.chest), 12, 6);
    if (det.details >= 1) {
      addTube(bk('metal'), Array.from({ length: 17 }, (_, i) => {
        const a = (i / 16) * Math.PI * 2;
        return center.clone().add(new THREE.Vector3(Math.cos(a) * 0.036 * s, Math.sin(a) * 0.036 * s, 0.014 * s).applyQuaternion(q));
      }), 0.004 * s, 4, scaleRGB(C.metal, 0.5), () => one(I.chest));
    }
    sockets.harness = { bone: 'chest', pos: center.clone().addScaledVector(n, 0.02 * s) };
    // Hip module on the left.
    const ht = (0.96 - pY0) / (pY1 - pY0);
    const hn = surfNormal(pelvis, ht, Math.PI * 0.06);
    const hp = pelvis.point(ht, Math.PI * 0.06, 0.04 * s);
    addRoundBox(bk('armor'), hp, V(0.075, 0.11, 0.04), faceQuat(hn), C.armor, one(I.hips), 0.25, lod === 0 ? 3 : 1);
    addRoundBox(bk('glow'), hp.clone().addScaledVector(hn, 0.021 * s), V(0.012, 0.075, 0.004), faceQuat(hn), C.glow2, one(I.hips), 0.4, 1);
  }

  // ---------------------------------------------------------------- Aether conduits
  if (look.glow && look.glow.pattern !== 'none' && det.details >= 1) {
    const g = bk('glow');
    const r = 0.0032 * s;
    const conduit = (surf: LoftSurface, a: [number, number], b: [number, number], seg: number, off: number, c0: RGB, c1: RGB) => {
      const path = surfPath(surf, a, b, seg, off);
      const base = g.count;
      addTube(g, path.map((q) => q.p), r, 4, c0, (i, p) => surf.influences(path[i].t, p));
      // Gradient along the conduit.
      for (let v = base; v < g.count; v++) {
        const k = Math.floor((v - base) / 5) / seg;
        const c = mixRGB(c0, c1, k);
        g.col[v * 3] = c[0]; g.col[v * 3 + 1] = c[1]; g.col[v * 3 + 2] = c[2];
      }
    };
    if (look.glow.pattern === 'kael') {
      const sl = sleeveSurf.R;
      conduit(sl, [0.66, Math.PI * 1.12], [0.06, Math.PI * 1.08], 18, 0.009 * s, C.glow, scaleRGB(C.glow, 0.55));
      conduit(torso, [torsoT(1.4), Math.PI * 0.95], [torsoT(1.12), Math.PI * 1.32], 12, 0.004 * s, scaleRGB(C.glow, 0.55), scaleRGB(C.glow, 0.25));
      conduit(torso, [torsoT(1.43), Math.PI * 1.5], [torsoT(1.06), Math.PI * 1.5], 14, 0.004 * s, scaleRGB(C.glow, 0.5), scaleRGB(C.glow, 0.2));
      conduit(torso, [torsoT(1.3), Math.PI * 0.32], [torsoT(Math.max(torsoBottom + 0.03, 0.9)), Math.PI * 0.28], 12, 0.004 * s, scaleRGB(C.glow, 0.35), scaleRGB(C.glow, 0.15));
    } else {
      const sl = sleeveSurf.L;
      conduit(sl, [0.05, -0.12], [0.93, -0.12], 20, 0.002 * s, C.glow, C.glow2);
      conduit(sl, [0.05, 0.12], [0.93, 0.12], 20, 0.002 * s, scaleRGB(C.glow, 0.8), scaleRGB(C.glow2, 0.8));
      conduit(torso, [torsoT(fem ? 1.29 : 1.25), Math.PI * 0.22], [torsoT(1.0), Math.PI * 0.08], 10, 0.004 * s, C.glow, C.glow2);
      conduit(legSurf.L, [0.04, 0.05], [0.44, 0.05], 12, 0.002 * s, C.glow2, scaleRGB(C.glow2, 0.4));
    }
  }

  // ---------------------------------------------------------------- Back pack / device
  if (look.backpack && det.details >= 1) {
    const bt = torsoT(1.1);
    const n = surfNormal(torso, bt, Math.PI * 1.5);
    const p = torso.point(bt, Math.PI * 1.5, 0.035 * s);
    addRoundBox(bk('armor'), p, V(0.17, 0.11, 0.06), faceQuat(n), scaleRGB(C.armor, 0.9), one(I.spine), 0.25, lod === 0 ? 3 : 1);
    if (look.glow) addRoundBox(bk('glow'), p.clone().addScaledVector(n, 0.031 * s), V(0.11, 0.008, 0.004), faceQuat(n), scaleRGB(C.glow, 0.6), one(I.spine), 0.4, 1);
  }

  // ---------------------------------------------------------------- Extras
  for (const ex of look.extras ?? []) {
    if (ex === 'scarf') {
      const sc = new LoftSurface({
        chain: { points: [V(0, 1.455, -0.03), V(0, 1.55, -0.02)], bones: [I.chest], extra: (p, t) => [{ bone: I.neck, w: t * 0.6 }] },
        profile: keysT([{ t: 0, rx: 0.1, rzF: 0.1, rzB: 0.098 }, { t: 0.5, rx: 0.088, rzF: 0.09, rzB: 0.088 }, { t: 1, rx: 0.07, rzF: 0.075, rzB: 0.076 }], s, bulk),
        rings: R(5),
        radial: det.radial,
        color: C.top2,
        displace: (t, phi) => Math.sin(phi * 7 + t * 4) * 0.004 * s,
      });
      sc.build(bk('cloth'));
    } else if (ex === 'headset') {
      const e = hc.clone().add(new THREE.Vector3(shape.r.x + 0.004 * s, -0.006 * s, -0.008 * s));
      addEllipsoid(bk('armor'), e, V(0.012, 0.026, 0.022), new THREE.Quaternion(), C.armor, one(I.head), 10, 6);
      addTube(bk('metal'), [e.clone(), e.clone().add(V(0.004, -0.03, 0.04)), e.clone().add(V(-0.02, -0.05, 0.075))], 0.0028 * s, 4, scaleRGB(C.metal, 0.4), () => one(I.head));
      addEllipsoid(bk('glow'), e.clone().add(V(0.012, 0.0, 0.0)), V(0.002, 0.012, 0.01), new THREE.Quaternion(), C.glow, one(I.head), 6, 4);
    } else if (ex === 'satchel') {
      const bt = (0.93 - pY0) / (pY1 - pY0);
      const n = surfNormal(pelvis, bt, Math.PI * 1.1);
      addRoundBox(bk('cloth'), pelvis.point(bt, Math.PI * 1.1, 0.06 * s), V(0.22, 0.17, 0.08), faceQuat(n), C.top2, one(I.hips), 0.25, 2);
      const path = surfPath(torso, [torsoT(1.47), Math.PI * 0.2], [torsoT(Math.max(torsoBottom + 0.02, 0.95)), Math.PI * 1.05], 16, 0.008 * s);
      addTube(bk('cloth'), path.map((q) => q.p), 0.014 * s, 5, scaleRGB(C.top2, 0.8), (i, p) => torso.influences(path[i].t, p), 0.3);
    } else if (ex === 'backpack') {
      const bt = torsoT(1.24);
      const n = surfNormal(torso, bt, Math.PI * 1.5);
      addRoundBox(bk('cloth'), torso.point(bt, Math.PI * 1.5, 0.09 * s), V(0.3, 0.38, 0.16), faceQuat(n), C.top2, one(I.chest), 0.2, 2);
    } else if (ex === 'goggles') {
      for (const sx of [1, -1]) {
        const c = hc.clone().add(new THREE.Vector3(sx * 0.03 * s, 0.062 * s, shape.r.z * 0.86));
        addEllipsoid(bk('metal'), c, V(0.022, 0.017, 0.012), new THREE.Quaternion().setFromEuler(new THREE.Euler(-0.5, 0, 0)), scaleRGB(C.metal, 0.6), one(I.head), 10, 6);
      }
    }
  }

  // ---------------------------------------------------------------- Hair
  buildHair(look, shape, hc, s, rig, det, bk, C.hair, lod);

  sockets.spine = { bone: 'chest', pos: torso.point(torsoT(1.25), Math.PI * 1.5, 0.08 * s) };
  sockets.chest = { bone: 'chest', pos: J.chest.clone().add(V(0, 0.08, 0.1)) };
  sockets.root = { bone: 'root', pos: new THREE.Vector3() };
  return { buckets, sockets, eyes };
}

/** Hairline (polar angle fraction of PI from the crown) at front / side / back for each style. */
export const HAIR_PARAMS: Record<Exclude<HairStyle, 'none'>, { front: number; side: number; back: number; thick: number; tuft: number; quiff: number; topBias?: number; curl?: number }> = {
  short: { front: 0.3, side: 0.45, back: 0.69, thick: 0.0095, tuft: 0.0045, quiff: 0.006 },
  swept: { front: 0.33, side: 0.47, back: 0.7, thick: 0.009, tuft: 0.003, quiff: 0.004 },
  undercut: { front: 0.29, side: 0.44, back: 0.67, thick: 0.004, tuft: 0.002, quiff: 0.012, topBias: 1 },
  buzz: { front: 0.31, side: 0.46, back: 0.7, thick: 0.0035, tuft: 0.001, quiff: 0 },
  curly: { front: 0.29, side: 0.5, back: 0.7, thick: 0.017, tuft: 0.009, quiff: 0.004, curl: 1 },
  tied: { front: 0.27, side: 0.46, back: 0.66, thick: 0.0058, tuft: 0.0012, quiff: 0.001 },
  bun: { front: 0.27, side: 0.46, back: 0.66, thick: 0.006, tuft: 0.0012, quiff: 0.001 },
  bob: { front: 0.29, side: 0.55, back: 0.68, thick: 0.013, tuft: 0.003, quiff: 0.003 },
  long: { front: 0.28, side: 0.49, back: 0.7, thick: 0.011, tuft: 0.003, quiff: 0.002 },
  hood: { front: 0.24, side: 0.74, back: 0.86, thick: 0.03, tuft: 0, quiff: 0.006 },
};

function buildHair(
  look: Look,
  shape: HeadShape,
  hc: THREE.Vector3,
  s: number,
  rig: Rig,
  det: Detail,
  bk: (k: MatKey) => MeshBucket,
  color: RGB,
  lod: number,
) {
  const style = look.hairStyle;
  if (style === 'none') return;
  const I = rig.index;
  const mat: MatKey = style === 'hood' ? 'cloth' : 'hair';
  const col = style === 'hood' ? lin(look.top.color2) : color;
  const params = HAIR_PARAMS[style];
  const [wSeg0, hSeg0] = det.head;
  const wSeg = wSeg0, hSeg = Math.max(6, Math.round(hSeg0 * 0.75));
  const hash = (a: number, c: number) => {
    const x = Math.sin(a * 127.1 + c * 311.7) * 43758.5453;
    return x - Math.floor(x);
  };
  const dir = new THREE.Vector3();
  /** Build a cap shell over the scalp; `extra` adds thickness (fuzz layer). */
  const shell = (b: MeshBucket, extra: number, colorK: number, uvMul: number) => {
    const base = b.count;
    const grid: THREE.Vector3[][] = [];
    for (let iy = 0; iy <= hSeg; iy++) {
      const v = iy / hSeg;
      const row: THREE.Vector3[] = [];
      for (let ix = 0; ix <= wSeg; ix++) {
        const phi = (ix / wSeg) * Math.PI * 2 - Math.PI;
        const a = Math.abs(phi) / Math.PI;
        const sideK = Math.sin(Math.abs(phi));
        let tmax = a < 0.5 ? lerp(params.front, params.side, smoothstep(0, 0.5, a)) : lerp(params.side, params.back, smoothstep(0.5, 1, a));
        if (style === 'short' || style === 'swept' || style === 'curly') tmax += 0.05 * Math.exp(-((Math.abs(phi) - 1.35) ** 2) / 0.02);
        const theta = v * tmax * Math.PI;
        dir.set(Math.sin(theta) * Math.sin(phi), Math.cos(theta), Math.sin(theta) * Math.cos(phi));
        const p = shape.sculpt(dir);
        const edge = smoothstep(1, 0.86, v);
        const tuft = (hash(Math.round(ix * 0.5), Math.round(iy * 0.5)) - 0.5) * params.tuft;
        const crown = smoothstep(0.6, 0.0, v) * 0.003;
        const quiff = params.quiff * Math.exp(-(phi ** 2) / 0.35) * smoothstep(1, 0.5, v) * smoothstep(0.1, 0.6, v);
        let thick = (params.thick + tuft + crown + quiff) * edge + 0.0012;
        if (params.topBias) thick += smoothstep(0.55, 0.2, v) * 0.012 * (1 - sideK * 0.4);
        if (params.curl) thick += (Math.sin(ix * 1.7) * Math.cos(iy * 2.3) * 0.5 + 0.5) * 0.007 * edge;
        if (style === 'swept') thick += smoothstep(0.1, 0.5, v) * smoothstep(0.9, 0.6, v) * 0.004 * Math.cos(phi);
        if (style === 'hood') thick = params.thick * (0.6 + 0.4 * sideK) + 0.004;
        p.addScaledVector(dir, (thick + extra) * s).add(hc);
        row.push(p);
      }
      grid.push(row);
    }
    for (let iy = 0; iy <= hSeg; iy++) {
      for (let ix = 0; ix <= wSeg; ix++) {
        const p = grid[iy][ix];
        const du = new THREE.Vector3().subVectors(grid[iy][ix === wSeg ? 1 : ix + 1], grid[iy][ix === 0 ? wSeg - 1 : ix - 1]);
        const dv = new THREE.Vector3().subVectors(grid[Math.min(hSeg, iy + 1)][ix], grid[Math.max(0, iy - 1)][ix]);
        const n = new THREE.Vector3().crossVectors(du, dv);
        if (n.lengthSq() < 1e-14) n.subVectors(p, hc);
        n.normalize();
        if (n.dot(new THREE.Vector3().subVectors(p, hc)) < 0) n.negate();
        const shade = (0.85 + 0.3 * hash(ix, iy * 3.1)) * colorK;
        b.addVertex(p, n, (ix / wSeg) * 3 * uvMul, (iy / hSeg) * 2 * uvMul, scaleRGB(col, style === 'hood' ? 1 : shade), one(I.head));
      }
    }
    const cols = wSeg + 1;
    for (let iy = 0; iy < hSeg; iy++) {
      for (let ix = 0; ix < wSeg; ix++) {
        const a = base + iy * cols + ix, bb = a + 1, c = a + cols, d = c + 1;
        if (iy !== 0) b.idx.push(a, c, bb);
        b.idx.push(bb, c, d);
      }
    }
  };
  shell(bk(mat), 0, 1, 1);
  // Strand fringe: an alpha-tested outer layer softens the silhouette and hairline.
  if (det.details >= 1 && style !== 'hood' && style !== 'buzz') shell(bk('hairfx'), 0.0035 + (params.curl ? 0.003 : 0), 1.1, 2);

  if ((style === 'tied' || style === 'bun') && det.details >= 0) {
    const bunPos = style === 'bun' ? hc.clone().add(new THREE.Vector3(0, 0.1 * s, -0.06 * s)) : hc.clone().add(new THREE.Vector3(0, 0.07 * s, -0.082 * s));
    const bunR = style === 'bun' ? new THREE.Vector3(0.042, 0.036, 0.04) : new THREE.Vector3(0.033, 0.03, 0.032);
    addEllipsoid(bk('hair'), bunPos, bunR.multiplyScalar(s), new THREE.Quaternion().setFromEuler(new THREE.Euler(style === 'bun' ? 0.9 : 0.5, 0, 0)), scaleRGB(color, 0.95), one(I.head), lod === 0 ? 14 : 8, lod === 0 ? 10 : 6, (d) => Math.sin(d.x * 30 + d.y * 20) * 0.0015 * s);
  }
  if (style === 'tied' && rig.spec.hairBones > 0) {
    // Hair tie and a braided ponytail along the hair chain.
    addTube(bk('armor'), Array.from({ length: 13 }, (_, i) => {
      const a = (i / 12) * Math.PI * 2;
      return rig.j.hair_0.clone().add(new THREE.Vector3(Math.cos(a) * 0.019 * s, 0.004 * s, Math.sin(a) * 0.016 * s));
    }), 0.004 * s, 4, lin(look.top.color2), () => one(I.hair_0));
    const pts: THREE.Vector3[] = [];
    const bones: number[] = [];
    for (let i = 0; i < rig.spec.hairBones; i++) {
      pts.push(rig.j['hair_' + i].clone());
      bones.push(I['hair_' + i]);
    }
    pts.push(rig.j.hairEnd.clone());
    const tail = new LoftSurface({
      chain: { points: pts, bones, blend: 0.03 * s },
      profile: [
        { t: 0, rx: 0.02 * s, rzF: 0.017 * s },
        { t: 0.15, rx: 0.024 * s, rzF: 0.019 * s },
        { t: 0.6, rx: 0.018 * s, rzF: 0.014 * s },
        { t: 0.92, rx: 0.009 * s, rzF: 0.008 * s },
        { t: 1, rx: 0.003 * s, rzF: 0.003 * s },
      ],
      rings: Math.max(6, Math.round(26 * det.ringMul)),
      radial: Math.max(5, det.radial - 8),
      capEnd: true,
      color: (t) => scaleRGB(color, 0.9 + 0.2 * Math.abs(Math.sin(t * 22))),
      displace: (t, phi) => (Math.abs(Math.sin(t * 22 + (Math.cos(phi) > 0 ? 0 : Math.PI / 2))) - 0.5) * 0.004 * s,
    });
    tail.build(bk('hair'));
  }
  if (style === 'long') {
    // A curtain of hair from the crown down past the shoulders, following head and neck.
    const top = hc.clone().add(new THREE.Vector3(0, 0.02 * s, -0.012 * s));
    const bottom = new THREE.Vector3(0, rig.j.neck.y - 0.13 * s, -0.05 * s);
    const curtain = new LoftSurface({
      chain: { points: [top, new THREE.Vector3(0, hc.y - 0.1 * s, -0.03 * s), bottom], bones: [I.head, I.neck], blend: 0.06 * s, extra: (p) => {
        const w = smoothstep(rig.j.neck.y, rig.j.neck.y - 0.12 * s, p.y) * 0.6;
        return w > 0 ? [{ bone: I.chest, w }] : [];
      } },
      profile: [
        { t: 0, rx: shape.r.x * 1.12, rzF: shape.r.z * 1.0, rzB: shape.r.z * 1.08 },
        { t: 0.45, rx: shape.r.x * 1.18, rzF: shape.r.z * 0.85, rzB: shape.r.z * 1.0 },
        { t: 0.75, rx: 0.13 * s, rzF: 0.07 * s, rzB: 0.09 * s },
        { t: 1, rx: 0.15 * s, rzF: 0.06 * s, rzB: 0.07 * s },
      ],
      rings: Math.max(6, Math.round(16 * det.ringMul)),
      radial: det.radial,
      color: (t) => scaleRGB(color, 0.95 - t * 0.1),
      displace: (t, phi) => Math.sin(phi * 18 + t * 3) * 0.003 * s * t,
    });
    addPatch(bk('hair'), curtain, { t0: 0.12, t1: 1, phi0: Math.PI + 0.25, phi1: Math.PI * 2 - 0.25, offset: 0, thickness: 0.012 * s, color: scaleRGB(color, 0.92), segT: Math.max(6, Math.round(12 * det.ringMul + 4)), segPhi: Math.max(8, det.radial), bevel: 0.3 });
  }
}
