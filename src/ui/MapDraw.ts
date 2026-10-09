import * as THREE from 'three';
import type { Zone } from '../world/Zone';

// Draws a zone's map (minimap or full map) onto a canvas.

export interface MapDrawOpts {
  center: THREE.Vector3;
  heading: number;
  radius: number;
  round: boolean;
  player: THREE.Vector3 | null;
  playerYaw: number;
  companion: THREE.Vector3 | null;
  npcs: THREE.Vector3[];
  enemies: THREE.Vector3[];
  objective: THREE.Vector3 | null;
  exits: THREE.Vector3[];
  echo: THREE.Vector3[];
  labels?: boolean;
  /** Full map: fit the zone extents instead of following the player. */
  fit?: boolean;
}

export function drawZoneMap(cv: HTMLCanvasElement, zone: Zone, o: MapDrawOpts) {
  const ctx = cv.getContext('2d')!;
  const W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);
  ctx.save();
  if (o.round) {
    ctx.beginPath();
    ctx.arc(W / 2, H / 2, W / 2 - 1, 0, Math.PI * 2);
    ctx.clip();
  }
  ctx.fillStyle = 'rgba(5,8,12,0.85)';
  ctx.fillRect(0, 0, W, H);
  const map = zone.map;
  let scale: number, cx: number, cz: number, rot: number;
  if (o.fit && map) {
    const w = map.max.x - map.min.x, d = map.max.y - map.min.y;
    scale = Math.min(W / w, H / d) * 0.92;
    cx = (map.min.x + map.max.x) / 2;
    cz = (map.min.y + map.max.y) / 2;
    rot = Math.PI; // north (-z) up
  } else {
    scale = (W / 2) / o.radius;
    cx = o.center.x;
    cz = o.center.z;
    rot = o.heading; // camera heading up
  }
  // World (x,z) -> canvas. Rotate so `rot` points up.
  const cr = Math.cos(rot), sr = Math.sin(rot);
  const tx = (x: number, z: number): [number, number] => {
    const dx = x - cx, dz = z - cz;
    // Heading vector (sin r, cos r) maps to screen up (0,-1).
    const rx = dx * cr - dz * sr;
    const rz = dx * sr + dz * cr;
    return [W / 2 - rx * scale, H / 2 - rz * scale];
  };
  if (map) {
    for (const s of map.shapes) {
      ctx.fillStyle = s.kind === 'road' ? 'rgba(60,72,86,0.55)' : s.kind === 'floor' ? 'rgba(96,116,134,0.5)' : s.kind === 'water' ? 'rgba(60,130,170,0.5)' : 'rgba(30,38,48,0.9)';
      const hw = s.w / 2, hd = s.d / 2;
      const r = s.rot ?? 0;
      const pts = [[-hw, -hd], [hw, -hd], [hw, hd], [-hw, hd]].map(([a, b]) => tx(s.x + a * Math.cos(r) + b * Math.sin(r), s.z - a * Math.sin(r) + b * Math.cos(r)));
      ctx.beginPath();
      pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.closePath();
      ctx.fill();
      if (s.kind === 'block') {
        ctx.strokeStyle = 'rgba(140,170,195,0.35)';
        ctx.stroke();
      }
    }
    if (o.labels !== false && (o.fit || scale > 1.5)) {
      ctx.font = `600 ${o.fit ? 13 : 9}px Rajdhani, sans-serif`;
      ctx.textAlign = 'center';
      ctx.fillStyle = 'rgba(200,220,235,0.7)';
      for (const l of map.labels) {
        const [x, y] = tx(l.x, l.z);
        ctx.fillText(l.text, x, y);
      }
    }
  }
  const dot = (p: THREE.Vector3, col: string, r: number, shape: 'circle' | 'diamond' | 'tri' = 'circle') => {
    let [x, y] = tx(p.x, p.z);
    if (o.round && shape === 'diamond') {
      const dx = x - W / 2, dy = y - H / 2;
      const d = Math.hypot(dx, dy);
      const max = W / 2 - 10;
      if (d > max) { x = W / 2 + (dx / d) * max; y = H / 2 + (dy / d) * max; }
    }
    ctx.fillStyle = col;
    ctx.beginPath();
    if (shape === 'circle') ctx.arc(x, y, r, 0, Math.PI * 2);
    else if (shape === 'diamond') { ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); }
    else { ctx.moveTo(x, y - r); ctx.lineTo(x + r, y + r); ctx.lineTo(x - r, y + r); }
    ctx.closePath();
    ctx.fill();
  };
  for (const e of o.exits) dot(e, 'rgba(95,212,240,0.9)', 4, 'tri');
  for (const n of o.npcs) dot(n, '#73e6b0', 3);
  for (const e of o.echo) dot(e, '#c39bff', 3, 'diamond');
  for (const e of o.enemies) dot(e, '#ff5a4a', 3);
  if (o.companion) dot(o.companion, '#a68bff', 3);
  if (o.objective) {
    ctx.shadowColor = '#ffb45e';
    ctx.shadowBlur = 6;
    dot(o.objective, '#ffb45e', 6, 'diamond');
    ctx.shadowBlur = 0;
  }
  if (o.player) {
    const [x, y] = tx(o.player.x, o.player.z);
    // Arrow pointing along the player's yaw in map space.
    const a = o.playerYaw - rot;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(-a + Math.PI);
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.moveTo(0, -8);
    ctx.lineTo(6, 6);
    ctx.lineTo(0, 3);
    ctx.lineTo(-6, 6);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }
  ctx.restore();
  if (o.round) {
    ctx.strokeStyle = 'rgba(130,190,220,0.4)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(W / 2, H / 2, W / 2 - 1, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = '#5fd4f0';
    ctx.font = '700 12px Rajdhani, sans-serif';
    ctx.textAlign = 'center';
    // North indicator rotates with the heading.
    const na = Math.PI - o.heading;
    ctx.fillText('N', W / 2 + Math.sin(na) * (W / 2 - 12) * -1, H / 2 - Math.cos(na) * (H / 2 - 12) + 4);
  }
}
