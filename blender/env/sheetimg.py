"""Compose PNG files into one contact sheet (Blender python; any sizes, resized by nearest-neighbour).
  Blender -b --factory-startup --python sheetimg.py -- out.png cols cell_px in1.png in2.png ...
"""
import sys
import bpy
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import pngio

a = sys.argv[sys.argv.index("--") + 1:]
out, cols, cell = a[0], int(a[1]), int(a[2])
tiles = []
for p in a[3:]:
    im = bpy.data.images.load(p)
    im.colorspace_settings.name = "Non-Color"
    w, h = im.size
    px = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)[::-1, :, :3]
    ys = (np.arange(cell) * h / cell).astype(int)
    xs = (np.arange(cell) * w / cell).astype(int)
    tiles.append((np.clip(px[ys][:, xs], 0, 1) * 255 + 0.5).astype(np.uint8))
rows = (len(tiles) + cols - 1) // cols
g = 4
S = np.full((rows * (cell + g) + g, cols * (cell + g) + g, 3), 20, np.uint8)
for i, t in enumerate(tiles):
    r, c = divmod(i, cols)
    S[g + r * (cell + g):g + r * (cell + g) + cell, g + c * (cell + g):g + c * (cell + g) + cell] = t
pngio.write_png(out, S)
print("[sheet]", out)
