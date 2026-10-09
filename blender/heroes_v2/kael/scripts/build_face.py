"""Stage 5 - Kael v2 face & skin: rebuilt eyes, hidden body faces stripped, Body UV relayout, skin/eye/brow textures.

  blender -b blends/kael_s4_tex.blend --python build_face.py -- [--preview] [--save]
"""
import bpy, sys, os, json, math, importlib, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
from mathutils import Vector
import skin_k2 as SK, texbake as TB, texstage as TS, gear, skin_hd, meshops
importlib.reload(SK)

a = K.args()
rig = bpy.data.objects["Kael"]
body = bpy.data.objects["Body"]
OUT = K.TEX
# ---- eyes: opaque eyeballs with corneal bulge, centred-iris UVs (CharacterModel.ApplyEyes contract)
ctx = gear.Ctx(body, rig, "Kael")
eye = bpy.data.objects["Eyes"]
skin_hd.rebuild_eyes(ctx, eye)
eyes = SK.eye_textures(OUT, 1024, iris_gain=1.05)          # concept: warm mid-brown iris once Unity tints it
K.log("EYES", len(eye.data.vertices), eyes)
# ---- concept face sculpt (rugged: brow ridge, cheekbones, squarer jaw), before the unstripped copy so the outfit /
# corrective source carries it too; brows and lashes follow their skin
import face_sculpt as FS
importlib.reload(FS)
FS.apply(body, rig, others=[bpy.data.objects.get(n) for n in ("Brows", "Lashes")])
# ---- keep an unstripped copy (weight / shape source for the outfit and the correctives), never exported
full = body.copy(); full.data = body.data.copy(); full.name = full.data.name = "BodyFull"
bpy.context.scene.collection.objects.link(full)
full.hide_render = True
# ---- strip hidden body faces (under jacket, trousers, boots, gloves)
covers = [bpy.data.objects[n] for n in ("Top", "Jacket", "Collar", "Pants", "Boots", "Gloves") if n in bpy.data.objects]
cov = SK.covered_vertices(body, covers)
cov |= K.get_co(body)[:, 2] < 1.5            # everything under the outfit below the collar line
n0 = len(body.data.polygons)
removed = SK.strip_hidden(body, cov, keep_rings=2)
K.log("STRIP", removed, "of", n0, "faces; body now", len(body.data.vertices), "verts", len(body.data.polygons), "faces")
json.dump({"removed": removed}, open(os.path.join(K.LOGS, "strip.json"), "w"))
# ---- material + UV relayout
body.data.materials.clear()
body.data.materials.append(gear.get_mat("Skin"))
body.data.polygons.foreach_set("material_index", np.zeros(len(body.data.polygons), np.int32))
SK.relayout(body, rig)
# ---- head self-occlusion (cavities) for the mask map / albedo
hide = [o for o in bpy.data.objects if o.type == "MESH" and o is not body and o.name not in ("Eyes", "Teeth")]
ao = TB.bake_ao([body], "Skin", 2048, samples=128, distance=0.025, hide=hide, scale=0.5)
ao = SK.gblur(ao, 2.0)
brows_o, brow_alpha, hair_o = SK.face_inputs(rig, OUT)
written, FL = SK.skin_textures(body, rig, OUT, int(K.opt(a, "--size") or 2048), ao=ao, stubble=1.0, brows=brows_o, brow_alpha=brow_alpha,
                               hair=hair_o)
if hair_o is not None:
    bpy.data.objects.remove(hair_o, do_unlink=True)
K.log("SKIN", written)
# ---- brows: left-brow scar gap, denser alpha; lashes, teeth, tongue textures
brows = bpy.data.objects["Brows"]
sc_c = FL["eyeL"] + np.array((0.012, -0.012, 0.022))
import bmesh
bm = bmesh.new(); bm.from_mesh(brows.data)
kill = []          # v3: the concept has no brow gap (the scar is the "x" on the forehead)
bmesh.ops.delete(bm, geom=kill, context="FACES")
bm.to_mesh(brows.data); bm.free()
K.log("SCAR brow faces removed", len(kill))
for o, fn in ((bpy.data.objects["Lashes"], "Lashes_eyelashes01.png"),
              (bpy.data.objects["Teeth"], "Teeth_teeth.png"), (bpy.data.objects["Tongue"], "Tongue_tongue01_diffuse.png")):
    src = None
    for m in o.data.materials:
        if m and m.use_nodes:
            for nd in m.node_tree.nodes:
                if nd.type == "TEX_IMAGE" and nd.image:
                    src = bpy.path.abspath(nd.image.filepath)
                    break
    if src and os.path.exists(src):
        shutil.copyfile(src, os.path.join(OUT, fn))
        if fn.startswith(("Brows", "Lashes")):
            img = TB.read_image(os.path.join(OUT, fn))
            al = img[..., 3]
            lo_, hi_ = (0.22, 0.85) if fn.startswith("Brows") else (0.3, 0.9)
            img[..., 3] = np.clip(K.ss(lo_, hi_, al), 0, 1) * (0.82 if fn.startswith("Brows") else 0.72)
            if fn.startswith("Lashes"):
                hh = img.shape[0]
                # lower lashes (bottom of the atlas, rows stored bottom-up): eroded + fainter so that after the
                # 0.32 alpha clip only thin, sparse hairs survive (they read as mascara otherwise)
                img[: hh // 2, :, 3] = np.clip(K.ss(0.5, 0.95, al[: hh // 2]), 0, 1) * 0.72 * 0.62
            img[..., :3] = np.clip(img[..., :3] * 0.9, 0, 1)
            img = TB.dilate(img, img[..., 3] > 0.05, 3)
            TB.write_png(img, os.path.join(OUT, fn), "RGBA")
        elif fn.startswith("Teeth"):
            # teeth sit in the shadow of the mouth: a bright white line between parted lips reads as a grimace
            img = TB.read_image(os.path.join(OUT, fn))
            img[..., :3] = np.clip(img[..., :3] * np.array((0.74, 0.71, 0.66)), 0, 1)
            TB.write_png(img, os.path.join(OUT, fn), "RGBA" if img.shape[-1] == 4 else "RGB")
    mat = {"Lashes": "Lashes", "Teeth": "Teeth", "Tongue": "Tongue"}[o.name]
    o.data.materials.clear(); o.data.materials.append(gear.get_mat(mat))
    o.data.polygons.foreach_set("material_index", np.zeros(len(o.data.polygons), np.int32))
brows.data.materials.clear(); brows.data.materials.append(gear.get_mat("Brows"))
brows.data.polygons.foreach_set("material_index", np.zeros(len(brows.data.polygons), np.int32))
eye.data.materials.clear(); eye.data.materials.append(gear.get_mat("Eyes"))
eye.data.polygons.foreach_set("material_index", np.zeros(len(eye.data.polygons), np.int32))
# ---- makeover: eye occlusion shell + tear meniscus (shared eye shading), measured on the export's baked face morphs
import eye_fx
importlib.reload(eye_fx)
from build_export_morphs import BAKE_MORPHS
eyefx = eye_fx.build(rig, body, eye, bake=BAKE_MORPHS)
json.dump({"skins": written, "eyes": eyes, "eyeFx": eyefx, "landmarks": {k: v.tolist() for k, v in FL.items()}}, open(os.path.join(K.LOGS, "face.json"), "w"), indent=1)
if K.opt(a, "--save"):
    bpy.ops.wm.save_as_mainfile(filepath=K.opt(a, "--out") or os.path.join(K.BLENDS, "kael_s5_face.blend"))
