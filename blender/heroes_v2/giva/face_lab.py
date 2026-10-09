"""Face lab: fast beauty iteration on the head with the real skin painter, eyes, brows and catalog hair.

  blender -b --python face_lab.py -- <tag> [--over overrides.json] [--size 1024] [--samples 32] [--hairid long_waves]
          [--shots face,face34,profile] [--light studio]
Writes out/lab/<tag>_*.png + sheet.
"""
import bpy, sys, os, json, math, importlib, shutil, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE, os.path.join(HERE, "..", "..", "scripts")]
import numpy as np
from mathutils import Vector
import gv, look, lookdev, mpfb_build, giva_def, face, raster, browtex, meshutil
for m in (gv, look, lookdev, mpfb_build, giva_def, face, raster, browtex):
    importlib.reload(m)

a = gv.args()
tag = a[0]
over = json.load(open(gv.opt(a, "--over"))) if "--over" in a else {}
SIZE = int(gv.opt(a, "--size", "1024"))
LAB = os.path.join(gv.OUT, "lab")
TEXL = os.path.join(LAB, "tex_" + tag)
os.makedirs(TEXL, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
ph = dict(giva_def.PHENOTYPE)
ph.update(over.get("phenotype", {}))
body, rig = mpfb_build.build_human(ph, giva_def.targets(over.get("targets")), dict(giva_def.ASSETS, **over.get("assets", {})))
parts = mpfb_build.find_parts(rig)
for o in [body] + list(parts.values()):
    if o.data.shape_keys:
        meshutil.bake_shape_keys(o)
meshutil.delete_verts_not_in_group(body, "body")
for md in list(body.modifiers):
    if md.type == "MASK":
        body.modifiers.remove(md)
body.name = "Body"
eyes = face.build_eyes(parts["eyes"], rig)
face.add_group_attrs(body)
face.skin_uvs(body)
maps = raster.Maps(SIZE)
raster.rasterize(maps, body, 0, None, ("g_lips", "g_ears", "g_scalp", "g_fingernails"))
tones, nrm, mm = face.paint_skin(maps, body, rig, np.ones((SIZE, SIZE), np.float32))


def save(arr, name, srgb=False, mask=None):
    x = raster.dilate(arr.astype(np.float32), mask, 8) if mask is not None else arr
    if srgb:
        x = gv.lin_to_srgb(np.clip(x, 0, 1))
    gv.write_image(x, os.path.join(TEXL, name))
    return name
skins = {t: save(img, f"Skin_{t}.png", True, maps.mask) for t, img in tones.items()}
save(nrm, "Skin_Normal.png", False, maps.mask)
save(mm, "Skin_MaskMap.png", False, maps.mask)
save(face.eye_texture(1024), "Eye_grey.png")
brow_id = giva_def.ASSETS["eyebrows"].split("/")[0] if "eyebrows" not in over.get("assets", {}) else over["assets"]["eyebrows"].split("/")[0]
src = gv.read_image(os.path.join(gv.MPFB_DATA, "eyebrows", brow_id, brow_id + ".png"))
gv.write_image(browtex.make(src, 1024, density=float(over.get("brow_density", 2.2))), os.path.join(TEXL, "Brows_giva.png"))
lash = (over.get("assets", {}).get("eyelashes") or giva_def.ASSETS["eyelashes"]).split("/")[0]
shutil.copyfile(os.path.join(gv.MPFB_DATA, "eyelashes", lash, lash + ".png"), os.path.join(TEXL, "Lashes_eyelashes03.png"))
for o, mn in ((body, "Skin"), (eyes, "Eyes"), (parts["brows"], "Brows"), (parts["lashes"], "Lashes")):
    o.data.materials.clear()
    o.data.materials.append(bpy.data.materials.new(mn))
pal = dict(lookdev.GAME)
pal.update(over.get("palette", {}))
atl = {"Skin": {"skins": skins, "normal": "Skin_Normal.png", "maskMap": "Skin_MaskMap.png"}}
lookdev.apply_all([body, eyes, parts["brows"], parts["lashes"]], TEXL, atl, pal)
if "--nohair" not in a:
    mpfb_build.attach_catalog(rig, "hair", gv.opt(a, "--hairid", "long_waves"), tint=pal["hair"])
le = rig.data.bones[gv.P + "LeftEye"].head_local
re = rig.data.bones[gv.P + "RightEye"].head_local
fc = (le + re) / 2 + Vector((0, -0.01, -0.035))
shots = gv.opt(a, "--shots", "face,face34,profile").split(",")
files = look.face_shots(os.path.join(LAB, tag), fc, gv.opt(a, "--light", "concept"), "CYCLES", int(gv.opt(a, "--samples", "32")), shots, res=(800, 1000))
subprocess.run(["/opt/homebrew/bin/python3", os.path.join(HERE, "sheet.py"), os.path.join(LAB, tag + "_sheet.png")] + files + ["--h", "760"])
# side by side with the concept face (same framing as the lab "face" shot)
subprocess.run(["/opt/homebrew/bin/python3", "-c", f"""
from PIL import Image
c = Image.open('/Users/kartikey/Desktop/Game/dreamlayer/characters/lyra/giva_master_front.png').convert('RGB').crop((675, 157, 1029, 599)).resize((800, 1000))
r = Image.open('{files[0]}').convert('RGB').resize((800, 1000))
s = Image.new('RGB', (1600, 1000)); s.paste(c, (0, 0)); s.paste(r, (800, 0)); s.save('{os.path.join(LAB, tag + '_vs_concept.png')}')
"""])
