"""Street-kit URP decals (numpy only; invented glyphs only - no real words, tags, brands or logos):
graffiti tags / throw-ups / stencils, sticker slaps, bill posters, asphalt utility patches, tyre skids, pavement
stains and tactile paving. Uses the environment kit's decal maths (blender/env/decaldefs.py) and finaliser.

  python3 st_decals.py [Name or glob ...]

Writes Assets/Art/CityStreet/Decals/<Name>/<Name>_{BaseColor,Normal,MaskMap}.png and out/decals.json.
"""
import fnmatch
import json
import math
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stpaths  # noqa: E402

sys.path.insert(1, stpaths.ENV)
sys.modules.setdefault("bpy", types.ModuleType("bpy"))
import envpaths  # noqa: E402

envpaths.UNITY_ENV = stpaths.UNITY_ST
envpaths.STATE = stpaths.OUT
import numpy as np  # noqa: E402

import build_decals as BD  # noqa: E402  (finalize / fill_under)
import decaldefs as D  # noqa: E402
import pngio  # noqa: E402
from decaldefs import F32, L, N, Canvas, Stack, blur, cov, fbm, n01, sst, mixc, mulc, rot, sd_box, sd_seg, speckle, warp  # noqa: E402

STATE = os.path.join(stpaths.OUT, "decals.json")
DEC = {}


def reg(name, fn, size, px, projection, use, tags, normal_blend=0.8, order=0, depth=0.3, **params):
    DEC[name] = {"fn": fn, "size": size, "px": px, "projection": projection, "use": use, "tags": tags, "normalBlend": normal_blend,
                 "drawOrder": order, "projectionDepth": depth, "seed": sum(ord(ch) * (i + 3) for i, ch in enumerate(name)), "params": params}


PALETTES = [("#ff2bd6", "#00e5ff"), ("#ffe14d", "#ff2bd6"), ("#00e5ff", "#9b5cff"), ("#3dff90", "#ff4f9a"),
            ("#ff8a2a", "#e8e8f0"), ("#e8e8f0", "#ff2bd6")]


def _glyph_mask(c, x0, y0, w, h, n, stroke, slant, rng, jitter=0.12):
    """Hand-styled row of invented glyphs: per glyph size / baseline jitter and a common slant."""
    M = c.zeros()
    cw = w / n
    for i in range(n):
        gw = cw * rng.uniform(0.8, 1.05)
        gh = h * rng.uniform(0.75, 1.1)
        gx = x0 + i * cw + rng.uniform(-0.04, 0.04) * cw
        gy = y0 + rng.uniform(-jitter, jitter) * h
        D.draw_glyph(c, M, gx, gy, gw, gh, rng, stroke=stroke, ang=slant + rng.uniform(-0.12, 0.12))
    return M


def _dilate(M, r_px):
    return np.clip(blur(M, r_px) * 3.0, 0, 1)


def graffiti_tag(c, p):
    """Quick hand tag: a slanted string of invented glyphs, thin marker-like spray line, outline halo, drips, an
    underline swoosh, aged over the wall."""
    rng = c.r
    st = Stack(c)
    W, H = c.wm, c.hm
    a, b = PALETTES[p.get("pal", 0)]
    n = rng.randint(3, 5)
    M = _glyph_mask(c, W * 0.1, H * 0.3, W * 0.8, H * 0.5, n, 0.11, math.radians(rng.uniform(4, 12)), rng)
    sw = c.full(0.02)
    P = D.frac_path(rng, (W * 0.12, H * 0.22), (W * 0.9, H * 0.3), 0.04, 5)
    D.draw_path(c, sw, P, D.width_profile(rng, P, 0.012, 0.05, 0.5, 0.3), 0.02)
    M = np.maximum(M, cov(sw, c, 0.8))
    out = np.clip(_dilate(M, 3.0) - M, 0, 1)
    D.spray(c, st, out, L(b) * 0.9, sm=0.35, halo=0.4, drips=3, wear=0.25)
    D.spray(c, st, M, L(a), sm=0.4, halo=0.8, drips=10, wear=0.3)
    st.ao_strength = 0.0
    return st


def graffiti_throwup(c, p):
    """Bubble throw-up: fat rounded invented glyphs, two-tone fill with a fade, thick dark outline, white highlights
    and a colour shadow; peeling where the wall is rough."""
    rng = c.r
    st = Stack(c)
    W, H = c.wm, c.hm
    a, b = PALETTES[p.get("pal", 1)]
    n = rng.randint(2, 3)
    core = _glyph_mask(c, W * 0.1, H * 0.22, W * 0.8, H * 0.58, n, 0.26, math.radians(rng.uniform(-4, 6)), rng, 0.06)
    fill = _dilate(core, 6.0)
    outline = np.clip(_dilate(fill, 5.0) - fill * 0.0, 0, 1)
    shadow = np.roll(np.roll(outline, -10, axis=0), 12, axis=1)
    D.spray(c, st, np.clip(shadow - outline, 0, 1), L(b) * 0.7, sm=0.3, halo=0.3, drips=2, wear=0.35)
    D.spray(c, st, outline, L("#0b0b10"), sm=0.35, halo=0.5, drips=4, wear=0.3)
    grad = np.clip((c.y - H * 0.2) / (H * 0.6), 0, 1)[..., None]
    col = L(a) * (1 - grad) + L(b) * grad
    paint = D.spray(c, st, fill, L(a), sm=0.4, halo=0.2, drips=6, wear=0.3)
    st.tint(fill * 0.85, col=None)
    st.C = st.C * (1 - (fill * 0.75)[..., None]) + (col * st.A[..., None]) * (fill * 0.75)[..., None]
    hl = np.clip(fill - np.roll(_dilate(fill, 1.0), -4, axis=0), 0, 1) * sst(D.fbm(c, 0.05, 3), 0.0, 0.8)
    D.spray(c, st, hl * 0.9, L("#f4f4f8"), sm=0.5, halo=0.0, drips=0, wear=0.0)
    st.ao_strength = 0.0
    return st


def graffiti_stencil(c, p):
    """Spray stencil: a staring cyber-eye pictogram and a row of bridged glyphs, overspray and runs."""
    rng = c.r
    st = Stack(c)
    W, H = c.wm, c.hm
    cx, cy, r = W * 0.5, H * 0.62, min(W, H) * 0.24
    up = np.hypot(c.x - cx, c.y - (cy - r * 0.6)) < r * 1.1
    dn = np.hypot(c.x - cx, c.y - (cy + r * 0.6)) < r * 1.1
    eye = (up & dn).astype(F32)
    inner = ((np.hypot(c.x - cx, c.y - (cy - r * 0.6)) < r * 0.95) & (np.hypot(c.x - cx, c.y - (cy + r * 0.6)) < r * 0.95)).astype(F32)
    pupil = (np.hypot(c.x - cx, c.y - cy) < r * 0.32).astype(F32)
    M = np.clip(eye - inner + pupil, 0, 1)
    for k in range(5):
        ang = math.radians(60 + k * 15)
        M = np.maximum(M, cov(sd_seg(c.x, c.y, cx + math.cos(ang) * r * 1.15, cy + math.sin(ang) * r * 0.75,
                                     cx + math.cos(ang) * r * 1.45, cy + math.sin(ang) * r * 1.0) - r * 0.04, c))
    G = c.zeros()
    D.glyph_row(c, G, W * 0.15, H * 0.12, W * 0.7, H * 0.18, 4, rng, stroke=0.13, bridges=True)
    M = np.maximum(blur(M, 0.6), G)
    D.spray(c, st, M, L(PALETTES[p.get("pal", 2)][0]), sm=0.35, halo=1.0, drips=8, wear=0.35)
    st.ao_strength = 0.0
    return st


def stickers(c, p):
    """Sticker slap cluster: overlapping printed stickers (rect / round / pill) with icons and glyphs, scuffed and torn."""
    rng = c.r
    st = Stack(c)
    W, H = c.wm, c.hm
    for k in range(rng.randint(9, 14)):
        cx, cy = rng.uniform(0.15, 0.85) * W, rng.uniform(0.15, 0.85) * H
        w, h = rng.uniform(0.06, 0.16), rng.uniform(0.04, 0.12)
        ang = math.radians(rng.uniform(-25, 25))
        shape = rng.random()
        sd = sd_box(c.x, c.y, cx, cy, w / 2, h / 2, ang, min(w, h) * (0.5 if shape < 0.3 else 0.08))
        if shape > 0.8:
            sd = np.hypot(c.x - cx, c.y - cy) - min(w, h) / 2
        tear = sst(D.fbm(c, 0.03, 3) + rng.uniform(-0.5, 1.2), 1.3, 1.5)
        m = cov(sd, c) * (1 - tear)
        bg = L(rng.choice(["#f2f0ea", "#141418", "#ffe14d", "#ff2bd6", "#00e5ff", "#3dff90", "#ff4f9a", "#e8e8f0"]))
        st.add(m, mulc(np.broadcast_to(bg, (c.H, c.W, 3)).copy(), 0.85 + 0.15 * n01(D.fbm(c, 0.02, 2))), sm=0.55, h=m * 0.0002)
        g = c.zeros()
        D.glyph_row(c, g, cx - w * 0.35, cy - h * 0.25, w * 0.7, h * 0.5, rng.randint(1, 3), rng, stroke=0.15, ang=ang)
        ink = L("#0b0b0b") if bg.mean() > 0.3 else L(rng.choice(["#ff2bd6", "#00e5ff", "#ffe14d"]))
        st.add(g * m, ink, sm=0.5)
    grime = sst(D.fbm(c, 0.2, 4), 0.2, 1.6) * st.A
    st.tint(grime, mul=L("#6a6258"))
    st.ao_strength = 0.0
    return st


def asphalt_patch(c, p):
    """Utility-cut patch: a rectangle of newer, darker asphalt with sealed (tar) seams, slightly sunk, cracked edge."""
    rng = c.r
    st = Stack(c)
    W, H = c.wm, c.hm
    hw, hh = W * 0.42, H * 0.38
    jag = D.fbm(c, 0.06, 3) * 0.012
    sd = sd_box(c.x, c.y, W / 2, H / 2, hw, hh, math.radians(rng.uniform(-1.5, 1.5)), 0.03) + jag
    inside = cov(sd, c, 1.5)
    agg = D.speckle(c, 0.035, 1.1)
    col = mulc(np.broadcast_to(L("#202022"), (c.H, c.W, 3)).copy(), 0.85 + agg * 0.5 + n01(D.fbm(c, 0.4, 3)) * 0.15)
    st.add(inside * 0.96, col, sm=0.3, h=-inside * 0.003)
    seam = sst(np.abs(sd), 0.03, 0.012) * sst(D.fbm(c, 0.3, 3), -1.2, -0.4)
    st.add(seam * 0.95, L("#0a0a0b"), sm=0.75, h=seam * 0.001)
    cr = c.full(0.02)
    for _ in range(3):
        x0 = rng.uniform(0.2, 0.8) * W
        P = D.frac_path(rng, (x0, H / 2 + hh), (x0 + rng.uniform(-0.3, 0.3), H / 2 + hh + rng.uniform(0.05, 0.2)), 0.2, 5)
        D.draw_path(c, cr, P, D.width_profile(rng, P, 0.003), 0.02)
    crm = cov(cr, c)
    st.add(crm * 0.8, L("#060606"), sm=0.4, h=-crm * 0.004)
    st.ao_strength = 0.6
    return st


def skid_marks(c, p):
    """Two tyre skid streaks (rubber deposit with tread banding), gently curving, fading at both ends."""
    rng = c.r
    st = Stack(c)
    W, H = c.wm, c.hm
    for lane in (0.32, 0.68):
        y0 = H * lane + rng.uniform(-0.03, 0.03)
        bend = rng.uniform(-0.12, 0.12)
        yy = y0 + bend * ((c.x / W) - 0.5) ** 2 * 4
        d = np.abs(c.y - yy)
        band = sst(d, 0.11, 0.07)
        tread = 0.65 + 0.35 * np.sin(c.y / 0.012) ** 2
        fade = sst(c.x, 0.0, W * 0.25) * sst(c.x, W, W * 0.7) * n01(D.fbm(c, 0.4, 3, ax=6.0, ay=0.4), -1.6, 1.0)
        st.add(band * tread * fade * 0.85, L("#0d0d0e"), sm=0.42)
    st.ao_strength = 0.0
    return st


def pavement_stains(c, p):
    """Pavement stains: flattened gum, a coffee splash, a drip trail and a rust ring from a removed sign post."""
    rng = c.r
    st = Stack(c)
    W, H = c.wm, c.hm
    for _ in range(rng.randint(16, 26)):
        x, y = rng.uniform(0.05, 0.95) * W, rng.uniform(0.05, 0.95) * H
        r = rng.uniform(0.008, 0.02)
        m = cov(np.hypot(c.x - x, c.y - y) - r + D.fbm(c, 0.01, 2) * 0.002, c)
        st.add(m * 0.9, L(rng.choice(["#3e3b37", "#2f2d2a", "#4a4640"])), sm=0.35, h=m * 0.0006)
    x, y = W * rng.uniform(0.3, 0.7), H * rng.uniform(0.3, 0.7)
    rr = np.hypot(c.x - x, c.y - y)
    splash = sst(rr + D.fbm(c, 0.05, 3) * 0.03, 0.14, 0.09) + D.speckle(c, 0.003, 1.3) * np.exp(-rr / 0.25)
    st.add(np.clip(splash, 0, 1) * 0.55, L("#3a2616"), sm=0.3)
    ring = sst(np.abs(np.hypot(c.x - W * 0.2, c.y - H * 0.75) - 0.05), 0.012, 0.004)
    st.add(ring * 0.7, L("#5a3218"), sm=0.25)
    st.ao_strength = 0.0
    return st


def tactile_strip(c, p):
    """Yellow tactile warning paving (truncated domes on a 50 mm grid) laid at crossings, scuffed and dirty."""
    st = Stack(c)
    W, H = c.wm, c.hm
    inside = cov(sd_box(c.x, c.y, W / 2, H / 2, W / 2 - 0.02, H / 2 - 0.02, 0, 0.005), c)
    pitch = 0.05
    gx = np.mod(c.x, pitch) - pitch / 2
    gy = np.mod(c.y, pitch) - pitch / 2
    dome = np.clip(1 - np.hypot(gx, gy) / 0.0125, 0, 1) ** 0.6
    wear = n01(D.fbm(c, 0.3, 3), -1.0, 2.0)
    col = mixc(np.broadcast_to(L("#c9a21a"), (c.H, c.W, 3)).copy(), L("#6e5a1c"), wear * 0.6)
    col = mixc(col, L("#e0bd3a"), dome[..., None][..., 0] * 0.3 * (1 - wear))
    st.add(inside, col, sm=0.35, h=dome * 0.004 * inside)
    joints = np.minimum(np.mod(c.x, 0.6), 0.6 - np.mod(c.x, 0.6))
    st.tint(sst(joints, 0.004, 0.0) * inside, mul=L("#3a3020"))
    st.ao_strength = 0.6
    return st


def poster_wall2(c, p):
    return D.poster_wall(c, p)


# ---------------------------------------------------------------------------------------------- registry
for i, pal in enumerate((0, 2, 3, 4)):
    reg(f"St_Graffiti_Tag_{chr(65 + i)}", graffiti_tag, (1.6, 0.8), (1024, 512), "wall",
        "Hand tag of invented glyphs with an underline swoosh, outline halo and drips. Shutters, walls, boxes.",
        ["wall", "graffiti", "tag", "glyph"], 0.3, 3, 0.3, pal=pal)
for i, pal in enumerate((1, 5)):
    reg(f"St_Graffiti_Throwup_{chr(65 + i)}", graffiti_throwup, (2.2, 1.1), (1024, 512), "wall",
        "Bubble throw-up (fat invented glyphs, two-tone fade fill, dark outline, highlights, colour shadow). Shutters, walls.",
        ["wall", "graffiti", "throwup", "glyph", "shutter"], 0.3, 3, 0.3, pal=pal)
reg("St_Graffiti_Stencil_A", graffiti_stencil, (1.0, 1.0), (768, 768), "wall",
    "Spray stencil: cyber-eye pictogram over a bridged glyph row.", ["wall", "graffiti", "stencil", "glyph"], 0.3, 3, 0.3, pal=2)
reg("St_Stickers_A", stickers, (0.6, 0.6), (512, 512), "wall", "Sticker slap cluster (invented glyphs / icons), torn and grimy.",
    ["wall", "sticker", "glyph", "pole"], 0.4, 4, 0.25)
reg("St_Stickers_B", stickers, (0.6, 0.6), (512, 512), "wall", "Sticker slap cluster B.", ["wall", "sticker", "glyph", "pole"], 0.4, 4, 0.25)
reg("St_Posters_D", poster_wall2, (1.6, 1.6), (1024, 1024), "wall", "Layered torn bill posters (invented glyphs).",
    ["wall", "poster", "flyer", "glyph"], 0.8, 4, 0.3, variant="b")
reg("St_Posters_E", poster_wall2, (1.6, 1.6), (1024, 1024), "wall", "Layered torn bill posters, dense (invented glyphs).",
    ["wall", "poster", "flyer", "glyph"], 0.8, 4, 0.3, variant="c")
reg("St_Asphalt_Patch_A", asphalt_patch, (3.0, 1.6), (1024, 544), "floor", "Utility-cut asphalt patch with tar-sealed seams (road).",
    ["road", "patch", "street"], 0.9, 1, 0.3)
reg("St_Asphalt_Patch_B", asphalt_patch, (2.0, 2.0), (768, 768), "floor", "Square utility-cut patch (road).", ["road", "patch", "street"], 0.9, 1, 0.3)
reg("St_Skid_Marks", skid_marks, (4.0, 1.4), (1024, 358), "floor", "Tyre skid streaks (road).", ["road", "skid", "street"], 0.2, 2, 0.3)
reg("St_Pavement_Stains", pavement_stains, (1.6, 1.6), (768, 768), "floor", "Gum, coffee splash, rust ring (pavement).",
    ["sidewalk", "stain", "street"], 0.5, 1, 0.25)
reg("St_Tactile_Strip", tactile_strip, (2.4, 0.6), (1024, 256), "floor", "Yellow tactile warning paving at a kerb crossing (domes).",
    ["sidewalk", "tactile", "crossing"], 1.0, 2, 0.25)


def entry(name, files):
    d = DEC[name]
    return {"name": name, "sizeMeters": list(d["size"]), "textures": files, "resolution": max(d["px"]), "pixels": list(d["px"]),
            "projection": d["projection"], "use": d["use"],
            "urp": {"shader": D.URP_SHADER, "affectsBaseColor": True, "affectsNormal": True, "affectsMAOS": True,
                    "normalBlend": d["normalBlend"], "drawOrder": d["drawOrder"], "projectionDepth": d["projectionDepth"]},
            "tags": d["tags"], "orientation": "+U = decal right, +V = decal up (walls: world up; floors: forward). Pivot centre."}


def main():
    pats = [a for a in sys.argv[1:] if not a.startswith("--")]
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    for name, d in DEC.items():
        if pats and not any(fnmatch.fnmatch(name, p) for p in pats):
            continue
        c = Canvas(d["size"], d["px"], d["seed"])
        st = d["fn"](c, d["params"])
        m = BD.finalize(c, st)
        out = os.path.join(stpaths.DECALS, name)
        os.makedirs(out, exist_ok=True)
        bc = np.concatenate([pngio.to_u8(pngio.linear_to_srgb(m["col"])), pngio.to_u8(m["a"])[..., None]], axis=-1)
        files = {}
        for suf, arr in (("BaseColor", bc), ("Normal", pngio.to_u8(m["nrm"])), ("MaskMap", pngio.to_u8(m["mask"]))):
            pngio.write_png(os.path.join(out, f"{name}_{suf}.png"), arr[::-1], level=9)
            files[suf] = f"Decals/{name}/{name}_{suf}.png"
        state[name] = entry(name, files)
        print(f"[decal] {name:24s} {c.W}x{c.H} alpha mean {m['a'].mean():.3f}")
        json.dump(state, open(STATE, "w"), indent=1)
    # preview sheet: colour over a mid-grey ground
    tiles = []
    for name in DEC:
        p = os.path.join(stpaths.DECALS, name, f"{name}_BaseColor.png")
        if os.path.exists(p):
            tiles.append(p)
    try:
        from PIL import Image
        S = Image.new("RGB", (4 * 320, ((len(tiles) + 3) // 4) * 200), (40, 40, 44))
        for i, p in enumerate(tiles):
            im = Image.open(p).convert("RGBA")
            im.thumbnail((310, 190))
            bgc = Image.new("RGBA", im.size, (70, 70, 74, 255))
            bgc.alpha_composite(im)
            S.paste(bgc.convert("RGB"), ((i % 4) * 320 + 5, (i // 4) * 200 + 5))
        S.save(os.path.join(stpaths.PREVIEWS, "decals_sheet.png"))
    except Exception as e:  # noqa: BLE001
        print("[decal] sheet failed", e)


if __name__ == "__main__":
    main()
