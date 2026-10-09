"""Tileable numpy image operations used by the material post-process stage (weathering that needs neighbourhood
information a shader node graph can't express: curvature, cavity dirt, downward drip/rain streaks, wet rims).

All arrays are (res, res) float32, BOTTOM row first (Blender pixel order), so +row = +V = "up" on walls (box UVs map
world Z to V on vertical faces). Every operation wraps around so the texture stays perfectly tileable.
"""
import numpy as np


def _fft_conv(a, k):
    return np.real(np.fft.ifft2(np.fft.fft2(a) * np.fft.fft2(k)))


def blur(a, sigma_px):
    """Wrap-around gaussian blur (FFT)."""
    if sigma_px <= 0:
        return a
    n = a.shape[0]
    f = np.fft.fftfreq(n)
    g = np.exp(-2.0 * (np.pi * sigma_px) ** 2 * (f[:, None] ** 2 + f[None, :] ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def blur_v(a, sigma_px):
    """Blur along V only."""
    n = a.shape[0]
    f = np.fft.fftfreq(n)
    g = np.exp(-2.0 * (np.pi * sigma_px) ** 2 * f[:, None] ** 2)
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def curvature(h, px_m, radius_m=0.004):
    """Signed curvature-ish measure of a height field (metres): >0 on convex edges/ridges, <0 in cavities.
    Normalised by the radius so thresholds are scale independent."""
    s = max(0.7, radius_m / px_m)
    return (h - blur(h, s)) / max(radius_m, 1e-6)


def drip(src, length_m, px_m, jitter=None, gain=4.0, spread_px=0.6):
    """Streaks running DOWN (toward -V) from `src` (0..1): one-sided exponential smear, ~`length_m` long.
    Output = mean of the source over the streak window * gain (so a source covering ~1/gain of the window
    saturates). `jitter` (0..1 array, e.g. noise stretched along V) modulates the streaks per column."""
    n = src.shape[0]
    L = max(2.0, min(length_m / px_m, n * 0.45))
    rows = np.arange(n)
    w = np.exp(-rows / L * 3.0)
    w[rows > 3 * L] = 0
    k = np.zeros((n, n), np.float64)
    # out[y] = sum_r src[y + r] w[r]: each pixel collects from sources above it
    k[(-rows) % n, 0] = w
    if spread_px > 0:
        k = blur(k, spread_px)
    k /= w.sum()
    out = _fft_conv(src.astype(np.float64), k) * gain
    if jitter is not None:
        out = out * jitter
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def rain_streaks(seed_noise, px_m, density=0.5, length_m=0.6):
    """Vertical rain/grime streaks from a noise field (0..1) - sparse starts that run down."""
    starts = smooth(seed_noise, 1.0 - density * 0.25, 1.0 - density * 0.25 + 0.04)
    return drip(starts, length_m, px_m, gain=6.0)


def edge_mask(h, px_m, radius_m=0.003, lo=0.15, hi=0.6):
    """Convex-edge mask (0..1) from height (metres)."""
    c = curvature(h, px_m, radius_m)
    return smooth(c, lo, hi)


def cavity_mask(h, px_m, radius_m=0.01, lo=0.1, hi=0.6):
    c = -curvature(h, px_m, radius_m)
    return smooth(c, lo, hi)


def grow(mask, px):
    """Soft dilation."""
    return np.clip(blur(mask, px) * 3.0, 0.0, 1.0)


def rim(mask, px):
    """Soft ring just outside a mask (e.g. damp rim around puddles)."""
    g = blur(mask, px)
    return np.clip((g - mask) * 3.0, 0.0, 1.0)


def lerp(a, b, t):
    t = np.asarray(t, np.float32)
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    colour = (a.ndim >= 1 and a.shape[-1] == 3 and a.ndim != 2) or (b.ndim >= 1 and b.shape[-1] == 3 and b.ndim != 2)
    if t.ndim == 2 and colour:
        t = t[..., None]
    return a + (b - a) * t


def mulc(c, f):
    f = np.asarray(f, np.float32)
    return c * (f[..., None] if f.ndim == 2 else f)
