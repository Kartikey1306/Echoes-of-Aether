"""Probe: build the MPFB Kael base, compare its rest bone directions with Anim_Male.fbx, print mesh/weight stats."""
import bpy, sys, os, math, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "blender", "scripts"))
import numpy as np
import build_human

bpy.ops.wm.read_factory_settings(use_empty=True)
body = build_human.build("kael")
rig = body.parent
print("BODY", body.name, len(body.data.vertices), len(body.data.polygons), [m.type for m in body.modifiers])
print("VG count", len(body.vertex_groups))
bones = {b.name: b for b in rig.data.bones}
print("NBONES", len(bones))
out = {}
for b in rig.data.bones:
    h = rig.matrix_world @ b.head_local
    t = rig.matrix_world @ b.tail_local
    m = (rig.matrix_world @ b.matrix_local).to_3x3()
    out[b.name] = {"head": list(h), "tail": list(t), "x": list(m.col[0]), "z": list(m.col[2]), "parent": b.parent.name if b.parent else None}
before = set(bpy.data.objects)
ANIM = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets", "Art", "Animations", "Anim_Male.fbx")
bpy.ops.import_scene.fbx(filepath=ANIM, automatic_bone_orientation=False)
src = next(o for o in bpy.data.objects if o not in before and o.type == "ARMATURE")
print("ANIM rig", src.name, len(src.data.bones), "scale", src.scale[:], "rot", src.rotation_euler[:])
worst = []
for b in src.data.bones:
    if b.name not in out:
        print("MISSING in MPFB:", b.name); continue
    h = src.matrix_world @ b.head_local; t = src.matrix_world @ b.tail_local
    d_a = (t - h).normalized()
    o = out[b.name]
    d_m = (np.array(o["tail"]) - np.array(o["head"])); d_m /= np.linalg.norm(d_m)
    ang = math.degrees(math.acos(max(-1, min(1, float(np.dot(d_a, d_m))))))
    ma = (src.matrix_world @ b.matrix_local).to_3x3()
    xa = ma.col[0]
    xang = math.degrees(math.acos(max(-1, min(1, float(np.dot(xa, o["x"]))))))
    worst.append((ang, xang, b.name, tuple(round(v, 3) for v in h), tuple(round(v, 3) for v in o["head"])))
worst.sort(reverse=True)
for w in worst[:40]:
    print("DIR %6.2f  ROLL %6.2f  %-32s anim %s mpfb %s" % w)
print("ACTIONS", len(bpy.data.actions), sorted(a.name for a in bpy.data.actions)[:50])
json.dump(out, open(os.path.join(HERE, "..", "logs", "mpfb_bones.json"), "w"), indent=1)
# weights stats
me = body.data
cnt = np.array([len([g for g in v.groups if g.weight > 1e-4]) for v in me.vertices])
print("INFL hist", np.bincount(cnt)[:12])
print("GROUPS", sorted(g.name for g in body.vertex_groups)[:200])
