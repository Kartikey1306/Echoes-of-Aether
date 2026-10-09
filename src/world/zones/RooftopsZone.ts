import * as THREE from 'three';
import type RAPIER from '@dimforge/rapier3d-compat';
import { rng } from '../../core/MathUtil';
import { bakeEnvironment, createSky } from '../../render/Environment';
import { getMaterial } from '../../render/Materials';
import { Weather } from '../../render/Weather';
import { LevelBuilder } from '../kit/LevelBuilder';
import * as P from '../kit/Props';
import { Zone, type BuildContext, type ZoneRuntime } from '../Zone';

// Rooftop Sector above the Collapsed Market.
//  R1 entry roof x[-6,10] z[-6,10] top 14 (ladder from the market)
//  R2 hollow building x[14,28] z[-4,8] roof 15.5 (Anya's hidden room inside, hatch at x=20,z=6)
//  R3 shed roof x[-4,12] z[16,30] top 16 (stair ramp from R1)
//  R4 x[18,30] z[18,32] top 16 (6 m gap from R3: Phase Dash, or the beam from R2)
//  R5 relay roof x[30,44] z[-10,6] top 19 (ladder from R2)

export class RooftopsZone extends Zone {
  private hatch!: THREE.Mesh;
  private hatchCollider: RAPIER.Collider | null = null;
  private relayOn = false;
  private relayGlow!: THREE.Mesh;
  private beacon: THREE.Sprite | null = null;

  constructor() {
    super('rooftops');
    this.killY = 6;
    this.music = 'sidequest';
    this.ambience = 'wind_roof';
    this.grade = { exposure: 1.3, contrast: 1.08, saturation: 0.95, lift: [0.004, 0.006, 0.02], gain: [0.97, 1.0, 1.05], bloomThreshold: 0.88 };
  }

  async build(ctx: BuildContext) {
    const S = this.scene;
    const b = (this.builder = new LevelBuilder(this.root, ctx.physics));
    b.lightBudget = 10;
    const skyCfg = { top: 0x080c14, horizon: 0x34405a, bottom: 0x0a0d12, glow: 0x6a4a78, glowStrength: 1.0, storm: true };
    const sky = createSky(skyCfg);
    S.add(sky);
    S.environment = bakeEnvironment(ctx.rs.renderer, skyCfg, [{ dir: new THREE.Vector3(-0.4, 0.3, -1), color: 0x5fd8ff, size: 5, intensity: 1.6 }]);
    S.environmentIntensity = 0.9;
    S.fog = new THREE.FogExp2(0x1e2a3a, 0.0085);
    const hemi = new THREE.HemisphereLight(0x6a84a8, 0x16181e, 1.4);
    S.add(hemi);
    const moon = new THREE.DirectionalLight(0xb8c8e8, 2.0);
    moon.position.set(-40, 60, -30);
    moon.castShadow = true;
    S.add(moon, moon.target);
    this.sun = moon;
    await ctx.progress(0.1, 'Skyline');

    // ---------------------------------------------------------------- Buildings under the roofs
    const block = (x0: number, z0: number, x1: number, z1: number, top: number, mat: 'concrete' | 'brick' | 'plaster' | 'concrete_dark') => {
      const cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
      b.box(cx, top / 2 - 0.25, cz, x1 - x0, top - 0.5, z1 - z0, mat);
      b.box(cx, top - 0.15, cz, x1 - x0, 0.3, z1 - z0, 'concrete_wet');
      // parapets
      const ph = 0.9;
      b.box(cx, top + ph / 2, z0 + 0.12, x1 - x0, ph, 0.24, mat, { collide: false });
      b.box(cx, top + ph / 2, z1 - 0.12, x1 - x0, ph, 0.24, mat, { collide: false });
      b.box(x0 + 0.12, top + ph / 2, cz, 0.24, ph, z1 - z0, mat, { collide: false });
      b.box(x1 - 0.12, top + ph / 2, cz, 0.24, ph, z1 - z0, mat, { collide: false });
      // Window grid on the faces
      const r = rng(Math.round(x0 * 7 + z0 * 13));
      for (let y = 2; y < top - 1.5; y += 3.4) {
        for (let x = x0 + 1.5; x < x1 - 1; x += 2.8) {
          for (const z of [z0 - 0.04, z1 + 0.04]) b.box(x, y, z, 1.4, 1.5, 0.06, r.next() < 0.08 ? 'win_warm' : 'glass_dark', { collide: false, shadow: false });
        }
      }
    };
    block(-6, -6, 10, 10, 14, 'brick');
    block(-4, 16, 12, 30, 16, 'concrete');
    block(18, 18, 30, 32, 16, 'plaster');
    block(30, -10, 44, 6, 19, 'concrete_dark');
    // R2 is hollow (Anya's room): floor, walls and a roof with a hatch opening.
    b.box(21, 5.5, 2, 14, 11.5, 12, 'concrete');
    b.box(21, 11.5, 2, 14, 0.3, 12, 'wood');
    for (const [x, z, w, d] of [[21, -3.85, 14, 0.3], [21, 7.85, 14, 0.3], [14.15, 2, 0.3, 12], [27.85, 2, 0.3, 12]] as [number, number, number, number][]) b.box(x, 13.5, z, w, 4, d, 'concrete');
    // Roof slabs leaving a 1.2 m hatch at x[19.4,20.6] z[5.4,6.6]
    b.box(16.7, 15.35, 2, 5.4, 0.3, 12, 'concrete_wet');
    b.box(24.3, 15.35, 2, 7.4, 0.3, 12, 'concrete_wet');
    b.box(20, 15.35, -0.7, 1.2, 0.3, 6.6, 'concrete_wet');
    b.box(20, 15.35, 7.3, 1.2, 0.3, 1.4, 'concrete_wet');
    this.hatch = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.12, 1.2), getMaterial('metal_dark'));
    this.hatch.position.set(20, 15.45, 6);
    b.object(this.hatch);
    if (!ctx.flag('anya_hatch_open')) this.hatchCollider = b.physics.addBox(20, 15.4, 6, 0.6, 0.1, 0.6);
    else this.hatch.visible = false;
    for (const [x, z, w, d] of [[21, -3.85, 14, 0.24], [21, 7.85, 14, 0.24], [14.15, 2, 0.24, 12], [27.85, 2, 0.24, 12]] as [number, number, number, number][]) b.box(x, 15.95, z, w, 0.9, d, 'concrete', { collide: false });
    // Anya's room interior
    b.box(24, 12.2, 5.5, 3, 0.08, 1.2, 'wood');
    b.box(24, 11.85, 5.5, 2.8, 0.7, 0.1, 'wood');
    b.box(23.4, 12.45, 5.7, 0.8, 0.4, 0.4, 'metal_dark', { collide: false });
    b.box(24.6, 12.45, 5.65, 0.6, 0.3, 0.02, 'screen', { collide: false });
    const at = (y: number) => {
      const g = new THREE.Group();
      this.root.add(g);
      const lb = new LevelBuilder(g, b.physics, new THREE.Vector3(0, y, 0));
      levelBuilders.push(lb);
      return lb;
    };
    const levelBuilders: LevelBuilder[] = [];
    P.crateStack(at(11.65), 16.5, -1.5, 0.2, 1201);
    b.box(20, 11.6, 6, 1, 0.1, 1, 'tarp_blue', { collide: false, shadow: false });
    for (let y = 11.7; y < 15.3; y += 0.35) b.box(20.62, y, 6, 0.04, 0.04, 0.6, 'metal_yellow', { collide: false, shadow: false });
    b.pointLight(22, 14, 2, 0xffc890, 30, 9, 1.6);
    await ctx.progress(0.3, 'Rooftops');

    // ---------------------------------------------------------------- Connections
    // R1 -> R2 plank ramp (14 -> 15.5)
    b.ramp(10, 14, 2, Math.PI / 2, 1.6, 4.4, 1.5, 0.15, 'wood');
    P.railing(b, 10, 1.2, 14, 1.2, 14, 1.0, true);
    P.railing(b, 10, 2.8, 14, 2.8, 14, 1.0, true);
    // R1 -> R3 stair ramp (14 -> 16)
    b.stairs(2, 14, 10, 0, 2.4, 6, 0.333, 1.0, 'metal_dark');
    b.box(2, 15.9, 15.5, 2.4, 0.2, 1.2, 'grate');
    // R2 -> R4 balance beam (optional route) from (24, 15.5, 8) to (24, 16, 18)
    b.box(24, 15.65, 13, 0.45, 0.25, 10.4, 'metal_yellow', { rotX: -0.05 });
    // R2 -> R5 ladder (climb)
    for (let y = 15.6; y < 19.2; y += 0.35) b.box(29.6, y, 0, 0.05, 0.04, 0.6, 'metal_yellow', { collide: false, shadow: false });
    b.box(29.6, 17.3, -0.3, 0.05, 3.6, 0.05, 'metal_dark', { collide: false });
    b.box(29.6, 17.3, 0.3, 0.05, 3.6, 0.05, 'metal_dark', { collide: false });
    // Rooftop dressing
    P.waterTank(b, -3, 14, -3);
    P.acUnit(b, 6, 14, 6, 0.3);
    P.vent(b, -2, 14, 7);
    P.acUnit(b, 25, 15.5, -2, 1.2);
    P.vent(b, 17, 15.5, -1);
    P.antenna(b, 9, 16, 28, 5);
    P.acUnit(b, 26, 16, 28, 0);
    P.vent(b, 20, 16, 22);
    P.crateStack(at(16), 28, 30, 0.6, 1202);
    P.terminal(at(14), 6, 1.6, 0);
    // Maintenance shed on R3
    b.box(3, 17.4, 23, 5, 2.8, 4, 'metal_painted');
    b.box(3, 18.9, 23, 5.4, 0.2, 4.4, 'metal_dark', { collide: false });
    b.box(3, 17.2, 25.05, 1.4, 2.4, 0.1, 'black', { collide: false });
    b.solidCollider(3, 17.4, 23, 5, 2.8, 4);
    b.box(6, 16.5, 25.6, 1.4, 1.0, 0.7, 'metal_dark');
    // Relay tower on R5
    for (const [x, z] of [[36, -4], [40, -4], [36, 0], [40, 0]] as [number, number][]) b.box(x, 25, z, 0.25, 12, 0.25, 'metal_dark');
    for (let y = 21; y < 31; y += 2.5) {
      b.box(38, y, -4, 4.2, 0.12, 0.12, 'metal_dark', { collide: false });
      b.box(38, y, 0, 4.2, 0.12, 0.12, 'metal_dark', { collide: false });
      b.box(36, y, -2, 0.12, 0.12, 4.2, 'metal_dark', { collide: false });
      b.box(40, y, -2, 0.12, 0.12, 4.2, 'metal_dark', { collide: false });
    }
    b.box(38, 31.2, -2, 0.4, 0.4, 0.4, 'metal', { collide: false });
    this.beacon = b.glowSprite(38, 31.8, -2, 2, 0xff3030, 1.2);
    b.box(38, 19.8, 2.2, 3, 1.6, 1, 'metal_dark');
    this.relayGlow = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.9, 0.04), new THREE.MeshBasicMaterial({ color: new THREE.Color(0x101820) }));
    this.relayGlow.position.set(38, 20.1, 2.72);
    b.object(this.relayGlow, false);
    b.box(35.5, 19.6, 2.2, 0.6, 0.6, 0.6, 'metal_yellow');
    b.pointLight(38, 22, 3, 0x8fd8ff, 40, 14, 1.6);
    // Street-level glow far below and the surrounding skyline
    b.box(15, 0, 10, 200, 0.2, 200, 'asphalt', { collide: false });
    for (let i = 0; i < 18; i++) P.streetLight(b, -40 + (i % 6) * 22, -40 + Math.floor(i / 6) * 40, 0, { light: false, intensity: 1.5 });
    const r = rng(77);
    for (let i = 0; i < 22; i++) {
      const a = (i / 22) * Math.PI * 2, d = 70 + r.next() * 40;
      P.building(b, 15 + Math.cos(a) * d, 10 + Math.sin(a) * d, 12 + r.next() * 10, 12 + r.next() * 10, 20 + r.next() * 45, 1300 + i, { lit: 0.12, collide: false });
    }
    // Distant Aether core glow on the horizon
    b.glowSprite(-60, 30, -140, 60, 0x5fd8ff, 0.6);
    b.glowSprite(-60, 30, -140, 25, 0xa47dff, 0.8);
    await ctx.progress(0.5, 'Relay tower');

    // Bounds: invisible walls around the roof cluster at parapet height
    b.wall(2, 15, -6.3, 16.6, 4, 0.4);
    b.wall(-6.3, 15, 2, 0.4, 4, 16.6);
    b.wall(37, 20.5, -10.3, 14.6, 4, 0.4);
    b.wall(44.3, 20.5, -2, 0.4, 4, 16.6);
    b.wall(24, 17.5, 32.3, 12.6, 4, 0.4);
    b.wall(30.3, 17.5, 25, 0.4, 4, 14.6);
    b.wall(4, 17.5, 30.3, 16.6, 4, 0.4);
    b.wall(-4.3, 17.5, 23, 0.4, 4, 14.6);

    b.finalize();
    for (const lb of levelBuilders) lb.finalize();
    this.weather = new Weather({ rain: 0.55, wind: new THREE.Vector2(6, 2), lightning: true, lightningInterval: [8, 18], splashHeight: 14.05 }, ctx.quality.effects);
    this.weather.skyMat = sky.material as THREE.ShaderMaterial;
    this.weather.flashLights.push({ light: hemi, base: hemi.intensity, boost: 3.5 }, { light: moon, base: moon.intensity, boost: 2.5 });
    S.add(this.weather.group);
    this.layout();
    this.map = {
      min: new THREE.Vector2(-10, -14),
      max: new THREE.Vector2(48, 36),
      shapes: [
        { kind: 'floor', x: 2, z: 2, w: 16, d: 16 },
        { kind: 'floor', x: 21, z: 2, w: 14, d: 12 },
        { kind: 'floor', x: 4, z: 23, w: 16, d: 14 },
        { kind: 'floor', x: 24, z: 25, w: 12, d: 14 },
        { kind: 'floor', x: 37, z: -2, w: 14, d: 16 },
        { kind: 'road', x: 12, z: 2, w: 4, d: 1.6 },
        { kind: 'road', x: 24, z: 13, w: 0.6, d: 10 },
        { kind: 'block', x: 3, z: 23, w: 5, d: 4 },
      ],
      labels: [{ text: 'LADDER', x: 0, z: 0 }, { text: 'SHED', x: 3, z: 23 }, { text: 'RELAY', x: 38, z: -2 }, { text: 'BEAM', x: 24, z: 13 }],
    };
  }

  private layout() {
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    const rt = () => this.rtRef;
    this.spawns = {
      start: { pos: v(0, 14.05, 1), yaw: Math.PI * 0.5 },
      from_market: { pos: v(0, 14.05, 1), yaw: Math.PI * 0.5 },
    };
    this.exits.push(
      { id: 'x_roof_market', target: 'plaza', entry: 'from_rooftops', pos: v(-1.2, 14.05, -1.5), radius: 1.4, prompt: 'Climb down to the market' },
      { id: 'i_drop_plaza', target: 'plaza', entry: 'camp', pos: v(29, 16.05, 20), radius: 1.6, prompt: 'Drop down to the survivors\' camp (shortcut)' },
    );
    this.triggers.push(
      { id: 't_roof_r2', box: new THREE.Box3(v(14, 15, -4), v(28, 19, 8)) },
      { id: 't_roof_r4', box: new THREE.Box3(v(18, 15.5, 18), v(30, 19, 32)) },
    );
    this.encounters.push(
      { id: 'e_roof_drones', spawn: 'trigger:t_roof_r2', waves: [[{ type: 'drone', pos: v(18, 20, -2) }, { type: 'drone', pos: v(26, 20.5, 5) }, { type: 'drone', pos: v(12, 19.5, 10) }]], arena: { center: v(18, 15, 8), radius: 26 } },
      { id: 'e_roof_stalkers', spawn: 'trigger:t_roof_r4', waves: [[{ type: 'stalker', pos: v(26, 16.05, 28) }, { type: 'stalker', pos: v(21, 16.05, 30) }]], arena: { center: v(24, 16, 25), radius: 12 } },
    );
    this.collectibles.push(
      { id: 'c_frag_10', pos: v(28.5, 17.0, 31) },
      { id: 'c_frag_11', pos: v(42.5, 20.0, -9) },
      { id: 'c_cache_04', pos: v(-2.5, 16.6, 28.5) },
    );
    this.itemPickups.push(
      { id: 'i_control_component', item: 'q_control_component', pos: v(6, 17.15, 25.6), cond: ['quest:sq_broken_guardian:active'] },
      { id: 'i_relay_cell', item: 'q_relay_cell', pos: v(1.2, 16.6, 25.6), cond: ['quest:sq_last_signal:active'] },
      { id: 'i_anya_recording', item: 'q_anya_recording', pos: v(24, 12.4, 5.3), cond: ['quest:sq_last_signal:active'] },
    );
    this.questPoint('i_relay_tower', v(38, 20.4, 3.4), 'Inspect the relay transmitter', ['stage:sq_last_signal:locate'], { radius: 2.4 });
    this.addInteractable({
      id: 'i_relay_socket', kind: 'inspect', pos: v(35.5, 20.2, 3.2), radius: 2.2, prompt: 'Insert the relay power cell',
      available: () => rt()?.check('stage:sq_last_signal:activate') ?? false,
      onInteract: () => {
        this.setRelay(true);
        rt()?.setFlag('relay_active');
        rt()?.sfx('door', v(38, 20, 2));
        rt()?.emitInteract('i_relay_socket');
      },
    });
    this.addInteractable({
      id: 'i_hidden_hatch', kind: 'door', pos: v(20, 15.6, 6), radius: 2.4, prompt: 'Open the hidden hatch', hidden: true,
      available: () => !!this.hatchCollider,
      onInteract: async () => {
        this.openHatch();
        rt()?.setFlag('anya_hatch_open');
        rt()?.emitInteract('i_hidden_hatch');
        await rt()?.traverse([v(20, 15.5, 6), v(20, 11.7, 6), v(20.6, 11.7, 5)], 'climb', 1.6);
      },
    });
    this.addInteractable({
      id: 'i_hatch_ladder', kind: 'ladder', pos: v(20.4, 12.6, 6), radius: 1.6, prompt: 'Climb back up',
      available: () => !this.hatchCollider,
      onInteract: () => rt()?.traverse([v(20.3, 11.7, 6), v(20.3, 15.6, 6), v(20, 15.65, 4.6)], 'climb', 2.2),
    });
    this.addInteractable({
      id: 'i_ladder_r5', kind: 'ladder', pos: v(28.9, 16.4, 0), radius: 1.6, prompt: 'Climb to the relay roof',
      onInteract: () => rt()?.traverse([v(29.1, 15.55, 0), v(29.1, 19.1, 0), v(31, 19.05, 0)], 'climb', 2.4, Math.PI / 2),
    });
    this.addInteractable({
      id: 'i_ladder_r5_down', kind: 'ladder', pos: v(30.6, 19.8, 0), radius: 1.4, prompt: 'Climb down',
      onInteract: () => rt()?.traverse([v(30.6, 19.05, 0), v(29.1, 19.05, 0), v(29.1, 15.55, 0), v(27.5, 15.55, 0)], 'climb', 2.4, -Math.PI / 2),
    });
    this.addInteractable({ id: 'i_save_roof', kind: 'save', pos: v(6, 15.3, 2), radius: 2, prompt: 'Use save terminal', onInteract: () => undefined });
  }

  private setRelay(on: boolean) {
    this.relayOn = on;
    (this.relayGlow.material as THREE.MeshBasicMaterial).color.set(on ? 0x5fd8ff : 0x101820).multiplyScalar(on ? 1.6 : 1);
    if (this.beacon) (this.beacon.material as THREE.SpriteMaterial).color.set(on ? 0x5fd8ff : 0xff3030).multiplyScalar(1.2);
  }

  private openHatch() {
    if (this.hatchCollider) {
      this.rtRef?.removeCollider(this.hatchCollider);
      this.hatchCollider = null;
    }
    this.hatch.visible = false;
    this.rtRef?.sfx('door', this.hatch.position);
  }

  onEnter(rt: ZoneRuntime) {
    if (rt.flag('relay_active')) this.setRelay(true);
    if (rt.flag('anya_hatch_open')) this.openHatch();
    rt.vfx.addEmitter(new THREE.Vector3(-2, 15.4, 7), 'steam', 2);
    rt.vfx.addEmitter(new THREE.Vector3(17, 16.9, -1), 'steam', 2);
  }

  update(dt: number, rt: ZoneRuntime) {
    super.update(dt, rt);
    if (this.beacon) this.beacon.material.opacity = 0.5 + 0.5 * Math.max(0, Math.sin(this.time * (this.relayOn ? 4 : 1.5)));
  }
}
