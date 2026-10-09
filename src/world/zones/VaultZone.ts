import * as THREE from 'three';
import type RAPIER from '@dimforge/rapier3d-compat';
import { bakeEnvironment } from '../../render/Environment';
import { getMaterial } from '../../render/Materials';
import { LevelBuilder } from '../kit/LevelBuilder';
import { pod, room } from '../kit/Interior';
import * as P from '../kit/Props';
import { Zone, type BuildContext, type ZoneRuntime } from '../Zone';

// Underground Aether Vault (z increases deeper).
//  Lift landing z[-4,4] → great hall x[-10,10] z[4,40] (vents at z=16, z=28; hidden wall west at z=24)
//  → lock chamber x[-14,14] z[40,60] (three resonators, glyphs) → attunement z[60,74]
//  → Guardian gallery x[-8,8] z[74,104] → blast door z=104 → core lift z[104,118].
//  Secret room x[-22,-10] z[18,30].

const GLYPH_TARGET = [3, 1, 4];
const DOOR_TIME = 38;

export class VaultZone extends Zone {
  private resonators: { ring: THREE.Mesh[]; value: number; pos: THREE.Vector3 }[] = [];
  private lockDoor!: THREE.Group;
  private lockCollider: RAPIER.Collider | null = null;
  private lockOpen = false;
  private blastDoor!: THREE.Group;
  private blastCollider: RAPIER.Collider | null = null;
  private blastT = 0;
  private blastOpen = false;
  private blastLights: THREE.Mesh[] = [];
  private vents: { box: THREE.Box3; mesh: THREE.Mesh; offset: number; hitCd: number }[] = [];
  private hiddenWall!: THREE.Mesh;
  private hiddenCollider: RAPIER.Collider | null = null;
  private attuneCore!: THREE.Mesh;
  private glowLights: THREE.PointLight[] = [];

  constructor() {
    super('vault');
    this.indoor = true;
    this.killY = -14;
    this.music = 'tension';
    this.ambience = 'vault_hum';
    this.grade = { exposure: 1.2, contrast: 1.1, saturation: 1.0, lift: [0.004, 0.0, 0.02], gain: [0.96, 0.98, 1.06], bloomThreshold: 0.82 };
  }

  async build(ctx: BuildContext) {
    const S = this.scene;
    const b = (this.builder = new LevelBuilder(this.root, ctx.physics));
    b.lightBudget = 12;
    S.background = new THREE.Color(0x020306);
    S.fog = new THREE.FogExp2(0x070812, 0.02);
    S.environment = bakeEnvironment(ctx.rs.renderer, { top: 0x0a0c18, horizon: 0x141830, bottom: 0x050508 }, [
      { dir: new THREE.Vector3(1, 0.2, 0), color: 0x5fd8ff, size: 4, intensity: 2 },
      { dir: new THREE.Vector3(-1, 0.2, 0), color: 0xa47dff, size: 4, intensity: 2 },
    ]);
    S.environmentIntensity = 0.7;
    const hemi = new THREE.HemisphereLight(0x5a6a9a, 0x161220, 1.3);
    S.add(hemi);
    const key = new THREE.DirectionalLight(0x8090c0, 0.5);
    key.position.set(-10, 40, 30);
    key.castShadow = true;
    S.add(key, key.target);
    this.sun = key;
    const metal = { floor: 'grate' as const, wall: 'metal_dark' as const, ceiling: 'metal_dark' as const, panels: null, trim: 'emit_violet' as const };
    await ctx.progress(0.1, 'Vault shell');

    // ---------------------------------------------------------------- Lift landing
    room(b, -5, -4, 5, 4, 6, { ...metal, skip: ['s'] });
    b.box(0, 0.05, -1, 5, 0.1, 5, 'metal_yellow', { collide: false });
    P.terminal(b, 3.8, 2.5, -Math.PI / 2, true);
    P.sign(b, 0, 4.5, -3.75, 5, 0.8, 0, ['LEVEL V-3 · CONTAINMENT'], { bg: '#100a1a', fg: '#c8a8ff', glow: 1.2 });
    this.glowLights.push(b.pointLight(0, 4.5, 0, 0xa47dff, 50, 12, 1.6)!);

    // ---------------------------------------------------------------- Great hall
    room(b, -10, 4, 10, 40, 9, { ...metal, skip: ['n', 's'], doors: [{ side: 'w', at: 24, w: 2.6, h: 3.2 }] });
    // Back-fill the north wall around the landing opening and the south wall around the lock chamber opening.
    b.box(-7.7, 4.5, 3.8, 4.6, 9, 0.4, 'metal_dark');
    b.box(7.7, 4.5, 3.8, 4.6, 9, 0.4, 'metal_dark');
    b.box(0, 7.5, 3.8, 10, 3, 0.4, 'metal_dark');
    // Conduits along the walls
    for (const x of [-9.4, 9.4]) {
      for (let i = 0; i < 3; i++) P.pipe(b, x, 1.2 + i * 1.6, 4, x, 1.2 + i * 1.6, 40, 0.18, 'metal');
      b.box(x * 0.98, 6.4, 22, 0.08, 0.12, 36, x < 0 ? 'emit_violet' : 'emit_cyan', { collide: false, shadow: false });
    }
    // Containment alcoves with sealed chambers
    for (const z of [10, 20, 34]) {
      pod(b, -7.5, z, true);
      pod(b, 7.5, z, z !== 20);
    }
    // Hazard vents
    for (const [z, off] of [[16, 0], [28, 1.6]] as [number, number][]) {
      b.box(0, 0.02, z, 20, 0.04, 1.6, 'grate', { collide: false, shadow: false });
      const m = new THREE.Mesh(new THREE.BoxGeometry(19.6, 2.4, 1.4), new THREE.MeshBasicMaterial({ color: new THREE.Color(0xa47dff).multiplyScalar(1.6), transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
      m.position.set(0, 1.2, z);
      b.object(m, false);
      this.vents.push({ box: new THREE.Box3(new THREE.Vector3(-10, -1, z - 0.8), new THREE.Vector3(10, 2.5, z + 0.8)), mesh: m, offset: off, hitCd: 0 });
    }
    this.glowLights.push(b.pointLight(0, 7, 12, 0x5fd8ff, 90, 22, 1.5)!);
    this.glowLights.push(b.pointLight(0, 7, 30, 0xa47dff, 90, 22, 1.5)!);
    // The hidden wall (west, z=24)
    this.hiddenWall = new THREE.Mesh(new THREE.BoxGeometry(0.42, 3.2, 2.6), getMaterial('metal_dark'));
    this.hiddenWall.position.set(-10.2, 1.6, 24);
    b.object(this.hiddenWall);
    this.hiddenCollider = b.physics.addBox(-10.2, 1.6, 24, 0.21, 1.6, 1.3);
    await ctx.progress(0.3, 'Containment hall');

    // ---------------------------------------------------------------- Secret room (Hidden Vault)
    room(b, -22, 18, -10, 30, 4.5, { floor: 'wood', wall: 'plaster', ceiling: 'plaster', panels: null, trim: 'emit_violet', skip: ['e'] });
    b.cyl(-16, 0.5, 24, 0.8, 1.0, 1.0, 'metal_dark', 16);
    b.cyl(-16, 1.02, 24, 0.7, 0.7, 0.04, 'emit_violet', 24, { collide: false });
    const relic = new THREE.Mesh(new THREE.OctahedronGeometry(0.35, 1), getMaterial('aether'));
    relic.position.set(-16, 1.7, 24);
    relic.name = 'relic';
    b.object(relic, false);
    this.markers.relic = relic.position.clone();
    for (let i = 0; i < 4; i++) b.box(-21.6, 0.6 + i * 0.5, 24, 0.3, 0.05, 4, 'wood', { collide: false });
    this.glowLights.push(b.pointLight(-16, 3.6, 24, 0xc8a8ff, 60, 12, 1.6)!);

    // ---------------------------------------------------------------- Lock chamber
    room(b, -14, 40, 14, 60, 10, { ...metal, skip: ['n'], doors: [{ side: 's', at: 0, w: 6, h: 5 }] });
    b.box(-12, 5, 39.8, 4, 10, 0.4, 'metal_dark');
    b.box(12, 5, 39.8, 4, 10, 0.4, 'metal_dark');
    b.box(0, 9.5, 39.8, 20, 1, 0.4, 'metal_dark');
    const rp = [new THREE.Vector3(-8, 0, 50), new THREE.Vector3(0, 0, 54), new THREE.Vector3(8, 0, 50)];
    rp.forEach((p, i) => this.resonators.push(this.makeResonator(b, p, i)));
    // Glyph plates on the walls (hidden, revealed by Echo Sight)
    const glyphPos = [new THREE.Vector3(-13.75, 4, 46), new THREE.Vector3(0, 6, 59.75), new THREE.Vector3(13.75, 4, 46)];
    glyphPos.forEach((p, i) => this.makeGlyph(b, p, i));
    // The resonance lock door
    this.lockDoor = new THREE.Group();
    const half = (x: number) => {
      const m = new THREE.Mesh(new THREE.BoxGeometry(3, 5, 0.5), getMaterial('metal_painted'));
      m.position.set(x, 2.5, 0);
      const s = new THREE.Mesh(new THREE.BoxGeometry(0.08, 4.6, 0.52), getMaterial('emit_violet'));
      s.position.set(x > 0 ? -1.45 : 1.45, 2.5, 0);
      return [m, s];
    };
    this.lockDoor.add(...half(-1.5), ...half(1.5));
    this.lockDoor.position.set(0, 0, 60.2);
    b.object(this.lockDoor);
    if (!ctx.flag('vault_lock_open')) this.lockCollider = b.physics.addBox(0, 2.5, 60.2, 3, 2.5, 0.25);
    else this.openLock(true);
    // High ledge with a fragment
    b.box(12, 3, 56, 3, 0.4, 7, 'grate');
    b.stairs(12.2, 0, 47, 0, 2.6, 6, 0.5, 0.9, 'grate');
    this.glowLights.push(b.pointLight(0, 8, 50, 0x8fd8ff, 110, 24, 1.5)!);
    await ctx.progress(0.45, 'Resonance lock');

    // ---------------------------------------------------------------- Attunement chamber
    room(b, -8, 60, 8, 74, 8, { ...metal, skip: ['n', 's'] });
    b.cyl(0, 0.6, 67, 1.6, 2, 1.2, 'metal_dark', 24);
    this.attuneCore = new THREE.Mesh(new THREE.IcosahedronGeometry(0.9, 3), getMaterial('aether'));
    this.attuneCore.position.set(0, 2.6, 67);
    b.object(this.attuneCore, false);
    for (const x of [-6, 6]) b.cyl(x, 4, 67, 0.4, 0.5, 8, 'metal', 10);
    this.glowLights.push(b.pointLight(0, 3, 67, 0x5fd8ff, 100, 16, 1.6)!);

    // ---------------------------------------------------------------- Guardian gallery
    room(b, -8, 74, 8, 104, 11, { ...metal, skip: ['n', 's'] });
    for (const z of [80, 88, 96]) for (const x of [-5, 5]) b.box(x, 2, z, 1.4, 4, 1.4, 'concrete_dark');
    b.box(0, -0.5, 78, 6, 0.1, 6, 'emit_red', { collide: false, shadow: false });
    P.debris(b, -4, 92, 2, 6, 701, 'concrete_dark');
    // Blast door
    this.blastDoor = new THREE.Group();
    const bd = new THREE.Mesh(new THREE.BoxGeometry(16, 10, 0.8), getMaterial('metal_yellow'));
    bd.position.y = 5;
    this.blastDoor.add(bd);
    for (let i = 0; i < 8; i++) {
      const l = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.3, 0.1), new THREE.MeshBasicMaterial({ color: new THREE.Color(0x401010) }));
      l.position.set(-4.2 + i * 1.2, 8.5, -0.45);
      this.blastDoor.add(l);
      this.blastLights.push(l);
    }
    this.blastDoor.position.set(0, 0, 104.2);
    b.object(this.blastDoor);
    if (!ctx.flag('vault_escaped')) this.blastCollider = b.physics.addBox(0, 5, 104.2, 8, 5, 0.4);
    else this.blastDoor.position.y = 9.5;
    this.glowLights.push(b.pointLight(0, 9, 90, 0xff8a6a, 160, 30, 1.4)!);
    this.glowLights.push(b.pointLight(0, 8, 78, 0x8fb8ff, 120, 24, 1.5)!);
    // Core lift room
    room(b, -8, 104, 8, 118, 7, { ...metal, skip: ['n'] });
    for (const [x, z, w, d] of [[0, 109, 6, 0.12], [0, 115, 6, 0.12], [-3, 112, 0.12, 6], [3, 112, 0.12, 6]] as [number, number, number, number][]) b.box(x, 0.05, z, w, 0.04, d, 'emit_cyan', { collide: false, shadow: false });
    P.terminal(b, 5, 109, -Math.PI / 2, true);
    P.sign(b, 0, 5, 117.75, 6, 0.9, Math.PI, ['CORE ACCESS'], { bg: '#08141a', fg: '#7fe0ff', glow: 1.4 });
    await ctx.progress(0.6, 'Guardian gallery');

    b.finalize();
    this.layout(ctx);
    this.map = {
      min: new THREE.Vector2(-24, -6),
      max: new THREE.Vector2(16, 120),
      shapes: [
        { kind: 'floor', x: 0, z: 0, w: 10, d: 8 },
        { kind: 'floor', x: 0, z: 22, w: 20, d: 36 },
        { kind: 'floor', x: -16, z: 24, w: 12, d: 12 },
        { kind: 'floor', x: 0, z: 50, w: 28, d: 20 },
        { kind: 'floor', x: 0, z: 67, w: 16, d: 14 },
        { kind: 'floor', x: 0, z: 89, w: 16, d: 30 },
        { kind: 'floor', x: 0, z: 111, w: 16, d: 14 },
      ],
      labels: [{ text: 'HALL', x: 0, z: 22 }, { text: 'LOCK', x: 0, z: 50 }, { text: 'ATTUNEMENT', x: 0, z: 67 }, { text: 'GALLERY', x: 0, z: 89 }, { text: 'CORE LIFT', x: 0, z: 111 }],
    };
  }

  private makeResonator(b: LevelBuilder, p: THREE.Vector3, i: number) {
    b.cyl(p.x, 1.4, p.z, 0.5, 0.7, 2.8, 'metal_dark', 12);
    const ring: THREE.Mesh[] = [];
    for (let k = 0; k < 4; k++) {
      const seg = new THREE.Mesh(new THREE.TorusGeometry(0.75, 0.06, 6, 16, Math.PI / 2 - 0.15), new THREE.MeshBasicMaterial({ color: new THREE.Color(0x202030) }));
      seg.position.set(p.x, 2.2, p.z);
      seg.rotation.set(Math.PI / 2, 0, k * (Math.PI / 2) + 0.075);
      b.object(seg, false);
      ring.push(seg);
    }
    const top = new THREE.Mesh(new THREE.OctahedronGeometry(0.25, 0), getMaterial('emit_violet'));
    top.position.set(p.x, 3.1, p.z);
    b.object(top, false);
    void i;
    return { ring, value: 1, pos: p.clone() };
  }

  private makeGlyph(b: LevelBuilder, p: THREE.Vector3, i: number) {
    const group = new THREE.Group();
    group.position.copy(p);
    if (Math.abs(p.x) > 10) group.rotation.y = p.x < 0 ? Math.PI / 2 : -Math.PI / 2;
    else group.rotation.y = Math.PI;
    const mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(0xc8a8ff).multiplyScalar(2.2) });
    const frame = new THREE.Mesh(new THREE.RingGeometry(0.8, 0.9, 6), mat);
    group.add(frame);
    // Order mark (which resonator) as bars at the top, value as dots in the centre.
    for (let k = 0; k <= i; k++) {
      const bar = new THREE.Mesh(new THREE.PlaneGeometry(0.08, 0.3), mat);
      bar.position.set(-0.15 * i / 2 + k * 0.15, 0.55, 0.01);
      group.add(bar);
    }
    const n = GLYPH_TARGET[i];
    for (let k = 0; k < n; k++) {
      const dot = new THREE.Mesh(new THREE.CircleGeometry(0.09, 12), mat);
      dot.position.set((k - (n - 1) / 2) * 0.28, -0.05, 0.01);
      group.add(dot);
    }
    group.visible = false;
    b.object(group, false);
    this.addInteractable({
      id: `g_glyph_${i + 1}`,
      kind: 'lore',
      pos: p.clone(),
      radius: 4,
      prompt: `Resonance glyph ${i + 1}`,
      hidden: true,
      available: () => true,
      revealObject: group,
      onInteract: () => this.rtRef?.hint(`Glyph ${i + 1}: tune resonator ${i + 1} to ${n}.`),
    });
  }

  private layout(ctx: BuildContext) {
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    const rt = () => this.rtRef;
    this.spawns = {
      start: { pos: v(0, 0.05, 1.5), yaw: 0 },
      from_facility: { pos: v(0, 0.05, 1.5), yaw: 0 },
      from_core: { pos: v(0, 0.05, 110), yaw: Math.PI },
    };
    this.exits.push(
      { id: 'x_vault_facility', target: 'facility', entry: 'from_vault', pos: v(0, 0.05, -1.5), radius: 2, prompt: 'Ride the lift back up to the facility' },
      { id: 'i_core_lift', target: 'core', entry: 'from_vault', pos: v(0, 0.05, 112), radius: 2.8, prompt: 'Ride the lift down to the Aether Core', requires: () => rt()?.flag('vault_escaped') ?? false, lockedText: 'The lift is sealed behind the blast door.' },
    );
    this.triggers.push(
      { id: 't_vault_lock', box: new THREE.Box3(v(-14, -1, 40), v(14, 6, 46)) },
      { id: 't_vault_guardian', box: new THREE.Box3(v(-8, -1, 84), v(8, 6, 90)), available: () => rt()?.check('stage:m4_vault:guardian') ?? false },
      { id: 't_vault_blastdoor', box: new THREE.Box3(v(-8, -1, 106), v(8, 6, 116)) },
    );
    this.encounters.push(
      { id: 'e_vault_hall', spawn: 'quest', waves: [[{ type: 'stalker', pos: v(-5, 0.05, 30) }, { type: 'stalker', pos: v(5, 0.05, 33) }, { type: 'drone', pos: v(0, 5, 26) }]], arena: { center: v(0, 0, 24), radius: 22 } },
      { id: 'e_vault_deep', spawn: 'quest', waves: [[{ type: 'sentinel', pos: v(-8, 0.05, 56) }, { type: 'stalker', pos: v(8, 0.05, 56) }], [{ type: 'stalker', pos: v(0, 0.05, 44) }, { type: 'sentinel', pos: v(6, 0.05, 46) }]], arena: { center: v(0, 0, 55), radius: 22 } },
      { id: 'e_vault_guardian', spawn: 'quest', waves: [[{ type: 'guardian_vault', pos: v(0, 0.05, 78), yaw: 0 }]], arena: { center: v(0, 0, 89), radius: 30 } },
    );
    this.collectibles.push(
      { id: 'c_frag_12', pos: v(12, 4.1, 58) },
      { id: 'c_rec_06', pos: v(-6.5, 1.1, 70) },
      { id: 'c_cache_05', pos: v(-20.5, 0.6, 20) },
    );
    // Resonators
    this.resonators.forEach((r, i) => {
      this.addInteractable({
        id: `i_resonator_${i + 1}`, kind: 'puzzle', pos: r.pos.clone().setY(1.6), radius: 2.2,
        prompt: () => `Tune resonator ${i + 1} (now ${r.value})`,
        available: () => !this.lockOpen,
        onInteract: () => this.tune(i),
      });
    });
    this.questPoint('i_vault_lock', v(0, 1.6, 58.5), 'Inspect the resonance lock', null, {
      available: () => !this.lockOpen,
      onInteract: () => rt()?.hint('Three resonators must hum in tune. Echo Sight should reveal how.'),
    });
    this.questPoint('i_attunement', v(0, 1.6, 65), 'Attune to the Core', ['stage:m4_vault:upgrade'], { radius: 2.6 });
    this.addInteractable({
      id: 'i_hidden_door', kind: 'door', pos: v(-10.2, 1.6, 24), radius: 3, prompt: 'Enter the singing wall', hidden: true,
      available: () => !!this.hiddenCollider,
      onReveal: () => {
        this.hiddenWall.material = getMaterial('emit_violet');
      },
      onInteract: () => {
        this.openHidden();
        rt()?.emitInteract('i_hidden_door');
      },
    });
    this.addInteractable({
      id: 'i_hidden_pedestal', kind: 'inspect', pos: v(-16, 1.4, 24), radius: 2.4, prompt: 'Take what Maren left behind',
      available: () => rt()?.check('stage:sq_hidden_vault:claim') ?? false,
      lockedReason: () => (rt()?.check('quest:sq_hidden_vault:done') ? null : 'An echo hums here, waiting for someone who was asked to come.'),
      onInteract: () => rt()?.emitInteract('i_hidden_pedestal'),
    });
    this.addInteractable({ id: 'i_save_vault', kind: 'save', pos: v(3.8, 1.3, 2.5), radius: 2, prompt: 'Use save terminal', onInteract: () => undefined });
    this.markers.guardian_rise = v(0, 0, 78);
    void ctx;
  }

  private tune(i: number) {
    const r = this.resonators[i];
    r.value = (r.value % 4) + 1;
    this.rtRef?.sfx('echo', r.pos);
    this.paintResonators();
    if (this.resonators.every((x, k) => x.value === GLYPH_TARGET[k])) {
      this.openLock(false);
      this.rtRef?.setFlag('vault_lock_open');
      this.rtRef?.sfx('door', this.lockDoor.position);
      this.rtRef?.hint('The resonance lock disengages.');
    }
  }

  private paintResonators() {
    this.resonators.forEach((r, i) => {
      const ok = r.value === GLYPH_TARGET[i];
      r.ring.forEach((seg, k) => (seg.material as THREE.MeshBasicMaterial).color.set(k < r.value ? (ok ? 0x52ff9a : 0xa47dff) : 0x202030).multiplyScalar(k < r.value ? 2.4 : 1));
    });
  }

  private openLock(instant: boolean) {
    this.lockOpen = true;
    if (this.lockCollider) {
      this.rtRef?.removeCollider(this.lockCollider);
      this.lockCollider = null;
    }
    if (instant) {
      this.lockDoor.children.forEach((c) => (c.position.x += Math.sign(c.position.x) * 3));
      this.resonators.forEach((r, i) => (r.value = GLYPH_TARGET[i]));
    }
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
    if (rt.flag('vault_lock_open')) this.openLock(true);
    if (rt.check('quest:sq_hidden_vault:done') || rt.check('stage:sq_hidden_vault:claim')) this.openHidden();
    if (rt.revealed('i_hidden_door')) this.hiddenWall.material = getMaterial('emit_violet');
    this.paintResonators();
    rt.vfx.addEmitter(new THREE.Vector3(0, 0.5, 67), 'aether', 10, 2);
    rt.vfx.addEmitter(new THREE.Vector3(0, 0.3, 22), 'aether', 4, 9);
    if (rt.flag('vault_escaped')) {
      this.blastOpen = true;
      if (this.blastCollider) {
        rt.removeCollider(this.blastCollider);
        this.blastCollider = null;
      }
    }
  }

  update(dt: number, rt: ZoneRuntime) {
    super.update(dt, rt);
    const t = this.time;
    this.attuneCore.rotation.y += dt * 0.6;
    this.attuneCore.scale.setScalar(1 + Math.sin(t * 2) * 0.06);
    // Lock door slides open.
    if (this.lockOpen) {
      for (const c of this.lockDoor.children) {
        const target = Math.sign(c.position.x) * (Math.abs(c.position.x) < 2 ? 4.5 : 4.5);
        c.position.x += (target - c.position.x) * Math.min(1, dt * 0.8);
      }
    }
    // Vents: telegraph glow, then a lethal pulse.
    for (const v of this.vents) {
      const c = (t + v.offset) % 4.2;
      const active = c > 2.4 && c < 3.6;
      const warn = c > 1.6 && c <= 2.4;
      const m = v.mesh.material as THREE.MeshBasicMaterial;
      m.opacity = active ? 0.55 + Math.sin(t * 40) * 0.1 : warn ? 0.12 + Math.sin(t * 20) * 0.08 : 0;
      v.hitCd -= dt;
      if (active && v.hitCd <= 0 && v.box.containsPoint(rt.playerPos.clone().setY(rt.playerPos.y + 0.4))) {
        v.hitCd = 0.9;
        rt.damagePlayer(14, 'vent', new THREE.Vector3(rt.playerPos.x, 0, v.box.getCenter(new THREE.Vector3()).z));
        rt.vfx.sparks(rt.playerPos.clone().setY(rt.playerPos.y + 0.6), new THREE.Vector3(0, 1, 0), 12, 0xc8a8ff, 5);
      }
      if (active && Math.random() < 0.3) rt.vfx.embers(new THREE.Vector3((Math.random() - 0.5) * 18, 0.2, v.box.getCenter(new THREE.Vector3()).z), 1, 0xa47dff, 0.4, 3);
    }
    // Blast door cycle during the Guardian encounter.
    if (rt.flag('blastdoor_cycling') && !this.blastOpen) {
      this.blastT += dt;
      const k = Math.min(1, this.blastT / DOOR_TIME);
      this.blastLights.forEach((l, i) => (l.material as THREE.MeshBasicMaterial).color.set(i < Math.floor(k * 8) ? 0x52ff9a : 0xff3a2e).multiplyScalar(2));
      if (k >= 1) {
        this.blastOpen = true;
        if (this.blastCollider) {
          rt.removeCollider(this.blastCollider);
          this.blastCollider = null;
        }
        rt.sfx('door', this.blastDoor.position);
        rt.hint('The blast door is open. Get through!');
      }
    }
    if (this.blastOpen && this.blastDoor.position.y < 9.5) this.blastDoor.position.y = Math.min(9.5, this.blastDoor.position.y + dt * 3);
    // Lights breathe slightly.
    this.glowLights.forEach((l, i) => l && (l.intensity *= 1 + Math.sin(t * 1.5 + i) * 0.002));
  }
}
