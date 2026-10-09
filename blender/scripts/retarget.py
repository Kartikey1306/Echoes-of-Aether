"""Retarget the prototype's sampled clips (blender/anim/clips.json) onto the MPFB mixamo rig and export an
animation FBX for Unity's Humanoid retargeting.

blender -b <hero.blend> --python retarget.py -- <male|female> [--sheet clip1,clip2] [--export out.fbx]
"""
import bpy, sys, os, json, math
from mathutils import Matrix, Vector, Quaternion

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
A = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
STYLE = A[0] if A else "male"
DATA = json.load(open(os.path.join(ROOT, "anim", "clips.json")))
BONES = DATA["bones"]
BI = {n: i for i, n in enumerate(BONES)}

# TS (Y up, +Z forward, +X = character left) -> Blender (Z up, -Y forward, +X = character left)
M = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
MI = M.transposed()

TS_PARENT = {"hips": "root", "spine": "hips", "chest": "spine", "neck": "chest", "head": "neck",
             "clavicle_L": "chest", "upperarm_L": "clavicle_L", "forearm_L": "upperarm_L", "hand_L": "forearm_L",
             "clavicle_R": "chest", "upperarm_R": "clavicle_R", "forearm_R": "upperarm_R", "hand_R": "forearm_R",
             "thigh_L": "hips", "shin_L": "thigh_L", "foot_L": "shin_L", "thigh_R": "hips", "shin_R": "thigh_R", "foot_R": "shin_R"}
TS_ORDER = ["root", "hips", "spine", "chest", "neck", "head", "clavicle_L", "upperarm_L", "forearm_L", "hand_L",
            "clavicle_R", "upperarm_R", "forearm_R", "hand_R", "thigh_L", "shin_L", "foot_L", "thigh_R", "shin_R", "foot_R"]


def ts_rest_dirs(fem):
    a = math.radians(17 if fem else 16)
    a2 = a - 0.04
    up, fo, hand = (0.292, 0.252, 0.172) if fem else (0.305, 0.262, 0.185)
    d = {}
    for side, sx in (("L", 1), ("R", -1)):
        d["clavicle_" + side] = Vector((sx * 0.17, 0.005, -0.016))
        d["upperarm_" + side] = Vector((sx * math.sin(a) * up, -math.cos(a) * up, -0.012))
        d["forearm_" + side] = Vector((sx * math.sin(a2) * fo, -math.cos(a2) * fo, 0.022))
        d["hand_" + side] = Vector((sx * math.sin(a2) * hand, -math.cos(a2) * hand, 0.008))
        d["thigh_" + side] = Vector((sx * 0.008, -0.415, 0.016))
        d["shin_" + side] = Vector((sx * 0.004, -0.427, -0.038))
        d["foot_" + side] = Vector((sx * 0.008, -0.058, 0.187))
    return {k: (M @ v).normalized() for k, v in d.items()}


MAP = {  # mixamo bone -> TS bone whose world rotation drives it (with rest correction)
    "LeftShoulder": "clavicle_L", "LeftArm": "upperarm_L", "LeftForeArm": "forearm_L", "LeftHand": "hand_L",
    "RightShoulder": "clavicle_R", "RightArm": "upperarm_R", "RightForeArm": "forearm_R", "RightHand": "hand_R",
    "LeftUpLeg": "thigh_L", "LeftLeg": "shin_L", "LeftFoot": "foot_L",
    "RightUpLeg": "thigh_R", "RightLeg": "shin_R", "RightFoot": "foot_R",
}


def euler_ts(x, y, z):
    """three.js Euler 'XYZ' (degrees) -> rotation matrix (Rx @ Ry @ Rz), converted to Blender axes."""
    r = Matrix.Rotation(math.radians(x), 3, "X") @ Matrix.Rotation(math.radians(y), 3, "Y") @ Matrix.Rotation(math.radians(z), 3, "Z")
    return M @ r @ MI


def main():
    rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
    fem = STYLE == "female"
    pre = "mixamorig:"
    bones = rig.data.bones
    rest = {b.name: b.matrix_local.to_3x3() for b in bones}
    dirs_ts = ts_rest_dirs(fem)
    corr = {}
    for mb, tb in MAP.items():
        b = bones[pre + mb]
        dm = (b.tail_local - b.head_local).normalized()
        corr[mb] = dm.rotation_difference(dirs_ts[tb]).to_matrix()
    height = max(v.co.z for o in bpy.data.objects if o.type == "MESH" and o.name == "Body" for v in o.data.vertices) if "Body" in bpy.data.objects else 1.8
    scale = height / 1.8
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
    clips = DATA["styles"][STYLE]
    order = [b.name for b in bones]  # parents come before children in Blender's bone list
    made = []
    for name, clip in clips.items():
        act = bpy.data.actions.new(name)
        act.use_fake_user = True
        rig.animation_data_create()
        rig.animation_data.action = act
        prevq = {}
        for fi, fr in enumerate(clip["frames"]):
            W = {"root": Matrix.Identity(3)}
            R = {}
            for tb in TS_ORDER:
                i = BI[tb] * 3
                R[tb] = euler_ts(fr[i], fr[i + 1], fr[i + 2])
                W[tb] = (W[TS_PARENT[tb]] if tb != "root" else Matrix.Identity(3)) @ R[tb] if tb != "root" else R[tb]
            half = Quaternion().slerp(R["chest"].to_quaternion(), 0.5).to_matrix()
            target = {
                "Hips": W["hips"], "Spine": W["spine"], "Spine1": W["spine"] @ half, "Spine2": W["chest"],
                "Neck": W["neck"], "Head": W["head"],
            }
            for mb, tb in MAP.items():
                target[mb] = W[tb] @ corr[mb]
            world = {}
            for bn in order:
                short = bn[len(pre):] if bn.startswith(pre) else bn
                b = bones[bn]
                pw = world[b.parent.name] if b.parent else Matrix.Identity(3)
                wt = target.get(short, pw)
                world[bn] = wt
                basis = rest[bn].inverted() @ (pw.inverted() @ wt) @ rest[bn]
                q = basis.to_quaternion()
                if bn in prevq and q.dot(prevq[bn]) < 0:
                    q.negate()
                prevq[bn] = q
                pb = rig.pose.bones[bn]
                pb.rotation_quaternion = q
                pb.keyframe_insert("rotation_quaternion", frame=fi + 1, group=bn)
            # Root motion of the hips (bob, crouch, lunges).
            hp = rig.pose.bones[pre + "Hips"]
            p = Vector(fr[-3:])
            d = (M @ p) * scale
            hp.location = rest[pre + "Hips"].inverted() @ d
            hp.keyframe_insert("location", frame=fi + 1, group=pre + "Hips")
        act["eoa_loop"] = clip["loop"]
        act["eoa_duration"] = clip["duration"]
        made.append(name)
    print("ACTIONS", len(made))
    return rig


def contact_sheet(rig, names):
    import build_human  # noqa
    scene = bpy.context.scene
    scene.render.fps = 30
    body = bpy.data.objects.get("Body") or [o for o in bpy.data.objects if o.type == "MESH"][0]
    for o in bpy.data.objects:
        if o.type == "MESH" and (o.name.startswith(("Hair_", "Facial_")) and not o.name.endswith(("_short", "_ponytail"))):
            o.hide_render = True
    out = []
    for n in names:
        act = bpy.data.actions[n]
        rig.animation_data.action = act
        nfr = int(act.frame_range[1])
        for k, f in enumerate([1, max(1, nfr // 3), max(1, 2 * nfr // 3), nfr]):
            scene.frame_set(f)
            build_human.setup_render(body, f"anim_{STYLE}_{n}_{k}", {"q": (3.2, 0.95, 30, 50)})
            out.append(f"anim_{STYLE}_{n}_{k}")
    return out


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    rig = main()
    if "--sheet" in A:
        contact_sheet(rig, A[A.index("--sheet") + 1].split(","))
    if "--export" in A:
        path = A[A.index("--export") + 1]
        for o in list(bpy.data.objects):
            if o.type != "ARMATURE":
                bpy.data.objects.remove(o, do_unlink=True)
        rig.animation_data.action = None
        bpy.ops.object.select_all(action="DESELECT")
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE"}, apply_scale_options="FBX_SCALE_ALL",
                                 axis_forward="-Z", axis_up="Y", bake_space_transform=True, add_leaf_bones=False,
                                 use_armature_deform_only=True, bake_anim=True, bake_anim_use_all_actions=True,
                                 bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.0)
        print("EXPORTED", path)
