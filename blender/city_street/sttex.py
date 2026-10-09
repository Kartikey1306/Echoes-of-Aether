"""Tileable texture maths for the street kit (plain numpy + scipy; no Blender needed).

Every field is periodic over the square canvas by construction (FFT-filtered noise, periodic KD-tree Voronoi,
modular grids), so the maps tile seamlessly. Arrays are BOTTOM row first (row index = +V), like blender/env/bakekit,
so bakekit.height_to_normal / save_set can be reused unchanged.
"""
import math

import numpy as np
from scipy.spatial import cKDTree

F32 = np.float32


class Tex:
    """Tileable canvas: nu x nv pixels; the u axis covers `tile` metres (square pixels, so v covers tile * nv / nu)."""

    def __init__(self, n, tile, seed, nv=None):
        self.n = n                       # pixels along u
        self.nv = nv or n                # pixels along v
        self.tile = tile
        self.tile_v = tile * self.nv / n
        self.px = tile / n
        self.seed = seed
        self._k = 0
        v, u = np.mgrid[0:self.nv, 0:n]
        self.u = ((u + 0.5) / n).astype(F32)        # 0..1 across the tile (u)
        self.v = ((v + 0.5) / n).astype(F32)        # same units as u (0..nv/n)
        self.vn = ((v + 0.5) / self.nv).astype(F32)  # 0..1 across v
        self.shape = (self.nv, n)
        self.rng = np.random.RandomState(seed)

    def s(self):
        self._k += 1
        return (self.seed * 7919 + self._k * 104729) % (2 ** 31 - 1)

    # ------------------------------------------------------------------ noise
    def noise(self, feat_m, octaves=5, gain=0.5, lac=2.0, ax=1.0, ay=1.0, seed=None):
        """Periodic fractal noise, zero mean / unit std. feat_m = largest feature size (m). ax/ay > 1 stretch along u/v."""
        seed = self.s() if seed is None else seed
        F = np.fft.rfft2(np.random.RandomState(seed).standard_normal(self.shape).astype(F32))
        fy = np.fft.fftfreq(self.nv)[:, None]
        fx = np.fft.rfftfreq(self.n)[None, :]
        acc = 0.0
        for i in range(octaves):
            s = feat_m / (lac ** i) / self.px * 0.25
            if s < 0.3:
                break
            g = np.exp(-2.0 * np.pi ** 2 * ((s * ax * fx) ** 2 + (s * ay * fy) ** 2))
            acc = acc + (gain ** i) * g / np.sqrt(np.mean(g * g) + 1e-12)
        out = np.fft.irfft2(F * acc, s=self.shape)
        out -= out.mean()
        out /= out.std() + 1e-9
        return out.astype(F32)

    def white(self, seed=None):
        seed = self.s() if seed is None else seed
        return np.random.RandomState(seed).rand(*self.shape).astype(F32)

    def blur(self, a, sigma_px, sy=None):
        """Wrap-around gaussian blur (FFT), optionally anisotropic (sx along u, sy along v)."""
        sy = sigma_px if sy is None else sy
        if sigma_px <= 0.2 and sy <= 0.2:
            return a
        fy = np.fft.fftfreq(a.shape[0])[:, None]
        fx = np.fft.fftfreq(a.shape[1])[None, :]
        g = np.exp(-2.0 * np.pi ** 2 * ((sigma_px * fx) ** 2 + (sy * fy) ** 2))
        if a.ndim == 3:
            return np.stack([np.real(np.fft.ifft2(np.fft.fft2(a[..., k]) * g)) for k in range(a.shape[2])], -1).astype(F32)
        return np.real(np.fft.ifft2(np.fft.fft2(a) * g)).astype(F32)

    def warp(self, a, amp_m, feat_m, octaves=3):
        """Domain-warp (periodic) by noise of amplitude amp_m metres."""
        dx = self.noise(feat_m, octaves) * (amp_m / self.px)
        dy = self.noise(feat_m, octaves) * (amp_m / self.px)
        yy, xx = np.mgrid[0:self.nv, 0:self.n].astype(F32)
        return sample_wrap(a, xx + dx, yy + dy)

    # ------------------------------------------------------------------ cells
    def voronoi(self, cell_m, jitter=1.0, seed=None, k=2, aspect=1.0):
        """Periodic Voronoi: returns (d1, d2, id) with distances in metres. aspect > 1 squashes cells along v."""
        seed = self.s() if seed is None else seed
        rs = np.random.RandomState(seed)
        ar = self.nv / self.n
        cnt = max(4, int(round((self.tile / cell_m) ** 2 * ar * aspect)))
        pts = rs.rand(cnt, 2) * np.array([1.0, ar])
        tree = cKDTree(pts, boxsize=[1.0, ar])
        q = np.stack([self.u.ravel(), self.v.ravel()], -1)
        d, i = tree.query(q, k=k, workers=-1)
        d = d.astype(F32) * self.tile
        sh = self.shape
        return d[:, 0].reshape(sh), d[:, 1].reshape(sh), i[:, 0].reshape(sh)

    def cell_rand(self, ids, seed=None):
        """Random value per Voronoi id / grid cell id (same shape)."""
        seed = self.s() if seed is None else seed
        lut = np.random.RandomState(seed).rand(int(ids.max()) + 1).astype(F32)
        return lut[ids]


def sample_wrap(a, X, Y):
    """Bilinear sample with wrap-around (periodic)."""
    H, W = a.shape[:2]
    x0 = np.floor(X).astype(np.int64)
    y0 = np.floor(Y).astype(np.int64)
    fx = (X - x0).astype(F32)
    fy = (Y - y0).astype(F32)
    x0 %= W
    y0 %= H
    x1 = (x0 + 1) % W
    y1 = (y0 + 1) % H
    if a.ndim == 3:
        fx = fx[..., None]
        fy = fy[..., None]
    return ((a[y0, x0] * (1 - fx) + a[y0, x1] * fx) * (1 - fy) + (a[y1, x0] * (1 - fx) + a[y1, x1] * fx) * fy).astype(F32)


def sst(x, a, b):
    """smoothstep from a to b (a > b gives the falling edge)."""
    t = np.clip((np.asarray(x, F32) - a) / (b - a), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(F32)


def lerp(a, b, t):
    t = np.asarray(t, F32)
    if t.ndim == 2 and (np.ndim(a) == 3 or np.ndim(b) == 3 or (np.ndim(a) == 1 and np.size(a) == 3) or (np.ndim(b) == 1 and np.size(b) == 3)):
        t = t[..., None]
    return (np.asarray(a, F32) + (np.asarray(b, F32) - np.asarray(a, F32)) * t).astype(F32)


def mulc(c, f):
    f = np.asarray(f, F32)
    return (c * (f[..., None] if f.ndim == 2 else f)).astype(F32)


def lin(hexstr):
    h = hexstr.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return np.array([x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c], F32)


def grey(v):
    """sRGB grey level -> linear rgb."""
    x = v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return np.array([x, x, x], F32)


def cracks(t, feat_m, width_m, keep=0.5, warp_m=0.0, seed=None):
    """Thin wiggly crack network: zero crossings of a noise field, gated by a second noise. Returns 0..1."""
    n = t.noise(feat_m, 5, 0.55, seed=seed)
    if warp_m > 0:
        n = t.warp(n, warp_m, feat_m * 0.5)
    # distance-ish to the zero set: |n| / |grad n|
    gy, gx = np.gradient(n)
    g = np.sqrt(gx * gx + gy * gy) / t.px + 1e-6
    d = np.abs(n) / g
    line = sst(d, width_m, 0.0)
    gate = sst(t.noise(feat_m * 2.5, 2), keep - 1.0, keep - 0.6)
    return (line * gate).astype(F32)


def periodic_line_mask(t, paths, width_m, soft_m=None):
    """Anti-aliased mask of wrapped polylines (lists of (u, v) in tile units). Width in metres."""
    from PIL import Image, ImageDraw
    n, nv = t.n, t.nv
    ss = 2
    img = Image.new("L", (n * ss, nv * ss), 0)
    dr = ImageDraw.Draw(img)
    w = max(1, int(round(width_m / t.px * ss)))
    for P in paths:
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                pts = [((u + ox) * n * ss, (v + oy * nv / n) * n * ss) for u, v in P]
                dr.line(pts, fill=255, width=w, joint="curve")
    a = np.asarray(img, F32) / 255.0
    a = a.reshape(nv, ss, n, ss).mean((1, 3))
    if soft_m:
        a = t.blur(a, soft_m / t.px)
    return a.astype(F32)


def wander(rng, start, steps, step_len, turn=0.35, heading=None):
    """Random-walk polyline in tile units (unwrapped; periodic_line_mask wraps it)."""
    u, v = start
    a = rng.uniform(0, math.tau) if heading is None else heading
    pts = [(u, v)]
    for _ in range(steps):
        a += rng.normal(0, turn)
        u += math.cos(a) * step_len
        v += math.sin(a) * step_len
        pts.append((u, v))
    return pts


def cavity_ao(t, hm, radii=(0.004, 0.015, 0.05), strength=1.0):
    """AO from a height field in metres (periodic, any aspect)."""
    occ = np.zeros_like(hm)
    for r in radii:
        sig = max(0.6, r / t.px)
        occ += np.clip((t.blur(hm, sig) - hm) / (r * 1.2), 0.0, 1.0) / len(radii)
    return np.clip(1.0 - occ * strength, 0.0, 1.0).astype(F32)


def crack_mask(t, rng, count, length_m, width_m, branch=0.5, turn=0.45, jag_m=0.002, taper=True):
    """Natural crack network: random-walk polylines with tapering width and short side branches, rasterised with
    anti-aliasing and wrapped across the tile, then jagged by a fine domain warp. Returns 0..1 (1 = open crack)."""
    from PIL import Image, ImageDraw
    n, nv = t.n, t.nv
    ss = 2
    img = Image.new("L", (n * ss, nv * ss), 0)
    dr = ImageDraw.Draw(img)
    scale = n * ss                      # tile units -> supersampled px
    step = 0.01 / t.tile                # 1 cm steps (tile units)

    def stroke(P, w0):
        m = len(P)
        for i in range(m - 1):
            f = i / max(1, m - 2)
            w = w0 * ((1 - abs(f * 2 - 1) ** 2) if taper else 1.0) * (0.6 + 0.4 * rng.rand())
            wp = max(1, int(round(w / t.px * ss)))
            (u0, v0), (u1, v1) = P[i], P[i + 1]
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    dr.line([((u0 + ox) * scale, (v0 + oy * nv / n) * scale), ((u1 + ox) * scale, (v1 + oy * nv / n) * scale)], fill=255, width=wp)

    for _ in range(count):
        steps = int(length_m * (0.5 + rng.rand()) / 0.01)
        P = wander(rng, (rng.rand(), rng.rand() * nv / n), steps, step, turn=turn * 0.25)
        stroke(P, width_m)
        for _b in range(int(branch * steps / 30)):
            k = rng.randint(0, len(P))
            Q = wander(rng, P[k], int(steps * rng.uniform(0.1, 0.35)), step, turn=turn * 0.3)
            stroke(Q, width_m * 0.55)
    a = np.asarray(img, F32) / 255.0
    a = a.reshape(nv, ss, n, ss).mean((1, 3)).astype(F32)
    if jag_m > 0:
        a = t.warp(a, jag_m, jag_m * 6, 2)
    return np.clip(a, 0, 1).astype(F32)
