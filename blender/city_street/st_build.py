"""Build the street-kit assets -> Assets/Art/CityStreet/Models/<Folder>/<Name>.fbx (LOD0/LOD1[/LOD2]) + out/assets.json.

  Blender -b --factory-startup --python st_build.py -- [--list] [--module shops] [names or globs...]
"""
import fnmatch
import importlib
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stkit  # noqa: E402  (must come first: re-points envpaths)
import stpaths  # noqa: E402

K = stkit.K
MODULES = ["st_assets_shops", "st_assets_street", "st_assets_overhead"]
FOLDERS = {"storefront": "Shops", "streetprop": "Props", "wallprop": "Wall", "overhead": "Overhead"}


def registry():
    reg = {}
    for m in MODULES:
        try:
            mod = importlib.import_module(m)
        except ModuleNotFoundError as e:
            if e.name == m:
                continue
            raise
        for name, spec in mod.ASSETS.items():
            spec = dict(spec)
            spec["module"] = m
            reg[name] = spec
    return reg


def build_one(name, spec):
    K.reset()
    t0 = time.time()
    meta = {}

    def runner(**kk):
        r = spec["fn"](**kk)
        if K.LOD == 0 and isinstance(r, dict):
            meta.update(r)

    lods = K.build_asset(name, runner, lods=spec.get("lods"), **spec.get("kw", {}))
    folder = FOLDERS.get(spec["cat"], spec["cat"].title())
    rel = f"Models/{folder}/{name}.fbx"
    K.export_fbx(lods, os.path.join(stpaths.UNITY_ST, rel))
    extra = {k: v for k, v in meta.items() if k != "colliders"}
    rec = K.record(name, spec["cat"], spec.get("zones", []), lods[0], lods[1], rel, colliders=meta.get("colliders"),
                   pivot=spec.get("pivot", "base-centre"), notes=spec.get("notes", ""), extra=extra or None,
                   lod2=lods[2] if len(lods) > 2 else None)
    K.save_record(rec)
    t = rec["tris"]
    print(f"[st] {name:26s} LOD0 {t['LOD0']:6d} LOD1 {t['LOD1']:6d}{' LOD2 %6d' % t['LOD2'] if 'LOD2' in t else ''}  size {rec['size']}  {time.time() - t0:.1f}s")
    return rec


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    reg = registry()
    if "--list" in argv:
        for n, s in reg.items():
            print(f"{n:30s} {s['cat']:12s} {s['module']}")
        return
    mods, pats = [], []
    i = 0
    while i < len(argv):
        if argv[i] == "--module":
            mods.append(argv[i + 1])
            i += 2
        else:
            pats.append(argv[i])
            i += 1
    names = [n for n, s in reg.items() if (not mods or any(s["module"].endswith(m) for m in mods))
             and (not pats or any(fnmatch.fnmatch(n, p) for p in pats))]
    fails = []
    for n in names:
        try:
            build_one(n, reg[n])
        except Exception:
            traceback.print_exc()
            fails.append(n)
    print(f"[st] {len(names) - len(fails)}/{len(names)} ok" + (f"  FAILED: {fails}" if fails else ""))


main()
