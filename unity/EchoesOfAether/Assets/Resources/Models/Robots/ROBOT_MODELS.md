# Robot models (Blender → Unity)

Rigid-part robot FBX files for `RobotRig` (`Resources.Load<GameObject>("Models/Robots/<type>")`). They are built
headlessly by Python scripts in `blender/robots/` and checked against `Assets/Scripts/Enemies/ROBOT_PARTS.md` by
`blender/robots/check_robots.py`. The checker reads the contract file itself; all six files **PASS**.

| File | Height | Triangles | Materials | Nodes (mesh) | Notes |
|---|---:|---:|---|---:|---|
| `drone.fbx`    | 0.52 m pod, 1.7 m wide | 4,408 | shell, frame, glow, rotor | 14 (9) | `body` → `rotor_0..3` |
| `sentinel.fbx` | 2.15 m | 5,770 | shell, frame, joint, glow | 21 (19) | forearm blade is a separate weapon model (see below) |
| `warden.fbx`   | 2.6 m  | 6,402 | shell, frame, joint, glow | 21 (19) | crest, mantle, shield emitter on `forearm_L` |
| `stalker.fbx`  | 2.0 m  | 3,900 | shell, frame, joint, glow | 21 (19) | glowing blades on `hand_L/R` |
| `guardian.fbx` | 5.2 m (stacks reach 5.55 m) | 8,978 | shell, frame, joint, glow | 24 (22) | `core`, `plate_L`, `plate_R` |
| `bolt.fbx`     | 1.55 m | 5,798 | shell, frame, joint, glow | 21 (19) | NPC, not in the contract (see below) |

The material names are exactly `robot_shell`, `robot_frame`, `robot_joint`, `robot_glow` and `robot_rotor`.

## What RobotRig needs to know

* **Hierarchy and pivots.** Bipeds have the 20 contract transforms (`root … foot_R`) with pivots on the contract
  joints. The largest error is 0.75 mm, which is the 3-decimal rounding in the contract tables. The mesh for each
  part sits directly on its bone's GameObject (for example, the `chest` transform has the chest MeshRenderer).
  `root` and the drone's `rotor_N` are empty transforms.
* **Rotation and scale.** Every node has an identity local rotation and a scale of 1. The robot faces +Z, its left
  is -X, and units are metres. The FBX declares a Y-up right-handed axis system with UnitScaleFactor 100
  (1 unit = 1 m), so Unity needs only its usual X flip. The defaults work: Scale Factor 1, Convert Units on, Bake
  Axis Conversion off, Normals = Import.
* **The extra `meta_<type>` root node.** It is an empty sibling of `root` (or of the drone's `body`). With a
  single root node, Unity's importer reuses that node as the prefab root and renames it to the file name, so
  `root` / `body` would disappear. Ignore `meta_<type>`.
* **Guardian.**
  * `core` is a child of `chest`, with its pivot at the core centre (0, 4.001, 0.687). Its only material is
    `robot_glow`; RobotRig swaps it to `robot_core` because it is the `core` transform.
  * `plate_L` / `plate_R` are children of `chest`, with pivots at (∓0.347, 4.001, 0.803).
  * Each visible plate sits 0.17 m in front of its pivot, so the closed plates clear the core. The 0.46 m slide
    along local X stays inside a recessed bay with rails above and below.
  * No other object or material name on the guardian contains `core`.
* **Drone.**
  * `body` (the aim point at (0, 0, 0)) holds all static parts: shell, eye, visor, gun, under-glow, stabiliser
    ring, booms and fan ducts.
  * Each `rotor_N` is an empty at 0.82 m out (45/135/225/315°, y = 0.1) with identity rotation, because
    Drone.cs overwrites `localRotation`.
  * Under each rotor, `prop_N` holds the blades (`robot_frame`) and `rotor_N_blur` holds the spin disc
    (`robot_rotor`). The blade objects deliberately avoid "rotor" in their name, so only the disc becomes
    transparent.
  * The drone's dark detail parts use `robot_shell` (the drone's dark colour), keeping it at 4 materials like
    the placeholder.
* **Emissive parts all use `robot_glow`.**
  * Bipeds: visors, the chest light, forearm telegraph seams, blades, Aether cracks, exhaust glows and shoulder
    heat-sink fins. Warden adds the crest inlay and shield-emitter lenses; BOLT adds its eye, antenna tip, status
    lights and torch tip.
  * Drone: the eye, side lights, under-glow and rear exhaust.
  * Because all of these share one material, they all brighten together during telegraphs (2.6x).
* **Object names** never contain a material keyword (`shell`, `frame`, `joint`, `glow`, `rotor`, `emissive`,
  `core`) unless intended. RobotRig matches material *and* object names, so such a name would capture every slot
  on that renderer. The checker replays RobotRig's swap rule on every slot.
* **No Animator clips, colliders or skinning.** Animation Type can be None (Generic also works: RobotRig disables
  the Animator).

## Textures (optional, not used by the current C#)

`Textures/robot_worn_metal_{BaseColor,Normal,MetallicSmoothness}.png` form a 1024², seamlessly tiling, greyscale
worn-paint set, following the contract's "texture maps should be greyscale detail":

* BaseColor (sRGB) multiplies `_BaseColor`.
* Normal is OpenGL / +Y.
* MetallicSmoothness is URP-packed: R = metallic, A = smoothness.

UV0 on every mesh is a smart-projected, non-overlapping atlas scaled to **1 UV unit = 1 m**, so a tiling of about
2.5 gives the detail density used in the previews. The FBX materials have **no** textures on purpose: with
"Naming: By Base Texture Name" Unity would rename them after the texture and break RobotRig's name matching.

*Requested change (RobotRig owner):* in `MakeMaterials`, assign these maps to ShellMat and FrameMat (`_BaseMap`,
`_BumpMap` with `_NORMALMAP`, `_MetallicGlossMap` with `_METALLICSPECGLOSSMAP`, tiling 2.5). If they are not
adopted, move them out of `Resources/`, because everything under Resources ships in the WebGL build (three
1024² textures).

## BOLT (not in ROBOT_PARTS.md)

Npc.ts builds BOLT as a `RobotModel(1.55, …, 'robot')` on the robot rig. `bolt.fbx` therefore uses the same
20-transform skeleton with the `RobotRig.ComputeJoints(1.55, 1.15)` joints, the same A-pose rest, +Z facing and the
same material names. Its palette is shell #9a7a2a, frame #2a2a2e, glow #ffc24a at intensity 2.2.

*Requested change:* RobotRig has no `RobotKind` or height for BOLT. Adding `RobotKind.Bolt` (HeightOf 1.55, robot
clips including `sit`), or an NPC path that reuses `TryBindModel`, would let the NPC code bind it unchanged.

## Interpretations and deviations

* **Triangle budget.** The contract says "~5k for WebGL" while the art brief said 3–12k (Guardian up to 25k).
  The stalker and drone are under 5k, the sentinel/BOLT are about 5.8k, the warden 6.4k and the one-per-fight
  guardian about 9k. A biped is 19–22 renderers with 52–62 submeshes in total (the placeholder sentinel is about
  36 single-material renderers). Every submesh uses one of the same 4 runtime materials, so the SRP Batcher
  can batch them.
* **Guardian head.** It is about 15% larger and sits higher and further forward than the placeholder, so the top of
  the head reaches the contract's 5.2 m (the placeholder stopped at about 5.0 m) and stays visible above the plate
  bay.
* **Guardian core.** The core is a flattened icosphere, so the closed plates cover it.
* **Drone ring.** The stabiliser ring is open at the front. The prototype's torus passes through the eye.
* **Torso widths below the shoulders** are kept inside the A-pose arm path to avoid rest-pose clipping. The
  placeholder chests intersect the arms; the silhouette mass comes from pauldrons, yokes and depth instead.
* **`guardian_vault`** is not exported. The contract marks it optional, and RobotRig falls back to `guardian` and
  recolours the glow.

## Regenerate / verify

```
cd blender/robots
B=/Applications/Blender.app/Contents/MacOS/Blender
$B -b --factory-startup --python make_textures.py                      # Textures/
$B -b --factory-startup --python build_robots.py -- [types] [--no-preview]   # FBX + out/*.blend + previews/
$B -b --factory-startup --python-exit-code 1 --python check_robots.py -- [types]   # contract check, exit 1 on failure
$B -b --factory-startup --python render_lineup.py                      # previews/lineup.png from the exported FBX
```

## Weapons (separate models)

The Sentinel / Warden forearm blade, the drone's twin blaster and the Guardian's arm cannon and folding arm blade are
not part of these files. They are built by `blender/weapons/build_weapons.py` into `Assets/Resources/Weapons/`
(`sentinel_blade.fbx`, `drone_blaster.fbx`, `guardian_weapons.fbx`) and attached to the bones at spawn by
`EnemyWeaponFx` (their glow faces use the robot's own glow material, so telegraphs still brighten them).

