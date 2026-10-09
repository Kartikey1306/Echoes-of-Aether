"""Stage 1 - Kael v2 base: MPFB human (system assets) + procedural face sculpt + customisation/expression morphs,
helpers removed, Catmull-Clark level 1 with every shape key, attachments bound with the same morphs.

  blender -b --python build_base.py -- [--no-subdiv]
Writes blends/kael_s1_base.blend (objects: Kael armature, Body, Eyes, Brows, Lashes, Teeth, Tongue)
and blends/kael_s1_mh.blend (the same before subdivision, MakeHuman topology: used for refitting old assets).
"""
import bpy, sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
import body_def, mpfb_build, sculpt, meshops
import morphs, meshutil
for m in (body_def, sculpt, meshops, morphs, meshutil):
    importlib.reload(m)
from meshutil import SurfaceBinding, add_shape_key, bake_shape_keys, get_co, set_co

a = K.args()
bpy.ops.wm.read_factory_settings(use_empty=True)
body = mpfb_build.build("Kael", body_def.PHENOTYPE, body_def.TARGETS, body_def.ASSETS)
rig = body.parent
L = mpfb_build.landmarks(rig)
K.log("PROP", json.dumps(mpfb_build.proportions(body, rig)))
atts = [o for o in bpy.data.objects if o.type == "MESH" and o is not body and (o.parent is rig or o.parent is body)]
# ---- sculpt (body as a shape key so the MPFB morph capture runs on top of it; attachments directly)
guard = [(L["LeftEye"], 0.0125), (L["RightEye"], 0.0125)]
sculpt.apply_to_objects([body] + [o for o in atts if "high-poly" not in o.name], L["Head"], 1.0, guard)
# ---- customisation + expression morphs (MPFB targets) relative to the sculpted base
base, deltas = morphs.capture(body, False, custom=True)
bake_shape_keys(body)
set_co(body, base)
for o in atts:
    if o.data.shape_keys:
        bake_shape_keys(o)
    pts = get_co(o)
    bind = SurfaceBinding(body, base, pts, max_dist=0.2)
    eye = "high-poly" in o.name
    for name, d in deltas.items():
        if eye and name.startswith("x_"):
            continue
        dd = bind.transfer(d)
        if np.abs(dd).max() > 1e-5:
            add_shape_key(o, name, pts + dd)
for name, d in deltas.items():
    add_shape_key(body, name, base + d)
# ---- drop helpers / masks
del_groups = [m.vertex_group for m in body.modifiers if m.type == "MASK" and m.invert_vertex_group and m.vertex_group and m.vertex_group != "body"]
meshutil.delete_verts_in_groups(body, del_groups)
meshutil.delete_verts_not_in_group(body, "body")
for m in list(body.modifiers):
    if m.type == "MASK":
        body.modifiers.remove(m)
meshutil.remove_groups(body, lambda n: n.startswith(("joint-", "helper-")) or n in ("HelperGeometry", "JointCubes", "body"))
# ---- names
names = {"body": "Body", "high-poly": "Eyes", "eyebrow": "Brows", "eyelash": "Lashes", "teeth": "Teeth", "tongue": "Tongue"}
for o in [body] + atts:
    for k, v in names.items():
        if k in o.name:
            o.name = v
            o.data.name = v
for o in bpy.data.objects:
    if o.type == "MESH":
        for p in o.data.polygons:
            p.use_smooth = True
K.log("BODY", len(body.data.vertices), "verts", len(body.data.polygons), "faces", len(body.data.shape_keys.key_blocks) - 1, "shapes")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(K.BLENDS, "kael_s1_mh.blend"))
if not K.opt(a, "--no-subdiv"):
    meshops.subdivide_with_shapes(body, 1)
    K.log("SUBDIV", len(body.data.vertices), "verts", len(body.data.polygons), "faces")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(K.BLENDS, "kael_s1_base.blend"))
K.log("done")
