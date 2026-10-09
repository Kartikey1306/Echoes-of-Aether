"""Procedural texture helpers (plain Python 3 + numpy/scipy/PIL; no Blender). Everything is generated from seeded
noise and analytic shapes - no photos, no AI images.

Conventions: images are float32 arrays, row 0 = TOP of the image (PIL order). Colours are LINEAR RGB unless a
name says srgb. Tileable functions wrap around both axes.
"""
import math

import numpy as np
from PIL import Image
from scipy import ndimage


# ============================================================================================== colour
def srgb_to_linear(x):
    x = np.clip(np.asarray(x, np.float32), 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(x):
    x = np.clip(np.asarray(x, np.float32), 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1.0 / 2.4) - 0.055).astype(np.float32)


def hexlin(h):
    h = h.lstrip("#")
    return srgb_to_linear(np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32))


def to_u8(x):
    return (np.clip(x, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def save_rgb(path, lin_rgb=None, srgb=None):
    a = linear_to_srgb(lin_rgb) if srgb is None else srgb
    Image.fromarray(to_u8(a), "RGB").save(path, optimize=False, compress_level=6)


def save_rgba(path, rgba):
    Image.fromarray(to_u8(rgba), "RGBA").save(path, compress_level=6)


def load(path, mode="RGB"):
    return np.asarray(Image.open(path).convert(mode), np.float32) / 255.0


# ============================================================================================== noise
def vnoise(h, w, cells_y, cells_x, seed, order=3):
    """Tileable value noise: a random lattice (cells_y x cells_x) upsampled with wrap-around cubic interpolation."""
    rng = np.random.default_rng(seed)
    g = rng.random((cells_y, cells_x)).astype(np.float32)
    zy, zx = h / cells_y, w / cells_x
    yy = (np.arange(h) + 0.5) / zy - 0.5
    xx = (np.arange(w) + 0.5) / zx - 0.5
    Y, X = np.meshgrid(yy, xx, indexing="ij")
    out = ndimage.map_coordinates(g, [Y, X], order=order, mode="grid-wrap")
    return out.astype(np.float32)


def fbm(h, w, base_cells, seed, octaves=5, rough=0.5, aspect=1.0):
    """Tileable fractal noise in 0..1 (base_cells across the width; `aspect` stretches cells vertically)."""
    tot = np.zeros((h, w), np.float32)
    amp, norm = 1.0, 0.0
    c = base_cells
    for o in range(octaves):
        cx = max(1, int(round(c)))
        cy = max(1, int(round(c * h / w / aspect)))
        tot += amp * vnoise(h, w, cy, cx, seed + o * 7919)
        norm += amp
        amp *= rough
        c *= 2.0
    return tot / norm


def blur(a, sigma, wrap=True):
    if sigma <= 0:
        return a
    mode = "wrap" if wrap else "nearest"
    if a.ndim == 3:
        return np.stack([ndimage.gaussian_filter(a[..., k], sigma, mode=mode) for k in range(a.shape[2])], -1)
    return ndimage.gaussian_filter(a, sigma, mode=mode)


def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    t = np.asarray(t, np.float32)
    if t.ndim == 2 and (np.ndim(a) == 3 or np.ndim(b) == 3 or (np.ndim(a) == 1 and np.size(a) == 3) or (np.ndim(b) == 1 and np.size(b) == 3)):
        t = t[..., None]
    return np.asarray(a, np.float32) + (np.asarray(b, np.float32) - np.asarray(a, np.float32)) * t


def normal_from_height(hm, px_m, strength=1.0, wrap=True):
    """OpenGL tangent-space normal (+Y up, i.e. image row 0 is +V) from a height field in metres."""
    mode = "wrap" if wrap else "nearest"
    dx = (np.roll(hm, -1, 1) - np.roll(hm, 1, 1)) * 0.5 if wrap else ndimage.sobel(hm, 1, mode=mode) / 8.0
    dy = (np.roll(hm, -1, 0) - np.roll(hm, 1, 0)) * 0.5 if wrap else ndimage.sobel(hm, 0, mode=mode) / 8.0
    # px_m = metres per pixel; slope along U = dx / px_m. Rows grow downward (-V), so dh/dV = -dy / px_m.
    nx = -dx / px_m * strength
    ny = dy / px_m * strength
    nz = np.ones_like(hm)
    n = np.stack([nx, ny, nz], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def ao_from_height(hm, px_m, radius_m=0.02, strength=1.0):
    r = max(0.8, radius_m / px_m)
    cav = blur(hm, r) - hm
    return np.clip(1.0 - np.clip(cav / max(radius_m * 0.25, 1e-6), 0, 1) * strength, 0.0, 1.0)


# ============================================================================================== drawing (antialiased, in pixel space)
def grid(h, w):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return x + 0.5, y + 0.5


def rect_mask(h, w, x0, y0, x1, y1, soft=0.75):
    X, Y = grid(h, w)
    mx = smooth(X, x0 - soft, x0 + soft) * (1 - smooth(X, x1 - soft, x1 + soft))
    my = smooth(Y, y0 - soft, y0 + soft) * (1 - smooth(Y, y1 - soft, y1 + soft))
    return mx * my


def seg_mask(h, w, segs, width, soft=0.8):
    """Union of thick line segments [(x0,y0,x1,y1)...] in pixels (round caps)."""
    X, Y = grid(h, w)
    m = np.zeros((h, w), np.float32)
    for (x0, y0, x1, y1) in segs:
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        if L2 < 1e-6:
            d = np.hypot(X - x0, Y - y0)
        else:
            t = np.clip(((X - x0) * dx + (Y - y0) * dy) / L2, 0, 1)
            d = np.hypot(X - (x0 + t * dx), Y - (y0 + t * dy))
        m = np.maximum(m, 1 - smooth(d, width / 2 - soft, width / 2 + soft))
    return m


def circle_mask(h, w, cx, cy, r, soft=0.8):
    X, Y = grid(h, w)
    return 1 - smooth(np.hypot(X - cx, Y - cy), r - soft, r + soft)


def glyph_strokes(rng, x0, y0, gw, gh, cols=3, rows=4):
    """Invented glyph: 3-6 strokes on a small grid (no real letters). Returns pixel segments."""
    pts = [(x0 + gw * i / (cols - 1), y0 + gh * j / (rows - 1)) for j in range(rows) for i in range(cols)]
    segs = []
    n = rng.integers(3, 7)
    used = set()
    a = rng.integers(len(pts))
    for _ in range(n):
        # move to a grid neighbour (orthogonal or diagonal), sometimes jump
        ai, aj = a % cols, a // cols
        cand = [(ai + di, aj + dj) for di in (-1, 0, 1) for dj in (-1, 0, 1) if (di or dj) and 0 <= ai + di < cols and 0 <= aj + dj < rows]
        bi, bj = cand[rng.integers(len(cand))]
        b = bj * cols + bi
        key = (min(a, b), max(a, b))
        if key not in used:
            used.add(key)
            segs.append((*pts[a], *pts[b]))
        a = b if rng.random() < 0.75 else rng.integers(len(pts))
    if rng.random() < 0.5:  # a dot / short tick
        p = pts[rng.integers(len(pts))]
        segs.append((p[0], p[1], p[0] + 0.01, p[1] + 0.01))
    return segs


# ============================================================================================== resampling
def resample_tile(img, src_tile_m, out_w, out_h, span_w_m, span_h_m, y_off_m=0.0, x_off_m=0.0):
    """Sample a tileable texture (src_tile_m metres per repeat) into an out_w x out_h block covering
    span_w_m x span_h_m metres, with a supersampled box filter (wrap-around)."""
    sh, sw = img.shape[:2]
    ss = 3
    xs = (np.arange(out_w * ss) + 0.5) / (out_w * ss) * span_w_m + x_off_m
    ys = (np.arange(out_h * ss) + 0.5) / (out_h * ss) * span_h_m + y_off_m
    px = (xs / src_tile_m * sw) % sw - 0.5
    py = (ys / src_tile_m * sh) % sh - 0.5
    Y, X = np.meshgrid(py, px, indexing="ij")
    chans = img.shape[2] if img.ndim == 3 else 1
    src = img if img.ndim == 3 else img[..., None]
    out = np.stack([ndimage.map_coordinates(src[..., k], [Y, X], order=1, mode="grid-wrap") for k in range(chans)], -1)
    out = out.reshape(out_h, ss, out_w, ss, chans).mean(axis=(1, 3))
    return out if img.ndim == 3 else out[..., 0]


def resize(img, w, h):
    """Area/Lanczos resize of a float image (0..1)."""
    chans = img.shape[2] if img.ndim == 3 else 1
    out = []
    for k in range(chans):
        ch = img[..., k] if img.ndim == 3 else img
        im = Image.fromarray(ch.astype(np.float32), "F").resize((w, h), Image.LANCZOS)
        out.append(np.asarray(im, np.float32))
    o = np.stack(out, -1) if img.ndim == 3 else out[0]
    return np.clip(o, 0.0, 1.0)


def renorm(nmap01):
    n = nmap01 * 2 - 1
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)
    return n * 0.5 + 0.5
