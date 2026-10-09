"""Kael texture layouts: garment masks/normals (Top, Pants atlases), armour, boots and gloves maps."""
import math
import numpy as np
import fabric as F
from fabric import Layer
from texbake import fbm3, vnoise3, worley3, hash3, smoothstep as ss
from gear import limb_coords, nrm


def _phi_torso(B, cy):
    return np.arctan2(B[:, 0], -(B[:, 1] - cy))


def top(t, L, T, names):
    """t: dict of texel arrays (P, N, B (body coords), A attrs, obj index, mpt). Returns Layer."""
    n = len(t["P"])
    Ly = Layer(n)
    P, N, B = t["P"], t["N"], t["B"]
    name = np.array(names)[t["obj"]]
    jacket = name == "Kael_Top"
    vest = name == "Kael_ChestRig"
    collar = name == "Kael_Collar"
    pouch = t["A"]["pouch"] > 0.5
    vest_panel = vest & ~pouch
    hips_z = L["Hips"][2]
    cy = L["Spine1"][1]
    x, y, z = B[:, 0], B[:, 1], B[:, 2]
    phi = _phi_torso(B, cy)
    r_t = 0.16
    shL, shR, elL, elR, wrL = L["LeftArm"], L["RightArm"], L["LeftForeArm"], L["RightForeArm"], L["LeftHand"]
    armL = (x > 0.2) & jacket
    armR = (x < -0.2) & jacket
    torso = jacket & ~armL & ~armR
    # ---------------- jacket: base fabric
    F.ripstop(Ly, P, N, jacket | collar)
    # yoke (shoulders, front/back) - accent, quilted
    zy = 1.425 + 0.01 * np.cos(phi * 2)
    dy = z - zy
    yoke = torso & (dy > 0)
    Ly.R = np.where(yoke, 1.0, Ly.R)
    Ly.G = np.maximum(Ly.G, 0.24 * yoke)   # charcoal, not black (readability)
    F.seam(Ly, dy, phi * r_t, mask=torso & (np.abs(x) < 0.27), stitch=(0.003, 0.006), stitch_side=1)
    F.panel_edge(Ly, dy, mask=torso, raise_=0.0012)
    F.quilt(Ly, x, z + np.abs(y) * 0.5, yoke & (np.abs(x) < 0.25), q=0.036, pad=0.0018)
    # side panels (stretch, ribbed) on the torso
    side_d = (np.abs(phi) - 1.3) * r_t
    side = torso & (side_d > 0) & (dy < 0)
    Ly.R = np.where(side, 1.0, Ly.R)
    Ly.G = np.maximum(Ly.G, 0.2 * side)
    F.seam(Ly, side_d, z, mask=torso & (dy < 0), stitch=(0.003,), stitch_side=-1)
    F.knit(Ly, P, N, side, period=0.004, amp=0.0002, axis=2)
    # diagonal closure (left collar -> right hip) with zipper and storm flap
    a = np.array((0.07, 1.52)); b = np.array((-0.13, hips_z - 0.02))
    ab = b - a
    q = np.stack([x, z], 1)
    tt = np.clip(((q - a) @ ab) / (ab @ ab), 0, 1)
    d_line = (q[:, 0] - (a[0] + tt * ab[0])) * (-ab[1]) / np.linalg.norm(ab) + (q[:, 1] - (a[1] + tt * ab[1])) * ab[0] / np.linalg.norm(ab)
    front = (N[:, 1] < -0.15) & (y < cy)
    along = tt * np.linalg.norm(ab)
    F.zipper(Ly, d_line + 0.006, along, mask=torso & front & (np.abs(d_line) < 0.03))
    F.seam(Ly, d_line - 0.012, along, mask=torso & front, stitch=(0.0035, 0.0065), stitch_side=-1)
    F.panel_edge(Ly, -(d_line - 0.012), mask=torso & front, raise_=0.0018, soft=0.006)  # storm flap
    Ly.B = np.maximum(Ly.B, np.exp(-((d_line - 0.012) / 0.002) ** 2) * (torso & front))
    # right chest vertical zip pocket
    pz = (np.abs(x + 0.1) < 0.0035 * 4) & (z > 1.27) & (z < 1.39)
    F.zipper(Ly, x + 0.1, z, mask=torso & front & (z > 1.27) & (z < 1.39), tape=0.006)
    # back: centre seam, princess seams, back yoke chevron
    back = torso & (y > cy)
    F.seam(Ly, x, z, mask=back & (dy < 0), stitch=(0.003,))
    for xs in (0.095, -0.095):
        F.seam(Ly, x - xs, z, mask=back & (dy < 0) & (z > hips_z + 0.05), stitch=(0.003,), stitch_side=int(np.sign(xs)))
    # hem band
    hem_d = z - (hips_z - 0.045 + (-0.04) * ss(-0.05, 0.08, y)) - 0.04
    Ly.R = np.where(torso & (hem_d < 0), 1.0, Ly.R)
    F.seam(Ly, hem_d, phi * r_t, mask=torso, stitch=(0.003, 0.006), stitch_side=1)
    F.knit(Ly, P, N, torso & (hem_d < 0), period=0.0035, amp=0.00018, axis=0)
    # ---------------- sleeves
    for arm, sh, el, wr, s_ in ((armL, shL, elL, wrL, 1), (armR, shR, elR, L["RightHand"], -1)):
        ta, pa, _ = limb_coords(B, sh, wr, (0, 0, 1))
        ua = np.linalg.norm(el - sh)
        # shoulder seam (raglan-ish ring)
        F.seam(Ly, ta - 0.035, pa * 0.05, mask=arm, stitch=(0.003, 0.006), stitch_side=1)
        # outer seam along the arm (glow strip runs here on the left)
        dph = (np.angle(np.exp(1j * (pa - math.pi / 2)))) * 0.05
        F.seam(Ly, dph, ta, mask=arm & (ta > 0.035), stitch=(0.0035,))
        if s_ > 0:
            Ly.B = np.maximum(Ly.B, np.exp(-(dph / 0.002) ** 2) * arm)
            # quilted elbow pad (outer/back side)
            de = np.hypot((ta - ua) / 0.075, np.angle(np.exp(1j * (pa - math.pi * 0.85))) / 1.1)
            pad = arm & (de < 1)
            Ly.R = np.where(pad, 1.0, Ly.R)
            F.seam(Ly, (1 - de) * 0.05, pa * 0.05, mask=arm & (de < 1.3), stitch=(0.003,), stitch_side=1)
            F.quilt(Ly, ta, pa * 0.05, pad, q=0.022, pad=0.0016)
            # forearm cuff panel
            cuf = arm & (ta > np.linalg.norm(wr - sh) - 0.085)
            Ly.R = np.where(cuf, 1.0, Ly.R)
            F.seam(Ly, ta - (np.linalg.norm(wr - sh) - 0.085), pa * 0.05, mask=arm, stitch=(0.003,), stitch_side=1)
            # upper-arm patch pocket with a velcro ID panel (blank) and flap
            du = np.abs(ta - 0.13) - 0.045
            dv = np.abs(np.angle(np.exp(1j * (pa - math.pi * 0.5)))) * 0.05 - 0.032
            pocket = arm & (du < 0) & (dv < 0)
            dpk = -np.maximum(du, dv)
            F.panel_edge(Ly, dpk, mask=arm & (dpk > -0.004), raise_=0.0015, soft=0.003)
            F.seam(Ly, dpk, ta + pa * 0.05, mask=arm & (np.abs(dpk) < 0.01), stitch=(0.003,), stitch_side=1)
            vel = pocket & (np.abs(ta - 0.14) < 0.022) & (np.abs(np.angle(np.exp(1j * (pa - math.pi * 0.5)))) * 0.05 < 0.022)
            F.velcro(Ly, P, vel)
            Ly.G = np.maximum(Ly.G, 0.08 * vel)
            # reflective trim tapes across the forearm
            for tb in (np.linalg.norm(wr - sh) - 0.11, np.linalg.norm(wr - sh) - 0.125):
                band = arm & (np.abs(ta - tb) < 0.0035)
                Ly.G = np.maximum(Ly.G, 0.7 * band)
                Ly.h += 0.0003 * band
        else:
            # right sleeve end cuff (above the elbow)
            end = 0.86 * ua
            cuf = arm & (ta > end - 0.05)
            Ly.R = np.where(cuf, 1.0, Ly.R)
            F.seam(Ly, ta - (end - 0.05), pa * 0.05, mask=arm, stitch=(0.003, 0.006), stitch_side=1)
            F.knit(Ly, P, N, cuf, period=0.0035, amp=0.00018, axis=0)
        # elbow / armpit wrinkles
        F.wrinkles(Ly, B, nrm(wr - sh), arm & (np.abs(ta - ua) < 0.08), wavelength=0.011, amp=0.0006, seed=s_)
        F.wrinkles(Ly, B, nrm(el - sh), arm & (ta < 0.09), wavelength=0.014, amp=0.0005, seed=s_ + 3)
    # waist wrinkles under the belt
    F.wrinkles(Ly, B, (0, 0, 1), torso & (z < hips_z + 0.16) & (z > hips_z + 0.02), wavelength=0.016, amp=0.0006, seed=2.0)
    # ---------------- collar: padded channels, bound top edge, accent
    if collar.any():
        Ly.R = np.where(collar, 1.0, Ly.R)
        Ly.G = np.maximum(Ly.G, 0.24 * collar)
        F.ripstop(Ly, P, N, collar)
        zc = P[:, 2]
        for k, zz in enumerate(np.arange(1.52, 1.64, 0.022)):
            F.seam(Ly, zc - zz, np.arctan2(P[:, 0], -P[:, 1]) * 0.07, mask=collar, stitch=(0.0025,), depth=0.0005)
        F.quilt(Ly, np.arctan2(P[:, 0], -P[:, 1]) * 0.07, zc, collar, q=0.022, pad=0.0012)
    # ---------------- vest (plate carrier): accent, MOLLE rows, edge binding
    if vest.any():
        Ly.R = np.where(vest, 1.0, Ly.R)
        # graphite carrier with lighter MOLLE panels so the torso reads in the dark scenes
        Ly.G = np.maximum(Ly.G, 0.3 * vest)
        Ly.G = np.maximum(Ly.G, 0.42 * (vest_panel & (z < 1.33) & (z > hips_z + 0.16)))
        F.ripstop(Ly, P, N, vest, cell=0.004, amp=0.0001)
        u_ = phi * 0.17
        F.molle(Ly, u_, z, vest_panel & (z < 1.33) & (z > hips_z + 0.16))
        # bound edges (lighter tape) near the vest openings: distance from the panel boundary via body z
        top_edge = vest_panel & (z > 1.41 - 0.04 * ss(0.1, 0.2, np.abs(x)))
        Ly.G = np.maximum(Ly.G, 0.58 * top_edge)
        bot_edge = vest_panel & (z < hips_z + 0.165)
        Ly.G = np.maximum(Ly.G, 0.58 * bot_edge)
        F.seam(Ly, z - 1.33, u_, mask=vest_panel, stitch=(0.003,), stitch_side=1)
        # vertical side seams of the carrier
        F.seam(Ly, (np.abs(phi) - 1.45) * 0.17, z, mask=vest_panel, stitch=(0.003,))
    # ---------------- pouches (fabric, both atlases use the same treatment)
    if pouch.any():
        Ly.R = np.where(pouch, 1.0, Ly.R)
        F.ripstop(Ly, P, N, pouch, cell=0.004, amp=0.0001)
        flap = t["A"]["pouch"] > 1.5
        Ly.G = np.maximum(Ly.G, 0.32 * pouch)
        Ly.G = np.maximum(Ly.G, 0.44 * flap)
    return Ly


def pants(t, L, T, names):
    n = len(t["P"])
    Ly = Layer(n)
    P, N, B = t["P"], t["N"], t["B"]
    name = np.array(names)[t["obj"]]
    pants = name == "Kael_Pants"
    pouch = t["A"]["pouch"] > 0.5
    x, y, z = B[:, 0], B[:, 1], B[:, 2]
    hips_z = L["Hips"][2]
    F.ripstop(Ly, P, N, pants | pouch, cell=0.006)
    # Main trouser fabric = accent (charcoal) by default so the jacket (outfit colour) contrasts.
    Ly.R = np.where(pants, 0.85, Ly.R)
    Ly.G = np.maximum(Ly.G, 0.2 * pants)   # graphite trousers (accent + trim), olive knee panels
    for s_, hp, kn, an in ((1, L["LeftUpLeg"], L["LeftLeg"], L["LeftFoot"]), (-1, L["RightUpLeg"], L["RightLeg"], L["LeftFoot"] * np.array((-1, 1, 1)))):
        leg = pants & (np.sign(x) == s_) & (z < hips_z - 0.04)
        tl, pl, _ = limb_coords(B, hp, an, (0, -1, 0))
        ul = np.linalg.norm(kn - hp)
        # outer seam and inseam
        outer = np.angle(np.exp(1j * (pl - s_ * math.pi / 2))) * 0.07
        inner = np.angle(np.exp(1j * (pl + s_ * math.pi / 2))) * 0.06
        F.seam(Ly, outer, tl, mask=leg, stitch=(0.003, 0.006), stitch_side=1)
        F.seam(Ly, inner, tl, mask=leg, stitch=(0.003,))
        # articulated knee panel (outfit colour) with darts and quilting
        dk = np.abs(tl - ul) - 0.085
        front = np.abs(np.angle(np.exp(1j * pl))) < 1.25
        kp = leg & (dk < 0) & front
        Ly.R = np.where(kp, 0.0, Ly.R)
        F.seam(Ly, -dk, pl * 0.07, mask=leg & front, stitch=(0.003, 0.006), stitch_side=1)
        F.seam(Ly, (np.abs(np.angle(np.exp(1j * pl))) - 1.25) * 0.07, tl, mask=leg & (dk < 0), stitch=(0.003,))
        F.quilt(Ly, pl * 0.07, tl, kp, q=0.03, pad=0.0018)
        for dz in (-0.03, 0.03):
            F.seam(Ly, tl - ul - dz, pl * 0.07, mask=kp, stitch=(), depth=0.0005)
        # back-of-knee and front-thigh wrinkles, stacking above the boots
        F.wrinkles(Ly, B, nrm(an - hp), leg & (np.abs(tl - ul) < 0.1), wavelength=0.012, amp=0.0007, seed=s_)
        F.wrinkles(Ly, B, nrm(an - hp), leg & (z < 0.42), wavelength=0.013, amp=0.0008, seed=s_ + 5)
        F.wrinkles(Ly, B, (0.5 * s_, 0, 0.8), leg & (z > hips_z - 0.2), wavelength=0.02, amp=0.0005, seed=s_ + 9)
        # thigh tape (trim)
        band = leg & (np.abs(tl - 0.17) < 0.004) & (np.abs(outer) < 0.05)
        Ly.G = np.maximum(Ly.G, 0.65 * band)
    # waistband and back yoke
    wb = pants & (z > L["Spine"][2] - 0.045)
    Ly.G = np.maximum(Ly.G, 0.36 * wb)
    F.seam(Ly, z - (L["Spine"][2] - 0.045), np.arctan2(x, -y) * 0.17, mask=pants, stitch=(0.003, 0.006), stitch_side=-1)
    back = pants & (y > 0.02) & (z > hips_z - 0.12)
    yk = z - (hips_z - 0.02 - np.abs(x) * 0.35)
    F.seam(Ly, yk, x, mask=back, stitch=(0.003, 0.006), stitch_side=1)
    F.seam(Ly, x, z, mask=back & (yk < 0), stitch=(0.003,))
    # crotch gusset
    gus = pants & (np.abs(x) < 0.05) & (z < hips_z - 0.04) & (z > hips_z - 0.16)
    Ly.R = np.where(gus, 0.0, Ly.R)
    if pouch.any():
        Ly.R = np.where(pouch, 0.0, Ly.R)
        flap = t["A"]["pouch"] > 1.5
        Ly.G = np.maximum(Ly.G, 0.1 * flap)
    return Ly


# ----------------------------------------------------------------------------- armour (painted plates)


def armor(t, ao):
    """Returns (basecolor RGB, height m, metallic, smoothness, paint mask) for the Armor atlas texels.
    BaseColor is a light neutral meant to be multiplied by the Armor tint in Unity; worn edges are bare metal."""
    n = len(t["P"])
    P = t["P"]
    A = t["A"]
    lx, ly, plate, wear, cav = A["lx"], A["ly"], A["plate"], A["wear"], A["cavity"]
    h = np.zeros(n, np.float32)
    seed = plate * 3.1
    chips = F.edge_wear(wear, P, 1.0, 1.0)
    scr = F.scratches(lx, ly, plate, density=90, seed=1.0)
    scr2 = F.scratches(lx, ly, plate + 100, density=40, seed=2.0, length=(0.01, 0.05), width=0.0004)
    # Panel details in plate space: vent slots and an abstract glyph block on some plates (no text).
    pid = np.round(plate).astype(int)
    vents = np.zeros(n, np.float32)
    glyph = np.zeros(n, np.float32)
    stripe = np.zeros(n, np.float32)
    for k in np.unique(pid):
        sel = pid == k
        if k in (1, 3, 7):  # chest plate, pauldron cap, knee: three slots
            for i in range(3):
                cx, cy = -0.02 + i * 0.012, -0.035 if k != 3 else 0.03
                d = np.maximum(np.abs(lx - cx) - 0.0025, np.abs(ly - cy) - 0.012)
                v = sel * (1 - ss(-0.0004, 0.0004, d))
                vents = np.maximum(vents, v)
        if k in (1, 3, 5):  # hazard chevrons in a corner (paint)
            u = lx * 0.7 + ly * 0.7
            stripe = np.maximum(stripe, sel * (np.sin(u / 0.006 * math.pi) > 0.2) * (lx > 0.03) * (ly < -0.025))
        if k in (1, 4, 6):  # abstract glyph strip: blocks of varying width (no letters)
            gx = np.floor((lx + 0.06) / 0.0045)
            on = hash3(np.stack([gx, gx * 0 + k, gx * 0], -1), 3.0) > 0.45
            glyph = np.maximum(glyph, sel * on * (np.abs(ly - 0.03) < 0.003) * (lx < 0.0) * (lx > -0.05))
    h -= 0.0012 * vents
    h -= 0.00012 * scr + 0.0002 * scr2
    h += 0.00004 * fbm3(P, 400.0, 3, 5.0)
    h -= 0.0006 * cav
    g = F.grime(P, ao, cav, 2.0)
    paint = np.clip(1 - chips - scr * 0.8, 0, 1)
    base_paint = 0.88 + 0.05 * fbm3(P, 60.0, 3, 1.0)
    # darker paint for stripes/glyphs
    base_paint = base_paint * (1 - 0.72 * np.clip(stripe + glyph, 0, 1))
    metal = 0.62 + 0.08 * fbm3(P, 200.0, 2, 4.0)
    col = paint * base_paint + (1 - paint) * metal
    col = col * (1 - 0.45 * g) * (1 - 0.5 * vents)
    rgb = np.stack([col, col * 0.995, col * 0.985], 1)
    metallic = np.clip(1 - paint, 0, 1)
    smooth = paint * (0.42 - 0.18 * g) + (1 - paint) * (0.62 - 0.2 * g)
    return rgb, h, metallic, smooth, paint


def boots(t, ao):
    n = len(t["P"])
    P, N = t["P"], t["N"]
    A = t["A"]
    sole = A["sole"] > 0.5
    strap = A["strap"] > 0.5
    h = np.zeros(n, np.float32)
    # leather grain (cellular) and creases over the toe flex
    cell = worley3(P, 420.0, 1.0)
    grain = (cell - 0.5)
    h += 0.00012 * grain * ~sole
    z = P[:, 2]
    crease = (z > 0.04) & (z < 0.1) & (N[:, 1] < -0.3)
    h += 0.0005 * np.sin(P[:, 1] / 0.006 * math.pi + fbm3(P, 40, 2, 3) * 3) * crease * ss(0.04, 0.06, z) * (1 - ss(0.08, 0.1, z))
    # panel seams: vamp (around the toe) and quarter/heel counter, with stitching
    yv = P[:, 1]
    xs = np.sign(P[:, 0])
    # stitch line around the upper just above the sole
    F_ = F.Layer(n)
    F.seam(F_, z - 0.05, np.arctan2(P[:, 0] - xs * 0.2, P[:, 1]) * 0.06, mask=~sole & ~strap, stitch=(0.0035,), stitch_side=1)
    F.seam(F_, z - 0.17, np.arctan2(P[:, 0] - xs * 0.2, P[:, 1]) * 0.06, mask=~sole & ~strap, stitch=(0.003, 0.006), stitch_side=1)
    # lacing on the front of the shaft: criss-cross laces (raised) between z 0.08 and 0.27
    front = (N[:, 1] < -0.55) & ~sole & ~strap & (z > 0.07) & (z < 0.28)
    lx = P[:, 0] - xs * 0.2
    lace = (np.abs(((z / 0.018) % 1.0) - 0.5) < 0.12) & (np.abs(lx) < 0.025)
    h += 0.0012 * lace * front
    F.seam(F_, np.abs(lx) - 0.03, z, mask=front, stitch=(0.003,), stitch_side=1)
    h += F_.h
    # sole: tread ribs on the side wall, rubber
    rib = np.sin(z / 0.004 * math.pi)
    h += 0.0004 * rib * sole * (N[:, 2] < 0.5)
    # webbing straps
    h += 0.00015 * np.sin(P[:, 2] / 0.0012 * math.pi) * strap
    g = F.grime(P, ao, np.zeros(n), 4.0)
    mud = ss(0.12, 0.02, z) * (0.5 + 0.5 * fbm3(P, 30, 3, 6))
    # readable in the dark URP scenes: dark-but-not-black leather, charcoal rubber, graphite webbing
    leather = np.array((0.29, 0.245, 0.205))
    rubber = np.array((0.19, 0.19, 0.2))
    webbing = np.array((0.25, 0.25, 0.245))
    base = np.where(sole[:, None], rubber, np.where(strap[:, None], webbing, leather))
    base = base * (1 + 0.15 * fbm3(P, 50, 3, 2)[:, None])
    scuff = ss(0.6, 0.8, fbm3(P, 90, 3, 9) * 0.5 + 0.5) * ~sole * (N[:, 1] < -0.3)
    base = base * (1 + 0.6 * scuff[:, None])
    base = base * (1 - 0.3 * g[:, None]) * (1 - 0.3 * F_.A[:, None])
    base = base * (1 - mud[:, None] * 0.25) + np.array((0.2, 0.18, 0.15)) * mud[:, None] * 0.25
    smooth = np.where(sole, 0.22, np.where(strap, 0.25, 0.48 - 0.25 * scuff)) * (1 - 0.4 * g)
    # moulded toe/heel caps: matte polymer with scuffed convex edges (baked curvature)
    cap = A.get("cap", np.zeros(n)) > 0.5
    if cap.any():
        curv = t.get("curv", np.zeros(n))
        sc_ = ss(0.25, 0.7, np.clip(curv, 0, 1) + 0.3 * fbm3(P, 120, 3, 4))
        base[cap] = (np.array((0.26, 0.26, 0.27)) * (1 + 0.6 * sc_[cap])[:, None]) * (1 - 0.3 * g[cap])[:, None]
        smooth = np.where(cap, 0.34 - 0.1 * sc_, smooth)
        h += 0.00002 * vnoise3(P, 2200.0, 5.0) * cap
    return base, h, np.zeros(n, np.float32), smooth


def gloves(t, ao, L):
    """Tactical gloves: synthetic-leather back with padded, stitched knuckle and finger segments, side seams along each
    finger, grippy dotted palm patch, reinforced thumb crotch, velcro wrist strap. Plates (Armor) paint separately."""
    import gear
    n = len(t["P"])
    P, N, B = t["P"], t["N"], t["B"]
    Ly = F.Layer(n)
    base = np.full(n, 0.72)
    rough_extra = np.zeros(n)
    leather = worley3(P, 650.0, 2.0)
    Ly.h += 0.00007 * (leather - 0.5)
    for s_ in (1, -1):
        side = np.sign(B[:, 0]) == s_
        if not side.any():
            continue
        wr, dors, fdir, mcp = gear.hand_frame(L, s_)
        el = np.asarray(L["LeftForeArm" if s_ > 0 else "RightForeArm"])
        dn = N @ dors
        along = (B - wr) @ fdir
        up_arm = (B - wr) @ nrm(el - wr)
        back = side & (dn > 0.25)
        palm = side & (dn < -0.25)
        edge = side & (np.abs(dn) <= 0.25)
        # knuckle pads: stitched rounded panels over each MCP joint, quilted back-of-hand panel
        for k_ in mcp:
            dk = np.linalg.norm(B - k_, axis=1)
            F.panel_edge(Ly, 0.011 - dk, mask=back, raise_=0.0009, soft=0.003)
            F.seam(Ly, dk - 0.011, np.arctan2(*(B - k_)[:, :2].T) * 0.011, mask=back & (dk < 0.016), stitch=(0.0022,), stitch_side=1, depth=0.0005)
            base = np.where(back & (dk < 0.011), base * 1.12, base)
        bh = back & (along > 0.0) & (along < 0.065) & (up_arm < 0.0)
        F.quilt(Ly, (B @ np.cross(dors, fdir)), along, bh, q=0.014, pad=0.0008, line=0.0008)
        # finger side seams (where the back and palm panels meet) and segment creases
        F.seam(Ly, dn * 0.008, along, mask=side & (along > 0.06) & (np.abs(dn) < 0.4), stitch=(0.0018,), depth=0.0005)
        cre = side & (along > 0.07)
        Ly.h -= 0.00035 * cre * (np.abs(np.sin(along / 0.026 * math.pi + 0.6)) < 0.12) * (dn < 0.3)
        # palm: grip patch with raised dots, reinforced heel of the hand and thumb crotch
        gp = palm & (along > 0.005) & (along < 0.075)
        dots = (np.abs(((B[:, 0] / 0.0035) % 1) - 0.5) < 0.22) & (np.abs(((B[:, 1] / 0.0035) % 1) - 0.5) < 0.22) & (np.abs(((B[:, 2] / 0.0035) % 1) - 0.5) < 0.3)
        Ly.h += 0.00025 * gp * dots
        F.seam(Ly, np.minimum(along - 0.005, 0.075 - along), B[:, 2] * 0.5, mask=palm & (along > -0.005) & (along < 0.085), stitch=(0.0025,), stitch_side=1)
        base = np.where(gp, base * 0.8, base)
        rough_extra = np.where(gp, 0.25, rough_extra)
        # wrist strap with velcro and a pull tab line
        strap_m = side & (up_arm > 0.005) & (up_arm < 0.03)
        F.velcro(Ly, P, strap_m & (dn > 0.0))
        F.seam(Ly, np.minimum(up_arm - 0.005, 0.03 - up_arm), along, mask=side & (up_arm > 0.0) & (up_arm < 0.035), stitch=(0.0018,), stitch_side=1, depth=0.0006)
        base = np.where(strap_m, base * 0.9, base)
        F.knit(Ly, P, N, side & (up_arm > 0.03), period=0.0028, amp=0.00015, axis=2)
    Ly.h += 0.00004 * fbm3(P, 300, 2, 4.0)
    g = F.grime(P, ao, np.zeros(n), 7.0)
    wear = ss(0.62, 0.8, fbm3(P, 120, 3, 9) * 0.5 + 0.5) * (Ly.h > 0.0004)
    col = base * (1 + 0.05 * fbm3(P, 70, 2, 3)) * (1 - 0.35 * g) * (1 - 0.3 * Ly.A) * (1 + 0.25 * wear)
    rgb = np.stack([col, col * 0.99, col * 0.97], 1)
    smooth = np.clip(0.42 - 0.15 * g - rough_extra * 0.6 - Ly.rough * 0.3 + 0.08 * wear, 0.08, 0.6)
    return rgb, Ly.h, np.zeros(n, np.float32), smooth
