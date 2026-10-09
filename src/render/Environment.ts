import * as THREE from 'three';

// Sky dome, environment map and lighting presets per zone.

export interface SkyConfig {
  top: number;
  horizon: number;
  bottom: number;
  glow?: number; // city/aether glow colour near the horizon
  glowStrength?: number;
  stars?: boolean;
  storm?: boolean;
}

export function createSky(cfg: SkyConfig): THREE.Mesh {
  const mat = new THREE.ShaderMaterial({
    name: 'sky',
    uniforms: {
      uTop: { value: new THREE.Color(cfg.top) },
      uHor: { value: new THREE.Color(cfg.horizon) },
      uBot: { value: new THREE.Color(cfg.bottom) },
      uGlow: { value: new THREE.Color(cfg.glow ?? cfg.horizon) },
      uGlowS: { value: cfg.glowStrength ?? 0.5 },
      uFlash: { value: 0 },
      uTime: { value: 0 },
      uStorm: { value: cfg.storm ? 1 : 0 },
    },
    vertexShader: /* glsl */ `
      varying vec3 vDir;
      void main(){ vDir = normalize(position); vec4 p = projectionMatrix * modelViewMatrix * vec4(position,1.0); gl_Position = p.xyww; }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uTop, uHor, uBot, uGlow; uniform float uGlowS, uFlash, uTime, uStorm;
      varying vec3 vDir;
      float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233)))*43758.5453); }
      float n2(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f); return mix(mix(h(i),h(i+vec2(1,0)),f.x), mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x), f.y); }
      float fbm(vec2 p){ float s=0.0,a=0.5; for(int i=0;i<5;i++){ s+=a*n2(p); p*=2.03; a*=0.5;} return s; }
      void main(){
        vec3 d = normalize(vDir);
        float y = d.y;
        vec3 col = y > 0.0 ? mix(uHor, uTop, pow(clamp(y,0.0,1.0), 0.55)) : mix(uHor, uBot, clamp(-y*4.0,0.0,1.0));
        float glow = exp(-abs(y) * 9.0) * uGlowS;
        col += uGlow * glow;
        // Cloud layer
        vec2 cp = d.xz / max(0.08, y + 0.15) * 0.6 + vec2(uTime*0.004, uTime*0.002);
        float cl = fbm(cp * 1.5);
        float cloudMask = smoothstep(0.0, 0.35, y) * smoothstep(0.35, 0.75, cl);
        col = mix(col, uHor * 1.25 + uGlow * 0.08, cloudMask * 0.55);
        // Distant storm: violet glow pockets near the horizon
        if (uStorm > 0.5) {
          float st = smoothstep(0.55, 0.8, fbm(d.xz * 3.0 + vec2(uTime*0.01))) * exp(-abs(y - 0.08) * 12.0);
          col += vec3(0.25, 0.12, 0.45) * st * (0.4 + 0.6 * uFlash);
        }
        col += vec3(0.55, 0.6, 0.75) * uFlash * (0.25 + cloudMask * 0.9) * smoothstep(-0.05, 0.3, y);
        gl_FragColor = vec4(col, 1.0);
      }`,
    side: THREE.BackSide,
    depthWrite: false,
    fog: false,
  });
  const m = new THREE.Mesh(new THREE.SphereGeometry(400, 32, 16), mat);
  m.frustumCulled = false;
  m.renderOrder = -10;
  m.name = 'sky';
  return m;
}

/** Bake a PMREM environment map from a simple procedural scene (sky gradient + glow sources). */
export function bakeEnvironment(renderer: THREE.WebGLRenderer, cfg: SkyConfig, lights: { dir: THREE.Vector3; color: number; size: number; intensity: number }[] = []): THREE.Texture {
  const scene = new THREE.Scene();
  const sky = createSky({ ...cfg, glowStrength: (cfg.glowStrength ?? 0.5) * 1.2 });
  (sky.material as THREE.ShaderMaterial).uniforms.uTime.value = 0;
  sky.scale.setScalar(0.1);
  scene.add(sky);
  for (const l of lights) {
    const m = new THREE.Mesh(new THREE.SphereGeometry(l.size, 12, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(l.color).multiplyScalar(l.intensity) }));
    m.position.copy(l.dir).normalize().multiplyScalar(30);
    scene.add(m);
  }
  const pmrem = new THREE.PMREMGenerator(renderer);
  const rt = pmrem.fromScene(scene, 0.02, 0.1, 100);
  pmrem.dispose();
  scene.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (mesh.isMesh) {
      mesh.geometry.dispose();
      (mesh.material as THREE.Material).dispose();
    }
  });
  return rt.texture;
}
