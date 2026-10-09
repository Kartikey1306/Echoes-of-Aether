# Hero remake v2: shared style guide and technical contract

Two agents remake the protagonists in parallel: **Kael Voss** (`kael`) and **Giva Vale** (`lyra`, the asset id stays `lyra`).
Both must follow this document so the two heroes match in quality and style and plug straight into the game.

## Art direction
- AAA third-person action game protagonists (reference quality bar: modern AAA action games). Stylised-realistic,
  believable anatomy, appealing and attractive faces, strong readable silhouettes, cyberpunk tech-wear and armour.
- Rainy neon night setting: materials must read under dark, cool ambient light with cyan/magenta neon accents and
  under the game's studio menu lighting (neutral key + cyan/magenta rims). Avoid near-black-on-black: give base
  colours value range (graphite/charcoal with lighter panels, metal edges catching light, accent colour panels).
- No AI-generated images, meshes or textures. No third-party assets except the CC0 MakeHuman/MPFB system assets
  (base mesh, skins, targets) already used by the project; document anything else.

## Kael Voss — rugged, handsome vanguard
- Adult male, about 1.85 m, about 7.5 heads tall, long legs, athletic V-taper (broad natural shoulders, defined
  waist), arms hanging naturally close to the body, normal hand size, proportional neck.
- Face: strong defined jaw and chin, sculpted cheekbones, straight well-proportioned nose, intense almond eyes
  (brown), defined brow ridge, fuller natural brows, natural lips, light stubble; subtle scar on the left eyebrow.
  Nothing puffy, doughy or uncanny. Natural, clean skin (no blotches or speckle noise).
- Default hair (user decision: NO curly hair on the heroes): the catalog style `side_part_volume` (short sides, swept
  side part; Resources/Characters/Custom). The built-in fallback `defaultHair` in the manifest must not be curly either
  (use a short swept style). Keep the head size and position
  within about ±1 cm of the current head so catalog hair and eyewear still fit (report any change).
- Outfit: graphite techwear jacket with panels, seams, straps and buckles; high tactical collar; layered chest
  plate; segmented pauldrons seated on the shoulders (hinges/pistons visible); right-forearm Aether interface as a
  hero piece (screen, conduits, emitter); utility belt with modelled pouches; knee/shin guards; tech gloves with
  knuckle plates; armoured boots with toe/heel caps and real sole tread. Cyan/magenta glow accents, restrained.

## Giva Vale — beautiful (not sexualised) systems engineer
- Adult female, about 1.73 m, about 7.5 heads tall, athletic balanced proportions, elegant neck and shoulders.
- Face: refined, symmetric features, defined cheekbones, elegant jawline, slim straight nose, expressive almond
  eyes (brown) with natural lashes, shaped brows, natural full lips, smooth healthy skin with subtle natural makeup.
- Default hair: catalog `long_waves` (long, wavy, not curly; same head-size rule as Kael). Built-in fallback: `wavy`.
- Outfit: asymmetric graphite tech suit with violet panels; lightweight layered shoulder armour; signature
  left-side Aether harness with a glowing core, cabling and clips; forearm guard with holo screen; thigh rig;
  armoured boots; HUD visor (mesh `Visor`, hidden by the game when catalog eyewear is worn). Magenta/violet glow.

## Quality workflow (both)
- Hard surface: high-poly (support loops, bevels, boolean panel cuts, bolts, vents, hinges, pistons, cable
  sockets) baked to the game mesh: normal + AO + curvature; curvature/AO drive edge wear, chips, cavity grime.
- Cloth: real folds at elbows/knees/shoulders/waist on the high-poly, plus seams, stitching, zips, pocket flaps,
  webbing; baked to the game mesh.
- Materials: carbon fibre, painted/anodised metal with edge wear, brushed steel, rubber grip, ballistic nylon,
  leather, matte polymer, tinted glass/screens, emissive conduits following panel lines; decals with invented
  glyphs, serials, hazard chevrons (no real brands). 2K PBR per material set (BaseColor, Normal, MaskMap with
  R metallic, G occlusion, B paint mask, A smoothness).

## Deformation (this is what makes movement look right)
- Clean edge flow at shoulders, elbows, wrists, hips, knees and neck (enough loops to bend without collapse).
- Careful weight painting: smooth falloff, no stray weights, max 4 influences per vertex (Unity uses up to 4).
  Garments and armour weighted so they move with the body without shearing; rigid plates follow one bone (or a
  blended pair) and must not intersect the body in extreme poses.
- Twist bones: add `mixamorig:LeftForeArmTwist`, `mixamorig:RightForeArmTwist`, `mixamorig:LeftArmTwist`,
  `mixamorig:RightArmTwist` (children of ForeArm / Arm, at about 60 % along the bone) and weight the wrist /
  upper-arm twist zones to them. The game drives them at runtime with `TwistBones.cs` (written by the Kael agent;
  the Giva agent uses the same bone names): ForeArmTwist takes 50 % of the hand's twist about the forearm axis,
  ArmTwist takes 50 % of the upper arm's twist away from the shoulder. Unity's humanoid ignores extra bones, so the
  rest of the rig is unchanged.
- Corrective blend shapes for elbows, knees, shoulders (arm raised), hips (leg raised) and wrists, named
  `corr_<Bone>_<axis>_<deg>` (e.g. `corr_LeftForeArm_x_120`), listed in the manifest under `"correctives"`:
  `[{ "shape": "...", "bone": "mixamorig:LeftForeArm", "parent": "mixamorig:LeftArm", "axis": [x,y,z],
  "from": 30, "to": 120 }]` (weight rises linearly with the bone's bend angle relative to its parent between `from`
  and `to` degrees). The runtime driver `CorrectiveShapes.cs` is written by the Kael agent.

## Rig and naming contract (must not break)
- Bone names and hierarchy: the existing `mixamorig:*` skeleton. Rest pose: the A-pose that matches
  `Assets/Art/Animations/Anim_Male.fbx` / `Anim_Female.fbx` (bone directions within ~1°; the game builds the
  humanoid avatar from these names automatically and enforces a T-pose itself).
- Mesh names the game toggles: `Body`, `Brows`, `Lashes`, `Eyes`, `Teeth`, `Tongue`, `Hair_<style>`,
  `Facial_<style>`, `Gloves`, `Harness`, `HipModule`, `ThighRig`, `Visor`, and armour parts starting with
  `Pauldron`, `ChestPlate`, `ChestRig`, `KneePad`, `ForearmGuard`, `ShoulderR`, `Interface`.
- Material slots the builder knows: `Skin`, `Eyes`, `Brows`, `Lashes`, `Teeth`, `Tongue`, `Hair_*`, `Facial_*`,
  `Garment_Top`, `Garment_Pants` (runtime tint composite from a mask), `Armor`, `Boots`, `Gloves`, `Metal`,
  `Glow`, `Glow2`, `Screen`, `Belt`, `Harness`, `Strap`, `Cloth_*`. New slots: describe them in `materialDefs`
  and report what `CharacterBuilder.MaterialFor` needs (the lead adds it).
- Body morph blend shapes used by the designer sliders must keep their names (`m_*_incr` / `m_*_decr`, see
  `Assets/Scripts/Game/Appearance.cs` BodyMorphs / FaceMorphs), plus `x_mouthOpen` etc. for lip sync.
- Export: `unity/EchoesOfAether/Assets/Art/Characters/<Kael|Lyra>/<Name>.fbx` + `<Name>.manifest.json` +
  `Textures/`, same manifest schema as now (read the current manifest and `Assets/Editor/Characters/CharacterBuilder.cs`).
- Budget: about 90k triangles visible at LOD0; optional LOD1 (about 40 %) as meshes named `<mesh>_LOD1` in the same
  FBX (the lead adds LODGroup support).

## Verification (required before reporting done)
1. Blender: turntable beauty renders and pose tests with the game's real clips (import the actions from
   `Anim_Male.fbx` / `Anim_Female.fbx` onto your rig: bone names match) at extreme frames: run, sprint, all attacks,
   dash, climb, kneel_work, death, sit. No candy-wrap wrists, collapsed elbows/shoulders, broken knees or
   intersections.
2. Unity (one process at a time via the lock below):
   - `CharacterBuilder.BuildAll` (with -quit), then `SmokeTest.RunHeroes` (designer close-ups: face, body, back).
   - `SmokeTest.RunCombat -combatFeel` (play-mode combat sequences, both heroes) for deformation in motion.
   - Note: an edit-mode `AnimationClip.SampleAnimation` render does not skin correctly; judge motion from play-mode captures.
3. Iterate until it genuinely looks AAA in Unity, not only in Cycles.

Unity lock: `until mkdir /Users/kartikey/Desktop/Game/.unity_lock 2>/dev/null; do sleep 30; done` … `rmdir /Users/kartikey/Desktop/Game/.unity_lock`
(also on failure). Never kill another Unity process. Copy Captures/smoke PNGs out right away (others overwrite them).

## Runtime drivers: exact data contract (added by the Kael agent; code in `Assets/Scripts/Actors/`)
- `TwistBones.cs` (added to the prefab by CharacterBuilder whenever the twist bones exist; manifest key
  `"twistBones"` is optional, the defaults below apply without it):
  - `<Side>ForeArmTwist` (child of `<Side>ForeArm`, on the forearm axis): mode `follow`, its roll about the forearm
    axis = 0.5 x the hand's roll relative to the forearm. Weight mid-forearm -> wrist onto it.
  - `<Side>ArmTwist` (child of `<Side>Arm`, on the upper-arm axis): mode `counter`, it keeps 0.5 of the upper arm's
    roll relative to `<Side>Shoulder` (un-rolls the other half). Weight the shoulder-side half of the upper arm (deltoid
    zone) onto it, blending into `<Side>Arm` towards the elbow.
  - Twist bones must lie exactly on their parent's long axis with the parent's orientation (roll only, no swing).
  - Optional override: `"twistBones": [{"bone","source","reference","weight","mode"}]`.
- `CorrectiveShapes.cs` (manifest `"correctives"`, schema above; optional `"child"` and `"power"` keys):
  - angle = rotation of the bone's direction (bone -> its main child; twist bones ignored; hand -> Middle1) in the
    `parent` frame, measured from its rest-pose direction, signed by the right-hand rule about `axis`;
  - `axis` is in Blender world space of the rest pose (Z up, character facing -Y, +X = character's left), e.g.
    `(rig.matrix_world @ bone.matrix_local).to_3x3() @ Vector((1, 0, 0))`; weight = clamp((angle - from) / (to - from)).
  - Bake each shape as a rest-space delta (inverse of the skinning matrix at the authoring pose) and add the same
    shape name to every mesh that needs it (Body, Top, Pants, Gloves ...); the driver sets them all.
