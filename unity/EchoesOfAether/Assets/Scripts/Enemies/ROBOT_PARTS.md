# Robot parts contract (enemy models)

Enemy visuals are built by `RobotRig` (`Assets/Scripts/Enemies/RobotRig.cs`). At spawn it first tries

```
Resources.Load<GameObject>("Models/Robots/" + model)
```

and, if found, instantiates it and binds transforms **by name**. If the asset is missing or a required
transform is missing, it logs a warning and builds the procedural placeholder robot instead (same proportions
as below), so models can be dropped in one at a time.

| Enemy type (factory)  | Resources path                              | Notes |
|-----------------------|---------------------------------------------|-------|
| `drone`               | `Resources/Models/Robots/drone`             | flying, no skeleton (see Drone) |
| `sentinel`            | `Resources/Models/Robots/sentinel`          | 2.15 m biped |
| `warden`              | `Resources/Models/Robots/warden`            | 2.6 m elite sentinel (crest, plating, shield emitter on left forearm) |
| `stalker`             | `Resources/Models/Robots/stalker`           | 2.0 m slim biped with long hand blades |
| `guardian`            | `Resources/Models/Robots/guardian`          | 5.2 m boss with chest `core` and `plate_L/plate_R` |
| `guardian_vault`      | `Resources/Models/Robots/guardian_vault`    | optional; falls back to `guardian` (glow is recoloured red at runtime) |

All animation is **procedural** (keyframed poses in code, `RobotClips.cs`). Models need **no animation clips**;
any `Animator` on the prefab is disabled and any `Collider` is removed (gameplay colliders are added by code).

## Units, axes, scale

* Metres, +Y up, **facing +Z** (Unity). The pivot of the prefab (and the `root` transform) is **on the ground
  between the feet**. Robot's **left side is -X** in Unity.
* Blender: model in metres facing **-Y** (Blender front view), robot's left on +X; export FBX with
  *Forward: -Z, Up: Y*, *Apply Scalar Scale: FBX Units Scale*, *Apply Transform* on (or tick *Bake Axis
  Conversion* in the Unity importer). Unity import *Scale Factor 1*, *Convert Units* on. The prefab root must
  end up with identity rotation and scale 1.
* Overall heights (feet to top of head): sentinel 2.15, warden 2.6, stalker 2.0, guardian 5.2.
  `RobotRig` warns if the `hips` height is more than 20% off the table below.

## Skeleton (bipeds: sentinel, warden, stalker, guardian)

Exactly these 20 transform names are required (a namespace prefix like `Armature|` or `rig:` is ignored):

```
root                         (ground, between the feet)
└─ hips
   ├─ spine
   │  └─ chest
   │     ├─ neck
   │     │  └─ head
   │     ├─ clavicle_L ─ upperarm_L ─ forearm_L ─ hand_L
   │     └─ clavicle_R ─ upperarm_R ─ forearm_R ─ hand_R
   ├─ thigh_L ─ shin_L ─ foot_L
   └─ thigh_R ─ shin_R ─ foot_R
```

* `_L` / `_R` are the **robot's own** left / right (`_L` at -X in Unity).
* Each transform's **pivot (position)** must be at the joint position in the tables below (tolerance a few cm).
  The bone *orientation* does not matter (Blender bone rolls are fine): `RobotRig` records each bone's rest
  rotation at bind time and applies the procedural pose on top of it in world-aligned axes.
* **Rest pose = A-pose:** arms hang down and out at **14 deg from vertical** with straight elbows and
  wrists, legs straight, standing upright, facing +Z. Poses are authored relative to this rest pose, so a
  T-pose model will animate wrongly.
* Rigid parts: put each mesh as a child of the bone it moves with (e.g. forearm plating under `forearm_L`).
  Skinned meshes bound to these bones also work (rigid weights recommended).
* Hips are translated by the animation (crouches, slams); every other bone only rotates.

### Special parts

| Name | Parent | Purpose |
|------|--------|---------|
| `core`    | `chest` (guardian) | Glowing chest core: lock-on / aim point, laser origin, exposed-window weak spot (hits within 1.6 m of it deal 2.4x while exposed). Pivot at its centre: (0, 3.597+0.404, -0.064+0.751) = **(0, 4.001, 0.687)** in rest pose. |
| `plate_L`, `plate_R` | `chest` (guardian) | Armour plates in front of the core. They slide sideways (away from `core`, along local X) by 0.46 m while the core is exposed, then close. Rest centres (+/-0.347, 4.001, 0.803). |
| `body`    | prefab root (drone) | Drone body; pitches/rolls with movement and spins when staggered. Pivot = drone centre = **aim point**. |
| `rotor_0`..`rotor_3` | `body` (drone) | Rotor discs, spun about their local +Y. |

Optional names used only for material matching: anything containing `glow`, `core`, `rotor`.

### Materials

Materials are matched by **material name or object name (case-insensitive substring)** and replaced at runtime
by code-created URP materials so hit flashes, attack telegraphs, phasing transparency and per-variant glow
colours work:

| Substring | Runtime material | Notes |
|-----------|------------------|-------|
| `core`    | `robot_core`  (Unlit HDR) | guardian core only (pulses gold while exposed) |
| `glow` / `emissive` | `robot_glow` (Unlit HDR) | visor, seams, blades; brightens 2.6x during telegraphs |
| `rotor`   | `robot_rotor` (transparent dark) | drone rotor discs |
| `shell`   | `robot_shell` (Lit, metallic .65, smoothness .58) | outer armour; white hit flash |
| `frame`   | `robot_frame` (Lit, metallic .75, smoothness .45) | structure; dimmer hit flash |
| `joint`   | `robot_joint` (Lit, near black) | joints and cables |

Other materials are kept as authored (no hit flash). Base colours come from code palettes
(sentinel shell #4a4f56 / frame #24272c / glow #ff5a3a; warden #3a2e30 / #1f1c1e / #ff3b30; stalker #2a2436 /
#141218 / #b48cff; guardian #3a3f48 / #1c1f24 / #5fd8ff (vault: #ff5a3a); drone #2b3036 / #5a6068 / #5fd8ff),
so texture maps should be greyscale detail (or use the palette colours). Keep each robot under ~5k triangles
(WebGL target) and avoid more than 4 materials.

## Bind-pose joint positions (Unity space, metres, rest A-pose)

Computed by `RobotRig.ComputeJoints(height, shoulderWidth)` (reference 1.8 m body scaled by `s = height / 1.8`;
shoulder width 1.15 for sentinel/warden/stalker and 1.35 for the guardian). `headCenter` and `handEnd_*` are
reference points (not transforms) used to place the head shell and hands/blades.

### sentinel (height 2.15 m, s = 1.1944, shoulderWidth 1.15)
| node | x | y | z |
|---|---:|---:|---:|
| `root` | 0.000 | 0.000 | 0.000 |
| `hips` | 0.000 | 1.141 | 0.000 |
| `spine` | 0.000 | 1.284 | -0.014 |
| `chest` | 0.000 | 1.487 | -0.026 |
| `neck` | 0.000 | 1.756 | -0.031 |
| `head` | 0.000 | 1.863 | -0.014 |
| `clavicle_L` | -0.033 | 1.736 | -0.007 |
| `upperarm_L` | -0.255 | 1.741 | -0.026 |
| `forearm_L` | -0.344 | 1.388 | -0.041 |
| `hand_L` | -0.407 | 1.082 | -0.014 |
| `clavicle_R` | +0.033 | 1.736 | -0.007 |
| `upperarm_R` | +0.255 | 1.741 | -0.026 |
| `forearm_R` | +0.344 | 1.388 | -0.041 |
| `hand_R` | +0.407 | 1.082 | -0.014 |
| `thigh_L` | -0.112 | 1.111 | 0.000 |
| `shin_L` | -0.122 | 0.615 | +0.019 |
| `foot_L` | -0.127 | 0.105 | -0.026 |
| `thigh_R` | +0.112 | 1.111 | 0.000 |
| `shin_R` | +0.122 | 0.615 | +0.019 |
| `foot_R` | +0.127 | 0.105 | -0.026 |
| `headCenter` | 0.000 | 1.986 | +0.017 |
| `handEnd_L` | -0.452 | 0.865 | -0.005 |
| `handEnd_R` | +0.452 | 0.865 | -0.005 |

### warden (height 2.6 m, s = 1.4444, shoulderWidth 1.15)
| node | x | y | z |
|---|---:|---:|---:|
| `root` | 0.000 | 0.000 | 0.000 |
| `hips` | 0.000 | 1.379 | 0.000 |
| `spine` | 0.000 | 1.553 | -0.017 |
| `chest` | 0.000 | 1.798 | -0.032 |
| `neck` | 0.000 | 2.123 | -0.038 |
| `head` | 0.000 | 2.253 | -0.017 |
| `clavicle_L` | -0.040 | 2.099 | -0.009 |
| `upperarm_L` | -0.309 | 2.106 | -0.032 |
| `forearm_L` | -0.416 | 1.679 | -0.049 |
| `hand_L` | -0.492 | 1.308 | -0.017 |
| `clavicle_R` | +0.040 | 2.099 | -0.009 |
| `upperarm_R` | +0.309 | 2.106 | -0.032 |
| `forearm_R` | +0.416 | 1.679 | -0.049 |
| `hand_R` | +0.492 | 1.308 | -0.017 |
| `thigh_L` | -0.136 | 1.343 | 0.000 |
| `shin_L` | -0.147 | 0.744 | +0.023 |
| `foot_L` | -0.153 | 0.127 | -0.032 |
| `thigh_R` | +0.136 | 1.343 | 0.000 |
| `shin_R` | +0.147 | 0.744 | +0.023 |
| `foot_R` | +0.153 | 0.127 | -0.032 |
| `headCenter` | 0.000 | 2.402 | +0.020 |
| `handEnd_L` | -0.547 | 1.046 | -0.006 |
| `handEnd_R` | +0.547 | 1.046 | -0.006 |

### stalker (height 2.0 m, s = 1.1111, shoulderWidth 1.15)
| node | x | y | z |
|---|---:|---:|---:|
| `root` | 0.000 | 0.000 | 0.000 |
| `hips` | 0.000 | 1.061 | 0.000 |
| `spine` | 0.000 | 1.194 | -0.013 |
| `chest` | 0.000 | 1.383 | -0.024 |
| `neck` | 0.000 | 1.633 | -0.029 |
| `head` | 0.000 | 1.733 | -0.013 |
| `clavicle_L` | -0.031 | 1.614 | -0.007 |
| `upperarm_L` | -0.238 | 1.620 | -0.024 |
| `forearm_L` | -0.320 | 1.291 | -0.038 |
| `hand_L` | -0.379 | 1.006 | -0.013 |
| `clavicle_R` | +0.031 | 1.614 | -0.007 |
| `upperarm_R` | +0.238 | 1.620 | -0.024 |
| `forearm_R` | +0.320 | 1.291 | -0.038 |
| `hand_R` | +0.379 | 1.006 | -0.013 |
| `thigh_L` | -0.104 | 1.033 | 0.000 |
| `shin_L` | -0.113 | 0.572 | +0.018 |
| `foot_L` | -0.118 | 0.098 | -0.024 |
| `thigh_R` | +0.104 | 1.033 | 0.000 |
| `shin_R` | +0.113 | 0.572 | +0.018 |
| `foot_R` | +0.118 | 0.098 | -0.024 |
| `headCenter` | 0.000 | 1.848 | +0.016 |
| `handEnd_L` | -0.420 | 0.805 | -0.004 |
| `handEnd_R` | +0.420 | 0.805 | -0.004 |

### guardian (height 5.2 m, s = 2.8889, shoulderWidth 1.35)
| node | x | y | z |
|---|---:|---:|---:|
| `root` | 0.000 | 0.000 | 0.000 |
| `hips` | 0.000 | 2.759 | 0.000 |
| `spine` | 0.000 | 3.106 | -0.035 |
| `chest` | 0.000 | 3.597 | -0.064 |
| `neck` | 0.000 | 4.247 | -0.075 |
| `head` | 0.000 | 4.507 | -0.035 |
| `clavicle_L` | -0.081 | 4.198 | -0.017 |
| `upperarm_L` | -0.725 | 4.212 | -0.064 |
| `forearm_L` | -0.939 | 3.357 | -0.098 |
| `hand_L` | -1.092 | 2.616 | -0.035 |
| `clavicle_R` | +0.081 | 4.198 | -0.017 |
| `upperarm_R` | +0.725 | 4.212 | -0.064 |
| `forearm_R` | +0.939 | 3.357 | -0.098 |
| `hand_R` | +1.092 | 2.616 | -0.035 |
| `thigh_L` | -0.272 | 2.687 | 0.000 |
| `shin_L` | -0.295 | 1.488 | +0.046 |
| `foot_L` | -0.306 | 0.254 | -0.064 |
| `thigh_R` | +0.272 | 2.687 | 0.000 |
| `shin_R` | +0.295 | 1.488 | +0.046 |
| `foot_R` | +0.306 | 0.254 | -0.064 |
| `headCenter` | 0.000 | 4.804 | +0.040 |
| `handEnd_L` | -1.201 | 2.093 | -0.012 |
| `handEnd_R` | +1.201 | 2.093 | -0.012 |

## Drone (no skeleton)

Pivot (prefab root) = drone centre (it hovers 3-7 m above ground; the aim point is the pivot).

| Part | Position (m) | Shape (procedural placeholder) |
|------|--------------|-------------------------------|
| `body` | (0, 0, 0) | parent of everything below |
| shell | (0, 0, 0) | ellipsoid r 0.42 scaled (1, 0.62, 1.1) |
| ring | (0, 0, 0) | horizontal torus R 0.58, tube 0.06 |
| eye (glow) | (0, 0.02, 0.42) | sphere r 0.13, faces +Z |
| visor | (0, 0.02, 0.43) | torus R 0.16 facing +Z |
| gun | (0, -0.2, 0.32) | barrel along +Z, length 0.42 |
| under-glow | (0, -0.27, 0) | disc r 0.16 facing down |
| arms 0..3 | 0.55 m out at 45/135/225/315 deg, y 0.05 | 0.08 x 0.05 x 0.5 boxes |
| `rotor_0..3` | 0.82 m out at the same angles, y 0.1 | discs r 0.22 |

## Procedural placeholder layout (reference for modellers)

The placeholder bodies in `RobotBodies.cs` show the intended silhouette per robot (rounded boxes and
cylinders attached to the bones above): chest shell with a glowing chest core and back vents, visor slit on the
head, shoulder pauldrons on the clavicles, forearm glow seams (telegraph), a glowing blade on the sentinel's
right forearm, long glowing hand blades on the stalker, crest + extra plating + left-forearm shield emitter on the
warden, and on the guardian a massive chest with the exposed `core` between two `plate_*`s, three glowing
exhaust stacks on its back and glowing shoulder fins.

The warden's frontal shield dome and the guardian's laser beam and shockwave rings are effects created in code;
they are not part of the models.
