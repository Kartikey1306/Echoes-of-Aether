# Echoes of Aether — Character Bible

Status date: 2026-10-04. Characters are the HD rebuild (pipeline tag `hd-2026-10` in every manifest).

Sources:

| Topic | Source |
|---|---|
| Story, voice and personality | `src/data/speakers.json`, `dialogue.json`, `quests.json`, `locale/en.json` (identical copies in `unity/EchoesOfAether/Assets/Resources/Data/`) |
| Physical builds | `blender/scripts/characters.py` (phenotypes), `hero_hd.py` and `npc_hd.py` (HD build and export), `outfit_kael.py`, `outfit_lyra.py`, `outfit_npc.py`, `hair_hd.py`, `skin_hd.py`, `gear.py`, `texbake.py`, and the exported `Assets/Art/Characters/<Name>/<Name>.manifest.json` |
| In-game customisation | `Assets/Scripts/Game/Appearance.cs`, `Assets/Scripts/Actors/CharacterModel.cs`, `Assets/Scripts/Actors/Customization.cs`, `Assets/Scripts/UI/Screens/DesignerScreen.cs` |
| Previews | `blender/out/previews_hd/` (studio and night renders per character) |

**Naming.** The female lead is **Giva Vale** everywhere the player sees (`Characters.DisplayName`, `speakers.json`,
dialogue, credits). Her internal ids were not renamed: speaker id and character id `lyra`, and the asset folder,
FBX, manifest and prefab are still `Lyra` (`Assets/Art/Characters/Lyra`, `Resources/Characters/Lyra.prefab`).
`Characters.AssetName` maps one to the other. This note is the only place in the player-facing docs that uses the
internal name.

Dialogue is subtitled. Voice-over is **off by default** and plays human recordings only; none are recorded yet
(0 of 161 lines). See `AUDIO_BIBLE.md` §6 and `VO_SCRIPT.md`.

## 1. Cast overview

| Character | Speaker id | Role | Subtitle colour | 3D model |
|---|---|---|---|---|
| Kael Voss | `kael` | Protagonist; survey lead | `#6ec3ff` | `Kael.fbx`, 1.85 m, full customisation |
| Giva Vale | `lyra` | Protagonist; systems engineer | `#b79bff` | `Lyra.fbx` (internal asset name), 1.73 m, full customisation |
| Dr. Ilse Maren | `maren` | Head of Project Echo; appears as message, logs and finally as an Aether echo | `#8ff0e0` | `Maren.fbx`, 1.58 m, translucent echo |
| Oren Hale | `oren` | Leader of the survivors' camp | `#e0b47c` | `Oren.fbx`, 1.72 m |
| Mira Sato | `mira` | Camp radio listener; Anya's sister | `#ff9a80` | `Mira.fbx`, 1.50 m |
| Tomas Reyes | `tomas` | Market trader who "trades in memories" | `#a7d68a` | `Tomas.fbx`, 1.82 m |
| Nia | `nia` | A child's echo, visible only with Echo Sight | `#a9c4ff` | `Nia.fbx`, 1.31 m, translucent echo |
| BOLT-7 | `bolt` | Camp maintenance robot | `#ffd36a` | `bolt.fbx` robot, 1.55 m |
| Aether Guardian | `guardian` | Boss machine guarding the Core | `#ff7a7a` | `guardian.fbx` robot, 5.2 m |
| Anya Sato | `anya` | Mira's sister; relay operator, heard only on a recording | `#ffc3b0` | none |
| Narrator, System, Transit PA, Unknown Parent, Stall Keeper, Vault Technician, Lab 7 Researcher | `narrator`, `system`, `pa`, `parent`, `vendor`, `tech`, `researcher` | Voices in cinematics, system messages and lore recordings | various | none |

* **Heights.** Heights are the exported model heights from the manifests. The heroes can be scaled ±6% in the
  designer.
* **Speaker data.** `speakers.json` also contains `voice` pitch, rate and preferred-voice fields. They are left over
  from the prototype's browser speech synthesis, which is disabled in the prototype and is not ported. The Unity
  game never reads them.

## 2. Protagonists

### Kael Voss

| Field | Value |
|---|---|
| Role | "Survey Lead · Vanguard" |
| Character | "Analytical, controlled, protective. Kael fights up close with a hard-light blade projected from his forearm interface, and breaks enemy lines with heavy Aether strikes." (`cs.kael.desc`) |
| Voice in dialogue | Short, dry, steady under pressure ("I stopped to argue with some drones." "I'm here." "Not a chance."). He closes the game: "Now we wake the rest of the city." |
| Story function | One of Maren's two resonance keys (`lore_log_keys`: "Survey lead Voss"). Pragmatic counterweight to Giva's curiosity. |
| Abilities | Aether Pulse, Phase Dash, Core Break (see `GDD.md` §3) |

**Build.** MakeHuman male: gender 1.0, age macro 0.56, muscle 0.74, weight 0.52, height 0.6, mixed ancestry
(asian 0.35, caucasian 0.45, african 0.20). Face targets give a strong square jaw and chin, a heavier brow, a
straight nose and pronounced cheekbones. Exported height 1.85 m.

**Default look** (`Appearance.Default("kael")`, manifest palette).

| Part | Default |
|---|---|
| Hair | Curly, medium length (`curly`, procedural hair cards from `hair_hd.py`), dark (`#1d1714`) |
| Eyes | Brown (`#5b3a22`) |
| Skin | `#b98a6e` |
| Stubble and scar | Stubble 0.6; scar flag on (the scar has no visible effect yet, see §5) |
| Tattoos | Glowing circuit tattoos in cyan (`#00e5ff`), with magenta (`#ff2bd6`) as the second glow colour |
| Glasses | None by default; optional through the customisation catalog (§5) |

**Outfit** (`outfit_kael.py`: cyberpunk vanguard / street-samurai techwear). Mesh names in the exported FBX:

* `Top`, `Pants`: armoured techwear jacket with a high collar (`Collar`) and illuminated seams; cargo techwear
  trousers. Colours are composited at runtime from painted masks (outfit `#4d5243`, accent `#1f2126`).
* Armour: `PauldronL` / `PauldronR` with lames (`PauldronLameL/R`), `ChestPlate`, plate-carrier chest rig
  (`ChestRig`), `ForearmGuardR` with the `Interface` (the Aether interface), `KneePadL` / `KneePadR`. Armour
  base colour `#a9a59a`.
* Gear: `Belt` with modules, `Boots`, `Gloves` with knuckle plates, `Conduit` glow lines.
* **Cyberware** (`Cyberware`, always on): temple implant lines and a neck port in metal and glow.
* Glow colours drive the `Glow`, `Glow2` and `Screen` materials: cyan `#00e5ff` and magenta `#ff2bd6`.

### Giva Vale

| Field | Value |
|---|---|
| Role | "Systems Engineer · Phase" |
| Character | "Intelligent, curious, technically fearless. Giva moves faster than anything can track, cuts with twin phase-blades and sees what the Aether hides." (`cs.lyra.desc`) |
| Voice in dialogue | Quick, warm, a little wry ("You took your time." "Did you win?"). She names the stakes: "It isn't running. It's waiting." "The Echo Collapse wasn't an accident. It was a rescue." She knew Maren personally ("Ilse?"). |
| Story function | The second resonance key ("Systems engineer Vale"). Echo Sight makes her the one who finds hidden truths, rooms and people (Nia). |
| Abilities | Echo Sight, Phase Step, Resonance Burst |

**Build.** MakeHuman female: gender 0.0, age macro 0.53, muscle 0.62, weight 0.45, height 0.48, mixed ancestry
(asian 0.40, caucasian 0.40, african 0.20). Defined cheekbones, fuller lips, slightly upturned brows, an oval head.
Exported height 1.73 m.

**Default look** (manifest palette; see the inconsistency note below for the in-game default).

| Part | Default |
|---|---|
| Hair | Long, wavy (`wavy`, procedural hair cards from `hair_hd.py`), dark brown (`#2b1b14`) |
| Eyes | Brown (`#5a3920`) |
| Skin | `#c79878` |
| Tattoos | Glowing circuit tattoos in magenta (`#ff2bd6`); second glow colour violet (`#8a5bff`) |

**Outfit** (`outfit_lyra.py`: cyberpunk netrunner / phase engineer). Mesh names in the exported FBX:

* `Top`, `Pants`: tight bodysuit with glowing circuit traces and a scoop neckline; techwear leggings
* `Jacket`: cropped bomber jacket with a stand collar, sleeves rolled above the elbow (forearms bare for the tattoos)
* `Harness` with `ChestUnit` and a glowing `ChestCore`, `HipModule` (left hip), `ThighRig` (right thigh)
* `ShoulderR` (light right shoulder plate), `ForearmGuardL` (holo bracer), `ConduitL` / `ConduitR` glow lines
* `Visor`: optional HUD monocle visor; `Cyberware`: cyber-eye ring and implant detail
* `Boots`, fingerless `Gloves`
* Glow colours: magenta `#ff2bd6` and violet `#8a5bff`. Armour base colour `#6a6474`, outfit `#8c8577`, accent `#2a2431`.

### Their relationship

They are colleagues woken from the same stasis. The banter is familiar and teasing (`cin_meeting_lines`,
`dlg_m1_comms`). Many lines are written for "the active hero" and "the partner", so the same scene works whichever
hero the player chose (`active` / `partner` speakers in `dialogue.json`; `{partner}` in objective text).

## 3. Supporting characters

### Dr. Ilse Maren

* **Story.** Head of the Aether Research Division and of Project Echo (`lore_log_echo`). Faced with a certain
  cascade, she had the Core keep four thousand minds. She is unsure whether it was "mercy or a cage" (`dlg_truth`).
  She kept Kael and Giva asleep as the only keys that can make the Core let go.
* **Appearances.**
  * Transmitter message in the metro (`dlg_maren_message`)
  * Four research logs and her final entry
  * As an Aether echo in the Core (`dlg_final_truth`: "I'm not a recording this time, Lyra. I'm one of them.")
  * Her hidden room in the vault (`cin_hidden_vault_lines`)
  * The ending
  * Her testament asks whoever releases the echoes to "ask if I chose right"
* **Guardian link.** She describes the Guardian as "the part of me that was afraid".
* **Model.** MakeHuman female, age macro 0.72; hair in a bun, a MakeHuman elegant suit and flats under a long
  lab coat with illuminated trim (`LabCoat`). Flagged `echo` in the manifest, so it is spawned as a translucent, additive hologram-like figure (`CharacterModel.SetEcho`, tint
  `#9ebfff`). It is staged by cinematics (`CineCtx.SpawnEcho`).

### Oren Hale

* **Story.** Has kept the camp alive, "kept them hidden, mostly", for seven years. He counts the years since the
  Core went quiet. Gruff and practical ("Keep your voice down. The drones hunt by sound when they can't see.").
  Tender about BOLT ("Hello, old friend.").
* **Side quest.** Gives Broken Guardian.
* **Model.** Older male (age macro 0.82), grey hair (`#8d8a86`) and a full grey procedural beard (`#7a7570`), MakeHuman casual
  suit and ankle boots under a patched parka (`Parka`) with a scarf, fingerless gloves and a cyber brace on the left
  forearm (`Gear`, `Armor` materials). Idle behaviour: `npc_crossed` (arms crossed) at the camp.

### Mira Sato

* **Story.** Listens to the radio band every night. Her sister Anya ran Relay Tower Three and never came home. Her
  arc in The Last Signal ends with Anya's last broadcast: "the Core isn't killing us. It's keeping us." That line is
  also the Rooftops loading quote.
* **Model.** Female, age macro 0.6, short bob, oversized hoodie with LED trim (`Hoodie`), cargo pants and ankle
  boots, plus an LED headset (`EarpieceL/R`), a satchel and glowing tattoos (cyan-green). The CC0 fisherman sweater
  was removed from her build. Idle behaviour: `npc_work`.

### Tomas Reyes

* **Story.** A market trader who collects the city's "little blue recording cores" so the camp remembers what the
  city sounded like. He gives Memory Fragments and plays the recordings for the camp afterwards.
* **Model.** Male, age macro 0.55, buzz cut, crude t-shirt and cargo pants under a long coat (`Coat`), with boots,
  goggles, a scarf and glowing green tattoos. The CC0 monk robe was removed from his build. Idle behaviour:
  `npc_hips`, in the Collapsed Market.

### Nia

* **Story.** A child's echo wandering the plaza ("You can see me? Everyone stopped seeing me."). Her mother "worked
  under the Vault". Maren's message "tell Nia I'm sorry I was late", and Nia's reply "She's always late", imply
  that Maren is her mother. The dialogue never states it outright.
* **Side quest.** Gives Hidden Vault.
* **Model.** Child (age macro 0.24), short bob, a small hoodie with LED trim (`Hoodie`), harem pants and cloth
  shoes. The CC0 t-shirt was removed from her build. Flagged `echo`: translucent
  (tint `#80b8ff`) and visible and talkable only while an Echo reveal is active (`ZoneNpc.EchoOnly`).
* **Movement.** She walks a 7-point loop around the monument, as in the prototype. In Unity this is done by a
  plaza-specific `PzWander` component (`PlazaZone.cs`); the generic `Npc` has no route support (see `GDD.md` §12).

### BOLT-7

* **Story.** The camp's maintenance robot, offline with a burnt-out actuator ("Maintenance unit BOLT-7. Actuator
  failure. Unit offline."). Once repaired, BOLT recalibrates the heroes' shields (Shield Matrix upgrade) and reports
  camp morale "at forty-one percent. Improving."
* **Model.** `bolt.fbx` on the shared 20-bone robot skeleton, yellow-ochre shell (`#9a7a2a`) with warm glow
  (`#ffc24a`). While offline it holds a slumped pose: the sentinel `stagger` clip, because no `sit` robot clip
  exists.

### Aether Guardian

* **Story.** Maren built it to protect the echoes; "It remembers what I built it to protect. Not why." It speaks
  in short machine statements ("Echoes detected. Containment is protection. Return to stasis.").
* **Model and fight.** See `GDD.md` §6 and `ART_BIBLE.md` §6.

## 4. Character production pipeline (Blender + MPFB, HD rebuild)

All human characters are built headlessly in Blender 5.2 with the MPFB 2.0.17 add-on and MakeHuman CC0 assets. The
HD rebuild (manifest `pipeline: hd-2026-10`) replaced the earlier outfit and hair pipeline:

1. **`hero.py` / `build_human.py`** create the MPFB human from the phenotype in `characters.py` (face targets, skin,
   eyebrows, eyelashes, MakeHuman hair and clothes) and add the `mixamo_unity` rig (`mixamorig:` bone names, Unity
   Humanoid compatible).
2. **`morphs.py`** captures blendshape deltas from MakeHuman targets: customisation morphs `m_<name>_incr` /
   `m_<name>_decr` for the heroes (25 on Kael, 27 on Giva with bust) and the eight expression shapes `x_<name>`
   (blink_L/R, mouthOpen, smile, frown, browsUp, browsDown, squint) for every character.
3. **`hero_hd.py`** (heroes) and **`npc_hd.py`** (Oren, Mira, Tomas, Maren, Nia) run the HD build: layered garments
   and gear, rebuilt eyes, decimation, atlases, FBX and manifest export, and previews
   (`--previews studio,night`, written to `blender/out/previews_hd/`).
   * **`gear.py`**: garment shells, machined armour plates, straps, buckles, pouches, cables and glow seams, built
     on the body surface. Skin weights and blendshapes transfer through a nearest-surface binding.
   * **`outfit_kael.py`, `outfit_lyra.py`, `outfit_npc.py`**: the outfits. NPC outfits are cyberpunk street-survivor
     layers over their MakeHuman base clothes.
   * **`hair_hd.py`**: procedural `curly` (Kael) and `wavy` (Giva) alpha-tested hair cards over an inner volume;
     strand textures are drawn by script.
   * **`skin_hd.py`**: new eyes with a procedural iris, UV re-layout of the visible body, skin textures (resampled
     CC0 MakeHuman skins plus pores and detail), skin normal and mask maps, and the **glowing tattoo** emission map
     (`Skin_Tattoo.png`, `Skin_TattooMask.png`).
   * **`texbake.py`, `paint_kael.py`, `paint_lyra.py`, `paint_npc.py`**: UV atlas packing, ambient-occlusion bake and
     the garment and armour BaseColor / Normal / MaskMap textures.
4. **`export_hero.py`** writes `Assets/Art/Characters/<Name>/<Name>.fbx`, `<Name>.manifest.json` and `Textures/`.

| Character | Meshes | Morph shapes | Visible triangles | Hair styles in the FBX | Facial hair in the FBX |
|---|---:|---:|---:|---|---|
| Kael | 41 | 25 | 67,487 | 15, default `curly`: afro, bob, bobshort, braid, bun, buzz, curly, frenchbraid, long, messy, ponytail, short, swept, undercut, wavy | beard, moustache |
| Giva | 37 | 27 | 67,724 | the same 15, default `wavy` | none |
| Oren | 14 | 0 | 37,239 | own hair only | procedural beard |
| Mira | 15 | 0 | 33,791 | own hair only | none |
| Tomas | 14 | 0 | 36,158 | own hair only | none |
| Maren | 11 | 0 | 40,000 | own hair only | none |
| Nia | 11 | 0 | 39,999 | own hair only | none |

All figures are from the manifests. Maren and Nia are echoes (hologram shading in game); Mira and Tomas carry glowing
tattoos; every NPC has the eight expression shapes.

**Garments removed.** Three CC0 MakeHuman base garments were taken out of the NPC builds: Mira's fisherman sweater,
Tomas's monk robe and Nia's t-shirt. Their cyberpunk hoodie, coat and hoodie replace them. See
`THIRD_PARTY_LICENSES.md` §5 for the CC0 clothing that remains.

The Unity side (`Assets/Editor/Characters/CharacterBuilder.cs`, run by EOA -> Build Characters or the project setup)
turns each export into a prefab in `Assets/Resources/Characters/<Name>.prefab` (URP materials, Humanoid avatar,
Animator controller `Humanoid_Male` or `Humanoid_Female`, `CharacterModel`). Seven prefabs are present. Whether they
were rebuilt from the HD exports in a Unity session after the rebuild is **not verified** here.

## 5. In-game character designer

Opened from Character Select ("Customize") and from the pause menu ("Appearance"). It edits Kael and Giva only. The
hero is previewed live on the menu stage: drag or right-stick to rotate, and toggle between body and face camera.
Changes are debounced by 120 ms and applied with `GameManager.SetAppearance`. They are saved to `appearance.json`
under `persistentDataPath`, so they apply to new games. During a game they are also stored in the save
(`GameStateData.Appearance`).

### Sections and controls

Six section tabs (`DesignerScreen.SectionIds`): Presets, Body, Face, Hair, Ink, Outfit.

| Section | Controls | Implementation |
|---|---|---|
| Presets | Kael: Survey Lead (Default), Night Shift, Field Veteran, Long Watch. Giva: Systems Engineer (Default), Phase Runner, Copper, Short Cut. | `AppearancePresets` |
| Body | Height (-1..1 -> uniform scale 0.94-1.06), Muscle, Weight, Shoulders, Hips, Bust (Giva only), skin tone (9 swatches) | Signed values drive the `m_*_incr` / `m_*_decr` blendshapes |
| Face | Eye colour (7 swatches), Jaw width, Chin, Cheekbones, Nose size, Nose width, Lips, Eye size, Brow height, Age; Kael only: facial hair (None / Beard / Moustache); **Glasses** grid (shown only when the catalog has eyewear) | Blendshapes; the iris is recoloured from the grey eye texture; glasses are catalog attachments bound to the head bone |
| Hair | **Style** thumbnail grid (when the catalog has hair) or text chips (fallback list `DesignerScreen.HairStyles`); hair colour (12 swatches) | Catalog hair is a skinned or rigid attachment that hides the built-in hair; otherwise one `Hair_<style>` mesh is shown |
| Ink | **Tattoo design** thumbnail grid (when the catalog has tattoos), tattoo glow colour (9 swatches), glow intensity 0-2 | Design = ink map as detail albedo plus glow map as skin emission; without a design, the model's own tattoo map is used. Glow breathes slowly. |
| Outfit | **Armour set** thumbnail grid (when the catalog has armour sets), Jacket/suit, Accent panels, Armour, Aether glow, Glow secondary colours; toggles: Shoulder armour, Gloves; Kael: Chest plate & rig, Knee pads; Giva: Utility harness | Garment textures are composited from the painted masks (R secondary, G trim, B glow, A seam); parts are toggled by name |
| Actions | View Face/Body, Randomize, Reset (with confirmation), Done | |

* **Catalog.** `CustomCatalog` reads `Assets/Resources/Characters/Custom/catalog.json` and has four categories per
  hero: hair, eyewear, armour, tattoos. Each item names an FBX or texture, a thumbnail and, for rigid items, a bone
  and local transform. `Attachments.Attach` binds items to the character skeleton at runtime.
* **Skin.** The chosen colour selects the nearest of four skin base textures by luminance, then a light tint
  fine-tunes it (`CharacterModel.ApplySkin`).

### Customisation library status (verified 2026-10-04)

The catalog-driven system is implemented in code, but its content is **incomplete in the repository**:

| Item | State |
|---|---|
| `Resources/Characters/Custom/catalog.json` | **Not present.** The merge script `blender/custom/catalog.py` writes it from per-item fragments; it has not been run into the project yet. Until it exists, `CustomCatalog.Get()` returns an empty catalog, so the Glasses, Armour set and Tattoo design grids do not appear and Hair uses the text-chip fallback. |
| Hair FBX in `Custom/Hair/` | 9: Kael 7 (burst_fade_mohawk, edgy_caesar, ivy_league, korean_perm, man_bun_fade, modern_bowl, textured_fringe), Giva 2 (long_curls, long_waves) |
| Hair thumbnails in `Custom/Thumbs/` | 15 (Kael 11, Giva 4); several have no matching FBX yet (for example Kael curly_medium, wolf_cut, mullet_fade, mohawk_fade; Giva sleek_long, high_ponytail) |
| Eyewear, armour sets, tattoo designs | No assets in the repository. `blender/custom/catalog.py` lists the intended content: 6-7 eyewear styles, 4 armour sets and 6 tattoo designs per hero, and 20 Kael / 14 Giva hair styles. These lists are a plan, not shipped content. |

So "glasses, armour sets and tattoo designs" are **designed and wired but not yet selectable** in this repository
state. The tattoos themselves are present: each hero's built-in glowing tattoo map renders and its colour and
intensity are editable in the Ink section.

### Facial animation (all characters)

* **Blinking.** Automatic every 2.2-5.5 s, 0.16 s per blink, on `x_blink_L` and `x_blink_R`.
* **Talking.** While a character is the current dialogue speaker, `x_mouthOpen` moves with an irregular flap. This
  is driven by the `DialogueLineShown` event for heroes, NPCs and cinematic echoes.
* **Other expressions.** `smile`, `frown`, `browsUp`, `browsDown` and `squint` are exported and settable through
  `CharacterModel.SetExpression`. No game code calls it yet, so they are unused.

### Designer controls and defaults to re-check

Verified by reading the code on 2026-10-04 (not by playing). Re-test in Unity before relying on any of it.

| Control | Behaviour |
|---|---|
| Facial scar (`Appearance.Scar`) | Stored; no scar mesh, decal or texture is applied. Kael's default has it on, so there is no visible scar. The designer no longer shows a scar control. |
| Stubble | Only the skin material smoothness changes (`CharacterModel.ApplySkin`); the stubble map `Skin_Stubble.png` listed in Kael's manifest is not read by that code as far as reviewed. The designer no longer shows a stubble control. |
| Giva default hair | `Appearance.Default` sets `HairStyle = "long_curls"` and hair colour `#3b2350` (violet-dark). The FBX default is `wavy` in `#2b1b14`. `long_curls` is a catalog id, so without the catalog the model's default hair is shown. Kael's default `curly_medium` is the same case (the FBX style is `curly`). |
| Hair "Shaved" | `CharacterModel` now treats `none` as no hair mesh (a fix since the 2026-10-03 check); not re-tested in Unity |
