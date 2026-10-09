"""Stage 3 - Kael v2 outfit geometry on the rigged rest body.

  blender -b blends/kael_s2_rig.blend --python build_outfit.py -- [--parts top,pants,...] [--preview] [--save]
"""
import bpy, sys, os, json, math, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
from mathutils import Vector
import garment as G, outfit_k2 as OK2, meshops
for m in (G, OK2, meshops):
    importlib.reload(m)
import outfit_k3 as OK
importlib.reload(OK)

a = K.args()
rig = bpy.data.objects["Kael"]
body = bpy.data.objects["Body"]
mh = bpy.data.objects["BodyMH"]
B = G.BodyInfo(rig, body, mh)
K.log("BodyInfo", len(B.co), "verts", len(B.mh_co), "cage")
O = OK.Outfit(B)
parts = (K.opt(a, "--parts") or "pants,top").split(",")
for p in parts:
    getattr(O, p)()
for n, o in O.objs.items():
    fl = G.fix_orientation(o)
    K.log("PART", n, len(o.data.vertices), "v", sum(len(f.vertices) - 2 for f in o.data.polygons), "tris", "flipped pieces", fl)

PREV = {"Garment_Top": ((0.10, 0.11, 0.09), 0.8, 0.0), "Garment_Pants": ((0.06, 0.065, 0.06), 0.8, 0.0), "Armor": ((0.5, 0.48, 0.44), 0.4, 0.3),
        "Metal": ((0.6, 0.6, 0.62), 0.3, 1.0), "Boots": ((0.05, 0.05, 0.05), 0.6, 0.0), "Gloves": ((0.05, 0.05, 0.05), 0.6, 0.0),
        "Cloth_Gear": ((0.035, 0.036, 0.038), 0.8, 0.0), "Cloth_Jacket": ((0.04, 0.042, 0.047), 0.6, 0.0), "Glow": ((0.0, 0.9, 1.0), 0.3, 0.0), "Glow2": ((1.0, 0.17, 0.84), 0.3, 0.0),
        "Screen": ((0.0, 0.5, 0.6), 0.2, 0.0), "Skin": ((0.55, 0.40, 0.33), 0.5, 0.0)}


def preview_mats():
    for name, (c, r, m) in PREV.items():
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.use_nodes = True
        b = mat.node_tree.nodes.get("Principled BSDF")
        b.inputs["Base Color"].default_value = (*c, 1)
        b.inputs["Roughness"].default_value = r
        b.inputs["Metallic"].default_value = m
        if name.startswith("Glow") or name == "Screen":
            b.inputs["Emission Color"].default_value = (*c, 1)
            b.inputs["Emission Strength"].default_value = 6.0
    skin = bpy.data.materials["Skin"]
    body.data.materials.clear(); body.data.materials.append(skin)


if K.opt(a, "--preview"):
    preview_mats()
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name in ("BodyMH",):
            o.hide_render = True
    out = []
    H = 1.86
    SH = (("front", 0, 4.6, 1.0, 0.95, 50), ("q34", 35, 4.6, 1.05, 0.95, 50), ("back", 180, 4.6, 1.0, 0.95, 50),
          ("chest", 25, 1.6, 1.45, 1.35, 50), ("legs", 20, 2.0, 0.6, 0.55, 50))
    if K.opt(a, "--detail"):
        SH = (("d_chest", 0, 1.2, 1.42, 1.38, 50), ("d_shoulderR", -70, 1.0, 1.5, 1.42, 50), ("d_shoulderL", 60, 1.0, 1.5, 1.42, 50),
              ("d_back", 160, 1.5, 1.45, 1.35, 50), ("d_legs", 55, 1.7, 0.55, 0.5, 50), ("d_boots", 30, 1.0, 0.25, 0.18, 50),
              ("d_armR", -40, 1.0, 1.25, 1.2, 50), ("d_hand", 20, 0.6, 1.15, 1.1, 50), ("d_front", 0, 3.2, 1.0, 0.95, 50), ("d_side", 90, 3.2, 1.0, 0.95, 50))
    for tag, yaw, dist, z, aim, lens in SH:
        K.clear_preview()
        K.cycles(samples=32, res=(700, 900))
        K.world((0.03, 0.033, 0.04), 1.0)
        K.floor((0.06, 0.065, 0.07), 0.6)
        K.rig_lights("portrait", Vector((0, 0, aim)), 1.6 if dist > 3 else 1.0)
        r = math.radians(yaw)
        K.camera(Vector((math.sin(r) * dist, -math.cos(r) * dist, z)), Vector((0, 0, aim)), lens)
        out.append(K.render_to(os.path.join(K.PREVIEWS, "outfit", f"geo_{tag}.png")))
    K.contact_sheet(out, os.path.join(K.PREVIEWS, "outfit", "geo_sheet.png" if not K.opt(a, "--detail") else "geo_detail.png"), cols=5, width=420)
if K.opt(a, "--save"):
    bpy.ops.wm.save_as_mainfile(filepath=K.opt(a, "--out") or os.path.join(K.BLENDS, "kael_s3_outfit.blend"))
