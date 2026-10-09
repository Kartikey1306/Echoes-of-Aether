"""Kael concept stance (dreamlayer/characters/kael/kael_master_front.png): arms hanging close to the body about 15 deg
out from vertical with soft elbows, palms towards the thighs, legs straight with the feet under the hips.

Bones are aimed in world space with the minimal rotation from their current direction, then rolled about their own
axis (forearm/hand) so the back of the hand faces outwards; twist bones are driven like TwistBones.cs."""
import math
import numpy as np
from mathutils import Matrix, Vector
import kcommon as K

PRE = K.PRE


def _world(rig, bone):
    return rig.matrix_world @ rig.pose.bones[PRE + bone].matrix


def _set_world(rig, bone, M):
    import bpy
    rig.pose.bones[PRE + bone].matrix = rig.matrix_world.inverted() @ M
    bpy.context.view_layer.update()


def aim(rig, bone, target):
    """Rotate `bone` about its head so its head->tail direction points along `target` (world)."""
    M = _world(rig, bone)
    head = M.to_translation()
    d0 = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
    t = Vector(target).normalized()
    ax = d0.cross(t)
    if ax.length < 1e-8:
        return
    ang = math.acos(max(-1.0, min(1.0, d0.dot(t))))
    R = Matrix.Rotation(ang, 4, ax.normalized())
    _set_world(rig, bone, Matrix.Translation(head) @ R @ Matrix.Translation(-head) @ M)


def roll(rig, bone, deg):
    M = _world(rig, bone)
    head = M.to_translation()
    d0 = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
    R = Matrix.Rotation(math.radians(deg), 4, d0)
    _set_world(rig, bone, Matrix.Translation(head) @ R @ Matrix.Translation(-head) @ M)


def dorsal(rig, side):
    """Back-of-hand normal (world) from the hand and the index / pinky knuckle bones."""
    S = "Left" if side > 0 else "Right"
    mw = rig.matrix_world
    pb = rig.pose.bones
    w = mw @ pb[PRE + S + "Hand"].head
    i = mw @ pb[PRE + S + "HandIndex1"].head
    p = mw @ pb[PRE + S + "HandPinky1"].head
    return ((i - w).cross(p - w) * side).normalized()


def hand_facing(rig, side, target):
    """Roll the forearm about its own axis so the back of the hand faces `target` (world) as well as possible."""
    S = "Left" if side > 0 else "Right"
    if PRE + S + "HandIndex1" not in rig.pose.bones:
        return 0
    t = Vector(target).normalized()
    best, best_d = 0, -9.0
    for deg in range(-180, 180, 6):
        roll(rig, S + "ForeArm", deg)
        d = dorsal(rig, side).dot(t)
        roll(rig, S + "ForeArm", -deg)
        if d > best_d:
            best, best_d = deg, d
    for deg in range(best - 6, best + 7, 1):
        roll(rig, S + "ForeArm", deg)
        d = dorsal(rig, side).dot(t)
        roll(rig, S + "ForeArm", -deg)
        if d > best_d:
            best, best_d = deg, d
    roll(rig, S + "ForeArm", best)
    return best


def concept_stance(rig, arm_out=15.0, elbow=9.0, legs_in=1.0):
    import bpy
    for s, S in ((1, "Left"), (-1, "Right")):
        a = math.radians(arm_out)
        aim(rig, S + "Arm", (s * math.sin(a), 0.03, -math.cos(a)))
        e = math.radians(elbow)
        aim(rig, S + "ForeArm", (s * math.sin(a * 0.75), -math.sin(e), -math.cos(e)))
        aim(rig, S + "Hand", (s * math.sin(a * 0.5), -math.sin(e * 1.4), -math.cos(e * 1.4)))
        # concept: back of the hand turned out and forwards (the knuckle studs read from the front)
        hand_facing(rig, s, (s * 0.5, -0.87, 0.0))
        # legs: straight, feet under the hips (the rest pose spreads them ~6 deg)
        M = _world(rig, S + "UpLeg")
        d0 = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
        cur = math.degrees(math.atan2(abs(d0.x), -d0.z))
        tgt = max(cur - legs_in, 0.0)
        aim(rig, S + "UpLeg", (s * math.sin(math.radians(tgt)), d0.y, -math.cos(math.radians(tgt))))
        M2 = _world(rig, S + "Leg")
        d1 = (M2.to_3x3() @ Vector((0, 1, 0))).normalized()
        aim(rig, S + "Leg", (s * math.sin(math.radians(tgt)), d1.y, -math.cos(math.radians(tgt))))
    try:
        import posing
        posing.drive_twist(rig)
    except Exception as ex:
        print("twist drive skipped", ex)
    bpy.context.view_layer.update()
