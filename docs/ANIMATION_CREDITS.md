# Echoes of Aether — Animation Credits (motion capture)

Status date: 2026-10-08.

**Since 2026-10-08 the Quaternius Universal Animation Library (UAL 1 and 2, CC0) is the primary source**: 22 clip
slots per style come from it (section "Quaternius Universal Animation Library" at the end). The remaining slots
still use the CMU clips described below; Mixamo files, when dropped in `incoming/mixamo/`, override both.

All 42 humanoid clips in `Assets/Art/Animations/Anim_Male.fbx` and `Anim_Female.fbx` are built from the
**CMU Graphics Lab Motion Capture Database** (http://mocap.cs.cmu.edu). No other motion capture source and no
AI-generated animation was used in them. The only non-captured motion is the finger posing (the CMU skeleton has no finger
joints), which the pipeline sets from a small set of hand-written poses (relaxed, fist, grip, open, point, spread).

## Credit line (required)

> The data used in this project was obtained from mocap.cs.cmu.edu.
> The database was created with funding from NSF EIA-0196217.

Place this line in the game credits and keep it in the documentation.

## Licence terms (as published by the CMU Graphics Lab)

* The data is free to use for any purpose, including in commercially sold products (the game).
* The raw motion data may **not** be resold, alone or as part of a motion library.
* Credit the database with the line above.

What this project does to comply:

* The raw ASF/AMC downloads, the BVH conversions and the sampling caches stay out of git
  (`blender/anim/.gitignore`) and are re-downloaded on demand with `python3 tools/anim/cmu.py fetch-all`.
* Only retargeted, edited and baked clips are shipped (inside the two FBX files), never the raw files.

## Sources

Original Acclaim ASF/AMC files from `http://mocap.cs.cmu.edu/subjects/<subject>/<trial>.amc` (retrieved 2026-10-03),
converted to BVH by `tools/anim/cmu.py` (verified identical to the ASF/AMC kinematics to 1e-14). Capture rate is
120 fps, except subjects 79 and 88 (60 fps). Frame numbers below are 0-based frames of the original trial.

### Clips (both styles unless noted)

| Clip | CMU trial (subject — trial description) | Source frames | Result (male / female) | Edits |
|---|---|---|---|---|
| `idle` (male) | 82_08 (jumping; pushing; emotional walks — "stand still; casual walk forward") | 8–640 | 5.27 s loop | best loop window found automatically; pelvis centred; feet locked |
| `idle` (female) | 113_21 (female performer — "Standing Still") | 516–1036 | 4.33 s loop | as above |
| `combat_idle` | 15_13 (everyday behaviours — "boxing") | 1348–1484 | 1.13 s loop | boxing guard between combinations; fists |
| `walk` | 07_12 (walk — "brisk walk") | 30–137 (one gait cycle) | 1.03 / 0.87 s loop, 1.9 m/s | travel removed; time-scaled so planted feet move exactly at 1.9 m/s; foot plant + leg IK |
| `run` | 127_06 (action adventure — "Run") | 67–145 (one cycle) | 0.60 / 0.50 s loop, 5.0 m/s | as walk |
| `sprint` | 143_01 (general subject — "Run", full sprint) | 8–52 (one cycle) | 0.37 / 0.30 s loop, 7.4 m/s | as walk |
| `jump` | 91_39 (walks and turns — "JumpForward") | 158–200 | 0.40 s | take-off to apex; hips height held (the controller does the rising); slowed ×0.85 |
| `fall` | 91_39 | 192–214 | 0.80 s loop | apex-to-descent air pose, eased ping-pong loop, hips height held |
| `land` | 91_39 | 216–262 | 0.40 s | touch-down and absorb |
| `k_light1` | 15_13 ("boxing") | 1560–1652 | 0.53 s | right cross; anticipation trimmed, full extension at 0.16 s; follow-through un-turned to the start facing |
| `k_light2` | 14_01 (everyday behaviours — "boxing") | 2866–2975 | 0.53 s | left hook; contact at 0.17 s; body rotation after the hook un-turned |
| `k_light3` | 14_02 ("boxing") | 1752–1852 | 0.63 s | right uppercut (chain finisher); contact at 0.21 s |
| `k_heavy` | 79_01 (actor everyday activities — "chopping wood", 60 fps) | 285–400 | 0.93 s | two-handed overhead smash; hands reach the bottom at 0.43 s |
| `k_pulse` | 135_05 (martial arts — "Gedanbarai") | 505–640 | 0.87 s | deep stance, arm driven down at 0.30 s |
| `k_ult` | 91_39 ("JumpForward") | 100–300 | 1.60 s | crouch, leap and two-footed landing; vertical motion kept, landing at 0.90 s |
| `dash` | 143_01 ("Run") | 0–44 | 0.37 s | one driving sprint stride, pelvis pinned |
| `l_quick1` | 144_13 (punching female — "Left_Punch_Sequence001") | 805–905 | 0.37 s | left straight punch; retimed ×2.7 faster around the strike, extension at 0.13 s |
| `l_quick2` | 144_09 (punching female — "Left_Front_Kicking") | 100–250 | 0.40 s | left front snap kick, extension at 0.15 s |
| `l_heavy` | 135_07 (martial arts — "Mawashigeri") | 380–520 | 0.77 s | left roundhouse kick, contact at 0.32 s; follow-through spin (142°) un-turned |
| `l_echo` | 139_25 (action walks — "Giving Directions") | 250–362 | 0.73 s | arm sweeps out and points at 0.26 s; left hand opens |
| `l_ult` | 88_06 (acrobatics — "jump and spin kick", 60 fps) | 20–130 | 1.33 s | jump spin kick, kick at 0.60 s; vertical motion kept |
| `phase_step` | 76_11 (avoidance — "quick large steps backwards") | 55–115 | 0.30 s | one quick step back |
| `aim_l` | 79_96 (actor everyday activities — "shooting a gun", 60 fps) | 248–290 | 0.70 s loop | arm extended, faces along the aiming arm; aiming hand open |
| `fire_l` | 79_96 | 288–310 | 0.30 s | arm kick and settle, starts from the aim pose |
| `aim_r`, `fire_r` | 79_96 | as `aim_l` / `fire_l` | as above | mirrored left/right |
| `hit` | 76_03 (avoidance — "avoid attacker") | 205–265 | 0.33 s | flinch with arms up |
| `stagger` | 76_03 | 820–980 | 0.87 s | knocked low and recovering |
| `death` | 90_18 (acrobatics — "RugPullFall") | 52–200 | 1.50 s | legs go, falls flat on the back; last pose held 0.25 s |
| `interact` | 144_24 (punching female — "Reach_Right") | 60–262 | 0.70 s | reach out and press (index finger points); ×2.4 faster |
| `pickup` | 137_27 (stylized motions — "Normal Pick Up") | 640–820 | 0.73 s | squat and grab from the floor; ×2 faster |
| `climb` | 13_33 (everyday behaviours — "climb ladder") | 528–636 | 0.90 s loop | vertical travel removed (in place), grip hands |
| `talk` | 18_08 (interaction — "conversation - explain with hand gestures", subject A) | 504–888 | 3.20 s loop | explaining gestures |
| `npc_crossed` | 79_68 (actor everyday activities — "cold", 60 fps) | 719–899 | 3.00 s loop | arms folded, hugging the arms |
| `npc_hips` | 137_28 (stylized motions — "Normal Wait") | 2298–2682 | 3.20 s loop | hands on hips |
| `npc_work` | 79_85 ("typing on a laptop", 60 fps) | 540–636 | 1.60 s loop | hands busy in front (console work) |
| `npc_look` | 137_28 ("Normal Wait") | 968–1652 | 5.70 s loop | waiting, looking around, weight shifts |
| `npc_react` | 79_73 ("scared", 60 fps) | 640–760 | 1.43 s | startle and settle; ×1.4 faster |
| `wave` | 141_16 (general subject — "Wave Hello") | 0–230 | 1.60 s | right-hand wave, open hand; ×1.2 faster |
| `sit` | 13_04 ("sit on stepstool, chin in hand") | 545–853 | 2.57 s loop | seated idle (seat height about 0.45 m) |
| `kneel_work` | 23_03 (interaction — "B kneels, comforts A", subject B) | 289–457 | 1.40 s loop | kneeling, hands busy in front |
| `lie` | 140_08 (getting up from ground — "Get Up From Ground Laying on Back") | 0–120 | 1.00 s loop | lying on the back, breathing |
| `wake` | 140_08 | 120–700 | 3.47 s | gets up from the `lie` pose; ×1.4 faster |
| `crouch_idle` (2026-10-06) | same source as `idle` (82_08 / 113_21) | as `idle` | 5.27 / 4.33 s loop | procedural crouch: hips lowered 25 cm, leg IK keeps the feet, knees over the toes |
| `crouch_walk` (2026-10-06) | same source as `walk` (07_12) | as `walk` | loop at 1.3 m/s | the walk cycle slowed to 1.3 m/s, hips 24 cm lower, leg IK |

32 trials from 21 subjects are used in total (raw download about 46 MB).

### Edits applied to every clip

1. **Retarget.** BVH imported with Blender's importer; the A-posed MPFB `mixamo_unity` rig is aligned bone by bone to
   the CMU T-pose, then world-space rotations are transferred. Hips placed from the CMU hip joints, scaled by the
   leg-length ratio. Male clips are baked on Kael's rig, female clips on Lyra's.
2. **Facing.** +Z forward in Unity: by travel direction (locomotion), by the striking hand or foot at contact
   (attacks), by the guard pose (Kael's chain) or by the mean body facing.
3. **In place.** Root XY removed (average travel for loops, pelvis pinned for attacks, centred for idles). Vertical
   motion kept where it is part of the move (landings, crouches, ultimate leaps, getting up). `jump`/`fall` hold
   the hips height because the character controller does the rising and falling.
4. **Timing.** Anti-aliased resampling to 30 fps. Locomotion time-scaled to the blend-tree speeds. Attacks retimed
   with monotone warps: anticipation trimmed, contact frame placed on a fixed time, follow-through kept.
5. **Cleanup.** Gaussian smoothing (0.5–0.7 frame; hands 1.4 frames), wrist bend limited to 60°, seamless loops
   (error distributed over the cycle; seam 0.00° / 0.00 cm after export), rolling-contact foot planting (the current
   heel, ball or toe pivot is pinned on the floor) with two-bone leg IK, soles grounded on the floor.
6. **Hands.** Procedural finger poses per clip: fists for strikes and the guard, grip for climbing and pickups, an
   open hand for the bolt (aim/fire, echo) and the wave. The relaxed and loose poses were re-curled on 2026-10-06
   (index middle joint 40° / 28°).
7. **Posture (2026-10-06, `blender/anim/posture.py`).** This is a cleanup of the capture subjects' posture and the
   retarget's calibration offsets; it does not change any motion source. Per clip:
   * spine, neck, head and wrists are re-centred on the rig's upright rest, with their motion kept;
   * the average trunk lean is rotated into a natural band at the hips, with the legs kept;
   * the neck is brought in line with the trunk;
   * head roll is levelled and gaze kept level;
   * standing knees are straightened.
   Before/after values are in `blender/anim/posture_report_<style>.json`.

### Event timing (`clips_meta.json`, seconds)

| Clip | Old (prototype) | New |
|---|---|---|
| `k_light1` | hit_start 0.12, combo 0.20, hit_end 0.25 (0.52 s) | 0.12, 0.22, 0.26 (0.533 s) |
| `k_light2` | 0.12, 0.21, 0.26 (0.54 s) | 0.13, 0.23, 0.27 (0.533 s) |
| `k_light3` | 0.16, 0.28, 0.32 (0.62 s) | 0.17, 0.30, 0.34 (0.633 s) |
| `k_heavy` | hit_start 0.36, impact 0.43, hit_end 0.50 (0.92 s) | unchanged (0.933 s) |
| `l_quick1` | 0.08, 0.16, 0.20 (0.38 s) | 0.10, 0.17, 0.21 (0.367 s) |
| `l_quick2` | 0.09, 0.17, 0.21 (0.40 s) | 0.12, 0.18, 0.22 (0.40 s) |
| `l_heavy` | hit_start 0.16, impact 0.32, hit_end 0.46 (0.78 s) | 0.20, 0.32, 0.46 (0.767 s) |
| `k_pulse` | pulse 0.30 (0.85 s) | pulse 0.30 (0.867 s) |
| `k_ult` | impact 0.90 (1.60 s) | impact 0.90 (1.60 s) |
| `l_echo` | echo 0.24 (0.75 s) | echo 0.24 (0.733 s) |
| `l_ult` | impact 0.60 (1.35 s) | impact 0.60 (1.333 s) |
| `fire_r`, `fire_l` | fire 0.02 (0.30 s) | fire 0.02 (0.30 s) |
| `interact` | use 0.30 (0.80 s) | use 0.36 (0.70 s) |
| `pickup` | use 0.25 (0.55 s) | use 0.35 (0.733 s) |

Each `hit_start` sits one or two frames before the contact pose (full extension of the fist or foot), `hit_end`
about 0.1 s after it, and `combo` between them so a buffered attack chains on the recovery.

## Reproducing

```
python3 tools/anim/cmu.py fetch-all                                   # downloads the 32 trials (about 46 MB)
blender -b blender/out/kael_export.blend --python blender/anim/cmu_retarget.py -- male   --meta --export
blender -b blender/out/lyra_export.blend --python blender/anim/cmu_retarget.py -- female --meta --export
blender -b --python tools/anim/verify_fbx.py                          # take names, lengths, loop seams, events
# previews: add --preview --frames all, then python3 tools/anim/previews.py --sheet --gif <style_clip,...>
```

Recipes (trial, frames and edits per clip) are in `blender/anim/clips_cmu.py`. Previews are in `blender/anim/previews/`.

## Quaternius Universal Animation Library (UAL 1 and 2)

Universal Animation Library and Universal Animation Library 2 ("Standard" editions) by Quaternius
(https://quaternius.com, CC0 1.0, no credit required; the game credits it as a courtesy). Professionally authored on
one game humanoid rig (UAL 1 uses Rigify `DEF-*` bone names, UAL 2 UE-style names). Files: `incoming/ual/` (not in git)
→ `Assets/Art/Animations/UAL/UAL1.fbx`, `UAL2.fbx` → per-hero clips `UAL/Generated/<male|female>/<clip>.anim`
(`MixamoImporter.Ual.cs`). Source per slot and every measurement: `Assets/Art/Animations/clip_sources.json`.

| Game clip | UAL take | Use |
|---|---|---|
| `idle` | UAL 1 `Idle_Loop` | loop; trunk, knees, neck and head squared to the posture bands |
| `jump`, `fall`, `land` | UAL 1 `Jump_Start`, `Jump_Loop`, `Jump_Land` | fitted to the tuned durations |
| `talk`, `sit` | UAL 1 `Idle_Talking_Loop`, `Sitting_Idle_Loop` | loops |
| `npc_crossed` | UAL 2 `Idle_FoldArms_Loop` | loop |
| `hit`, `death`, `interact`, `pickup` | UAL 1 `Hit_Chest`, `Death01`, `Interact`, `PickUp_Table` | fitted / lead-in trimmed |
| `k_light1`, `k_light2`, `k_light3` | UAL 1 `Punch_Jab`, `Punch_Cross`, UAL 2 `Melee_Hook` | strike re-timed onto the tuned hit time |
| `k_heavy`, `k_pulse` | UAL 1 `Sword_Attack`, `Spell_Simple_Shoot` | strike re-timed |
| `aim_r`, `fire_r` | UAL 1 `Pistol_Aim_Neutral`, `Pistol_Shoot` | upper-body layer |
| `l_quick1`, `l_quick2`, `l_heavy` | UAL 2 `Sword_Regular_A`, `Sword_Regular_B`, `Sword_Regular_C` | strike re-timed |
| `l_echo` | UAL 2 `OverhandThrow` | strike re-timed onto the echo event |

Still CMU (UAL has no suitable clip): `walk` (UAL's walks are strolls authored for 1.05 m/s; the heroes walk at
2.2 m/s and the feet slid 0.75 m/s), `run` and `sprint` (UAL's forefoot strides lean 24° / 37°; brought upright on the
heroes, the planted-foot slip rose from 0.3–0.9 to 2.7 m/s and 1.5–1.8 to 3.3 m/s, so they stay CMU for now),
`combat_idle` (no boxing-guard loop), `crouch_idle` / `crouch_walk` (UAL's is a
deep stealth squat with a 44° trunk), `dash` and `phase_step` (a full roll does not fit a 0.3 s dash), `stagger` (UAL's
knockback ends lying down), `wave`, `npc_look`, `npc_hips`, `npc_work`, `npc_react`, `kneel_work`, `lie`, `wake`,
`climb`, `k_ult`, `l_ult`, `aim_l`, `fire_l` (Giva fires from her left hand; UAL aims a pistol).

