# Echoes of Aether — Art Bible

Status date: 2026-10-04. This document covers the visual direction and the production pipelines that actually exist in
this repository. Every 3D asset in the Unity project was produced by scripts in `blender/` (Blender 5.2.2 LTS,
headless) or by the game's own C# code. Recent changes: HD character rebuild, 10-vehicle kit, cyberpunk city kit
(332 assets) and the open-city district.

## Image-generation policy

**No AI image generation is used for any game or marketing image** (user directive). All art comes from one of these
sources:

* Blender-built geometry and textures, produced by the project's own Python scripts.
* MakeHuman/MPFB CC0 character assets assembled in Blender.
* Procedural meshes and materials created at runtime by the game's C# code.
* Blender Cycles renders of scenes built from the above.

DreamLayer (an AI image service) was integrated early in the project but generated 0 images and used 0 credits;
nothing from it is in the game or in marketing. See `DREAMLAYER_ASSET_LOG.md`.

## 1. Direction

**Neon-noir cyberpunk, on top of a ruined research colony.** Aether-9 is a city that stopped seven years ago, now
shown as a dense, wet, neon-lit district:

* wet asphalt and concrete, tenements and podium towers, canal and skywalks
* neon tubes, LED billboards, holographic ad frames, lantern strings, cable bundles, vending machines and ramen stalls
* cyber vehicles, parked and driving
* rain, fog and practical light carry the mood

All signage is an **invented glyph script** (no real words, brands or logos), in the city kit, the vehicles and the
renders.

**Characters are techwear.** Kael and Giva wear armoured and layered techwear with glowing seams, cyberware and
glowing circuit tattoos; the NPCs wear cyberpunk street-survivor layers (see §7).

**Palette logic.** Cool cyan and hot magenta are the neon pair; violet and amber are secondary. The Aether keeps its
own cyan and violet identity (monument, Core, conduits, Echo Sight). Enemy telegraphs stay red and orange, so
combat reads against the neon.

**Readable combat.** Enemies telegraph in red and orange, player effects are cyan (Kael) or violet (Giva), and
success states are green.

**Scope note.** The cyberpunk direction is what the open city, the vehicles, the characters and the 2D art follow.
The per-zone mood table in §3 holds the prototype's values for fog, exposure and bloom and has not been re-tuned for
the neon look; the indoor zones (metro, facility, vault, core) were not part of the recent art pass.

## 2. Palette

### World accents (sRGB)

| Use | Colour | Where defined |
|---|---|---|
| Aether cyan | `#5fd8ff` | `EnvMaterials` fallback `emit_cyan`, `EOA_Aether.shader` default, `blender/art/scripts/artkit.py` `CYAN` |
| Aether violet | `#a77bff` | `emit_violet`, Aether shader secondary, `artkit.py` `VIOLET` |
| Kael glow (default) | `#56b8ff` | `Appearance.Default("kael")` |
| Kael glow and tattoos (default) | `#00e5ff` cyan primary, `#ff2bd6` magenta secondary | `Appearance.Default("kael")` (the older `#56b8ff` is superseded) |
| Giva glow and tattoos (default) | `#ff2bd6` magenta primary, `#9b5cff` violet secondary (model palette `#8a5bff`) | `Appearance.Default("lyra")`; internal id `lyra` |
| Neon pair | cyan `#00e5ff`, magenta `#ff2bd6` | character manifests, vehicles (`veh_neon`, `veh_underglow`) |
| Vehicle emissives | headlight `#dbedff`, taillight `#ff0b0f`, underglow `#00ccff`, neon `#ff1ab8`, hazard `#ff7305`, thruster `#4db3ff` | `Assets/Art/Vehicles/manifest.json` tints (HDR x3.5-6) |
| Kael combat FX | `#5fb8ff` / `#6fc8ff` / `#9fe0ff` | `Hero.cs` |
| Giva combat FX | `#a47dff` / `#b48cff` / `#c8a8ff` | `Hero.cs` |
| Practical warm light | `#ffa21f` (amber), `#ffd2a0` (warm panel), `#ffb878` (lit windows) | env materials |
| Enemy telegraph / danger | `#ff5a3a` (sentinel), `#ff3b30` (warden), `#ff3a2e` (emit_red) | `Sentinel.cs`, env materials |
| Success / powered | `#52ff9a` | env `emit_green`, metro junctions |
| BOLT | shell `#9a7a2a`, glow `#ffc24a` | `Npc.cs` |

### UI tokens

UI tokens are deliberately a touch softer than the world accents (`Assets/UI/Styles/eoa.uss`):

| Token | Value |
|---|---|
| text | `#dfe7ee` |
| cyan | `#5fd4f0` |
| violet | `#a68bff` |
| amber | `#ffb45e` |
| red | `#ff5a4a` |
| green | `#73e6b0` |
| background | `rgba(10,14,19,0.92)` |

See `UI_BIBLE.md`.

### Robot palettes

From the enemy scripts. Shell and frame are tinted over the worn-metal texture; glow is HDR.

| Robot | Shell | Frame | Glow (intensity) |
|---|---|---|---|
| Drone | `#2b3036` | `#5a6068` | `#5fd8ff` (3.0) |
| Sentinel | `#4a4f56` | `#24272c` | `#ff5a3a` (3.0) |
| Warden | `#3a2e30` | `#1f1c1e` | `#ff3b30` (3.4) |
| Stalker | `#2a2436` | `#141218` | `#b48cff` (3.2) |
| Aether Guardian | `#3a3f48` | `#1c1f24` | `#5fd8ff` (3.6); red `#ff5a3a` for the vault encounter |
| BOLT | `#9a7a2a` | `#2a2a2e` | `#ffc24a` (2.2) |

## 3. Zones: mood, fog and grade

These are the prototype values from the `src/world/zones/*.ts` constructors. The Unity zone ports pass them to
`AtmosphereSettings`, and `PostFx.ApplyGrade` converts them to URP.

| Zone | Mood | Fog colour / density (exp²) | Exposure / contrast / saturation | Bloom threshold | Weather |
|---|---|---|---|---|---|
| Central Plaza | Night storm, rain-soaked civic square, warm camp fire against cold blue | `#1d2836` / 0.0125 | 1.30 / 1.08 / 0.92 | 0.90 | Rain 1.0, wind (2.5, 1), lightning every 14–32 s |
| Plaza after the ending | Dawn, no rain, warm low sun | `#8a8a90` / 0.008 | 1.15 / 1.05 / 1.05 | 0.92 | none |
| Abandoned Metro | Dark, wet, red emergency light until powered, then white tubes | `#0a0c0e` / 0.03 | 1.35 / 1.10 / 0.90 (warm lift) | 0.85 | Indoor; sparks, steam, drips |
| Research Facility | Clean lab surfaces gone cold, holo pedestals, alarm lights | `#0a0f14` / 0.009 | 1.08 / 1.06 / 0.88 | 0.88 | Indoor |
| Underground Vault | Monumental containment, violet vents, cyan crystals | `#070812` / 0.02 | 1.20 / 1.10 / 1.00 | 0.82 | Indoor |
| Rooftop Sector | Wind, lighter rain, city skyline with the Core glow on the horizon | `#1e2a3a` / 0.0085 | 1.30 / 1.08 / 0.95 | 0.88 | Rain 0.55, wind (6, 2), lightning every 8–18 s |
| Aether Core | Deep blue void, suspended Core, floating debris | `#060a16` / 0.008 | 0.95 / 1.10 / 1.05 | 0.95 | Indoor |

## 4. Lighting and post-processing (Unity, URP)

### Pipeline asset

`Assets/Editor/Setup/ProjectSetup.cs` creates `Assets/Settings/EOA_URP.asset`:

| Setting | Value |
|---|---|
| Rendering path | Forward+, HDR |
| Main light shadows | 2048 shadow map, 2 cascades (split 0.22), 70 m distance, soft shadows |
| Additional lights | Per pixel, up to 8 per object, no shadows |
| Batching and grading | SRP Batcher on; HDR grading with a 32³ LUT; LOD cross-fade |
| Lighting | Fully realtime: baked and realtime GI are off in the Boot scene lighting settings |

### Zone atmosphere

`Assets/Scripts/World/Kit/Atmosphere.cs` sets up each zone at load:

* **Sky.** `EOA/Sky` skybox (`Assets/Shaders/EOA_Sky.shader`): a night gradient with horizon glow, drifting
  clouds, storm pockets, optional stars and a lightning flash input. Indoor zones can set
  `AtmosphereSettings.SolidBackground` to clear to the fog colour instead of drawing the sky.
* **Fog.** Exponential-squared.
* **Ambient.** Trilight ambient built from the prototype's hemisphere light plus the diffuse part of its baked
  environment map.
* **Sun.** One shadow-casting directional "sun" or moon light.
* **Reflections.** A realtime reflection probe rendered once over the zone bounds (128 px, HDR).
* **Colour grade.** Applied through `PostFx.ApplyGrade`.
* **Light conversion.** Prototype light intensities are converted with `ProtoSpace.LightToUnity = 1/π`.
  `LevelKit` caps realtime lights at 24 per zone (`LightBudget`) for WebGL.

### Weather

`Assets/Scripts/World/Kit/Weather.cs`:

* **Rain.** Rain streaks and splash rings are two particle systems that follow the camera. The streak count is
  9000 / 5500 / 2800 (Effects high / medium / low) multiplied by the zone's rain density.
* **Lightning.** Multi-strike flickers drive the sky flash, ambient boost and registered flash lights, and emit a
  `Lightning` event. That event plays a thunder clip after a distance delay.
* **Accessibility.** The Flash intensity setting scales all of it.

### Post-processing

`Assets/Scripts/Game/Rendering.cs` (`PostFx`) builds one global volume:

| Effect | Settings |
|---|---|
| Tonemapping | ACES |
| Bloom | threshold 1.05 (per-zone override), intensity 0.9, scatter 0.68 |
| Colour adjustments | post exposure +0.15, contrast +12, saturation -6 |
| Lift / gamma / gain | cool lift, warm gain |
| Vignette | 0.28 |
| Film grain | Thin1, 0.12 |
| Chromatic aberration | 0.04 |

Effects quality levels:

| Level | Bloom | Grain and chromatic aberration |
|---|---|---|
| Low | off | off |
| Medium | on | off |
| High | on | on |

Gameplay feedback through the volume:

* The vignette reddens with damage and below 30% health.
* Echo Sight lerps saturation toward -45 and tints violet (`#d1c7ff` colour filter).

### Aether material

`Assets/Shaders/EOA_Aether.shader` (`EOA/Aether`) draws additive Aether energy: a fresnel rim plus two scrolling noise
layers blending cyan and violet. It is used for the Core, tethers, crystals and resonance effects through
`EnvMaterials.Aether(...)`.

### VFX

`Assets/Scripts/VFX/VfxManager.cs` uses the built-in Particle System only (no VFX Graph, for WebGL):

* four pooled world-space particle systems: sparks, glow motes, smoke and flash sprites
* pools of shockwave rings, slash arcs, point lights and one echo wave

Particle counts scale 0.4 / 0.7 / 1.0 with Effects quality. Materials are URP Particles/Unlit, cloned from template
materials in `Resources/VFX` so that shader variants survive build stripping.

## 5. Environment kit (`blender/env` → `Assets/Art/Environment`)

Generated headlessly by `blender/env/*.py`. The data source of truth is `Assets/Art/Environment/manifest.json`, and
the human-readable catalogue is `Assets/Art/Environment/ENV_ASSETS.md`.

| Fact | Value |
|---|---|
| Assets | 332 FBX (manifest count): structure 67, facade 56, dressing 37, neon 33, facility 18, rooftop 16, metro 14, core 12, vault 12, street 11, debris 10, props 10, building 7, monument 7, vehicles 7, camp 6, signage 5, skyline 4 |
| Materials | 94 in the manifest (baked tileable PBR, tint variants and parameter-only materials), plus 36 decal sets in `Environment/Decals` |
| Size | Not re-measured since the 185-asset kit (that kit was 63 MB textures, 8.9 MB FBX) |
| Units and axes | Metres; Unity Y up; asset front faces +Z; pivot at base centre unless the manifest says otherwise |
| LODs | Each FBX has `<Name>_LOD0` and `<Name>_LOD1`; LOD1 is about 25–45% of LOD0 triangles; the manifest gives suggested LOD transition heights |
| UV0 | World-scale metres for tiling materials (1 UV = 1 m); `fit` materials (panels, screens, windows) use 0..1 per face; `strip` materials use U = metres along the strip |
| UV1 | Not authored (realtime lighting only) |
| Normals | Custom split normals (weighted, sharp above 50°) |
| Colliders | Suggested primitive colliders per asset in the manifest (box, capsule or cylinder, or `mesh` / `none`) |
| Extra metadata | Screen rectangles for signs and terminals, light anchors, monument part placements, blast-door light sockets |

### PBR texture conventions

Every texture is 1024² and tiles seamlessly (procedural noise is evaluated on a 4D torus). Materials are authored as
shader-node graphs (`nodekit.py`, `matdefs.py`) and baked with Cycles (`bakekit.py`). Normal maps are derived from
the baked height in metres, so bump strength matches the tile size.

| Map | Colour space | Content | URP Lit slot |
|---|---|---|---|
| `<name>_BaseColor.png` | sRGB | Albedo (RGBA for `grating`: A = cutout) | `_BaseMap` |
| `<name>_Normal.png` | linear | Tangent space, OpenGL (+Y up) | `_BumpMap` |
| `<name>_MaskMap.png` | linear | R metallic, G AO, B height, A smoothness | `_MetallicGlossMap` (smoothness from metallic alpha) |
| `<name>_Occlusion.png` | linear | AO (same as MaskMap G) | `_OcclusionMap` |
| `<name>_Emission.png` | sRGB | Emission colour (emissive materials only) | `_EmissionMap`, HDR `_EmissionColor` |

Tint variants reuse the parent's Normal, MaskMap and Occlusion maps:

* `concrete_dark`
* `metal_painted_red`, `_yellow`, `_white`, `_green`
* `metal_dark`
* `tarp_blue`
* `car_paint_dark`, `_red`, `_white`

### Tile sizes

Material tiling = 1 / tile size.

| Tile (m) | Materials |
|---|---|
| 4.0 | asphalt |
| 3.0 | paving |
| 2.4 | lab_panel |
| 2.0 | concrete, concrete_dark, concrete_wet, plaster, gravel, metal_painted (+ tints), metal_dark, metal_rusted, metal_plate, lab_floor, car_paint_grey (+ tints) |
| 1.8 | brick |
| 1.2 | metro_tile |
| 1.0 | metal_bare, corrugated, grating, rubber, tarp, tarp_blue, wood |
| 0.5 (strip) | emit_strip_cyan, emit_strip_violet, emit_strip_warm |
| fit (0..1) | emit_panel_cyan / violet / white / warm, screen, window_lit_warm / cool |

### Emission intensities

| Material | Intensity |
|---|---|
| emit_strip_cyan / violet | 4.0 |
| emit_cyan | 3.2 |
| emit_panel_cyan / violet, emit_violet, emit_red | 3.0 |
| emit_amber | 2.8 |
| emit_panel_white, emit_white, emit_green | 2.6 |
| emit_panel_warm | 2.5 |
| window_lit_warm | 1.2 |
| window_lit_cool, screen | 1.0 |

`aether_energy` and `water` are placeholders in the kit; the game uses the `EOA/Aether` shader for Aether energy.

### Into Unity

`Assets/Editor/Environment/EnvLibraryBuilder.cs`, run by EOA → Setup Project (All) or EOA → Build Environment
Library:

1. Sets the texture import settings.
2. Writes one URP Lit material per manifest material to `Assets/Resources/Env/Materials/<name>.mat` with world-scale
   tiling.
3. Remaps the FBX materials by slot name.
4. Writes a prefab per asset with a LODGroup, the suggested colliders and the World layer to
   `Assets/Resources/Env/Props/<Name>.prefab`.
5. Copies the manifest to `Assets/Resources/Env/env_manifest.json`.

A batch run of the setup on 2026-10-03 reported "55 materials, 185 prefabs (0 failed)".

At runtime:

* `LevelKit.Prop(name, x, y, z, yaw, ...)` instantiates a prefab. If a prefab is missing, it places a grey box of
  the manifest size so the layout stays playable.
* `EnvMaterials.Get(name)` accepts kit names and the prototype's material names (for example `rust` →
  `metal_rusted`, `tile_lab` → `metro_tile`). It falls back to a flat-colour URP material when the library has not
  been built.

### Rebuild

From `ENV_ASSETS.md`:

```
cd blender/env
B=/Applications/Blender.app/Contents/MacOS/Blender
$B -b --factory-startup --python build_materials.py -- --res 1024 --samples 8
$B -b --factory-startup --python build_assets.py --
$B -b --factory-startup --python render_assets.py -- --sheet street 'Barrier*'
$B -b --factory-startup --python render_materials.py --
python3 write_manifest.py
```

Preview contact sheets are in `blender/env/previews/`. The kit now includes complete buildings (`Building_MidRise_A/B/C`, `Building_HighRise_D`), facade modules, a neon and signage set, skyline megatowers and cyber traffic lights.

## 6. Robots (`blender/robots` → `Assets/Resources/Models/Robots`)

Rigid-part robot FBX files, built by `blender/robots/build_robots.py` with per-type scripts (`bot_drone.py`,
`bot_sentinel.py`, `bot_guardian.py`, `bot_stalker.py`, `bot_bolt.py`). The build is checked against the bone and
part contract in `Assets/Scripts/Enemies/ROBOT_PARTS.md` by `check_robots.py`. Details are in
`Assets/Resources/Models/Robots/ROBOT_MODELS.md`.

| File | Height | Triangles | Notes |
|---|---|---:|---|
| `drone.fbx` | 0.52 m pod, 1.7 m wide | 4,408 | `body` with `rotor_0..3` |
| `sentinel.fbx` | 2.15 m | 5,858 | Blade on the right forearm |
| `warden.fbx` | 2.6 m | 6,402 | Crest, mantle, shield emitter on the left forearm |
| `stalker.fbx` | 2.0 m | 3,900 | Glowing blades on both hands |
| `guardian.fbx` | 5.2 m (stacks reach 5.55 m) | 8,978 | `core`, `plate_L`, `plate_R` (the opening chest plates) |
| `bolt.fbx` | 1.55 m | 5,798 | NPC robot on the same 20-bone skeleton |

* **Skeleton.** Bipeds share a 20-transform skeleton (`root … foot_R`) with identity rest rotations, so the C#
  procedural animator can drive them (see `ANIMATION_BIBLE.md`).
* **Materials.** Every part uses one of five materials: `robot_shell`, `robot_frame`, `robot_joint`, `robot_glow`
  and `robot_rotor`. All emissive parts share `robot_glow`, so telegraphs brighten them together.
* **Textures.** `make_textures.py` produces a 1024², greyscale, worn-paint set:
  `Textures/robot_worn_metal_{BaseColor,Normal,MetallicSmoothness}.png`.
  * `ProjectSetup` builds `Resources/Models/Robots/robot_metal.mat` from it (URP Lit, tiling 2.5).
  * `RobotRig` loads that material and tints it per palette.
  * `ROBOT_MODELS.md` still says the textures are "not used by the current C#" and requests a `RobotKind.Bolt`.
    Both have since been implemented (`RobotRig.cs`), so those two notes are out of date.
* **Fallback.** Without the FBX, `RobotRig` builds the same robots from procedural meshes (`RobotBodies.cs`,
  `FxMesh.cs`).

## 7. Characters

Human characters are MakeHuman/MPFB bodies assembled and outfitted by the HD scripts in `blender/scripts/`
(`hero_hd.py`, `npc_hd.py`). See `CHARACTER_BIBLE.md` for design and the full pipeline, and `ANIMATION_BIBLE.md` for
rigs and clips. Previews: `blender/out/previews_hd/` (studio and night renders per character).

* **Exports.** `Assets/Art/Characters/<Name>/<Name>.fbx` with a `.manifest.json` and `Textures/`. Seven characters:
  Kael, Giva, Oren, Mira, Tomas, Maren and Nia (Giva's folder and FBX are internally named `Lyra`).
* **Kael.** Curly medium-length hair (procedural hair cards). Ultra-high-tech armour: pauldrons with lames, chest
  plate and plate-carrier chest rig, right forearm guard with the Aether interface, knee pads, collar, belt modules,
  knuckle-plate gloves, subtle facial cyberware. Glowing cyan and magenta circuit tattoos.
* **Giva.** Long wavy hair. Bodysuit with glowing circuit traces, cropped bomber jacket, harness with chest unit and
  glowing core, left hip module, right thigh rig, holo bracer, optional HUD visor, cyberware. Glowing magenta and
  violet tattoos.
* **NPCs.** Oren (patched parka, scarf, cyber forearm brace), Mira (LED hoodie, headset, satchel, tattoos), Tomas
  (long coat, goggles, scarf, tattoos), Maren (illuminated lab coat; echo), Nia (LED hoodie; echo). Three CC0 base
  garments were removed (Mira's sweater, Tomas's robe, Nia's t-shirt).
* **Materials.** Hero garment colours are composited at runtime from painted masks (R secondary, G trim, B glow,
  A seam). Skin has normal, mask and tattoo-emission maps; hair uses alpha-tested cards tinted from a neutral texture.
  Glow materials (`Glow`, `Glow2`, `Screen`) take the character's neon colours as HDR emission.
* **Detail.** Roughly 34,000-68,000 visible triangles per character (heroes about 67,500).
* **Customisation.** Hair, glasses, armour sets and tattoo designs are catalog attachments; the catalog and most of
  its content are not in the repository yet (`CHARACTER_BIBLE.md` §5).
* **Echoes.** Maren and Nia are rendered as translucent additive echoes (`CharacterModel.SetEcho`). The tint
  is `#9ebfff` for Maren and `#80b8ff` for Nia.

## 8. Vehicles (`blender/vehicles` -> `Assets/Art/Vehicles`)

Ten cyberpunk vehicles, fully procedural (lofted subdivision shells, bmesh, booleans; textures generated by script).
Data source of truth: `Assets/Art/Vehicles/manifest.json`; human-readable: `Assets/Art/Vehicles/VEHICLES.md`. 26
materials (all prefixed `veh_`), textures 79.4 MB, FBX 11.7 MB. No real brands, logos or text: every badge, plate and
sign uses an invented glyph script.

| Vehicle | Type | LOD0 tris | Animated parts |
|---|---|---:|---|
| `CyberCar_Coupe` | Cab-forward wedge supercar | 30,838 | 4 wheels |
| `CyberCar_Sedan` | Armoured executive sedan | 27,654 | 4 wheels |
| `CyberCar_Taxi` | Compact cab with roof holo-sign | 29,196 | 4 wheels |
| `CyberVan` | Forward-control utility van | 26,812 | 4 wheels |
| `CyberBike` | Hubless-wheel motorcycle | 16,042 | 2 wheels |
| `HoverCar_A` | Spinner-style flyer | 21,370 | 4 thrusters |
| `HoverCar_B` | Two-seat bubble-canopy flyer | 17,522 | 4 thrusters (2 ducted fans) |
| `HoverTruck` | Heavy flying hauler, about 9.5 m | 22,324 | 6 thrusters |
| `CyberCar_Sedan_Wrecked` | Static wreck prop | 28,673 | none |
| `CyberVan_Burnt` | Static burnt-out prop | 19,253 | none |

* **LODs.** LOD1 about 40% and LOD2 about 12% of LOD0 triangles.
* **Emissive slots** are separate materials so Unity can animate them: headlight, taillight, underglow, neon, hazard,
  thruster, navlight and holo sign.
* **Paint.** Six paints (midnight, gunmetal, pearl, magenta, cyan, taxi yellow), plus wrecked and burnt finishes.
* **In the game today.** All ten have prefabs in `Resources/Env/Props`. `Traffic.cs` drives sedan, taxi, coupe, van
  and bike on the city streets; the wreck and burnt van are used as street dressing. **No code references the hover
  vehicles** (`HoverCar_A`, `HoverCar_B`, `HoverTruck`) yet, so they are built but not placed (the plaza's sky traffic
  is a separate system). Wheel rotation and thruster pulsing are described in `VEHICLES.md` as integrator work; this
  has not been verified in game.
* **Previews:** `blender/vehicles/previews/` (street and studio, 3/4 front and rear).

## 9. Open-world city (`Assets/Scripts/World/City`, `Zones/Plaza/OpenCity.cs`)

The open district around the Central Plaza is built at load by code (`OpenCity`, seed 7741) from the kit above, with
procedural stand-ins where a kit prefab is missing. It is a **721 x 625 m** street grid (x -360..360, z -292..332),
66 blocks, with the plaza as the cordoned central square. Districts (`CityDistrict`), from `CityLayout`:

| District | Where | Character (from the code's lot rules) |
|---|---|---|
| Neon Market | West | Dense low/mid-rise, many small shops, the strongest neon |
| Arcology Gate | East | Corporate podium megatowers; the east avenue ends at the megawall gate |
| Kowloon Stacks | North | Narrow, tall, stacked tenements |
| Foundry Row | North-east | Industrial sheds and works; the most wrecks |
| Canal Ward | South | Mid-rise brick and plaster, a canal and bridges |

Also in code: avenues and alleys leaving the plaza, quarantine checkpoints, skybridges (Market and Canal), a megawall
with sealed tunnels, a skyline ring, traffic lights, a pedestrian crowd (`Crowd.cs`, drawn from the NPC models, with
a budget that shrinks on lower effects settings) and street traffic (`Traffic.cs`), all culled by distance
(`CityCuller`). The district is excluded from the plaza NavMesh bake.

> **TODO(lead): update after city art pass.** Other agents are adding Blender landmark buildings, street-level props
> and lighting. This section describes only what exists in code at 2026-10-04. Replace this note with the final
> landmark list, prop sets and lighting description, and add screenshots.

Whether the district runs at target frame rates in the WebGL build is not measured.

## 10. Rendered 2D art

All 2D art is produced as Blender Cycles renders of scenes assembled from the game's own assets. Provenance and
render settings: `marketing/ART_CREDITS.md`. The shared library `blender/art/scripts/artkit.py` handles render setup
(AgX view, compositor bloom and vignette), camera and lighting helpers, volumetric fog, wet-surface shading, loading
environment-kit assets, posing characters with the retargeted clips, and rain. Per-image scene scripts
(`scene_plaza.py`, `scene_metro.py`, `scene_facility.py`, `scene_rooftops.py`, ...) live in `blender/art/scripts/`;
scene copies go to `blender/art/scenes`, previews to `blender/art/previews`.

| Output | Path the game reads | Used by | Present (2026-10-04) |
|---|---|---|---|
| Title logotype | `Assets/Resources/Art/Title/logo` | Main menu | `logo.png` |
| Loading art per zone | `Assets/Resources/Art/Loading/<zoneId>` | `LoadingScreen` (slow pan) | plaza, metro, facility, vault, rooftops, core (6 JPG) |
| Portraits | `Assets/Resources/Art/Portraits/<id>` | HUD, dialogue panel | 9 PNG (bolt, guardian, kael, lyra, maren, mira, nia, oren, tomas; `lyra` is Giva's id) |
| Item art | `Assets/Resources/Art/Items/<icon>` | Inventory | 18 PNG |
| Marketing images | `marketing/` | itch.io page | **None in the repository**: `marketing/` holds only `ART_CREDITS.md` and `ITCH_PAGE.md` |

The portraits and loading art may predate the latest character and city art; whether they have been re-rendered is
not verified. `marketing/ART_CREDITS.md` lists `key_art_1920x1080.png`, `itch_cover_630x500.png`,
`banner_1920x480.png` and `social_1200x630.png` as outputs of `marketing.py`; they do not exist in `marketing/` yet.

## 11. Asset provenance summary

| Asset class | Made by | Licence |
|---|---|---|
| Environment kit (332 FBX, 94 materials, decals) | `blender/env` scripts | Project's own work |
| Vehicles (10 FBX, 26 materials) | `blender/vehicles` scripts | Project's own work |
| Robots (6 FBX + worn-metal textures) | `blender/robots` scripts | Project's own work |
| Human base meshes, skins, eyebrows, eyelashes, remaining NPC base clothing, shoes, legacy hair options | MakeHuman community assets via MPFB | CC0 per the pack indexes (the three AGPL3-headed assets were removed; beards, bun and French braid are procedural, see `THIRD_PARTY_LICENSES.md` §5) |
| HD outfits, armour, cyberware, procedural hair, skin detail, tattoo maps, garment textures, morph and expression shape keys | `blender/scripts`, `blender/custom` (geometry and painted masks, MakeHuman targets) | Project's own work, built on CC0 MakeHuman data |
| Zone geometry, UI gradients, VFX meshes and materials | C# at runtime (`LevelKit`, `FxMesh`, `FxMaterials`, `City*`) and baked PNGs in `Assets/UI/Textures` | Project's own work |
| Animation | CMU Graphics Lab Motion Capture Database, retargeted | Free incl. commercial use; credit required (`ANIMATION_CREDITS.md`) |
| UI glyph icons | Prototype SVG set (`src/ui/Icons.ts`), rasterised by `Assets/Editor/UI/Tools~/rasterize_icons.mjs` | Project's own work |
| Fonts | Rajdhani, Inter | SIL OFL 1.1 |
| 2D art (logo, loading, portraits, items) | Blender Cycles renders | Project's own work |
| AI-generated images | none | none |
