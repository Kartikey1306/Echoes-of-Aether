"""Procedural atlas cells: lit / dark window interiors, office curtain-wall panes and lightbox signs.

Every function returns a dict of float arrays for an (h, w) cell, row 0 = top:
  base  : linear albedo RGB          mask : (metallic, ao, height, smoothness)
  emit  : linear emission RGB (absolute, before the atlas' intensity normalisation)
  height: metres (for the normal map)
Interiors are painted as seen from the street (slightly from below: ceilings show more than floors). Glyphs are
invented strokes, never real words or logos.
"""
import numpy as np

import ptex as P

WARM = P.hexlin("#ffb070")
WARM2 = P.hexlin("#ffd29a")
COOL = P.hexlin("#bfe4ff")
FLUO = P.hexlin("#e6fff2")
TV = P.hexlin("#6fa8ff")
NEON_PINK = P.hexlin("#ff3fb4")
NEON_CYAN = P.hexlin("#19e3ff")
AMBER = P.hexlin("#ff9a3a")


def _empty(h, w):
    return {"base": np.zeros((h, w, 3), np.float32), "emit": np.zeros((h, w, 3), np.float32),
            "mask": np.zeros((h, w, 4), np.float32), "height": np.zeros((h, w), np.float32)}


def _glass(c, rng, h, w, dark_tint=(0.02, 0.028, 0.035), smooth=0.93):
    """Glass reflection layer: dark albedo, high smoothness, faint diagonal reflection streaks, dust at the bottom."""
    X, Y = P.grid(h, w)
    diag = (X / w * 0.6 + Y / h) * 1.0
    streak = 0.5 + 0.5 * np.sin(diag * 9.0 + rng.uniform(0, 6))
    dust = P.smooth(Y / h, 0.75, 1.0) * 0.35 + P.fbm(h, w, 6, int(rng.integers(1 << 30)), 4, 0.6) * 0.15
    base = np.asarray(dark_tint, np.float32)[None, None, :] * (0.8 + 0.4 * streak[..., None]) + dust[..., None] * 0.03
    c["base"] = base.astype(np.float32)
    c["mask"][..., 0] = 0.1
    c["mask"][..., 1] = 1.0
    c["mask"][..., 2] = 0.5
    c["mask"][..., 3] = np.clip(smooth - dust * 0.35, 0, 1)
    return c


def _room(h, w, rng, light, wall, lamp_x=None, ceiling=0.22, falloff=1.0, level=1.0):
    """Lit room: back wall with lamp hotspot, ceiling band, floor/furniture darkening. Returns emission."""
    X, Y = P.grid(h, w)
    u, v = X / w, Y / h
    lx = rng.uniform(0.25, 0.75) if lamp_x is None else lamp_x
    # back wall lit by a ceiling lamp: radial falloff from (lx, ceiling)
    d = np.hypot((u - lx) * 1.2, (v - ceiling) * 1.0)
    wall_l = (0.35 + 0.95 * np.exp(-(d * 2.2 / falloff) ** 2)) * P.smooth(v, ceiling - 0.02, ceiling + 0.03)
    # ceiling (seen from below): brighter near the lamp, darker at the far edge
    ceil = (0.55 + 0.6 * np.exp(-((u - lx) * 3.0) ** 2)) * (1 - P.smooth(v, ceiling - 0.02, ceiling + 0.03))
    lamp = np.exp(-(((u - lx) * w / max(w * 0.07, 2.0)) ** 2 + ((v - ceiling * 0.5) * h / max(h * 0.035, 1.5)) ** 2))
    e = (wall_l + ceil * 0.8)[..., None] * wall[None, None, :] + lamp[..., None] * light[None, None, :] * 2.5
    tex = P.fbm(h, w, 5, int(rng.integers(1 << 30)), 3, 0.5)
    e *= (0.85 + 0.3 * tex)[..., None]
    return (e * level).astype(np.float32)


def _furniture(h, w, rng, emit, dark=0.06):
    """Dark silhouettes along the bottom (sofa / table / shelf / plant) that occlude the lit room."""
    m = np.zeros((h, w), np.float32)
    x = rng.uniform(-0.1, 0.2) * w
    while x < w:
        kind = rng.integers(4)
        fw = rng.uniform(0.18, 0.42) * w
        if kind == 0:     # sofa / bed block
            top = h * rng.uniform(0.72, 0.82)
            m = np.maximum(m, P.rect_mask(h, w, x, top, x + fw, h + 2))
        elif kind == 1:   # shelf with books
            top = h * rng.uniform(0.35, 0.55)
            m = np.maximum(m, P.rect_mask(h, w, x, top, x + fw * 0.6, h + 2) * 0.92)
            for k in range(4):
                yy = top + (h - top) * k / 4
                m = np.minimum(m, 1 - P.rect_mask(h, w, x + 3, yy + 2, x + fw * 0.6 - 3, yy + 4) * 0.4)
        elif kind == 2:   # plant
            cx, cy, r = x + fw * 0.4, h * rng.uniform(0.62, 0.74), fw * 0.28
            leaf = P.circle_mask(h, w, cx, cy, r) * (0.6 + 0.4 * P.fbm(h, w, 12, int(rng.integers(1 << 30)), 3, 0.6))
            m = np.maximum(m, P.smooth(leaf, 0.45, 0.6))
            m = np.maximum(m, P.rect_mask(h, w, cx - fw * 0.12, cy + r * 0.6, cx + fw * 0.12, h + 2))
        else:             # table + lamp
            top = h * rng.uniform(0.78, 0.86)
            m = np.maximum(m, P.rect_mask(h, w, x, top, x + fw, top + h * 0.03))
            m = np.maximum(m, P.rect_mask(h, w, x + fw * 0.1, top, x + fw * 0.16, h + 2))
            m = np.maximum(m, P.rect_mask(h, w, x + fw * 0.84, top, x + fw * 0.9, h + 2))
        x += fw + rng.uniform(0.02, 0.2) * w
    emit *= (1 - m * (1 - dark))[..., None]
    return emit


def _curtain(h, w, rng, emit, side, cover, color, translucent=0.35):
    """Gathered curtain on one side (side -1 left, 1 right) covering `cover` of the width; glows when backlit."""
    X, Y = P.grid(h, w)
    u = X / w
    edge = cover if side < 0 else 1 - cover
    m = P.smooth(u, edge + 0.02, edge - 0.02) if side < 0 else P.smooth(u, edge - 0.02, edge + 0.02)
    folds = 0.55 + 0.45 * np.sin(u * w / rng.uniform(5, 9) * 2 * np.pi + rng.uniform(0, 6)) ** 2
    lum = np.mean(emit, axis=-1, keepdims=True)
    glow = lum * translucent * folds[..., None] * color[None, None, :] / max(float(np.max(color)), 1e-3)
    return emit * (1 - m[..., None]) + glow * m[..., None]


def _blinds(h, w, rng, emit, top_frac, slat_px=6.0, open_frac=0.35):
    X, Y = P.grid(h, w)
    v = Y / h
    region = 1 - P.smooth(v, top_frac - 0.01, top_frac + 0.01)
    ph = (Y % slat_px) / slat_px
    slat = P.smooth(ph, open_frac - 0.08, open_frac) * (1 - P.smooth(ph, 0.92, 1.0))
    lum = emit * (0.25 + 0.55 * (1 - slat))[..., None] + emit * 0.1
    shade = emit * (1 - region[..., None]) + lum * region[..., None]
    return shade


def _sill_shadow(h, w, emit):
    X, Y = P.grid(h, w)
    v = Y / h
    vign = (P.smooth(v, 1.0, 0.86) * 0.6 + 0.4) * (P.smooth(X / w, 0.0, 0.06) * P.smooth(X / w, 1.0, 0.94) * 0.5 + 0.5)
    return emit * vign[..., None]


def window_cell(h, w, variant, seed):
    """Residential window interior variants (see VARIANTS)."""
    rng = np.random.default_rng(seed)
    c = _glass(_empty(h, w), rng, h, w)
    e = np.zeros((h, w, 3), np.float32)
    if variant == "warm_living":
        e = _room(h, w, rng, WARM, WARM * 0.55, level=0.9)
        e = _furniture(h, w, rng, e)
        e = _curtain(h, w, rng, e, -1, 0.22, P.hexlin("#c8502e"))
    elif variant == "tv_room":
        e = _room(h, w, rng, TV * 0.4, P.hexlin("#203a66") * 0.6, ceiling=0.18, level=0.45)
        X, Y = P.grid(h, w)
        flick = np.exp(-(((X / w - 0.6) * 2.5) ** 2 + ((Y / h - 0.75) * 3.0) ** 2))
        e += flick[..., None] * TV[None, None, :] * 1.1
        e = _furniture(h, w, rng, e, dark=0.03)
    elif variant == "neon_room":
        e = _room(h, w, rng, NEON_PINK, NEON_PINK * 0.45, level=0.8)
        X, Y = P.grid(h, w)
        segs = []
        for k in range(3):
            segs += P.glyph_strokes(rng, w * (0.18 + 0.22 * k), h * 0.3, w * 0.14, h * 0.2)
        tube = P.seg_mask(h, w, segs, max(2.0, w * 0.012))
        e += P.blur(tube, 2.0, False)[..., None] * NEON_CYAN[None, None, :] * 1.5 + tube[..., None] * NEON_CYAN[None, None, :] * 2.0
        e = _furniture(h, w, rng, e)
    elif variant == "dark":
        e = _room(h, w, rng, COOL * 0.05, COOL * 0.02, level=0.25)
        e = _furniture(h, w, rng, e, 0.3)
    elif variant == "blinds_warm":
        e = _room(h, w, rng, WARM2, WARM * 0.6, level=0.95)
        e = _blinds(h, w, rng, e, rng.uniform(0.45, 0.75), slat_px=max(4.0, h / 34))
    elif variant == "plants":
        e = _room(h, w, rng, WARM2, WARM * 0.7, level=1.0)
        X, Y = P.grid(h, w)
        leaves = np.zeros((h, w), np.float32)
        for k in range(7):
            cx, cy = rng.uniform(0.05, 0.95) * w, rng.uniform(0.55, 0.95) * h
            r = rng.uniform(0.06, 0.16) * w
            leaves = np.maximum(leaves, P.circle_mask(h, w, cx, cy, r) * (0.5 + 0.5 * P.fbm(h, w, 16, int(rng.integers(1 << 30)), 3, 0.6)))
        e *= (1 - P.smooth(leaves, 0.45, 0.62) * 0.94)[..., None]
    elif variant == "fluoro_kitchen":
        e = _room(h, w, rng, FLUO, P.hexlin("#a9d8b8") * 0.7, ceiling=0.15, level=0.95)
        X, Y = P.grid(h, w)
        tube = P.rect_mask(h, w, w * 0.2, h * 0.06, w * 0.8, h * 0.09)
        e += tube[..., None] * FLUO[None, None, :] * 3.0
        e = _furniture(h, w, rng, e, 0.08)
    elif variant == "standby":
        e = _room(h, w, rng, COOL * 0.03, COOL * 0.015, level=0.25)
        e = _furniture(h, w, rng, e, 0.4)
        for k in range(3):
            e += P.circle_mask(h, w, rng.uniform(0.2, 0.8) * w, rng.uniform(0.6, 0.85) * h, max(1.2, w * 0.006))[..., None] * P.hexlin("#ff2020")[None, None, :] * 3.0
    elif variant == "curtains_closed":
        e = _room(h, w, rng, AMBER, AMBER * 0.8, level=0.9)
        e = _curtain(h, w, rng, e, -1, 0.52, P.hexlin("#ff7a2a"), 0.55)
        e = _curtain(h, w, rng, e, 1, 0.5, P.hexlin("#ff7a2a"), 0.55)
    elif variant == "monitor_den":
        e = _room(h, w, rng, NEON_CYAN * 0.3, P.hexlin("#0f3040"), ceiling=0.2, level=0.4)
        for k in range(rng.integers(2, 4)):
            x0 = rng.uniform(0.1, 0.65) * w
            y0 = rng.uniform(0.5, 0.65) * h
            sw, sh = rng.uniform(0.16, 0.26) * w, rng.uniform(0.1, 0.16) * h
            scr = P.rect_mask(h, w, x0, y0, x0 + sw, y0 + sh)
            lines = 0.6 + 0.4 * (np.sin(P.grid(h, w)[1] * 1.4) > 0)
            e += (scr * lines)[..., None] * NEON_CYAN[None, None, :] * 1.6
            e += P.blur(scr, w * 0.05, False)[..., None] * NEON_CYAN[None, None, :] * 0.8
        e = _furniture(h, w, rng, e, 0.04)
    elif variant == "frosted":
        e = _room(h, w, rng, COOL, COOL * 0.8, level=0.8)
        e = P.blur(e, w * 0.06, False)
        c["mask"][..., 3] = 0.45
        c["base"] = c["base"] + 0.06
    elif variant == "papered":
        e = _room(h, w, rng, WARM * 0.15, WARM * 0.08, level=0.4)
        X, Y = P.grid(h, w)
        paper = np.zeros((h, w), np.float32)
        for k in range(rng.integers(3, 6)):
            x0, y0 = rng.uniform(-0.1, 0.7) * w, rng.uniform(-0.1, 0.7) * h
            paper = np.maximum(paper, P.rect_mask(h, w, x0, y0, x0 + rng.uniform(0.3, 0.6) * w, y0 + rng.uniform(0.3, 0.5) * h))
        news = 0.55 + 0.25 * P.fbm(h, w, 30, int(rng.integers(1 << 30)), 3, 0.6)
        c["base"] = P.lerp(c["base"], np.stack([news * 0.5, news * 0.46, news * 0.38], -1), paper)
        c["mask"][..., 3] = P.lerp(c["mask"][..., 3], 0.25, paper)
        e = e * (1 - paper[..., None]) + e * paper[..., None] * 0.25
    else:
        raise KeyError(variant)
    e = _sill_shadow(h, w, e)
    c["emit"] = np.clip(e, 0, 8).astype(np.float32)
    return c


WINDOW_VARIANTS = ["warm_living", "tv_room", "neon_room", "dark", "blinds_warm", "plants", "fluoro_kitchen", "standby",
                   "curtains_closed", "monitor_den", "frosted", "papered"]


def office_cell(h, w, variant, seed):
    """Tall curtain-wall pane (about 1.8 x 2.7 m) of an office floor seen from the street (slightly from below):
    ceiling with perspective rows of troffer lights, far wall / columns, desk band with monitors, chair silhouettes."""
    rng = np.random.default_rng(seed)
    c = _glass(_empty(h, w), rng, h, w, dark_tint=(0.016, 0.022, 0.03), smooth=0.95)
    X, Y = P.grid(h, w)
    u, v = X / w, Y / h
    e = np.zeros((h, w, 3), np.float32)
    lit = not variant.startswith("dark")
    if lit:
        col = {"open_cool": COOL, "open_warm": WARM2, "partial": COOL, "lounge_magenta": NEON_PINK * 0.8 + WARM * 0.2,
               "server": NEON_CYAN * 0.5, "blinds": COOL * 0.9 + WARM2 * 0.1}[variant]
        hz = 0.42                                      # horizon of the ceiling perspective (eye below the floor)
        ceil = 1 - P.smooth(v, hz - 0.01, hz + 0.01)
        # ceiling: falloff toward the horizon (far away = dimmer and denser)
        e += (ceil * (0.05 + 0.12 * (1 - v / hz)))[..., None] * col[None, None, :]
        # troffer rows in perspective: depth t -> screen row hz * (1 - 1/(1+t))
        rows = 7
        for k in range(rows):
            t = (k + 0.6) * 0.9
            yy = hz * (1 - 1 / (1 + t)) * 0.98
            yy = hz - yy
            th = max(0.7, h * 0.03 / (1 + t))
            on = variant != "partial" or (k % 3 == 1)
            if not on:
                continue
            gap = 0.5 / (1 + t * 0.5)
            off = rng.uniform(0, 1)
            seg = ((u * (2.0 + t) + off) % 1.0) < (1 - gap * 0.6)
            m = P.rect_mask(h, w, 0, yy * h - th, w, yy * h + th) * seg
            e += m[..., None] * col[None, None, :] * (2.2 / (1 + 0.35 * t))
        e += P.blur(e, 2.0, False) * 0.6
        # far wall + columns under the ceiling
        wall = P.smooth(v, hz, hz + 0.02) * (1 - P.smooth(v, 0.66, 0.68))
        tex = P.fbm(h, w, 4, int(rng.integers(1 << 30)), 3)
        e += (wall * (0.07 + 0.06 * tex))[..., None] * col[None, None, :]
        for k in range(rng.integers(0, 2) + 1):
            cx = rng.uniform(0.1, 0.9) * w
            colm = P.rect_mask(h, w, cx - w * 0.04, hz * h, cx + w * 0.04, h)
            e *= (1 - colm * 0.75)[..., None]
        # desks / partitions band, monitors, chair silhouettes
        desk = P.smooth(v, 0.66, 0.68)
        e *= (1 - desk * 0.9)[..., None]
        for k in range(rng.integers(2, 5)):
            x0 = rng.uniform(0.02, 0.8) * w
            mw = rng.uniform(0.1, 0.18) * w
            y0 = rng.uniform(0.56, 0.63) * h
            scr = P.rect_mask(h, w, x0, y0, x0 + mw, y0 + h * 0.06)
            tint = TV if variant != "server" else NEON_CYAN
            e += scr[..., None] * tint[None, None, :] * 0.9
            e += P.blur(scr, w * 0.05, False)[..., None] * tint[None, None, :] * 0.25
        for k in range(rng.integers(0, 3)):
            cx, cy = rng.uniform(0.1, 0.9) * w, rng.uniform(0.66, 0.72) * h
            chair = P.circle_mask(h, w, cx, cy, w * 0.07) + P.rect_mask(h, w, cx - w * 0.08, cy, cx + w * 0.08, cy + h * 0.1)
            e *= (1 - np.clip(chair, 0, 1) * 0.85)[..., None]
        if variant == "server":
            for k in range(int(w / 9)):
                x0 = k * 9 + 2
                rack = P.rect_mask(h, w, x0, h * 0.44, x0 + 5, h * 0.95)
                blink = ((Y // 3 + k * 7) % 5 == 0).astype(np.float32)
                e = e * (1 - rack[..., None] * 0.7) + (rack * blink)[..., None] * NEON_CYAN[None, None, :] * 1.4
        if variant == "blinds":
            e = _blinds(h, w, rng, e, 0.62, slat_px=max(3.0, h / 70))
        e *= rng.uniform(0.75, 1.0)
    else:
        e += P.rect_mask(h, w, 0, h * 0.43, w, h * 0.437)[..., None] * P.hexlin("#2a6a50")[None, None, :] * 0.10
        if variant == "dark_exit":
            e += P.rect_mask(h, w, w * 0.6, h * 0.47, w * 0.78, h * 0.5)[..., None] * P.hexlin("#20ff70")[None, None, :] * 1.6
        refl = (1 - v) * 0.5 + 0.5 * P.fbm(h, w, 3, int(rng.integers(1 << 30)), 3)
        c["base"] = c["base"] * (0.8 + 0.7 * refl[..., None])
    # mullion / transom shadow at the pane edges
    edge = P.smooth(u, 0.0, 0.05) * P.smooth(u, 1.0, 0.95) * P.smooth(v, 0.0, 0.03) * P.smooth(v, 1.0, 0.97)
    e *= (0.35 + 0.65 * edge)[..., None]
    c["emit"] = np.clip(e, 0, 8).astype(np.float32)
    return c


OFFICE_VARIANTS = ["open_cool", "dark", "open_warm", "dark_exit", "partial", "dark", "lounge_magenta", "server", "blinds", "dark",
                   "open_cool", "dark_exit", "partial", "dark", "open_warm", "dark"]

SIGN_SCHEMES = [  # (box colour, glyph colour, border colour) linear-ish via hex
    ("#f2efe6", "#c81e1e", "#c81e1e"), ("#ffd21f", "#151515", "#151515"), ("#1f3fb8", "#ffffff", "#ffffff"),
    ("#c4141a", "#ffe04a", "#ffe04a"), ("#0f8f4e", "#ffffff", "#e8ffe8"), ("#101010", "#ff2bd6", "#ff2bd6"),
    ("#101010", "#19e3ff", "#19e3ff"), ("#ffffff", "#1a1a1a", "#ff4f9a"), ("#ff6a00", "#ffffff", "#ffffff"),
    ("#2a1050", "#ffe14d", "#9b5cff"), ("#e8f6ff", "#0050c8", "#0050c8"), ("#101010", "#ffe14d", "#ff7a00"),
    ("#ff4f9a", "#ffffff", "#ffffff"), ("#063a3a", "#5dffd8", "#5dffd8"), ("#fafafa", "#008a3a", "#e01020"),
]


def sign_cell(h, w, scheme, seed):
    """Vertical lightbox sign: coloured box, border, 3-4 invented glyphs stacked, optional icon. Emissive."""
    rng = np.random.default_rng(seed)
    box, ink, bord = (P.hexlin(x) for x in SIGN_SCHEMES[scheme % len(SIGN_SCHEMES)])
    c = _empty(h, w)
    X, Y = P.grid(h, w)
    dark_box = float(np.max(box)) < 0.05
    pad = w * 0.08
    inner = P.rect_mask(h, w, pad, pad, w - pad, h - pad)
    border = P.rect_mask(h, w, pad * 0.45, pad * 0.45, w - pad * 0.45, h - pad * 0.45) - inner
    # lightbox diffuser: brighter in the centre, faint tube banding
    diff = 0.75 + 0.25 * np.exp(-(((X / w - 0.5) * 1.6) ** 2)) + 0.04 * np.sin(X / w * np.pi * 6)
    n = int(rng.integers(3, 5))
    gh = (h - 2 * pad) / n
    segs = []
    for k in range(n):
        segs += P.glyph_strokes(rng, pad * 2.0, pad * 1.4 + k * gh, w - pad * 4.0, gh * 0.72)
    glyph = P.seg_mask(h, w, segs, max(2.5, w * 0.075))
    if dark_box:  # neon-on-black: tubes glow, box is black metal
        emit = glyph[..., None] * ink[None, None, :] * 2.6 + P.blur(glyph, w * 0.04, False)[..., None] * ink[None, None, :] * 0.9
        emit += border[..., None] * bord[None, None, :] * 2.0
        base = np.full((h, w, 3), 0.02, np.float32) + glyph[..., None] * ink[None, None, :] * 0.4
    else:
        face = box[None, None, :] * diff[..., None]
        face = P.lerp(face, ink[None, None, :] * 0.6, glyph)
        emit = face * inner[..., None] * 1.6 + border[..., None] * bord[None, None, :] * 1.2
        base = face * 0.7
    frame = 1 - np.clip(inner + border, 0, 1)
    base = P.lerp(base, np.full(3, 0.03, np.float32), frame)
    c["base"] = base.astype(np.float32)
    c["emit"] = (emit * (1 - frame[..., None])).astype(np.float32)
    c["mask"][..., 0] = frame * 0.8
    c["mask"][..., 1] = 1.0
    c["mask"][..., 2] = 0.5 + glyph * 0.1
    c["mask"][..., 3] = 0.55 + frame * 0.1
    c["height"] = (border * 0.004 + glyph * 0.002 * (1 if dark_box else 0)).astype(np.float32)
    return c
