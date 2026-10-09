"""Stage 6 - Kael v2 deformation: skin weights for every outfit piece (cloth smoothed from the body, rigid plates on
one bone or a fixed pair, articulated bracer segments ramped onto the twist bone), body-morph shapes for garments
(rigid parts translate), refit of the previous export's hair cards / facial hair onto the new head, and pose
corrective blend shapes baked from a volume-preserving reference (dual-quaternion skinning + corrective smooth)
against the game's linear blend skinning.

  blender -b blends/kael_s5_face.blend --python build_deform.py -- [--save] [--no-corr]
"""
import bpy, bmesh, sys, os, json, math, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
import garment as G, meshops, posing, gear
for m in (G, meshops, posing):
    importlib.reload(m)

PRE = K.PRE
a = K.args()
rig = bpy.data.objects["Kael"]
body = bpy.data.objects["Body"]
full = bpy.data.objects.get("BodyFull") or body
mh = bpy.data.objects["BodyMH"]
B = G.BodyInfo(rig, full, mh)
L, T = B.L, B.T
OBJ = {o.name: o for o in bpy.data.objects if o.type == "MESH"}


def ramp_weights(o, bone_a, bone_b, a_, b_, t0, t1, names=None):
    """Two-bone weights ramping from bone_a to bone_b along the segment a_->b_ (t0..t1)."""
    co = K.get_co(o)
    d = b_ - a_
    t = (co - a_) @ d / (d @ d)
    w = K.ss(t0, t1, t)
    nm = list(B.names)
    W = np.zeros((len(co), len(nm)))
    W[:, nm.index(PRE + bone_a)] = 1 - w
    W[:, nm.index(PRE + bone_b)] = w
    meshops.set_weights(o, nm, meshops.limit_normalize(W, 4, 0.01))


def parent_rig(o):
    o.parent = rig
    o.matrix_parent_inverse = rig.matrix_world.inverted()
    if not any(m.type == "ARMATURE" for m in o.modifiers):
        m = o.modifiers.new("Armature", "ARMATURE"); m.object = rig


def rigid_shapes(o, prefixes=("m_",)):
    """Body morphs for rigid parts: every connected piece translates by its mean bound delta (no deformation)."""
    co = K.get_co(o)
    I, Wt, D = B.bind(co)
    me = o.data
    # connected pieces
    parent = np.arange(len(co))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for e in me.edges:
        ra, rb = find(e.vertices[0]), find(e.vertices[1])
        if ra != rb:
            parent[ra] = rb
    comp = np.array([find(i) for i in range(len(co))])
    shapes = {}
    for n, sco in B.shapes.items():
        if not n.startswith(prefixes):
            continue
        d = ((sco - B.co)[I] * Wt[..., None]).sum(1)
        if np.abs(d).max() < 1e-5:
            continue
        out = np.zeros_like(d)
        for c in np.unique(comp):
            m = comp == c
            out[m] = d[m].mean(0)
        shapes[n] = co + out
    meshops.set_shapes(o, co, shapes)


# ============================================================================= outfit weights
t0 = __import__("time").time()
cloth = {"Top": dict(smooth_iters=8), "Jacket": dict(smooth_iters=10), "Pants": dict(smooth_iters=6),
         "ChestRig": dict(smooth_iters=12, limit_bones=["Hips", "Spine", "Spine1", "Spine2", "LeftShoulder", "RightShoulder", "Neck"]),
         "Belt": dict(smooth_iters=14, limit_bones=["Hips", "Spine"]),
         "Boots": dict(smooth_iters=4, limit_bones=["LeftFoot", "LeftToeBase", "LeftLeg", "RightFoot", "RightToeBase", "RightLeg"]),
         "Gloves": dict(smooth_iters=2)}
for n, kw in cloth.items():
    if n in OBJ:
        G.skin_from_body(OBJ[n], B, rig, **kw)
        parent_rig(OBJ[n])
# gloves: knuckle / back-of-hand plates ride the hand bone rigidly
g = OBJ.get("Gloves")
if g is not None and g.data.attributes.get("kplate"):
    kp = np.empty(len(g.data.vertices), np.float32); g.data.attributes["kplate"].data.foreach_get("value", kp)
    names, W = meshops.get_weights(g)
    co = K.get_co(g)
    for s, S in ((1, "Left"), (-1, "Right")):
        m = (kp > 0.5) & (np.sign(co[:, 0]) == s)
        W[m] = 0
        W[m, names.index(PRE + S + "Hand")] = 1
    meshops.set_weights(g, names, W)
# collar: lower edge on the chest, upper edge follows the neck
c = OBJ.get("Collar")
if c is not None:
    co = K.get_co(c)
    w = K.ss(1.56, 1.66, co[:, 2]) * 0.75
    nm = list(B.names)
    W = np.zeros((len(co), len(nm)))
    W[:, nm.index(PRE + "Spine2")] = 1 - w
    W[:, nm.index(PRE + "Neck")] = w
    meshops.set_weights(c, nm, W)
    parent_rig(c)
    G.transfer_shapes(c, B)
# rigid plates
for n, bone in (("ChestPlate", "Spine2"), ("KneePadL", "LeftLeg"), ("KneePadR", "RightLeg")):
    if n in OBJ:
        G.skin_from_body(OBJ[n], B, rig, rigid=bone)
        parent_rig(OBJ[n])
for s, S in (("L", "Left"), ("R", "Right")):
    if "Pauldron" + s in OBJ:
        G.skin_from_body(OBJ["Pauldron" + s], B, rig, blend=[(S + "Shoulder", 0.6), (S + "ArmTwist", 0.4)])
        parent_rig(OBJ["Pauldron" + s])
    if "PauldronLame" + s in OBJ:
        o = OBJ["PauldronLame" + s]
        ramp_weights(o, S + "ArmTwist", S + "Arm", L[S + "Arm"], L[S + "ForeArm"], 0.3, 0.5)
        names, W = meshops.get_weights(o)
        nm = list(B.names)
        Wf = np.zeros((len(W), len(nm)))
        for k, nn in enumerate(names):
            Wf[:, nm.index(nn)] = W[:, k]
        Wf[:, nm.index(PRE + S + "Shoulder")] += 0.15
        meshops.set_weights(o, nm, meshops.limit_normalize(Wf, 4, 0.01))
        parent_rig(o)
_iface = "Left" if "ForearmGuardL" in OBJ else "Right"


def _seg_dist(co, a_, b_):
    d = b_ - a_
    t = np.clip((co - a_) @ d / (d @ d), 0, 1)
    return np.linalg.norm(co - (a_ + t[:, None] * d), axis=1), (co - a_) @ d / (d @ d)


for n in ("ForearmGuardL", "ForearmGuardR", "Interface"):
    if n in OBJ:
        S_ = _iface if n == "Interface" else ("Left" if n.endswith("L") else "Right")
        o = OBJ[n]
        ramp_weights(o, S_ + "ForeArm", S_ + "ForeArmTwist", L[S_ + "ForeArm"], L[S_ + "Hand"], 0.42, 0.68)
        # the holo wrap continues past the elbow onto the upper arm: those parts ride the upper arm
        co = K.get_co(o)
        du, tu = _seg_dist(co, L[S_ + "Arm"], L[S_ + "ForeArm"])
        df, tf = _seg_dist(co, L[S_ + "ForeArm"], L[S_ + "Hand"])
        up = (du < df) & (tf < 0.02)
        if up.any():
            names, W = meshops.get_weights(o)
            nm = list(B.names)
            Wf = np.zeros((len(co), len(nm)))
            for k, nn in enumerate(names):
                Wf[:, nm.index(nn)] = W[:, k]
            Wf[up] = 0
            Wf[up, nm.index(PRE + S_ + "Arm")] = 1.0
            meshops.set_weights(o, nm, meshops.limit_normalize(Wf, 4, 0.01))
            K.log("HOLO upper-arm verts", n, int(up.sum()))
        parent_rig(o)
for n in ("ChestPlate", "PauldronL", "PauldronR", "PauldronLameL", "PauldronLameR", "KneePadL", "KneePadR", "ForearmGuardL", "ForearmGuardR", "Interface"):
    if n in OBJ:
        rigid_shapes(OBJ[n])
for n in ("Belt",):
    if n in OBJ:
        rigid_shapes(OBJ[n])
K.log("WEIGHTS outfit", round(__import__("time").time() - t0, 1), "s")

# ============================================================================= refit the previous hair cards / facial hair
old_fbx = os.path.join(K.BLENDS, "old_export", "Kael.fbx")
R = np.load(os.path.join(K.LOGS, "mh_old.npz"), allow_pickle=True)
old_co = R["co"]
new_co = K.get_co(mh)
before = set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=old_fbx, automatic_bone_orientation=False)
imported = [o for o in bpy.data.objects if o not in before]
old_tree = BVHTree.FromPolygons([Vector(p) for p in old_co], B.mh_faces)
from mathutils.interpolate import poly_3d_calc
disp = new_co - old_co
hair_objs = []
for o in imported:
    if o.type != "MESH" or not (o.name.startswith("Hair_") or o.name.startswith("Facial_")):
        continue
    nm = o.name.split(".")[0]
    w = np.array([o.matrix_world @ v.co for v in o.data.vertices])
    dd = np.zeros_like(w)
    for i, p in enumerate(w):
        loc, n_, fi, dist = old_tree.find_nearest(Vector(p), 0.5)
        f = B.mh_faces[fi]
        bw = poly_3d_calc([Vector(old_co[v]) for v in f], loc)
        dd[i] = (disp[f] * np.array(bw)[:, None]).sum(0)
    names, Wv = meshops.get_weights(o)
    o.shape_key_clear() if o.data.shape_keys else None
    mats = [m.name.split(".")[0] if m else nm for m in o.data.materials]
    o.parent = None
    o.matrix_world = Matrix.Identity(4)
    o.modifiers.clear()
    K.set_co(o, w + dd)
    o.name = o.data.name = nm
    if not names:
        names, Wv = [PRE + "Head"], np.ones((len(w), 1))
    nmB = list(B.names)
    Wf = np.zeros((len(w), len(nmB)))
    for k, n2 in enumerate(names):
        if n2 in nmB:
            Wf[:, nmB.index(n2)] = Wv[:, k]
    meshops.set_weights(o, nmB, meshops.limit_normalize(Wf, 4, 0.01))
    parent_rig(o)
    G.transfer_shapes(o, B, prefixes=("m_", "x_") if nm.startswith("Facial_") else ("m_",))
    o.data.materials.clear()
    o.data.materials.append(gear.get_mat(nm))
    o.data.polygons.foreach_set("material_index", np.zeros(len(o.data.polygons), np.int32))
    o.hide_render = True
    hair_objs.append(o.name)
for o in imported:
    if o.name not in hair_objs and o.name in bpy.data.objects:
        bpy.data.objects.remove(o, do_unlink=True)
# the concept face sculpt (face_sculpt.py, stored on BodyFull by the face stage) also moves the refitted facial hair
if full.data.attributes.get("k_sx") is not None:
    import face_sculpt as FS
    from mathutils.kdtree import KDTree
    fco = K.get_co(full)
    sd = np.stack([np.array([v.value for v in full.data.attributes[k].data]) for k in ("k_sx", "k_sy", "k_sz")], 1)
    kd = KDTree(len(fco))
    for i, c in enumerate(fco):
        kd.insert(c, i)
    kd.balance()
    for n in hair_objs:
        if n.startswith("Facial_"):
            FS.transfer(bpy.data.objects[n], kd, fco, sd)
for ac in list(bpy.data.actions):
    if ac.users == 0:
        bpy.data.actions.remove(ac)
# fit report: scalp relative to the head bone vs the committed export (catalog hair / eyewear reference)
hn = np.array(rig.matrix_world @ rig.data.bones[PRE + "Head"].head_local)
rel_new = new_co - hn
rel_old = old_co - R["head"]
eye_z = (L["LeftEye"][2] + L["RightEye"][2]) / 2 - hn[2]
dist = np.linalg.norm(rel_new - rel_old, axis=1)
scalp = (rel_old[:, 2] > eye_z + 0.035) & (np.linalg.norm(rel_old, axis=1) < 0.2)
ears = (np.abs(rel_old[:, 0]) > 0.06) & (np.abs(rel_old[:, 2] - eye_z) < 0.03) & (rel_old[:, 1] > 0.0) & (np.linalg.norm(rel_old, axis=1) < 0.2)
bridge = (np.abs(rel_old[:, 0]) < 0.012) & (np.abs(rel_old[:, 2] - eye_z) < 0.012) & (rel_old[:, 1] < -0.06) & (np.linalg.norm(rel_old, axis=1) < 0.2)
fit = {k: [round(float(dist[m].max() * 1000), 1), round(float(dist[m].mean() * 1000), 1)] for k, m in (("scalp_mm", scalp), ("ears_mm", ears), ("bridge_mm", bridge))}
fit["head_bone_offset_mm"] = [round(float(x * 1000), 1) for x in (hn - R["head"])]
K.log("REFIT hair", hair_objs, "FIT", fit)
json.dump(fit, open(os.path.join(K.LOGS, "head_fit.json"), "w"), indent=1)

# ============================================================================= teeth/tongue weight
for n, ratio in (("Teeth", 0.18),):
    if n in OBJ:
        import skin_hd
        skin_hd.decimate_with_shapes(OBJ[n], ratio)


# ============================================================================= correctives
def joint_axes():
    out = {}
    for s, S in ((1, "Left"), (-1, "Right")):
        dU = K.nrm(L[S + "ForeArm"] - L[S + "Arm"]); dF = K.nrm(L[S + "Hand"] - L[S + "ForeArm"])
        out["elbow" + S] = K.nrm(np.cross(dU, dF))
        out["knee" + S] = np.array((1.0, 0, 0))
        out["abduct" + S] = np.array((0, -s * 1.0, 0))
        out["flexarm" + S] = K.nrm(np.cross(dU, np.array((0, -1.0, 0))))
        out["hip" + S] = np.array((-1.0, 0, 0))
        wr, dors, fdir, mcp = gear.hand_frame(L, s)
        out["wristflex" + S] = K.nrm(np.cross(fdir, -dors))
    return out


AX = joint_axes()
CORR = []
for S in ("Left", "Right"):
    CORR += [
        dict(shape=f"corr_{S}ForeArm_x_125", bone=PRE + S + "ForeArm", parent=PRE + S + "Arm", axis=AX["elbow" + S], angle=125, frm=15, to=125,
             meshes=["Top", "Jacket", "Gloves"], zone=[S + "Arm", S + "ArmTwist", S + "ForeArm", S + "ForeArmTwist"], center=L[S + "ForeArm"]),
        dict(shape=f"corr_{S}Leg_x_130", bone=PRE + S + "Leg", parent=PRE + S + "UpLeg", axis=AX["knee" + S], angle=130, frm=15, to=130,
             meshes=["Pants", "Boots"], zone=[S + "UpLeg", S + "Leg"], center=L[S + "Leg"]),
        dict(shape=f"corr_{S}Arm_y_95", bone=PRE + S + "Arm", parent=PRE + "Spine2", axis=AX["abduct" + S], angle=95, frm=20, to=95,
             meshes=["Top", "Jacket", "ChestRig", "Collar"], zone=[S + "Shoulder", S + "Arm", S + "ArmTwist", "Spine2"], center=L[S + "Arm"]),
        dict(shape=f"corr_{S}Arm_x_90", bone=PRE + S + "Arm", parent=PRE + "Spine2", axis=AX["flexarm" + S], angle=90, frm=20, to=90,
             meshes=["Top", "Jacket", "ChestRig"], zone=[S + "Shoulder", S + "Arm", S + "ArmTwist", "Spine2"], center=L[S + "Arm"]),
        dict(shape=f"corr_{S}UpLeg_x_100", bone=PRE + S + "UpLeg", parent=PRE + "Hips", axis=AX["hip" + S], angle=100, frm=20, to=100,
             meshes=["Pants", "Top", "Jacket"], zone=["Hips", S + "UpLeg"], center=L[S + "UpLeg"]),
        dict(shape=f"corr_{S}Hand_x_60", bone=PRE + S + "Hand", parent=PRE + S + "ForeArm", axis=AX["wristflex" + S], angle=60, frm=10, to=60,
             meshes=["Gloves", "Top", "Jacket"], zone=[S + "ForeArm", S + "ForeArmTwist", S + "Hand"], center=L[S + "Hand"]),
        dict(shape=f"corr_{S}Hand_xn_60", bone=PRE + S + "Hand", parent=PRE + S + "ForeArm", axis=-AX["wristflex" + S], angle=60, frm=10, to=60,
             meshes=["Gloves", "Top", "Jacket"], zone=[S + "ForeArm", S + "ForeArmTwist", S + "Hand"], center=L[S + "Hand"]),
    ]


def pose_single(bone, axis, angle):
    posing.reset_pose(rig)
    pb = rig.pose.bones[bone]
    M = rig.matrix_world @ pb.matrix
    head = M.to_translation()
    R = Matrix.Rotation(math.radians(angle), 4, Vector(axis))
    pb.matrix = rig.matrix_world.inverted() @ (Matrix.Translation(head) @ R @ Matrix.Translation(-head) @ M)
    bpy.context.view_layer.update()
    posing.drive_twist(rig)


def eval_mesh(o, dqs, smooth):
    arm = next(m for m in o.modifiers if m.type == "ARMATURE")
    arm.use_deform_preserve_volume = dqs
    cs = None
    if smooth:
        cs = o.modifiers.new("k_cs", "CORRECTIVE_SMOOTH")
        cs.factor = 0.5
        cs.iterations = 10
        cs.scale = 1.0
        cs.smooth_type = "LENGTH_WEIGHTED"
        cs.use_pin_boundary = True
        cs.rest_source = "ORCO"
    bpy.context.view_layer.update()
    co = K.evaluated_co(o)
    if cs:
        o.modifiers.remove(cs)
    arm.use_deform_preserve_volume = False
    return co


def bake_corrective(c):
    pose_single(c["bone"], c["axis"], c["angle"])
    made = []
    for n in c["meshes"]:
        o = OBJ.get(n)
        if o is None:
            continue
        if o.data.shape_keys:
            for k in o.data.shape_keys.key_blocks:
                k.value = 0.0
        p_lbs = eval_mesh(o, False, False)
        p_ref = eval_mesh(o, True, True)
        names, W = meshops.get_weights(o)
        s = W.sum(1, keepdims=True)
        W = np.where(s > 0, W / np.maximum(s, 1e-9), 0)
        zi = [names.index(PRE + z) for z in c["zone"] if PRE + z in names]
        zone = W[:, zi].sum(1)
        rest = K.get_co(o) if not o.data.shape_keys else meshops.shape_arrays(o)[0]
        dist = np.linalg.norm(rest - c["center"], axis=1)
        mask = K.ss(0.05, 0.35, zone) * (1 - K.ss(0.16, 0.26, dist))
        delta = (p_ref - p_lbs) * mask[:, None]
        if np.abs(delta).max() < 0.0008:
            continue
        Ms = meshops.pose_matrices(rig, names)
        S_ = meshops.skin_matrices(W, Ms)
        S_[s[:, 0] <= 0] = np.eye(4)
        d_rest = meshops.unskin_delta(S_, delta)
        basis, shapes = meshops.shape_arrays(o)
        shapes[c["shape"]] = basis + d_rest
        meshops.set_shapes(o, basis, shapes)
        made.append((n, round(float(np.abs(delta).max() * 1000), 1)))
    posing.reset_pose(rig)
    return made


manifest_corr = []
if not K.opt(a, "--no-corr"):
    for c in CORR:
        made = bake_corrective(c)
        K.log("CORR", c["shape"], made)
        if made:
            manifest_corr.append({"shape": c["shape"], "bone": c["bone"], "parent": c["parent"],
                                  "axis": [round(float(x), 5) for x in c["axis"]], "from": c["frm"], "to": c["to"],
                                  "meshes": [m for m, _ in made]})
    json.dump(manifest_corr, open(os.path.join(K.LOGS, "correctives.json"), "w"), indent=1)
for o in bpy.data.objects:
    if o.type == "MESH" and o.parent is rig:
        for m in o.modifiers:
            if m.type == "ARMATURE":
                m.use_deform_preserve_volume = False
if K.opt(a, "--save"):
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(K.BLENDS, "kael_s6_deform.blend"))
K.log("done")
