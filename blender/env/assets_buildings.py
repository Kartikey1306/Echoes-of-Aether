"""Complete cyberpunk buildings (mid/high-rise assemblies of the facade kit), distant skyline megatowers with emissive
window-grid textures and ad panels, skybridges and catwalks.

Assemblies: pivot base-centre of the building MASS (the facade modules project outside it; notes give the full
footprint including projections). Front = Blender -Y = Unity +Z. Storey 3.4 m. They replace a prototype box block of
(mass width x depth x roof height): the zone code can drop one in at the block centre instead of B.Box + PzKit.Building.

Skyline towers: low poly, UV 'world0' window grids (skyline_windows_a/b/c) aligned to the geometry (widths are
multiples of 2 x the window pitch, heights multiples of the floor pitch), LED fins, ad panels (screen_ad_*), beacons.
"""
import math
import random

import envkit as K
from envkit import box, cyl, tube, torus, beam, lathe, detail
import assets_facade as F
from assets_facade import bx, H as STOREY

NEON_LIST = F.NEONS
STRIPS = F.NEON_STRIP


class lod_cap:
    """Temporarily raise K.LOD to at least `lvl` (detail tiering inside an assembly)."""

    def __init__(self, lvl):
        self.lvl = lvl

    def __enter__(self):
        self.prev = K.LOD
        K.set_lod(max(K.LOD, self.lvl))

    def __exit__(self, *a):
        K.set_lod(self.prev)
        return False


# ============================================================================================== roof furniture
def water_tower(x, y, z, r=1.4, h=2.6, legs=2.4):
    if K.LOD >= 2:
        cyl(r, h + legs, 8, at=(x, y, z), mat="metal_rusted")
        return
    for a in range(4):
        ang = math.radians(45 + a * 90)
        lx, ly = x + math.cos(ang) * r * 0.75, y + math.sin(ang) * r * 0.75
        beam((lx, ly, z), (lx, ly, z + legs), 0.12, 0.12, mat="metal_dark")
    if detail():
        for a in range(4):
            a0, a1 = math.radians(45 + a * 90), math.radians(135 + a * 90)
            beam((x + math.cos(a0) * r * 0.75, y + math.sin(a0) * r * 0.75, z + 0.2),
                 (x + math.cos(a1) * r * 0.75, y + math.sin(a1) * r * 0.75, z + legs - 0.2), 0.05, 0.05, mat="metal_dark")
    cyl(r + 0.05, 0.12, K.seg(20), at=(x, y, z + legs), mat="metal_dark")
    t = cyl(r, h, K.seg(20), at=(x, y, z + legs + 0.12), mat="wood" if (int(x * 7) % 2) else "metal_rusted")
    if detail():
        for k in (0.3, 0.5, 0.75):
            torus(r + 0.02, 0.025, n_major=K.seg(20, 8), n_minor=4, mat="metal_dark").move(x, y, z + legs + 0.12 + h * k)
    lathe([(r + 0.08, 0.0), (r * 0.15, 0.7), (0.0, 0.75)], K.seg(20), at=(x, y, z + legs + 0.12 + h), mat="metal_dark")
    if detail():
        tube([(x + r, y, z + legs + 0.3), (x + r + 0.3, y, z + legs + 0.1), (x + r + 0.3, y, z + 0.1)], 0.06, 6, "metal_dark")


def roof_ac(x, y, z, rot=0.0):
    w, d, h = 1.5, 1.0, 1.0
    p0 = K.part_count()
    bx(-w / 2, w / 2, -d / 2, d / 2, 0.12, 0.12 + h, "metal_painted_white", bevel=0.02)
    for sx in (-1, 1):
        bx(sx * w / 2 - 0.06 * sx - 0.03, sx * w / 2 - 0.06 * sx + 0.03, -d / 2, d / 2, 0.0, 0.12, "metal_dark")
    if K.LOD < 2:
        cyl(0.36, 0.04, K.seg(20), at=(0, 0, 0.12 + h), mat="black")
        if detail():
            torus(0.36, 0.02, n_major=16, n_minor=4, mat="metal_dark").move(0, 0, 0.12 + h + 0.04)
            for a in range(0, 180, 45):
                bx(-0.36, 0.36, -0.01, 0.01, 0.0, 0.015, "metal_dark").rot(z=a).move(0, 0, 0.12 + h + 0.03)
            bx(-w / 2 + 0.1, w / 2 - 0.1, -d / 2 - 0.01, -d / 2, 0.25, 0.95, "grating")
    for p in K.parts_since(p0):
        p.rot(z=rot).move(x, y, z)


def antenna(x, y, z, h=6.0, beacon=True):
    cyl(0.06, h, K.seg(8), at=(x, y, z), r2=0.03, mat="metal_dark")
    if K.LOD < 2:
        for k in (0.35, 0.65):
            for a in (0, 120, 240):
                ang = math.radians(a)
                beam((x, y, z + h * k), (x + math.cos(ang) * 0.5, y + math.sin(ang) * 0.5, z + h * k + 0.4), 0.02, 0.02, mat="metal_bare")
        if detail():
            for a in (0, 120, 240):
                ang = math.radians(a)
                tube([(x, y, z + h * 0.7), (x + math.cos(ang) * 1.6, y + math.sin(ang) * 1.6, z)], 0.006, 4, "metal_bare")
    if beacon:
        cyl(0.07, 0.12, 8, at=(x, y, z + h), mat="emit_red")


def dish(x, y, z, r=0.6, rot=0.0):
    p0 = K.part_count()
    cyl(0.04, 1.0, 8, at=(0, 0, 0), mat="metal_dark")
    d = lathe([(0.02, 0.0), (r * 0.5, 0.05), (r, 0.2), (r * 0.98, 0.21)], K.seg(16), at=(0, 0, 0), mat="metal_painted_white", close_top=False)
    d.rot(x=-55).move(0, 0.1, 1.05)
    if detail():
        beam((0, 0.1, 1.05), (0, -0.35, 1.45), 0.015, 0.015, mat="metal_dark")
    for p in K.parts_since(p0):
        p.rot(z=rot).move(x, y, z)


def bulkhead(x, y, z, w=3.0, d=4.0, h=2.8, led="emit_strip_cyan"):
    """Roof stair bulkhead with door (front -Y), LED lip and a lamp."""
    bx(x - w / 2, x + w / 2, y - d / 2, y + d / 2, z, z + h, "concrete", bevel=0.02)
    bx(x - w / 2 - 0.1, x + w / 2 + 0.1, y - d / 2 - 0.1, y + d / 2 + 0.1, z + h, z + h + 0.15, "concrete_dark", bevel=0.01)
    if K.LOD < 2:
        bx(x - 0.5, x + 0.5, y - d / 2 - 0.03, y - d / 2 + 0.01, z, z + 2.1, "metal_painted", bevel=0.006)
        bx(x - w / 2 - 0.1, x + w / 2 + 0.1, y - d / 2 - 0.12, y - d / 2 - 0.1, z + h + 0.02, z + h + 0.06, led)
        bx(x + 0.65, x + 0.85, y - d / 2 - 0.08, y - d / 2, z + 2.2, z + 2.35, "emit_amber")


def billboard_rig(x, y, z, w=12.0, h=5.0, lift=2.5, mat="screen_ad_a", rot=0.0):
    """Roof billboard on a steel truss: screen face toward local -Y, catwalk, spot lights."""
    p0 = K.part_count()
    legs = [-w / 2 + 0.6, 0.0, w / 2 - 0.6] if w > 8 else [-w / 2 + 0.5, w / 2 - 0.5]
    for lx in legs:
        beam((lx, 0.4, 0), (lx, 0.4, lift + h), 0.2, 0.2, mat="metal_dark")
        beam((lx, 1.6, 0), (lx, 0.4, lift + h * 0.6), 0.12, 0.12, mat="metal_dark")
    if K.LOD < 2:
        for zz in (lift, lift + h):
            beam((-w / 2, 0.4, zz), (w / 2, 0.4, zz), 0.14, 0.14, mat="metal_dark")
        if detail():
            for i in range(len(legs) - 1):
                beam((legs[i], 0.4, lift), (legs[i + 1], 0.4, lift + h), 0.06, 0.06, mat="metal_dark")
    bx(-w / 2 - 0.15, w / 2 + 0.15, -0.05, 0.3, lift - 0.15, lift + h + 0.15, "metal_dark", bevel=0.03)
    bx(-w / 2, w / 2, -0.07, -0.05, lift, lift + h, mat)
    if K.LOD < 2:
        bx(-w / 2 - 0.15, w / 2 + 0.15, -0.09, -0.05, lift - 0.17, lift - 0.13, "emit_strip_magenta")
        bx(-w / 2 - 0.15, w / 2 + 0.15, -0.09, -0.05, lift + h + 0.13, lift + h + 0.17, "emit_strip_cyan")
        # catwalk + rail under the screen
        bx(-w / 2, w / 2, -1.0, 0.3, lift - 0.45, lift - 0.4, "grating")
        tube([(-w / 2, -1.0, lift + 0.6), (w / 2, -1.0, lift + 0.6)], 0.025, 6, "metal_painted_yellow")
        if detail():
            for i in range(int(w / 3)):
                lx = -w / 2 + 1.5 + i * 3
                beam((lx, -0.9, lift - 0.4), (lx, -1.5, lift - 0.2), 0.04, 0.04, mat="metal_dark")
                cyl(0.12, 0.25, 10, at=(lx, -1.5, lift - 0.3), axis="Y", mat="metal_dark").rot_about((lx, -1.5, lift - 0.2), x=-60)
    for p in K.parts_since(p0):
        p.rot(z=rot).move(x, y, z)


def blade_sign(x, y, z, height, neon, seed, rot=0.0, cells=None):
    """Big vertical blade sign spanning several storeys, projecting from a facade (local +Y = wall)."""
    p0 = K.part_count()
    n = cells or max(3, int(height / 1.6))
    ch = height / n
    bx(-0.12, 0.12, -1.3, 0.0, 0.0, height, "metal_dark", bevel=0.03)
    for side in (-1, 1):
        bx(side * 0.12, side * 0.125, -1.25, -0.05, 0.05, height - 0.05, "black")
    if K.LOD < 2:
        rng = random.Random(seed)
        for side in (-1, 1):
            for i in range(n):
                gz = (n - 1 - i) * ch
                for (a, b) in F.glyph_segments(rng):
                    pa = (side * 0.16, -1.15 + a[0] * 1.0, gz + 0.12 + a[1] * (ch - 0.24))
                    pb = (side * 0.16, -1.15 + b[0] * 1.0, gz + 0.12 + b[1] * (ch - 0.24))
                    if math.dist(pa, pb) > 0.03:
                        tube([pa, pb], 0.022, K.seg(5, 4), neon, caps=False)
            bx(side * 0.12, side * 0.14, -1.3, -0.0, -0.03, 0.0, "metal_dark")
        for zz in (0.3, height - 0.3):
            beam((0, 0, zz), (0, -0.6, zz), 0.06, 0.06, mat="metal_dark")
        bx(-0.14, 0.14, -1.33, -1.3, 0.0, height, STRIPS[seed % len(STRIPS)])
    for p in K.parts_since(p0):
        p.rot(z=rot).move(x, y, z)


def roof_neon(x, y, z, count, neon, seed, cell=1.6, rot=0.0):
    """Rooftop neon glyph letters on a scaffold frame (local front -Y)."""
    p0 = K.part_count()
    w = count * cell
    for lx in (-w / 2, 0.0, w / 2):
        beam((lx, 0.3, 0.0), (lx, 0.3, cell + 0.6), 0.08, 0.08, mat="metal_dark")
        beam((lx, 1.0, 0.0), (lx, 0.3, cell * 0.7), 0.05, 0.05, mat="metal_dark")
    beam((-w / 2, 0.3, 0.5), (w / 2, 0.3, 0.5), 0.08, 0.08, mat="metal_dark")
    if K.LOD < 2:
        rng = random.Random(seed)
        for i in range(count):
            gx = -w / 2 + i * cell
            for (a, b) in F.glyph_segments(rng):
                pa = (gx + 0.12 + a[0] * (cell - 0.24), 0.0, 0.5 + a[1] * cell)
                pb = (gx + 0.12 + b[0] * (cell - 0.24), 0.0, 0.5 + b[1] * cell)
                if math.dist(pa, pb) > 0.03:
                    tube([pa, pb], 0.03, K.seg(5, 4), neon, caps=False)
                    if detail():
                        beam(pa, (pa[0], 0.3, pa[2]), 0.015, 0.015, mat="metal_dark")
    for p in K.parts_since(p0):
        p.rot(z=rot).move(x, y, z)


def fire_escape(x0, x1, yw, floors, z0=3.4):
    """Steel fire escape on a wall (wall at y=yw, platforms toward -Y): landings each storey, zig-zag stairs, rails."""
    dep = 1.2
    for f in range(floors):
        z = z0 + f * STOREY
        bx(x0, x1, yw - dep, yw, z - 0.06, z, "grating")
        bx(x0, x1, yw - dep - 0.02, yw - dep + 0.03, z - 0.14, z, "metal_dark")
        if K.LOD < 2:
            tube([(x0, yw - dep, z + 1.0), (x1, yw - dep, z + 1.0)], 0.02, 6, "metal_dark")
            for xx in (x0, x1):
                tube([(xx, yw, z + 1.0), (xx, yw - dep, z + 1.0)], 0.02, 6, "metal_dark")
            n = int((x1 - x0) / 0.6)
            for i in range(n + 1):
                xx = x0 + i * (x1 - x0) / n
                cyl(0.01, 1.0, 4, at=(xx, yw - dep, z), mat="metal_dark")
            for xx in (x0 + 0.1, x1 - 0.1):
                beam((xx, yw - dep, z - 0.1), (xx, yw, z - 0.9), 0.05, 0.05, mat="metal_dark")
        if f < floors - 1 and K.LOD < 2:
            # stair flight to the next landing
            a = (x1 - 0.2 if f % 2 == 0 else x0 + 0.2, yw - dep * 0.5, z)
            b = (x0 + 1.6 if f % 2 == 0 else x1 - 1.6, yw - dep * 0.5, z + STOREY)
            beam(a, b, 0.75, 0.06, mat="grating", up=(0, 0, 1))
            for dy in (-0.38, 0.38):
                beam((a[0], a[1] + dy, a[2]), (b[0], b[1] + dy, b[2]), 0.04, 0.2, mat="metal_dark", up=(0, 0, 1))
    if K.LOD < 2:
        # drop ladder from the first landing
        for dx in (-0.2, 0.2):
            cyl(0.015, z0 - 0.8, 4, at=(x1 - 0.5 + dx, yw - dep + 0.1, 0.8), mat="metal_dark")
        for k in range(7):
            beam((x1 - 0.7, yw - dep + 0.1, 1.0 + k * 0.3), (x1 - 0.3, yw - dep + 0.1, 1.0 + k * 0.3), 0.02, 0.02, mat="metal_dark")


# ============================================================================================== assembly
def _module_lite(style, kind, seed, ground=False):
    """Massing-tier module (~40-90 tris) built on the building MASS face (local y=+0.15 is the mass face):
    glass panes 2 cm proud with sills, pier strips, floor band, and a one-box stand-in for AC / cage / neon / balcony."""
    s = F.STY[style]
    rnd = random.Random(seed * 13 + 5)
    yf = 0.15  # mass face
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 2.0, sx * 1.75))
        bx(x0, x1, yf - 0.1, yf, 0.0, STOREY, s["pil"])
    bx(-1.75, 1.75, yf - 0.08, yf, 0.0, 0.3, s["band"])
    if ground:
        g_ = "window_lit_warm" if rnd.random() < 0.6 else ("window_lit_cool" if rnd.random() < 0.5 else "metal_painted")
        bx(-1.65, 1.65, yf - 0.03, yf, 0.0, 2.7, g_)
        bx(-1.8, 1.8, yf - 0.4, yf, 2.78, 3.3, "metal_dark")
        bx(-1.7, 1.7, yf - 0.41, yf - 0.4, 2.84, 3.24, rnd.choice(["screen_ad_a", "screen_ad_b", "screen_ad_c"]))
        return
    lit = rnd.random()
    gm = "window_lit_warm" if lit < 0.18 else ("window_lit_cool" if lit < 0.27 else ("black" if kind == "damaged" else "glass_dark"))
    if kind == "double":
        for cx in (-0.9, 0.9):
            bx(cx - 0.55, cx + 0.55, yf - 0.02, yf, 0.9, 2.6, gm)
            bx(cx - 0.65, cx + 0.65, yf - 0.12, yf, 0.84, 0.9, s["sill"])
        return
    if kind == "balcony":
        bx(-1.45, 0.25, yf - 0.02, yf, 0.2, 2.5, "glass_dark")
        bx(0.6, 1.5, yf - 0.02, yf, 1.0, 2.3, gm)
        bx(-1.9, 1.9, yf - 1.25 - 0.3, yf, 0.0, 0.2, s["band"])
        bx(-1.9, 1.9, yf - 1.55, yf - 1.5, 0.2, 1.15, "grating")
        bx(-1.85, 1.85, yf - 1.5, yf - 1.47, -0.012, 0.0, F.NEON_STRIP[seed % len(F.NEON_STRIP)])
        return
    wx = -0.35 if kind in ("window_ac", "neon") else 0.0
    bx(wx - 0.8, wx + 0.8, yf - 0.02, yf, 0.9, 2.5, gm)
    bx(wx - 0.9, wx + 0.9, yf - 0.14, yf, 0.83, 0.9, s["sill"])
    if kind == "window_ac":
        bx(0.9, 1.6, yf - 0.36, yf - 0.06, 1.05, 1.57, "metal_painted_white")
    elif kind == "cage":
        bx(-0.95, 0.95, yf - 0.5, yf, 0.82, 2.6, "grating")
    elif kind == "neon":
        bx(0.72, 1.24, yf - 0.1, yf, 0.75, 2.85, "metal_dark")
        bx(0.78, 1.18, yf - 0.11, yf - 0.1, 0.85, 2.75, F.NEONS[seed % len(F.NEONS)])
    elif kind == "pipes":
        bx(-1.5, -1.4, yf - 0.12, yf, 0.0, STOREY, "metal_dark")
        bx(0.3, 1.0, yf - 0.22, yf, 1.0, 1.95, "metal_painted")


# ============================================================================================== assembly (cont.)
_NEON_HEX = {"magenta": "#ff2bd6", "pink": "#ff4f9a", "cyan": "#00e5ff", "blue": "#3d7bff", "yellow": "#ffe14d", "violet": "#9b5cff"}


def _glow_hex(mat):
    for k, v in _NEON_HEX.items():
        if mat and k in mat:
            return v
    return "#ffb878"


FACE = {  # name: (rz deg, outward normal sign handling)
    "s": 0.0, "n": 180.0, "e": 90.0, "w": -90.0,
}


def _unity_to_blender(u):
    return (-u[0], -u[2], u[1])


def _place_module(fn, kw, face, i, nx, nz, Wm, Dm, z, collect=None):
    if face == "s":
        x, y = -Wm / 2 + 2 + 4 * i, -(Dm / 2 + 0.15)
    elif face == "n":
        x, y = Wm / 2 - 2 - 4 * i, Dm / 2 + 0.15
    elif face == "e":
        x, y = Wm / 2 + 0.15, -Dm / 2 + 2 + 4 * i
    else:
        x, y = -(Wm / 2 + 0.15), Dm / 2 - 2 - 4 * i
    pl = K.placed(x=x, y=y, z=z, rz=FACE[face])
    with pl:
        meta = fn(**kw) or {}
    if collect is not None:
        from mathutils import Vector
        for u in meta.get("lights", []):
            b = pl.m @ Vector(_unity_to_blender(u))
            collect.append({"position": [round(v, 3) for v in K.to_unity_vec(tuple(b))], "color": _glow_hex(meta.get("glowMaterial")),
                            "source": kw.get("kind", "")})


def _lod2_face(face, nx, nz, Wm, Dm, floors, rnd, style):
    """LOD2: flat facade with window planes per module (massing + glazing only)."""
    s = F.STY[style]
    n = nx if face in ("s", "n") else nz
    for i in range(n):
        for f in range(1, floors):
            g_ = "window_lit_warm" if rnd.random() < 0.18 else ("window_lit_cool" if rnd.random() < 0.08 else "glass_dark")
            with K.placed(**_face_xy(face, i, Wm, Dm, f * STOREY)):
                bx(-0.8, 0.8, -0.02, 0.0, 0.9, 2.5, g_)
        with K.placed(**_face_xy(face, i, Wm, Dm, 0.0)):
            bx(-1.65, 1.65, -0.02, 0.0, 0.0, 2.7, "window_lit_warm" if rnd.random() < 0.6 else "metal_dark")
    _ = s


def _face_xy(face, i, Wm, Dm, z, off=0.0):
    if face == "s":
        return dict(x=-Wm / 2 + 2 + 4 * i, y=-(Dm / 2 + off), z=z, rz=0.0)
    if face == "n":
        return dict(x=Wm / 2 - 2 - 4 * i, y=Dm / 2 + off, z=z, rz=180.0)
    if face == "e":
        return dict(x=Wm / 2 + off, y=-Dm / 2 + 2 + 4 * i, z=z, rz=90.0)
    return dict(x=-(Wm / 2 + off), y=Dm / 2 - 2 - 4 * i, z=z, rz=-90.0)


def building(nx=3, nz=3, floors=5, style="Plaster", seed=1, front_ground=("shop_glass", "noodle", "shop_shutter"),
             side_ground=("boarded", "entrance"), upper=("window_ac", "cage", "double", "neon", "pipes"), balcony_cols=(),
             blade=None, roof=("tower", "ac", "antenna"), billboard=None, roofneon=None, escape=None, ground_style="Concrete"):
    """Assemble a building from facade modules. nx/nz modules along X/Y (4 m each), floors storeys."""
    rnd = random.Random(seed)
    Wm, Dm = nx * 4.0, nz * 4.0
    Ztop = floors * STOREY
    # structural mass (interior), roof slab
    bx(-Wm / 2, Wm / 2, -Dm / 2, Dm / 2, 0.0, Ztop, "concrete_dark")
    bx(-Wm / 2 + 0.3, Wm / 2 - 0.3, -Dm / 2 + 0.3, Dm / 2 - 0.3, Ztop, Ztop + 0.04, "concrete_wet")
    # corner piers fill the module-free corners
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, x1 = sorted((sx * Wm / 2, sx * (Wm / 2 + 0.42)))
            y0, y1 = sorted((sy * Dm / 2, sy * (Dm / 2 + 0.42)))
            bx(x0, x1, y0, y1, 0.0, Ztop + 0.6, F.STY[style]["pil"], bevel=0.015)
    lights = []
    if K.LOD >= 2:
        for face in ("s", "n", "e", "w"):
            _lod2_face(face, nx, nz, Wm, Dm, floors, rnd, style)
    else:
        for face in ("s", "e", "w", "n"):
            n = nx if face in ("s", "n") else nz
            for i in range(n):
                for f in range(floors):
                    front = face == "s"
                    # detail tiering: street-front ground floor full detail, front floors 1-4 LOD1, everything else massing-level
                    if front:
                        tier = 0 if f == 0 else (1 if f <= 4 else 2)
                    else:
                        tier = 1 if (f == 0 and face != "n") else 2
                    if tier == 2:
                        if f == 0:
                            kinds = side_ground
                            k_ = "ground"
                        else:
                            k_ = upper[(i * 3 + f * 5 + seed + 2) % len(upper)] if not (front and i in balcony_cols) else "balcony"
                        with K.placed(**_face_xy(face, i, Wm, Dm, f * STOREY, off=0.15)):
                            _module_lite(style, k_, seed + f * 13 + i * 5, ground=(f == 0))
                        continue
                    with lod_cap(tier):
                        if f == 0:
                            kinds = front_ground if front else side_ground
                            kind = kinds[(i + seed) % len(kinds)]
                            _place_module(F._ground, {"kind": kind, "seed": seed + i * 7 + (0 if front else 3), "style": ground_style},
                                          face, i, nx, nz, Wm, Dm, 0.0, collect=lights)
                        else:
                            if front and i in balcony_cols:
                                kind = "balcony"
                            else:
                                kind = upper[(i * 3 + f * 5 + seed + (len(face) * 0 if front else 2)) % len(upper)]
                            _place_module(F._upper, {"style": style, "kind": kind, "seed": seed + f * 13 + i * 5}, face, i, nx, nz, Wm, Dm,
                                          f * STOREY, collect=lights)
                with lod_cap(1):
                    _place_module(F.cornice, {"style": style}, face, i, nx, nz, Wm, Dm, Ztop)
                with lod_cap(1), K.placed(**_face_xy(face, i, Wm, Dm, Ztop, off=-0.12)):
                    F.parapet(style)
    # roof furniture
    with lod_cap(1):
        r = rnd
        if "tower" in roof:
            water_tower(-Wm / 4, Dm / 5, Ztop, r=1.3 if Wm < 14 else 1.6)
        if "bulkhead" in roof:
            bulkhead(Wm / 4, -Dm / 5, Ztop)
        if "ac" in roof:
            for k in range(2 + (nx * nz) // 6):
                roof_ac(r.uniform(-Wm / 2 + 1.5, Wm / 2 - 1.5), r.uniform(-Dm / 2 + 1.5, Dm / 2 - 1.5), Ztop, rot=r.choice((0, 90, 180)))
        if "antenna" in roof:
            antenna(Wm / 2 - 1.2, Dm / 2 - 1.2, Ztop, h=5 + r.uniform(0, 4))
            dish(-Wm / 2 + 1.2, -Dm / 2 + 1.5, Ztop, rot=r.uniform(0, 360))
        if billboard:
            billboard_rig(0.0, Dm / 2 - 1.8, Ztop, w=min(Wm - 1.0, billboard[1]), h=billboard[2], mat=billboard[0])
        if roofneon:
            roof_neon(0.0, -Dm / 2 + 1.2, Ztop + 0.1, roofneon[0], roofneon[1], seed + 5)
            lights.append({"position": K.to_unity_vec((0, -Dm / 2 - 1.0, Ztop + 1.4)), "color": _glow_hex(roofneon[1]), "source": "roof neon"})
    if blade:
        # vertical blade sign at the front-right corner pier, floors 1..n
        with lod_cap(0 if K.LOD == 0 else 1):
            h = blade[1] * STOREY - 0.6
            blade_sign(Wm / 2 + 0.21, -(Dm / 2 + 0.42), STOREY + 0.3, h, blade[0], seed + 1, rot=90)
            lights.append({"position": K.to_unity_vec((Wm / 2 + 1.2, -(Dm / 2 + 1.0), STOREY + h / 2)), "color": _glow_hex(blade[0]), "source": "blade sign"})
    if escape and K.LOD < 2:
        with lod_cap(1):
            # on the west face: wall at x=-(Wm/2+0.15+projection); landings stick out toward -X
            p0 = K.part_count()
            fire_escape(-escape / 2, escape / 2, 0.0, floors - 1)
            for p in K.parts_since(p0):
                p.rot(z=-90).move(-(Wm / 2 + 0.55), 0.0, 0.0)
    meta = {
        "colliders": [K.collider_box((0, 0, Ztop / 2), (Wm, Dm, Ztop))],
        "massFootprint": [Wm, Dm], "roofHeight": round(Ztop, 3), "floors": floors, "storeyHeight": STOREY,
        "frontFace": "+Z (Unity)", "lights": lights,
    }
    return meta


# ============================================================================================== skyline towers
def _sky_box(x0, x1, y0, y1, z0, z1, mat, roof="concrete_dark"):
    """Tower mass: window-grid material on the walls, plain roof (separate so the grid never lands on the roof)."""
    bx(x0, x1, y0, y1, z0, z1 - 0.3, mat)
    bx(x0 - 0.2, x1 + 0.2, y0 - 0.2, y1 + 0.2, z1 - 0.3, z1, roof)


def _fins(x0, x1, y0, y1, z0, z1, strip):
    for (x, y) in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        bx(x - 0.18, x + 0.18, y - 0.18, y + 0.18, z0, z1, "metal_dark")
        if K.LOD == 0:
            bx(x - 0.2, x + 0.2, y - 0.2, y + 0.2, z0 + 1.0, z1 - 1.0, strip)


def _ad(cx, dist, z0, w, h, mat, rot=0.0):
    """Ad screen in a frame on the face at distance `dist` from the origin (face normal -Y before rotation by rot
    degrees about Z), centred at x=cx along that face."""
    p0 = K.part_count()
    y = -dist
    bx(cx - w / 2 - 0.3, cx + w / 2 + 0.3, y - 0.6, y, z0 - 0.3, z0 + h + 0.3, "metal_dark")
    bx(cx - w / 2, cx + w / 2, y - 0.64, y - 0.6, z0, z0 + h, mat)
    if K.LOD == 0:
        bx(cx - w / 2 - 0.3, cx + w / 2 + 0.3, y - 0.68, y - 0.6, z0 - 0.34, z0 - 0.3, "emit_strip_cyan")
    for p in K.parts_since(p0):
        p.rot(z=rot)
    import mathutils
    v = mathutils.Matrix.Rotation(math.radians(rot), 3, "Z") @ mathutils.Vector((cx, y - 0.64, z0 + h / 2))
    nrm = mathutils.Matrix.Rotation(math.radians(rot), 3, "Z") @ mathutils.Vector((0, -1, 0))
    return {"center": [round(x, 3) for x in K.to_unity_vec(tuple(v))], "size": [w, h], "normal": [round(x, 3) for x in K.to_unity_vec(tuple(nrm))], "material": mat}


def skyline_tower_a():
    """Stepped megatower 28.8 m square, 115.2 m + spire, magenta LED corner fins, two 14.4 x 7.2 ad screens."""
    m = "skyline_windows_c"
    _sky_box(-14.4, 14.4, -14.4, 14.4, 0.0, 72.0, m)
    _sky_box(-10.8, 10.8, -10.8, 10.8, 72.0, 100.8, m)
    _sky_box(-7.2, 7.2, -7.2, 7.2, 100.8, 115.2, "skyline_windows_b")
    _fins(-14.4, 14.4, -14.4, 14.4, 0.0, 72.0, "emit_strip_magenta")
    _fins(-10.8, 10.8, -10.8, 10.8, 72.0, 100.8, "emit_strip_cyan")
    cyl(0.6, 30.0, K.seg(8), at=(0, 0, 115.2), r2=0.12, mat="metal_dark")
    cyl(0.35, 0.6, 8, at=(0, 0, 145.2), mat="emit_red")
    screens = [_ad(0.0, 14.4, 52.0, 14.4, 7.2, "screen_ad_a"), _ad(0.0, 14.4, 52.0, 14.4, 7.2, "screen_ad_c", rot=90)]
    if K.LOD == 0:
        for z in (72.0, 100.8):
            for k in range(4):
                bx(-3 + k * 2, -2 + k * 2, -2, 2, z, z + 2.5, "metal_dark")
    return {"colliders": "none", "screens": screens, "beacons": [K.to_unity_vec((0, 0, 145.5))], "height": 145.8}


def skyline_tower_b():
    """Office slab 32 x 16 m, 80 m, roof billboard (24 x 8 m) and a mid-height LED band."""
    m = "skyline_windows_b"
    _sky_box(-16.0, 16.0, -8.0, 8.0, 0.0, 80.0, m)
    bx(-16.3, 16.3, -8.3, 8.3, 39.6, 40.4, "metal_dark")
    if K.LOD == 0:
        bx(-16.32, 16.32, -8.32, 8.32, 39.9, 40.1, "emit_strip_blue")
    with lod_cap(1):
        billboard_rig(0.0, -2.0, 80.0, w=24.0, h=8.0, lift=3.0, mat="screen_ad_b")
    for x in (-15.5, 15.5):
        cyl(0.2, 6.0, 6, at=(x, 7.5, 80.0), mat="metal_dark")
        cyl(0.18, 0.3, 6, at=(x, 7.5, 86.0), mat="emit_red")
    return {"colliders": "none", "screens": [{"center": K.to_unity_vec((0, -2.07, 87.0)), "size": [24.0, 8.0]}], "height": 91.2}


def skyline_tower_c():
    """Residential stack 38.4 x 19.2 m, 57.6 m, cantilevered upper block, giant vertical neon blade, water tanks."""
    m = "skyline_windows_a"
    _sky_box(-19.2, 19.2, -9.6, 9.6, 0.0, 38.4, m)
    _sky_box(-14.4, 24.0, -9.6, 9.6, 38.4, 57.6, m)
    bx(-19.4, 24.2, -9.8, 9.8, 38.2, 38.6, "concrete_dark")
    with lod_cap(1):
        blade_sign(-19.2, -9.6, 6.0, 28.0, "emit_neon_pink", 31, rot=0, cells=9)
        water_tower(-8.0, 3.0, 57.6, r=2.0, h=3.0, legs=3.0)
        water_tower(8.0, 3.0, 57.6, r=2.0, h=3.0, legs=3.0)
        antenna(20.0, 6.0, 57.6, h=10.0)
    return {"colliders": "none", "height": 67.8}


def skyline_twin_d():
    """Twin megatowers 24 x 24 m on a podium, 144 m, three skybridges, crown LED rings, spires."""
    m = "skyline_windows_c"
    _sky_box(-36.0, 36.0, -16.8, 16.8, 0.0, 14.4, "skyline_windows_b")
    for cx in (-21.6, 21.6):
        _sky_box(cx - 12.0, cx + 12.0, -12.0, 12.0, 14.4, 144.0, m)
        _fins(cx - 12.0, cx + 12.0, -12.0, 12.0, 14.4, 144.0, "emit_strip_cyan" if cx < 0 else "emit_strip_magenta")
        bx(cx - 9.0, cx + 9.0, -9.0, 9.0, 144.0, 152.0, "metal_dark")
        if K.LOD == 0:
            bx(cx - 9.05, cx + 9.05, -9.05, 9.05, 151.0, 151.4, "emit_strip_violet")
        cyl(0.5, 26.0, 8, at=(cx, 0, 152.0), r2=0.1, mat="metal_dark")
        cyl(0.3, 0.5, 8, at=(cx, 0, 178.0), mat="emit_red")
    for z in (43.2, 86.4, 122.4):
        bx(-9.6, 9.6, -3.0, 3.0, z, z + 4.0, "glass_dark")
        bx(-9.6, 9.6, -3.2, 3.2, z - 0.4, z, "metal_dark")
        if K.LOD == 0:
            bx(-9.6, 9.6, -3.22, -3.18, z - 0.3, z - 0.1, "emit_strip_cyan")
    screens = [_ad(-21.6, 12.0, 100.0, 14.4, 21.6, "screen_ad_c"), _ad(21.6, 12.0, 60.0, 14.4, 10.8, "screen_ad_a")]
    return {"colliders": "none", "screens": screens, "height": 178.5}


# ============================================================================================== skybridges / catwalks
def skybridge_enclosed(L=12.0, Wd=3.2, Hc=3.0):
    """Enclosed glass skybridge spanning L along X. Pivot: centre of the walkway floor (top at 0)."""
    # deck + truss underside
    bx(-L / 2, L / 2, -Wd / 2, Wd / 2, -0.25, 0.0, "metal_plate", bevel=0.02)
    for sy in (-1, 1):
        y = sy * (Wd / 2 - 0.1)
        beam((-L / 2, y, -1.1), (L / 2, y, -1.1), 0.18, 0.22, mat="metal_dark")
        beam((-L / 2, y, -0.3), (L / 2, y, -0.3), 0.15, 0.15, mat="metal_dark")
        n = int(L / 1.5)
        for i in range(n):
            xa, xb = -L / 2 + i * L / n, -L / 2 + (i + 1) * L / n
            beam((xa, y, -1.1), (xb, y, -0.3) if i % 2 == 0 else (xa, y, -0.3), 0.08, 0.08, mat="metal_dark")
            if i % 2 == 1:
                beam((xa, y, -0.3), (xb, y, -1.1), 0.08, 0.08, mat="metal_dark")
        bx(-L / 2, L / 2, y - 0.03 * sy, y + 0.03 * sy, -1.24, -1.2, STRIPS[0] if sy < 0 else STRIPS[1])
    # walls: mullions + glass, roof with LED lip
    n = int(L / 1.5)
    for sy in (-1, 1):
        y = sy * Wd / 2
        for i in range(n + 1):
            x = -L / 2 + i * L / n
            bx(x - 0.05, x + 0.05, y - 0.06, y + 0.06, 0.0, Hc, "metal_dark", bevel=0.01)
        bx(-L / 2, L / 2, y - 0.02, y + 0.02, 0.05, Hc - 0.05, "glass")
        bx(-L / 2, L / 2, y - 0.07, y + 0.07, 0.0, 0.25, "paint_glossy_dark")
        bx(-L / 2, L / 2, y - 0.07, y + 0.07, Hc - 0.1, Hc, "metal_dark")
    bx(-L / 2 - 0.1, L / 2 + 0.1, -Wd / 2 - 0.25, Wd / 2 + 0.25, Hc, Hc + 0.25, "carbon_panel", bevel=0.03)
    if K.LOD < 2:
        for sy in (-1, 1):
            bx(-L / 2, L / 2, sy * (Wd / 2 + 0.25) - 0.01, sy * (Wd / 2 + 0.25) + 0.01, Hc + 0.05, Hc + 0.2, "emit_strip_cyan")
        for i in range(int(L / 3)):
            x = -L / 2 + 1.5 + i * 3
            bx(x - 0.6, x + 0.6, -0.15, 0.15, Hc - 0.12, Hc - 0.1, "emit_panel_white")
    if detail():
        for k in range(3):
            F.cable_sag((-L / 2, -Wd / 2 + 0.4 + k * 0.5, -1.3), (L / 2, -Wd / 2 + 0.3 + k * 0.6, -1.3), sag=0.8 + k * 0.3, r=0.03)
    return {"colliders": [K.collider_box((0, 0, -0.125), (L, Wd, 0.25)), K.collider_box((0, -Wd / 2, Hc / 2), (L, 0.12, Hc)),
                          K.collider_box((0, Wd / 2, Hc / 2), (L, 0.12, Hc)), K.collider_box((0, 0, Hc + 0.12), (L, Wd + 0.5, 0.25))],
            "span": L, "walkway": {"width": Wd - 0.24, "height": Hc}, "lights": [K.to_unity_vec((x, 0, Hc - 0.3)) for x in (-L / 4, L / 4)]}


def skybridge_catwalk(L=8.0, Wd=1.4):
    """Open steel catwalk spanning L along X: grating deck, side stringers, railings, hanging cables, LED kick strip."""
    for sy in (-1, 1):
        y = sy * Wd / 2
        bx(-L / 2, L / 2, y - 0.05 * (sy > 0) - 0.0, y + 0.05 * (sy < 0), -0.3, 0.0, "metal_painted", bevel=0.01)
        bx(-L / 2, L / 2, y - 0.04, y + 0.04, -0.3, -0.28, "metal_dark")
        if K.LOD < 2:
            n = int(L / 1.0)
            for i in range(n + 1):
                x = -L / 2 + i * L / n
                cyl(0.025, 1.1, K.seg(8), at=(x, y, 0.0), mat="metal_dark")
            tube([(-L / 2, y, 1.1), (L / 2, y, 1.1)], 0.03, K.seg(8), "metal_painted_yellow")
            tube([(-L / 2, y, 0.55), (L / 2, y, 0.55)], 0.018, K.seg(6), "metal_dark")
            bx(-L / 2, L / 2, y - 0.01, y + 0.01, 0.02, 0.05, "emit_strip_yellow")
    bx(-L / 2, L / 2, -Wd / 2 + 0.05, Wd / 2 - 0.05, -0.04, 0.0, "grating")
    if K.LOD < 2:
        for i in range(int(L / 1.0) + 1):
            x = -L / 2 + i * L / int(L / 1.0)
            bx(x - 0.03, x + 0.03, -Wd / 2, Wd / 2, -0.14, -0.04, "metal_dark")
    if detail():
        for k in range(2):
            F.cable_sag((-L / 2, -Wd / 2 + 0.2 + k * 0.9, -0.35), (L / 2, -Wd / 2 + 0.3 + k * 0.8, -0.35), sag=0.6 + k * 0.4, r=0.025)
    return {"colliders": [K.collider_box((0, 0, -0.15), (L, Wd, 0.3)), K.collider_box((0, -Wd / 2, 0.55), (L, 0.06, 1.1)),
                          K.collider_box((0, Wd / 2, 0.55), (L, 0.06, 1.1))], "span": L, "walkway": {"width": Wd}}


def catwalk_wall(L=4.0, Wd=1.2):
    """Wall-mounted maintenance catwalk module (repeat every 4 m along X): wall at local y=0 (Unity z=0) on the +Y
    side, deck sticks out toward -Y (Unity +Z), deck top at 0."""
    bx(-L / 2, L / 2, -Wd, 0.0, -0.04, 0.0, "grating")
    bx(-L / 2, L / 2, -Wd - 0.05, -Wd, -0.2, 0.02, "metal_painted")
    for x in (-L / 2 + 0.3, L / 2 - 0.3):
        beam((x, 0.0, -0.05), (x, -Wd, -0.05), 0.06, 0.12, mat="metal_dark")
        beam((x, 0.0, -1.0), (x, -Wd * 0.85, -0.12), 0.05, 0.05, mat="metal_dark")
        bx(x - 0.1, x + 0.1, -0.02, 0.0, -1.1, 0.0, "metal_dark")
    if K.LOD < 2:
        for i in range(5):
            x = -L / 2 + i * L / 4
            cyl(0.022, 1.1, K.seg(8), at=(x, -Wd, 0.0), mat="metal_dark")
        tube([(-L / 2, -Wd, 1.1), (L / 2, -Wd, 1.1)], 0.028, K.seg(8), "metal_painted_yellow")
        tube([(-L / 2, -Wd, 0.55), (L / 2, -Wd, 0.55)], 0.018, K.seg(6), "metal_dark")
    if detail():
        F.cable_sag((-L / 2, -0.1, -0.15), (L / 2, -0.1, -0.15), sag=0.25, r=0.02)
        bx(-0.2, 0.2, -0.08, 0.0, 1.6, 1.75, "metal_dark")
        bx(-0.18, 0.18, -0.085, -0.075, 1.6, 1.62, "emit_panel_warm")
    return {"colliders": [K.collider_box((0, -Wd / 2, -0.06), (L, Wd, 0.12)), K.collider_box((0, -Wd, 0.55), (L, 0.06, 1.1))],
            "lights": [K.to_unity_vec((0, -0.3, 1.5))]}


ASSETS = {
    "Building_MidRise_A": dict(fn=building, kw=dict(nx=3, nz=3, floors=5, style="Plaster", seed=11, front_ground=("shop_glass", "noodle", "shop_shutter"),
                                                   blade=("emit_neon_magenta", 3), roof=("tower", "ac", "antenna")),
                               cat="building", zones=["plaza", "rooftops"], lods=3,
                               notes="5-storey plaster block. Mass 12 x 12 m, roof 17.0 m (parapet rail 18.6). Ground floor: glazed shop, noodle bar, "
                                     "half-open shutter; upper: AC / cage / neon / double / services modules; magenta neon blade on the front-right corner; "
                                     "water tower, AC, antenna, dish. Replaces a 12 x 12 x ~17 box block (prototype P.building). Projections: front +1.3 m (blade sign), sides +0.8 m."),
    "Building_MidRise_B": dict(fn=building, kw=dict(nx=5, nz=3, floors=7, style="Concrete", seed=23, front_ground=("shop_awning", "shop_glass", "entrance", "shop_glass", "shop_shutter"),
                                                   balcony_cols=(1, 3), upper=("window_ac", "double", "cage", "pipes", "window_ac", "neon"),
                                                   billboard=("screen_ad_b", 14.0, 5.0), roof=("bulkhead", "ac", "antenna")),
                               cat="building", zones=["plaza", "rooftops"], lods=3,
                               notes="7-storey concrete slab. Mass 20 x 12 m, roof 23.8 m. Stacked balconies (columns 2 and 4), awning + glass shops and an apartment entrance at street level, "
                                     "roof LED billboard rig 14 x 5 m (screen_ad_b, 'screens' n/a: billboard face at the north roof edge facing +Z), stair bulkhead. Replaces 20 x 12-14 m blocks of ~24 m."),
    "Building_MidRise_C": dict(fn=building, kw=dict(nx=4, nz=3, floors=4, style="Brick", seed=37, front_ground=("noodle", "shop_glass", "shop_boarded", "shop_shutter"),
                                                   side_ground=("boarded", "entrance"), upper=("window_ac", "damaged", "cage", "double", "neon"), escape=6.0,
                                                   roofneon=(4, "emit_neon_cyan"), roof=("tower", "ac")),
                               cat="building", zones=["plaza"], lods=3,
                               notes="4-storey brick walk-up. Mass 16 x 12 m, roof 13.6 m. Steel fire escape on the west (Unity +X) side, rooftop neon glyph sign (4 glyphs, cyan) at the front edge, "
                                     "noodle bar / shops / boarded unit at street level. Replaces 16 x 10-12 m blocks of 12-14 m."),
    "Building_HighRise_D": dict(fn=building, kw=dict(nx=4, nz=4, floors=12, style="Panel", seed=41, ground_style="Panel",
                                                    front_ground=("shop_glass", "entrance", "shop_awning", "shop_glass"),
                                                    upper=("window_ac", "double", "neon", "cage", "pipes", "double"), balcony_cols=(0, 3),
                                                    blade=("emit_neon_cyan", 6), billboard=("screen_ad_c", 12.0, 6.0), roof=("ac", "antenna", "bulkhead")),
                                cat="building", zones=["plaza", "rooftops"], lods=3,
                                notes="12-storey corporate-residential tower, metal-panel cladding with LED seams. Mass 16 x 16 m, roof 40.8 m. Balcony columns at both ends, "
                                      "cyan neon blade (6 storeys), roof billboard (screen_ad_c 12 x 6 m), bulkhead, AC. Use as a tall block at the plaza perimeter (26-30 m prototype blocks can be swapped for it where height is free)."),
    "Skyline_Tower_A": dict(fn=skyline_tower_a, cat="skyline", zones=["plaza", "rooftops"], uv_offset=(0.0, 0.0),
                            notes="Distant stepped megatower 28.8 x 28.8 m base, 115 m roof, spire to 146 m (red beacon). Thousands of lit windows (skyline_windows_c, emissive), "
                                  "magenta/cyan LED corner fins, two 14.4 x 7.2 m ad screens (screen_ad_a/c; 'screens'). No collider. Place 150-400 m out; do not scale non-uniformly."),
    "Skyline_Tower_B": dict(fn=skyline_tower_b, cat="skyline", zones=["plaza", "rooftops"], uv_offset=(0.0, 0.0),
                            notes="Distant office slab 32 x 16 m, 80 m + 24 x 8 m roof billboard (screen_ad_b), blue LED mid band, beacons. No collider."),
    "Skyline_Tower_C": dict(fn=skyline_tower_c, cat="skyline", zones=["plaza", "rooftops"], uv_offset=(0.0, 0.0),
                            notes="Distant residential stack 38.4 x 19.2 m, 57.6 m with cantilevered upper block, 28 m pink neon blade sign, water tanks, antenna. No collider."),
    "Skyline_Twin_D": dict(fn=skyline_twin_d, cat="skyline", zones=["plaza", "rooftops"], uv_offset=(0.0, 0.0),
                           notes="Distant twin megatowers on a 72 x 33.6 m podium, towers 24 x 24 m to 152 m, spires to 178 m, three glass skybridges, LED fins + crown rings, "
                                 "two big ad screens. Hero of the far skyline (place once, 300-500 m out). No collider."),
    "Skybridge_Enclosed_12m": dict(fn=skybridge_enclosed, cat="building", zones=["plaza", "rooftops"], pivot="deck-centre",
                                   notes="Enclosed glass skybridge 12 m span (along Unity X) x 3.2 m wide, 3.0 m clear height; truss underside to -1.24 m with magenta/cyan LED, "
                                         "carbon roof with LED lips, ceiling light panels, sagging cables. Pivot = centre of the walkway floor top. Colliders: floor, walls, roof."),
    "Skybridge_Catwalk_8m": dict(fn=skybridge_catwalk, cat="building", zones=["plaza", "rooftops"], pivot="deck-centre",
                                 notes="Open steel catwalk 8 m span x 1.4 m: grating deck, stringers, railings (1.1 m) with yellow LED kick strips, hanging cables. Pivot = deck top centre."),
    "Catwalk_Wall_4m": dict(fn=catwalk_wall, cat="building", zones=["plaza", "rooftops", "metro"], pivot="wall-deck",
                            notes="Wall-mounted maintenance catwalk module 4 m x 1.2 m: wall plane at Unity z=0 (module behind it), deck toward +Z, deck top at y=0; "
                                  "repeat every 4 m. Brackets, railing, cable, wall lamp ('lights')."),
}
EOF_MARKER = None
