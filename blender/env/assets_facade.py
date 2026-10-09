"""Cyberpunk facade kit on a 4 m x 3.4 m (one storey) grid + in-place upgrades of the original Facade_* modules.

Module convention (identical to the original Facade_* so the zone code's PzKit.Building() can use either):
  * width 4.0 m along X (centred), storey height 3.4 m from z=0, pivot base-centre.
  * the module's BACK plane is Blender y=+0.15 (Unity z=-0.15); the structural wall face is y=-0.15 (Unity z=+0.15).
    PzKit places modules 0.16 m outside the building mass box face, so the back plane sits 1 cm off the mass.
  * the outer face looks toward Blender -Y = Unity +Z.
  * windows: glass plane at y=+0.04 (Unity z -0.04) so the zone code's lit-window overlay quads still sit in front.
  * half-pilasters (0.25 m) at both module edges: two adjacent modules form a 0.5 m pier with an expansion joint.
  * a floor band (spandrel ledge) at the module bottom hides the stacking seam.

New modules (Building_Facade_*) may project further (AC units, cages, balconies, awnings, signs); their notes
give the projection. Original modules (Facade_*) stay inside their 4.0 x 3.4 x 0.4 m envelope (shops 0.75 m).
"""
import math
import random

import envkit as K
from envkit import box, cyl, tube, torus, beam, extrude, lathe, detail

T_BACK, T_FACE, T_RELIEF = 0.15, -0.15, -0.25
W, H = 4.0, 3.4

STY = {
    "Concrete": dict(wall="concrete", band="concrete_dark", pil="concrete", sill="concrete_dark", head="concrete_dark", frame="metal_dark"),
    "Plaster": dict(wall="plaster", band="concrete_dark", pil="plaster", sill="concrete", head="concrete", frame="metal_dark"),
    "Brick": dict(wall="brick", band="concrete", pil="brick", sill="concrete", head="concrete", frame="metal_dark"),
    "Panel": dict(wall="metal_plate", band="metal_dark", pil="paint_glossy_dark", sill="metal_dark", head="metal_dark", frame="metal_dark",
                  led="emit_strip_cyan"),
}
NEONS = ["emit_neon_magenta", "emit_neon_cyan", "emit_neon_pink", "emit_neon_yellow", "emit_neon_blue", "emit_neon_violet"]


# ============================================================================================== helpers
def bx(x0, x1, y0, y1, z0, z1, mat, bevel=0.0, bseg=1, name="box"):
    """Box from extents (Blender coords)."""
    return box(x1 - x0, y1 - y0, z1 - z0, at=((x0 + x1) / 2, (y0 + y1) / 2, z0), mat=mat, base=True, bevel=bevel, bseg=bseg, name=name)


def wall(x0, x1, z0, z1, y0, y1, mat, holes=()):
    """Solid wall slab with rectangular holes (x0,x1,z0,z1), built from boxes (clean topology, no booleans)."""
    xs = sorted({x0, x1} | {h[0] for h in holes} | {h[1] for h in holes})
    zs = sorted({z0, z1} | {h[2] for h in holes} | {h[3] for h in holes})
    for j in range(len(zs) - 1):
        za, zb = zs[j], zs[j + 1]
        if zb - za < 1e-4:
            continue
        run = None
        for i in range(len(xs) - 1):
            xa, xb = xs[i], xs[i + 1]
            if xb - xa < 1e-4:
                continue
            cx, cz = (xa + xb) / 2, (za + zb) / 2
            inside = any(h[0] <= cx <= h[1] and h[2] <= cz <= h[3] for h in holes)
            if not inside:
                run = (run[0], xb) if run else (xa, xb)
            elif run:
                bx(run[0], run[1], y0, y1, za, zb, mat)
                run = None
        if run:
            bx(run[0], run[1], y0, y1, za, zb, mat)


def shell(style, holes=(), led=True, band=True, pil=True, relief=T_RELIEF):
    s = STY[style]
    wall(-W / 2, W / 2, 0.0, H, T_FACE, T_BACK, s["wall"], holes)
    if pil:
        for sx in (-1, 1):
            x0, x1 = sorted((sx * W / 2, sx * (W / 2 - 0.25)))
            bx(x0, x1, relief, T_FACE, 0.0, H, s["pil"], bevel=0.012)
    if band:
        bx(-W / 2 + (0.25 if pil else 0), W / 2 - (0.25 if pil else 0), relief + 0.01, T_FACE, 0.0, 0.3, s["band"], bevel=0.01)
        if K.LOD == 0:  # drip groove shadow line under the band lip
            bx(-W / 2 + 0.25, W / 2 - 0.25, relief + 0.012, T_FACE, 0.3, 0.315, s["band"])
    if style == "Panel" and led and s.get("led") and K.LOD < 2:
        # LED seam strips on the pier faces (two adjacent modules make a lit double seam)
        for sx in (-1, 1):
            x = sx * (W / 2 - 0.07)
            bx(x - 0.012, x + 0.012, relief - 0.006, relief, 0.32, H, s["led"])


def window(cx, sill, w, h, glass="glass_dark", frame="metal_dark", sill_mat="concrete_dark", head_mat="concrete_dark",
           mull=True, blind=0.0, blind_mat="metal_painted_white", grille=False, broken=False, relief=T_RELIEF, transom=0.68):
    """Window fittings inside a hole (cx-w/2..cx+w/2, sill..sill+h) of the shell. Returns the hole tuple."""
    x0, x1, z0, z1 = cx - w / 2, cx + w / 2, sill, sill + h
    f = 0.06
    if K.LOD < 2:
        bx(x0, x0 + f, -0.02, 0.06, z0, z1, frame, bevel=0.006)
        bx(x1 - f, x1, -0.02, 0.06, z0, z1, frame, bevel=0.006)
        bx(x0 + f, x1 - f, -0.02, 0.06, z0, z0 + f, frame, bevel=0.006)
        bx(x0 + f, x1 - f, -0.02, 0.06, z1 - f, z1, frame, bevel=0.006)
        if mull:
            bx(cx - 0.025, cx + 0.025, -0.01, 0.055, z0 + f, z1 - f, frame, bevel=0.004)
            if transom:
                zt = z0 + h * transom
                bx(x0 + f, x1 - f, -0.01, 0.055, zt - 0.025, zt + 0.025, frame, bevel=0.004)
    bx(x0 + f, x1 - f, 0.034, 0.046, z0 + f, z1 - f, glass)
    if blind > 0 and K.LOD == 0 and not broken:
        zb = z1 - f - (h - 2 * f) * blind
        bx(x0 + f, x1 - f, 0.07, 0.074, zb, z1 - f, blind_mat)
        n = int((z1 - f - zb) / 0.05)
        for i in range(n):
            z = zb + 0.025 + i * 0.05
            bx(x0 + f + 0.01, x1 - f - 0.01, 0.06, 0.07, z - 0.008, z + 0.008, blind_mat)
    # precast sill with a drip edge, projecting to the relief plane
    bx(x0 - 0.1, x1 + 0.1, relief, -0.02, z0 - 0.07, z0, sill_mat, bevel=0.008)
    if K.LOD == 0:
        bx(x0 - 0.08, x1 + 0.08, relief + 0.01, relief + 0.03, z0 - 0.085, z0 - 0.07, sill_mat)
    # lintel / head band
    bx(x0 - 0.1, x1 + 0.1, relief + 0.05, T_FACE, z1, z1 + 0.16, head_mat, bevel=0.006)
    if grille and K.LOD == 0:
        # security grille set in the reveal (round bars + flat rails)
        n = int(w / 0.12)
        for i in range(1, n):
            x = x0 + i * w / n
            cyl(0.008, h - 0.02, 6, at=(x, -0.12, z0 + 0.01), mat="metal_dark")
        for z in (z0 + 0.12, z0 + h * 0.5, z1 - 0.12):
            bx(x0, x1, -0.13, -0.11, z - 0.012, z + 0.012, "metal_dark")
    if broken and K.LOD == 0:
        rnd = random.Random(int(cx * 100 + sill * 10))
        for i in range(5):
            sx = x0 + f + rnd.uniform(0.0, w - 2 * f)
            ez = z0 + f if i % 2 else z1 - f
            pts = [(sx - 0.08, ez), (sx + 0.09, ez), (sx + rnd.uniform(-0.05, 0.05), ez + (rnd.uniform(0.12, 0.35) if i % 2 else -rnd.uniform(0.12, 0.35)))]
            extrude([(p[0], p[1]) for p in pts], 0.006, plane="XZ", mat="glass").move(0, 0.04, 0)
    return (x0, x1, z0, z1)


# ---------------------------------------------------------------------------------------------- props on facades
def ac_unit(cx, z0, yw=T_FACE, w=0.8, d=0.3, h=0.56, led=True, seed=0):
    """Wall-hung AC condenser on brackets with fan grille, louvres, pipes and a drip line. Back at y=yw."""
    rnd = random.Random(seed)
    yb = yw - 0.05
    y0 = yb - d
    bx(cx - w / 2, cx + w / 2, y0, yb, z0, z0 + h, "metal_painted_white", bevel=0.014, bseg=2 if K.LOD == 0 else 1)
    fx, fz, r = cx - w * 0.14, z0 + h / 2, h * 0.38
    cyl(r, 0.012, K.seg(28), at=(fx, y0 - 0.004, fz), axis="Y", mat="black")
    if K.LOD < 2:
        for rr in (r * 0.98, r * 0.66, r * 0.34):
            torus(rr, 0.006, n_major=K.seg(24, 8), n_minor=4, mat="metal_dark").rot(x=90).move(fx, y0 - 0.008, fz)
        for a in range(0, 180, 45):
            bx(-r, r, -0.004, 0.004, -0.006, 0.006, "metal_dark").rot(y=a).move(fx, y0 - 0.008, fz)
        # louvres on the right
        for i in range(7):
            z = z0 + 0.08 + i * (h - 0.16) / 6
            bx(cx + w * 0.16, cx + w / 2 - 0.05, y0 - 0.012, y0 + 0.01, z - 0.01, z + 0.01, "metal_painted_white").rot_about((cx, y0, z), x=-25)
    # brackets
    for sx in (-1, 1):
        x = cx + sx * (w / 2 - 0.08)
        bx(x - 0.02, x + 0.02, y0 - 0.02, yw, z0 - 0.04, z0, "metal_dark")
        if K.LOD == 0:
            beam((x, yw, z0 - 0.3), (x, y0 + 0.03, z0 - 0.02), 0.03, 0.03, mat="metal_dark")
    if detail():
        # refrigerant lines into the wall, insulated, and a drip pipe running down
        py = yb + 0.02
        tube([(cx + w / 2 - 0.08, yb - 0.08, z0 + 0.12), (cx + w / 2 + 0.06, yb - 0.08, z0 + 0.12), (cx + w / 2 + 0.06, py, z0 + 0.12),
              (cx + w / 2 + 0.06, py, z0 + 0.45), (cx + w / 2 + 0.06, yw, z0 + 0.45)], 0.016, 6, "rubber")
        tube([(cx - w / 2 + 0.1, y0 + 0.05, z0 + 0.01), (cx - w / 2 + 0.1, y0 + 0.05, max(0.02, z0 - 0.25 - rnd.uniform(0, 0.4)))], 0.008, 5, "plastic_dark")
        if led:
            bx(cx + w / 2 - 0.07, cx + w / 2 - 0.05, y0 - 0.005, y0, z0 + h - 0.08, z0 + h - 0.06, "emit_green" if rnd.random() < 0.6 else "emit_red")


def glyph_segments(rng):
    """Invented glyph as line segments in 0..1 (same radical grammar as matdefs_hd.glyph)."""
    segs = []
    top = rng.uniform(0.8, 0.92)
    segs.append(((rng.uniform(0.08, 0.2), top), (rng.uniform(0.8, 0.92), top)))
    for x in sorted(rng.sample([0.22, 0.38, 0.5, 0.62, 0.78], 2)):
        segs.append(((x, rng.uniform(0.05, 0.3)), (x, rng.uniform(0.6, top))))
    if rng.random() < 0.55:
        x0, x1 = rng.uniform(0.15, 0.35), rng.uniform(0.65, 0.85)
        y0, y1 = rng.uniform(0.1, 0.3), rng.uniform(0.45, 0.62)
        segs += [((x0, y0), (x1, y0)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))]
    else:
        segs.append(((rng.uniform(0.1, 0.3), rng.uniform(0.1, 0.3)), (rng.uniform(0.55, 0.9), rng.uniform(0.45, 0.7))))
        segs.append(((rng.uniform(0.55, 0.9), rng.uniform(0.05, 0.25)), (rng.uniform(0.15, 0.45), rng.uniform(0.5, 0.7))))
    mid = rng.uniform(0.38, 0.6)
    segs.append(((rng.uniform(0.05, 0.25), mid), (rng.uniform(0.7, 0.95), mid)))
    x, y = rng.uniform(0.15, 0.85), rng.uniform(0.15, 0.85)
    segs.append(((x, y), (x + rng.uniform(-0.15, 0.15), y - rng.uniform(0.08, 0.15))))
    return segs


def neon_glyphs(x0, z0, cw, ch, count, yw, mat, seed, vertical=True, backing="metal_dark", r=0.011):
    """Neon tube glyph sign mounted on a slim backing rail (standoffs, transformer box). Glyph cells cw x ch.
    Tubes sit 6 cm proud of the backing; backing back face at y=yw."""
    rng = random.Random(seed)
    yb = yw - 0.04
    yt = yb - 0.06
    if vertical:
        bw, bh = cw + 0.12, count * ch + 0.12
        bx(x0 - 0.06, x0 + cw + 0.06, yb, yw, z0 - 0.06, z0 + count * ch + 0.06, backing, bevel=0.01)
    else:
        bw, bh = count * cw + 0.12, ch + 0.12
        bx(x0 - 0.06, x0 + count * cw + 0.06, yb, yw, z0 - 0.06, z0 + ch + 0.06, backing, bevel=0.01)
    for i in range(count):
        gx = x0 + (0 if vertical else i * cw)
        gz = z0 + ((count - 1 - i) * ch if vertical else 0)
        for (a, b) in glyph_segments(rng):
            pa = (gx + 0.1 * cw + a[0] * cw * 0.8, yt, gz + 0.1 * ch + a[1] * ch * 0.8)
            pb = (gx + 0.1 * cw + b[0] * cw * 0.8, yt, gz + 0.1 * ch + b[1] * ch * 0.8)
            if math.dist(pa, pb) < 0.02:
                continue
            tube([pa, pb], r, K.seg(6, 4), mat, caps=K.LOD == 0)
            if detail():
                for p in (pa, pb):
                    cyl(0.004, 0.06, 4, at=(p[0], yt, p[2]), axis="Y", mat="metal_bare")
    if detail():
        bx(x0 + 0.02, x0 + 0.2, yb - 0.08, yb, z0 - 0.3, z0 - 0.12, "metal_dark", bevel=0.008)  # transformer
        tube([(x0 + 0.11, yb - 0.04, z0 - 0.12), (x0 + 0.11, yb - 0.04, z0 - 0.05)], 0.008, 5, "rubber")
    return {"center": [x0 + bw / 2 - 0.06, (z0 + bh / 2 - 0.06)]}


def conduit(points, r=0.022, mat="metal_dark", clips=True):
    tube(points, r, K.seg(8, 4), mat)
    if clips and detail():
        for (a, b) in zip(points[:-1], points[1:]):
            L = math.dist(a, b)
            n = int(L / 0.6)
            for i in range(1, n + 1):
                t = i / (n + 1)
                p = [a[k] + (b[k] - a[k]) * t for k in range(3)]
                cyl(r * 1.6, 0.03, 6, at=(p[0], p[1], p[2] - 0.015), mat="metal_dark")


def cable_sag(a, b, sag=0.15, r=0.01, n=10, mat="rubber"):
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t - sag * 4 * t * (1 - t)))
    tube(pts, r, K.seg(6, 4), mat)


def downpipe(x, z0, z1, yw=T_FACE, r=0.05, mat="metal_dark"):
    y = yw - r - 0.03
    cyl(r, z1 - z0, K.seg(12), at=(x, y, z0), mat=mat)
    if detail():
        for z in (z0 + 0.3, (z0 + z1) / 2, z1 - 0.3):
            cyl(r + 0.012, 0.04, K.seg(12), at=(x, y, z), mat="metal_dark")
            bx(x - 0.015, x + 0.015, y + r * 0.6, yw, z, z + 0.04, "metal_dark")


def col_box(x0, x1, y0, y1, z0, z1):
    return K.collider_box(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0))


def wall_collider():
    return [K.collider_box((0, 0, H / 2), (W, 0.3, H))]


# ============================================================================================== original modules (in place)
LEGACY = {
    # name-style: (wall, band/head, sill, pilaster)
    "plaster": ("plaster", "concrete_dark", "concrete", "plaster"),
    "brick": ("brick", "concrete_dark", "concrete", "brick"),
    "concrete": ("concrete", "concrete_dark", "concrete_dark", "concrete"),
}


def legacy_facade(style="plaster", kind="window", lit=False, broken=False, seed=1):
    """Upgraded Facade_* module, same envelope (4.0 x 3.4 x 0.4 m, shops 0.75 m deep), opening and glass plane."""
    wm, bm, sm, pm = LEGACY[style]
    STY["_legacy"] = dict(wall=wm, band=bm, pil=pm, sill=sm, head=bm, frame="metal_dark")
    rnd = random.Random(seed)
    meta = {"colliders": wall_collider()}
    if kind == "window":
        hole = (-0.8, 0.8, 0.9, 2.5)
        shell("_legacy", [hole])
        glass = "black" if broken else ("window_lit_warm" if lit else "glass_dark")
        window(0.0, 0.9, 1.6, 1.6, glass=glass, sill_mat=sm, head_mat=bm, blind=0.0 if (lit or broken) else 0.35 + rnd.random() * 0.3,
               grille=(style == "plaster" and not lit), broken=broken)
        if style == "concrete":
            # formwork tie-hole rhythm + a recessed reveal panel band (cast-in-place look)
            if detail():
                for x in (-1.45, 1.45):
                    for z in (0.75, 1.65, 2.55):
                        cyl(0.012, 0.01, 6, at=(x, T_FACE - 0.004, z), axis="Y", mat="concrete_dark")
        if detail():
            conduit([(1.55, T_FACE - 0.03, 0.32), (1.55, T_FACE - 0.03, H)], r=0.018)
            if style == "brick":
                # soldier-course header and a stone keystone
                bx(-0.35 * 0 - 0.12, 0.12, T_RELIEF + 0.05, T_FACE, 2.5, 2.72, "concrete", bevel=0.006)
        meta["opening"] = {"width": 1.6, "height": 1.6, "sill": 0.9, "glassZ": -0.04}
    elif kind == "plain":
        shell("_legacy", [])
        # recessed panel field, vent grille and services
        bx(-1.5, 1.5, T_FACE - 0.01, T_FACE, 0.6, 3.0, bm)
        bx(-1.45, 1.45, T_FACE - 0.012, T_FACE - 0.008, 0.65, 2.95, wm)
        if detail():
            bx(0.6, 1.1, T_FACE - 0.05, T_FACE, 2.2, 2.6, bm, bevel=0.006)
            for i in range(6):
                z = 2.24 + i * 0.06
                bx(0.63, 1.07, T_FACE - 0.07, T_FACE - 0.045, z, z + 0.02, bm)
            conduit([(-1.55, T_FACE - 0.03, 0.32), (-1.55, T_FACE - 0.03, 2.0), (-0.4, T_FACE - 0.03, 2.0), (-0.4, T_FACE - 0.03, H)], r=0.018)
            bx(-1.75, -1.35, T_FACE - 0.08, T_FACE, 1.4, 1.9, bm, bevel=0.008)
    elif kind == "shop":
        hole = (-1.6, 1.6, 0.0, 2.75)
        shell("_legacy", [hole], band=False)
        # roller shutter: ribbed slats 0..2.0, guide channels, bottom bar with handle
        sm_ = "metal_rusted" if broken else "metal_painted"
        n = 25
        for i in range(n):
            z = i * 0.08
            off = 0.0 if not broken else (0.03 * math.sin(i * 1.7) if i > 18 else 0.0)
            if broken and i in (21, 23):
                continue
            bx(-1.55, 1.55, 0.0 + off, 0.04 + off, z, z + 0.075, sm_, bevel=0.01 if K.LOD == 0 else 0)
        bx(-1.58, 1.58, -0.01, 0.06, 0.0, 0.06, "metal_dark", bevel=0.006)
        for sx in (-1, 1):
            bx(sx * 1.6 - 0.05, sx * 1.6 + 0.05, -0.03, 0.08, 0.0, 2.75, "metal_dark", bevel=0.006)
        if detail():
            for x in (-0.6, 0.6):
                bx(x - 0.08, x + 0.08, -0.035, -0.01, 0.02, 0.045, "metal_dark")
            bx(-0.03, 0.03, -0.05, -0.01, 0.0, 0.08, "metal_bare")
        # transom glazing 2.0..2.75 (glass at Unity z -0.06) with mullions
        bx(-1.55, 1.55, -0.02, 0.1, 1.95, 2.05, "metal_dark", bevel=0.006)
        bx(-1.55, 1.55, 0.054, 0.066, 2.05, 2.72, "black" if broken else "glass_dark")
        for x in (-0.53, 0.53):
            bx(x - 0.025, x + 0.025, 0.0, 0.08, 2.05, 2.72, "metal_dark")
        bx(-1.6, 1.6, -0.02, 0.08, 2.72, 2.78, "metal_dark")
        # fascia + canopy box projecting to y=-0.6 (z 2.85..3.2), underside downlights / LED lip
        cm = "metal_rusted" if broken else "metal_dark"
        can = bx(-1.8, 1.8, -0.6, T_FACE, 2.85, 3.2, cm, bevel=0.02)
        if broken:
            can.rot_about((0, -0.375, 3.025), y=2.5)  # sagging on one side (stays inside the 0.75 m envelope)
        bx(-2.0, 2.0, T_RELIEF + 0.01, T_FACE, 3.2, 3.4, bm, bevel=0.01)
        if detail() and not broken:
            bx(-1.75, 1.75, -0.585, -0.57, 2.86, 2.88, "corrugated")
            for x in (-1.1, 0.0, 1.1):
                cyl(0.05, 0.012, 12, at=(x, -0.35, 2.838), mat="metal_bare")
        if detail() and broken:
            cable_sag((-1.5, -0.55, 2.85), (-0.6, -0.5, 2.85), sag=0.5)
            cable_sag((0.4, -0.55, 2.85), (1.2, -0.45, 2.85), sag=0.35)
        meta["transom"] = {"width": 3.2, "height": 0.75, "y0": 2.0, "glassZ": -0.06}
    return meta


ASSETS = {
    "Facade_Plaster_Window": dict(fn=legacy_facade, kw={"style": "plaster", "seed": 1}, cat="structure", zones=["plaza", "rooftops"],
                                  notes="One-storey facade 4 x 3.4 m: 1.6 x 1.6 window (sill 0.9) in a deep reveal with frame, mullion/transom, blinds, "
                                        "security grille, precast sill + head, half-pilasters, floor band, conduit. Outer face +Z."),
    "Facade_Plaster_Window_Lit": dict(fn=legacy_facade, kw={"style": "plaster", "lit": True, "seed": 2}, cat="structure", zones=["plaza", "rooftops"],
                                      notes="Lit-window variant (window_lit_warm)."),
    "Facade_Plaster_Plain": dict(fn=legacy_facade, kw={"style": "plaster", "kind": "plain"}, cat="structure", zones=["plaza", "rooftops"],
                                 notes="Blank module: recessed panel field, louvred vent, conduit run, service box."),
    "Facade_Brick_Window": dict(fn=legacy_facade, kw={"style": "brick", "seed": 3}, cat="structure", zones=["plaza", "rooftops"],
                                notes="Brick facade, window with precast sill/head, keystone, conduit."),
    "Facade_Brick_Window_Broken": dict(fn=legacy_facade, kw={"style": "brick", "broken": True, "seed": 4}, cat="structure", zones=["plaza"],
                                       notes="Brick facade, smashed window (black void, glass shards)."),
    "Facade_Concrete_Window": dict(fn=legacy_facade, kw={"style": "concrete", "seed": 5}, cat="structure", zones=["plaza", "rooftops"],
                                   notes="Cast-concrete facade with window, tie holes, blinds."),
    "Facade_Shop": dict(fn=legacy_facade, kw={"style": "plaster", "kind": "shop"}, cat="structure", zones=["plaza"],
                        notes="Ground-floor shop front: ribbed roller shutter (0-2 m) in guide channels, transom glazing 3.2 x 0.75 at 2.0 m "
                              "(glass Unity z -0.06), fascia/canopy box projecting 0.6 m with downlights."),
    "Facade_Shop_Broken": dict(fn=legacy_facade, kw={"style": "concrete", "kind": "shop", "broken": True}, cat="structure", zones=["plaza"],
                               notes="Looted shop front: rusted shutter with missing/buckled slats, smashed transom, sagging canopy, hanging cables."),
}
for _n, _s in ASSETS.items():
    _s["uv_offset"] = (0.0, 0.0)  # textures continue across neighbouring modules


# ============================================================================================== new cyberpunk modules
def _upper(style="Concrete", kind="window_ac", seed=1):
    """Upper-storey cyberpunk module. kinds: window_ac, cage, neon, balcony, double, pipes, damaged."""
    s = STY[style]
    rnd = random.Random(seed * 31 + len(style))
    meta = {"colliders": wall_collider()}
    lights = []
    glass = "glass_dark"
    if kind in ("window_ac", "cage", "neon", "damaged"):
        wx = -0.35 if kind in ("window_ac", "neon") else 0.0
        hole = window_hole = (wx - 0.8, wx + 0.8, 0.9, 2.5)
        shell(style, [hole])
        lit = rnd.random() < 0.35 and kind != "damaged"
        g_ = "black" if kind == "damaged" else (("window_lit_warm" if rnd.random() < 0.6 else "window_lit_cool") if lit else glass)
        window(wx, 0.9, 1.6, 1.6, glass=g_, frame=s["frame"], sill_mat=s["sill"], head_mat=s["head"],
               blind=0.0 if lit or kind == "damaged" else rnd.uniform(0.2, 0.6), broken=(kind == "damaged"))
        if kind == "window_ac":
            ac_unit(1.25, 1.05, w=0.72, d=0.3, h=0.52, seed=seed)
            if detail():
                cable_sag((-1.95, T_FACE - 0.05, 3.25), (1.95, T_FACE - 0.08, 3.1), sag=0.12, r=0.012)
                cable_sag((-1.95, T_FACE - 0.07, 3.18), (1.95, T_FACE - 0.05, 3.22), sag=0.2, r=0.009)
            meta["projection"] = 0.41
        elif kind == "cage":
            # protruding window cage (bars + mesh floor) with a few pots / boxes inside
            cy0, cy1 = -0.62, T_RELIEF
            x0, x1, z0, z1 = wx - 0.95, wx + 0.95, 0.82, 2.6
            if K.LOD < 2:
                for (a, b) in (((x0, cy0, z0), (x1, cy0, z0)), ((x0, cy0, z1), (x1, cy0, z1)), ((x0, cy0, z0), (x0, cy0, z1)), ((x1, cy0, z0), (x1, cy0, z1)),
                               ((x0, cy0, z0), (x0, cy1, z0)), ((x1, cy0, z0), (x1, cy1, z0)), ((x0, cy0, z1), (x0, cy1, z1)), ((x1, cy0, z1), (x1, cy1, z1))):
                    beam(a, b, 0.03, 0.03, mat="metal_dark")
                bx(x0, x1, cy0, cy1, z0 - 0.02, z0 + 0.01, "grating")
                if detail():
                    for i in range(1, 16):
                        x = x0 + i * (x1 - x0) / 16
                        cyl(0.007, z1 - z0, 5, at=(x, cy0, z0), mat="metal_dark")
                    for i in range(1, 4):
                        y = cy0 + i * (cy1 - cy0) / 4
                        for xx in (x0, x1):
                            cyl(0.007, z1 - z0, 5, at=(xx, y, z0), mat="metal_dark")
                    for z in (z0 + 0.6, z0 + 1.2):
                        beam((x0, cy0, z), (x1, cy0, z), 0.012, 0.012, mat="metal_dark")
                    cyl(0.1, 0.18, 10, at=(wx - 0.5, -0.45, z0 + 0.01), r2=0.12, mat="plastic_orange")
                    bx(wx + 0.2, wx + 0.6, -0.55, -0.3, z0 + 0.01, z0 + 0.3, "wood", bevel=0.01)
            meta["projection"] = 0.62
        elif kind == "neon":
            col = NEONS[seed % len(NEONS)]
            neon_glyphs(0.75, 0.75, 0.42, 0.5, 4, T_FACE, col, seed)
            lights.append(K.to_unity_vec((1.0, -0.4, 1.75)))
            meta["glowMaterial"] = col
            meta["projection"] = 0.17
        elif kind == "damaged":
            if detail():
                # boards over half the window, scorch-dark lintel, hanging cable
                for i, z in enumerate((1.2, 1.55, 2.0)):
                    b = bx(-0.95, 0.95, -0.2, -0.17, z, z + 0.22, "wood", bevel=0.006)
                    b.rot_about((0, -0.18, z + 0.11), y=rnd.uniform(-8, 8))
                    for x in (-0.8, 0.8):
                        cyl(0.006, 0.03, 5, at=(x, -0.2, z + 0.11), axis="Y", mat="metal_bare")
                cable_sag((-1.7, T_FACE - 0.05, 3.3), (-1.2, -0.3, 1.2), sag=0.1, r=0.012)
            meta["projection"] = 0.25
    elif kind == "double":
        holes = [(-1.45, -0.35, 0.9, 2.6), (0.35, 1.45, 0.9, 2.6)]
        shell(style, holes)
        for i, (x0, x1, z0, z1) in enumerate(holes):
            lit = rnd.random() < 0.3
            window((x0 + x1) / 2, z0, x1 - x0, z1 - z0, glass=("window_lit_cool" if i else "window_lit_warm") if lit else glass, frame=s["frame"],
                   sill_mat=s["sill"], head_mat=s["head"], mull=False, blind=0.0 if lit else rnd.uniform(0.2, 0.7))
        if detail():
            downpipe(0.0, 0.0, H, r=0.045)
            ac_unit(-0.9, 0.35, w=0.6, d=0.26, h=0.42, seed=seed + 5)
        meta["projection"] = 0.37
    elif kind == "balcony":
        door = (-1.45, 0.25, 0.2, 2.5)
        win = (0.6, 1.5, 1.0, 2.3)
        shell(style, [door, win], band=False)
        window(-0.6, 0.2, 1.7, 2.3, glass=glass, frame=s["frame"], sill_mat=s["band"], head_mat=s["head"], blind=rnd.uniform(0.0, 0.5), transom=0.82)
        window(1.05, 1.0, 0.9, 1.3, glass="window_lit_warm" if rnd.random() < 0.4 else glass, frame=s["frame"], sill_mat=s["sill"], head_mat=s["head"], mull=False)
        # cantilever slab with up-stand and LED soffit strip
        yf = -1.25
        bx(-1.9, 1.9, yf, T_FACE, 0.0, 0.2, s["band"], bevel=0.015)
        bx(-1.9, 1.9, yf, yf + 0.12, 0.2, 0.32, s["band"], bevel=0.01)
        if K.LOD < 2:
            bx(-1.85, 1.85, yf + 0.03, yf + 0.06, -0.012, 0.0, NEON_STRIP[seed % len(NEON_STRIP)])
            # railing: posts, top rail, perforated infill panels
            posts = [-1.85, -0.62, 0.62, 1.85]
            for x in posts:
                bx(x - 0.025, x + 0.025, yf + 0.03, yf + 0.08, 0.32, 1.15, "metal_dark", bevel=0.005)
            tube([(-1.88, yf + 0.055, 1.15), (1.88, yf + 0.055, 1.15)], 0.025, K.seg(8), "metal_dark")
            for sx in (-1, 1):
                tube([(sx * 1.88, yf + 0.055, 1.15), (sx * 1.88, T_FACE - 0.02, 1.15)], 0.025, K.seg(8), "metal_dark")
                bx(sx * 1.88 - 0.01, sx * 1.88 + 0.01, yf + 0.08, T_FACE - 0.02, 0.32, 1.1, "grating")
            for a, b in zip(posts[:-1], posts[1:]):
                bx(a + 0.03, b - 0.03, yf + 0.045, yf + 0.065, 0.36, 1.08, "grating")
        if detail():
            # clutter: plant, chair, crate, laundry line with cloths, wall AC + wall lamp
            cyl(0.13, 0.32, 12, at=(-1.55, -1.0, 0.32), r2=0.16, mat="concrete_dark")
            for k in range(5):
                a = k * 1.2566
                tube([(-1.55, -1.0, 0.6), (-1.55 + math.cos(a) * 0.22, -1.0 + math.sin(a) * 0.22, 0.95 + (k % 2) * 0.15)], 0.01, 4, "wood")
            bx(1.2, 1.6, -1.05, -0.65, 0.32, 0.62, "metal_painted_green", bevel=0.01)
            bx(1.25, 1.55, -1.0, -0.7, 0.62, 0.86, "wood", bevel=0.01)
            tube([(-1.85, yf + 0.055, 2.3), (1.85, yf + 0.055, 2.25)], 0.004, 4, "rubber")
            for i, x in enumerate((-1.2, -0.7, 0.4, 0.9)):
                c = bx(x - 0.2, x + 0.2, yf + 0.05, yf + 0.06, 1.75 + (i % 2) * 0.1, 2.28, "tarp" if i % 2 else "tarp_blue")
                c.rot_about((x, yf + 0.055, 2.28), z=rnd.uniform(-6, 6))
            ac_unit(1.05, 2.45, w=0.62, d=0.24, h=0.42, seed=seed + 9)
            bx(-1.82, -1.66, T_FACE - 0.06, T_FACE, 2.2, 2.32, "metal_dark", bevel=0.006)
            bx(-1.8, -1.68, T_FACE - 0.065, T_FACE - 0.055, 2.19, 2.21, "emit_panel_warm")
            lights.append(K.to_unity_vec((-1.74, -0.4, 2.1)))
            downpipe(1.88, 0.32, H, r=0.04)
        meta["colliders"] = wall_collider() + [col_box(-1.9, 1.9, yf, T_FACE, 0.0, 0.32), col_box(-1.9, 1.9, yf, yf + 0.1, 0.32, 1.15)]
        meta["projection"] = 1.25
        meta["walkable"] = "balcony slab top at y=0.32 (Unity local), 3.8 x 1.1 m"
    elif kind == "pipes":
        shell(style, [])
        if K.LOD < 2:
            downpipe(-1.45, 0.0, H, r=0.06)
            yp = T_FACE - 0.12
            for z, r in ((2.75, 0.07), (2.95, 0.045)):
                cyl(r, W, K.seg(12), at=(-W / 2, yp + (0.07 - r), z), axis="X", mat="metal_rusted" if r > 0.06 else "metal_dark")
            if detail():
                for x in (-1.2, 0.0, 1.2):
                    bx(x - 0.03, x + 0.03, yp - 0.02, T_FACE, 2.62, 3.05, "metal_dark")
                # electrical cabinet with conduit and status LEDs
                bx(0.3, 1.0, T_FACE - 0.22, T_FACE, 1.0, 1.95, "metal_painted", bevel=0.01)
                bx(0.32, 0.98, T_FACE - 0.225, T_FACE - 0.215, 1.02, 1.93, "metal_painted")
                for i, m in enumerate(("emit_green", "emit_amber", "emit_green")):
                    bx(0.4 + i * 0.06, 0.43 + i * 0.06, T_FACE - 0.23, T_FACE - 0.22, 1.82, 1.85, m)
                conduit([(0.65, T_FACE - 0.04, 1.95), (0.65, T_FACE - 0.04, 2.6)], r=0.025)
                conduit([(0.5, T_FACE - 0.04, 1.0), (0.5, T_FACE - 0.04, 0.3)], r=0.02)
                # wall vent and a cable bundle
                bx(-0.9, -0.3, T_FACE - 0.06, T_FACE, 1.4, 1.9, "metal_dark", bevel=0.008)
                for i in range(7):
                    z = 1.44 + i * 0.065
                    bx(-0.87, -0.33, T_FACE - 0.08, T_FACE - 0.05, z, z + 0.022, "metal_dark").rot_about((-0.6, T_FACE - 0.06, z), x=-30)
                for k in range(3):
                    cable_sag((-1.95, T_FACE - 0.05 - k * 0.02, 2.45 - k * 0.04), (1.95, T_FACE - 0.05 - k * 0.02, 2.4 + k * 0.03), sag=0.18 + k * 0.06, r=0.011)
        meta["projection"] = 0.3
    meta["colliders"] = meta.get("colliders", wall_collider())
    if lights:
        meta["lights"] = lights
    return meta


NEON_STRIP = ["emit_strip_magenta", "emit_strip_cyan", "emit_strip_pink", "emit_strip_blue", "emit_strip_yellow", "emit_strip_violet"]


def _ground(kind="shop_glass", seed=1, style="Concrete"):
    """Ground-floor cyberpunk modules (one storey, 3.4 m). kinds: shop_glass, shop_shutter, shop_awning, noodle, entrance, boarded."""
    s = STY[style]
    rnd = random.Random(seed * 17)
    meta = {"colliders": wall_collider()}
    lights, screens = [], []
    neon = NEONS[seed % len(NEONS)]
    strip = NEON_STRIP[seed % len(NEON_STRIP)]
    if kind in ("shop_glass", "shop_awning"):
        hole = (-1.65, 1.65, 0.0, 2.7)
        shell(style, [hole], band=False)
        # aluminium storefront: door left, two fixed panes, kick plate, transom
        fr = "metal_dark"
        for x in (-1.65, -0.75, 0.45, 1.65):
            bx(x - 0.035, x + 0.035, -0.06, 0.02, 0.0, 2.7, fr, bevel=0.005)
        bx(-1.65, 1.65, -0.06, 0.02, 2.2, 2.27, fr)
        bx(-1.65, 1.65, -0.06, 0.02, 2.63, 2.7, fr)
        bx(-0.75, 1.65, -0.05, 0.01, 0.0, 0.25, "metal_bare")
        bx(-1.62, -0.78, -0.03, -0.018, 0.02, 2.18, "glass")
        bx(-0.72, 1.62, -0.03, -0.018, 0.25, 2.18, "glass")
        bx(-1.62, 1.62, -0.03, -0.018, 2.27, 2.63, "glass")
        if detail():
            bx(-0.88, -0.84, -0.1, -0.06, 0.9, 1.4, "chrome_scratched", bevel=0.01)
        # shallow lit interior: back glow panel + shelves + ceiling strip (parallax depth 0.15 m)
        bx(-1.6, 1.6, 0.13, 0.145, 0.0, 2.65, "window_lit_warm" if seed % 2 else "window_lit_cool")
        if K.LOD < 2:
            for z in (0.7, 1.25, 1.8):
                bx(-0.7, 1.55, 0.02, 0.13, z, z + 0.03, "metal_dark")
                if detail():
                    for i in range(9):
                        x = -0.6 + i * 0.24 + rnd.uniform(-0.03, 0.03)
                        hh = rnd.uniform(0.12, 0.3)
                        bx(x - 0.07, x + 0.07, 0.04, 0.11, z + 0.03, z + 0.03 + hh, rnd.choice(["plastic_orange", "metal_painted_white", "plastic_dark", "paint_glossy_red"]))
            bx(-1.6, 1.6, 0.0, 0.1, 2.6, 2.63, "emit_white")
        # fascia sign box with an LED ad face + neon edge
        bx(-1.85, 1.85, -0.42, T_FACE, 2.78, 3.32, "metal_dark", bevel=0.02)
        bx(-1.75, 1.75, -0.425, -0.415, 2.84, 3.26, ["screen_ad_a", "screen_ad_b", "screen_ad_c"][seed % 3])
        screens.append({"center": K.to_unity_vec((0, -0.425, 3.05)), "size": [3.5, 0.42], "normal": [0, 0, 1], "material": ["screen_ad_a", "screen_ad_b", "screen_ad_c"][seed % 3]})
        if K.LOD < 2:
            bx(-1.85, 1.85, -0.44, -0.42, 2.77, 2.79, strip)
            bx(-1.85, 1.85, -0.44, -0.42, 3.31, 3.33, strip)
        lights.append(K.to_unity_vec((0, -1.0, 2.6)))
        if kind == "shop_awning":
            # projecting steel awning with tarp skin, LED lip, and a hanging neon blade
            yf = -1.6
            for sx in (-1, 1):
                beam((sx * 1.8, T_FACE, 2.72), (sx * 1.8, yf, 2.45), 0.06, 0.08, mat="metal_dark")
                if K.LOD == 0:
                    beam((sx * 1.8, T_FACE, 2.2), (sx * 1.8, yf + 0.3, 2.47), 0.03, 0.03, mat="metal_dark")
            aw = bx(-1.9, 1.9, yf, T_FACE, 2.5, 2.53, "tarp_blue" if seed % 2 else "tarp")
            aw.rot_about((0, T_FACE, 2.72), x=-8.0)
            bx(-1.9, 1.9, yf - 0.02, yf + 0.02, 2.36, 2.46, "metal_dark")
            bx(-1.9, 1.9, yf - 0.03, yf - 0.02, 2.37, 2.4, strip)
            if detail():
                # hanging blade sign under the awning
                bx(1.2, 1.24, yf + 0.3, yf + 0.34, 1.9, 2.45, "metal_dark")
                bx(1.0, 1.44, yf + 0.25, yf + 0.39, 1.2, 1.9, "metal_dark", bevel=0.01)
                neon_glyphs(1.06, 1.27, 0.32, 0.31, 2, yf + 0.25, neon, seed + 3, backing="black", r=0.008)
            meta["colliders"] = wall_collider()
            meta["projection"] = 1.62
        else:
            meta["projection"] = 0.44
    elif kind == "shop_shutter":
        hole = (-1.65, 1.65, 0.0, 2.75)
        shell(style, [hole], band=False)
        zb = 1.05 + rnd.uniform(0.0, 0.4)  # shutter half up: warm light spills under it
        n = int((2.75 - zb) / 0.08) if K.LOD < 2 else 0
        if K.LOD >= 2:
            bx(-1.6, 1.6, 0.0, 0.04, zb, 2.75, "metal_painted")
        for i in range(n):
            z = zb + i * 0.08
            bx(-1.6, 1.6, 0.0, 0.04, z, z + 0.075, ["metal_painted", "metal_painted_green", "metal_painted_red", "metal_dark"][seed % 4],
               bevel=0.01 if K.LOD == 0 else 0)
        bx(-1.62, 1.62, -0.01, 0.06, zb - 0.06, zb, "metal_dark", bevel=0.006)
        for sx in (-1, 1):
            bx(sx * 1.65 - 0.05, sx * 1.65 + 0.05, -0.03, 0.08, 0.0, 2.75, "metal_dark", bevel=0.006)
        bx(-1.6, 1.6, 0.13, 0.145, 0.0, zb, "window_lit_warm")
        bx(-1.6, 1.6, 0.05, 0.13, zb - 0.04, zb - 0.01, "emit_panel_warm")
        if detail():
            for i in range(5):
                x = -1.4 + i * 0.7
                bx(x - 0.2, x + 0.2, 0.05, 0.12, 0.0, rnd.uniform(0.3, 0.8), rnd.choice(["wood", "metal_painted", "plastic_dark"]), bevel=0.008)
        # shutter hood + neon glyph sign
        bx(-1.8, 1.8, -0.35, T_FACE, 2.8, 3.25, "metal_dark", bevel=0.02)
        neon_glyphs(-1.4, 2.85, 0.36, 0.34, 3, -0.35, neon, seed, vertical=False, backing="black", r=0.009)
        lights.append(K.to_unity_vec((0, -0.6, 0.6)))
        lights.append(K.to_unity_vec((-0.9, -0.6, 3.0)))
        meta["glowMaterial"] = neon
        meta["projection"] = 0.6
    elif kind == "noodle":
        hole = (-1.65, 1.65, 0.0, 2.7)
        shell(style, [hole], band=False)
        # serving counter, hatch, noren strips, lanterns, menu lightbox, stools, steam flue
        bx(-1.65, 1.65, -0.05, 0.15, 0.0, 0.95, "tile_grimy")
        bx(-1.7, 1.7, -0.45, 0.05, 0.95, 1.02, "metal_bare", bevel=0.01)
        bx(-1.6, 1.6, 0.13, 0.145, 1.02, 2.65, "window_lit_warm")
        bx(-1.6, 1.6, 0.0, 0.12, 2.55, 2.58, "emit_white")
        if K.LOD < 2:
            for i in range(9):
                x = -1.5 + i * 0.375
                c = bx(x - 0.16, x + 0.16, -0.08, -0.07, 1.9, 2.62, "tarp_blue" if i % 3 else "tarp")
                if detail():
                    c.rot_about((x, -0.075, 2.62), x=rnd.uniform(-4, 4))
            bx(-1.65, 1.65, -0.1, -0.06, 2.6, 2.66, "wood")
        if detail():
            for i in range(3):
                x = -1.0 + i * 1.0
                cyl(0.11, 0.22, 10, at=(x, -0.42, -0.35 + 0.0), mat="metal_dark").move(0, 0, 0.35)
                cyl(0.025, 0.5, 6, at=(x, -0.42, 0.0), mat="chrome_scratched")
                cyl(0.18, 0.04, 12, at=(x, -0.42, 0.5), mat="paint_glossy_red")
            for x in (-1.85, 1.85):
                tube([(x, -0.3, 3.3), (x, -0.3, 3.0)], 0.004, 4, "rubber")
                lathe([(0.0, 0.0), (0.1, 0.03), (0.14, 0.15), (0.12, 0.3), (0.06, 0.34), (0.0, 0.34)], 12, at=(x, -0.3, 2.66), mat="emit_amber")
            tube([(1.45, 0.05, 2.7), (1.45, -0.25, 2.85), (1.45, -0.25, 3.33)], 0.06, 8, "metal_bare")
        # menu lightbox with glyph column + neon bowl ring
        bx(-1.85, 1.85, -0.38, T_FACE, 2.78, 3.32, "metal_dark", bevel=0.02)
        bx(-1.75, 0.6, -0.385, -0.375, 2.84, 3.26, "emit_panel_yellow")
        if K.LOD < 2:
            rng = random.Random(seed + 77)
            for i in range(6):
                gx = -1.65 + i * 0.37
                for (a, b) in glyph_segments(rng):
                    pa = (gx + a[0] * 0.3, -0.39, 2.88 + a[1] * 0.32)
                    pb = (gx + b[0] * 0.3, -0.39, 2.88 + b[1] * 0.32)
                    if math.dist(pa, pb) > 0.02:
                        beam(pa, pb, 0.018, 0.004, mat="black", up=(0, 1, 0))
            torus(0.17, 0.012, n_major=K.seg(24, 8), n_minor=6, mat=neon).rot(x=90).move(1.2, -0.43, 3.05)
            torus(0.17, 0.012, arc=180, n_major=K.seg(16, 8), n_minor=6, mat=neon, start=180).rot(x=90).move(1.2, -0.43, 3.0)
        lights += [K.to_unity_vec((0, -0.8, 2.4)), K.to_unity_vec((1.2, -0.6, 3.05))]
        meta["colliders"] = wall_collider() + [col_box(-1.7, 1.7, -0.45, T_FACE, 0.0, 1.02)]
        meta["glowMaterial"] = neon
        meta["projection"] = 0.6
    elif kind == "entrance":
        hole = (-0.75, 0.75, 0.0, 2.6)
        shell(style, [hole], band=False)
        bx(-0.75, 0.75, 0.0, 0.15, 0.0, 2.6, s["band"])
        # recessed steel door with vision slot, frame, canopy with downlight, intercom, mailboxes
        bx(-0.6, 0.6, -0.02, 0.0, 0.0, 2.3, "paint_glossy_dark", bevel=0.008)
        if K.LOD < 2:
            bx(-0.65, 0.65, -0.05, 0.0, 2.3, 2.42, "metal_dark")
            for sx in (-1, 1):
                bx(sx * 0.62 - 0.03, sx * 0.62 + 0.03, -0.05, 0.0, 0.0, 2.42, "metal_dark")
            bx(-0.15, 0.15, -0.03, -0.019, 1.45, 1.55, "glass_dark")
            bx(0.42, 0.46, -0.06, -0.02, 0.95, 1.15, "chrome_scratched")
        bx(-1.1, 1.1, -1.0, T_FACE, 2.72, 2.85, "metal_dark", bevel=0.015)
        bx(-1.05, 1.05, -0.98, -0.95, 2.85, 2.9, strip)
        cyl(0.07, 0.015, 12, at=(0, -0.5, 2.705), mat="emit_white")
        for sx in (-1, 1):
            beam((sx * 1.0, T_FACE, 3.2), (sx * 1.0, -0.95, 2.86), 0.02, 0.02, mat="metal_dark")
        bx(0.9, 1.2, T_FACE - 0.05, T_FACE, 1.1, 1.55, "metal_dark", bevel=0.006)
        bx(0.93, 1.17, T_FACE - 0.055, T_FACE - 0.045, 1.3, 1.5, "screen")
        screens.append({"center": K.to_unity_vec((1.05, T_FACE - 0.055, 1.4)), "size": [0.24, 0.2], "normal": [0, 0, 1], "material": "screen"})
        if detail():
            for i in range(3):
                for j in range(2):
                    bx(-1.65 + i * 0.2, -1.47 + i * 0.2, T_FACE - 0.12, T_FACE, 1.0 + j * 0.25, 1.22 + j * 0.25, "metal_painted", bevel=0.005)
            neon_glyphs(-1.6, 2.0, 0.3, 0.3, 1, T_FACE, neon, seed, backing="metal_dark", r=0.008)
        lights.append(K.to_unity_vec((0, -0.6, 2.6)))
        meta["opening"] = {"width": 1.2, "height": 2.3, "doorZ": 0.0}
        meta["projection"] = 1.0
    elif kind == "boarded":
        hole = (-1.65, 1.65, 0.0, 2.75)
        shell(style, [hole], band=False)
        for i in range(4):
            x0 = -1.65 + i * 0.825
            p = bx(x0 + 0.01, x0 + 0.815, -0.03, 0.0, 0.0, 2.7, "wood" if i % 2 else "metal_rusted", bevel=0.004)
            if detail():
                p.rot_about((x0 + 0.41, 0.0, 0.0), y=rnd.uniform(-1.5, 1.5))
        if detail():
            for z in (0.5, 1.4, 2.3):
                bx(-1.65, 1.65, -0.06, -0.03, z, z + 0.1, "metal_rusted")
                for x in (-1.5, -0.4, 0.6, 1.5):
                    cyl(0.01, 0.03, 6, at=(x, -0.09, z + 0.05), axis="Y", mat="metal_bare")
            cable_sag((-1.9, T_FACE - 0.05, 3.1), (0.3, -0.2, 2.1), sag=0.2, r=0.012)
        bx(-1.8, 1.8, -0.3, T_FACE, 2.82, 3.25, "metal_rusted", bevel=0.02).rot_about((-1.8, T_FACE, 3.25), y=-1.5)
        meta["projection"] = 0.3
    if lights:
        meta["lights"] = lights
    if screens:
        meta["screens"] = screens
    return meta


def pier(style="Concrete", w=0.5):
    """Pier / pilaster column module (w x 3.4 m) to fill odd lengths between 4 m modules or flank shops."""
    s = STY[style]
    bx(-w / 2, w / 2, T_RELIEF, T_BACK, 0.0, H, s["pil"], bevel=0.012)
    bx(-w / 2 - 0.01, w / 2 + 0.01, T_RELIEF - 0.01, T_FACE, 0.0, 0.3, s["band"], bevel=0.01)
    if style == "Panel" and K.LOD < 2:
        bx(-0.012, 0.012, T_RELIEF - 0.006, T_RELIEF, 0.32, H, STY["Panel"]["led"])
    if detail():
        conduit([(w / 2 - 0.06, T_RELIEF - 0.03, 0.3), (w / 2 - 0.06, T_RELIEF - 0.03, H)], r=0.018)
    return {"colliders": [K.collider_box((0, (T_RELIEF + T_BACK) / 2, H / 2), (w, T_BACK - T_RELIEF, H))]}


def corner(style="Concrete"):
    """Outside corner piece: an L of two 0.5 m pier faces wrapping a building corner (corner at the pivot,
    faces toward -Y and -X); place at the mass-box corner, offset like the modules."""
    s = STY[style]
    bx(-0.5, 0.0, -0.1, 0.15, 0.0, H, s["pil"], bevel=0.012)
    bx(-0.6, -0.35, -0.6, 0.15, 0.0, H, s["pil"], bevel=0.012)
    bx(-0.62, 0.02, -0.62, 0.15, 0.0, 0.3, s["band"], bevel=0.01)
    if style == "Panel" and K.LOD < 2:
        bx(-0.616, -0.6, -0.616, -0.6, 0.32, H, STY["Panel"]["led"])
    if detail():
        downpipe(-0.66, 0.0, H, yw=-0.62, r=0.05)
    return {"colliders": [K.collider_box((-0.3, -0.2, H / 2), (0.6, 0.7, H))]}


def cornice(style="Concrete"):
    """Top-of-wall cornice band (4 m x 0.6 m), sits on top of the last storey: stepped profile + drip, Panel style
    gets a neon underline."""
    s = STY[style]
    bx(-W / 2, W / 2, -0.3, T_BACK, 0.0, 0.25, s["band"], bevel=0.01)
    bx(-W / 2, W / 2, -0.42, T_BACK, 0.25, 0.45, s["band"], bevel=0.015)
    bx(-W / 2, W / 2, -0.36, T_BACK, 0.45, 0.6, s["head"], bevel=0.01)
    if style == "Panel" and K.LOD < 2:
        bx(-W / 2, W / 2, -0.425, -0.415, 0.235, 0.25, "emit_strip_magenta")
    return {"colliders": [K.collider_box((0, -0.13, 0.3), (W, 0.56, 0.6))]}


def parapet(style="Concrete"):
    """Roof parapet module 4 m: wall + coping + safety rail + roof-side drain scupper; sits on the roof slab edge
    (back = roof side toward +Y Blender / Unity -Z)."""
    s = STY[style]
    bx(-W / 2, W / 2, -0.12, 0.12, 0.0, 1.0, s["wall"])
    bx(-W / 2 - 0.0, W / 2, -0.16, 0.16, 1.0, 1.08, "concrete_dark" if style != "Panel" else "metal_dark", bevel=0.01)
    if K.LOD < 2:
        for x in (-1.5, 0.0, 1.5):
            cyl(0.02, 0.55, 6, at=(x, 0.06, 1.08), mat="metal_painted_yellow")
        tube([(-W / 2, 0.06, 1.62), (W / 2, 0.06, 1.62)], 0.022, K.seg(8), "metal_painted_yellow")
    if detail():
        bx(0.6, 0.85, -0.2, -0.12, 0.05, 0.15, "metal_rusted")
        if style == "Panel":
            bx(-W / 2, W / 2, -0.125, -0.12, 0.85, 0.87, "emit_strip_cyan")
    return {"colliders": [K.collider_box((0, 0, 0.54), (W, 0.32, 1.08))]}


UP_KINDS = {"Window_AC": "window_ac", "Window_Cage": "cage", "Window_Neon": "neon", "Balcony": "balcony", "Window_Double": "double",
            "Pipes": "pipes", "Damaged": "damaged"}
UP_NOTES = {
    "window_ac": "1.6 x 1.6 window (sill 0.9, offset 0.35 m left) + wall-hung AC condenser with refrigerant lines and drip pipe, sagging cables. Projects 0.41 m.",
    "cage": "Window with a protruding steel security cage (0.47 m out) with mesh floor, pots and a crate inside.",
    "neon": "Window + vertical 4-glyph neon tube sign on a backing rail with transformer (invented glyphs). Light anchor in 'lights'.",
    "balcony": "Cantilever balcony 3.8 x 1.1 m (LED soffit strip), sliding door + small window, railing with perforated infill, plant, crate, laundry, wall lamp, AC. Projects 1.25 m; colliders include slab + railing.",
    "double": "Two narrow windows (1.1 x 1.7 m) + downpipe + small AC unit.",
    "pipes": "Blank services wall: downpipe, two horizontal pipes on brackets, electrical cabinet with status LEDs, conduit, louvred vent, sagging cables.",
    "damaged": "Smashed window boarded with planks, hanging cable.",
}
GR_KINDS = {"Shop_Glass": "shop_glass", "Shop_Awning": "shop_awning", "Shop_Shutter": "shop_shutter", "Shop_Noodle": "noodle",
            "Entrance": "entrance", "Shop_Boarded": "boarded"}
GR_NOTES = {
    "shop_glass": "Glazed storefront (door + panes, kick plate), lit shallow interior with stocked shelves, fascia sign box with LED ad face (screen_ad_*, 'screens') and neon LED strips. Projects 0.44 m.",
    "shop_awning": "Glazed storefront + projecting steel/tarp awning 1.6 m with LED lip and a hanging neon blade sign. Projects 1.62 m (awning bottom 2.36 m).",
    "shop_shutter": "Roller shutter half up with warm light spilling out, crates inside, shutter hood with horizontal neon glyph sign.",
    "noodle": "Noodle bar front: tiled counter (top 1.02 m) with stools, noren cloth strips, two paper lanterns (emissive), menu lightbox with invented glyphs, neon bowl ring, steam flue. Counter collider.",
    "entrance": "Apartment entrance: recessed steel door 1.2 x 2.3, canopy with downlight + LED edge, intercom 'screen', mailboxes, neon house glyph.",
    "boarded": "Boarded-up shop (plywood and rusted sheet, rails, bolts), sagging fascia, hanging cable.",
}

for st in ("Concrete", "Plaster", "Brick", "Panel"):
    for i, (nm, kind) in enumerate(UP_KINDS.items()):
        ASSETS[f"Building_Facade_{st}_{nm}"] = dict(fn=_upper, kw={"style": st, "kind": kind, "seed": i + 1 + len(st) * 3}, cat="facade",
                                                     zones=["plaza", "rooftops"], uv_offset=(0.0, 0.0),
                                                     notes=f"{st} upper-storey module 4 x 3.4 m (same placement as Facade_*). " + UP_NOTES[kind])
    ASSETS[f"Building_Facade_{st}_Pier"] = dict(fn=pier, kw={"style": st}, cat="facade", zones=["plaza", "rooftops"], uv_offset=(0.0, 0.0),
                                                 notes=f"{st} 0.5 x 3.4 m pier: fills odd lengths at module ends; back at Unity z -0.15 like the modules.")
    ASSETS[f"Building_Facade_{st}_Corner"] = dict(fn=corner, kw={"style": st}, cat="facade", zones=["plaza", "rooftops"], uv_offset=(0.0, 0.0),
                                                   notes=f"{st} outside-corner piece (L, 0.62 x 0.62 m, 3.4 m tall) with downpipe. Pivot = building corner; wraps toward Unity +Z and +X.")
    ASSETS[f"Building_Facade_{st}_Cornice_4m"] = dict(fn=cornice, kw={"style": st}, cat="facade", zones=["plaza", "rooftops"], uv_offset=(0.0, 0.0),
                                                       notes=f"{st} 4 m cornice band, 0.6 m tall, projects 0.42 m: place on top of the last storey (y = floors x 3.4).")
    ASSETS[f"Building_Parapet_{st}_4m"] = dict(fn=parapet, kw={"style": st}, cat="facade", zones=["plaza", "rooftops"], uv_offset=(0.0, 0.0),
                                               notes=f"{st} roof parapet 4 m: 1.0 m wall + coping (1.08) + yellow safety rail (1.62), scupper. Centre line on the roof edge.")
for i, (nm, kind) in enumerate(GR_KINDS.items()):
    for st in ("Concrete", "Panel"):
        ASSETS[f"Building_Facade_{st}_{nm}"] = dict(fn=_ground, kw={"kind": kind, "seed": i + 1 + (7 if st == "Panel" else 0), "style": st}, cat="facade",
                                                     zones=["plaza"], uv_offset=(0.0, 0.0),
                                                     notes=f"{st} ground-floor module 4 x 3.4 m (same placement as Facade_Shop). " + GR_NOTES[kind])
