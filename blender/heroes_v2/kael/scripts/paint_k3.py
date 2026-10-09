"""Kael v3 textures: high-poly displacement fields (real quilting, ribbing, seams, folds baked to the game mesh) and
per-texel painters for the v3 outfit. Base colours keep a readable value range under night lighting (no near-black:
graphite fabrics sit around sRGB 0.2, polymer plates around 0.25 with lighter machined edges).

Uses the paint_k2 bake/atlas/raster/write helpers.
"""
import math
import numpy as np
import kcommon as K
from kcommon import ss, nrm
import texbake as TB
import fabric as FB
import gear
import paint_k2 as PK
from paint_k2 import limb, ring_folds, norm_ao, curvature, edge_distance, stitch_line, hem, panel
import outfit_k3 as O3


def _quilt_d(u, v, q):
    a = (u + v) / q
    b = (u - v) / q
    da = np.abs(a - np.round(a)) * q / 1.4142
    db = np.abs(b - np.round(b)) * q / 1.4142
    return np.minimum(da, db), np.where(da < db, (u - v), (u + v)) / 1.4142


def jacket_fields(L, P):
    """Shared region fields of the jacket (used by the high-poly displacement and the painter)."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    S = O3.SLEEVE
    sx = -O3.IS
    sh, el, wr = L[S + "Arm"], L[S + "ForeArm"], L[S + "Hand"]
    tu, ru, qu = limb(P, sh, el)
    tf, rf, qf = limb(P, el, wr)
    sleeve = (x * sx > 0.17) & (((tu > 0.04) & (ru < 0.12)) | ((tf > -0.05) & (rf < 0.1)))
    hemz = O3.jk_hem(y)
    band = (z < hemz + 0.045) & ~sleeve                      # ribbed hem band
    cuff = (x * sx > 0.3) & (tf > 0.74) & (rf < 0.1)
    quilt_top = np.where(y < 0, 1.2, 1.29)
    quilted = (z > quilt_top) & ~sleeve & ~band
    # front edge distance (open front), front region only
    front_e = np.where(y < -0.03, ax - O3.jacket_gap(z), 1.0)
    # quilting coordinates: across = x, up = z plus the run over the shoulder (mirrored at the shoulder seam y=0)
    u = x
    v = z + 0.85 * np.abs(y - 0.0)
    return dict(x=x, y=y, z=z, ax=ax, tu=tu, tf=tf, ru=ru, rf=rf, qu=qu, sleeve=sleeve, band=band, cuff=cuff, quilted=quilted,
                front_e=front_e, u=u, v=v, hemz=hemz)


Q = 0.05           # diamond cell (m): concept ~5 cm diamonds


def jacket_disp(L):
    def fn(P, N):
        F = jacket_fields(L, P)
        x, y, z, ax = F["x"], F["y"], F["z"], F["ax"]
        d = np.zeros(len(P))
        # --- diamond quilting: pillows with stitched valleys (real relief: ~3.5 mm)
        qd, along = _quilt_d(F["u"], F["v"], Q)
        qm = F["quilted"] * ss(0.004, 0.012, F["front_e"])
        pillow = ss(0.0, Q * 0.3, qd)
        d += 0.0048 * (pillow - 1.0) * qm
        d -= 0.001 * np.exp(-(qd / 0.0009) ** 2) * qm
        # --- plain lower panels: soft fabric undulation and waist blousing folds above the hem band
        plain = (~F["quilted"]) & (~F["band"]) & (~F["sleeve"])
        wz = ss(F["hemz"] + 0.04, F["hemz"] + 0.06, z) * (1 - ss(F["hemz"] + 0.11, F["hemz"] + 0.15, z))
        d += 0.0026 * wz * plain * np.sin((z / 0.022 + 0.7 * TB.fbm3(P, 10.0, 2, 3.0)) * 2 * math.pi) * (0.4 + 0.6 * ss(-0.2, 0.5, TB.fbm3(P, 12.0, 2, 4.0)))
        # --- panel seam between quilted and plain panels (welted, raised edge)
        qt = np.where(y < 0, 1.2, 1.29)
        sd = z - qt
        d += 0.0012 * np.exp(-((sd - 0.003) / 0.002) ** 2) * ~F["sleeve"] - 0.0011 * np.exp(-(sd / 0.0011) ** 2) * ~F["sleeve"]
        # --- side seams (x = +-0.17 at the flank) and centre back seam
        for sx in (1, -1):
            dd = (x - sx * 0.168) * (np.abs(y) < 0.06)
            d -= 0.0009 * np.exp(-(dd / 0.0012) ** 2) * (np.abs(y) < 0.06) * ~F["sleeve"]
        d -= 0.0008 * np.exp(-(x / 0.0012) ** 2) * (y > 0.04)
        # --- ribbed hem band and left cuff (knit ribs), seam at the band top
        around = np.arctan2(x, -y) * 0.16
        rib = np.sin(around / 0.0042 * 2 * math.pi)
        d += 0.0007 * rib * F["band"] + 0.0011 * ss(F["hemz"] + 0.045, F["hemz"] + 0.03, z) * F["band"] - 0.0014 * np.exp(-((z - F["hemz"] - 0.045) / 0.0014) ** 2) * ~F["sleeve"]
        ra = np.arctan2(F["qu"][:, 1], F["qu"][:, 0])
        d += 0.0006 * np.sin(ra * 18) * F["cuff"]
        # --- zipper tapes on both front edges: tape + teeth
        fe = F["front_e"]
        tape = (fe < 0.009) & (fe > -0.001) & (z > F["hemz"] + 0.002)
        teeth = (fe < 0.0035) * (0.5 + 0.5 * np.cos((z / 0.0048) * 2 * math.pi))
        d += 0.0006 * tape + 0.0009 * teeth * tape
        # piping cord just inside the zipper tape
        d += 0.0011 * np.exp(-((fe - 0.011) / 0.0016) ** 2) * (y < -0.03)
        # --- slanted welt pockets on the lower fronts
        for sx in (1, -1):
            a_ = np.array((sx * 0.135, -0.11, 1.175)); b_ = np.array((sx * 0.158, -0.1, 1.105))
            dd_, tt_ = TB.line_sdf2(x, z, a_[0], a_[2], b_[0], b_[2])
            m = (y < -0.04) & (np.sign(x) == sx)
            d += np.where(m, 0.0013 * np.exp(-((dd_ - 0.004) / 0.002) ** 2) - 0.0018 * np.exp(-(dd_ / 0.0011) ** 2), 0)
        # --- jacket sleeve: elbow compression folds, drag folds from the shoulder, wrist stacking above the cuff
        sh, el, wr = L[O3.SLEEVE + "Arm"], L[O3.SLEEVE + "ForeArm"], L[O3.SLEEVE + "Hand"]
        du = nrm(el - sh); df = nrm(wr - el)
        inner = df - du * (df @ du)
        sl = F["sleeve"]
        dd = ring_folds(P, sh, el, 0.6, 1.05, 0.026, 0.0034, side=inner, seed=1.0)
        dd += ring_folds(P, el, wr, -0.05, 0.35, 0.024, 0.003, side=inner, seed=3.0)
        dd += ring_folds(P, el, wr, 0.55, 0.74, 0.018, 0.0024, seed=5.0)
        dd += ring_folds(P, sh, el, 0.1, 0.5, 0.05, 0.0014, seed=7.0)
        d += dd * sl
        # sleeve seam along the back of the arm
        # armpit drag (both sides, torso)
        for s_ in (1, -1):
            c = np.array((s_ * 0.17, 0.0, 1.36))
            g = np.exp(-np.sum(((P - c) / np.array((0.07, 0.12, 0.08))) ** 2, 1))
            d += np.where(np.sign(x) == s_, 0.0016 * g * np.sin(((z - 1.36) * 0.8 + (ax - 0.17) * 0.6) / 0.02 * 2 * math.pi), 0) * ~F["quilted"]
        d += 0.0003 * TB.fbm3(P, 60.0, 3, 13.0)
        return d
    return fn


def collar_disp(L):
    def fn(P, N):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        rad = P[:, :2] - np.array((0.0, -0.014))
        rad /= np.maximum(np.linalg.norm(rad, axis=1, keepdims=True), 1e-6)
        inner = (rad * N[:, :2]).sum(1) < 0
        ang = np.arctan2(x, -(y + 0.014)) * 0.09
        d = np.zeros(len(P))            # concept: smooth black collar (no rib knit inside)
        # outer: two topstitch channels parallel to the top edge, soft creases
        top = O3.JK_NECK + O3.COLLAR_TOP + 0.04 * (0.5 - 0.5 * np.cos(np.arctan2(x, -(y + 0.014))))
        dz = top - z
        d += np.where(~inner, -0.0006 * np.exp(-((dz - 0.012) / 0.0009) ** 2) - 0.0006 * np.exp(-((dz - 0.05) / 0.0009) ** 2), 0)
        d += np.where(~inner, 0.0012 * np.sin((ang / 0.03 + 0.5 * TB.fbm3(P, 14.0, 2, 2.0)) * 2 * math.pi) * ss(0.06, 0.02, dz) * 0.5, 0)
        d += 0.0003 * TB.fbm3(P, 70.0, 3, 6.0)
        return d
    return fn


def paint_jacket(T, t, objs, L, nbake, ao):
    """Cloth_Jacket: graphite ripstop nylon (satin), quilted with tonal stitching, knit rib trims, gunmetal zips,
    grey piping along the front edges. Returns (rgb, h, metal, smooth, paint) in sRGB."""
    P, N = t["P"], t["N"]
    n = len(P)
    names = [o.name for o in objs]
    oid = t["obj"]
    is_col = oid == names.index("Collar") if "Collar" in names else np.zeros(n, bool)
    F = jacket_fields(L, P)
    x, y, z = F["x"], F["y"], F["z"]
    ao_t = norm_ao(ao, t, 0.0)
    curv = curvature(T, t, nbake)
    h = np.zeros(n)
    # concept: matte black quilted bomber (sRGB ~0.05 base; the quilting reads through soft grey sheen on the pillows)
    base = np.array((0.052, 0.054, 0.058))
    var = 0.03 * TB.fbm3(P, 9.0, 3, 1.0) + 0.012 * TB.fbm3(P, 45.0, 2, 2.0)
    rgb = base[None] * (1 + var[:, None])
    smooth = np.full(n, 0.22)
    metal = np.zeros(n)
    # ripstop weave micro relief + sheen variation
    Ly = FB.Layer(n)
    FB.ripstop(Ly, P, N, 1.0, cell=0.0052, amp=0.00006)
    h += Ly.h
    # quilting: tonal stitching thread on the valleys (slightly lighter, dashed)
    qd, along = _quilt_d(F["u"], F["v"], Q)
    qm = F["quilted"] * ss(0.004, 0.012, F["front_e"]) * ~is_col
    valley = np.exp(-(qd / 0.0011) ** 2) * qm
    dash = ((along / 0.0032) % 1.0) < 0.6
    rgb = rgb * (1 - 0.45 * valley[:, None]) * (1 + 0.5 * (valley * dash * (qd < 0.0004))[:, None])
    smooth = smooth - 0.1 * valley
    # pillow crests catch light (puffed nylon has a soft sheen on top)
    pil = ss(Q * 0.1, Q * 0.3, qd) * qm
    rgb = rgb * (1 + 0.28 * pil[:, None])
    smooth = smooth + 0.1 * pil
    # knit rib trims: hem band, left cuff, collar inner face
    rad = P[:, :2] - np.array((0.0, -0.014))
    rad /= np.maximum(np.linalg.norm(rad, axis=1, keepdims=True), 1e-6)
    col_inner = is_col & ((rad * N[:, :2]).sum(1) < 0)
    knit = ((F["band"] | F["cuff"]) & ~is_col)
    rgb = np.where(knit[:, None], np.array((0.062, 0.064, 0.068))[None] * (1 + 0.5 * var[:, None]), rgb)
    smooth = np.where(knit, 0.18, smooth)
    # zipper: gunmetal teeth on dark tape; grey piping inside it
    fe = F["front_e"]
    tape = (fe < 0.009) & (fe > -0.001) & (z > F["hemz"] + 0.002) & ~is_col
    teeth = tape & (fe < 0.0035)
    rgb = np.where(tape[:, None], np.array((0.07, 0.072, 0.076))[None], rgb)
    rgb = np.where(teeth[:, None], np.array((0.3, 0.31, 0.33))[None], rgb)
    metal = np.where(teeth, 0.9, metal); smooth = np.where(teeth, 0.62, np.where(tape, 0.3, smooth))
    pip = np.exp(-((fe - 0.011) / 0.002) ** 2) * (y < -0.03) * ~is_col
    rgb = rgb * (1 - pip[:, None]) + np.array((0.24, 0.245, 0.255))[None] * pip[:, None]
    # piping along the quilt/plain panel seam and along the collar top edge
    qt = np.where(y < 0, 1.2, 1.29)
    pp = np.exp(-((z - qt - 0.003) / 0.0018) ** 2) * ~F["sleeve"] * ~is_col
    rgb = rgb * (1 - 0.7 * pp[:, None]) + 0.7 * np.array((0.2, 0.205, 0.215))[None] * pp[:, None]
    ctop = O3.JK_NECK + O3.COLLAR_TOP + 0.04 * (0.5 - 0.5 * np.cos(np.arctan2(x, -(y + 0.014))))
    cp = np.exp(-((ctop - z) / 0.003) ** 2) * is_col
    rgb = rgb * (1 - 0.6 * cp[:, None]) + 0.6 * np.array((0.2, 0.205, 0.215))[None] * cp[:, None]
    # stitch lines along all openings
    ed = edge_distance(T, t, objs)
    hm = FB.Layer(n)
    hem(hm, ed, P, 1.0, band=0.01, stitch=(0.005,))
    h += hm.h
    rgb = rgb * (1 + 0.35 * hm.G[:, None])
    # woven name tape / glyph patch on the jacket sleeve (invented glyphs), lighter grey
    if True:
        sh, el = L[O3.SLEEVE + "Arm"], L[O3.SLEEVE + "ForeArm"]
        c = sh + (el - sh) * 0.3
        du = nrm(el - sh)
        ov = np.array((-O3.IS, -0.35, 0.3))
        outv = nrm(ov - du * (ov @ du))
        pc = c + outv * 0.055
        q = P - pc
        lx = q @ nrm(np.cross(du, outv)); ly = q @ (-du)
        patch = (np.abs(lx) < 0.026) & (np.abs(ly) < 0.016) & F["sleeve"]
        g = PK.glyphs(lx, ly, -0.022, -0.006, 0.044, 0.012, seed=31, cells=5) * patch
        rgb = np.where(patch[:, None], np.array((0.1, 0.104, 0.11))[None], rgb)
        rgb = rgb * (1 - g[:, None]) + g[:, None] * np.array((0.46, 0.47, 0.49))[None]
        h += 0.0002 * patch
    # wear: lighter scuffing on convex crests (cuffs, hem, collar edge), dust low
    wear = np.clip(curv, 0, 1) * (0.5 + 0.5 * ss(-0.2, 0.6, TB.fbm3(P, 30.0, 2, 8.0)))
    rgb = rgb * (1 + 0.15 * wear[:, None])
    # ambient occlusion into the albedo (quilting valleys, under collar, armpits)
    rgb = rgb * (0.45 + 0.55 * ao_t[:, None])
    smooth = smooth * (0.75 + 0.25 * ao_t)
    return np.clip(rgb, 0, 1), h, metal, np.clip(smooth, 0.08, 0.8), np.zeros(n)


# ============================================================================= Garment_Top: olive undersuit with a ribbed turtleneck


def suit_disp(L):
    def fn(P, N):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        d = np.zeros(len(P))
        neck = ss(1.562, 1.572, z)
        seg = ((z - 1.566) / 0.0125) % 1.0
        d += neck * (0.0016 * ss(0.0, 0.15, seg) * (1 - ss(0.75, 1.0, seg)) - 0.0004)      # segmented neck guard
        # interface-arm sleeve: elbow folds, upper-arm drag
        S = O3.IFACE
        sh, el, wr = L[S + "Arm"], L[S + "ForeArm"], L[S + "Hand"]
        du = nrm(el - sh); df = nrm(wr - el)
        inner = df - du * (df @ du)
        side = x * O3.IS > 0.15
        dd = ring_folds(P, sh, el, 0.6, 1.05, 0.024, 0.003, side=inner, seed=11.0)
        dd += ring_folds(P, el, wr, -0.05, 0.3, 0.022, 0.0026, side=inner, seed=13.0)
        dd += ring_folds(P, sh, el, 0.05, 0.45, 0.045, 0.0014, seed=17.0)
        d += np.where(side, dd, 0)
        # torso: waist creases
        wz = ss(1.0, 1.05, z) * (1 - ss(1.14, 1.2, z))
        brk = 0.3 + 0.7 * ss(-0.3, 0.5, TB.fbm3(P, 9.0, 2, 22.0))
        d += 0.0012 * wz * brk * np.sin((z / 0.024 + 1.1 * TB.fbm3(P, 7.0, 2, 21.0) + 0.6 * x / 0.05) * 2 * math.pi)
        d += 0.0003 * TB.fbm3(P, 60.0, 3, 23.0)
        return d
    return fn


def paint_suit(T, t, objs, L, nbake):
    """Garment_Top mask for the under-suit: black (accent) body and segmented neck, olive (primary) sleeve on the
    interface arm with an articulated elbow patch."""
    P, N = t["P"], t["N"]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    n = len(P)
    Ly = FB.Layer(n)
    ed = edge_distance(T, t, objs)
    along = x * 0.6 + y * 0.4 + z * 0.8
    FB.ripstop(Ly, P, N, 1.0, cell=0.0056, amp=0.0001)
    Ly.R[:] = 1.0
    S = O3.IFACE
    sh, el, wr = L[S + "Arm"], L[S + "ForeArm"], L[S + "Hand"]
    tu, ru, qu = limb(P, sh, el)
    tf, rf, qf = limb(P, el, wr)
    arm = (x * O3.IS > 0.17) & (((tu > 0.0) & (ru < 0.11)) | ((tf > -0.1) & (rf < 0.1)))
    Ly.R = np.where(arm, 0.0, Ly.R)
    panel(Ly, (tu - 0.06) * np.linalg.norm(el - sh), mask=arm.astype(float) * (tu < 0.3), along=along * 2, R_val=None)
    du = nrm(el - sh); df = nrm(wr - el)
    inner = nrm(df - du * (df @ du))
    elbow_d = np.linalg.norm(P - (el - inner * 0.035), axis=1)
    em = panel(Ly, 0.05 - elbow_d, mask=arm.astype(float), along=along, R_val=0.6)
    FB.quilt(Ly, tu * 0.3, qu @ nrm(np.cross(du, inner)), em, q=0.018, pad=0.0012)
    # segmented neck: horizontal ridges with dark gaps (concept)
    neck = ss(1.556, 1.566, z)
    seg = ((z - 1.566) / 0.0125) % 1.0
    Ly.A = np.maximum(Ly.A, 0.55 * neck * (1 - ss(0.0, 0.12, seg)) * ss(1.57, 1.575, z))
    Ly.G = np.maximum(Ly.G, 0.12 * neck * ss(0.3, 0.5, seg) * (1 - ss(0.6, 0.85, seg)))
    panel(Ly, z - 1.561, mask=1.0, along=along, R_val=None)
    front = (y < -0.06) & (z < 1.2) & (z > 1.0)
    FB.zipper(Ly, x - 0.0, z, front * (np.abs(x) < 0.01))
    hem(Ly, ed, P, 1.0)
    if nbake is not None:
        c = curvature(T, t, nbake)
        Ly.A = np.maximum(Ly.A, np.clip(-c * 0.35, 0, 0.35))
    return Ly


# ============================================================================= Garment_Pants: cargo trousers


def pants_disp(L):
    base = PK.pants_disp(L)

    def fn(P, N):
        d = base(P, N)
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        for s, S in ((1, "Left"), (-1, "Right")):
            hp, kn, an = L[S + "UpLeg"], L[S + "Leg"], L[S + "Foot"]
            side = np.sign(x) == s
            # piping cord: hip-front down to the inner knee (concept) and the outer side panel edge
            a_ = hp + np.array((s * 0.02, -0.1, 0.02)); b_ = kn + np.array((-s * 0.035, -0.08, 0.06))
            dd_, tt_ = TB.line_sdf2(x, z, a_[0], a_[2], b_[0], b_[2])
            m = side & (y < -0.02)
            d += np.where(m, 0.0011 * np.exp(-(dd_ / 0.0016) ** 2) - 0.0005 * np.exp(-((dd_ - 0.003) / 0.001) ** 2), 0)
            # side panel boundary (front edge of the outer panel)
            tl, rl, ql = limb(P, hp, an)
            lat = np.array((s * 1.0, 0, 0))
            phi = np.arctan2(ql @ np.array((0, -1.0, 0)), ql @ lat)
            dseam = (phi - 0.55) * np.maximum(rl, 0.01)
            d += np.where(side & (z < 1.0) & (z > 0.5), 0.0010 * np.exp(-(dseam / 0.0016) ** 2), 0)
            # knee: articulated darts
            kz = z - kn[2]
            kd = side & (y < 0.0) & (np.abs(kz) < 0.07)
            d += np.where(kd, 0.0012 * np.sin(kz / 0.017 * 2 * math.pi) * (1 - np.abs(kz) / 0.07), 0)
            # vertical drape folds down the front/back of the thigh and the shin (cargo cut hangs)
            ang = np.arctan2(ql @ np.array((0, -1.0, 0)), ql @ lat)
            dr = np.sin(ang * 5.0 + 1.6 * TB.fbm3(P * np.array((1, 1, 0.25)), 6.0, 2, 31.0 + s)) * (0.4 + 0.6 * ss(-0.3, 0.4, TB.fbm3(P, 5.0, 2, 33.0 + s)))
            d += np.where(side & (z < 0.95) & (z > 0.3), 0.0024 * dr, 0)
        # bloused into the boots: soft stacked folds over the calf just above / inside the boot top
        for s, S in ((1, "Left"), (-1, "Right")):
            side = np.sign(x) == s
            kz = z - L[S + "Leg"][2]
            bl = side & (kz < -0.02) & (kz > -0.11)
            d += np.where(bl, 0.0022 * np.sin((kz / 0.016 + 0.6 * TB.fbm3(P, 9.0, 2, 51.0 + s)) * 2 * math.pi)
                          * ss(-0.11, -0.07, kz) * ss(-0.02, -0.05, kz), 0)
        d += 0.00025 * TB.fbm3(P, 80.0, 3, 41.0)
        return d
    return fn


def paint_pants(T, t, objs, L, nbake):
    P, N = t["P"], t["N"]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    n = len(P)
    A = t["A"]
    pouch = np.round(A.get("pouch", np.zeros(n))).astype(int)
    Ly = FB.Layer(n)
    ed = edge_distance(T, t, objs)
    along = x * 0.6 + y * 0.4 + z * 0.8
    FB.ripstop(Ly, P, N, 1.0, cell=0.0062, amp=0.0001)
    for s, S in ((1, "Left"), (-1, "Right")):
        hp, kn, an = L[S + "UpLeg"], L[S + "Leg"], L[S + "Foot"]
        side = (np.sign(x) == s) & (pouch == 0)
        # trim piping hip-front -> inner knee
        a_ = hp + np.array((s * 0.02, -0.1, 0.02)); b_ = kn + np.array((-s * 0.035, -0.08, 0.06))
        dd_, tt_ = TB.line_sdf2(x, z, a_[0], a_[2], b_[0], b_[2])
        pip = np.exp(-(dd_ / 0.0022) ** 2) * side * (y < -0.02)
        Ly.G = np.maximum(Ly.G, 0.36 * pip)
        Ly.A = np.maximum(Ly.A, 0.3 * np.exp(-((dd_ - 0.004) / 0.0012) ** 2) * side * (y < -0.02))
        # outer side panel in the accent colour (hip to knee), trim piping on its front edge
        tl, rl, ql = limb(P, hp, an)
        lat = np.array((s * 1.0, 0, 0))
        phi = np.arctan2(ql @ np.array((0, -1.0, 0)), ql @ lat)
        dseam = (phi - 0.55) * np.maximum(rl, 0.01)
        inside = side & (dseam < 0) & (phi > -1.2) & (z < 1.0) & (z > 0.52)
        Ly.R = np.where(inside, np.maximum(Ly.R, 0.85 * ss(0.5, 0.56, z)), Ly.R)
        pp = np.exp(-(dseam / 0.0022) ** 2) * side * (z < 1.0) * (z > 0.52)
        Ly.G = np.maximum(Ly.G, 0.34 * pp)
        # knee darts
        kz = z - kn[2]
        kd = side & (y < 0.0) & (np.abs(kz) < 0.07)
        Ly.A = np.maximum(Ly.A, 0.35 * kd * ss(0.6, 0.95, np.abs(np.sin(kz / 0.017 * 2 * math.pi))))
        # outseam stitch
        lat0 = np.arctan2(ql @ np.array((0, -1.0, 0)), ql @ lat) * np.maximum(rl, 0.01)
        stitch_line(Ly, lat0 - 0.004, z, side * (z < 1.0) * (np.abs(lat0) < 0.008))
    # cargo pockets: body olive, flap edge darker, stitched borders, snaps trim
    pz = pouch > 0
    Ly.A = np.where(pz, np.maximum(Ly.A, 0.12), Ly.A)
    flap = pouch == 2
    Ly.R = np.where(flap, 0.25, Ly.R)
    Ly.G = np.where(pz & (np.round(A.get("wear", np.zeros(n))) > 0.5), 0.9, Ly.G)
    # seat yoke seam
    sy = 0.98 - 0.03 * ss(0.0, 0.12, np.abs(x))
    panel(Ly, (z - sy) * (y > 0.0), mask=(y > 0.0).astype(float) * (z > 0.9) * (pouch == 0), along=along, R_val=None)
    hem(Ly, ed, P, 1.0, band=0.01)
    if nbake is not None:
        c = curvature(T, t, nbake)
        Ly.A = np.maximum(Ly.A, np.clip(-c * 0.4, 0, 0.4))
    return Ly


# ============================================================================= Cloth_Gear: carrier, placard, pouches, belt, straps


def paint_gear(T, t, objs, nbake, ao):
    P, N = t["P"], t["N"]
    A = t["A"]
    n = len(P)
    pouch = np.round(A.get("pouch", np.zeros(n))).astype(int)
    strap = A.get("strap", np.zeros(n)) > 0.5
    vest = A.get("vest", np.zeros(n)) > 0.5
    ao_t = norm_ao(ao, t, 0.0)
    curv = curvature(T, t, nbake)
    names = [o.name for o in objs]
    oid = t["obj"]
    h = np.zeros(n)
    cordura = np.array((0.075, 0.077, 0.082))
    var = 0.05 * TB.fbm3(P, 12.0, 3, 2.0) + 0.02 * TB.fbm3(P, 60.0, 2, 3.0)
    rgb = cordura[None] * (1 + var[:, None])
    smooth = np.full(n, 0.3)
    Ly = FB.Layer(n)
    FB.ripstop(Ly, P, N, 1.0, cell=0.0032, amp=0.00012)
    h += Ly.h
    # webbing: belt band, straps (tighter weave, slightly darker)
    wv = np.sin(P[:, 0] / 0.0008 * math.pi) * np.sin(P[:, 2] / 0.0011 * math.pi)
    web = strap | (oid == names.index("Belt") if "Belt" in names else np.zeros(n, bool)) & (pouch == 0)
    rgb = np.where(web[:, None], np.array((0.085, 0.087, 0.09))[None] * (1 + 0.08 * wv[:, None]), rgb)
    h += np.where(web, 0.0001 * wv, 0)
    smooth = np.where(web, 0.26, smooth)
    # vest: MOLLE rows on the visible lower front / sides, bound edges (lighter binding tape)
    if vest.any():
        Lm = FB.Layer(n)
        vm = vest.astype(float) * (P[:, 2] > 1.16) * (P[:, 2] < 1.32)
        FB.molle(Lm, P[:, 0], P[:, 2] - 1.165, vm, row=0.032, band=0.022, tack=0.036, height=0.0016)
        h += Lm.h
        rgb = rgb * (1 - 0.5 * Lm.A[:, None])
        ed = edge_distance(T, t, objs)
        bind = vest & (ed < 0.008)
        rgb = np.where(bind[:, None], np.array((0.13, 0.133, 0.14))[None], rgb)
    # pouches: body black cordura, side flaps black, centre flap olive-grey (concept), placard panel
    rgb = np.where((pouch == 3)[:, None], np.array((0.27, 0.285, 0.22))[None] * (1 + var[:, None]), rgb)
    rgb = np.where((pouch == 4)[:, None], np.array((0.07, 0.072, 0.077))[None] * (1 + var[:, None]), rgb)
    rgb = np.where((pouch == 1)[:, None] | (pouch == 2)[:, None], np.array((0.068, 0.07, 0.075))[None] * (1 + var[:, None]), rgb)
    # convex edges: binding tape catches light; scuffs
    edge = np.clip(curv, 0, 1)
    rgb = rgb * (1 + 0.35 * edge[:, None])
    rgb = rgb * (0.42 + 0.58 * ao_t[:, None])
    smooth = smooth * (0.8 + 0.2 * ao_t)
    return np.clip(rgb, 0, 1), h, np.zeros(n), np.clip(smooth, 0.08, 0.8), np.zeros(n)


# ============================================================================= Armor: dark satin polymer (zone 3) gets real value range


def paint_armor(T, t, objs, nbake, ao):
    rgb, h, metal, smooth, paint = PK.paint_armor(T, t, objs, nbake, ao)
    P, N = t["P"], t["N"]
    A = t["A"]
    n = len(P)
    mz = np.round(A.get("mz", np.zeros(n))).astype(int)
    ao_t = norm_ao(ao, t, 0.0)
    curv = curvature(T, t, nbake)
    pid = A.get("plate", np.zeros(n))
    # pauldrons, lames, brackets, emblem (zone 0): brushed silver steel (the armour tint warms it slightly), with a
    # darker satin recessed panel inside the groove of the large caps
    z0 = mz == 0
    pr = np.round(pid)
    brushed = 0.82 + 0.06 * TB.fbm3(P * np.array((1.0, 1.0, 6.0)), 160.0, 2, 14.0) + 0.04 * TB.fbm3(P, 9.0, 2, 15.0)
    steel = np.array((0.74, 0.75, 0.78))[None] * brushed[:, None]
    lx0, ly0 = A.get("lx", np.zeros(n)), A.get("ly", np.zeros(n))
    capm = z0 & ((pr == 20) | (pr == 21))
    inset = capm & (np.abs(lx0) < 0.062) & (np.abs(ly0) < 0.05)
    rgb = np.where(z0[:, None], steel, rgb)
    metal = np.where(z0, 0.55, metal)
    smooth = np.where(z0, 0.5 + 0.05 * TB.fbm3(P, 40.0, 2, 16.0), smooth)
    rgb = np.where(inset[:, None], np.array((0.36, 0.37, 0.39))[None], rgb)
    metal = np.where(inset, 0.6, metal)
    smooth = np.where(inset, 0.5, smooth)
    paint = np.where(z0, 0.0, paint)
    # zone 3: moulded polymer, satin, with a fine stipple, lighter machined chamfers and scuffs, cavity grime
    lz = mz == 3
    stip = TB.worley3(P, 1 / 0.0011, 5.0)
    pol = np.array((0.085, 0.087, 0.092))[None] * (1 + 0.04 * TB.fbm3(P, 18.0, 3, 7.0)[:, None] + 0.05 * (stip[:, None] - 0.5))
    edge = np.clip(curv * 1.4, 0, 1)
    pol = pol * (1 + 0.5 * edge[:, None])
    sc = FB.scratches(A.get("lx", np.zeros(n)), A.get("ly", np.zeros(n)), pid, density=60, seed=9.0)
    pol = pol * (1 + 0.3 * sc[:, None])
    g = FB.grime(P, ao_t, A.get("cavity", np.zeros(n)), seed=11.0)
    pol = pol * (1 - 0.35 * g[:, None])
    rgb = np.where(lz[:, None], pol, rgb)
    smooth = np.where(lz, 0.34 - 0.1 * g + 0.06 * edge - 0.04 * (stip > 0.6), smooth)
    h = np.where(lz, h + 0.000015 * (stip - 0.5), h)
    metal = np.where(lz, 0.0, metal)
    paint = np.where(lz, 0.0, paint)
    # concept: chest plate, its yoke and band, the knee caps and the belt buckle are satin BLACK polymer (machined
    # chamfers a little lighter, fine stipple), only the pauldrons are steel
    blk = lz & np.isin(pr, (10, 11, 12, 13, 40))
    bcol = np.array((0.052, 0.054, 0.058))[None] * (1 + 0.035 * TB.fbm3(P, 18.0, 3, 7.0)[:, None] + 0.04 * (stip[:, None] - 0.5))
    bcol = bcol * (1 + 1.6 * edge[:, None]) * (1 + 0.25 * sc[:, None]) * (1 - 0.3 * g[:, None])
    rgb = np.where(blk[:, None], bcol, rgb)
    smooth = np.where(blk, 0.46 - 0.08 * g + 0.06 * edge, smooth)
    # glyph decal + serial on the knee caps / greaves / chest plate (light grey print)
    dec = np.zeros(n)
    lx, ly = A.get("lx", np.zeros(n)), A.get("ly", np.zeros(n))
    for p_id, (gx, gy, gw, gh) in ((40, (-0.03, -0.045, 0.04, 0.007)), (42, (-0.022, 0.07, 0.03, 0.006)), (10, (0.03, 0.05, 0.05, 0.008))):
        m = (np.round(pid) == p_id) & lz
        dec = np.maximum(dec, PK.glyphs(lx, ly, gx, gy, gw, gh, seed=p_id + 100) * m)
    rgb = rgb * (1 - 0.5 * dec[:, None]) + 0.5 * dec[:, None] * np.array((0.32, 0.33, 0.34))[None]
    rgb = rgb * (0.55 + 0.45 * ao_t[:, None])
    return np.clip(rgb, 0, 1), h, metal, np.clip(smooth, 0.15, 0.85), paint


# ============================================================================= Boots: values up, laces, glossy moulded caps


def paint_boots(T, t, objs, nbake, ao):
    rgb, h, metal, smooth, paint = PK.paint_boots(T, t, objs, nbake, ao)
    P = t["P"]
    A = t["A"]
    n = len(P)
    ao_t = norm_ao(ao, t, 0.0)
    curv = curvature(T, t, nbake)
    # lift every value (the k2 boot was near-black): leather ~0.17, caps 0.22 glossy, sole 0.13
    rgb = np.clip(rgb * 1.3 + 0.012, 0, 1)
    cap = A.get("cap", np.zeros(n)) > 0.5
    sole = A.get("sole", np.zeros(n)) > 0.5
    strap = A.get("strap", np.zeros(n)) > 0.5
    plate = A.get("plate", np.zeros(n)) > 0.5
    rgb = np.where(cap[:, None], np.array((0.1, 0.102, 0.108))[None] * (1 + 0.8 * np.clip(curv, 0, 1)[:, None]), rgb)
    smooth = np.where(cap, 0.62, smooth)
    # shin plate: glossy black polymer, lighter machined chamfer
    rgb = np.where(plate[:, None], np.array((0.075, 0.077, 0.082))[None] * (1 + 1.4 * np.clip(curv, 0, 1)[:, None]), rgb)
    smooth = np.where(plate, 0.6, smooth)
    rgb = np.where(strap[:, None], np.array((0.13, 0.132, 0.135))[None], rgb)
    rgb = rgb * (0.5 + 0.5 * ao_t[:, None])
    return np.clip(rgb, 0, 1), h, metal, np.clip(smooth, 0.1, 0.85), paint


# ============================================================================= Gloves: black tactical (the runtime tint is outfit*0.75)


def paint_gloves(T, t, objs, nbake, ao, L):
    rgb, h, metal, smooth, paint = PK.paint_gloves(T, t, objs, nbake, ao, L)
    A = t["A"]
    n = len(rgb)
    stud = A.get("stud", np.zeros(n)) > 0.5
    cp = A.get("cuffplate", np.zeros(n)) > 0.5
    strap = A.get("strap", np.zeros(n)) > 0.5
    # leather/knit down to near-black once tinted; metal studs and edges stay bright
    dark = ~stud & (metal < 0.5)
    rgb = np.where(dark[:, None], rgb * 0.5, rgb)
    rgb = np.where(stud[:, None], np.array((0.95, 0.88, 0.7))[None], rgb)
    metal = np.where(stud, 1.0, metal); smooth = np.where(stud, 0.7, smooth)
    rgb = np.where(cp[:, None], np.array((0.62, 0.63, 0.66))[None], rgb)
    metal = np.where(cp, 0.8, metal); smooth = np.where(cp, 0.55, smooth)
    rgb = np.where(strap[:, None], rgb * 0.8, rgb)
    return rgb, h, metal, smooth, paint
