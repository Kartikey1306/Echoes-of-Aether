import type { MatName } from '../../render/Materials';
import type { LevelBuilder } from './LevelBuilder';

// Interior room construction with door openings. Sides: n = min z, s = max z, w = min x, e = max x.

export type Side = 'n' | 's' | 'e' | 'w';
export interface Door { side: Side; at: number; w: number; h?: number }
export interface RoomOpts {
  floor: MatName;
  wall: MatName;
  ceiling?: MatName | null;
  doors?: Door[];
  skip?: Side[];
  thick?: number;
  y?: number;
  /** Emissive ceiling light panels. */
  panels?: MatName | null;
  trim?: MatName | null;
}

export function room(b: LevelBuilder, x0: number, z0: number, x1: number, z1: number, h: number, o: RoomOpts) {
  const t = o.thick ?? 0.4;
  const y = o.y ?? 0;
  const cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
  b.box(cx, y - 0.25, cz, x1 - x0, 0.5, z1 - z0, o.floor);
  if (o.ceiling !== null) b.box(cx, y + h + 0.25, cz, x1 - x0 + t * 2, 0.5, z1 - z0 + t * 2, o.ceiling ?? 'concrete_dark', { collide: false });
  const sides: Side[] = ['n', 's', 'e', 'w'];
  for (const side of sides) {
    if (o.skip?.includes(side)) continue;
    const along = side === 'n' || side === 's';
    const a0 = along ? x0 - t : z0 - t;
    const a1 = along ? x1 + t : z1 + t;
    const fixed = side === 'n' ? z0 - t / 2 : side === 's' ? z1 + t / 2 : side === 'w' ? x0 - t / 2 : x1 + t / 2;
    const doors = (o.doors ?? []).filter((d) => d.side === side).sort((p, q) => p.at - q.at);
    let cur = a0;
    const seg = (s0: number, s1: number, yb: number, yt: number) => {
      if (s1 - s0 < 0.01 || yt - yb < 0.01) return;
      const mid = (s0 + s1) / 2, len = s1 - s0;
      if (along) b.box(mid, y + (yb + yt) / 2, fixed, len, yt - yb, t, o.wall);
      else b.box(fixed, y + (yb + yt) / 2, mid, t, yt - yb, len, o.wall);
    };
    for (const d of doors) {
      const d0 = d.at - d.w / 2, d1 = d.at + d.w / 2;
      seg(cur, d0, 0, h);
      seg(d0, d1, d.h ?? Math.min(h, 3), h);
      cur = d1;
    }
    seg(cur, a1, 0, h);
    if (o.trim) {
      // Baseboard trim
      if (along) b.box((a0 + a1) / 2, y + 0.08, fixed + (side === 'n' ? t / 2 + 0.02 : -t / 2 - 0.02), a1 - a0, 0.16, 0.04, o.trim, { collide: false, shadow: false });
      else b.box(fixed + (side === 'w' ? t / 2 + 0.02 : -t / 2 - 0.02), y + 0.08, (a0 + a1) / 2, 0.04, 0.16, a1 - a0, o.trim, { collide: false, shadow: false });
    }
  }
  if (o.panels) {
    for (let x = x0 + 2.5; x < x1 - 1; x += 5) for (let z = z0 + 2.5; z < z1 - 1; z += 5) b.box(x, y + h - 0.02, z, 1.6, 0.04, 0.6, o.panels, { collide: false, shadow: false });
  }
}

/** Glass partition with a metal frame. */
export function glassWall(b: LevelBuilder, x0: number, z0: number, x1: number, z1: number, h: number, y = 0) {
  const len = Math.hypot(x1 - x0, z1 - z0);
  const yaw = Math.atan2(x1 - x0, z1 - z0);
  const cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
  b.box(cx, y + h / 2, cz, 0.05, h, len, 'glass', { rotY: yaw });
  b.box(cx, y + 0.05, cz, 0.12, 0.1, len, 'metal_dark', { rotY: yaw, collide: false });
  b.box(cx, y + h, cz, 0.12, 0.1, len, 'metal_dark', { rotY: yaw, collide: false });
  const n = Math.max(1, Math.round(len / 2.5));
  for (let i = 0; i <= n; i++) {
    const k = i / n;
    b.box(x0 + (x1 - x0) * k, y + h / 2, z0 + (z1 - z0) * k, 0.08, h, 0.08, 'metal_dark', { collide: false });
  }
}

/** Lab bench with equipment. */
export function labBench(b: LevelBuilder, x: number, z: number, yaw: number, seed: number) {
  b.box(x, 0.45, z, 2.4, 0.9, 0.9, 'panel_lab', { rotY: yaw });
  b.box(x, 0.92, z, 2.5, 0.05, 1.0, 'metal', { rotY: yaw, collide: false });
  const r = (k: number) => {
    const s = Math.sin(seed * 12.9898 + k * 78.233) * 43758.5453;
    return s - Math.floor(s);
  };
  for (let i = 0; i < 3; i++) {
    const lx = (r(i) - 0.5) * 1.8, h = 0.15 + r(i + 5) * 0.3;
    const c = Math.cos(yaw), sn = Math.sin(yaw);
    b.cyl(x + lx * c, 0.95 + h / 2, z - lx * sn, 0.06 + r(i + 9) * 0.06, 0.08, h, r(i + 3) > 0.5 ? 'glass' : 'metal', 10, { collide: false });
  }
}

export function serverRack(b: LevelBuilder, x: number, z: number, yaw: number, lit = true) {
  b.box(x, 1.1, z, 0.8, 2.2, 1.0, 'metal_dark', { rotY: yaw });
  for (let i = 0; i < 6; i++) b.box(x + Math.sin(yaw) * 0.51, 0.4 + i * 0.32, z + Math.cos(yaw) * 0.51, 0.6, 0.04, 0.02, lit && i % 2 === 0 ? 'emit_green' : 'emit_cyan', { rotY: yaw, collide: false, shadow: false });
}

export function pod(b: LevelBuilder, x: number, z: number, glowing: boolean) {
  b.cyl(x, 0.2, z, 0.75, 0.85, 0.4, 'metal_dark', 16);
  b.cyl(x, 1.4, z, 0.6, 0.6, 2.0, 'glass', 16, { collide: false });
  b.cyl(x, 2.55, z, 0.75, 0.7, 0.3, 'metal_dark', 16);
  if (glowing) b.cyl(x, 1.3, z, 0.35, 0.35, 1.4, 'aether', 12, { collide: false });
  b.solidCollider(x, 1.4, z, 1.2, 2.8, 1.2);
}
