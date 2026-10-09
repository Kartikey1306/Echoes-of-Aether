"""BOLT-7 (friendly maintenance robot NPC, 1.55 m).

Not covered by ROBOT_PARTS.md: the prototype (src/actors/Npc.ts) builds BOLT as a RobotModel of height 1.55 on the
humanoid robot rig (shoulder width 1.15, 'robot' animation style incl. the 'sit' clip), so this model uses exactly
the same 20-transform skeleton contract (joints = RobotRig.ComputeJoints(1.55, 1.15)), rest A-pose, +Z facing and the
same material names (palette from Npc.ts: shell #9a7a2a, frame #2a2a2e, glow #ffc24a). Reference units (1.8 m body).
"""
import math

from mathutils import Vector

import robokit as K
from robokit import FRAME, GLOW, JOINT, SHELL, HEX, OCT, RIDGE, R, Rd, T, box, cyl, ico, limb, prism, sphere, torus, tube
from bot_sentinel import bolts, fold, vent


def hazard(rb, obj, M, w, h, n, depth=0.012):
    """Yellow/black hazard band: dark plate with diagonal shell-coloured stripes (geometry, no texture)."""
    rb.add(obj, box(w, h, depth, FRAME), M)
    step = w / n
    for i in range(n):
        x0 = -w / 2 + i * step + step * 0.12
        sw = step * 0.5
        pts = [(x0, -h / 2), (x0 + sw, -h / 2), (min(x0 + sw + h * 0.6, w / 2), h / 2), (min(x0 + h * 0.6, w / 2 - 0.002), h / 2)]
        rb.add(obj, prism(pts, depth * 0.5, SHELL, axis="z"), M @ T(0, 0, depth * 0.6))


def build():
    rb = K.Robot("bolt", 1.55, 1.15)
    J = rb.J

    # ------------------------------------------------------------------ hips + tool belt
    rb.add("hips", box(0.3, 0.14, 0.22, FRAME, bev=0.02, seg=2), T(0, 0.95, -0.01))
    rb.add("hips", box(0.34, 0.045, 0.25, JOINT, bev=0.008), T(0, 1.03, -0.01))
    for sx in (1, -1):
        rb.add("hips", box(0.07, 0.08, 0.06, FRAME, bev=0.01), T(sx * 0.1, 0.99, 0.13))        # belt pouches
        rb.add("hips", box(0.04, 0.12, 0.17, SHELL, bev=0.02, seg=2), T(sx * 0.19, 0.95, 0.0))  # hip guards
        rb.add("hips", cyl(0.045, 0.03, 8, JOINT, axis="x"), T(sx * 0.165, 0.93, 0.0))
    rb.add("hips", cyl(0.025, 0.1, 8, FRAME, axis="y"), T(-0.15, 0.94, -0.13))                    # wrench on the belt
    rb.add("hips", box(0.05, 0.025, 0.012, FRAME), T(-0.15, 0.995, -0.13))

    # ------------------------------------------------------------------ waist bellows
    for i, y in enumerate((1.07, 1.11, 1.15, 1.19, 1.23)):
        rb.add("spine", cyl(0.12 - (i % 2) * 0.012, 0.035, 12, JOINT, axis="y"), T(0, y, -0.01))

    # ------------------------------------------------------------------ chest: rounded utility torso + battery pack
    rb.add("chest", box(0.36, 0.3, 0.26, SHELL, bev=0.04, seg=2, taper=(1.04, 1.0), pan=[("+z", 0.03, -0.006)]),
           T(0, 1.39, -0.01))
    rb.add("chest", box(0.3, 0.07, 0.22, FRAME, bev=0.015), T(0, 1.255, -0.01))
    for k, x in enumerate((-0.07, -0.04, -0.01)):
        rb.add("chest", cyl(0.011, 0.012, 8, GLOW if k == 0 else FRAME, axis="z"), T(x, 1.46, 0.125))   # status lights
    rb.add("chest", box(0.1, 0.06, 0.02, FRAME, bev=0.004), T(0.08, 1.45, 0.122))                       # display slot
    rb.add("chest", box(0.08, 0.04, 0.012, GLOW), T(0.08, 1.45, 0.13))
    bolts(rb, "chest", T(0, 0, 0.12), [(x, y, 0) for x in (-0.15, 0.15) for y in (1.29, 1.49)], r=0.01)
    rb.add("chest", box(0.32, 0.3, 0.13, FRAME, bev=0.02), T(0, 1.4, -0.2))                             # battery pack
    rb.add("chest", box(0.33, 0.06, 0.14, SHELL, bev=0.015, seg=2), T(0, 1.56, -0.2))
    hazard(rb, "chest", T(0, 1.3, -0.267) @ Rd(0, 180, 0), 0.28, 0.05, 7)
    vent(rb, "chest", T(0, 1.42, -0.267) @ Rd(0, 180, 0), 0.18, 0.12, 4)
    coil = [(0.17 + 0.03 * math.cos(t * 0.9), 1.3 + 0.022 * t, -0.2 + 0.03 * math.sin(t * 0.9)) for t in range(10)]
    rb.add("chest", tube(coil, 0.009, JOINT, n=5, sub=2))                                               # coiled lead
    rb.add("chest", box(0.12, 0.04, 0.2, FRAME, bev=0.01), T(0, 1.55, -0.05))                           # neck collar

    # ------------------------------------------------------------------ head: big single camera lens
    rb.add("neck", cyl(0.04, 0.1, 8, JOINT, axis="y"), T(0, 1.52, -0.02))
    rb.add("neck", tube([(0.03, 1.47, -0.06), (0.05, 1.53, -0.07), (0.03, 1.58, -0.05)], 0.008, JOINT, n=4, sub=2))
    rb.add("head", box(0.28, 0.21, 0.23, SHELL, bev=0.035, seg=2, pan=[("+y", 0.03, -0.006)]), T(0, 1.665, 0.0))
    rb.add("head", box(0.23, 0.16, 0.03, FRAME, bev=0.012), T(0, 1.66, 0.112))                         # face plate
    rb.add("head", cyl(0.075, 0.05, 16, FRAME, axis="z", bev=0.006, hollow=(0.014, 0.02)), T(-0.025, 1.665, 0.14))
    rb.add("head", cyl(0.052, 0.02, 16, GLOW, axis="z"), T(-0.025, 1.665, 0.142))
    rb.add("head", torus(0.03, 0.008, JOINT, n=12, m=4, axis="z"), T(-0.025, 1.665, 0.155))             # iris
    rb.add("head", cyl(0.028, 0.03, 10, FRAME, axis="z"), T(0.075, 1.62, 0.13))                          # second lens
    rb.add("head", cyl(0.018, 0.012, 10, GLOW, axis="z"), T(0.075, 1.62, 0.145))
    rb.add("head", box(0.26, 0.03, 0.06, SHELL, bev=0.008), T(0, 1.765, 0.1) @ Rd(-12, 0, 0))            # brim
    for sx in (1, -1):
        rb.add("head", cyl(0.055, 0.03, 12, FRAME, axis="x", cap_inset=(0.018, -0.005)),
               (K.ID if sx > 0 else K.MIRROR_X) @ T(0.145, 1.66, -0.01))
    rb.add("head", cyl(0.007, 0.16, 5, FRAME, axis="y"), T(0.08, 1.84, -0.06) @ Rd(-10, 0, 8))
    rb.add("head", ico(0.016, GLOW, 1), T(0.068, 1.918, -0.075))

    # ------------------------------------------------------------------ arms
    for sd in ("L", "R"):
        rb.side(sd)
        ua, fa, hd, he = J["upperarm_L"], J["forearm_L"], J["hand_L"], J["handEnd_L"]
        rb.add("clavicle_S", ico(0.11, SHELL, 2, scale=(1.0, 0.75, 1.0)), T(ua + Vector((0.025, 0.05, 0.0))))   # round shoulder cap
        rb.add("clavicle_S", cyl(0.1, 0.03, 12, FRAME, axis="y"), T(ua + Vector((0.025, 0.0, 0.0))))
        Mu = limb(ua, fa)
        rb.add("upperarm_S", sphere(0.055, JOINT, 8, 5), T(ua))
        rb.add("upperarm_S", cyl(0.04, 0.24, 8, FRAME, axis="y"), Mu @ T(0, -0.15, 0))
        rb.add("upperarm_S", tube([(0.045, -0.04, 0.03), (0.06, -0.15, 0.04), (0.045, -0.27, 0.03)], 0.008, JOINT, n=4, sub=2), Mu)
        rb.add("upperarm_S", box(0.06, 0.12, 0.1, SHELL, bev=0.02, seg=2), Mu @ T(0.03, -0.13, 0.0))
        L = (hd - fa).length
        Mf = limb(fa, hd)
        rb.add("forearm_S", cyl(0.05, 0.1, 10, JOINT, axis="x"), Mf)
        rb.add("forearm_S", cyl(0.055, 0.02, 10, FRAME, axis="x", cap_inset=(0.016, -0.004)), Mf @ T(0.055, 0, 0))
        rb.add("forearm_S", box(0.13, 0.2, 0.13, SHELL, bev=0.025, seg=2, btaper=(0.9, 0.9), pan=[("+x", 0.02, -0.005)]),
               Mf @ T(0.0, -0.13, 0.0))
        rb.add("forearm_S", cyl(0.062, 0.03, 10, FRAME, axis="y"), Mf @ T(0, -L + 0.02, 0))
        Mh = limb(hd, he)
        rb.add("hand_S", box(0.08, 0.08, 0.1, FRAME, bev=0.012), Mh @ T(0, -0.045, 0.0))
        for z in (-0.03, 0.03):
            rb.add("hand_S", box(0.03, 0.08, 0.03, FRAME, bev=0.006), Mh @ T(-0.015, -0.115, z) @ Rd(0, 0, -15))
            rb.add("hand_S", box(0.026, 0.035, 0.028, SHELL), Mh @ T(-0.03, -0.16, z) @ Rd(0, 0, -35))
        rb.add("hand_S", box(0.03, 0.07, 0.03, FRAME, bev=0.006), Mh @ T(-0.035, -0.08, 0.06) @ Rd(30, 0, -15))
    # left forearm: welding torch with an amber tip
    rb.side("L")
    Mf = limb(J["forearm_L"], J["hand_L"])
    rb.add("forearm_S", cyl(0.018, 0.17, 8, FRAME, axis="y"), Mf @ T(0.0, -0.17, 0.085))
    rb.add("forearm_S", cyl(0.024, 0.04, 8, JOINT, axis="y"), Mf @ T(0.0, -0.08, 0.085))
    rb.add("forearm_S", cyl(0.01, 0.015, 6, GLOW, axis="y"), Mf @ T(0.0, -0.262, 0.085))
    # right forearm: tool rack
    rb.side("R")
    Mf = limb(J["forearm_L"], J["hand_L"])
    rb.add("forearm_S", box(0.04, 0.14, 0.04, FRAME, bev=0.006), Mf @ T(0.075, -0.13, 0.03))
    rb.add("forearm_S", cyl(0.008, 0.16, 6, SHELL, axis="y"), Mf @ T(0.095, -0.13, -0.02))

    # ------------------------------------------------------------------ legs: sturdy boots
    for sd in ("L", "R"):
        rb.side(sd)
        th, sn, ft = J["thigh_L"], J["shin_L"], J["foot_L"]
        Mt = limb(th, sn)
        rb.add("thigh_S", sphere(0.06, JOINT, 8, 5), T(th))
        rb.add("thigh_S", cyl(0.045, 0.32, 8, FRAME, axis="y"), Mt @ T(0, -0.2, 0))
        rb.add("thigh_S", box(0.13, 0.22, 0.13, SHELL, bev=0.025, seg=2, btaper=(0.9, 0.9), pan=[("+z", 0.02, -0.005)]),
               Mt @ T(0.005, -0.17, 0.01))
        Ms = limb(sn, ft)
        rb.add("shin_S", cyl(0.055, 0.12, 10, JOINT, axis="x"), T(sn))
        rb.add("shin_S", cyl(0.06, 0.02, 10, FRAME, axis="x", cap_inset=(0.02, -0.004)), T(sn) @ T(0.065, 0, 0))
        rb.add("shin_S", box(0.15, 0.3, 0.16, SHELL, bev=0.03, seg=2, taper=(1.0, 1.0), btaper=(1.1, 1.08),
                             pan=[("+z", 0.022, -0.006)]), Ms @ T(0, -0.23, 0.0))
        rb.add("shin_S", box(0.12, 0.05, 0.08, FRAME, bev=0.01), Ms @ T(0, -0.04, 0.06))                # knee pad
        hazard(rb, "shin_S", Ms @ T(0, -0.3, 0.083) @ Rd(-2, 0, 0), 0.13, 0.045, 4)                         # hazard band
        fx = ft.x
        rb.add("foot_S", cyl(0.04, 0.12, 8, JOINT, axis="x"), T(ft))
        sole = [(-0.1, 0.0), (0.2, 0.0), (0.23, 0.03), (0.2, 0.07), (0.05, 0.09), (-0.08, 0.09), (-0.11, 0.05)]
        rb.add("foot_S", prism(sole, 0.17, FRAME, axis="x", bev=0.015), T(fx, 0, 0))
        rb.add("foot_S", box(0.17, 0.06, 0.1, SHELL, bev=0.02, seg=2, taper=(0.9, 0.7)), T(fx, 0.06, 0.165))
        rb.add("foot_S", box(0.18, 0.025, 0.32, JOINT), T(fx, 0.0125, 0.06))                              # rubber sole
    return rb
