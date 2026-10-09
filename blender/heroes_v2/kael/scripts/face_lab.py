"""Face/body design iteration for Kael v2 (Cycles GPU).

  blender -b --python face_lab.py -- <tag> [--json overrides.json] [--shots face,face34,profile,body,side] [--old]
Overrides JSON: {"phenotype": {...}, "targets": [[t, w], ...], "add": [[t, w], ...], "assets": {...}}
"""
import bpy, sys, os, json, math, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
from mathutils import Vector
import body_def, mpfb_build
importlib.reload(body_def)

a = K.args()
tag = a[0] if a else "lab"
ph = dict(body_def.PHENOTYPE)
targets = list(body_def.TARGETS)
assets = dict(body_def.ASSETS)
if K.opt(a, "--old"):
    sys.path.insert(0, K.BLENDER_SCRIPTS)
    import characters
    c = characters.CHARACTERS["kael"]
    ph, targets = dict(c["phenotype"]), list(c["targets"])
js = K.opt(a, "--json")
if js:
    ov = json.load(open(js))
    ph.update(ov.get("phenotype", {}))
    if "targets" in ov:
        targets = [tuple(t) for t in ov["targets"]]
    if "add" in ov:
        d = dict(targets)
        for t, w in ov["add"]:
            d[t] = w
        targets = [(t, w) for t, w in d.items() if w != 0]
    assets.update(ov.get("assets", {}))
shots = (K.opt(a, "--shots") or "face,face34,profile,body,side").split(",")
bpy.ops.wm.read_factory_settings(use_empty=True)
body = mpfb_build.build("Kael", ph, targets, assets)
rig = body.parent
P = mpfb_build.proportions(body, rig)
K.log("PROP", tag, json.dumps(P))
L = mpfb_build.landmarks(rig)
eye = (L["LeftEye"] + L["RightEye"]) / 2
fc = Vector((0, eye[1] + 0.03, eye[2] - 0.03))
for o in bpy.data.objects:
    if o.type == "MESH":
        for p in o.data.polygons:
            p.use_smooth = True
if not K.opt(a, "--old") and not K.opt(a, "--nosculpt"):
    import sculpt
    importlib.reload(sculpt)
    heads = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig and "high-poly" not in o.name]
    guard = [(L["LeftEye"], 0.0125), (L["RightEye"], 0.0125)]
    sculpt.apply_to_objects(heads, L["Head"], float(K.opt(a, "--sculpt") or 1.0), guard)
# ---- head fit vs the committed Kael (catalog hair/eyewear): per-vertex deviation relative to the Head bone
dg = bpy.context.evaluated_depsgraph_get()
co = np.array([v.co[:] for v in body.evaluated_get(dg).data.vertices])
ref_p = os.path.join(K.LOGS, (K.opt(a, "--ref") or "old") + "_head_ref.npz")
if K.opt(a, "--old") and not os.path.exists(ref_p):
    np.savez(ref_p, co=co, head=L["Head"])
if K.opt(a, "--saveref"):
    np.savez(os.path.join(K.LOGS, K.opt(a, "--saveref") + "_head_ref.npz"), co=co, head=L["Head"])
if os.path.exists(ref_p) and not K.opt(a, "--old"):
    R = np.load(ref_p)
    rc = R["co"] - R["head"]; nc = co - L["Head"]
    n = min(len(rc), len(nc))
    d = np.linalg.norm(nc[:n] - rc[:n], axis=1)
    eye_z = (L["LeftEye"][2] + L["RightEye"][2]) / 2 - L["Head"][2]
    scalp = (rc[:n, 2] > eye_z + 0.035) & (np.linalg.norm(rc[:n], axis=1) < 0.2)
    ears = (np.abs(rc[:n, 0]) > 0.06) & (np.abs(rc[:n, 2] - eye_z) < 0.03) & (rc[:n, 1] > 0.0) & (np.linalg.norm(rc[:n], axis=1) < 0.2)
    bridge = (np.abs(rc[:n, 0]) < 0.012) & (np.abs(rc[:n, 2] - eye_z) < 0.012) & (rc[:n, 1] < -0.06) & (np.linalg.norm(rc[:n], axis=1) < 0.2)
    K.log("FIT", tag, json.dumps({k: [round(float(d[m].max() * 1000), 1), round(float(d[m].mean() * 1000), 1)] for k, m in
                                  (("scalp_mm", scalp), ("ears_mm", ears), ("bridge_mm", bridge))}))
# ---- preview: smooth subdivision and a simple skin shader (fast)
skin_img = None
for m in body.data.materials:
    if m and m.use_nodes:
        for nd in m.node_tree.nodes:
            nm = nd.image.name.lower() if nd.type == "TEX_IMAGE" and nd.image else ""
            if nm and skin_img is None and not any(k in nm for k in ("nrm", "spec", "normal", "bump", "_n.", "rough")):
                skin_img = nd.image
print("SKIN IMG", skin_img.name if skin_img else None)
sm = bpy.data.materials.new("lab_skin"); sm.use_nodes = True
nt = sm.node_tree; b = nt.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.55, 0.42, 0.36, 1)
if skin_img is not None and not K.opt(a, "--clay"):
    tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = skin_img
    nt.links.new(tx.outputs["Color"], b.inputs["Base Color"])
b.inputs["Roughness"].default_value = 0.48
b.inputs["Subsurface Weight"].default_value = 0.25
b.inputs["Subsurface Radius"].default_value = (1.0, 0.4, 0.25)
b.inputs["Subsurface Scale"].default_value = 0.004
body.data.materials.clear(); body.data.materials.append(sm)
for p in body.data.polygons:
    p.material_index = 0
sub = body.modifiers.new("lab_sub", "SUBSURF"); sub.levels = sub.render_levels = 1
out = []
H = P["height"]
for s in shots:
    K.clear_preview()
    if s.startswith("face") or s == "profile":
        K.cycles(samples=48, res=(720, 880))
        K.world((0.02, 0.022, 0.026), 1.0)
        K.rig_lights("portrait", fc, 0.6)
        yaw = {"face": 0, "face34": 35, "profile": 90}[s]
        r = math.radians(yaw)
        d = 0.75
        K.camera(fc + Vector((math.sin(r) * d, -math.cos(r) * d, 0.01)), fc, 85)
    else:
        K.cycles(samples=32, res=(600, 900))
        K.world((0.02, 0.022, 0.026), 1.0)
        K.floor((0.05, 0.052, 0.056), 0.6)
        c = Vector((0, 0, H * 0.55))
        K.rig_lights("portrait", c, 1.6)
        yaw = {"body": 15, "side": 90, "back": 180}.get(s, 0)
        r = math.radians(yaw)
        K.camera(Vector((math.sin(r) * 5.2, -math.cos(r) * 5.2, H * 0.55)), Vector((0, 0, H * 0.5)), 50)
    out.append(K.render_to(os.path.join(K.PREVIEWS, "lab", f"{tag}_{s}.png")))
K.contact_sheet(out, os.path.join(K.PREVIEWS, "lab", f"{tag}_sheet.png"), cols=len(out), width=500)
