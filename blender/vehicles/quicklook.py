"""Fast iteration: build one vehicle LOD in build space and render a few studio views (no export).
Blender -b --factory-startup --python quicklook.py -- <Name> [lod] [samples] [views=fr,rr,side,top] [scene]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import vehicles  # noqa: E402
import vkit as K  # noqa: E402
import vmat  # noqa: E402
import vpaths  # noqa: E402
import vscene  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
name = a[0] if a else "CyberCar_Coupe"
lod = int(a[1]) if len(a) > 1 else 0
samples = int(a[2]) if len(a) > 2 else 24
views = (a[3] if len(a) > 3 else "fr,rr").split(",")
scene = a[4] if len(a) > 4 else "studio"

t0 = time.time()
K.reset()
res = vehicles.build(name, lod)
objs = [res["body"]] + [w[0] for w in res["wheels"].values()] + [t[0] for t in res.get("thrusters", {}).values()]
for wn, (wo, c) in list(res["wheels"].items()) + list(res.get("thrusters", {}).items()):
    wo.location = c
nt = sum(K.tris(o) for o in objs if o.type == "MESH")
print(f"[ql] built {name} lod{lod}: {nt} tris in {time.time() - t0:.1f}s")
for o in objs:
    K.box_uv(o)
    K.shade(o)
vmat.build_all()
lo, hi = K.bounds_world(objs)
size = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
print("[ql] size", [round(float(x), 3) for x in size])
vscene.setup_render((960, 540), samples)
if scene == "studio":
    vscene.studio(size)
else:
    vscene.street(size)
front = Vector((0, 1, 0))
for v in views:
    if v == "fr":
        vscene.cam_three_quarter(size, front)
    elif v == "rr":
        vscene.cam_three_quarter(size, front, rear=True)
    elif v == "side":
        vscene.camera((size[0] * 0 + 7.5, 0, 0.8), (0, 0, 0.6), lens=50)
    elif v == "top":
        vscene.camera((0.01, 0, 9), (0, 0, 0), lens=50)
    elif v == "front":
        vscene.camera((0, 7, 0.7), (0, 0, 0.6), lens=50)
    elif v == "low":
        vscene.cam_three_quarter(size, front, height=0.45, lens=28, dist_mul=0.75)
    bpy.context.scene.render.filepath = os.path.join(vpaths.OUT, "ql", f"{name}_lod{lod}_{v}.png")
    bpy.ops.render.render(write_still=True)
print(f"[ql] done {time.time() - t0:.1f}s")
