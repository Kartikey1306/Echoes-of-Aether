"""Inspection sheet of a baked material's maps: full maps (downscaled) on the top row, 1:1 crops below.

  Blender -b --factory-startup --python mapsheet.py -- name [name...]   -> previews/maps_<name>.png
Top row: BaseColor, Normal, Smoothness (MaskMap.A), Metal(R)/AO(G)/Height(B) as RGB.
Bottom row: 1:1 crops (centre 480 px) of BaseColor, Normal, Smoothness and a 2x2 tiling of BaseColor (seam check).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import envpaths  # noqa: E402
import pngio  # noqa: E402

T = 480


def load(path):
    im = bpy.data.images.load(path)
    im.colorspace_settings.name = "Non-Color"
    w, h = im.size
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    return a.reshape(h, w, 4)[::-1]  # top row first, raw values (no colour transform)


def down(a, n):
    h = a.shape[0]
    f = h // n
    if f <= 1:
        return a[:n, :n]
    return a[:f * n, :f * n].reshape(n, f, n, f, -1).mean(axis=(1, 3))


def crop(a, n):
    h = a.shape[0]
    c = h // 2
    return a[c - n // 2:c + n // 2, c - n // 2:c + n // 2]


def rgb(a):
    return (np.clip(a[..., :3], 0, 1) * 255 + 0.5).astype(np.uint8)


def gray(x):
    return np.repeat((np.clip(x, 0, 1) * 255 + 0.5).astype(np.uint8)[..., None], 3, axis=-1)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    st = json.load(open(os.path.join(envpaths.STATE, "materials_baked.json")))
    for name in argv:
        tex = st[name]["textures"]
        P = lambda k: os.path.join(envpaths.UNITY_ENV, tex[k])
        bc = load(P("BaseColor"))
        nm = load(P("Normal"))
        mk = load(P("MaskMap"))
        tiles = [rgb(down(bc, T)), rgb(down(nm, T)), gray(down(mk, T)[..., 3]), rgb(down(mk, T)[..., :3])]
        tiles2 = [rgb(crop(bc, T)), rgb(crop(nm, T)), gray(crop(mk, T)[..., 3])]
        half = down(bc, T // 2)
        tiles2.append(rgb(np.concatenate([np.concatenate([half, half], 1), np.concatenate([half, half], 1)], 0)))
        g = 4
        S = np.full((2 * T + 3 * g, 4 * T + 5 * g, 3), 20, np.uint8)
        for r, row in enumerate((tiles, tiles2)):
            for c, t in enumerate(row):
                y, x = g + r * (T + g), g + c * (T + g)
                S[y:y + T, x:x + T] = t[:T, :T]
        out = os.path.join(envpaths.PREVIEWS, f"maps_{name}.png")
        pngio.write_png(out, S)
        print("[maps]", out, bc.shape)


main()
