"""Signature shapes for the landmarks: pagoda roofs, sign armatures, lattice masts, sculpted curtain-wall towers,
sky gardens, holo crowns, smokestacks, cooling towers, pipe racks, tanks, gantry cranes, sawtooth roofs, stilts.
All in Blender coordinates (Z up, front -Y), LOD aware (K.LOD)."""
import math
import random

from mathutils import Vector

import lmkit as L
from lmkit import K, Mesh, fbox, box
import lmparts as P


def lv():
    return K.LOD


# ============================================================================================== pagoda roof
def pagoda_roof(cx, cy, z, hw, hd, rise=3.2, eave=1.6, lift=0.9, steps=6, tile="lm_roof_tiles", soffit="lacquer_red",
                trim="brass", neon=None, ridge=0.25, n_corner=4):
    """Hipped roof with concave (curved) slopes and upturned corners. hw/hd: half size of the wall top; the eave
    overhangs by `eave`. Tiles carry explicit UVs (U along the eave, V up the slope)."""
    st = max(2, min(steps, steps if lv() == 0 else (4 if lv() == 1 else 2)))
    rx, ry = ridge if isinstance(ridge, (tuple, list)) else (ridge, ridge)
    rx, ry = min(rx, hw), min(ry, hd)
    rings = []
    for k in range(st + 1):
        t = k / st
        # concave profile: outward at the bottom, steep near the ridge
        s_out = (1 - t) ** 1.6
        x = (hw - rx) * (1 - t) + rx + eave * s_out
        y = (hd - ry) * (1 - t) + ry + eave * s_out
        zz = z + rise * (t ** 0.85) + 0.0
        cl = lift * (1 - t) ** 2.2
        rings.append((x, y, zz, cl))
    m = Mesh(tile, "pagoda")
    # each side: quads between ring k and k+1, corner lift applied at corners and blended along the edge
    sides = [((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))]
    nseg = 6 if lv() == 0 else (4 if lv() == 1 else 1)

    def pt(k, a, b, f):
        x, y, zz, cl = rings[k]
        sx = a[0] + (b[0] - a[0]) * f
        sy = a[1] + (b[1] - a[1]) * f
        lift_f = (abs(2 * f - 1)) ** 3 * cl
        return Vector((cx + sx * x, cy + sy * y, zz + lift_f))

    vacc = [0.0]
    for k in range(st):
        a = Vector(rings[k][:2] + (rings[k][2],))
        b = Vector(rings[k + 1][:2] + (rings[k + 1][2],))
        vacc.append(vacc[-1] + math.hypot(math.hypot(b.x - a.x, b.y - a.y) * 0.7, b.z - a.z))
    for (a, b) in sides:
        for k in range(st):
            for j in range(nseg):
                f0, f1 = j / nseg, (j + 1) / nseg
                p00, p10 = pt(k, a, b, f0), pt(k, a, b, f1)
                p11, p01 = pt(k + 1, a, b, f1), pt(k + 1, a, b, f0)
                elen = (pt(0, a, b, 1) - pt(0, a, b, 0)).length
                m.quad(p00, p10, p11, p01, tile, ((f0 * elen, vacc[k]), (f1 * elen, vacc[k]), (f1 * elen, vacc[k + 1]), (f0 * elen, vacc[k + 1])))
        # soffit (underside) from the wall line to the eave + fascia board
        if lv() < 2:
            for j in range(nseg):
                f0, f1 = j / nseg, (j + 1) / nseg
                e0, e1 = pt(0, a, b, f0), pt(0, a, b, f1)
                w0 = Vector((cx + (a[0] + (b[0] - a[0]) * f0) * hw, cy + (a[1] + (b[1] - a[1]) * f0) * hd, z - 0.05))
                w1 = Vector((cx + (a[0] + (b[0] - a[0]) * f1) * hw, cy + (a[1] + (b[1] - a[1]) * f1) * hd, z - 0.05))
                m.quad(w0, e0 - Vector((0, 0, 0.18)), e1 - Vector((0, 0, 0.18)), w1, soffit)
                m.quad(e0 - Vector((0, 0, 0.18)), e0, e1, e1 - Vector((0, 0, 0.18)), trim)
            if neon and lv() == 0:
                pts = [tuple(pt(0, a, b, j / nseg) - Vector((0, 0, 0.2))) for j in range(nseg + 1)]
                K.tube(pts, 0.035, 5, neon, caps=False)
    # ridge cap + finial
    top = rings[-1]
    box(cx - top[0], cx + top[0], cy - top[1], cy + top[1], top[2] - 0.05, top[2] + 0.25, trim)
    if lv() < 2:
        K.lathe([(0.25, 0.0), (0.18, 0.4), (0.3, 0.6), (0.06, 1.4), (0.02, 2.6)], 8, at=(cx, cy, top[2] + 0.25), mat=trim)
        if lv() == 0:
            # corner ornaments (upturned dragon-tail hooks)
            for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                x, y, zz, cl = rings[0]
                p = (cx + sx * x, cy + sy * y, zz + cl)
                K.tube([p, (p[0] + sx * 0.35, p[1] + sy * 0.35, p[2] + 0.45), (p[0] + sx * 0.25, p[1] + sy * 0.25, p[2] + 0.75)], 0.07, 5, trim)
                K.cyl(0.13, 0.32, 8, at=(p[0], p[1], p[2] - 0.75), mat="lantern_red")
    return rings[0]


# ============================================================================================== sign armatures
def sign_armature(F, u0, u1, z0, z1, out=0.6, rng=None, density=1.0):
    """Steel lattice frame bolted to a facade carrying a stack of lightbox signs, neon glyph boards and LED
    screens (Neon Market signature)."""
    rng = rng or random.Random(1)
    lvl = lv()
    # frame: two verticals + horizontals every 1.2 m, diagonal braces
    for u in (u0, u1):
        fbox(F, u - 0.06, u + 0.06, z0, z1, out - 0.06, out + 0.06, "metal_dark")
        if lvl < 2:
            z = z0
            while z < z1:
                fbox(F, u - 0.04, u + 0.04, z, z + 0.08, 0.0, out, "metal_dark")
                z += 2.4
    if lvl < 2:
        z = z0
        while z <= z1:
            fbox(F, u0, u1, z - 0.04, z + 0.04, out - 0.05, out + 0.05, "metal_dark")
            z += 1.2
    # panels
    z = z0 + 0.15
    while z < z1 - 0.6:
        h = rng.choice((0.9, 1.1, 1.6, 2.2))
        if z + h > z1:
            break
        kind = rng.random()
        if kind < 0.45:
            # horizontal lightbox board (front face), sign cell rotated -> use screen / panels
            mat = rng.choice(L.ADS + ["emit_panel_warm", "emit_panel_cyan", "emit_panel_magenta", "emit_panel_yellow", "emit_panel_violet"])
            fbox(F, u0 + 0.1, u1 - 0.1, z, z + h - 0.12, out + 0.06, out + 0.22, "metal_dark")
            m = Mesh(mat, "board")
            m.wall(F, u0 + 0.16, u1 - 0.16, z + 0.05, z + h - 0.17, out + 0.225, mat)
        elif kind < 0.8 and lvl == 0:
            # neon glyph row on a dark board
            fbox(F, u0 + 0.1, u1 - 0.1, z, z + h - 0.12, out + 0.06, out + 0.12, "black")
            cell = min(h - 0.3, 0.9)
            nglyph = max(1, int((u1 - u0 - 0.4) / cell))
            P.neon_glyphs(F, u0 + 0.25, z + 0.1, cell, nglyph, out + 0.16, rng.choice(L.NEONS), rng)
        else:
            fbox(F, u0 + 0.1, u1 - 0.1, z, z + h - 0.12, out + 0.06, out + 0.14, rng.choice(["metal_rusted", "metal_painted", "black"]))
        z += h
    return


def blade_tower(F, u, z0, h, out=1.4, rng=None, signs=None):
    """Tall vertical blade sign (several stacked lightbox cells) on a corner, both faces lit."""
    rng = rng or random.Random(2)
    n = max(2, int(h / 2.4))
    ch = h / n
    for i in range(n):
        P.lightbox_sign(F, u, z0 + i * ch, ch - 0.08, w_out=0.3, width=out, rng=rng, sign=(signs[i % len(signs)] if signs else None), depth=0.3)
    fbox(F, u - 0.17, u + 0.17, z0 - 0.15, z0 + h + 0.15, 0.25, 0.3 + out + 0.05, "metal_dark")


# ============================================================================================== masts / antennas
def lattice_mast(x, y, z, h, base=1.6, top=0.3, beacons=3, dishes=4, rng=None, mat="metal_painted_red", alt="metal_painted_white"):
    """Triangular lattice telecom mast tapering from base to top, red/white bands, beacons, dishes and panels."""
    rng = rng or random.Random(3)
    lvl = lv()
    n = max(3, int(h / 3.0))
    corners = [(math.cos(math.radians(90 + 120 * k)), math.sin(math.radians(90 + 120 * k))) for k in range(3)]

    def r_at(t):
        return base + (top - base) * t

    for k in range(3):
        a = corners[k]
        pts = [(x + a[0] * r_at(i / n), y + a[1] * r_at(i / n), z + h * i / n) for i in range(n + 1)]
        for i in range(n):
            K.beam(pts[i], pts[i + 1], 0.08 if lvl < 2 else 0.14, mat=mat if (i // 2) % 2 == 0 else alt)
        if lvl < 2:
            b = corners[(k + 1) % 3]
            for i in range(n):
                t0, t1 = i / n, (i + 1) / n
                p0 = (x + a[0] * r_at(t0), y + a[1] * r_at(t0), z + h * t0)
                p1 = (x + b[0] * r_at(t1), y + b[1] * r_at(t1), z + h * t1)
                K.beam(p0, p1, 0.035, mat="metal_dark")
                if lvl == 0:
                    p2 = (x + b[0] * r_at(t0), y + b[1] * r_at(t0), z + h * t0)
                    K.beam(p2, (x + a[0] * r_at(t0), y + a[1] * r_at(t0), z + h * t0), 0.03, mat="metal_dark")
    K.cyl(0.08, h * 0.18, 6, at=(x, y, z + h), r2=0.03, mat="metal_dark")
    for k in range(beacons):
        zz = z + h * (k + 1) / beacons
        K.cyl(0.14, 0.2, 6, at=(x, y, zz + (0.1 if k == beacons - 1 else 0)), mat="beacon_red")
    if lvl < 2:
        for k in range(dishes):
            t = rng.uniform(0.35, 0.85)
            ang = rng.uniform(0, 360)
            P.dish(x + math.cos(math.radians(ang)) * r_at(t), y + math.sin(math.radians(ang)) * r_at(t), z + h * t - 0.9, r=rng.uniform(0.5, 1.0), rot=ang - 90)
        for k in range(3):
            a = corners[k]
            t = 0.88
            px, py = x + a[0] * (r_at(t) + 0.15), y + a[1] * (r_at(t) + 0.15)
            box(px - 0.15, px + 0.15, py - 0.15, py + 0.15, z + h * t, z + h * t + 1.6, "paint_white")
    return [L.unity_pt(x, y, z + h * (k + 1) / beacons) for k in range(beacons)]


# ============================================================================================== towers
def loft_tower(pts_fn, z0, z1, floors_h, st, fl, key, cap=True, lobby=False):
    """Tower shaft whose plan is pts_fn(t) (CCW polygon, t = 0 at z0 .. 1 at z1). Each storey is a vertical
    prism of its own plan (setbacks/tapers step per floor), curtain walls on every facet."""
    M = Mesh(st.wall, "tower")
    n = max(1, int(round((z1 - z0) / floors_h)))
    fh = (z1 - z0) / n
    lvl = lv()
    prev = None
    for i in range(n):
        za = z0 + i * fh
        t = (i + 0.5) / n
        pts = pts_fn(t)
        frames = L.poly_frames(pts)
        for j, F in enumerate(frames):
            nb = max(1, int(round(F.length / st.bay)))
            bw = F.length / nb
            if lvl >= 2:
                M.wall(F, 0, F.length, za, za + fh, 0.0, st.wall)
                if i % 1 == 0:
                    g = fl.office_pane(i, (key, j))
                    M.quad(F.p(0.2, za + 0.9, 0.02), F.p(F.length - 0.2, za + 0.9, 0.02), F.p(F.length - 0.2, za + fh - 0.1, 0.02),
                           F.p(0.2, za + fh - 0.1, 0.02), g, ((0, 0), (1, 0), (1, 1), (0, 1)))
                continue
            for b in range(nb):
                P._curtain_bay(M, F, st, b * bw, (b + 1) * bw, za, fh, fl, i, (key, j, b), None, 0.0, light=True)
            if lvl == 0 and st.led_seam and i % 3 == 0:
                fbox(F, 0, F.length, za - 0.03, za + 0.03, 0.0, 0.06, st.led_seam)
        # slab edge between differing plans (setback roofs)
        if prev is not None and lvl < 2:
            if _area(prev) - _area(pts) > 0.5:
                M.cap(prev, za, "concrete_dark")
        prev = pts
    # vertical fins on the facets of the top plan (cheap) for depth
    if lvl < 2:
        for F in L.poly_frames(pts_fn(0.5)):
            nb = max(1, int(round(F.length / st.bay)))
            for b in range(0, nb + 1, 2):
                u = F.length * b / nb
                fbox(F, max(0, u - 0.06), min(F.length, u + 0.06), z0, z1, -0.06, st.fin or 0.4, st.trim)
    if cap:
        M.cap(pts_fn(1.0), z1, "concrete_dark")
    return M


def _area(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a / 2


def chamfer_rect(cx, cy, hw, hd, ch):
    return [(cx - hw + ch, cy - hd), (cx + hw - ch, cy - hd), (cx + hw, cy - hd + ch), (cx + hw, cy + hd - ch),
            (cx + hw - ch, cy + hd), (cx - hw + ch, cy + hd), (cx - hw, cy + hd - ch), (cx - hw, cy - hd + ch)]


def lobed_plan(cx, cy, r, lobe, n=4, seg=3, rot=0.0):
    """Cross / clover plan: n lobes of half-width `lobe` reaching r, faceted (CCW)."""
    pts = []
    for k in range(n):
        a = math.radians(rot + k * 360 / n)
        ca, sa = math.cos(a), math.sin(a)
        # lobe end: two corners + a faceted nose
        px, py = -sa, ca
        for s in range(seg + 1):
            f = -1 + 2 * s / seg
            ang = math.asin(max(-1, min(1, f)))
            ex = r * 0.86 + r * 0.14 * math.cos(ang)
            pts.append((cx + ca * ex + px * lobe * f, cy + sa * ex + py * lobe * f))
        # re-entrant corner between this lobe and the next
        a2 = math.radians(rot + (k + 0.5) * 360 / n)
        rr = lobe * 1.15
        pts.append((cx + math.cos(a2) * rr, cy + math.sin(a2) * rr))
    return pts


def sky_garden(cx, cy, pts, z, h, rng):
    """Open double-height garden storey: recessed glazing, columns at the facet corners, trees, planters, warm light."""
    lvl = lv()
    inner = [(cx + (x - cx) * 0.78, cy + (y - cy) * 0.78) for (x, y) in pts]
    M = Mesh("concrete", "garden")
    for F in L.poly_frames(inner):
        M.wall(F, 0, F.length, z, z + h, 0.0, "glass_dark")
        if lvl < 2:
            nb = max(1, int(F.length / 2.0))
            for b in range(nb):
                g = rng.choice(["win_plants", "window_lit_warm", "win_warm_living"])
                M.quad(F.p(b * F.length / nb + 0.05, z + 0.2, 0.01), F.p((b + 1) * F.length / nb - 0.05, z + 0.2, 0.01),
                       F.p((b + 1) * F.length / nb - 0.05, z + h - 0.3, 0.01), F.p(b * F.length / nb + 0.05, z + h - 0.3, 0.01), g,
                       ((0, 0), (1, 0), (1, 1), (0, 1)))
    M.cap(pts, z, "stone_light")
    M.cap(pts, z + h, "concrete_dark", down=True)
    for (x, y) in pts:
        K.cyl(0.35, h, 8 if lvl < 2 else 6, at=(x + (cx - x) * 0.04, y + (cy - y) * 0.04, z), mat="paint_white")
    if lvl < 2:
        for F in L.poly_frames(pts):
            fbox(F, 0, F.length, z + 1.0, z + 1.06, -0.4, -0.3, "titanium")
            if lvl == 0:
                m = Mesh("glass", "rail")
                m.wall(F, 0.3, F.length - 0.3, z + 0.05, z + 1.0, -0.35, "glass")
        # trees in planters along the rim
        for F in L.poly_frames(pts):
            n = max(1, int(F.length / 4.0))
            for k in range(n):
                u = (k + 0.5) * F.length / n
                p = F.p(u, z, -1.6)
                box(p.x - 0.8, p.x + 0.8, p.y - 0.8, p.y + 0.8, z, z + 0.6, "stone_dark")
                if lvl == 0 or k % 2 == 0:
                    K.cyl(0.12, 2.0, 6, at=(p.x, p.y, z + 0.6), mat="bark")
                    K.lathe([(0.2, 0.0), (1.3, 0.6), (1.1, 1.7), (0.0, 2.6)], 7, at=(p.x, p.y, z + 1.8),
                            mat=rng.choice(["foliage_dark", "foliage_mid"]))
        box(cx - 0.4, cx + 0.4, cy - 0.4, cy + 0.4, z + h - 0.12, z + h - 0.02, "led_white")


def holo_ring(cx, cy, z, r, h=1.2, mat="holo_cyan", n=48, tilt=0.0):
    """Open cylindrical band (holographic crown ring) - double sided additive material."""
    m = Mesh(mat, "holo")
    nn = n if lv() == 0 else max(16, n // 2)
    for i in range(nn):
        a0, a1 = math.tau * i / nn, math.tau * (i + 1) / nn
        p0 = Vector((cx + math.cos(a0) * r, cy + math.sin(a0) * r, z + math.sin(a0) * tilt))
        p1 = Vector((cx + math.cos(a1) * r, cy + math.sin(a1) * r, z + math.sin(a1) * tilt))
        up = Vector((0, 0, h))
        u0, u1 = i / nn, (i + 1) / nn
        m.quad(p0, p1, p1 + up, p0 + up, mat, ((u0, 0), (u1, 0), (u1, 1), (u0, 1)))
    return m


# ============================================================================================== industry
def smokestack(x, y, z, h, r0=2.4, r1=1.6, mat="metal_rusted", bands=("metal_painted_red", "paint_white"), beacon=True, ladder=True):
    lvl = lv()
    n = 20 if lvl == 0 else (12 if lvl == 1 else 8)
    K.cyl(r0, h, n, at=(x, y, z), r2=r1, mat=mat)
    if lvl < 2:
        for k, bm in enumerate(bands):
            zz = z + h * (0.82 + 0.08 * k)
            rr = r0 + (r1 - r0) * (zz - z) / h + 0.04
            K.cyl(rr, h * 0.05, n, at=(x, y, zz), mat=bm)
        K.cyl(r1 + 0.15, 0.6, n, at=(x, y, z + h - 0.6), mat="metal_dark")
        for k in range(1, int(h / 12)):
            zz = z + k * 12
            rr = r0 + (r1 - r0) * k * 12 / h
            K.torus(rr + 0.05, 0.06, n_major=n, n_minor=4, mat="metal_dark").move(x, y, zz)
            if lvl == 0:
                # platform ring
                K.cyl(rr + 0.9, 0.08, n, at=(x, y, zz), mat="metal_dark")
        if ladder and lvl == 0:
            K.beam((x + r0 + 0.25, y, z), (x + r1 + 0.25, y, z + h), 0.06, mat="metal_dark")
    if beacon:
        K.cyl(0.18, 0.25, 6, at=(x + r1 * 0.7, y, z + h), mat="beacon_red")
        K.cyl(0.18, 0.25, 6, at=(x - r1 * 0.7, y, z + h), mat="beacon_red")
    # glowing throat (furnace glow seen from above)
    K.cyl(r1 * 0.85, 0.05, n, at=(x, y, z + h - 0.2), mat="furnace")
    return L.unity_pt(x, y, z + h + 0.3)


def cooling_tower(x, y, z, h, rb, rw, rt, mat="lm_concrete_weathered"):
    """Hyperbolic cooling tower shell on raker legs (open at the top, steam glow inside)."""
    lvl = lv()
    n = 40 if lvl == 0 else (24 if lvl == 1 else 14)
    prof = []
    k = 10 if lvl < 2 else 5
    zw = 0.72
    for i in range(k + 1):
        t = i / k
        if t < zw:
            r = rw + (rb - rw) * ((zw - t) / zw) ** 1.8
        else:
            r = rw + (rt - rw) * ((t - zw) / (1 - zw)) ** 1.8
        prof.append((r, 0.06 * h + t * h * 0.94))
    outer = K.lathe(prof, n, at=(x, y, z), mat=mat, close_bottom=False, close_top=False)
    inner = K.lathe([(r - 0.35, zz) for (r, zz) in prof], n, at=(x, y, z), mat="concrete_dark", close_bottom=False, close_top=False)
    import bmesh as _b
    _b.ops.reverse_faces(inner.bm, faces=inner.bm.faces)
    # lip
    K.torus(rt - 0.17, 0.2, n_major=n, n_minor=6 if lvl < 2 else 4, mat=mat).move(x, y, z + h)
    # raker legs (diagonal columns) around the base
    nl = 24 if lvl == 0 else (12 if lvl == 1 else 0)
    for i in range(nl):
        a0 = math.tau * i / nl
        a1 = math.tau * (i + 1.5) / nl
        p0 = (x + math.cos(a0) * rb, y + math.sin(a0) * rb, z)
        p1 = (x + math.cos(a1) * (rb - 0.2), y + math.sin(a1) * (rb - 0.2), z + 0.06 * h)
        K.beam(p0, p1, 0.45, mat="concrete")
    K.cyl(rt - 0.5, 0.3, n, at=(x, y, z + h - 3.0), mat="furnace")    # steam glow inside the throat
    return L.unity_pt(x, y, z + h)


def tank(x, y, z, r, h, mat="metal_painted_white", dome=True, ladder=True, stripes=None):
    lvl = lv()
    n = 28 if lvl == 0 else (16 if lvl == 1 else 10)
    K.cyl(r, h, n, at=(x, y, z), mat=mat)
    if dome:
        K.lathe([(r, 0.0), (r * 0.8, r * 0.18), (r * 0.4, r * 0.28), (0.0, r * 0.3)], n, at=(x, y, z + h), mat=mat)
    if lvl < 2:
        if stripes:
            K.cyl(r + 0.02, h * 0.06, n, at=(x, y, z + h * 0.7), mat=stripes)
        if ladder and lvl == 0:
            K.beam((x + r + 0.3, y, z), (x + r + 0.3, y, z + h), 0.05, mat="metal_dark")
            K.tube([(x + r + 0.2, y - 0.5, z + h + 1.0), (x + r * 0.5, y - 0.5, z + h + r * 0.3 + 1.0)], 0.03, 4, "metal_painted_yellow")
        K.cyl(r + 0.1, 0.3, n, at=(x, y, z), mat="concrete_dark")


def pipe_run(pts, r, mat="metal_rusted", n=8, flanges=True):
    K.tube(pts, r, n if lv() == 0 else max(4, n // 2), mat)
    if flanges and lv() == 0:
        for i in range(len(pts) - 1):
            a, b = Vector(pts[i]), Vector(pts[i + 1])
            L_ = (b - a).length
            k = int(L_ / 4.0)
            for j in range(1, k):
                c = a + (b - a) * (j / k)
                K.tube([tuple(c - (b - a).normalized() * 0.06), tuple(c + (b - a).normalized() * 0.06)], r * 1.25, 8, "metal_dark")


def pipe_rack(x0, y, x1, z, levels=3, w=3.0, rng=None):
    """Steel pipe rack along X: portal frames every 6 m, stacked pipe runs of varied diameter."""
    rng = rng or random.Random(5)
    lvl = lv()
    L_ = x1 - x0
    nb = max(1, int(L_ / 6))
    for i in range(nb + 1):
        xx = x0 + L_ * i / nb
        for s in (-1, 1):
            box(xx - 0.15, xx + 0.15, y + s * w / 2 - 0.15, y + s * w / 2 + 0.15, 0.0, z + levels * 1.4, "metal_painted_yellow" if lvl < 2 else "metal_dark")
        for k in range(levels):
            zz = z + k * 1.4
            box(xx - 0.12, xx + 0.12, y - w / 2, y + w / 2, zz - 0.15, zz, "metal_dark")
    mats = ["metal_rusted", "metal_painted", "paint_glossy_red", "metal_painted_white", "metal_bare", "metal_painted_yellow"]
    for k in range(levels):
        zz = z + k * 1.4
        npipe = 3 if lvl < 2 else 1
        for p in range(npipe):
            r = rng.uniform(0.12, 0.35)
            yy = y - w / 2 + 0.4 + (w - 0.8) * (p + 0.5) / npipe
            pipe_run([(x0 - 0.5, yy, zz + r), (x1 + 0.5, yy, zz + r)], r, rng.choice(mats), flanges=lvl == 0)


def gantry_crane(x, y, z, span, h, length, rng=None, mat="metal_painted_yellow"):
    """Overhead gantry crane: two A-frame legs on rails, box girder, trolley, hook block; span along X."""
    lvl = lv()
    for s in (-1, 1):
        xx = x + s * span / 2
        for d in (-1, 1):
            K.beam((xx, y + d * 2.5, z), (xx, y + d * 0.6, z + h), 0.45, mat=mat)
        box(xx - 0.5, xx + 0.5, y - 3.0, y + 3.0, z, z + 0.6, "metal_dark")
        if lvl < 2:
            K.beam((xx, y - 2.0, z + h * 0.35), (xx, y + 2.0, z + h * 0.35), 0.25, mat=mat)
    box(x - span / 2 - 3, x + span / 2 + 3, y - 0.8, y + 0.8, z + h, z + h + 1.8, mat)
    if lvl < 2:
        box(x - 2.0, x + 0.5, y - 1.2, y + 1.2, z + h + 1.8, z + h + 3.6, "metal_painted")
        box(x + 0.6, x + 2.2, y - 1.4, y - 0.2, z + h + 1.8, z + h + 3.6, "glass_dark")
        if lvl == 0:
            for d in (-0.3, 0.3):
                K.cyl(0.02, h * 0.45, 4, at=(x + d, y, z + h * 0.55), mat="metal_bare")
            box(x - 0.5, x + 0.5, y - 0.4, y + 0.4, z + h * 0.5, z + h * 0.55, "hazard_yellow")
            K.tube([(x, y, z + h * 0.5), (x, y, z + h * 0.45), (x + 0.3, y, z + h * 0.42)], 0.08, 6, "metal_dark")
        K.cyl(0.18, 0.25, 6, at=(x - span / 2 - 2.8, y, z + h + 1.8), mat="emit_amber")
        K.cyl(0.18, 0.25, 6, at=(x + span / 2 + 2.8, y, z + h + 1.8), mat="emit_amber")
    # rails
    if lvl < 2:
        for s in (-1, 1):
            box(x + s * span / 2 - 0.15, x + s * span / 2 + 0.15, y - length / 2, y + length / 2, z, z + 0.15, "metal_bare")


def sawtooth_roof(x0, y0, x1, y1, z, teeth, rise=3.0, glass_mat="win_fluoro_kitchen", wall="lm_corrugated_painted"):
    """North-light sawtooth roof along Y: each tooth has a steep glazed face (toward +Y) and a sloped roof."""
    m = Mesh(wall, "saw")
    lvl = lv()
    tw = (y1 - y0) / teeth
    for i in range(teeth):
        ya, yb = y0 + i * tw, y0 + (i + 1) * tw
        # sloped roof from (ya, z) up to (yb, z+rise)
        a, b, c, d = Vector((x0, ya, z)), Vector((x1, ya, z)), Vector((x1, yb, z + rise)), Vector((x0, yb, z + rise))
        m.quad(a, b, c, d, wall, ((0, 0), (x1 - x0, 0), (x1 - x0, (d - a).length), (0, (d - a).length)))
        # glazed near-vertical face at yb (faces +Y)
        g0, g1 = Vector((x1, yb, z)), Vector((x0, yb, z))
        g2, g3 = Vector((x0, yb, z + rise)), Vector((x1, yb, z + rise))
        nwin = max(1, int((x1 - x0) / 3.0)) if lvl < 2 else 1
        for k in range(nwin):
            fa, fb = k / nwin, (k + 1) / nwin
            p0 = g0.lerp(g1, fa)
            p1 = g0.lerp(g1, fb)
            m.quad(p0, p1, p1 + Vector((0, 0, rise)), p0 + Vector((0, 0, rise)), glass_mat, ((0, 0), (1, 0), (1, 1), (0, 1)))
        # gable triangles at both ends
        for xx, s in ((x0, -1), (x1, 1)):
            bm = m.bm
            vs = [bm.verts.new((xx, ya, z)), bm.verts.new((xx, yb, z)), bm.verts.new((xx, yb, z + rise))]
            if s < 0:
                vs.reverse()
            try:
                f = bm.faces.new(vs)
                f[m.part.mats] = m.part.slot(wall)
                f[m.part.uvm] = K.UVM_KEEP
                for l in f.loops:
                    l[m.part.uvl].uv = (l.vert.co.y, l.vert.co.z)
            except ValueError:
                pass
        if lvl == 0:
            box(x0, x1, yb - 0.06, yb + 0.06, z + rise - 0.1, z + rise + 0.06, "metal_dark")
    return m


def stilts(x0, y0, x1, y1, z_top, spacing=4.0, r=0.3, mat="concrete", bracing=True):
    lvl = lv()
    nx = max(1, int((x1 - x0) / spacing))
    ny = max(1, int((y1 - y0) / spacing))
    for i in range(nx + 1):
        for j in range(ny + 1):
            xx = x0 + (x1 - x0) * i / nx
            yy = y0 + (y1 - y0) * j / ny
            if i not in (0, nx) and j not in (0, ny):
                continue
            K.cyl(r, z_top, 10 if lvl == 0 else 6, at=(xx, yy, 0.0), mat=mat)
            if bracing and lvl == 0 and i < nx and (j in (0, ny)):
                K.beam((xx, yy, 0.6), (x0 + (x1 - x0) * (i + 1) / nx, yy, z_top - 0.8), 0.12, mat="metal_rusted")
