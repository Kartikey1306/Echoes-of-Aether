import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { rng, type Rng } from '../../core/MathUtil';
import { getMaterial, signTexture, type MatName } from '../../render/Materials';
import type { LevelBuilder } from './LevelBuilder';

// Procedural prop library built on LevelBuilder primitives.

const rot = (x: number, z: number, yaw: number, lx: number, lz: number): [number, number] => {
  const c = Math.cos(yaw), s = Math.sin(yaw);
  return [x + lx * c + lz * s, z - lx * s + lz * c];
};

const m4 = (x: number, y: number, z: number, yaw = 0, sx = 1, sy = 1, sz = 1, rx = 0, rz = 0) =>
  new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, yaw, rz, 'YXZ')), new THREE.Vector3(sx, sy, sz));

const geoCache = new Map<string, THREE.BufferGeometry>();
function rbox(w: number, h: number, d: number, r: number, seg = 2): THREE.BufferGeometry {
  const k = `${w}|${h}|${d}|${r}|${seg}`;
  let g = geoCache.get(k);
  if (!g) {
    g = new RoundedBoxGeometry(w, h, d, seg, r);
    const uv = g.getAttribute('uv') as THREE.BufferAttribute;
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * Math.max(w, d), uv.getY(i) * h);
    geoCache.set(k, g);
  }
  return g;
}

const CAR_PAINTS: MatName[] = ['vehicle', 'vehicle_dark', 'metal_painted', 'metal_red'];

/** Compact sci-fi ground car. */
export function car(b: LevelBuilder, x: number, z: number, yaw: number, seed: number, damaged = true) {
  const r = rng(seed);
  const paint = r.pick(CAR_PAINTS);
  const tilt = damaged ? r.range(-0.05, 0.05) : 0;
  const y0 = damaged && r.chance(0.3) ? 0.32 : 0.42;
  b.geo(rbox(4.3, 0.75, 1.9, 0.28, 3), paint, m4(x, y0 + 0.38, z, yaw, 1, 1, 1, 0, tilt), { colliderBox: new THREE.Box3(new THREE.Vector3(-2.15, -0.4, -0.95), new THREE.Vector3(2.15, 0.9, 0.95)) });
  const [cx, cz] = rot(x, z, yaw, -0.25, 0);
  b.geo(rbox(2.3, 0.62, 1.7, 0.26, 3), 'glass_dark', m4(cx, y0 + 0.98, cz, yaw, 1, 1, 1, 0, tilt));
  for (const [lx, lz] of [[1.4, 0.95], [1.4, -0.95], [-1.4, 0.95], [-1.4, -0.95]] as [number, number][]) {
    if (damaged && r.chance(0.15)) continue;
    const [wx, wz] = rot(x, z, yaw, lx, lz);
    b.cyl(wx, 0.36, wz, 0.36, 0.36, 0.28, 'rubber', 12, { rotX: Math.PI / 2, rotY: yaw + Math.PI / 2, collide: false });
  }
  // Light strips (dead or flickering amber)
  const [fx, fz] = rot(x, z, yaw, 2.16, 0);
  b.box(fx, y0 + 0.5, fz, 0.04, 0.08, 1.4, damaged ? 'black' : 'emit_white', { rotY: yaw, collide: false });
  const [bx, bz] = rot(x, z, yaw, -2.16, 0);
  b.box(bx, y0 + 0.5, bz, 0.04, 0.08, 1.4, damaged && r.chance(0.6) ? 'emit_red' : 'black', { rotY: yaw, collide: false });
}

/** Transit bus / tram pod. */
export function bus(b: LevelBuilder, x: number, z: number, yaw: number, seed: number) {
  const r = rng(seed);
  const tilt = r.range(-0.06, 0.06);
  b.geo(rbox(11, 2.8, 2.7, 0.5, 3), 'metal_painted', m4(x, 1.75, z, yaw, 1, 1, 1, 0, tilt), { colliderBox: new THREE.Box3(new THREE.Vector3(-5.5, -1.4, -1.35), new THREE.Vector3(5.5, 1.4, 1.35)) });
  for (const side of [1, -1]) {
    const [wx, wz] = rot(x, z, yaw, 0, side * 1.36);
    b.box(wx, 2.25, wz, 9.6, 0.9, 0.06, 'glass_dark', { rotY: yaw, collide: false, rotZ: tilt });
  }
  const [sx, sz] = rot(x, z, yaw, 0, 1.39);
  b.box(sx, 1.25, sz, 10.6, 0.12, 0.04, 'emit_cyan', { rotY: yaw, collide: false, rotZ: tilt });
  for (const lx of [-3.6, 3.6]) {
    const [wx, wz] = rot(x, z, yaw, lx, 0);
    b.box(wx, 0.4, wz, 1.4, 0.7, 2.5, 'metal_dark', { rotY: yaw, collide: false });
  }
}

/** Concrete jersey barrier. */
export function barrier(b: LevelBuilder, x: number, z: number, yaw: number, mat: MatName = 'concrete', len = 2.6) {
  b.box(x, 0.22, z, len, 0.44, 0.62, mat, { rotY: yaw });
  b.box(x, 0.66, z, len, 0.46, 0.3, mat, { rotY: yaw, collide: false });
  const [sx, sz] = rot(x, z, yaw, 0, 0.16);
  b.box(sx, 0.55, sz, len * 0.95, 0.08, 0.02, 'metal_yellow', { rotY: yaw, collide: false });
}

export function crate(b: LevelBuilder, x: number, y: number, z: number, s: number, yaw: number, mat: MatName = 'metal_painted') {
  b.box(x, y + s / 2, z, s * 1.2, s, s, mat, { rotY: yaw });
  b.box(x, y + s / 2, z, s * 1.22, s * 0.1, s * 1.02, 'metal_dark', { rotY: yaw, collide: false });
}

export function crateStack(b: LevelBuilder, x: number, z: number, yaw: number, seed: number) {
  const r = rng(seed);
  const s = r.range(0.7, 1.0);
  crate(b, x, 0, z, s, yaw, r.pick(['metal_painted', 'metal_dark', 'metal_yellow', 'wood'] as MatName[]));
  if (r.chance(0.7)) {
    const [ox, oz] = rot(x, z, yaw, s * 1.25, r.range(-0.2, 0.2));
    crate(b, ox, 0, oz, s * 0.9, yaw + r.range(-0.3, 0.3), r.pick(['metal_painted', 'wood'] as MatName[]));
  }
  if (r.chance(0.5)) crate(b, x + r.range(-0.1, 0.1), s, z, s * 0.75, yaw + r.range(-0.4, 0.4), 'metal_dark');
}

export interface LightOpts { on?: boolean; color?: number; light?: boolean; flicker?: boolean; height?: number; intensity?: number }

/** Street lamp with emissive head, light pool decal, halo and optional real point light. */
export function streetLight(b: LevelBuilder, x: number, z: number, yaw: number, o: LightOpts = {}): { light: THREE.PointLight | null; halo: THREE.Sprite | null; head: THREE.Vector3 } {
  const h = o.height ?? 6.2;
  b.cyl(x, h / 2, z, 0.08, 0.12, h, 'metal_dark', 8);
  const [ax, az] = rot(x, z, yaw, 0, 0.9);
  b.box(ax, h - 0.1, az, 0.1, 0.1, 1.9, 'metal_dark', { rotY: yaw, collide: false });
  const [hx, hz] = rot(x, z, yaw, 0, 1.7);
  b.box(hx, h - 0.22, hz, 0.42, 0.16, 0.7, 'metal_dark', { rotY: yaw, collide: false });
  const on = o.on ?? true;
  const color = o.color ?? 0xffc98a;
  b.box(hx, h - 0.31, hz, 0.34, 0.03, 0.6, on ? 'emit_warm' : 'black', { rotY: yaw, collide: false });
  let light: THREE.PointLight | null = null;
  let halo: THREE.Sprite | null = null;
  if (on) {
    b.glowDecal(hx, 0.03, hz, 8, color, 0.22 * (o.intensity ?? 1));
    halo = b.glowSprite(hx, h - 0.45, hz, 1.2, color, 0.45);
    if (o.light !== false) light = b.pointLight(hx, h - 0.6, hz, color, 140 * (o.intensity ?? 1), 22, 1.7);
  }
  return { light, halo, head: new THREE.Vector3(hx, h - 0.4, hz) };
}

export function bench(b: LevelBuilder, x: number, z: number, yaw: number) {
  b.box(x, 0.45, z, 1.8, 0.08, 0.5, 'metal_dark', { rotY: yaw });
  const [bx, bz] = rot(x, z, yaw, 0, -0.22);
  b.box(bx, 0.75, bz, 1.8, 0.45, 0.06, 'metal_dark', { rotY: yaw, collide: false, rotX: -0.12 });
  for (const lx of [-0.8, 0.8]) {
    const [lxx, lzz] = rot(x, z, yaw, lx, 0);
    b.box(lxx, 0.22, lzz, 0.06, 0.44, 0.45, 'metal', { rotY: yaw, collide: false });
  }
}

export function trashBin(b: LevelBuilder, x: number, z: number, tipped = false) {
  if (tipped) b.cyl(x, 0.3, z, 0.3, 0.3, 0.9, 'metal_painted', 10, { rotZ: Math.PI / 2, rotY: x * 0.3 });
  else b.cyl(x, 0.45, z, 0.3, 0.27, 0.9, 'metal_painted', 10);
}

export function debris(b: LevelBuilder, x: number, z: number, radius: number, count: number, seed: number, mat: MatName = 'concrete') {
  const r = rng(seed);
  for (let i = 0; i < count; i++) {
    const a = r.range(0, Math.PI * 2), d = Math.sqrt(r.next()) * radius;
    const s = r.range(0.15, 0.6) * (i === 0 ? 2 : 1);
    b.box(x + Math.cos(a) * d, s * 0.35, z + Math.sin(a) * d, s * r.range(0.8, 1.6), s * r.range(0.4, 0.9), s * r.range(0.7, 1.3), r.chance(0.8) ? mat : 'rust', {
      rotY: r.range(0, 3), rotX: r.range(-0.3, 0.3), rotZ: r.range(-0.3, 0.3), collide: s > 0.45, shadow: s > 0.3,
    });
  }
}

export function rebar(b: LevelBuilder, x: number, y: number, z: number, count: number, seed: number) {
  const r = rng(seed);
  for (let i = 0; i < count; i++) {
    b.cyl(x + r.range(-0.6, 0.6), y + 0.4, z + r.range(-0.6, 0.6), 0.015, 0.015, r.range(0.5, 1.2), 'rust', 4, { collide: false, rotX: r.range(-0.6, 0.6), rotZ: r.range(-0.6, 0.6), shadow: false });
  }
}

/** Flat sign (unmerged so each can have its own texture). */
export function sign(b: LevelBuilder, x: number, y: number, z: number, w: number, h: number, yaw: number, lines: string[], o: { bg?: string; fg?: string; glow?: number; border?: string } = {}) {
  const t = signTexture(lines, { w: Math.round(256 * Math.min(4, w / h)), h: 128, bg: o.bg, fg: o.fg, border: o.border });
  const mat = o.glow
    ? new THREE.MeshBasicMaterial({ map: t, color: new THREE.Color(1, 1, 1).multiplyScalar(o.glow) })
    : new THREE.MeshStandardMaterial({ map: t, roughness: 0.5, metalness: 0.2 });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat);
  mesh.position.set(x, y, z);
  mesh.rotation.y = yaw;
  b.root.add(mesh);
  // Backing plate
  const [bx, bz] = rot(x, z, yaw, 0, -0.04);
  b.box(bx, y, bz, w + 0.1, h + 0.1, 0.06, 'metal_dark', { rotY: yaw, collide: false });
  return mesh;
}

export function tarpShelter(b: LevelBuilder, x: number, z: number, yaw: number, w: number, d: number, mat: MatName = 'tarp') {
  for (const [lx, lz] of [[-w / 2, -d / 2], [w / 2, -d / 2], [-w / 2, d / 2], [w / 2, d / 2]] as [number, number][]) {
    const [px, pz] = rot(x, z, yaw, lx, lz);
    b.cyl(px, lz < 0 ? 1.3 : 1.05, pz, 0.04, 0.04, lz < 0 ? 2.6 : 2.1, 'metal_dark', 6);
  }
  b.box(x, 2.35, z, w + 0.4, 0.04, d + 0.4, mat, { rotY: yaw, rotX: 0.12, collide: false });
}

/** Market stall: counter, frame, canopy and goods. */
export function stall(b: LevelBuilder, x: number, z: number, yaw: number, seed: number, canopy: MatName = 'tarp') {
  const r = rng(seed);
  b.box(x, 0.5, z, 2.6, 1.0, 0.9, 'metal_painted', { rotY: yaw });
  const [tx, tz] = rot(x, z, yaw, 0, 0.0);
  b.box(tx, 1.03, tz, 2.7, 0.06, 1.0, 'wood', { rotY: yaw, collide: false });
  for (const lx of [-1.25, 1.25]) for (const lz of [-0.4, 0.4]) {
    const [px, pz] = rot(x, z, yaw, lx, lz);
    b.cyl(px, 1.3, pz, 0.035, 0.035, 2.6, 'metal_dark', 6, { collide: false });
  }
  if (r.chance(0.8)) b.box(x, 2.62, z, 2.9, 0.04, 1.4, canopy, { rotY: yaw, rotX: r.range(-0.15, 0.15), rotZ: r.range(-0.08, 0.08), collide: false });
  for (let i = 0; i < 4; i++) {
    const [gx, gz] = rot(x, z, yaw, r.range(-1.1, 1.1), r.range(-0.3, 0.3));
    const s = r.range(0.12, 0.3);
    b.box(gx, 1.06 + s / 2, gz, s, s, s, r.pick(['tarp', 'tarp_blue', 'wood', 'metal_yellow'] as MatName[]), { rotY: r.range(0, 3), collide: false, shadow: false });
  }
}

/** Free-standing terminal kiosk. Returns the screen centre. */
export function terminal(b: LevelBuilder, x: number, z: number, yaw: number, screenOn = true): THREE.Vector3 {
  b.box(x, 0.6, z, 0.7, 1.2, 0.5, 'metal_dark', { rotY: yaw });
  const [sx, sz] = rot(x, z, yaw, 0, 0.12);
  b.box(sx, 1.35, sz, 0.66, 0.5, 0.12, 'metal_dark', { rotY: yaw, rotX: -0.35, collide: false });
  const [px, pz] = rot(x, z, yaw, 0, 0.19);
  b.box(px, 1.37, pz, 0.56, 0.4, 0.02, screenOn ? 'screen' : 'glass_dark', { rotY: yaw, rotX: -0.35, collide: false });
  return new THREE.Vector3(px, 1.37, pz);
}

export function pipe(b: LevelBuilder, x1: number, y1: number, z1: number, x2: number, y2: number, z2: number, r: number, mat: MatName = 'metal') {
  const a = new THREE.Vector3(x1, y1, z1), c = new THREE.Vector3(x2, y2, z2);
  const len = a.distanceTo(c);
  const mid = a.clone().add(c).multiplyScalar(0.5);
  const dir = c.clone().sub(a).normalize();
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
  const g = new THREE.CylinderGeometry(r, r, len, 10, 1, true);
  b.geo(g, mat, new THREE.Matrix4().compose(mid, q, new THREE.Vector3(1, 1, 1)), { collide: false });
}

export function railing(b: LevelBuilder, x1: number, z1: number, x2: number, z2: number, y: number, h = 1.05, collide = true) {
  const len = Math.hypot(x2 - x1, z2 - z1);
  const yaw = Math.atan2(x2 - x1, z2 - z1);
  const cx = (x1 + x2) / 2, cz = (z1 + z2) / 2;
  b.box(cx, y + h, cz, 0.06, 0.06, len, 'metal_yellow', { rotY: yaw, collide: false });
  b.box(cx, y + h * 0.5, cz, 0.04, 0.04, len, 'metal_dark', { rotY: yaw, collide: false });
  const n = Math.max(2, Math.round(len / 1.5));
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    b.box(x1 + (x2 - x1) * t, y + h / 2, z1 + (z2 - z1) * t, 0.05, h, 0.05, 'metal_dark', { collide: false });
  }
  if (collide) b.wall(cx, y + 0.6, cz, 0.15, 1.2, len, yaw);
}

export function acUnit(b: LevelBuilder, x: number, y: number, z: number, yaw: number) {
  b.box(x, y + 0.5, z, 1.4, 1.0, 1.0, 'metal', { rotY: yaw });
  const [fx, fz] = rot(x, z, yaw, 0, 0.51);
  b.box(fx, y + 0.5, fz, 0.8, 0.8, 0.02, 'grate', { rotY: yaw, collide: false });
}

export function vent(b: LevelBuilder, x: number, y: number, z: number) {
  b.box(x, y + 0.6, z, 0.9, 1.2, 0.9, 'metal', {});
  b.box(x, y + 1.3, z, 1.2, 0.12, 1.2, 'metal_dark', { collide: false });
}

export function antenna(b: LevelBuilder, x: number, y: number, z: number, h: number) {
  b.cyl(x, y + h / 2, z, 0.05, 0.12, h, 'metal_dark', 6);
  for (let i = 1; i < 4; i++) b.box(x, y + (h * i) / 4, z, 0.9 - i * 0.18, 0.04, 0.04, 'metal_dark', { collide: false });
  b.glowSprite(x, y + h + 0.1, z, 0.6, 0xff3030, 1.2);
}

export function waterTank(b: LevelBuilder, x: number, y: number, z: number) {
  for (const [lx, lz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) b.cyl(x + lx, y + 1.2, z + lz, 0.08, 0.08, 2.4, 'metal_dark', 6);
  b.cyl(x, y + 3.6, z, 1.6, 1.6, 2.4, 'rust', 16);
  b.cyl(x, y + 5.0, z, 0.2, 1.7, 0.5, 'rust', 16, { collide: false });
}

/** Rail car for the metro. */
export function trainCar(b: LevelBuilder, x: number, z: number, yaw: number, seed: number, lit = false) {
  const r = rng(seed);
  b.geo(rbox(16, 3.1, 3.0, 0.6, 3), 'metal_painted', m4(x, 1.85, z, yaw), { colliderBox: new THREE.Box3(new THREE.Vector3(-8, -1.55, -1.5), new THREE.Vector3(8, 1.55, 1.5)) });
  for (const side of [1, -1]) {
    for (let i = -3; i <= 3; i++) {
      const [wx, wz] = rot(x, z, yaw, i * 2.1, side * 1.51);
      b.box(wx, 2.3, wz, 1.5, 0.95, 0.04, lit && r.chance(0.6) ? 'win_warm' : 'glass_dark', { rotY: yaw, collide: false });
    }
    const [sx, sz] = rot(x, z, yaw, 0, side * 1.53);
    b.box(sx, 1.4, sz, 15.4, 0.06, 0.03, 'win_cool', { rotY: yaw, collide: false });
  }
}

/** A city building block with a window grid, ledges and roof parapet. Returns its roof height. */
export function building(b: LevelBuilder, x: number, z: number, w: number, d: number, h: number, seed: number, o: { mat?: MatName; lit?: number; broken?: boolean; faces?: ('n' | 's' | 'e' | 'w')[]; floorH?: number; collide?: boolean } = {}) {
  const r = rng(seed);
  const mat = o.mat ?? r.pick(['concrete', 'plaster', 'concrete_dark', 'brick'] as MatName[]);
  b.box(x, h / 2, z, w, h, d, mat, { collide: o.collide !== false });
  const fh = o.floorH ?? 3.4;
  const floors = Math.floor((h - 1) / fh);
  // Ledges
  for (let f = 1; f <= floors; f++) {
    b.box(x, f * fh, z, w + 0.3, 0.18, d + 0.3, 'concrete_dark', { collide: false, shadow: false });
  }
  // Parapet
  b.box(x, h + 0.45, z - d / 2 + 0.12, w, 0.9, 0.24, mat, { collide: false });
  b.box(x, h + 0.45, z + d / 2 - 0.12, w, 0.9, 0.24, mat, { collide: false });
  b.box(x - w / 2 + 0.12, h + 0.45, z, 0.24, 0.9, d, mat, { collide: false });
  b.box(x + w / 2 - 0.12, h + 0.45, z, 0.24, 0.9, d, mat, { collide: false });
  const faces = o.faces ?? ['n', 's', 'e', 'w'];
  const lit = o.lit ?? 0.08;
  const win = (cx: number, cy: number, cz: number, ww: number, along: 'x' | 'z') => {
    const roll = r.next();
    const m: MatName = roll < lit ? 'win_warm' : roll < lit * 1.3 ? 'win_cool' : o.broken && roll > 0.9 ? 'black' : 'glass_dark';
    if (along === 'x') b.box(cx, cy, cz, ww, 1.5, 0.08, m, { collide: false, shadow: false });
    else b.box(cx, cy, cz, 0.08, 1.5, ww, m, { collide: false, shadow: false });
  };
  for (const face of faces) {
    const along: 'x' | 'z' = face === 'n' || face === 's' ? 'x' : 'z';
    const len = along === 'x' ? w : d;
    const cols = Math.max(1, Math.floor(len / 2.6));
    const step = len / cols;
    for (let f = 0; f < floors; f++) {
      const cy = f * fh + fh * 0.55 + 0.4;
      if (cy < 1.2) continue;
      for (let c = 0; c < cols; c++) {
        const t = -len / 2 + step * (c + 0.5);
        if (face === 'n') win(x + t, cy, z - d / 2 - 0.03, step * 0.6, 'x');
        if (face === 's') win(x + t, cy, z + d / 2 + 0.03, step * 0.6, 'x');
        if (face === 'e') win(x + w / 2 + 0.03, cy, z + t, step * 0.6, 'z');
        if (face === 'w') win(x - w / 2 - 0.03, cy, z + t, step * 0.6, 'z');
      }
    }
  }
  return h;
}

/** Simple doorway frame on a wall face (visual only). */
export function doorFrame(b: LevelBuilder, x: number, z: number, yaw: number, w: number, h: number, lit: MatName | null = 'emit_amber') {
  for (const lx of [-w / 2 - 0.15, w / 2 + 0.15]) {
    const [px, pz] = rot(x, z, yaw, lx, 0);
    b.box(px, h / 2, pz, 0.3, h, 0.5, 'metal_dark', { rotY: yaw, collide: false });
  }
  b.box(x, h + 0.15, z, w + 0.6, 0.3, 0.5, 'metal_dark', { rotY: yaw, collide: false });
  if (lit) b.box(x, h + 0.02, z, w, 0.05, 0.52, lit, { rotY: yaw, collide: false });
}

export function pickRng(seed: number): Rng {
  return rng(seed);
}

export function materialOf(n: MatName) {
  return getMaterial(n);
}
