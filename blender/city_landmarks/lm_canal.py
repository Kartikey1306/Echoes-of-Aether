"""Canal Ward landmarks: Waterfront Row (canal houses with balconies, laundry and cyber retrofits over a pier
arcade), Clock Pump House (brick pump hall with a 48 m clock tower), Stilt Tower (residential tower on piers)."""
import math
import random

from mathutils import Vector

import lmkit as L
from lmkit import K, Mesh, fbox, box
import lmparts as P
import lmshapes as SH
import styles as ST


def waterfront_row():
    """40 x 18 m: five narrow canal houses (6-8 storeys, brick / pastel render alternating) on a pier arcade facing
    the canal (front -Y), stacked balconies with laundry lines strung between houses, retrofit cable trays, LED
    strips, AC and satellite dishes, gabled and flat roofs."""
    meta = {"lights": []}
    rng = random.Random(401)
    fl = L.Floors(401, base=0.5, warm_bias=0.8)
    xs = [-20.0, -11.5, -4.0, 4.5, 12.0, 20.0]
    hs = [24.6, 28.0, 21.2, 31.4, 24.6]
    tops = []
    for i in range(5):
        st = ST.CANAL if i % 2 == 0 else ST.CANAL_B
        st = P.style(st, balcony=0.45, laundry=0.6, plants=0.4)
        x0, x1 = xs[i], xs[i + 1]
        zf = {}
        faces = "sn"
        if i == 0:
            faces += "w"
        if i == 4:
            faces += "e"
        if i > 0 and hs[i - 1] < hs[i]:
            faces += "w"
            zf["w"] = hs[i - 1]
        if i < 4 and hs[i + 1] < hs[i]:
            faces += "e"
            zf["e"] = hs[i + 1]
        top = P.block(x0, -7, x1, 7, hs[i], st, fl, 4010 + i, faces=faces, street="s", z_from=zf, roofkind="canal", clutter=1.0, meta=meta,
                      ground_override="arcade")
        tops.append(top)
        if i % 2 == 1 and L.lod() < 2:
            # gabled roof
            gw = (x1 - x0) / 2
            m = Mesh("metal_rusted", "gable")
            for s in (-1, 1):
                a = Vector((x0, s * 7.3, top))
                b = Vector((x1, s * 7.3, top))
                c = Vector((x1, 0.0, top + 3.0))
                d = Vector((x0, 0.0, top + 3.0))
                if s > 0:
                    m.quad(b, a, d, c, "lm_corrugated_painted", ((0, 0), (x1 - x0, 0), (x1 - x0, 7.9), (0, 7.9)))
                else:
                    m.quad(a, b, c, d, "lm_corrugated_painted", ((0, 0), (x1 - x0, 0), (x1 - x0, 7.9), (0, 7.9)))
            for xx, s in ((x0, -1), (x1, 1)):
                bm = m.bm
                vs = [bm.verts.new((xx, -7.0, top)), bm.verts.new((xx, 7.0, top)), bm.verts.new((xx, 0.0, top + 3.0))]
                if s < 0:
                    vs.reverse()
                f = bm.faces.new(vs)
                f[m.part.mats] = m.part.slot(st.wall)
                f[m.part.uvm] = K.UVM_KEEP
                for l in f.loops:
                    l[m.part.uvl].uv = (l.vert.co.y, l.vert.co.z)
    F = L.rect_frames(-20, -7, 20, 7)["s"]
    if L.lod() < 2:
        # retrofit cable tray + LED strip along the front at every other floor line
        for z in (7.6, 14.4, 21.2):
            fbox(F, 0.0, 40.0, z + 0.05, z + 0.22, 0.12, 0.4, "metal_painted")
            if L.lod() == 0:
                fbox(F, 0.0, 40.0, z + 0.22, z + 0.25, 0.38, 0.41, L.STRIPS[int(z) % 3])
        # laundry lines strung across between balconies
        if L.lod() == 0:
            for i in range(10):
                z = rng.uniform(6, 22)
                u0 = rng.uniform(0, 30)
                P.laundry(F, u0, u0 + rng.uniform(2.5, 6.0), z, 0.3, rng)
    meta["lights"] += [L.light(0, -9, 3.5, "#ffb070", 18, 1.4, "arcade"), L.light(-12, -9, 9, "#00e5ff", 12, 0.8, "led")]
    meta["colliders"] = [L.collider(0, 0, max(hs) / 2, 40, 14, max(hs))]
    meta["roofHeight"] = round(min(tops), 2)
    meta["height"] = round(max(tops) + 6, 2)
    meta["footprint"] = [40.0, 14.0]
    return meta


def clock_pump_house():
    """30 x 20 m Victorian pump house (brick, tall arched factory windows, corrugated pitched roof with a lantern
    ridge) and a 48 m brick clock tower on its front corner: four lit clock faces with tick marks (no text), a
    copper cupola, retrofitted antenna array and a holo halo."""
    meta = {"lights": []}
    rng = random.Random(402)
    fl = L.Floors(402, base=0.6, warm_bias=0.9)
    st = P.style(ST.FOUNDRY_B, wall="lm_brick_soot", trim="concrete", sill="concrete", G=6.0, H=6.0, bay=4.2, win="industrial", ground="industrial",
                 parapet=0.0, ledge="concrete", ledge_proj=0.18)
    top = P.block(-15, -6, 15, 14, 12.0, st, fl, 4020, faces="sewn", street="sewn", roof=False, clutter=0.0, floors=[(0.0, 6.0), (6.0, 6.0)])
    # pitched roof along X + ridge lantern
    m = Mesh("lm_corrugated_painted", "roof")
    for s in (-1, 1):
        y0, y1 = (-6.6, 4.0) if s < 0 else (14.6, 4.0)
        a, b = Vector((-15.4, y0, 11.8)), Vector((15.4, y0, 11.8))
        c, d = Vector((15.4, y1, 17.5)), Vector((-15.4, y1, 17.5))
        if s < 0:
            m.quad(a, b, c, d, "lm_corrugated_painted")
        else:
            m.quad(b, a, d, c, "lm_corrugated_painted")
    for xx, s in ((-15.0, -1), (15.0, 1)):
        bm = m.bm
        vs = [bm.verts.new((xx, -6.0, 12.0)), bm.verts.new((xx, 14.0, 12.0)), bm.verts.new((xx, 4.0, 17.2))]
        if s < 0:
            vs.reverse()
        f = bm.faces.new(vs)
        f[m.part.mats] = m.part.slot("lm_brick_soot")
        f[m.part.uvm] = K.UVM_KEEP
        for l in f.loops:
            l[m.part.uvl].uv = (l.vert.co.y, l.vert.co.z)
    box(-12, 12, 2.6, 5.4, 17.2, 18.8, "metal_dark")
    if L.lod() < 2:
        mm = Mesh("glass_dark", "lantern")
        for (F, k) in ((L.Frame(-12, 2.59, 1, 0, 24), "a"), (L.Frame(12, 5.41, -1, 0, 24), "b")):
            for i in range(8):
                mm.wall(F, 0.3 + i * 3.0, 2.7 + i * 3.0, 17.4, 18.5, 0.0, "win_fluoro_kitchen" if i % 3 else "window_lit_warm")
    # clock tower 9 x 9 at the front-left corner, 48 m
    tx0, ty0, tx1, ty1 = -19.0, -10.0, -10.0, -1.0
    tst = P.style(st, win="punched", win_w=1.0, win_h=2.6, win_sill=1.0, bay=3.0, ground="service", ledge_every=2)
    floors = [(0.0, 6.0)] + [(6.0 + i * 5.0, 5.0) for i in range(6)]
    ttop = P.block(tx0, ty0, tx1, ty1, 36.0, tst, fl, 4021, faces="sewn", street="sw", roof=False, clutter=0.0, floors=floors)
    # clock stage
    box(tx0 - 0.4, tx1 + 0.4, ty0 - 0.4, ty1 + 0.4, ttop, ttop + 0.6, "concrete")
    cz = ttop + 0.6
    box(tx0, tx1, ty0, ty1, cz, cz + 7.0, "lm_brick_soot")
    cx, cy = (tx0 + tx1) / 2, (ty0 + ty1) / 2
    for k, F in L.rect_frames(tx0, ty0, tx1, ty1).items():
        u = F.length / 2
        p = F.p(u, cz + 3.5, 0.05)
        # clock face disc (emissive) + ring + hands + 12 ticks
        disc = K.cyl(3.1, 0.12, 40 if L.lod() == 0 else 16, at=(0, 0, 0), mat="lantern_warm", axis="Y")
        disc.move(0, -0.06, 0)
        disc.xform(F.matrix() @ __import__("mathutils").Matrix.Translation((u, 0, cz + 3.5)))
        if L.lod() < 2:
            ring = K.torus(3.2, 0.14, n_major=40 if L.lod() == 0 else 16, n_minor=4, mat="copper_patina")
            ring.rot(x=90).move(u, -0.15, cz + 3.5)
            ring.xform(F.matrix())
            for t in range(12):
                a = math.tau * t / 12
                fbox(F, u + math.cos(a) * 2.6 - 0.08, u + math.cos(a) * 2.6 + 0.08, cz + 3.5 + math.sin(a) * 2.6 - (0.35 if t % 3 == 0 else 0.18),
                     cz + 3.5 + math.sin(a) * 2.6 + (0.35 if t % 3 == 0 else 0.18), 0.1, 0.16, "black")
            hang = rng.uniform(0, math.tau)
            K.beam(tuple(F.p(u, cz + 3.5, 0.2)), tuple(F.p(u + math.cos(hang) * 2.2, cz + 3.5 + math.sin(hang) * 2.2, 0.2)), 0.12, mat="black")
            K.beam(tuple(F.p(u, cz + 3.5, 0.24)), tuple(F.p(u + math.cos(hang * 3) * 1.4, cz + 3.5 + math.sin(hang * 3) * 1.4, 0.24)), 0.16, mat="black")
    # cornice + copper cupola + antenna array + holo halo
    ctop = cz + 7.0
    box(tx0 - 0.6, tx1 + 0.6, ty0 - 0.6, ty1 + 0.6, ctop, ctop + 0.8, "concrete")
    K.lathe([(4.2, 0.0), (4.0, 1.2), (3.2, 3.0), (1.8, 4.6), (0.3, 6.2), (0.05, 8.5)], 8, at=(cx, cy, ctop + 0.8), mat="copper_patina")
    if L.lod() < 2:
        for k in range(4):
            a = math.radians(45 + 90 * k)
            P.antenna(cx + math.cos(a) * 3.0, cy + math.sin(a) * 3.0, ctop + 0.8, h=rng.uniform(5, 9), beacon=True)
    SH.holo_ring(cx, cy, ctop + 4.2, 5.5, h=0.8, mat="holo_cyan", n=36)
    meta["lights"] += [L.light(cx, ty0 - 2, cz + 3.5, "#ffd29a", 20, 2.0, "clock"), L.light(0, -8, 4, "#ffb070", 16, 1.2, "doors")]
    meta["beacons"] = [L.unity_pt(cx, cy, ctop + 9.3)]
    meta["colliders"] = [L.collider(0, 4, 6, 30, 20, 12), L.collider(cx, cy, (ctop + 1) / 2, 9, 9, ctop + 1)]
    meta["roofHeight"] = 12.0
    meta["height"] = round(ctop + 9.3, 2)
    meta["footprint"] = [38.0, 24.0]
    return meta


def stilt_tower():
    """12 x 14 m canal residential tower (13 storeys) raised on a 6 m concrete pier frame over a covered quay deck,
    stacked balconies with laundry and plants, rooftop garden pergola, water tanks."""
    meta = {"lights": []}
    rng = random.Random(403)
    fl = L.Floors(403, base=0.5, warm_bias=0.75)
    SH.stilts(-6, -7, 6, 7, 6.0, spacing=4.0, r=0.38, mat="concrete")
    box(-6.4, 6.4, -7.4, 7.4, 5.4, 6.0, "concrete_dark")
    st = P.style(ST.CANAL_B, balcony=0.55, laundry=0.6, plants=0.5, ground="none")
    floors = [(5.999, 0.001)] + [(6.0 + i * 3.4, 3.4) for i in range(13)]
    top = P.block(-6, -7, 6, 7, 6.0 + 13 * 3.4, st, fl, 4030, faces="sewn", street="", floors=floors, z_from=6.0, roofkind="canal", clutter=0.7, meta=meta)
    # stair core down to the deck
    box(-2.0, 2.0, 3.0, 7.0, 0.0, 6.0, "lm_brick_soot")
    if L.lod() < 2:
        m = Mesh("metal_painted", "door")
        m.wall(L.Frame(-1.0, 2.99, 1, 0, 2.0), 0.0, 2.0, 0.0, 2.3, 0.0, "metal_painted")
        # rooftop pergola with plants
        for x in (-4.5, 0.0, 4.5):
            for y in (-5.0, 5.0):
                K.cyl(0.08, 2.6, 6, at=(x, y, top), mat="wood")
        for y in (-5.0, 0.0, 5.0):
            box(-4.7, 4.7, y - 0.06, y + 0.06, top + 2.6, top + 2.7, "wood")
        for k in range(6):
            x, y = rng.uniform(-4, 4), rng.uniform(-4, 4)
            K.lathe([(0.2, 0.0), (0.7, 0.3), (0.6, 0.9), (0.0, 1.3)], 7, at=(x, y, top), mat=rng.choice(["foliage_dark", "foliage_mid"]))
        box(-6.0, 6.0, -7.3, -7.1, 5.6, 5.8, "emit_strip_warm")
    meta["lights"] += [L.light(0, 0, 4.8, "#ffb070", 14, 1.2, "deck")]
    meta["colliders"] = [L.collider(0, 0, (top + 6.0) / 2, 12, 14, top - 6.0), L.collider(0, 5, 3.0, 4, 4, 6.0)] + \
                        [L.collider(x, y, 3.0, 0.8, 0.8, 6.0) for x in (-6, -2, 2, 6) for y in (-7, 7)]
    meta["roofHeight"] = round(top, 2)
    meta["height"] = round(top + 4, 2)
    meta["footprint"] = [12.8, 14.8]
    return meta


LANDMARKS = {
    "LM_CW_WaterfrontRow": dict(fn=waterfront_row, district="CanalWard",
                                notes="Waterfront Row: five canal houses (6-8 storeys, brick / pastel) over a pier arcade facing the canal, balconies, laundry lines, retrofit cable trays and LED."),
    "LM_CW_ClockPumpHouse": dict(fn=clock_pump_house, district="CanalWard",
                                 notes="Clock Pump House: brick pump hall with arched factory glazing and a 48 m clock tower (lit dials, copper cupola, antenna array, holo halo)."),
    "LM_CW_StiltTower": dict(fn=stilt_tower, district="CanalWard",
                             notes="Stilt Tower: 13-storey canal tower on a 6 m pier frame over a covered deck, stacked balconies with laundry and plants, rooftop pergola."),
}
