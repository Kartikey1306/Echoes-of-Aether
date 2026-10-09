import * as THREE from 'three';
import { HumanModel } from '../actors/human/HumanModel';
import { LOOKS } from '../actors/human/Looks';
import { RenderSystem } from '../render/Renderer';

// Developer tool: renders characters on a stage for visual inspection and screenshot capture.
// URL: ?view=chars&ids=kael,lyra&anim=idle&yaw=0&dist=4&h=1.2&speed=0

export async function runCharacterViewer(params: URLSearchParams) {
  const app = document.getElementById('app')!;
  const rs = new RenderSystem(app, { resolution: 'native', shadows: 'high', effects: 'high', textures: 'high', viewDistance: 'high', antialiasing: 'msaa', frameLimit: 'vsync' });
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0b0f14);
  scene.fog = new THREE.FogExp2(0x0b0f14, 0.03);
  const hemi = new THREE.HemisphereLight(0x8fa8c8, 0x1a1612, 0.9);
  scene.add(hemi);
  const key = new THREE.DirectionalLight(0xffe8d0, parseFloat(params.get('key') ?? '3.2'));
  key.position.set(3, 6, 5);
  key.castShadow = true;
  scene.add(key, key.target);
  const rim = new THREE.DirectionalLight(0x6fc8ff, 2.2);
  rim.position.set(-4, 3, -5);
  scene.add(rim);
  const fill = new THREE.PointLight(0xa080ff, 6, 10, 2);
  fill.position.set(-2, 1.5, 2);
  scene.add(fill);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(8, 48).rotateX(-Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0x1b1f24, roughness: 0.35, metalness: 0.1 }));
  ground.receiveShadow = true;
  scene.add(ground);
  const pmrem = new THREE.PMREMGenerator(rs.renderer);
  const envScene = new THREE.Scene();
  envScene.background = new THREE.Color(0x223040);
  const envLight = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 8), new THREE.MeshBasicMaterial({ color: 0x8090a0, side: THREE.BackSide }));
  envScene.add(envLight);
  scene.environment = pmrem.fromScene(envScene, 0.04).texture;
  scene.environmentIntensity = 0.4;

  const ids = (params.get('ids') ?? 'kael,lyra').split(',');
  const anim = params.get('anim') ?? 'idle';
  const speed = parseFloat(params.get('speed') ?? '0');
  const models: HumanModel[] = [];
  ids.forEach((id, i) => {
    const look = LOOKS[id];
    if (!look) return;
    const m = new HumanModel(look, { lods: parseInt(params.get('lods') ?? '1') });
    m.root.position.x = (i - (ids.length - 1) / 2) * 1.1;
    m.root.rotation.y = parseFloat(params.get('yaw') ?? '0') * (Math.PI / 180);
    scene.add(m.root);
    models.push(m);
    if (anim === 'combat') m.animator.combatStance = 1;
    else if (anim !== 'idle' && m.anims.clips[anim]) m.animator.play(m.anims.clips[anim], { hold: true, fadeIn: 0 });
    m.animator.speed = speed;
  });
  (window as unknown as { __models: HumanModel[] }).__models = models;
  rs.setScene(scene);
  rs.setGrade({ exposure: parseFloat(params.get('exp') ?? '1.0') });
  const cam = rs.camera;
  const dist = parseFloat(params.get('dist') ?? '4');
  const h = parseFloat(params.get('h') ?? '1.0');
  const orbit = parseFloat(params.get('orbit') ?? '0') * (Math.PI / 180);
  cam.position.set(Math.sin(orbit) * dist, h + parseFloat(params.get('ch') ?? '0.2'), Math.cos(orbit) * dist);
  cam.lookAt(0, h, 0);
  cam.fov = parseFloat(params.get('fov') ?? '40');
  cam.updateProjectionMatrix();
  const t0 = parseFloat(params.get('t') ?? '0');
  // Advance to the requested time deterministically.
  for (let i = 0; i < Math.round(t0 * 60); i++) models.forEach((m) => m.update(1 / 60));
  let last = performance.now();
  const loop = () => {
    const now = performance.now();
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    if (params.get('freeze') !== '1') models.forEach((m) => m.update(dt));
    rs.updateShadowFocus(new THREE.Vector3());
    rs.render(now / 1000);
    requestAnimationFrame(loop);
  };
  loop();
  (window as unknown as { __ready: boolean }).__ready = true;
  (window as unknown as { __stats: unknown }).__stats = models.map((m) => ({ id: m.look.id, tris: m.stats.triangles }));
}
