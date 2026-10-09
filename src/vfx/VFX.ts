import * as THREE from 'three';
import { glowTexture } from '../render/Materials';

// Pooled visual effects. Everything allocates up front; nothing is created during combat.

interface P { alive: boolean; pos: THREE.Vector3; vel: THREE.Vector3; life: number; max: number; size: number; size1: number; color: THREE.Color; gravity: number; drag: number; additive: boolean }

class ParticleField {
  readonly points: THREE.Points;
  private parts: P[] = [];
  private geo: THREE.BufferGeometry;
  private pos: Float32Array;
  private col: Float32Array;
  private size: Float32Array;
  private cursor = 0;
  constructor(count: number, additive: boolean) {
    this.geo = new THREE.BufferGeometry();
    this.pos = new Float32Array(count * 3);
    this.col = new Float32Array(count * 4);
    this.size = new Float32Array(count);
    this.geo.setAttribute('position', new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    this.geo.setAttribute('color', new THREE.BufferAttribute(this.col, 4).setUsage(THREE.DynamicDrawUsage));
    this.geo.setAttribute('psize', new THREE.BufferAttribute(this.size, 1).setUsage(THREE.DynamicDrawUsage));
    const mat = new THREE.ShaderMaterial({
      uniforms: { uMap: { value: glowTexture() }, uScale: { value: 600 } },
      vertexShader: /* glsl */ `
        attribute vec4 color; attribute float psize; uniform float uScale;
        varying vec4 vC;
        void main(){ vC = color; vec4 mv = modelViewMatrix * vec4(position,1.0); gl_PointSize = psize * uScale / max(0.1, -mv.z); gl_Position = projectionMatrix * mv; }`,
      fragmentShader: /* glsl */ `
        uniform sampler2D uMap; varying vec4 vC;
        void main(){ vec4 t = texture2D(uMap, gl_PointCoord); gl_FragColor = vec4(vC.rgb * t.a * vC.a, ${additive ? 't.a * vC.a' : 't.a * vC.a'}); }`,
      transparent: true,
      depthWrite: false,
      blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    });
    if (!additive) {
      mat.fragmentShader = /* glsl */ `
        uniform sampler2D uMap; varying vec4 vC;
        void main(){ vec4 t = texture2D(uMap, gl_PointCoord); gl_FragColor = vec4(vC.rgb, t.a * vC.a); }`;
    }
    this.points = new THREE.Points(this.geo, mat);
    this.points.frustumCulled = false;
    this.points.renderOrder = additive ? 6 : 4;
    for (let i = 0; i < count; i++) this.parts.push({ alive: false, pos: new THREE.Vector3(), vel: new THREE.Vector3(), life: 0, max: 1, size: 0.1, size1: 0, color: new THREE.Color(), gravity: 0, drag: 0, additive });
  }
  setScale(h: number) {
    (this.points.material as THREE.ShaderMaterial).uniforms.uScale.value = h * 0.6;
  }
  spawn(pos: THREE.Vector3, vel: THREE.Vector3, life: number, size: number, size1: number, color: THREE.Color | number, gravity: number, drag: number) {
    const p = this.parts[this.cursor];
    this.cursor = (this.cursor + 1) % this.parts.length;
    p.alive = true;
    p.pos.copy(pos);
    p.vel.copy(vel);
    p.life = life;
    p.max = life;
    p.size = size;
    p.size1 = size1;
    if (typeof color === 'number') p.color.set(color);
    else p.color.copy(color);
    p.gravity = gravity;
    p.drag = drag;
  }
  update(dt: number) {
    const n = this.parts.length;
    for (let i = 0; i < n; i++) {
      const p = this.parts[i];
      if (!p.alive) {
        this.col[i * 4 + 3] = 0;
        this.size[i] = 0;
        continue;
      }
      p.life -= dt;
      if (p.life <= 0) {
        p.alive = false;
        this.col[i * 4 + 3] = 0;
        this.size[i] = 0;
        continue;
      }
      p.vel.y -= p.gravity * dt;
      p.vel.multiplyScalar(Math.max(0, 1 - p.drag * dt));
      p.pos.addScaledVector(p.vel, dt);
      const k = p.life / p.max;
      this.pos[i * 3] = p.pos.x;
      this.pos[i * 3 + 1] = p.pos.y;
      this.pos[i * 3 + 2] = p.pos.z;
      this.col[i * 4] = p.color.r;
      this.col[i * 4 + 1] = p.color.g;
      this.col[i * 4 + 2] = p.color.b;
      this.col[i * 4 + 3] = Math.min(1, k * 2.2);
      this.size[i] = p.size1 + (p.size - p.size1) * k;
    }
    (this.geo.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true;
    (this.geo.getAttribute('color') as THREE.BufferAttribute).needsUpdate = true;
    (this.geo.getAttribute('psize') as THREE.BufferAttribute).needsUpdate = true;
  }
  clear() {
    for (const p of this.parts) p.alive = false;
  }
}

interface Timed { obj: THREE.Mesh; t: number; dur: number; active: boolean; update: (k: number, o: THREE.Mesh) => void }

const ringVS = /* glsl */ `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`;

export class VFX {
  readonly group = new THREE.Group();
  private add: ParticleField;
  private smoke: ParticleField;
  private rings: Timed[] = [];
  private slashes: Timed[] = [];
  private flashes: Timed[] = [];
  private lights: { light: THREE.PointLight; t: number; dur: number; peak: number }[] = [];
  private echoWave: Timed;
  private tmpV = new THREE.Vector3();
  private tmpV2 = new THREE.Vector3();
  quality: 'low' | 'medium' | 'high' = 'high';
  emitters: { pos: THREE.Vector3; kind: 'fire' | 'sparks' | 'steam' | 'aether'; rate: number; acc: number; active: boolean; radius?: number }[] = [];

  constructor() {
    this.group.name = 'vfx';
    this.add = new ParticleField(1800, true);
    this.smoke = new ParticleField(500, false);
    this.group.add(this.add.points, this.smoke.points);
    // Shockwave rings
    for (let i = 0; i < 6; i++) {
      const mat = new THREE.ShaderMaterial({
        uniforms: { uColor: { value: new THREE.Color(0x5fd8ff) }, uK: { value: 0 } },
        vertexShader: ringVS,
        fragmentShader: /* glsl */ `uniform vec3 uColor; uniform float uK; varying vec2 vUv;
          void main(){ float r = length(vUv-0.5)*2.0; float band = smoothstep(0.7,0.95,r)*smoothstep(1.0,0.95,r); float a = band*(1.0-uK); gl_FragColor = vec4(uColor*a*3.0, a); }`,
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
      });
      const m = new THREE.Mesh(new THREE.PlaneGeometry(2, 2).rotateX(-Math.PI / 2), mat);
      m.visible = false;
      m.renderOrder = 7;
      this.group.add(m);
      this.rings.push({ obj: m, t: 0, dur: 0.5, active: false, update: () => undefined });
    }
    // Slash arcs (crescent strips)
    for (let i = 0; i < 6; i++) {
      const geo = this.crescent();
      const mat = new THREE.ShaderMaterial({
        uniforms: { uColor: { value: new THREE.Color(0x6fd0ff) }, uK: { value: 0 } },
        vertexShader: ringVS,
        fragmentShader: /* glsl */ `uniform vec3 uColor; uniform float uK; varying vec2 vUv;
          void main(){ float along = vUv.x; float across = vUv.y;
            float head = smoothstep(uK - 0.55, uK, along) * step(along, uK + 0.02);
            float edge = smoothstep(0.0, 0.25, across) * smoothstep(1.0, 0.55, across);
            float a = head * edge * (1.0 - uK * 0.6);
            gl_FragColor = vec4(uColor * a * 2.6 + vec3(a*0.6), a); }`,
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
      });
      const m = new THREE.Mesh(geo, mat);
      m.visible = false;
      m.renderOrder = 7;
      this.group.add(m);
      this.slashes.push({ obj: m, t: 0, dur: 0.22, active: false, update: () => undefined });
    }
    // Flash sprites
    for (let i = 0; i < 8; i++) {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: glowTexture(), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, color: 0xffffff }));
      m.visible = false;
      m.renderOrder = 8;
      this.group.add(m);
      this.flashes.push({ obj: m, t: 0, dur: 0.12, active: false, update: () => undefined });
    }
    // Impact lights (always present to avoid shader recompiles; intensity 0 when idle)
    for (let i = 0; i < 2; i++) {
      const l = new THREE.PointLight(0x7fd8ff, 0, 9, 2);
      this.group.add(l);
      this.lights.push({ light: l, t: 1, dur: 1, peak: 0 });
    }
    // Echo Sight wave
    const echoMat = new THREE.ShaderMaterial({
      uniforms: { uK: { value: 0 }, uColor: { value: new THREE.Color(0x8fd8ff) } },
      vertexShader: /* glsl */ `varying vec3 vN; varying vec3 vV; void main(){ vec4 wp = modelMatrix*vec4(position,1.0); vN = normalize(mat3(modelMatrix)*normal); vV = normalize(cameraPosition - wp.xyz); gl_Position = projectionMatrix*viewMatrix*wp; }`,
      fragmentShader: /* glsl */ `uniform float uK; uniform vec3 uColor; varying vec3 vN; varying vec3 vV;
        void main(){ float f = pow(1.0-abs(dot(vN,vV)), 3.0); float a = f*(1.0-uK)*0.8; gl_FragColor = vec4(uColor*a*2.0, a); }`,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    });
    const em = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), echoMat);
    em.visible = false;
    em.renderOrder = 9;
    this.group.add(em);
    this.echoWave = { obj: em, t: 0, dur: 1.2, active: false, update: () => undefined };
  }

  private crescent(): THREE.BufferGeometry {
    // Arc strip in the XZ plane from -70deg to +70deg; uv.x along the arc, uv.y across.
    const seg = 24;
    const pos: number[] = [], uv: number[] = [], idx: number[] = [];
    for (let i = 0; i <= seg; i++) {
      const t = i / seg;
      const a = (-1 + 2 * t) * 1.25;
      const inner = 0.55, outer = 1.0 + Math.sin(t * Math.PI) * 0.12;
      pos.push(Math.sin(a) * inner, 0, Math.cos(a) * inner, Math.sin(a) * outer, 0, Math.cos(a) * outer);
      uv.push(t, 0, t, 1);
      if (i < seg) {
        const k = i * 2;
        idx.push(k, k + 1, k + 2, k + 1, k + 3, k + 2);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    g.setIndex(idx);
    return g;
  }

  private take(pool: Timed[]): Timed {
    let best = pool[0];
    for (const p of pool) {
      if (!p.active) return p;
      if (p.t > best.t) best = p;
    }
    return best;
  }

  setViewportHeight(h: number) {
    this.add.setScale(h);
    this.smoke.setScale(h);
  }

  sparks(pos: THREE.Vector3, dir: THREE.Vector3 | null, count: number, color = 0x9fe0ff, speed = 7) {
    const n = this.quality === 'low' ? Math.ceil(count * 0.4) : this.quality === 'medium' ? Math.ceil(count * 0.7) : count;
    for (let i = 0; i < n; i++) {
      const v = this.tmpV.set(Math.random() - 0.5, Math.random() - 0.2, Math.random() - 0.5).normalize();
      if (dir) v.addScaledVector(dir, 1.2).normalize();
      v.multiplyScalar(speed * (0.4 + Math.random() * 0.8));
      this.add.spawn(pos, v, 0.25 + Math.random() * 0.35, 0.06 + Math.random() * 0.05, 0.01, color, 14, 2);
    }
  }

  embers(pos: THREE.Vector3, count: number, color: number, spread = 0.5, up = 1.5) {
    for (let i = 0; i < count; i++) {
      this.tmpV2.set(pos.x + (Math.random() - 0.5) * spread, pos.y + (Math.random() - 0.5) * spread, pos.z + (Math.random() - 0.5) * spread);
      this.add.spawn(this.tmpV2, this.tmpV.set((Math.random() - 0.5) * 0.6, up * (0.5 + Math.random()), (Math.random() - 0.5) * 0.6), 0.6 + Math.random() * 0.8, 0.1 + Math.random() * 0.1, 0.02, color, -0.5, 0.5);
    }
  }

  smokePuff(pos: THREE.Vector3, count: number, color = 0x2a2e34, size = 0.8) {
    if (this.quality === 'low') count = Math.ceil(count / 2);
    for (let i = 0; i < count; i++) {
      this.tmpV2.set(pos.x + (Math.random() - 0.5) * 0.6, pos.y + Math.random() * 0.4, pos.z + (Math.random() - 0.5) * 0.6);
      this.smoke.spawn(this.tmpV2, this.tmpV.set((Math.random() - 0.5) * 1.2, 0.6 + Math.random() * 0.8, (Math.random() - 0.5) * 1.2), 0.8 + Math.random() * 0.8, size * 0.5, size * 1.6, color, -0.3, 1.2);
    }
  }

  flash(pos: THREE.Vector3, size: number, color = 0xffffff, dur = 0.12) {
    const f = this.take(this.flashes);
    f.active = true;
    f.t = 0;
    f.dur = dur;
    f.obj.visible = true;
    f.obj.position.copy(pos);
    f.obj.scale.setScalar(size);
    (f.obj.material as THREE.MeshBasicMaterial).color.set(color).multiplyScalar(2);
    f.update = (k, o) => {
      o.scale.setScalar(size * (1 + k * 0.6));
      (o.material as THREE.MeshBasicMaterial).opacity = 1 - k;
    };
  }

  light(pos: THREE.Vector3, color: number, peak: number, dur = 0.18) {
    let l = this.lights[0];
    for (const x of this.lights) if (x.t >= x.dur) { l = x; break; }
    l.light.position.copy(pos);
    l.light.color.set(color);
    l.t = 0;
    l.dur = dur;
    l.peak = peak;
  }

  shockwave(pos: THREE.Vector3, radius: number, color = 0x5fd8ff, dur = 0.45) {
    const r = this.take(this.rings);
    r.active = true;
    r.t = 0;
    r.dur = dur;
    r.obj.visible = true;
    r.obj.position.copy(pos).setY(pos.y + 0.08);
    const mat = r.obj.material as THREE.ShaderMaterial;
    mat.uniforms.uColor.value.set(color);
    r.update = (k, o) => {
      o.scale.setScalar(0.3 + radius * (1 - Math.pow(1 - k, 3)));
      mat.uniforms.uK.value = k;
    };
  }

  /** Energy slash arc in front of a character. yaw = facing, tilt = roll of the swing plane, mirror for backhand. */
  slash(pos: THREE.Vector3, yaw: number, radius: number, color: number, tilt = 0, mirror = false, dur = 0.2) {
    const s = this.take(this.slashes);
    s.active = true;
    s.t = 0;
    s.dur = dur;
    s.obj.visible = true;
    s.obj.position.copy(pos);
    s.obj.rotation.set(0, yaw, tilt, 'YXZ');
    s.obj.scale.set(mirror ? -radius : radius, radius, radius);
    const mat = s.obj.material as THREE.ShaderMaterial;
    mat.uniforms.uColor.value.set(color);
    s.update = (k) => {
      mat.uniforms.uK.value = Math.min(1.2, k * 1.3);
    };
  }

  echoReveal(pos: THREE.Vector3, radius: number) {
    const e = this.echoWave;
    e.active = true;
    e.t = 0;
    e.dur = 1.1;
    e.obj.visible = true;
    e.obj.position.copy(pos);
    const mat = e.obj.material as THREE.ShaderMaterial;
    e.update = (k, o) => {
      o.scale.setScalar(0.5 + radius * Math.pow(k, 0.7));
      mat.uniforms.uK.value = k;
    };
  }

  /** Large explosion for destroyed machines. */
  explode(pos: THREE.Vector3, scale = 1, color = 0x7fd8ff) {
    this.flash(pos, 3.2 * scale, 0xffe2b0, 0.18);
    this.sparks(pos, null, Math.round(36 * scale), 0xffc070, 10 * scale);
    this.sparks(pos, null, Math.round(16 * scale), color, 6 * scale);
    this.smokePuff(pos, Math.round(8 * scale), 0x1c1f24, 1.2 * scale);
    this.light(pos, 0xffb060, 40 * scale, 0.35);
    this.shockwave(pos.clone().setY(pos.y - 0.6), 3 * scale, 0xffb060, 0.35);
  }

  update(dt: number) {
    this.add.update(dt);
    this.smoke.update(dt);
    for (const pool of [this.rings, this.slashes, this.flashes]) {
      for (const p of pool) {
        if (!p.active) continue;
        p.t += dt;
        const k = Math.min(1, p.t / p.dur);
        p.update(k, p.obj);
        if (k >= 1) {
          p.active = false;
          p.obj.visible = false;
        }
      }
    }
    if (this.echoWave.active) {
      const e = this.echoWave;
      e.t += dt;
      const k = Math.min(1, e.t / e.dur);
      e.update(k, e.obj);
      if (k >= 1) {
        e.active = false;
        e.obj.visible = false;
      }
    }
    for (const l of this.lights) {
      if (l.t < l.dur) {
        l.t += dt;
        const k = Math.min(1, l.t / l.dur);
        l.light.intensity = l.peak * (1 - k) * (1 - k);
      } else l.light.intensity = 0;
    }
    // Continuous emitters
    for (const e of this.emitters) {
      if (!e.active) continue;
      e.acc += dt * e.rate * (this.quality === 'low' ? 0.4 : this.quality === 'medium' ? 0.7 : 1);
      while (e.acc >= 1) {
        e.acc -= 1;
        if (e.kind === 'fire') {
          this.add.spawn(this.tmpV2.set(e.pos.x + (Math.random() - 0.5) * 0.4, e.pos.y, e.pos.z + (Math.random() - 0.5) * 0.4), this.tmpV.set((Math.random() - 0.5) * 0.3, 1.2 + Math.random(), (Math.random() - 0.5) * 0.3), 0.5 + Math.random() * 0.4, 0.35, 0.05, Math.random() < 0.5 ? 0xff7a2a : 0xffb050, -1, 1);
          if (Math.random() < 0.15) this.smoke.spawn(this.tmpV2.set(e.pos.x, e.pos.y + 0.8, e.pos.z), this.tmpV.set((Math.random() - 0.5) * 0.4, 1, (Math.random() - 0.5) * 0.4), 2, 0.4, 1.4, 0x1a1c20, -0.2, 0.4);
        } else if (e.kind === 'sparks') {
          if (Math.random() < 0.08) this.sparks(e.pos, new THREE.Vector3(0, -1, 0), 10, 0xffd890, 4);
        } else if (e.kind === 'steam') {
          this.smoke.spawn(this.tmpV2.set(e.pos.x + (Math.random() - 0.5) * 0.3, e.pos.y, e.pos.z + (Math.random() - 0.5) * 0.3), this.tmpV.set((Math.random() - 0.5) * 0.3, 1.2, (Math.random() - 0.5) * 0.3), 1.6, 0.3, 1.2, 0x8a96a2, -0.2, 0.8);
        } else if (e.kind === 'aether') {
          const r = e.radius ?? 1;
          const a = Math.random() * Math.PI * 2;
          this.add.spawn(this.tmpV2.set(e.pos.x + Math.cos(a) * r * Math.random(), e.pos.y + Math.random() * 0.4, e.pos.z + Math.sin(a) * r * Math.random()), this.tmpV.set(0, 0.6 + Math.random() * 0.8, 0), 1.4, 0.08, 0.02, Math.random() < 0.6 ? 0x5fd8ff : 0xa47dff, -0.2, 0.3);
        }
      }
    }
  }

  addEmitter(pos: THREE.Vector3, kind: 'fire' | 'sparks' | 'steam' | 'aether', rate: number, radius?: number) {
    const e = { pos: pos.clone(), kind, rate, acc: 0, active: true, radius };
    this.emitters.push(e);
    return e;
  }

  clear() {
    this.add.clear();
    this.smoke.clear();
    this.emitters = [];
    for (const pool of [this.rings, this.slashes, this.flashes]) for (const p of pool) { p.active = false; p.obj.visible = false; }
    for (const l of this.lights) { l.t = l.dur; l.light.intensity = 0; }
  }
}
