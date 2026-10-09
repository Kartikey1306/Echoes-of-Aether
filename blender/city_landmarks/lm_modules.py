"""Modular district pieces for ordinary (procedural) city blocks: roof sets, crowns and facade stacks.

Roof sets: pivot base-centre on the roof slab, footprint in the record (fits lots >= footprint + 1 m).
Facade pieces: pivot 'wall-base' = centre of the bottom edge ON the wall plane; they project toward Blender -Y
(Unity +Z); designed on the city's storey grid (ground 4.4 m, storeys 3.4 m) - place the base at y = 4.4 + k * 3.4.
"""
import math
import random

import lmkit as L
from lmkit import K, Mesh, fbox, box
import lmparts as P
import lmshapes as SH
import styles as ST


def _meta(fw, fd, h, colliders="none"):
    return {"colliders": colliders, "footprint": [fw, fd], "height": round(h, 2)}


# ============================================================================================== roof sets
def roof_ks_shanties(w=9.0, d=9.0, seed=1):
    """Shanty town roof: 3-4 shacks, water tanks, antenna forest, dishes, laundry, a small mast."""
    rng = random.Random(seed)
    P.roof_clutter(-w / 2, -d / 2, w / 2, d / 2, 0.0, rng, "kowloon", density=1.6)
    if L.lod() == 0:
        for k in range(3):
            y = rng.uniform(-d / 2, d / 2)
            K.tube([(-w / 2, y, 2.4), (0, y, 2.0), (w / 2, y, 2.4)], 0.01, 4, "rope")
    return _meta(w, d, 9.0)


def roof_nm_pagoda(w=8.0, d=8.0, seed=2):
    """Rooftop pavilion: lacquer columns, red lantern string, pagoda roof with neon eaves, two tanks."""
    rng = random.Random(seed)
    for (x, y) in ((-w / 2 + 1, -d / 2 + 1), (w / 2 - 1, -d / 2 + 1), (w / 2 - 1, d / 2 - 1), (-w / 2 + 1, d / 2 - 1)):
        K.cyl(0.18, 3.0, 10 if L.lod() == 0 else 6, at=(x, y, 0.0), mat="lacquer_red")
    box(-w / 2 + 1.5, w / 2 - 1.5, -d / 2 + 1.5, d / 2 - 1.5, 0.0, 2.8, "lm_plaster_pastel")
    if L.lod() < 2:
        m = Mesh("win_warm_living", "pav")
        m.wall(L.Frame(-1.2, -d / 2 + 1.49, 1, 0, 2.4), 0.0, 2.4, 0.4, 2.3, 0.0, rng.choice(L.WIN_WARM))
    SH.pagoda_roof(0, 0, 3.0, w / 2 - 0.8, d / 2 - 0.8, rise=2.4, eave=1.2, lift=0.7, steps=5, neon=rng.choice(["emit_neon_cyan", "emit_neon_magenta"]),
                   ridge=0.3)
    P.water_tank(w / 2 - 1.0, d / 2 + 0.2, 0.0, r=0.8, h=1.6, legs=0.6)
    return _meta(w + 2.4, d + 2.4, 8.0)


def roof_nm_signframe(w=12.0, d=3.0, seed=3):
    """Rooftop neon sign frame: steel scaffold carrying a glyph row and two lightbox boards (front -Y)."""
    rng = random.Random(seed)
    F = L.Frame(-w / 2, -d / 2, 1, 0, w)
    for u in (0.0, w / 2, w):
        p = F.p(u, 0)
        K.beam((p.x, p.y + 0.3, 0.0), (p.x, p.y + 0.3, 6.0), 0.14, mat="metal_dark")
        K.beam((p.x, p.y + 2.2, 0.0), (p.x, p.y + 0.3, 4.0), 0.1, mat="metal_dark")
    K.beam((-w / 2, -d / 2 + 0.3, 1.0), (w / 2, -d / 2 + 0.3, 1.0), 0.12, mat="metal_dark")
    P.neon_glyphs(F, 0.4, 3.4, 2.2, int((w - 0.8) / 2.2), 0.0, rng.choice(L.NEONS), rng, r=0.06)
    m = Mesh("screen_ad_a", "rsf")
    fbox(F, 0.4, w - 0.4, 1.3, 3.2, 0.0, 0.2, "metal_dark")
    m.wall(F, 0.5, w - 0.5, 1.4, 3.1, 0.205, rng.choice(L.ADS))
    if L.lod() > 0:
        m.wall(F, 0.4, w - 0.4, 3.4, 5.6, 0.0, "emit_panel_magenta")
    return _meta(w, d, 6.2)


def roof_ag_crown(w=14.0, d=14.0, seed=4, h=7.2):
    """Corporate crown: two-storey glass setback box with office panes, LED cornice rings, roof mast + beacon."""
    rng = random.Random(seed)
    fl = L.Floors(seed, base=0.5, office=True)
    st = P.style(ST.CORP, bay=2.0, ground="none")
    M = Mesh(st.wall, "crown")
    fr = L.rect_frames(-w / 2, -d / 2, w / 2, d / 2)
    for k, F in fr.items():
        P.facade(M, F, st, [(0.0, 0.001), (0.001, 3.6), (3.601, 3.6)], fl, (seed, k), street=False, ground="none", z_from=0.001)
    M.cap([(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)], h, "concrete_dark")
    for zz in (h - 0.2, 0.1):
        box(-w / 2 - 0.15, w / 2 + 0.15, -d / 2 - 0.15, d / 2 + 0.15, zz, zz + 0.16, "emit_strip_cyan" if zz > 1 else "metal_dark")
    K.cyl(0.25, 14.0, 6, at=(w / 4, d / 4, h), r2=0.05, mat="titanium")
    K.cyl(0.14, 0.25, 6, at=(w / 4, d / 4, h + 14.0), mat="beacon_red")
    return _meta(w + 0.4, d + 0.4, h + 14.3)


def roof_ag_spire(w=10.0, d=10.0, seed=5):
    """Pyramidal LED crown: four sloped fins converging on a spire, holo ring."""
    for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        K.beam((sx * w / 2, sy * d / 2, 0.0), (sx * 0.6, sy * 0.6, 12.0), 0.35, mat="lm_cladding_dark")
        if L.lod() == 0:
            K.beam((sx * (w / 2 + 0.2), sy * (d / 2 + 0.2), 0.2), (sx * 0.75, sy * 0.75, 12.0), 0.06, mat="emit_strip_violet")
    box(-w / 2, w / 2, -d / 2, d / 2, 0.0, 0.6, "lm_cladding_dark")
    SH.holo_ring(0, 0, 5.0, w * 0.32, h=0.8, mat="holo_magenta", n=32)
    K.cyl(0.3, 10.0, 6, at=(0, 0, 11.5), r2=0.05, mat="titanium")
    K.cyl(0.14, 0.25, 6, at=(0, 0, 21.5), mat="beacon_red")
    return _meta(w, d, 21.8)


def roof_cw_garden(w=9.0, d=8.0, seed=6):
    """Rooftop garden: planters with shrubs, pergola, laundry lines, water tank, string lights."""
    rng = random.Random(seed)
    for k in range(5):
        x, y = rng.uniform(-w / 2 + 1, w / 2 - 1), rng.uniform(-d / 2 + 1, d / 2 - 1)
        box(x - 0.6, x + 0.6, y - 0.4, y + 0.4, 0.0, 0.5, rng.choice(["wood", "terracotta", "stone_dark"]))
        K.lathe([(0.3, 0.0), (0.7, 0.25), (0.55, 0.75), (0.0, 1.1)], 7, at=(x, y, 0.5), mat=rng.choice(["foliage_dark", "foliage_mid"]))
    for x in (-w / 2 + 0.5, 0.0, w / 2 - 0.5):
        K.cyl(0.07, 2.5, 6, at=(x, -d / 2 + 0.5, 0.0), mat="wood")
        K.cyl(0.07, 2.5, 6, at=(x, d / 2 - 0.5, 0.0), mat="wood")
    for y in (-d / 2 + 0.5, d / 2 - 0.5):
        box(-w / 2 + 0.4, w / 2 - 0.4, y - 0.05, y + 0.05, 2.5, 2.6, "wood")
    if L.lod() == 0:
        for k in range(3):
            y = -d / 2 + 1.5 + k * 2.0
            K.tube([(-w / 2 + 0.5, y, 2.2), (0, y, 1.9), (w / 2 - 0.5, y, 2.2)], 0.01, 4, "rope")
            for j in range(rng.randint(3, 6)):
                x = rng.uniform(-w / 2 + 1, w / 2 - 1)
                box(x - 0.22, x + 0.22, y - 0.03, y + 0.03, 1.3, 1.95, rng.choice(["cloth_white", "cloth_red", "cloth_blue", "cloth_yellow", "cloth_pink"]))
        for k in range(10):
            x = -w / 2 + 0.5 + k * (w - 1) / 9
            K.cyl(0.06, 0.1, 6, at=(x, -d / 2 + 0.5, 2.4 - 0.25 * math.sin(math.pi * k / 9)), mat="lantern_warm")
    P.water_tank(w / 2 - 1.2, d / 2 - 1.2, 0.0, r=0.9, h=1.8, legs=1.0, mat="metal_rusted")
    return _meta(w, d, 4.6)


def roof_fr_vents(w=10.0, d=8.0, seed=7):
    """Industrial roof plant: extract fans, duct runs, a small flue stack with beacon, cable tray."""
    rng = random.Random(seed)
    for k in range(4):
        x, y = -w / 2 + 1.5 + k * (w - 3) / 3, rng.uniform(-d / 2 + 1.5, 0)
        K.cyl(0.7, 1.2, 12 if L.lod() == 0 else 6, at=(x, y, 0.0), mat="metal_bare")
        K.lathe([(0.75, 0.0), (0.5, 0.4), (0.0, 0.5)], 12 if L.lod() == 0 else 6, at=(x, y, 1.2), mat="metal_dark")
    SH.pipe_run([(-w / 2, d / 4, 0.8), (w / 2 - 2, d / 4, 0.8), (w / 2 - 2, d / 4, 3.0)], 0.4, "metal_painted")
    SH.smokestack(w / 2 - 1.5, d / 2 - 1.5, 0.0, 9.0, r0=0.6, r1=0.45, bands=("metal_painted_red",), ladder=False)
    box(-w / 2 + 0.5, w / 2 - 0.5, -d / 2 + 0.3, -d / 2 + 0.6, 0.0, 0.25, "metal_dark")
    return _meta(w, d, 9.5)


# ============================================================================================== facade pieces
def fac_ks_cagestack(w=3.0, floors=3, seed=11):
    """Three storeys of caged windows with AC units and laundry (Kowloon), on a 3 m bay."""
    rng = random.Random(seed)
    F = L.Frame(-w / 2, 0.0, 1, 0, w)
    for f in range(floors):
        z = f * 3.4
        P.cage(F, 0.3, w - 0.3, z + 0.75, z + 2.55, depth=rng.uniform(0.45, 0.7))
        if rng.random() < 0.6:
            P.ac_unit(F, w / 2 + rng.uniform(-0.6, 0.6), z + 0.05, 0.0)
        if rng.random() < 0.5:
            P.laundry(F, 0.4, w - 0.4, z + 2.45, 0.55, rng)
    return _meta(w, 1.4, floors * 3.4)


def fac_ks_cantilever(w=2.8, seed=12):
    """Two-storey enclosed box room hung off the wall: cladding, lit windows, tin roof, raker brackets, AC."""
    rng = random.Random(seed)
    fl = L.Floors(seed, base=0.6)
    F = L.Frame(-w / 2, 0.0, 1, 0, w)
    dep = 1.2
    clad = rng.choice(["lm_corrugated_painted", "metal_painted", "lm_mosaic_tile"])
    fbox(F, 0.0, w, 0.0, 6.6, 0.0, dep, clad)
    m = Mesh("glass_dark", "cw")
    for f in range(2):
        m.wall(F, 0.35, w - 0.35, f * 3.4 + 1.0, f * 3.4 + 2.2, dep + 0.005, fl.window(f, ("c", seed)))
        if L.lod() == 0:
            fbox(F, 0.3, w - 0.3, f * 3.4 + 0.95, f * 3.4 + 1.0, dep, dep + 0.07, "metal_dark")
    fbox(F, -0.05, w + 0.05, 6.6, 6.68, -0.02, dep + 0.15, "metal_rusted")
    if L.lod() < 2:
        for u in (0.15, w - 0.15):
            P.ftube(F, [(u, -1.2, 0.0), (u, 0.0, dep - 0.1)], 0.04, "metal_rusted", n=4)
        P.ac_unit(F, w / 2, 3.4 + 2.4, dep)
    return _meta(w, dep + 0.5, 6.7)


def fac_nm_signstack(w=4.0, seed=13):
    """Sign armature over three storeys: stacked lightbox boards, neon glyph rows, LED screens."""
    rng = random.Random(seed)
    F = L.Frame(-w / 2, 0.0, 1, 0, w)
    SH.sign_armature(F, 0.0, w, 0.2, 10.0, out=0.55, rng=rng)
    return _meta(w, 1.0, 10.2)


def fac_nm_blade(h=9.0, seed=14):
    """Vertical blade sign (stacked lightbox cells, both faces lit) on arms, projecting 1.6 m."""
    rng = random.Random(seed)
    F = L.Frame(-0.5, 0.0, 1, 0, 1.0)
    SH.blade_tower(F, 0.5, 0.0, h, out=1.4, rng=rng)
    return _meta(0.5, 1.9, h + 0.2)


def fac_cw_balconies(w=3.4, floors=3, seed=15):
    """Three stacked balconies (rail / parapet / enclosed mix) with lit doors, laundry and plants (Canal Ward).
    Nothing is drawn on the wall plane itself (no z-fighting with the host wall): doors are 2 cm proud."""
    rng = random.Random(seed)
    fl = L.Floors(seed, base=0.55, warm_bias=0.8)
    F = L.Frame(-w / 2, 0.0, 1, 0, w)
    for f in range(floors):
        z0 = f * 3.4
        br = random.Random(seed * 7 + f)
        dep = br.uniform(1.0, 1.35)
        P.fq(F, 0.6, w - 0.6, z0 + 0.12, z0 + 2.5, 0.02, fl.window(f + 1, ("door", seed, f)))
        if L.lod() == 0:
            P.fq(F, 0.55, w - 0.55, z0 + 2.5, z0 + 2.58, 0.025, "metal_dark")
        fbox(F, 0.05, w - 0.05, z0 - 0.08, z0 + 0.12, 0.0, dep, "concrete")
        kind = br.random()
        if kind < 0.45:
            fbox(F, 0.05, w - 0.05, z0 + 0.12, z0 + 1.0, dep - 0.08, dep, "lm_brick_soot")
            for s0 in (0.05, w - 0.13):
                fbox(F, s0, s0 + 0.08, z0 + 0.12, z0 + 1.0, 0.0, dep, "lm_brick_soot")
        elif kind < 0.78:
            if L.lod() == 0:
                n = int(w / 0.14)
                for k in range(n + 1):
                    uu = 0.1 + (w - 0.2) * k / n
                    P.fq(F, uu - 0.012, uu + 0.012, z0 + 0.12, z0 + 1.05, dep - 0.04, "metal_dark")
            fbox(F, 0.05, w - 0.05, z0 + 1.02, z0 + 1.07, dep - 0.08, dep - 0.02, "metal_dark")
        else:
            fbox(F, 0.05, w - 0.05, z0 + 0.12, z0 + 1.0, dep - 0.06, dep, "lm_corrugated_painted")
            P.fq(F, 0.08, w - 0.08, z0 + 1.0, z0 + 2.5, dep - 0.03, fl.window(f + 1, ("encl", seed, f)))
            fbox(F, 0.0, w, z0 + 2.5, z0 + 2.62, 0.0, dep + 0.05, "metal_rusted")
            for s0 in (0.05, w - 0.11):
                fbox(F, s0, s0 + 0.06, z0 + 0.12, z0 + 2.5, 0.0, dep, "metal_dark")
        if br.random() < 0.7:
            P.laundry(F, 0.3, w - 0.3, z0 + 2.3, dep - 0.2, br)
        if br.random() < 0.5:
            P.plant_pots(F, 0.3, w - 0.3, z0 + 0.12, dep - 0.45, br)
        if br.random() < 0.3 and L.lod() < 2:
            P.ac_unit(F, 0.7, z0 + 0.12, dep - 0.5)
    return _meta(w, 1.6, floors * 3.4)


def fac_fr_piperiser(w=3.0, floors=3, seed=16):
    """Pipe riser bundle with brackets and a service platform per two storeys (Foundry Row)."""
    rng = random.Random(seed)
    F = L.Frame(-w / 2, 0.0, 1, 0, w)
    H = floors * 3.4 + 2.0
    mats = ["metal_rusted", "paint_glossy_red", "metal_painted", "metal_painted_yellow"]
    for k in range(3):
        u = 0.5 + k * (w - 1.0) / 2
        r = rng.uniform(0.1, 0.22)
        P.ftube(F, [(u, 0.0, 0.3 + r), (u, H, 0.3 + r)], r, rng.choice(mats), n=8)
    for f in range(floors + 1):
        fbox(F, 0.0, w, f * 3.4 + 0.5, f * 3.4 + 0.6, 0.0, 0.7, "metal_dark")
    if L.lod() < 2:
        fbox(F, 0.0, w, 3.4 * 2 - 0.1, 3.4 * 2, 0.0, 1.2, "metal_dark")
        P.fq(F, 0.0, w, 3.4 * 2, 3.4 * 2 + 1.0, 1.2, "metal_painted_yellow")
    return _meta(w, 1.3, H)


def fac_ag_ledfin(h=20.0, seed=17):
    """Vertical LED fin (0.6 m) with a lit edge strip - corporate corners and piers."""
    F = L.Frame(-0.3, 0.0, 1, 0, 0.6)
    fbox(F, 0.0, 0.6, 0.0, h, 0.0, 0.9, "lm_cladding_dark")
    fbox(F, 0.2, 0.4, 0.3, h - 0.3, 0.9, 0.95, random.Random(seed).choice(["emit_strip_cyan", "emit_strip_violet", "emit_strip_magenta"]))
    return _meta(0.6, 1.0, h)


A = dict
ASSETS = {
    "LMM_Roof_KS_Shanties_A": A(fn=roof_ks_shanties, kw=dict(w=9.0, d=9.0, seed=21), cat="module", district="KowloonStacks",
                                notes="Kowloon roof set 9 x 9 m: shacks, tanks, antenna forest, dishes, laundry."),
    "LMM_Roof_KS_Shanties_B": A(fn=roof_ks_shanties, kw=dict(w=12.0, d=7.0, seed=22), cat="module", district="KowloonStacks",
                                notes="Kowloon roof set 12 x 7 m."),
    "LMM_Roof_NM_Pagoda": A(fn=roof_nm_pagoda, kw=dict(w=8.0, d=8.0, seed=23), cat="module", district="NeonMarket",
                            notes="Neon Market rooftop pagoda pavilion 8 x 8 m with neon eaves."),
    "LMM_Roof_NM_SignFrame": A(fn=roof_nm_signframe, kw=dict(w=12.0, d=3.0, seed=24), cat="module", district="NeonMarket",
                               notes="Neon Market rooftop sign scaffold 12 m: neon glyph row + LED board, front -Y (Unity +Z)."),
    "LMM_Roof_AG_Crown_A": A(fn=roof_ag_crown, kw=dict(w=14.0, d=14.0, seed=25), cat="module", district="ArcologyGate",
                             notes="Arcology crown 14 x 14 m: two glass storeys, LED cornice, mast."),
    "LMM_Roof_AG_Crown_B": A(fn=roof_ag_crown, kw=dict(w=10.0, d=10.0, seed=26), cat="module", district="ArcologyGate",
                             notes="Arcology crown 10 x 10 m."),
    "LMM_Roof_AG_Spire": A(fn=roof_ag_spire, kw=dict(w=10.0, d=10.0, seed=27), cat="module", district="ArcologyGate",
                           notes="Arcology pyramidal LED crown with holo ring and spire, 10 x 10 m."),
    "LMM_Roof_CW_Garden": A(fn=roof_cw_garden, kw=dict(w=9.0, d=8.0, seed=28), cat="module", district="CanalWard",
                            notes="Canal Ward rooftop garden 9 x 8 m: planters, pergola, laundry, tank, string lights."),
    "LMM_Roof_FR_Vents": A(fn=roof_fr_vents, kw=dict(w=10.0, d=8.0, seed=29), cat="module", district="FoundryRow",
                           notes="Foundry roof plant 10 x 8 m: extract fans, ducts, flue stack."),
    "LMM_Fac_KS_CageStack": A(fn=fac_ks_cagestack, kw=dict(w=3.0, floors=3, seed=31), cat="module", district="KowloonStacks", pivot="wall-base",
                              notes="Facade piece: 3 storeys of caged windows + AC + laundry, 3 m wide; wall plane at Unity z=0, projects +Z."),
    "LMM_Fac_KS_Cantilever": A(fn=fac_ks_cantilever, kw=dict(w=2.8, seed=32), cat="module", district="KowloonStacks", pivot="wall-base",
                               notes="Facade piece: two-storey cantilevered box room 2.8 m wide, projects 1.2 m."),
    "LMM_Fac_NM_SignStack": A(fn=fac_nm_signstack, kw=dict(w=4.0, seed=33), cat="module", district="NeonMarket", pivot="wall-base",
                              notes="Facade piece: sign armature 4 x 10 m with lightboxes, neon glyphs and LED boards."),
    "LMM_Fac_NM_Blade": A(fn=fac_nm_blade, kw=dict(h=9.0, seed=34), cat="module", district="NeonMarket", pivot="wall-base",
                          notes="Facade piece: 9 m vertical blade sign projecting 1.6 m."),
    "LMM_Fac_CW_Balconies": A(fn=fac_cw_balconies, kw=dict(w=3.4, floors=3, seed=35), cat="module", district="CanalWard", pivot="wall-base",
                              notes="Facade piece: three stacked balconies with laundry and plants, 3.4 m wide."),
    "LMM_Fac_FR_PipeRiser": A(fn=fac_fr_piperiser, kw=dict(w=3.0, floors=3, seed=36), cat="module", district="FoundryRow", pivot="wall-base",
                              notes="Facade piece: pipe riser bundle with brackets and a platform, 3 m wide."),
    "LMM_Fac_AG_LEDFin": A(fn=fac_ag_ledfin, kw=dict(h=20.0, seed=37), cat="module", district="ArcologyGate", pivot="wall-base",
                           notes="Facade piece: 20 m vertical LED fin for corporate corners."),
}
