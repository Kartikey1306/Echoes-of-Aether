"""Phase Stalker (2.0 m): lean, fast, phasing hunter with long hand blades.

Robot space, reference units of the 1.8 m body (x = robot's left, y = up, z = forward). Layout follows
RobotBodies.BuildStalker: slim pelvis, thin spine, compact chest with a glowing core, pointed head (forward cone)
with a visor slit, small shoulder plates, thin limbs, long glowing blades extending from the hands.
Note the whole body goes semi-transparent while phasing (robot_shell/frame/joint opacity), so the silhouette is
kept clean and the glow parts carry the read.
"""
from mathutils import Vector

import robokit as K
from robokit import FRAME, GLOW, JOINT, SHELL, HEX, OCT, RIDGE, R, Rd, T, box, cyl, ico, limb, prism, sphere, tube
from bot_sentinel import fold


def build():
    rb = K.Robot("stalker", 2.0, 1.15)
    J = rb.J

    # ------------------------------------------------------------------ hips
    rb.add("hips", prism(OCT(0.21, 0.15, 0.045), 0.1, FRAME, axis="y", bev=0.008), T(0, 0.95, -0.01))
    cod = [(-0.07, 1.0), (0.07, 1.0), (0.04, 0.9), (0.0, 0.86), (-0.04, 0.9)]
    rb.add("hips", prism(cod, 0.03, SHELL, axis="z", bev=0.006), T(0, 0, 0.075) @ Rd(-10, 0, 0))
    for sd in ("L", "R"):
        rb.side(sd)
        rb.add("hips_S", cyl(0.04, 0.03, 8, JOINT, axis="x"), T(0.125, 0.93, 0.0))
        rb.add("hips_S", cyl(0.043, 0.012, 8, FRAME, axis="x"), T(0.142, 0.93, 0.0))
        fin = [(0.06, 1.02), (-0.03, 1.03), (-0.2, 0.93), (-0.02, 0.95)]          # swept hip blade (side view z, y)
        rb.add("hips_S", prism(fin, 0.02, SHELL, axis="x", bev=0.004), T(0.158, 0, -0.02) @ Rd(0, 0, -8))
    fold(rb, "hips")

    # ------------------------------------------------------------------ spine: exposed vertebrae
    rb.add("spine", cyl(0.032, 0.27, 8, JOINT, axis="y"), T(0, 1.15, -0.035))
    for y in (1.085, 1.145, 1.205):
        rb.add("spine", prism(HEX(0.13, 0.09, 0.03), 0.032, FRAME, axis="y", bev=0.004), T(0, y, -0.035))
        rb.add("spine", box(0.02, 0.025, 0.07, FRAME), T(0, y, -0.1) @ Rd(-25, 0, 0))   # dorsal spines
    rb.add("spine", box(0.06, 0.17, 0.02, SHELL, bev=0.004), T(0, 1.15, 0.05))
    for sx in (1, -1):
        rb.add("spine", tube([(sx * 0.05, 1.05, 0.0), (sx * 0.075, 1.15, 0.01), (sx * 0.06, 1.26, 0.0)], 0.01, JOINT, n=4, sub=2))

    # ------------------------------------------------------------------ chest: inverted triangle with a keel
    torso = [(-0.05, 1.26), (0.05, 1.26), (0.19, 1.43), (0.185, 1.5), (0.1, 1.535), (-0.1, 1.535), (-0.185, 1.5), (-0.19, 1.43)]
    rb.add("chest", prism(torso, 0.2, FRAME, axis="z", bev=0.008, taper=0.82), T(0, 0, -0.025))
    keel = [(0.012, 1.27), (0.06, 1.28), (0.17, 1.43), (0.165, 1.49), (0.09, 1.515), (0.012, 1.5)]
    for sd in ("L", "R"):
        rb.side(sd)
        rb.add("chest_S", prism(keel, 0.03, SHELL, axis="z", bev=0.006, pan=[("+z", 0.012, -0.004)]),
               T(0, 0, 0.085) @ Rd(0, 22, 0))
        rb.add("chest_S", box(0.1, 0.02, 0.18, FRAME), T(0.12, 1.36, -0.03) @ Rd(0, 0, 40))       # rib
        # phase vane on the back: thin swept fin with a glowing edge
        vane = [(0.0, 0.0), (0.05, 0.0), (0.02, 0.34), (-0.015, 0.33)]
        Mv = T(0.07, 1.47, -0.13) @ Rd(-35, 0, -22)
        rb.add("chest_S", prism(vane, 0.018, SHELL, axis="x", bev=0.004), Mv)
        rb.add("chest_S", tube([(0, 0.02, 0.052), (0, 0.18, 0.04), (0, 0.335, 0.022)], 0.006, GLOW, n=3), Mv)
        rb.add("chest_S", box(0.05, 0.06, 0.06, FRAME), T(0.07, 1.48, -0.12))
    fold(rb, "chest")
    rb.add("chest", cyl(0.05, 0.04, 6, FRAME, axis="z"), T(0, 1.385, 0.09))
    rb.add("chest", ico(0.034, GLOW, 1, scale=(1, 1.3, 0.8)), T(0, 1.385, 0.11))
    rb.add("chest", box(0.14, 0.05, 0.12, FRAME, bev=0.006), T(0, 1.52, -0.04))                    # collar
    cowl = [(-0.03, 1.5), (-0.13, 1.49), (-0.155, 1.6), (-0.09, 1.625)]
    rb.add("chest", prism(cowl, 0.17, SHELL, axis="x", bev=0.006, taper=0.8))                       # rear cowl

    # ------------------------------------------------------------------ neck / head: forward wedge sensor head
    rb.add("neck", cyl(0.032, 0.11, 8, JOINT, axis="y"), T(0, 1.515, -0.025))
    rb.add("neck", cyl(0.01, 0.1, 5, FRAME, axis="y"), T(0, 1.51, -0.065))
    # long, low wedge skull pitched slightly nose-down; narrow visor slit + paired side lenses
    Mhd = T(0, 1.64, 0.045) @ Rd(6, 0, 0)
    rb.add("head", prism(HEX(0.15, 0.115, 0.045), 0.34, SHELL, axis="z", bev=0.006, taper=0.3,
                         pan=[("-z", 0.02, -0.006)]), Mhd)
    rb.add("head", prism(HEX(0.12, 0.06, 0.035), 0.2, FRAME, axis="z", taper=0.5), Mhd @ T(0, -0.045, -0.04))
    rb.add("head", box(0.07, 0.01, 0.012, GLOW), Mhd @ T(0, 0.012, 0.115) @ Rd(-14, 0, 0))
    for sx in (1, -1):
        for z, y, x, r in ((0.06, 0.018, 0.047, 0.01), (0.0, 0.022, 0.056, 0.008)):
            rb.add("head", cyl(r, 0.012, 6, GLOW, axis="x"), Mhd @ T(sx * x, y, z))
    rb.add("head", prism([(0.08, 0.0), (-0.1, 0.0), (-0.2, 0.05), (-0.02, 0.025)], 0.016, FRAME, axis="x"),
           Mhd @ T(0, 0.05, 0.0))                                                                       # swept crest

    # ------------------------------------------------------------------ arms
    for sd in ("L", "R"):
        rb.side(sd)
        ua, fa, hd, he = J["upperarm_L"], J["forearm_L"], J["hand_L"], J["handEnd_L"]
        Mp = T(ua + Vector((0.02, 0.05, 0.0))) @ R(0, 0, -0.2)
        sp = [(-0.07, -0.04), (0.06, -0.05), (0.1, 0.0), (0.07, 0.055), (-0.05, 0.05)]
        rb.add("clavicle_S", prism(sp, 0.18, SHELL, axis="z", bev=0.006, taper=0.7), Mp)
        rb.add("clavicle_S", prism([(0.0, 0.04), (0.05, 0.05), (-0.06, 0.13)], 0.02, SHELL, axis="x"), Mp @ T(0.04, 0, -0.04))
        Mu = limb(ua, fa)
        rb.add("upperarm_S", sphere(0.048, JOINT, 8, 5), T(ua))
        rb.add("upperarm_S", cyl(0.033, 0.25, 8, FRAME, axis="y"), Mu @ T(0, -0.15, 0))
        rb.add("upperarm_S", prism(RIDGE(0.07, 0.03), 0.17, SHELL, axis="y", bev=0.004, taper=1.15),
               Mu @ T(0.035, -0.13, 0.0) @ Rd(0, 90, 0))
        rb.add("upperarm_S", cyl(0.009, 0.2, 5, JOINT, axis="y"), Mu @ T(0.0, -0.15, 0.045))
        L = (hd - fa).length
        Mf = limb(fa, hd)
        rb.add("forearm_S", cyl(0.04, 0.085, 8, JOINT, axis="x"), Mf)
        rb.add("forearm_S", prism(RIDGE(0.09, 0.1, 0.035, back=0.025), 0.21, SHELL, axis="y", bev=0.006, taper=1.15,
                                  pan=[("+x", 0.012, -0.004)]), Mf @ T(0.005, -0.13, 0.0) @ Rd(0, 90, 0))
        rb.add("forearm_S", box(0.006, 0.12, 0.012, GLOW), Mf @ T(0.055, -0.13, 0.0))
        rb.add("forearm_S", prism(OCT(0.07, 0.07, 0.02), 0.03, FRAME, axis="y"), Mf @ T(0, -L + 0.02, 0))
        # hand = blade mount with talons; the long glowing blade runs along the arm direction past the hand
        Mh = limb(hd, he)
        rb.add("hand_S", box(0.06, 0.08, 0.08, FRAME, bev=0.008), Mh @ T(0.0, -0.045, 0.0))
        rb.add("hand_S", box(0.03, 0.12, 0.05, SHELL, bev=0.005), Mh @ T(0.035, -0.06, 0.0))
        for z in (-0.025, 0.025):
            tal = [(0.0, 0.0), (0.02, 0.0), (0.012, -0.07), (-0.01, -0.1)]
            rb.add("hand_S", prism(tal, 0.014, FRAME, axis="x"), Mh @ T(-0.025, -0.08, z) @ Rd(0, 0, -20))
        blade = [(-0.022, -0.02), (0.03, -0.035), (0.036, -0.32), (0.02, -0.58), (-0.012, -0.8), (-0.02, -0.56), (-0.028, -0.26)]
        rb.add("hand_S", prism(blade, 0.016, GLOW, axis="x"), Mh @ T(0.012, -0.03, 0.0))
        rb.add("hand_S", prism([(-0.035, 0.03), (0.04, 0.03), (0.04, -0.09), (-0.03, -0.07)], 0.03, FRAME, axis="x", bev=0.004),
               Mh @ T(0.012, -0.03, 0.0))

    # ------------------------------------------------------------------ legs
    for sd in ("L", "R"):
        rb.side(sd)
        th, sn, ft = J["thigh_L"], J["shin_L"], J["foot_L"]
        Mt = limb(th, sn)
        rb.add("thigh_S", sphere(0.052, JOINT, 8, 5), T(th))
        rb.add("thigh_S", prism(OCT(0.075, 0.085, 0.02), 0.34, FRAME, axis="y", taper=1.15), Mt @ T(0, -0.2, 0))
        rb.add("thigh_S", prism(RIDGE(0.1, 0.05), 0.24, SHELL, axis="y", bev=0.006, taper=1.3,
                                pan=[("+z", 0.01, -0.004)]), Mt @ T(0.005, -0.18, 0.05) @ Rd(3, 0, 0))
        rb.add("thigh_S", cyl(0.012, 0.24, 6, JOINT, axis="y"), Mt @ T(0.02, -0.2, -0.05))
        Ms = limb(sn, ft)
        rb.add("shin_S", cyl(0.04, 0.09, 8, JOINT, axis="x"), T(sn))
        kn = [(-0.02, 0.06), (0.05, 0.05), (0.07, -0.02), (0.02, -0.09)]
        rb.add("shin_S", prism(kn, 0.09, SHELL, axis="x", bev=0.006), Ms @ T(0, 0.0, 0.03))
        rb.add("shin_S", prism(RIDGE(0.085, 0.1, 0.03, back=0.02), 0.32, SHELL, axis="y", bev=0.006, taper=1.25,
                               pan=[("+x", 0.012, -0.004), ("-x", 0.012, -0.004)]), Ms @ T(0, -0.21, 0.01))
        spur = [(-0.03, 0.0), (-0.17, -0.07), (-0.04, -0.15)]                                            # calf spur
        rb.add("shin_S", prism(spur, 0.025, SHELL, axis="x", bev=0.003), Ms @ T(0, -0.08, -0.02))
        rb.add("shin_S", cyl(0.014, 0.2, 6, FRAME, axis="y"), Ms @ T(0, -0.22, -0.06))
        fx = ft.x
        rb.add("foot_S", cyl(0.032, 0.09, 8, JOINT, axis="x"), T(ft))
        sole = [(-0.08, 0.0), (0.14, 0.0), (0.16, 0.02), (0.1, 0.06), (-0.03, 0.08), (-0.085, 0.045)]
        rb.add("foot_S", prism(sole, 0.09, FRAME, axis="x", bev=0.006), T(fx, 0, 0))
        for k, dx in enumerate((-0.03, 0.0, 0.03)):
            claw = [(0.0, 0.0), (0.08 + (0.02 if k == 1 else 0.0), 0.0), (0.0, 0.035)]
            rb.add("foot_S", prism(claw, 0.022, SHELL, axis="x", bev=0.003), T(fx + dx, 0.0, 0.13) @ Rd(0, dx * 400, 0))
        rb.add("foot_S", prism([(-0.07, 0.0), (-0.15, 0.0), (-0.07, 0.04)], 0.03, SHELL, axis="x"), T(fx, 0, 0))   # heel spur
    return rb
