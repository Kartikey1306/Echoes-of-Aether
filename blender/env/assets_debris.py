"""Debris (cyberpunk restyle): rubble piles, chunks, rebar clusters, collapsed slabs, scrap metal.

Compatibility: names, pivots, colliders and material slots match the baseline (out/baseline/assets.json). Because the
piles are procedural, each restyled asset is fitted to its baseline bounding box (FIT, Blender coordinates) after
building, so the Unity size and bounds centre are unchanged at every LOD.
"""
import math
import random

import bmesh
from mathutils import Vector

import envkit as K
from envkit import box, cyl, lathe, rock, tube, torus, boolean, detail
from assets_dressing import rebar, broken_slab, chips_scatter, soft_box, ribbon, bend_path, catenary, U

# baseline bounds (Blender min, max) of every debris asset
FIT = {
    "A": ((-1.2555, -1.3895, 0.0), (1.0915, 1.2115, 0.8955)),
    "B": ((-2.068, -2.265, 0.0), (2.34, 2.333, 1.3595)),
    "C": ((-0.832, -0.787, 0.0), (0.672, 0.679, 0.5295)),
    "Dark": ((-1.0, -1.092, 0.0), (1.266, 1.05, 1.1505)),
    "ChunkL": ((-0.4245, -0.323, 0.0), (0.6985, 0.347, 0.5885)),
    "ChunkS": ((-0.188, -0.146, 0.0), (0.296, 0.15, 0.2285)),
    "Rebar": ((-0.405, -0.172, 0.0), (0.397, 0.45, 1.0685)),
    "SlabC": ((-2.429, -2.052, 0.0), (2.951, 1.5, 1.946)),
    "SlabF": ((-2.5005, -1.3, 0.0), (2.2365, 1.3, 0.81)),
    "Scrap": ((-1.5565, -1.4425, 0.0), (1.4145, 0.7785, 0.8205)),
}


def fit_bounds(parts, key):
    """Affinely remap the parts so their joint bounding box equals FIT[key] exactly."""
    tmn, tmx = (Vector(v) for v in FIT[key])
    mn = Vector((1e9, 1e9, 1e9))
    mx = Vector((-1e9, -1e9, -1e9))
    for p in parts:
        for v in p.bm.verts:
            for i in range(3):
                mn[i] = min(mn[i], v.co[i])
                mx[i] = max(mx[i], v.co[i])
    s = [(tmx[i] - tmn[i]) / max(1e-6, mx[i] - mn[i]) for i in range(3)]
    for p in parts:
        for v in p.bm.verts:
            v.co = Vector(tuple(tmn[i] + (v.co[i] - mn[i]) * s[i] for i in range(3)))
        p.bm.normal_update()
    return s


# ---------------------------------------------------------------------------------------------- pieces
def _fragment(rnd, size, seed, mat="concrete", bars=3, at=(0, 0, 0), rot=(0, 0, 0)):
    """Broken slab fragment: flat angular plate with rebar stubs out of one fractured edge."""
    sx, sy, sz = size
    m0 = K.part_count()
    rock((sx, sy, sz), seed, cuts=14, mat=mat, rough=0.03, flat=0.8, bevel=0.05)
    if detail() and bars:
        for i in range(bars):
            f = (i + 0.5) / bars - 0.5
            st = (sx * 0.3, f * sy * 0.8, rnd.uniform(-sz * 0.15, sz * 0.15))
            rebar(st, (1, rnd.uniform(-0.3, 0.3), rnd.uniform(-0.2, 0.5)), rnd.uniform(0.2, 0.45) * max(1.0, sx), 0.007, rnd)
    for p in K.parts_since(m0):
        p.rot(*rot).move(*at)


def _brick(rnd, at, half=False):
    L = 0.11 if half else 0.215
    b = box(L, 0.1, 0.065, mat="brick", bevel=0.006 if detail() else 0.0)
    b.rot(x=rnd.uniform(-25, 25), y=rnd.uniform(-25, 25), z=rnd.uniform(0, 180)).move(*at)
    return b


def _bent_sheet(rnd, w, h, at, mat="metal_rusted", seed=0, corrugated=False):
    nx = K.seg(int(w / (0.03 if corrugated else 0.12)) + 2, 3)
    p = K.plane(w, h, mat=mat, nx=nx, ny=K.seg(4, 2), name="sheet")
    ph = rnd.uniform(0, 6)
    amp = 0.012 if corrugated else 0.0
    p.displace(lambda co: (co.x, co.y, 0.18 * math.sin(co.x * 2.2 + ph) * (co.y / h + 0.5) ** 2 + 0.06 * math.sin(co.y * 5 + ph)
                           + amp * math.sin(co.x * 2 * math.pi / 0.076)))
    back = p.copy()
    bmesh.ops.reverse_faces(back.bm, faces=back.bm.faces)
    back.move(0, 0, -0.003)
    for q in (p, back):
        q.rot(x=rnd.uniform(-20, 20), y=rnd.uniform(-15, 15), z=rnd.uniform(0, 180)).move(*at)


def _cable_tangle(rnd, at, n=3):
    x, y, z = at
    for k in range(n):
        pts = []
        a0 = rnd.uniform(0, math.tau)
        for i in range(K.seg(10, 4)):
            a = a0 + i * 0.9
            r = 0.12 + 0.08 * math.sin(i * 1.3 + k)
            pts.append((x + math.cos(a) * r + i * 0.03, y + math.sin(a) * r, z + 0.02 + 0.02 * math.sin(i * 2.1)))
        tube(pts, 0.008 + 0.003 * k, 5, "rubber", "cable")


def mound(R, h, seed, mat="gravel", at=(0, 0, 0), ry=None):
    """Soft lumpy heap (lathe dome + noise), closed at the base."""
    rnd = random.Random(seed)
    ry = R if ry is None else ry
    prof = [(R, 0.0), (R * 0.82, h * 0.22), (R * 0.58, h * 0.6), (R * 0.32, h * 0.88), (R * 0.1, h * 0.99), (0.001, h)]
    m = lathe(prof if K.LOD < 2 else [prof[0], prof[2], prof[-1]], K.seg(16, 8), mat=mat, name="mound")
    ph = [rnd.uniform(0, 6.28) for _ in range(4)]

    def fn(co):
        a = math.atan2(co.y, co.x)
        t = min(1.0, co.z / max(h, 1e-6))
        k = 1 + 0.16 * math.sin(3 * a + ph[0]) + 0.1 * math.sin(5 * a + ph[1]) + 0.06 * math.sin(9 * a + ph[2])
        dz = h * 0.12 * math.sin(4 * a + ph[3]) * math.sin(math.pi * t)
        return (co.x * k, co.y * k * ry / R, co.z + dz if co.z > 1e-4 else 0.0)
    m.displace(fn)
    m.move(*at)
    return m


def _pile_z(d, R, h):
    return max(0.0, (1 - (d / R) ** 2)) * h * 0.55


# ---------------------------------------------------------------------------------------------- builders
def rubble_pile(radius=1.2, count=12, seed=1, mats=("concrete", "concrete_dark"), rebar=3, height=0.7, fit="A"):
    """Layered rubble heap: grit mound, big chunks, slab fragments with rebar, bricks, plaster with paint, a bent
    rusted sheet, a pipe stub, a cable tangle, a dead neon tube fragment and scattered chips."""
    rnd = random.Random(seed)
    R, h = radius, height
    m0 = K.part_count()
    grit = "gravel" if mats[0] == "concrete" else "concrete_dark"
    mound(R * 0.95, h * 0.62, seed, grit)
    for i in range(2):
        a = rnd.uniform(0, math.tau)
        mound(R * 0.45, h * 0.3, seed + 5 + i, grit, at=(math.cos(a) * R * 0.6, math.sin(a) * R * 0.6, 0))
    rock((R * 1.0, R * 0.85, h * 0.75), seed + 1, cuts=16, mat=mats[0], rough=0.05).move(rnd.uniform(-0.1, 0.1) * R, 0, h * 0.42)
    # big chunks
    nb = 3 if R > 1 else 2
    for i in range(nb):
        a = rnd.uniform(0, math.tau)
        d = rnd.uniform(0.25, 0.6) * R
        s = rnd.uniform(0.35, 0.55) * R
        rock((s * 1.2, s, s * 0.7), seed * 31 + i, cuts=rnd.randint(12, 16), mat=mats[0] if i % 2 == 0 or mats[1].startswith("metal") else mats[1], rough=0.05).rot(
            x=rnd.uniform(-20, 20), z=rnd.uniform(0, 360)).move(math.cos(a) * d, math.sin(a) * d, _pile_z(d, R, h) + s * 0.25)
    # slab fragments with rebar, leaning on the mound
    for i in range(2 if R < 1.5 else 3):
        a = rnd.uniform(0, math.tau)
        d = rnd.uniform(0.2, 0.55) * R
        s = rnd.uniform(0.45, 0.7) * R
        _fragment(rnd, (s, s * 0.8, 0.14 * min(1.4, R)), seed * 7 + i, mats[0], bars=rebar if i == 0 else max(1, rebar - 1),
                  at=(math.cos(a) * d, math.sin(a) * d, _pile_z(d, R, h) + 0.1), rot=(rnd.uniform(-25, 25), rnd.uniform(-30, 30), math.degrees(a)))
    # medium chunks
    n = min(count, 13) if K.LOD < 2 else max(3, count // 3)
    for i in range(n):
        a = rnd.uniform(0, math.tau)
        d = math.sqrt(rnd.random()) * R * 0.95
        s = rnd.uniform(0.1, 0.3) * R / 1.2 + 0.05
        rock((s * rnd.uniform(1.0, 1.4), s, s * rnd.uniform(0.55, 0.85)), seed * 13 + i, cuts=rnd.randint(9, 13),
             mat=mats[0] if rnd.random() < 0.6 or mats[1].startswith("metal") else mats[1], rough=0.05).rot(x=rnd.uniform(-30, 30), y=rnd.uniform(-30, 30), z=rnd.uniform(0, 360)).move(
            math.cos(a) * d, math.sin(a) * d, _pile_z(d, R, h) + s * 0.2)
    if K.LOD < 2:
        # bricks + plaster with a painted face
        for i in range(6 if R > 1 else 4):
            a = rnd.uniform(0, math.tau)
            d = rnd.uniform(0.3, 1.0) * R
            _brick(rnd, (math.cos(a) * d, math.sin(a) * d, _pile_z(d, R, h) + 0.04), half=i % 3 == 0)
        for i in range(2):
            a = rnd.uniform(0, math.tau)
            d = rnd.uniform(0.3, 0.8) * R
            p = rock((0.3, 0.22, 0.04), seed * 3 + 70 + i, cuts=10, mat="plaster", rough=0.02, bevel=0.0)
            p.set_mat("metal_painted_green" if i else "paint_glossy_white", where=lambda f: f.normal.z > 0.6)
            p.rot(x=rnd.uniform(-20, 20), z=rnd.uniform(0, 360)).move(math.cos(a) * d, math.sin(a) * d, _pile_z(d, R, h) + 0.03)
        # bent rusted sheet, pipe stub, cable tangle, dead neon tube
        a = rnd.uniform(0, math.tau)
        _bent_sheet(rnd, 0.6 * R, 0.4 * R, (math.cos(a) * R * 0.5, math.sin(a) * R * 0.5, _pile_z(R * 0.5, R, h) + 0.1), "metal_rusted", seed)
        a = rnd.uniform(0, math.tau)
        L = 0.7 * R
        c = cyl(0.045, L, 10, axis="X", mat=mats[1] if mats[1].startswith("metal") else "metal_rusted")
        c.move(-L / 2, 0, 0).rot(y=rnd.uniform(-15, 5), z=math.degrees(a)).move(math.cos(a) * R * 0.6, math.sin(a) * R * 0.6, _pile_z(R * 0.6, R, h) + 0.05)
        a = rnd.uniform(0, math.tau)
        _cable_tangle(rnd, (math.cos(a) * R * 0.7, math.sin(a) * R * 0.7, _pile_z(R * 0.7, R, h)))
        a = rnd.uniform(0, math.tau)
        pts = [(math.cos(a) * R * 0.75 + t * 0.35, math.sin(a) * R * 0.75 + 0.1 * math.sin(t * 3), _pile_z(R * 0.75, R, h) + 0.04 + 0.05 * t) for t in (0.0, 0.4, 0.7, 1.0)]
        tube(pts, 0.012, 6, "glass", "neon_dead")
        box(0.05, 0.03, 0.03, at=pts[0], mat="black")
    if mats[1].startswith("metal") and K.LOD < 2:
        for i in range(3):
            a = rnd.uniform(0, math.tau)
            d = rnd.uniform(0.3, 0.8) * R
            pl = box(rnd.uniform(0.3, 0.6), rnd.uniform(0.2, 0.4), 0.02, mat=mats[1], bevel=0.004)
            pl.rot(x=rnd.uniform(-35, 35), y=rnd.uniform(-35, 35), z=rnd.uniform(0, 360)).move(math.cos(a) * d, math.sin(a) * d, _pile_z(d, R, h) + 0.08)
        bm_ = box(1.0 * R, 0.1, 0.16, mat=mats[1], bevel=0.005)
        bm_.rot(y=-18, z=rnd.uniform(0, 180)).move(0.1 * R, -0.2 * R, h * 0.5)
    # chips around the foot
    cm = (mats[0], "concrete") if mats[1].startswith("metal") else mats
    chips_scatter(rnd, 14 if R > 1 else 9, (-R * 1.05, R * 1.05, -R * 1.05, R * 1.05), 0.0, 0.04, 0.12, cm)
    fit_bounds(K.parts_since(m0), fit)
    return {"colliders": [K.collider_box((0, 0, height * 0.35), (radius * 1.6, radius * 1.4, height * 0.7))]}


def rubble_chunk(size=0.8, seed=5, fit="ChunkL"):
    """Single concrete chunk: one formed (flat) face, fractured faces, aggregate chips, bent rebar stubs (+X)."""
    rnd = random.Random(seed)
    m0 = K.part_count()
    c = box(size, size * 0.8, size * 0.55, mat="concrete", bevel=size * 0.02 if detail() else 0.0)
    corners = [(1, 1, 1), (-1, 1, -1), (-1, -1, 1), (1, -1, -1), (0, 1, 1), (0.3, -1, 1.1), (-1.1, 0.2, 0.9)]
    for i, (cx, cy, cz) in enumerate(corners[: (7 if detail() else 3)]):
        sc = 1.0 if i < 5 else 0.55
        k = rock((size * 0.75 * sc, size * 0.7 * sc, size * 0.6 * sc), seed * 11 + i, cuts=10, mat="concrete_dark", rough=0.06, bevel=0.0)
        k.rot(z=rnd.uniform(0, 90), x=rnd.uniform(-30, 30)).move(cx * size * 0.55, cy * size * 0.45, cz * size * 0.3)
        boolean(c, k)
    if detail():
        for i in range(2):
            rebar((size * 0.2, rnd.uniform(-0.1, 0.1) * size, 0.05 * size + i * 0.08 * size), (1, rnd.uniform(-0.4, 0.4), rnd.uniform(0.0, 0.6)), size * 0.6, 0.009, rnd)
        for i in range(3):
            s = size * rnd.uniform(0.08, 0.14)
            rock((s, s, s * 0.6), seed * 5 + i, cuts=9, mat="concrete_dark", rough=0.05, bevel=0.0).move(
                rnd.uniform(-0.7, 0.7) * size, rnd.uniform(-0.6, 0.6) * size, -size * 0.27 + s * 0.3)
    else:
        rebar((size * 0.2, 0, 0.05 * size), (1, 0, 0.3), size * 0.6, 0.009, rnd)
    fit_bounds(K.parts_since(m0), fit)
    return {"colliders": [K.collider_box((0, 0, size * 0.27), (size, size * 0.8, size * 0.55))]}


def rebar_cluster(seed=3, count=7):
    """Broken column stub with bent rebar: hooked bars, tie wire, a stirrup ring, chips at the foot."""
    rnd = random.Random(seed)
    m0 = K.part_count()
    base = rock((0.5, 0.35, 0.26), seed, cuts=14, mat="concrete", rough=0.04)
    base.move(0, 0, 0.1)
    n = count if detail() else max(3, count // 2)
    tops = []
    for i in range(n):
        st = Vector((rnd.uniform(-0.17, 0.17), rnd.uniform(-0.09, 0.09), 0.12))
        d = Vector((rnd.uniform(-0.45, 0.45), rnd.uniform(-0.2, 0.6), 1.0)).normalized()
        L = rnd.uniform(0.6, 1.25)
        side = d.cross(Vector((0, 0, 1)))
        side = side.normalized() if side.length > 0.01 else Vector((1, 0, 0))
        bend = rnd.uniform(-0.35, 0.35)
        pts = [st + d * L * (k / 5) + side * bend * L * (k / 5) ** 2 for k in range(6)]
        if i % 3 == 0 and detail():  # hooked end
            e = pts[-1]
            for k in range(1, 4):
                a = math.pi * k / 3
                pts.append(e + side * 0.05 * (1 - math.cos(a)) + d * 0.05 * math.sin(a))
        rebar([tuple(p) for p in pts], r=0.01)
        tops.append(pts[2])
    if detail():
        # stirrup ring around the bars + tie wire knots
        ring_pts = [(0.19 * math.cos(a), 0.12 * math.sin(a), 0.38) for a in (k * math.tau / 10 for k in range(10))]
        tube(ring_pts, 0.006, 4, "metal_rusted", "stirrup", closed=True)
        for p in tops[:3]:
            torus(0.02, 0.003, n_major=6, n_minor=3, mat="metal_dark").move(*p)
        chips_scatter(rnd, 6, (-0.35, 0.35, -0.25, 0.4), 0.0, 0.03, 0.08)
        for i in range(2):
            rock((0.14, 0.12, 0.1), seed + 20 + i, cuts=9, mat="concrete_dark", rough=0.05, bevel=0.0).move(rnd.uniform(-0.2, 0.2), rnd.uniform(-0.15, 0.15), 0.18)
    fit_bounds(K.parts_since(m0), "Rebar")
    return {"colliders": [K.collider_box((0, 0, 0.12), (0.5, 0.35, 0.24))]}


def _hanging_fixture(at, drop=0.45):
    """Broken ceiling light fixture dangling from its cables under a slab."""
    x, y, z = at
    for dx in (-0.25, 0.25):
        tube(catenary((x + dx, y, z), (x + dx * 0.8, y + 0.05, z - drop - (0.12 if dx > 0 else 0)), 0.03, 4), 0.005, 4, "rubber")
    f = box(0.6, 0.18, 0.06, at=(0, 0, 0), mat="metal_painted_white", bevel=0.01)
    d = box(0.56, 0.14, 0.01, at=(0, 0, -0.033), mat="glass_dark")
    for p in (f, d):
        p.rot(y=-11).move(x, y + 0.05, z - drop - 0.09)


def slab_collapsed(seed=11):
    """Fallen ceiling slab resting with one end on the ground and the other on a rubble heap (+X); fractured
    edges with rebar mesh, ceiling tile remnants and a dangling light fixture underneath."""
    rnd = random.Random(seed)
    m0 = K.part_count()
    broken_slab(5.0, 3.0, 0.35, seed, ("+x", "-y"), chips=4)
    if detail():
        # plaster ceiling finish on the underside + a duct strap
        p = K.plane(4.3, 2.4, at=(-0.2, 0.2, -0.176), mat="plaster")
        bmesh.ops.reverse_faces(p.bm, faces=p.bm.faces)
        box(0.5, 2.2, 0.12, at=(-1.2, 0.2, -0.24), mat="metal_bare", bevel=0.005)
        _hanging_fixture((0.6, -0.3, -0.18), 0.4)
    for p in K.parts_since(m0):
        p.rot(y=-18)
    m1 = K.part_count()
    _heap(rnd, 1.0, 0.9, seed + 1)
    for p in K.parts_since(m1):
        p.move(1.9, 0.1, 0)
    for p in K.parts_since(m0)[: m1 - m0]:
        p.move(0, 0, 0.95)
    chips_scatter(rnd, 12, (-2.4, 2.8, -1.9, 1.4), 0.0, 0.05, 0.16)
    fit_bounds(K.parts_since(m0), "SlabC")
    return {"colliders": [{"type": "box", "center": K.to_unity_vec((0, 0, 0.95)), "size": K.to_unity_size((4.8, 3.0, 0.35)),
                           "rotationEuler": [0, 0, -18]}, K.collider_box((1.9, 0.1, 0.4), (1.6, 1.4, 0.8))]}


def _heap(rnd, R, h, seed):
    """Support heap for the collapsed slab (chunks + grit)."""
    mound(R * 0.85, h * 0.55, seed, "gravel")
    rock((R * 1.2, R * 1.0, h), seed + 1, cuts=16, mat="concrete", rough=0.05).move(0, 0, h * 0.45)
    for i in range(6 if detail() else 2):
        a = rnd.uniform(0, math.tau)
        d = rnd.uniform(0.3, 0.8) * R
        s = rnd.uniform(0.2, 0.4)
        rock((s * 1.3, s, s * 0.7), seed * 5 + i, cuts=11, mat=rnd.choice(("concrete", "concrete_dark")), rough=0.05).move(math.cos(a) * d, math.sin(a) * d, _pile_z(d, R, h) * 0.8)
    if detail():
        _fragment(rnd, (0.7, 0.5, 0.14), seed + 9, "concrete", 3, at=(0.4, -0.4, 0.35), rot=(15, -20, 40))


def slab_broken_flat(seed=21):
    """Floor-level slab cracked into pieces with a lifted edge, exposed rebar, wet grit in the crack, chips."""
    rnd = random.Random(seed)
    m0 = K.part_count()
    m = K.part_count()
    broken_slab(2.4, 2.6, 0.3, seed, ("+x",), chips=4)
    for p in K.parts_since(m):
        p.move(-1.3, 0, 0.15)
    m = K.part_count()
    broken_slab(1.8, 2.6, 0.3, seed + 3, ("-x", "+x"), chips=3, bars=detail())
    for p in K.parts_since(m):
        p.rot(y=12).move(0.85, 0, 0.32)
    # grit + water in the gap, small pieces
    rock((0.6, 2.2, 0.12), seed + 30, cuts=16, mat="gravel", rough=0.02, bevel=0.0).move(-0.1, 0, 0.02)
    for i in range(7 if detail() else 3):
        s = rnd.uniform(0.12, 0.35)
        rock((s, s * 0.8, s * 0.5), seed + 40 + i, cuts=10, mat="concrete_dark", rough=0.05).move(rnd.uniform(-0.2, 2.0), rnd.uniform(-1.3, 1.3), s * 0.25)
    if detail():
        # painted floor marking remnant + a floor drain grate on the big piece
        box(1.6, 0.12, 0.004, at=(-1.4, 0.7, 0.3), mat="metal_painted_yellow", base=True)
        box(0.3, 0.3, 0.006, at=(-1.8, -0.6, 0.3), mat="grating", base=True)
        box(0.34, 0.34, 0.004, at=(-1.8, -0.6, 0.299), mat="metal_dark", base=True)
        chips_scatter(rnd, 8, (-0.5, 2.2, -1.3, 1.3))
    fit_bounds(K.parts_since(m0), "SlabF")
    return {"colliders": [K.collider_box((-1.3, 0, 0.15), (2.4, 2.6, 0.3)), K.collider_box((0.85, 0, 0.35), (1.8, 2.6, 0.5))]}


def scrap_metal(seed=31):
    """Scrap heap: crushed drum, bent corrugated sheets, twisted I-beam, pipes, a tyre, a smashed fan guard,
    cable tangle."""
    rnd = random.Random(seed)
    m0 = K.part_count()
    # crushed drum (ribbed, dented)
    prof = [(0.001, 0.0), (0.28, 0.0), (0.29, 0.02)]
    for z in (0.2, 0.62):
        prof += [(0.29, z), (0.3, z + 0.02), (0.29, z + 0.04)]
    prof += [(0.29, 0.85), (0.28, 0.87), (0.001, 0.87)]
    d = lathe(prof if detail() else [(0.001, 0.0), (0.28, 0.0), (0.29, 0.02), (0.29, 0.85), (0.28, 0.87), (0.001, 0.87)], 18, mat="metal_rusted")
    d.displace(lambda co: (co.x * (1 + 0.25 * math.sin(co.z * 7)), co.y * (0.7 + 0.22 * math.cos(co.x * 9)), co.z - 0.08 * max(0.0, co.x) ** 2))
    d.rot(x=90).rot(z=30).move(0, 0, 0.26)
    # bent corrugated sheets (real corrugation, double sided)
    for i in range(2):
        _bent_sheet(rnd, 1.8, 1.0, (rnd.uniform(-0.8, 0.8), rnd.uniform(-0.6, 0.6), 0.3 + i * 0.12), "corrugated", seed + i, corrugated=True)
    # twisted I-beam
    L = 2.0
    for zz, (w, hh) in ((0.0, (0.02, 0.2)), (0.09, (0.12, 0.02)), (-0.09, (0.12, 0.02))):
        b = soft_box(L, w if hh > 0.1 else 0.12, hh if hh > 0.1 else 0.02, 6 if detail() else 2, "metal_rusted",
                     lambda co, zz=zz: (co.x, co.y * math.cos(co.x * 0.4) - (co.z) * math.sin(co.x * 0.4), co.y * math.sin(co.x * 0.4) + co.z + 0.08 * co.x ** 2), base=False)
        b.move(0, 0, zz)
        b.rot(z=rnd.uniform(0, 180), x=10).move(0.2, -0.3, 0.3)
    # pipes
    for i in range(3):
        Lp = rnd.uniform(1.0, 2.0)
        c = cyl(rnd.uniform(0.04, 0.07), Lp, 10, axis="X", mat=rnd.choice(["metal_rusted", "metal_bare", "metal_dark"]))
        c.move(-Lp / 2, 0, 0).rot(z=rnd.uniform(0, 180), y=rnd.uniform(-8, 8)).move(rnd.uniform(-0.6, 0.6), rnd.uniform(-0.6, 0.6), 0.08)
    # tyre leaning on the drum
    if K.LOD < 2:
        t = torus(0.27, 0.09, n_major=K.seg(20, 10), n_minor=K.seg(8, 4), mat="rubber")
        t.rot(x=70).rot(z=-20).move(-0.7, 0.35, 0.3)
        cyl(0.18, 0.12, 12, at=(0, 0, -0.06), mat="metal_dark").rot(x=70).rot(z=-20).move(-0.7, 0.35, 0.3)
    if detail():
        # smashed fan guard + cable tangle
        for rr in (0.12, 0.22):
            tq = torus(rr, 0.005, n_major=14, n_minor=3, mat="metal_dark")
            tq.displace(lambda co: (co.x, co.y, co.z + 0.06 * math.sin(co.x * 8)))
            tq.rot(x=15).move(0.75, 0.3, 0.12)
        _cable_tangle(rnd, (0.4, 0.55, 0.05), 3)
    fit_bounds(K.parts_since(m0), "Scrap")
    return {"colliders": [K.collider_box((0, 0, 0.3), (2.2, 2.0, 0.6))]}


ASSETS = {
    "Debris_Pile_A": dict(fn=rubble_pile, kw={"radius": 1.2, "count": 12, "seed": 1, "fit": "A"}, cat="debris", zones=["plaza", "metro", "rooftops", "core"],
                          notes="Concrete rubble pile ~2.6 m wide: grit mound, big chunks, slab fragments with rebar, bricks, painted plaster, bent "
                                "rusted sheet, pipe stub, cable tangle, dead neon tube, chips."),
    "Debris_Pile_B": dict(fn=rubble_pile, kw={"radius": 2.0, "count": 18, "seed": 2, "height": 1.0, "rebar": 5, "fit": "B"}, cat="debris", zones=["plaza", "metro"],
                          notes="Large rubble heap ~4.5 m wide (same dressing as Debris_Pile_A)."),
    "Debris_Pile_C": dict(fn=rubble_pile, kw={"radius": 0.7, "count": 7, "seed": 3, "height": 0.4, "rebar": 1, "fit": "C"}, cat="debris",
                          zones=["plaza", "metro", "vault", "facility"], notes="Small rubble scatter ~1.5 m."),
    "Debris_Pile_Dark": dict(fn=rubble_pile, kw={"radius": 1.2, "count": 12, "seed": 4, "mats": ("concrete_dark", "metal_dark"), "fit": "Dark"}, cat="debris",
                             zones=["core", "vault"], notes="Dark concrete + metal debris for the vault / core."),
    "Rubble_Chunk_L": dict(fn=rubble_chunk, kw={"size": 0.9, "seed": 5, "fit": "ChunkL"}, cat="debris", zones=["plaza", "metro", "core"],
                           notes="Single large concrete chunk: formed top face, fractured sides, bent rebar stubs (Unity -X)."),
    "Rubble_Chunk_S": dict(fn=rubble_chunk, kw={"size": 0.4, "seed": 6, "fit": "ChunkS"}, cat="debris", zones=["plaza", "metro", "core", "vault"], notes="Small concrete chunk."),
    "Rebar_Cluster": dict(fn=rebar_cluster, cat="debris", zones=["plaza", "metro"],
                          notes="Bent and hooked rebar out of a broken concrete stub, stirrup ring, tie wire, chips."),
    "Slab_Collapsed": dict(fn=slab_collapsed, cat="debris", zones=["metro", "plaza", "facility"],
                           notes="5 x 3 x 0.35 m fallen ceiling slab, broken edges with exposed rebar mesh, plaster underside, dangling light fixture, one "
                                 "end on a rubble heap (+X Blender = Unity -X)."),
    "Slab_Broken_Flat": dict(fn=slab_broken_flat, cat="debris", zones=["plaza", "rooftops"],
                             notes="Cracked floor slab pieces with a lifted edge, rebar, grit in the crack, floor drain and paint-line remnants."),
    "Scrap_Metal": dict(fn=scrap_metal, cat="debris", zones=["plaza", "metro", "rooftops"],
                        notes="Crushed drum, corrugated sheets, twisted I-beam, pipes, a tyre, smashed fan guard, cables."),
}
