"""Analyse material usage of exported FBX buildings: per material face count, area, short-extent stats."""
import sys, bpy, bmesh, math, json
import numpy as np
argv = sys.argv[sys.argv.index("--") + 1:]
out = {}
for path in argv:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH" or not ob.name.endswith("LOD0"):
            continue
        me = ob.data
        bm = bmesh.new(); bm.from_mesh(me)
        uvl = bm.loops.layers.uv.active
        stats = {}
        for f in bm.faces:
            mn = me.materials[f.material_index].name.split(".")[0]
            us = [l[uvl].uv[0] for l in f.loops]; vs = [l[uvl].uv[1] for l in f.loops]
            du, dv = max(us) - min(us), max(vs) - min(vs)
            s = stats.setdefault(mn, {"faces": 0, "area": 0.0, "short": []})
            s["faces"] += 1; s["area"] += f.calc_area(); s["short"].append(min(du, dv))
        res = {}
        for k, s in stats.items():
            a = np.array(s["short"])
            res[k] = {"faces": s["faces"], "area": round(s["area"], 2), "short_p50": round(float(np.percentile(a, 50)), 3),
                      "short_p90": round(float(np.percentile(a, 90)), 3), "short_max": round(float(a.max()), 3),
                      "frac_gt_025": round(float((a > 0.25).mean()), 3), "frac_gt_05": round(float((a > 0.5).mean()), 3)}
        out[ob.name] = res
        bm.free()
json.dump(out, open("/Users/kartikey/Desktop/Game/blender/city_landmarks/out/analyze.json", "w"), indent=1)
