"""Face/body shape iteration: build the MPFB human from giva_def (+ overrides) and render close-ups.

  blender -b --python iter_face.py -- <tag> [--over overrides.json] [--shots face,face34,profile] [--body]
          [--engine CYCLES|BLENDER_EEVEE] [--samples 64] [--nohair]
Writes out/iter/<tag>_<shot>.png
"""
import bpy, sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import gv, look, mpfb_build, giva_def
for m in (gv, look, mpfb_build, giva_def):
    importlib.reload(m)
from mathutils import Vector

a = gv.args()
tag = a[0]
over = json.load(open(gv.opt(a, "--over"))) if "--over" in a else {}
bpy.ops.wm.read_factory_settings(use_empty=True)
ph = dict(giva_def.PHENOTYPE)
ph.update(over.get("phenotype", {}))
body, rig = mpfb_build.build_human(ph, giva_def.targets(over.get("targets")), dict(giva_def.ASSETS, **over.get("assets", {})))
parts = mpfb_build.find_parts(rig)
if "--nohair" not in a:
    mpfb_build.attach_catalog(rig, "hair", over.get("hair", "long_waves"), tint=over.get("hairColor", "#2a1a1e"))
hb = rig.data.bones["mixamorig:Head"]
head = rig.matrix_world @ hb.head_local
dg = bpy.context.evaluated_depsgraph_get()
ev = body.evaluated_get(dg)
top = max((body.matrix_world @ v.co).z for v in ev.data.vertices)
gv.log("HEAD", tuple(round(x, 4) for x in head), "HEIGHT", round(top, 4))
le = rig.matrix_world @ rig.data.bones["mixamorig:LeftEye"].head_local
re = rig.matrix_world @ rig.data.bones["mixamorig:RightEye"].head_local
face = (le + re) / 2 + Vector((0, -0.01, -0.035))
gv.log("EYES", tuple(round(x, 4) for x in le), tuple(round(x, 4) for x in re))
eng = gv.opt(a, "--engine", "CYCLES")
smp = int(gv.opt(a, "--samples", "64"))
prefix = os.path.join(gv.OUT, "iter", tag)
shots = gv.opt(a, "--shots", "face,face34,profile").split(",")
if shots != [""]:
    look.face_shots(prefix, face, "studio", eng, smp, shots, res=(720, 880))
if "--body" in a:
    look.body_shots(prefix, top, "clay", eng, smp, ("front", "side"), res=(700, 1000))
if "--save" in a:
    gv.save(gv.opt(a, "--save"))
