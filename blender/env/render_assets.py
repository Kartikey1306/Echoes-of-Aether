"""Re-import every exported FBX, validate it, and render preview contact sheets with the baked textures.

  Blender -b --factory-startup --python render_assets.py -- [--sheet name] [--cols 4] [--size 480x360]
          [--views 1|2] [--lod 0|1|2] [--night] [--check-only] [names or globs...]
--night renders under the neon night studio (wet floor, magenta/cyan rim lights, bloom).

Checks: exactly the record's <Name>_LOD0 / _LOD1 (/ _LOD2) meshes, material names all in the registry (no '.001'
suffixes), UV0 present, base pivot (min Y ~ 0 in Unity space), dimensions match the record.
Results -> blender/env/out/fbx_check.json
"""
import fnmatch
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import envpaths  # noqa: E402
import matdefs  # noqa: E402
import preview  # noqa: E402


def check_and_load(rec):
    path = os.path.join(envpaths.UNITY_ENV, rec["file"])
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, axis_forward="-Z", axis_up="Y", use_custom_normals=True, bake_space_transform=True)
    objs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    issues = []
    names = sorted(o.name for o in objs)
    want = sorted(rec["meshes"].values())
    if names != want:
        issues.append(f"mesh names {names} != {want}")
    for o in objs:
        for m in o.data.materials:
            if m is None or m.name not in matdefs.REGISTRY:
                issues.append(f"{o.name}: bad material {m.name if m else None}")
        if not o.data.uv_layers:
            issues.append(f"{o.name}: no UVs")
        if any(abs(s - 1) > 1e-4 for s in o.scale) or any(abs(r) > 1e-4 for r in o.rotation_euler):
            issues.append(f"{o.name}: non-identity transform scale={tuple(o.scale)} rot={tuple(o.rotation_euler)}")
    lod0 = [o for o in objs if o.name.endswith("_LOD0")]
    if lod0:
        o = lod0[0]
        a = np.array([o.matrix_world @ v.co for v in o.data.vertices])
        mn, mx = a.min(0), a.max(0)
        size_u = [mx[0] - mn[0], mx[2] - mn[2], mx[1] - mn[1]]
        if rec.get("pivot", "base-centre") == "base-centre" and abs(mn[2]) > 0.02:
            issues.append(f"pivot: min height {mn[2]:.3f} != 0")
        if any(abs(a_ - b_) > 0.01 for a_, b_ in zip(size_u, rec["size"])):
            issues.append(f"size {np.round(size_u, 3).tolist()} != record {rec['size']}")
    return objs, issues


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    cols, size, views, lod, sheet_name, pats, night, check_only = 4, (480, 360), 1, 0, None, [], False, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--cols":
            cols = int(argv[i + 1]); i += 2
        elif a == "--size":
            size = tuple(int(x) for x in argv[i + 1].split("x")); i += 2
        elif a == "--views":
            views = int(argv[i + 1]); i += 2
        elif a == "--lod":
            lod = int(argv[i + 1]); i += 2
        elif a == "--sheet":
            sheet_name = argv[i + 1]; i += 2
        elif a == "--night":
            night = True; i += 1
        elif a == "--check-only":
            check_only = True; i += 1
        else:
            pats.append(a); i += 1
    recs = json.load(open(os.path.join(envpaths.STATE, "assets.json")))
    names = [n for n in recs if not pats or any(fnmatch.fnmatch(n, p) for p in pats)]
    check_path = os.path.join(envpaths.STATE, "fbx_check.json")
    checks = json.load(open(check_path)) if os.path.exists(check_path) else {}
    tiles = []
    tmp = os.path.join(envpaths.STATE, f"tmp_render_{os.getpid()}.png")
    for n in names:
        rec = recs[n]
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if check_only:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            objs, issues = check_and_load(rec)
            checks[n] = {"ok": not issues, "issues": issues}
            if issues:
                print(f"[check] {n}: {issues}")
            continue
        cam = preview.night(size, 32) if night else preview.studio(size, 24)
        objs, issues = check_and_load(rec)
        checks[n] = {"ok": not issues, "issues": issues}
        print(f"[check] {n}: {'OK' if not issues else issues}")
        show = [o for o in objs if o.name.endswith(f"_LOD{lod}")]
        for o in objs:
            if o not in show:
                o.hide_render = True
        for o in show:
            for k, m in enumerate(o.data.materials):
                if m is not None and m.name in matdefs.REGISTRY:
                    preview.textured(m.name, m)
        a = np.array([o.matrix_world @ v.co for o in show for v in o.data.vertices])
        mn, mx = a.min(0), a.max(0)
        if mn[2] < -0.01:  # non-base pivots (hanging signs, pipes): lift for display only
            for o in objs:
                o.location.z -= mn[2]
            bpy.context.view_layer.update()
            mx[2] -= mn[2]
            mn[2] = 0.0
        if night:  # scale the neon rim lights to the asset so big buildings are lit like props
            ext = float(max(mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]))
            k = max(1.0, ext / 4.0)
            cz = float(mn[2] + mx[2]) / 2
            for o in bpy.context.scene.objects:
                if o.type == "LIGHT" and o.data.type == "AREA":
                    o.location = (o.location.x * k + (mn[0] + mx[0]) / 2, o.location.y * k + (mn[1] + mx[1]) / 2, o.location.z * k * 0.8 + max(0.0, cz - 2.0))
                    o.data.energy *= k * k
                    o.data.size *= k
        t = rec["tris"][f"LOD{lod}"]
        view_list = [(35, 20), (215, 28)] if views == 2 else [(35, 20)]
        row = []
        for vi, (az, el) in enumerate(view_list):
            preview.frame(cam, mn, mx, az=az, el=el, margin=1.02)
            if vi == 0:
                lab = preview.label(cam, f"{n}  {t} tris  {rec['size'][0]:.2f}x{rec['size'][1]:.2f}x{rec['size'][2]:.2f} m", size=0.034)
            row.append(preview.render_array(tmp))
        tiles.append(np.concatenate(row, axis=1) if len(row) > 1 else row[0])
    import fcntl
    with open(check_path + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        cur = json.load(open(check_path)) if os.path.exists(check_path) else {}
        cur.update({n: checks[n] for n in names})
        json.dump(cur, open(check_path, "w"), indent=1)
        fcntl.flock(lk, fcntl.LOCK_UN)
    if os.path.exists(tmp):
        os.remove(tmp)
    if tiles:
        per = cols * max(1, 12 // cols)
        base = sheet_name or "assets"
        for s in range(0, len(tiles), per):
            out = os.path.join(envpaths.PREVIEWS, f"{base}_{s // per + 1:02d}.png")
            preview.sheet(tiles[s:s + per], cols, out)
            print("[render] sheet", out)
    bad = [k for k in names if not checks[k]["ok"]]
    print(f"[check] {len(names) - len(bad)}/{len(names)} ok" + (f" BAD: {bad}" if bad else ""))


main()
