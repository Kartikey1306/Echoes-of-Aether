"""Build landmark-kit assets -> Assets/Art/CityLandmarks/Models/<folder>/<name>.fbx + out/records/<name>.json.

  Blender -b --factory-startup --python build.py -- [--list] [name or glob ...]
"""
import fnmatch
import importlib
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmkit as L  # noqa: E402

MODULES = ["lm_market", "lm_kowloon", "lm_arcology", "lm_canal", "lm_foundry", "lm_buildings", "lm_plaza", "lm_modules"]
FOLDER = {"landmark": "Landmarks", "building": "Buildings", "plaza": "Plaza", "module": "Modules"}


def registry():
    reg = {}
    for m in MODULES:
        try:
            mod = importlib.import_module(m)
        except ModuleNotFoundError as e:
            if e.name == m:
                continue
            raise
        for k, v in getattr(mod, "LANDMARKS", {}).items():
            reg[k] = dict(v, cat=v.get("cat", "landmark"), module=m)
        for k, v in getattr(mod, "ASSETS", {}).items():
            reg[k] = dict(v, module=m)
    return reg


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    reg = registry()
    if "--list" in argv:
        for n, s in reg.items():
            print(f"{n:36s} {s['cat']:9s} {s['module']}")
        return
    names = [n for n in reg if not argv or any(fnmatch.fnmatch(n, p) for p in argv)]
    fails = []
    for n in names:
        s = reg[n]
        t0 = time.time()
        try:
            rec, _ = L.build(n, s["fn"], s["cat"], notes=s.get("notes", ""), folder=FOLDER.get(s["cat"], s["cat"].title()),
                             pivot=s.get("pivot", "base-centre"), **s.get("kw", {}))
            rec["district"] = s.get("district", "")
            import json
            json.dump(rec, open(os.path.join(L.lmpaths.RECORDS, n + ".json"), "w"), indent=1)
            print(f"[build] {n} ok {time.time() - t0:.1f}s", flush=True)
        except Exception:
            traceback.print_exc()
            fails.append(n)
    print(f"[build] {len(names) - len(fails)}/{len(names)} ok" + (f"  FAILED: {fails}" if fails else ""), flush=True)


main()
