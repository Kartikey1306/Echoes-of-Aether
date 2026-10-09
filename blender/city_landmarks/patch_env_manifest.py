"""Targeted patch of Assets/Art/Environment/manifest.json after rebuild_env_buildings.py: replaces ONLY the four
Building_* asset entries (from blender/env/out/assets.json) and adds/updates the two shared building atlas materials
(building_trim_atlas, emit_building_atlas). Every other asset / material / decal entry is left untouched.

  python3 patch_env_manifest.py
"""
import json
import os

import lmpaths

NAMES = ["Building_MidRise_A", "Building_MidRise_B", "Building_MidRise_C", "Building_HighRise_D"]


def atlas_materials():
    lay = json.load(open(lmpaths.ATLAS_LAYOUT))
    out = {}
    for name, a in lay["atlases"].items():
        e = {"kind": "baked", "shader": "Universal Render Pipeline/Lit", "surface": "Opaque", "uvMode": "atlas", "tileSizeMeters": None,
             "tiling": [1.0, 1.0], "textures": dict(a["textures"]), "textureSize": 2048, "maxTextureSize": {"desktop": 2048, "webgl": 1024},
             "normalScale": 1.0, "occlusionStrength": 1.0,
             "notes": "Shared building atlas (blender/city_landmarks/atlas_build.py): " +
                      ("trim sheet - full-width bands tile along U, flat colour cells" if "trim" in name else
                       "LED ads, light boxes, window / office interiors, signs, LED strips, neon / lamp colours; emission texels are pre-scaled by emissionIntensity")}
        if name.startswith("emit_"):
            e["emissionColor"] = [1.0, 1.0, 1.0]
            e["emissionIntensity"] = lay["emitMax"]
        out[name] = e
    return out


def main():
    mp = os.path.join(lmpaths.ENV_KIT, "manifest.json")
    man = json.load(open(mp))
    recs = json.load(open(os.path.join(lmpaths.ENV_STATE, "assets.json")))
    by = {a["name"]: i for i, a in enumerate(man["assets"])}
    for n in NAMES:
        r = dict(recs[n])
        old = man["assets"][by[n]]
        r["lodTransitions"] = old.get("lodTransitions", [0.25, 0.08, 0.0])
        if "fbxCheck" in old:
            r["fbxCheck"] = old["fbxCheck"]
        man["assets"][by[n]] = r
        print(f"[patch] {n}: {len(old['materials'])} -> {len(r['materials'])} materials")
    man["materials"].update(atlas_materials())
    tmp = mp + ".tmp"
    json.dump(man, open(tmp, "w"), indent=1)
    os.replace(tmp, mp)
    print("[patch] wrote", mp)


if __name__ == "__main__":
    main()
