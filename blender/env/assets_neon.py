"""Cyberpunk neon & signage kit (cat "neon" -> Models/Neon/).

Neon signs are built like real neon: 15 mm glass tubes (r 7.5 mm) bent with rounded bends, held 5-7 cm off a
dark backer on support posts, each tube unit ending in two back-bends that dive into electrode boots; jumps
between strokes run behind the lit strokes and are painted out ('black' slot). Backers sit on a raceway box /
spacers against the wall, fed by a wall transformer through a flexible conduit.

Pivots:
  * "wall-back": origin = the wall plane (back face of the mount), horizontally centred, at the LOWEST point of
    the asset. The sign projects toward Unity +Z (Blender -Y). Place the origin on the wall surface at the height
    given in each asset's notes (bottom edge height).
  * "base-centre": floor standing.
Metadata: 'light' (dominant point-light anchor), 'lights' (one per colour / lamp; position, color, range,
intensity, slot), 'glow' (dominant colour hex), 'screen'/'screens' (centre, size, normal, material).
All glyphs are invented (radical grammar of matdefs_hd.glyph); no real text.
"""
import math
import random

from mathutils import Matrix, Vector

import envkit as K
from envkit import box, cyl, tube, torus, beam, extrude, lathe, inset, faces_where, detail

TUBE_R = 0.0075
HEX = {"magenta": "#ff2bd6", "pink": "#ff4f9a", "cyan": "#00e5ff", "blue": "#3d7bff", "yellow": "#ffe14d", "violet": "#9b5cff"}
SLOT_HEX = {"emit_red": "#ff3a2e", "emit_amber": "#ffa21f", "emit_green": "#52ff99", "emit_white": "#e8f2ff",
            "emit_cyan": "#5fd8ff", "emit_violet": "#a77bff", "emit_panel_warm": "#ffd2a0", "emit_panel_white": "#e8f2ff",
            "emit_panel_cyan": "#5fd8ff", "emit_panel_violet": "#a77bff", "emit_panel_magenta": HEX["magenta"],
            "emit_panel_yellow": HEX["yellow"], "screen_ad_a": HEX["magenta"], "screen_ad_b": HEX["yellow"],
            "screen_ad_c": HEX["violet"], "screen": "#4fb8ff", "holo_cyan": HEX["cyan"], "holo_magenta": HEX["magenta"]}
for _k, _v in HEX.items():
    SLOT_HEX[f"emit_strip_{_k}"] = _v
    SLOT_HEX[f"emit_neon_{_k}"] = _v
DARK = "paint_glossy_dark"


# ============================================================================================== metadata
class Meta:
    """Collects colliders / light anchors / screens in asset space; frame() transforms apply to anchors."""

    def __init__(self):
        self.cols, self.lights, self.screens, self.extra = [], [], [], {}
        self.M = Matrix.Identity(4)

    def col(self, c, s):
        self.cols.append((Vector(c), tuple(s)))

    def light(self, p, hexc, rng=4.0, inten=1.5, slot=None):
        self.lights.append((self.M @ Vector(p), hexc, rng, inten, slot))

    def screen(self, c, size, n, mat):
        self.screens.append((self.M @ Vector(c), size, (self.M.to_3x3() @ Vector(n)).normalized(), mat))

    def done(self, dz=0.0, glow=None, single_screen=True):
        d = Vector((0, 0, dz))
        r3 = lambda v: [round(float(x), 3) + 0.0 for x in v]
        out = {"colliders": [K.collider_box(tuple(c + d), s) for c, s in self.cols]}
        ls = []
        for p, h, rg, it, sl in self.lights:
            e = {"position": r3(K.to_unity_vec(p + d)), "color": h, "range": round(rg, 2), "intensity": round(it, 2)}
            if sl:
                e["slot"] = sl
            ls.append(e)
        if ls:
            out["light"] = ls[0]
            out["lights"] = ls
            out["glow"] = glow or ls[0]["color"]
        if self.screens:
            sc = [{"center": r3(K.to_unity_vec(c + d)), "size": [round(s[0], 3), round(s[1], 3)], "normal": r3(K.to_unity_vec(n)),
                   "material": m} for c, s, n, m in self.screens]
            out["screens"] = sc
            if single_screen:
                out["screen"] = sc[0]
        out.update(self.extra)
        return out


class frame:
    """K.placed() that also transforms Meta anchors recorded inside the block."""

    def __init__(self, meta, m=None, **kw):
        self.meta = meta
        self.pl = K.placed(m, **kw)
        self.m = self.pl.m

    def __enter__(self):
        self.prev = self.meta.M
        self.meta.M = self.prev @ self.m
        self.pl.__enter__()
        return self

    def __exit__(self, *exc):
        self.meta.M = self.prev
        return self.pl.__exit__(*exc)


def side_frame(meta, side, x_face, y_centre, z=0.0):
    """Sign space (x right, z up, front -Y, backer front at y=0) onto a face whose outward normal is side*X."""
    rz = 90 if side > 0 else -90
    return frame(meta, x=side * x_face, y=y_centre, z=z, rz=rz)


# ============================================================================================== 2D helpers
def _rrect(w, h, r, cx=0.0, cz=0.0, n=4):
    """CCW rounded rectangle polygon (x, z)."""
    pts = []
    r = min(r, w / 2 - 1e-3, h / 2 - 1e-3)
    n = K.seg(n, 2) if r > 0 else 0
    for (ox, oz, a0) in ((w / 2 - r, -h / 2 + r, -90), (w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180)):
        if n == 0:
            pts.append((cx + ox + math.copysign(r, ox), cz + oz + math.copysign(r, oz)))
            continue
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + ox + r * math.cos(a), cz + oz + r * math.sin(a)))
    return pts


def _circle(R, cx=0.0, cz=0.0, n=40, a0=-90.0):
    n = K.seg(n, 12)
    return [(cx + R * math.cos(math.radians(a0) + math.tau * i / n), cz + R * math.sin(math.radians(a0) + math.tau * i / n)) for i in range(n)]


def _offset(poly, d):
    """Miter offset of a CCW polygon (outward for d > 0)."""
    n = len(poly)
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(poly[i - 1]), Vector(poly[i]), Vector(poly[(i + 1) % n])
        e1, e2 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n1, n2 = Vector((e1.y, -e1.x)), Vector((e2.y, -e2.x))
        k = d / max(0.2, 1.0 + n1.dot(n2))
        q = p1 + (n1 + n2) * k
        out.append((q.x, q.y))
    return out


def _bbox2(pts):
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(zs), max(xs), max(zs)


# ============================================================================================== glyphs (invented)
def S(pts, closed=False, layer=None, color=None):
    """A neon / vinyl stroke: polyline in unit (u, v) or sign coords."""
    return {"pts": [tuple(p) for p in pts], "closed": closed, "layer": layer, "color": color}


def glyph_strokes(rng, max_strokes=8):
    """Invented glyph from radicals (roof bar, stems, enclosure or crossing strokes, mid bar, ticks, dot): same
    grammar as matdefs_hd.glyph(), 5-8 strokes, unit square."""
    st = []
    top = rng.uniform(0.8, 0.9)
    st.append(S([(rng.uniform(0.08, 0.2), top), (rng.uniform(0.8, 0.92), top)]))
    xs = sorted(rng.sample([0.22, 0.38, 0.5, 0.62, 0.78], 2))
    for x in xs:
        st.append(S([(x, top), (x, rng.uniform(0.05, 0.3))]))
    if rng.random() < 0.6:
        x0, x1 = rng.uniform(0.15, 0.3), rng.uniform(0.7, 0.85)
        y0, y1 = rng.uniform(0.12, 0.28), rng.uniform(0.48, 0.62)
        st.append(S([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], closed=True))
        mid = None
    else:
        st.append(S([(rng.uniform(0.1, 0.3), rng.uniform(0.1, 0.3)), (rng.uniform(0.6, 0.9), rng.uniform(0.45, 0.7))]))
        st.append(S([(rng.uniform(0.6, 0.9), rng.uniform(0.05, 0.25)), (rng.uniform(0.15, 0.4), rng.uniform(0.5, 0.7))]))
        mid = rng.uniform(0.62, 0.7)
    m = mid if mid is not None else rng.uniform(0.66, 0.72)
    st.append(S([(rng.uniform(0.05, 0.2), m), (rng.uniform(0.8, 0.95), m)]))
    for _ in range(rng.randint(1, 2)):
        x, y = rng.choice([(rng.uniform(0.04, 0.14), rng.uniform(0.3, 0.6)), (rng.uniform(0.86, 0.96), rng.uniform(0.3, 0.6))])
        st.append(S([(x, y + 0.07), (x + rng.uniform(-0.04, 0.04), y - 0.08)]))
    if rng.random() < 0.5:
        st.append(S(_circle(0.045, rng.choice([0.3, 0.7]), 0.95, n=12), closed=True))
    return st[:max_strokes]


# hand-designed hero glyphs (unit square)
GLYPH_A = [S([(0.1, 0.76), (0.1, 0.88), (0.9, 0.88), (0.9, 0.76)]),                  # hooked roof
           S([(0.44, 0.99), (0.52, 0.93)]),                                           # top tick
           S([(0.16, 0.4), (0.58, 0.4), (0.58, 0.7), (0.16, 0.7)], closed=True),      # enclosure (left)
           S([(0.78, 0.8), (0.78, 0.08), (0.66, 0.14)], layer=1),                     # hooked stem (right)
           S([(0.64, 0.5), (0.95, 0.5)]),                                             # bar across the stem
           S([(0.26, 0.32), (0.12, 0.06)]),                                           # splayed legs
           S([(0.48, 0.32), (0.58, 0.08)]),
           S(_circle(0.04, 0.37, 0.55, n=12), closed=True)]                           # dot in the box
GLYPH_B = [S([(0.2, 0.96), (0.2, 0.04)], layer=1),                                    # left stem
           S([(0.05, 0.74), (0.2, 0.66)]),                                            # radical ticks
           S([(0.05, 0.36), (0.2, 0.46)]),
           S([(0.36, 0.86), (0.95, 0.86)]),                                           # roof
           S([(0.46, 0.44), (0.86, 0.44), (0.86, 0.72), (0.46, 0.72)], closed=True),  # box under the roof
           S([(0.66, 0.44), (0.66, 0.06), (0.55, 0.12)], layer=1),                    # hooked stem below
           S([(0.38, 0.3), (0.94, 0.16)], layer=2),                                   # sweep
           S(_circle(0.045, 0.9, 0.97, n=12), closed=True)]                           # dot
GLYPH_C = [S([(0.12, 0.92), (0.88, 0.92)]),                                           # top bar
           S([(0.5, 0.92), (0.5, 0.58)], layer=1),                                    # short stem
           S([(0.33, 0.83), (0.2, 0.6)], layer=2),                                    # splayed ticks
           S([(0.67, 0.83), (0.84, 0.62)], layer=2),
           S([(0.04, 0.5), (0.96, 0.5)]),                                             # wide mid bar
           S([(0.22, 0.06), (0.78, 0.06), (0.78, 0.4), (0.22, 0.4)], closed=True),    # enclosure
           S([(0.5, 0.4), (0.5, 0.06)], layer=1),                                     # split
           S([(0.06, 0.36), (0.13, 0.2)])]                                            # tick


def _xform_strokes(strokes, cx, cz, size, sy=None):
    sy = size if sy is None else sy
    out = []
    for s in strokes:
        t = dict(s)
        t["pts"] = [(cx + (u - 0.5) * size, cz + (v - 0.5) * sy) for u, v in s["pts"]]
        out.append(t)
    return out


def _chains(strokes, max_per=4):
    """Greedy nearest-neighbour ordering of strokes into tube units (open strokes may be reversed)."""
    left = list(strokes)
    chains = []
    while left:
        cur = [left.pop(0)]
        while left and len(cur) < max_per:
            end = Vector(cur[-1]["pts"][-1] if not cur[-1]["closed"] else cur[-1]["pts"][0])
            best, bi, rev = 1e9, 0, False
            for i, s in enumerate(left):
                for r in ((False, True) if not s["closed"] else (False,)):
                    p = Vector(s["pts"][-1] if r else s["pts"][0])
                    d = (p - end).length
                    if d < best:
                        best, bi, rev = d, i, r
            s = left.pop(bi)
            if rev:
                s = dict(s)
                s["pts"] = list(reversed(s["pts"]))
            cur.append(s)
        chains.append(cur)
    return chains


# ============================================================================================== neon tubes
def _round(pts, flags, r_lit, r_bend, closed=False, n=3):
    """Fillet the corners of a 3D polyline (quadratic Bezier bends). flags = per-segment lit flags (True = lit).
    Corner radius r_lit between lit segments, r_bend at back-bends / jumpers. Returns (points, flags)."""
    P, F = [Vector(pts[0])], []
    for i in range(1, len(pts)):  # drop duplicate points
        q = Vector(pts[i])
        if (q - P[-1]).length < 1e-5:
            if F:
                F[-1] = F[-1] or flags[i - 1]
            continue
        P.append(q)
        F.append(flags[i - 1])
    if closed:
        F.append(flags[-1])
    m = len(P)
    reps = []
    for i in range(m):
        if not closed and (i == 0 or i == m - 1):
            reps.append([P[i]])
            continue
        A, B, C = P[i - 1], P[i], P[(i + 1) % m]
        d1, d2 = A - B, C - B
        l1, l2 = d1.length, d2.length
        d1n, d2n = d1 / l1, d2 / l2
        ang = math.acos(max(-1.0, min(1.0, d1n.dot(d2n))))
        if ang > math.radians(141):            # gentle turns (circle facets) stay sharp
            reps.append([B])
            continue
        fa, fb = F[i - 1], F[i % len(F)]
        r = r_lit if (fa and fb) else r_bend
        t = min(r / math.tan(ang / 2), l1 * 0.48, l2 * 0.48)
        p1, p2 = B + d1n * t, B + d2n * t
        turn = math.pi - ang
        if K.LOD > 0 or not (fa and fb):
            k = 1                                   # back-bends / painted-out jumper bends: cheap chamfers
        elif turn > math.radians(50):
            k = n
        else:
            k = 2
        reps.append([(1 - s) ** 2 * p1 + 2 * (1 - s) * s * B + s ** 2 * p2 for s in (j / k for j in range(k + 1))])
    out, of = [], []
    for i in range(m):
        rep = reps[i]
        kk = len(rep) - 1
        for j, q in enumerate(rep):
            if out:
                if j == 0:
                    of.append(F[i - 1])
                else:
                    of.append(F[i - 1] if j <= kk / 2 else F[i % len(F)])
            out.append(q)
    if closed:
        of.append(F[-1])
    return out, of


def _open_loop(pts, gap=0.04, at=None):
    """Closed polygon -> open path starting/ending at the middle of its lowest edge with a small gap."""
    n = len(pts)
    if at is None:
        at = min(range(n), key=lambda i: (pts[i][1] + pts[(i + 1) % n][1]) / 2 - 1e-3 * abs(pts[i][0] - pts[(i + 1) % n][0]))
    a, b = Vector(pts[at]), Vector(pts[(at + 1) % n])
    d = (b - a)
    L = d.length
    d = d / max(L, 1e-6)
    g = min(gap / 2, L * 0.3)
    mid = (a + b) / 2
    path = [tuple(mid + d * g)]
    for k in range(1, n + 1):
        path.append(pts[(at + k) % n])
    path.append(tuple(mid - d * g))
    return path


class Neon:
    """Neon tube runs in sign space (x right, z up, front -Y) on a backer whose front face is the plane y = yb."""

    def __init__(self, meta, yb=0.0, standoff=0.07):
        self.meta, self.yb = meta, yb
        self.layers = [yb - standoff, yb - standoff + 0.018, yb - standoff + 0.036]
        self.yj = yb - 0.016
        self.lit = {}
        self.boots = []

    def _layer(self, s):
        if s.get("layer") is not None:
            return s["layer"]
        if s["closed"]:
            return 0
        a, b = s["pts"][0], s["pts"][-1]
        dx, dz = abs(b[0] - a[0]), abs(b[1] - a[1])
        return 1 if dz > 2 * dx else (0 if dx > 2 * dz else 2)

    def run(self, strokes, color, fillet=0.03, spacing=0.32, gap=0.045, tube_r=TUBE_R, bend_n=3):
        """One tube unit: strokes chained with painted-out jumpers behind, back-bends into two electrode boots."""
        yb, yj = self.yb, self.yj
        ye = yb - 0.022
        path, flags = [], []
        for si, s in enumerate(strokes):
            y = self.layers[self._layer(s)]
            pts2 = _open_loop(s["pts"], gap) if s["closed"] else s["pts"]
            P = [Vector((x, y, z)) for x, z in pts2]
            if si == 0:
                path.append(Vector((P[0].x, ye, P[0].z)))
                flags.append(False)
            else:
                prev = path[-1]
                path += [Vector((prev.x, yj, prev.z)), Vector((P[0].x, yj, P[0].z))]
                flags += [False, False, False]
            path += P
            flags += [True] * (len(P) - 1)
        last = path[-1]
        path.append(Vector((last.x, ye, last.z)))
        flags.append(False)
        pts, fl = _round(path, flags, fillet, 0.014, n=bend_n)
        n = 6
        p = tube(pts, tube_r, n, mat=f"emit_neon_{color}", name="neon", caps=False)
        ne = K.seg(n, 4)
        for i, f in enumerate(p.bm.faces):
            si = i // ne
            if si >= len(fl) or not fl[si]:
                f[p.mats] = p.slot("black")
        # electrode boots
        for q in (pts[0], pts[-1]):
            cyl(0.0125, 0.03, 6, at=(q.x, yb - 0.03, q.z), axis="Y", mat="rubber", name="boot")
            if detail():
                cyl(0.016, 0.006, 6, at=(q.x, yb - 0.006, q.z), axis="Y", mat="metal_bare")
        # supports along lit runs
        acc = spacing * 0.5
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            L = (b - a).length
            if not fl[i]:
                acc = spacing * 0.6
                continue
            self.lit.setdefault(color, []).extend([self.meta.M @ a, self.meta.M @ b])
            t = 0.0
            while detail() and L > 0.06 and acc + (L - t) >= spacing:
                t += spacing - acc
                acc = 0.0
                q = a + (b - a) * (t / L)
                tube([(q.x, q.y, q.z), (q.x, yb, q.z)], 0.0035, 4, mat="metal_bare", name="support", caps=False)
            acc += L - t
        return p

    def runs(self, strokes, color, max_per=4, **kw):
        for ch in _chains(strokes, max_per):
            self.run(ch, color, **kw)

    def lights(self, ahead=0.45, rng=None, inten=None, order=None):
        """Point-light anchors (one per colour) in front of the lit tube centroid. Returns dominant colour hex."""
        cols = sorted(self.lit, key=lambda c: -len(self.lit[c])) if order is None else order
        Minv = self.meta.M.inverted()
        for c in cols:
            pts = self.lit[c]
            cen = sum(pts, Vector()) / len(pts)
            ext = max((p - cen).length for p in pts)
            loc = Minv @ cen
            self.meta.light((loc.x, self.yb - ahead, loc.z), HEX[c], rng=rng or round(2.5 + ext * 3.0, 1),
                            inten=inten or round(1.2 + ext * 0.8, 2), slot=f"emit_neon_{c}")
        return HEX[cols[0]]


# ============================================================================================== mounting hardware
def _bolt(x, y, z, axis="Y", r=0.009):
    if detail():
        cyl(r, 0.008, 6, at=(x, y - 0.008, z) if axis == "Y" else (x, y, z), axis=axis, mat="metal_bare", start=0)


def _raceway(x0, x1, zc, h=0.1, d=0.07, mat=DARK):
    """Horizontal raceway box against the wall (y 0..-d) with end caps and wall bolts."""
    box(x1 - x0, d, h, at=((x0 + x1) / 2, -d / 2, zc), mat=mat, bevel=0.006)
    for x in (x0, x1):
        box(0.012, d + 0.004, h + 0.008, at=(x, -d / 2, zc), mat="metal_dark", bevel=0.002)
    if detail():
        for x in (x0 + 0.06, x1 - 0.06):
            box(0.05, 0.008, h + 0.06, at=(x, -0.004, zc), mat="metal_dark", bevel=0.002)
            for z in (zc - h / 2 - 0.018, zc + h / 2 + 0.018):
                cyl(0.008, 0.01, 6, at=(x, -0.018, z), axis="Y", mat="metal_bare", start=0)


def _vraceway(xc, z0, z1, w=0.1, d=0.07, mat=DARK):
    box(w, d, z1 - z0, at=(xc, -d / 2, (z0 + z1) / 2), mat=mat, bevel=0.006)
    for z in (z0, z1):
        box(w + 0.008, d + 0.004, 0.012, at=(xc, -d / 2, z), mat="metal_dark", bevel=0.002)
    if detail():
        for z in (z0 + 0.06, z1 - 0.06):
            box(w + 0.06, 0.008, 0.05, at=(xc, -0.004, z), mat="metal_dark", bevel=0.002)
            for x in (xc - w / 2 - 0.018, xc + w / 2 + 0.018):
                cyl(0.008, 0.01, 6, at=(x, -0.018, z), axis="Y", mat="metal_bare", start=0)


def _spacer(x, z, y_to):
    """Round wall standoff from the wall (y=0) to the backer back (y_to < 0) with a bolt head."""
    cyl(0.018, -y_to, 8, at=(x, y_to, z), axis="Y", mat="metal_bare")
    if detail():
        cyl(0.03, 0.006, 8, at=(x, -0.006, z), axis="Y", mat="metal_dark")


def _transformer(x, ztop, to, side=1):
    """Wall neon transformer, box top centre at (x, 0, ztop); flexible conduit from its top gland to `to`."""
    w, h, d = 0.24, 0.15, 0.085
    zc = ztop - h / 2
    b = box(w, d, h, at=(x, -d / 2, zc), mat="metal_painted", bevel=0.01, bseg=2)
    box(w + 0.05, 0.006, h - 0.04, at=(x, -0.003, zc), mat="metal_dark")                    # mounting plate
    if detail():
        for i in range(4):
            box(w - 0.07, 0.01, 0.008, at=(x - 0.02, -d - 0.004, zc + 0.045 - i * 0.026), mat="metal_painted")
        box(0.05, 0.003, 0.07, at=(x + 0.085, -d - 0.001, zc), mat="metal_painted_yellow")  # HV warning label
        box(0.036, 0.004, 0.012, at=(x + 0.085, -d - 0.003, zc + 0.012), mat="black")
        for sx in (-1, 1):
            cyl(0.007, 0.01, 6, at=(x + sx * (w / 2 + 0.012), -0.01, zc), axis="Y", mat="metal_bare", start=0)
        cyl(0.004, 0.003, 6, at=(x - 0.09, -d - 0.003, zc + 0.05), axis="Y", mat="emit_green")   # status pip
    gx = x - side * 0.06
    cyl(0.014, 0.025, 8, at=(gx, -d / 2, ztop), mat="metal_dark")                              # cable gland
    tx, ty, tz = to
    ym = -d / 2
    tube([(gx, ym, ztop + 0.02), (gx, ym, ztop + 0.07), (gx + (tx - gx) * 0.3, ym, ztop + 0.12),
          (tx, (ym + ty) / 2, tz - 0.06), (tx, ty, tz)], 0.009, 6, mat="rubber", name="conduit")
    return b


def _bolts_on(pts, y):
    for x, z in pts:
        _bolt(x, y, z)


def _plate(poly, y_front, t=0.02, mat=DARK, bevel=0.005):
    """Backer plate from a CCW (x, z) polygon, front face at y_front, thickness t (toward +Y)."""
    p = extrude(poly, t, plane="XZ", mat=mat, name="backer")
    p.move(0, y_front + t / 2, 0)
    if bevel:
        p.bevel(bevel, 1, angle=30)
    return p


def _perf_panel(w, h, cx, cz, y_front, frame_w=0.05, t=0.03):
    """Perforated backer: box-section frame with a grating infill."""
    yc = y_front + t / 2
    for sx in (-1, 1):
        box(frame_w, t, h, at=(cx + sx * (w - frame_w) / 2, yc, cz), mat=DARK, bevel=0.005)
    for sz in (-1, 1):
        box(w - 2 * frame_w + 0.002, t, frame_w, at=(cx, yc, cz + sz * (h - frame_w) / 2), mat=DARK, bevel=0.005)
    box(w - 2 * frame_w + 0.01, 0.004, h - 2 * frame_w + 0.01, at=(cx, yc + 0.004, cz), mat="grating")
    if detail():
        for sx in (-1, 1):
            for sz in (-1, 1):
                _bolt(cx + sx * (w - frame_w) / 2, y_front, cz + sz * (h - frame_w) / 2)
        box(w - 2 * frame_w, 0.02, 0.03, at=(cx, yc + 0.004, cz), mat=DARK)   # mid stiffener


def _finish_wall(M, glow=None):
    dz = K.ground()
    return M.done(dz, glow)


# ============================================================================================== neon signs
YB = -0.09   # backer front plane for wall signs (raceway 0..-0.07, backer -0.07..-0.09)


def neon_arrow_right():
    M = Meta()
    N = Neon(M, YB)
    outer = [(-0.85, -0.13), (0.22, -0.13), (0.22, -0.34), (0.85, 0.0), (0.22, 0.34), (0.22, 0.13), (-0.85, 0.13)]
    inner = _offset(outer, -0.062)
    bp = _offset(outer, 0.075)
    _plate(bp, YB)
    if detail():
        tube([(x, YB - 0.003, z) for x, z in _offset(outer, 0.068)], 0.005, 6, mat="chrome_scratched", closed=True)
    N.run([S(outer, closed=True)], "cyan", fillet=0.035)
    N.run([S(inner, closed=True)], "magenta", fillet=0.03)
    _raceway(-0.7, 0.35, 0.0, h=0.12)
    _transformer(-0.55, -0.32, (-0.5, -0.035, -0.06))
    if detail():
        _bolts_on([(-0.88, 0.0), (0.12, 0.3), (0.12, -0.3), (0.78, 0.0)], YB)
    M.col((0.0, -0.06, 0.0), (1.9, 0.12, 0.88))
    return _finish_wall(M, N.lights(order=["cyan", "magenta"]))


def neon_arrow_down():
    M = Meta()
    N = Neon(M, YB)
    w, h = 0.72, 1.9
    _perf_panel(w, h, 0, 0, YB, frame_w=0.055)
    chev = []
    for i in range(4):
        zc = 0.55 - i * 0.36
        chev.append(S([(-0.24, zc + 0.12), (0.0, zc - 0.1), (0.24, zc + 0.12)]))
    N.runs(chev[:2], "yellow", fillet=0.03)
    N.runs(chev[2:], "yellow", fillet=0.03)
    border = _rrect(w - 0.1, h - 0.1, 0.09)
    N.run([S(border, closed=True)], "pink", fillet=0.05)
    _vraceway(0, -0.75, 0.75, w=0.12, d=0.06)
    _transformer(0.0, -h / 2 - 0.1, (0.0, -0.035, -0.75))
    M.col((0, -0.06, 0), (w, 0.12, h))
    return _finish_wall(M, N.lights(order=["yellow", "pink"]))


def neon_circle(R=0.5, color="magenta"):
    M = Meta()
    N = Neon(M, YB)
    ring = lathe([(R - 0.07, 0.0), (R + 0.07, 0.0), (R + 0.07, 0.02), (R - 0.07, 0.02), (R - 0.07, 0.0)], 48, mat=DARK,
                 close_bottom=False, close_top=False)
    ring.rot(x=90).move(0, YB + 0.02, 0)
    if detail():
        for a in range(0, 360, 45):
            _bolt(math.cos(math.radians(a)) * (R + 0.045), YB, math.sin(math.radians(a)) * (R + 0.045))
    N.run([S(_circle(R, n=48), closed=True)], color, fillet=0.03)
    _vraceway(0, -R - 0.02, R + 0.02, w=0.11)
    _transformer(0.0, -R - 0.12, (0.0, -0.035, -R - 0.02))
    M.col((0, -0.06, 0), (2 * R + 0.14, 0.12, 2 * R + 0.14))
    return _finish_wall(M, N.lights())


def neon_ring_double():
    M = Meta()
    N = Neon(M, YB)
    Ro = 0.72
    d = cyl(Ro, 0.02, 48, at=(0, YB, 0), axis="Y", mat=DARK, bevel=0.004)
    if detail():
        t = torus(Ro - 0.004, 0.008, n_major=40, n_minor=4, mat="chrome_scratched")
        t.rot(x=90).move(0, YB - 0.002, 0)
        a = lathe([(0.5, 0.0), (0.56, 0.0), (0.56, 0.006), (0.5, 0.006), (0.5, 0.0)], 48, mat="carbon_panel", close_bottom=False, close_top=False)
        a.rot(x=90).move(0, YB, 0)
        for k in range(12):
            ang = math.tau * k / 12
            _bolt(math.cos(ang) * (Ro - 0.035), YB, math.sin(ang) * (Ro - 0.035), r=0.007)
    N.run([S(_circle(0.62, n=48), closed=True)], "cyan", fillet=0.03)
    N.run([S(_circle(0.43, n=40, a0=-70), closed=True)], "pink", fillet=0.03)
    for x in (-0.45, 0.45):
        _spacer(x, 0.42, -0.07)
        _spacer(x, -0.42, -0.07)
    _raceway(-0.3, 0.3, 0.0, h=0.12)
    _transformer(0.0, -Ro - 0.06, (0.0, -0.035, -0.06))
    M.col((0, -0.06, 0), (2 * Ro, 0.12, 2 * Ro))
    return _finish_wall(M, N.lights(order=["cyan", "pink"]))


def neon_frame_rect(W=2.4, H=1.4):
    M = Meta()
    N = Neon(M, YB)
    fw, t = 0.16, 0.025
    yc = YB + t / 2
    for sx in (-1, 1):
        box(fw, t, H, at=(sx * (W - fw) / 2, yc, 0), mat=DARK, bevel=0.005)
    for sz in (-1, 1):
        box(W - 2 * fw + 0.002, t, fw, at=(0, yc, sz * (H - fw) / 2), mat=DARK, bevel=0.005)
    if detail():  # return lips of the channel
        for sx in (-1, 1):
            box(0.012, 0.03, H, at=(sx * (W / 2 - 0.006), YB - 0.012, 0), mat="metal_dark")
            box(0.012, 0.03, H - 2 * fw + 0.012, at=(sx * (W / 2 - fw + 0.006), YB - 0.012, 0), mat="metal_dark")
        for sz in (-1, 1):
            box(W, 0.03, 0.012, at=(0, YB - 0.012, sz * (H / 2 - 0.006)), mat="metal_dark")
            box(W - 2 * fw + 0.012, 0.03, 0.012, at=(0, YB - 0.012, sz * (H / 2 - fw + 0.006)), mat="metal_dark")
    N.run([S(_rrect(W - 0.1, H - 0.1, 0.1), closed=True)], "blue", fillet=0.06, gap=0.05)
    oz = _rrect(W - 0.22, H - 0.22, 0.05)
    N.run([S(oz, closed=True)], "violet", fillet=0.04, gap=0.05)
    for sx in (-1, 1):
        for sz in (-1, 1):
            _spacer(sx * (W / 2 - fw / 2), sz * (H / 2 - fw / 2), YB + t)
        _spacer(sx * (W / 2 - fw / 2), 0.0, YB + t)
    for sz in (-1, 1):
        _spacer(0.0, sz * (H / 2 - fw / 2), YB + t)
    _transformer(W / 2 - 0.35, -H / 2 - 0.06, (W / 2 - 0.3, -0.04, -H / 2 + 0.05), side=-1)
    M.col((0, -0.06, 0), (W, 0.12, H))
    return _finish_wall(M, N.lights(order=["blue", "violet"]))


def neon_glyph(glyph="A", color="magenta", accent="cyan"):
    M = Meta()
    N = Neon(M, YB)
    size, pw = 0.86, 1.12
    _perf_panel(pw, pw, 0, 0, YB, frame_w=0.06)
    base = {"A": GLYPH_A, "B": GLYPH_B, "C": GLYPH_C}[glyph]
    st = _xform_strokes(base, 0, 0, size)
    if glyph == "A":   # accent: top tick, the dot and the two legs in the second colour
        acc = [st[1], st[7], st[5], st[6]]
        main = [s for i, s in enumerate(st) if i not in (1, 5, 6, 7)]
    elif glyph == "B":  # accent: the dot + the sweep
        acc = [st[7], st[6]]
        main = st[:6]
    else:               # accent: a border loop around the glyph
        acc = [S(_rrect(pw - 0.13, pw - 0.13, 0.06), closed=True)]
        main = st
    N.runs(main, color, max_per=4, fillet=0.03)
    N.runs(acc, accent, max_per=3, fillet=0.03)
    for z in (-0.3, 0.3):
        _raceway(-0.4, 0.4, z, h=0.09, d=0.06)
    _transformer(0.3, -pw / 2 - 0.05, (0.3, -0.03, -0.3 - 0.045))
    M.col((0, -0.06, 0), (pw, 0.12, pw))
    return _finish_wall(M, N.lights(order=[color, accent]))


def neon_glyph_column(seed=3, color="cyan", border="pink", n=4):
    M = Meta()
    N = Neon(M, YB)
    cell, gapz = 0.46, 0.1
    w = 0.66
    h = n * cell + (n - 1) * gapz + 0.3
    b = box(w, 0.02, h, at=(0, YB + 0.01, 0), mat=DARK, bevel=0.006)
    inset(b, faces_where(b, lambda f: f.normal.y < -0.9), 0.035, -0.006, mat="carbon_panel")
    rng = random.Random(seed)
    for i in range(n):
        zc = h / 2 - 0.15 - cell / 2 - i * (cell + gapz)
        N.runs(_xform_strokes(glyph_strokes(rng, 6), 0, zc, cell), color, max_per=6, fillet=0.022, spacing=0.42, bend_n=2)
    N.run([S(_rrect(w - 0.06, h - 0.06, 0.06), closed=True)], border, fillet=0.05)
    _vraceway(0, -h / 2 + 0.2, h / 2 - 0.2, w=0.12)
    _transformer(0.0, -h / 2 - 0.08, (0.0, -0.035, -h / 2 + 0.2))
    if detail():
        _bolts_on([(sx * (w / 2 - 0.018), sz * (h / 2 - 0.018)) for sx in (-1, 1) for sz in (-1, 1)], YB)
    M.col((0, -0.06, 0), (w, 0.12, h))
    return _finish_wall(M, N.lights(order=[color, border]))


def _bowl_strokes(cx=0.0, cz=0.0, s=1.0):
    """Abstract noodle-bowl icon: bowl + foot (main), noodle wave (accent), chopsticks, three steam squiggles."""
    def T(pts):
        return [(cx + x * s, cz + z * s) for x, z in pts]
    bowl = [(-0.5, 0.0), (0.5, 0.0)] + [(0.48 * math.cos(math.pi * i / 10.0), -0.38 * math.sin(math.pi * i / 10.0)) for i in range(1, 10)]
    bowl = S(T(bowl), closed=True)
    foot = S(T([(-0.17, -0.47), (0.17, -0.47)]))
    noodle = S(T([(-0.32 + 0.64 * i / 12, -0.13 + 0.035 * math.sin(i * 1.6)) for i in range(13)]), layer=1)
    chop = [S(T([(0.02, 0.07), (0.56, 0.64)]), layer=2), S(T([(0.15, 0.07), (0.66, 0.58)]), layer=1)]
    steam = []
    for k, x0 in enumerate((-0.36, -0.19, -0.02)):
        pts = [(x0 + 0.045 * math.sin(i * 0.95 + k), 0.12 + 0.5 * i / 10 + (0.04 if k == 1 else 0.0)) for i in range(11)]
        steam.append(S(T(pts), layer=0))
    return bowl, foot, noodle, chop, steam


def neon_bowl():
    M = Meta()
    N = Neon(M, YB)
    bowl, foot, noodle, chop, steam = _bowl_strokes(0.0, -0.05)
    pw, ph = 1.38, 1.38
    b = _plate(_rrect(pw, ph, 0.12, cx=0.06, cz=0.02), YB)
    inset(b, faces_where(b, lambda f: f.normal.y < -0.9), 0.04, -0.006, mat="metal_dark")
    if detail():
        t = tube([(x, YB - 0.003, z) for x, z in _rrect(pw - 0.02, ph - 0.02, 0.11, cx=0.06, cz=0.02)], 0.006, 6, mat="chrome_scratched", closed=True)
    N.run([bowl, foot], "magenta", fillet=0.04)
    N.run([noodle], "pink", fillet=0.02)
    N.run(chop, "yellow", fillet=0.03)
    N.run(steam, "cyan", fillet=0.02, spacing=0.24)
    _raceway(-0.45, 0.55, -0.2, h=0.12)
    _raceway(-0.45, 0.55, 0.35, h=0.1)
    _transformer(-0.35, -0.73, (-0.3, -0.035, -0.26))
    M.col((0.06, -0.06, 0.02), (pw, 0.12, ph))
    return _finish_wall(M, N.lights(order=["magenta", "cyan", "yellow", "pink"]))


ASSETS = {}


def _reg(name, fn, kw=None, cat="neon", zones=("plaza",), pivot="base-centre", notes="", **extra):
    ASSETS[name] = dict(fn=fn, kw=kw or {}, cat=cat, zones=list(zones), pivot=pivot, notes=notes, **extra)


_WALL = ("Pivot 'wall-back': wall plane, centred, at the bottom of the transformer box; sign projects ~0.17 m toward +Z. ")
_reg("Neon_Arrow_Right", neon_arrow_right, pivot="wall-back",
     notes="Neon arrow pointing to the viewer's right (Unity -X), 1.9 x 0.9 m: cyan outer + magenta inner tube on a contour-cut "
           "backer, raceway, wall transformer. " + _WALL + "Mount the pivot ~2.6-3.2 m up (arrow centre ~3.3 m).")
_reg("Neon_Arrow_Down", neon_arrow_down, pivot="wall-back",
     notes="Vertical neon pointer 0.72 x 2.1 m: four acid-yellow chevrons pointing down inside a pink border on a perforated "
           "backer. " + _WALL + "Mount pivot ~2.4 m up above a door / stairs.")
_reg("Neon_Circle", neon_circle, pivot="wall-back",
     notes="1.14 m magenta neon ring on an annular backer with a vertical raceway spine. " + _WALL + "Pivot ~2.5-4 m up.")
_reg("Neon_Ring_Double", neon_ring_double, pivot="wall-back",
     notes="Double ring (cyan 1.24 m outer, pink 0.86 m inner) on a 1.44 m disc backer with chrome rim. " + _WALL + "Pivot ~2.5-4 m up.")
_reg("Neon_Frame_Rect", neon_frame_rect, pivot="wall-back",
     notes="2.4 x 1.4 m neon border (blue outer, violet inner) on an open channel frame; frame a shop window, poster or "
           "a Sign_Panel. " + _WALL + "Pivot at the window head height minus ~1.5 m.")
_reg("Neon_Glyph_A", neon_glyph, kw={"glyph": "A", "color": "magenta", "accent": "cyan"}, pivot="wall-back",
     notes="Single invented glyph, magenta with cyan accents, on a 1.12 m perforated square backer. " + _WALL + "Pivot ~2.6-5 m up.")
_reg("Neon_Glyph_B", neon_glyph, kw={"glyph": "B", "color": "cyan", "accent": "pink"}, pivot="wall-back",
     notes="Single invented glyph, cyan with pink accents, 1.12 m perforated backer. " + _WALL)
_reg("Neon_Glyph_C", neon_glyph, kw={"glyph": "C", "color": "yellow", "accent": "violet"}, pivot="wall-back",
     notes="Single invented glyph, acid yellow inside a violet border loop, 1.12 m perforated backer. " + _WALL)
_reg("Neon_Glyph_Column", neon_glyph_column, pivot="wall-back",
     notes="Vertical stack of 4 invented cyan glyphs in a pink border, 0.66 x 2.5 m panel. " + _WALL + "Pivot ~2.5-3 m up; stack "
           "several at different heights up a facade.")
_reg("Neon_Bowl", neon_bowl, pivot="wall-back",
     notes="Noodle-bar icon 1.38 m: magenta bowl, pink noodles, yellow chopsticks, cyan steam. " + _WALL + "Pivot ~2.6-3.5 m up "
           "over a food stall / shop front.")


# ============================================================================================== flat glyphs
def flat_glyph(strokes, cx, cz, size, y, mat="black", w=0.075, t=0.004):
    """Glyph as flat strips on the plane y (sign space, front -Y): cut vinyl on lightboxes or hologram strokes."""
    sw = w * size
    for s in strokes:
        pts = [(cx + (u - 0.5) * size, cz + (v - 0.5) * size) for u, v in s["pts"]]
        x0, z0, x1, z1 = _bbox2(pts)
        if s["closed"] and max(x1 - x0, z1 - z0) < 0.16 * size:
            cyl(max(x1 - x0, z1 - z0) / 2 + sw / 2, t, 10, at=((x0 + x1) / 2, y - t, (z0 + z1) / 2), axis="Y", mat=mat)
            continue
        if s["closed"]:
            pts = pts + [pts[0]]
        for a, b in zip(pts, pts[1:]):
            a, b = Vector((a[0], y - t / 2, a[1])), Vector((b[0], y - t / 2, b[1]))
            d = (b - a).normalized() * (sw / 2)
            beam(a - d, b + d, sw, t, mat=mat, up=(0, -1, 0))


def glyph_set(seed, n, max_strokes=8):
    rng = random.Random(seed)
    return [glyph_strokes(rng, max_strokes) for _ in range(n)]


# ============================================================================================== blade signs
def _blade_mount(T, P, H, G, z0, M, strip="emit_strip_violet", body_mat=DARK):
    """Wall rail + three bracket arms with gussets + top tie rod + lightbox body. Returns body Part."""
    yc = -(G + P / 2)
    rail_h = H + z0 + 0.25
    box(0.3, 0.03, rail_h, at=(0, -0.015, 0), mat="metal_dark", base=True, bevel=0.006)
    if detail():
        for z in (0.08, rail_h - 0.08, rail_h * 0.5):
            for sx in (-1, 1):
                cyl(0.012, 0.012, 6, at=(sx * 0.1, -0.042, z), axis="Y", mat="metal_bare", start=0)
    for zb in (z0 + 0.3, z0 + H * 0.5, z0 + H - 0.3):
        box(0.1, G - 0.03, 0.09, at=(0, -0.03 - (G - 0.03) / 2, zb), mat="metal_dark", bevel=0.008)
        g = extrude([(-0.03, zb - 0.045), (-0.03, zb - 0.26), (-G, zb - 0.045)], 0.014, plane="YZ", mat="metal_dark")
        if detail():
            box(0.16, 0.012, 0.16, at=(0, -G + 0.006, zb), mat="metal_dark", bevel=0.003)
    # top tie rod with turnbuckle
    tr_a, tr_b = (0, -0.035, z0 + H + 0.2), (0, -(G + P - 0.08), z0 + H + 0.045)
    tube([tr_a, tr_b], 0.011, 6, mat="metal_bare")
    if detail():
        m = [(a + b) / 2 for a, b in zip(tr_a, tr_b)]
        cyl(0.018, 0.12, 6, at=(0, m[1] + 0.03, m[2] + 0.009), axis="Y", mat="metal_dark")
        box(0.06, 0.05, 0.03, at=(0, tr_b[1], tr_b[2] - 0.005), mat="metal_dark")
    # body
    b = box(T, P, H, at=(0, yc, z0 + H / 2), mat=body_mat, bevel=0.012, bseg=2)
    for zz, s in ((z0 + H + 0.03, 1), (z0 - 0.03, -1)):
        c = box(T + 0.05, P + 0.05, 0.06, at=(0, yc, zz), mat="metal_dark", bevel=0.01, bseg=2)
    box(0.05, 0.02, H - 0.08, at=(0, -(G + P) - 0.01, z0 + H / 2), mat=strip)
    if detail():
        for sx in (-1, 1):
            box(0.016, 0.016, H, at=(sx * (T / 2 + 0.002), -(G + P) + 0.006, z0 + H / 2), mat="chrome_scratched")
        # conduit from the rail into the lowest bracket
        tube([(0.11, -0.04, z0 + 0.02), (0.11, -0.06, z0 + 0.2), (0.06, -0.1, z0 + 0.28), (0.06, -G + 0.02, z0 + 0.25)], 0.012, 6, mat="rubber")
    M.col((0, -0.015, rail_h / 2), (0.3, 0.03, rail_h))
    M.col((0, yc, z0 + H / 2), (T + 0.05, P + 0.05, H + 0.12))
    return b


def sign_blade_a():
    """Lightbox blade: white diffuser faces with cut-vinyl glyph column, magenta neon outline."""
    M = Meta()
    T, P, H, G, z0 = 0.3, 0.6, 3.6, 0.16, 0.25
    b = _blade_mount(T, P, H, G, z0, M, strip="emit_strip_magenta")
    inset(b, faces_where(b, lambda f: abs(f.normal.x) > 0.9), 0.045, -0.012, mat="emit_panel_white")
    glyphs = glyph_set(21, 4)
    nlit = None
    for side in (-1, 1):
        with side_frame(M, side, T / 2, -(G + P / 2), z0):
            N = Neon(M, 0.0, standoff=0.06)
            for i, g in enumerate(glyphs):
                flat_glyph(g, 0, H - 0.5 - i * 0.84, 0.44, 0.012, w=0.085)
            N.run([S(_rrect(P - 0.03, H - 0.03, 0.04, cz=H / 2), closed=True)], "magenta", fillet=0.035, gap=0.05)
            if detail():
                box(P - 0.09, 0.006, 0.012, at=(0, 0.006, 0.42), mat="black")
                box(P - 0.09, 0.006, 0.012, at=(0, 0.006, H - 0.12), mat="black")
            nlit = N
            M.light((0, -0.7, H * 0.55), SLOT_HEX["emit_panel_white"], rng=6.0, inten=1.6, slot="emit_panel_white")
            N.lights(ahead=0.6, rng=5.0, inten=1.4)
    M.light((0, -(G + P) - 0.4, z0 + H / 2), HEX["magenta"], rng=4.0, inten=1.0, slot="emit_strip_magenta")
    return M.done(glow=HEX["magenta"])


def sign_blade_b():
    """Dark blade with a neon glyph column, yellow ring emblem and pink border; violet LED front edge."""
    M = Meta()
    T, P, H, G, z0 = 0.3, 0.7, 4.2, 0.16, 0.25
    b = _blade_mount(T, P, H, G, z0, M, strip="emit_strip_violet")
    inset(b, faces_where(b, lambda f: abs(f.normal.x) > 0.9), 0.045, -0.01, mat="carbon_panel")
    glyphs = glyph_set(57, 4, 5)
    for side in (-1, 1):
        with side_frame(M, side, T / 2, -(G + P / 2), z0):
            N = Neon(M, 0.01, standoff=0.065)
            ring_z = H - 0.42
            N.run([S(_circle(0.24, 0, ring_z, n=24), closed=True), S(_circle(0.07, 0, ring_z, n=8), closed=True)], "yellow", fillet=0.03,
                  spacing=0.5)
            for i, g in enumerate(glyphs):
                N.runs(_xform_strokes(g, 0, H - 1.05 - i * 0.72, 0.5), "cyan", max_per=6, fillet=0.022, spacing=0.6, bend_n=2)
            N.run([S(_rrect(P - 0.04, H - 0.04, 0.05, cz=H / 2), closed=True)], "pink", fillet=0.04, gap=0.05)
            if detail():
                box(P - 0.12, 0.004, 0.01, at=(0, 0.006, H - 0.78), mat="chrome_scratched")
            N.lights(ahead=0.6, order=["cyan", "yellow", "pink"])
    M.light((0, -(G + P) - 0.4, z0 + H / 2), HEX["violet"], rng=4.0, inten=1.0, slot="emit_strip_violet")
    return M.done(glow=HEX["cyan"])


def sign_blade_c():
    """Media blade: stacked LED ad panel (screen_ad_a), animated 'screen' panel and a magenta lightbox with glyphs."""
    M = Meta()
    T, P, H, G, z0 = 0.36, 0.9, 4.5, 0.18, 0.25
    b = _blade_mount(T, P, H, G, z0, M, strip="emit_strip_blue")
    panels = [("emit_panel_magenta", 0.12, 1.12), ("screen", 1.3, 3.1), ("screen_ad_a", 3.28, 4.38)]
    fw = P - 0.1
    for side in (-1, 1):
        with side_frame(M, side, T / 2, -(G + P / 2), z0):
            for mat, za, zb in panels:
                pn = box(fw, 0.02, zb - za, at=(0, -0.01, (za + zb) / 2), mat=DARK, bevel=0.004)
                pn.set_mat(mat, where=lambda f: f.normal.y < -0.9)
                if mat != "emit_panel_magenta":
                    M.screen((0, -0.021, (za + zb) / 2), (fw, zb - za), (0, -1, 0), mat)
            for za in (1.12, 1.3, 3.1, 3.28):
                box(P - 0.02, 0.03, 0.04 if za in (1.12, 3.28) else 0.03, at=(0, -0.015, za + (0.0 if za < 3 else 0)), mat="chrome_scratched", bevel=0.004)
            for i, g in enumerate(glyph_set(88, 2)):
                flat_glyph(g, 0, 0.36 + i * 0.5, 0.4, -0.02, w=0.09)
            N = Neon(M, -0.02, standoff=0.06)
            N.run([S(_rrect(P - 0.03, H - 0.03, 0.05, cz=H / 2), closed=True)], "pink", fillet=0.04, gap=0.05)
            M.light((0, -0.8, 3.83), HEX["magenta"], rng=6.0, inten=1.8, slot="screen_ad_a")
            M.light((0, -0.8, 2.2), SLOT_HEX["screen"], rng=6.0, inten=1.4, slot="screen")
            M.light((0, -0.6, 0.62), HEX["magenta"], rng=4.0, inten=1.2, slot="emit_panel_magenta")
    if detail():  # crown: blue neon chevron on top of the cap
        with frame(M, x=0, y=-(G + P / 2), z=z0 + H + 0.06):
            box(0.12, P - 0.1, 0.05, at=(0, 0, 0.025), mat="metal_dark")
    return M.done(glow=HEX["magenta"], single_screen=False)


_BLADE = ("Pivot 'wall-back' = bottom centre of the wall rail's back face; blade projects toward +Z (out of the wall) and both "
          "lit faces look along the street (Unity +/-X). ")
_reg("Sign_Blade_A", sign_blade_a, pivot="wall-back",
     notes="Vertical lightbox blade, overall 0.44 x 4.1 x 0.79 m (0.3 m thick, 0.6 m deep body on a 0.16 m wall gap): white diffuser faces with a cut-vinyl "
           "column of 4 invented glyphs, magenta neon outline, magenta LED front edge. " + _BLADE + "Mount the pivot 3.0-4.5 m up.")
_reg("Sign_Blade_B", sign_blade_b, pivot="wall-back",
     notes="Dark carbon blade, overall 0.43 x 4.7 x 0.89 m: cyan neon glyph column, yellow ring emblem, pink border on both faces, violet LED "
           "front edge. " + _BLADE + "Mount the pivot 3.0-5 m up.")
_reg("Sign_Blade_C", sign_blade_c, pivot="wall-back",
     notes="Media blade, overall 0.54 x 5.0 x 1.1 m: per face a screen_ad_a LED panel (top), an animatable 'screen' panel (middle, see "
           "'screens') and a magenta glyph lightbox (bottom); pink neon outline, blue LED front edge. " + _BLADE + "Mount 3-5 m up.")


# ============================================================================================== LED billboards
def _led_cabinet(W, H, D, y_front, z0, face="screen_ad_a", bezel=0.12, module=0.5, M=None, faces=(-1,), hood=True,
                 crown="emit_strip_cyan"):
    """LED video-wall cabinet spanning x +-W/2, z z0..z0+H, front face at y_front, depth D toward +Y (or both faces
    lit when faces=(-1, 1)). Module seams every `module` m. Records screens in M."""
    yc = y_front + D / 2
    b = box(W, D, H, at=(0, yc, z0 + H / 2), mat=DARK, bevel=0.02, bseg=2)
    sw, sh = W - 2 * bezel, H - 2 * bezel
    mats = face if isinstance(face, (list, tuple)) else [face] * len(faces)
    for side, fm in zip(faces, mats):
        inset(b, faces_where(b, lambda f, s=side: f.normal.y * s > 0.9), bezel, -0.025, mat=fm)
        yf = (y_front + 0.025) if side < 0 else (y_front + D - 0.025)
        if M is not None:
            M.screen((0, yf + side * 0.001, z0 + H / 2), (sw, sh), (0, side, 0), fm)
        if K.LOD < 2:  # LED module seams
            nx, nz = int(round(sw / module)), int(round(sh / module))
            for i in range(1, nx):
                box(0.008, 0.004, sh, at=(-sw / 2 + i * sw / nx, yf + side * 0.002, z0 + H / 2), mat="black")
            for j in range(1, nz):
                box(sw, 0.004, 0.008, at=(0, yf + side * 0.002, z0 + bezel + j * sh / nz), mat="black")
        if detail():  # corner caps + bezel bolts + status LEDs
            ys = y_front - 0.004 if side < 0 else y_front + D + 0.004
            for sx in (-1, 1):
                for sz in (0, 1):
                    box(0.16, 0.02, 0.16, at=(sx * (W / 2 - 0.07), ys, z0 + 0.07 + sz * (H - 0.14)), mat="chrome_scratched", bevel=0.005)
            for i in range(3):
                cyl(0.008, 0.006, 6, at=(W / 2 - 0.35 - i * 0.04, ys - side * 0.004, z0 + 0.05), axis="Y", mat="emit_green" if i else "emit_amber")
    if hood:  # rain hood with LED lip
        hd = box(W + 0.12, 0.34, 0.035, at=(0, y_front + 0.1, z0 + H + 0.06), mat="metal_dark", bevel=0.008)
        hd.rot_about((0, y_front + 0.27, z0 + H + 0.06), x=-8)
        box(W, 0.022, 0.03, at=(0, y_front - 0.055, z0 + H + 0.02), mat=crown)
    else:
        box(W - 0.1, 0.03, 0.03, at=(0, y_front + 0.01, z0 + H + 0.015), mat=crown)
    if detail():  # side vent grilles + service handles
        for sx in (-1, 1):
            for k in range(int(H // 0.9)):
                box(0.006, D * 0.6, 0.5, at=(sx * (W / 2 + 0.001), yc, z0 + 0.35 + k * 0.9 + 0.25), mat="grating")
    return b


def billboard_led_wall(face="screen_ad_a"):
    M = Meta()
    W, H, D = 6.24, 3.24, 0.3
    yf = -0.16 - D
    for zz in (0.55, H - 0.55):  # wall rails + Z brackets
        box(W - 0.6, 0.06, 0.14, at=(0, -0.03, zz), mat="metal_dark", bevel=0.006)
        for x in (-2.4, -0.8, 0.8, 2.4):
            box(0.12, 0.1, 0.18, at=(x, -0.11, zz), mat="metal_dark", bevel=0.006)
            if detail():
                for sz in (-1, 1):
                    cyl(0.012, 0.012, 6, at=(x, -0.072, zz + sz * 0.05), axis="Y", mat="metal_bare", start=0)
    _led_cabinet(W, H, D, yf, 0.0, face=face, M=M, crown="emit_strip_cyan")
    for sx in (-1, 1):   # vertical LED accents on the bezel edges + chunky corner brackets
        box(0.025, 0.02, H - 0.5, at=(sx * (W / 2 - 0.035), yf - 0.008, H / 2), mat="emit_strip_cyan")
        for zz in (0.25, H - 0.25):
            box(0.08, D + 0.1, 0.22, at=(sx * (W / 2 + 0.03), yf + D / 2 + 0.05, zz), mat="metal_dark", bevel=0.01)
    box(W - 0.8, 0.12, 0.06, at=(0, -0.08, -0.02), mat="metal_dark", bevel=0.006)                    # cable tray
    # power distribution box under the cabinet on the wall + conduit into the cabinet base
    box(0.5, 0.18, 0.4, at=(2.2, -0.09, -0.3), mat="metal_painted", bevel=0.012, bseg=2)
    if detail():
        box(0.12, 0.004, 0.08, at=(2.33, -0.182, -0.22), mat="metal_painted_yellow")
        for i in range(5):
            box(0.3, 0.012, 0.012, at=(2.12, -0.185, -0.4 + i * 0.03), mat="metal_painted")
        cyl(0.006, 0.004, 6, at=(2.0, -0.184, -0.18), axis="Y", mat="emit_green")
    tube([(2.05, -0.1, -0.1), (2.05, -0.1, -0.05), (2.05, -0.2, 0.0), (2.05, -0.25, 0.03)], 0.025, 8, mat="rubber")
    tube([(2.35, -0.1, -0.1), (2.35, -0.1, -0.03), (2.35, -0.22, 0.02), (2.35, -0.3, 0.03)], 0.018, 8, mat="rubber")
    M.col((0, yf + D / 2, H / 2), (W, D + 0.06, H + 0.1))
    M.col((0, -0.08, H / 2), (W - 0.6, 0.16, H - 0.9))
    hx = SLOT_HEX[face]
    M.light((0, yf - 1.5, H / 2), hx, rng=10.0, inten=3.0, slot=face)
    M.light((0, yf - 0.3, H + 0.02), HEX["cyan"], rng=3.0, inten=0.8, slot="emit_strip_cyan")
    return _finish_wall(M, hx)


def _ladder(x, y, z0, z1, side_y=1, cage=True, w=0.45):
    for sx in (-1, 1):
        box(0.05, 0.05, z1 - z0 + 1.0, at=(x + sx * w / 2, y, z0), mat="metal_painted_yellow", base=True, bevel=0.004)
    n = int((z1 - z0) / 0.3)
    for i in range(1, n + 1):
        cyl(0.014, w, 6, at=(x - w / 2, y, z0 + i * 0.3), axis="X", mat="metal_bare")
    if cage and detail():
        for zz in [z0 + 2.2 + k * 0.9 for k in range(int((z1 - z0 - 1.8) / 0.9) + 1)] + [z1 + 0.9]:
            t = torus(0.36, 0.012, arc=180, n_major=8, n_minor=4, mat="metal_painted_yellow", start=0)
            if side_y < 0:
                t.mirror("y")
            t.move(x, y, zz)
        for sx in (-0.3, 0.0, 0.3):
            yy = y + side_y * (0.36 if sx == 0 else 0.2)
            box(0.03, 0.01, z1 - z0 - 1.3, at=(x + sx, yy, z0 + 2.2), mat="metal_painted_yellow", base=True)


def _railing(x0, x1, y, z, h=1.05, step=1.5, axis="X"):
    L = x1 - x0
    n = max(1, int(round(L / step)))
    for i in range(n + 1):
        t = x0 + L * i / n
        p = (t, y, z) if axis == "X" else (y, t, z)
        box(0.05, 0.05, h, at=p, mat="metal_painted_yellow", base=True, bevel=0.004)
    if axis == "X":
        cyl(0.025, L, 8, at=(x0, y, z + h), axis="X", mat="metal_painted_yellow")
        cyl(0.016, L, 6, at=(x0, y, z + h * 0.5), axis="X", mat="metal_painted_yellow")
        box(L, 0.012, 0.12, at=(x0 + L / 2, y, z), mat="metal_dark", base=True)
    else:
        cyl(0.025, L, 8, at=(y, x0, z + h), axis="Y", mat="metal_painted_yellow")
        cyl(0.016, L, 6, at=(y, x0, z + h * 0.5), axis="Y", mat="metal_painted_yellow")
        box(0.012, L, 0.12, at=(y, x0 + L / 2, z), mat="metal_dark", base=True)


def _spotlight(at, aim_pitch, M=None):
    """Billboard floodlight: yoke + housing + lens (emit_white). The lens looks along -Y rotated by aim_pitch deg about X."""
    x, y, z = at
    parts0 = K.part_count()
    hs = cyl(0.13, 0.32, 12, at=(0, -0.16, 0), axis="Y", mat=DARK, bevel=0.01)
    lens = cyl(0.11, 0.01, 12, at=(0, -0.17, 0), axis="Y", mat="emit_white")
    if detail():
        for k in range(4):
            box(0.27, 0.012, 0.012, at=(0, 0.06 + k * 0.03, 0.135), mat="metal_dark")
        box(0.24, 0.05, 0.012, at=(0, -0.19, 0.12), mat=DARK)  # glare visor
    for p in K.parts_since(parts0):
        p.rot(x=aim_pitch).move(x, y, z)
    for sx in (-1, 1):  # yoke
        box(0.015, 0.06, 0.2, at=(x + sx * 0.145, y, z - 0.08), mat="metal_dark")
    box(0.3, 0.06, 0.02, at=(x, y, z - 0.18), mat="metal_dark")
    if M is not None:
        d = Matrix.Rotation(math.radians(aim_pitch), 3, "X") @ Vector((0, -1, 0))
        M.light((x + d.x * 0.25, y + d.y * 0.25, z + d.z * 0.25), "#dfe8ff", rng=12.0, inten=2.5, slot="emit_white")
        M.extra.setdefault("spots", []).append({"position": [round(v, 3) for v in K.to_unity_vec((x, y, z))],
                                                "direction": [round(v, 3) for v in K.to_unity_vec(tuple(d))]})


def billboard_rooftop_rig():
    M = Meta()
    W, H, D = 12.3, 6.3, 0.5
    zs = 3.0
    yf = -D / 2
    cab = _led_cabinet(W, H, D, yf, zs, face="screen_ad_b", module=1.0, M=M, hood=False, crown="emit_strip_magenta")
    # back of the cabinet: horizontal stiffeners
    for zz in (zs + 0.6, zs + H / 2, zs + H - 0.6):
        box(W - 0.4, 0.12, 0.2, at=(0, D / 2 + 0.06, zz), mat="metal_dark", bevel=0.01)
    cols = (-5.0, 0.0, 5.0)
    yc, yr = 0.55, 4.0
    for x in cols:
        box(0.9, 0.9, 0.3, at=(x, yc, 0), mat="concrete_dark", base=True, bevel=0.03)
        box(0.9, 0.9, 0.3, at=(x, yr, 0), mat="concrete_dark", base=True, bevel=0.03)
        box(0.6, 0.6, 0.025, at=(x, yc, 0.3), mat="metal_dark", base=True)
        box(0.5, 0.5, 0.025, at=(x, yr, 0.3), mat="metal_dark", base=True)
        box(0.3, 0.3, zs + H - 0.3 - 0.33, at=(x, yc, 0.325), mat="metal_painted", base=True, bevel=0.01)
        beam((x, yr, 0.33), (x, yc + 0.1, zs + H * 0.62), 0.22, 0.22, mat="metal_painted", up=(1, 0, 0))
        beam((x, yr - 0.1, 0.5), (x, yc + 0.15, zs - 0.1), 0.12, 0.12, mat="metal_painted", up=(1, 0, 0))
        beam((x, yc + 0.15, 1.6), (x, yr - 0.4, 1.6), 0.12, 0.12, mat="metal_painted", up=(0, 0, 1))
        if detail():
            for sx in (-1, 1):
                for sy in (-1, 1):
                    cyl(0.018, 0.06, 6, at=(x + sx * 0.22, yc + sy * 0.22, 0.325), mat="metal_bare")
        # catwalk cantilever under the screen
        beam((x, yc, zs - 0.45), (x, -1.4, zs - 0.45), 0.16, 0.2, mat="metal_painted", up=(0, 0, 1))
        beam((x, yc, zs - 1.6), (x, -1.3, zs - 0.55), 0.1, 0.1, mat="metal_painted", up=(1, 0, 0))
    # bracing between columns (X braces, lower bay) + girders
    for xa, xb in ((-5.0, 0.0), (0.0, 5.0)):
        beam((xa, yc, 0.5), (xb, yc, zs - 0.6), 0.1, 0.1, mat="metal_painted", up=(0, 1, 0))
        beam((xa, yc, zs - 0.6), (xb, yc, 0.5), 0.1, 0.1, mat="metal_painted", up=(0, 1, 0))
    for zz in (zs - 0.6, zs + H * 0.62):
        box(10.6, 0.16, 0.22, at=(0, yc + 0.23, zz), mat="metal_painted", bevel=0.008)
    # catwalk deck, toe boards, railing
    zc = zs - 0.35
    box(W + 0.2, 1.05, 0.05, at=(0, -0.85, zc - 0.05), mat="grating", base=True)
    for sy in (-0.33, -1.37):
        box(W + 0.2, 0.06, 0.1, at=(0, sy, zc - 0.1), mat="metal_painted", base=True)
    _railing(-W / 2 - 0.1, W / 2 + 0.1, -1.36, zc)
    for sx in (-1, 1):
        _railing(-1.36, -0.4, sx * (W / 2 + 0.1), zc, axis="Y", step=0.9)
    # floodlights on arms off the catwalk rail, aimed up at the screen
    for x in (-4.5, -1.5, 1.5, 4.5):
        beam((x, -1.36, zc + 1.0), (x, -1.95, zc + 1.25), 0.06, 0.06, mat="metal_painted", up=(1, 0, 0))
        _spotlight((x, -2.0, zc + 1.42), -130, M=M)
    # ladder roof -> catwalk at the +X end, with cage
    _ladder(W / 2 + 0.45, -0.9, 0.0, zc, side_y=-1)
    box(0.6, 1.05, 0.05, at=(W / 2 + 0.38, -0.85, zc - 0.05), mat="grating", base=True)
    # conduits + junction box + crown beacons
    box(0.6, 0.25, 0.8, at=(-2.5, yc - 0.3, 0.6), mat="metal_painted", base=True, bevel=0.015, bseg=2)
    if detail():
        box(0.15, 0.005, 0.1, at=(-2.35, yc - 0.428, 1.2), mat="metal_painted_yellow")
        tube([(-2.5, yc - 0.3, 1.4), (-2.5, yc - 0.3, 2.3), (-2.5, -0.05, zs - 0.2), (-2.5, 0.0, zs + 0.05)], 0.04, 8, mat="rubber")
        tube([(-2.3, yc - 0.3, 1.4), (-2.3, yc - 0.1, 2.0), (-1.0, yc, 2.2), (2.0, yc, 2.2), (4.6, yc, 2.4)], 0.03, 6, mat="rubber")
    for sx in (-1, 1):
        cyl(0.04, 0.3, 6, at=(sx * (W / 2 - 0.15), 0, zs + H), mat="metal_dark")
        cyl(0.07, 0.12, 10, at=(sx * (W / 2 - 0.15), 0, zs + H + 0.3), mat="emit_red")
        M.light((sx * (W / 2 - 0.15), 0, zs + H + 0.36), SLOT_HEX["emit_red"], rng=3.0, inten=0.8, slot="emit_red")
    M.lights.insert(0, ((Vector((0, yf - 3.0, zs + H / 2))), SLOT_HEX["screen_ad_b"], 18.0, 4.0, "screen_ad_b"))
    for x in cols:
        M.col((x, yc, 0.15), (0.9, 0.9, 0.3))
        M.col((x, yr, 0.15), (0.9, 0.9, 0.3))
        M.col((x, yc, (zs + H) / 2), (0.3, 0.3, zs + H))
    M.col((0, 0, zs + H / 2), (W, D, H))
    M.col((0, -0.85, zc - 0.025), (W + 0.2, 1.05, 0.05))
    M.col((0, -1.36, zc + 0.55), (W + 0.2, 0.06, 1.1))
    M.extra["walkable"] = {"catwalk_height": round(zc, 3)}
    return M.done(glow=SLOT_HEX["screen_ad_b"], single_screen=True)


def billboard_pole_double():
    M = Meta()
    W, H, D = 5.4, 2.9, 0.8
    zt = 7.6
    box(1.5, 1.5, 0.45, mat="concrete_dark", base=True, bevel=0.04, bseg=2)
    box(1.0, 1.0, 0.04, at=(0, 0, 0.45), mat="metal_dark", base=True, bevel=0.006)
    if detail():
        for sx in (-1, 1):
            for sy in (-1, 1):
                cyl(0.025, 0.08, 6, at=(sx * 0.38, sy * 0.38, 0.49), mat="metal_bare")
                cyl(0.04, 0.03, 6, at=(sx * 0.38, sy * 0.38, 0.49), mat="metal_dark", start=0)
    lathe([(0.48, 0.49), (0.48, 0.6), (0.42, 0.75), (0.41, 3.5), (0.44, 3.55), (0.44, 3.68), (0.39, 3.73), (0.35, zt), (0.001, zt)],
          24, mat=DARK)
    box(0.3, 0.06, 0.5, at=(0, -0.42, 1.2), mat="metal_dark", bevel=0.01)          # service door
    box(0.02, 0.03, 2.4, at=(0, -0.43, 1.6), mat="emit_strip_cyan", base=True)       # pole LED stripe
    # yoke + catwalk
    box(W * 0.8, 0.5, 0.35, at=(0, 0, zt - 0.1), mat="metal_painted", bevel=0.015)
    for sx in (-1, 1):
        beam((sx * 0.3, 0, zt - 1.6), (sx * W * 0.38, 0, zt - 0.2), 0.16, 0.16, mat="metal_painted", up=(0, 1, 0))
    zc = zt + 0.08
    box(W + 0.4, 2.0, 0.05, at=(0, 0, zc - 0.05), mat="grating", base=True)
    for sy in (-1, 1):
        box(W + 0.4, 0.06, 0.12, at=(0, sy * 0.97, zc - 0.12), mat="metal_painted", base=True)
        _railing(-W / 2 - 0.2, W / 2 + 0.2, sy * 0.97, zc, step=1.4)
    _ladder(0.0, 0.55, 0.45, zt - 0.05, side_y=1, w=0.42)
    zs = zc + 0.25
    _led_cabinet(W, H, D, -D / 2, zs, face=["screen_ad_c", "screen_ad_a"], M=M, faces=(-1, 1), hood=False,
                 crown="emit_strip_cyan")
    box(W - 0.1, 0.03, 0.03, at=(0, D / 2 - 0.01, zs + H + 0.015), mat="emit_strip_magenta")
    cyl(0.04, 0.35, 6, at=(0, 0, zs + H), mat="metal_dark")
    cyl(0.07, 0.12, 10, at=(0, 0, zs + H + 0.35), mat="emit_red")
    M.light((0, -2.2, zs + H / 2), SLOT_HEX["screen_ad_c"], rng=12.0, inten=3.0, slot="screen_ad_c")
    M.light((0, 2.2, zs + H / 2), SLOT_HEX["screen_ad_a"], rng=12.0, inten=3.0, slot="screen_ad_a")
    M.light((0, 0, zs + H + 0.42), SLOT_HEX["emit_red"], rng=3.0, inten=0.8, slot="emit_red")
    M.col((0, 0, 0.225), (1.5, 1.5, 0.45))
    M.col((0, 0, zt / 2), (0.84, 0.84, zt))
    M.col((0, 0, zs + H / 2), (W, D, H))
    M.col((0, 0, zc - 0.025), (W + 0.4, 2.0, 0.05))
    return M.done(glow=SLOT_HEX["screen_ad_c"], single_screen=False)


for _v, _f in (("", "screen_ad_a"), ("_B", "screen_ad_b"), ("_C", "screen_ad_c"), ("_Screen", "screen")):
    _reg(f"Billboard_LED_Wall_6x3{_v}", billboard_led_wall, kw={"face": _f}, pivot="wall-back",
         notes=f"Wall-mounted LED video wall, 6.0 x 3.0 m active face ('{_f}', UV 0..1, see 'screens'; swap the slot for "
               "screen_ad_a/b/c or 'screen' to drive a RenderTexture), 6.38 x 3.86 x 0.53 m overall with rain hood, Z-bracket rails "
               "and a power box under it. Pivot 'wall-back' = wall plane, centred, at the bottom of the power box (cabinet "
               "bottom is 0.5 m above). Mount the pivot 4-8 m up a facade.")
_reg("Billboard_Rooftop_Rig_12x6", billboard_rooftop_rig, lods=3,
     notes="Rooftop billboard: 12.0 x 6.0 m LED face (screen_ad_b, 'screens'), 3 steel columns + rakers on concrete ballast "
           "pads, catwalk with railing (walkable deck at 'walkable.catwalk_height'), caged access ladder at +X (Unity -X), 4 "
           "floodlights aimed up at the screen ('spots': position + direction), red beacons. 13.25 x 9.72 x 6.65 m; pivot base-centre on the roof slab; "
           "screen faces +Z. Keep 4.5 m clear behind it for the rakers.")
_reg("Billboard_Pole_Double", billboard_pole_double, lods=3,
     notes="Two-sided pylon billboard: 5.2 x 2.7 m LED faces (front screen_ad_c toward +Z, back screen_ad_a toward -Z; "
           "'screens'), 0.8 m pylon on a 1.5 m concrete footing, caged ladder, catwalk under the head, red beacon. "
           "~5.8 x 11.3 x 2.0 m. Plazas, highway edges, roof corners.")


# ============================================================================================== holograms
def _fan(apex, ring, mat, closed=True):
    """Open cone/pyramid surface from an apex to a ring of points (hologram light cones)."""
    p = K._new(mat, "cone")
    bm = p.bm
    a = bm.verts.new(apex)
    vs = [bm.verts.new(q) for q in ring]
    n = len(vs)
    for i in range(n if closed else n - 1):
        bm.faces.new((a, vs[i], vs[(i + 1) % n]))
    return p


def _frustum(ring0, ring1, mat):
    p = K._new(mat, "beam")
    bm = p.bm
    a = [bm.verts.new(q) for q in ring0]
    b = [bm.verts.new(q) for q in ring1]
    n = len(a)
    for i in range(n):
        bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    return p


def _vplane(w, h, at, mat, name="holo"):
    """Vertical plane in XZ (normal -Y), centred at `at`."""
    p = K.plane(w, h, mat=mat, name=name)
    p.rot(x=90).move(*at)
    return p


def _holo_puck(M, light=True):
    """Floor hologram emitter puck (0.64 m), lens top at z ~0.165. Returns lens centre."""
    lathe([(0.001, 0.0), (0.32, 0.0), (0.32, 0.03), (0.305, 0.035), (0.305, 0.1), (0.285, 0.13), (0.255, 0.14),
           (0.17, 0.14), (0.165, 0.125), (0.001, 0.125)], 32, mat="metal_dark")
    cyl(0.322, 0.03, 32, mat="rubber")
    a = lathe([(0.17, 0.14), (0.25, 0.14), (0.25, 0.146), (0.17, 0.146), (0.17, 0.14)], 32, mat="chrome_scratched",
              close_bottom=False, close_top=False)
    for R in (0.272, 0.16):
        torus(R, 0.006, n_major=32, n_minor=4, mat="emit_cyan").move(0, 0, 0.143 if R > 0.2 else 0.128)
    lathe([(0.11, 0.125), (0.105, 0.15), (0.085, 0.168), (0.05, 0.178), (0.001, 0.181)], 20, mat="glass_dark")
    cyl(0.035, 0.004, 16, at=(0, 0, 0.18), mat="emit_cyan")
    if detail():
        for i in range(10):
            v = box(0.012, 0.02, 0.045, at=(0, -0.304, 0.07), mat="black")
            v.rot(z=i * 36 + 18)
        for i in range(6):
            a_ = math.tau * i / 6
            cyl(0.008, 0.006, 6, at=(math.cos(a_) * 0.21, math.sin(a_) * 0.21, 0.146), mat="metal_bare", start=0)
        cyl(0.006, 0.004, 6, at=(0.2, -0.24, 0.1), axis="Y", mat="emit_violet")
        tube([(0, 0.3, 0.05), (0, 0.36, 0.03), (0.04, 0.46, 0.012), (0.12, 0.58, 0.012)], 0.012, 6, mat="rubber")
    if light:
        M.light((0, 0, 0.6), HEX["cyan"], rng=3.0, inten=1.2, slot="emit_cyan")
    return (0, 0, 0.18)


def holo_projector_base():
    M = Meta()
    lens = _holo_puck(M)
    M.col((0, 0, 0.09), (0.64, 0.64, 0.18))
    M.extra["holo"] = {"emitter": [round(v, 3) for v in K.to_unity_vec(lens)], "up": [0, 1, 0]}
    return M.done(glow=HEX["cyan"])


def holo_ad_frame():
    M = Meta()
    W, zb, zt = 1.5, 0.22, 2.7
    pl = box(W + 0.1, 0.55, zb, mat="metal_dark", base=True, bevel=0.02, bseg=2)
    inset(pl, faces_where(pl, lambda f: f.normal.y < -0.9), 0.03, -0.01, mat=DARK)
    box(W - 0.1, 0.015, 0.02, at=(0, -0.283, zb - 0.06), mat="emit_strip_cyan")
    for sx in (-1, 1):
        box(0.1, 0.12, zt - zb, at=(sx * W / 2, 0, zb), mat=DARK, base=True, bevel=0.01)
        box(0.02, 0.02, zt - zb - 0.2, at=(sx * (W / 2 - 0.055), -0.04, zb + 0.1), mat="emit_strip_cyan", base=True)
        if detail():
            for z in (zb + 0.4, zt - 0.4):
                box(0.11, 0.13, 0.03, at=(sx * W / 2, 0, z), mat="chrome_scratched", bevel=0.004)
    box(W + 0.14, 0.2, 0.2, at=(0, 0, zt), mat=DARK, base=True, bevel=0.015)
    # projector on a cantilever arm in front of the header, aimed back at the plane
    beam((0, -0.08, zt + 0.1), (0, -0.62, zt + 0.1), 0.08, 0.08, mat="metal_dark", up=(0, 0, 1))
    hd = box(0.26, 0.2, 0.16, at=(0, -0.68, zt + 0.05), mat=DARK, bevel=0.02)
    lens = Vector((0, -0.62, zt - 0.04))
    cyl(0.05, 0.03, 16, at=tuple(lens), mat="glass_dark", center=True).rot_about(tuple(lens), x=-35)
    cyl(0.03, 0.02, 12, at=tuple(lens + Vector((0, 0.01, -0.02))), mat="emit_cyan", center=True)
    if detail():
        for k in range(4):
            box(0.27, 0.012, 0.01, at=(0, -0.62 - k * 0.03, zt + 0.135), mat="metal_dark")
        tube([(0.1, -0.1, zt + 0.2), (0.1, -0.4, zt + 0.22), (0.1, -0.6, zt + 0.14)], 0.01, 6, mat="rubber")
    # projection plane + content
    pw, ph, pz = W - 0.18, 2.05, (zb + zt) / 2 + 0.02
    _vplane(pw, ph, (0, 0.0, pz), "holo_cyan")
    for i, g in enumerate(glyph_set(140, 3, 7)):
        flat_glyph(g, -0.32, pz + 0.6 - i * 0.52, 0.42, -0.01, mat="holo_magenta", w=0.07, t=0.004)
    ring = [(0.3 + 0.26 * math.cos(math.tau * i / 24), -0.012, pz + 0.35 + 0.26 * math.sin(math.tau * i / 24)) for i in range(24)]
    tube(ring, 0.012, 4, mat="holo_magenta", closed=True)
    if K.LOD < 2:
        for k in range(9):
            box(pw - 0.04, 0.002, 0.012, at=(0, -0.006, pz - ph / 2 + 0.1 + k * 0.23), mat="holo_cyan")
        box(0.5, 0.003, 0.06, at=(0.3, -0.008, pz - 0.25), mat="holo_magenta")
        box(0.4, 0.003, 0.03, at=(0.25, -0.008, pz - 0.4), mat="holo_cyan")
    # light cone: lens -> plane corners
    cs = [(-pw / 2, 0.0, pz - ph / 2), (pw / 2, 0.0, pz - ph / 2), (pw / 2, 0.0, pz + ph / 2), (-pw / 2, 0.0, pz + ph / 2)]
    _fan(tuple(lens), cs, "holo_cyan")
    M.light((0, -0.5, pz), HEX["cyan"], rng=4.0, inten=1.5, slot="holo_cyan")
    M.light((-0.32, -0.4, pz + 0.3), HEX["magenta"], rng=3.0, inten=1.0, slot="holo_magenta")
    M.col((0, 0, zb / 2), (W + 0.1, 0.55, zb))
    for sx in (-1, 1):
        M.col((sx * W / 2, 0, (zb + zt) / 2), (0.1, 0.12, zt - zb))
    M.col((0, 0, zt + 0.1), (W + 0.14, 0.2, 0.2))
    M.screen((0, -0.003, pz), (pw, ph), (0, -1, 0), "holo_cyan")
    return M.done(glow=HEX["cyan"])


def holo_sign_glyph():
    M = Meta()
    lens = _holo_puck(M, light=False)
    zc, size = 1.55, 0.8
    # projection plate + frame ring + glyph
    _vplane(size + 0.1, size + 0.1, (0, 0, zc), "holo_cyan")
    flat_glyph(GLYPH_B, 0, zc, size * 0.82, -0.008, mat="holo_magenta", w=0.08, t=0.006)
    flat_glyph(GLYPH_B, 0, zc, size * 0.82, 0.014, mat="holo_magenta", w=0.08, t=0.006)
    sq = _rrect(size + 0.1, size + 0.1, 0.06, cz=zc)
    tube([(x, 0, z) for x, z in sq], 0.008, 4, mat="holo_cyan", closed=True)
    for k, (R, tilt) in enumerate(((0.62, 72), (0.56, -64))):
        t = torus(R, 0.006, n_major=40, n_minor=4, mat="holo_cyan" if k == 0 else "holo_magenta")
        t.rot(x=tilt).rot(z=25 if k == 0 else -20).move(0, 0, zc)
    # beam: lens -> flattened ellipse at the plate bottom
    n = 16
    zb = zc - (size + 0.1) / 2
    ring0 = [(0.04 * math.cos(math.tau * i / n), 0.04 * math.sin(math.tau * i / n), lens[2] + 0.005) for i in range(n)]
    ring1 = [(0.47 * math.cos(math.tau * i / n), 0.07 * math.sin(math.tau * i / n), zb) for i in range(n)]
    _frustum(ring0, ring1, "holo_cyan")
    M.light((0, -0.3, zc), HEX["magenta"], rng=4.0, inten=1.6, slot="holo_magenta")
    M.light((0, 0, 0.5), HEX["cyan"], rng=2.5, inten=1.0, slot="emit_cyan")
    M.col((0, 0, 0.09), (0.64, 0.64, 0.18))
    M.extra["holo"] = {"emitter": [round(v, 3) for v in K.to_unity_vec(lens)], "glyphCentre": [round(v, 3) for v in K.to_unity_vec((0, 0, zc))]}
    return M.done(glow=HEX["magenta"])


_reg("Holo_Projector_Base", holo_projector_base,
     notes="Floor hologram emitter puck 0.64 m dia x 0.18 m (0.91 m deep incl. the floor cable trailing toward -Z): glass lens with cyan core, two cyan LED rings, vents, floor cable "
           "toward -Z. 'holo.emitter' = lens point for runtime hologram meshes / VFX. Walk-over height; collider is the puck.")
_reg("Holo_Ad_Frame", holo_ad_frame,
     notes="Free-standing hologram ad frame 1.64 x 2.93 x 1.06 m: plinth, two posts with cyan LED, header with a cantilever "
           "projector throwing a holo_cyan light cone onto a 1.32 x 2.05 m holo_cyan plane with holo_magenta glyph column. "
           "Faces +Z. 'screens' gives the plane rect (Unity can replace it with an animated hologram). Plane/cone have no collider.")
_reg("Holo_Sign_Glyph", holo_sign_glyph,
     notes="Floor puck projecting a floating 0.9 m holographic glyph plate (holo_magenta glyph on a holo_cyan plate, two orbit "
           "rings) at 1.55 m, readable from both sides. 1.15 x 2.15 x 0.91 m overall (puck 0.64). Collider = puck only.")


# ============================================================================================== traffic
def _signal_head(at, facing=-1, M=None, backplate=True, heads=("emit_red", "emit_amber", "emit_green")):
    """Three-aspect LED signal head centred at `at`, lenses facing -Y (facing=-1) or +Y (facing=1). Returns top z."""
    n0 = K.part_count()
    hb = box(0.34, 0.26, 0.98, mat=DARK, bevel=0.03, bseg=2)
    for i, mat in enumerate(heads):
        z = 0.3 - i * 0.3
        box(0.3, 0.02, 0.28, at=(0, -0.135, z), mat="black", bevel=0.006)
        cyl(0.102, 0.018, 16, at=(0, -0.15, z), axis="Y", mat=mat)
        if detail():
            torus(0.108, 0.007, n_major=16, n_minor=4, mat="metal_dark").rot(x=90).move(0, -0.155, z)
        pts = [(math.cos(math.radians(a)) * 0.132, math.sin(math.radians(a)) * 0.132) for a in range(-20, 201, 22)]
        pts += [(math.cos(math.radians(a)) * 0.12, math.sin(math.radians(a)) * 0.12) for a in range(200, -21, -22)]
        v = extrude(pts, 0.2, plane="XZ", mat=DARK, name="visor")
        v.move(0, -0.25, z)
    if backplate:
        bp = box(0.58, 0.02, 1.22, at=(0, 0.14, 0), mat="black", bevel=0.004)
        for sx in (-1, 1):
            box(0.025, 0.012, 1.2, at=(sx * 0.275, 0.126, 0), mat="emit_strip_cyan")
        for sz in (-1, 1):
            box(0.55, 0.012, 0.025, at=(0, 0.126, sz * 0.595), mat="emit_strip_cyan")
    if detail():
        for sz in (-1, 1):
            box(0.2, 0.02, 0.012, at=(0, -0.131, sz * 0.47), mat="metal_bare")
    x, y, z = at
    for p in K.parts_since(n0):
        if facing > 0:
            p.rot(z=180)
        p.move(x, y, z)
    if M is not None:
        for i, mat in enumerate(heads):
            M.light((x, y + facing * 0.45, z + 0.3 - i * 0.3), SLOT_HEX[mat], rng=6.0, inten=1.2, slot=mat)
    return z + 0.49


def _ped_signal(at, facing_x=1, M=None):
    """Pedestrian signal (hand = emit_red, walker = emit_white) facing +X/-X."""
    n0 = K.part_count()
    box(0.34, 0.3, 0.62, mat=DARK, bevel=0.025, bseg=2)
    for z, mat in ((0.14, "emit_red"), (-0.14, "emit_white")):
        box(0.26, 0.02, 0.22, at=(0, -0.155, z), mat=mat, bevel=0.004)
        box(0.3, 0.12, 0.012, at=(0, -0.2, z + 0.13), mat=DARK)
    if detail():  # stylised icons (abstract blocks, no text)
        box(0.05, 0.006, 0.1, at=(-0.02, -0.168, 0.12), mat="black")
        box(0.03, 0.006, 0.08, at=(0.04, -0.168, -0.16), mat="black")
        cyl(0.02, 0.006, 8, at=(0.04, -0.168, -0.08), axis="Y", mat="black", center=True)
    x, y, z = at
    for p in K.parts_since(n0):
        p.rot(z=90 if facing_x > 0 else -90).move(x, y, z)
    if M is not None:
        M.light((x + facing_x * 0.4, y, z + 0.14), SLOT_HEX["emit_red"], rng=3.0, inten=0.8, slot="emit_red")
        M.light((x + facing_x * 0.4, y, z - 0.14), SLOT_HEX["emit_white"], rng=3.0, inten=0.8, slot="emit_white")


def _pole_base(r=0.13):
    box(0.7, 0.7, 0.12, mat="concrete_dark", base=True, bevel=0.02)
    box(0.42, 0.42, 0.02, at=(0, 0, 0.12), mat="metal_dark", base=True, bevel=0.004)
    lathe([(r + 0.07, 0.14), (r + 0.07, 0.2), (r + 0.02, 0.45), (r + 0.01, 0.47)], 16, mat=DARK)
    if detail():
        for sx in (-1, 1):
            for sy in (-1, 1):
                cyl(0.016, 0.05, 6, at=(sx * 0.16, sy * 0.16, 0.14), mat="metal_bare")


def _push_button(at, facing=-1, M=None):
    x, y, z = at
    box(0.12, 0.08, 0.22, at=(x, y, z), mat="metal_painted_yellow", bevel=0.012)
    t = torus(0.03, 0.005, n_major=12, n_minor=4, mat="emit_cyan")
    t.rot(x=90).move(x, y + facing * 0.042, z + 0.02)
    cyl(0.022, 0.012, 10, at=(x, y + facing * 0.04 - (0.012 if facing < 0 else 0), z + 0.02), axis="Y", mat="metal_bare")
    box(0.06, 0.004, 0.04, at=(x, y + facing * 0.041, z - 0.06), mat="black")


def traffic_light_cyber():
    M = Meta()
    _pole_base(0.13)
    H = 6.4
    lathe([(0.13, 0.47), (0.115, 3.0), (0.1, H - 0.1), (0.105, H - 0.08), (0.105, H), (0.06, H + 0.06), (0.001, H + 0.07)], 16, mat=DARK)
    za = 5.75
    box(0.3, 0.06, 0.36, at=(0.13, 0, za), mat="metal_dark", bevel=0.01)       # arm flange
    cyl(0.095, 6.0, 16, at=(0.14, 0, za), axis="X", r2=0.06, mat=DARK)
    cyl(0.065, 0.04, 12, at=(6.14, 0, za), axis="X", mat="metal_dark")
    tube([(0.1, 0, H - 0.15), (2.0, 0, za + 0.3), (3.6, 0, za + 0.07)], 0.018, 6, mat="metal_bare")
    for x in (3.0, 5.2):
        cyl(0.03, 0.22, 8, at=(x, 0, za - 0.3), mat="metal_dark")
        box(0.14, 0.14, 0.04, at=(x, 0, za - 0.08), mat="metal_dark")
        _signal_head((x, 0.0, za - 0.3 - 0.61), -1, M)
    _signal_head((0.0, -0.32, 3.4), -1, M)
    box(0.08, 0.2, 0.08, at=(0, -0.13, 3.75), mat="metal_dark")
    box(0.08, 0.2, 0.08, at=(0, -0.13, 3.05), mat="metal_dark")
    _ped_signal((0.33, 0.0, 2.6), 1, M)
    box(0.2, 0.08, 0.08, at=(0.15, 0, 2.6), mat="metal_dark")
    _push_button((0.0, -0.15, 1.1), -1)
    # pole LED stripe on standoffs
    box(0.045, 0.03, 2.3, at=(0, -0.155, 0.8), mat="emit_strip_cyan", base=True)
    box(0.06, 0.02, 2.32, at=(0, -0.13, 0.79), mat="metal_dark", base=True)
    # street-name blade (lit, invented glyphs both faces) + camera at the arm tip
    nb = box(1.3, 0.04, 0.26, at=(1.25, 0, za + 0.24), mat="metal_dark", bevel=0.008)
    nb.set_mat("emit_panel_white", where=lambda f: abs(f.normal.y) > 0.9)
    for side in (-1, 1):
        with frame(M, x=1.25, y=side * 0.021, z=za + 0.24, rz=0 if side < 0 else 180):
            for i, g in enumerate(glyph_set(301, 4, 6)):
                flat_glyph(g, -0.42 + i * 0.28, 0, 0.18, 0.0, w=0.1, t=0.003)
    for x in (0.9, 1.6):
        box(0.03, 0.03, 0.12, at=(x, 0, za + 0.07), mat="metal_dark", base=True)
    cam = box(0.12, 0.26, 0.12, at=(5.95, -0.08, za - 0.16), mat="paint_glossy_white", bevel=0.02)
    cyl(0.04, 0.02, 12, at=(5.95, -0.22, za - 0.16), axis="Y", mat="glass_dark")
    box(0.04, 0.04, 0.1, at=(5.95, 0, za - 0.07), mat="metal_dark")
    if detail():
        tube([(2.6, 0, za + 0.07), (2.6, -0.06, za + 0.0), (2.95, -0.06, za - 0.25)], 0.008, 4, mat="rubber")
    M.col((0, 0, H / 2), (0.3, 0.3, H))
    M.col((0, 0, 0.06), (0.7, 0.7, 0.12))
    M.extra["armReach"] = 6.15
    return M.done(glow=SLOT_HEX["emit_green"], single_screen=False)


def traffic_light_pole_small():
    M = Meta()
    _pole_base(0.1)
    H = 3.1
    lathe([(0.1, 0.47), (0.09, H), (0.06, H + 0.04), (0.001, H + 0.05)], 16, mat=DARK)
    for facing in (-1, 1):
        _signal_head((0.0, facing * 0.29, H - 0.35), facing, M, backplate=False)
        for z in (H - 0.1, H - 0.6):
            box(0.08, 0.16, 0.06, at=(0, facing * 0.1, z), mat="metal_dark")
    _ped_signal((0.3, 0.0, 2.1), 1, M)
    box(0.18, 0.07, 0.07, at=(0.13, 0, 2.1), mat="metal_dark")
    _push_button((0.0, -0.13, 1.1), -1)
    torus(0.105, 0.012, n_major=20, n_minor=4, mat="emit_cyan").move(0, 0, 1.75)
    torus(0.105, 0.012, n_major=20, n_minor=4, mat="emit_cyan").move(0, 0, 1.68)
    M.light((0, -0.3, 1.72), HEX["cyan"], rng=2.5, inten=0.8, slot="emit_cyan")
    M.col((0, 0, H / 2), (0.24, 0.24, H))
    M.col((0, 0, 0.06), (0.7, 0.7, 0.12))
    return M.done(glow=SLOT_HEX["emit_green"], single_screen=False)


def light_strip_bar(color="cyan", L=2.0):
    M = Meta()
    prof = [(0.0, 0.0), (0.0, 0.08), (-0.012, 0.08), (-0.05, 0.068), (-0.058, 0.058), (-0.058, 0.022), (-0.05, 0.012), (-0.012, 0.0)]
    b = extrude(prof, L, plane="YZ", mat="metal_dark", bevel=0.002)
    box(L - 0.04, 0.012, 0.034, at=(0, -0.062, 0.04), mat=f"emit_strip_{color}")
    for sx in (-1, 1):
        box(0.014, 0.064, 0.086, at=(sx * (L / 2 + 0.007), -0.03, 0.04), mat="plastic_dark", bevel=0.003)
    for x in (-L * 0.35, 0.0, L * 0.35):
        box(0.04, 0.066, 0.012, at=(x, -0.03, 0.086), mat="chrome_scratched")
        box(0.04, 0.066, 0.012, at=(x, -0.03, -0.006), mat="chrome_scratched")
        if detail():
            for z in (0.086, -0.006):
                cyl(0.006, 0.008, 6, at=(x, -0.066, z), axis="Y", mat="metal_bare", start=0)
    tube([(-L / 2 - 0.014, -0.03, 0.04), (-L / 2 - 0.06, -0.03, 0.04), (-L / 2 - 0.09, -0.015, 0.04), (-L / 2 - 0.09, -0.001, 0.04)],
         0.007, 6, mat="rubber")
    K.ground()
    for x in (-L / 4, L / 4):
        M.light((x, -0.35, 0.04), HEX[color], rng=3.0, inten=1.0, slot=f"emit_strip_{color}")
    M.col((0, -0.03, 0.046), (L, 0.06, 0.092))
    return M.done(glow=HEX[color])


_reg("Traffic_Light_Cyber", traffic_light_cyber, cat="neon", lods=3,
     notes="Mast-arm traffic signal: 6.5 m pole, 6.15 m arm reaching toward Unity -X (Blender +X) over the road, two LED signal "
           "heads with cyan-LED backplates on the arm + one near-side head on the pole (all face +Z), ped signal facing Unity -X, "
           "push button, cyan pole stripe, lit street-name blade (invented glyphs), camera. Lens slots emit_red / emit_amber / "
           "emit_green are separate so code can cycle them (each lens has a 'lights' entry with its slot). Pivot = pole base "
           "centre (NOT the bounds centre). Put the pole 0.5 m behind the kerb.")
_reg("Traffic_Light_Pole_Small", traffic_light_pole_small,
     notes="3.24 m pedestal signal (0.91 x 3.24 x 1.28 m overall): back-to-back LED heads (+Z and -Z), ped signal facing Unity -X, push button, cyan LED rings. "
           "Pivot = pole base centre. Medians, side streets, crossings.")
for _c, _sfx in (("cyan", ""), ("magenta", "_Magenta"), ("yellow", "_Yellow")):
    _reg(f"Light_Strip_Bar_2m{_sfx}", light_strip_bar, kw={"color": _c}, pivot="wall-back",
         notes=f"2.0 m wall LED bar (emit_strip_{_c} diffuser in an anodised extrusion, 3 clips, feed cable into the wall at -X "
               "end). 2.11 x 0.10 x 0.07 m. Pivot 'wall-back' = wall plane, centred, at the bar's bottom edge. Run under eaves, "
               "along door heads (2.4-3 m), stair edges or vertically (rotate 90 about Z-forward).")


# ============================================================================================== bus shelter
def bus_shelter_neon():
    M = Meta()
    W, D = 4.2, 1.7
    yb, yf = 0.75, -0.6
    slab = box(W + 0.2, D + 0.2, 0.1, at=(0, 0.05, 0), mat="concrete_dark", base=True, bevel=0.015)
    box(W + 0.1, 0.03, 0.02, at=(0, 0.05 - (D + 0.2) / 2 - 0.004, 0.08), mat="emit_strip_cyan")
    zr = 2.62
    for x in (-W / 2, 0.0, W / 2):
        box(0.09, 0.09, zr - 0.1, at=(x, yb, 0.1), mat=DARK, base=True, bevel=0.008)
    for x in (-W / 2, W / 2):
        box(0.09, 0.09, zr - 0.1, at=(x, yf, 0.1), mat=DARK, base=True, bevel=0.008)
    # roof: slab with fascia LED, downlight panels and a drip edge
    roof = box(W + 0.4, D + 0.45, 0.16, at=(0, 0.02, zr), mat=DARK, base=True, bevel=0.02, bseg=2)
    yfr = 0.02 - (D + 0.45) / 2
    box(W + 0.36, 0.02, 0.05, at=(0, yfr - 0.01, zr + 0.08), mat="emit_strip_magenta")
    for sx in (-1, 1):
        box(0.02, D + 0.4, 0.04, at=(sx * (W / 2 + 0.21), 0.02, zr + 0.08), mat="emit_strip_cyan")
    for x in (-1.0, 1.0):
        box(1.3, 0.55, 0.012, at=(x, 0.0, zr - 0.006), mat="emit_panel_white")
    if detail():
        box(W + 0.3, D + 0.3, 0.05, at=(0, 0.02, zr + 0.16), mat="carbon_panel", base=True, bevel=0.01)
    # back glazing with rails
    for x0, x1 in ((-W / 2, 0.0), (0.0, W / 2)):
        box(x1 - x0 - 0.09, 0.012, 1.95, at=((x0 + x1) / 2, yb, 0.3), mat="glass", base=True)
    for z in (0.28, 2.27):
        box(W, 0.05, 0.05, at=(0, yb, z), mat="chrome_scratched", base=True)
    # side glass at -X
    box(0.012, yb - yf - 0.09, 1.95, at=(-W / 2, (yb + yf) / 2, 0.3), mat="glass", base=True)
    for z in (0.28, 2.27):
        box(0.05, yb - yf, 0.05, at=(-W / 2, (yb + yf) / 2, z), mat="chrome_scratched", base=True)
    # double-sided ad lightbox at +X
    ax, ad_w, az0, az1 = W / 2 + 0.02, 1.2, 0.3, 2.25
    ab = box(0.2, ad_w + 0.1, az1 - az0 + 0.1, at=(ax, (yb + yf) / 2, (az0 + az1) / 2), mat="chrome_scratched", bevel=0.012)
    ycen = (yb + yf) / 2
    for side, mat in ((1, "screen_ad_c"), (-1, "screen_ad_a")):
        pn = box(0.02, ad_w, az1 - az0, at=(ax + side * 0.105, ycen, (az0 + az1) / 2), mat=DARK)
        pn.set_mat(mat, where=lambda f, s=side: f.normal.x * s > 0.9)
        M.screen((ax + side * 0.116, ycen, (az0 + az1) / 2), (ad_w, az1 - az0), (side, 0, 0), mat)
    # bench
    for x in (-1.3, 0.0, 1.3):
        box(0.06, 0.42, 0.05, at=(x, yb - 0.24, 0.42), mat="metal_dark", base=True)
        box(0.06, 0.05, 0.42, at=(x, yb - 0.05, 0.05), mat="metal_dark", base=True)
    for k in range(4):
        box(3.2, 0.085, 0.03, at=(0, yb - 0.08 - k * 0.1, 0.47), mat="chrome_scratched", base=True, bevel=0.004)
    # route map screen on the back glass + stop totem lightbox on the -X front post
    rm = box(0.72, 0.03, 1.02, at=(-1.05, yb - 0.025, 1.45), mat=DARK, bevel=0.006)
    rm.set_mat("screen", where=lambda f: f.normal.y < -0.9)
    M.screen((-1.05, yb - 0.041, 1.45), (0.72, 1.02), (0, -1, 0), "screen")
    tb = box(0.36, 0.1, 0.5, at=(-W / 2, yf - 0.1, 2.15), mat=DARK, bevel=0.01)
    tb.set_mat("emit_panel_cyan", where=lambda f: abs(f.normal.y) > 0.9)
    for side in (-1, 1):
        with frame(M, x=-W / 2, y=yf - 0.1 + side * 0.051, z=2.15, rz=0 if side < 0 else 180):
            flat_glyph(glyph_set(410, 1, 6)[0], 0, 0, 0.3, 0.0, w=0.1)
    # gutter + downpipe, post base plates, slim litter bin
    box(W + 0.3, 0.1, 0.08, at=(0, 0.02 + (D + 0.45) / 2 + 0.03, zr + 0.02), mat="metal_dark", bevel=0.01)
    cyl(0.04, zr - 0.12, 10, at=(W / 2 - 0.14, yb + 0.1, 0.1), mat="metal_dark")
    tube([(W / 2 - 0.14, yb + 0.1, zr - 0.04), (W / 2 - 0.14, yb + 0.2, zr + 0.0), (W / 2 - 0.14, yb + 0.25, zr + 0.03)], 0.04, 8, mat="metal_dark")
    if detail():
        for x, y in ((-W / 2, yb), (0.0, yb), (W / 2, yb), (-W / 2, yf), (W / 2, yf)):
            box(0.2, 0.2, 0.012, at=(x, y, 0.1), mat="metal_dark", base=True)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    cyl(0.01, 0.02, 6, at=(x + sx * 0.07, y + sy * 0.07, 0.112), mat="metal_bare")
    lathe([(0.001, 0.1), (0.2, 0.1), (0.2, 0.95), (0.21, 0.97), (0.21, 1.02), (0.15, 1.02), (0.15, 0.98), (0.001, 0.98)], 16,
          at=(W / 2 - 0.45, yf - 0.05, 0), mat="metal_painted_green")
    box(0.16, 0.012, 0.05, at=(W / 2 - 0.45, yf - 0.255, 0.9), mat="black")
    M.light((0, 0.0, zr - 0.3), SLOT_HEX["emit_panel_white"], rng=5.0, inten=1.4, slot="emit_panel_white")
    M.light((0, yfr - 0.3, zr + 0.05), HEX["magenta"], rng=4.0, inten=1.0, slot="emit_strip_magenta")
    M.light((ax + 0.6, ycen, 1.3), SLOT_HEX["screen_ad_c"], rng=4.0, inten=1.2, slot="screen_ad_c")
    M.col((0, 0.05, 0.05), (W + 0.2, D + 0.2, 0.1))
    M.col((0, yb, 1.3), (W, 0.08, 2.4))
    M.col((-W / 2, (yb + yf) / 2, 1.3), (0.08, yb - yf, 2.4))
    M.col((ax, ycen, (az0 + az1) / 2), (0.22, ad_w + 0.1, az1 - az0 + 0.1))
    M.col((0, yb - 0.22, 0.25), (3.2, 0.45, 0.5))
    M.col((0, 0.02, zr + 0.1), (W + 0.4, D + 0.45, 0.2))
    for x in (-W / 2, W / 2):
        M.col((x, yf, 1.3), (0.1, 0.1, 2.5))
    M.col((W / 2 - 0.45, yf - 0.05, 0.56), (0.42, 0.42, 0.92))
    return M.done(glow=HEX["magenta"], single_screen=False)


_reg("Bus_Shelter_Neon", bus_shelter_neon, lods=3,
     notes="Glass bus shelter 4.64 x 2.83 x 2.25 m, open side +Z: back + left glazing, chrome bench, roof with magenta LED fascia, "
           "cyan side LEDs and two downlight panels, double-sided ad lightbox at Unity -X end (screen_ad_c outside, screen_ad_a "
           "inside), route-map 'screen' on the back glass, cyan stop totem with an invented glyph. Kerb strip LED on the slab. "
           "Base-centre pivot, slab 0.1 m high (walkable).")


# ============================================================================================== street commerce
def _stool(x, y, seat="paint_glossy_red", h=0.68):
    cyl(0.19, 0.025, 14, at=(x, y, 0), mat="metal_dark", bevel=0.006)
    cyl(0.028, h - 0.06, 8, at=(x, y, 0.025), mat="chrome_scratched")
    torus(0.15, 0.011, n_major=14, n_minor=4, mat="chrome_scratched").move(x, y, 0.26)
    if detail():
        for a in (0, 90):
            b = box(0.3, 0.012, 0.012, at=(x, y, 0.26), mat="chrome_scratched")
            b.rot_about((x, y, 0.26), z=a)
    lathe([(0.001, h - 0.04), (0.165, h - 0.04), (0.18, h - 0.02), (0.18, h + 0.02), (0.165, h + 0.04), (0.001, h + 0.045)], 16,
          at=(x, y, 0), mat=seat)


def vending_machine(kind="drinks"):
    M = Meta()
    W, D, H = 0.9, 0.8, 1.85
    drinks = kind == "drinks"
    body = "paint_glossy_white" if drinks else DARK
    trim = "paint_glossy_red" if drinks else "metal_painted_yellow"
    strip = "emit_strip_cyan" if drinks else "emit_strip_violet"
    header = "emit_panel_magenta" if drinks else "emit_panel_yellow"
    yfr = -D / 2
    box(W - 0.04, D - 0.06, 0.08, at=(0, 0.01, 0), mat="metal_dark", base=True, bevel=0.01)
    sh = box(W, D - 0.12, H - 0.08, at=(0, 0.06, 0.08), mat=body, base=True, bevel=0.02, bseg=2)
    inset(sh, faces_where(sh, lambda f: abs(f.normal.x) > 0.9), 0.06, -0.006)
    yd = yfr + 0.06                                           # door front plane = yfr, cavity back at yd + 0.06
    zw0, zw1 = 0.66, 1.58
    xw0, xw1 = -0.42, 0.2
    # door frame pieces
    hd = box(W, 0.12, H - zw1, at=(0, yd, zw1), mat=body, base=True, bevel=0.012)
    hd.set_mat(header, where=lambda f: f.normal.y < -0.9)
    bt = box(W, 0.12, zw0 - 0.08, at=(0, yd, 0.08), mat=body, base=True, bevel=0.012)
    box(0.04, 0.12, zw1 - zw0, at=(-W / 2 + 0.02, yd, zw0), mat=trim, base=True, bevel=0.006)
    cc = box(W / 2 - xw1, 0.12, zw1 - zw0, at=((xw1 + W / 2) / 2, yd, zw0), mat=trim, base=True, bevel=0.008)
    # cavity: lit back panel, shelves, products, glass
    box(xw1 - xw0, 0.012, zw1 - zw0, at=((xw0 + xw1) / 2, yd + 0.055, zw0), mat="emit_panel_white", base=True)
    rows = [0.68, 0.915, 1.15, 1.385]
    cols_ = ["car_paint_red", "car_paint_teal", "car_paint_yellow", "car_paint_magenta", "car_paint_white", "car_paint_black"]
    for r, z in enumerate(rows):
        box(xw1 - xw0, 0.1, 0.012, at=((xw0 + xw1) / 2, yd - 0.005, z), mat="metal_bare", base=True)
        box(xw1 - xw0, 0.006, 0.026, at=((xw0 + xw1) / 2, yd - 0.056, z + 0.006), mat="black", base=True)
        n = 6 if drinks else 4
        for i in range(n):
            x = xw0 + (i + 0.5) * (xw1 - xw0) / n
            c = cols_[(i + r * 2) % len(cols_)]
            if drinks:
                cyl(0.032, 0.13 if (i + r) % 3 else 0.17, 8, at=(x, yd, z + 0.012), mat=c)
                if detail():
                    cyl(0.026, 0.008, 8, at=(x, yd, z + 0.012 + (0.13 if (i + r) % 3 else 0.17)), mat="metal_bare")
            else:
                pk = box(0.1, 0.035, 0.15, at=(x, yd - 0.025, z + 0.018), mat=c, base=True, bevel=0.012, bseg=1)
                pk.rot_about((x, yd - 0.025, z + 0.018), x=-6)
                if detail():
                    pts = [(x + 0.045 * math.cos(t * 0.9), yd - 0.04 + t * 0.006, z + 0.06 + 0.045 * math.sin(t * 0.9)) for t in range(14)]
                    tube(pts, 0.0035, 4, mat="metal_bare", caps=False)
            if detail():
                box(0.022, 0.006, 0.012, at=(x, yd - 0.06, z + 0.019), mat="emit_amber" if (i + r) % 4 else "emit_green")
    box(xw1 - xw0 + 0.01, 0.006, zw1 - zw0 + 0.01, at=((xw0 + xw1) / 2, yd - 0.055, zw0 - 0.005), mat="glass", base=True)
    # control column: screen, card reader, coin slot, keypad
    cx = (xw1 + W / 2) / 2
    sc = box(0.16, 0.012, 0.11, at=(cx, yfr - 0.004, 1.43), mat="black", bevel=0.003)
    sc.set_mat("screen", where=lambda f: f.normal.y < -0.9)
    M.screen((cx, yfr - 0.011, 1.43), (0.16, 0.11), (0, -1, 0), "screen")
    box(0.11, 0.03, 0.09, at=(cx, yfr - 0.012, 1.24), mat="black", bevel=0.008)
    box(0.07, 0.006, 0.008, at=(cx, yfr - 0.03, 1.27), mat="emit_green")
    box(0.09, 0.012, 0.05, at=(cx, yfr - 0.004, 1.12), mat="chrome_scratched", bevel=0.003)
    if detail():
        box(0.006, 0.006, 0.03, at=(cx, yfr - 0.011, 1.12), mat="black")
        for i in range(3):
            for j in range(3):
                box(0.026, 0.008, 0.02, at=(cx - 0.035 + j * 0.035, yfr - 0.004, 0.96 - i * 0.03), mat="metal_bare", bevel=0.002)
        box(0.1, 0.03, 0.06, at=(cx, yfr - 0.01, 0.76), mat="black", bevel=0.006)   # change return
    # dispenser hatch + kick panel
    hh = box(0.66, 0.02, 0.2, at=(-0.07, yfr - 0.004, 0.25), mat="chrome_scratched", bevel=0.006)
    box(0.6, 0.02, 0.15, at=(-0.07, yfr - 0.012, 0.25), mat="plastic_dark", bevel=0.01).rot_about((-0.07, yfr, 0.32), x=-8)
    box(W - 0.06, 0.01, 0.06, at=(0, yfr - 0.001, 0.12), mat="grating")
    # edge LEDs, header glyphs, top cap
    for sx in (-1, 1):
        box(0.02, 0.02, H - 0.2, at=(sx * (W / 2 - 0.004), yfr - 0.004, 0.12), mat=strip, base=True)
    with frame(M, x=-0.05, y=yfr, z=(zw1 + H) / 2):
        for i, g in enumerate(glyph_set(500 + (0 if drinks else 7), 4, 6)):
            flat_glyph(g, -0.27 + i * 0.18, 0, 0.15, -0.001, w=0.1, t=0.003)
        cyl(0.07, 0.003, 16, at=(0.36, -0.004, 0), axis="Y", mat="black")
    box(W + 0.02, D - 0.1, 0.03, at=(0, 0.05, H), mat="metal_dark", base=True, bevel=0.006)
    if detail():
        box(0.4, 0.006, 0.3, at=(0, D / 2 + 0.003, 0.3), mat="grating")
        tube([(0.3, D / 2 - 0.02, 0.15), (0.3, D / 2 + 0.03, 0.1), (0.3, D / 2 + 0.05, 0.012), (0.15, D / 2 + 0.06, 0.012)], 0.01, 6, mat="rubber")
    hx = SLOT_HEX[header]
    M.light((-0.1, yfr - 0.6, 1.1), SLOT_HEX["emit_panel_white"], rng=3.5, inten=1.2, slot="emit_panel_white")
    M.light((0, yfr - 0.4, 1.72), hx, rng=3.0, inten=0.9, slot=header)
    M.col((0, 0, H / 2), (W, D, H))
    return M.done(glow=hx)


_reg("Vending_Machine_Drinks", vending_machine, kw={"kind": "drinks"}, zones=("plaza", "metro"),
     notes="Drinks vending machine 0.92 x 1.88 x 0.91 m (0.8 m cabinet + rear cable), white gloss body with red trim: lit can display (4 rows behind glass, "
           "emit_panel_white back + amber/green price LEDs), magenta header lightbox with invented glyphs, cyan edge LEDs, "
           "card reader, coin slot, keypad, 'screen' (0.16 x 0.11) for prices, dispenser hatch. Front +Z; back against a wall.")
_reg("Vending_Machine_Food", vending_machine, kw={"kind": "food"}, zones=("plaza", "metro"),
     notes="Snack vending machine 0.92 x 1.88 x 0.91 m, dark gloss body with yellow trim: packets on spiral coils, yellow header "
           "lightbox, violet edge LEDs, card reader, keypad, 'screen'. Front +Z.")


def _lantern(x, y, ztop, drop=0.25, mat="emit_red", r=0.16, h=0.42):
    tube([(x, y, ztop), (x, y, ztop - drop)], 0.004, 4, mat="black")
    zc = ztop - drop - 0.03
    cyl(0.07, 0.03, 10, at=(x, y, zc), mat="wood")
    prof = [(0.07, 0.0), (r * 0.8, -h * 0.12), (r, -h * 0.35), (r, -h * 0.62), (r * 0.8, -h * 0.88), (0.07, -h)]
    lathe(prof, 14, at=(x, y, zc), mat=mat, close_bottom=False, close_top=False)
    cyl(0.07, 0.035, 10, at=(x, y, zc - h - 0.035), mat="wood")
    if detail():
        for k in (0.35, 0.62):
            torus(r + 0.003, 0.004, n_major=14, n_minor=3, mat="black").move(x, y, zc - h * k)
        tube([(x, y, zc - h - 0.035), (x, y, zc - h - 0.2)], 0.012, 4, mat="paint_glossy_red")  # tassel
    return (x, y, zc - h / 2)


def _noren(x0, x1, z_top, y, length=0.5, n=5, seed=3, mat="tarp_blue", glyph_seed=None, M=None):
    rnd = random.Random(seed)
    gap = 0.03
    w = (x1 - x0 - gap * (n - 1)) / n
    cyl(0.015, x1 - x0 + 0.12, 8, at=(x0 - 0.06, y, z_top + 0.01), axis="X", mat="wood")
    for i in range(n):
        xc = x0 + w / 2 + i * (w + gap)
        p = K.plane(w, length, mat=mat, nx=K.seg(4, 1) if K.LOD else 4, ny=K.seg(5, 1) if K.LOD else 5, name="noren")
        ph, sw = rnd.uniform(0, 6), rnd.uniform(0.02, 0.05)

        def f(co, ph=ph, sw=sw):
            u = (co.y + length / 2) / length          # 0 at bottom .. 1 top (before rotation y is "down")
            return (co.x, co.y, sw * (1 - u) ** 1.5 * math.sin(co.x * 9 + ph) + 0.012 * math.sin(co.x * 23 + ph))
        p.displace(f)
        p.rot(x=90).move(xc, y, z_top - length / 2)
        if glyph_seed is not None and detail():
            g = glyph_set(glyph_seed + i, 1, 6)[0]
            flat_glyph(g, xc, z_top - length * 0.45, w * 0.62, y - 0.012, mat="paint_glossy_white", w=0.09, t=0.003)


def ramen_stall():
    M = Meta()
    W, yF, yB = 3.5, -1.1, 1.1
    zf_bot, zf_top = 2.18, 2.4          # front fascia
    # ---- shell: back wall (corrugated outside, tiled inside), side walls over the kitchen half
    bw = box(W - 0.2, 0.06, 2.55, at=(0, yB - 0.05, 0), mat="corrugated", base=True)
    bw.set_mat("tile_grimy", where=lambda f: f.normal.y < -0.9)
    for sx in (-1, 1):
        sw = box(0.05, 1.05, 2.55, at=(sx * (W / 2 - 0.12), 0.55, 0), mat="metal_painted_red", base=True, bevel=0.006)
        if detail():
            for k in range(3):
                box(0.012, 1.02, 0.03, at=(sx * (W / 2 - 0.09), 0.55, 0.5 + k * 0.7), mat="metal_dark")
    for x in (-W / 2 + 0.12, W / 2 - 0.12):
        box(0.1, 0.1, zf_top, at=(x, -0.62, 0), mat="wood", base=True, bevel=0.01)
        box(0.18, 0.18, 0.04, at=(x, -0.62, 0), mat="metal_dark", base=True)
    # ---- roof: corrugated sheet on rafters, sloping to the front, fascia + warm LED under it
    slope = math.degrees(math.atan2(0.25, yB - yF))
    zr0 = zf_top
    for x in (-1.2, 0.0, 1.2):
        r = box(0.07, yB - yF + 0.1, 0.1, at=(x, (yF + yB) / 2, 0), mat="wood")
        r.rot(x=slope).move(0, 0, zr0 + 0.12)
    sheet = box(W + 0.1, yB - yF + 0.25, 0.03, at=(0, (yF + yB) / 2 - 0.05, 0), mat="corrugated")
    sheet.rot(x=slope).move(0, 0, zr0 + 0.2)
    box(W + 0.1, 0.05, zf_top - zf_bot, at=(0, yF + 0.02, zf_bot), mat="wood", base=True, bevel=0.008)
    for sx in (-1, 1):
        bb = box(0.04, yB - yF + 0.28, 0.12, mat="wood", bevel=0.006)
        bb.rot(x=slope).move(sx * (W / 2 + 0.07), -0.05, zr0 + 0.2)
    fl = box(W + 0.14, 0.12, 0.05, mat="metal_dark", bevel=0.006)
    fl.rot(x=slope).move(0, yB + 0.02, zr0 + 0.27 + 0.13)
    box(W - 0.2, 0.02, 0.02, at=(0, yF + 0.07, zf_bot + 0.01), mat="emit_strip_warm")
    for x in (-1.2, 0.0, 1.2):
        beam((x, -0.62, zf_bot - 0.02), (x, yF + 0.05, zf_bot - 0.02), 0.06, 0.08, mat="wood")
    box(W - 0.1, 0.08, 0.08, at=(0, -0.62, zf_bot - 0.06), mat="wood")
    for y in (-0.2, 0.55):   # warm tube lights under the roof (kitchen + counter glow)
        box(1.4, 0.05, 0.04, at=(0, y, 2.32 + (y + 0.2) * 0.1), mat="emit_panel_warm")
        box(1.45, 0.07, 0.02, at=(0, y, 2.355 + (y + 0.2) * 0.1), mat="metal_dark")
    # ---- customer counter: tiled front, wood top, raised pickup ledge
    cf = box(2.95, 0.42, 0.95, at=(0, -0.42, 0.06), mat="metal_dark", base=True, bevel=0.01)
    cf.set_mat("tile_grimy", where=lambda f: f.normal.y < -0.9)
    box(2.95, 0.4, 0.06, at=(0, -0.42, 0), mat="black", base=True)
    box(3.15, 0.66, 0.055, at=(0, -0.5, 1.01), mat="wood", base=True, bevel=0.012)
    box(2.95, 0.2, 0.045, at=(0, -0.3, 1.24), mat="wood", base=True, bevel=0.008)
    for x in (-1.3, -0.45, 0.45, 1.3):
        box(0.04, 0.04, 0.18, at=(x, -0.3, 1.065), mat="metal_dark", base=True)
    if detail():  # condiments, chopstick tubs, bowls on the counter
        for x in (-1.15, 0.2, 1.05):
            box(0.2, 0.1, 0.02, at=(x, -0.3, 1.285), mat="black", base=True)
            for k, m in enumerate(("paint_glossy_red", "car_paint_yellow", "black")):
                cyl(0.02, 0.1, 8, at=(x - 0.06 + k * 0.06, -0.3, 1.305), mat=m)
        for x in (-0.6, 0.85):
            cyl(0.045, 0.14, 10, at=(x, -0.3, 1.285), mat="wood")
            for k in range(5):
                cyl(0.004, 0.24, 4, at=(x - 0.02 + k * 0.01, -0.3 + (k % 2) * 0.01, 1.3), mat="wood")
        for x in (-0.95, 0.55):
            lathe([(0.001, 1.065), (0.05, 1.065), (0.085, 1.1), (0.095, 1.14), (0.088, 1.14), (0.001, 1.12)], 14, at=(x, -0.62, 0),
                  mat="paint_glossy_white")
    # ---- kitchen: back counter, stove + stock pots, hood + duct, shelf, menu lightbox
    bc = box(3.0, 0.55, 0.9, at=(0, 0.75, 0), mat="metal_bare", base=True, bevel=0.01)
    box(3.05, 0.6, 0.04, at=(0, 0.74, 0.9), mat="chrome_scratched", base=True, bevel=0.004)
    for x, r, h in ((-0.75, 0.22, 0.36), (-0.2, 0.17, 0.26)):
        cyl(r + 0.03, 0.08, 14, at=(x, 0.72, 0.94), mat="metal_dark")
        if detail():
            torus(r - 0.02, 0.01, n_major=14, n_minor=4, mat="emit_amber").move(x, 0.72, 1.0)
        lathe([(0.001, 1.02), (r, 1.02), (r + 0.01, 1.03), (r + 0.01, 1.02 + h), (r + 0.02, 1.03 + h), (r - 0.01, 1.03 + h),
               (r - 0.01, 1.03 + h - 0.08), (0.001, 1.03 + h - 0.08)], 18, at=(x, 0.72, 0), mat="metal_bare")
        if detail():
            for sx in (-1, 1):
                box(0.06, 0.02, 0.025, at=(x + sx * (r + 0.03), 0.72, 1.0 + h * 0.85), mat="metal_dark")
    lid = lathe([(0.001, 0.05), (0.18, 0.02), (0.23, 0.0), (0.001, 0.0)], 18, mat="chrome_scratched")
    lid.rot(x=-35).move(-0.75, 0.58, 1.45)
    hood = lathe([(0.42, 1.92), (0.25, 2.12), (0.12, 2.16), (0.001, 2.16)], 4, mat="chrome_scratched", start=math.pi / 4)
    hood.scale(1.0, 0.75, 1.0).move(-0.5, 0.72, 0)
    cyl(0.11, 0.9, 12, at=(-0.5, 0.72, 2.12), mat="chrome_scratched")
    cyl(0.17, 0.05, 12, at=(-0.5, 0.72, 3.02), mat="metal_dark")
    cyl(0.03, 0.08, 6, at=(-0.5, 0.72, 2.95), mat="metal_dark")
    box(1.2, 0.25, 0.03, at=(0.75, 0.95, 1.55), mat="wood", base=True)
    if detail():
        for k in range(7):
            m = ("glass_dark", "car_paint_red", "car_paint_yellow", "glass_dark", "wood", "car_paint_teal", "glass_dark")[k]
            lathe([(0.001, 0.0), (0.035, 0.0), (0.035, 0.16), (0.012, 0.21), (0.012, 0.25), (0.001, 0.25)], 8,
                  at=(0.25 + k * 0.15, 0.95, 1.58), mat=m)
        for k in range(4):  # bowl stack + ladle rail
            lathe([(0.001, 0.0), (0.06, 0.0), (0.1, 0.05), (0.105, 0.075), (0.098, 0.075), (0.001, 0.02)], 12,
                  at=(0.55, 0.62, 0.94 + k * 0.035), mat="paint_glossy_white")
        cyl(0.008, 1.1, 6, at=(-1.1, 1.02, 1.75), axis="X", mat="chrome_scratched")
        for k in range(4):
            x = -1.0 + k * 0.25
            tube([(x, 1.02, 1.75), (x, 1.0, 1.5), (x, 0.98, 1.4)], 0.006, 4, mat="chrome_scratched")
            cyl(0.045, 0.04, 8, at=(x, 0.98, 1.36), mat="chrome_scratched")
    mb = box(1.5, 0.06, 0.44, at=(0.75, yB - 0.11, 1.8), mat="metal_dark", base=True, bevel=0.008)
    mb.set_mat("emit_panel_warm", where=lambda f: f.normal.y < -0.9)
    with frame(M, x=0.75, y=yB - 0.141, z=2.02):
        gl = glyph_set(620, 10, 6)
        for r in range(2):
            for c in range(5):
                flat_glyph(gl[r * 5 + c], -0.52 + c * 0.26, 0.09 - r * 0.2, 0.15, 0.0, w=0.1, t=0.003)
    # ---- noren, lanterns, festoon bulbs
    _noren(-1.5, 1.5, zf_bot - 0.01, yF + 0.0, length=0.48, n=6, seed=11, glyph_seed=700)
    lan = [_lantern(sx * (W / 2 - 0.12), yF + 0.04, zf_bot, drop=0.12) for sx in (-1, 1)]
    if detail():
        pts = [(-1.4 + 2.8 * i / 12, -0.62, zf_bot - 0.14 - 0.08 * math.sin(math.pi * ((i % 4) / 4.0))) for i in range(13)]
        tube(pts, 0.004, 4, mat="black", caps=False)
        for q in pts[1:-1:2]:
            lathe([(0.001, 0.0), (0.025, -0.02), (0.03, -0.05), (0.02, -0.08), (0.001, -0.09)], 8, at=q, mat="emit_panel_warm")
    # ---- roof neon: bowl icon on a backer standing on the roof front
    with frame(M, x=0.0, y=yF + 0.12, z=zr0 + 0.45):
        N = Neon(M, -0.03, standoff=0.06)
        bowl, foot, noodle, chop, steam = _bowl_strokes(0.0, 0.0, 0.68)
        b = _plate(_rrect(1.1, 0.98, 0.1, cz=0.07), -0.03)
        N.run([bowl, foot], "magenta", fillet=0.025)
        N.run([noodle], "pink", fillet=0.015)
        N.run(chop, "yellow", fillet=0.02)
        N.run(steam, "cyan", fillet=0.015, spacing=0.3)
        for sx in (-1, 1):
            beam((sx * 0.4, 0.0, -0.47), (sx * 0.4, 0.0, 0.45), 0.05, 0.035, mat="metal_dark", up=(0, 1, 0))
            beam((sx * 0.4, 0.01, 0.15), (sx * 0.4, 0.55, -0.42), 0.035, 0.035, mat="metal_dark", up=(1, 0, 0))
        N.lights(ahead=0.5, order=["magenta", "cyan", "yellow", "pink"])
    # ---- stools, gas bottle, crate
    for x in (-1.05, -0.35, 0.35, 1.05):
        _stool(x, -0.98)
    lathe([(0.001, 0.0), (0.15, 0.0), (0.16, 0.03), (0.16, 0.55), (0.12, 0.65), (0.04, 0.68), (0.04, 0.75), (0.001, 0.76)], 14,
          at=(1.3, 0.3, 0), mat="metal_painted_white")
    if detail():
        box(0.5, 0.35, 0.3, at=(-1.2, 0.25, 0), mat="plastic_orange", base=True, bevel=0.015)
        for k in range(3):
            K.rock((0.12, 0.12, 0.1), 40 + k, cuts=6, mat="car_paint_teal").move(-1.32 + k * 0.12, 0.25, 0.32)
        tube([(1.3, 0.3, 0.76), (1.2, 0.5, 0.85), (-0.7, 0.6, 0.93)], 0.008, 4, mat="rubber")
    for p, sx in zip(lan, (-1, 1)):
        M.light(p, SLOT_HEX["emit_red"], rng=3.0, inten=0.9, slot="emit_red")
    M.light((0, -0.62, 1.95), SLOT_HEX["emit_panel_warm"], rng=5.0, inten=1.6, slot="emit_strip_warm")
    M.light((0.75, yB - 0.6, 2.0), SLOT_HEX["emit_panel_warm"], rng=3.0, inten=0.8, slot="emit_panel_warm")
    M.extra["steam"] = [[round(v, 3) for v in K.to_unity_vec((-0.75, 0.72, 1.45))], [round(v, 3) for v in K.to_unity_vec((-0.2, 0.72, 1.33))]]
    M.extra["seats"] = [[round(v, 3) for v in K.to_unity_vec((x, -0.98, 0.72))] for x in (-1.05, -0.35, 0.35, 1.05)]
    M.col((0, -0.45, 0.53), (3.15, 0.66, 1.06))
    M.col((0, 0.75, 0.47), (3.0, 0.6, 0.94))
    M.col((0, yB - 0.05, 1.27), (W - 0.2, 0.08, 2.55))
    for sx in (-1, 1):
        M.col((sx * (W / 2 - 0.12), 0.55, 1.27), (0.08, 1.05, 2.55))
        M.col((sx * (W / 2 - 0.12), -0.62, zf_top / 2), (0.12, 0.12, zf_top))
    M.col((0, 0.0, zr0 + 0.2), (W + 0.1, yB - yF + 0.2, 0.3))
    for x in (-1.05, -0.35, 0.35, 1.05):
        M.col((x, -0.98, 0.36), (0.36, 0.36, 0.72))
    return M.done(glow=HEX["magenta"])


_reg("Ramen_Stall", ramen_stall, zones=("plaza",), lods=3,
     notes="Noodle stall 3.68 x 3.41 x 2.48 m (roof sign top at 3.4 m) (customer side +Z): tiled counter with raised pickup ledge and 4 stools ('seats'), "
           "kitchen with stock pots ('steam' particle anchors), chrome hood and roof duct, bottle shelf, warm glyph menu "
           "lightbox, corrugated roof with warm LED fascia, indigo noren strips (tarp_blue, white invented glyphs), two red "
           "lanterns, festoon bulbs and a neon noodle-bowl sign on the roof. Base-centre pivot; back wall solid.")


def street_food_counter():
    M = Meta()
    W = 2.6
    cl = box(W, 0.04, 2.7, at=(0, -0.02, 0), mat=DARK, base=True)
    cl.set_mat("tile_grimy", where=lambda f: f.normal.y < -0.9)
    # service hatch: jambs, head, dark interior, warm strip, roller shutter box + guides
    zh0, zh1, xh = 1.05, 2.05, 0.95
    for sx in (-1, 1):
        box(0.1, 0.16, zh1 - zh0, at=(sx * xh, -0.12, zh0), mat="metal_dark", base=True, bevel=0.008)
        box(0.05, 0.05, zh1 - zh0, at=(sx * (xh - 0.03), -0.225, zh0), mat="metal_bare", base=True)
    box(2 * xh + 0.1, 0.16, 0.1, at=(0, -0.12, zh1), mat="metal_dark", base=True, bevel=0.008)
    box(2 * xh - 0.1, 0.01, zh1 - zh0, at=(0, -0.046, zh0), mat="black", base=True)
    box(2 * xh - 0.12, 0.1, 0.02, at=(0, -0.11, zh1 - 0.015), mat="emit_panel_warm")
    sb = box(2 * xh + 0.25, 0.26, 0.27, at=(0, -0.17, zh1 + 0.1), mat="metal_dark", base=True, bevel=0.012)
    sb.set_mat("corrugated", where=lambda f: f.normal.y < -0.9)
    if detail():  # kitchen silhouettes inside the hatch
        box(1.7, 0.06, 0.02, at=(0, -0.08, 1.5), mat="metal_bare", base=True)
        for x, r, h in ((-0.55, 0.11, 0.18), (-0.25, 0.08, 0.14), (0.4, 0.13, 0.12)):
            cyl(r, h, 12, at=(x, -0.11 + r * 0.3, 1.52), mat="metal_bare")
        for k in range(5):
            box(0.06, 0.004, 0.08, at=(-0.6 + k * 0.3, -0.05, 1.85), mat="paint_glossy_white")  # order slips
    # counter top on gussets, wall kick plate, foot rail
    box(2.3, 0.5, 0.05, at=(0, -0.29, zh0 - 0.05), mat="wood", base=True, bevel=0.01)
    box(2.3, 0.02, 0.06, at=(0, -0.545, zh0 - 0.055), mat="chrome_scratched", base=True)
    for x in (-1.0, 0.0, 1.0):
        extrude([(-0.04, zh0 - 0.05), (-0.04, zh0 - 0.42), (-0.44, zh0 - 0.05)], 0.02, plane="YZ", mat="metal_dark").move(x, 0, 0)
    kp = box(2.3, 0.02, 0.9, at=(0, -0.05, 0.05), mat="metal_plate", base=True, bevel=0.004)
    cyl(0.022, 2.2, 8, at=(-1.1, -0.3, 0.24), axis="X", mat="chrome_scratched")
    for x in (-0.9, 0.0, 0.9):
        box(0.03, 0.26, 0.03, at=(x, -0.18, 0.24), mat="metal_dark")
    if detail():  # counter items
        box(0.22, 0.12, 0.02, at=(-0.7, -0.35, zh0), mat="black", base=True)
        for k, m in enumerate(("paint_glossy_red", "car_paint_yellow", "black", "car_paint_teal")):
            cyl(0.022, 0.12, 8, at=(-0.78 + k * 0.055, -0.35, zh0 + 0.02), mat=m)
        box(0.14, 0.1, 0.09, at=(0.05, -0.3, zh0), mat="paint_glossy_white", base=True, bevel=0.01)
        for k in range(3):
            lathe([(0.001, 0.0), (0.035, 0.0), (0.045, 0.1), (0.04, 0.1), (0.001, 0.01)], 10, at=(0.6, -0.33, zh0 + k * 0.025),
                  mat="paint_glossy_white")
    # awning: corrugated sheet on struts, pink LED front edge, hanging price tags
    ya, za0, za1 = -1.0, 2.62, 2.45
    sl = math.degrees(math.atan2(za0 - za1, -ya))
    aw = box(W + 0.1, -ya + 0.05, 0.03, mat="corrugated")
    aw.rot(x=sl).move(0, ya / 2 - 0.02, (za0 + za1) / 2 + 0.02)
    box(W + 0.1, 0.05, 0.12, at=(0, ya, za1 - 0.04), mat="metal_dark", bevel=0.008)
    box(W, 0.02, 0.02, at=(0, ya - 0.03, za1 - 0.09), mat="emit_strip_pink")
    for sx in (-1, 1):
        beam((sx * 1.15, -0.04, 2.15), (sx * 1.15, ya + 0.08, za1 - 0.06), 0.05, 0.05, mat="metal_dark", up=(1, 0, 0))
        box(0.1, 0.012, 0.16, at=(sx * 1.15, -0.046, 2.15), mat="metal_dark")
    gl = glyph_set(810, 5, 6)
    for i, x in enumerate((-0.9, -0.45, 0.0, 0.45, 0.9)):
        if detail():
            tube([(x, ya, za1 - 0.1), (x, ya, za1 - 0.16)], 0.003, 4, mat="black")
        box(0.16, 0.012, 0.28, at=(x, ya, za1 - 0.3), mat="wood", bevel=0.004)
        with frame(M, x=x, y=ya - 0.007, z=za1 - 0.3):
            flat_glyph(gl[i], 0, 0.0, 0.13, 0.0, w=0.12, t=0.002)
    # vertical glyph lightboxes flanking the hatch
    for sx in (-1, 1):
        lb = box(0.34, 0.08, 0.95, at=(sx * 1.2, -0.08, zh0 + 0.02), mat="metal_dark", base=True, bevel=0.01)
        lb.set_mat("emit_panel_warm", where=lambda f: f.normal.y < -0.9)
        with frame(M, x=sx * 1.2, y=-0.121, z=zh0 + 0.02):
            for i, g in enumerate(glyph_set(830 + (sx > 0) * 5, 3, 6)):
                flat_glyph(g, 0, 0.78 - i * 0.29, 0.22, 0.0, w=0.1, t=0.003)
    # hanging cage lamp
    tube([(0, -0.55, 2.55), (0, -0.55, 2.25)], 0.004, 4, mat="black")
    lathe([(0.001, 2.25), (0.03, 2.25), (0.11, 2.15), (0.12, 2.13), (0.11, 2.13)], 12, at=(0, -0.55, 0), mat="metal_dark",
          close_bottom=False)
    lathe([(0.001, 2.2), (0.035, 2.17), (0.03, 2.12), (0.001, 2.1)], 10, at=(0, -0.55, 0), mat="emit_panel_warm")
    if detail():
        tube([(1.25, -0.04, 2.4), (1.25, -0.06, 2.0), (1.25, -0.08, 1.98)], 0.01, 6, mat="rubber")
    for x in (-0.75, 0.0, 0.75):
        _stool(x, -0.82, seat="paint_glossy_dark", h=0.72)
    M.light((0, -0.6, 1.7), SLOT_HEX["emit_panel_warm"], rng=3.5, inten=1.4, slot="emit_panel_warm")
    M.light((0, ya - 0.3, za1 - 0.1), HEX["pink"], rng=3.5, inten=1.0, slot="emit_strip_pink")
    M.light((0, -0.55, 2.05), SLOT_HEX["emit_panel_warm"], rng=3.0, inten=1.0, slot="emit_panel_warm")
    M.col((0, -0.02, 1.35), (W, 0.04, 2.7))
    M.col((0, -0.29, zh0 - 0.025), (2.3, 0.5, 0.05))
    M.col((0, -0.15, zh0 + 0.5), (2 * xh + 0.1, 0.2, zh1 - zh0 + 0.1))
    for x in (-0.75, 0.0, 0.75):
        M.col((x, -0.82, 0.38), (0.38, 0.38, 0.76))
    M.extra["seats"] = [[round(v, 3) for v in K.to_unity_vec((x, -0.82, 0.76))] for x in (-0.75, 0.0, 0.75)]
    return M.done(glow=SLOT_HEX["emit_panel_warm"])


def _face_panel(w, h, zc, mat, M, bezel="chrome_scratched", record=True):
    """Display panel on a face (sign space, face plane y=0): bezel frame + lit face."""
    box(w + 0.05, 0.025, h + 0.05, at=(0, -0.0125, zc), mat=bezel, bevel=0.006)
    p = box(w, 0.012, h, at=(0, -0.031, zc), mat=DARK)
    p.set_mat(mat, where=lambda f: f.normal.y < -0.9)
    if record:
        M.screen((0, -0.038, zc), (w, h), (0, -1, 0), mat)


def kiosk_neon():
    M = Meta()
    C, z0, z1 = 0.78, 0.2, 2.4
    box(1.0, 1.0, 0.18, mat="concrete_dark", base=True, bevel=0.03, bseg=2)
    box(0.9, 0.9, 0.025, at=(0, 0, 0.175), mat="chrome_scratched", base=True, bevel=0.004)
    box(C, C, z1 - z0, at=(0, 0, z0), mat=DARK, base=True, bevel=0.02, bseg=2)
    faces = [("front", dict(x=0, y=-C / 2, rz=0)), ("back", dict(x=0, y=C / 2, rz=180)),
             ("right", dict(x=C / 2, y=0, rz=90)), ("left", dict(x=-C / 2, y=0, rz=-90))]
    neon_col = {"front": "cyan", "back": "magenta", "right": "pink", "left": "violet"}
    for fid, kw in faces:
        with frame(M, **kw):
            if fid == "front":
                _face_panel(0.6, 0.86, 1.72, "screen", M)
                ld = box(0.6, 0.16, 0.04, at=(0, -0.08, 1.12), mat="metal_dark", bevel=0.006)
                ld.rot_about((0, 0, 1.12), x=-12)
                box(0.12, 0.05, 0.08, at=(0.18, -0.06, 1.18), mat="black", bevel=0.008)
                box(0.08, 0.004, 0.006, at=(0.18, -0.086, 1.2), mat="emit_green")
                if detail():
                    box(0.2, 0.006, 0.14, at=(-0.15, -0.003, 0.8), mat="grating")       # speaker
                    for i in range(3):
                        for j in range(3):
                            box(0.03, 0.01, 0.025, at=(-0.04 + j * 0.04, -0.07 - i * 0.008, 1.16 + i * 0.006), mat="metal_bare")
            elif fid == "left":
                lb = box(0.5, 0.03, 1.6, at=(0, -0.015, 1.35), mat="metal_dark", bevel=0.006)
                lb.set_mat("emit_panel_cyan", where=lambda f: f.normal.y < -0.9)
                for i, g in enumerate(glyph_set(905, 4, 6)):
                    flat_glyph(g, 0, 1.95 - i * 0.39, 0.3, -0.03, w=0.1, t=0.003)
            else:
                _face_panel(0.6, 1.5, 1.35, "screen_ad_a" if fid == "back" else "screen_ad_c", M)
            N = Neon(M, 0.0, standoff=0.05)
            N.run([S(_rrect(C - 0.08, z1 - z0 - 0.12, 0.05, cz=(z0 + z1) / 2), closed=True)], neon_col[fid], fillet=0.04, gap=0.05,
                  spacing=0.45)
            N.lights(ahead=0.5, rng=3.0, inten=1.0)
    # crown: glyph lightbox cube with cyan neon halo
    box(C + 0.08, C + 0.08, 0.08, at=(0, 0, z1), mat="metal_dark", base=True, bevel=0.012)
    cr = box(0.6, 0.6, 0.34, at=(0, 0, z1 + 0.08), mat="metal_dark", base=True, bevel=0.01)
    cr.set_mat("emit_panel_magenta", where=lambda f: abs(f.normal.z) < 0.1)
    for k, (fid, kw) in enumerate(faces):
        kw2 = dict(kw)
        kw2["x"] = kw["x"] * 0.6 / C
        kw2["y"] = kw["y"] * 0.6 / C
        with frame(M, **kw2):
            flat_glyph(glyph_set(950 + k, 1, 6)[0], 0, z1 + 0.25, 0.24, -0.001, w=0.11, t=0.003)
    box(0.66, 0.66, 0.04, at=(0, 0, z1 + 0.42), mat="metal_dark", base=True, bevel=0.008)
    halo = [(x, z) for x, z in _rrect(0.78, 0.78, 0.12)]
    pts, fl = _round([(x, y, z1 + 0.14) for x, y in halo], [True] * len(halo), 0.08, 0.02, closed=True)
    tube(pts, TUBE_R, 6, mat="emit_neon_cyan", closed=True)
    if detail():
        for sx in (-1, 1):
            for sy in (-1, 1):
                tube([(sx * 0.3, sy * 0.3, z1 + 0.14), (sx * 0.37, sy * 0.37, z1 + 0.14)], 0.0035, 4, mat="metal_bare", caps=False)
    M.light((0, -0.6, z1 + 0.25), HEX["magenta"], rng=4.0, inten=1.2, slot="emit_panel_magenta")
    M.lights.insert(0, M.lights.pop())
    M.col((0, 0, 0.09), (1.0, 1.0, 0.18))
    M.col((0, 0, (z0 + z1) / 2), (C + 0.1, C + 0.1, z1 - z0))
    M.col((0, 0, z1 + 0.23), (0.66, 0.66, 0.46))
    return M.done(glow=HEX["cyan"], single_screen=True)


_reg("Street_Food_Counter", street_food_counter, pivot="wall-back", zones=("plaza", "metro"),
     notes="Hole-in-the-wall food counter 2.74 x 2.7 x 1.1 m: tiled wall panel with a lit service hatch (kitchen "
           "silhouettes), roller-shutter box, wood counter on gussets, foot rail, corrugated awning with pink LED edge and "
           "hanging glyph price tags, two warm glyph lightboxes, cage lamp, 3 stools ('seats'). Pivot 'wall-back' = wall "
           "plane at floor level, centred: place it flush against any building wall at ground level.")
_reg("Kiosk_Neon", kiosk_neon, zones=("plaza", "metro"),
     notes="Free-standing info/ad kiosk 1.0 x 2.86 x 1.05 m: front 'screen' (0.6 x 0.86, info/RT) with card reader ledge, "
           "screen_ad_a back, screen_ad_c right (Unity -X), cyan glyph lightbox left; each face framed by a neon loop "
           "(cyan/magenta/pink/violet); magenta glyph crown with a cyan neon halo. Base-centre pivot.")
