"""Generate the URP decal texture set defined in decaldefs.py.

  Blender -b --factory-startup --python build_decals.py -- [Name or glob ...] [--maps] [--list]
  (pure numpy: also runs as `python3 build_decals.py [...]`)

Writes Assets/Art/Environment/Decals/<Name>/<Name>_{BaseColor,Normal,MaskMap}.png and merges the entries into
blender/env/out/decals.json (write_manifest.py turns that into the manifest "decals" array).
--maps also writes flat inspection sheets previews/decals_maps_NN.png (colour over ground, alpha, normal, smoothness).
"""
import fnmatch
import json
import os
import sys
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import bpy  # noqa: F401
except ImportError:  # plain python3: bakekit only touches bpy inside its bake functions
    sys.modules["bpy"] = types.ModuleType("bpy")

import numpy as np  # noqa: E402

import bakekit  # noqa: E402
import decaldefs as D  # noqa: E402
import envpaths  # noqa: E402
import pngio  # noqa: E402

OUT = os.path.join(envpaths.UNITY_ENV, "Decals")
STATE = os.path.join(envpaths.STATE, "decals.json")
F32 = np.float32


def cavity(h, px, radii, strength):
    """bakekit.cavity_ao equivalent for rectangular, non-wrapping arrays."""
    if strength <= 0:
        return np.ones_like(h)
    occ = np.zeros_like(h)
    for r in radii:
        s = max(0.6, r / px)
        occ += np.clip((D.blur(h, s) - h) / (r * 1.2), 0.0, 1.0) / len(radii)
    return np.clip(1.0 - occ * strength, 0.0, 1.0)


def _down(a):
    H, W = a.shape[:2]
    if H % 2:
        a = np.concatenate([a, a[-1:]], 0)
    if W % 2:
        a = np.concatenate([a, a[:, -1:]], 1)
    return 0.25 * (a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2])


def _box3(a):
    p = np.pad(a, ((1, 1), (1, 1)) + ((0, 0),) * (a.ndim - 2), mode="edge")
    return sum(p[i:i + a.shape[0], j:j + a.shape[1]] for i in range(3) for j in range(3)) / 9.0


def fill_under(arr, a, thr=0.004):
    """Push-pull pyramid fill of values under (near-)transparent texels from the visible ones, so mip-mapping
    never pulls in a dark halo (and the PNG compresses better)."""
    known = a > thr
    if known.all() or not known.any():
        return arr
    flat = arr.ndim == 2
    v = (arr[..., None] if flat else arr).astype(F32)
    w = (known * np.clip(a * 4.0, 0.05, 1.0)).astype(F32)
    V, Wt = [v * w[..., None]], [w]
    while min(Wt[-1].shape) > 2:
        V.append(_down(V[-1]))
        Wt.append(_down(Wt[-1]))
    est = np.broadcast_to(V[-1].sum((0, 1)) / max(float(Wt[-1].sum()), 1e-8), V[-1].shape).astype(F32)
    for i in range(len(V) - 1, -1, -1):
        H, W = Wt[i].shape
        if est.shape[:2] != (H, W):
            est = _box3(np.repeat(np.repeat(est, 2, 0), 2, 1)[:H, :W])
        ai = np.clip(Wt[i] * 3.0, 0.0, 1.0)[..., None]
        ci = V[i] / np.maximum(Wt[i], 1e-8)[..., None]
        est = ci * ai + est * (1.0 - ai)
    out = np.where(known[..., None], v, est)
    return out[..., 0] if flat else out


def finalize(c, st):
    r = st.result()
    ed = c.edge_dist() / c.px  # pixels from the nearest border
    a = r["a"] * np.clip((ed - 1.0) / 6.0, 0.0, 1.0)  # guarantees alpha == 0 on the outer pixel ring
    a = np.where(a < 1.0 / 510.0, 0.0, a).astype(F32)
    h = r["h"] * D.sst(ed, 2.0, 24.0)  # flatten height toward the borders (height_to_normal wraps)
    nrm = bakekit.height_to_normal(h.astype(np.float64), c.px, st.nstrength).astype(F32)
    ao = cavity(h, c.px, st.ao_radii, st.ao_strength) * r["ao"]
    vis = a > 0
    nrm[~vis] = (0.5, 0.5, 1.0)
    col = fill_under(r["col"], a)
    mask = np.stack([r["mt"], np.clip(ao, 0, 1), np.ones_like(a), r["sm"]], axis=-1)
    mask = fill_under(mask, a)
    mask[..., 2] = 1.0
    return {"col": col, "a": a, "nrm": nrm, "mask": mask}


def save(name, m):
    d = os.path.join(OUT, name)
    os.makedirs(d, exist_ok=True)
    bc = np.concatenate([pngio.to_u8(pngio.linear_to_srgb(m["col"])), pngio.to_u8(m["a"])[..., None]], axis=-1)
    files = {}
    for suf, arr in (("BaseColor", bc), ("Normal", pngio.to_u8(m["nrm"])), ("MaskMap", pngio.to_u8(m["mask"]))):
        p = os.path.join(d, f"{name}_{suf}.png")
        pngio.write_png(p, arr[::-1], level=9)  # bottom-first -> top-first
        files[suf] = f"Decals/{name}/{name}_{suf}.png"
    return files


def entry(name, files, c):
    d = D.DECALS[name]
    return {
        "name": name,
        "sizeMeters": [d["size"][0], d["size"][1]],
        "textures": files,
        "resolution": max(d["px"]),
        "pixels": [d["px"][0], d["px"][1]],
        "projection": d["projection"],
        "use": d["use"],
        "urp": {"shader": D.URP_SHADER, "affectsBaseColor": True, "affectsNormal": True, "affectsMAOS": True,
                "normalBlend": d["normalBlend"], "drawOrder": d["drawOrder"], "projectionDepth": d["projectionDepth"]},
        "tags": d["tags"],
        "orientation": "+U = decal right, +V = decal up (walls: world up; floors: forward). Pivot centre.",
        "texelsPerMeter": round(1.0 / c.px),
    }


# ---------------------------------------------------------------------------------------------- inspection sheet
def _fit(img, T):
    """Area-ish downscale into a T x T tile (letterboxed)."""
    H, W = img.shape[:2]
    s = T / max(H, W)
    if s < 1:
        img = D.blur(img.astype(F32), 0.45 / s)
    hh, ww = max(1, int(H * s)), max(1, int(W * s))
    ys = np.clip(((np.arange(hh) + 0.5) / s).astype(int), 0, H - 1)
    xs = np.clip(((np.arange(ww) + 0.5) / s).astype(int), 0, W - 1)
    out = np.full((T, T) + img.shape[2:], 0.07, F32)
    oy, ox = (T - hh) // 2, (T - ww) // 2
    out[oy:oy + hh, ox:ox + ww] = img[ys][:, xs]
    return out


def tiles_for(name, c, m):
    d = D.DECALS[name]
    wall = d["projection"] == "wall"
    gc = D.Canvas(d["size"], d["px"], 7)
    base = 0.11 if wall else 0.012
    g = base * (1 + 0.25 * D.fbm(gc, 0.3, 5, 0.6) * 0.5 + 0.1 * D.fbm(gc, 0.01, 2))
    ground = np.repeat(np.clip(g, 0, 1)[..., None], 3, axis=-1)
    a = m["a"][..., None]
    comp = ground * (1 - a) + m["col"] * m["mask"][..., 1:2] * a
    T = 300
    t = [pngio.linear_to_srgb(_fit(comp, T)),
         np.repeat(_fit(m["a"], T)[..., None], 3, -1),
         _fit(m["nrm"], T),
         np.repeat(_fit(m["mask"][..., 3] * m["a"], T)[..., None], 3, -1)]
    return [x[::-1] for x in t]  # top row first for the sheet


def write_sheets(rows, per=6):
    os.makedirs(envpaths.PREVIEWS, exist_ok=True)
    T, g = 300, 4
    for s in range(0, len(rows), per):
        chunk = rows[s:s + per]
        S = np.full((len(chunk) * (T + g) + g, 4 * (T + g) + g, 3), 0.1, F32)
        for r_, tiles in enumerate(chunk):
            for k, t in enumerate(tiles):
                y, x = g + r_ * (T + g), g + k * (T + g)
                S[y:y + T, x:x + T] = t
        p = os.path.join(envpaths.PREVIEWS, f"decals_maps_{s // per + 1:02d}.png")
        pngio.write_png(p, pngio.to_u8(S))
        print("[decals] sheet", p)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    maps = "--maps" in argv
    pats = [a for a in argv if not a.startswith("--")]
    if "--list" in argv:
        for n, d in D.DECALS.items():
            print(f"{n:24s} {d['size']} {d['px']} {d['projection']}")
        return
    names = [n for n in D.DECALS if not pats or any(fnmatch.fnmatch(n, p) for p in pats)]
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    state = {k: v for k, v in state.items() if k in D.DECALS}
    rows = []
    for name in names:
        t0 = time.time()
        c, st = D.generate(name)
        m = finalize(c, st)
        files = save(name, m)
        state[name] = entry(name, files, c)
        size = sum(os.path.getsize(os.path.join(envpaths.UNITY_ENV, f)) for f in files.values())
        edge = max(m["a"][0].max(), m["a"][-1].max(), m["a"][:, 0].max(), m["a"][:, -1].max())
        print(f"[decals] {name:24s} {c.W}x{c.H} {time.time() - t0:5.1f}s  {size / 1e6:5.2f} MB  alpha mean "
              f"{m['a'].mean():.3f} border {edge:.3f}")
        if maps:
            rows.append(tiles_for(name, c, m))
        json.dump(state, open(STATE, "w"), indent=1)
    if maps:
        write_sheets(rows)
    total = 0
    for root, _, fs in os.walk(OUT):
        total += sum(os.path.getsize(os.path.join(root, f)) for f in fs if f.endswith(".png"))
    print(f"[decals] {len(state)} decals in state, Decals/ PNG total {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
