"""Build environment assets -> FBX (LOD0 + LOD1) + records for the manifest.

  Blender -b --factory-startup --python build_assets.py -- [--list] [--module street] [names or prefixes*...]
"""
import fnmatch
import importlib
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import envkit as K  # noqa: E402
import envpaths  # noqa: E402

# assets_vehicles is intentionally NOT built here any more: vehicles are owned by the vehicle artist and ship from
# Assets/Art/Vehicles/ with their own manifest. The legacy Car_*/Bus_*/TrainCar_* exports and records stay frozen.
MODULES = ["assets_street", "assets_interior", "assets_structure", "assets_metro", "assets_vault",
           "assets_rooftop", "assets_monument", "assets_debris", "assets_facade", "assets_buildings", "assets_dressing",
           "assets_neon"]
FOLDERS = {"street": "Street", "props": "Props", "vehicles": "Vehicles", "facility": "Facility", "structure": "Structure",
           "metro": "Metro", "vault": "Vault", "rooftop": "Rooftop", "monument": "Monument", "debris": "Debris", "core": "Core",
           "signage": "Signage", "camp": "Camp", "facade": "Facade", "building": "Buildings", "skyline": "Buildings",
           "dressing": "Dressing", "neon": "Neon", "streetfx": "Neon"}


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
    kw = spec.get("kw", {})
    meta = {}

    def runner(**kk):
        r = spec["fn"](**kk)
        if K.LOD == 0 and isinstance(r, dict):
            meta.update(r)

    lods = K.build_asset(name, runner, lods=spec.get("lods"), uv_offset=spec.get("uv_offset"), **kw)
    lod0, lod1 = lods[0], lods[1]
    lod2 = lods[2] if len(lods) > 2 else None
    folder = FOLDERS.get(spec["cat"], spec["cat"].title())
    rel = f"Models/{folder}/{name}.fbx"
    K.export_fbx(lods, os.path.join(envpaths.UNITY_ENV, rel))
    extra = {k: v for k, v in meta.items() if k not in ("colliders",)}
    rec = K.record(name, spec["cat"], spec.get("zones", []), lod0, lod1, rel, colliders=meta.get("colliders"),
                   pivot=spec.get("pivot", "base-centre"), notes=spec.get("notes", ""), extra=extra or None, lod2=lod2)
    K.save_record(rec)
    l2 = f" LOD2 {rec['tris']['LOD2']:6d}" if lod2 is not None else ""
    print(f"[asset] {name:28s} LOD0 {rec['tris']['LOD0']:6d} LOD1 {rec['tris']['LOD1']:6d}{l2} tris  size {rec['size']}  {time.time() - t0:.1f}s")
    return rec


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    reg = registry()
    if "--list" in argv:
        for n, s in reg.items():
            print(f"{n:30s} {s['cat']:10s} {s['module']}")
        return
    mods = []
    pats = []
    i = 0
    while i < len(argv):
        if argv[i] == "--module":
            mods.append(argv[i + 1]); i += 2
        else:
            pats.append(argv[i]); i += 1
    names = [n for n, s in reg.items()
             if (not mods or any(s["module"].endswith(m) for m in mods))
             and (not pats or any(fnmatch.fnmatch(n, p) for p in pats))]
    fails = []
    for n in names:
        try:
            build_one(n, reg[n])
        except Exception:
            traceback.print_exc()
            fails.append(n)
    print(f"[build] {len(names) - len(fails)}/{len(names)} ok" + (f"  FAILED: {fails}" if fails else ""))


main()
