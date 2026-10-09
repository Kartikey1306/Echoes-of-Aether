"""Underground Aether Vault + Aether Core chamber assets.

Cyberpunk restyle: layered armour (dark gunmetal, carbon panels, scratched chrome), recessed light channels, hazard
chevrons, hydraulics, LED readouts and invented glyph plates (same grammar as matdefs_hd.glyph). Every asset keeps the
prototype's name, pivot, outer size, colliders, metadata anchors and the material slots the zone code swaps
(emit_violet on Vault_ResonatorRing, aether_energy on Vault_Crystal, emit_red on Vault_BlastDoor_Light).
Small parts only exist at LOD0 (K.detail()). The detail kit at the top is shared with assets_monument.
"""
import math
import random

from mathutils import Matrix, Vector

import envkit as K
from envkit import box, cyl, lathe, tube, torus, beam, extrude, inset, faces_where, detail, rock

CH, CB, GD = "chrome_scratched", "carbon_panel", "glass_dark"


# ============================================================================================== detail kit
def rx(r_ext, n):
    """Radius of an n-gon (default start pi/n, n % 4 == 0) whose extent along X and Y is r_ext."""
    return r_ext / math.cos(math.pi / n)


def frame(origin, right=(1, 0, 0), up=(0, 0, 1)):
    """Matrix for K.placed(): local x = right, local y = up, local z = right x up (out of the surface).
    The default is a front (-Y facing) surface."""
    r, u = Vector(right).normalized(), Vector(up).normalized()
    m = Matrix((r, u, r.cross(u))).transposed().to_4x4()
    m.translation = Vector(origin)
    return m


def front(x, y, z):
    return frame((x, y, z))


def back(x, y, z):
    return frame((x, y, z), right=(-1, 0, 0))


def glyph_strokes(rng):
    """Invented glyph strokes in 0..1 (matdefs_hd.glyph grammar: roof bar, two stems, enclosure box or crossing
    strokes, mid bar, ticks, optional dot), so a glyph never reads as a Latin letter."""
    s = []
    top = rng.uniform(0.78, 0.9)
    s.append((rng.uniform(0.08, 0.2), top, rng.uniform(0.8, 0.92), top))
    for x in sorted(rng.sample([0.22, 0.38, 0.5, 0.62, 0.78], 2)):
        s.append((x, rng.uniform(0.05, 0.3), x, rng.uniform(0.6, top)))
    if rng.random() < 0.6:
        x0, x1 = rng.uniform(0.15, 0.35), rng.uniform(0.65, 0.85)
        y0, y1 = rng.uniform(0.1, 0.3), rng.uniform(0.45, 0.62)
        s += [(x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)]
    else:
        s.append((rng.uniform(0.1, 0.3), rng.uniform(0.1, 0.3), rng.uniform(0.55, 0.9), rng.uniform(0.45, 0.7)))
        s.append((rng.uniform(0.55, 0.9), rng.uniform(0.05, 0.25), rng.uniform(0.15, 0.45), rng.uniform(0.5, 0.7)))
    mid = rng.uniform(0.38, 0.6)
    s.append((rng.uniform(0.05, 0.25), mid, rng.uniform(0.7, 0.95), mid + rng.uniform(-0.05, 0.05)))
    for _ in range(rng.randint(1, 2)):
        x, y = rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9)
        s.append((x, y, x + rng.uniform(-0.15, 0.15), y - rng.uniform(0.08, 0.15)))
    dot = (rng.uniform(0.15, 0.85), rng.uniform(0.15, 0.85)) if rng.random() < 0.5 else None
    return s, dot


def glyph(size, seed, at=(0.0, 0.0), depth=0.012, stroke=0.085, mat="metal_bare", z=0.0):
    """One invented glyph as raised strokes in LOCAL face space (x right, y up, raised along +z from z)."""
    rng = random.Random(seed)
    strokes, dot = glyph_strokes(rng)
    w = stroke * size
    cx, cy = at
    for (ax, ay, bx, by) in strokes:
        A = Vector((cx + (ax - 0.5) * size, cy + (ay - 0.5) * size, z + depth / 2))
        B = Vector((cx + (bx - 0.5) * size, cy + (by - 0.5) * size, z + depth / 2))
        d = B - A
        if d.length < 1e-3:
            continue
        e = d.normalized() * (w / 2)
        beam(A - e, B + e, w, depth, mat=mat, up=(0, 0, 1))
    if dot is not None:
        cyl(w * 0.75, depth, 8, at=(cx + (dot[0] - 0.5) * size, cy + (dot[1] - 0.5) * size, z), mat=mat)


def glyph_row(n, size, seed, at=(0.0, 0.0), gap=0.3, vertical=False, **kw):
    pitch = size * (1 + gap)
    for i in range(n):
        o = (i - (n - 1) / 2) * pitch
        glyph(size, seed * 31 + i, at=(at[0], at[1] - o) if vertical else (at[0] + o, at[1]), **kw)


def bolts(pts, r=0.03, h=0.02, z=0.0, mat=CH, n=6):
    """Hex bolt heads in local face space (LOD0 only)."""
    if not detail():
        return
    for (x, y) in pts:
        cyl(r, h, n, at=(x, y, z), mat=mat, start=0.0)


def bolt_line(x0, x1, y, count, **kw):
    if count < 2:
        return bolts([((x0 + x1) / 2, y)], **kw)
    bolts([(x0 + (x1 - x0) * i / (count - 1), y) for i in range(count)], **kw)


def vent(w, h, at=(0.0, 0.0), depth=0.035, t=0.035, frame_mat="metal_dark", slat_mat="metal_dark", n=None, z=0.0):
    """Louvred vent in local face space: proud frame, black throat, angled slats (LOD0)."""
    cx, cy = at
    box(w - 0.02, h - 0.02, 0.004, at=(cx, cy, z + 0.002), mat="black")
    for (sx_, sy_, px, py) in ((w, t, cx, cy + h / 2 - t / 2), (w, t, cx, cy - h / 2 + t / 2),
                               (t, h - 2 * t, cx - w / 2 + t / 2, cy), (t, h - 2 * t, cx + w / 2 - t / 2, cy)):
        box(sx_, sy_, depth, at=(px, py, z), base=True, mat=frame_mat)
    if detail():
        n = n or max(3, int((h - 2 * t) / 0.07))
        pitch = (h - 2 * t) / n
        for i in range(n):
            s = box(w - 2 * t, pitch * 0.85, 0.008, mat=slat_mat)
            s.rot(x=-38).move(cx, cy - h / 2 + t + pitch * (i + 0.5), z + depth * 0.45)


def led_bar(x0, x1, y, h=0.05, segs=6, lit=None, z=0.0, mat="emit_strip_cyan", dark="black", depth=0.012):
    """Segmented LED read-out (bar graph) in local face space; the first `lit` segments glow."""
    lit = segs if lit is None else lit
    pitch = (x1 - x0) / segs
    box(x1 - x0 + 0.03, h + 0.03, depth * 0.6, at=(0.5 * (x0 + x1), y, z), base=True, mat="metal_dark")
    for i in range(segs):
        box(pitch * 0.78, h, depth, at=(x0 + pitch * (i + 0.5), y, z), base=True, mat=mat if i < lit else dark)


def piston(a, b, r_body, r_rod, split=0.55, n=12, body="metal_dark", rod=CH, gland=1.14):
    """Hydraulic ram from a (cylinder end) to b (rod end), with gland and end collars."""
    a, b = Vector(a), Vector(b)
    d = (b - a).normalized()
    m = a + (b - a) * split
    tube([a + d * 0.04, m], r_body, n, body)
    tube([m - d * 0.1, b - d * 0.03], r_rod, n, rod)
    tube([m - d * 0.14, m + d * 0.05], r_body * gland, n, "metal_bare")
    tube([a - d * 0.03, a + d * 0.16], r_body * min(gland, 1.1), n, "metal_bare")
    if detail():
        for f in (0.25, 0.4):
            p = a + (m - a) * f
            tube([p - d * 0.02, p + d * 0.02], r_body * min(gland, 1.05), n, "metal_bare")


def arc_sweep(prof, a0, a1, steps, mat, R=0.0, face_mat=None, name="sweep"):
    """Sweep a closed cross-section [(dr, dz), ...] around Z from a0 to a1 degrees at radius R (capped)."""
    secs = []
    for i in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * i / steps)
        c, s = math.cos(a), math.sin(a)
        secs.append([((R + dr) * c, (R + dr) * s, dz) for dr, dz in prof])
    return K.loft(secs, mat=mat, face_mat=face_mat, name=name)


def cable(points, r=0.03, n=6, mat="rubber", sag=0.0, steps=8):
    """Cable through points; with sag, each span droops like a catenary."""
    pts = []
    for i in range(len(points) - 1):
        a, b = Vector(points[i]), Vector(points[i + 1])
        k = steps if sag else 1
        for j in range(k):
            t = j / k
            p = a.lerp(b, t)
            p.z -= sag * 4 * t * (1 - t)
            pts.append(p)
    pts.append(Vector(points[-1]))
    return tube(pts, r, n, mat)


def hazard_band(x0, x1, z0, z1, y, stripe=0.35, mat_a="metal_painted_yellow", mat_b="black", proud=0.012):
    """Yellow/black chevron band on a face at y (facing -Y), stripes as exact parallelograms."""
    h = z1 - z0
    box(x1 - x0, proud, h, at=((x0 + x1) / 2, y - proud / 2, z0), mat=mat_a, base=True)
    x = x0 - h
    while x < x1:
        a0, a1 = x, x + stripe
        poly = []
        for (xx, zz) in ((a0, z0), (a1, z0), (a1 + h, z1), (a0 + h, z1)):
            p = (min(max(xx, x0), x1), zz)
            if not poly or (abs(p[0] - poly[-1][0]) > 1e-4 or abs(p[1] - poly[-1][1]) > 1e-4):
                poly.append(p)
        if len(poly) >= 3 and max(p[0] for p in poly) - min(p[0] for p in poly) > 0.01:
            area = 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
            if abs(area) > 1e-3:
                e = extrude(poly, 0.004, plane="XZ", mat=mat_b)
                e.move(0, y - proud - 0.002, 0)
        x += stripe * 2


# ============================================================================================== doors
def _lock_hub(R=2.0, seed=11):
    """Central vault lock (local face space, +z out of the door, 0.19 deep)."""
    n = K.seg(48)
    prof = [(R, -0.02), (R, 0.06), (R - 0.04, 0.1), (1.76, 0.1), (1.73, 0.13), (1.26, 0.13), (1.23, 0.1),
            (1.0, 0.1), (1.0, 0.15), (0.96, 0.17), (0.56, 0.17), (0.53, 0.18), (0.001, 0.18)]
    hub = lathe(prof, n, mat="metal_dark")

    def rad(f):
        return f.calc_center_median().xy.length
    hub.set_mat(CH, where=lambda f: 1.2 < rad(f) < 1.77 or rad(f) < 0.555)
    hub.set_mat(CB, where=lambda f: 0.555 <= rad(f) < 0.99 and f.normal.z > 0.5)
    for i in range(8):
        b = box(0.2, 0.46, 0.05, at=(0, 1.49, 0.13), mat="metal_dark", base=True, bevel=0.012)
        b.rot(z=i * 45 + 22.5)
    torus(1.115, 0.024, n_major=n, n_minor=4, mat="emit_strip_cyan").move(0, 0, 0.1)
    for i in range(16):
        t = box(0.045, 0.15, 0.012, at=(0, 1.87, 0.1), mat="emit_strip_cyan" if i % 2 == 0 else "black", base=True)
        t.rot(z=i * 22.5)
    glyph(0.62, seed, mat="metal_dark", depth=0.01, z=0.18, stroke=0.1)
    if detail():
        for i in range(12):
            a = math.radians(i * 30 + 15)
            cyl(0.03, 0.02, 6, at=(math.cos(a) * 0.78, math.sin(a) * 0.78, 0.17), mat=CH, start=0.0)


def blast_door(W=16.0, H=10.0, T=0.8):
    hw, yf, yb = W / 2, -T / 2, T / 2
    Y = "metal_painted_yellow"
    glow = "emit_strip_cyan"
    # ---- core slab: five lift segments (bevelled seams read on the edges)
    sh = H / 5
    for i in range(5):
        box(W, T, sh - 0.04, at=(0, 0, i * sh + 0.02), mat="metal_dark", base=True, bevel=0.05)
    # ---- kick band with hazard chevrons
    box(W - 0.1, 0.08, 0.9, at=(0, yf - 0.04, 0.05), mat="metal_dark", base=True, bevel=0.02)
    hazard_band(-hw + 0.2, hw - 0.2, 0.14, 0.84, yf - 0.08, stripe=0.42)
    # ---- outer lock columns (yellow) with locking-bolt housings
    zs = (1.75, 3.15, 4.55, 5.95, 7.35)
    for sx in (-1, 1):
        c = box(1.25, 0.14, 8.15, at=(sx * 7.375, yf - 0.07, 0.95), mat=Y, base=True, bevel=0.04)
        inset(c, faces_where(c, lambda f: f.normal.y < -0.9), 0.1, -0.025, mat="metal_dark")
        for z in zs:
            hb = box(0.95, 0.14, 0.56, at=(sx * 7.05, -0.57, z), mat=Y, bevel=0.025)
            inset(hb, faces_where(hb, lambda f: f.normal.y < -0.9), 0.06, -0.012, mat="metal_dark")
            x0 = min(sx * 7.43, sx * 7.98)
            cyl(0.075, 0.55, 12, at=(x0, -0.6, z), axis="X", mat=CH, bevel=0.015)
            box(0.1, 0.17, 0.22, at=(sx * 7.8, -0.6, z), mat="metal_dark", bevel=0.01)
            box(0.16, 0.012, 0.06, at=(sx * 6.84, -0.634, z + 0.16), mat="emit_amber")
            with K.placed(front(sx * 7.1, -0.628, z - 0.04)):
                glyph(0.3, 40 + int(z * 10) + (sx > 0) * 7, depth=0.006, mat="black", stroke=0.11)
            with K.placed(front(0, -0.64, 0)):
                bolts([(sx * 6.66, z - 0.2), (sx * 6.66, z + 0.2), (sx * 7.44, z - 0.2), (sx * 7.44, z + 0.2)], r=0.022, h=0.012)
    # ---- main field: four armour plates around the central seam
    for sx in (-1, 1):
        for (z0, z1) in ((1.0, 4.28), (4.47, 7.85)):
            p = box(6.55, 0.1, z1 - z0, at=(sx * 3.425, yf - 0.05, z0), mat="metal_dark", base=True, bevel=0.04)
            inset(p, faces_where(p, lambda f: f.normal.y < -0.9), 0.16, -0.03, mat="paint_glossy_dark")
            with K.placed(front(0, yf - 0.07, 0)):
                for x in (2.3, 4.6):
                    box(0.03, z1 - z0 - 0.34, 0.004, at=(sx * x, (z0 + z1) / 2, 0), base=True, mat="black")
                box(6.2, 0.03, 0.004, at=(sx * 3.43, (z0 + z1) / 2 + (0.5 if z0 < 4 else -0.5), 0), base=True, mat="black")
            with K.placed(front(0, yf - 0.1, 0)):
                bolt_line(sx * 0.4, sx * 6.45, z0 + 0.08, 9, r=0.026, h=0.014)
                bolt_line(sx * 0.4, sx * 6.45, z1 - 0.08, 9, r=0.026, h=0.014)
        # seam rails + vertical LED channel
        box(0.05, 0.1, 6.85, at=(sx * 0.12, yf - 0.05, 1.0), mat=CH, base=True)
    for (z0, z1) in ((1.05, 2.3), (6.45, 7.8)):
        box(0.07, 0.02, z1 - z0, at=(0, yf - 0.01, z0), mat=glow, base=True)
    box(13.0, 0.02, 0.06, at=(0, yf - 0.01, 7.87), mat=glow, base=True)
    # ---- central lock hub + four hydraulic rams driving the bolt-work
    with K.placed(front(0, yf - 0.1, 4.375)):
        _lock_hub()
    for sx in (-1, 1):
        for (a, b) in (((sx * 6.2, 1.55), (sx * 1.7, 3.62)), ((sx * 6.2, 7.2), (sx * 1.7, 5.13))):
            piston((a[0], -0.585, a[1]), (b[0], -0.585, b[1]), 0.1, 0.058, gland=1.03)
            box(0.5, 0.1, 0.5, at=(a[0], -0.55, a[1]), mat="metal_bare", bevel=0.025)
            for k in (-1, 1):
                d = Vector((b[0] - a[0], 0, b[1] - a[1])).normalized()
                nrm = Vector((-d.z, 0, d.x)) * k * 0.13
                box(0.3, 0.09, 0.05, at=(a[0] + nrm.x, -0.64, a[1] + nrm.z), mat="metal_dark", bevel=0.01).rot_about((a[0] + nrm.x, -0.64, a[1] + nrm.z), y=-math.degrees(math.atan2(d.z, d.x)))
            cyl(0.055, 0.19, 8, at=(a[0], -0.69, a[1]), axis="Y", mat=CH)
            cyl(0.085, 0.09, 12, at=(b[0], -0.675, b[1]), axis="Y", mat="metal_dark")
    # ---- read-outs, vents and glyph plates on the plates
    for sx in (-1, 1):
        with K.placed(front(0, yf - 0.07, 0)):
            vent(1.6, 0.6, at=(sx * 3.8, 1.55), depth=0.04)
            box(0.95, 0.95, 0.04, at=(sx * 1.05, 1.75, 0), base=True, mat="metal_dark")
            for k, lit in enumerate((6, 4, 5, 2)):
                led_bar(sx * 1.05 - 0.38, sx * 1.05 + 0.38, 1.45 + k * 0.2, h=0.07, segs=6, lit=lit, z=0.04)
            box(1.9, 0.75, 0.06, at=(sx * 3.9, 7.05, 0), base=True, mat="metal_dark")
            glyph_row(3, 0.42, 3 + (sx > 0), at=(sx * 3.9, 7.05), depth=0.012, z=0.06, mat="metal_bare")
            led_bar(sx * 3.9 - 0.85, sx * 3.9 + 0.85, 7.6, h=0.06, segs=8, lit=5 + (sx > 0) * 2)
    # ---- light rail with the eight countdown sockets (Vault_BlastDoor_Light mounts at y=-0.69)
    box(13.4, 0.12, 1.1, at=(0, yf - 0.06, 7.95), mat="metal_dark", base=True, bevel=0.03)
    for i in range(8):
        x = -4.2 + i * 1.2
        box(0.75, 0.17, 0.45, at=(x, -0.605, 8.275), mat="metal_dark", base=True, bevel=0.015)
        if i < 7:
            box(0.08, 0.1, 0.62, at=(x + 0.6, -0.57, 8.19), mat=CH, base=True)
    for sx in (-1, 1):
        with K.placed(front(0, yf - 0.12, 0)):
            box(1.6, 0.8, 0.04, at=(sx * 5.75, 8.5, 0), base=True, mat=CB)
            glyph_row(2, 0.4, 9 + (sx > 0), at=(sx * 5.75, 8.55), z=0.04, depth=0.012)
            bolts([(sx * 5.0, 8.15), (sx * 6.5, 8.15), (sx * 5.0, 8.85), (sx * 6.5, 8.85)], r=0.022, h=0.012, z=0.04)
    # ---- top armour band with vents and chevron end caps
    tb = box(15.9, 0.1, 0.82, at=(0, yf - 0.05, 9.12), mat="metal_dark", base=True, bevel=0.03)
    inset(tb, faces_where(tb, lambda f: f.normal.y < -0.9), 0.08, -0.02, mat=CB)
    with K.placed(front(0, yf - 0.08, 0)):
        for x in (-4.6, -1.9, 1.9, 4.6):
            vent(1.9, 0.5, at=(x, 9.53), depth=0.04)
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 6.75, sx * 7.85))
        hazard_band(x0, x1, 9.2, 9.86, yf - 0.08, stripe=0.25)
    # ---- back: structural ribs, stiffeners, chevrons
    for k in range(9):
        x = -hw + 0.6 + k * (W - 1.2) / 8
        box(0.28, 0.11, H - 0.3, at=(x, yb + 0.055, 0.15), mat="metal_dark", base=True, bevel=0.02)
    for z in (3.3, 6.6):
        box(W - 0.4, 0.08, 0.3, at=(0, yb + 0.04, z), mat="metal_bare", base=True, bevel=0.015)
    with K.placed(rz=180):
        hazard_band(-hw + 0.2, hw - 0.2, 0.14, 0.84, yf, stripe=0.42)
    return {"colliders": [K.collider_box((0, 0, H / 2), (W, T, H))],
            "lightSockets": [K.to_unity_vec((-4.2 + i * 1.2, -T / 2 - 0.29, 8.5)) for i in range(8)],
            "lift": "slides up 9.5 m when open (prototype)"}


def blast_door_light():
    """Countdown indicator: lipped bezel, recessed segmented emit_red lens (state-swapped by VaultZone)."""
    box(0.7, 0.06, 0.4, at=(0, 0.03, -0.2), mat="metal_dark", base=True, bevel=0.01)
    for (sx_, sz_, x, z) in ((0.7, 0.05, 0, 0.175), (0.7, 0.05, 0, -0.175), (0.05, 0.3, 0.325, 0), (0.05, 0.3, -0.325, 0)):
        box(sx_, 0.032, sz_, at=(x, -0.014, z), mat="metal_dark", bevel=0.006)
    box(0.6, 0.03, 0.3, at=(0, -0.005, 0), mat="emit_red")
    if detail():
        for i in range(1, 6):
            box(0.012, 0.006, 0.3, at=(-0.3 + i * 0.1, -0.022, 0), mat="black")
        box(0.6, 0.006, 0.012, at=(0, -0.022, 0), mat="black")
    return {"colliders": "none"}


def blast_door_frame(W=16.0, H=10.0, D=1.2):
    hd = D / 2
    Y = "metal_painted_yellow"
    for sx in (-1, 1):
        cx = sx * (W / 2 + 0.8)
        box(1.6, D, H + 1.5, at=(cx, 0, 0), mat="metal_dark", base=True, bevel=0.05)
        # layered front armour
        box(1.3, 0.1, 2.9, at=(cx, -hd - 0.05, 0.2), mat="metal_dark", base=True, bevel=0.03)
        hazard_band(cx - 0.6, cx + 0.6, 0.3, 3.0, -hd - 0.1, stripe=0.3)
        for (z0, z1) in ((3.2, 6.55), (6.65, 9.9)):
            p = box(1.3, 0.1, z1 - z0, at=(cx, -hd - 0.05, z0), mat="metal_dark", base=True, bevel=0.03)
            inset(p, faces_where(p, lambda f: f.normal.y < -0.9), 0.1, -0.025, mat=CB)
        # inner lip (door guide) + glowing slot in the guide
        box(0.14, D + 0.04, H, at=(sx * (W / 2 + 0.07), -0.02, 0), mat=CH, base=True, bevel=0.02)
        box(0.025, 0.04, H - 0.6, at=(sx * (W / 2 + 0.07), -hd - 0.035, 0.3), mat="emit_red", base=True)
        with K.placed(front(cx, -hd - 0.075, 0)):
            for z in (4.1, 7.6):
                led_bar(-0.45, 0.45, z, h=0.07, segs=5, lit=3, mat="emit_red", z=0.0)
            glyph_row(2, 0.36, 21 + (sx > 0), at=(0, 5.4), vertical=True, depth=0.01, mat="metal_bare")
            glyph(0.36, 25 + (sx > 0), at=(0, 8.8), depth=0.01, mat="metal_bare")
            bolts([(x, z) for x in (-0.55, 0.55) for z in (3.35, 6.4, 6.8, 9.75)], r=0.025, h=0.015, z=0.025)
        # hydraulic ram (the body sets the frame's front extent: y -0.95 - 0.22)
        ram = lathe([(0.17, 1.5), (0.22, 1.56), (0.22, 7.32), (0.2, 7.4), (0.15, 7.5)], 16, at=(cx, -0.95, 0), mat="metal_dark")
        ram.set_mat("metal_bare", where=lambda f: 7.2 < f.calc_center_median().z or f.calc_center_median().z < 1.6)
        cyl(0.12, 3.5, 12, at=(cx, -0.95, 7.4), mat=CH)
        box(0.6, 0.6, 0.3, at=(cx, -hd - 0.25, 1.2), mat="metal_bare", base=True, bevel=0.03)
        box(0.5, 0.42, 1.2, at=(cx, -hd - 0.2, 0.0), mat="metal_dark", base=True, bevel=0.02)
        box(0.5, 0.55, 0.5, at=(cx, -0.85, 10.6), mat="metal_dark", base=True, bevel=0.03)
        cyl(0.07, 0.62, 10, at=(cx - 0.31, -0.85, 10.85), axis="X", mat=CH)
        for k in (-1, 1):
            box(0.06, 0.32, 0.4, at=(cx + k * 0.15, -0.85, 1.22), mat="metal_dark", base=True)
        if detail():
            for k in (-1, 1):
                cable([(cx + k * 0.16, -0.78, 1.7), (cx + k * 0.42, -0.72, 2.3), (cx + k * 0.5, -0.705, 3.1)], r=0.035, n=6, sag=0.05, steps=4)
                cable([(cx + k * 0.17, -0.8, 6.9), (cx + k * 0.42, -0.72, 7.4), (cx + k * 0.5, -0.705, 8.4)], r=0.03, n=6, sag=0.05, steps=4)
        # amber beacon on the column head
        cyl(0.24, 0.08, 16, at=(cx, -0.25, H + 1.5), mat="metal_dark", bevel=0.01)
        lathe([(0.17, 0.0), (0.17, 0.04), (0.14, 0.16), (0.07, 0.21), (0.001, 0.22)], 12, at=(cx, -0.25, H + 1.58), mat="emit_amber")
        if detail():
            for i in range(4):
                a = math.radians(45 + i * 90)
                tube([(cx + math.cos(a) * 0.2, -0.25 + math.sin(a) * 0.2, H + 1.58), (cx + math.cos(a) * 0.17, -0.25 + math.sin(a) * 0.17, H + 1.74),
                      (cx, -0.25, H + 1.775)], 0.012, 4, CH)
    # header: armour beam, central glyph crest, red LED slits, vents
    box(W + 3.2, D, 1.5, at=(0, 0, H), mat="metal_dark", base=True, bevel=0.05)
    box(W + 3.0, 0.04, 0.12, at=(0, -hd - 0.02, H + 1.3), mat="metal_plate", base=True)
    fb = box(15.6, 0.1, 1.06, at=(0, -hd - 0.05, H + 0.22), mat="metal_dark", base=True, bevel=0.03)
    inset(fb, faces_where(fb, lambda f: f.normal.y < -0.9), 0.07, -0.02, mat=CB)
    box(15.6, 0.06, 0.1, at=(0, -hd - 0.03, H + 0.06), mat=Y, base=True, bevel=0.01)
    with K.placed(front(0, -hd - 0.08, 0)):
        box(3.4, 0.9, 0.06, at=(0, H + 0.75, 0), base=True, mat="metal_dark")
        glyph_row(4, 0.5, 31, at=(0, H + 0.75), depth=0.014, z=0.06, mat=CH)
        for sx in (-1, 1):
            for k in range(3):
                box(2.4, 0.05, 0.02, at=(sx * (3.2 + 1.2), H + 0.5 + k * 0.25, 0), base=True, mat="emit_red" if k != 1 else "black")
            vent(1.5, 0.7, at=(sx * 6.7, H + 0.75), depth=0.035)
            bolts([(sx * 1.85, H + 0.4), (sx * 1.85, H + 1.1), (sx * 7.65, H + 0.4), (sx * 7.65, H + 1.1)], r=0.028, h=0.015)
    if detail():
        cable([(-8.0, -0.45, H + 1.53), (-3.0, -0.45, H + 1.53), (3.0, -0.45, H + 1.53), (8.0, -0.45, H + 1.53)], r=0.05, n=6, sag=0.0)
    return {"colliders": [K.collider_box((sx * (W / 2 + 0.8), 0, (H + 1.5) / 2), (1.6, D, H + 1.5)) for sx in (-1, 1)] +
            [K.collider_box((0, 0, H + 0.75), (W + 3.2, D, 1.5))]}


def lock_door_half(W=3.0, H=5.0, T=0.5):
    """One leaf of the resonance lock door; violet seam strip on the Unity +X edge (Blender -X). Each face carries a
    violet half-ring on the seam side, so the two closed leaves complete one resonance circle."""
    box(W, T, H, mat="metal_painted", base=True, bevel=0.03)
    box(0.08, T + 0.02, H - 0.4, at=(-W / 2 + 0.05, 0, 0.2), mat="emit_strip_violet", base=True)
    for sy in (-1, 1):
        for z in (0.6, 4.4):
            cyl(0.12, 0.05, 12, at=(-W / 2 + 0.35, sy * (T / 2 + 0.02), z), axis="Y", center=True, mat="emit_violet")
    for flip in (False, True):
        m = front(0, -T / 2, 0)
        if flip:
            m = Matrix.Diagonal((1, -1, 1, 1)) @ m
        with K.placed(m):
            # armour plates (local z 0..0.025) with violet light channels in the gaps
            for (z0, z1) in ((0.2, 1.55), (1.65, 3.35), (3.45, 4.8)):
                p = box(2.72, z1 - z0, 0.025, at=(0.12, (z0 + z1) / 2, 0), base=True, mat="metal_plate", bevel=0.008)
                inset(p, faces_where(p, lambda f: f.normal.z > 0.9), 0.07, -0.01, mat=CB)
            for z in (1.6, 3.4):
                box(2.6, 0.035, 0.012, at=(0.18, z, 0), base=True, mat="emit_strip_violet")
            for z in (0.12, 4.88):
                box(2.9, 0.07, 0.03, at=(0.05, z, 0), base=True, mat="metal_dark", bevel=0.008)
            # resonance half-ring on the seam (completed by the other leaf)
            ns = K.seg(16)
            arc_sweep([(-0.05, 0.025), (0.05, 0.025), (0.05, 0.045), (-0.05, 0.045)], -90, 90, ns, CH, R=1.12).move(-1.5, 2.5, 0)
            torus(0.95, 0.018, arc=180, n_major=ns, n_minor=4, mat="emit_strip_violet", start=-90).move(-1.5, 2.5, 0.027)
            arc_sweep([(-0.03, 0.025), (0.03, 0.025), (0.03, 0.04), (-0.03, 0.04)], -90, 90, K.seg(12), "metal_dark", R=0.72).move(-1.5, 2.5, 0)
            if detail():
                for a in (-67.5, -45, -22.5, 0, 22.5, 45, 67.5):
                    t = box(0.1, 0.025, 0.012, at=(0, 0, 0.025), base=True, mat="metal_bare")
                    t.move(0.82, 0, 0).rot(z=a).move(-1.5, 2.5, 0)
            glyph_row(3, 0.36, 50 + flip, at=(0.85, 2.5), vertical=True, depth=0.008, z=0.025, mat="metal_bare")
            bolts([(x, z) for x in (-1.2, 1.36) for z in (0.3, 4.7)] + [(1.36, z) for z in (1.45, 1.75, 3.25, 3.55)], r=0.022, h=0.012, z=0.025)
            for z in (0.6, 4.4):
                torus(0.15, 0.02, n_major=12, n_minor=4, mat=CH).move(-1.15, z, 0.025)
    return {"colliders": [K.collider_box((0, 0, H / 2), (W, T, H))]}


def vault_wall_panel(L=4.0, H=4.0, strip="emit_strip_violet"):
    """Wall-base pivot on the interior wall face; deep armour bays, recessed light channels, cable loom, vents.
    Panels tile edge to edge (half pilasters at both ends, cable loom continuous across)."""
    hl = L / 2
    box(L, 0.4, H, at=(0, 0.2, 0), mat="metal_plate", base=True)
    box(L, 0.1, H, at=(0, -0.05, 0), mat="metal_dark", base=True)
    glow = strip or "black"
    # edge half-pilasters (two neighbours form one 0.36 m pilaster with a seam)
    for sx in (-1, 1):
        p = box(0.18, 0.14, H, at=(sx * (hl - 0.09), -0.17, 0), mat="metal_dark", base=True, bevel=0.02)
        inset(p, faces_where(p, lambda f: f.normal.y < -0.9), 0.04, -0.015, mat="metal_plate")
    # plinth with vents
    pl = box(L - 0.36, 0.2, 0.36, at=(0, -0.2, 0), mat="metal_dark", base=True, bevel=0.02)
    with K.placed(front(0, -0.3, 0)):
        for x in (-0.9, 0.9):
            vent(1.2, 0.2, at=(x, 0.18), depth=0.02, t=0.025)
    # base light channel
    box(L - 0.36, 0.12, 0.04, at=(0, -0.16, 0.36), mat=CH, base=True)
    box(L - 0.36, 0.02, 0.045, at=(0, -0.11, 0.42), mat=glow, base=True)
    # cornice with under-lit channel
    co = box(L, 0.26, 0.42, at=(0, -0.13, H - 0.42), mat="metal_dark", base=True, bevel=0.025)
    inset(co, faces_where(co, lambda f: f.normal.y < -0.9), 0.05, -0.02, mat="metal_plate")
    box(L - 0.36, 0.02, 0.045, at=(0, -0.11, H - 0.53), mat=glow, base=True)
    box(L - 0.36, 0.1, 0.03, at=(0, -0.16, H - 0.58), mat=CH, base=True)
    # armour bays: two columns of plates around a recessed vertical light channel
    for sx in (-1, 1):
        for (z0, z1) in ((0.5, 1.88), (1.98, 3.4)):
            p = box(1.62, 0.1, z1 - z0, at=(sx * 0.95, -0.15, z0), mat="metal_dark", base=True, bevel=0.03)
            inset(p, faces_where(p, lambda f: f.normal.y < -0.9), 0.1, -0.03, mat="metal_plate")
            with K.placed(front(0, -0.2, 0)):
                bolts([(sx * 0.2, z0 + 0.06), (sx * 1.7, z0 + 0.06), (sx * 0.2, z1 - 0.06), (sx * 1.7, z1 - 0.06)], r=0.022, h=0.012)
        box(0.05, 0.12, H - 1.1, at=(sx * 0.115, -0.16, 0.5), mat=CH, base=True)
    box(0.06, 0.02, H - 1.1, at=(0, -0.11, 0.5), mat=glow, base=True)
    # bay details: vent (left low), glyph tag + LED read-out (right high), service hatch (left high)
    with K.placed(front(0, -0.17, 0)):
        vent(1.1, 0.5, at=(-0.95, 0.82), depth=0.03)
        box(0.9, 0.5, 0.025, at=(0.95, 2.95, 0), base=True, mat=CB)
        glyph_row(3, 0.2, 61, at=(0.95, 3.0), z=0.025, depth=0.008, mat="metal_bare")
        led_bar(0.6, 1.3, 2.78, h=0.03, segs=5, lit=3, z=0.025, mat=glow)
        box(0.7, 0.9, 0.02, at=(-0.95, 2.7, 0), base=True, mat="metal_dark")
        bolts([(-1.25, 2.3), (-0.65, 2.3), (-1.25, 3.1), (-0.65, 3.1)], r=0.02, h=0.012, z=0.02)
    # cable loom (continuous across neighbouring panels) on brackets at the pilasters and centre
    for x in (-hl + 0.09, 0.0, hl - 0.09):
        box(0.12, 0.17, 0.42, at=(x, -0.255, 2.32), mat="metal_bare", base=True, bevel=0.015)
        box(0.18, 0.02, 0.06, at=(x, -0.345, 2.62), mat="metal_dark", base=True)
    zc = 2.52
    if detail():
        for (y, dz, r, m) in ((-0.31, 0.0, 0.045, "rubber"), (-0.27, -0.09, 0.035, "rubber"), (-0.32, -0.17, 0.03, "rubber")):
            pts = [(-hl, y, zc + dz)]
            for (x0, x1) in ((-hl + 0.09, -0.06), (0.06, hl - 0.09)):
                for k in range(9):
                    x = x0 + (x1 - x0) * k / 8
                    t = (x - x0) / (x1 - x0)
                    pts.append((x, y, zc + dz - 0.07 * 4 * t * (1 - t)))
            pts.append((hl, y, zc + dz))
            tube(pts, r, 6, m)
    cyl(0.055, L, 12, at=(-hl, -0.31, 2.4), axis="X", mat=CH)
    if detail():
        for x in (-1.0, 1.0):
            cyl(0.06, 0.08, 12, at=(x - 0.04, -0.305, 2.4), axis="X", mat="metal_dark")
    # outermost conduit (sets the front extent: y = -0.367)
    cyl(0.06, L, 12, at=(-hl, -0.307, 1.18), axis="X", mat="metal_bare")
    for x in (-hl + 0.09, hl - 0.09):
        box(0.12, 0.16, 0.22, at=(x, -0.25, 1.07), mat="metal_dark", base=True, bevel=0.01)
    return {"colliders": [K.collider_box((0, 0.1, H / 2), (L, 0.6, H))]}


# ============================================================================================== resonators / glyphs
def resonator_pillar():
    n = 24
    R0 = rx(0.741, n)
    glow = "emit_strip_violet"
    # base flange (chrome) + drum
    lathe([(0.001, 0.0), (R0, 0.0), (R0, 0.08), (0.72, 0.12), (0.66, 0.12), (0.001, 0.12)], n, mat=CH)
    lathe([(0.66, 0.12), (0.66, 0.4), (0.62, 0.44), (0.001, 0.44)], n, mat="metal_dark")
    lathe([(0.64, 0.42), (0.64, 0.5), (0.6, 0.52), (0.001, 0.52)], n, mat=CH)
    # coil chamber: carbon core, glowing coils, chrome cage
    lathe([(0.4, 0.5), (0.4, 1.78), (0.001, 1.78)], n, mat=CB, close_bottom=False)
    nc = 7
    for i in range(nc):
        torus(0.455, 0.032, n_major=K.seg(24), n_minor=5, mat=glow).move(0, 0, 0.62 + i * 1.04 / (nc - 1))
    for i in range(6):
        a = i * 60 + 30
        b = box(0.07, 0.06, 1.28, at=(0, -0.55, 0.5), mat=CH, base=True, bevel=0.012)
        b.rot(z=a)
    lathe([(0.6, 1.74), (0.6, 1.82), (0.57, 1.86), (0.001, 1.86)], n, mat=CH)
    # upper shaft: carbon with violet inlay channels
    lathe([(0.55, 1.84), (0.5, 2.55), (0.001, 2.55)], n, mat=CB, close_bottom=False)
    for i in range(6):
        a = i * 60
        s = box(0.045, 0.03, 0.62, at=(0, 0, 0), mat=glow, base=True)
        s.rot(x=-4.1).move(0, -0.535, 1.9).rot(z=a)
        for k in (-1, 1):
            r = box(0.025, 0.04, 0.66, at=(0, 0, 0), mat="metal_dark", base=True)
            r.rot(x=-4.1).move(k * 0.045, -0.53, 1.88).rot(z=a)
    # collar, neck and the crystal cradle
    lathe([(0.53, 2.54), (0.53, 2.68), (0.5, 2.72), (0.42, 2.74), (0.001, 2.74)], n, mat=CH)
    lathe([(0.42, 2.72), (0.33, 2.86), (0.3, 2.9), (0.001, 2.9)], n, mat="metal_dark")
    torus(0.36, 0.018, n_major=K.seg(24), n_minor=4, mat=glow).move(0, 0, 2.8)
    lathe([(0.3, 2.88), (0.26, 2.94), (0.2, 2.96), (0.001, 2.95)], 12, mat="metal_bare")
    for i in range(3):
        p = box(0.05, 0.05, 0.14, at=(0, -0.24, 2.88), mat=CH, base=True)
        p.rot(z=i * 120)
    if detail():
        for i in range(12):
            a = math.radians(i * 30 + 15)
            cyl(0.02, 0.012, 6, at=(math.cos(a) * 0.69, math.sin(a) * 0.69, 0.12), mat="metal_bare", start=0.0)
        for i in range(6):
            fin = extrude([(0.0, 0.0), (0.0, 0.3), (-0.1, 0.0)], 0.05, plane="YZ", mat="metal_bare")
            fin.move(0, -0.63, 0.12).rot(z=i * 60 + 30)
    return {"colliders": [K.collider_box((0, 0, 1.45), (1.2, 1.2, 2.9))], "ringHeight": 2.2, "crystalHeight": 3.1}


def resonator_ring(R=0.75, r=0.06, gap=8.6):
    """Four emit_violet coil segments (VaultZone swaps them to metal_dark and overlays its own state glow) with
    machined chrome / carbon end clamps and emitter nodes in the gaps."""
    for k in range(4):
        torus(R, r, arc=90 - gap, n_major=10, n_minor=8, mat="emit_violet", start=k * 90 + gap / 2)
        if detail():
            for a in (k * 90 + gap / 2, k * 90 + 90 - gap / 2):
                c = cyl(r + 0.012, 0.04, 8, mat="metal_dark", center=True, axis="Y")
                c.move(R, 0, 0).rot(z=a)
                c2 = cyl(r + 0.004, 0.03, 8, mat=CH, center=True, axis="Y")
                c2.move(R, 0.02 if a % 90 < 45 else -0.02, 0).rot(z=a)
            nd = box(0.05, 0.06, 0.07, mat=CB, bevel=0.008)
            nd.move(R, 0, 0).rot(z=k * 90)
            cyl(0.022, 0.08, 8, at=(R, 0, 0), axis="X", center=True, mat=CH).rot(z=k * 90)
            for a in (k * 90 + 30, k * 90 + 60):
                t = torus(r - 0.001, 0.006, n_major=10, n_minor=3, mat=CH)
                t.rot(x=90).move(R, 0, 0).rot(z=a)
    return {"colliders": "none", "segments": 4}


def gem(levels, n=6, mat="aether_energy", st=30.0):
    """Faceted gem: levels [(r, z, twist_deg)], bottom to top; tips use r ~ 0."""
    secs = [[(r * math.cos(math.radians(st + tw + k * 360 / n)), r * math.sin(math.radians(st + tw + k * 360 / n)), z) for k in range(n)]
            for (r, z, tw) in levels]
    return K.loft(secs, mat=mat, name="gem")


def crystal(h=0.7, r=0.25, mat="aether_energy"):
    """Faceted Aether crystal: hex bipyramid with twisted crown/pavilion facets and a small side shard (same bounds)."""
    gem([(0.002, -h / 2, 0), (r * 0.66, -h * 0.24, 30), (r, -0.02, 0), (r * 0.8, h * 0.22, 30), (0.002, h / 2, 0)], 6, mat)
    if detail():
        c = gem([(0.002, -0.05, 0), (0.05, 0.0, 0), (0.002, 0.16, 0)], 5, mat)
        c.rot(x=-48).move(0, -0.12, -0.17).rot(z=-20)
    return {"colliders": "none"}


def glyph_plate():
    """Hexagonal wall plaque (frame for the hidden resonance glyph). Pivot = back centre on the wall.
    The centre field stays behind y = -0.05 so the game's glyph marks (Unity z 0.09) sit in front of it."""
    p = cyl(1.0, 0.06, 6, at=(0, 0, 0), axis="Y", mat="metal_dark", start=0, bevel=0.01)
    p.move(0, -0.03, 0)
    cyl(0.8, 0.012, 6, at=(0, -0.042, 0), axis="Y", mat=CB, start=0)
    cyl(0.62, 0.006, 6, at=(0, -0.048, 0), axis="Y", mat=GD, start=0)
    t = torus(0.85, 0.035, n_major=6, n_minor=6, mat="emit_violet", start=0)
    t.rot(x=90).move(0, -0.07, 0)
    # chrome rim bars along the hex edges (gapped at the corners)
    for i in range(6):
        a0, a1 = math.radians(i * 60), math.radians(i * 60 + 60)
        A = Vector((math.cos(a0) * 0.94, -0.045, math.sin(a0) * 0.94))
        B = Vector((math.cos(a1) * 0.94, -0.045, math.sin(a1) * 0.94))
        beam(A.lerp(B, 0.12), A.lerp(B, 0.88), 0.07, 0.03, mat=CH, up=(0, -1, 0))
    if detail():
        for i in range(6):
            a = math.radians(i * 60 + 30)
            cyl(0.03, 0.03, 8, at=(math.cos(a) * 0.95, -0.075, math.sin(a) * 0.95), axis="Y", center=True, mat="metal_bare")
        for i in range(6):
            b = box(0.025, 0.006, 0.09, mat="emit_violet" if i % 2 == 0 else "metal_bare")
            b.move(0, -0.051, 0.7).rot(y=-i * 60 + 90)
    return {"colliders": "none", "glyphCenter": K.to_unity_vec((0, -0.08, 0))}


def pedestal(r_bot=1.0, r_top=0.8, h=1.0, ring="emit_violet", ring_r=None, mat="metal_dark", ribs=12):
    """Machined pedestal: chrome flange, body skirt, recessed glowing coil band behind chrome ribs, carbon upper
    body, chrome cap and a dark-glass top with the emitter ring (outer extent / height as the prototype)."""
    ring_r = ring_r or r_top * 0.85
    n = 32 if r_bot < 2.5 else 48
    R0 = (r_bot + 0.1) * math.cos(math.pi / 32) / math.cos(math.pi / n)
    hz = h - 0.2

    def rr(z):
        t = min(max((z - 0.12) / max(hz, 1e-3), 0.0), 1.0)
        return r_bot + (r_top - r_bot) * t
    zA, zB = 0.12 + 0.2 * hz, 0.12 + 0.56 * hz
    body = lathe([(0.001, 0.0), (R0, 0.0), (R0, 0.06), (r_bot + 0.05, 0.1), (r_bot, 0.12),
                  (rr(zA - 0.05), zA - 0.05), (rr(zA) + 0.03, zA - 0.025), (rr(zA) + 0.03, zA), (rr(zA) - 0.1, zA),
                  (rr(zB) - 0.1, zB), (rr(zB) + 0.03, zB), (rr(zB) + 0.03, zB + 0.025), (rr(zB + 0.05), zB + 0.05),
                  (r_top, h - 0.08), (r_top + 0.04, h - 0.05), (r_top + 0.04, h), (0.001, h)], n, mat=mat)

    def zc(f):
        return f.calc_center_median().z
    body.set_mat(CH, where=lambda f: zc(f) < 0.115 or zA - 0.03 < zc(f) < zA + 0.001 or zB - 0.001 < zc(f) < zB + 0.03
                 or (zc(f) > h - 0.07 and f.calc_center_median().xy.length > r_top - 0.02))
    body.set_mat(CB, where=lambda f: zB + 0.03 <= zc(f) <= h - 0.07)
    body.set_mat("black", where=lambda f: zA + 0.002 < zc(f) < zB - 0.002 and abs(f.normal.z) < 0.5)
    rs = 0.03 * max(1.0, r_top)
    torus(ring_r, rs, n_major=K.seg(40) if n == 32 else K.seg(56), n_minor=6, mat=ring).move(0, 0, h + 0.005)
    # top: dark glass disc + chrome track rings
    cyl(max(ring_r - 0.16, 0.2), 0.006, n, at=(0, 0, h), mat=GD)
    for rad in (ring_r - 0.1, ring_r + 0.1):
        torus(rad, 0.012, n_major=K.seg(n), n_minor=3, mat=CH).move(0, 0, h)
    # glowing coils behind the ribs
    nc = max(2, int((zB - zA) / 0.09))
    for i in range(nc):
        z = zA + (zB - zA) * (i + 0.5) / nc
        torus(rr(z) - 0.075, min(0.02, (zB - zA) / nc * 0.25), n_major=K.seg(n), n_minor=4, mat=ring).move(0, 0, z)
    for i in range(ribs):
        a = 360 * i / ribs
        b = box(0.07 * max(1, r_top ** 0.5), 0.07, zB - zA + 0.04, at=(0, -(rr((zA + zB) / 2) - 0.015), zA - 0.02), mat="metal_bare", base=True)
        b.rot(z=a)
    if detail():
        for i in range(ribs):
            a = math.radians(360 * (i + 0.5) / ribs)
            cyl(0.022, 0.018, 6, at=(math.cos(a) * (R0 - 0.045), math.sin(a) * (R0 - 0.045), 0.06), mat="metal_bare", start=0.0)
        for i in range(ribs):
            a = 360 * (i + 0.5) / ribs
            s = box(0.04, 0.02, (h - 0.08) - (zB + 0.08), at=(0, 0, 0), mat="black", base=True)
            ang = math.degrees(math.atan2(rr(zB) - r_top, h - zB))
            s.rot(x=-ang).move(0, -(rr(zB + 0.07) + 0.004), zB + 0.07).rot(z=a)
        for i in range(4):
            a = 360 * i / 4 + 45
            pl = box(0.36 * max(1, r_top ** 0.5), 0.02, 0.08, at=(0, 0, 0), mat="emit_strip_cyan" if ring == "emit_cyan" else "emit_strip_violet", base=True)
            ang = math.degrees(math.atan2(rr(0.12) - rr(zA - 0.05), zA - 0.17))
            pl.rot(x=-ang).move(0, -(rr((zA + 0.12) / 2) + 0.004), (zA + 0.12) / 2 - 0.04).rot(z=a)
    return {"colliders": [{"type": "capsule", "center": [0, h / 2, 0], "radius": r_bot, "height": h, "direction": "Y"}]}


# ============================================================================================== core chamber
_MACH_PEAK = {12.0: 11.4, 16.0: 15.2, 20.0: 19.12}


def _mach_cell(z0, h, glow, panel, rnd):
    """One reactor cell on the machinery front (local face space, z out of the body face)."""
    f = box(3.0, h, 0.16, at=(0, z0 + h / 2, 0), base=True, mat="metal_dark", bevel=0.03)
    inset(f, faces_where(f, lambda q: q.normal.z > 0.9), 0.22, -0.1, mat=GD)
    box(0.16, h - 0.5, 0.04, at=(0, z0 + h / 2, 0.06), base=True, mat=glow)
    for x in (-0.62, 0.62):
        box(0.05, h - 0.6, 0.03, at=(x, z0 + h / 2, 0.06), base=True, mat=glow)
    for x in (-0.35, 0.35):
        box(0.05, h - 0.5, 0.06, at=(x, z0 + h / 2, 0.06), base=True, mat=CH)
    # read-out display + bar graphs behind the glass
    box(0.42, 0.3, 0.015, at=(0.98, z0 + h - 0.45, 0.06), base=True, mat=panel)
    if detail():
        for k in range(3):
            led_bar(-1.18, -0.8, z0 + h - 0.4 - k * 0.09, h=0.04, segs=5, lit=rnd.randint(1, 5), z=0.06, mat=glow)
        bolts([(x, z0 + y) for x in (-1.39, 1.39) for y in (0.11, h - 0.11)], r=0.03, h=0.015, z=0.16)


def core_machinery(H=12.0, strip="emit_strip_cyan", mat="metal_dark", seed=1):
    """Reactor machinery block facing the arena (Blender -Y): pilasters, chrome coolant risers with flanges, stacked
    reactor cells with glowing conduits behind dark glass, manifolds, coolant lines, LED read-outs, heat-sink crown,
    sagging cable loom. Base 1 m below the floor; outer extents as the prototype."""
    rnd = random.Random(seed)
    W, D = 5.8, 2.0
    top = H - 1.0
    peak = _MACH_PEAK.get(H, top + 0.2)
    glow = strip or "emit_strip_blue"
    panel = {"emit_strip_cyan": "emit_panel_cyan", "emit_strip_violet": "emit_panel_violet"}.get(glow, "emit_panel_white")
    yf = -D / 2
    # body (slightly narrower; side ribs reach the 5.8 m extent)
    box(W - 0.3, D, H, at=(0, 0, -1.0), mat=mat, base=True, bevel=0.05)
    for sx in (-1, 1):
        for k in range(int(H / 1.6)):
            z = -0.6 + k * 1.6
            box(0.15, D - 0.3, 0.2, at=(sx * 2.825, 0.1, z), mat="metal_dark", base=True)
        box(0.15, 0.3, H - 0.2, at=(sx * 2.825, 0.85, -1.0), mat="metal_dark", base=True)
        # pilasters
        p = box(0.6, 0.12, H - 0.4, at=(sx * 2.6, yf - 0.06, -1.0), mat="metal_dark", base=True, bevel=0.03)
        inset(p, faces_where(p, lambda f: f.normal.y < -0.9), 0.08, -0.02, mat="metal_plate")
        for k in range(int((H - 1.0) / 1.5)):
            box(0.6, 0.06, 0.12, at=(sx * 2.6, yf - 0.15, 0.9 + k * 1.5), mat="metal_bare", base=True, bevel=0.01)
        with K.placed(front(sx * 2.6, yf - 0.1, 0)):
            for k in range(int((H - 4.0) / 3.2)):
                z = 1.6 + k * 3.2
                box(0.4, 0.7, 0.02, at=(0, z, 0), base=True, mat="black")
                for j in range(4):
                    led_bar(-0.15, 0.15, z - 0.24 + j * 0.16, h=0.05, segs=4, lit=rnd.randint(1, 4), z=0.02,
                            mat=glow if j else "emit_amber")
        # coolant risers with flanges and clamps
        cyl(0.17, top - 0.6 + 1.0, 16, at=(sx * 1.85, -1.22, -1.0), mat=CH)
        for k in range(int((top - 0.8) / 2.6) + 1):
            z = 0.2 + k * 2.6
            lathe([(0.17, z - 0.07), (0.23, z - 0.05), (0.23, z + 0.05), (0.17, z + 0.07)], 16, at=(sx * 1.85, -1.22, 0), mat="metal_bare",
                  close_bottom=False, close_top=False)
            box(0.5, 0.24, 0.14, at=(sx * 1.85, -1.1, z + 0.6), mat="metal_dark", base=True)
        lathe([(0.17, top - 0.62), (0.24, top - 0.55), (0.24, top - 0.35), (0.001, top - 0.3)], 16, at=(sx * 1.85, -1.22, 0), mat="metal_dark")
    # base plinth with hazard chevrons + vents
    box(W - 0.3, 0.4, 1.8, at=(0, yf - 0.2 + 0.001, -1.0), mat="metal_dark", base=True, bevel=0.04)
    hazard_band(-2.2, 2.2, 0.08, 0.5, yf - 0.4, stripe=0.32)
    with K.placed(front(0, yf - 0.4, 0)):
        for x in (-1.0, 1.0):
            vent(1.2, 0.18, at=(x, 0.66), depth=0.025, t=0.025)
    # stacked reactor cells + manifolds between them
    z = 0.95
    ncell = 0
    while z + 1.2 < top - 1.6:
        h = 2.4 if ncell % 2 == 0 else 2.0
        if z + h + 0.34 > top - 1.6:
            h = top - 1.6 - z - 0.36
        with K.placed(front(0, yf, 0)):
            _mach_cell(z, h, glow, panel, rnd)
        mz = z + h + 0.02
        box(3.2, 0.3, 0.32, at=(0, yf - 0.15, mz), mat="metal_bare", base=True, bevel=0.03)
        if detail():
            with K.placed(front(0, yf - 0.3, 0)):
                bolt_line(-1.45, 1.45, mz + 0.16, 8, r=0.03, h=0.015)
            for sx in (-1, 1):
                tube([(sx * 1.67, -1.22, mz + 0.16), (sx * 1.55, -1.22, mz + 0.16)], 0.06, 8, "metal_bare")
                cable([(sx * 1.8, -1.4, mz - 0.5), (sx * 1.45, -1.35, mz - 0.45), (sx * 1.2, -1.32, mz - 0.1), (sx * 1.15, -1.3, mz + 0.1)],
                      r=0.035, n=6, mat="rubber", sag=0.03, steps=4)
        z = mz + 0.4
        ncell += 1
    # vertical glowing conduit between the cells (fills the remaining height up to the crown)
    if top - 1.6 - z > -0.1:
        box(0.12, 0.04, top - 1.6 - z + 0.3, at=(0, yf - 0.02, z - 0.3), mat=glow, base=True)
        for sx in (-1, 1):
            box(0.05, 0.14, top - 1.6 - z + 0.3, at=(sx * 0.12, yf - 0.07, z - 0.3), mat=CH, base=True)
    # heat-sink crown
    box(W - 0.3, 0.24, 1.1, at=(0, yf - 0.12 + 0.001, top - 1.5), mat="metal_dark", base=True, bevel=0.03)
    with K.placed(front(0, yf - 0.24, 0)):
        for i in range(13):
            box(0.07, 0.8, 0.14, at=(-2.1 + i * 0.35, top - 0.95, 0), base=True, mat="metal_bare", bevel=0.01)
        box(4.5, 0.82, 0.01, at=(0, top - 0.95, 0), base=True, mat="black")
        box(4.4, 0.04, 0.02, at=(0, top - 1.44, 0), base=True, mat=glow)
        box(4.4, 0.04, 0.02, at=(0, top - 0.46, 0), base=True, mat=glow)
    # roof: exhaust housings / cap up to the prototype's peak height
    ph = peak - top
    for sx in (-1, 1):
        cyl(0.42, ph, 16, at=(sx * 1.4, 0.1, top), mat="metal_bare")
        cyl(0.3, 0.004, 16, at=(sx * 1.4, 0.1, peak - 0.002), mat="black")
    box(1.2, 1.2, ph * 0.6, at=(0, 0.2, top), mat="metal_dark", base=True)
    # sagging cable loom across the crown (front-most part: y = -1.48)
    cable([(-2.6, -1.1, top - 1.5), (-1.2, -1.4, top - 2.2), (1.2, -1.4, top - 2.2), (2.6, -1.1, top - 1.5)], r=0.08, n=8, mat="rubber")
    if detail():
        cable([(-2.5, -1.12, top - 1.6), (0.0, -1.33, top - 1.75), (2.5, -1.12, top - 1.6)], r=0.05, n=6, sag=0.35, steps=6)
        for x in (-1.2, 1.2):
            box(0.2, 0.2, 0.2, at=(x, -1.36, top - 2.3), mat="metal_dark", bevel=0.02)
    return {"colliders": [K.collider_box((0, 0, H / 2 - 1.0), (W, D, H))], "pivotNote": "base at y=-1 (prototype embeds 1 m below the floor)"}


def core_tether_anchor():
    n = 24
    R0 = rx(1.2346, n)
    lathe([(0.001, 0.0), (R0, 0.0), (R0, 0.1), (1.18, 0.15), (1.12, 0.2), (0.001, 0.2)], n, mat=CH)
    lathe([(1.12, 0.18), (1.1, 0.24), (0.92, 1.3), (0.001, 1.3)], n, mat="metal_dark", close_bottom=False)
    lathe([(0.98, 1.28), (0.98, 1.42), (0.95, 1.46), (0.001, 1.46)], n, mat=CH)
    lathe([(0.95, 1.44), (0.95, 1.6), (0.001, 1.6)], n, mat=CB, close_bottom=False)
    torus(0.62, 0.05, n_major=24, n_minor=6, mat="emit_cyan").move(0, 0, 1.62)
    torus(0.42, 0.025, n_major=24, n_minor=4, mat=CH).move(0, 0, 1.61)
    torus(0.82, 0.02, n_major=24, n_minor=4, mat=CH).move(0, 0, 1.6)
    lathe([(0.34, 1.58), (0.3, 1.65), (0.18, 1.69), (0.001, 1.7)], 16, mat="emit_cyan")
    # glowing slits between the clamp arms (recessed carbon panels)
    ang = math.degrees(math.atan2(1.1 - 0.92, 1.06))
    for i in range(4):
        pn = box(0.34, 0.04, 0.82, mat=CB, base=True, bevel=0.01)
        pn.rot(x=-ang).move(0, -1.0, 0.36).rot(z=i * 90)
        s = box(0.06, 0.03, 0.66, mat="emit_cyan", base=True)
        s.rot(x=-ang).move(0, -1.03, 0.44).rot(z=i * 90)
    # clamp arms with yellow lock plates and twin rams
    for i in range(4):
        with K.placed(rz=45 + i * 90):
            c = box(0.3, 0.3, 1.1, mat="metal_bare", base=True, bevel=0.03)
            c.rot(x=-12).move(0, -1.05, 0.12)
            cp = box(0.36, 0.08, 0.4, mat="metal_painted_yellow", base=True, bevel=0.015)
            cp.rot(x=-12).move(0, -1.2, 0.3)
            if detail():
                for k in (-1, 1):
                    piston((k * 0.22, -1.08, 0.25), (k * 0.2, -0.86, 1.25), 0.045, 0.025, n=8)
    if detail():
        for i in range(16):
            a = math.radians(i * 22.5 + 11.25)
            cyl(0.025, 0.02, 6, at=(math.cos(a) * 1.16, math.sin(a) * 1.16, 0.14), mat="metal_bare", start=0.0)
    return {"colliders": [{"type": "capsule", "center": [0, 0.8, 0], "radius": 1.2, "height": 1.6, "direction": "Y"}], "tetherOrigin": K.to_unity_vec((0, 0, 1.7))}


def core_ring(R=8.0, arc=288.0, glow="emit_cyan"):
    """Broken orbit ring: segmented scratched-chrome armour with emissive gaps over a glowing core, carbon inlays on
    the outer face, dark clamp collars (the collars keep the prototype's outer extent)."""
    n = int(arc / 24)
    half = arc / n / 2                            # segment span (deg): gaps at every half step
    gap = math.degrees(0.3 / R)                   # 30 cm glowing gap
    # glowing core visible in the gaps
    torus(R, 0.12, arc=arc, n_major=K.seg(72), n_minor=5, mat=glow)
    sec = [(-0.215, -0.16), (-0.245, -0.12), (-0.245, 0.12), (-0.215, 0.16), (0.215, 0.16), (0.245, 0.12), (0.245, -0.12), (0.215, -0.16)]
    inlay = [(0.2, -0.07), (0.249, -0.07), (0.249, 0.07), (0.2, 0.07)]
    steps = 3 if K.LOD == 0 else 2
    nseg = n * 2
    for i in range(nseg):
        a0 = i * half + (gap / 2 if i > 0 else 0.0)
        a1 = (i + 1) * half - (gap / 2 if i < nseg - 1 else 0.0)
        arc_sweep(sec, a0, a1, steps, CH, R=R)
        am = (a0 + a1) / 2
        arc_sweep([(-0.252, -0.025), (-0.235, -0.025), (-0.235, 0.025), (-0.252, 0.025)], am - (a1 - a0) * 0.3, am + (a1 - a0) * 0.3, 2, glow, R=R)
        if detail():
            arc_sweep(inlay, a0 + 1.0, a1 - 1.0, steps, CB, R=R)
    if detail():
        for i in range(n):
            a = arc * (i + 0.5) / n
            c = cyl(0.3, 0.2, 12, mat="metal_dark", center=True, axis="Y")
            c.move(R, 0, 0).rot(z=a)
            c2 = cyl(0.27, 0.32, 10, mat="metal_bare", center=True, axis="Y")
            c2.move(R, 0, 0).rot(z=a)
            for k in (-1, 1):
                b = box(0.05, 0.08, 0.06, mat=glow)
                b.move(R - 0.27, k * 0.06, 0).rot(z=a)
    # broken ends: exposed core stubs
    for a, d in ((0.0, -1), (arc, 1)):
        c = cyl(0.13, 0.25, 8, mat="metal_dark", center=True, axis="Y")
        c.move(R, d * 0.1, 0).rot(z=a)
    return {"colliders": "mesh", "radius": R, "arcDeg": arc}


def _floor_ring(r0, r1, z, n, mat):
    p = K._new(mat, "ann")
    bm = p.bm
    a0 = [bm.verts.new((r0 * math.cos(math.tau * i / n), r0 * math.sin(math.tau * i / n), z)) for i in range(n)] if r0 > 0 else None
    a1 = [bm.verts.new((r1 * math.cos(math.tau * i / n), r1 * math.sin(math.tau * i / n), z)) for i in range(n)]
    if a0 is None:
        bm.faces.new(a1)
    else:
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a0[i], a0[j], a1[j], a1[i]))
    return p


def core_arena_floor(R=27.0):
    """54 m arena disc: chamfered plate tiles (alternating plate / carbon) over a dark sub-layer, concentric and radial
    light channels, grating ring over a lit sub-floor, LED rim curb, rim wall. Top of the plates = 0."""
    n = K.seg(96, 48)
    dz = -0.04
    glow = "emit_strip_cyan"
    if K.LOD == 0:
        _floor_ring(0.0, 20.0, dz, n, "metal_dark")
        _floor_ring(24.0, R, dz, n, "metal_dark")
        bands = [(4.2, 12.0, 2, 24, "metal_plate"), (12.4, 19.6, 2, 32, "metal_plate"), (24.4, 26.3, 1, 48, "metal_plate")]
        _floor_ring(0.0, 3.9, 0.0, n, "metal_plate")
        for i in range(8):
            b = box(3.6, 0.03, 0.004, at=(1.8, 0, 0.001), mat="metal_dark")
            b.rot(z=i * 45 + 22.5)
        for (r0, r1, rows, sectors, m) in bands:
            for row in range(rows):
                ra = r0 + (r1 - r0) * row / rows + (0.03 if row else 0.0)
                rb = r0 + (r1 - r0) * (row + 1) / rows - (0.03 if row < rows - 1 else 0.0)
                c = 0.02
                prof = [(ra, dz), (rb, dz), (rb, -c), (rb - c, 0.0), (ra + c, 0.0), (ra, -c)]
                for s in range(sectors):
                    wide = (s % (sectors // 8) == 0)
                    g = (0.09 if wide else 0.025) / ((ra + rb) / 2)
                    a0 = 360.0 * s / sectors + math.degrees(g)
                    a1 = 360.0 * (s + 1) / sectors - (math.degrees(0.025 / ((ra + rb) / 2)))
                    st = max(2, int((a1 - a0) / 3.0))
                    mt = CB if (s + row) % 3 == 0 else m
                    arc_sweep(prof, a0, a1, st, mt, R=0.0)
            # radial light channels in the wide gaps
            for k in range(8):
                a = 360.0 * k / 8
                L = r1 - r0
                s = box(L - 0.1, 0.05, 0.01, at=(r0 + L / 2, 0, dz + 0.005), mat=glow)
                s.rot(z=a + math.degrees(0.0325 / ((r0 + r1) / 2)))
        # concentric light channels
        for (r0, r1) in ((3.9, 4.2), (12.0, 12.4), (19.6, 20.0), (24.0, 24.4)):
            rm = (r0 + r1) / 2
            _floor_ring(rm - 0.04, rm + 0.04, dz + 0.012, n, glow)
            _floor_ring(r0, r0 + 0.03, -0.005, n, CH)
            _floor_ring(r1 - 0.03, r1, -0.005, n, CH)
        # LED rim curb
        _floor_ring(26.3, R, 0.0, n, "metal_dark")
    else:
        rings = [(0.0, 3.9, "metal_plate"), (3.9, 4.2, "metal_dark"), (4.2, 12.0, "metal_plate"), (12.0, 12.4, "metal_dark"), (12.4, 19.6, "metal_plate"),
                 (19.6, 20.0, "metal_dark"), (24.0, 24.4, "metal_dark"), (24.4, R, "metal_plate")]
        for (r0, r1, m) in rings:
            _floor_ring(r0, r1, 0.0, n, m)
        for rm in (4.05, 12.2, 19.8, 24.2):
            _floor_ring(rm - 0.04, rm + 0.04, 0.002, n, glow)
    # grating ring over a lit sub-floor
    _floor_ring(20.0, 24.0, -0.005, n, "grating")
    _floor_ring(20.0, 24.0, -0.4, n, "metal_dark")
    lathe([(20.0, -0.4), (20.0, -0.04)], n, mat="metal_dark", close_bottom=False, close_top=False)
    lathe([(24.0, -0.04), (24.0, -0.4)], n, mat="metal_dark", close_bottom=False, close_top=False)
    for rm in (21.0, 22.0, 23.0):
        _floor_ring(rm - 0.05, rm + 0.05, -0.385, n, glow if rm == 22.0 else "metal_bare")
    if K.LOD == 0:
        for i in range(48):
            b = box(4.0, 0.12, 0.3, at=(22.0, 0, -0.4), mat="metal_dark", base=True)
            b.rot(z=i * 7.5)
    # rim wall and the 24 LED rim strips (raised 6 cm curb lights)
    lathe([(R, 0.0), (R + 0.5, -0.1), (R + 0.5, -1.0)], n, mat="metal_dark", close_bottom=False, close_top=False)
    for i in range(24):
        a = 360 * i / 24
        hs = box(0.4, 6.6, 0.04, at=(0, 0, 0), mat="metal_dark", base=True)
        hs.move(R - 0.4, 0, 0.0).rot(z=a)
        s = box(0.12, 6.4, 0.06, at=(0, 0, 0), mat=glow, base=True)
        s.move(R - 0.4, 0, 0.0).rot(z=a)
        if K.LOD == 0:
            for k in (-1, 1):
                c = box(0.42, 0.1, 0.05, at=(0, 0, 0), mat=CH, base=True)
                c.move(R - 0.4, k * 3.25, 0.0).rot(z=a)
    return {"colliders": [{"type": "cylinder", "center": [0, -0.5, 0], "radius": R, "height": 1.0, "note": "use a MeshCollider on LOD1 or a flat box + ring walls"}]}


def core_cover_block(L=3.0, H=1.6, D=1.4, seed=1):
    """Machined cover block: dark core, chrome corner guards, plate armour with recessed seams, cyan LED channel
    under the top lip, chevrons at the foot, top grip plate; the same debris chunks as the prototype."""
    box(L - 0.12, D - 0.12, H, mat="metal_dark", base=True, bevel=0.05)
    for sy in (-1, 1):
        p = box(L - 0.5, 0.06, H - 0.55, at=(0, sy * (D / 2 - 0.03), 0.3), mat="metal_bare", base=True, bevel=0.02)
        inset(p, faces_where(p, lambda f, sy=sy: f.normal.y * sy > 0.9), 0.08, -0.02, mat="metal_plate")
        box(L - 0.6, 0.02, 0.045, at=(0, sy * (D / 2 - 0.05), H - 0.19), mat="emit_strip_cyan", base=True)
    for sx in (-1, 1):
        e = box(0.06, D - 0.5, H - 0.55, at=(sx * (L / 2 - 0.03), 0, 0.3), mat="metal_bare", base=True, bevel=0.02)
        inset(e, faces_where(e, lambda f, sx=sx: f.normal.x * sx > 0.9), 0.08, -0.02, mat="metal_plate")
        for sy in (-1, 1):
            box(0.24, 0.045, H - 0.06, at=(sx * (L / 2 - 0.12), sy * (D / 2 - 0.0225), 0.03), mat=CH, base=True, bevel=0.01)
            box(0.045, 0.24, H - 0.06, at=(sx * (L / 2 - 0.0225), sy * (D / 2 - 0.12), 0.03), mat=CH, base=True, bevel=0.01)
    hazard_band(-L / 2 + 0.3, L / 2 - 0.3, 0.06, 0.25, -(D / 2 - 0.06), stripe=0.18)
    with K.placed(rz=180):
        hazard_band(-L / 2 + 0.3, L / 2 - 0.3, 0.06, 0.25, -(D / 2 - 0.06), stripe=0.18)
    if detail():
        for sy in (-1, 1):
            with K.placed(frame((0, sy * D / 2, 0), right=(sy * -1, 0, 0))):
                bolt_line(-L / 2 + 0.35, L / 2 - 0.35, 0.36, 6, r=0.022, h=0.012)
                bolt_line(-L / 2 + 0.35, L / 2 - 0.35, H - 0.31, 6, r=0.022, h=0.012)
        rnd = random.Random(seed)
        box(L * 0.9, D * 0.4, 0.06, at=(0, 0, H), mat="metal_dark", base=True, bevel=0.015)
        for i in range(3):
            rock((0.3, 0.25, 0.15), seed + i, cuts=8, mat="metal_dark").move(rnd.uniform(-L / 2, L / 2), rnd.uniform(-D, -D / 2), 0.075)
    else:
        box(L * 0.9, D * 0.4, 0.06, at=(0, 0, H), mat="metal_dark", base=True)
    return {"colliders": [K.collider_box((0, 0, H / 2), (L, D, H))]}


ASSETS = {
    "Vault_BlastDoor": dict(fn=blast_door, cat="vault", zones=["vault"],
                            notes="16 x 10 x 0.8 vertical-lift blast door (hero): five lift segments, yellow lock columns with ten chrome locking bolts, "
                                  "four carbon armour plates, central lock hub with LED ring, four hydraulic rams, LED read-outs, glyph plates, vents, "
                                  "hazard chevrons front and back. 8 light sockets on the top rail (place Vault_BlastDoor_Light at 'lightSockets')."),
    "Vault_BlastDoor_Light": dict(fn=blast_door_light, cat="vault", zones=["vault"], pivot="top-centre",
                                  notes="Indicator lens (emit_red, segmented) in a lipped bezel; swap/tint the emit_red slot per light for the countdown."),
    "Vault_BlastDoor_Frame": dict(fn=blast_door_frame, cat="vault", zones=["vault"],
                                  notes="Surround for the 16 x 10 opening: armoured columns with hydraulic rams, hoses, red LED guide slots and read-outs, "
                                        "hazard bands, glyph-crest header with red LED slits and vents, amber beacons."),
    "Vault_LockDoor_Half": dict(fn=lock_door_half, cat="vault", zones=["vault"],
                                notes="Resonance lock door leaf 3 x 5 x 0.5. Violet seam strip on its +X edge (Unity); violet half-rings on both faces "
                                      "complete one circle when the leaves close. Left leaf at x=-1.5; right leaf = same asset rotated 180 deg at x=+1.5."),
    "Vault_Wall_Panel_4m": dict(fn=vault_wall_panel, cat="vault", zones=["vault"], pivot="wall-base",
                                notes="Heavy 4 x 4 wall panel: half pilasters (tile edge to edge), armour bays around a recessed violet light channel, "
                                      "lit base and cornice channels, cable loom, vents, glyph tag. Front face at z=+0.12 (Unity), back flush at -0.4."),
    "Vault_Wall_Panel_4m_Cyan": dict(fn=vault_wall_panel, kw={"strip": "emit_strip_cyan"}, cat="vault", zones=["vault", "core"], pivot="wall-base",
                                     notes="Cyan light-channel variant."),
    "Vault_ResonatorPillar": dict(fn=resonator_pillar, cat="vault", zones=["vault"],
                                  notes="Resonator column 2.9 m: chrome flange, glowing violet coil chamber in a chrome cage, carbon shaft with violet inlays, "
                                        "crystal cradle. Put Vault_ResonatorRing at y=2.2 and Vault_Crystal at y=3.1."),
    "Vault_ResonatorRing": dict(fn=resonator_ring, cat="vault", zones=["vault"], pivot="centre",
                                notes="Four quarter-ring segments (R 0.75), horizontal, material emit_violet (tint per state), chrome/carbon clamps. Rotates about Y in game."),
    "Vault_Crystal": dict(fn=crystal, cat="vault", zones=["vault", "plaza"], pivot="centre", notes="Small faceted Aether crystal (aether_energy), 0.7 m tall."),
    "Vault_GlyphPlate": dict(fn=glyph_plate, cat="vault", zones=["vault"], pivot="back-centre",
                             notes="Hexagonal glyph plaque (r 1.0): carbon field, dark-glass core, chrome rim, violet hex ring; glyph marks drawn by the game at 'glyphCenter'."),
    "Vault_Pedestal_Relic": dict(fn=pedestal, kw={"r_bot": 1.0, "r_top": 0.8, "h": 1.0}, cat="vault", zones=["vault"],
                                 notes="Relic pedestal (secret room): chrome / carbon, violet coil band and ring."),
    "Vault_Pedestal_Attunement": dict(fn=pedestal, kw={"r_bot": 2.0, "r_top": 1.6, "h": 1.2, "ring": "emit_cyan", "ribs": 16}, cat="vault", zones=["vault"],
                                      notes="Attunement chamber pedestal r 2.0, cyan coil band and ring."),
    "Holo_Pedestal": dict(fn=pedestal, kw={"r_bot": 2.8, "r_top": 2.6, "h": 0.8, "ring": "emit_cyan", "ring_r": 2.2, "ribs": 24}, cat="facility", zones=["facility"],
                          notes="Atrium hologram base r 2.8, cyan emitter ring r 2.2, glowing coil band."),
    "Core_Pedestal": dict(fn=pedestal, kw={"r_bot": 3.8, "r_top": 3.2, "h": 1.2, "ring": "emit_cyan", "ring_r": 2.6, "mat": "metal_bare", "ribs": 24}, cat="core", zones=["core"],
                          notes="Heart pedestal under the Aether Core."),
    "Core_Machinery_12m": dict(fn=core_machinery, kw={"H": 12.0}, cat="core", zones=["core"], pivot="base-1m",
                               notes="Reactor machinery block 5.8 x 12 x 2 (hero): coolant risers, reactor cells with cyan conduits behind dark glass, "
                                     "LED read-outs, heat-sink crown, cable loom; facing +Z (toward the arena centre). Base sits 1 m below floor (y=-1)."),
    "Core_Machinery_16m": dict(fn=core_machinery, kw={"H": 16.0, "strip": "emit_strip_violet", "mat": "metal_bare", "seed": 2}, cat="core", zones=["core"], pivot="base-1m",
                               notes="16 m variant, violet conduits."),
    "Core_Machinery_20m": dict(fn=core_machinery, kw={"H": 20.0, "strip": None, "seed": 3}, cat="core", zones=["core"], pivot="base-1m",
                               notes="20 m variant, electric-blue conduits."),
    "Core_TetherAnchor": dict(fn=core_tether_anchor, cat="core", zones=["core"], notes="Floor anchor for an energy tether: chrome flange, clamp arms with rams, cyan slits and emitter crown; 'tetherOrigin' = beam start."),
    "Core_Ring_A": dict(fn=core_ring, kw={"R": 8.0, "arc": 288.0}, cat="core", zones=["core"], pivot="centre", notes="Broken orbit ring R 8, 288 deg: segmented chrome, cyan core glowing in the gaps (horizontal; game rotates)."),
    "Core_Ring_B": dict(fn=core_ring, kw={"R": 9.6, "arc": 342.0, "glow": "emit_violet"}, cat="core", zones=["core"], pivot="centre", notes="R 9.6, 342 deg, violet."),
    "Core_Ring_C": dict(fn=core_ring, kw={"R": 11.2, "arc": 288.0}, cat="core", zones=["core"], pivot="centre", notes="R 11.2, 288 deg, cyan."),
    "Core_Ring_D": dict(fn=core_ring, kw={"R": 12.8, "arc": 342.0, "glow": "emit_violet"}, cat="core", zones=["core"], pivot="centre", notes="R 12.8, 342 deg, violet."),
    "Core_ArenaFloor": dict(fn=core_arena_floor, cat="core", zones=["core"], pivot="top-centre",
                            notes="54 m arena disc (hero): chamfered plate / carbon tiles, concentric + radial cyan light channels, grating ring (r 20-24) "
                                  "over a lit sub-floor, rim wall, 24 cyan rim curb lights."),
    "Core_CoverBlock": dict(fn=core_cover_block, cat="core", zones=["core"], notes="Machined metal cover block 3 x 1.6 x 1.4: chrome corner guards, cyan LED channel."),
    "Core_CoverBlock_Large": dict(fn=core_cover_block, kw={"L": 4.0, "H": 2.2, "seed": 2}, cat="core", zones=["core"], notes="4 x 2.2 x 1.4 cover block."),
}
