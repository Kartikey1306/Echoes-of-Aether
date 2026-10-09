"""Arcology Gate landmarks: the Helix Arcology (megacorp tower, ~210 m with crown), the Meridian Spire (twisting
curtain-wall tower) and the Exchange Atrium (sloped-glass podium with a standing holo ring)."""
import math
import random

import lmkit as L
from lmkit import K, Mesh, fbox, box
import lmparts as P
import lmshapes as SH
import styles as ST

CORP_TOWER = P.style(ST.CORP, bay=2.2, fin=0.45, trim="lm_cladding_dark", led_seam="emit_strip_cyan")


def _portal(cx, y_face, w, h, depth, fl, rng, key):
    """Monumental entrance: two pylons with LED edges, a recessed double-height glass atrium, canopy, steps."""
    lv = L.lod()
    F = L.Frame(cx - w / 2, y_face, 1, 0, w)
    M = Mesh("lm_cladding_dark", "portal")
    # recessed atrium glazing in a grid of tall panes
    nb = max(2, int(w / 2.4))
    for i in range(nb):
        u0, u1 = i * w / nb, (i + 1) * w / nb
        for j, (z0, z1) in enumerate(((0.0, h * 0.45), (h * 0.45, h))):
            M.quad(F.p(u0, z0, -depth), F.p(u1, z0, -depth), F.p(u1, z1, -depth), F.p(u0, z1, -depth),
                   fl.office_pane(j, (key, i)) if j else "office_02_open_warm", ((0, 0), (1, 0), (1, 1), (0, 1)))
        if lv < 2:
            fbox(F, u1 - 0.08, u1 + 0.08, 0.0, h, -depth, -depth + 0.4, "titanium")
    # reveal walls
    M.reveal(F, 0.0, w, 0.0, h, depth, "lm_cladding_dark", None, bottom_mat="stone_light")
    # pylons
    for (a, b) in ((-4.0, 0.0), (w, w + 4.0)):
        fbox(F, a, b, 0.0, h + 6.0, -0.5, 1.5, "lm_cladding_dark")
        if lv < 2:
            fbox(F, a + 0.2, a + 0.3, 0.3, h + 5.6, 1.5, 1.56, "emit_strip_cyan")
            fbox(F, b - 0.3, b - 0.2, 0.3, h + 5.6, 1.5, 1.56, "emit_strip_cyan")
    # lintel band with an LED glyph screen
    fbox(F, -4.0, w + 4.0, h, h + 6.0, -0.5, 1.0, "lm_cladding_dark")
    m = Mesh("screen_ad_c", "lintel")
    m.wall(F, 2.0, w - 2.0, h + 1.2, h + 4.8, 1.02, "screen_ad_c")
    # canopy + steps
    fbox(F, -1.0, w + 1.0, h * 0.42, h * 0.42 + 0.5, 0.0, 6.0, "titanium")
    if lv < 2:
        fbox(F, -1.0, w + 1.0, h * 0.42 - 0.06, h * 0.42, 0.2, 5.8, "led_white")
        for k in range(4):
            fbox(F, -2.0, w + 2.0, 0.0, 0.18 * (4 - k), 0.0, 1.0 + k * 0.6, "stone_light")
    return F


def helix_arcology():
    """Megacorp arcology on a 56 x 58 m block: 18 m podium with a 22 m portal, four-lobed curtain-wall tower (34 m
    across) tapering and twisting 30 deg to 190 m, three sky gardens, crown cage with three holo rings and a spire."""
    meta = {"lights": []}
    rng = random.Random(301)
    fl = L.Floors(301, base=0.42, office=True)
    W, D = 56.0, 58.0
    pod_h = 18.0
    pod = P.style(ST.CORP, wall="lm_cladding_dark", bay=3.0, ground="lobby", G=6.0, H=4.0, led_seam="emit_strip_cyan")
    P.block(-W / 2 + 2, -D / 2 + 2, W / 2 - 2, D / 2 - 2, pod_h, pod, fl, 3011, faces="ewn", street="ewn", roof=True, clutter=0.0, parapet_h=1.4,
            floors=[(0.0, 6.0), (6.0, 4.0), (10.0, 4.0), (14.0, 4.0)])
    # front face: portal across the middle, cladding either side
    Ff = L.Frame(-W / 2 + 2, -D / 2 + 2, 1, 0, W - 4)
    M = Mesh("lm_cladding_dark", "front")
    pw = 22.0
    side = (W - 4 - pw - 8.0) / 2
    for (u0, u1) in ((0.0, side), (side + pw + 8.0, W - 4)):
        sub = L.Frame(Ff.p(u0, 0).x, Ff.p(u0, 0).y, 1, 0, u1 - u0)
        P.facade(M, sub, pod, [(0.0, 6.0), (6.0, 4.0), (10.0, 4.0), (14.0, 4.0)], fl, (3012, u0), street=True)
    _portal(0.0, -D / 2 + 2, pw, 14.0, 6.0, fl, rng, 3013)
    P.parapet(Ff, pod_h, 1.4, "lm_cladding_dark")
    # tower
    z0, z1 = pod_h, 190.0
    gardens = [(64.0, 7.2), (108.0, 7.2), (150.0, 7.2)]
    R0, lobe0 = 17.0, 8.0

    def plan(z):
        t = (z - z0) / (z1 - z0)
        r = R0 * (1 - 0.32 * t)
        lb = lobe0 * (1 - 0.28 * t)
        return SH.lobed_plan(0, 0, r, lb, n=4, seg=3, rot=45 + 30 * t)

    segs = []
    za = z0
    for (gz, gh) in gardens + [(z1, 0.0)]:
        segs.append((za, gz))
        za = gz + gh
    for i, (a, b) in enumerate(segs):
        SH.loft_tower(lambda t, a=a, b=b: plan(a + (b - a) * t), a, b, 3.6, CORP_TOWER, fl, (3014, i), cap=True)
    for (gz, gh) in gardens:
        SH.sky_garden(0, 0, plan(gz), gz, gh, rng)
        meta["lights"].append(L.light(0, -R0 * 0.8, gz + 3, "#ffd29a", 24, 1.5, "sky garden"))
    # crown: tapering cage of fins, three holo rings, spire
    top_plan = plan(z1)
    lv = L.lod()
    nf = 16 if lv == 0 else 8
    for k in range(nf):
        a = math.tau * k / nf
        p0 = (math.cos(a) * 11.0, math.sin(a) * 11.0, z1)
        p1 = (math.cos(a + 0.4) * 3.0, math.sin(a + 0.4) * 3.0, z1 + 26.0)
        K.beam(p0, p1, 0.5 if lv < 2 else 0.8, mat="lm_cladding_dark")
        if lv == 0:
            K.beam((p0[0] * 1.02, p0[1] * 1.02, p0[2] + 0.5), (p1[0] * 1.05, p1[1] * 1.05, p1[2] - 0.5), 0.08, mat="emit_strip_cyan")
    for (zz, r, mat) in ((z1 + 6.0, 10.0, "holo_cyan"), (z1 + 13.0, 7.6, "holo_magenta"), (z1 + 19.5, 5.2, "holo_cyan")):
        SH.holo_ring(0, 0, zz, r, h=1.6, mat=mat, n=40, tilt=0.6)
        if lv < 2:
            K.torus(r, 0.12, n_major=32 if lv == 0 else 16, n_minor=4, mat="led_white").move(0, 0, zz)
    K.cyl(0.6, 22.0, 8, at=(0, 0, z1 + 18.0), r2=0.1, mat="titanium")
    K.cyl(0.3, 0.4, 6, at=(0, 0, z1 + 40.0), mat="beacon_red")
    meta["lights"] += [L.light(0, -D / 2 - 4, 8, "#00e5ff", 28, 2.5, "portal"), L.light(0, 0, z1 + 12, "#00e5ff", 40, 3.0, "crown")]
    meta["screens"] = [{"center": L.unity_pt(0, -D / 2 + 1.0, 14.0 + 3.0), "size": [pw - 4, 3.6], "normal": [0, 0, 1]}]
    meta["beacons"] = [L.unity_pt(0, 0, z1 + 40.2)]
    meta["colliders"] = [L.collider(0, 0, pod_h / 2, W - 4, D - 4, pod_h), L.collider(0, 0, (z1 + pod_h) / 2, 30, 30, z1 - pod_h)]
    meta["roofHeight"] = pod_h
    meta["height"] = round(z1 + 40.4, 2)
    meta["footprint"] = [W, D]
    return meta


def meridian_spire():
    """Chamfered 28 m square curtain-wall tower twisting 45 deg over 34 storeys (~132 m), on a 44 x 44 m glass lobby
    podium; open crown frame with LED rings, a holo band and a 30 m spire."""
    meta = {"lights": []}
    rng = random.Random(302)
    fl = L.Floors(302, base=0.4, office=True)
    pod = P.style(ST.CORP_B, ground="lobby", G=6.5, H=4.0, bay=3.0)
    P.block(-22, -22, 22, 22, 10.5, pod, fl, 3021, faces="sewn", street="sewn", clutter=0.0, floors=[(0.0, 6.5), (6.5, 4.0)], parapet_h=0.8)
    z0, z1 = 10.5, 132.0
    st = P.style(ST.CORP_B, bay=2.2, trim="metal_dark", led_seam="emit_strip_violet", fin=0.35)

    def plan(t):
        rot = math.radians(45 * t)
        pts = SH.chamfer_rect(0, 0, 14.0 - 1.5 * t, 14.0 - 1.5 * t, 4.0)
        return [(x * math.cos(rot) - y * math.sin(rot), x * math.sin(rot) + y * math.cos(rot)) for (x, y) in pts]

    SH.loft_tower(plan, z0, z1, 3.6, st, fl, 3022, cap=True)
    # crown frame
    lv = L.lod()
    tp = plan(1.0)
    for (x, y) in tp:
        K.beam((x, y, z1), (x * 0.55, y * 0.55, z1 + 18.0), 0.45, mat="metal_dark")
    for zz, s in ((z1 + 6.0, 0.88), (z1 + 12.0, 0.72)):
        pts = [(x * s, y * s) for (x, y) in tp]
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            K.beam((a[0], a[1], zz), (b[0], b[1], zz), 0.3, mat="emit_strip_violet" if lv < 2 else "metal_dark")
    SH.holo_ring(0, 0, z1 + 2.0, 10.5, h=3.0, mat="holo_magenta", n=40)
    K.cyl(0.5, 30.0, 8, at=(0, 0, z1 + 10.0), r2=0.08, mat="titanium")
    K.cyl(0.25, 0.35, 6, at=(0, 0, z1 + 40.0), mat="beacon_red")
    meta["lights"] += [L.light(0, -23, 4, "#9b5cff", 22, 2.0, "lobby"), L.light(0, 0, z1 + 8, "#ff2bd6", 36, 2.5, "crown")]
    meta["beacons"] = [L.unity_pt(0, 0, z1 + 40.2)]
    meta["colliders"] = [L.collider(0, 0, 5.25, 44, 44, 10.5), L.collider(0, 0, (z0 + z1) / 2, 26, 26, z1 - z0)]
    meta["roofHeight"] = 10.5
    meta["height"] = round(z1 + 40.4, 2)
    meta["footprint"] = [44.0, 44.0]
    return meta


def exchange_atrium():
    """50 x 40 m corporate exchange: four storeys of dark cladding with a raked glass atrium front, LED fins, and an
    18 m standing holo ring (logo-free) on the roof plaza with a light mast."""
    meta = {"lights": []}
    rng = random.Random(303)
    fl = L.Floors(303, base=0.55, office=True)
    W, D, H = 50.0, 40.0, 21.0
    st = P.style(ST.CORP, wall="lm_cladding_dark", ground="lobby", G=6.0, H=5.0, bay=3.3, led_seam="emit_strip_cyan")
    top = P.block(-W / 2, -D / 2 + 8, W / 2, D / 2, H, st, fl, 3031, faces="ewn", street="ewn", clutter=0.0, parapet_h=1.0)
    # raked atrium: glass plane leaning out from the roof edge down to the street 8 m forward
    M = Mesh("glass_dark", "rake")
    nb = 16
    for i in range(nb):
        x0, x1 = -W / 2 + i * W / nb, -W / 2 + (i + 1) * W / nb
        for j in range(5):
            t0, t1 = j / 5, (j + 1) / 5
            ya, yb = -D / 2 + 8 * (1 - t0), -D / 2 + 8 * (1 - t1)
            za, zb = H * t0, H * t1
            from mathutils import Vector
            M.quad(Vector((x0, ya, za)), Vector((x1, ya, za)), Vector((x1, yb, zb)), Vector((x0, yb, zb)),
                   fl.office_pane(j, ("rake", i)) if j > 0 else "office_02_open_warm", ((0, 0), (1, 0), (1, 1), (0, 1)))
        if L.lod() < 2:
            K.beam((x1, -D / 2, 0.0), (x1, -D / 2 + 8, H), 0.22, mat="titanium")
            if L.lod() == 0 and i % 2 == 0:
                K.beam((x1, -D / 2 - 0.15, 0.2), (x1, -D / 2 + 7.85, H + 0.2), 0.05, mat="emit_strip_cyan")
    # side triangles of the rake
    for xx, s in ((-W / 2, -1), (W / 2, 1)):
        bm = M.bm
        vs = [bm.verts.new((xx, -D / 2, 0.0)), bm.verts.new((xx, -D / 2 + 8, 0.0)), bm.verts.new((xx, -D / 2 + 8, H))]
        if s < 0:
            vs.reverse()
        f = bm.faces.new(vs)
        f[M.part.mats] = M.part.slot("lm_cladding_dark")
        f[M.part.uvm] = K.UVM_KEEP
        for l in f.loops:
            l[M.part.uvl].uv = (l.vert.co.y, l.vert.co.z)
    # roof plaza: standing holo ring + mast
    ring_z = top + 0.4
    box(-6, 6, -2, 4, top, top + 0.4, "stone_light")
    if L.lod() < 2:
        for k in range(36 if L.lod() == 0 else 18):
            a0 = math.tau * k / (36 if L.lod() == 0 else 18)
            a1 = math.tau * (k + 1) / (36 if L.lod() == 0 else 18)
            p0 = (math.cos(a0) * 9.0, 1.0, ring_z + 9.4 + math.sin(a0) * 9.0)
            p1 = (math.cos(a1) * 9.0, 1.0, ring_z + 9.4 + math.sin(a1) * 9.0)
            K.beam(p0, p1, 0.45, mat="titanium")
    hr = SH.holo_ring(0, 0, 0, 8.6, h=1.0, mat="holo_cyan", n=48)
    hr.part.rot(x=90).move(0, 1.5, ring_z + 9.4)
    for x in (-3.0, 3.0):
        K.beam((x, 1.0, ring_z), (math.copysign(6.4, x), 1.0, ring_z + 3.5), 0.4, mat="titanium")
    meta["lights"] += [L.light(0, -D / 2 - 3, 6, "#00e5ff", 26, 2.2, "atrium"), L.light(0, -2, ring_z + 9, "#00e5ff", 30, 2.5, "holo ring")]
    meta["colliders"] = [L.collider(0, 8 / 2, H / 2, W, D - 8, H), L.collider(0, -D / 2 + 4, H / 4, W, 8, H / 2)]
    meta["roofHeight"] = round(top, 2)
    meta["height"] = round(ring_z + 18.8, 2)
    meta["footprint"] = [W, D]
    return meta


LANDMARKS = {
    "LM_AG_HelixArcology": dict(fn=helix_arcology, district="ArcologyGate",
                                notes="Helix Arcology: megacorp tower on an 18 m podium with a 22 m portal; four-lobed curtain-wall shaft twisting to 190 m, three sky gardens, crown cage with three holo rings and a spire (~230 m)."),
    "LM_AG_MeridianSpire": dict(fn=meridian_spire, district="ArcologyGate",
                                notes="Meridian Spire: chamfered curtain-wall tower twisting 45 deg to 132 m on a glass lobby podium, LED crown frame, holo band, spire."),
    "LM_AG_ExchangeAtrium": dict(fn=exchange_atrium, district="ArcologyGate",
                                 notes="Exchange Atrium: four-storey corporate exchange with a raked glass atrium front and an 18 m standing holo ring on the roof."),
}
