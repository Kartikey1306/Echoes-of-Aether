"""Minimal dependency-free PNG writer/reader helpers (numpy + zlib) usable inside Blender's Python.

Arrays are row-major with the TOP row first (image convention). Blender pixel buffers are bottom row
first, so callers flip with arr[::-1] when moving between the two.
"""
import struct
import zlib

import numpy as np


def _chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path, arr, level=6):
    """Write uint8/uint16 array (H,W) / (H,W,2|3|4) as PNG. Picks the best of filter None/Sub/Up."""
    arr = np.ascontiguousarray(arr)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    h, w, c = arr.shape
    depth = 16 if arr.dtype == np.uint16 else 8
    ctype = {1: 0, 2: 4, 3: 2, 4: 6}[c]
    if depth == 16:
        raw = arr.astype(">u2").view(np.uint8).reshape(h, w * c * 2)
        bpp = c * 2
    else:
        raw = arr.astype(np.uint8).reshape(h, w * c)
        bpp = c
    best = None
    for f in (0, 1, 2):
        if f == 0:
            filt = raw
        elif f == 1:
            filt = raw.copy()
            filt[:, bpp:] = raw[:, bpp:] - raw[:, :-bpp]  # uint8 wraps mod 256
        else:
            filt = raw.copy()
            filt[1:] = raw[1:] - raw[:-1]
        data = np.hstack([np.full((h, 1), f, np.uint8), filt]).tobytes()
        comp = zlib.compress(data, level)
        if best is None or len(comp) < len(best):
            best = comp
    ihdr = struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, 0)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(_chunk(b"IHDR", ihdr))
        fh.write(_chunk(b"IDAT", best))
        fh.write(_chunk(b"IEND", b""))


def to_u8(x):
    return (np.clip(x, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def linear_to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1.0 / 2.4) - 0.055)


def srgb_to_linear(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))
