# Echoes of Aether — Third-Party Components and Licences

Status date: 2026-10-04. This file lists only components that the project actually uses. Each licence was checked
against the installed package or asset metadata on this machine:

* Unity packages: `LICENSE.md` and `Third Party Notices.md` in `unity/EchoesOfAether/Library/PackageCache/*`.
* npm packages: `node_modules/<pkg>/package.json`.
* MakeHuman assets: the MPFB pack indexes and asset headers.

"Ships" means the component ends up inside a player build (WebGL or macOS) or the web prototype build. "Tool" means
it is used only to produce assets or to develop and test.

Everything not listed here was made for this project:

* C# code, Blender scripts and their outputs: environment kit (332 assets), the 10-vehicle kit, robots, HD
  outfits, armour, cyberware, procedural hair cards, glowing tattoo maps, loading art, portraits, item art, logo
  and marketing renders
* audio synthesised by the project's code
* game data and writing
* UI textures and icons

No AI image, audio or voice generation was used anywhere: all images are Blender renders or procedural textures,
all audio is synthesised by the project's own DSP code, and there are no synthesised or AI voices (voice-over is
off by default and plays human recordings only; none are recorded yet). The DreamLayer image service was
integrated but generated 0 images and used 0 credits (`DREAMLAYER_ASSET_LOG.md`).

## 1. Unity engine and packages

The Unity Editor 6000.3.25f1 and the Unity runtime embedded in player builds are licensed under the Unity Terms of
Service and the Unity Editor Software Terms. The editor licence is the user's Unity account licence.

Packages from `unity/EchoesOfAether/Packages/manifest.json` (direct) and `packages-lock.json` (dependencies):

| Package | Version | Licence | Use |
|---|---|---|---|
| com.unity.render-pipelines.universal (URP) | 17.3.0 | Unity Companion License (UCL); third-party notice: FXAA3_11 (NVIDIA FXAA licence) | Ships: renderer, post-processing |
| com.unity.render-pipelines.core | 17.3.0 | UCL; third-party notices: RadeonRays 4.1 (MIT), Bullet Physics SDK (zlib), Sobol sampler (MIT) | Ships (URP dependency) |
| com.unity.render-pipelines.universal-config | 17.0.3 | UCL | Ships (URP dependency) |
| com.unity.shadergraph | 17.3.0 | UCL | URP dependency; the project's shaders are hand-written HLSL |
| com.unity.inputsystem | 1.20.0 | UCL | Ships: all input and rebinding |
| com.unity.ai.navigation | 2.0.15 | UCL | Ships: runtime NavMesh (`NavMeshSurface`) |
| com.unity.nuget.newtonsoft-json | 3.2.2 | UCL for the package; bundled **Newtonsoft.Json under MIT** (see §2) | Ships: all JSON data and saves |
| com.unity.ugui | 2.0.0 | UCL | Ships: `EventSystem` for UI Toolkit pointer input |
| com.unity.test-framework | 1.6.0 | UCL | Tool: EditMode tests |
| com.unity.ext.nunit | 2.0.5 | Unity Package Distribution License; third-party: NUnit 3.5 (MIT) | Tool: test dependency |
| com.unity.test-framework.performance | 3.5.0 | UCL; third-party: Perfolizer (MIT) | Tool: dependency (not used directly) |
| com.unity.cinemachine | 3.1.7 | UCL | Installed; **not referenced by game code** (the camera is the custom `CameraRig`) |
| com.unity.splines | 2.9.1 | UCL | Cinemachine dependency; not referenced by game code |
| com.unity.timeline | 1.8.13 | UCL | Installed; **not referenced by game code** (cinematics are C# scripts) |
| com.unity.burst | 1.8.30 | UCL for source, Unity Package Distribution License otherwise; third-party notices: LLVM (Apache 2.0 with LLVM exceptions; legacy LLVM under NCSA), Mono.Cecil (MIT), Smash and xxHash (BSD 2-Clause), musl (MIT), mimalloc (MIT), SLEEF, gRPC for .NET and Google.Protobuf (texts in the package's `Third Party Notices.md`) | Dependency of Collections/Mathematics; the project has no Burst jobs |
| com.unity.collections | 2.6.8 | UCL | Dependency |
| com.unity.mathematics | 1.3.3 | UCL | Dependency |
| com.unity.nuget.mono-cecil | 1.11.6 | UCL; third-party: Mono.Cecil (MIT) | Editor dependency |
| com.unity.searcher | 4.9.5 | Unity Companion Package License v1.0 | Editor dependency |
| com.unity.settings-manager | 2.1.1 | UCL | Editor dependency |
| com.unity.ide.rider | 3.0.40 | MIT (Unity Technologies, JetBrains s.r.o.) | Tool: IDE integration added by the editor |
| com.unity.ide.visualstudio | 2.0.26 | MIT (Unity Technologies, Microsoft Corporation) | Tool: IDE integration added by the editor |
| com.unity.modules.* (built-in modules, version 1.0.0) | — | Part of the Unity engine (Unity terms) | Engine modules |

Licence texts, as cited in the packages' `LICENSE.md`:

* Unity Companion License: https://unity3d.com/legal/licenses/unity_companion_license
* Unity Package Distribution License: https://unity3d.com/legal/licenses/Unity_Package_Distribution_License

## 2. Libraries shipped in the Unity build

**Newtonsoft.Json**, delivered by `com.unity.nuget.newtonsoft-json` 3.2.2. From the package's
`Third Party Notices.md`:

| Component | Licence | Copyright |
|---|---|---|
| Newtonsoft.Json | MIT | Copyright (c) 2007 James Newton-King |
| Json.Net.Unity3D | MIT | Copyright (c) 2016 SaladLab |
| Newtonsoft.Json-for-Unity | MIT | Copyright (c) 2019 Kalle Jillheden (jilleJr) |
| com.newtonsoft.json | MIT | Copyright (c) 2019 Mike Wuetherick |

The MIT licence requires the copyright and permission notice in copies or substantial portions. The notices ship
with the package source; include this table (or the package's `Third Party Notices.md`) in the release credits or
documentation.

## 3. Fonts

| Font | Files in the project | Licence | Copyright |
|---|---|---|---|
| Rajdhani (Medium, SemiBold, Bold) | `unity/EchoesOfAether/Assets/UI/Fonts/Rajdhani/*.ttf` + generated `*_SDF.asset`; licence `Assets/UI/Fonts/Rajdhani/OFL.txt` | SIL Open Font License 1.1 | Copyright (c) 2014, Indian Type Foundry |
| Inter (Regular, Medium, SemiBold, Italic) | `unity/EchoesOfAether/Assets/UI/Fonts/Inter/*.ttf` + generated `*_SDF.asset`; licence `Assets/UI/Fonts/Inter/OFL.txt` | SIL Open Font License 1.1 | Copyright 2020 The Inter Project Authors |

Both ship in the game. The OFL allows bundling and embedding. The fonts must not be sold on their own, and the licence
text must accompany them; it does, beside the TTFs. The web prototype uses the same fonts through `@fontsource`
(§6).

## 4. Blender and the MPFB add-on (tools)

| Component | Version | Licence | Notes |
|---|---|---|---|
| Blender | 5.2.2 LTS | GNU GPL v2 or later | Tool only. Blender's licence does not apply to its output: renders, exported FBX and baked textures are the project's own work. |
| MPFB (MakeHuman plugin for Blender) | 2.0.17 | GPL-3.0-or-later (`blender_manifest.toml`: `SPDX:GPL-3.0-or-later`) | Tool only; its code is not distributed with the game. Scripts in `blender/scripts/` import MPFB services when run inside Blender. |
| Blender's bundled Python and NumPy | bundled with Blender 5.2.2 | PSF License / BSD-3-Clause | Used by the Blender scripts |

## 5. MakeHuman assets

The human characters are built from MakeHuman data read through MPFB. Licences were checked in two places on this
machine: the MPFB asset-pack indexes (`.../mpfb/data/packs/*.json`) and the header of each asset file
(`# license ...` in the `.mhclo` / `.mhmat`). They disagreed for three assets, which were therefore removed and replaced procedurally (see "Removed (replaced procedurally)" below).

### Base data

* **Base mesh** `data/3dobjs/base.obj`: its header states "This asset was explicitly released as CC0 in september
  2020".
* **Rig weights** for the `mixamo_unity` rig (`weights.mixamo_unity.json`): `"license": "CC0"`.
* **Targets.** Shape targets for the phenotype, the customisation morphs and the facial expressions ship in the MPFB
  add-on's `data/targets` folder. Those files carry no licence text locally. MakeHuman releases its targets under
  CC0 like the base mesh, but this was **not verified from a local file**.

### MakeHuman system assets (author `makehuman_system`, pack index licence CC0)

| Type | Assets |
|---|---|
| Skins | young_caucasian_male, young_caucasian_female, young_asian_male, young_asian_female, young_african_male, young_african_female, middleage_caucasian_male, middleage_caucasian_female |
| Eyes, teeth, tongue | eye material `brown`; `teeth_base`, `tongue01` |
| Eyebrows and eyelashes | eyebrow002, eyebrow004, eyebrow009, eyebrow010, eyebrow011; eyelashes01, eyelashes02, eyelashes03 |
| Hair | short01, short02, short03, short04, ponytail01, braid01, bob01, bob02, long01, afro01 |
| Clothes | male_casualsuit05 (Oren), female_elegantsuit01 (Maren) |

The hero skin textures (`Skin_light/medium/tan/dark.png`) are resampled from these CC0 skins with procedural pores,
detail and tattoo ink added by `skin_hd.py`. The hero HD hair styles `curly` and `wavy`, the garment and armour
textures, the glowing tattoo maps and the eye textures are drawn by the project's scripts (no MakeHuman data, no
image generation).

### Community assets (pack index licence CC0)

Source of the list: `blender/scripts/characters.py`; verified against the current NPC manifests.

| Asset | Author (index) | Source page | Used for | Header in the asset file |
|---|---|---|---|---|
| toigo_light_skin_male_bronze | MargaretToigo | makehumancommunity.org/node/1136 | Medium skin tone (male) | no licence line |
| toigo_light_skin_female_bronze | MargaretToigo | makehumancommunity.org/node/1133 | Medium skin tone (female) | no licence line |
| cortu_short_messy_hair | Cortu | makehumancommunity.org/node/2809 | Hero hair option "messy" | no licence line |
| rehmanpolanski_moustache_viking | RehmanPolanski | makehumancommunity.org/node/2615 | Kael's moustache option | CC0 |
| toigo_ankle_boots_male | MargaretToigo | makehumancommunity.org/node/1743 | Oren | CC0 (author "MRT") |
| toigo_ankle_boots_female | MargaretToigo | makehumancommunity.org/node/1738 | Mira | CC0 |
| cortu_cargo_pants | Cortu | makehumancommunity.org/node/2798 | Mira, Tomas | no licence line |
| elvs_crude_t-shirt_male | Elvaerwyn | makehumancommunity.org/node/1416 | Tomas | CC0 |
| culturalibre_male_boots | culturalibre | makehumancommunity.org/node/2548 | Tomas | CC-0 |
| toigo_flats | MargaretToigo | makehumancommunity.org/node/1117 | Maren | CC0 |
| toigo_harem_pants | MargaretToigo | makehumancommunity.org/node/1728 | Nia | CC0 |
| toigo_mj_cloth_shoes | MargaretToigo | makehumancommunity.org/node/1700 | Nia | CC0 |

**Removed in the HD rebuild** (no longer used by any character; their meshes are not in the character manifests. Orphaned leftovers remain in the Unity project and should be deleted by whoever owns `Assets/Art`: `Materials/Cloth_toigo_fisherman_sweater.mat`, `Cloth_donitz_monk_robe_hood_down.mat`, `Cloth_joepal_crude_t-shirt_female.mat`, and import-remap entries for them in `Mira.fbx.meta`, `Tomas.fbx.meta`, `Nia.fbx.meta`):
`toigo_fisherman_sweater` (Mira's sweater), `donitz_monk_robe_hood_down` (Tomas's monk robe) and
`joepal_crude_t-shirt_female` (Nia's t-shirt). Their credits can be dropped from the credit roll. Mira, Tomas and Nia
now wear scripted cyberpunk garments (hoodie, coat, hoodie) made by `outfit_npc.py`.

**Removed (replaced procedurally), 2026-10-04.** Three community assets whose own files carry an AGPL3 header (although
the MPFB pack index lists them as CC0) were removed from the pipeline (decision "Option B"); no mesh, texture or UV
layout derived from them is produced or shipped any more:
`elvs_french_braid_variation` (hero hair option "frenchbraid"), `rehmanpolanski_hair_bun_brown` (hero hair option
"bun" and Maren's hair) and `wdg_scruffy_beard` (Kael's beard option and Oren's beard). Their replacements are made by
the project's scripts with the same ids: "bun" and "frenchbraid" are hair-card styles built with the project's
customisation hair system (`blender/scripts/hair_extra.py` driving `blender/custom/hairlib.py` recipes), Maren's hair is
a procedural low chignon from the same system, and both beards (`Facial_beard`) are procedural hair cards over a thin
shell (`blender/scripts/beard.py`).

The pack indexes also list assets under CC-BY (`vendor/assetpacks.html` mentions CC-BY target and mesh packs). **None of the assets
used by `characters.py` is CC-BY**, as checked above, so no attribution is legally required for the character
assets. The authors are credited as a courtesy.

The derived meshes and textures in `unity/EchoesOfAether/Assets/Art/Characters/` ship in the game. Only CC0
assets appear in the NPC outfits that remain: cargo pants (Mira, Tomas), crude t-shirt (Tomas), harem pants (Nia),
casual suit (Oren), elegant suit and flats (Maren).

## 6. Web prototype npm dependencies

From `package.json`; licences read from `node_modules/<pkg>/package.json`. None of these are in the Unity build.

### Runtime dependencies (in the prototype's Vite build)

| Package | Version | Licence |
|---|---|---|
| three | 0.186.1 | MIT |
| @dimforge/rapier3d-compat | 0.21.0 | Apache-2.0 |
| @fontsource/inter | 5.3.0 | OFL-1.1 |
| @fontsource/rajdhani | 5.3.0 | OFL-1.1 |

### Development dependencies (tools only)

| Package | Version | Licence | Use |
|---|---|---|---|
| vite | 7.3.6 | MIT | Prototype dev server and build. Also serves the prototype for `tools/audio/render.mjs` and `tools/anim/sample_clips.mjs`. |
| typescript | 5.9.3 | Apache-2.0 | Type checking |
| @types/three | 0.186.0 | MIT | Types |
| @playwright/test, playwright, playwright-core | 1.63.0 | Apache-2.0 | Prototype tests; headless Chromium for the audio render and animation sampling tools; UI icon rasterisation (`Assets/Editor/UI/Tools~/rasterize_icons.mjs`) |

Transitive development packages present in `node_modules`:

| Package | Version | Licence |
|---|---|---|
| esbuild (+ @esbuild/darwin-arm64) | 0.28.2 | MIT |
| rollup (+ @rollup/rollup-darwin-arm64) | 4.64.0 | MIT |
| postcss | 8.5.28 | MIT |
| nanoid | 3.3.19 | MIT |
| picocolors | 1.1.1 | ISC |
| source-map-js | 1.2.2 | BSD-3-Clause |
| fdir | 6.5.0 | MIT |
| picomatch | 4.0.7 | MIT |
| tinyglobby | 0.2.17 | MIT |
| fsevents (optional) | 2.3.3 | MIT |
| @types/estree | 1.0.9 | MIT |
| @types/stats.js | 0.17.4 | MIT |
| @types/webxr | 0.5.24 | MIT |
| @tweenjs/tween.js | 23.1.3 | MIT |
| fflate | 0.8.3 | MIT |
| meshoptimizer | 1.1.1 | MIT |

* `@tweenjs/tween.js`, `fflate` and `meshoptimizer` arrive through `@types/three`.
* The Chromium binary that Playwright downloads is used only by local tools. It is covered by Chromium's own
  licences (BSD-3-Clause and bundled third-party notices) and is not distributed.

## 7. Other tools (not distributed)

| Tool | Licence | Use |
|---|---|---|
| Node.js 22.20 | MIT (plus bundled third-party licences) | Validators, audio, animation and VO tools |
| Python 3.14 | PSF License | `tools/unitycheck/check.py`, `tools/vo/make_vo_script.py`, `blender/env/write_manifest.py` |
| Roslyn compiler and .NET runtime bundled with the Unity editor | MIT | Invoked by `tools/unitycheck/check.py` |
| DreamLayer CLI (`dreamlayer@0.4.0-beta.4` via `tools/dreamlayer/dl.sh`) | — | Integrated but never used: 0 images generated, 0 credits used, nothing shipped (see `DREAMLAYER_ASSET_LOG.md`). No API key is stored in the repository. |

## 8. Animation: CMU Graphics Lab Motion Capture Database (ships)

| Component | Licence | Use |
|---|---|---|
| CMU Graphics Lab Motion Capture Database, http://mocap.cs.cmu.edu (original ASF/AMC files, 32 trials from 21 subjects, retrieved 2026-10-03) | Free to use, including in commercially sold products; the raw data may not be resold. Credit required (below). | Source of all 42 humanoid clips in `Assets/Art/Animations/Anim_Male.fbx` and `Anim_Female.fbx`, after retargeting and cleanup by `blender/anim/cmu_retarget.py` |

Required credit line (game credits and docs):

> The data used in this project was obtained from mocap.cs.cmu.edu.
> The database was created with funding from NSF EIA-0196217.

* Only the retargeted, edited clips ship. The raw downloads, BVH conversions and caches are not committed
  (`blender/anim/.gitignore`) and are fetched with `python3 tools/anim/cmu.py fetch-all`.
* Per-clip sources (subject, trial, frame range) and the edits made are listed in `ANIMATION_CREDITS.md`.
* No other motion capture library and no AI-generated animation was used. Finger poses are hand-set in the
  pipeline because the CMU skeleton has no finger joints.

## 9. Own work and non-licensed content

* **Vehicles** (`Assets/Art/Vehicles`, 10 vehicles, 26 materials): modelled and textured by `blender/vehicles`
  scripts; no third-party meshes or textures. All badges, plates and signs use an invented glyph script.
* **City kit** (`Assets/Art/Environment`, 332 assets, 94 materials): `blender/env` scripts. Signage is an invented
  glyph script, with no real brands or words.
* **Customisation library** (`Resources/Characters/Custom`): procedural hair cards from `blender/custom`. The
  catalogue is incomplete (see `CHARACTER_BIBLE.md` §5).
* **Fonts in renders:** Rajdhani Bold / SemiBold (OFL 1.1) for the logo only.
* **Music, effects, ambience:** synthesised by the project's code. **Voices:** none.


## Voice-over (added 2026-10-06)

| Component | Licence | Use |
|---|---|---|
| Kokoro-82M (hexgrad) model weights and voices | Apache License 2.0 | Offline text-to-speech that rendered all 161 voice lines (`tools/vo/gen_voices.py`) |
| kokoro-onnx (thewh1teagle) | MIT | ONNX runtime wrapper used by the generator |
| onnxruntime (Microsoft) | MIT | Inference runtime for the generator |
| espeak-ng (via espeakng-loader) | GPL-3.0 | Phonemizer used only by the offline generator; **not shipped** with the game |

Only the generated WAV files ship with the game; the model and tools stay in `tools/vo/` (git-ignored).

## Animation: Mixamo by Adobe (ships when present, 2026-10-06)

| Component | Licence | Use |
|---|---|---|
| Mixamo animations (https://www.mixamo.com, Adobe; downloaded by the project owner with their Adobe account, "FBX for Unity, Without Skin", Y Bot skeleton) | Adobe General Terms of Use and the Mixamo FAQ terms. Use is royalty-free in personal, commercial and non-profit projects, including games. The animations **may not be redistributed or sold as standalone files** or as part of an animation library. | Replace CMU clips of the same name. `MixamoImporter` copies them from `incoming/mixamo/` into `Assets/Art/Animations/Mixamo/` and imports them as humanoid clips. Players only receive the compiled animation data inside the build. |

* Which clip slots use Mixamo is recorded per style in `Assets/Art/Animations/clip_sources.json`
  (`"source": "mixamo"`). Every other slot is CMU (section 8).
* **Raw files.** The raw Mixamo FBX copies under `Assets/Art/Animations/Mixamo/` and the drop folder `incoming/` must
  not be published. If the repository or a source package is made public, exclude both folders (for example with
  `.gitignore`).
* **Credit.** No credit line is required. The credits may say "Additional animation: Mixamo (Adobe)".
* **Status.** The importer was tested with clips made from the CMU data in Mixamo's file layout. No real Mixamo
  file is in the project yet (`clip_sources.json`: 0 Mixamo slots).

## Animation: Quaternius Universal Animation Library (ships, 2026-10-08)

| Component | Licence | Use |
|---|---|---|
| Universal Animation Library (UAL 1, "Standard", `AnimationLibrary_Unity_Standard.fbx`) and Universal Animation Library 2 (UAL 2, "Standard", `UAL2_Standard.fbx`) by Quaternius, https://quaternius.com (downloaded by the project owner, 2026-10-07) | CC0 1.0 Universal (public domain dedication), https://creativecommons.org/publicdomain/zero/1.0/. No attribution required; redistribution allowed. | Primary source of 22 humanoid clip slots per style (idle, jump/fall/land, talk, sit, folded-arms NPC idle, hit, death, interact, pickup, Kael's punches, blade smash, pulse and pistol aim/shot, Giva's slashes and echo throw). `MixamoImporter` copies the two FBX files from `incoming/ual/` into `Assets/Art/Animations/UAL/` and builds per-hero clips in `UAL/Generated/`. |

* Order of sources per clip slot: Mixamo (only if files are dropped in `incoming/mixamo/`), then UAL, then CMU
  (section 8). The slot-by-slot table is `Assets/Art/Animations/clip_sources.json` (`"source": "ual"`).
* The FBX copies under `Assets/Art/Animations/UAL/` may be committed and redistributed (CC0). The female mannequin of
  UAL 2 is not used (the clips are retargeted through Unity's humanoid avatars).
* **Credit.** Not required. The in-game credits say "Universal Animation Library 1 & 2 by Quaternius (quaternius.com,
  CC0)" as a courtesy.

## Concept references (2026-10-06)

Two character concept references were generated with DreamLayer (see `DREAMLAYER_ASSET_LOG.md`). They are used as
modelling references only and are not shipped in the game.
