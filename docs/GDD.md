# Echoes of Aether — Game Design Document

Status date: 2026-10-04. This document describes the game as it is defined by the data and code in this repository.
The design source of truth is the JSON data (`src/data/*.json`, copied verbatim to
`unity/EchoesOfAether/Assets/Resources/Data/`) and the TypeScript prototype (`src/`). The Unity 6 port
(`unity/EchoesOfAether`) implements the same rules in C#. Where the Unity port is incomplete, this document says so.

Status words used below:

| Word | Meaning |
|---|---|
| Implemented | Code exists in the Unity project and compiles. Behaviour has not been confirmed in a recorded Unity play session unless stated. |
| In progress | Partially present in the Unity project; other agents were still working on it at the final check. |
| Prototype only | Exists in the web prototype, not yet in the Unity port. |

## 1. Summary

| Field | Value |
|---|---|
| Title | Echoes of Aether |
| Genre | Third-person sci-fi action-adventure (melee + ranged combat, light exploration and puzzles, story) |
| Setting | Aether-9, a research colony seven years after the "Echo Collapse" |
| Protagonists | Kael Voss and Giva Vale (pick one at the start; switch freely after they reunite) |
| Structure | 6 hand-built zones, 5 main missions, 4 side quests, 5 staged cinematics |
| Target length | About 45 minutes for the main story (design target; not yet measured in the Unity build) |
| Platforms | WebGL (itch.io, jam target) and macOS desktop |
| Engine | Unity 6.3 LTS (6000.3.25f1), URP, C#. The TypeScript/three.js prototype is the design reference. |
| Input | Keyboard + mouse and gamepad, rebindable |
| Look | Neon-noir cyberpunk: HD techwear characters, a cyberpunk city kit and cyber vehicles, all built in Blender and by code (no AI-generated images). See `ART_BIBLE.md`. |
| Voice | Dialogue is subtitled. **Voice-over is off by default**; the player chooses at game start (character select) or later in Settings -> Audio -> Voice-over. It plays human recordings only (none recorded yet), never synthesised or AI voices. |
| Animation | CMU motion capture, 42 humanoid clips in two styles (Kael, Giva), plus procedural robot animation. See `ANIMATION_BIBLE.md`. |

## 2. Premise and story

Aether-9 was a city of about four thousand researchers built around the Aether Core, a reactor "that drew power from
somewhere no one could name" (`cin_intro_lines`). Seven years before the game, the Core's cascade became certain
(`lore_log_cascade`). Dr. Ilse Maren, head of Project Echo, asked the Core to keep the population's minds ("echoes")
rather than let them die (`dlg_truth`). The Core agreed and folded everyone into the Aether. That event is the
"Echo Collapse". The Aether Guardian, a giant machine Maren built, keeps the echoes contained.

Kael Voss (survey lead) and Giva Vale (systems engineer) showed more than 90 percent resonance compatibility
(`lore_log_keys`). Maren kept them asleep as "resonance keys", the only people the Core will listen to
(`dlg_maren_message`). The game begins when they wake in the rain beside the Aether Monument in the Central Plaza.

Story arc by mission:

| # | Mission (`quests.json` id) | Zone | Story beat |
|---|---|---|---|
| 1 | The Awakening (`m1_awakening`) | Central Plaza | The hero wakes, reaches the partner over the comm link, inspects the monument (it is still broadcasting a signal from under the city), destroys three security drones, takes an Aether Shard and finds the partner at the survivors' camp. Oren explains the city has been silent for seven years and that the old Line B tunnels are the way down. |
| 2 | Dead Signal (`m2_dead_signal`) | Abandoned Metro | The heroes follow the signal underground, clear the concourse, restore power by routing three junctions, and find a transmitter carrying Maren's message. Their interfaces recalibrate: Phase Dash (Kael) and Phase Step (Giva) unlock. Maren's access code opens the spur tunnel to the facility. |
| 3 | The Researcher (`m3_researcher`) | Research Facility | The heroes read three research logs (Project Echo, Resonance Keys, Cascade Projection), recover Maren's data (Echo Sight unlocks for Giva), find Maren's hidden office with Echo Sight and learn the truth: the collapse was a rescue that never finished. They defeat the Warden and take Maren's vault clearance. |
| 4 | Into the Vault (`m4_vault`) | Underground Aether Vault | The heroes cross the vault, solve the resonance lock, claim Core Attunement (ultimates unlock), and meet the Aether Guardian. It cannot be harmed here: they survive until the blast door opens and escape to the Core lift. |
| 5 | The Core (`m5_core`) | Aether Core | Maren speaks as an echo: the Guardian is "the part of me that was afraid". The heroes hold off waves of defenders, defeat the Guardian and release the echoes. Ending: the rain stops over Aether-9 for the first time since the collapse. "Now we wake the rest of the city." |

There is one dialogue choice in the main story (`dlg_truth` node `n6`: "Then we finish it." / "She chose for all of
them."). It changes Giva's next line only; the story has one ending.

After `game_complete` is set, the prototype rebuilds the Central Plaza at dawn (no rain, warm light, `ending` music;
`src/world/zones/PlazaZone.ts`). The Unity plaza port includes the dawn variant (`PlazaZone.Dawn`, set from
`game_complete`).

## 3. Protagonists

Both heroes share one control scheme. Their numbers come from `Progression.Stats` (`Assets/Scripts/Game/Inventory.cs`)
and `Hero.cs`, which match the prototype.

| | Kael Voss | Giva Vale |
|---|---|---|
| Role (`locale/en.json`) | Survey Lead · Vanguard | Systems Engineer · Phase |
| Fantasy | Hard-light blade from a forearm interface; breaks enemy lines with heavy Aether strikes | Twin phase-blades; moves faster than anything can track; sees what the Aether hides |
| Max health | 110 | 95 |
| Max shield | 50 (+40 with Shield Matrix) | 50 (+40 with Shield Matrix) |
| Energy | 100, regenerates 9/s | 100, regenerates 9/s |
| Light chain | 3 hits (`k_light1..3`), 15 damage each, third hit x1.25; poise 14; range 2.5 m, 75° either side of facing | 2 hits (`l_quick1..2`), 11 damage; poise 10; range 2.2 m, 75° either side; attacks 12% faster |
| Heavy / finisher | `k_heavy`: 38 damage (x1.4 as a chain finisher), poise 45, 100° either side; plus a 3.4 m ground impact 1.4 m ahead | `l_heavy`: 28 damage (x1.4 as finisher), poise 36, hits all around her (180° half-angle), plus a 3.2 m impact around her |
| Aether Bolt | 1 bolt, 12 damage | 2 bolts in a 2.3° spread, 8 damage each |
| Ability | Aether Pulse: 35 energy, 6 s cooldown, radius 5.5 m, 32 damage, heavy stagger and knockback (available from the start) | Echo Sight: 25 energy, 4 s cooldown, reveals hidden things within 28 m for 10 s (unlocked in mission 3) |
| Evade | Phase Dash: 6.5 m in 0.17 s, 0.28 s invulnerability, 1.4 s cooldown (unlocked in mission 2) | Phase Step: 4.6 m in 0.15 s, 0.34 s invulnerability, 1.0 s cooldown; with no stick input she steps backwards (unlocked in mission 2) |
| Ultimate | Core Break: leap, 9 m radius, 150 damage, 200 poise (unlocked in mission 4) | Resonance Burst: 8 m radius, 115 damage, 200 poise, stuns enemies in range for 3 s (unlocked in mission 4) |
| Combo shown on character select | L · L · L · Heavy | Q · Q · Heavy |

The hint text "light attack (chain up to 4)" (`hints.json`, `combat`) is accurate for Kael (three lights plus the
finisher). Giva's chain is three attacks.

### Appearance and customisation

The player designs the chosen hero on the character-select screen ("Customize") or later from the pause menu
("Appearance"). Sections: Presets, Body, Face, Hair, Ink (glowing tattoos) and Outfit; options for glasses, armour
sets and tattoo designs come from a content catalog. The system is implemented, but the catalog and most of its
content are not in the repository yet, so only the built-in look and the fallback hair list are selectable today
(`CHARACTER_BIBLE.md` §5). Customisation does not change stats.

Looks: Kael has curly medium-length hair, high-tech armour (pauldrons, chest plate and rig, forearm guard, knee pads,
cyberware) and cyan/magenta circuit tattoos. Giva has long wavy hair, a jacket, visor, harness, thigh rig and
cyberware, and magenta/violet tattoos. Giva's internal id and asset folder remain `lyra`.

### Character switching and the companion

* Switching (`swap`, default T / D-pad down) is allowed once the flag `swap_unlocked` is set at the end of mission 1
  (`cin_meeting`). It has a 1.2 s cooldown, keeps the camera heading and plays a coloured flash on both heroes
  (`GameManager.SwapCharacter`).
* Before the reunion, the partner waits at the survivors' camp, scripted in the `npc_crossed` idle.
* The inactive hero is an AI companion (`Hero.UpdateCompanion`):
  * Follows a slot 2 m behind and 1.3 m to the side of the leader. Beyond 6 m it follows the leader's breadcrumb trail.
  * Walks, runs or sprints (2.6 / 5.2 / 7.4 m/s) depending on distance, and jumps when the leader is higher.
  * Teleports next to the leader when stuck for 1.6 s, more than 28 m away or more than 6 m apart vertically. It
    only does this out of the camera's view when possible.
  * In combat, fires a homing support bolt every 2.2–3.7 s (60% of its bolt damage, 22 m range).
  * Regenerates 4 health/s and 10 shield/s, and can be targeted by enemies.

## 4. Controls (defaults)

From `Assets/Scripts/Core/GameInput.cs`. Settings → Controls can rebind every action in this table except Move,
Look, Pause, Skip and Debug.

| Action | Keyboard / mouse | Gamepad |
|---|---|---|
| Move | WASD or arrow keys | Left stick |
| Look | Mouse | Right stick |
| Jump | Space | A / South |
| Sprint (hold) / Phase Dash / Phase Step (tap) | Left Shift | B / East |
| Light attack | Left mouse | X / West |
| Heavy attack | Right mouse | Y / North |
| Aether Bolt (tap to fire, hold to aim) | F | Left trigger |
| Ability (Pulse / Echo Sight) | Q | Left bumper |
| Ultimate | X | Right bumper |
| Interact | E | A / South |
| Switch character | T | D-pad down |
| Lock on | Middle mouse or R | Right stick press |
| Pause | Esc or P | Start |
| Inventory | I or Tab | D-pad left |
| Map | M | Select / View |
| Journal | J | D-pad up |
| Ability Matrix | K | D-pad right |
| Quick-use powerups 1–5 | 1–5 | (none) |
| Skip cinematic (hold) | Space / Enter (or Pause) | A / South |
| Debug overlay (development builds only) | F1 | (none) |

On gamepad, Jump and Interact share A, as they did in the prototype. Reading the code (`GameManager.Update` handles
Interact before `Hero` reads Jump in the same frame), pressing A at a non-dialogue interactable such as an item pickup
should both use it and jump. This has not been confirmed in play (`QA_CHECKLIST.md` §17).

## 5. Combat

### Movement

| Parameter | Value |
|---|---|
| Walk / run / sprint speed | up to 2.2 / 5.2 / 7.6 m/s (sprint = hold Sprint with the stick past half) |
| Aim-walk speed | 2.6 m/s |
| Jump | 7.6 m/s launch, gravity -22 m/s², 0.12 s coyote time, 0.15 s jump buffer |
| Falling out of the level | Below the zone's kill height: teleport to the last safe ground point, 10 piercing damage, 1 s invulnerability |
| Hard landing | Above 9 m/s: camera shake and a landing clip |

### Attacks

* **Input buffer.** Light and heavy presses are buffered for 0.35 s. The next chain hit starts when the current clip
  fires its `combo` animation event.
* **Target magnetism.** Each attack picks the best target within 70° of the stick direction, or of the facing
  direction when the stick is idle, and lunges toward it. Reach is 5.5 m for lights, 6 m for heavies and 8 m for
  ultimates. A lock-on target always wins.
* **Hit windows.** Damage is dealt between the clip's `hit_start` and `hit_end` events with an arc sweep. Each target
  is hit once per swing. Heavy attacks also have an `impact` event that deals area damage.
* **Hit feedback.** Hitstop (0.045 s for lights, 0.085 s for heavies, 0.12 s for ultimates), camera shake, sparks,
  flash and gamepad rumble. Shake follows the camera-shake settings, flashes follow Flash intensity, and rumble
  follows the vibration toggle.
* **Aether Bolt.**
  * Costs 6 energy, with a 0.28 s cooldown. Bolts travel at 42 m/s and home on a target.
  * Tap: fires at the lock-on target, or the best target within 40 m of the camera direction.
  * Hold for 0.2 s: enters aim mode (over-the-shoulder camera, slower movement, aim sensitivity). Release to fire
    at the screen centre with weak homing.
* **Resources.**
  * Each light hit restores 3 energy and each heavy hit restores 1.
  * Ultimate charge (0–100) grows by 35% of damage dealt and 50% of damage taken. The ultimate is usable at 100 once
    Core Attunement is owned.
* **Lock-on.**
  * Toggles onto the best target within 25 m and 52° of the camera direction, with line of sight.
  * Released when the target dies, becomes untargetable (for example a phased Stalker) or moves beyond 30 m.

### Defence, poise and stagger

* **Shields and health.**
  * Shields absorb damage first, unless the hit pierces. After a hit, shields wait 3.5 s, then regenerate at
    16/s. With the Shield Matrix the wait is 2.6 s and the rate 24/s. Story difficulty multiplies the rate by 1.5
    and Hard by 0.8.
  * Health does not regenerate for the player-controlled hero.
* **Invulnerability.** Dashes and steps grant i-frames, ultimates grant 1.8 s, and respawning grants 1.5 s. With
  Ghost Step, a hit avoided during Giva's step refunds 15 energy.
* **Player stagger.** A single hit with 35 or more poise interrupts the hero (`stagger` clip). Smaller hits play a
  short `hit` reaction when the hero is not already acting.
* **Enemy poise.** Every enemy has a poise pool (`enemies.json`). When it reaches 0, the enemy staggers, the pool
  refills, and damage taken while staggered is x1.25. The Guardian ignores poise and is exposed only after its slams.
* **Attack tokens.** Only a limited number of enemies may attack at once: 1 on Story, 2 on Normal and 3 on Hard
  (`GameManager.ApplySettings`, `ZoneRuntime.RequestAttackToken`).

### Difficulty

`Settings.Difficulty` (`Assets/Scripts/Game/Settings.cs`), identical to the prototype:

| Difficulty | Enemy damage | Enemy health | Player shield regen | Enemy aggression (attack cadence) | Simultaneous attackers |
|---|---|---|---|---|---|
| Story | x0.5 | x0.75 | x1.5 | x0.75 | 1 |
| Normal | x1 | x1 | x1 | x1 | 2 |
| Hard | x1.45 | x1.3 | x0.8 | x1.3 | 3 |

Difficulty can be changed at any time in Settings → Gameplay.

## 6. Enemies

Base values from `src/data/enemies.json`. Behaviour from `unity/EchoesOfAether/Assets/Scripts/Enemies/*`, which are
ports of `src/actors/enemies/*.ts`. Models are Blender robots (`Assets/Resources/Models/Robots`, see `ART_BIBLE.md`).

| Enemy | Health | Poise | Damage | Speed | Sight | Attack range | Drops | Behaviour |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Aether Drone (`drone`) | 45 | 20 | 9 | 5.5 | 26 m | 16 m | Shield Fragment 12% | Flying ranged unit. Orbits at about 9 m, fires 2-shot bursts after a 0.55 s charge telegraph, and periodically dives to ram for 80% damage. Staggering spins it; on death it spins, falls and explodes. |
| Corrupted Sentinel (`sentinel`) | 130 | 60 | 18 | 3.6 | 22 m | 2.6 m | Shield Fragment 20%, Overcharge 6% | Melee biped with a red-glow telegraph. Sweep (80° either side) or overhead slam (50° either side, x1.5 damage, 45 poise). Strafes between attacks. |
| Phase Stalker (`stalker`) | 95 | 40 | 16 | 6.2 | 24 m | 2.3 m | Phase Core 15%, Shield Fragment 15% | Fast melee hunter. Phases out to flank: nearly invisible, untargetable and immune unless Echo Sight is active. Three hits within 1.2 s make it phase away. |
| The Warden (`warden`) | 420 | 160 | 24 | 3.4 | 30 m | 3.0 m | Aether Core 100% | Elite Sentinel variant. Its frontal energy shield blocks most non-piercing damage from the front until it is staggered. Its slam shockwave reaches 5 m. |
| Aether Guardian (`guardian`) | 1600 | 400 | 30 | 4.2 | 80 m | 6.5 m | none | The boss (see below). |

Health is multiplied by the difficulty's enemy-health factor at spawn. Enemies have a forward sight cone until alerted
(sight range x1.5 once aggressive), share aggro within their encounter, return home past their leash distance, and use
NavMesh steering when the zone has a NavMesh.

### Aether Guardian (boss)

* **Armour.** The Guardian is armoured everywhere except its chest core.
* **Exposed window.** After each slam the core plates open for 3.4 s. In that window, hits near the core, bolts,
  Pulse and ultimates deal x2.4; other hits deal x1.2.
* **Armoured multipliers.** Lights x0.18, heavies and Pulse x0.35, ultimates x0.7.
* **Shockwave rings.** Slams send out ground shockwave rings that the player must jump or phase over.
* **Phases.**

  | Phase | Health | Attacks |
  |---|---|---|
  | 1 | above 66% | Slams and sweeps |
  | 2 | 66–33% | Adds a chest laser and summons 2 drones |
  | 3 | below 33% | Faster attacks; summons 2 Stalkers |

  Each phase change triggers a roar and emits `BossPhase`, which updates the HUD boss bar.
* **Arena hazard.** In the Core arena, telegraphed Aether discharges strike near the player every 3.5–6 s during the
  boss stage: 18 damage within 2.6 m after a 1.3 s warning ring.
* **Vault Guardian (`guardian_vault`).** The mission-4 encounter uses the same model with red glow. It takes no
  damage ("It shrugs it off. Survive until the blast door opens!"). The blast door opens 38 s after it starts
  cycling, which happens at the reveal.

## 7. Encounters

Encounters are defined per zone. Spawn modes:

| Mode | When it spawns |
|---|---|
| `quest` | When a quest action fires it |
| `trigger:<id>` | When the player enters that box |
| `auto` | On zone load |

Waves advance when every enemy of the current wave is dead. The list below is from the prototype zone files.

| Encounter | Zone | Spawn | Waves |
|---|---|---|---|
| `e_plaza_drones` | Plaza | quest (m1 fight) | 3 drones |
| `e_market_patrol` | Plaza (Collapsed Market) | trigger `t_market` | 2 sentinels + 1 drone |
| `e_metro_concourse` | Metro | quest (m2) | 3 drones |
| `e_metro_platform` | Metro | quest (m2) | 2 sentinels, then 1 drone + 1 sentinel |
| `e_metro_tunnel` | Metro | quest (after the transmitter) | 2 sentinels + 1 drone |
| `e_fac_labs` | Facility | quest (m3) | 2 sentinels + 1 drone |
| `e_fac_offices` | Facility | quest (m3) | 2 drones + 1 sentinel |
| `e_fac_warden` | Facility | quest (m3) | Warden + 2 drones |
| `e_roof_drones` | Rooftops | trigger `t_roof_r2` | 3 drones |
| `e_roof_stalkers` | Rooftops | trigger `t_roof_r4` | 2 stalkers |
| `e_vault_hall` | Vault | quest (m4) | 2 stalkers + 1 drone |
| `e_vault_deep` | Vault | quest (after attunement) | sentinel + stalker, then stalker + sentinel |
| `e_vault_guardian` | Vault | quest (m4) | invulnerable Guardian (survival) |
| `e_core_waves` | Core | quest (m5) | 2 drones + 2 stalkers, then 2 sentinels + stalker + drone |
| `e_core_guardian` | Core | quest (m5) | Aether Guardian |

## 8. Zones

Metadata from `zones.json`. Layouts are from `src/world/zones/*.ts`, which the Unity zone classes
(`Assets/Scripts/World/Zones/*Zone.cs`) port in the same coordinates (see `TECHNICAL_ARCHITECTURE.md`, ProtoSpace).

| Zone | Name / subtitle | Music | Ambience | Unity port status (final check, 2026-10-03) |
|---|---|---|---|---|
| `plaza` | Central Plaza — The Fallen District | explore | rain_city | Ported in code (`PlazaZone.cs`); not yet play-verified |
| `metro` | Abandoned Metro — Line B Transit | tension | metro_drip | Ported in code (`MetroZone.cs`); not yet play-verified |
| `facility` | Research Facility — Aether Research Division | tension | facility_hum | Ported in code (`FacilityZone.cs`); not yet play-verified |
| `vault` | Underground Aether Vault — Containment Level | tension | vault_hum | Ported in code (`VaultZone.cs`); not yet play-verified |
| `rooftops` | Rooftop Sector — Above the Market | sidequest | wind_roof | Ported in code (`RooftopsZone.cs`); not yet play-verified |
| `core` | Aether Core — The Heart of Aether-9 | boss | core_drone | Ported in code (`CoreZone.cs`); not yet play-verified |

All six zone classes were written during 2026-10-03 by other agents. At the final check, the validator found every
quest objective, marker, encounter, collectible, NPC and exit of the data in the C# zones; its only remaining FAILs
are two validator false positives (`TECHNICAL_ARCHITECTURE.md` §10). Play verification (automated smoke test and
manual QA) was still running. Run `node tools/validation/validate_unity.mjs` for the current state.

### Connections

| From | To | Where | Requirement |
|---|---|---|---|
| Plaza | Metro | West stairwell (walk-in) | flag `metro_open` (end of m1) |
| Plaza | Research Facility | North gate | flag `facility_gate_open` (gate control inside the facility, or end of m3) |
| Plaza (market) | Rooftops | Ladder behind the noodle stalls | flag `swap_unlocked` |
| Rooftops | Plaza camp | Drop-down shortcut | none |
| Metro | Research Facility | Spur tunnel (walk-in) | flag `spur_open` (after the transmitter) |
| Research Facility | Vault | Freight lift | item `q_vault_clearance` |
| Vault | Core | Core lift behind the blast door | flag `vault_escaped` |
| Core | Vault | Lift | blocked during the waves and boss stages |

### Central Plaza and Collapsed Market (hub)

> **TODO(lead): update after city art pass.** Landmark buildings, street-level props and lighting are being added by
> other agents. This section lists only what exists in code on 2026-10-04.

| Aspect | Details |
|---|---|
| Time and weather | Night, heavy rain, lightning |
| Layout | 64 m paved square around the Aether Monument, ring road, broken civic buildings, derailed tram under the elevated rail (east), sealed facility gate (north), metro stairwell (west), market street to the south |
| Survivors' camp (north-east) | Fire barrel, Oren, Mira, BOLT (offline until repaired), save terminal |
| Collapsed Market | Market stalls, Tomas, ladder to the rooftops |
| Open city (new) | The plaza is no longer enclosed: avenues and alleys lead out into a **721 x 625 m** cyberpunk district (66 blocks) with five districts: Neon Market (west), Arcology Gate (east), Kowloon Stacks (north), Foundry Row (north-east) and Canal Ward (south, canal and bridges). It has skybridges, quarantine checkpoints, a megawall, a pedestrian crowd and street traffic, all distance-culled. Quest objects, arenas and exits are unchanged, and enemies stay in the plaza arenas. Code: `Assets/Scripts/World/City`, `Zones/Plaza/OpenCity.cs`. Details: `ART_BIBLE.md` §9. |
| Nia | An echo visible only with Echo Sight, wandering a loop around the monument |
| Collectibles | 5 fragments (one hidden at the monument), 2 recordings, 1 hidden cache |

### Abandoned Metro (Line B)

| Aspect | Details |
|---|---|
| Layout | Entry corridor and concourse (upper level), stairs to a flooded platform hall (wading splashes), maintenance bay, power room, signal room |
| Puzzle | Rotate three junctions in the power room so the lit conduit runs from the generator to the breaker; this opens the signal room |
| Lighting | Red emergency lighting until power is restored |
| Exit | An energy barrier seals the spur tunnel east until the transmitter is used |
| Collectibles | 2 fragments (1 hidden), 1 recording, 1 hidden cache |

### Research Facility (Aether Research Division)

| Aspect | Details |
|---|---|
| Layout | Lobby (main gate control and save terminal), central atrium, west wing labs and server room, east offices, Maren's lab, a hidden office reached through a wall that Echo Sight reveals, freight lift room, spur station from the metro |
| Hazard | A security field in the server room pulses on 2.2 s of every 4 s for 9 damage |
| Collectibles | 2 fragments, 2 recordings (1 hidden), 1 hidden cache |

### Underground Aether Vault

| Aspect | Details |
|---|---|
| Path | Lift landing → great hall → lock chamber → attunement chamber → Guardian gallery → blast door → Core lift |
| Hazard | Two energy vent rows in the great hall glow as a warning, then pulse for 14 damage on a 4.2 s cycle |
| Puzzle | Tune three resonators (values 1–4) to the glyph values that Echo Sight reveals (3, 1, 4) |
| Secret room | The "singing wall" (hidden door) leads to Maren's last room, for side quest `sq_hidden_vault` |
| Collectibles | 1 fragment, 1 recording, 1 cache (not hidden) |

### Rooftop Sector

| Aspect | Details |
|---|---|
| Layout | Five connected roofs above the market at 14–19 m, in wind and lighter rain |
| Traversal | A 6 m gap needs Phase Dash or the beam from R2. Ladders are scripted traversals. Falling costs health and returns the player to the last safe ledge. |
| Landmarks | Relay tower (`sq_last_signal`); Anya's hidden room inside the hollow R2 building, entered through a hatch that Echo Sight reveals |
| Collectibles | 2 fragments (1 hidden), 1 hidden cache, plus side-quest parts |

### Aether Core

| Aspect | Details |
|---|---|
| Layout | Circular arena (radius about 27 m) under the suspended Core, with the heart pedestal at the centre, floating debris and broken orbit rings |
| Encounters | Wave defence, then the Guardian, then "Release the echoes" at the heart |

## 9. Missions and quests

Quests are data driven (`quests.json`). Each stage has objectives of these types: `flag`, `interact`, `kill`
(encounter cleared), `collect` (inventory count), `reach` (trigger), `zone` (zone entered) and `talk` (NPC dialogue
finished). Stages also have `onStart` and `onComplete` actions:

`dialogue`, `cinematic`, `encounter`, `despawn`, `spawnPickup`, `hint`, `give`, `take`, `setFlag`, `startQuest`,
`unlock`, `autosave`, `credits`.

### Main missions

| Mission | Stages (objective) | Completion rewards / effects |
|---|---|---|
| m1 The Awakening | wake (move) → monument (inspect `i_monument`) → fight (clear `e_plaza_drones`) → powerup (collect the Aether Shard) → meet (reach the camp; `cin_meeting`; `swap_unlocked`) | +1 Aether Fragment, `metro_open`, starts m2, autosave |
| m2 Dead Signal | enter the metro → clear the concourse → restore power (`metro_power_on`) → investigate the transmitter (Maren's message; unlock Dash and Step; Facility Access Code; `spur_open`) → take the spur to the facility | +1 Fragment, starts m3, autosave |
| m3 The Researcher | reach the labs → read 3 logs → recover Maren's data (Echo Sight unlocks) → find the hidden office (`dlg_truth`) → defeat the Warden → take the vault clearance | +1 Fragment, `facility_gate_open`, starts m4, autosave |
| m4 Into the Vault | take the freight lift → reach the resonance lock → open the lock (`vault_lock_open`) → claim Core Attunement (ultimates) → approach the Core access (`cin_guardian_reveal`, blast door starts cycling) → survive and get through the blast door → ride the lift to the Core | +1 Fragment, starts m5 |
| m5 The Core | approach the Core (`dlg_final_truth`) → hold off the waves → defeat the Aether Guardian (`dlg_boss_intro`) → release the echoes | `game_complete`, `cin_ending`, credits |

### Side quests

| Quest | Giver / zone | Objectives | Reward |
|---|---|---|---|
| The Last Signal (`sq_last_signal`) | Mira, camp; played on the rooftops | Locate the relay tower → find a relay power cell → activate the relay → find the hidden room (Echo Sight) → recover Anya's recording → return to Mira | Echo Amplifier, +2 Fragments |
| Broken Guardian (`sq_broken_guardian`) | Oren, camp | Servo actuator (metro maintenance bay), maintenance power cell (market), control component (rooftop shed) → repair BOLT | Shield Matrix, +2 Fragments; BOLT patrols the camp |
| Memory Fragments (`sq_memory_fragments`) | Tomas, market | Recordings Market Day (plaza market), Last Train (metro), Lullaby (facility, hidden) → return to Tomas | Aether Core; flag `tomas_concert` |
| Hidden Vault (`sq_hidden_vault`) | Nia (echo), plaza | Find the singing wall in the vault (Echo Sight) → claim what Maren left (`cin_hidden_vault`) | Resonant Core, Maren's Testament (lore) |

* Oren, Mira and Tomas offer their quests only after the reunion (`flag:swap_unlocked`).
* Nia offers hers to anyone who can see her. Quest data marks it `requires: "ability:echo"`, but neither the
  prototype nor the Unity `QuestSystem` checks that field. Nia is effectively gated by Echo Sight, or by the Echo
  Fragment powerup, which also reveals echoes.

### Cinematics

| Id | Where | Content (prototype staging; see `src/game/Cinematics.ts`) |
|---|---|---|
| `cin_intro` | New game | About 90 s: aerial push over the district, the monument, the hero lying in the rain, the partner at the camp, narrator and hero lines |
| `cin_meeting` | End of m1 | About 45 s: shot and reverse shot of the reunion, Oren joins, both look toward the metro |
| `cin_guardian_reveal` | m4 | About 30 s: the Guardian rises from the containment pit |
| `cin_hidden_vault` | `sq_hidden_vault` | About 25 s: Maren's echo in her last room |
| `cin_ending` | End of m5 | About 90 s: release, the echoes rise, dawn over Aether-9 |

Unity status:

* `Cinematics.cs` falls back to playing the cinematic's `<id>_lines` dialogue as auto-paced subtitles when no staged
  script is registered.
* At the final check, all five cinematics had staged C# scripts in `Assets/Scripts/World/Zones/Cinematics/`:
  * `PlazaCinematics.cs`: `cin_intro`, `cin_meeting`
  * `VaultCinematics.cs`: `cin_guardian_reveal`, `cin_hidden_vault`
  * `CoreCinematics.cs`: `cin_ending`

  They are not yet play-verified.
* Hold to skip (1.1 s) is implemented for both the staged scripts and the subtitle fallback.

## 10. Items, powerups and progression

### Inventory

Inventory categories (`items.json`): Aether, Powerups, Quest, Upgrades and Lore. Each item has a stack limit;
fragments stack to 99, for example. Quest items are listed with their quest. Lore items replay their recording or log
text in the inventory detail and the journal.

### Powerups

Defined in `powerups.json`.

| Powerup | Effect | Duration |
|---|---|---|
| Aether Shard | +30% damage | 20 s |
| Phase Core | +60% dash and step distance | 25 s |
| Overcharge | +35% attack speed | 15 s |
| Shield Fragment | Restores the shield instantly | — |
| Echo Fragment | Echo reveal around the player for either hero | 30 s |

* Powerups spawned by quests and enemy drops activate on pickup.
* Powerups found in caches go to the inventory. They are used from the inventory screen or quick slots 1–5.

### Upgrades

| Upgrade | Source | Effect |
|---|---|---|
| Shield Matrix | Broken Guardian | +40 max shield, faster shield recovery |
| Echo Amplifier | The Last Signal | Echo Sight range +50%, +4 s |
| Core Attunement | m4 | Unlocks ultimates |
| Resonant Core | Hidden Vault | Ability cooldowns -20%, +15 max health |

### Ability Matrix (skill tree)

Twelve nodes, three per ability, bought in order. Each Aether Fragment is worth 1 point and each Aether Core 3 points
(`Progression.Points`). A node requires its ability to be unlocked first.

| Ability | Node 1 | Node 2 | Node 3 |
|---|---|---|---|
| Aether Pulse | Wide Pulse (1): radius +40% | Heavy Pulse (2): damage +50% | Concussive Pulse (2): staggers elites, more knockback |
| Phase Dash | Long Phase (1): distance +40% | Quick Phase (2): cooldown -35% | Twin Phase (3): second charge |
| Echo Sight | Far Sight (1): range +50% | Lingering Echo (2): +6 s | Deep Echo (2): hidden caches and collectibles shown on the minimap while Echo Sight is active |
| Phase Step | Long Step (1): distance +40% | Quick Step (2): cooldown -35% | Ghost Step (2): double i-frames, perfect dodge refunds energy |

Economy check (from the data):

| Source | Points |
|---|---:|
| 12 collectible fragments | 12 |
| Mission and side-quest fragment rewards (1+1+1+1+2+2) | 8 |
| 4 Aether Cores (two caches, Tomas, the Warden's guaranteed drop), 3 points each | 12 |
| **Total available** | **32** |
| Cost of the full tree | 21 |

### Collectibles

Defined in `collectibles.json`. The pause screen shows the totals per kind.

| Kind | Count | Zones | Hidden (need an Echo reveal) |
|---|---:|---|---|
| Aether Fragments | 12 | plaza 5, metro 2, facility 2, rooftops 2, vault 1 | `c_frag_03` (plaza), `c_frag_07` (metro), `c_frag_11` (rooftops) |
| Memory recordings | 6 | plaza 2, metro 1, facility 2, vault 1 | `c_rec_05` (facility, Lullaby) |
| Hidden caches | 5 | plaza, metro, facility, rooftops, vault | 4 of 5 (`c_cache_05` in the vault is visible) |

Lore has 11 entries:

* 6 recordings: Morning Shift, Market Day, Last Train, Lab 7 Notes, Lullaby, Vault Watch
* 4 research logs: Project Echo, Resonance Keys, Cascade Projection, Final Entry
* Maren's Testament

Picking up a recording plays it as radio subtitles.

### Echo Sight reveals

While an Echo reveal is active (Giva's Echo Sight, or the Echo Fragment powerup for either hero), everything hidden
within range of the player is revealed permanently and stored in the save (`ZoneRuntime.UpdateEcho`):

| Category | Items |
|---|---|
| Hidden doors | Maren's hidden office wall (facility, `i_maren_hidden_door`), the singing wall (vault, `i_hidden_door`), the rooftop hatch to Anya's room (`i_hidden_hatch`) |
| Resonance glyphs | `g_glyph_1..3` in the vault lock chamber, which give the resonator values |
| Hidden collectibles | The 8 hidden collectibles listed above |
| Echoes | Nia can be seen and talked to only while a reveal is active |
| Enemies | Phase Stalkers stay visible and targetable while phased |
| Presentation | The screen desaturates with a violet tint (`PostFx.Tick`); a ring wave plays and a toast "Echo revealed something hidden" appears |

## 11. Saving

Player-facing summary; technical details are in `TECHNICAL_ARCHITECTURE.md`.

* **Slots.** Three slots. Each has a thumbnail, mission title, zone, hero, playtime and timestamp. A rolling backup
  is kept per slot.
* **Autosaves.**
  * On entering a zone (not after a respawn or when loading a save).
  * At quest `autosave` actions: the end of m1, m2 and m3.
  * When the credits start.
* **Manual saves.** From the pause menu or a save terminal (plaza camp, metro, facility lobby, vault landing, roof
  R1). Not allowed during combat, dialogue or cinematics.
* **Damaged saves.** Detected by checksum and schema validation. The slot offers "Restore Backup" when a valid
  backup exists.
* **Death.** The "Signal Lost" screen offers Retry from Checkpoint (the zone entry point), Load Last Save, or Quit
  to Main Menu.

## 12. Known gaps between data, prototype and the Unity port

| Item | Detail |
|---|---|
| Zones and cinematics | All six zones and five staged cinematics are written in C#. An automated story smoke run on 2026-10-04 (`Captures/smoke/report.json`) reports story PASS with no errors from intro to credits (14 screenshots), but manual play-testing is not done (see §8 and `PROJECT_AUDIT.md`) |
| Customisation content | The catalog (`Resources/Characters/Custom/catalog.json`) is missing; glasses, armour sets and tattoo designs are not selectable yet (`CHARACTER_BIBLE.md` §5) |
| Hover vehicles | `HoverCar_A`, `HoverCar_B` and `HoverTruck` exist as prefabs but no code places them |
| Voice-over | Switch and playback code exist; 0 of 161 lines are recorded, so the option changes nothing audible yet |
| Nia's wander route | The generic `Npc` has no route support (`wander` maps to an idle). The plaza port adds Nia's 7-point loop with its own `PzWander` component (`PlazaZone.cs`), so it works only for Nia in the plaza. |
| Unenforced data field | `quests.json` `requires` on `sq_hidden_vault` is not enforced in either implementation |
| Gamepad A | Jump and Interact share the gamepad A button |
