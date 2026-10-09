# Echoes of Aether — Animation Bible

Status date: 2026-10-04. The game has two animation systems:

| System | Characters | Format |
|---|---|---|
| Humanoid | Kael, Giva and the human NPCs | 42 CMU motion-capture clips (two styles: male for Kael, female for Giva) retargeted onto the MPFB `mixamo_unity` rig, played by a Unity Mecanim Humanoid Animator |
| Robot | Enemies and BOLT | A procedural keyframe animator written in C#, driving the rigid-part robot skeleton |

Facial animation (blink, talk, expressions) is driven by blendshapes from code.

## 1. Humanoid pipeline

**Since 2026-10-08 the primary clip source is the Quaternius Universal Animation Library** (UAL 1 and 2, CC0), for
22 of the 44 slots per style (idle, talk, jump / fall / land, reactions, interaction, sit, folded-arms NPC idle, the
heroes' attacks and Kael's pistol); walk, run, sprint, crouch, the combat stance and the remaining NPC clips stay CMU,
and Mixamo files override both (section 1.11).

All 42 humanoid clips originally came from **CMU Graphics Lab motion capture** (mocap.cs.cmu.edu; credit line in
`docs/ANIMATION_CREDITS.md` and the in-game credits). The earlier prototype-sampled clips
(`tools/anim/sample_clips.mjs` → `blender/scripts/retarget.py`) are superseded and no longer used.

### 1.1 Source and download (`tools/anim/cmu.py`)
32 CMU trials (ASF/AMC → BVH), fetched on demand (`python3 tools/anim/cmu.py fetch-all`, ~46 MB, git-ignored;
raw data is never shipped). Every clip's subject/trial and edits are listed in `docs/ANIMATION_CREDITS.md`.

### 1.2 Retarget and clean-up (`blender/anim/cmu_retarget.py`, `clips_cmu.py`, `qmath.py`)
- Rest-pose aligned retarget onto the `mixamo_unity` rig (bones `mixamorig:*`), baked at 30 fps.
- In place (no root translation except vertical for jumps); seamless loops (0.00° / 0.00 cm seams).
- Locomotion time-scaled so planted feet travel at exactly 1.9 / 5.0 / 7.4 m/s; a contact IK step pins the
  planted heel/ball/toe to the floor. Unity scales playback to the game speeds 2.2 / 5.2 / 7.6 m/s.
- Exported as `Assets/Art/Animations/Anim_Male.fbx` (Kael rig) and `Anim_Female.fbx` (Giva rig) with the same
  take names; verified by `tools/anim/verify_fbx.py`; previews in `blender/anim/previews/`.

### 1.3 Clip metadata (`clips_meta.json`)

* **Content.** Per style (`male` and `female`), each of the 42 clips has `duration`, `loop`, `events` (time in
  seconds and name) and `speed`.
* **Provenance.** The file is `clips.json` without the frame data. Every field matches `blender/anim/clips.json`
  (checked on 2026-10-03). No committed script writes it, so after re-sampling it has to be regenerated from
  `clips.json` by dropping `frames`.

### 1.4 Clip list

Durations are for the male style; the female set has the same names.

| Group | Clips (duration in s; L = loops; events) |
|---|---|
| Locomotion | `idle` L, `walk` L, `run` L, `sprint` L, `combat_idle` L, `jump`, `fall`, `land` 0.38 |
| Kael combat | `k_light1` 0.52, `k_light2` 0.54, `k_light3` 0.62 (each: `hit_start`, `combo`, `hit_end`); `k_heavy` 0.92 (`hit_start` 0.36, `impact` 0.43, `hit_end` 0.50); `k_pulse` 0.85 (`pulse` 0.30); `k_ult` 1.60 (`impact` 0.90); `dash` 0.36 |
| Giva combat | `l_quick1` 0.38, `l_quick2` 0.40 (`hit_start`, `combo`, `hit_end`); `l_heavy` 0.78 (`hit_start` 0.16, `impact` 0.32, `hit_end` 0.46); `l_echo` 0.75 (`echo` 0.24); `l_ult` 1.35 (`impact` 0.60); `phase_step` 0.30 |
| Ranged (upper body) | `aim_r` L, `aim_l` L, `fire_r` 0.30, `fire_l` 0.30 (`fire` 0.02) |
| Reactions | `hit` 0.30, `stagger` 0.80, `death` 1.15 |
| Interaction and traversal | `interact` 0.80 (`use` 0.30), `pickup` 0.55 (`use` 0.25), `climb` L |
| NPC and cinematic | `talk` L, `npc_crossed` L, `npc_hips` L, `npc_work` L, `npc_look` L, `npc_react` 1.30, `wave` 1.30, `sit` L, `kneel_work` L, `lie` L, `wake` 3.40 |

* Kael's moves use the right hand (`aim_r`, `fire_r`, bolt origin on the right hand). Giva's use the left.
* Both style sets contain every clip, so either hero could play the other's moves.

### 1.5 Unity import

`CharacterBuilder.ConfigureAnimations` imports the clips:

* **Rig.** Humanoid, avatar created from the FBX.
* **Clip split.** One clip per FBX take, named after the action.
* **Looping.** `loopTime` comes from `clips_meta.json`.
* **Root motion.** All root rotation, height and XZ position are locked (in-place clips). Movement is code-driven
  through the `CharacterController`.
* **Events.** Every metadata event becomes an `AnimationEvent` that calls `OnAnimEvent(string)` with the event
  name, at time = t ÷ duration.

### 1.6 Animator controller

`CharacterBuilder.BuildController` builds `Humanoid_Male` and `Humanoid_Female`.

**Parameters**

| Name | Type | Set by |
|---|---|---|
| `Speed` | float | `Hero` (horizontal speed, damped 0.05 s; the velocity already has its own acceleration; scaled ×0.2 during attacks) |
| `Grounded` | bool | `Hero` (`CharacterController.isGrounded` or coyote time) |
| `Combat` | bool | `Hero` (player in combat) |
| `VerticalSpeed` | float | `Hero` |
| `MoveSpeedMul` | float (default 1) | `Hero` (locomotion playback speed) |
| `ActionSpeed` | float (default 1) | `Hero.PlayAction` (attack-speed buffs, Giva's +12%) |

**Layers**

| # | Layer | Contents |
|---|---|---|
| 0 | Base | `Locomotion` blend tree on `Speed`: idle 0, then walk / run / sprint at the hero's speeds 2.2 / 5.2 / 7.6 m/s, each with time scale = game speed ÷ authored stride speed (§1.8, `MixamoImporter.Gaits`; the values used are in `clip_sources.json` → `locomotion`). `CombatLocomotion` is the same with `combat_idle`. Transitions: Locomotion ↔ CombatLocomotion on `Combat` (0.25 / 0.4 s); → `Jump` when airborne with `VerticalSpeed` > 1.5; → `Fall` when airborne with `VerticalSpeed` < -3; Jump → Fall at 85%; Jump/Fall → `Land` on ground contact; Land → (Combat)Locomotion at 60%, or at once (0.1 s) when `Speed` > 1.2. |
| 1 | Action | Full-body override. `Empty` default state, plus one state per non-locomotion clip with speed parameter `ActionSpeed`. Non-looping states (except `death`) return to `Empty` at 92% exit time over 0.14 s. Looping actions (`talk`, `npc_*`, `sit`, `kneel_work`, `lie`, `aim_r`, `aim_l`, `climb`) hold until replaced. |
| 2 | UpperBody | Avatar mask with body, head, arms, fingers and hand IK. States `Empty`, `aim_r`, `aim_l`, `fire_r`, `fire_l`. Fire returns to `Empty` at 90%. Lets the hero aim and fire bolts while walking. |

**How code drives it**

* **Actions.** `Hero.PlayAction(clip)` cross-fades layer 1 to the named state and times the action by the clip
  length ÷ speed.
* **Looping actions.** `talk`, `npc_*` and the like have no exit transition. `PlayClip(clip)` without `hold` used to
  leave them overriding the whole body after their timed length: `CancelActions` skipped the fade once the timer had
  run out, so after the reunion cinematic the hero kept the talk pose while running. Now:
  * `StopActions` fades layer 1 to `Empty` whenever the layer is not empty.
  * `ReleaseOrphanLoop` fades an orphaned loop once the hero is controllable again (or is a following companion).
    Scripted and cinematic heroes keep their loop.
* **Upper body.** `PlayUpper` and `StopUpper` drive layer 2. `CancelActions` cross-fades both layers to `Empty`.
* **Events.** Animation events arrive through `AnimEventRelay` (added to the model root) at `Hero.OnAnimEvent`. The
  current action's handler consumes them.

| Event | Consumer |
|---|---|
| `hit_start` / `hit_end` | Opens and closes the melee damage sweep |
| `combo` | Opens the chain window for the next buffered attack |
| `impact` | Area damage of heavies and ultimates |
| `pulse` | Aether Pulse shockwave |
| `echo` | Echo Sight reveal |
| `fire`, `use` | Exported but not consumed: bolts fire on input, and interactions do not wait for the clip |

### 1.7 Use by actor

| Actor | Clips used |
|---|---|
| Hero (player or companion) | Locomotion; `k_*` / `l_*` combat; `dash` / `phase_step`; `k_pulse`, `l_echo`, `k_ult`, `l_ult`; aim and fire on the upper body; `hit`, `stagger`, `death`, `land`, `pickup`; `climb` during scripted traversal; `npc_crossed` for the partner waiting at the camp before the reunion |
| NPCs (`Npc.cs`) | Their behaviour loop from zone data (`npc_crossed`, `npc_work`, `npc_hips`, ...); `talk` while in conversation; `npc_react` occasionally (8 s cooldown). Within 3.5 m the head glances toward the player. This does not happen while talking (the whole body turns toward the speaker instead) or in the `npc_work` and `lie` behaviours. |
| Cinematics | `lie` and `wake` in the intro and `talk` in the meeting (`PlazaCinematics.cs`). The Vault and Core scripts stage Maren's echo (`SpawnEcho`). |

Clips with no Unity caller at the final check: `interact`, `wave`, `kneel_work`, `npc_look`, `sit`. The prototype's
cinematics use some of them.

### 1.8 Mixamo import (`MixamoImporter`)

Mixamo clips replace CMU clips one by one. Any clip without a Mixamo file stays on CMU, and with no Mixamo files
at all the game builds exactly as before. The download list is in `docs/MIXAMO_DOWNLOAD_GUIDE.md`.

**Running it.** Drop the files into `incoming/mixamo/`, then run the character build:

```
Unity -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.CharacterBuilder.BuildAll
```

`BuildAll` runs `MixamoImporter.Import` between the CMU import and the controller build. The importer can also run
alone (`-executeMethod EOA.EditorTools.MixamoImporter.Import`, or menu **EOA/Import Mixamo Animations**), but the
controllers only pick the clips up in `BuildAll`. To test with another drop folder, pass `-mixamoIncoming <dir>` or
set `EOA_MIXAMO_INCOMING`.

**Files**

| Path | Role |
|---|---|
| `incoming/mixamo/<clip>.fbx` | Drop folder, shared by both styles. Names are the game clip names (`idle.fbx`, `k_light1.fbx`, ...). Other names are logged and ignored. |
| `incoming/mixamo/female/<clip>.fbx`, `.../male/<clip>.fbx` | Optional override for one style (Giva / Kael). |
| `incoming/mixamo/ybot.fbx` (also `tpose.fbx` / `reference.fbx`) | Optional but recommended: the same Mixamo character (Y Bot) downloaded once in **T-pose** ("FBX for Unity", With Skin). Copied to `Mixamo/Reference/reference.fbx`; every clip then copies its humanoid avatar (`CopyFromOther`). |
| `Assets/Art/Animations/Mixamo/` | Project copies. A file is copied when it is new or its SHA-1 differs. These copies are what the build uses, so a fresh clone works without `incoming/`. To go back to CMU for a clip, delete its copy here. |
| `Assets/Art/Animations/Mixamo/Generated/*.anim` | Re-timed one-shot clips (see below). Regenerated on every import; stale ones are deleted. |
| `Assets/Art/Animations/clip_sources.json` | Generated report: for every clip slot of both styles, `source` (`mixamo` or `cmu`), the file, length, category, analysis (strike, lead-in, stride speed, root travel, posture) and the re-timing. The `locomotion` block lists the blend thresholds and time scales the controllers were built with. |

**Import settings.** Each copy is set to **Humanoid**. With a T-pose reference, the avatar is copied from it.
Without one, the avatar is created from the file's own skeleton through the same deterministic bone map as the
characters (`CharacterBuilder.ConfigureAvatar`: Mixamo names with any `mixamorig*:` prefix, arms and legs brought into
a T-pose).

An animation-only FBX has no bind pose, so Unity takes the trunk, neck and head reference from the file's default
pose, and some exporters write the first animated frame there. The end-to-end test hit exactly this: a run with
36° of lean imported with its lean treated as neutral (1°). The importer therefore warns in `clip_sources.json`
(`restWarning`) when a file's default pose is not upright and no reference is present. The import uses one clip named after the game clip, taken from
the `mixamo.com` take (otherwise the longest take), with keyframe compression off.

**Analysis.** `ClipProbe` samples each clip on the hero rigs (Kael for shared and male files, Giva for female
files). It measures:

* **Strike:** the peak speed of a hand or foot relative to the hips.
* **Lead-in:** the dead frames before any limb moves faster than 15% of the clip's peak, and at least 0.35 m/s.
* **Stride speed:** the median speed of the hips over the planted foot. This works for in-place clips and for
  clips that travel.
* **Left-foot plant phase:** used to align the loops.
* **Root travel**
* **Posture**

**Clip categories**

| Category | Clips | Treatment |
|---|---|---|
| Strike | `k_light1-3`, `k_heavy`, `l_quick1-2`, `l_heavy`, `k_pulse`, `k_ult`, `l_echo`, `l_ult` | Re-timed piecewise linearly: lead-in trimmed, the detected strike moved onto the tuned hit time (light: 30% into the `hit_start`–`hit_end` window; heavy: 0.02 s before `impact`; abilities: their effect event), recovery fitted to the `clips_meta.json` duration. Wind-up plays at most 2.5×, recovery between 0.6× and 2×; the clip is cut at 1.25× the tuned duration. Events stay at the tuned seconds, so `Hero`'s `Active0/Active1/Recover` and the combat feel tuning hold. |
| Fit | `dash`, `phase_step`, `hit`, `stagger`, `land`, `jump`, `fire_r`, `fire_l`, `interact`, `pickup` | Lead-in trimmed, then one time scale (0.6–2×) fitting the tuned duration (cut at 1.25×). Events scaled to the new length. |
| Trim | `death` | Lead-in trimmed, natural speed. |
| Loop | every `loop: true` clip | Used straight from the FBX. Loop time and loop pose are on; `walk`, `run` and `sprint` get a cycle offset so every gait starts on the left-foot plant (the 1D blend tree keeps their feet in phase). |
| Natural | `wave`, `npc_react`, `wake` | Used straight from the FBX. |

Strike, fit and trim clips are written to `Generated/*.anim`, with keys moved, not resampled, and tangents scaled
per segment.

**Root settings.** Root rotation and height are baked into the pose. Height is based on the feet so they stay
grounded, except for `jump` and `fall`, which keep the authored height. Clips with less than 0.15 m of horizontal
root travel (all loops other than the gaits count as in place) keep their small sway baked in. Travelling clips have
the motion extracted as root motion, which the heroes discard (`applyRootMotion` is off), so the body stays over
the `CharacterController` and does not snap back.

**Locomotion tuning (`MixamoImporter.Gaits`).** A gait plays at `game speed ÷ authored speed`, so the planted foot
moves at exactly the hero's speed:

* **CMU:** authored speeds are 1.9 / 5.0 / 7.4 m/s (the `clips_meta.json` speeds).
* **Mixamo:** the authored speed is the stride speed measured on that style's hero rig, divided by the probe's bias.
  The bias is taken each build from the CMU gaits (authoring-rig reading ÷ authored speed, about 0.91). The playback
  scale is held between 0.75 and 1.4 so the cadence stays natural. If the scale hits that limit, the threshold moves
  to the speed the clip then matches.

Mixed sources (for example a Mixamo walk and a CMU run) blend correctly.

**End-to-end test (2026-10-06/07, no Adobe account needed).** `blender/anim` clips were exported from
`Anim_Male.fbx` / `Anim_Female.fbx` in Mixamo's file layout (`mixamorig:*` bones with `*_end` leaf bones, no mesh, one
`mixamo.com` take, 30 fps) into a temporary drop folder:

* `walk.fbx`, with the cycle shifted by 40%;
* `k_light1.fbx`, with 10 dead frames and slowed 1.6×;
* `run.fbx`;
* `female/idle.fbx`;
* `Some Dance.fbx`, a name that is not a game clip;
* `ybot.fbx`, the rest pose as the T-pose reference.

`BuildAll -mixamoIncoming <dir>` gave these results:

* The bad name was ignored.
* The female override was used for Giva only (Male 3 Mixamo slots, Female 4).
* `k_light1`: lead-in 0.30 s detected and trimmed, strike detected at 0.50 s (expected 0.49 s), re-timed to land at
  0.162 s with the tuned 0.533 s length and events.
* `walk`: plant phase 0.54 detected (CMU 0.92) and cycle offset 0.62 applied, so the gaits stay in phase.
* Locomotion time scales were re-tuned from the measured strides.

Without the reference, the run's 36–41° lean was absorbed into the avatar as "neutral" (measured 1°). With it, the lean
was kept as authored, which is why the reference is recommended. The test files were then removed and the clean
rebuild was back to 0 Mixamo slots.

**Licence.** See `THIRD_PARTY_LICENSES.md`, section "Animation: Mixamo by Adobe". The Mixamo FBX copies under `Assets/Art/Animations/Mixamo/` must not
be published as standalone files. If the repository is ever made public, keep that folder and `incoming/` out of it.

### 1.9 Posture ("proper humanoid"), crouch and responsiveness

**At the source (`blender/anim/posture.py`, run by `cmu_retarget.py` before grounding and foot locking).** The raw
CMU retarget carried the capture subjects' posture and calibration offsets: the run leaned 41° (male) / 33° (female),
the arms-crossed idle 41°, Giva's idle head was tilted 52° sideways and every combat_idle head was turned about 41°.
Wrists were bent 30–60°, and the idles stood on 22–29° of knee bend. Each clip now gets:

1. **Re-centring.** The mean local rotation of Spine/Spine1/Spine2, Neck, Head and the wrists becomes the rig's
   upright rest, and the motion around it is kept (per-category gain).
   **Twist.** The clip-average yaw of the chest (Spine2) and then of the head against the pelvis is removed by one
   constant twist (Spine 40 / Spine1 30 / Spine2 30 %, then Neck / Head) about each parent's up axis, so the trunk and
   head face where the pelvis faces. The per-frame twist (the gait's shoulder counter-rotation, glances) stays,
   centred on 0. Standing idles, sit and the combat stance keep head glances within 10° of the chest (`npc_look`
   unlimited), carried by the head (the neck takes 10 %), so the neck stays within a few degrees of the trunk. Applies
   to the idles, talk, NPC idles, gaits, crouch, sit and the combat stance; attacks, aiming and reactions keep their
   captured torso turn.
2. **Trunk.** The average hips→neck lean is brought into a band with one constant rotation about the hips, in the
   character's frame. The legs keep their world motion, so the feet stay put.
3. **Neck.** It stays within a few degrees of the trunk line, with no sideways lean.
4. **Head.** Average roll is levelled and average gaze kept in a band.
5. **Knees.** Standing idles are raised until the straighter leg is at about 4°. The foot lock re-plants the feet
   with leg IK.

Bands: idle / talk / NPC idles 0–4° trunk; walk 2–5°; run 10–12°; sprint 12–14°; combat stance 2–8° (crouch and
fists kept); attacks capped at 14–18° with level heads; acrobatics, kneeling, picking up and lying keep their head
pitch.

**Rest take (avatar reference pose).** Unity poses an imported model that carries animation in the first frame of
its first take, and `CharacterBuilder.ConfigureAvatar` builds the animation avatar's T-pose (the humanoid muscle
reference) from that pose. That take used to be `aim_l`, whose torso is turned 26° against the pelvis while aiming, so
the avatar took the twisted chest as neutral and every clip arrived on the heroes with the trunk turned 22–24° left of
the pelvis (the "bent" heroes), although the clips themselves were square. The export now starts with a two-frame
`_rest` take holding the rig's rest pose (`cmu_retarget.REST_TAKE`; actions export in name order and `_` sorts first),
so the avatar is built from the true rest. `_rest` also appears as an unused clip. Trunk and head yaw of every clip,
on the hero prefabs and on the authoring rig: `EOA.EditorTools.ClipProbe.TwistReport` → `Captures/clip_twist.txt`;
in game, `SmokeTest.RunPosture` logs "twist vs pelvis" per shot.

The animation avatars' T-pose skeletons now equal the hero avatars' (trunk and arms). One consequence:
`HeroStance` used to pull the clavicles (Shoulder Down-Up / Front-Back) to the rig's bind pose, the A-pose with
raised clavicles. With the old, offset avatar this was nearly a no-op. With the true reference it swung both arms
15–23° across the body, so in gameplay, the menu and the designer the hands met in front (hands 0.03–0.27 m apart,
against 0.34–0.52 m in the clips). The clavicles are now left to the animation. Arm pose per stage (sampled, played
by the controller, pose round trip, `HeroStance` game / menu): `EOA.EditorTools.ArmProbe.Report` →
`Captures/arm_report.txt`.

Before → after per clip and style: `blender/anim/posture_report_<style>.json`. Contact sheet with the HEAD FBX
against the new FBX on the hero rigs: `blender/anim/previews/posture_fixed_sheet.png`
(`blender/anim/posture_sheet.py` + `tools/anim/posture_sheet_compose.py`). Re-export:

```
blender -b blender/out/kael_export.blend --python blender/anim/cmu_retarget.py -- male --export --meta
blender -b blender/out/lyra_export.blend --python blender/anim/cmu_retarget.py -- female --export --meta
```

Add `--no-posture` to compare against the raw retarget. Relaxed and loose finger poses now curl naturally (index
middle joint about 40° / 28°).

**Unity safety nets (no double correction)**

* **`MocapNeckFix`.** It now acts only when a neck, head or wrist muscle median is more than 0.3–0.45 from the
  rig's *rest-pose* muscles (computed from the bind pose; Unity's muscle zero is not this rig's rest), or when a
  relaxed-hand clip arrives with straight fingers. The old version re-centred everything on muscle zero, which itself
  tilted and nodded the head about 20°. Each intervention is logged ("[mocap] safety net on ...").
* **`MocapPosture.Calibrate`.** It runs in `BuildAll`, measures on the hero rigs and solves body-pitch, thigh, neck
  and head offsets into `posture_fix.json` only for clips outside their bands. With the fixed source, everything is
  in band.
* **`HeroStance` posture guard (runtime).** Active in Locomotion / CombatLocomotion with no action playing, it
  removes only the averaged excess beyond the bands. **`HumanoidPolish`** raises the pelvis when standing still
  (out of combat, not crouched, up to 7 cm) so the straighter knee is at 3°. Its **foot lock** (2026-10-08) pins a foot
  where it touched down while its sole stays within 2.5 cm of the ground, eased in and out, and lets go when the foot
  lifts or the animated foot has moved 16 cm away (turning in place, teleports). Planted-foot slip in the posture
  capture: walk 0.10 / 0.16 → 0.00, run 0.38 / 0.89 → 0.25 / 0.51, sprint 1.79 → 0.61 / 0.89 m/s (Kael / Giva).
  Gait trunk bands since then: run 5–8°, sprint 9–12° (`MocapPosture.Specs`).

**Locomotion speed.** The gaits play at game speed ÷ authored speed. CMU clips use their clips_meta speeds
(1.9 / 5.0 / 7.4 m/s; time scales 1.16 / 1.04 / 1.03), which the gameplay capture confirms: walk foot slip 0.09–0.10
m/s. A trial at the speeds `ClipProbe` measures on the hero rigs (1.69 / 4.45 / 6.65 for Kael) tripled the walk slip
to 0.33 m/s and did not help the run. The probe reads about 0.91× of the true stride (planted-joint speed, not the
contact point), so measured Mixamo strides are divided by that bias, taken each build from the CMU gaits
(`MixamoImporter.StrideBias`).

The capture's run and sprint "slip" (0.7–1.1 m/s, unchanged by the time scale) comes from touch-down and toe-off frames
in the very short running stance, not from a speed mismatch.

**Crouch.** Toggle with C / Left Ctrl / left stick press (rebindable "Crouch"); jump or any action stands up.

* `crouch_idle` and `crouch_walk` are made at the source from the cleaned idle and walk: hips lowered 25 / 24 cm,
  leg IK keeps the feet on their paths with the knees tracking over the toes (85–93° knee bend), trunk inclined
  14–16°, level gaze.
* `CrouchLocomotion` blend tree on the `Crouch` bool, 0.22 s fades. The walk is time-scaled to `Hero.CrouchSpeed`
  1.5 m/s.
* The Hero's capsule shrinks to 64% height. Standing up waits for headroom (sphere cast). Sprinting is disabled
  while crouched.

**Responsiveness**

* `Speed` damping is 0.05 s (was 0.12). The animator parameter now trails the body by about 50–65 ms.
* A landing while moving no longer plays the full-body `land` action, and the base `Land` state hands over to the
  gait at once when `Speed` > 1.2.
* Pushing the stick during `land`, `pickup` or `interact` gestures cancels them (0.12 s fade).
* The CMU clips have no dead lead-in (≤ 1 frame; `wake` 0.12 s, cinematic). Mixamo one-shots are trimmed by the
  importer.

### 1.10 Measuring (`ClipProbe`, gameplay posture capture)

* `-executeMethod EOA.EditorTools.ClipProbe.Report`: per clip and style on the hero rigs, the trunk / neck lean, gaze,
  knee bend, finger curl, lead-in, strike time, stride speed and plant phase → `Captures/clip_probe.txt`.
* `-executeMethod EOA.EditorTools.SmokeTest.RunPosture`:
  * Kael, then Giva through the swap, standing, walking, running, sprinting, in the combat stance and talking, side
    and front views (`Captures/smoke/p_*.png`). The camera follows the hero every frame.
  * The run plays at 60 fps with `AlwaysAnimate`, and the final pose is averaged over each shot ("[posture]" lines):
    torso and neck lean, neck vs torso, knee bend, planted-foot slip.
  * Move start-up ("ramp") reports when body speed and the animator `Speed` reach 50% and 90%.
* `EOA.EditorTools.ClipProbe.TwistReport` (trunk and head yaw against the pelvis), `EOA.EditorTools.ArmProbe.Report`
  (arm abduction, flexion and hand distance per stage: sampled, controller, pose round trip, `HeroStance`) and
  `EOA.EditorTools.ClipProbe.GaitTrace` (sole joints per frame of walk / run / sprint, raw and corrected) write
  `Captures/clip_twist.txt`, `arm_report.txt` and `gait_trace.txt`. RunPosture also logs signed trunk pitch, head
  ahead of the shoulders (cm) and hand distance per shot.
* `RunPosture -storyDiag`: replays the story opening and logs the m1 quest stage, progress, radio dialogue, cinematic and
  voice-over state once a second after `tut_moved` is set ("[storydiag]"). The "wake" stage normally holds about 13 s
  while `dlg_m1_comms` plays its three voiced radio lines.

### 1.11 Quaternius Universal Animation Library (primary source, `MixamoImporter.Ual.cs`)

* **Source order per slot:** Mixamo (`incoming/mixamo/`) > UAL (`incoming/ual/`) > CMU. `MixamoImporter.Import` (run
  by `BuildAll`) copies `AnimationLibrary_Unity_Standard.fbx` and `UAL2_Standard.fbx` to
  `Assets/Art/Animations/UAL/UAL1.fbx` / `UAL2.fbx`, imports one clip per mapped slot (`UalMap`, listed in
  `docs/ANIMATION_CREDITS.md`) and writes per-hero clips `UAL/Generated/<male|female>/<clip>.anim`.
  `CharacterBuilder.LoadClips` gets them through `MixamoImporter.ClipsFor`; `clip_sources.json` records every slot
  (`"source": "ual"`, take, timing plan, posture before → after, foot-goal shift, gait speed).
* **Avatar (reference pose).** Humanoid, explicit bone map (UAL 1 Rigify `DEF-*`, UAL 2 UE names), Bake Axis
  Conversion on. The T-pose is built exactly like the heroes': the rig's own rest (the `A_TPose` take comes first, so it
  is Unity's default pose) with arms aimed straight out and legs straight down (largest turn 4°). Rest maps to rest, the
  limbs share the canonical T-pose. Copying the hero's bone directions instead (tried first) carried UAL's different
  pelvis and clavicle segments over and pushed the shoulders back (head 14 cm ahead of the shoulders).
* **Orientation.** UAL's root does not face the body: the clips are oriented by the body ("Body Orientation"), so the
  heroes face where they move.
* **Timing.** Attacks and abilities are re-timed so the detected strike lands on the tuned hit time; fit / trim / loop
  as for Mixamo (`Plan`).
* **Posture** (per hero, solved on the hero rig by `MocapPosture.Solve` and baked into the generated clip): trunk lean
  into its band (body pitch, thighs keeping their swing), standing knees straightened (thighs bring the feet back under
  the body, feet kept flat), arms brought to the sides in idle / walk (Arm Down-Up), neck in line, gaze level, head
  squared to the pelvis in the standing clips, run / sprint shoulder twist ×0.6. The foot IK goal curves are moved with
  the corrected feet (`SyncFootGoals`), so the locomotion foot IK neither undoes the straight knees nor drags the feet
  with a pitched body.
* **Gaits (not shipped).** The UAL walks are strolls (1.05 m/s against the heroes' 2.2 m/s: 0.75 m/s foot slip), and
  the jog / sprint plant only the forefoot while leaning 24° / 37°: brought upright on the heroes their planted-foot
  slip measured 2.7 / 3.3 m/s against CMU's 0.3–0.9 / 1.5–1.8. `UalMap` leaves walk, run and sprint on CMU; the gait
  support below stays for a later pass. Authored ground speed of each take on the UAL mannequin (walk 1.06, jog 5.90, sprint 8.90 m/s, measured
  from foot contact in Blender; the in-editor stride probes misread the short forefoot stances), scaled by the hero's
  human scale; `Gaits` sets thresholds and time scales from it.

## 2. Robot procedural animation

Robots have no skinned meshes or Mecanim clips. The FBX parts are rigid children of a 20-transform skeleton:

```
root, hips, spine, chest, neck, head,
clavicle_L/R, upperarm_L/R, forearm_L/R, hand_L/R,
thigh_L/R, shin_L/R, foot_L/R
```

The contract is in `Assets/Scripts/Enemies/ROBOT_PARTS.md`. Animation is computed every frame in C#.

### `RobotAnimator` (`Assets/Scripts/Enemies/RobotAnimator.cs`)

A port of the prototype's layered `Animator.ts`, without the airborne, look, aim and lean layers that robots never
use.

* **Pose representation.**
  * Per-bone Euler angles in degrees in the prototype's convention (three.js XYZ, right-handed, facing +Z with the
    left side on +X), plus a hips offset at the 1.8 m reference scale.
  * Converted to Unity by mirroring X: quaternion (x, -y, -z, w), offset (-x, y, z). This keeps clip numbers
    identical to the prototype so they can be copied verbatim.
* **Pose specs.** Written as compact strings, for example `"hipsPos:0,-0.06,0 spine:10,0,0 upperarm_S:-20,-10,6"`.
  A `_S` key expands to `_L` as written and to `_R` mirrored.
* **Clip types.**
  * `RobotKeyClip`: keyframes with Catmull-Rom interpolation and timed events.
  * `RobotFnClip`: a function of normalised phase, used for gaits.
* **Layers.**
  * Locomotion: blended idle, walk, run and sprint by ground speed and stride length, blended toward the combat
    idle by a 0..1 weight.
  * One-shot actions: cross-faded in and out, with event callbacks and an end callback.
  * Full-body state clip: for example `death`, overriding locomotion.
  * A global time scale for hitstop.
* **Applying the pose.** `RobotRig.Tick` applies the local rotations relative to each bone's rest pose and the hips
  offset scaled by the robot's height.

### Clip library (`RobotClips.cs`)

Numbers are verbatim from the prototype's `EnemyAnims.ts` and `Anims.ts`.

| Kind | Clips | Events |
|---|---|---|
| Sentinel (also Warden and BOLT) | `stance` L, `slam` 1.5 s, `sweep` 1.1 s, `stagger` 1.3 s, `death` 1.1 s | `telegraph`, `hit_start`, `impact`, `hit_end` |
| Guardian | Slower versions of the above (`slam` 2.2 s, `sweep` 1.6 s), plus `roar` 2.4 s, `laser` 3.4 s and `exposed` 3.8 s (kneeling with the core open) | adds `laser_on`, `laser_off`, `roar` |
| Stalker | Crouched `stance` L, `slash`, `stagger`, `death` | `telegraph`, `hit_start`, `hit_end` |

* **Locomotion styles.** `Robot` (walk stride 1.6 m) for the bipeds, and `Heavy` (walk stride 1.9 m, heavier gait)
  for the Guardian. Run stride is 3.4 m and sprint 4.6 m.
* **Idle.** An 8 s weight-shifting loop.
* **Enemy events.** Enemies drive their attack windows from these events, for example `Sentinel.OnAttackEvent`.
  `telegraph` raises `RobotRig.Telegraph`, which brightens the shared glow material up to 2.6× (glow intensity ×
  (1 + 1.6 × telegraph)).

### Other robot motion

| Robot | Motion |
|---|---|
| Drone | No skeleton clips. `Drone.cs` spins the four rotors, tilts and bobs the body, spins it on stagger, and plays a spinning fall on death. |
| Stalker | Phasing fades opacity through a transparent variant of the robot material (`robot_metal_TransparentVariant`). |
| All robots | Hit flash adds an emission boost (`RobotRig.HitFlash`). On death the visual sinks below the floor after the death clip. |
| BOLT | Offline: slumped in the sentinel `stagger` pose, because no robot `sit` clip exists. Repaired: walks a slow 3 m perimeter loop around its camp spot (`Npc.Tick`). |

## 3. Facial animation

Runs in `CharacterModel.LateUpdate` on the blendshapes exported by the Blender pipeline (see `CHARACTER_BIBLE.md` §4).

| Channel | Behaviour |
|---|---|
| Blink | `x_blink_L` and `x_blink_R`. Automatic every 2.2–5.5 s (random), 0.16 s per blink (close then open). `SetExpression("blink", w)` can force it. |
| Talk | `x_mouthOpen` flaps (sine at 11 rad/s × Perlin variation) while `Talk` > 0. `GameManager.SetSpeaker` sets `Talk = 1` on the hero, NPC or cinematic echo whose speaker id matches the line on screen (`DialogueLineShown`) and clears it afterwards. Without recorded voice-over, the flap is not lip-synced. |
| Expressions | `x_smile`, `x_frown`, `x_browsUp`, `x_browsDown`, `x_squint` are applied from `SetExpression(name, 0..1)`. No game code calls it yet, so these shapes are currently unused. |
| Customisation | `m_*_incr` / `m_*_decr` shapes are set by the appearance (static, not animated). |

## 4. Status

| Item | State |
|---|---|
| 42 humanoid clips per style, exported and imported | Done (a batch setup on 2026-10-03 logged "controller Male: 42 clips", "controller Female: 42 clips") |
| Animator controllers and character prefabs | Built by the setup (7 prefabs) |
| Robot procedural animator and clips | Implemented |
| Clips in actual play | Not yet verified in a recorded Unity play session |
| Staged cinematics (camera shots, actor staging) | Scripts for all five cinematics exist at the final check; not yet play-verified |
