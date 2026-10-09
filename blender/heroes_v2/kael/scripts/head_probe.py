"""Dump head landmarks: midline profile and face width per height (relative to the Head bone)."""
import bpy, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
import body_def, mpfb_build

bpy.ops.wm.read_factory_settings(use_empty=True)
body = mpfb_build.build("Kael", body_def.PHENOTYPE, body_def.TARGETS, body_def.ASSETS)
rig = body.parent
L = mpfb_build.landmarks(rig)
dg = bpy.context.evaluated_depsgraph_get()
M = np.array(body.matrix_world)
ev = body.evaluated_get(dg).to_mesh()
co = np.array([v.co[:] for v in ev.vertices]) @ M[:3, :3].T + M[:3, 3]
print('MW', np.round(M, 3).tolist())
gi = body.vertex_groups["body"].index
inb = np.ones(len(co), bool)
H = L["Head"]
P = co - H
eye = (L["LeftEye"] + L["RightEye"]) / 2 - H
print("EYE", np.round(eye, 4), "LEYE", np.round(L["LeftEye"] - H, 4), "NECK", np.round(L["Neck"] - H, 4))
head = inb & (P[:, 2] > -0.12) & (np.linalg.norm(P, axis=1) < 0.25)
mid = head & (np.abs(P[:, 0]) < 0.004) & (P[:, 1] < 0.02)
pm = P[mid]
pm = pm[np.argsort(-pm[:, 2])]
print("MIDLINE front profile (z, y)")
for z in np.arange(0.17, -0.13, -0.008):
    s = pm[np.abs(pm[:, 2] - z) < 0.004]
    if len(s):
        print("  z %+.3f  y %+.4f" % (z, s[:, 1].min()))
print("WIDTH (z: max |x| front half, y at max)")
for z in np.arange(0.14, -0.13, -0.01):
    s = P[head & (np.abs(P[:, 2] - z) < 0.004) & (P[:, 1] < 0.04)]
    if len(s):
        i = np.argmax(np.abs(s[:, 0]))
        print("  z %+.3f  x %.4f  y %+.4f" % (z, abs(s[i, 0]), s[i, 1]))
json.dump({"head": H.tolist(), "eye": eye.tolist()}, open(os.path.join(K.LOGS, "head_probe.json"), "w"))
