# Echoes of Aether — Project Audit

Status date: 2026-10-04. Written from reading the code, the data and `tools/validation/validate_unity.mjs`; Unity was
not opened. Section 7 (final QA) was filled in by the lead on 2026-10-05.

## 1. How to read this

| Status | Meaning |
|---|---|
| **Verified** | Checked by a tool that ran (validator, smoke report) or by reading data/assets that exist on disk. |
| **Implemented-unverified** | Code exists and (where stated) compiles, but nobody has confirmed the behaviour by playing. |
| **Missing** | Referenced or planned, but not present in the repository. |

"Verified" never means play-tested by a person. There is no recorded manual play session in the repository.

## 2. What was run for this audit

`node tools/validation/validate_unity.mjs` (needs no Unity), run 2026-10-04:

```
17 PASS, 1 WARN, 0 FAIL
WARN [audio] voice-over: 0 of 161 lines recorded (subtitle-only; see docs/VO_SCRIPT.md)
```

Checks that passed: JSON data parses and matches `src/data`; no duplicate ids; 6 zones registered; 9 spawn names and
all exits resolve; 12 Aether Fragments, 6 Memory Recordings, 5 Hidden Caches placed; 15 encounters resolve to enemy
factories; 9 quests and 45 objectives found in the C# zones; 32 dialogues and 158 nodes valid; 24 input actions; 71
audio clips and 45 referenced sounds resolve; 42 retargeted animation clips (both styles); character FBX exports
present; 332 environment assets and the 84 props / 39 materials used by zones resolve; save envelope has CRC32,
schema validation, backup and atomic writes; editor setup and builders present; **no API keys or secrets in 191
scripts, data files and docs**.

The optional `--compile` check (`tools/unitycheck/check.py`, offline Roslyn compile of the player assembly) was
started during this audit and finished after about 7 minutes (other agents were editing code at the same time): editor Assembly-CSharp OK (104 files); **editor Assembly-CSharp-Editor FAILED (1 error)** and **player Assembly-CSharp FAILED (2 errors)**; summary 18 PASS, 1 WARN, 2 FAIL (release blocked). The error text was not captured. These may be transient edits by parallel agents; re-run `node tools/validation/validate_unity.mjs --compile` once the code is quiet.

`Captures/smoke/report.json` (an earlier automated run, not repeated here): `story: PASS`, 364.5 s, flags through
`game_complete`, `errors: []`, 3 warnings (an inactive animator object, two out-of-order lore dialogue requests). The
14 screenshots `s01`-`s14` came from the same run. It was produced before the latest character, city and vehicle
changes, so treat it as evidence for the story flow only.

## 3. Systems, locations and status

Paths are under `unity/EchoesOfAether/Assets/` unless noted. Line counts are approximate C# totals per folder.

### 3.1 Core game

| System | Where | Status | Notes |
|---|---|---|---|
| Bootstrap, game state, quests, inventory, powerups, dialogue, cinematics runtime | `Scripts/Game/` (16 files, ~2.7k lines) | Verified (data) / implemented-unverified (behaviour) | Quest, dialogue and item ids validated against the zones; the smoke run drove the whole story |
| Data (items, quests, dialogue, speakers, zones, hints, locale) | `Resources/Data/*.json`, mirrors `src/data` | Verified | Validator: identical to authoring data |
| Save system (3 slots, CRC32, schema check, backup, atomic write, thumbnails) | `Scripts/Game/SaveSystem.cs`, `GameState.cs` | Verified (presence) / implemented-unverified (behaviour) | Validator checks the code features exist; no save/load round trip recorded |
| Settings (gameplay, graphics, audio, controls, accessibility, language) | `Scripts/Game/Settings.cs`, `UI/Screens/SettingsScreen.cs` | Implemented-unverified | Language is English only |
| Input and rebinding | `Scripts/Core/GameInput.cs` | Implemented-unverified | 24 actions validated; defaults match `GDD.md` §4 |
| Event bus and contracts | `Scripts/Core/` | Implemented-unverified | |

### 3.2 Characters and customisation

| System | Where | Status | Notes |
|---|---|---|---|
| Seven HD character FBX + manifests (Kael, Giva, Oren, Mira, Tomas, Maren, Nia) | `Art/Characters/<Name>/` (Giva's folder is `Lyra`) | Verified (files and manifests exist, pipeline `hd-2026-10`) | Whether the Unity prefabs were rebuilt from the HD exports is not confirmed |
| Character prefabs | `Resources/Characters/*.prefab` (7) | Implemented-unverified | Built by `Editor/Characters/CharacterBuilder.cs` |
| Hero actors, combat, companion AI | `Scripts/Actors/Hero.cs`, `Scripts/Combat/` | Implemented-unverified | Unit tests exist for combat math (`Tests/EditMode/Combat/CombatTests.cs`, 271 lines); no run recorded |
| Appearance model and presets | `Scripts/Game/Appearance.cs`, `Scripts/Actors/CharacterModel.cs` | Implemented-unverified | |
| Designer screen (6 sections) | `Scripts/UI/Screens/DesignerScreen.cs` | Implemented-unverified | |
| Customisation catalog loader and attachment binder | `Scripts/Actors/Customization.cs` | Implemented-unverified | |
| **Catalog content** (`Resources/Characters/Custom/catalog.json`, eyewear, armour sets, tattoo designs) | `blender/custom/` (generators) | **Missing** | No `catalog.json`; no eyewear, armour or tattoo-design assets in the project |
| Custom hair library | `Resources/Characters/Custom/Hair`, `Thumbs` | Partial | 9 hair FBX and 15 thumbnails; the sets do not line up (`CHARACTER_BIBLE.md` §5) |
| Glowing tattoo maps and emission | `Skin_Tattoo.png` in the hero manifests; `CharacterModel` | Verified (files) / implemented-unverified (look in game) | |
| Facial blink and talk | `CharacterModel.cs` | Implemented-unverified | |

### 3.3 Animation

| System | Where | Status | Notes |
|---|---|---|---|
| 42 humanoid clips x 2 styles (CMU mocap) | `Art/Animations/Anim_Male.fbx`, `Anim_Female.fbx`, `clips_meta.json` | Verified (42 per style in the metadata; validator PASS) | Credit line required and present in the in-game credits and `ANIMATION_CREDITS.md` |
| Animator controllers, upper-body mask, foot IK | `Art/Animations/*.controller`, `UpperBody.mask`, `Scripts/Actors/HumanoidPolish.cs` | Implemented-unverified | Clips `interact`, `wave`, `kneel_work`, `npc_look`, `sit` have no caller |
| Robot procedural animation | `Scripts/Enemies/Robot*.cs` | Implemented-unverified | |

### 3.4 Enemies, world and city

| System | Where | Status | Notes |
|---|---|---|---|
| Enemies (drone, sentinel, warden, stalker, Guardian boss) | `Scripts/Enemies/` (10 files, ~3.9k lines) | Verified (15 encounters resolve to factories) / implemented-unverified (balance, behaviour) | |
| Six zones | `Scripts/World/Zones/*.cs` | Verified (objectives, markers, exits resolve) / implemented-unverified | |
| Open city: 721 x 625 m, 5 districts | `Scripts/World/City/*.cs`, `Scripts/World/Zones/Plaza/OpenCity.cs` | Implemented-unverified | Layout, streets, buildings, crowd, traffic, culling; performance in WebGL not measured |
| Environment kit (332 assets, 94 materials) | `Art/Environment/`, `Resources/Env/` | Verified (validator resolves the used props and materials) | |
| City landmark buildings, street props, lighting, sky/rain, graphics pass | `Art/CityLandmarks`, `Art/CityStreet`, `Art/FX`, `Scripts/World/Kit/*`, `Shaders/*` | Verified (zone tour and city tour 0 errors, before/after captures) | 15 landmarks, 47 street assets, Cyberpunk-style palette, SSR wet streets, Blender sky and rain |
| Vehicle kit (10 vehicles) | `Art/Vehicles/`, prefabs in `Resources/Env/Props` | Verified (files, manifest, `VEHICLES.md`) | Traffic uses sedan, taxi, coupe, van and bike; the wreck and burnt van are dressing. Hover cars and hover truck fly the sky lanes (`CyberCity` SkyTraffic) |
| Weather, atmosphere, post-processing | `Scripts/World/Kit/Atmosphere.cs`, `Weather.cs`, `Scripts/Game/Rendering.cs` | Implemented-unverified | |
| VFX | `Scripts/VFX/` | Implemented-unverified | |

### 3.5 UI

| System | Where | Status | Notes |
|---|---|---|---|
| UI Toolkit screens (menu, character select, designer, HUD, dialogue, pause, panels, settings, saves, credits, death) | `Scripts/UI/` (19 files, ~4.8k lines), `UI/` | Implemented-unverified | `UI_BIBLE.md` |
| Voice-over choice at game start and in Settings | `UI/Screens/MenuScreens.cs`, `SettingsScreen.cs`, `Game/Settings.cs` | Verified (read in code) | Default `false`; no behaviour change is audible because no recordings exist |
| Art used by UI (6 loading images, 9 portraits, 18 item images, logo) | `Resources/Art/` | Verified (files exist) | Not confirmed to be re-rendered after the latest character/city art |

### 3.6 Audio and voice

| System | Where | Status | Notes |
|---|---|---|---|
| Synthesised music, SFX, ambience | `Scripts/Audio/AudioManager.cs`, `Resources/Audio/*`, `tools/audio` | Verified (71 clips; 45 referenced sounds resolve) | All audio is synthesised by project code |
| Voice-over playback | `Scripts/Audio/VoiceOver.cs` | Implemented-unverified | Human recordings only; `Resources/Audio/Voice/<dialogue>/<node>[_<speaker>]` |
| **Voice recordings** | `docs/VO_SCRIPT.md`, `tools/vo/` | **Missing** | 0 of 161 lines recorded (validator WARN). No synthesised or AI voice exists or is planned |

### 3.7 Tools, tests and builds

| Item | Where | Status |
|---|---|---|
| Offline validator | `tools/validation/validate_unity.mjs` | Verified (ran, 17 PASS / 1 WARN / 0 FAIL) |
| Offline C# compile check | `tools/unitycheck/check.py` | Verified: **FAILED** on 2026-10-04 (3 errors, see §2); re-run |
| EditMode tests | `Tests/EditMode/Combat/CombatTests.cs` | Implemented-unverified (no run recorded) |
| PlayMode tests | `Tests/PlayMode/` | **Missing** (folder has no test scripts) |
| In-editor smoke test and autopilot | `Editor/Testing/SmokeTest.cs`, `Scripts/Dev/AutoPilot*.cs` | Verified by the 2026-10-04 smoke report (story flow) |
| Build scripts (WebGL, macOS) | `Editor/Build/BuildScripts.cs`, `docs/BUILD_CHECKLIST.md` | Implemented-unverified. **No `Builds/` folder exists**: no build has been produced |
| Capture scripts | `tools/capture` | Prototype capture tooling |
| Secrets scan | validator `[secrets]` | Verified (no keys in 191 files) |

## 4. Content and legal checks

| Claim | Status |
|---|---|
| No AI-generated images in the game or marketing | Verified by provenance: all art is Blender/procedural (`marketing/ART_CREDITS.md`, `ART_BIBLE.md`). DreamLayer was integrated and generated 0 images, 0 credits (`DREAMLAYER_ASSET_LOG.md`). The absence of AI imagery cannot be proved from files alone; it rests on the pipeline scripts |
| No synthesised or AI voices | Verified: no speech-synthesis API in the C# (validator rule, see `AUDIO_BIBLE.md` §6); voice-over off by default |
| CMU mocap credit present | Verified in `MenuScreens.cs` credits and `ANIMATION_CREDITS.md` |
| CC0 characters | **Verified.** Pack indexes say CC0; the three assets whose files carried an AGPL3 header were removed and replaced procedurally on 2026-10-04 (`THIRD_PARTY_LICENSES.md` §5) |
| Removed garments (Mira's sweater, Tomas's monk robe, Nia's t-shirt) | Meshes gone from the manifests; three orphan `.mat` files remain in `Art/Characters` |
| Marketing images exist | **Missing.** `marketing/` has only markdown. The four store images named in `ART_CREDITS.md` are not rendered |

## 5. Inconsistencies found between code, data and docs (2026-10-04)

1. `Appearance.Default("lyra")` sets hair `long_curls` / `#3b2350`; the HD model default is `wavy` / `#2b1b14`. Kael: `curly_medium` vs the model's `curly`. These ids are catalog ids, so they only resolve once the catalog exists.
2. The customisation catalog and most of its content are absent although the designer, builder and docs refer to them.
3. `Resources/Characters/Custom/Thumbs` has 15 hair thumbnails but `Hair` has 9 FBX files.
4. The hover vehicles have prefabs but no consumers.
5. `blender/scripts/outfit_npc.py` still documents Tomas's "LED trim on the robe" although the monk robe was removed.
6. The three licence-header mismatches above.
7. Stale `Cloth_*` materials for the three removed garments remain in `Art/Characters`.
8. Hero heights in the earlier docs (Kael 1.83 m, Giva 1.58 m) did not match the manifests (1.85 m, 1.73 m); corrected.
9. `ART_BIBLE.md` said the art direction avoided saturated cyberpunk neon; the city, vehicles and characters are now neon cyberpunk. Rewritten, but the per-zone mood table in `ART_BIBLE.md` §3 still holds prototype values.
10. `Captures/smoke` screenshots predate the HD/city/vehicle changes.

## 6. Missing or open items

- Voice recordings (0 of 161).
- Customisation: default hair cards (hard hairline) and armour refit to the remade heroes.
- Re-render portraits / key art / plaza and rooftop loading screens with the remade heroes.
- A human play session; WebGL performance measurement.
- PlayMode tests.

## 7. Final QA

Filled in by the lead on 2026-10-05; details in `FINAL_QA_REPORT.md` and `VISUAL_AUDIT.md`.

| Section | Result |
|---|---|
| Offline compile check (`tools/unitycheck/check.py --player`) | 0 errors (editor + player) |
| Project validator (`validate_unity.mjs`) | 17 PASS, 1 WARN (voice-over not recorded), 0 FAIL |
| Unity setup / character, kit and customization builds | Run repeatedly in batch mode; 0 failed prefabs, 0 Rig Errors |
| EditMode test run | Not run (no EditMode suite beyond the batch-mode autopilots) |
| Automated story play-through (M1–M5, ending, credits) | PASS, 279 s, 0 errors |
| Manual play-through by a human as Kael and as Giva | **Not done by the development agents** |
| Open-city frame time | macOS dev player, M4 1080p High: 84.8 fps avg (city), 129.8 fps fullscreen combat; WebGL not measured |
| Customisation: glasses, armour sets, tattoo designs selectable and visible | Verified in designer captures; glasses auto-fit to the face; armour not yet refit to the remade bodies |
| Voice-over choice persists; no audio change without recordings | Implemented; 0 recordings |
| WebGL build size and load time | 202 MB (512 px textures, armour sets desktop-only); load time not measured |
| macOS build | Built: `Builds/macOS/EchoesOfAether.app` |
| Store screenshots after the city art pass | City/combat captures in `Captures/gfx_after/`; key art and portraits still use the previous hero models |
| Licence decision on the three AGPL3-headed MakeHuman assets | Done: removed and replaced procedurally (Option B, 2026-10-04) |
