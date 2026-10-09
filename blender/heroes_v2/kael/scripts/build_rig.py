"""Stage 2 - Kael v2 rig: rest pose conformed to Anim_Male.fbx (bone directions), twist bones, clean body weights.

  blender -b blends/kael_s1_base.blend --python build_rig.py
Writes blends/kael_s2_rig.blend.
"""
import bpy, sys, os, json, math, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
from mathutils import Vector, Matrix
import meshops, weights
importlib.reload(meshops); importlib.reload(weights)

PRE = K.PRE
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = bpy.data.objects["Body"]
atts = [bpy.data.objects[n] for n in ("Eyes", "Brows", "Lashes", "Teeth", "Tongue") if n in bpy.data.objects]
# MakeHuman-topology copy of the body (garment cages, refits): conformed together with everything else
with bpy.data.libraries.load(os.path.join(K.BLENDS, "kael_s1_mh.blend")) as (src, dst):
    dst.objects = ["Body"]
mh = dst.objects[0]
mh.name = mh.data.name = "BodyMH"
bpy.context.scene.collection.objects.link(mh)
mh.parent = rig
mh.hide_render = True
for m in mh.modifiers:
    if m.type == "ARMATURE":
        m.object = rig


# ----------------------------------------------------------------------------- 1. rest pose conform


def anim_rest_dirs():
    before = set(bpy.data.objects)
    acts_before = set(bpy.data.actions)
    bpy.ops.import_scene.fbx(filepath=K.ANIM_MALE, automatic_bone_orientation=False)
    new = [o for o in bpy.data.objects if o not in before]
    src = next(o for o in new if o.type == "ARMATURE")
    d = {}
    for b in src.data.bones:
        h = src.matrix_world @ b.head_local
        t = src.matrix_world @ b.tail_local
        d[b.name] = (np.array(h), np.array((t - h).normalized()))
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    for ac in list(bpy.data.actions):
        if ac not in acts_before:
            bpy.data.actions.remove(ac)
    return d


def conform_rest(rig, meshes, target, tol_deg=0.25):
    """Rotate each bone (top-down, about its head) so its direction matches target; deform the meshes (all shape
    keys) with the same pose through numpy LBS, then apply the pose as the new rest pose."""
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="POSE")
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    bpy.context.view_layer.update()
    mw = rig.matrix_world
    report = []

    def depth(b):
        k = 0
        while b.parent:
            b = b.parent; k += 1
        return k
    for pb in sorted(rig.pose.bones, key=lambda p: depth(p.bone)):
        if pb.name not in target:
            continue
        bpy.context.view_layer.update()
        M = mw @ pb.matrix
        head = M.to_translation()
        y = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
        want = Vector(target[pb.name][1])
        ang = math.degrees(y.angle(want))
        if ang < tol_deg:
            continue
        report.append((round(ang, 2), pb.name))
        R = y.rotation_difference(want).to_matrix().to_4x4()
        Mn = Matrix.Translation(head) @ R @ Matrix.Translation(-head) @ M
        pb.matrix = mw.inverted() @ Mn
    bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode="OBJECT")
    # deform meshes (basis + shape keys) with numpy LBS
    for o in meshes:
        names, W = meshops.get_weights(o)
        if not names:
            continue
        s = W.sum(1, keepdims=True)
        W = np.where(s > 0, W / np.maximum(s, 1e-9), 0)
        Ms = meshops.pose_matrices(rig, names)
        mwo = np.array(o.matrix_world); mwoi = np.linalg.inv(mwo)
        basis, shapes = meshops.shape_arrays(o)
        wb = basis @ mwo[:3, :3].T + mwo[:3, 3]
        pb_, S = meshops.lbs(wb, W, Ms)
        unw = s[:, 0] <= 0
        pb_[unw] = wb[unw]
        new_basis = pb_ @ mwoi[:3, :3].T + mwoi[:3, 3]
        A = S[:, :3, :3]
        A[unw] = np.eye(3)
        new_shapes = {}
        for n, c in shapes.items():
            dl = (c - basis) @ mwo[:3, :3].T
            dw = np.einsum("vij,vj->vi", A, dl)
            new_shapes[n] = new_basis + dw @ mwoi[:3, :3].T
        values = {k.name: k.value for k in o.data.shape_keys.key_blocks} if o.data.shape_keys else {}
        meshops.set_shapes(o, new_basis, new_shapes, values)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    return report


target = anim_rest_dirs()
rep = conform_rest(rig, [body, mh] + atts, target)
K.log("CONFORM", len(rep), "bones rotated", sorted(rep, reverse=True)[:12])
# verify
worst = 0
for b in rig.data.bones:
    if b.name in target:
        d = Vector((rig.matrix_world @ b.tail_local) - (rig.matrix_world @ b.head_local)).normalized()
        worst = max(worst, math.degrees(d.angle(Vector(target[b.name][1]))))
K.log("CONFORM worst dir error deg", round(worst, 3))


# ----------------------------------------------------------------------------- 2. twist bones


def add_twist_bones(rig, frac=0.6, frac_tail=0.85):
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    eb = rig.data.edit_bones
    made = []
    for side in ("Left", "Right"):
        for parent, name in (("ForeArm", "ForeArmTwist"), ("Arm", "ArmTwist")):
            p = eb[PRE + side + parent]
            n = eb.get(PRE + side + name) or eb.new(PRE + side + name)
            n.head = p.head + (p.tail - p.head) * frac
            n.tail = p.head + (p.tail - p.head) * frac_tail
            n.roll = p.roll
            n.parent = p
            n.use_connect = False
            n.use_deform = True
            made.append(n.name)
    bpy.ops.object.mode_set(mode="OBJECT")
    # orientation check: same frame as the parent
    for nm in made:
        b = rig.data.bones[nm]
        r = (b.parent.matrix_local.to_3x3().inverted() @ b.matrix_local.to_3x3()).to_quaternion()
        ang = math.degrees(2 * math.acos(min(1.0, abs(r.w))))
        assert ang < 0.05, (nm, ang)
    return made


tw = add_twist_bones(rig)
K.log("TWIST", tw)

# ----------------------------------------------------------------------------- 3. body weights
info = weights.body_weights(body, rig)
K.log("WEIGHTS", json.dumps(info))
for o in atts:
    weights.attachment_weights(o, rig)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(K.BLENDS, "kael_s2_rig.blend"))
K.log("done")
