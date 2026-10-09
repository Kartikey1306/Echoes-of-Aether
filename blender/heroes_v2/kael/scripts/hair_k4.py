"""Kael built-in hair 'swept_fade', v4 (concept dreamlayer/characters/kael/kael_master_front.png): mid-brown hair
swept up from a parting on his left, back and over to his right with real volume, a fringe lock falling onto the
forehead on his right and the right side falling over the temple; his left side (below and beside the parting) is
shaved short silver/grey (painted into the skin by skin_k2; the cap is transparent there).

Construction (all modelled here, no scanned or generated assets):
  * a sculpted volume shell = the style's mass (thickness envelope T(az, el): ~3 cm at the front-top, tapering to the
    crown, the right side and a short nape), painted in 3-D with flow-aligned strands (hair v4 cap painter);
  * three layers of strand cards that climb to a fraction of the envelope and then follow the flow field at that
    height, so the cards build one cohesive swept shape instead of a fan of loose ribbons;
  * an explicit fringe lock (up, over and down onto the right forehead) and soft hairline cards.
Uses the hair v4 card library (blender/custom, read-only); run in its own Blender process.

  blender -b blends/kael_s3_outfit.blend --python scripts/hair_k4.py -- [--fast] [--preview tag]
Writes blends/hair_k3.blend (object Hair_swept_fade, Head-rigid; the file name is what the export/face stages read)
and tex/Hair_swept_fade_Color.png (RGBA, grey).
"""
import bpy, os, sys, math, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
KROOT = os.path.abspath(os.path.join(HERE, ".."))
CUSTOM = os.path.abspath(os.path.join(KROOT, "..", "..", "custom"))
sys.path.insert(0, CUSTOM)
sys.path.insert(1, os.path.join(CUSTOM, "lib"))
import numpy as np
from mathutils import Vector
import common as C
import gear
import hair_v4 as HV
import hairlib as HL
from hairlib import Head, volume_shell, arclen
from common import ss, nrm, nrm_rows

R_ = np.radians
STYLE = "swept_fade"
PART_X = 0.052           # parting high on his left (+x), at the edge of the top; the top sweeps over to his right (-x)
ARGS = C.args()
FAST = "--fast" in ARGS
HAIRLINE = [30, 28, 24, 13, 5, -8, -24, -31, -34]
VOLUME = 1.12            # makeover: fuller mass (envelope scale)


def shaved(P, az, el):
    """1 on his shaved left side (below the parting line, forward of the back of the head)."""
    a = np.degrees(np.abs(az))
    side = ss(PART_X + 0.002, PART_X + 0.011, P[:, 0])
    back = 1 - ss(128, 160, a)
    return side * back


def env_T(az, el, x):
    """Thickness (m) of the style's mass above the scalp."""
    a = np.degrees(az); e = np.degrees(el)
    top = ss(14, 44, e)
    back = ss(112, 165, np.abs(a))
    T = 0.006 + 0.01 * top
    T += 0.03 * ss(10, 36, e) * ss(85, 20, np.abs(a + 18)) * (1 - 0.35 * ss(70, 88, e))   # quiff / volume over the front-top
    T += 0.0075 * ss(-30, -78, a) * ss(-8, 24, e) * (1 - back)                    # the sweep falling over his right side
    T *= 1 - 0.6 * back * ss(36, -4, e)                                            # short tapered nape
    T *= 1 - 0.85 * ss(PART_X - 0.012, PART_X + 0.004, x) * (1 - ss(128, 160, np.abs(a)))   # rises steeply out of the parting
    # makeover: more volume (concept: a full swept mass), most of it in the quiff over the front-top
    T *= VOLUME * (1 + 0.06 * ss(10, 36, e) * ss(85, 20, np.abs(a + 18)))
    return T


def make_flow(H):
    def flow(P):
        az, el, r = H.angles(P)
        a = np.degrees(az); e = np.degrees(el)
        n = len(P)
        right = ss(-28, -70, a) * ss(40, 10, e)          # his right side, below the top: falls down and back
        back = ss(105, 150, np.abs(a))
        F = np.stack([-np.ones(n) * 0.95, 0.42 + 0.25 * ss(30, 80, np.abs(a)), 0.08 * ss(40, 20, e)], 1)
        F = F * (1 - right[:, None]) + np.stack([np.full(n, -0.25), np.full(n, 0.45), np.full(n, -1.0)], 1) * right[:, None]
        Fb = np.stack([np.sign(P[:, 0] - 0.0) * 0.18 - 0.2, np.full(n, 0.55), np.full(n, -1.0)], 1)
        F = F * (1 - back[:, None]) + Fb * back[:, None]
        # the short left side and the faded area: combed down and back
        sh = shaved(P, az, el)
        Fs = np.stack([np.full(n, 0.35), np.full(n, 0.5), np.full(n, -1.0)], 1)
        F = F * (1 - sh[:, None]) + Fs * sh[:, None]
        return H.tangent(P, F)
    return flow


def grow_env(H, root, n0, L, frac, flow, segs=12, guard=None, droop=0.0, climb=0.9):
    """Card centre line: climbs from the root to `frac` of the envelope thickness, then follows the flow at that
    height (droop pulls it down past the envelope's edge, e.g. over the temple)."""
    step = L / segs
    p = np.asarray(root, np.float64) + nrm(n0) * 0.0008
    P = [p]
    for i in range(segs):
        s = (i + 0.5) / segs
        az, el, r = H.angles(p[None])
        R0 = H.R(az, el)[0]
        h = r[0] - R0
        xs = H.surf(az, el, 0.0)[0][0]
        Tl = float(env_T(az, el, np.array([xs]))[0])
        ht = frac * Tl + 0.0012
        F = flow(p[None])[0]
        rad = nrm(p - H.hc)
        dr = float(np.clip((ht - h) / max(step, 1e-4), -1.6, 1.6)) * climb
        d = nrm(F + rad * dr + np.array((0, 0, -1.0)) * droop * s)
        q = p + d * step
        q = H.collide(q, 0.0011, 0.0035)
        if guard is not None:
            q = guard(q, p)
            if q is None:
                break
        if np.linalg.norm(q - p) < 1e-6:
            break
        P.append(q)
        p = q
    return np.array(P)


def settle(H, P, frac, iters=5):
    """Combed look: smooth the centre line and keep everything past the root at its layer height on the envelope (no
    strands sticking out into spikes)."""
    P = np.array(P, np.float64)
    if len(P) < 4:
        return P
    n = len(P)
    s = np.linspace(0, 1, n)
    for _ in range(iters):
        Q = P.copy()
        Q[1:-1] = P[1:-1] * 0.5 + (P[:-2] + P[2:]) * 0.25
        Q[-1] = P[-1] * 0.6 + P[-2] * 0.4
        P = np.where((s > 0.12)[:, None], Q, P)
    az, el, r = H.angles(P)
    R0 = H.R(az, el)
    xs = H.surf(az, el, 0.0)[:, 0]
    T = env_T(az, el, xs)
    h = r - R0
    hmax = frac * T * 1.0 + 0.0012          # final pass: tighter band -> one smooth swept surface, no spikes
    hmin = np.minimum(frac * T * 0.88, hmax) + 0.001
    hn = np.clip(h, hmin, hmax)
    k = ss(0.1, 0.3, s)
    hn = h * (1 - k) + hn * k
    upper = el > np.radians(-35)
    dirs = nrm_rows(P - H.hc)
    P2 = np.where(upper[:, None], H.hc + dirs * (R0 + hn)[:, None], P)
    return np.array([P2[0]] + [H.collide(q, 0.0011, 0.0035) for q in P2[1:]])


def catmull(pts, n):
    P = [np.asarray(p, np.float64) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    seg = len(P) - 3
    out = []
    for i in range(n):
        x = i / (n - 1) * seg
        k = min(int(x), seg - 1)
        t = x - k
        p0, p1, p2, p3 = P[k], P[k + 1], P[k + 2], P[k + 3]
        out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return np.array(out)


def build(b):
    H, rng = b.H, b.rng
    b.kind = "rigid"
    b.cutoff = 0.4
    cap_line = [k - 5 for k in HAIRLINE]
    mask, az, el = H.scalp(cap_line)
    co = b.ctx.basis
    sh_v = shaved(co, az, el)
    flow = make_flow(H)

    def thick(az_, el_):
        # inner mass at about half the envelope (the cards build the outer half), thin at the front hairline so its
        # edge never reads as a helmet rim
        x = H.surf(az_, el_, 0.0)[..., 0]
        hl = H.hairline_el(az_, HAIRLINE)
        return (0.6 * env_T(az_, el_, x) + 0.0015) * (0.25 + 0.75 * ss(hl, hl + R_(12), el_))
    vol = volume_shell(H, b.ctx, b.sid + "_cap", mask & (sh_v < 0.6), thick)
    cm = H.scalp(HAIRLINE)[0] & (sh_v < 0.35)
    tiles_top = list(range(0, 12))
    tiles_side = list(range(12, 20))
    wisp = [20, 21]
    fringe_t = [22, 23]

    def brow_guard(q, p):
        # nothing over the eyes; the fringe lock is built separately
        if q[2] < H.brow_z + 0.016 and abs(q[0]) < H.face_hw + 0.012 and q[1] < H.eye[1] + 0.035:
            return None
        return q

    # ---------------- three layers of strand cards following the envelope
    layers = [(190, 0.0064, 0.62, (0, 1, 2, 3, 4, 5)), (190, 0.0068, 0.82, (3, 4, 5, 6, 7, 8)), (130, 0.0076, 0.95, (6, 7, 8, 9, 10, 11))]
    for li, (n, mind, frac, tl) in enumerate(layers):
        roots, rn = H.sample_roots(cm, n, mind, seed=31 + 17 * li)
        for p, nn in zip(roots, rn):
            a_, e_, _ = H.angles(p[None]); ad = math.degrees(a_[0]); ed = math.degrees(e_[0])
            top = ed > 26
            front = abs(ad + 15) < 60
            if top and front:
                Lc = rng.uniform(0.12, 0.165)
            elif top:
                Lc = rng.uniform(0.085, 0.12)
            elif ad < -25 and abs(ad) < 125:
                Lc = rng.uniform(0.06, 0.09)         # his right side: falls over the temple
            else:
                Lc = rng.uniform(0.035, 0.06)        # back / nape: short
            droop = 0.5 if (ad < -30 and abs(ad) < 120) else 0.0
            jit = rng.normal(0, 0.02 if li < 2 else 0.012, 3)
            fl = (lambda P_, j=jit: H.tangent(P_, flow(P_) + j[None, :]))
            fr_ = frac * rng.uniform(0.94, 1.06)
            Pp = grow_env(H, p, nn, Lc, fr_, fl, segs=10, guard=brow_guard, droop=droop)
            if len(Pp) < 4:
                continue
            if droop == 0.0:
                Pp = settle(H, Pp, fr_)
            w0 = rng.uniform(0.0095, 0.0128) * (0.9 if li == 2 else 1.0)
            b.card(Pp, w0, rng.uniform(0.0036, 0.005), int(rng.choice(tl)), jitter=0.005, twist=rng.normal(0, 0.005))
    # ---------------- side / back short cards (texture density over the cap edge)
    zone = cm & (el < R_(26))
    roots, rn = H.sample_roots(zone, 120, 0.0075, seed=77)
    for p, nn in zip(roots, rn):
        Pp = grow_env(H, p, nn, rng.uniform(0.025, 0.045), 0.8, flow, segs=7, guard=brow_guard)
        if len(Pp) >= 3:
            b.card(Pp, rng.uniform(0.006, 0.0075), 0.0018, int(rng.choice(tiles_side)), jitter=0.1)
    # ---------------- fringe lock: rises off the front hairline on his right, arcs over and falls onto the forehead
    fz = H.brow_z
    for k in range(13):
        t = k / 12.0
        x0 = 0.004 - 0.03 * t + rng.normal(0, 0.002)
        ar = math.atan2(x0, 0.08)
        e0 = H.hairline_el(np.array([ar]), HAIRLINE)[0] + R_(2.5 + rng.uniform(0, 2.0))
        p0 = H.surf(np.array([ar]), np.array([e0]), 0.0)[0]
        n0 = H.radial(p0[None])[0]
        up = p0 + n0 * 0.016 + np.array((-0.01, 0.004, 0.012))
        over = p0 + n0 * 0.024 + np.array((-0.03 - 0.008 * t, -0.006, 0.0))
        end_x = -0.018 - 0.034 * t + rng.normal(0, 0.003)
        end_z = fz + 0.013 + 0.02 * t + rng.normal(0, 0.003)
        ea = math.atan2(end_x, 0.08)
        eel = math.asin(np.clip((end_z - H.hc[2]) / 0.1, -0.9, 0.9))
        endp = H.surf(np.array([ea]), np.array([eel]), 0.005 + 0.002 * t)[0]
        mid = (over + endp) * 0.5 + H.radial(((over + endp) * 0.5)[None])[0] * 0.008
        P = catmull([p0 + n0 * 0.001, up, over, mid, endp], 18)
        P = np.array([P[0]] + [H.collide(q, 0.0035, 0.0035) for q in P[1:]])
        b.card(P, rng.uniform(0.01, 0.013), 0.0018, int(rng.choice([4, 5, 6, 7, 9])), jitter=0.06)
        if k % 2 == 0:
            b.card(P + H.radial(P) * 0.0025, rng.uniform(0.005, 0.007), 0.0012, int(rng.choice(wisp)), jitter=0.08)
    # ---------------- a few wisps over the crown for a soft silhouette
    roots, rn = H.sample_roots(cm & (el > R_(40)), 0, 0.025, seed=5) if False else ([], [])
    for p, nn in zip(roots, rn):
        Pp = grow_env(H, p, nn, rng.uniform(0.05, 0.08), 1.08, flow, segs=8, guard=brow_guard)
        if len(Pp) >= 3:
            b.card(Pp, 0.004, 0.001, int(rng.choice(wisp)))

    # ---------------- soft hairline on the haired part of the hairline
    def hl_dir(p, a):
        # hairline hairs lie down and lead into the sweep (up and back at the front, down on the sides)
        F = flow(p[None])[0]
        return H.tangent(p[None], (F + np.array((0.0, 0.35, 0.45)) * ss(60, 20, abs(math.degrees(a))))[None])[0]

    def hl_guard(q, p):
        a_, e_, _ = H.angles(q[None])
        return None if float(shaved(q[None], a_, e_)[0]) > 0.3 else q
    b.hairline_cards(HAIRLINE, hl_dir, fringe_t, az_max=150.0, step_deg=2.2, L=(0.02, 0.036), w=(0.0055, 0.0072), off=0.0014,
                     guard=hl_guard, segs=6, rows=1, tiles_dense=fringe_t + [3, 4, 5], row_step=2.4)
    # ---------------- strand atlas + 3-D painted cap
    img = np.zeros((HV.ATLAS, HV.ATLAS, 4), np.float32)
    # makeover: narrower value spread between tiles (neighbouring cards read as one mass, not as light/dark bands)
    tv = [0.74, 0.79, 0.82, 0.86, 0.89, 0.93, 0.84, 0.87, 0.9, 0.93, 0.96, 0.99]
    specs = ([dict(v5=True, wave=0.03, tip_min=0.55, converge=0.5, value=tv[k], per=30, under=70, cw=(0.1, 0.2), root_dark=0.3)
              for k in range(12)] +
             [dict(v5=True, wave=0.0, tip_min=0.3, converge=0.4, value=v, per=28, under=60, root_dark=0.25)
              for v in (0.7, 0.75, 0.8, 0.85, 0.9, 0.94, 0.78, 0.83)] +
             [dict(n=8, wave=0.2, clumps=(1, 2), spread=0.15, tip_min=0.6, sparse=True, width=(0.9, 1.3))] * 2 +
             [dict(v5=True, wave=0.05, clumps=(5, 8), per=9, under=14, cw=(0.06, 0.12), cval=(0.75, 1.0), tip_min=0.35,
                   width=(0.9, 1.3), root_dark=0.12, root_stagger=0.32, converge=0.2, edge_fade=0.25)] * 2)
    HV.paint_atlas_tiles(img, specs, rng)

    def dens(az_, el_, P):
        a = np.degrees(np.abs(az_))
        lo = np.interp(a, [0, 45, 70, 110, 150, 180], [-40, -40, -6, -8, -22, -26])
        hi = np.interp(a, [0, 45, 70, 110, 150, 180], [-30, -30, 18, 16, 2, -2])
        d = 0.08 + 0.92 * ss(R_(lo), R_(hi), el_)
        return d * (1 - shaved(P, az_, el_))
    partf = lambda P, el_: np.where((el_ > R_(26)) & (P[:, 1] < H.hc[1] + 0.02), P[:, 0] - PART_X, 1.0)
    if FAST:
        S = img.shape[0]
        u0, v0, u1, v1 = HL.VOL_RECT
        ys, ye, xs_, xe = int(v0 * S), int(v1 * S), int(u0 * S), int(u1 * S)
        yy, xx = np.mgrid[ys:ye, xs_:xe]
        img[ys:ye, xs_:xe, 0] = 0.55 + 0.25 * np.sin(xx * 0.9 + np.sin(yy * 0.05) * 3)
        img[ys:ye, xs_:xe, 3] = 1.0
    else:
        HV.paint_cap(H, vol, img, flow, dens, partf, [k + (2.6 if i < 4 else 1.6) for i, k in enumerate(HAIRLINE)], soft=4.0,
                     band_el=None, stroke=(0.008, 0.02), lum_mul=0.82, part_cut=False)
    return vol, HV.finish(img, 0.64)        # final pass: darker brown (concept)


def strand_data(obj, H):
    """Second UV set 'Strand' for EOA/Hair (_STRAND_DATA): x = root (0) -> tip (1) along the card (from the tile's v
    range; card_strip runs v from the tile top at the root to the bottom at the tip), y = inner-layer occlusion
    (1 deep in the mass near the scalp, 0 at the outer surface of the envelope). The painted cap gets x -1 / y 0.6."""
    me = obj.data
    nl = len(me.loops)
    uv = np.empty(nl * 2, np.float32); me.uv_layers[0].data.foreach_get("uv", uv); uv = uv.reshape(-1, 2).astype(np.float64)
    lv = np.empty(nl, np.int32); me.loops.foreach_get("vertex_index", lv)
    co = gear.get_co(obj)
    hv = gear.attr(obj, "hairvol")
    u, v = uv[:, 0], uv[:, 1]
    top = v >= 0.5
    vt = np.where(top, 1.0 - 0.004, 0.5 - 0.004)
    vb = np.where(top, 0.5 + 0.004, 0.004)
    t = np.clip((vt - v) / (vt - vb), 0, 1)
    az, el, r = H.angles(co)
    env = np.maximum(env_T(az, el, co[:, 0]), 0.005)
    occ_v = 1 - np.clip(H.height(co) / env, 0, 1)
    occ = np.clip(occ_v[lv], 0, 1) ** 1.3
    cap = (hv[lv] > 0.5) | ((u < 0.5) & (v < 0.5))
    x = np.where(cap, -1.0, t)          # x < 0 flags the cap for EOA/Hair (matte, no root fade)
    y = np.where(cap, 0.6, occ)
    lay = me.uv_layers.get("Strand") or me.uv_layers.new(name="Strand")
    lay.data.foreach_set("uv", np.stack([x, y], 1).astype(np.float32).ravel())
    me.uv_layers.active_index = 0
    for i, l in enumerate(me.uv_layers):
        l.active_render = (i == 0)
    C.log("STRAND data", "loops", nl, "cap", int(cap.sum()), "occ mean", round(float(y[~cap].mean()), 3) if (~cap).any() else None)


def main():
    rig = bpy.data.objects["Kael"]
    body = bpy.data.objects.get("BodyFull") or bpy.data.objects["Body"]
    for o in list(bpy.data.objects):
        if o.type == "MESH" and (o.name.startswith("Hair_") or o.name.startswith("Facial_")):
            bpy.data.objects.remove(o, do_unlink=True)
    ctx = gear.Ctx(body, rig, "Kael")
    for n in ("Top", "Collar", "Jacket", "ChestRig", "PauldronL", "PauldronR", "PauldronLameL", "PauldronLameR"):
        o = bpy.data.objects.get(n)
        if o is not None:
            HL.orient_outward(o, ctx)
            ctx.push_stack(o)
    H = Head(ctx, female=False)
    C.log("head", H.hc.round(4), "top", round(H.top, 4), "face_hw", round(H.face_hw, 4))
    t0 = time.time()
    b = HV.V4(H, ctx, "kael", STYLE)
    vol, atlas = build(b)
    cards = b.part.build(mat_order=["Hair"], max_edge=None)
    obj = gear.join([vol, cards], "Hair_" + STYLE)
    for p in obj.data.polygons:
        p.use_smooth = True
    HV.env_normals(obj, H, mix=0.35)
    strand_data(obj, H)
    tex = os.path.join(KROOT, "tex", f"Hair_{STYLE}_Color.png")
    C.write_png(atlas, tex, "RGBA")
    C.log(STYLE, "tris", C.tris(obj), "cards", b.ncards, "s", round(time.time() - t0, 1))
    obj.data.name = obj.name
    bpy.data.libraries.write(os.path.join(KROOT, "blends", "hair_k3.blend"), {obj}, fake_user=True, compress=True)
    json.dump({"style": STYLE, "cutoff": b.cutoff, "tris": C.tris(obj), "part_x": PART_X, "builder": "hair_k4"},
              open(os.path.join(KROOT, "logs", "hair_k3.json"), "w"), indent=1)
    C.log("done")


if __name__ == "__main__":
    main()
