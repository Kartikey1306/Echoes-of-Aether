"""Build every vehicle at each LOD without rendering; print triangle counts and bounds (dev check)."""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402

import vehicles  # noqa: E402
import vkit as K  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
names = [n for n in a if not n.isdigit()] or vehicles.names()
lods = [int(n) for n in a if n.isdigit()] or [0, 1, 2]
for name in names:
    for lod in lods:
        t0 = time.time()
        K.reset()
        try:
            res = vehicles.build(name, lod)
        except Exception:
            print(f"[smoke] {name} lod{lod} FAILED")
            traceback.print_exc()
            continue
        parts = [res["body"]] + [w[0] for w in res["wheels"].values()] + [t[0] for t in res.get("thrusters", {}).values()]
        tb = K.tris(res["body"])
        tw = sum(K.tris(w[0]) for w in res["wheels"].values())
        tt = sum(K.tris(t[0]) for t in res.get("thrusters", {}).values())
        lo, hi = K.bounds_world([res["body"]])
        mats = [m.name for m in res["body"].data.materials]
        print(f"[smoke] {name} lod{lod}: body {tb} wheels {tw} thr {tt} total {tb + tw + tt} | body z {lo[2]:.2f}..{hi[2]:.2f} "
              f"y {lo[1]:.2f}..{hi[1]:.2f} x {lo[0]:.2f}..{hi[0]:.2f} | {time.time() - t0:.1f}s | {len(mats)} mats")
