# Echoes of Aether: 2D art credits and provenance

Every image listed here is a **render of a 3D scene built in Blender with Python scripts**. No AI image
generation, AI upscaling, AI inpainting or AI texture synthesis was used anywhere: no diffusion models, no
text-to-image or image-to-image services, no generated stock. (The DreamLayer image service was integrated early
on but generated 0 images and used 0 credits; see `docs/DREAMLAYER_ASSET_LOG.md`.) Each scene can be rebuilt and re-rendered
headlessly from the scripts in `blender/art/scripts/` (`render_all.sh` runs every job).

## Tools and render settings

| | |
|---|---|
| Software | Blender 5.2.2 LTS (headless: `Blender -b --factory-startup --python <script>.py`) |
| Engine | Cycles path tracing on the Apple M4 GPU (Metal). Adaptive sampling (128 samples for 1080p scenes, 160 for portraits, 192 for items, 256 for the logo), light tree, OpenImageDenoise (albedo + normal passes, high quality) |
| Colour | AgX view transform, "AgX - Medium High Contrast" look, sRGB display. Palette: sodium-amber street light against teal shadows, cyan neon, magenta only as an occasional accent |
| Atmosphere | Bounded Principled Volume boxes (haze, ground mist, rain clouds) with noise-modulated density; volumetric light shafts from spot lights |
| Rain | Thousands of thin camera-facing streak quads, lit by the scene |
| Compositor | Blender compositor node group: Glare (Bloom) for neon glow, a slight lens-dispersion (chromatic) pass, a saturation lift, a soft vignette. Key and store art composite the rendered logo with Alpha Over. The logo's glow is kept in its alpha channel (luminance key) |
| Output | Loading screens: 1920 x 1080 JPEG (quality 88). Portraits: 512 x 512 PNG. Items: 256 x 256 RGBA PNG (transparent, Cycles shadow catcher for the contact shadow). Logo: 2048 x 640 RGBA PNG. Store art: PNG |

## What is in the pictures

**Environments.** The game's own art kits, imported as FBX with Cycles materials built from each kit's manifest
(BaseColor / Normal / MaskMap / Emission textures, metre-based tiling):
- environment kit `unity/EchoesOfAether/Assets/Art/Environment/` (`blender/env/`): street furniture, monument,
  metro, facility, vault and core pieces, complete buildings, skyline megatowers, neon and signage kit;
- city landmark kit `unity/EchoesOfAether/Assets/Art/CityLandmarks/` (`blender/city_landmarks/`): the bespoke
  `Plaza_Block_00..22` buildings placed at their prototype block positions, district buildings (`LB_*`) and
  landmarks (Jade Lantern Tower, Helix Arcology, Meridian Spire, The Stack, Signal Spire, Bridge Twins ...);
- city street kit `unity/EchoesOfAether/Assets/Art/CityStreet/` (`blender/city_street/`) materials;
- cyber vehicle kit `unity/EchoesOfAether/Assets/Art/Vehicles/` (`blender/vehicles/`).
The outdoor scenes use the FX team's storm-sky panorama (`blender/fx/out/sky_pano_color_final_4096.exr`, rendered by
`blender/fx/scripts/sky_pano.py`) as the world, with sodium-amber street light against teal shadows. A wetness layer
adds damp albedo, low roughness, puddles and ripples on up-facing surfaces in the rain scenes. Zone layouts follow
the prototype levels in `src/world/zones/*.ts`.

**Extra set dressing.** Modelled procedurally inside the render scenes by `blender/art/scripts/cyberkit.py`:
neon tubes (bevelled curves with an emissive shader), holographic advert planes (additive scanline shader), light
strips, catenary cables, distant air-traffic light trails, searchlight beams and holographic glyph rings. All
signage text, in the kit and in these scenes, is an **invented glyph script** (`cyberkit.glyph()` builds it
from a stroke grammar). No real-world words, brand names or logos appear in any sign.

**Characters.** Kael Voss and Giva Vale are the remade heroes (`blender/heroes_v2/kael`, `blender/heroes_v2/giva`),
loaded from their game exports (`unity/EchoesOfAether/Assets/Art/Characters/{Kael,Lyra}/*.fbx`; Giva's files keep
the id `lyra`). Their materials are rebuilt from each manifest's `materialDefs` and textures with the game's
default appearance colours (`Appearance.BaseDefault`), and the garments are composited from their masks the way
`CharacterModel` does at runtime. They wear their catalog default look
(`unity/EchoesOfAether/Assets/Resources/Characters/Custom/catalog.json`, sources in `blender/custom/`): Kael's
`side_part_volume` hair and `circuit_neck` tattoo, Giva's `long_waves` hair and `circuit_sleeve` tattoo. In the key
and store art Kael also wears the catalog `aviator` glasses and Giva the `cyber_visor`. The NPCs (Oren, Mira, Tomas,
Nia, Dr. Ilse Maren) come from `blender/out/<id>_export.blend` (MPFB 2.0.17 and the project's HD character scripts).
All hair is procedural hair cards with strand textures drawn by script. Characters are posed with frames of the
game's animation clips (`blender/anim/clips.json`, retargeted with `blender/scripts/retarget.py`). Maren and Nia are
rendered as Aether "echoes" with a translucent fresnel-and-scanline hologram shader. The giant holographic advert
figure is the same character mesh shaded as a hologram.

MakeHuman / MPFB assets used, and their licences:

- CC0 (MakeHuman system assets, released CC0 in September 2020): base mesh, skins (young/middle-aged
  caucasian, asian and african), eyes, eyebrows (eyebrow001/002/004/009/010), eyelashes (01, 02), teeth,
  tongue, hair short01/short02/short04/ponytail01/bob01/bob02, shoes03, female_elegantsuit01, male_casualsuit05.
- CC0 (MakeHuman community assets): cortu_cargo_pants (Cortu), toigo_harem_pants, toigo_mj_cloth_shoes,
  toigo_flats, toigo_ankle_boots (MRT), elvs_crude_t-shirt_male (Elvaerwyn), culturalibre_male_boots
  (culturalibre), rehmanpolanski_moustache_viking, skin tones toigo_light_skin_* (MargaretToigo).
- Removed from the characters in the HD rebuild and not in current renders: toigo_fisherman_sweater (Mira),
  donitz_monk_robe_hood_down (Tomas), joepal_crude_t-shirt_female (Nia).
- Removed and replaced procedurally (2026-10-04): the hero hair options "bun" and "frenchbraid", Maren's hair
  and the beards (Kael's beard option, Oren's beard) are now made by the project's own scripts; the former
  MakeHuman community assets for them are no longer used.
- Hero skins are resampled from the CC0 MakeHuman skins; the hero hair (curly, wavy, bun, frenchbraid), Maren's hair,
  the beards, outfits, armour, tattoos and textures are made by the project's scripts.

**Robots.** The game's rigid-part robot models (drone, sentinel, warden, stalker, guardian, BOLT) from
`blender/robots/out/*.blend`, built by the project's scripts in `blender/robots/`, with their palette x
worn-metal materials. Posed by rotating their named joint transforms.

**Items.** Each inventory item (all 18 `icon` ids in `src/data/items.json`) is modelled from primitives,
bmesh and bevels in `blender/art/scripts/items.py`. Accent colours follow the game UI palette, remapped onto
the cyberpunk neon palette.

**Logo.** "ECHOES OF AETHER": extruded and bevelled 3D text in Rajdhani Bold / SemiBold with a stylised chrome
shader, a dark keyline, magenta / cyan neon tubes traced from the letter outlines, and a cyan Aether seam.

## Fonts

- Rajdhani (Bold, SemiBold), Copyright (c) 2014 Indian Type Foundry, SIL Open Font License 1.1. Files and
  licence: `unity/EchoesOfAether/Assets/UI/Fonts/Rajdhani/` (`OFL.txt`). Used for the logo.
- No other fonts are rendered. Signage uses the procedural invented glyph script, not a font.

## Files

| File | Scene script |
|---|---|
| `unity/EchoesOfAether/Assets/Resources/Art/Loading/{plaza,metro,facility,vault,rooftops,core}.jpg` | `scene_<zone>.py` |
| `unity/EchoesOfAether/Assets/Resources/Art/Portraits/*.png` (9) | `portraits.py` |
| `unity/EchoesOfAether/Assets/Resources/Art/Items/*.png` (18) | `items.py` |
| `unity/EchoesOfAether/Assets/Resources/Art/Title/logo.png` | `logo.py` |
| `marketing/key_art_1920x1080.png`, `itch_cover_630x500.png`, `banner_1920x480.png`, `social_1200x630.png`, `title_background_1920x1080.png` (title-screen plate, no logo) | `marketing.py` (plaza scene; logo composited in Blender's compositor) |

Scene copies (`.blend`, compressed, textures referenced from the project) are saved in `blender/art/scenes/`;
preview sheets are in `blender/art/previews/`.

## Gameplay screenshots

`Captures/smoke/s01..s14_*.png` are in-engine captures from the automated story smoke run (Unity player renders of
the game itself, not Blender renders and not AI images). They are not part of the Blender render pipeline above.
