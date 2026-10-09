"""Re-project the catalog's Lyra tattoo textures (authored in the previous Body UV layout) onto the new Giva skin
UV layout through the 3D surface (each new texel -> nearest point on the previous Body -> its UV -> sample).
Output: out/tattoo_remap/<same file names>.png (drop-in replacements for Resources/Characters/Custom/Tattoos/).

  blender -b out/giva_face.blend --python remap_tattoos.py
"""
import bpy, sys, os, json, importlib, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import gv, raster
SIZE = 2048
OUTD = os.path.join(gv.OUT, "tattoo_remap")
os.makedirs(OUTD, exist_ok=True)
rig = bpy.data.objects[gv.RIG]
body = bpy.data.objects["Body"]
maps = raster.Maps(SIZE)
raster.rasterize(maps, body, 0)
# previous Body from the committed FBX
scr = os.path.join(gv.OUT, "export_tmp", "Lyra_committed.fbx")
if not os.path.exists(scr):
    os.makedirs(os.path.dirname(scr), exist_ok=True)
    open(scr, "wb").write(subprocess.run(["git", "-C", gv.ROOT, "show", "HEAD:unity/EchoesOfAether/Assets/Art/Characters/Lyra/Lyra.fbx"],
                                         capture_output=True).stdout)
before = set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=scr, automatic_bone_orientation=False)
new = [o for o in bpy.data.objects if o not in before]
old = next(o for o in new if o.type == "MESH" and o.name.split(".")[0] == "Body")
mw = old.matrix_world
me = old.data
me.calc_loop_triangles()
co = np.array([mw @ v.co for v in me.vertices])
tris = np.array([t.vertices[:] for t in me.loop_triangles])
tl = np.array([t.loops[:] for t in me.loop_triangles])
uv = np.empty(len(me.loops) * 2, np.float32)
me.uv_layers.active.data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
tree = BVHTree.FromPolygons([Vector(c) for c in co], tris.tolist(), all_triangles=True)
m = maps.mask
Pm = maps.P[m]
UV = np.full((len(Pm), 2), np.nan, np.float32)
for i, p in enumerate(Pm):
    loc, n, fi, d = tree.find_nearest(Vector(p), 0.025)
    if fi is None:
        continue
    a, b, c = co[tris[fi]]
    w = gv._bary(np.array(loc), a, b, c)
    UV[i] = w @ uv[tl[fi]]
gv.log("mapped texels", int(np.isfinite(UV[:, 0]).sum()), "of", len(Pm))
cat = json.load(open(os.path.join(gv.CUSTOM, "catalog.json")))
done = []
for it in cat.get("tattoos", []):
    if it.get("hero") != "lyra":
        continue
    for key in ("ink", "glow"):
        rel = it.get(key)
        if not rel:
            continue
        src = os.path.join(gv.CUSTOM, rel + ".png")
        img = gv.read_image(src)
        H, W = img.shape[:2]
        okk = np.isfinite(UV[:, 0])
        x = np.clip(UV[okk, 0] * W - 0.5, 0, W - 1.001)
        y = np.clip(UV[okk, 1] * H - 0.5, 0, H - 1.001)
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = (x - x0)[:, None], (y - y0)[:, None]
        s = (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)
        neutral = np.array((0.5, 0.5, 0.5, 1.0)) if key == "ink" else np.array((0, 0, 0, 1.0))
        outimg = np.tile(neutral.astype(np.float32), (SIZE, SIZE, 1))
        vals = np.tile(neutral.astype(np.float32), (len(Pm), 1))
        vals[okk] = s
        outimg[m] = vals
        outimg = raster.dilate(outimg, m, 6)
        gv.write_image(outimg, os.path.join(OUTD, os.path.basename(rel) + ".png"))
        done.append(os.path.basename(rel) + ".png")
gv.log("remapped", done)
