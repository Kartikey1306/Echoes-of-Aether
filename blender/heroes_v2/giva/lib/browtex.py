"""Procedural brow texture: individual tapered hair strands painted inside the brow card's envelope (taken from a
CC0 MakeHuman system brow texture), growth direction rising at the brow head, diagonal in the body, flat at the
tail. Output RGBA (colour dark neutral, the game desaturates and tints with the hair colour)."""
import math
import numpy as np
import gv


def _resize_nearest(a, size):
    h, w = a.shape[:2]
    yi = (np.arange(size) * h / size).astype(int)
    xi = (np.arange(size) * w / size).astype(int)
    return a[yi][:, xi]


def _blur(a, r):
    out = a.astype(np.float32)
    for axis in (0, 1):
        acc = np.zeros_like(out)
        for k in range(-r, r + 1):
            acc += np.roll(out, k, axis)
        out = acc / (2 * r + 1)
    return out


def make(src_rgba, size=1024, seed=7, density=1.0):
    """src_rgba: float (H,W,4) of the source brow texture (row 0 = bottom). Returns (size,size,4)."""
    rng = np.random.default_rng(seed)
    a = _resize_nearest(src_rgba[..., 3], size)
    env = np.clip(_blur(a, size // 128) * 1.6, 0, 1)
    # dilate the envelope a little (fuller brows), keep the shape
    env = np.clip(_blur(env, size // 110) * 1.45, 0, 1)
    out_a = np.zeros((size, size), np.float32)
    out_c = np.zeros((size, size), np.float32)
    # two brows stacked vertically: process each connected band separately (rows with envelope)
    rows = np.nonzero(env.max(1) > 0.2)[0]
    if len(rows) == 0:
        return np.zeros((size, size, 4), np.float32)
    bands = np.split(rows, np.nonzero(np.diff(rows) > 4)[0] + 1)
    for band in bands:
        y0, y1 = band.min(), band.max()
        sub = env[y0:y1 + 1]
        cols = np.nonzero(sub.max(0) > 0.2)[0]
        x0, x1 = cols.min(), cols.max()
        # centre line v(u) and thickness
        cy = np.zeros(x1 - x0 + 1)
        for i, x in enumerate(range(x0, x1 + 1)):
            col = sub[:, x]
            cy[i] = (np.arange(len(col)) * col).sum() / max(col.sum(), 1e-6) + y0
        cy = np.convolve(np.pad(cy, 8, mode="edge"), np.ones(17) / 17, mode="valid")
        # which end is the brow head (thicker)?
        thick = (sub > 0.3).sum(0)[x0:x1 + 1]
        k = max(1, len(thick) // 5)
        flip = thick[-k:].mean() > thick[:k].mean()
        n = int((x1 - x0) * (y1 - y0) * 0.09 * density)
        for _ in range(n):
            x = rng.uniform(x0, x1)
            y = rng.uniform(y0, y1)
            e = env[int(y), int(x)]
            if rng.random() > e:
                continue
            t = (x - x0) / max(x1 - x0, 1)          # 0 head (inner) .. 1 tail
            if flip:
                t = 1 - t
            # feathered brow head (sparser, softer) and a tapering tail: no blunt dark block at either end
            if rng.random() > 0.4 + 0.6 * gv.ss(0.0, 0.2, t) * (1 - 0.5 * gv.ss(0.8, 1.0, t)):
                continue
            i = int(x - x0)
            i2 = min(i + 6, len(cy) - 1)
            i1 = max(i - 6, 0)
            tan = math.atan2(cy[i2] - cy[i1], (i2 - i1))
            # growth angle relative to the brow line: steep at the head, flat at the tail
            rel = math.radians(70) * (1 - gv.ss(0.0, 0.35, t)) + math.radians(22) * gv.ss(0.0, 0.35, t) * (1 - gv.ss(0.5, 1.0, t)) \
                + math.radians(6) * gv.ss(0.5, 1.0, t)
            # upper half of the brow points a bit more downward (hairs meet along the line)
            above = (y - cy[min(i, len(cy) - 1)]) / max((y1 - y0) * 0.5, 1)
            rel -= math.radians(18) * np.clip(above, -1, 1)
            ang = tan + rel + rng.normal(0, math.radians(8))
            if flip:
                # mirror: growth from the head (right) towards the tail (left)
                ang = math.pi - (-tan + rel + rng.normal(0, math.radians(8))) if False else (math.pi + tan - rel)
            L = size * rng.uniform(0.012, 0.022) * (1.15 - 0.4 * t)
            w = size * rng.uniform(0.0012, 0.0021)
            dx, dy = math.cos(ang) * L, math.sin(ang) * L
            bx0, bx1 = int(min(x, x + dx) - 3), int(max(x, x + dx) + 3)
            by0, by1 = int(min(y, y + dy) - 3), int(max(y, y + dy) + 3)
            bx0, by0 = max(bx0, 0), max(by0, 0)
            bx1, by1 = min(bx1, size - 1), min(by1, size - 1)
            if bx1 <= bx0 or by1 <= by0:
                continue
            ys, xs = np.mgrid[by0:by1 + 1, bx0:bx1 + 1]
            px, py = xs - x, ys - y
            s = np.clip((px * dx + py * dy) / (L * L), 0, 1)
            d = np.hypot(px - dx * s, py - dy * s)
            width = w * (1 - 0.75 * s)                 # tapered tip
            cov = np.clip(1 - d / np.maximum(width, 0.3), 0, 1) * (s > 0) * (s < 1)
            alpha = rng.uniform(0.55, 0.95) * (0.6 + 0.4 * e) * (0.6 + 0.4 * gv.ss(0.0, 0.15, t))
            sl = (slice(by0, by1 + 1), slice(bx0, bx1 + 1))
            out_a[sl] = 1 - (1 - out_a[sl]) * (1 - cov * alpha)
            shade = rng.uniform(0.6, 1.0)
            out_c[sl] = np.maximum(out_c[sl], cov * shade)
    col = 0.06 + 0.07 * (1 - out_c)
    img = np.zeros((size, size, 4), np.float32)
    img[..., 0] = col * 1.05
    img[..., 1] = col * 0.92
    img[..., 2] = col * 0.85
    img[..., 3] = np.clip(out_a, 0, 1)
    return img
