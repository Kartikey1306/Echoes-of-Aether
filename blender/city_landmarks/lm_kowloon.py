"""Kowloon Stacks landmarks: The Stack (walled-city megablock), Bridge Twins (tenement towers joined by enclosed
skybridges), Signal Spire (tenement crowned by a red/white lattice telecom mast)."""
import math
import random

import lmkit as L
from lmkit import K, Mesh, fbox, box
import lmparts as P
import lmshapes as SH
import styles as ST


def _cells_compound(cells, st_pick, fl, seed, meta, roofkind="kowloon", street_all=True):
    """Grid of abutting tenement towers [(x0, y0, x1, y1, height)]: each face is built only where it is exposed
    (above a lower neighbour or on the street); every tower gets its own roof clutter."""
    def neighbour_h(c, face):
        x0, y0, x1, y1, h = c
        best = 0.0
        for o in cells:
            if o is c:
                continue
            ox0, oy0, ox1, oy1, oh = o
            if face == "s" and abs(oy1 - y0) < 0.05 and ox0 < x1 - 0.5 and ox1 > x0 + 0.5:
                best = max(best, oh)
            if face == "n" and abs(oy0 - y1) < 0.05 and ox0 < x1 - 0.5 and ox1 > x0 + 0.5:
                best = max(best, oh)
            if face == "e" and abs(ox0 - x1) < 0.05 and oy0 < y1 - 0.5 and oy1 > y0 + 0.5:
                best = max(best, oh)
            if face == "w" and abs(ox1 - x0) < 0.05 and oy0 < y1 - 0.5 and oy1 > y0 + 0.5:
                best = max(best, oh)
        return best

    tops = []
    for i, c in enumerate(cells):
        x0, y0, x1, y1, h = c
        zf = {}
        faces = ""
        street = ""
        for f in "sewn":
            nh = neighbour_h(c, f)
            if nh >= h - 0.5:
                continue
            faces += f
            zf[f] = nh
            if nh < 0.5:
                street += f
        st = st_pick(i)
        top = P.block(x0, y0, x1, y1, h, st, fl, seed + i * 13, faces=faces, street=street if street_all else street[:1],
                      roofkind=roofkind, z_from=zf, meta=meta, clutter=1.3)
        tops.append(top)
    return tops


def the_stack():
    """40 x 30 m walled-city megablock: nine abutting tenements 34-62 m tall in two rows, every exposed face covered
    in cages, cantilevered rooms, AC clusters and laundry; shanty towns, water tanks and an antenna forest on every
    roof; a 22 m lattice mast on the tallest tower."""
    meta = {"lights": []}
    rng = random.Random(201)
    fl = L.Floors(201, base=0.55, warm_bias=0.4)
    xs = [-20.0, -11.0, -1.5, 7.0, 20.0]
    ys = [-15.0, -1.0, 15.0]
    hs = [[44.8, 57.6, 38.4, 51.2], [35.2, 48.0, 61.4, 41.6]]
    cells = []
    for j in range(2):
        for i in range(4):
            cells.append((xs[i], ys[j], xs[i + 1], ys[j + 1], hs[j][i] + 4.0))
    tops = _cells_compound(cells, lambda i: ST.STACK if i % 3 != 1 else ST.STACK_B, fl, 2010, meta)
    k = max(range(len(cells)), key=lambda i: tops[i])
    c = cells[k]
    beacons = SH.lattice_mast((c[0] + c[2]) / 2, (c[1] + c[3]) / 2, tops[k], 22.0, base=1.4, top=0.25, beacons=3, dishes=5, rng=rng)
    # laundry lines between neighbouring towers at random heights (front)
    if L.lod() == 0:
        for i in range(8):
            z = rng.uniform(8, 30)
            x = rng.uniform(-18, 18)
            K.tube([(x, -15.3, z), (x + 0.2, -15.9, z - 0.4), (x + 0.4, -16.5, z)], 0.01, 4, "rope")
    # street-level cage arcade signs on the front
    F = L.rect_frames(-20, -15, 20, 15)["s"]
    for u in (3.0, 14.0, 27.0, 36.0):
        P.lightbox_sign(F, u, 4.6, rng.uniform(4, 9), w_out=0.4, width=1.0, rng=rng, depth=0.25)
    meta["lights"] += [L.light(0, -17, 4, "#ffb070", 14, 1.0, "street"), L.light(-10, -17, 12, "#00e5ff", 14, 0.8, "signs")]
    meta["beacons"] = beacons
    meta["colliders"] = [L.collider((c[0] + c[2]) / 2, (c[1] + c[3]) / 2, c[4] / 2, c[2] - c[0], c[3] - c[1], c[4]) for c in cells]
    meta["roofHeight"] = round(max(tops), 2)
    meta["height"] = round(max(tops) + 22.0, 2)
    meta["footprint"] = [40.0, 30.0]
    return meta


def bridge_twins():
    """Two 14 x 14 m tenement towers (20 / 18 storeys) 8 m apart on a two-storey podium, joined by four enclosed
    skybridges with lit windows, laundry lines strung between them, rooftop shanties and water tanks."""
    meta = {"lights": []}
    rng = random.Random(202)
    fl = L.Floors(202, base=0.5)
    P.block(-19, -9, 19, 9, 8.6, P.style(ST.STACK, ground="shops", signs=0.3), fl, 2020, faces="sewn", street="sewn",
            floors=[(0.0, 4.6), (4.6, 4.0)], roofkind="kowloon", clutter=0.0, meta=meta)
    tA = P.block(-18, -7, -4, 7, 68.4, ST.STACK, fl, 2021, faces="sewn", street="", z_from=8.6, z_base=0.0, roofkind="kowloon", clutter=1.4,
                 floors=[(0.0, 8.6)] + [(8.6 + i * 3.2, 3.2) for i in range(18)])
    tB = P.block(4, -7, 18, 7, 62.0, ST.STACK_B, fl, 2022, faces="sewn", street="", z_from=8.6, roofkind="kowloon", clutter=1.4,
                 floors=[(0.0, 8.6)] + [(8.6 + i * 3.2, 3.2) for i in range(16)])
    # podium roof between and around the towers
    M = Mesh("concrete_wet", "podroof")
    M.cap([(-19, -9), (19, -9), (19, 9), (-19, 9)], 8.62, "concrete_wet")
    for zb in (18.2, 30.0, 43.0, 52.6):
        y0 = rng.uniform(-5.0, 1.0)
        box(-4.0, 4.0, y0, y0 + 3.2, zb, zb + 3.0, "lm_corrugated_painted")
        box(-4.0, 4.0, y0 - 0.1, y0 + 3.3, zb - 0.25, zb, "metal_rusted")
        box(-4.0, 4.0, y0 - 0.1, y0 + 3.3, zb + 3.0, zb + 3.15, "metal_rusted")
        mm = Mesh("glass_dark", "bridgewin")
        Fw = L.Frame(-3.6, y0 - 0.01, 1, 0, 7.2)
        for k in range(3):
            mm.wall(Fw, 0.2 + k * 2.4, 2.2 + k * 2.4, zb + 1.0, zb + 2.2, 0.0, fl.window(int(zb / 3.2), ("bw", zb, k)))
        Fn = L.Frame(3.6, y0 + 3.21, -1, 0, 7.2)
        for k in range(3):
            mm.wall(Fn, 0.2 + k * 2.4, 2.2 + k * 2.4, zb + 1.0, zb + 2.2, 0.0, fl.window(int(zb / 3.2), ("bn", zb, k)))
        if L.lod() < 2:
            for x in (-3.0, 3.0):
                K.beam((x, y0 + 1.6, zb - 0.25), (x * 1.3, y0 + 1.6, zb - 3.0), 0.12, mat="metal_rusted")
    if L.lod() == 0:
        for i in range(10):
            z = rng.uniform(12, 55)
            y = rng.uniform(-6.5, 6.5)
            K.tube([(-4.0, y, z), (0.0, y, z - rng.uniform(0.4, 1.2)), (4.0, y, z)], 0.012, 4, "rope")
            for k in range(rng.randint(2, 5)):
                x = rng.uniform(-3, 3)
                box(x - 0.2, x + 0.2, y - 0.05, y + 0.05, z - 1.0 - rng.uniform(0, 0.4), z - 0.45, rng.choice(["cloth_white", "cloth_red", "cloth_blue", "cloth_yellow"]))
    # tall vertical sign on tower A's street corner
    Fa = L.rect_frames(-18, -7, -4, 7)["s"]
    SH.blade_tower(Fa, 0.4, 10.0, 22.0, out=1.8, rng=rng)
    meta["lights"] += [L.light(-18.5, -9.5, 20, "#ff2bd6", 18, 1.4, "blade"), L.light(0, -10, 4, "#ffb070", 14, 1.0, "street")]
    meta["colliders"] = [L.collider(0, 0, 4.3, 38, 18, 8.6), L.collider(-11, 0, 34.2, 14, 14, 68.4), L.collider(11, 0, 31.0, 14, 14, 62.0)]
    meta["roofHeight"] = round(max(tA, tB), 2)
    meta["height"] = round(max(tA, tB) + 8, 2)
    meta["footprint"] = [38.0, 18.0]
    return meta


def signal_spire():
    """18 x 18 m tenement (12 storeys) crowned by a 38 m red / white lattice telecom mast with dishes, panel
    antennas and three beacons - the tallest silhouette of the Stacks (~84 m)."""
    meta = {"lights": []}
    rng = random.Random(203)
    fl = L.Floors(203, base=0.45)
    top = P.block(-9, -9, 9, 9, 42.4, P.style(ST.STACK_B, signs=0.25), fl, 2030, faces="sewn", street="sewn", roofkind="kowloon", clutter=0.8,
                  meta=meta)
    # equipment house under the mast
    box(-4, 4, -4, 4, top, top + 3.2, "lm_concrete_weathered")
    box(-4.2, 4.2, -4.2, 4.2, top + 3.2, top + 3.45, "metal_dark")
    if L.lod() < 2:
        mm = Mesh("glass_dark", "eqh")
        mm.wall(L.Frame(-4, -4.01, 1, 0, 8), 1.0, 7.0, top + 1.4, top + 2.4, 0.0, "office_07_server")
    beacons = SH.lattice_mast(0, 0, top + 3.45, 38.0, base=3.2, top=0.35, beacons=3, dishes=6, rng=rng)
    SH.blade_tower(L.rect_frames(-9, -9, 9, 9)["s"], 17.6, 4.8, 14.0, out=1.5, rng=rng)
    meta["lights"] += [L.light(9.5, -10.5, 11, "#00e5ff", 16, 1.2, "blade")]
    meta["beacons"] = beacons
    meta["colliders"] = [L.collider(0, 0, top / 2, 18, 18, top)]
    meta["roofHeight"] = round(top, 2)
    meta["height"] = round(top + 3.45 + 38.0 * 1.18, 2)
    meta["footprint"] = [18.0, 18.0]
    return meta


LANDMARKS = {
    "LM_KS_TheStack": dict(fn=the_stack, district="KowloonStacks",
                           notes="The Stack: walled-city megablock of eight abutting tenements (38-65 m), cages, cantilevered rooms, AC, laundry, shanty roofs, antenna forest, 22 m lattice mast."),
    "LM_KS_BridgeTwins": dict(fn=bridge_twins, district="KowloonStacks",
                              notes="Bridge Twins: two 20/18-storey tenement towers on a podium joined by four enclosed skybridges, laundry lines, blade sign."),
    "LM_KS_SignalSpire": dict(fn=signal_spire, district="KowloonStacks",
                              notes="Signal Spire: 12-storey tenement crowned by a 38 m red/white lattice telecom mast with beacons and dishes (~88 m)."),
}
