"""Street / civic props: barriers, crates, street lights, benches, bins, signage, market & camp props.

Cyberpunk restyle: every asset keeps its name, pivot, outer size, colliders, metadata anchors and baseline material
slots (zone code swaps the emit_* / screen slots), but is rebuilt with layered detail: faceted carbon / glossy
bodies, LED strips, neon glyph signage (invented glyphs, same grammar as matdefs_hd.glyph), hazard chevrons,
bolts, cable runs and brackets. Small parts only exist at LOD0 (K.detail()).
"""
import math
import random

from mathutils import Euler, Matrix, Vector

import envkit as K
from envkit import box, cyl, tube, torus, beam, extrude, lathe, rock, boolean, inset, faces_where, detail


# ============================================================================================== detail kit
def _xf(x=0.0, y=0.0, z=0.0, rx=0.0, ry=0.0, rz=0.0):
    """4x4 transform for K.placed(): rotate (degrees, XYZ) then translate."""
    return Matrix.Translation((x, y, z)) @ Euler((math.radians(rx), math.radians(ry), math.radians(rz))).to_matrix().to_4x4()


def _aim(p, n):
    """Rotate a part built along +Z so that +Z points along n."""
    q = Vector((0, 0, 1)).rotation_difference(Vector(n).normalized())
    return p.xform(q.to_matrix().to_4x4())


def _bolt(at, n=(0, 0, 1), r=0.011, h=0.008, mat="metal_bare", washer=False):
    """Hex bolt head standing on a surface at `at`, pointing along normal n (LOD0 only)."""
    if not detail():
        return
    ps = [cyl(r, h, 6, mat=mat, start=0, name="bolt")]
    if washer:
        ps.append(cyl(r * 1.45, h * 0.3, 8, mat=mat, name="washer"))
    for p in ps:
        _aim(p, n).move(*at)


def _prism(profile, n=8, mat="metal_dark", name="prism", rx=1.0):
    """Faceted lathe [(r, z), ...] with n flats (no LOD reduction, flats face the axes for n=8/4)."""
    secs = []
    for r, z in profile:
        secs.append([(r * rx * math.cos(math.pi / n + k * math.tau / n), r * math.sin(math.pi / n + k * math.tau / n), z) for k in range(n)])
    return K.loft(secs, mat=mat, name=name)


def _apo(r, n=8):
    """Apothem (flat distance) of an n-gon prism of circumradius r."""
    return r * math.cos(math.pi / n)


def _tbeam(a, b, w0, h0, w1=None, h1=None, mat="metal_dark", side=(1, 0, 0), bevel=0.0, name="tbeam"):
    """Tapered rectangular beam from a to b. Width runs along `side`, height along side x dir."""
    a, b = Vector(a), Vector(b)
    w1 = w0 if w1 is None else w1
    h1 = h0 if h1 is None else h1
    d = (b - a).normalized()
    sx = Vector(side)
    sx = (sx - d * sx.dot(d)).normalized()
    sz = sx.cross(d).normalized()
    secs = []
    for c, w, h in ((a, w0, h0), (b, w1, h1)):
        secs.append([tuple(c + sx * (w / 2) * i + sz * (h / 2) * j) for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    p = K.loft(secs, mat=mat, name=name)
    if bevel:
        p.bevel(bevel, 1, angle=30)
    return p


def _clip(poly, x0, x1, y0, y1):
    """Sutherland-Hodgman clip of a 2D polygon against an axis-aligned rect."""
    def edge(pts, inside, cut):
        out = []
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            if inside(b):
                if not inside(a):
                    out.append(cut(a, b))
                out.append(b)
            elif inside(a):
                out.append(cut(a, b))
        return out

    def cx(c):
        return lambda a, b: (c, a[1] + (b[1] - a[1]) * (c - a[0]) / (b[0] - a[0]))

    def cy(c):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (c - a[1]) / (b[1] - a[1]), c)
    pts = list(poly)
    for inside, cut in ((lambda p: p[0] >= x0, cx(x0)), (lambda p: p[0] <= x1, cx(x1)),
                        (lambda p: p[1] >= y0, cy(y0)), (lambda p: p[1] <= y1, cy(y1))):
        if len(pts) < 3:
            return []
        pts = edge(pts, inside, cut)
    out = []
    for q in pts:
        if not out or abs(q[0] - out[-1][0]) + abs(q[1] - out[-1][1]) > 1e-5:
            out.append(q)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) + abs(out[0][1] - out[-1][1]) < 1e-5:
        out.pop()
    return out if len(out) >= 3 else []


def _stripes(w, h, pitch=0.1, frac=0.5, slant=0.6, depth=0.004, mat="metal_painted_yellow", chevron=False, back=None):
    """Hazard stripes / chevrons on a w x h rect in the XZ plane (x centred, z from 0), raised toward -Y from y=0.
    back: optional backing-plate material (thin plate behind the stripes)."""
    t = pitch * frac
    sl = slant * h
    if back:
        box(w, depth * 0.6, h, at=(0, -depth * 0.3, h / 2), mat=back, name="hzback")
    s = -w / 2 - abs(sl) - pitch
    while s < w / 2 + pitch:
        if chevron:
            a = sl / 2
            poly = [(s, 0), (s + t, 0), (s + t + a, h / 2), (s + t, h), (s, h), (s + a, h / 2)]
        else:
            poly = [(s, 0), (s + t, 0), (s + t + sl, h), (s + sl, h)]
        c = _clip(poly, -w / 2, w / 2, 0, h)
        if c:
            extrude(c, depth, plane="XZ", mat=mat, name="stripe").move(0, -depth / 2 - (depth * 0.6 if back else 0), 0)
        s += pitch


def _glyph_strokes(rng):
    """Invented glyph as polylines in 0..1 (same radical grammar as matdefs_hd.glyph): roof bar, two stems,
    enclosure box or crossing diagonals, mid bar, 1-2 ticks. Returns [(points, closed), ...]."""
    cl = lambda v: min(0.97, max(0.03, v))
    S = []
    top = rng.uniform(0.78, 0.9)
    S.append(([(rng.uniform(0.08, 0.2), top), (rng.uniform(0.8, 0.92), top)], False))
    for x in sorted(rng.sample([0.22, 0.38, 0.5, 0.62, 0.78], 2)):
        S.append(([(x, rng.uniform(0.05, 0.3)), (x, rng.uniform(0.6, top))], False))
    if rng.random() < 0.6:
        x0, x1 = rng.uniform(0.15, 0.35), rng.uniform(0.65, 0.85)
        y0, y1 = rng.uniform(0.1, 0.3), rng.uniform(0.45, 0.62)
        S.append(([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], True))
    else:
        S.append(([(rng.uniform(0.1, 0.3), rng.uniform(0.1, 0.3)), (rng.uniform(0.55, 0.9), rng.uniform(0.45, 0.7))], False))
        S.append(([(rng.uniform(0.55, 0.9), rng.uniform(0.05, 0.25)), (rng.uniform(0.15, 0.45), rng.uniform(0.5, 0.7))], False))
    mid = rng.uniform(0.38, 0.6)
    S.append(([(rng.uniform(0.05, 0.25), mid), (rng.uniform(0.7, 0.95), mid + rng.uniform(-0.05, 0.05))], False))
    for _ in range(rng.randint(1, 2)):
        x, y = rng.uniform(0.1, 0.9), rng.uniform(0.15, 0.9)
        S.append(([(x, y), (cl(x + rng.uniform(-0.15, 0.15)), cl(y - rng.uniform(0.08, 0.15)))], False))
    return S


def _neon_glyph(rng, origin, ux, uy, size, r=0.006, mat="emit_neon_cyan", n=6):
    """One neon-tube glyph: origin = glyph's (0,0) corner, ux/uy = unit axes of the glyph plane, size = (w, h)."""
    o, ux, uy = Vector(origin), Vector(ux), Vector(uy)
    for pts, closed in _glyph_strokes(rng):
        P = [tuple(o + ux * (u * size[0]) + uy * (v * size[1])) for u, v in pts]
        tube(P, r, n, mat, name="neon", closed=closed)


def _fit(parts, pivot, xmin=None, xmax=None, ymin=None, ymax=None, zmin=None, zmax=None):
    """Stretch `parts` about `pivot` (per axis) so their extreme reaches the given target (keeps legacy extents)."""
    import numpy as np
    vs = np.array([v.co[:] for p in parts for v in p.bm.verts])
    mn, mx = vs.min(0), vs.max(0)
    sc = [1.0, 1.0, 1.0]
    for i, lo, hi in ((0, xmin, xmax), (1, ymin, ymax), (2, zmin, zmax)):
        if lo is not None and abs(mn[i] - pivot[i]) > 1e-6:
            sc[i] = (lo - pivot[i]) / (mn[i] - pivot[i])
        elif hi is not None and abs(mx[i] - pivot[i]) > 1e-6:
            sc[i] = (hi - pivot[i]) / (mx[i] - pivot[i])
    m = Matrix.Translation(pivot) @ Matrix.Diagonal((sc[0], sc[1], sc[2], 1.0)) @ Matrix.Translation(Vector(pivot) * -1)
    for p in parts:
        p.xform(m)
    return sc


def _fit_box(parts, x=None, y=None, z=None, xmax=None, ymax=None, zmax=None):
    """Scale+translate parts so their bounds hit (lo, hi) on the given axes; *max: translate only."""
    import numpy as np
    vs = np.array([v.co[:] for p in parts for v in p.bm.verts])
    mn, mx = vs.min(0), vs.max(0)
    sc, tr = [1.0, 1.0, 1.0], [0.0, 0.0, 0.0]
    for i, rng_, hi in ((0, x, xmax), (1, y, ymax), (2, z, zmax)):
        if rng_ is not None:
            sc[i] = (rng_[1] - rng_[0]) / max(1e-6, mx[i] - mn[i])
            tr[i] = rng_[0] - mn[i] * sc[i]
        elif hi is not None:
            tr[i] = hi - mx[i]
    m = Matrix.Translation(tr) @ Matrix.Diagonal((sc[0], sc[1], sc[2], 1.0))
    for p in parts:
        p.xform(m)


def _sag(a, b, sag, n=8):
    """Points of a sagging cable between a and b (parabolic droop of `sag` m at mid-span)."""
    a, b = Vector(a), Vector(b)
    return [tuple(a.lerp(b, i / n) - Vector((0, 0, sag * 4 * (i / n) * (1 - i / n)))) for i in range(n + 1)]


def _cable(points, r=0.008, mat="rubber", n=6):
    return tube(points, r, n, mat, name="cable")


def _led(a, b, w=0.012, h=0.006, mat="emit_strip_cyan", up=(0, 0, 1)):
    """Thin LED strip bar from a to b (w across, h thick)."""
    return beam(a, b, w, h, mat=mat, up=up, name="led")


def _vent(w, h, n, at, depth=0.006, mat="black", frame="metal_dark"):
    """Slotted vent grille facing -Y on a plane at y=at[1] (LOD0 only)."""
    if not detail():
        return
    x, y, z = at
    box(w, depth, h, at=(x, y - depth / 2, z), mat=frame, name="ventframe")
    for i in range(n):
        zz = z - h / 2 + (i + 0.5) * h / n
        box(w * 0.86, depth * 0.6, h / n * 0.45, at=(x, y - depth - depth * 0.3, zz), mat=mat, name="slot")


# ============================================================================================== barriers
JERSEY = [(0.305, 0.0), (0.305, 0.075), (0.13, 0.33), (0.078, 0.81)]  # NJ/F-shape half profile (y, z)


def _jersey_poly():
    return [(y, z) for y, z in JERSEY] + [(-y, z) for y, z in reversed(JERSEY)]


JERSEY_TILT = math.degrees(math.atan2(0.13 - 0.078, 0.81 - 0.33))   # upper face lean (deg)


def _jersey_y(z):
    """Half width of the jersey profile on its upper (sloped) face at height z."""
    return 0.13 + (0.078 - 0.13) * (z - 0.33) / 0.48


def _jersey_body(length, x0=0.0, mat="concrete", slots=True, grime=True):
    b = extrude(_jersey_poly(), length, plane="YZ", mat=mat, name="jersey")
    b.move(x0, 0, 0)
    if slots:
        for sx in (-length * 0.27, length * 0.27):
            boolean(b, box(0.32, 1.0, 0.2, at=(x0 + sx, 0, 0), mat="concrete_dark" if grime else mat))
    if grime:
        # road grime on the kerb band, rain-soaked crown
        b.set_mat("concrete_dark", where=lambda f: abs(f.normal.y) > 0.9 and f.calc_center_median().z < 0.08)
        b.set_mat("concrete_wet", where=lambda f: f.normal.z > 0.9 and f.calc_center_median().z > 0.8)
    return b


def _on_jersey_face(xc, z0, side):
    """Transform placing local XZ-plane geometry (facing -Y, bottom edge at z=0) onto the upper face of the jersey."""
    y = _jersey_y(z0) + 0.002
    return _xf(xc, -y, z0, rx=-JERSEY_TILT) if side < 0 else _xf(xc, y, z0, rx=-JERSEY_TILT, rz=180)


def _chevron_panel(w, h=0.16):
    """Reflective hazard chevron panel (local XZ plane facing -Y, bottom edge at z=0) with corner rivets."""
    box(w + 0.02, 0.004, h + 0.02, at=(0, -0.002, h / 2), mat="metal_dark", bevel=0.002)
    with K.placed(_xf(0, -0.004, 0.0)):
        _stripes(w, h, pitch=0.12, frac=0.5, slant=0.55, depth=0.003, chevron=True, back="black")
    if detail():
        for sx in (-1, 1):
            for z in (0.0, h):
                _bolt((sx * (w / 2 + 0.002), -0.006, z), n=(0, -1, 0), r=0.006, h=0.003)


def _blinker(lit=True):
    """Clip-on LED warning blinker (local: mounted on a -Y facing surface at the origin)."""
    box(0.13, 0.012, 0.15, at=(0, -0.006, 0.0), mat="metal_dark", bevel=0.003)
    cyl(0.074, 0.035, 16, at=(0, -0.047, 0.0), axis="Y", mat="plastic_dark")
    cyl(0.064, 0.008, 16, at=(0, -0.053, 0.0), axis="Y", mat="emit_amber" if lit else "black")
    if detail():
        hood = torus(0.077, 0.007, arc=180, n_major=10, n_minor=4, mat="plastic_dark")
        hood.rot(x=90).move(0, -0.05, 0.0)
        for sx in (-1, 1):
            _bolt((sx * 0.052, -0.012, 0.058), n=(0, -1, 0), r=0.007, h=0.004)


def _jersey_hardware(length, mat_loop="metal_rusted", ends=(True, True), x0=0.0, reflectors=None, panel=None, blink=None):
    for side, on in zip((-1, 1), ends):
        if not on:
            continue
        x = x0 + side * length / 2
        for z in (0.24, 0.58):
            t = torus(0.055, 0.011, arc=180, n_major=8, n_minor=6, mat=mat_loop, start=-90)
            if side < 0:
                t.mirror("x")
            t.move(x - side * 0.02, 0, z)
    for sx in (reflectors if reflectors is not None else (-length * 0.33, length * 0.33)):
        if detail():
            for sy in (-1, 1):
                with K.placed(_on_jersey_face(sx, 0.7, sy)):
                    box(0.12, 0.006, 0.05, at=(0, -0.003, 0.025), mat="metal_painted_yellow", bevel=0.002)
    if panel:
        pc, pw = panel
        for sy in (-1, 1):
            with K.placed(_on_jersey_face(pc, 0.42, sy)):
                _chevron_panel(pw)
    if blink is not None:
        with K.placed(_on_jersey_face(blink, 0.64, -1)):
            _blinker()


def barrier_jersey(length=2.6):
    b = _jersey_body(length)
    b.bevel(0.012, 2, angle=25)
    _jersey_hardware(length, reflectors=(-1.1,), panel=(-0.2, 1.3), blink=0.95)
    return {"colliders": [K.collider_box((0, 0, 0.405), (length, 0.61, 0.81))]}


def barrier_jersey_broken(seed=7):
    rnd = random.Random(seed)
    L = 1.75
    b = _jersey_body(L, x0=-0.42, slots=False)
    boolean(b, box(0.32, 1.0, 0.2, at=(-0.85, 0, 0), mat="concrete_dark"))
    # break the +X end with irregular chunks
    for i in range(3):
        c = rock((0.6, 0.9, 0.7), seed + i, cuts=10, mat="concrete", rough=0.05)
        c.move(0.47 + rnd.uniform(-0.04, 0.12), rnd.uniform(-0.3, 0.3), 0.2 + i * 0.25)
        boolean(b, c)
    b.bevel(0.01, 1, angle=25)
    _jersey_hardware(L, ends=(True, False), x0=-0.42, reflectors=(-1.15,), panel=(-0.55, 0.85), blink=-1.08)
    for k, (y, z) in enumerate([(-0.12, 0.2), (0.12, 0.2), (-0.06, 0.55), (0.06, 0.55)]):
        bend = rnd.uniform(0.1, 0.35)
        pts = [(0.25, y, z), (0.45, y, z + rnd.uniform(-0.03, 0.03)), (0.58, y + rnd.uniform(-0.1, 0.1), z + bend), (0.62, y + rnd.uniform(-0.15, 0.15), z + bend + 0.15)]
        tube(pts, 0.009, 6, "metal_rusted")
    # broken-off piece lying on its side
    c = _jersey_body(0.75, slots=False, mat="concrete", grime=False)
    for sx in (-1, 1):
        cut = rock((0.5, 0.9, 0.9), seed + 10 + sx, cuts=9, mat="concrete", rough=0.05)
        cut.move(sx * 0.55, 0, 0.4)
        boolean(c, cut)
    c.bevel(0.008, 1, angle=25)
    c.rot(x=-82).rot(z=18).move(0.95, 0.55, 0.3)
    K.ground([c])
    for i in range(4):
        r = rock((rnd.uniform(0.08, 0.2), rnd.uniform(0.08, 0.18), rnd.uniform(0.05, 0.12)), seed + 30 + i, cuts=8, mat="concrete")
        r.move(rnd.uniform(0.3, 1.3), rnd.uniform(-0.5, 0.3), 0.03)
    return {"colliders": [K.collider_box((-0.42, 0, 0.405), (1.75, 0.61, 0.81)), K.collider_box((0.95, 0.5, 0.3), (0.85, 0.85, 0.6))]}


# ============================================================================================== crates
def crate_cargo(L=1.2, D=1.0, H=1.0, paint="metal_painted"):
    t = 0.07
    box(L - 0.03, D - 0.03, H - 0.03, at=(0, 0, 0), mat=paint, base=True).move(0, 0, 0.015)
    # edge frame
    hx, hy = L / 2 - t / 2, D / 2 - t / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(t, t, H - 0.16, at=(sx * hx, sy * hy, H / 2), mat="metal_dark", bevel=0.006)
    for z in (t / 2, H - t / 2):
        for sy in (-1, 1):
            box(L - 0.18, t, t * 0.9, at=(0, sy * hy, z), mat="metal_dark", bevel=0.006)
        for sx in (-1, 1):
            box(t, D - 0.18, t * 0.9, at=(sx * hx, 0, z), mat="metal_dark", bevel=0.006)
    # corner castings with recessed apertures
    for sx in (-1, 1):
        for sy in (-1, 1):
            for z in (0.045, H - 0.045):
                c = box(0.11, 0.11, 0.09, at=(sx * (L / 2 - 0.055), sy * (D / 2 - 0.055), z), mat="metal_dark", bevel=0.005)
                if detail():
                    fs = faces_where(c, lambda f, sx=sx, sy=sy: f.normal.x * sx > 0.9 or f.normal.y * sy > 0.9)
                    inset(c, fs, 0.03, -0.015, mat="black")
    # corrugation ribs on all four sides
    nrib = 5
    for i in range(nrib):
        f = (i + 0.5) / nrib - 0.5
        for sy in (-1, 1):
            box(0.05, 0.02, H - 0.2, at=(f * (L - 0.25), sy * (D / 2 - 0.012), H / 2), mat=paint, bevel=0.006)
    for i in range(4):
        f = (i + 0.5) / 4 - 0.5
        for sx in (-1, 1):
            box(0.02, 0.05, H - 0.2, at=(sx * (L / 2 - 0.012), f * (D - 0.25), H / 2), mat=paint, bevel=0.006)
    # door locking bars (front, -Y)
    if detail():
        for x in (-0.18, 0.18):
            cyl(0.012, H - 0.2, 8, at=(x, -D / 2 - 0.035, 0.1), mat="metal_bare")
            for z in (0.15, H - 0.15):
                box(0.05, 0.04, 0.03, at=(x, -D / 2 - 0.02, z), mat="metal_dark", bevel=0.004)
            box(0.03, 0.03, 0.16, at=(x + 0.04, -D / 2 - 0.05, H * 0.45), mat="metal_bare", bevel=0.005)
        # e-lock module between the bars, shipping label, hazard band on the top frame, hinges
        box(0.14, 0.03, 0.2, at=(0, -D / 2 - 0.016, H * 0.62), mat="metal_dark", bevel=0.006)
        box(0.09, 0.006, 0.06, at=(0, -D / 2 - 0.033, H * 0.66), mat="black")
        box(0.06, 0.006, 0.012, at=(0, -D / 2 - 0.034, H * 0.56), mat="emit_green")
        with K.placed(_xf(-0.36, -D / 2 - 0.006, H * 0.78)):
            _label(0.26, 0.1, 31)
        with K.placed(_xf(0, -D / 2 - 0.001, H - t + 0.008)):
            _stripes(L - 0.24, t - 0.02, pitch=0.08, slant=0.5, depth=0.003)
        for sx in (-1, 1):
            for z in (0.22, H - 0.22):
                cyl(0.016, 0.08, 8, at=(sx * (L / 2 - 0.08), -D / 2 - 0.016, z - 0.04), mat="metal_bare")
    return {"colliders": [K.collider_box((0, 0, H / 2), (L, D, H))]}


def crate_small(L=0.8, D=0.55, H=0.5, paint="metal_painted_green"):
    b = box(L, D, H - 0.04, at=(0, 0, 0.04), mat=paint, base=True, bevel=0.02, bseg=2)
    # lid seam + lid
    box(L + 0.012, D + 0.012, 0.012, at=(0, 0, H - 0.1), mat="metal_dark", bevel=0.003)
    # skids
    for x in (-L / 2 + 0.08, L / 2 - 0.08):
        box(0.06, D - 0.04, 0.04, at=(x, 0, 0), mat="metal_dark", base=True, bevel=0.006)
    # ribs on long sides and handles on short sides
    for sy in (-1, 1):
        for x in (-0.22, 0.0, 0.22):
            box(0.04, 0.015, H - 0.2, at=(x * L / 0.8, sy * (D / 2 + 0.006), 0.04 + (H - 0.04) / 2 - 0.04), mat=paint, bevel=0.004)
    for sx in (-1, 1):
        t = torus(0.06, 0.009, arc=180, n_major=8, n_minor=6, mat="metal_bare", start=0)
        t.rot(y=90 * sx).rot(z=90).move(sx * (L / 2 + 0.01), 0, H * 0.62)
        for y in (-0.06, 0.06):
            box(0.012, 0.025, 0.04, at=(sx * (L / 2 + 0.005), y, H * 0.62), mat="metal_dark")
    if detail():
        for x in (-0.25, 0.25):
            box(0.06, 0.02, 0.07, at=(x * L / 0.8, -D / 2 - 0.008, H - 0.12), mat="metal_bare", bevel=0.004)
            box(0.03, 0.01, 0.02, at=(x * L / 0.8, -D / 2 - 0.012, H - 0.1), mat="metal_dark")
        # corner bumpers, status LED, stencil glyphs
        for sx in (-1, 1):
            for sy in (-1, 1):
                for z in (0.06, H - 0.03):
                    box(0.05, 0.05, 0.05, at=(sx * (L / 2 - 0.02), sy * (D / 2 - 0.02), z), mat="rubber", bevel=0.008)
        box(0.05, 0.006, 0.01, at=(0.11 * L / 0.8, -D / 2 - 0.003, H - 0.17), mat="emit_cyan")
        rng = random.Random(55)
        for gx in (0.09, 0.15):
            for pts, closed in _glyph_strokes(rng):
                P = [(gx * L / 0.8 - 0.025 + u * 0.05, -D / 2 - 0.0025, 0.16 + v * 0.05) for u, v in pts]
                tube(P, 0.0025, 4, "metal_painted_white", closed=closed)
    return {"colliders": [K.collider_box((0, 0, H / 2), (L, D, H))]}


def crate_wood(L=1.0, D=0.8, H=0.8):
    # slatted wooden crate on a frame
    box(L - 0.06, D - 0.06, H - 0.06, at=(0, 0, 0.03), mat="wood", base=True)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(0.07, 0.07, H, at=(sx * (L / 2 - 0.035), sy * (D / 2 - 0.035), 0), mat="wood", base=True, bevel=0.006)
    for z in (0.035, H - 0.035):
        for sy in (-1, 1):
            box(L - 0.14, 0.03, 0.07, at=(0, sy * (D / 2 - 0.015), z), mat="wood", bevel=0.005)
        for sx in (-1, 1):
            box(0.03, D - 0.14, 0.07, at=(sx * (L / 2 - 0.015), 0, z), mat="wood", bevel=0.005)
    # diagonal braces on long faces
    for sy in (-1, 1):
        beam((-L / 2 + 0.08, sy * (D / 2 - 0.01), 0.09), (L / 2 - 0.08, sy * (D / 2 - 0.01), H - 0.09), 0.07, 0.025, mat="wood", up=(0, 1, 0))
    if detail():
        for sx in (-1, 1):
            for sy in (-1, 1):
                for z in (0.035, H - 0.035):
                    box(0.09, 0.09, 0.012, at=(sx * (L / 2 - 0.04), sy * (D / 2 - 0.04), z + (0.04 if z > 0.1 else -0.04)), mat="metal_dark")
        # burnt-in stencil glyphs on the end panels + a shipping label on the front
        rng = random.Random(91)
        for sx in (-1, 1):
            for gi in range(2):
                y0 = -0.13 + gi * 0.15
                for pts, closed in _glyph_strokes(rng):
                    P = [(sx * (L / 2 - 0.028), y0 + sx * (u * 0.12 - 0.06), H * 0.42 + v * 0.12) for u, v in pts]
                    tube(P, 0.005, 4, "black", closed=closed)
        with K.placed(_xf(0.18, -D / 2 + 0.0, H - 0.035)):
            _label(0.24, 0.055, 92, n=3)
    return {"colliders": [K.collider_box((0, 0, H / 2), (L, D, H))]}


def crate_stack():
    crate_cargo()
    m0 = len(K._parts)
    crate_small()
    for p in K._parts[m0:]:
        p.rot(z=8).move(0.05, 0.04, 1.0)
    m = len(K._parts)
    crate_wood(0.9, 0.75, 0.75)
    for p in K._parts[m:]:
        p.rot(z=-4).move(1.12, -0.05, 0)
    return {"colliders": [K.collider_box((0, 0, 0.75), (1.2, 1.0, 1.5)), K.collider_box((1.12, -0.05, 0.375), (0.95, 0.8, 0.75))]}


# ============================================================================================== street light
LAMP_Z0 = 0.8                      # pole starts on top of the base shroud
LAMP_R0, LAMP_R1 = 0.084, 0.056    # octagonal pole circumradius at LAMP_Z0 / at the top


def _pole_r(z, height=6.2):
    return LAMP_R0 + (LAMP_R1 - LAMP_R0) * (z - LAMP_Z0) / (height - LAMP_Z0)


def _ring_at(z, h, grow=0.008, mat="metal_dark", height=6.2, bevel=0.003):
    """Octagonal clamp band around the pole centred at z."""
    r = _pole_r(z, height) + grow
    p = _prism([(r, z - h / 2), (r, z + h / 2)], 8, mat=mat, name="band")
    p.bevel(bevel, 1, angle=30)
    return p


def _lamp_base(fault=False):
    """Base plate + anchor bolts, octagonal shroud with a hazard-striped skirt and a junction access panel (-Y)."""
    box(0.34, 0.34, 0.025, mat="metal_dark", base=True, bevel=0.006)
    if detail():
        for sx in (-1, 1):
            for sy in (-1, 1):
                at = (sx * 0.135, sy * 0.135, 0.025)
                cyl(0.021, 0.005, 8, at=at, mat="metal_bare")
                cyl(0.014, 0.013, 6, at=(at[0], at[1], 0.03), mat="metal_bare", start=0)
                cyl(0.007, 0.03, 6, at=(at[0], at[1], 0.03), mat="metal_bare")
    sh = _prism([(0.152, 0.025), (0.152, 0.2), (0.126, 0.24), (0.116, 0.70), (0.096, 0.76), (0.088, 0.8)], 8,
                mat="paint_glossy_dark", name="shroud")
    sh.bevel(0.004, 1, angle=20)
    sh.set_mat("black", where=lambda f: f.calc_center_median().z < 0.2 and abs(f.normal.z) < 0.5)
    if detail():
        ap = _apo(0.152)
        for k in range(8):
            with K.placed(_xf(0, 0, 0.04, rz=k * 45) @ Matrix.Translation((0, -ap, 0))):
                _stripes(0.1, 0.14, pitch=0.05, frac=0.5, slant=0.35, depth=0.003)
    # junction access panel with screws, louvre vent, status LED
    ap = _apo(0.121)
    pz = 0.47
    box(0.078, 0.012, 0.36, at=(0, -ap - 0.003, pz), mat="metal_dark", bevel=0.003)
    if detail():
        for sx in (-1, 1):
            for sz in (-1, 1):
                _bolt((sx * 0.028, -ap - 0.009, pz + sz * 0.16), n=(0, -1, 0), r=0.005, h=0.003)
        _vent(0.05, 0.09, 5, (0, -ap - 0.009, pz - 0.08))
        box(0.014, 0.004, 0.014, at=(0, -ap - 0.011, pz + 0.11), mat="emit_red" if fault else "emit_green")
        box(0.05, 0.003, 0.03, at=(0, -ap - 0.0105, pz + 0.05), mat="metal_painted_yellow")


def _lamp_pole(z0, z1, height=6.2):
    return _prism([(_pole_r(z0, height), z0), (_pole_r(z1, height), z1)], 8, mat="metal_dark", name="pole")


def _lamp_lower_details(height=6.2, lit=True):
    """Collar, front LED channel and LED ring (all below the 2.4 m buckle point of the broken variant)."""
    _ring_at(LAMP_Z0 + 0.02, 0.05, 0.01, height=height)
    # vertical LED channel on the front flat
    z0, z1 = 0.95, 1.9
    a0, a1 = _apo(_pole_r(z0, height)), _apo(_pole_r(z1, height))
    _tbeam((0, -a0 - 0.004, z0 - 0.03), (0, -a1 - 0.004, z1 + 0.03), 0.026, 0.01, mat="metal_dark", side=(1, 0, 0))
    _tbeam((0, -a0 - 0.009, z0), (0, -a1 - 0.009, z1), 0.012, 0.006, mat="emit_strip_cyan" if lit else "black", side=(1, 0, 0))
    # LED ring between two chrome bands
    _ring_at(2.02, 0.022, 0.012, mat="chrome_scratched", height=height)
    _ring_at(2.09, 0.06, 0.009, mat="emit_strip_cyan" if lit else "black", height=height, bevel=0.0)
    _ring_at(2.16, 0.022, 0.012, mat="chrome_scratched", height=height)
    if detail():
        for z in (LAMP_Z0 + 0.02,):
            r = _apo(_pole_r(z, height) + 0.01)
            for k in range(4):
                a = math.radians(45 + k * 90)
                _bolt((math.cos(a) * r, math.sin(a) * r, z), n=(math.cos(a), math.sin(a), 0), r=0.006, h=0.004)


def _conduit(z0, z1, height=6.2, ang=45.0, off=0.014, clamps=True):
    """Cable conduit running up the pole on the flat at angle `ang`, with strap clamps."""
    c, s_ = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    pts = []
    n = 6
    for i in range(n + 1):
        z = z0 + (z1 - z0) * i / n
        d = _apo(_pole_r(z, height)) + off
        pts.append((c * d, s_ * d, z))
    tube(pts, 0.011, 6, "metal_dark", name="conduit")
    if clamps and detail():
        z = z0 + 0.25
        while z < z1 - 0.1:
            d = _apo(_pole_r(z, height)) + off
            p = box(0.03, 0.028, 0.025, mat="metal_bare", bevel=0.003)
            p.rot(z=ang - 90).move(c * d, s_ * d, z)
            z += 0.85


def _blade_sign(z0, z1, y0, y1, lit=True, seed=21, height=6.2):
    """Pole-mounted blade sign (YZ plane, toward -Y) with neon glyphs on both faces and a magenta edge strip."""
    zc, yc = (z0 + z1) / 2, (y0 + y1) / 2
    W, H, T = abs(y1 - y0), z1 - z0, 0.05
    b = box(T, W, H, at=(0, yc, zc), mat="paint_glossy_dark", bevel=0.008)
    inset(b, faces_where(b, lambda f: abs(f.normal.x) > 0.9), 0.022, -0.005, mat="black")
    neon = "emit_neon_cyan" if lit else "glass_dark"
    gs = 0.2
    zs = [zc + H / 2 - 0.06 - gs - i * (gs + 0.06) for i in range(3)]
    for sx in (-1, 1):
        rng2 = random.Random(seed)
        for zg in zs:
            if K.LOD < 2:
                _neon_glyph(rng2, (sx * (T / 2 - 0.001), yc - sx * gs / 2, zg), (0, sx, 0), (0, 0, 1), (gs, gs), r=0.0055, mat=neon)
    box(0.016, 0.006, H - 0.06, at=(0, y1 - 0.003, zc), mat="emit_strip_magenta" if lit else "black")
    box(0.016, W - 0.06, 0.006, at=(0, yc, z1 + 0.003), mat="emit_strip_magenta" if lit else "black")
    for z in (z0 + 0.1, z1 - 0.1):
        a = _apo(_pole_r(z, height))
        _tbeam((0, -a + 0.01, z), (0, y0 + 0.01, z), 0.03, 0.045, mat="metal_dark", side=(1, 0, 0))
        _ring_at(z, 0.06, 0.008, height=height)
    if detail():
        _cable(_sag((0.02, -_apo(_pole_r(z0 + 0.1, height)), z0 + 0.04), (0.02, y0 - 0.03, z0 - 0.0), 0.06, 5), r=0.006)


def _pole_camera(z, height=6.2, lit=True):
    """CCTV camera on the back flat (+Y), pitched down."""
    a = _apo(_pole_r(z, height))
    _ring_at(z, 0.07, 0.008, height=height)
    _tbeam((0, a, z), (0, a + 0.075, z - 0.01), 0.03, 0.035, mat="metal_dark", side=(1, 0, 0))
    with K.placed(_xf(0, a + 0.109, z - 0.035, rx=-18)):
        box(0.07, 0.13, 0.068, mat="paint_glossy_white", bevel=0.014, bseg=2)
        box(0.084, 0.115, 0.008, at=(0, 0.012, 0.039), mat="metal_dark", bevel=0.002)
        cyl(0.023, 0.012, 12, at=(0, 0.06, 0), axis="Y", mat="black")
        if detail():
            cyl(0.016, 0.004, 12, at=(0, 0.071, 0), axis="Y", mat="glass_dark")
            box(0.008, 0.004, 0.008, at=(0.025, 0.066, -0.022), mat="emit_red" if lit else "black")
            box(0.012, 0.03, 0.02, at=(0, -0.075, 0.0), mat="metal_dark")


def _lamp_head(lit=True, smashed=False, seed=3):
    """Slim LED head bar at head-local origin (bottom centre), tip toward -Y."""
    prof = [(-0.34, 0.0), (0.30, 0.0), (0.34, 0.035), (0.34, 0.092), (0.22, 0.112), (-0.26, 0.07), (-0.34, 0.046)]
    h = extrude(prof, 0.26, plane="YZ", mat="paint_glossy_dark", name="head")
    h.bevel(0.009, 2, angle=25)
    inset(h, faces_where(h, lambda f: f.normal.z < -0.9), 0.026, -0.006, mat="emit_panel_warm" if lit else "black")
    edge = "emit_strip_cyan" if lit else "black"
    for sx in (-1, 1):
        box(0.006, 0.56, 0.011, at=(sx * 0.1315, -0.03, 0.022), mat=edge)
    box(0.2, 0.006, 0.012, at=(0, -0.3425, 0.024), mat=edge)
    slope = math.degrees(math.atan2(0.042, 0.48))
    if detail():
        # LED module ribs across the diffuser
        for y in (-0.17, -0.02, 0.13):
            box(0.2, 0.008, 0.006, at=(0, y, 0.004), mat="black")
        for i in range(5):
            x = -0.08 + i * 0.04
            f = box(0.007, 0.36, 0.02, mat="metal_dark")
            f.rot(x=slope).move(x, 0.0, 0.072 + 0.26 * 0.0875 + 0.008)
        lathe([(0.026, 0.0), (0.026, 0.012), (0.018, 0.026), (0.001, 0.03)], 10, at=(0, 0.25, 0.104), mat="paint_glossy_white")
    if smashed and detail():
        for k, (x, dz) in enumerate(((-0.05, 0.5), (0.04, 0.38), (0.0, 0.62))):
            tube([(x, 0.25, 0.01), (x + 0.01, 0.2, -dz * 0.4), (x - 0.02, 0.24, -dz * 0.8), (x + 0.01, 0.3, -dz)], 0.005, 4,
                 ("rubber", "metal_painted_red", "metal_painted_yellow")[k])
        rnd = random.Random(seed)
        for i in range(4):
            r_ = rock((0.07, 0.05, 0.012), seed + i, cuts=6, mat="black", rough=0.1, bevel=0.0)
            r_.rot(x=rnd.uniform(-40, 40), y=rnd.uniform(-30, 30)).move(rnd.uniform(-0.08, 0.08), rnd.uniform(-0.25, 0.2), -0.012)


def _lamp_arm(height=6.2, lit=True):
    top = height - 0.05
    a, b = Vector((0, 0.0, top - 0.07)), Vector((0, -1.52, top + 0.255))
    _tbeam(a, b, 0.075, 0.11, 0.05, 0.055, mat="metal_dark", side=(1, 0, 0), bevel=0.006)
    d = (b - a).normalized()
    sz = Vector((1, 0, 0)).cross(d).normalized()          # arm "down" side
    # underside LED strip
    p0 = a.lerp(b, 0.22) + sz * (0.11 - 0.055 * 0.22 + 0.006) / 2 * 1.0
    p1 = a.lerp(b, 0.86) + sz * (0.11 - 0.055 * 0.86 + 0.006) / 2 * 1.0
    _led(tuple(p0), tuple(p1), 0.014, 0.006, mat="emit_strip_cyan" if lit else "black", up=tuple(sz))
    # tension strut + clamps
    s0, s1 = Vector((0, -0.06, top - 0.8)), a.lerp(b, 0.56) + sz * 0.035
    _tbeam(s0, s1, 0.03, 0.03, mat="metal_dark", side=(1, 0, 0), bevel=0.004)
    _ring_at(top - 0.8, 0.07, 0.01, height=height)
    box(0.06, 0.06, 0.05, at=tuple(s1 + sz * 0.005), mat="metal_dark", bevel=0.006)
    # arm clamp collar + top LED ring + pole cap
    _ring_at(top - 0.1, 0.22, 0.014, height=height, bevel=0.006)
    _ring_at(top - 0.27, 0.035, 0.008, mat="emit_strip_cyan" if lit else "black", height=height, bevel=0.0)
    _ring_at(top - 0.32, 0.03, 0.012, mat="chrome_scratched", height=height)
    r1 = _pole_r(height, height)
    _prism([(r1 + 0.008, height - 0.01), (r1 + 0.008, height + 0.02), (0.03, height + 0.05)], 8, mat="metal_dark", name="cap")
    if detail():
        # feed cable: from the head along the strut into the pole
        c0 = b + Vector((0.035, 0.07, -0.02))
        c1 = s1 + Vector((0.03, 0, -0.02))
        _cable(_sag(tuple(c0), tuple(c1), 0.07, 6), r=0.007)
        _cable(_sag(tuple(c1), (0.03, -_apo(_pole_r(top - 0.95)) + 0.005, top - 0.95), 0.04, 5), r=0.007)
        for k in range(4):
            ang = math.radians(45 + 90 * k)
            r = _apo(_pole_r(top - 0.1) + 0.014)
            _bolt((math.cos(ang) * r, math.sin(ang) * r, top - 0.1), n=(math.cos(ang), math.sin(ang), 0), r=0.008, h=0.005)
    return b


def street_light(height=6.2, broken=False):
    lit = not broken
    top = height - 0.05
    _lamp_base(fault=broken)
    if not broken:
        _lamp_pole(LAMP_Z0, height, height)
        _lamp_lower_details(height, lit=True)
        _conduit(0.7, top - 0.2, height)
        _ring_at(4.55, 0.05, 0.009, height=height)
        _blade_sign(2.75, 3.7, -0.13, -0.47, lit=True, height=height)
        _pole_camera(3.95, height, lit=True)
        _lamp_arm(height, lit=True)
        with K.placed(_xf(0, -1.78, top + 0.205, rx=-5.0)):
            _lamp_head(lit=True)
        return {"colliders": [K.collider_box((0, 0, height / 2), (0.3, 0.3, height))],
                "light": {"position": K.to_unity_vec((0, -1.78, top + 0.15)), "color": "#ffc98a"}}
    # broken: pole buckled at 2.4 m and leaning toward the street, head smashed, sign dead, fault LED on the base
    bend_z = 2.4
    lean = 24.0
    _lamp_pole(LAMP_Z0, bend_z, height)
    _lamp_lower_details(height, lit=False)
    _conduit(0.7, bend_z - 0.15, height, clamps=True)
    k = len(K._parts)
    _lamp_pole(bend_z, height, height)
    _conduit(bend_z + 0.12, top - 0.2, height)
    _ring_at(4.55, 0.05, 0.009, height=height)
    _blade_sign(2.75, 3.7, -0.13, -0.47, lit=False, height=height)
    _pole_camera(3.95, height, lit=False)
    _lamp_arm(height, lit=False)
    with K.placed(_xf(0, -1.78, top + 0.205, rx=35.0)):
        _lamp_head(lit=False, smashed=True)
    for p in K._parts[k:]:
        p.rot_about((0, 0, bend_z), x=lean)
    # fit the leaning top to the baseline extents (front reach -3.4545, height 5.892) with a tiny stretch
    _fit(K._parts[k:], (0, 0, bend_z), ymin=-3.4545, zmax=5.892)
    kink = _prism([(_pole_r(bend_z) + 0.002, -0.09), (_pole_r(bend_z) + 0.016, -0.03), (_pole_r(bend_z) + 0.02, 0.0),
                   (_pole_r(bend_z) + 0.012, 0.04), (_pole_r(bend_z) + 0.001, 0.09)], 8, mat="paint_glossy_dark", name="kink")
    kink.rot(x=lean / 2).move(0, 0, bend_z)
    if detail():
        # torn feed cable spilling out of the base onto the pavement behind the pole
        pts = [(0.08, 0.1, 0.62), (0.1, 0.2, 0.3), (0.06, 0.35, 0.03), (-0.04, 0.6, 0.012), (0.05, 0.85, 0.012), (0.02, 1.12, 0.014)]
        _cable(pts, r=0.011)
        box(0.03, 0.06, 0.03, at=(0.02, 1.1585, 0.0), mat="metal_bare", base=True, bevel=0.004)
        for i, (x, y) in enumerate(((-0.06, 0.45), (0.08, 0.72), (-0.1, 0.95))):
            rock((0.07, 0.05, 0.01), 40 + i, cuts=6, mat="black", rough=0.1, bevel=0.0).move(x, y, 0.006)
    return {"colliders": [K.collider_box((0, 0, bend_z / 2), (0.3, 0.3, bend_z))]}


ASSETS_A = {
    "Barrier_Jersey": dict(fn=barrier_jersey, cat="street", zones=["plaza", "rooftops"],
                           notes="Concrete NJ/F-shape barrier 2.6 m. Long axis = X. Grimy kerb band and wet crown, drain slots, pin loops, reflective hazard chevron panels on both faces, LED warning blinker (emit_amber) on the -Y (Unity +Z) face."),
    "Barrier_Jersey_Broken": dict(fn=barrier_jersey_broken, cat="street", zones=["plaza"],
                                  notes="Snapped barrier with exposed rebar plus the broken-off piece lying beside it; chevron panels and a still-blinking emit_amber warning light on the intact part."),
    "Crate_Cargo": dict(fn=crate_cargo, cat="props", zones=["plaza", "metro", "rooftops"],
                        notes="Reinforced steel cargo crate 1.2 x 1.0 x 1.0. Swap 'metal_painted' slot with any metal_painted_* tint. Door/locking bars face +Z."),
    "Crate_Cargo_Red": dict(fn=crate_cargo, kw={"paint": "metal_painted_red"}, cat="props", zones=["plaza", "metro"], notes="Red paint variant of Crate_Cargo."),
    "Crate_Cargo_Yellow": dict(fn=crate_cargo, kw={"paint": "metal_painted_yellow"}, cat="props", zones=["plaza", "metro"], notes="Yellow paint variant of Crate_Cargo."),
    "Crate_Small": dict(fn=crate_small, cat="props", zones=["plaza", "metro", "rooftops", "facility"], notes="0.8 x 0.55 x 0.5 equipment case with handles and latches."),
    "Crate_Wood": dict(fn=crate_wood, cat="props", zones=["plaza", "metro"], notes="Slatted wooden crate 1.0 x 0.8 x 0.8 with braces."),
    "Crate_Stack": dict(fn=crate_stack, cat="props", zones=["plaza", "metro", "rooftops"], notes="Pre-composed stack: cargo crate + small case on top + wooden crate beside (+X)."),
    "StreetLight": dict(fn=street_light, cat="street", zones=["plaza", "rooftops"],
                        notes="6.2 m cyberpunk lamp post: octagonal tapered pole, hazard-striped base shroud with junction panel, cyan LED channel + rings (emit_strip_cyan), neon glyph blade sign (emit_neon_cyan / emit_strip_magenta), CCTV camera on the back, slim LED head bar. Arm and lamp head point +Z (prototype local +Z). Lamp diffuser = emit_panel_warm. 'light' gives a point-light anchor."),
    "StreetLight_Broken": dict(fn=street_light, kw={"broken": True}, cat="street", zones=["plaza"],
                               notes="Buckled pole leaning toward +Z, smashed head with dangling wires, dead sign and LEDs (no emission except a red fault LED on the base junction panel), torn feed cable on the pavement behind."),
}


# ============================================================================================== bench / bin
def _slots(w, h, nx, ny, sw, sh, mat="black"):
    """Perforation slots: nx x ny black quads (sw x sh) on a w x h area in the XY plane at z=0 (LOD0 only)."""
    if not detail():
        return
    for i in range(nx):
        for j in range(ny):
            K.plane(sw, sh, at=(-w / 2 + (i + 0.5) * w / nx, -h / 2 + (j + 0.5) * h / ny, 0), mat=mat, name="perf")


def bench(L=1.8, slat="wood"):
    """Cantilever street bench: sculpted side frames, slatted (wood) or perforated (metal) seat and back,
    anti-sleep divider, LED under-glow strip below the front rail."""
    glow = "emit_strip_cyan" if slat == "wood" else "emit_strip_magenta"
    frame = [(-0.22, 0.0), (0.24, 0.0), (0.24, 0.022), (0.19, 0.034), (0.212, 0.40), (0.3, 0.852), (0.262, 0.866),
             (0.17, 0.452), (-0.236, 0.432), (-0.2505, 0.414), (-0.24, 0.388), (0.07, 0.368), (0.115, 0.034),
             (-0.2, 0.024), (-0.22, 0.016)]
    fx = L / 2 - 0.13
    for sx in (-1, 1):
        f = extrude(frame, 0.07, plane="YZ", mat="metal_dark", name="frame")
        f.bevel(0.01, 2, angle=25)
        f.move(sx * fx, 0, 0)
        # inlays on the outer face: LED line along the seat arm, chrome along the back support
        beam((sx * (fx + 0.036), 0.13, 0.415), (sx * (fx + 0.036), -0.215, 0.405), 0.01, 0.004, mat=glow, up=(1, 0, 0))
        if detail():
            beam((sx * (fx + 0.036), 0.205, 0.45), (sx * (fx + 0.036), 0.282, 0.82), 0.012, 0.004, mat="chrome_scratched", up=(1, 0, 0))
            for y in (-0.16, 0.16):
                _bolt((sx * fx + 0.0, y, 0.024), r=0.012, h=0.008)
    # rails between the frames
    box(2 * fx, 0.05, 0.035, at=(0, -0.215, 0.39), mat="metal_dark", bevel=0.006)
    box(2 * fx, 0.05, 0.035, at=(0, 0.13, 0.405), mat="metal_dark", bevel=0.006)
    box(2 * fx - 0.08, 0.008, 0.012, at=(0, -0.236, 0.381), mat=glow)
    slope = math.degrees(math.atan2(0.3 - 0.17, 0.852 - 0.452))
    if slat == "wood":
        for k in range(5):
            box(L, 0.07, 0.034, at=(0, -0.205 + k * 0.08, 0.452), mat=slat, bevel=0.008)
        for t in (0.3, 0.58, 0.86):
            y, z = 0.17 + 0.13 * t - 0.034, 0.452 + 0.4 * t
            b = box(L, 0.028, 0.09, mat=slat, bevel=0.008)
            b.rot(x=-slope).move(0, y, z)
    else:
        seat = box(L, 0.4, 0.016, at=(0, -0.035, 0.44), mat=slat, bevel=0.004)
        cyl(0.018, L, 12, at=(-L / 2, -0.235, 0.432), axis="X", mat=slat)
        with K.placed(_xf(0, -0.04, 0.4485)):
            _slots(L - 0.2, 0.3, 26, 5, 0.045, 0.012)
        bk = box(L, 0.016, 0.36, mat=slat, bevel=0.004)
        bk.rot(x=-slope).move(0, 0.17 + 0.13 * 0.55 - 0.03, 0.452 + 0.4 * 0.55)
        cyl(0.016, L, 12, at=(-L / 2, 0.262, 0.84), axis="X", mat=slat)
        with K.placed(_xf(0, 0.17 + 0.13 * 0.55 - 0.039, 0.452 + 0.4 * 0.55, rx=90 - slope)):
            _slots(L - 0.2, 0.26, 26, 4, 0.045, 0.012)
    # metal (keeps the paint slot) end caps on the seat + anti-sleep divider
    tube([(0, -0.17, 0.46), (0, -0.15, 0.62), (0, -0.04, 0.66), (0, 0.06, 0.62), (0, 0.08, 0.46)], 0.016, 8, "chrome_scratched")
    if detail():
        for sx in (-1, 1):
            box(0.03, 0.4, 0.04, at=(sx * (L / 2 - 0.015), -0.035, 0.452), mat="metal_dark", bevel=0.006)
    return {"colliders": [K.collider_box((0, 0.0, 0.25), (L, 0.5, 0.5)), K.collider_box((0, 0.22, 0.68), (L, 0.12, 0.4))]}


BIN_R = 0.2995   # 12-gon circumradius; shell 0.579 across the flats, LED bands / sensor reach 0.602


def trash_bin(tipped=False, paint="metal_painted_green", seed=4):
    """Smart litter bin: faceted glossy shell, coloured sorting panel, fill-level LEDs, status ring, sensor eye,
    lid with a chute and an overflowing bag."""
    rnd = random.Random(seed)
    n0 = len(K._parts)
    R = BIN_R
    sh = _prism([(R * 0.93, 0.0), (R * 0.97, 0.03), (R * 0.97, 0.05), (R, 0.07), (R, 0.8), (R * 0.97, 0.82)], 12,
                mat="paint_glossy_dark", name="shell")
    sh.set_mat("metal_dark", where=lambda f: f.calc_center_median().z < 0.06)
    sh.bevel(0.004, 1, angle=20)
    inset(sh, faces_where(sh, lambda f: f.normal.y < -0.95 and f.calc_center_median().z > 0.3), 0.025, -0.006, mat=paint)
    inset(sh, faces_where(sh, lambda f: abs(f.normal.x) > 0.95 and f.calc_center_median().z > 0.3), 0.03, -0.004, mat="carbon_panel")
    # status LED ring under the lid
    _prism([(R + 0.008, 0.76), (R + 0.008, 0.785)], 12, mat="emit_strip_cyan", name="ring")
    _prism([(R + 0.012, 0.745), (R + 0.012, 0.76)], 12, mat="metal_dark", name="band")
    _prism([(R + 0.012, 0.785), (R + 0.012, 0.8)], 12, mat="metal_dark", name="band")
    if tipped:
        sh.set_mat("plastic_dark", where=lambda f: f.normal.z > 0.9 and f.calc_center_median().z > 0.79)
    # lid: sloped top with a dark chute opening toward the front (knocked off on the tipped bin)
    lid0 = len(K._parts)
    lid = _prism([(R * 0.98, 0.8), (R * 0.98, 0.84), (R * 0.9, 0.87), (R * 0.55, 0.89), (R * 0.2, 0.892)], 12, mat="metal_dark", name="lid")
    lid.bevel(0.004, 1, angle=20)
    ch = box(0.26, 0.1, 0.06, at=(0, -0.2, 0.85), mat="plastic_dark", bevel=0.01)
    ch.rot_about((0, -0.2, 0.85), x=-12)
    box(0.22, 0.012, 0.035, at=(0, -0.252, 0.85), mat="black")
    lid_parts = list(K._parts[lid0:])
    ap = _apo(R, 12)
    if detail():
        # fill-level bar + sensor eye + status LED on the front panel
        for i in range(5):
            box(0.05, 0.004, 0.018, at=(0.09, -ap - 0.003, 0.42 + i * 0.03), mat="emit_green" if i < 3 else "black")
        cyl(0.02, 0.008, 12, at=(-0.09, -ap - 0.008, 0.62), axis="Y", mat="black")
        cyl(0.012, 0.003, 12, at=(-0.09, -ap - 0.011, 0.62), axis="Y", mat="glass_dark")
        rng = random.Random(seed + 50)
        for gx in (-0.07, 0.0):
            for pts, closed in _glyph_strokes(rng):
                P = [(gx - 0.025 + u * 0.05, -ap - 0.0035, 0.3 + v * 0.05) for u, v in pts]
                tube(P, 0.0025, 4, "metal_painted_white", closed=closed)
        # hinge + foot pads
        box(0.2, 0.02, 0.02, at=(0, _apo(R, 12) - 0.002, 0.81), mat="metal_bare", bevel=0.004)
        for k in range(4):
            a = math.radians(45 + k * 90)
            box(0.06, 0.06, 0.012, at=(math.cos(a) * 0.22, math.sin(a) * 0.22, 0.0), mat="rubber", base=True)
    parts = [p for p in K._parts[n0:] if p not in lid_parts]
    if not tipped:
        rock((0.3, 0.26, 0.14), seed, cuts=10, mat="plastic_dark", rough=0.06).move(0.02, -0.178, 0.862)
        return {"colliders": [K.collider_box((0, 0, 0.45), (0.6, 0.6, 0.9))]}
    for p in parts:
        p.rot(x=90).rot(z=20)
    K.ground(parts)
    _fit_box(parts, x=(-0.497, 0.591), ymax=0.084)   # legacy footprint of the tipped bin
    for p in lid_parts:   # lid lying upside down beside the mouth
        p.move(0, 0, -0.8).rot(x=172).rot(z=-30).move(-0.2, -0.55, 0.0)
    K.ground(lid_parts)
    for i in range(5):
        s = rnd.uniform(0.12, 0.3)
        _bag((s, s * 0.9, s * 0.6), seed + i, mat=rnd.choice(["plastic_dark", "tarp", "plastic_dark"]), knot=True).move(
            rnd.uniform(-0.6, 0.4), rnd.uniform(-1.4, -0.75), s * 0.3)
    return {"colliders": [K.collider_box((0, -0.1, 0.3), (0.95, 0.95, 0.6))]}


# ============================================================================================== signage
def _bezel_face(part, normal_sign, y_face, w, h, glow="emit_strip_cyan", depth_out=0.0):
    """Stepped bezel on the +/-Y face of `part` (outer face at y_face): 0.02 outer step, 0.03 inner lip, screen
    face w x h pushed 0.008 in (screen ends 0.01 behind the bezel front like the legacy signs)."""
    sel = lambda f: f.normal.y * normal_sign > 0.9
    f1 = inset(part, faces_where(part, sel), 0.02, -0.003)
    f2 = inset(part, f1, 0.03, -0.005, mat="screen")
    s = normal_sign
    yl = y_face - s * 0.0015          # proud of the sloped inner lip, flush with the bezel front
    if glow:
        for (bw, bh, x, z) in ((w + 0.05, 0.007, 0, h / 2 + 0.026), (w + 0.05, 0.007, 0, -h / 2 - 0.026),
                               (0.007, h + 0.045, w / 2 + 0.026, 0), (0.007, h + 0.045, -w / 2 - 0.026, 0)):
            box(bw, 0.004, bh, at=(x, yl, z), mat=glow)
    return f2


def _corner_caps(w, h, y_face, s=-1, mat="chrome_scratched"):
    """L-shaped corner brackets with a bolt each, on the bezel front."""
    for sx in (-1, 1):
        for sz in (-1, 1):
            x, z = sx * (w / 2 + 0.03), sz * (h / 2 + 0.03)
            box(0.085, 0.003, 0.025, at=(x - sx * 0.0275, y_face + s * 0.0015, z + sz * 0.0075), mat=mat)
            box(0.025, 0.003, 0.06, at=(x + sx * 0.0075, y_face + s * 0.0015, z - sz * 0.01), mat=mat)
            _bolt((x + sx * 0.006, y_face + s * 0.003, z + sz * 0.006), n=(0, s, 0), r=0.006, h=0.002)


def sign_panel(w=3.6, h=0.7, depth=0.08):
    """Backlit LED wall sign with a blank 'screen' face. Pivot = BACK centre (mount on a wall); face toward -Y
    (Unity +Z). Thick stepped bezel with an inner glow line, corner brackets, stepped light-box housing, wall rails,
    cable gland + conduit into the wall."""
    yf = -0.078
    b = box(w + 0.1, 0.048, h + 0.1, at=(0, yf + 0.024, 0), mat="metal_dark", bevel=0.01)
    _bezel_face(b, -1, yf, w, h)
    # rear light-box housing + cooling ribs (between the bezel and the wall)
    rb = box(w - 0.06, 0.026, h - 0.06, at=(0, -0.018, 0), mat="paint_glossy_dark", bevel=0.006)
    # backlight spill: glowing strips along the top and bottom outer edges of the bezel
    for sz in (-1, 1):
        box(w + 0.02, 0.008, 0.004, at=(0, yf + 0.008, sz * (h / 2 + 0.0485)), mat="emit_strip_magenta")
    if detail():
        _corner_caps(w, h, yf)
        nr = max(2, int(w / 0.5))
        for i in range(nr):
            box(0.012, 0.024, h - 0.12, at=(-w / 2 + 0.1 + i * (w - 0.2) / max(1, nr - 1), -0.017, 0), mat="metal_dark")
        # wall rails (top/bottom) with anchor bolts
        for sz in (-1, 1):
            z = sz * (h / 2 - 0.015)
            box(w * 0.7, 0.026, 0.03, at=(0, -0.018, z), mat="metal_bare")
            box(w * 0.7, 0.008, 0.06, at=(0, 0.001, z), mat="metal_bare")
            for k in (-1, 1):
                _bolt((k * w * 0.3, -0.03, z), n=(0, -1, 0), r=0.008, h=0.005)
        # cable gland under the housing and a conduit running into the wall
        x0 = w / 2 - 0.18
        cyl(0.018, 0.02, 8, at=(x0, -0.03, -h / 2 - 0.035), mat="metal_dark")
        tube([(x0, -0.03, -h / 2 - 0.02), (x0 - 0.06, -0.03, -h / 2 - 0.03), (x0 - 0.14, -0.016, -h / 2 - 0.035), (x0 - 0.2, -0.004, -h / 2 - 0.035)], 0.011, 6, "rubber")
        # status LED on the bezel corner
        box(0.012, 0.004, 0.012, at=(w / 2 + 0.03, yf - 0.002, -h / 2 - 0.0), mat="emit_green")
    return {"colliders": [K.collider_box((0, -depth / 2, 0), (w + 0.1, depth, h + 0.1))],
            "screen": {"center": K.to_unity_vec((0, -depth + 0.01, 0)), "size": [w, h], "normal": [0, 0, 1], "material": "screen"}}


def sign_hanging(w=3.4, h=0.7, drop=0.6):
    """Ceiling-hung double-sided LED sign. Pivot = TOP centre (ceiling attach point). Stepped bezels with glow lines
    on both faces, glowing bottom edge, top cable tray + junction box, rods with turnbuckles, bolted ceiling plates."""
    zc = -(drop + (h + 0.1) / 2)
    b = box(w + 0.1, 0.14, h + 0.1, at=(0, 0, zc), mat="metal_dark", bevel=0.012)
    f_m = inset(b, faces_where(b, lambda f: f.normal.y < -0.9), 0.02, -0.003)
    inset(b, f_m, 0.03, -0.007, mat="screen")
    f_p = inset(b, faces_where(b, lambda f: f.normal.y > 0.9), 0.02, -0.003)
    inset(b, f_p, 0.03, -0.007, mat="screen")
    for s in (-1, 1):
        yl = s * (0.07 - 0.0035) + s * 0.0015
        for (bw, bh, x, z) in ((w + 0.05, 0.007, 0, h / 2 + 0.026), (w + 0.05, 0.007, 0, -h / 2 - 0.026),
                               (0.007, h + 0.045, w / 2 + 0.026, 0), (0.007, h + 0.045, -w / 2 - 0.026, 0)):
            box(bw, 0.004, bh, at=(x, yl, zc + z), mat="emit_strip_cyan")
    # glowing underside edge
    box(w - 0.1, 0.05, 0.008, at=(0, 0, zc - (h + 0.1) / 2 - 0.0), mat="emit_strip_magenta")
    top = zc + (h + 0.1) / 2
    # cable tray / junction box on top
    box(w * 0.5, 0.08, 0.04, at=(0, 0, top), mat="metal_dark", base=True, bevel=0.006)
    box(0.2, 0.1, 0.08, at=(w * 0.12, 0, top), mat="metal_dark", base=True, bevel=0.008)
    for x in (-w / 2 + 0.3, w / 2 - 0.3):
        cyl(0.012, drop + 0.02, 6, at=(x, 0, top - 0.01), mat="metal_bare")
        box(0.12, 0.12, 0.012, at=(x, 0, -0.006), mat="metal_dark")
        if detail():
            box(0.034, 0.03, 0.12, at=(x, 0, top + drop * 0.45), mat="metal_dark", bevel=0.004)
            cyl(0.03, 0.03, 8, at=(x, 0, -0.042), mat="metal_dark")
            box(0.05, 0.05, 0.02, at=(x, 0, top + 0.01), mat="metal_dark", bevel=0.004)
            for k in range(4):
                a = math.radians(45 + k * 90)
                _bolt((x + math.cos(a) * 0.045, math.sin(a) * 0.045, -0.012), n=(0, 0, -1), r=0.007, h=0.004)
    if detail():
        # power feed from the ceiling into the junction box
        cyl(0.04, 0.03, 8, at=(w * 0.12 + 0.35, 0, -0.03), mat="metal_dark")
        _cable([(w * 0.12 + 0.35, 0, -0.03), (w * 0.12 + 0.33, 0.0, -0.25), (w * 0.12 + 0.2, 0.01, top + 0.2),
                (w * 0.12 + 0.06, 0, top + 0.07)], r=0.01)
    return {"colliders": [K.collider_box((0, 0, zc), (w + 0.1, 0.14, h + 0.1))],
            "screens": [{"center": K.to_unity_vec((0, -0.06, zc)), "size": [w, h], "normal": [0, 0, 1]},
                        {"center": K.to_unity_vec((0, 0.06, zc)), "size": [w, h], "normal": [0, 0, -1]}]}


# ============================================================================================== camp / market
def _cloth(W, D, z_front, z_back, sag, seed, mat, nx=10, ny=8, droop=0.12):
    import bmesh
    rnd = random.Random(seed)
    p = K.plane(W, D, mat=mat, nx=seg_(nx), ny=seg_(ny))
    ph = [rnd.uniform(0, 6) for _ in range(4)]

    def f(co):
        x, y, _ = co
        u, v = x / W + 0.5, y / D + 0.5
        z = z_front + (z_back - z_front) * v - sag * math.sin(math.pi * u) * math.sin(math.pi * v)
        z += 0.025 * math.sin(x * 5 + ph[0]) * math.sin(y * 4 + ph[1]) + 0.015 * math.sin(x * 11 + ph[2])
        e = max(0.0, abs(u - 0.5) - 0.42) + max(0.0, abs(v - 0.5) - 0.42)
        z -= droop * e / 0.08
        return (x, y, z)
    p.displace(f)
    back = p.copy()
    import bmesh as _bm
    _bm.ops.reverse_faces(back.bm, faces=back.bm.faces)
    back.move(0, 0, -0.004)
    return p


def seg_(n):
    return n if K.LOD == 0 else max(2, n // 2)


def _bag(size, seed, mat="plastic_dark", knot=False):
    """Lumpy rounded sack / trash bag that stays inside a size-box centred at the origin."""
    rnd = random.Random(seed)
    sx, sy, sz = size
    b = box(sx, sy, sz, mat=mat, bevel=min(size) * 0.42, bseg=3, name="bag")
    ph = [rnd.uniform(0, 6) for _ in range(3)]
    b.displace(lambda c: (c.x * (0.95 + 0.05 * math.sin(c.z * 23 + ph[0])), c.y * (0.95 + 0.05 * math.sin(c.x * 19 + ph[1])),
                          c.z * (0.94 + 0.06 * math.sin(c.y * 17 + ph[2]))))
    if knot and detail():
        k = lathe([(0.001, 0.0), (0.02, 0.01), (0.012, 0.04), (0.025, 0.06), (0.001, 0.07)], 6, mat=mat)
        k.rot(x=rnd.uniform(-25, 25)).move(0, 0, sz * 0.38)
    return b


def _bulbs(a, b, sag, n, mat="emit_amber", dead=(), wire="rubber"):
    """String of hanging festoon bulbs on a sagging wire from a to b."""
    pts = _sag(a, b, sag, 10)
    _cable(pts, r=0.0045, mat=wire)
    A, B = Vector(a), Vector(b)
    for i in range(n):
        t = (i + 0.5) / n
        c = A.lerp(B, t) - Vector((0, 0, sag * 4 * t * (1 - t)))
        if detail():
            cyl(0.008, 0.025, 6, at=(c.x, c.y, c.z - 0.025), mat="rubber")
            lathe([(0.004, -0.075), (0.012, -0.072), (0.019, -0.058), (0.017, -0.04), (0.008, -0.027)], 6, at=tuple(c),
                  mat="black" if i in dead else mat)
        else:
            box(0.03, 0.03, 0.04, at=(c.x, c.y, c.z - 0.05), mat="black" if i in dead else mat)


def _neon_sign(w, h, seed, neon="emit_neon_magenta", outline="emit_neon_cyan", n=2, both=True, t=0.03):
    """Small salvaged neon sign: dark board (XZ plane, centred on the origin, front -Y) with glyph tubes and a neon
    outline on the front (and back)."""
    bd = box(w, t, h, mat="metal_dark", bevel=0.006)
    inset(bd, faces_where(bd, lambda f: abs(f.normal.y) > 0.9), 0.02, -0.004, mat="black")
    g = min(h * 0.62, (w - 0.08) / n * 0.85)
    for s in ((-1, 1) if both else (-1,)):
        r2 = random.Random(seed)
        for i in range(n):
            x = -w / 2 + 0.04 + (i + 0.5) * (w - 0.08) / n
            if K.LOD < 2:
                _neon_glyph(r2, (x + s * g / 2, s * (t / 2 + 0.002), -g / 2), (-s, 0, 0), (0, 0, 1), (g, g), r=0.006, mat=neon)
        o = [(-w / 2 + 0.025, -h / 2 + 0.025), (w / 2 - 0.025, -h / 2 + 0.025), (w / 2 - 0.025, h / 2 - 0.025), (-w / 2 + 0.025, h / 2 - 0.025)]
        tube([(x, s * (t / 2 + 0.002), z) for x, z in o], 0.006, 6, outline, closed=True)


def tarp_shelter(W=4.0, D=3.0, mat="tarp", seed=2):
    """Street-camp tarp shelter: four poles with clamp collars and sandbag weights, sagging tarp roof (double
    sided), festoon bulbs along the low front beam, LED bar under the back beam, a caged work lamp on a feed cable,
    a salvaged neon glyph sign, guy lines with stakes."""
    hf, hb = 2.1, 2.6
    for sx in (-1, 1):
        for sy, h in ((-1, hf), (1, hb)):
            cyl(0.035, h, 8, at=(sx * W / 2, sy * D / 2, 0), mat="metal_dark")
            cyl(0.05, 0.12, 8, at=(sx * W / 2, sy * D / 2, h - 0.14), mat="metal_dark")
            if detail():
                box(0.16, 0.16, 0.012, at=(sx * W / 2, sy * D / 2, 0), mat="metal_dark", base=True)
                _bag((0.32, 0.22, 0.14), seed + int(sx * 3 + sy), mat="tarp").move(sx * W / 2 + 0.12 * sx, sy * D / 2, 0.07)
                _bag((0.3, 0.2, 0.13), seed + 20 + int(sx * 3 + sy), mat="tarp").rot(z=70).move(sx * W / 2 + 0.03 * sx, sy * D / 2 + 0.1 * sy, 0.19)
    beam((-W / 2, -D / 2, hf - 0.03), (W / 2, -D / 2, hf - 0.03), 0.04, mat="metal_dark")
    beam((-W / 2, D / 2, hb - 0.03), (W / 2, D / 2, hb - 0.03), 0.04, mat="metal_dark")
    for sx in (-1, 1):
        beam((sx * W / 2, -D / 2, hf - 0.03), (sx * W / 2, D / 2, hb - 0.03), 0.04, mat="metal_dark")
    _cloth(W + 0.5, D + 0.5, hf + 0.03, hb + 0.03, 0.16, seed, mat)
    # lights: festoon bulbs on the front beam, LED bar under the back beam, caged work lamp
    _bulbs((-W / 2 + 0.05, -D / 2 - 0.03, hf - 0.06), (W / 2 - 0.05, -D / 2 - 0.03, hf - 0.06), 0.14, 12 if detail() else 6,
           dead=(3, 8))
    box(W * 0.6, 0.025, 0.012, at=(0, D / 2 - 0.03, hb - 0.058), mat="emit_strip_cyan")
    lx, ly = 0.35 * W / 4, 0.2
    zl = hf + (hb - hf) * (ly / D + 0.5) - 0.62
    lathe([(0.001, -0.02), (0.05, -0.01), (0.06, 0.04), (0.03, 0.08), (0.012, 0.1)], 8, at=(lx, ly, zl), mat="metal_dark")
    cyl(0.035, 0.06, 8, at=(lx, ly, zl - 0.04), mat="emit_panel_warm")
    if detail():
        for k in range(4):
            a = math.radians(k * 90 + 45)
            tube([(lx, ly, zl - 0.07), (lx + math.cos(a) * 0.045, ly + math.sin(a) * 0.045, zl - 0.04), (lx + math.cos(a) * 0.05, ly + math.sin(a) * 0.05, zl)], 0.003, 4, "metal_dark")
        # feed cable: from the back-right pole, along the back beam, down to the lamp
        _cable([(W / 2 - 0.03, D / 2 - 0.05, hb - 0.2), (W / 2 - 0.4, D / 2 - 0.06, hb - 0.12), (W / 4, D / 2 - 0.08, hb - 0.2)] +
               _sag((W / 4, D / 2 - 0.08, hb - 0.2), (lx, ly, zl + 0.1), 0.12, 6)[1:], r=0.008)
        _cable(_sag((-W / 2 + 0.05, D / 2 - 0.04, hb - 0.1), (W / 4, D / 2 - 0.05, hb - 0.12), 0.25, 8), r=0.007)
        # salvaged neon sign lashed under the front beam
        with K.placed(_xf(-W / 2 + 0.75, -D / 2 - 0.06, hf - 0.3)):
            _neon_sign(0.62, 0.26, seed + 40, neon="emit_neon_pink", outline="emit_neon_cyan", n=2)
        for x in (-W / 2 + 0.5, -W / 2 + 1.0):
            tube([(x, -D / 2 - 0.06, hf - 0.17), (x, -D / 2 - 0.03, hf - 0.06)], 0.004, 4, "rubber")
        for sx in (-1, 1):
            tube([(sx * (W / 2 + 0.2), -D / 2 - 0.2, hf - 0.05), (sx * (W / 2 + 0.9), -D / 2 - 1.1, 0.02)], 0.006, 4, "rubber")
            box(0.03, 0.03, 0.15, at=(sx * (W / 2 + 0.9), -D / 2 - 1.1, 0.0), mat="metal_dark", base=True)
    return {"colliders": [K.collider_box((sx * W / 2, sy * D / 2, 1.2), (0.12, 0.12, 2.4)) for sx in (-1, 1) for sy in (-1, 1)]}


def market_stall(canopy="tarp", seed=5):
    """Night-market stall: painted counter (customer side -Y = Unity +Z) with corrugated front, LED edge strip and a
    neon glyph plate, poles + tarp canopy, festoon bulbs, hanging neon glyph sign, warm LED work bar on a cable,
    goods on the counter and crates on the back shelf."""
    rnd = random.Random(seed)
    accent = "emit_strip_magenta" if canopy == "tarp" else "emit_strip_cyan"
    neon_a, neon_b = ("emit_neon_magenta", "emit_neon_cyan") if canopy == "tarp" else ("emit_neon_cyan", "emit_neon_yellow")
    c = box(2.6, 0.9, 0.97, at=(0, 0, 0.03), mat="metal_painted", base=True, bevel=0.012)
    inset(c, faces_where(c, lambda f: f.normal.y < -0.9), 0.06, -0.012, mat="corrugated")
    box(2.5, 0.8, 0.04, at=(0, 0, 0), mat="metal_dark", base=True)
    box(2.72, 1.02, 0.05, at=(0, 0, 1.0), mat="wood", base=True, bevel=0.008)
    box(2.5, 0.008, 0.014, at=(0, -0.452, 0.982), mat=accent)
    for sx in (-1.25, 1.25):
        for sy in (-0.42, 0.42):
            cyl(0.03, 2.6, 8, at=(sx, sy, 0), mat="metal_dark")
            if detail():
                cyl(0.042, 0.1, 8, at=(sx, sy, 1.05), mat="metal_dark")
    for sy, z in ((-0.42, 2.55), (0.42, 2.7)):
        beam((-1.3, sy, z), (1.3, sy, z), 0.035, mat="metal_dark")
    _cloth(2.95, 1.45, 2.57, 2.73, 0.08, seed, canopy, nx=8, ny=4, droop=0.06)
    _bulbs((-1.22, -0.45, 2.52), (1.22, -0.45, 2.52), 0.13, 10 if detail() else 5, dead=(6,))
    # warm LED work bar on two cables (keeps the emit_panel_warm slot)
    bar = box(0.6, 0.07, 0.035, at=(0, 0.02, 2.33), mat="metal_dark", bevel=0.008)
    inset(bar, faces_where(bar, lambda f: f.normal.z < -0.9), 0.012, -0.003, mat="emit_panel_warm")
    for x in (-0.25, 0.25):
        cyl(0.004, 2.62 - 2.35, 4, at=(x, 0.02, 2.35), mat="rubber")
    # hanging neon glyph sign under the front beam
    with K.placed(_xf(0.0, -0.44, 2.2)):
        _neon_sign(0.86, 0.28, seed + 60, neon=neon_a, outline=neon_b, n=3)
    # neon glyph plate on the counter front
    with K.placed(_xf(0.72, -0.475, 0.62)):
        _neon_sign(0.56, 0.24, seed + 70, neon=neon_b, outline=neon_a, n=2, both=False)
    for i in range(5):
        s = rnd.uniform(0.14, 0.3)
        m = rnd.choice(["tarp", "tarp_blue", "wood", "metal_painted_yellow", "crate"])
        x = -1.05 + i * 0.52 + rnd.uniform(-0.05, 0.05)
        if m == "crate":
            y = rnd.uniform(-0.2, 0.2)
            box(s * 1.3, s, s * 0.8, at=(x, y, 1.05), mat="wood", base=True, bevel=0.01).rot_about((x, y, 1.05), z=rnd.uniform(-20, 20))
        elif m == "tarp" or m == "tarp_blue":
            _bag((s * 1.2, s, s * 0.7), seed + i, mat=m, knot=True).move(x, rnd.uniform(-0.2, 0.2), 1.05 + s * 0.35)
        else:
            cyl(s * 0.35, s, 10, at=(x, rnd.uniform(-0.25, 0.25), 1.05), mat=m)
    if detail():
        for x in (-0.3, 0.3):
            tube([(x, -0.44, 2.34), (x, -0.43, 2.45), (x, -0.42, 2.53)], 0.004, 4, "metal_bare")
        # shelf with crates under the counter, visible from the back
        box(2.4, 0.5, 0.03, at=(0, 0.48, 0.5), mat="wood")
        for i, (x, w, h, m) in enumerate(((-0.8, 0.42, 0.3, "plastic_dark"), (-0.3, 0.36, 0.24, "wood"), (0.55, 0.5, 0.32, "metal_painted"))):
            box(w, 0.36, h, at=(x, 0.5, 0.515), mat=m, base=True, bevel=0.01)
        # power cable draped along the back beam and down the back-right pole
        _cable(_sag((-1.25, 0.45, 2.66), (0.0, 0.44, 2.66), 0.18, 8) + _sag((0.0, 0.44, 2.66), (1.22, 0.45, 2.6), 0.14, 8)[1:] +
               [(1.22, 0.46, 1.9), (1.22, 0.47, 1.1)], r=0.008)
        # price tags / LED price strip on the counter
        box(0.3, 0.012, 0.05, at=(-0.7, -0.505, 1.04), mat="emit_panel_cyan" if canopy == "tarp" else "emit_panel_magenta")
    return {"colliders": [K.collider_box((0, 0, 0.52), (2.72, 1.02, 1.05))]}


def _chamfer_sec(x0, x1, y0, y1, c, z):
    """Chamfered-rectangle section (8 points, CCW from the front-left) at height z."""
    return [(x0 + c, y0, z), (x1 - c, y0, z), (x1, y0 + c, z), (x1, y1 - c, z), (x1 - c, y1, z), (x0 + c, y1, z), (x0, y1 - c, z), (x0, y0 + c, z)]


def terminal_kiosk(on=True):
    em = (lambda m: m) if on else (lambda m: "black")
    # plinth: chamfered slab with anchor bolts and a cyan under-glow lip on the front
    pl = K.loft([_chamfer_sec(-0.41, 0.41, -0.3, 0.3, 0.05, 0.0), _chamfer_sec(-0.41, 0.41, -0.3, 0.3, 0.05, 0.045),
                 _chamfer_sec(-0.39, 0.39, -0.28, 0.28, 0.04, 0.06)], mat="metal_dark", name="plinth")
    pl.bevel(0.004, 1, angle=20)
    box(0.62, 0.006, 0.012, at=(0, -0.3015, 0.024), mat=em("emit_strip_cyan"))
    if detail():
        for sx in (-1, 1):
            for sy in (-1, 1):
                cyl(0.016, 0.01, 6, at=(sx * 0.35, sy * 0.24, 0.052), mat="metal_bare", start=0)
    # body: tapered faceted pillar, glossy shell, carbon side panels, LED front edges
    body = K.loft([_chamfer_sec(-0.32, 0.32, -0.21, 0.25, 0.035, 0.06), _chamfer_sec(-0.3, 0.3, -0.2, 0.22, 0.035, 0.9),
                   _chamfer_sec(-0.29, 0.29, -0.19, 0.2, 0.035, 1.12)], mat="paint_glossy_dark", name="body")
    fl = lambda f: f.normal.y < -0.5 and f.normal.x < -0.3
    fr = lambda f: f.normal.y < -0.5 and f.normal.x > 0.3
    body.set_mat(em("emit_strip_cyan"), where=lambda f: (fl(f) or fr(f)) and f.calc_center_median().z > 0.1)
    inset(body, faces_where(body, lambda f: abs(f.normal.x) > 0.95), 0.05, -0.006, mat="carbon_panel")
    inset(body, faces_where(body, lambda f: f.normal.y < -0.95), 0.04, -0.012, mat="plastic_dark")
    inset(body, faces_where(body, lambda f: f.normal.y > 0.95), 0.045, -0.004, mat="metal_dark")
    # front panel: dispenser slit, status LEDs, glyph plate, louvre vent near the floor
    fy = lambda z: -0.21 + 0.01 * (z - 0.06) / 0.84 + 0.012      # recessed front surface y at height z
    box(0.3, 0.02, 0.05, at=(0, fy(0.62) - 0.008, 0.62), mat="metal_dark", bevel=0.006)
    box(0.24, 0.006, 0.012, at=(0, fy(0.62) - 0.018, 0.62), mat="black")
    if detail():
        for i, m in enumerate(("emit_green", "emit_amber", "emit_cyan")):
            box(0.016, 0.006, 0.008, at=(-0.05 + i * 0.05, fy(0.69) - 0.002, 0.69), mat=em(m) if on else "black")
        box(0.16, 0.004, 0.05, at=(0, fy(0.8) - 0.001, 0.8), mat="metal_painted_white")
        rng = random.Random(77)
        for gx in (-0.05, 0.0, 0.05):
            for pts, closed in _glyph_strokes(rng):
                P = [(gx - 0.018 + u * 0.036, fy(0.8) - 0.0035, 0.782 + v * 0.036) for u, v in pts]
                tube(P, 0.0022, 4, "black", closed=closed)
        _vent(0.4, 0.12, 6, (0, fy(0.2) - 0.0, 0.2))
    # console: sloped shelf with keypad, card slot and palm scanner
    prof = [(-0.18, 0.92), (-0.39, 1.012), (-0.3985, 1.03), (-0.392, 1.046), (-0.18, 1.098)]
    con = extrude(prof, 0.54, plane="YZ", mat="paint_glossy_dark", name="console")
    con.bevel(0.006, 1, angle=25)
    slope = math.degrees(math.atan2(1.098 - 1.046, 0.392 - 0.18))
    top = lambda t: (-0.392 + (0.392 - 0.18) * t, 1.046 + (1.098 - 1.046) * t)
    kpad = box(0.2, 0.15, 0.008, mat="metal_dark", bevel=0.002)
    y, z = top(0.45)
    kpad.rot(x=slope).move(-0.12, y, z + 0.004)
    if detail():
        for i in range(4):
            for j in range(3):
                y, z = top(0.2 + i * 0.17)
                k = box(0.045, 0.026, 0.01, mat="plastic_dark", bevel=0.002)
                k.rot(x=slope).move(-0.18 + j * 0.06, y, z + 0.012)
    y, z = top(0.5)
    cs = box(0.11, 0.07, 0.03, mat="metal_dark", bevel=0.006)
    cs.rot(x=slope).move(0.12, y + 0.035, z + 0.016)
    if detail():
        sl = box(0.08, 0.004, 0.006, mat="black")
        sl.rot(x=slope).move(0.12, y + 0.0, z + 0.024)
        led = box(0.012, 0.006, 0.006, mat=em("emit_green"))
        led.rot(x=slope).move(0.165, y - 0.002, z + 0.03)
        y2, z2 = top(0.18)
        pad = box(0.1, 0.06, 0.004, mat=em("emit_panel_cyan") if on else "glass_dark")
        pad.rot(x=slope).move(0.12, y2, z2 + 0.004)
    # support gusset under the console
    extrude([(-0.18, 0.86), (-0.33, 0.995), (-0.18, 0.99)], 0.06, plane="YZ", mat="metal_dark").bevel(0.004)
    # neck + head (screen face unchanged: 0.62 x 0.44 inset into a 0.72 x 0.54 housing tilted back 20 deg)
    box(0.3, 0.14, 0.12, at=(0, 0.0, 1.08), mat="metal_dark", base=True, bevel=0.01)
    with K.placed(_xf(0, -0.06, 1.38, rx=-20)):
        hd = box(0.72, 0.14, 0.54, mat="paint_glossy_dark", bevel=0.025, bseg=2)
        inset(hd, faces_where(hd, lambda f: f.normal.y < -0.9), 0.05, -0.01, mat="screen" if on else "glass_dark")
        inset(hd, faces_where(hd, lambda f: f.normal.y > 0.9), 0.06, -0.006, mat="carbon_panel")
        # rain hood: visor + side cheeks
        vz = extrude([(-0.055, 0.268), (-0.06, 0.255), (-0.16, 0.198), (-0.163, 0.21)], 0.74, plane="YZ", mat="paint_glossy_dark", name="visor")
        for sx in (-1, 1):
            ch = extrude([(-0.068, -0.25), (-0.068, 0.262), (-0.158, 0.203), (-0.09, -0.25)], 0.012, plane="YZ", mat="paint_glossy_dark", name="cheek")
            ch.move(sx * 0.364, 0, 0)
        box(0.6, 0.004, 0.008, at=(0, -0.071, 0.246), mat=em("emit_strip_cyan"))
        box(0.6, 0.004, 0.008, at=(0, -0.071, -0.246), mat=em("emit_strip_cyan"))
        if detail():
            # back heat-sink ribs + cable gland
            for i in range(6):
                box(0.008, 0.012, 0.36, at=(-0.15 + i * 0.06, 0.076, -0.02), mat="metal_dark")
            if on:
                # holo frame hint: thin additive outline just in front of the bezel, fed by two corner emitters
                for (w, h, x, z) in ((0.66, 0.005, 0, 0.243), (0.66, 0.005, 0, -0.243), (0.005, 0.48, -0.332, 0), (0.005, 0.48, 0.332, 0)):
                    box(w, 0.002, h, at=(x, -0.09, z), mat="holo_cyan")
            for sx in (-1, 1):
                box(0.03, 0.02, 0.02, at=(sx * 0.33, -0.075, -0.25), mat="metal_dark", bevel=0.004)
                box(0.01, 0.004, 0.01, at=(sx * 0.33, -0.086, -0.25), mat=em("emit_cyan"))
    # service cable from the head into the plinth (back)
    if detail():
        _cable([(0.2, 0.17, 1.45), (0.22, 0.24, 1.25), (0.24, 0.255, 0.9), (0.24, 0.265, 0.4), (0.24, 0.27, 0.12), (0.24, 0.255, 0.06)], r=0.012)
        for z in (0.35, 0.75):
            box(0.05, 0.03, 0.02, at=(0.24, 0.262, z), mat="metal_bare")
        # back door hinges + lock
        for z in (0.25, 0.85):
            cyl(0.01, 0.07, 8, at=(-0.24, 0.258, z - 0.035), mat="metal_bare")
        box(0.03, 0.01, 0.05, at=(0.2, 0.254, 0.62), mat="metal_bare", bevel=0.003)
    n = (0, -math.cos(math.radians(20)), math.sin(math.radians(20)))
    ctr = (0, -0.06 - 0.07 * math.cos(math.radians(20)), 1.38 + 0.07 * math.sin(math.radians(20)))
    return {"colliders": [K.collider_box((0, 0, 0.75), (0.82, 0.6, 1.5))],
            "screen": {"center": K.to_unity_vec(ctr), "size": [0.62, 0.44], "normal": K.to_unity_vec(n), "material": "screen"}}


# ============================================================================================== pipes / rails / frames
def pipe_straight(L=1.0, r=0.18, mat="metal_bare"):
    """Straight pipe along X (scaled to length in Unity): smooth 24-sided shell, longitudinal weld seam, painted
    identification line along the side (both stretch cleanly when scaled in X)."""
    cyl(r, L, 24, at=(-L / 2, 0, 0), axis="X", mat=mat)
    if detail():
        beam((-L / 2 + 0.002, 0, -r + 0.003), (L / 2 - 0.002, 0, -r + 0.003), 0.012, 0.008, mat="metal_dark", up=(0, 0, 1))
        a = math.radians(35)
        beam((-L / 2 + 0.002, -math.cos(a) * (r + 0.001), math.sin(a) * (r + 0.001)), (L / 2 - 0.002, -math.cos(a) * (r + 0.001), math.sin(a) * (r + 0.001)),
             0.03, 0.003, mat="metal_painted_yellow", up=(0, -math.cos(a), math.sin(a)))
    return {"colliders": [{"type": "capsule", "center": [0, 0, 0], "radius": r, "height": L, "direction": "X"}]}


def _flange_bolts(center, axis, r_bolt, n=8, face_off=0.025, sign=1, r=0.012, h=0.012):
    """Hex bolt heads on a flange face (axis 'X' or 'Y'), pointing along sign*axis."""
    if not detail():
        return
    cx, cy, cz = center
    for i in range(n):
        a = math.tau * (i + 0.5) / n
        if axis == "X":
            at, nn = (cx + sign * face_off, cy + math.cos(a) * r_bolt, cz + math.sin(a) * r_bolt), (sign, 0, 0)
        else:
            at, nn = (cx + math.cos(a) * r_bolt, cy + sign * face_off, cz + math.sin(a) * r_bolt), (0, sign, 0)
        _bolt(at, n=nn, r=r, h=h)


def pipe_elbow(r=0.18, R=0.45, mat="metal_bare"):
    """90 deg elbow with bolted flanges, weld beads and a painted hazard band at mid-bend."""
    t = torus(R, r, arc=90, n_major=12, n_minor=20, mat=mat, start=180)
    t.move(R, R, 0)
    t.set_mat("metal_painted_yellow", where=lambda f: 218 < (math.degrees(math.atan2(f.calc_center_median().y - R, f.calc_center_median().x - R)) % 360) < 232)
    for at, ax in (((0, R, 0), "Y"), ((R, 0, 0), "X")):
        cyl(r + 0.045, 0.05, 16, at=at, axis=ax, center=True, mat="metal_dark", bevel=0.008)
        if detail():
            ring = torus(r + 0.004, 0.006, n_major=24, n_minor=4, mat="metal_dark")
            if ax == "Y":
                ring.rot(x=90).move(at[0], at[1] - 0.03, at[2])
            else:
                ring.rot(y=90).move(at[0] - 0.03, at[1], at[2])
            _flange_bolts(at, ax, r + 0.026, sign=-1, r=0.011, h=0.01)
    return {"colliders": "mesh"}


def pipe_flange(r=0.18):
    """Bolted flange pair: two plates with a rubber gasket between them, 8 through-bolts with hex nuts both sides."""
    for x in (-0.017, 0.017):
        cyl(r + 0.05, 0.026, 16, at=(x, 0, 0), axis="X", center=True, mat="metal_dark", bevel=0.006)
    cyl(r + 0.035, 0.008, 16, at=(0, 0, 0), axis="X", center=True, mat="rubber")
    if detail():
        for i in range(8):
            a = math.tau * i / 8
            y, z = math.cos(a) * (r + 0.025), math.sin(a) * (r + 0.025)
            cyl(0.009, 0.08, 6, at=(0, y, z), axis="X", center=True, mat="metal_bare")
            for sx in (-1, 1):
                cyl(0.017, 0.01, 6, at=(sx * 0.035, y, z), axis="X", center=True, mat="metal_bare", start=0)
    return {"colliders": "mesh"}


def pipe_bracket(r=0.18, standoff=0.3):
    """Wall clamp: pivot on the wall surface (y=0), pipe axis along X at y=-standoff. Bolted wall plate, gusseted
    standoff arm, saddle block and a flat strap band around the pipe."""
    box(0.16, 0.02, 0.3, at=(0, -0.01, 0), mat="metal_dark", bevel=0.004)
    beam((0, -0.02, 0), (0, -standoff + r, 0), 0.06, 0.06, mat="metal_dark", bevel=0.004)
    # flat strap band (outer radius r + 0.024 like the legacy ring)
    band = lathe([(r + 0.024, -0.025), (r + 0.024, 0.025), (r + 0.004, 0.025), (r + 0.004, -0.025)], 20, mat="metal_dark",
                 close_bottom=False, close_top=False)
    band.rot(y=90).move(0, -standoff, 0)
    if detail():
        box(0.09, 0.03, 0.08, at=(0, -standoff + r + 0.01, 0), mat="metal_dark", bevel=0.004)
        for sz in (-1, 1):
            extrude([(-0.02, 0.0), (-0.1, 0.0), (-0.02, 0.09)], 0.008, plane="YZ", mat="metal_dark").scale(1, 1, sz).move(0, 0, sz * 0.031)
            for sx in (-1, 1):
                _bolt((sx * 0.055, -0.02, sz * 0.11), n=(0, -1, 0), r=0.01, h=0.008, washer=True)
        for sx in (-1, 1):
            cyl(0.008, 0.05, 6, at=(sx * 0.03, -standoff + r + 0.025, -0.04), mat="metal_bare")
    return {"colliders": "none"}


def railing(L=2.0, h=1.05, with_end_post=False):
    """Safety railing module: square posts on bolted base plates with weld collars, yellow top rail with end caps,
    mid rail, kick plate with hazard stripes on both faces."""
    posts = [-L / 2 + 0.03, 0.0] + ([L / 2 - 0.03] if with_end_post else [])
    for x in posts:
        box(0.05, 0.05, h - 0.02, at=(x, 0, 0), mat="metal_dark", base=True, bevel=0.006)
        box(0.11, 0.11, 0.012, at=(x, 0, 0), mat="metal_dark", base=True, bevel=0.002)
        if detail():
            for sx in (-1, 1):
                for sy in (-1, 1):
                    _bolt((x + sx * 0.038, sy * 0.038, 0.012), r=0.007, h=0.006)
            box(0.06, 0.06, 0.018, at=(x, 0, 0.012), mat="metal_dark", base=True, bevel=0.003)
            box(0.06, 0.06, 0.02, at=(x, 0, h * 0.52 - 0.01), mat="metal_dark", base=True, bevel=0.003)
            box(0.012, 0.016, 0.12, at=(x, 0, 0.1), mat="metal_dark")
    cyl(0.024, L, 12, at=(-L / 2, 0, h), axis="X", mat="metal_painted_yellow")
    cyl(0.016, L, 8, at=(-L / 2, 0, h * 0.52), axis="X", mat="metal_dark")
    box(L, 0.006, 0.1, at=(0, 0, 0.04), mat="metal_dark", base=True)
    if detail():
        for s_ in (-1, 1):
            with K.placed(_xf(0, s_ * 0.003, 0.05, rz=0 if s_ < 0 else 180)):
                _stripes(L - 0.02, 0.08, pitch=0.16, frac=0.5, slant=0.9, depth=0.002)
        for x in posts:
            box(0.056, 0.056, 0.03, at=(x, 0, h - 0.055), mat="metal_dark", base=True, bevel=0.003)
    return {"colliders": [K.collider_box((0, 0, 0.6), (L, 0.15, 1.2))]}


def railing_post():
    box(0.05, 0.05, 1.03, mat="metal_dark", base=True, bevel=0.006)
    box(0.11, 0.11, 0.012, mat="metal_dark", base=True, bevel=0.002)
    lathe([(0.001, 1.03), (0.03, 1.035), (0.03, 1.06), (0.001, 1.075)], 10, mat="metal_painted_yellow")
    if detail():
        for sx in (-1, 1):
            for sy in (-1, 1):
                _bolt((sx * 0.038, sy * 0.038, 0.012), r=0.007, h=0.006)
        box(0.06, 0.06, 0.018, at=(0, 0, 0.012), mat="metal_dark", base=True, bevel=0.003)
        box(0.058, 0.058, 0.02, at=(0, 0, 0.98), mat="metal_dark", base=True, bevel=0.003)
        box(0.012, 0.016, 0.12, at=(0, 0, 0.1), mat="metal_dark")
    return {"colliders": [K.collider_box((0, 0, 0.53), (0.11, 0.11, 1.06))]}


def door_frame(w=2.0, h=3.0, light="emit_amber"):
    """Industrial door surround for a w x h opening (opening centred at x=0, floor at z=0): jambs with recessed
    plate panels and bolt rows, hazard chevrons, header with a lit amber strip (code-switchable emit slot), access
    keypad with status LED, cable conduit up the jamb into a junction box, header vent."""
    for sx in (-1, 1):
        j = box(0.3, 0.5, h, at=(sx * (w / 2 + 0.15), 0, 0), mat="metal_dark", base=True, bevel=0.02)
        inset(j, faces_where(j, lambda f: abs(f.normal.y) > 0.9), 0.05, -0.008, mat="metal_plate")
        if detail():
            for k in range(5):
                st = box(0.3, 0.012, 0.09, mat="metal_painted_yellow")
                st.rot(y=35 * sx).move(sx * (w / 2 + 0.15), -0.252, 0.18 + k * 0.2)
            for sy in (-1, 1):
                for k in range(int((h - 0.3) / 0.35)):
                    z = 1.25 + k * 0.35
                    if z > h - 0.15:
                        break
                    for xx in (0.035, 0.265):
                        _bolt((sx * (w / 2 + xx), sy * 0.25, z), n=(0, sy, 0), r=0.009, h=0.005)
    hd = box(w + 0.6, 0.5, 0.3, at=(0, 0, h), mat="metal_dark", base=True, bevel=0.02)
    inset(hd, faces_where(hd, lambda f: abs(f.normal.y) > 0.9), 0.04, -0.006, mat="metal_plate")
    if light:
        box(w, 0.52, 0.05, at=(0, 0, h - 0.005), mat=light, base=True)
    if detail():
        # access keypad on the right jamb (front)
        x = w / 2 + 0.15
        box(0.16, 0.02, 0.24, at=(x, -0.245, 1.3), mat="paint_glossy_dark", bevel=0.006)
        box(0.12, 0.004, 0.06, at=(x, -0.256, 1.37), mat="black")
        for i in range(3):
            for j_ in range(3):
                box(0.025, 0.005, 0.02, at=(x - 0.035 + j_ * 0.035, -0.256, 1.29 - i * 0.03), mat="plastic_dark")
        box(0.1, 0.004, 0.008, at=(x, -0.256, 1.212), mat="emit_green")
        # conduit up the left jamb into a junction box on the header
        xl = -(w / 2 + 0.27)
        tube([(xl, -0.245, 0.05), (xl, -0.245, h - 0.2), (xl, -0.24, h + 0.08), (xl + 0.2, -0.24, h + 0.12)], 0.016, 6, "metal_dark")
        for z in (0.4, 1.2, 2.0, h - 0.4):
            box(0.05, 0.012, 0.03, at=(xl, -0.256, z), mat="metal_bare")
        box(0.2, 0.012, 0.16, at=(xl + 0.3, -0.256, h + 0.14), mat="metal_dark", bevel=0.004)
        # header vent + warning chevrons
        _vent(w * 0.4, 0.1, 4, (w * 0.18, -0.25, h + 0.15))
        with K.placed(_xf(-w * 0.12, -0.256, h + 0.1)):
            _stripes(w * 0.3, 0.1, pitch=0.1, slant=0.6, depth=0.003, chevron=True, back="black")
    return {"colliders": [K.collider_box((sx * (w / 2 + 0.15), 0, h / 2), (0.3, 0.5, h)) for sx in (-1, 1)] +
            [K.collider_box((0, 0, h + 0.15), (w + 0.6, 0.5, 0.3))]}


def bollard():
    """LED bollard: flanged base with anchor bolts, glossy shaft with a reflective hazard band, louvred LED head."""
    lathe([(0.001, 0.0), (0.13, 0.0), (0.13, 0.018), (0.122, 0.028), (0.104, 0.034), (0.001, 0.034)], 16, mat="metal_dark")
    lathe([(0.1, 0.03), (0.1, 0.74), (0.098, 0.75)], 16, mat="paint_glossy_dark", close_bottom=False, close_top=True)
    cyl(0.103, 0.075, 16, at=(0, 0, 0.52), mat="metal_painted_yellow")
    if detail():
        for k in range(6):
            b = box(0.025, 0.006, 0.08, mat="black")
            b.rot(y=35).move(0, -0.1035, 0.557).rot(z=k * 60 + 30)
        for k in range(4):
            a = math.radians(45 + k * 90)
            _bolt((math.cos(a) * 0.115, math.sin(a) * 0.115, 0.018), r=0.01, h=0.008, washer=True)
        for z in (0.3, 0.46):
            torus(0.1005, 0.0035, n_major=24, n_minor=4, mat="metal_dark").move(0, 0, z)
    # LED head: chrome collars, glowing window behind louvre fins, chamfered cap
    lathe([(0.104, 0.74), (0.104, 0.77), (0.096, 0.775)], 16, mat="chrome_scratched", close_bottom=False, close_top=False)
    cyl(0.09, 0.085, 16, at=(0, 0, 0.775), mat="emit_strip_cyan")
    for k in range(8 if detail() else 4):
        f = box(0.012, 0.03, 0.085, at=(0, -0.093, 0.8175), mat="metal_dark")
        f.rot(z=k * (45 if detail() else 90) + 22.5)
    lathe([(0.104, 0.86), (0.104, 0.885), (0.094, 0.9), (0.06, 0.915), (0.001, 0.92)], 16, mat="paint_glossy_dark")
    torus(0.0995, 0.004, n_major=24, n_minor=4, mat="chrome_scratched").move(0, 0, 0.873)
    return {"colliders": [K.collider_box((0, 0, 0.46), (0.26, 0.26, 0.92))]}


def traffic_cone():
    """Traffic cone with a reflective collar, a glowing LED ring and a battery puck on the weighted base."""
    b = K.loft([_chamfer_sec(-0.19, 0.19, -0.19, 0.19, 0.04, 0.0), _chamfer_sec(-0.19, 0.19, -0.19, 0.19, 0.04, 0.02),
                _chamfer_sec(-0.175, 0.175, -0.175, 0.175, 0.035, 0.034)], mat="plastic_dark", name="base")
    b.bevel(0.004, 1, angle=20)
    prof = [(0.16, 0.03), (0.155, 0.045)] + [(0.155 - (0.125 * (z - 0.045) / 0.655), z) for z in (0.22, 0.3, 0.42, 0.5, 0.56, 0.64)] + [(0.03, 0.70), (0.001, 0.71)]
    c = lathe(prof, 16, mat="plastic_orange")
    c.set_mat("metal_painted_white", where=lambda f: 0.42 < f.calc_center_median().z < 0.5)
    r_at = lambda z: 0.155 - 0.125 * (z - 0.045) / 0.655
    # LED ring band (sits proud of the cone wall) + clip housing
    lathe([(r_at(0.24) + 0.006, 0.24), (r_at(0.3) + 0.006, 0.3)], 16, mat="emit_strip_yellow", close_bottom=False, close_top=False)
    torus(r_at(0.236) + 0.004, 0.006, n_major=16, n_minor=4, mat="plastic_dark").move(0, 0, 0.236)
    torus(r_at(0.304) + 0.004, 0.006, n_major=16, n_minor=4, mat="plastic_dark").move(0, 0, 0.304)
    if detail():
        box(0.06, 0.03, 0.03, at=(0, -r_at(0.27) - 0.012, 0.27), mat="plastic_dark", bevel=0.006)
        box(0.012, 0.004, 0.008, at=(0.015, -r_at(0.27) - 0.028, 0.275), mat="emit_red")
        for sx in (-1, 1):
            for sy in (-1, 1):
                cyl(0.012, 0.006, 8, at=(sx * 0.15, sy * 0.15, 0.03), mat="metal_bare")
    return {"colliders": [K.collider_box((0, 0, 0.35), (0.38, 0.38, 0.71))]}


ASSETS_B = {
    "Bench_Street": dict(fn=bench, cat="street", zones=["plaza", "metro", "facility"], notes="1.8 m cantilever bench: sculpted steel side frames, wooden slats, anti-sleep divider, cyan LED under-glow (emit_strip_cyan). Seat faces +Z."),
    "Bench_Metal": dict(fn=bench, kw={"slat": "metal_painted"}, cat="street", zones=["metro"], notes="Cantilever bench with perforated painted-steel seat/back (metal_painted) and magenta LED under-glow (emit_strip_magenta)."),
    "TrashBin": dict(fn=trash_bin, cat="street", zones=["plaza", "metro"], notes="Smart litter bin: faceted glossy shell, green sorting panel (metal_painted_green), cyan status ring (emit_strip_cyan), fill-level LEDs, sensor eye, chute lid with an overflowing bag."),
    "TrashBin_Tipped": dict(fn=trash_bin, kw={"tipped": True}, cat="street", zones=["plaza", "metro"], notes="Knocked-over smart bin (open mouth toward +Z), lid lying beside it, spilled trash bags."),
    "Sign_Panel_S": dict(fn=sign_panel, kw={"w": 2.4, "h": 0.5}, cat="signage", zones=["plaza", "metro", "facility", "vault"], pivot="back-centre",
                         notes="Backlit LED wall sign, 2.4 x 0.5 m blank 'screen' face (UV 0..1) for text/RT in a stepped bezel with a cyan glow line, magenta edge spill strips, corner brackets, wall rails, conduit. Pivot = centre of the back (wall) face."),
    "Sign_Panel_M": dict(fn=sign_panel, kw={"w": 3.6, "h": 0.7}, cat="signage", zones=["plaza", "metro", "facility", "vault"], pivot="back-centre", notes="Wall sign 3.6 x 0.7."),
    "Sign_Panel_L": dict(fn=sign_panel, kw={"w": 6.0, "h": 1.2}, cat="signage", zones=["plaza", "metro", "facility"], pivot="back-centre", notes="Wall sign 6.0 x 1.2."),
    "Sign_Panel_Tall": dict(fn=sign_panel, kw={"w": 2.2, "h": 4.6}, cat="signage", zones=["plaza"], pivot="back-centre", notes="Vertical shop sign 2.2 x 4.6 (e.g. NOODLES 24H)."),
    "Sign_Hanging": dict(fn=sign_hanging, cat="signage", zones=["metro", "facility"], pivot="top-centre",
                         notes="Ceiling-hung double-sided LED sign 3.4 x 0.7 with two screen faces, cyan glow lines, magenta underside strip, junction box, rods with turnbuckles, power feed. Pivot = ceiling attach point."),
    "TarpShelter": dict(fn=tarp_shelter, cat="camp", zones=["plaza"], notes="Street-camp tarp shelter 4 x 3 m, back (+Y Unity -Z) side taller. Tarp is double-sided geometry. Festoon bulbs (emit_amber) on the front beam, cyan LED bar under the back beam, caged work lamp (emit_panel_warm) on a feed cable, salvaged neon glyph sign, sandbag weights."),
    "TarpShelter_Blue": dict(fn=tarp_shelter, kw={"mat": "tarp_blue", "seed": 9}, cat="camp", zones=["plaza"], notes="Blue tarp variant."),
    "TarpShelter_Large": dict(fn=tarp_shelter, kw={"W": 5.0, "D": 4.0, "seed": 4}, cat="camp", zones=["plaza"], notes="5 x 4 m shelter."),
    "MarketStall": dict(fn=market_stall, cat="camp", zones=["plaza"], notes="Night-market stall: counter (customer side +Z) with corrugated front, magenta LED edge, neon glyph plates, tarp canopy, festoon bulbs (emit_amber), hanging neon glyph sign, warm LED work bar (emit_panel_warm), goods, crates on the back shelf."),
    "MarketStall_Blue": dict(fn=market_stall, kw={"canopy": "tarp_blue", "seed": 8}, cat="camp", zones=["plaza"], notes="Blue canopy variant (cyan LED edge, cyan/yellow neon)."),
    "Terminal_Kiosk": dict(fn=terminal_kiosk, cat="props", zones=["plaza", "metro", "facility", "vault", "rooftops"],
                           notes="Free-standing neon terminal / save kiosk: glossy faceted body with carbon side panels, cyan LED edges + plinth under-glow (emit_strip_cyan), sloped console with keypad, card slot, palm pad, rain hood, faint holo frame. Screen slot 'screen' (UV 0..1), see 'screen' rect."),
    "Terminal_Kiosk_Off": dict(fn=terminal_kiosk, kw={"on": False}, cat="props", zones=["metro"], notes="Dead kiosk (glass_dark screen, all LEDs black, no holo frame)."),
    "Pipe_Straight_1m": dict(fn=pipe_straight, cat="structure", zones=["vault", "metro", "facility"], pivot="centre",
                             notes="1 m pipe along X (r 0.18), pivot at the centre of the axis. Scale X to length."),
    "Pipe_Elbow": dict(fn=pipe_elbow, cat="structure", zones=["vault", "metro"], pivot="corner",
                       notes="90 deg elbow (bend radius 0.45) joining a pipe along +Y at x=0 and a pipe along +X at y=0 (Blender); flanges at both ends."),
    "Pipe_Flange": dict(fn=pipe_flange, cat="structure", zones=["vault", "metro"], pivot="centre", notes="Bolted flange ring for r 0.18 pipes (axis X)."),
    "Pipe_Bracket": dict(fn=pipe_bracket, cat="structure", zones=["vault", "metro"], pivot="wall",
                         notes="Wall clamp; pivot on the wall plane, clamp ring 0.3 m in front (+Z) around an X-axis pipe."),
    "Railing_2m": dict(fn=railing, cat="structure", zones=["plaza", "metro", "facility", "vault"],
                       notes="2 m railing module along X (posts at -1.0 and 0.0; chain modules every 2 m, finish with Railing_Post). Top rail yellow."),
    "Railing_Post": dict(fn=railing_post, cat="structure", zones=["plaza", "metro", "facility", "vault"], notes="End post for railing runs."),
    "DoorFrame_2x3": dict(fn=door_frame, cat="structure", zones=["metro", "facility", "vault"],
                          notes="Steel door surround for a 2.0 x 3.0 opening, lit amber header strip (emit_amber), plate-panel jambs with bolt rows, hazard stripes, access keypad (emit_green), conduit + junction box, header vent and chevrons."),
    "DoorFrame_3x3_4": dict(fn=door_frame, kw={"w": 3.0, "h": 3.4}, cat="structure", zones=["metro", "facility"], notes="Surround for a 3.0 x 3.4 opening."),
    "Bollard": dict(fn=bollard, cat="street", zones=["plaza"], notes="LED bollard: bolted flange, glossy shaft, reflective hazard band, louvred cyan LED head (emit_strip_cyan)."),
    "TrafficCone": dict(fn=traffic_cone, cat="street", zones=["plaza", "metro"], notes="Traffic cone with reflective collar, yellow LED ring (emit_strip_yellow) and a battery clip with a red LED."),
}

ASSETS = {**ASSETS_A, **ASSETS_B}


# ============================================================================================== extras: planter, fire barrel
def _label(w, h, seed, n=3, plate="metal_painted_white", ink="black"):
    """Stencil label plate with invented glyphs (local XZ plane facing -Y, centred at the origin)."""
    box(w, 0.004, h, at=(0, -0.002, 0), mat=plate, bevel=0.0015)
    if detail():
        rng = random.Random(seed)
        g = min(h * 0.7, w / n * 0.8)
        for i in range(n):
            x = -w / 2 + (i + 0.5) * w / n
            for pts, closed in _glyph_strokes(rng):
                P = [(x - g / 2 + u * g, -0.0045, -g / 2 + v * g) for u, v in pts]
                tube(P, g * 0.045, 4, ink, closed=closed)


def planter(seed=7):
    """Tiled concrete planter: shadow-gap plinth, grimy tile cladding, steel coping with an under-lip LED line,
    gravel bed, dead tree in a tree guard wrapped with a half-dead string of fairy lights."""
    rnd = random.Random(seed)
    box(2.3, 2.3, 0.06, mat="concrete_dark", base=True)
    body = box(2.36, 2.36, 0.76, at=(0, 0, 0.06), mat="concrete_dark", base=True, bevel=0.02)
    inset(body, faces_where(body, lambda f: abs(f.normal.z) < 0.1), 0.07, -0.01, mat="tile_grimy")
    # coping rim
    for sx, sy, w, d in ((0, -1, 2.4, 0.15), (0, 1, 2.4, 0.15), (-1, 0, 0.15, 2.1), (1, 0, 0.15, 2.1)):
        box(w, d, 0.08, at=(sx * 1.125, sy * 1.125, 0.82), mat="metal_dark", base=True, bevel=0.01)
    for sx, sy, w, d in ((0, -1, 2.3, 0.012), (0, 1, 2.3, 0.012), (-1, 0, 0.012, 2.3), (1, 0, 0.012, 2.3)):
        box(w, d, 0.01, at=(sx * 1.182, sy * 1.182, 0.808), mat="emit_strip_cyan")
    box(2.1, 2.1, 0.04, at=(0, 0, 0.8), mat="gravel", base=True)
    pts = [(0, 0, 0.84), (0.03, 0.02, 1.8), (-0.02, 0.05, 2.7), (0.05, 0.0, 3.6)]
    tube(pts, 0.11, 8, "wood", radii=[0.14, 0.11, 0.08, 0.05])
    branches = []
    for i in range(6 if detail() else 3):
        z = rnd.uniform(2.2, 3.5)
        a = rnd.uniform(0, math.tau)
        L = rnd.uniform(0.6, 1.4)
        d = (math.cos(a) * L, math.sin(a) * L, rnd.uniform(0.3, 0.8) * L)
        mid = (d[0] * 0.5 + rnd.uniform(-0.1, 0.1), d[1] * 0.5 + rnd.uniform(-0.1, 0.1), d[2] * 0.6)
        tube([(0, 0, z), (mid[0], mid[1], z + mid[2]), (d[0], d[1], z + d[2])], 0.035, 5, "wood", radii=[0.045, 0.03, 0.012])
        branches.append(((0, 0, z), (mid[0], mid[1], z + mid[2]), (d[0], d[1], z + d[2])))
    if detail():
        r2 = random.Random(seed + 100)
        for p0, p1, p2 in branches:
            for t in (0.45, 0.75):
                base = Vector(p0).lerp(Vector(p1), t * 2) if t < 0.5 else Vector(p1).lerp(Vector(p2), (t - 0.5) * 2)
                dirv = (Vector(p2) - Vector(p0)).normalized()
                side = Vector((r2.uniform(-1, 1), r2.uniform(-1, 1), r2.uniform(0.2, 0.9))).normalized()
                tip = base + (dirv * 0.4 + side * 0.6).normalized() * r2.uniform(0.25, 0.45)
                tip.z = min(tip.z, 3.5)
                tip.x, tip.y = max(-1.1, min(1.1, tip.x)), max(-1.1, min(1.1, tip.y))
                tube([tuple(base), tuple(base.lerp(tip, 0.5) + Vector((0, 0, 0.03))), tuple(tip)], 0.012, 4, "wood", radii=[0.016, 0.01, 0.004])
        # tree guard: ring + four bars
        torus(0.32, 0.012, n_major=20, n_minor=4, mat="metal_dark").move(0, 0, 1.25)
        torus(0.32, 0.012, n_major=20, n_minor=4, mat="metal_dark").move(0, 0, 0.9)
        for k in range(6):
            a = math.radians(k * 60)
            cyl(0.01, 0.43, 6, at=(math.cos(a) * 0.32, math.sin(a) * 0.32, 0.84), mat="metal_dark")
        # fairy-light string spiralling up the trunk (some bulbs dead)
        pts = []
        for i in range(29):
            t = i / 28
            z = 1.0 + 1.6 * t
            r = 0.14 + (0.08 - 0.14) * (z - 0.84) / 1.86 + 0.012
            a = t * math.tau * 4.2
            pts.append((math.cos(a) * r + 0.02 * t, math.sin(a) * r + 0.03 * t, z))
        tube(pts, 0.003, 4, "rubber")
        for i in range(1, 28, 2):
            x, y, z = pts[i]
            box(0.02, 0.02, 0.026, at=(x, y, z - 0.015), mat="emit_amber" if (i * 7) % 5 else "black")
        # placard, drain slots, litter
        with K.placed(_xf(0.55, -1.181, 0.45)):
            _label(0.36, 0.1, seed + 3)
        for sx in (-1, 1):
            with K.placed(_xf(sx * 0.6, -1.18, 0.0)):
                _vent(0.3, 0.05, 3, (0, 0, 0.1))
        for i in range(3):
            c = cyl(0.033, 0.11, 8, mat=("metal_bare", "metal_painted_red", "plastic_dark")[i])
            c.rot(y=90).rot(z=40 * i).move(0.5 - i * 0.45, 0.6 - i * 0.35, 0.874)
    return {"colliders": [K.collider_box((0, 0, 0.45), (2.4, 2.4, 0.9))]}


def fire_barrel(seed=3):
    """Burn barrel: dented rusted chem drum with rolled hoops, punched vent holes glowing from inside with soot
    scorch above them, rebar grill across the mouth, a glowing ember bed with charred wood and burning trash,
    stencil hazard label."""
    rnd = random.Random(seed)
    prof = [(0.001, 0.0), (0.28, 0.0), (0.29, 0.03), (0.29, 0.28), (0.3, 0.3), (0.29, 0.32), (0.29, 0.58), (0.3, 0.6), (0.29, 0.62),
            (0.29, 0.86), (0.28, 0.88), (0.265, 0.88), (0.265, 0.6), (0.001, 0.6)]
    b = lathe(prof, 18 if detail() else 14, mat="metal_rusted")
    if detail():
        # dents
        b.displace(lambda c: (c.x * (1 - 0.035 * max(0.0, math.cos(math.atan2(c.y, c.x) - 1.1)) ** 6 * math.sin(min(math.pi, c.z / 0.88 * math.pi))),
                              c.y * (1 - 0.035 * max(0.0, math.cos(math.atan2(c.y, c.x) - 1.1)) ** 6 * math.sin(min(math.pi, c.z / 0.88 * math.pi))), c.z))
    b.set_mat("black", where=lambda f: f.calc_center_median().xy.length < 0.27 and f.calc_center_median().z > 0.59)
    for i in range(6):
        a = math.radians(i * 60 + 15)
        h = box(0.06, 0.04, 0.09, mat="emit_amber")
        h.move(0, -0.287, 0.15 + (i % 2) * 0.12).rot(z=math.degrees(a))
        if detail():
            sc = box(0.07, 0.004, 0.16, mat="black")
            sc.move(0, -0.2905, 0.15 + (i % 2) * 0.12 + 0.12).rot(z=math.degrees(a))
    if detail():
        # inner glow ring just under the rim (fire light on the inner wall)
        lathe([(0.262, 0.7), (0.262, 0.86)], 18, mat="emit_amber", close_bottom=False, close_top=False)
        for i in range(5):
            w = cyl(0.03, 0.4, 6, axis="X", center=False, mat="wood")
            w.move(-0.2, 0, 0).rot(y=rnd.uniform(-35, 35), z=rnd.uniform(0, 180)).move(0, 0, 0.82)
        coals = rock((0.42, 0.42, 0.14), seed + 9, cuts=10, mat="emit_amber", rough=0.08, bevel=0.0)
        coals.move(0, 0, 0.74)
        # charred chunks + burning trash
        for i in range(4):
            r_ = rock((0.1, 0.08, 0.06), seed + 20 + i, cuts=7, mat="black", rough=0.1, bevel=0.0)
            a = i * 1.6
            r_.move(math.cos(a) * 0.12, math.sin(a) * 0.12, 0.8)
        # rebar grill across the mouth
        for k in (-0.12, 0.0, 0.12):
            L = 2 * math.sqrt(max(0.0, 0.285 ** 2 - k ** 2))
            cyl(0.008, L, 6, at=(-L / 2, k, 0.886), axis="X", mat="metal_rusted")
        # stencil hazard label
        with K.placed(_xf(0, 0, 0, rz=200) @ Matrix.Translation((0, -0.292, 0.44))):
            _label(0.16, 0.07, seed + 5, n=2, plate="metal_painted_yellow")
    return {"colliders": [K.collider_box((0, 0, 0.44), (0.6, 0.6, 0.88))], "light": {"position": K.to_unity_vec((0, 0, 1.15)), "color": "#ff8a3a"}}


ASSETS.update({
    "Planter_DeadTree": dict(fn=planter, cat="street", zones=["plaza"], notes="2.4 m planter: grimy-tile cladding, steel coping with a cyan under-lip LED line, gravel bed, dead tree in a tree guard with a half-dead string of fairy lights (emit_amber)."),
    "FireBarrel": dict(fn=fire_barrel, cat="camp", zones=["plaza"], notes="Survivor fire barrel: rusted drum, glowing vent holes and coal bed (emit_amber), charred wood. Add flames/smoke as particles at 'light'."),
})
