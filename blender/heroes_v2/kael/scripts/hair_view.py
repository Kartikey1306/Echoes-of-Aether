"""Preview Kael's built-in concept hair (blends/hair_k3.blend) on a stage blend, next to the concept face crop.

  blender -b <blend> --python hair_view.py -- <tag> [--light portrait|menu]
"""
import bpy, sys, os, math, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
from mathutils import Vector
import preview_k2 as PV

a = K.args()
tag = a[0] if a else "hair"
light = K.opt(a, "--light") or "portrait"
with bpy.data.libraries.load(os.path.join(K.BLENDS, "hair_k3.blend")) as (src, dst):
    dst.objects = [n for n in src.objects if n.startswith("Hair_")]
for o in dst.objects:
    bpy.context.scene.collection.objects.link(o)
    hair = o
for o in bpy.data.objects:
    if o.type == "MESH" and (o.name in ("BodyMH", "BodyFull") or o.name.endswith(("_HI", "_HIB", "_HPG"))):
        o.hide_render = True
    if o.type == "MESH" and o.name.startswith(("Hair_", "Facial_")) and o is not hair:
        o.hide_render = True
body = bpy.data.objects["Body"]
if body.data.uv_layers.get("UVOld") is not None:
    PV.setup_materials()
else:
    sm = bpy.data.materials.new("clay_skin"); sm.use_nodes = True
    bb = sm.node_tree.nodes["Principled BSDF"]; bb.inputs["Base Color"].default_value = (0.62, 0.43, 0.33, 1); bb.inputs["Roughness"].default_value = 0.5
    body.data.materials.clear(); body.data.materials.append(sm)
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name not in ("Body", "Eyes", "Brows", "Lashes", "Teeth", "Tongue") and not o.name.startswith("Hair_"):
            o.hide_render = o.name not in ("Collar", "Jacket", "Top")
tex = os.path.join(K.TEX, "Hair_swept_fade_Color.png")
m = PV.card_material("prev_hair_k3", tex, PV.hexc("#2e231c") ** 2.2 * 1.8, 0.4)
hair.data.materials.clear(); hair.data.materials.append(m)
rig = bpy.data.objects["Kael"]
L = {b.name.split(":")[1]: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones if ":" in b.name}
eye = (L["LeftEye"] + L["RightEye"]) / 2
fc = Vector((0, eye[1] + 0.03, eye[2] + 0.0))
out = []
for s, yaw in (("front", 0), ("q34r", -35), ("q34l", 35), ("back", 165)):
    K.clear_preview()
    K.cycles(samples=64, res=(760, 860))
    K.world((0.55, 0.56, 0.58), 0.9)
    K.rig_lights(light, fc, 0.6)
    r = math.radians(yaw)
    K.camera(fc + Vector((math.sin(r) * 0.72, -math.cos(r) * 0.72, 0.02)), fc, 85)
    out.append(K.render_to(os.path.join(K.PREVIEWS, "faceiter", f"{tag}_{s}.png")))
K.contact_sheet(out, os.path.join(K.PREVIEWS, "faceiter", f"{tag}_sheet.png"), cols=4, width=480)
