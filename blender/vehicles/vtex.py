"""Procedural, seamlessly tileable texture generators for the vehicle kit (pure numpy).

Every generator works on an N x N torus (FFT-filtered noise, wrap-around distances) so the maps tile.
Arrays are float32, row 0 = TOP of the image (PNG order).  Texture space: u -> columns (right), v -> rows UP.
"""
import math

import numpy as np


# ------------------------------------------------------------------------------------------------ noise
def _freq(n):
    fy = np.fft.fftfreq(n).astype(np.float32)[:, None]
    fx = np.fft.rfftfreq(n).astype(np.float32)[None, :]
    return fx, fy


def band_noise(n, scale_px, seed, aniso=(1.0, 1.0)):
    """Gaussian-filtered white noise, features ~scale_px pixels, zero mean / unit std, tileable."""
    rng = np.random.default_rng(seed)
    w = rng.standard_normal((n, n)).astype(np.float32)
    F = np.fft.rfft2(w)
    fx, fy = _freq(n)
    g = np.exp(-((fx * scale_px * aniso[0]) ** 2 + (fy * scale_px * aniso[1]) ** 2) * 2.0)
    out = np.fft.irfft2(F * g, s=(n, n)).astype(np.float32)
    out -= out.mean()
    s = out.std()
    return out / (s if s > 1e-8 else 1.0)


def fbm(n, scale_px, seed, octaves=5, gain=0.5, lacunarity=2.0, aniso=(1.0, 1.0)):
    out = np.zeros((n, n), np.float32)
    amp, sc, tot = 1.0, float(scale_px), 0.0
    for o in range(octaves):
        if sc < 0.6:
            break
        out += amp * band_noise(n, sc, seed + 101 * o, aniso)
        tot += amp
        amp *= gain
        sc /= lacunarity
    return out / max(tot, 1e-6)


def remap01(x, lo=None, hi=None):
    lo = x.min() if lo is None else lo
    hi = x.max() if hi is None else hi
    return np.clip((x - lo) / max(hi - lo, 1e-8), 0.0, 1.0)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def blur(x, sigma_px):
    """Periodic gaussian blur via FFT."""
    if sigma_px <= 0:
        return x
    n = x.shape[0]
    fx, fy = _freq(n)
    g = np.exp(-2.0 * (math.pi ** 2) * (sigma_px ** 2) * (fx ** 2 + fy ** 2))
    if x.ndim == 2:
        return np.fft.irfft2(np.fft.rfft2(x) * g, s=x.shape).astype(np.float32)
    return np.stack([blur(x[..., c], sigma_px) for c in range(x.shape[2])], -1)


def blur_u(x, sigma_px):
    """Blur along u (columns) only -> brushed streaks."""
    n = x.shape[1]
    f = np.fft.rfftfreq(n).astype(np.float32)[None, :]
    g = np.exp(-2.0 * (math.pi ** 2) * (sigma_px ** 2) * f ** 2)
    return np.fft.irfft(np.fft.rfft(x, axis=1) * g, n=n, axis=1).astype(np.float32)


def grid_uv(n):
    """u, v in [0,1) for each pixel (v up)."""
    c = (np.arange(n, dtype=np.float32) + 0.5) / n
    u = np.broadcast_to(c[None, :], (n, n))
    v = np.broadcast_to(c[::-1][:, None], (n, n))
    return u, v


def voronoi(n, count, seed, jitter=1.0):
    """Tileable F1, F2 distances (in pixels) and cell id for `count` random sites."""
    rng = np.random.default_rng(seed)
    pts = rng.random((count, 2)).astype(np.float32) * n
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    f1 = np.full((n, n), 1e9, np.float32)
    f2 = np.full((n, n), 1e9, np.float32)
    cid = np.zeros((n, n), np.int32)
    for i, (px, py) in enumerate(pts):
        dx = np.abs(xx - px)
        dx = np.minimum(dx, n - dx)
        dy = np.abs(yy - py)
        dy = np.minimum(dy, n - dy)
        d = np.sqrt(dx * dx + dy * dy)
        closer = d < f1
        f2 = np.where(closer, f1, np.minimum(f2, d))
        cid = np.where(closer, i, cid)
        f1 = np.where(closer, d, f1)
    return f1, f2, cid


# ------------------------------------------------------------------------------------------------ maps
def normal_from_height(h, texel_m, depth_m=1.0, strength=1.0):
    """h in [0,1] scaled by depth_m metres; OpenGL tangent normal (+Y = v up). Returns float RGB in 0..1."""
    hh = h * depth_m
    dhdu = (np.roll(hh, -1, 1) - np.roll(hh, 1, 1)) / (2 * texel_m)
    dhdv = (np.roll(hh, 1, 0) - np.roll(hh, -1, 0)) / (2 * texel_m)  # row-1 is "up"
    nx = -dhdu * strength
    ny = -dhdv * strength
    nz = np.ones_like(nx)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / ln, ny / ln, nz / ln], -1) * 0.5 + 0.5


def normal_from_tilt(tx, ty):
    nz = np.sqrt(np.clip(1.0 - tx * tx - ty * ty, 0.05, 1.0))
    return np.stack([tx, ty, nz], -1) * 0.5 + 0.5


def combine_normals(a, b):
    """Whiteout blend of two encoded normal maps."""
    na = a * 2 - 1
    nb = b * 2 - 1
    n = np.stack([na[..., 0] + nb[..., 0], na[..., 1] + nb[..., 1], na[..., 2] * nb[..., 2]], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def cavity_ao(h, radius_px=6, strength=1.0):
    """Cheap tileable AO from height: darker where below the local blurred mean."""
    d = blur(h, radius_px) - h
    return np.clip(1.0 - np.clip(d, 0, None) * strength, 0.0, 1.0)


def mask_map(metal, ao, smooth, b=None):
    n = metal.shape[0]
    b = np.zeros((n, n), np.float32) if b is None else b
    return np.stack([metal, ao, b, smooth], -1)


def flat(n, rgb):
    return np.broadcast_to(np.asarray(rgb, np.float32)[None, None, :], (n, n, len(rgb))).copy()


# ------------------------------------------------------------------------------------------------ glyphs
# Invented script: each glyph = 2..4 strokes on a 3 x 5 node lattice (never a real-world letter on purpose:
# strokes are picked at random from a fixed seed, then filtered so a glyph is not a single straight bar).
_NODES = [(x, y) for y in range(5) for x in range(3)]


def make_glyph(seed):
    rng = np.random.default_rng(seed)
    strokes = []
    k = int(rng.integers(3, 5))
    for _ in range(k):
        a = _NODES[int(rng.integers(len(_NODES)))]
        dx, dy = [(1, 0), (0, 1), (1, 1), (1, -1), (2, 0), (0, 2), (2, 2), (0, 4), (2, 4)][int(rng.integers(9))]
        b = (min(2, a[0] + dx), max(0, min(4, a[1] + dy)))
        if a != b:
            strokes.append((a, b))
    if len(strokes) < 2:
        strokes.append(((0, 0), (2, 0)))
    if not any(s[0][1] == s[1][1] for s in strokes):  # every glyph gets a horizontal "bar" (script style)
        y = int(rng.integers(0, 5))
        strokes.append(((0, y), (2, y)))
    return strokes


def draw_glyphs(img, glyphs, x0, y0, gh, spacing=1.25, width_frac=0.13, value=1.0, slant=0.0):
    """Rasterise glyph stroke lists into float image `img` (H,W) starting at pixel (x0,y0 top-left)."""
    gw = gh * 0.6
    lw = gh * width_frac
    H, W = img.shape
    x = x0
    for g in glyphs:
        if g is None:
            x += gw * spacing
            continue
        xa, xb = int(max(0, x - lw * 2)), int(min(W, x + gw + lw * 2 + abs(slant) * gh))
        ya, yb = int(max(0, y0 - lw * 2)), int(min(H, y0 + gh + lw * 2))
        if xb <= xa or yb <= ya:
            x += gw * spacing
            continue
        yy, xx = np.mgrid[ya:yb, xa:xb].astype(np.float32)
        d = np.full(xx.shape, 1e9, np.float32)
        for (a, b) in g:
            ax = x + a[0] / 2 * gw + (1 - a[1] / 4) * slant * gh
            ay = y0 + a[1] / 4 * gh
            bx = x + b[0] / 2 * gw + (1 - b[1] / 4) * slant * gh
            by = y0 + b[1] / 4 * gh
            vx, vy = bx - ax, by - ay
            L2 = max(vx * vx + vy * vy, 1e-6)
            t = np.clip(((xx - ax) * vx + (yy - ay) * vy) / L2, 0, 1)
            px, py = ax + t * vx - xx, ay + t * vy - yy
            d = np.minimum(d, np.sqrt(px * px + py * py))
        cov = np.clip(lw * 0.5 - d + 0.5, 0, 1)
        img[ya:yb, xa:xb] = np.maximum(img[ya:yb, xa:xb], cov * value)
        x += gw * spacing
    return img


def rounded_rect_sdf(xx, yy, cx, cy, hw, hh, r):
    qx = np.abs(xx - cx) - (hw - r)
    qy = np.abs(yy - cy) - (hh - r)
    out = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0) - r
    return out


# ------------------------------------------------------------------------------------------------ material sets
def paint_set(n, tile_m, base_srgb, metal, metal_flake, smooth, seed=7, flake_tilt=0.035, shared=None):
    """Clear-coat car paint. Normal + flake field are shared by all colours (pass `shared` to reuse)."""
    texel = tile_m / n
    if shared is None:
        rng = np.random.default_rng(seed)
        # metallic flakes: sparse 1-2 texel platelets with random tilt
        dens = rng.random((n, n)).astype(np.float32)
        flake = (dens < 0.22).astype(np.float32)
        flake = np.clip(blur(flake, 0.55) * 1.6, 0, 1)
        tx = rng.standard_normal((n, n)).astype(np.float32)
        ty = rng.standard_normal((n, n)).astype(np.float32)
        tx = blur(tx, 0.6) * flake
        ty = blur(ty, 0.6) * flake
        s = max(tx.std(), 1e-6)
        tx, ty = tx / s * flake_tilt * 0.5, ty / s * flake_tilt * 0.5
        # orange peel: very low clear-coat waviness (height in metres ~ 10 microns)
        peel = fbm(n, 9.0, seed + 3, octaves=3)
        nrm_peel = normal_from_height(peel * 0.5 + 0.5, texel, depth_m=0.000004)
        nrm = combine_normals(normal_from_tilt(np.clip(tx, -0.4, 0.4), np.clip(ty, -0.4, 0.4)), nrm_peel)
        sparkle = rng.random((n, n)).astype(np.float32) * flake
        mottle = fbm(n, 220.0, seed + 11, octaves=3)
        shared = {"normal": nrm, "flake": flake, "sparkle": sparkle, "peel": peel, "mottle": mottle}
    f = shared["flake"]
    base = np.asarray(base_srgb, np.float32)
    bc = base[None, None, :] * (1.0 + 0.012 * shared["mottle"][..., None])
    m = np.clip(metal + (metal_flake - metal) * f * (0.6 + 0.4 * shared["sparkle"]), 0, 1)
    sm = np.clip(smooth - 0.018 * np.abs(shared["peel"]) - 0.035 * f, 0, 1)
    ao = np.ones((n, n), np.float32)
    return {"BaseColor": np.clip(bc, 0, 1), "MaskMap": mask_map(m, ao, sm), "Normal": shared["normal"]}, shared


def chrome_set(n, tile_m, seed=21, base=(0.93, 0.94, 0.96), smooth=0.95):
    rng = np.random.default_rng(seed)
    scr = np.zeros((n, n), np.float32)
    # micro scratches: a few hundred short random segments (wrap-aware via tiling 3x3 offsets)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    for _ in range(140):
        ax, ay = rng.random(2) * n
        ang = rng.random() * math.pi
        L = rng.uniform(0.04, 0.25) * n
        bx, by = ax + math.cos(ang) * L, ay + math.sin(ang) * L
        xa, xb = int(min(ax, bx)) - 3, int(max(ax, bx)) + 3
        ya, yb = int(min(ay, by)) - 3, int(max(ay, by)) + 3
        sx, sy = np.meshgrid(np.arange(xa, xb), np.arange(ya, yb))
        vx, vy = bx - ax, by - ay
        t = np.clip(((sx - ax) * vx + (sy - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        d = np.hypot(ax + t * vx - sx, ay + t * vy - sy)
        cov = np.clip(1.0 - d, 0, 1) * rng.uniform(0.3, 1.0)
        np.maximum.at(scr, (sy % n, sx % n), cov)
    brush = blur_u(np.random.default_rng(seed + 1).standard_normal((n, n)).astype(np.float32), 30.0)
    brush /= max(brush.std(), 1e-6)
    h = 0.5 + 0.08 * brush - 0.3 * scr
    bc = np.asarray(base, np.float32)[None, None, :] * (1 - 0.05 * scr[..., None])
    sm = np.clip(smooth - 0.25 * scr - 0.01 * np.abs(brush), 0, 1)
    return {"BaseColor": bc, "MaskMap": mask_map(np.ones((n, n), np.float32), np.ones((n, n), np.float32), sm),
            "Normal": normal_from_height(h, tile_m / n, depth_m=0.00002)}


def carbon_set(n, tile_m, seed=31, repeats=16):
    """2x2 twill carbon weave with clear coat. `repeats` = twill repeats (4 tows) across the tile."""
    u, v = grid_uv(n)
    tows = repeats * 4
    cu, cv = u * tows, v * tows
    iu, iv = np.floor(cu).astype(np.int32), np.floor(cv).astype(np.int32)
    fu, fv = cu - iu, cv - iv
    warp_over = ((iu - iv) % 4) < 2
    # tow cross-section heights
    hw = np.sin(np.pi * fv) ** 0.6   # warp tow runs along u, profile across v
    hf = np.sin(np.pi * fu) ** 0.6   # weft tow runs along v
    h = np.where(warp_over, 0.55 + 0.45 * hw, 0.55 + 0.45 * hf)
    # weave undulation where tows cross under
    rng = np.random.default_rng(seed)
    fib_u = blur_u(rng.standard_normal((n, n)).astype(np.float32), 6.0)
    fib_v = blur_u(rng.standard_normal((n, n)).astype(np.float32).T, 6.0).T
    fib = np.where(warp_over, fib_u, fib_v)
    fib /= max(fib.std(), 1e-6)
    h = h + 0.04 * fib
    sheen = np.where(warp_over, 0.17, 0.095) + 0.014 * fib
    base = np.stack([sheen * 0.95, sheen * 0.98, sheen * 1.08], -1)
    ao = 0.82 + 0.18 * np.clip(h, 0, 1)
    sm = np.full((n, n), 0.9, np.float32) - 0.04 * (1 - np.clip(h, 0, 1))
    return {"BaseColor": np.clip(base, 0, 1), "MaskMap": mask_map(np.zeros((n, n), np.float32), ao, sm),
            "Normal": normal_from_height(np.clip(h, 0, 1), tile_m / n, depth_m=0.00035)}


def brushed_metal_set(n, tile_m, seed=41, base=(0.44, 0.45, 0.47), smooth=0.68):
    rng = np.random.default_rng(seed)
    s = blur_u(rng.standard_normal((n, n)).astype(np.float32), 40.0)
    s /= max(s.std(), 1e-6)
    blot = fbm(n, 140, seed + 2, octaves=3)
    h = 0.5 + 0.12 * s
    bc = np.asarray(base, np.float32)[None, None, :] * (1 + 0.04 * s[..., None] + 0.03 * blot[..., None])
    sm = np.clip(smooth + 0.05 * s - 0.04 * np.abs(blot), 0, 1)
    return {"BaseColor": np.clip(bc, 0, 1), "MaskMap": mask_map(np.ones((n, n), np.float32), np.ones((n, n), np.float32), sm),
            "Normal": normal_from_height(h, tile_m / n, depth_m=0.00003)}


def rubber_set(n, tile_m, seed=51):
    g = fbm(n, 3.0, seed, octaves=3)
    blot = fbm(n, 90, seed + 4, octaves=4)
    h = 0.5 + 0.15 * g
    v = 0.072 + 0.01 * blot + 0.005 * g
    bc = np.stack([v, v, v * 1.04], -1)
    sm = np.clip(0.24 - 0.05 * blot, 0, 1)
    ao = np.clip(0.9 + 0.1 * g, 0, 1)
    return {"BaseColor": bc, "MaskMap": mask_map(np.zeros((n, n), np.float32), ao, sm),
            "Normal": normal_from_height(h, tile_m / n, depth_m=0.00008)}


def plastic_set(n, tile_m, seed=61, base=0.09, smooth=0.40):
    g = fbm(n, 2.0, seed, octaves=2)
    h = 0.5 + 0.2 * g
    blot = fbm(n, 120, seed + 9, octaves=3)
    v = base * (1 + 0.08 * blot)
    bc = np.stack([v, v * 1.02, v * 1.06], -1)
    sm = np.clip(smooth - 0.05 * g - 0.03 * blot, 0, 1)
    return {"BaseColor": bc, "MaskMap": mask_map(np.zeros((n, n), np.float32), np.ones((n, n), np.float32), sm),
            "Normal": normal_from_height(h, tile_m / n, depth_m=0.00005)}


def interior_set(n, tile_m, seed=71, quilt=8):
    """Charcoal leather with diamond quilting and stitch rows."""
    u, v = grid_uv(n)
    a = (u + v) * quilt
    b = (u - v) * quilt
    da = np.abs(a - np.round(a))
    db = np.abs(b - np.round(b))
    seam = np.minimum(da, db)
    pillow = np.clip(seam * 2.0, 0, 1) ** 0.5
    stitch_dash = (np.sin((u + v) * quilt * 40 * np.pi) > 0.2) | (np.sin((u - v) * quilt * 40 * np.pi) > 0.2)
    stitch = (seam < 0.018) & stitch_dash
    grain = fbm(n, 2.5, seed, octaves=3)
    cells = np.abs(band_noise(n, 6.0, seed + 3))
    h = 0.35 + 0.5 * pillow + 0.03 * grain - 0.04 * np.clip(1 - cells, 0, 1)
    base = np.array([0.115, 0.105, 0.10], np.float32)
    bc = base[None, None, :] * (0.9 + 0.1 * pillow[..., None] + 0.03 * grain[..., None])
    bc = np.where(stitch[..., None], np.array([0.30, 0.10, 0.26], np.float32)[None, None, :], bc)
    ao = np.clip(0.55 + 0.45 * pillow, 0, 1)
    sm = np.clip(0.42 + 0.06 * grain, 0, 1)
    return {"BaseColor": np.clip(bc, 0, 1), "MaskMap": mask_map(np.zeros((n, n), np.float32), ao, sm),
            "Normal": normal_from_height(np.clip(h, 0, 1), tile_m / n, depth_m=0.004)}


def led_pattern(n, rows=25, cols=40):
    """Grid of rounded LED cells; returns (cell mask 0..1, dome height)."""
    u, v = grid_uv(n)
    cu, cv = u * cols, v * rows
    fu, fv = cu - np.floor(cu), cv - np.floor(cv)
    d = rounded_rect_sdf(fu, fv, 0.5, 0.5, 0.40, 0.33, 0.14)
    cell = np.clip(0.5 - d * 60.0, 0, 1)
    dome = np.clip(-d / 0.33, 0, 1) ** 0.5 * cell
    return cell, dome


def emissive_set(n, tile_m, emit_rgb, lens_srgb, pattern):
    cell, dome = pattern
    e = np.asarray(emit_rgb, np.float32)
    em = e[None, None, :] * (0.28 + 0.72 * cell[..., None])
    lens = np.asarray(lens_srgb, np.float32)
    bc = lens[None, None, :] * (0.55 + 0.45 * cell[..., None])
    return {"BaseColor": np.clip(bc, 0, 1), "Emission": np.clip(em, 0, 1)}


def led_shared(n, tile_m, pattern):
    cell, dome = pattern
    sm = 0.9 + 0.05 * cell
    return {"MaskMap": mask_map(np.zeros((n, n), np.float32), np.clip(0.75 + 0.25 * cell, 0, 1), sm),
            "Normal": normal_from_height(dome, tile_m / n, depth_m=0.0012)}


def honeycomb(n, cells=18):
    """Hex honeycomb thrust grille: returns (glow 0..1 bright in cell centres, height)."""
    u, v = grid_uv(n)
    x = u * cells
    y = v * cells * 2 / math.sqrt(3)  # keep tileable: vertical period = cells*2/sqrt3 rows
    y = v * round(cells * 2 / math.sqrt(3) / 2) * 2
    # axial hex distance (approximate, via two offset grids)
    def cellc(xx, yy):
        fx, fy = xx - np.floor(xx) - 0.5, (yy - np.floor(yy) - 0.5)
        return np.sqrt((fx * 1.0) ** 2 + (fy * 0.866) ** 2)
    d1 = cellc(x, y)
    d2 = cellc(x + 0.5, y + 0.5)
    d = np.minimum(d1, d2)
    glow = np.clip(1.0 - d / 0.42, 0, 1) ** 1.5
    wall = smoothstep(0.30, 0.40, d)
    return glow, 1.0 - wall


def thruster_set(n, tile_m, emit_rgb, seed=81):
    glow, h = honeycomb(n)
    e = np.asarray(emit_rgb, np.float32)
    hot = np.array([0.85, 0.95, 1.0], np.float32)
    em = e[None, None, :] * (0.15 + 0.85 * glow[..., None]) + hot[None, None, :] * (glow[..., None] ** 4) * 0.6
    bc = np.stack([0.12 + 0.2 * glow, 0.14 + 0.3 * glow, 0.18 + 0.4 * glow], -1)
    sm = 0.55 + 0.3 * glow
    return {"BaseColor": np.clip(bc, 0, 1), "Emission": np.clip(em, 0, 1),
            "MaskMap": mask_map(1.0 - glow, np.clip(0.5 + 0.5 * h, 0, 1), sm),
            "Normal": normal_from_height(h, tile_m / n, depth_m=0.003)}


def navlight_set(n):
    u, v = grid_uv(n)
    red = np.array([1.0, 0.06, 0.04], np.float32)
    green = np.array([0.1, 1.0, 0.35], np.float32)
    white = np.array([0.92, 0.96, 1.0], np.float32)
    em = np.where((u < 0.5)[..., None], red, green)
    em = np.where((v > 0.75)[..., None], white, em)
    bc = em * 0.55 + 0.1
    return {"BaseColor": bc.astype(np.float32), "Emission": em.astype(np.float32),
            "MaskMap": mask_map(np.zeros((n, n), np.float32), np.ones((n, n), np.float32), np.full((n, n), 0.9, np.float32)),
            "Normal": flat(n, (0.5, 0.5, 1.0))}


def holo_sign_set(n, rgb=(1.0, 0.82, 0.18), seed=91):
    """Holographic glyph sign (0..1 'fit' UV): frame, two glyph lines, scanlines. RGBA BaseColor (A = opacity)."""
    img = np.zeros((n, n), np.float32)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    frame = np.abs(rounded_rect_sdf(xx, yy, n / 2, n / 2, n * 0.47, n * 0.44, n * 0.05))
    img = np.maximum(img, np.clip(1.0 - frame / (n * 0.008), 0, 1))
    word = [make_glyph(seed + i) for i in range(4)]
    gh = n * 0.27
    total = len(word) * gh * 0.6 * 1.3
    draw_glyphs(img, word, (n - total) / 2 - gh * 0.05, n * 0.20, gh, spacing=1.3, width_frac=0.16, slant=0.12)
    sub = [make_glyph(seed + 50 + i) for i in range(9)]
    gh2 = n * 0.11
    total2 = len(sub) * gh2 * 0.6 * 1.3
    draw_glyphs(img, sub, (n - total2) / 2, n * 0.64, gh2, spacing=1.3, width_frac=0.15, value=0.8)
    scan = 0.82 + 0.18 * (np.sin(yy / n * np.pi * 2 * 96) > 0)
    a = np.clip(img * scan, 0, 1)
    rgb = np.asarray(rgb, np.float32)
    em = rgb[None, None, :] * (a[..., None] * 1.0 + 0.06)
    bc = np.concatenate([rgb[None, None, :] * np.ones((n, n, 1), np.float32), (0.10 + 0.9 * a)[..., None]], -1)
    return {"BaseColor": np.clip(bc, 0, 1), "Emission": np.clip(em, 0, 1)}


def glass_cracked_set(n, tile_m, seed=101):
    """Tinted glass with a tileable crack network. RGBA BaseColor (A = opacity), mask smoothness."""
    f1, f2, cid = voronoi(n, 46, seed)
    edge = f2 - f1
    cracks = np.clip(1.0 - edge / 1.6, 0, 1)
    rng = np.random.default_rng(seed)
    keep = rng.random(46) < 0.75
    cracks *= keep[cid]
    # radial cracks from 3 impact points
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    for _ in range(3):
        cx, cy = rng.random(2) * n
        dx = (xx - cx + n / 2) % n - n / 2
        dy = (yy - cy + n / 2) % n - n / 2
        r = np.hypot(dx, dy)
        ang = np.arctan2(dy, dx)
        spokes = int(rng.integers(9, 15))
        ray = np.abs(np.sin(ang * spokes / 2 + band_noise(n, 30, int(rng.integers(1e6))) * 0.25))
        cracks = np.maximum(cracks, np.clip(1 - ray * r / 2.2, 0, 1) * (r < n * 0.3) * (r > 2))
        ring = np.abs(np.sin(r / (n * 0.05) * np.pi + band_noise(n, 12, int(rng.integers(1e6))) * 1.2))
        cracks = np.maximum(cracks, np.clip(1 - ring * 8, 0, 1) * (r < n * 0.07) * 0.5 * (ray < 0.6))
    cracks = np.clip(cracks, 0, 1)
    tint = np.array([0.05, 0.075, 0.095], np.float32)
    rgb = tint[None, None, :] * (1 - cracks[..., None]) + np.array([0.75, 0.8, 0.82], np.float32) * cracks[..., None]
    a = 0.55 + 0.4 * cracks
    sm = 0.95 - 0.5 * cracks
    return {"BaseColor": np.concatenate([rgb, a[..., None]], -1),
            "MaskMap": mask_map(np.zeros((n, n), np.float32), np.ones((n, n), np.float32), sm),
            "Normal": normal_from_height(cracks * 0.5 + 0.5, tile_m / n, depth_m=0.0004)}


def wrecked_paint_set(n, tile_m, seed=111, base=(0.17, 0.18, 0.19)):
    """Dull scratched gunmetal paint: rust concentrated in blooms + streaks, soot/scorch, grime, sparse chips."""
    rust_n = fbm(n, 300, seed, octaves=6)
    streak = blur_u(np.random.default_rng(seed + 1).standard_normal((n, n)).astype(np.float32).T, 60.0).T
    streak /= max(streak.std(), 1e-6)
    rust = smoothstep(0.62, 0.95, rust_n + 0.12 * streak)
    pits = fbm(n, 6.0, seed + 5, octaves=3)
    scorch = smoothstep(0.15, 0.95, fbm(n, 420, seed + 9, octaves=5))
    chips = smoothstep(0.78, 0.86, fbm(n, 22, seed + 13, octaves=4)) * (1 - rust)
    grime = remap01(fbm(n, 60, seed + 17, octaves=5))
    scr = np.clip(blur_u(np.random.default_rng(seed).standard_normal((n, n)).astype(np.float32), 80.0) * 3.0 - 2.6, 0, 1)
    paint = np.asarray(base, np.float32)[None, None, :] * (0.75 + 0.25 * grime[..., None])
    rust_c = np.stack([0.30 + 0.10 * pits, 0.14 + 0.04 * pits, 0.07 + 0.02 * pits], -1)
    primer = np.array([0.30, 0.30, 0.29], np.float32)
    soot = np.array([0.045, 0.042, 0.04], np.float32)
    c = paint * (1 - chips[..., None]) + primer * chips[..., None]
    c = c * (1 - rust[..., None]) + rust_c * rust[..., None]
    c = c * (1 - scr[..., None] * 0.45) + scr[..., None] * 0.45 * np.array([0.45, 0.45, 0.46], np.float32)
    c = c * (1 - scorch[..., None] * 0.7) + soot * scorch[..., None] * 0.7
    metal = np.clip(0.5 * (1 - rust) * (1 - scorch) + 0.6 * scr, 0, 1)
    sm = np.clip(0.52 * (1 - rust) * (1 - 0.6 * scorch) + 0.12, 0, 1)
    h = 0.5 + 0.25 * rust * pits - 0.15 * chips + 0.04 * pits
    ao = np.clip(0.78 + 0.22 * (1 - rust * 0.5) - 0.15 * (1 - grime), 0, 1)
    return {"BaseColor": np.clip(c, 0, 1), "MaskMap": mask_map(metal, ao, sm),
            "Normal": normal_from_height(np.clip(h, 0, 1), tile_m / n, depth_m=0.0012)}


def burnt_set(n, tile_m, seed=121):
    """Fire-gutted steel: mostly black char, brown heat rust running in streaks, small ash blooms, flaking."""
    a = fbm(n, 300, seed, octaves=6)
    ash = smoothstep(0.74, 1.05, a) * 0.40
    streak = blur_u(np.random.default_rng(seed + 2).standard_normal((n, n)).astype(np.float32).T, 90.0).T
    streak /= max(streak.std(), 1e-6)
    rust = smoothstep(0.30, 0.95, fbm(n, 220, seed + 3, octaves=6) + 0.25 * streak) * (1 - ash)
    flakes = smoothstep(0.55, 0.68, fbm(n, 12, seed + 5, octaves=4))
    pits = fbm(n, 4.0, seed + 7, octaves=3)
    char = np.array([0.050, 0.045, 0.042], np.float32)
    rust_c = np.stack([0.24 + 0.08 * pits, 0.11 + 0.03 * pits, 0.05 + 0.015 * pits], -1)
    ash_c = np.array([0.34, 0.33, 0.31], np.float32)
    c = char[None, None, :] * (1 + 0.5 * flakes[..., None]) * np.ones((n, n, 1), np.float32)
    c = c * (1 - rust[..., None] * 0.85) + rust_c * rust[..., None] * 0.85
    c = c * (1 - ash[..., None]) + ash_c * ash[..., None]
    metal = np.clip(0.25 * flakes * (1 - ash), 0, 1)
    sm = np.clip(0.16 + 0.12 * flakes - 0.08 * ash, 0, 1)
    h = 0.5 + 0.2 * pits * rust + 0.2 * flakes
    ao = np.clip(0.7 + 0.3 * (1 - ash), 0, 1)
    return {"BaseColor": np.clip(c, 0, 1), "MaskMap": mask_map(metal, ao, sm),
            "Normal": normal_from_height(np.clip(h, 0, 1), tile_m / n, depth_m=0.0016)}


def decal_atlas_set(n=1024, seed=200):
    """4 x 4 atlas (cells of n/4). Layout (cell col,row from TOP-left):
    row0: (0) badge glyph chrome-on-black, (1) badge glyph cyan, (2) round hub emblem, (3) warning glyph
    row1: ID plate (full width 4:1)
    row2: top half taxi checker band, bottom half hazard chevrons (full width)
    row3: cargo / fleet markings (full width)
    """
    c = n // 4
    rgb = np.zeros((n, n, 3), np.float32)
    metal = np.zeros((n, n), np.float32)
    smooth = np.full((n, n), 0.8, np.float32)
    h = np.zeros((n, n), np.float32)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)

    def cell(col, row, w=1, hh=1):
        return slice(row * c, (row + hh) * c), slice(col * c, (col + w) * c)

    # --- badges
    for col, glyph_seed, accent in ((0, seed, (0.85, 0.87, 0.9)), (1, seed + 7, (0.2, 0.9, 1.0))):
        sy, sx = cell(col, 0)
        m = np.zeros((c, c), np.float32)
        lyy, lxx = np.mgrid[0:c, 0:c].astype(np.float32)
        plate = rounded_rect_sdf(lxx, lyy, c / 2, c / 2, c * 0.46, c * 0.30, c * 0.12)
        border = np.clip(1 - np.abs(plate + c * 0.025) / (c * 0.012), 0, 1)
        draw_glyphs(m, [make_glyph(glyph_seed + i) for i in range(3)], c * 0.17, c * 0.31, c * 0.38, width_frac=0.15, slant=0.15)
        glyph = np.maximum(m, border)
        bg = np.array([0.02, 0.02, 0.025], np.float32)
        rgb[sy, sx] = bg * (1 - glyph[..., None]) + np.asarray(accent, np.float32) * glyph[..., None]
        metal[sy, sx] = glyph
        smooth[sy, sx] = 0.85 + 0.1 * glyph
        h[sy, sx] = glyph * 0.6
    # --- hub emblem
    sy, sx = cell(2, 0)
    lyy, lxx = np.mgrid[0:c, 0:c].astype(np.float32)
    r = np.hypot(lxx - c / 2, lyy - c / 2)
    ring = np.clip(1 - np.abs(r - c * 0.42) / (c * 0.03), 0, 1)
    m = np.zeros((c, c), np.float32)
    draw_glyphs(m, [make_glyph(seed + 33)], c * 0.36, c * 0.27, c * 0.46, width_frac=0.18)
    g = np.maximum(ring, m) * (r < c * 0.48)
    rgb[sy, sx] = np.array([0.03, 0.03, 0.035]) * (1 - g[..., None]) + np.array([0.9, 0.9, 0.92]) * g[..., None]
    metal[sy, sx] = np.maximum(g, 0.2)
    smooth[sy, sx] = 0.9
    h[sy, sx] = g * 0.5
    # --- warning glyph (yellow triangle)
    sy, sx = cell(3, 0)
    tri = np.maximum(np.abs(lxx - c / 2) * 1.15 + (lyy - c * 0.85) * 0.66, (lyy - c * 0.85))
    t_in = np.clip(-(np.maximum(np.abs(lxx - c / 2) * 1.732 - (lyy - c * 0.12), lyy - c * 0.86)) / 3.0, 0, 1)
    m = np.zeros((c, c), np.float32)
    draw_glyphs(m, [make_glyph(seed + 44)], c * 0.42, c * 0.42, c * 0.32, width_frac=0.2)
    rgb[sy, sx] = (np.array([0.02, 0.02, 0.02]) * (1 - t_in[..., None]) + np.array([0.95, 0.72, 0.05]) * t_in[..., None]) * (1 - m[..., None]) + np.array([0.02, 0.02, 0.02]) * m[..., None]
    smooth[sy, sx] = 0.7
    # --- ID plate: 4:1, light reflective plate, dark border, 7 glyphs, small region tag
    sy, sx = cell(0, 1, 4, 1)
    pw, ph = n, c
    pyy, pxx = np.mgrid[0:ph, 0:pw].astype(np.float32)
    plate = rounded_rect_sdf(pxx, pyy, pw / 2, ph / 2, pw * 0.485, ph * 0.44, ph * 0.12)
    inside = np.clip(-plate, 0, 1)
    border = np.clip(1 - np.abs(plate + ph * 0.05) / (ph * 0.025), 0, 1)
    m = np.zeros((ph, pw), np.float32)
    gl = [make_glyph(seed + 60 + i) for i in range(3)] + [None] + [make_glyph(seed + 70 + i) for i in range(4)]
    draw_glyphs(m, gl, pw * 0.12, ph * 0.22, ph * 0.56, spacing=1.35, width_frac=0.14)
    tag = rounded_rect_sdf(pxx, pyy, pw * 0.055, ph / 2, pw * 0.03, ph * 0.3, ph * 0.05)
    tagm = np.clip(-tag, 0, 1)
    plate_c = np.array([0.80, 0.82, 0.80], np.float32)
    ink = np.array([0.03, 0.03, 0.04], np.float32)
    col = plate_c * inside[..., None]
    col = col * (1 - np.maximum(m, border)[..., None]) + ink * np.maximum(m, border)[..., None]
    col = col * (1 - tagm[..., None]) + np.array([0.1, 0.6, 0.85]) * tagm[..., None]
    rgb[sy, sx] = col
    smooth[sy, sx] = 0.55 + 0.2 * inside
    h[sy, sx] = inside * 0.3 + m * 0.4
    # --- taxi checker band (top half row2) + hazard chevrons (bottom half)
    sy, sx = cell(0, 2, 4, 1)
    half = c // 2
    chk = ((np.floor(pxx[:half] / (half / 2)) + np.floor(pyy[:half] / (half / 2))) % 2).astype(np.float32)
    yel = np.array([0.95, 0.72, 0.04], np.float32)
    blk = np.array([0.015, 0.015, 0.017], np.float32)
    rgb[sy.start:sy.start + half, :] = blk * chk[..., None] + yel * (1 - chk[..., None])
    hz = (((pxx[:half] + pyy[:half]) / (half * 0.5)) % 2 < 1).astype(np.float32)
    rgb[sy.start + half:sy.stop, :] = blk * hz[..., None] + yel * (1 - hz[..., None])
    smooth[sy, sx] = 0.85
    # --- fleet / cargo markings row 3: glyph line, barcode, arrows, unit number
    sy, sx = cell(0, 3, 4, 1)
    m = np.zeros((c, n), np.float32)
    draw_glyphs(m, [make_glyph(seed + 90 + i) for i in range(6)], n * 0.03, c * 0.12, c * 0.42, spacing=1.3, width_frac=0.13, slant=0.1)
    draw_glyphs(m, [make_glyph(seed + 120 + i) for i in range(14)], n * 0.03, c * 0.66, c * 0.18, spacing=1.35, width_frac=0.14)
    rng = np.random.default_rng(seed + 5)
    x = n * 0.55
    while x < n * 0.8:
        w = rng.integers(2, 9)
        m[int(c * 0.15):int(c * 0.85), int(x):int(x + w)] = 1.0
        x += w + rng.integers(3, 9)
    for k in range(3):
        ax0 = n * 0.84 + k * c * 0.16
        ar = np.clip(1 - np.abs(np.abs(pyy[:, :] - c / 2) * 0.9 - (pxx - ax0) * 1.0) / 4.0, 0, 1) * ((pxx - ax0) > -c * 0.05) * ((pxx - ax0) < c * 0.18) * (np.abs(pyy - c / 2) < c * 0.3)
        m = np.maximum(m, ar)
    white = np.array([0.88, 0.9, 0.9], np.float32)
    rgb[sy, sx] = np.array([0.02, 0.02, 0.025]) * (1 - m[..., None]) + white * m[..., None]
    smooth[sy, sx] = 0.7
    nrm = normal_from_height(np.clip(h, 0, 1), 0.3 / n, depth_m=0.0004)
    return {"BaseColor": np.clip(rgb, 0, 1), "MaskMap": mask_map(metal, np.ones((n, n), np.float32), smooth), "Normal": nrm}


# Atlas cell rects in UV space (u0, v0, u1, v1), v up, for the builder.
def atlas_rect(name):
    q = 0.25
    cells = {
        "badge_a": (0 * q, 1 - 1 * q, 1 * q, 1.0),
        "badge_b": (1 * q, 1 - 1 * q, 2 * q, 1.0),
        "hub": (2 * q, 1 - 1 * q, 3 * q, 1.0),
        "warning": (3 * q, 1 - 1 * q, 4 * q, 1.0),
        "plate": (0.0, 1 - 2 * q, 1.0, 1 - q),
        "checker": (0.0, 1 - 2.5 * q, 1.0, 1 - 2 * q),
        "hazard": (0.0, 1 - 3 * q, 1.0, 1 - 2.5 * q),
        "fleet": (0.0, 0.0, 1.0, q),
    }
    return cells[name]
