"""Procedural PBR material definitions (Blender shader nodes) for the Aether-9 environment set.

Each baked material: define(nb, params) -> dict of sockets
  color  : linear RGB colour socket              (-> BaseColor, sRGB PNG)
  rough  : roughness 0..1                        (-> MaskMap.A as smoothness = 1 - rough)
  metal  : metallic 0..1                         (-> MaskMap.R)
  height : 0..1 height, scaled by `depth` metres (-> Normal (OpenGL), AO, MaskMap.B)
  ao     : optional extra AO multiplier          (-> multiplied into MaskMap.G / Occlusion)
  alpha  : optional opacity (cutout)             (-> BaseColor.A)
  emit   : optional emission colour              (-> Emission)
`tile` is the real-world size of one texture repeat in metres (meshes carry UVs in metres).

REGISTRY lists every material name used by the meshes (baked, tint variants and parameter-only ones) with
the Unity-side settings; build_materials.py writes it into the manifest.
"""


from matdefs_base import lin, g, crack_lines, puddles  # noqa: E402,F401
import matdefs_hd as HD  # noqa: E402


# ============================================================================================== concrete
def concrete(nb, p):
    base = p.get("base", g(0.39))
    big = nb.noise(2, detail=3, seed=1)
    mid = nb.noise(14, detail=5, rough=0.55, seed=2)
    fine = nb.noise(180, detail=3, rough=0.6, seed=3)
    pores = nb.smooth(nb.voronoi(120, seed=4), 0.16, 0.04) * nb.smooth(nb.noise(5, seed=5), 0.35, 0.6)
    cracks = crack_lines(nb, 3, 6, 0.007)
    h = 0.6 + (big - 0.5) * 0.2 + (mid - 0.5) * 0.45 + (fine - 0.5) * 0.4 - pores * 0.4 - cracks * 0.55
    blot = nb.noise(4, detail=6, rough=0.6, seed=7)
    streak = nb.noise(24, fv=1.5, detail=3, seed=8)
    speck = nb.voronoi(260, seed=9, out="Color")
    shade = 1.0 + (blot - 0.5) * 0.75 + (big - 0.5) * 0.25 + (streak - 0.5) * 0.12 + (speck - 0.5) * 0.18 - pores * 0.45 - cracks * 0.5 + (fine - 0.5) * 0.15
    col = nb.mulc(base, shade)
    stain = nb.smooth(nb.noise(3, detail=6, rough=0.65, seed=10), 0.56, 0.76)
    col = nb.mixc(col, nb.mulc(col, 0.6), stain * 0.85)
    rough = 0.84 + (fine - 0.5) * 0.16 + pores * 0.1 - stain * 0.1
    wet = p.get("wet", 0.0)
    if wet:
        pud = puddles(nb, h, 2.0, 11, level=0.5)
        damp = nb.smooth(nb.noise(3, detail=3, seed=12), 0.3, 0.6)
        col = nb.mixc(nb.mulc(col, 0.6 - damp * 0.1), nb.mulc(col, 0.34), pud)
        rough = nb.lerp(rough * (0.55 - damp * 0.15), 0.03, pud)
        h = nb.lerp(h, 0.52, pud)
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp()}


# ============================================================================================== asphalt
def asphalt(nb, p):
    stones = nb.voronoi(420, seed=21)
    stone_c = nb.voronoi(420, seed=21, out="Color")
    dome = nb.smooth(stones, 0.55, 0.0)
    exposed = nb.smooth(nb.noise(6, detail=4, seed=22), 0.45, 0.65)
    binder = nb.noise(90, detail=3, seed=23)
    cracks = crack_lines(nb, 2.5, 24, 0.005, keep=0.5)
    patch_r = nb.cell_rand(3, 3, seed=25)
    pu = nb.fract(nb.u * 3)
    pv = nb.fract(nb.v * 3)
    edge_n = (nb.noise(40, seed=26) - 0.5) * 0.06
    in_patch = nb.lt(patch_r, 0.22) * nb.smooth(nb.minf(nb.minf(pu, 1 - pu), nb.minf(pv, 1 - pv)) + edge_n, 0.05, 0.07)
    h = 0.55 + dome * exposed * 0.35 + (binder - 0.5) * 0.25 - cracks * 0.6 - in_patch * 0.05
    sc = 0.9 + (stone_c - 0.5) * 0.9
    col_bind = nb.mulc(g(0.15), 0.85 + (binder - 0.5) * 0.6)
    col_stone = nb.mulc(g(0.32), sc)
    col = nb.mixc(col_bind, col_stone, dome * exposed * 0.85)
    col = nb.mixc(col, g(0.10), in_patch * 0.8)
    oil = nb.smooth(nb.noise(5, detail=5, seed=27), 0.66, 0.74)
    col = nb.mixc(col, g(0.06), oil * 0.6)
    col = nb.mixc(col, g(0.07), cracks)
    rough = 0.86 - dome * exposed * 0.08 - oil * 0.2 + cracks * 0.1
    pud = puddles(nb, h, 1.6, 28, level=0.53)
    col = nb.mixc(col, nb.mulc(col, 0.45), pud)
    rough = nb.lerp(rough * 0.7, 0.03, pud)
    h = nb.lerp(h, 0.55, pud)
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp()}


# ============================================================================================== paving
def paving(nb, p):
    n = 4  # slabs per tile (tile 3 m -> 0.75 m slabs)
    gd = nb.minf(nb.grid_dist(nb.u, n), nb.grid_dist(nb.v, n))  # tile units
    grout = nb.smooth(gd, 0.0022, 0.0010)  # ~3-6 mm joints
    bevel = nb.smooth(gd, 0.006, 0.0018)
    rnd = nb.cell_rand(n, n, seed=31)
    rnd2 = nb.cell_rand(n, n, seed=32)
    tilt = (nb.fract(nb.u * n) - 0.5) * (rnd - 0.5) * 0.12 + (nb.fract(nb.v * n) - 0.5) * (rnd2 - 0.5) * 0.12
    surf = nb.noise(60, detail=4, rough=0.6, seed=33)
    grain = nb.noise(300, detail=2, seed=34)
    chip = nb.smooth(nb.noise(40, detail=3, seed=35), 0.68, 0.72) * nb.smooth(gd, 0.03, 0.0)
    cracks = crack_lines(nb, 3, 36, 0.004, keep=0.62)
    h = 0.7 + tilt + (surf - 0.5) * 0.12 + (grain - 0.5) * 0.06 - bevel * 0.15 - grout * 0.55 - chip * 0.25 - cracks * 0.3
    tint = 0.85 + rnd * 0.3
    col = nb.mulc(lin("#6e7276"), tint + (surf - 0.5) * 0.25 + (grain - 0.5) * 0.15)
    dirt = nb.smooth(nb.noise(3, detail=6, rough=0.62, seed=37), 0.5, 0.8)
    col = nb.mixc(col, nb.mulc(col, 0.55), dirt * 0.7)
    col = nb.mixc(col, g(0.12), nb.maxf(grout, chip * 0.6))
    col = nb.mixc(col, g(0.15), cracks * 0.8)
    rough = 0.62 + (grain - 0.5) * 0.1 + grout * 0.3 + dirt * 0.1
    pud = puddles(nb, h, 2.0, 38, level=0.52, bias=0.6)
    col = nb.mixc(col, nb.mulc(col, 0.5), pud)
    rough = nb.lerp(rough * 0.75, 0.04, pud)
    h = nb.lerp(h, 0.66, pud * 0.85)
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp()}


# ============================================================================================== metals
def metal_painted(nb, p):
    paint = p.get("tint", lin("#4d5b63"))
    peel = nb.noise(380, detail=2, seed=41)
    blot = nb.noise(5, detail=5, rough=0.6, seed=42)
    chipn = nb.noise(9, detail=6, rough=0.65, seed=43)
    chips = nb.smooth(chipn + (nb.noise(80, detail=3, seed=44) - 0.5) * 0.25, 0.68, 0.70)
    chip_edge = nb.smooth(chipn + (nb.noise(80, detail=3, seed=44) - 0.5) * 0.25, 0.64, 0.68) - chips
    scr = nb.smooth(nb.absf(nb.noise(3, fv=90, detail=2, seed=45) - 0.5), 0.004, 0.0) * nb.smooth(nb.noise(6, seed=46), 0.55, 0.65)
    rust_spot = nb.smooth(nb.noise(12, detail=5, seed=47), 0.70, 0.76)
    streak = nb.smooth(nb.noise(40, fv=2.5, detail=4, seed=48), 0.6, 0.8) * p.get("streaks", 0.5)
    h = 0.6 + (peel - 0.5) * 0.08 - chips * 0.35 - scr * 0.15 + rust_spot * 0.12
    col = nb.mulc(paint, 0.92 + (blot - 0.5) * 0.25 + (peel - 0.5) * 0.06)
    grime = nb.smooth(nb.noise(3, detail=6, rough=0.6, seed=49), 0.5, 0.85)
    col = nb.mixc(col, nb.mulc(col, 0.55), grime * 0.6)
    col = nb.mixc(col, lin("#4a3a2c"), streak * 0.35)
    col = nb.mixc(col, lin("#b9b9b6"), nb.maxf(scr * 0.7, chip_edge * 0.25))
    bare = lin("#8e8e8c")
    col = nb.mixc(col, bare, chips)
    col = nb.mixc(col, lin("#5b2f17"), rust_spot)
    metal = nb.maxf(chips, scr * 0.8) * (1.0 - rust_spot)
    rough = 0.48 + (blot - 0.5) * 0.12 + grime * 0.18 - chips * 0.12 + rust_spot * 0.35
    return {"color": col, "rough": rough.clamp(), "metal": metal.clamp(), "height": h.clamp()}


def metal_bare(nb, p):
    brush = nb.noise(1.5, fv=500, detail=3, rough=0.7, seed=51)
    brush2 = nb.noise(4, fv=1200, detail=2, seed=52)
    smudge = nb.noise(4, detail=5, rough=0.6, seed=53)
    scr = nb.smooth(nb.absf(nb.noise(5, fv=40, detail=3, seed=54) - 0.5), 0.003, 0.0) * nb.smooth(nb.noise(5, seed=55), 0.5, 0.6)
    pits = nb.smooth(nb.voronoi(70, seed=56), 0.05, 0.0) * nb.smooth(nb.noise(4, seed=57), 0.6, 0.7)
    h = 0.5 + (brush - 0.5) * 0.3 + (brush2 - 0.5) * 0.2 - scr * 0.3 - pits * 0.3
    col = nb.mulc(lin("#a4a6a8"), 0.9 + (brush - 0.5) * 0.25 + (brush2 - 0.5) * 0.1 - (smudge - 0.5) * 0.2 - pits * 0.4)
    stain = nb.smooth(nb.noise(3, detail=5, seed=58), 0.6, 0.8)
    col = nb.mixc(col, lin("#6b6458"), stain * 0.45)
    rough = 0.44 + (brush - 0.5) * 0.18 + (brush2 - 0.5) * 0.12 + (smudge - 0.5) * 0.25 + stain * 0.2 + scr * 0.1
    return {"color": col, "rough": rough.clamp(), "metal": 1.0 - stain * 0.3, "height": h.clamp()}


def metal_rusted(nb, p):
    m1 = nb.noise(6, detail=7, rough=0.62, seed=61)
    m2 = nb.noise(30, detail=4, seed=62)
    m3 = nb.noise(2.5, detail=4, seed=67)
    flake = nb.noise(4, detail=6, rough=0.65, seed=63)
    paint_left = nb.smooth(flake + (nb.noise(60, detail=3, seed=64) - 0.5) * 0.2, 0.55, 0.57)
    pits = nb.smooth(nb.voronoi(90, seed=65), 0.18, 0.03) * (1 - paint_left)
    scale = nb.voronoi(160, seed=66, out="Color")
    streak = nb.smooth(nb.noise(30, fv=2.0, detail=4, seed=68), 0.55, 0.8)
    h = 0.45 + (m1 - 0.5) * 0.35 + (m2 - 0.5) * 0.3 - pits * 0.3 + paint_left * 0.25 + (scale - 0.5) * 0.12
    rust = nb.ramp(m1 * 0.55 + m2 * 0.3 + (scale - 0.5) * 0.25 + (m3 - 0.5) * 0.3, [
        (0.2, lin("#1c120c")), (0.38, lin("#3a2416")), (0.5, lin("#553420")), (0.62, lin("#74431f")), (0.74, lin("#8a5226")), (0.86, lin("#4a3020"))])
    paint = nb.mulc(p.get("tint", lin("#3e474c")), 0.75 + (m2 - 0.5) * 0.3)
    col = nb.mixc(rust, paint, paint_left)
    col = nb.mixc(col, lin("#2a1a10"), streak * 0.45 * (1 - paint_left))
    col = nb.mixc(col, lin("#140c08"), pits * 0.7)
    rough = 0.84 + (m2 - 0.5) * 0.12 - paint_left * 0.32
    return {"color": col, "rough": rough.clamp(), "metal": paint_left * 0.15, "height": h.clamp()}


def metal_plate(nb, p):
    # Heavy dark steel plating 1.0 x 0.5 m (2 x 4 per 2 m tile), alternate rows offset half a plate.
    rows = 4
    row = nb.floor(nb.v * rows)
    off = nb.mod(row, 2.0) * 0.5
    uu = nb.u * 2 + off
    gu = nb.fract(uu)
    gv = nb.fract(nb.v * rows)
    du = nb.minf(gu, 1 - gu) / 2.0
    dv = nb.minf(gv, 1 - gv) / rows
    gd = nb.minf(du, dv)
    seam = nb.smooth(gd, 0.0025, 0.0012)
    bev = nb.smooth(gd, 0.006, 0.0025)
    # bolts near plate corners
    bx = nb.minf(gu, 1 - gu) * 1.0  # metres (plate 1 m wide)
    by = nb.minf(gv, 1 - gv) * 0.5
    bolt_d = ((bx - 0.03) ** 2 + (by - 0.03) ** 2) ** 0.5
    bolt = nb.smooth(bolt_d, 0.009, 0.006)
    rnd = nb.cell_rand(2, rows, seed=71, ou=off * 1.0)
    swirl = nb.noise(2, fv=200, detail=3, seed=72)
    wear = nb.noise(6, detail=6, rough=0.6, seed=73)
    h = 0.6 - seam * 0.6 - bev * 0.12 + bolt * 0.3 + (swirl - 0.5) * 0.05 + (wear - 0.5) * 0.05
    col = nb.mulc(p.get("tint", lin("#4c525a")), 0.85 + rnd * 0.25 + (wear - 0.5) * 0.3)
    col = nb.mixc(col, lin("#6e7276"), nb.smooth(wear, 0.68, 0.8) * 0.5)
    grime = nb.smooth(nb.noise(3, detail=6, seed=74), 0.5, 0.8)
    col = nb.mixc(col, g(0.05), nb.maxf(seam, grime * 0.4))
    rough = 0.5 + (wear - 0.5) * 0.22 + seam * 0.4 + grime * 0.15 - bolt * 0.1
    return {"color": col, "rough": rough.clamp(), "metal": 0.8 - seam * 0.6, "height": h.clamp()}


# ============================================================================================== tiles / panels
def metro_tile(nb, p):
    n = 8  # 0.15 m tiles on a 1.2 m repeat
    gd = nb.minf(nb.grid_dist(nb.u, n), nb.grid_dist(nb.v, n))  # tile units (1 = 1.2 m)
    grout = nb.smooth(gd, 0.0018, 0.0008)
    pillow = nb.smooth(gd, 0.006, 0.0015)
    rnd = nb.cell_rand(n, n, seed=81)
    rnd2 = nb.cell_rand(n, n, seed=82)
    crack = crack_lines(nb, 6, 83, 0.004, keep=0.66) * nb.lt(rnd2, 0.25)
    chip = nb.smooth(nb.noise(30, detail=3, seed=84), 0.72, 0.75) * nb.smooth(gd, 0.012, 0.0) * nb.lt(rnd2, 0.5)
    glaze = nb.noise(50, detail=3, seed=85)
    h = 0.75 - pillow * 0.18 - grout * 0.6 - crack * 0.25 - chip * 0.5 + (glaze - 0.5) * 0.04
    tile = nb.mulc(lin("#d6d8d4"), 0.92 + rnd * 0.1 + (glaze - 0.5) * 0.04)
    grime = nb.smooth(nb.noise(3, detail=7, rough=0.65, seed=86), 0.4, 0.85)
    drip = nb.smooth(nb.noise(30, fv=2.0, detail=4, seed=87), 0.55, 0.85)
    dirt = nb.maxf(grime * 0.75, drip * 0.5)
    col = nb.mixc(tile, nb.mulc(lin("#8a8270"), 0.7), dirt * 0.55)
    col = nb.mixc(col, lin("#3e3c38"), grout)
    col = nb.mixc(col, lin("#55534e"), chip)
    col = nb.mixc(col, lin("#2a2926"), crack * 0.8)
    rough = 0.14 + dirt * 0.45 + grout * 0.7 + chip * 0.6 + (glaze - 0.5) * 0.06
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp()}


def lab_panel(nb, p):
    # 2.4 m repeat: two 1.2 x 2.4 m panels side by side; 8 mm shadow-gap seams; screws at corners.
    gu = nb.fract(nb.u * 2)
    gv = nb.v
    du = nb.minf(gu, 1 - gu) * 1.2  # metres
    dv = nb.minf(nb.fract(gv), 1 - nb.fract(gv)) * 2.4
    gd = nb.minf(du, dv)
    seam = nb.smooth(gd, 0.0045, 0.003)
    bev = nb.smooth(gd, 0.009, 0.004)
    sd = ((du - 0.035) ** 2 + (dv - 0.035) ** 2) ** 0.5
    screw = nb.smooth(sd, 0.0045, 0.0035)
    rnd = nb.cell_rand(2, 1, seed=91)
    orange = nb.noise(200, detail=2, seed=92)
    smudge = nb.noise(4, detail=5, rough=0.6, seed=93)
    h = 0.7 - seam * 0.7 - bev * 0.08 + screw * 0.1 + (orange - 0.5) * 0.03
    col = nb.mulc(p.get("tint", lin("#c4c8c9")), 0.96 + rnd * 0.06 + (smudge - 0.5) * 0.1)
    scuff = nb.smooth(nb.noise(10, fv=3, detail=5, seed=94), 0.66, 0.78)
    col = nb.mixc(col, nb.mulc(col, 0.7), scuff * 0.5)
    col = nb.mixc(col, g(0.08), seam)
    col = nb.mixc(col, lin("#8c8f91"), screw)
    rough = 0.38 + (smudge - 0.5) * 0.12 + scuff * 0.15 + seam * 0.4 - screw * 0.1
    return {"color": col, "rough": rough.clamp(), "metal": screw * 0.9, "height": h.clamp()}


def lab_floor(nb, p):
    n = 4  # 0.5 m vinyl tiles on a 2 m repeat
    gd = nb.minf(nb.grid_dist(nb.u, n), nb.grid_dist(nb.v, n))
    seam = nb.smooth(gd, 0.0008, 0.0003)
    cu = nb.floor(nb.u * n)
    cv = nb.floor(nb.v * n)
    checker = nb.mod(cu + cv, 2.0)
    rnd = nb.cell_rand(n, n, seed=101)
    fleck = nb.voronoi(500, seed=102, out="Color")
    scuff = nb.smooth(nb.absf(nb.noise(6, fv=25, detail=4, seed=103) - 0.5), 0.01, 0.0) * nb.smooth(nb.noise(8, seed=104), 0.55, 0.62)
    wear = nb.smooth(nb.noise(2, detail=5, seed=105), 0.45, 0.8)
    h = 0.6 - seam * 0.5 + (nb.noise(120, detail=2, seed=106) - 0.5) * 0.04
    base = nb.mixc(lin("#7d8387"), lin("#747a7e"), checker)
    col = nb.mulc(base, 0.95 + rnd * 0.08 + (fleck - 0.5) * 0.12)
    col = nb.mixc(col, nb.mulc(col, 0.6), wear * 0.5)
    col = nb.mixc(col, g(0.08), nb.maxf(seam, scuff * 0.7))
    rough = 0.32 + wear * 0.25 + scuff * 0.2 + seam * 0.3
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp()}


# ============================================================================================== soft / misc
def rubber(nb, p):
    grain = nb.noise(300, detail=3, seed=111)
    blot = nb.noise(5, detail=5, seed=112)
    dust = nb.smooth(nb.noise(4, detail=6, seed=113), 0.55, 0.8)
    h = 0.5 + (grain - 0.5) * 0.4 + (blot - 0.5) * 0.15
    col = nb.mulc(g(0.075), 0.9 + (blot - 0.5) * 0.3 + (grain - 0.5) * 0.15)
    col = nb.mixc(col, lin("#4a4640"), dust * 0.35)
    rough = 0.82 + (grain - 0.5) * 0.08 + dust * 0.1
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp()}


def tarp(nb, p):
    N = 160  # threads per metre (tile 1 m)
    a = nb.sin(nb.u * (3.14159265 * N))
    b = nb.sin(nb.v * (3.14159265 * N))
    warp = nb.absf(a)
    weft = nb.absf(b)
    chk = nb.mod(nb.floor(nb.u * N) + nb.floor(nb.v * N), 2.0)
    weave = nb.lerp(warp * 0.6 + weft * 0.4, weft * 0.6 + warp * 0.4, chk)
    wrink = nb.noise(4, detail=5, rough=0.55, seed=121)
    crease = nb.smooth(nb.absf(nb.noise(3, detail=4, seed=122) - 0.5), 0.02, 0.0)
    h = 0.5 + (weave - 0.5) * 0.45 + (wrink - 0.5) * 0.4 - crease * 0.06
    stain = nb.smooth(nb.noise(3, detail=6, rough=0.62, seed=123), 0.55, 0.8)
    fade = nb.noise(2, detail=4, seed=124)
    col = nb.mulc(p.get("tint", lin("#4a5236")), 0.85 + (weave - 0.5) * 0.35 + (fade - 0.5) * 0.35 - crease * 0.06)
    col = nb.mixc(col, nb.mulc(col, 0.5), stain * 0.6)
    rough = 0.82 + (weave - 0.5) * 0.06 - stain * 0.12
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp()}


def corrugated(nb, p):
    pitch = 13  # ~77 mm corrugation pitch on a 1 m repeat; ridges run along V
    prof = nb.sin(nb.u * (6.2831853 * pitch)) * 0.5 + 0.5
    spangle = nb.voronoi(70, seed=131, out="Color")
    streak = nb.smooth(nb.noise(30, fv=2.0, detail=5, rough=0.6, seed=132), 0.52, 0.75)
    rustb = nb.smooth(nb.noise(5, detail=6, rough=0.6, seed=133), 0.58, 0.7)
    rust = nb.maxf(streak * 0.8, rustb)
    oxide = nb.smooth(nb.noise(6, detail=5, seed=134), 0.55, 0.75)
    h = prof * 0.85 + (nb.noise(80, detail=3, seed=135) - 0.5) * 0.08 * rust + 0.05
    zinc = nb.mulc(lin("#8d9398"), 0.85 + (spangle - 0.5) * 0.25)
    zinc = nb.mixc(zinc, lin("#b4b7b3"), oxide * 0.5)
    rcol = nb.ramp(nb.noise(25, detail=4, seed=136), [(0.3, lin("#3a1c0c")), (0.55, lin("#7a3a16")), (0.75, lin("#9b5a2a"))])
    col = nb.mixc(zinc, rcol, rust)
    rough = 0.42 + oxide * 0.25 + rust * 0.45 + (spangle - 0.5) * 0.08
    return {"color": col, "rough": rough.clamp(), "metal": (0.9 - oxide * 0.3) * (1 - rust), "height": h.clamp()}


def grating(nb, p):
    # Bearing bars every 30 mm (run along V), cross bars every 100 mm; 1 m repeat.
    bu = nb.fract(nb.u * 33)  # ~30 mm
    bv = nb.fract(nb.v * 10)  # 100 mm
    bear = nb.smooth(nb.minf(bu, 1 - bu), 0.085, 0.06)
    cross = nb.smooth(nb.minf(bv, 1 - bv), 0.028, 0.02)
    solid = nb.maxf(bear, cross)
    wear = nb.noise(5, detail=5, seed=141)
    rust = nb.smooth(nb.noise(8, detail=6, seed=142), 0.64, 0.74)
    h = solid * (0.85 + bear * 0.1) + (wear - 0.5) * 0.03
    steel = nb.mulc(p.get("tint", lin("#4e5357")), 0.85 + (wear - 0.5) * 0.4)
    steel = nb.mixc(steel, lin("#8a8d90"), nb.smooth(wear, 0.62, 0.75) * 0.6)
    steel = nb.mixc(steel, lin("#5e2e14"), rust * 0.8)
    col = nb.mixc(g(0.02), steel, solid)
    rough = nb.lerp(1.0, 0.5 + rust * 0.35 + (wear - 0.5) * 0.15, solid)
    return {"color": col, "rough": rough.clamp(), "metal": solid * (0.8 - rust * 0.7), "height": h.clamp(),
            "alpha": nb.smooth(solid, 0.3, 0.5)}


def car_paint(nb, p):
    paint = p.get("tint", lin("#5a6068"))
    orange = nb.noise(400, detail=2, seed=151)
    dust = nb.smooth(nb.noise(3, detail=6, rough=0.6, seed=152), 0.5, 0.8)
    streak = nb.smooth(nb.noise(40, fv=1.6, detail=4, seed=153), 0.55, 0.78)
    scr = nb.smooth(nb.absf(nb.noise(4, fv=60, detail=3, seed=154) - 0.5), 0.003, 0.0) * nb.smooth(nb.noise(5, seed=155), 0.6, 0.66)
    chips = nb.smooth(nb.noise(14, detail=6, seed=156) + (nb.noise(90, seed=157) - 0.5) * 0.2, 0.74, 0.76)
    h = 0.6 + (orange - 0.5) * 0.05 - chips * 0.3 - scr * 0.1
    col = nb.mulc(paint, 0.95 + (orange - 0.5) * 0.04)
    grime = lin("#6a6458")
    col = nb.mixc(col, grime, nb.maxf(dust * 0.55, streak * 0.4))
    col = nb.mixc(col, lin("#b0b0ae"), scr * 0.6)
    col = nb.mixc(col, lin("#7a7a78"), chips)
    rough = 0.22 + dust * 0.45 + streak * 0.25 + chips * 0.2 + scr * 0.2
    metal = (0.35 - dust * 0.3) * (1 - chips) + chips * 0.9
    return {"color": col, "rough": rough.clamp(), "metal": metal.clamp(), "height": h.clamp()}


def wood(nb, p):
    boards = 8  # 125 mm boards across V, grain along U (1 m repeat)
    row = nb.floor(nb.v * boards)
    gv = nb.fract(nb.v * boards)
    seam = nb.smooth(nb.minf(gv, 1 - gv) / boards, 0.0025, 0.001)
    rnd = nb.cell_rand(1, boards, seed=161)
    off = rnd * 7.0
    grain = nb.noise(2, fv=70, detail=5, rough=0.6, seed=162)
    rings = nb.sin((nb.v * boards + (grain - 0.5) * 2.0 + off) * 40.0) * 0.5 + 0.5
    knots = nb.smooth(nb.voronoi(6, seed=163), 0.04, 0.0) * nb.lt(nb.noise(5, seed=164), 0.45)
    weather = nb.noise(4, detail=6, rough=0.6, seed=165)
    h = 0.6 + (grain - 0.5) * 0.3 + (rings - 0.5) * 0.08 - seam * 0.6 - knots * 0.1
    base = nb.mixc(lin("#5d4630"), lin("#7b7062"), nb.smooth(weather, 0.4, 0.7))
    col = nb.mulc(base, 0.8 + rnd * 0.3 + (grain - 0.5) * 0.35 + (rings - 0.5) * 0.12 - knots * 0.4)
    col = nb.mixc(col, g(0.04), seam)
    rough = 0.78 + (grain - 0.5) * 0.1 + seam * 0.2
    _ = row
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp()}


def plaster(nb, p):
    st = nb.noise(60, detail=5, rough=0.62, seed=171)
    big = nb.noise(3, detail=4, seed=172)
    cracks = crack_lines(nb, 2.5, 173, 0.006, keep=0.58)
    spall = nb.smooth(nb.noise(4, detail=6, rough=0.62, seed=174), 0.72, 0.74)
    h = 0.6 + (st - 0.5) * 0.4 + (big - 0.5) * 0.1 - cracks * 0.4 - spall * 0.35
    col = nb.mulc(p.get("tint", lin("#8f8a80")), 0.9 + (st - 0.5) * 0.25 + (big - 0.5) * 0.3)
    drip = nb.smooth(nb.noise(40, fv=1.2, detail=4, seed=175), 0.6, 0.85)
    blot = nb.smooth(nb.noise(3, detail=6, rough=0.62, seed=176), 0.5, 0.8)
    col = nb.mixc(col, nb.mulc(col, 0.6), drip * 0.3 + blot * 0.35)
    col = nb.mixc(col, lin("#5a5650"), spall)
    col = nb.mixc(col, g(0.1), cracks * 0.7)
    rough = 0.9 - drip * 0.05
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp()}


def brick(nb, p):
    # 1.8 m repeat: 8 bricks (225 mm incl. 10 mm joint) x 24 courses (75 mm), running bond.
    rows, cols = 24, 8
    row = nb.floor(nb.v * rows)
    off = nb.mod(row, 2.0) * 0.5
    bu = nb.fract(nb.u * cols + off)
    bv = nb.fract(nb.v * rows)
    du = nb.minf(bu, 1 - bu) * (1.8 / cols)
    dv = nb.minf(bv, 1 - bv) * (1.8 / rows)
    gd = nb.minf(du, dv)
    mortar = nb.smooth(gd, 0.0055, 0.004)
    rnd = nb.cell_rand(cols, rows, seed=181, ou=off)
    rnd2 = nb.cell_rand(cols, rows, seed=182, ou=off)
    surf = nb.noise(120, detail=4, seed=183)
    chip = nb.smooth(nb.noise(30, detail=4, seed=184), 0.7, 0.74) * nb.smooth(gd, 0.015, 0.0)
    h = 0.75 - mortar * 0.6 + (surf - 0.5) * 0.15 - chip * 0.3 + (rnd2 - 0.5) * 0.05
    bcol = nb.ramp(rnd, [(0.0, lin("#5a2a1e")), (0.5, lin("#7a3a26")), (0.85, lin("#8a4a32")), (1.0, lin("#4a3a34"))])
    col = nb.mulc(bcol, 0.85 + (surf - 0.5) * 0.3)
    soot = nb.smooth(nb.noise(3, detail=6, seed=185), 0.5, 0.8)
    col = nb.mixc(col, nb.mulc(col, 0.45), soot * 0.7)
    col = nb.mixc(col, lin("#5a5650"), mortar)
    col = nb.mixc(col, lin("#6a4a3a"), chip)
    rough = 0.85 + mortar * 0.1
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp()}


def gravel(nb, p):
    d1 = nb.voronoi(55, seed=191)
    c1 = nb.voronoi(55, seed=191, out="Color")
    d2 = nb.voronoi(110, seed=192)
    c2 = nb.voronoi(110, seed=192, out="Color")
    st1 = nb.smooth(d1, 0.6, 0.05)
    st2 = nb.smooth(d2, 0.6, 0.05)
    top = nb.gt(st1, st2 * 0.8)
    h = nb.maxf(st1, st2 * 0.8) + (nb.noise(200, detail=2, seed=193) - 0.5) * 0.06
    sc = nb.lerp(c2, c1, top)
    col = nb.ramp(sc, [(0.0, lin("#4a4a48")), (0.4, lin("#6b6862")), (0.7, lin("#7e766a")), (1.0, lin("#55504a"))])
    col = nb.mulc(col, 0.5 + h * 0.6)
    rust = nb.smooth(nb.noise(4, detail=5, seed=194), 0.55, 0.8)
    col = nb.mixc(col, lin("#4a3020"), rust * 0.5)
    rough = 0.88 - rust * 0.05
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": h.clamp()}


# ============================================================================================== emissive / fit
def emit_panel(nb, p):
    """Recessed light panel (UV fit 0..1): dark frame, prismatic diffuser."""
    c = p["color"]
    du = nb.minf(nb.u, 1 - nb.u)
    dv = nb.minf(nb.v, 1 - nb.v)
    d = nb.minf(du, dv)
    frame = nb.smooth(d, 0.045, 0.04)
    lip = nb.smooth(d, 0.06, 0.05) - frame
    prism = nb.maxf(nb.smooth(nb.grid_dist(nb.u, 48), 0.0016, 0.0), nb.smooth(nb.grid_dist(nb.v, 24), 0.003, 0.0))
    glow = (1.0 - nb.smooth(d, 0.06, 0.2) * 0.25) * (1.0 - prism * 0.2)
    diff = nb.mulc(lin("#d8dcdc"), 0.9 + prism * 0.1)
    col = nb.mixc(diff, lin("#2b2e31"), nb.maxf(frame, lip * 0.6))
    em = nb.mulc(c, glow * (1.0 - frame) * (1.0 - lip))
    h = 0.6 + frame * 0.3 - lip * 0.2 - prism * 0.05
    rough = nb.lerp(0.3, 0.45, frame)
    return {"color": col, "rough": rough, "metal": frame * 0.6, "height": h.clamp(), "emit": em}


def emit_strip(nb, p):
    """LED strip (U along length, 0.5 m repeat; V across 0..1): housing edges, diffused LED line."""
    c = p["color"]
    dv = nb.absf(nb.v - 0.5)
    housing = nb.smooth(dv, 0.36, 0.40)
    core = nb.smooth(dv, 0.34, 0.0)
    leds = nb.sin(nb.u * (6.2831853 * 24)) * 0.5 + 0.5
    em = nb.mulc(c, core * (0.85 + leds * 0.15))
    col = nb.mixc(lin("#e0e4e4"), lin("#26292c"), housing)
    h = 0.5 + housing * 0.3 - core * 0.1
    return {"color": col, "rough": nb.lerp(0.25, 0.5, housing), "metal": housing * 0.5, "height": h.clamp(), "emit": em}


def screen(nb, p):
    """Blank display (UV fit). Unity puts text / a RenderTexture on top; this is the 'off' look."""
    px = nb.maxf(nb.smooth(nb.grid_dist(nb.u, 320), 0.0004, 0.0), nb.smooth(nb.grid_dist(nb.v, 180), 0.0007, 0.0))
    d = nb.minf(nb.minf(nb.u, 1 - nb.u), nb.minf(nb.v, 1 - nb.v))
    vign = nb.smooth(d, 0.0, 0.25)
    smudge = nb.noise(3, detail=4, seed=201)
    col = nb.mulc(lin("#0b1418"), 1.0 - px * 0.3)
    em = nb.mulc(lin("#103040"), (0.25 + vign * 0.35) * (1 - px * 0.4))
    rough = 0.08 + (smudge - 0.5) * 0.08
    return {"color": col, "rough": rough.clamp(), "metal": 0.0, "height": 0.5, "emit": em}


def window_lit(nb, p):
    """Lit apartment window seen from outside (UV fit): mullion cross, blinds, warm/cool interior."""
    c = p["color"]
    du = nb.minf(nb.u, 1 - nb.u)
    dv = nb.minf(nb.v, 1 - nb.v)
    frame = nb.smooth(nb.minf(du, dv), 0.035, 0.03)
    mull = nb.smooth(nb.absf(nb.u - 0.5), 0.012, 0.008)
    blind_h = nb.smooth(nb.v, 0.62, 0.6)  # blinds cover the top 40 %
    slats = nb.sin(nb.v * 220.0) * 0.5 + 0.5
    room = nb.noise(3, detail=3, seed=211)
    grad = nb.smooth(nb.v, 0.0, 1.0)
    inten = (0.55 + room * 0.5 + grad * 0.2) * (1 - blind_h * (0.35 + slats * 0.3))
    inten = inten * (1 - nb.maxf(frame, mull))
    em = nb.mulc(c, inten)
    col = nb.mixc(nb.mulc(c, 0.25), lin("#1e2226"), nb.maxf(frame, mull))
    h = 0.5 + nb.maxf(frame, mull) * 0.4
    return {"color": col, "rough": nb.lerp(0.05, 0.5, nb.maxf(frame, mull)), "metal": 0.0, "height": h.clamp(), "emit": em}


# ============================================================================================== registry
CYAN, VIOLET, WARM = lin("#5fd8ff"), lin("#a77bff"), lin("#ffd2a0")
NEON_HEX = {"magenta": "#ff2bd6", "pink": "#ff4f9a", "cyan": "#00e5ff", "blue": "#3d7bff", "yellow": "#ffe14d", "violet": "#9b5cff"}
NEON = {k: lin(v) for k, v in NEON_HEX.items()}
NEON_SRGB = {k: [round(int(v[i:i + 2], 16) / 255.0, 3) for i in (1, 3, 5)] for k, v in NEON_HEX.items()}


def T(define, tile, depth, uv="world", params=None, unity=None, **kw):
    d = {"kind": "baked", "define": define, "tile": tile, "depth": depth, "uv": uv, "params": params or {}, "unity": unity or {}}
    d.update(kw)
    return d


def TINT(parent, params, unity=None):
    return {"kind": "tint", "parent": parent, "params": params, "unity": unity or {}}


def P(unity, preview):
    """Parameter-only material (no textures)."""
    return {"kind": "param", "unity": unity, "preview": preview}


REGISTRY = {
    # ---- ground / structure
    "concrete": T(HD.concrete, 2.0, 0.006, normal_strength=1.4, res=2048),
    "concrete_dark": TINT("concrete", {"base": lin("#4a4e53")}),
    "concrete_wet": T(HD.concrete, 2.0, 0.006, params={"base": g(0.40), "wet": 1.0}, normal_strength=1.4, res=2048),
    "asphalt": T(HD.asphalt, 4.0, 0.008, normal_strength=1.2, res=2048),
    "paving": T(HD.paving, 3.0, 0.012, normal_strength=1.0, res=2048),
    "plaster": T(HD.plaster, 2.0, 0.006, normal_strength=1.2, res=2048),
    "brick": T(HD.brick, 1.8, 0.012, res=2048),
    "gravel": T(gravel, 2.0, 0.03),
    # ---- metals
    "metal_painted": T(HD.metal_painted, 2.0, 0.0015, ao_strength=0.6, res=2048),
    "metal_painted_red": TINT("metal_painted", {"tint": lin("#6e1f17")}),
    "metal_painted_yellow": TINT("metal_painted", {"tint": lin("#b08a1c")}),
    "metal_painted_white": TINT("metal_painted", {"tint": lin("#bfc2c0")}),
    "metal_painted_green": TINT("metal_painted", {"tint": lin("#3b4733")}),
    "metal_dark": TINT("metal_painted", {"tint": lin("#2a2d31")}),
    "metal_bare": T(HD.metal_bare, 1.0, 0.0004, ao_strength=0.4, res=2048),
    "metal_rusted": T(HD.metal_rusted, 2.0, 0.003, res=2048),
    "metal_plate": T(HD.metal_plate, 2.0, 0.006, ao_strength=0.8, res=2048),
    "corrugated": T(HD.corrugated, 1.0, 0.018, ao_strength=0.5, ao_radii=(0.01, 0.03), res=2048),
    "grating": T(HD.grating, 1.0, 0.03, ao_strength=0.5, unity={"alphaClip": 0.5, "cull": "Off"}, res=2048),
    # ---- interior
    "metro_tile": T(HD.metro_tile, 1.2, 0.004, normal_strength=1.0, res=2048),
    "lab_panel": T(HD.lab_panel, 2.4, 0.004, res=2048),
    "lab_floor": T(HD.lab_floor, 2.0, 0.002, res=2048),
    # ---- soft / misc
    "rubber": T(rubber, 1.0, 0.0008),
    "tarp": T(tarp, 1.0, 0.003, unity={"cull": "Off"}),
    "tarp_blue": TINT("tarp", {"tint": lin("#22374f")}, unity={"cull": "Off"}),
    "wood": T(wood, 1.0, 0.003),
    "car_paint_grey": T(car_paint, 2.0, 0.0008, params={"tint": lin("#5a6068")}, ao_strength=0.3),
    "car_paint_dark": TINT("car_paint_grey", {"tint": lin("#23272c")}),
    "car_paint_red": TINT("car_paint_grey", {"tint": lin("#6a1b15")}),
    "car_paint_white": TINT("car_paint_grey", {"tint": lin("#b3b7b6")}),
    # ---- emissive / UV-fit
    "emit_panel_cyan": T(emit_panel, 1.0, 0.004, uv="fit", params={"color": CYAN}, unity={"emission": [0.373, 0.847, 1.0], "emissionIntensity": 3.0}),
    "emit_panel_violet": T(emit_panel, 1.0, 0.004, uv="fit", params={"color": VIOLET}, unity={"emission": [0.655, 0.482, 1.0], "emissionIntensity": 3.0}),
    "emit_panel_white": T(emit_panel, 1.0, 0.004, uv="fit", params={"color": lin("#e8f2ff")}, unity={"emission": [0.91, 0.95, 1.0], "emissionIntensity": 2.6}),
    "emit_panel_warm": T(emit_panel, 1.0, 0.004, uv="fit", params={"color": WARM}, unity={"emission": [1.0, 0.824, 0.627], "emissionIntensity": 2.5}),
    "emit_strip_cyan": T(emit_strip, 0.5, 0.002, uv="strip", params={"color": CYAN}, unity={"emissionIntensity": 4.0}),
    "emit_strip_violet": T(emit_strip, 0.5, 0.002, uv="strip", params={"color": VIOLET}, unity={"emissionIntensity": 4.0}),
    "emit_strip_warm": T(emit_strip, 0.5, 0.002, uv="strip", params={"color": WARM}, unity={"emissionIntensity": 3.0}),
    "screen": T(screen, 1.0, 0.001, uv="fit", unity={"emissionIntensity": 1.0}),
    "window_lit_warm": T(window_lit, 1.0, 0.004, uv="fit", params={"color": lin("#ffb878")}, unity={"emissionIntensity": 1.2}),
    "window_lit_cool": T(window_lit, 1.0, 0.004, uv="fit", params={"color": lin("#8fd0ff")}, unity={"emissionIntensity": 1.0}),
    # ---- cyberpunk surfaces (baked)
    "paint_glossy_dark": T(HD.paint_glossy, 2.0, 0.0008, params={"tint": lin("#15181d")}, ao_strength=0.3, res=1024),
    "paint_glossy_white": TINT("paint_glossy_dark", {"tint": lin("#c9cdd1")}),
    "paint_glossy_red": TINT("paint_glossy_dark", {"tint": lin("#7a0f14")}),
    "chrome_scratched": T(HD.chrome, 1.0, 0.0004, ao_strength=0.2, res=1024),
    "carbon_panel": T(HD.carbon, 0.5, 0.0008, ao_strength=0.3, res=1024),
    "tile_grimy": T(HD.tile_grimy, 1.2, 0.004, res=1024),
    "car_paint_black": TINT("car_paint_grey", {"tint": lin("#0e1013")}),
    "car_paint_teal": TINT("car_paint_grey", {"tint": lin("#0f5560")}),
    "car_paint_yellow": TINT("car_paint_grey", {"tint": lin("#c99a12")}),
    "car_paint_magenta": TINT("car_paint_grey", {"tint": lin("#6e0f52")}),
    # LED ad screens (UV fit, emissive art with invented glyphs). Slot names start with 'screen' so Unity code can
    # swap in RenderTextures / animated sheets; the baked art is the default content.
    "screen_ad_a": T(HD.screen_ad, 1.0, 0.001, uv="fit", params={"variant": "a"}, unity={"emissionIntensity": 2.2}),
    "screen_ad_b": T(HD.screen_ad, 1.0, 0.001, uv="fit", params={"variant": "b"}, unity={"emissionIntensity": 2.2}),
    "screen_ad_c": T(HD.screen_ad, 1.0, 0.001, uv="fit", params={"variant": "c"}, unity={"emissionIntensity": 2.2}),
    # distant skyline facades: emissive window grids, UV 'world0' (metres from asset origin, no random offset)
    "skyline_windows_a": T(HD.skyline_windows, 19.2, 0.05, uv="world0", params={"kind": "a"}, unity={"emissionIntensity": 1.6}),
    "skyline_windows_b": T(HD.skyline_windows, 16.0, 0.05, uv="world0", params={"kind": "b"}, unity={"emissionIntensity": 1.6}),
    "skyline_windows_c": T(HD.skyline_windows, 14.4, 0.05, uv="world0", params={"kind": "c"}, unity={"emissionIntensity": 1.8}),
    # extra LED strips / light boxes in the neon palette
    "emit_strip_magenta": T(emit_strip, 0.5, 0.002, uv="strip", params={"color": NEON["magenta"]}, unity={"emissionIntensity": 4.5}),
    "emit_strip_pink": T(emit_strip, 0.5, 0.002, uv="strip", params={"color": NEON["pink"]}, unity={"emissionIntensity": 4.5}),
    "emit_strip_blue": T(emit_strip, 0.5, 0.002, uv="strip", params={"color": NEON["blue"]}, unity={"emissionIntensity": 4.5}),
    "emit_strip_yellow": T(emit_strip, 0.5, 0.002, uv="strip", params={"color": NEON["yellow"]}, unity={"emissionIntensity": 4.0}),
    "emit_panel_magenta": T(emit_panel, 1.0, 0.004, uv="fit", params={"color": NEON["magenta"]}, unity={"emissionIntensity": 3.0}),
    "emit_panel_yellow": T(emit_panel, 1.0, 0.004, uv="fit", params={"color": NEON["yellow"]}, unity={"emissionIntensity": 3.0}),
    # ---- neon tubes (parameter-only emissive; HDR intensity drives bloom). 'emit_' prefix on purpose: the zone
    # code switches every 'emit_*' slot for power on/off and the importer disables shadows for emissive-only parts.
    **{f"emit_neon_{k}": P({"surface": "Opaque", "baseColor": [round(c * 0.8, 3) for c in NEON_SRGB[k]] + [1.0], "smoothness": 0.85,
                           "emission": NEON_SRGB[k], "emissionIntensity": 6.0}, NEON[k]) for k in NEON},
    # ---- holograms (additive transparent; Unity can replace with a scanline/flicker shader)
    "holo_cyan": P({"surface": "Transparent", "blend": "Additive", "baseColor": [0.0, 0.898, 1.0, 0.35], "emission": [0.0, 0.898, 1.0],
                    "emissionIntensity": 1.6, "cull": "Off"}, NEON["cyan"]),
    "holo_magenta": P({"surface": "Transparent", "blend": "Additive", "baseColor": [1.0, 0.169, 0.839, 0.35], "emission": [1.0, 0.169, 0.839],
                       "emissionIntensity": 1.6, "cull": "Off"}, NEON["magenta"]),
    # ---- parameter-only
    "glass": P({"surface": "Transparent", "baseColor": [0.56, 0.71, 0.78, 0.22], "metallic": 0.0, "smoothness": 0.95, "cull": "Off"}, (0.56, 0.71, 0.78)),
    "glass_dark": P({"surface": "Opaque", "baseColor": [0.043, 0.07, 0.094, 1.0], "metallic": 0.6, "smoothness": 0.92}, (0.043, 0.07, 0.094)),
    "plastic_dark": P({"surface": "Opaque", "baseColor": [0.06, 0.065, 0.07, 1.0], "metallic": 0.0, "smoothness": 0.45}, (0.06, 0.065, 0.07)),
    "plastic_orange": P({"surface": "Opaque", "baseColor": [0.75, 0.2, 0.03, 1.0], "metallic": 0.0, "smoothness": 0.45}, (0.75, 0.2, 0.03)),
    "black": P({"surface": "Opaque", "baseColor": [0.02, 0.02, 0.02, 1.0], "metallic": 0.0, "smoothness": 0.1}, (0.02, 0.02, 0.02)),
    "emit_red": P({"surface": "Opaque", "baseColor": [0.2, 0.02, 0.02, 1.0], "smoothness": 0.6, "emission": [1.0, 0.227, 0.18], "emissionIntensity": 3.0}, (1.0, 0.227, 0.18)),
    "emit_green": P({"surface": "Opaque", "baseColor": [0.02, 0.2, 0.08, 1.0], "smoothness": 0.6, "emission": [0.32, 1.0, 0.6], "emissionIntensity": 2.6}, (0.32, 1.0, 0.6)),
    "emit_amber": P({"surface": "Opaque", "baseColor": [0.2, 0.12, 0.02, 1.0], "smoothness": 0.6, "emission": [1.0, 0.635, 0.12], "emissionIntensity": 2.8}, (1.0, 0.635, 0.12)),
    "emit_white": P({"surface": "Opaque", "baseColor": [0.8, 0.82, 0.85, 1.0], "smoothness": 0.6, "emission": [0.91, 0.95, 1.0], "emissionIntensity": 2.6}, (0.91, 0.95, 1.0)),
    "emit_cyan": P({"surface": "Opaque", "baseColor": [0.05, 0.2, 0.25, 1.0], "smoothness": 0.6, "emission": [0.373, 0.847, 1.0], "emissionIntensity": 3.2}, (0.373, 0.847, 1.0)),
    "emit_violet": P({"surface": "Opaque", "baseColor": [0.15, 0.1, 0.25, 1.0], "smoothness": 0.6, "emission": [0.655, 0.482, 1.0], "emissionIntensity": 3.0}, (0.655, 0.482, 1.0)),
    "car_headlight": P({"surface": "Opaque", "baseColor": [0.75, 0.78, 0.8, 1.0], "metallic": 0.2, "smoothness": 0.9, "emission": [0.91, 0.95, 1.0], "emissionIntensity": 0.0}, (0.75, 0.78, 0.8)),
    "car_taillight": P({"surface": "Opaque", "baseColor": [0.35, 0.03, 0.03, 1.0], "metallic": 0.0, "smoothness": 0.85, "emission": [1.0, 0.1, 0.06], "emissionIntensity": 0.0}, (0.35, 0.03, 0.03)),
    "aether_energy": P({"surface": "Transparent", "blend": "Additive", "baseColor": [0.373, 0.847, 1.0, 0.6], "emission": [0.373, 0.847, 1.0], "emissionIntensity": 2.2,
                        "note": "Use the game's Aether energy shader (fresnel + flowing cyan/violet noise). Params here are a fallback."}, (0.4, 0.85, 1.0)),
    "water": P({"surface": "Transparent", "baseColor": [0.04, 0.078, 0.094, 0.85], "metallic": 0.2, "smoothness": 0.94}, (0.04, 0.078, 0.094)),
}

# Agent-owned extension registries: matext_<owner>.py files may define REGISTRY = {name: P(...)} with
# PARAMETER-ONLY materials (no bakes). They are merged here so every tool sees one registry.
def _merge_ext():
    import glob
    import importlib
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    for f in sorted(glob.glob(os.path.join(here, "matext_*.py"))):
        mod = importlib.import_module(os.path.basename(f)[:-3])
        for k, v in getattr(mod, "REGISTRY", {}).items():
            if k not in REGISTRY:
                REGISTRY[k] = v


_merge_ext()

# Map from the prototype's MatName (src/render/Materials.ts) to these materials.
PROTO_MAP = {
    "concrete": "concrete", "curb": "concrete", "concrete_dark": "concrete_dark", "concrete_wet": "concrete_wet",
    "asphalt": "asphalt", "paving": "paving", "plaster": "plaster", "brick": "brick",
    "metal": "metal_bare", "metal_dark": "metal_dark", "metal_painted": "metal_painted", "metal_red": "metal_painted_red",
    "metal_yellow": "metal_painted_yellow", "rust": "metal_rusted", "grate": "grating",
    "tile_lab": "metro_tile", "floor_lab": "lab_floor", "panel_lab": "lab_panel",
    "glass": "glass", "glass_dark": "glass_dark", "rubber": "rubber", "wood": "wood", "tarp": "tarp", "tarp_blue": "tarp_blue",
    "emit_cyan": "emit_cyan", "emit_violet": "emit_violet", "emit_warm": "emit_panel_warm", "emit_red": "emit_red",
    "emit_white": "emit_white", "emit_amber": "emit_amber", "emit_green": "emit_green",
    "win_warm": "window_lit_warm", "win_cool": "window_lit_cool", "water": "water", "aether": "aether_energy",
    "black": "black", "screen": "screen", "vehicle": "car_paint_grey", "vehicle_dark": "car_paint_dark", "rock": "concrete_dark",
    "cable": "rubber",
}


def preview_color(name):
    """Representative linear colour for untextured export/preview materials."""
    d = REGISTRY[name]
    if d["kind"] == "param":
        return d["preview"]
    p = d["params"]
    for k in ("tint", "base", "color"):
        if k in p:
            return p[k]
    return (0.3, 0.3, 0.3)
