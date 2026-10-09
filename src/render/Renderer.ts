import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js';
import { FXAAShader } from 'three/examples/jsm/shaders/FXAAShader.js';

export type Quality3 = 'low' | 'medium' | 'high';
export interface GraphicsOptions {
  resolution: 'performance' | 'balanced' | 'quality' | 'native';
  shadows: 'off' | Quality3;
  effects: Quality3;
  textures: Quality3;
  viewDistance: Quality3;
  antialiasing: 'off' | 'fxaa' | 'msaa';
  frameLimit: 'vsync' | '30';
}

const FinalShader = {
  uniforms: {
    tDiffuse: { value: null as THREE.Texture | null },
    exposure: { value: 1.0 },
    saturation: { value: 1.0 },
    contrast: { value: 1.06 },
    lift: { value: new THREE.Vector3(0.0, 0.004, 0.012) },
    gain: { value: new THREE.Vector3(1.0, 1.0, 1.0) },
    vignette: { value: 0.32 },
    grain: { value: 0.035 },
    chroma: { value: 0.0012 },
    time: { value: 0 },
    damage: { value: 0 },
    echo: { value: 0 },
    flash: { value: 0 },
    fade: { value: 0 },
    resolution: { value: new THREE.Vector2(1, 1) },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
  `,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse;
    uniform float exposure, saturation, contrast, vignette, grain, chroma, time, damage, echo, flash, fade;
    uniform vec3 lift, gain;
    uniform vec2 resolution;
    varying vec2 vUv;

    vec3 RRTAndODTFit(vec3 v) {
      vec3 a = v * (v + 0.0245786) - 0.000090537;
      vec3 b = v * (0.983729 * v + 0.4329510) + 0.238081;
      return a / b;
    }
    vec3 aces(vec3 color) {
      const mat3 ACESInputMat = mat3(vec3(0.59719, 0.07600, 0.02840), vec3(0.35458, 0.90834, 0.13383), vec3(0.04823, 0.01566, 0.83777));
      const mat3 ACESOutputMat = mat3(vec3(1.60475, -0.10208, -0.00327), vec3(-0.53108, 1.10813, -0.07276), vec3(-0.07367, -0.00605, 1.07602));
      color = ACESInputMat * color;
      color = RRTAndODTFit(color);
      color = ACESOutputMat * color;
      return clamp(color, 0.0, 1.0);
    }
    vec3 toSRGB(vec3 c) {
      vec3 lo = c * 12.92;
      vec3 hi = 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055;
      return mix(hi, lo, step(c, vec3(0.0031308)));
    }
    float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

    void main() {
      vec2 uv = vUv;
      vec2 dc = uv - 0.5;
      float r2 = dot(dc, dc);
      float ca = chroma * (1.0 + damage * 3.0);
      vec3 hdr;
      hdr.r = texture2D(tDiffuse, uv - dc * ca * 4.0).r;
      hdr.g = texture2D(tDiffuse, uv).g;
      hdr.b = texture2D(tDiffuse, uv + dc * ca * 4.0).b;

      hdr *= exposure * (1.0 + flash * 1.5) / 0.6;
      vec3 c = aces(hdr);

      // Grade: lift / gain / contrast / saturation
      c = c * gain + lift * (1.0 - c);
      c = (c - 0.5) * contrast + 0.5;
      float luma = dot(c, vec3(0.2126, 0.7152, 0.0722));
      c = mix(vec3(luma), c, saturation);

      // Echo Sight: cool desaturation with cyan edge tint
      if (echo > 0.001) {
        vec3 echoCol = vec3(luma * 0.55, luma * 0.85 + 0.02, luma * 1.05 + 0.04);
        c = mix(c, echoCol, echo * 0.6);
        c += vec3(0.0, 0.08, 0.12) * echo * smoothstep(0.12, 0.5, r2);
      }

      // Vignette and damage pulse
      float vig = smoothstep(0.8, 0.2, sqrt(r2) * (1.0 + vignette));
      c *= mix(1.0, vig, 0.85);
      c = mix(c, vec3(0.55, 0.04, 0.05), damage * smoothstep(0.06, 0.35, r2) * 0.75);

      c = clamp(c, 0.0, 1.0);
      c = toSRGB(c);
      c += (hash(uv * resolution + fract(time) * 91.7) - 0.5) * grain;
      c = mix(c, vec3(0.0), fade);
      gl_FragColor = vec4(c, 1.0);
    }
  `,
};

export class RenderSystem {
  readonly renderer: THREE.WebGLRenderer;
  readonly canvas: HTMLCanvasElement;
  camera: THREE.PerspectiveCamera;
  scene: THREE.Scene;
  private composer!: EffectComposer;
  private renderPass!: RenderPass;
  bloom!: UnrealBloomPass;
  final!: ShaderPass;
  private fxaa!: ShaderPass;
  opts: GraphicsOptions;
  private width = 1;
  private height = 1;
  private shadowLight: THREE.DirectionalLight | null = null;
  private shadowOffset = new THREE.Vector3(18, 32, 12);
  /** Fog density multiplier from the view-distance setting. */
  fogScale = 1;
  /** Base camera far plane before view-distance scaling. */
  baseFar = 420;
  stats = { drawCalls: 0, triangles: 0, textures: 0, geometries: 0, programs: 0 };

  constructor(container: HTMLElement, opts: GraphicsOptions) {
    this.opts = { ...opts };
    this.renderer = new THREE.WebGLRenderer({
      antialias: false,
      powerPreference: 'high-performance',
      stencil: false,
      depth: true,
      preserveDrawingBuffer: false,
    });
    this.canvas = this.renderer.domElement;
    this.canvas.id = 'game-canvas';
    this.canvas.tabIndex = -1;
    container.appendChild(this.canvas);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.NoToneMapping;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.info.autoReset = false;

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(60, 16 / 9, 0.1, this.baseFar);
    this.buildComposer();
    this.applyOptions(this.opts);
    window.addEventListener('resize', () => this.resize());
    this.resize();
  }

  private buildComposer() {
    const msaa = this.opts.antialiasing === 'msaa' ? 4 : 0;
    const rt = new THREE.WebGLRenderTarget(this.width, this.height, {
      type: THREE.HalfFloatType,
      samples: msaa,
      colorSpace: THREE.LinearSRGBColorSpace,
    });
    this.composer?.dispose();
    this.composer = new EffectComposer(this.renderer, rt);
    this.renderPass = new RenderPass(this.scene, this.camera);
    this.composer.addPass(this.renderPass);
    this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.55, 0.55, 0.92);
    this.composer.addPass(this.bloom);
    this.final = new ShaderPass(FinalShader);
    this.composer.addPass(this.final);
    this.fxaa = new ShaderPass(FXAAShader);
    this.composer.addPass(this.fxaa);
  }

  applyOptions(o: GraphicsOptions) {
    const rebuild = o.antialiasing !== this.opts.antialiasing && (o.antialiasing === 'msaa' || this.opts.antialiasing === 'msaa');
    this.opts = { ...o };
    if (rebuild) this.buildComposer();

    const r = this.renderer;
    r.shadowMap.enabled = o.shadows !== 'off';
    const mapSize = o.shadows === 'high' ? 4096 : o.shadows === 'medium' ? 2048 : 1024;
    if (this.shadowLight) this.configureShadowLight(this.shadowLight, mapSize);
    this.bloom.enabled = o.effects !== 'low';
    this.bloom.strength = o.effects === 'high' ? 0.6 : 0.5;
    this.fxaa.enabled = o.antialiasing === 'fxaa';
    this.final.uniforms.grain.value = o.effects === 'low' ? 0 : 0.03;
    this.final.uniforms.chroma.value = o.effects === 'high' ? 0.0005 : 0.0;
    this.fogScale = o.viewDistance === 'low' ? 1.6 : o.viewDistance === 'medium' ? 1.2 : 1.0;
    this.camera.far = this.baseFar * (o.viewDistance === 'low' ? 0.5 : o.viewDistance === 'medium' ? 0.75 : 1.0);
    this.camera.updateProjectionMatrix();
    // Force material recompiles so shadow on/off takes effect.
    this.scene.traverse((obj) => {
      const m = (obj as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined;
      if (!m) return;
      (Array.isArray(m) ? m : [m]).forEach((mm) => (mm.needsUpdate = true));
    });
    this.resize();
  }

  pixelRatio(): number {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const h = window.innerHeight;
    const target = this.opts.resolution === 'performance' ? 720 : this.opts.resolution === 'balanced' ? 1080 : this.opts.resolution === 'quality' ? 1440 : h * dpr;
    return Math.max(0.5, Math.min(dpr, target / h));
  }

  resize() {
    const w = Math.max(1, window.innerWidth);
    const h = Math.max(1, window.innerHeight);
    this.width = w;
    this.height = h;
    const pr = this.pixelRatio();
    this.renderer.setPixelRatio(pr);
    this.renderer.setSize(w, h, true);
    this.composer.setPixelRatio(pr);
    this.composer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    const pw = Math.floor(w * pr), ph = Math.floor(h * pr);
    this.fxaa.material.uniforms['resolution'].value.set(1 / pw, 1 / ph);
    this.final.uniforms.resolution.value.set(pw, ph);
    // Bloom at reduced resolution keeps cost down.
    const bs = this.opts.effects === 'high' ? 0.5 : 0.35;
    this.bloom.setSize(Math.floor(pw * bs), Math.floor(ph * bs));
  }

  setScene(scene: THREE.Scene) {
    this.scene = scene;
    this.renderPass.scene = scene;
    let found: THREE.DirectionalLight | null = null;
    scene.traverse((o) => {
      const l = o as THREE.DirectionalLight;
      if (l.isDirectionalLight && l.castShadow && !found) found = l;
    });
    this.shadowLight = found;
    const light = found as THREE.DirectionalLight | null;
    if (light) {
      const mapSize = this.opts.shadows === 'high' ? 4096 : this.opts.shadows === 'medium' ? 2048 : 1024;
      this.configureShadowLight(light, mapSize);
      this.shadowOffset.copy(light.position).sub(light.target.position).normalize().multiplyScalar(60);
    }
  }

  private configureShadowLight(light: THREE.DirectionalLight, mapSize: number) {
    if (light.shadow.mapSize.x !== mapSize) {
      light.shadow.mapSize.set(mapSize, mapSize);
      light.shadow.map?.dispose();
      light.shadow.map = null as unknown as THREE.WebGLRenderTarget;
    }
    const ext = this.opts.shadows === 'high' ? 34 : 28;
    const cam = light.shadow.camera;
    cam.left = -ext; cam.right = ext; cam.top = ext; cam.bottom = -ext;
    cam.near = 1; cam.far = 160;
    cam.updateProjectionMatrix();
    light.shadow.bias = -0.0004;
    light.shadow.normalBias = 0.035;
    light.shadow.radius = 2;
  }

  /** Keep the shadow frustum centred on the focus point, snapped to texels to avoid shimmering. */
  updateShadowFocus(focus: THREE.Vector3) {
    const l = this.shadowLight;
    if (!l) return;
    const ext = l.shadow.camera.right;
    const texel = (ext * 2) / l.shadow.mapSize.x;
    const fx = Math.round(focus.x / texel) * texel;
    const fz = Math.round(focus.z / texel) * texel;
    l.target.position.set(fx, focus.y, fz);
    l.position.set(fx, focus.y, fz).add(this.shadowOffset);
    l.target.updateMatrixWorld();
  }

  render(time: number) {
    this.final.uniforms.time.value = time;
    this.renderer.info.reset();
    this.composer.render();
    const info = this.renderer.info;
    this.stats.drawCalls = info.render.calls;
    this.stats.triangles = info.render.triangles;
    this.stats.textures = info.memory.textures;
    this.stats.geometries = info.memory.geometries;
    this.stats.programs = info.programs?.length ?? 0;
  }

  /** Pre-compile shaders for the current scene so the first frames of a zone don't hitch. */
  async compile(scene: THREE.Scene, camera: THREE.Camera) {
    const r = this.renderer as THREE.WebGLRenderer & { compileAsync?: (s: THREE.Object3D, c: THREE.Camera) => Promise<unknown> };
    if (r.compileAsync) await r.compileAsync(scene, camera);
    else r.compile(scene, camera);
  }

  setPost(p: Partial<{ damage: number; echo: number; flash: number; fade: number; exposure: number; saturation: number; vignette: number }>) {
    const u = this.final.uniforms;
    if (p.damage !== undefined) u.damage.value = p.damage;
    if (p.echo !== undefined) u.echo.value = p.echo;
    if (p.flash !== undefined) u.flash.value = p.flash;
    if (p.fade !== undefined) u.fade.value = p.fade;
    if (p.exposure !== undefined) u.exposure.value = p.exposure;
    if (p.saturation !== undefined) u.saturation.value = p.saturation;
    if (p.vignette !== undefined) u.vignette.value = p.vignette;
  }

  setGrade(g: { lift?: [number, number, number]; gain?: [number, number, number]; contrast?: number; saturation?: number; exposure?: number; bloomThreshold?: number }) {
    const u = this.final.uniforms;
    if (g.lift) u.lift.value.set(...g.lift);
    if (g.gain) u.gain.value.set(...g.gain);
    if (g.contrast !== undefined) u.contrast.value = g.contrast;
    if (g.saturation !== undefined) u.saturation.value = g.saturation;
    if (g.exposure !== undefined) u.exposure.value = g.exposure;
    if (g.bloomThreshold !== undefined) this.bloom.threshold = g.bloomThreshold;
  }

  /** Capture the current frame as a data URL (used by capture tools and save thumbnails). */
  snapshot(maxWidth = 320, quality = 0.7): string {
    this.composer.render();
    const src = this.canvas;
    const scale = Math.min(1, maxWidth / src.width);
    const c = document.createElement('canvas');
    c.width = Math.round(src.width * scale);
    c.height = Math.round(src.height * scale);
    c.getContext('2d')!.drawImage(src, 0, 0, c.width, c.height);
    return c.toDataURL('image/jpeg', quality);
  }
}
