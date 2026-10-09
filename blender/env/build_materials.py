"""Bake the environment material set to Unity textures.

  Blender -b --factory-startup --python build_materials.py -- [--res N (forces one size)] [--samples 6] [names...]

Resolution per material comes from matdefs ('res', default 1024; tints follow their parent).

Writes Assets/Art/Environment/Textures/<name>/<name>_{BaseColor,Normal,MaskMap,Occlusion[,Emission]}.png and
blender/env/out/materials_baked.json (merged into manifest.json by write_manifest.py).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bakekit  # noqa: E402
import envpaths  # noqa: E402
import matdefs  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    res, samples, names, force_res = 1024, 6, [], False
    i = 0
    while i < len(argv):
        if argv[i] == "--res":
            res = int(argv[i + 1]); force_res = True; i += 2
        elif argv[i] == "--samples":
            samples = int(argv[i + 1]); i += 2
        else:
            names.append(argv[i]); i += 1
    reg = matdefs.REGISTRY
    todo = names or [n for n, d in reg.items() if d["kind"] in ("baked", "tint")]
    # parents first so tints can reference them
    todo.sort(key=lambda n: 0 if reg[n]["kind"] == "baked" else 1)
    os.makedirs(envpaths.STATE, exist_ok=True)
    state_path = os.path.join(envpaths.STATE, "materials_baked.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    baker = bakekit.Baker(res=res, samples=samples)
    t0 = time.time()
    for name in todo:
        d = reg[name]
        # per-material resolution (matdefs 'res'; tints follow their parent) unless --res forces one
        r = res if force_res else (d.get("res") or (reg[d["parent"]].get("res") if d["kind"] == "tint" else None) or res)
        baker.set_res(r)
        out_dir = os.path.join(envpaths.TEXTURES, name)
        if d["kind"] == "baked":
            info = bakekit.bake_material(baker, name, d, out_dir)
            info["textures"] = {k: f"Textures/{name}/{v}" for k, v in info.pop("files").items()}
        else:
            parent = reg[d["parent"]]
            mdef = dict(parent)
            mdef["params"] = dict(parent.get("params", {}), **d["params"])
            info = bakekit.bake_material(baker, name, mdef, out_dir, tint_only=True)
            tex = {k: f"Textures/{name}/{v}" for k, v in info.pop("files").items()}
            ptex = state.get(d["parent"], {}).get("textures", {})
            for k in ("Normal", "MaskMap", "Occlusion"):
                p = ptex.get(k) or f"Textures/{d['parent']}/{d['parent']}_{k}.png"
                tex[k] = p
            info["textures"] = tex
            info["sharesMapsWith"] = d["parent"]
        info["res"] = r
        state[name] = info
        tmp = state_path + f".tmp{os.getpid()}"
        json.dump(state, open(tmp, "w"), indent=1)
        os.replace(tmp, state_path)
    print(f"[materials] baked {len(todo)} in {time.time() - t0:.1f}s")


main()
