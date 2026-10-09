"""
Procedural rain surface data (numpy): puddle ripple normal flipbook + wet-surface droplet / streak maps.

  Rain/rain_ripple_n.png     1024x1024 normal map, 4x4 flipbook (frame i: column i % 4, row i // 4 from the TOP),
                             256 px per frame, every frame tiles; the 16 frames loop. Rain drops hitting a puddle:
                             damped capillary wave packets (leading ring + 2-3 trailing crests), overlapping.
  Rain/rain_drops_n.png      1024x1024 tileable normal map: beaded droplets of 0.5-6 px radius (static wet surface).
  Rain/rain_streaks.png      1024x1024 tileable linear RGBA: RG streak normal (0.5 centred), B streak/bead mask,
                             A flow phase (0..1 sawtooth down each rivulet; animate with frac(A + t * speed)).

Usage: Blender -b -P rain_ripples.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np  # noqa: E402
import fxkit as K  # noqa: E402

RNG = np.random.default_rng(20261004)


def periodic_delta(a, b):
    d = a - b
    return d - np.round(d)


def ripple_frames(n=256, frames=16, drops=46):
    """Height field per frame (tile units: the frame is 1x1 and wraps)."""
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float32)
    xs = (xs + 0.5) / n
    ys = (ys + 0.5) / n
    px = RNG.random(drops)
    py = RNG.random(drops)
    t0 = RNG.random(drops)
    size = 0.55 + RNG.random(drops) ** 1.5 * 0.75
    out = []
    life = 0.62                       # fraction of the loop a ripple lives
    for f in range(frames):
        t = f / frames
        h = np.zeros((n, n), np.float32)
        for i in range(drops):
            a = (t - t0[i]) % 1.0
            if a > life:
                continue
            u = a / life                                      # 0..1 over the ripple's life
            rmax = 0.11 * size[i]
            r = rmax * (1 - (1 - u) ** 1.6)                   # fast at impact, slowing
            lam = 0.018 * (0.75 + 0.5 * size[i])
            dx = periodic_delta(xs, px[i])
            dy = periodic_delta(ys, py[i])
            d = np.sqrt(dx * dx + dy * dy)
            k = 2 * math.pi / lam
            behind = r - d                                      # >0 inside the leading front
            env = np.exp(-np.square(np.maximum(-behind, 0) / (lam * 0.35)))   # sharp outside the front
            env *= np.exp(-np.maximum(behind, 0) / (lam * 0.75))              # 1-2 trailing crests, decaying inward
            amp = (1 - u) ** 1.4 * size[i]
            # impact splash dimple at the start
            dimple = -0.8 * math.exp(-a / 0.03) * np.exp(-np.square(d / (lam * 0.6)))
            h += amp * np.cos(k * behind) * env + dimple * size[i]
        out.append(h)
    return out


def ripple_normals():
    frames = ripple_frames()
    n = frames[0].shape[0]
    tiles = []
    for h in frames:
        nm = K.height_to_normal(h, strength=n * 0.022)
        tiles.append(nm * 0.5 + 0.5)
    at = K.atlas(tiles, 4, 4)
    K.save_png(at, os.path.join(K.UNITY_FX, "Rain", "rain_ripple_n.png"), dither=False)
    # preview: shade with a fake neon-lit environment (reflection of a bright strip)
    prev = []
    for t in tiles[:8]:
        nm = t * 2 - 1
        refl = np.clip(nm[:, :, 0] * 0.8 + nm[:, :, 1] * 0.6, -1, 1)
        c = 0.05 + 0.9 * np.clip(refl * 6, 0, 1) ** 2
        prev.append(np.stack([c * 0.35, c * 0.75, c], -1))
    K.save_png(K.atlas(prev, 8, 1), os.path.join(K.PREV, "rain_ripple_preview.png"), to_srgb=True)


def drops_normal(n=1024, count=5200):
    """Beaded droplets on a wet surface (spherical caps, periodic placement, no overlap growth)."""
    h = np.zeros((n, n), np.float32)
    occ = np.zeros((n, n), np.float32)
    rad = 0.6 + (RNG.random(count) ** 3.2) * 5.6        # many tiny, few big
    order = np.argsort(-rad)
    for i in order:
        r = rad[i]
        cx, cy = RNG.random() * n, RNG.random() * n
        R = int(math.ceil(r + 1))
        ys = (np.arange(int(cy) - R, int(cy) + R + 1)) % n
        xs = (np.arange(int(cx) - R, int(cx) + R + 1)) % n
        yy, xx = np.meshgrid(np.arange(int(cy) - R, int(cy) + R + 1) - cy, np.arange(int(cx) - R, int(cx) + R + 1) - cx, indexing="ij")
        # slightly squashed vertically (drops sag)
        d2 = (xx / r) ** 2 + (yy / (r * 1.12)) ** 2
        cap = np.sqrt(np.clip(1 - d2, 0, 1)) * r * 0.55
        sub = np.ix_(ys, xs)
        if (occ[sub] * (cap > 0)).max() > 0.5 and r > 1.5:
            continue
        h[sub] = np.maximum(h[sub], cap)
        occ[sub] = np.maximum(occ[sub], (cap > 0).astype(np.float32))
    nm = K.height_to_normal(h, strength=1.0)
    K.save_png(nm * 0.5 + 0.5, os.path.join(K.UNITY_FX, "Rain", "rain_drops_n.png"), dither=False)
    return h


def streaks(n=1024, count=70):
    """Rivulets running down a wall / glass: wandering vertical channels with beads, flow phase in A."""
    h = np.zeros((n, n), np.float32)
    mask = np.zeros((n, n), np.float32)
    phase = np.zeros((n, n), np.float32)
    y = np.arange(n, dtype=np.float32)
    for i in range(count):
        x0 = RNG.random() * n
        w = 1.2 + RNG.random() ** 2 * 3.2
        ph0 = RNG.random()
        cycles = float(RNG.integers(1, 4))           # phase wraps an integer number of times (tiles vertically)
        # wander: sum of periodic sines (integer frequencies -> tileable in y)
        xs = x0 + sum(RNG.normal(0, 6.0 / (k + 1)) * np.sin(2 * math.pi * (k + 1) * y / n + RNG.random() * 6.28) for k in range(5))
        # beads along the trail
        bead = 1 + 0.6 * np.clip(np.sin(2 * math.pi * (y / n * RNG.integers(8, 20) + RNG.random())), 0, 1) ** 6
        # partial streaks: the trail fades in and out along y (dry gaps)
        presence = np.clip(0.5 + 0.9 * np.sin(2 * math.pi * (y / n * RNG.integers(1, 3) + RNG.random())), 0, 1)
        for j in range(n):
            if presence[j] <= 0.01:
                continue
            ww = w * bead[j]
            c = xs[j]
            x_lo, x_hi = int(math.floor(c - ww - 1)), int(math.ceil(c + ww + 1))
            xx = np.arange(x_lo, x_hi + 1)
            d = (xx - c) / ww
            prof = np.sqrt(np.clip(1 - d * d, 0, 1))
            idx = xx % n
            val = prof * ww * 0.6 * presence[j]
            h[j, idx] = np.maximum(h[j, idx], val)
            m = (prof > 0).astype(np.float32) * presence[j]
            sel = m > mask[j, idx]
            mask[j, idx] = np.maximum(mask[j, idx], m)
            # flow phase: increases downward (row index grows downward in the image)
            p = (ph0 + cycles * j / n) % 1.0
            phase[j, idx[sel]] = p
    nm = K.height_to_normal(K.blur(h, 0.6, wrap=True), strength=1.0)
    out = np.stack([nm[:, :, 0] * 0.5 + 0.5, nm[:, :, 1] * 0.5 + 0.5, mask, phase], -1)
    K.save_png(out, os.path.join(K.UNITY_FX, "Rain", "rain_streaks.png"), dither=False)
    return h


def main():
    ripple_normals()
    if "--ripples-only" in K.args():
        return
    hd = drops_normal()
    hs = streaks()
    # preview of the wet-surface maps (shaded heights)
    def shade(h):
        nm = K.height_to_normal(h, 1.0)
        l = np.clip(nm[:, :, 0] * -0.5 + nm[:, :, 1] * 0.6 + nm[:, :, 2] * 0.62, 0, 1)
        return np.stack([l * 0.6, l * 0.75, l], -1)
    K.save_png(np.concatenate([shade(hd)[:512, :512], shade(hs)[:512, :512]], axis=1), os.path.join(K.PREV, "rain_surface_preview.png"), to_srgb=True)


if __name__ == "__main__":
    main()
