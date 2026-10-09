"""Cycles previews of built landmark-kit FBX files (what Unity imports): a hero 3/4 view at night per asset, plus an
optional street-level view, composed into a contact sheet.

  Blender -b --factory-startup --python render_lm.py -- sheet.png name [name ...] [--street] [--samples 64] [--cols 3]
"""
import glob
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmpaths  # noqa: E402
import lmpreview as LP  # noqa: E402


def fbx_of(name):
    r = os.path.join(lmpaths.RECORDS, name + ".json")
    return os.path.join(lmpaths.KIT, json.load(open(r))["file"])


def render_one(name, out, street=False, samples=64, res=(900, 1100), yaw=28.0, lod=0):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    LP.setup(samples=samples, res=res)
    LP.night_world(0.7, top=(0.01, 0.014, 0.03), horizon=(0.07, 0.045, 0.09))
    bpy.ops.import_scene.fbx(filepath=fbx_of(name))
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    keep = [o for o in objs if o.name.endswith(f"_LOD{lod}")] or objs
    for o in objs:
        if o not in keep:
            bpy.data.objects.remove(o)
    LP.apply_materials(keep)
    mn, mx = LP.bounds(keep)
    LP.ground(2000, "asphalt")
    LP.moon(0.18)
    LP.city_lights(mn, mx, seed=7, n=8, power=1.2 if not street else 0.6)
    c = (mn + mx) / 2
    hgt = mx.z - mn.z
    span = max(mx.x - mn.x, mx.y - mn.y)
    if street:
        cam = LP.camera((c.x, mn.y, 1.7), 1.0, 0, 0, lens=20)
        cam.location = (c.x - span * 0.35, mn.y - max(14.0, span * 0.45), 1.7)
        look = Vector((c.x + span * 0.1, mn.y, min(hgt * 0.45, 22.0)))
        cam.rotation_euler = (look - cam.location).to_track_quat("-Z", "Y").to_euler()
    else:
        dist = max(hgt * 1.25, span * 1.7)
        LP.camera((c.x, c.y, mn.z + hgt * 0.42), dist, yaw, 9, lens=32)
    LP.render(out)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = argv[0]
    names, street, samples, cols, lod = [], False, 64, 3, 0
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--street":
            street = True; i += 1
        elif a == "--samples":
            samples = int(argv[i + 1]); i += 2
        elif a == "--cols":
            cols = int(argv[i + 1]); i += 2
        elif a == "--lod":
            lod = int(argv[i + 1]); i += 2
        else:
            names += [os.path.basename(p)[:-5] for p in sorted(glob.glob(os.path.join(lmpaths.RECORDS, a + ".json")))]; i += 1
    tiles = []
    for n in names:
        p = out.replace(".png", f"_{n}.png")
        render_one(n, p, street=street, samples=samples, lod=lod)
        tiles.append(p)
        print("[render]", n, flush=True)
    ims = []
    for p in tiles:
        im = bpy.data.images.load(p)
        w, h = im.size
        ims.append(np.array(im.pixels[:], np.float32).reshape(h, w, 4))
    rows = []
    for r in range(0, len(ims), cols):
        row = ims[r:r + cols]
        while len(row) < cols:
            row.append(np.zeros_like(ims[0]))
        rows.append(np.concatenate(row, axis=1))
    sheet = np.concatenate(rows[::-1], axis=0)
    H, W = sheet.shape[:2]
    img = bpy.data.images.new("sheet", W, H, alpha=True)
    img.pixels = sheet.ravel()
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()
    for p in tiles:
        os.remove(p)
    print("[render] sheet", out)


main()
