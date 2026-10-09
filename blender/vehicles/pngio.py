"""Dependency-free PNG writer (numpy + zlib); works inside Blender's Python and plain python3.
Arrays are row-major, TOP row first."""
import struct
import zlib

import numpy as np


def _chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path, arr, level=6):
    arr = np.ascontiguousarray(arr)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    h, w, c = arr.shape
    ctype = {1: 0, 2: 4, 3: 2, 4: 6}[c]
    raw = arr.astype(np.uint8).reshape(h, w * c)
    bpp = c
    best = None
    for f in (1, 2):
        if f == 0:
            filt = raw
        elif f == 1:
            filt = raw.copy()
            filt[:, bpp:] = raw[:, bpp:] - raw[:, :-bpp]
        else:
            filt = raw.copy()
            filt[1:] = raw[1:] - raw[:-1]
        data = np.hstack([np.full((h, 1), f, np.uint8), filt]).tobytes()
        comp = zlib.compress(data, level)
        if best is None or len(comp) < len(best):
            best = comp
    ihdr = struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0)
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
