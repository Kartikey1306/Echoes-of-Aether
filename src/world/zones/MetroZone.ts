import * as THREE from 'three';
import type RAPIER from '@dimforge/rapier3d-compat';
import { bakeEnvironment } from '../../render/Environment';
import { getMaterial, type MatName } from '../../render/Materials';
import { LevelBuilder } from '../kit/LevelBuilder';
import * as P from '../kit/Props';
import { Zone, type BuildContext, type ZoneRuntime } from '../Zone';

// Abandoned Metro (Line B). Platform level y=0; concourse and entry corridor at y=4.
// Concourse x[-18,18] z[12,36]; stairs x[-4,4] z[32,42] down to the platform hall x[-44,44] z[42,58].
// Power room x[28,40] z[34,42] (junction puzzle); signal room x[-40,-28] z[34,42] (transmitter);
// maintenance bay x[-26,-20] z[37,42]; spur tunnel east along the track pit to x=70.

const JUNCTION_TARGET = [3, 0, 2]; // elbow orientations that complete the circuit
const JUNCTION_START = [0, 2, 1];

export class MetroZone extends Zone {
  private junctions: { group: THREE.Group; piece: THREE.Group; state: number; mat: THREE.MeshBasicMaterial }[] = [];
  private conduitMats: THREE.MeshBasicMaterial[] = [];
  private lamps: THREE.Mesh[] = [];
  private emergency: THREE.PointLight[] = [];
  private mainLights: THREE.PointLight[] = [];
  private powered = false;
  private signalDoor!: THREE.Mesh;
  private signalDoorCollider: RAPIER.Collider | null = null;
  private barrier!: THREE.Mesh;
  private barrierCollider: RAPIER.Collider | null = null;
  private barrierOpen = false;
  private waterBox = new THREE.Box3(new THREE.Vector3(8, -2, 52), new THREE.Vector3(44, 0.2, 58));
  private splashT = 0;
  private transmitterGlow!: THREE.Mesh;
  private signalLight: THREE.PointLight | null = null;

  constructor() {
    super('metro');
    this.indoor = true;
    this.killY = -10;
    this.music = 'tension';
    this.ambience = 'metro_drip';
    this.grade = { exposure: 1.35, contrast: 1.1, saturation: 0.9, lift: [0.012, 0.004, 0.0], gain: [1.04, 0.98, 0.95], bloomThreshold: 0.85 };
  }

  async build(ctx: BuildContext) {
    const S = this.scene;
    const b = (this.builder = new LevelBuilder(this.root, ctx.physics));
    b.lightBudget = 13;
    const upRoot = new THREE.Group();
    this.root.add(upRoot);
    const u = new LevelBuilder(upRoot, ctx.physics, new THREE.Vector3(0, 4, 0));
    u.lightBudget = 4;
    S.background = new THREE.Color(0x020304);
    S.fog = new THREE.FogExp2(0x0a0c0e, 0.03);
    S.environment = bakeEnvironment(ctx.rs.renderer, { top: 0x101418, horizon: 0x181c20, bottom: 0x060708 }, [{ dir: new THREE.Vector3(0, 1, 0.3), color: 0xffe0c0, size: 5, intensity: 1 }]);
    S.environmentIntensity = 0.6;
    const hemi = new THREE.HemisphereLight(0x5a6878, 0x1a1612, 0.9);
    S.add(hemi);
    const key = new THREE.DirectionalLight(0x8a9cb4, 0.6);
    key.position.set(20, 30, 10);
    key.castShadow = true;
    S.add(key, key.target);
    this.sun = key;
    await ctx.progress(0.1, 'Tunnels');

    // ---------------------------------------------------------------- Entry corridor (from the plaza stairs) at y=4
    u.box(0, -0.25, 5, 6, 0.5, 14, 'tile_lab');
    u.box(-3.25, 1.8, 5, 0.5, 3.6, 14, 'tile_lab');
    u.box(3.25, 1.8, 5, 0.5, 3.6, 14, 'tile_lab');
    u.box(0, 3.85, 5, 7, 0.5, 14, 'concrete_dark');
    u.box(0, 1.8, -2.25, 7, 3.6, 0.5, 'concrete_dark');
    for (let z = 0; z < 12; z += 4) u.box(0, 3.55, z, 0.2, 0.06, 1.6, 'emit_red', { collide: false });
    P.sign(u, 0, 2.6, 11.7, 3.4, 0.7, Math.PI, ['LINE B  ·  PLATFORM 2'], { bg: '#0c1418', fg: '#9fd8ee', glow: 1.0 });

    // ---------------------------------------------------------------- Concourse (y=4)
    u.box(0, -0.25, 22, 36, 0.5, 20, 'floor_lab');
    u.box(-12, -0.25, 34, 16, 0.5, 4, 'floor_lab');
    u.box(12, -0.25, 34, 16, 0.5, 4, 'floor_lab');
    u.box(0, 6.25, 24, 37, 0.5, 25, 'concrete_dark', { collide: false });
    u.box(-18.25, 3, 24, 0.5, 6.5, 25, 'tile_lab');
    u.box(18.25, 3, 24, 0.5, 6.5, 25, 'tile_lab');
    u.box(-10.5, 3, 11.75, 15, 6.5, 0.5, 'tile_lab');
    u.box(10.5, 3, 11.75, 15, 6.5, 0.5, 'tile_lab');
    u.box(-11, 3, 36.25, 14, 6.5, 0.5, 'tile_lab');
    u.box(11, 3, 36.25, 14, 6.5, 0.5, 'tile_lab');
    u.box(0, 4.9, 36.25, 8, 2.7, 0.5, 'tile_lab');
    for (const x of [-12, -6, 6, 12]) for (const z of [17, 24, 31]) u.box(x, 3, z, 0.9, 6.5, 0.9, 'concrete');
    // Ticket gates
    for (let x = -16; x <= 16; x += 2.4) {
      if (Math.abs(x) < 1.5) continue;
      u.box(x, 0.55, 27, 0.35, 1.1, 1.4, 'metal_dark');
      u.box(x, 1.12, 27, 0.36, 0.04, 1.3, Math.abs(x) % 4.8 < 1 ? 'emit_red' : 'emit_green', { collide: false });
    }
    // Kiosks, benches, debris, collapsed ceiling
    P.terminal(u, -14, 20, Math.PI / 2, false);
    P.terminal(u, 14, 20, -Math.PI / 2, true);
    P.terminal(u, -12, 12.9, 0, true); // save terminal
    P.bench(u, -8, 15, 0);
    P.bench(u, 8, 15, 0);
    P.debris(u, 5, 21, 2.4, 10, 31, 'concrete_dark');
    u.box(4, 1.2, 20, 5, 0.4, 3, 'concrete_dark', { rotZ: 0.35, rotY: 0.4 });
    P.rebar(u, 4, 2, 20, 6, 32);
    P.sign(u, 0, 4.4, 35.9, 5, 1.0, Math.PI, ['PLATFORM 2  ↓'], { bg: '#0c1418', fg: '#9fd8ee', glow: 1.2 });
    P.sign(u, -17.9, 3.5, 22, 6, 1.3, Math.PI / 2, ['AETHER-9 TRANSIT AUTHORITY'], { bg: '#10161c', fg: '#c8d8e8', glow: 0.7 });
    u.pointLight(0, 5.4, 18, 0xff5a40, 60, 18, 1.6);
    u.pointLight(0, 5.4, 30, 0xff5a40, 50, 16, 1.6);
    for (const x of [-9, 0, 9]) for (const z of [16, 24, 32]) this.lamps.push(lampTube(u, x, 5.95, z));
    await ctx.progress(0.3, 'Concourse');

    // ---------------------------------------------------------------- Stairs down to the platform
    b.stairs(0, 0, 42, Math.PI, 8, 10, 0.4, 1.0, 'concrete_dark');
    b.box(-4.25, 2.6, 37, 0.5, 5.2, 10, 'tile_lab');
    b.box(4.25, 2.6, 37, 0.5, 5.2, 10, 'tile_lab');
    P.railing(b, -3.8, 32.5, -3.8, 41.5, 2.0, 1.0, false);

    // ---------------------------------------------------------------- Platform hall (y=0)
    b.box(0, -0.25, 47, 88, 0.5, 10, 'concrete');
    b.box(0, 0.02, 51.7, 88, 0.04, 0.4, 'metal_yellow', { collide: false, shadow: false });
    // Track pit (y=-1.3)
    b.box(0, -1.55, 55, 88, 0.5, 6, 'concrete_dark');
    b.box(0, -0.65, 52.1, 88, 1.3, 0.2, 'concrete_dark');
    for (let x = -43; x < 44; x += 1.2) b.box(x, -1.25, 55, 0.25, 0.1, 3.6, 'wood', { collide: false, shadow: false });
    b.box(0, -1.15, 54.2, 88, 0.15, 0.12, 'rust', { collide: false });
    b.box(0, -1.15, 55.8, 88, 0.15, 0.12, 'rust', { collide: false });
    // Walls & ceiling
    b.box(0, 1.5, 58.25, 90, 6, 0.5, 'tile_lab');
    b.box(0, 4.75, 50, 90, 0.5, 17, 'concrete_dark', { collide: false });
    b.box(-44.25, 1.5, 50, 0.5, 6, 17, 'tile_lab');
    // North wall with openings: stairs x[-4,4], power door x[32.5,35.5], signal door x[-35.5,-32.5], bay x[-26,-20]
    const northSegs: [number, number][] = [[-44, -35.5], [-32.5, -26], [-20, -4], [4, 32.5], [35.5, 44]];
    for (const [a, c] of northSegs) b.box((a + c) / 2, 1.5, 41.75, c - a, 6, 0.5, 'tile_lab');
    b.box(0, 3.75, 41.75, 8, 1.5, 0.5, 'tile_lab');
    for (const [x, w] of [[34, 3], [-34, 3]] as [number, number][]) b.box(x, 3.25, 41.75, w, 2.5, 0.5, 'tile_lab');
    b.box(-23, 3.25, 41.75, 6, 2.5, 0.5, 'tile_lab');
    // Columns along the platform edge
    for (let x = -40; x <= 40; x += 8) b.box(x, 2.2, 45.5, 0.8, 4.4, 0.8, 'concrete');
    // Platform lights (off until power is restored) and emergency lights
    for (let x = -36; x <= 36; x += 12) this.lamps.push(lampTube(b, x, 4.4, 48));
    for (const x of [-30, -6, 18, 38]) {
      const l = b.pointLight(x, 3.6, 47, 0xff4030, 60, 16, 1.6);
      if (l) this.emergency.push(l);
      b.box(x, 4.3, 46.2, 0.4, 0.2, 0.2, 'emit_red', { collide: false });
    }
    // Derailed train on the track
    P.trainCar(b, -22, 55, 0.03, 81, true);
    for (const x of [-28, -16]) b.box(x, -0.5, 55, 2.4, 1.4, 2.2, 'metal_dark', { collide: false });
    P.trainCar(b, -4, 56.2, 0.12, 82, false);
    b.box(-4, -0.4, 55.6, 2.4, 1.6, 2.2, 'metal_dark', { collide: false, rotY: 0.12 });
    // Flooded section of track
    const water = new THREE.Mesh(new THREE.PlaneGeometry(36, 6).rotateX(-Math.PI / 2), getMaterial('water'));
    water.position.set(26, -0.95, 55);
    b.object(water, false);
    // Platform clutter
    P.bench(b, -12, 44, 0);
    P.bench(b, 12, 44, 0);
    P.crateStack(b, 24, 44, 0.2, 90);
    P.crateStack(b, -40, 47, 1.1, 91);
    P.trashBin(b, 8, 43.5, true);
    P.debris(b, 30, 48, 2, 8, 92, 'concrete_dark');
    P.sign(b, 0, 3.2, 58, 6, 1.1, Math.PI, ['LINE B  ·  WESTBOUND'], { bg: '#10161c', fg: '#c8d8e8', glow: 0.8 });
    P.sign(b, 34, 3.0, 41.48, 3.4, 0.6, Math.PI, ['POWER CONTROL'], { bg: '#1a1008', fg: '#ffb46a', glow: 1.2 });
    P.sign(b, -34, 3.0, 41.48, 3.4, 0.6, Math.PI, ['SIGNAL ROOM'], { bg: '#08141a', fg: '#7fe0ff', glow: 1.2 });
    P.sign(b, -23, 3.0, 41.48, 3.6, 0.6, Math.PI, ['MAINTENANCE'], { bg: '#141414', fg: '#d0d0d0', glow: 0.8 });
    await ctx.progress(0.5, 'Platform');

    // ---------------------------------------------------------------- Power room (junction puzzle)
    this.room(b, 28, 40, 34, 42, 'panel_lab');
    b.box(30, 0.8, 35.2, 2.2, 1.6, 1.4, 'metal_yellow');
    b.box(30, 1.62, 35.2, 1.6, 0.04, 1.0, 'emit_amber', { collide: false });
    this.markers.generator = new THREE.Vector3(30, 1, 36.2);
    // Wall-mounted junction board
    b.box(35, 2.2, 34.15, 9, 3.2, 0.1, 'metal_dark', { collide: false });
    const jx = [32.5, 35, 37.5];
    const jy = 1.8;
    for (let i = 0; i < 3; i++) this.junctions.push(this.makeJunction(b, jx[i], jy, 34.25, i));
    // Fixed conduits between junctions (light up as the circuit completes)
    const conduit = (x1: number, y1: number, x2: number, y2: number) => {
      const m = new THREE.MeshBasicMaterial({ color: new THREE.Color(0x401010) });
      const len = Math.hypot(x2 - x1, y2 - y1);
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(len, 0.07, 0.04), m);
      mesh.position.set((x1 + x2) / 2, (y1 + y2) / 2, 34.24);
      mesh.rotation.z = Math.atan2(y2 - y1, x2 - x1);
      b.object(mesh, false);
      this.conduitMats.push(m);
    };
    conduit(31.1, jy, 32.1, jy); // generator -> J1 (left)
    conduit(32.5, jy + 0.4, 32.5, jy + 1.0); // J1 up
    conduit(32.5, jy + 1.0, 35, jy + 1.0); // over
    conduit(35, jy + 1.0, 35, jy + 0.4); // into J2 top
    conduit(35.4, jy, 37.1, jy); // J2 right -> J3 left
    conduit(37.5, jy - 0.4, 37.5, jy - 0.9); // J3 down -> breaker
    b.box(37.5, jy - 1.15, 34.25, 0.5, 0.4, 0.12, 'metal_red', { collide: false });
    P.sign(b, 35, 3.55, 34.22, 4, 0.45, 0, ['ROUTE POWER: GENERATOR → BREAKER'], { bg: '#140c06', fg: '#ffb46a', glow: 1.0 });
    b.pointLight(35, 3, 38, 0xffa060, 40, 10, 1.6);
    // Maintenance bay
    this.room(b, -26, -20, 37, 42, 'concrete_dark');
    P.crateStack(b, -24.5, 38.2, 0.3, 93);
    b.box(-21, 0.9, 38, 1.2, 0.06, 0.8, 'wood');
    // Signal room (locked until powered)
    this.room(b, -40, -28, 34, 42, 'panel_lab');
    const doorMat = getMaterial('metal_painted');
    this.signalDoor = new THREE.Mesh(new THREE.BoxGeometry(3, 3.4, 0.2), doorMat);
    this.signalDoor.position.set(-34, 1.7, 41.8);
    b.object(this.signalDoor);
    this.signalDoorCollider = b.physics.addBox(-34, 1.7, 41.8, 1.5, 1.7, 0.15);
    // Transmitter console
    b.box(-34, 0.6, 35.2, 4, 1.2, 1.2, 'metal_dark');
    b.box(-34, 2.6, 34.4, 3, 2.6, 0.2, 'metal_dark');
    this.transmitterGlow = new THREE.Mesh(new THREE.BoxGeometry(2.6, 1.8, 0.04), new THREE.MeshBasicMaterial({ color: new THREE.Color(0x101820) }));
    this.transmitterGlow.position.set(-34, 2.6, 34.52);
    b.object(this.transmitterGlow, false);
    P.antenna(b, -38.5, 0, 35, 3);
    this.signalLight = b.pointLight(-34, 3.4, 38.5, 0x8fd8ff, 0, 14, 1.6);
    this.markers.transmitter = new THREE.Vector3(-34, 1.4, 36.4);
    await ctx.progress(0.62, 'Control rooms');

    // ---------------------------------------------------------------- Spur tunnel east (to the facility)
    b.box(57, -1.55, 55, 26, 0.5, 6, 'concrete_dark');
    b.box(57, 1.5, 51.75, 26, 6, 0.5, 'concrete_dark');
    b.box(57, 1.5, 58.25, 26, 6, 0.5, 'concrete_dark');
    b.box(57, 3.25, 55, 26, 0.5, 7, 'concrete_dark', { collide: false });
    b.box(70.25, 1.5, 55, 0.5, 6, 7, 'concrete_dark');
    for (let x = 46; x < 70; x += 6) b.box(x, 2.6, 52.1, 0.3, 0.15, 0.2, 'emit_amber', { collide: false });
    // Energy barrier
    const barMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(0xff3a2e).multiplyScalar(1.6), transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
    this.barrier = new THREE.Mesh(new THREE.PlaneGeometry(6, 4), barMat);
    this.barrier.rotation.y = Math.PI / 2;
    this.barrier.position.set(45, 0.7, 55);
    b.object(this.barrier, false);
    if (!ctx.flag('spur_open')) this.barrierCollider = b.physics.addBox(45, 0.7, 55, 0.2, 3, 3);
    else this.openBarrier(true);
    P.sign(b, 46, 2.6, 52.03, 3.2, 0.55, 0, ['SPUR → RESEARCH FACILITY'], { bg: '#08141a', fg: '#7fe0ff', glow: 1.0 });
    // Ramps between platform and track pit (to reach the tunnel)
    b.stairs(41.5, -1.3, 53.6, Math.PI, 2.5, 3, 0.433, 0.6, 'metal_dark');

    // Bounds
    b.wall(0, 3, -3, 10, 10, 1);
    finalizeAll(b, u);
    this.setPowered(ctx.flag('metro_power_on'), true);
    await ctx.progress(0.8, 'Lighting');
    this.layout(ctx);
    this.map = {
      min: new THREE.Vector2(-46, -4),
      max: new THREE.Vector2(72, 60),
      shapes: [
        { kind: 'floor', x: 0, z: 5, w: 6, d: 14 },
        { kind: 'floor', x: 0, z: 24, w: 36, d: 24 },
        { kind: 'road', x: 0, z: 37, w: 8, d: 10 },
        { kind: 'floor', x: 0, z: 47, w: 88, d: 10 },
        { kind: 'road', x: 0, z: 55, w: 88, d: 6 },
        { kind: 'water', x: 26, z: 55, w: 36, d: 6 },
        { kind: 'block', x: 34, z: 38, w: 12, d: 8 },
        { kind: 'block', x: -34, z: 38, w: 12, d: 8 },
        { kind: 'block', x: -23, z: 39.5, w: 6, d: 5 },
        { kind: 'road', x: 57, z: 55, w: 26, d: 6 },
      ],
      labels: [{ text: 'CONCOURSE', x: 0, z: 22 }, { text: 'PLATFORM 2', x: 0, z: 47 }, { text: 'POWER', x: 34, z: 38 }, { text: 'SIGNAL', x: -34, z: 38 }, { text: 'SPUR', x: 58, z: 55 }],
    };
  }

  private room(b: LevelBuilder, x0: number, x1: number, z0: number, z1: number, mat: MatName) {
    b.box((x0 + x1) / 2, -0.25, (z0 + z1) / 2, x1 - x0, 0.5, z1 - z0, 'floor_lab');
    b.box((x0 + x1) / 2, 4.25, (z0 + z1) / 2, x1 - x0, 0.5, z1 - z0, 'concrete_dark', { collide: false });
    b.box(x0 - 0.25, 2, (z0 + z1) / 2, 0.5, 4.5, z1 - z0, mat);
    b.box(x1 + 0.25, 2, (z0 + z1) / 2, 0.5, 4.5, z1 - z0, mat);
    b.box((x0 + x1) / 2, 2, z0 - 0.25, x1 - x0 + 1, 4.5, 0.5, mat);
  }

  private makeJunction(b: LevelBuilder, x: number, y: number, z: number, i: number) {
    const group = new THREE.Group();
    group.position.set(x, y, z);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.42, 0.05, 8, 32), getMaterial('metal'));
    const back = new THREE.Mesh(new THREE.CircleGeometry(0.42, 32), getMaterial('metal_dark'));
    back.position.z = -0.01;
    const mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(0xff8040).multiplyScalar(2) });
    const piece = new THREE.Group();
    const bar1 = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.4, 0.05), mat);
    bar1.position.set(0, 0.2, 0.03);
    const bar2 = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.08, 0.05), mat);
    bar2.position.set(0.2, 0, 0.03);
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.06, 12).rotateX(Math.PI / 2), mat);
    hub.position.z = 0.03;
    piece.add(bar1, bar2, hub);
    group.add(back, ring, piece);
    b.object(group, false);
    const j = { group, piece, state: JUNCTION_START[i], mat };
    piece.rotation.z = -j.state * (Math.PI / 2);
    return j;
  }

  private layout(ctx: BuildContext) {
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    this.spawns = {
      start: { pos: v(0, 4.05, 1), yaw: 0 },
      from_plaza: { pos: v(0, 4.05, 1), yaw: 0 },
      from_facility: { pos: v(62, -1.25, 55), yaw: -Math.PI / 2 },
    };
    this.exits.push(
      { id: 'x_metro_plaza', target: 'plaza', entry: 'from_metro', pos: v(0, 4.05, -1.2), radius: 1.6, prompt: 'Return to the plaza', auto: true },
      { id: 'x_metro_facility', target: 'facility', entry: 'from_metro', pos: v(66, -1.25, 55), radius: 2.5, prompt: 'Follow the spur tunnel', auto: true, requires: () => this.rtRef?.flag('spur_open') ?? false, lockedText: 'An energy barrier seals the spur tunnel.' },
    );
    this.triggers.push(
      { id: 't_metro_concourse', box: new THREE.Box3(v(-18, 3, 12), v(18, 9, 36)) },
      { id: 't_metro_platform', box: new THREE.Box3(v(-44, -2, 42), v(44, 5, 52)) },
    );
    this.encounters.push(
      { id: 'e_metro_concourse', spawn: 'quest', waves: [[{ type: 'drone', pos: v(-8, 8.5, 26) }, { type: 'drone', pos: v(8, 8.6, 24) }, { type: 'drone', pos: v(0, 8.8, 31) }]], arena: { center: v(0, 4, 24), radius: 20 } },
      { id: 'e_metro_platform', spawn: 'quest', waves: [[{ type: 'sentinel', pos: v(-14, 0.05, 47) }, { type: 'sentinel', pos: v(16, 0.05, 48) }], [{ type: 'drone', pos: v(0, 3.4, 49) }, { type: 'sentinel', pos: v(26, 0.05, 46) }]], arena: { center: v(0, 0, 47), radius: 46 } },
      { id: 'e_metro_tunnel', spawn: 'quest', waves: [[{ type: 'sentinel', pos: v(36, 0.05, 47) }, { type: 'sentinel', pos: v(40, 0.05, 45) }, { type: 'drone', pos: v(30, 3.4, 50) }]], arena: { center: v(30, 0, 50), radius: 30 } },
    );
    this.collectibles.push(
      { id: 'c_frag_06', pos: v(-42.5, 1.0, 46) },
      { id: 'c_frag_07', pos: v(34, -0.4, 56.5) },
      { id: 'c_rec_03', pos: v(-18, 1.0, 51.0) },
      { id: 'c_cache_02', pos: v(-21.2, 0.6, 40.8) },
    );
    this.itemPickups.push({ id: 'i_metro_actuator', item: 'q_actuator', pos: v(-21, 1.15, 38), cond: ['quest:sq_broken_guardian:active'] });
    // Junctions
    this.junctions.forEach((j, i) => {
      this.addInteractable({
        id: `i_junction_${i + 1}`,
        kind: 'puzzle',
        pos: j.group.position.clone().add(v(0, 0, 0.8)),
        radius: 1.4,
        prompt: `Rotate junction ${i + 1}`,
        available: () => !this.powered,
        onInteract: () => this.rotateJunction(i),
      });
    });
    this.addInteractable({
      id: 'i_generator', kind: 'inspect', pos: this.markers.generator, radius: 2.2, prompt: 'Inspect generator',
      available: () => !this.powered,
      onInteract: () => this.rtRef?.hint('The generator is running, but power isn\'t reaching the breaker. Rotate the three junctions so the conduit runs from the generator to the breaker.'),
    });
    this.questPoint('i_transmitter', this.markers.transmitter, 'Investigate the transmitter', ['stage:m2_dead_signal:transmitter'], { radius: 2.6 });
    this.addInteractable({ id: 'i_save_metro', kind: 'save', pos: v(-12, 5.3, 13.3), radius: 2, prompt: 'Use save terminal', onInteract: () => undefined });
    void ctx;
  }

  private rotateJunction(i: number) {
    const j = this.junctions[i];
    j.state = (j.state + 1) % 4;
    this.rtRef?.sfx('metal_impact', j.group.position);
    this.updateCircuit();
  }

  private updateCircuit() {
    const ok = this.junctions.map((j, i) => j.state === JUNCTION_TARGET[i]);
    this.junctions.forEach((j, i) => j.mat.color.set(ok[i] ? 0x52ff9a : 0xff8040).multiplyScalar(2));
    // Conduits light progressively along the path.
    const lit = [true, ok[0], ok[0], ok[0] && ok[1], ok[0] && ok[1], ok.every(Boolean)];
    this.conduitMats.forEach((m, i) => m.color.set(lit[i] ? 0x5fd8ff : 0x401010).multiplyScalar(lit[i] ? 2.2 : 1));
    if (ok.every(Boolean) && !this.powered) {
      this.setPowered(true, false);
      this.rtRef?.setFlag('metro_power_on');
      this.rtRef?.sfx('door', this.signalDoor.position);
      this.rtRef?.hint('Power restored. The signal room is open.');
    }
  }

  private setPowered(on: boolean, instant: boolean) {
    this.powered = on;
    const lampMat = getMaterial(on ? 'emit_white' : 'black');
    for (const l of this.lamps) l.material = lampMat;
    for (const e of this.emergency) {
      e.color.set(on ? 0xdfe8ff : 0xff4030);
      e.intensity = on ? 110 : 60;
      e.distance = on ? 22 : 16;
    }
    if (this.signalLight) this.signalLight.intensity = on ? 70 : 0;
    if (on) {
      if (this.signalDoorCollider) {
        this.rtRef?.removeCollider(this.signalDoorCollider);
        this.signalDoorCollider = null;
      }
      (this.transmitterGlow.material as THREE.MeshBasicMaterial).color.set(0x5fd8ff).multiplyScalar(1.5);
      if (instant) this.signalDoor.position.y = 5;
      this.junctions.forEach((j, i) => {
        j.state = JUNCTION_TARGET[i];
        j.piece.rotation.z = -j.state * (Math.PI / 2);
      });
    }
    this.junctions.forEach((j, i) => j.mat.color.set(j.state === JUNCTION_TARGET[i] ? 0x52ff9a : 0xff8040).multiplyScalar(2));
    if (on) this.conduitMats.forEach((m) => m.color.set(0x5fd8ff).multiplyScalar(2.2));
  }

  private openBarrier(instant = false) {
    this.barrierOpen = true;
    if (this.barrierCollider) {
      this.rtRef?.removeCollider(this.barrierCollider);
      this.barrierCollider = null;
    }
    if (instant) this.barrier.visible = false;
  }

  onEnter(rt: ZoneRuntime) {
    // Sparks from broken fixtures and drips.
    rt.vfx.addEmitter(new THREE.Vector3(4, 5.8, 20), 'sparks', 3);
    rt.vfx.addEmitter(new THREE.Vector3(-30, 4.3, 46.3), 'sparks', 3);
    rt.vfx.addEmitter(new THREE.Vector3(18, 4.3, 46.3), 'sparks', 2);
    rt.vfx.addEmitter(new THREE.Vector3(30, 1.7, 35.2), 'steam', 2);
    this.updateCircuit();
    if (this.powered) this.setPowered(true, true);
  }

  update(dt: number, rt: ZoneRuntime) {
    super.update(dt, rt);
    // Junction pieces animate toward their target rotation.
    for (const j of this.junctions) {
      const want = -j.state * (Math.PI / 2);
      j.piece.rotation.z += (want - j.piece.rotation.z) * Math.min(1, dt * 12);
    }
    if (this.powered && this.signalDoor.position.y < 5) this.signalDoor.position.y = Math.min(5, this.signalDoor.position.y + dt * 1.5);
    if (!this.barrierOpen && rt.flag('spur_open')) this.openBarrier();
    if (this.barrierOpen && this.barrier.visible) {
      const m = this.barrier.material as THREE.MeshBasicMaterial;
      m.opacity = Math.max(0, m.opacity - dt * 0.5);
      if (m.opacity <= 0) this.barrier.visible = false;
    } else if (this.barrier.visible) (this.barrier.material as THREE.MeshBasicMaterial).opacity = 0.35 + Math.sin(this.time * 4) * 0.12;
    if (!this.powered) for (const e of this.emergency) e.intensity = 45 + Math.sin(this.time * 3 + e.position.x) * 15;
    // Splashes while wading through the flooded track.
    const p = rt.playerPos;
    if (this.waterBox.containsPoint(p)) {
      this.splashT -= dt;
      const sp = Math.hypot(rt.playerVelocity.x, rt.playerVelocity.z);
      if (sp > 1 && this.splashT <= 0) {
        this.splashT = 0.18;
        rt.vfx.sparks(p.clone().setY(-0.9), new THREE.Vector3(0, 1, 0), 6, 0x8ab0c8, 2.5);
      }
    }
  }
}

function lampTube(b: LevelBuilder, x: number, y: number, z: number): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.06, 2.2), getMaterial('black'));
  m.position.set(x, y, z);
  b.object(m, false);
  const housing = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.1, 2.4), getMaterial('metal_dark'));
  housing.position.set(x, y + 0.08, z);
  b.object(housing, false);
  return m;
}

function finalizeAll(...bs: LevelBuilder[]) {
  for (const b of bs) b.finalize();
}
