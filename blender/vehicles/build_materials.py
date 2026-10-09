"""Bake every vehicle texture set into Assets/Art/Vehicles/Textures (procedural numpy generators, tileable).

Run:  Blender -b --factory-startup --python build_materials.py -- [names...]
 (also runs under plain python3 + numpy)
Writes out/materials_baked.json with per-material texture paths and stats.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import pngio  # noqa: E402
import vmatdefs as MD  # noqa: E402
import vpaths  # noqa: E402
import vtex as T  # noqa: E402


def argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else a[1:]


def write_set(name, maps, srgb=("BaseColor", "Emission")):
    """maps: chan -> float array (H,W,C) in 0..1; Emission given in LINEAR and converted to sRGB here."""
    out = {}
    d = os.path.join(vpaths.TEXTURES, name)
    os.makedirs(d, exist_ok=True)
    for chan, arr in maps.items():
        a = np.asarray(arr, np.float32)
        if chan == "Emission":
            a = pngio.linear_to_srgb(a)
        if chan == "Normal":
            a = a[..., :3]
        p = os.path.join(d, f"{name}_{chan}.png")
        pngio.write_png(p, pngio.to_u8(a))
        out[chan] = os.path.relpath(p, vpaths.UNITY_VEH)
    return out


def stats(maps):
    s = {}
    if "MaskMap" in maps:
        m = maps["MaskMap"]
        s["metal_mean"] = round(float(m[..., 0].mean()), 3)
        s["smooth_mean"] = round(float(m[..., 3].mean()), 3)
    if "BaseColor" in maps:
        s["albedo_mean_srgb"] = [round(float(x), 3) for x in maps["BaseColor"][..., :3].reshape(-1, 3).mean(0)]
    return s


def build(only=None):
    t0 = time.time()
    state_p = os.path.join(vpaths.OUT, "materials_baked.json")
    state = json.load(open(state_p)) if os.path.exists(state_p) else {}

    def want(n):
        return not only or n in only

    # ---------------------------------------------------------------- paints (shared flake normal)
    shared = None
    for name, (c, m, mf, s, _lab) in MD.PAINTS.items():
        if not want(name) and not (only and any(o in MD.PAINTS for o in only) and shared is None and name == "veh_paint_midnight"):
            continue
        maps, shared = T.paint_set(MD.BODY, 2.0, c, m, mf, s, shared=shared)
        if name == "veh_paint_midnight":
            files = write_set(name, maps)
        else:
            files = write_set(name, {"BaseColor": maps["BaseColor"], "MaskMap": maps["MaskMap"]})
        state[name] = {"stats": stats(maps), "files": files}
        print(f"[mat] {name} {time.time() - t0:.1f}s", flush=True)
    gens = {
        "veh_paint_wrecked": lambda: T.wrecked_paint_set(MD.BODY, 2.0),
        "veh_burnt": lambda: T.burnt_set(MD.BODY, 2.0),
        "veh_chrome": lambda: T.chrome_set(MD.DETAIL, 1.0),
        "veh_carbon": lambda: T.carbon_set(MD.DETAIL, 0.25),
        "veh_metal": lambda: T.brushed_metal_set(MD.DETAIL, 0.5),
        "veh_rubber": lambda: T.rubber_set(MD.DETAIL, 0.5),
        "veh_plastic": lambda: T.plastic_set(MD.DETAIL, 0.5),
        "veh_interior": lambda: T.interior_set(MD.DETAIL, 0.5),
        "veh_decal": lambda: T.decal_atlas_set(MD.DETAIL),
        "veh_glass_cracked": lambda: T.glass_cracked_set(MD.DETAIL, 1.0),
        "veh_thruster": lambda: T.thruster_set(MD.DETAIL, 0.3, MD.REGISTRY["veh_thruster"]["emission"]),
        "veh_navlight": lambda: T.navlight_set(256),
        "veh_holo_sign": lambda: T.holo_sign_set(MD.DETAIL),
    }
    for name, g in gens.items():
        if not want(name):
            continue
        maps = g()
        state[name] = {"stats": stats(maps), "files": write_set(name, maps)}
        print(f"[mat] {name} {time.time() - t0:.1f}s", flush=True)
    # ---------------------------------------------------------------- LED light units
    if not only or any(n in MD.EMISSIVE for n in only) or "veh_led" in only:
        pat = T.led_pattern(MD.DETAIL)
        sh = T.led_shared(MD.DETAIL, 0.25, pat)
        state["veh_led"] = {"stats": stats(sh), "files": write_set("veh_led", sh)}
        for name, d in MD.EMISSIVE.items():
            maps = T.emissive_set(MD.DETAIL, 0.25, d["emission"], d["lens"], pat)
            state[name] = {"stats": stats(maps), "files": write_set(name, maps)}
            print(f"[mat] {name} {time.time() - t0:.1f}s", flush=True)
    json.dump(state, open(state_p, "w"), indent=1)
    tot = 0
    for root, _, files in os.walk(vpaths.TEXTURES):
        tot += sum(os.path.getsize(os.path.join(root, f)) for f in files if f.endswith(".png"))
    print(f"[mat] done in {time.time() - t0:.1f}s, textures total {tot / 1e6:.1f} MB")


if __name__ == "__main__":
    build(set(argv()) or None)
