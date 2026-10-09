"""envkit: shared helper library for the Aether-9 environment asset pipeline (Blender 5.2, headless).

Conventions (Blender side; FBX export converts to Unity):
  * metres, Z up. Assets are built with the pivot at the BASE CENTRE (0,0,0) unless documented otherwise.
  * The asset's FRONT faces Blender -Y, which becomes Unity +Z with the export axis settings
    (axis_forward='-Z', axis_up='Y', bake_space_transform=True). Blender +X -> Unity -X, Blender +Z -> Unity +Y.
  * UV0 is in METRES for tiling materials (box projection; cylinders/lathes/tori get their own unwrap), so
    a Unity material's tiling = 1 / tile_size_m. 'fit' materials get 0..1 per face; 'strip' materials get
    U = metres along the long axis, V = 0..1 across.
  * Material slot names == material names in matdefs.REGISTRY.
  * Builders take a `lod` argument through the module global LOD (0, 1 or 2); primitives reduce segment counts,
    drop bevels and builders skip `detail()` parts at LOD1+. LOD2 is only generated for assets whose LOD0 exceeds
    LOD2_THRESHOLD tris (or that ask for it with lods=3); builders may test `K.LOD >= 2` for a massing-only version.
  * `placed(matrix_or_offset)` is a context manager that transforms every part created inside it, so module
    builders can be instanced into larger assemblies (buildings) in asset space.
"""
import json
import math
import os
import random

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

import envpaths
import matdefs

LOD = 0
_parts = []
UVM_BOX, UVM_KEEP = 0, 1


# ============================================================================================== scene
def reset():
    global _parts
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _parts = []


def set_lod(l):
    global LOD
    LOD = l


def seg(n, minimum=4):
    """Segment count for the current LOD."""
    return max(minimum, n if LOD == 0 else int(round(n * (0.5 if LOD == 1 else 0.3))))


def detail():
    """True when small detail parts should be built (LOD0 only)."""
    return LOD == 0


# ============================================================================================== materials
def material(name):
    """Get/create the (untextured) export material for a registry name."""
    if name not in matdefs.REGISTRY:
        raise KeyError(f"unknown material '{name}'")
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        c = matdefs.preview_color(name)
        m.diffuse_color = (c[0], c[1], c[2], 1.0)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
    return m


# ============================================================================================== parts
class Part:
    """A piece of geometry in asset space. Geometry is created in local space, then transformed in place."""

    def __init__(self, bm, mat, name="part"):
        self.bm = bm
        self.mat = mat
        self.name = name
        self.uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
        self.uvm = bm.faces.layers.int.get("uvm") or bm.faces.layers.int.new("uvm")
        self.mats = bm.faces.layers.int.get("mslot") or bm.faces.layers.int.new("mslot")
        self.matnames = [mat]
        _parts.append(self)

    # --- transforms
    def xform(self, m):
        bmesh.ops.transform(self.bm, matrix=m, verts=self.bm.verts)
        return self

    def move(self, x=0.0, y=0.0, z=0.0):
        return self.xform(Matrix.Translation((x, y, z)))

    def rot(self, x=0.0, y=0.0, z=0.0, order="XYZ"):
        """Rotate by Euler angles in DEGREES about the asset origin."""
        return self.xform(Euler((math.radians(x), math.radians(y), math.radians(z)), order).to_matrix().to_4x4())

    def rot_about(self, pivot, x=0.0, y=0.0, z=0.0):
        p = Vector(pivot)
        m = Matrix.Translation(p) @ Euler((math.radians(x), math.radians(y), math.radians(z))).to_matrix().to_4x4() @ Matrix.Translation(-p)
        return self.xform(m)

    def scale(self, x=1.0, y=1.0, z=1.0):
        bmesh.ops.scale(self.bm, vec=(x, y, z), verts=self.bm.verts)
        if x * y * z < 0:
            bmesh.ops.reverse_faces(self.bm, faces=self.bm.faces)
        return self

    def copy(self):
        bm2 = self.bm.copy()
        p = Part(bm2, self.mat, self.name)
        p.matnames = list(self.matnames)
        return p

    def mirror(self, axis="x"):
        s = {"x": (-1, 1, 1), "y": (1, -1, 1), "z": (1, 1, -1)}[axis]
        return self.scale(*s)

    # --- materials
    def slot(self, matname):
        if matname not in self.matnames:
            self.matnames.append(matname)
        return self.matnames.index(matname)

    def set_mat(self, matname, faces=None, where=None):
        """Assign a material to `faces` or to faces for which where(face) is True."""
        i = self.slot(matname)
        fs = faces if faces is not None else [f for f in self.bm.faces if where is None or where(f)]
        for f in fs:
            f[self.mats] = i
        return self

    # --- modelling
    def bevel(self, width, segments=1, angle=30.0, edges=None, profile=0.5):
        if LOD > 0 or width <= 0:
            return self
        bm = self.bm
        if edges is None:
            lim = math.radians(angle)
            edges = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0) > lim]
        if edges:
            bmesh.ops.bevel(bm, geom=edges, offset=width, offset_type="OFFSET", segments=segments, profile=profile,
                            affect="EDGES", clamp_overlap=True, loop_slide=True)
        return self

    def displace(self, fn):
        for v in self.bm.verts:
            v.co = Vector(fn(v.co.copy()))
        return self

    def bounds(self):
        a = np.array([v.co[:] for v in self.bm.verts])
        return a.min(0), a.max(0)

    def tri_count(self):
        return sum(len(f.verts) - 2 for f in self.bm.faces)

    def delete(self):
        if self in _parts:
            _parts.remove(self)
        self.bm.free()


def ground(parts=None, target=0.0):
    """Shift parts (default: all built so far) so their lowest point sits at z=target."""
    parts = _parts if parts is None else parts
    mn = min(v.co.z for p in parts for v in p.bm.verts)
    for p in parts:
        p.move(0, 0, target - mn)
    return target - mn


class placed:
    """Context manager: every Part created inside is transformed by `m` on exit.
    m: 4x4 Matrix, or a dict(x=, y=, z=, rz=, sx=) (rz degrees about Z, sx=-1 mirrors X)."""

    def __init__(self, m=None, **kw):
        if m is None:
            sx = kw.get("sx", 1.0)
            m = Matrix.Translation((kw.get("x", 0.0), kw.get("y", 0.0), kw.get("z", 0.0))) @ \
                Euler((0.0, 0.0, math.radians(kw.get("rz", 0.0)))).to_matrix().to_4x4() @ \
                Matrix.Diagonal((sx, 1.0, 1.0, 1.0))
        self.m = m

    def __enter__(self):
        self.n0 = len(_parts)
        return self

    def __exit__(self, *exc):
        if exc[0] is not None:
            return False
        flip = self.m.to_3x3().determinant() < 0
        for p in _parts[self.n0:]:
            p.xform(self.m)
            if flip:
                bmesh.ops.reverse_faces(p.bm, faces=p.bm.faces)
        return False


def parts_since(n0):
    return _parts[n0:]


def part_count():
    return len(_parts)


def _new(mat, name="part"):
    return Part(bmesh.new(), mat, name)


def _faces_mode(part, faces, mode):
    for f in faces:
        f[part.uvm] = mode


# ---------------------------------------------------------------------------------------------- primitives
def box(sx, sy, sz, at=(0, 0, 0), mat="concrete", bevel=0.0, bseg=1, base=False, name="box"):
    """Axis aligned box of size (sx,sy,sz). `at` is the centre (or bottom centre if base=True)."""
    p = _new(mat, name)
    bmesh.ops.create_cube(p.bm, size=1.0)
    bmesh.ops.scale(p.bm, vec=(sx, sy, sz), verts=p.bm.verts)
    if bevel:
        p.bevel(min(bevel, min(sx, sy, sz) * 0.45), bseg)
    x, y, z = at
    p.move(x, y, z + (sz / 2 if base else 0))
    return p


def _ring_verts(bm, r, n, z, start=0.0, rx=None):
    rx = r if rx is None else rx
    return [bm.verts.new((rx * math.cos(start + i * math.tau / n), r * math.sin(start + i * math.tau / n), z)) for i in range(n)]


def cyl(r, h, n=16, at=(0, 0, 0), mat="metal_bare", r2=None, caps=True, center=False, axis="Z", name="cyl", start=None, bevel=0.0):
    """Cylinder/cone along +axis from the base at `at` (or centred if center=True). UVs: metres around/along."""
    p = _new(mat, name)
    bm = p.bm
    n = seg(n, 6)
    r2 = r if r2 is None else r2
    st = (math.pi / n) if start is None else start
    lo = _ring_verts(bm, r, n, 0.0, st)
    hi = _ring_verts(bm, r2, n, h, st)
    rm = max(r, r2)
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
        for l, (uu, vv) in zip(f.loops, ((i, 0.0), (i + 1, 0.0), (i + 1, h), (i, h))):
            l[p.uvl].uv = (uu / n * math.tau * rm, vv)
    caps_f = []
    if caps:
        caps_f.append(bm.faces.new(list(reversed(lo))))
        caps_f.append(bm.faces.new(hi))
        for f in caps_f:
            for l in f.loops:
                l[p.uvl].uv = (l.vert.co.x, l.vert.co.y)
    _faces_mode(p, bm.faces, UVM_KEEP)
    if bevel and caps:
        p.bevel(bevel, 1, angle=50)
    if center:
        p.move(0, 0, -h / 2)
    if axis == "X":
        p.rot(y=90)
    elif axis == "Y":
        p.rot(x=-90)
    p.move(*at)
    return p


def lathe(profile, n=16, at=(0, 0, 0), mat="metal_bare", name="lathe", close_bottom=True, close_top=True, start=None):
    """Revolve [(r, z), ...] (bottom to top) around Z. r=0 points become poles."""
    p = _new(mat, name)
    bm = p.bm
    n = seg(n, 6)
    st = (math.pi / n) if start is None else start
    rings = []
    vlen = [0.0]
    for k in range(1, len(profile)):
        (r0, z0), (r1, z1) = profile[k - 1], profile[k]
        vlen.append(vlen[-1] + math.hypot(r1 - r0, z1 - z0))
    rm = max(r for r, _ in profile)
    for (r, z) in profile:
        rings.append(_ring_verts(bm, max(r, 1e-5), n, z, st))
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            f = bm.faces.new((a[i], a[j], b[j], b[i]))
            for l, (kk, ii) in zip(f.loops, ((k, i), (k, i + 1), (k + 1, i + 1), (k + 1, i))):
                l[p.uvl].uv = (ii / n * math.tau * rm, vlen[kk])
    if close_bottom and profile[0][0] > 1e-4:
        f = bm.faces.new(list(reversed(rings[0])))
        for l in f.loops:
            l[p.uvl].uv = (l.vert.co.x, l.vert.co.y)
    if close_top and profile[-1][0] > 1e-4:
        f = bm.faces.new(rings[-1])
        for l in f.loops:
            l[p.uvl].uv = (l.vert.co.x, l.vert.co.y)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    _faces_mode(p, bm.faces, UVM_KEEP)
    p.move(*at)
    return p


def extrude(poly, depth, plane="XZ", at=(0, 0, 0), mat="concrete", name="extrude", bevel=0.0, bseg=1):
    """Extrude a 2D polygon (CCW) lying in `plane` symmetrically along the plane normal by `depth`.
    plane 'XZ': points are (x, z), extruded along Y.  'YZ': (y, z) along X.  'XY': (x, y) along Z (from 0 up)."""
    p = _new(mat, name)
    bm = p.bm
    if plane == "XZ":
        vs = [bm.verts.new((a, -depth / 2, b)) for a, b in poly]
        dvec = (0, depth, 0)
    elif plane == "YZ":
        vs = [bm.verts.new((-depth / 2, a, b)) for a, b in poly]
        dvec = (depth, 0, 0)
    else:
        vs = [bm.verts.new((a, b, 0)) for a, b in poly]
        dvec = (0, 0, depth)
    f = bm.faces.new(vs)
    bm.normal_update()
    res = bmesh.ops.extrude_face_region(bm, geom=[f])
    nv = [e for e in res["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=dvec, verts=nv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bevel:
        p.bevel(bevel, bseg)
    p.move(*at)
    return p


def tube(points, r, n=8, mat="metal_rusted", name="tube", closed=False, caps=True, radii=None):
    """Sweep a circle along a polyline. UVs: metres around / along."""
    p = _new(mat, name)
    bm = p.bm
    n = seg(n, 4)
    pts = [Vector(q) for q in points]
    m = len(pts)
    rings = []
    along = [0.0]
    for i in range(1, m):
        along.append(along[-1] + (pts[i] - pts[i - 1]).length)
    if closed:
        along.append(along[-1] + (pts[0] - pts[-1]).length)
    prev_side = None
    for i, c in enumerate(pts):
        if closed:
            t = (pts[(i + 1) % m] - c).normalized() + (c - pts[i - 1]).normalized()
        elif i == 0:
            t = pts[1] - pts[0]
        elif i == m - 1:
            t = pts[-1] - pts[-2]
        else:
            t = (pts[i + 1] - pts[i]).normalized() + (pts[i] - pts[i - 1]).normalized()
        t.normalize()
        if prev_side is None:
            up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
            side = t.cross(up).normalized()
        else:
            side = (prev_side - t * prev_side.dot(t)).normalized()
        prev_side = side
        up2 = side.cross(t).normalized()
        rr = r if radii is None else radii[i]
        rings.append([bm.verts.new(c + (side * math.cos(k * math.tau / n) + up2 * math.sin(k * math.tau / n)) * rr) for k in range(n)])
    segs = [(i, i + 1) for i in range(m - 1)] + ([(m - 1, 0)] if closed else [])
    for si, (i0, i1) in enumerate(segs):
        a, b = rings[i0], rings[i1]
        va, vb = along[si], along[si + 1]
        for k in range(n):
            j = (k + 1) % n
            f = bm.faces.new((a[k], a[j], b[j], b[k]))
            for l, (vv, kk) in zip(f.loops, ((va, k), (va, k + 1), (vb, k + 1), (vb, k))):
                l[p.uvl].uv = (kk / n * math.tau * r, vv)
    if caps and not closed:
        for ring, rev in ((rings[0], True), (rings[-1], False)):
            f = bm.faces.new(list(reversed(ring)) if rev else ring)
            for l in f.loops:
                l[p.uvl].uv = (l.vert.co.x, l.vert.co.y)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    _faces_mode(p, bm.faces, UVM_KEEP)
    return p


def torus(R, r, arc=360.0, n_major=32, n_minor=8, mat="metal_bare", name="torus", caps=True, start=0.0):
    """Torus (or arc) in the XY plane around Z, starting at angle `start` (deg) and sweeping `arc` deg."""
    full = arc >= 359.99
    nm = seg(n_major, min(8, n_major))
    cnt = nm if full else nm + 1
    pts = [(R * math.cos(math.radians(start + arc * i / nm)), R * math.sin(math.radians(start + arc * i / nm)), 0.0) for i in range(cnt)]
    return tube(pts, r, n_minor, mat, name, closed=full, caps=caps and not full)


def beam(a, b, w, h=None, mat="metal_dark", name="beam", up=(0, 0, 1), bevel=0.0):
    """Rectangular beam from point a to b, cross-section w x h (h defaults to w)."""
    h = w if h is None else h
    a, b = Vector(a), Vector(b)
    d = b - a
    L = d.length
    p = box(w, h, L, mat=mat, name=name, bevel=bevel)
    z = d.normalized()
    upv = Vector(up)
    if abs(z.dot(upv)) > 0.99:
        upv = Vector((1, 0, 0))
    x = upv.cross(z).normalized()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    p.xform(m)
    p.move(*((a + b) / 2))
    return p


def plane(sx, sy, at=(0, 0, 0), mat="concrete", nx=1, ny=1, name="plane"):
    p = _new(mat, name)
    bmesh.ops.create_grid(p.bm, x_segments=nx, y_segments=ny, size=0.5)
    bmesh.ops.scale(p.bm, vec=(sx, sy, 1), verts=p.bm.verts)
    p.move(*at)
    return p


def rock(size, seed, cuts=14, at=(0, 0, 0), mat="concrete", name="rock", rough=0.0, flat=0.6, bevel=0.06):
    """Angular broken chunk: convex hull of random points near the surface of a (sx,sy,sz) box.
    Always closed/manifold, so it is safe as a boolean cutter."""
    rnd = random.Random(seed)
    sx, sy, sz = size
    n = seg(cuts + 8, 9)
    p = _new(mat, name)
    bm = p.bm
    vs = []
    for i in range(n):
        v = [rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)]
        k = max(range(3), key=lambda a: abs(v[a]))
        v[k] = math.copysign(rnd.uniform(0.72, 1.0), v[k])
        vs.append(bm.verts.new((v[0] * sx / 2, v[1] * sy / 2, v[2] * sz / 2)))
    res = bmesh.ops.convex_hull(bm, input=vs)
    junk = list({g for g in res["geom_interior"] + res["geom_unused"] if isinstance(g, bmesh.types.BMVert)})
    if junk:
        bmesh.ops.delete(bm, geom=junk, context="VERTS")
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(4), verts=bm.verts, edges=bm.edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    cen = sum((v.co for v in bm.verts), Vector()) / max(1, len(bm.verts))
    if sum((f.calc_center_median() - cen).dot(f.normal) * f.calc_area() for f in bm.faces) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    if rough > 0 and LOD == 0:
        for v in bm.verts:
            v.co += Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * rough * min(sx, sy, sz)
    if bevel > 0 and LOD == 0:
        p.bevel(bevel * min(sx, sy, sz), 1, angle=20)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    p.move(*at)
    return p


def loft(sections, mat="concrete", cap_start=True, cap_end=True, face_mat=None, name="loft"):
    """Skin closed cross-section loops (equal point counts) into a surface. face_mat(i, k) -> material or None
    for the quad between section i..i+1 and points k..k+1."""
    p = _new(mat, name)
    bm = p.bm
    K = len(sections[0])
    rings = [[bm.verts.new(c) for c in sec] for sec in sections]
    for i in range(len(rings) - 1):
        for k in range(K):
            f = bm.faces.new((rings[i][k], rings[i][(k + 1) % K], rings[i + 1][(k + 1) % K], rings[i + 1][k]))
            if face_mat:
                m = face_mat(i, k)
                if m:
                    f[p.mats] = p.slot(m)
    caps = []
    if cap_start:
        caps.append(bm.faces.new(list(reversed(rings[0]))))
    if cap_end:
        caps.append(bm.faces.new(rings[-1]))
    if caps:
        bmesh.ops.triangulate(bm, faces=caps, quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return p


def rounded_section(hwb, hwt, zb, zt, rb, rt, n_flat=2, n_arc=3, n_side=4, bulge=0.0, y=0.0):
    """Closed (x,z) loop of a rounded trapezoid at station y, structured so that point indices mean the same
    feature on every station. Returns (points3d, index_map) where index_map gives the k ranges of
    'bottom', 'side_r', 'top', 'side_l' (faces k..k+1)."""
    h = max(zt - zb, 1e-3)
    rb = min(rb, h * 0.45, hwb * 0.9)
    rt = min(rt, h * 0.45, hwt * 0.9)
    pts = []
    idx = {}

    def arc(cx, cz, r, a0, a1, n, incl_end=False):
        m = n + (1 if incl_end else 0)
        return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * t / n)), cz + r * math.sin(math.radians(a0 + (a1 - a0) * t / n))) for t in range(m)]

    # bottom flat (centre -> right)
    for t in range(n_flat):
        pts.append(((hwb - rb) * t / n_flat, zb))
    idx["bottom_r"] = (0, len(pts))
    pts += arc(hwb - rb, zb + rb, rb, -90, 0, n_arc)
    s0 = len(pts)
    for t in range(n_side):
        f = t / n_side
        x = hwb + (hwt - hwb) * f + bulge * math.sin(math.pi * f)
        pts.append((x, zb + rb + (h - rb - rt) * f))
    idx["side_r"] = (s0, len(pts))
    a0 = len(pts)
    pts += arc(hwt - rt, zt - rt, rt, 0, 90, n_arc)
    idx["arc_tr"] = (a0, len(pts))
    t0 = len(pts)
    for t in range(2 * n_flat):
        pts.append(((hwt - rt) * (1 - t / n_flat), zt))
    idx["top"] = (t0, len(pts))
    a1 = len(pts)
    pts += arc(-(hwt - rt), zt - rt, rt, 90, 180, n_arc)
    idx["arc_tl"] = (a1, len(pts))
    s1 = len(pts)
    for t in range(n_side):
        f = t / n_side
        x = -(hwt + (hwb - hwt) * f + bulge * math.sin(math.pi * (1 - f)))
        pts.append((x, zt - rt - (h - rb - rt) * f))
    idx["side_l"] = (s1, len(pts))
    pts += arc(-(hwb - rb), zb + rb, rb, 180, 270, n_arc)
    for t in range(n_flat):
        pts.append((-(hwb - rb) * (1 - t / n_flat), zb))
    return [(x, y, z) for x, z in pts], idx


def boolean(part, cutter, op="DIFFERENCE", solver="MANIFOLD"):
    """Boolean `cutter` into `part` (both Parts). Cutter faces keep their material and get box UVs."""
    for f in cutter.bm.faces:
        f[cutter.mats] = part.slot(cutter.matnames[f[cutter.mats]])
        f[cutter.uvm] = UVM_BOX
    tmp = []
    for pp in (part, cutter):
        me = bpy.data.meshes.new("__bool")
        pp.bm.to_mesh(me)
        ob = bpy.data.objects.new("__bool", me)
        bpy.context.scene.collection.objects.link(ob)
        tmp.append(ob)
    a, b = tmp
    for sv in (solver, "EXACT"):
        mod = a.modifiers.new("b", "BOOLEAN")
        mod.object = b
        mod.operation = op
        mod.solver = sv
        with bpy.context.temp_override(object=a, active_object=a):
            bpy.ops.object.modifier_apply(modifier=mod.name)
        if len(a.data.polygons) or op == "INTERSECT":
            break
        a.data.clear_geometry()
        part.bm.to_mesh(a.data)
    part.bm.clear()
    part.bm.from_mesh(a.data)
    part.uvl = part.bm.loops.layers.uv.get("UVMap")
    part.uvm = part.bm.faces.layers.int.get("uvm") or part.bm.faces.layers.int.new("uvm")
    part.mats = part.bm.faces.layers.int.get("mslot") or part.bm.faces.layers.int.new("mslot")
    for ob in tmp:
        me = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
    cutter.delete()
    return part


# ---------------------------------------------------------------------------------------------- face ops
def faces_where(part, fn):
    return [f for f in part.bm.faces if fn(f)]


def inset(part, faces, thickness, depth=0.0, mat=None, individual=True):
    """Inset faces; the new inner faces get `mat` (if given) and are pushed by depth along their normal.
    Returns the inner faces."""
    bm = part.bm
    bm.normal_update()
    faces = [f for f in faces if f.is_valid and _min_extent(f) > 2.5 * thickness]
    if not faces:
        return faces
    if individual:
        res = bmesh.ops.inset_individual(bm, faces=faces, thickness=thickness, depth=depth, use_even_offset=True)
    else:
        res = bmesh.ops.inset_region(bm, faces=faces, thickness=thickness, depth=depth, use_even_offset=True)
    if mat:
        part.set_mat(mat, faces=faces)
    return faces


def _min_extent(f):
    """Smallest in-plane extent of a face (approx.: min over edges of the max distance to that edge's line)."""
    c = f.calc_center_median()
    n = f.normal
    best = 1e9
    for e in f.edges:
        d = (e.verts[1].co - e.verts[0].co)
        if d.length < 1e-9:
            continue
        perp = n.cross(d).normalized()
        span = max(abs((v.co - e.verts[0].co).dot(perp)) for v in f.verts)
        best = min(best, span)
    return best


def extrude_faces(part, faces, dist, mat=None):
    bm = part.bm
    res = bmesh.ops.extrude_discrete_faces(bm, faces=faces)
    new = res["faces"]
    for f in new:
        n = f.normal.copy()
        bmesh.ops.translate(bm, vec=n * dist, verts=list(f.verts))
    if mat:
        part.set_mat(mat, faces=new)
    return new


def normal_is(f, axis, sign=1, tol=0.7):
    i = "xyz".index(axis)
    return f.normal[i] * sign > tol


# ============================================================================================== finalize
def _box_uv(bm, uvl, uvm, mslot, matnames, offset):
    ox, oy = offset
    for f in bm.faces:
        mname = matnames[f.material_index] if f.material_index < len(matnames) else ""
        mode = matdefs.REGISTRY.get(mname, {}).get("uv", "world")
        if mode in ("fit", "strip"):
            _fit_uv(f, uvl, mode)
            continue
        oxx, oyy = (0.0, 0.0) if mode == "world0" else (ox, oy)
        if f[uvm] == UVM_KEEP:
            for l in f.loops:
                u, v = l[uvl].uv
                l[uvl].uv = (u + oxx, v + oyy)
            continue
        n = f.normal
        ax = max(range(3), key=lambda k: abs(n[k]))
        for l in f.loops:
            c = l.vert.co
            if ax == 2:
                uv = (c.x, c.y)
            elif ax == 1:
                uv = (c.x, c.z)
            else:
                uv = (c.y, c.z)
            l[uvl].uv = (uv[0] + oxx, uv[1] + oyy)


def _fit_uv(f, uvl, mode):
    n = f.normal
    if abs(n.z) < 0.7:  # wall-like: U horizontal (left->right seen from the front), V up
        t = Vector((0, 0, 1)).cross(n).normalized()
    else:
        t = Vector((1, 0, 0))
    b = n.cross(t).normalized()
    cs = [(l.vert.co.dot(t), l.vert.co.dot(b)) for l in f.loops]
    us, vs = [c[0] for c in cs], [c[1] for c in cs]
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
    du, dv = max(u1 - u0, 1e-6), max(v1 - v0, 1e-6)
    if mode == "strip":
        long_is_u = du >= dv
        for l, (u, v) in zip(f.loops, cs):
            l[uvl].uv = ((u - u0), (v - v0) / dv) if long_is_u else ((v - v0), (u - u0) / du)
    else:
        for l, (u, v) in zip(f.loops, cs):
            l[uvl].uv = ((u - u0) / du, (v - v0) / dv)


def _part_to_object(p, idx):
    bm = p.bm
    me = bpy.data.meshes.new(f"{p.name}_{idx}")
    # material slots: map part-local slot index (layer mslot) -> material_index
    for f in bm.faces:
        f.material_index = f[p.mats]
    bm.to_mesh(me)
    for mn in p.matnames:
        me.materials.append(material(mn))
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def finalize(name, sharp_angle=50.0, uv_offset=None, weighted=True):
    """Join all parts built since the last reset/finalize into one mesh object `name`."""
    global _parts
    parts = [p for p in _parts if len(p.bm.faces)]
    if not parts:
        raise RuntimeError(f"{name}: no geometry")
    if FAST_JOIN:
        ob = _join_fast(parts, name)
        for p in _parts:
            p.bm.free()
        _parts = []
    else:
        objs = [_part_to_object(p, i) for i, p in enumerate(parts)]
        for p in _parts:
            p.bm.free()
        _parts = []
        with bpy.context.temp_override(active_object=objs[0], selected_editable_objects=objs, selected_objects=objs):
            bpy.ops.object.join()
        ob = objs[0]
        ob.name = name
        ob.data.name = name
        # merge duplicate material slots (same material appended by several parts)
        _dedupe_slots(ob)
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    uvl = bm.loops.layers.uv.get("UVMap")
    uvm = bm.faces.layers.int.get("uvm")
    mslot = bm.faces.layers.int.get("mslot")
    names = [m.name for m in me.materials]
    if uv_offset is None:
        rnd = random.Random(hash(name.split("_LOD")[0]) & 0xFFFF)
        uv_offset = (round(rnd.uniform(0, 8), 2), round(rnd.uniform(0, 8), 2))
    _box_uv(bm, uvl, uvm, mslot, names, uv_offset)
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:  # triangulate n-gons here (concave caps) so Unity never has to guess
        bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")
    lim = math.radians(sharp_angle)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        e.smooth = not (len(e.link_faces) != 2 or e.calc_face_angle(0) > lim)
    for lay in (uvm, mslot):
        if lay is not None:
            bm.faces.layers.int.remove(lay)
    bm.to_mesh(me)
    bm.free()
    for a in list(me.attributes):
        if a.name in ("uvm", "mslot"):
            me.attributes.remove(a)
    if weighted:
        mod = ob.modifiers.new("wn", "WEIGHTED_NORMAL")
        mod.keep_sharp = True
        mod.mode = "FACE_AREA"
        mod.weight = 50
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_apply(modifier=mod.name)
    return ob


FAST_JOIN = True


def _join_fast(parts, name):
    """Merge part bmeshes into one mesh without creating an object per part (O(n), no operator/depsgraph cost).
    Material slots are remapped to one de-duplicated list in first-use order."""
    names = []
    for p in parts:
        for mn in p.matnames:
            if mn not in names:
                names.append(mn)
    acc = bmesh.new()
    tmp = bpy.data.meshes.new("__join_tmp")
    for p in parts:
        remap = [names.index(mn) for mn in p.matnames]
        lay = p.mats
        for f in p.bm.faces:
            f.material_index = remap[f[lay]] if f[lay] < len(remap) else 0
        tmp.clear_geometry()
        p.bm.to_mesh(tmp)
        acc.from_mesh(tmp)
    me = bpy.data.meshes.new(name)
    acc.to_mesh(me)
    acc.free()
    bpy.data.meshes.remove(tmp)
    for mn in names:
        me.materials.append(material(mn))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _dedupe_slots(ob):
    me = ob.data
    names = [m.name for m in me.materials]
    uniq = []
    remap = []
    for n in names:
        if n not in uniq:
            uniq.append(n)
        remap.append(uniq.index(n))
    if len(uniq) == len(names):
        return
    idx = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", idx)
    idx = np.array(remap, np.int32)[idx]
    me.materials.clear()
    for n in uniq:
        me.materials.append(bpy.data.materials[n])
    me.polygons.foreach_set("material_index", idx)
    me.update()


def tris(ob):
    me = ob.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def decimate_to(ob, target_tris):
    t = tris(ob)
    if t <= target_tris:
        return ob
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.ratio = max(0.05, target_tris / t)
    mod.use_collapse_triangulate = True
    with bpy.context.temp_override(object=ob, active_object=ob):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return ob


# ============================================================================================== build + export
def to_unity_vec(v):
    """Blender (x,y,z) -> Unity (x,y,z)."""
    return [-v[0], v[2], -v[1]]


def to_unity_size(s):
    return [abs(s[0]), abs(s[2]), abs(s[1])]


def bounds(ob):
    a = np.empty(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", a)
    a = a.reshape(-1, 3)
    return a.min(0), a.max(0)


LOD2_THRESHOLD = 5000


def build_asset(name, builder, lod1_ratio=0.45, lods=None, uv_offset=None, lod2_ratio=0.15, **kw):
    """Run builder for LOD0 and LOD1 (and LOD2 when LOD0 > LOD2_THRESHOLD tris or lods=3).
    Returns [lod0, lod1(, lod2)]."""
    set_lod(0)
    builder(**kw)
    lod0 = finalize(f"{name}_LOD0", uv_offset=uv_offset)
    set_lod(1)
    builder(**kw)
    lod1 = finalize(f"{name}_LOD1", uv_offset=uv_offset)
    t0 = tris(lod0)
    if tris(lod1) > t0 * lod1_ratio:
        decimate_to(lod1, int(t0 * 0.4))
    out = [lod0, lod1]
    want2 = lods == 3 or (lods is None and t0 > LOD2_THRESHOLD)
    if want2:
        set_lod(2)
        builder(**kw)
        lod2 = finalize(f"{name}_LOD2", uv_offset=uv_offset)
        if tris(lod2) > t0 * lod2_ratio:
            decimate_to(lod2, int(t0 * lod2_ratio * 0.9))
        out.append(lod2)
    set_lod(0)
    return out


def export_fbx(objs, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for o in bpy.context.scene.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"MESH"}, apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Z", axis_up="Y", bake_space_transform=True, use_mesh_modifiers=True,
        mesh_smooth_type="OFF", use_tspace=False, path_mode="STRIP", embed_textures=False,
        add_leaf_bones=False, use_custom_props=False, use_triangles=False, colors_type="NONE")


def collider_box(center, size):
    """Collider suggestion in BLENDER coordinates -> Unity dict."""
    return {"type": "box", "center": [round(x, 3) for x in to_unity_vec(center)], "size": [round(x, 3) for x in to_unity_size(size)]}


def record(name, category, zones, lod0, lod1, fbx_rel, colliders=None, pivot="base-centre", notes="", extra=None, lod2=None):
    mn, mx = bounds(lod0)
    size = mx - mn
    ctr = (mn + mx) / 2
    if colliders is None:
        colliders = [collider_box(ctr, size)]
    rec = {
        "name": name,
        "category": category,
        "file": fbx_rel,
        "meshes": {"LOD0": lod0.name, "LOD1": lod1.name, **({"LOD2": lod2.name} if lod2 is not None else {})},
        "tris": {"LOD0": tris(lod0), "LOD1": tris(lod1), **({"LOD2": tris(lod2)} if lod2 is not None else {})},
        "size": [round(float(x), 3) for x in to_unity_size(size)],
        "boundsCenter": [round(float(x), 3) for x in to_unity_vec(ctr)],
        "pivot": pivot,
        "materials": [m.name for m in lod0.data.materials],
        "colliders": colliders,
        "zones": zones,
    }
    if notes:
        rec["notes"] = notes
    if extra:
        rec.update(extra)
    return rec


def save_record(rec, fname="assets.json"):
    """Merge one record into out/<fname> under an exclusive file lock (several Blender builds may run at once)."""
    import fcntl
    os.makedirs(envpaths.STATE, exist_ok=True)
    p = os.path.join(envpaths.STATE, fname)
    with open(p + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            data = json.load(open(p)) if os.path.exists(p) else {}
            data[rec["name"]] = rec
            tmp = p + f".tmp{os.getpid()}"
            json.dump(data, open(tmp, "w"), indent=1)
            os.replace(tmp, p)
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)
