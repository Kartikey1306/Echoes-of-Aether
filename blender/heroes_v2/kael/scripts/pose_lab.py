"""Pose tests with the game's real clips (Anim_Male.fbx) on the Kael v2 rig.

  blender -b <blend> --python pose_lab.py -- scan                       # extreme frames per clip -> logs/extremes.json
  blender -b <blend> --python pose_lab.py -- render <tag> [clip:frame,...|auto] [--hide a,b] [--close] [--noshapes]
Renders previews/pose/<tag>_<clip>_<frame>.png (+ a contact sheet) with twist bones and correctives driven like the
game. 'auto' uses the scanned extremes (run, sprint, attacks, dash, climb, kneel_work, death, sit ...).
"""
import bpy, sys, os, json, math, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
from mathutils import Vector
import posing
importlib.reload(posing)

a = K.args()
mode = a[0]
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE" and not o.name.startswith("Kael.0"))
src, acts = posing.load_anim()
PRE = K.PRE


def metrics(rig):
    P = rig.pose.bones
    m = {}

    def ang(b1, b2):
        d1 = (P[b1].tail - P[b1].head).normalized(); d2 = (P[b2].tail - P[b2].head).normalized()
        return math.degrees(d1.angle(d2))
    for s in ("Left", "Right"):
        m["elbow" + s] = ang(PRE + s + "Arm", PRE + s + "ForeArm")
        m["knee" + s] = ang(PRE + s + "UpLeg", PRE + s + "Leg")
        up = (P[PRE + "Spine2"].tail - P[PRE + "Spine2"].head).normalized()
        arm = (P[PRE + s + "Arm"].tail - P[PRE + s + "Arm"].head).normalized()
        m["raise" + s] = 180 - math.degrees(arm.angle(up))   # 0 = arm down along the body
        hip_up = (P[PRE + "Spine"].tail - P[PRE + "Hips"].head).normalized()
        thigh = (P[PRE + s + "UpLeg"].tail - P[PRE + s + "UpLeg"].head).normalized()
        m["hip" + s] = 180 - math.degrees(thigh.angle(hip_up))
        q = posing._rel(rig, PRE + s + "ForeArm", PRE + s + "Hand") @ posing._rel_rest(rig, PRE + s + "ForeArm", PRE + s + "Hand").inverted()
        tw = posing._twist_about(q, Vector((0, 1, 0)))
        m["wrist" + s] = math.degrees(2 * math.acos(min(1, abs(tw.w))))
        q = posing._rel_rest(rig, PRE + s + "Shoulder", PRE + s + "Arm").inverted() @ posing._rel(rig, PRE + s + "Shoulder", PRE + s + "Arm")
        tw = posing._twist_about(q, Vector((0, 1, 0)))
        m["armroll" + s] = math.degrees(2 * math.acos(min(1, abs(tw.w))))
    return m


if mode == "scan":
    out = {}
    for clip, act in sorted(acts.items()):
        f0, f1 = posing.clip_range(act)
        best = {}
        for f in range(f0, f1 + 1, 2):
            posing.apply_clip(rig, clip, f, src, acts)
            for k, v in metrics(rig).items():
                if k not in best or v > best[k][0]:
                    best[k] = (round(v, 1), f)
        out[clip] = {"range": [f0, f1], "max": best}
        K.log("SCAN", clip, f0, f1, {k: v for k, v in best.items() if k.endswith("Left") or k.endswith("Right")})
    json.dump(out, open(os.path.join(K.LOGS, "extremes.json"), "w"), indent=1)
    raise SystemExit(0)

# ------------------------------------------------------------------ render
tag = a[1]
spec = a[2] if len(a) > 2 else "auto"
hide = (K.opt(a, "--hide") or "")
hide = [h for h in hide.split(",") if h]
close = K.opt(a, "--close")
if spec == "auto":
    ex = json.load(open(os.path.join(K.LOGS, "extremes.json")))
    picks = []
    for clip, keys in (("run", ["kneeLeft", "elbowRight"]), ("sprint", ["kneeRight", "hipLeft"]), ("k_light1", ["elbowRight"]),
                       ("k_light2", ["raiseRight"]), ("k_light3", ["armrollRight"]), ("k_heavy", ["raiseRight", "hipLeft"]),
                       ("k_pulse", ["raiseLeft"]), ("k_ult", ["raiseRight"]), ("dash", ["kneeLeft"]), ("climb", ["raiseLeft", "hipRight"]),
                       ("kneel_work", ["kneeLeft", "elbowRight"]), ("death", ["hipLeft"]), ("sit", ["kneeRight"]),
                       ("pickup", ["kneeLeft"]), ("phase_step", ["kneeRight"]), ("hit", ["elbowLeft"])):
        if clip not in ex:
            continue
        for k in keys:
            f = ex[clip]["max"][k][1]
            if (clip, f) not in picks:
                picks.append((clip, f))
else:
    picks = [(s.split(":")[0], int(s.split(":")[1])) for s in spec.split(",")]
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig]
import preview_k2
if K.opt(a, "--mats"):
    preview_k2.setup_materials()
for o in meshes:
    if any(o.name.startswith(h) for h in hide) or (o.name.startswith("Hair_") and o.name != "Hair_curly") or o.name.startswith("Facial_"):
        o.hide_render = True
corr = []
man = os.path.join(K.LOGS, "correctives.json")
if os.path.exists(man) and not K.opt(a, "--noshapes"):
    corr = json.load(open(man))
out = []
for clip, f in picks:
    posing.apply_clip(rig, clip, f, src, acts)
    posing.drive_twist(rig)
    if corr:
        wts = posing.corrective_weights(rig, corr)
        posing.set_corrective_shapes(meshes, wts)
        K.log("CORR", clip, f, {k: round(v[0], 2) for k, v in wts.items() if v[0] > 0.01})
    bpy.context.view_layer.update()
    K.clear_preview()
    K.cycles(samples=24, res=(700, 900))
    K.world((0.03, 0.033, 0.04), 1.0)
    hips = rig.matrix_world @ rig.pose.bones[PRE + "Hips"].head
    K.floor((0.06, 0.065, 0.07), 0.6, z=0.0)
    c = Vector((hips.x, hips.y, max(0.6, hips.z)))
    K.rig_lights("portrait", c, 1.5)
    if K.opt(a, "--hand"):
        side = K.opt(a, "--hand")
        hb = rig.matrix_world @ rig.pose.bones[PRE + ("Right" if side == "R" else "Left") + "Hand"].head
        K.camera(hb + Vector((0.25, -0.45, 0.12)), hb, 60)
    elif close:
        K.camera(c + Vector((1.2, -1.6, 0.35)), c + Vector((0, 0, 0.1)), 50)
    else:
        K.camera(c + Vector((2.4, -3.2, 0.25)), c + Vector((0, 0, -0.05)), 45)
    out.append(K.render_to(os.path.join(K.PREVIEWS, "pose", f"{tag}_{clip}_{f}.png")))
K.contact_sheet(out, os.path.join(K.PREVIEWS, "pose", f"{tag}_sheet.png"), cols=4, width=420)
