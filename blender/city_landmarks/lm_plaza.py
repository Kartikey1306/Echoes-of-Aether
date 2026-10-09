"""Bespoke buildings for the 23 Central Plaza blocks (PlazaZone.BuildBlocks): exact mass footprint and roof height of
each block so PzKit.Building can swap its box + facade modules for one prefab (mass collider kept by PzKit).
West / market side = Neon Market style, east column and north-east row = Arcology Gate corporate style.
Pivot = base centre of the mass. Faces: Blender -Y = prototype +z ('s'), +X = prototype +x ('e')."""
import random

import lmkit as L
import lmparts as P
import styles as ST

# PlazaZone.BuildBlocks (x, z, w, d, h) - keep in sync (OpenCity.PlazaBlocks mirrors it too)
BLOCKS = [
    (-58, -60, 24, 22, 26), (-34, -60, 20, 22, 18), (-20, -62, 12, 18, 12), (20, -62, 12, 18, 14), (34, -60, 20, 22, 22), (58, -60, 24, 22, 30),
    (-60, -32, 22, 18, 20), (-62, -10, 22, 22, 15), (-60, 14, 22, 22, 24), (-62, 36, 22, 18, 17),
    (66, -34, 20, 20, 28), (66, -8, 20, 24, 18), (66, 18, 20, 22, 24), (66, 40, 20, 18, 16),
    (-30, 52, 24, 16, 16), (30, 52, 24, 16, 20), (-30, 66, 24, 10, 12), (30, 66, 24, 10, 14),
    (-44, 82, 26, 22, 14), (-44, 104, 26, 20, 18), (44, 80, 26, 20, 16), (44, 102, 26, 22, 22), (0, 126, 64, 22, 20),
]
# outer faces that OpenCity.PlazaFace dresses onto the avenues / ring street / alleys (index -> faces)
AVENUE = {9: "s", 13: "s", 18: "n", 20: "n", 22: "s", 14: "w", 16: "w", 15: "e", 17: "e", 6: "n", 10: "n"}


def plaza_faces(x, z):
    f = ""

    def add(c):
        nonlocal f
        if c not in f:
            f += c
    if z < -40:
        add("s")
    if x < -40 and -45 < z < 60:
        add("e")
    if x > 40 and -45 < z < 60:
        add("w")
    if 40 < z < 75 and x < 0:
        add("e")
    if 40 < z < 75 and x > 0:
        add("w")
    if z >= 75 and x < -20:
        add("e")
    if z >= 75 and x > 20:
        add("w")
    if z > 115:
        add("n")
    return f or "s"


def style_for(i, x, z):
    corp = (x > 40 and z < 60) or (x > 0 and z < -40)
    if corp:
        return ("corp", P.style(ST.CORP if i % 2 else ST.CORP_B, bay=2.4 if i % 2 else 3.0, G=5.0, H=3.6,
                                led_seam="emit_strip_cyan" if i % 3 else "emit_strip_violet", fin=0.3))
    base = ST.MARKET if i % 2 == 0 else ST.MARKET_B
    return ("market", P.style(base, signs=0.45, cables=0.9))


def plaza_block(i):
    x, z, w, d, h = BLOCKS[i]
    kind, st = style_for(i, x, z)
    faces = plaza_faces(x, z)
    street = faces + "".join(c for c in AVENUE.get(i, "") if c not in faces)
    fl = L.Floors(9000 + i, base=0.42 if kind == "market" else 0.45, warm_bias=0.65 if kind == "market" else 0.3, office=kind == "corp")
    meta = {"lights": []}
    flat = "".join(c for c in "sewn" if c not in street)
    if kind == "corp":
        # corporate blocks: curtain wall on the plaza faces, cladding with punched ribbon windows elsewhere
        side = P.style(st, win="ribbon", win_w=2.0, win_h=1.6, win_sill=1.0, ground="service", led_seam=None)
        M = P.Mesh(st.wall, "walls")
        fr = L.rect_frames(-w / 2, -d / 2, w / 2, d / 2)
        floors = P.floor_list(h, st.G, st.H, st.parapet)
        for k in "sewn":
            s_ = st if k in street else side
            P.facade(M, fr[k], s_, floors, fl, (9000 + i, k), street=k in street, meta=meta)
            P.parapet(fr[k], h, st.parapet, st.wall, st.coping)
        M.cap([(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)], h, st.roof)
        if L.lod() < 2:
            P.roof_clutter(-w / 2 + 0.6, -d / 2 + 0.6, w / 2 - 0.6, d / 2 - 0.6, h, random.Random(i), "corp", density=0.5)
            # crown: LED-lit plant screen on the roof
            sw, sd = min(w - 4, 10.0), min(d - 4, 8.0)
            P.box(-sw / 2, sw / 2, -sd / 2, sd / 2, h, h + 3.2, "lm_cladding_dark")
            P.box(-sw / 2 - 0.05, sw / 2 + 0.05, -sd / 2 - 0.05, sd / 2 + 0.05, h + 3.0, h + 3.12, "emit_strip_cyan")
    else:
        P.block(-w / 2, -d / 2, w / 2, d / 2, h, st, fl, 9000 + i, faces="sewn", street=street, flat_sides=flat,
                roofkind="market", clutter=0.7, meta=meta)
    meta["colliders"] = [L.collider(0, 0, h / 2, w, d, h)]
    meta["massFootprint"] = [w, d]
    meta["roofHeight"] = h
    meta["plazaBlock"] = {"index": i, "x": x, "z": z, "faces": faces, "street": street, "style": kind}
    return meta


ASSETS = {f"Plaza_Block_{i:02d}": dict(fn=plaza_block, kw={"i": i}, cat="plaza",
                                       notes=f"Bespoke plaza block {i}: mass {BLOCKS[i][2]} x {BLOCKS[i][3]} m, roof {BLOCKS[i][4]} m "
                                             f"({style_for(i, BLOCKS[i][0], BLOCKS[i][1])[0]} style); PzKit.Building uses it instead of box + facade modules.")
          for i in range(len(BLOCKS))}
