"""Landmark-kit tiling materials (plain Python 3 + numpy/scipy/PIL, fully procedural, no photos / AI images).

Each material is a tileable PBR set with built-in macro variation (stains, rain streaks, repairs, patches at several
scales over a 3-6 m repeat) so large facades don't show an obvious grid:
  lm_concrete_weathered  6.0 m  board-marked precast concrete, rain streaks, damp stains, efflorescence
  lm_mosaic_tile         3.0 m  Kowloon-style 45 mm mosaic tiles, repaired patches, missing tiles, grime runs
  lm_brick_soot          4.0 m  old running-bond brick, burnt headers, soot, efflorescence, concrete repairs
  lm_cladding_dark       4.8 m  arcology composite / anodised panels 1.2 x 0.6 m, fasteners, streaks
  lm_corrugated_painted  4.0 m  painted corrugated steel (76 mm pitch), lap lines with rust bleed, chalking
  lm_plaster_pastel      4.0 m  pastel painted render, peeling to grey render and brick, rain streaks
  lm_roof_tiles          2.0 m  glazed barrel roof tiles (pagoda roofs): U along the eave, V up the slope

Writes Assets/Art/CityLandmarks/Textures/<name>/<name>_{BaseColor,Normal,MaskMap}.png and out/kit_materials.json.
  python3 lmmats.py [names...]
"""
import json
import os
import sys
import time

import numpy as np

import lmpaths
import ptex as P

RES = 2048


def _fft_drip(src, length_px):
    """Smear sources DOWN the image (increasing row), exponential tail, wrap-around (tileable)."""
    n = src.shape[0]
    r = np.arange(n)
    w = np.exp(-r / max(length_px, 1.0) * 3.0)
    w[r > 3 * length_px] = 0
    w /= w.sum()
    k = np.zeros(n)
    k[:] = w
    F = np.fft.fft(src, axis=0) * np.fft.fft(k)[:, None]
    return np.real(np.fft.ifft(F, axis=0)).astype(np.float32)


def streaks(res, tile_m, seed, density=0.5, length_m=1.2, width_px=2.0):
    """Tileable vertical grime runs (0..1): soft-edged sources of 3-12 cm smeared down with a fading tail,
    broken up by vertically stretched noise."""
    rng = np.random.default_rng(seed)
    src = np.zeros((res, res), np.float32)
    n = int(density * tile_m * 14)
    px_m = tile_m / res
    for _ in range(n):
        x = rng.integers(res)
        y = rng.integers(res)
        wpx = max(2, int(rng.uniform(0.03, 0.12) / px_m * width_px / 4.0))
        xs = (x + np.arange(-wpx, wpx + 1)) % res
        prof = np.cos(np.linspace(-np.pi / 2, np.pi / 2, len(xs))) ** 2
        src[y, xs] += prof * rng.uniform(0.4, 1.0)
    src = P.blur(src, 1.5)
    run = _fft_drip(src, length_m / tile_m * res * rng.uniform(0.8, 1.2)) * res * 0.25
    jitter = P.fbm(res, res, 24, seed + 3, 4, 0.55, aspect=10.0)
    run = run * P.smooth(jitter, 0.25, 0.75)
    run = P.blur(run, 1.2)
    return np.clip(run, 0, 1) ** 0.8


def finish(name, res, tile_m, base_lin, height_m, rough, metal, ao_extra=None, normal_strength=1.0):
    px_m = tile_m / res
    n = P.normal_from_height(height_m, px_m, normal_strength)
    ao = P.ao_from_height(height_m, px_m, radius_m=tile_m / 120, strength=0.8)
    if ao_extra is not None:
        ao = ao * ao_extra
    hmin, hmax = float(height_m.min()), float(height_m.max())
    h01 = (height_m - hmin) / max(hmax - hmin, 1e-6)
    mask = np.stack([np.broadcast_to(metal, h01.shape), ao, h01, 1.0 - np.broadcast_to(rough, h01.shape)], -1).astype(np.float32)
    d = os.path.join(lmpaths.TEXTURES, name)
    os.makedirs(d, exist_ok=True)
    P.save_rgb(os.path.join(d, f"{name}_BaseColor.png"), lin_rgb=base_lin)
    P.save_rgb(os.path.join(d, f"{name}_Normal.png"), srgb=n)
    P.save_rgba(os.path.join(d, f"{name}_MaskMap.png"), mask)
    alb = P.linear_to_srgb(base_lin).reshape(-1, 3).mean(0)
    return {"kind": "baked", "shader": "Universal Render Pipeline/Lit", "surface": "Opaque", "uvMode": "world", "tileSizeMeters": tile_m,
            "tiling": [round(1 / tile_m, 6), round(1 / tile_m, 6)],
            "textures": {"BaseColor": f"Textures/{name}/{name}_BaseColor.png", "Normal": f"Textures/{name}/{name}_Normal.png",
                         "MaskMap": f"Textures/{name}/{name}_MaskMap.png", "Occlusion": f"Textures/{name}/{name}_MaskMap.png"},
            "heightDepthMeters": round(hmax - hmin, 4), "textureSize": res, "maxTextureSize": {"desktop": res, "webgl": min(1024, res)},
            "normalScale": 1.0, "occlusionStrength": 1.0,
            "stats": {"albedo_mean_srgb": [round(float(x), 3) for x in alb], "rough_mean": round(float(np.mean(rough)), 3),
                      "metal_mean": round(float(np.mean(metal)), 3)}}


# ============================================================================================== materials
def concrete_weathered(res=RES, tile=6.0):
    X, Y = P.grid(res, res)
    big = P.fbm(res, res, 3, 11, 4, 0.55)
    mid = P.fbm(res, res, 24, 12, 4, 0.55)
    fine = P.fbm(res, res, 220, 13, 3, 0.6)
    # board marks: horizontal planks 0.15 m (40 planks per 6 m), faint
    plank = (Y / res * tile / 0.15) % 1.0
    board = P.smooth(plank, 0.0, 0.05) * (1 - P.smooth(plank, 0.95, 1.0))
    pr = np.random.default_rng(14)
    plank_shift = pr.uniform(-1, 1, 40)[np.floor(Y / res * 40).astype(int) % 40] * 0.02
    pores = P.smooth(P.fbm(res, res, 300, 15, 2, 0.5), 0.72, 0.8)
    # form-tie holes on a 0.75 x 0.6 m grid (8 x 10 per tile)
    tx, ty = (X / res * 8) % 1.0, (Y / res * 10) % 1.0
    tie = 1 - P.smooth(np.hypot((tx - 0.5) * tile / 8, (ty - 0.5) * tile / 10), 0.012, 0.016)
    h = (big - 0.5) * 0.004 + (mid - 0.5) * 0.002 + (fine - 0.5) * 0.0012 + (1 - board) * -0.0006 + plank_shift * 0.01 - pores * 0.0008 - tie * 0.006
    base = P.hexlin("#8d8b86") * 0.92
    shade = 1.0 + (big - 0.5) * 0.35 + (mid - 0.5) * 0.18 + (fine - 0.5) * 0.12 - pores * 0.25 - tie * 0.5 + plank_shift * 2.0
    col = base[None, None, :] * shade[..., None]
    warm = P.fbm(res, res, 2, 16, 3, 0.5)
    col *= (1 + (warm[..., None] - 0.5) * np.array([0.12, 0.02, -0.1], np.float32))
    # damp stains (large, vertical-ish) and rain streaks
    stain = P.smooth(P.fbm(res, res, 3, 17, 5, 0.6, aspect=2.5), 0.55, 0.75)
    run = streaks(res, tile, 18, density=0.8, length_m=1.6, width_px=3)
    run2 = streaks(res, tile, 19, density=0.4, length_m=3.5, width_px=6) * 0.6
    tie_run = np.clip(_fft_drip(tie * 1.0, 0.5 / tile * res) * 30, 0, 1)
    dirt = np.clip(stain * 0.55 + run * 0.6 + run2 * 0.5 + tie_run * 0.6, 0, 1)
    col = P.lerp(col, col * np.array([0.42, 0.4, 0.38], np.float32), dirt)
    eff = P.smooth(P.fbm(res, res, 6, 20, 5, 0.6), 0.66, 0.86) * (1 - dirt)
    col = P.lerp(col, P.hexlin("#b9b7b0"), eff * 0.3)
    moss = P.smooth(P.fbm(res, res, 6, 21, 5, 0.6), 0.74, 0.82) * stain
    col = P.lerp(col, P.hexlin("#3d4a2c"), moss * 0.6)
    rough = 0.88 - run * 0.2 - stain * 0.12 + pores * 0.05
    return finish("lm_concrete_weathered", res, tile, col, h, rough, 0.0)


def mosaic_tile(res=RES, tile=3.0):
    n = 64  # tiles across the repeat -> 46.9 mm pitch
    X, Y = P.grid(res, res)
    cu, cv = X / res * n, Y / res * n
    iu, iv = np.floor(cu).astype(int) % n, np.floor(cv).astype(int) % n
    fu, fv = cu % 1.0, cv % 1.0
    pitch = tile / n
    gr = 0.0035 / pitch
    edge = np.minimum(np.minimum(fu, 1 - fu), np.minimum(fv, 1 - fv))
    tile_m = P.smooth(edge, gr * 0.5, gr * 0.5 + 0.06)
    rng = np.random.default_rng(31)
    rnd = rng.random((n, n)).astype(np.float32)
    rnd2 = rng.random((n, n)).astype(np.float32)
    r_t = rnd[iv, iu]
    r_t2 = rnd2[iv, iu]
    pal = np.array([P.hexlin(c) for c in ("#a9cfc3", "#9cc5b8", "#b4d6cb", "#a3c9be")], np.float32)
    col = pal[(r_t * 4).astype(int) % 4]
    col *= (0.92 + 0.16 * r_t2)[..., None]
    # repaired patches (other colour) from macro noise sampled per tile
    patch = P.fbm(res, res, 4, 32, 4, 0.55)
    pt = patch[(iv * res // n + res // (2 * n)) % res, (iu * res // n + res // (2 * n)) % res]
    rep = (pt > 0.68).astype(np.float32)
    col = P.lerp(col, P.hexlin("#d8d0b8") * (0.9 + 0.15 * r_t2)[..., None], rep)
    # missing tiles
    miss_n = P.fbm(res, res, 7, 33, 3, 0.6)
    mt = miss_n[(iv * res // n + 3) % res, (iu * res // n + 3) % res]
    missing = ((mt > 0.74) & (r_t > 0.55)).astype(np.float32)
    grout = P.hexlin("#8a877f")
    conc = P.hexlin("#6f6c66") * (0.85 + 0.3 * P.fbm(res, res, 80, 34, 3))[..., None]
    surf = P.lerp(grout[None, None, :] * np.ones_like(col), col, tile_m)
    surf = P.lerp(surf, conc, missing)
    bulge = np.sin(np.clip(fu, 0, 1) * np.pi) * np.sin(np.clip(fv, 0, 1) * np.pi)
    h = tile_m * (0.0015 + 0.0004 * bulge) * (1 - missing) - missing * 0.004 + (r_t - 0.5) * 0.0003 * tile_m
    # grime: soot runs, overall dirt gradient, dark grout lines get dirtier
    run = streaks(res, tile, 35, density=1.0, length_m=0.9, width_px=3)
    run2 = streaks(res, tile, 36, density=0.5, length_m=2.2, width_px=7) * 0.7
    grime = P.smooth(P.fbm(res, res, 2, 37, 4, 0.6, aspect=3.0), 0.45, 0.8)
    dirt = np.clip(run * 0.7 + run2 * 0.6 + grime * 0.45, 0, 1)
    surf = P.lerp(surf, surf * np.array([0.3, 0.29, 0.27], np.float32), dirt)
    surf = P.lerp(surf, surf * 0.55, (1 - tile_m) * 0.6)
    rough = np.where(tile_m > 0.5, 0.28, 0.85) + dirt * 0.35 + missing * 0.5
    return finish("lm_mosaic_tile", res, tile, surf, h, np.clip(rough, 0, 1), 0.0)


def brick_soot(res=RES, tile=4.0):
    courses, per = 54, 18
    X, Y = P.grid(res, res)
    cv = Y / res * courses
    row = np.floor(cv).astype(int) % courses
    fv = cv % 1.0
    cu = X / res * per + (row % 2) * 0.5
    col_i = np.floor(cu).astype(int) % per
    fu = cu % 1.0
    mort_v = 0.01 / (tile / courses)
    mort_u = 0.01 / (tile / per)
    eb = np.minimum(np.minimum(fu / mort_u * 0.5, (1 - fu) / mort_u * 0.5), np.minimum(fv / mort_v * 0.5, (1 - fv) / mort_v * 0.5))
    brick = P.smooth(eb, 0.5, 0.9)
    rng = np.random.default_rng(41)
    R1 = rng.random((courses, per)).astype(np.float32)
    R2 = rng.random((courses, per)).astype(np.float32)
    r1, r2 = R1[row, col_i], R2[row, col_i]
    pal = np.array([P.hexlin(c) for c in ("#7a3a2a", "#8a4430", "#6b3426", "#93533a", "#5a2c22", "#7f4a36")], np.float32)
    bc = pal[(r1 * len(pal)).astype(int) % len(pal)] * (0.85 + 0.3 * r2)[..., None]
    burnt = (r2 > 0.9).astype(np.float32)
    bc = P.lerp(bc, P.hexlin("#2e1c18"), burnt * 0.8)
    tex = P.fbm(res, res, 160, 42, 3, 0.6)
    bc *= (0.88 + 0.24 * tex)[..., None]
    mortar = P.hexlin("#7d776c") * (0.8 + 0.3 * P.fbm(res, res, 90, 43, 3))[..., None]
    col = P.lerp(mortar, bc, brick)
    # spalled faces, concrete repair patches
    spall = (R1[row, col_i] < 0.04).astype(np.float32) * P.smooth(P.fbm(res, res, 40, 44, 3), 0.4, 0.55)
    repair = P.smooth(P.fbm(res, res, 3, 45, 4, 0.55), 0.76, 0.78)
    h = brick * (0.006 + (tex - 0.5) * 0.0015) - spall * 0.004
    h = P.lerp(h, 0.004 + (P.fbm(res, res, 60, 46, 3) - 0.5) * 0.002, repair)
    col = P.lerp(col, P.hexlin("#77746d") * (0.9 + 0.2 * tex)[..., None], repair)
    col = P.lerp(col, col * 1.35, spall)
    soot = P.smooth(P.fbm(res, res, 2, 47, 5, 0.6, aspect=2.0), 0.35, 0.85)
    run = streaks(res, tile, 48, density=0.7, length_m=1.4, width_px=4)
    dirt = np.clip(soot * 0.7 + run * 0.6, 0, 1)
    col = P.lerp(col, col * np.array([0.32, 0.3, 0.3], np.float32), dirt)
    eff = P.smooth(P.fbm(res, res, 12, 49, 4, 0.6), 0.68, 0.8) * (1 - brick * 0.6) * (1 - soot)
    col = P.lerp(col, P.hexlin("#d2cec4"), eff * 0.7)
    rough = 0.9 - run * 0.15
    return finish("lm_brick_soot", res, tile, col, h, rough, 0.0)


def cladding_dark(res=RES, tile=4.8):
    nu, nv = 4, 8
    X, Y = P.grid(res, res)
    cu, cv = X / res * nu, Y / res * nv
    iu, iv = np.floor(cu).astype(int) % nu, np.floor(cv).astype(int) % nv
    fu, fv = cu % 1.0, cv % 1.0
    ju, jv = 0.008 / (tile / nu), 0.008 / (tile / nv)
    panel = P.smooth(np.minimum(np.minimum(fu, 1 - fu) / ju, np.minimum(fv, 1 - fv) / jv), 0.5, 1.2)
    rng = np.random.default_rng(51)
    R = rng.random((nv, nu)).astype(np.float32)
    R2 = rng.random((nv, nu)).astype(np.float32)
    r, r2 = R[iv, iu], R2[iv, iu]
    base = P.hexlin("#2b3036") * (0.9 + 0.2 * r)[..., None]
    brush = P.fbm(res, res, 600, 52, 2, 0.5, aspect=0.04)
    base *= (0.96 + 0.08 * brush)[..., None]
    # fasteners near panel corners
    fx = np.minimum(fu, 1 - fu) * tile / nu
    fy = np.minimum(fv, 1 - fv) * tile / nv
    fast = 1 - P.smooth(np.hypot(fx - 0.05, fy - 0.05), 0.006, 0.009)
    joint = 1 - panel
    run = streaks(res, tile, 53, density=0.4, length_m=1.0, width_px=2) * 0.8
    jrun = np.clip(_fft_drip((1 - P.smooth(np.minimum(fv, 1 - fv) / jv, 0.5, 1.2)) * (r2 > 0.5), 0.5 / tile * res) * 4, 0, 1) * 0.5
    dirt = np.clip(run + jrun, 0, 1)
    col = P.lerp(base, base * 0.45, dirt)
    col = P.lerp(col, P.hexlin("#0a0b0c"), joint)
    col = P.lerp(col, P.hexlin("#6b6e72"), fast * 0.8)
    h = panel * 0.004 + (r - 0.5) * 0.0004 * panel + fast * 0.002
    metal = np.clip(0.85 * panel - dirt * 0.3, 0, 1)
    rough = 0.38 + (r2 - 0.5) * 0.12 + dirt * 0.3 + joint * 0.4 + brush * 0.04
    return finish("lm_cladding_dark", res, tile, col, h, np.clip(rough, 0, 1), metal)


def corrugated_painted(res=RES, tile=4.0):
    n = 52
    X, Y = P.grid(res, res)
    phase = X / res * n * 2 * np.pi
    prof = np.sin(phase)
    h = prof * 0.009
    # sheet laps every 2 m (horizontal), fastener rows every 1 m with rust bleed
    lap = (Y / res * 2) % 1.0
    lapline = P.smooth(lap, 0.0, 0.004) * (1 - P.smooth(lap, 0.996, 1.0))
    h += (1 - lapline) * 0.003
    fy = (Y / res * 4) % 1.0
    frow = 1 - P.smooth(np.abs(fy - 0.5) * tile / 4, 0.004, 0.007)
    fcol = 1 - P.smooth(np.abs(((X / res * n) % 2.0) - 0.75), 0.06, 0.1)
    fast = frow * fcol
    h += fast * 0.003
    paint = P.hexlin("#55716e")
    fade = P.fbm(res, res, 3, 61, 4, 0.55)
    col = paint[None, None, :] * (0.85 + 0.3 * fade)[..., None]
    col *= (0.9 + 0.12 * (prof * 0.5 + 0.5))[..., None]   # chalky highlight on the crowns
    rust_src = np.clip(fast * 2 + (1 - lapline) * 0.6, 0, 1)
    rust_run = np.clip(_fft_drip(rust_src, 0.6 / tile * res) * 18, 0, 1) * (0.5 + 0.5 * P.fbm(res, res, 40, 62, 3, 0.5, aspect=8))
    patch = P.smooth(P.fbm(res, res, 6, 63, 5, 0.6), 0.66, 0.74)
    chip = P.smooth(P.fbm(res, res, 40, 64, 4, 0.6), 0.72, 0.76) * (prof > 0.3)
    rust = np.clip(rust_run * 0.8 + patch + chip, 0, 1)
    rcol = P.lerp(P.hexlin("#5a2a14"), P.hexlin("#8e4a1e"), P.fbm(res, res, 50, 65, 3))
    col = P.lerp(col, rcol, rust)
    grime = streaks(res, tile, 66, 0.6, 1.5, 4)
    col = P.lerp(col, col * 0.4, grime * 0.7)
    h -= patch * 0.0008
    metal = np.clip(0.15 * (1 - rust) + chip * 0.0, 0, 1)
    rough = 0.55 + rust * 0.35 + grime * 0.1
    return finish("lm_corrugated_painted", res, tile, col, h, rough, metal)


def plaster_pastel(res=RES, tile=4.0):
    X, Y = P.grid(res, res)
    big = P.fbm(res, res, 3, 71, 4, 0.55)
    fine = P.fbm(res, res, 200, 72, 3, 0.6)
    stip = P.fbm(res, res, 500, 73, 2, 0.5)
    paint = P.hexlin("#c89383")
    col = paint[None, None, :] * (0.88 + 0.22 * big + 0.06 * stip)[..., None]
    peel_n = P.fbm(res, res, 8, 74, 5, 0.6)
    peel = P.smooth(peel_n, 0.68, 0.7)
    deep = P.smooth(peel_n, 0.78, 0.8)
    render = P.hexlin("#8f8b83") * (0.85 + 0.3 * fine)[..., None]
    # brick under the deepest peel
    cv = Y / res * 54
    rowi = np.floor(cv).astype(int)
    cu = X / res * 18 + (rowi % 2) * 0.5
    mort = 1 - P.smooth(np.minimum(np.minimum(cu % 1, 1 - cu % 1) * 4.5, np.minimum(cv % 1, 1 - cv % 1) * 7.4), 0.05, 0.12)
    brick = P.lerp(P.hexlin("#7a3c2c"), P.hexlin("#6e6a62"), mort)
    col = P.lerp(col, render, peel)
    col = P.lerp(col, brick, deep)
    edge = np.clip(P.smooth(peel_n, 0.66, 0.68) - peel, 0, 1)
    col = P.lerp(col, col * 1.15, edge)
    h = (fine - 0.5) * 0.0012 + stip * 0.0004 + (1 - peel) * 0.0015 - deep * 0.004
    run = streaks(res, tile, 75, 0.9, 1.6, 4)
    run2 = streaks(res, tile, 76, 0.4, 3.0, 8) * 0.6
    damp = P.smooth(P.fbm(res, res, 3, 77, 5, 0.6, aspect=2.0), 0.55, 0.8)
    dirt = np.clip(run * 0.7 + run2 * 0.5 + damp * 0.5, 0, 1)
    col = P.lerp(col, col * np.array([0.38, 0.36, 0.35], np.float32), dirt)
    rough = 0.86 - dirt * 0.15
    return finish("lm_plaster_pastel", res, tile, col, h, rough, 0.0)


def roof_tiles(res=1024, tile=2.0):
    nu, nv = 10, 8   # 0.2 m barrels across, 0.25 m courses up the slope
    X, Y = P.grid(res, res)
    v_up = 1 - Y / res          # image row 0 = top = high V (up the slope)
    cu = X / res * nu
    cv = v_up * nv
    fu, fv = cu % 1.0, cv % 1.0
    iu = np.floor(cu).astype(int) % nu
    iv = np.floor(cv).astype(int) % nv
    barrel = np.sin(fu * np.pi)                          # semicircle-ish profile
    lapz = (1 - fv) * 0.012                              # each course thickens toward its lower edge
    h = barrel * 0.03 + lapz
    rng = np.random.default_rng(81)
    R = rng.random((nv, nu)).astype(np.float32)
    r = R[iv, iu]
    broken = (r > 0.985).astype(np.float32) * P.smooth(fv, 0.3, 0.32)
    h -= broken * 0.02
    glaze = P.hexlin("#1f4f49") * (0.85 + 0.25 * r)[..., None]
    col = glaze * (0.75 + 0.35 * barrel)[..., None]
    gutter = 1 - P.smooth(barrel, 0.05, 0.25)
    moss = P.smooth(P.fbm(res, res, 6, 82, 5, 0.6), 0.6, 0.75)
    grime = np.clip(gutter * 0.8 + moss * 0.6 + (1 - fv) ** 6 * 0.4, 0, 1)
    col = P.lerp(col, P.hexlin("#1a1c15"), grime * 0.7)
    col = P.lerp(col, P.hexlin("#46512e"), moss * gutter * 0.6)
    col = P.lerp(col, P.hexlin("#2a221e"), broken)
    rough = 0.25 + grime * 0.6 + broken * 0.5
    ao = 1 - gutter * 0.4 - (1 - fv) ** 8 * 0.4
    return finish("lm_roof_tiles", res, tile, col, h, rough, 0.0, ao_extra=ao)


MATS = {"lm_concrete_weathered": concrete_weathered, "lm_mosaic_tile": mosaic_tile, "lm_brick_soot": brick_soot,
        "lm_cladding_dark": cladding_dark, "lm_corrugated_painted": corrugated_painted, "lm_plaster_pastel": plaster_pastel,
        "lm_roof_tiles": roof_tiles}

# preview / modelling colours (linear) and registry info for the Blender side (lmkit registers them in matdefs)
INFO = {"lm_concrete_weathered": (6.0, "#7c7a75"), "lm_mosaic_tile": (3.0, "#9cbdb2"), "lm_brick_soot": (4.0, "#6a3a2c"),
        "lm_cladding_dark": (4.8, "#2b3036"), "lm_corrugated_painted": (4.0, "#55716e"), "lm_plaster_pastel": (4.0, "#c08a7b"),
        "lm_roof_tiles": (2.0, "#1f4f49")}


def main():
    names = [a for a in sys.argv[1:] if not a.startswith("-")] or list(MATS)
    p = os.path.join(lmpaths.OUT, "kit_materials.json")
    state = json.load(open(p)) if os.path.exists(p) else {}
    for n in names:
        t0 = time.time()
        state[n] = MATS[n]()
        json.dump(state, open(p, "w"), indent=1)
        print(f"[mat] {n} {time.time() - t0:.1f}s {state[n]['stats']}")


if __name__ == "__main__":
    main()
