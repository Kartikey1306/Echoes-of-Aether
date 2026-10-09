import * as THREE from 'three';
import { lerp, smoothstep } from '../../core/MathUtil';
import { field, heightToNormal, makeCanvas, tex, TileNoise } from '../../render/TexGen';
import { HeadShape } from './HeadShape';
import { HAIR_PARAMS, type Look, type MatKey } from './HumanBuilder';

// Character materials and their procedural textures (face, eyes, fabric weave, armor panels, hair strands).

const shared: { fabric?: THREE.Texture; armor?: THREE.Texture; hair?: THREE.Texture; pores?: THREE.Texture; strands?: THREE.Texture } = {};

function fabricNormal(): THREE.Texture {
  if (shared.fabric) return shared.fabric;
  const N = 256;
  const n = new TileNoise(7);
  const h = field(N, (u, v) => {
    // Twill weave plus slub noise.
    const w = Math.sin((u * 64 + v * 64) * Math.PI) * 0.5 + Math.sin(v * 128 * Math.PI) * 0.25;
    return w * 0.6 + n.fbm(u, v, 16, 3) * 0.5;
  });
  shared.fabric = tex(heightToNormal(h, N, 1.6));
  return shared.fabric;
}

function armorNormal(): THREE.Texture {
  if (shared.armor) return shared.armor;
  const N = 256;
  const n = new TileNoise(11);
  const h = field(N, (u, v) => {
    // Fine machining marks with sparse panel grooves and scuffs.
    const groove = Math.min(Math.abs(((u * 2) % 1) - 0.5), Math.abs(((v * 3) % 1) - 0.5));
    const g = groove < 0.012 ? -1 : 0;
    return g * 0.6 + n.fbm(u, v, 32, 3) * 0.12 + n.value(u * 256, v * 4, 256, 4) * 0.05;
  });
  shared.armor = tex(heightToNormal(h, N, 2.2));
  return shared.armor;
}

function hairNormal(): THREE.Texture {
  if (shared.hair) return shared.hair;
  const N = 256;
  const n = new TileNoise(19);
  const h = field(N, (u, v) => n.value(u * 128, v * 6, 128, 6) * 0.8 + n.value(u * 256, v * 12, 256, 12) * 0.3);
  shared.hair = tex(heightToNormal(h, N, 3));
  return shared.hair;
}

/** Alpha mask of individual hair strands for the fringe layer. */
function strandAlpha(): THREE.Texture {
  if (shared.strands) return shared.strands;
  const N = 256;
  const n = new TileNoise(41);
  const [c, ctx] = makeCanvas(N, N);
  const img = ctx.createImageData(N, N);
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const strand = n.value(x * 0.9, y * 0.04, N, Math.ceil(N * 0.04)) * 0.5 + 0.5;
      const breakup = n.value(x * 0.15, y * 0.15, Math.ceil(N * 0.15), Math.ceil(N * 0.15)) * 0.5 + 0.5;
      const a = strand > 0.55 - breakup * 0.25 ? 255 : 0;
      const i = (y * N + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = a;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  shared.strands = tex(c);
  return shared.strands;
}

function poreNormal(): THREE.Texture {
  if (shared.pores) return shared.pores;
  const N = 256;
  const n = new TileNoise(23);
  const h = field(N, (u, v) => n.fbm(u, v, 48, 2) * 0.5);
  shared.pores = tex(heightToNormal(h, N, 0.8), { repeat: 3 });
  return shared.pores;
}

const hexToRgb = (hex: string): [number, number, number] => {
  const c = new THREE.Color(hex);
  // Work in sRGB for painting.
  return [c.r, c.g, c.b].map((x) => (x <= 0.0031308 ? x * 12.92 : 1.055 * Math.pow(x, 1 / 2.4) - 0.055)) as [number, number, number];
};

/** Paint the face texture in the head's spherical UV space using the same sculpt as the mesh. */
export function paintFace(look: Look, size = 512): HTMLCanvasElement {
  const shape = new HeadShape(look.face, 1);
  const f = shape.f;
  const W = size, H = size;
  const [c, ctx] = makeCanvas(W, H);
  const img = ctx.createImageData(W, H);
  const d = img.data;
  const n = new TileNoise(look.id.length * 31 + 5);
  const skin = hexToRgb(look.skin);
  const hair = hexToRgb(look.hair);
  const brow = hexToRgb(f.browColor);
  const lip: [number, number, number] = [skin[0] * 0.86, skin[1] * 0.6, skin[2] * 0.6];
  const dir = new THREE.Vector3();
  const p = new THREE.Vector3();
  const style = look.hairStyle;
  const hpp = style !== 'none' ? HAIR_PARAMS[style] : null;
  const hp: [number, number, number] | null = hpp ? [hpp.front, hpp.side, hpp.back] : null;
  const g = (x: number, y: number, cx: number, cy: number, sx: number, sy: number) => Math.exp(-((x - cx) ** 2) / (2 * sx * sx) - ((y - cy) ** 2) / (2 * sy * sy));
  for (let py = 0; py < H; py++) {
    const theta = ((py + 0.5) / H) * Math.PI;
    for (let px = 0; px < W; px++) {
      const phi = ((px + 0.5) / W) * Math.PI * 2 - Math.PI;
      dir.set(Math.sin(theta) * Math.sin(phi), Math.cos(theta), Math.sin(theta) * Math.cos(phi));
      shape.sculpt(dir, p);
      const x = p.x, y = p.y;
      const ax = Math.abs(x);
      const front = smoothstep(0.1, 0.6, dir.z);
      const u = px / W, v = py / H;
      const mott = n.fbm(u, v, 24, 3) * 0.035;
      let r = skin[0] + mott, gg = skin[1] + mott * 0.9, b = skin[2] + mott * 0.8;
      // Warmth on cheeks, nose and ears; cooler, slightly darker jaw.
      const warm = (g(ax, y, 0.045, -0.02, 0.018, 0.016) * 0.6 + g(x, y, 0, -0.03, 0.008, 0.012) * 0.5) * front;
      r += warm * 0.06; gg -= warm * 0.01; b -= warm * 0.01;
      const jawShade = smoothstep(-0.06, -0.11, y) * 0.06;
      r -= jawShade; gg -= jawShade; b -= jawShade * 0.8;
      if (front > 0) {
        // Eye socket shading and lid lines.
        for (const sx of [1, -1]) {
          const ex = 0.0315 * sx, ey = 0.0078;
          const socket = g(x, y, ex, ey + 0.002, 0.016, 0.012) * 0.14;
          r -= socket * 0.9; gg -= socket; b -= socket * 0.85;
          const dx = (x - ex) / 0.0135, dy = (y - ey) / 0.0085;
          const rr = Math.hypot(dx, dy);
          // Upper-lid crease above the geometric lid (the lash line itself is on the lid mesh);
          // makeup deepens it into soft liner/shadow.
          if (dy > 0 && rr > 1.12 && rr < 1.6) {
            const k = (1 - Math.abs(rr - 1.36) / 0.24) * (0.2 + f.makeup * 0.45);
            r = lerp(r, skin[0] * 0.58, k); gg = lerp(gg, skin[1] * 0.5, k); b = lerp(b, skin[2] * 0.55, k);
          }
          if (dy < 0 && rr > 0.95 && rr < 1.25) {
            const k = (1 - Math.abs(rr - 1.1) / 0.15) * 0.1;
            r = lerp(r, skin[0] * 0.62, k); gg = lerp(gg, skin[1] * 0.56, k); b = lerp(b, skin[2] * 0.6, k);
          }
          // Brows
          const bx = (x - sx * 0.012) * sx;
          if (bx > -0.002 && bx < 0.046) {
            const by = 0.027 + 0.007 * Math.sin((bx / 0.046) * Math.PI * 0.85) - bx * 0.06;
            const thick = (f.female ? 0.0042 : 0.0062) * (1 - bx / 0.075);
            const dyb = Math.abs(y - by);
            if (dyb < thick) {
              const strand = 0.82 + 0.18 * n.value(px * 0.9, py * 0.25, W, H);
              const k = smoothstep(0, 0.6, 1 - dyb / thick) * strand * 0.85;
              r = lerp(r, brow[0], k); gg = lerp(gg, brow[1], k); b = lerp(b, brow[2], k);
            }
          }
        }
        // Lips and mouth line
        const lips = Math.min(1, g(x, y, 0, -0.0585, 0.018 * (f.female ? 1.05 : 1), 0.0042) + g(x, y, 0, -0.0675, 0.0155, 0.0048)) * (f.female ? 0.55 : 0.35);
        r = lerp(r, lip[0], lips); gg = lerp(gg, lip[1], lips); b = lerp(b, lip[2], lips);
        const mouth = g(x, y, 0, -0.063, 0.017, 0.0009) * smoothstep(0.022, 0.01, ax);
        r = lerp(r, skin[0] * 0.45, mouth * 0.55); gg = lerp(gg, skin[1] * 0.35, mouth * 0.55); b = lerp(b, skin[2] * 0.35, mouth * 0.55);
        // Soft baked occlusion: under the nose, under the lower lip, beside the nose.
        const ao = g(x, y, 0, -0.045, 0.012, 0.004) * 0.06 + g(x, y, 0, -0.077, 0.016, 0.005) * 0.07 + (g(x, y, 0.016, -0.03, 0.006, 0.012) + g(x, y, -0.016, -0.03, 0.006, 0.012)) * 0.05;
        r -= ao; gg -= ao; b -= ao * 0.9;
        // Nostrils
        const nos = g(ax, y, 0.0085, -0.0395, 0.0026, 0.0018) * 0.3;
        r = lerp(r, skin[0] * 0.4, nos); gg = lerp(gg, skin[1] * 0.3, nos); b = lerp(b, skin[2] * 0.3, nos);
        // Stubble (a fine shadow tint) and beard (hair-coloured coverage)
        const beardZone = smoothstep(-0.03, -0.05, y) * smoothstep(-0.118, -0.095, y) * smoothstep(0.075, 0.05, ax) * (1 - Math.min(1, lips * 2.2));
        const lipZone = g(x, y, 0, -0.051, 0.018, 0.0035) * 0.8;
        const zoneAll = Math.min(1, beardZone + lipZone);
        if (f.stubble > 0 && zoneAll > 0) {
          const dots = n.value(px * 2.1, py * 2.1, W * 3, H * 3) * 0.5 + 0.5;
          const k = zoneAll * f.stubble * (0.1 + dots * 0.12);
          r = lerp(r, skin[0] * 0.55, k); gg = lerp(gg, skin[1] * 0.55, k); b = lerp(b, skin[2] * 0.62, k);
        }
        if (f.beard > 0 && zoneAll > 0) {
          const strands = n.value(px * 1.2, py * 3.5, W * 2, H * 4) * 0.5 + 0.5;
          const k = Math.min(1, zoneAll * 1.3) * f.beard * (0.55 + strands * 0.4);
          r = lerp(r, hair[0], k); gg = lerp(gg, hair[1], k); b = lerp(b, hair[2], k);
        }
        // Freckles across the nose and cheeks
        if (f.freckles > 0) {
          const zone = Math.max(g(x, y, 0.035, -0.012, 0.022, 0.014), g(x, y, -0.035, -0.012, 0.022, 0.014), g(x, y, 0, -0.012, 0.012, 0.01));
          const dots = n.value(px * 2.3 + 17, py * 2.3 + 5, W * 3, H * 3);
          if (dots > 0.62 && zone > 0.25) {
            const k = (dots - 0.62) * 2.2 * zone * f.freckles;
            r = lerp(r, skin[0] * 0.62, k); gg = lerp(gg, skin[1] * 0.5, k); b = lerp(b, skin[2] * 0.45, k);
          }
        }
        // Scar (character's left brow down onto the cheek)
        if (f.scar) {
          const ax0 = 0.052, ay0 = 0.045, ax1 = 0.038, ay1 = -0.006;
          const t = Math.max(0, Math.min(1, ((x - ax0) * (ax1 - ax0) + (y - ay0) * (ay1 - ay0)) / ((ax1 - ax0) ** 2 + (ay1 - ay0) ** 2)));
          const dd = Math.hypot(x - lerp(ax0, ax1, t), y - lerp(ay0, ay1, t));
          if (dd < 0.0024 && t > 0.02 && t < 0.98) {
            const k = 1 - dd / 0.0024;
            r = lerp(r, skin[0] * 1.12 + 0.04, k * 0.8); gg = lerp(gg, skin[1] * 0.92, k * 0.8); b = lerp(b, skin[2] * 0.95, k * 0.8);
            if (dd > 0.0014) { r -= 0.05 * k; gg -= 0.05 * k; b -= 0.04 * k; }
          }
        }
        // Age lines
        if (f.age > 0) {
          const fore = smoothstep(0.045, 0.06, y) * smoothstep(0.09, 0.07, y) * (Math.abs(Math.sin(y * 900)) < 0.15 ? 1 : 0) * smoothstep(0.05, 0.02, ax);
          const fold = g(ax, y, 0.022 + (-0.04 - y) * 0.25, -0.045, 0.0016, 0.012);
          const k = (fore * 0.5 + fold * 0.6) * f.age * 0.3;
          r -= k; gg -= k; b -= k * 0.9;
        }
      }
      // Hair colour near/above the hairline so gaps never show bare scalp.
      if (hp && style !== 'none') {
        const a = Math.abs(phi) / Math.PI;
        const tmax = a < 0.5 ? lerp(hp[0], hp[1], smoothstep(0, 0.5, a)) : lerp(hp[1], hp[2], smoothstep(0.5, 1, a));
        const k = smoothstep(tmax * Math.PI + 0.03, tmax * Math.PI - 0.06, theta);
        const hcCol = style === 'hood' ? [0.08, 0.08, 0.09] : hair;
        r = lerp(r, hcCol[0], k); gg = lerp(gg, hcCol[1], k); b = lerp(b, hcCol[2], k);
      }
      const i = (py * W + px) * 4;
      d[i] = Math.max(0, Math.min(255, r * 255));
      d[i + 1] = Math.max(0, Math.min(255, gg * 255));
      d[i + 2] = Math.max(0, Math.min(255, b * 255));
      d[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return c;
}

export function paintEye(irisHex: string, size = 128): HTMLCanvasElement {
  const [c, ctx] = makeCanvas(size, size / 2);
  const W = size, H = size / 2;
  const img = ctx.createImageData(W, H);
  const d = img.data;
  const iris = hexToRgb(irisHex);
  const n = new TileNoise(3);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      // Angular distance from the front (u=0.5, v=0.5).
      const phi = (x / W) * Math.PI * 2 - Math.PI;
      const theta = (y / H) * Math.PI - Math.PI / 2;
      const ang = Math.hypot(phi, theta);
      let r = 0.8, g = 0.78, b = 0.74;
      r -= smoothstep(0.6, 1.4, ang) * 0.12; g -= smoothstep(0.6, 1.4, ang) * 0.14; b -= smoothstep(0.6, 1.4, ang) * 0.1;
      if (ang < 0.5) {
        const fib = 0.75 + 0.25 * n.value(Math.atan2(theta, phi) * 12 + 50, ang * 8, 256, 256);
        const k = smoothstep(0.5, 0.42, ang);
        const limb = smoothstep(0.32, 0.48, ang) * 0.5;
        r = lerp(r, iris[0] * fib * (1 - limb), k);
        g = lerp(g, iris[1] * fib * (1 - limb), k);
        b = lerp(b, iris[2] * fib * (1 - limb), k);
      }
      if (ang < 0.2) {
        const k = smoothstep(0.2, 0.16, ang);
        r = lerp(r, 0.02, k); g = lerp(g, 0.02, k); b = lerp(b, 0.025, k);
      }
      const i = (y * W + x) * 4;
      d[i] = r * 255; d[i + 1] = g * 255; d[i + 2] = b * 255; d[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return c;
}

export type HumanMaterials = Record<MatKey, THREE.Material>;

export function createHumanMaterials(look: Look, faceSize = 512): HumanMaterials {
  const faceTex = tex(paintFace(look, faceSize), { srgb: true });
  faceTex.wrapS = THREE.RepeatWrapping;
  faceTex.wrapT = THREE.ClampToEdgeWrapping;
  const eyeTex = tex(paintEye(look.eyes), { srgb: true });
  const glowCol = new THREE.Color(1, 1, 1).multiplyScalar(2.6);
  const skinSheen = new THREE.Color(0xff8f78);
  return {
    skin: new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.55, metalness: 0, sheen: 0.35, sheenColor: skinSheen, sheenRoughness: 0.55, name: 'skin' }),
    face: new THREE.MeshPhysicalMaterial({ map: faceTex, roughness: 0.52, metalness: 0, normalMap: poreNormal(), normalScale: new THREE.Vector2(0.25, 0.25), sheen: 0.35, sheenColor: skinSheen, sheenRoughness: 0.55, name: 'face' }),
    cloth: new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.82, metalness: 0.02, normalMap: fabricNormal(), normalScale: new THREE.Vector2(0.55, 0.55), sheen: 0.5, sheenColor: new THREE.Color(0x9aa6b4), sheenRoughness: 0.8, name: 'cloth' }),
    armor: new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.42, metalness: 0.5, normalMap: armorNormal(), normalScale: new THREE.Vector2(0.4, 0.4), clearcoat: 0.35, clearcoatRoughness: 0.35, name: 'armor' }),
    metal: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.3, metalness: 0.9, name: 'metal' }),
    glow: new THREE.MeshBasicMaterial({ vertexColors: true, color: glowCol, name: 'glow' }),
    hair: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.48, metalness: 0.05, normalMap: hairNormal(), normalScale: new THREE.Vector2(0.7, 0.7), name: 'hair' }),
    hairfx: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.5, metalness: 0.05, alphaMap: strandAlpha(), alphaTest: 0.5, side: THREE.DoubleSide, name: 'hairfx' }),
    eye: new THREE.MeshPhysicalMaterial({ map: eyeTex, roughness: 0.1, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.05, name: 'eye' }),
  };
}
