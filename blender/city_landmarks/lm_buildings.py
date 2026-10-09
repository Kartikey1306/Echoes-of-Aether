"""District complete buildings for ordinary kit lots (CityLayout.KitModels): street front = Blender -Y (Unity +Z),
side faces flat (neighbouring lots, 0.8 m margins), back face plain. Pivot = base centre of the mass; massFootprint
and roofHeight in the record."""
import random

import lmkit as L
from lmkit import K
import lmparts as P
import lmshapes as SH
import styles as ST


def _kit(w, d, h, st, seed, roofkind, extra=None, back_plain=True, clutter=1.0, ground=None):
    meta = {"lights": []}
    fl = L.Floors(seed, base=st.lit or 0.42, warm_bias=st.warm or 0.5)
    top = P.block(-w / 2, -d / 2, w / 2, d / 2, h, st, fl, seed, faces="sewn", street="s", flat_sides="ew" + ("n" if back_plain else ""),
                  roofkind=roofkind, clutter=clutter, meta=meta, ground_override=ground)
    if extra:
        extra(w, d, top, meta, random.Random(seed))
    meta["colliders"] = [L.collider(0, 0, top / 2, w, d, top)]
    meta["massFootprint"] = [w, d]
    meta["roofHeight"] = round(top, 2)
    return meta


def _pagoda_cap(w, d, top, meta, rng):
    P.box(-w / 2 + 2.5, w / 2 - 2.5, -d / 2 + 2.5, d / 2 - 2.5, top, top + 3.0, "lm_plaster_pastel")
    SH.pagoda_roof(0, 0, top + 3.0, w / 2 - 2.5, d / 2 - 2.5, rise=3.0, eave=1.4, lift=0.8, steps=5, neon="emit_neon_cyan",
                   ridge=(max(0.3, w / 2 - d / 2 + 0.4), 0.4))


def _front_signs(w, d, top, meta, rng):
    F = L.rect_frames(-w / 2, -d / 2, w / 2, d / 2)["s"]
    SH.sign_armature(F, w * 0.15, w * 0.15 + 4.0, 4.8, min(top - 1.0, 4.8 + 10.2), out=0.55, rng=rng)
    SH.blade_tower(F, w - 0.4, 4.6, min(top - 6.0, 12.0), out=1.4, rng=rng)


def _roof_signframe(w, d, top, meta, rng):
    Fg = L.Frame(-w / 2 + 1.0, -d / 2 + 1.5, 1, 0, w - 2.0)
    for u in (0.0, (w - 2.0) / 2, w - 2.0):
        p = Fg.p(u, 0)
        K.beam((p.x, p.y + 0.3, top), (p.x, p.y + 0.3, top + 4.5), 0.12, mat="metal_dark")
    P.neon_glyphs(Fg, 0.3, top + 2.4, 1.9, int((w - 2.6) / 1.9), 0.0, rng.choice(L.NEONS), rng, r=0.05)
    if L.lod() > 0:
        L.Mesh("emit_panel_magenta", "rs").wall(Fg, 0.3, w - 2.3, top + 2.4, top + 4.3, 0.0, "emit_panel_magenta")


def _corp_crown(w, d, top, meta, rng):
    P.box(-w / 2 + 2, w / 2 - 2, -d / 2 + 2, d / 2 - 2, top, top + 4.0, "lm_cladding_dark")
    P.box(-w / 2 + 1.9, w / 2 - 1.9, -d / 2 + 1.9, d / 2 - 1.9, top + 3.8, top + 3.95, "emit_strip_cyan")
    K.cyl(0.3, 12.0, 6, at=(w / 4, d / 4, top + 4.0), r2=0.06, mat="titanium")
    K.cyl(0.15, 0.25, 6, at=(w / 4, d / 4, top + 16.0), mat="beacon_red")


def _kowloon_mast(w, d, top, meta, rng):
    SH.lattice_mast(-w / 4, d / 5, top, 12.0, base=0.9, top=0.2, beacons=2, dishes=2, rng=rng)


def _sawtooth(w, d, top, meta, rng):
    SH.sawtooth_roof(-w / 2, -d / 2, w / 2, d / 2, top, 3, rise=2.6)


def _chimney(w, d, top, meta, rng):
    SH.smokestack(w / 2 - 2.0, d / 2 - 2.0, top, 16.0, r0=0.9, r1=0.7, mat="lm_brick_soot", bands=("concrete",), ladder=False)


A = dict
ASSETS = {
    # Neon Market
    "LB_NM_Shophouse_A": A(fn=_kit, kw=dict(w=12, d=12, h=21.4, st=P.style(ST.MARKET, signs=0.5), seed=7101, roofkind="market", extra=_front_signs),
                           cat="building", district="NeonMarket", notes="Neon Market shophouse, 6 storeys, sign armature + corner blade, stalls."),
    "LB_NM_Shophouse_B": A(fn=_kit, kw=dict(w=16, d=12, h=24.8, st=P.style(ST.MARKET_B, signs=0.4, wall2="lm_plaster_pastel"), seed=7102, roofkind="market", extra=_pagoda_cap),
                           cat="building", district="NeonMarket", notes="Neon Market mosaic shophouse, 7 storeys, pagoda roof pavilion with neon eaves."),
    "LB_NM_Arcade_C": A(fn=_kit, kw=dict(w=20, d=14, h=14.6, st=P.style(ST.MARKET, ground="arcade", signs=0.3), seed=7103, roofkind="market",
                                          extra=_roof_signframe), cat="building", district="NeonMarket",
                        notes="Neon Market arcade block, 4 storeys over a colonnade, rooftop neon glyph frame."),
    # Kowloon Stacks
    "LB_KS_Tenement_A": A(fn=_kit, kw=dict(w=12, d=12, h=42.4, st=ST.STACK, seed=7201, roofkind="kowloon", clutter=1.4, back_plain=False),
                          cat="building", district="KowloonStacks", notes="Kowloon tenement, 13 storeys, cages, cantilevered rooms, shanty roof."),
    "LB_KS_Tenement_B": A(fn=_kit, kw=dict(w=16, d=12, h=52.0, st=ST.STACK_B, seed=7202, roofkind="kowloon", clutter=1.4, extra=_kowloon_mast,
                                            back_plain=False), cat="building", district="KowloonStacks",
                          notes="Kowloon tenement, 16 storeys, lattice mast on a shanty roof."),
    "LB_KS_Slab_C": A(fn=_kit, kw=dict(w=20, d=12, h=36.0, st=P.style(ST.STACK, wall="lm_concrete_weathered", wall2="lm_mosaic_tile"), seed=7203,
                                        roofkind="kowloon", clutter=1.2, back_plain=False), cat="building", district="KowloonStacks",
                      notes="Kowloon slab block, 11 storeys of caged flats, AC clusters, laundry."),
    # Arcology Gate
    "LB_AG_Office_A": A(fn=_kit, kw=dict(w=20, d=16, h=45.0, st=ST.CORP, seed=7301, roofkind="corp", clutter=0.4, extra=_corp_crown),
                        cat="building", district="ArcologyGate", notes="Corporate curtain-wall office, 12 storeys, lobby, LED seams, crown."),
    "LB_AG_Office_B": A(fn=_kit, kw=dict(w=16, d=16, h=66.6, st=ST.CORP_B, seed=7302, roofkind="corp", clutter=0.4, extra=_corp_crown),
                        cat="building", district="ArcologyGate", notes="Corporate tower, 18 storeys, metal-panel spandrels, violet LED seams."),
    # Canal Ward
    "LB_CW_House_A": A(fn=_kit, kw=dict(w=12, d=12, h=21.2, st=ST.CANAL, seed=7401, roofkind="canal"), cat="building", district="CanalWard",
                       notes="Canal Ward brick house, 6 storeys, balconies with laundry, retrofit cables."),
    "LB_CW_House_B": A(fn=_kit, kw=dict(w=16, d=12, h=24.6, st=ST.CANAL_B, seed=7402, roofkind="canal"), cat="building", district="CanalWard",
                       notes="Canal Ward pastel render house, 7 storeys, balconies, plants."),
    "LB_CW_Warehouse_C": A(fn=_kit, kw=dict(w=20, d=14, h=16.2, st=P.style(ST.CANAL, win="industrial", bay=4.0, ground="shops"), seed=7403,
                                             roofkind="canal", extra=_chimney), cat="building", district="CanalWard",
                           notes="Canal Ward brick warehouse conversion, 4 storeys of factory glazing, chimney."),
    # Foundry Row
    "LB_FR_Shed_A": A(fn=_kit, kw=dict(w=20, d=14, h=10.2, st=ST.FOUNDRY, seed=7501, roofkind="foundry", extra=_sawtooth, clutter=0.0),
                      cat="building", district="FoundryRow", notes="Foundry shed, corrugated, roller doors, sawtooth north-light roof."),
    "LB_FR_Works_B": A(fn=_kit, kw=dict(w=16, d=16, h=18.6, st=ST.FOUNDRY_B, seed=7502, roofkind="foundry", extra=_chimney),
                       cat="building", district="FoundryRow", notes="Foundry brick works, 4 storeys of steel factory windows, chimney."),
}
