# Visual Audit

Status date: 2026-10-07 (concept-match pass). Internal production classification only — **PASS**, **NEEDS_REFINEMENT** or
**MISSING** — based on in-engine Unity captures reviewed by the lead (paths given), not on Blender renders.

## Characters

| Asset | Status | Evidence | Notes |
|---|---|---|---|
| Giva Vale — body, suit, harness | PASS | `blender/heroes_v2/giva/out/report/concept_vs_unity.png` | Rebuilt to the DreamLayer concept (~105k tris): violet panels and diagonal band, magenta core harness with cable bundle, segmented left pauldron, violet forearm screen, thigh holster, knee boots with magenta strips; bare hands |
| Giva — face | NEEDS_REFINEMENT | `blender/heroes_v2/giva/out/report/designer_face.png` | Softer, younger oval with amber eyes and freckles; smooth since the SSAO change; still less detailed than the concept painting |
| Kael Voss — body, outfit, armour | PASS | `blender/heroes_v2/kael/previews/concept/final_concept_blender_unity.png` | Rebuilt to the DreamLayer concept (~115k tris): quilted black bomber, black chest plate with pouches, compact steel pauldrons, olive cargo trousers tucked into light-strip boots, brass-knuckle gloves, translucent cyan holo sleeve; still leaner than the painting |
| Kael — face | NEEDS_REFINEMENT | `Captures/kael_v2/final2/concept/kael_front.png` | Stronger brow, cheekbones, jaw, stubble and scar; neutral tan skin; still softer than the concept painting |
| Standing pose (menu, designer, idle) | PASS | `Captures/anim/arm_fix/heroes/h00_character_select.png` | Trunk square to the hips (a 23° avatar twist removed at the source), arms at the sides, level head |
| Hands, wrists, feet in motion | PASS | `Captures/avatar_diag.txt` | Wrist bend 0–4° (was 30–55°), relaxed finger curl, planted feet |
| Default hair — Kael `swept_fade` | PASS (game distance) / NEEDS_REFINEMENT (close-up) | `Captures/kael_v2/final2/concept/` | Concept swept brown with silver shaved side; strand banding visible up close |
| Default hair — Giva `waves` | PASS (game distance) / NEEDS_REFINEMENT (close-up) | `blender/heroes_v2/giva/out/report/concept_vs_unity.png` | Concept dark-brown waves with centre parting and real S-curves; less lush than the painting |
| Eyewear (15 items) | PASS | `Captures/lead_eyewear4/` | Fitted to each face at runtime from the eye bones; frame styling is functional rather than premium |
| Armour sets (8) | PASS | `blender/custom/previews/final/unity_v3_all.png` | High-poly bakes and real materials; not yet refitted to the remade bodies (minor poke-through possible) |
| Tattoos (16) | PASS | catalog thumbnails | Remapped to the remade bodies; defaults visible with the outfits |
| NPCs (Oren, Mira, Tomas, Maren, Nia) | PASS | `Captures/lead_story_final/s03_m1_meeting.png` | Procedural beards and hair (no AGPL assets) |
| Enemies (drones, sentinels, stalkers, guardian) | PASS | `Captures/gfx_after/compare/combat_*.png` | Telegraph glints, debris deaths, subtle hit flash |

## World

| Asset | Status | Evidence | Notes |
|---|---|---|---|
| City palette (5 districts) | PASS | `Captures/gfx_after/compare/city_09_aerial_north.png` | Amber/sodium vs teal; magenta reduced to ~6% |
| Landmarks (15) and district buildings | PASS | `blender/city_landmarks/previews/lm_sheet_a.png`, `Captures/emission_fix/` | Kit emissives fixed (they imported dark) |
| Glowing "slab" facades | PASS (fixed) | `Captures/gfx_after/fixes/slab_fix_foundry_canal.png` | Neon band bug in `EOA_CityLights` |
| Street level (storefronts, props, decals) | PASS | `blender/city_street/captures/after/` | Interiors visible through shop windows |
| Wet streets and reflections | PASS | `Captures/gfx_after/compare/city_03_kowloon_street.png` | SSR streaks + shader fallback |
| Rain, splashes, lightning | REMOVED | — | Turned off at the owner's request (2026-10-07); wet streets and puddles kept |
| Sky | PASS | `blender/fx/previews/unity_final/` | Blender storm panorama, far city band |
| Interiors (metro, facility, vault, core) | PASS | `Captures/gfx_after/compare/zone_10_*` | Per-zone grades; hero readable |
| Vehicles (10) | PASS | `Captures/vehicles_run5/` | Wheels, lights, LODs |

## Presentation

| Asset | Status | Evidence | Notes |
|---|---|---|---|
| Main menu / character select | PASS | `Captures/lead_stance2/h00_character_select.png` | Studio lighting, upright heroes |
| HUD, dialogue, subtitles | PASS | `Captures/lead_story_final/` | Subtitles above letterbox |
| Combat VFX (trails, impacts, perfect dodge) | PASS | `Captures/gfx_after/compare/combat_kael_combo_side.png` | Compact coloured impacts |
| Loading screens (6) | PASS | `unity/EchoesOfAether/Assets/Resources/Art/Loading/` | Plaza/rooftops renders predate the new city art and hero remakes |
| Portraits (9), key art, itch cover, banner, social card | PASS | `blender/art/previews/contact_sheet.png` | Rendered with the previous hero models; re-render pending |
| Item icons (18), logo | PASS | `blender/art/previews/contact_sheet.png` | |

## Weapons and glow

| Asset | Status | Evidence | Notes |
|---|---|---|---|
| Hero weapons (blade, pistol, holster, gauntlets) | PASS | `Captures/weapons/` | Blade along the forearm on the striking arm, only during attacks; pistol held level; slim thigh holster |
| Enemy weapons | PASS | `Captures/weapons/w_enemy_*` | Drone blasters, sentinel blades, Guardian arm cannon and folding blade (thin when seen edge-on) |
| Character glows | PASS | `blender/heroes_v2/giva/out/report/glow_closeups.png` | Hue kept through ACES: magenta and cyan read saturated with bloom |

## DreamLayer

DreamLayer generated 2 images (2 promotional credits): the master concept references for Kael and Giva. The 3D models
were built in Blender to match them; no DreamLayer image ships in the game. See `DREAMLAYER_ASSET_LOG.md`.
