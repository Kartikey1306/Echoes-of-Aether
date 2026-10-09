"""Street furniture and clutter (Blender, envkit): dumpster, trash-bag piles, wall AC unit, fire escape, yatai food cart,
steam grate, manhole, LED bollard, water barrier, tram shelter with lit ads, charging totem, data booth, capsule-toy
vending bank, cable wall anchor. Front = -Y (Unity +Z). Floor props pivot at base centre; wall props at the wall plane.
"""
import math
import random

import bmesh
from mathutils import Vector

import st_layout as LY
from stgeo import K, Meta, bmin, card, front_card, side_card


# ============================================================================================== dumpster
def dumpster(colour="metal_painted_green", lid_open=0.0, seed=1):
    M = Meta()
    W, D, H = 1.9, 1.1, 1.15
    # tapered body: profile in YZ (front slopes back), extruded along X
    prof = [(-D / 2 + 0.12, 0.18), (D / 2, 0.18), (D / 2, H), (-D / 2, H)]
    body = K.extrude(prof, W, plane="YZ", mat=colour, bevel=0.015)
    bmin(-W / 2 - 0.03, -D / 2 - 0.03, H - 0.06, W / 2 + 0.03, D / 2 + 0.03, H, colour, bevel=0.01)    # top rim
    for s in (-1, 1):  # side forklift sleeves + reinforcing ribs
        bmin(s * W / 2, -0.3, 0.55, s * (W / 2 + 0.06), 0.3, 0.72, "metal_dark", bevel=0.01)
        for y in (-0.35, 0.0, 0.35):
            bmin(s * W / 2, y - 0.03, 0.2, s * (W / 2 + 0.04), y + 0.03, H - 0.08, colour)
    for x in (-0.6, 0.0, 0.6):
        bmin(x - 0.035, -D / 2 + 0.08, 0.25, x + 0.035, -D / 2 + 0.13, H - 0.08, colour)
    bmin(-W / 2 + 0.05, -D / 2 + 0.05, 0.12, W / 2 - 0.05, D / 2 - 0.05, 0.2, "metal_dark")
    for x in (-W / 2 + 0.2, W / 2 - 0.2):
        for y in (-D / 2 + 0.22, D / 2 - 0.15):
            K.cyl(0.07, 0.05, 12, at=(x - 0.025, y, 0.07), mat="rubber", axis="X")
            bmin(x - 0.04, y - 0.04, 0.12, x + 0.04, y + 0.04, 0.16, "metal_dark")
    # lids: two plastic lids hinged at the back; one may be propped open
    for i, s in enumerate((-1, 1)):
        lid = bmin(s * 0.02 if s > 0 else -W / 2 - 0.02, -D / 2 - 0.05, H, W / 2 + 0.02 if s > 0 else -0.02, D / 2 + 0.04, H + 0.05, "plastic_dark", bevel=0.01)
        if i == 1 and lid_open > 0:
            lid.rot_about((0, D / 2 + 0.04, H + 0.025), x=-lid_open)
    if K.detail():
        # overflow: a bag and cardboard on top / leaning
        r = random.Random(seed)
        bag(0.32, 0.28, 0.3, (r.uniform(-0.5, -0.2), r.uniform(-0.2, 0.2), H + 0.02), "st_bag_black", seed)
        bmin(W / 2 - 0.05, -0.35, 0.05, W / 2 + 0.03, 0.25, 0.75, "cardboard_wet").rot_about((W / 2, 0, 0.05), y=-12)
        bmin(-0.3, -D / 2 - 0.006, 0.6, 0.3, -D / 2 + 0.01, 0.82, "metal_painted_white")      # hazard plate
    M.col((0, 0, H / 2 + 0.03), (W + 0.12, D + 0.08, H + 0.06))
    return M.done()


# ============================================================================================== trash bags
def bag(sx, sy, sz, at, mat, seed, tie=True):
    """Deformed garbage bag: icosphere squashed onto the ground, lumpy, with a twisted tie on top."""
    r = random.Random(seed)
    p = K._new(mat, "bag")
    bmesh.ops.create_icosphere(p.bm, subdivisions=3 if K.LOD == 0 else 1, radius=0.5)
    ph = [r.uniform(0, 6.28) for _ in range(6)]

    def f(co):
        x, y, z = co
        n = 1 + 0.08 * math.sin(x * 9 + ph[0]) * math.sin(y * 8 + ph[1]) + 0.07 * math.sin(z * 11 + ph[2]) + 0.05 * math.sin((x + y) * 13 + ph[3]) \
            + 0.035 * math.sin(x * 23 + z * 17 + ph[5]) + 0.025 * math.sin(y * 29 - z * 21 + ph[4])   # wrinkles
        z2 = z if z > -0.25 else -0.25 - (z + 0.25) * 0.15          # flat bottom
        if z > 0.3:                                                   # gathered neck
            k = (z - 0.3) / 0.2
            x, y = x * (1 - 0.6 * k), y * (1 - 0.6 * k)
        return (x * sx * n, y * sy * n, (z2 + 0.27) * sz * (0.95 + 0.1 * math.sin(x * 5 + ph[4])))
    p.displace(f)
    p.move(*at)
    if tie and K.detail():
        tx, ty, tz = at[0], at[1], at[2] + sz * 0.77
        K.cyl(0.035, 0.07, 6, at=(tx, ty, tz), mat=mat, r2=0.015)
        for a in (0.5, 2.3):
            K.tube([(tx, ty, tz + 0.06), (tx + 0.07 * math.cos(a), ty + 0.07 * math.sin(a), tz + 0.11)], 0.012, 4, mat=mat)
    return p


def bag_pile(n=5, seed=3, mats=("st_bag_black", "st_bag_black", "st_bag_black", "st_bag_blue", "st_bag_white")):
    M = Meta()
    r = random.Random(seed)
    placed = []
    for i in range(n):
        for _ in range(20):
            x, y = r.uniform(-0.55, 0.55), r.uniform(-0.35, 0.35)
            if all((x - a) ** 2 + (y - b) ** 2 > 0.12 for a, b, _ in placed):
                break
        s = r.uniform(0.75, 1.15)
        z = 0.0
        for a, b, hh in placed:
            if (x - a) ** 2 + (y - b) ** 2 < 0.2:
                z = max(z, hh * 0.55)
        sz = 0.42 * s
        bag(0.42 * s, 0.38 * s, sz, (x, y, z), r.choice(mats), seed * 31 + i)
        placed.append((x, y, z + sz))
    if K.detail():
        bmin(0.35, 0.2, 0, 0.75, 0.55, 0.32, "cardboard_wet").rot_about((0.55, 0.37, 0), z=r.uniform(-30, 30))
        K.cyl(0.035, 0.12, 8, at=(-0.7, -0.3, 0), mat="metal_bare", axis="X")
    M.col((0, 0, 0.3), (1.4, 0.95, 0.6))
    return M.done()


# ============================================================================================== wall AC unit
def ac_unit(drip=True):
    """Split-system outdoor unit on wall brackets (pivot: wall plane at the bracket base)."""
    M = Meta()
    W, D, H = 0.82, 0.3, 0.56
    y0 = -0.08
    body = bmin(-W / 2, y0 - D, 0.04, W / 2, y0, 0.04 + H, "metal_painted_white", bevel=0.012)
    # fan opening: dark disc, guard rings and spokes
    cx, cz = -0.12, 0.04 + H / 2
    K.cyl(0.21, 0.02, 24, at=(cx, y0 - D - 0.005, cz), mat="black", axis="Y")
    if K.detail():
        for rr in (0.08, 0.14, 0.2):
            K.torus(rr, 0.004, n_major=24, n_minor=4, mat="metal_bare").rot(x=90).move(cx, y0 - D - 0.012, cz)
        for k in range(8):
            a = k / 8 * math.tau
            K.tube([(cx, y0 - D - 0.012, cz), (cx + 0.2 * math.cos(a), y0 - D - 0.012, cz + 0.2 * math.sin(a))], 0.003, 3, mat="metal_bare")
        for i in range(10):  # side fin louvres on the right
            z = 0.08 + i * 0.05
            bmin(0.14, y0 - D - 0.012, z, 0.38, y0 - D + 0.002, z + 0.012, "metal_painted_white").rot_about((0.26, y0 - D, z), x=25)
        K.tube([(W / 2 - 0.05, y0 - 0.05, 0.1), (W / 2 + 0.03, y0 - 0.05, 0.1), (W / 2 + 0.03, -0.01, 0.1)], 0.012, 6, mat="metal_bare")
        K.tube([(W / 2 - 0.05, y0 - 0.12, 0.14), (W / 2 + 0.06, y0 - 0.12, 0.14), (W / 2 + 0.06, -0.01, 0.4)], 0.008, 6, mat="rubber")
        if drip:
            K.tube([(-W / 2 + 0.1, y0 - 0.15, 0.04), (-W / 2 + 0.1, y0 - 0.15, -0.6)], 0.01, 5, mat="plastic_dark")
    for x in (-W / 2 + 0.12, W / 2 - 0.12):     # L brackets
        bmin(x - 0.02, y0 - D - 0.04, 0.0, x + 0.02, 0, 0.04, "metal_rusted")
        K.beam((x, -0.01, -0.35), (x, y0 - D, 0.02), 0.035, mat="metal_rusted")
    bmin(-W / 2 - 0.02, -0.02, -0.4, W / 2 + 0.02, 0.0, 0.06, "metal_rusted")
    return M.done()


# ============================================================================================== fire escape
def fire_escape(W=3.0, floors=2, fh=3.4):
    """Two-landing fire escape segment: grating landings, railings, a stair flight between them, drop ladder below the
    lowest landing. Pivot: wall plane at the lower landing deck. Stack segments every 2 floors."""
    M = Meta()
    Dp = 1.1
    for f in range(floors):
        z = f * fh
        bmin(-W / 2, -Dp, z - 0.04, W / 2, 0, z, "grating")
        for y in (-Dp, -0.02):
            bmin(-W / 2, y - 0.03, z - 0.12, W / 2, y + 0.03, z, "metal_dark")
        for x in (-W / 2, W / 2):
            bmin(x - 0.03, -Dp, z - 0.12, x + 0.03, 0, z, "metal_dark")
        # rail posts + top rail + mid rail on the street side and the ends
        n = 6
        for i in range(n + 1):
            x = -W / 2 + W * i / n
            K.cyl(0.016, 1.0, 6, at=(x, -Dp + 0.02, z), mat="metal_dark")
        for zz in (1.0, 0.5):
            K.tube([(-W / 2, -0.02, z + zz), (-W / 2, -Dp + 0.02, z + zz), (W / 2, -Dp + 0.02, z + zz), (W / 2, -0.02, z + zz)], 0.016, 6, mat="metal_dark", caps=True)
        if K.detail():
            for i in range(n * 3):
                x = -W / 2 + W * (i + 0.5) / (n * 3)
                K.cyl(0.007, 0.5, 4, at=(x, -Dp + 0.02, z + 0.5), mat="metal_dark")
        # diagonal braces to the wall
        for x in (-W / 2 + 0.15, W / 2 - 0.15):
            K.beam((x, -Dp + 0.05, z - 0.1), (x, -0.02, z - 0.9), 0.04, mat="metal_dark")
        # stair flight up to the next landing (inside the landing depth, along X)
        if f < floors - 1:
            run = W - 1.0
            ang = math.atan2(fh, run)
            L = math.hypot(fh, run)
            for s in (-0.95, -0.25):
                K.beam((-W / 2 + 0.5, s, z + 0.02), (W / 2 - 0.5, s, z + fh - 0.02), 0.03, 0.18, mat="metal_dark")
            steps = 11
            for k in range(1, steps):
                t = k / steps
                x = -W / 2 + 0.5 + run * t
                bmin(x - 0.12, -0.93, z + fh * t - 0.015, x + 0.12, -0.27, z + fh * t + 0.015, "grating")
            K.tube([(-W / 2 + 0.5, -0.95, z + 0.9), (W / 2 - 0.5, -0.95, z + fh + 0.9)], 0.015, 6, mat="metal_dark")
    # retracted drop ladder under the lowest landing
    for x in (-W / 2 + 0.35, -W / 2 + 0.75):
        K.cyl(0.015, 2.2, 6, at=(x, -Dp + 0.1, -2.3), mat="metal_dark")
    for i in range(8):
        K.cyl(0.01, 0.4, 5, at=(-W / 2 + 0.35, -Dp + 0.1, -2.2 + i * 0.28), mat="metal_dark", axis="X")
    return M.done()


# ============================================================================================== food cart (yatai)
def food_cart(seed=5):
    M = Meta()
    L_, D_, H_ = 2.1, 1.0, 0.95
    bmin(-L_ / 2, -D_ / 2, 0.35, L_ / 2, D_ / 2, H_, "wood", bevel=0.01)
    bmin(-L_ / 2 - 0.08, -D_ / 2 - 0.12, H_, L_ / 2 + 0.08, D_ / 2 + 0.05, H_ + 0.05, "wood", bevel=0.008)
    for x in (-L_ / 2 + 0.05, L_ / 2 - 0.05):
        K.cyl(0.38, 0.06, 18, at=(x - 0.03, 0.15, 0.38), mat="wood", axis="X")
        if K.detail():
            for k in range(8):
                a = k / 8 * math.tau
                K.beam((x, 0.15, 0.38), (x, 0.15 + 0.36 * math.cos(a), 0.38 + 0.36 * math.sin(a)), 0.03, mat="wood")
    K.beam((L_ / 2, -0.35, 0.6), (L_ / 2 + 0.6, -0.35, 0.55), 0.05, mat="wood")
    K.beam((L_ / 2, 0.35, 0.6), (L_ / 2 + 0.6, 0.35, 0.55), 0.05, mat="wood")
    # roof on four posts + noren cloth at the front + lanterns
    for x in (-L_ / 2 + 0.06, L_ / 2 - 0.06):
        for y in (-D_ / 2 + 0.05, D_ / 2 - 0.05):
            bmin(x - 0.03, y - 0.03, H_, x + 0.03, y + 0.03, 2.2, "wood")
    roof = bmin(-L_ / 2 - 0.2, -D_ / 2 - 0.35, 2.2, L_ / 2 + 0.2, D_ / 2 + 0.15, 2.26, "st_awning_red")
    roof.rot_about((0, 0, 2.2), x=-8)
    n = 4
    for i in range(n):
        r = LY.sub(LY.uv("cloth_1"), i / n + 0.004, 0.0, (i + 1) / n - 0.004, 1.0)
        x0 = -L_ / 2 + 0.1 + i * (L_ - 0.2) / n
        front_card("emit_st_signs", x0, x0 + (L_ - 0.2) / n - 0.03, -D_ / 2 - 0.3, 1.75, 2.18, r, two_sided=True)
    for x in (-L_ / 2 + 0.1, L_ / 2 - 0.1):
        prof = [(0.07, 0), (0.15, 0.06), (0.17, 0.2), (0.15, 0.34), (0.07, 0.4)]
        K.lathe(prof, 12, at=(x, -D_ / 2 - 0.3, 1.3), mat="emit_st_lantern_red")
        M.light((x, -D_ / 2 - 0.3, 1.5), "#ff6a3a", 3.5, 1.0)
    # cooking side: pots with lids, menu board, stools for customers
    for i, x in enumerate((-0.55, 0.0, 0.5)):
        K.cyl(0.17, 0.22, 16, at=(x, 0.1, H_ + 0.05), mat="metal_bare")
        K.cyl(0.18, 0.02, 16, at=(x, 0.1, H_ + 0.27), mat="metal_dark")
        M.vent((x, 0.1, H_ + 0.32))
    front_card("emit_st_signs", -0.45, 0.45, D_ / 2 + 0.06, 1.25, 1.75, LY.uv("square_8"), flip_u=True)
    for x in (-0.6, 0.6):
        K.cyl(0.15, 0.05, 12, at=(x, -D_ / 2 - 0.55, 0.45), mat="st_awning_red")
        K.cyl(0.025, 0.45, 6, at=(x, -D_ / 2 - 0.55, 0.0), mat="metal_bare")
    M.light((0, -0.5, 1.8), "#ffb46a", 6.0, 1.6)
    M.col((0.1, 0, 0.6), (L_ + 0.7, D_ + 0.2, 1.2))
    return M.done()


# ============================================================================================== ground details
def steam_grate():
    M = Meta()
    W, D = 1.2, 0.7
    bmin(-W / 2, -D / 2, -0.02, W / 2, D / 2, 0.012, "metal_dark")
    bmin(-W / 2 + 0.04, -D / 2 + 0.04, -0.03, W / 2 - 0.04, D / 2 - 0.04, 0.0125, "black")
    for i in range(16):
        x = -W / 2 + 0.07 + i * (W - 0.14) / 15
        bmin(x - 0.012, -D / 2 + 0.04, -0.01, x + 0.012, D / 2 - 0.04, 0.014, "metal_rusted")
    for y in (-0.12, 0.12):
        bmin(-W / 2 + 0.04, y - 0.01, -0.01, W / 2 - 0.04, y + 0.01, 0.013, "metal_rusted")
    M.vent((0, 0, 0.05))
    return M.done()


def manhole():
    M = Meta()
    R = 0.36
    K.cyl(R + 0.06, 0.012, 32, at=(0, 0, -0.004), mat="metal_dark")
    K.cyl(R, 0.016, 32, at=(0, 0, -0.002), mat="metal_rusted")
    if K.detail():
        for rr in (0.12, 0.22, 0.31):
            K.torus(rr, 0.006, n_major=28, n_minor=4, mat="metal_bare").move(0, 0, 0.014)
        for k in range(12):
            a = k / 12 * math.tau
            K.tube([(0.12 * math.cos(a), 0.12 * math.sin(a), 0.014), (0.31 * math.cos(a), 0.31 * math.sin(a), 0.014)], 0.005, 3, mat="metal_bare")
        for k in range(2):
            K.cyl(0.025, 0.006, 8, at=(0.27 * (1 if k else -1), 0, 0.014), mat="black")
    return M.done()


def bollard_led(colour="emit_st_led_cyan"):
    M = Meta()
    K.cyl(0.11, 0.05, 16, at=(0, 0, 0), mat="metal_dark")
    K.cyl(0.085, 0.95, 16, at=(0, 0, 0.0), mat="metal_bare")
    K.cyl(0.088, 0.06, 16, at=(0, 0, 0.72), mat=colour)
    K.cyl(0.088, 0.03, 16, at=(0, 0, 0.55), mat="metal_painted_yellow")
    K.lathe([(0.088, 0), (0.07, 0.05), (0.0, 0.07)], 16, at=(0, 0, 0.95), mat="metal_dark")
    M.light((0, 0, 0.75), "#40e0ff", 2.0, 0.6)
    M.col((0, 0, 0.5), (0.22, 0.22, 1.0))
    return M.done()


def water_barrier(colour="plastic_orange"):
    M = Meta()
    L = 1.8
    prof = [(-0.3, 0), (0.3, 0), (0.22, 0.25), (0.12, 0.85), (-0.12, 0.85), (-0.22, 0.25)]
    K.extrude(prof, L, plane="YZ", mat=colour, bevel=0.02)
    for x in (-L / 2 + 0.25, L / 2 - 0.25):
        K.cyl(0.05, 0.03, 10, at=(x, 0, 0.85), mat=colour)
    bmin(-L / 2 + 0.1, -0.205, 0.45, L / 2 - 0.1, -0.18, 0.58, "metal_painted_white")
    bmin(-L / 2 + 0.1, 0.18, 0.45, L / 2 - 0.1, 0.205, 0.58, "metal_painted_white")
    M.col((0, 0, 0.43), (L, 0.6, 0.86))
    return M.done()


# ============================================================================================== shelters / kiosks
def tram_shelter():
    M = Meta()
    W, D, H = 4.2, 1.6, 2.75
    for x in (-W / 2 + 0.08, W / 2 - 0.08):
        for y in (D / 2 - 0.08,):
            bmin(x - 0.06, y - 0.06, 0, x + 0.06, y + 0.06, H, "metal_dark", bevel=0.01)
    # cantilever roof with glass inlay and LED edge
    bmin(-W / 2 - 0.1, -D / 2 - 0.25, H, W / 2 + 0.1, D / 2 + 0.05, H + 0.12, "metal_dark", bevel=0.015)
    bmin(-W / 2 + 0.1, -D / 2 - 0.1, H + 0.121, W / 2 - 0.1, D / 2 - 0.1, H + 0.125, "glass_dark")
    bmin(-W / 2 - 0.1, -D / 2 - 0.26, H - 0.02, W / 2 + 0.1, -D / 2 - 0.22, H + 0.01, "emit_st_led_white")
    # back glass wall and a side ad box (double sided lightbox, screen_ad material)
    K.plane(W - 1.6, H - 0.4, mat="glass").rot(x=90).move(-0.7, D / 2 - 0.06, H / 2 + 0.05)
    bmin(-W / 2 + 0.1, D / 2 - 0.09, 0.15, W / 2 - 1.5, D / 2 - 0.03, 0.2, "metal_dark")
    ad = bmin(W / 2 - 1.4, D / 2 - 0.2, 0.15, W / 2 - 0.15, D / 2 + 0.02, H - 0.2, "metal_dark", bevel=0.01)
    bmin(W / 2 - 1.33, -0.0, 0.25, W / 2 - 0.22, D / 2 - 0.205, H - 0.3, "screen_ad_b").move(0, 0, 0)
    side = bmin(-W / 2 + 0.04, -D / 2 + 0.2, 0.3, -W / 2 + 0.1, D / 2 - 0.12, H - 0.3, "screen_ad_a")
    bmin(-W / 2, -D / 2 + 0.14, 0.2, -W / 2 + 0.14, D / 2 - 0.08, H - 0.2, "metal_dark")
    # bench, route map, timetable screen
    bmin(-1.6, D / 2 - 0.5, 0.42, 0.5, D / 2 - 0.12, 0.47, "wood", bevel=0.01)
    for x in (-1.4, 0.3):
        bmin(x - 0.03, D / 2 - 0.4, 0, x + 0.03, D / 2 - 0.2, 0.42, "metal_dark")
    front_card("emit_st_signs", -1.5, -0.9, D / 2 - 0.065, 1.2, 1.8, LY.uv("square_12"), flip_u=False)
    bmin(-0.6, -D / 2 - 0.22, H - 0.5, 0.6, -D / 2 - 0.12, H - 0.02, "black")
    front_card("emit_st_signs", -0.57, 0.57, -D / 2 - 0.225, H - 0.47, H - 0.05, LY.sub(LY.uv("fascia_capsule_1"), 0, 0, 0.4, 1))
    M.light((0, 0, H - 0.2), "#dfeaff", 5.0, 1.2)
    M.col((-W / 2 + 0.1, 0, H / 2), (0.25, D, H))
    M.col((W / 2 - 0.75, D / 2 - 0.1, H / 2), (1.5, 0.3, H))
    M.col((-0.7, D / 2 - 0.05, H / 2), (W - 1.6, 0.12, H))
    return M.done()


def charge_totem():
    M = Meta()
    bmin(-0.26, -0.18, 0, 0.26, 0.18, 1.95, "paint_glossy_dark", bevel=0.03)
    bmin(-0.2, -0.185, 0.95, 0.2, -0.17, 1.6, "screen_ad_c")
    for x in (-0.262, 0.262):
        bmin(x - 0.004, -0.15, 0.2, x + 0.004, 0.15, 1.85, "emit_st_led_cyan")
    bmin(-0.27, -0.19, 1.95, 0.27, 0.19, 2.02, "emit_st_led_cyan")
    for x in (-0.12, 0.12):
        bmin(x - 0.05, -0.22, 0.65, x + 0.05, -0.17, 0.8, "metal_bare")
        if K.detail():
            K.tube([(x, -0.22, 0.65), (x + 0.02, -0.3, 0.45), (x - 0.05, -0.25, 0.3), (x, -0.19, 0.4)], 0.012, 5, mat="rubber")
    M.light((0, -0.3, 1.3), "#40e0ff", 2.5, 0.8)
    M.col((0, 0, 1.0), (0.55, 0.4, 2.0))
    return M.done()


def data_booth():
    M = Meta()
    W, D, H = 1.05, 1.05, 2.35
    for x in (-W / 2 + 0.04, W / 2 - 0.04):
        for y in (-D / 2 + 0.04, D / 2 - 0.04):
            bmin(x - 0.04, y - 0.04, 0, x + 0.04, y + 0.04, H, "metal_dark")
    bmin(-W / 2 - 0.05, -D / 2 - 0.05, H, W / 2 + 0.05, D / 2 + 0.05, H + 0.32, "metal_dark", bevel=0.02)
    for s in (1, -1):
        front_card("emit_st_signs", -0.42, 0.42, s * (D / 2 + 0.052), H + 0.04, H + 0.28, LY.sub(LY.uv("fascia_clinic_0"), 0.1, 0, 0.5, 1),
                   flip_u=s > 0) if s < 0 else card("emit_st_signs", [(0.42, D / 2 + 0.052, H + 0.04), (-0.42, D / 2 + 0.052, H + 0.04),
                                                            (-0.42, D / 2 + 0.052, H + 0.28), (0.42, D / 2 + 0.052, H + 0.28)],
                                                    LY.sub(LY.uv("fascia_clinic_0"), 0.1, 0, 0.5, 1))
    for (x, y, rx) in ((-W / 2 + 0.02, 0, 90), (W / 2 - 0.02, 0, 90)):
        K.plane(D - 0.1, H - 0.2, mat="glass").rot(x=90, z=90).move(x, y, H / 2 + 0.05)
    K.plane(W - 0.1, H - 0.2, mat="glass").rot(x=90).move(0, D / 2 - 0.02, H / 2 + 0.05)
    bmin(-0.3, D / 2 - 0.25, 0.9, 0.3, D / 2 - 0.08, 1.6, "paint_glossy_dark", bevel=0.01)
    bmin(-0.24, D / 2 - 0.255, 1.15, 0.24, D / 2 - 0.24, 1.5, "screen_ad_a")
    bmin(-W / 2, -D / 2, 0, W / 2, D / 2, 0.04, "rubber")
    M.light((0, 0, H - 0.1), "#5fe8ff", 3.0, 1.0)
    M.col((-W / 2 + 0.03, 0, H / 2), (0.08, D, H))
    M.col((W / 2 - 0.03, 0, H / 2), (0.08, D, H))
    M.col((0, D / 2 - 0.03, H / 2), (W, 0.08, H))
    return M.done()


def capsule_toys(seed=7):
    """Bank of 2 x 3 capsule-toy machines on a stand (clear domes full of coloured capsules, coin knobs, lit headers)."""
    M = Meta()
    r = random.Random(seed)
    cols = ["emit_st_led_magenta", "emit_st_led_cyan", "emit_st_led_amber"]
    caps = ["paint_glossy_red", "paint_glossy_white", "car_paint_teal", "car_paint_yellow", "car_paint_magenta"]
    bmin(-0.75, -0.25, 0, 0.75, 0.25, 0.3, "metal_dark")
    for row in range(2):
        z0 = 0.3 + row * 0.62
        for i in range(3):
            x = -0.5 + i * 0.5
            bmin(x - 0.23, -0.22, z0, x + 0.23, 0.22, z0 + 0.22, "paint_glossy_white" if (i + row) % 2 else "paint_glossy_red", bevel=0.01)
            K.cyl(0.05, 0.03, 12, at=(x, -0.22, z0 + 0.11), mat="metal_bare", axis="Y").move(0, -0.03, 0)
            bmin(x - 0.21, -0.2, z0 + 0.22, x + 0.21, 0.2, z0 + 0.56, "glass")
            if K.detail():
                for k in range(10):
                    p = K._new(r.choice(caps), "cap")
                    bmesh.ops.create_icosphere(p.bm, subdivisions=1, radius=0.045)
                    p.move(x + r.uniform(-0.15, 0.15), r.uniform(-0.14, 0.14), z0 + 0.27 + r.uniform(0, 0.16))
            bmin(x - 0.23, -0.22, z0 + 0.56, x + 0.23, 0.22, z0 + 0.6, cols[(i + row) % 3])
    M.light((0, -0.4, 1.0), "#ff4fd8", 2.5, 0.8)
    M.col((0, 0, 0.75), (1.5, 0.5, 1.5))
    return M.done()


def cable_anchor():
    """Wall anchor where overhead cables terminate: plate, two insulators, eye bolts. Pivot: wall plane."""
    M = Meta()
    bmin(-0.18, -0.02, -0.12, 0.18, 0.0, 0.12, "metal_rusted")
    for x in (-0.08, 0.08):
        K.cyl(0.012, 0.18, 6, at=(x, -0.02, 0.0), mat="metal_bare", axis="Y").rot_about((x, -0.02, 0), x=180)
        K.lathe([(0.03, 0), (0.045, 0.02), (0.03, 0.04), (0.045, 0.06), (0.03, 0.08)], 10, at=(x, -0.12, -0.04), mat="plastic_dark")
    return M.done()


ASSETS = {}


def _reg(name, fn, cat="streetprop", pivot="base-centre", notes="", **kw):
    ASSETS[name] = dict(fn=fn, kw=kw, cat=cat, zones=["plaza"], pivot=pivot, notes=notes)


_reg("St_Dumpster_Green", dumpster, notes="Steel dumpster 1.9 x 1.15 x 1.1 m, tapered body, plastic lids, forklift sleeves, castors, overflow bag.", colour="metal_painted_green")
_reg("St_Dumpster_Blue", dumpster, notes="Dumpster, blue-grey paint, one lid propped open.", colour="metal_painted", lid_open=70, seed=9)
_reg("St_TrashBags_A", bag_pile, notes="Pile of 5 garbage bags with a soggy box. Low collider.", n=5, seed=3)
_reg("St_TrashBags_B", bag_pile, notes="Pile of 7 garbage bags (black / blue / grey).", n=7, seed=11, mats=("st_bag_black", "st_bag_blue", "st_bag_black", "st_bag_white", "st_bag_black"))
_reg("St_TrashBags_C", bag_pile, notes="Small pile of 3 black bags.", n=3, seed=21, mats=("st_bag_black",))
_reg("St_AC_Unit_Wall", ac_unit, cat="wallprop", pivot="wall-base", notes="Split AC outdoor unit on rusty L-brackets, fan guard, louvres, pipes, drip hose. Pivot at the wall plane, bracket base.")
_reg("St_FireEscape_2F", fire_escape, cat="wallprop", pivot="wall-base", notes="Fire escape segment: two grating landings 3.4 m apart with railings, stair flight and drop ladder. Pivot = wall plane at the lower deck.")
_reg("St_FoodCart_Yatai", food_cart, notes="Yatai noodle cart: wooden cart on spoked wheels, red roof, noren cloths, red lanterns, three steaming pots (steam anchors), menu board, stools.")
_reg("St_SteamGrate", steam_grate, notes="Road / pavement steam grate 1.2 x 0.7 m (steam anchor).")
_reg("St_Manhole", manhole, notes="Cast manhole cover with rim, raised rings and ribs (sits 1.5 cm proud).")
_reg("St_Bollard_LED", bollard_led, notes="Steel bollard with cyan LED ring and yellow band.")
_reg("St_WaterBarrier_Orange", water_barrier, notes="Water-filled plastic road barrier 1.8 m.", colour="plastic_orange")
_reg("St_WaterBarrier_White", water_barrier, notes="Water-filled plastic road barrier 1.8 m (white).", colour="paint_glossy_white")
_reg("St_TramShelter", tram_shelter, notes="Tram / bus shelter 4.2 m: cantilever roof with LED edge, glass back wall, double-sided ad lightboxes (screen_ad), bench, route map, timetable board. Open front +Z.")
_reg("St_ChargeTotem", charge_totem, notes="EV / phone charging totem with ad screen, cyan LED edges and two holstered cables.")
_reg("St_DataBooth", data_booth, notes="Glass data / phone booth with lit roof sign and terminal screen; open front +Z.")
_reg("St_CapsuleToys", capsule_toys, notes="Bank of 6 capsule-toy machines (clear domes, coloured capsules, lit headers) on a stand.")
_reg("St_CableAnchor", cable_anchor, cat="wallprop", pivot="wall-centre", notes="Wall anchor plate with insulators where overhead cables terminate.")
