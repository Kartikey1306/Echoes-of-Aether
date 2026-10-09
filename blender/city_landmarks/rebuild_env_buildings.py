"""Rebuild the environment kit's complete buildings (Building_MidRise_A/B/C, Building_HighRise_D) with the same
geometry builders (blender/env/assets_buildings.py, untouched) and remap their ~40 small materials onto the shared
building atlases (building_trim_atlas + emit_building_atlas): <= 8 material slots each.

Only the four Building_* FBX files and their records in blender/env/out/assets.json are written; patch the
manifest afterwards with  python3 patch_env_manifest.py.

  Blender -b --factory-startup --python rebuild_env_buildings.py -- [names...]
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lmpaths  # noqa: E402
sys.path.insert(1, lmpaths.ENV_SRC)
import envkit as K  # noqa: E402
import envpaths  # noqa: E402
import assets_buildings as AB  # noqa: E402
import atlas_remap as R  # noqa: E402

NAMES = ["Building_MidRise_A", "Building_MidRise_B", "Building_MidRise_C", "Building_HighRise_D"]


def build_one(name):
    spec = AB.ASSETS[name]
    K.reset()
    t0 = time.time()
    meta = {}

    def runner(**kk):
        r = spec["fn"](**kk)
        if K.LOD == 0 and isinstance(r, dict):
            meta.update(r)

    lods = K.build_asset(name, runner, lods=spec.get("lods"), uv_offset=spec.get("uv_offset"), **spec.get("kw", {}))
    before = len(lods[0].data.materials)
    for ob in lods:
        R.remap(ob)
    lod0, lod1 = lods[0], lods[1]
    lod2 = lods[2] if len(lods) > 2 else None
    rel = f"Models/Buildings/{name}.fbx"
    K.export_fbx(lods, os.path.join(envpaths.UNITY_ENV, rel))
    extra = {k: v for k, v in meta.items() if k not in ("colliders",)}
    rec = K.record(name, spec["cat"], spec.get("zones", []), lod0, lod1, rel, colliders=meta.get("colliders"),
                   pivot=spec.get("pivot", "base-centre"), notes=spec.get("notes", ""), extra=extra or None, lod2=lod2)
    rec["atlasRemap"] = {"materialsBefore": before, "materialsAfter": len(lod0.data.materials),
                         "atlases": ["building_trim_atlas", "emit_building_atlas"]}
    K.save_record(rec)
    print(f"[bld] {name}: materials {before} -> {len(lod0.data.materials)} {rec['materials']}  tris {rec['tris']}  {time.time() - t0:.1f}s")
    return rec


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for n in (argv or NAMES):
        build_one(n)


main()
