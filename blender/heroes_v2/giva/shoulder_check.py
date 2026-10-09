"""Right shoulder armour close-ups at the clips' most raised-arm frames (clay)."""
import bpy, sys, os, json, math, importlib, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
from mathutils import Vector
import gv, look, poses, deform
a = gv.args(); tag = a[0]
rig = bpy.data.objects[gv.RIG]
poses.load()
cdefs = json.load(open(os.path.join(gv.OUT, "correctives.json")))
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig]
tints = {"ShoulderR": (0.5, 0.35, 0.6), "Top": (0.12, 0.13, 0.15), "Body": (0.42, 0.27, 0.21)}
for o in meshes:
    if o.name.startswith("Hair_") or o.name in ("Brows", "Lashes"):
        o.hide_render = True
    c = tints.get(o.name, (0.35, 0.35, 0.37)); m = bpy.data.materials.new("c"); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = 0.5
    o.data.materials.clear(); o.data.materials.append(m)
frames = [s.split(":") for s in gv.opt(a, "--frames", "climb:15,death:39,jump:1,hit:11,l_ult:33,k_heavy:5").split(",")]
files = []
out = os.path.join(gv.OUT, "pose", tag); os.makedirs(out, exist_ok=True)
for clip, fr in frames:
    poses.pose(rig, clip, int(fr))
    deform.drive_correctives(rig, meshes, cdefs, True)
    sh = rig.matrix_world @ rig.pose.bones[gv.P + "RightArm"].head
    for k, d in (("f", Vector((-0.45, -0.5, 0.15))), ("b", Vector((-0.4, 0.5, 0.2))), ("t", Vector((-0.15, -0.1, 0.65)))):
        p = os.path.join(out, f"{clip}_{fr}_{k}.png")
        look.shot(p, sh + d, sh, 45, "clay", "BLENDER_EEVEE", (480, 480), 24, center=(sh.x, sh.y, 0), floor=False)
        files.append(p)
subprocess.run(["/opt/homebrew/bin/python3", os.path.join(HERE, "sheet.py"), os.path.join(gv.OUT, "pose", tag + "_sheet.png")] + files + ["--h", "320", "--cols", "6"])
