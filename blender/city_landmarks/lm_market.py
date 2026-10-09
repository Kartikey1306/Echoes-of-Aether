"""Neon Market landmarks: Jade Lantern Tower (pagoda tower), Sign Canyon (sign-armature market block),
Night Market Hall (pagoda-roofed arcade hall). Front = Blender -Y."""
import math
import random

import lmkit as L
from lmkit import K, Mesh, fbox, box
import lmparts as P
import lmshapes as SH
import styles as ST


def jade_lantern_tower():
    """28 x 28 m lot: two-storey market podium with arcades and stalls, a 16 m square tower of seven tiers (two
    storeys each) skirted by pagoda roofs with neon eaves, red lantern strings, a crown pavilion and a mast (~78 m)."""
    meta = {"lights": []}
    rng = random.Random(101)
    fl = L.Floors(101, base=0.5, warm_bias=0.7)
    st = P.style(ST.MARKET, wall="lm_mosaic_tile", wall2="lm_plaster_pastel", ledge="lacquer_red", signs=0.5, balcony=0.0, cant=0.0)
    # podium 26 x 26, 2 storeys, shops on all faces
    pod_top = P.block(-13, -13, 13, 13, 8.8, st, fl, 1011, faces="sewn", street="sewn", roof=True, clutter=0.0, parapet_h=0.6, meta=meta,
                      floors=[(0.0, 4.6), (4.6, 4.2)])
    SH.pagoda_roof(0, 0, pod_top + 0.6, 13.2, 13.2, rise=1.6, eave=1.2, lift=0.6, steps=3, neon="emit_neon_magenta", ridge=8.6)
    # tower tiers
    tier_st = P.style(ST.MARKET_B, wall="lm_plaster_pastel", wall2="lm_mosaic_tile", ledge="lacquer_red", win="pair", win_w=1.6,
                      ac=0.3, cage=0.1, signs=0.0, laundry=0.15, plants=0.25, ground="none", parapet=0)
    z = pod_top + 2.2
    hw = 8.0
    neons = ["emit_neon_cyan", "emit_neon_magenta", "emit_neon_yellow", "emit_neon_pink", "emit_neon_cyan", "emit_neon_violet", "emit_neon_magenta"]
    for t in range(7):
        h = 6.8
        floors = [(z, 3.4), (z + 3.4, 3.4)]
        M = Mesh(tier_st.wall, "tier")
        fr = L.rect_frames(-hw, -hw, hw, hw)
        for k in "sewn":
            P.facade(M, fr[k], tier_st, [(z - 0.001, 0.001)] + floors, fl, (1012, t, k), street=False, ground="none", z_from=z)
            # lacquered corner columns
            if L.lod() < 2:
                F = fr[k]
                fbox(F, 0.0, 0.5, z, z + h, 0.0, 0.25, "lacquer_red")
        M.cap([(-hw, -hw), (hw, -hw), (hw, hw), (-hw, hw)], z + h, "concrete_dark")
        SH.pagoda_roof(0, 0, z + h, hw, hw, rise=2.4 if t < 6 else 5.5, eave=1.9 - 0.08 * t, lift=1.0, steps=5,
                       neon=neons[t], ridge=hw - 1.2 if t < 6 else 0.4)
        if L.lod() == 0:
            # lantern strings hanging from the eave corners
            for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                ex, ey = sx * (hw + 1.6), sy * (hw + 1.6)
                for k in range(3):
                    K.cyl(0.16, 0.36, 8, at=(ex, ey, z + h - 0.9 - k * 0.55), mat="lantern_red")
        meta["lights"].append(L.light(0, -(hw + 2.0), z + h - 0.4, neons[t], 14, 1.2, "eave neon"))
        z += h + 2.4
        hw -= 0.45
    top = z - 2.4 + 5.5
    # crown mast with beacon
    K.cyl(0.25, 14, 8, at=(0, 0, top + 1.0), r2=0.08, mat="brass")
    for k in range(5):
        K.torus(0.9 - k * 0.12, 0.05, n_major=16, n_minor=4, mat="brass").move(0, 0, top + 4 + k * 1.6)
    K.cyl(0.16, 0.3, 6, at=(0, 0, top + 15.0), mat="beacon_red")
    # giant vertical blade on the south-east corner of the podium / lower tiers
    Ffront = L.rect_frames(-13, -13, 13, 13)["s"]
    SH.blade_tower(Ffront, 24.5, 4.8, 16.0, out=1.5, rng=rng, signs=L.SIGNS[:6])
    SH.sign_armature(L.rect_frames(-13, -13, 13, 13)["e"], 6.0, 11.0, 4.9, 8.6, out=0.5, rng=rng)
    SH.sign_armature(L.rect_frames(-13, -13, 13, 13)["w"], 15.0, 20.0, 4.9, 8.6, out=0.5, rng=rng)
    meta["lights"].append(L.light(13.5, -15.0, 10.0, "#ff2bd6", 16, 1.4, "blade"))
    meta["colliders"] = [L.collider(0, 0, pod_top / 2, 26.0, 26.0, pod_top)]
    meta["roofHeight"] = round(top, 2)
    meta["height"] = round(top + 15.3, 2)
    meta["footprint"] = [28.0, 28.0]
    meta["beacons"] = [L.unity_pt(0, 0, top + 15.2)]
    return meta


def sign_canyon():
    """40 x 22 m market block, 7 storeys: front facade buried under stacked sign armatures and lightbox blades,
    arcade shops, corner blade towers, a 16 x 6 m rooftop LED billboard on a truss with a catwalk and a neon glyph frame."""
    meta = {"lights": []}
    rng = random.Random(102)
    fl = L.Floors(102, base=0.55, warm_bias=0.6)
    st = P.style(ST.MARKET, signs=0.6, cage=0.15, balcony=0.08, ac=0.45)
    top = P.block(-20, -11, 20, 11, 25.2, st, fl, 1021, faces="sewn", street="sew", meta=meta, roofkind="market", clutter=0.6,
                  ground_override="shops")
    fr = L.rect_frames(-20, -11, 20, 11)
    F = fr["s"]
    us = [(1.5, 6.5), (9.0, 13.5), (16.5, 22.0), (25.0, 30.0), (33.0, 38.5)]
    for i, (a, b) in enumerate(us):
        z0 = 5.0 + (i % 2) * 3.4
        SH.sign_armature(F, a, b, z0, min(top - 1.0, z0 + rng.choice((10.2, 13.6, 17.0))), out=0.55 + 0.3 * (i % 2), rng=rng)
    SH.blade_tower(F, 0.4, 4.6, 18.0, out=1.6, rng=rng)
    SH.blade_tower(F, 39.6, 4.6, 15.0, out=1.6, rng=rng)
    SH.sign_armature(fr["e"], 3.0, 9.0, 4.8, 18.0, out=0.6, rng=rng)
    SH.sign_armature(fr["w"], 12.0, 18.0, 4.8, 15.0, out=0.6, rng=rng)
    # rooftop billboard truss facing the street (-Y)
    bw, bh, lift = 16.0, 6.0, 3.0
    for x in (-bw / 2 + 0.6, 0.0, bw / 2 - 0.6):
        K.beam((x, -6.0, top), (x, -6.0, top + lift + bh), 0.25, mat="metal_dark")
        K.beam((x, -3.5, top), (x, -6.0, top + lift + bh * 0.6), 0.16, mat="metal_dark")
    box(-bw / 2 - 0.2, bw / 2 + 0.2, -6.3, -5.8, top + lift - 0.2, top + lift + bh + 0.2, "metal_dark")
    m = Mesh("screen_ad_b", "bb")
    Fb = L.Frame(-bw / 2, -6.32, 1, 0, bw)
    m.wall(Fb, 0.0, bw, top + lift, top + lift + bh, 0.0, rng.choice(L.ADS))
    if L.lod() < 2:
        box(-bw / 2, bw / 2, -7.4, -6.3, top + lift - 0.5, top + lift - 0.42, "metal_dark")
        box(-bw / 2 - 0.2, bw / 2 + 0.2, -6.36, -6.3, top + lift - 0.3, top + lift - 0.22, "emit_strip_magenta")
        box(-bw / 2 - 0.2, bw / 2 + 0.2, -6.36, -6.3, top + lift + bh + 0.22, top + lift + bh + 0.3, "emit_strip_cyan")
    # neon glyph frame on the back half of the roof (faces -Y as well, higher)
    Fg = L.Frame(-9.0, 4.0, 1, 0, 18.0)
    for x in (-9.0, 0.0, 9.0):
        K.beam((x, 4.3, top), (x, 4.3, top + 9.0), 0.14, mat="metal_dark")
    P.neon_glyphs(Fg, 0.3, top + 6.5, 2.2, 8, 0.0, "emit_neon_yellow", rng, r=0.06)
    if L.lod() > 0:
        m.wall(Fg, 0.3, 17.7, top + 6.5, top + 8.7, 0.0, "emit_panel_yellow")
    meta["lights"] += [L.light(0, -8.0, top + lift + 2, "#ff2bd6", 22, 2.0, "billboard"), L.light(0, -2.0, 12.0, "#00e5ff", 18, 1.4, "signs")]
    meta["screens"] = [{"center": L.unity_pt(0, -6.33, top + lift + bh / 2), "size": [bw, bh], "normal": [0, 0, 1]}]
    meta["colliders"] = [L.collider(0, 0, top / 2, 40.0, 22.0, top)]
    meta["roofHeight"] = round(top, 2)
    meta["height"] = round(top + lift + bh, 2)
    meta["footprint"] = [40.0, 22.0]
    return meta


def night_market_hall():
    """44 x 26 m hall: lacquer-red colonnade with stalls under it (recessed 3 m), clerestory of lightboxes, a huge
    hipped pagoda roof (eaves 13 m, ridge 22 m) with neon eaves, a paifang gate with neon in front of the entrance."""
    meta = {"lights": []}
    rng = random.Random(103)
    fl = L.Floors(103, base=0.7, warm_bias=0.85)
    W, D = 44.0, 26.0
    eave_z = 12.0
    # inner mass recessed 3 m on the front and the sides
    st = P.style(ST.MARKET, wall="lm_plaster_pastel", wall2="lm_mosaic_tile", ground="shops", signs=0.0, ac=0.1, cage=0.0, balcony=0.0)
    P.block(-W / 2 + 3, -D / 2 + 3, W / 2 - 3, D / 2, eave_z, st, fl, 1031, faces="sewn", street="sew", roof=False, clutter=0.0,
            floors=[(0.0, 5.0), (5.0, 3.5), (8.5, 3.5)], meta=meta)
    # colonnade + roof over the arcade
    cols = []
    for i in range(12):
        cols.append((-W / 2 + 1 + i * (W - 2) / 11, -D / 2 + 1))
    for j in range(1, 7):
        cols.append((-W / 2 + 1, -D / 2 + 1 + j * (D - 2) / 6.5))
        cols.append((W / 2 - 1, -D / 2 + 1 + j * (D - 2) / 6.5))
    for (x, y) in cols:
        K.cyl(0.38, 5.2, 12 if L.lod() == 0 else 6, at=(x, y, 0.0), mat="lacquer_red")
        if L.lod() < 2:
            box(x - 0.55, x + 0.55, y - 0.55, y + 0.55, 0.0, 0.35, "stone_dark")
            box(x - 0.6, x + 0.6, y - 0.6, y + 0.6, 5.2, 5.6, "brass" if L.lod() == 0 else "lacquer_red")
    # arcade ceiling + lintel beams
    box(-W / 2 + 0.5, W / 2 - 0.5, -D / 2 + 0.5, -D / 2 + 3.0, 5.6, 6.0, "lacquer_green")
    box(-W / 2 + 0.5, -W / 2 + 3.0, -D / 2 + 0.5, D / 2 - 0.5, 5.6, 6.0, "lacquer_green")
    box(W / 2 - 3.0, W / 2 - 0.5, -D / 2 + 0.5, D / 2 - 0.5, 5.6, 6.0, "lacquer_green")
    # second-level arcade roof (small pagoda skirt) + clerestory lightboxes
    SH.pagoda_roof(0, 0.25, 6.0, W / 2 - 0.5, 12.75, rise=1.0, eave=1.0, lift=0.5, steps=2, neon="emit_neon_yellow", ridge=(W / 2 - 2.1, 11.15))
    if L.lod() < 2:
        F = L.Frame(-W / 2 + 3, -D / 2 + 3, 1, 0, W - 6)
        n = 9
        for i in range(n):
            u = 1.0 + i * (W - 8) / (n - 1)
            m = Mesh("sign_00", "clere")
            m.wall(F, u - 1.0, u + 1.0, 8.9, 10.9, 0.05, L.SIGNS[i % len(L.SIGNS)] if i % 2 else rng.choice(L.ADS))
    # stalls under the arcade (front)
    if L.lod() < 2:
        for i in range(10):
            x = -W / 2 + 3.2 + i * 3.9
            y = -D / 2 + 1.8
            box(x - 1.4, x + 1.4, y - 0.6, y + 0.4, 0.0, 0.95, rng.choice(["wood", "metal_painted", "tile_grimy"]))
            if L.lod() == 0:
                for k in range(3):
                    box(x - 1.2 + k * 0.85, x - 0.6 + k * 0.85, y - 0.5, y + 0.2, 0.95, 0.95 + rng.uniform(0.1, 0.35),
                        rng.choice(["cloth_red", "cloth_yellow", "plastic_orange", "foliage_mid", "cloth_white"]))
                tarp = K.box(3.1, 1.6, 0.05, at=(x, y - 0.5, 2.6), mat=rng.choice(["tarp", "tarp_blue", "cloth_red", "cloth_yellow"]))
                tarp.rot(x=-12)
                for k in range(2):
                    K.cyl(0.03, 2.5, 4, at=(x - 1.4 + k * 2.8, y - 1.2, 0.0), mat="metal_dark")
                K.cyl(0.2, 0.45, 8, at=(x, y - 1.0, 3.3), mat="lantern_red")
    # main hipped pagoda roof
    SH.pagoda_roof(0, 1.5, eave_z, W / 2 - 3, D / 2 - 1.5, rise=8.0, eave=3.2, lift=1.6, steps=7, neon="emit_neon_magenta", ridge=(W / 2 - 3 - D / 2 + 1.5 + 1.0, 1.0))
    # paifang gate in front of the entrance
    gx, gy = 0.0, -D / 2 - 2.5
    for x in (-5.0, -1.6, 1.6, 5.0):
        hcol = 7.0 if abs(x) > 2 else 9.0
        K.cyl(0.3, hcol, 10 if L.lod() == 0 else 6, at=(gx + x, gy, 0.0), mat="lacquer_red")
        if L.lod() < 2:
            box(gx + x - 0.45, gx + x + 0.45, gy - 0.45, gy + 0.45, 0.0, 0.5, "stone_dark")
    for (x0, x1, zz) in ((-5.6, -1.0, 7.0), (1.0, 5.6, 7.0), (-2.2, 2.2, 9.0)):
        box(gx + x0, gx + x1, gy - 0.35, gy + 0.35, zz - 0.6, zz, "lacquer_green")
        SH.pagoda_roof(gx + (x0 + x1) / 2, gy, zz, (x1 - x0) / 2, 0.4, rise=0.8, eave=0.6, lift=0.35, steps=2, ridge=((x1 - x0) / 2 - 0.3, 0.08))
    m = Mesh("sign_00", "gate")
    Fg = L.Frame(gx - 1.3, gy - 0.36, 1, 0, 2.6)
    m.wall(Fg, 0.0, 2.6, 7.6, 8.3, 0.0, "emit_panel_yellow")
    P.neon_glyphs(Fg, 0.25, 7.62, 0.66, 3, 0.03, "emit_neon_magenta", rng, r=0.03)
    meta["lights"] += [L.light(0, -D / 2 - 3.5, 6.5, "#ff2bd6", 16, 1.5, "gate"), L.light(-12, -D / 2, 3.0, "#ff9a3a", 14, 1.2, "stalls"),
                       L.light(12, -D / 2, 3.0, "#ff9a3a", 14, 1.2, "stalls")]
    meta["colliders"] = [L.collider(0, 1.5, eave_z / 2, W - 6, D - 3, eave_z)] + \
                        [L.collider(x, y, 2.6, 0.8, 0.8, 5.2) for (x, y) in cols[::2]] + \
                        [L.collider(gx + x, gy, 3.5, 0.6, 0.6, 7.0) for x in (-5.0, 5.0)]
    meta["roofHeight"] = eave_z
    meta["height"] = round(eave_z + 8.0 + 2.6, 2)
    meta["footprint"] = [W + 0.0, D + 5.0]
    return meta


LANDMARKS = {
    "LM_NM_JadeLanternTower": dict(fn=jade_lantern_tower, district="NeonMarket",
                                   notes="Jade Lantern Tower: 7-tier pagoda tower on a 26 m market podium, neon eaves, lantern strings, crown mast (~94 m to the beacon)."),
    "LM_NM_SignCanyon": dict(fn=sign_canyon, district="NeonMarket",
                             notes="Sign Canyon: 7-storey market block buried in sign armatures, corner blade towers, 16 x 6 m rooftop billboard and neon glyph frame."),
    "LM_NM_NightMarketHall": dict(fn=night_market_hall, district="NeonMarket",
                                  notes="Night Market Hall: lacquer colonnade with stalls, clerestory lightboxes, huge hipped pagoda roof, paifang gate."),
}
