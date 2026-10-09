"""Giva (asset id lyra) texture layouts: bodysuit + cropped bomber (Top atlas), leggings + thigh pouch (Pants atlas).
Armour, boots and gloves reuse the shared painters from paint_kael."""
import math
import numpy as np
import fabric as F
from fabric import Layer
from texbake import fbm3, smoothstep as ss
from gear import limb_coords, nrm
from paint_kael import armor, boots, gloves  # noqa: F401  (shared hard-surface painters)


def top(t, L, T, names):
    n = len(t["P"])
    Ly = Layer(n)
    P, N, B = t["P"], t["N"], t["B"]
    name = np.array(names)[t["obj"]]
    suit = name == "Lyra_Top"
    jacket = name == "Lyra_Jacket"
    collar = jacket & (t["A"]["collar"] > 0.5)
    jbody = jacket & ~collar
    x, y, z = B[:, 0], B[:, 1], B[:, 2]
    cy = L["Spine1"][1]
    phi = np.arctan2(x, -(y - cy))
    hips_z = L["Hips"][2]
    # ---------------- bodysuit: graphite (outfit colour) with asymmetric violet (accent) panels on the LEFT side
    side_l = suit & (x > 0) & (np.abs(phi) > 0.95) & (np.abs(phi) < 2.0)
    chev = suit & (y < cy) & (x > -0.02) & (np.abs((z - (L["Spine2"][2] + 0.03)) - 0.6 * x) < 0.016)
    # bodysuit uses the accent colour (dark by default in Unity); the asymmetric left panels are a lighter trim tone
    Ly.R = np.where(suit, 1.0, Ly.R)
    Ly.G = np.maximum(Ly.G, 0.16 * suit)   # dark violet-graphite, never flat black
    Ly.G = np.maximum(Ly.G, 0.36 * (side_l | chev))
    F.seam(Ly, (np.abs(phi) - 0.95) * 0.15, z, mask=suit & (x > 0), stitch=(0.0025,), depth=0.0005)
    F.seam(Ly, np.abs((z - (L["Spine2"][2] + 0.03)) - 0.6 * x) - 0.016, x, mask=suit & (y < cy) & (x > -0.02), stitch=(0.0025,), depth=0.0005)
    F.knit(Ly, P, N, suit, period=0.0022, amp=0.00009, axis=2)
    F.ripstop(Ly, P, N, suit, cell=0.0035, amp=0.00006)
    for xs in (0.07, -0.07):
        F.seam(Ly, x - xs, z, mask=suit & (y < cy), stitch=(0.0025,), stitch_side=int(np.sign(xs)), depth=0.0005)
    F.seam(Ly, (np.abs(phi) - 1.35) * 0.15, z, mask=suit, stitch=(0.0025,), depth=0.0005)
    neck_d = (L["LeftShoulder"][2] - 0.045 + 0.06 * ss(cy - 0.02, cy + 0.06, y)) - z
    pip = suit & (neck_d < 0.008)
    Ly.G = np.maximum(Ly.G, 0.45 * pip)
    F.seam(Ly, neck_d - 0.008, phi * 0.15, mask=suit, stitch=(0.003,), stitch_side=1)
    # abdominal panel (articulated ribs)
    abd = suit & (y < cy) & (np.abs(x) < 0.09) & (z > hips_z + 0.06) & (z < L["Spine2"][2] + 0.04)
    F.seam(Ly, ((z - hips_z) % 0.035) - 0.0175, x, mask=abd, stitch=(), depth=0.0004)
    Ly.h += 0.0004 * abd
    # ---------------- jacket: outfit colour, quilted shoulders, knit bands, open-front zip, raglan seams
    F.ripstop(Ly, P, N, jacket, cell=0.005, amp=0.00012)
    yoke = jbody & (z > 1.40 + 0.01 * np.cos(phi * 2))
    F.quilt(Ly, x, z + np.abs(y) * 0.5, yoke & (np.abs(x) < 0.27), q=0.03, pad=0.0018)
    F.seam(Ly, z - (1.40 + 0.01 * np.cos(phi * 2)), phi * 0.16, mask=jbody & (np.abs(x) < 0.26), stitch=(0.003, 0.006), stitch_side=1)
    Ly.R = np.where(yoke & (y > cy), 1.0, Ly.R)  # dark back yoke
    hem = jbody & (z < L["Spine2"][2] + 0.035 + 0.04) & (np.abs(x) < 0.24)
    Ly.R = np.where(hem, 1.0, Ly.R)
    F.knit(Ly, P, N, hem, period=0.003, amp=0.0002, axis=0)
    F.seam(Ly, z - (L["Spine2"][2] + 0.075), phi * 0.16, mask=jbody & (np.abs(x) < 0.24), stitch=(0.003,), stitch_side=1)
    # open front edges: zipper tapes
    for s_ in (1, -1):
        d = (x - s_ * (0.045 + 0.03 * ss(L["LeftShoulder"][2] - 0.1, L["LeftShoulder"][2], z))) * s_
        F.zipper(Ly, d - 0.005, z, mask=jbody & (y < cy) & (d < 0.02) & (d > -0.005), tape=0.008)
    # sleeves: raglan seam, rolled cuff band (knit, accent), sleeve pocket with a blank hex badge
    for sh, el, s_ in ((L["LeftArm"], L["LeftForeArm"], 1), (L["RightArm"], L["RightForeArm"], -1)):
        arm = jbody & (np.sign(x) == s_) & (np.abs(x) > 0.19)
        ta, pa, _ = limb_coords(B, sh, L["LeftHand"] if s_ > 0 else L["RightHand"], (0, 0, 1))
        ua = np.linalg.norm(el - sh)
        F.seam(Ly, ta - 0.03, pa * 0.05, mask=arm, stitch=(0.003, 0.006), stitch_side=1)
        cuff = arm & (ta > ua + 0.0)
        Ly.R = np.where(cuff, 1.0, Ly.R)
        F.knit(Ly, P, N, cuff, period=0.003, amp=0.0002, axis=0)
        F.seam(Ly, ta - (ua + 0.0), pa * 0.05, mask=arm, stitch=(0.003,), stitch_side=1)
        F.wrinkles(Ly, B, nrm(el - sh), arm & (ta > ua * 0.45), wavelength=0.012, amp=0.0006, seed=s_)
        if s_ > 0:
            hx = np.abs(ta - 0.12); hv = np.abs(np.angle(np.exp(1j * (pa - math.pi * 0.5)))) * 0.05
            hexd = np.maximum(hx * 0.866 + hv * 0.5, hv) - 0.02
            badge = arm & (hexd < 0)
            F.panel_edge(Ly, -hexd, mask=arm & (hexd < 0.003), raise_=0.0008, soft=0.002)
            Ly.G = np.maximum(Ly.G, 0.35 * badge)
            F.seam(Ly, hexd + 0.002, ta + pa * 0.05, mask=arm & (np.abs(hexd) < 0.006), stitch=(), depth=0.0004)
    # collar: knit accent band
    Ly.R = np.where(collar, 1.0, Ly.R)
    F.knit(Ly, P, N, collar, period=0.003, amp=0.0002, axis=2)
    F.wrinkles(Ly, B, (0, 0, 1), jbody & (np.abs(x) < 0.2) & (z < L["Spine2"][2] + 0.12), wavelength=0.016, amp=0.0005, seed=4)
    return Ly


def pants(t, L, T, names):
    n = len(t["P"])
    Ly = Layer(n)
    P, N, B = t["P"], t["N"], t["B"]
    name = np.array(names)[t["obj"]]
    legs = name == "Lyra_Pants"
    pouch = t["A"]["pouch"] > 0.5
    x, y, z = B[:, 0], B[:, 1], B[:, 2]
    hips_z = L["Hips"][2]
    Ly.R = np.where(legs, 1.0, Ly.R)
    Ly.G = np.maximum(Ly.G, 0.16 * legs)
    F.knit(Ly, P, N, legs, period=0.0022, amp=0.00008, axis=2)
    F.ripstop(Ly, P, N, legs | pouch, cell=0.0045, amp=0.00008)
    for s_, hp, kn, an in ((1, L["LeftUpLeg"], L["LeftLeg"], L["LeftFoot"]), (-1, L["RightUpLeg"], L["RightLeg"], L["RightFoot"])):
        leg = legs & (np.sign(x) == s_) & (z < hips_z - 0.03)
        tl, pl, _ = limb_coords(B, hp, an, (0, -1, 0))
        ul = np.linalg.norm(kn - hp)
        outer = np.angle(np.exp(1j * (pl - s_ * math.pi / 2))) * 0.065
        F.seam(Ly, outer - 0.012, tl, mask=leg, stitch=(0.0025,), depth=0.0005)
        F.seam(Ly, outer + 0.012, tl, mask=leg, stitch=(0.0025,), depth=0.0005)
        stripe = leg & (np.abs(outer) < 0.011)
        Ly.G = np.maximum(Ly.G, (0.4 if s_ > 0 else 0.22) * stripe)   # asymmetric: stronger panel on the left leg
        dk = np.abs(tl - ul) - 0.06
        front = np.abs(np.angle(np.exp(1j * pl))) < 1.1
        kp = leg & (dk < 0) & front
        F.seam(Ly, -dk, pl * 0.065, mask=leg & front, stitch=(0.003, 0.006), stitch_side=1)
        F.quilt(Ly, pl * 0.065, tl, kp, q=0.024, pad=0.0014)
        Ly.G = np.maximum(Ly.G, 0.3 * kp)
        F.wrinkles(Ly, B, nrm(an - hp), leg & (np.abs(tl - ul) < 0.08), wavelength=0.01, amp=0.0005, seed=s_)
    wb = legs & (z > L["Spine"][2] - 0.03)
    Ly.G = np.maximum(Ly.G, 0.2 * wb)
    F.seam(Ly, z - (L["Spine"][2] - 0.03), np.arctan2(x, -y) * 0.15, mask=legs, stitch=(0.003, 0.006), stitch_side=-1)
    if pouch.any():
        Ly.R = np.where(pouch, 0.0, Ly.R)
        Ly.G = np.maximum(Ly.G, 0.1 * (t["A"]["pouch"] > 1.5))
    return Ly
