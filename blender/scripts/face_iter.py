"""Face/body design iteration: build the MPFB human with the current character targets (+ JSON overrides), report
proportions (height, head height, heads tall, shoulder/waist/hip widths, leg ratio) and render face + body.
  blender -b --python face_iter.py -- <cid> <tag> [overrides.json]
"""
import bpy, sys, os, json, math
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from mathutils import Vector
import characters, build_human, preview_hd
a = sys.argv[sys.argv.index("--") + 1:]
cid, tag = a[0], a[1]
c = characters.CHARACTERS[cid]
if len(a) > 2:
    ov = json.load(open(a[2]))
    c["phenotype"].update(ov.get("phenotype", {}))
    if "targets" in ov:
        c["targets"] = [tuple(t) for t in ov["targets"]]
    for k in ("eyebrows", "eyelashes", "skin"):
        if k in ov:
            c[k] = ov[k]
c["extra_hair"] = {}; c["extra_clothes"] = {}
bpy.ops.wm.read_factory_settings(use_empty=True)
body = build_human.build(cid)
rig = body.parent
for o in bpy.data.objects:
    if o.type == "MESH" and o is not body and o.parent is rig and any(k in o.name for k in ("hair", "short", "ponytail")):
        o.hide_render = True
dg = bpy.context.evaluated_depsgraph_get()
ev = body.evaluated_get(dg)
co = np.array([(body.matrix_world @ v.co)[:] for v in ev.data.vertices])
H = co[:, 2].max()
L = {b.name.split(":")[1]: rig.matrix_world @ b.head_local for b in rig.data.bones if ":" in b.name}
eye_z = (L["LeftEye"].z + L["RightEye"].z) / 2
headv = co[(co[:, 2] > L["Neck"].z + 0.03)]
front = headv[(np.abs(headv[:, 0]) < 0.012) & (headv[:, 1] < L["LeftEye"].y)]
chin = front[:, 2].min() if len(front) else L["Head"].z - 0.05
hh = H - chin
def width(z, band=0.01, xmax=0.4):
    s = co[(np.abs(co[:, 2] - z) < band) & (np.abs(co[:, 0]) < xmax)]
    return s[:, 0].max() - s[:, 0].min() if len(s) else 0
sh_w = (L["LeftArm"].x - L["RightArm"].x)
print("PROP", cid, tag, json.dumps({"height": round(H, 3), "head_h": round(hh, 3), "heads": round(H / hh, 2), "shoulder_joint_w": round(sh_w, 3),
      "chest_w": round(width(L["Spine2"].z + 0.08, xmax=0.2), 3), "waist_w": round(width(L["Spine"].z + 0.02, xmax=0.2), 3),
      "hip_w": round(width(L["Hips"].z - 0.05, xmax=0.25), 3), "leg_ratio": round(L["Hips"].z / H, 3),
      "eye_sep": round(L["LeftEye"].x - L["RightEye"].x, 4)}))
face = Vector((0, L["Head"].y - 0.02, eye_z - 0.01))
preview_hd.OUT = os.path.join(os.path.dirname(__file__), "..", "out", "hd", "faceiter")
os.makedirs(preview_hd.OUT, exist_ok=True)
preview_hd.render(f"{cid}_{tag}", (0, 0, 0), H, face, "studio", ["face", "face34", "front"], samples=24)
