"""Foundry Row landmarks: Ember Refinery (three smokestacks, distillation columns, tanks, pipe racks, flare),
Cooling Tower (55 m hyperbolic shell + pump house), Sawtooth Works (north-light hall + yard gantry crane)."""
import math
import random

import lmkit as L
from lmkit import K, Mesh, fbox, box
import lmparts as P
import lmshapes as SH
import styles as ST


def ember_refinery():
    """56 x 60 m works: three banded smokestacks (72 / 64 / 56 m) with beacons and furnace glow, four distillation
    columns with platforms, three storage tanks, pipe racks feeding a three-storey control building, flare stack."""
    meta = {"lights": [], "beacons": []}
    rng = random.Random(501)
    fl = L.Floors(501, base=0.35)
    # concrete apron
    box(-28, 28, -29, 29, 0.0, 0.15, "concrete_dark")
    # control building at the front
    P.block(-26, -29, 0, -15, 12.6, P.style(ST.FOUNDRY_B, ground="industrial", win="ribbon", win_w=2.0, G=4.2, H=4.2, bay=3.2), fl, 5010,
            faces="sewn", street="s", roofkind="foundry", clutter=0.6, meta=meta, floors=[(0.0, 4.2), (4.2, 4.2), (8.4, 4.2)])
    # stacks on a plinth
    for (x, y, h, r0, r1) in ((14.0, 18.0, 72.0, 2.6, 1.7), (20.0, 6.0, 64.0, 2.3, 1.5), (6.0, 24.0, 56.0, 2.1, 1.4)):
        box(x - r0 - 1, x + r0 + 1, y - r0 - 1, y + r0 + 1, 0.0, 2.0, "concrete")
        meta["beacons"].append(SH.smokestack(x, y, 2.0, h, r0=r0, r1=r1))
    # distillation columns with platforms + ladders
    for (x, y, h, r) in ((-14.0, 8.0, 38.0, 1.6), (-8.0, 14.0, 32.0, 1.3), (-17.0, 20.0, 28.0, 1.1), (-6.0, 24.0, 24.0, 1.0)):
        K.cyl(r, h, 16 if L.lod() == 0 else 8, at=(x, y, 0.15), mat="metal_bare" if L.lod() < 2 else "metal_painted_white")
        K.lathe([(r, 0.0), (r * 0.5, r * 0.4), (0.0, r * 0.5)], 12 if L.lod() == 0 else 6, at=(x, y, h + 0.15), mat="metal_bare")
        if L.lod() < 2:
            for k in range(1, int(h / 6)):
                K.cyl(r + 0.9, 0.1, 12, at=(x, y, k * 6.0), mat="metal_dark")
                if L.lod() == 0:
                    K.torus(r + 0.85, 0.03, n_major=12, n_minor=4, mat="metal_painted_yellow").move(x, y, k * 6.0 + 1.0)
            K.cyl(0.1, 0.18, 6, at=(x, y, h + r * 0.5), mat="beacon_red")
    # tanks
    for (x, y, r, h) in ((-20.0, -4.0, 6.0, 9.0), (-7.0, -6.0, 5.0, 8.0), (20.0, -12.0, 6.5, 10.0)):
        SH.tank(x, y, 0.15, r, h, mat="metal_painted_white", stripes="metal_painted_red")
    # pipe racks connecting everything
    SH.pipe_rack(-26.0, -11.5, 26.0, 4.5, levels=3, w=3.2, rng=rng)
    if L.lod() < 2:
        SH.pipe_run([(-14.0, 8.0, 12.0), (-14.0, -10.0, 12.0), (-14.0, -11.5, 7.3)], 0.35, "metal_rusted")
        SH.pipe_run([(14.0, 15.0, 6.0), (14.0, -10.0, 6.0), (14.0, -11.5, 4.6)], 0.45, "paint_glossy_red")
        SH.pipe_run([(20.0, 3.5, 3.0), (25.0, 3.5, 3.0), (25.0, -11.0, 3.0)], 0.3, "metal_painted")
    # flare stack with flame glow
    K.cyl(0.5, 46.0, 8, at=(25.0, 26.0, 0.15), r2=0.35, mat="metal_rusted")
    K.lathe([(0.0, 0.0), (0.9, 1.2), (0.5, 3.2), (0.0, 4.5)], 8, at=(25.0, 26.0, 46.2), mat="furnace")
    meta["beacons"].append(L.unity_pt(25.0, 26.0, 50.0))
    meta["lights"] += [L.light(25.0, 26.0, 48.0, "#ff8a2a", 40, 4.0, "flare"), L.light(14.0, 18.0, 70.0, "#ff3a2e", 30, 2.0, "stack"),
                       L.light(0, -31, 4, "#ffa21f", 18, 1.4, "gate")]
    meta["colliders"] = [L.collider(-13, -22, 6.3, 26, 14, 12.6)] + \
                        [L.collider(x, y, h / 2 + 1, r0 * 2 + 2, r0 * 2 + 2, h + 2) for (x, y, h, r0) in ((14, 18, 72, 2.6), (20, 6, 64, 2.3), (6, 24, 56, 2.1))] + \
                        [L.collider(x, y, h / 2, r * 2, r * 2, h) for (x, y, r, h) in ((-20, -4, 6, 9), (-7, -6, 5, 8), (20, -12, 6.5, 10))] + \
                        [L.collider(x, y, h / 2, r * 2, r * 2, h) for (x, y, h, r) in ((-14, 8, 38, 1.6), (-8, 14, 32, 1.3), (-17, 20, 28, 1.1), (-6, 24, 24, 1.0))]
    meta["roofHeight"] = 12.6
    meta["height"] = 74.5
    meta["footprint"] = [56.0, 58.0]
    return meta


def cooling_tower():
    """55 m hyperbolic cooling tower (42 m base) on raker legs with a glowing throat, a pump house and pipes."""
    meta = {"lights": []}
    rng = random.Random(502)
    fl = L.Floors(502, base=0.3)
    box(-27, 27, -27, 27, 0.0, 0.15, "concrete_dark")
    beacon = SH.cooling_tower(0.0, 3.0, 0.15, 55.0, 21.0, 13.0, 14.6)
    P.block(-26, -26, -12, -16, 8.4, P.style(ST.FOUNDRY, ground="industrial", G=4.2, H=4.2), fl, 5020, faces="sewn", street="sw",
            roofkind="foundry", clutter=0.8, floors=[(0.0, 4.2), (4.2, 4.2)])
    if L.lod() < 2:
        for k, (x, y) in enumerate(((-16.0, -16.5), (-14.0, -16.5))):
            SH.pipe_run([(x, y + 0.5, 1.2 + k), (x, -6.0, 1.2 + k), (-6.0, -6.0, 1.2 + k)], 0.55, "paint_glossy_red" if k else "metal_painted")
        for a in range(6):
            ang = math.radians(a * 60 + 15)
            K.cyl(0.18, 0.25, 6, at=(math.cos(ang) * 14.6, 3.0 + math.sin(ang) * 14.6, 55.3), mat="beacon_red")
    meta["lights"] += [L.light(0, 3, 52, "#ff8a2a", 30, 2.0, "throat"), L.light(-19, -27, 4, "#ffa21f", 14, 1.0, "pump house")]
    meta["beacons"] = [beacon]
    # ring of box colliders approximating the shell base
    cols = []
    for a in range(12):
        ang = math.tau * a / 12
        cols.append(L.collider(math.cos(ang) * 19.5, 3.0 + math.sin(ang) * 19.5, 27.5, 10.0, 10.0, 55.0))
    meta["colliders"] = cols + [L.collider(-19, -21, 4.2, 14, 10, 8.4)]
    meta["roofHeight"] = 8.4
    meta["height"] = 55.5
    meta["footprint"] = [54.0, 54.0]
    return meta


def sawtooth_works():
    """50 x 40 m north-light works: brick base, corrugated upper walls, eight-tooth sawtooth roof with lit
    glazing, loading docks, a 22 m gantry crane over the side yard, chimney and water tower."""
    meta = {"lights": []}
    rng = random.Random(503)
    fl = L.Floors(503, base=0.6, warm_bias=0.2)
    st = P.style(ST.FOUNDRY, wall="lm_corrugated_painted", wall2="lm_brick_soot", G=5.0, H=4.6, bay=4.6)
    top = P.block(-25, -20, 15, 20, 9.6, st, fl, 5030, faces="sewn", street="sw", roof=False, clutter=0.0, floors=[(0.0, 5.0), (5.0, 4.6)])
    SH.sawtooth_roof(-25, -20, 15, 20, top, 8, rise=3.4)
    if L.lod() < 2:
        box(-25.2, 15.2, -20.2, 20.2, top - 0.2, top, "metal_dark")
    # side yard with the gantry crane (east, x 15..25)
    box(15, 25, -20, 20, 0.0, 0.12, "concrete_wet")
    SH.gantry_crane(20.5, 0.0, 0.12, 9.0, 14.0, 40.0, rng=rng)
    if L.lod() < 2:
        for k in range(5):
            y = -16 + k * 7.0
            box(17.0, 23.5, y, y + 2.5, 0.12, 2.7, rng.choice(["metal_painted_red", "lm_corrugated_painted", "metal_painted", "metal_painted_yellow"]))
            if k % 2 == 0:
                box(17.0, 23.5, y, y + 2.5, 2.7, 5.3, rng.choice(["metal_painted", "metal_rusted", "lm_corrugated_painted"]))
    # chimney + water tower
    SH.smokestack(-21.0, 16.0, 0.0, 30.0, r0=1.2, r1=0.9, mat="lm_brick_soot", bands=("concrete",), ladder=False)
    P.water_tank(-6.0, 14.0, top + 3.4, r=2.0, h=3.0, legs=4.0, mat="metal_rusted")
    meta["lights"] += [L.light(20, 0, 13, "#ffa21f", 22, 1.6, "crane"), L.light(-5, -22, 5, "#ffb070", 18, 1.2, "docks")]
    meta["colliders"] = [L.collider(-5, 0, top / 2, 40, 40, top), L.collider(-21, 16, 15, 2.6, 2.6, 30.0)] + \
                        [L.collider(20.5 + s * 4.5, 0, 7, 1.2, 6.0, 14) for s in (-1, 1)]
    meta["roofHeight"] = round(top, 2)
    meta["height"] = 30.0
    meta["footprint"] = [50.0, 40.0]
    return meta


LANDMARKS = {
    "LM_FR_EmberRefinery": dict(fn=ember_refinery, district="FoundryRow",
                                notes="Ember Refinery: three banded smokestacks (72/64/56 m) with beacons and furnace glow, distillation columns, tanks, pipe racks, control building, flare stack."),
    "LM_FR_CoolingTower": dict(fn=cooling_tower, district="FoundryRow",
                               notes="Cooling Tower: 55 m hyperbolic shell on raker legs with a glowing throat, pump house, pipes, beacons."),
    "LM_FR_SawtoothWorks": dict(fn=sawtooth_works, district="FoundryRow",
                                notes="Sawtooth Works: north-light hall with an eight-tooth glazed sawtooth roof, brick/corrugated walls, yard gantry crane, containers, chimney, water tower."),
}
