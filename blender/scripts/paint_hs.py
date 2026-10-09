"""Smart materials for baked hard-surface atlases (Armor), driven by the high->low bake.

Zones (per-vertex attribute `mz`, set by gear.plate(zone=..., edge_zone=...) and the hinge/piston helpers):
  0 painted composite   - light neutral paint (Unity multiplies the Armor colour), satin, decals, chipped edges
  1 carbon fibre        - 2x2 twill weave of 3.5 mm tows under clear coat, dark (barely affected by the tint)
  2 anodised / brushed  - metallic, brushed along the plate's local x axis, tinted by the Armor colour (anodised)
  3 rubber / polymer    - matte dark polymer with a fine stipple
Wear: convex curvature (baked) + chamfer rings -> thin bright chips; AO + cavities -> grime; fine scratches.
Decals (zone 0): hazard chevrons, invented glyph serials (seven-segment style, no real letters), unit insignia.
"""
import math
import numpy as np
from texbake import fbm3, vnoise3, hash3, smoothstep as ss
import fabric as F

# decals per plate id: list of (kind, x, y, size_m, angle_deg, colour)
DECALS = {
    1: [("insignia", 0.025, 0.02, 0.03, 0, "light"), ("serial", -0.035, -0.045, 0.006, 0, "dark"), ("chevron", 0.0, -0.06, 0.012, 0, "amber")],
    2: [("serial", 0.0, 0.0, 0.005, 0, "dark")],
    3: [("insignia", 0.0, 0.02, 0.036, 0, "dark"), ("serial", -0.02, -0.06, 0.006, 0, "dark")],
    5: [("chevron", 0.0, -0.01, 0.01, 0, "amber")],
    7: [("serial", 0.0, -0.04, 0.005, 90, "dark"), ("chevron", 0.0, 0.05, 0.009, 0, "amber")],
    40: [("serial", 0.0, 0.0, 0.0045, 90, "light")],
    41: [("chevron", 0.0, 0.02, 0.008, 0, "amber")],
    60: [("serial", 0.0, -0.02, 0.005, 0, "light")],
    70: [("chevron", 0.0, 0.0, 0.008, 90, "amber")],
    100: [("insignia", 0.0, 0.0, 0.03, 0, "light"), ("serial", 0.0, -0.04, 0.005, 0, "dark")],
    101: [("serial", 0.0, 0.02, 0.005, 0, "dark")],
}
COL = {"dark": np.array((0.09, 0.09, 0.095)), "light": np.array((0.95, 0.95, 0.92)), "amber": np.array((0.9, 0.58, 0.12))}

# seven-segment layout in a unit cell (x 0..1, y 0..2): segments as rectangles
SEG = [(0.1, 1.9, 0.9, 2.0), (0.8, 1.05, 0.9, 1.95), (0.8, 0.05, 0.9, 0.95), (0.1, 0.0, 0.9, 0.1), (0.1, 0.05, 0.2, 0.95),
       (0.1, 1.05, 0.2, 1.95), (0.1, 0.95, 0.9, 1.05)]


def _rot(x, y, ang):
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return x * c + y * s, -x * s + y * c


def decal_mask(kind, x, y, size, seed):
    """Coverage 0..1 of a decal at local coordinates x, y (metres, decal centred at 0)."""
    if kind == "serial":
        h = size * 2
        n = 7
        w = size * 1.35
        X = x + n * w / 2
        idx = np.floor(X / w)
        fx = (X - idx * w) / size
        fy = (y + h / 2) / size
        on = np.zeros(len(x), bool)
        valid = (idx >= 0) & (idx < n) & (fy >= 0) & (fy <= 2)
        rng = np.random.default_rng(seed)
        pats = [rng.random(7) < 0.55 for _ in range(n)]
        for k in range(n):
            pk = pats[k]
            if k == 2:
                pk = np.array([False] * 6 + [True])     # a dash in the serial
            sel = valid & (idx == k)
            for si, (x0, y0, x1, y1) in enumerate(SEG):
                if pk[si]:
                    on |= sel & (fx >= x0) & (fx <= x1) & (fy >= y0) & (fy <= y1)
        return on.astype(np.float32)
    if kind == "chevron":
        band = np.abs(y) < size * 0.9
        stripe = ((x + np.abs(y) * 1.0) / (size * 1.4)) % 1.0 < 0.5
        lim = np.abs(x) < size * 4.5
        return (band & stripe & lim).astype(np.float32)
    if kind == "insignia":
        r = np.hypot(x, y) / size
        ring = (r > 0.82) & (r < 0.95)
        # inner triangle (pointing up) and three bars underneath: invented unit emblem
        tri = (y / size > -0.35) & (y / size < 0.55) & (np.abs(x / size) < (0.55 - y / size) * 0.62)
        hole = (y / size > -0.2) & (y / size < 0.3) & (np.abs(x / size) < (0.3 - y / size) * 0.45)
        bars = (y / size < -0.45) & (y / size > -0.62) & (np.abs(x / size) < 0.5) & ((np.floor((x / size + 0.5) / 0.34) % 1) == 0)
        return (ring | (tri & ~hole) | bars).astype(np.float32)
    return np.zeros(len(x), np.float32)


def armor(t, ao):
    n = len(t["P"])
    P = t["P"]
    A = t["A"]
    lx, ly, plate, wear_attr, cav = A["lx"], A["ly"], A["plate"], A["wear"], A["cavity"]
    zone = np.rint(A.get("mz", np.zeros(n))).astype(int)
    curv = t.get("curv", np.zeros(n))
    h = np.zeros(n, np.float32)
    base = np.full(n, 0.86, np.float32)
    metal = np.zeros(n, np.float32)
    smooth = np.full(n, 0.48, np.float32)
    paint = np.ones(n, np.float32)
    pid = np.round(plate).astype(int)
    # ---------------- zone 1: carbon fibre twill
    z1 = zone == 1
    if z1.any():
        tow = 0.0035
        u, v = lx[z1] / tow, ly[z1] / tow
        iu, iv = np.floor(u), np.floor(v)
        warp = (((iu + iv) // 2) % 2) == 0
        fu, fv = u - iu, v - iv
        crown = np.where(warp, np.sin(math.pi * fv), np.sin(math.pi * fu))
        fib = np.where(warp, np.sin(fu * 2 * math.pi * 6), np.sin(fv * 2 * math.pi * 6)) * 0.5 + 0.5
        h[z1] += 0.00012 * crown
        # graphite carbon (not black): readable weave under the clear coat in dark scenes
        base[z1] = 0.17 + 0.08 * np.where(warp, 1.0, 0.5) * (0.7 + 0.3 * fib)
        smooth[z1] = 0.66
        paint[z1] = 0.0
    # ---------------- zone 2: anodised, brushed
    z2 = zone == 2
    if z2.any():
        Q = np.stack([lx[z2] * 25.0, ly[z2] * 1400.0, plate[z2] * 3.1], -1)
        streak = vnoise3(Q, 1.0, 5.0) * 0.6 + vnoise3(Q * np.array((2, 2.1, 1)), 1.0, 9.0) * 0.4
        base[z2] = 0.74 + 0.06 * streak
        metal[z2] = 0.85
        smooth[z2] = 0.52 + 0.08 * streak
        h[z2] += 0.000006 * streak
        paint[z2] = 0.0
    # ---------------- zone 3: rubber / matte polymer
    z3 = zone == 3
    if z3.any():
        st = vnoise3(P[z3], 2500.0, 3.0)
        base[z3] = 0.22 + 0.02 * st
        smooth[z3] = 0.22
        h[z3] += 0.00002 * st
        paint[z3] = 0.0
    # ---------------- zone 0: painted composite, panel lines, decals
    z0 = zone == 0
    if z0.any():
        base[z0] = 0.84 + 0.04 * fbm3(P[z0], 60.0, 3, 1.0)
        smooth[z0] = 0.46 + 0.04 * fbm3(P[z0], 200.0, 2, 2.0)
        # extra panel lines in plate space: one cut across each larger plate, offset per plate
        off = (hash3(np.stack([plate[z0], plate[z0] * 0 + 1, plate[z0] * 0], -1), 3.0) - 0.5) * 0.04
        d_line = np.abs(ly[z0] - off - 0.35 * lx[z0])
        big = (np.abs(lx[z0]) > 0.02) | (np.abs(ly[z0]) > 0.03)
        d2 = np.abs(lx[z0] + off * 0.7 + 0.25 * ly[z0] - 0.03)
        groove = np.maximum(np.exp(-(d_line / 0.0006) ** 2), np.exp(-(d2 / 0.0006) ** 2) * (ly[z0] < off)) * big
        h[z0] -= 0.0004 * groove
        cav_z0 = groove
        dec_any = np.zeros(z0.sum(), np.float32)
        dec_col = np.zeros((z0.sum(), 3), np.float32)
        for p_id, items in DECALS.items():
            sel = pid[z0] == p_id
            if not sel.any():
                continue
            for k, (kind, dx, dy, size, ang, col) in enumerate(items):
                xx, yy = _rot(lx[z0][sel] - dx, ly[z0][sel] - dy, ang)
                m = decal_mask(kind, xx, yy, size, seed=p_id * 31 + k)
                if kind == "chevron":
                    m = (np.abs(yy) < size * 0.9) & (np.abs(xx) < size * 4.5)
                    m = m.astype(np.float32)
                    cvals = np.where((((xx + np.abs(yy)) / (size * 1.4)) % 1.0 < 0.5)[:, None], COL["amber"], COL["dark"])
                else:
                    cvals = np.tile(COL[col], (sel.sum(), 1))
                idx = np.where(sel)[0]
                upd = m > 0.5
                dec_any[idx[upd]] = 1.0
                dec_col[idx[upd]] = cvals[upd]
        zi = np.where(z0)[0]
        # decals are painted: keep them under wear
        decal_keep = dec_any > 0.5
    # ---------------- wear, grime, scratches (all zones)
    edge = np.clip(np.maximum(np.clip(curv, 0, 1), wear_attr * 0.55), 0, 1)
    nz = fbm3(P, 160.0, 4, 1.0) * 0.5 + 0.5
    chips = ss(0.72, 0.8, edge * 0.75 + nz * 0.38)          # thin, broken bands on the sharpest convex edges only
    scr = F.scratches(lx, ly, plate, density=40, seed=1.0, width=0.00016) * 0.35
    g = np.clip((1 - ao) * 1.1 + np.clip(-curv, 0, 1) * 0.6 + cav * 0.5 + (fbm3(P, 22.0, 4, 2.0) * 0.5 + 0.5 - 0.6) * 0.5, 0, 1)
    rgb = np.repeat(base[:, None], 3, 1) * np.array((1.0, 0.995, 0.985))
    if z0.any():
        dc = dec_col[decal_keep]
        rgb[zi[decal_keep]] = dc
    bare = np.clip(chips * np.where(zone == 3, 0.0, 1.0) * np.where(zone == 1, 0.2, 1.0) + scr * (zone == 0), 0, 1)
    steel = np.array((0.78, 0.78, 0.8))
    rgb = rgb * (1 - bare[:, None]) + steel * bare[:, None]
    metal = np.clip(metal * (1 - bare) + bare * 0.8, 0, 1)
    smooth = smooth * (1 - bare) + 0.62 * bare
    h -= 0.00008 * bare * (zone == 0)                          # paint thickness step at chips
    # grime last: darker, rougher in cavities and occluded areas
    rgb = rgb * (1 - 0.3 * g[:, None]) * np.array((1.0, 0.98, 0.95)) ** g[:, None]
    smooth = smooth * (1 - 0.35 * g)
    h += 0.000015 * fbm3(P, 500.0, 2, 7.0)
    return rgb, h, metal, np.clip(smooth, 0.05, 0.9), np.clip(paint * (1 - bare), 0, 1)
