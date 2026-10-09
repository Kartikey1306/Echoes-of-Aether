"""Clip recipes for the CMU mocap retarget (blender/anim/cmu_retarget.py).

The data used in this project was obtained from mocap.cs.cmu.edu.
The database was created with funding from NSF EIA-0196217.

Every game clip names its CMU source as (trial, first_frame, last_frame[, per-segment options]) in the trial's own
frame numbering (0-based, 120 fps unless the subject was captured at 60 fps, see tools/anim/cmu.py).

Common options
  loop / speed      looping clip; with speed (m/s) the cycle is time-scaled so planted feet move exactly with the
                    character controller (foot lock + leg IK then removes any residual slide)
  loop_search       (min_s, max_s): search the best seamless loop window inside the given range
  root              XY handling: "loop" (subtract the average travel), "pin" (pelvis stays over the controller),
                    "center", "start", "damp"
  face              "travel" | "mean" | ("frame", f) | ("effector", joint, f): which direction becomes forward (+Z)
  yaw               extra facing correction in degrees
  warp              [(source_frame, output_seconds), ...] monotone retiming (attacks: trimmed anticipation,
                    impact pose on a fixed time, longer follow-through)
  rate / dur        uniform retiming
  events            [(name, seconds)] in output time (Unity AnimationEvents -> Hero.OnAnimEvent)
  ground            "feet" (soles on the floor), "body" (lowest body part on the floor), "source" (capture floor)
  zlock / zloop     vertical handling for airborne loops (jump / fall) and in-place ladder climbing
  feet              "lock" (default): planted-foot locking with two-bone leg IK; "none"
  fingers           procedural hand pose name (or (left, right), or [(t, pose), ...]); CMU hands have no fingers
  mirror            mirror left/right (aim_r / fire_r from a left-handed shooter)
"""

FIST = "fist"


def strike(src, warp, events, face, fingers=FIST, **kw):
    d = dict(src=[src], warp=warp, events=events, face=face, root="pin", fingers=fingers, feet="lock", smooth=0.5)
    d.update(kw)
    return d


BASE = {
    # ------------------------------------------------------------------ locomotion
    "idle": dict(src=[("82_08", 0, 640)], loop=True, loop_search=(3.5, 5.3), root="center", face="mean", fingers="relaxed",
                 notes="relaxed standing, small weight shifts"),
    "combat_idle": dict(src=[("15_13", 1300, 1560)], loop=True, loop_search=(1.0, 1.8), root="center", face="mean", fingers=FIST,
                        notes="boxing guard between combinations"),
    "walk": dict(src=[("07_12", 30, 137)], loop=True, speed=1.9, root="loop", face="travel", fingers="relaxed",
                 notes="brisk walk, one gait cycle (left heel strike to left heel strike)"),
    "run": dict(src=[("127_06", 67, 145)], loop=True, speed=5.0, root="loop", face="travel", fingers="loose",
                notes="run, one gait cycle"),
    "sprint": dict(src=[("143_01", 8, 52)], loop=True, speed=7.4, root="loop", face="travel", fingers="loose",
                   feet_opts=dict(v=3.0), notes="sprint, one gait cycle"),
    "jump": dict(src=[("91_39", 158, 200)], root="pin", face="mean", ground="source", zlock="first", feet="none",
                 fingers="loose", rate=0.85, notes="take-off to apex of a standing broad jump (arm swing), hips height held"),
    "fall": dict(src=[("91_39", 192, 214)], loop=True, pingpong=True, dur=0.8, root="pin", face="mean", ground="source",
                 zlock="stand", feet="none", fingers="loose", notes="apex-to-descent air pose, ping-pong looped"),
    "land": dict(src=[("91_39", 216, 262)], root="pin", face="mean", ground="feet", fingers="loose", rate=1.0,
                 notes="touch-down and absorb of the broad jump"),
    # ------------------------------------------------------------------ Kael (heavy vanguard): boxing + overhead smash
    "k_light1": strike(("15_13", 1560, 1652), [(1560, 0.0), (1584, 0.06), (1604, 0.16), (1628, 0.31), (1652, 0.52)],
                       [("hit_start", 0.12), ("combo", 0.22), ("hit_end", 0.26)], ("frame", 1560), yaw=-17, unturn=0.25,
                       notes="right cross"),
    "k_light2": strike(("14_01", 2866, 2975), [(2866, 0.0), (2888, 0.06), (2909, 0.17), (2945, 0.33), (2975, 0.54)],
                       [("hit_start", 0.13), ("combo", 0.23), ("hit_end", 0.27)], ("frame", 2866), yaw=-11, unturn=0.2,
                       notes="left hook"),
    "k_light3": strike(("14_02", 1752, 1852), [(1752, 0.0), (1775, 0.09), (1795, 0.21), (1816, 0.34), (1852, 0.62)],
                       [("hit_start", 0.17), ("combo", 0.30), ("hit_end", 0.34)], ("frame", 1752), yaw=-7, unturn=0.3,
                       notes="right uppercut (chain finisher)"),
    "k_heavy": strike(("79_01", 285, 400), [(285, 0.0), (329, 0.30), (354, 0.43), (375, 0.60), (400, 0.92)],
                      [("hit_start", 0.36), ("impact", 0.43), ("hit_end", 0.50)], ("effector", "rhand", 354),
                      notes="two-handed overhead smash (wood chop)"),
    "k_pulse": strike(("135_05", 505, 640), [(505, 0.0), (540, 0.14), (564, 0.30), (600, 0.55), (640, 0.85)],
                      [("pulse", 0.30)], "mean", fingers=FIST, notes="karate gedan-barai: deep stance, arm driven down"),
    "k_ult": strike(("91_39", 100, 300), [(100, 0.0), (163, 0.50), (192, 0.70), (220, 0.90), (300, 1.60)],
                    [("impact", 0.90)], "travel", ground="source", feet="none",
                    notes="crouch, leap and two-footed landing; impact on touch-down"),
    "dash": dict(src=[("143_01", 0, 44)], root="pin", face="travel", fingers="loose", rate=1.0, notes="one driving sprint stride"),
    # ------------------------------------------------------------------ Lyra (quick striker)
    "l_quick1": strike(("144_13", 805, 905), [(805, 0.0), (823, 0.04), (853, 0.13), (884, 0.27), (905, 0.38)],
                       [("hit_start", 0.10), ("combo", 0.17), ("hit_end", 0.21)], ("effector", "lhand", 853),
                       notes="left straight punch"),
    "l_quick2": strike(("144_09", 100, 250), [(100, 0.0), (125, 0.05), (172, 0.15), (235, 0.30), (250, 0.40)],
                       [("hit_start", 0.12), ("combo", 0.18), ("hit_end", 0.22)], ("effector", "ltoes", 172),
                       notes="left front snap kick"),
    "l_heavy": strike(("135_07", 380, 520), [(380, 0.0), (400, 0.07), (441, 0.32), (490, 0.55), (520, 0.78)],
                      [("hit_start", 0.20), ("impact", 0.32), ("hit_end", 0.46)], ("effector", "ltoes", 441), unturn=0.36,
                      notes="left roundhouse kick (mawashi-geri)"),
    "l_echo": dict(src=[("139_25", 250, 362)], warp=[(250, 0.0), (290, 0.16), (316, 0.26), (340, 0.45), (362, 0.75)],
                   events=[("echo", 0.24)], root="pin", face="mean", fingers=[(0.0, "relaxed"), (0.18, ("spread", "relaxed"))],
                   notes="left arm sweeps out and points (directing gesture)"),
    "l_ult": strike(("88_06", 20, 130), [(20, 0.0), (55, 0.42), (71, 0.60), (88, 0.80), (130, 1.35)],
                    [("impact", 0.60)], "mean", fingers="loose", ground="source", feet="none",
                    notes="jump spin kick, impact at the kick"),
    "phase_step": dict(src=[("76_11", 55, 115)], root="pin", face="mean", fingers="loose", dur=0.30,
                       notes="one quick step back"),
    # ------------------------------------------------------------------ ranged (upper body layer)
    "aim_l": dict(src=[("79_96", 226, 296)], loop=True, loop_search=(0.7, 1.15), root="center", face=("effector", "lhand", 260),
                  fingers=("spread", "relaxed"), notes="arm extended, aiming (left-handed shooter)"),
    "fire_l": dict(src=[("79_96", 288, 310)], root="center", face=("effector", "lhand", 260), fingers=("spread", "relaxed"), dur=0.30,
                   events=[("fire", 0.02)], notes="shot: arm kick and settle"),
    "aim_r": dict(src=[("79_96", 226, 296)], mirror=True, loop=True, loop_search=(0.7, 1.15), root="center", face=("effector", "rhand", 260),
                  fingers=("relaxed", "spread"), notes="mirrored aim"),
    "fire_r": dict(src=[("79_96", 288, 310)], mirror=True, root="center", face=("effector", "rhand", 260), fingers=("relaxed", "spread"), dur=0.30,
                   events=[("fire", 0.02)], notes="mirrored shot"),
    # ------------------------------------------------------------------ reactions
    "hit": dict(src=[("76_03", 205, 265)], root="pin", face="mean", fingers="loose", dur=0.33, notes="flinch, arms up"),
    "stagger": dict(src=[("76_03", 820, 980)], root="pin", face="mean", fingers="loose", dur=0.85,
                    notes="knocked low and recovering"),
    "death": dict(src=[("90_18", 52, 200)], root="start", face=("frame", 52), fingers="loose", ground="body", feet="none",
                  hold_end=0.25, notes="legs go, falls flat on the back"),
    # ------------------------------------------------------------------ interaction and traversal
    "interact": dict(src=[("144_24", 60, 262)], root="center", face="mean", fingers=[(0.0, "relaxed"), (0.25, ("relaxed", "point")), (0.6, "relaxed")],
                     rate=2.4, events=[("use", 0.36)], notes="reach out and press"),
    "pickup": dict(src=[("137_27", 640, 820)], root="center", face="mean", fingers=[(0.0, "relaxed"), (0.3, "grip")],
                   rate=2.0, events=[("use", 0.35)], notes="squat and grab from the floor"),
    "climb": dict(src=[("13_33", 300, 760)], loop=True, loop_search=(0.9, 1.6), root="center", face="mean", fingers="grip",
                  ground="source", zloop=True, feet="none", notes="ladder climb, vertical travel removed"),
    # ------------------------------------------------------------------ NPC and cinematic
    "talk": dict(src=[("18_08", 0, 2085)], loop=True, loop_search=(3.0, 5.0), root="center", face="mean", fingers="loose",
                 notes="conversation with explaining hand gestures"),
    "npc_crossed": dict(src=[("79_68", 689, 979)], loop=True, loop_search=(3.0, 4.6), root="center", face="mean", fingers="relaxed",
                        notes="arms folded (cold, hugging the arms)"),
    "npc_hips": dict(src=[("137_28", 2150, 2700)], loop=True, loop_search=(2.8, 4.4), root="center", face="mean", fingers="relaxed",
                     notes="hands on hips"),
    "npc_work": dict(src=[("79_85", 120, 700)], loop=True, loop_search=(1.6, 3.0), root="center", face="mean", fingers="loose",
                     notes="typing / working with the hands in front"),
    "npc_look": dict(src=[("137_28", 900, 2100)], loop=True, loop_search=(5.0, 8.0), root="center", face="mean", fingers="relaxed",
                     notes="waiting, looking around"),
    "npc_react": dict(src=[("79_73", 640, 760)], root="center", face="mean", fingers="spread", rate=1.4, notes="startled"),
    "wave": dict(src=[("141_16", 0, 230)], root="center", face="mean", fingers=("relaxed", "open"), rate=1.2, notes="wave hello"),
    "sit": dict(src=[("13_04", 457, 900)], loop=True, loop_search=(2.5, 3.6), root="center", face="mean", fingers="relaxed",
                notes="seated on a stool, chin on hand"),
    "kneel_work": dict(src=[("23_03", 225, 495)], loop=True, loop_search=(1.4, 2.2), root="center", face="mean", fingers="loose",
                       ground="body", notes="kneeling, hands busy in front"),
    "lie": dict(src=[("140_08", 0, 280)], loop=True, loop_search=(1.0, 2.0), root="center", face="mean", fingers="loose",
                ground="body", feet="none", notes="lying on the back, breathing"),
    "wake": dict(src=[("140_08", 120, 700)], root="start", face="mean", fingers="loose", ground="body", feet="none", rate=1.4,
                 notes="gets up from lying on the back"),
}

# Female style (Lyra and the female NPCs): female performers where the database has them.
FEMALE = {
    "idle": dict(src=[("113_21", 0, 1366)], loop=True, loop_search=(4.0, 6.0), root="center", face="mean", fingers="relaxed",
                 notes="standing still (female performer)"),
}


def recipes(style):
    out = {k: dict(v) for k, v in BASE.items()}
    if style == "female":
        for k, v in FEMALE.items():
            out[k] = dict(v)
    # Crouch stance (procedural, from this style's cleaned idle and walk): hips lowered with leg IK keeping the feet,
    # trunk leaning into the crouch (posture.py bands), slower walk cycle for the crouched move speed.
    out["crouch_idle"] = dict(out["idle"], crouch=0.25, notes="crouch idle: the standing idle lowered 25 cm (knees bent by IK, tracking over the toes)")
    out["crouch_walk"] = dict(out["walk"], speed=1.3, crouch=0.24, notes="crouch walk: the walk cycle at 1.3 m/s, hips 24 cm lower")
    return out
