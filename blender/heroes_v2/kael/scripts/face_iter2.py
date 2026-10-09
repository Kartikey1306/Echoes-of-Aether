"""Fast face look iteration on the stage-5 blend: regenerate skin textures (optional), swap brow/lash assets, render
face shots with the Unity-mirroring preview materials.

  blender -b blends/kael_s5_face.blend --python face_iter2.py -- <tag> [--skin] [--stubble 0.6] [--lashes eyelashes01] [--brows eyebrow004]
"""
import bpy, sys, os, json, importlib, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
import skin_k2 as SK, texbake as TB, preview_k2 as PV
importlib.reload(SK); importlib.reload(PV)

a = K.args()
tag = a[0]
rig = bpy.data.objects["Kael"]
body = bpy.data.objects["Body"]
if K.opt(a, "--skin"):
    hide = [o for o in bpy.data.objects if o.type == "MESH" and o is not body and o.name not in ("Eyes", "Teeth")]
    ao = TB.bake_ao([body], "Skin", 2048, samples=96, distance=0.025, hide=hide, scale=0.5)
    ao = SK.gblur(ao, 2.0)
    bo, ba, ho = SK.face_inputs(rig, K.TEX)
    SK.skin_textures(body, rig, K.TEX, 2048, ao=ao, stubble=float(K.opt(a, "--stubble") or 0.6), brows=bo, brow_alpha=ba, hair=ho)
    if ho is not None:
        bpy.data.objects.remove(ho, do_unlink=True)
PV.setup_materials()
if K.opt(a, "--shapes"):
    for kv in K.opt(a, "--shapes").split(","):
        n, v = kv.split("=")
        for o in bpy.data.objects:
            if o.type == "MESH" and o.data.shape_keys and n in o.data.shape_keys.key_blocks:
                o.data.shape_keys.key_blocks[n].value = float(v)
for o in bpy.data.objects:
    if o.type == "MESH" and (o.name in ("BodyMH", "BodyFull") or o.name.endswith(("_HI", "_HIB", "_HPG"))):
        o.hide_render = True
PV.add_catalog_hair(rig)
out = PV.render_set(tag, (K.opt(a, "--shots") or "face,face34,profile").split(","), K.opt(a, "--light") or "menu", outdir=os.path.join(K.PREVIEWS, "faceiter"))
K.contact_sheet(out, os.path.join(K.PREVIEWS, "faceiter", f"{tag}_sheet.png"), cols=3, width=600)
