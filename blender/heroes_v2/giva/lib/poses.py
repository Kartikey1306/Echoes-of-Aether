"""Game clips (Anim_Female.fbx) on the Giva rig: import once, copy rest-relative local rotations bone by bone
(both rigs are the MPFB mixamo_unity skeleton with the same rest orientations, within ~2 degrees), find the
extreme frames of each clip and pose the rig there."""
import bpy, math
import numpy as np
from mathutils import Quaternion, Vector, Matrix
import gv

SRC = None
ACTIONS = {}


def load(path=gv.ANIM_F):
    global SRC, ACTIONS
    if SRC is not None:
        return SRC
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=False)
    new = [o for o in bpy.data.objects if o not in before]
    SRC = next(o for o in new if o.type == "ARMATURE")
    SRC.name = "AnimSrc"
    for o in new:
        o.hide_render = True
    ACTIONS = {a.name.split("|")[-1]: a for a in bpy.data.actions if "|" in a.name}
    SRC.animation_data_create()
    return SRC


def frame_range(clip):
    a = ACTIONS[clip]
    f0, f1 = a.frame_range
    return int(round(f0)), int(round(f1))


_CURVES = {}


def _curves(clip):
    """{bone: {"rot": [fc w,x,y,z], "loc": [fc x,y,z]}} from the action's fcurves (layered actions)."""
    if clip in _CURVES:
        return _CURVES[clip]
    act = ACTIONS[clip]
    fcs = []
    if hasattr(act, "layers") and len(act.layers):
        for L in act.layers:
            for st in L.strips:
                for cb in st.channelbags:
                    fcs += list(cb.fcurves)
    else:
        fcs = list(act.fcurves)
    out = {}
    for fc in fcs:
        dp = fc.data_path
        if not dp.startswith('pose.bones["'):
            continue
        bone = dp[len('pose.bones["'):dp.index('"]')]
        prop = dp[dp.index('"]') + 3:]
        d = out.setdefault(bone, {})
        if prop == "rotation_quaternion":
            d.setdefault("rot", [None] * 4)[fc.array_index] = fc
        elif prop == "location":
            d.setdefault("loc", [None] * 3)[fc.array_index] = fc
    _CURVES[clip] = out
    return out


def _bone_quats(clip, frame):
    cv = _curves(clip)
    q = {}
    hloc = Vector()
    for bone, d in cv.items():
        r = d.get("rot")
        if r and all(r):
            qq = Quaternion([fc.evaluate(frame) for fc in r])
            qq.normalize()
            q[bone] = qq
        if bone == gv.P + "Hips" and d.get("loc") and all(d["loc"]):
            hloc = Vector([fc.evaluate(frame) for fc in d["loc"]])
    return q, hloc


def pose(rig, clip, frame, root_motion=False):
    """Pose `rig` at clip/frame (local rotations copied; hips translation scaled by hip height)."""
    q, hloc = _bone_quats(clip, frame)
    s_src = (SRC.matrix_world @ SRC.data.bones[gv.P + "Hips"].head_local).z
    s_dst = (rig.matrix_world @ rig.data.bones[gv.P + "Hips"].head_local).z
    k = s_dst / max(s_src, 1e-6)
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        if pb.name in q:
            pb.rotation_quaternion = q[pb.name]
        else:
            pb.rotation_quaternion = Quaternion()
        pb.location = Vector()
    hp = rig.pose.bones[gv.P + "Hips"]
    loc = hloc * k
    if not root_motion:
        # keep the character over the origin horizontally (bone-local axes: convert via rest matrix)
        rest = rig.data.bones[gv.P + "Hips"].matrix_local.to_3x3()
        w = rest @ loc
        w.x = 0
        w.y = 0
        loc = rest.inverted() @ w
    hp.location = loc
    bpy.context.view_layer.update()


def rest(rig):
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Quaternion()
        pb.location = Vector()
        pb.scale = Vector((1, 1, 1))
    bpy.context.view_layer.update()


JOINTS = [("LeftForeArm", "LeftArm"), ("RightForeArm", "RightArm"), ("LeftLeg", "LeftUpLeg"), ("RightLeg", "RightUpLeg"),
          ("LeftArm", "LeftShoulder"), ("RightArm", "RightShoulder"), ("LeftUpLeg", "Hips"), ("RightUpLeg", "Hips"),
          ("LeftHand", "LeftForeArm"), ("RightHand", "RightForeArm"), ("Spine1", "Spine")]


def bend_angles(rig):
    """Angle (deg) between each joint's bone direction and its parent's, minus the rest angle."""
    out = {}
    for b, p in JOINTS:
        pb, pp = rig.pose.bones[gv.P + b], rig.pose.bones[gv.P + p]
        d1 = (pb.tail - pb.head).normalized()
        d0 = (pp.tail - pp.head).normalized()
        r1 = (rig.data.bones[gv.P + b].tail_local - rig.data.bones[gv.P + b].head_local).normalized()
        r0 = (rig.data.bones[gv.P + p].tail_local - rig.data.bones[gv.P + p].head_local).normalized()
        a = math.degrees(d1.angle(d0, 0.0)) - math.degrees(r1.angle(r0, 0.0))
        # wrist / forearm twist: angle of the bone's x axis relative to parent's x axis about the bone
        out[b] = a
    return out


def twist_angle(rig, bone, parent):
    pb, pp = rig.pose.bones[gv.P + bone], rig.pose.bones[gv.P + parent]
    rb, rp = rig.data.bones[gv.P + bone], rig.data.bones[gv.P + parent]
    local = (pp.matrix.to_quaternion().inverted() @ pb.matrix.to_quaternion())
    rest_local = rp.matrix_local.to_quaternion().inverted() @ rb.matrix_local.to_quaternion()
    d = rest_local.inverted() @ local
    # swing-twist about local Y
    tw = Quaternion((d.w, 0, d.y, 0))
    tw.normalize()
    ang = 2 * math.degrees(math.atan2(tw.y, tw.w))
    return (ang + 180) % 360 - 180


def extremes(rig, clips, per_clip=2, step=2):
    """[(clip, frame, score, angles)] picking the frames with the largest joint stress per clip."""
    res = []
    for c in clips:
        if c not in ACTIONS:
            continue
        f0, f1 = frame_range(c)
        scored = []
        for f in range(f0, f1 + 1, step):
            pose(rig, c, f)
            a = bend_angles(rig)
            tw = abs(twist_angle(rig, "LeftHand", "LeftForeArm")) + abs(twist_angle(rig, "RightHand", "RightForeArm"))
            s = sum(max(0, v) for v in a.values()) + 0.5 * tw
            scored.append((s, f, a))
        scored.sort(key=lambda x: -x[0])
        picked = []
        for s, f, a in scored:
            if all(abs(f - p[1]) > (f1 - f0) * 0.2 for p in picked):
                picked.append((c, f, s, a))
            if len(picked) >= per_clip:
                break
        res += picked
    rest(rig)
    return res
