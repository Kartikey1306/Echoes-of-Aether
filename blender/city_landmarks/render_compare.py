"""Before/after render of FBX buildings (e.g. original env Building_* vs the atlas-remapped export).

  Blender -b --factory-startup --python render_compare.py -- out.png fbxA [fbxB ...]   (one row, one column per FBX)
Options after --: --yaw 35 --pitch 12 --dist 1.0 (x auto) --lod 0 --samples 64
"""
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmpreview as LP  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
opts = {"--yaw": 35.0, "--pitch": 12.0, "--dist": 1.0, "--lod": 0, "--samples": 64, "--res": 900}
rest = []
i = 0
while i < len(argv):
    if argv[i] in opts:
        opts[argv[i]] = type(opts[argv[i]])(argv[i + 1]); i += 2
    else:
        rest.append(argv[i]); i += 1
out, fbxs = rest[0], rest[1:]
tmp = []
for k, f in enumerate(fbxs):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    LP.setup(samples=opts["--samples"], res=(opts["--res"], int(opts["--res"] * 1.25)))
    LP.night_world(0.6)
    bpy.ops.import_scene.fbx(filepath=f)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    keep = [o for o in objs if o.name.endswith(f"_LOD{opts['--lod']}")] or objs
    for o in objs:
        if o not in keep:
            bpy.data.objects.remove(o)
    LP.apply_materials(keep)
    mn, mx = LP.bounds(keep)
    LP.ground(600, "asphalt")
    LP.moon(0.15)
    LP.city_lights(mn, mx, seed=4, n=6, power=0.6)
    LP.area((mn.x - 10, mn.y - 25, 18), (math.radians(70), 0, math.radians(-20)), 20, (0.9, 0.55, 1.0), 9000)
    c = (mn + mx) / 2
    hgt = mx.z - mn.z
    size = max(mx.x - mn.x, mx.y - mn.y, hgt)
    LP.camera((c.x, c.y, mn.z + hgt * 0.45), size * 1.55 * opts["--dist"], opts["--yaw"], opts["--pitch"], lens=35)
    p = out.replace(".png", f"_{k}.png")
    LP.render(p)
    tmp.append(p)
# compose
import numpy as np  # noqa: E402
ims = []
for p in tmp:
    im = bpy.data.images.load(p)
    w, h = im.size
    ims.append(np.array(im.pixels[:], np.float32).reshape(h, w, 4))
row = np.concatenate(ims, axis=1)
H, W = row.shape[:2]
img = bpy.data.images.new("sheet", W, H, alpha=True)
img.pixels = row.ravel()
img.filepath_raw = out
img.file_format = "PNG"
img.save()
for p in tmp:
    os.remove(p)
print("[compare] wrote", out)
