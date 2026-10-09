"""Rooftop sector (cyberpunk restyle): parapets, AC condenser, vents, water tank, antenna masts, relay tower +
transmitter, hatch, ladder, maintenance shed.

Compatibility: every asset keeps its baseline name, pivot, outer extents (Unity size), colliders, metadata keys and
material slots (out/baseline/assets.json; check_regression.py). Extents are reproduced by design: each builder notes
which part defines each outer face.
"""
import math
import random

from mathutils import Vector

import envkit as K
from envkit import box, cyl, lathe, tube, torus, beam, extrude, inset, faces_where, detail
from assets_dressing import (hexbolt, bolt_grid, led, streak, ring_at, bend_path, conduit, strap, warning_triangle,
                             hazard_stripes, light, U, cyl_patch, ribbon, dish_shell, catenary)


def _crack(x0, z0, length, y, seed, facing="-y", mat="black"):
    """Hairline crack: a jagged thin sliver on a wall face (LOD0)."""
    if not detail():
        return
    rnd = random.Random(seed)
    pts = [(x0, z0)]
    for i in range(5):
        x, z = pts[-1]
        pts.append((x + rnd.uniform(-0.04, 0.04), z - length / 5))
    w = 0.004
    poly = [(x - w, z) for x, z in pts] + [(x + w * 0.6, z) for x, z in reversed(pts)]
    c = extrude(poly, 0.0014, plane="XZ", mat=mat, name="crack")
    c.move(0, y + (-0.0008 if facing == "-y" else 0.0008), 0)


# ============================================================================================== parapets
def parapet(L=4.0, H=0.9, T=0.24, mat="concrete"):
    """Extents: coping drip legs define y +-0.16; scupper lip defines y -0.18; coping top z 0.9."""
    hc = 0.06
    box(L, T, H - hc, mat=mat, base=True, bevel=0.008)
    # coping cap (top at H - 0.004) + joint cover straps to H, drip legs both faces
    box(L, T + 0.08, hc - 0.004, at=(0, 0, H - hc), mat="metal_dark", base=True, bevel=0.004)
    for sy in (-1, 1):
        box(L, 0.012, 0.05, at=(0, sy * (T / 2 + 0.034), H - 0.1), mat="metal_dark", base=True)
    for x in (-L / 2 + 0.05, -L / 4, 0.0, L / 4, L / 2 - 0.05):
        box(0.07, T + 0.08, 0.006, at=(x, 0, H - 0.006), mat="metal_dark", base=True)
        if detail():
            for sy in (-1, 1):
                hexbolt((x, sy * (T / 2 + 0.04), H - 0.075), "+y" if sy > 0 else "-y", 0.006, 0.004)
    # sealant control joint (centre) on both faces
    for sy in (-1, 1):
        box(0.012, 0.003, H - hc - 0.03, at=(0, sy * (T / 2 + 0.001), (H - hc) / 2), mat="black")
    # through-wall scupper on the outer face (-Y), rusted, with its stain
    box(0.3, 0.06, 0.12, at=(0.9, -T / 2 - 0.03, 0.0), mat="metal_rusted", base=True, bevel=0.004)
    box(0.24, 0.004, 0.07, at=(0.9, -T / 2 - 0.0605, 0.035), mat="black", base=True)
    # roof-side conduit on straps (+Y face)
    tube([(-L / 2, T / 2 + 0.016, 0.32), (L / 2, T / 2 + 0.016, 0.32)], 0.012, 8, "metal_rusted", "conduit")
    if detail():
        for x in (-1.5, -0.5, 0.5, 1.5):
            box(0.025, 0.006, 0.04, at=(x, T / 2 + 0.003, 0.32), mat="metal_dark")
            ring_at((x, T / 2 + 0.016, 0.32), (1, 0, 0), 0.015, 0.003, 8, 3, "metal_dark")
        # rust run-off under the coping joints and water stains on both faces
        k = 0
        for x in (-L / 4, L / 4, L / 2 - 0.3):
            for sy in (-1, 1):
                streak(x + 0.02 * sy, H - 0.1, 0.22 + 0.08 * (k % 3), 0.022, sy * T / 2, "-y" if sy < 0 else "+y", "metal_rusted", taper=0.3, seed=k)
                if k % 2 == 0:
                    streak(x - 0.35, H - 0.1, 0.3, 0.07, sy * T / 2, "-y" if sy < 0 else "+y", "concrete_wet", taper=0.6, seed=k + 50)
                k += 1
        _crack(-1.2, 0.7, 0.45, -T / 2, 3)
        _crack(1.45, 0.55, 0.4, T / 2, 4, facing="+y")
    return {"colliders": [K.collider_box((0, 0, H / 2), (L, T, H))]}


def parapet_corner(H=0.9, T=0.24, mat="concrete"):
    hc = 0.06
    box(T, T, H - hc, mat=mat, base=True, bevel=0.008)
    box(T + 0.08, T + 0.08, hc - 0.004, at=(0, 0, H - hc), mat="metal_dark", base=True, bevel=0.004)
    box(T + 0.08, T + 0.08, 0.004, at=(0, 0, H - 0.004), mat="metal_dark", base=True)
    for s in (-1, 1):
        box(T + 0.08, 0.012, 0.05, at=(0, s * (T / 2 + 0.034), H - 0.1), mat="metal_dark", base=True)
        box(0.012, T + 0.08, 0.05, at=(s * (T / 2 + 0.034), 0, H - 0.1), mat="metal_dark", base=True)
    if detail():
        for s in (-1, 1):
            streak(0.03, H - 0.1, 0.25, 0.022, s * T / 2, "-y" if s < 0 else "+y", "metal_rusted", taper=0.3, seed=7 + s)
            streak(-0.04, H - 0.1, 0.3, 0.06, s * T / 2, "+x" if s > 0 else "-x", "concrete_wet", taper=0.6, seed=9 + s)
    return {"colliders": [K.collider_box((0, 0, H / 2), (T, T, H))]}


# ============================================================================================== AC condenser
def _louvre_face(x0, x1, z0, z1, y, sy, n, paint, recess=0.05):
    """Louvred coil guard on a face at y (sy = outward sign): black recess, coil fins, angled slats."""
    w, h = x1 - x0, z1 - z0
    box(w, 0.004, h, at=((x0 + x1) / 2, y - sy * recess, (z0 + z1) / 2), mat="black")
    box(w - 0.01, 0.003, h - 0.01, at=((x0 + x1) / 2, y - sy * (recess - 0.012), (z0 + z1) / 2), mat="grating")
    for i in range(n):
        z = z0 + 0.03 + i * (h - 0.06) / (n - 1)
        s = box(w - 0.004, 0.06, 0.008, mat=paint)
        s.rot(x=-40 * sy).move((x0 + x1) / 2, y - sy * 0.025, z)


def ac_unit():
    """Weathered rooftop condenser. Extents: body x -0.7..0.7, rails y +-0.55, disconnect box to x 0.88,
    fan guard top z 1.036."""
    paint = "metal_painted"
    # galvanised base rails (C-channel look) with bolts
    for x in (-0.5, 0.5):
        r = box(0.08, 1.1, 0.1, at=(x, 0, 0), mat="metal_dark", base=True, bevel=0.004)
        inset(r, faces_where(r, lambda f: abs(f.normal.x) > 0.9), 0.014, -0.025, mat="black")
        if detail():
            for y in (-0.48, 0.48):
                hexbolt((x, y, 0.1), "+z", 0.012, 0.008)
    # base pan, corner posts, top deck
    box(1.4, 1.0, 0.08, at=(0, 0, 0.1), mat="metal_dark", base=True, bevel=0.006)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(0.05, 0.05, 0.78, at=(sx * 0.675, sy * 0.475, 0.18), mat="metal_dark", base=True, bevel=0.004)
    box(1.4, 1.0, 0.04, at=(0, 0, 0.96), mat=paint, base=True, bevel=0.008)
    # louvred coil guards on front/back (+-Y) and the -X end
    for sy in (-1, 1):
        box(1.3, 0.03, 0.78, at=(0, sy * 0.485 - sy * 0.06, 0.18), mat="black", base=True)
        _louvre_face(-0.62, 0.62, 0.2, 0.94, sy * 0.5, sy, 12 if detail() else 6, paint)
        box(1.3, 0.03, 0.03, at=(0, sy * 0.485, 0.18), mat=paint, base=True)
        box(1.3, 0.03, 0.03, at=(0, sy * 0.485, 0.93), mat=paint, base=True)
        box(0.03, 0.03, 0.75, at=(0, sy * 0.485, 0.18), mat=paint, base=True)
    with K.placed(x=-0.7, rz=-90):
        box(0.9, 0.03, 0.78, at=(0, 0.06, 0.18), mat="black", base=True)
        _louvre_face(-0.42, 0.42, 0.2, 0.94, 0.0, -1, 12 if detail() else 6, paint)
    # +X service panel: solid, screws, rating plate, hazard label, status LEDs, handle
    box(0.03, 0.9, 0.76, at=(0.685, 0, 0.18), mat=paint, base=True, bevel=0.004)
    with K.placed(x=0.7, rz=90):
        box(0.5, 0.004, 0.32, at=(-0.18, -0.002, 0.68), mat=paint, bevel=0.002)
        box(0.12, 0.003, 0.07, at=(0.25, -0.0015, 0.8), mat="metal_painted_white")
        box(0.1, 0.022, 0.02, at=(-0.18, -0.012, 0.56), mat="metal_bare", bevel=0.004)
        if detail():
            for i in range(4):
                box(0.09, 0.0025, 0.005, at=(0.25, -0.0035, 0.82 - i * 0.012), mat="black")
            warning_triangle((0.25, -0.002, 0.65), 0.09)
            for (x, z) in ((-0.41, 0.82), (0.05, 0.82), (-0.41, 0.54), (0.05, 0.54)):
                hexbolt((x, -0.004, z), "-y", 0.006, 0.004)
            streak(0.05, 0.53, 0.3, 0.025, -0.0, seed=3)
            streak(-0.41, 0.53, 0.25, 0.02, -0.0, seed=4, mat="metal_dark")
        led((0.05, -0.002, 0.42), "emit_green", 0.007)
        led((0.09, -0.002, 0.42), "emit_red", 0.007)
    # disconnect box on a stand at +X with flexible conduit into the panel
    box(0.04, 0.04, 0.42, at=(0.84, 0.3, 0.1), mat="metal_dark", base=True)
    box(0.16, 0.12, 0.28, at=(0.79, 0.3, 0.36), mat="metal_dark", base=True, bevel=0.01)
    box(0.012, 0.03, 0.12, at=(0.874, 0.3, 0.5), mat="metal_painted_red", bevel=0.003)
    tube(bend_path([(0.79, 0.3, 0.36), (0.79, 0.3, 0.28), (0.74, 0.2, 0.26), (0.7, 0.15, 0.3)], 0.04, 3 if detail() else 1), 0.014, 6, "rubber", "flex")
    # refrigerant line set: insulated suction (rubber) + liquid line (copper look) down to the roof and away
    for j, (y, r, m) in enumerate(((-0.15, 0.022, "rubber"), (-0.28, 0.011, "metal_rusted"))):
        tube(bend_path([(0.7, y, 0.35 - 0.04 * j), (0.82, y, 0.35 - 0.04 * j), (0.84, y, 0.12), (0.84, y - 0.2, 0.03), (0.84, -0.55 + r, 0.03)], 0.05, 3 if detail() else 1), r, 8, m, "lineset")
    if detail():
        for z in (0.2,):
            ring_at((0.84, -0.15, z), (0, 0, 1), 0.024, 0.004, 8, 3, "metal_painted_white")
    # top: venturi ring, black throat, fan blades, guard rings + radial wires (top exactly 1.036)
    lathe([(0.44, 1.0), (0.44, 1.02), (0.42, 1.03), (0.4, 1.022)], 32, mat="metal_dark", close_bottom=False, close_top=False)
    cyl(0.405, 0.002, 32, at=(0, 0, 1.0), mat="black")
    cyl(0.08, 0.025, 12, at=(0, 0, 1.002), mat="metal_dark")
    for k in range(4):
        bl = box(0.3, 0.1, 0.006, at=(0.19, 0, 0), mat="metal_dark", bevel=0.002)
        bl.rot(x=22).rot(z=k * 90 + 20).move(0, 0, 1.012)
    for rr in (0.13, 0.26, 0.4):
        t = torus(rr, 0.006, n_major=K.seg(32 if rr > 0.3 else 24, 12), n_minor=4, mat="metal_dark")
        t.move(0, 0, 1.03)
    for k in range(8 if detail() else 4):
        a = k * math.tau / (8 if detail() else 4)
        beam((0.05 * math.cos(a), 0.05 * math.sin(a), 1.03), (0.4 * math.cos(a), 0.4 * math.sin(a), 1.03), 0.008, 0.008, mat="metal_dark")
    # grime: rust run-off at the corner posts, dirt at the base
    if detail():
        for sx in (-1, 1):
            for sy in (-1, 1):
                streak(sx * 0.62, 0.96, 0.35 + 0.1 * (sx + sy + 2) / 4, 0.03, sy * 0.5, "-y" if sy < 0 else "+y", seed=10 + sx + 2 * sy)
        for sy in (-1, 1):
            box(1.38, 0.003, 0.05, at=(0, sy * 0.5015, 0.205), mat="metal_rusted")
    return {"colliders": [K.collider_box((0, 0, 0.52), (1.4, 1.1, 1.05))]}


# ============================================================================================== vents
def roof_vent():
    """Louvred box exhaust on a curb with a hipped cap. Extents: cap +-0.6, top z 1.32."""
    box(0.95, 0.95, 0.15, mat="metal_dark", base=True, bevel=0.006)
    box(0.97, 0.97, 0.03, at=(0, 0, 0.15), mat="metal_dark", base=True, bevel=0.004)
    b = box(0.9, 0.9, 0.82, at=(0, 0, 0.18), mat="metal_bare", base=True, bevel=0.008)
    # standing seams + rivets, louvre band on all four sides
    for k in range(4):
        with K.placed(rz=k * 90):
            for x in (-0.22, 0.22):
                box(0.012, 0.012, 0.42, at=(x, -0.456, 0.2), mat="metal_bare", base=True)
            box(0.86, 0.004, 0.3, at=(0, -0.451, 0.79), mat="black")
            for i in range(6 if detail() else 3):
                s = box(0.84, 0.05, 0.008, mat="metal_bare", bevel=0.002)
                s.rot(x=40).move(0, -0.46, 0.68 + i * 0.045)
            if detail():
                for x in (-0.4, -0.2, 0.0, 0.2, 0.4):
                    hexbolt((x, -0.45, 0.62), "-y", 0.005, 0.003)
                streak(-0.3, 0.62, 0.35, 0.05, -0.45, seed=k * 2, mat="metal_rusted")
                streak(0.15, 0.62, 0.25, 0.04, -0.45, seed=k * 2 + 1, mat="metal_dark")
    # legs, bird screen, cap
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(0.05, 0.05, 0.25, at=(sx * 0.4, sy * 0.4, 1.0), mat="metal_dark", base=True)
    box(0.8, 0.8, 0.02, at=(0, 0, 0.99), mat="black", base=True)
    box(0.78, 0.78, 0.21, at=(0, 0, 1.005), mat="grating", base=True)
    box(1.2, 1.2, 0.06, at=(0, 0, 1.22), mat="metal_dark", base=True, bevel=0.006)
    box(0.95, 0.95, 0.12, mat="metal_dark", base=True)
    K.loft([[(-0.58, -0.58, 1.28), (0.58, -0.58, 1.28), (0.58, 0.58, 1.28), (-0.58, 0.58, 1.28)],
            [(-0.2, -0.2, 1.32), (0.2, -0.2, 1.32), (0.2, 0.2, 1.32), (-0.2, 0.2, 1.32)]], mat="metal_dark", cap_start=False)
    if detail():
        for sx in (-1, 1):
            for sy in (-1, 1):
                streak(sx * 0.4, 1.22, 0.4, 0.04, sy * 0.45, "-y" if sy < 0 else "+y", seed=20 + sx + 3 * sy)
    return {"colliders": [K.collider_box((0, 0, 0.66), (1.2, 1.2, 1.32))]}


def turbine_vent():
    """Whirlybird: flashing boot, swaged throat, bearing bar, 24 curved vanes, domed crown. Extents r 0.3345."""
    box(0.5, 0.5, 0.04, mat="metal_dark", base=True, bevel=0.004)
    lathe([(0.24, 0.04), (0.2, 0.1), (0.185, 0.14)], 16, mat="metal_dark", close_bottom=False, close_top=False)
    lathe([(0.18, 0.04), (0.18, 0.2), (0.186, 0.21), (0.18, 0.22), (0.18, 0.44), (0.186, 0.45), (0.18, 0.46), (0.18, 0.58), (0.22, 0.6), (0.3, 0.62)],
          16, mat="metal_bare", close_bottom=False, close_top=False)
    # bearing bar + spindle
    beam((-0.18, 0, 0.58), (0.18, 0, 0.58), 0.025, 0.012, mat="metal_dark")
    cyl(0.012, 0.36, 6, at=(0, 0, 0.58), mat="metal_bare")
    # lower ring
    t = torus(0.3, 0.008, n_major=K.seg(24, 12), n_minor=4, mat="metal_bare")
    t.move(0, 0, 0.62)
    # curved vanes (two-sided ribbons)
    nv = 24 if detail() else 12
    ns = 4 if detail() else 2
    for k in range(nv):
        a0 = k * 360.0 / nv
        def edge(da):
            pts = []
            for i in range(ns + 1):
                t_ = i / ns
                ang = math.radians(a0 + da + 22 * t_)
                r = 0.3 + 0.033 * math.sin(math.pi * t_)
                pts.append((r * math.cos(ang), r * math.sin(ang), 0.62 + 0.27 * t_))
            return pts
        l, r = edge(0.0), edge(10.0)
        ribbon(l, r, "metal_bare", out=lambda c: (c.x, c.y, 0))
        ribbon(r, l, "metal_bare", out=lambda c: (-c.x, -c.y, 0))
    # crown dome (top exactly 1.0)
    lathe([(0.315, 0.88), (0.322, 0.9), (0.3, 0.94), (0.22, 0.975), (0.1, 0.995), (0.001, 1.0)], 24, mat="metal_bare")
    if detail():
        for k in range(12):
            a = k * math.tau / 12
            beam((0.3 * math.cos(a), 0.3 * math.sin(a), 0.905), (0.06 * math.cos(a), 0.06 * math.sin(a), 0.992), 0.012, 0.006, mat="metal_bare")
        cyl_patch(0.181, 200, 215, 0.25, 0.55, "metal_rusted", n=2)
        cyl_patch(0.181, 20, 30, 0.3, 0.57, "metal_rusted", n=1)
    return {"colliders": [K.collider_box((0, 0, 0.5), (0.7, 0.7, 1.0))]}


# ============================================================================================== water tank
def water_tank():
    """Rusted steel tank on a braced I-beam stand. Extents: rim (r 1.7, 24 seg) x +-1.6855, ladder y -1.715,
    outlet pipe end y 1.9, vent top z 5.5."""
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * 1.0, sy * 1.0
            box(0.3, 0.3, 0.02, at=(x, y, 0), mat="metal_dark", base=True)
            for dx in (-0.06, 0.06):
                box(0.02, 0.14, 2.4, at=(x + dx, y, 0), mat="metal_dark", base=True)
            box(0.12, 0.02, 2.4, at=(x, y, 0), mat="metal_dark", base=True)
            if detail():
                for dx in (-0.11, 0.11):
                    for dy in (-0.11, 0.11):
                        hexbolt((x + dx, y + dy, 0.02), "+z", 0.012, 0.012)
    for (a, b) in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
        beam((a[0], a[1], 2.35), (b[0], b[1], 2.35), 0.12, mat="metal_dark")
        beam((a[0], a[1], 0.3), (b[0], b[1], 2.2), 0.05, 0.012, mat="metal_rusted")
        beam((b[0], b[1], 0.3), (a[0], a[1], 2.2), 0.05, 0.012, mat="metal_rusted")
        beam((a[0], a[1], 0.35), (b[0], b[1], 0.35), 0.08, 0.05, mat="metal_dark")
        if detail():
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 1.25)
            box(0.1, 0.1, 0.1, at=m, mat="metal_dark")
    # tank shell: welded courses, bottom, roof (rim r 1.7 with 24 segments keeps the baseline extents)
    lathe([(0.001, 2.42), (1.62, 2.42), (1.62, 3.2), (1.628, 3.21), (1.62, 3.22), (1.62, 4.0), (1.628, 4.01), (1.62, 4.02), (1.62, 4.8), (1.7, 4.82),
           (0.25, 5.3), (0.001, 5.32)], 24, mat="metal_rusted")
    for z in (3.0, 3.8, 4.5):
        torus(1.632, 0.022, n_major=K.seg(32, 16), n_minor=4, mat="metal_dark").move(0, 0, z)
    if detail():
        # vertical weld seams + dark run-off streaks
        for k in range(6):
            a = k * 60 + 15
            cyl_patch(1.622, a, a + 0.6, 2.45, 4.78, "metal_dark", n=1)
        rnd = random.Random(5)
        for k in range(9):
            a = rnd.uniform(0, 360)
            cyl_patch(1.6225, a, a + rnd.uniform(1.5, 4.0), rnd.uniform(2.6, 3.8), 4.79, "black" if k % 3 == 0 else "metal_dark", n=1)
        # roof hatch + level gauge with a glowing level strip
        hb = box(0.4, 0.3, 0.1, at=(0, 0, 0), mat="metal_dark", base=True, bevel=0.01)
        hb.rot(x=-17).move(0.0, -0.9, 5.02)
        tube([(1.1, -1.21, 2.6), (1.1, -1.21, 4.7)], 0.02, 6, "metal_bare", "gauge")
        for z in (2.62, 4.68):
            tube([(1.1, -1.21, z), (1.15, -1.13, z)], 0.015, 6, "metal_bare")
        box(0.012, 0.012, 1.3, at=(1.08, -1.235, 3.0), mat="emit_strip_cyan", base=True)
    cyl(0.12, 0.25, 10, at=(0, 0, 5.25), mat="metal_dark")
    lathe([(0.001, 5.43), (0.16, 5.43), (0.17, 5.46), (0.001, 5.5)], 10, mat="metal_dark")
    # outlet pipe with gate valve (end at y 1.9)
    tube(bend_path([(0.6, 0.6, 2.42), (0.6, 0.6, 1.2), (0.6, 1.6, 0.4), (0.6, 1.9, 0.4)], 0.2, 3 if detail() else 1), 0.07, 10, "metal_rusted", "outlet")
    cyl(0.1, 0.14, 12, at=(0.6, 0.6, 1.7), mat="metal_dark")
    cyl(0.03, 0.2, 6, at=(0.6, 0.6, 1.77), axis="X", mat="metal_bare")
    torus(0.09, 0.01, n_major=12, n_minor=4, mat="metal_painted_yellow").rot(y=90).move(0.8, 0.6, 1.77)
    # ladder on -Y with standoffs (rails define y -1.715)
    for x in (-0.22, 0.22):
        box(0.05, 0.03, 5.0, at=(x, -1.7, 0.0), mat="metal_dark", base=True)
        for z in (2.6, 4.0, 4.7):
            box(0.04, 0.12, 0.04, at=(x, -1.64, z), mat="metal_dark")
    for i in range(16):
        cyl(0.014, 0.44, 6, at=(-0.22, -1.7, 0.3 + i * 0.3), axis="X", mat="metal_painted_yellow")
    return {"colliders": [K.collider_box((0, 0, 1.2), (2.2, 2.2, 2.4)), {"type": "capsule", "center": [0, 3.85, 0], "radius": 1.7, "height": 2.9, "direction": "Y"}]}


# ============================================================================================== antenna mast
def antenna_mast(h=5.0, beacon=True):
    """Tapered steel pole with yagi cross-arms, sector panel, cable run, base box, guy wires with turnbuckles to
    ballast anchors (radius 0.45 h: they define the footprint), red aviation beacon in a cage (top h+0.18)."""
    box(0.4, 0.4, 0.03, mat="metal_dark", base=True, bevel=0.004)
    if detail():
        for k in range(4):
            g = extrude([(0.0, 0.0), (0.12, 0.0), (0.0, 0.2)], 0.01, plane="XZ", mat="metal_dark")
            g.move(0.05, 0, 0.03).rot(z=k * 90 + 45)
        for sx in (-1, 1):
            for sy in (-1, 1):
                hexbolt((sx * 0.15, sy * 0.15, 0.03), "+z", 0.012, 0.015)
    cyl(0.12, h, 10, at=(0, 0, 0.03), r2=0.05, mat="metal_dark")
    # flange splice + climbing pegs
    if h > 4:
        torus(0.1, 0.02, n_major=10, n_minor=4, mat="metal_dark").move(0, 0, h * 0.5)
    if detail():
        n = int(h / 0.45)
        for i in range(1, n):
            z = 0.6 + i * 0.4
            if z > h - 0.4:
                break
            r = 0.12 + (0.05 - 0.12) * (z / h)
            s = 1 if i % 2 else -1
            cyl(0.008, 0.14, 4, at=(s * r, 0, z), axis="X", mat="metal_bare").move(-0.14 if s < 0 else 0, 0, 0)
    for i in range(1, 4):
        z = h * i / 4
        L = 0.9 - i * 0.18
        beam((-L / 2, 0, z), (L / 2, 0, z), 0.04, mat="metal_dark")
        if detail():
            for k in range(5):
                x = -L / 2 + 0.05 + k * (L - 0.1) / 4
                cyl(0.008, 0.35, 4, at=(x, -0.175, z), axis="Y", mat="metal_bare")
                cyl(0.014, 0.03, 6, at=(x, -0.015, z - 0.015), mat="metal_dark")
    # sector panel + coax run down the pole
    zp = h * 0.62
    box(0.16, 0.07, 0.6 if h > 4 else 0.4, at=(0, 0.13, zp), mat="metal_painted_white", base=True, bevel=0.015)
    box(0.06, 0.08, 0.04, at=(0, 0.075, zp + 0.1), mat="metal_dark")
    tube([(0.06, 0.04, zp), (0.075, 0.06, 0.4)], 0.008, 5, "black", "coax")
    box(0.18, 0.12, 0.24, at=(0.0, 0.17, 0.08), mat="metal_painted", base=True, bevel=0.008)
    led((0.05, 0.109, 0.27), "emit_green", 0.005)
    tube(bend_path([(0.075, 0.06, 0.42), (0.04, 0.15, 0.36), (0.02, 0.17, 0.32)], 0.04, 2), 0.008, 5, "black")
    if beacon:
        lathe([(0.07, h), (0.07, h + 0.04), (0.06, h + 0.14), (0.001, h + 0.18)], 10, mat="emit_red")
        if detail():
            for k in range(4):
                a = k * math.tau / 4 + 0.4
                tube([(0.075 * math.cos(a), 0.075 * math.sin(a), h), (0.078 * math.cos(a), 0.078 * math.sin(a), h + 0.12), (0, 0, h + 0.175)], 0.004, 3, "metal_dark")
            torus(0.077, 0.004, n_major=10, n_minor=3, mat="metal_dark").move(0, 0, h + 0.07)
    # guy wires: anchors at radius 0.45 h, turnbuckles near the anchor
    for a in (0, 120, 240):
        ax, ay = math.cos(math.radians(a)) * h * 0.45, math.sin(math.radians(a)) * h * 0.45
        top = Vector((0, 0, h * 0.7))
        bot = Vector((ax, ay, 0.04))
        tb = bot.lerp(top, 0.08 / (top - bot).length * 3)
        tube([tuple(top), tuple(tb)], 0.005, 4, "metal_bare", "guy")
        if detail():
            d = (top - bot).normalized()
            tube([tuple(tb), tuple(tb - d * 0.12)], 0.012, 6, "metal_dark", "turnbuckle")
            tube([tuple(tb - d * 0.12), tuple(bot)], 0.004, 4, "metal_bare", "guy")
        box(0.1, 0.1, 0.04, at=(ax, ay, 0), mat="concrete", base=True, bevel=0.005)
    return {"colliders": [K.collider_box((0, 0, h / 2), (0.25, 0.25, h))], "beacon": K.to_unity_vec((0, 0, h + 0.1))}


# ============================================================================================== relay tower
def _angle_leg(x, y, H, sx, sy, w=0.25, t=0.03):
    """L-angle leg (two flanges) opening toward the tower centre."""
    box(w, t, H, at=(x, y + sy * (w / 2 - t / 2), 0), mat="metal_dark", base=True, bevel=0.004)
    box(t, w, H, at=(x + sx * (w / 2 - t / 2), y, 0), mat="metal_dark", base=True, bevel=0.004)


def relay_tower(H=12.0, s=4.0):
    """Lattice relay tower. Extents: sector panels define x +-2.397, dish feed arm y -2.6, rails y +2.325,
    beacon tip z H+4.06."""
    hs = s / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * hs, sy * hs
            _angle_leg(x, y, H, sx, sy)
            box(0.5, 0.5, 0.05, at=(x, y, 0), mat="metal_dark", base=True, bevel=0.005)
            if detail():
                for z in (4.0, 8.0):  # bolted splice plates
                    box(0.27, 0.27, 0.22, at=(x, y, z - 0.11), mat="metal_dark", base=True)
                for dx in (-0.18, 0.18):
                    for dy in (-0.18, 0.18):
                        hexbolt((x + dx, y + dy, 0.05), "+z", 0.015, 0.025)
    zs = [2.0 + 2.5 * i for i in range(5)]
    faces = [((-hs, -hs), (hs, -hs)), ((hs, -hs), (hs, hs)), ((hs, hs), (-hs, hs)), ((-hs, hs), (-hs, -hs))]
    for z in zs:
        for a, b in faces:
            beam((a[0], a[1], z), (b[0], b[1], z), 0.12, 0.08, mat="metal_dark")
    for k in range(len(zs) - 1):
        z0, z1 = zs[k], zs[k + 1]
        for a, b in faces:
            if detail() or k % 2 == 0:
                beam((a[0], a[1], z0), (b[0], b[1], z1), 0.07, 0.05, mat="metal_dark")
                beam((b[0], b[1], z0), (a[0], a[1], z1), 0.07, 0.05, mat="metal_dark")
    for a, b in faces:
        beam((a[0], a[1], 0.3), ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, zs[0]), 0.07, 0.05, mat="metal_dark")
        beam((b[0], b[1], 0.3), ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, zs[0]), 0.07, 0.05, mat="metal_dark")
    # mid-height obstruction lights on two legs
    for sx, sy in ((-1, -1), (1, 1)):
        x, y = sx * (hs + 0.08), sy * (hs + 0.08)
        box(0.1, 0.1, 0.05, at=(x, y, 6.0), mat="metal_dark", base=True)
        lathe([(0.04, 0.0), (0.04, 0.03), (0.03, 0.07), (0.001, 0.08)], 8, at=(x, y, 6.05), mat="emit_red")
    # cable ladder with feeders up the -X/-Y leg side
    for j in range(5):
        tube([(-hs + 0.2 + j * 0.035, -hs + 0.12, 0.4), (-hs + 0.2 + j * 0.035, -hs + 0.12, H - 0.15)], 0.012, 5, "black", "feeder")
    if detail():
        for z in range(1, int(H), 1):
            box(0.25, 0.05, 0.02, at=(-hs + 0.27, -hs + 0.12, z), mat="metal_bare")
    # platform: frame, grating, toe board with a cyan LED strip, rails
    box(s + 0.6, s + 0.6, 0.06, at=(0, 0, H), mat="grating", base=True)
    box(s + 0.6, s + 0.6, 0.12, at=(0, 0, H - 0.12), mat="metal_dark", base=True)
    for a, b in faces:
        beam((a[0], a[1], H - 0.06), (b[0], b[1], H - 0.06), 0.15, 0.12, mat="metal_dark")
    e = hs + 0.3
    for (a, b) in (((-e, -e), (e, -e)), ((e, -e), (e, e)), ((e, e), (-e, e)), ((-e, e), (-e, -e))):
        beam((a[0], a[1], H + 1.0), (b[0], b[1], H + 1.0), 0.05, mat="metal_painted_yellow")
        beam((a[0], a[1], H + 0.5), (b[0], b[1], H + 0.5), 0.04, mat="metal_painted_yellow")
        d = Vector((b[0] - a[0], b[1] - a[1], 0)).normalized()
        n = Vector((-d.y, d.x, 0))
        mid = Vector(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, H + 0.06))
        box(s + 0.6 if abs(d.x) > 0.5 else 0.02, 0.02 if abs(d.x) > 0.5 else s + 0.6, 0.12, at=tuple(mid - n * 0.0 * 0), mat="metal_dark", base=True)
        box(s + 0.5 if abs(d.x) > 0.5 else 0.008, 0.008 if abs(d.x) > 0.5 else s + 0.5, 0.012,
            at=(mid.x * 0.997, mid.y * 0.997, H + 0.13), mat="emit_strip_cyan", base=True)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(0.05, 0.05, 1.0, at=(sx * (hs + 0.3), sy * (hs + 0.3), H), mat="metal_dark", base=True)
    for sx in (-1, 1):
        box(0.05, 0.05, 1.0, at=(sx * (hs + 0.3), 0, H), mat="metal_dark", base=True)
        box(0.05, 0.05, 1.0, at=(0, sx * (hs + 0.3), H), mat="metal_dark", base=True)
    # equipment cabinets on the deck
    box(0.6, 0.45, 0.9, at=(-0.8, 0.9, H + 0.06), mat="metal_painted", base=True, bevel=0.012)
    box(0.62, 0.47, 0.03, at=(-0.8, 0.9, H + 0.96), mat="metal_dark", base=True)
    for k, m in enumerate(("emit_green", "emit_amber", "emit_green")):
        led((-0.95 + k * 0.03, 0.674, H + 0.8), m, 0.007)
    box(0.4, 0.4, 0.4, at=(0, 0, H + 1.0), mat="metal_bare", base=True, bevel=0.01)
    box(0.42, 0.42, 0.95, at=(0, 0, H + 0.06), mat="metal_dark", base=True)
    # central mast + beacon (beacon centre H+3.95, tip H+4.06)
    cyl(0.06, 2.4, 8, at=(0, 0, H + 1.4), mat="metal_dark")
    lathe([(0.12, H + 3.8), (0.12, H + 3.86), (0.1, H + 4.0), (0.001, H + 4.06)], 10, mat="emit_red")
    cyl(0.14, 0.03, 10, at=(0, 0, H + 3.77), mat="metal_dark")
    cyl(0.018, 1.2, 6, at=(0.12, 0, H + 2.2), mat="paint_glossy_white")
    beam((0, 0, H + 2.2), (0.12, 0, H + 2.2), 0.03, mat="metal_dark")
    # sector panels on outrigger pipes at +-X (outer faces define x +-2.397)
    for sx in (-1, 1):
        for y in (-0.8, 0.8):
            px = sx * (2.397 - 0.06)
            cyl(0.03, 1.8, 8, at=(sx * (hs + 0.3), y, H + 0.1), mat="metal_bare")
            for z in (H + 0.4, H + 1.5):
                beam((sx * (hs + 0.3), y, z), (px - sx * 0.04, y, z), 0.04, mat="metal_dark")
            box(0.12, 0.32, 1.6, at=(px, y, H + 0.1), mat="metal_painted_white", base=True, bevel=0.03)
            box(0.14, 0.12, 0.3, at=(px - sx * 0.16, y, H + 0.7), mat="metal_dark", base=True, bevel=0.006)
    # dish facing -Y on its mount (feed arm tip at y -2.6)
    dish = lathe([(0.001, 0.0), (0.3, 0.03), (0.6, 0.12), (0.8, 0.22), (0.82, 0.24), (0.8, 0.25), (0.6, 0.14), (0.3, 0.05), (0.001, 0.02)], 20,
                 mat="metal_painted_white", close_bottom=False, close_top=False)
    dish.rot(x=90).move(-hs * 0.4, -hs - 0.2, H + 1.6)
    cyl(0.04, 0.6, 6, at=(-hs * 0.4, -hs - 0.6, H + 1.6), axis="Y", mat="metal_dark")
    cyl(0.07, 0.12, 10, at=(-hs * 0.4, -hs - 0.6, H + 1.6), axis="Y", mat="metal_painted_white")
    for k in range(3):
        a = math.radians(90 + k * 120)
        beam((-hs * 0.4 + 0.78 * math.cos(a), -hs - 0.42, H + 1.6 + 0.78 * math.sin(a)), (-hs * 0.4, -hs - 0.58, H + 1.6), 0.02, mat="metal_painted_white")
    beam((-hs * 0.4, -hs + 0.05, H + 1.6), (-hs * 0.4, -hs - 0.2, H + 1.6), 0.12, mat="metal_dark")
    cyl(0.05, 1.6, 8, at=(-hs * 0.4, -hs + 0.05, H + 0.06), mat="metal_dark")
    # ladder on +X face (no cage: keeps the footprint)
    for i in range(int(H / 0.3)):
        cyl(0.014, 0.4, 6, at=(hs + 0.2, -0.2, 0.3 + i * 0.3), axis="Y", mat="metal_painted_yellow")
    for y in (-0.2, 0.2):
        box(0.05, 0.03, H, at=(hs + 0.2, y, 0), mat="metal_dark", base=True)
        if detail():
            for z in (1.0, 4.0, 7.0, 10.0):
                box(0.2, 0.03, 0.04, at=(hs + 0.1, y, z), mat="metal_dark")
    return {"colliders": [K.collider_box((sx * hs, sy * hs, H / 2), (0.3, 0.3, H)) for sx in (-1, 1) for sy in (-1, 1)] +
            [K.collider_box((0, 0, H - 0.03), (s + 0.6, s + 0.6, 0.18))], "beacon": K.to_unity_vec((0, 0, H + 3.95))}


# ============================================================================================== relay transmitter
def relay_transmitter():
    """Weatherproof transmitter cabinet. Screen recess 2.4 x 1.0 (slot 'screen') at the baseline position;
    battery pack at -X (x -2.8), feeder cables out of the back (y 1.82). Front margins carry LED status columns."""
    b = box(3.0, 1.0, 1.6, mat="metal_dark", base=True, bevel=0.025)
    inset(b, faces_where(b, lambda f: f.normal.y < -0.9), 0.3, -0.03, mat="screen")
    box(3.1, 1.1, 0.06, at=(0, 0, 1.6), mat="metal_dark", base=True, bevel=0.01)
    # bezel strips around the screen (outside the 2.4 x 1.0 rect), front margins with LEDs / keypad
    for sz in (-1, 1):
        box(2.5, 0.02, 0.04, at=(0, -0.51, 0.8 + sz * 0.52), mat="black")
    for sx in (-1, 1):
        box(0.04, 0.02, 1.08, at=(sx * 1.22, -0.51, 0.8), mat="black")
        for k, m in enumerate(("emit_green", "emit_green", "emit_amber", "emit_red")):
            led((sx * 1.36, -0.5, 1.3 - k * 0.06), m, 0.01)
        box(0.012, 0.012, 0.9, at=(sx * 1.45, -0.505, 0.35), mat="emit_strip_cyan", base=True)
    if detail():
        for i in range(3):
            for j in range(3):
                box(0.035, 0.012, 0.03, at=(-1.36 + (i - 1) * 0.045, -0.505, 0.45 + j * 0.04), mat="metal_bare", bevel=0.003)
        warning_triangle((1.36, -0.5, 0.55), 0.12)
        for sx in (-1, 1):
            for z in (0.12, 1.48):
                hexbolt((sx * 1.4, -0.5, z), "-y", 0.012, 0.006)
        streak(-1.38, 0.28, 0.25, 0.06, -0.5, seed=1, mat="metal_rusted")
        streak(1.3, 0.3, 0.2, 0.05, -0.5, seed=2, mat="metal_rusted")
    # side louvres + fan grille (+X side), base plinth rails
    if detail():
        for sx in (-1, 1):
            for i in range(5):
                box(0.012, 0.6, 0.04, at=(sx * 1.506, 0.0, 0.3 + i * 0.12), mat="black")
    t = torus(0.18, 0.01, n_major=K.seg(20, 10), n_minor=4, mat="metal_bare")
    t.rot(y=90).move(1.51, 0.0, 1.2)
    cyl(0.17, 0.01, 16, at=(1.5, 0.0, 1.2), axis="X", mat="black")
    for k in range(4):
        sp = box(0.008, 0.34, 0.008, mat="metal_bare")
        sp.rot(x=k * 45).move(1.512, 0.0, 1.2)
    # feeder cables out of the back (end points as baseline)
    tube(bend_path([(1.2, 0.5, 1.4), (1.2, 0.9, 1.4), (1.6, 1.6, 1.6)], 0.15, 3 if detail() else 1), 0.05, 6, "rubber")
    tube(bend_path([(-1.2, 0.5, 1.2), (-1.2, 1.0, 1.2), (-1.6, 1.8, 1.4)], 0.15, 3 if detail() else 1), 0.05, 6, "rubber")
    for x in (1.2, -1.2):
        cyl(0.075, 0.06, 8, at=(x, 0.5, 1.4 if x > 0 else 1.2), axis="Y", mat="metal_bare", start=0)
    # battery / power pack at -X (0.6 cube)
    box(0.6, 0.6, 0.6, at=(-2.5, 0, 0), mat="metal_painted_yellow", base=True, bevel=0.02)
    hazard_stripes(-2.78, -2.22, 0.04, 0.12, -0.3, n=4)
    for sx in (-1, 1):
        tube(bend_path([(-2.5 + sx * 0.18, -0.08, 0.6), (-2.5 + sx * 0.18, -0.08, 0.64), (-2.5 + sx * 0.18, 0.08, 0.64), (-2.5 + sx * 0.18, 0.08, 0.6)], 0.02, 2), 0.01, 6, "metal_dark")
    box(0.14, 0.01, 0.05, at=(-2.5, -0.302, 0.45), mat="metal_dark", bevel=0.002)
    for k in range(4):
        box(0.025, 0.004, 0.03, at=(-2.548 + k * 0.032, -0.308, 0.45), mat="emit_green" if k < 3 else "black")
    tube(bend_path([(-2.2, 0.15, 0.3), (-1.9, 0.2, 0.25), (-1.5, 0.2, 0.3)], 0.1, 2), 0.02, 6, "rubber")
    return {"colliders": [K.collider_box((0, 0, 0.8), (3.0, 1.0, 1.6))],
            "screen": {"center": K.to_unity_vec((0, -0.53, 0.8)), "size": [2.4, 1.0], "normal": [0, 0, 1], "material": "screen"}}


# ============================================================================================== roof hatch
def roof_hatch_frame():
    """Insulated hatch curb. Extents: base flashing band +-0.8, top 0.35. Hinge brackets on the +Y (Unity -Z) side."""
    for sx in (-1, 1):
        box(0.188, 1.588, 0.33, at=(sx * 0.7, 0, 0), mat="metal_dark", base=True, bevel=0.01)
        box(1.2, 0.188, 0.33, at=(0, sx * 0.7, 0), mat="metal_dark", base=True, bevel=0.01)
    # top capping with drip lip, inner liner
    for sx in (-1, 1):
        box(0.2, 1.6, 0.02, at=(sx * 0.7, 0, 0.33), mat="metal_dark", base=True, bevel=0.004)
        box(1.2, 0.2, 0.02, at=(0, sx * 0.7, 0.33), mat="metal_dark", base=True, bevel=0.004)
        box(0.006, 1.2, 0.3, at=(sx * 0.603, 0, 0.03), mat="metal_bare", base=True)
        box(1.2, 0.006, 0.3, at=(0, sx * 0.603, 0.03), mat="metal_bare", base=True)
    # base flashing band (defines the +-0.8 extents)
    for sx in (-1, 1):
        box(0.012, 1.6, 0.08, at=(sx * 0.794, 0, 0.0), mat="metal_dark", base=True)
        box(1.6, 0.012, 0.08, at=(0, sx * 0.794, 0.0), mat="metal_dark", base=True)
    # hazard edge on the top capping (front), hinge brackets (back), latch keeper (front)
    hazard_stripes(-0.6, 0.6, 0.27, 0.32, -0.794, n=8)
    for x in (-0.5, 0.5):
        box(0.12, 0.04, 0.05, at=(x, 0.7, 0.3), mat="metal_dark", base=True)
    box(0.12, 0.05, 0.05, at=(0, -0.7, 0.28), mat="metal_bare", base=True, bevel=0.004)
    if detail():
        for sx in (-1, 1):
            for t in (-0.55, 0.0, 0.55):
                hexbolt((sx * 0.8, t, 0.04), "+x" if sx > 0 else "-x", 0.006, 0.004)
                hexbolt((t, sx * 0.8, 0.04), "+y" if sx > 0 else "-y", 0.006, 0.004)
        for sx in (-1, 1):
            streak(0.3 * sx, 0.3, 0.2, 0.05, sx * 0.794, "+x" if sx > 0 else "-x", seed=4 + sx)
            streak(-0.3 * sx, 0.3, 0.18, 0.04, sx * 0.794, "+y" if sx > 0 else "-y", seed=6 + sx)
    return {"colliders": [K.collider_box((sx * 0.7, 0, 0.175), (0.2, 1.6, 0.35)) for sx in (-1, 1)] +
            [K.collider_box((0, sy * 0.7, 0.175), (1.2, 0.2, 0.35)) for sy in (-1, 1)], "opening": [1.2, 1.2]}


def roof_hatch_lid():
    """Hatch lid; pivot on the hinge line (back edge, +Y Blender = Unity -Z). Extents x +-0.75, y -1.5..0.04,
    z 0..0.12 (handle). The underside stays flat (it rests on the curb)."""
    l = box(1.5, 1.5, 0.06, at=(0, -0.75, 0), mat="metal_painted", base=True, bevel=0.01)
    # raised top panel + stiffener ribs + rubber gasket edge
    box(1.36, 1.36, 0.016, at=(0, -0.75, 0.06), mat="metal_painted", base=True, bevel=0.006)
    for x in (-0.34, 0.34):
        box(0.05, 1.3, 0.008, at=(x, -0.75, 0.076), mat="metal_painted", base=True, bevel=0.003)
    box(1.3, 0.05, 0.008, at=(0, -0.75, 0.076), mat="metal_painted", base=True, bevel=0.003)
    box(1.44, 1.44, 0.004, at=(0, -0.75, 0.0), mat="black", base=True)
    # hinges: knuckles on the back edge (y max 0.04)
    for x in (-0.5, 0.5):
        box(0.16, 0.08, 0.04, at=(x, -0.04, 0.02), mat="metal_dark", base=True)
        cyl(0.02, 0.16, 10, at=(x - 0.08, 0.015, 0.04), axis="X", mat="metal_dark")
        box(0.12, 0.005, 0.05, at=(x, 0.0375, 0.01), mat="metal_dark", base=True)
    # pull handle (top 0.12) + latch + hold-open arm lug
    tube(bend_path([(-0.14, -1.45, 0.076), (-0.14, -1.45, 0.11), (0.14, -1.45, 0.11), (0.14, -1.45, 0.076)], 0.02, 2), 0.01, 6, "metal_bare")
    box(0.1, 0.04, 0.02, at=(0, -1.38, 0.076), mat="metal_dark", base=True)
    box(0.06, 0.06, 0.03, at=(0.6, -0.4, 0.06), mat="metal_dark", base=True)
    if detail():
        for x in (-0.6, -0.2, 0.2, 0.6):
            for y in (-0.1, -1.4):
                hexbolt((x, y, 0.076), "+z", 0.006, 0.004)
        # paint wear + rust around the handle and hinges
        box(0.3, 0.12, 0.002, at=(0.0, -1.42, 0.076), mat="metal_rusted", base=True)
        for x in (-0.5, 0.5):
            box(0.2, 0.1, 0.002, at=(x, -0.11, 0.076), mat="metal_rusted", base=True)
    return {"colliders": [K.collider_box((0, -0.75, 0.04), (1.5, 1.5, 0.08))]}


# ============================================================================================== ladder
def ladder(H=4.0, standoff=0.18):
    """Wall ladder; pivot on the wall plane at the bottom (ladder in front, -Y = Unity +Z). Extents: stiles
    x +-0.255, stile front y -0.1925 (+wear), top 5.0."""
    for x in (-0.23, 0.23):
        # rectangular-tube stile, gooseneck grab rail bending back toward the wall at the top
        box(0.05, 0.025, H + 0.85, at=(x, -standoff, 0), mat="metal_dark", base=True, bevel=0.004)
        tube(bend_path([(x, -standoff, H + 0.84), (x, -standoff, H + 0.9), (x, -standoff + 0.06, H + 0.985)], 0.05, 3 if detail() else 1), 0.0125, 6, "metal_dark", "goose")
        box(0.052, 0.027, 0.25, at=(x, -standoff, H + 0.55), mat="metal_painted_yellow", base=True)
        # wall brackets: plate + arm + bolts
        for z in (0.4, H * 0.5, H - 0.3):
            box(0.04, standoff, 0.04, at=(x, -standoff / 2, z), mat="metal_dark", base=True)
            box(0.05, 0.006, 0.12, at=(x, -0.003, z - 0.04), mat="metal_dark", base=True)
            if detail():
                hexbolt((x, -0.006, z + 0.05), "-y", 0.008, 0.006)
                hexbolt((x, -0.006, z - 0.02), "-y", 0.008, 0.006)
                beam((x, -0.012, z - 0.1), (x, -standoff + 0.02, z), 0.015, 0.006, mat="metal_dark")
        box(0.06, 0.03, 0.006, at=(x, -standoff, 0.0), mat="metal_dark", base=True)
        if detail():
            streak(-standoff + 0.0, 0.5, 0.45, 0.02, x + 0.025, "+x", seed=int(x * 100))
    for i in range(int(H / 0.3)):
        z = 0.3 + i * 0.3
        cyl(0.014, 0.46, 8, at=(-0.23, -standoff, z), axis="X", mat="metal_painted_yellow")
        if detail():
            for x in (-0.205, 0.205):
                cyl(0.018, 0.012, 8, at=(x - 0.006, -standoff, z), axis="X", mat="metal_dark")
            if i % 3 == 1:
                cyl(0.0145, 0.12, 8, at=(-0.06, -standoff, z), axis="X", mat="metal_rusted")
    return {"colliders": [K.collider_box((0, -standoff, (H + 1.0) / 2), (0.5, 0.1, H + 1.0))], "climbable": True}


# ============================================================================================== shed
def roof_shed(W=5.0, D=4.0, H=2.8):
    """Maintenance shed. Extents: roof overhang x/y +-2.7/+-2.2, side cabinet to x 3.7, roof vent top 3.6.
    Door on the front (-Y = Unity +Z) with the amber light (emit_amber) above it."""
    b = box(W, D, H, mat="corrugated", base=True)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(0.1, 0.1, H, at=(sx * (W / 2 - 0.02), sy * (D / 2 - 0.02), 0), mat="metal_dark", base=True, bevel=0.006)
    box(W, D, 0.12, at=(0, 0, 0), mat="metal_dark", base=True)
    box(W + 0.03, D + 0.03, 0.08, at=(0, 0, 0.12), mat="metal_dark", base=True)
    # roof slab with fascia + gutter at the front
    box(W + 0.4, D + 0.4, 0.2, at=(0, 0, H), mat="metal_dark", base=True, bevel=0.02)
    if detail():
        for sx in (-1, 0, 1):
            box(0.04, D + 0.38, 0.03, at=(sx * 1.6, 0, H + 0.2), mat="metal_dark", base=True)
    # door: frame, leaf, vision panel, handle, kick plate, hazard band, amber light + hood
    box(1.4, 0.06, 2.4, at=(0, -D / 2 - 0.01, 0.12), mat="black", base=True)
    box(1.3, 0.06, 2.3, at=(0.03, -D / 2 - 0.04, 0.15), mat="metal_painted", base=True, bevel=0.01)
    box(0.3, 0.012, 0.5, at=(-0.25, -D / 2 - 0.074, 1.5), mat="metal_dark", base=True)
    box(0.26, 0.012, 0.46, at=(-0.25, -D / 2 - 0.078, 1.52), mat="glass_dark", base=True)
    box(1.26, 0.008, 0.25, at=(0.03, -D / 2 - 0.074, 0.18), mat="metal_bare", base=True)
    box(0.04, 0.04, 0.18, at=(0.55, -D / 2 - 0.09, 1.1), mat="metal_bare", base=True)
    _frame = [(-0.75, 0.0), (0.75, 0.0)]
    for x, _ in _frame:
        box(0.08, 0.1, 2.5, at=(x, -D / 2 - 0.03, 0.12), mat="metal_dark", base=True)
    box(1.6, 0.1, 0.08, at=(0, -D / 2 - 0.03, 2.55), mat="metal_dark", base=True)
    box(0.3, 0.12, 0.12, at=(0, -D / 2 - 0.06, 2.65), mat="metal_dark", base=True)
    box(0.24, 0.02, 0.06, at=(0, -D / 2 - 0.12, 2.64), mat="emit_amber", base=True)
    box(0.34, 0.08, 0.015, at=(0, -D / 2 - 0.1, 2.77), mat="metal_dark", base=True)
    hazard_stripes(-0.72, 0.72, 2.565, 2.615, -D / 2 - 0.08, n=10)
    # access keypad with a cyan screen beside the door
    box(0.14, 0.04, 0.2, at=(0.95, -D / 2 - 0.02, 1.25), mat="metal_dark", base=True, bevel=0.006)
    box(0.1, 0.006, 0.05, at=(0.95, -D / 2 - 0.042, 1.39), mat="emit_cyan", base=True)
    if detail():
        for i in range(3):
            for j in range(3):
                box(0.022, 0.008, 0.018, at=(0.92 + i * 0.03, -D / 2 - 0.042, 1.28 + j * 0.03), mat="metal_bare", base=True)
        # rust run-off, door grime, a cage lamp + conduit on the side (+X wall)
        streak(-0.6, 2.75, 1.2, 0.12, -D / 2, seed=1)
        streak(1.9, 2.8, 1.6, 0.18, -D / 2, seed=2, mat="metal_dark")
        streak(-1.8, 2.8, 1.0, 0.12, -D / 2, seed=3)
        streak(-1.0, 2.8, 1.4, 0.15, W / 2, "+x", seed=4)
        streak(1.2, 2.8, 0.9, 0.1, -W / 2, "-x", seed=5, mat="metal_dark")
        warning_triangle((0.03, -D / 2 - 0.071, 1.95), 0.16)
        conduit([(1.6, -D / 2, 2.75), (1.6, -D / 2 - 0.03, 2.75), (1.6, -D / 2 - 0.03, 1.5), (1.6, -D / 2 - 0.03, 1.32)], 0.014, "metal_bare", 0.04, fittings=False)
        box(0.12, 0.05, 0.16, at=(1.6, -D / 2 - 0.025, 1.24), mat="metal_dark", base=True, bevel=0.006)
        led((1.63, -D / 2 - 0.05, 1.36), "emit_green", 0.006)
    # side window on +X
    box(0.04, 0.9, 0.6, at=(W / 2 + 0.01, -0.6, 1.4), mat="metal_dark", base=True)
    box(0.04, 0.82, 0.52, at=(W / 2 + 0.02, -0.6, 1.44), mat="glass_dark", base=True)
    for z in (1.55, 1.7, 1.85):
        box(0.05, 0.86, 0.02, at=(W / 2 + 0.035, -0.6, z), mat="metal_dark", base=True)
    if detail():
        # roof vent (top 3.6) + rain cap
        cyl(0.15, 0.45, 12, at=(1.2, 0.8, H + 0.2), mat="metal_bare")
        lathe([(0.001, H + 0.62), (0.26, H + 0.62), (0.27, H + 0.64), (0.001, H + 0.8)], 12, at=(1.2, 0.8, 0), mat="metal_dark")
        for k in range(3):
            a = k * math.tau / 3
            beam((1.2 + 0.14 * math.cos(a), 0.8 + 0.14 * math.sin(a), H + 0.6), (1.2 + 0.2 * math.cos(a), 0.8 + 0.2 * math.sin(a), H + 0.64), 0.015, mat="metal_dark")
        # side cabinet / generator at +X (x to 3.7) with louvres, LEDs, exhaust
        box(1.4, 1.0, 0.7, at=(3.0, -0.2, 0), mat="metal_dark", base=True, bevel=0.03)
        for i in range(6):
            box(0.9, 0.01, 0.02, at=(3.0, -0.705, 0.18 + i * 0.07), mat="black")
        led((3.55, -0.7, 0.6), "emit_green", 0.008)
        led((3.5, -0.7, 0.6), "emit_amber", 0.008)
        cyl(0.04, 0.25, 8, at=(3.5, 0.1, 0.7), mat="metal_rusted")
        hazard_stripes(2.32, 3.68, 0.03, 0.09, -0.7, n=10)
        tube(bend_path([(2.3, -0.2, 0.5), (2.6, -0.2, 0.5)], 0.05, 1), 0.02, 6, "rubber")
    return {"colliders": [K.collider_box((0, 0, H / 2), (W, D, H))]}


ASSETS = {
    "Roof_Parapet_4m": dict(fn=parapet, cat="rooftop", zones=["rooftops", "plaza"],
                            notes="Roof parapet 4 m x 0.9 m, 0.24 thick: steel coping with drip edges and joint straps, sealant joint, rusted "
                                  "scupper on the outer face (+Z), roof-side conduit (-Z), rust/water streaks, hairline cracks."),
    "Roof_Parapet_4m_Brick": dict(fn=parapet, kw={"mat": "brick"}, cat="rooftop", zones=["rooftops"], notes="Brick parapet (same details)."),
    "Roof_Parapet_Corner": dict(fn=parapet_corner, cat="rooftop", zones=["rooftops", "plaza"], notes="Corner block for parapet runs, coping with drips on all sides."),
    "AC_Unit": dict(fn=ac_unit, cat="rooftop", zones=["rooftops", "plaza"],
                    notes="Weathered rooftop condenser 1.4 x 1.0 x 1.0 on galvanised rails: dark frame, louvred coil guards on 3 sides (front +Z), "
                          "venturi fan ring with guard and blades on top, service panel (Unity -X) with rating plate, hazard label and green/red "
                          "status LEDs, disconnect box, insulated line set, rust run-off."),
    "Roof_Vent": dict(fn=roof_vent, cat="rooftop", zones=["rooftops"], notes="Louvred box exhaust on a flashed curb, standing seams, bird screen, hipped cap. 1.2 x 1.32 x 1.2."),
    "Roof_TurbineVent": dict(fn=turbine_vent, cat="rooftop", zones=["rooftops"], notes="Whirlybird turbine ventilator: 24 curved vanes, domed crown, swaged throat, flashing boot."),
    "WaterTank": dict(fn=water_tank, cat="rooftop", zones=["rooftops"],
                      notes="Rusted welded water tank (r 1.6) on a braced I-beam stand, conical roof with hatch and vent, hoops, weld seams, level gauge "
                            "with a cyan glow strip, ladder (+Z), outlet pipe with gate valve. 5.5 m tall."),
    "Antenna_Mast_5m": dict(fn=antenna_mast, cat="rooftop", zones=["rooftops", "plaza"],
                            notes="Tapered mast with yagi cross-arms, sector panel, coax run, base box with status LED, climbing pegs, guy wires with "
                                  "turnbuckles to ballast anchors, caged red beacon (emit_red)."),
    "Antenna_Mast_3m": dict(fn=antenna_mast, kw={"h": 3.0}, cat="rooftop", zones=["metro", "plaza", "rooftops"], notes="Short 3 m mast (camp / signal room)."),
    "Antenna_Mast_10m": dict(fn=antenna_mast, kw={"h": 10.0}, cat="rooftop", zones=["plaza"], notes="Tall 10 m mast (skyline)."),
    "RelayTower": dict(fn=relay_tower, cat="rooftop", zones=["rooftops"],
                       notes="12 m lattice relay tower, 4 m footprint: angle legs with splice plates, K/X-bracing, feeder ladder, mid-height red "
                             "obstruction lights, grating platform with yellow rails and a cyan LED toe-strip, equipment cabinet, four sector panels "
                             "(+-X), dish (+Z), ladder (Unity -X face), red beacon at 'beacon'."),
    "Relay_Transmitter": dict(fn=relay_transmitter, cat="rooftop", zones=["rooftops"],
                              notes="Relay transmitter cabinet 3 x 1.6 x 1 with 2.4 x 1.0 screen slot (lights up when repaired), bezel, LED status "
                                    "columns + cyan strips, keypad, hazard label, side fan, feeder cables, yellow battery pack with charge LEDs (Unity +X)."),
    "Roof_Hatch_Frame": dict(fn=roof_hatch_frame, cat="rooftop", zones=["rooftops"],
                             notes="1.6 m insulated curb around a 1.2 m roof opening: capping, liner, flashing band, hazard edge (front), hinge brackets (back)."),
    "Roof_Hatch_Lid": dict(fn=roof_hatch_lid, cat="rooftop", zones=["rooftops"], pivot="hinge",
                           notes="Hatch lid 1.5 m; pivot on the hinge (back edge); rotate about X to open. Raised stiffened panel, hinge knuckles, "
                                 "pull handle, gasket, paint wear."),
    "Ladder_4m": dict(fn=ladder, cat="rooftop", zones=["rooftops", "metro", "plaza"], pivot="wall-base",
                      notes="Wall ladder 4 m (+1 m gooseneck grab rails), yellow rungs every 0.3 m with weld collars, 0.18 m off the wall on bolted brackets."),
    "Roof_Shed": dict(fn=roof_shed, cat="rooftop", zones=["rooftops"],
                      notes="5 x 4 x 2.8 maintenance shed: corrugated cladding, corner posts, roof overhang with battens, door (+Z) with vision panel, "
                            "hazard band and amber light, cyan keypad, side window, roof vent, generator cabinet with LEDs (Unity -X side), grime."),
}
