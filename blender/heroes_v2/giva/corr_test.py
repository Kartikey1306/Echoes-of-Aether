"""Corrective check: each corrective's joint at its `to` angle, LBS only vs with correctives (clay close-ups).
  blender -b out/giva_rig.blend --python corr_test.py -- <tag>"""
import bpy, sys, os, json, math, importlib, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
from mathutils import Vector
import gv, look, deform
a = gv.args(); tag = a[0]
rig = bpy.data.objects[gv.RIG]
defs = json.load(open(os.path.join(gv.OUT, "correctives.json")))
objs = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig]
clay = bpy.data.materials.new("clay"); clay.use_nodes = True
b = clay.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (0.55, 0.55, 0.56, 1); b.inputs["Roughness"].default_value = 0.55
for o in objs:
    if o.name in ("Brows", "Lashes"): o.hide_render = True
    o.data.materials.clear(); o.data.materials.append(clay)
out = os.path.join(gv.OUT, "corr", tag); os.makedirs(out, exist_ok=True)
files = []
only = gv.opt(a, "--only")
for d in defs:
    later = [e for e in defs if e["bone"] == d["bone"] and e["axis"] == d["axis"] and e["from"] == d["to"]]
    if later: continue     # only the last step of each chain
    if not d["shape"].startswith("corr_Left"): continue
    if only and only not in d["shape"]: continue
    deform.pose_swing(rig, d["bone"], d["axis"], d["to"])
    pb = rig.pose.bones[d["bone"]]
    j = rig.matrix_world @ pb.head
    par = pb.parent
    d1 = (pb.tail - pb.head).normalized(); d0 = (par.tail - par.head).normalized()
    n = d0.cross(d1)
    if n.length < 1e-3: n = Vector((1, 0, 0))
    n.normalize()
    if j.x * n.x < 0: n = -n
    for on in (0, 1):
        w = deform.drive_correctives(rig, objs, defs, bool(on))
        for k2, vv in (("a", n), ("b", (n * 0.5 + (d0 - d1).normalized()).normalized()), ("c", -n)):
            p = os.path.join(out, f"{d['shape']}_{k2}_{'on' if on else 'off'}.png")
            look.shot(p, j + vv * 0.55, j, 50, "clay", "BLENDER_EEVEE", (420, 420), 24, center=(j.x, j.y, 0), floor=False)
            files.append(p)
    gv.log(d["shape"], {k: round(v, 2) for k, v in w.items() if v > 0})
subprocess.run(["/opt/homebrew/bin/python3", os.path.join(HERE, "sheet.py"), os.path.join(gv.OUT, "corr", tag + "_sheet.png")] + files + ["--h", "300", "--cols", "6"])
