import * as THREE from 'three';
import { events } from '../core/Events';
import { glowTexture } from './Materials';

// GPU rain (single instanced draw), splash rings and lightning.

export interface WeatherConfig {
  rain: number; // 0..1 density
  wind: THREE.Vector2;
  lightning: boolean;
  lightningInterval: [number, number];
  splashHeight?: number; // ground height for splashes (approx)
  indoor?: boolean;
}

export class Weather {
  readonly group = new THREE.Group();
  private rain: THREE.Mesh;
  private rainMat: THREE.ShaderMaterial;
  private splash: THREE.InstancedMesh;
  private splashMat: THREE.ShaderMaterial;
  cfg: WeatherConfig;
  private nextFlash = 6;
  flash = 0;
  private flashSeq: number[] = [];
  /** Scales flash brightness for accessibility. */
  flashScale = 1;
  private time = 0;
  /** Lights affected by lightning (hemisphere/ambient). */
  flashLights: { light: THREE.Light; base: number; boost: number }[] = [];
  skyMat: THREE.ShaderMaterial | null = null;

  constructor(cfg: WeatherConfig, quality: 'low' | 'medium' | 'high') {
    this.cfg = cfg;
    this.group.name = 'weather';
    const count = cfg.rain <= 0 ? 0 : Math.floor((quality === 'high' ? 9000 : quality === 'medium' ? 5500 : 2800) * cfg.rain);
    // Rain streaks: each instance is a thin quad animated entirely in the vertex shader.
    const quad = new THREE.PlaneGeometry(0.012, 0.75);
    quad.translate(0, -0.375, 0);
    const geo = new THREE.InstancedBufferGeometry();
    geo.index = quad.index;
    geo.setAttribute('position', quad.getAttribute('position'));
    geo.setAttribute('uv', quad.getAttribute('uv'));
    const seeds = new Float32Array(Math.max(1, count) * 4);
    for (let i = 0; i < count; i++) {
      seeds[i * 4] = Math.random();
      seeds[i * 4 + 1] = Math.random();
      seeds[i * 4 + 2] = Math.random();
      seeds[i * 4 + 3] = 0.7 + Math.random() * 0.6;
    }
    geo.setAttribute('seed', new THREE.InstancedBufferAttribute(seeds, 4));
    geo.instanceCount = count;
    this.rainMat = new THREE.ShaderMaterial({
      name: 'rain',
      uniforms: {
        uTime: { value: 0 },
        uCam: { value: new THREE.Vector3() },
        uWind: { value: cfg.wind.clone() },
        uBox: { value: new THREE.Vector3(36, 26, 36) },
        uFlash: { value: 0 },
        uColor: { value: new THREE.Color(0x9fb8cc) },
      },
      vertexShader: /* glsl */ `
        attribute vec4 seed;
        uniform float uTime; uniform vec3 uCam; uniform vec2 uWind; uniform vec3 uBox;
        varying float vA; varying vec2 vUv;
        void main(){
          float speed = 16.0 * seed.w;
          vec3 base = vec3(seed.x, seed.y, seed.z) * uBox;
          base.y = mod(base.y - uTime * speed, uBox.y);
          base.xz += uWind * (uBox.y - base.y) * 0.05;
          // Wrap around the camera so rain is always present.
          vec3 p = base - uBox * 0.5;
          p.x = mod(p.x - uCam.x + uBox.x*0.5, uBox.x) - uBox.x*0.5 + uCam.x;
          p.z = mod(p.z - uCam.z + uBox.z*0.5, uBox.z) - uBox.z*0.5 + uCam.z;
          p.y += uCam.y + 2.0;
          // Billboard around the vertical axis, tilted by wind.
          vec3 toCam = normalize(vec3(cameraPosition.x - p.x, 0.0, cameraPosition.z - p.z));
          vec3 side = normalize(cross(vec3(0.0,1.0,0.0), toCam));
          vec3 dir = normalize(vec3(uWind.x*0.05, -1.0, uWind.y*0.05));
          vec3 wp = p + side * position.x + (-dir) * position.y * seed.w;
          vec4 mv = viewMatrix * vec4(wp, 1.0);
          float dist = -mv.z;
          vA = smoothstep(0.5, 2.5, dist) * smoothstep(34.0, 12.0, dist);
          vUv = uv;
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        uniform vec3 uColor; uniform float uFlash;
        varying float vA; varying vec2 vUv;
        void main(){
          float edge = 1.0 - abs(vUv.x - 0.5) * 2.0;
          float a = vA * edge * (0.16 + uFlash * 0.4) * smoothstep(0.0, 0.3, vUv.y);
          gl_FragColor = vec4(uColor * (1.0 + uFlash * 3.0), a);
        }`,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    this.rain = new THREE.Mesh(geo, this.rainMat);
    this.rain.frustumCulled = false;
    this.rain.renderOrder = 5;
    this.rain.visible = count > 0;
    this.group.add(this.rain);

    // Splash rings near the camera, animated on the GPU from instance seeds.
    const sCount = count > 0 ? (quality === 'low' ? 120 : 320) : 0;
    const sGeo = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
    this.splashMat = new THREE.ShaderMaterial({
      name: 'splash',
      uniforms: { uTime: { value: 0 }, uCam: { value: new THREE.Vector3() }, uMap: { value: glowTexture() }, uY: { value: cfg.splashHeight ?? 0.02 } },
      vertexShader: /* glsl */ `
        uniform float uTime; uniform vec3 uCam; uniform float uY;
        varying vec2 vUv; varying float vT;
        void main(){
          vec4 s = instanceMatrix[3];
          float t = fract(uTime * (1.2 + s.w * 0.6) + s.x * 7.13);
          float cycle = floor(uTime * (1.2 + s.w * 0.6) + s.x * 7.13);
          vec2 off = vec2(fract(sin(cycle * 12.9898 + s.x * 78.233) * 43758.5453), fract(sin(cycle * 39.346 + s.z * 11.135) * 24634.6345)) - 0.5;
          vec3 c = vec3(uCam.x + off.x * 22.0, uY, uCam.z + off.y * 22.0);
          float sc = 0.05 + t * 0.32;
          vec3 wp = c + position * sc;
          vUv = uv; vT = t;
          gl_Position = projectionMatrix * viewMatrix * vec4(wp, 1.0);
        }`,
      fragmentShader: /* glsl */ `
        varying vec2 vUv; varying float vT;
        void main(){
          float r = length(vUv - 0.5) * 2.0;
          float ring = smoothstep(0.75, 0.9, r) * smoothstep(1.0, 0.92, r);
          float a = ring * (1.0 - vT) * 0.35;
          gl_FragColor = vec4(vec3(0.75, 0.82, 0.9) * a, a);
        }`,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    this.splash = new THREE.InstancedMesh(sGeo, this.splashMat, Math.max(1, sCount));
    const m = new THREE.Matrix4();
    for (let i = 0; i < sCount; i++) {
      m.identity();
      m.setPosition(Math.random(), Math.random(), Math.random());
      m.elements[15] = 1;
      this.splash.setMatrixAt(i, m);
    }
    // Stash a 4th random in the w column via elements[15] is not possible; reuse x/z.
    this.splash.count = sCount;
    this.splash.frustumCulled = false;
    this.splash.visible = sCount > 0 && !cfg.indoor;
    this.group.add(this.splash);
    this.nextFlash = cfg.lightningInterval[0] * 0.5;
  }

  setRain(r: number) {
    this.cfg.rain = r;
    this.rain.visible = r > 0.01;
    this.splash.visible = r > 0.01 && !this.cfg.indoor;
    this.rainMat.uniforms.uColor.value.setScalar(0.62 * r);
  }

  triggerLightning(intensity = 1) {
    // Double / triple strike flicker sequence (times in seconds, values are brightness).
    this.flashSeq = [0, intensity, 0.06, 0.2 * intensity, 0.11, intensity * 0.8, 0.3, 0];
    this.flashT = 0;
    events.emit('lightning', { intensity });
  }
  private flashT = 0;

  update(dt: number, cam: THREE.Camera) {
    this.time += dt;
    const camPos = cam.getWorldPosition(new THREE.Vector3());
    this.rainMat.uniforms.uTime.value = this.time;
    this.rainMat.uniforms.uCam.value.copy(camPos);
    this.splashMat.uniforms.uTime.value = this.time;
    this.splashMat.uniforms.uCam.value.copy(camPos);
    if (this.cfg.lightning) {
      this.nextFlash -= dt;
      if (this.nextFlash <= 0) {
        const [a, b] = this.cfg.lightningInterval;
        this.nextFlash = a + Math.random() * (b - a);
        this.triggerLightning(0.6 + Math.random() * 0.4);
      }
    }
    // Evaluate flash sequence.
    let f = 0;
    if (this.flashSeq.length) {
      this.flashT += dt;
      const seq = this.flashSeq;
      for (let i = 0; i < seq.length; i += 2) {
        if (this.flashT >= seq[i]) f = seq[i + 1];
      }
      f *= Math.exp(-((this.flashT % 0.12) * 18));
      if (this.flashT > seq[seq.length - 2] + 0.2) this.flashSeq = [];
    }
    this.flash = f * this.flashScale;
    this.rainMat.uniforms.uFlash.value = this.flash;
    for (const fl of this.flashLights) fl.light.intensity = fl.base + fl.boost * this.flash;
    if (this.skyMat) {
      this.skyMat.uniforms.uFlash.value = this.flash;
      this.skyMat.uniforms.uTime.value = this.time;
    }
  }

  dispose() {
    this.rain.geometry.dispose();
    this.rainMat.dispose();
    this.splash.geometry.dispose();
    this.splashMat.dispose();
    this.group.removeFromParent();
  }
}
