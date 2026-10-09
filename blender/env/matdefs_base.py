"""Shared colour / pattern helpers for material definitions (no Blender imports at module level)."""


def lin(hexstr):
    """sRGB hex -> linear tuple."""
    h = hexstr.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def g(v):
    """sRGB grey level -> linear tuple."""
    x = v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return (x, x, x)


def crack_lines(nb, f, seed, width, keep=0.55):
    """Wiggly crack network: zero-crossings of an fbm, broken up by a second noise."""
    n = nb.noise(f, detail=5, rough=0.6, seed=seed)
    line = nb.smooth(nb.absf(n - 0.5), width, 0.0)
    gate = nb.smooth(nb.noise(f * 0.6, detail=2, seed=seed + 9), keep, keep + 0.08)
    return line * gate


def puddles(nb, h, f, seed, level=0.5, soft=0.06, bias=0.3):
    """Mask of standing water in low areas."""
    return nb.smooth(nb.noise(f, detail=4, rough=0.55, seed=seed) + (0.5 - h) * bias, level, level + soft)
