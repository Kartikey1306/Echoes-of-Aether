# Echoes of Aether — Project Architecture

Updated 2026-10-03.

**The primary project is the Unity 6 port in `unity/EchoesOfAether`.** The TypeScript/three.js web prototype in
`src/` is kept as the **design reference**: its data, tuning numbers, level layouts and procedural recipes are what
the Unity port reproduces.

Detailed documents live in `docs/`:

| Document | Covers |
|---|---|
| `TECHNICAL_ARCHITECTURE.md` | Unity runtime, systems and tooling |
| `GDD.md` | Game design |
| `ART_BIBLE.md` | Visual direction and art pipelines |
| `CHARACTER_BIBLE.md` | Cast and character customisation |
| `ANIMATION_BIBLE.md` | Humanoid and robot animation |
| `AUDIO_BIBLE.md` | Music, ambience, SFX and voice-over |
| `UI_BIBLE.md` | Interface |
| `QA_CHECKLIST.md` | Manual and automated tests |
| `BUILD_CHECKLIST.md` | Build and upload steps |
| `THIRD_PARTY_LICENSES.md` | Third-party components and licences |
| `DREAMLAYER_ASSET_LOG.md`, `DREAMLAYER_INTEGRATION.md` | DreamLayer status |
| `VO_SCRIPT.md` | Voice-over recording script |

## Environment (checked 2026-10-03)

| Item | Found |
|---|---|
| Machine | Apple M4 (10-core GPU, Metal 4), 16 GB RAM, macOS 26.6.2 |
| Game engine | Unity 6000.3.25f1 (6.3 LTS) via Unity Hub, with the WebGL and Mac Standalone build modules. The editor licence is active; a batch-mode project setup ran successfully on 2026-10-03. |
| DCC | Blender 5.2.2 LTS with the MPFB 2.0.17 add-on (MakeHuman CC0 asset packs installed in the Blender user data folder) |
| Runtimes | Node 22.20, Bun 1.3, Python 3.14 |
| Browser automation | Playwright 1.63 (Chromium), used by the prototype tests and the audio and animation export tools |
| DreamLayer | Configured early in the project but never used; no images generated. The user has since directed that no AI-generated imagery be used (see `docs/DREAMLAYER_ASSET_LOG.md`). |

## Engine decision

The project started as a web prototype (TypeScript, three.js r186, Rapier3D, Vite) because no engine or DCC tool was
installed at the start, and everything had to be creatable and testable from code. The prototype reached a complete,
playable main story (commit `cb1d204`: "All six zones, stalker and guardian, cinematics, full main-story playthrough
passing").

The game is now being ported to **Unity 6.3 LTS with URP** for:

* a stronger renderer
* proper skinned characters made in Blender
* the Unity WebGL and macOS players

| Field | Unity port | Web prototype (reference) |
|---|---|---|
| Engine | Unity 6000.3.25f1 | Custom layer on three.js r186 |
| Language | C# 9 (`namespace EOA`) | TypeScript 5.9 |
| Renderer | URP 17.3, Forward+, HDR, ACES, bloom, realtime lighting | WebGL2, HDR composer, ACES, bloom |
| Physics | Unity Physics (CharacterController, queries), AI Navigation runtime NavMesh | Rapier3D 0.21 (WASM) |
| UI | UI Toolkit, built in C# | DOM/CSS |
| Data | `Assets/Resources/Data/*.json` (byte-identical copy of `src/data`) via Newtonsoft.Json | `src/data/*.json` |
| Build targets | WebGL (itch.io) and macOS | Web (Vite build) |

## Asset formats and pipeline

| Asset | Source | Format in Unity |
|---|---|---|
| Kael, Giva and 5 NPCs | MPFB/MakeHuman CC0 assets plus project outfit scripts (`blender/scripts/`) | FBX + manifest + textures in `Assets/Art/Characters/<Name>/` → prefabs in `Resources/Characters` |
| Humanoid animation | Prototype procedural clips sampled (`tools/anim/sample_clips.mjs`) and retargeted (`blender/scripts/retarget.py`) | `Assets/Art/Animations/Anim_{Male,Female}.fbx` + `clips_meta.json` → Animator controllers |
| Enemies and BOLT | `blender/robots/` scripts (rigid parts, 20-bone contract) | `Assets/Resources/Models/Robots/*.fbx` |
| Robot animation | C# procedural animator ported from the prototype | code (`RobotAnimator`, `RobotClips`) |
| Environment props and materials | `blender/env/` scripts (185 assets, 55 tileable PBR materials) | `Assets/Art/Environment/` → prefabs and materials in `Resources/Env` |
| Zone layouts | C# zone classes ported from `src/world/zones/*.ts` (`ProceduralZone` + `LevelKit`) | Generated at load time |
| Audio | Prototype WebAudio recipes rendered offline (`tools/audio/render.mjs`) | WAV in `Assets/Resources/Audio` + `manifest.json` |
| Voice-over | Human recordings only (script in `docs/VO_SCRIPT.md`); none recorded yet | `Resources/Audio/Voice/<dialogue>/<node>.wav` (not present) |
| 2D art (logo, loading art, portraits, item art, marketing) | Blender Cycles renders of game assets (`blender/art/scripts/artkit.py` + per-scene scripts); in progress | `Assets/Resources/Art/*` (loading art for plaza and metro so far), `marketing/` (not present yet) |
| UI icons | Prototype SVG icon set rasterised to PNG | `Assets/Resources/UI/Icons` |
| Fonts | Rajdhani and Inter (SIL OFL 1.1) | `Assets/UI/Fonts` |

No AI image or voice generation is used anywhere.

## Directory structure

```
unity/EchoesOfAether/   Unity project (primary): Assets/{Scripts,Editor,Resources,Art,Shaders,UI,Plugins,Tests}
blender/                env/ (environment kit), robots/, scripts/ (characters, retarget), art/ (2D renders),
                        anim/ (sampled clips, git-ignored), out/ (preview renders)
tools/                  validation/ (validate_unity.mjs; validate.mjs for the prototype), unitycheck/ (offline C#
                        compile check), audio/ (render + verify), anim/ (clip sampler), vo/ (VO script generator),
                        dreamlayer/ (unused CLI wrapper), test/ + capture/ (prototype Playwright tests)
docs/                   design, art, audio, UI, technical, QA and build documents
src/                    web prototype (design reference): core, render, physics, audio, actors, world, game, vfx, ui, data
public/, index.html     prototype static files
dreamlayer/             empty folders from the original DreamLayer plan (no images)
```

## Rendering strategy (Unity)

* **Lighting.** Realtime only: one shadow-casting directional light per zone (2048 shadow map, 2 cascades, 70 m),
  per-pixel additional lights without shadows, and a realtime reflection probe rendered once per zone.
* **Geometry.** Static zone geometry is merged per material and per 32 m cell. Props are prefabs with two LODs.
  The SRP Batcher is on.
* **Atmosphere.** Fog is exponential-squared. The sky is a custom shader with lightning flashes. Rain is camera-local
  particle systems.
* **Effects.** Built-in Particle System only (WebGL-safe). The realtime light budget is 24 per zone.

## Performance targets

These targets come from the prototype and have **not yet been measured on the Unity build**:

* 60 FPS at 1080p on Apple M4 at the High preset (desktop)
* zone load under 3 s

The F1 debug overlay (development builds) and the smoke-test report (`Captures/smoke/report.json`) report frame time,
memory and zone load times.

## World streaming

Exactly one zone is resident at a time:

1. `ZoneRuntime` builds it procedurally (or loads an optional `Zone_<id>` scene).
2. It bakes a runtime NavMesh and spawns the zone's actors.
3. The loading screen shows real staged progress.

Zone transitions happen at physical exits (stairs, tunnels, lifts, ladders) through fades.
