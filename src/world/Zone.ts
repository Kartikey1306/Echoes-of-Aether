import * as THREE from 'three';
import type { Physics } from '../physics/Physics';
import type { RenderSystem } from '../render/Renderer';
import type { Weather } from '../render/Weather';
import { Data, type ZoneMeta } from '../game/Data';
import { LevelBuilder } from './kit/LevelBuilder';

// Zone framework: a zone builds its geometry and registers gameplay objects
// (spawns, exits, triggers, interactables, encounters, collectibles, NPCs, markers).

export interface SpawnPoint { pos: THREE.Vector3; yaw: number }

export interface Interactable {
  id: string;
  kind: 'inspect' | 'npc' | 'pickup' | 'door' | 'terminal' | 'save' | 'exit' | 'puzzle' | 'ladder' | 'collectible' | 'cache' | 'lore';
  pos: THREE.Vector3;
  radius: number;
  prompt: string | (() => string);
  /** Visible/usable only after Echo Sight reveals it. */
  hidden?: boolean;
  /** Extra availability condition (quest stage, flags...). */
  available?: () => boolean;
  /** Short explanation shown when unavailable but in range. */
  lockedReason?: () => string | null;
  onInteract: () => void | Promise<void>;
  object?: THREE.Object3D;
  /** Visual shown once a hidden interactable has been revealed by Echo Sight. */
  revealObject?: THREE.Object3D;
  /** Called once when revealed (e.g. remove a blocking collider). */
  onReveal?: () => void;
  /** Prevents re-use (pickups). */
  consumed?: boolean;
  /** Character-facing height for prompts. */
  height?: number;
}

export interface Trigger {
  id: string;
  box: THREE.Box3;
  once?: boolean;
  fired?: boolean;
  inside?: boolean;
  available?: () => boolean;
  onEnter?: () => void;
}

export interface Exit {
  id: string;
  target: string;
  entry: string;
  pos: THREE.Vector3;
  radius: number;
  prompt: string;
  /** Automatic on entering the radius (tunnels) vs. interact (doors, lifts). */
  auto?: boolean;
  requires?: () => boolean;
  lockedText?: string;
}

export interface EnemyPlacement { type: string; pos: THREE.Vector3; yaw?: number; variant?: string }

export interface EncounterDef {
  id: string;
  /** 'auto': spawns on zone load unless defeated; 'trigger:<id>': spawns when trigger fires; 'quest': spawned by quest actions. */
  spawn: 'auto' | 'quest' | `trigger:${string}`;
  waves: EnemyPlacement[][];
  /** Arena centre/radius for leash and reset. */
  arena?: { center: THREE.Vector3; radius: number };
  /** Respawn every time the zone loads even if defeated (ambient patrols). */
  respawn?: boolean;
  /** Called when cleared. */
  onCleared?: () => void;
}

export interface CollectiblePlacement { id: string; pos: THREE.Vector3 }

export interface NpcPlacement { id: string; pos: THREE.Vector3; yaw: number; behaviour: string; route?: THREE.Vector3[]; dialogue: string; echoOnly?: boolean; available?: () => boolean }

export interface ZoneMapInfo {
  /** World XZ rectangle covered by the map image. */
  min: THREE.Vector2;
  max: THREE.Vector2;
  /** Simple map drawing primitives (rects of walkable space / buildings). */
  shapes: { kind: 'floor' | 'block' | 'water' | 'road'; x: number; z: number; w: number; d: number; rot?: number }[];
  labels: { text: string; x: number; z: number }[];
}

export interface BuildContext {
  physics: Physics;
  rs: RenderSystem;
  progress: (frac: number, label: string) => Promise<void>;
  quality: { effects: 'low' | 'medium' | 'high'; textures: 'low' | 'medium' | 'high' };
  /** Read-only progression flags (to build doors open/closed etc.). */
  flag: (name: string) => boolean;
}

export abstract class Zone {
  readonly id: string;
  readonly meta: ZoneMeta;
  readonly scene = new THREE.Scene();
  readonly root = new THREE.Group();
  builder!: LevelBuilder;
  spawns: Record<string, SpawnPoint> = {};
  exits: Exit[] = [];
  triggers: Trigger[] = [];
  interactables: Interactable[] = [];
  encounters: EncounterDef[] = [];
  collectibles: CollectiblePlacement[] = [];
  /** Quest/world item pickups (persisted as collected by id). */
  itemPickups: { id: string; item: string; pos: THREE.Vector3; cond?: string[]; prompt?: string }[] = [];
  npcs: NpcPlacement[] = [];
  markers: Record<string, THREE.Vector3> = {};
  map!: ZoneMapInfo;
  weather: Weather | null = null;
  sun: THREE.DirectionalLight | null = null;
  /** Below this height the player is considered out of bounds. */
  killY = -20;
  /** Horizontal bounds (failsafe). */
  bounds = new THREE.Box3(new THREE.Vector3(-500, -100, -500), new THREE.Vector3(500, 200, 500));
  /** Music track key. */
  music = 'explore';
  ambience = 'rain_city';
  /** Whether the camera should use indoor (tighter) collision settings. */
  indoor = false;
  /** Colour grade for this zone. */
  grade: Parameters<RenderSystem['setGrade']>[0] = {};
  time = 0;
  /** Hidden objects (revealed by Echo Sight) with their visuals. */
  echoObjects: { id: string; object: THREE.Object3D; pos: THREE.Vector3 }[] = [];

  constructor(id: string) {
    this.id = id;
    this.meta = Data.zones[id];
    this.scene.name = 'zone:' + id;
    this.root.name = 'zone-root:' + id;
    this.scene.add(this.root);
  }

  abstract build(ctx: BuildContext): Promise<void>;

  /** Per-frame zone logic (animated props, puzzles, hazards). */
  update(dt: number, _ctx: ZoneRuntime): void {
    this.time += dt;
  }

  /** Called after the zone is entered and the player placed. */
  onEnter(_ctx: ZoneRuntime): void {}

  addInteractable(i: Interactable) {
    this.interactables.push(i);
    return i;
  }

  /** Interactable that simply reports `interact:<id>` to the quest system while `cond` holds. */
  questPoint(id: string, pos: THREE.Vector3, prompt: string, cond: string[] | null, opts: Partial<Interactable> = {}) {
    return this.addInteractable({
      id,
      kind: 'inspect',
      pos,
      radius: 2.2,
      prompt,
      available: () => !cond || cond.every((c) => this.rtRef?.check(c) ?? false),
      onInteract: () => this.rtRef?.emitInteract(id),
      ...opts,
    });
  }

  rtRef: ZoneRuntime | null = null;

  bindRuntime(rt: ZoneRuntime) {
    this.rtRef = rt;
  }

  findInteractable(id: string) {
    return this.interactables.find((i) => i.id === id) ?? null;
  }

  /** Resolve a marker id (interactable, trigger, exit, npc, named point) to a world position. */
  resolveMarker(id: string): THREE.Vector3 | null {
    const i = this.findInteractable(id);
    if (i && !i.consumed) return i.pos;
    const t = this.triggers.find((x) => x.id === id);
    if (t) return t.box.getCenter(new THREE.Vector3());
    const e = this.exits.find((x) => x.id === id);
    if (e) return e.pos;
    if (id.startsWith('npc_')) {
      const n = this.npcs.find((x) => x.id === id.slice(4));
      if (n) return n.pos;
    }
    const c = this.collectibles.find((x) => x.id === id);
    if (c) return c.pos;
    return this.markers[id] ?? null;
  }

  dispose() {
    this.weather?.dispose();
    this.scene.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh || (o as THREE.Sprite).isSprite) {
        m.geometry?.dispose();
        const mats = Array.isArray(m.material) ? m.material : [m.material];
        for (const mat of mats) {
          // Shared library materials are cached; only dispose per-object ones.
          if (mat && (mat as THREE.Material).userData?.shared !== true && !(mat as THREE.Material).name?.match(/^(concrete|asphalt|paving|curb|plaster|brick|metal|rust|grate|tile|floor|panel|glass|rubber|wood|tarp|rock|vehicle|cable|black|emit_|screen|aether|water)/)) {
            (mat as THREE.MeshStandardMaterial).map?.dispose();
            mat.dispose();
          }
        }
      }
    });
    this.scene.clear();
  }
}

/** What zones can access at runtime. */
export interface ZoneRuntime {
  playerPos: THREE.Vector3;
  check(cond: string): boolean;
  revealed(id: string): boolean;
  flag(name: string): boolean;
  setFlag(name: string, v?: boolean): void;
  emitInteract(id: string): void;
  toast(text: string): void;
  sfx(id: string, pos?: THREE.Vector3): void;
  damagePlayer(amount: number, source: string, from?: THREE.Vector3): void;
  echoActive: boolean;
  shake(amount: number): void;
  vfx: import('../vfx/VFX').VFX;
  /** Remove a collider (doors opening). */
  removeCollider(c: import('@dimforge/rapier3d-compat').Collider): void;
  playerVelocity: THREE.Vector3;
  /** Spawn a quest encounter by id (zone scripted events). */
  spawnEncounter(id: string): void;
  isDefeated(id: string): boolean;
  hint(text: string): void;
  giveItem(id: string, qty?: number): void;
  playDialogue(id: string): void;
  /** Scripted traversal (ladders, drops): move the player through points while playing a clip. */
  traverse(points: THREE.Vector3[], clip: string, duration: number, endYaw?: number): Promise<void>;
}
