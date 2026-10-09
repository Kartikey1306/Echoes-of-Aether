"""Re-rasterise Kael's catalog tattoo designs (blender/custom/tattoo.py, unchanged 3-D designs) into the NEW exported
Body UV layout. Only the Ink/Glow textures are rewritten (same file names, so the catalog entries and Unity GUIDs stay);
no thumbnails, no catalog changes. Needed because the remade Body has a new UV layout (the old maps landed on the face
as dark patches).

  blender -b blends/kael_s6_deform.blend --python tattoo_refit.py [-- --out <dir>]
"""
import bpy, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
CUSTOM = os.path.join(GAME, "blender", "custom")
sys.path.insert(0, CUSTOM)
import numpy as np
import common as C          # puts blender/custom/lib (frozen helpers) first on sys.path
import gear
import tattoo as TT

a = C.args()
out_dir = a[a.index("--out") + 1] if "--out" in a else TT.OUT_DIR
os.makedirs(out_dir, exist_ok=True)
rig = bpy.data.objects["Kael"]
full = bpy.data.objects.get("BodyFull") or bpy.data.objects["Body"]
body = bpy.data.objects["Body"]
for uv in body.data.uv_layers:
    if uv.name != "UVOld":
        body.data.uv_layers.active = uv
        break
ctx = gear.Ctx(full, rig, "Kael")
ch = TT.Charts(ctx)
mat = body.data.materials[0].name
for i, (did, label, vis) in enumerate(TT.DESIGNS["kael"]):
    rng = np.random.default_rng(1000 + i * 17)
    regs = TT.design("kael", did, ch, rng)
    iv, gv, frac, n_ink = TT.raster_maps(body, regs, TT.SIZE, rng, mat)
    C.write_png(np.stack([iv] * 3, -1), os.path.join(out_dir, f"kael_{did}_Ink.png"), "RGB")
    C.write_png(gv, os.path.join(out_dir, f"kael_{did}_Glow.png"), "RGB")
    C.log("TATTOO", did, "visible ink texels", n_ink)
