"""Pose test with the game's real clips at their most extreme frames (clay or full materials).

  blender -b <file.blend> --python pose_test.py -- <tag> [--clips run,sprint,...] [--per 2] [--clay]
          [--frames clip:frame,...] [--views q34,q34L] [--engine BLENDER_EEVEE] [--hide Hair_*]
Writes out/pose/<tag>/<clip>_<frame>_<view>.png and out/pose/<tag>_sheet.png (via system python sheet.py).
"""
import bpy, sys, os, math, importlib, subprocess, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
import numpy as np
from mathutils import Vector
import gv, look, poses, deform
for m in (gv, look, poses, deform):
    importlib.reload(m)

CLIPS = ["run", "sprint", "l_quick1", "l_quick2", "l_heavy", "l_ult", "l_echo", "dash", "climb", "kneel_work", "death", "sit",
         "jump", "hit", "phase_step", "k_heavy", "pickup", "stagger"]

a = gv.args()
tag = a[0]
rig = bpy.data.objects[gv.RIG]
poses.load()
clips = gv.opt(a, "--clips", ",".join(CLIPS)).split(",")
per = int(gv.opt(a, "--per", "1"))
views = gv.opt(a, "--views", "q34,q34L").split(",")
eng = gv.opt(a, "--engine", "BLENDER_EEVEE")
out_dir = os.path.join(gv.OUT, "pose", tag)
os.makedirs(out_dir, exist_ok=True)

meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig]
for o in meshes:
    if o.name.startswith("Hair_") or o.name.startswith("Facial_"):
        o.hide_render = True
if "--clay" in a:
    clay = bpy.data.materials.new("clay")
    clay.use_nodes = True
    b = clay.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.55, 0.55, 0.56, 1)
    b.inputs["Roughness"].default_value = 0.6
    for o in meshes:
        if o.name in ("Brows", "Lashes"):
            o.hide_render = True
            continue
        o.data.materials.clear()
        o.data.materials.append(clay)

if "--lookdev" in a:
    import lookdev, mpfb_build
    atl = json.load(open(os.path.join(gv.OUT, "tex", "atlases.json")))
    lookdev.apply_all(meshes, os.path.join(gv.OUT, "tex"), atl, lookdev.PROPOSED if "--proposed" in a else lookdev.GAME)
    if bpy.data.objects.get("Hair_waves"):
        ho = bpy.data.objects["Hair_waves"]
        ho.hide_render = False
        ho.data.materials.clear()
        ho.data.materials.append(lookdev.alpha_card("pv_hair", os.path.join(gv.OUT, "tex", "Hair_waves_Color.png"),
                                                    lookdev.GAME["hair"], cutoff=0.35))
    else:
        mpfb_build.attach_catalog(rig, "hair", "long_waves")
if "--frames" in a:
    picks = [(s.split(":")[0], int(s.split(":")[1]), 0, {}) for s in gv.opt(a, "--frames").split(",")]
else:
    picks = poses.extremes(rig, clips, per)
report = []
files = []
from mathutils import Quaternion


def curl_fingers(rig, deg):
    """Curl every finger (proximal -> distal) toward the palm by deg = (j1, j2, j3) degrees; the thumb at half."""
    pb_ = rig.pose.bones
    for side in ("Left", "Right"):
        bpy.context.view_layer.update()
        H = rig.matrix_world.to_3x3()
        hand = pb_[gv.P + side + "Hand"]
        d_h = (pb_[gv.P + side + "HandMiddle1"].head - hand.head).normalized()
        s_ = (pb_[gv.P + side + "HandIndex1"].head - pb_[gv.P + side + "HandPinky1"].head).normalized()
        n = d_h.cross(s_) if side == "Left" else s_.cross(d_h)
        n.normalize()
        for f in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
            for j in (1, 2, 3):
                bpy.context.view_layer.update()
                b = pb_.get(gv.P + side + "Hand" + f + str(j))
                if b is None:
                    continue
                fd = (b.tail - b.head).normalized()
                ax = fd.cross(n)
                if ax.length < 1e-4:
                    continue
                ax.normalize()
                ang = math.radians(deg[j - 1] * (0.45 if f == "Thumb" else 1.0))
                loc = b.matrix.to_3x3().normalized().inverted() @ ax
                b.rotation_mode = "QUATERNION"
                b.rotation_quaternion = b.rotation_quaternion @ Quaternion(loc, ang)
    bpy.context.view_layer.update()
    return n


CURL = [float(x) for x in gv.opt(a, "--curl").split(",")] if "--curl" in a else None
cdefs = json.load(open(os.path.join(gv.OUT, "correctives.json"))) if os.path.exists(os.path.join(gv.OUT, "correctives.json")) else []
use_corr = "--nocorr" not in a
for clip, fr, score, ang in picks:
    poses.pose(rig, clip, fr)
    if CURL:
        curl_fingers(rig, CURL)
    if cdefs:
        deform.drive_correctives(rig, meshes, cdefs, use_corr)
    dg = bpy.context.evaluated_depsgraph_get()
    body = bpy.data.objects.get("Body")
    ev = body.evaluated_get(dg)
    co = np.array([body.matrix_world @ v.co for v in ev.data.vertices])
    lo, hi = co.min(0), co.max(0)
    c = Vector(((lo + hi) / 2).tolist())
    ext = float(max(hi - lo))
    for v in views:
        yaw = {"q34": 35, "q34L": -35, "front": 0, "back": 180, "side": 90, "sideL": -90}[v]
        r = math.radians(yaw)
        dist = ext * 1.9 + 0.8
        cam = c + Vector((math.sin(r) * dist, -math.cos(r) * dist, 0.15 * ext))
        p = os.path.join(out_dir, f"{clip}_{fr}_{v}.png")
        look.shot(p, cam, c, 50, "clay" if "--clay" in a else "studio", eng, (640, 800), 24 if eng != "CYCLES" else 48,
                  height=1.73, center=(c.x, c.y, lo[2]))
        files.append(p)
    if "--hands" in a:
        pb_ = rig.pose.bones
        for side in ("Left", "Right"):
            hand = pb_[gv.P + side + "Hand"]
            d_h = (pb_[gv.P + side + "HandMiddle1"].head - hand.head).normalized()
            s_ = (pb_[gv.P + side + "HandIndex1"].head - pb_[gv.P + side + "HandPinky1"].head).normalized()
            n = d_h.cross(s_) if side == "Left" else s_.cross(d_h)
            n.normalize()
            hc = rig.matrix_world @ (hand.head + d_h * 0.07)
            for k2, vv in (("back", (-n + s_ * 0.5).normalized()), ("palm", (n * 0.8 - s_ * 0.6).normalized()),
                           ("side", (s_ * 0.9 - n * 0.3).normalized())):
                cam = hc + vv * 0.42 + Vector((0, 0, 0.02))
                p = os.path.join(out_dir, f"{clip}_{fr}_{side}Hand_{k2}.png")
                look.shot(p, cam, hc, 50, "studio", eng, (520, 520), 24 if eng != "CYCLES" else 48,
                          height=1.73, center=(hc.x, hc.y, lo[2]), floor=False)
                files.append(p)
    if "--joints" in a:
        ang2 = poses.bend_angles(rig)
        cand = [(v, k) for k, v in ang2.items() if k not in ("Spine1",)]
        cand.sort(reverse=True)
        for v_, j in cand[:int(gv.opt(a, "--joints"))]:
            pb = rig.pose.bones[gv.P + j]
            par = pb.parent
            jc = rig.matrix_world @ pb.head
            d1 = (pb.tail - pb.head).normalized()
            d0 = (par.tail - par.head).normalized()
            n = d0.cross(d1)
            if n.length < 1e-3:
                n = Vector((1, 0, 0))
            n.normalize()
            # view the crease side-on, from the side facing away from the body centre
            if (jc - c).dot(n) < 0:
                n = -n
            for k2, vv in (("a", n), ("b", (n * 0.6 + (d0 - d1).normalized() * 0.8).normalized())):
                cam = jc + vv * 0.62 + Vector((0, 0, 0.04))
                p = os.path.join(out_dir, f"{clip}_{fr}_{j}_{k2}.png")
                look.shot(p, cam, jc, 50, "clay" if "--clay" in a else "studio", eng, (560, 560), 24 if eng != "CYCLES" else 48,
                          height=1.73, center=(jc.x, jc.y, lo[2]), floor=False)
                files.append(p)
    report.append({"clip": clip, "frame": fr, "score": round(score, 1), "angles": {k: round(x, 1) for k, x in ang.items()}})
json.dump(report, open(os.path.join(out_dir, "frames.json"), "w"), indent=1)
poses.rest(rig)
subprocess.run(["/opt/homebrew/bin/python3", os.path.join(HERE, "sheet.py"), os.path.join(gv.OUT, "pose", tag + "_sheet.png")] + files +
               ["--h", "400", "--cols", str(len(views) * 3)])
gv.log("pose test done", len(files))
