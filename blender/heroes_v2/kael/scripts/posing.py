"""Posing helpers for Kael v2: the game's clips (Anim_Male.fbx) retargeted onto the hero rig by world-space
rotation deltas, the runtime twist-bone / corrective drivers emulated in Python (same maths as TwistBones.cs and
CorrectiveShapes.cs), and joint-angle metrics for picking extreme frames."""
import bpy, math
import numpy as np
from mathutils import Matrix, Vector, Quaternion
import kcommon as K

PRE = K.PRE
_SRC = {}


def load_anim(path=K.ANIM_MALE):
    """Import the clip armature once; returns (armature object, {clip: action})."""
    if "rig" in _SRC and _SRC["rig"].name in bpy.data.objects:
        return _SRC["rig"], _SRC["acts"]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=False)
    new = [o for o in bpy.data.objects if o not in before]
    src = next(o for o in new if o.type == "ARMATURE")
    for o in new:
        o.hide_render = True
        o.hide_set(False)
    acts = {a.name.split("|")[-1]: a for a in bpy.data.actions}
    src.animation_data_create()
    _SRC.update(rig=src, acts=acts)
    return src, acts


def clip_range(act):
    a, b = act.frame_range
    return int(a), int(b)


def _depth(b):
    k = 0
    while b.parent:
        b = b.parent; k += 1
    return k


def apply_clip(rig, clip, frame, src=None, acts=None):
    """Pose rig like the source armature at (clip, frame): world rotation deltas, hips translation scaled by leg
    length. Non-matching bones (twist bones) stay at rest (drive them with drive_twist)."""
    if src is None:
        src, acts = load_anim()
    act = acts[clip]
    if src.animation_data.action != act:
        src.animation_data.action = act
        if hasattr(src.animation_data, "action_slot") and len(act.slots):
            src.animation_data.action_slot = act.slots[0]
    bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()
    smw = src.matrix_world
    rmw = rig.matrix_world
    world = {}
    hips_ratio = (rig.data.bones[PRE + "Hips"].head_local.z / max(src.data.bones[PRE + "Hips"].head_local.z, 1e-6))
    bones = sorted(rig.data.bones, key=_depth)
    for b in bones:
        pb = rig.pose.bones[b.name]
        pb.rotation_mode = "QUATERNION"
        sb = src.pose.bones.get(b.name)
        rest_w = rmw @ b.matrix_local
        if b.parent is None:
            parent_pose = rmw
            rest_rel = b.matrix_local
        else:
            parent_pose = world[b.parent.name]
            rest_rel = b.parent.matrix_local.inverted() @ b.matrix_local
        if sb is not None:
            D = (smw @ sb.matrix).to_3x3() @ (smw @ sb.bone.matrix_local).to_3x3().inverted()
            R = D @ rest_w.to_3x3()
        else:
            R = (parent_pose @ rest_rel).to_3x3()
        pos = (parent_pose @ rest_rel).to_translation()
        if b.parent is None and sb is not None:
            # root motion: hips offset from rest, scaled to this rig
            off = (smw @ sb.matrix).to_translation() - (smw @ sb.bone.matrix_local).to_translation()
            pos = pos + off * hips_ratio
        Wm = Matrix.Translation(pos) @ R.normalized().to_4x4()
        world[b.name] = Wm
        basis = rest_rel.inverted() @ parent_pose.inverted() @ Wm
        pb.rotation_quaternion = basis.to_quaternion()
        pb.location = basis.to_translation() if b.parent is None else Vector()
    bpy.context.view_layer.update()


def reset_pose(rig):
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    bpy.context.view_layer.update()


# ----------------------------------------------------------------------------- runtime driver emulation


def _twist_about(q, axis):
    p = Vector((q.x, q.y, q.z)).dot(axis) * axis
    t = Quaternion((q.w, p.x, p.y, p.z))
    n = t.magnitude
    if n < 1e-6:
        return Quaternion()
    t.normalize()
    if t.w < 0:
        t.negate()
    return t


def _rel(rig, ref, bone):
    """Rotation of bone relative to ref (posed), as a quaternion (armature space)."""
    return (rig.pose.bones[ref].matrix.to_3x3().inverted() @ rig.pose.bones[bone].matrix.to_3x3()).to_quaternion()


def _rel_rest(rig, ref, bone):
    return (rig.data.bones[ref].matrix_local.to_3x3().inverted() @ rig.data.bones[bone].matrix_local.to_3x3()).to_quaternion()


def drive_twist(rig, weight=0.5):
    """TwistBones.cs: ForeArmTwist follows `weight` of the hand roll about the forearm axis; ArmTwist keeps `weight`
    of the upper arm roll relative to the shoulder."""
    for side in ("Left", "Right"):
        # follow
        tb, src, ref = PRE + side + "ForeArmTwist", PRE + side + "Hand", PRE + side + "ForeArm"
        if tb in rig.pose.bones:
            rest = _rel_rest(rig, ref, src)
            delta = _rel(rig, ref, src) @ rest.inverted()
            # forearm axis in reference (bone-local) space = +Y in Blender bone frames
            axis = (rig.data.bones[src].head_local - rig.data.bones[ref].head_local)
            axis = (rig.data.bones[ref].matrix_local.to_3x3().inverted() @ axis).normalized()
            tw = _twist_about(delta, axis)
            q = Quaternion().slerp(tw, weight)
            # twist bone basis: its rest equals the parent's frame -> pose basis = q expressed in its own frame
            rest_tb = _rel_rest(rig, ref, tb)
            rig.pose.bones[tb].rotation_mode = "QUATERNION"
            rig.pose.bones[tb].rotation_quaternion = rest_tb.inverted() @ q @ rest_tb
        # counter
        tb, src, ref = PRE + side + "ArmTwist", PRE + side + "Arm", PRE + side + "Shoulder"
        if tb in rig.pose.bones:
            rest = _rel_rest(rig, ref, src)
            q = rest.inverted() @ _rel(rig, ref, src)
            axis = Vector((0, 1, 0))  # bone-local long axis
            twl = _twist_about(q, axis)
            qq = Quaternion().slerp(twl.inverted(), 1 - weight)
            rest_tb = _rel_rest(rig, src, tb)
            rig.pose.bones[tb].rotation_mode = "QUATERNION"
            rig.pose.bones[tb].rotation_quaternion = rest_tb.inverted() @ qq @ rest_tb
    bpy.context.view_layer.update()


def bone_dir_local_child(rig, bone, child=None):
    b = rig.data.bones[bone]
    kids = [c for c in b.children if "Twist" not in c.name]
    if child:
        kids = [c for c in kids if c.name.endswith(child)] or kids
    elif b.name.endswith("Hand"):
        kids = [c for c in kids if "Middle1" in c.name] or kids
    if not kids:
        return Vector((0, 1, 0))
    c = max(kids, key=lambda c: (c.head_local - b.head_local).length)
    return (b.matrix_local.to_3x3().inverted() @ (c.head_local - b.head_local)).normalized()


def corrective_angle(rig, bone, parent, axis_world, child=None):
    """CorrectiveShapes.cs angle (degrees, right-hand rule about axis_world at rest) of bone relative to parent."""
    dl = bone_dir_local_child(rig, bone, child)
    P0 = rig.data.bones[parent].matrix_local.to_3x3()
    B0 = rig.data.bones[bone].matrix_local.to_3x3()
    P = rig.pose.bones[parent].matrix.to_3x3()
    B = rig.pose.bones[bone].matrix.to_3x3()
    rest = (P0.inverted() @ B0 @ dl).normalized()
    cur = (P.inverted() @ B @ dl).normalized()
    ax = (P0.inverted() @ (rig.matrix_world.to_3x3().inverted() @ Vector(axis_world))).normalized()
    c = rest.cross(cur)
    s = c.length
    if s < 1e-6:
        return 0.0
    return math.degrees(math.atan2(s, rest.dot(cur))) * (c / s).dot(ax)


def corrective_weights(rig, correctives):
    out = {}
    for c in correctives:
        ang = corrective_angle(rig, c["bone"], c["parent"], c["axis"], c.get("child"))
        w = min(1.0, max(0.0, (ang - c["from"]) / (c["to"] - c["from"])))
        out[c["shape"]] = (w ** c.get("power", 1.0), ang)
    return out


def set_corrective_shapes(meshes, weights):
    for o in meshes:
        kb = o.data.shape_keys.key_blocks if o.data.shape_keys else None
        if not kb:
            continue
        for k in kb:
            if k.name.startswith("corr_"):
                k.value = weights.get(k.name, (0.0, 0.0))[0]
