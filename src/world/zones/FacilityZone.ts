import * as THREE from 'three';
import type RAPIER from '@dimforge/rapier3d-compat';
import { bakeEnvironment } from '../../render/Environment';
import { getMaterial } from '../../render/Materials';
import { LevelBuilder } from '../kit/LevelBuilder';
import { glassWall, labBench, pod, room, serverRack } from '../kit/Interior';
import * as P from '../kit/Props';
import { Zone, type BuildContext, type ZoneRuntime } from '../Zone';

// Aether Research Division. Grid layout (x east, z south):
//  North row z[-20,0]:  lift room x[-44,-30] | hidden office x[-30,-14] | north hall x[-14,14] | Maren's lab x[14,34]
//  Middle  z[0,30]:     west wing x[-44,-14] (containment, server / corridor / Lab A, Lab B) | atrium x[-14,14] | offices x[14,34]
//  South   z[30,46]:    lobby x[-12,12]  (main gate to the plaza)
//  East:                spur station x[34,48] z[0,20] (to the metro)

export class FacilityZone extends Zone {
  private holo: THREE.Object3D[] = [];
  private hiddenWall!: THREE.Mesh;
  private hiddenCollider: RAPIER.Collider | null = null;
  private fieldOn = true;
  private fieldT = 0;
  private fieldMesh!: THREE.Mesh;
  private fieldBox = new THREE.Box3(new THREE.Vector3(-28, 0, 5.2), new THREE.Vector3(-16, 3, 7.8));
  private fieldHitCd = 0;
  private alarm: THREE.PointLight | null = null;

  constructor() {
    super('facility');
    this.indoor = true;
    this.killY = -10;
    this.music = 'tension';
    this.ambience = 'facility_hum';
    this.grade = { exposure: 1.08, contrast: 1.06, saturation: 0.88, lift: [0.0, 0.008, 0.014], gain: [0.97, 1.0, 1.04], bloomThreshold: 0.88 };
  }

  async build(ctx: BuildContext) {
    const S = this.scene;
    const b = (this.builder = new LevelBuilder(this.root, ctx.physics));
    b.lightBudget = 12;
    S.background = new THREE.Color(0x05080b);
    S.fog = new THREE.FogExp2(0x0a0f14, 0.009);
    S.environment = bakeEnvironment(ctx.rs.renderer, { top: 0x1a2530, horizon: 0x223040, bottom: 0x0a0e12 }, [{ dir: new THREE.Vector3(0, 1, 0), color: 0xe8f2ff, size: 8, intensity: 1.2 }]);
    S.environmentIntensity = 0.8;
    const hemi = new THREE.HemisphereLight(0x9ab4cc, 0x20242a, 1.0);
    S.add(hemi);
    const sky = new THREE.DirectionalLight(0xc8dcf0, 1.2);
    sky.position.set(10, 40, 18);
    sky.castShadow = true;
    S.add(sky, sky.target);
    this.sun = sky;
    await ctx.progress(0.1, 'Facility shell');

    const lab = { floor: 'floor_lab' as const, wall: 'panel_lab' as const, ceiling: 'panel_lab' as const, panels: 'emit_white' as const, trim: 'metal_dark' as const };
    // ---------------------------------------------------------------- Lobby
    room(b, -12, 30, 12, 46, 5, { ...lab, skip: ['n'], doors: [{ side: 's', at: 0, w: 6, h: 3.6 }] });
    b.box(0, 0.55, 37, 7, 1.1, 1.6, 'metal_painted');
    b.box(0, 1.12, 37, 7.2, 0.06, 1.8, 'metal', { collide: false });
    P.terminal(b, -2, 36.4, Math.PI, true);
    P.terminal(b, 2, 36.4, Math.PI, false);
    glassWall(b, -12, 34, -5, 34, 3.2);
    glassWall(b, 5, 34, 12, 34, 3.2);
    P.sign(b, 0, 3.9, 30.3, 9, 1.0, Math.PI, ['AETHER RESEARCH DIVISION'], { bg: '#0b1218', fg: '#9fd8ee', glow: 1.1 });
    for (const x of [-9, 9]) P.bench(b, x, 42, 0);
    b.box(0, -0.25, 48, 10, 0.5, 4, 'concrete_wet');
    b.wall(0, 2, 50.2, 10, 4, 0.4);
    b.wall(-5.2, 2, 48, 0.4, 4, 4);
    b.wall(5.2, 2, 48, 0.4, 4, 4);
    b.pointLight(0, 4, 40, 0xe8f2ff, 70, 18, 1.6);

    // ---------------------------------------------------------------- Atrium
    room(b, -14, 0, 14, 30, 10, { ...lab, ceiling: 'glass_dark', panels: null, doors: [{ side: 'n', at: 0, w: 4, h: 3.2 }, { side: 's', at: 0, w: 12, h: 5 }, { side: 'w', at: 15, w: 4, h: 3.2 }, { side: 'e', at: 10, w: 4, h: 3.2 }] });
    // Balcony ring (visual) and columns
    for (const x of [-10, 10]) for (const z of [5, 15, 25]) b.box(x, 5, z, 0.8, 10, 0.8, 'concrete');
    b.box(-12.5, 5, 15, 3, 0.3, 30, 'panel_lab', { collide: false });
    b.box(12.5, 5, 15, 3, 0.3, 30, 'panel_lab', { collide: false });
    P.railing(b, -11, 0.5, -11, 29.5, 5.15, 1.0, false);
    P.railing(b, 11, 0.5, 11, 29.5, 5.15, 1.0, false);
    // Aether hologram centrepiece
    b.cyl(0, 0.4, 15, 2.6, 2.8, 0.8, 'metal_dark', 32);
    b.cyl(0, 0.82, 15, 2.2, 2.2, 0.04, 'emit_cyan', 48, { collide: false });
    const holoCore = new THREE.Mesh(new THREE.IcosahedronGeometry(1.1, 3), getMaterial('aether'));
    holoCore.position.set(0, 3.6, 15);
    b.object(holoCore, false);
    this.holo.push(holoCore);
    for (let i = 0; i < 3; i++) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(1.8 + i * 0.5, 0.02, 6, 64), getMaterial('emit_cyan'));
      ring.position.set(0, 3.6, 15);
      ring.rotation.set(Math.PI / 2 + i * 0.5, i, 0);
      b.object(ring, false);
      this.holo.push(ring);
    }
    b.pointLight(0, 3.6, 15, 0x5fd8ff, 160, 22, 1.6);
    b.pointLight(0, 8.5, 6, 0xe8f2ff, 90, 24, 1.5);
    this.markers.warden_drop = new THREE.Vector3(0, 1.2, 9);
    await ctx.progress(0.3, 'Atrium');

    // ---------------------------------------------------------------- West wing
    b.box(-29, -0.25, 15, 30, 0.5, 30, 'floor_lab');
    b.box(-29, 4.25, 15, 30.8, 0.5, 30.8, 'panel_lab', { collide: false });
    // Outer walls (n with door to the lift room; w; s)
    b.box(-41.3, 2, -0.2, 6.2, 4, 0.4, 'panel_lab');
    b.box(-24.8, 2, -0.2, 22, 4, 0.4, 'panel_lab');
    b.box(-37, 3.5, -0.2, 2.8, 1, 0.4, 'panel_lab');
    b.box(-44.2, 2, 15, 0.4, 4, 30.8, 'panel_lab');
    b.box(-29, 2, 30.2, 30.8, 4, 0.4, 'panel_lab');
    // Internal walls: z=13 (doors at -37, -22) and glass at z=17 for the labs
    const wallZ = (z: number, gaps: number[]) => {
      let cur = -44;
      for (const g of gaps) {
        b.box((cur + g - 1.2) / 2, 2, z, g - 1.2 - cur, 4, 0.3, 'panel_lab');
        b.box(g, 3.5, z, 2.4, 1, 0.3, 'panel_lab');
        cur = g + 1.2;
      }
      b.box((cur - 14) / 2, 2, z, -14 - cur, 4, 0.3, 'panel_lab');
    };
    wallZ(13, [-37, -22]);
    glassWall(b, -44, 17, -38.2, 17, 3);
    glassWall(b, -35.8, 17, -23.2, 17, 3);
    glassWall(b, -20.8, 17, -14, 17, 3);
    b.box(-30, 2, 6.5, 0.3, 4, 13, 'panel_lab');
    glassWall(b, -30, 17, -30, 30, 3);
    // Corridor panels
    for (let x = -42; x < -15; x += 5) b.box(x, 3.98, 15, 1.6, 0.04, 0.6, 'emit_white', { collide: false, shadow: false });
    // Lab A & B
    labBench(b, -40, 22, 0, 1);
    labBench(b, -34, 22, 0, 2);
    labBench(b, -40, 26.5, 0, 3);
    P.terminal(b, -41, 28.6, Math.PI, true);
    labBench(b, -26, 21.5, 0, 4);
    labBench(b, -19, 21.5, 0, 5);
    labBench(b, -26, 26, 0.1, 6);
    P.terminal(b, -24, 28.6, Math.PI, true);
    b.pointLight(-37, 3.6, 23, 0xe8f2ff, 60, 14, 1.6);
    b.pointLight(-22, 3.6, 23, 0xe8f2ff, 50, 14, 1.6);
    // Containment (pods) and server room
    for (const [x, z, g] of [[-41, 4, true], [-36.5, 4, false], [-33, 4, true], [-41, 9, true], [-33, 9, false]] as [number, number, boolean][]) pod(b, x, z, g);
    for (let x = -28; x <= -17; x += 2.2) {
      serverRack(b, x, 2, 0);
      serverRack(b, x, 11, Math.PI);
    }
    P.terminal(b, -15.2, 6.5, -Math.PI / 2, true);
    this.alarm = b.pointLight(-22, 3.4, 6.5, 0xff3a2e, 40, 12, 1.6);
    const fieldMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(0xff3a2e).multiplyScalar(1.8), transparent: true, opacity: 0.4, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
    this.fieldMesh = new THREE.Mesh(new THREE.BoxGeometry(12, 2.6, 2.6), fieldMat);
    this.fieldMesh.position.set(-22, 1.3, 6.5);
    b.object(this.fieldMesh, false);
    for (const x of [-28.2, -15.8]) b.box(x, 1.4, 6.5, 0.3, 2.8, 0.3, 'metal_red', { collide: false });
    await ctx.progress(0.45, 'Laboratories');

    // ---------------------------------------------------------------- Offices (east)
    room(b, 14, 0, 34, 30, 4, { ...lab, skip: ['w'], doors: [{ side: 'e', at: 10, w: 4, h: 3.2 }] });
    glassWall(b, 14, 12.5, 22, 12.5, 2.8);
    glassWall(b, 26, 12.5, 34, 12.5, 2.8);
    glassWall(b, 14, 7.5, 34, 7.5, 2.8);
    for (const [x, z] of [[17, 17], [22, 17], [27, 17], [31, 17], [17, 23], [22, 23], [27, 23], [31, 23]] as [number, number][]) {
      b.box(x, 0.75, z, 1.8, 0.06, 0.9, 'wood');
      b.box(x, 0.37, z, 1.7, 0.74, 0.1, 'metal_dark');
      b.box(x, 1.05, z - 0.3, 0.6, 0.38, 0.04, Math.random() < 0.5 ? 'screen' : 'glass_dark', { collide: false });
    }
    P.crateStack(b, 31, 3, 0.4, 501);
    b.pointLight(24, 3.6, 20, 0xe8f2ff, 60, 16, 1.6);
    // Spur station
    room(b, 34, 0, 48, 20, 5, { floor: 'concrete', wall: 'concrete_dark', ceiling: 'concrete_dark', panels: null, trim: null, skip: ['e'], doors: [{ side: 'w', at: 10, w: 4, h: 3.2 }] });
    b.box(45, -0.65, 10, 6, 1.3, 20, 'concrete_dark', { collide: false });
    b.box(50, 2, 10, 4, 6, 22, 'concrete_dark');
    P.trainCar(b, 46, 12.2, Math.PI / 2, 88, true);
    b.box(41.8, 0.02, 10, 0.3, 0.04, 20, 'metal_yellow', { collide: false, shadow: false });
    P.sign(b, 34.3, 3.4, 10, 4, 0.7, Math.PI / 2, ['SPUR STATION'], { bg: '#08141a', fg: '#7fe0ff', glow: 1.0 });
    b.pointLight(40, 4, 10, 0xffc890, 60, 16, 1.6);

    // ---------------------------------------------------------------- North row
    room(b, -14, -20, 14, 0, 4.5, { ...lab, skip: ['s'], doors: [{ side: 'w', at: -10, w: 2.4, h: 3 }, { side: 'e', at: -10, w: 2.6, h: 3 }] });
    P.sign(b, 0, 3.6, -19.75, 6, 0.8, 0, ['DIRECTOR · DR. I. MAREN'], { bg: '#0b1218', fg: '#9fd8ee', glow: 1.0 });
    // The hidden office door is a wall panel that Echo Sight reveals.
    this.hiddenWall = new THREE.Mesh(new THREE.BoxGeometry(0.42, 3, 2.4), getMaterial('panel_lab'));
    this.hiddenWall.position.set(-14.2, 1.5, -10);
    b.object(this.hiddenWall);
    this.hiddenCollider = b.physics.addBox(-14.2, 1.5, -10, 0.21, 1.5, 1.2);
    // Maren's lab
    room(b, 14, -20, 34, 0, 4.5, { ...lab, skip: ['w', 's'] });
    labBench(b, 20, -14, 0, 11);
    labBench(b, 27, -14, 0, 12);
    pod(b, 30, -5, true);
    P.terminal(b, 24, -18.2, 0, true);
    b.box(24, 2.4, -19.75, 6, 2.2, 0.06, 'screen', { collide: false });
    b.pointLight(24, 3.8, -10, 0xd8ecff, 60, 16, 1.6);
    // Hidden office
    room(b, -30, -20, -14, 0, 4, { floor: 'wood', wall: 'plaster', ceiling: 'plaster', panels: null, trim: 'metal_dark', skip: ['e'] });
    b.box(-26, 0.75, -17, 3, 0.08, 1.4, 'wood');
    b.box(-26, 0.37, -17, 2.8, 0.74, 0.2, 'wood');
    P.terminal(b, -26, -18.6, 0, true);
    for (let i = 0; i < 5; i++) b.box(-29.6, 0.5 + i * 0.42, -10 + i * 0.2, 0.3, 0.05, 3.2, 'wood', { collide: false });
    b.pointLight(-22, 3.2, -10, 0xffd6a0, 90, 14, 1.6);
    // Lift room
    room(b, -44, -20, -30, 0, 6, { floor: 'grate', wall: 'metal_dark', ceiling: 'metal_dark', panels: null, trim: 'metal_yellow', skip: ['s'] });
    b.box(-37, 0.05, -10, 6, 0.1, 6, 'metal_yellow', { collide: false });
    for (const [x, z] of [[-40, -13], [-34, -13], [-40, -7], [-34, -7]] as [number, number][]) b.box(x, 3, z, 0.3, 6, 0.3, 'metal_dark', { collide: false });
    b.box(-37, 0.11, -10, 5.6, 0.02, 5.6, 'emit_amber', { collide: false, shadow: false });
    P.terminal(b, -33, -4, -Math.PI / 2, true);
    P.sign(b, -37, 4.8, -19.75, 5, 0.8, 0, ['FREIGHT LIFT · VAULT ACCESS'], { bg: '#1a1008', fg: '#ffb46a', glow: 1.2 });
    await ctx.progress(0.6, 'Offices');

    b.finalize();
    this.layout();
    this.map = {
      min: new THREE.Vector2(-46, -22),
      max: new THREE.Vector2(50, 50),
      shapes: [
        { kind: 'floor', x: 0, z: 38, w: 24, d: 16 },
        { kind: 'floor', x: 0, z: 15, w: 28, d: 30 },
        { kind: 'floor', x: -29, z: 15, w: 30, d: 30 },
        { kind: 'floor', x: 24, z: 15, w: 20, d: 30 },
        { kind: 'floor', x: 41, z: 10, w: 14, d: 20 },
        { kind: 'floor', x: 0, z: -10, w: 28, d: 20 },
        { kind: 'floor', x: 24, z: -10, w: 20, d: 20 },
        { kind: 'floor', x: -37, z: -10, w: 14, d: 20 },
        { kind: 'block', x: -29, z: 15, w: 30, d: 4 },
      ],
      labels: [{ text: 'LOBBY', x: 0, z: 38 }, { text: 'ATRIUM', x: 0, z: 15 }, { text: 'LABS', x: -29, z: 23 }, { text: 'OFFICES', x: 24, z: 20 }, { text: 'MAREN', x: 24, z: -10 }, { text: 'LIFT', x: -37, z: -10 }, { text: 'SPUR', x: 41, z: 10 }],
    };
  }

  private layout() {
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    this.spawns = {
      start: { pos: v(40, 0.05, 10), yaw: -Math.PI / 2 },
      from_metro: { pos: v(40, 0.05, 10), yaw: -Math.PI / 2 },
      from_plaza: { pos: v(0, 0.05, 43), yaw: Math.PI },
      from_vault: { pos: v(-37, 0.1, -6), yaw: 0 },
    };
    const rt = () => this.rtRef;
    this.exits.push(
      { id: 'x_facility_metro', target: 'metro', entry: 'from_facility', pos: v(46.5, 0.05, 2.5), radius: 1.8, prompt: 'Back to the metro', auto: true },
      { id: 'x_facility_plaza', target: 'plaza', entry: 'from_facility', pos: v(0, 0.05, 47.5), radius: 2.4, prompt: 'Exit to the Central Plaza', requires: () => rt()?.flag('facility_gate_open') ?? false, lockedText: 'The gate is sealed. The control panel by reception can open it.' },
      { id: 'i_freight_lift', target: 'vault', entry: 'from_facility', pos: v(-37, 0.1, -10), radius: 3, prompt: 'Take the freight lift down to the Vault', requires: () => rt()?.check('item:q_vault_clearance') ?? false, lockedText: 'The lift requires Dr. Maren\'s vault clearance.' },
    );
    this.triggers.push(
      { id: 't_fac_labs', box: new THREE.Box3(v(-20, -1, 12), v(-12, 4, 18)) },
      { id: 't_fac_atrium', box: new THREE.Box3(v(-14, -1, 0), v(14, 8, 30)) },
    );
    this.encounters.push(
      { id: 'e_fac_labs', spawn: 'quest', waves: [[{ type: 'sentinel', pos: v(-36, 0.05, 15) }, { type: 'sentinel', pos: v(-25, 0.05, 22) }, { type: 'drone', pos: v(-30, 3.2, 15) }]], arena: { center: v(-29, 0, 15), radius: 24 } },
      { id: 'e_fac_offices', spawn: 'quest', waves: [[{ type: 'drone', pos: v(24, 3.0, 20) }, { type: 'drone', pos: v(20, 3.0, 4) }, { type: 'sentinel', pos: v(28, 0.05, 10) }]], arena: { center: v(24, 0, 15), radius: 22 } },
      { id: 'e_fac_warden', spawn: 'quest', waves: [[{ type: 'warden', pos: v(0, 0.05, 6), yaw: 0 }, { type: 'drone', pos: v(-8, 6, 10) }, { type: 'drone', pos: v(8, 6, 10) }]], arena: { center: v(0, 0, 15), radius: 18 } },
    );
    this.collectibles.push(
      { id: 'c_frag_08', pos: v(-17, 1.1, 27.5) },
      { id: 'c_frag_09', pos: v(0, 1.6, 21.5) },
      { id: 'c_rec_04', pos: v(31, 1.15, 23) },
      { id: 'c_rec_05', pos: v(-42.6, 0.8, 1.6) },
      { id: 'c_cache_03', pos: v(-15.4, 0.6, 1.3) },
    );
    // Research logs: completing quest objectives and recovering lore.
    const log = (id: string, item: string, pos: THREE.Vector3, label: string) =>
      this.addInteractable({
        id, kind: 'terminal', pos, radius: 2, prompt: `Read log: ${label}`,
        available: () => !(rt()?.check(`item:${item}`) ?? true),
        onInteract: () => {
          const r = rt();
          if (!r) return;
          r.sfx('terminal', pos);
          r.giveItem(item);
          r.playDialogue(item);
          r.emitInteract(id);
        },
      });
    log('i_log_echo', 'lore_log_echo', v(-41, 1.3, 27.6), 'Project Echo');
    log('i_log_keys', 'lore_log_keys', v(-24, 1.3, 27.6), 'Resonance Keys');
    log('i_log_cascade', 'lore_log_cascade', v(-15.9, 1.3, 6.5), 'Cascade Projection');
    this.questPoint('i_maren_terminal', v(24, 1.3, -17.2), 'Recover Dr. Maren\'s research data', ['stage:m3_researcher:data'], { radius: 2.2 });
    this.addInteractable({
      id: 'i_maren_hidden_door', kind: 'door', pos: v(-14.2, 1.5, -10), radius: 3, prompt: 'Hidden door', hidden: true,
      available: () => false,
      onInteract: () => undefined,
      onReveal: () => this.openHidden(),
    });
    this.addInteractable({
      id: 'i_maren_final', kind: 'terminal', pos: v(-26, 1.3, -17.8), radius: 2, prompt: 'Read Maren\'s final entry',
      available: () => !(rt()?.check('item:lore_log_final') ?? true),
      onInteract: () => {
        const r = rt();
        if (!r) return;
        r.sfx('terminal');
        r.giveItem('lore_log_final');
        r.emitInteract('i_maren_final');
      },
    });
    this.addInteractable({
      id: 'i_gate_control', kind: 'inspect', pos: v(-2, 1.3, 35.8), radius: 2, prompt: 'Open the main gate (shortcut to the plaza)',
      available: () => !(rt()?.flag('facility_gate_open') ?? true),
      onInteract: () => {
        rt()?.setFlag('facility_gate_open');
        rt()?.sfx('door');
        rt()?.hint('Main gate unlocked. The facility now connects directly to the Central Plaza.');
      },
    });
    this.addInteractable({ id: 'i_save_facility', kind: 'save', pos: v(2, 1.3, 35.8), radius: 2, prompt: 'Use save terminal', onInteract: () => undefined });
  }

  private openHidden() {
    if (this.hiddenCollider) {
      this.rtRef?.removeCollider(this.hiddenCollider);
      this.hiddenCollider = null;
    }
    this.hiddenWall.visible = false;
    this.rtRef?.sfx('door', this.hiddenWall.position);
  }

  onEnter(rt: ZoneRuntime) {
    if (rt.revealed('i_maren_hidden_door')) this.openHidden();
    rt.vfx.addEmitter(new THREE.Vector3(0, 0.9, 15), 'aether', 6, 2.2);
    rt.vfx.addEmitter(new THREE.Vector3(-36.5, 2.6, 4), 'sparks', 2);
  }

  update(dt: number, rt: ZoneRuntime) {
    super.update(dt, rt);
    this.holo.forEach((o, i) => {
      o.rotation.y += dt * (0.2 + i * 0.15);
      if (i > 0) o.rotation.x += dt * 0.1 * i;
    });
    // Security field in the server room pulses on and off.
    this.fieldT += dt;
    const cycle = this.fieldT % 4;
    const wasOn = this.fieldOn;
    this.fieldOn = cycle < 2.2;
    if (this.fieldOn !== wasOn) rt.sfx(this.fieldOn ? 'enemy_telegraph' : 'shield_hit', this.fieldMesh.position);
    const m = this.fieldMesh.material as THREE.MeshBasicMaterial;
    m.opacity = this.fieldOn ? 0.32 + Math.sin(this.time * 30) * 0.06 : cycle > 3.5 ? 0.12 : 0.02;
    if (this.alarm) this.alarm.intensity = this.fieldOn ? 40 : 6;
    this.fieldHitCd -= dt;
    if (this.fieldOn && this.fieldHitCd <= 0 && this.fieldBox.containsPoint(rt.playerPos.clone().setY(rt.playerPos.y + 0.5))) {
      this.fieldHitCd = 0.8;
      rt.damagePlayer(9, 'security field', new THREE.Vector3(rt.playerPos.x, 1, 6.5));
      rt.vfx.sparks(rt.playerPos.clone().setY(rt.playerPos.y + 1), null, 14, 0xff5a3a, 5);
    }
  }
}
