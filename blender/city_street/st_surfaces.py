"""HD street surface materials (numpy, tileable): asphalt (two wear states), concrete pavers, poured slabs, kerb stone,
gutter strip and worn road paint (alpha cut-out).

  python3 st_surfaces.py [--res-scale 0.5] [--sheet] [names...]

Writes Assets/Art/CityStreet/Textures/<name>/<name>_{BaseColor,Normal,MaskMap[,Emission]}.png (MaskMap: R metallic,
G AO, B height, A smoothness; the manifest points _OcclusionMap at the MaskMap since URP samples .g) and merges
out/materials_baked.json. Design rules for no visible tiling: big tiles (6 m asphalt, 3.6 m pavers), no landmark
features inside a tile (puddles, patches, manholes and oil come from decals and geometry), low-contrast macro tone.
"""
import json
import math
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stpaths  # noqa: E402

sys.path.insert(1, stpaths.ENV)
sys.modules.setdefault("bpy", types.ModuleType("bpy"))
import numpy as np  # noqa: E402

import bakekit  # noqa: E402  (pure numpy helpers: height_to_normal, cavity_ao, save_set)
import pngio  # noqa: E402
import sttex as X  # noqa: E402
from sttex import F32, sst, lerp, mulc, lin, grey  # noqa: E402

MATS = {}
# Baked textures are near-dry: EOA/StreetSurface adds the rain (film, pore water, puddles) from _EOA_Wetness.
BAKE_WET = 0.25


def mat(name, tile, depth, res, uv="world", normal_strength=1.0, ao_strength=1.0, ao_radii=(0.004, 0.015, 0.05), unity=None, **kw):
    def deco(fn):
        MATS[name] = dict(fn=fn, tile=tile, depth=depth, res=res, uv=uv, normal_strength=normal_strength, ao_strength=ao_strength,
                          ao_radii=ao_radii, unity=unity or {}, **kw)
        return fn
    return deco


# ============================================================================================== asphalt
def _asphalt(t, worn):
    """Wet asphalt concrete: binder-coated aggregate (only worn stones show their colour), sparse coarse stones, air
    voids, hairline + structural cracks, a couple of sealed crack bands. Texture reads mostly through the normal and
    the smoothness (wet film); albedo stays low contrast so the 6 m repeat never shows."""
    rng = np.random.RandomState(31 + worn)
    d1, d2, ids = t.voronoi(0.0095, seed=11 + worn)
    edge = d2 - d1
    rid = t.cell_rand(ids, seed=12)
    rsz = t.cell_rand(ids, seed=13)
    size = 0.0018 + rsz * 0.0034
    dome = sst(edge, 0.0, size) * sst(rid, 0.08, 0.14)         # stones (some cells are binder pockets)
    cd1, cd2, cid = t.voronoi(0.045, seed=17 + worn)            # sparse coarse aggregate (12..20 mm)
    coarse = sst(cd2 - cd1, 0.0, 0.006 + t.cell_rand(cid, seed=18) * 0.006) * (t.cell_rand(cid, seed=19) > 0.55)
    stones = np.clip(dome + coarse, 0, 1)
    expo_n = t.noise(1.6, 4, 0.55)
    wear = np.clip(0.35 + expo_n * 0.12 + (0.25 if worn else 0.0), 0, 1)
    exposed = stones * sst(rid * 0.6 + wear * 0.8, 0.55, 0.85)  # binder worn off the stone tops
    fines = t.noise(0.004, 2, 0.6)
    voids = sst(t.white(), 0.982, 0.996) * (1 - stones)
    hair = X.crack_mask(t, rng, 3 if not worn else 6, 1.2, 0.0015, branch=0.8, jag_m=0.0015)
    big = X.crack_mask(t, rng, 1 if not worn else 2, 2.5, 0.006, branch=0.6, turn=0.35, jag_m=0.003)
    seal_paths = [X.wander(rng, (rng.rand(), rng.rand() * t.nv / t.n), 160, 0.012 / t.tile * 6, turn=0.06) for _ in range(1 if not worn else 2)]
    seal = X.periodic_line_mask(t, seal_paths, 0.028, soft_m=0.003)
    seal = t.warp(seal, 0.004, 0.03, 2) * sst(t.noise(0.6, 3), -1.6, -0.9)
    h = 0.42 + stones * 0.4 + exposed * 0.05 + fines * 0.025 - voids * 0.35 - hair * 0.3 - big * 0.55
    h = h * (1 - seal) + (0.66 + fines * 0.01) * seal
    # colour: dark oxidised binder, stones only lighter where exposed
    binder = grey(0.15 if not worn else 0.2)
    tone = 1 + t.noise(0.25, 3) * 0.04 + expo_n * 0.035 + fines * 0.03
    col = mulc(np.broadcast_to(binder, t.shape + (3,)).copy(), tone)
    sa, sb, sc = grey(0.36), lin("#5d5650"), lin("#474c51")
    stc = lerp(lerp(sa, sb, sst(t.cell_rand(ids, seed=14), 0.6, 0.85)), sc, sst(t.cell_rand(ids, seed=15), 0.65, 0.9))
    stc = mulc(stc, 0.7 + rid * 0.45)
    col = lerp(col, stc, exposed * 0.85)
    col = lerp(col, mulc(col, 0.85), stones * (1 - exposed) * 0.5)
    col = lerp(col, grey(0.05), np.clip(hair * 0.7 + big * 0.9, 0, 1))
    col = lerp(col, grey(0.04), seal * 0.9)
    oil = sst(t.noise(0.9, 4, 0.6), 1.5, 2.4)
    col = mulc(col, 1 - oil * 0.2)
    # wet film: the macro look of the surface (gentle, frequency high enough not to form landmarks)
    low = np.clip(0.5 - h, 0, 1) * 2.5
    film = np.clip(0.5 + t.noise(0.45, 4, 0.55) * 0.08 + t.noise(0.08, 3) * 0.05, 0.3, 0.7)
    wet = np.clip(film + low * 0.6, 0, 1) * BAKE_WET
    col = mulc(col, 1 - wet * 0.3)
    rough = 0.84 - exposed * 0.1 + voids * 0.05 + fines * 0.02
    rough = rough * (1 - wet) + (0.24 - film * 0.12) * wet
    rough = rough * (1 - seal) + 0.16 * seal - oil * 0.12
    ao = 1 - np.clip(voids * 0.6 + hair * 0.4 + big * 0.6, 0, 0.8)
    return dict(color=col, rough=np.clip(rough, 0.04, 1).astype(F32), metal=np.zeros_like(h), h01=np.clip(h, 0, 1).astype(F32), ao=ao)


@mat("st_asphalt", tile=6.0, depth=0.006, res=2048, normal_strength=1.2)
def asphalt(t):
    return _asphalt(t, 0)


@mat("st_asphalt_worn", tile=6.0, depth=0.007, res=2048, normal_strength=1.25)
def asphalt_worn(t):
    return _asphalt(t, 1)


# ============================================================================================== pavers
@mat("st_pavers", tile=3.6, depth=0.01, res=2048, normal_strength=1.0)
def pavers(t):
    """0.4 m square concrete pavers (9 x 9 per tile): fine-aggregate concrete faces with pores, worn chamfers, chipped
    corners, per-unit tone, dirt that collects toward the joints, sandy joints with moss, gum, a few settled units."""
    n = t.n
    rng = np.random.RandomState(47)
    N = 9
    gu, gv = t.u * N, t.v * N
    iu, iv = np.floor(gu).astype(np.int64), np.floor(gv).astype(np.int64)
    fu, fv = gu - iu, gv - iv
    cid = (iv % N) * N + (iu % N)
    r1, r2, r3, r4, r5 = (t.cell_rand(cid, seed=41 + k) for k in range(5))
    S = t.tile / N
    jit = t.noise(0.05, 3) * 0.0008
    de = np.minimum(np.minimum(fu, 1 - fu), np.minimum(fv, 1 - fv)) * S + jit
    joint_w, cham = 0.0035, 0.005
    face = sst(de, joint_w, joint_w + cham)
    arris = sst(de, joint_w, joint_w + cham) * sst(de, joint_w + cham + 0.004, joint_w + cham)   # the chamfer band
    # chipped corners: distance to the nearest unit corner
    cu, cv = np.minimum(fu, 1 - fu) * S, np.minimum(fv, 1 - fv) * S
    corner = np.sqrt(cu * cu + cv * cv)
    chip = sst(corner, 0.012 + r5 * 0.02, 0.004) * (r4 > 0.55) * sst(t.noise(0.01, 2), -1.0, 0.5)
    # concrete face: fine aggregate, pores, mottling at three scales
    d1, d2, aid = t.voronoi(0.0035, seed=48)
    agg = sst(d2 - d1, 0.0, 0.0012) * (t.cell_rand(aid, seed=49) > 0.6)
    pores = sst(t.white(), 0.993, 0.998)
    mott = t.noise(0.03, 3, 0.5) * 0.5 + t.noise(0.12, 3, 0.5) * 0.35 + t.noise(0.5, 3) * 0.25
    tilt = (r2 - 0.5) * 0.002 * ((fu - 0.5) * np.cos(r3 * 6.28) + (fv - 0.5) * np.sin(r3 * 6.28)) * 2
    sunk = (r1 > 0.975).astype(F32)
    cr = X.crack_mask(t, rng, 7, 0.35, 0.0012, branch=0.4, jag_m=0.001) * (r3 > 0.8)
    hm = face * (0.006 + tilt + (r4 - 0.5) * 0.001 - sunk * 0.002) + agg * 0.0004 + mott * 0.00025 - pores * 0.0009 \
        - cr * 0.002 - chip * 0.004
    h01 = np.clip(hm / 0.01 + 0.3, 0, 1)
    # colour
    warm, cool = lin("#7a756e"), lin("#6f7377")
    base = lerp(cool, warm, r2 * 0.3 + 0.35)
    col = mulc(base, 0.9 + (r1 - 0.5) * 0.16 + mott * 0.05 + agg * 0.12 - pores * 0.4)
    repl = (r2 > 0.965).astype(F32)
    col = lerp(col, mulc(col, 0.72), repl)
    effl = sst(t.noise(0.2, 3), 1.4, 2.2) * (r5 > 0.7)
    col = lerp(col, lin("#8e8c86"), effl * 0.18)
    col = lerp(col, mulc(col, 1.12), arris * 0.6)
    dirt = sst(de, joint_w + cham + 0.025, joint_w) * (0.4 + 0.4 * sst(t.noise(0.3, 3), -0.5, 1.0))
    col = lerp(col, lin("#2e2b26"), np.clip(dirt * 0.55, 0, 1))
    joint = 1 - face
    sand = mulc(lin("#3a362f"), 0.8 + t.white() * 0.3)
    col = lerp(col, sand, joint)
    moss = joint * sst(t.noise(0.5, 3), 0.8, 1.5)
    col = lerp(col, lin("#2c3520"), moss * 0.55)
    col = lerp(col, lin("#25221f"), chip * 0.7)
    gd1, _, gid = t.voronoi(0.32, seed=45)
    gsz = 0.005 + t.cell_rand(gid, seed=46) * 0.009
    gum = sst(gd1, gsz, gsz * 0.5) * (t.cell_rand(gid, seed=47) > 0.6)
    col = lerp(col, lin("#45423e"), gum * 0.8)
    stain = sst(t.noise(0.6, 4, 0.6), 1.2, 2.2)
    col = mulc(col, 1 - stain * 0.15)
    col = lerp(col, grey(0.07), cr * 0.75)
    traffic = np.clip(0.5 + t.noise(1.3, 3) * 0.2, 0, 1)
    col = mulc(col, 1 - traffic * 0.06)
    # wet: damp film, joints and settled units hold water
    film = np.clip(0.45 + t.noise(0.5, 4) * 0.08 + t.noise(0.06, 3) * 0.05, 0.25, 0.7)
    water = np.clip(joint * 0.95 + sunk * face * 0.4 + chip * 0.6 + gum * 0.2, 0, 1)
    wet = np.clip(film + water, 0, 1) * BAKE_WET
    col = mulc(col, 1 - wet * 0.3)
    rough = 0.8 + mott * 0.02 + pores * 0.1 - arris * 0.08
    rough = rough * (1 - wet) + (0.3 - film * 0.1) * wet
    rough = lerp(rough, 0.45, water * 0.6)
    ao = 1 - np.clip(joint * 0.5 + cr * 0.4 + dirt * 0.25 + chip * 0.3, 0, 0.8)
    return dict(color=col, rough=np.clip(rough, 0.04, 1).astype(F32), metal=np.zeros_like(h01), h01=h01.astype(F32), ao=ao)


# ============================================================================================== poured slabs
@mat("st_slab", tile=3.6, depth=0.006, res=1024, normal_strength=1.0)
def slab(t):
    """1.2 m poured concrete slabs with saw-cut joints, broom finish, stains, cracks across a few slabs."""
    n = t.n
    N = 3
    gu, gv = t.u * N, t.v * N
    iu, iv = np.floor(gu).astype(np.int64), np.floor(gv).astype(np.int64)
    fu, fv = gu - iu, gv - iv
    cid = (iv % N) * N + (iu % N)
    r1 = t.cell_rand(cid, seed=51)
    r2 = t.cell_rand(cid, seed=52)
    S = t.tile / N
    de = np.minimum(np.minimum(fu, 1 - fu), np.minimum(fv, 1 - fv)) * S
    joint = sst(de, 0.006, 0.0)
    # broom finish: fine streaks across the slab (direction alternates per slab)
    brA = t.noise(0.03, 3, 0.5, ax=0.06, ay=1.0)
    brB = t.noise(0.03, 3, 0.5, ax=1.0, ay=0.06)
    broom = np.where((iu + iv) % 2 == 0, brA, brB)
    agg = sst(t.white(), 0.96, 1.0)
    cr = X.cracks(t, 1.4, 0.0018, keep=0.25, warp_m=0.05) * (r2 > 0.6)
    h = 0.55 + broom * 0.05 + agg * 0.06 - joint * 0.5 - cr * 0.35
    col = mulc(np.broadcast_to(grey(0.5), (t.nv, t.n, 3)).copy(), 0.85 + r1 * 0.18 + t.noise(0.5, 4) * 0.05 + broom * 0.02)
    stain = sst(t.noise(0.8, 4, 0.6), 0.9, 2.0)
    col = lerp(col, mulc(col, 0.62), stain * 0.6)
    rust = sst(t.noise(0.25, 3), 1.8, 2.6)
    col = lerp(col, lin("#5e3a22"), rust * 0.35)
    col = lerp(col, grey(0.08), np.clip(joint * 0.8 + cr * 0.8, 0, 1))
    film = np.clip(0.45 + t.noise(0.7, 4) * 0.15, 0.1, 0.8)
    wet = np.clip(film + joint * 0.8, 0, 1) * BAKE_WET
    col = mulc(col, 1 - wet * 0.32)
    rough = (0.82 + agg * 0.08) * (1 - wet) + (0.3 - film * 0.1) * wet
    ao = 1 - np.clip(joint * 0.5 + cr * 0.4, 0, 0.8)
    return dict(color=col, rough=np.clip(rough, 0.04, 1).astype(F32), metal=np.zeros_like(h), h01=np.clip(h, 0, 1), ao=ao)


# ============================================================================================== kerb
@mat("st_curb", tile=2.0, depth=0.006, res=1024, normal_strength=1.1)
def curb(t):
    """Granite-like kerb stone: speckled, joints every 1 m along U, chips, tyre scuffs, faded yellow paint in places."""
    n = t.n
    agg = t.noise(0.006, 3, 0.6)
    spk = sst(t.white(), 0.9, 1.0)
    dark = sst(t.white(), 0.0, 0.07)
    jd = np.minimum(np.mod(t.u * 2, 1.0), 1 - np.mod(t.u * 2, 1.0)) * (t.tile / 2)
    joint = sst(jd, 0.004, 0.0)
    chips = sst(t.noise(0.04, 3), 1.6, 2.4)
    h = 0.6 + agg * 0.04 - joint * 0.6 - chips * 0.4
    col = mulc(np.broadcast_to(grey(0.48), (t.nv, t.n, 3)).copy(), 0.9 + agg * 0.05 + spk * 0.25 - dark * 0.45 + t.noise(0.6, 3) * 0.05)
    paint = sst(t.noise(1.2, 3), 1.0, 1.4) * sst(t.noise(0.05, 4, 0.6), -0.9, -0.2) * (1 - chips)
    col = lerp(col, lin("#b88a1e"), paint * 0.55)
    scuff = sst(t.noise(0.3, 4, 0.5, ax=3.0, ay=0.4), 1.0, 2.0)
    col = lerp(col, grey(0.05), scuff * 0.5)
    grime = sst(t.v, 0.4, 0.0) * 0.4 + sst(t.noise(0.3, 4), 0.5, 1.8) * 0.4
    col = mulc(col, 1 - grime * 0.45)
    col = lerp(col, grey(0.06), joint * 0.7)
    wet = np.clip(0.55 + t.noise(0.5, 3) * 0.15, 0, 1) * BAKE_WET
    col = mulc(col, 1 - wet * 0.3)
    rough = (0.7 - spk * 0.1 + chips * 0.15) * (1 - wet) + 0.25 * wet
    ao = 1 - np.clip(joint * 0.5 + chips * 0.4, 0, 0.8)
    return dict(color=col, rough=np.clip(rough, 0.04, 1).astype(F32), metal=np.zeros_like(h), h01=np.clip(h, 0, 1), ao=ao)


# ============================================================================================== gutter strip
@mat("st_gutter", tile=8.0, depth=0.006, res=2048, uv="strip", normal_strength=1.2, aspect=0.078)
def gutter(t):
    """Gutter band along the kerb (U = metres along, 8 m tile; V = 0 road side .. 1 kerb side): darker asphalt with
    grit and sand drifts, litter flecks, a water film that deepens toward the kerb and shallow puddles."""
    base = _asphalt(t, 1)
    col, rough, h = base["color"], base["rough"], base["h01"]
    v = t.vn
    near = sst(v, 0.25, 0.95)                              # toward the kerb
    grit = sst(t.noise(0.35, 4, 0.6, ax=5.0, ay=1.0) * 0.7 + t.noise(0.02, 2) * 0.3 + near * 1.3, 0.9, 1.9)
    sand = lin("#5a5246")
    col = lerp(col, mulc(np.broadcast_to(sand, (t.nv, t.n, 3)), 0.6 + t.white() * 0.5), grit * 0.45)
    fleck = sst(t.white(), 0.997, 1.0) * near
    col = lerp(col, lin("#c9c2b0"), fleck * 0.7)
    leaves = sst(t.noise(0.06, 3), 1.9, 2.4) * near
    col = lerp(col, lin("#3b2a18"), leaves * 0.7)
    h = h + grit * 0.08 + leaves * 0.06
    # standing water: continuous film at the kerb, puddles that reach out along the strip
    pud = sst(t.noise(1.1, 4, 0.55, ax=3.0, ay=1.0) + near * 1.8 - 0.4, 0.6, 1.0)
    pud = np.clip(pud + sst(v, 0.88, 0.97), 0, 1)
    col = lerp(col, mulc(col, 0.55), pud)
    rough = lerp(rough, 0.25, pud)
    h = lerp(h, 0.3, pud * 0.9)          # low: the shader fills it with water when the street is wet
    return dict(color=col, rough=np.clip(rough, 0.03, 1).astype(F32), metal=np.zeros_like(h), h01=np.clip(h, 0, 1),
                ao=base["ao"] * (1 - grit * 0.15))


# ============================================================================================== road paint
def _paint(t, colour, worn):
    """Thermoplastic road paint following the asphalt texture underneath, with worn-through gaps (alpha cut-out)."""
    under = _asphalt(t, 0)
    wear = t.noise(0.35, 5, 0.6) * 0.8 + t.noise(0.04, 3) * 0.35
    alpha = sst(wear, -1.2 + worn, -0.9 + worn)                # holes where the paint wore away
    beads = sst(t.white(), 0.97, 1.0)                           # glass beads: tiny bright sparkles
    dirt = sst(t.noise(0.5, 4), 0.2, 1.8)
    col = mulc(np.broadcast_to(colour, (t.nv, t.n, 3)).copy(), 0.82 + t.noise(0.05, 3) * 0.05 - dirt * 0.35)
    col = lerp(col, mulc(under["color"], 1.4), sst(under["h01"], 0.5, 0.35) * 0.35)   # aggregate shows through thin paint
    col = mulc(col, 1 + beads * 0.25)
    h = np.clip(under["h01"] * 0.6 + 0.35, 0, 1)
    rough = np.clip(0.45 - beads * 0.2 - 0.15 * np.clip(0.5 + t.noise(0.7, 3) * 0.2, 0, 1) + dirt * 0.1, 0.05, 1)
    return dict(color=col, rough=rough.astype(F32), metal=np.zeros_like(h), h01=h.astype(F32), ao=under["ao"], alpha=alpha)


@mat("st_paint_white", tile=2.0, depth=0.004, res=1024, unity={"alphaClip": 0.5})
def paint_white(t):
    return _paint(t, grey(0.74), 0.0)


@mat("st_paint_yellow", tile=2.0, depth=0.004, res=1024, unity={"alphaClip": 0.5})
def paint_yellow(t):
    return _paint(t, lin("#d6a21e"), 0.2)


# ============================================================================================== bake / write
def build(name, res_scale=1.0):
    d = MATS[name]
    t0 = time.time()
    res = int(d["res"] * res_scale)
    aspect = d.get("aspect", 1.0)
    t = X.Tex(res, d["tile"], seed=sum(map(ord, name)) * 131, nv=max(64, int(round(res * aspect / 32)) * 32) if aspect != 1.0 else None)
    r = d["fn"](t)
    hm = r["h01"] * d["depth"]
    nrm = bakekit.height_to_normal(hm.astype(np.float64), t.px, d["normal_strength"]).astype(F32)
    ao = X.cavity_ao(t, hm.astype(F32), d["ao_radii"], d["ao_strength"]) * r.get("ao", 1.0)
    ao = np.clip(ao, 0, 1).astype(F32)
    color = np.clip(r["color"], 0, 1)
    mask = np.stack([np.clip(r["metal"], 0, 1), ao, np.clip(r["h01"], 0, 1), 1 - np.clip(r["rough"], 0, 1)], -1)
    out_dir = os.path.join(stpaths.TEXTURES, name)
    alpha = r.get("alpha")
    files = bakekit.save_set(out_dir, name, color=color, normal=nrm, mask=mask, alpha=alpha)
    tex = {k: f"Textures/{name}/{v}" for k, v in files.items()}
    tex["Occlusion"] = tex["MaskMap"]                      # URP samples .g of the occlusion map
    info = {"name": name, "textures": tex, "res": res,
            "stats": {"albedo_mean_srgb": [round(float(x), 3) for x in pngio.linear_to_srgb(color.reshape(-1, 3).mean(0))],
                      "smooth_mean": round(float(mask[..., 3].mean()), 3)}}
    print(f"[surf] {name:18s} {res}px {time.time() - t0:5.1f}s albedo~{info['stats']['albedo_mean_srgb']} smooth~{info['stats']['smooth_mean']}")
    return info, (color, nrm, mask, alpha)


def sheet(results, path):
    """Inspection sheet: per material a 2x2 tiled albedo (shows the repeat), normal, smoothness."""
    T = 384
    rows = []
    for name, (color, nrm, mask, alpha) in results:
        def fit(a, rep=1):
            a = np.concatenate([np.concatenate([a] * rep, 1)] * rep, 0)
            idx = (np.arange(T) * a.shape[0] / T).astype(int)
            idy = (np.arange(T) * a.shape[1] / T).astype(int)
            return a[idx][:, idy]
        c2 = pngio.linear_to_srgb(fit(color, 2))
        if alpha is not None:
            c2 = c2 * fit(alpha, 2)[..., None] + 0.1 * (1 - fit(alpha, 2)[..., None])
        tiles = [pngio.linear_to_srgb(fit(color)), c2, fit(nrm), np.repeat(fit(mask[..., 3])[..., None], 3, -1)]
        rows.append(np.concatenate([x[::-1] for x in tiles], 1))
    S = np.concatenate(rows, 0)
    pngio.write_png(path, pngio.to_u8(S))
    print("[surf] sheet", path)


def main():
    argv = sys.argv[1:]
    scale = 1.0
    if "--res-scale" in argv:
        i = argv.index("--res-scale")
        scale = float(argv[i + 1])
        del argv[i:i + 2]
    want_sheet = "--sheet" in argv
    names = [a for a in argv if not a.startswith("--")] or list(MATS)
    state_path = os.path.join(stpaths.OUT, "materials_baked.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    res = []
    for n in names:
        info, maps = build(n, scale)
        state[n] = info
        res.append((n, maps))
        json.dump(state, open(state_path, "w"), indent=1)
    if want_sheet:
        sheet(res, os.path.join(stpaths.PREVIEWS, "surfaces_sheet.png"))


if __name__ == "__main__" and "--macro" not in sys.argv:
    main()


# ============================================================================================== macro variation maps
def macro(name, tile, res=512, basins=1.0, seed=7):
    """Runtime macro map for EOA/StreetSurface (Resources/CityStreet/<name>.png, sampled at world XZ / tile):
    R tone (0.5 neutral), G grime (> 0.5 adds grime), B puddle basins (0..1), A anti-tiling blend noise.
    Values are pre-encoded so the default sRGB import decodes back to the intended linear numbers."""
    t = X.Tex(res, tile, seed=seed)
    r = 0.5 + t.noise(9.0, 4, 0.5) * 0.07 + t.noise(2.0, 3) * 0.03
    g = 0.5 + 0.5 * sst(t.noise(6.0, 4, 0.55) + t.noise(1.5, 3) * 0.3, 0.4, 1.8)
    bn = t.noise(3.5, 4, 0.5) * 0.8 + t.noise(1.0, 3) * 0.25
    b = sst(bn, 0.2, 2.1) * basins
    a = np.clip(0.5 + t.noise(7.0, 3, 0.5) * 0.3, 0, 1)
    rgba = np.stack([np.clip(r, 0, 1), np.clip(g, 0, 1), np.clip(b, 0, 1), a], -1)
    enc = pngio.linear_to_srgb(rgba)
    path = os.path.join(stpaths.RUNTIME, f"{name}.png")
    pngio.write_png(path, pngio.to_u8(enc[::-1]))
    print(f"[surf] macro {name} {res}px / {tile} m  basin>0.8: {float((b > 0.8).mean()):.3f}")


if __name__ == "__main__" and "--macro" in sys.argv:
    macro("st_macro_road", 48.0, basins=1.0, seed=7)
    macro("st_macro_walk", 40.0, basins=0.85, seed=19)
