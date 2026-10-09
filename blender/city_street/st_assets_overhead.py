"""Overhead street dressing: projecting signs on long wall brackets over the pavement, a tall neon glyph column, and
a single paper lantern used along the cables strung across the streets (the cables themselves are generated in game).
Wall pieces: pivot at the wall plane (y = 0) at the bracket height; they project toward -Y (Unity +Z).
"""
import math
import random

import st_layout as LY
from stgeo import K, Meta, bmin, card, side_card, front_card


def hanging_blade(blade_idx=0, reach=1.9, h=2.6, seed=1):
    """Tall double-sided lightbox hanging from a cantilever bracket (top of the box at z = 0)."""
    M = Meta()
    w = h / 3.0
    bmin(-0.15, -0.03, -0.25, 0.15, 0.0, 0.35, "metal_dark")                                  # wall plate
    K.beam((0, -0.02, 0.25), (0, -reach - 0.2, 0.18), 0.08, 0.12, mat="metal_dark")
    K.beam((0, -0.02, -0.2), (0, -reach * 0.6, 0.18), 0.05, mat="metal_dark")                # strut
    yc = -reach + 0.05
    for y in (yc + w / 2 - 0.12, yc - w / 2 + 0.12):
        K.tube([(0, y, 0.16), (0, y, 0.02)], 0.012, 5, mat="metal_bare")
    bmin(-0.09, yc - w / 2, -h, 0.09, yc + w / 2, 0.02, "metal_dark", bevel=0.01)
    r = LY.uv(f"blade_{blade_idx}")
    side_card("emit_st_signs", 0.092, yc + w / 2 - 0.03, yc - w / 2 + 0.03, -h + 0.03, -0.01, r, facing=1)
    side_card("emit_st_signs", -0.092, yc + w / 2 - 0.03, yc - w / 2 + 0.03, -h + 0.03, -0.01, r, facing=-1)
    if K.detail():
        for z in (-h, 0.02):
            bmin(-0.1, yc - w / 2 - 0.01, z - 0.015, 0.1, yc + w / 2 + 0.01, z + 0.015, "metal_bare")
    M.light((0, yc, -h / 2), "#ff4fd8", 5.0, 1.0)
    return M.done()


def hanging_box(square_idx=1, reach=1.5, seed=2):
    """Square double-sided lightbox hanging on chains under a short bracket (top of the chains at z = 0)."""
    M = Meta()
    s = 0.9
    bmin(-0.12, -0.03, -0.1, 0.12, 0.0, 0.2, "metal_dark")
    K.beam((0, -0.02, 0.1), (0, -reach - 0.1, 0.1), 0.06, mat="metal_dark")
    yc = -reach + 0.1
    for y in (yc - s / 2 + 0.08, yc + s / 2 - 0.08):
        K.tube([(0, y, 0.08), (0, y, -0.32)], 0.008, 4, mat="metal_bare")
    bmin(-0.1, yc - s / 2, -0.32 - s, 0.1, yc + s / 2, -0.32, "metal_dark", bevel=0.01)
    r = LY.uv(f"square_{square_idx}")
    side_card("emit_st_signs", 0.102, yc + s / 2 - 0.03, yc - s / 2 + 0.03, -0.32 - s + 0.03, -0.35, r, facing=1)
    side_card("emit_st_signs", -0.102, yc + s / 2 - 0.03, yc - s / 2 + 0.03, -0.32 - s + 0.03, -0.35, r, facing=-1)
    M.light((0, yc, -0.32 - s / 2), "#00e5ff", 4.0, 0.8)
    return M.done()


def neon_column(seed=3, glyphs=4, tube="emit_neon_cyan", tube2="emit_neon_magenta"):
    """Tall vertical neon sign: dark backer on a stand-off frame with glyphs bent from neon tube (invented glyph
    grammar of the kit), pivot at the wall plane at the bottom of the backer."""
    M = Meta()
    r = random.Random(seed)
    W, gh = 0.9, 1.0
    H = glyphs * gh + 0.3
    yb = -0.35
    bmin(-W / 2, yb - 0.06, 0, W / 2, yb, H, "metal_dark", bevel=0.015)
    for z in (0.3, H - 0.3):
        bmin(-0.05, yb, z - 0.05, 0.05, 0, z + 0.05, "metal_dark")
    K.tube([(-W / 2 + 0.05, yb - 0.08, 0.05), (W / 2 - 0.05, yb - 0.08, 0.05), (W / 2 - 0.05, yb - 0.08, H - 0.05),
            (-W / 2 + 0.05, yb - 0.08, H - 0.05), (-W / 2 + 0.05, yb - 0.08, 0.05)], 0.014, 6, mat=tube2)
    for g in range(glyphs):
        z0 = 0.15 + g * gh
        top = r.uniform(0.78, 0.9)
        S = [(r.uniform(0.1, 0.2), top, r.uniform(0.8, 0.9), top)]
        for x in sorted(r.sample([0.25, 0.4, 0.55, 0.7], 2)):
            S.append((x, r.uniform(0.08, 0.3), x, r.uniform(0.55, top)))
        mid = r.uniform(0.4, 0.6)
        S.append((r.uniform(0.1, 0.25), mid, r.uniform(0.7, 0.9), mid))
        if r.random() < 0.6:
            S.append((r.uniform(0.15, 0.3), r.uniform(0.1, 0.3), r.uniform(0.6, 0.85), r.uniform(0.1, 0.3)))
        for (ax, ay, bx, by) in S:
            K.tube([(-W / 2 + 0.1 + ax * (W - 0.2), yb - 0.1, z0 + ay * gh * 0.9), (-W / 2 + 0.1 + bx * (W - 0.2), yb - 0.1, z0 + by * gh * 0.9)],
                   0.016, 6, mat=tube)
    M.light((0, -0.8, H / 2), "#00e5ff", 6.0, 1.4)
    return M.done()


def lantern_single(mat="emit_st_lantern_red"):
    M = Meta()
    r, h = 0.16, 0.4
    prof = [(r * 0.45, -h), (r * 0.85, -h * 0.88), (r, -h * 0.5), (r * 0.85, -h * 0.12), (r * 0.45, 0)]
    K.lathe(prof, 12, at=(0, 0, -0.06), mat=mat)
    K.cyl(r * 0.5, 0.05, 10, at=(0, 0, -0.08), mat="black")
    K.cyl(r * 0.5, 0.04, 10, at=(0, 0, -h - 0.08), mat="black")
    K.cyl(0.005, 0.06, 4, at=(0, 0, -0.06), mat="black")
    if K.detail():
        K.tube([(0, 0, -h - 0.1), (0, 0, -h - 0.32)], 0.012, 4, mat=mat)
        for i in range(4):
            zz = -0.06 - h * (0.2 + 0.2 * i)
            K.torus(r * 0.98 if 0 < i < 3 else r * 0.88, 0.004, n_major=12, n_minor=3, mat="black").move(0, 0, zz)
    return M.done()


ASSETS = {}


def _reg(name, fn, cat="overhead", pivot="wall-centre", notes="", **kw):
    ASSETS[name] = dict(fn=fn, kw=kw, cat=cat, zones=["plaza"], pivot=pivot, notes=notes)


for i, b in enumerate((0, 3, 5, 9, 12, 14)):
    _reg(f"St_HangingSign_{chr(65 + i)}", hanging_blade, notes="Double-sided blade lightbox (invented glyphs) hanging from a 1.9 m cantilever bracket; pivot at the wall plane at the bracket top. Mount 6-7 m up.",
         blade_idx=b, reach=1.9 if i % 2 == 0 else 2.3, h=2.6 if i < 3 else 3.2)
for i, sq in enumerate((1, 5, 9, 13)):
    _reg(f"St_HangingBox_{chr(65 + i)}", hanging_box, notes="Square double-sided lightbox on chains under a short bracket; pivot at the wall plane, bracket height.", square_idx=sq)
_reg("St_NeonColumn_A", neon_column, pivot="wall-base", notes="4-glyph vertical neon tube sign on a dark backer, 4.3 m tall, stands off the facade 0.35 m.", seed=3)
_reg("St_NeonColumn_B", neon_column, pivot="wall-base", notes="3-glyph neon column (magenta / yellow).", seed=8, glyphs=3, tube="emit_neon_magenta", tube2="emit_neon_yellow")
_reg("St_Lantern_Paper", lantern_single, notes="Single red paper lantern with tassel; pivot at the hanging point (top).")
_reg("St_Lantern_Paper_Warm", lantern_single, notes="Single warm paper lantern; pivot at the hanging point (top).", mat="emit_st_lantern_warm")
