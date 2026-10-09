"""Modular building kit on a 4 m grid: walls (straight / door / window / half), floors, ceilings, stairs, ramps,
pillars, platform edges, facades and complete background buildings.

Wall modules: length along X (centred), thickness along Y (centred on y=0), height 4 m from z=0.
Floors: top surface at z=0 (pivot top-centre). Ceilings: underside at z=0 (pivot bottom-centre).
Stairs / ramps: pivot at the FOOT (front edge of the first step, floor level, centred); they ascend toward -Y
(Unity +Z).
"""
import math
import random

import envkit as K
from envkit import box, cyl, lathe, tube, beam, extrude, rock, boolean, inset, faces_where, detail

STYLES = {
    # name: (wall material, skirting material, skirting height, top trim material or None)
    "Concrete": ("concrete", "concrete_dark", 0.15, None),
    "Lab": ("lab_panel", "metal_dark", 0.12, "metal_dark"),
    "Metro": ("metro_tile", "concrete_dark", 0.25, None),
    "Vault": ("metal_plate", "metal_dark", 0.2, "emit_strip_violet"),
    "Plaster": ("plaster", "concrete_dark", 0.3, None),
}
WALL_H, WALL_T, MOD = 4.0, 0.3, 4.0


def _skirting(L, style, z0=0.0, openings=()):
    mat, sk, skh, top = STYLES[style]
    for sy in (-1, 1):
        segs = [(-L / 2, L / 2)]
        for (a, b) in openings:
            segs = [(s0, min(s1, a)) for (s0, s1) in segs if s0 < a] + [(max(s0, b), s1) for (s0, s1) in segs if s1 > b]
        for (s0, s1) in segs:
            if s1 - s0 > 0.02:
                box(s1 - s0, 0.02, skh, at=((s0 + s1) / 2, sy * (WALL_T / 2 + 0.01), z0), mat=sk, base=True)
        if top and detail():
            box(L, 0.02, 0.05 if top.startswith("emit") else 0.06, at=(0, sy * (WALL_T / 2 + 0.01), WALL_H - 0.3), mat=top, base=True)


def wall_straight(style="Concrete", L=MOD, H=WALL_H):
    mat = STYLES[style][0]
    box(L, WALL_T, H, mat=mat, base=True)
    _skirting(L, style)
    return {"colliders": [K.collider_box((0, 0, H / 2), (L, WALL_T, H))]}


def _frame(w, h, z0, depth, mat="metal_dark", t=0.08):
    for sx in (-1, 1):
        box(t, depth, h + t, at=(sx * (w / 2 + t / 2), 0, z0), mat=mat, base=True, bevel=0.008)
    box(w + 2 * t, depth, t, at=(0, 0, z0 + h), mat=mat, base=True, bevel=0.008)


def wall_door(style="Concrete", L=MOD, H=WALL_H, dw=1.6, dh=2.6):
    mat = STYLES[style][0]
    w = box(L, WALL_T, H, mat=mat, base=True)
    boolean(w, box(dw, WALL_T + 0.2, dh + 0.1, at=(0, 0, -0.1), mat=mat, base=True))
    _frame(dw, dh, 0.0, WALL_T + 0.04)
    _skirting(L, style, openings=[(-dw / 2 - 0.08, dw / 2 + 0.08)])
    side = (L - dw) / 2
    return {"colliders": [K.collider_box((sx * (dw / 2 + side / 2), 0, H / 2), (side, WALL_T, H)) for sx in (-1, 1)] +
            [K.collider_box((0, 0, (dh + H) / 2), (dw, WALL_T, H - dh))], "opening": {"width": dw, "height": dh}}


def wall_window(style="Concrete", L=MOD, H=WALL_H, ww=2.4, wh=1.4, sill=1.0, glass="glass"):
    mat = STYLES[style][0]
    w = box(L, WALL_T, H, mat=mat, base=True)
    boolean(w, box(ww, WALL_T + 0.2, wh, at=(0, 0, sill), mat=mat, base=True))
    _frame(ww, wh, sill, 0.1)
    box(ww + 0.16, 0.1, 0.08, at=(0, 0, sill - 0.08), mat="metal_dark", base=True)
    box(ww + 0.2, WALL_T + 0.12, 0.05, at=(0, 0, sill - 0.05), mat="concrete" if style != "Lab" else "metal_bare", base=True, bevel=0.01)
    box(0.05, 0.06, wh, at=(0, 0, sill), mat="metal_dark", base=True)
    box(ww, 0.012, wh, at=(0, 0, sill), mat=glass, base=True)
    _skirting(L, style)
    return {"colliders": [K.collider_box((0, 0, H / 2), (L, WALL_T, H))], "opening": {"width": ww, "height": wh, "sill": sill}}


def floor_tile(mat="concrete", L=MOD, T=0.3):
    box(L, L, T, at=(0, 0, -T), mat=mat, base=True)
    return {"colliders": [K.collider_box((0, 0, -T / 2), (L, L, T))]}


def floor_grate(L=MOD):
    """Vault/industrial floor: steel frame, four grating panels, dark sub-floor 0.35 m below with pipes."""
    for sx in (-1, 1):
        box(0.1, L, 0.12, at=(sx * (L / 2 - 0.05), 0, -0.12), mat="metal_dark", base=True, bevel=0.008)
        box(L, 0.1, 0.12, at=(0, sx * (L / 2 - 0.05), -0.12), mat="metal_dark", base=True, bevel=0.008)
    box(L - 0.2, 0.08, 0.1, at=(0, 0, -0.1), mat="metal_dark", base=True)
    box(0.08, L - 0.2, 0.1, at=(0, 0, -0.1), mat="metal_dark", base=True)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(L / 2 - 0.14, L / 2 - 0.14, 0.03, at=(sx * L / 4, sy * L / 4, -0.03), mat="grating", base=True)
    box(L, L, 0.1, at=(0, 0, -0.55), mat="metal_plate", base=True)
    if detail():
        for x in (-1.1, 0.4, 1.3):
            cyl(0.08, L, 10, at=(x, -L / 2, -0.36), axis="Y", mat="metal_rusted")
        cyl(0.04, L, 8, at=(-0.5, -L / 2, -0.4), axis="Y", mat="rubber")
    return {"colliders": [K.collider_box((0, 0, -0.06), (L, L, 0.12))]}


def ceiling_tile(mat="lab_panel", light="emit_panel_white", L=MOD, T=0.3):
    c = box(L, L, T, at=(0, 0, 0), mat=mat, base=True)
    if light:
        for sx in (-1, 1):
            box(1.6, 0.6, 0.04, at=(sx * 1.0, 0, -0.02), mat="metal_dark", base=True)
            box(1.5, 0.5, 0.01, at=(sx * 1.0, 0, -0.025), mat=light, base=True)
    if detail():
        for k in (-1, 1):
            box(L, 0.012, 0.004, at=(0, k * 1.0, -0.002), mat="metal_dark", base=True)
    return {"colliders": [K.collider_box((0, 0, T / 2), (L, L, T))], "lights": [K.to_unity_vec((sx * 1.0, 0, -0.1)) for sx in (-1, 1)] if light else []}


def stairs(W=3.0, rise=4.0, run=6.6, steps=22, mat="concrete", side_walls=True, nosing="metal_painted_yellow"):
    r, g = rise / steps, run / steps
    for i in range(steps):
        box(W, g, r * (i + 1), at=(0, -(i + 0.5) * g, 0), mat=mat, base=True, bevel=0.006 if i % 1 == 0 else 0)
        if nosing and detail():
            box(W - 0.1, 0.05, 0.012, at=(0, -i * g - 0.03, r * (i + 1)), mat=nosing, base=True)
    if side_walls:
        for sx in (-1, 1):
            sw = extrude([(0.0, 0.0), (0.0, 0.95), (-run, rise + 0.95), (-run, rise)], 0.2, plane="YZ", mat=mat)
            sw.move(sx * (W / 2 + 0.1), 0, 0)
            tube([(sx * (W / 2 + 0.1), 0.0, 1.0), (sx * (W / 2 + 0.1), -run, rise + 1.0)], 0.03, 8, "metal_dark")
    ang = math.degrees(math.atan2(rise, run))
    L = math.hypot(rise, run)
    return {"colliders": [{"type": "box", "center": K.to_unity_vec((0, -run / 2, rise / 2 - 0.1)), "size": [W, 0.2, round(L, 3)], "rotationEuler": [-round(ang, 2), 0, 0],
                           "note": "ramp collider for smooth traversal"}], "rise": rise, "run": run, "steps": steps}


def stairs_metal(W=1.2, rise=2.0, steps=11, run=None):
    run = run or steps * 0.27
    r, g = rise / steps, run / steps
    ang = math.atan2(rise, run)
    for sx in (-1, 1):
        beam((sx * (W / 2 + 0.03), 0.05, -0.05), (sx * (W / 2 + 0.03), -run - 0.05, rise - 0.02), 0.22, 0.04, mat="metal_dark", up=(1, 0, 0))
        for i in range(0, steps + 1, 3):
            y, z = -i * g, i * r
            cyl(0.02, 1.0, 6, at=(sx * (W / 2 + 0.03), y, z), mat="metal_dark")
        tube([(sx * (W / 2 + 0.03), 0.0, 1.0), (sx * (W / 2 + 0.03), -run, rise + 1.0)], 0.022, 8, "metal_painted_yellow")
    for i in range(steps):
        box(W, g + 0.03, 0.04, at=(0, -(i + 0.5) * g, r * (i + 1) - 0.04), mat="grating", base=True)
        box(W, 0.035, 0.05, at=(0, -i * g - 0.02, r * (i + 1) - 0.05), mat="metal_dark", base=True)
    return {"colliders": [{"type": "box", "center": K.to_unity_vec((0, -run / 2, rise / 2 - 0.1)), "size": [W, 0.2, round(math.hypot(rise, run), 3)],
                           "rotationEuler": [-round(math.degrees(ang), 2), 0, 0]}], "rise": rise, "run": round(run, 3)}


def ramp(W=3.0, Lr=4.0, rise=1.0, mat="concrete"):
    extrude([(0.0, 0.0), (-Lr, 0.0), (-Lr, rise), (0.0, 0.02)][::-1], W, plane="YZ", mat=mat, bevel=0.01)
    if detail():
        for sx in (-1, 1):
            box(0.12, Lr, 0.01, at=(sx * (W / 2 - 0.1), -Lr / 2, 0), mat="metal_painted_yellow").rot_about((0, 0, 0), x=-math.degrees(math.atan2(rise, Lr))).move(0, 0, 0.012)
    ang = math.degrees(math.atan2(rise, Lr))
    return {"colliders": "mesh", "rise": rise, "length": Lr, "angleDeg": round(ang, 2)}


def pillar(H=4.0, w=0.8, mat="concrete", cap=True, round_=False, band=None):
    if round_:
        cyl(w / 2, H, 24, mat=mat)
    else:
        p = box(w, w, H, mat=mat, base=True, bevel=0.03, bseg=1)
    if cap:
        box(w + 0.16, w + 0.16, 0.25, mat=mat if mat != "metro_tile" else "concrete_dark", base=True, bevel=0.02)
        box(w + 0.12, w + 0.12, 0.2, at=(0, 0, H - 0.2), mat=mat if mat != "metro_tile" else "concrete_dark", base=True, bevel=0.02)
    if band and detail():
        for z in (1.2, H - 0.8):
            box(w + 0.04, w + 0.04, 0.1, at=(0, 0, z), mat=band, base=True)
    return {"colliders": [K.collider_box((0, 0, H / 2), (w + 0.16, w + 0.16, H))]}


def platform_edge(L=MOD, depth=2.0, pit=1.3):
    """Metro platform edge: platform top at z=0, edge line at y=0, track pit toward -Y (Unity +Z)."""
    box(L, depth, 0.3, at=(0, depth / 2, -0.3), mat="concrete", base=True)
    box(L, 0.35, 0.12, at=(0, -0.02, -0.12), mat="concrete", base=True, bevel=0.015)
    box(L, 0.4, 0.006, at=(0, 0.32, 0), mat="metal_painted_yellow", base=True)
    if detail():
        for i in range(int(L / 0.1)):
            box(0.03, 0.36, 0.008, at=(-L / 2 + 0.05 + i * 0.1, 0.32, 0.004), mat="metal_painted_yellow", base=True)
    box(L, 0.4, pit - 0.25, at=(0, 0.35, -pit), mat="concrete_dark", base=True)
    box(L, 0.15, 0.3, at=(0, 0.1, -0.42), mat="concrete_dark", base=True)
    if detail():
        for x in (-L / 2 + 0.5, L / 2 - 0.5):
            box(0.15, 0.3, pit - 0.45, at=(x, 0.0, -pit), mat="concrete_dark", base=True)
        cyl(0.05, L, 8, at=(-L / 2, 0.12, -1.0), axis="X", mat="rubber")
    return {"colliders": [K.collider_box((0, depth / 2 - 0.02, -0.15), (L, depth + 0.04, 0.3)), K.collider_box((0, 0.35, -pit / 2 - 0.1), (L, 0.4, pit - 0.2))]}


# ============================================================================================== facades & buildings
def facade(style="plaster", kind="window", L=MOD, H=3.4, lit=False, broken=False, seed=1):
    """Exterior facade module (one floor). Outer face toward -Y. kind: window | plain | shop."""
    rnd = random.Random(seed)
    T = 0.3
    w = box(L, T, H, mat=style, base=True)
    if kind == "window":
        ww, wh, sill = 1.6, 1.6, 0.9
        boolean(w, box(ww, T + 0.2, wh, at=(0, 0, sill), mat=style, base=True))
        gm = "black" if broken else ("window_lit_warm" if lit else "glass_dark")
        box(ww, 0.02, wh, at=(0, 0.04, sill), mat=gm, base=True)
        _frame(ww, wh, sill, 0.08)
        box(ww + 0.3, 0.12, 0.08, at=(0, -T / 2 - 0.04, sill - 0.08), mat="concrete", base=True, bevel=0.01)
        box(ww + 0.2, 0.06, 0.18, at=(0, -T / 2 - 0.01, sill + wh), mat="concrete_dark", base=True)
        if detail() and not broken and not lit and rnd.random() < 0.5:
            box(ww - 0.1, 0.02, 0.5, at=(0, 0.02, sill + wh - 0.5), mat="metal_painted_white", base=True)
    elif kind == "shop":
        ww, wh = 3.2, 2.8
        boolean(w, box(ww, T + 0.2, wh, at=(0, 0, -0.05), mat=style, base=True))
        box(ww, 0.08, 2.0, at=(0, 0.0, 0.0), mat="corrugated" if not broken else "metal_rusted", base=True)
        box(ww, 0.04, 0.75, at=(0, 0.06, 2.0), mat="black" if broken else "glass_dark", base=True)
        box(ww + 0.1, 0.3, 0.12, at=(0, -0.1, 2.0), mat="metal_dark", base=True)
        _frame(ww, wh, 0.0, 0.1)
        box(ww + 0.4, 0.5, 0.35, at=(0, -0.35, wh + 0.05), mat="metal_dark", base=True, bevel=0.02)
    box(L, 0.12, 0.18, at=(0, -T / 2 - 0.04, H - 0.18), mat="concrete_dark", base=True)
    return {"colliders": [K.collider_box((0, 0, H / 2), (L, T, H))]}


def _grid_face(mat, xs, zs, pt):
    import bmesh
    p = K._new(mat, "facade")
    bm = p.bm
    vs = [[bm.verts.new(pt(x, z)) for z in zs] for x in xs]
    cells = {}
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            cells[(i, j)] = bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
    return p, cells


def building_block(W=12.0, D=12.0, floors=5, fh=3.4, mat="plaster", seed=3, lit=0.08, broken=0.12, top=None, neon=0.25):
    """Complete background building (skyline filler, scaled by the zone code): four facades with recessed windows
    (warm / cool / neon-tinted lit rooms, some broken), lit ground-floor shopfronts with LED ad fascias, floor
    ledges, flat neon glyph signs and AC boxes on the facades, LED corner strips, parapet and roof clutter.
    Everything stays inside the original envelope (ledges +0.15 m, roof clutter up to `top`). Pivot base centre."""
    import bmesh
    import assets_facade as F
    rnd = random.Random(seed)
    H = floors * fh + 0.6
    zs = [0.0, 0.4, 2.8]
    for k in range(1, floors):
        zs += [k * fh + 0.9, k * fh + 0.9 + 1.6]
    zs.append(H)
    zs = sorted(set(round(z, 4) for z in zs))
    neon_mats = ["emit_neon_magenta", "emit_neon_cyan", "emit_neon_pink", "emit_neon_violet", "emit_neon_blue", "emit_neon_yellow"]
    faces = [(W, lambda a, z: (a, -D / 2, z), 0), (W, lambda a, z: (-a, D / 2, z), 1), (D, lambda a, z: (W / 2, a, z), 2), (D, lambda a, z: (-W / 2, -a, z), 3)]
    for span, pt, fi in faces:
        n = max(1, int(span / 2.6))
        pitch = span / n
        xs = [-span / 2]
        for i in range(n):
            c = -span / 2 + pitch * (i + 0.5)
            xs += [c - 0.7, c + 0.7]
        xs.append(span / 2)
        p, cells = _grid_face(mat, xs, zs, pt)
        p.bm.normal_update()
        wins, shut = [], []
        for (i, j), f in cells.items():
            if i % 2 == 0:
                continue
            z0, z1 = zs[j], zs[j + 1]
            if abs(z0 - 0.4) < 1e-3 and abs(z1 - 2.8) < 1e-3:
                shut.append(f)
            elif abs((z1 - z0) - 1.6) < 1e-3:
                wins.append(f)
        bmesh.ops.inset_individual(p.bm, faces=wins, thickness=0.07, depth=-0.16, use_even_offset=True)
        bmesh.ops.inset_individual(p.bm, faces=shut, thickness=0.08, depth=-0.12, use_even_offset=True)
        for f in wins:
            r = rnd.random()
            if r < lit:
                m = "window_lit_warm"
            elif r < lit * 1.6:
                m = "window_lit_cool"
            elif r < lit * 1.6 + 0.025:
                m = rnd.choice(neon_mats[:3])  # neon-lit room
            elif r > 1 - broken:
                m = "black"
            else:
                m = "glass_dark"
            f[p.mats] = p.slot(m)
        for f in shut:
            r = rnd.random()
            f[p.mats] = p.slot("window_lit_warm" if r < 0.45 else ("corrugated" if r < 0.8 else "metal_rusted"))
        # facade dressing inside the 0.15 m ledge envelope
        if K.LOD == 0:
            for i in range(n):
                c = -span / 2 + pitch * (i + 0.5)
                for k in range(1, floors):
                    if rnd.random() < 0.22:  # AC box under a window
                        a0, z0 = c + rnd.choice((-0.35, 0.35)), k * fh + 0.25
                        _face_box(pt, fi, a0, z0, 0.55, 0.12, 0.42, "metal_painted_white")
            # ground-floor fascia LED ad strips over every shop bay
            for i in range(n):
                c = -span / 2 + pitch * (i + 0.5)
                _face_box(pt, fi, c, 2.82, 1.5, 0.05, 0.36, rnd.choice(["screen_ad_a", "screen_ad_b", "screen_ad_c"]))
        if K.LOD < 2 and rnd.random() < neon * 4:
            # a flat neon glyph column between two window bays (tubes 6 cm proud, inside the ledge envelope)
            col = rnd.choice(neon_mats)
            gi = rnd.randrange(max(1, n - 1))
            cx = -span / 2 + pitch * (gi + 1)
            z0 = fh * rnd.randint(1, max(1, floors - 3)) + 0.4
            cnt = min(4, floors - 1)
            rng = random.Random(seed * 7 + fi)
            for g in range(cnt):
                for (a_, b_) in F.glyph_segments(rng):
                    pa = (cx - 0.3 + a_[0] * 0.6, z0 + (cnt - 1 - g) * 0.85 + a_[1] * 0.7)
                    pb = (cx - 0.3 + b_[0] * 0.6, z0 + (cnt - 1 - g) * 0.85 + b_[1] * 0.7)
                    if abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) > 0.03:
                        _face_tube(pt, fi, pa, pb, 0.022, col)
    box(W, D, 0.3, at=(0, 0, H - 0.3), mat="concrete_dark", base=True)
    for k in range(1, floors):
        box(W + 0.3, D + 0.3, 0.16, at=(0, 0, k * fh), mat="concrete_dark", base=True)
    box(W + 0.3, D + 0.3, 0.25, at=(0, 0, 3.0), mat="concrete_dark", base=True)
    for sx in (-1, 1):
        box(0.25, D, 0.9, at=(sx * (W / 2 - 0.125), 0, H), mat=mat, base=True)
        box(W - 0.5, 0.25, 0.9, at=(0, sx * (D / 2 - 0.125), H), mat=mat, base=True)
    box(W - 0.5, D - 0.5, 0.02, at=(0, 0, H), mat="concrete_wet", base=True)
    if K.LOD < 2:
        strip = rnd.choice(["emit_strip_magenta", "emit_strip_cyan", "emit_strip_violet"])
        for sx in (-1, 1):
            for sy in (-1, 1):
                box(0.06, 0.06, H - 3.3, at=(sx * (W / 2 + 0.11), sy * (D / 2 + 0.11), 3.3), mat=strip, base=True)
    # roof clutter: everything below `top`; one AC/vent block reaches exactly `top` (keeps the original bounds)
    t = (top - H) if top else 1.0
    if detail():
        for i in range(rnd.randint(2, 4)):
            hh = rnd.uniform(0.5, max(0.55, t * 0.85))
            box(rnd.uniform(1.0, 2.5), rnd.uniform(1.0, 2.0), hh, at=(rnd.uniform(-W / 3, W / 3), rnd.uniform(-D / 3, D / 3), H), mat="metal_bare", base=True, bevel=0.03)
        cyl(0.05, t - 0.15, 6, at=(W / 2 - 1.0, D / 2 - 1.0, H), mat="metal_dark")
        cyl(0.06, 0.15, 6, at=(W / 2 - 1.0, D / 2 - 1.0, H + t - 0.15), mat="emit_red")
    box(1.6, 1.1, t, at=(-W / 4, D / 4, H), mat="metal_painted_white", base=True, bevel=0.02)
    if K.LOD < 2:
        cyl(0.38, 0.02, K.seg(16), at=(-W / 4, D / 4, H + t - 0.0), mat="black")
    return {"colliders": [K.collider_box((0, 0, H / 2), (W, D, H))], "roofHeight": round(H, 3), "floorHeight": fh}


def _face_box(pt, fi, a, z, w, d, h, mat):
    """Box on a building_block face: centred at face coordinate a (along the face), bottom z, depth d outward."""
    from mathutils import Vector
    o = Vector(pt(a, z))
    o2 = Vector(pt(a + 1.0, z))
    t = (o2 - o).normalized()
    nrm = Vector((t.y, -t.x, 0.0))  # outward for the face winding used above
    c = o + nrm * (d / 2)
    p = box(w, d, h, mat=mat, base=True)
    ang = math.degrees(math.atan2(t.y, t.x))
    p.rot(z=ang).move(c.x, c.y, z)
    return p


def _face_tube(pt, fi, pa, pb, off, mat):
    from mathutils import Vector
    o = Vector(pt(0.0, 0.0))
    t = (Vector(pt(1.0, 0.0)) - o).normalized()
    nrm = Vector((t.y, -t.x, 0.0))
    A = Vector(pt(pa[0], pa[1])) + nrm * off
    Bv = Vector(pt(pb[0], pb[1])) + nrm * off
    tube([tuple(A), tuple(Bv)], 0.012, K.seg(6, 4), mat)


ASSETS = {}
for st in STYLES:
    ASSETS[f"Wall_{st}_Straight_4m"] = dict(fn=wall_straight, kw={"style": st}, cat="structure", zones=[], notes=f"{st} wall module 4 x 4 m, 0.3 thick, skirting both faces.")
    ASSETS[f"Wall_{st}_Straight_2m"] = dict(fn=wall_straight, kw={"style": st, "L": 2.0}, cat="structure", zones=[], notes=f"{st} half module 2 x 4 m.")
    ASSETS[f"Wall_{st}_Door_4m"] = dict(fn=wall_door, kw={"style": st}, cat="structure", zones=[], notes=f"{st} wall with a 1.6 x 2.6 m door opening and steel frame.")
    ASSETS[f"Wall_{st}_Window_4m"] = dict(fn=wall_window, kw={"style": st}, cat="structure", zones=[], notes=f"{st} wall with a 2.4 x 1.4 m glazed window (sill 1.0 m).")
for st, zones in (("Concrete", ["plaza", "metro", "rooftops"]), ("Lab", ["facility"]), ("Metro", ["metro"]), ("Vault", ["vault", "core"]), ("Plaster", ["plaza", "rooftops", "vault"])):
    for k in list(ASSETS):
        if k.startswith(f"Wall_{st}_"):
            ASSETS[k]["zones"] = zones
ASSETS.update({
    "Wall_Lab_Door_Wide": dict(fn=wall_door, kw={"style": "Lab", "dw": 4.0 - 0.6, "dh": 3.2}, cat="structure", zones=["facility"], notes="Lab wall with a 3.4 x 3.2 opening (atrium/lab doors)."),
    "Floor_Concrete_4m": dict(fn=floor_tile, kw={"mat": "concrete"}, cat="structure", zones=["plaza", "metro", "rooftops"], pivot="top-centre", notes="4 x 4 x 0.3 floor slab, top at 0."),
    "Floor_ConcreteWet_4m": dict(fn=floor_tile, kw={"mat": "concrete_wet"}, cat="structure", zones=["plaza", "rooftops"], pivot="top-centre", notes="Wet concrete floor slab (puddles)."),
    "Floor_Paving_4m": dict(fn=floor_tile, kw={"mat": "paving"}, cat="structure", zones=["plaza"], pivot="top-centre", notes="Plaza paving slab module."),
    "Floor_Asphalt_4m": dict(fn=floor_tile, kw={"mat": "asphalt"}, cat="structure", zones=["plaza"], pivot="top-centre", notes="Road surface module."),
    "Floor_Lab_4m": dict(fn=floor_tile, kw={"mat": "lab_floor"}, cat="structure", zones=["facility"], pivot="top-centre", notes="Lab vinyl floor module."),
    "Floor_MetroTile_4m": dict(fn=floor_tile, kw={"mat": "metro_tile"}, cat="structure", zones=["metro"], pivot="top-centre", notes="Tiled corridor floor (metro entry)."),
    "Floor_Grate_4m": dict(fn=floor_grate, cat="structure", zones=["vault", "core"], pivot="top-centre", notes="Steel frame with alpha-cut grating panels over a dark sub-floor with pipes."),
    "Ceiling_Lab_4m": dict(fn=ceiling_tile, cat="structure", zones=["facility"], pivot="bottom-centre", notes="Lab ceiling module with two 1.5 x 0.5 emissive panels (emit_panel_white). 'lights' = suggested light anchors."),
    "Ceiling_Concrete_4m": dict(fn=ceiling_tile, kw={"mat": "concrete_dark", "light": None}, cat="structure", zones=["metro", "plaza"], pivot="bottom-centre", notes="Plain concrete ceiling slab."),
    "Ceiling_Metro_4m": dict(fn=ceiling_tile, kw={"mat": "concrete_dark", "light": "emit_panel_warm"}, cat="structure", zones=["metro"], pivot="bottom-centre", notes="Concrete ceiling with warm light panels."),
    "Stairs_Concrete_3m": dict(fn=stairs, cat="structure", zones=["plaza", "metro", "facility"], pivot="foot",
                               notes="3 m wide, 4 m rise over 6.6 m (22 steps, 182/300 mm), side walls with handrails, yellow nosings. Ascends toward +Z."),
    "Stairs_Concrete_8m": dict(fn=stairs, kw={"W": 8.0, "run": 10.0, "steps": 26, "side_walls": False}, cat="structure", zones=["metro", "plaza"], pivot="foot",
                               notes="8 m wide station stairs: 4 m rise over 10 m (26 steps) matching the prototype metro stairs."),
    "Stairs_Metal_2m": dict(fn=stairs_metal, cat="structure", zones=["vault", "rooftops", "metro"], pivot="foot",
                            notes="Steel stairs 1.2 m wide, 2 m rise, grating treads, stringers, yellow handrails."),
    "Stairs_Metal_3m": dict(fn=stairs_metal, kw={"W": 2.6, "rise": 3.0, "steps": 16}, cat="structure", zones=["vault"], pivot="foot",
                            notes="Wide steel stairs 2.6 m, 3 m rise (vault ledge)."),
    "Ramp_Concrete": dict(fn=ramp, cat="structure", zones=["plaza", "metro", "rooftops"], pivot="foot", notes="3 m wide wedge ramp, 1 m rise over 4 m."),
    "Pillar_Concrete_4m": dict(fn=pillar, cat="structure", zones=["plaza", "metro", "facility"], notes="0.8 m square column 4 m with base and capital."),
    "Pillar_Concrete_10m": dict(fn=pillar, kw={"H": 10.0}, cat="structure", zones=["facility"], notes="10 m atrium column."),
    "Pillar_Metro_4m": dict(fn=pillar, kw={"H": 4.4, "mat": "metro_tile", "band": "metal_painted_yellow"}, cat="structure", zones=["metro"], notes="Tiled platform column 4.4 m with yellow safety bands."),
    "Pillar_Round_4m": dict(fn=pillar, kw={"round_": True, "w": 0.7}, cat="structure", zones=["plaza", "facility"], notes="Round concrete column 0.7 m dia."),
    "Pillar_Vault_4m": dict(fn=pillar, kw={"w": 1.4, "mat": "concrete_dark", "band": "metal_dark"}, cat="structure", zones=["vault"], notes="1.4 m square heavy column (guardian gallery)."),
    "Platform_Edge_4m": dict(fn=platform_edge, cat="metro", zones=["metro"], pivot="edge-top",
                             notes="Metro platform edge module: top at y=0, edge line at z=0, pit (1.3 m) toward +Z. Tactile yellow strip, refuge recess, cable."),
    "Building_Block_A": dict(fn=building_block, kw={"W": 12.0, "D": 12.0, "floors": 5, "mat": "plaster", "seed": 3, "top": 18.726}, cat="structure", zones=["plaza", "rooftops"],
                             notes="Background building 12 x 12 x ~17.6 m, inset windows (some lit / broken), ledges, parapet, roof clutter."),
    "Building_Block_B": dict(fn=building_block, kw={"W": 20.0, "D": 14.0, "floors": 7, "mat": "concrete", "seed": 4, "top": 25.375}, cat="structure", zones=["plaza", "rooftops"], notes="20 x 14 x ~24.4 m concrete block."),
    "Building_Block_C": dict(fn=building_block, kw={"W": 10.0, "D": 16.0, "floors": 9, "mat": "brick", "seed": 5, "lit": 0.12, "top": 32.694}, cat="structure", zones=["plaza", "rooftops"], notes="Tall brick block ~31 m."),
    "Building_Block_D": dict(fn=building_block, kw={"W": 24.0, "D": 22.0, "floors": 4, "mat": "concrete_dark", "seed": 6, "top": 15.186}, cat="structure", zones=["plaza"], notes="Low wide civic block."),
})


# ============================================================================================== elevated rail, gates, door leaves
def rail_pier(H=8.0):
    """Elevated rail pier: chamfered column, hammerhead cap with bearing plinths, neon LED collar under the cap,
    hazard-striped base, cable conduit and access hatch. Envelope 2.6 x 8.0 x 1.6 m."""
    box(1.2, 1.2, H - 0.6, mat="concrete_dark", base=True, bevel=0.06, bseg=2 if K.LOD == 0 else 1)
    box(2.6, 1.6, 0.6, at=(0, 0, H - 0.6), mat="concrete_dark", base=True, bevel=0.04)
    box(1.6, 1.6, 0.25, mat="concrete", base=True, bevel=0.02)
    box(1.26, 1.26, 0.5, at=(0, 0, 0.25), mat="metal_painted_yellow", base=True, bevel=0.01)
    if K.LOD < 2:
        # LED collar ring under the cap + vertical LED slot on the street face
        box(1.24, 1.24, 0.08, at=(0, 0, H - 1.0), mat="emit_strip_magenta", base=True)
        box(1.28, 1.28, 0.05, at=(0, 0, H - 1.06), mat="metal_dark", base=True)
        box(1.28, 1.28, 0.05, at=(0, 0, H - 0.92), mat="metal_dark", base=True)
        box(0.05, 0.02, H - 2.4, at=(0, -0.61, 1.0), mat="emit_strip_cyan", base=True)
    if detail():
        for sx in (-1, 1):
            box(0.5, 0.5, 0.08, at=(sx * 0.75, 0, H), mat="metal_dark", base=True, bevel=0.01)
            box(0.4, 0.4, 0.04, at=(sx * 0.75, 0, H - 0.04), mat="rubber", base=True)
        cyl(0.06, H - 0.6, 8, at=(0.66, 0.4, 0), mat="metal_rusted")
        for z in (1.5, 3.5, 5.5):
            box(0.06, 0.16, 0.05, at=(0.63, 0.4, z), mat="metal_dark", base=True)
        box(0.5, 0.04, 0.8, at=(0, 0.62, 1.2), mat="metal_painted", base=True, bevel=0.01)
        box(0.06, 0.02, 0.06, at=(0.18, 0.645, 1.75), mat="emit_amber", base=True)
    return {"colliders": [K.collider_box((0, 0, H / 2), (1.2, 1.2, H))]}


def rail_deck(L=14.0, W=5.0):
    """Elevated rail deck span along Y (Unity Z), top of deck at z=0 (pivot top-centre): box girder with lit LED
    underside (cyan edges, magenta centre line), cable trays, drain pipes, parapets with rail, sleepers, rails,
    third-rail conductor. Envelope 5.0 x 2.725 x 14 m."""
    extrude([(-W / 2, 0.0), (W / 2, 0.0), (W / 2, -0.35), (W / 2 - 0.7, -1.2), (-W / 2 + 0.7, -1.2), (-W / 2, -0.35)], L, plane="XZ", mat="concrete_dark", bevel=0.02)
    if K.LOD < 2:
        # LED underside: two edge strips along the soffit corners + a centre line, all facing down
        for x in (-(W / 2 - 0.72), (W / 2 - 0.72)):
            box(0.05, L - 0.2, 0.012, at=(x, 0, -1.212), mat="emit_strip_cyan", base=True)
        box(0.08, L - 0.2, 0.012, at=(0, 0, -1.212), mat="emit_strip_magenta", base=True)
        for k in range(int(L / 3.5)):
            box(1.4, 0.12, 0.014, at=(0, -L / 2 + 1.75 + k * 3.5, -1.214), mat="metal_dark", base=True)
    for sx in (-1, 1):
        box(0.2, L, 0.5, at=(sx * (W / 2 - 0.1), 0, 0), mat="concrete_dark", base=True, bevel=0.02)
        if detail():
            for k in range(int(L / 2)):
                box(0.05, 0.05, 1.0, at=(sx * (W / 2 - 0.1), -L / 2 + 1 + k * 2, 0.5), mat="metal_dark", base=True)
            # cable tray hung on the girder flank
            box(0.18, L, 0.05, at=(sx * (W / 2 - 0.22), 0, -0.55), mat="metal_bare", base=True)
            for k in range(3):
                cyl(0.02, L, 6, at=(sx * (W / 2 - 0.22) + (k - 1) * 0.05, -L / 2, -0.48), axis="Y", mat="rubber")
        cyl(0.025, L, 6, at=(sx * (W / 2 - 0.1), -L / 2, 1.5), axis="Y", mat="metal_dark")
        if K.LOD < 2:
            box(0.04, L, 0.03, at=(sx * (W / 2 - 0.22), 0, 0.5), mat="emit_strip_cyan", base=True)
    for sx in (-1, 1):
        r = extrude([(x, z + 0.2) for x, z in [(-0.075, -0.172), (0.075, -0.172), (0.075, -0.16), (0.009, -0.145), (0.009, -0.05), (0.035, -0.04), (0.035, 0.0), (-0.035, 0.0), (-0.035, -0.04), (-0.009, -0.05), (-0.009, -0.145), (-0.075, -0.16)]],
                    L, plane="XZ", mat="metal_rusted")
        r.move(sx * 0.7525, 0, 0.0)
    for k in range(int(L / 0.7)):
        box(2.4, 0.22, 0.03, at=(0, -L / 2 + 0.35 + k * 0.7, 0.0), mat="concrete", base=True)
    if detail():
        box(0.08, L, 0.1, at=(1.35, 0, 0.03), mat="metal_bare", base=True)  # third rail
        for k in range(int(L / 2.8)):
            box(0.14, 0.1, 0.08, at=(1.35, -L / 2 + 1.4 + k * 2.8, 0.0), mat="plastic_dark", base=True)
    return {"colliders": [K.collider_box((0, 0, -0.6), (W, L, 1.2))], "length": L, "lights": [K.to_unity_vec((0, 0, -1.6))]}


def gate_leaf(W=12.0, H=8.6, T=0.6):
    """Facility gate leaf (slides along X)."""
    g = box(W, T, H, mat="metal_painted", base=True, bevel=0.03)
    for sy in (-1, 1):
        inset(g, faces_where(g, lambda f, sy=sy: f.normal.y * sy > 0.9), 0.3, -0.05, mat="metal_plate")
        for z in (2.0, 4.0, 6.0, 8.0):
            box(W - 0.4, 0.1, 0.18, at=(0, sy * (T / 2 + 0.02), z - 0.09), mat="metal_dark", base=True)
        for x in (-W / 4, 0.0, W / 4):
            box(0.25, 0.1, H - 0.6, at=(x, sy * (T / 2 + 0.03), 0.3), mat="metal_dark", base=True)
    box(W, T + 0.04, 0.3, at=(0, 0, 1.05), mat="metal_painted_yellow", base=True)
    return {"colliders": [K.collider_box((0, 0, H / 2), (W, T, H))], "slide": "prototype opens each leaf 10 m outward along X"}


def gate_frame(W=24.0, H=10.0):
    for sx in (-1, 1):
        box(2.0, 2.0, H, at=(sx * (W / 2 + 1.0), 0, 0), mat="metal_dark", base=True, bevel=0.04)
        hazard_x = sx * (W / 2 + 1.0)
        box(2.04, 2.04, 0.4, at=(hazard_x, 0, 1.0), mat="metal_painted_yellow", base=True)
        box(0.4, 0.2, 0.2, at=(sx * (W / 2 - 2.0), -1.1, H - 1.0), mat="emit_red", base=True)
    box(W + 4.0, 2.0, 1.0, at=(0, 0, H - 1.0), mat="metal_dark", base=True, bevel=0.04)
    box(W, 0.3, 0.2, at=(0, -0.6, H - 1.2), mat="metal_bare", base=True)
    return {"colliders": [K.collider_box((sx * (W / 2 + 1.0), 0, H / 2), (2.0, 2.0, H)) for sx in (-1, 1)]}


def door_leaf(W=1.5, H=3.0, T=0.1, mat="metal_painted_white", window=True):
    d = box(W, T, H, mat=mat, base=True, bevel=0.01)
    if window:
        box(W * 0.5, T + 0.01, 0.6, at=(0, 0, H * 0.62), mat="glass_dark", base=True)
    box(0.04, T + 0.02, 0.4, at=(W / 2 - 0.12, 0, 1.0), mat="metal_bare", base=True)
    box(W, T + 0.01, 0.12, at=(0, 0, 0.0), mat="metal_dark", base=True)
    return {"colliders": [K.collider_box((0, 0, H / 2), (W, T, H))]}


ASSETS.update({
    "ElevatedRail_Pier": dict(fn=rail_pier, cat="structure", zones=["plaza"], notes="8 m concrete pier with cap (prototype elevated rail, every 14 m)."),
    "ElevatedRail_Deck_14m": dict(fn=rail_deck, cat="structure", zones=["plaza"], pivot="top-centre", notes="14 m deck span along Z: box girder, parapets with rail, sleepers and two rails."),
    "Gate_Facility_Leaf": dict(fn=gate_leaf, cat="structure", zones=["plaza", "facility"], notes="12 x 8.6 x 0.6 sliding gate leaf with yellow stripe (two per gate)."),
    "Gate_Facility_Frame": dict(fn=gate_frame, cat="structure", zones=["plaza"], notes="Gate pylons (2 x 2 x 10) + header for a 24 m opening, red status lights."),
    "Door_Sliding_Lab": dict(fn=door_leaf, cat="structure", zones=["facility"], notes="Sliding door leaf 1.5 x 3.0 (white, vision panel)."),
    "Door_Sliding_Metal": dict(fn=door_leaf, kw={"W": 3.0, "H": 3.4, "T": 0.2, "mat": "metal_painted", "window": False}, cat="structure", zones=["metro", "vault"],
                               notes="Heavy door leaf 3.0 x 3.4 x 0.2 (metro signal room)."),
})
