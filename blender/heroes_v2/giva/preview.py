"""Quick preview of a stage blend: clay (per-object tints) or materials as-is.
  blender -b <blend> --python preview.py -- <tag> [--shots front,q34,back,side,upper] [--clay] [--hair] [--face]
          [--engine BLENDER_EEVEE|CYCLES] [--samples N] [--light studio|night|clay] [--hide a,b]"""
import bpy, sys, os, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
import numpy as np
from mathutils import Vector
import gv, look, mpfb_build
a = gv.args(); tag = a[0]
rig = bpy.data.objects[gv.RIG]
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig]
hide = gv.opt(a, "--hide", "").split(",")
for o in meshes:
    if o.name in hide or o.name.startswith("Hair_"): o.hide_render = True
if "--clay" in a:
    tints = {"Body": (0.42, 0.27, 0.21), "Top": (0.1, 0.105, 0.12), "Pants": (0.075, 0.08, 0.09)}
    for o in meshes:
        c = tints.get(o.name, (0.2, 0.2, 0.22))
        m = bpy.data.materials.new("clay_" + o.name); m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = 0.6
        if o.name in ("Brows", "Lashes"): o.hide_render = True
        o.data.materials.clear(); o.data.materials.append(m)
if "--hair" in a:
    mpfb_build.attach_catalog(rig, "hair", "long_waves")
eng = gv.opt(a, "--engine", "BLENDER_EEVEE"); smp = int(gv.opt(a, "--samples", "32")); light = gv.opt(a, "--light", "studio")
prefix = os.path.join(gv.OUT, "prev", tag)
shots = gv.opt(a, "--shots", "front,q34,back,side").split(",")
look.body_shots(prefix, 1.73, light, eng, smp, shots, res=(900, 1300))
if "--face" in a:
    le = rig.data.bones[gv.P + "LeftEye"].head_local; re = rig.data.bones[gv.P + "RightEye"].head_local
    look.face_shots(prefix, (le + re) / 2 + Vector((0, -0.01, -0.035)), light, eng, smp, ("face", "face34"), res=(800, 1000))
import subprocess
fs = [f"{prefix}_{s}.png" for s in shots] + ([f"{prefix}_face.png", f"{prefix}_face34.png"] if "--face" in a else [])
subprocess.run(["/opt/homebrew/bin/python3", os.path.join(HERE, "sheet.py"), prefix + "_sheet.png"] + fs + ["--h", "700"])
