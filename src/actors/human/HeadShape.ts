import * as THREE from 'three';
import { smoothstep } from '../../core/MathUtil';

// Shared head sculpting used by both the head mesh and the face texture painter,
// so painted features line up with geometry.

export interface FaceSpec {
  female?: boolean;
  jaw?: number; // jaw width factor (1 = default)
  chin?: number; // chin projection factor
  brow?: number; // brow ridge strength
  nose?: number; // nose size factor
  cheek?: number; // cheekbone strength
  lips?: number; // lip fullness
  scar?: boolean;
  stubble?: number; // 0..1
  beard?: number; // 0..1
  age?: number; // 0..1 adds lines and grey
  freckles?: number; // 0..1
  makeup?: number; // subtle eye definition
  browColor?: string;
}

/** Reference-space eye centre (right eye at -x). */
export const EYE = { x: 0.0315, y: 0.0078 };

export class HeadShape {
  readonly r: THREE.Vector3;
  /** When set, featureDisp leaves out the hidden recess behind the eyelid patches. */
  private natural = false;
  readonly f: Required<Omit<FaceSpec, 'browColor'>> & { browColor: string };
  constructor(face: FaceSpec, scale: number) {
    const fem = !!face.female;
    this.r = new THREE.Vector3(fem ? 0.0735 : 0.0775, fem ? 0.108 : 0.113, fem ? 0.094 : 0.0985).multiplyScalar(scale);
    this.f = {
      female: fem,
      jaw: face.jaw ?? 1,
      chin: face.chin ?? 1,
      brow: face.brow ?? (fem ? 0.55 : 1),
      nose: face.nose ?? (fem ? 0.85 : 1),
      cheek: face.cheek ?? 1,
      lips: face.lips ?? (fem ? 1.25 : 1),
      scar: face.scar ?? false,
      stubble: face.stubble ?? 0,
      beard: face.beard ?? 0,
      age: face.age ?? 0,
      freckles: face.freckles ?? 0,
      makeup: face.makeup ?? 0,
      browColor: face.browColor ?? '#2a1d15',
    };
    this.scale = scale;
  }
  readonly scale: number;

  /**
   * Map a unit direction to a sculpted head-local point (metres, before scale is applied to features).
   * Features are authored for a 1.8 m reference head and scaled.
   */
  sculpt(dir: THREE.Vector3, out = new THREE.Vector3(), natural?: boolean): THREE.Vector3 {
    if (natural !== undefined) {
      const prev = this.natural;
      this.natural = natural;
      this.sculpt(dir, out);
      this.natural = prev;
      return out;
    }
    const r = this.r, s = this.scale, f = this.f;
    // Work in ring terms: h is the horizontal extent at this height, (ux, uz) the heading around the head.
    const h = Math.hypot(dir.x, dir.z);
    const ux = h > 1e-9 ? dir.x / h : 0, uz = h > 1e-9 ? dir.z / h : 1;
    const dy = dir.y;
    const wf = smoothstep(0, 0.55, uz); // 0 at the sides and back, 1 on the face
    // Below the eye line the face is a near-vertical plane (jaw and chin), not the underside of an
    // egg: the ring shrinks much more slowly than an ellipse would, then closes under the jaw.
    const box = 1 - 0.5 * Math.pow(Math.abs(dy), 3.2);
    const lowFace = dy < 0 ? smoothstep(-0.05, -0.35, dy) * smoothstep(-1, -0.93, dy) : 0;
    const hh = h + Math.max(0, box - h) * wf * lowFace;
    // In plan view the face is broad and fairly flat (superellipse), the skull rounder behind.
    const p = 2 + 0.65 * smoothstep(0, 0.7, uz);
    const k = 1 / Math.pow(Math.pow(Math.abs(ux), p) + Math.pow(Math.abs(uz), p), 1 / p);
    let x = hh * ux * k * r.x, y = dy * r.y, z = hh * uz * k * r.z;
    const yr = y / s; // reference-space height
    // Jaw taper: lower face narrows; back of skull narrows into the neck.
    const lower = smoothstep(-0.02, -0.11, yr);
    const jawW = (f.female ? 0.78 : 0.88) * f.jaw;
    x *= 1 - lower * lower * (1 - jawW) * (z > 0 ? 1 : 0.8);
    // The chin sits a little behind the brow line.
    if (z > 0) z *= 1 - smoothstep(-0.02, -0.1, yr) * 0.05;
    if (z < 0) z *= 1 - smoothstep(-0.02, -0.11, yr) * 0.3;
    // Slight flattening of the face plane and fuller crown.
    if (z > 0) z *= 1 - smoothstep(0.02, 0.09, yr) * 0.06;
    y += smoothstep(0.03, 0.1, yr) * 0.004 * s;
    out.set(x, y, z);
    const front = smoothstep(0.15, 0.7, dir.z);
    if (front > 0) {
      const d = this.featureDisp(x / s, y / s) * front * s;
      // Displace mostly forward for face features.
      out.z += d;
    }
    return out;
  }

  /** Facial relief (reference metres) at reference-space x,y on the front of the head. */
  featureDisp(x: number, y: number): number {
    const f = this.f;
    const g = (cx: number, cy: number, sx: number, sy: number) => Math.exp(-((x - cx) ** 2) / (2 * sx * sx) - ((y - cy) ** 2) / (2 * sy * sy));
    const ax = Math.abs(x);
    let d = 0;
    // Brow ridge
    d += 0.0055 * f.brow * g(0, 0.031, 0.04, 0.007) * (1 - smoothstep(0.05, 0.07, ax));
    // Eye sockets: a gentle seat for the eyes and a hollow up under the brow.
    d -= 0.003 * (g(EYE.x, EYE.y, 0.016, 0.009) + g(-EYE.x, EYE.y, 0.016, 0.009));
    d -= 0.0022 * (g(0.03, 0.019, 0.016, 0.006) + g(-0.03, 0.019, 0.016, 0.006));
    // Hidden recess under the eyelid patches (built separately), so the head never pokes through them.
    if (!this.natural) {
      for (const ex of [EYE.x, -EYE.x]) d -= 0.013 * Math.exp(-(((x - ex) / 0.0118) ** 6) - (((y - EYE.y) / 0.0068) ** 6));
    }
    // Nose bridge and tip
    const noseW = 0.0095 * (0.9 + 0.1 * f.nose);
    const bridge = Math.exp(-(x * x) / (2 * noseW * noseW));
    let prof = 0;
    if (y < 0.016 && y > -0.044) {
      const t = (0.016 - y) / 0.052;
      prof = 0.003 + t * t * 0.0135 * f.nose;
      if (y < -0.034) prof *= 1 - (-(y + 0.034) / 0.01) * 0.8;
    }
    d += prof * bridge;
    // Nostril wings
    d += 0.004 * f.nose * (g(0.0115, -0.035, 0.0055, 0.005) + g(-0.0115, -0.035, 0.0055, 0.005));
    // Cheekbones
    d += 0.005 * f.cheek * (g(0.045, -0.014, 0.018, 0.014) + g(-0.045, -0.014, 0.018, 0.014));
    // Slight mid-face fullness beside the mouth.
    d += 0.0015 * (g(0.035, -0.045, 0.02, 0.02) + g(-0.035, -0.045, 0.02, 0.02));
    // Upper lip / philtrum and lips
    d += 0.0032 * g(0, -0.049, 0.012, 0.006);
    d += 0.0042 * f.lips * g(0, -0.0585, 0.019, 0.0045);
    d += 0.0036 * f.lips * g(0, -0.0675, 0.016, 0.005);
    d -= 0.0018 * g(0, -0.063, 0.02, 0.0016);
    // Chin
    d += 0.006 * f.chin * g(0, -0.092, 0.02, 0.012);
    // Jaw angle definition (male)
    if (!f.female) d += 0.002 * (g(0.055, -0.07, 0.01, 0.02) + g(-0.055, -0.07, 0.01, 0.02));
    return d;
  }

  /**
   * Head-local surface point on the front at reference x,y (used to seat eyes). `natural` ignores the
   * hidden eye recess; `dirOut` receives the sculpt direction (for matching face-texture UVs).
   */
  frontPoint(xr: number, yr: number, natural = false, dirOut?: THREE.Vector3): THREE.Vector3 {
    const s = this.scale;
    this.natural = natural;
    // Search for the direction whose sculpted point matches x,y (few Newton-ish iterations).
    const dir = new THREE.Vector3(xr * s / this.r.x, yr * s / this.r.y, 0);
    dir.z = Math.sqrt(Math.max(0.01, 1 - dir.x * dir.x - dir.y * dir.y));
    dir.normalize();
    const p = new THREE.Vector3();
    for (let i = 0; i < 6; i++) {
      this.sculpt(dir, p);
      dir.x += (xr * s - p.x) / this.r.x;
      dir.y += (yr * s - p.y) / this.r.y;
      dir.z = Math.sqrt(Math.max(0.01, 1 - dir.x * dir.x - dir.y * dir.y));
      dir.normalize();
    }
    this.sculpt(dir, p);
    this.natural = false;
    dirOut?.copy(dir);
    return p;
  }
}
