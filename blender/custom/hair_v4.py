"""Hair v4: hero-quality card hair for the defaults (Giva `long_waves`, Kael `side_part_volume`).

  blender -b --python blender/custom/hair_v4.py -- <cid> <style> [--no-export]

What is different from the v3 library (hair_build.py):
  * many thin layered strand cards (10-14 mm at the root, tapering to 2-4 mm), 3-4 offset layers that build real
    volume at the crown, phase-coherent waves, tip clumping, a soft U haircut, flyaways;
  * strand tiles drawn strand by strand: dense opaque roots, staggered strand ends (wispy tips, never a hard card end),
    sparse strands towards the card sides (no visible card edge), darker roots, lighter tips, per-strand value
    variation, and baked highlight bands at the crown (each card gets the tile whose band sits where it crosses the
    crown);
  * the scalp cap is painted in 3-D from the same flow field with a parting, a broken-up hairline (alpha strokes,
    the cap's geometric edge lies outside the visible hairline) and short-hair fades;
  * shading normals from a smooth envelope that becomes horizontal below the head (no downward-facing card normals
    over the chest) - Unity renders the cards double sided without flipping normals, so both sides shade alike;
  * the atlas colour bleeds into every transparent texel (no dark alpha-clip fringes).
"""
import bpy, os, sys, math, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree
import common as C
import gear, texbake as TB
import hairlib as HL
from hairlib import Head, grow, cut, frame, tangents, arclen, resample, volume_shell, dirv, tile_rect, bleed, VOL_RECT
import hair_build as HBD
import studio
from common import ss, nrm, nrm_rows

R_ = np.radians
ATLAS = 2048
TW = ATLAS // 16          # tile width (px)
TH = ATLAS // 2 - 8       # tile height (px)


# ============================================================================= strand tiles


def strand_tile(rng, n=220, wave=0.0, clumps=(3, 6), spread=0.3, tip_min=0.5, band=None, width=(0.9, 1.5),
                converge=0.25, frizz=0.0, root_dark=0.32, tip_light=0.18, sparse=False):
    """Draw one strand tile (TH x TW): row 0 = tip, last row = root. Returns (lum, alpha)."""
    W, H = TW, TH
    v = (np.arange(H) + 0.5) / H                 # 0 tip .. 1 root
    lum = np.zeros((H, W), np.float32)
    alpha = np.zeros((H, W), np.float32)
    nc = int(rng.integers(clumps[0], clumps[1] + 1))
    cen = rng.uniform(0.3, 0.7, nc) * W
    csig = W * spread / math.sqrt(nc)
    xs = np.arange(W, dtype=np.float32)
    for k in range(n):
        c = int(rng.integers(nc))
        x0 = cen[c] + rng.normal(0, csig)
        if not (1.5 < x0 < W - 2.5):
            continue
        edge = abs(x0 - W / 2) / (W / 2)           # 0 centre .. 1 side
        Lf = rng.uniform(tip_min, 1.0) * (1 - 0.35 * edge ** 2)
        if not sparse and rng.random() < 0.25:
            Lf = rng.uniform(0.85, 1.0)
        vend = 1 - Lf
        amp = W * (0.004 + 0.02 * wave) * rng.uniform(0.5, 1.5)
        ph = rng.uniform(0, 2 * math.pi)
        fq = rng.uniform(1.0, 2.2) + wave * 2.0
        cx = x0 + amp * np.sin(v * fq * 2 * math.pi + ph)
        if converge:
            cx = cx + (cen[c] - x0) * converge * (1 - v) ** 1.4
        if frizz:
            cx = cx + np.cumsum(rng.normal(0, frizz, H)) * 0.03 * (1 - v)
        w = rng.uniform(*width) * (0.55 + 0.45 * ss(vend, vend + 0.25, v))
        rows = np.where(v > vend)[0]
        if len(rows) < 4:
            continue
        lo = int(max(0, np.floor(cx[rows].min() - 3))); hi = int(min(W, np.ceil(cx[rows].max() + 4)))
        X = xs[lo:hi][None, :]
        a = np.clip(0.5 + w[rows, None] * 0.5 - np.abs(X - cx[rows, None]), 0, 1)
        a *= ss(vend, vend + 0.06, v[rows])[:, None]
        b = rng.uniform(0.55, 1.0)
        l = b * (1 - root_dark * ss(0.8, 1.0, v[rows])) * (1 + tip_light * (1 - v[rows]))
        if band is not None:
            bj = band + rng.normal(0, 0.008)
            l = l * (1 + 0.42 * np.exp(-(((1 - v[rows]) - bj) / 0.03) ** 2))
        sub_l = lum[rows, lo:hi]; sub_a = alpha[rows, lo:hi]
        lum[rows, lo:hi] = sub_l * (1 - a) + l[:, None] * a
        alpha[rows, lo:hi] = sub_a + a * (1 - sub_a)
    lum = np.where(alpha > 1e-3, lum / np.maximum(alpha, 1e-3), 0)
    return lum, np.clip(alpha * 1.25, 0, 1)


def strand_tile5(rng, clumps=(4, 7), cw=(0.10, 0.22), per=34, under=90, wave=0.0, tip_min=0.45, band=None, value=1.0,
                 cval=(0.6, 1.12), width=(1.0, 1.8), converge=0.35, root_dark=0.4, tip_light=0.15, root_stagger=0.0,
                 under_val=(0.3, 0.5), edge_fade=0.18, band_amp=0.55):
    """v5 strand tile with structure that survives mip-mapping: a darker under-layer of loose strands (depth between
    clumps), then 4-7 distinct clumps with their own value (light/dark streaks), strands converging towards the tip,
    staggered tips (and optionally staggered roots for hairline cards). Row 0 = tip, last row = root."""
    W, H = TW, TH
    v = (np.arange(H) + 0.5) / H
    lum = np.zeros((H, W), np.float32)
    alpha = np.zeros((H, W), np.float32)
    xs = np.arange(W, dtype=np.float32)

    def strand(x0, cx_target, b, Lf, wdt, conv, rs):
        vend = 1 - Lf
        vroot = 1 - rs
        amp = W * (0.003 + 0.018 * wave) * rng.uniform(0.5, 1.5)
        ph = rng.uniform(0, 2 * math.pi)
        fq = rng.uniform(1.0, 2.2) + wave * 2.0
        cx = x0 + amp * np.sin(v * fq * 2 * math.pi + ph) + (cx_target - x0) * conv * (1 - v) ** 1.3
        rows = np.where((v > vend) & (v < vroot))[0]
        if len(rows) < 4:
            return
        w = wdt * (0.5 + 0.5 * ss(vend, vend + 0.2, v[rows]))
        lo = int(max(0, np.floor(cx[rows].min() - 3))); hi = int(min(W, np.ceil(cx[rows].max() + 4)))
        X = xs[lo:hi][None, :]
        a = np.clip(0.5 + w[:, None] * 0.5 - np.abs(X - cx[rows, None]), 0, 1)
        a *= ss(vend, vend + 0.05, v[rows])[:, None]
        if rs > 0:
            a *= (1 - ss(vroot - 0.04, vroot, v[rows]))[:, None]
        edge = np.abs(cx[rows] - W / 2) / (W / 2)
        a *= (1 - ss(1 - edge_fade * 2, 1.0, edge))[:, None]
        l = b * (1 - root_dark * ss(0.78, 1.0, v[rows])) * (1 + tip_light * (1 - v[rows]))
        if band is not None:
            bj = band + rng.normal(0, 0.01)
            l = l * (1 + band_amp * np.exp(-(((1 - v[rows]) - bj) / 0.028) ** 2))
        sub_l = lum[rows, lo:hi]; sub_a = alpha[rows, lo:hi]
        lum[rows, lo:hi] = sub_l * (1 - a) + l[:, None] * a
        alpha[rows, lo:hi] = sub_a + a * (1 - sub_a)

    for _ in range(under):                       # loose dark under-strands
        x0 = rng.uniform(0.12, 0.88) * W
        strand(x0, x0, rng.uniform(*under_val) * value, rng.uniform(0.55, 1.0), rng.uniform(0.9, 1.4), 0.0,
               rng.uniform(0, root_stagger) if root_stagger else 0.0)
    nc = int(rng.integers(clumps[0], clumps[1] + 1))
    cen = np.sort(rng.uniform(0.16, 0.84, nc)) * W
    for c in range(nc):
        cb = rng.uniform(*cval) * value
        sig = rng.uniform(*cw) * W * 0.5
        tipc = cen[c] + rng.normal(0, W * 0.03)
        for _ in range(per):
            x0 = cen[c] + rng.normal(0, sig)
            if not (1.5 < x0 < W - 2.5):
                continue
            Lf = rng.uniform(tip_min, 1.0)
            if rng.random() < 0.3:
                Lf = rng.uniform(0.85, 1.0)
            strand(x0, tipc, cb * rng.uniform(0.78, 1.04), Lf, rng.uniform(*width), converge,
                   rng.uniform(0, root_stagger) if root_stagger else 0.0)
    lum = np.where(alpha > 1e-3, lum / np.maximum(alpha, 1e-3), 0)
    return lum, np.clip(alpha * 1.3, 0, 1)


def paint_atlas_tiles(img, specs, rng):
    for k, sp in enumerate(specs):
        if sp is None:
            continue
        sp = dict(sp)
        fn = strand_tile5 if sp.pop("v5", False) else strand_tile
        lum, al = fn(rng, **sp)
        u0, v0, u1, v1 = tile_rect(k)
        x0 = int(round(u0 * ATLAS)); y0 = int(round(v0 * ATLAS)) + 4
        img[y0:y0 + TH, x0:x0 + TW, 0] = lum
        img[y0:y0 + TH, x0:x0 + TW, 3] = al


# ============================================================================= scalp cap painting


def lic(P, flow, freq, half, steps, seed, chunk=250000):
    """Line-integral-convolution of 3-D value noise along the flow field (streaks that follow the hair direction,
    seamless across UV islands). Returns zero-mean, unit-variance values."""
    out = np.zeros(len(P))
    for s0 in range(0, len(P), chunk):
        Q0 = P[s0:s0 + chunk]
        acc = TB.vnoise3(Q0, freq, seed)
        wsum = 1.0
        for sg in (1.0, -1.0):
            Q = Q0.copy()
            for k in range(steps):
                Q = Q + sg * flow(Q) * (half / steps)
                w = 1.0 - (k + 1) / (steps + 1)
                acc = acc + w * TB.vnoise3(Q, freq, seed)
                wsum += w
        out[s0:s0 + chunk] = acc / wsum
    return (out - out.mean()) / max(out.std(), 1e-6)


def paint_cap(H, vol, img, flow, density=None, part=None, hairline=None, soft=4.0, band_el=None, seed=1.0, stroke=(0.012, 0.03),
              lum_mul=0.85, part_cut=True):
    """3-D painted cap texture into VOL_RECT. flow(P)->F; density(az, el, P)->0..1 (short-hair fade, 0 = skin);
    part(P, el)->distance to the parting (m) or None; hairline: knots (deg) for H.hairline_el."""
    S = img.shape[0]
    T = TB.raster([vol], "Hair", S, attrs=())
    idx = np.where(T.cov)[0]
    P = T.P[idx].astype(np.float64); N = T.N[idx].astype(np.float64)
    az, el, r = H.angles(P)
    t0 = time.time()
    fine = lic(P, flow, 1300.0, 0.007, 10, seed)
    clump = lic(P, flow, 200.0, 0.016, 6, seed + 1)
    st = np.clip(0.5 + 0.24 * fine, 0, 1)
    cl = np.clip(0.5 + 0.22 * clump, 0, 1)
    lum = (0.25 + 0.75 * st) * (0.72 + 0.56 * cl) * lum_mul
    C.log("cap LIC", len(P), "texels", round(time.time() - t0, 1), "s")
    if band_el is not None:
        lum = lum * (1 + 0.38 * np.exp(-((np.degrees(el) - band_el) / 7.0) ** 2) * (0.5 + st))
    alpha = np.ones(len(P), np.float32)
    # hairline: strokes thinning out over `soft` degrees, jittered
    if hairline is not None:
        jit = 1.6 * TB.fbm3(P, 90.0, 2, seed + 7) - 0.8
        d = np.degrees(el - H.hairline_el(az, hairline)) + jit
        ramp = np.clip(d / soft, 0, 1)
        alpha = np.where(d < soft, (fine > 2.0 - 3.1 * ramp) * (d > 0), alpha).astype(np.float32)
        lum = lum * (1 - 0.15 * (1 - ramp))
    # short hair fade: short down-pointing strokes whose coverage equals the density
    if density is not None:
        dens = np.clip(density(az, el, P), 0, 1)
        short = lic(P, flow, 1700.0, 0.0022, 4, seed + 5)
        stub = short > (1.25 - 2.7 * dens)
        full = dens > 0.995
        alpha = np.where(full, alpha, np.minimum(alpha, stub.astype(np.float32))).astype(np.float32)
        lum = np.where(full, lum, (0.32 + 0.3 * np.clip(0.5 + 0.25 * short, 0, 1)) * lum_mul * (0.85 + 0.25 * dens))
    if part is not None:
        dp = part(P, el)
        if dp is not None:
            jit = 0.0004 * (TB.vnoise3(P, 220.0, 5.0) - 0.5)
            pa = np.abs(dp + jit)
            if part_cut:
                alpha = np.where(pa < 0.0007 + 0.0005 * np.clip(fine, 0, 2), 0.0, alpha).astype(np.float32)
                lum = np.where(pa < 0.0035, lum * (0.7 + 0.3 * ss(0.0007, 0.0035, pa)), lum)
            else:          # no scalp line (it reads as a bald stripe in-game): only darker roots along the parting
                lum = np.where(pa < 0.004, lum * (0.62 + 0.38 * ss(0.0, 0.004, pa)), lum)
    out = np.zeros((S * S, 4), np.float32)
    out[idx, 0] = lum; out[idx, 3] = alpha
    out = out.reshape(S, S, 4)
    cov = T.cov.reshape(S, S)
    u0, v0, u1, v1 = VOL_RECT
    ys, ye, xs_, xe = int(v0 * S), int(v1 * S), int(u0 * S), int(u1 * S)
    sub = out[ys:ye, xs_:xe]; cs = cov[ys:ye, xs_:xe]
    ak = sub[..., 3].copy()
    sub = TB.dilate(sub, cs, 6)
    sub[..., 3] = np.where(cs, ak, 0.0)
    img[ys:ye, xs_:xe] = sub


def finish(img, target=0.78):
    lum = img[..., 0]; a = img[..., 3]
    m = lum[a > 0.5].mean() if (a > 0.5).any() else 0.5
    lum = np.clip(lum / max(m, 1e-3) * target, 0, 1)
    out = np.zeros_like(img)
    rgb = np.stack([lum] * 3, -1) * np.array((1.0, 0.985, 0.97))
    out[..., :3] = bleed(rgb, a)
    out[..., 3] = a
    return np.clip(out, 0, 1)


# ============================================================================= builder


class V4:
    def __init__(self, H, ctx, cid, sid, seed=7):
        self.H, self.ctx, self.cid, self.sid = H, ctx, cid, sid
        self.rng = np.random.default_rng(seed)
        self.part = gear.Part(sid + "_cards")
        self.kind = "rigid"
        self.cutoff = 0.4
        self.ncards = 0

    def card(self, P, w0, w1, tile, normals=None, side=None, jitter=0.0, twist=0.0):
        """Tapered ribbon card along P (root first). side defaults to the frame side vector. jitter tilts the shading
        normal per card (breaks the smooth 'helmet' sheen into strand-group streaks); twist (rad) rolls the ribbon about
        its own axis so neighbouring cards are not coplanar."""
        if len(P) < 3 or arclen(P)[-1] < 0.004:
            return
        T_, S_, N_ = frame(self.H, P)
        side = S_ if side is None else side
        nrmls = N_ if normals is None else normals
        if twist:
            c_, s_ = math.cos(twist), math.sin(twist)
            side = nrm_rows(side * c_ + nrmls * s_)
        if jitter:
            nrmls = nrm_rows(nrmls + self.rng.normal(0, jitter, 3)[None, :])
        s = arclen(P); s = s / max(s[-1], 1e-9)
        w = w0 + (w1 - w0) * s ** 1.15
        w = w * (1 - 0.45 * ss(0.85, 1.0, s))
        HL.card_strip(self.part, P, side, w, tile, 0.5, nrmls)
        self.ncards += 1

    def fringe(self, hairline, flow, tiles, az_max=150.0, rows=3, step_deg=1.3, L=(0.008, 0.02), w=(0.0035, 0.0055), seed=3):
        """Soft hairline: tiny sparse strand cards rooted along the hairline (and 2 rows just above it) lying on the
        scalp along the flow, so the leading edge of the hair is made of individual strands instead of a texture
        edge (alpha-clipped edges alias into hard lines in Unity)."""
        H, rng = self.H, self.rng
        for r in range(rows):
            for a in np.arange(-az_max, az_max + 1e-6, step_deg):
                ar = R_(a + rng.uniform(-0.5, 0.5))
                e = H.hairline_el(np.array([ar]), hairline)[0] + R_(-0.4 + r * 1.4 + rng.uniform(-0.6, 0.6))
                p = H.surf(np.array([ar]), np.array([e]), 0.0)[0]
                n = H.radial(p[None])[0]
                d0 = flow(p[None])[0]
                Ln = rng.uniform(*L) * (1.0 + 0.4 * r)
                Pp = grow(H, p, n, Ln, d0 + rng.normal(0, 0.12, 3), 5, 0.02, 1.0, 0.05, 0.0011 + 0.0006 * r, 1.6, 0.0, None, 0.0, 0.0,
                          clear=0.0009, guard=None, body_clear=0.003)
                if len(Pp) >= 3:
                    self.card(Pp, rng.uniform(*w), 0.0012, int(rng.choice(tiles)))

    def hairline_cards(self, hairline, dirf, tiles, az_max=125.0, step_deg=1.5, L=(0.03, 0.055), w=(0.006, 0.008),
                       off=0.0016, inside=(0.2, 1.6), segs=8, guard=None, rows=1, tiles_dense=None, row_step=2.4):
        """Soft hairline: cards rooted on the hairline lying close to the scalp in the growth direction, textured with
        root-staggered sparse strands, so the hairline is a gradient of single hairs instead of a hard alpha edge.
        They also hide the cap's edge (the cap's painted hairline sits a little inside)."""
        H, rng = self.H, self.rng
        for r in range(rows):
            for a in np.arange(-az_max, az_max + 1e-6, step_deg):
                ar = R_(a + rng.uniform(-0.6, 0.6))
                e = H.hairline_el(np.array([ar]), hairline)[0] + R_(rng.uniform(*inside) + r * row_step)
                p = H.surf(np.array([ar]), np.array([e]), 0.0)[0]
                n = H.radial(p[None])[0]
                d0 = dirf(p, ar)
                Pp = grow(H, p, n, rng.uniform(*L), d0 + rng.normal(0, 0.06, 3), segs, 0.03, 1.15, 0.03, off, 1.4, 0.0015, None,
                          0.0, 0.0, clear=off * 0.7, guard=guard, body_clear=0.004)
                if len(Pp) >= 4:
                    tl = tiles if (r == 0 or tiles_dense is None) else tiles_dense
                    self.card(Pp, rng.uniform(*w), rng.uniform(0.0015, 0.0025), int(rng.choice(tl)), jitter=0.1)

    def band_tile(self, P, tiles_by_band, plain, el_band=46.0):
        """Tile whose highlight band position matches where this card crosses elevation `el_band`."""
        az, el, r = self.H.angles(P)
        e = np.degrees(el)
        arc = arclen(P); s = arc / max(arc[-1], 1e-9)
        cross = np.where((e[:-1] >= el_band) & (e[1:] < el_band))[0]
        if not len(cross):
            return int(self.rng.choice(plain))
        sb = s[cross[0]]
        keys = np.array(sorted(tiles_by_band))
        k = keys[np.argmin(np.abs(keys - sb))]
        if abs(k - sb) > 0.06:
            return int(self.rng.choice(plain))
        return int(self.rng.choice(tiles_by_band[k]))


def env_normals(obj, H, mix=0.5):
    """Card normals = envelope normal (ellipsoid around the head, horizontal-radial below it) mixed with the card's
    own normal; cap vertices keep their smooth normals."""
    me = obj.data
    me.update()
    co = gear.get_co(obj)
    vn = gear.vnormals(obj)
    hv = gear.attr(obj, "hairvol")
    hc = H.hc + np.array((0, 0.01, 0.0))
    d = co - hc
    above = co[:, 2] >= hc[2]
    env = np.where(above[:, None], d / np.array((1.0, 1.0, 1.1)), np.stack([d[:, 0], d[:, 1], d[:, 2] * 0.15], 1))
    env = nrm_rows(env)
    ln = np.stack([gear.attr(obj, "lnx"), gear.attr(obj, "lny"), gear.attr(obj, "lnz")], 1)
    has = np.linalg.norm(ln, axis=1) > 0.5
    own = np.where(has[:, None], ln, vn)
    sg = np.sign((own * env).sum(1, keepdims=True)); sg[sg == 0] = 1
    own = own * sg
    n = np.where(hv[:, None] > 0.5, vn, env * (1 - mix) + own * mix)
    n = nrm_rows(n)
    me.normals_split_custom_set_from_vertices([tuple(v) for v in n])


def coherent_waves(H, P, amp, lam, phase, start_z, ramp=0.12):
    """S-waves in the card frame starting below `start_z` (phase supplied per card, coherent between neighbours)."""
    T_, S_, N_ = frame(H, P)
    arc = arclen(P)
    zs = np.maximum(0, start_z - P[:, 2])
    k = ss(0.0, ramp, zs)
    th = 2 * math.pi * arc / lam + phase
    off = S_ * (amp * k * np.sin(th))[:, None] + N_ * (0.5 * amp * k * np.cos(th))[:, None]
    return P + off


# ============================================================================= Giva: long_waves


def slerp_dir(d0, d1, t):
    om = math.acos(float(np.clip(np.dot(d0, d1), -1, 1)))
    if om < 1e-5:
        return d0
    return (math.sin((1 - t) * om) * d0 + math.sin(t * om) * d1) / math.sin(om)


def push_out(H, q, clear, reach=0.07):
    """Keep hair outside the outermost garment layer near the neck/shoulders (stand-up collars, harness, shoulder
    armour): cast horizontally away from the body axis; if the last surface crossed within `reach` is an exit (its
    normal points along the ray), q lies under / inside that garment and moves just outside it."""
    if q[2] > H.jaw_z + 0.02 or q[2] < H.shoulder_z - 0.12:
        return q
    rh = q - np.array((H.hc[0], H.hc[1] + 0.01, q[2]))
    if np.linalg.norm(rh) < 1e-6:
        return q
    rh = nrm(rh)
    if abs(rh[1]) < 0.45 and q[2] < H.shoulder_z + 0.03:
        return q                      # lateral rays at shoulder height would hit the arms
    o = Vector(q); last = None; travelled = 0.0
    for _ in range(6):
        hit, n, _, d = H.outer.ray_cast(o, Vector(rh), reach - travelled)
        if hit is None:
            break
        last = (np.array(hit), np.array(n))
        travelled += d + 1e-4
        o = hit + Vector(rh) * 1e-4
        if travelled >= reach:
            break
    if last is not None and np.dot(last[1], rh) > 0.05:
        q = last[0] + rh * clear
    return q


def guide_curve(H, root_dir, exit_dir, off, lift, L, clear, guard, n=30, step=0.008):
    """Guide polyline: over the scalp from root_dir to exit_dir (directions from the head centre, `off` above the
    scalp, lifted by `lift` mid-way = crown volume), then falling under gravity with collisions; resampled to n."""
    om = math.acos(float(np.clip(np.dot(root_dir, exit_dir), -1, 1)))
    k = max(4, int(om * 0.11 / step))
    pts = []
    for i in range(k + 1):
        t = i / k
        d = nrm(slerp_dir(root_dir, exit_dir, t))
        az, el = math.atan2(d[0], -d[1]), math.asin(max(-1, min(1, d[2])))
        o = off + lift * math.sin(math.pi * min(1, t * 1.6)) ** 2 * (1 - t) * 1.8
        pts.append(H.surf(np.array([az]), np.array([el]), o)[0])
    P = [pts[0]]
    for q in pts[1:]:
        q = H.collide(q, off * 0.9, clear)
        if guard is not None:
            q = guard(q, P[-1])
        P.append(q)
    arc = sum(np.linalg.norm(np.diff(np.array(P), axis=0), axis=1))
    rad_h = P[-1] - np.array((H.hc[0], H.hc[1] + 0.01, P[-1][2]))
    rad_h = nrm(rad_h) if np.linalg.norm(rad_h) > 1e-6 else np.array((0, 1.0, 0))
    d = nrm(np.array((0, 0, -1.0)) + rad_h * 0.25)
    while arc < L:
        d = nrm(d * 0.6 + np.array((0, 0, -1.0)) * 0.4)
        rh = P[-1] - np.array((H.hc[0], H.hc[1] + 0.01, P[-1][2]))
        rh = nrm(rh) if np.linalg.norm(rh) > 1e-6 else rad_h
        inward = np.dot(d, rh)
        if inward < 0:                      # hair drapes from the widest point: never curls in towards the neck
            d = nrm(d - rh * inward)
        q = P[-1] + d * step
        q = H.collide(push_out(H, q, clear), off * 0.9, clear)
        if guard is not None:
            q = guard(q, P[-1])
        d = nrm(q - P[-1]) if np.linalg.norm(q - P[-1]) > 1e-6 else d
        arc += np.linalg.norm(q - P[-1])
        P.append(q)
    return resample(np.array(P), n)


def smooth_guides(G, iters=3, w=0.5):
    G = G.copy()
    for _ in range(iters):
        G[1:-1, 1:] = G[1:-1, 1:] * w + (G[:-2, 1:] + G[2:, 1:]) * (1 - w) * 0.5
    return G


def build_long_waves(b):
    H, rng = b.H, b.rng
    b.kind = "skinned"
    b.cutoff = 0.35
    part_x = 0.024
    hairline = [26, 24, 17, 7, -2, -15, -30, -36, -40]
    cap_line = [k - 5 for k in hairline]
    mask, az, el = H.scalp(cap_line)

    def flow(P):
        az_, el_, r_ = H.angles(P)
        side = np.sign(P[:, 0] - part_x + 1e-6)
        top = ss(R_(25), R_(55), el_)
        F = np.stack([side * (0.35 + 0.65 * top), 0.35 + 0.2 * top, -1.0 + 0.75 * top], 1)
        return H.tangent(P, F)

    vol = volume_shell(H, b.ctx, b.sid + "_cap", mask, lambda a_, e_: 0.0035 + 0.0025 * ss(R_(0), R_(40), e_))
    hw = H.face_hw + 0.016

    def guard(q, p):
        if q[2] < H.brow_z + 0.03 and q[2] > H.jaw_z - 0.08 and q[1] < H.eye[1] + 0.045 and abs(q[0]) < hw:
            q = q.copy()
            q[0] = math.copysign(hw, q[0] if abs(q[0]) > 1e-4 else 1.0)
        return q

    def part_dir(t):
        """Direction (from the head centre) of the parting: t 0 = front hairline .. 1 = crown."""
        th = R_(34 + (122 - 34) * t)
        q = H.hc + np.array((0.0, -math.cos(th), math.sin(th))) * 0.12
        q[0] = part_x
        return nrm(q - H.hc)

    def exit_el(a):
        return R_(np.interp(abs(math.degrees(a)), [60, 80, 100, 130, 160, 180], [12, 6, 2, -10, -20, -24]))

    tiles_band = {0.05: [0, 1, 2], 0.10: [3, 4, 5], 0.16: [6, 7, 8], 0.23: [9, 10, 11]}
    plain_light = [16, 17, 18, 19]
    plain_mid = [13, 14, 15, 16, 17]
    plain_dark = [12, 13, 14, 15]
    wisp = [20, 21]
    fringe_t = [22, 23]
    NG = 34
    # v5: the hair lies close to the head (the old crown lift read as a helmet), narrower cards, more of them
    layers = [  # name, n guides per side, az range (deg), root, offset, lift, length, clearance, cards per gap
        ("front", 12, (58, 82), "partfront", 0.0050, 0.0025, 0.55, 0.011, 4),
        ("outer", 42, (68, 178), "part", 0.0072, 0.0035, 0.62, 0.013, 3),
        ("mid", 38, (64, 178), 40.0, 0.0050, 0.002, 0.56, 0.010, 3),
        ("inner", 30, (74, 178), 14.0, 0.0030, 0.0, 0.50, 0.0075, 2),
        ("nape", 12, (128, 178), -14.0, 0.0022, 0.0, 0.42, 0.007, 2),
    ]
    for side in (1, -1):
        for li, (name, ng, (a0, a1), root, off, lift, Lm, clear, cpg) in enumerate(layers):
            azs = np.linspace(a0, a1, ng)
            G = []
            for k, a in enumerate(azs):
                ar = R_(a) * side
                ex = dirv(ar, exit_el(ar))
                if root in ("part", "partfront"):
                    t = (a - a0) / (a1 - a0) * (0.22 if root == "partfront" else 1.0)
                    rd = part_dir(min(1.0, t * 1.05))
                    rd = nrm(rd + np.array((side * 0.03, 0, 0)))
                else:
                    rd = dirv(ar, R_(root))
                L = Lm * (0.9 + 0.1 * ss(70, 170, a))
                G.append(guide_curve(H, rd, ex, off, lift, L, clear, guard, NG))
            G = smooth_guides(np.array(G), 3)
            for it in range(4):
                for k in range(len(G)):
                    P = G[k].copy()
                    P[1:-1] = P[1:-1] * 0.5 + (P[:-2] + P[2:]) * 0.25
                    P[-1] = P[-1] * 0.5 + (P[-2] * 2 - P[-3]) * 0.5
                    G[k] = np.array([P[0]] + [guard(H.collide(push_out(H, q, clear), off * 0.85, clear), P[i]) for i, q in enumerate(P[1:])])
            # coherent waves: phase from height (bands) + slow azimuth drift
            for k in range(len(G)):
                P = G[k]
                T_, S_, N_ = frame(H, P)
                drop = np.maximum(0, (H.jaw_z + 0.04) - P[:, 2])
                kk = ss(0.0, 0.12, drop)
                ph = 2 * math.pi * drop / 0.105 + 0.45 * R_(azs[k]) + li * 0.5 + 0.9 * math.sin(2.3 * R_(azs[k]) + li) + side * 0.7
                amp = 0.013 + 0.005 * ss(0.1, 0.3, drop)
                P = P + N_ * (amp * kk * np.sin(ph))[:, None] + S_ * (0.45 * amp * kk * np.cos(ph))[:, None]
                G[k] = np.array([P[0]] + [guard(H.collide(push_out(H, q, clear * 0.7), off * 0.85, clear * 0.7), P[i])
                                          for i, q in enumerate(P[1:])])
            # cards between neighbouring guides
            for k in range(len(G) - 1):
                A_, B_ = G[k], G[k + 1]
                gap = np.linalg.norm(A_ - B_, axis=1)
                for j in range(cpg):
                    t = (j + rng.uniform(0.15, 0.85)) / cpg
                    P = A_ * (1 - t) + B_ * t
                    T_, S_, N_ = frame(H, P)
                    P = P + N_ * rng.normal(0, 0.0012) + S_ * rng.normal(0, 0.002)
                    cut_f = rng.uniform(0.84, 1.0)
                    m = max(6, int(round(NG * cut_f)))
                    P = P[:m]
                    sidev = nrm_rows((B_ - A_)[:m] - T_[:m] * ((B_ - A_)[:m] * T_[:m]).sum(1, keepdims=True))
                    w0 = float(np.clip(np.median(gap) / cpg * 1.7, 0.0055, 0.0125))
                    if name in ("front", "outer"):
                        tile = b.band_tile(P, tiles_band, plain_light)
                    elif name == "mid":
                        tile = int(rng.choice(plain_mid))
                    else:
                        tile = int(rng.choice(plain_dark))
                    b.card(P, w0, w0 * rng.uniform(0.22, 0.32), tile, normals=N_[:m], side=sidev, jitter=0.16,
                           twist=rng.normal(0, 0.18))
    # flyaways (few, thin, on the crown and the outer surface)
    roots, rn = H.sample_roots(H.scalp(hairline)[0] & (el > R_(20)) & (np.abs(az) > R_(40)), 30, 0.025, seed=91)
    for p, nn in zip(roots, rn):
        out = H.radial(p[None])[0]
        d0 = flow(p[None])[0]
        Pp = grow(H, p, out, rng.uniform(0.04, 0.09), d0 + out * rng.uniform(0.05, 0.2) + rng.normal(0, 0.15, 3), 10, 0.12, 1.0, 0.6,
                  0.016, 0.3, 0.004, None, 0.0, 0.0, clear=0.014, guard=guard, body_clear=0.02)
        if len(Pp) >= 4:
            b.card(Pp, 0.004, 0.0012, int(rng.choice(wisp)))
    def hl_dir(p, a):
        """Growth direction at the hairline: away from the parting and back over the head at the front, down/back
        over the temples and behind the ears."""
        sd = (1.0 if p[0] >= part_x else -1.0) * (0.3 + 0.7 * ss(0.004, 0.012, abs(p[0] - part_x)))
        fa = ss(45, 85, abs(math.degrees(a)))
        d = np.array((sd * 0.9, 0.75, 0.45)) * (1 - fa) + np.array((sd * 0.25, 0.55, -1.0)) * fa
        return H.tangent(p[None], d[None])[0]
    b.hairline_cards(hairline, hl_dir, fringe_t, az_max=128.0, step_deg=1.35, L=(0.035, 0.065), w=(0.0055, 0.0075), off=0.0015,
                     guard=guard, rows=3, tiles_dense=fringe_t + [18, 19], row_step=2.3)
    # textures (v5 tiles: clump structure + value families that survive mip-mapping)
    img = np.zeros((ATLAS, ATLAS, 4), np.float32)
    specs = []
    vals = [0.5, 0.58, 0.66, 0.74, 0.84, 0.92, 1.0, 1.06]
    for k in range(24):
        if k < 12:
            specs.append(dict(v5=True, wave=0.25, band=[0.05, 0.10, 0.16, 0.23][k // 3], value=[0.86, 1.0, 1.1][k % 3], tip_min=0.45,
                              per=32, under=80))
        elif k < 20:
            specs.append(dict(v5=True, wave=0.25, band=None, value=vals[k - 12], tip_min=0.45, per=32, under=80))
        elif k < 22:
            specs.append(dict(n=10, wave=0.5, clumps=(1, 2), spread=0.15, tip_min=0.6, sparse=True, width=(0.8, 1.2)))
        else:
            specs.append(dict(v5=True, wave=0.15, clumps=(5, 8), per=9, under=14, cw=(0.06, 0.12), cval=(0.75, 1.0), tip_min=0.35,
                              width=(0.9, 1.3), root_dark=0.12, root_stagger=0.32, converge=0.15, edge_fade=0.25))
    paint_atlas_tiles(img, specs, rng)
    partf = lambda P, el_: np.where((el_ > R_(35)) & (P[:, 1] < H.hc[1] + 0.03), P[:, 0] - part_x, 1.0)
    paint_cap(H, vol, img, flow, None, partf, [k + 2.6 for k in hairline], soft=4.0, band_el=None, stroke=(0.02, 0.05), lum_mul=0.62,
              part_cut=False)
    return vol, finish(img, 0.74)


# ============================================================================= Kael: side_part_volume


def build_side_part(b):
    H, rng = b.H, b.rng
    b.kind = "rigid"
    b.cutoff = 0.4
    part_x = 0.036
    hairline = [30, 28, 24, 13, 5, -8, -24, -31, -34]          # temples slightly recessed
    cap_line = [k - 6 for k in hairline]
    mask, az, el = H.scalp(cap_line)

    def big(P):
        return P[:, 0] < part_x

    def flow(P):
        az_, el_, r_ = H.angles(P)
        side = np.where(big(P), -1.0, 1.0)
        top = ss(R_(18), R_(50), el_)
        back = ss(R_(80), R_(150), np.abs(az_))
        F = np.stack([side * (0.5 + 0.4 * top) * (1 - 0.5 * back), 0.55 + 0.35 * back, -0.2 - 0.8 * (1 - top)], 1)
        return H.tangent(P, F)

    def dens(az_, el_, P):
        a = np.degrees(np.abs(az_))
        lo = np.interp(a, [0, 45, 70, 110, 150, 180], [-40, -40, -6, -8, -22, -26])
        hi = np.interp(a, [0, 45, 70, 110, 150, 180], [-30, -30, 18, 16, 2, -2])
        return 0.08 + 0.92 * ss(R_(lo), R_(hi), el_)

    def brow_guard(q, p):
        if q[1] < H.eye[1] + 0.03 and abs(q[0]) < H.face_hw + 0.01 and q[2] < H.brow_z + 0.03:
            return None
        a_, e_, _ = H.angles(q[None])
        if abs(a_[0]) < R_(72) and e_[0] < H.hairline_el(a_, hairline)[0] + R_(1.0):
            return None           # swept-back style: nothing hangs onto the forehead (no stray 'blade' cards)
        return q

    vol = volume_shell(H, b.ctx, b.sid + "_cap", mask,
                       lambda a_, e_: 0.0015 + 0.0045 * ss(R_(12), R_(42), e_) * (1 - 0.5 * ss(R_(100), R_(170), np.abs(a_))))
    cm = H.scalp(hairline)[0]
    co = b.ctx.basis
    # ---------------- top: layered swept cards with a front quiff
    tiles_top = list(range(0, 12))
    tiles_side = list(range(12, 20))
    wisp = [20, 21]
    fringe_t = [22, 23]
    for li, (n, off0, off1, lift, Lm) in enumerate([(390, 0.0022, 0.0042, 0.09, 1.0), (300, 0.0045, 0.0068, 0.15, 0.95),
                                                    (190, 0.0068, 0.0095, 0.22, 0.9)]):
        zone = cm & ((el > R_(24)) | ((np.abs(az) < R_(55)) & (el > R_(14))))
        roots, rn = H.sample_roots(zone, n, 0.0056, seed=11 + 13 * li)
        F0 = flow(roots)
        for p, nn, f in zip(roots, rn, F0):
            a_, e_, _ = H.angles(p[None]); ad = abs(math.degrees(a_[0])); ed = math.degrees(e_[0])
            front = ad < 50
            L = (0.095 if front else 0.075 - 0.02 * ss(90, 160, ad)) * Lm * rng.uniform(0.85, 1.12)
            L *= 1 - 0.3 * ss(55, 100, ad) * (1 - ss(30, 50, ed))      # shorter where the top meets the sides (no flare)
            if p[0] >= part_x:
                L *= 0.7
            lf = lift + (0.24 if front and ed < 40 else 0.0)
            backv = np.array((np.sign(part_x - p[0]) * 0.25, 1.0, 0.15))
            curve = (lambda s_, q, d, bv=backv: bv * 0.35 * ss(0.05, 0.6, s_)) if front else None
            off = rng.uniform(off0, off1)
            hg = 0.75 + 0.6 * ss(50, 90, ad)
            Pp = grow(H, p, nrm(nn * 0.4 + H.radial(p[None])[0] * 0.6), L, f + rng.normal(0, 0.08, 3), 12, lf, 1.25, 0.08, off, hg,
                      0.005, None, 0.0, 0.0, clear=off * 0.75, guard=brow_guard, body_clear=0.006, curve=curve)
            if len(Pp) < 4:
                continue
            Pp = np.array([Pp[0]] + [H.collide(q, off * 0.7, 0.006) for q in Pp[1:]])
            tl = [tiles_top[k] for k in ((0, 1, 2, 3) if li == 0 else (2, 3, 4, 5, 6, 7) if li == 1 else (6, 7, 8, 9, 10, 11))]
            b.card(Pp, rng.uniform(0.0058, 0.0082), rng.uniform(0.0012, 0.0022), int(rng.choice(tl)), jitter=0.16,
                   twist=rng.normal(0, 0.2))
    # ---------------- sides and back: short layered cards lying down/back, getting shorter towards the fade
    zone = cm & (el > R_(-10)) & ~((el > R_(24)) | ((np.abs(az) < R_(55)) & (el > R_(14))))
    roots, rn = H.sample_roots(zone, 360, 0.0058, seed=77)
    F0 = flow(roots)
    for p, nn, f in zip(roots, rn, F0):
        a_, e_, _ = H.angles(p[None])
        dd = float(dens(a_, e_, p[None])[0])
        if dd < 0.3:
            continue
        L = (0.008 + 0.038 * dd ** 1.5) * rng.uniform(0.85, 1.15)
        Pp = grow(H, p, nn, L, f, 7, 0.05, 1.0, 0.1, 0.0022, 1.2, 0.0, None, 0.0, 0.0, clear=0.0018, body_clear=0.004)
        if len(Pp) >= 3:
            b.card(Pp, rng.uniform(0.0055, 0.007), 0.0018, int(rng.choice(tiles_side)), jitter=0.12)
    # a few strays on top
    roots, rn = H.sample_roots(cm & (el > R_(35)), 14, 0.03, seed=5)
    for p, nn in zip(roots, rn):
        d0 = flow(p[None])[0] + H.radial(p[None])[0] * 0.3
        Pp = grow(H, p, nn, rng.uniform(0.035, 0.06), d0, 6, 0.22, 1.2, 0.12, 0.010, 0.0, 0.0, None, 0.0, 0.0, clear=0.008, body_clear=0.01)
        if len(Pp) >= 3:
            b.card(Pp, 0.004, 0.001, int(rng.choice(wisp)))
    def hl_dir(p, a):
        """Hairline growth: up and back from the forehead, swept away from the parting; down/back at the temples."""
        sd = (-1.0 if p[0] < part_x else 1.0) * ss(0.004, 0.012, abs(p[0] - part_x))
        fa = ss(50, 80, abs(math.degrees(a)))
        d = np.array((sd * 0.35, 0.85, 0.75)) * (1 - fa) + np.array((math.copysign(0.2, p[0]), 0.8, -0.7)) * fa
        return H.tangent(p[None], d[None])[0]
    b.hairline_cards(hairline, hl_dir, fringe_t, az_max=78.0, step_deg=1.4, L=(0.022, 0.04), w=(0.005, 0.0068), off=0.0014,
                     guard=None, segs=7, rows=3, tiles_dense=fringe_t + [3, 4, 5], row_step=2.2)
    # ---------------- textures (v5 tiles: clump structure, value families)
    img = np.zeros((ATLAS, ATLAS, 4), np.float32)
    tv = [0.62, 0.7, 0.78, 0.86, 0.92, 1.0, 0.82, 0.9, 0.96, 1.02, 1.08, 1.12]
    specs = ([dict(v5=True, wave=0.05, tip_min=0.35, converge=0.5, value=tv[k], per=30, under=70, cw=(0.1, 0.2), root_dark=0.3)
              for k in range(12)] +
             [dict(v5=True, wave=0.0, tip_min=0.3, converge=0.4, value=v, per=28, under=60, root_dark=0.25)
              for v in (0.6, 0.68, 0.76, 0.84, 0.9, 0.96, 0.72, 0.8)] +
             [dict(n=8, wave=0.2, clumps=(1, 2), spread=0.15, tip_min=0.6, sparse=True, width=(0.9, 1.3))] * 2 +
             [dict(v5=True, wave=0.05, clumps=(5, 8), per=9, under=14, cw=(0.06, 0.12), cval=(0.75, 1.0), tip_min=0.35,
                   width=(0.9, 1.3), root_dark=0.12, root_stagger=0.32, converge=0.2, edge_fade=0.25)] * 2)
    paint_atlas_tiles(img, specs, rng)
    partf = lambda P, el_: np.where((el_ > R_(26)) & (P[:, 1] < H.hc[1] + 0.02), P[:, 0] - part_x, 1.0)
    paint_cap(H, vol, img, flow, dens, partf, [k + (2.6 if i < 4 else 1.6) for i, k in enumerate(hairline)], soft=4.0, band_el=None,
              stroke=(0.008, 0.02), lum_mul=0.7, part_cut=False)
    return vol, finish(img, 0.8)


STYLES = {"long_waves": ("lyra", "Long Waves", build_long_waves), "side_part_volume": ("kael", "Slicked Side Part", build_side_part)}


def main():
    a = C.args()
    cid, sid = a[0], a[1]
    rig, body = C.load_ref(cid)
    ctx = gear.Ctx(body, rig, C.HEROES[cid]["name"])
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name.startswith("U_") and o.name[2:] in ("Top", "Collar", "Jacket", "ChestRig", "PauldronL", "PauldronR",
                                                                         "PauldronLameL", "PauldronLameR", "ShoulderR", "Harness", "ChestPlate"):
            nf = HL.orient_outward(o, ctx)
            ctx.push_stack(o)
    H = Head(ctx, female=cid == "lyra")
    C.log("head", H.hc.round(4), "top", round(H.top, 4), "face_hw", round(H.face_hw, 4))
    studio.hero_materials(cid)
    t0 = time.time()
    b = V4(H, ctx, cid, sid)
    vol, atlas = STYLES[sid][2](b)
    cards = b.part.build(mat_order=["Hair"], max_edge=None)
    obj = gear.join([vol, cards], f"{cid}_{sid}")
    for p in obj.data.polygons:
        p.use_smooth = True
    env_normals(obj, H)
    tex = os.path.join(HBD.TEX_DIR, f"{cid}_{sid}_Hair.png")
    C.write_png(atlas, tex, "RGBA")
    ntri = C.tris(obj)
    C.log(sid, "tris", ntri, "cards", b.ncards, "s", round(time.time() - t0, 1))
    thumb, prevs = HBD.preview_and_thumb(cid, sid, obj, tex, b, H)
    # in-game colour previews (the appearance default hair colour)
    ingame = {"kael": "#1d1714", "lyra": "#2a1a1e"}[cid]
    obj.data.materials[0] = studio.hair_mat(f"ig_{sid}", tex, ingame, b.cutoff)
    hc = Vector(H.hc)
    aim = hc + Vector((0, 0, -0.035 if cid == "kael" else -0.07))
    dist = 0.95 if cid == "kael" else 1.25
    for tag, yaw, pitch in (("ig_q34", 32, 6), ("ig_front", 0, 3), ("ig_back", 160, 8), ("ug_front", 8, 3)):
        studio.world_and_lights(hc, 0.6, rim=1.0, yaw=yaw)
        studio.camera(studio.view(aim, yaw, pitch, dist * (0.7 if tag.startswith("ug") else 1.0)), aim, 70)
        sc = bpy.context.scene
        if tag.startswith("ug"):
            sc.eevee.taa_render_samples = 1
            sc.render.filter_size = 0.01
        studio.render(os.path.join(HBD.PREV_DIR, f"{cid}_{sid}_{tag}.png"), 900 if tag.startswith("ug") else 512)
        sc.render.filter_size = 1.5
    bpy.data.libraries.write(os.path.join(C.CACHE, f"hairobj_{cid}_{sid}.blend"), {obj}, fake_user=True, compress=True)
    if "--no-export" not in a:
        obj.data.materials[0] = gear.get_mat("Hair")
        HBD.export_hair(cid, sid, obj, b, H, rig)
        entry = {"id": sid, "label": STYLES[sid][1], "hero": cid, "file": f"Hair/{cid}_{sid}", "kind": b.kind, "bone": "mixamorig:Head",
                 "thumb": f"Thumbs/hair_{cid}_{sid}", "alphaCutoff": b.cutoff, "baseMap": f"Hair/Textures/{cid}_{sid}_Hair",
                 "material": "Hair", "tint": "hair", "tris": ntri, "localPos": [0, 0, 0], "localRot": [0, 0, 0], "pipeline": "hair v5 (layered strand cards, soft hairline)"}
        if b.kind == "skinned":
            entry["bones"] = ["mixamorig:Head", "mixamorig:Neck", "mixamorig:Spine2"]
        with open(os.path.join(C.CACHE, "catalog", "hair", f"{cid}_{sid}.json"), "w") as f:
            json.dump(entry, f, indent=1)
        import catalog
        catalog.merge()
    C.log("done")


if __name__ == "__main__":
    main()
