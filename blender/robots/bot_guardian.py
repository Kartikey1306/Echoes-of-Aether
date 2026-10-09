"""Aether Guardian (5.2 m boss) -- also used for guardian_vault (glow recoloured at runtime).

Robot space, reference units of the 1.8 m body (s = 2.8889, shoulder width 1.35). Layout follows
RobotBodies.BuildGuardian: massive chest with the exposed `core` between `plate_L` / `plate_R`, a rear frame block with
three glowing exhaust stacks, huge pauldrons with glowing fins, heavy gauntlets and fists.

Special parts (ROBOT_PARTS.md): `core` (child of chest, pivot = core centre), `plate_L` / `plate_R` (children of
chest, pivots at the rest centres; they slide 0.46 m outward along local X while the core is exposed, so the track in
front of the chest is kept clear and rails run above/below it). The core mesh is a separate renderer whose only
material is robot_glow (RobotRig swaps it to robot_core because it is the `core` transform). Nothing else on the
guardian contains "core" in its object/material name (RobotRig would treat it as core).
"""
from mathutils import Vector

import robokit as K
from robokit import FRAME, GLOW, JOINT, SHELL, HEX, OCT, RIDGE, R, Rd, T, box, cyl, ico, limb, prism, sphere, tube
from bot_sentinel import bolts, fold, vent

CORE = Vector((0.0, 1.385, 0.238))         # chest + (0, 0.14, 0.26)
PLATE_X, PLATE_Z = 0.12, 0.278             # chest + (+/-0.12, 0.14, 0.30)


def build():
    rb = K.Robot("guardian", 5.2, 1.35)
    J = rb.J

    # ------------------------------------------------------------------ hips
    pelvis = [(-0.15, 0.85), (0.1, 0.84), (0.16, 0.92), (0.15, 1.04), (-0.16, 1.05), (-0.18, 0.95)]
    rb.add("hips", prism(pelvis, 0.3, FRAME, axis="x", bev=0.012, pan=[("+x", 0.02, -0.005), ("-x", 0.02, -0.005)]))
    rb.add("hips", box(0.36, 0.04, 0.3, JOINT), T(0, 1.06, -0.02))
    cod = [(-0.09, 1.02), (0.09, 1.02), (0.08, 0.9), (0.0, 0.83), (-0.08, 0.9)]
    rb.add("hips", prism(cod, 0.05, SHELL, axis="z", bev=0.008, pan=[("+z", 0.014, -0.004)]), T(0, 0, 0.165) @ Rd(-8, 0, 0))
    rb.add("hips", box(0.3, 0.09, 0.06, SHELL, bev=0.01, pan=[("-z", 0.012, -0.004)]), T(0, 0.99, -0.175))
    for sd in ("L", "R"):
        rb.side(sd)
        rb.add("hips_S", cyl(0.07, 0.05, 10, JOINT, axis="x"), T(0.19, 0.93, 0.0))
        rb.add("hips_S", cyl(0.075, 0.02, 10, FRAME, axis="x", cap_inset=(0.02, -0.005)), T(0.222, 0.93, 0.0))
        tas = [(-0.13, 1.07), (0.13, 1.07), (0.12, 0.95), (0.0, 0.88), (-0.12, 0.95)]
        rb.add("hips_S", prism(tas, 0.035, SHELL, axis="x", bev=0.008, pan=[("+x", 0.018, -0.005)]),
               T(0.255, 0.0, -0.01) @ T(0, 1.0, 0) @ Rd(0, 0, -12) @ T(0, -1.0, 0))
    fold(rb, "hips")

    # ------------------------------------------------------------------ spine
    rb.add("spine", cyl(0.1, 0.26, 10, JOINT, axis="y"), T(0, 1.155, -0.05))
    for i, y in enumerate((1.095, 1.16, 1.225)):
        rb.add("spine", prism(OCT(0.32 - i * 0.015, 0.24, 0.06), 0.05, FRAME, axis="y", bev=0.008), T(0, y, 0.0))
    for sx in (1, -1):
        rb.add("spine", cyl(0.025, 0.14, 8, FRAME, axis="y"), T(sx * 0.15, 1.13, -0.08))
        rb.add("spine", cyl(0.014, 0.12, 6, SHELL, axis="y"), T(sx * 0.15, 1.22, -0.08))
        rb.add("spine", tube([(sx * 0.05, 1.06, 0.11), (sx * 0.07, 1.16, 0.14), (sx * 0.05, 1.27, 0.12)], 0.016, JOINT, n=5, sub=2))

    # ------------------------------------------------------------------ chest
    core_prof = [(-0.2, 1.12), (0.12, 1.12), (0.2, 1.22), (0.21, 1.47), (0.15, 1.53), (-0.2, 1.56), (-0.26, 1.4)]
    rb.add("chest", prism(core_prof, 0.4, FRAME, axis="x", bev=0.014))
    # core socket: octagonal frame block with a recessed throat around the core
    rb.add("chest", prism(OCT(0.4, 0.42, 0.12), 0.07, FRAME, axis="z", bev=0.01), T(0, 1.385, 0.2))
    rb.add("chest", cyl(0.155, 0.04, 16, JOINT, axis="z", hollow=(0.02, 0.02)), T(0, 1.385, 0.24))
    for k in range(8):                                   # radial vanes around the socket
        rb.add("chest", box(0.018, 0.06, 0.03, FRAME), T(0, 1.385, 0.255) @ Rd(0, 0, 22.5 + 45 * k) @ T(0, 0.17, 0))
    # rails for the sliding plates (static, above and below the track)
    for y in (1.385 + 0.19, 1.385 - 0.19):
        rb.add("chest", box(0.76, 0.036, 0.06, FRAME, bev=0.008), T(0, y, 0.29))
        rb.add("chest", box(0.74, 0.012, 0.02, JOINT), T(0, y, 0.322))
        for sx in (1, -1):
            rb.add("chest", box(0.04, 0.06, 0.09, FRAME, bev=0.008), T(sx * 0.39, y, 0.29))       # end stops
    # armoured lips over the rails: the plates run in a recessed bay (upper lip split around the jaw)
    for sx in (1, -1):
        rb.add("chest", box(0.27, 0.05, 0.11, SHELL, bev=0.01, taper=(0.95, 0.8), pan=[("+y", 0.016, -0.004)]),
               T(sx * 0.275, 1.6, 0.285) @ Rd(-12, 0, sx * 4))
    rb.add("chest", box(0.8, 0.05, 0.1, SHELL, bev=0.01, btaper=(0.9, 0.8), pan=[("+z", 0.014, -0.004)]), T(0, 1.17, 0.28) @ Rd(10, 0, 0))
    pec = [(0.245, 1.2), (0.285, 1.21), (0.375, 1.36), (0.37, 1.5), (0.31, 1.565), (0.245, 1.555)]
    Mpec = T(0.245, 0, 0.19) @ Rd(0, 20, 0) @ T(-0.245, 0, 0)
    for sd in ("L", "R"):
        rb.side(sd)
        rb.add("chest_S", prism(pec, 0.08, SHELL, axis="z", bev=0.014, pan=[("+z", 0.02, -0.006)]), Mpec)
        bolts(rb, "chest_S", Mpec @ T(0, 0, 0.04), [(0.27, 1.24, 0), (0.33, 1.32, 0), (0.35, 1.48, 0), (0.28, 1.53, 0)], r=0.012)
        rb.add("chest_S", box(0.17, 0.12, 0.44, SHELL, bev=0.016, taper=(0.88, 0.9), pan=[("+y", 0.02, -0.006)]),
               T(0.2, 1.62, -0.06) @ Rd(0, 0, -10))                                                         # yoke
        rb.add("chest_S", tube([(0.12, 1.62, -0.36), (0.22, 1.66, -0.3), (0.3, 1.62, -0.16)], 0.02, JOINT, n=6, sub=2))
        for k in range(3):
            rb.add("chest_S", box(0.03, 0.03, 0.2, FRAME), T(0.2, 1.26 + k * 0.055, -0.06) @ Rd(0, 0, -20))   # rib vents
    fold(rb, "chest")
    rb.add("chest", box(0.38, 0.2, 0.08, SHELL, bev=0.014, pan=[("-z", 0.02, -0.006)]), T(0, 1.63, -0.2) @ Rd(-14, 0, 0))   # rear collar
    # reactor block + three exhaust stacks
    rb.add("chest", box(0.5, 0.4, 0.24, FRAME, bev=0.018, pan=[("+x", 0.03, -0.008), ("-x", 0.03, -0.008)]), T(0, 1.445, -0.382))
    vent(rb, "chest", T(0, 1.4, -0.503) @ Rd(0, 180, 0), 0.34, 0.24, 6)
    for i in range(3):
        x = -0.15 + i * 0.15
        top = 1.92 if i == 1 else 1.88
        h = top - 1.5
        rb.add("chest", cyl(0.046, h, 10, FRAME, axis="y", hollow=(0.01, 0.04)), T(x, 1.5 + h / 2, -0.442))
        rb.add("chest", cyl(0.034, 0.01, 10, GLOW, axis="y"), T(x, top - 0.035, -0.442))
        rb.add("chest", cyl(0.049, 0.03, 10, GLOW, axis="y"), T(x, top - 0.1, -0.442))
        rb.add("chest", cyl(0.058, 0.05, 10, FRAME, axis="y"), T(x, 1.62, -0.442))
    rb.add("chest", box(0.42, 0.04, 0.05, FRAME), T(0, 1.76, -0.442))
    # Aether crack across the right pectoral
    crack = [(-0.265, 1.52), (-0.29, 1.47), (-0.28, 1.43), (-0.32, 1.38), (-0.31, 1.34), (-0.345, 1.29)]
    rb.add("chest", tube([(x, y, 0.232 - (abs(x) - 0.245) * 0.364) for x, y in crack], 0.007, GLOW, n=3))

    # core + plates (special transforms)
    rb.special("core", "chest", CORE)
    rb.add("core", ico(0.12, GLOW, 2, scale=(1, 1, 0.55)), T(CORE))
    for name, sx in (("plate_L", 1), ("plate_R", -1)):
        piv = Vector((sx * PLATE_X, CORE.y, PLATE_Z))
        rb.special(name, "chest", piv)
        Mx = K.ID if sx > 0 else K.MIRROR_X
        Mpl = Mx @ T(PLATE_X, CORE.y, PLATE_Z + 0.06) @ T(-0.115, 0, 0.0) @ Rd(0, 10, 0) @ T(0.115, 0, 0)   # shallow keel
        prof = [(-0.115, -0.165), (0.085, -0.175), (0.115, -0.13), (0.115, 0.13), (0.085, 0.175), (-0.115, 0.165)]
        rb.parts[name].add(prism(prof, 0.065, SHELL, axis="z", bev=0.02, taper=0.9, pan=[("+z", 0.022, -0.006)]), Mpl)
        rb.parts[name].add(prism([(-0.09, 0.02), (0.07, 0.07), (0.09, 0.04), (-0.07, -0.015)], 0.03, SHELL,
                                 axis="z", bev=0.006), Mpl @ T(0.0, 0.05, 0.045))                 # chevron rib
        rb.parts[name].add(prism([(-0.09, -0.02), (0.07, -0.07), (0.09, -0.04), (-0.07, 0.015)], 0.03, SHELL,
                                 axis="z", bev=0.006), Mpl @ T(0.0, -0.05, 0.045))
        rb.parts[name].add(box(0.02, 0.32, 0.05, FRAME), Mpl @ T(-0.106, 0, 0.0))               # meeting edge
        for y in (-0.178, 0.178):
            rb.parts[name].add(box(0.16, 0.018, 0.03, FRAME), Mpl @ T(0.0, y, -0.03))           # rail shoes
        for p in ((0.08, 0.14), (0.08, -0.14), (-0.07, 0.14), (-0.07, -0.14)):
            rb.parts[name].add(cyl(0.011, 0.01, 6, FRAME, axis="z"), Mpl @ T(p[0], p[1], 0.034))

    # ------------------------------------------------------------------ neck / head
    rb.add("neck", cyl(0.08, 0.17, 10, JOINT, axis="y"), T(0, 1.55, -0.04))
    for sx in (1, -1):
        rb.add("neck", cyl(0.02, 0.14, 6, FRAME, axis="y"), T(sx * 0.07, 1.54, -0.08))
    # head geometry sits higher / further forward than the placeholder and 15% larger: top of head = 1.8 ref (5.2 m)
    Hd = T(0, 1.63 + 0.06, 0.07) @ K.Sc(1.15) @ T(0, -1.63, 0)
    helm = [(-0.12, 1.53), (0.08, 1.525), (0.18, 1.57), (0.19, 1.64), (0.15, 1.71), (0.02, 1.735), (-0.1, 1.72), (-0.14, 1.64)]
    rb.add("head", prism(helm, 0.25, SHELL, axis="x", bev=0.014, pan=[("+y", 0.03, -0.006), ("+x", 0.03, -0.006), ("-x", 0.03, -0.006)]), Hd)
    rb.add("head", box(0.24, 0.05, 0.06, FRAME, bev=0.008), Hd @ T(0, 1.63, 0.17))
    rb.add("head", box(0.2, 0.018, 0.012, GLOW), Hd @ T(0, 1.632, 0.2))
    rb.add("head", box(0.25, 0.03, 0.08, SHELL, bev=0.006), Hd @ T(0, 1.672, 0.16) @ Rd(-16, 0, 0))
    rb.add("head", box(0.17, 0.05, 0.09, SHELL, bev=0.01, btaper=(0.8, 0.9)), Hd @ T(0, 1.565, 0.14))
    for sx in (1, -1):
        horn = [(0.0, 0.0), (0.06, 0.0), (-0.12, 0.09), (-0.16, 0.08)]
        rb.add("head", prism(horn, 0.03, SHELL, axis="x", bev=0.004), Hd @ T(sx * 0.115, 1.69, -0.04))
        rb.add("head", cyl(0.04, 0.03, 8, FRAME, axis="x", cap_inset=(0.014, -0.004)),
               (K.ID if sx > 0 else K.MIRROR_X) @ Hd @ T(0.13, 1.625, 0.03))

    # ------------------------------------------------------------------ arms
    for sd in ("L", "R"):
        rb.side(sd)
        ua, fa, hd, he = J["upperarm_L"], J["forearm_L"], J["hand_L"], J["handEnd_L"]
        Mp = T(ua + Vector((0.08, 0.075, -0.01))) @ R(0, 0, -0.3)
        pauld = [(-0.2, -0.08), (0.18, -0.14), (0.22, -0.04), (0.19, 0.09), (0.08, 0.15), (-0.1, 0.15), (-0.19, 0.08)]
        rb.add("clavicle_S", prism([(x, y * 0.9) for x, y in pauld], 0.38, SHELL, axis="z", bev=0.022,
                                   pan=[("+y", 0.03, -0.008), ("+z", 0.03, -0.008)]), Mp)
        rb.add("clavicle_S", box(0.36, 0.05, 0.34, FRAME), Mp @ T(0.03, -0.14, 0))
        rb.add("clavicle_S", prism([(-0.15, 0.03), (0.15, 0.04), (0.17, -0.05), (-0.13, -0.04)], 0.32, SHELL, axis="z", bev=0.01),
               Mp @ T(0.06, -0.19, 0) @ Rd(0, 0, -8))
        bolts(rb, "clavicle_S", Mp, [(x, 0.07, 0.192) for x in (-0.1, 0.0, 0.1)], r=0.013)
        # heat-sink fins (glow) on the outside (placeholder: shoulder fin at upperarm + (0.3, 0.12, 0))
        Mfin = T(ua + Vector((0.3, 0.07, -0.01)))
        rb.add("clavicle_S", box(0.03, 0.24, 0.3, FRAME, bev=0.006), Mfin @ T(-0.015, 0, 0))
        for z in (-0.06, 0.06):
            rb.add("clavicle_S", box(0.03, 0.2, 0.012, GLOW), Mfin @ T(0.012, 0, z))
            rb.add("clavicle_S", box(0.034, 0.22, 0.02, FRAME), Mfin @ T(0.01, 0, z + 0.03))
        Mu = limb(ua, fa)
        rb.add("upperarm_S", sphere(0.11, JOINT, 10, 6), T(ua))
        rb.add("upperarm_S", cyl(0.085, 0.24, 10, FRAME, axis="y"), Mu @ T(0, -0.16, 0))
        rb.add("upperarm_S", prism(RIDGE(0.2, 0.07), 0.2, SHELL, axis="y", bev=0.01, taper=1.1, pan=[("+z", 0.016, -0.005)]),
               Mu @ T(0.085, -0.15, 0.0) @ Rd(0, 90, 0))
        for z in (0.09, -0.09):
            rb.add("upperarm_S", cyl(0.028, 0.13, 8, FRAME, axis="y"), Mu @ T(0.0, -0.1, z))
            rb.add("upperarm_S", cyl(0.015, 0.12, 6, SHELL, axis="y"), Mu @ T(0.0, -0.21, z))
        L = (hd - fa).length
        Mf = limb(fa, hd)
        rb.add("forearm_S", cyl(0.095, 0.2, 12, JOINT, axis="x"), Mf)
        rb.add("forearm_S", cyl(0.1, 0.03, 12, FRAME, axis="x", cap_inset=(0.03, -0.006)), Mf @ T(0.11, 0, 0))
        rb.add("forearm_S", prism(OCT(0.27, 0.3, 0.07), 0.23, SHELL, axis="y", bev=0.016, taper=1.12,
                                  pan=[("+x", 0.022, -0.008), ("+z", 0.022, -0.008), ("-z", 0.022, -0.008)]), Mf @ T(0.0, -0.14, 0.0))
        rb.add("forearm_S", box(0.26, 0.12, 0.06, SHELL, bev=0.012), Mf @ T(0.0, -0.08, 0.165) @ Rd(-8, 0, 0))
        rb.add("forearm_S", prism(OCT(0.24, 0.26, 0.06), 0.05, FRAME, axis="y"), Mf @ T(0, -L + 0.02, 0))
        rb.add("forearm_S", box(0.03, 0.22, 0.09, JOINT), Mf @ T(0.137, -0.14, 0.0))
        rb.add("forearm_S", box(0.012, 0.2, 0.016, GLOW), Mf @ T(0.148, -0.14, 0.0))
        Mh = limb(hd, he)
        rb.add("hand_S", box(0.2, 0.17, 0.24, FRAME, bev=0.014), Mh @ T(0.0, -0.08, 0.0))
        rb.add("hand_S", box(0.05, 0.15, 0.22, SHELL, bev=0.01), Mh @ T(0.09, -0.08, 0.0))
        for k, z in enumerate((-0.08, -0.027, 0.027, 0.08)):
            rb.add("hand_S", box(0.1, 0.07, 0.05, FRAME, bev=0.008), Mh @ T(-0.04, -0.19, z) @ Rd(0, 0, 25))
            rb.add("hand_S", box(0.05, 0.04, 0.052, SHELL), Mh @ T(0.01, -0.175, z))
        rb.add("hand_S", box(0.06, 0.1, 0.06, FRAME, bev=0.008), Mh @ T(-0.06, -0.09, 0.13) @ Rd(25, 0, 0))

    # ------------------------------------------------------------------ legs
    for sd in ("L", "R"):
        rb.side(sd)
        th, sn, ft = J["thigh_L"], J["shin_L"], J["foot_L"]
        Mt = limb(th, sn)
        rb.add("thigh_S", sphere(0.095, JOINT, 10, 6), T(th))
        rb.add("thigh_S", prism(OCT(0.15, 0.17, 0.04), 0.34, FRAME, axis="y", taper=1.12), Mt @ T(0.01, -0.2, 0))
        rb.add("thigh_S", prism(RIDGE(0.17, 0.08), 0.28, SHELL, axis="y", bev=0.012, taper=1.25, pan=[("+z", 0.018, -0.006)]),
               Mt @ T(0.025, -0.2, 0.09) @ Rd(4, 0, 0))
        rb.add("thigh_S", box(0.05, 0.26, 0.2, SHELL, bev=0.01, pan=[("+x", 0.02, -0.006)]), Mt @ T(0.105, -0.2, -0.005))
        for z in (-0.1,):
            rb.add("thigh_S", cyl(0.03, 0.18, 8, FRAME, axis="y"), Mt @ T(0.03, -0.15, z))
            rb.add("thigh_S", cyl(0.016, 0.16, 6, SHELL, axis="y"), Mt @ T(0.03, -0.3, z))
        Ms = limb(sn, ft)
        rb.add("shin_S", cyl(0.085, 0.18, 12, JOINT, axis="x"), T(sn))
        rb.add("shin_S", cyl(0.09, 0.025, 12, FRAME, axis="x", cap_inset=(0.03, -0.006)), T(sn) @ T(0.1, 0, 0))
        knee = [(-0.04, 0.11), (0.07, 0.1), (0.12, 0.0), (0.08, -0.11), (-0.03, -0.08)]
        rb.add("shin_S", prism(knee, 0.2, SHELL, axis="x", bev=0.014, pan=[("+x", 0.02, -0.005)]), Ms @ T(0.01, 0.0, 0.07))
        rb.add("shin_S", prism(RIDGE(0.19, 0.22, 0.07, back=0.04), 0.3, SHELL, axis="y", bev=0.014, taper=1.25,
                               pan=[("+x", 0.024, -0.006), ("-x", 0.024, -0.006)]), Ms @ T(0.01, -0.22, 0.03))
        rb.add("shin_S", box(0.13, 0.27, 0.1, FRAME), Ms @ T(0.0, -0.2, -0.09))
        for x in (-0.04, 0.04):
            rb.add("shin_S", cyl(0.026, 0.18, 8, FRAME, axis="y"), Ms @ T(x, -0.13, -0.16))
            rb.add("shin_S", cyl(0.014, 0.17, 6, SHELL, axis="y"), Ms @ T(x, -0.3, -0.15))
        rb.add("shin_S", prism(OCT(0.18, 0.2, 0.045), 0.05, FRAME, axis="y"), Ms @ T(0, -0.385, 0.0))
        fx = ft.x + 0.02
        rb.add("foot_S", cyl(0.065, 0.17, 10, JOINT, axis="x"), T(ft))
        sole = [(-0.16, 0.0), (0.27, 0.0), (0.31, 0.03), (0.27, 0.08), (0.12, 0.12), (-0.08, 0.13), (-0.165, 0.08)]
        rb.add("foot_S", prism(sole, 0.21, FRAME, axis="x", bev=0.012, pan=[("+x", 0.02, -0.005)]), T(fx, 0, 0))
        for dx in (-0.055, 0.055):
            rb.add("foot_S", box(0.1, 0.07, 0.13, SHELL, bev=0.012, taper=(0.9, 0.7)), T(fx + dx, 0.06, 0.23))
        rb.add("foot_S", box(0.18, 0.06, 0.16, SHELL, bev=0.012), T(fx, 0.12, 0.08) @ Rd(-22, 0, 0))
        rb.add("foot_S", box(0.16, 0.07, 0.07, JOINT), T(fx, 0.04, -0.15))
    return rb
