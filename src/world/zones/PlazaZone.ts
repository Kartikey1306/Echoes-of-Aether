import * as THREE from 'three';
import { rng } from '../../core/MathUtil';
import { bakeEnvironment, createSky } from '../../render/Environment';
import { getMaterial } from '../../render/Materials';
import { Weather } from '../../render/Weather';
import { LevelBuilder } from '../kit/LevelBuilder';
import * as P from '../kit/Props';
import { Zone, type BuildContext, type ZoneRuntime } from '../Zone';

// Central Plaza (hub) + Collapsed Market, night, heavy rain.
// Layout (metres): square x[-32,32] z[-32,32] with the monument at the origin; ring road to |44|;
// survivors' camp NE; metro stairwell W; facility gate N; elevated rail E; market street S to z=112.

export class PlazaZone extends Zone {
  private monumentCore!: THREE.Mesh;
  private monumentRings: THREE.Object3D[] = [];
  private monumentLight: THREE.PointLight | null = null;
  private fireLight: THREE.PointLight | null = null;
  private flickers: { light: THREE.PointLight | null; mesh?: THREE.Object3D; base: number; seed: number }[] = [];
  private gate!: THREE.Object3D;
  private gateOpen = false;
  private gateCollider: import('@dimforge/rapier3d-compat').Collider | null = null;
  rt: ZoneRuntime | null = null;

  constructor() {
    super('plaza');
    this.killY = -12;
    this.bounds.set(new THREE.Vector3(-48, -15, -50), new THREE.Vector3(48, 60, 116));
    this.music = 'explore';
    this.ambience = 'rain_city';
    this.grade = { exposure: 1.3, contrast: 1.08, saturation: 0.92, lift: [0.0, 0.006, 0.016], gain: [0.98, 1.0, 1.04], bloomThreshold: 0.9 };
  }

  /** After the ending the city wakes at dawn: no rain, warm low sun. */
  dawn = false;

  async build(ctx: BuildContext) {
    const b = (this.builder = new LevelBuilder(this.root, ctx.physics));
    b.lightBudget = 12;
    const S = this.scene;
    this.dawn = ctx.flag('game_complete');

    // ---------------------------------------------------------------- Sky, light, fog
    const skyCfg = this.dawn
      ? { top: 0x2a4a7a, horizon: 0xf0a878, bottom: 0x3a3030, glow: 0xffc890, glowStrength: 1.2, storm: false }
      : { top: 0x070b12, horizon: 0x2c3a4e, bottom: 0x0a0d12, glow: 0x5a4058, glowStrength: 0.8, storm: true };
    const sky = createSky(skyCfg);
    S.add(sky);
    S.environment = bakeEnvironment(ctx.rs.renderer, skyCfg, [
      { dir: new THREE.Vector3(0, 0.3, 1), color: 0xffb070, size: 6, intensity: 1.2 },
      { dir: new THREE.Vector3(0.2, 0.6, -1), color: 0x5fd8ff, size: 4, intensity: 2 },
    ]);
    S.environmentIntensity = 1.0;
    S.fog = new THREE.FogExp2(this.dawn ? 0x8a8a90 : 0x1d2836, this.dawn ? 0.008 : 0.0125);
    const hemi = new THREE.HemisphereLight(this.dawn ? 0xa8c4e8 : 0x6a84a8, this.dawn ? 0x4a3a30 : 0x1a1c22, this.dawn ? 1.8 : 1.5);
    S.add(hemi);
    const moon = new THREE.DirectionalLight(this.dawn ? 0xffc890 : 0xa8c0e4, this.dawn ? 3.2 : 1.9);
    moon.position.set(this.dawn ? 40 : -30, this.dawn ? 18 : 50, this.dawn ? 30 : -20);
    moon.target.position.set(0, 0, 0);
    moon.castShadow = true;
    S.add(moon, moon.target);
    this.sun = moon;
    await ctx.progress(0.1, 'Sky and lighting');

    // ---------------------------------------------------------------- Ground
    // Asphalt ring around the square (four slabs so the stairwell hole stays open).
    b.box(0, -0.25, -56, 160, 0.5, 48, 'asphalt');
    b.box(0, -0.25, 81, 160, 0.5, 98, 'asphalt');
    b.box(-56, -0.25, 0, 48, 0.5, 64, 'asphalt');
    b.box(56, -0.25, 0, 48, 0.5, 64, 'asphalt');
    // Plaza paving (raised 15 cm) with the metro stairwell cut out at x[-30,-24] z[4,18].
    b.box(0, -0.075, -14, 64, 0.45, 36, 'paving');
    b.box(0, -0.075, 25, 64, 0.45, 14, 'paving');
    b.box(-31, -0.075, 11, 2, 0.45, 14, 'paving');
    b.box(4, -0.075, 11, 56, 0.45, 14, 'paving');
    // Curbs
    for (const [x, z, w, d] of [[0, -32.2, 64.6, 0.4], [0, 32.2, 64.6, 0.4], [-32.2, 0, 0.4, 64.6], [32.2, 0, 0.4, 64.6]] as [number, number, number, number][]) {
      b.box(x, 0.0, z, w, 0.36, d, 'curb', { collide: false });
    }
    // Sidewalks outside the ring road
    b.box(0, 0.05, -47, 96, 0.2, 6, 'concrete_wet');
    b.box(-47, 0.05, 0, 6, 0.2, 100, 'concrete_wet');
    b.box(47, 0.05, 0, 6, 0.2, 100, 'concrete_wet');
    // Market street sidewalks and market square
    b.box(-15, 0.05, 57, 6, 0.2, 26, 'concrete_wet');
    b.box(15, 0.05, 57, 6, 0.2, 26, 'concrete_wet');
    b.box(0, 0.06, 91, 60, 0.2, 42, 'concrete_wet');
    // Lane markings (subtle)
    for (let z = -28; z <= 28; z += 6) {
      b.box(38, 0.005, z, 0.15, 0.01, 2.5, 'emit_amber', { collide: false, shadow: false });
      b.box(-38, 0.005, z, 0.15, 0.01, 2.5, 'emit_amber', { collide: false, shadow: false });
    }
    await ctx.progress(0.2, 'Streets');

    // ---------------------------------------------------------------- Monument
    this.buildMonument(b);
    await ctx.progress(0.3, 'Aether Monument');

    // ---------------------------------------------------------------- Metro stairwell (west)
    this.buildStairwell(b);

    // ---------------------------------------------------------------- Buildings
    const r = rng(9);
    const blocks: [number, number, number, number, number][] = [
      // x, z, w, d, h  (north row; gate gap at x[-12,12])
      [-58, -60, 24, 22, 26], [-34, -60, 20, 22, 18], [-20, -62, 12, 18, 12], [20, -62, 12, 18, 14], [34, -60, 20, 22, 22], [58, -60, 24, 22, 30],
      // west column
      [-60, -32, 22, 18, 20], [-62, -10, 22, 22, 15], [-60, 14, 22, 22, 24], [-62, 36, 22, 18, 17],
      // east column (behind elevated rail)
      [66, -34, 20, 20, 28], [66, -8, 20, 24, 18], [66, 18, 20, 22, 24], [66, 40, 20, 18, 16],
      // market street
      [-30, 52, 24, 16, 16], [30, 52, 24, 16, 20], [-30, 66, 24, 10, 12], [30, 66, 24, 10, 14],
      // market enclosure
      [-44, 82, 26, 22, 14], [-44, 104, 26, 20, 18], [44, 80, 26, 20, 16], [44, 102, 26, 22, 22], [0, 126, 64, 22, 20],
    ];
    blocks.forEach(([x, z, w, d, h], i) => {
      const faces: ('n' | 's' | 'e' | 'w')[] = [];
      if (z < -40) faces.push('s');
      if (x < -40 && z > -45 && z < 60) faces.push('e');
      if (x > 40 && z > -45 && z < 60) faces.push('w');
      if (z > 40 && z < 75 && x < 0) faces.push('e');
      if (z > 40 && z < 75 && x > 0) faces.push('w');
      if (z >= 75 && x < -20) faces.push('e');
      if (z >= 75 && x > 20) faces.push('w');
      if (z > 115) faces.push('n');
      P.building(b, x, z, w, d, h, 100 + i, { lit: 0.05 + r.next() * 0.06, broken: true, faces: faces.length ? faces : ['s'] });
    });
    await ctx.progress(0.45, 'Civic district');

    // ---------------------------------------------------------------- Facility gate (north)
    this.buildGate(b, ctx.flag('facility_gate_open'));
    // Distant facility tower for the skyline
    b.box(0, 22, -86, 30, 44, 22, 'panel_lab', { collide: false });
    for (let i = 0; i < 6; i++) b.box(0, 6 + i * 6.5, -74.9, 26, 0.3, 0.1, 'emit_cyan', { collide: false, shadow: false });
    b.box(0, 46, -86, 8, 4, 8, 'metal_dark', { collide: false });
    P.antenna(b, 0, 48, -86, 10);

    // ---------------------------------------------------------------- Elevated rail (east)
    for (let z = -70; z <= 70; z += 14) {
      b.box(52, 4, z, 1.2, 8, 1.2, 'concrete_dark');
    }
    b.box(52, 8.6, 0, 5, 1.2, 150, 'concrete_dark', { collide: false });
    b.box(50.8, 9.3, 0, 0.2, 0.25, 150, 'metal', { collide: false });
    b.box(53.2, 9.3, 0, 0.2, 0.25, 150, 'metal', { collide: false });
    // Derailed tram hanging off the track
    P.bus(b, 45.5, 20, 0.4 + Math.PI / 2, 77);
    b.box(46, 0.5, 21.5, 2, 1, 3, 'concrete', { rotY: 0.3 });
    P.debris(b, 44, 22, 3, 8, 78);
    await ctx.progress(0.55, 'Transit line');

    // ---------------------------------------------------------------- Streets dressing
    const cars: [number, number, number][] = [[-38, -20, 0.1], [-39, 18, Math.PI + 0.3], [38, -24, Math.PI - 0.15], [37, 26, 0.6], [-18, -38, Math.PI / 2 + 0.2], [16, 38, -Math.PI / 2], [-5, 40, Math.PI / 2 + 0.5], [6, 60, 0.15], [-7, 66, Math.PI]];
    cars.forEach(([x, z, y], i) => P.car(b, x, z, y, 300 + i));
    P.bus(b, 39, -6, 0.05 + Math.PI / 2, 401);
    for (const [x, z, y] of [[-34, -34, 0.8], [-33, -30, 0.4], [34, 34, 2.4], [30, -40, 0.2], [-10, 44, 0.1], [10, 44, -0.1], [-26, 34, 1.4]] as [number, number, number][]) P.barrier(b, x, z, y);
    for (const [x, z] of [[-26, -26], [26, 26], [-22, 28], [36, 12], [-36, -6], [8, -38], [-4, 52], [12, 74], [-22, 106]] as [number, number][]) P.debris(b, x, z, 2.2, 7, x * 31 + z);
    for (const [x, z, y] of [[-12, -18, 0.3], [14, 16, 1.6], [-16, 18, -0.9], [-24, -10, 1.0]] as [number, number, number][]) P.bench(b, x, z, y);
    for (const [x, z, t] of [[-14, -20, false], [16, 18, true], [28, 10, false], [-20, 24, true]] as [number, number, boolean][]) P.trashBin(b, x, z, t);
    // Planters with dead trees around the square
    for (const [x, z] of [[-20, -20], [20, 20], [-20, 20], [24, -4], [-24, -4]] as [number, number][]) this.planter(b, x, z);

    // Street lights (some dead, a few flickering)
    const lamps: [number, number, number, boolean, boolean][] = [
      [-30, -30, Math.PI / 4, true, false], [30, 30, -3 * Math.PI / 4, true, true], [-30, 30, 3 * Math.PI / 4, false, false],
      [-30, -6, Math.PI / 2, true, false], [30, -10, -Math.PI / 2, true, false], [0, -30, 0, true, true],
      [-13, 50, Math.PI / 2, true, false], [13, 62, -Math.PI / 2, true, true], [-20, 86, Math.PI / 2, true, false], [22, 100, -Math.PI / 2, false, false], [0, 108, Math.PI, true, false],
    ];
    for (const [x, z, y, on, flick] of lamps) {
      const l = P.streetLight(b, x, z, y, { on, light: on && Math.abs(x) < 40, intensity: 0.9 });
      if (flick && l.light) this.flickers.push({ light: l.light, mesh: l.halo ?? undefined, base: l.light.intensity, seed: x * 3 + z });
    }

    // Signage
    P.sign(b, -27, 3.4, 3.6, 5.5, 1.1, Math.PI, ['TRANSIT  LINE B  ↓'], { bg: '#0a1a24', fg: '#7fe0ff', glow: 1.4, border: '#2d6f88' });
    P.sign(b, 0, 9.5, -45.6, 14, 1.6, 0, ['AETHER RESEARCH DIVISION'], { bg: '#0c141a', fg: '#9fd8ee', glow: 1.1 });
    P.sign(b, -18.2, 6, 44.5, 6, 1.4, Math.PI / 2, ['MARKET STREET'], { bg: '#1a120a', fg: '#ffb46a', glow: 1.6, border: '#7a4a1e' });
    P.sign(b, 18.4, 8, 60, 5, 2.2, -Math.PI / 2, ['NOODLES', '24H'], { bg: '#200a12', fg: '#ff7a8a', glow: 1.8 });
    P.sign(b, -18.4, 7, 64, 4.6, 1.8, Math.PI / 2, ['REPAIRS'], { bg: '#08161a', fg: '#7fffd0', glow: 1.3 });
    P.sign(b, 44.5, 9, -20, 7, 1.6, -Math.PI / 2, ['CIVIC CENTER'], { bg: '#0b1016', fg: '#c8d8ea', glow: 0.9 });
    await ctx.progress(0.65, 'Abandoned streets');

    // ---------------------------------------------------------------- Survivors' camp (NE)
    this.buildCamp(b);

    // ---------------------------------------------------------------- Market
    this.buildMarket(b);
    await ctx.progress(0.75, 'Collapsed Market');

    // ---------------------------------------------------------------- Bounds
    b.wall(0, 3, -48.5, 120, 8, 1);
    b.wall(0, 3, 115, 120, 8, 1);
    b.wall(-48.5, 3, 30, 1, 8, 170);
    b.wall(48.5, 3, 30, 1, 8, 170);
    // Market street side blocks (between the street buildings and the ring road)
    b.wall(-18.5, 3, 56, 1, 8, 26);
    b.wall(18.5, 3, 56, 1, 8, 26);
    b.wall(-31, 3, 71.5, 26, 8, 1);
    b.wall(31, 3, 71.5, 26, 8, 1);
    b.wall(-31, 3, 44.5, 26, 8, 1);
    b.wall(31, 3, 44.5, 26, 8, 1);

    b.finalize();

    // ---------------------------------------------------------------- Weather
    this.weather = new Weather({ rain: this.dawn ? 0 : 1, wind: new THREE.Vector2(2.5, 1), lightning: !this.dawn, lightningInterval: [14, 32], splashHeight: 0.17 }, ctx.quality.effects);
    if (this.dawn) {
      this.grade = { exposure: 1.15, contrast: 1.05, saturation: 1.05, lift: [0.02, 0.01, 0.0], gain: [1.05, 1.0, 0.95], bloomThreshold: 0.92 };
      this.ambience = 'none';
      this.music = 'ending';
    }
    this.weather.skyMat = sky.material as THREE.ShaderMaterial;
    this.weather.flashLights.push({ light: hemi, base: hemi.intensity, boost: 4 }, { light: moon, base: moon.intensity, boost: 3 });
    S.add(this.weather.group);
    await ctx.progress(0.85, 'Weather');

    this.layoutGameplay();
    this.map = {
      min: new THREE.Vector2(-50, -52),
      max: new THREE.Vector2(50, 116),
      shapes: [
        { kind: 'road', x: 0, z: 0, w: 92, d: 92 },
        { kind: 'floor', x: 0, z: 0, w: 64, d: 64 },
        { kind: 'road', x: 0, z: 56, w: 24, d: 26 },
        { kind: 'floor', x: 0, z: 91, w: 60, d: 42 },
        { kind: 'block', x: -27, z: 11, w: 6, d: 14 },
        { kind: 'water', x: 0, z: 0, w: 14, d: 14 },
      ],
      labels: [
        { text: 'MONUMENT', x: 0, z: 0 }, { text: 'CAMP', x: 22, z: -22 }, { text: 'METRO', x: -27, z: 11 },
        { text: 'FACILITY GATE', x: 0, z: -46 }, { text: 'MARKET', x: 0, z: 92 }, { text: 'LADDER', x: 28, z: 92 },
      ],
    };
  }

  private planter(b: LevelBuilder, x: number, z: number) {
    b.box(x, 0.45, z, 2.4, 0.9, 2.4, 'concrete_dark');
    b.box(x, 0.88, z, 2.1, 0.08, 2.1, 'rock', { collide: false });
    b.cyl(x, 2.4, z, 0.08, 0.14, 3.2, 'wood', 6, { collide: false });
    const r = rng(x * 7 + z);
    for (let i = 0; i < 4; i++) b.cyl(x + r.range(-0.4, 0.4), 3.4 + r.range(0, 0.8), z + r.range(-0.4, 0.4), 0.02, 0.05, 1.4, 'wood', 4, { collide: false, rotX: r.range(-0.8, 0.8), rotZ: r.range(-0.8, 0.8), shadow: false });
  }

  private buildMonument(b: LevelBuilder) {
    // Stepped base with a fountain basin.
    b.cyl(0, 0.3, 0, 7.4, 7.6, 0.3, 'concrete', 40);
    b.cyl(0, 0.6, 0, 6.4, 6.6, 0.3, 'concrete', 40);
    b.cyl(0, 0.7, 0, 5.4, 5.4, 0.12, 'concrete_dark', 40, { collide: false });
    const water = new THREE.Mesh(new THREE.CircleGeometry(5.2, 40).rotateX(-Math.PI / 2), getMaterial('water'));
    water.position.set(0, 0.78, 0);
    b.object(water, false);
    b.cyl(0, 1.1, 0, 2.2, 2.6, 0.8, 'concrete', 24);
    // Central obelisk, broken in two around the exposed core.
    b.cyl(0, 3.9, 0, 0.8, 1.3, 5.0, 'metal_dark', 6, { rotY: Math.PI / 6 });
    b.cyl(0, 6.55, 0, 0.35, 0.8, 0.5, 'metal', 6, { rotY: Math.PI / 6, collide: false });
    b.cyl(0.2, 10.4, 0.1, 0.25, 0.7, 3.6, 'metal_dark', 6, { rotY: Math.PI / 6 + 0.1, rotZ: 0.07, collide: false });
    b.cyl(0.05, 8.45, 0.03, 0.62, 0.3, 0.5, 'metal', 6, { rotY: Math.PI / 6 + 0.1, rotZ: 0.07, collide: false });
    // Glowing seams on the lower shaft
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2 + Math.PI / 6;
      b.box(Math.cos(a) * 0.98, 3.9, Math.sin(a) * 0.98, 0.05, 4.4, 0.05, 'emit_cyan', { collide: false, shadow: false, rotZ: Math.cos(a) * 0.04 });
    }
    // Core sphere floating in the break
    const core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.9, 3), getMaterial('aether'));
    core.position.set(0, 7.45, 0);
    this.monumentCore = core;
    b.object(core, false);
    const inner = new THREE.Mesh(new THREE.IcosahedronGeometry(0.42, 2), getMaterial('emit_cyan'));
    inner.position.copy(core.position);
    b.object(inner, false);
    // Broken halo rings
    for (const [h, rad, tilt, arc] of [[7.45, 2.9, 0.25, 1.65], [9.3, 2.2, -0.35, 1.8]] as [number, number, number, number][]) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(rad, 0.12, 8, 64, Math.PI * arc), getMaterial('metal'));
      ring.position.set(0, h, 0);
      ring.rotation.set(Math.PI / 2 + tilt, 0, 0);
      b.object(ring);
      const glowRing = new THREE.Mesh(new THREE.TorusGeometry(rad, 0.025, 6, 64, Math.PI * arc * 0.9), getMaterial('emit_cyan'));
      ring.add(glowRing);
      glowRing.position.z = 0.1;
      this.monumentRings.push(ring);
    }
    // Fallen ring segment on the base
    const fallen = new THREE.Mesh(new THREE.TorusGeometry(2.8, 0.14, 8, 32, 1.1), getMaterial('metal'));
    fallen.position.set(3.4, 1.1, 2.4);
    fallen.rotation.set(0.2, 0.6, 0.1);
    b.object(fallen);
    b.solidCollider(3.6, 1.2, 2.6, 2.4, 0.6, 1.2, 0.6);
    this.monumentLight = b.pointLight(0, 7.45, 0, 0x5fd8ff, 600, 45, 1.5);
    b.glowDecal(0, 0.8, 0, 9, 0x5fd8ff, 0.45);
    // Plaque
    P.sign(b, 0, 1.25, 2.62, 2.4, 0.5, 0, ['AETHER-9  ·  WE LISTEN TO THE DEEP'], { bg: '#121a1e', fg: '#9fc8d8' });
    this.markers.monument_drop = new THREE.Vector3(3.5, 0.2, 9);
  }

  private buildStairwell(b: LevelBuilder) {
    // Hole x[-30,-24] z[4,18]; stairs descend southwards to y=-4.2, landing z[15.2,18].
    const depth = 4.2, steps = 14, run = 0.8;
    for (let i = 0; i < steps; i++) {
      const top = -(i + 1) * (depth / steps);
      b.box(-27, top - 0.15 + 0.15, 4 + run * (i + 0.5), 6, 0.3, run, 'concrete_dark', { collide: false });
    }
    // Smooth ramp collider for the stairs.
    const ang = Math.atan2(depth, steps * run);
    b.physics.addBoxQ(new THREE.Vector3(-27, -depth / 2 - 0.12, 4 + (steps * run) / 2), new THREE.Vector3(3, 0.1, Math.hypot(depth, steps * run) / 2), new THREE.Quaternion().setFromEuler(new THREE.Euler(ang, 0, 0)));
    b.box(-27, -depth - 0.15, 16.6, 6, 0.3, 3.2, 'concrete_dark');
    // Walls of the well
    b.box(-30.15, -2.1, 11, 0.3, 4.5, 14.4, 'concrete');
    b.box(-23.85, -2.1, 11, 0.3, 4.5, 14.4, 'concrete');
    b.box(-27, -2.1, 18.15, 6.6, 4.5, 0.3, 'concrete');
    b.box(-27, -2.1, 3.85, 6.6, 4.5, 0.3, 'concrete', { collide: false });
    // Tunnel doorway at the bottom
    b.box(-27, -2.6, 17.95, 3.2, 3.0, 0.1, 'black', { collide: false });
    for (const x of [-28.75, -25.25]) b.box(x, -2.7, 17.9, 0.3, 3.0, 0.4, 'metal_dark', { collide: false });
    b.box(-27, -1.05, 17.9, 3.8, 0.3, 0.4, 'metal_dark', { collide: false });
    b.box(-27, -1.22, 17.9, 3.2, 0.05, 0.42, 'emit_cyan', { collide: false });
    b.glowDecal(-27, -4.15, 16.5, 4, 0x5fd8ff, 0.5);
    // Canopy and railings
    for (const x of [-30.2, -23.8]) for (const z of [4, 18]) b.cyl(x, 1.8, z, 0.08, 0.08, 3.6, 'metal_dark', 6, { collide: false });
    b.box(-27, 3.65, 11, 7, 0.08, 15, 'glass', { collide: false });
    b.box(-27, 3.6, 11, 7.2, 0.15, 0.2, 'metal_dark', { collide: false });
    P.railing(b, -30.1, 4, -30.1, 18, 0.15);
    P.railing(b, -23.9, 4, -23.9, 18, 0.15);
    P.railing(b, -30.1, 18.1, -23.9, 18.1, 0.15);
    b.pointLight(-27, -2.2, 16, 0x8fd8ff, 80, 12, 1.6);
  }

  private buildGate(b: LevelBuilder, open: boolean) {
    // Gate wall with a sliding door segment.
    b.box(-13, 5, -46, 2, 10, 2, 'metal_dark');
    b.box(13, 5, -46, 2, 10, 2, 'metal_dark');
    b.box(0, 9.5, -46, 28, 1, 2, 'metal_dark', { collide: false });
    for (const x of [-10, 10]) b.box(x, 9.0, -44.9, 0.4, 0.2, 0.2, 'emit_red', { collide: false });
    const door = new THREE.Group();
    const left = new THREE.Mesh(new THREE.BoxGeometry(12, 8.6, 0.6), getMaterial('metal_painted'));
    left.position.set(-6, 4.3, 0);
    const right = left.clone();
    right.position.x = 6;
    const stripe = new THREE.Mesh(new THREE.BoxGeometry(24, 0.3, 0.62), getMaterial('metal_yellow'));
    stripe.position.y = 1.2;
    door.add(left, right, stripe);
    door.position.set(0, 0, -46);
    b.object(door);
    this.gate = door;
    this.gateOpen = open;
    if (open) {
      left.position.x = -16;
      right.position.x = 16;
      stripe.visible = false;
    } else {
      this.gateCollider = b.physics.addBox(0, 4.3, -46, 12, 4.3, 0.4);
    }
  }

  private buildCamp(b: LevelBuilder) {
    const cx = 22, cz = -22;
    P.tarpShelter(b, cx + 4, cz - 4, 0.3, 5, 4, 'tarp');
    P.tarpShelter(b, cx - 3, cz - 6, -0.2, 4, 3.5, 'tarp_blue');
    P.tarpShelter(b, cx + 6, cz + 3, 1.2, 4, 3, 'tarp');
    for (let i = 0; i < 5; i++) P.crateStack(b, cx - 6 + (i % 3) * 2.2, cz + 5 + Math.floor(i / 3) * 2, i * 0.4, 500 + i);
    // Generator
    b.box(cx - 7, 0.75, cz - 1, 2.2, 1.2, 1.4, 'metal_yellow');
    b.box(cx - 7, 1.45, cz - 1, 1.4, 0.2, 0.9, 'metal_dark', { collide: false });
    b.box(cx - 5.88, 0.85, cz - 1, 0.04, 0.3, 0.6, 'emit_green', { collide: false });
    // Fire barrel
    b.cyl(cx, 0.6, cz, 0.38, 0.38, 1.0, 'rust', 12);
    this.fireLight = b.pointLight(cx, 1.8, cz, 0xff8a3a, 160, 16, 1.6);
    b.glowDecal(cx, 0.17, cz, 6, 0xff8a3a, 0.4);
    this.markers.fire = new THREE.Vector3(cx, 1.15, cz);
    // Radio table (Mira)
    b.box(cx + 4.5, 0.8, cz - 2.6, 2.2, 0.08, 1.0, 'wood');
    for (const lx of [-1, 1]) b.box(cx + 4.5 + lx, 0.4, cz - 2.6, 0.08, 0.8, 0.9, 'metal_dark', { collide: false });
    b.box(cx + 4.2, 1.05, cz - 2.7, 0.7, 0.4, 0.4, 'metal_dark', { collide: false });
    b.box(cx + 4.2, 1.06, cz - 2.49, 0.5, 0.2, 0.02, 'screen', { collide: false });
    P.antenna(b, cx + 6, 0.15, cz - 3.4, 6);
    // Sleeping mats and a lantern
    for (let i = 0; i < 3; i++) b.box(cx + 3 + i * 1.2, 0.2, cz - 6, 0.9, 0.06, 2, 'tarp_blue', { collide: false, shadow: false });
    b.glowSprite(cx + 3.5, 2.0, cz - 5, 0.8, 0xffb46a, 1.2);
    // Save terminal
    const scr = P.terminal(b, cx - 8.5, cz + 2.5, Math.PI / 2 + 0.3);
    this.markers.save_screen = scr;
    // Barricade around the camp
    for (const [x, z, y] of [[cx - 10, cz - 8, 0.4], [cx + 9, cz + 8, -0.7], [cx - 10, cz + 8, 2.2]] as [number, number, number][]) P.barrier(b, x, z, y, 'concrete_dark');
  }

  private buildMarket(b: LevelBuilder) {
    // Stalls in rows; some collapsed.
    const r = rng(77);
    const rows: [number, number, number][] = [];
    for (let z = 78; z <= 104; z += 7) for (const x of [-20, -10, 10, 20]) rows.push([x + r.range(-1, 1), z + r.range(-1, 1), (x < 0 ? Math.PI / 2 : -Math.PI / 2) + r.range(-0.2, 0.2)]);
    rows.forEach(([x, z, y], i) => {
      if (i % 5 === 3) {
        // Collapsed stall
        b.box(x, 0.35, z, 2.6, 0.7, 0.9, 'metal_painted', { rotY: y, rotZ: 0.4 });
        b.box(x + 0.6, 0.08, z, 3, 0.04, 1.6, 'tarp', { rotY: y + 0.3, collide: false, shadow: false });
      } else P.stall(b, x, z, y, 600 + i, i % 2 ? 'tarp' : 'tarp_blue');
    });
    // Storefronts on the enclosure buildings (lit shop windows, shutters)
    for (const z of [76, 86, 96, 106]) {
      b.box(-30.9, 1.6, z, 0.2, 3.2, 6, z % 20 === 16 ? 'emit_warm' : 'glass_dark', { collide: false });
      b.box(-30.7, 3.4, z, 0.6, 0.3, 6.4, 'metal_dark', { collide: false });
      b.box(30.9, 1.6, z, 0.2, 3.2, 6, z % 20 === 6 ? 'emit_cyan' : 'glass_dark', { collide: false });
      b.box(30.7, 3.4, z, 0.6, 0.3, 6.4, 'metal_dark', { collide: false });
    }
    // Shutters half down
    b.box(-30.75, 2.4, 96, 0.08, 1.6, 6, 'metal', { collide: false });
    // Maintenance robots (deactivated)
    for (const [x, z, y] of [[4, 82, 0.5], [-4, 100, 2.2]] as [number, number, number][]) this.deadRobot(b, x, z, y);
    // Fire escape + ladder on the east building (rooftop access)
    b.box(30.6, 4.5, 92, 1.2, 0.12, 4, 'grate', { collide: false });
    b.box(30.6, 8.5, 92, 1.2, 0.12, 4, 'grate', { collide: false });
    for (let y = 0.3; y < 12; y += 0.35) b.box(30.15, y, 91, 0.05, 0.04, 0.6, 'metal_yellow', { collide: false, shadow: false });
    b.box(30.15, 6, 90.7, 0.05, 12, 0.05, 'metal_dark', { collide: false });
    b.box(30.15, 6, 91.3, 0.05, 12, 0.05, 'metal_dark', { collide: false });
    b.box(30.2, 0.5, 91, 0.02, 1, 0.8, 'emit_amber', { collide: false, shadow: false });
    // Hanging cables and lanterns
    for (let i = 0; i < 6; i++) {
      const z = 78 + i * 5;
      P.pipe(b, -28, 6, z, 28, 5.5, z + 1, 0.02, 'cable');
      b.glowSprite(-10 + i * 4, 5.6, z + 0.5, 0.5, i % 2 ? 0xff7a5a : 0xffd27a, 1.4);
    }
    b.pointLight(0, 4.5, 88, 0xffb46a, 160, 22, 1.6);
    b.pointLight(-18, 3.5, 102, 0x7fffd0, 90, 14, 1.6);
    P.debris(b, 16, 108, 2.5, 9, 911, 'concrete_dark');
  }

  private deadRobot(b: LevelBuilder, x: number, z: number, yaw: number) {
    b.geo(new THREE.CapsuleGeometry(0.45, 0.7, 4, 10), 'metal_yellow', new THREE.Matrix4().compose(new THREE.Vector3(x, 0.5, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(0, yaw, Math.PI / 2 - 0.2)), new THREE.Vector3(1, 1, 1)), { colliderBox: new THREE.Box3(new THREE.Vector3(-0.5, -0.5, -0.5), new THREE.Vector3(0.5, 0.5, 0.5)) });
    b.box(x + 0.7, 0.25, z + 0.2, 0.4, 0.4, 0.4, 'metal_dark', { rotY: yaw, collide: false });
    b.cyl(x - 0.3, 0.2, z + 0.6, 0.05, 0.05, 0.8, 'metal_dark', 6, { rotX: 1.3, collide: false });
  }

  /** Gameplay object placement: spawns, exits, triggers, interactables, encounters, collectibles, NPCs. */
  private layoutGameplay() {
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    this.spawns = {
      start: { pos: v(-7, 0.16, 12), yaw: Math.PI },
      from_metro: { pos: v(-27, 0.16, 1.5), yaw: Math.PI },
      from_facility: { pos: v(0, 0.06, -41), yaw: 0 },
      from_rooftops: { pos: v(28.6, 0.16, 91), yaw: -Math.PI / 2 },
      camp: { pos: v(16, 0.16, -16), yaw: Math.PI * 0.75 },
    };
    this.markers.partner_wait = v(19.5, 0.16, -18.5);
    this.exits.push(
      { id: 'x_plaza_metro', target: 'metro', entry: 'from_plaza', pos: v(-27, -4.0, 17.2), radius: 1.8, prompt: 'Enter the Metro', auto: true, requires: () => this.flagFn('metro_open'), lockedText: 'Find the survivors first.' },
      { id: 'x_plaza_facility', target: 'facility', entry: 'from_plaza', pos: v(0, 0.06, -44.4), radius: 3, prompt: 'Enter the Research Facility', requires: () => this.flagFn('facility_gate_open'), lockedText: 'The facility gate is sealed from the inside.' },
      { id: 'x_plaza_rooftops', target: 'rooftops', entry: 'from_market', pos: v(29.6, 0.16, 91), radius: 1.6, prompt: 'Climb to the rooftops', requires: () => this.flagFn('swap_unlocked'), lockedText: 'Check in at the survivors\' camp first.' },
    );
    this.triggers.push(
      { id: 't_plaza_camp', box: new THREE.Box3(v(12, -1, -30), v(30, 4, -12)) },
      { id: 't_market', box: new THREE.Box3(v(-30, -1, 72), v(30, 6, 112)) },
      { id: 't_plaza_monument', box: new THREE.Box3(v(-9, -1, -9), v(9, 6, 9)) },
    );
    this.encounters.push(
      { id: 'e_plaza_drones', spawn: 'quest', waves: [[{ type: 'drone', pos: v(-9, 6, -22) }, { type: 'drone', pos: v(0, 7.5, -26) }, { type: 'drone', pos: v(9, 6, -22) }]], arena: { center: v(0, 0, 0), radius: 34 } },
      { id: 'e_market_patrol', spawn: 'trigger:t_market', waves: [[{ type: 'sentinel', pos: v(-5, 0.2, 86) }, { type: 'sentinel', pos: v(7, 0.2, 99) }, { type: 'drone', pos: v(0, 6, 94) }]], arena: { center: v(0, 0, 92), radius: 30 } },
    );
    this.collectibles.push(
      { id: 'c_frag_01', pos: v(39.4, 3.3, -6) },
      { id: 'c_frag_02', pos: v(-40, 0.8, -32) },
      { id: 'c_frag_03', pos: v(0.4, 1.9, -2.7) },
      { id: 'c_frag_04', pos: v(20, 1.5, 82) },
      { id: 'c_frag_05', pos: v(-27, 0.8, 110) },
      { id: 'c_rec_01', pos: v(12.6, 0.9, -27.8) },
      { id: 'c_rec_02', pos: v(10.3, 1.4, 96) },
      { id: 'c_cache_01', pos: v(27.5, 0.6, 74) },
    );
    this.npcs.push(
      { id: 'oren', pos: v(19, 0.16, -15.5), yaw: Math.PI * 1.1, behaviour: 'npc_crossed', dialogue: 'dlg_oren' },
      { id: 'mira', pos: v(26.5, 0.16, -23.6), yaw: Math.PI * 0.5, behaviour: 'npc_work', dialogue: 'dlg_mira' },
      { id: 'tomas', pos: v(-9, 0.22, 90), yaw: Math.PI * 0.4, behaviour: 'npc_hips', dialogue: 'dlg_tomas' },
      { id: 'nia', pos: v(-8.6, 0.16, -5), yaw: Math.PI * 0.3, behaviour: 'wander', dialogue: 'dlg_nia', echoOnly: true, route: [v(-8.6, 0.16, -5), v(-9, 0.16, 4), v(-3, 0.16, 8.5), v(4, 0.16, 8.5), v(8.6, 0.16, 2), v(6, 0.16, -7), v(-2, 0.16, -9)] },
    );
    this.markers.bolt = v(14.5, 0.16, -26.5);
    this.npcs.push({ id: 'bolt', pos: this.markers.bolt.clone(), yaw: Math.PI * 0.8, behaviour: 'idle', dialogue: 'dlg_bolt' });
    // Interactables
    this.questPoint('i_monument', v(0, 1.3, 6.4), 'Inspect the Aether Monument', ['stage:m1_awakening:monument'], { radius: 3.4 });
    this.questPoint('i_bolt', v(14.5, 1.0, -25.2), 'Repair BOLT', ['stage:sq_broken_guardian:repair'], { radius: 2.4 });
    this.addInteractable({ id: 'i_save_plaza', kind: 'save', pos: this.markers.save_screen.clone(), radius: 2.2, prompt: 'Use save terminal', onInteract: () => undefined });
    // Quest item pickups
    this.itemPickups.push({ id: 'i_market_cell', item: 'q_power_cell_bolt', pos: v(-19.6, 1.15, 92.2), cond: ['quest:sq_broken_guardian:active'] });
  }

  private flagFn: (name: string) => boolean = () => false;

  bindRuntime(rt: ZoneRuntime) {
    super.bindRuntime(rt);
    this.rt = rt;
    this.flagFn = (n) => rt.flag(n);
  }

  update(dt: number, rt: ZoneRuntime) {
    super.update(dt, rt);
    const t = this.time;
    if (this.monumentCore) {
      const pulse = 1 + Math.sin(t * 2.2) * 0.06 + (rt.flag('swap_unlocked') ? 0 : Math.max(0, Math.sin(t * 6)) * 0.04);
      this.monumentCore.scale.setScalar(pulse);
      this.monumentCore.rotation.y += dt * 0.3;
    }
    this.monumentRings.forEach((r, i) => (r.rotation.z += dt * (i ? -0.08 : 0.05)));
    if (this.monumentLight) this.monumentLight.intensity = 560 + Math.sin(t * 2.2) * 80;
    if (this.fireLight) this.fireLight.intensity = 150 + Math.sin(t * 13) * 20 + Math.sin(t * 7.3) * 25;
    for (const f of this.flickers) {
      const on = Math.sin(t * 1.3 + f.seed) > -0.6 || Math.sin(t * 37 + f.seed) > 0.4;
      if (f.light) f.light.intensity = on ? f.base : f.base * 0.05;
      if (f.mesh) f.mesh.visible = on;
    }
    // Gate animation when the flag flips during play.
    if (!this.gateOpen && rt.flag('facility_gate_open')) {
      this.gateOpen = true;
      if (this.gateCollider) {
        this.builder.physics.removeCollider(this.gateCollider);
        this.gateCollider = null;
      }
    }
    if (this.gateOpen && this.gate) {
      const [l, r] = this.gate.children;
      l.position.x += (-16 - l.position.x) * Math.min(1, dt * 0.8);
      r.position.x += (16 - r.position.x) * Math.min(1, dt * 0.8);
    }
  }
}
