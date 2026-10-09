import * as THREE from 'three';
import { rng } from '../../core/MathUtil';
import { bakeEnvironment } from '../../render/Environment';
import { getMaterial } from '../../render/Materials';
import { LevelBuilder } from '../kit/LevelBuilder';
import * as P from '../kit/Props';
import { Zone, type BuildContext, type ZoneRuntime } from '../Zone';

// The Aether Core: a circular chamber (radius ~27) with the Core suspended above the centre.
// Lift arrives at the south edge (z≈31). The heart pedestal sits at the centre beneath the Core.

interface Strike { pos: THREE.Vector3; t: number; ring: THREE.Mesh; fired: boolean }

export class CoreZone extends Zone {
  private core!: THREE.Mesh;
  private coreInner!: THREE.Mesh;
  private rings: THREE.Mesh[] = [];
  private debris: { mesh: THREE.Object3D; axis: THREE.Vector3; speed: number; orbit: number; r: number; y: number; a: number }[] = [];
  private tethers: THREE.Mesh[] = [];
  private coreLight: THREE.PointLight | null = null;
  private strikes: Strike[] = [];
  private strikeT = 4;
  released = false;

  constructor() {
    super('core');
    this.indoor = true;
    this.killY = -20;
    this.music = 'boss';
    this.ambience = 'core_drone';
    this.grade = { exposure: 0.95, contrast: 1.1, saturation: 1.05, lift: [0.0, 0.006, 0.02], gain: [0.96, 1.0, 1.06], bloomThreshold: 0.95 };
  }

  async build(ctx: BuildContext) {
    const S = this.scene;
    const b = (this.builder = new LevelBuilder(this.root, ctx.physics));
    b.lightBudget = 10;
    S.background = new THREE.Color(0x02040a);
    S.fog = new THREE.FogExp2(0x060a16, 0.008);
    S.environment = bakeEnvironment(ctx.rs.renderer, { top: 0x0c1830, horizon: 0x101c34, bottom: 0x04060c }, [
      { dir: new THREE.Vector3(0, 1, 0), color: 0x5fd8ff, size: 8, intensity: 2.4 },
      { dir: new THREE.Vector3(0.6, 0.4, 0.6), color: 0xa47dff, size: 5, intensity: 1.5 },
    ]);
    S.environmentIntensity = 0.9;
    const hemi = new THREE.HemisphereLight(0x4a6a9a, 0x0c0a14, 1.1);
    S.add(hemi);
    const key = new THREE.DirectionalLight(0x9ad8ff, 1.0);
    key.position.set(5, 50, 10);
    key.castShadow = true;
    S.add(key, key.target);
    this.sun = key;
    await ctx.progress(0.1, 'Core chamber');

    // ---------------------------------------------------------------- Arena floor: central disc + broken outer ring
    b.cyl(0, -0.5, 0, 27, 27.5, 1.0, 'metal_dark', 64);
    b.cyl(0, 0.01, 0, 26.8, 26.8, 0.02, 'grate', 64, { collide: false, open: true });
    for (let i = 0; i < 24; i++) {
      const a = (i / 24) * Math.PI * 2;
      b.box(Math.sin(a) * 26.6, 0.1, Math.cos(a) * 26.6, 0.4, 0.2, 6.6, 'emit_cyan', { rotY: a + Math.PI / 2, collide: false, shadow: false });
    }
    // Outer machinery wall
    for (let i = 0; i < 36; i++) {
      const a = (i / 36) * Math.PI * 2;
      const r = 33;
      if (Math.abs(Math.sin(a / 2)) < 0.06) continue; // gap at the lift (south)
      const h = 12 + (i % 3) * 4;
      b.box(Math.sin(a) * r, h / 2 - 1, Math.cos(a) * r, 5.8, h, 2, i % 4 === 0 ? 'metal' : 'metal_dark', { rotY: a });
      if (i % 2 === 0) b.box(Math.sin(a) * (r - 1.05), h * 0.6, Math.cos(a) * (r - 1.05), 0.3, h * 0.7, 0.1, i % 4 === 0 ? 'emit_violet' : 'emit_cyan', { rotY: a, collide: false, shadow: false });
    }
    // Invisible fence at the arena edge (falls are allowed at the broken gaps only).
    for (let i = 0; i < 32; i++) {
      const a = (i / 32) * Math.PI * 2;
      if (Math.abs(Math.cos(a) - 1) < 0.02) continue;
      b.wall(Math.sin(a) * 27.6, 2, Math.cos(a) * 27.6, 5.6, 4, 0.5, a + Math.PI / 2);
    }
    // Lift landing (south)
    b.box(0, -0.25, 31, 8, 0.5, 8, 'metal_dark');
    for (const [x, z, w, d] of [[0, 28, 6, 0.12], [0, 34, 6, 0.12], [-3, 31, 0.12, 6], [3, 31, 0.12, 6]] as [number, number, number, number][]) b.box(x, 0.02, z, w, 0.04, d, 'emit_cyan', { collide: false, shadow: false });
    b.wall(0, 2, 35.2, 8, 4, 0.4);
    b.wall(-4.2, 2, 31, 0.4, 4, 8);
    b.wall(4.2, 2, 31, 0.4, 4, 8);
    // Damaged platforms and cover
    const r = rng(404);
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2 + 0.2;
      const d = 14 + r.next() * 8;
      b.box(Math.sin(a) * d, 0.6, Math.cos(a) * d, 2 + r.next() * 2, 1.2 + r.next(), 1.4, 'metal', { rotY: a, rotZ: r.range(-0.1, 0.1) });
    }
    P.debris(b, -12, -10, 2.4, 8, 405, 'metal_dark');
    P.debris(b, 14, 6, 2.4, 8, 406, 'metal_dark');
    await ctx.progress(0.3, 'Arena');

    // ---------------------------------------------------------------- Heart pedestal and the Core
    b.cyl(0, 0.6, 0, 3.2, 3.8, 1.2, 'metal', 32);
    b.cyl(0, 1.22, 0, 2.6, 2.6, 0.04, 'emit_cyan', 48, { collide: false });
    // Dedicated, dimmer instance of the Aether shader for the giant core so it doesn't flood the bloom.
    const coreMat = (getMaterial('aether') as THREE.ShaderMaterial).clone();
    coreMat.uniforms.uTime = (getMaterial('aether') as THREE.ShaderMaterial).uniforms.uTime;
    coreMat.uniforms.uIntensity = { value: 0.75 };
    this.core = new THREE.Mesh(new THREE.IcosahedronGeometry(6, 5), coreMat);
    this.core.position.set(0, 15, 0);
    b.object(this.core, false);
    this.coreInner = new THREE.Mesh(new THREE.IcosahedronGeometry(3.6, 3), new THREE.MeshBasicMaterial({ color: new THREE.Color(0x8fdcff).multiplyScalar(1.15) }));
    this.coreInner.position.copy(this.core.position);
    b.object(this.coreInner, false);
    for (let i = 0; i < 4; i++) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(8 + i * 1.6, 0.25, 8, 96, Math.PI * (1.6 + (i % 2) * 0.3)), getMaterial('metal'));
      ring.position.copy(this.core.position);
      ring.rotation.set(i * 0.7, i * 1.3, 0);
      b.object(ring, false);
      const glow = new THREE.Mesh(new THREE.TorusGeometry(8 + i * 1.6, 0.06, 6, 96, Math.PI * (1.5 + (i % 2) * 0.3)), getMaterial(i % 2 ? 'emit_violet' : 'emit_cyan'));
      ring.add(glow);
      this.rings.push(ring);
    }
    // Energy tethers from the floor to the Core
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      const base = new THREE.Vector3(Math.sin(a) * 20, 0, Math.cos(a) * 20);
      const top = this.core.position.clone().add(new THREE.Vector3(Math.sin(a) * 4, -2, Math.cos(a) * 4));
      const len = base.distanceTo(top);
      const m = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.3, len, 8, 1, true), getMaterial('aether'));
      m.position.copy(base).lerp(top, 0.5);
      m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), top.clone().sub(base).normalize());
      b.object(m, false);
      this.tethers.push(m);
      b.cyl(base.x, 0.8, base.z, 0.9, 1.2, 1.6, 'metal_dark', 10);
    }
    this.coreLight = b.pointLight(0, 12, 0, 0x7fe0ff, 320, 60, 1.5);
    b.pointLight(0, 4, 24, 0x8fd8ff, 40, 16, 1.6);
    // Floating debris
    for (let i = 0; i < 26; i++) {
      const g = new THREE.Mesh(new THREE.BoxGeometry(r.range(0.6, 2.4), r.range(0.4, 1.4), r.range(0.6, 2)), getMaterial(r.chance(0.3) ? 'rust' : 'metal_dark'));
      g.castShadow = true;
      this.root.add(g);
      this.debris.push({ mesh: g, axis: new THREE.Vector3(r.range(-1, 1), r.range(-1, 1), r.range(-1, 1)).normalize(), speed: r.range(0.1, 0.5), orbit: r.range(0.02, 0.06) * r.sign(), r: r.range(10, 26), y: r.range(6, 24), a: r.range(0, Math.PI * 2) });
    }
    await ctx.progress(0.5, 'The Core');
    b.finalize();
    this.layout();
    this.map = {
      min: new THREE.Vector2(-34, -34),
      max: new THREE.Vector2(34, 36),
      shapes: [{ kind: 'floor', x: 0, z: 0, w: 52, d: 52 }, { kind: 'water', x: 0, z: 0, w: 7, d: 7 }, { kind: 'floor', x: 0, z: 31, w: 8, d: 8 }],
      labels: [{ text: 'HEART', x: 0, z: 0 }, { text: 'LIFT', x: 0, z: 31 }],
    };
  }

  private layout() {
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    this.spawns = {
      start: { pos: v(0, 0.05, 30), yaw: Math.PI },
      from_vault: { pos: v(0, 0.05, 30), yaw: Math.PI },
    };
    this.exits.push({ id: 'x_core_vault', target: 'vault', entry: 'from_core', pos: v(0, 0.05, 33.5), radius: 1.6, prompt: 'Ride the lift back up', requires: () => !(this.rtRef?.check('stage:m5_core:boss') ?? false) && !(this.rtRef?.check('stage:m5_core:waves') ?? false), lockedText: 'The lift won\'t move while the Core is under attack.' });
    this.encounters.push(
      { id: 'e_core_waves', spawn: 'quest', waves: [
        [{ type: 'drone', pos: v(-10, 6, -6) }, { type: 'drone', pos: v(10, 6, -6) }, { type: 'stalker', pos: v(-8, 0.05, 4) }, { type: 'stalker', pos: v(8, 0.05, 4) }],
        [{ type: 'sentinel', pos: v(-12, 0.05, -12) }, { type: 'sentinel', pos: v(12, 0.05, -12) }, { type: 'stalker', pos: v(0, 0.05, -18) }, { type: 'drone', pos: v(0, 7, 0) }],
      ], arena: { center: v(0, 0, 0), radius: 26 } },
      { id: 'e_core_guardian', spawn: 'quest', waves: [[{ type: 'guardian', pos: v(0, 0.05, -14), yaw: 0 }]], arena: { center: v(0, 0, 0), radius: 26 } },
    );
    this.questPoint('i_core_terminal', v(0, 1.4, 22), 'Approach the Core', ['stage:m5_core:listen'], { radius: 5 });
    this.questPoint('i_core_heart', v(0, 1.6, 3.2), 'Release the echoes', ['stage:m5_core:release'], { radius: 3.6 });
    this.markers.heart = v(0, 1.25, 0);
    this.markers.core = v(0, 15, 0);
  }

  onEnter(rt: ZoneRuntime) {
    rt.vfx.addEmitter(new THREE.Vector3(0, 1.3, 0), 'aether', 14, 2.5);
    rt.vfx.addEmitter(new THREE.Vector3(0, 0.3, 0), 'aether', 10, 22);
  }

  /** Telegraphed energy discharge (boss fight hazard). */
  private strike(rt: ZoneRuntime) {
    const p = rt.playerPos;
    const pos = new THREE.Vector3(p.x + (Math.random() - 0.5) * 6, 0.05, p.z + (Math.random() - 0.5) * 6);
    if (pos.length() > 25) pos.setLength(24);
    const ring = new THREE.Mesh(new THREE.RingGeometry(2.2, 2.5, 32).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: new THREE.Color(0xa47dff).multiplyScalar(2), transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending, depthWrite: false }));
    ring.position.copy(pos).setY(0.08);
    this.scene.add(ring);
    this.strikes.push({ pos, t: 0, ring, fired: false });
    rt.sfx('enemy_telegraph', pos);
  }

  update(dt: number, rt: ZoneRuntime) {
    super.update(dt, rt);
    const t = this.time;
    const intensity = this.released ? 2.2 : 1;
    this.core.rotation.y += dt * 0.08 * intensity;
    this.core.scale.setScalar(1 + Math.sin(t * 1.4) * 0.03 * intensity);
    this.coreInner.rotation.y -= dt * 0.2;
    this.rings.forEach((r, i) => {
      r.rotation.x += dt * (0.05 + i * 0.02) * intensity;
      r.rotation.y += dt * (0.03 + i * 0.015) * (i % 2 ? -1 : 1) * intensity;
    });
    for (const d of this.debris) {
      d.a += d.orbit * dt;
      d.mesh.position.set(Math.sin(d.a) * d.r, d.y + Math.sin(t * 0.4 + d.r) * 0.6, Math.cos(d.a) * d.r);
      d.mesh.rotateOnAxis(d.axis, d.speed * dt);
    }
    if (this.coreLight) this.coreLight.intensity = (300 + Math.sin(t * 1.4) * 40) * (this.released ? 1.8 : 1);
    (this.core.material as THREE.ShaderMaterial).uniforms.uIntensity.value = this.released ? 1.6 : 0.75;
    // Discharges during the boss fight.
    if (rt.check('stage:m5_core:boss')) {
      this.strikeT -= dt;
      if (this.strikeT <= 0) {
        this.strikeT = 3.5 + Math.random() * 2.5;
        this.strike(rt);
      }
    }
    for (const s of this.strikes) {
      s.t += dt;
      const m = s.ring.material as THREE.MeshBasicMaterial;
      s.ring.scale.setScalar(1 - Math.min(0.6, s.t * 0.4));
      m.opacity = 0.5 + Math.sin(s.t * 20) * 0.3;
      if (!s.fired && s.t > 1.3) {
        s.fired = true;
        rt.vfx.flash(s.pos.clone().setY(1.5), 4, 0xc8a8ff, 0.2);
        rt.vfx.sparks(s.pos.clone().setY(0.3), new THREE.Vector3(0, 1, 0), 30, 0xc8a8ff, 9);
        rt.vfx.light(s.pos.clone().setY(2), 0xa47dff, 60, 0.3);
        rt.sfx('slam', s.pos);
        rt.shake(0.2);
        const p = rt.playerPos;
        if (p.distanceTo(s.pos) < 2.6 && p.y < 1.2) rt.damagePlayer(18, 'discharge', s.pos);
      }
    }
    for (const s of this.strikes.filter((x) => x.t > 1.6)) {
      s.ring.removeFromParent();
      s.ring.geometry.dispose();
      (s.ring.material as THREE.Material).dispose();
    }
    this.strikes = this.strikes.filter((x) => x.t <= 1.6);
    void rng;
  }
}
