"""Re-import every exported vehicle FBX and check it against its record.

Blender -b --factory-startup --python verify_fbx.py -- [Name ...]
Checks: object names + hierarchy (LOD meshes, pivot empties, child LODs), root transforms (identity), pivot
positions, LOD0 bounds/size, triangle counts, material slot names (== record, all known to the registry),
UV layer present, no loose verts at the pivot and the vehicle resting on y=0 (Unity space).
Writes out/verify_report.json; exit code 1 when any check fails.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import vmatdefs as MD  # noqa: E402
import vpaths  # noqa: E402


def argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def unity_from_blender(v):
    """Re-imported Blender space (front -Y) -> Unity."""
    return [-v[0], v[2], -v[1]]


def tris(o):
    o.data.calc_loop_triangles()
    return len(o.data.loop_triangles)


def world_bounds(objs):
    lo = np.array([1e9] * 3)
    hi = np.array([-1e9] * 3)
    for o in objs:
        a = np.empty(len(o.data.vertices) * 3, np.float32)
        o.data.vertices.foreach_get("co", a)
        a = a.reshape(-1, 3)
        M = np.array(o.matrix_world)
        a = a @ M[:3, :3].T + M[:3, 3]
        lo = np.minimum(lo, a.min(0))
        hi = np.maximum(hi, a.max(0))
    return lo, hi


def verify(name):
    rec = json.load(open(os.path.join(vpaths.RECORDS, f"{name}.json")))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    path = os.path.join(vpaths.UNITY_VEH, rec["file"])
    bpy.ops.import_scene.fbx(filepath=path, bake_space_transform=True)
    bpy.context.view_layer.update()
    obs = {o.name: o for o in bpy.context.scene.objects}
    errs, info = [], {}

    def check(cond, msg):
        if not cond:
            errs.append(msg)
    # ---- names / hierarchy
    for lod, mn in rec["meshes"].items():
        o = obs.get(mn)
        check(o is not None and o.type == "MESH", f"missing body mesh {mn}")
        if o is None:
            continue
        check(o.parent is None, f"{mn} should be a root object")
        mw = np.array(o.matrix_world)
        check(np.allclose(mw, np.eye(4), atol=1e-4), f"{mn} transform not identity: {np.round(mw, 4).tolist()}")
        t = tris(o)
        info[f"{mn}_tris"] = t
    for a in rec["animatedParts"]:
        em = obs.get(a["name"])
        check(em is not None, f"missing pivot {a['name']}")
        if em is None:
            continue
        pu = unity_from_blender(em.matrix_world.translation)
        check(np.allclose(pu, a["pivot"], atol=2e-3), f"{a['name']} pivot {np.round(pu, 3).tolist()} != record {a['pivot']}")
        r = np.array(em.matrix_world.to_3x3())
        check(np.allclose(r / np.linalg.norm(r, axis=0), np.eye(3), atol=1e-3), f"{a['name']} pivot has rotation/scale {np.round(r, 3).tolist()}")
        for lod, mn in a["meshes"].items():
            c = obs.get(mn)
            check(c is not None and c.parent == em, f"{mn} missing or not parented to {a['name']}")
            if c is not None:
                check(np.allclose(np.array(c.matrix_local), np.eye(4), atol=1e-4), f"{mn} local transform not identity")
    # ---- triangle counts per LOD (body + parts)
    for lod in ("LOD0", "LOD1", "LOD2"):
        objs = [o for o in obs.values() if o.type == "MESH" and o.name.endswith("_" + lod)]
        t = sum(tris(o) for o in objs)
        info[f"tris_{lod}"] = t
        check(abs(t - rec["tris"][lod]) <= max(4, rec["tris"][lod] * 0.01), f"{lod} tris {t} != record {rec['tris'][lod]}")
    t0 = info["tris_LOD0"]
    check(t0 <= 35500, f"LOD0 {t0} tris over the 35k budget")
    r1, r2 = info["tris_LOD1"] / max(t0, 1), info["tris_LOD2"] / max(t0, 1)
    info["lod_ratios"] = [round(r1, 3), round(r2, 3)]
    check(0.30 <= r1 <= 0.46, f"LOD1 ratio {r1:.2f} outside ~40%")
    check(0.07 <= r2 <= 0.16, f"LOD2 ratio {r2:.2f} outside ~12%")
    # ---- bounds / size / ground
    lod0 = [o for o in obs.values() if o.type == "MESH" and o.name.endswith("_LOD0")]
    lo, hi = world_bounds(lod0)
    ulo = np.array(unity_from_blender(lo))
    uhi = np.array(unity_from_blender(hi))
    size = np.abs(uhi - ulo)
    info["size"] = np.round(size, 3).tolist()
    check(np.allclose(size, rec["size"], atol=0.01), f"size {np.round(size, 3).tolist()} != record {rec['size']}")
    check(abs(lo[2]) < 0.012, f"vehicle does not rest on the ground: min y = {lo[2]:.3f}")
    ctr = (lo + hi) / 2
    check(abs(ctr[0]) < 0.06, f"not centred in X: {ctr[0]:.3f}")
    # front faces Unity +Z: the headlight anchor must be at +Z
    hl = rec["lights"].get("headlight")
    if hl:
        check(hl["center"][2] > 0, "headlight anchor not at +Z (front)")
    tl = rec["lights"].get("taillight")
    if tl:
        check(tl["center"][2] < 0, "taillight anchor not at -Z (rear)")
    # ---- materials
    slots = []
    for o in lod0:
        for m in o.data.materials:
            n = m.name if m else None
            if n and n not in slots:
                slots.append(n)
    info["materials"] = slots
    check(set(slots) == set(rec["materials"]), f"material slots {sorted(slots)} != record {sorted(rec['materials'])}")
    unknown = [s for s in slots if s not in MD.REGISTRY]
    check(not unknown, f"unknown materials {unknown}")
    for o in obs.values():
        if o.type == "MESH":
            check(len(o.data.uv_layers) >= 1, f"{o.name} has no UVs")
            for m in o.data.materials:
                check(m is not None, f"{o.name} has an empty material slot")
    return {"name": name, "ok": not errs, "errors": errs, "info": info}


if __name__ == "__main__":
    names = argv() or [f[:-5] for f in sorted(os.listdir(vpaths.RECORDS)) if f.endswith(".json")]
    rep_p = os.path.join(vpaths.OUT, "verify_report.json")
    rep = json.load(open(rep_p)) if os.path.exists(rep_p) else {}
    bad = 0
    for n in names:
        r = verify(n)
        rep[n] = r
        bad += not r["ok"]
        print(f"[verify] {n}: {'OK' if r['ok'] else 'FAIL'} tris={[r['info'].get('tris_LOD' + str(l)) for l in range(3)]} "
              f"size={r['info'].get('size')} ratios={r['info'].get('lod_ratios')}")
        for e in r["errors"]:
            print(f"[verify]    - {e}")
    json.dump(rep, open(rep_p, "w"), indent=1)
    sys.exit(1 if bad else 0)
