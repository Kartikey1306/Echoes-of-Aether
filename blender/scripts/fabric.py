"""Texture building blocks evaluated per texel (1-D arrays of covered texels) for garments, armour, boots, gloves.

Heights are in metres (converted to tangent-space normals by texbake.height_to_normal using metres-per-texel).
Mask channels for garments follow the Unity contract: R accent panel, G trim/lighten, B glow, A seam/occlusion.
"""
import math
import numpy as np
from texbake import fbm3, vnoise3, worley3, hash3, smoothstep as ss


class Layer:
    """Accumulates height (m), R (accent), G (trim), A (seam/darken) and extra channels for a set of texels."""

    def __init__(self, n):
        self.h = np.zeros(n, np.float32)
        self.R = np.zeros(n, np.float32)
        self.G = np.zeros(n, np.float32)
        self.B = np.zeros(n, np.float32)
        self.A = np.zeros(n, np.float32)
        self.rough = np.zeros(n, np.float32)   # extra roughness 0..1 (fuzzy patches)


# ----------------------------------------------------------------------------- seam primitives
# Every seam is (sdf metres, along metres); seams are rendered with groove + puckering + optional stitches.


def seam(L, d, along, mask=1.0, depth=0.0007, width=0.0009, stitch=(0.0032,), stitch_side=0, dash=0.0032, thread=0.18, pucker=0.00025):
    """Draw a seam on Layer L. d: signed distance (m) to the seam line; along: coordinate along the seam (m)."""
    m = np.asarray(mask, np.float32) * np.ones_like(d)
    g = np.exp(-(d / width) ** 2)
    L.h -= depth * g * m
    L.h += pucker * np.exp(-((np.abs(d) - width * 2.6) / (width * 1.6)) ** 2) * m * (0.6 + 0.4 * np.sin(along / 0.004 * 2 * math.pi))
    L.A = np.maximum(L.A, 0.55 * g * m)
    for off in stitch:
        for sgn in ((1, -1) if stitch_side == 0 else (stitch_side,)):
            dd = d - sgn * off
            line = np.exp(-(dd / 0.00042) ** 2)
            ph = (along / dash) % 1.0
            dash_m = ss(0.05, 0.15, ph) * (1 - ss(0.62, 0.72, ph))
            st = line * dash_m * m
            L.h += 0.00022 * st
            L.h -= 0.00018 * line * (1 - dash_m) * m  # thread holes between dashes
            L.G = np.maximum(L.G, thread * st)
            L.A = np.maximum(L.A, 0.12 * line * (1 - dash_m) * m)


def panel_edge(L, d, mask=1.0, raise_=0.0006, soft=0.004):
    """Raise the panel on the positive side of d (padded/layered look) with a soft roll toward the seam."""
    m = np.asarray(mask, np.float32) * np.ones_like(d)
    L.h += raise_ * ss(0.0, soft, d) * m


# ----------------------------------------------------------------------------- surface patterns


def triplanar_grid(P, N, cell, width):
    """Lines of a square grid projected triplanarly (0..1 line intensity)."""
    w = np.abs(N) ** 4
    w /= w.sum(1, keepdims=True) + 1e-9
    out = 0
    for ax, (i, j) in enumerate(((1, 2), (0, 2), (0, 1))):
        u = P[:, i] / cell; v = P[:, j] / cell
        du = np.abs(u - np.round(u)) * cell; dv = np.abs(v - np.round(v)) * cell
        line = np.maximum(np.exp(-(du / width) ** 2), np.exp(-(dv / width) ** 2))
        out = out + w[:, ax] * line
    return out


def ripstop(L, P, N, mask=1.0, cell=0.0055, amp=0.00012):
    g = triplanar_grid(P, N, cell, 0.00045)
    L.h += amp * g * mask
    L.h += amp * 0.6 * fbm3(P, 900.0, 2, 3.1) * mask  # fibre noise


def knit(L, P, N, mask=1.0, period=0.0028, amp=0.00014, axis=2):
    """Fine rib knit (cuffs, collar lining): ridges across `axis`."""
    v = P[:, axis] / period
    L.h += amp * (np.abs(np.sin(v * math.pi)) - 0.6) * mask


def quilt(L, u, v, mask, q=0.032, pad=0.0022, line=0.0011, stitch_dash=0.003):
    """Diamond quilting over 2-D coordinates (u, v metres): puffy cells, stitched valleys."""
    a = (u + v) / q; b = (u - v) / q
    da = np.abs(a - np.round(a)) * q / 1.4142; db = np.abs(b - np.round(b)) * q / 1.4142
    d = np.minimum(da, db)
    puff = ss(0.0, q * 0.32, d)
    L.h += pad * (puff - 1.0) * mask
    valley = np.exp(-(d / line) ** 2)
    L.A = np.maximum(L.A, 0.35 * valley * mask)
    along = np.where(da < db, (u - v), (u + v)) / 1.4142
    ph = (along / stitch_dash) % 1.0
    L.G = np.maximum(L.G, 0.12 * valley * (ph < 0.6) * mask)


def molle(L, u, v, mask, row=0.038, band=0.025, tack=0.038, height=0.0016):
    """MOLLE/PALS webbing rows: raised horizontal bands with bar-tack stitching every `tack` metres."""
    rv = (v / row) % 1.0 * row
    inband = ss(0.0, 0.0015, rv) * (1 - ss(band - 0.0015, band, rv))
    L.h += height * inband * mask
    L.A = np.maximum(L.A, 0.45 * (1 - ss(0.0, 0.003, np.minimum(rv, np.abs(rv - band)))) * mask * (rv < band + 0.003))
    tu = np.abs(((u / tack) % 1.0) - 0.5) * tack
    bar = np.exp(-(tu / 0.0012) ** 2) * inband
    L.h -= 0.0007 * bar * mask
    L.A = np.maximum(L.A, 0.35 * bar * mask)
    # webbing weave
    L.h += 0.00012 * np.sin(u / 0.0011 * math.pi) * inband * mask


def velcro(L, P, mask):
    L.h += 0.00025 * fbm3(P, 2200.0, 2, 9.0) * mask
    L.rough = np.maximum(L.rough, 0.8 * mask)
    L.A = np.maximum(L.A, 0.15 * mask)


def zipper(L, d, along, mask=1.0, tape=0.0065, teeth=0.0024):
    """Zipper: tape (trim) band with interlocking teeth bumps along the centre line."""
    m = np.asarray(mask, np.float32) * np.ones_like(d)
    band = 1 - ss(tape * 0.5, tape * 0.5 + 0.0006, np.abs(d))
    L.G = np.maximum(L.G, 0.55 * band * m)
    ph = (along / teeth) % 1.0
    tooth = (np.abs(d) < 0.0022) * (0.5 + 0.5 * np.cos((ph + (d > 0) * 0.5) * 2 * math.pi))
    L.h += 0.0008 * tooth * m + 0.0004 * band * m
    L.G = np.maximum(L.G, 0.8 * tooth * m)
    L.A = np.maximum(L.A, 0.4 * np.exp(-((np.abs(d) - tape * 0.5) / 0.0006) ** 2) * m)


def wrinkles(L, P, axis_dir, mask, wavelength=0.012, amp=0.0006, seed=0.0):
    """Anisotropic fabric wrinkles: ridges perpendicular to axis_dir, broken up by noise."""
    s = P @ np.asarray(axis_dir) / wavelength
    warp = 1.5 * fbm3(P, 30.0, 2, seed)
    r = np.sin((s + warp) * 2 * math.pi)
    br = ss(-0.2, 0.6, fbm3(P, 22.0, 2, seed + 4))
    L.h += amp * r * br * mask


# ----------------------------------------------------------------------------- hard-surface wear


def scratches(lx, ly, plate, density=120, seed=0.0, length=(0.004, 0.03), width=0.00025):
    """Fine random scratches in 2-D plate space; returns 0..1 intensity."""
    out = np.zeros(len(lx), np.float32)
    rng = np.random.default_rng(int(seed * 1000) + 7)
    ids = np.unique(np.round(plate).astype(int))
    for pid in ids:
        sel = np.where(np.round(plate).astype(int) == pid)[0]
        if len(sel) == 0:
            continue
        x, y = lx[sel], ly[sel]
        xmn, xmx, ymn, ymx = x.min(), x.max(), y.min(), y.max()
        area = max((xmx - xmn) * (ymx - ymn), 1e-6)
        n = int(density * area / 0.01) + 3
        acc = np.zeros(len(sel), np.float32)
        for _ in range(n):
            cx, cy = rng.uniform(xmn, xmx), rng.uniform(ymn, ymx)
            ang = rng.uniform(0, math.pi)
            ln = rng.uniform(*length)
            ax_, ay_ = cx - math.cos(ang) * ln / 2, cy - math.sin(ang) * ln / 2
            bx_, by_ = cx + math.cos(ang) * ln / 2, cy + math.sin(ang) * ln / 2
            dx, dy = bx_ - ax_, by_ - ay_
            t = np.clip(((x - ax_) * dx + (y - ay_) * dy) / (dx * dx + dy * dy), 0, 1)
            d = np.hypot(x - (ax_ + t * dx), y - (ay_ + t * dy))
            acc = np.maximum(acc, np.exp(-(d / width) ** 2) * (0.4 + 0.6 * np.sin(t * math.pi)) * rng.uniform(0.4, 1.0))
        out[sel] = acc
    return out


def edge_wear(wear, P, amount=1.0, seed=0.0):
    """Chipped paint mask from the per-vertex `wear` attribute broken up by noise (1 = bare metal)."""
    n = fbm3(P, 180.0, 4, seed) * 0.5 + 0.5
    chips = ss(0.55, 0.62, n * 0.65 + wear * 0.55 * amount)
    return np.clip(chips, 0, 1)


def grime(P, ao, cavity, seed=0.0):
    n = fbm3(P, 25.0, 4, seed) * 0.5 + 0.5
    return np.clip((1 - ao) * 0.9 + cavity * 0.6 + (n - 0.55) * 0.5, 0, 1)
