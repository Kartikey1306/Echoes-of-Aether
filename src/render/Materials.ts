import * as THREE from 'three';
import { field, heightToNormal, makeCanvas, paint, tex, TexQuality, TileNoise } from './TexGen';

// Procedural PBR material library. Textures are generated once per quality level and shared.
// All world geometry uses world-scale UVs: 1 UV unit = 1 metre, so `scale` controls texture size in metres.

export type MatName =
  | 'concrete' | 'concrete_dark' | 'concrete_wet' | 'asphalt' | 'paving' | 'curb' | 'plaster' | 'brick'
  | 'metal' | 'metal_dark' | 'metal_painted' | 'metal_red' | 'metal_yellow' | 'rust' | 'grate'
  | 'tile_lab' | 'floor_lab' | 'panel_lab' | 'glass' | 'glass_dark' | 'rubber' | 'wood' | 'tarp' | 'tarp_blue'
  | 'emit_cyan' | 'emit_violet' | 'emit_warm' | 'emit_red' | 'emit_white' | 'emit_amber' | 'emit_green' | 'win_warm' | 'win_cool'
  | 'water' | 'aether' | 'black' | 'screen' | 'vehicle' | 'vehicle_dark' | 'rock' | 'cable';

interface TexSet { map?: THREE.Texture; normalMap?: THREE.Texture; roughnessMap?: THREE.Texture }

const cache = new Map<string, THREE.Material>();
const texCache = new Map<string, TexSet>();
let timeUniform = { value: 0 };
let rainUniform = { value: 1 };

export function materialTime(t: number) {
  timeUniform.value = t;
}
export function setWetness(w: number) {
  rainUniform.value = w;
}

function srgb(r: number, g: number, b: number): [number, number, number] {
  return [r, g, b];
}

/** Build albedo + normal + roughness textures from a height function and colour function. */
function texSet(key: string, opts: {
  height: (u: number, v: number) => number;
  color: (u: number, v: number, h: number) => [number, number, number];
  rough: (u: number, v: number, h: number) => number;
  normalStrength: number;
}): TexSet {
  const k = key + ':' + TexQuality.size;
  const hit = texCache.get(k);
  if (hit) return hit;
  const N = TexQuality.size;
  const h = field(N, opts.height);
  const albedo = paint(N, (u, v, x, y) => opts.color(u, v, h[y * N + x]));
  const rough = paint(N, (u, v, x, y) => {
    const r = opts.rough(u, v, h[y * N + x]);
    return [1, r, 0];
  });
  const set: TexSet = {
    map: tex(albedo, { srgb: true, aniso: TexQuality.aniso }),
    normalMap: tex(heightToNormal(h, N, opts.normalStrength * (N / 512)), { aniso: TexQuality.aniso }),
    roughnessMap: tex(rough, { aniso: TexQuality.aniso }),
  };
  texCache.set(k, set);
  return set;
}

const nA = new TileNoise(101), nB = new TileNoise(202), nC = new TileNoise(303);

function concreteSet(variant: 'light' | 'dark' | 'wet') {
  return texSet('concrete_' + variant, {
    height: (u, v) => nA.fbm(u, v, 8, 5) * 0.6 + nB.fbm(u, v, 32, 3) * 0.25 - (nC.ridged(u, v, 4, 3) > 0.92 ? 0.8 : 0),
    color: (u, v, h) => {
      const base = variant === 'dark' ? 0.2 : variant === 'wet' ? 0.24 : 0.36;
      const stain = nC.fbm(u, v, 3, 4) * 0.08;
      const c = base + h * 0.06 + stain;
      return srgb(c * 0.98, c, c * 1.03);
    },
    rough: (u, v, h) => {
      const puddle = variant === 'wet' ? Math.max(0, nB.fbm(u + 0.3, v, 2, 3) * 2.2 - 0.35) : 0;
      return Math.max(0.12, Math.min(1, (variant === 'wet' ? 0.62 : 0.86) + h * 0.15 - Math.min(0.55, puddle)));
    },
    normalStrength: 2.2,
  });
}

function asphaltSet() {
  return texSet('asphalt', {
    height: (u, v) => nA.fbm(u, v, 48, 3) * 0.5 + nB.fbm(u, v, 6, 4) * 0.3 - (nC.ridged(u, v, 3, 4) > 0.94 ? 0.7 : 0),
    color: (u, v, h) => {
      const c = 0.13 + h * 0.04 + nC.fbm(u, v, 2, 3) * 0.03;
      return srgb(c, c, c * 1.04);
    },
    rough: (u, v, h) => {
      const puddle = Math.max(0, nB.fbm(u, v + 0.5, 2, 3) * 2.4 - 0.3);
      return Math.max(0.08, Math.min(1, 0.72 + h * 0.1 - Math.min(0.62, puddle)));
    },
    normalStrength: 2.6,
  });
}

function pavingSet() {
  return texSet('paving', {
    height: (u, v) => {
      // 4x4 large slabs with grout lines and wear.
      const gu = (u * 4) % 1, gv = (v * 4) % 1;
      const grout = Math.min(gu, 1 - gu, gv, 1 - gv) < 0.012 ? -1 : 0;
      return grout * 0.35 + nA.fbm(u, v, 16, 3) * 0.25;
    },
    color: (u, v, h) => {
      const tile = Math.floor(u * 4) * 7 + Math.floor(v * 4) * 13;
      const tint = ((tile * 2654435761) % 100) / 100;
      const stain = Math.max(0, nC.fbm(u * 0.5, v * 0.5, 3, 4)) * 0.12;
      const c = (h < -0.2 ? 0.2 : 0.3 + tint * 0.07) + nC.fbm(u, v, 4, 3) * 0.05 - stain;
      return srgb(c * 0.97, c * 0.99, c * 1.04);
    },
    rough: (u, v, h) => {
      const puddle = Math.max(0, nB.fbm(u, v, 2, 3) * 2.2 - 0.32);
      return Math.max(0.1, Math.min(1, (h < -0.2 ? 0.9 : 0.62) - Math.min(0.5, puddle)));
    },
    normalStrength: 1.6,
  });
}

function metalPanelSet(key: string, base: [number, number, number], rustAmt: number) {
  return texSet('metal_' + key, {
    height: (u, v) => {
      const gu = (u * 2) % 1, gv = (v * 2) % 1;
      const seam = Math.min(gu, 1 - gu, gv, 1 - gv) < 0.01 ? -1 : 0;
      const rivet = (Math.hypot(gu - 0.04, gv - 0.04) < 0.012 || Math.hypot(gu - 0.96, gv - 0.04) < 0.012) ? 0.6 : 0;
      return seam * 0.6 + rivet + nA.fbm(u, v, 24, 3) * 0.08;
    },
    color: (u, v, h) => {
      const rust = Math.max(0, nB.fbm(u, v, 4, 4) * 2 - (1 - rustAmt) * 1.3) * rustAmt;
      const dirt = nC.fbm(u, v, 3, 3) * 0.06;
      const r = base[0] * (1 - rust) + 0.32 * rust + dirt;
      const g = base[1] * (1 - rust) + 0.16 * rust + dirt;
      const b = base[2] * (1 - rust) + 0.08 * rust + dirt;
      return srgb(r, g, b);
    },
    rough: (u, v) => 0.38 + nB.fbm(u, v, 4, 4) * 0.25 + nA.fbm(u, v, 32, 2) * 0.1,
    normalStrength: 2.5,
  });
}

function rustSet() {
  return texSet('rust', {
    height: (u, v) => nA.fbm(u, v, 12, 5) * 0.8,
    color: (u, v, h) => {
      const k = nB.fbm(u, v, 6, 4) * 0.5 + 0.5;
      return srgb(0.22 + k * 0.18, 0.11 + k * 0.08, 0.06 + k * 0.03);
    },
    rough: (u, v, h) => 0.75 + h * 0.2,
    normalStrength: 3,
  });
}

function tileSet(key: string, rows: number, base: number, grout: number) {
  return texSet('tile_' + key, {
    height: (u, v) => {
      const gu = (u * rows) % 1, gv = (v * rows) % 1;
      return (Math.min(gu, 1 - gu, gv, 1 - gv) < 0.03 ? -1 : 0) * 0.5 + nA.fbm(u, v, 32, 2) * 0.05;
    },
    color: (u, v, h) => {
      const c = h < -0.3 ? grout : base + nC.fbm(u, v, 4, 3) * 0.04;
      return srgb(c * 0.97, c * 0.99, c);
    },
    rough: (u, v, h) => (h < -0.3 ? 0.9 : 0.28 + nB.fbm(u, v, 8, 2) * 0.1),
    normalStrength: 2,
  });
}

function grateSet() {
  return texSet('grate', {
    height: (u, v) => {
      const gu = (u * 8) % 1, gv = (v * 16) % 1;
      return gu < 0.15 || gv < 0.2 ? 1 : -1;
    },
    color: (u, v, h) => (h > 0 ? srgb(0.28, 0.28, 0.27) : srgb(0.03, 0.03, 0.03)),
    rough: (u, v, h) => (h > 0 ? 0.5 : 1),
    normalStrength: 1.4,
  });
}

function plasterSet() {
  return texSet('plaster', {
    height: (u, v) => nA.fbm(u, v, 10, 5) * 0.4 + (nC.ridged(u, v, 3, 4) > 0.93 ? -0.6 : 0),
    color: (u, v, h) => {
      const stain = Math.max(0, nB.fbm(u, v * 0.5, 3, 4)) * 0.12 * (1 - v);
      const c = 0.42 + h * 0.05 - stain;
      return srgb(c * 0.97, c * 0.96, c * 0.94);
    },
    rough: () => 0.88,
    normalStrength: 1.6,
  });
}

function brickSet() {
  return texSet('brick', {
    height: (u, v) => {
      const row = Math.floor(v * 16);
      const uu = (u * 8 + (row % 2) * 0.5) % 1;
      const vv = (v * 16) % 1;
      return (uu < 0.05 || vv < 0.1 ? -1 : 0) * 0.6 + nA.fbm(u, v, 32, 3) * 0.15;
    },
    color: (u, v, h) => {
      const row = Math.floor(v * 16), col = Math.floor(u * 8 + (row % 2) * 0.5);
      const tint = (((row * 31 + col * 17) * 2654435761) % 100) / 100;
      return h < -0.5 ? srgb(0.16, 0.15, 0.14) : srgb(0.3 + tint * 0.08, 0.15 + tint * 0.04, 0.11);
    },
    rough: (u, v, h) => (h < -0.5 ? 0.95 : 0.8),
    normalStrength: 2.4,
  });
}

function woodSet() {
  return texSet('wood', {
    height: (u, v) => Math.sin(u * 60 + nA.fbm(u, v, 4, 3) * 6) * 0.3 + ((v * 4) % 1 < 0.02 ? -1 : 0),
    color: (u, v, h) => srgb(0.26 + h * 0.04, 0.17 + h * 0.03, 0.1),
    rough: () => 0.82,
    normalStrength: 1.5,
  });
}

function tarpSet(r: number, g: number, b: number, key: string) {
  return texSet('tarp_' + key, {
    height: (u, v) => nA.fbm(u, v, 6, 4) * 0.6 + Math.sin(u * 30 + v * 8) * 0.1,
    color: (u, v, h) => srgb(r + h * 0.04, g + h * 0.04, b + h * 0.04),
    rough: () => 0.7,
    normalStrength: 2,
  });
}

function rockSet() {
  return texSet('rock', {
    height: (u, v) => nA.ridged(u, v, 6, 5),
    color: (u, v, h) => srgb(0.18 + h * 0.08, 0.17 + h * 0.08, 0.18 + h * 0.08),
    rough: () => 0.9,
    normalStrength: 3.5,
  });
}

function std(name: string, set: TexSet, params: THREE.MeshStandardMaterialParameters, scale = 1): THREE.MeshStandardMaterial {
  const m = new THREE.MeshStandardMaterial({ ...params, ...set, name });
  for (const t of [m.map, m.normalMap, m.roughnessMap]) if (t) t.repeat.set(1 / scale, 1 / scale);
  return m;
}

/** Adds animated rain ripples to the normal of low-roughness (puddle) areas. */
function addRipples(m: THREE.MeshStandardMaterial) {
  m.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = timeUniform;
    shader.uniforms.uRain = rainUniform;
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWPos;')
      .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\nvWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
        uniform float uTime; uniform float uRain; varying vec3 vWPos;
        vec2 rippleHash(vec2 p){ p = vec2(dot(p,vec2(127.1,311.7)), dot(p,vec2(269.5,183.3))); return fract(sin(p)*43758.5453); }
        vec2 ripples(vec2 uv){
          vec2 acc = vec2(0.0);
          for (int i = 0; i < 2; i++) {
            vec2 cell = floor(uv); vec2 f = fract(uv);
            for (int y=-1; y<=1; y++) for (int x=-1; x<=1; x++) {
              vec2 o = vec2(float(x), float(y));
              vec2 h = rippleHash(cell + o + float(i)*17.0);
              float t = fract(uTime * (0.6 + h.x*0.5) + h.y);
              vec2 d = o + h - f;
              float r = length(d);
              float ring = sin((r - t*0.9) * 40.0) * smoothstep(0.9, 0.0, t) * smoothstep(0.0, 0.08, r) * smoothstep(t*0.9+0.08, t*0.9, r);
              acc += normalize(d + 1e-4) * ring;
            }
            uv = uv * 1.7 + 3.1;
          }
          return acc;
        }`)
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
        {
          float wetMask = 1.0 - smoothstep(0.2, 0.45, roughnessFactor);
          if (wetMask > 0.01 && uRain > 0.01 && vNormal.y > 0.0) {
            vec2 rp = ripples(vWPos.xz * 2.2) * 0.35 * wetMask * uRain;
            normal = normalize(normal + vec3(rp.x, 0.0, rp.y) * 0.6);
          }
        }`);
  };
  m.customProgramCacheKey = () => 'ripples';
}

function emissive(name: string, color: number, intensity: number): THREE.MeshBasicMaterial {
  const m = new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(intensity), name });
  return m;
}

export function getMaterial(name: MatName): THREE.Material {
  const key = name + ':' + TexQuality.size;
  const hit = cache.get(key);
  if (hit) return hit;
  let m: THREE.Material;
  switch (name) {
    case 'concrete': m = std(name, concreteSet('light'), { roughness: 1, metalness: 0 }, 3); break;
    case 'concrete_dark': m = std(name, concreteSet('dark'), { roughness: 1, metalness: 0 }, 3); break;
    case 'concrete_wet': m = std(name, concreteSet('wet'), { roughness: 1, metalness: 0 }, 4); addRipples(m as THREE.MeshStandardMaterial); break;
    case 'asphalt': m = std(name, asphaltSet(), { roughness: 1, metalness: 0 }, 5); addRipples(m as THREE.MeshStandardMaterial); break;
    case 'paving': m = std(name, pavingSet(), { roughness: 1, metalness: 0 }, 6); addRipples(m as THREE.MeshStandardMaterial); break;
    case 'curb': m = std(name, concreteSet('light'), { roughness: 0.9, metalness: 0, color: 0xb8b8b8 }, 1.5); break;
    case 'plaster': m = std(name, plasterSet(), { roughness: 1, metalness: 0 }, 4); break;
    case 'brick': m = std(name, brickSet(), { roughness: 1, metalness: 0 }, 3); break;
    case 'metal': m = std(name, metalPanelSet('plain', [0.42, 0.43, 0.45], 0.15), { roughness: 1, metalness: 0.75 }, 2); break;
    case 'metal_dark': m = std(name, metalPanelSet('dark', [0.2, 0.21, 0.23], 0.1), { roughness: 1, metalness: 0.45 }, 2); break;
    case 'metal_painted': m = std(name, metalPanelSet('painted', [0.22, 0.27, 0.3], 0.35), { roughness: 1, metalness: 0.35 }, 2); break;
    case 'metal_red': m = std(name, metalPanelSet('red', [0.38, 0.08, 0.06], 0.3), { roughness: 1, metalness: 0.3 }, 2); break;
    case 'metal_yellow': m = std(name, metalPanelSet('yellow', [0.55, 0.42, 0.08], 0.3), { roughness: 1, metalness: 0.3 }, 2); break;
    case 'rust': m = std(name, rustSet(), { roughness: 1, metalness: 0.4 }, 2); break;
    case 'grate': m = std(name, grateSet(), { roughness: 1, metalness: 0.8 }, 1); break;
    case 'tile_lab': m = std(name, tileSet('lab', 4, 0.62, 0.3), { roughness: 1, metalness: 0 }, 1.2); break;
    case 'floor_lab': m = std(name, tileSet('floor', 2, 0.36, 0.2), { roughness: 1, metalness: 0.05 }, 2); break;
    case 'panel_lab': m = std(name, metalPanelSet('lab', [0.58, 0.6, 0.62], 0.0), { roughness: 1, metalness: 0.2 }, 2.5); break;
    case 'glass': m = new THREE.MeshPhysicalMaterial({ name, color: 0x8fb4c8, roughness: 0.05, metalness: 0, transparent: true, opacity: 0.22, envMapIntensity: 1.4, depthWrite: false, side: THREE.DoubleSide }); break;
    case 'glass_dark': m = new THREE.MeshStandardMaterial({ name, color: 0x0b1218, roughness: 0.08, metalness: 0.6, envMapIntensity: 1.5 }); break;
    case 'rubber': m = new THREE.MeshStandardMaterial({ name, color: 0x111111, roughness: 0.85 }); break;
    case 'wood': m = std(name, woodSet(), { roughness: 1, metalness: 0 }, 1.5); break;
    case 'tarp': m = std(name, tarpSet(0.22, 0.24, 0.2, 'olive'), { roughness: 1, metalness: 0, side: THREE.DoubleSide }, 2); break;
    case 'tarp_blue': m = std(name, tarpSet(0.1, 0.16, 0.24, 'blue'), { roughness: 1, metalness: 0, side: THREE.DoubleSide }, 2); break;
    case 'rock': m = std(name, rockSet(), { roughness: 1, metalness: 0 }, 4); break;
    case 'vehicle': m = new THREE.MeshStandardMaterial({ name, color: 0x5a6068, roughness: 0.35, metalness: 0.6 }); break;
    case 'vehicle_dark': m = new THREE.MeshStandardMaterial({ name, color: 0x23272c, roughness: 0.45, metalness: 0.5 }); break;
    case 'cable': m = new THREE.MeshStandardMaterial({ name, color: 0x0d0d0f, roughness: 0.6 }); break;
    case 'black': m = new THREE.MeshStandardMaterial({ name, color: 0x050505, roughness: 0.9 }); break;
    case 'emit_cyan': m = emissive(name, 0x5fd8ff, 3.2); break;
    case 'emit_violet': m = emissive(name, 0xa47dff, 3.0); break;
    case 'emit_warm': m = emissive(name, 0xffb46a, 3.2); break;
    case 'emit_red': m = emissive(name, 0xff3a2e, 3.0); break;
    case 'emit_white': m = emissive(name, 0xe8f2ff, 2.6); break;
    case 'emit_amber': m = emissive(name, 0xffa21f, 2.8); break;
    case 'emit_green': m = emissive(name, 0x52ff9a, 2.6); break;
    case 'win_warm': m = emissive(name, 0xffb878, 0.85); break;
    case 'win_cool': m = emissive(name, 0x8fd8ff, 0.7); break;
    case 'screen': m = screenMaterial(); break;
    case 'aether': m = aetherMaterial(); break;
    case 'water': m = waterMaterial(); break;
    default: m = new THREE.MeshStandardMaterial({ color: 0xff00ff });
  }
  cache.set(key, m);
  return m;
}

/** Glowing terminal screen with scrolling lines. */
function screenMaterial(): THREE.Material {
  const [c, ctx] = makeCanvas(256, 256);
  ctx.fillStyle = '#04121a';
  ctx.fillRect(0, 0, 256, 256);
  ctx.fillStyle = '#5fd8ff';
  for (let y = 10; y < 250; y += 12) {
    const w = 40 + ((y * 37) % 160);
    ctx.globalAlpha = 0.35 + ((y * 13) % 50) / 100;
    ctx.fillRect(12, y, w, 4);
  }
  ctx.globalAlpha = 0.8;
  ctx.strokeStyle = '#5fd8ff';
  ctx.strokeRect(4, 4, 248, 248);
  const t = tex(c, { srgb: true });
  t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
  const m = new THREE.MeshBasicMaterial({ map: t, color: new THREE.Color(1.6, 1.6, 1.6), name: 'screen' });
  return m;
}

/** Animated Aether energy surface (fresnel + flowing noise), additive. */
function aetherMaterial(): THREE.Material {
  return new THREE.ShaderMaterial({
    name: 'aether',
    uniforms: { uTime: timeUniform, uColA: { value: new THREE.Color(0x4fd6ff) }, uColB: { value: new THREE.Color(0xa070ff) }, uIntensity: { value: 2.2 } },
    vertexShader: /* glsl */ `
      varying vec3 vN; varying vec3 vV; varying vec3 vP;
      void main(){
        vec4 wp = modelMatrix * vec4(position,1.0);
        vP = wp.xyz;
        vN = normalize(mat3(modelMatrix) * normal);
        vV = normalize(cameraPosition - wp.xyz);
        gl_Position = projectionMatrix * viewMatrix * wp;
      }`,
    fragmentShader: /* glsl */ `
      uniform float uTime; uniform vec3 uColA; uniform vec3 uColB; uniform float uIntensity;
      varying vec3 vN; varying vec3 vV; varying vec3 vP;
      float h(vec3 p){ return fract(sin(dot(p, vec3(12.9898,78.233,37.719)))*43758.5453); }
      float n3(vec3 p){ vec3 i=floor(p); vec3 f=fract(p); f=f*f*(3.0-2.0*f);
        return mix(mix(mix(h(i),h(i+vec3(1,0,0)),f.x),mix(h(i+vec3(0,1,0)),h(i+vec3(1,1,0)),f.x),f.y),
                   mix(mix(h(i+vec3(0,0,1)),h(i+vec3(1,0,1)),f.x),mix(h(i+vec3(0,1,1)),h(i+vec3(1,1,1)),f.x),f.y),f.z); }
      void main(){
        float fres = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.0);
        float flow = n3(vP*1.6 + vec3(0.0, uTime*0.8, uTime*0.3)) * 0.6 + n3(vP*4.0 - vec3(uTime*0.5)) * 0.4;
        vec3 col = mix(uColA, uColB, smoothstep(0.3, 0.8, flow));
        float a = clamp(fres * 0.9 + flow * 0.35, 0.0, 1.0);
        gl_FragColor = vec4(col * uIntensity * a, a);
      }`,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
}

/** Dark reflective water with moving ripples. */
function waterMaterial(): THREE.Material {
  const N = 256;
  const n = new TileNoise(77);
  const h = field(N, (u, v) => n.fbm(u, v, 8, 4));
  const nm = tex(heightToNormal(h, N, 2), { repeat: 1 });
  const m = new THREE.MeshStandardMaterial({ name: 'water', color: 0x0a1418, roughness: 0.06, metalness: 0.2, normalMap: nm, normalScale: new THREE.Vector2(0.4, 0.4), transparent: true, opacity: 0.85, envMapIntensity: 1.3 });
  nm.repeat.set(0.25, 0.25);
  m.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = timeUniform;
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform float uTime;')
      .replace('#include <normal_fragment_maps>', `
        vec3 mapN = texture2D( normalMap, vNormalMapUv + vec2(uTime*0.02, uTime*0.013) ).xyz * 2.0 - 1.0;
        vec3 mapN2 = texture2D( normalMap, vNormalMapUv*1.7 - vec2(uTime*0.017, -uTime*0.021) ).xyz * 2.0 - 1.0;
        mapN = normalize(mapN + mapN2);
        mapN.xy *= normalScale;
        normal = normalize( tbn * mapN );`);
  };
  return m;
}

export function disposeMaterialCache() {
  for (const m of cache.values()) m.dispose();
  cache.clear();
  for (const s of texCache.values()) { s.map?.dispose(); s.normalMap?.dispose(); s.roughnessMap?.dispose(); }
  texCache.clear();
}

/** Canvas texture with text, for signage. */
export function signTexture(lines: string[], opts: { w?: number; h?: number; bg?: string; fg?: string; font?: string; border?: string } = {}): THREE.Texture {
  const w = opts.w ?? 512, h = opts.h ?? 128;
  const [c, ctx] = makeCanvas(w, h);
  ctx.fillStyle = opts.bg ?? '#0c1218';
  ctx.fillRect(0, 0, w, h);
  if (opts.border) {
    ctx.strokeStyle = opts.border;
    ctx.lineWidth = 6;
    ctx.strokeRect(6, 6, w - 12, h - 12);
  }
  ctx.fillStyle = opts.fg ?? '#d8e4ee';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const fs = Math.floor((h * 0.62) / lines.length);
  ctx.font = opts.font ?? `600 ${fs}px Rajdhani, Inter, sans-serif`;
  lines.forEach((l, i) => ctx.fillText(l, w / 2, (h / (lines.length + 1)) * (i + 1)));
  const t = tex(c, { srgb: true });
  t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
  return t;
}

/** Radial gradient sprite texture (light pools, glows). */
let glowTex: THREE.Texture | null = null;
export function glowTexture(): THREE.Texture {
  if (glowTex) return glowTex;
  const [c, ctx] = makeCanvas(128, 128);
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(0.25, 'rgba(255,255,255,0.55)');
  g.addColorStop(0.6, 'rgba(255,255,255,0.12)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 128, 128);
  glowTex = new THREE.CanvasTexture(c);
  glowTex.colorSpace = THREE.SRGBColorSpace;
  return glowTex;
}
