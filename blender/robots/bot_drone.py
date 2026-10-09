"""Aether Drone (flying security drone, ~0.9 m pod + rotor booms). Metres, robot space (x = left, y = up, z = forward).

Contract (ROBOT_PARTS.md "Drone"): prefab root -> `body` (pivot = drone centre = aim point) -> `rotor_0..3` at 0.82 m
out at 45/135/225/315 deg, y 0.1, spun about local +Y by Drone.cs (localRotation is overwritten, so rotors have
identity rest rotation). Dark detail parts use the drone's dark shell colour, so the drone keeps the contract's
4 materials (shell / frame / glow / rotor) like the placeholder. Each rotor transform holds `prop_N` (blades, robot_frame) and `rotor_N_blur` (spin disc,
robot_rotor = transparent dark at runtime). Static parts (shell, ring, eye, visor, gun, under-glow, arms, fan ducts)
are one mesh on `body`. Angle convention as RobotBodies.BuildDrone: radial = (sin a, 0, cos a) in robot space.
"""
import math

from mathutils import Vector

import robokit as K
from robokit import FRAME, GLOW, ROTOR, SHELL, OCT, R, Rd, T, box, cyl, ico, lathe, prism, sphere, torus, tube
from bot_sentinel import bolts, vent


def build():
    rb = K.Robot("drone", None, skeleton=False)
    rb.special("body", None, Vector((0, 0, 0)))
    B = "body"
    ZS = K.Sc(1.0, 1.0, 1.1)          # pod is 10% longer front-to-back (placeholder ellipsoid 1 : 0.62 : 1.1)

    # ------------------------------------------------------------------ pod: armoured upper shell, darker lower hull
    upper = [(0.0, 0.262), (0.16, 0.25), (0.29, 0.2), (0.38, 0.12), (0.42, 0.03), (0.42, -0.01)]
    lower = [(0.405, -0.035), (0.37, -0.12), (0.28, -0.2), (0.15, -0.25), (0.0, -0.262)]
    rb.add(B, lathe(upper, 16, SHELL, math.pi / 16), ZS)
    rb.add(B, lathe(lower, 16, FRAME, math.pi / 16), ZS)
    rb.add(B, torus(0.414, 0.014, SHELL, n=16, m=4), ZS @ T(0, -0.022, 0))              # hull seam
    # raised dorsal hatch + panel strips
    rb.add(B, prism(OCT(0.24, 0.3, 0.06), 0.03, SHELL, axis="y", bev=0.008, pan=[("+y", 0.02, -0.004)]), T(0, 0.258, -0.03))
    for sx in (1, -1):
        rb.add(B, box(0.03, 0.02, 0.32, FRAME), T(sx * 0.15, 0.245, -0.02) @ Rd(0, 0, sx * -12))
        rb.add(B, box(0.12, 0.06, 0.02, SHELL), T(sx * 0.26, 0.12, -0.43) @ Rd(0, sx * 30, 0))   # rear vents
    rb.add(B, cyl(0.006, 0.18, 5, FRAME, axis="y"), T(-0.08, 0.34, -0.2) @ Rd(-20, 0, 0))       # antenna
    for sx in (1, -1):                                                                            # flank armour
        rb.add(B, box(0.035, 0.13, 0.34, SHELL, bev=0.008, pan=[("+x", 0.016, -0.004)]),
               T(sx * 0.39, 0.075, -0.03) @ Rd(0, 0, sx * 28))
    rb.add(B, box(0.3, 0.03, 0.13, SHELL, bev=0.008), T(0, 0.2, 0.33) @ Rd(24, 0, 0))             # brow over the eye
    rb.add(B, cyl(0.016, 0.03, 6, FRAME, axis="y"), T(-0.08, 0.262, -0.17))
    # rear exhaust
    rb.add(B, cyl(0.07, 0.08, 10, FRAME, axis="z", hollow=(0.015, 0.03)), T(0, -0.04, -0.47))
    rb.add(B, cyl(0.05, 0.01, 10, GLOW, axis="z"), T(0, -0.04, -0.495) @ Rd(0, 180, 0))

    # ------------------------------------------------------------------ sensor eye (glow) in a visor housing, facing +Z
    rb.add(B, cyl(0.2, 0.12, 16, FRAME, axis="z", bev=0.01, hollow=(0.03, 0.05)), T(0, 0.02, 0.38))
    rb.add(B, torus(0.16, 0.03, FRAME, n=16, m=6, axis="z"), T(0, 0.02, 0.44))
    rb.add(B, ico(0.12, GLOW, 2, scale=(1, 1, 0.65)), T(0, 0.02, 0.405))
    rb.add(B, torus(0.085, 0.01, SHELL, n=12, m=4, axis="z"), T(0, 0.02, 0.48))             # iris ring
    for sx in (1, -1):
        rb.add(B, cyl(0.016, 0.012, 6, GLOW, axis="z"), T(sx * 0.23, 0.08, 0.37) @ Rd(0, sx * 35, 0))
        rb.add(B, box(0.05, 0.13, 0.07, FRAME, bev=0.006), T(sx * 0.2, 0.0, 0.35) @ Rd(0, sx * 30, 0))   # cheek guards

    # ------------------------------------------------------------------ chin turret + gun barrel (+Z)
    rb.add(B, box(0.16, 0.08, 0.2, FRAME, bev=0.012), T(0, -0.2, 0.2))
    rb.add(B, cyl(0.06, 0.09, 10, SHELL, axis="x"), T(0, -0.2, 0.25))
    # the twin blaster itself is a separate weapon model (Resources/Weapons/drone_blaster.fbx) mounted on this chin
    # turret at runtime by EnemyWeaponFx (muzzle flashes, recoil, barrel glow)

    # ------------------------------------------------------------------ under-glow (scanner / lift emitter), facing down
    rb.add(B, torus(0.17, 0.022, FRAME, n=16, m=4), T(0, -0.262, 0))
    rb.add(B, cyl(0.16, 0.012, 16, GLOW, axis="y"), T(0, -0.262, 0))

    # ------------------------------------------------------------------ stabiliser ring (octagon of beams) + booms + fan ducts
    Rr = 0.58
    seg = 2 * Rr * math.tan(math.radians(22.5))
    for k in range(1, 7):             # open at the front (k = 0, 7) so the ring never crosses the eye / gun
        a = math.radians(22.5 + 45 * k)
        rb.add(B, prism(OCT(0.06, 0.09, 0.018), seg * 1.02, FRAME, axis="y", bev=0.004),
               R(0, a, 0) @ T(0, 0, Rr * math.cos(math.radians(22.5))) @ R(0, 0, math.pi / 2))
    for i in range(4):
        a = i / 4 * 2 * math.pi + math.pi / 4
        Ma = R(0, a, 0)                                   # local +z = radial (sin a, 0, cos a)
        rb.add(B, box(0.09, 0.06, 0.5, FRAME, bev=0.01, taper=(0.8, 1.0)), Ma @ T(0, 0.05, 0.55))      # boom
        rb.add(B, box(0.1, 0.1, 0.1, FRAME, bev=0.012), Ma @ T(0, 0.02, Rr))                            # ring joint
        rb.add(B, cyl(0.012, 0.42, 5, SHELL, axis="z"), Ma @ T(0.035, 0.085, 0.55))                     # power line
        rb.add(B, cyl(0.055, 0.1, 10, FRAME, axis="y", bev=0.006), Ma @ T(0, 0.045, 0.82))             # motor pod
        rb.add(B, cyl(0.03, 0.03, 8, SHELL, axis="y"), Ma @ T(0, 0.085, 0.82))
        rb.add(B, torus(0.25, 0.024, FRAME, n=16, m=4, rx=0.012), Ma @ T(0, 0.1, 0.82))                # fan duct
        for sa in (90, -90):
            rb.add(B, box(0.2, 0.02, 0.025, FRAME), Ma @ T(0, 0.07, 0.82) @ Rd(0, sa, 0) @ T(0.13, 0, 0))   # duct struts
        # rotor transform (spins) with blades + blur disc
        piv = Vector((math.sin(a) * 0.82, 0.1, math.cos(a) * 0.82))
        rn = "rotor_%d" % i
        rb.special(rn, B, piv)
        rb.special("prop_%d" % i, rn, piv)
        rb.special(rn + "_blur", rn, piv)
        rb.add("prop_%d" % i, cyl(0.03, 0.03, 8, FRAME, axis="y"), T(piv))
        for b in range(3):
            rb.add("prop_%d" % i, box(0.19, 0.006, 0.045, FRAME), T(piv) @ Rd(0, 120 * b + 15 * i, 0) @ T(0.11, 0, 0) @ Rd(14, 0, 0))
        rb.add(rn + "_blur", cyl(0.22, 0.004, 16, ROTOR, axis="y"), T(piv) @ T(0, 0.012, 0))
    return rb
