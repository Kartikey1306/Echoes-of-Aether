"""Corrupted Sentinel (2.15 m) and The Warden (2.6 m elite variant).

Authored in robot space, reference units of the 1.8 m body (x = robot's left, y = up, z = forward); the part
layout follows RobotBodies.BuildSentinel (pelvis, abdomen, chest + chest light + back vents, visor head,
pauldrons on the clavicles, forearm glow seams, right forearm blade; warden: crest, extra plating, left-forearm
shield emitter). Tiny parts are left unbevelled to stay inside the triangle budget.
"""
import math

from mathutils import Vector

import robokit as K
from robokit import FRAME, GLOW, JOINT, SHELL, HEX, OCT, RIDGE, R, Rd, T, box, cyl, limb, prism, sphere, tube


def bolts(rb, obj, M, pts, r=0.009, h=0.008, axis="z", mat=FRAME):
    for p in pts:
        rb.add(obj, cyl(r, h, 6, mat, axis=axis), M @ T(*p))


def vent(rb, obj, M, w, h, n, depth=0.03, mat=FRAME, slat=JOINT):
    """Louvred vent facing +z in M's frame: dark recess block + angled slats."""
    rb.add(obj, box(w, h, depth, slat), M @ T(0, 0, -depth / 2))
    for i in range(n):
        y = -h / 2 + h * (i + 0.5) / n
        rb.add(obj, box(w * 0.94, h / n * 0.55, 0.012, mat), M @ T(0, y, 0.002) @ Rd(35, 0, 0))


def fold(rb, name):
    """Parts added as name_L / name_R (mirrored side builds) onto a central object: merge them into `name`."""
    for sd in ("L", "R"):
        k = name + "_" + sd
        if k in rb.parts:
            src = rb.parts.pop(k)
            dst = rb.parts[name]
            base = len(dst.v)
            dst.v.extend(src.v)
            dst.f.extend([[i + base for i in f] for f in src.f])
            dst.m.extend(src.m)


def build(elite=False):
    height = 2.6 if elite else 2.15
    rb = K.Robot("warden" if elite else "sentinel", height, 1.15)
    J = rb.J
    E = 1.12 if elite else 1.0          # warden armour bulk

    # ------------------------------------------------------------------ hips / pelvis
    pelvis = [(-0.12, 0.88), (0.07, 0.87), (0.13, 0.93), (0.12, 1.025), (-0.13, 1.03), (-0.14, 0.95)]
    rb.add("hips", prism(pelvis, 0.3, FRAME, axis="x", bev=0.014, pan=[("+x", 0.02, -0.005), ("-x", 0.02, -0.005)]))
    rb.add("hips", box(0.32, 0.04, 0.24, JOINT), T(0, 1.045, -0.01))                          # waist band
    cod = [(-0.07, 1.0), (0.07, 1.0), (0.065, 0.91), (0.0, 0.855), (-0.065, 0.91)]
    rb.add("hips", prism(cod, 0.05, SHELL, axis="z", bev=0.01, pan=[("+z", 0.014, -0.005)]), T(0, 0, 0.135) @ Rd(-6, 0, 0))
    rb.add("hips", box(0.24, 0.07, 0.05, SHELL, bev=0.01), T(0, 0.985, -0.135))
    for sd in ("L", "R"):
        rb.side(sd)
        # hip actuator on the hinge axis (y=.93, z=0) so leg swing never exposes a seam
        rb.add("hips_S", cyl(0.055, 0.04, 10, JOINT, axis="x"), T(0.182, 0.93, 0.0))
        rb.add("hips_S", cyl(0.06 * E, 0.016, 10, FRAME, axis="x", cap_inset=(0.016, -0.004)), T(0.206, 0.93, 0.0))
        tas = [(-0.09, 1.06), (0.09, 1.06), (0.085, 0.95), (0.0, 0.9), (-0.085, 0.95)]
        rb.add("hips_S", prism(tas, 0.03, SHELL, axis="x", bev=0.006, pan=[("+x", 0.014, -0.004)]),
               T(0.232, 0.0, -0.005) @ T(0, 1.0, 0) @ Rd(0, 0, -10) @ T(0, -1.0, 0))
    fold(rb, "hips")

    # ------------------------------------------------------------------ spine / abdomen
    rb.add("spine", cyl(0.07, 0.25, 8, JOINT, axis="y"), T(0, 1.15, -0.045))
    for i, y in enumerate((1.105, 1.178)):
        rb.add("spine", prism(OCT(0.25 - i * 0.012, 0.19, 0.045), 0.055, FRAME, axis="y"), T(0, y, 0.0))
    for sx in (1, -1):
        rb.add("spine", tube([(sx * 0.035, 1.07, 0.07), (sx * 0.05, 1.15, 0.105), (sx * 0.04, 1.25, 0.085)], 0.011, JOINT, n=5, sub=2))
        rb.add("spine", box(0.04, 0.16, 0.07, FRAME), T(sx * 0.12, 1.15, -0.06))

    # ------------------------------------------------------------------ chest
    core = [(-0.16, 1.27), (0.12, 1.27), (0.19, 1.35), (0.205, 1.44), (0.16, 1.50), (-0.12, 1.50), (-0.175, 1.43)]
    rb.add("chest", prism(core, 0.34, FRAME, axis="x", bev=0.015))
    rb.add("chest", box(0.28, 0.12, 0.25, FRAME, bev=0.014, taper=(1.15, 1.1), pan=[("+z", 0.014, -0.005)]), T(0, 1.235, -0.02))
    pec = [(0.045, 1.29), (0.15, 1.30), (0.19, 1.37), (0.19, 1.47), (0.12, 1.515), (0.045, 1.49)]
    Mpec = T(0.0, 0.0, 0.19) @ T(0.1, 0, 0) @ Rd(0, 12, 0) @ T(-0.1, 0, 0)
    for sd in ("L", "R"):
        rb.side(sd)
        rb.add("chest_S", prism(pec, 0.055, SHELL, axis="z", bev=0.01, pan=[("+z", 0.016, -0.005)]), Mpec)
        bolts(rb, "chest_S", Mpec @ T(0, 0, 0.027), [(0.07, 1.31, 0.0), (0.165, 1.32, 0.0)])
        rb.add("chest_S", box(0.15 * E, 0.09, 0.28, SHELL, bev=0.015, taper=(0.9, 0.9), pan=[("+y", 0.016, -0.005)]),
               T(0.165, 1.515, -0.03) @ Rd(0, 0, -12))                                       # shoulder yoke
        for k in range(3):                                                                    # rib vents under the armpit
            rb.add("chest_S", box(0.045, 0.03, 0.2, FRAME), T(0.16, 1.29 + k * 0.05, -0.03))
        rb.add("chest_S", tube([(0.1, 1.48, -0.29), (0.15, 1.52, -0.24), (0.19, 1.5, -0.16)], 0.014, JOINT, n=5, sub=2))
    fold(rb, "chest")
    # sternum + chest light (security emblem) in an octagonal bezel
    rb.add("chest", box(0.07, 0.07, 0.05, FRAME, bev=0.008), T(0, 1.31, 0.195))
    rb.add("chest", box(0.07, 0.06, 0.05, FRAME, bev=0.008), T(0, 1.48, 0.19))
    rb.add("chest", cyl(0.052, 0.05, 8, FRAME, axis="z", bev=0.006, hollow=(0.012, 0.015)), T(0, 1.395, 0.2) @ Rd(0, 0, 22.5))
    rb.add("chest", cyl(0.036, 0.02, 8, GLOW, axis="z"), T(0, 1.395, 0.208) @ Rd(0, 0, 22.5))
    # back collar (protects the neck; head sits in front of it)
    rb.add("chest", box(0.26, 0.12 * E, 0.06, FRAME, bev=0.012, pan=[("-z", 0.014, -0.004)]),
           T(0, 1.535 + (0.03 if elite else 0.0), -0.165) @ Rd(-14, 0, 0))
    # back power pack: louvres + twin exhausts
    rb.add("chest", box(0.3, 0.27, 0.11, FRAME, bev=0.015), T(0, 1.4, -0.235))
    vent(rb, "chest", T(0, 1.39, -0.292) @ Rd(0, 180, 0), 0.2, 0.17, 5)
    for sx in (1, -1):
        rb.add("chest", cyl(0.028, 0.12, 8, FRAME, axis="y", hollow=(0.008, 0.03)), T(sx * 0.11, 1.56, -0.255))
        rb.add("chest", cyl(0.02, 0.01, 8, GLOW, axis="y"), T(sx * 0.11, 1.585, -0.255))
        rb.add("chest", box(0.04, 0.27, 0.12, SHELL, bev=0.01), T(sx * 0.155, 1.4, -0.235))
    # Aether corruption: crack leaking light across the left pectoral
    crack = [(0.07, 1.47), (0.095, 1.43), (0.085, 1.405), (0.12, 1.37), (0.11, 1.345), (0.15, 1.31)]
    rb.add("chest", tube([(x, y, 0.219 - (x - 0.1) * math.tan(math.radians(12))) for x, y in crack], 0.0055, GLOW, n=3))

    # ------------------------------------------------------------------ neck / head
    rb.add("neck", cyl(0.05, 0.11, 8, JOINT, axis="y"), T(0, 1.515, -0.03))
    for sx in (1, -1):
        rb.add("neck", cyl(0.013, 0.09, 6, FRAME, axis="y"), T(sx * 0.05, 1.51, -0.06))
    helm = [(-0.115, 1.55), (0.05, 1.54), (0.13, 1.58), (0.148, 1.655), (0.125, 1.735), (0.02, 1.765), (-0.09, 1.752), (-0.128, 1.68)]
    rb.add("head", prism(helm, 0.205, SHELL, axis="x", bev=0.014,
                         pan=[("+y", 0.025, -0.005), ("+x", 0.03, -0.005), ("-x", 0.03, -0.005)]))
    rb.add("head", box(0.215, 0.06, 0.05, FRAME, bev=0.008), T(0, 1.662, 0.138))            # visor band
    rb.add("head", box(0.165, 0.014, 0.012, GLOW), T(0, 1.663, 0.165))                     # visor slit
    rb.add("head", box(0.21, 0.028, 0.07, SHELL, bev=0.006), T(0, 1.703, 0.125) @ Rd(-18, 0, 0))   # brow
    rb.add("head", box(0.15, 0.055, 0.08, SHELL, bev=0.01, btaper=(0.8, 0.9)), T(0, 1.585, 0.105))  # jaw guard
    for x in (-0.035, 0.0, 0.035):
        rb.add("head", box(0.014, 0.035, 0.01, JOINT), T(x, 1.585, 0.146))
    for sx in (1, -1):
        rb.add("head", cyl(0.036, 0.026, 8, FRAME, axis="x", cap_inset=(0.012, -0.004)),
               (K.ID if sx > 0 else K.MIRROR_X) @ T(0.11, 1.655, 0.0))
    if not elite:
        rb.add("head", cyl(0.006, 0.13, 5, FRAME, axis="y"), T(-0.06, 1.8, -0.07) @ Rd(-12, 0, 0))
        rb.add("head", cyl(0.012, 0.02, 6, FRAME, axis="y"), T(-0.06, 1.745, -0.065))
    if elite:
        crest = [(0.115, 1.735), (0.06, 1.795), (-0.06, 1.845), (-0.165, 1.835), (-0.145, 1.735)]
        rb.add("head", prism(crest, 0.045, SHELL, axis="x", bev=0.008))
        cz = sum(p[0] for p in crest) / len(crest)
        cy = sum(p[1] for p in crest) / len(crest)
        inlay = [(cz + (z - cz) * 0.62, cy + (y - cy) * 0.5 + 0.012) for z, y in crest]
        rb.add("head", prism(inlay, 0.051, GLOW, axis="x"))                                  # glowing inlay through the fin

    # ------------------------------------------------------------------ arms
    for sd in ("L", "R"):
        rb.side(sd)
        ua, fa, hd, he = J["upperarm_L"], J["forearm_L"], J["hand_L"], J["handEnd_L"]
        # pauldron (chamfered faceted plate) on the clavicle
        Mp = T(ua + Vector((0.04, 0.08, 0.0))) @ R(0, 0, -0.25)
        pauld = [(-0.14, -0.06), (0.13, -0.1), (0.16, -0.02), (0.13, 0.065), (0.05, 0.105), (-0.07, 0.105), (-0.135, 0.06)]
        rb.add("clavicle_S", prism([(x * E, y * 0.85 * E) for x, y in pauld], 0.33 * E, SHELL, axis="z", bev=0.018,
                                   pan=[("+y", 0.022, -0.006)]), Mp)
        side_pl = [(-0.13, 0.05), (0.13, 0.05), (0.145, -0.02), (0.11, -0.09), (-0.11, -0.09), (-0.145, -0.02)]
        rb.add("clavicle_S", prism([(z * E, y * E) for z, y in side_pl], 0.025, SHELL, axis="x",
                                   pan=[("+x", 0.016, -0.004)]), Mp @ T(0.15 * E, -0.035 * E, 0.0) @ Rd(0, 0, -18))
        rb.add("clavicle_S", box(0.27 * E, 0.035, 0.29 * E, FRAME), Mp @ T(0.02, -0.105 * E, 0))
        rb.add("clavicle_S", box(0.2 * E, 0.03, 0.25 * E, SHELL), Mp @ T(0.05, -0.132 * E, 0) @ Rd(0, 0, -6))
        bolts(rb, "clavicle_S", Mp, [(x, 0.05, 0.166 * E) for x in (-0.05, 0.07)], r=0.01)
        if elite:
            rb.add("clavicle_S", prism([(-0.15, 0.09), (0.15, 0.09), (0.1, 0.15), (-0.12, 0.18)], 0.03, FRAME, axis="x"), Mp)
        # upper arm: frame strut, outer plate, bicep piston
        Mu = limb(ua, fa)
        rb.add("upperarm_S", sphere(0.08, JOINT, 8, 5), T(ua))
        rb.add("upperarm_S", cyl(0.055, 0.2, 8, FRAME, axis="y"), Mu @ T(0, -0.16, 0))
        rb.add("upperarm_S", prism(RIDGE(0.13 * E, 0.05), 0.18, SHELL, axis="y", bev=0.008, taper=1.08),
               Mu @ T(0.058, -0.15, 0.0) @ Rd(0, 90, 0))
        rb.add("upperarm_S", cyl(0.022, 0.12, 8, FRAME, axis="y"), Mu @ T(0.0, -0.1, 0.068))
        rb.add("upperarm_S", cyl(0.012, 0.11, 6, SHELL, axis="y"), Mu @ T(0.0, -0.2, 0.068))
        rb.add("upperarm_S", cyl(0.018, 0.03, 6, JOINT, axis="x"), Mu @ T(0.0, -0.035, 0.068))
        # forearm: elbow hinge + octagonal gauntlet + telegraph seam
        L = (hd - fa).length
        Mf = limb(fa, hd)
        rb.add("forearm_S", cyl(0.058, 0.12, 10, JOINT, axis="x"), Mf)
        rb.add("forearm_S", cyl(0.066, 0.022, 10, FRAME, axis="x", cap_inset=(0.02, -0.004)), Mf @ T(0.07, 0, 0))
        g = OCT(0.175 * E, 0.19 * E, 0.04 * E)
        rb.add("forearm_S", prism(g, 0.2, SHELL, axis="y", bev=0.012, taper=1.1,
                                  pan=[("+x", 0.016, -0.006), ("+z", 0.016, -0.006)]), Mf @ T(0.005, -0.145, 0.005))
        rb.add("forearm_S", box(0.15 * E, 0.11, 0.045, SHELL, bev=0.01), Mf @ T(0.0, -0.085, 0.105) @ Rd(-8, 0, 0))
        rb.add("forearm_S", prism(OCT(0.13, 0.13, 0.03), 0.035, FRAME, axis="y"), Mf @ T(0, -L + 0.03, 0))
        rb.add("forearm_S", box(0.02, 0.17, 0.05, JOINT), Mf @ T(0.092 * E, -0.145, 0.0))
        rb.add("forearm_S", box(0.01, 0.15, 0.022, GLOW), Mf @ T(0.1 * E, -0.145, 0.0))
        # hand: palm block, knuckle bar, two-segment fingers, thumb
        Mh = limb(hd, he)
        rb.add("hand_S", box(0.095, 0.1, 0.12, FRAME, bev=0.01), Mh @ T(-0.005, -0.055, 0.005))
        rb.add("hand_S", box(0.03, 0.09, 0.11, SHELL), Mh @ T(0.045, -0.055, 0.0))
        rb.add("hand_S", box(0.07, 0.03, 0.11, JOINT), Mh @ T(-0.01, -0.108, 0.005))
        for z in (-0.035, 0.0, 0.035):
            rb.add("hand_S", box(0.03, 0.05, 0.028, FRAME), Mh @ T(-0.012, -0.14, z) @ Rd(0, 0, -12))
            rb.add("hand_S", box(0.026, 0.045, 0.026, FRAME), Mh @ T(-0.03, -0.18, z) @ Rd(0, 0, -30))
        rb.add("hand_S", box(0.028, 0.06, 0.03, FRAME), Mh @ T(-0.04, -0.07, 0.07) @ Rd(30, 0, -20))

    # The right-forearm blade is a separate weapon model (blender/weapons -> Resources/Weapons/sentinel_blade.fbx),
    # attached to forearm_R at runtime by EnemyWeaponFx, so it can be baked, extend and break away on its own.

    if elite:
        # Warden: shield emitter on the left forearm + heavy mantle over the shoulders
        rb.side("L")
        fa, hd = J["forearm_L"], J["hand_L"]
        Ms = limb(fa, hd)
        Ms.translation = fa.lerp(hd, 0.5) + Vector((0.13, 0, 0))
        sh = [(-0.2, 0.2), (0.12, 0.25), (0.2, 0.17), (0.2, -0.17), (0.1, -0.25), (-0.17, -0.22)]
        rb.add("forearm_S", prism(sh, 0.05, SHELL, axis="x", bev=0.014, pan=[("+x", 0.03, -0.008)]), Ms)
        rb.add("forearm_S", box(0.05, 0.3, 0.06, FRAME), Ms @ T(-0.04, 0, 0.0))
        for y in (-0.13, 0.0, 0.13):
            rb.add("forearm_S", cyl(0.03, 0.02, 8, FRAME, axis="x"), Ms @ T(0.03, y, 0.02))
            rb.add("forearm_S", cyl(0.02, 0.012, 8, GLOW, axis="x"), Ms @ T(0.04, y, 0.02))
        rb.add("forearm_S", box(0.008, 0.36, 0.01, GLOW), Ms @ T(0.03, 0, -0.12))
        for Mx in (K.ID, K.MIRROR_X):
            rb.parts["chest"].add(box(0.2, 0.06, 0.32, SHELL, bev=0.014, pan=[("+y", 0.02, -0.005)]),
                                  Mx @ T(0.2, 1.585, -0.03) @ Rd(0, 0, -18))
            rb.parts["chest"].add(box(0.09, 0.16, 0.06, SHELL, bev=0.01), Mx @ T(0.13, 1.62, -0.165) @ Rd(-12, 0, -20))
        rb.parts["chest"].add(box(0.3, 0.05, 0.07, SHELL, bev=0.01, pan=[("+z", 0.012, -0.004)]), T(0, 1.29, 0.17) @ Rd(10, 0, 0))

    # ------------------------------------------------------------------ legs
    for sd in ("L", "R"):
        rb.side(sd)
        th, sn, ft = J["thigh_L"], J["shin_L"], J["foot_L"]
        Mt = limb(th, sn)
        rb.add("thigh_S", sphere(0.068, JOINT, 6, 4), T(th))                     # hidden inside the pelvis
        rb.add("thigh_S", prism(OCT(0.11, 0.12, 0.03), 0.3, FRAME, axis="y", taper=1.12), Mt @ T(0, -0.2, 0))
        rb.add("thigh_S", prism(RIDGE(0.14 * E, 0.065), 0.26, SHELL, axis="y", bev=0.01, taper=1.25,
                                pan=[("+z", 0.014, -0.005)]), Mt @ T(0.005, -0.2, 0.07) @ Rd(4, 0, 0))
        rb.add("thigh_S", box(0.035, 0.22, 0.13, SHELL, bev=0.008, pan=[("+x", 0.016, -0.005)]), Mt @ T(0.066, -0.2, -0.005))
        rb.add("thigh_S", cyl(0.02, 0.15, 8, FRAME, axis="y"), Mt @ T(0.02, -0.15, -0.07))
        rb.add("thigh_S", cyl(0.011, 0.14, 6, SHELL, axis="y"), Mt @ T(0.02, -0.29, -0.07))
        Ms = limb(sn, ft)
        rb.add("shin_S", cyl(0.055, 0.125, 10, JOINT, axis="x"), T(sn))
        knee = [(-0.03, 0.08), (0.05, 0.075), (0.085, 0.0), (0.06, -0.08), (-0.02, -0.06)]
        rb.add("shin_S", prism(knee, 0.14 * E, SHELL, axis="x", bev=0.012), Ms @ T(0, 0.0, 0.05))
        rb.add("shin_S", prism(RIDGE(0.13 * E, 0.15, 0.05, back=0.03), 0.29, SHELL, axis="y", bev=0.012, taper=1.3,
                               pan=[("+x", 0.02, -0.005), ("-x", 0.02, -0.005)]), Ms @ T(0, -0.22, 0.02))
        rb.add("shin_S", box(0.1, 0.25, 0.08, FRAME), Ms @ T(0, -0.19, -0.075))
        rb.add("shin_S", cyl(0.022, 0.17, 8, FRAME, axis="y"), Ms @ T(0, -0.13, -0.13))
        rb.add("shin_S", cyl(0.012, 0.16, 6, SHELL, axis="y"), Ms @ T(0, -0.29, -0.125))
        rb.add("shin_S", cyl(0.016, 0.04, 6, JOINT, axis="x"), Ms @ T(0, -0.05, -0.13))
        rb.add("shin_S", prism(OCT(0.13, 0.14, 0.03), 0.05, FRAME, axis="y"), Ms @ T(0, -0.385, 0.0))
        # foot: ankle hinge, sole, toe cap, instep, heel
        fx = ft.x
        rb.add("foot_S", cyl(0.042, 0.12, 8, JOINT, axis="x"), T(ft))
        sole = [(-0.11, 0.0), (0.2, 0.0), (0.235, 0.025), (0.2, 0.058), (0.09, 0.085), (-0.06, 0.095), (-0.115, 0.06)]
        rb.add("foot_S", prism(sole, 0.15 * E, FRAME, axis="x", bev=0.01), T(fx, 0, 0))
        rb.add("foot_S", box(0.16 * E, 0.05, 0.1, SHELL, bev=0.012, taper=(0.9, 0.7), pan=[("+y", 0.014, -0.004)]), T(fx, 0.05, 0.168))
        rb.add("foot_S", box(0.13 * E, 0.045, 0.12, SHELL, bev=0.01), T(fx, 0.093, 0.065) @ Rd(-22, 0, 0))
        rb.add("foot_S", box(0.12, 0.05, 0.05, JOINT), T(fx, 0.028, -0.1))
    return rb
