"""High-definition (2K) material definitions for the main Aether-9 surfaces.

Same contract as matdefs.py (define(nb, p) -> dict of sockets), plus:
  masks : {name: float socket}  extra fields baked for the post stage
  post  : numpy weathering pass (texops) - rain streaks, drips below cracks/bolts/chips, cavity dirt,
          convex-edge wear, wet darkening, puddles with flat water and damp rims.
Mask names used by `weather()`:
  rainseed  sparse noise; its peaks start long rain/grime streaks
  jit       noise stretched along V (vertical bands) that modulates streaks per column
  drip      sources of short dark drips (cracks, bug holes, seams, bolts)
  rust      sources of rust-coloured runoff (rust spots, bolts, fasteners)
  pud       large noise field for puddles (wet materials)
  damp      noise for patchy wetness
Walls get box-projected UVs with V = world up, so streaks always run down on vertical faces.
"""
import numpy as np

import texops as X
from matdefs_base import lin, g, crack_lines

GRIME = np.array(lin("#2e2a24"))
RUST = np.array(lin("#6a3416"))
RUST_DARK = np.array(lin("#3a1e10"))
MOSS = np.array(lin("#3c4426"))
SALT = np.array(lin("#c9c6bc"))


def _a(c):
    return np.array(c, np.float32)


def weather(rain=0.0, rain_len=0.9, rain_dark=0.3, drip=0.0, drip_len=0.25, drip_dark=0.35, rust=0.0, rust_len=0.35,
            cavity=0.25, cav_r=0.006, edge=0.0, edge_r=0.003, edge_col=None, grime=GRIME, wet=None, extra=None, salt=0.0):
    """Build a post-process closure. wet: dict(level=coverage 0..1, dark=0.6, rough=0.45, pud_dark=0.4)."""

    def post(st):
        M = st["masks"]
        px = st["px_m"]
        col = st["color"].astype(np.float32)
        rough = st["rough"].astype(np.float32)
        h01 = st["h01"].astype(np.float32)
        hm = h01 * st["depth"]
        jit = X.smooth(M["jit"], 0.25, 0.75) if "jit" in M else None
        streak = np.zeros_like(h01)
        if rain > 0 and "rainseed" in M:
            starts = X.smooth(M["rainseed"], 0.70, 0.76)
            streak = np.maximum(streak, X.drip(starts, rain_len, px, jitter=jit, gain=7.0) * rain)
        if drip > 0 and "drip" in M:
            streak = np.maximum(streak, X.drip(np.clip(M["drip"], 0, 1), drip_len, px, jitter=jit, gain=6.0) * drip)
        if streak.any():
            col = X.lerp(col, X.mulc(col, 1.0 - rain_dark) * 0.6 + _a(grime) * 0.4, np.clip(streak, 0, 1) * 0.9)
            rough = rough + streak * 0.04
        if salt > 0 and "drip" in M:
            # efflorescence: chalky white bloom leaching out just below cracks/voids (shorter than the dark drips)
            sl = X.drip(np.clip(M["drip"], 0, 1), drip_len * 0.45, px, jitter=jit, gain=5.0, spread_px=1.5)
            sl = np.clip(sl - np.clip(M["drip"], 0, 1), 0, 1) * salt
            col = X.lerp(col, SALT * 0.8 + col * 0.2, sl)
            rough = rough + sl * 0.06
        if rust > 0 and "rust" in M:
            rs = X.drip(np.clip(M["rust"], 0, 1), rust_len, px, jitter=jit, gain=5.0) * rust
            rs = np.clip(rs - np.clip(M["rust"], 0, 1), 0, 1)  # the runoff, not the source
            col = X.lerp(col, X.mulc(col, 0.55) * 0.3 + RUST * 0.7, rs * 0.85)
            rough = rough + rs * 0.08
        if cavity > 0:
            cav = X.cavity_mask(hm, px, cav_r, 0.08, 0.7)
            col = X.mulc(col, 1.0 - cavity * cav)
            rough = rough + cav * 0.05
        if edge > 0:
            e = X.edge_mask(hm, px, edge_r, 0.1, 0.55)
            if edge_col is None:
                col = X.mulc(col, 1.0 + edge * e)
            else:
                col = X.lerp(col, _a(edge_col), e * edge)
            rough = rough - e * edge * 0.1
        if extra is not None:
            st.update(color=col, rough=rough, h01=h01)
            st = extra(st) or st
            col, rough, h01 = st["color"], st["rough"], st["h01"]
        if wet:
            lvl = wet.get("level", 0.18)
            damp = X.smooth(M["damp"], 0.3, 0.65) if "damp" in M else np.ones_like(h01)
            hb = X.blur(h01, 0.02 / px)
            hn = (hb - hb.mean()) / max(1e-4, hb.std())
            field = X.blur(M["pud"], 0.03 / px) - hn * 0.025
            thr = np.quantile(field, 1.0 - lvl)
            pud = X.smooth(field, thr - 0.002, thr + 0.006)
            rim = X.rim(pud, 0.012 / px)
            wetness = np.clip(0.55 + 0.45 * damp + rim, 0, 1) * wet.get("amount", 1.0)
            col = X.mulc(col, 1.0 - wet.get("dark", 0.38) * wetness)
            rough = rough * (1.0 - wet.get("rough", 0.5) * wetness)
            col = X.lerp(col, X.mulc(col, 1.0 - wet.get("pud_dark", 0.35)), pud)
            rough = X.lerp(rough, np.full_like(rough, 0.02), pud)
            level = np.quantile(h01, 0.7)
            h01 = X.lerp(h01, np.maximum(h01 * 0.25 + level * 0.75, h01 * 0.0 + level), pud)
            st["masks"]["_puddle"] = pud
        st.update(color=np.clip(col, 0, 1), rough=np.clip(rough, 0.0, 1.0), h01=np.clip(h01, 0, 1))
        return st

    return post


def common_masks(nb, seed, rain_f=26.0, jit_f=70.0, extra=None):
    m = {
        "rainseed": nb.noise(rain_f, detail=2, rough=0.5, seed=seed, fv=rain_f * 0.6),
        "jit": nb.noise(jit_f, detail=3, rough=0.6, seed=seed + 1, fv=1.0),
    }
    if extra:
        m.update(extra)
    return m


def nz(nb, f, lo=0.32, hi=0.68, **kw):
    """Contrast-normalised tileable noise in 0..1 (Blender's normalised 4D fBm mostly lives in 0.3..0.7)."""
    return nb.maprange(nb.noise(f, **kw), lo, hi)


def sn(nb, f, **kw):
    """Signed contrast noise in -0.5..0.5."""
    return nz(nb, f, **kw) - 0.5


# ============================================================================================== concrete
def concrete(nb, p):
    base = p.get("base", g(0.40))
    cloud = sn(nb, 1.6, detail=4, rough=0.55, seed=1)
    mott = sn(nb, 9, detail=6, rough=0.6, seed=2)
    fine = sn(nb, 110, detail=4, rough=0.6, seed=3)
    grain = nb.noise(900, detail=1, seed=4) - 0.5
    agg_d = nb.voronoi(240, seed=5)
    agg_c = nb.voronoi(240, seed=5, out="Color")
    worn = nb.smooth(nz(nb, 3.5, detail=5, seed=6), 0.55, 0.85)
    stones = nb.smooth(agg_d, 0.45, 0.12) * worn
    pin = nb.smooth(nb.voronoi(150, seed=7), 0.06, 0.025) * nb.smooth(nz(nb, 4, seed=8), 0.3, 0.6)
    bug = nb.smooth(nb.voronoi(36, seed=17), 0.05, 0.02) * nb.smooth(nz(nb, 3, seed=18), 0.5, 0.7)
    cracks = crack_lines(nb, 2.0, 9, 0.0042, keep=0.52)
    hair = crack_lines(nb, 6, 10, 0.0018, keep=0.56)
    pcell = nb.voronoi(2.5, seed=11, out="Color")
    pedge = nb.voronoi(2.5, seed=11, feature="DISTANCE_TO_EDGE")
    pj = sn(nb, 24, detail=4, seed=12) * 0.09
    inpatch = nb.lt(pcell, 0.07)
    patch = inpatch * nb.smooth(pedge + pj, 0.02, 0.05)
    prim = inpatch * nb.smooth(pedge + pj, 0.01, 0.02) * nb.smooth(pedge + pj, 0.05, 0.02)
    h = (0.55 + cloud * 0.06 + mott * 0.22 + fine * 0.22 + grain * 0.06 + stones * 0.12 - pin * 0.55 - bug * 0.7
         - cracks * 0.6 - hair * 0.3 + patch * 0.03 - patch * fine * 0.12 - prim * 0.2)
    tone = 1.0 + cloud * 0.32 + mott * 0.26 + fine * 0.1 + grain * 0.16
    col = nb.mulc(base, tone)
    stone_col = nb.ramp(agg_c, [(0.0, lin("#55524d")), (0.35, lin("#8a8680")), (0.7, lin("#6e675e")), (1.0, lin("#a7a196"))])
    col = nb.mixc(col, stone_col, stones * 0.7)
    col = nb.mixc(col, nb.mulc(col, 1.07 + fine * 0.1), patch)
    blot = nb.smooth(nz(nb, 2.2, detail=6, rough=0.62, seed=13), 0.5, 0.9)
    col = nb.mixc(col, nb.mulc(col, 0.62), blot * 0.55)
    col = nb.mixc(col, nb.mulc(col, 0.25), nb.maxf(nb.maxf(pin, bug), cracks))
    col = nb.mixc(col, nb.mulc(col, 0.5), hair * 0.7)
    rough = 0.84 + fine * 0.12 + mott * 0.08 - patch * 0.14 - blot * 0.08 + nb.maxf(pin, bug) * 0.1
    masks = common_masks(nb, 14, extra={"drip": cracks * 0.9 + bug + pin * 0.4 + prim * 0.5 + hair * 0.4})
    if p.get("wet"):
        masks["pud"] = nb.noise(2.0, detail=1.5, rough=0.4, seed=15)
        masks["damp"] = nb.noise(3, detail=3, seed=16)
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp(), "masks": masks,
            "post": weather(rain=0.7, rain_len=1.0, rain_dark=0.35, drip=0.8, drip_len=0.28, drip_dark=0.4, cavity=0.35,
                            edge=0.1, salt=0.35,
                            wet={"level": 0.12, "dark": 0.4, "rough": 0.55, "pud_dark": 0.08} if p.get("wet") else None)}


# ============================================================================================== cyberpunk surfaces
def paint_glossy(nb, p):
    """Dark glossy painted / clear-coated metal (vehicles, kiosks, corporate fittings): swirl marks, dust,
    water spots, fine chips. Tint via params['tint']."""
    paint = p.get("tint", lin("#15181d"))
    flake = nb.noise(900, detail=1, seed=301) - 0.5
    mott = sn(nb, 5, detail=4, seed=302)
    swirl = nb.smooth(nb.absf(nb.noise(8, detail=3, seed=303, distortion=2.5) - 0.5), 0.004, 0.0) * nb.smooth(nz(nb, 4, seed=304), 0.4, 0.7)
    scr = nb.smooth(nb.absf(nb.noise(3, fv=70, detail=3, seed=305) - 0.5), 0.0025, 0.0) * nb.smooth(nz(nb, 5, seed=306), 0.55, 0.75)
    scr2 = nb.smooth(nb.absf(nb.noise(60, fv=4, detail=3, seed=307) - 0.5), 0.0025, 0.0) * nb.smooth(nz(nb, 5, seed=308), 0.6, 0.8)
    dust = nb.smooth(nz(nb, 1.5, detail=4, rough=0.5, seed=309), 0.4, 1.0)
    spots = nb.smooth(nb.voronoi(40, seed=310), 0.03, 0.022) * nb.smooth(nz(nb, 3, seed=311), 0.5, 0.7)
    chips = nb.smooth(nz(nb, 14, detail=6, seed=312) + sn(nb, 120, seed=313) * 0.3, 0.965, 0.98)
    h = 0.6 + flake * 0.02 - scr * 0.25 - scr2 * 0.2 - chips * 0.4 + mott * 0.02
    col = nb.mulc(paint, 1.0 + mott * 0.12 + flake * 0.15)
    col = nb.mixc(col, lin("#57544e"), dust * 0.12)
    col = nb.mixc(col, lin("#8a8c8f"), nb.maxf(scr, scr2) * 0.55)
    col = nb.mixc(col, lin("#9a9a98"), chips)
    rough = 0.14 + dust * 0.18 + swirl * 0.1 + nb.maxf(scr, scr2) * 0.25 + spots * 0.2 + chips * 0.2 + mott * 0.05
    metal = 0.15 + chips * 0.8 + nb.maxf(scr, scr2) * 0.5
    return {"color": col, "rough": rough.clamp(), "metal": metal.clamp(), "height": h.clamp(),
            "masks": common_masks(nb, 315, extra={"drip": chips * 0.6}),
            "post": weather(rain=0.35, rain_len=0.5, rain_dark=0.2, drip=0.4, drip_len=0.15, cavity=0.15)}


def chrome(nb, p):
    """Scratched chrome / polished steel: near-mirror with directional scratches, smudges, water spots, pits."""
    brush = nb.noise(1.0, fv=300, detail=3, seed=321) - 0.5
    smudge = nz(nb, 3, detail=5, rough=0.6, seed=322)
    scr = nb.smooth(nb.absf(nb.noise(4, fv=50, detail=3, seed=323) - 0.5), 0.002, 0.0) * nb.smooth(nz(nb, 4, seed=324), 0.4, 0.7)
    scr2 = nb.smooth(nb.absf(nb.noise(45, fv=3, detail=3, seed=325) - 0.5), 0.002, 0.0) * nb.smooth(nz(nb, 4, seed=326), 0.5, 0.75)
    spots = nb.smooth(nb.voronoi(30, seed=327), 0.035, 0.02) * nb.smooth(nz(nb, 2.5, seed=328), 0.45, 0.65)
    pits = nb.smooth(nb.voronoi(110, seed=329), 0.04, 0.0) * nb.smooth(nz(nb, 3, seed=330), 0.7, 0.85)
    h = 0.5 + brush * 0.04 - nb.maxf(scr, scr2) * 0.35 - pits * 0.4
    col = nb.mulc(lin("#cfd2d6"), 1.0 + brush * 0.05 - pits * 0.5 - spots * 0.08)
    rough = 0.06 + smudge * 0.12 + nb.maxf(scr, scr2) * 0.22 + spots * 0.18 + pits * 0.3 + brush * 0.03
    return {"color": col, "rough": rough.clamp(), "metal": 1.0, "height": h.clamp(), "masks": common_masks(nb, 331),
            "post": weather(rain=0.25, rain_len=0.4, rain_dark=0.15, cavity=0.1)}


def carbon(nb, p):
    """2x2 twill carbon fibre under a clear coat (0.5 m repeat, ~6 mm tows)."""
    N = 80
    cu = nb.floor(nb.u * N)
    cv = nb.floor(nb.v * N)
    fu = nb.fract(nb.u * N)
    fv = nb.fract(nb.v * N)
    warp_top = nb.lt(nb.mod(cu + cv, 4.0), 2.0)
    # tow cross-section bulge across its width
    bu = nb.sin(fu * 3.14159265)
    bv = nb.sin(fv * 3.14159265)
    sheen_w = nb.noise(N * 2, fv=6, detail=2, seed=341) - 0.5
    sheen_f = nb.noise(6, fv=N * 2, detail=2, seed=342) - 0.5
    hw = nb.lerp(bv, bu, warp_top)
    tone = nb.lerp(0.55 + bv * 0.45 + sheen_f * 0.4, 0.85 + bu * 0.25 + sheen_w * 0.4, warp_top)
    scr = nb.smooth(nb.absf(nb.noise(3, fv=60, detail=3, seed=343) - 0.5), 0.002, 0.0) * nb.smooth(nz(nb, 4, seed=344), 0.6, 0.8)
    dust = nb.smooth(nz(nb, 1.5, detail=3, seed=345), 0.5, 1.0) * 0.4
    col = nb.mulc(lin("#1a1c20"), tone)
    col = nb.mixc(col, lin("#4a4a4c"), dust * 0.25 + scr * 0.4)
    h = 0.5 + hw * 0.12 - scr * 0.1
    rough = 0.1 + dust * 0.3 + scr * 0.2 + (1.0 - warp_top) * 0.04
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp()}


def tile_grimy(nb, p):
    """Small glazed tiles (0.1 m, 12 x 12 per 1.2 m) in dark teal / charcoal: grimy grout, cracked and missing
    tiles, mineral drips. Back-alley walls, ramen counters, metro service corridors."""
    n = 12
    gd = nb.minf(nb.grid_dist(nb.u, n), nb.grid_dist(nb.v, n))
    grout = nb.smooth(gd, 0.0022, 0.001)
    pillow = nb.smooth(gd, 0.007, 0.0015)
    r1 = nb.cell_rand(n, n, seed=351)
    r2 = nb.cell_rand(n, n, seed=352)
    missing = nb.lt(r2, 0.025)
    crack = crack_lines(nb, 8, 353, 0.003, keep=0.6) * nb.lt(r2, 0.2)
    chip = nb.smooth(nz(nb, 30, detail=3, seed=354), 0.8, 0.84) * nb.smooth(gd, 0.012, 0.0)
    glaze = sn(nb, 60, detail=3, seed=355)
    base = nb.ramp(r1, [(0.0, lin("#1d3a3d")), (0.5, lin("#22413f")), (0.8, lin("#1d3236")), (0.96, lin("#26302f")), (1.0, lin("#3a2335"))])
    h = 0.75 - pillow * 0.15 - grout * 0.55 - crack * 0.25 - chip * 0.45 + glaze * 0.03 - missing * 0.5
    col = nb.mulc(base, 0.92 + r2 * 0.12 + glaze * 0.1)
    grime = nb.smooth(nz(nb, 2.5, detail=7, rough=0.65, seed=356), 0.35, 0.9)
    col = nb.mixc(col, nb.mulc(lin("#3a3226"), 0.8), grime * 0.45)
    col = nb.mixc(col, lin("#1b1915"), grout)
    col = nb.mixc(col, lin("#4b4a45"), nb.maxf(chip, missing))
    col = nb.mixc(col, lin("#0d0c0b"), crack * 0.8)
    rough = 0.1 + grime * 0.35 + grout * 0.75 + chip * 0.6 + missing * 0.7 + glaze * 0.05
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp(),
            "masks": common_masks(nb, 357, extra={"drip": grout * 0.25 + crack + missing, "rust": crack * 0.3}),
            "post": weather(rain=0.5, rain_len=0.6, drip=0.7, drip_len=0.3, cavity=0.3, salt=0.25)}


# ---------------------------------------------------------------------------------------------- numpy-generated
def _grid(n):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    return (xx + 0.5) / n, (yy + 0.5) / n  # u, v in 0..1 (v up: bottom-first arrays)


def _line_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / max(dx * dx + dy * dy, 1e-9), 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def glyph(u, v, rng, stroke=0.09):
    """One invented glyph on local coords u,v in 0..1 -> 0..1 coverage mask. Built like an East-Asian character
    from radicals (top bar, stems, enclosure box, crossing strokes, ticks, dots) with 5-8 strokes, so it never
    reads as a Latin letter or any real character."""
    m = np.zeros_like(u)

    def seg(ax, ay, bx, by, w=stroke):
        d = _line_dist(u, v, ax, ay, bx, by)
        return X.smooth(-d, -w * 0.5 - 0.02, -w * 0.5 + 0.02)

    strokes = []
    top = rng.uniform(0.78, 0.9)
    strokes.append((rng.uniform(0.08, 0.2), top, rng.uniform(0.8, 0.92), top))           # roof bar
    xs = sorted(rng.sample([0.22, 0.38, 0.5, 0.62, 0.78], 2))
    for x in xs:                                                                          # two stems
        strokes.append((x, rng.uniform(0.05, 0.3), x, rng.uniform(0.6, top)))
    if rng.random() < 0.6:                                                                # enclosure (box radical)
        x0, x1 = rng.uniform(0.15, 0.35), rng.uniform(0.65, 0.85)
        y0, y1 = rng.uniform(0.1, 0.3), rng.uniform(0.45, 0.62)
        strokes += [(x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)]
    else:                                                                                 # crossing diagonals
        strokes.append((rng.uniform(0.1, 0.3), rng.uniform(0.1, 0.3), rng.uniform(0.55, 0.9), rng.uniform(0.45, 0.7)))
        strokes.append((rng.uniform(0.55, 0.9), rng.uniform(0.05, 0.25), rng.uniform(0.15, 0.45), rng.uniform(0.5, 0.7)))
    mid = rng.uniform(0.38, 0.6)
    strokes.append((rng.uniform(0.05, 0.25), mid, rng.uniform(0.7, 0.95), mid + rng.uniform(-0.05, 0.05)))  # mid bar
    for _ in range(rng.randint(1, 2)):                                                    # ticks
        x, y = rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9)
        strokes.append((x, y, x + rng.uniform(-0.15, 0.15), y - rng.uniform(0.08, 0.15)))
    for st_ in strokes:
        m = np.maximum(m, seg(*st_))
    if rng.random() < 0.5:
        cx, cy = rng.uniform(0.15, 0.85), rng.uniform(0.15, 0.85)
        m = np.maximum(m, X.smooth(-np.hypot(u - cx, v - cy), -stroke * 0.85, -stroke * 0.55))
    return m


def glyph_row(u, v, rng, count, stroke=0.075, gap=0.15):
    """A row of `count` glyphs filling u in 0..1, v in 0..1."""
    m = np.zeros_like(u)
    for i in range(count):
        x0 = i / count
        lu = (u - x0) * count
        lu = lu * (1 + gap) - gap / 2
        inside = (lu >= 0) & (lu <= 1) & (v >= 0) & (v <= 1)
        if not inside.any():
            continue
        g_ = glyph(np.clip(lu, 0, 1), np.clip(v, 0, 1), rng, stroke)
        m = np.where(inside, np.maximum(m, g_), m)
    return m


def screen_ad_post(variant):
    """LED ad panel art (UV fit), invented glyphs + gradients + scanlines. Variants: a magenta/cyan noodle-bar
    style, b acid-yellow/blue corporate, c violet/pink idol poster."""
    import random

    def post(st):
        n = st["res"]
        u, v = _grid(n)
        rng = random.Random({"a": 11, "b": 23, "c": 37}[variant])
        pal = {"a": ("#ff2bd6", "#00e5ff", "#1a0630"), "b": ("#ffe14d", "#3d7bff", "#05081a"),
               "c": ("#9b5cff", "#ff4f9a", "#14051f")}[variant]
        c1, c2, bg = (np.array(lin(h), np.float32) for h in pal)
        grad = X.smooth(v + (u - 0.5) * 0.3, 0.0, 1.0)
        em = X.lerp(bg * 2.5, X.lerp(c2 * 0.35, c1 * 0.35, grad), 0.6)
        if variant == "a":
            # big circle emblem + vertical glyph column + horizontal glyph band
            d = np.hypot(u - 0.68, v - 0.58)
            ring = X.smooth(-np.abs(d - 0.2), -0.03, -0.012)
            disc = X.smooth(-d, -0.17, -0.15)
            em = X.lerp(em, c1 * 1.0, ring)
            em = X.lerp(em, c2 * 0.55, disc * 0.6)
            gl = glyph(np.clip((u - 0.56) / 0.24, 0, 1), np.clip((v - 0.46) / 0.24, 0, 1), rng, 0.12) * ((u > 0.56) & (u < 0.8) & (v > 0.46) & (v < 0.7))
            em = X.lerp(em, np.ones(3, np.float32), gl)
            col_m = glyph_row((v - 0.1) / 0.8, (u - 0.07) / 0.2, rng, 5, 0.1)  # vertical column
            em = X.lerp(em, c2 * 1.1, col_m * ((u > 0.07) & (u < 0.27)))
            band = glyph_row((u - 0.35) / 0.6, (v - 0.12) / 0.13, rng, 7, 0.12)
            em = X.lerp(em, c1 * 1.1, band)
        elif variant == "b":
            stripes = X.smooth(np.sin((u * 1.4 + v) * 60.0), 0.6, 0.8) * (u > 0.62)
            em = X.lerp(em, c2 * 0.7, stripes * 0.5)
            tri = (v < 0.25 + (u - 0.05) * 1.6) & (v > 0.25 - (u - 0.05) * 1.6) & (u > 0.05) & (u < 0.45)
            em = X.lerp(em, c1 * 1.1, X.blur(tri.astype(np.float32), 1.0))
            band = glyph_row((u - 0.06) / 0.88, (v - 0.62) / 0.22, rng, 5, 0.13)
            em = X.lerp(em, np.ones(3, np.float32) * 0.95, band)
            small = glyph_row((u - 0.5) / 0.44, (v - 0.12) / 0.09, rng, 9, 0.12)
            em = X.lerp(em, c1, small)
        else:
            d = np.hypot((u - 0.5) * 1.0, (v - 0.55) * 1.0)
            halo = X.smooth(-d, -0.45, -0.05)
            em = em + c1 * halo[..., None] * 0.6
            # abstract figure silhouette (stacked ellipses, no likeness)
            head = X.smooth(-np.hypot((u - 0.5) / 0.09, (v - 0.68) / 0.11), -1.05, -0.95)
            body = X.smooth(-np.hypot((u - 0.5) / 0.2, (v - 0.33) / 0.24), -1.05, -0.95) * (v < 0.52)
            sil = np.maximum(head, body)
            em = X.lerp(em, bg * 0.6, sil)
            rimm = X.rim(sil, 3.0)
            em = X.lerp(em, c2 * 1.4, rimm)
            col_l = glyph_row((v - 0.15) / 0.75, (u - 0.06) / 0.14, rng, 4, 0.12)
            col_r = glyph_row((v - 0.15) / 0.75, (u - 0.8) / 0.14, rng, 4, 0.12)
            em = X.lerp(em, np.ones(3, np.float32) * 0.9, np.maximum(col_l * ((u > 0.06) & (u < 0.2)), col_r * ((u > 0.8) & (u < 0.94))))
        # LED pixel grid + scanlines + edge vignette
        pg = n / 160.0
        cell = np.minimum(np.abs(((u * n) / pg) % 1.0 - 0.5), np.abs(((v * n) / pg) % 1.0 - 0.5))
        led = 0.72 + 0.28 * X.smooth(cell, 0.5, 0.3)
        scan = 0.92 + 0.08 * np.sin(v * n * 0.9)
        vign = X.smooth(np.minimum(np.minimum(u, 1 - u), np.minimum(v, 1 - v)), 0.0, 0.06)
        em = X.mulc(np.clip(em, 0, 1.4), led * scan * (0.4 + 0.6 * vign))
        st["emit"] = np.clip(em, 0, 1)
        st["color"] = np.clip(em * 0.25 + 0.01, 0, 1)
        st["rough"] = np.full((n, n), 0.12, np.float32)
        st["metal"] = np.zeros((n, n), np.float32)
        st["h01"] = np.full((n, n), 0.5, np.float32)
        return st

    return post


def screen_ad(nb, p):
    return {"color": nb.gray(0.02), "rough": 0.12, "metal": 0.0, "height": 0.5, "emit": nb.gray(0.0),
            "post": screen_ad_post(p.get("variant", "a"))}


SKY = {
    # kind: (pitch_x, pitch_y, tile, window w, sill, window h, lit fraction, palette)
    "a": (2.4, 3.2, 19.2, 1.5, 0.9, 1.7, 0.34, "res"),
    "b": (1.6, 4.0, 16.0, 1.5, 0.35, 3.2, 0.28, "office"),
    "c": (1.2, 3.6, 14.4, 1.12, 0.3, 3.0, 0.4, "mega"),
}


def skyline_post(kind):
    """Emissive window grid for distant towers (UV 'world0': metres from the asset origin, no random offset, so
    floors/columns line up with geometry built on the same pitch)."""
    import random
    px_, py_, tile, ww, sill, wh, litf, pal = SKY[kind]

    def post(st):
        n = st["res"]
        u, v = _grid(n)
        x, y = u * tile, v * tile
        cols, rows = int(round(tile / px_)), int(round(tile / py_))
        ci = np.minimum((x / px_).astype(np.int32), cols - 1)
        ri = np.minimum((y / py_).astype(np.int32), rows - 1)
        fx = x - ci * px_ - (px_ - ww) / 2
        fy = y - ri * py_ - sill
        inside = (fx > 0) & (fx < ww) & (fy > 0) & (fy < wh)
        rng = random.Random(ord(kind) * 977)
        R = np.array([[rng.random() for _ in range(cols)] for _ in range(rows)], np.float32)
        R2 = np.array([[rng.random() for _ in range(cols)] for _ in range(rows)], np.float32)
        R3 = np.array([[rng.random() for _ in range(cols)] for _ in range(rows)], np.float32)
        # whole-floor clusters (offices lit floor by floor)
        if pal == "office":
            fl = np.array([rng.random() for _ in range(rows)], np.float32)
            R = np.where(fl[:, None] < 0.35, R * 0.5, np.minimum(1, R * 1.6))
        lit = R[ri, ci] < litf
        r2 = R2[ri, ci]
        r3 = R3[ri, ci]
        warm = np.array(lin("#ffb878"), np.float32)
        cool = np.array(lin("#cfe6ff"), np.float32)
        mag = np.array(lin("#ff2bd6"), np.float32)
        cyn = np.array(lin("#00e5ff"), np.float32)
        vio = np.array(lin("#9b5cff"), np.float32)
        c = X.lerp(np.broadcast_to(warm, (n, n, 3)), np.broadcast_to(cool, (n, n, 3)), (r2 > 0.55).astype(np.float32))
        neon = (r2 > 0.88).astype(np.float32)
        c = X.lerp(c, X.lerp(np.broadcast_to(mag, (n, n, 3)), np.broadcast_to(cyn, (n, n, 3)), (r3 > 0.5).astype(np.float32)), neon)
        if pal == "mega":
            c = X.lerp(c, np.broadcast_to(vio, (n, n, 3)), ((r2 > 0.8) & (r2 <= 0.88)).astype(np.float32))
        lu = np.clip(fx / ww, 0, 1)
        lv = np.clip(fy / wh, 0, 1)
        blind = r3 * 0.6
        inten = (0.55 + 0.45 * np.sin(lu * 3.14159)) * np.where(lv > 1 - blind, 0.35 + 0.15 * (np.sin(lv * 260) > 0), 1.0)
        inten = inten * (0.6 + 0.5 * R[ri, ci] / max(litf, 1e-3))
        # interior clutter silhouettes at the bottom of lit windows
        inten = inten * np.where((lv < 0.25) & (np.sin(lu * 17 + r3 * 40) > 0.3), 0.55, 1.0)
        mull = (np.abs(fx - ww / 2) < 0.025) if pal != "office" else (np.abs(((fx / (ww / 2)) % 1.0) - 0.5) > 0.48)
        em = np.where((inside & lit & ~mull)[..., None], c * np.clip(inten, 0, 1.2)[..., None], 0.0)
        # glass and facade
        glass = np.array(lin("#0c1218"), np.float32)
        wall = np.array(lin({"res": "#3a3b3d", "office": "#202429", "mega": "#17191d"}[pal]), np.float32)
        wall_n = X.blur(np.asarray(np.random.RandomState(3).rand(n, n), np.float32), 2.0) - 0.5
        col = np.where(inside[..., None], glass + em * 0.25, X.mulc(np.broadcast_to(wall, (n, n, 3)), 1.0 + wall_n * 0.6))
        if pal == "res":  # AC units under some windows, slab edges
            ac = (~inside) & (fy < 0) & (fy > -0.55) & (fx > ww * 0.55) & (fx < ww * 0.95) & (R2[ri, ci] < 0.4)
            col = np.where(ac[..., None], np.array(lin("#8c8e8f"), np.float32), col)
        slab = (y - ri * py_) < 0.22
        col = np.where((slab & ~inside)[..., None], col * 0.7, col)
        st["emit"] = np.clip(em, 0, 1)
        st["color"] = np.clip(col, 0, 1)
        st["rough"] = np.where(inside, 0.06, 0.8).astype(np.float32)
        st["metal"] = np.where(inside, 0.5, 0.0).astype(np.float32)
        h = np.where(inside, 0.3, 0.6).astype(np.float32)
        st["h01"] = X.blur(h, 1.0)
        return st

    return post


def skyline_windows(nb, p):
    return {"color": nb.gray(0.02), "rough": 0.5, "metal": 0.0, "height": 0.5, "emit": nb.gray(0.0),
            "post": skyline_post(p.get("kind", "a"))}


# ============================================================================================== HD base set (part 2)
def hash2(nb, a, b, seed=0):
    """White noise of two float sockets (per-cell random value for irregular grids)."""
    comb = nb.nodes.new("ShaderNodeCombineXYZ")
    nb.link_or_set(comb.inputs[0], a)
    nb.link_or_set(comb.inputs[1], b)
    comb.inputs[2].default_value = seed * 1.618 + 0.37
    wn = nb.nodes.new("ShaderNodeTexWhiteNoise")
    wn.noise_dimensions = "3D"
    nb.links.new(comb.outputs[0], wn.inputs["Vector"])
    from nodekit import S
    return S(nb, wn.outputs["Value"])


def rect_mask(nb, fu, fv, cx, cy, hw, hh, soft=0.004):
    """1 inside an axis-aligned rectangle (centre cx,cy, half sizes hw,hh) in local coords fu,fv."""
    return nb.smooth(hw - nb.absf(fu - cx), 0.0, soft) * nb.smooth(hh - nb.absf(fv - cy), 0.0, soft)


def asphalt(nb, p):
    """Wet city asphalt (4 m): exposed aggregate, worn binder, long + alligator cracks, glossy tar crack sealant,
    rectangular patch repairs with sealed seams, oil drips, puddles in the low spots."""
    agg_d = nb.voronoi(520, seed=21)
    agg_c = nb.voronoi(520, seed=21, out="Color")
    fines = nb.voronoi(1300, seed=22)
    exposed = nb.smooth(nz(nb, 4.5, detail=4, seed=23), 0.3, 0.8)
    dome = nb.smooth(agg_d, 0.5, 0.06)
    dome2 = nb.smooth(fines, 0.55, 0.1)
    binder = sn(nb, 140, detail=3, seed=24)
    tone = sn(nb, 1.5, detail=4, seed=25)
    mott = sn(nb, 9, detail=5, seed=20)
    cracks = crack_lines(nb, 1.6, 26, 0.0032, keep=0.5)
    az = nb.smooth(nz(nb, 2.0, detail=3, seed=27), 0.72, 0.82)
    allig = nb.smooth(nb.voronoi(22, seed=28, feature="DISTANCE_TO_EDGE"), 0.005, 0.0015) * az
    sealn = nb.noise(1.1, detail=4, rough=0.5, seed=29)
    seal = nb.smooth(nb.absf(sealn - 0.5), 0.011, 0.006) * nb.smooth(nz(nb, 1.4, seed=30), 0.45, 0.55)
    # patch repairs on a 2 x 2 grid of 2 m cells (about 40% of cells), straight saw-cut edges
    pr, pr2, pr3, pr4 = (nb.cell_rand(2, 2, seed=s) for s in (31, 32, 33, 34))
    fu = nb.fract(nb.u * 2) - 0.5
    fv = nb.fract(nb.v * 2) - 0.5
    cx, cy = (pr4 - 0.5) * 0.2, (pr - 0.5) * 0.2
    hw, hh = 0.12 + pr2 * 0.2, 0.08 + pr3 * 0.22
    on = nb.lt(pr, 0.42)
    inrect = rect_mask(nb, fu, fv, cx, cy, hw, hh, 0.002) * on
    seam = (rect_mask(nb, fu, fv, cx, cy, hw + 0.006, hh + 0.006, 0.002) - rect_mask(nb, fu, fv, cx, cy, hw - 0.003, hh - 0.003, 0.002)) * on
    seam = seam.clamp()
    oil = nb.smooth(nz(nb, 5.0, detail=5, seed=35), 0.92, 0.97) * nb.smooth(nz(nb, 1.2, seed=34), 0.55, 0.7)
    drips = nb.smooth(nb.voronoi(30, seed=36), 0.04, 0.02) * nb.smooth(nz(nb, 2.2, seed=37), 0.72, 0.8)
    oilm = nb.maxf(oil, drips)
    ex = exposed * (1.0 - inrect * 0.8)
    h = (0.5 + dome * ex * 0.3 + dome2 * 0.08 + binder * 0.14 + mott * 0.08 - cracks * 0.6 - allig * 0.45 + seal * 0.05
         + seam * 0.04 - inrect * 0.02)
    stone = nb.ramp(agg_c, [(0.0, lin("#3d3d3c")), (0.4, lin("#5f5e5b")), (0.75, lin("#787570")), (1.0, lin("#8f8b84"))])
    bind = nb.mulc(lin("#232425"), 1.0 + binder * 0.5 + tone * 0.35 + mott * 0.3)
    col = nb.mixc(bind, stone, dome * ex * 0.8)
    col = nb.mixc(col, nb.mulc(lin("#161718"), 1.0 + binder * 0.4), inrect * 0.85)
    col = nb.mixc(col, lin("#0b0b0c"), nb.maxf(seal, seam))
    col = nb.mixc(col, lin("#0e0c0a"), oilm * 0.55)
    col = nb.mixc(col, lin("#0a0a0a"), nb.maxf(cracks, allig * 0.8))
    rough = 0.82 - dome * ex * 0.08 - nb.maxf(seal, seam) * 0.45 - oilm * 0.3 + nb.maxf(cracks, allig) * 0.1 + binder * 0.06
    masks = common_masks(nb, 38, extra={"pud": nb.noise(2.6, detail=2.0, rough=0.45, seed=39), "damp": nb.noise(2.5, detail=3, seed=40)})
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp(), "masks": masks,
            "post": weather(cavity=0.3, cav_r=0.008, edge=0.06,
                            wet={"level": p.get("puddles", 0.07), "dark": 0.5, "rough": 0.5, "pud_dark": 0.04})}


def paving(nb, p):
    """Wet plaza paving (3 m): 4 courses of 0.75 m with a random slab length per course (0.75 / 1.0 / 1.5 m) so it
    reads as laid stone not a grid; colour batches, replaced slabs, chamfers, chipped arrises, cracked slabs, sunken
    slabs holding water, gum spots, moss and grit in the joints."""
    rows = 4
    row = nb.floor(nb.v * rows)
    rr = nb.cell_rand(1, rows, seed=41)
    n = 2.0 + nb.floor(rr * 2.999)
    off = nb.cell_rand(1, rows, seed=42)
    uu = nb.u * n + off
    si = nb.mod(nb.floor(uu), n)
    fu = nb.fract(uu)
    fv = nb.fract(nb.v * rows)
    du = nb.minf(fu, 1.0 - fu) * (3.0 / n)
    dv = nb.minf(fv, 1.0 - fv) * (3.0 / rows)
    gd = nb.minf(du, dv)  # metres to the nearest joint
    joint = nb.smooth(gd, 0.005, 0.002)
    cham = nb.smooth(gd, 0.014, 0.004)
    r1 = hash2(nb, row, si, 1)
    r2 = hash2(nb, row, si, 2)
    r3 = hash2(nb, row, si, 3)
    tilt = (fu - 0.5) * (r2 - 0.5) * 0.06 + (fv - 0.5) * (r3 - 0.5) * 0.06
    sunk = nb.lt(r3, 0.1) * 0.12
    surf = sn(nb, 60, detail=4, seed=43)
    agg = nb.smooth(nb.voronoi(900, seed=44), 0.5, 0.15)
    chip = nb.smooth(nz(nb, 28, detail=4, seed=45), 0.82, 0.86) * nb.smooth(gd, 0.03, 0.0)
    crack = crack_lines(nb, 2.5, 46, 0.0028, keep=0.45) * nb.lt(r2, 0.22)
    gum = nb.smooth(nb.voronoi(22, seed=47), 0.012, 0.009) * nb.smooth(nz(nb, 3, seed=48), 0.45, 0.6)
    h = 0.7 + tilt - sunk + surf * 0.06 + agg * 0.05 - cham * 0.18 - joint * 0.5 - chip * 0.3 - crack * 0.35 + gum * 0.03
    batch = nb.ramp(r1, [(0.0, lin("#5f6264")), (0.55, lin("#6e7173")), (0.8, lin("#77726b")), (0.92, lin("#4f5355")), (1.0, lin("#83807a"))])
    col = nb.mulc(batch, 1.0 + surf * 0.18 + agg * 0.08)
    dirt = nb.smooth(nz(nb, 2.5, detail=6, rough=0.62, seed=49), 0.45, 0.9)
    col = nb.mixc(col, nb.mulc(col, 0.55), dirt * 0.6)
    moss = nb.smooth(nz(nb, 5, detail=4, seed=50), 0.5, 0.75)
    jcol = nb.mixc(lin("#25221d"), lin("#2f3a1c"), moss)
    col = nb.mixc(col, jcol, nb.maxf(joint, chip * 0.7))
    col = nb.mixc(col, lin("#1c1b19"), crack * 0.85)
    col = nb.mixc(col, lin("#3a3936"), gum * 0.9)
    rough = 0.7 + surf * 0.1 + joint * 0.25 + dirt * 0.08 - gum * 0.2
    masks = common_masks(nb, 51, extra={"pud": nb.noise(1.8, detail=1.5, rough=0.4, seed=52), "damp": nb.noise(3, detail=3, seed=53)})
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp(), "masks": masks,
            "post": weather(cavity=0.35, cav_r=0.006, edge=0.08,
                            wet={"level": p.get("puddles", 0.1), "dark": 0.35, "rough": 0.6, "pud_dark": 0.06})}


def plaster(nb, p):
    """Painted render over brick (2 m): stipple + trowel swirl, map cracks, spalls exposing brick, repaint patches,
    rain streaks and dark tide marks below sills/cracks, algae tint in wet streaks."""
    tint = p.get("tint", lin("#8f8a80"))
    st = sn(nb, 70, detail=5, rough=0.62, seed=171)
    trowel = sn(nb, 5, detail=3, seed=172, distortion=3.0)
    cloud = sn(nb, 1.8, detail=4, seed=173)
    cracks = crack_lines(nb, 2.2, 174, 0.0035, keep=0.52)
    craq = nb.smooth(nb.voronoi(14, seed=175, feature="DISTANCE_TO_EDGE"), 0.0025, 0.0008) * nb.smooth(nz(nb, 2.5, seed=176), 0.62, 0.72)
    spn = nz(nb, 1.8, detail=6, rough=0.62, seed=177)
    spall = nb.smooth(spn, 0.875, 0.885)
    lip = nb.smooth(spn, 0.85, 0.875) * (1.0 - spall)
    # brick under the render (running bond 225 x 75)
    rows = 26.0
    brow = nb.floor(nb.v * rows)
    boff = nb.mod(brow, 2.0) * 0.5
    bu = nb.fract(nb.u * 9.0 + boff)
    bv = nb.fract(nb.v * rows)
    bgd = nb.minf(nb.minf(bu, 1.0 - bu) * (2.0 / 9.0), nb.minf(bv, 1.0 - bv) * (2.0 / rows))
    mortar = nb.smooth(bgd, 0.005, 0.003)
    brk = nb.mixc(nb.mulc(lin("#6e3a2a"), 0.8 + hash2(nb, nb.floor(nb.u * 9.0 + boff), brow, 7) * 0.4), lin("#6a655c"), mortar)
    repaint = nb.lt(nb.voronoi(2.2, seed=178, out="Color"), 0.18) * nb.smooth(nb.voronoi(2.2, seed=178, feature="DISTANCE_TO_EDGE") + sn(nb, 30, seed=179) * 0.05, 0.01, 0.03)
    h = 0.62 + st * 0.18 + trowel * 0.08 - cracks * 0.45 - craq * 0.2 - spall * (0.35 + mortar * 0.15) + lip * 0.08
    col = nb.mulc(tint, 1.0 + st * 0.12 + cloud * 0.3 + trowel * 0.08)
    col = nb.mixc(col, nb.mulc(tint, 1.12), repaint * 0.7)
    blot = nb.smooth(nz(nb, 2.3, detail=6, rough=0.62, seed=180), 0.5, 0.9)
    col = nb.mixc(col, nb.mulc(col, 0.6), blot * 0.45)
    col = nb.mixc(col, brk, spall)
    col = nb.mixc(col, nb.mulc(col, 0.55), lip * 0.6)
    col = nb.mixc(col, nb.mulc(col, 0.3), nb.maxf(cracks, craq * 0.7))
    rough = 0.9 - repaint * 0.06 + spall * 0.02
    masks = common_masks(nb, 181, extra={"drip": cracks + lip * 0.4 + craq * 0.3})
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp(), "masks": masks,
            "post": weather(rain=0.9, rain_len=1.2, rain_dark=0.38, drip=0.9, drip_len=0.4, drip_dark=0.45, cavity=0.3,
                            salt=0.2, grime=lin("#2c2b20"))}


def brick(nb, p):
    """Brick (1.8 m: 8 x 24 courses, running bond): clay colour batches, pitted faces, chipped arrises, recessed
    sandy mortar with missing pockets, replaced bricks, soot, efflorescence, moss in joints, rain streaks."""
    rows, cols = 24, 8
    row = nb.floor(nb.v * rows)
    off = nb.mod(row, 2.0) * 0.5
    bu = nb.fract(nb.u * cols + off)
    bv = nb.fract(nb.v * rows)
    du = nb.minf(bu, 1 - bu) * (1.8 / cols)
    dv = nb.minf(bv, 1 - bv) * (1.8 / rows)
    gd = nb.minf(du, dv)
    mortar = nb.smooth(gd, 0.0055, 0.0035)
    arris = nb.smooth(gd, 0.012, 0.004)
    bi = nb.floor(nb.u * cols + off)
    r1 = hash2(nb, bi, row, 181)
    r2 = hash2(nb, bi, row, 182)
    r3 = hash2(nb, bi, row, 183)
    surf = sn(nb, 120, detail=4, seed=184)
    pits = nb.smooth(nb.voronoi(260, seed=185), 0.06, 0.02) * nb.smooth(nz(nb, 6, seed=186), 0.4, 0.7)
    chip = nb.smooth(nz(nb, 26, detail=4, seed=187), 0.76, 0.8) * nb.smooth(gd, 0.02, 0.0)
    missing = nb.smooth(nz(nb, 12, detail=3, seed=188), 0.8, 0.84) * mortar
    h = 0.75 - mortar * (0.5 + missing * 0.3) + surf * 0.12 - pits * 0.3 - chip * 0.35 - arris * 0.06 + (r2 - 0.5) * 0.06
    bcol = nb.ramp(r1, [(0.0, lin("#4e2419")), (0.3, lin("#6c3322")), (0.6, lin("#7d3f2a")), (0.86, lin("#8a4d36")), (0.96, lin("#4a3a33")), (1.0, lin("#6e6560"))])
    col = nb.mulc(bcol, 0.85 + surf * 0.35 + (r3 - 0.5) * 0.15 - pits * 0.3)
    soot = nb.smooth(nz(nb, 2.5, detail=6, seed=189), 0.45, 0.9)
    col = nb.mixc(col, nb.mulc(col, 0.42), soot * 0.65)
    eff = nb.smooth(nz(nb, 3.5, detail=6, seed=190), 0.78, 0.95) * nb.smooth(gd, 0.025, 0.0)
    moss = nb.smooth(nz(nb, 4, detail=5, seed=191), 0.6, 0.8)
    mcol = nb.mixc(nb.mulc(lin("#6b665c"), 0.9 + surf * 0.2), lin("#3d4626"), moss * 0.8)
    col = nb.mixc(col, mcol, mortar)
    col = nb.mixc(col, nb.mulc(mcol, 0.4), missing)
    col = nb.mixc(col, lin("#7a5244"), chip * 0.8)
    col = nb.mixc(col, lin("#b9b5aa"), eff * 0.3)
    rough = 0.86 + mortar * 0.08 - soot * 0.04
    masks = common_masks(nb, 192, extra={"drip": missing + chip * 0.5 + mortar * 0.08})
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp(), "masks": masks,
            "post": weather(rain=0.6, rain_len=1.0, rain_dark=0.4, drip=0.6, drip_len=0.3, cavity=0.35, cav_r=0.005, salt=0.3)}


def metal_painted(nb, p):
    """Painted steel (2 m): orange peel, layered chips (paint -> grey primer -> bare steel with rust in the middle),
    fine scratches, rust blooms with runoff streaks, dust and grime. Tints share the maps."""
    paint = p.get("tint", lin("#4d5b63"))
    peel = nb.noise(420, detail=2, seed=41) - 0.5
    mott = sn(nb, 5, detail=5, rough=0.6, seed=42)
    cn = nz(nb, 8, detail=6, rough=0.65, seed=43) + sn(nb, 90, detail=3, seed=44) * 0.25
    chips = nb.smooth(cn, 0.87, 0.885)
    primer = nb.smooth(cn, 0.84, 0.86) - chips
    rustc = nb.smooth(cn, 0.93, 0.96)
    scr = nb.smooth(nb.absf(nb.noise(3, fv=90, detail=2, seed=45) - 0.5), 0.003, 0.0) * nb.smooth(nz(nb, 6, seed=46), 0.55, 0.75)
    scr2 = nb.smooth(nb.absf(nb.noise(80, fv=3, detail=2, seed=47) - 0.5), 0.003, 0.0) * nb.smooth(nz(nb, 6, seed=48), 0.6, 0.8)
    s_ = nb.maxf(scr, scr2)
    bloom = nb.smooth(nz(nb, 11, detail=5, seed=50), 0.93, 0.96)
    h = 0.6 + peel * 0.06 - primer * 0.12 - chips * 0.3 - s_ * 0.15 + bloom * 0.1 + rustc * 0.05
    col = nb.mulc(paint, 1.0 + mott * 0.2 + peel * 0.05)
    dust = nb.smooth(nz(nb, 3, detail=6, rough=0.6, seed=49), 0.45, 0.9)
    col = nb.mixc(col, nb.mulc(col, 0.6), dust * 0.5)
    col = nb.mixc(col, lin("#8d8d89"), primer)
    col = nb.mixc(col, lin("#9a9a98"), chips)
    col = nb.mixc(col, lin("#5c2d16"), nb.maxf(rustc, bloom))
    col = nb.mixc(col, lin("#b6b6b3"), s_ * 0.6)
    metal = nb.maxf(chips * (1.0 - rustc), s_ * 0.8) * (1.0 - bloom)
    rough = 0.42 + mott * 0.1 + dust * 0.22 - chips * 0.1 + nb.maxf(rustc, bloom) * 0.45 + primer * 0.15
    masks = common_masks(nb, 51, extra={"rust": nb.maxf(rustc, bloom), "drip": chips * 0.3})
    return {"color": col, "rough": rough.clamp(), "metal": metal.clamp(), "height": h.clamp(), "masks": masks,
            "post": weather(rain=0.4, rain_len=0.8, rain_dark=0.22, drip=0.25, rust=0.5, rust_len=0.22, cavity=0.2)}


def metal_bare(nb, p):
    """Brushed / worn bare steel (1 m): directional grain, smudges and fingerprints, scratches, water spots,
    light oxidation."""
    brush = nb.noise(1.5, fv=500, detail=3, rough=0.7, seed=51) - 0.5
    brush2 = nb.noise(4, fv=1200, detail=2, seed=52) - 0.5
    smudge = nz(nb, 4, detail=5, rough=0.6, seed=53)
    prints = nb.smooth(nb.absf(nb.sin(nb.voronoi(18, seed=54) * 180.0)), 0.3, 0.0) * nb.smooth(nb.voronoi(18, seed=54), 0.05, 0.03) * nb.smooth(nz(nb, 4, seed=55), 0.6, 0.7)
    scr = nb.smooth(nb.absf(nb.noise(5, fv=40, detail=3, seed=56) - 0.5), 0.0025, 0.0) * nb.smooth(nz(nb, 5, seed=57), 0.45, 0.7)
    spots = nb.smooth(nb.voronoi(24, seed=58), 0.03, 0.018) * nb.smooth(nz(nb, 3, seed=59), 0.5, 0.7)
    ox = nb.smooth(nz(nb, 3, detail=5, seed=60), 0.8, 0.97)
    h = 0.5 + brush * 0.3 + brush2 * 0.2 - scr * 0.3
    col = nb.mulc(lin("#a8aaac"), 1.0 + brush * 0.25 + brush2 * 0.1 - (smudge - 0.5) * 0.15)
    col = nb.mixc(col, lin("#6b6458"), ox * 0.5)
    col = nb.mixc(col, lin("#8f8e8a"), spots * 0.4)
    rough = 0.34 + brush * 0.15 + brush2 * 0.1 + (smudge - 0.5) * 0.12 + prints * 0.12 + spots * 0.15 + ox * 0.25 + scr * 0.12
    return {"color": col, "rough": rough.clamp(), "metal": 1.0 - ox * 0.4, "height": h.clamp(), "masks": common_masks(nb, 61),
            "post": weather(rain=0.12, rain_len=0.5, rain_dark=0.1, cavity=0.15)}


def metal_rusted(nb, p):
    """Heavily rusted steel (2 m): layered oxide colours, flaking paint islands with lifted edges, pitting, scale,
    dark wet runoff streaks."""
    m1 = nz(nb, 6, detail=7, rough=0.62, seed=61)
    m2 = nz(nb, 30, detail=4, seed=62)
    m3 = sn(nb, 2.5, detail=4, seed=67)
    flake = nz(nb, 4, detail=6, rough=0.65, seed=63) + sn(nb, 60, detail=3, seed=64) * 0.2
    paint_left = nb.smooth(flake, 0.62, 0.64)
    lift = nb.smooth(flake, 0.6, 0.62) * (1 - paint_left)
    pits = nb.smooth(nb.voronoi(90, seed=65), 0.16, 0.03) * (1 - paint_left)
    scale = nb.voronoi(160, seed=66, out="Color")
    h = 0.45 + (m1 - 0.5) * 0.4 + (m2 - 0.5) * 0.3 - pits * 0.35 + paint_left * 0.22 + lift * 0.3 + (scale - 0.5) * 0.14
    rust = nb.ramp(m1 * 0.55 + m2 * 0.3 + (scale - 0.5) * 0.25 + m3 * 0.3, [
        (0.15, lin("#1c120c")), (0.32, lin("#3a2416")), (0.45, lin("#553420")), (0.58, lin("#6a3e20")), (0.7, lin("#7e4a24")), (0.82, lin("#8c5a2c")), (0.92, lin("#4a3020"))])
    paint = nb.mulc(p.get("tint", lin("#3e474c")), 0.75 + (m2 - 0.5) * 0.3)
    col = nb.mixc(rust, paint, paint_left)
    col = nb.mixc(col, lin("#140c08"), pits * 0.7)
    col = nb.mixc(col, lin("#2a1a10"), lift * 0.5)
    rough = 0.86 + (m2 - 0.5) * 0.12 - paint_left * 0.32
    masks = common_masks(nb, 68, extra={"drip": pits * 0.4 + lift, "rust": (1 - paint_left) * nb.smooth(m1, 0.6, 0.8)})
    return {"color": col, "rough": rough.clamp(), "metal": paint_left * 0.15, "height": h.clamp(), "masks": masks,
            "post": weather(rain=0.6, rain_len=0.9, rain_dark=0.45, drip=0.5, drip_len=0.3, rust=0.5, rust_len=0.5, cavity=0.35,
                            grime=lin("#24160e"))}


def metal_plate(nb, p):
    """Heavy steel plating (2 m: 1.0 x 0.5 m plates, staggered): bevelled plate edges with paint worn to bright
    steel, countersunk bolts with rust bleed, dirt packed in seams with drips below, replaced plates, scuffs."""
    rows = 4
    row = nb.floor(nb.v * rows)
    off = nb.mod(row, 2.0) * 0.5
    uu = nb.u * 2 + off
    gu = nb.fract(uu)
    gv = nb.fract(nb.v * rows)
    du = nb.minf(gu, 1 - gu) * 1.0
    dv = nb.minf(gv, 1 - gv) * 0.5
    gd = nb.minf(du, dv)
    seam = nb.smooth(gd, 0.0026, 0.0012)
    bev = nb.smooth(gd, 0.008, 0.0026)
    bx = nb.minf(gu, 1 - gu) * 1.0
    by = nb.minf(gv, 1 - gv) * 0.5
    bxm = nb.absf(gu - 0.5) * 1.0
    bd1 = ((bx - 0.035) ** 2 + (by - 0.035) ** 2) ** 0.5
    bd2 = ((bxm) ** 2 + (by - 0.035) ** 2) ** 0.5
    bd = nb.minf(bd1, bd2)
    bolt = nb.smooth(bd, 0.011, 0.008)
    bring = nb.smooth(bd, 0.013, 0.011) * (1.0 - bolt)
    slot = nb.smooth(nb.absf((nb.u * 2 + off) * 1.0 - nb.floor(uu) - 0.035) * 0 + nb.absf(by - 0.035), 0.0012, 0.0008) * bolt
    ri = hash2(nb, nb.floor(uu), row, 71)
    swirl = nb.noise(2, fv=200, detail=3, seed=72) - 0.5
    wear = nz(nb, 6, detail=6, rough=0.6, seed=73)
    scuff = nb.smooth(nb.absf(nb.noise(5, fv=40, detail=3, seed=74) - 0.5), 0.004, 0.0) * nb.smooth(nz(nb, 5, seed=75), 0.6, 0.8)
    h = 0.6 - seam * 0.6 - bev * 0.14 + bolt * 0.22 - bring * 0.12 - slot * 0.1 + swirl * 0.05 + (wear - 0.5) * 0.06 - scuff * 0.08
    tint = p.get("tint", lin("#4c525a"))
    col = nb.mulc(tint, 0.85 + ri * 0.25 + (wear - 0.5) * 0.3)
    col = nb.mixc(col, nb.mulc(tint, 0.7), nb.lt(ri, 0.15))
    col = nb.mixc(col, lin("#7a7e82"), nb.smooth(wear, 0.7, 0.85) * 0.4 + scuff * 0.5)
    col = nb.mixc(col, lin("#2a2c2e"), bolt * 0.5)
    grime = nb.smooth(nz(nb, 3, detail=6, seed=76), 0.5, 0.85)
    col = nb.mixc(col, nb.mulc(col, 0.55), grime * 0.4)
    col = nb.mixc(col, lin("#100f0e"), seam)
    rough = 0.48 + (wear - 0.5) * 0.22 + seam * 0.45 + grime * 0.15 - bolt * 0.1 - scuff * 0.15
    masks = common_masks(nb, 77, extra={"drip": seam * 0.5 + bring, "rust": bring * 0.8 + bolt * 0.3})
    return {"color": col, "rough": rough.clamp(), "metal": (0.8 - seam * 0.6).clamp(), "height": h.clamp(), "masks": masks,
            "post": weather(rain=0.35, rain_len=0.7, drip=0.6, drip_len=0.25, rust=0.7, rust_len=0.3, cavity=0.3,
                            edge=0.55, edge_r=0.004, edge_col=lin("#9a9c9e"))}


def metro_tile(nb, p):
    """Glazed metro wall tiles (0.15 m, 8 x 8 per 1.2 m): pillowed glaze, colour drift, crazing, cracked and missing
    tiles showing the mortar bed, grout packed with grime and moss, mineral drips."""
    n = 8
    gd = nb.minf(nb.grid_dist(nb.u, n), nb.grid_dist(nb.v, n)) * 1.2  # metres
    grout = nb.smooth(gd, 0.0022, 0.001)
    pillow = nb.smooth(gd, 0.008, 0.0015)
    r1 = nb.cell_rand(n, n, seed=81)
    r2 = nb.cell_rand(n, n, seed=82)
    missing = nb.lt(r2, 0.02)
    crack = crack_lines(nb, 6, 83, 0.003, keep=0.62) * nb.lt(r2, 0.2)
    craze = nb.smooth(nb.voronoi(70, seed=84, feature="DISTANCE_TO_EDGE"), 0.0012, 0.0004) * nb.lt(r1, 0.35)
    chip = nb.smooth(nz(nb, 30, detail=3, seed=85), 0.82, 0.86) * nb.smooth(gd, 0.014, 0.0)
    glaze = sn(nb, 50, detail=3, seed=86)
    h = 0.75 - pillow * 0.16 - grout * 0.6 - crack * 0.25 - chip * 0.45 + glaze * 0.04 - missing * 0.45
    tile = nb.mulc(lin("#d2d5d0"), 0.9 + r1 * 0.12 + glaze * 0.06)
    grime = nb.smooth(nz(nb, 2.5, detail=7, rough=0.65, seed=87), 0.35, 0.9)
    col = nb.mixc(tile, nb.mulc(lin("#7e7462"), 0.75), grime * 0.55)
    moss = nb.smooth(nz(nb, 4, detail=5, seed=88), 0.55, 0.8)
    gcol = nb.mixc(lin("#3a372f"), lin("#2e3820"), moss)
    col = nb.mixc(col, gcol, grout)
    col = nb.mixc(col, lin("#5a5850"), nb.maxf(chip, missing))
    col = nb.mixc(col, lin("#2a2926"), nb.maxf(crack * 0.8, craze * 0.4))
    rough = 0.12 + grime * 0.45 + grout * 0.7 + chip * 0.6 + missing * 0.7 + glaze * 0.05
    masks = common_masks(nb, 89, extra={"drip": grout * 0.2 + crack + missing + chip * 0.5})
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp(), "masks": masks,
            "post": weather(rain=0.7, rain_len=0.9, rain_dark=0.35, drip=0.8, drip_len=0.35, cavity=0.3, salt=0.35)}


def lab_panel(nb, p):
    """Corporate / lab wall cladding (2.4 m: two 1.2 x 2.4 m panels): 8 mm shadow gaps, a horizontal reveal at
    1.2 m, countersunk screws, satin powder coat with subtle tonal panels, smudges, scuffs and faint drips."""
    gu = nb.fract(nb.u * 2)
    gv = nb.v
    du = nb.minf(gu, 1 - gu) * 1.2
    dv = nb.minf(nb.fract(gv), 1 - nb.fract(gv)) * 2.4
    dmid = nb.absf(nb.fract(gv) - 0.5) * 2.4
    gd = nb.minf(du, dv)
    seam = nb.smooth(gd, 0.0045, 0.003)
    bev = nb.smooth(gd, 0.010, 0.004)
    reveal = nb.smooth(dmid, 0.006, 0.004) * nb.smooth(du, 0.0, 0.004)
    sd = nb.minf(((du - 0.035) ** 2 + (dv - 0.035) ** 2) ** 0.5, ((du - 0.035) ** 2 + (dmid - 0.035) ** 2) ** 0.5)
    screw = nb.smooth(sd, 0.0045, 0.0035)
    rnd = nb.cell_rand(2, 1, seed=91)
    orange = nb.noise(240, detail=2, seed=92) - 0.5
    smudge = nz(nb, 4, detail=5, rough=0.6, seed=93)
    scuff = nb.smooth(nz(nb, 10, fv=3, detail=5, seed=94), 0.78, 0.88)
    prints = nb.smooth(nb.voronoi(14, seed=95), 0.04, 0.025) * nb.smooth(nz(nb, 3, seed=96), 0.6, 0.72)
    h = 0.7 - seam * 0.7 - bev * 0.08 - reveal * 0.4 + screw * 0.08 + orange * 0.03
    col = nb.mulc(p.get("tint", lin("#c4c8c9")), 0.95 + rnd * 0.07 + (smudge - 0.5) * 0.1)
    col = nb.mixc(col, nb.mulc(col, 0.72), scuff * 0.6)
    col = nb.mixc(col, g(0.06), nb.maxf(seam, reveal))
    col = nb.mixc(col, lin("#8c8f91"), screw)
    rough = 0.34 + (smudge - 0.5) * 0.14 + scuff * 0.15 + nb.maxf(seam, reveal) * 0.4 - screw * 0.1 + prints * 0.12
    masks = common_masks(nb, 97, extra={"drip": screw * 0.5 + reveal * 0.15})
    return {"color": col, "rough": rough.clamp(), "metal": screw * 0.9, "height": h.clamp(), "masks": masks,
            "post": weather(rain=0.15, rain_len=0.6, rain_dark=0.12, drip=0.25, drip_len=0.15, cavity=0.2)}


def lab_floor(nb, p):
    """Lab / corporate vinyl tiles (0.5 m on a 2 m repeat): speckle, two-tone checker, heel scuffs, worn traffic
    paths (glossier), grime in the seams, lifted and cracked tiles, dried water stains."""
    n = 4
    gd = nb.minf(nb.grid_dist(nb.u, n), nb.grid_dist(nb.v, n)) * 2.0
    seam = nb.smooth(gd, 0.0012, 0.0004)
    cu = nb.floor(nb.u * n)
    cv = nb.floor(nb.v * n)
    checker = nb.mod(cu + cv, 2.0)
    rnd = nb.cell_rand(n, n, seed=101)
    rnd2 = nb.cell_rand(n, n, seed=106)
    fleck = nb.voronoi(600, seed=102, out="Color")
    scuff = nb.smooth(nb.absf(nb.noise(6, fv=25, detail=4, seed=103) - 0.5), 0.008, 0.0) * nb.smooth(nz(nb, 8, seed=104), 0.6, 0.72)
    wear = nb.smooth(nz(nb, 2, detail=5, seed=105), 0.4, 0.85)
    crack = crack_lines(nb, 5, 107, 0.0022, keep=0.6) * nb.lt(rnd2, 0.15)
    lifted = nb.lt(rnd2, 0.05) * nb.smooth(gd, 0.04, 0.0)
    stain = nb.smooth(nb.absf(nz(nb, 3, detail=4, seed=108) - 0.7), 0.012, 0.004)
    h = 0.6 - seam * 0.5 + (nb.noise(140, detail=2, seed=109) - 0.5) * 0.05 - crack * 0.3 + lifted * 0.2
    base = nb.mixc(lin("#7a8085"), lin("#6e7479"), checker)
    col = nb.mulc(base, 0.95 + rnd * 0.08 + (fleck - 0.5) * 0.16)
    col = nb.mixc(col, nb.mulc(col, 0.62), wear * 0.45)
    col = nb.mixc(col, g(0.07), nb.maxf(seam, scuff * 0.75))
    col = nb.mixc(col, nb.mulc(col, 0.8), stain * 0.6)
    col = nb.mixc(col, g(0.1), crack)
    rough = 0.36 - wear * 0.12 + scuff * 0.2 + seam * 0.35 + stain * 0.1
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp(),
            "masks": common_masks(nb, 110), "post": weather(cavity=0.25, cav_r=0.004)}


def grating(nb, p):
    """Steel bar grating (1 m: bearing bars every 30 mm along V, cross rods every 100 mm), alpha cut-out: rounded
    bar tops polished by foot traffic, rust at the weld nodes, grime."""
    bu = nb.fract(nb.u * 33)
    bv = nb.fract(nb.v * 10)
    du = nb.minf(bu, 1 - bu)
    dvv = nb.minf(bv, 1 - bv)
    bear = nb.smooth(du, 0.085, 0.06)
    cross = nb.smooth(dvv, 0.028, 0.02)
    solid = nb.maxf(bear, cross)
    node = bear * cross
    crown = nb.smooth(du, 0.085, 0.0) * bear
    serr = (nb.sin(nb.v * 6.2831853 * 160) * 0.5 + 0.5) * bear * 0.3
    wear = nz(nb, 5, detail=5, seed=141)
    traffic = nb.smooth(nz(nb, 2, detail=3, seed=143), 0.45, 0.75)
    rust = nb.smooth(nz(nb, 8, detail=6, seed=142), 0.68, 0.8)
    h = solid * (0.8 + crown * 0.12 - serr * 0.1) + (wear - 0.5) * 0.03
    steel = nb.mulc(p.get("tint", lin("#4e5357")), 0.85 + (wear - 0.5) * 0.4)
    steel = nb.mixc(steel, lin("#9a9d9f"), crown * traffic * 0.6)
    steel = nb.mixc(steel, lin("#5e2e14"), nb.maxf(rust * 0.8, node * rust))
    col = nb.mixc(g(0.02), steel, solid)
    rough = nb.lerp(1.0, 0.5 + rust * 0.35 + (wear - 0.5) * 0.15 - crown * traffic * 0.25, solid)
    return {"color": col, "rough": rough.clamp(), "metal": solid * (0.85 - rust * 0.7), "height": h.clamp(),
            "alpha": nb.smooth(solid, 0.3, 0.5)}


def corrugated(nb, p):
    """Corrugated galvanised sheet (1 m, ~77 mm pitch, ribs along V): spangle, white rust, fastener rows every
    0.5 m with rust bleeding down the valleys, dents, paint remnants."""
    pitch = 13
    ph = nb.u * (6.2831853 * pitch)
    prof = nb.sin(ph) * 0.5 + 0.5
    spangle = nb.voronoi(70, seed=131, out="Color")
    dent = sn(nb, 3, detail=3, seed=137) * 0.08
    fv = nb.fract(nb.v * 2)
    rowd = nb.minf(fv, 1 - fv) * 0.5
    crest = nb.smooth(prof, 0.85, 0.95)
    fx = nb.absf(nb.fract(nb.u * pitch) - 0.25) / pitch
    screw = nb.smooth(((fx) ** 2 + (rowd - 0.0) ** 2) ** 0.5, 0.007, 0.005)
    oxide = nb.smooth(nz(nb, 4, detail=5, seed=134), 0.55, 0.9)
    rustb = nb.smooth(nz(nb, 4, detail=6, rough=0.6, seed=133), 0.82, 0.92)
    h = prof * 0.85 + 0.05 + dent + screw * 0.08 + (nb.noise(80, detail=3, seed=135) - 0.5) * 0.05 * rustb
    zinc = nb.mulc(lin("#8d9398"), 0.85 + (spangle - 0.5) * 0.3)
    zinc = nb.mixc(zinc, lin("#aeb0ab"), oxide * 0.35)
    rcol = nb.ramp(nz(nb, 25, detail=4, seed=136), [(0.3, lin("#3a1c0c")), (0.55, lin("#7a3a16")), (0.75, lin("#9b5a2a"))])
    col = nb.mixc(zinc, rcol, rustb)
    col = nb.mixc(col, lin("#3a3c3e"), screw)
    rough = 0.4 + oxide * 0.28 + rustb * 0.45 + (spangle - 0.5) * 0.08
    masks = common_masks(nb, 138, extra={"rust": screw + rustb * 0.3, "drip": screw * 0.5})
    return {"color": col, "rough": rough.clamp(), "metal": ((0.9 - oxide * 0.3) * (1 - rustb)).clamp(), "height": h.clamp(),
            "masks": masks, "post": weather(rain=0.5, rain_len=0.8, rain_dark=0.3, rust=1.0, rust_len=0.45, drip=0.4, cavity=0.2,
                                            grime=lin("#3a2a1c"))}
