"""Facades, floors, roofs and street-level / rooftop furniture for the landmark generator (see lmkit).

Units: metres. Faces are built in a Frame (u along the wall, z up, w outward). Every module honours K.LOD:
  LOD0  full detail (reveals, sills, mullions, frames, props, cables)
  LOD1  openings with reveals, big props only
  LOD2  massing: flat walls + flush window panes (lit windows keep the night silhouette), no props
"""
import math
import random

import lmkit as L
from lmkit import K, Mesh, fbox, fcyl, ftube, box

T = "building_trim_atlas"


class S(dict):
    """Style dict with attribute access and defaults."""

    def __getattr__(self, k):
        return self.get(k)


DEFAULT = S(wall="lm_concrete_weathered", wall2=None, trim="concrete_dark", ledge="concrete_dark", ledge_every=1, ledge_h=0.22,
            ledge_proj=0.1, G=4.4, H=3.4, bay=3.4, win="punched", win_w=1.5, win_sill=0.9, win_h=1.55, reveal=0.2,
            frame="metal_dark", mullion=True, transom=0.66, sill="concrete_dark", ac=0.15, cage=0.0, balcony=0.0, cant=0.0,
            grille=0.0, laundry=0.0, plants=0.0, signs=0.0, lit=0.4, warm=0.55, ground="shops", parapet=1.1, coping="metal_dark",
            roof="concrete_wet", pier_proj=0.0, cables=0.3, led_seam=None, blinds=0.0)


def style(base=None, **kw):
    s = S(DEFAULT if base is None else base)
    s.update(kw)
    return s


_DM = [None, None]


def dm():
    """Shared quad accumulator for small flat details of the current build pass (frame bars, grilles, fans)."""
    if _DM[0] is None or _DM[1] is not K._parts:
        _DM[0] = Mesh("metal_dark", "details")
        _DM[1] = K._parts
    return _DM[0]


def fq(F, u0, u1, z0, z1, w, mat):
    """Flat outward-facing quad in frame space (2 tris): thin bars, grilles, fan discs, LED lines."""
    return dm().wall(F, u0, u1, z0, z1, w, mat)


def rnd(*k):
    return random.Random(L.h(k))


# ============================================================================================== small props (frame space)
def ac_unit(F, u, z, w=0.0, s=1.0, rng=None):
    """Split-system condenser on brackets (back on the wall at w, sticks out ~0.35 m)."""
    W, Hh, D = 0.82 * s, 0.58 * s, 0.32 * s
    if L.lod() >= 1:
        return
    fbox(F, u - W / 2, u + W / 2, z, z + Hh, w + 0.04, w + 0.04 + D, "metal_painted_white")
    if L.lod() == 0:
        r = Hh * 0.36
        fq(F, u - W * 0.12 - r, u - W * 0.12 + r, z + Hh / 2 - r, z + Hh / 2 + r, w + 0.045 + D, "black")
        fq(F, u + W * 0.3, u + W * 0.44, z + 0.1, z + Hh - 0.1, w + 0.045 + D, "metal_painted")
        fq(F, u - W / 2 - 0.05, u - W / 2 - 0.02, z - 1.2, z + 0.2, w + 0.01, "rubber")


def cage(F, u0, u1, z0, z1, depth=0.55, w=0.0, pitch=0.13):
    """Burglar cage over a window: tin roof lip, frame posts, flat bar grille (KS signature)."""
    lv = L.lod()
    fbox(F, u0, u1, z1, z1 + 0.06, w, w + depth + 0.08, "metal_rusted")          # tin roof lip
    if lv >= 1:
        return
    fq(F, u0, u1, z0, z0 + 0.05, w + depth, "metal_dark")
    if lv == 0:
        for (a, b) in ((u0, u0 + 0.045), (u1 - 0.045, u1)):
            fq(F, a, b, z0, z1, w + depth - 0.01, "metal_dark")
        n = max(3, int((u1 - u0) / pitch))
        for i in range(1, n):
            uu = u0 + (u1 - u0) * i / n
            fq(F, uu - 0.009, uu + 0.009, z0, z1, w + depth - 0.02, "metal_dark")
        fq(F, u0, u1, (z0 + z1) / 2 - 0.02, (z0 + z1) / 2 + 0.02, w + depth - 0.015, "metal_dark")
        fq(F, u0, u1, z1 - 0.05, z1, w + depth - 0.015, "metal_dark")


def plant_pots(F, u0, u1, z, w, rng):
    if L.lod() > 0:
        return
    n = rng.randint(1, 3)
    for i in range(n):
        u = u0 + (u1 - u0) * (i + 0.5) / n + rng.uniform(-0.1, 0.1)
        fbox(F, u - 0.12, u + 0.12, z, z + 0.2, w + 0.05, w + 0.29, "terracotta")
        c = K.lathe([(0.24, 0.0), (0.2, 0.28), (0.0, 0.42)], 5, mat=rng.choice(["foliage_dark", "foliage_mid"]))
        c.move(u, -(w + 0.17), z + 0.18)
        c.xform(F.matrix())


def laundry(F, u0, u1, z, w, rng):
    """Bamboo poles sticking out with a line of clothes hanging parallel to the wall (Kowloon / canal balconies)."""
    if L.lod() > 0:
        return
    fbox(F, u0, u0 + 0.03, z, z + 0.03, w, w + 1.0, "wood")
    wl = w + 0.86
    fq(F, u0, u1, z - 0.01, z + 0.01, wl, "rope")
    cloth = ["cloth_white", "cloth_red", "cloth_blue", "cloth_yellow", "cloth_pink", "cloth_white"]
    u = u0 + 0.1
    while u < u1 - 0.3:
        ww = rng.uniform(0.25, 0.55)
        if rng.random() > 0.25 and u + ww < u1 - 0.05:
            hh = rng.uniform(0.35, 0.85)
            fq(F, u, u + ww, z - hh, z, wl + rng.uniform(-0.03, 0.03), rng.choice(cloth))
        u += ww + rng.uniform(0.03, 0.15)


def lightbox_sign(F, u, z0, h, w_out=0.2, width=0.7, rng=None, sign=None, depth=0.18):
    """Vertical blade lightbox projecting from the wall (both faces lit) on two arms."""
    sign = sign or rng.choice(L.SIGNS)
    a, b = w_out, w_out + width
    lv = L.lod()
    # body: two faces are separate quads so each carries the sign cell; edges trim
    p0 = K.part_count()
    fbox(F, u - depth / 2, u + depth / 2, z0, z0 + h, a, b, "metal_dark")
    m = Mesh(sign, "sign")
    for side in (-1, 1):
        uu = u + side * (depth / 2 + 0.004)
        p00, p10 = F.p(uu, z0 + 0.04, a + 0.03), F.p(uu, z0 + 0.04, b - 0.03)
        p11, p01 = F.p(uu, z0 + h - 0.04, b - 0.03), F.p(uu, z0 + h - 0.04, a + 0.03)
        if side > 0:
            m.quad(p00, p10, p11, p01, sign, ((0, 0), (1, 0), (1, 1), (0, 1)))
        else:
            m.quad(p10, p00, p01, p11, sign, ((0, 0), (1, 0), (1, 1), (0, 1)))
    if lv < 2:
        for zz in (z0 + 0.2, z0 + h - 0.2):
            fbox(F, u - 0.025, u + 0.025, zz - 0.025, zz + 0.025, 0.0, a, "metal_dark")
    return sign


def neon_glyphs(F, u0, z0, cell, count, w, mat, rng, r=0.025, vertical=False):
    """Neon tube glyphs (invented strokes) on a face plane at offset w."""
    if L.lod() > 0:
        return
    for i in range(count):
        gu = u0 + (0 if vertical else i * cell)
        gz = z0 + ((count - 1 - i) * cell if vertical else 0)
        pts = [(gu + cell * (0.15 + 0.35 * (k % 3)), gz + cell * (0.12 + 0.25 * (k // 3))) for k in range(12)]
        a = rng.randrange(12)
        for _ in range(rng.randint(3, 6)):
            ai, aj = a % 3, a // 3
            cand = [(ai + di, aj + dj) for di in (-1, 0, 1) for dj in (-1, 0, 1) if (di or dj) and 0 <= ai + di < 3 and 0 <= aj + dj < 4]
            bi, bj = rng.choice(cand)
            b = bj * 3 + bi
            ftube(F, [(pts[a][0], pts[a][1], w), (pts[b][0], pts[b][1], w)], r, mat, n=4)
            a = b


def awning(F, u0, u1, z, depth, mat, led=None):
    fbox(F, u0, u1, z, z + 0.12, 0.0, depth, mat)
    if L.lod() < 2:
        for uu in (u0 + 0.1, u1 - 0.1):
            ftube(F, [(uu, z + 0.06, depth - 0.05), (uu, z + 0.9, 0.0)], 0.02, "metal_dark", n=4)
        if led:
            fbox(F, u0, u1, z - 0.03, z, depth - 0.06, depth, led)


def cable_run(F, u0, u1, z, w, sag, rng, n=3):
    if L.lod() > 0:
        return
    for k in range(n):
        zz = z - k * 0.07
        mid = (u0 + u1) / 2
        ftube(F, [(u0, zz, w), (mid * 0.5 + u0 * 0.5, zz - sag * 0.75, w), (mid, zz - sag - k * 0.05, w),
                  (mid * 0.5 + u1 * 0.5, zz - sag * 0.75, w), (u1, zz, w)], 0.012 + 0.006 * k, "rubber", n=4)


# ============================================================================================== facade
def floor_list(height, G, H, parapet):
    """Storeys (z0, h) for a mass whose roof slab top is at `height` (parapet above). Ground = G, upper = H."""
    n = max(1, int((height - G) / H + 0.35) + 1)
    out = [(0.0, G)]
    for i in range(1, n):
        out.append((G + (i - 1) * H, H))
    # absorb the remainder into the top storey
    top = out[-1][0] + out[-1][1]
    if len(out) > 1:
        z0, h = out[-1]
        out[-1] = (z0, h + (height - top))
    else:
        out[0] = (0.0, height)
    return out


def facade(M, F, st, floors, fl, key, street=True, ground=None, upper=True, z_from=0.0, uoff=0.0, bays=None, meta=None):
    """One wall face from z_from to the top of `floors`. `fl` = L.Floors; `key` identifies the face for variants."""
    rng = random.Random(L.h((key, "facade")))
    lv = L.lod()
    Lf = F.length
    n = bays or max(1, int(round(Lf / st.bay)))
    bw = Lf / n
    ground = st.ground if ground is None else ground
    if not street and ground in ("shops", "arcade", "lobby"):
        ground = "service"
    top = floors[-1][0] + floors[-1][1]
    if lv >= 2:
        _facade_lod2(M, F, st, floors, fl, key, n, bw, ground, z_from, uoff)
        return
    for fi, (z0, h) in enumerate(floors):
        if z0 + h <= z_from + 1e-3:
            continue
        if fi == 0:
            _ground(M, F, st, z0, h, n, bw, ground, fl, key, rng, uoff, meta)
            continue
        kind = st.win
        for i in range(n):
            u0, u1 = i * bw, (i + 1) * bw
            br = random.Random(L.h((key, fi, i)))
            if kind == "curtain":
                _curtain_bay(M, F, st, u0, u1, z0, h, fl, fi, (key, i), br, uoff)
            elif kind == "ribbon":
                _ribbon_bay(M, F, st, u0, u1, z0, h, fl, fi, (key, i), br, uoff, first=(i == 0), last=(i == n - 1))
            elif kind == "industrial":
                _industrial_bay(M, F, st, u0, u1, z0, h, fl, fi, (key, i), br, uoff)
            else:
                _punched_bay(M, F, st, u0, u1, z0, h, fl, fi, (key, i), br, uoff, street)
        # floor ledge / slab band
        if st.ledge and (fi % max(1, st.ledge_every) == 0):
            fbox(F, -0.02, Lf + 0.02, z0 - st.ledge_h / 2, z0 + st.ledge_h / 2, 0.0, st.ledge_proj, st.ledge)
        if st.led_seam and lv == 0 and fi % 2 == 0:
            fbox(F, -0.01, Lf + 0.01, z0 - 0.02, z0 + 0.02, st.ledge_proj, st.ledge_proj + 0.01, st.led_seam)
    # curtain wall: vertical mullion fins over the tower shaft (one box per column, cheap)
    if st.win == "curtain" and lv < 2:
        zf = floors[0][0] + floors[0][1] if len(floors) > 1 else z_from
        for i in range(n + 1):
            u = i * bw
            fbox(F, max(0.0, u - 0.05), min(Lf, u + 0.05), max(zf, z_from), top, -0.06, st.fin or 0.32, st.trim)
    # corner / pier pilasters
    if st.pier_proj and lv < 2:
        for i in range(n + 1):
            u = i * bw
            fbox(F, max(-0.0, u - 0.18), min(Lf, u + 0.18), z_from, top, 0.0, st.pier_proj, st.trim)
    if street and lv == 0 and st.cables and rng.random() < st.cables:
        z = floors[0][1] + 0.3
        cable_run(F, 0.3, Lf - 0.3, z, 0.08, rng.uniform(0.2, 0.6), rng)


def _glass_for(fl, fi, key, st):
    return fl.window(fi, key)


def _punched_bay(M, F, st, u0, u1, z0, h, fl, fi, key, br, uoff, street):
    lv = L.lod()
    fine = fi <= (st.fine_floors or 4)
    bw = u1 - u0
    pair = st.win == "pair" and bw > 2.6
    ww = min(st.win_w, bw - 0.6) if not pair else min(st.win_w * 0.62, (bw - 0.9) / 2)
    sill, wh = st.win_sill, min(st.win_h, h - st.win_sill - 0.45)
    wz0, wz1 = z0 + sill, z0 + sill + wh
    cu = (u0 + u1) / 2
    opens = [(cu - ww / 2, cu + ww / 2)] if not pair else [(cu - 0.15 - ww, cu - 0.15), (cu + 0.15, cu + 0.15 + ww)]
    # wall around the openings
    xs = [u0] + [x for o in opens for x in o] + [u1]
    for k in range(0, len(xs) - 1, 2):
        M.wall(F, xs[k], xs[k + 1], z0, z0 + h, 0.0, st.wall, uoff)            # piers
    for (a, b) in opens:
        M.wall(F, a, b, z0, wz0, 0.0, st.wall2 or st.wall, uoff)              # spandrel below
        M.wall(F, a, b, wz1, z0 + h, 0.0, st.wall, uoff)                       # header above
        glass = _glass_for(fl, fi, (key, a), st)
        M.reveal(F, a, b, wz0, wz1, st.reveal, st.trim, glass, bottom_mat=st.sill)
        if lv == 0:
            # sill, frame and mullion/transom (flat bars in front of the pane). Full detail on the lower storeys,
            # upper storeys (seen from 15 m+) keep a two-quad sill and the mullion only.
            d = -st.reveal + 0.02
            if fine:
                fbox(F, a - 0.06, b + 0.06, wz0 - 0.07, wz0, -0.02, 0.06, st.sill)
            else:
                M.quad(F.p(a - 0.06, wz0, 0.06), F.p(b + 0.06, wz0, 0.06), F.p(b + 0.06, wz0, -0.02), F.p(a - 0.06, wz0, -0.02), st.sill)
                M.wall(F, a - 0.06, b + 0.06, wz0 - 0.07, wz0, 0.06, st.sill)
            if st.mullion and (b - a) > 0.9:
                fq(F, (a + b) / 2 - 0.03, (a + b) / 2 + 0.03, wz0, wz1, d, st.frame)
            if fine:
                if st.transom:
                    zt = wz0 + (wz1 - wz0) * st.transom
                    fq(F, a, b, zt - 0.03, zt + 0.03, d, st.frame)
                fq(F, a, b, wz1 - 0.06, wz1, d, st.frame)
                fq(F, a, a + 0.06, wz0, wz1, d, st.frame)
                fq(F, b - 0.06, b, wz0, wz1, d, st.frame)
    # extras
    roll = br.random()
    a, b = opens[0][0], opens[-1][1]
    if roll < st.cage:
        cage(F, a - 0.08, b + 0.08, wz0 - 0.15, wz1 + 0.1, depth=br.uniform(0.4, 0.7), pitch=0.13 if fine else 0.26)
        if br.random() < st.laundry * 2:
            laundry(F, a, b, wz1 - 0.1, 0.55, br)
        elif fine and br.random() < st.plants * 2:
            plant_pots(F, a, b, wz0 - 0.1, 0.0, br)
    elif roll < st.cage + st.balcony:
        _balcony(M, F, st, u0, u1, z0, br, fl, fi, key)
    elif roll < st.cage + st.balcony + st.cant and h < 4.0:
        _cantilever(M, F, st, u0 + 0.15, u1 - 0.15, z0 + 0.1, z0 + h - 0.1, br, fl, fi, key)
    else:
        if br.random() < st.ac:
            side = b + 0.55 if br.random() < 0.5 and b + 0.95 < u1 else (a - 0.55 if a - 0.95 > u0 else (a + b) / 2)
            zz = wz0 - 0.75 if side == (a + b) / 2 else wz0 + br.uniform(-0.2, 0.6)
            ac_unit(F, side, zz, 0.0)
        if br.random() < st.grille and lv == 0:
            n = int((b - a) / 0.12)
            for k in range(1, n):
                uu = a + (b - a) * k / n
                fq(F, uu - 0.009, uu + 0.009, wz0, wz1, -0.08, "metal_dark")
        if fine and br.random() < st.plants:
            plant_pots(F, a, b, wz0 - 0.07, 0.06, br)
    if street and br.random() < st.signs and lv < 2:
        u = u0 + 0.12 if br.random() < 0.5 else u1 - 0.12
        lightbox_sign(F, u, z0 + 0.4, min(h * br.uniform(0.7, 1.9), 5.5), w_out=0.25, width=br.uniform(0.6, 0.9), rng=br)


def _balcony(M, F, st, u0, u1, z0, br, fl, fi, key):
    """Recessed door + projecting slab with rail (open) or glazed / caged enclosure."""
    lv = L.lod()
    a, b = u0 + 0.35, u1 - 0.35
    M.wall(F, u0, a, z0, z0 + st.H, 0.0, st.wall)
    M.wall(F, b, u1, z0, z0 + st.H, 0.0, st.wall)
    M.wall(F, a, b, z0 + 2.6, z0 + st.H, 0.0, st.wall)
    M.reveal(F, a, b, z0 + 0.05, z0 + 2.6, 0.25, st.trim, fl.window(fi, (key, "b")), bottom_mat=st.trim)
    dep = br.uniform(1.0, 1.4)
    fbox(F, u0 + 0.1, u1 - 0.1, z0 - 0.08, z0 + 0.12, 0.0, dep, st.trim)
    kind = br.random()
    if kind < 0.45:          # solid parapet + rail
        fbox(F, u0 + 0.1, u1 - 0.1, z0 + 0.12, z0 + 1.0, dep - 0.08, dep, st.wall2 or st.trim)
        for s0 in (u0 + 0.1, u1 - 0.18):
            fbox(F, s0, s0 + 0.08, z0 + 0.12, z0 + 1.0, 0.0, dep, st.wall2 or st.trim)
        if lv == 0:
            fbox(F, u0 + 0.1, u1 - 0.1, z0 + 1.0, z0 + 1.05, dep - 0.09, dep + 0.01, "metal_dark")
    elif kind < 0.75:        # steel rail
        if lv == 0:
            n = int((u1 - u0) / 0.14)
            for k in range(n + 1):
                uu = u0 + 0.12 + (u1 - u0 - 0.24) * k / n
                fq(F, uu - 0.012, uu + 0.012, z0 + 0.12, z0 + 1.05, dep - 0.04, "metal_dark")
        fbox(F, u0 + 0.1, u1 - 0.1, z0 + 1.02, z0 + 1.07, dep - 0.08, dep - 0.02, "metal_dark")
    else:                    # enclosed (glazed / boarded) - Kowloon style
        fbox(F, u0 + 0.1, u1 - 0.1, z0 + 0.12, z0 + 1.0, dep - 0.06, dep, "lm_corrugated_painted")
        m = Mesh("glass_dark", "encl")
        m.wall(F, u0 + 0.1, u1 - 0.1, z0 + 1.0, z0 + 2.5, dep - 0.03, fl.window(fi, (key, "e")))
        fbox(F, u0 + 0.1, u1 - 0.1, z0 + 2.5, z0 + 2.62, 0.0, dep + 0.05, "metal_rusted")
        for s0 in (u0 + 0.1, u1 - 0.16):
            fbox(F, s0, s0 + 0.06, z0 + 0.12, z0 + 2.5, 0.0, dep, "metal_dark")
    if br.random() < st.laundry:
        laundry(F, u0 + 0.3, u1 - 0.3, z0 + 2.3, dep - 0.2, br)
    elif br.random() < st.plants * 2:
        plant_pots(F, u0 + 0.3, u1 - 0.3, z0 + 0.12, dep - 0.45, br)
    if br.random() < st.ac and lv < 2:
        ac_unit(F, u0 + 0.7, z0 + 0.12, dep - 0.5)


def _cantilever(M, F, st, u0, u1, z0, z1, br, fl, fi, key):
    """Enclosed box room hung off the facade (Kowloon): cladding, small windows, tin roof, brackets."""
    lv = L.lod()
    M.wall(F, u0 - 0.15, u1 + 0.15, z0 - 0.1, z1 + 0.1, 0.0, st.wall)
    dep = br.uniform(0.7, 1.3)
    clad = br.choice(["lm_corrugated_painted", "metal_painted", "lm_mosaic_tile", "metal_rusted"])
    fbox(F, u0, u1, z0, z1, 0.0, dep, clad)
    m = Mesh("glass_dark", "cant")
    wa, wb = u0 + 0.25, u1 - 0.25
    m.wall(F, wa, wb, z0 + 0.9, z0 + 2.0, dep + 0.005, fl.window(fi, (key, "c")))
    fbox(F, u0 - 0.05, u1 + 0.05, z1, z1 + 0.06, -0.02, dep + 0.12, "metal_rusted")
    if lv == 0:
        fbox(F, wa - 0.04, wb + 0.04, z0 + 0.86, z0 + 0.9, dep, dep + 0.06, "metal_dark")
        for uu in (u0 + 0.1, u1 - 0.1):
            ftube(F, [(uu, z0 - 0.9, 0.0), (uu, z0, dep - 0.1)], 0.03, "metal_rusted", n=4)
        if br.random() < 0.5:
            ac_unit(F, (u0 + u1) / 2, z0 - 0.7, 0.0, s=0.9)


def _curtain_bay(M, F, st, u0, u1, z0, h, fl, fi, key, br, uoff, light=False):
    lv = L.lod() if not light else 1
    spand = 0.9
    pane = fl.office_pane(fi, key)
    M.wall(F, u0, u1, z0, z0 + spand, 0.0, st.wall, uoff)                       # spandrel panel at the slab
    m = Mesh("glass_dark", "cw")
    m.quad(F.p(u0, z0 + spand, -0.06), F.p(u1, z0 + spand, -0.06), F.p(u1, z0 + h, -0.06), F.p(u0, z0 + h, -0.06), pane,
           ((0, 0), (1, 0), (1, 1), (0, 1)))
    # sloped sill joining the spandrel to the recessed glass
    M.quad(F.p(u0, z0 + spand, 0.0), F.p(u1, z0 + spand, 0.0), F.p(u1, z0 + spand, -0.06), F.p(u0, z0 + spand, -0.06), st.trim)
    if lv == 0:
        fbox(F, u0, u1, z0 + spand - 0.03, z0 + spand + 0.03, -0.04, 0.03, st.frame)
        if st.transom:
            fbox(F, u0, u1, z0 + h - 0.06, z0 + h, -0.06, 0.0, st.frame)


def _ribbon_bay(M, F, st, u0, u1, z0, h, fl, fi, key, br, uoff, first, last):
    sill = st.win_sill
    head = min(h - 0.4, sill + st.win_h)
    M.wall(F, u0, u1, z0, z0 + sill, 0.0, st.wall, uoff)
    M.wall(F, u0, u1, z0 + head, z0 + h, 0.0, st.wall, uoff)
    glass = fl.window(fi, key)
    M.quad(F.p(u0, z0 + sill, -0.12), F.p(u1, z0 + sill, -0.12), F.p(u1, z0 + head, -0.12), F.p(u0, z0 + head, -0.12), glass,
           ((0, 0), (1, 0), (1, 1), (0, 1)))
    M.quad(F.p(u0, z0 + sill, 0.0), F.p(u1, z0 + sill, 0.0), F.p(u1, z0 + sill, -0.12), F.p(u0, z0 + sill, -0.12), st.sill)
    M.quad(F.p(u0, z0 + head, -0.12), F.p(u1, z0 + head, -0.12), F.p(u1, z0 + head, 0.0), F.p(u0, z0 + head, 0.0), st.trim)
    if first:
        M.quad(F.p(u0, z0 + sill, 0.0), F.p(u0, z0 + sill, -0.12), F.p(u0, z0 + head, -0.12), F.p(u0, z0 + head, 0.0), st.trim)
    if last:
        M.quad(F.p(u1, z0 + sill, -0.12), F.p(u1, z0 + sill, 0.0), F.p(u1, z0 + head, 0.0), F.p(u1, z0 + head, -0.12), st.trim)
    if L.lod() == 0:
        fbox(F, u1 - 0.03, u1 + 0.03, z0 + sill, z0 + head, -0.11, -0.05, st.frame)
    if br.random() < st.ac:
        ac_unit(F, (u0 + u1) / 2, z0 + 0.15, 0.0, s=0.9)


def _industrial_glass(fl, fi, key):
    """Factory glazing: fluorescent / sodium-warm / frosted interiors only (no living rooms on a 4 m steel window)."""
    g = fl.window(fi, key)
    if g in L.WIN_DARK:
        return g
    return L.WIN_INDUSTRIAL[L.h(fl.seed, fi, key, "ind") % len(L.WIN_INDUSTRIAL)]


def _industrial_bay(M, F, st, u0, u1, z0, h, fl, fi, key, br, uoff):
    """Tall steel-framed multi-pane factory window (foundry / canal warehouses)."""
    lv = L.lod()
    a, b = u0 + 0.45, u1 - 0.45
    s0, s1 = z0 + 0.8, z0 + h - 0.5
    M.wall(F, u0, a, z0, z0 + h, 0.0, st.wall, uoff)
    M.wall(F, b, u1, z0, z0 + h, 0.0, st.wall, uoff)
    M.wall(F, a, b, z0, s0, 0.0, st.wall, uoff)
    M.wall(F, a, b, s1, z0 + h, 0.0, st.wall, uoff)
    M.reveal(F, a, b, s0, s1, 0.25, st.trim, _industrial_glass(fl, fi, key), bottom_mat=st.sill)
    if lv == 0:
        nu = max(2, int((b - a) / 0.5))
        nz = max(3, int((s1 - s0) / 0.45))
        d = -0.22
        for k in range(1, nu):
            uu = a + (b - a) * k / nu
            fq(F, uu - 0.025, uu + 0.025, s0, s1, d + 0.01, st.frame)
        for k in range(1, nz):
            zz = s0 + (s1 - s0) * k / nz
            fq(F, a, b, zz - 0.025, zz + 0.025, d + 0.015, st.frame)
        fbox(F, a - 0.08, b + 0.08, s0 - 0.08, s0, -0.02, 0.08, st.sill)
        # arched / lintel head
        fbox(F, a - 0.15, b + 0.15, s1, s1 + 0.25, 0.0, 0.06, st.trim)


def _facade_lod2(M, F, st, floors, fl, key, n, bw, ground, z_from, uoff):
    top = floors[-1][0] + floors[-1][1]
    M.wall(F, 0.0, F.length, max(z_from, 0.0), top, 0.0, st.wall, uoff)
    for fi, (z0, h) in enumerate(floors):
        if z0 + h <= z_from + 1e-3:
            continue
        if fi == 0:
            if ground in ("shops", "arcade", "lobby"):
                for i in range(n):
                    g = fl.window(0, (key, "g", i))
                    if g in L.WIN_DARK:
                        g = "window_lit_warm"
                    M.quad(F.p(i * bw + 0.3, z0 + 0.3, 0.02), F.p((i + 1) * bw - 0.3, z0 + 0.3, 0.02),
                           F.p((i + 1) * bw - 0.3, z0 + h - 1.0, 0.02), F.p(i * bw + 0.3, z0 + h - 1.0, 0.02), g, ((0, 0), (1, 0), (1, 1), (0, 1)))
            continue
        for i in range(n):
            u0, u1 = i * bw, (i + 1) * bw
            if st.win == "curtain":
                g = fl.office_pane(fi, (key, i))
                a, b, s0, s1 = u0, u1, z0 + 0.9, z0 + h
            elif st.win == "ribbon":
                g = fl.window(fi, (key, i))
                a, b, s0, s1 = u0, u1, z0 + st.win_sill, z0 + min(h - 0.4, st.win_sill + st.win_h)
            else:
                g = fl.window(fi, ((key, i), (u0 + u1) / 2 - min(st.win_w, bw - 0.6) / 2))
                ww = min(st.win_w, bw - 0.6)
                cu = (u0 + u1) / 2
                a, b, s0, s1 = cu - ww / 2, cu + ww / 2, z0 + st.win_sill, z0 + st.win_sill + min(st.win_h, h - st.win_sill - 0.45)
                if st.win == "industrial":
                    a, b, s0, s1 = u0 + 0.45, u1 - 0.45, z0 + 0.8, z0 + h - 0.5
                    g = _industrial_glass(fl, fi, (key, i))
            M.quad(F.p(a, s0, 0.02), F.p(b, s0, 0.02), F.p(b, s1, 0.02), F.p(a, s1, 0.02), g, ((0, 0), (1, 0), (1, 1), (0, 1)))


# ============================================================================================== ground floor
SHOP_FASCIA = ["screen_ad_a", "screen_ad_b", "screen_ad_c", "emit_panel_warm", "emit_panel_cyan", "emit_panel_white", "emit_panel_violet",
               "emit_panel_magenta", "emit_panel_yellow"]
AWNINGS = ["tarp", "tarp_blue", "metal_painted_red", "metal_dark", "metal_painted_yellow", "lacquer_green", "cloth_red"]


def _ground(M, F, st, z0, h, n, bw, ground, fl, key, rng, uoff, meta):
    lv = L.lod()
    Lf = F.length
    if ground in ("shops", "arcade"):
        rec = 0.0 if ground == "shops" else 1.6
        for i in range(n):
            u0, u1 = i * bw, (i + 1) * bw
            br = random.Random(L.h((key, "shop", i)))
            a, b = u0 + 0.28, u1 - 0.28
            sh = min(3.2, h - 1.0)
            M.wall(F, u0, a, z0, z0 + h, 0.0, st.trim)
            M.wall(F, b, u1, z0, z0 + h, 0.0, st.trim)
            M.wall(F, a, b, z0 + sh, z0 + h, 0.0, st.wall2 or st.wall, uoff)
            kind = br.random()
            if kind < 0.68:
                glass = L.WIN_WARM[br.randrange(len(L.WIN_WARM))] if br.random() < 0.7 else br.choice(L.WIN_LIT)
                M.reveal(F, a, b, z0 + 0.25, z0 + sh, 0.35 + rec, st.trim, glass, bottom_mat="concrete_dark")
                M.wall(F, a, b, z0, z0 + 0.25, 0.0, "concrete_dark")
                if lv == 0:
                    d = -0.33 - rec
                    for k in range(1, max(2, int((b - a) / 1.3))):
                        uu = a + (b - a) * k / max(2, int((b - a) / 1.3))
                        fq(F, uu - 0.035, uu + 0.035, z0 + 0.25, z0 + sh, d + 0.02, "metal_dark")
                    fq(F, a, b, z0 + sh - 0.8, z0 + sh - 0.74, d + 0.02, "metal_dark")
                if meta is not None and lv == 0:
                    p = F.p((a + b) / 2, z0 + 2.2, 0.8)
                    meta.setdefault("lights", []).append(L.light(p.x, p.y, p.z, glass if "warm" in glass else "#ffc890", 8, 0.8, "shop"))
            elif kind < 0.86:   # roller shutter (half-open, lit gap)
                M.reveal(F, a, b, z0 + 0.0, z0 + sh, 0.12 + rec, st.trim, "metal_painted", bottom_mat="concrete_dark")
                if lv == 0:
                    fbox(F, a, b, z0 + sh - 0.35, z0 + sh, -0.1, 0.12, "metal_dark")
                    m = Mesh("emit_strip_warm", "gap")
                    m.wall(F, a + 0.05, b - 0.05, z0 + 0.0, z0 + 0.25, -0.115, "emit_panel_warm")
            else:               # open stall front with counter
                M.reveal(F, a, b, z0 + 0.0, z0 + sh, 1.2 + rec, st.trim, br.choice(L.WIN_WARM), bottom_mat="concrete_dark")
                fbox(F, a + 0.05, b - 0.05, z0, z0 + 1.0, -0.6, 0.15, br.choice(["wood", "metal_painted", "tile_grimy"]))
                if lv == 0:
                    for k in range(3):
                        bx_u = a + 0.3 + k * (b - a - 0.6) / 2.5
                        fbox(F, bx_u, bx_u + 0.45, z0 + 1.0, z0 + 1.0 + br.uniform(0.15, 0.4), -0.4, 0.0,
                             br.choice(["cloth_red", "cloth_yellow", "plastic_orange", "cloth_white", "metal_painted_white"]))
                    for k in range(br.randint(2, 4)):
                        uu = a + 0.4 + k * 0.9
                        if uu < b - 0.2:
                            fcyl(F, uu, z0 + sh - 0.65, 0.5, 0.17, 0.42, br.choice(["lantern_red", "lantern_warm"]), n=8)
            # fascia sign + awning
            fz = z0 + sh + 0.12
            if lv < 2:
                fbox(F, a - 0.1, b + 0.1, fz, fz + 0.62, 0.0, 0.16, "metal_dark")
                m = Mesh("screen_ad_a", "fascia")
                m.wall(F, a, b, fz + 0.05, fz + 0.57, 0.165, br.choice(SHOP_FASCIA))
            if br.random() < 0.55:
                awning(F, u0 + 0.1, u1 - 0.1, fz - 0.15, br.uniform(1.1, 1.6), br.choice(AWNINGS),
                       led=br.choice(L.STRIPS) if br.random() < 0.6 else None)
        if ground == "arcade" and lv < 2:
            # colonnade on the face line, soffit above the arcade
            for i in range(n + 1):
                u = min(max(i * bw, 0.25), Lf - 0.25)
                fbox(F, u - 0.25, u + 0.25, z0, z0 + h, -0.25, 0.25, st.trim)
    elif ground == "lobby":
        M.wall(F, 0, Lf, z0 + h - 0.8, z0 + h, 0.0, st.wall, uoff)
        for i in range(n):
            u0, u1 = i * bw, (i + 1) * bw
            M.wall(F, u0, u0 + 0.2, z0, z0 + h - 0.8, 0.0, st.trim)
            M.wall(F, u1 - 0.2, u1, z0, z0 + h - 0.8, 0.0, st.trim)
            M.reveal(F, u0 + 0.2, u1 - 0.2, z0, z0 + h - 0.8, 0.6, st.trim, fl.office_pane(0, (key, i)), bottom_mat="concrete_dark")
        if lv < 2:
            fbox(F, 0, Lf, z0 + h - 0.85, z0 + h - 0.8, 0.0, 0.6, st.led_seam or "emit_strip_cyan")
    elif ground == "industrial":
        for i in range(n):
            u0, u1 = i * bw, (i + 1) * bw
            br = random.Random(L.h((key, "ind", i)))
            if br.random() < 0.45 and bw > 3.6:
                a, b = u0 + 0.4, u1 - 0.4
                dh = min(h - 0.6, 4.2)
                M.wall(F, u0, a, z0, z0 + h, 0.0, st.wall, uoff)
                M.wall(F, b, u1, z0, z0 + h, 0.0, st.wall, uoff)
                M.wall(F, a, b, z0 + dh, z0 + h, 0.0, st.wall, uoff)
                M.reveal(F, a, b, z0, z0 + dh, 0.2, st.trim, "metal_painted", bottom_mat="concrete_dark")
                if lv == 0:
                    for k in range(int(dh / 0.24)):
                        zz = z0 + 0.06 + k * 0.24
                        fq(F, a, b, zz, zz + 0.03, -0.18, "metal_dark")
                    fbox(F, a - 0.3, b + 0.3, z0 + dh + 0.05, z0 + dh + 0.2, 0.0, 0.8, "metal_dark")
                    fcyl(F, (a + b) / 2, z0 + dh + 0.35, 0.2, 0.08, 0.2, "emit_amber", n=8)
            else:
                _industrial_bay(M, F, st, u0, u1, z0, h, fl, 0, (key, i), br, uoff)
    else:  # service / plain: blank wall with a door and a lamp per few bays
        for i in range(n):
            u0, u1 = i * bw, (i + 1) * bw
            br = random.Random(L.h((key, "svc", i)))
            if br.random() < 0.3 and bw > 2.2:
                a, b = (u0 + u1) / 2 - 0.55, (u0 + u1) / 2 + 0.55
                M.wall(F, u0, a, z0, z0 + h, 0.0, st.wall, uoff)
                M.wall(F, b, u1, z0, z0 + h, 0.0, st.wall, uoff)
                M.wall(F, a, b, z0 + 2.3, z0 + h, 0.0, st.wall, uoff)
                M.reveal(F, a, b, z0, z0 + 2.3, 0.15, st.trim, "metal_painted", bottom_mat="concrete_dark")
                if lv == 0:
                    fbox(F, a + 0.3, b - 0.3, z0 + 2.45, z0 + 2.6, 0.0, 0.12, "metal_dark")
                    m = Mesh("emit_amber", "lamp")
                    m.wall(F, a + 0.33, b - 0.33, z0 + 2.46, z0 + 2.48, 0.121, "emit_amber")
            else:
                M.wall(F, u0, u1, z0, z0 + h, 0.0, st.wall, uoff)
                if br.random() < 0.25 and lv == 0:
                    fbox(F, u0 + 0.4, u0 + 1.0, z0 + 1.2, z0 + 2.1, 0.0, 0.25, "metal_painted")   # meter box


# ============================================================================================== roofs
def parapet(F, top, h, wall, coping="metal_dark", t=0.25):
    fbox(F, 0.0, F.length, top, top + h, -t, 0.0, wall)
    fbox(F, -0.02, F.length + 0.02, top + h, top + h + 0.06, -t - 0.03, 0.04, coping)


def water_tank(x, y, z, r=1.2, h=2.2, legs=1.6, mat="metal_painted_white"):
    lv = L.lod()
    if lv >= 2:
        K.cyl(r, h + legs, 6, at=(x, y, z), mat=mat)
        return
    for a in range(4):
        ang = math.radians(45 + a * 90)
        lx, ly = x + math.cos(ang) * r * 0.7, y + math.sin(ang) * r * 0.7
        K.beam((lx, ly, z), (lx, ly, z + legs), 0.1, 0.1, mat="metal_dark")
    K.cyl(r, h, K.seg(16), at=(x, y, z + legs), mat=mat)
    K.lathe([(r + 0.04, 0.0), (r * 0.2, 0.45), (0.0, 0.5)], K.seg(16), at=(x, y, z + legs + h), mat="metal_dark")
    if lv == 0:
        K.tube([(x + r, y, z + legs + 0.3), (x + r + 0.25, y, z + legs + 0.1), (x + r + 0.25, y, z + 0.05)], 0.05, 6, "metal_rusted")
        for k in (0.33, 0.66):
            K.torus(r + 0.02, 0.02, n_major=K.seg(16, 8), n_minor=4, mat="metal_dark").move(x, y, z + legs + h * k)


def antenna(x, y, z, h=6.0, beacon=True, arms=3):
    K.cyl(0.05, h, K.seg(6), at=(x, y, z), r2=0.025, mat="metal_dark")
    if L.lod() < 2:
        for k in range(arms):
            zz = z + h * (0.4 + 0.5 * k / max(1, arms))
            L_ = 0.9 - 0.2 * k
            K.beam((x - L_, y, zz), (x + L_, y, zz), 0.02, 0.02, mat="metal_bare")
    if beacon:
        K.cyl(0.07, 0.12, 6, at=(x, y, z + h), mat="beacon_red")


def dish(x, y, z, r=0.6, rot=0.0):
    p0 = K.part_count()
    K.cyl(0.04, 0.9, 6, at=(0, 0, 0), mat="metal_dark")
    d = K.lathe([(0.02, 0.0), (r * 0.5, 0.05), (r, 0.2), (r * 0.98, 0.21)], K.seg(14), at=(0, 0, 0), mat="paint_white", close_top=False)
    d.rot(x=-55).move(0, 0.1, 0.95)
    for p in K.parts_since(p0):
        p.rot(z=rot).move(x, y, z)


def roof_ac(x, y, z, rot=0.0):
    p0 = K.part_count()
    box(-0.75, 0.75, -0.5, 0.5, 0.12, 1.1, "metal_painted_white")
    box(-0.8, 0.8, -0.55, 0.55, 0.0, 0.12, "metal_dark")
    if L.lod() < 2:
        K.cyl(0.35, 0.03, K.seg(16), at=(0, 0, 1.1), mat="black")
    for p in K.parts_since(p0):
        p.rot(z=rot).move(x, y, z)


def shanty(x, y, z, w, d, h, rng, rot=0.0):
    """Rooftop shack: corrugated / plywood walls, mono-pitch tin roof, a lit window, door, pipes."""
    p0 = K.part_count()
    wall = rng.choice(["lm_corrugated_painted", "metal_rusted", "wood", "metal_painted", "metal_painted_white"])
    box(-w / 2, w / 2, -d / 2, d / 2, 0.0, h, wall)
    roof = K.box(w + 0.3, d + 0.4, 0.06, at=(0, 0, h + 0.15), mat=rng.choice(["metal_rusted", "lm_corrugated_painted", "tarp_blue"]))
    roof.rot(x=rng.choice((-7, 7)))
    if L.lod() < 2:
        m = Mesh("glass_dark", "shw")
        F = L.Frame(-w / 2, -d / 2, 1, 0, w)
        m.wall(F, w * 0.15, w * 0.15 + min(0.9, w * 0.35), h * 0.45, h * 0.8, 0.01,
               rng.choice(L.WIN_WARM + ["win_dark", "win_neon_room"]))
        fbox(F, w * 0.6, w * 0.6 + 0.8, 0.0, min(2.0, h - 0.1), 0.0, 0.03, "wood")
        if L.lod() == 0 and rng.random() < 0.5:
            K.cyl(0.05, h + 1.2, 6, at=(w / 2 - 0.2, d / 2 - 0.2, 0.0), mat="metal_rusted")
    for p in K.parts_since(p0):
        p.rot(z=rot).move(x, y, z)


def roof_clutter(x0, y0, x1, y1, z, rng, kind="mixed", density=1.0):
    """Rooftop clutter set inside a footprint: AC units, vents, tanks, antennas, dishes, shanties, solar, stairs hut."""
    W, D = x1 - x0, y1 - y0
    area = W * D
    lv = L.lod()
    n_ac = int(area / 60 * density)
    for i in range(n_ac):
        roof_ac(rng.uniform(x0 + 1.2, x1 - 1.2), rng.uniform(y0 + 1.2, y1 - 1.2), z, rot=rng.choice((0, 90)))
    if kind in ("mixed", "kowloon", "canal", "market"):
        n_t = 1 + int(area / 180 * density)
        for i in range(n_t):
            water_tank(rng.uniform(x0 + 1.6, x1 - 1.6), rng.uniform(y0 + 1.6, y1 - 1.6), z, r=rng.uniform(0.7, 1.3), h=rng.uniform(1.4, 2.4),
                       legs=rng.uniform(0.6, 2.2), mat=rng.choice(["metal_painted_white", "metal_rusted", "cloth_blue", "metal_painted"]))
    if kind == "kowloon":
        for i in range(int(area / 70 * density) + 1):
            w, d = rng.uniform(2.0, 3.6), rng.uniform(1.8, 3.0)
            shanty(rng.uniform(x0 + w / 2 + 0.3, x1 - w / 2 - 0.3), rng.uniform(y0 + d / 2 + 0.3, y1 - d / 2 - 0.3), z, w, d,
                   rng.uniform(2.1, 2.6), rng, rot=rng.choice((0, 90, 180, 270)) if abs(w - d) < 0.5 else rng.choice((0, 180)))
        for i in range(int(area / 25 * density) + 2):
            antenna(rng.uniform(x0 + 0.5, x1 - 0.5), rng.uniform(y0 + 0.5, y1 - 0.5), z, h=rng.uniform(3, 9), beacon=rng.random() < 0.3,
                    arms=rng.randint(1, 4))
        for i in range(int(area / 120) + 1):
            dish(rng.uniform(x0 + 1, x1 - 1), rng.uniform(y0 + 1, y1 - 1), z, r=rng.uniform(0.4, 0.9), rot=rng.uniform(0, 360))
    else:
        for i in range(int(area / 200 * density) + 1):
            antenna(rng.uniform(x0 + 0.8, x1 - 0.8), rng.uniform(y0 + 0.8, y1 - 0.8), z, h=rng.uniform(3, 7), beacon=True)
    if lv < 2 and W > 7 and D > 7:
        # stair bulkhead
        bw, bd = 2.6, 3.6
        bx = rng.uniform(x0 + bw / 2 + 0.8, x1 - bw / 2 - 0.8)
        by = rng.uniform(y0 + bd / 2 + 0.8, y1 - bd / 2 - 0.8)
        box(bx - bw / 2, bx + bw / 2, by - bd / 2, by + bd / 2, z, z + 2.7, "concrete_dark")
        box(bx - bw / 2 - 0.1, bx + bw / 2 + 0.1, by - bd / 2 - 0.1, by + bd / 2 + 0.1, z + 2.7, z + 2.85, "concrete_dark")
        box(bx - 0.45, bx + 0.45, by - bd / 2 - 0.03, by - bd / 2, z, z + 2.05, "metal_painted")
        box(bx + 0.55, bx + 0.75, by - bd / 2 - 0.08, by - bd / 2, z + 2.15, z + 2.3, "emit_amber")


# ============================================================================================== mass (block) builder
def side_style(st):
    """Flat variant for party / side faces next to other lots: same walls and windows, nothing projecting."""
    return style(st, cage=0.0, balcony=0.0, cant=0.0, signs=0.0, laundry=0.0, plants=0.0, ac=min(st.ac or 0.0, 0.2), cables=0.0)


def block(x0, y0, x1, y1, height, st, fl, seed, faces="sewn", street="s", roof=True, z_base=0.0, roofkind="mixed",
          meta=None, floors=None, clutter=1.0, parapet_h=None, ground_override=None, flat_sides="", z_from=None):
    """A complete rectangular mass: four facades (street faces get shops etc.), roof slab, parapet and clutter.
    faces: which faces are built ('s','e','n','w'); street: which of them are street faces."""
    M = Mesh(st.wall, "walls")
    fr = L.rect_frames(x0, y0, x1, y1)
    if floors is None:
        floors = floor_list(height - z_base, st.G, st.H, st.parapet)
        floors = [(z0 + z_base, h) for (z0, h) in floors]
    top = floors[-1][0] + floors[-1][1]
    for k in "sewn":
        if k not in faces:
            continue
        F = fr[k]
        fs = side_style(st) if k in flat_sides else st
        zf = z_base if z_from is None else max(z_base, z_from.get(k, z_base) if isinstance(z_from, dict) else z_from)
        facade(M, F, fs, floors, fl, (seed, k), street=k in street, ground=ground_override, z_from=zf, uoff=random.Random(seed).uniform(0, 4), meta=meta)
        if roof and st.parapet:
            parapet(F, top, parapet_h or st.parapet, st.wall2 or st.wall, st.coping)
    if roof:
        M.cap([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], top, st.roof)
        if clutter > 0 and L.lod() < 2:
            roof_clutter(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5, top, random.Random(seed * 7 + 1), roofkind, density=clutter)
    return top
