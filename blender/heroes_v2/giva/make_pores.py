"""Giva's fine skin pore detail tile (tangent-space normal, seamless): pores on a jittered grid (~0.5 mm apart at the
default tiling), a faint cross-hatched micro-relief (skin lines) and band-limited unevenness. Procedural, numpy + PIL
(system python):   python3 make_pores.py [out.png]
"""
import sys
import numpy as np
from PIL import Image

N = 512
rng = np.random.default_rng(5)


def periodic_noise(sigma_lo, sigma_hi, aniso=(1.0, 1.0)):
    """Band-pass filtered white noise, periodic by construction (FFT)."""
    w = rng.normal(size=(N, N))
    fy = np.fft.fftfreq(N)[:, None] * aniso[1]
    fx = np.fft.fftfreq(N)[None, :] * aniso[0]
    f2 = fx * fx + fy * fy
    band = np.exp(-f2 * (2 * np.pi * sigma_lo) ** 2 / 2) - np.exp(-f2 * (2 * np.pi * sigma_hi) ** 2 / 2)
    out = np.real(np.fft.ifft2(np.fft.fft2(w) * band))
    return out / (out.std() + 1e-9)


def pores():
    h = np.zeros((N, N))
    cell = 7.0
    n = int(N / cell)
    yy, xx = np.mgrid[0:N, 0:N]
    for j in range(n):
        for i in range(n):
            if rng.random() < 0.18:
                continue
            cx = (i + rng.uniform(0.15, 0.85)) * cell
            cy = (j + rng.uniform(0.15, 0.85)) * cell
            r = rng.uniform(1.0, 1.9)
            d = rng.uniform(0.5, 1.0)
            x0, y0 = int(cx) - 5, int(cy) - 5
            ys = (np.arange(y0, y0 + 11) % N)
            xs = (np.arange(x0, x0 + 11) % N)
            dy = (np.arange(y0, y0 + 11) - cy)[:, None]
            dx = (np.arange(x0, x0 + 11) - cx)[None, :]
            pit = d * np.exp(-(dx * dx + dy * dy) / (2 * r * r))
            h[np.ix_(ys, xs)] -= pit
    return h


h = pores()
h += 0.22 * periodic_noise(0.6, 3.0)                                   # fine unevenness
h += 0.12 * np.abs(periodic_noise(0.8, 2.5, (1.0, 0.18)))               # skin lines (two directions)
h += 0.12 * np.abs(periodic_noise(0.8, 2.5, (0.18, 1.0)))
h += 0.18 * periodic_noise(6.0, 24.0)                                  # soft larger undulation
h -= h.mean()
k = 0.6                                                                # slope scale
gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * k
gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * k
nz = 1.0 / np.sqrt(1 + gx * gx + gy * gy)
nx, ny = -gx * nz, gy * nz            # image rows run downwards: +Y (OpenGL-style green up)
img = np.stack([nx * 0.5 + 0.5, ny * 0.5 + 0.5, nz * 0.5 + 0.5], -1)
out = sys.argv[1] if len(sys.argv) > 1 else "Giva_Pores_Normal.png"
Image.fromarray(np.clip(img * 255 + 0.5, 0, 255).astype(np.uint8)).save(out)
print("pores", out, "tilt p95 deg", round(float(np.degrees(np.arccos(np.percentile(nz, 5)))), 1))
