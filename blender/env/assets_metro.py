"""Metro: tunnel segment, track, ticket gate, lamp fixture, generator, transmitter console, junction box, and neon
wayfinding (hanging LED sign box, wall line strip, line pylon, platform screen doors, neon arrow).

Track / tunnel modules run along Blender Y (Unity Z), 8 m long, pivot at RAIL-TOP height on the centre line.
Restyle: wet grimy concrete, steel arch ribs, cable trays and conduit, LED guide strips, signal lights; neon line colours
(magenta / cyan / yellow) with invented glyphs, never real text. Shared helpers come from assets_interior.
"""
import math
import random

import envkit as K
from envkit import box, cyl, lathe, tube, beam, extrude, inset, faces_where, detail, torus
from assets_interior import M, Flat, poly, vquad, stroke, ring2d, glyph, glyph_row, slots, bolts

LINES = ("emit_neon_magenta", "emit_neon_cyan", "emit_neon_yellow")


def _arch(hw, z_spring, z_crown, n=12):
    pts = []
    for i in range(n + 1):
        a = math.pi * i / n
        pts.append((hw * math.cos(a), z_spring + (z_crown - z_spring) * math.sin(a)))
    return pts  # from (+hw, spring) over the top to (-hw, spring)


def _contour(hw, floor, spring, crown, d, n):
    """Inner tunnel contour offset inward by d: right wall foot -> over the arch -> left wall foot."""
    return [(hw - d, floor)] + _arch(hw - d, spring, crown - d, n) + [(-(hw - d), floor)]


def rounded_rect(w, h, r, n=4):
    """CCW outline of a rounded rectangle centred at the origin (2D)."""
    pts = []
    for (cx, cy, a0) in ((w / 2 - r, -h / 2 + r, -90), (w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def hazard_band(x0, x1, z0, z1, y, fl, pitch=0.12, mat="black"):
    """Diagonal hazard stripes (flat quads facing -Y) over a yellow base, clipped to [x0, x1]."""
    h = z1 - z0
    x = x0 - h
    while x < x1:
        q = [(x, z0), (x + pitch / 2, z0), (x + pitch / 2 + h, z1), (x + h, z1)]
        c = _clip_x(q, x0, x1)
        if len(c) >= 3:
            poly([(a, y, b) for a, b in c], mat, fl)
        x += pitch


def _clip_x(pts, x0, x1):
    def clip(ps, keep, inter):
        out = []
        for i in range(len(ps)):
            a, b = ps[i - 1], ps[i]
            ka, kb = keep(a), keep(b)
            if kb:
                if not ka:
                    out.append(inter(a, b))
                out.append(b)
            elif ka:
                out.append(inter(a, b))
        return out

    def ix(xc):
        return lambda a, b: (xc, a[1] + (b[1] - a[1]) * (xc - a[0]) / (b[0] - a[0]))
    ps = clip(pts, lambda p: p[0] >= x0, ix(x0))
    return clip(ps, lambda p: p[0] <= x1, ix(x1)) if ps else ps


# ============================================================================================== tunnel
def _wet_band(x, z0, ztop, L, rnd, thick=0.012):
    """Wet grime band on a tunnel wall (YZ plane) with a ragged top edge and drip tongues."""
    pts = [(-L / 2, z0), (L / 2, z0)]
    k = K.seg(18, 6)
    for i in range(k + 1):
        y = L / 2 - L * i / k
        zz = ztop + rnd.uniform(-0.1, 0.08)
        if detail() and 0 < i < k and rnd.random() < 0.35:
            hgt = rnd.uniform(0.25, 0.7)
            pts += [(y, zz), (y - 0.03, zz + hgt), (y - 0.1, zz + hgt * 0.8), (y - 0.14, zz)]
        else:
            pts.append((y, zz))
    extrude(pts, thick, plane="YZ", at=(x, 0, 0), mat="concrete_wet")


def tunnel(L=8.0, hw=3.0, floor=-0.45, spring=3.2, crown=4.6, t=0.4, walkway=True):
    rnd = random.Random(21 if walkway else 22)
    n = K.seg(12, 6)
    inner = [(hw, floor)] + _arch(hw, spring, crown, n) + [(-hw, floor)]
    outer = [(-hw - t, floor)] + list(reversed(_arch(hw + t, spring, crown + t, n))) + [(hw + t, floor)]
    extrude(inner + outer, L, plane="XZ", mat="concrete_dark", name="lining")
    box(2 * hw + 2 * t, L, 0.3, at=(0, 0, floor - 0.3), mat="concrete_dark", base=True)
    # wet floor margins, wet grime bands on both walls
    box(hw - 1.7, L, 0.01, at=((hw + 1.7) / 2, 0, floor), mat="concrete_wet", base=True)
    box(hw - 1.7, L, 0.01, at=(-(hw + 1.7) / 2, 0, floor), mat="concrete_wet", base=True)
    _wet_band(hw - 0.006, floor, 1.05, L, rnd)
    _wet_band(-hw + 0.006, floor, 1.35 if walkway else 1.0, L, rnd)
    # steel arch ribs every 2 m (web + inner flange), anchor plates, bolts
    for yy in (-3.0, -1.0, 1.0, 3.0):
        c0 = _contour(hw, floor, spring, crown, -0.01, n)
        c1 = _contour(hw, floor, spring, crown, 0.09, n)
        extrude(c0 + list(reversed(c1)), 0.1, plane="XZ", at=(0, yy, 0), mat="metal_dark")
        if K.LOD < 2:
            c2 = _contour(hw, floor, spring, crown, 0.125, n)
            extrude(c1 + list(reversed(c2)), 0.26, plane="XZ", at=(0, yy, 0), mat="metal_dark")
        if detail():
            for sx in (-1, 1):
                box(0.05, 0.4, 0.3, at=(sx * (hw - 0.025), yy, floor), mat="metal_dark", base=True)
                bolts([(sx * (hw - 0.05) - (0.012 if sx > 0 else 0.0), yy + dy, floor + dz) for dy in (-0.14, 0.14) for dz in (0.08, 0.22)], 0.012, 0.012, axis="X")
    fl = Flat("black")
    if detail():
        # segmental lining joints (rings between the ribs + longitudinal seams)
        cs = _contour(hw, floor, spring, crown, 0.004, n)
        for yy in (-2.0, 0.0, 2.0):
            for (x0, z0), (x1, z1) in zip(cs, cs[1:]):
                poly([(x0, yy - 0.008, z0), (x1, yy - 0.008, z1), (x1, yy + 0.008, z1), (x0, yy + 0.008, z0)], "black", fl)
        for k in (3, n // 2 + 1, n - 1):
            (x0, z0), (x1, z1) = cs[k], cs[k + 1]
            mx, mz = (x0 + x1) / 2, (z0 + z1) / 2
            tx, tz = (x1 - x0), (z1 - z0)
            tl = math.hypot(tx, tz)
            tx, tz = tx / tl * 0.008, tz / tl * 0.008
            poly([(mx - tx, -L / 2, mz - tz), (mx + tx, -L / 2, mz + tz), (mx + tx, L / 2, mz + tz), (mx - tx, L / 2, mz - tz)], "black", fl)
    # crown LED guide line
    cz = crown - 0.006
    box(0.05, L, 0.008, at=(0, 0, cz), mat="emit_strip_cyan")
    box(0.12, L, 0.012, at=(0, 0, cz + 0.004), mat="metal_dark")
    # walkway (Unity +X side): concrete, checker plates, yellow nosing, LED edge, wall handrail
    if walkway:
        box(0.9, L, 0.9, at=(-hw + 0.45, 0, floor), mat="concrete", base=True, bevel=0.02)
        box(0.05, L, 0.05, at=(-hw + 0.9, 0, floor + 0.9), mat="metal_painted_yellow", base=True)
        box(0.006, L, 0.02, at=(-hw + 0.903, 0, floor + 0.8), mat="emit_strip_cyan", base=True)
        if detail():
            for k in range(4):
                box(0.7, 1.96, 0.012, at=(-hw + 0.44, -L / 2 + 1.0 + k * 2.0, floor + 0.9), mat="metal_plate", base=True, bevel=0.003)
            box(0.004, L, 0.12, at=(-hw + 0.902, 0, floor + 0.62), mat="black", base=True)
            hazard_band(-L / 2, L / 2, floor + 0.62, floor + 0.74, 0.0, Flat("metal_painted_yellow"), 0.16, "metal_painted_yellow")
            for p in K.parts_since(K.part_count() - 1):
                p.rot(z=90).move(-hw + 0.9 + 0.0045, 0, 0)
            for yy in (-3.0, -1.0, 1.0, 3.0):
                beam((-hw, yy + 0.3, 1.32), (-hw + 0.12, yy + 0.3, 1.32), 0.03, 0.03, mat="metal_dark")
            cyl(0.022, L, 8, at=(-hw + 0.12, -L / 2, 1.32), axis="Y", mat="metal_painted_yellow")
    # neon line stripe on the walkway-side wall, blue low guide strip on the cable side
    box(0.008, L, 0.04, at=(-hw + 0.018, 0, 1.6), mat="emit_strip_magenta")
    box(0.008, L, 0.03, at=(hw - 0.018, 0, 0.32), mat="emit_strip_blue")
    box(0.3, L, 0.25, at=(hw - 0.15, 0, floor), mat="concrete", base=True, bevel=0.015)
    if detail():
        for k in range(8):
            box(0.28, 0.98, 0.01, at=(hw - 0.15, -L / 2 + 0.5 + k, floor + 0.25), mat="metal_plate", base=True)
    # cable trays on the right wall (Unity -X): two tiers on cantilever brackets, cables, sagging feeders
    for zt in (1.75, 2.25):
        for yy in (-3.0, -1.0, 1.0, 3.0):
            beam((hw - 0.12, yy, zt), (hw - 0.47, yy, zt), 0.04, 0.05, mat="metal_dark")
            if detail():
                beam((hw - 0.12, yy, zt - 0.28), (hw - 0.36, yy, zt - 0.02), 0.03, 0.03, mat="metal_dark")
        box(0.42, L, 0.012, at=(hw - 0.335, 0, zt + 0.025), mat="grating", base=True)
        box(0.012, L, 0.07, at=(hw - 0.546, 0, zt + 0.025), mat="metal_dark", base=True)
        for k, (dx, r, m) in enumerate(((0.08, 0.035, "rubber"), (0.17, 0.03, "rubber"), (0.25, 0.04, "rubber"), (0.33, 0.022, "metal_painted_yellow"))):
            if K.LOD and k % 2:
                continue
            cyl(r, L, 8, at=(hw - 0.12 - dx, -L / 2, zt + 0.037 + r), axis="Y", mat=m)
    if detail():
        for k, (z0, sag, r) in enumerate(((1.42, 0.16, 0.022), (1.32, 0.22, 0.018))):
            pts = [(hw - 0.14 - 0.03 * k, -L / 2, z0)]
            for s in range(4):
                for i in range(5):
                    f = i / 5
                    yv = -L / 2 + s * 2 + f * 2
                    if s == 0 and i == 0:
                        yv += 0.04
                    pts.append((hw - 0.14 - 0.03 * k, yv, z0 - sag * 4 * f * (1 - f)))
            pts += [(hw - 0.14 - 0.03 * k, L / 2 - 0.04, z0), (hw - 0.14 - 0.03 * k, L / 2, z0)]
            tube(pts, r, 5, mat="rubber")
        for yy in (-4.0, -2.0, 0.0, 2.0):
            box(0.12, 0.03, 0.03, at=(hw - 0.08, yy + 0.02, 1.43), mat="metal_dark")
    # wall lamps (+-2 m, 3 m above rail): caged housings with warm diffusers (zone code adds halos here)
    for yy in (-2.0, 2.0):
        box(0.12, 0.5, 0.18, at=(hw - 0.06, yy, 3.0), mat="metal_dark", bevel=0.02)
        box(0.02, 0.42, 0.1, at=(hw - 0.125, yy, 3.0), mat="emit_strip_warm")
        if detail():
            for dz in (-0.04, 0.0, 0.04):
                box(0.012, 0.46, 0.008, at=(hw - 0.142, yy, 3.0 + dz), mat="metal_dark")
            tube([(hw - 0.08, yy + 0.25, 3.05), (hw - 0.05, yy + 0.45, 3.0), (hw - 0.05, yy + 0.6, 2.4), (hw - 0.12, yy + 0.6, 2.3)], 0.015, 5, mat="metal_bare")
    # conduits high on the left of the arch, strapped to the lining
    for (a, r, m) in ((128.0, 0.07, "metal_bare"), (140.0, 0.05, "metal_painted_yellow"), (151.0, 0.045, "metal_bare")):
        ca = math.radians(a)
        x = (hw - 0.2) * math.cos(ca)
        z = spring + (crown - 0.2 - spring) * math.sin(ca)
        cyl(r, L, 10, at=(x, -L / 2, z), axis="Y", mat=m)
        if detail():
            for yy in (-2.0, 0.0, 2.0):
                ox, oz = math.cos(ca) * 0.12, math.sin(ca) * 0.12
                beam((x, yy, z), (x + ox, yy, z + oz), 0.03, 0.04, mat="metal_dark")
                box(r * 2 + 0.03, 0.04, r * 2 + 0.03, at=(x, yy, z), mat="metal_dark")
    # signal head (walkway variant) / red marker light, drain channel with grating, puddles
    if walkway:
        sy = 3.55
        box(0.18, 0.06, 0.04, at=(hw - 0.09, sy + 0.1, 1.05), mat="metal_dark")
        box(0.18, 0.22, 0.62, at=(hw - 0.2, sy, 0.75), mat="black", base=True, bevel=0.02)
        for k, m in enumerate(("emit_red", "black", "emit_green")):
            zz = 1.25 - k * 0.19
            cyl(0.055, 0.02, 14, at=(hw - 0.2, sy - 0.13, zz), axis="Y", mat=m)
            if detail():
                cyl(0.075, 0.12, 14, at=(hw - 0.2, sy - 0.23, zz), axis="Y", mat="black", caps=False)
        box(0.06, 0.06, 0.95, at=(hw - 0.2, sy, floor + 0.25), mat="metal_dark", base=True)
    box(0.1, 0.12, 0.1, at=(hw - 0.05, -3.55, 1.0), mat="black", bevel=0.01)
    box(0.012, 0.07, 0.05, at=(hw - 0.106, -3.55, 1.0), mat="emit_red")
    box(0.3, L, 0.06, at=(hw - 0.5, 0, floor - 0.01), mat="black", base=True)
    if detail():
        box(0.28, L, 0.008, at=(hw - 0.5, 0, floor + 0.05), mat="grating", base=True)
        for (px, py, s) in ((2.0, -1.6, 0.28), (2.05, 2.4, 0.3), (-2.0 if not walkway else 2.0, 0.6, 0.24)):
            k = 9
            pts = [(px + s * (0.6 + 0.4 * rnd.random()) * math.cos(i * math.tau / k), py + s * 1.6 * (0.6 + 0.4 * rnd.random()) * math.sin(i * math.tau / k)) for i in range(k)]
            poly([(a, b, floor + 0.012) for a, b in pts], "water")
    return {"colliders": [K.collider_box((sx * (hw + t / 2), 0, (floor + crown) / 2), (t, L, crown - floor)) for sx in (-1, 1)] +
            [K.collider_box((0, 0, floor - 0.15), (2 * hw, L, 0.3))] + ([K.collider_box((-hw + 0.45, 0, floor + 0.45), (0.9, L, 0.9))] if walkway else []),
            "floorHeight": floor, "length": L}


RAIL = [(-0.075, -0.172), (0.075, -0.172), (0.075, -0.16), (0.009, -0.145), (0.009, -0.05), (0.035, -0.04), (0.035, 0.0), (-0.035, 0.0), (-0.035, -0.04), (-0.009, -0.05), (-0.009, -0.145), (-0.075, -0.16)]


def track(L=8.0, gauge=1.435, third_rail=True):
    rnd = random.Random(31)
    extrude([(-1.7, -0.45), (1.7, -0.45), (1.3, -0.2), (-1.3, -0.2)], L, plane="XZ", mat="gravel")
    n = int(L / 0.6)
    xc = gauge / 2 + 0.035
    for i in range(n):
        y = -L / 2 + 0.3 + i * 0.6
        extrude([(-0.13, -0.35), (0.13, -0.35), (0.105, -0.17), (-0.105, -0.17)], 2.5, plane="YZ", at=(0, y, 0), mat="concrete", bevel=0.012)
        if detail():
            for sx in (-1, 1):
                box(0.17, 0.2, 0.006, at=(sx * xc, y, -0.176), mat="rubber", base=True)
                for d in (-1, 1):
                    xx = sx * xc + d * 0.1
                    box(0.035, 0.07, 0.035, at=(xx, y, -0.17), mat="metal_dark", base=True, bevel=0.004)
                    tube([(xx, y - 0.04, -0.15), (xx - d * 0.03, y - 0.03, -0.142), (sx * xc + d * 0.072, y, -0.158), (xx - d * 0.03, y + 0.03, -0.142),
                          (xx, y + 0.04, -0.15)], 0.007, 4, mat="metal_rusted", caps=False)
    for sx in (-1, 1):
        r = extrude(RAIL, L, plane="XZ", mat="metal_rusted")
        r.set_mat("metal_bare", where=lambda f: f.normal.z > 0.9 and f.calc_center_median().z > -0.005)
        r.move(sx * xc, 0, 0)
    if third_rail:
        box(0.08, L, 0.1, at=(1.45, 0, -0.17), mat="metal_bare", base=True)
        box(0.16, L, 0.03, at=(1.45, 0, -0.05), mat="metal_painted_yellow", base=True)
        if detail():
            fl = Flat("black")
            hazard_band(-L / 2, L / 2, -0.048, -0.022, 0.0, fl, 0.14, "black")
            for p in K.parts_since(K.part_count() - 1):
                p.rot(z=90).move(1.45 + 0.0805, 0, 0)
        for i in range(int(L / 2)):
            yy = -L / 2 + 1 + i * 2
            box(0.1, 0.1, 0.12, at=(1.45, yy, -0.29), mat="plastic_dark", base=True)
            if detail():
                box(0.06, 0.14, 0.02, at=(1.45, yy, -0.175), mat="metal_dark", base=True)
                beam((1.45, yy, -0.06), (1.56, yy, -0.06), 0.02, 0.03, mat="metal_dark")
                beam((1.56, yy, -0.06), (1.56, yy, -0.24), 0.02, 0.02, mat="metal_dark")
    # cable trough with lids on the far side, track-bed LED markers, puddles
    box(0.3, L, 0.12, at=(-1.5, 0, -0.34), mat="concrete", base=True)
    if detail():
        for k in range(8):
            box(0.26, 0.97, 0.01, at=(-1.5, -L / 2 + 0.5 + k, -0.22), mat="metal_plate", base=True)
    for yy in (-2.2, 2.0):
        box(0.16, 0.08, 0.03, at=(0, yy, -0.205), mat="metal_dark", base=True, bevel=0.006)
        box(0.1, 0.03, 0.006, at=(0, yy, -0.175), mat="emit_cyan", base=True)
    if detail():
        for yy in (-3.4, -0.4, 2.6):
            k = 8
            pts = [(rnd.uniform(-0.25, 0.25) + 0.22 * (0.6 + 0.4 * rnd.random()) * math.cos(i * math.tau / k),
                    yy + 0.2 * (0.6 + 0.4 * rnd.random()) * math.sin(i * math.tau / k)) for i in range(k)]
            poly([(a, b, -0.196) for a, b in pts], "water")
    return {"colliders": [K.collider_box((0, 0, -0.32), (3.4, L, 0.25))], "railTop": 0.0, "gauge": gauge, "length": L}


# ============================================================================================== station props
def ticket_gate(light="emit_green"):
    """Ticket gate cabinet: long axis along Y (passage direction), glass paddle toward +X (Unity -X)."""
    prof = [(-0.15, 0.06), (0.15, 0.06), (0.175, 0.1), (0.175, 0.96), (0.15, 1.02), (-0.15, 1.02), (-0.175, 0.96), (-0.175, 0.1)]
    extrude(prof, 1.4, plane="XZ", mat="paint_glossy_dark", bevel=0.012)
    box(0.3, 1.34, 0.06, at=(0, 0, 0), mat="metal_dark", base=True)
    box(0.006, 1.3, 0.008, at=(0.153, 0, 0.004), mat=light, base=True)
    box(0.006, 1.3, 0.008, at=(-0.153, 0, 0.004), mat=light, base=True)
    # side inlay panels, top cap with light lines, glass top, card reader (top at 1.142)
    for sx in (-1, 1):
        box(0.006, 1.2, 0.64, at=(sx * 0.176, 0, 0.2), mat="metal_painted_white", base=True, bevel=0.002)
        box(0.006, 1.2, 0.012, at=(sx * 0.177, 0, 0.88), mat=light, base=True)
    box(0.37, 1.3, 0.04, at=(0, 0, 1.02), mat="plastic_dark", base=True, bevel=0.01)
    box(0.3, 1.1, 0.012, at=(0, 0.06, 1.06), mat="glass_dark", base=True, bevel=0.003)
    for sx in (-1, 1):
        box(0.01, 1.2, 0.014, at=(sx * 0.166, 0, 1.058), mat=light, base=True)
    box(0.16, 0.2, 0.05, at=(0, -0.45, 1.072), mat="plastic_dark", base=True, bevel=0.01)
    box(0.11, 0.13, 0.02, at=(0, -0.45, 1.122), mat=light, base=True)
    fl = Flat(light)
    if detail():
        # status symbol on the glass top + on the approach end: chevron (open) or cross (locked)
        def symbol(cx, cz, s, y, f):
            if light == "emit_red":
                stroke((cx - s, cz - s), (cx + s, cz + s), s * 0.35, y, light, fl=f)
                stroke((cx - s, cz + s), (cx + s, cz - s), s * 0.35, y, light, fl=f)
            else:
                for dz in (-s * 0.45, s * 0.45):
                    stroke((cx - s, cz - s * 0.4 + dz), (cx, cz + s * 0.4 + dz), s * 0.3, y, light, fl=f)
                    stroke((cx, cz + s * 0.4 + dz), (cx + s, cz - s * 0.4 + dz), s * 0.3, y, light, fl=f)
        n0 = K.part_count()
        symbol(0.0, 0.0, 0.05, 0.0, Flat(light))
        for p in K.parts_since(n0):
            p.rot(x=-90).move(0, 0.25, 1.0725)
        symbol(0.0, 0.62, 0.06, -0.7015, fl)
        # lane-flow band on both side panels: dark glass strip with light-coloured flow symbols
        for sx in (-1, 1):
            n0 = K.part_count()
            box(1.0, 0.006, 0.14, at=(0, 0.0, 0.5), mat="glass_dark", base=True)
            sf = Flat(light)
            for k in range(5):
                cx = -0.36 + k * 0.18
                if light == "emit_red":
                    stroke((cx - 0.03, 0.54), (cx + 0.03, 0.6), 0.012, -0.0035, light, fl=sf)
                    stroke((cx - 0.03, 0.6), (cx + 0.03, 0.54), 0.012, -0.0035, light, fl=sf)
                else:
                    stroke((cx - 0.03 * sx, 0.6), (cx + 0.02 * sx, 0.57), 0.012, -0.0035, light, fl=sf)
                    stroke((cx + 0.02 * sx, 0.57), (cx - 0.03 * sx, 0.54), 0.012, -0.0035, light, fl=sf)
            for p in K.parts_since(n0):
                p.rot(z=90 * sx).move(sx * 0.18, 0, 0)
        box(0.05, 0.006, 0.5, at=(0, -0.703, 0.12), mat="metal_bare", base=True)
        box(0.02, 0.008, 0.46, at=(0, -0.704, 0.14), mat=light, base=True)
    # glass paddles with chrome edges and light-coloured leading edge, hinge drums
    for dy in (-0.15, 0.15):
        pad = [(0.155, 0.55), (0.56, 0.55), (0.605, 0.6), (0.605, 0.92), (0.56, 0.97), (0.155, 0.97)]
        extrude(pad, 0.012, plane="XZ", at=(0, dy, 0), mat="glass")
        if detail():
            beam((0.16, dy, 0.972), (0.56, dy, 0.972), 0.014, 0.016, mat="chrome_scratched")
            box(0.006, 0.016, 0.3, at=(0.603, dy, 0.61), mat=light, base=True)
        cyl(0.035, 0.5, 12, at=(0.19, dy, 0.5), mat="metal_bare")
    box(0.03, 0.42, 0.52, at=(0.177, 0, 0.49), mat="metal_bare", base=True, bevel=0.006)
    return {"colliders": [K.collider_box((0, 0, 0.55), (0.37, 1.4, 1.1))]}


def lamp_tube(L=1.5, drop=0.3):
    """Hanging linear luminaire; pivot = ceiling attach point (top). The only emissive slot is emit_panel_warm
    (the zone code swaps every emit_* slot to emit_white / black)."""
    prof = [(-0.11, -0.295), (0.11, -0.295), (0.11, -0.318), (0.085, -0.352), (-0.085, -0.352), (-0.11, -0.318)]
    extrude(prof, L - 0.06, plane="YZ", mat="metal_painted_white", bevel=0.004)
    for sx in (-1, 1):
        extrude(prof, 0.03, plane="YZ", at=(sx * (L / 2 - 0.015), 0, 0), mat="metal_dark", bevel=0.003)
    box(L - 0.1, 0.15, 0.008, at=(0, 0, -0.356), mat="emit_panel_warm")
    if detail():
        # wire guard: U loops + longitudinal rods
        for k in range(6):
            x = -L / 2 + 0.12 + k * (L - 0.24) / 5
            tube([(x, -0.088, -0.34), (x, -0.08, -0.372), (x, 0.08, -0.372), (x, 0.088, -0.34)], 0.004, 4, mat="metal_dark", caps=False)
        for yy in (-0.05, 0.05):
            cyl(0.004, L - 0.24, 4, at=(-L / 2 + 0.12, yy, -0.375), axis="X", mat="metal_dark")
        box(0.3, 0.1, 0.045, at=(0.3, 0, -0.295), mat="metal_dark", base=True, bevel=0.006)
        box(0.12, 0.002, 0.03, at=(0.3, -0.051, -0.272), mat="metal_painted_yellow")
        tube([(0.42, 0.0, -0.27), (0.5, 0.04, -0.2), (0.55, 0.0, -0.1), (0.55, 0.0, -0.012)], 0.008, 5, mat="rubber")
    for x in (-L / 2 + 0.2, L / 2 - 0.2):
        cyl(0.004, 0.3, 4, at=(x, 0, -0.3), mat="metal_bare")
        cyl(0.01, 0.05, 6, at=(x, 0, -0.18), mat="chrome_scratched")
        box(0.08, 0.08, 0.012, at=(x, 0, -0.012), mat="metal_dark", base=True, bevel=0.003)
    return {"colliders": "none", "light": K.to_unity_vec((0, 0, -drop - 0.2))}


def generator(seed=3):
    rnd = random.Random(seed)
    fl = Flat("black")
    # skid with forklift pockets
    box(2.4, 1.6, 0.12, mat="metal_dark", base=True, bevel=0.01)
    for x in (-0.6, 0.6):
        box(0.3, 1.602, 0.07, at=(x, 0, 0.025), mat="black", base=True)
    g = box(2.2, 1.4, 1.5, at=(0, 0, 0.12), mat="metal_painted_yellow", base=True, bevel=0.04, bseg=2)
    # door seams, louvre doors, hazard band, glyph plates on both long faces
    for sy in (-1, 1):
        yf = sy * 0.7005
        n0 = K.part_count()
        ff = Flat("black")
        for x in (-0.95, 0.0, 0.95):
            vquad(x - 0.004, 0.26, x + 0.004, 1.52, 0.0, "black", ff)
        vquad(-1.0, 1.515, 1.0, 1.523, 0.0, "black", ff)
        hb = Flat("metal_painted_yellow")
        hazard_band(-1.06, 1.06, 0.13, 0.24, 0.0, hb, 0.14, "black")
        for p in K.parts_since(n0):
            if sy > 0:
                p.mirror("y")
            p.move(0, yf, 0)
        if detail():
            for i in range(8):
                l = box(0.9, 0.03, 0.05, mat="metal_dark")
                l.rot(x=30 * sy).move(0.48, sy * 0.715, 0.48 + i * 0.1)
            for zz in (0.42, 1.25):
                box(0.92, 0.02, 0.012, at=(0.48, sy * 0.71, zz), mat="metal_dark")
    # radiator end (+X): grating over a dark fan shroud
    box(0.012, 1.1, 1.1, at=(1.101, 0, 0.32), mat="black", base=True)
    box(0.012, 1.04, 1.04, at=(1.106, 0, 0.35), mat="grating", base=True)
    if detail():
        cyl(0.42, 0.01, 20, at=(1.102, 0, 0.87), axis="X", mat="metal_dark")
        for k in range(5):
            b = box(0.006, 0.08, 0.38, at=(1.103, 0, 0.87 + 0.19), mat="metal_dark")
            b.rot_about((1.103, 0, 0.87), x=k * 72)
    # control panel (front, -Y): screen (panelScreen), status lamps, e-stop, cyan status bar, glyph labels
    p = box(0.7, 0.08, 0.6, at=(-0.55, -0.71, 0.6), mat="metal_dark", base=True, bevel=0.02)
    inset(p, faces_where(p, lambda f: f.normal.y < -0.9), 0.05, -0.008, mat="screen")
    box(0.6, 0.05, 0.04, at=(-0.55, -0.74, 1.25), mat="emit_amber", base=True)
    box(0.6, 0.006, 0.01, at=(-0.55, -0.753, 1.23), mat="emit_strip_cyan")
    if detail():
        for x, m in ((-0.85, "emit_red"), (-0.6, "emit_green")):
            box(0.05, 0.02, 0.03, at=(x, -0.76, 0.75), mat=m)
        cyl(0.04, 0.03, 12, at=(-0.0, -0.73, 0.95), axis="Y", mat="metal_painted_yellow").move(0, -0.03, 0)
        cyl(0.03, 0.03, 12, at=(-0.0, -0.79, 0.95), axis="Y", mat="paint_glossy_red")
        box(0.22, 0.004, 0.08, at=(-0.0, -0.702, 1.08), mat="metal_painted_white")
        glyph_row(random.Random(seed), -0.08, 1.08, 0.05, 3, y=-0.705, mat="black", fl=fl)
        box(0.3, 0.004, 0.22, at=(0.55, -0.702, 1.2), mat="metal_painted_white")
        stroke((0.45, 1.12), (0.55, 1.29), 0.016, -0.705, "black", fl=fl)
        stroke((0.55, 1.29), (0.65, 1.12), 0.016, -0.705, "black", fl=fl)
        stroke((0.45, 1.12), (0.65, 1.12), 0.016, -0.705, "black", fl=fl)
        stroke((0.56, 1.25), (0.53, 1.19), 0.012, -0.705, "black", fl=fl)
        stroke((0.53, 1.19), (0.575, 1.19), 0.012, -0.705, "black", fl=fl)
        stroke((0.575, 1.19), (0.545, 1.14), 0.012, -0.705, "black", fl=fl)
    # roof: lifting eyes, intake hood, muffler + exhaust stack with rain cap (top 2.65), fuel / output hoses
    if detail():
        for x in (-0.8, 0.8):
            torus(0.06, 0.014, n_major=10, n_minor=4, mat="metal_dark").rot(x=90).move(x, 0, 1.68)
        box(0.6, 0.5, 0.12, at=(-0.45, 0.2, 1.62), mat="metal_painted_yellow", base=True, bevel=0.02)
        slots(-0.7, -0.2, 1.64, 1.72, 0.0, 3, "black", 0.016)
        for p in K.parts_since(K.part_count() - 3):
            p.move(0, -0.051, 0)
    cyl(0.15, 0.8, 14, at=(0.3, 0.4, 1.8), axis="X", mat="metal_rusted")
    for x in (0.4, 0.95):
        box(0.04, 0.34, 0.2, at=(x, 0.4, 1.62), mat="metal_dark", base=True)
    cyl(0.09, 0.95, 10, at=(0.8, 0.4, 1.6), mat="metal_rusted")
    cyl(0.12, 0.1, 10, at=(0.8, 0.4, 2.55), mat="metal_dark")
    if detail():
        f = box(0.2, 0.2, 0.012, at=(0, 0, 0), mat="metal_rusted")
        f.rot(y=-25).move(0.8, 0.4, 2.6)
        tube([(-1.0, 0.5, 1.4), (-1.0, 0.5, 2.0), (-1.0, 0.9, 2.4)], 0.05, 6, "rubber")
        tube([(-1.08, 0.72, 0.9), (-1.15, 0.84, 0.6), (-1.12, 0.87, 0.2), (-0.9, 0.88, 0.04)], 0.035, 6, "rubber")
        box(0.25, 0.08, 0.3, at=(-0.95, 0.72, 0.8), mat="metal_dark", base=True, bevel=0.01)
    return {"colliders": [K.collider_box((0, 0, 0.8), (2.4, 1.6, 1.62))], "panelScreen": {"center": K.to_unity_vec((-0.55, -0.76, 0.9)), "size": [0.6, 0.5]}}


def console_transmitter():
    """Signal-room transmitter: sculpted desk console + tall panel with a large screen (game tints it)."""
    rnd = random.Random(2)
    prof = [(-0.5, 0.0), (0.6, 0.0), (0.6, 1.12), (0.3, 1.12), (-0.646, 0.9), (-0.646, 0.86), (-0.58, 0.8), (-0.58, 0.1), (-0.5, 0.1)]
    extrude(prof, 4.0, plane="YZ", mat="paint_glossy_dark", bevel=0.01)
    box(3.98, 0.02, 0.1, at=(0, -0.51, 0), mat="metal_dark", base=True)
    box(3.9, 0.004, 0.012, at=(0, -0.6475, 0.88), mat="emit_strip_cyan")
    fl = Flat("black")
    if detail():
        for k in range(9):
            x = -1.6 + k * 0.4
            vquad(x - 0.003, 0.14, x + 0.003, 0.78, -0.5805, "black", fl)
        for x in (-1.2, 1.2):
            slots(x - 0.25, x + 0.25, 0.25, 0.5, -0.5806, 6, "black", 0.014, fl)
        vquad(-1.95, 0.7, 1.95, 0.712, -0.5808, "emit_strip_cyan", fl)
    # angled control surface (local frame on the slope, z up)
    with K.placed(M(0, -0.173, 1.01, rx=13)):
        box(3.8, 0.82, 0.012, at=(0, 0, 0), mat="plastic_dark", base=True, bevel=0.003)
        for i in range(10):
            x = -1.7 + i * 0.38
            m = "screen" if i % 3 == 0 else rnd.choice(["emit_green", "emit_amber", "plastic_dark"])
            box(0.32, 0.22, 0.012, at=(x, 0.16, 0.012), mat="black", base=True, bevel=0.003)
            box(0.3, 0.2, 0.004, at=(x, 0.16, 0.024), mat=m, base=True)
        if detail():
            lf = Flat("emit_cyan")
            for i in range(10):
                x0 = -1.84 + i * 0.38
                for r in range(2):
                    for c in range(5):
                        m = rnd.choice(["emit_cyan", "emit_cyan", "emit_amber", "black", "black", "emit_green"])
                        xx, yy = x0 + c * 0.05, -0.08 - r * 0.06
                        lf.face([(xx, yy, 0.0125), (xx + 0.03, yy, 0.0125), (xx + 0.03, yy + 0.03, 0.0125), (xx, yy + 0.03, 0.0125)], m)
            box(0.7, 0.18, 0.018, at=(0, -0.29, 0.012), mat="black", base=True, bevel=0.004)
            box(0.72, 0.2, 0.004, at=(0, -0.29, 0.012), mat="emit_strip_blue", base=True)
            for x in (-1.3, -1.15, 1.15, 1.3):
                box(0.02, 0.14, 0.006, at=(x, -0.27, 0.012), mat="black", base=True)
                box(0.04, 0.025, 0.025, at=(x, -0.27 + rnd.uniform(-0.05, 0.05), 0.018), mat="chrome_scratched", base=True)
        beam((-1.95, -0.43, 0.0), (1.95, -0.43, 0.0), 0.03, 0.03, mat="chrome_scratched")
    # back panel: chrome bezel + cyan LED frame around the big screen, glyph header
    bp = box(3.0, 0.3, 2.6, at=(0, 0.5, 1.0), mat="paint_glossy_dark", base=True, bevel=0.03)
    inset(bp, faces_where(bp, lambda f: f.normal.y < -0.9), 0.2, -0.02, mat="screen")
    for (x, z, sx_, sz_) in ((0, 1.18, 2.66, 0.02), (0, 3.42, 2.66, 0.02), (-1.32, 2.3, 0.02, 2.26), (1.32, 2.3, 0.02, 2.26)):
        box(sx_, 0.02, sz_, at=(x, 0.345, z), mat="chrome_scratched")
    for (x, z, sx_, sz_) in ((0, 1.15, 2.74, 0.012), (0, 3.45, 2.74, 0.012), (-1.37, 2.3, 0.012, 2.3), (1.37, 2.3, 0.012, 2.3)):
        box(sx_, 0.006, sz_, at=(x, 0.348, z), mat="emit_strip_cyan")
    if detail():
        glyph_row(random.Random(9), -0.45, 3.52, 0.1, 6, y=0.344, mat="emit_cyan", depth=0.01)
        n0 = K.part_count()
        bf = Flat("black")
        for x in (-0.75, 0.0, 0.75):
            vquad(x - 0.004, 1.15, x + 0.004, 3.45, 0.0, "black", bf)
        for x in (-1.1, -0.38, 0.38, 1.1):
            slots(x - 0.22, x + 0.22, 2.9, 3.3, 0.0, 7, "black", 0.016, bf)
            vquad(x - 0.1, 1.4, x + 0.1, 1.55, 0.0, "metal_painted_yellow", bf)
        for p in K.parts_since(n0):
            p.mirror("y").move(0, 0.6505, 0)
    # side towers: rack-style LED rows (emit_cyan), vents, vertical edge strips, cable looms at the back
    for sx in (-1, 1):
        box(0.4, 0.4, 3.6, at=(sx * 1.75, 0.5, 0.0), mat="metal_dark", base=True, bevel=0.03)
        box(0.006, 0.006, 3.2, at=(sx * 1.75 + sx * 0.17, 0.297, 0.2), mat="emit_strip_cyan", base=True)
        if detail():
            for i in range(6):
                box(0.3, 0.02, 0.04, at=(sx * 1.75, 0.29, 0.6 + i * 0.4), mat="emit_cyan" if i % 2 else "plastic_dark")
                for k in range(6):
                    xx = sx * 1.75 - 0.12 + k * 0.03
                    vquad(xx, 0.68 + i * 0.4, xx + 0.012, 0.69 + i * 0.4, 0.298, rnd.choice(["emit_green", "emit_cyan", "black"]), fl)
            slots(sx * 1.75 - 0.14, sx * 1.75 + 0.14, 2.9, 3.4, 0.299, 8, "black", 0.016, fl)
        tube([(sx * 1.55, 0.62, 2.2), (sx * 1.3, 0.66, 1.6), (sx * 1.2, 0.665, 0.6), (sx * 1.1, 0.65, 0.03)], 0.03, 6, mat="rubber")
        tube([(sx * 1.55, 0.6, 2.4), (sx * 1.25, 0.64, 1.7), (sx * 1.12, 0.66, 0.7), (sx * 1.0, 0.64, 0.03)], 0.022, 5, mat="rubber")
    return {"colliders": [K.collider_box((0, 0, 0.55), (4.0, 1.2, 1.1)), K.collider_box((0, 0.5, 1.8), (4.3, 0.4, 3.6))],
            "screen": {"center": K.to_unity_vec((0, 0.33, 2.3)), "size": [2.6, 2.2], "normal": [0, 0, 1], "material": "screen"}}


def junction_box(W=0.8, H=1.2, D=0.3):
    """Wall-mounted electrical cabinet; pivot = back centre at floor level (wall plane y=0)."""
    fl = Flat("black")
    for x in (-0.3, 0.3):
        box(0.04, 0.03, 1.5, at=(x, -0.015, 0.45), mat="metal_dark", base=True)
    box(W, D - 0.02, H, at=(0, -(D - 0.02) / 2, 0.6), mat="metal_painted", base=True, bevel=0.012)
    dr = box(W - 0.04, 0.02, H - 0.04, at=(0, -D + 0.01, 0.62), mat="metal_painted", base=True, bevel=0.006)
    inset(dr, faces_where(dr, lambda f: f.normal.y < -0.9), 0.05, 0.004)
    if detail():
        box(W - 0.02, 0.004, H - 0.02, at=(0, -D + 0.0185, 0.61), mat="black", base=True)
        slots(-0.25, 0.25, 0.68, 0.86, -D - 0.0045, 6, "black", 0.012, fl)
        for zz in (0.75, 1.55):
            cyl(0.012, 0.12, 8, at=(-W / 2 + 0.03, -D - 0.005, zz), mat="metal_bare")
        box(0.03, 0.03, 0.16, at=(W / 2 - 0.08, -D - 0.02, 1.1), mat="chrome_scratched", base=True, bevel=0.006)
        cyl(0.012, 0.015, 8, at=(W / 2 - 0.08, -D - 0.02, 1.32), axis="Y", mat="chrome_scratched").move(0, -0.0, 0)
        # hazard plate (warning triangle with an invented zig-zag), ID plate with invented glyphs, status window
        box(0.18, 0.006, 0.14, at=(0, -D - 0.006, 1.48), mat="metal_painted_yellow", base=True)
        yq = -D - 0.0095
        for a, b in (((-0.06, 1.5), (0.06, 1.5)), ((0.06, 1.5), (0.0, 1.605)), ((0.0, 1.605), (-0.06, 1.5))):
            stroke(a, b, 0.008, yq, "black", fl=fl)
        for a, b in (((0.012, 1.585), (-0.012, 1.55)), ((-0.012, 1.55), (0.012, 1.55)), ((0.012, 1.55), (-0.006, 1.515))):
            stroke(a, b, 0.006, yq, "black", fl=fl)
        box(0.2, 0.004, 0.05, at=(0, -D - 0.005, 1.33), mat="chrome_scratched")
        glyph_row(random.Random(4), -0.075, 1.355, 0.035, 3, y=-D - 0.0075, mat="black", fl=fl)
        box(0.16, 0.008, 0.05, at=(0, -D - 0.007, 1.2), mat="black", base=True)
        for k, m in enumerate(("emit_green", "emit_amber", "emit_red")):
            cyl(0.008, 0.006, 8, at=(-0.045 + k * 0.045, -D - 0.017, 1.225), axis="Y", mat=m if k != 2 else "black")
        vquad(-0.3, 1.71, 0.3, 1.715, -D - 0.0046, "emit_strip_cyan", fl)
    # conduits: three up from the floor, two up to the ceiling, couplings, glands and straps
    for x in (-0.2, 0.0, 0.2):
        cyl(0.03, 0.6, 8, at=(x, -0.06, 0.0), mat="metal_bare")
        if detail():
            cyl(0.036, 0.04, 8, at=(x, -0.06, 0.3), mat="metal_bare")
            cyl(0.04, 0.03, 6, at=(x, -0.06, 0.57), mat="metal_dark")
            box(0.09, 0.06, 0.01, at=(x, -0.06, 0.0), mat="metal_dark", base=True)
    tube([(0.0, -0.06, 1.8), (0.0, -0.06, 3.5)], 0.035, 8, "metal_bare")
    tube([(0.22, -0.18, 1.8), (0.22, -0.18, 2.1), (0.22, -0.05, 2.25), (0.22, -0.05, 3.5)], 0.022, 6, "metal_painted_yellow")
    if detail():
        for zz in (2.4, 3.0):
            box(0.1, 0.06, 0.03, at=(0.0, -0.05, zz), mat="metal_dark")
            box(0.07, 0.05, 0.025, at=(0.22, -0.045, zz + 0.1), mat="metal_dark")
        cyl(0.045, 0.04, 8, at=(0.0, -0.06, 1.8), mat="metal_dark")
    return {"colliders": [K.collider_box((0, -D / 2, 1.2), (W, D, H))]}


# ============================================================================================== neon wayfinding (new)
def _roundel(cx, cz, r, line, y, fl, seed):
    ring2d(cx, cz, r * 0.78, r, 0, 360, 24, y, line, fl)
    glyph(random.Random(seed), cx, cz, r * 1.0, y, "emit_white", w=r * 0.13, fl=fl)


def wayfinding_hanging(w=2.6, h=0.5, d=0.22, drop=0.5):
    """Ceiling-hung LED sign box, double sided. Pivot = TOP centre (ceiling attach point)."""
    zc = -(drop + h / 2)
    extrude(rounded_rect(w, h, 0.08, 3), d, plane="XZ", at=(0, 0, zc), mat="paint_glossy_dark", bevel=0.01)
    box(w - 0.12, d + 0.004, 0.012, at=(0, 0, zc + h / 2 - 0.006), mat="chrome_scratched")
    box(w - 0.2, 0.05, 0.006, at=(0, 0, zc - h / 2 - 0.002), mat="emit_strip_cyan")
    screens = []
    for side in (0, 1):
        n0 = K.part_count()
        fl = Flat("emit_white")
        yf = -d / 2 - 0.002
        box(w - 0.66, 0.004, h - 0.15, at=(0.25, -d / 2 - 0.002, zc + 0.03), mat="screen")
        box(w - 0.62, 0.006, h - 0.11, at=(0.25, -d / 2 + 0.001, zc + 0.03), mat="black")
        _roundel(-w / 2 + 0.22, zc + 0.03, 0.15, LINES[0], yf - 0.001, fl, 11)
        segs = [(-w / 2 + 0.08, -0.25, LINES[0]), (-0.25 + 0.02, 0.45, LINES[1]), (0.45 + 0.02, w / 2 - 0.08, LINES[2])]
        for (x0, x1, m) in segs:
            box(x1 - x0, 0.012, 0.03, at=((x0 + x1) / 2, -d / 2 - 0.004, zc - h / 2 + 0.04), mat=m)
        for p in K.parts_since(n0):
            if side:
                p.rot(z=180)
        screens.append({"center": K.to_unity_vec((0.25 * (1 - 2 * side), (-1 + 2 * side) * (d / 2 + 0.004), zc + 0.03)), "size": [round(w - 0.66, 3), round(h - 0.15, 3)],
                        "normal": [0, 0, 1 if side == 0 else -1]})
    for x in (-w / 2 + 0.35, w / 2 - 0.35):
        cyl(0.01, drop + 0.02, 6, at=(x, 0, zc + h / 2 - 0.01), mat="chrome_scratched")
        box(0.12, 0.12, 0.012, at=(x, 0, -0.012), mat="metal_dark", base=True, bevel=0.003)
        cyl(0.02, 0.04, 8, at=(x, 0, zc + h / 2), mat="metal_dark")
    return {"colliders": [K.collider_box((0, 0, zc), (w, d, h))], "screens": screens, "light": K.to_unity_vec((0, 0, zc - h / 2 - 0.4))}


def wayfinding_wall_strip(L=4.0, h=0.5, d=0.06, line="emit_neon_magenta"):
    """Wall wayfinding band, 4 m along X (chain end to end), pivot = wall plane at the band's bottom centre."""
    box(L, d - 0.012, h, at=(0, -(d - 0.012) / 2, 0), mat="paint_glossy_dark", base=True)
    for zz in (0.0, h - 0.016):
        box(L, 0.014, 0.016, at=(0, -d + 0.007, zz), mat="chrome_scratched", base=True)
    box(L, 0.012, 0.06, at=(0, -d + 0.012, 0.055), mat="black", base=True)
    cyl(0.011, L, 8, at=(-L / 2, -d + 0.008, 0.085), axis="X", mat=line)
    fl = Flat("emit_white")
    for k, x in enumerate((-1.0, 1.0)):
        box(1.7, 0.006, 0.3, at=(x, -d + 0.009, 0.15), mat="glass_dark", base=True)
        _roundel(x - 0.68, 0.3, 0.11, line, -d + 0.005, fl, 30 + k)
        glyph_row(random.Random(40 + k), x - 0.5, 0.3, 0.16, 4, y=-d + 0.005, mat="emit_white", w=0.016, fl=fl)
        # chevron arrows (direction of travel: Blender +X)
        for j in range(2):
            ax = x + 0.5 + j * 0.1
            stroke((ax, 0.38), (ax + 0.07, 0.3), 0.022, -d + 0.005, "emit_white", fl=fl)
            stroke((ax + 0.07, 0.3), (ax, 0.22), 0.022, -d + 0.005, "emit_white", fl=fl)
        vquad(x - 0.83, 0.16, x - 0.53, 0.172, -d + 0.005, line, fl)
    return {"colliders": "none", "light": K.to_unity_vec((0, -0.5, 0.3))}


def line_pylon(W=0.6, Dp=0.36, H=2.8):
    """Free-standing line totem: LED screens front/back, line-colour neon rings, lit glyph crown."""
    box(0.8, 0.52, 0.1, mat="metal_dark", base=True, bevel=0.012)
    for sy in (-1, 1):
        box(0.76, 0.006, 0.008, at=(0, sy * 0.262, 0.012), mat="emit_strip_cyan", base=True)
    rr = rounded_rect(W, Dp, 0.07, 3)
    extrude(rr, 2.25, plane="XY", at=(0, 0, 0.1), mat="paint_glossy_dark", bevel=0.01)
    fl = Flat("emit_white")
    screens = []
    for sy in (-1, 1):
        y = sy * (Dp / 2 + 0.002)
        box(0.46, 0.004, 1.1, at=(0, y, 0.95), mat="screen", base=True)
        for (x, z, a, b) in ((0, 0.94, 0.5, 0.014), (0, 2.06, 0.5, 0.014), (-0.243, 1.5, 0.014, 1.13), (0.243, 1.5, 0.014, 1.13)):
            box(a, 0.01, b, at=(x, sy * (Dp / 2 + 0.003), z), mat="chrome_scratched")
        screens.append({"center": K.to_unity_vec((0, sy * (Dp / 2 + 0.004), 1.5)), "size": [0.46, 1.1], "normal": [0, 0, 1 if sy < 0 else -1]})
    if detail():
        for side in (0, 1):
            n0 = K.part_count()
            ff = Flat("emit_white")
            for r in range(3):
                zz = 0.78 - r * 0.17
                _roundel(-0.18, zz, 0.055, LINES[r], -Dp / 2 - 0.002, ff, 50 + r)
                glyph_row(random.Random(60 + r), -0.1, zz, 0.08, 3, y=-Dp / 2 - 0.002, mat="emit_white", w=0.009, fl=ff)
            for p in K.parts_since(n0):
                if side:
                    p.rot(z=180)
    for k, m in enumerate(LINES):
        z = 2.0 + 0.1 * k + 0.12
        pts = [(x * 1.06, y * 1.12, z) for (x, y) in rounded_rect(W, Dp, 0.07, 3)]
        tube(pts, 0.012, 6, mat=m, closed=True)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x = sx * (W / 2 - 0.07 + 0.074 * 0.7071)
            y = sy * (Dp / 2 - 0.07 + 0.074 * 0.7071)
            b = box(0.01, 0.008, 1.7, at=(0, 0, 0.2), mat="emit_strip_cyan", base=True)
            b.rot(z=45 * sx * sy).move(x, y, 0)
    cr = box(0.64, 0.4, 0.32, at=(0, 0, 2.38), mat="paint_glossy_white", base=True, bevel=0.02)
    inset(cr, faces_where(cr, lambda f: abs(f.normal.z) < 0.1), 0.03, -0.006, mat="emit_panel_cyan")
    for sy in (-1, 1):
        glyph(random.Random(70), 0.0, 2.54, 0.2, sy * 0.198, "black", w=0.024, depth=0.008)
    box(0.66, 0.42, 0.02, at=(0, 0, 2.7), mat="chrome_scratched", base=True, bevel=0.004)
    cyl(0.05, 0.08, 12, at=(0, 0, 2.72), mat="emit_cyan")
    return {"colliders": [K.collider_box((0, 0, H / 2), (0.8, 0.52, H))], "screens": screens, "light": K.to_unity_vec((0, -0.6, 1.5))}


def platform_screen_door(L=4.0, H=2.6, D=0.3, ow=2.0, oh=2.15):
    """Platform screen door module, 4 m along X (chain end to end). Platform side -Y (Unity +Z), track side +Y."""
    fl = Flat("emit_cyan")
    box(L, D, 0.03, mat="metal_plate", base=True)
    box(L, 0.06, 0.006, at=(0, -D / 2 + 0.03, 0.03), mat="metal_painted_yellow", base=True)
    box(ow - 0.04, 0.012, 0.006, at=(0, -0.05, 0.03), mat="emit_strip_cyan", base=True)
    for sx in (-1, 1):
        # half end post (completes with the neighbour), door jamb post, fixed glass panel with kick panel
        box(0.08, D, H - 0.43, at=(sx * (L / 2 - 0.04), 0, 0.03), mat="paint_glossy_dark", base=True, bevel=0.006)
        box(0.08, D, oh, at=(sx * (ow / 2 + 0.04), 0, 0.03), mat="paint_glossy_dark", base=True, bevel=0.006)
        box(0.012, 0.012, oh - 0.2, at=(sx * (ow / 2 + 0.04), -D / 2 - 0.005, 0.12), mat="emit_strip_cyan", base=True)
        x0, x1 = ow / 2 + 0.08, L / 2 - 0.08
        xm, wf = (x0 + x1) / 2 * sx, x1 - x0
        box(wf, 0.06, 0.24, at=(xm, 0, 0.03), mat="paint_glossy_dark", base=True, bevel=0.004)
        box(wf, 0.012, oh - 0.27, at=(xm, 0, 0.27), mat="glass", base=True)
        box(wf, 0.014, 0.14, at=(xm, 0, 1.02), mat="glass_frosted", base=True)
        box(wf, 0.05, 0.03, at=(xm, 0, oh + 0.0), mat="paint_glossy_dark", base=True)
    # door leaves (closed): glass in chrome frames, rubber meeting seals, frosted band, line stripe
    for sx in (-1, 1):
        lx = sx * ow / 4
        yl = -0.04
        for (x, z, a, b) in ((lx - ow / 4 + 0.025, oh / 2, 0.05, oh - 0.06), (lx + ow / 4 - 0.025, oh / 2, 0.05, oh - 0.06),
                             (lx, 0.08, ow / 2, 0.1), (lx, oh - 0.07, ow / 2, 0.06)):
            box(a, 0.04, b, at=(x, yl, z + 0.03), mat="chrome_scratched", bevel=0.004)
        box(ow / 2 - 0.1, 0.012, oh - 0.26, at=(lx, yl, 0.16), mat="glass", base=True)
        box(ow / 2 - 0.1, 0.014, 0.12, at=(lx, yl, 1.04), mat="glass_frosted", base=True)
        box(ow / 2 - 0.1, 0.016, 0.02, at=(lx, yl, 1.0), mat=LINES[0], base=True)
        box(0.02, 0.044, oh - 0.08, at=(sx * 0.01, yl, 0.07), mat="rubber", base=True)
    # header: LED header strips both faces, info screen, door-state lamps, pixel band
    hz = oh + 0.03
    hb = box(L, D + 0.04, H - hz, at=(0, 0, hz), mat="paint_glossy_dark", base=True, bevel=0.012)
    for sy in (-1, 1):
        box(L - 0.02, 0.008, 0.016, at=(0, sy * (D / 2 + 0.022), hz + 0.02), mat="emit_strip_cyan")
        box(L, 0.006, 0.01, at=(0, sy * (D / 2 + 0.021), H - 0.03), mat="chrome_scratched")
    yh = -D / 2 - 0.021
    box(1.0, 0.006, 0.2, at=(0, yh, hz + 0.18), mat="screen", base=True)
    for sx in (-1, 1):
        box(0.12, 0.012, 0.05, at=(sx * 0.7, yh, hz + 0.26), mat="emit_amber")
        if detail():
            for k in range(14):
                xx = sx * (0.78 + k * 0.075)
                fl.face([(xx, yh - 0.0005, hz + 0.1), (xx + 0.05, yh - 0.0005, hz + 0.1), (xx + 0.05, yh - 0.0005, hz + 0.14), (xx, yh - 0.0005, hz + 0.14)],
                        LINES[k % 3] if k % 4 == 0 else "emit_cyan")
    box(0.3, 0.012, 0.03, at=(0, yh, hz + 0.06), mat="emit_red")
    cols = [K.collider_box((sx * (ow / 2 + (L / 2 - ow / 2) / 2), 0, (oh + 0.03) / 2), (L / 2 - ow / 2, D, oh + 0.03)) for sx in (-1, 1)]
    cols.append(K.collider_box((0, 0, (hz + H) / 2), (L, D + 0.04, H - hz)))
    cols.append(K.collider_box((0, -0.04, (oh + 0.03) / 2), (ow, 0.06, oh + 0.03)))
    return {"colliders": cols, "opening": {"width": ow, "height": oh, "doorCollider": 3},
            "screen": {"center": K.to_unity_vec((0, yh - 0.003, hz + 0.18)), "size": [1.0, 0.2], "normal": [0, 0, 1], "material": "screen"},
            "lights": [[round(c, 3) for c in K.to_unity_vec((0, -0.6, hz))], [round(c, 3) for c in K.to_unity_vec((0, 0.6, hz))]]}


def neon_arrow():
    """Wall neon arrow pointing UP (Blender +Z): roll the prop about its facing axis (Unity Z) to point it anywhere.
    Pivot = back centre (wall plane). Neon tube (emit_neon_cyan) on a dark acrylic backer with chrome stand-offs."""
    out = [(-0.08, -0.48), (0.08, -0.48), (0.08, 0.14), (0.26, 0.14), (0.0, 0.48), (-0.26, 0.14), (-0.08, 0.14)]
    back = [(-0.15, -0.55), (0.15, -0.55), (0.15, 0.08), (0.37, 0.08), (0.0, 0.58), (-0.37, 0.08), (-0.15, 0.08)]
    extrude(back, 0.012, plane="XZ", at=(0, -0.04, 0), mat="glass_dark", bevel=0.003)
    tube([(x, -0.06, z) for x, z in out], 0.011, 6, mat="emit_neon_cyan", closed=True)
    tube([(-0.13, -0.06, 0.2), (0.0, -0.06, 0.35), (0.13, -0.06, 0.2)], 0.009, 6, mat="emit_neon_magenta")
    if detail():
        for (x, z) in ((-0.13, 0.2), (0.13, 0.2)):
            cyl(0.013, 0.03, 8, at=(x, -0.075, z), axis="Y", mat="black")
        for (x, z) in ((-0.08, -0.3), (0.08, -0.3), (-0.08, 0.0), (0.08, 0.0), (-0.17, 0.14), (0.17, 0.14), (-0.13, 0.31), (0.13, 0.31)):
            box(0.03, 0.03, 0.012, at=(x, -0.05, z), mat="chrome_scratched")
        for (x, z) in ((-0.1, -0.45), (0.1, -0.45), (-0.28, 0.12), (0.28, 0.12)):
            cyl(0.012, 0.034, 8, at=(x, -0.034, z), axis="Y", mat="chrome_scratched")
        box(0.1, 0.02, 0.06, at=(0.0, -0.025, -0.38), mat="black", bevel=0.004)
    return {"colliders": "none", "light": K.to_unity_vec((0, -0.5, 0.05))}


ASSETS = {
    "Metro_Tunnel_8m": dict(fn=tunnel, cat="metro", zones=["metro"], pivot="rail-top-centre",
                            notes="8 m tunnel lining segment along Z: 6 m wide, arched crown at 4.6 m above rail top, floor at -0.45, walkway on "
                                  "the +X side (Unity) with checker plates, hazard edge, cyan LED edge strip and handrail; steel arch ribs every "
                                  "2 m, segmental lining joints, wet grime bands and floor margins, cyan crown LED line, magenta wall stripe, blue "
                                  "low guide strip, two-tier cable trays + sagging feeders and caged warm wall lamps (+-2 m, 3 m) on -X, conduits "
                                  "on the arch, signal head + red marker light, drain grating, puddles. Chain every 8 m."),
    "Metro_Tunnel_8m_NoWalk": dict(fn=tunnel, kw={"walkway": False}, cat="metro", zones=["metro"], pivot="rail-top-centre",
                                   notes="Tunnel segment without walkway (no signal head; red marker light only)."),
    "Metro_Track_8m": dict(fn=track, cat="metro", zones=["metro"], pivot="rail-top-centre",
                           notes="8 m standard-gauge track: ballast (gravel), tapered concrete sleepers every 0.6 m with rail pads, shoulders and "
                                 "e-clips, extruded rails (shiny heads), third rail with hazard-striped yellow cover on insulators and brackets, "
                                 "cable trough with lids, cyan track-bed LED markers, puddles. Rail top at y=0."),
    "Metro_TicketGate": dict(fn=ticket_gate, cat="metro", zones=["metro"],
                             notes="Ticket gate cabinet (passage along Z): sculpted glossy body, white side inlays, light-coloured top/side lines, "
                                   "floor wash, card reader and status chevrons (emit_green), glass paddles with chrome edges toward -X (Unity)."),
    "Metro_TicketGate_Red": dict(fn=ticket_gate, kw={"light": "emit_red"}, cat="metro", zones=["metro"], notes="Locked gate (red lights, cross symbols)."),
    "Metro_LampTube": dict(fn=lamp_tube, cat="metro", zones=["metro", "facility"], pivot="top-centre",
                           notes="Hanging 1.5 m linear luminaire: chamfered housing with end caps, wire guard, driver box, suspension cables "
                                 "and power cord; diffuser = emit_panel_warm (the only emit_* slot; code swaps it). 'light' = point-light anchor."),
    "Generator_Industrial": dict(fn=generator, cat="metro", zones=["metro", "rooftops"],
                                 notes="Diesel generator (yellow): skid with forklift pockets, door seams, louvres, hazard band, radiator grille "
                                       "with fan, control panel with screen (panelScreen), status lamps, e-stop, cyan status bar, invented glyph "
                                       "plates, lifting eyes, intake hood, muffler + exhaust stack with rain cap, hoses."),
    "Console_Transmitter": dict(fn=console_transmitter, cat="metro", zones=["metro"],
                                notes="Signal-room transmitter: sculpted desk with angled control surface (mini screens, LED button grids, "
                                      "keyboard, sliders), cyan LED lip, tall panel with a 2.6 x 2.2 screen slot (prototype transmitterGlow) in a "
                                      "chrome bezel with cyan LED frame and glyph header, rack-style side towers with LED rows, cable looms."),
    "Junction_Box": dict(fn=junction_box, cat="props", zones=["metro", "facility", "rooftops", "vault"], pivot="wall-floor",
                         notes="Wall electrical cabinet on strut rails: raised door panel, louvres, hinges, handle, warning and glyph ID plates, "
                               "status lamps, cyan status line; conduits with couplings from the floor and up to 3.5 m; pivot on the wall "
                               "plane at floor level."),
    "Metro_Wayfinding_Hanging": dict(fn=wayfinding_hanging, cat="metro", zones=["metro"], pivot="top-centre",
                                     notes="Ceiling-hung double-sided LED sign box 2.6 x 0.5 x 0.22 m, hung 0.5 m below the attach point "
                                           "(overall 2.6 x 1.0 x 0.22): blank 'screen' faces (front +Z / back -Z, see 'screens') for runtime "
                                           "text, magenta line roundel with an invented glyph, magenta/cyan/yellow line stripes, cyan "
                                           "downlight strip. 'light' = anchor under the sign."),
    "Metro_Wayfinding_Wall_Strip_4m": dict(fn=wayfinding_wall_strip, cat="metro", zones=["metro"], pivot="wall-base",
                                           notes="Wall wayfinding band 4 x 0.5 m, 0.06 deep (chain end to end along X): glossy band with chrome "
                                                 "trims, continuous magenta neon line stripe (emit_neon_magenta), two dark glass glyph panels "
                                                 "with line roundels, invented glyph rows and chevron arrows pointing Unity -X. Pivot = wall "
                                                 "plane at the band's bottom centre; mount at ~1.8-2.4 m. No collider."),
    "Metro_Line_Pylon": dict(fn=line_pylon, cat="metro", zones=["metro"],
                             notes="Free-standing line totem 0.8 x 2.8 x 0.52 m: glossy body with LED 'screens' front/back (0.46 x 1.1), "
                                   "line directory (roundels + invented glyph rows), magenta/cyan/yellow neon line rings, cyan corner LEDs, "
                                   "lit glyph crown (emit_panel_cyan) with a beacon, LED floor wash."),
    "Metro_Platform_Screen_Door_4m": dict(fn=platform_screen_door, cat="metro", zones=["metro"],
                                          notes="Platform screen door module 4 x 2.6 x 0.34 m (chain along X; half posts at both ends). "
                                                "Platform side +Z (Unity). Fixed glass panels with frosted bands, closed 2.0 x 2.15 sliding "
                                                "leaves in chrome frames with a magenta line stripe, header with cyan LED strips both faces, info "
                                                "'screen', amber door lamps, red closing light and a line-colour pixel band. Colliders: two side "
                                                "panels, header, door leaves (index 3, disable to open)."),
    "Metro_Neon_Arrow": dict(fn=neon_arrow, cat="metro", zones=["metro", "plaza"], pivot="back-centre",
                             notes="Wall neon arrow 0.74 x 1.13 x 0.07 m pointing UP (Unity +Y): cyan neon outline with a magenta chevron "
                                   "on a dark acrylic backer and chrome stand-offs. Pivot = back centre; roll about Unity Z (rotZ) to point "
                                   "it in any direction. No collider; 'light' = cyan fill anchor."),
}
