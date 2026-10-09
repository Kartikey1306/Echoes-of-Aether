"""Procedural texture helpers (numpy): value noise / fbm in 3D, cellular, stitch and seam profiles, quilting,
knit/twill/webbing micro-height, glyph decals (invented characters, no real text or brands)."""
import math
import numpy as np
import gv


def hash3(i, j, k, seed=0):
    h = (i * 374761393 + j * 668265263 + k * 2147483647 + seed * 974711) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF) / float(0xFFFFFF)


def vnoise(P, freq, seed=0):
    """Smooth value noise in 3D (P: (...,3) metres, freq: cells per metre) -> [0,1]."""
    Q = P * freq
    i = np.floor(Q).astype(np.int64)
    f = Q - i
    u = f * f * (3 - 2 * f)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                h = hash3(i[..., 0] + dx, i[..., 1] + dy, i[..., 2] + dz, seed)
                w = (u[..., 0] if dx else 1 - u[..., 0]) * (u[..., 1] if dy else 1 - u[..., 1]) * (u[..., 2] if dz else 1 - u[..., 2])
                out = out + h * w
    return out


def fbm(P, freq, octaves=4, seed=0, gain=0.5, lac=2.03):
    a, s, n = 1.0, 0.0, 0.0
    for o in range(octaves):
        s += a * vnoise(P, freq * lac ** o, seed + o * 17)
        n += a
        a *= gain
    return s / n


def ridge(x, w):
    """Smooth bump of half-width w centred on 0."""
    return np.exp(-(x / w) ** 2)


def groove(d, w, depth):
    """Seam groove profile from distance-to-line d."""
    return -depth * np.exp(-(d / w) ** 2)


def stitches(d, s, offset=0.0026, w=0.00045, pitch=0.0032, duty=0.62, height=0.00022):
    """Row of stitches parallel to a seam: d = signed distance to the seam line (m), s = arc length along it."""
    out = 0.0
    for side in (-1, 1):
        dd = d - side * offset
        on = ((s / pitch) % 1.0) < duty
        out = out + height * ridge(dd, w) * on
    return out


def periodic_ribs(x, pitch, amp, sharp=2.0):
    return amp * (0.5 + 0.5 * np.cos(2 * math.pi * x / pitch)) ** sharp


def quilt(u, v, pitch, amp, line_w=0.0012, angle=45.0):
    """Diamond quilting: stitched channels on a rotated grid (u, v metres in a local 2D frame)."""
    a = math.radians(angle)
    x = u * math.cos(a) + v * math.sin(a)
    y = -u * math.sin(a) + v * math.cos(a)
    fx = (x / pitch) % 1.0 - 0.5
    fy = (y / pitch) % 1.0 - 0.5
    puff = amp * (np.cos(fx * math.pi) * np.cos(fy * math.pi)) ** 0.7
    ch = np.minimum(np.abs(fx), np.abs(fy)) * pitch
    return puff - amp * 0.6 * np.exp(-(ch / line_w) ** 2)


def knit(u, v, scale=0.0011, amp=0.00012):
    """Fine technical knit / twill micro height."""
    t = (u + v) / scale
    t2 = (u - 0.5 * v) / (scale * 1.7)
    return amp * (0.6 * np.sin(t * 2 * math.pi) * 0.5 + 0.5) + amp * 0.4 * (np.sin(t2 * 2 * math.pi) * 0.5 + 0.5)


def webbing(across, along, amp=0.00018):
    """Nylon webbing: tight ribs along the strap + fine cross weave."""
    r = periodic_ribs(across, 0.0011, amp, 1.5)
    c = periodic_ribs(along, 0.0009, amp * 0.4, 1.0)
    return r + c


def sdf_box(x, y, hx, hy, r=0.0):
    qx, qy = np.abs(x) - hx + r, np.abs(y) - hy + r
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def sdf_segment(x, y, ax, ay, bx, by):
    px, py = x - ax, y - ay
    dx, dy = bx - ax, by - ay
    t = np.clip((px * dx + py * dy) / max(dx * dx + dy * dy, 1e-12), 0, 1)
    return np.hypot(px - dx * t, py - dy * t)


# ----------------------------------------------------------------------------- invented glyphs for decals

GLYPHS = {
    # 3x5 stroke glyphs on a unit cell (x 0..1, y 0..1): invented "Aether" script + digits
    "0": [((0, 0), (1, 0)), ((1, 0), (1, 1)), ((1, 1), (0, 1)), ((0, 1), (0, 0))],
    "1": [((0.5, 0), (0.5, 1)), ((0.2, 0.8), (0.5, 1))],
    "2": [((0, 1), (1, 1)), ((1, 1), (1, 0.5)), ((1, 0.5), (0, 0.5)), ((0, 0.5), (0, 0)), ((0, 0), (1, 0))],
    "3": [((0, 1), (1, 1)), ((1, 1), (1, 0)), ((1, 0), (0, 0)), ((0.3, 0.5), (1, 0.5))],
    "4": [((0, 1), (0, 0.5)), ((0, 0.5), (1, 0.5)), ((1, 1), (1, 0))],
    "7": [((0, 1), (1, 1)), ((1, 1), (0.4, 0))],
    "9": [((1, 0.5), (0, 0.5)), ((0, 0.5), (0, 1)), ((0, 1), (1, 1)), ((1, 1), (1, 0))],
    "A": [((0, 0), (0.5, 1)), ((0.5, 1), (1, 0)), ((0.25, 0.45), (0.75, 0.45))],
    "V": [((0, 1), (0.5, 0)), ((0.5, 0), (1, 1))],
    "E": [((1, 1), (0, 1)), ((0, 1), (0, 0)), ((0, 0), (1, 0)), ((0, 0.5), (0.7, 0.5))],
    "Λ": [((0, 0), (0.5, 1)), ((0.5, 1), (1, 0))],
    "Ξ": [((0, 1), (1, 1)), ((0.15, 0.5), (0.85, 0.5)), ((0, 0), (1, 0))],
    "Ψ": [((0.5, 0), (0.5, 1)), ((0, 1), (0, 0.55)), ((0, 0.55), (1, 0.55)), ((1, 0.55), (1, 1))],
    "-": [((0.1, 0.5), (0.9, 0.5))],
    "·": [((0.45, 0.45), (0.55, 0.55))],
}


def text_sdf(x, y, text, h, spacing=0.35):
    """Distance field of a glyph string laid along +x with cap height h (glyph width 0.62 h)."""
    w = 0.62 * h
    d = np.full(np.shape(x), 1e9)
    for i, ch in enumerate(text):
        segs = GLYPHS.get(ch)
        if not segs:
            continue
        ox = i * (w + spacing * h)
        for (a, b) in segs:
            d = np.minimum(d, sdf_segment(x, y, ox + a[0] * w, a[1] * h, ox + b[0] * w, b[1] * h))
    return d


def chevrons(x, y, w, pitch, slant=1.0):
    """Hazard chevron stripes mask in a band |y| < w (x along the band)."""
    t = ((x + np.abs(y) * slant) / pitch) % 1.0
    return ((t < 0.5) & (np.abs(y) < w)).astype(np.float32)


def local2(P, c, n, up):
    """Local decal coordinates (x, y, depth) of points P relative to centre c, normal n, up direction."""
    n = gv.nrm(n)
    u = gv.nrm(np.asarray(up, float) - n * (np.asarray(up, float) @ n))
    r = np.cross(u, n)
    d = P - c
    return d @ r, d @ u, d @ n
