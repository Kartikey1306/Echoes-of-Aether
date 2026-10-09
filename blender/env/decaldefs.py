"""URP decal texture definitions for the Aether-9 environment kit (rain-soaked cyberpunk megacity at night).

Every decal is ONE non-tiling image set generated in numpy (no Blender needed, so it also runs in plain python3):
  <Name>_BaseColor.png  sRGB RGB + decal opacity in A (fades to 0 at every border)
  <Name>_Normal.png     OpenGL tangent-space normal (derived from a height field with bakekit.height_to_normal)
  <Name>_MaskMap.png    URP decal MAOS: R metallic, G ambient occlusion, B unused (1), A smoothness

A definition is a generator fn(c, p) -> Stack, where `c` is a Canvas (pixel grid in metres) and `p` its params.
Arrays are BOTTOM row first (Blender pixel order): +row = +V = "up" on walls / "forward" on floors.
Generators composite layers into a Stack (premultiplied alpha for colour / smoothness / metallic / AO, additive height).

All glyphs are invented with the same grammar as matdefs_hd.glyph() (roof bar, stems, enclosure box or crossing
diagonals, mid bar, ticks, dot: 5-8 strokes) so nothing reads as a Latin letter or any real script. No words, no logos.
"""
import math
import random

import numpy as np

from matdefs_base import lin

F32 = np.float32
TAU = math.tau

NEON = {"magenta": "#ff2bd6", "pink": "#ff4f9a", "cyan": "#00e5ff", "blue": "#3d7bff", "yellow": "#ffe14d",
        "violet": "#9b5cff"}


def L(h):
    """sRGB hex -> linear float32 RGB."""
    return np.array(lin(h), F32)


def N(name):
    return L(NEON[name])


# ============================================================================================== canvas + maths
class Canvas:
    """W x H pixels covering w x h metres (square pixels). x, y are pixel-centre coordinates in metres."""

    def __init__(self, size_m, pixels, seed):
        self.W, self.H = int(pixels[0]), int(pixels[1])
        self.wm, self.hm = float(size_m[0]), float(size_m[1])
        self.px = self.wm / self.W
        yy, xx = np.mgrid[0:self.H, 0:self.W]
        self.x = ((xx + 0.5) * self.px).astype(F32)
        self.y = ((yy + 0.5) * self.px).astype(F32)
        self.seed = seed
        self.r = random.Random(seed)
        self._k = 0

    def s(self):
        self._k += 1
        return (self.seed * 7919 + self._k * 104729) % (2 ** 31 - 1)

    def zeros(self):
        return np.zeros((self.H, self.W), F32)

    def full(self, v):
        return np.full((self.H, self.W), v, F32)

    def win(self, x0, y0, x1, y1):
        """Pixel window (slices) covering the metre rectangle, clamped; None if empty."""
        i0 = max(0, int(math.floor(y0 / self.px)))
        i1 = min(self.H, int(math.ceil(y1 / self.px)) + 1)
        j0 = max(0, int(math.floor(x0 / self.px)))
        j1 = min(self.W, int(math.ceil(x1 / self.px)) + 1)
        if i0 >= i1 or j0 >= j1:
            return None
        return (slice(i0, i1), slice(j0, j1))

    def edge_dist(self):
        return np.minimum(np.minimum(self.x, self.wm - self.x), np.minimum(self.y, self.hm - self.y))

    def aa(self, k=0.75):
        return self.px * k


def sst(x, a, b):
    """smoothstep from a to b (a > b gives the falling edge)."""
    t = np.clip((np.asarray(x, F32) - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def cov(sd, c, k=0.75):
    """Anti-aliased coverage of a signed distance field (metres, negative inside)."""
    w = c.px * k
    return np.clip(0.5 - sd / (2.0 * w), 0.0, 1.0).astype(F32)


def _nice(n):
    m = 64
    return int(math.ceil(n / m) * m)


def blur(a, sx, sy=None, mode="reflect"):
    """Gaussian blur (sigma in px, optionally anisotropic) for any rectangular array; padded, so it does NOT wrap."""
    sy = sx if sy is None else sy
    if sx < 0.3 and sy < 0.3:
        return a
    if a.ndim == 3:
        return np.stack([blur(a[..., k], sx, sy, mode) for k in range(a.shape[2])], axis=-1)
    H, W = a.shape
    py = min(H - 1, int(3 * sy) + 2)
    pxx = min(W - 1, int(3 * sx) + 2)
    Hb, Wb = _nice(H + 2 * py), _nice(W + 2 * pxx)
    b = np.pad(a, ((py, Hb - H - py), (pxx, Wb - W - pxx)), mode=mode if mode else "constant")
    fy = np.fft.fftfreq(Hb)[:, None]
    fx = np.fft.rfftfreq(Wb)[None, :]
    g = np.exp(-2.0 * np.pi ** 2 * ((sx * fx) ** 2 + (sy * fy) ** 2))
    out = np.fft.irfft2(np.fft.rfft2(b) * g, s=(Hb, Wb))
    return out[py:py + H, pxx:pxx + W].astype(F32)


def fbm(c, feat_m, octaves=5, gain=0.5, lac=2.0, ax=1.0, ay=1.0, seed=None):
    """Fractal gaussian noise, zero mean / unit std. feat_m = size of the largest features in metres.
    ax / ay > 1 STRETCH features along x / y (ay=5, ax=0.3 gives vertical streaks)."""
    seed = c.s() if seed is None else seed
    rs = np.random.RandomState(seed % (2 ** 31 - 1))
    H, W = c.H, c.W
    F = np.fft.rfft2(rs.standard_normal((H, W)).astype(F32))
    fy = np.fft.fftfreq(H)[:, None]
    fx = np.fft.rfftfreq(W)[None, :]
    acc = 0.0
    for i in range(octaves):
        s = feat_m / (lac ** i) / c.px * 0.25
        if s < 0.35:
            break
        g = np.exp(-2.0 * np.pi ** 2 * ((s * ax * fx) ** 2 + (s * ay * fy) ** 2))
        acc = acc + (gain ** i) * g / np.sqrt(np.mean(g * g) + 1e-12)
    out = np.fft.irfft2(F * acc, s=(H, W))
    out -= out.mean()
    out /= out.std() + 1e-9
    return out.astype(F32)


def n01(f, lo=-2.0, hi=2.0):
    return np.clip((f - lo) / (hi - lo), 0.0, 1.0).astype(F32)


def white(c, seed=None):
    seed = c.s() if seed is None else seed
    return np.random.RandomState(seed % (2 ** 31 - 1)).rand(c.H, c.W).astype(F32)


def sample(a, X, Y):
    """Bilinear sample of a (H,W[,k]) at float pixel coords X, Y (clamped)."""
    H, W = a.shape[:2]
    X = np.clip(X, 0, W - 1.001)
    Y = np.clip(Y, 0, H - 1.001)
    x0 = X.astype(np.int32)
    y0 = Y.astype(np.int32)
    fx = (X - x0).astype(F32)
    fy = (Y - y0).astype(F32)
    if a.ndim == 3:
        fx = fx[..., None]
        fy = fy[..., None]
    return ((a[y0, x0] * (1 - fx) + a[y0, x0 + 1] * fx) * (1 - fy) + (a[y0 + 1, x0] * (1 - fx) + a[y0 + 1, x0 + 1] * fx) * fy)


def warp(c, a, amp_m, feat_m, octaves=4):
    """Domain-warp field a by fractal noise (amplitude amp_m metres)."""
    dx = fbm(c, feat_m, octaves) * (amp_m / c.px)
    dy = fbm(c, feat_m, octaves) * (amp_m / c.px)
    yy, xx = np.mgrid[0:c.H, 0:c.W].astype(F32)
    return sample(a, xx + dx, yy + dy)


def mixc(col, c2, t):
    t = np.asarray(t, F32)
    if t.ndim == 2:
        t = t[..., None]
    return col + (np.asarray(c2, F32) - col) * t


def mulc(col, f):
    f = np.asarray(f, F32)
    return col * (f[..., None] if f.ndim == 2 else f)


def rot(X, Y, cx, cy, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    dx, dy = X - cx, Y - cy
    return dx * ca + dy * sa, -dx * sa + dy * ca


def sd_box(X, Y, cx, cy, hw, hh, ang=0.0, r=0.0):
    lx, ly = rot(X, Y, cx, cy, ang)
    qx = np.abs(lx) - hw + r
    qy = np.abs(ly) - hh + r
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def sd_seg(X, Y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = np.clip(((X - ax) * dx + (Y - ay) * dy) / max(dx * dx + dy * dy, 1e-12), 0, 1)
    return np.hypot(X - ax - t * dx, Y - ay - t * dy)


def sd_poly(X, Y, P):
    """Signed distance to a closed polygon P (list of (x,y)), negative inside."""
    d = np.full(X.shape, 1e9, F32)
    inside = np.zeros(X.shape, bool)
    n = len(P)
    for i in range(n):
        ax, ay = P[i]
        bx, by = P[(i + 1) % n]
        d = np.minimum(d, sd_seg(X, Y, ax, ay, bx, by))
        if ay != by:
            cond = ((ay > Y) != (by > Y)) & (X < (bx - ax) * (Y - ay) / (by - ay) + ax)
            inside ^= cond
    return np.where(inside, -d, d).astype(F32)


def jag_poly(rng, cx, cy, r, n=12, jit=0.3, ang0=None, sx=1.0, sy=1.0, ang=0.0):
    """Irregular star-convex polygon around (cx, cy)."""
    ang0 = rng.uniform(0, TAU) if ang0 is None else ang0
    ca, sa = math.cos(ang), math.sin(ang)
    P = []
    for k in range(n):
        a = ang0 + TAU * (k + rng.uniform(-0.3, 0.3)) / n
        rr = r * (1 + rng.uniform(-jit, jit))
        lx, ly = math.cos(a) * rr * sx, math.sin(a) * rr * sy
        P.append((cx + lx * ca - ly * sa, cy + lx * sa + ly * ca))
    return P


def stamp(c, x0, y0, x1, y1, fn):
    """Evaluate fn(X, Y) in the window of the metre rectangle; returns (slice, value) or None."""
    sl = c.win(x0, y0, x1, y1)
    if sl is None:
        return None
    return sl, fn(c.x[sl], c.y[sl])


def put_max(arr, res):
    if res is not None:
        sl, v = res
        np.maximum(arr[sl], v, out=arr[sl])


# ---------------------------------------------------------------------------------------------- paths
def frac_path(rng, a, b, rough=0.22, levels=7, decay=1.0):
    """Midpoint-displacement polyline from a to b (crack / rivulet look)."""
    P = [np.array(a, float), np.array(b, float)]
    amp = rough
    for _ in range(levels):
        Q = [P[0]]
        for p, q in zip(P[:-1], P[1:]):
            d = q - p
            Ld = math.hypot(d[0], d[1]) + 1e-12
            nrm = np.array((-d[1], d[0])) / Ld
            Q += [(p + q) / 2 + nrm * rng.gauss(0, 1) * amp * Ld, q]
        P = Q
        amp *= decay
    return np.array(P)


def path_len(P):
    return np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(P, axis=0).T))])


def width_profile(rng, P, w0, taper0=0.15, taper1=0.15, wobble=0.35, end0=0.0, end1=0.0):
    """Half-widths along a path: tapered ends with a smooth random wobble."""
    s = path_len(P)
    t = s / max(s[-1], 1e-9)
    k = np.ones_like(t)
    if taper0 > 0:
        k *= end0 + (1 - end0) * np.clip(t / taper0, 0, 1) ** 0.6
    if taper1 > 0:
        k *= end1 + (1 - end1) * np.clip((1 - t) / taper1, 0, 1) ** 0.6
    wob = np.zeros_like(t)
    for f in (2, 5, 11):
        ph = rng.uniform(0, TAU)
        wob += np.sin(t * f * TAU + ph) / f
    return w0 * k * np.clip(1 + wobble * wob, 0.25, 2.0)


def draw_path(c, S, P, hw, pad):
    """S = min(S, distance-to-path minus half-width) inside the path's bounding windows (S initialised to pad)."""
    for k in range(len(P) - 1):
        ax, ay = P[k]
        bx, by = P[k + 1]
        wa, wb = hw[k], hw[k + 1]
        m = max(wa, wb) + pad
        sl = c.win(min(ax, bx) - m, min(ay, by) - m, max(ax, bx) + m, max(ay, by) + m)
        if sl is None:
            continue
        X, Y = c.x[sl], c.y[sl]
        dx, dy = bx - ax, by - ay
        t = np.clip(((X - ax) * dx + (Y - ay) * dy) / max(dx * dx + dy * dy, 1e-12), 0, 1)
        d = np.hypot(X - ax - t * dx, Y - ay - t * dy) - (wa + (wb - wa) * t)
        np.minimum(S[sl], d, out=S[sl])


def near(S, r, pad):
    """exp falloff of a capped distance field (draw_path caps S at `pad`): exactly 0 where nothing was drawn."""
    return np.exp(-np.maximum(S, 0) / r) * sst(S, pad * 0.97, pad * 0.55)


def bound_path(P, maxdev):
    """Scale a path's deviation from its chord so it never strays more than maxdev from the straight line."""
    a, b = P[0], P[-1]
    d = b - a
    ln = math.hypot(d[0], d[1]) + 1e-12
    n = np.array((-d[1], d[0])) / ln
    dev = (P - a) @ n
    m = np.abs(dev).max()
    if m > maxdev:
        P = P - np.outer(dev * (1 - maxdev / m), n)
    return P


def crack_tree(rng, a, b, w0, rough=0.24, levels=7, branches=3, depth=2, blen=(0.15, 0.45), bang=(25, 65),
               maxdev=None, box=None):
    """Main fractal crack + recursive side branches. Returns list of (points, half-widths).
    maxdev bounds the wander from the chord; box = (x0, y0, x1, y1) keeps branch ends inside the decal."""
    out = []
    P = frac_path(rng, a, b, rough, levels)
    if maxdev is not None:
        P = bound_path(P, maxdev)
    hw = width_profile(rng, P, w0, 0.2, 0.2)
    out.append((P, hw))
    if depth > 0:
        total = path_len(P)[-1]
        for _ in range(branches):
            i = rng.randint(int(len(P) * 0.12), int(len(P) * 0.88))
            d = P[min(i + 2, len(P) - 1)] - P[max(i - 2, 0)]
            ang = math.atan2(d[1], d[0]) + math.radians(rng.uniform(*bang)) * rng.choice((-1, 1))
            ln = total * rng.uniform(*blen)
            e = P[i] + np.array((math.cos(ang), math.sin(ang))) * ln
            if box is not None:
                e = np.array((min(max(e[0], box[0]), box[2]), min(max(e[1], box[1]), box[3])))
            sub = crack_tree(rng, P[i], e, hw[i] * 0.6, rough, max(4, levels - 1), max(1, branches - 1), depth - 1, blen, bang,
                             ln * 0.3, box)
            sub[0] = (sub[0][0], width_profile(rng, sub[0][0], hw[i] * 0.6, 0.0, 0.5, end0=0.8))
            out += sub
    return out


# ---------------------------------------------------------------------------------------------- voronoi
def voronoi(c, cell_m, seed, jitter=0.9, X=None, Y=None):
    """Jittered-grid Voronoi on (X, Y) metres: F1, F2, edge distance (to the bisector), random id of the nearest
    and second-nearest cell, and nearest seed position."""
    X = c.x if X is None else X
    Y = c.y if Y is None else Y
    T = 211
    tab = np.random.RandomState(seed % (2 ** 31 - 1)).rand(T, T, 3).astype(F32)
    gx = np.floor(X / cell_m).astype(np.int32)
    gy = np.floor(Y / cell_m).astype(np.int32)
    b1 = np.full(X.shape, 1e9, F32)
    b2 = np.full(X.shape, 1e9, F32)
    p1x = np.zeros(X.shape, F32)
    p1y = np.zeros(X.shape, F32)
    p2x = np.zeros(X.shape, F32)
    p2y = np.zeros(X.shape, F32)
    i1 = np.zeros(X.shape, F32)
    i2 = np.zeros(X.shape, F32)
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            cx, cy = gx + ox, gy + oy
            h = tab[cx % T, cy % T]
            sx = (cx + 0.5 + (h[..., 0] - 0.5) * jitter) * cell_m
            sy = (cy + 0.5 + (h[..., 1] - 0.5) * jitter) * cell_m
            d = (X - sx) ** 2 + (Y - sy) ** 2
            n1 = d < b1
            n2 = (~n1) & (d < b2)
            # shift best -> second where a new best arrives
            b2 = np.where(n1, b1, np.where(n2, d, b2))
            p2x = np.where(n1, p1x, np.where(n2, sx, p2x))
            p2y = np.where(n1, p1y, np.where(n2, sy, p2y))
            i2 = np.where(n1, i1, np.where(n2, h[..., 2], i2))
            b1 = np.where(n1, d, b1)
            p1x = np.where(n1, sx, p1x)
            p1y = np.where(n1, sy, p1y)
            i1 = np.where(n1, h[..., 2], i1)
    ex, ey = p2x - p1x, p2y - p1y
    el = np.sqrt(ex * ex + ey * ey) + 1e-9
    edge = np.abs(((X - (p1x + p2x) * 0.5) * ex + (Y - (p1y + p2y) * 0.5) * ey) / el)
    pair = np.mod(np.sin((i1 + i2) * 91.7 + i1 * i2 * 47.3) * 43758.5453, 1.0).astype(F32)
    return {"F1": np.sqrt(b1), "F2": np.sqrt(b2), "edge": edge.astype(F32), "id": i1, "id2": i2, "pair": pair,
            "sx": p1x, "sy": p1y}


# ---------------------------------------------------------------------------------------------- vertical flow
def drip_down(src, decay_px, gain=1.0):
    """Smear a source downward (toward row 0): out[y] = sum_{r>=0} src[y+r] k^r (1-k)."""
    k = math.exp(-1.0 / max(decay_px, 1.0))
    out = np.empty_like(src)
    acc = np.zeros(src.shape[1], F32)
    for i in range(src.shape[0] - 1, -1, -1):
        acc = acc * k + src[i]
        out[i] = acc
    return out * (1 - k) * gain


# ============================================================================================== glyphs
def glyph_strokes(rng):
    """Stroke list for one invented glyph (unit box), same grammar as matdefs_hd.glyph(): roof bar, two stems,
    enclosure box or crossing diagonals, mid bar, 1-2 ticks, optional dot. Returns (segments, dot or None)."""
    S = []
    top = rng.uniform(0.78, 0.9)
    S.append((rng.uniform(0.08, 0.2), top, rng.uniform(0.8, 0.92), top))
    xs = sorted(rng.sample([0.22, 0.38, 0.5, 0.62, 0.78], 2))
    for x in xs:
        S.append((x, rng.uniform(0.05, 0.3), x, rng.uniform(0.6, top)))
    if rng.random() < 0.6:
        x0, x1 = rng.uniform(0.15, 0.35), rng.uniform(0.65, 0.85)
        y0, y1 = rng.uniform(0.1, 0.3), rng.uniform(0.45, 0.62)
        S += [(x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)]
    else:
        S.append((rng.uniform(0.1, 0.3), rng.uniform(0.1, 0.3), rng.uniform(0.55, 0.9), rng.uniform(0.45, 0.7)))
        S.append((rng.uniform(0.55, 0.9), rng.uniform(0.05, 0.25), rng.uniform(0.15, 0.45), rng.uniform(0.5, 0.7)))
    mid = rng.uniform(0.38, 0.6)
    S.append((rng.uniform(0.05, 0.25), mid, rng.uniform(0.7, 0.95), mid + rng.uniform(-0.05, 0.05)))
    for _ in range(rng.randint(1, 2)):
        x, y = rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9)
        S.append((x, y, x + rng.uniform(-0.15, 0.15), y - rng.uniform(0.08, 0.15)))
    dot = (rng.uniform(0.15, 0.85), rng.uniform(0.15, 0.85)) if rng.random() < 0.5 else None
    return S, dot


def bridge_strokes(S, rng, gap=0.09, minlen=0.3):
    """Stencil bridges: split long strokes with a small gap so islands stay attached (stencil look)."""
    out = []
    for (ax, ay, bx, by) in S:
        ln = math.hypot(bx - ax, by - ay)
        if ln > minlen and rng.random() < 0.85:
            t = rng.uniform(0.35, 0.65)
            g = gap / ln / 2
            out.append((ax, ay, ax + (bx - ax) * (t - g), ay + (by - ay) * (t - g)))
            out.append((ax + (bx - ax) * (t + g), ay + (by - ay) * (t + g), bx, by))
        else:
            out.append((ax, ay, bx, by))
    return out


def glyph_sd(U, V, S, dot, stroke, sx=1.0, sy=1.0, square=False):
    """Signed distance (glyph units, scaled by sx/sy so strokes can be stretched) to a stroke set."""
    d = np.full(U.shape, 1e9, F32)
    for (ax, ay, bx, by) in S:
        if square:
            # butt-capped stroke: box along the segment
            cx, cy = (ax + bx) / 2 * sx, (ay + by) / 2 * sy
            ln = math.hypot((bx - ax) * sx, (by - ay) * sy)
            ang = math.atan2((by - ay) * sy, (bx - ax) * sx)
            d = np.minimum(d, sd_box(U * sx, V * sy, cx, cy, ln / 2 + stroke * 0.5, stroke * 0.5, ang))
        else:
            d = np.minimum(d, sd_seg(U * sx, V * sy, ax * sx, ay * sy, bx * sx, by * sy) - stroke * 0.5)
    if dot is not None:
        d = np.minimum(d, np.hypot(U * sx - dot[0] * sx, V * sy - dot[1] * sy) - stroke * 0.7)
    return d


def draw_glyph(c, M, x0, y0, w, h, rng, stroke=0.1, ang=0.0, bridges=False, square=False, strokes=None, soft=0.75,
               vthick=1.0):
    """Rasterise one invented glyph into M (max) inside the metre box (x0, y0, w, h), optionally rotated."""
    S, dot = strokes if strokes is not None else glyph_strokes(rng)
    if bridges:
        S = bridge_strokes(S, rng, gap=stroke * 0.9)
    pad = max(w, h) * 0.25
    sl = c.win(x0 - pad, y0 - pad, x0 + w + pad, y0 + h + pad)
    if sl is None:
        return S, dot
    X, Y = c.x[sl], c.y[sl]
    cx, cy = x0 + w / 2, y0 + h / 2
    lx, ly = rot(X, Y, cx, cy, ang)
    U = lx / w + 0.5
    V = ly / h + 0.5
    sd = glyph_sd(U, V, S, dot, stroke * min(w, h) / w, 1.0, h / w / vthick, square) * w  # metres (stretch along V)
    np.maximum(M[sl], cov(sd, c, soft), out=M[sl])
    return S, dot


def glyph_row(c, M, x0, y0, w, h, n, rng, stroke=0.11, gap=0.18, ang=0.0, **kw):
    """n glyphs left to right in the box (rotation about the box centre)."""
    cw = w / n
    cx, cy = x0 + w / 2, y0 + h / 2
    ca, sa = math.cos(ang), math.sin(ang)
    for i in range(n):
        lx = -w / 2 + cw * (i + 0.5)
        gx, gy = cx + lx * ca, cy + lx * sa
        gw = cw * (1 - gap)
        draw_glyph(c, M, gx - gw / 2, gy - h / 2, gw, h, rng, stroke, ang, **kw)


def greek_lines(c, M, x0, y0, w, h, rows, rng, ang=0.0, fill=0.9, thick=0.55):
    """'Greeked' small print: rows of rounded word blocks of random length (reads as text, contains no letters)."""
    lh = h / rows
    cx, cy = x0 + w / 2, y0 + h / 2
    sl = c.win(cx - w, cy - h, cx + w, cy + h)
    if sl is None:
        return
    X, Y = c.x[sl], c.y[sl]
    lx, ly = rot(X, Y, cx, cy, ang)
    acc = np.zeros(X.shape, F32)
    for r in range(rows):
        yc = h / 2 - lh * (r + 0.5)
        x = -w / 2
        end = w / 2 - (rng.uniform(0, w * 0.45) if r == rows - 1 or rng.random() < 0.2 else 0)
        while x < end:
            ln = min(rng.uniform(0.04, 0.16) * w, end - x)
            if ln > lh * 0.4:
                d = sd_box(lx, ly, x + ln / 2, yc, ln / 2, lh * thick / 2, 0.0, lh * thick * 0.3)
                acc = np.maximum(acc, cov(d, c, 0.6) * rng.uniform(0.75, 1.0))
            x += ln + lh * 0.45
    np.maximum(M[sl], acc * fill, out=M[sl])


# ============================================================================================== layer stack
class Stack:
    """Premultiplied layer compositor: colour, smoothness, metallic and AO are 'over'-blended by coverage;
    height is additive (metres)."""

    def __init__(self, c):
        self.c = c
        self.A = c.zeros()
        self.C = np.zeros((c.H, c.W, 3), F32)
        self.S = c.zeros()
        self.M = c.zeros()
        self.O = c.zeros()
        self.h = c.zeros()
        self.nstrength = 1.0
        self.ao_radii = (0.003, 0.01, 0.03)
        self.ao_strength = 1.0

    def add(self, a, col, sm=0.5, mt=0.0, ao=1.0, h=None):
        a = np.clip(np.asarray(a, F32), 0.0, 1.0)
        if a.ndim == 0:
            a = np.full(self.A.shape, float(a), F32)
        k = 1.0 - a
        col = np.asarray(col, F32)
        self.C = self.C * k[..., None] + (col if col.ndim == 3 else col[None, None, :]) * a[..., None]
        self.S = self.S * k + np.asarray(sm, F32) * a
        self.M = self.M * k + np.asarray(mt, F32) * a
        self.O = self.O * k + np.asarray(ao, F32) * a
        self.A = self.A * k + a
        if h is not None:
            self.h += h

    def tint(self, mask, mul=None, col=None, amount=1.0):
        """Modify existing colour without changing coverage: multiply and/or mix toward col."""
        m = np.clip(np.asarray(mask, F32) * amount, 0, 1)
        if mul is not None:
            self.C = self.C * (1 - m[..., None] * (1 - np.asarray(mul, F32)))
        if col is not None:
            self.C = self.C + (np.asarray(col, F32)[None, None, :] * self.A[..., None] - self.C) * m[..., None]

    def set_sm(self, mask, val):
        m = np.clip(np.asarray(mask, F32), 0, 1)
        self.S = self.S + (np.asarray(val, F32) * self.A - self.S) * m

    def set_mt(self, mask, val):
        m = np.clip(np.asarray(mask, F32), 0, 1)
        self.M = self.M + (np.asarray(val, F32) * self.A - self.M) * m

    def mul_ao(self, mask, val):
        m = np.clip(np.asarray(mask, F32), 0, 1)
        self.O = self.O * (1 - m * (1 - val))

    def result(self):
        A = np.maximum(self.A, 1e-5)
        return {"col": np.clip(self.C / A[..., None], 0, 1), "a": np.clip(self.A, 0, 1), "sm": np.clip(self.S / A, 0, 1),
                "mt": np.clip(self.M / A, 0, 1), "ao": np.clip(self.O / A, 0, 1), "h": self.h}


# ============================================================================================== shared materials
def ground_micro(c, scale=1.0):
    """Small-scale ground relief (std ~1): asphalt / concrete grain the shorelines and stain edges follow."""
    return fbm(c, 0.06 * scale, 4, 0.55) * 0.6 + fbm(c, 0.018 * scale, 3, 0.5) * 0.4


def speckle(c, density, size_px=1.0, seed=None):
    """Sparse random dots (0..1), `density` = fraction of pixels that are dot centres."""
    w = white(c, seed)
    d = (w < density).astype(F32)
    if size_px > 0.6:
        d = np.clip(blur(d, size_px) * (2 * math.pi * size_px ** 2) * 0.8, 0, 1)
    return d


def aggregate(c, cell=0.009, seed=None):
    """Asphalt / concrete aggregate: domed stones (0..1 height) and their ids."""
    v = voronoi(c, cell, c.s() if seed is None else seed, 0.95)
    dome = np.clip(1.0 - v["F1"] / (cell * 0.62), 0, 1) ** 0.5 * np.clip(v["edge"] / (cell * 0.12), 0, 1)
    return dome.astype(F32), v["id"]


def thin_film(t_nm):
    """Thin-film interference colour (oil on water) for thickness in nm -> RGB 0..1 (grey 0.5 = no tint)."""
    lam = np.array((640.0, 545.0, 465.0), F32)
    ph = 4 * math.pi * 1.45 * t_nm[..., None] / lam
    r = 0.5 - 0.5 * np.cos(ph)
    k = np.exp(-t_nm / 1400.0)[..., None]
    return np.clip(0.5 + (r - 0.5) * k * 1.4, 0, 1)


# ============================================================================================== PUDDLES
def _puddle_core(c, p, st=None):
    """Standing water: organic lobed basin (domain-warped), shoreline following the ground micro-relief.
    Returns (stack, fields)."""
    st = st or Stack(c)
    size = min(c.wm, c.hm)
    wamp = p.get("warp", 0.1) * size
    wx = c.x + fbm(c, size * 0.45, 3, 0.5) * wamp
    wy = c.y + fbm(c, size * 0.45, 3, 0.5) * wamp
    basin = c.full(-3.0)
    for (fx, fy, rx, ry, ang) in p["lobes"]:
        lx, ly = rot(wx, wy, fx * c.wm, fy * c.hm, math.radians(ang))
        b = 1.0 - (lx / (rx * c.wm)) ** 2 - (ly / (ry * c.hm)) ** 2
        k = 0.4
        hh = np.clip(0.5 + 0.5 * (b - basin) / k, 0, 1)
        basin = b * hh + basin * (1 - hh) + k * hh * (1 - hh)  # smooth max
    basin = basin + fbm(c, size * 0.25, 3, 0.5) * p.get("irreg", 0.1)
    micro = fbm(c, 0.14, 3, 0.5) * 0.7 + fbm(c, 0.03, 3, 0.55) * 0.3
    D = p.get("depth_mm", 9.0)
    depth = (D * np.minimum(basin, 1.2) + p.get("micro_mm", 0.6) * micro) * 0.001  # metres of water
    water = sst(depth, -0.00004, 0.00012)
    deep = sst(depth, 0.0004, 0.004)
    # damp rim (capillary film) and a wider faint damp halo
    rim_mm = 0.7 * (1 + 0.5 * fbm(c, 0.3, 2))
    damp = sst(depth, -np.maximum(rim_mm, 0.15) * 0.001, 0.0) * (1 - water)
    halo = sst(depth, -0.003, -0.0004) * (1 - water) * (0.6 + 0.4 * n01(fbm(c, 0.2, 3)))
    tide_lvl = -0.0009 + 0.0002 * fbm(c, 0.4, 2)
    tide = np.exp(-((depth - tide_lvl) / 0.00012) ** 2) * sst(fbm(c, 0.15, 3), -0.4, 0.5) * (1 - water)
    col_deep = L(p.get("deep", "#0a0c0f"))
    col_shallow = L(p.get("shallow", "#17181a"))
    silt = L("#2a261f")
    sed = n01(fbm(c, 0.3, 3), -1.5, 2.0)
    wcol = mixc(np.broadcast_to(col_shallow, (c.H, c.W, 3)).copy(), col_deep, deep)
    wcol = mixc(wcol, silt, (1 - deep) * sed * 0.35)
    st.add(halo * 0.32, L("#151515"), sm=0.55)
    st.add(damp * (0.55 + 0.2 * n01(fbm(c, 0.08, 3))), L("#101011"), sm=0.75)
    st.add(tide * 0.4, L("#3d3831"), sm=0.4)
    st.add(water * (0.82 + 0.14 * deep), wcol, sm=0.96 - 0.04 * (1 - deep))
    # thin dark line of grime collected at the waterline, and floating grit near the shore
    shore = np.exp(-(np.maximum(depth, 0) / 0.00025) ** 2) * water
    st.add(shore * 0.35, L("#0a0a0a"), sm=0.9)
    grit = speckle(c, 0.0008, 0.8) * sst(depth, 0.0016, 0.0002) * water
    st.add(grit * 0.7, L("#2a2622"), sm=0.4, h=grit * 0.0003)
    # meniscus: the water edge rounds over the last couple of millimetres; otherwise dead flat
    st.h += 0.0006 * sst(depth, 0.0, 0.0006) * water
    return st, {"depth": depth, "water": water, "deep": deep, "damp": damp}


def puddle(c, p):
    st, _ = _puddle_core(c, p)
    st.ao_radii = (0.004, 0.012)
    st.ao_strength = 0.4
    return st


def oil_rainbow_puddle(c, p):
    st, f = _puddle_core(c, p)
    depth, water = f["depth"], f["water"]
    # oil film: smooth marbled swirls (low-octave, domain-warped), concentrated toward the shore
    edge = np.exp(-np.maximum(depth, 0) / 0.0018)
    base = fbm(c, 0.6, 2, 0.4)
    sw = warp(c, warp(c, base, 0.12, 0.5, 2), 0.06, 0.3, 2)
    present = sst(sw * 0.5 + edge * 1.4, 0.55, 1.25) * water
    t = 180.0 + 420.0 * n01(warp(c, fbm(c, 0.35, 2, 0.4), 0.08, 0.4, 2), -1.8, 1.8) + 300.0 * (1 - edge)
    tf = thin_film(t.astype(F32))
    film = 0.035 + tf * 0.3
    st.add(present * 0.55, film, sm=0.95, mt=0.28 * present)
    # brown oily scum on the dry rim
    scum = sst(depth, -0.003, 0.0) * (1 - water) * sst(fbm(c, 0.15, 3), -0.2, 0.8)
    st.add(scum * 0.55, L("#17110c"), sm=0.75)
    st.ao_radii = (0.004, 0.012)
    st.ao_strength = 0.4
    return st


# ============================================================================================== OIL
def _oil_spots(c, st, spots, micro):
    """spots: (x, y, r, fresh 0..1, stretch_x, ang). Soft optical-density model: oil soaks into porous ground with
    a gradual edge (the pores make the outline slightly irregular), fresh pools are denser."""
    od = c.zeros()
    fresh_od = c.zeros()
    wob = fbm_cache(c, 0.12)
    fine = fbm_cache(c, 0.03)
    for (x, y, r, fresh, sx, ang) in spots:
        pad = r * 1.8 * max(sx, 1)
        res = stamp(c, x - pad, y - pad, x + pad, y + pad, lambda X, Y: rot(X, Y, x, y, ang))
        if res is None:
            continue
        sl, (lx, ly) = res
        d = np.hypot(lx / sx, ly) / r + wob[sl] * 0.16 + fine[sl] * 0.05 + micro[sl] * 0.03
        soft = 0.12 + 0.25 * (1 - fresh)
        prof = sst(d, 1.0 + soft * 0.4, 1.0 - soft) * (1.0 - 0.55 * np.clip(d, 0, 1) ** 1.5)
        pores = 0.7 + 0.5 * n01(wob[sl] * 0.5 + fine[sl] * 0.8, -1.5, 1.5)
        dens = prof * (0.55 + 1.6 * fresh) * pores
        rim = np.exp(-((d - 0.95) / 0.07) ** 2) * (0.25 * (1 - fresh))
        od[sl] += dens + rim
        fresh_od[sl] += dens * fresh
    return od, fresh_od


def fbm_cache(c, feat):
    cache = c.__dict__.setdefault("_cache", {})
    if feat not in cache:
        cache[feat] = fbm(c, feat, 4, 0.55)
    return cache[feat]


def _oil_finish(c, st, od, fresh_od):
    a = 1.0 - np.exp(-od * 1.3)
    fr = np.clip(fresh_od / np.maximum(od, 1e-4), 0, 1)
    dense = 1 - np.exp(-od * 0.8)
    col = mixc(np.broadcast_to(L("#3a2f25"), (c.H, c.W, 3)).copy(), L("#0d0b09"), dense)
    col = mixc(col, L("#060505"), fr * dense * 0.7)
    st.add(np.clip(a, 0, 0.96), col, sm=0.32 + 0.5 * fr * dense)
    # fresh oil fills the pores: slight levelling, faint gloss ripples
    st.h += -0.0002 * fr * dense
    return st


def oil_stain_a(c, p):
    rng = c.r
    st = Stack(c)
    micro = ground_micro(c)
    spots = []
    cx, cy = c.wm * 0.5, c.hm * 0.5
    for _ in range(4):  # old, wide, faded stains
        spots.append((cx + rng.gauss(0, 0.12), cy + rng.gauss(0, 0.1), rng.uniform(0.16, 0.3), rng.uniform(0.0, 0.2),
                      rng.uniform(1.0, 1.5), rng.uniform(0, TAU)))
    for _ in range(3):  # fresh pools
        spots.append((cx + rng.gauss(0, 0.08), cy + rng.gauss(0, 0.06), rng.uniform(0.05, 0.12), rng.uniform(0.7, 1.0),
                      rng.uniform(1.0, 1.4), rng.uniform(0, TAU)))
    for _ in range(26):  # drips and splatter
        a = rng.uniform(0, TAU)
        d = abs(rng.gauss(0, 0.22)) + 0.05
        spots.append((cx + math.cos(a) * d, cy + math.sin(a) * d * 0.8, rng.uniform(0.006, 0.03), rng.uniform(0.2, 1.0),
                      1.0, 0.0))
    od, fo = _oil_spots(c, st, spots, micro)
    _oil_finish(c, st, od, fo)
    st.ao_strength = 0.0
    return st


def oil_stain_b(c, p):
    """Drip trail from a parked vehicle plus a tyre track that rolled through the pool and smeared oil."""
    rng = c.r
    st = Stack(c)
    micro = ground_micro(c)
    spots = [(c.wm * 0.22, c.hm * 0.52, 0.17, 0.85, 1.3, 0.2), (c.wm * 0.2, c.hm * 0.5, 0.28, 0.1, 1.2, 0.5)]
    for k in range(9):
        spots.append((c.wm * (0.3 + 0.05 * k + rng.uniform(-0.02, 0.02)), c.hm * 0.52 + rng.gauss(0, 0.04),
                      rng.uniform(0.012, 0.04), rng.uniform(0.3, 0.9), 1.0, 0.0))
    od, fo = _oil_spots(c, st, spots, micro)
    # tyre track: band along +x, tread blocks, fading as the oil is used up
    y0 = c.hm * 0.42
    tw = 0.19
    across = np.abs(c.y - y0 - 0.02 * np.sin(c.x * 1.3)) / (tw / 2)
    band = sst(across, 1.0, 0.85)
    along = np.clip((c.x - c.wm * 0.2) / (c.wm * 0.68), 0, 1)
    fade = np.exp(-along * 2.6) * sst(c.x, c.wm * 0.12, c.wm * 0.24) * sst(c.x, c.wm * 0.94, c.wm * 0.86)
    lug = 0.5 + 0.5 * np.sin((c.x / 0.032 + np.abs(c.y - y0) / 0.05) * TAU)
    groove = sst(np.abs(np.abs(c.y - y0) - tw * 0.22), 0.004, 0.009)
    tread = sst(lug, 0.35, 0.6) * groove
    patchy = sst(fbm(c, 0.08, 4) + micro * 0.5, -0.8, 0.6)
    track = band * fade * (0.35 + 0.65 * tread) * patchy
    od += track * 1.6
    fo += track * 0.6
    _oil_finish(c, st, od, fo)
    st.ao_strength = 0.0
    return st


# ============================================================================================== CRACKS
def crack_render(c, st, paths, depth=0.008, spall=0.6, dirt=0.6, moss=0.0, wet=0.7, light="#6f6b64", pad=0.05,
                 hair=None, dirt_r=0.012):
    """Render crack paths (list of (P, hw)) with depth, spalled edges, dirt halo, optional moss."""
    rng = c.r
    S = c.full(pad)
    for P, hw in paths:
        draw_path(c, S, P, hw, pad)
    micro = ground_micro(c, 0.7)
    core = cov(S, c, 0.6)
    # spalling: chipped edges where a noise gate is high
    gate = sst(fbm(c, 0.08, 4), 0.1, 0.7)
    spw = (0.002 + 0.008 * gate) * spall * (1 + 0.35 * micro)
    spal = cov(S - spw, c, 0.7) * (1 - core) * (gate > 0.02)
    spal_d = (0.0012 + 0.0016 * n01(micro)) * spal
    dh = near(S, dirt_r, pad)
    dirt_a = dh * (0.45 + 0.35 * n01(fbm(c, 0.06, 4))) * dirt
    wide = near(S, dirt_r * 3.2, pad) * 0.26 * dirt * n01(fbm(c, 0.2, 3), -1, 2)
    st.add(wide, L("#24211d"), sm=0.3)
    st.add(dirt_a, L("#1b1916"), sm=0.35, ao=0.85)
    st.add(spal * 0.8, mixc(L(light), L("#3a3733"), 0.35 + n01(micro, -2, 2) * 0.5), sm=0.2, ao=0.7)
    inner = sst(-S, 0.0, 0.0015)
    st.add(core, mixc(L("#1a1714"), L("#070606"), inner), sm=0.35 + wet * 0.5 * inner, ao=0.12 + 0.5 * (1 - inner))
    h = -depth * sst(-S, -0.0002, 0.0018) - spal_d + 0.0003 * micro * dirt_a
    if moss > 0:
        mg = sst(fbm(c, 0.12, 4), 0.35, 0.9) * near(S, 0.006, pad)
        tuft = n01(fbm(c, 0.006, 3), -1.5, 1.5)
        mm = np.clip(mg * (0.5 + tuft) * moss, 0, 1)
        st.add(mm, mixc(L("#2e3a1a"), L("#4a5a24"), tuft), sm=0.3, ao=0.9)
        h += mm * 0.0015 * tuft
    if hair:
        Sh = c.full(0.01)
        for P, hw in hair:
            draw_path(c, Sh, P, hw, 0.01)
        hc = cov(Sh, c, 0.55) * (1 - core)
        st.add(hc * 0.85, L("#1b1916"), sm=0.4, ao=0.5)
        st.add(near(Sh, 0.003, 0.01) * 0.25, L("#26231f"), sm=0.3)
        h += -0.0015 * hc
    st.h += h
    return S


def crack_concrete_a(c, p):
    rng = c.r
    st = Stack(c)
    paths = crack_tree(rng, (c.wm * 0.12, c.hm * 0.36), (c.wm * 0.86, c.hm * 0.6), 0.0034, rough=0.2, levels=8,
                       branches=3, depth=2, maxdev=c.hm * 0.18, box=(c.wm * 0.08, c.hm * 0.08, c.wm * 0.92, c.hm * 0.92))
    hair = []
    for _ in range(6):
        a = (rng.uniform(0.2, 0.8) * c.wm, rng.uniform(0.2, 0.8) * c.hm)
        ang = rng.uniform(0, TAU)
        ln = rng.uniform(0.1, 0.3)
        b = (a[0] + math.cos(ang) * ln, a[1] + math.sin(ang) * ln)
        P = frac_path(rng, a, b, 0.25, 6)
        hair.append((P, width_profile(rng, P, 0.0007, 0.3, 0.3)))
    crack_render(c, st, paths, depth=0.009, spall=0.8, dirt=0.75, moss=0.5, hair=hair)
    st.ao_radii = (0.002, 0.006, 0.02)
    return st


def crack_concrete_b(c, p):
    """Long structural crack along a slab: wide, spalled, water in the bottom, moss tufts."""
    rng = c.r
    st = Stack(c)
    paths = crack_tree(rng, (c.wm * 0.07, c.hm * 0.47), (c.wm * 0.93, c.hm * 0.53), 0.0055, rough=0.16, levels=9,
                       branches=4, depth=2, blen=(0.06, 0.16), maxdev=c.hm * 0.16, box=(c.wm * 0.08, c.hm * 0.08, c.wm * 0.92, c.hm * 0.92))
    hair = []
    for P, hw in paths[:1]:
        for _ in range(10):
            i = rng.randint(10, len(P) - 10)
            ang = rng.uniform(0, TAU)
            ln = rng.uniform(0.04, 0.14)
            b = (P[i][0] + math.cos(ang) * ln, P[i][1] + math.sin(ang) * ln)
            Q = frac_path(rng, P[i], b, 0.3, 5)
            hair.append((Q, width_profile(rng, Q, 0.0008, 0.0, 0.6, end0=1.0)))
    crack_render(c, st, paths, depth=0.014, spall=1.4, dirt=0.9, moss=0.9, wet=1.0, hair=hair, dirt_r=0.016)
    st.ao_radii = (0.002, 0.008, 0.025)
    return st


def crack_concrete_c(c, p):
    """Impact star: crushed pit, radial cracks and concentric spider-web arcs."""
    rng = c.r
    st = Stack(c)
    cx, cy = c.wm * 0.5, c.hm * 0.5
    paths = []
    nrad = 8
    angs = sorted(rng.uniform(0, TAU) for _ in range(nrad))
    ends = []
    for a in angs:
        ln = rng.uniform(0.25, 0.52)
        s = (cx + math.cos(a) * 0.05, cy + math.sin(a) * 0.05)
        e = (cx + math.cos(a) * ln, cy + math.sin(a) * ln)
        P = frac_path(rng, s, e, 0.16, 7)
        paths.append((P, width_profile(rng, P, 0.0036, 0.0, 0.5, end0=1.0)))
        ends.append((a, P))
    for ring_r in (0.11, 0.2):
        for k in range(nrad):
            if rng.random() < 0.35:
                continue
            a0, P0 = ends[k]
            a1, P1 = ends[(k + 1) % nrad]
            if a1 < a0:
                a1 += TAU
            if a1 - a0 > 1.4:
                continue
            rr = ring_r * rng.uniform(0.85, 1.15)
            s = (cx + math.cos(a0) * rr, cy + math.sin(a0) * rr)
            e = (cx + math.cos(a1) * rr, cy + math.sin(a1) * rr)
            mid = ((a0 + a1) / 2)
            P = frac_path(rng, s, (cx + math.cos(mid) * rr * 1.04, cy + math.sin(mid) * rr * 1.04), 0.2, 5)
            Q = frac_path(rng, P[-1], e, 0.2, 5)
            P = np.concatenate([P, Q[1:]])
            paths.append((P, width_profile(rng, P, 0.0018, 0.2, 0.2)))
    S = crack_render(c, st, paths, depth=0.01, spall=1.0, dirt=0.7)
    # crushed pit: rubble cells, depression, pulverised dust
    r = np.hypot(c.x - cx, (c.y - cy) * 1.1)
    pit_r = 0.065 * np.maximum(1 + 0.25 * fbm(c, 0.05, 3), 0.4)
    pit = sst(r, pit_r, pit_r * 0.85)
    v = voronoi(c, 0.012, c.s(), 0.95)
    rub = np.clip(1 - v["F1"] / 0.009, 0, 1) ** 0.6 * sst(v["edge"], 0.0005, 0.0018)
    pcol = mixc(np.broadcast_to(L("#77736b"), (c.H, c.W, 3)).copy(), L("#a19c92"), v["id"][..., None] * np.ones(3, F32))
    pcol = mulc(pcol, 0.45 + 0.55 * rub)
    st.add(pit, pcol, sm=0.2, ao=0.55 + 0.4 * rub)
    dust = np.exp(-np.maximum(r - pit_r, 0) / 0.05) * (1 - pit) * 0.5 * n01(fbm(c, 0.04, 4), -1.5, 1.5)
    st.add(dust, L("#8b877f"), sm=0.12)
    st.h += pit * (-0.012 * sst(r, pit_r, 0.0) + rub * 0.004)
    st.ao_radii = (0.002, 0.008, 0.025)
    return st


def crack_asphalt_network(c, p):
    """Alligator (fatigue) cracking: warped Voronoi plates, a sealed tar snake, ravelled pothole starts."""
    rng = c.r
    st = Stack(c)
    cx, cy = c.wm * 0.5, c.hm * 0.5
    # fatigue region
    reg = 1 - ((c.x - cx) / (c.wm * 0.36)) ** 2 - ((c.y - cy) / (c.hm * 0.3)) ** 2 + fbm(c, 0.6, 3) * 0.35
    region = sst(reg, -0.05, 0.35)
    wx = c.x + fbm(c, 0.25, 3) * 0.035
    wy = c.y + fbm(c, 0.25, 3) * 0.035
    v = voronoi(c, 0.13, c.s(), 0.95, wx, wy)
    v2 = voronoi(c, 0.055, c.s(), 0.95, wx + fbm(c, 0.06, 3) * 0.006, wy + fbm(c, 0.06, 3) * 0.006)
    keep1 = (v["pair"] < 0.35 + 0.65 * region) & (reg > -0.35)
    keep2 = (v2["pair"] < 0.7 * region) & (region > 0.1)
    hw1 = 0.0022 * (0.6 + 0.6 * n01(fbm(c, 0.2, 3))) * np.clip(region + 0.3, 0, 1)
    hw2 = 0.0011 * (0.6 + 0.6 * n01(fbm(c, 0.2, 3))) * region
    S = np.where(keep1, v["edge"] - hw1, 0.05)
    S = np.minimum(S, np.where(keep2, v2["edge"] - hw2, 0.05)).astype(F32)
    # long longitudinal crack, half of it sealed with a tar snake
    P = frac_path(rng, (c.wm * 0.06, c.hm * 0.7), (c.wm * 0.94, c.hm * 0.62), 0.1, 9)
    hwp = width_profile(rng, P, 0.0035, 0.1, 0.1)
    S2 = c.full(0.06)
    draw_path(c, S2, P, hwp, 0.06)
    S = np.minimum(S, S2)
    micro = ground_micro(c)
    core = cov(S, c, 0.6)
    ravel = np.exp(-np.maximum(S, 0) / 0.004) * (1 - core) * sst(fbm(c, 0.05, 3), -0.4, 0.6)
    # plates: oxidised grey asphalt, each plate tilted a little
    plate = region * 0.32 * (1 - core)
    tone = v["id"]
    pcol = mixc(np.broadcast_to(L("#37373a"), (c.H, c.W, 3)).copy(), L("#4a4946"), tone[..., None] * np.ones(3, F32))
    st.add(plate * (0.6 + 0.4 * n01(fbm(c, 0.3, 3))), pcol, sm=0.45)
    st.add(ravel * 0.6, L("#5a5853"), sm=0.25)
    inner = sst(-S, 0.0, 0.0012)
    st.add(core, mixc(L("#141312"), L("#050505"), inner), sm=0.45 + 0.4 * inner, ao=0.2 + 0.5 * (1 - inner))
    tilt = ((v["id"] - 0.5) * (c.x - v["sx"]) + (v["id2"] - 0.5) * (c.y - v["sy"])) * 0.012
    st.h += region * (tilt + (v["id"] - 0.5) * 0.0008) - 0.006 * sst(-S, -0.0002, 0.0015)
    # pothole starts: a few plates gone, gravel base exposed
    hole = (v["id"] < 0.05) & (region > 0.5)
    hole = blur(hole.astype(F32), 1.0)
    hole = sst(hole - fbm(c, 0.02, 3) * 0.1, 0.35, 0.6)
    agg, aid = aggregate(c, 0.011)
    gcol = mixc(np.broadcast_to(L("#3d3a35"), (c.H, c.W, 3)).copy(), L("#6b665e"), (aid[..., None] * np.ones(3, F32)))
    gcol = mulc(gcol, 0.35 + 0.65 * agg)
    st.add(hole, gcol, sm=0.3, ao=0.4 + 0.5 * agg)
    st.h += hole * (-0.016 + agg * 0.005)
    # tar snake: glossy black sealant squeegeed over part of the long crack
    snake = c.full(0.08)
    n = len(P)
    i0, i1 = int(n * rng.uniform(0.05, 0.25)), int(n * rng.uniform(0.6, 0.85))
    Q = P[i0:i1]
    draw_path(c, snake, Q, np.full(len(Q), 0.018) * (1 + 0.25 * np.sin(np.arange(len(Q)) * 0.07)), 0.08)
    snake = snake + fbm(c, 0.03, 3) * 0.004
    tar = cov(snake, c, 0.8)
    st.add(tar, L("#0b0b0c"), sm=0.7, ao=1.0)
    st.h += tar * 0.0016 + tar * sst(-snake, 0.0, 0.006) * 0.0006
    st.ao_radii = (0.002, 0.008, 0.025)
    st.ao_strength = 0.8
    return st


# ============================================================================================== ROAD PAINT
def paint_finish(c, st, cov_paint, colour, p, sd=None, travel="y"):
    """Worn road paint over asphalt: aggregate peaks scuffed bare, chips, tyre-path wear, crazing, grime, beads."""
    rng = c.r
    agg, aid = aggregate(c, p.get("agg", 0.009))
    wear_big = fbm(c, p.get("wear_f", 0.35), 4, 0.55)
    wear_small = fbm(c, 0.03, 3, 0.5)
    track = p.get("track", 0.0)
    w = wear_big * p.get("wear_big", 0.35) + wear_small * 0.25 + agg * 1.0 + track * 2.4
    thr = p.get("wear_thr", 1.25)
    keep = sst(w, thr + 0.08, thr - 0.06)
    thin = sst(w, thr - 0.06, thr - 0.6)  # 1 = fully intact
    paint = cov_paint * keep * p.get("fade", 1.0)
    # crazing of the thick film
    v = voronoi(c, p.get("craze", 0.035), c.s(), 0.9, c.x + fbm(c, 0.05, 2) * 0.004, c.y + fbm(c, 0.05, 2) * 0.004)
    craze = sst(v["edge"], 0.0012, 0.0004) * sst(fbm(c, 0.3, 3), 0.0, 0.8)
    paint = paint * (1 - craze * 0.85)
    col = np.broadcast_to(L(colour), (c.H, c.W, 3)).copy()
    col = mulc(col, 0.88 + 0.12 * n01(wear_small) - 0.18 * (1 - thin))
    # tyre / shoe grime streaks along the travel direction
    if travel == "y":
        streak = fbm(c, 0.6, 4, 0.55, ax=0.4, ay=6.0)
    else:
        streak = fbm(c, 0.6, 4, 0.55, ax=6.0, ay=0.4)
    grime = sst(streak, 0.0, 1.8) * 0.6 + sst(fbm(c, 0.12, 4), 0.4, 1.6) * 0.4
    col = mixc(col, L("#3a3631"), np.clip(grime * p.get("grime", 0.55), 0, 0.85))
    col = mixc(col, L("#25221e"), (1 - agg) * 0.18)  # dirt sits between the stones
    st.add(np.clip(paint * (0.55 + 0.45 * thin), 0, 1), col, sm=p.get("sm", 0.5) - 0.12 * grime, ao=0.95)
    # retroreflective glass beads: sparse glints
    beads = speckle(c, 0.004, 0.6) * paint
    st.set_sm(beads, 0.9)
    # overspray beads just outside the edge
    if sd is not None:
        osp = speckle(c, 0.0035, 0.7) * np.exp(-np.maximum(sd, 0) / 0.004) * (sd > 0) * (sd < 0.02) * p.get("fade", 1.0)
        st.add(osp * 0.7, col, sm=0.45)
    st.h += paint * (0.0011 + agg * 0.0012) - craze * paint * 0.0005 + (1 - paint) * cov_paint * agg * 0.0008
    return paint


def _ends(c, x, ramp=0.35, gap=0.04):
    """Ragged fade at both ends of a long marking (decals overlap end-to-end by ~ramp)."""
    e = np.minimum(x - gap, c.wm - gap - x) / ramp
    return np.clip(sst(e + fbm(c, 0.08, 3) * 0.18, 0.15, 0.85), 0, 1)


def roadline_solid(c, p):
    st = Stack(c)
    y0 = c.hm * 0.5 + 0.004 * np.sin(c.x * 0.8)
    sd = np.abs(c.y - y0) - 0.075 + fbm(c, 0.02, 2) * 0.0006
    cv = cov(sd, c, 0.7) * _ends(c, c.x)
    p = dict(p, track=sst(fbm(c, 1.2, 2, ax=4.0, ay=0.3), 0.4, 1.4) * 0.35)
    paint_finish(c, st, cv, p.get("colour", "#d9a21c"), p, sd, travel="x")
    st.add(np.exp(-np.maximum(sd, 0) / 0.04) * 0.18 * _ends(c, c.x), L("#26241f"), sm=0.4)
    st.ao_radii = (0.002, 0.006)
    st.ao_strength = 0.5
    return st


def roadline_dashed(c, p):
    st = Stack(c)
    x0, x1 = c.wm * 0.5 - 1.5, c.wm * 0.5 + 1.5
    sd = np.maximum(np.abs(c.y - c.hm * 0.5) - 0.075, np.abs(c.x - c.wm * 0.5) - 1.5)
    sd = sd + fbm(c, 0.02, 2) * 0.0006
    cv = cov(sd, c, 0.7)
    p = dict(p, track=sst(np.abs(c.x - c.wm * 0.5) / 1.5, 0.75, 1.0) * 0.45 + sst(fbm(c, 0.8, 2), 0.8, 1.6) * 0.3)
    paint_finish(c, st, cv, p.get("colour", "#d6d3cb"), p, sd, travel="x")
    st.add(np.exp(-np.maximum(sd, 0) / 0.05) * 0.16, L("#26241f"), sm=0.4)
    st.ao_radii = (0.002, 0.006)
    st.ao_strength = 0.5
    return st


def crosswalk_faded(c, p):
    """Zebra bars (0.5 m wide, travel along +V), wheel paths worn through, ghost of an older misaligned paint job."""
    rng = c.r
    st = Stack(c)
    sd = c.full(1.0)
    ghost = c.full(1.0)
    fades = c.full(1.0)
    for k in range(4):
        cx = 0.5 + k * 1.0 + rng.uniform(-0.015, 0.015)
        hw = 0.25 + rng.uniform(-0.01, 0.01)
        b = sd_box(c.x, c.y, cx, c.hm / 2, hw, c.hm / 2 - 0.22, math.radians(rng.uniform(-0.4, 0.4)), 0.012)
        sd = np.minimum(sd, b)
        fades = np.where(b < 0.05, rng.uniform(0.7, 1.0), fades)
        g = sd_box(c.x, c.y, cx + 0.17, c.hm / 2 + 0.06, 0.24, c.hm / 2 - 0.28, math.radians(1.2), 0.01)
        ghost = np.minimum(ghost, g)
    sd = sd + fbm(c, 0.02, 2) * 0.0008
    wheel = np.zeros_like(sd)
    for wx in (0.85, 2.55, 3.6):
        wheel = np.maximum(wheel, sst(np.abs(c.x - wx + fbm(c, 1.0, 2) * 0.03), 0.22, 0.06))
    ends = sst(np.minimum(c.y, c.hm - c.y) + fbm(c, 0.1, 3) * 0.05, 0.22, 0.4)
    p = dict(p, track=wheel * 0.75 + (1 - ends) * 0.3, fade=fades, wear_thr=1.3)
    gp = cov(ghost, c, 1.0) * (1 - cov(sd - 0.01, c)) * sst(fbm(c, 0.3, 4), 0.2, -0.6) * 0.22
    st.add(gp, L("#8c8a84"), sm=0.4)
    paint_finish(c, st, cov(sd, c, 0.7), p.get("colour", "#d6d3cb"), p, sd, travel="y")
    st.add(np.exp(-np.maximum(sd, 0) / 0.08) * 0.12 * (sd > 0), L("#25231f"), sm=0.45)
    st.ao_radii = (0.002, 0.006)
    st.ao_strength = 0.5
    return st


def road_arrow_stencil(c, p):
    """Straight-and-right lane arrow, elongated along +V (perspective-compensated like real markings)."""
    st = Stack(c)
    X, Y = c.x, c.y
    sx = c.wm * 0.36
    shaft = sd_box(X, Y, sx, 1.25, 0.075, 1.05)
    head = sd_poly(X, Y, [(sx - 0.25, 2.25), (sx + 0.25, 2.25), (sx, 3.75)])
    stem = sd_box(X, Y, sx, 2.2, 0.075, 0.08)
    # right turn branch along a quadratic curve
    t = np.linspace(0, 1, 40)
    p0, p1, p2 = np.array((sx, 0.95)), np.array((sx, 1.55)), np.array((sx + 0.6, 1.95))
    B = ((1 - t) ** 2)[:, None] * p0 + (2 * (1 - t) * t)[:, None] * p1 + (t ** 2)[:, None] * p2
    br = c.full(1.0)
    draw_path(c, br, B, np.full(len(B), 0.075), 1.0)
    dvec = p2 - p1
    dvec = dvec / np.linalg.norm(dvec)
    nvec = np.array((-dvec[1], dvec[0]))
    tip = p2 + dvec * 0.75
    rh = sd_poly(X, Y, [tuple(p2 + nvec * 0.22 - dvec * 0.05), tuple(p2 - nvec * 0.22 - dvec * 0.05), tuple(tip)])
    sd = np.minimum.reduce([shaft, head, stem, br, rh])
    sd = sd + fbm(c, 0.02, 2) * 0.0008
    wheel = sst(np.abs(c.x - sx - 0.1 + fbm(c, 1.0, 2) * 0.04), 0.25, 0.05) * 0.55
    p = dict(p, track=wheel, wear_thr=1.2)
    paint_finish(c, st, cov(sd, c, 0.7), p.get("colour", "#d6d3cb"), p, sd, travel="y")
    st.add(np.exp(-np.maximum(sd, 0) / 0.08) * 0.12 * (sd > 0), L("#25231f"), sm=0.45)
    st.ao_radii = (0.002, 0.006)
    st.ao_strength = 0.5
    return st


def road_glyph_stencil(c, p):
    """Two invented glyphs stretched 2x along the travel direction (+V), like painted road text, plus a bar."""
    rng = c.r
    st = Stack(c)
    M = c.zeros()
    gw, gh = 1.2, 1.45
    for k, y0 in enumerate((2.35, 0.75)):
        draw_glyph(c, M, (c.wm - gw) / 2, y0, gw, gh, rng, stroke=0.1, square=True, vthick=1.6)
    bar = sd_box(c.x, c.y, c.wm / 2, 0.42, 0.62, 0.07)
    M = np.maximum(M, cov(bar, c, 0.7))
    wheel = sst(np.abs(c.x - c.wm * 0.5 - 0.45 + fbm(c, 1.0, 2) * 0.04), 0.22, 0.04) * 0.6
    p = dict(p, track=wheel, wear_thr=1.2)
    paint_finish(c, st, M, p.get("colour", "#d6d3cb"), p, None, travel="y")
    osp = speckle(c, 0.0035, 0.7) * sst(blur(M, 3.0), 0.03, 0.3) * (1 - M)
    st.add(osp * 0.7, L("#cfccc4"), sm=0.45)
    st.add(sst(blur(M, 20), 0.02, 0.3) * 0.12 * (1 - M), L("#25231f"), sm=0.45)
    st.ao_radii = (0.002, 0.006)
    st.ao_strength = 0.5
    return st


# ============================================================================================== WALL STREAKS
PAL_GRIME = {"near": "#1d1b17", "far": "#2f2b25", "line": "#121110", "effl": "#c4beb0", "algae": "#1c2516"}
PAL_RUST = {"near": "#4a220c", "far": "#8c5a28", "line": "#3a1a0b", "effl": None, "algae": None}


def streak_bands(c, st, sources, pal, length, width=(0.02, 0.1), alpha=0.8, lines=10, algae=0.0, effl=0.0,
                 wet=0.5, line_w=0.0018, spread=0.35):
    """Photo-style run-off staining: for each source (x, y_top) a soft vertical band, darkest where the water leaves
    the surface, narrowing and fading with its own length; turbulent edges and fine vertical striation; plus a few
    sharp drip lines, algae tint near the source and white efflorescence."""
    rng = c.r
    acc = c.zeros()
    srcz = c.zeros()
    wob = fbm(c, 0.35, 3, 0.5, ax=0.6, ay=3.0)
    for (x0, y0) in sources:
        w0 = rng.uniform(*width)
        ln = length * rng.uniform(0.3, 1.0)
        inten = rng.uniform(0.45, 1.0)
        decay = rng.uniform(1.4, 2.8)
        drift = rng.uniform(-spread, spread) * w0
        sl = c.win(x0 - w0 * 3.5 - abs(drift), y0 - ln * 1.6, x0 + w0 * 3.5 + abs(drift), y0 + 0.03)
        if sl is None:
            continue
        X, Y = c.x[sl], c.y[sl]
        d = np.clip((y0 - Y) / ln, 0, None)
        xc = x0 + wob[sl] * w0 * 0.45 + d * drift
        w = w0 * (1.0 - 0.5 * np.clip(d, 0, 1.2)) + 0.002
        prof = np.exp(-((X - xc) / w) ** 2 * 1.3)
        along = np.exp(-d * decay) * sst(Y, y0 + 0.006, y0 - 0.012) * sst(d, 1.5, 1.0)
        v = inten * prof * along
        acc[sl] = 1 - (1 - acc[sl]) * (1 - v)
        srcz[sl] = np.maximum(srcz[sl], prof * sst(d, 0.12, 0.0) * sst(Y, y0 + 0.006, y0 - 0.01))
    stri = n01(fbm(c, 0.5, 5, 0.6, ax=0.2, ay=7.0), -1.8, 1.8)
    stri2 = n01(fbm(c, 0.1, 3, 0.6, ax=0.2, ay=8.0), -1.8, 1.8)
    edge = n01(fbm(c, 0.03, 3), -2, 2)
    a = np.clip(acc * (0.35 + 0.55 * stri + 0.35 * stri2) * 1.25, 0, 1)
    a = a * sst(a + edge * 0.08, 0.04, 0.2)
    far = 1 - np.clip(acc * 1.4, 0, 1)
    col = mixc(np.broadcast_to(L(pal["near"]), (c.H, c.W, 3)).copy(), L(pal["far"]), far)
    st.add(a * alpha, col, sm=0.3 + wet * 0.3 * acc)
    front = np.clip(acc * (1 - acc) * 4, 0, 1) * sst(stri2, 0.5, 0.9) * 0.25
    st.add(front, L(pal["line"]), sm=0.35)
    if lines:
        S = c.full(0.01)
        for _ in range(lines):
            x0, y0 = sources[rng.randint(0, len(sources) - 1)]
            x0 += rng.uniform(-0.6, 0.6) * width[1]
            ln = length * rng.uniform(0.25, 0.9)
            P = frac_path(rng, (x0, y0), (x0 + rng.uniform(-0.01, 0.01), y0 - ln), 0.012, 6)
            draw_path(c, S, P, width_profile(rng, P, line_w * rng.uniform(0.5, 1.2), 0.02, 0.6, end0=0.8, wobble=0.6), 0.01)
        ln_ = cov(S, c, 0.9) * 0.75
        st.add(ln_, L(pal["line"]), sm=0.35 + wet * 0.4)
        st.h += ln_ * 0.0001
    if algae > 0 and pal.get("algae"):
        g = srcz * sst(fbm(c, 0.12, 4), -0.4, 0.8) * algae
        st.add(g * 0.75, L(pal["algae"]), sm=0.5)
    if effl > 0 and pal.get("effl"):
        e = srcz * sst(fbm(c, 0.05, 4), 0.4, 1.3) * effl
        e = np.maximum(e, sst(stri2, 0.82, 0.95) * acc * effl * 0.5)
        st.add(e * 0.6, L(pal["effl"]), sm=0.12, h=e * 0.0003)
    return acc


def leak_streak_a(c, p):
    """Water leaking from a short crack near the top: wet dark runs, algae at the crack, white mineral bloom."""
    rng = c.r
    st = Stack(c)
    top = c.hm * 0.86
    P = bound_path(frac_path(rng, (c.wm * 0.25, top + 0.03), (c.wm * 0.75, top - 0.02), 0.2, 7), 0.04)
    Sc = c.full(0.03)
    draw_path(c, Sc, P, width_profile(rng, P, 0.0018, 0.2, 0.2), 0.03)
    idx = sorted(rng.sample(range(int(len(P) * 0.1), int(len(P) * 0.9)), 7))
    src = [(P[i][0], P[i][1] - 0.002) for i in idx]
    streak_bands(c, st, src, PAL_GRIME, c.hm * 0.82, width=(0.012, 0.06), alpha=0.85, lines=9, algae=0.8, effl=0.6, wet=0.9)
    wet = near(Sc, 0.02, 0.03) * sst(fbm(c, 0.05, 3), -0.8, 0.5)
    st.add(wet * 0.6, L("#151412"), sm=0.7)
    crack = cov(Sc, c, 0.6)
    st.add(crack, L("#0c0b0a"), sm=0.6, ao=0.2, h=-0.004 * crack)
    st.ao_radii = (0.002, 0.008)
    st.ao_strength = 0.6
    return st


def leak_streak_b(c, p):
    """Curtain of run-off staining below a ledge / window sill (top edge = drip line)."""
    rng = c.r
    st = Stack(c)
    top = c.hm * 0.92
    xs = np.sort(np.array([rng.uniform(c.wm * 0.08, c.wm * 0.92) for _ in range(22)]))
    src = [(x, top + rng.uniform(-0.006, 0.006)) for x in xs]
    band = sst(top - c.y, 0.0, 0.004) * sst(top - c.y, 0.28, 0.0) * sst(np.minimum(c.x - c.wm * 0.06, c.wm * 0.94 - c.x), 0.0, 0.1)
    st.add(band * (0.25 + 0.3 * n01(fbm(c, 0.2, 3))), L("#24211c"), sm=0.3)
    streak_bands(c, st, src, PAL_GRIME, c.hm * 0.85, width=(0.015, 0.09), alpha=0.82, lines=14, algae=0.35, effl=0.35, wet=0.5)
    st.ao_radii = (0.002, 0.008)
    st.ao_strength = 0.5
    return st


def rust_streak_a(c, p):
    """Rust bleeding from an embedded steel anchor near the top."""
    rng = c.r
    st = Stack(c)
    bx, by = c.wm * 0.5, c.hm * 0.84
    r = np.hypot(c.x - bx, (c.y - by) * 1.1)
    rr = 0.026 * np.maximum(1 + 0.3 * fbm(c, 0.03, 3), 0.3)
    src = [(bx + rng.uniform(-0.022, 0.022), by - 0.012) for _ in range(7)]
    streak_bands(c, st, src, PAL_RUST, c.hm * 0.8, width=(0.014, 0.05), alpha=0.85, lines=6, wet=0.2, line_w=0.0013,
                 spread=0.5)
    haze = np.exp(-((c.x - bx) / (0.05 + 0.08 * np.clip((by - c.y) / c.hm, 0, 1))) ** 2) * sst(c.y, by, by - 0.05) * \
        sst(c.y, by - c.hm * 0.75, by - c.hm * 0.2) * n01(fbm(c, 0.3, 4, ax=0.3, ay=5.0), -1.5, 2)
    st.add(haze * 0.3, L("#6e3d1c"), sm=0.25)
    bloom = sst(r, rr * 2.0, rr * 0.5) * sst(fbm(c, 0.02, 3), -1.0, 0.4)
    st.add(bloom * 0.8, mixc(L("#7b3b16"), L("#3b1a0b"), sst(r, rr * 1.2, rr * 0.3)), sm=0.2)
    plate = cov(sd_box(c.x, c.y, bx, by, 0.016, 0.016, math.radians(rng.uniform(-8, 8)), 0.003), c)
    pit = n01(fbm(c, 0.006, 3))
    st.add(plate, mixc(L("#4a2210"), L("#8a4a1e"), pit), sm=0.18, mt=0.15, h=plate * (0.0015 + pit * 0.0008))
    st.ao_radii = (0.002, 0.008)
    st.ao_strength = 0.6
    return st


def rust_streak_b(c, p):
    """Spalled concrete exposing a corroded rebar near the top, rust run-off below it."""
    rng = c.r
    st = Stack(c)
    cy = c.hm * 0.8
    P = jag_poly(rng, c.wm * 0.5, cy, 0.3, 18, 0.18, sy=0.3)
    sd = sd_poly(c.x, c.y, P) + fbm(c, 0.04, 3) * 0.008
    cav = cov(sd, c, 0.8)
    micro = fbm(c, 0.02, 4)
    depth = 0.014 * sst(-sd, 0.0, 0.03) + 0.003 * micro * cav
    src = [(rng.uniform(c.wm * 0.3, c.wm * 0.7), cy - 0.035) for _ in range(9)]
    streak_bands(c, st, src, PAL_RUST, c.hm * 0.72, width=(0.012, 0.05), alpha=0.85, lines=6, wet=0.2, line_w=0.0012)
    ccol = mixc(L("#77736a"), L("#4d4a45"), n01(micro) * 0.8)
    st.add(cav, ccol, sm=0.2, ao=0.8)
    rim = cov(np.abs(sd) - 0.004, c) * sst(fbm(c, 0.03, 3), -0.2, 0.6)
    st.add(rim * 0.6, L("#8a857b"), sm=0.18)
    bars = c.zeros()
    bh = c.zeros()
    for yb, rb in ((cy + 0.012, 0.007), (cy - 0.03, 0.006)):
        dy = np.abs(c.y - yb - 0.003 * np.sin(c.x * 9))
        prof = np.sqrt(np.clip(1 - (dy / rb) ** 2, 0, 1))
        rib = 0.5 + 0.5 * np.sin((c.x + (c.y - yb) * 0.6) / 0.011 * TAU)
        inside = cav * sst(dy, rb, rb - 0.0012)
        bars = np.maximum(bars, inside)
        bh = np.maximum(bh, inside * (prof * rb + sst(rib, 0.6, 0.9) * 0.001))
    rp = n01(fbm(c, 0.008, 3))
    st.add(bars, mixc(L("#3c1b0b"), L("#8c4719"), rp * 0.8), sm=0.22, mt=0.1, ao=1.0)
    st.add(blur(bars, 4) * cav * (1 - bars) * 0.7, L("#5a2a10"), sm=0.25)
    st.h += -depth * (1 - bars) + bh - 0.014 * bars * 0.4
    st.ao_radii = (0.003, 0.01, 0.025)
    return st


def grime_base_wall(c, p):
    """Dirt band at the foot of a wall: splash-back, rising-damp tide lines, wet bottom, moss. Bottom edge = floor."""
    rng = c.r
    st = Stack(c)
    x = c.x
    band_h = 0.3 + 0.1 * fbm(c, 1.2, 3, ax=8, ay=0.2) + 0.04 * fbm(c, 0.25, 3, ax=4, ay=0.3)
    ends = sst(np.minimum(x, c.wm - x) + fbm(c, 0.15, 3) * 0.06, 0.04, 0.4)
    y = c.y
    g = sst(y, band_h + 0.12, band_h - 0.2) * (0.55 + 0.45 * n01(fbm(c, 0.2, 4)))
    st.add(g * 0.75 * ends, mixc(L("#3a352e"), L("#25221d"), sst(y, 0.3, 0.0)), sm=0.25)
    # splash-back dots (mud flung up by rain)
    dots = speckle(c, 0.006, 1.1) * np.exp(-y / 0.18) * sst(fbm(c, 0.3, 3), -0.8, 0.6)
    st.add(dots * 0.85 * ends, L("#2a251f"), sm=0.3)
    # rising-damp tide lines
    for k, base in enumerate((0.22, 0.34, 0.45)):
        ly = base + 0.035 * fbm(c, 0.6, 3, ax=6, ay=0.2) + 0.008 * fbm(c, 0.08, 2)
        line = np.exp(-((y - ly) / 0.0035) ** 2) * sst(fbm(c, 0.4, 3), -0.6, 0.4)
        under = sst(y, ly, ly - 0.08) * sst(y, ly - 0.25, ly - 0.08) * 0.25
        st.add(under * ends * (0.8 - 0.2 * k), L("#2e2a24"), sm=0.3)
        st.add(line * ends * (0.75 - 0.15 * k), L("#b9b3a5"), sm=0.12, h=line * 0.0002)
    # wet zone at the very bottom (rain splash), algae and moss tufts in the corner
    wetz = sst(y, np.maximum(0.12 + 0.05 * fbm(c, 0.4, 3), 0.03), 0.01)
    st.add(wetz * 0.7 * ends, L("#16140f"), sm=0.72)
    moss = sst(y, np.maximum(0.06 + 0.04 * fbm(c, 0.3, 3), 0.015), 0.0) * sst(fbm(c, 0.25, 4), 0.1, 0.9)
    tuft = n01(fbm(c, 0.006, 3))
    st.add(np.clip(moss * (0.5 + tuft), 0, 1) * ends, mixc(L("#24301a"), L("#465a26"), tuft), sm=0.35,
           h=moss * tuft * 0.0012)
    # vertical rain streaks from above fading into the band
    streak = sst(fbm(c, 0.5, 4, ax=0.2, ay=7.0), 0.6, 1.8) * sst(y, 0.75, 0.3)
    st.add(streak * 0.35 * ends, L("#2a2722"), sm=0.35)
    st.ao_radii = (0.002, 0.008)
    st.ao_strength = 0.4
    return st


# ============================================================================================== DAMAGE
def polar_noise(c, field, cx, cy, ang_rep=1, r_scale=0.2):
    """Sample a (periodic) fbm field in polar coordinates: features stretched radially."""
    th = np.arctan2(c.y - cy, c.x - cx)
    r = np.hypot(c.x - cx, c.y - cy)
    X = np.mod((th + math.pi) / TAU * ang_rep, 1.0) * (c.W - 1)
    Y = np.mod(r / c.px * r_scale, c.H - 1)
    return sample(field, X, Y)


def scorch_floor(c, p):
    """Blast mark on the ground: soot rays, crater, crazed char, shrapnel gouges, ash flecks."""
    rng = c.r
    st = Stack(c)
    cx, cy = c.wm * 0.5 + rng.uniform(-0.03, 0.03), c.hm * 0.5 + rng.uniform(-0.03, 0.03)
    r = np.hypot(c.x - cx, c.y - cy)
    ray = polar_noise(c, fbm(c, 0.08, 4, 0.6), cx, cy, 1, 0.12) * 0.6 + polar_noise(c, fbm(c, 0.3, 3), cx, cy, 1, 0.05) * 0.5
    blot = warp(c, fbm(c, 0.35, 4, 0.55), 0.06, 0.3, 3)
    R0 = p.get("R", 0.55) * (1 + 0.16 * ray + 0.14 * blot)
    soot = np.exp(-(r / R0) ** 2 * 1.7)
    soot = soot * (0.65 + 0.35 * n01(fbm(c, 0.1, 4))) + polar_noise(c, fbm(c, 0.03, 3), cx, cy, 2, 0.08) * 0.06 * soot
    soot = np.clip(soot * 1.2, 0, 1) * sst(soot, 0.03, 0.12)
    halo = sst(r / R0, 0.55, 0.95) * sst(r / R0, 1.6, 1.05) * (0.5 + 0.5 * n01(fbm(c, 0.2, 3)))
    st.add(halo * 0.22, L("#33291f"), sm=0.22)
    scol = mixc(np.broadcast_to(L("#2d2620"), (c.H, c.W, 3)).copy(), L("#090807"), sst(soot, 0.15, 0.85))
    st.add(soot * 0.97, scol, sm=0.1 + 0.08 * (1 - soot))
    # crazed char inside the core
    v = voronoi(c, 0.045, c.s(), 0.9, c.x + fbm(c, 0.05, 2) * 0.006, c.y + fbm(c, 0.05, 2) * 0.006)
    craze = sst(v["edge"], 0.0016, 0.0005) * sst(r, 0.42, 0.18)
    st.add(craze * 0.9, L("#030303"), sm=0.15, ao=0.4)
    # crater
    cr = 0.17 * (1 + 0.15 * fbm(c, 0.06, 3))
    crater = sst(r, cr, cr * 0.7)
    rub = n01(fbm(c, 0.01, 3))
    st.add(crater * 0.8, mixc(L("#24201c"), L("#4a4640"), rub * 0.5), sm=0.15)
    st.h += -0.008 * np.clip(1 - (r / cr) ** 2, 0, 1) + crater * rub * 0.0025 - craze * 0.0012
    # shrapnel gouges: fresh light chips pointing away from the centre
    S = c.full(0.01)
    for _ in range(36):
        a = rng.uniform(0, TAU)
        r0 = rng.uniform(0.12, 0.85)
        ln = rng.uniform(0.012, 0.07) * (1.3 - r0)
        P = np.array([(cx + math.cos(a) * r0, cy + math.sin(a) * r0), (cx + math.cos(a) * (r0 + ln), cy + math.sin(a) * (r0 + ln))])
        draw_path(c, S, P, np.array((rng.uniform(0.0015, 0.004), 0.0003)), 0.01)
    gouge = cov(S, c, 0.7)
    st.add(gouge, L("#8a857c"), sm=0.2, ao=0.6)
    st.h += -0.0018 * gouge
    # ash flecks, glassy melt beads, tiny metal fragments
    ash = speckle(c, 0.01, 0.7) * np.exp(-(r / 0.5) ** 2)
    st.add(ash * 0.8, L("#7a7670"), sm=0.08)
    melt = speckle(c, 0.0008, 1.3) * sst(r, 0.4, 0.1)
    st.add(melt, L("#141312"), sm=0.85, h=melt * 0.0006)
    metal = speckle(c, 0.0006, 0.9) * sst(r, 0.9, 0.2)
    st.add(metal, L("#5a5650"), sm=0.5, mt=0.85, h=metal * 0.0005)
    st.ao_radii = (0.002, 0.008, 0.03)
    st.ao_strength = 0.7
    return st


def scorch_wall(c, p):
    """Fire scorch on a wall: charred, blistered base and a turbulent soot plume rising in a V."""
    rng = c.r
    st = Stack(c)
    ox, oy = c.wm * 0.5, c.hm * 0.18
    wx = c.x + fbm(c, 0.35, 4) * 0.06
    wy = c.y + fbm(c, 0.35, 4) * 0.04
    dy = wy - oy
    w = 0.14 + 0.42 * np.maximum(dy, 0)
    lat = (wx - ox) / w
    rise = sst(dy, -0.12, 0.06) * np.exp(-np.maximum(dy, 0) / (c.hm * 0.55))
    plume = np.exp(-lat ** 2 * 1.3) * rise
    stri = n01(fbm(c, 0.4, 5, 0.6, ax=0.3, ay=5.0), -1.6, 1.6)
    plume = np.clip(plume * (0.6 + 0.6 * stri) * 1.35, 0, 1)
    plume = plume * sst(c.y, c.hm - 0.04, c.hm - 0.4)
    halo = np.clip(np.exp(-lat ** 2 * 0.45) * rise - plume, 0, 1) * 0.4
    st.add(halo, L("#4b3a28"), sm=0.25)
    pcol = mixc(np.broadcast_to(L("#2e2924"), (c.H, c.W, 3)).copy(), L("#0a0908"), sst(plume, 0.2, 0.9))
    st.add(plume * 0.96, pcol, sm=0.1)
    # charred base with blistered / flaking paint
    base = np.exp(-(((wx - ox) / 0.36) ** 2 + ((wy - oy) / 0.22) ** 2) * 1.5)
    base = sst(base + fbm(c, 0.06, 3) * 0.1, 0.12, 0.75)
    v = voronoi(c, 0.014, c.s(), 0.95, wx, wy)
    blister = np.clip(1 - v["F1"] / 0.009, 0, 1) ** 0.8 * (v["id"] < 0.4) * 0.6
    flake = ((v["id"] > 0.88) & (v["F1"] < 0.008)).astype(F32) * sst(fbm(c, 0.1, 3), 0.0, 0.8)
    st.add(base * 0.97, mixc(L("#0b0a09"), L("#1e1a17"), blister), sm=0.12, ao=0.85)
    st.add(base * flake * 0.8, L("#5d5850"), sm=0.25)
    st.h += base * (blister * 0.0025 - flake * 0.0006)
    ash = speckle(c, 0.004, 0.7) * base
    st.add(ash * 0.7, L("#6e6a64"), sm=0.08)
    st.ao_radii = (0.002, 0.008)
    st.ao_strength = 0.6
    return st


def bullet_holes(c, p):
    """Cluster of rifle impacts in concrete: jagged spall craters, deep holes, radial micro-cracks, dust, lead smear."""
    rng = c.r
    st = Stack(c)
    cx, cy = c.wm * 0.5, c.hm * 0.5
    CR = c.zeros()
    HO = c.zeros()
    DU = c.zeros()
    LE = c.zeros()
    Hh = c.zeros()
    Scr = c.full(0.01)
    holes = []
    while len(holes) < 13:
        x, y = cx + rng.gauss(0, 0.17), cy + rng.gauss(0, 0.13)
        if 0.12 < x / c.wm < 0.88 and 0.12 < y / c.hm < 0.88 and all(math.hypot(x - a, y - b) > 0.05 for a, b, _ in holes):
            holes.append((x, y, rng.random() < 0.15))
    for (x, y, gouge) in holes:
        rc = rng.uniform(0.013, 0.03)
        rh = rng.uniform(0.0035, 0.0055)
        ang = rng.uniform(0, TAU)
        sx = 2.6 if gouge else 1.0
        P = jag_poly(rng, x, y, rc, rng.randint(9, 14), 0.38, sx=sx, ang=ang)
        pad = rc * 4 * sx

        def f(X, Y):
            sd = sd_poly(X, Y, P)
            lx, ly = rot(X, Y, x, y, ang)
            r = np.hypot(lx / sx, ly)
            return sd, r
        res = stamp(c, x - pad, y - pad, x + pad, y + pad, f)
        if res is None:
            continue
        sl, (sd, r) = res
        crater = cov(sd, c)
        prof = np.clip(1 - r / (rc * 1.1), 0, 1) ** 1.3
        np.maximum(CR[sl], crater, out=CR[sl])
        Hh[sl] = np.minimum(Hh[sl], -crater * prof * (0.004 if gouge else 0.007))
        if not gouge:
            hole = cov(r - rh, c)
            np.maximum(HO[sl], hole, out=HO[sl])
            Hh[sl] = np.minimum(Hh[sl], -hole * 0.02)
            np.maximum(LE[sl], np.exp(-np.maximum(r - rh, 0) / 0.0025) * (1 - hole) * 0.8 * sst(r, rc, rc * 0.6), out=LE[sl])
        np.maximum(DU[sl], np.exp(-np.maximum(sd, 0) / (rc * 0.9)) * (1 - crater) * sst(r, rc * 3.6, rc * 2.4), out=DU[sl])
        for _ in range(rng.randint(2, 5)):
            a = rng.uniform(0, TAU)
            s0 = (x + math.cos(a) * rc * 0.8, y + math.sin(a) * rc * 0.8)
            ln = rng.uniform(0.02, 0.07)
            Q = frac_path(rng, s0, (s0[0] + math.cos(a) * ln, s0[1] + math.sin(a) * ln), 0.25, 5)
            draw_path(c, Scr, Q, width_profile(rng, Q, 0.0006, 0.0, 0.6, end0=1.0), 0.01)
    rub = n01(fbm(c, 0.004, 3))
    dn = n01(fbm(c, 0.03, 3))
    st.add(DU * 0.45 * (0.6 + 0.4 * dn), L("#a29e95"), sm=0.1)
    cr_col = mixc(L("#a8a49b"), L("#6f6b64"), rub)
    st.add(CR, cr_col, sm=0.15, ao=0.8)
    crk = cov(Scr, c, 0.55)
    st.add(crk * 0.9, L("#1a1816"), sm=0.3, ao=0.5)
    st.add(LE * (1 - HO) * 0.7 * CR, L("#55585c"), sm=0.45, mt=0.6)
    st.add(HO, L("#060606"), sm=0.2, ao=0.05)
    st.h += Hh + CR * rub * 0.0012 - crk * 0.0012
    st.ao_radii = (0.002, 0.006, 0.015)
    return st


# ============================================================================================== OBJECTS / LITTER
class Objs:
    """Painter's-algorithm object layer (later objects sit on top)."""

    def __init__(self, c):
        self.c = c
        self.A = c.zeros()
        self.C = np.zeros((c.H, c.W, 3), F32)
        self.S = c.zeros()
        self.M = c.zeros()
        self.H = c.zeros()

    def put(self, sl, a, col, sm=0.4, mt=0.0, h=0.0):
        a = np.clip(a, 0, 1).astype(F32)
        col = np.asarray(col, F32)
        if col.ndim == 1:
            col = col[None, None, :]
        self.C[sl] += (col - self.C[sl]) * a[..., None]
        self.S[sl] += (np.asarray(sm, F32) - self.S[sl]) * a
        self.M[sl] += (np.asarray(mt, F32) - self.M[sl]) * a
        under = self.H[sl]
        self.H[sl] = under * (1 - a) + (np.asarray(h, F32) + under * 0.7) * a
        self.A[sl] += (1 - self.A[sl]) * a

    def to_stack(self, st, shadow=0.55, shadow_px=3.0):
        sh = np.clip(blur(self.A, shadow_px) * 1.6, 0, 1) * (1 - self.A)
        st.add(sh * shadow, L("#0b0b0b"), sm=0.4, ao=0.35)
        st.add(self.A, self.C, sm=self.S, mt=self.M, ao=1.0, h=self.H)


def pebble(c, ob, rng, x, y, r, palette, wet=0.6):
    P = jag_poly(rng, x, y, r, rng.randint(9, 15), 0.22, sx=rng.uniform(0.7, 1.0), ang=rng.uniform(0, TAU))
    pad = r * 1.6
    sl = c.win(x - pad, y - pad, x + pad, y + pad)
    if sl is None:
        return
    X, Y = c.x[sl], c.y[sl]
    sd = sd_poly(X, Y, P)
    a = cov(sd, c)
    inner = np.clip(-sd / (r * 0.7), 0, 1)
    hgt = r * 0.55 * np.sqrt(1 - (1 - inner) ** 2)
    base = L(rng.choice(palette)) * rng.uniform(0.75, 1.15)
    spk = np.random.RandomState(rng.randint(0, 10 ** 6)).rand(*X.shape).astype(F32)
    col = base[None, None, :] * (0.85 + 0.3 * spk[..., None]) * (0.8 + 0.25 * inner[..., None])
    ob.put(sl, a, col, sm=wet + 0.15 * inner, h=hgt)


def shard(c, ob, rng, x, y, r, tint):
    P = jag_poly(rng, x, y, r, rng.randint(3, 5), 0.45, sx=rng.uniform(0.35, 1.0), ang=rng.uniform(0, TAU))
    pad = r * 1.6
    sl = c.win(x - pad, y - pad, x + pad, y + pad)
    if sl is None:
        return
    X, Y = c.x[sl], c.y[sl]
    sd = sd_poly(X, Y, P)
    a = cov(sd, c, 0.6)
    edge = sst(-sd, 0.0015, 0.0002)
    glint = sst(np.sin((X * 0.7 + Y) / max(r, 0.004) * rng.uniform(2, 5) + rng.uniform(0, 6)), 0.85, 1.0) * 0.35
    col = np.asarray(L(tint), F32)[None, None, :] * (1 + edge[..., None] * 2.5 + glint[..., None])
    ob.put(sl, a * 0.93, np.clip(col, 0, 1), sm=0.97, h=0.0012 + 0.0004 * (1 - edge))


def cig_butt(c, ob, rng, x, y):
    ang = rng.uniform(0, TAU)
    ln = rng.uniform(0.022, 0.032)
    rad = 0.0039 * rng.uniform(0.9, 1.15)
    pad = ln
    sl = c.win(x - pad, y - pad, x + pad, y + pad)
    if sl is None:
        return
    X, Y = c.x[sl], c.y[sl]
    lx, ly = rot(X, Y, x, y, ang)
    sd = sd_box(lx, ly, 0, 0, ln / 2, rad * rng.uniform(0.8, 1.1), 0, rad * 0.9)
    a = cov(sd, c, 0.6)
    t = lx / ln + 0.5
    prof = np.sqrt(np.clip(1 - (ly / rad) ** 2, 0, 1))
    spk = np.random.RandomState(rng.randint(0, 10 ** 6)).rand(*X.shape).astype(F32)
    filt = mixc(L("#c38d4f"), L("#8f5e2c"), (spk > 0.75).astype(F32) * 0.7)
    paper = L("#d4d0c6")
    ash = mixc(L("#2a2622"), L("#6a645d"), spk)
    col = mixc(mixc(filt, paper, sst(t, 0.6, 0.62)), ash, sst(t, 0.93, 0.97))
    col = mulc(col, 0.7 + 0.3 * prof)
    ob.put(sl, a, col, sm=0.35, h=prof * rad * 0.8)


def bottle_cap(c, ob, rng, x, y):
    R = 0.0135
    sl = c.win(x - R * 1.5, y - R * 1.5, x + R * 1.5, y + R * 1.5)
    if sl is None:
        return
    X, Y = c.x[sl], c.y[sl]
    th = np.arctan2(Y - y, X - x) + rng.uniform(0, 1)
    r = np.hypot(X - x, (Y - y) * rng.uniform(1.0, 1.25))
    re = R * (1 + 0.045 * np.cos(th * 21))
    a = cov(r - re, c, 0.6)
    rim = sst(r, R * 0.75, R * 0.95)
    paint = L(rng.choice(["#a3181c", "#1d4fa0", "#c79a2a", "#9a9a9a"]))
    chips = (np.random.RandomState(rng.randint(0, 10 ** 6)).rand(*X.shape) > 0.9).astype(F32) * rim
    col = mixc(mulc(np.broadcast_to(paint, X.shape + (3,)).copy(), 0.7 + 0.3 * (1 - rim)), L("#b9b9b6"), chips)
    ob.put(sl, a, col, sm=0.55, mt=0.75, h=0.002 * (0.6 + 0.4 * rim))


def wire(c, ob, rng, x, y):
    ang = rng.uniform(0, TAU)
    ln = rng.uniform(0.05, 0.16)
    e = (x + math.cos(ang) * ln, y + math.sin(ang) * ln)
    P = frac_path(rng, (x, y), e, 0.12, 4)
    t = np.linspace(0, 1, 40)
    idx = np.clip((t * (len(P) - 1)).astype(int), 0, len(P) - 1)
    P = P[idx]
    hw = rng.uniform(0.0014, 0.0026)
    S = c.full(0.01)
    draw_path(c, S, P, np.full(len(P), hw), 0.01)
    sl = c.win(min(x, e[0]) - 0.03, min(y, e[1]) - 0.03, max(x, e[0]) + 0.03, max(y, e[1]) + 0.03)
    if sl is None:
        return
    s = S[sl]
    a = cov(s, c, 0.6)
    prof = np.sqrt(np.clip(-s / hw, 0, 1))
    ins = L(rng.choice(["#a31a1a", "#1c3f9a", "#c9a21c", "#141414", "#1d7a3a", "#d0d0cc"]))
    X, Y = c.x[sl], c.y[sl]
    tip = np.minimum(np.hypot(X - x, Y - y), np.hypot(X - e[0], Y - e[1]))
    copper = sst(tip, 0.008, 0.005)
    col = mixc(mulc(np.broadcast_to(ins, X.shape + (3,)).copy(), 0.65 + 0.35 * prof), L("#c0703e"), copper)
    ob.put(sl, a, col, sm=0.45 + 0.15 * copper, mt=copper, h=prof * hw * (1 - 0.4 * copper))


def screw(c, ob, rng, x, y):
    R = rng.uniform(0.003, 0.0045)
    P = [(x + R * math.cos(k * TAU / 6 + 0.3), y + R * math.sin(k * TAU / 6 + 0.3)) for k in range(6)]
    sl = c.win(x - R * 2, y - R * 2, x + R * 2, y + R * 2)
    if sl is None:
        return
    X, Y = c.x[sl], c.y[sl]
    sd = sd_poly(X, Y, P)
    a = cov(sd, c, 0.6)
    slot = cov(np.minimum(np.abs(X - x), np.abs(Y - y)) - R * 0.12, c) * cov(np.hypot(X - x, Y - y) - R * 0.6, c)
    col = mixc(L("#8a8a88"), L("#2a2a2a"), slot)
    ob.put(sl, a, col, sm=0.5, mt=0.9, h=0.002 - slot * 0.001)


def pcb_bit(c, ob, rng, x, y):
    w, h = rng.uniform(0.025, 0.05), rng.uniform(0.018, 0.035)
    ang = rng.uniform(0, TAU)
    P = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    P = [(x + px * math.cos(ang) - py * math.sin(ang), y + px * math.sin(ang) + py * math.cos(ang)) for px, py in P]
    pad = max(w, h)
    sl = c.win(x - pad, y - pad, x + pad, y + pad)
    if sl is None:
        return
    X, Y = c.x[sl], c.y[sl]
    sd = sd_poly(X, Y, P) + (np.random.RandomState(rng.randint(0, 10 ** 6)).rand(*X.shape) - 0.5) * 0.0008
    a = cov(sd, c, 0.6)
    lx, ly = rot(X, Y, x, y, ang)
    tr = (np.abs(np.mod(ly / 0.0025, 1.0) - 0.5) < 0.12) & (np.mod(lx / 0.011 + np.floor(ly / 0.0025) * 0.37, 1.0) < 0.7)
    tr = tr.astype(F32)
    chip = cov(sd_box(lx, ly, rng.uniform(-w / 5, w / 5), rng.uniform(-h / 5, h / 5), w * 0.2, h * 0.18), c)
    col = mixc(mixc(L("#0f3a24"), L("#b38a3c"), tr * 0.8), L("#0c0c0d"), chip)
    ob.put(sl, a, col, sm=0.55 + 0.2 * tr, mt=tr * 0.9 * (1 - chip), h=0.0015 + chip * 0.0012)


def plastic_bit(c, ob, rng, x, y):
    r = rng.uniform(0.006, 0.02)
    P = jag_poly(rng, x, y, r, rng.randint(4, 7), 0.4, sx=rng.uniform(0.4, 1.0), ang=rng.uniform(0, TAU))
    sl = c.win(x - r * 2, y - r * 2, x + r * 2, y + r * 2)
    if sl is None:
        return
    X, Y = c.x[sl], c.y[sl]
    sd = sd_poly(X, Y, P)
    a = cov(sd, c, 0.6)
    col = L(rng.choice(["#1a1a1c", "#c2186b", "#0f8fa8", "#d8d4c8", "#3b3f46", "#c6a21a"])) * rng.uniform(0.6, 0.9)
    ob.put(sl, a, col, sm=0.45, h=0.0015 * sst(-sd, 0, 0.001))


def debris_base(c, st, ob, dust_a=0.35):
    """Fine grit and a faint dust film gathered around the placed objects (call after placing them)."""
    dens = np.clip(blur(ob.A, 0.06 / c.px) * 6.0, 0, 1)
    dust = dens * sst(fbm(c, 0.15, 4) + fbm(c, 0.03, 3) * 0.4, -0.6, 1.2) * sst(c.edge_dist(), 0.03, 0.2)
    grit = speckle(c, 0.012, 0.6) * sst(dens + fbm(c, 0.1, 3) * 0.2, 0.15, 0.6) * sst(c.edge_dist(), 0.03, 0.2)
    st.add(dust * dust_a, L("#3a352e"), sm=0.3)
    st.add(grit * 0.75, mixc(L("#4d483f"), L("#7d776c"), white(c)), sm=0.35, h=grit * 0.0005)
    return dust


def scatter(rng, c, n, cx, cy, sx, sy):
    pts = []
    while len(pts) < n:
        x, y = rng.gauss(cx, sx), rng.gauss(cy, sy)
        if 0.1 * c.wm < x < 0.9 * c.wm and 0.1 * c.hm < y < 0.9 * c.hm:
            pts.append((x, y))
    return pts


STONES = ["#6d6a65", "#8a857d", "#55524e", "#7a6d5e", "#9b968c", "#4a4642", "#6b5d4c"]


def debris_a(c, p):
    """Gravel, broken bottle glass, concrete crumbs, cigarette butts and grit drifted on wet ground."""
    rng = c.r
    st = Stack(c)
    ob = Objs(c)
    for (x, y) in scatter(rng, c, 260, c.wm * 0.5, c.hm * 0.5, c.wm * 0.2, c.hm * 0.18):
        r = 0.0025 + 0.012 * rng.random() ** 2.5
        pebble(c, ob, rng, x, y, r, STONES)
    bx, by = c.wm * 0.58, c.hm * 0.44
    tint = rng.choice(["#1f3d22", "#3a2410"])
    for k in range(60):
        a = rng.uniform(0, TAU)
        d = abs(rng.gauss(0, 0.12))
        r = 0.003 + 0.022 * rng.random() ** 2 * math.exp(-d * 3)
        shard(c, ob, rng, bx + math.cos(a) * d, by + math.sin(a) * d * 0.8, r, tint if rng.random() < 0.8 else "#7e8a8c")
    for (x, y) in scatter(rng, c, 4, c.wm * 0.45, c.hm * 0.55, c.wm * 0.18, c.hm * 0.15):
        cig_butt(c, ob, rng, x, y)
    bottle_cap(c, ob, rng, c.wm * 0.36, c.hm * 0.62)
    debris_base(c, st, ob, 0.3)
    ob.to_stack(st)
    st.ao_radii = (0.002, 0.006)
    st.ao_strength = 0.6
    return st


def debris_b(c, p):
    """Urban tech debris: cable offcuts with copper ends, screws, broken plastic, a circuit board fragment."""
    rng = c.r
    st = Stack(c)
    ob = Objs(c)
    for (x, y) in scatter(rng, c, 120, c.wm * 0.5, c.hm * 0.5, c.wm * 0.2, c.hm * 0.2):
        pebble(c, ob, rng, x, y, 0.002 + 0.006 * rng.random() ** 2, STONES)
    for (x, y) in scatter(rng, c, 30, c.wm * 0.5, c.hm * 0.5, c.wm * 0.16, c.hm * 0.16):
        plastic_bit(c, ob, rng, x, y)
    for (x, y) in scatter(rng, c, 9, c.wm * 0.5, c.hm * 0.5, c.wm * 0.14, c.hm * 0.14):
        wire(c, ob, rng, x, y)
    for (x, y) in scatter(rng, c, 2, c.wm * 0.5, c.hm * 0.5, c.wm * 0.1, c.hm * 0.1):
        pcb_bit(c, ob, rng, x, y)
    for (x, y) in scatter(rng, c, 14, c.wm * 0.5, c.hm * 0.5, c.wm * 0.15, c.hm * 0.15):
        screw(c, ob, rng, x, y)
    for k in range(25):
        x, y = rng.gauss(c.wm * 0.4, 0.06), rng.gauss(c.hm * 0.6, 0.05)
        shard(c, ob, rng, x, y, 0.002 + 0.008 * rng.random() ** 2, "#7e8a8c")
    for (x, y) in scatter(rng, c, 2, c.wm * 0.5, c.hm * 0.5, c.wm * 0.15, c.hm * 0.15):
        cig_butt(c, ob, rng, x, y)
    debris_base(c, st, ob, 0.3)
    ob.to_stack(st)
    st.ao_radii = (0.002, 0.006)
    st.ao_strength = 0.6
    return st


# ============================================================================================== PRINT (posters, flyers)
def shifted(c, feat, sl, rng):
    """Window of a cached canvas noise at a random offset (decorrelates sheets cheaply)."""
    f = fbm_cache(c, feat)
    dy, dx = rng.randint(0, c.H - 1), rng.randint(0, c.W - 1)
    rows = (np.arange(sl[0].start, sl[0].stop) + dy) % c.H
    cols = (np.arange(sl[1].start, sl[1].stop) + dx) % c.W
    return f[np.ix_(rows, cols)]


class Sheet:
    """A rotated sheet of print with local coordinates u, v in metres (0..w, 0..h) over its canvas window."""

    def __init__(self, c, cx, cy, w, h, ang=0.0, pad=0.03):
        self.c, self.cx, self.cy, self.w, self.h, self.ang = c, cx, cy, w, h, ang
        ca, sa = abs(math.cos(ang)), abs(math.sin(ang))
        ex, ey = 0.5 * (w * ca + h * sa) + pad, 0.5 * (w * sa + h * ca) + pad
        self.sl = c.win(cx - ex, cy - ey, cx + ex, cy + ey)
        X, Y = c.x[self.sl], c.y[self.sl]
        lx, ly = rot(X, Y, cx, cy, ang)
        self.u, self.v = lx + w / 2, ly + h / 2
        sh = self.u.shape
        self.col = np.zeros(sh + (3,), F32)
        self.cut = np.zeros(sh, F32)
        self.ink = np.zeros(sh, F32)  # where ink sits (glossier, for gloss variation)

    def sub(self, x0, y0, x1, y1, pad=0.004):
        ca, sa = math.cos(self.ang), math.sin(self.ang)
        xs, ys = [], []
        for (px, py) in ((x0 - pad, y0 - pad), (x1 + pad, y0 - pad), (x1 + pad, y1 + pad), (x0 - pad, y1 + pad)):
            lx, ly = px - self.w / 2, py - self.h / 2
            xs.append(self.cx + lx * ca - ly * sa)
            ys.append(self.cy + lx * sa + ly * ca)
        win = self.c.win(min(xs), min(ys), max(xs), max(ys))
        if win is None:
            return None
        a0, b0 = self.sl[0].start, self.sl[1].start
        i0, i1 = max(win[0].start, a0) - a0, min(win[0].stop, self.sl[0].stop) - a0
        j0, j1 = max(win[1].start, b0) - b0, min(win[1].stop, self.sl[1].stop) - b0
        if i0 >= i1 or j0 >= j1:
            return None
        return (slice(i0, i1), slice(j0, j1))

    def paint(self, m, colour, sb=None, ink=True):
        if sb is None:
            sb = (slice(None), slice(None))
        tgt = self.col[sb]
        tgt += (np.asarray(colour, F32) - tgt) * m[..., None]
        if ink:
            np.maximum(self.ink[sb], m, out=self.ink[sb])

    def fill(self, colour):
        self.col[:] = np.asarray(colour, F32)

    def vgrad(self, c0, c1, y0=0.0, y1=None):
        y1 = self.h if y1 is None else y1
        t = np.clip((self.v - y0) / (y1 - y0), 0, 1)[..., None]
        self.col[:] = np.asarray(c0, F32) * (1 - t) + np.asarray(c1, F32) * t

    def rect(self, x0, y0, x1, y1, colour, r=0.0, cut=False):
        sb = self.sub(x0, y0, x1, y1)
        if sb is None:
            return
        sd = sd_box(self.u[sb], self.v[sb], (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2, 0, r)
        m = cov(sd, self.c, 0.6)
        if cut:
            np.maximum(self.cut[sb], m, out=self.cut[sb])
        else:
            self.paint(m, colour, sb)

    def circle(self, x, y, r, colour, ring=0.0):
        sb = self.sub(x - r, y - r, x + r, y + r)
        if sb is None:
            return
        d = np.hypot(self.u[sb] - x, self.v[sb] - y) - r
        if ring > 0:
            d = np.abs(d + ring / 2) - ring / 2
        self.paint(cov(d, self.c, 0.6), colour, sb)

    def poly(self, P, colour):
        xs, ys = [p[0] for p in P], [p[1] for p in P]
        sb = self.sub(min(xs), min(ys), max(xs), max(ys))
        if sb is None:
            return
        self.paint(cov(sd_poly(self.u[sb], self.v[sb], P), self.c, 0.6), colour, sb)

    def glyph(self, x0, y0, w, h, rng, colour, stroke=0.12, bridges=False, strokes=None):
        S, dot = strokes if strokes is not None else glyph_strokes(rng)
        if bridges:
            S = bridge_strokes(S, rng, stroke * 0.9)
        sb = self.sub(x0, y0, x0 + w, y0 + h)
        if sb is None:
            return
        U = (self.u[sb] - x0) / w
        V = (self.v[sb] - y0) / h
        sd = glyph_sd(U, V, S, dot, stroke * min(w, h) / w, 1.0, h / w) * w
        self.paint(cov(sd, self.c, 0.65), colour, sb)

    def glyph_row(self, x0, y0, w, h, n, rng, colour, stroke=0.12, gap=0.16):
        cw = w / n
        for i in range(n):
            self.glyph(x0 + cw * i + cw * gap / 2, y0, cw * (1 - gap), h, rng, colour, stroke)

    def glyph_col(self, x0, y0, w, h, n, rng, colour, stroke=0.12, gap=0.16):
        ch = h / n
        for i in range(n):
            self.glyph(x0, y0 + h - ch * (i + 1) + ch * gap / 2, w, ch * (1 - gap), rng, colour, stroke)

    def greek(self, x0, y0, w, h, rows, rng, colour, thick=0.5):
        sb = self.sub(x0, y0, x0 + w, y0 + h)
        if sb is None:
            return
        u, v = self.u[sb], self.v[sb]
        acc = np.zeros(u.shape, F32)
        lh = h / rows
        for r in range(rows):
            yc = y0 + h - lh * (r + 0.5)
            x = x0
            end = x0 + w - (rng.uniform(0.1, 0.5) * w if (r == rows - 1 or rng.random() < 0.15) else 0)
            while x < end:
                ln = min(rng.uniform(0.04, 0.16) * w, end - x)
                if ln > lh * 0.4:
                    d = sd_box(u, v, x + ln / 2, yc, ln / 2, lh * thick / 2, 0, lh * thick * 0.25)
                    acc = np.maximum(acc, cov(d, self.c, 0.6))
                x += ln + lh * 0.5
        self.paint(acc, colour, sb)

    def halftone(self, x0, y0, x1, y1, tone, colour, cell=0.006, ang=0.6):
        sb = self.sub(x0, y0, x1, y1)
        if sb is None:
            return
        u, v = self.u[sb], self.v[sb]
        t = np.clip(tone(u, v), 0, 1)
        qa, qb = rot(u, v, 0.0, 0.0, ang)
        fa = np.mod(qa / cell, 1.0) - 0.5
        fb = np.mod(qb / cell, 1.0) - 0.5
        d = np.hypot(fa, fb) * cell - np.sqrt(t) * cell * 0.62
        box = cov(sd_box(u, v, (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2), self.c)
        self.paint(cov(d, self.c, 0.6) * box, colour, sb)


INK = L("#151417")
PAPER = L("#e4ded0")
POSTER_PALS = [("magenta", "cyan", "#12081c"), ("yellow", "blue", "#070a18"), ("violet", "pink", "#150620"),
               ("cyan", "yellow", "#04161a"), ("pink", "violet", "#1a0610"), ("blue", "magenta", "#05061a")]


def _pal(rng):
    a, b, bg = rng.choice(POSTER_PALS)
    return N(a) * 0.85, N(b) * 0.85, L(bg)


def art_gig(sh, rng):
    c1, c2, bg = _pal(rng)
    w, h = sh.w, sh.h
    sh.vgrad(bg, mixc(bg, c1, 0.3))
    cx, cy, R = w * rng.uniform(0.38, 0.62), h * rng.uniform(0.45, 0.6), min(w, h) * rng.uniform(0.26, 0.34)
    if rng.random() < 0.5:
        sh.circle(cx, cy, R, c2)
        sh.circle(cx, cy, R * 0.74, bg)
        sh.circle(cx + R * 0.18, cy - R * 0.12, R * 0.46, c1)
    else:
        sh.poly([(cx - R, cy - R * 0.8), (cx + R, cy - R * 0.8), (cx, cy + R * 0.95)], c2)
        sh.poly([(cx - R * 0.55, cy - R * 0.45), (cx + R * 0.55, cy - R * 0.45), (cx, cy + R * 0.5)], bg)
        sh.circle(cx, cy - R * 0.05, R * 0.18, c1)
    sh.halftone(0.0, 0.0, w, h * 0.42, lambda u, v: 0.9 - v / (h * 0.42), c1, cell=min(w, h) * 0.022)
    sh.glyph_row(w * 0.08, h * 0.79, w * 0.84, h * 0.13, rng.randint(3, 4), rng, L("#f2efe8"), 0.13)
    sh.glyph_row(w * 0.1, h * 0.14, w * 0.8, h * 0.045, rng.randint(6, 8), rng, c2, 0.12)
    sh.greek(w * 0.1, h * 0.04, w * 0.8, h * 0.07, 3, rng, L("#bdb8c4"))
    for (x0, y0, x1, y1) in ((0.03, 0.025, 0.97, 0.03), (0.03, 0.97, 0.97, 0.975), (0.03, 0.025, 0.035, 0.975),
                             (0.965, 0.025, 0.97, 0.975)):
        sh.rect(w * x0, h * y0, w * x1, h * y1, c1)


def art_flyer(sh, rng, tabs=True):
    w, h = sh.w, sh.h
    paper = L(rng.choice(["#e6e0d2", "#efe35a", "#ef72ad", "#a6e4ee", "#e8e8e2", "#f2a43a"]))
    sh.fill(paper)
    acc = rng.choice([N("magenta"), N("blue"), INK, N("violet")]) * 0.85
    sh.glyph_row(w * 0.08, h * 0.74, w * 0.84, h * 0.17, rng.randint(2, 3), rng, INK, 0.15)
    sh.rect(w * 0.06, h * 0.56, w * 0.94, h * 0.69, acc)
    sh.glyph_row(w * 0.12, h * 0.585, w * 0.76, h * 0.08, rng.randint(4, 6), rng, paper, 0.14)
    if rng.random() < 0.5:
        sh.circle(w * 0.76, h * 0.42, min(w, h) * 0.12, acc, ring=min(w, h) * 0.02)
        sh.glyph(w * 0.7, h * 0.36, w * 0.12, h * 0.12 * w / h, rng, acc, 0.16)
        sh.greek(w * 0.08, h * 0.3, w * 0.52, h * 0.2, 6, rng, INK)
    else:
        sh.greek(w * 0.08, h * 0.3, w * 0.84, h * 0.2, 6, rng, INK)
    if tabs:
        n = rng.randint(7, 10)
        tw = w / n
        top = h * 0.22
        for k in range(n):
            x0 = k * tw
            sh.rect(x0 + tw * 0.48, 0, x0 + tw * 0.52, top, mixc(paper, INK, 0.35))
            for j in range(3):
                sh.glyph(x0 + tw * 0.15, top * (0.12 + 0.28 * j), tw * 0.65, top * 0.24, rng, INK, 0.14)
            if rng.random() < 0.45:
                sh.rect(x0 + tw * 0.04, -0.01, x0 + tw * 0.96, top * rng.uniform(0.85, 1.0), None, cut=True)
        sh.rect(0, top - 0.0015, w, top + 0.0015, mixc(paper, INK, 0.5))
    else:
        sh.greek(w * 0.08, h * 0.06, w * 0.84, h * 0.18, 5, rng, INK)


def art_split(sh, rng):
    c1, c2, bg = _pal(rng)
    w, h = sh.w, sh.h
    t = (sh.u / w + sh.v / h * 0.7 > 0.95 + 0.0 * rng.random()).astype(F32)
    sh.col[:] = c1[None, None, :] * (1 - t[..., None]) + c2[None, None, :] * t[..., None]
    sh.col *= 0.9
    R = min(w, h) * 0.26
    sh.circle(w * 0.5, h * 0.58, R, bg)
    sh.circle(w * 0.5, h * 0.58, R * 1.08, bg, ring=R * 0.04)
    sh.glyph(w * 0.5 - R * 0.62, h * 0.58 - R * 0.62, R * 1.24, R * 1.24, rng, L("#f2efe8"), 0.15)
    sh.rect(0, h * 0.12, w, h * 0.26, bg)
    sh.glyph_row(w * 0.08, h * 0.14, w * 0.84, h * 0.1, rng.randint(4, 6), rng, c1, 0.13)
    sh.greek(w * 0.1, h * 0.03, w * 0.8, h * 0.07, 3, rng, bg)


def art_idol(sh, rng):
    c1, c2, bg = _pal(rng)
    w, h = sh.w, sh.h
    sh.vgrad(mixc(bg, c2, 0.45), mixc(bg, c1, 0.55))
    sh.circle(w * 0.55, h * 0.58, min(w, h) * 0.34, mixc(c1, L("#ffffff"), 0.15))
    sh.circle(w * 0.55, h * 0.58, min(w, h) * 0.3, mixc(bg, c1, 0.5))
    hx, hy = w * 0.55, h * 0.6
    for (ox, oy, rx, ry, col) in ((0, 0, 0.1, 0.13, c2), (0, -0.3, 0.26, 0.2, c2), (0, 0, 0.088, 0.118, bg),
                                  (0, -0.3, 0.245, 0.185, bg)):
        sb = sh.sub(hx - w * 0.3, hy - h * 0.55, hx + w * 0.3, hy + h * 0.2)
        if sb is None:
            continue
        d = np.hypot((sh.u[sb] - hx - ox * w) / (rx * w), (sh.v[sb] - hy - oy * h) / (ry * h)) - 1
        m = cov(d * min(rx * w, ry * h), sh.c, 0.7) * (sh.v[sb] > h * 0.08)
        sh.paint(m, col, sb)
    sh.glyph_col(w * 0.06, h * 0.2, w * 0.16, h * 0.72, rng.randint(4, 5), rng, L("#f2efe8"), 0.13)
    sh.glyph_row(w * 0.3, h * 0.05, w * 0.62, h * 0.06, rng.randint(5, 7), rng, c1, 0.12)
    sh.halftone(0, h * 0.75, w, h, lambda u, v: (v - h * 0.75) / (h * 0.25) * 0.7, c2, cell=min(w, h) * 0.02)


def art_notice(sh, rng):
    w, h = sh.w, sh.h
    sh.fill(L(rng.choice(["#ece8de", "#f1ecc8", "#dde6e8"])))
    sh.rect(0, h * 0.86, w, h, L("#2b2d33"))
    sh.glyph(w * 0.05, h * 0.875, h * 0.1, h * 0.1, rng, L("#f2efe8"), 0.14)
    sh.glyph_row(w * 0.3, h * 0.885, w * 0.62, h * 0.08, rng.randint(4, 6), rng, L("#f2efe8"), 0.13)
    sh.glyph_row(w * 0.08, h * 0.72, w * 0.6, h * 0.08, rng.randint(3, 4), rng, INK, 0.14)
    sh.greek(w * 0.08, h * 0.3, w * 0.4, h * 0.38, 11, rng, INK)
    sh.greek(w * 0.54, h * 0.3, w * 0.38, h * 0.38, 11, rng, INK)
    sh.greek(w * 0.08, h * 0.08, w * 0.84, h * 0.16, 4, rng, INK)
    red = L("#b3201c")
    cx, cy, R = w * 0.72, h * 0.18, min(w, h) * 0.13
    sb = sh.sub(cx - R, cy - R, cx + R, cy + R)
    if sb is not None:
        ink = (np.random.RandomState(rng.randint(0, 999)).rand(*sh.u[sb].shape) > 0.35).astype(F32)
        d = np.abs(np.hypot(sh.u[sb] - cx, sh.v[sb] - cy) - R * 0.9) - R * 0.07
        sh.paint(cov(d, sh.c) * blur(ink, 0.8) * 0.85, red, sb)
    sh.glyph(cx - R * 0.5, cy - R * 0.5, R, R, rng, red * 0.9, 0.14)


def art_sticker(sh, rng):
    c1, c2, bg = _pal(rng)
    w, h = sh.w, sh.h
    sh.fill(c1 if rng.random() < 0.5 else bg)
    R = min(w, h) * 0.5
    sh.circle(w / 2, h / 2, R * 0.8, c2, ring=R * 0.1)
    sh.glyph(w / 2 - R * 0.5, h / 2 - R * 0.5, R, R, rng, L("#f4f1ea"), 0.16)


ARTS = {"gig": art_gig, "flyer": art_flyer, "split": art_split, "idol": art_idol, "notice": art_notice,
        "sticker": art_sticker}


def weather_print(sh, rng, age, wet=0.0, bleach=0.0):
    """Fade / desaturate with age, streak-bleach from rain, darken when wet."""
    c = sh.c
    col = sh.col
    lum = (col * np.array((0.3, 0.55, 0.15), F32)).sum(-1, keepdims=True)
    col = col + ((lum * 0.6 + 0.3) - col) * (age * 0.55)
    if bleach > 0:
        st_ = n01(shifted(c, 0.3, sh.sl, rng), -1.5, 1.5)
        col = col + (L("#d8d4cc") - col) * (st_ * bleach)[..., None]
    if wet > 0:
        col = col * (1 - 0.35 * wet)
    sh.col = np.clip(col, 0, 1)


def paste(c, ob, sh, rng, age=0.0, tear=0.0, fold=None, wet=0.0, lift=0.00025, shape="rect", gloss=0.0,
          residue=True, wrinkle=1.0, crumple=0.0, ground=False):
    """Composite a sheet into the object layer: ragged edges, tears with white fibre edges, fold-over corner."""
    u, v, w, h = sh.u, sh.v, sh.w, sh.h
    rag = shifted(c, 0.012, sh.sl, rng) * 0.0009 + shifted(c, 0.004, sh.sl, rng) * 0.0004
    if shape == "circle":
        sd = np.hypot(u - w / 2, v - h / 2) - min(w, h) / 2
    else:
        sd = sd_box(u, v, w / 2, h / 2, w / 2, h / 2, 0, 0.0015)
    sd = sd + rag
    paper = cov(sd, c, 0.7) * (1 - sh.cut)
    keep = np.ones_like(paper)
    fibre = np.zeros_like(paper)
    if tear > 0:
        tf = shifted(c, 0.35, sh.sl, rng) * 0.7 + shifted(c, 0.1, sh.sl, rng) * 0.22 + rag * 45
        inner = np.clip(-sd / (min(w, h) * 0.5), 0, 1)
        low = np.clip(1 - v / h, 0, 1) * 0.5  # people tear at reachable heights
        field = tf + inner * 2.4 - tear * (2.4 + low)
        keep = sst(field, -0.02, 0.02)
        fibre = keep * sst(field, 0.11, 0.0)
    body = paper * keep
    flap = np.zeros_like(paper)
    fh = np.zeros_like(paper)
    if fold is not None:
        k, s0 = fold
        K = ((0, 0), (w, 0), (w, h), (0, h))[k]
        dx, dy = (1 if K[0] == 0 else -1) / math.sqrt(2), (1 if K[1] == 0 else -1) / math.sqrt(2)
        q = (u - K[0]) * dx + (v - K[1]) * dy
        q = q + rag * 4
        body = body * sst(q, s0 - 0.001, s0 + 0.001)
        up = u - 2 * (q - s0) * dx * 0.92
        vp = v - 2 * (q - s0) * dy * 0.92
        sd_f = sd_box(up, vp, w / 2, h / 2, w / 2, h / 2, 0, 0.0015)
        flap = cov(sd_f + rag, c, 0.7) * sst(q, s0, s0 + 0.0015) * sst(q, 2 * s0, 2 * s0 - 0.002)
        fh = np.clip((q - s0) / max(s0, 1e-3), 0, 1)
    # shadow of the lifted flap / torn edges on what's underneath
    if fold is not None:
        shd = np.clip(blur(flap, 3.5) * 1.5 - flap, 0, 1) * (1 - body)
        ob.put(sh.sl, shd * 0.55, L("#0e0d0c"), sm=0.3, h=0.0)
    # paper colour: print + torn fibre edges + grime
    col = sh.col.copy()
    core = L("#e3ded2") if not wet else L("#b9b3a6")
    col = col + (core - col) * fibre[..., None] * 0.9
    gr = n01(shifted(c, 0.15, sh.sl, rng), -0.5, 2.5) * age
    col = col * (1 - 0.45 * gr[..., None])
    sm = 0.22 + 0.2 * sh.ink + gloss * 0.4 + wet * 0.35
    hh = lift + (shifted(c, 0.05, sh.sl, rng) * 0.00025 + np.abs(shifted(c, 0.02, sh.sl, rng)) * 0.00012) * wrinkle
    if crumple > 0:
        cr = 1 - np.abs(shifted(c, 0.035, sh.sl, rng))
        cr2 = 1 - np.abs(shifted(c, 0.012, sh.sl, rng))
        hh = hh + crumple * (cr * 0.0025 + cr2 * 0.001)
        col = col * (0.82 + 0.18 * cr[..., None])
    ob.put(sh.sl, body, col, sm=sm, h=hh)
    if residue and tear > 0:
        res = paper * (1 - keep) * sst(shifted(c, 0.12, sh.sl, rng) + shifted(c, 0.03, sh.sl, rng) * 0.3, 0.6, 1.1)
        ob.put(sh.sl, res * 0.45, L("#c9c3b5") * (0.8 - 0.3 * age), sm=0.2, h=lift * 0.5)
    if fold is not None:
        back = mixc(np.broadcast_to(L("#d4cdbd"), u.shape + (3,)).copy(), L("#a69c88"),
                    sst(shifted(c, 0.03, sh.sl, rng), 0.2, 1.0) * 0.7)
        back = mulc(back, (0.65 + 0.4 * fh) * (1 - 0.35 * age))
        ob.put(sh.sl, flap, back, sm=0.25, h=lift + 0.006 * fh ** 1.6)
    return body


def staple(c, ob, rng, x, y, ang):
    sl = c.win(x - 0.01, y - 0.01, x + 0.01, y + 0.01)
    if sl is None:
        return
    lx, ly = rot(c.x[sl], c.y[sl], x, y, ang)
    m = cov(sd_box(lx, ly, 0, 0, 0.0055, 0.0006), c, 0.5)
    rust = np.random.RandomState(rng.randint(0, 999)).rand(*lx.shape) > 0.7
    ob.put(sl, m, np.where(rust[..., None], L("#6a3a1c"), L("#8d8f92")), sm=0.5, mt=0.8, h=0.0008)


def tape(c, ob, rng, x, y, ang, w=0.05, ln=0.11):
    sl = c.win(x - ln, y - ln, x + ln, y + ln)
    if sl is None:
        return
    lx, ly = rot(c.x[sl], c.y[sl], x, y, ang)
    sd = sd_box(lx, ly, 0, 0, ln / 2, w / 2) + (np.abs(np.mod(lx / 0.002, 1) - 0.5) * 0.001) * (np.abs(lx) > ln / 2 - 0.003)
    m = cov(sd, c, 0.6)
    dirt = sst(-sd, 0.003, 0.0) * m
    col = mixc(L("#cfc7a4"), L("#3a352b"), dirt * 0.8)
    ob.put(sl, m * 0.45, col, sm=0.85, h=0.0002)


def poster_wall(c, p):
    """Bill-posted wall: torn, layered posters and flyers with invented glyphs, peeling corners, tape and staples."""
    rng = c.r
    st = Stack(c)
    ob = Objs(c)
    W, H = c.wm, c.hm
    variant = p.get("variant", "a")
    items = []  # (kind, cx, cy, w, h, ang, age, tear, fold, art_seed)

    def add(kind, cx, cy, w, h, age, tear, fold=None, ang=None, seed=None):
        items.append((kind, cx, cy, w, h, math.radians(rng.uniform(-2.5, 2.5)) if ang is None else ang, age, tear, fold,
                      rng.randint(0, 10 ** 6) if seed is None else seed))

    # old background remnants
    for _ in range(3 if variant != "c" else 4):
        add(rng.choice(["gig", "split", "idol"]), rng.uniform(0.3, 0.7) * W, rng.uniform(0.35, 0.65) * H,
            rng.uniform(0.4, 0.6), rng.uniform(0.55, 0.75), 0.85, 0.75)
    if variant == "a":
        add("gig", W * 0.33, H * 0.5, 0.56, 0.8, 0.25, 0.25, fold=(2, 0.07))
        add("idol", W * 0.68, H * 0.62, 0.4, 0.56, 0.35, 0.35)
        add("split", W * 0.72, H * 0.3, 0.38, 0.5, 0.45, 0.5, fold=(1, 0.05))
        for _ in range(7):
            add(rng.choice(["flyer", "flyer", "notice"]), rng.uniform(0.2, 0.8) * W, rng.uniform(0.2, 0.75) * H,
                0.15, 0.21, rng.uniform(0.0, 0.5), rng.uniform(0.0, 0.4),
                fold=(rng.randint(0, 3), rng.uniform(0.025, 0.05)) if rng.random() < 0.3 else None)
    elif variant == "b":
        sd_ = rng.randint(0, 10 ** 6)
        kind = rng.choice(["gig", "idol", "split"])
        for r_ in range(2):
            for k in range(3):
                add(kind, W * (0.24 + 0.26 * k) + rng.uniform(-0.01, 0.01), H * (0.34 + 0.36 * r_) + rng.uniform(-0.01, 0.01),
                    0.38, 0.52, rng.uniform(0.1, 0.5), rng.choice([0.05, 0.2, 0.45, 0.7]),
                    fold=(rng.randint(0, 3), rng.uniform(0.04, 0.08)) if rng.random() < 0.35 else None,
                    ang=math.radians(rng.uniform(-0.8, 0.8)), seed=sd_)
        for _ in range(5):
            add(rng.choice(["flyer", "notice"]), rng.uniform(0.2, 0.8) * W, rng.uniform(0.2, 0.8) * H, 0.15, 0.21,
                rng.uniform(0.0, 0.4), rng.uniform(0.0, 0.3))
    else:
        xs = np.linspace(0.16, 0.84, 5)
        for x in xs:
            add(rng.choice(["gig", "split", "idol", "notice"]), x * W + rng.uniform(-0.03, 0.03), H * rng.uniform(0.45, 0.55),
                rng.uniform(0.34, 0.44), rng.uniform(0.5, 0.66), rng.uniform(0.2, 0.6), rng.uniform(0.3, 0.75),
                fold=(rng.randint(0, 3), rng.uniform(0.05, 0.09)) if rng.random() < 0.5 else None)
        for _ in range(8):
            add(rng.choice(["flyer", "flyer", "notice"]), rng.uniform(0.12, 0.88) * W, rng.uniform(0.25, 0.75) * H,
                0.15, 0.21, rng.uniform(0.0, 0.5), rng.uniform(0.0, 0.4))
    for _ in range(3):
        s_ = rng.uniform(0.07, 0.1)
        add("sticker", rng.uniform(0.2, 0.8) * W, rng.uniform(0.2, 0.8) * H, s_, s_, rng.uniform(0, 0.4), 0.15)
    for (kind, cx, cy, w, h, ang, age, tear, fold, sd_) in items:
        # keep every sheet inside the decal
        ex = 0.5 * (w * abs(math.cos(ang)) + h * abs(math.sin(ang))) + 0.03
        ey = 0.5 * (w * abs(math.sin(ang)) + h * abs(math.cos(ang))) + 0.03
        cx = min(max(cx, ex + 0.03), W - ex - 0.03)
        cy = min(max(cy, ey + 0.03), H - ey - 0.03)
        sh = Sheet(c, cx, cy, w, h, ang)
        ARTS[kind](sh, random.Random(sd_))
        weather_print(sh, rng, age, bleach=0.25 * age + 0.08)
        paste(c, ob, sh, rng, age=age, tear=tear, fold=fold, shape="circle" if (kind == "sticker" and sd_ % 2) else "rect",
              gloss=0.5 if kind in ("idol", "sticker") else 0.0)
        if kind in ("flyer", "notice") and rng.random() < 0.7:
            for (sx, sy) in ((0.012, h - 0.012), (w - 0.012, h - 0.012)):
                ca, sa = math.cos(ang), math.sin(ang)
                lx, ly = sx - w / 2, sy - h / 2
                staple(c, ob, rng, cx + lx * ca - ly * sa, cy + lx * sa + ly * ca, ang + rng.uniform(-0.3, 0.3))
        elif kind != "sticker" and rng.random() < 0.3:
            ca, sa = math.cos(ang), math.sin(ang)
            kx, ky = rng.choice([(-1, 1), (1, 1), (1, -1), (-1, -1)])
            lx, ly = kx * w / 2, ky * h / 2
            tape(c, ob, rng, cx + lx * ca - ly * sa, cy + lx * sa + ly * ca, ang + math.radians(45 * kx * ky))
    # wheat-paste halo and glue drips below the posters
    A = ob.A
    glue = np.clip(blur(A, 4) * 1.4 - A, 0, 1) * 0.3
    k = max(4, int(0.08 / c.px))
    bottom = A * (1 - np.roll(A, 4, axis=0)) * (np.roll(A, k, axis=0) < 0.05) * sst(fbm(c, 0.04, 3), 0.7, 1.5)
    drips = np.clip(drip_down(bottom, 0.06 / c.px, 30.0), 0, 1) * (1 - A)
    st.add(glue + drips * 0.35, L("#1d1b18"), sm=0.6)
    ob.to_stack(st, shadow=0.35, shadow_px=2.0)
    # global weathering: grime toward the bottom, rain streaks
    streak = sst(fbm(c, 0.4, 4, ax=0.25, ay=6.0), 0.4, 1.8)
    grime = sst(c.y, H * 0.45, 0.0) * n01(fbm(c, 0.2, 4), -1, 2)
    st.tint(np.clip(streak * 0.35 + grime * 0.45, 0, 0.7) * st.A, mul=L("#5c564c"))
    st.ao_radii = (0.002, 0.006)
    st.ao_strength = 0.6
    return st


def receipt(c, ob, rng, x, y):
    w, h = 0.058, rng.uniform(0.13, 0.22)
    sh = Sheet(c, x, y, w, h, rng.uniform(0, TAU))
    sh.fill(L("#e8e6e0"))
    sh.glyph_row(w * 0.15, h * 0.88, w * 0.7, h * 0.07, 3, rng, INK, 0.13)
    sh.greek(w * 0.08, h * 0.25, w * 0.84, h * 0.58, int(h / 0.007), rng, mixc(INK, L("#e8e6e0"), 0.35), 0.45)
    sh.rect(w * 0.1, h * 0.08, w * 0.9, h * 0.16, mixc(INK, L("#e8e6e0"), 0.2))
    paste(c, ob, sh, rng, age=0.3, tear=0.15, wet=0.5, lift=0.0004, crumple=0.3, residue=False)


def wrapper(c, ob, rng, x, y):
    w, h = rng.uniform(0.08, 0.14), rng.uniform(0.05, 0.075)
    ang = rng.uniform(0, TAU)
    sh = Sheet(c, x, y, w, h, ang)
    foil = rng.choice([N("magenta"), N("cyan"), N("yellow"), L("#b8bcc2"), N("violet")]) * 0.8
    sh.fill(foil)
    sh.rect(0, h * 0.35, w, h * 0.65, L("#141418"))
    sh.glyph_row(w * 0.2, h * 0.38, w * 0.6, h * 0.24, 3, rng, foil, 0.15)
    zig = np.abs(np.mod(sh.v / 0.004, 1.0) - 0.5) * 0.004
    sh.cut = np.maximum(sh.cut, cov(np.minimum(sh.u, w - sh.u) - zig - 0.003, c))
    v = voronoi(c, 0.006, c.s(), 0.95)
    fac = (v["id"][sh.sl] - 0.5)
    body = paste(c, ob, sh, rng, age=0.2, tear=0.1, wet=0.3, lift=0.0015, crumple=0.6, residue=False)
    ob.M[sh.sl] = np.maximum(ob.M[sh.sl], body * 0.85)
    ob.S[sh.sl] = ob.S[sh.sl] * (1 - body) + (0.55 + fac * 0.3) * body
    ob.C[sh.sl] *= (1 + fac[..., None] * 0.6 * body[..., None])


def cardboard(c, ob, rng, x, y):
    w, h = rng.uniform(0.28, 0.36), rng.uniform(0.2, 0.26)
    sh = Sheet(c, x, y, w, h, rng.uniform(0, TAU))
    sh.fill(L("#8a6a44"))
    flute = 0.5 + 0.5 * np.sin(sh.u / 0.004 * TAU)
    sh.col *= (0.92 + 0.08 * flute)[..., None]
    for k in range(2):  # 'this side up'-style arrows (symbols only)
        ax = w * (0.7 + 0.1 * k)
        sh.rect(ax - 0.004, h * 0.55, ax + 0.004, h * 0.75, INK)
        sh.poly([(ax - 0.014, h * 0.75), (ax + 0.014, h * 0.75), (ax, h * 0.82)], INK)
    sh.glyph_row(w * 0.08, h * 0.12, w * 0.4, h * 0.16, 3, rng, INK, 0.14)
    sh.rect(0, h * 0.44, w, h * 0.52, L("#b59a62"))
    paste(c, ob, sh, rng, age=0.4, tear=0.3, wet=0.6, lift=0.003, crumple=0.25, residue=False)


def litter(c, p):
    """Rain-soaked street litter: flyers, receipts, foil wrappers (and cardboard), stuck flat on wet ground."""
    rng = c.r
    st = Stack(c)
    ob = Objs(c)
    W, H = c.wm, c.hm
    if p.get("variant") == "b":
        cardboard(c, ob, rng, W * 0.45, H * 0.52)
    for k in range(p.get("flyers", 6)):
        x, y = rng.uniform(0.2, 0.8) * W, rng.uniform(0.2, 0.8) * H
        w, h = (0.15, 0.21) if rng.random() < 0.7 else (0.21, 0.297)
        sh = Sheet(c, x, y, w, h, rng.uniform(0, TAU))
        ARTS[rng.choice(["flyer", "flyer", "gig", "notice", "split"])](sh, random.Random(rng.randint(0, 10 ** 6)))
        wet = rng.uniform(0.4, 1.0)
        weather_print(sh, rng, rng.uniform(0.1, 0.6), wet=wet * 0.6, bleach=0.1)
        paste(c, ob, sh, rng, age=rng.uniform(0.2, 0.7), tear=rng.uniform(0.0, 0.5), wet=wet, lift=0.0004,
              crumple=rng.choice([0.0, 0.0, 0.3, 0.7]), residue=False,
              fold=(rng.randint(0, 3), rng.uniform(0.03, 0.06)) if rng.random() < 0.3 else None)
    for k in range(p.get("receipts", 3)):
        receipt(c, ob, rng, rng.uniform(0.2, 0.8) * W, rng.uniform(0.2, 0.8) * H)
    for k in range(p.get("wrappers", 4)):
        wrapper(c, ob, rng, rng.uniform(0.2, 0.8) * W, rng.uniform(0.2, 0.8) * H)
    for (x, y) in scatter(rng, c, 5, W * 0.5, H * 0.5, W * 0.2, H * 0.2):
        cig_butt(c, ob, rng, x, y)
    debris_base(c, st, ob, 0.2)
    wetz = np.clip(blur(ob.A, 0.015 / c.px) * 2.5, 0, 1) * (1 - ob.A)
    st.add(wetz * 0.45, L("#121212"), sm=0.75)
    ob.to_stack(st, shadow=0.45, shadow_px=2.5)
    # wet halo under sodden paper
    st.ao_radii = (0.002, 0.006)
    st.ao_strength = 0.6
    return st


# ============================================================================================== STENCILS
def spray(c, st, M, colour, sm=0.35, halo=1.0, drips=8, wear=0.3, h_paint=0.0001):
    """Spray paint through a stencil (M = crisp 0..1 mask): soft overspray, droplets, runs, ageing."""
    rng = c.r
    Mb = blur(M, 0.7)
    dens = 0.78 + 0.22 * n01(fbm(c, 0.06, 4))
    hal = (blur(M, 2.5) * 0.3 + blur(M, 8.0) * 0.16) * halo
    drops = speckle(c, 0.01, 0.6) * sst(blur(M, 10.0), 0.03, 0.35) * halo
    paint = np.clip(Mb * dens + (1 - Mb) * (hal + drops * 0.7), 0, 1)
    edge = M * (1 - np.roll(M, 3, axis=0))
    cand = np.argwhere(edge > 0.6)
    Sd = c.full(0.01)
    for _ in range(drips if len(cand) else 0):
        i, j = cand[rng.randint(0, len(cand) - 1)]
        x, y = (j + 0.5) * c.px, (i + 0.5) * c.px
        ln = rng.uniform(0.015, 0.12)
        P = frac_path(rng, (x, y), (x + rng.uniform(-0.002, 0.002), y - ln), 0.03, 5)
        hw = np.linspace(rng.uniform(0.0008, 0.0014), rng.uniform(0.0004, 0.0008), len(P))
        hw[-3:] *= 1.9
        draw_path(c, Sd, P, hw, 0.01)
    drip = cov(Sd, c, 0.7)
    paint = np.maximum(paint, drip * 0.9)
    if wear > 0:
        chips = sst(fbm(c, 0.12, 4) * 0.6 + fbm(c, 0.012, 3) * 0.5, 1.6 - wear * 1.8, 1.8 - wear * 1.8)
        paint = paint * (1 - chips)
    col = mulc(np.broadcast_to(colour, (c.H, c.W, 3)).copy(), 0.82 + 0.18 * dens)
    st.add(paint, col, sm=sm, h=Mb * h_paint + drip * 0.0004)
    return paint


def stencil_hazard(c, p):
    """Painted yellow / black chevron band (taped edges), chipped, scraped and grimy."""
    rng = c.r
    st = Stack(c)
    W, H = c.wm, c.hm
    yc = H * 0.5
    hb = 0.15
    band_sd = np.maximum(np.abs(c.y - yc) - hb, np.abs(c.x - W / 2) - (W / 2 - 0.07))
    band_sd = band_sd + fbm(c, 0.01, 2) * 0.0003
    band = cov(band_sd, c, 0.7)
    period = 0.2
    s = (c.x + np.abs(c.y - yc) * 1.0) / period
    f = np.mod(s, 1.0)
    d = (np.minimum(np.minimum(f, 1 - f), np.abs(f - 0.5)) * period) / math.sqrt(2)
    black = np.where(f >= 0.5, cov(-d, c, 0.6), 1 - cov(-d, c, 0.6))
    black = np.clip(black, 0, 1)
    micro = fbm(c, 0.02, 3)
    chip_big = fbm(c, 0.18, 4, 0.55)
    edge_w = sst(np.abs(band_sd), 0.06, 0.0)
    deep = sst(chip_big * 0.6 + micro * 0.35 + edge_w * 1.2, 1.25, 1.35)
    scr = c.zeros()
    for _ in range(14):
        x0, y0 = rng.uniform(0.1, W - 0.1), rng.uniform(yc - hb, yc + hb * 0.4)
        ln = rng.uniform(0.08, 0.5)
        a = math.radians(rng.uniform(-6, 6))
        P = frac_path(rng, (x0, y0), (x0 + math.cos(a) * ln, y0 + math.sin(a) * ln), 0.02, 4)
        S = c.full(0.005)
        draw_path(c, S, P, width_profile(rng, P, rng.uniform(0.0008, 0.0025), 0.3, 0.3), 0.005)
        scr = np.maximum(scr, cov(S, c, 0.6))
    ycol = mixc(L("#d6ad17"), L("#a88413"), n01(fbm(c, 0.2, 4)) * 0.6)
    keep_y = band * (1 - deep) * (1 - scr)
    st.add(keep_y, ycol, sm=0.5)
    bchip = sst(chip_big * 0.5 + micro * 0.5 + edge_w * 0.8, 0.95, 1.05)
    keep_b = black * keep_y * (1 - bchip)
    st.add(keep_b, L("#121212"), sm=0.48)
    st.h += keep_y * 0.00025 + keep_b * 0.0001 - scr * band * 0.0004
    # grime: rain streaks from the top edge, dirt toward the bottom of the band
    streak = sst(fbm(c, 0.3, 4, ax=0.25, ay=5.0), 0.2, 1.6) * sst(c.y, yc + hb, yc - hb * 0.6)
    grime = streak * 0.45 + sst(c.y, yc, yc - hb) * 0.3 * n01(fbm(c, 0.1, 3))
    st.tint(grime * st.A, mul=L("#4a4438"))
    run = drip_down(sst(np.abs(c.y - (yc - hb)), 0.004, 0.0) * band * sst(fbm(c, 0.05, 3), 0.6, 1.2), 0.08 / c.px, 4.0)
    run = np.clip(run, 0, 1) * (c.y < yc - hb)
    st.add(run * 0.4, L("#5a4a1e"), sm=0.4)
    st.ao_radii = (0.002, 0.006)
    st.ao_strength = 0.4
    return st


def stencil_glyph(c, p):
    """Spray-stencilled warning: hazard triangle with a bolt symbol and two rows of invented glyphs (with bridges)."""
    rng = c.r
    st = Stack(c)
    W, H = c.wm, c.hm
    tx, ty, side = 0.33, H * 0.5, 0.52
    hgt = side * math.sqrt(3) / 2
    T = [(tx - side / 2, ty - hgt / 3), (tx + side / 2, ty - hgt / 3), (tx, ty + hgt * 2 / 3)]
    th = 0.045
    tri = sd_poly(c.x, c.y, T)
    ring = np.maximum(tri, -(tri + th))
    for (a, b) in ((T[0], T[1]), (T[1], T[2]), (T[2], T[0])):
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        ring = np.maximum(ring, -(np.hypot(c.x - mx, c.y - my) - 0.008))
    bolt = [(tx + 0.02, ty + 0.17), (tx - 0.07, ty + 0.0), (tx - 0.005, ty + 0.0), (tx - 0.035, ty - 0.13),
            (tx + 0.075, ty + 0.04), (tx + 0.01, ty + 0.04)]
    M1 = np.maximum(cov(ring, c), cov(sd_poly(c.x, c.y, bolt), c))
    M2 = c.zeros()
    glyph_row(c, M2, 0.66, H * 0.5, 0.84, 0.19, 4, rng, stroke=0.15, bridges=True, square=True)
    glyph_row(c, M2, 0.66, H * 0.28, 0.84, 0.1, 6, rng, stroke=0.15, bridges=True, square=True)
    bar = sd_box(c.x, c.y, 1.08, H * 0.2, 0.42, 0.012)
    for bx in (0.86, 1.3):
        bar = np.maximum(bar, -(np.abs(c.x - bx) - 0.005))
    M2 = np.maximum(M2, cov(bar, c))
    spray(c, st, M1, L("#e2bd1c"), drips=10, wear=0.35)
    spray(c, st, M2, L("#d9d6cd"), drips=8, wear=0.3)
    # misregistered second pass (faint ghost)
    ghost = np.roll(np.roll(M2, 3, axis=0), -2, axis=1)
    st.add(blur(ghost, 1.2) * 0.14 * (1 - M2), L("#d9d6cd"), sm=0.3)
    st.ao_strength = 0.0
    return st


# ============================================================================================== UTILITY
def drain_grate(c, p):
    """Cast-iron slot drain in a concrete collar: deep slots, worn bars, rust, debris, converging wet stains."""
    rng = c.r
    st = Stack(c)
    W, H = c.wm, c.hm
    cx, cy = W / 2, H / 2
    ox, oy = 0.34, 0.165
    fr_out = sd_box(c.x, c.y, cx, cy, ox, oy, 0, 0.004)
    fr_in = sd_box(c.x, c.y, cx, cy, ox - 0.03, oy - 0.03, 0, 0.002)
    collar_sd = sd_box(c.x, c.y, cx, cy, ox + 0.055, oy + 0.05, 0, 0.012) + fbm(c, 0.05, 3) * 0.006
    n_sl = 13
    pitch = (2 * (ox - 0.03)) / n_sl
    lx = (c.x - (cx - ox + 0.03)) / pitch
    f = np.mod(lx, 1.0) - 0.5
    slot_sd = np.maximum.reduce([np.abs(f) * pitch - 0.0135, np.abs(c.y - cy) - (oy - 0.04), 0.011 - np.abs(c.y - cy)])
    slot_sd = np.maximum(slot_sd, fr_in)
    slot = cov(slot_sd, c, 0.7)
    inner = cov(fr_in, c)
    frame = cov(fr_out, c) * (1 - inner)
    metal = cov(fr_out, c) * (1 - slot)
    # collar and surroundings
    collar = cov(collar_sd, c) * (1 - cov(fr_out, c))
    dist = np.maximum(collar_sd, 0)
    micro = fbm(c, 0.015, 3)
    ring = polar_noise(c, fbm(c, 0.06, 4), cx, cy, 2, 0.04)
    stain = np.exp(-dist / 0.06) * (0.55 + 0.45 * n01(ring)) * (1 - collar) * sst(c.edge_dist(), 0.0, 0.06)
    st.add(stain * 0.75, L("#121110"), sm=0.75)
    ccol = mixc(L("#6c6860"), L("#4a4741"), n01(micro) * 0.6)
    wetc = sst(collar_sd, -0.02, -0.055)
    ccol = mixc(ccol, L("#2a2724"), wetc * 0.6)
    st.add(collar, ccol, sm=0.35 + 0.35 * wetc, ao=0.95)
    chips = sst(fbm(c, 0.03, 3), 1.1, 1.4) * collar
    st.tint(chips, col=L("#8b867c"))
    # metal: frame + bars
    rust = sst(fbm(c, 0.05, 4) + sst(slot_sd, 0.006, 0.0) * 1.2 + sst(fr_out, -0.006, 0.0) * 0.8, 0.8, 1.6)
    wear = sst(fbm(c, 0.08, 3), -0.3, 0.8) * sst(slot_sd, 0.002, 0.008)
    mcol = mixc(L("#2c2d2f"), L("#6d6e70"), wear)
    mcol = mixc(mcol, mixc(L("#4c240e"), L("#7a3d17"), n01(micro)), rust * 0.85)
    dia = np.abs(np.mod((c.x + c.y) / 0.012, 1) - 0.5) + np.abs(np.mod((c.x - c.y) / 0.012, 1) - 0.5)
    tread = sst(dia, 0.35, 0.25) * frame
    st.add(metal, mcol, sm=0.35 + 0.3 * wear - 0.15 * rust, mt=0.85 * (1 - rust) * (0.6 + 0.4 * wear), ao=1.0)
    st.add(slot, mixc(L("#050505"), L("#0e0f10"), sst(np.abs(f) * pitch, 0.012, 0.0)), sm=0.15,
           ao=0.04 + 0.2 * sst(slot_sd, -0.0015, 0.0))
    bolt = c.zeros()
    for sx in (-1, 1):
        for sy in (-1, 1):
            bolt = np.maximum(bolt, cov(np.hypot(c.x - cx - sx * (ox - 0.015), c.y - cy - sy * (oy - 0.015)) - 0.007, c))
    st.add(bolt, L("#4d4e50"), sm=0.45, mt=0.8)
    h = -0.002 * inner * (1 - slot) - 0.05 * sst(-slot_sd, 0.0, 0.004) + tread * 0.0006 + bolt * 0.0025
    h += -0.0012 * sst(slot_sd, 0.003, 0.0) * (1 - slot) - 0.004 * chips + collar * micro * 0.0006
    st.h += h
    # debris caught on the bars
    ob = Objs(c)
    for _ in range(2):
        cig_butt(c, ob, rng, cx + rng.uniform(-0.25, 0.25), cy + rng.uniform(-0.1, 0.1))
    for _ in range(4):
        plastic_bit(c, ob, rng, cx + rng.uniform(-0.3, 0.3), cy + rng.uniform(-0.13, 0.13))
    sh = Sheet(c, cx + 0.12, cy - 0.04, 0.07, 0.05, rng.uniform(0, TAU))
    art_flyer(sh, rng, tabs=False)
    paste(c, ob, sh, rng, age=0.6, tear=0.4, wet=1.0, crumple=0.5, residue=False)
    ob.to_stack(st, shadow=0.4, shadow_px=2.0)
    st.ao_radii = (0.003, 0.01, 0.03)
    return st


def manhole_cover(c, p):
    """Round cast-iron manhole cover in its frame: stud tread, invented glyph emblem, pick holes, tar sealant ring."""
    rng = c.r
    st = Stack(c)
    cx, cy = c.wm / 2, c.hm / 2
    dx, dy = c.x - cx, c.y - cy
    r = np.hypot(dx, dy)
    th = np.arctan2(dy, dx)
    Rc = 0.355
    cover = cov(r - Rc, c)
    micro = fbm(c, 0.012, 3)
    # raised pattern
    R = c.zeros()
    R = np.maximum(R, cov(np.abs(r - 0.34) - 0.013, c))           # outer rim band
    R = np.maximum(R, cov(np.abs(r - 0.137) - 0.007, c))          # emblem ring
    R = np.maximum(R, cov(np.abs(r - 0.074) - 0.004, c))          # inner ring
    dr = 0.0245
    k = np.floor((r - 0.155) / dr)
    rk = 0.155 + (k + 0.5) * dr
    nk = np.round(TAU * rk / 0.027)
    a = th / TAU * nk + 0.5 * np.mod(k, 2)
    fa = np.mod(a, 1.0) - 0.5
    arc = fa * TAU * rk / np.maximum(nk, 1)
    rad = r - rk
    qa, qb = (arc + rad) / math.sqrt(2), (arc - rad) / math.sqrt(2)
    stud = sd_box(qa, qb, 0, 0, 0.0062, 0.0062, 0, 0.0018)
    band = (r > 0.155) & (r < 0.155 + 6 * dr)
    R = np.maximum(R, cov(stud, c) * band)
    G = c.zeros()
    ng = 10
    for i in range(ng):
        a0 = TAU * i / ng + 0.2
        gx, gy = cx + math.cos(a0) * 0.105, cy + math.sin(a0) * 0.105
        draw_glyph(c, G, gx - 0.0125, gy - 0.0125, 0.025, 0.025, rng, 0.16, ang=a0 - math.pi / 2)
    draw_glyph(c, G, cx - 0.042, cy - 0.042, 0.084, 0.084, rng, 0.15)
    R = np.maximum(R, G)
    pick = c.full(1.0)
    for a0 in (0.0, math.pi):
        pick = np.minimum(pick, sd_box(c.x, c.y, cx + math.cos(a0) * 0.268, cy + math.sin(a0) * 0.268, 0.018, 0.0065, a0, 0.006))
    pickm = cov(pick, c)
    R = R * cover * (1 - pickm)
    # colours
    wear = sst(fbm(c, 0.1, 3), -0.6, 0.6)
    raised_col = mixc(L("#4b4b4a"), L("#7c7c7a"), wear * 0.8 + 0.2 * n01(micro))
    rec_rust = sst(fbm(c, 0.06, 4), -0.2, 0.9)
    rec_col = mixc(L("#24211f"), L("#4a2612"), rec_rust * 0.8)
    pool = sst(c.y, cy + 0.05, cy - 0.25) * sst(fbm(c, 0.08, 3), -0.6, 0.4) * (1 - R) * cover
    col = mixc(rec_col, raised_col, R)
    sm_c = 0.38 + 0.2 * R * wear + 0.45 * pool
    mt_c = 0.35 * (1 - R) * (1 - rec_rust) + 0.9 * R
    # frame ring and gap
    gap = cov(np.abs(r - 0.3575) - 0.0018, c)
    frame = cov(np.abs(r - 0.391) - 0.032, c) * (1 - gap)
    scr = sst(polar_noise(c, fbm(c, 0.004, 2), cx, cy, 3, 4.0), 1.2, 2.0)
    fcol = mixc(L("#3e3e3d"), L("#6e6e6c"), n01(fbm(c, 0.05, 3)) * 0.7 + scr * 0.3)
    # tar sealant + asphalt patch
    seal_r = 0.43 + 0.012 * fbm(c, 0.1, 3) + 0.004 * fbm(c, 0.02, 2)
    seal = cov(r - seal_r, c) * (1 - cov(r - 0.423, c))
    patch_r = 0.475 + 0.012 * fbm(c, 0.15, 3)
    patch = sst(r, patch_r, patch_r - 0.02) * (1 - cov(r - seal_r, c))
    Sp = c.full(0.01)
    for _ in range(9):
        a0 = rng.uniform(0, TAU)
        P = frac_path(rng, (cx + math.cos(a0) * 0.44, cy + math.sin(a0) * 0.44),
                      (cx + math.cos(a0) * 0.49, cy + math.sin(a0) * 0.49), 0.25, 4)
        draw_path(c, Sp, P, width_profile(rng, P, 0.0015, 0.0, 0.5, end0=1.0), 0.01)
    pcr = cov(Sp, c, 0.6) * patch
    st.add(patch * 0.85, mixc(L("#1c1c1e"), L("#2a2a2b"), n01(micro)), sm=0.55)
    st.add(pcr, L("#080808"), sm=0.6, ao=0.4)
    st.add(seal, L("#0b0b0c"), sm=0.7)
    st.add(frame, fcol, sm=0.5, mt=0.85)
    st.add(gap, L("#050505"), sm=0.2, ao=0.1)
    st.add(cover * (1 - pickm), col, sm=sm_c, mt=mt_c)
    st.add(pickm * cover, L("#040404"), sm=0.1, ao=0.05)
    bleed = np.exp(-np.maximum(r - 0.36, 0) / 0.012) * (r > 0.36) * sst(polar_noise(c, fbm(c, 0.05, 3), cx, cy, 1, 0.1), 0.4, 1.2)
    st.add(bleed * 0.6 * frame, L("#6b3414"), sm=0.3, mt=0.1)
    st.h += cover * (0.004 * R + micro * 0.0002) - gap * 0.01 - pickm * cover * 0.03 + frame * 0.0005 + seal * 0.0008
    st.h += -pcr * 0.003
    st.ao_radii = (0.002, 0.006, 0.02)
    return st


# ============================================================================================== GRIME
def grime_free(c, p):
    """Generic tag-free grime: soot smudges, mud splashes, tide marks, mould spots, wipe smears."""
    rng = c.r
    st = Stack(c)
    W, H = c.wm, c.hm
    inside = sst(c.edge_dist(), 0.02, 0.35)
    soot = sst(warp(c, fbm(c, 0.5, 5, 0.6), 0.05, 0.3), 0.3, 1.8) * inside
    st.add(soot * 0.55, L("#1a1816"), sm=0.18)
    # tide marks: level-set lines of a smooth field
    tf = warp(c, fbm(c, 0.6, 3), 0.03, 0.2)
    for lvl in (-0.4, 0.2, 0.7):
        line = np.exp(-((tf - lvl) / 0.02) ** 2) * sst(fbm(c, 0.2, 3), -0.4, 0.6) * inside
        st.add(line * 0.5, L("#3a342b"), sm=0.25)
    # mud splashes: blob + droplets thrown radially
    for _ in range(3):
        sx, sy = rng.uniform(0.25, 0.75) * W, rng.uniform(0.2, 0.6) * H
        r = np.hypot(c.x - sx, c.y - sy)
        blob = sst(r + fbm_cache(c, 0.03) * 0.012, 0.045, 0.03)
        drops = speckle(c, 0.004, 1.2) * np.exp(-r / 0.12) * (r > 0.04)
        st.add(np.clip(blob + drops, 0, 1) * 0.75, L("#2c261e"), sm=0.3, h=(blob + drops) * 0.0002)
    # mould clusters
    for _ in range(2):
        mx, my = rng.uniform(0.25, 0.75) * W, rng.uniform(0.25, 0.75) * H
        reg = np.exp(-(((c.x - mx) / 0.18) ** 2 + ((c.y - my) / 0.12) ** 2))
        spots = speckle(c, 0.02, 1.0) * reg
        st.add(np.clip(spots * 1.4 + reg * 0.15 * n01(fbm(c, 0.05, 3)), 0, 1) * inside, L("#121410"), sm=0.25)
    # wipe smears (diagonal swipes)
    for _ in range(3):
        a = math.radians(rng.uniform(-35, 35))
        x0, y0 = rng.uniform(0.3, 0.7) * W, rng.uniform(0.3, 0.7) * H
        lx, ly = rot(c.x, c.y, x0, y0, a)
        sw = sst(np.abs(ly) / 0.05, 1.0, 0.3) * sst(np.abs(lx) / rng.uniform(0.2, 0.35), 1.0, 0.5)
        fib = n01(fbm(c, 0.3, 3, ax=12.0, ay=0.3) if abs(a) < 0.4 else fbm(c, 0.3, 3), -1.5, 1.5)
        st.add(sw * fib * 0.45 * inside, L("#24211d"), sm=0.45)
    st.ao_strength = 0.0
    return st


# ============================================================================================== REGISTRY
DECALS = {}
URP_SHADER = "Shader Graphs/Decal"


def reg(name, fn, size, px, projection, use, tags, normal_blend=0.8, order=0, depth=0.3, seed=None, **params):
    DECALS[name] = {"fn": fn, "size": size, "px": px, "projection": projection, "use": use, "tags": tags,
                    "normalBlend": normal_blend, "drawOrder": order, "projectionDepth": depth,
                    "seed": seed if seed is not None else sum(ord(ch) * (i + 1) for i, ch in enumerate(name)),
                    "params": params}


# draw order (higher renders on top): grime 0, cracks 1, paint 2, utility/stencils 3, oil/posters 4, scorch 5,
# water 6, loose objects 7
reg("Puddle_A", puddle, (2.4, 2.4), (1024, 1024), "floor",
    "Neon-reflection puddle, large lobed shape. Ground/sidewalk low spots; pair with reflection probes.",
    ["water", "wet", "reflective", "street"], 1.0, 6, 0.25,
    lobes=[(0.47, 0.5, 0.3, 0.24, 15), (0.62, 0.42, 0.18, 0.16, 0), (0.36, 0.6, 0.16, 0.13, -30)])
reg("Puddle_B", puddle, (3.2, 1.6), (2048, 1024), "floor",
    "Long gutter puddle; align the long straighter edge (+V side) with a kerb. Road edges, alley gutters.",
    ["water", "wet", "reflective", "gutter"], 1.0, 6, 0.25,
    lobes=[(0.5, 0.62, 0.42, 0.22, 0), (0.25, 0.6, 0.16, 0.2, 0), (0.75, 0.58, 0.17, 0.24, 0), (0.5, 0.75, 0.44, 0.08, 0)],
    irreg=0.12, micro_mm=1.3)
reg("Puddle_C", puddle, (2.0, 2.0), (1024, 1024), "floor",
    "Cluster of small puddles in a dip. Scatter between larger puddles, plazas, rooftops.",
    ["water", "wet", "reflective", "small"], 1.0, 6, 0.25,
    lobes=[(0.3, 0.35, 0.13, 0.1, 20), (0.62, 0.3, 0.1, 0.08, -10), (0.45, 0.62, 0.15, 0.1, 40), (0.72, 0.66, 0.09, 0.12, 0),
           (0.25, 0.7, 0.07, 0.06, 0)], depth_mm=6.0, micro_mm=1.4, irreg=0.25)
reg("Puddle_D", puddle, (2.8, 2.8), (1024, 1024), "floor",
    "Wide shallow puddle broken by dry islands. Large open areas (plaza, parking).",
    ["water", "wet", "reflective", "shallow"], 1.0, 6, 0.25,
    lobes=[(0.5, 0.5, 0.36, 0.3, -20), (0.38, 0.62, 0.2, 0.16, 0)], depth_mm=4.0, micro_mm=1.9, irreg=0.2)
reg("Oil_Stain_A", oil_stain_a, (1.6, 1.6), (1024, 1024), "floor",
    "Layered engine-oil stain (old wide halos + fresh glossy pools + splatter). Parking bays, garages, alley ends.",
    ["oil", "stain", "vehicle"], 0.4, 4, 0.2)
reg("Oil_Stain_B", oil_stain_b, (2.4, 1.2), (1024, 512), "floor",
    "Oil drip trail with a tyre track smearing out of the pool along +U. Roads, garage ramps.",
    ["oil", "stain", "vehicle", "tyre"], 0.4, 4, 0.2)
reg("Oil_Rainbow_Puddle", oil_rainbow_puddle, (2.0, 2.0), (1024, 1024), "floor",
    "Puddle with a thin-film oil sheen (iridescent swirls toward the shore; metallic tint carries the colour into "
    "reflections). Next to vehicles, garages, under leaking machinery.",
    ["water", "oil", "iridescent", "reflective"], 1.0, 6, 0.25,
    lobes=[(0.5, 0.5, 0.3, 0.24, 30), (0.38, 0.4, 0.15, 0.13, 0)], depth_mm=7.0)
reg("Crack_Concrete_A", crack_concrete_a, (1.6, 1.6), (1024, 1024), "floor",
    "Branching concrete crack with spalled edges, dirt and moss. Floors; also works on walls (projection any).",
    ["crack", "concrete", "damage"], 1.0, 1, 0.3)
reg("Crack_Concrete_B", crack_concrete_b, (2.4, 1.2), (2048, 1024), "floor",
    "Long structural crack along +U: wide, chipped, water in the bottom, moss tufts. Slabs, sidewalks, walls.",
    ["crack", "concrete", "damage", "long"], 1.0, 1, 0.3)
reg("Crack_Concrete_C", crack_concrete_c, (1.4, 1.4), (1024, 1024), "floor",
    "Impact star: crushed pit with radial and spider-web cracks. Where heavy objects fell; combat damage.",
    ["crack", "concrete", "damage", "impact"], 1.0, 1, 0.3)
reg("Crack_Asphalt_Network", crack_asphalt_network, (2.4, 2.4), (1024, 1024), "floor",
    "Alligator cracking on asphalt with a glossy tar-snake sealant and ravelled pothole starts. Roads, parking.",
    ["crack", "asphalt", "road", "damage"], 1.0, 1, 0.3)
reg("RoadLine_Solid", roadline_solid, (4.0, 0.5), (2048, 256), "floor",
    "Worn yellow solid line (0.15 m) along +U. Chain end to end with ~0.3 m overlap (ends fade irregularly).",
    ["road", "paint", "marking"], 0.5, 2, 0.2, colour="#d9a21c")
reg("RoadLine_Dashed", roadline_dashed, (4.0, 0.5), (2048, 256), "floor",
    "One worn white 3 m lane dash (0.15 m) along +U. Repeat every 9 m (3 m dash + 6 m gap).",
    ["road", "paint", "marking"], 0.5, 2, 0.2, colour="#d6d3cb")
reg("Crosswalk_Faded", crosswalk_faded, (4.0, 3.0), (2048, 1536), "floor",
    "Four faded zebra bars (0.5 m, traffic runs along +V) with wheel paths worn through and a ghost of older paint. "
    "Tile across the road every 4 m.",
    ["road", "paint", "marking", "crosswalk"], 0.5, 2, 0.2)
reg("Road_Arrow_Stencil", road_arrow_stencil, (2.0, 4.0), (1024, 2048), "floor",
    "Straight-and-right lane arrow, pointing +V, elongated like real markings. Lane centres before junctions.",
    ["road", "paint", "marking", "arrow"], 0.5, 2, 0.2)
reg("Road_Glyph_Stencil", road_glyph_stencil, (2.0, 4.0), (1024, 2048), "floor",
    "Two invented glyphs painted on the road (read toward +V), stretched along travel like real road text, with bar.",
    ["road", "paint", "marking", "glyph"], 0.5, 2, 0.2)
reg("Grime_Leak_Streak_A", leak_streak_a, (1.2, 2.4), (512, 1024), "wall",
    "Water leak from a crack near the top: meandering wet rivulets, algae, efflorescence. +V = up. Under joints, pipes.",
    ["wall", "grime", "water", "streak"], 0.6, 1, 0.3)
reg("Grime_Leak_Streak_B", leak_streak_b, (2.0, 2.0), (1024, 1024), "wall",
    "Curtain of grime streaks below a ledge or sill (top edge = ledge line). +V = up.",
    ["wall", "grime", "water", "streak"], 0.6, 1, 0.3)
reg("Rust_Streak_A", rust_streak_a, (0.8, 1.6), (512, 1024), "wall",
    "Rust bleeding from an embedded steel anchor (source at top). +V = up. Under bolts, brackets, sign mounts.",
    ["wall", "rust", "streak"], 0.6, 1, 0.3)
reg("Rust_Streak_B", rust_streak_b, (1.6, 1.6), (1024, 1024), "wall",
    "Spalled concrete exposing corroded rebar with rust runoff below. +V = up. Old structures, overpass piers.",
    ["wall", "rust", "streak", "damage", "concrete"], 0.9, 1, 0.3)
reg("Grime_Base_Wall", grime_base_wall, (4.0, 1.0), (2048, 512), "wall",
    "Dirt band at the foot of walls (splash-back, rising-damp tide lines, wet bottom, moss). Bottom edge = floor line "
    "(sink the projector ~3 cm into the ground). Chain along walls with ~0.3 m overlap.",
    ["wall", "grime", "base", "wet"], 0.5, 0, 0.3)
reg("Scorch_Mark_A", scorch_floor, (2.4, 2.4), (1024, 1024), "floor",
    "Blast mark: soot rays, crater, crazed char, shrapnel gouges, ash. Explosion sites, burnt-out vehicles.",
    ["damage", "scorch", "blast"], 0.8, 5, 0.3)
reg("Scorch_Mark_B", scorch_wall, (2.0, 2.0), (1024, 1024), "wall",
    "Fire scorch on a wall: blistered char at the base and a turbulent soot plume rising in a V. +V = up.",
    ["damage", "scorch", "fire", "wall"], 0.8, 5, 0.3)
reg("Bullet_Holes_Cluster", bullet_holes, (1.0, 1.0), (1024, 1024), "wall",
    "Cluster of 13 rifle impacts with spall craters, radial micro-cracks and dust. Combat arenas, cover walls.",
    ["damage", "bullet", "combat", "wall"], 1.0, 7, 0.3)
reg("Debris_Scatter_A", debris_a, (1.6, 1.6), (1024, 1024), "floor",
    "Gravel, broken bottle glass, crumbs, cigarette butts, a bottle cap, grit. Alleys, under benches, corners.",
    ["litter", "debris", "glass", "gravel"], 1.0, 7, 0.2)
reg("Debris_Scatter_B", debris_b, (1.2, 1.2), (1024, 1024), "floor",
    "Tech debris: cable offcuts with copper ends, screws, broken plastic, a circuit-board fragment, glass crumbs.",
    ["litter", "debris", "tech"], 1.0, 7, 0.2)
reg("Litter_Paper_A", litter, (2.0, 2.0), (1024, 1024), "floor",
    "Rain-soaked flyers (invented glyph print), receipts, foil wrappers, butts stuck flat to wet ground.",
    ["litter", "paper", "flyer", "wet"], 0.9, 7, 0.2, flyers=6, receipts=3, wrappers=4)
reg("Litter_Paper_B", litter, (2.0, 2.0), (1024, 1024), "floor",
    "Sodden cardboard piece with scattered flyers, receipts and wrappers.",
    ["litter", "paper", "cardboard", "wet"], 0.9, 7, 0.2, variant="b", flyers=5, receipts=2, wrappers=3)
reg("Poster_Flyer_Wall_A", poster_wall, (1.6, 1.6), (1024, 1024), "wall",
    "Layered torn posters and flyers (invented glyphs, neon palette, peeling corners, tape, staples). +V = up.",
    ["wall", "poster", "flyer", "glyph", "neon"], 0.8, 4, 0.3, variant="a")
reg("Poster_Flyer_Wall_B", poster_wall, (1.6, 1.6), (1024, 1024), "wall",
    "Bill-posting grid: one poster repeated 3 x 2, partly torn, flyers on top. +V = up.",
    ["wall", "poster", "flyer", "glyph", "neon"], 0.8, 4, 0.3, variant="b")
reg("Poster_Flyer_Wall_C", poster_wall, (2.4, 1.2), (2048, 1024), "wall",
    "Wide strip of heavily peeled posters over older layers. Hoardings, underpasses. +V = up.",
    ["wall", "poster", "flyer", "glyph", "neon"], 0.8, 4, 0.3, variant="c")
reg("Stencil_Warning_Hazard", stencil_hazard, (2.0, 0.5), (2048, 512), "wall",
    "Yellow/black chevron hazard band (0.3 m) along +U, chipped and scraped. Dock edges, machinery, low clearance; "
    "also usable on floors.",
    ["stencil", "hazard", "paint", "warning"], 0.5, 3, 0.3)
reg("Stencil_Warning_Glyph", stencil_glyph, (1.6, 0.8), (1024, 512), "wall",
    "Spray-stencilled warning: hazard triangle with bolt symbol + two rows of invented glyphs, overspray and runs.",
    ["stencil", "warning", "glyph", "spray"], 0.3, 3, 0.3)
reg("Drain_Grate", drain_grate, (1.0, 0.5), (1024, 512), "floor",
    "Cast-iron slot drain (0.68 x 0.33 m) in a concrete collar, deep slots, rust, caught debris. Gutters, plazas.",
    ["utility", "drain", "metal", "street"], 1.0, 3, 0.2)
reg("Manhole_Cover", manhole_cover, (1.0, 1.0), (1024, 1024), "floor",
    "0.71 m cast-iron manhole cover with stud tread and invented glyph emblem ring, frame, tar seal. Roads, sidewalks.",
    ["utility", "manhole", "metal", "street", "glyph"], 1.0, 3, 0.2)
reg("Grime_Tags_Free", grime_free, (1.6, 1.6), (1024, 1024), "wall",
    "Generic tag-free grime: soot smudges, mud splashes, tide marks, mould spots, wipe smears. Break up any wall.",
    ["wall", "grime", "dirt"], 0.4, 0, 0.3)


def generate(name):
    """Build the decal: returns (canvas, stack result dict, stack)."""
    d = DECALS[name]
    c = Canvas(d["size"], d["px"], d["seed"])
    st = d["fn"](c, d["params"])
    return c, st
