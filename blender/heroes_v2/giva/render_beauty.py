"""Beauty renders with Unity-equivalent materials (lookdev) + the catalog default hair.

  blender -b out/giva_face.blend --python render_beauty.py -- <tag> [--pal game|proposed] [--shots front,q34,back,face,face34]
          [--light studio|night] [--samples 64] [--engine CYCLES] [--nohair] [--turntable N]
"""
import bpy, sys, os, json, math, importlib, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
from mathutils import Vector
import gv, look, lookdev, mpfb_build
for m in (gv, look, lookdev, mpfb_build):
    importlib.reload(m)

a = gv.args()
tag = a[0]
pal = lookdev.PROPOSED if gv.opt(a, "--pal", "game") == "proposed" else lookdev.GAME
rig = bpy.data.objects[gv.RIG]
TEX = os.path.join(gv.OUT, "tex")
atl = json.load(open(os.path.join(TEX, "atlases.json")))
objs = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig]
for o in bpy.data.objects:
    if o.name == "Gloves" and "--gloves" not in gv.args():
        o.hide_render = True                  # the game default is bare hands (concept)
    if o.name.endswith("_high") or (o.type == "MESH" and o.name.startswith("Hair_")):
        o.hide_render = True
lookdev.apply_all(objs, TEX, atl, pal)
hid = gv.opt(a, "--hairid", "waves")
if "--nohair" not in a and hid == "waves" and bpy.data.objects.get("Hair_waves"):
    ho = bpy.data.objects["Hair_waves"]
    ho.hide_render = False
    hm = lookdev.alpha_card("pv_hair", os.path.join(TEX, "Hair_waves_Color.png"), pal["hair"], cutoff=0.35)
    ho.data.materials.clear()
    ho.data.materials.append(hm)
elif "--nohair" not in a:
    mpfb_build.attach_catalog(rig, "hair", hid, tint=pal["hair"])
eng = gv.opt(a, "--engine", "CYCLES")
smp = int(gv.opt(a, "--samples", "64"))
light = gv.opt(a, "--light", "studio")
out = os.path.join(gv.OUT, "renders", tag)
shots = gv.opt(a, "--shots", "front,q34,back,face,face34").split(",")
body_shots = [s for s in shots if not s.startswith("face") and s != "profile" and s != "close"]
face_sh = [s for s in shots if s.startswith("face") or s in ("profile", "close")]
files = []
if body_shots:
    files += look.body_shots(out, 1.73, light, eng, smp, body_shots, res=(1000, 1400))
if face_sh:
    le = rig.data.bones[gv.P + "LeftEye"].head_local
    re = rig.data.bones[gv.P + "RightEye"].head_local
    files += look.face_shots(out, (le + re) / 2 + Vector((0, -0.01, -0.035)), light, eng, smp, face_sh, res=(900, 1100))
if "--turntable" in a:
    n = int(gv.opt(a, "--turntable"))
    for k in range(n):
        ang = 2 * math.pi * k / n
        cam = Vector((math.sin(ang) * 4.6, -math.cos(ang) * 4.6, 1.73 * 0.58))
        p = f"{out}_tt{k:02d}.png"
        look.shot(p, cam, Vector((0, 0, 0.87)), 55, light, eng, (700, 1000), smp, height=1.73)
        files.append(p)
subprocess.run(["/opt/homebrew/bin/python3", os.path.join(HERE, "sheet.py"), out + "_sheet.png"] + files + ["--h", "700"])
