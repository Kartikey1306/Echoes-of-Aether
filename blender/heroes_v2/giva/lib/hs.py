"""Hard-surface toolkit for Giva's gear: conforming plates on surface charts, straps, cables, bolts, buckles.

Every generator takes `hi` (bool): the same shape at game resolution (low) or bake resolution (high: denser
outline, more rim segments, detail heights displaced into the top surface, real bolts). Geometry is accumulated in
a Part (verts, quads/tris, per-face material slot, per-loop UVs, per-vertex attributes).
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
import gv


# ----------------------------------------------------------------------------- accumulation

class Part:
    def __init__(self, name):
        self.name = name
        self.V = []          # (3,)
        self.F = []          # tuples of vertex indices
        self.M = []          # material name per face
        self.UV = []         # per face: list of (u,v)
        self.attr = {}       # name -> list per vertex
        self.fattr = {}      # name -> list per face (material class id etc.)

    def add(self, verts, faces, mat, uvs=None, cls=0.0, attrs=None):
        off = len(self.V)
        self.npieces = getattr(self, "npieces", 0) + 1
        attrs = dict(attrs or {})
        attrs["pid"] = np.full(len(verts), float(self.npieces))
        self.V.extend([np.asarray(v, float) for v in verts])
        for k, f in enumerate(faces):
            self.F.append(tuple(off + i for i in f))
            self.M.append(mat)
            self.UV.append(uvs[k] if uvs is not None else [(0.0, 0.0)] * len(f))
            self.fattr.setdefault("cls", []).append(float(cls))
        n = len(verts)
        for k in set(self.attr) | set(attrs or {}):
            vals = (attrs or {}).get(k)
            self.attr.setdefault(k, [0.0] * off)
            self.attr[k].extend(list(vals) if vals is not None else [0.0] * n)
        return off

    def build(self, mat_order=None, smooth=True, auto_sharp=None):
        mats = mat_order or sorted(set(self.M), key=self.M.index)
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([tuple(v) for v in self.V], [], self.F)
        me.update()
        for m in mats:
            me.materials.append(bpy.data.materials.get(m) or bpy.data.materials.new(m))
        mi = np.array([mats.index(m) for m in self.M], dtype=np.int32)
        me.polygons.foreach_set("material_index", mi)
        uv = me.uv_layers.new(name="UVMap")
        flat = [c for f in self.UV for c in f]
        uv.data.foreach_set("uv", np.array(flat, dtype=np.float32).ravel())
        me.polygons.foreach_set("use_smooth", np.full(len(self.F), smooth))
        for k, vals in self.attr.items():
            a = me.attributes.new(k, "FLOAT", "POINT")
            a.data.foreach_set("value", np.array(vals, dtype=np.float32))
        for k, vals in self.fattr.items():
            a = me.attributes.new(k, "FLOAT", "FACE")
            a.data.foreach_set("value", np.array(vals, dtype=np.float32))
        bm = bmesh.new()
        bm.from_mesh(me)
        ng = [f for f in bm.faces if len(f.verts) > 4]
        if ng:
            bmesh.ops.triangulate(bm, faces=ng, quad_method="BEAUTY", ngon_method="BEAUTY")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(o)
        if auto_sharp:
            try:
                o.data.set_sharp_from_angle(angle=auto_sharp)
            except Exception:
                pass
        return o


# ----------------------------------------------------------------------------- reference surface

class Ref:
    """Reference surface (suit/garment rest meshes) for projecting gear."""

    @classmethod
    def from_arrays(cls, co, tris):
        r = cls.__new__(cls)
        r.co, r.tris = np.asarray(co, float), np.asarray(tris)
        r.tree = BVHTree.FromPolygons([Vector(c) for c in r.co], r.tris.tolist(), all_triangles=True)
        r.vn = gv.vertex_normals(r.co, r.tris)
        return r

    def __init__(self, objs):
        V, T = [], []
        off = 0
        for o in objs:
            co = gv.basis_co(o)
            t = gv.tri_index(o.data)
            V.append(co)
            T.append(t + off)
            off += len(co)
        self.co = np.concatenate(V)
        self.tris = np.concatenate(T)
        self.tree = BVHTree.FromPolygons([Vector(c) for c in self.co], self.tris.tolist(), all_triangles=True)
        self.vn = gv.vertex_normals(self.co, self.tris)

    def smooth_normal(self, fi, loc):
        t = self.tris[fi]
        w = gv._bary(np.array(loc), *self.co[t])
        return gv.nrm((self.vn[t] * w[:, None]).sum(0))

    def project(self, p, d, maxd=0.5):
        """Ray from p along d (both directions tried); returns (hit, smooth normal) or (None, None)."""
        p, d = Vector(p), Vector(d).normalized()
        best = None
        for s in (1, -1):
            loc, nrm, fi, dist = self.tree.ray_cast(p, d * s, maxd)
            if loc is not None and (best is None or dist < best[2]):
                best = (loc, fi, dist)
        if best is None:
            return None, None
        return np.array(best[0]), self.smooth_normal(best[1], best[0])

    def cast(self, p, d, maxd=0.5):
        """One-directional ray; (hit, smooth normal) or (None, None)."""
        loc, nrm, fi, dist = self.tree.ray_cast(Vector(p), Vector(d).normalized(), maxd)
        if loc is None:
            return None, None
        return np.array(loc), self.smooth_normal(fi, loc)

    def nearest(self, p, maxd=0.5):
        loc, nrm, fi, d = self.tree.find_nearest(Vector(p), maxd)
        if loc is None:
            return np.array(p), np.array((0, 0, 1.0))
        return np.array(loc), self.smooth_normal(fi, loc)


class TorsoChart:
    """Torso chart: u = metres around (arc at radius r0, 0 = front centre, + = character left), v = height (m);
    rays from the spine axis outward."""

    def __init__(self, ref, frames, r0=0.13):
        self.ref, self.Fr, self.r0 = ref, frames, r0

    def at(self, u, v):
        sp = self.Fr.spine
        cx = np.interp(v, sp[:, 2], sp[:, 0])
        cy = np.interp(v, sp[:, 2], sp[:, 1])
        phi = u / self.r0
        d = np.array((math.sin(phi), -math.cos(phi), 0.0))
        c = np.array((cx, cy, v))
        hit, n = self.ref.cast(c, d, 0.4)
        if hit is None:
            return c + d * self.r0, d
        return hit, n


class Chart:
    """2D chart on the reference: (u, v) metres in the plane (O, eu, ev), projected along -n0."""

    def __init__(self, ref, origin, normal, up, lift=0.25):
        self.ref = ref
        self.n0 = gv.nrm(normal)
        up = np.asarray(up, float)
        self.ev = gv.nrm(up - self.n0 * (up @ self.n0))
        self.eu = np.cross(self.ev, self.n0)
        self.O = np.asarray(origin, float)
        self.lift = lift

    def at(self, u, v):
        p = self.O + self.eu * u + self.ev * v
        hit, n = self.ref.cast(p + self.n0 * self.lift, -self.n0, self.lift + 0.09)
        if hit is None:
            return self.ref.nearest(p)
        return hit, n


class CylChart:
    """Cylindrical chart around a limb axis a->b: u = arc length around (m, at radius r0), v = metres along."""

    def __init__(self, ref, a, b, ref_dir, r0=0.05):
        self.ref = ref
        self.a = np.asarray(a, float)
        self.ax = gv.nrm(np.asarray(b, float) - self.a)
        rd = np.asarray(ref_dir, float)
        self.e0 = gv.nrm(rd - self.ax * (rd @ self.ax))
        self.e1 = np.cross(self.ax, self.e0)
        self.r0 = r0

    def at(self, u, v):
        phi = u / self.r0
        d = self.e0 * math.cos(phi) + self.e1 * math.sin(phi)
        c = self.a + self.ax * v
        hit, n = self.ref.cast(c, d, 0.25)
        if hit is None:
            return c + d * self.r0, d
        return hit, n


# ----------------------------------------------------------------------------- outlines

def superellipse(a, b, n=4.0, segs=48, rot=0.0, c=(0, 0)):
    t = np.linspace(0, 2 * math.pi, segs, endpoint=False)
    ct, st = np.cos(t), np.sin(t)
    x = a * np.sign(ct) * np.abs(ct) ** (2 / n)
    y = b * np.sign(st) * np.abs(st) ** (2 / n)
    cr, sr = math.cos(rot), math.sin(rot)
    return np.stack([c[0] + x * cr - y * sr, c[1] + x * sr + y * cr], 1)


def rounded_poly(pts, r, segs_per_corner=5):
    """Polygon (2D, CCW) with each corner filleted by radius r (or per-corner list)."""
    pts = np.asarray(pts, float)
    n = len(pts)
    rr = r if np.ndim(r) else [r] * n
    out = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        d0, d1 = gv.nrm(p0 - p1), gv.nrm(p2 - p1)
        ang = math.acos(np.clip(d0 @ d1, -1, 1))
        if rr[i] <= 0 or ang < 1e-3 or ang > math.pi - 1e-3:
            out.append(p1)
            continue
        t = rr[i] / math.tan(ang / 2)
        t = min(t, 0.45 * np.linalg.norm(p0 - p1), 0.45 * np.linalg.norm(p2 - p1))
        a, b = p1 + d0 * t, p1 + d1 * t
        bis = gv.nrm(d0 + d1)
        c = p1 + bis * (t / math.cos(ang / 2) if False else math.sqrt(t * t + (t * math.tan(ang / 2)) ** 2))
        # arc from a to b around c
        va, vb = a - c, b - c
        a0, a1 = math.atan2(va[1], va[0]), math.atan2(vb[1], vb[0])
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        R = np.linalg.norm(va)
        for k in range(segs_per_corner + 1):
            th = a0 + da * k / segs_per_corner
            out.append(c + R * np.array((math.cos(th), math.sin(th))))
    return np.array(out)


def resample(poly, n):
    """Uniform arc-length resampling of a closed 2D/3D polyline."""
    P_ = np.concatenate([poly, poly[:1]])
    seg = np.linalg.norm(np.diff(P_, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    u = np.linspace(0, s[-1], n, endpoint=False)
    return np.stack([np.interp(u, s, P_[:, k]) for k in range(P_.shape[1])], 1)


def poly_area(p):
    return 0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])


# ----------------------------------------------------------------------------- plates

def plate(part, chart, outline, gap=0.003, thick=0.004, crown=0.0, fillet=0.0018, hi=False, mat="Armor",
          height_fn=None, cls=0.0, rings=None, lip=True, attrs=None, ring_space=None):
    """Conforming shell plate. outline: (N,2) in chart metres (any orientation). Top surface = reference +
    normal * (gap + thick + crown * dome + height_fn(u, v)); filleted rim down to `gap`; short inward lip below.
    Returns (first vertex index, vertex count, top-surface vertex mask)."""
    if poly_area(outline) < 0:
        outline = outline[::-1]
    perim = float(np.linalg.norm(np.diff(np.concatenate([outline, outline[:1]]), axis=0), axis=1).sum())
    n = int(np.clip(perim / (0.0008 if hi else 0.0095), 20, 1400 if hi else 68))
    O2 = resample(outline, n)
    c2 = O2.mean(0)
    span = float(np.linalg.norm(O2 - c2, axis=1).max())
    K = rings or max(2, int(span / (ring_space or (0.0009 if hi else 0.012))))

    def top_h(u, v, s):
        h = gap + thick + crown * (1 - s * s)
        if height_fn is not None:
            h += height_fn(u, v)
        return h

    # outward 2D normals of the outline
    tang = np.roll(O2, -1, 0) - np.roll(O2, 1, 0)
    on2 = gv.nrm(np.stack([tang[:, 1], -tang[:, 0]], 1))
    # the top surface ends where the fillet starts: its outer ring is inset by `fillet`
    Otop = O2 - on2 * fillet
    verts, faces = [], []
    rings_idx = []
    for k in range(K):
        s = 1 - k / K
        ids = []
        for (u, v) in c2 + (Otop - c2) * s:
            p, nn = chart.at(u, v)
            verts.append(p + nn * top_h(u, v, s))
            ids.append(len(verts) - 1)
        rings_idx.append(ids)
    p, nn = chart.at(*c2)
    verts.append(p + nn * top_h(c2[0], c2[1], 0.0))
    cidx = len(verts) - 1
    for k in range(K - 1):
        a, b = rings_idx[k], rings_idx[k + 1]
        for i in range(n):
            j = (i + 1) % n
            faces.append((a[i], a[j], b[j], b[i]))
    last = rings_idx[-1]
    for i in range(n):
        faces.append((last[i], last[(i + 1) % n], cidx))
    ntop = len(verts)
    # rim rows: quarter-circle fillet then straight down to the gap
    segs = 6 if hi else 2
    rows = [rings_idx[0]]
    for k in range(1, segs + 1):
        th = (math.pi / 2) * k / segs
        ins = -fillet * (1 - math.sin(th))
        drop = -fillet * (1 - math.cos(th))
        ids = []
        for i in range(n):
            u, v = O2[i] + on2[i] * ins
            p, nn = chart.at(u, v)
            verts.append(p + nn * (top_h(u, v, 1.0) + drop))
            ids.append(len(verts) - 1)
        rows.append(ids)
    ids = []
    for i in range(n):
        u, v = O2[i]
        p, nn = chart.at(u, v)
        verts.append(p + nn * gap)
        ids.append(len(verts) - 1)
    rows.append(ids)
    if lip:
        ids = []
        for i in range(n):
            u, v = O2[i] - on2[i] * 0.0022
            p, nn = chart.at(u, v)
            verts.append(p + nn * (gap * 0.55))
            ids.append(len(verts) - 1)
        rows.append(ids)
    for r in range(len(rows) - 1):
        a, b = rows[r], rows[r + 1]
        for i in range(n):
            j = (i + 1) % n
            faces.append((a[i], a[j], b[j], b[i]))
    topmask = np.zeros(len(verts))
    topmask[:ntop] = 1
    at = dict(attrs or {})
    at["top"] = topmask
    at["plate"] = np.ones(len(verts))
    off = part.add(verts, faces, mat, None, cls, at)
    return off, len(verts)


# ----------------------------------------------------------------------------- straps / tubes / small parts

def frame_along(P_, N_):
    T = np.gradient(P_, axis=0)
    T = gv.nrm(T)
    N2 = gv.nrm(N_ - T * (N_ * T).sum(1, keepdims=True))
    B = np.cross(T, N2)
    return T, N2, B


def surface_path(ref, pts3d, n=40, push=0.0, smooth=3):
    """Catmull-Rom through 3D waypoints, every sample snapped onto the reference surface (+push along normal)."""
    W = np.asarray(pts3d, float)
    P_ = catmull(W, n)
    out, nor = [], []
    for p in P_:
        h, nn = ref.nearest(p)
        out.append(h)
        nor.append(nn)
    out, nor = np.array(out), np.array(nor)
    for _ in range(smooth):
        out[1:-1] = 0.5 * out[1:-1] + 0.25 * (out[:-2] + out[2:])
        nor[1:-1] = gv.nrm(0.5 * nor[1:-1] + 0.25 * (nor[:-2] + nor[2:]))
    for i, p in enumerate(out):
        h, nn = ref.nearest(p)
        out[i] = h
        nor[i] = gv.nrm(nor[i] * 0.5 + nn * 0.5)
    return out + nor * push, nor


def catmull(W, n, closed=False):
    W = np.asarray(W, float)
    if closed:
        W = np.concatenate([W[-1:], W, W[:2]])
    else:
        W = np.concatenate([W[:1] * 2 - W[1:2], W, W[-1:] * 2 - W[-2:-1]])
    segs = len(W) - 3
    out = []
    for i in range(segs):
        p0, p1, p2, p3 = W[i:i + 4]
        m = max(2, int(n / segs))
        for k in range(m):
            t = k / m
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    if not closed:
        out.append(W[-2])
    return np.array(out)


def strap(part, P_, N_, width, thick, mat, cls=1.0, hi=False, uv=(0.0, 0.0, 1.0), closed=False, edge_r=0.0012, attrs=None):
    """Webbing strap: rounded-edge band following P_ with surface normals N_ (rests on the surface)."""
    T, Nn, B = frame_along(P_, N_)
    if closed:
        T = gv.nrm(np.roll(P_, -1, 0) - np.roll(P_, 1, 0))
        Nn = gv.nrm(N_ - T * (N_ * T).sum(1, keepdims=True))
        B = np.cross(T, Nn)
    w = width / 2
    segs = 3 if hi else 1
    # cross-section (b, n): bottom-left -> top-left (round) -> top-right (round) -> bottom-right
    cs = [(-w, 0.0)]
    for k in range(segs + 1):
        th = (math.pi / 2) * k / segs
        cs.append((-w + edge_r * (1 - math.cos(th)), thick - edge_r + edge_r * math.sin(th)))
    for k in range(segs + 1):
        th = (math.pi / 2) * k / segs
        cs.append((w - edge_r + edge_r * math.sin(th), thick - edge_r * (1 - math.cos(th))))
    cs.append((w, 0.0))
    m = len(cs)
    n = len(P_)
    verts = []
    for i in range(n):
        for (b, h) in cs:
            verts.append(P_[i] + B[i] * b + Nn[i] * h)
    L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))])
    csl = np.concatenate([[0], np.cumsum([math.hypot(cs[j + 1][0] - cs[j][0], cs[j + 1][1] - cs[j][1]) for j in range(m - 1)])])
    u0, v0, sc = uv
    faces, uvs = [], []
    rng = n if closed else n - 1
    for i in range(rng):
        i2 = (i + 1) % n
        Li = L[i] if i < len(L) else L[-1]
        Li2 = L[i2] if i2 > 0 else L[-1] + np.linalg.norm(P_[0] - P_[-1])
        for j in range(m - 1):
            faces.append((i * m + j, i2 * m + j, i2 * m + j + 1, i * m + j + 1))
            uvs.append([(u0 + csl[j] * sc, v0 + Li * sc), (u0 + csl[j] * sc, v0 + Li2 * sc),
                        (u0 + csl[j + 1] * sc, v0 + Li2 * sc), (u0 + csl[j + 1] * sc, v0 + Li * sc)])
    if not closed:
        for end, rng_i in ((0, 0), (n - 1, n - 1)):
            ids = [rng_i * m + j for j in range(m)]
            if end == 0:
                ids = ids[::-1]
            faces.append(tuple(ids))
            uvs.append([(u0, v0)] * m)
    part.add(verts, faces, mat, uvs, cls, attrs)
    return L[-1]


def tube(part, P_, radius, mat, cls=2.0, hi=False, sides=None, uv=(0.0, 0.0, 1.0), caps=True, N_=None, attrs=None):
    sides = sides or (16 if hi else 6)
    T = gv.nrm(np.gradient(P_, axis=0))
    ref = N_ if N_ is not None else np.tile(np.array((0, 0, 1.0)), (len(P_), 1))
    N1 = gv.nrm(ref - T * (ref * T).sum(1, keepdims=True))
    B1 = np.cross(T, N1)
    verts = []
    r = np.broadcast_to(np.asarray(radius, float), (len(P_),))
    for i, p in enumerate(P_):
        for k in range(sides):
            a = 2 * math.pi * k / sides
            verts.append(p + (N1[i] * math.cos(a) + B1[i] * math.sin(a)) * r[i])
    L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))])
    u0, v0, sc = uv
    circ = 2 * math.pi * float(np.mean(r))
    faces, uvs = [], []
    for i in range(len(P_) - 1):
        for k in range(sides):
            k2 = (k + 1) % sides
            faces.append((i * sides + k, i * sides + k2, (i + 1) * sides + k2, (i + 1) * sides + k))
            uvs.append([(u0 + k / sides * circ * sc, v0 + L[i] * sc), (u0 + (k + 1) / sides * circ * sc, v0 + L[i] * sc),
                        (u0 + (k + 1) / sides * circ * sc, v0 + L[i + 1] * sc), (u0 + k / sides * circ * sc, v0 + L[i + 1] * sc)])
    if caps:
        n = len(P_)
        faces.append(tuple(range(sides))[::-1])
        uvs.append([(u0, v0)] * sides)
        faces.append(tuple((n - 1) * sides + k for k in range(sides)))
        uvs.append([(u0, v0)] * sides)
    part.add(verts, faces, mat, uvs, cls, attrs)


def frame(n, up):
    n = gv.nrm(n)
    up = np.asarray(up, float)
    u = gv.nrm(up - n * (up @ n))
    if np.linalg.norm(u) < 1e-6:
        u = gv.nrm(np.cross(n, (1, 0, 0)))
    r = np.cross(u, n)
    return r, u, n


def rbox(part, c, n, up, size, bevel=0.0015, mat="Metal", cls=3.0, hi=False, uv=(0.0, 0.0, 1.0), attrs=None):
    """Rounded box (bevelled cube) centred at c, axes (right, up, n), size (sx, sy, sz along n)."""
    r, u, nn = frame(n, up)
    sx, sy, sz = [s / 2 for s in size]
    seg = 2 if hi else 1
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * 2 * sx, v.co.y * 2 * sy, v.co.z * 2 * sz))
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=min(bevel, sx * 0.9, sy * 0.9, sz * 0.9), segments=seg, profile=0.5, affect="EDGES")
    M = np.stack([r, u, nn], 1)
    verts = [c + M @ np.array(v.co) for v in bm.verts]
    faces = [tuple(v.index for v in f.verts) for f in bm.faces]
    u0, v0, sc = uv
    uvs = []
    for f in bm.faces:
        uvs.append([(u0 + (v.co.x + sx) * sc, v0 + (v.co.y + sy + v.co.z) * sc) for v in f.verts])
    bm.free()
    part.add(verts, faces, mat, uvs, cls, attrs)


def cylinder(part, c, n, up, radius, height, mat="Metal", cls=3.0, hi=False, sides=None, bevel=0.0006, uv=(0, 0, 1.0),
             r_top=None, attrs=None):
    """Capped cylinder standing on c along n (optionally tapered), with a small bevel ring at the top."""
    sides = sides or (32 if hi else 12)
    r_, u_, nn = frame(n, up)
    rt = r_top if r_top is not None else radius
    rings = [(0.0, radius), (height - bevel, rt), (height, rt - bevel)]
    verts = []
    for h, rr in rings:
        for k in range(sides):
            a = 2 * math.pi * k / sides
            verts.append(c + nn * h + (r_ * math.cos(a) + u_ * math.sin(a)) * rr)
    faces, uvs = [], []
    u0, v0, sc = uv
    for j in range(len(rings) - 1):
        for k in range(sides):
            k2 = (k + 1) % sides
            faces.append((j * sides + k, j * sides + k2, (j + 1) * sides + k2, (j + 1) * sides + k))
            uvs.append([(u0 + k / sides * sc * 0.02, v0 + j * sc * 0.002)] * 4)
    top = [(len(rings) - 1) * sides + k for k in range(sides)]
    faces.append(tuple(top))
    uvs.append([(u0 + 0.01 * sc + math.cos(2 * math.pi * k / sides) * rt * sc, v0 + 0.01 * sc + math.sin(2 * math.pi * k / sides) * rt * sc) for k in range(sides)])
    part.add(verts, faces, mat, uvs, cls, attrs)


def bolt(part, p, n, up, radius=0.0022, height=0.0012, hi=False, mat="Metal", cls=3.0, uv=(0.0, 0.0, 1.0)):
    """Hex socket cap screw head (low: 6-sided, high: rounded hex + socket)."""
    cylinder(part, p - gv.nrm(n) * 0.0004, n, up, radius, height, mat, cls, hi, sides=6 if not hi else 24, bevel=0.0004, uv=uv)


class SphChart:
    """Chart on a sphere around centre c: (u, v) metres at radius r0 from the pole direction e0 (u towards e1,
    v towards e2); rays shot inward onto the reference."""

    def __init__(self, ref, c, pole, toward_v, r0=0.08):
        self.ref = ref
        self.c = np.asarray(c, float)
        self.e0 = gv.nrm(pole)
        tv = np.asarray(toward_v, float)
        self.e2 = gv.nrm(tv - self.e0 * (tv @ self.e0))
        self.e1 = np.cross(self.e2, self.e0)
        self.r0 = r0

    def dir(self, u, v):
        a, b = u / self.r0, v / self.r0
        d = self.e0 * math.cos(math.hypot(a, b)) + (self.e1 * a + self.e2 * b) * (math.sin(math.hypot(a, b)) / max(math.hypot(a, b), 1e-9))
        return gv.nrm(d)

    def at(self, u, v):
        d = self.dir(u, v)
        hit, n = self.ref.cast(self.c, d, 0.3)
        if hit is None:
            return self.c + d * self.r0, d
        return hit, n


def rigid_weights_from(obj, src_objs, pts, top=3):
    """Same weights on every vertex of obj: average of the source surfaces' weights near `pts` (top bones)."""
    acc = {}
    for s in src_objs:
        names, W = gv.bone_weights(s)
        if not names:
            continue
        co = gv.basis_co(s)
        tris = gv.tri_index(s.data)
        b = gv.Binding(co, tris, np.asarray(pts), 0.2)
        w = b.transfer(W)
        ok = b.D < 0.05
        if ok.sum() == 0:
            continue
        m = w[ok].mean(0)
        for n_, v in zip(names, m):
            acc[n_] = acc.get(n_, 0) + v
    items = sorted(acc.items(), key=lambda x: -x[1])[:top]
    tot = sum(v for _, v in items)
    pairs = [(n_, v / tot) for n_, v in items if v / tot > 0.04]
    tot = sum(v for _, v in pairs)
    pairs = [(n_, v / tot) for n_, v in pairs]
    gv.rigid_weights(obj, pairs)
    return pairs
