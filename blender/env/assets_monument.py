"""The Aether Monument (plaza hero centrepiece), cyberpunk restyle.

A sleek hexagonal monolith of layered carbon / dark-glass / scratched-chrome panels with cyan edge seams, a holographic
glyph column and subtle neon rings, standing on a carved pedestal (tilted screen plaque + two glyph plaques) inside a
fountain basin with an LED lip, on two stone steps with LED nosings. The core holder, floating crystal, upper shard and
halo rings are separate assets (animated in game); world placements from the prototype are given in 'placements'
(plinth pivot at the plaza origin). Names, pivots, outer sizes, colliders and metadata match the prototype.
"""
import math
import random

from mathutils import Vector

import envkit as K
from envkit import box, cyl, lathe, tube, torus, beam, extrude, inset, faces_where, detail
from assets_vault import CH, CB, GD, arc_sweep, bolts, frame, gem, glyph, glyph_row

# monolith: hexagonal (flat faces at +-Y), circumradius R_BOT at Z_BOT tapering to R_TOP at Z_TOP
Z_BOT, Z_TOP, R_BOT, R_TOP = 1.45, 6.5, 1.25, 0.86


def _hex_r(z, z0=Z_BOT, z1=Z_TOP, r0=R_BOT, r1=R_TOP):
    return r0 + (r1 - r0) * (z - z0) / (z1 - z0)


def _hex_band(z0, z1, dr, mat, z_a=Z_BOT, z_b=Z_TOP, r_a=R_BOT, r_b=R_TOP, cham=0.02):
    """Hex collar hugging a tapered hex prism between z0..z1, proud by dr (chamfered)."""
    ra, rb = _hex_r(z0, z_a, z_b, r_a, r_b) + dr, _hex_r(z1, z_a, z_b, r_a, r_b) + dr
    return lathe([(ra - dr, z0), (ra, z0 + cham), (rb, z1 - cham), (rb - dr, z1)], 6, mat=mat, start=0.0,
                 close_bottom=False, close_top=False)


def _face_frame(i, z0, z1, z_a=Z_BOT, z_b=Z_TOP, r_a=R_BOT, r_b=R_TOP):
    """Local frame on hex face i (i=0 faces -Y): origin on the face centre line at z0, y along the slant, z out.
    Returns (matrix, slant length, side length at z0, side length at z1)."""
    th = math.radians(-90 + 60 * i)
    nh = Vector((math.cos(th), math.sin(th), 0.0))
    c30 = math.cos(math.radians(30))
    r0, r1 = _hex_r(z0, z_a, z_b, r_a, r_b), _hex_r(z1, z_a, z_b, r_a, r_b)
    p0 = nh * (r0 * c30) + Vector((0, 0, z0))
    p1 = nh * (r1 * c30) + Vector((0, 0, z1))
    right = Vector((-math.sin(th), math.cos(th), 0.0))
    return frame(p0, right=right, up=(p1 - p0)), (p1 - p0).length, r0, r1


def _trap(w0, w1, y0, y1, depth, mat, z=0.0, bevel=0.0):
    """Trapezoid plate in local face space (bottom width w0 at y0, top width w1 at y1), z..z+depth."""
    p = extrude([(-w0 / 2, y0), (w0 / 2, y0), (w1 / 2, y1), (-w1 / 2, y1)], depth, plane="XY", mat=mat, bevel=bevel)
    p.move(0, 0, z)
    return p


def _face_panels(i, z0, z1, holo=False, seed=0, z_a=Z_BOT, z_b=Z_TOP, r_a=R_BOT, r_b=R_TOP, inner_glow=None, mb=0.16, mg=0.42):
    """Layered panel stack on one hex face: carbon backing, dark-glass panel with chrome trims, optional holo glyphs.
    mb / mg: total width margins of the backing / glass relative to the face width."""
    m, L, s0, s1 = _face_frame(i, z0, z1, z_a, z_b, r_a, r_b)
    with K.placed(m):
        _trap(s0 - mb, s1 - mb, 0.0, L, 0.03, CB, bevel=0.008)
        _trap(s0 - mg, s1 - mg, 0.12, L - 0.12, 0.016, GD, z=0.03)
        mt = mg - 0.04
        for (a, b) in (((-(s0 - mt) / 2, 0.1), (-(s1 - mt) / 2, L - 0.1)), (((s0 - mt) / 2, 0.1), ((s1 - mt) / 2, L - 0.1))):
            beam((a[0], a[1], 0.045), (b[0], b[1], 0.045), 0.03, 0.03, mat=CH, up=(0, 0, 1))
        for y in (0.08, L - 0.08):
            w = (s0 + (s1 - s0) * y / L) - mt + 0.02
            box(w, 0.04, 0.03, at=(0, y, 0.03), base=True, mat=CH)
        if inner_glow:
            for y in (0.2, L - 0.2):
                w = (s0 + (s1 - s0) * y / L) - mg - 0.18
                box(w, 0.02, 0.006, at=(0, y, 0.046), base=True, mat=inner_glow)
        if holo:
            n = 5
            for k in range(n):
                y = L * (0.2 + 0.6 * k / (n - 1))
                glyph(0.3, seed * 17 + k, at=(0.0, y), depth=0.004, z=0.09, stroke=0.1, mat="holo_cyan")
            box(0.012, L * 0.72, 0.004, at=(-0.24, L * 0.5, 0.09), base=True, mat="holo_cyan")
            box(0.012, L * 0.72, 0.004, at=(0.24, L * 0.5, 0.09), base=True, mat="holo_cyan")
        if detail():
            bolts([(x * (s0 - 0.24) / 2, 0.05) for x in (-1, 1)] + [(x * (s1 - 0.24) / 2, L - 0.05) for x in (-1, 1)], r=0.02, h=0.012, z=0.03)


def _edge_seams(z0, z1, mat="emit_strip_cyan", z_a=Z_BOT, z_b=Z_TOP, r_a=R_BOT, r_b=R_TOP, w=0.04):
    """Glowing strips along the six hex vertex edges between z0..z1."""
    for i in range(6):
        a = math.radians(60 * i)
        d = Vector((math.cos(a), math.sin(a), 0))
        A = d * (_hex_r(z0, z_a, z_b, r_a, r_b) - 0.005) + Vector((0, 0, z0))
        B = d * (_hex_r(z1, z_a, z_b, r_a, r_b) - 0.005) + Vector((0, 0, z1))
        beam(A, B, w, w, mat=mat, up=(d.x, d.y, 0))


def _plaque(angle, screen=True, seed=0):
    """Tilted plaque on the pedestal slope (front one = the game's text screen)."""
    n0 = K.part_count()
    pl = box(2.4, 0.08, 0.5, mat="metal_dark", bevel=0.012)
    if screen:
        inset(pl, faces_where(pl, lambda f: f.normal.y < -0.9), 0.04, -0.008, mat="screen")
    else:
        inset(pl, faces_where(pl, lambda f: f.normal.y < -0.9), 0.05, -0.008, mat=CB)
        with K.placed(frame((0, -0.032, 0))):
            glyph_row(5, 0.3, seed, at=(0, 0), gap=0.45, depth=0.008, mat=CH)
    box(2.5, 0.05, 0.04, at=(0, 0.0, -0.27), mat=CH, bevel=0.008)
    box(2.3, 0.012, 0.025, at=(0, -0.044, -0.232), mat="emit_strip_cyan")
    for p in K.parts_since(n0):
        p.rot(x=-27).move(0, -2.45, 1.08).rot(z=angle)


def monument_base(seed=3):
    n = K.seg(64, 32)
    glow = "emit_strip_cyan"
    # ---- plinth: two stone steps with chrome nosings and LED lips under the noses, basin rim, basin floor, pedestal
    prof = [(0.001, 0.0), (7.48, 0.0), (7.48, 0.205), (7.6, 0.215), (7.6, 0.28), (7.58, 0.3),           # step 1 (nose at r 7.6)
            (6.6, 0.3), (6.48, 0.31), (6.48, 0.505), (6.6, 0.515), (6.6, 0.58), (6.58, 0.6),          # step 2
            (5.62, 0.6), (5.62, 0.84), (5.6, 0.88), (5.4, 0.88), (5.38, 0.84), (5.38, 0.66),         # basin rim
            (2.64, 0.66), (2.62, 0.7), (2.25, 1.44), (2.2, 1.48), (2.15, 1.5), (0.001, 1.5)]          # basin floor, pedestal
    p = lathe(prof, n, mat="concrete")

    def rz(f):
        c = f.calc_center_median()
        return c.xy.length, c.z
    p.set_mat("concrete_dark", where=lambda f: (abs(f.normal.z) < 0.5 and rz(f)[0] > 5.5) or (2.55 < rz(f)[0] < 5.4 and rz(f)[1] < 0.86))
    p.set_mat("metal_dark", where=lambda f: 5.37 < rz(f)[0] < 5.63 and rz(f)[1] > 0.85)
    p.set_mat(CB, where=lambda f: rz(f)[0] < 2.62 and 0.72 < rz(f)[1] < 1.42 and abs(f.normal.z) < 0.9)
    p.set_mat("metal_dark", where=lambda f: rz(f)[1] > 1.49)
    p.set_mat(CH, where=lambda f: (rz(f)[0] > 7.55 and 0.2 < rz(f)[1] < 0.3) or (6.55 < rz(f)[0] < 6.61 and 0.5 < rz(f)[1] < 0.6))
    # LED lips under the step noses and the basin's LED lip just above the water
    for (r, z) in ((7.6, 0.215), (6.6, 0.515)):
        lathe([(r - 0.115, z - 0.03), (r - 0.115, z - 0.005)], n, mat=glow, close_bottom=False, close_top=False)
    lathe([(5.38 - 0.004, 0.83), (5.38 - 0.004, 0.8)], n, mat=glow, close_bottom=False, close_top=False)
    lathe([(5.62 + 0.004, 0.84), (5.62 + 0.004, 0.86)], n, mat=CH, close_bottom=False, close_top=False)
    torus(5.632, 0.012, n_major=n, n_minor=4, mat="emit_neon_magenta").move(0, 0, 0.72)
    # water surface (separate slot -> Unity water shader)
    nw = K.seg(64, 32)
    w = K._new("water", "water")
    bm = w.bm
    a0 = [bm.verts.new((2.64 * math.cos(math.tau * i / nw), 2.64 * math.sin(math.tau * i / nw), 0.78)) for i in range(nw)]
    a1 = [bm.verts.new((5.4 * math.cos(math.tau * i / nw), 5.4 * math.sin(math.tau * i / nw), 0.78)) for i in range(nw)]
    for i in range(nw):
        j = (i + 1) % nw
        bm.faces.new((a0[i], a0[j], a1[j], a1[i]))
    # underwater light lines on the basin floor
    for i in range(16):
        s = box(1.6, 0.05, 0.01, at=(4.0, 0, 0.66), mat=glow, base=True)
        s.rot(z=i * 22.5 + 11.25)
    # pedestal: chrome ring at the waterline, neon ring at the top edge, plaques
    lathe([(2.66, 0.66), (2.66, 0.74), (2.6, 0.78)], n, mat=CH, close_bottom=False, close_top=False)
    torus(2.17, 0.014, n_major=n, n_minor=4, mat="emit_neon_cyan").move(0, 0, 1.5)
    _plaque(0.0, screen=True)
    _plaque(120.0, screen=False, seed=71)
    _plaque(240.0, screen=False, seed=73)
    for a in (60.0, 180.0, 300.0):
        s = box(0.05, 0.03, 0.62, mat=glow, base=True)
        s.rot(x=-26.57).move(0, -2.585, 0.78).rot(z=a)
    # ---- monolith
    lathe([(R_BOT, Z_BOT), (_hex_r(Z_TOP - 0.22), Z_TOP - 0.22), (0.001, Z_TOP - 0.22)], 6, mat="metal_dark", start=0.0, close_bottom=False)
    _hex_band(Z_BOT + 0.03, 1.78, 0.12, CH)
    _hex_band(1.78, 1.86, 0.06, "metal_dark")
    _hex_band(3.8, 3.89, 0.06, CH)
    _hex_band(3.95, 4.04, 0.06, CH)
    _hex_band(5.92, Z_TOP - 0.22, 0.07, CH)
    # crown: raised hex rim around the core-holder socket (top at 6.5) + emitter well
    lathe([(R_TOP + 0.07 - 0.02, Z_TOP - 0.22), (R_TOP + 0.05, Z_TOP), (R_TOP - 0.06, Z_TOP), (R_TOP - 0.08, Z_TOP - 0.15), (0.001, Z_TOP - 0.15)],
          6, mat=CH, start=0.0, close_bottom=False)
    torus(_hex_r(3.92) + 0.045, 0.014, n_major=6, n_minor=4, mat="emit_neon_cyan", start=0.0).move(0, 0, 3.92)
    for i in range(6):
        _face_panels(i, 1.95, 3.72, holo=(i in (0, 3)), seed=seed * 10 + i, inner_glow=glow if i % 2 else None)
        _face_panels(i, 4.12, 5.82, holo=False, seed=seed * 10 + i + 6, inner_glow=glow if i % 2 == 0 else None)
    _edge_seams(1.95, 3.72)
    _edge_seams(4.12, 5.82)
    # pedestal top deck: dark-glass ring with chrome tracks and radial glyph tiles
    cyl(2.0, 0.006, n, at=(0, 0, 1.5), mat=GD)
    for rad in (1.55, 1.95):
        torus(rad, 0.012, n_major=n, n_minor=3, mat=CH).move(0, 0, 1.5)
    # holographic data rings orbiting the upper monolith (segmented ticker bands)
    hr = random.Random(seed * 7)
    for (zr, rad, hgt) in ((5.05, 1.42, 0.14), (5.28, 1.48, 0.05)):
        a = hr.uniform(0, 20)
        while a < 350:
            span = hr.uniform(8, 34)
            arc_sweep([(-0.002, 0.0), (0.002, 0.0), (0.002, hgt), (-0.002, hgt)], a, min(a + span, 358), max(2, int(span / 8)), "holo_cyan", R=rad).move(0, 0, zr)
            a += span + hr.uniform(3, 9)
    # paved treads: radial joints on both steps
    if detail():
        for (r0, r1, z, cnt) in ((6.62, 7.54, 0.3, 36), (5.64, 6.54, 0.6, 30)):
            for i in range(cnt):
                b = box(r1 - r0, 0.018, 0.004, at=((r0 + r1) / 2, 0, z - 0.002), mat="metal_dark", base=True)
                b.rot(z=360 * (i + 0.5) / cnt)
    if detail():
        # in-ground uplights on step 2 aimed at the monolith
        for i in range(8):
            a = math.tau * i / 8 + 0.2
            x, y = math.cos(a) * 6.1, math.sin(a) * 6.1
            cyl(0.14, 0.012, 12, at=(x, y, 0.6), mat=CH)
            cyl(0.1, 0.016, 12, at=(x, y, 0.6), mat="emit_cyan")
        for i in range(24):
            a = math.radians(i * 15 + 7.5)
            cyl(0.03, 0.01, 6, at=(math.cos(a) * 5.5, math.sin(a) * 5.5, 0.88), mat="metal_bare", start=0.0)
    return {"colliders": [{"type": "capsule", "center": [0, 0.3, 0], "radius": 7.6, "height": 0.6, "direction": "Y", "note": "approximate the steps with two cylinders: r7.6 h0.3 and r6.6 h0.6"},
                          {"type": "capsule", "center": [0, 1.0, 0], "radius": 2.6, "height": 1.0, "direction": "Y"},
                          {"type": "box", "center": [0, 3.9, 0], "size": [2.2, 5.0, 2.2]}],
            "water": {"y": 0.78, "innerRadius": 2.64, "outerRadius": 5.4},
            "plaque": {"center": K.to_unity_vec((0, -2.5, 1.08)), "size": [2.3, 0.42], "tiltDeg": 27},
            "placements": {"Monument_CoreHolder": [0, 6.35, 0], "Monument_Crystal": [0, 7.45, 0], "Monument_UpperShard": [0.2, 8.6, -0.1],
                           "Monument_Ring_A": [0, 7.45, 0], "Monument_Ring_B": [0, 9.3, 0], "Monument_Ring_Fallen": [3.4, 0.6, -2.4]}}


def core_holder():
    """Chrome collar with a glowing iris and three armoured claws (cyan channels, emitter tips) cradling the core."""
    col = lathe([(0.001, 0.0), (0.85, 0.0), (0.88, 0.05), (0.84, 0.1), (0.8, 0.18), (0.55, 0.26), (0.5, 0.32), (0.001, 0.32)], 18, mat="metal_bare")
    col.set_mat(CB, where=lambda f: 0.06 < f.calc_center_median().z < 0.17 and abs(f.normal.z) < 0.8)
    col.set_mat(CH, where=lambda f: f.calc_center_median().z > 0.17)
    torus(0.68, 0.03, n_major=24, n_minor=5, mat="emit_cyan").move(0, 0, 0.21)
    torus(0.38, 0.02, n_major=24, n_minor=4, mat="emit_cyan").move(0, 0, 0.32)
    torus(0.46, 0.015, n_major=24, n_minor=4, mat=CH).move(0, 0, 0.31)
    for i in range(3):
        a = math.radians(i * 120 + 30)
        ca, sa = math.cos(a), math.sin(a)
        pts = [(ca * r, sa * r, z) for (r, z) in ((0.55, 0.25), (0.95, 0.55), (1.22, 1.0), (1.18, 1.5), (0.95, 1.9))]
        tube(pts, 0.09, 8, "metal_dark", radii=[0.11, 0.1, 0.09, 0.07, 0.05])
        tube([(ca * 1.0, sa * 1.0, 0.6), (ca * 1.18, sa * 1.18, 1.0), (ca * 1.15, sa * 1.15, 1.45)], 0.025, 4, "emit_strip_cyan")
        lathe([(0.06, 0.0), (0.001, 0.14)], 6, at=(ca * 0.93, sa * 0.93, 1.92), mat="emit_cyan")
        # chrome armour shells on the outer side of each claw segment (inside the claw's envelope)
        for (r0, z0, r1, z1, rad) in ((0.6, 0.3, 0.92, 0.55, 0.1), (0.98, 0.6, 1.17, 0.98, 0.088), (1.17, 1.06, 1.14, 1.46, 0.07)):
            A = Vector((ca * r0, sa * r0, z0))
            B = Vector((ca * r1, sa * r1, z1))
            tube([A, B], rad + 0.006, 8, CH)
        # inner carbon spine + emitter collar near the tip
        tube([(ca * 0.6, sa * 0.6, 0.38), (ca * 0.86, sa * 0.86, 0.62), (ca * 1.05, sa * 1.05, 1.0), (ca * 1.02, sa * 1.02, 1.5), (ca * 0.85, sa * 0.85, 1.82)],
             0.05, 6, CB)
        tube([(ca * 0.98, sa * 0.98, 1.78), (ca * 0.94, sa * 0.94, 1.86)], 0.065, 8, CH)
        if detail():
            # small ram between the collar and the claw
            tube([(ca * 0.5, sa * 0.5, 0.3), (ca * 0.78, sa * 0.78, 0.7)], 0.035, 8, "metal_dark")
            tube([(ca * 0.74, sa * 0.74, 0.64), (ca * 0.96, sa * 0.96, 0.98)], 0.02, 6, CH)
            for k in range(3):
                b = box(0.05, 0.03, 0.03, mat="emit_cyan")
                b.move(0, 0, 0).rot(z=math.degrees(a)).move(ca * 0.86, sa * 0.86, 0.12 - k * 0.03 + 0.0)
    return {"colliders": [K.collider_box((0, 0, 0.15), (1.7, 1.7, 0.4))], "coreCenter": K.to_unity_vec((0, 0, 1.1))}


def upper_shard(seed=5):
    """Hovering upper monolith piece: chrome base crown with a downward emitter, tapered carbon / dark-glass faces,
    cyan edge seams, chrome tip cap."""
    zb, zt, rb, rt = 0.0, 3.6, 0.72, 0.25

    def hr(z):
        return _hex_r(z, zb, zt, rb, rt)
    lathe([(0.001, 0.035), (0.42, 0.035), (0.44, 0.0), (rb * 0.9, 0.0), (rb, 0.06), (hr(0.34), 0.34), (0.001, 0.34)], 6, mat=CH, start=0.0)
    lathe([(hr(0.3), 0.3), (hr(zt - 0.2), zt - 0.2), (0.001, zt - 0.2)], 6, mat="metal_dark", start=0.0, close_bottom=False)
    _hex_band(0.34, 0.42, 0.02, "metal_bare", zb, zt, rb, rt)
    _hex_band(zt - 0.45, zt - 0.2, 0.02, CH, zb, zt, rb, rt)
    lathe([(hr(zt - 0.2), zt - 0.2), (hr(zt - 0.2) + 0.015, zt - 0.12), (rt, zt - 0.03), (rt * 0.9, zt), (0.001, zt)], 6, mat=CH, start=0.0, close_bottom=False)
    for i in range(6):
        _face_panels(i, 0.5, zt - 0.55, holo=False, seed=seed + i, z_a=zb, z_b=zt, r_a=rb, r_b=rt, mb=0.08, mg=0.2,
                     inner_glow="emit_strip_cyan" if i % 2 == 0 else None)
    _edge_seams(0.46, zt - 0.5, z_a=zb, z_b=zt, r_a=rb, r_b=rt, w=0.03)
    # downward emitter recessed in the base (faces the floating core)
    cyl(0.3, 0.01, 24, at=(0, 0, 0.022), mat="emit_cyan")
    torus(0.36, 0.012, n_major=24, n_minor=4, mat="emit_strip_cyan").move(0, 0, 0.026)
    torus(0.43, 0.014, n_major=24, n_minor=4, mat="metal_dark").move(0, 0, 0.02)
    return {"colliders": [K.collider_box((0, 0, 1.8), (1.3, 1.3, 3.6))]}


def monument_crystal(seed=7):
    """Aether core: faceted bipyramid (aether_energy) with twisted facet bands, inner emit_cyan heart and four shards."""
    rnd = random.Random(seed)
    gem([(0.002, -1.0, 0), (0.34, -0.62, 30), (0.5, -0.3, 0), (0.58, 0.15, 0), (0.42, 0.62, 30), (0.002, 1.15, 0)], 6, "aether_energy")
    lathe([(0.001, -0.42), (0.3, -0.3), (0.42, 0.0), (0.3, 0.3), (0.001, 0.42)], 12, mat="emit_cyan")
    for i in range(4):
        h = rnd.uniform(0.35, 0.6)
        c = lathe([(0.001, -h * 0.3), (h * 0.22, 0.0), (0.001, h)], 6, mat="aether_energy")
        c.rot(x=rnd.uniform(25, 60)).rot(z=i * 90 + rnd.uniform(-20, 20)).move(0, 0, rnd.uniform(-0.6, 0.2))
    return {"colliders": "none", "light": {"position": [0, 0, 0], "color": "#5fd8ff"}}


def halo_ring(R=2.9, arc=297.0, glow="emit_cyan", r=0.12, accent=None):
    """Broken halo: segmented scratched-chrome armour over a glowing core (visible in the gaps), carbon inlays,
    dark clamp collars (same outer envelope as the prototype ring)."""
    torus(R, r * 0.5, arc=arc, n_major=K.seg(48), n_minor=5, mat=glow)
    torus(R - r - 0.008, 0.022, arc=arc * 0.9, n_major=K.seg(48), n_minor=4, mat=accent or glow, start=arc * 0.05)
    nseg = 12
    gap = math.degrees(0.09 / R)
    sec = [(-r * 0.85, -r * 0.8), (-r, -r * 0.55), (-r, r * 0.55), (-r * 0.85, r * 0.8), (r * 0.85, r * 0.8), (r, r * 0.55), (r, -r * 0.55), (r * 0.85, -r * 0.8)]
    steps = 4 if K.LOD == 0 else 2
    for i in range(nseg):
        a0 = arc * i / nseg + (gap / 2 if i > 0 else 0.0)
        a1 = arc * (i + 1) / nseg - (gap / 2 if i < nseg - 1 else 0.0)
        arc_sweep(sec, a0, a1, steps, CH, R=R)
        if detail():
            arc_sweep([(r * 0.8, -r * 0.35), (r * 1.004, -r * 0.35), (r * 1.004, r * 0.35), (r * 0.8, r * 0.35)], a0 + 1.2, a1 - 1.2, steps, CB, R=R)
    if detail():
        for i in range(6):
            a = arc * (i + 0.5) / 6
            c = cyl(r + 0.03, 0.12, 10, mat="metal_dark", center=True, axis="Y")
            c.move(R, 0, 0).rot(z=a)
            b = box(0.03, 0.05, 0.05, mat=glow)
            b.move(R - r - 0.03, 0, 0).rot(z=a)
            for k in (-1, 1):
                c2 = cyl(r + 0.012, 0.025, 10, mat="metal_bare", center=True, axis="Y")
                c2.move(R, k * 0.07, 0).rot(z=a)
    return {"colliders": "none", "radius": R, "arcDeg": arc}


def fallen_ring():
    """63 deg broken halo segment lying on the plinth: chrome armour segments, dead (black) core and strip."""
    R, r = 2.8, 0.14
    torus(R, r * 0.5, arc=63, n_major=12, n_minor=6, mat="black", start=-31.5)
    torus(R - r - 0.008, 0.026, arc=56, n_major=12, n_minor=5, mat="black", start=-28)
    sec = [(-r * 0.85, -r), (-r, -r * 0.7), (-r, r * 0.7), (-r * 0.85, r), (r * 0.85, r), (r, r * 0.7), (r, -r * 0.7), (r * 0.85, -r)]
    gap = math.degrees(0.09 / R)
    for k in range(3):
        a0 = -31.5 + 21 * k + (gap / 2 if k > 0 else 0)
        a1 = -31.5 + 21 * (k + 1) - (gap / 2 if k < 2 else 0)
        arc_sweep(sec, a0, a1, 4, "metal_bare", R=R)
        if detail():
            arc_sweep([(r * 0.8, -r * 0.35), (r * 1.004, -r * 0.35), (r * 1.004, r * 0.35), (r * 0.8, r * 0.35)], a0 + 1.5, a1 - 1.5, 3, CB, R=R)
    for p in K._parts:
        p.move(-2.8, 0, 0)
    K.ground()
    return {"colliders": [K.collider_box((0.1, 0, 0.14), (0.6, 2.9, 0.28))]}


ASSETS = {
    "Monument_Base": dict(fn=monument_base, cat="monument", zones=["plaza"],
                          notes="Hero centrepiece. Plinth (r 7.6, two stone steps with chrome nosings + cyan LED lips), fountain basin (water slot at y 0.78) "
                                "with a cyan LED lip, magenta neon rim ring and underwater light lines, carved pedestal with the tilted screen plaque (front) "
                                "and two glyph plaques, sleek hexagonal monolith to 6.5 m: layered carbon / dark-glass / chrome panels, cyan edge seams, "
                                "holographic glyph columns (front/back), cyan neon mid ring, chrome crown with an emitter socket for the core holder. "
                                "'placements' gives the other monument parts' prototype positions."),
    "Monument_CoreHolder": dict(fn=core_holder, cat="monument", zones=["plaza"],
                                notes="Chrome collar with a glowing iris and three armoured claws (cyan channels, emitter tips) cradling the floating core; sits on the monolith crown (y 6.35)."),
    "Monument_UpperShard": dict(fn=upper_shard, cat="monument", zones=["plaza"],
                                notes="Hovering upper monolith piece (3.6 m): chrome base crown with a downward cyan emitter, carbon / dark-glass faces, cyan edge seams; tilt ~4 deg about Z."),
    "Monument_Crystal": dict(fn=monument_crystal, cat="monument", zones=["plaza"], pivot="centre",
                             notes="Aether core crystal cluster (faceted aether_energy shell + emit_cyan heart). Bob/rotate in game; point light at its centre."),
    "Monument_Ring_A": dict(fn=halo_ring, cat="monument", zones=["plaza"], pivot="centre",
                            notes="Broken halo ring R 2.9, 297 deg arc: segmented chrome over a cyan core glowing in the gaps. Horizontal; tilt +0.25 rad about X."),
    "Monument_Ring_B": dict(fn=halo_ring, kw={"R": 2.2, "arc": 324.0, "accent": "emit_neon_magenta"}, cat="monument", zones=["plaza"], pivot="centre",
                            notes="Upper halo ring R 2.2, 324 deg, cyan core + subtle magenta inner neon; tilt -0.35 rad."),
    "Monument_Ring_Fallen": dict(fn=fallen_ring, cat="monument", zones=["plaza"], notes="63 deg ring segment lying on the plinth (segmented chrome, dead glow core)."),
}
