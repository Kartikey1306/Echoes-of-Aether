"""Stage 2: deformation rig for Giva.

  blender -b out/giva_base.blend --python s2_rig.py [-- --nocorr]

* twist bones (LeftForeArmTwist, RightForeArmTwist, LeftArmTwist, RightArmTwist at 60 % of their parent)
* body weights: stray influences removed, joint zones (knees, elbows, wrists, ankles, shoulders, hips) smoothed,
  forearm/upper-arm twist split, max 4 influences, normalised
* corrective blend shapes (Delta-Mush targets at the joint angles the game's clips actually reach, converted to
  rest-space deltas), piecewise for elbows/knees/hips; definitions in out/correctives.json (Blender bone-local axes)
Saves out/giva_rig.blend.
"""
import bpy, sys, os, json, math, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
import numpy as np
import gv, deform
for m in (gv, deform):
    importlib.reload(m)
P = gv.P


def axis_label(ax):
    k = int(np.argmax(np.abs(ax)))
    return ("" if ax[k] >= 0 else "n") + "xyz"[k]


def main():
    a = gv.args()
    rig = bpy.data.objects[gv.RIG]
    body = bpy.data.objects["Body"]
    deform.add_twist_bones(rig)
    me = body.data
    X = gv.basis_co(body)
    tris = gv.tri_index(me)
    off, idx = gv.neighbours(me)
    names, W = gv.bone_weights(body)
    for n in deform.TWIST:
        if P + n in names:
            j = names.index(P + n)
            names.pop(j)
            W = np.delete(W, j, 1)
    gv.log("weights in", W.shape, "max infl", int((W > 0.01).sum(1).max()))
    W = deform.remove_strays(W, names, X, rig)
    ix = {n: i for i, n in enumerate(names)}
    mask = np.zeros(len(X), bool)
    for side in ("Left", "Right"):
        for pair, rad, ms in (((side + "UpLeg", side + "Leg"), 0.11, 0.92), ((side + "Arm", side + "ForeArm"), 0.08, 0.92),
                              ((side + "ForeArm", side + "Hand"), 0.035, 0.9), ((side + "Leg", side + "Foot"), 0.06, 0.9)):
            m, _ = deform.joint_mask(W, ix, X, rig, pair, rad, ms)
            mask |= m
        # shoulder: upper arm / clavicle / chest blend around the shoulder joint
        b = rig.data.bones[P + side + "Arm"]
        d = np.linalg.norm(X - np.array(b.head_local), axis=1)
        sh = (W[:, ix[P + side + "Arm"]] + W[:, ix[P + side + "Shoulder"]] + W[:, ix[P + "Spine2"]] > 0.9) & (d < 0.09)
        mask |= sh
        # hip: thigh / hips / buttock around the hip joint (not the groin midline)
        b = rig.data.bones[P + side + "UpLeg"]
        d = np.linalg.norm(X - np.array(b.head_local), axis=1)
        hp = (W[:, ix[P + side + "UpLeg"]] > 0.03) & (d < 0.13) & (np.abs(X[:, 0]) > 0.025)
        mask |= hp
    gv.log("smoothing", int(mask.sum()), "joint-zone vertices")
    W = deform.smooth_weights(W, off, idx, mask, iters=int(gv.opt(a, "--smooth", "6")), lam=0.5)
    W, names = deform.twist_split(W, names, X, rig)
    W = gv.limit_normalize(W, 4, 0.01)
    gv.write_weights(body, names, W)
    names, W = gv.bone_weights(body)
    gv.log("weights out", W.shape, "max infl", int((W > 0).sum(1).max()))
    # proxies: rigid to the head (eyes/teeth/tongue/brows/lashes already have MPFB head-area weights; limit them)
    for pn in ("Eyes", "Brows", "Lashes", "Teeth", "Tongue"):
        o = bpy.data.objects.get(pn)
        if o is None:
            continue
        nn, WW = gv.bone_weights(o)
        if WW.shape[1]:
            gv.write_weights(o, nn, gv.limit_normalize(WW, 4, 0.01))
    if "--nocorr" not in a:
        build_correctives(rig, body, X, tris, off, idx, names, W)
    gv.save(os.path.join(gv.OUT, "giva_rig.blend"))


# (bone, parent, swing-axis index, sign, [(deg, base_deg)])  angles from out/logs/swing_axes.json (all 42 clips)
PLAN = [("ForeArm", "Arm", 0, 1, [(60, None), (115, 60)]),
        ("Leg", "UpLeg", 0, 1, [(70, None), (140, 70)]),
        ("Arm", "Shoulder", 0, 1, [(80, None)]),
        ("Arm", "Shoulder", 1, 1, [(70, None)]),
        ("Arm", "Shoulder", 1, -1, [(45, None)]),
        ("UpLeg", None, 0, 1, [(65, None), (125, 65)]),     # deep hip flexion: CoR inflates the buttock -> 50 %
        ("UpLeg", None, 1, 1, [(60, None)]),
        ("Hand", "ForeArm", 0, 1, [(55, None)])]


def corrective_defs(rig):
    """Corrective definitions in the runtime's convention: world-space rest axes perpendicular to the bone direction."""
    from mathutils import Vector
    axes = json.load(open(os.path.join(gv.OUT, "logs", "swing_axes.json")))
    defs = []
    for side in ("Left", "Right"):
        for b, par, k, sign, steps in PLAN:
            bone = P + side + b
            parent = P + side + par if par else P + "Hips"
            child = deform.main_child(rig, bone)
            d = (rig.data.bones[child].head_local - rig.data.bones[bone].head_local).normalized()
            ax = Vector(axes[side + b][k]["axis"]) * sign
            ax = (ax - d * ax.dot(d)).normalized()
            al = rig.data.bones[bone].matrix_local.to_3x3().inverted() @ ax
            for deg, base in steps:
                defs.append({"shape": f"corr_{side}{b}_{axis_label(np.array(al))}_{deg}", "bone": bone, "parent": parent,
                             "child": child, "axis": [round(v, 5) for v in ax], "from": float(base or 0), "to": float(deg)})
    return defs


def strength(d):
    if "UpLeg" in d["bone"] and d["to"] > 100:
        return 0.5
    if "UpLeg" in d["bone"]:
        return 0.8
    return 1.0


def build_correctives(rig, body, X, tris, off, idx, names, W):
    defs = corrective_defs(rig)
    for d in defs:
        delta = deform.cor_corrective(rig, X, W, names, tris, d["bone"], d["axis"], d["to"], d["from"] or None)
        delta *= strength(d)
        d["maxDelta"] = round(float(np.linalg.norm(delta, axis=1).max()), 4)
        gv.add_shape(body, d["shape"], X + delta)
        # check: the runtime-equivalent angle at the authoring pose must equal "to"
        deform.pose_swing(rig, d["bone"], d["axis"], d["to"])
        chk = deform.swing_angle(rig, d["bone"], d["parent"], d["axis"], d["child"])
        deform.pose_single(rig, None, None, 0)
        gv.log("corrective", d["shape"], "max delta %.1f mm" % (d["maxDelta"] * 1000), "angle check %.2f" % chk)
    json.dump(defs, open(os.path.join(gv.OUT, "correctives.json"), "w"), indent=1)


main()
