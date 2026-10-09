"""Facility / interior props, corporate high-tech restyle (Deus Ex / Cyberpunk 2077 interiors).

Glossy white and dark paint, carbon panels, scratched chrome, frosted glass, LED edge strips (emit_strip_cyan / blue)
and additive holographic displays (holo_cyan / holo_magenta) floating over desks and benches.

Existing assets keep their name, size, pivot, colliders, metadata and every slot the zone code swaps (emit_*, screen,
aether_energy). Also hosts small shared helpers (holograms, invented glyphs, flat-face batches, the corporate emblem)
that assets_metro imports.
"""
import math
import random

from mathutils import Euler, Matrix

import envkit as K
from envkit import box, cyl, lathe, tube, torus, beam, plane, extrude, inset, faces_where, detail


# ============================================================================================== shared helpers
def M(x=0.0, y=0.0, z=0.0, rx=0.0, ry=0.0, rz=0.0):
    """4x4 transform for K.placed(): rotate (degrees, XYZ) then translate."""
    return Matrix.Translation((x, y, z)) @ Euler((math.radians(rx), math.radians(ry), math.radians(rz)), "XYZ").to_matrix().to_4x4()


def pt(m, v):
    """Transform point v by matrix m (for wiring light sheets to placed holograms)."""
    from mathutils import Vector
    return tuple(m @ Vector(v))


class Flat:
    """Collects many flat faces into ONE part (holograms, LED dots, port holes): far cheaper than one part each."""

    def __init__(self, mat):
        self.p = K._new(mat, "flat")

    def face(self, pts, mat=None):
        bm = self.p.bm
        f = bm.faces.new([bm.verts.new(v) for v in pts])
        if mat:
            f[self.p.mats] = self.p.slot(mat)
        return f


def poly(pts, mat, fl=None):
    """One flat face from 3D points (counter-clockwise seen from the front)."""
    if fl is not None:
        return fl.face(pts, mat)
    p = K._new(mat, "poly")
    p.bm.faces.new([p.bm.verts.new(v) for v in pts])
    return p


def vquad(x0, z0, x1, z1, y=0.0, mat="holo_cyan", fl=None):
    """Quad in the XZ plane at depth y facing -Y (the asset front)."""
    return poly([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], mat, fl)


def hquad(x0, y0, x1, y1, z=0.0, mat="holo_cyan", fl=None):
    """Horizontal quad facing +Z."""
    return poly([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], mat, fl)


def stroke(a, b, w, y=0.0, mat="holo_cyan", depth=0.0, fl=None):
    """Straight stroke from a=(x,z) to b=(x,z) of width w facing -Y; ends extended by w/2 so strokes join.
    depth > 0 makes a solid bar (3D glyphs); a == b makes a dot."""
    ax, az = a
    bx, bz = b
    dx, dz = bx - ax, bz - az
    L = math.hypot(dx, dz)
    if L < 1e-6:
        ax, bx = ax - w * 0.05, ax + w * 0.05
        dx, dz, L = bx - ax, 0.0, bx - ax
    ux, uz = dx / L, dz / L
    ax, az, bx, bz = ax - ux * w / 2, az - uz * w / 2, bx + ux * w / 2, bz + uz * w / 2
    if depth > 0:
        return beam((ax, y, az), (bx, y, bz), w, depth, mat=mat, up=(0, 1, 0))
    nx, nz = -uz * w / 2, ux * w / 2
    return poly([(ax - nx, y, az - nz), (bx - nx, y, bz - nz), (bx + nx, y, bz + nz), (ax + nx, y, az + nz)], mat, fl)


def ring2d(cx, cz, r0, r1, a0=0.0, a1=360.0, n=24, y=0.0, mat="holo_cyan", fl=None):
    """Flat annulus sector in the XZ plane facing -Y (angles in degrees, CCW from +X)."""
    n = K.seg(n, 6)
    for i in range(n):
        t0 = math.radians(a0 + (a1 - a0) * i / n)
        t1 = math.radians(a0 + (a1 - a0) * (i + 1) / n)
        if a1 < a0:
            t0, t1 = t1, t0
        c0, s0, c1, s1 = math.cos(t0), math.sin(t0), math.cos(t1), math.sin(t1)
        poly([(cx + r0 * c0, y, cz + r0 * s0), (cx + r1 * c0, y, cz + r1 * s0), (cx + r1 * c1, y, cz + r1 * s1),
              (cx + r0 * c1, y, cz + r0 * s1)], mat, fl)


def glyph_strokes(rng):
    """Invented glyph after matdefs_hd.glyph(): roof bar, two stems, enclosure box or crossing diagonals, mid bar,
    ticks, optional dot. Strokes (ax, ay, bx, by) and dots (x, y) in 0..1. Never a Latin letter."""
    S = []
    top = rng.uniform(0.78, 0.9)
    S.append((rng.uniform(0.08, 0.2), top, rng.uniform(0.8, 0.92), top))
    for x in sorted(rng.sample([0.22, 0.38, 0.5, 0.62, 0.78], 2)):
        S.append((x, rng.uniform(0.05, 0.3), x, rng.uniform(0.6, top)))
    if rng.random() < 0.6:
        x0, x1 = rng.uniform(0.15, 0.35), rng.uniform(0.65, 0.85)
        y0, y1 = rng.uniform(0.1, 0.3), rng.uniform(0.45, 0.62)
        S += [(x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)]
    else:
        S.append((rng.uniform(0.1, 0.3), rng.uniform(0.1, 0.3), rng.uniform(0.55, 0.9), rng.uniform(0.45, 0.7)))
        S.append((rng.uniform(0.55, 0.9), rng.uniform(0.05, 0.25), rng.uniform(0.15, 0.45), rng.uniform(0.5, 0.7)))
    mid = rng.uniform(0.38, 0.6)
    S.append((rng.uniform(0.05, 0.25), mid, rng.uniform(0.7, 0.95), mid + rng.uniform(-0.05, 0.05)))
    for _ in range(rng.randint(1, 2)):
        x, y = rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9)
        S.append((x, y, x + rng.uniform(-0.15, 0.15), y - rng.uniform(0.08, 0.15)))
    dots = [(rng.uniform(0.15, 0.85), rng.uniform(0.15, 0.85))] if rng.random() < 0.5 else []
    return S, dots


def glyph(rng, cx, cz, size, y=0.0, mat="holo_cyan", w=None, depth=0.0, fl=None):
    """One invented glyph centred at (cx, cz) in the XZ plane facing -Y."""
    S, dots = glyph_strokes(rng)
    w = w or size * 0.085
    for (ax, ay, bx, by) in S:
        stroke((cx + (ax - 0.5) * size, cz + (ay - 0.5) * size), (cx + (bx - 0.5) * size, cz + (by - 0.5) * size), w, y, mat, depth, fl)
    for (x, yy) in dots:
        d = (cx + (x - 0.5) * size, cz + (yy - 0.5) * size)
        stroke(d, d, w * 1.3, y, mat, depth, fl)


def glyph_row(rng, x0, cz, size, count, y=0.0, mat="holo_cyan", gap=0.3, w=None, depth=0.0, fl=None):
    for i in range(count):
        glyph(rng, x0 + size * (1 + gap) * i + size / 2, cz, size, y, mat, w, depth, fl)


def corp_symbol(size=1.0, depth=0.04, y=0.0, mat="chrome_scratched", bevel=0.0):
    """Invented corporate emblem (no real logo): three tapered crescents on a broken ring around a split rhombus,
    with radial ticks in the gaps. XZ plane, centred at (0, y, 0), front -Y, overall diameter ~1.16 * size."""
    R0, R1 = 0.36 * size, 0.5 * size
    n = K.seg(14, 5)
    for k in range(3):
        a0 = math.radians(90 + k * 120 + 13)
        a1 = math.radians(90 + (k + 1) * 120 - 13)
        outer = [(R1 * math.cos(a0 + (a1 - a0) * i / n), R1 * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
        inner = []
        for i in reversed(range(n + 1)):
            t = a0 + (a1 - a0) * i / n
            r = R0 + (R1 - R0) * 0.62 * (1 - math.sin(math.pi * i / n))
            inner.append((r * math.cos(t), r * math.sin(t)))
        extrude(outer + inner, depth, plane="XZ", at=(0, y, 0), mat=mat, bevel=bevel)
    r, g = 0.24 * size, 0.022 * size
    extrude([(-r * 0.72, g), (r * 0.72, g), (0, r)], depth, plane="XZ", at=(0, y, 0), mat=mat, bevel=bevel)
    extrude([(-r * 0.72, -g), (0, -r), (r * 0.72, -g)], depth, plane="XZ", at=(0, y, 0), mat=mat, bevel=bevel)
    for k in range(3):
        t = math.radians(90 + k * 120 + 60)
        c, s = math.cos(t), math.sin(t)
        beam((c * R1 * 1.04, y, s * R1 * 1.04), (c * R1 * 1.16, y, s * R1 * 1.16), 0.035 * size, depth, mat=mat, up=(0, 1, 0))


# ---------------------------------------------------------------------------------------------- holograms
def _rows(fl, rng, x0, x1, z0, z1, n, lw, mat, acc=None):
    """Data rows: dashes of random length, like lines of text."""
    pitch = (z1 - z0) / n
    for i in range(n):
        z = z1 - (i + 0.5) * pitch
        x = x0
        while x < x1 - (x1 - x0) * 0.08:
            xe = min(x + rng.uniform(0.06, 0.32) * (x1 - x0), x1)
            vquad(x, z - lw * 0.8, xe, z + lw * 0.8, 0.0, acc if acc and rng.random() < 0.1 else mat, fl)
            x = xe + rng.uniform(0.03, 0.08) * (x1 - x0)


def _bars(fl, rng, x0, x1, z0, z1, n, lw, mat, acc=None):
    bw = (x1 - x0) / n
    for i in range(n):
        hgt = rng.uniform(0.15, 1.0) * (z1 - z0)
        m = acc if acc and i == n - 2 else mat
        vquad(x0 + bw * (i + 0.18), z0 + lw, x0 + bw * (i + 0.82), z0 + lw + hgt, 0.0, m, fl)
    stroke((x0, z0), (x1, z0), lw * 0.7, 0.0, mat, fl=fl)


def _wave(fl, rng, x0, x1, z0, z1, lw, mat, n=26):
    ph, ph2 = rng.uniform(0, 6), rng.uniform(0, 6)
    zc, A = (z0 + z1) / 2, (z1 - z0) * 0.42
    n = K.seg(n, 8)
    pts = [(x0 + (x1 - x0) * i / n, zc + A * (0.65 * math.sin(i * 0.55 + ph) + 0.35 * math.sin(i * 1.7 + ph2))) for i in range(n + 1)]
    for a, b in zip(pts, pts[1:]):
        stroke(a, b, lw, 0.0, mat, fl=fl)
    for k in range(3):  # faint grid
        z = z0 + (z1 - z0) * (k + 0.5) / 3
        stroke((x0, z), (x1, z), lw * 0.35, 0.0, mat, fl=fl)


def _gauge(fl, rng, cx, cz, r, lw, mat, acc):
    arc = rng.uniform(150, 300)
    ring2d(cx, cz, r * 0.8, r, 90, 90 - arc, 20, 0.0, mat, fl)
    ring2d(cx, cz, r * 1.08, r * 1.08 + lw * 0.6, 0, 360, 28, 0.0, mat, fl)
    ring2d(cx, cz, r * 0.55, r * 0.55 + lw * 0.6, 0, 360, 16, 0.0, acc, fl)
    glyph(rng, cx, cz, r * 0.7, 0.0, mat, w=r * 0.07, fl=fl)


def _helix(fl, x0, x1, z0, z1, lw, mat, acc, n=26):
    cx, A = (x0 + x1) / 2, (x1 - x0) * 0.36
    n = K.seg(n, 10)
    strands = []
    for s in (0.0, math.pi):
        pts = [(cx + A * math.sin(i * 0.5 + s), z0 + (z1 - z0) * i / n) for i in range(n + 1)]
        strands.append(pts)
        for a, b in zip(pts, pts[1:]):
            stroke(a, b, lw * 1.1, 0.0, mat, fl=fl)
    for i in range(1, n, 2):
        stroke(strands[0][i], strands[1][i], lw * 0.6, 0.0, acc if i % 6 == 1 else mat, fl=fl)


def holo_panel(w, h, seed=1, kind="data", mat="holo_cyan", acc="holo_magenta"):
    """Floating hologram, centred at the origin in the XZ plane, facing -Y: scanline fill, corner brackets,
    glyph header with an accent tag, and a body by `kind`: 'data' (rows, bar chart, waveform, gauge),
    'lab' (helix + rows + gauge), 'dash' (two gauges, waveform chart, rows, bars), 'mini' (rows + gauge)."""
    rng = random.Random(seed)
    fl = Flat(mat)
    hw, hh = w / 2, h / 2
    lw = max(0.0035, min(w, h) * 0.011)
    n = max(6, int(h / 0.024))
    if K.LOD:
        n = max(4, n // 3)
    pitch = h / n
    for i in range(n):
        z = -hh + (i + 0.5) * pitch
        vquad(-hw, z - pitch * 0.13, hw, z + pitch * 0.13, 0.0, mat, fl)
    c = min(w, h) * 0.14
    for sx in (-1, 1):
        for sz in (-1, 1):
            x, z = sx * hw, sz * hh
            stroke((x, z), (x - sx * c, z), lw * 1.3, 0.0, mat, fl=fl)
            stroke((x, z), (x, z - sz * c), lw * 1.3, 0.0, mat, fl=fl)
    if not detail():
        return fl
    m = min(w, h) * 0.08
    zh = hh - h * 0.2
    stroke((-hw + m, zh), (hw - m, zh), lw * 0.6, 0.0, mat, fl=fl)
    gs = h * 0.1
    glyph_row(rng, -hw + m, zh + (hh - zh) * 0.5, gs, 4 if w > 1.3 * h else 3, mat=mat, w=gs * 0.11, fl=fl)
    vquad(hw - m - w * 0.12, zh + (hh - zh) * 0.32, hw - m, zh + (hh - zh) * 0.68, 0.0, acc, fl)
    x0, x1, z0, z1 = -hw + m, hw - m, -hh + m, zh - m * 0.8
    W_, H_ = x1 - x0, z1 - z0
    if kind == "lab":
        _helix(fl, x0, x0 + W_ * 0.28, z0, z1, lw, mat, acc)
        _rows(fl, rng, x0 + W_ * 0.36, x1, z0 + H_ * 0.45, z1, 4, lw, mat, acc)
        _gauge(fl, rng, x0 + W_ * 0.5, z0 + H_ * 0.2, H_ * 0.2, lw, mat, acc)
        _bars(fl, rng, x0 + W_ * 0.66, x1, z0, z0 + H_ * 0.38, 7, lw, mat, acc)
    elif kind == "dash":
        r = min(H_ * 0.22, W_ * 0.1)
        _gauge(fl, rng, x0 + r * 1.15, z1 - r * 1.15, r, lw, mat, acc)
        _gauge(fl, rng, x0 + r * 1.15, z0 + r * 1.15, r, lw, mat, acc)
        _wave(fl, rng, x0 + W_ * 0.27, x0 + W_ * 0.72, z0 + H_ * 0.42, z1, lw, mat)
        _bars(fl, rng, x0 + W_ * 0.27, x0 + W_ * 0.72, z0, z0 + H_ * 0.34, 14, lw, mat, acc)
        _rows(fl, rng, x0 + W_ * 0.77, x1, z0, z1, 9, lw, mat, acc)
    elif kind == "mini":
        _rows(fl, rng, x0, x0 + W_ * 0.58, z0, z1, 4, lw, mat, acc)
        _gauge(fl, rng, x0 + W_ * 0.8, (z0 + z1) / 2, min(H_ * 0.42, W_ * 0.18), lw, mat, acc)
    else:
        _rows(fl, rng, x0, x0 + W_ * 0.42, z0, z1, 6, lw, mat, acc)
        _bars(fl, rng, x0 + W_ * 0.5, x1 - W_ * 0.2, z0 + H_ * 0.52, z1, 9, lw, mat, acc)
        _wave(fl, rng, x0 + W_ * 0.5, x1, z0, z0 + H_ * 0.42, lw, mat)
        _gauge(fl, rng, x1 - W_ * 0.09, z0 + H_ * 0.76, min(W_ * 0.08, H_ * 0.2), lw, mat, acc)
    return fl


def holo_emitter(x, y, z, r=0.06, lit=True):
    """Desk-top holo projector puck (base at z)."""
    cyl(r, 0.022, 24, at=(x, y, z), mat="paint_glossy_dark", bevel=0.005)
    torus(r * 0.78, 0.005, n_major=16, n_minor=4, mat="emit_cyan" if lit else "black").move(x, y, z + 0.022)
    cyl(r * 0.55, 0.004, 16, at=(x, y, z + 0.02), mat="glass_dark")
    if detail():
        cyl(r * 1.05, 0.006, 24, at=(x, y, z), mat="chrome_scratched")


def open_box(fl, x, y, z, sx, sy, h, mat="holo_cyan"):
    """Bottomless box (top + 4 sides, 10 tris) added to a Flat: hologram buildings, LED blocks."""
    x0, x1, y0, y1, z1 = x - sx / 2, x + sx / 2, y - sy / 2, y + sy / 2, z + h
    fl.face([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], mat)
    fl.face([(x0, y0, z), (x1, y0, z), (x1, y0, z1), (x0, y0, z1)], mat)
    fl.face([(x1, y0, z), (x1, y1, z), (x1, y1, z1), (x1, y0, z1)], mat)
    fl.face([(x1, y1, z), (x0, y1, z), (x0, y1, z1), (x1, y1, z1)], mat)
    fl.face([(x0, y1, z), (x0, y0, z), (x0, y0, z1), (x0, y1, z1)], mat)


def light_sheet(base_pts, top_pts, mat="holo_cyan"):
    """Projection sheet: quad between two point pairs (emitter lip -> hologram edge)."""
    a0, a1 = base_pts
    b0, b1 = top_pts
    poly([a0, a1, b1, b0], mat)


def slots(x0, x1, z0, z1, y, n, mat="black", h=0.012, fl=None):
    """Row of horizontal vent slots (flat quads facing -Y)."""
    for i in range(n):
        z = z0 + (z1 - z0) * (i + 0.5) / n
        vquad(x0, z - h / 2, x1, z + h / 2, y, mat, fl)


def bolts(pts, r=0.007, h=0.005, axis="Y", mat="chrome_scratched", n=6):
    """Small bolt heads (LOD0 only). For axis 'Y' each bolt spans y..y+h, so pass y = face_y - h for a -Y face."""
    if not detail():
        return
    for p in pts:
        cyl(r, h, n, at=p, axis=axis, mat=mat)


# ============================================================================================== server rack
def _patch(x, z, side, rnd, yf):
    """Patch cable from a port at (x, yf, z) sweeping down into the side cable manager."""
    xm = side * 0.31
    pts = [(x, yf + 0.004, z), (x, yf - 0.018, z - 0.004), (x + (xm - x) * 0.45, yf - 0.03, z - 0.03),
           (xm, yf - 0.012, z - rnd.uniform(0.05, 0.09))]
    tube(pts, 0.0032, 4, mat=rnd.choice(["rubber", "tarp_blue", "tarp_blue", "metal_painted_yellow", "plastic_orange"]), caps=False)


def server_rack(W=0.8, D=1.0, H=2.2, lit=True, seed=11):
    rnd = random.Random(seed)
    E = (lambda m: m) if lit else (lambda m: "black")
    zb, zt = 0.08, H - 0.035
    hb = zt - zb
    # levelling feet, recessed plinth with intake grille and a floor-wash LED line
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(0.022, 0.034, 10, at=(sx * (W / 2 - 0.06), sy * (D / 2 - 0.06), -0.002), mat="chrome_scratched")
    box(W - 0.06, D - 0.06, zb - 0.03, at=(0, 0, 0.03), mat="black", base=True, bevel=0.004)
    box(W - 0.2, 0.004, 0.028, at=(0, -(D - 0.06) / 2 - 0.002, 0.041), mat="grating", base=True)
    box(W - 0.12, 0.004, 0.005, at=(0, -(D - 0.06) / 2 - 0.002, 0.035), mat=E("emit_strip_cyan"))
    # corner posts + carbon side skins with raised field and vent slots
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(0.05, 0.05, hb, at=(sx * (W / 2 - 0.025), sy * (D / 2 - 0.045), zb), mat="paint_glossy_dark", base=True, bevel=0.006)
        sp = box(0.02, D - 0.14, hb - 0.04, at=(sx * (W / 2 - 0.012), 0, zb + 0.02), mat="paint_glossy_dark", base=True, bevel=0.004)
        inset(sp, faces_where(sp, lambda f, s=sx: f.normal.x * s > 0.9), 0.045, 0.003)
        if detail():
            n0 = K.part_count()
            vf = Flat("black")
            for z0 in (0.32, zt - 0.42):
                slots(-0.23, 0.23, z0, z0 + 0.21, 0.0, 7, "black", 0.012, vf)
            for p in K.parts_since(n0):
                p.rot(z=90 * sx).move(sx * (W / 2 + 0.0012), 0, 0)
    # top cap: fan grilles with chrome rings, cable brush entry, front status line
    box(W + 0.01, D + 0.01, H - zt, at=(0, 0, zt), mat="paint_glossy_dark", base=True, bevel=0.008)
    box(W - 0.14, 0.004, 0.01, at=(0, -(D + 0.01) / 2 - 0.0015, zt + 0.0175), mat=E("emit_strip_blue"))
    for y in (-0.2, 0.2):
        cyl(0.118, 0.0015, 20, at=(0, y, H), mat="black")
        cyl(0.12, 0.004, 20, at=(0, y, H + 0.0015), mat="grating")
        torus(0.124, 0.0045, n_major=24, n_minor=4, mat="chrome_scratched").move(0, y, H + 0.0015)
        cyl(0.032, 0.005, 12, at=(0, y, H), mat="metal_dark")
    if detail():
        box(0.46, 0.05, 0.004, at=(0, D / 2 - 0.07, H + 0.002), mat="black")
        bolts([(sx * (W / 2 - 0.03), sy * (D / 2 - 0.03), H) for sx in (-1, 1) for sy in (-1, 1)], 0.008, 0.003, axis="Z")
    # dark interior + rack rails + side cable managers with vertical bundles
    box(W - 0.1, D - 0.2, hb - 0.02, at=(0, 0.06, zb + 0.01), mat="black", base=True)
    yf = -0.44
    for sx in (-1, 1):
        box(0.016, 0.012, hb - 0.06, at=(sx * 0.29, yf + 0.008, zb + 0.03), mat="metal_bare", base=True)
        xm = sx * 0.322
        box(0.042, 0.004, hb - 0.06, at=(xm, -0.40, zb + 0.03), mat="plastic_dark", base=True)
        for s in (-1, 1):
            box(0.003, 0.05, hb - 0.06, at=(xm + s * 0.0195, -0.425, zb + 0.03), mat="plastic_dark", base=True)
        for k, (dx, m) in enumerate(((-0.009, "rubber"), (0.007, "tarp_blue"), (-0.001, "metal_painted_yellow"), (0.01, "rubber"))):
            cyl(0.0058, hb - 0.12, 6, at=(xm + dx, -0.412 - (k % 2) * 0.012, zb + 0.06), mat=m)
        if detail():
            z = zb + 0.12
            while z < zt - 0.1:
                box(0.042, 0.006, 0.012, at=(xm, -0.448, z), mat="plastic_dark")
                z += 0.178
    # rack units behind the mesh door
    units = []
    z = zb + 0.07
    while True:
        u = rnd.choice([1, 1, 1, 2, 2, 2, 3, 4])
        h = 0.0445 * u
        if z + h > zt - 0.07:
            break
        units.append((z, h, u))
        z += h + 0.003
    fl = Flat("black")
    def led():
        r = rnd.random()
        return E("emit_green" if r < 0.55 else ("emit_cyan" if r < 0.88 else "emit_amber"))
    for (z, h, u) in units:
        kind = rnd.choice(["switch", "compute", "blank", "compute", "switch"]) if u == 1 else rnd.choice(["storage", "compute", "storage"])
        fm = {"switch": "plastic_dark", "compute": "metal_dark", "storage": "paint_glossy_dark", "blank": "metal_dark"}[kind]
        box(0.56, 0.1, h - 0.003, at=(0, yf + 0.05, z + h / 2), mat=fm, bevel=0.002)
        if not detail():
            continue
        yq = yf - 0.0006
        for sx in (-1, 1):
            box(0.01, 0.008, min(h * 0.62, 0.11), at=(sx * 0.266, yf - 0.006, z + h / 2), mat="chrome_scratched")
        if kind == "storage":
            n = 6 if u == 2 else 8
            bw = 0.44 / n
            for k in range(n):
                xk = -0.22 + bw * (k + 0.5)
                box(bw - 0.005, 0.008, h * 0.8, at=(xk, yf - 0.004, z + h / 2), mat="plastic_dark")
                vquad(xk - 0.004, z + h * 0.16, xk + 0.004, z + h * 0.16 + 0.004, yf - 0.0085, led(), fl)
                if u >= 3:
                    vquad(xk - 0.004, z + h * 0.26, xk + 0.004, z + h * 0.26 + 0.004, yf - 0.0085, led(), fl)
        elif kind == "compute":
            box(0.28, 0.004, h * 0.62, at=(-0.07, yf - 0.002, z + h / 2), mat="grating")
            for k in range(rnd.randint(4, 9)):
                xk = 0.235 - k * 0.014
                vquad(xk - 0.005, z + h * 0.6, xk + 0.005, z + h * 0.6 + 0.007, yq, led(), fl)
            vquad(0.1, z + h * 0.28, 0.24, z + h * 0.28 + 0.005, yq, E("emit_strip_blue"), fl)
        elif kind == "switch":
            for row in range(2):
                zr = z + h * (0.3 + 0.38 * row)
                for k in range(12):
                    xk = -0.2 + k * 0.026
                    vquad(xk - 0.008, zr - 0.006, xk + 0.008, zr + 0.006, yq, "black", fl)
                    if rnd.random() < 0.7:
                        vquad(xk - 0.003, zr + 0.008, xk + 0.001, zr + 0.011, yq, led(), fl)
            for k in rnd.sample(range(12), rnd.randint(3, 6)):
                xk = -0.2 + k * 0.026
                _patch(xk, z + h * 0.3, -1 if xk < 0 else 1, rnd, yf)
        else:
            slots(-0.2, 0.2, z + h * 0.25, z + h * 0.75, yq, 3, "black", 0.004, fl)
            vquad(-0.25, z + h * 0.5 - 0.003, 0.25, z + h * 0.5 + 0.003, yq - 0.0004, E("emit_cyan"), fl)
    # front door: glossy frame, perforated mesh, LED edge strips, chrome handle, keypad, hinges
    yd = -D / 2 + 0.01
    for sx in (-1, 1):
        box(0.05, 0.02, hb - 0.01, at=(sx * (W / 2 - 0.03), yd, zb + 0.005), mat="paint_glossy_dark", base=True, bevel=0.005)
        box(0.007, 0.004, hb - 0.3, at=(sx * 0.351, yd - 0.0115, zb + 0.15), mat=E("emit_strip_cyan"), base=True)
    for z0 in (zb + 0.005, zt - 0.065):
        box(W - 0.11, 0.02, 0.06, at=(0, yd, z0), mat="paint_glossy_dark", base=True, bevel=0.005)
    box(W - 0.11, 0.004, hb - 0.13, at=(0, yd + 0.002, zb + 0.065), mat="grating", base=True)
    box(0.018, 0.012, 0.34, at=(0.374, -0.503, 0.96), mat="chrome_scratched", base=True, bevel=0.004)
    if detail():
        for zz in (0.985, 1.275):
            box(0.012, 0.01, 0.02, at=(0.374, -0.4955, zz), mat="chrome_scratched")
        kp = box(0.034, 0.006, 0.07, at=(0.374, -0.503, 1.4), mat="plastic_dark", bevel=0.002)
        vquad(0.368, 1.42, 0.38, 1.426, -0.5065, E("emit_green"), fl)
        for zz in (0.3, 1.1, 1.9):
            cyl(0.007, 0.07, 6, at=(-0.397, -0.497, zz), mat="chrome_scratched")
        box(0.12, 0.004, 0.03, at=(-0.24, yd - 0.011, zt - 0.035), mat="metal_painted_yellow")
        for k in range(3):
            glyph(random.Random(seed * 7 + k), -0.275 + k * 0.032, zt - 0.035, 0.024, yd - 0.0135, "black", fl=fl)
    # rear door: glossy skin with perforated field + handle
    rd = box(W - 0.02, 0.02, hb - 0.01, at=(0, D / 2 - 0.01, zb + 0.005), mat="paint_glossy_dark", base=True, bevel=0.005)
    inset(rd, faces_where(rd, lambda f: f.normal.y > 0.9), 0.06, -0.004, mat="grating")
    box(0.02, 0.03, 0.26, at=(W / 2 - 0.08, D / 2 + 0.015, 0.98), mat="chrome_scratched", base=True, bevel=0.005)
    return {"colliders": [K.collider_box((0, 0, H / 2), (W, D, H))]}


ASSETS_A = {
    "Server_Rack": dict(fn=server_rack, cat="facility", zones=["facility"],
                        notes="0.8 x 1.0 x 2.2 rack: glossy frame, carbon side skins, perforated mesh front door with cyan LED edge strips "
                              "(emit_strip_cyan) and chrome handle; behind it rack units with drive bays and blinking LED rows "
                              "(emit_green / emit_cyan / emit_amber), patch-cable bundles into side cable managers; top fan grilles."),
    "Server_Rack_Dark": dict(fn=server_rack, kw={"lit": False, "seed": 12}, cat="facility", zones=["facility"],
                             notes="Unpowered variant (every LED / strip slot is black)."),
}


# ============================================================================================== lab furniture
def _flask(at, h=0.25, mat="glass"):
    x, y, z = at
    lathe([(0.001, 0.0), (h * 0.42, 0.0), (h * 0.44, h * 0.08), (h * 0.12, h * 0.7), (h * 0.12, h), (h * 0.14, h * 1.02), (h * 0.1, h * 1.02)],
          8, at=(x, y, z), mat=mat, close_top=False)


def _bottle(x, y, z, r, h, cap="plastic_dark", mat="glass"):
    lathe([(r, 0.0), (r, h * 0.72), (r * 0.45, h * 0.86), (r * 0.45, h * 0.9)], 8, at=(x, y, z), mat=mat, close_top=False)
    cyl(r * 0.5, h * 0.12, 6, at=(x, y, z + h * 0.88), mat=cap)


def _microscope(x, y, z):
    box(0.2, 0.26, 0.04, at=(x, y + 0.03, z), mat="paint_glossy_white", base=True, bevel=0.01)
    beam((x, y + 0.13, z + 0.04), (x, y + 0.1, z + 0.36), 0.06, 0.07, mat="paint_glossy_white", bevel=0.012)
    box(0.08, 0.17, 0.065, at=(x, y + 0.04, z + 0.36), mat="paint_glossy_white", bevel=0.012)
    box(0.15, 0.12, 0.012, at=(x, y - 0.01, z + 0.16), mat="black", bevel=0.003)
    box(0.05, 0.05, 0.1, at=(x, y + 0.075, z + 0.12), mat="paint_glossy_dark", base=True)
    cyl(0.032, 0.03, 12, at=(x, y - 0.005, z + 0.3), mat="chrome_scratched")
    for dx in (-0.016, 0.0, 0.016):
        cyl(0.008, 0.06, 8, at=(x + dx, y - 0.005, z + 0.24), mat="chrome_scratched")
    for dx in (-0.018, 0.018):
        t = cyl(0.012, 0.09, 10, mat="black")
        t.rot(x=-35).move(x + dx, y - 0.03, z + 0.38)
    cyl(0.03, 0.02, 12, at=(x + 0.06, y + 0.11, z + 0.1), axis="X", mat="chrome_scratched")
    vquad(x - 0.04, z + 0.015, x + 0.04, z + 0.022, y - 0.101, "emit_cyan")


def _centrifuge(x, y, z):
    lathe([(0.16, 0.0), (0.17, 0.02), (0.17, 0.15), (0.16, 0.17), (0.001, 0.17)], 20, at=(x, y, z), mat="paint_glossy_white", close_bottom=False)
    lathe([(0.14, 0.17), (0.12, 0.2), (0.06, 0.215), (0.001, 0.218)], 20, at=(x, y, z), mat="glass_dark", close_bottom=False)
    torus(0.15, 0.006, n_major=20, n_minor=3, mat="emit_cyan").move(x, y, z + 0.172)
    p = box(0.12, 0.03, 0.05, mat="black", bevel=0.004)
    p.rot(x=-20).move(x, y - 0.16, z + 0.09)
    vquad(x - 0.045, z + 0.075, x + 0.045, z + 0.1, y - 0.178, "emit_panel_cyan")


def _vial_rack(x, y, z, rnd):
    box(0.32, 0.1, 0.05, at=(x, y, z), mat="chrome_scratched", base=True, bevel=0.004)
    for r in range(2):
        for k in range(6):
            vx, vy = x - 0.125 + k * 0.05, y - 0.022 + r * 0.044
            cyl(0.011, 0.1, 6, at=(vx, vy, z + 0.02), mat="glass", caps=False)
            cyl(0.0125, 0.018, 6, at=(vx, vy, z + 0.12), mat=rnd.choice(["plastic_orange", "plastic_dark", "tarp_blue"]))


def _analyzer(x, y, z):
    """Sequencer tower: glossy body, dark glass sample bay with LED rim, angled touch display, vial carousel."""
    box(0.4, 0.36, 0.06, at=(x, y, z), mat="paint_glossy_dark", base=True, bevel=0.01)
    box(0.38, 0.34, 0.34, at=(x, y + 0.01, z + 0.06), mat="paint_glossy_white", base=True, bevel=0.025, bseg=2)
    box(0.26, 0.012, 0.16, at=(x - 0.04, y - 0.163, z + 0.13), mat="glass_dark", base=True, bevel=0.004)
    box(0.27, 0.006, 0.006, at=(x - 0.04, y - 0.168, z + 0.305), mat="emit_strip_cyan")
    box(0.006, 0.006, 0.16, at=(x + 0.098, y - 0.168, z + 0.13), mat="emit_strip_cyan", base=True)
    d = box(0.28, 0.02, 0.11, mat="paint_glossy_dark", bevel=0.006)
    inset(d, faces_where(d, lambda f: f.normal.y < -0.9), 0.012, -0.002, mat="emit_panel_cyan")
    d.rot(x=-35).move(x + 0.02, y - 0.11, z + 0.43)
    cyl(0.1, 0.025, 16, at=(x - 0.03, y + 0.08, z + 0.4), mat="chrome_scratched")
    for k in range(8):
        a = math.radians(k * 45)
        cyl(0.01, 0.045, 6, at=(x - 0.03 + 0.07 * math.cos(a), y + 0.08 + 0.07 * math.sin(a), z + 0.425), mat="glass", caps=False)


def _pipettes(x, y, z):
    cyl(0.06, 0.012, 16, at=(x, y, z), mat="chrome_scratched")
    cyl(0.008, 0.32, 8, at=(x, y, z + 0.012), mat="chrome_scratched")
    for k in range(3):
        a = math.radians(k * 120 + 30)
        px, py = x + 0.03 * math.cos(a), y + 0.03 * math.sin(a)
        cyl(0.011, 0.14, 8, at=(px, py, z + 0.12), mat="paint_glossy_white")
        cyl(0.004, 0.08, 6, at=(px, py, z + 0.04), r2=0.0015, mat="glass")
        cyl(0.013, 0.02, 8, at=(px, py, z + 0.26), mat="plastic_orange" if k == 1 else "tarp_blue")


def lab_bench(seed=1, W=2.4, D=0.9):
    rnd = random.Random(seed)
    var = 1 if seed >= 5 else 0
    # plinth with toe-kick floor wash
    box(W - 0.06, D - 0.2, 0.1, at=(0, 0.05, 0), mat="black", base=True)
    box(W - 0.16, 0.005, 0.007, at=(0, 0.05 - (D - 0.2) / 2 - 0.0025, 0.012), mat="emit_strip_cyan")
    # glossy white carcass, shadow-gap fronts with chrome pulls
    box(W, D - 0.06, 0.76, at=(0, 0.03, 0.1), mat="paint_glossy_white", base=True, bevel=0.012)
    yf = 0.03 - (D - 0.06) / 2
    box(W - 0.03, 0.004, 0.73, at=(0, yf - 0.001, 0.115), mat="black", base=True)
    cw = W / 3
    z0, z1 = 0.115, 0.845

    def front(x, za, w, h, pull=True):
        box(w - 0.006, 0.02, h - 0.006, at=(x, yf - 0.011, za + 0.003), mat="paint_glossy_white", base=True, bevel=0.004)
        if pull and detail():
            box(min(0.32, w * 0.5), 0.012, 0.01, at=(x, yf - 0.025, za + h - 0.032), mat="chrome_scratched", bevel=0.003)

    for c in range(3):
        x = -W / 2 + cw * (c + 0.5)
        if c == 1 and var == 0:  # sample refrigerator: dark window, status display, bar handle
            front(x, z0, cw, z1 - z0, pull=False)
            box(cw - 0.16, 0.006, 0.36, at=(x, yf - 0.022, 0.38), mat="glass_dark", base=True)
            box(cw - 0.14, 0.004, 0.004, at=(x, yf - 0.023, 0.376), mat="emit_strip_cyan")
            vquad(x - 0.12, 0.79, x + 0.02, 0.82, yf - 0.0215, "emit_panel_cyan")
            box(0.016, 0.022, 0.5, at=(x + cw / 2 - 0.06, yf - 0.032, 0.25), mat="chrome_scratched", base=True, bevel=0.004)
        elif c == 1:
            for s in (-1, 1):
                front(x + s * cw / 4, z0, cw / 2, z1 - z0, pull=False)
                box(0.014, 0.02, 0.24, at=(x + s * 0.035, yf - 0.03, 0.6), mat="chrome_scratched", base=True, bevel=0.004)
        else:
            hs = [0.29, 0.24, 0.2] if (c == 0) != bool(var) else [0.19, 0.18, 0.18, 0.18]
            za = z0
            for hh in hs:
                front(x, za, cw, hh)
                za += hh
    # epoxy worktop with LED under-lip
    box(W + 0.1, D + 0.1, 0.04, at=(0, 0, 0.86), mat="plastic_dark", base=True, bevel=0.006)
    box(W - 0.05, 0.008, 0.005, at=(0, -0.465, 0.8575), mat="emit_strip_cyan")
    # carbon service spine (sockets, status LEDs), uprights, top light bar
    box(W - 0.14, 0.05, 0.42, at=(0, 0.435, 0.9), mat="paint_glossy_dark", base=True, bevel=0.006)
    yb = 0.03 + (D - 0.06) / 2
    for c in range(3):
        x = -W / 2 + cw * (c + 0.5)
        hp = box(cw - 0.08, 0.012, 0.6, at=(x, yb + 0.004, 0.17), mat="paint_glossy_white", base=True, bevel=0.004)
        if detail():
            slots(x - 0.2, x + 0.2, 0.25, 0.4, 0.0, 5, "black", 0.01)
            for p in K.parts_since(K.part_count() - 5):
                p.mirror("y").move(0, yb + 0.0105, 0)
            bolts([(x - cw / 2 + 0.07, yb + 0.01, 0.21), (x + cw / 2 - 0.07, yb + 0.01, 0.73)], 0.007, 0.004)
    box(W - 0.34, 0.014, 0.06, at=(0, 0.403, 0.97), mat="metal_bare", base=True, bevel=0.003)
    for sx in (-1, 1):
        box(0.05, 0.05, 2.12 - 0.9, at=(sx * (W / 2 - 0.07), 0.435, 0.9), mat="paint_glossy_dark", base=True, bevel=0.006)
    lb = box(W - 0.09, 0.2, 0.05, at=(0, 0.36, 2.07), mat="paint_glossy_dark", base=True, bevel=0.008)
    inset(lb, faces_where(lb, lambda f: f.normal.z < -0.9), 0.03, -0.004, mat="emit_panel_white")
    box(W - 0.2, 0.004, 0.008, at=(0, 0.258, 2.095), mat="emit_strip_cyan")
    if detail():
        for k in range(6):
            sxk = -0.85 + k * 0.34
            box(0.07, 0.006, 0.04, at=(sxk, 0.394, 1.0), mat="black", bevel=0.002)
            vquad(sxk + 0.042, 0.995, sxk + 0.05, 1.003, 0.3955, "emit_green" if k % 3 else "emit_amber")
        for sx in (-1, 1):
            tube([(sx * 0.5, 0.41, 0.94), (sx * 0.62, 0.36, 0.905), (sx * 0.75, 0.3, 0.902)], 0.006, 5, mat="rubber")
    # frosted glass shelves on glossy brackets, chrome nosing, LED under each shelf
    for z in (1.42, 1.78):
        box(W - 0.2, 0.3, 0.014, at=(0, 0.27, z), mat="glass_frosted", base=True)
        box(W - 0.2, 0.012, 0.03, at=(0, 0.114, z - 0.008), mat="chrome_scratched", base=True, bevel=0.002)
        box(W - 0.26, 0.006, 0.004, at=(0, 0.13, z - 0.006), mat="emit_strip_cyan")
        for x in (-W / 2 + 0.35, 0.0, W / 2 - 0.35):
            box(0.02, 0.26, 0.05, at=(x, 0.29, z - 0.05), mat="metal_painted_white", base=True, bevel=0.004)
    # holographic display over the bench
    hx = -0.15 if var == 0 else 0.12
    holo_emitter(hx, -0.17, 0.9)
    hz, tilt = 1.2, -12
    with K.placed(M(hx, -0.06, hz, rx=tilt)):
        holo_panel(0.72, 0.36, seed=seed + 3, kind="lab" if var == 0 else "data")
    by = -0.06 - 0.18 * math.sin(math.radians(-tilt))
    bz = hz - 0.18 * math.cos(math.radians(tilt))
    light_sheet([(hx - 0.035, -0.17, 0.925), (hx + 0.035, -0.17, 0.925)], [(hx - 0.36, by, bz), (hx + 0.36, by, bz)])
    if not detail():
        return {"colliders": [K.collider_box((0, 0, 0.45), (W + 0.1, D + 0.1, 0.9))]}
    # equipment
    if var == 0:
        _microscope(-0.85, 0.02, 0.9)
        _centrifuge(0.72, 0.02, 0.9)
        _vial_rack(0.32, 0.25, 0.9, rnd)
        for (fx, fy, fh) in ((0.25, -0.25, 0.2), (0.4, -0.2, 0.15), (-0.55, -0.3, 0.24)):
            _flask((fx, fy, 0.9), fh)
        t = box(0.24, 0.17, 0.008, mat="black", bevel=0.003)
        inset(t, faces_where(t, lambda f: f.normal.z > 0.9), 0.012, -0.001, mat="emit_panel_cyan")
        t.rot(z=12).move(1.0, -0.28, 0.904)
        box(0.2, 0.14, 0.09, at=(1.02, 0.2, 0.9), mat="wood", base=True, bevel=0.004)
    else:
        _analyzer(-0.72, 0.1, 0.9)
        _pipettes(0.95, 0.22, 0.9)
        for k in range(4):
            cyl(0.045, 0.012, 16, at=(0.5, -0.22, 0.9 + k * 0.013), mat="glass")
        for (fx, fy, fh) in ((0.65, 0.05, 0.22), (0.78, -0.2, 0.16), (-0.35, -0.3, 0.18)):
            _flask((fx, fy, 0.9), fh)
    # shelf stock
    for z in (1.434, 1.794):
        x = -W / 2 + 0.2
        while x < W / 2 - 0.3:
            k = rnd.random()
            if k < 0.35:
                for j in range(rnd.randint(2, 3)):
                    _bottle(x + j * 0.07, 0.3 + rnd.uniform(-0.04, 0.04), z, rnd.uniform(0.025, 0.035), rnd.uniform(0.12, 0.2),
                            cap=rnd.choice(["plastic_dark", "plastic_orange", "tarp_blue"]))
                x += 0.07 * 4 + 0.05
            elif k < 0.65:
                bw = rnd.uniform(0.22, 0.32)
                bb = box(bw, 0.24, rnd.uniform(0.12, 0.2), at=(x + bw / 2, 0.29, z), mat=rnd.choice(["paint_glossy_white", "paint_glossy_dark"]), base=True, bevel=0.008)
                vquad(x + bw * 0.2, z + 0.04, x + bw * 0.6, z + 0.07, 0.169, "metal_painted_yellow")
                x += bw + 0.06
            elif k < 0.8:
                lathe([(0.06, 0), (0.065, 0.02), (0.065, 0.2), (0.04, 0.24), (0.04, 0.27), (0.001, 0.27)], 12, at=(x + 0.07, 0.29, z), mat="chrome_scratched", close_bottom=False)
                x += 0.2
            else:
                x += rnd.uniform(0.15, 0.35)
    return {"colliders": [K.collider_box((0, 0, 0.45), (W + 0.1, D + 0.1, 0.9))]}


# ============================================================================================== cryo pod
def cryo_pod(glowing=True):
    E = (lambda m: m) if glowing else (lambda m: "black")
    # stepped glossy pedestal: chrome trim, vent ring, LED floor wash, cyan top ring
    lathe([(0.001, 0.0), (0.88, 0.0), (0.88, 0.05), (0.865, 0.065), (0.865, 0.15), (0.835, 0.18), (0.79, 0.34), (0.745, 0.385),
           (0.7, 0.4), (0.001, 0.4)], 24, mat="paint_glossy_dark")
    torus(0.85, 0.009, n_major=32, n_minor=5, mat="chrome_scratched").move(0, 0, 0.163)
    torus(0.858, 0.006, n_major=32, n_minor=4, mat=E("emit_strip_cyan")).move(0, 0, 0.03)
    torus(0.66, 0.025, n_major=32, n_minor=5, mat=E("emit_cyan")).move(0, 0, 0.41)
    if detail():
        for k in range(20):
            if k in (0, 1, 19):  # leave the console bay (front, -Y) clear
                continue
            v = box(0.07, 0.012, 0.045, at=(0, -0.866, 0.108), mat="black")
            v.set_mat("black")
            v.rot(z=k * 18)
    # glass tube with frosted base band and chrome collars
    cyl(0.6, 2.0, 32, at=(0, 0, 0.4), mat="glass", caps=False)
    cyl(0.593, 0.26, 32, at=(0, 0, 0.4), mat="glass_frosted", caps=False)
    for zz in (0.42, 2.38):
        torus(0.606, 0.016, n_major=32, n_minor=4, mat="chrome_scratched").move(0, 0, zz)
    # cap: glossy shell, carbon band, chrome ring (metal_bare), inner LED halo
    lathe([(0.001, 2.4), (0.77, 2.4), (0.77, 2.47), (0.75, 2.49), (0.75, 2.56), (0.7, 2.62), (0.5, 2.7), (0.32, 2.74), (0.001, 2.76)], 24,
          mat="paint_glossy_dark")
    lathe([(0.756, 2.495), (0.756, 2.555)], 24, mat="carbon_panel", close_bottom=False, close_top=False)
    torus(0.62, 0.03, n_major=32, n_minor=5, mat="metal_bare").move(0, 0, 2.4)
    torus(0.5, 0.012, n_major=28, n_minor=4, mat=E("emit_cyan")).move(0, 0, 2.39)
    if detail():
        for k in range(8):
            a = math.radians(k * 45 + 22.5)
            cyl(0.014, 0.012, 8, at=(0.6 * math.cos(a), 0.6 * math.sin(a), 2.645), mat="chrome_scratched")
        lathe([(0.24, 2.745), (0.28, 2.744)], 20, mat="emit_strip_cyan" if glowing else "black", close_bottom=False, close_top=False)
    # three glossy-white struts (front stays open), LED inlays, chrome clamps
    for a in (0, 120, 240):
        n0 = K.part_count()
        box(0.1, 0.09, 1.96, at=(0, 0.66, 0.42), mat="paint_glossy_white", base=True, bevel=0.02, bseg=2)
        box(0.018, 0.006, 1.6, at=(0, 0.708, 0.6), mat=E("emit_strip_cyan"), base=True)
        for zz in (0.42, 2.32):
            box(0.13, 0.11, 0.06, at=(0, 0.655, zz), mat="chrome_scratched", base=True, bevel=0.008)
        for p in K.parts_since(n0):
            p.rot(z=a)
    # Aether column between chrome emitters (or the empty cradle)
    lathe([(0.001, 0.4), (0.42, 0.4), (0.42, 0.45), (0.36, 0.5), (0.3, 0.56), (0.001, 0.56)], 24, mat="chrome_scratched")
    lathe([(0.001, 2.0), (0.3, 2.0), (0.34, 2.06), (0.34, 2.4), (0.001, 2.4)], 24, mat="carbon_panel")
    torus(0.31, 0.008, n_major=24, n_minor=4, mat=E("emit_cyan")).move(0, 0, 2.0)
    if glowing:
        cyl(0.35, 1.4, 16, at=(0, 0, 0.6), mat="aether_energy")
        cyl(0.17, 1.44, 12, at=(0, 0, 0.56), mat="aether_energy")
    else:
        cyl(0.25, 0.04, 16, at=(0, 0, 0.56), mat="metal_bare")
        torus(0.2, 0.01, n_major=20, n_minor=4, mat="black").move(0, 0, 0.6)
    # front console with screen, buttons and a small hologram readout
    p = box(0.4, 0.07, 0.22, mat="paint_glossy_dark", bevel=0.012)
    inset(p, faces_where(p, lambda f: f.normal.y < -0.9), 0.03, -0.006, mat="screen")
    p.rot(x=-30).move(0, -0.83, 0.3)
    if detail():
        for k in range(4):
            b = box(0.03, 0.012, 0.014, at=(-0.075 + k * 0.05, -0.81, 0.165), mat=E("emit_cyan") if k != 3 else E("emit_amber"))
        if glowing:
            with K.placed(M(0, -0.84, 0.66, rx=-8)):
                holo_panel(0.46, 0.22, seed=31, kind="mini")
    # rear service spine, hoses and clamps
    box(0.18, 0.06, 1.7, at=(0, 0.74, 0.55), mat="carbon_panel", base=True, bevel=0.008)
    if detail():
        for zz in (0.8, 1.4, 2.0):
            cyl(0.03, 0.03, 10, at=(0, 0.77, zz), axis="Y", mat="metal_dark")
            cyl(0.008, 0.012, 6, at=(0, 0.8, zz), axis="Y", mat=E("emit_amber"))
        for x in (-0.25, 0.25):
            tube([(x, 0.55, 2.62), (x, 0.95, 2.5), (x, 1.0, 1.2), (x, 0.85, 0.25)], 0.035, 6, "rubber")
            for (yy, zz) in ((0.969, 2.0), (0.937, 0.8)):
                torus(0.042, 0.008, n_major=10, n_minor=4, mat="chrome_scratched").move(x, yy, zz)
    return {"colliders": [{"type": "capsule", "center": [0, 1.4, 0], "radius": 0.8, "height": 2.8, "direction": "Y"}]}


# ============================================================================================== desks / chairs
def terminal_desk(on=True):
    # glossy white top, LED under-lip, glossy slab legs with LED inlays, carbon modesty panel
    box(1.6, 0.8, 0.04, at=(0, 0, 0.72), mat="paint_glossy_white", base=True, bevel=0.008)
    box(1.5, 0.008, 0.005, at=(0, -0.37, 0.7175), mat="emit_strip_cyan")
    for sx in (-1, 1):
        x = sx * 0.76
        box(0.04, 0.7, 0.72, at=(x, 0, 0), mat="paint_glossy_dark", base=True, bevel=0.006)
        box(0.004, 0.012, 0.56, at=(x + sx * 0.0215, -0.27, 0.08), mat="emit_strip_cyan", base=True)
        box(0.05, 0.72, 0.012, at=(x, 0, 0), mat="metal_dark", base=True)
    box(1.48, 0.02, 0.4, at=(0, 0.3, 0.3), mat="carbon_panel", base=True, bevel=0.004)
    # monitor (screen rect unchanged), slim glossy shell with rear LED ring, chrome arm on a desk clamp
    m = box(0.64, 0.045, 0.4, mat="paint_glossy_dark", bevel=0.008)
    inset(m, faces_where(m, lambda f: f.normal.y < -0.9), 0.02, -0.005, mat="screen" if on else "glass_dark")
    m.rot(x=-6).move(0.1, 0.08, 1.15)
    rb = box(0.36, 0.04, 0.24, mat="paint_glossy_dark", bevel=0.012)
    rb.rot(x=-6).move(0.1, 0.12, 1.14)
    if detail():
        lp = box(0.3, 0.004, 0.006, mat="emit_strip_cyan")
        lp.rot(x=-6).move(0.1, 0.142, 1.03)
    box(0.25, 0.2, 0.012, at=(0.1, 0.12, 0.76), mat="metal_dark", base=True, bevel=0.004)
    cyl(0.022, 0.24, 12, at=(0.1, 0.16, 0.772), mat="chrome_scratched")
    beam((0.1, 0.16, 1.0), (0.1, 0.13, 1.08), 0.04, 0.03, mat="chrome_scratched")
    # keyboard with key caps + glow, mouse, PC tower
    box(0.45, 0.15, 0.016, at=(0.05, -0.18, 0.76), mat="plastic_dark", base=True, bevel=0.004)
    box(0.47, 0.17, 0.003, at=(0.05, -0.18, 0.7605), mat="emit_strip_blue", base=True)
    box(0.06, 0.1, 0.028, at=(0.42, -0.18, 0.76), mat="plastic_dark", base=True, bevel=0.012)
    box(0.18, 0.45, 0.45, at=(-0.56, 0.05, 0.02), mat="paint_glossy_dark", base=True, bevel=0.01)
    for (dy, dz, sy, sz) in ((0, -0.21, 0.45, 0.03), (0, 0.21, 0.45, 0.03), (-0.21, 0, 0.03, 0.45), (0.21, 0, 0.03, 0.45)):
        box(0.02, sy, sz, at=(-0.46, 0.05 + dy, 0.245 + dz), mat="paint_glossy_dark", bevel=0.004)
    if detail():
        for r in range(4):
            for c in range(13):
                if r == 0 and 4 <= c <= 8:
                    if c == 6:
                        box(0.15, 0.024, 0.008, at=(0.05, -0.236, 0.776), mat="black", base=True)
                    continue
                box(0.026, 0.024, 0.008, at=(-0.155 + c * 0.0317, -0.236 + r * 0.033, 0.776), mat="black", base=True)
        box(0.004, 0.42, 0.42, at=(-0.452, 0.05, 0.035), mat="glass", base=True)
        for yy, zz in ((0.12, 0.15), (0.12, 0.33), (-0.06, 0.33)):
            torus(0.058, 0.007, n_major=16, n_minor=4, mat="emit_cyan").rot(y=90).move(-0.466, yy, zz)
            cyl(0.02, 0.006, 8, at=(-0.472, yy, zz), axis="X", mat="black")
        box(0.01, 0.12, 0.08, at=(-0.47, -0.08, 0.12), mat="emit_strip_blue")
        box(0.01, 0.002, 0.1, at=(-0.55, -0.176, 0.35), mat="emit_green", base=True)
        box(0.004, 0.003, 0.36, at=(-0.47, -0.176, 0.06), mat="emit_strip_cyan", base=True)
        # coffee cup + tablet
        lathe([(0.001, 0.0), (0.03, 0.0), (0.04, 0.09), (0.036, 0.09), (0.026, 0.006), (0.001, 0.006)], 14, at=(0.62, 0.05, 0.76), mat="metal_painted_white")
        t = box(0.2, 0.14, 0.008, mat="black", bevel=0.003)
        inset(t, faces_where(t, lambda f: f.normal.z > 0.9), 0.01, -0.001, mat="emit_panel_cyan")
        t.rot(z=-14).move(0.58, -0.2, 0.764)
        tube([(0.1, 0.17, 0.95), (0.1, 0.3, 0.8), (0.12, 0.38, 0.76), (0.2, 0.38, 0.3)], 0.006, 5, mat="rubber")
    # side hologram over the desk
    holo_emitter(-0.5, 0.15, 0.76, 0.05)
    hm = M(-0.52, 0.1, 1.04, rx=-8, rz=18)
    with K.placed(hm):
        holo_panel(0.42, 0.28, seed=17, kind="data")
    light_sheet([(-0.53, 0.15, 0.782), (-0.47, 0.15, 0.782)], [pt(hm, (-0.21, 0, -0.14)), pt(hm, (0.21, 0, -0.14))])
    return {"colliders": [K.collider_box((0, 0, 0.38), (1.6, 0.8, 0.76))],
            "screen": {"center": K.to_unity_vec((0.1, 0.055, 1.15)), "size": [0.6, 0.36], "normal": [0, 0, 1], "material": "screen"}}


def office_chair():
    # chrome five-star base (layout unchanged) with caster forks and twin-wheel casters
    for i in range(5):
        a = i * 72
        b = beam((0, 0, 0.085), (0.29, 0, 0.065), 0.042, 0.03, mat="chrome_scratched", bevel=0.008)
        b.rot(z=a)
        c = cyl(0.03, 0.03, 10, at=(0.3, 0, 0.0), axis="Y", center=True, mat="rubber")
        c.move(0, 0, 0.03).rot(z=a)
        if detail():
            f = box(0.024, 0.036, 0.022, at=(0.296, 0, 0.05), mat="black", bevel=0.004)
            f.rot(z=a)
    cyl(0.05, 0.05, 16, at=(0, 0, 0.065), mat="black")
    cyl(0.026, 0.33, 12, at=(0, 0, 0.1), mat="metal_bare")
    cyl(0.036, 0.13, 12, at=(0, 0, 0.1), mat="plastic_dark")
    box(0.18, 0.2, 0.04, at=(0, 0.02, 0.4), mat="black", base=True, bevel=0.006)
    # seat: carbon shell, padded cushion with bolsters and stitch grooves
    box(0.44, 0.44, 0.035, at=(0, 0, 0.425), mat="carbon_panel", base=True, bevel=0.01)
    box(0.36, 0.44, 0.06, at=(0, -0.005, 0.455), mat="rubber", base=True, bevel=0.025, bseg=2)
    for sx in (-1, 1):
        box(0.06, 0.44, 0.08, at=(sx * 0.195, -0.005, 0.45), mat="rubber", base=True, bevel=0.025, bseg=2)
    if detail():
        for sx in (-1, 1):
            box(0.006, 0.38, 0.004, at=(sx * 0.07, -0.01, 0.513), mat="black")
    # arm rests (inside the base footprint)
    for sx in (-1, 1):
        beam((sx * 0.2, 0.0, 0.44), (sx * 0.245, 0.0, 0.64), 0.03, 0.05, mat="chrome_scratched")
        box(0.045, 0.22, 0.03, at=(sx * 0.245, 0.0, 0.64), mat="rubber", base=True, bevel=0.012)
    # back: glossy shell, padded front with channels, headrest, cyan accent strips
    n0 = K.part_count()
    shell = [(-0.17, -0.25), (0.17, -0.25), (0.212, -0.1), (0.224, 0.12), (0.2, 0.235), (0.1, 0.258), (-0.1, 0.258), (-0.2, 0.235),
             (-0.224, 0.12), (-0.212, -0.1)]
    extrude(shell, 0.035, plane="XZ", at=(0, 0.025, 0.0), mat="paint_glossy_dark", bevel=0.01)
    pad = [(-0.15, -0.235), (0.15, -0.235), (0.188, -0.1), (0.196, 0.11), (0.17, 0.19), (-0.17, 0.19), (-0.196, 0.11), (-0.188, -0.1)]
    extrude(pad, 0.04, plane="XZ", at=(0, -0.012, 0.0), mat="rubber", bevel=0.014, bseg=2)
    box(0.26, 0.04, 0.1, at=(0, -0.005, 0.24), mat="rubber", bevel=0.02, bseg=2)
    for sx in (-1, 1):
        beam((sx * 0.214, 0.02, -0.09), (sx * 0.226, 0.02, 0.12), 0.006, 0.006, mat="emit_strip_cyan")
    if detail():
        for sx in (-1, 1):
            box(0.006, 0.004, 0.36, at=(sx * 0.065, -0.033, -0.03), mat="black")
        box(0.12, 0.004, 0.03, at=(0, 0.044, 0.12), mat="chrome_scratched")
    for p in K.parts_since(n0):
        p.rot(x=-8).move(0, 0.238, 0.778)
    beam((0, 0.18, 0.44), (0, 0.27, 0.6), 0.05, 0.03, mat="plastic_dark")
    return {"colliders": [K.collider_box((0, 0, 0.5), (0.62, 0.62, 1.0))]}


def glass_partition(L=2.5, H=3.0):
    # glossy rails and mullion (Unity +X end), chrome shoes
    box(L, 0.08, 0.08, at=(0, 0, 0), mat="paint_glossy_dark", base=True, bevel=0.006)
    box(L, 0.08, 0.08, at=(0, 0, H - 0.08), mat="paint_glossy_dark", base=True, bevel=0.006)
    box(0.07, 0.08, H - 0.16, at=(-L / 2 + 0.035, 0, 0.08), mat="paint_glossy_dark", base=True, bevel=0.006)
    gx0 = -L / 2 + 0.07
    gw, gc = L / 2 - gx0, (gx0 + L / 2) / 2
    # glazing: clear / frosted privacy band / clear
    box(gw, 0.012, 0.9, at=(gc, 0, 0.08), mat="glass", base=True)
    box(gw, 0.012, 0.66, at=(gc, 0, 0.98), mat="glass_frosted", base=True)
    box(gw, 0.012, H - 0.16 - 1.56, at=(gc, 0, 1.64), mat="glass", base=True)
    # LED wash lines on the rails either side of the glass
    for sy in (-1, 1):
        for zz in (0.083, H - 0.083):
            box(gw - 0.02, 0.006, 0.006, at=(gc, sy * 0.022, zz), mat="emit_strip_cyan")
    if detail():
        # manifestation dashes (frosted) and chrome patch fittings
        for sy in (-1, 1):
            k = 0
            x = gx0 + 0.08
            while x < L / 2 - 0.1:
                wd = 0.05 if k % 5 else 0.14
                vquad(x, 1.7, x + wd, 1.73, sy * 0.0065, "glass_frosted")
                x += wd + 0.03
                k += 1
        for x in (gx0 + 0.04, L / 2 - 0.04):
            for zz in (0.95, 1.67):
                box(0.03, 0.022, 0.06, at=(x, 0, zz), mat="chrome_scratched", bevel=0.004)
        box(0.012, 0.03, 0.6, at=(L / 2 - 0.012, 0, 1.2), mat="metal_painted_white", base=True, bevel=0.003)
        for x in (gx0 + 0.2, L / 2 - 0.2):
            box(0.12, 0.03, 0.03, at=(x, 0, 0.08), mat="metal_dark", base=True)
    return {"colliders": [K.collider_box((0, 0, H / 2), (L, 0.1, H))]}


def ceiling_light(L=1.6, W=0.6, mat="emit_panel_white", halo="emit_strip_cyan"):
    """Recessed ceiling luminaire; pivot = ceiling surface (top centre). Every glowing part is on an emit_* slot
    (the zone code switches all of them for flicker / power loss)."""
    box(L, W, 0.012, at=(0, 0, -0.012), mat="paint_glossy_white", base=True, bevel=0.003)
    f = box(L - 0.04, W - 0.04, 0.048, at=(0, 0, -0.06), mat="metal_dark", base=True, bevel=0.004)
    inset(f, faces_where(f, lambda q: q.normal.z < -0.9), 0.045, -0.008, mat=mat)
    # halo LED frame around the diffuser
    for sy in (-1, 1):
        box(L - 0.1, 0.008, 0.003, at=(0, sy * (W / 2 - 0.042), -0.0585), mat=halo)
    for sx in (-1, 1):
        box(0.008, W - 0.092, 0.003, at=(sx * (L / 2 - 0.042), 0, -0.0585), mat=halo)
    if detail():
        for k in range(7):
            x = -L / 2 + 0.1 + (L - 0.2) * (k + 0.5) / 7
            box(0.012, W - 0.13, 0.008, at=(x, 0, -0.056), mat="chrome_scratched")
        for sx in (-1, 1):
            for sy in (-1, 1):
                cyl(0.006, 0.003, 6, at=(sx * (L / 2 - 0.018), sy * (W / 2 - 0.018), -0.0135), mat="chrome_scratched")
    return {"colliders": "none", "light": K.to_unity_vec((0, 0, -0.2))}


def reception_desk(L=7.0):
    """Lobby counter: visitor face toward -Y (Unity +Z), staff side +Y with a lower work surface."""
    # toe-kick with floor wash
    box(L - 0.2, 1.4, 0.1, at=(0, 0.05, 0), mat="black", base=True)
    box(L - 0.3, 0.006, 0.008, at=(0, -0.653, 0.012), mat="emit_strip_cyan")
    # high counter: raked glossy-white front, dark glossy transaction top with chrome nosing
    extrude([(-0.7, 0.1), (-0.1, 0.1), (-0.1, 1.08), (-0.8, 1.08)], L, plane="YZ", mat="paint_glossy_white", bevel=0.012)
    box(L + 0.2, 0.9, 0.06, at=(0, -0.45, 1.08), mat="paint_glossy_dark", base=True, bevel=0.01)
    box(L + 0.16, 0.012, 0.02, at=(0, -0.894, 1.11), mat="chrome_scratched", bevel=0.003)
    box(L - 0.2, 0.01, 0.006, at=(0, -0.81, 1.074), mat="emit_strip_cyan")
    # staff side: low cabinets (lab_panel doors), work surface, counter brackets
    lo = box(L, 0.9, 0.72, at=(0, 0.35, 0.0), mat="metal_painted", base=True, bevel=0.01)
    inset(lo, faces_where(lo, lambda f: f.normal.y > 0.9), 0.06, -0.012, mat="lab_panel")
    box(L, 1.0, 0.04, at=(0, 0.4, 0.72), mat="metal_painted_white", base=True, bevel=0.005)
    box(L - 0.4, 0.01, 0.006, at=(0, 0.905, 0.716), mat="emit_strip_cyan")
    # raked front: vertical LED seams + carbon base band
    sl = math.atan2(0.1, 0.98)
    ny, nz = -math.cos(sl), -math.sin(sl)
    for k in range(8):
        x = -L / 2 + 0.5 + k * (L - 1.0) / 7
        if abs(x) < 0.8:
            continue
        yface = lambda z: -0.7 - 0.1 * (z - 0.1) / 0.98
        beam((x, yface(0.32) + ny * 0.003, 0.32 + nz * 0.003), (x, yface(1.06) + ny * 0.003, 1.06 + nz * 0.003), 0.006, 0.014, mat="emit_strip_cyan")
    with K.placed(M(0, -0.7, 0.1, rx=math.degrees(sl))):
        box(L - 0.04, 0.012, 0.2, at=(0, -0.004, 0.0), mat="carbon_panel", base=True)
        box(L - 0.06, 0.006, 0.006, at=(0, -0.012, 0.205), mat="chrome_scratched")
        # backlit emblem in the middle of the counter front
        box(1.3, 0.01, 0.56, at=(0, -0.006, 0.27), mat="paint_glossy_dark", base=True, bevel=0.004)
        box(1.24, 0.006, 0.5, at=(0, -0.012, 0.3), mat="emit_panel_cyan", base=True)
        with K.placed(M(0, 0, 0.55)):
            corp_symbol(0.4, 0.02, y=-0.03, mat="chrome_scratched", bevel=0.002)
    if detail():
        for k in range(4):
            x = -L / 2 + 0.6 + k * (L - 1.2) / 3
            box(0.04, 0.3, 0.2, at=(x, -0.05, 0.88), mat="metal_bare", base=True)
        # staff workstations: monitors facing the staff, keyboards
        for x in (-1.0, 0.45):
            mo = box(0.56, 0.03, 0.32, at=(x, 0.0, 0.0), mat="paint_glossy_dark", bevel=0.008)
            inset(mo, faces_where(mo, lambda f: f.normal.y > 0.9), 0.018, -0.004, mat="screen")
            mo.rot(x=8).move(x, 0.12, 0.96)
            box(0.16, 0.12, 0.012, at=(x, 0.06, 0.76), mat="chrome_scratched", base=True, bevel=0.003)
            cyl(0.015, 0.06, 8, at=(x, 0.06, 0.772), mat="chrome_scratched")
            box(0.42, 0.14, 0.014, at=(x, 0.4, 0.76), mat="plastic_dark", base=True, bevel=0.004)
            box(0.44, 0.16, 0.003, at=(x, 0.4, 0.7602), mat="emit_strip_blue", base=True)
    return {"colliders": [K.collider_box((0, 0, 0.56), (L + 0.2, 1.8, 1.12))]}


def shelving(W=2.0, D=0.6, H=2.2, seed=4):
    rnd = random.Random(seed)
    fl = Flat("black")
    # glossy uprights with levelling feet and perforation slots
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (W / 2 - 0.0225), sy * (D / 2 - 0.0225)
            box(0.045, 0.045, H - 0.02, at=(x, y, 0.02), mat="paint_glossy_dark", base=True, bevel=0.004)
            cyl(0.014, 0.02, 8, at=(x, y, 0.0), mat="chrome_scratched")
            if detail() and sy < 0:
                for k in range(40):
                    zz = 0.08 + k * 0.052
                    vquad(x - 0.006, zz, x + 0.006, zz + 0.022, y - 0.0231, "black", fl)
    # back X-bracing
    if detail():
        for (z0, z1) in ((0.12, 1.12), (1.12, 2.12)):
            for s in (-1, 1):
                beam((-W / 2 + 0.05, D / 2 + 0.004, z0 if s > 0 else z1), (W / 2 - 0.05, D / 2 + 0.004, z1 if s > 0 else z0), 0.025, 0.008, mat="metal_dark", up=(0, 1, 0))
    for sx in (-1, 1):
        box(0.03, 0.03, 0.05, at=(sx * (W / 2 - 0.0225), D / 2 + 0.015, H - 0.12), mat="metal_dark", base=True)
    for k in range(5):
        z = 0.1 + k * (H - 0.2) / 4
        box(W - 0.02, D - 0.02, 0.025, at=(0, 0, z), mat="metal_painted", base=True, bevel=0.004)
        box(W - 0.06, 0.02, 0.05, at=(0, -D / 2 - 0.01, z - 0.012), mat="chrome_scratched", base=True, bevel=0.003)
        box(W - 0.12, 0.008, 0.032, at=(0, -D / 2 - 0.024, z - 0.003), mat="black", base=True)
        box(W - 0.12, 0.004, 0.006, at=(0, -D / 2 - 0.0295, z), mat="emit_strip_cyan")
        if detail() and k < 4:
            for j in range(4):
                xl = -W / 2 + 0.2 + j * 0.5 + rnd.uniform(-0.05, 0.05)
                vquad(xl, z + 0.005, xl + 0.07, z + 0.022, -D / 2 - 0.0285, "metal_painted_yellow", fl)
            x = -W / 2 + 0.08
            while x < W / 2 - 0.36:
                w = min(rnd.uniform(0.22, 0.45), W / 2 - 0.06 - x)
                r = rnd.random()
                zz = z + 0.025
                if r < 0.4:  # hard case with chrome latches
                    hh = rnd.uniform(0.12, 0.24)
                    m = rnd.choice(["paint_glossy_white", "paint_glossy_dark", "plastic_orange", "metal_painted_yellow", "metal_painted_green"])
                    box(w - 0.04, D * 0.72, hh, at=(x + w / 2, -0.02, zz), mat=m, base=True, bevel=0.015, bseg=2)
                    for dx in (-0.25, 0.25):
                        box(0.03, 0.01, 0.025, at=(x + w / 2 + dx * (w - 0.04), -0.02 - D * 0.36 - 0.004, zz + hh * 0.7), mat="chrome_scratched")
                    box(0.1, 0.02, 0.012, at=(x + w / 2, -0.02, zz + hh + 0.006), mat="plastic_dark")
                elif r < 0.6:  # stacked data cartridges
                    for j in range(rnd.randint(4, 8)):
                        box(0.025, 0.12, 0.1, at=(x + 0.02 + j * 0.03, -0.12, zz), mat="plastic_dark", base=True)
                        vquad(x + 0.012 + j * 0.03, zz + 0.07, x + 0.028 + j * 0.03, zz + 0.085, -0.1805, "paint_glossy_white", fl)
                    w = 0.3
                elif r < 0.72:  # canisters
                    for j in range(2):
                        lathe([(0.001, 0), (0.06, 0), (0.065, 0.02), (0.065, 0.24), (0.04, 0.28), (0.04, 0.3), (0.001, 0.3)], 14,
                              at=(x + 0.07 + j * 0.14, 0.05, zz), mat="chrome_scratched")
                    w = 0.3
                elif r < 0.82:  # coiled cable + tarp bundle
                    torus(0.09, 0.016, n_major=16, n_minor=6, mat="rubber").move(x + 0.11, -0.05, zz + 0.016)
                    box(0.2, 0.3, 0.12, at=(x + 0.12, 0.1, zz), mat="tarp", base=True, bevel=0.03, bseg=2)
                    w = 0.26
                elif r < 0.9:
                    box(w - 0.06, D * 0.6, 0.2, at=(x + w / 2, 0.0, zz), mat="wood", base=True, bevel=0.006)
                x += w
    return {"colliders": [K.collider_box((0, 0, H / 2), (W, D, H))]}


# ============================================================================================== new corporate assets
def holo_display_wall(w=2.2, h=1.2, zc=1.75):
    """Wall-mounted holo projector. Pivot = wall plane at floor level (y=0, z=0); everything in front (-Y)."""
    # carbon backplate with glossy inner field and LED seams
    bp = box(w + 0.5, 0.05, h + 0.6, at=(0, -0.025, zc), mat="paint_glossy_dark", bevel=0.01)
    inset(bp, faces_where(bp, lambda f: f.normal.y < -0.9), 0.05, -0.006, mat="glass_dark")
    for sx in (-1, 1):
        box(0.01, 0.006, h + 0.4, at=(sx * (w / 2 + 0.2), -0.052, zc), mat="emit_strip_blue")
    # projector heads (sleek wedge extrusions) top and bottom
    zt, zb = zc + h / 2 + 0.16, zc - h / 2 - 0.2
    top = [(0.0, -0.06), (-0.3, -0.06), (-0.46, -0.01), (-0.46, 0.03), (-0.3, 0.08), (0.0, 0.1)]
    extrude(top, w + 0.3, plane="YZ", at=(0, 0, zt), mat="paint_glossy_dark", bevel=0.01)
    bot = [(0.0, -0.08), (-0.26, -0.06), (-0.36, -0.02), (-0.36, 0.02), (-0.2, 0.05), (0.0, 0.05)]
    extrude(bot, w + 0.1, plane="YZ", at=(0, 0, zb), mat="paint_glossy_dark", bevel=0.01)
    box(w + 0.1, 0.03, 0.008, at=(0, -0.43, zt - 0.03), mat="glass_dark")
    box(w + 0.08, 0.012, 0.006, at=(0, -0.44, zt - 0.036), mat="emit_strip_cyan")
    box(w, 0.012, 0.006, at=(0, -0.33, zb + 0.026), mat="emit_strip_cyan")
    box(w + 0.32, 0.4, 0.012, at=(0, -0.24, zt + 0.02), mat="chrome_scratched", base=True)
    for sx in (-1, 1):
        box(0.02, 0.47, 0.17, at=(sx * (w / 2 + 0.16), -0.235, zt - 0.06), mat="chrome_scratched", base=True, bevel=0.004)
        box(0.02, 0.37, 0.14, at=(sx * (w / 2 + 0.06), -0.185, zb - 0.08), mat="chrome_scratched", base=True, bevel=0.004)
    if detail():
        slots(-w / 2, w / 2, zt + 0.04, zt + 0.07, -0.3, 1, "black", 0.012)
        for x in (-w / 2 + 0.2, w / 2 - 0.2):
            cyl(0.02, 0.01, 12, at=(x, -0.465, zt + 0.0), axis="Y", mat="emit_cyan")
        bolts([(sx * (w / 2 + 0.2), -0.056, zc + sz * (h / 2 + 0.24)) for sx in (-1, 1) for sz in (-1, 1)], 0.012, 0.006)
    # floating hologram + projection curtains
    yh = -0.3
    hm = M(0, yh, zc, rx=-3)
    with K.placed(hm):
        holo_panel(w, h, seed=41, kind="dash")
    light_sheet([(-w / 2 - 0.05, -0.43, zt - 0.04), (w / 2 + 0.05, -0.43, zt - 0.04)], [pt(hm, (-w / 2, 0, h / 2)), pt(hm, (w / 2, 0, h / 2))])
    light_sheet([pt(hm, (-w / 2, 0, -h / 2)), pt(hm, (w / 2, 0, -h / 2))], [(-w / 2, -0.33, zb + 0.03), (w / 2, -0.33, zb + 0.03)])
    return {"colliders": [K.collider_box((0, -0.03, zc), (w + 0.5, 0.06, h + 0.6)),
                          K.collider_box((0, -0.23, zt), (w + 0.3, 0.46, 0.16)), K.collider_box((0, -0.18, zb), (w + 0.1, 0.36, 0.13))],
            "screen": {"center": K.to_unity_vec((0, yh, zc)), "size": [w, h], "normal": [0, 0, 1], "material": "holo_cyan"},
            "light": K.to_unity_vec((0, -0.9, zc))}


def holo_table(R=0.9, H=0.95, seed=8):
    """Round holo table with a floating city-map hologram. Pivot base-centre."""
    rnd = random.Random(seed)
    lathe([(0.001, 0.0), (0.56, 0.0), (0.56, 0.035), (0.52, 0.07), (0.3, 0.12), (0.24, 0.16), (0.001, 0.16)], 28, mat="paint_glossy_dark")
    torus(0.545, 0.006, n_major=32, n_minor=4, mat="emit_strip_cyan").move(0, 0, 0.04)
    cyl(0.2, 0.62, 24, at=(0, 0, 0.16), mat="carbon_panel")
    for zz in (0.2, 0.74):
        torus(0.205, 0.012, n_major=20, n_minor=4, mat="chrome_scratched").move(0, 0, zz)
    for k in range(4):
        s = box(0.012, 0.006, 0.44, at=(0, -0.203, 0.25), mat="emit_strip_cyan", base=True)
        s.rot(z=45 + k * 90)
    # under-bowl, glossy white rim ring, glass projector bed with emissive rings
    lathe([(0.2, 0.76), (0.4, 0.78), (0.75, 0.85), (0.86, 0.87), (0.001, 0.87)], 32, mat="paint_glossy_dark", close_bottom=False)
    lathe([(0.76, 0.86), (R - 0.02, 0.86), (R, 0.88), (R, 0.93), (R - 0.02, H), (0.76, H), (0.76, 0.86)], 36, mat="paint_glossy_white",
          close_bottom=False, close_top=False)
    lathe([(R + 0.001, 0.895), (R + 0.001, 0.915)], 48, mat="emit_strip_cyan", close_bottom=False, close_top=False)
    cyl(0.76, 0.06, 48, at=(0, 0, 0.875), mat="glass_dark")
    for r in (0.72, 0.5, 0.26):
        torus(r, 0.004, n_major=32 if r > 0.4 else 20, n_minor=4, mat="emit_cyan").move(0, 0, 0.936)
    if detail():
        for k in range(12):
            a = math.radians(k * 30)
            b = box(0.05, 0.012, 0.004, at=(0.83 * math.cos(a), 0.83 * math.sin(a), H + 0.001), mat="chrome_scratched")
            b.rot_about((0.83 * math.cos(a), 0.83 * math.sin(a), H), z=k * 30 + 90)
    # hologram: projection band, map ground grid, city blocks, route, target marker, scan ring
    z0 = 1.02
    cyl(0.72, 0.08, 48, at=(0, 0, 0.94), r2=0.7, mat="holo_cyan", caps=False)
    torus(0.7, 0.004, n_major=40, n_minor=3, mat="holo_cyan").move(0, 0, z0)
    fl = Flat("holo_cyan")
    rr = 0.68
    sp = 0.12
    for i in range(-5, 6):
        c = i * sp
        half = math.sqrt(max(0.0, rr * rr - c * c))
        if half < 0.05:
            continue
        hquad(c - 0.003, -half, c + 0.003, half, z0, "holo_cyan", fl)
        hquad(-half, c - 0.003, half, c + 0.003, z0, "holo_cyan", fl)
    for i in range(-6, 6):
        for j in range(-6, 6):
            for (di, dj) in ((0.0, 0.0), (0.5, 0.0), (0.0, 0.5), (0.5, 0.5)):
                if rnd.random() < 0.5:
                    continue
                x = (i + 0.27 + di * 0.95) * sp * 1.0
                y = (j + 0.27 + dj * 0.95) * sp * 1.0
                d = math.hypot(x, y)
                if d > rr - 0.05:
                    continue
                hgt = (0.03 + rnd.random() ** 2.2 * 0.32) * (1.15 - d / rr)
                if K.LOD and hgt < 0.08:
                    continue
                open_box(fl, x, y, z0 + 0.002, 0.045, 0.045, hgt, "holo_magenta" if rnd.random() < 0.04 else "holo_cyan")
    if detail():
        route = [(-0.6, -0.12), (-0.24, -0.12), (-0.24, 0.24), (0.12, 0.24), (0.12, 0.48)]
        for a, b in zip(route, route[1:]):
            beam((a[0], a[1], z0 + 0.01), (b[0], b[1], z0 + 0.01), 0.012, 0.004, mat="holo_magenta")
        cyl(0.035, 0.07, 10, at=(0.12, 0.48, z0 + 0.4), r2=0.0, mat="holo_magenta").rot_about((0.12, 0.48, z0 + 0.435), x=180)
        cyl(0.003, 0.36, 6, at=(0.12, 0.48, z0), mat="holo_magenta")
        torus(0.06, 0.003, n_major=16, n_minor=4, mat="holo_magenta").move(0.12, 0.48, z0 + 0.005)
        torus(0.69, 0.0025, n_major=40, n_minor=3, mat="holo_cyan").move(0, 0, z0 + 0.22)
        for k, (tx, ty, tz) in enumerate(((-0.3, -0.2, 1.36), (0.28, 0.1, 1.4), (-0.05, 0.38, 1.3))):
            with K.placed(M(tx, ty, tz, rz=-30 + k * 25)):
                vquad(-0.06, -0.045, 0.06, -0.04, 0.0, "holo_cyan")
                glyph(random.Random(60 + k), -0.025, 0.0, 0.05, 0.0, "holo_cyan")
                glyph(random.Random(70 + k), 0.03, 0.0, 0.05, 0.0, "holo_cyan")
                beam((-0.06, 0.0, -0.045), (-0.06, 0.0, -0.25), 0.003, 0.003, mat="holo_cyan")
    return {"colliders": [K.collider_box((0, 0, H / 2), (1.6, 1.6, H))], "light": K.to_unity_vec((0, 0, 1.25))}


def corp_wall_panel(L=4.0, H=4.0, T=0.3):
    """Corporate cladding wall module (Wall_* grid: length X centred, 0.3 thick centred on y=0, 4 m tall).
    Both faces: carbon dado, glossy white field in a 1 m grid with shadow gaps, LED seams at x=+-1 (2 m rhythm when
    chained), cyan dado line and ceiling cove, dark soffit band."""
    box(L, T - 0.04, H, mat="concrete_dark", base=True)
    for side in (-1, 1):
        n0 = K.part_count()
        yo = -T / 2  # build the front (-Y) face, mirror for the back
        box(L, 0.004, H, at=(0, yo + 0.018, 0), mat="black", base=True)
        box(L, 0.022, 0.12, at=(0, yo + 0.011, 0), mat="black", base=True)
        box(L, 0.004, 0.012, at=(0, yo - 0.001, 0.115), mat="chrome_scratched")
        for (x0, x1) in ((-L / 2, -1.0), (-1.0, 1.0), (1.0, L / 2)):
            g0 = 0.005 if x0 == -L / 2 else 0.012
            g1 = 0.005 if x1 == L / 2 else 0.012
            box(x1 - x0 - g0 - g1, 0.016, 0.86, at=((x0 + g0 + x1 - g1) / 2, yo + 0.008, 0.13), mat="paint_glossy_dark", base=True, bevel=0.003)
            if detail():
                slots(x0 + g0 + 0.02, x1 - g1 - 0.02, 0.2, 0.92, yo - 0.0004, 9, "black", 0.006)
            box(x1 - x0 - g0 - g1 - 0.1, 0.004, 0.08, at=((x0 + g0 + x1 - g1) / 2, yo - 0.001, 0.86), mat="carbon_panel", base=True)
        box(L, 0.006, 0.014, at=(0, yo + 0.009, 1.003), mat="emit_strip_cyan", base=True)
        for (z0, z1) in ((1.02, 2.2), (2.2, 3.38)):
            for (x0, x1) in ((-2.0, -1.0), (-1.0, 0.0), (0.0, 1.0), (1.0, 2.0)):
                g0 = 0.004 if x0 == -2.0 else (0.012 if abs(x0) == 1.0 else 0.005)
                g1 = 0.004 if x1 == 2.0 else (0.012 if abs(x1) == 1.0 else 0.005)
                box(x1 - x0 - g0 - g1, 0.016, z1 - z0 - 0.01, at=((x0 + g0 + x1 - g1) / 2, yo + 0.008, z0 + 0.005), mat="paint_glossy_white", base=True, bevel=0.003)
                if detail():
                    bolts([(x, yo - 0.004, z) for x in (x0 + g0 + 0.04, x1 - g1 - 0.04) for z in (z0 + 0.045, z1 - 0.045)], 0.006, 0.004)
        for x in (-1.0, 1.0):
            box(0.008, 0.006, 2.36, at=(x, yo + 0.012, 1.02), mat="emit_strip_blue", base=True)
        box(L, 0.04, 0.03, at=(0, yo + 0.02, 3.38), mat="paint_glossy_dark", base=True, bevel=0.004)
        box(L, 0.006, 0.01, at=(0, yo + 0.035, 3.37), mat="emit_strip_cyan")
        sb = box(L, 0.02, 0.59, at=(0, yo + 0.01, 3.41), mat="paint_glossy_dark", base=True, bevel=0.003)
        if detail():
            for x in (-1.5, -0.5, 0.5, 1.5):
                slots(x - 0.3, x + 0.3, 3.55, 3.85, yo - 0.0005, 5, "black", 0.012)
        if side > 0:
            for p in K.parts_since(n0):
                p.mirror("y")
    return {"colliders": [K.collider_box((0, 0, H / 2), (L, T, H))]}


def corp_logo_frame(w=3.2, h=1.6, d=0.16):
    """Backlit lobby emblem frame. Pivot = back centre (wall plane, vertical centre); face -Y."""
    # glossy frame, black back tray, backlight, LED lip
    for sz in (-1, 1):
        box(w, d, 0.1, at=(0, -d / 2, sz * (h / 2 - 0.05)), mat="paint_glossy_dark", bevel=0.01)
    for sx in (-1, 1):
        box(0.1, d, h - 0.2, at=(sx * (w / 2 - 0.05), -d / 2, 0), mat="paint_glossy_dark", bevel=0.01)
    box(w - 0.2, 0.04, h - 0.2, at=(0, -0.02, 0), mat="black")
    box(w - 0.24, 0.01, h - 0.24, at=(0, -0.045, 0), mat="emit_panel_white")
    for sz in (-1, 1):
        box(w - 0.2, 0.006, 0.008, at=(0, -d - 0.002, sz * (h / 2 - 0.1)), mat="emit_strip_cyan")
    for sx in (-1, 1):
        box(0.008, 0.006, h - 0.2, at=(sx * (w / 2 - 0.1), -d - 0.002, 0), mat="emit_strip_cyan")
    # chrome emblem standing off the light box (halo-lit silhouette) + invented glyph line
    with K.placed(M(0, 0, 0.07)):
        corp_symbol(0.95, 0.035, y=-0.1, mat="chrome_scratched", bevel=0.003)
        for a in (150, 270, 30, None):
            x, z = (0.0, 0.1) if a is None else (0.41 * math.cos(math.radians(a)), 0.41 * math.sin(math.radians(a)))
            cyl(0.01, 0.06, 8, at=(x, -0.085, z), axis="Y", mat="chrome_scratched")
    if detail():
        glyph_row(random.Random(77), -0.4125, -0.62, 0.11, 6, y=-0.07, mat="paint_glossy_dark", depth=0.012)
        bolts([(sx * (w / 2 - 0.05), -d - 0.005, sz * (h / 2 - 0.05)) for sx in (-1, 1) for sz in (-1, 1)], 0.01, 0.005)
    return {"colliders": [K.collider_box((0, -d / 2, 0), (w, d, h))], "light": K.to_unity_vec((0, -0.8, 0))}


def security_gate(PW=0.9, PH=2.1, D=0.7):
    """Walk-through body scanner. Passage along Y (Unity Z), pivot base-centre."""
    pw = 0.26
    xo = PW / 2 + pw / 2
    for sx in (-1, 1):
        x = sx * xo
        box(pw + 0.04, D + 0.04, 0.04, at=(x, 0, 0), mat="chrome_scratched", base=True, bevel=0.006)
        p = box(pw, D, PH + 0.02, at=(x, 0, 0.04), mat="paint_glossy_white", base=True, bevel=0.04, bseg=3)
        inner = faces_where(p, lambda f, s=sx: f.normal.x * s < -0.9)
        inset(p, inner, 0.05, -0.012, mat="carbon_panel")
        for k in range(3):
            yy = -0.18 + k * 0.18
            box(0.006, 0.02, PH - 0.4, at=(x - sx * (pw / 2 - 0.006), yy, 0.28), mat="emit_strip_cyan", base=True)
        box(0.006, D - 0.14, 0.01, at=(x + sx * (pw / 2 + 0.001), 0, 1.1), mat="chrome_scratched")
        if detail():
            n0 = K.part_count()
            slots(-0.2, 0.2, 0.25, 0.5, 0, 6, "black", 0.012)
            for pp in K.parts_since(n0):
                pp.rot(z=90 * sx).move(x + sx * (pw / 2 + 0.0005), 0, 0)
    # header with downlight, status screen and lamps
    hd = box(PW + 2 * pw + 0.04, D + 0.04, 0.3, at=(0, 0, PH + 0.06), mat="paint_glossy_white", base=True, bevel=0.04, bseg=3)
    inset(hd, faces_where(hd, lambda f: f.normal.z < -0.9), 0.06, -0.01, mat="emit_panel_cyan")
    sc = box(0.44, 0.014, 0.14, at=(0, -(D + 0.04) / 2 - 0.007, PH + 0.21), mat="glass_dark", bevel=0.004)
    vquad(-0.2, PH + 0.155, 0.2, PH + 0.265, -(D + 0.04) / 2 - 0.0145, "screen")
    for sx, m in ((-1, "emit_green"), (1, "emit_red")):
        cyl(0.03, 0.012, 14, at=(sx * 0.4, -(D + 0.04) / 2 - 0.012, PH + 0.21), axis="Y", mat=m)
        torus(0.034, 0.005, n_major=14, n_minor=4, mat="chrome_scratched").rot(x=90).move(sx * 0.4, -(D + 0.04) / 2 - 0.006, PH + 0.21)
    box(PW + 2 * pw, 0.008, 0.012, at=(0, -(D + 0.04) / 2 - 0.004, PH + 0.09), mat="emit_strip_cyan")
    box(PW + 2 * pw, 0.008, 0.012, at=(0, (D + 0.04) / 2 + 0.004, PH + 0.09), mat="emit_strip_cyan")
    # floor threshold and scan curtain (holo, no collider)
    box(PW, D, 0.012, at=(0, 0, 0), mat="metal_plate", base=True)
    for sy in (-1, 1):
        box(PW, 0.012, 0.006, at=(0, sy * (D / 2 - 0.03), 0.012), mat="emit_strip_cyan", base=True)
    fl = Flat("holo_cyan")
    n = K.seg(28, 8)
    for i in range(n):
        z = 0.06 + (PH - 0.12) * (i + 0.5) / n
        hh = 0.004 if abs(z - 1.25) > 0.08 else 0.012
        vquad(-PW / 2, z - hh, PW / 2, z + hh, 0.0, "holo_cyan", fl)
    for sx in (-1, 1):
        vquad(sx * PW / 2 - 0.01, 0.04, sx * PW / 2 + 0.01, PH, 0.0, "holo_cyan", fl)
    return {"colliders": [K.collider_box((sx * xo, 0, (PH + 0.06) / 2), (pw, D, PH + 0.06)) for sx in (-1, 1)] +
            [K.collider_box((0, 0, PH + 0.21), (PW + 2 * pw + 0.04, D + 0.04, 0.3))],
            "opening": {"width": PW, "height": PH},
            "screen": {"center": K.to_unity_vec((0, -(D + 0.04) / 2 - 0.015, PH + 0.21)), "size": [0.4, 0.11], "normal": [0, 0, 1], "material": "screen"},
            "lights": [K.to_unity_vec((0, 0, PH - 0.1)), K.to_unity_vec((0, -0.6, 1.2))]}


ASSETS = {**ASSETS_A,
          "Lab_Bench": dict(fn=lab_bench, cat="facility", zones=["facility"],
                            notes="2.4 m lab bench: glossy white drawer cabinet (+Z front) with sample fridge, black epoxy worktop with LED "
                                  "under-lip, carbon service spine, frosted-glass shelves with LED nosing, overhead light bar, desk-top holo "
                                  "projector with a floating DNA/data hologram (holo_cyan / holo_magenta), microscope, centrifuge, vial rack."),
          "Lab_Bench_B": dict(fn=lab_bench, kw={"seed": 5}, cat="facility", zones=["facility"],
                              notes="Variant: double-door cabinet, analyzer unit, pipette stand, petri dishes, data hologram."),
          "CryoPod": dict(fn=cryo_pod, cat="facility", zones=["facility", "vault"],
                          notes="Containment / cryo pod 2.76 m: stepped glossy pedestal (chrome trim, vent ring, LED floor wash), cyan "
                                "ring (emit_cyan), glass tube with frosted base band, glossy-white struts with LED inlays (front open), "
                                "glowing Aether column (aether_energy) between chrome emitters, console with screen (+Z) and mini "
                                "hologram, rear service spine and hoses."),
          "CryoPod_Empty": dict(fn=cryo_pod, kw={"glowing": False}, cat="facility", zones=["facility", "vault"],
                                notes="Unpowered empty pod (all emissive slots black, no hologram)."),
          "Terminal_Desk": dict(fn=terminal_desk, cat="facility", zones=["facility", "metro", "rooftops"],
                                notes="Corporate workstation: glossy white top with LED under-lip, glossy slab legs with LED inlays, monitor "
                                      "(screen slot, rect unchanged) on a chrome arm, backlit keyboard, glass-side PC tower with fans, side "
                                      "holo projector with a floating data hologram (holo_cyan). User side +Z."),
          "Office_Chair": dict(fn=office_chair, cat="facility", zones=["facility", "rooftops"],
                               notes="Executive chair: chrome five-star base, carbon seat shell, bolstered cushion, padded back with headrest "
                                     "and cyan accent strips."),
          "Glass_Partition_2_5m": dict(fn=glass_partition, cat="facility", zones=["facility"],
                                       notes="2.5 x 3 m glass partition module (mullion on the Unity +X end, chain along X): glossy rails, "
                                             "frosted privacy band (glass_frosted) with manifestation dashes, LED wash lines on the rails."),
          "Lab_CeilingLight": dict(fn=ceiling_light, cat="facility", zones=["facility", "vault"], pivot="top-centre",
                                   notes="Recessed 1.6 x 0.6 luminaire: emit_panel_white diffuser behind chrome louvres, emit_strip_cyan "
                                         "halo frame (all emit_* slots switch together)."),
          "Lab_CeilingLight_Warm": dict(fn=ceiling_light, kw={"mat": "emit_panel_warm", "halo": "emit_strip_warm"}, cat="facility",
                                        zones=["metro", "rooftops"], pivot="top-centre", notes="Warm variant (emit_panel_warm + emit_strip_warm)."),
          "Desk_Reception": dict(fn=reception_desk, cat="facility", zones=["facility"],
                                 notes="7 m lobby reception counter: raked glossy-white front with vertical cyan LED seams, carbon base band "
                                       "and a backlit chrome emblem, dark transaction top with chrome nosing and LED under-lip; staff side -Z "
                                       "(Blender +Y) with a lower work surface, two monitors (screen slot) and backlit keyboards."),
          "Shelving_Unit": dict(fn=shelving, cat="props", zones=["facility", "metro", "rooftops"],
                                notes="2 m steel shelving: glossy perforated uprights, chrome shelf nosing with label rails and LED strips "
                                      "under each shelf, X-bracing; hard cases with latches, data cartridges, canisters, cable coils, crates."),
          "Holo_Display_Wall": dict(fn=holo_display_wall, cat="facility", zones=["facility"], pivot="wall-floor",
                                    notes="Wall-mounted holo display, footprint 2.7 x 0.47 m (Unity X x Z), 0.9..2.62 m high: carbon "
                                          "backplate with LED seams, wedge projector heads top/bottom with cyan emitter lips, floating 2.2 x 1.2 "
                                          "dashboard hologram (holo_cyan / holo_magenta) 0.3 m off the wall plus projection curtains. Pivot on the "
                                          "wall plane at floor level; place against a wall facing the room. 'screen' = hologram rect, 'light' = "
                                          "cyan fill-light anchor."),
          "Holo_Table": dict(fn=holo_table, cat="facility", zones=["facility"],
                             notes="Round holographic briefing table, 1.8 m diameter, 0.95 m top: glossy pedestal with LED floor ring and "
                                   "column strips, white rim, glass projector bed with emissive rings, floating city-map hologram (street "
                                   "grid, extruded blocks, magenta route and target marker) up to ~1.4 m. Collider = 1.6 m box (table only)."),
          "Corp_Wall_Panel_LED_4m": dict(fn=corp_wall_panel, cat="facility", zones=["facility"],
                                         notes="Corporate wall module on the Wall_* grid (4 x 4 m, 0.3 thick, length X centred, pivot "
                                               "base-centre), both faces clad: carbon dado, glossy white panels with shadow gaps and chrome "
                                               "fixings, cyan dado line + ceiling cove (emit_strip_cyan), blue vertical LED seams at x=+-1 m "
                                               "(emit_strip_blue, 2 m rhythm when chained), dark soffit band with vents."),
          "Corp_Reception_Logo_Frame": dict(fn=corp_logo_frame, cat="facility", zones=["facility"], pivot="back-centre",
                                            notes="Backlit lobby emblem frame 3.2 x 1.6 x 0.16 m (face +Z): glossy frame with cyan LED lip, "
                                                  "white light box (emit_panel_white) behind a chrome invented emblem (three crescents around "
                                                  "a split rhombus, no real logo) and a raised invented-glyph line. Pivot = back centre; mount "
                                                  "on the wall behind Desk_Reception at ~2.4 m."),
          "Security_Gate_Scanner": dict(fn=security_gate, cat="facility", zones=["facility"],
                                        notes="Walk-through body scanner 1.46 x 2.46 x 0.74 m, passage 0.9 x 2.1 along Z: glossy white pillars "
                                              "with carbon inner faces and vertical cyan scan bars, header with downlight (emit_panel_cyan), "
                                              "status screen (screen slot) and green/red lamps, holo scan curtain in the passage (no collider), "
                                              "LED floor threshold. Colliders: two pillars + header."),
          }
