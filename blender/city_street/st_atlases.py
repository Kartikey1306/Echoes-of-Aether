"""Procedural texture atlases for the street kit (numpy only, no AI, invented glyphs only - no real words or brands):

  emit_st_signs     2048 atlas: shop fascia lightboxes (6 shop types x 2 colourways + dead), vertical blade signs,
                    square signs / menu boards / icons, noren cloths. Layout in st_layout.SIGN_RECTS.
  st_shutter        roll-shutter slats (1 m tile), st_awning_* canvas (1 m tile), st_tile_wall mosaic (1.2 m tile)

  python3 st_atlases.py [names...]
"""
import json
import math
import os
import random
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stpaths  # noqa: E402

sys.path.insert(1, stpaths.ENV)
sys.modules.setdefault("bpy", types.ModuleType("bpy"))
import numpy as np  # noqa: E402

import bakekit  # noqa: E402
import decaldefs as D  # noqa: E402
import pngio  # noqa: E402
import st_layout as L  # noqa: E402
import sttex as X  # noqa: E402
from sttex import F32, sst, lerp, mulc, lin, grey  # noqa: E402

STATE = os.path.join(stpaths.OUT, "materials_baked.json")

PAL = {
    "noodle": [("#ff3b2f", "#ffd9a0", "lightbox"), ("#ff8a2a", "#fff1d6", "neon")],
    "pharmacy": [("#19c46a", "#f2fff6", "lightbox"), ("#3dffa0", "#e8fff2", "neon")],
    "clinic": [("#00e5ff", "#dffbff", "neon"), ("#3d7bff", "#e6f0ff", "lightbox")],
    "pawn": [("#ffe14d", "#1a1406", "lightbox"), ("#ffb000", "#fff4c8", "neon")],
    "capsule": [("#7fb8ff", "#f4f8ff", "lightbox"), ("#9b5cff", "#efe6ff", "neon")],
    "arcade": [("#ff2bd6", "#ffe6fb", "neon"), ("#9b5cff", "#ffe14d", "lightbox")],
}


# ============================================================================================== drawing helpers
class Slot:
    """A drawing canvas for one atlas rect: metre-free, 1 unit = 1 px; arrays bottom row first."""

    def __init__(self, rect, seed):
        x, y, w, h = rect
        self.rect = rect
        self.c = D.Canvas((w, h), (w, h), seed)    # px == 1 'metre'
        self.col = np.zeros((h, w, 3), F32)        # albedo (linear)
        self.emi = np.zeros((h, w, 3), F32)        # emission (linear, 0..1)
        self.rng = random.Random(seed)
        self.w, self.h = w, h

    def mask_box(self, cx, cy, hw, hh, r=0.0, ang=0.0, soft=0.75):
        return D.cov(D.sd_box(self.c.x, self.c.y, cx, cy, hw, hh, ang, r), self.c, soft)

    def mask_circle(self, cx, cy, r, ring=0.0):
        d = np.hypot(self.c.x - cx, self.c.y - cy) - r
        if ring > 0:
            d = np.abs(d) - ring / 2
        return D.cov(d, self.c)

    def mask_seg(self, ax, ay, bx, by, w):
        return D.cov(D.sd_seg(self.c.x, self.c.y, ax, ay, bx, by) - w / 2, self.c)

    def glyphs(self, x0, y0, w, h, n, stroke=0.12, square=False):
        M = self.c.zeros()
        D.glyph_row(self.c, M, x0, y0, w, h, n, self.rng, stroke=stroke, gap=0.22, square=square)
        return M

    def paint(self, mask, colour, emit=0.0, emit_colour=None):
        colour = np.asarray(colour, F32)
        m = mask[..., None]
        self.col = self.col * (1 - m) + colour * m
        if emit > 0:
            ec = np.asarray(emit_colour if emit_colour is not None else colour, F32)
            self.emi = self.emi * (1 - m) + ec * emit * m
        else:
            self.emi = self.emi * (1 - m)

    def glow(self, mask, colour, radius, amount):
        """Additive soft halo (neon bloom baked into the emission around strokes)."""
        g = D.blur(mask, radius)
        self.emi = self.emi + np.asarray(colour, F32) * (g * amount)[..., None]


def icon(s, kind, cx, cy, r):
    """Shop pictogram mask (no text): bowl, cross, cyber-eye, three balls, capsule grid, joystick."""
    m = s.c.zeros()
    if kind == "noodle":
        bowl = s.mask_circle(cx, cy - r * 0.05, r * 0.72) * (s.c.y < cy - r * 0.05)
        m = np.maximum(m, bowl)
        m = np.maximum(m, s.mask_box(cx, cy - r * 0.08, r * 0.8, r * 0.05))
        m = np.maximum(m, s.mask_seg(cx - r * 0.2, cy + r * 0.05, cx + r * 0.75, cy + r * 0.8, r * 0.07))
        m = np.maximum(m, s.mask_seg(cx - r * 0.05, cy + r * 0.05, cx + r * 0.85, cy + r * 0.62, r * 0.07))
        for k in (-1, 0, 1):
            for t in range(6):
                y0 = cy + r * (0.15 + t * 0.12)
                xx = cx + k * r * 0.3 + math.sin(t * 1.4 + k) * r * 0.07
                xx2 = cx + k * r * 0.3 + math.sin((t + 1) * 1.4 + k) * r * 0.07
                m = np.maximum(m, s.mask_seg(xx, y0, xx2, y0 + r * 0.12, r * 0.05) * (0.9 if k else 1.0))
    elif kind == "pharmacy":
        m = np.maximum(s.mask_box(cx, cy, r * 0.62, r * 0.2, r * 0.04), s.mask_box(cx, cy, r * 0.2, r * 0.62, r * 0.04))
        m = np.maximum(m, s.mask_circle(cx, cy, r * 0.88, ring=r * 0.08))
    elif kind == "clinic":
        a = (np.hypot(s.c.x - cx, s.c.y - (cy - r * 0.55)) < r * 0.95) & (np.hypot(s.c.x - cx, s.c.y - (cy + r * 0.55)) < r * 0.95)
        eye = D.blur(a.astype(F32), 0.8)
        inner = (np.hypot(s.c.x - cx, s.c.y - (cy - r * 0.55)) < r * 0.85) & (np.hypot(s.c.x - cx, s.c.y - (cy + r * 0.55)) < r * 0.85)
        m = np.clip(eye - D.blur(inner.astype(F32), 0.8), 0, 1)
        m = np.maximum(m, s.mask_circle(cx, cy, r * 0.22))
        for k in (-1, 1):
            m = np.maximum(m, s.mask_seg(cx + k * r * 0.75, cy, cx + k * r * 0.95, cy, r * 0.06))
            m = np.maximum(m, s.mask_seg(cx + k * r * 0.95, cy, cx + k * r * 0.95, cy - r * 0.45, r * 0.06))
            m = np.maximum(m, s.mask_circle(cx + k * r * 0.95, cy - r * 0.5, r * 0.08))
    elif kind == "pawn":
        for ox, oy in ((-0.42, 0.35), (0.42, 0.35), (0.0, -0.38)):
            m = np.maximum(m, s.mask_circle(cx + ox * r, cy + oy * r, r * 0.3))
        m = np.maximum(m, s.mask_seg(cx - r * 0.42, cy + r * 0.65, cx + r * 0.42, cy + r * 0.65, r * 0.06))
    elif kind == "capsule":
        for i in range(3):
            for j in range(2):
                m = np.maximum(m, s.mask_box(cx + (i - 1) * r * 0.62, cy + (j - 0.5) * r * 0.6, r * 0.26, r * 0.2, r * 0.12))
        m = m - D.blur((m > 0.5).astype(F32), 0.5) * 0.0
    elif kind == "arcade":
        m = np.maximum(s.mask_circle(cx, cy + r * 0.45, r * 0.28), s.mask_box(cx, cy - r * 0.05, r * 0.06, r * 0.35))
        m = np.maximum(m, s.mask_box(cx, cy - r * 0.55, r * 0.75, r * 0.18, r * 0.05))
        m = np.maximum(m, s.mask_circle(cx + r * 0.55, cy - r * 0.2, r * 0.12))
        m = np.maximum(m, s.mask_circle(cx - r * 0.55, cy - r * 0.2, r * 0.12))
    return np.clip(m, 0, 1)


def fascia(rect, shop, k, seed):
    s = Slot(rect, seed)
    w, h = s.w, s.h
    main, light, style = PAL[shop][k]
    mc, lc = lin(main), lin(light)
    # housing: dark metal frame
    s.paint(np.ones((h, w), F32), grey(0.06))
    inner = s.mask_box(w / 2, h / 2, w / 2 - 5, h / 2 - 5, 3)
    vgrad = 0.8 + 0.2 * np.sin(np.clip(s.c.y / h, 0, 1) * math.pi)
    hgrad = 0.85 + 0.15 * np.sin(np.clip(s.c.x / w, 0, 1) * math.pi)
    if style == "lightbox":
        bg = mulc(np.broadcast_to(mc, (h, w, 3)), vgrad * hgrad)
        s.col = s.col * (1 - inner[..., None]) + bg * 0.8 * inner[..., None]
        s.emi = bg * 0.85 * inner[..., None]
        ink = lin("#0b0b0d") if shop == "pawn" else lc
        ink_emit = 0.0 if shop == "pawn" else 1.0
    else:
        s.col = s.col * (1 - inner[..., None]) + grey(0.05) * inner[..., None]
        border = np.clip(s.mask_box(w / 2, h / 2, w / 2 - 9, h / 2 - 9, 6) - s.mask_box(w / 2, h / 2, w / 2 - 13, h / 2 - 13, 4), 0, 1)
        s.paint(border, mc, 1.0)
        s.glow(border, mc, 4, 0.5)
        ink, ink_emit = mc, 1.0
    # icon on the left, glyph name, greeked tagline
    ic = icon(s, shop, h * 0.62, h * 0.5, h * 0.36)
    s.paint(ic, ink if style == "neon" else lc, 1.0 if (style == "neon" or shop != "pawn") else 0.0,
            ink if style == "neon" else lc)
    if style == "neon":
        s.glow(ic, mc, 5, 0.6)
    n = s.rng.randint(3, 5)
    gw = min(w * 0.62, n * h * 0.62)
    gx = h * 1.25
    gm = s.glyphs(gx, h * 0.24, gw, h * 0.56, n, stroke=0.13, square=(shop == "arcade"))
    s.paint(gm, ink, ink_emit, lc if style == "lightbox" else mc)
    if style == "neon":
        s.glow(gm, mc, 6, 0.55)
    tag = s.c.zeros()
    D.greek_lines(s.c, tag, gx + gw + h * 0.25, h * 0.32, w - (gx + gw + h * 0.25) - h * 0.35, h * 0.3, 2, s.rng, fill=0.9)
    s.paint(tag, ink, ink_emit * 0.7, lc if style == "lightbox" else mc)
    # grime on the housing and a dead tube band on some
    grime = sst(D.fbm(s.c, w * 0.3, 4) * 0.6 + (1 - s.c.y / h) * 0.8, 0.7, 1.6)
    s.col = mulc(s.col, 1 - grime * 0.35)
    s.emi = mulc(s.emi, 1 - grime * 0.25)
    if s.rng.random() < 0.4:
        x0 = s.rng.uniform(0.2, 0.8) * w
        dead = sst(np.abs(s.c.x - x0), w * 0.06, w * 0.03) * inner
        s.emi = mulc(s.emi, 1 - dead * 0.7)
    return s


def dead_fascia(rect, seed):
    s = Slot(rect, seed)
    w, h = s.w, s.h
    s.paint(np.ones((h, w), F32), grey(0.07))
    inner = s.mask_box(w / 2, h / 2, w / 2 - 5, h / 2 - 5, 3)
    s.paint(inner, lin("#3a3a3c"))
    n = s.rng.randint(3, 6)
    gm = s.glyphs(w * 0.18, h * 0.22, w * 0.55, h * 0.56, n, 0.12)
    s.paint(gm * 0.8, lin("#7a2a24"))
    grime = sst(D.fbm(s.c, w * 0.2, 5) + (1 - s.c.y / h) * 0.6, 0.0, 1.8)
    s.col = mulc(s.col, 1 - grime * 0.55)
    return s


def blade(rect, i, seed):
    s = Slot(rect, seed)
    w, h = s.w, s.h
    names = list(PAL)
    shop = names[i % len(names)]
    main, light, style = PAL[shop][(i // len(names)) % 2]
    mc, lc = lin(main), lin(light)
    s.paint(np.ones((h, w), F32), grey(0.05))
    inner = s.mask_box(w / 2, h / 2, w / 2 - 4, h / 2 - 4, 3)
    neon = (i % 3 == 0) or style == "neon"
    if not neon:
        s.paint(inner, mulc(mc, 0.85), 0.85, mc)
        ink, ie = lc, 1.0
    else:
        s.paint(inner, grey(0.04))
        bd = np.clip(s.mask_box(w / 2, h / 2, w / 2 - 8, h / 2 - 8, 5) - s.mask_box(w / 2, h / 2, w / 2 - 11, h / 2 - 11, 4), 0, 1)
        s.paint(bd, mc, 1.0)
        s.glow(bd, mc, 4, 0.45)
        ink, ie = mc, 1.0
    ic = icon(s, shop, w / 2, h - w * 0.62, w * 0.34)
    s.paint(ic, ink, ie)
    n = s.rng.randint(2, 3)
    gh = (h - w * 1.3) / n
    for k in range(n):
        gm = s.c.zeros()
        D.draw_glyph(s.c, gm, w * 0.18, h - w * 1.2 - (k + 1) * gh + gh * 0.1, w * 0.64, gh * 0.8, s.rng, stroke=0.13)
        s.paint(gm, ink, ie)
        if neon:
            s.glow(gm, mc, 5, 0.5)
    return s


def square(rect, i, seed):
    """Menu boards, single big glyph signs, price tags, open/closed lights."""
    s = Slot(rect, seed)
    w, h = s.w, s.h
    kind = i % 4
    cols = ["#ff4f9a", "#00e5ff", "#ffe14d", "#ff8a2a", "#3dffa0", "#9b5cff"]
    mc = lin(cols[i % len(cols)])
    if kind == 0:   # menu board: dark board, greeked rows, price chips, a "photo" block
        s.paint(np.ones((h, w), F32), grey(0.04))
        board = s.mask_box(w / 2, h / 2, w / 2 - 8, h / 2 - 8, 6)
        s.paint(board, lin("#1a1612"), 0.12, lin("#ffe0b0"))
        for r in range(3):
            ph = s.mask_box(w * 0.22, h * (0.78 - r * 0.28), w * 0.13, h * 0.1, 4)
            tone = lin(["#c86a2a", "#e0b060", "#8a3a1a"][r])
            s.paint(ph, mulc(tone, 0.9), 0.75, tone)
            tm = s.c.zeros()
            D.greek_lines(s.c, tm, w * 0.42, h * (0.72 - r * 0.28), w * 0.36, h * 0.12, 2, s.rng)
            s.paint(tm, lin("#f4ead8"), 0.8)
            chip = s.mask_box(w * 0.86, h * (0.78 - r * 0.28), w * 0.07, h * 0.05, 3)
            s.paint(chip, mc, 1.0)
    elif kind == 1:  # one big neon glyph in a circle
        s.paint(np.ones((h, w), F32), grey(0.04))
        ring = s.mask_circle(w / 2, h / 2, w * 0.42, ring=w * 0.04)
        gm = s.c.zeros()
        D.draw_glyph(s.c, gm, w * 0.27, h * 0.27, w * 0.46, h * 0.46, s.rng, stroke=0.14)
        m = np.maximum(ring, gm)
        s.paint(m, mc, 1.0)
        s.glow(m, mc, 6, 0.6)
    elif kind == 2:  # lightbox square with dark glyph pair
        s.paint(np.ones((h, w), F32), grey(0.06))
        inner = s.mask_box(w / 2, h / 2, w / 2 - 8, h / 2 - 8, 6)
        s.paint(inner, mulc(mc, 0.8), 0.8, mc)
        gm = s.glyphs(w * 0.14, h * 0.25, w * 0.72, h * 0.5, 2, 0.14)
        s.paint(gm, grey(0.05))
    else:            # "open" pill + glyph line (status light)
        s.paint(np.ones((h, w), F32), grey(0.05))
        pill = s.mask_box(w / 2, h * 0.58, w * 0.4, h * 0.18, h * 0.17)
        pill = np.clip(pill - s.mask_box(w / 2, h * 0.58, w * 0.37, h * 0.15, h * 0.14), 0, 1)
        gm = s.glyphs(w * 0.2, h * 0.47, w * 0.6, h * 0.22, 3, 0.15)
        m = np.maximum(pill, gm)
        s.paint(m, mc, 1.0)
        s.glow(m, mc, 6, 0.6)
        tm = s.c.zeros()
        D.greek_lines(s.c, tm, w * 0.15, h * 0.18, w * 0.7, h * 0.1, 1, s.rng)
        s.paint(tm, lin("#c8d0d8"), 0.5)
    return s


def cloth(rect, i, seed):
    """Noren / cloth banner: dyed cloth with a big white glyph pair, fold shading, wear (not lit)."""
    s = Slot(rect, seed)
    w, h = s.w, s.h
    base = lin(["#1c2a4a", "#7a1a1a", "#1d1d1f", "#5a2a6a"][i % 4])
    folds = 0.82 + 0.18 * np.cos(s.c.x / w * math.tau * 3.0) ** 2
    s.col = mulc(np.broadcast_to(base, (h, w, 3)).copy(), folds * (0.9 + D.fbm(s.c, w * 0.1, 3) * 0.04))
    gm = s.glyphs(w * 0.12, h * 0.18, w * 0.76, h * 0.6, 3, 0.16)
    s.paint(gm * 0.92, lin("#e8e2d6"))
    wear = sst(D.fbm(s.c, w * 0.05, 4), 1.2, 2.0)
    s.col = mulc(s.col, 1 - wear * 0.3)
    hem = s.mask_box(w / 2, h - 6, w / 2, 6)
    s.paint(hem, mulc(base, 0.6))
    return s


def build_signs():
    W, H = L.SIGNS_W, L.SIGNS_H
    col = np.zeros((H, W, 3), F32)
    emi = np.zeros((H, W, 3), F32)
    seed = 9100
    for name, rect in L.SIGN_RECTS.items():
        seed += 17
        if name.startswith("fascia_dead"):
            s = dead_fascia(rect, seed)
        elif name.startswith("fascia_"):
            _, shop, k = name.split("_")
            s = fascia(rect, shop, int(k), seed)
        elif name.startswith("blade_"):
            s = blade(rect, int(name.split("_")[1]), seed)
        elif name.startswith("square_"):
            s = square(rect, int(name.split("_")[1]), seed)
        else:
            s = cloth(rect, int(name.split("_")[1]), seed)
        x, y, w, h = rect
        col[y:y + h, x:x + w] = s.col
        emi[y:y + h, x:x + w] = s.emi
    emi = np.clip(emi, 0, 1)
    rough = np.full((H, W), 0.35, F32)
    mask = np.stack([np.zeros_like(rough), np.ones_like(rough), np.full_like(rough, 0.5), 1 - rough], -1)
    out = os.path.join(stpaths.TEXTURES, "emit_st_signs")
    files = bakekit.save_set(out, "emit_st_signs", color=np.clip(col, 0, 1), mask=mask, emission=emi)
    pngio.write_png(os.path.join(stpaths.PREVIEWS, "signs_atlas.png"), pngio.to_u8(pngio.linear_to_srgb(np.clip(col * 0.3 + emi, 0, 1)))[::-1])
    return {k: f"Textures/emit_st_signs/{v}" for k, v in files.items()}


# ============================================================================================== tiling shop materials
def shutter_maps(t):
    """Roll shutter: 76 mm horizontal slats (V), galvanised / painted steel, dents, rust from the slat lips, grime
    rising from the pavement (bottom of each 1 m tile is not special: the tile repeats vertically)."""
    pitch = 0.076
    fv = np.mod(t.v * t.tile / pitch, 1.0)
    prof = 0.5 - 0.5 * np.cos(fv * math.tau)
    lip = sst(fv, 0.9, 0.98) + sst(fv, 0.08, 0.02)
    dent = sst(t.noise(0.25, 3), 1.4, 2.2) * 0.6
    h = 0.5 + prof * 0.4 - lip * 0.35 - dent * 0.2 + t.noise(0.01, 2) * 0.02
    paint = lerp(grey(0.42), lin("#5b6670"), sst(t.noise(0.8, 3), -0.5, 0.5))
    col = mulc(np.broadcast_to(paint, t.shape + (3,)).copy(), 0.85 + prof * 0.1 + t.noise(0.05, 3) * 0.04)
    rust = sst(lip * 0.6 + t.noise(0.08, 4, 0.6) * 0.5 + dent * 0.5, 0.75, 1.3)
    streak = sst(t.noise(0.4, 4, 0.5, ax=0.08, ay=3.0), 0.8, 1.8)
    col = lerp(col, lin("#5a3420"), np.clip(rust * 0.75 + streak * 0.25, 0, 1))
    col = mulc(col, 1 - sst(t.noise(0.3, 4), 0.4, 1.6) * 0.3)
    rough = 0.55 + rust * 0.3 - prof * 0.05
    metal = np.clip(0.35 * (1 - rust), 0, 1)
    return col, rough, metal, h


def awning_maps(t, colour_a, colour_b=None, stripes=0):
    """Woven canvas awning: weave, stripes (U), rain streaks and tide marks, sun-faded crowns."""
    weave = 0.5 + 0.25 * np.sin(t.u * t.tile / 0.0016 * math.pi) * np.sin(t.v * t.tile / 0.0016 * math.pi)
    h = weave * 0.6 + t.noise(0.05, 3) * 0.05 + 0.2
    a, b = lin(colour_a), lin(colour_b or colour_a)
    if stripes:
        st = (np.mod(t.u * stripes, 1.0) < 0.5).astype(F32)
        st = D.blur(st, 0.7) if False else st
        base = lerp(np.broadcast_to(a, t.shape + (3,)), np.broadcast_to(b, t.shape + (3,)), st)
    else:
        base = np.broadcast_to(a, t.shape + (3,)).copy()
    col = mulc(base, 0.85 + weave * 0.15 + t.noise(0.4, 3) * 0.05)
    streak = sst(t.noise(0.3, 4, 0.5, ax=0.06, ay=4.0), 0.4, 1.6)
    tide = sst(np.abs(t.noise(0.6, 3)), 0.04, 0.0) * 0.6
    col = mulc(col, 1 - streak * 0.35 - tide * 0.2)
    rough = 0.82 - streak * 0.25
    return col, rough, np.zeros_like(rough), h


def tile_wall_maps(t):
    """25 mm glazed mosaic tiles (shopfront pilasters / bulkheads): random tone mix, dirty grout, chips."""
    N = int(round(t.tile / 0.025))
    gu, gv = t.u * N, t.v * N
    iu, iv = np.floor(gu).astype(np.int64), np.floor(gv).astype(np.int64)
    fu, fv = gu - iu, gv - iv
    cid = (iv % N) * N + (iu % N)
    r1 = t.cell_rand(cid, seed=61)
    r2 = t.cell_rand(cid, seed=62)
    de = np.minimum(np.minimum(fu, 1 - fu), np.minimum(fv, 1 - fv)) * 0.025
    face = sst(de, 0.0012, 0.0025)
    tones = [lin("#c9ccc8"), lin("#9aa3a3"), lin("#6f8486"), lin("#d8d4cc")]
    col = np.zeros(t.shape + (3,), F32)
    for k, tc in enumerate(tones):
        sel = ((r1 * len(tones)).astype(int) == k).astype(F32)
        col += sel[..., None] * tc
    col = mulc(col, 0.88 + r2 * 0.18)
    grout = lin("#3a3a36")
    col = lerp(grout, col, face)
    dirt = sst(t.noise(0.3, 4, 0.6), 0.2, 1.8)
    col = mulc(col, 1 - dirt * 0.45)
    chip = sst(t.white(), 0.997, 1.0)
    h = face * 0.7 + 0.2 - chip * 0.3
    rough = lerp(0.85, 0.12 + dirt * 0.3, face)
    return col, rough, np.zeros_like(rough), h


TILED = {
    "st_shutter": (1.0, 0.004, lambda t: shutter_maps(t)),
    "st_awning_red": (1.0, 0.001, lambda t: awning_maps(t, "#8a1c18")),
    "st_awning_teal": (1.0, 0.001, lambda t: awning_maps(t, "#145a60")),
    "st_awning_stripe": (1.0, 0.001, lambda t: awning_maps(t, "#d8d2c6", "#a3221c", stripes=4)),
    "st_tile_wall": (1.2, 0.002, lambda t: tile_wall_maps(t)),
}


def build_tiled(name):
    tile, depth, fn = TILED[name]
    t = X.Tex(1024, tile, seed=sum(map(ord, name)) * 7)
    col, rough, metal, h = fn(t)
    hm = np.clip(h, 0, 1) * depth
    nrm = bakekit.height_to_normal(hm.astype(np.float64), t.px, 1.0).astype(F32)
    ao = X.cavity_ao(t, hm.astype(F32))
    mask = np.stack([np.clip(metal, 0, 1), ao, np.clip(h, 0, 1), 1 - np.clip(rough, 0, 1)], -1)
    files = bakekit.save_set(os.path.join(stpaths.TEXTURES, name), name, color=np.clip(col, 0, 1), normal=nrm, mask=mask)
    tex = {k: f"Textures/{name}/{v}" for k, v in files.items()}
    tex["Occlusion"] = tex["MaskMap"]
    return tex


def main():
    names = sys.argv[1:] or ["emit_st_signs"] + list(TILED)
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    for n in names:
        if n == "emit_st_signs":
            tex = build_signs()
            state[n] = {"name": n, "textures": tex, "res": L.SIGNS_W}
        else:
            state[n] = {"name": n, "textures": build_tiled(n), "res": 1024}
        print("[atlas]", n)
        json.dump(state, open(STATE, "w"), indent=1)


if __name__ == "__main__":
    main()
