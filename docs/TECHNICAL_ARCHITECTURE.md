# Echoes of Aether — Technical Architecture (Unity port)

Status date: 2026-10-03.

| Fact | Value |
|---|---|
| Project | `unity/EchoesOfAether` |
| Engine | Unity 6000.3.25f1 (6.3 LTS) |
| Rendering | Universal Render Pipeline 17.3 |
| Language | C# 9 in `namespace EOA` |
| Code size | 88 runtime C# files (about 24,700 lines) under `Assets/Scripts`; 7 editor files (about 1,700 lines) under `Assets/Editor` |

The TypeScript prototype in `src/` is the behavioural reference: tuning numbers, data and level layouts are ported
from it (see `PROJECT_ARCHITECTURE.md`).

Build state:

* A batch-mode run of the project setup on 2026-10-03 compiled the project in the real editor with 0 errors and 4
  warnings, and completed every setup step.
* The offline compile check (`tools/unitycheck/check.py`) is the fast pre-check. At the final check (after all
  zones were written) it compiled Assembly-CSharp (88 files) in the editor and player configurations, and
  Assembly-CSharp-Editor (7 files), with 0 errors and 0 warnings.

## 1. Runtime overview

```
Boot.unity
 └─ GameManager (DontDestroyOnLoad, execution order -1000)
     ├─ Actors/                 Hero ×2 (Kael, Giva), created when a game starts, re-placed on every zone load
     ├─ CombatSystem            targeting queries, damage application, projectile pool
     ├─ VfxManager              pooled particles, rings, slash arcs, lights
     ├─ AudioManager, VoiceOver
     ├─ CameraRig → Main Camera (AudioListener)
     ├─ PostFx                  global URP Volume
     ├─ MenuStage               3D menu backdrop (500 m below the world)
     └─ UI                      UIDocument + UIManager (HUD, dialogue, screens, loading, debug)
ZoneRuntime (plain C# object, G.World)
 └─ Zone_<id> root GameObject  built procedurally by a ProceduralZone subclass
```

### Boot

`Assets/Scenes/Boot.unity` is created by the project setup and contains only a `GameManager` object. Its lighting is
fully realtime, with the Sky material as the skybox. It is the only scene in Build Settings.

`Assets/Scripts/Game/Bootstrap.cs` is a safety net: `[RuntimeInitializeOnLoadMethod(AfterSceneLoad)]` creates a
`GameManager` when Play is pressed in a scene without one.

`GameManager` is a partial class in three files:

| File | Contents |
|---|---|
| `GameManager.cs` | `Awake`: registers `G.Manager`, `DontDestroyOnLoad`, loads data (`GameData.EnsureLoaded`), creates `Settings`, `SaveSystem`, `GameInput` (applying saved binding overrides), a default `GameState`, `Inventory`, `Progression`, `DialogueSystem` and `QuestSystem`, then calls `InitRuntime`. Also `SetPaused` (time scale 0, cursor, audio duck). |
| `GameManager.Runtime.cs` | `InitRuntime` creates every runtime service listed above and wires bus events. Also: modes (Boot, Menu, CharSelect, Loading, Play, Credits); `ShowMenu`; `NewGame`; `LoadFromEnvelope`; `RespawnAtCheckpoint`; `LoadZone` / `ChangeZone`; hero placement; the data-driven action runner `RunActions`; `PlayDialogue` (interactive, radio or cinematic); NPC conversations; scripted traversal; pickups and powerups; character swap; credits; the objective-marker resolver; and the frame loop (hitstop time scale, playtime, powerup timers, interaction, swap, quick slots, zone tick, combat state, music mood). |
| `GameManager.Api.cs` | Operations for the UI and tools: appearance (lazy `AppearanceStore`), `CanSaveNow`, `ManualSave`, `Autosave`, `UsePowerupItem`, `TrackQuest`, `RetryFromCheckpoint`, `LoadLastSave`, `ContinueGame`, `HasAnySave`. |

### Service locator and event bus

`G` (`Assets/Scripts/Game/G.cs`) holds the running services, so modules never search the scene in hot paths:

| Member | Holds |
|---|---|
| `G.Manager`, `G.Input`, `G.Settings`, `G.Saves` | Core services |
| `G.Audio`, `G.Vfx`, `G.World`, `G.Presentation` | Facade interfaces: `IAudio`, `IVfx`, `IWorld`, `IPresentation` from `Core/Contracts.cs` |
| `G.State`, `G.Inventory`, `G.Progression`, `G.Quests`, `G.Dialogue`, `G.Powerups` | Shortcuts through the manager |

`Bus` (`Assets/Scripts/Core/Bus.cs`) is a typed static event bus:

* `Bus.On<T>(handler)` returns an unsubscribe action. `Bus.Emit<T>(struct)` dispatches over a copy of the handler
  list and logs handler exceptions without breaking the loop.
* Event structs include:
  * enemy events: `EnemyKilled`, `EnemyDamaged`, `EnemyAggro`
  * player events: `PlayerDamaged`, `PlayerDied`, `PlayerRespawned`, `PlayerLanded`
  * progression events: `AbilityUsed`, `AbilityUnlocked`, `ItemAdded`, `ItemRemoved`, `PowerupActivated`,
    `PowerupExpired`, `CollectibleFound`
  * world events: `Interacted`, `TriggerEnter`, `TriggerExit`, `ZoneEntered`, `ZoneLeaving`, `FlagSet`
  * quest and dialogue events: `QuestStarted`, `QuestStage`, `QuestObjective`, `QuestCompleted`, `DialogueStarted`,
    `DialogueEnded`, `DialogueChoiceMade`, `CinematicStarted`, `CinematicEnded`, `Talked`, `PickedUp`
  * game events: `CharacterSwapped`, `SaveWritten`, `SaveFailed`, `CheckpointReached`, `CombatState`, `BossPhase`,
    `SettingsChanged`, `Toast`, `Lightning`
  * feedback events: `ShakeRequested`, `HitstopRequested`, `DialogueLineShown`
* `Bus.Clear()` runs when the GameManager is destroyed.

## 2. Data layer

* **Files.** Game data is JSON in `Assets/Resources/Data/`: `items`, `powerups`, `abilities` (abilities and the skill
  tree), `enemies`, `quests`, `dialogue`, `speakers`, `zones`, `collectibles`, `hints`, and `locale/en.json`.
* **Source of truth.** The files are byte-identical to the prototype's `src/data`. The validator checks this parity.
* **Loading.** `GameData` (`Assets/Scripts/Data/GameData.cs`) loads them once through `Resources.Load<TextAsset>`
  into typed definitions (`ItemDef`, `QuestDef`, `DialogueDef`, and so on) with dictionaries by id.
* **Deserialisation.** Uses **Newtonsoft.Json** (`com.unity.nuget.newtonsoft-json` 3.2.2):
  * camelCase contract resolver, string enums, missing members ignored
  * `ActionDef` keeps the raw `JObject` of an action (`{ "do": ..., ... }`) with typed accessors
  * `QuestRefConverter` maps the JSON `false` "no quest" value to null
* **Localisation.** `GameData.T(key)` and `U.T(key)` look up `locale/en.json`.

**Game state.** `GameState` and `GameStateData` (`Game/GameState.cs`) hold the serialisable progression of one
playthrough:

* hero, zone, entry, position, yaw, checkpoint
* quests (status, stage, progress) and the tracked quest
* flags (`JToken`), inventory counts
* unlocked abilities, skills
* collected, defeated and revealed ids, lore
* stats, and both heroes' appearance

`GameState.Check(cond)` evaluates the condition grammar shared by quests, dialogue, exits and interactables:

```
flag:x   quest:id:none|active|done   stage:quest:stage   item:id[>=n]
char:c   ability:a   revealed:id   collected:id          (prefix ! negates)
```

## 3. Game systems

| System | File | Notes |
|---|---|---|
| Quests | `Game/Quests.cs` | Bus events advance objectives: `Interacted` and `PickedUp` → interact, `EncounterCleared` → kill, `ItemAdded` → collect, `TriggerEnter` → reach, `ZoneEntered` → zone, `FlagSet` → flag, `Talked` → talk. Stage transitions and their actions run through a **serial async queue**, so quest-triggered dialogue and cinematics never overlap. Objectives that are already satisfied complete on stage entry (`EvaluateInstant`). `Refresh()` re-evaluates after loads and zone changes. |
| Actions | `GameManager.RunAction` | `dialogue`, `cinematic`, `encounter` (also sets flag `enc_<id>` so it respawns after loads), `despawn`, `spawnPickup`, `hint`, `give`, `take`, `setFlag`, `startQuest`, `unlock`, `autosave`, `credits`. On zone load, `RestoreStageWorldActions` re-runs the idempotent world actions (`encounter`, `spawnPickup`) of every active stage. |
| Dialogue | `Game/Dialogue.cs` | Branch nodes (`branch` with `if` conditions), node conditions with `else`, choices with conditions and actions, node actions. `active` / `partner` speakers resolve to the current heroes. `LinearLines` resolves a dialogue without presenting it (cinematics, lore). Presentation goes through `IDialogueView` (`UI/DialogueView.cs`). Ending an NPC dialogue emits `Talked`. |
| Inventory | `Game/Inventory.cs` | Stack limits; lore items add their lore id; emits `ItemAdded` / `ItemRemoved`. |
| Progression | `Game/Inventory.cs` (`Progression`, `CharStats`) | Skill-tree purchase (fragments first, cores broken into 3 fragments) and derived per-hero stats from skills and upgrades. |
| Powerups | `Game/Powerups.cs` | Timed buffs with `Buffs` multipliers (damage, attack speed, dash distance, reveal); shield restore is instant. |
| Settings | `Game/Settings.cs` | Six sections. `Sanitize` clamps every value and repairs missing sections. `Parse` reads untrusted JSON leniently (bad fields fall back to defaults). `Update(section, change)` validates, persists and emits `SettingsChanged`. Graphics presets. Difficulty modifiers. |
| Appearance | `Game/Appearance.cs`, `Actors/CharacterModel.cs` (`AppearanceStore`) | Per-hero look, sanitised from untrusted data; persisted to `appearance.json` and inside saves. |
| Cinematics | `Game/Cinematics.cs` | See §7. |
| Rendering config | `Game/Rendering.cs` | `GraphicsConfig.Apply` (URP render scale, shadow distance, MSAA, mip limit, LOD bias, far clip, AA mode, vsync and frame cap, fullscreen except on WebGL); `PostFx`; `ThumbnailCapture` (256×144 JPEG for save slots). |

## 4. Saving

`Game/SaveSystem.cs`.

**Files** (under `Application.persistentDataPath`):

| File | Content |
|---|---|
| `saves/slot{1..3}.json` | Main save per slot |
| `saves/slot{n}.bak.json` | Rolling backup per slot |
| `settings.json` | Settings |
| `appearance.json` | Hero appearance for menus and new games |

**Envelope.**

```
{ magic: "EOA-SAVE", version: 1, slot, kind: manual|auto|checkpoint, timestamp (UTC ISO),
  playtime, zone, character, mission, thumbnail (base64 JPEG), checksum, state, settings }
```

`checksum` is the **CRC32** (hex) of the `state` JSON exactly as stored.

**Write path** (`Write`):

1. Refuse if another write is in progress.
2. Deep-copy the state and validate it (`GameState.Validate`: schema version, known hero, zone, quest, item ids,
   sane counts, finite position).
3. Build the envelope.
4. If the current main file is valid, copy it to the backup first.
5. Write the new main file **atomically** (`SafeFile.WriteAtomic`): write a temp file, read it back and compare,
   then `File.Replace`. On file systems without replace (WebGL IDBFS) it copies over the verified temp file instead.
6. Parse the written file again (post-write verification).
7. Emit `SaveWritten` or `SaveFailed`.

**Read path.**

* `Info(slot)` parses the main file and the backup and classifies the slot as `ok`, `empty`, `corrupt` or
  `recovered` (main damaged, backup valid).
* `Parse` rejects files that are not JSON, have the wrong magic, are a newer version, fail the checksum, or fail
  state validation.
* `Latest()` picks the newest loadable envelope across slots (main or backup).
* `Recover(slot)` copies the backup over a damaged main file.

**WebGL.** `persistentDataPath` lives in IndexedDB. `SafeFile.Flush` calls `EOA_SyncFS`
(`Assets/Plugins/WebGL/SyncFS.jslib`, `FS.syncfs`) after every write and delete, so saves survive closing the tab.

**When saves happen.** See `GDD.md` §11. A thumbnail is captured by rendering the game camera into a 256×144 render
texture.

## 5. Input

`Core/GameInput.cs` builds the whole Input System setup in code: one `InputActionAsset` with a **Gameplay** map and a
**UI** map, no `.inputactions` asset.

* **Gameplay map.**
  * `move` (WASD and arrow composites, left stick with deadzone) and `look` (mouse delta, right stick)
  * 22 buttons: jump, dash, light, heavy, bolt, ability, ultimate, interact, swap, lockon, pause, inventory, map,
    journal, skills, quick1–5, skip, debug
  * Bindings are grouped `KeyboardMouse` / `Gamepad`
* **UI map.** `navigate`, `submit`, `cancel`, `tabPrev`, `tabNext`.
* **Query API.**
  * `Pressed`, `Held`, `Released`, `HoldTime(action)`
  * `MoveVector`, `LookDelta(padSpeed)`: mouse pixels × 0.12, or stick × 220°/s × pad speed
  * `Label(action)` gives the binding label for the current device
  * `UsingGamepad` is tracked from the last performed action
  * `Rumble(low, high, seconds, enabled)`
  * `LockCursor`
* **Rebinding.** `StartRebind(action, gamepad, done)` uses `PerformInteractiveRebinding`. It excludes mouse position
  and delta, cancels on Esc, and restricts to keyboard and mouse or to gamepad. Conflicts are swapped. Overrides are
  saved with `SaveBindingOverridesAsJson` into `settings.json` and loaded at boot.
* **Gating.** Gameplay input is disabled during loading, menus, dialogue and cinematics (`EnableGameplay(false)`).
* **Project setting.** The setup sets Active Input Handling to "Both". The game itself uses only the Input System.

## 6. World

### Zone loading (`World/ZoneRuntime.cs`, implements `IWorld`)

`ZoneRuntime.Load(zoneId)`:

1. Unloads the previous zone.
2. If an additive scene `Zone_<id>` is in Build Settings and contains a `ZoneDefinition`, loads it. Scenes are an
   optional override; none exist today.
3. Otherwise, the normal path: creates `Zone_<id>`, adds a `ZoneDefinition`, instantiates the zone class from
   `ZoneRegistry`, and `await`s its `Build`, reporting progress to the loading screen.
4. Bakes a **runtime NavMesh** over the zone's physics colliders on the World, Default and IgnoreCamera layers
   (`NavMeshSurface`, AI Navigation 2.0). If the bake fails, enemies steer without it. Zone scripts call
   `RefreshNavMesh()` (`NavMeshSurface.UpdateNavMesh`) after a door opens or a barrier is removed, so enemies can path
   through the new opening.
5. If neither path works, builds a fallback test zone (plane and sun) and logs a warning.
6. Spawns NPCs (with `npc_<id>` talk interactables), collectibles not yet collected (hidden ones stay invisible until
   revealed), quest item pickups, registered interactables, and encounters (`auto`, or `quest` when flag `enc_<id>`
   is set and not defeated).
7. Builds the zone map data.
8. Calls `ZoneScript.Bind` and `OnLoaded`.

`GameManager.LoadZone` then places the heroes (saved position, checkpoint, or the named spawn snapped to the ground),
records a checkpoint, starts music and ambience, emits `ZoneEntered`, refreshes quests, calls `OnEnter`, and plays
the intro cinematic on a new game or autosaves otherwise.

**Per frame** (`ZoneRuntime.Tick`):

* Echo reveal (§6, "Echo Sight").
* Zone script tick and NPC ticks.
* Auto-collect pickups within 1.5 m.
* Box triggers: enter and exit events, `once`, conditions, trigger-spawned encounters.
* **Exits.** Walk-in exits fire automatically. Others become the interaction candidate, with a locked text when
  their requirements fail. There is a 3 s cooldown.
* **Interaction candidate.** The nearest available interactable within its radius, using horizontal distance plus
  half the height difference. Hidden ones count only once revealed. Locked ones show their reason.

**Encounters** advance wave by wave as enemies die (`OnEnemyKilled`) and emit `EncounterCleared`, which completes
`kill` objectives and marks the encounter defeated.

**Attack tokens.** `RequestAttackToken` allows at most `MaxTokens` enemies to attack at once (1, 2 or 3 by
difficulty).

### Procedural zones

* **`ZoneRegistry`** maps zone id → zone class explicitly, without reflection, so IL2CPP or managed stripping never
  removes a zone.
* **`ProceduralZone`** (`World/ProceduralZone.cs`, base `ZoneScript`) is the authoring API used by
  `World/Zones/<Name>Zone.cs`:
  * `BuildZone()` (async)
  * `ZoneSettings(killY, indoor, music, ambience)`, `SetAtmosphere`, `MakeWeather`
  * `Spawn`, `Exit`, `Trigger`, `Encounter(... Wave(E(type, x, y, z)))`, `Collectible`, `ItemPickup`, `Npc`,
    `Marker`
  * `MapBounds`, `MapShape`, `MapLabel`
  * `Interactable` (with closures for availability, prompt, use, locked reason, Echo reveal object), `QuestPoint`,
    `SaveTerminal`
  * runtime helpers: flags, checks, hints, SFX, shake, `DamagePlayer`, `Traverse`, `Emitter`
  * `ZoneScript` virtuals: `OnLoaded`, `OnEnter`, `Tick`, `OnFlag`, `OnRevealed`, `OnEncounterCleared`,
    `OnTrigger`, `ResolveMarker`, and more
* **`ProtoSpace`** (`World/Kit/ProtoSpace.cs`) converts the prototype's right-handed three.js design space to Unity:
  * `V(x, y, z) = (-x, y, z)` (the X axis is mirrored)
  * yaw → `-yaw` in degrees; Euler conversions
  * light intensity × 1/π
  * Zone code is written in **prototype coordinates**, so layouts read side by side with `src/world/zones/*.ts`.
* **`LevelKit`** (`World/Kit/LevelKit.cs`) is the static level builder, ported from `LevelBuilder.ts`:
  * Primitives: `Box`, `BoxMin`, `Cyl`, `Stairs`, `Ramp`, `AddMesh`.
  * World-scale UVs (1 UV = 1 m).
  * Pieces are **merged per material and per 32 m cell** into a few meshes on `Finish()`.
  * Colliders are separate static objects on the World layer. Invisible walls (`Wall`) use the IgnoreCamera layer,
    which blocks characters but not the camera or projectiles.
  * Also: `Prop` (Blender prefab by name), point and spot lights with prototype falloff compensation and a light
    budget of 24, glow decals and sprites, signs.
* **`EnvMaterials` / `EnvProps`.** Material and prefab libraries for the Blender kit, with flat-colour and grey-box
  fallbacks. See `ART_BIBLE.md` §5.
* **`Atmosphere` / `Weather`.** Sky, fog, ambient, sun, reflection probe and grade; rain, splashes and lightning.
  See `ART_BIBLE.md` §4.

**Zone port status** (final check, 2026-10-03; see `GDD.md` §8):

* All six zone classes are written (`PlazaZone`, `MetroZone`, `FacilityZone`, `VaultZone`, `RooftopsZone`,
  `CoreZone`). They build the prototype layouts with the Blender kit, and the validator finds every data reference
  in them.
* They are not yet play-verified.
* `node tools/validation/validate_unity.mjs` reports the current state.

### Echo Sight

`ZoneRuntime.EchoReveal(center, range, duration)` starts a reveal. Each frame of an active reveal (`UpdateEcho`)
permanently reveals:

* hidden interactables and pickups within range of the player
* registered reveal objects, which are shown
* hide-on-reveal objects, which are hidden

Each reveal is stored in `GameState.Revealed` and raises `OnRevealed`. Echo-only NPCs are visible while a reveal is
active. `IWorld.EchoActive` makes phased Stalkers visible and targetable. The Echo Fragment powerup keeps re-pulsing
a 24 m reveal while active.

### Other world actors

| Actor | File | Behaviour |
|---|---|---|
| NPCs | `World/Npc.cs` | Human NPCs from `Resources/Characters/<Name>`; BOLT as a `RobotRig`. Echo tint, conversation turning, head glance, reactions. |
| Pickups | `World/Pickup.cs` | Procedural visuals with bob, spin, halo and light; kinds fragment, recording, cache, quest, powerup, item. |
| Menu stage | `World/MenuStage.cs` | Dark floor disc, two emissive-ring pads, key, fill and rim lights, and both hero models, placed at y = -500 so gameplay never sees it. The doc comment calls it "a rain-swept rooftop", but the code builds only the floor, pads and lights. |

## 7. Actors, combat, enemies, cinematics

### Heroes and camera

**`Actors/Hero.cs`** is the same component for the player and the companion.

* **Body.** `CharacterController` (radius 0.36 m, step 0.42 m, slope 50°) plus the character prefab
  (`CharacterModel` and a humanoid Animator).
* **States.** Move, Attack, Dash, Ability, Hit, Dead, Scripted, Aim, Ult.
* **Interfaces.** Implements `IDamageable` and `IHeroStatus`.
* **Details.** Combat rules are in `GDD.md` §5; animation wiring in `ANIMATION_BIBLE.md` §1.6.

**`Actors/CameraRig.cs`** is a third-person orbit camera:

| Parameter | Value |
|---|---|
| Distance | 4.3 m |
| Shoulder offset | 0.42 m |
| Pivot height | 1.55 m |
| Base field of view | 62° |
| Near / far clip | 0.08 m / 400 m (far clip later set by the view-distance setting) |

It provides smoothed focus, sphere-cast collision, aim mode, lock-on framing, sprint field-of-view kick, combat zoom,
trauma shake scaled by the settings, and a cinematic override `(pos, look, fov)`. It runs at execution order 200.

### Combat

* **`Combat/CombatSystem.cs`.** Physics layers and masks (`CombatLayers`). Queries:
  * `Arc`: cone sweep with a half-angle
  * `Radial`
  * `BestTarget`: score = distance × (1 + 2.2 × angle), with line of sight
  * `ArcDamage` and `RadialDamage`: hit sets, knockback, damage-dealt callbacks

  It also applies hits (`Apply` returns the damage that landed), raises an `OnHit` event, `Shake` and `Hitstop`
  (through the bus), and checks line of sight.
* **`CombatSystem.Projectiles.cs`.** A pooled projectile system (`ProjectileSpec`: speed, homing target, turn rate,
  team, poise, size) and beams (the Guardian laser).
* **`Combat/CombatMath.cs`.** Pure math (angles, arcs, damping, steering) shared by heroes, enemies and the EditMode
  tests.

### Enemies

`Assets/Scripts/Enemies/`:

* **`Enemy`** is the base class:
  * perception (sight range and cone with line of sight), alert sharing per encounter, leash and return, stuck
    recovery
  * poise and stagger, attack tokens, death, drops, events
  * movement: NavMeshAgent-constrained steering on a NavMesh, a `CharacterController` otherwise, free movement for
    flyers
  * `Enemy.FreezeAll` for cinematics
* **`EnemyHost`** is the single adapter to game services.
* **`EnemyFactory`** creates `drone`, `sentinel`, `warden`, `stalker`, `guardian` and `guardian_vault` from
  `enemies.json`.
* **Visuals.** `RobotRig` (Blender FBX or procedural fallback, `RobotBodies.cs`), animated by `RobotAnimator` and
  `RobotClips` (see `ANIMATION_BIBLE.md` §2). The FBX contract is `ROBOT_PARTS.md`.

### VFX

`VFX/VfxManager.cs` (implements `IVfx`), `FxKit.cs` (static facade with the prototype's call shapes), `FxMesh.cs`
(cached procedural meshes) and `FxMaterials.cs` (URP materials cloned from templates in `Resources/VFX`). No
allocations during combat.

### Cinematics

`Game/Cinematics.cs`:

* `Register(id, script, finalize)`. Scripts are `async Task` functions over a `CineCtx` API:

  ```
  Shot(posA, lookA, posB, lookB, dur, fov)   Cut   Drift   Wait   Lines(dialogue, from, to)
  Fade   Music   Sfx   Toast   SpawnEcho(prefab, pos, yaw)   Track
  ```

* During a cinematic the runner disables gameplay input, sets the player to scripted, shows letterbox bars, ducks
  audio and freezes enemies. Afterwards it cleans up spawned objects, runs `finalize` and emits `CinematicEnded`.
* **Skipping.** Hold Skip or Pause for 1.1 s, or press once when hold-to-skip is off. The runner sets a flag;
  `CineCtx` throws `CinematicSkipped` at its next await.
* **Fallback.** Without a registered script, `Play(id)` plays the dialogue `<id>_lines` as auto-paced subtitles.
* **NPC conversations.** `FrameConversation` provides an over-the-shoulder two-shot.
* **Registration.** Zone groups register their scripts through the partial `CinematicScripts.RegisterZoneScripts`:
  `World/Zones/Cinematics/{Plaza,Vault,Core}Cinematics.cs`. At the final check these register all five
  cinematics (`cin_intro`, `cin_meeting`, `cin_guardian_reveal`, `cin_hidden_vault`, `cin_ending`).

### UI and audio

See `UI_BIBLE.md` and `AUDIO_BIBLE.md`.

## 8. Physics layers

Created by `ProjectSetup.SetupLayers` and used through `CombatLayers`:

| # | Layer | Use |
|---:|---|---|
| 0 | Default | Treated as world geometry in queries |
| 6 | World | Static level geometry and colliders, props |
| 7 | Player | Heroes |
| 8 | Enemy | Enemies |
| 9 | NPC | NPCs |
| 10 | Interactable | Interaction volumes |
| 11 | Projectile | Projectiles (resolved by queries) |
| 12 | IgnoreCamera | Invisible walls: block characters, not the camera or projectiles |
| 13 | Pickup | Pickups |

Collision matrix:

* Projectiles ignore Projectile, Pickup, Interactable and IgnoreCamera.
* Pickups and Interactables ignore everything except the player.
* `Physics.queriesHitTriggers` is false.

## 9. Editor tooling (`Assets/Editor`)

| Tool | Menu / entry point | What it does |
|---|---|---|
| `Setup/ProjectSetup.cs` | **EOA → Setup Project (All)**; batch `-executeMethod EOA.EditorTools.ProjectSetup.RunAllBatch` | Steps: layers → physics matrix → URP asset and renderer (Forward+, settings in `ART_BIBLE.md` §4; every quality level uses it) → player settings (product name, linear colour, 1920×1080, WebGL Brotli + decompression fallback, data caching, explicit-throw exceptions, minimal managed stripping, Mono on desktop, Input handling "Both", `Assets/link.xml` preserving Assembly-CSharp, Newtonsoft.Json and Unity.AI.Navigation) → shader template materials in `Resources/VFX` and `Resources/Env` → environment library → robot material → characters → UI assets → Boot scene and Build Settings. Writes `ProjectSettings/EOA_Setup.txt` (version 1) only if no step failed. `[InitializeOnLoad]`: runs automatically on the first editor open (not in batch mode) while that marker is missing or older. The batch entry exits with code 1 on failure. |
| `Environment/EnvLibraryBuilder.cs` | EOA → Build Environment Library | Environment kit → URP materials, prefabs with LODs and colliders, runtime manifest (`ART_BIBLE.md` §5) |
| `Characters/CharacterBuilder.cs` | EOA → Build Characters; batch `-executeMethod EOA.EditorTools.CharacterBuilder.BuildAll` | Character FBX → materials, Humanoid avatars, animator controllers, prefabs in `Resources/Characters` (`ANIMATION_BIBLE.md` §1.5–1.6) |
| `UI/UISetup.cs` | Tools → EOA → Setup UI; batch `-executeMethod EOA.EditorTools.UISetup.Run` | TextCore SDF font assets for the 7 OFL font files, rewrites `eoa_fonts.uss` to reference them, panel text settings with glyph fallbacks, `EOA_PanelSettings` (1920×1080, match 0.5, EOA theme), `Resources/UI/UIRefs.asset`, icon checks |
| `Audio/AudioImportPostprocessor.cs` | automatic on import | Audio import settings by folder (`AUDIO_BIBLE.md` §5) |
| `Build/BuildScripts.cs` | EOA → Build → WebGL / macOS; batch `-executeMethod EOA.EditorTools.BuildScripts.WebGL` (or `.MacOS`) | Runs the setup if needed, strips the `EOA_DEV` define, builds the enabled scenes to `<repo>/Builds/WebGL` or `<repo>/Builds/macOS/EchoesOfAether.app`, exits 1 on failure in batch mode (`BUILD_CHECKLIST.md`) |
| `Testing/SmokeTest.cs` + `Scripts/Dev/AutoPilot.cs` | EOA → Test → Smoke Test; batch `-executeMethod EOA.EditorTools.SmokeTest.Run`; players with `-autopilot <dir>` | Added on 2026-10-03. Automated play-through: menu → character select → new game and intro → every zone → a fight. Writes screenshots and `report.json` (errors, warnings, zone load and frame times) to `<repo>/Captures/smoke`; times out after 25 min. At the final check, the first run had captured screenshots of the menus, the intro and every zone, but had not yet written `report.json`. |

## 10. Validation and compile checks

### `tools/validation/validate_unity.mjs`

Prints PASS / WARN / FAIL lines and exits 1 on any FAIL (release blocked). Options: `--compile` also runs the
offline compile check; `--json` gives machine-readable output.

What it checks:

* data parses and matches `src/data`; no duplicate ids
* zones registered and not placeholders; spawns and exits resolve
* collectibles placed
* enemies resolve to factories
* every quest objective, marker, encounter, cinematic and NPC exists in the C# zones
* dialogue ids
* input actions and locale keys in hints
* audio manifest files exist and referenced sounds resolve; no speech-synthesis APIs; voice-over coverage
* animation clips and NPC behaviour clips exist; character FBX present
* portraits and item art (WARN when not rendered); glyph icons
* environment props and materials used by zones exist
* shaders present
* editor pipeline files present
* save system has checksum, backup and atomic writes
* settings sections
* marketing provenance file
* **secret scan** for the DreamLayer key pattern across scripts, data, docs, tools, marketing, Blender scripts and
  builds

Results on 2026-10-03:

| When | Result |
|---|---|
| Mid-port | 17 PASS, 51 WARN, 71 FAIL |
| Final check (all zones written) | **17 PASS, 17 WARN, 5 FAIL** |

The remaining WARNs are missing rendered portraits, loading art and item art, 0 recorded voice lines, and the missing
`marketing/ART_CREDITS.md`. All 5 remaining FAILs come from two checks that are false positives of the validator
itself:

* "settings section Controls missing": the validator's regex expects `ControlsSettings`, but the class is
  `ControlSettings`.
* "hint move references unknown action {moveF/moveL/moveB/moveR}": these placeholders are resolved by
  `U.KeyLabel`, which maps them onto the parts of the `move` composite.

### `tools/unitycheck/check.py`

An offline C# compile check using the Unity editor's bundled Roslyn (`csc.dll`), .NET runtime and reference DLLs.

* It reimplements enough of Unity's script compilation (asmdef discovery, GUID references, define constraints,
  version defines, precompiled references, Editor folders) to compile packages and the project without opening the
  editor.
* `--player` also compiles runtime code without `UNITY_EDITOR`, catching editor-only API in player code.
* Set `UNITYCHECK_OUT=<private dir>` when several agents run it at once.
* Package sources are cached in `tools/unitycheck/pkgs` (git-ignored).
* Some Unity package assemblies report errors in this checker: Burst, URP Editor, Splines, Cinemachine Editor,
  Collections code generators, TextMeshPro in the player configuration, and the test-framework samples. The checker
  does not emulate every package reference. Those assemblies are not project code and compile in the real editor.
  Only the `Assembly-CSharp*` and `EOA*` lines matter, which is what `validate_unity.mjs --compile` reads.

### Tests

* `Assets/Tests/EditMode/Combat/CombatTests.cs`: 18 NUnit tests of the pure combat helpers, in assembly
  `EOA.Tests.Combat`. The runtime compiles into Assembly-CSharp, which an asmdef cannot reference, so the tests reach
  the static helpers through reflection.
* `Assets/Tests/PlayMode` is empty.

## 11. WebGL constraints

* **Single-threaded.**
  * No threads, `Task.Run` or `Task.Delay`.
  * Asynchronous flows are `async Task` methods that wait with `Awaitable.NextFrameAsync()` or
    `Awaitable.WaitForSecondsAsync()`. This applies to zone loading, quests, dialogue, cinematics, fades and
    traversal.
  * The quest system serialises its work on a task queue instead of using locks.
* **Shaders.** The built-in Particle System only (no VFX Graph); no compute or geometry shaders. The custom shaders
  (`EOA/Sky`, `EOA/Aether`) are plain vertex/fragment HLSL for URP.
* **Variant stripping.** Template materials in `Resources/VFX` keep runtime-enabled keywords (emission,
  transparency, additive) from being stripped. `link.xml` preserves reflection-deserialised types for Newtonsoft.
* **Saves.** IndexedDB-backed `persistentDataPath`, flushed with `FS.syncfs` after each write.
* **Platform differences.**
  * The Exit menu item is hidden.
  * The fullscreen setting is not applied by code (the browser controls it).
  * Audio load and compression settings are ignored (the browser decodes).
* **Build settings.** Brotli compression with decompression fallback (itch.io does not send `Content-Encoding`
  headers), data caching on, explicitly-thrown exceptions only.
* **Budgets.** Realtime lights are capped at 24 per zone. Rain particle counts follow Effects quality. Rendering
  scales through the URP render scale.

## 12. Directory layout

```
unity/EchoesOfAether/
  Assets/
    Scripts/            Core (Bus, Contracts, GameInput) · Data (GameData) · Game (GameManager, systems, save,
                        settings, cinematics, rendering) · Actors (Hero, CharacterModel, CameraRig) · Combat ·
                        Enemies · World (ZoneRuntime, ProceduralZone, Kit/, Zones/, Npc, Pickup, MenuStage) ·
                        UI (UIManager, Hud, DialogueView, Screens/) · Audio · VFX · Dev (AutoPilot)
    Editor/             Setup · Environment · Characters · UI · Audio · Build · Testing
    Resources/          Data/ · Audio/ · Models/Robots/ · UI/Icons/ · (generated: Characters/, Env/, VFX/, UI/UIRefs)
    Art/                Characters/<Name>/ · Animations/ · Environment/ (Models, Textures, manifest, ENV_ASSETS.md)
    Shaders/            EOA_Sky.shader, EOA_Aether.shader
    UI/                 Styles/ (eoa.uss, eoa_fonts.uss) · Fonts/ (Rajdhani, Inter + OFL) · Textures/ · EOA_Theme.tss
    Plugins/WebGL/      SyncFS.jslib
    Scenes/             Boot.unity (generated)
    Settings/           EOA_URP.asset, EOA_URP_Renderer.asset, EOA_Lighting.lighting (generated)
    Tests/EditMode/     Combat tests
  Packages/manifest.json
blender/                env/ (environment kit) · robots/ · scripts/ (characters, retarget) · art/ (2D renders)
tools/                  validation/ · unitycheck/ · audio/ · anim/ · vo/ · dreamlayer/ · test/ and capture/ (prototype)
docs/                   design, art, audio, UI, technical, QA and build documents
```
