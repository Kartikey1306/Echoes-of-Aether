# Echoes of Aether — QA Checklist (Unity build)

Status date: 2026-10-03. Use this list for every release candidate.

* **Automated checks (§1)** run first. They are cheap and catch most regressions.
* **Manual checks (§2–§16)** need the Unity editor (Play mode from `Assets/Scenes/Boot.unity`) or a built player.
* Record the result of each item: Pass, Fail (with steps) or N/A, plus the build or commit tested.

Item numbers (`B1`, `Z3`, `S7`, ...) are for bug reports.

**Known open items at the final check (2026-10-03):**

* All six zones and the five staged cinematics were written in C# on 2026-10-03 and have not been play-verified
  (`GDD.md` §8–9).
* Rendered 2D art is incomplete: only plaza and metro loading art exists.
* The designer controls listed in `CHARACTER_BIBLE.md` §5 have no visible effect.

Check these first so they are not reported twice.

## 1. Automated checks

Run from the repository root (`/Users/kartikey/Desktop/Game`).

| # | Check | Command | Pass criteria |
|---|---|---|---|
| A1 | Data, content and pipeline validation | `node tools/validation/validate_unity.mjs` | Exit code 0 ("no FAIL"). Review every WARN. Two FAILs are validator false positives: "settings section Controls missing" (regex expects `ControlsSettings`; the class is `ControlSettings`) and "hint move references unknown action {moveF…}" (handled by `U.KeyLabel`). Fix the validator rather than ignoring them, or confirm only those two remain. |
| A2 | Validation plus offline C# compile (editor and player configurations) | `node tools/validation/validate_unity.mjs --compile` (or directly: `python3 tools/unitycheck/check.py --player`; set `UNITYCHECK_OUT=<private dir>` when another agent is compiling) | All `Assembly-CSharp*` and `EOA*` assemblies report OK (final check 2026-10-03: OK with 0 errors and 0 warnings). Errors in Unity package assemblies are a known limitation of the offline checker and can be ignored. |
| A3 | Real editor compile and setup | `"/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity" -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.ProjectSetup.RunAllBatch -logFile setup.log` | Exit code 0; the log shows `[setup] ✓` for every step and no `error CS`; `ProjectSettings/EOA_Setup.txt` exists |
| A4 | EditMode unit tests (18 combat tests) | Unity Test Runner (Window → General → Test Runner → EditMode → Run All), or batch: `Unity -batchmode -projectPath unity/EchoesOfAether -runTests -testPlatform EditMode -testResults editmode.xml` | All pass, none inconclusive |
| A5 | Rendered audio integrity | `node tools/audio/verify.mjs` | Prints `PASS` (passed on 2026-10-03) |
| A6 | Smoke play-through with screenshots | EOA → Test → Smoke Test, or batch `Unity -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.Run` | Exit code 0. `Captures/smoke/report.json` lists no errors. Review the screenshots and per-zone load and frame times. (Tool added 2026-10-03. The first run had captured the menu, character select, intro, plaza gameplay and start, overview and vista shots of all six zones, but had not yet written `report.json` at the final check.) |
| A7 | Secret scan | Included in A1; manual: `grep -rlE 'dlr_(live|test)_[A-Za-z0-9]{20,}' . --exclude-dir=node_modules --exclude-dir=Library` | No matches, including in `Builds/` |
| A8 | Data parity with the design source | Included in A1 ("Unity data matches the authoring data in src/data") | PASS |

## 2. Boot and main menu

| # | Check |
|---|---|
| B1 | Opening the project for the first time runs the automatic setup (Console: "[setup] first open: running EOA project setup", then "project setup complete"). |
| B2 | Play from `Boot.unity` reaches the main menu with no Console errors. Pressing Play in an empty scene also reaches the main menu (`Bootstrap` safety net). |
| B3 | The menu stage shows Kael and Giva on their pads; the title shows (rendered logo, or the typographic fallback). |
| B4 | With no saves, Continue is disabled and shows "No saved game", and New Game has focus. With a save, Continue shows "Mission · playtime" and has focus. |
| B5 | Load Game, Settings and Credits open and close (Esc / B returns). Exit asks for confirmation (desktop) and is absent on WebGL. |
| B6 | Mouse hover, keyboard arrows, D-pad and left stick all move focus; Enter / Space / A activate; `ui_hover`, `ui_click` and `ui_back` sounds play. |
| B7 | The footer shows "Jam build 1.0 · release" in release builds ("development" in development builds). |

## 3. Character select and designer

| # | Check |
|---|---|
| C1 | Kael / Giva tabs (click, Q/E, LB/RB) switch the description, role, combo text and abilities, and the stage focus. |
| C2 | Dragging and the right stick rotate the hero. |
| C3 | Save-slot selector defaults to the first empty slot. Choosing an occupied slot asks for overwrite confirmation on Begin. |
| C4 | Begin starts a new game in the chosen slot. The intro plays as subtitles until `cin_intro` is staged in C#. Mission 1 starts afterwards. |
| C5 | Customize opens the designer for the selected hero. Each Presets button changes the look. |
| C6 | Body sliders: Height scales the model, and Muscle, Weight, Shoulders, Hips (and Bust for Giva) visibly deform the body. Skin swatches and the picker change the skin. |
| C7 | Face sliders deform the face. Eye colour changes the iris only. View Face/Body moves the camera. |
| C8 | Hair chips switch the visible hair mesh; hair colour tints hair, brows and lashes. |
| C9 | Outfit colours change jacket, accent, armour and both glow colours. Shoulder armour and Gloves toggle meshes; Chest plate and Knee pads toggle meshes on Kael. |
| C10 | Known no-ops, which should be confirmed and tracked rather than filed again: Facial scar and Stubble (no visible change; the designer no longer shows them). Chest plate and Knee pads exist only on Kael. Giva's default hair id `long_curls` is a catalog id: confirm the wavy default shows without the catalog. |
| C10a | Customisation catalog (`Resources/Characters/Custom/catalog.json`): present? If so, Glasses, Hair, Tattoo design and Armour set grids show thumbnails and each choice visibly changes the hero. If absent (the state at 2026-10-04), those grids are hidden and Hair shows text chips. |
| C11 | Randomize gives a plausible look. Reset asks for confirmation and restores the default. Done returns to character select with the change visible. |
| C12 | Appearance persists after restarting the game (`appearance.json`) and applies in game. Changing appearance from the pause menu updates the in-game hero. |

## 4. Zone traversal

Repeat for each zone.

**Common checks (every zone):**

* The loading screen shows the zone name, subtitle, quote, a hint and moving progress.
* No fall-through on any walkable surface, and no invisible snags.
* The camera never clips through walls (sphere-cast collision).
* Falling below the kill height returns the hero to the last safe ground with 10 damage.
* Every exit works and shows its locked text when requirements fail.
* The map and minimap show the layout, exits and the player arrow.
* Music and ambience match `AUDIO_BIBLE.md` §2–3.

| # | Zone | Specific checks |
|---|---|---|
| Z1 | Central Plaza | Spawn beside the monument; rain, lightning and thunder. Partner waits at the camp before the reunion. Metro stairwell locked until m1 ends. Facility gate sealed until opened from inside. Rooftop ladder (market) locked until the reunion. Save terminal at the camp. Nia visible only with Echo Sight. Collapsed Market reached through the south street. `e_market_patrol` spawns when entering the market. After the ending: dawn variant (no rain, `ending` music). Nia walks her loop around the monument. |
| Z2 | Abandoned Metro | Arrival on the concourse; red emergency light. Stairs to the flooded platform with wading splashes. Inspecting the generator gives a hint. Rotating the three junctions lights the conduits, restores power and opens the signal room. Spur tunnel barrier until the transmitter is used. Back exit to the plaza. |
| Z3 | Research Facility | Arrival at the spur station. Server-room security field pulses (9 damage on a 4 s cycle). Log terminals. Maren's terminal. The hidden office wall opens after an Echo reveal. Gate control opens the main gate (shortcut to the plaza). Freight lift requires the vault clearance. |
| Z4 | Underground Vault | Lift landing and save terminal. Vents telegraph, then pulse (14 damage). Resonators cycle 1–4; the glyphs (Echo Sight) show 3, 1, 4; the lock opens when they match. Attunement pedestal. Guardian gallery and blast door: green lights fill over 38 s, then the door opens. Core lift sealed until then. Singing wall leads to the secret room. |
| Z5 | Rooftop Sector | Wind and lighter rain. Ladders are scripted climbs (up and down). The 6 m gap needs Phase Dash or the beam. Falling returns to the last ledge. Relay tower. The hidden hatch climbs into Anya's room and back out. Drop-down shortcut to the plaza camp. Triggered drone and stalker encounters. |
| Z6 | Aether Core | Arrival by the lift. The lift back is blocked during the waves and boss stages. Discharge rings strike near the player during the boss (18 damage after a 1.3 s warning). Heart interaction at the end. |

## 5. Main missions

Play each mission as Kael and again as Giva. Some lines and the meeting cinematic differ by hero.

| # | Mission | Checks |
|---|---|---|
| M1 | The Awakening | The comms dialogue matches the chosen hero. Moving 4 m completes "Find your footing". Monument interact plays `dlg_m1_signal`. Three drones spawn; clearing them plays `dlg_m1_after_fight`. The Aether Shard spawns at the monument and activates on pickup (+30% damage, 20 s timer on the HUD). Reaching the camp plays `cin_meeting`, then the swap unlocks with a hint. Mission complete: +1 fragment, metro opens, m2 starts, autosave. |
| M2 | Dead Signal | Entering the metro completes stage 1. The concourse drones must die. The platform encounter spawns with the power stage. Routing the junctions sets `metro_power_on`. The transmitter plays Maren's message and unlocks Dash and Step (toast and hint), gives the Facility Access Code, opens the spur and spawns the tunnel encounter. Taking the spur completes the mission (+1 fragment, autosave). |
| M3 | The Researcher | Lab trigger spawns enemies. Three logs (each plays its lore, adds the lore entry and ticks its objective; the offices encounter spawns). Maren's data unlocks Echo Sight with a dialogue and hint. The hidden office is found with Echo Sight; reading the final entry plays `dlg_truth` with a choice (both options work). Warden fight in the atrium. Vault clearance pickup at the Warden drop. Gate opens. +1 fragment, m4 starts, autosave. |
| M4 | Into the Vault | Freight lift. Hall encounter. Lock puzzle. Attunement gives Core Attunement (ultimates unlock, hint, deep encounter). The Guardian approach plays `cin_guardian_reveal`; the invulnerable Guardian attacks; survive until the blast door opens and get through (`vault_escaped`; the Guardian despawns). Core lift. +1 fragment, m5 starts. |
| M5 | The Core | Approaching the Core plays `dlg_final_truth`. Two waves. `dlg_boss_intro`, then the boss bar appears. The Guardian dies. "Release the echoes" sets `game_complete` and plays `cin_ending`. Credits roll (48 s, skippable after 0.8 s), then the main menu. The save written at credits loads as "Epilogue". |

## 6. Side quests

| # | Quest | Checks |
|---|---|---|
| Q1 | The Last Signal (Mira) | Offered only after the reunion. Both acceptance paths ("Who do you think it is?") work; "Not yet" declines. The relay cell pickup appears only while the quest is active. Socket activation plays `dlg_relay_active`. The hidden hatch needs Echo Sight. The recording pickup works. Turn-in plays Anya's lines and gives the Echo Amplifier and +2 fragments; the recording item is taken. |
| Q2 | Broken Guardian (Oren) | Offer and the "Where would we even look?" branch. The three parts appear only while the quest is active (metro bay, market, rooftop shed). Oren's progress and ready lines. Repairing BOLT takes the parts, sets `bolt_repaired` and plays `dlg_bolt_repaired`. Shield Matrix (+40 max shield) and +2 fragments. BOLT then walks its loop and has new dialogue. |
| Q3 | Memory Fragments (Tomas) | Offer and the "why" branch. Recordings Market Day, Last Train and Lullaby (the last one is hidden). Turn-in gives an Aether Core (worth 3 points) and both choice lines work. |
| Q4 | Hidden Vault (Nia) | Nia can be talked to only during an Echo reveal. The singing wall is revealed and entered. Claiming plays `cin_hidden_vault` and gives the Resonant Core (-20% cooldowns, +15 max health) and Maren's Testament. Nia's after-line. |
| Q5 | Tracking | The journal lists active and completed quests. Tracking a side quest moves the HUD tracker and objective marker. A side quest tracked on the rooftops switches music to `sidequest`. |

## 7. Combat

| # | Check |
|---|---|
| K1 | Kael: L-L-L chains (third hit stronger); light after the third becomes the heavy finisher; heavy alone; heavy ground impact. Giva: Q-Q chain plus heavy finisher (360° sweep). |
| K2 | Input buffering: presses during an attack chain correctly. Target magnetism lunges toward the nearest enemy in the stick direction. |
| K3 | Bolt tap fires at the best or locked target (Kael 1 bolt, Giva 2). Holding 0.2 s enters aim mode (crosshair, slower movement, over-shoulder camera); release fires. Costs 6 energy; "error" sound with no energy. |
| K4 | Aether Pulse (35 energy, 6 s cooldown, knockback and stagger). Echo Sight (25 energy, 4 s cooldown). Cooldown pies on the HUD. |
| K5 | Phase Dash and Phase Step: i-frames (attacks pass through), cooldown, Twin Phase second charge. Giva steps backwards without stick input. Sprint by holding the same key. |
| K6 | Ultimates: ring fills from dealing and taking damage; unusable before attunement; Core Break and Resonance Burst (enemies stunned 3 s); invulnerable during the ultimate. |
| K7 | Lock-on toggles with R / middle mouse / R3; drops on death, phasing or distance over 30 m. |
| K8 | Hitstop, camera shake, sparks and rumble on hits; damage vignette and low-health vignette. |
| K9 | Player stagger from heavy hits (sentinel slam, guardian). Shield absorbs first, then regenerates after the delay. |
| K10 | Difficulty: Story halves enemy damage and allows only 1 attacker at a time; Hard allows 3 and hits harder. Switch mid-fight and verify the change applies. |
| K11 | Companion: follows, catches up or teleports when stuck or far away, fires support bolts in combat, is targeted by enemies, never blocks the player. Swapping mid-fight works (1.2 s cooldown). |

### Enemies

| # | Enemy | Checks |
|---|---|---|
| E1 | Drone | Orbits at range, charge telegraph then 2-shot burst, dive ram, spin on stagger, falling explosion on death, possible Shield Fragment drop |
| E2 | Sentinel | Red telegraph, sweep and slam, strafing, stagger after poise break (bonus damage while staggered), drops |
| E3 | Phase Stalker | Phases out (invisible, untargetable, immune), reappears to flank, phases away after 3 quick hits; with Echo Sight active it is visible and hittable |
| E4 | Warden | Frontal shield blocks most frontal damage until staggered; 5 m slam shockwave; guaranteed Aether Core drop |
| E5 | Vault Guardian | Takes no damage (toast "It shrugs it off…"); survival until the blast door opens |
| E6 | Aether Guardian | Armour multipliers (lights barely hurt); core exposed for 3.4 s after slams; shockwave rings must be jumped or dashed; phase 2 laser and drone summons; phase 3 faster with stalker summons; boss bar shows the phase; arena discharges |
| E7 | General | Aggro sharing within an encounter; leash return; enemies do not get stuck (stuck recovery); waves advance; attack tokens limit simultaneous attackers; enemies freeze during cinematics |

## 8. Abilities, powerups, inventory and skills

| # | Check |
|---|---|
| P1 | Each powerup's effect and duration: Shard +30% damage 20 s, Phase Core +60% dash 25 s, Overcharge +35% attack speed 15 s, Shield Fragment instant, Echo Fragment reveal 30 s. HUD timers. Pickups activate immediately; cache items go to the inventory. |
| P2 | Quick slots 1–5 use stored powerups; "No … left" toast when empty. Inventory Use button works. |
| P3 | Inventory categories, counts, stack limits (a "full" toast at the limit), item details, quest item labels, lore text. |
| P4 | Ability Matrix: points = fragments + 3 × cores; nodes buy in order; locked reasons ("Requires …", "Not enough Aether"); a core is broken into fragments when needed. Each node's effect is noticeable (for example, Wide Pulse radius). |
| P5 | Upgrades: Shield Matrix, Echo Amplifier, Core Attunement, Resonant Core apply their stat changes (check with the F1 overlay in a development build). |

## 9. Echo Sight and collectibles

| # | Check |
|---|---|
| R1 | Echo Sight: violet desaturation, wave effect, reveal sound and toast. Reveals within range persist after reloading. |
| R2 | Each hidden element is revealed and usable: Maren's office wall, the singing wall, the rooftop hatch, glyphs 1–3, Nia, and the 8 hidden collectibles (`c_frag_03`, `c_frag_07`, `c_frag_11`, `c_rec_05`, `c_cache_01`–`04`). |
| R3 | Echo Fragment powerup reveals for Kael as well as Giva. |
| R4 | Deep Echo: hidden collectibles appear on the minimap while Echo Sight is active. |
| R5 | Totals: the pause screen shows Aether Fragments x/12, Recordings x/6, Hidden Caches x/5. Every collectible can be reached and collected once; recordings play as radio subtitles and appear in Journal → Lore. |

## 10. Saving, loading and corruption recovery

On macOS (editor and player) the save folder is `~/Library/Application Support/EchoesOfAether/Echoes of Aether/`. It
contains `saves/slot{n}.json`, `saves/slot{n}.bak.json`, `settings.json` and `appearance.json`.

| # | Check |
|---|---|
| S1 | Autosave on zone entry and at the end of m1–m3 ("Autosaved" indicator). Manual save from the pause menu and from save terminals. |
| S2 | Saving is refused during combat, dialogue and cinematics, with a reason (the pause button is disabled with the reason as subtitle). |
| S3 | Slot cards show a thumbnail, mission, zone, hero, playtime, date and kind. Overwrite and delete confirmations work. |
| S4 | Loading restores zone, position, hero, quests and stages, inventory, flags, revealed and collected items, defeated encounters, appearance and playtime. Encounters and pickups of the active stage come back. |
| S5 | Continue loads the newest save across slots. |
| S6 | Corruption, case 1: edit one character inside `"state"` of `slot1.json`. The slot shows "Damaged - backup available" with "Checksum mismatch"; Restore Backup repairs it; Load (backup) works. |
| S7 | Corruption, case 2: truncate `slot1.json` (invalid JSON) → damaged. Delete both main and backup → empty. Set `"version": 99` → "Save is from a newer version". |
| S8 | Corruption, case 3: invalid state (unknown zone id with a recomputed checksum, or a negative item count) → "Invalid state: …". |
| S9 | `settings.json` with garbage or out-of-range values → the game starts with defaults or clamped values (no crash). Bad `appearance.json` → default looks. |
| S10 | Kill the process during a save (stress): on restart the slot is either the old or the new save, never broken (atomic write plus backup). |

## 11. Settings, persistence and rebinding

| # | Check |
|---|---|
| T1 | Every option in all six sections changes the game immediately and survives a restart. |
| T2 | Graphics presets set their group; changing an individual option switches to Custom. Resolution changes the render scale. ("1440p" and "Native" are both 1.0, a known labelling issue.) |
| T3 | Reset section asks for confirmation and restores defaults (Controls also resets bindings). |
| T4 | Rebinding: click, press a key → saved. Esc cancels. A conflict swaps with the other action and a toast names it. Labels update in the HUD and hints. Bindings survive a restart. Controller rebinding requires a connected pad. Move cannot be rebound. |
| T5 | Invert Y, camera, aim and controller look sensitivity, vibration toggle. |
| T6 | Fullscreen toggle (desktop only). |

## 12. Accessibility

| # | Check |
|---|---|
| X1 | Subtitles off hides radio and cinematic subtitles (interactive dialogue still shows). Sizes S, M, L and XL; background opacity; speaker names off. |
| X2 | Flash intensity 0 removes lightning flashes and screen flashes; camera-shake limit 0 removes all shake. |
| X3 | UI scale 75% and 150% re-flows every screen without overlap or clipping (HUD, pause, panels, settings, designer, saves, dialogue). |
| X4 | Hold-to-skip off: a single press skips cinematics. |
| X5 | The whole game is playable with gamepad only and with keyboard and mouse only. Prompts and key labels follow the last device. |

## 13. Audio

| # | Check |
|---|---|
| AU1 | Music: menu → zone mood → combat when enemies aggro → back 4 s after combat → boss music during bosses; silence while loading and dying; ending at credits. 2 s crossfades without clicks or gaps. |
| AU2 | Ambience per zone. Loops are seamless (listen across the loop point). |
| AU3 | Thunder follows lightning with a delay (plaza, rooftops). |
| AU4 | Positional SFX attenuate with distance; footsteps match speed; no stacking spam of the same sound. |
| AU5 | Dialogue ducks music. Each volume slider works; 0 mutes its bus. |
| AU6 | Voice-over is off by default: confirm the character-select choice and Settings -> Audio -> Voice-over stay in sync and persist. 0 lines are recorded, so nothing is audible either way and subtitles always show. If recordings are added: check playback, ducking, pause/resume, the Voice volume slider and the `_kael` / `_lyra` variants; update the credits. |

## 14. Cinematics, death and retry

| # | Check |
|---|---|
| CI1 | Each cinematic (`cin_intro`, `cin_meeting`, `cin_guardian_reveal`, `cin_hidden_vault`, `cin_ending`) plays (staged, or the subtitle fallback). Hold Skip shows the ring and skips at 1.1 s. After skipping, game state is correct (quest advanced, actors placed, no stuck letterbox, input restored). |
| CI2 | NPC conversations use the two-shot camera; choices are navigable with keyboard, mouse and gamepad; the camera returns afterwards. |
| D1 | Death: "Signal Lost" after 2.4 s. Retry from Checkpoint restores full health at the zone entry. Load Last Save works. Quit returns to the menu. |
| D2 | Hazards (facility field, vault vents, core discharges) deal the documented damage and can kill. |
| D3 | Deaths during cinematics or dialogue cannot happen (enemies frozen, player scripted). |

## 15. Performance

There are no Unity performance measurements yet. The targets below are carried over from the prototype.

| # | Check | Target |
|---|---|---|
| PF1 | FPS at 1080p, High preset, Apple M4 (macOS player) in each zone during the largest fight | 60 FPS |
| PF2 | Zone load time (Console "[game] zone … loaded in … ms", or the smoke report) | < 3 s |
| PF3 | Memory (F1 overlay) after touring all zones | No growth from zone to zone (leak check) |
| PF4 | WebGL in Chrome and Safari on the same machine: Medium and High presets | Playable frame rate; note the results |
| PF5 | Effects quality Low, Medium and High change rain density, particles and post-processing as documented | — |

## 16. WebGL specifics

| # | Check |
|---|---|
| W1 | The build loads from itch.io (Brotli with the decompression fallback, no `Content-Encoding` errors). The loading bar progresses. |
| W2 | Saves, settings and appearance persist after reloading the tab and after closing the browser (IndexedDB plus `FS.syncfs`). |
| W3 | No Exit button. The fullscreen toggle does nothing harmful; browser fullscreen works. |
| W4 | Audio starts after the first click or keypress (browser autoplay policy) and music loops play. |
| W5 | Pointer lock: the cursor locks in gameplay and unlocks for menus and dialogue. Esc releases browser pointer lock and opens pause. Focus loss pauses the game. |
| W6 | Gamepad works in the browser. |
| W7 | No console exceptions (exception support is "explicitly thrown only", so check the browser console). |
| W8 | The secret scan includes `Builds/WebGL`. |

## 17. Known issues to confirm or track

| Issue | Reference |
|---|---|
| Gamepad A is both Jump and Interact: pressing A at a pickup also jumps | `GDD.md` §4 |
| Designer controls with no visible effect | `CHARACTER_BIBLE.md` §5 |
| Expressions other than blink and talk are never driven | `ANIMATION_BIBLE.md` §3 |
| No Voice volume slider; `AutoLock` setting unused | `UI_BIBLE.md` §6 |
| `quests.json` `requires` (Hidden Vault) is not enforced | `GDD.md` §9 |
| `ROBOT_MODELS.md` notes about unused robot textures and a missing `RobotKind.Bolt` are out of date | `ART_BIBLE.md` §6 |
| The root `.gitignore` does not ignore `Builds/` (the build output folder of `BuildScripts`) | `BUILD_CHECKLIST.md` |
| In the first smoke-test captures (`Captures/smoke/00_main_menu.png`, `01_character_select.png`, 2026-10-03), Kael and Giva were seen **from behind** on the menu stage. At the final check, the working tree changes `MenuStage` to yaw 0 ± 12° ("Models face +Z, toward the camera"). Re-verify, and confirm the heroes face their movement direction in gameplay. | B3, C2 |
| The same character-select capture shows the main-menu column behind the panel. AutoPilot opens the screen with `GameManager.ShowCharSelect()` without popping the menu, which the real New Game button does. The working tree adds `UIScreen.HidesBelow` (character select, designer and credits hide the screens beneath). Re-verify both paths. | C1 |
| The WebGL canvas is 960×600 (Unity default, not set by the setup) while the UI is authored for 16:9 | `BUILD_CHECKLIST.md` 5.5 |
| Smoke captures of the metro and facility (`Captures/smoke/10_metro_start.png`, `10_facility_start.png`) show sign text as bright floating or garbled fragments on and through walls ("SPUR STATION", "PLATFORM 2" doubled). Signs are built with legacy `TextMesh` in `LevelKit.Sign`. A likely cause is the built-in font material drawing without depth testing; not yet diagnosed. | Z2, Z3 |
| `Captures/smoke/11_vault_overview.png` is almost entirely black. Check the vault lighting and exposure, or the capture camera placement. | Z4, PF5 |
