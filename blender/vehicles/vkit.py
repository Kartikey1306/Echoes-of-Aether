"""Vehicle geometry kit (Blender 5.2, bmesh + modifiers).

Build space: +Y = vehicle FRONT, +X = vehicle RIGHT, +Z = up, metres, ground at z = 0.
At export everything is rotated 180 deg about Z so the front faces Blender -Y, which the FBX settings
(axis_forward=-Z, axis_up=Y, bake_space_transform) turn into Unity +Z (Blender +X -> Unity -X).
"""
import math
import os
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import vmatdefs as MD

LOD = 0


def set_lod(l):
    global LOD
    LOD = l


def seg(n, lo=4):
    """Segment count scaled for the current LOD."""
    f = (1.0, 0.5, 0.25)[LOD]
    return max(lo, int(round(n * f)))


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        c = MD.preview_colour(name)
        m.diffuse_color = (c[0], c[1], c[2], 1.0)
    return m


# ================================================================================================ Part
class Part:
    """A bmesh under construction with named material slots."""

    def __init__(self, name="part"):
        self.name = name
        self.bm = bmesh.new()
        self.mats = []
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.crease = self.bm.edges.layers.float.new("crease_edge")
        self._recs = []

    def begin(self):
        """Start recording created verts (nestable)."""
        self._recs.append([])

    def end(self):
        r = self._recs.pop()
        return [v for v in r if v.is_valid]

    def record(self, verts):
        for r in self._recs:
            r.extend(verts)

    def slot(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def vert(self, co):
        v = self.bm.verts.new(co)
        for r in self._recs:
            r.append(v)
        return v

    def face(self, verts, m):
        try:
            f = self.bm.faces.new(verts)
        except ValueError:
            return None
        f.material_index = self.slot(m)
        return f

    def merge(self, other):
        """Append another Part's geometry (consumes it)."""
        remap = [self.slot(m) for m in other.mats]
        me = bpy.data.meshes.new("_tmp")
        for f in other.bm.faces:
            f.material_index = f.material_index  # keep
        other.bm.to_mesh(me)
        for f in self.bm.faces:
            f.tag = True
        self.bm.from_mesh(me)
        for f in self.bm.faces:
            if not f.tag:
                f.material_index = remap[f.material_index] if f.material_index < len(remap) else 0
            f.tag = False
        bpy.data.meshes.remove(me)
        other.bm.free()
        self.uv = self.bm.loops.layers.uv.get("UVMap")
        self.crease = self.bm.edges.layers.float.get("crease_edge")
        return self

    def transform(self, M, verts=None):
        bmesh.ops.transform(self.bm, matrix=M, verts=list(verts) if verts is not None else self.bm.verts[:])
        return self

    def to_object(self, name=None):
        name = name or self.name
        me = bpy.data.meshes.new(name)
        self.bm.normal_update()
        self.bm.to_mesh(me)
        for m in self.mats:
            me.materials.append(material(m))
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        self.bm.free()
        return ob


def new_verts_since(bm, n0):
    raise RuntimeError("new_verts_since is unreliable (bmesh reuses freed slots); use Part.begin()/end()")


def T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def R(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


def S(x=1.0, y=1.0, z=1.0):
    return Matrix.Diagonal((x, y, z, 1.0))


# ================================================================================================ primitives
def box(p, size, at=(0, 0, 0), m="veh_trim", bevel=0.0, bseg=1, M=None):
    p.begin()
    res = bmesh.ops.create_cube(p.bm, size=1.0)
    vs = res["verts"]
    p.record(vs)
    bmesh.ops.scale(p.bm, vec=size, verts=vs)
    fs = list({f for v in vs for f in v.link_faces})
    for f in fs:
        f.material_index = p.slot(m)
    if bevel > 0 and LOD < 2:
        es = list({e for v in vs for e in v.link_edges})
        r = bmesh.ops.bevel(p.bm, geom=es + vs, offset=min(bevel, min(size) * 0.45), segments=bseg if LOD == 0 else 1,
                            profile=0.5, affect="EDGES", clamp_overlap=True)
        p.record(r["verts"])
    vs = p.end()
    if M is not None:
        p.transform(M, vs)
    p.transform(T(*at), vs)
    return vs


def cyl(p, r, h, n=16, at=(0, 0, 0), axis="Z", m="veh_metal", r2=None, caps=True, M=None):
    res = bmesh.ops.create_cone(p.bm, cap_ends=caps, cap_tris=False, segments=n, radius1=r, radius2=r if r2 is None else r2, depth=h)
    vs = list(res["verts"])
    p.record(vs)
    for f in {f for v in vs for f in v.link_faces}:
        f.material_index = p.slot(m)
    if axis == "X":
        p.transform(R("Y", 90), vs)
    elif axis == "Y":
        p.transform(R("X", 90), vs)
    if M is not None:
        p.transform(M, vs)
    p.transform(T(*at), vs)
    return vs


def grid_faces(p, rows, mat_fn, closed_u=False, closed_v=False):
    """rows: list (along v) of lists (along u) of BMVerts. Builds quads; mat_fn(i,j)->material or None."""
    fs = []
    nv = len(rows)
    nu = len(rows[0])
    for i in range(nv - 1 + (1 if closed_v else 0)):
        a, b = rows[i], rows[(i + 1) % nv]
        for j in range(nu - 1 + (1 if closed_u else 0)):
            j1 = (j + 1) % nu
            m = mat_fn(i, j)
            if m is None:
                continue
            f = p.face([a[j], a[j1], b[j1], b[j]], m)
            if f is not None:
                fs.append(f)
    return fs


def lathe(p, profile, n=24, at=(0, 0, 0), axis="X", m="veh_metal", mats=None, closed=False, a0=0.0, a1=360.0,
          sharp_rows=()):
    """profile: [(r, x)] -- radius and axial position; revolved around `axis` (default X: wheel axis).
    mats: optional list of material per profile segment. closed: connect last profile point to first."""
    full = abs(a1 - a0) >= 359.999
    na = n if full else n + 1
    rings = []
    for k in range(na):
        t = math.radians(a0 + (a1 - a0) * k / n)
        ring = []
        for (r, x) in profile:
            if axis == "X":
                co = (x, r * math.cos(t), r * math.sin(t))
            elif axis == "Z":
                co = (r * math.cos(t), r * math.sin(t), x)
            else:
                co = (r * math.sin(t), x, r * math.cos(t))
            ring.append(p.vert(Vector(co) + Vector(at)))
        rings.append(ring)
    npf = len(profile)

    def mf(i, j):
        return mats[j] if mats else m
    fs = grid_faces(p, rings, mf, closed_u=closed, closed_v=full)
    if sharp_rows:
        for e in {e for f in fs for e in f.edges}:
            pass
    return rings, fs


def loft(p, rings, mat_fn, cap0=None, cap1=None, closed_ring=True):
    """rings: list of lists of Vector (equal length). Faces between consecutive rings.
    cap0/cap1: None or (nu, nv, start, bulge) Coons-patch quad caps for the first/last ring."""
    vrows = [[p.vert(c) for c in ring] for ring in rings]
    fs = grid_faces(p, vrows, lambda i, j: mat_fn(i, j), closed_u=closed_ring)
    caps = []
    for cap, idx, sgn in ((cap0, 0, -1), (cap1, len(vrows) - 1, 1)):
        if cap is None:
            continue
        nu, nv, start, bulge, m = cap
        caps.append(coons_cap(p, vrows[idx], nu, nv, start, bulge, m))
    return vrows, fs, caps


def coons_cap(p, ring, nu, nv, start, bulge, m, bulge_dir=None):
    """Fill a closed ring of 2(nu+nv) verts with an nu x nv quad grid (Coons patch).
    B[0..nu] bottom (left->right), B[nu..nu+nv] right (up), B[nu+nv..2nu+nv] top (right->left), rest left (down)."""
    N = len(ring)
    assert N == 2 * (nu + nv), (N, nu, nv)
    B = [ring[(start + k) % N] for k in range(N)]

    def bottom(i):
        return B[i]

    def top(i):
        return B[2 * nu + nv - i]

    def left(j):
        return B[(2 * nu + 2 * nv - j) % N]

    def right(j):
        return B[nu + j]
    P00, P10, P01, P11 = bottom(0).co, bottom(nu).co, top(0).co, top(nu).co
    cen = sum((v.co for v in ring), Vector()) / N
    if bulge_dir is None:
        # ring normal (Newell)
        nrm = Vector()
        for k in range(N):
            a, b = ring[k].co, ring[(k + 1) % N].co
            nrm += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
        bulge_dir = nrm.normalized() if nrm.length > 1e-9 else Vector((0, 1, 0))
    G = [[None] * (nv + 1) for _ in range(nu + 1)]
    for i in range(nu + 1):
        G[i][0] = bottom(i)
        G[i][nv] = top(i)
    for j in range(nv + 1):
        G[0][j] = left(j)
        G[nu][j] = right(j)
    for i in range(1, nu):
        for j in range(1, nv):
            u, v = i / nu, j / nv
            c = ((1 - v) * bottom(i).co + v * top(i).co + (1 - u) * left(j).co + u * right(j).co
                 - ((1 - u) * (1 - v) * P00 + u * (1 - v) * P10 + (1 - u) * v * P01 + u * v * P11))
            c = c + bulge_dir * bulge * math.sin(math.pi * u) * math.sin(math.pi * v)
            G[i][j] = p.vert(c)
    fs = []
    for i in range(nu):
        for j in range(nv):
            f = p.face([G[i][j], G[i + 1][j], G[i + 1][j + 1], G[i][j + 1]], m)
            if f:
                fs.append(f)
    return fs


def frames_along(path, up=Vector((0, 0, 1))):
    """Rotation-minimising-ish frames (tangent, side, normal) for a polyline."""
    n = len(path)
    out = []
    for i in range(n):
        if i == 0:
            t = path[1] - path[0]
        elif i == n - 1:
            t = path[-1] - path[-2]
        else:
            t = (path[i + 1] - path[i - 1])
        t = t.normalized()
        u = up if isinstance(up, Vector) else up[i]
        s = t.cross(u)
        if s.length < 1e-6:
            s = t.cross(Vector((1, 0, 0)))
        s.normalize()
        nn = s.cross(t).normalized()
        out.append((t, s, nn))
    return out


def sweep(p, path, profile, m="veh_trim", closed_path=False, caps=True, up=Vector((0, 0, 1)), scales=None, mats=None,
          twist=None):
    """Sweep a closed 2D profile [(s, n)] (side, normal coords) along a 3D polyline."""
    path = [Vector(c) for c in path]
    fr = frames_along(path, up)
    rings = []
    for i, (c, (t, s, nn)) in enumerate(zip(path, fr)):
        sc = scales[i] if scales else 1.0
        sx, sy = (sc if isinstance(sc, (int, float)) else sc[0]), (sc if isinstance(sc, (int, float)) else sc[1])
        rings.append([p.vert(c + s * (a * sx) + nn * (b * sy)) for (a, b) in profile])
    fs = grid_faces(p, rings, lambda i, j: (mats[j] if mats else m), closed_u=True, closed_v=closed_path)
    if caps and not closed_path:
        f0 = p.face(list(reversed(rings[0])), m)
        f1 = p.face(rings[-1], m)
        fs += [f for f in (f0, f1) if f]
    return rings, fs


def rrect(w, h, r, n=3):
    """Rounded rectangle profile (closed, CCW) centred at 0: [(x, y)]."""
    r = min(r, w / 2 * 0.999, h / 2 * 0.999)
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def circle(r, n=12):
    return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def extrude_poly(p, poly, depth, M=Matrix(), m="veh_trim", m_side=None):
    """Extrude a 2D polygon (x,y CCW) along +z by depth, then transform by M."""
    p.begin()
    a = [p.vert((x, y, 0)) for x, y in poly]
    b = [p.vert((x, y, depth)) for x, y in poly]
    p.face(list(reversed(a)), m)
    p.face(b, m)
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        p.face([a[i], a[j], b[j], b[i]], m_side or m)
    vs = p.end()
    p.transform(M, vs)
    return vs


# ================================================================================================ objects
def obj_from_bm(bm, name, mats):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    for m in mats:
        me.materials.append(material(m))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def apply_mods(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    me.name = old.name
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return ob


def subsurf(ob, levels):
    if levels <= 0:
        return ob
    md = ob.modifiers.new("ss", "SUBSURF")
    md.levels = levels
    md.render_levels = levels
    md.use_creases = True
    md.quality = 3
    md.uv_smooth = "PRESERVE_BOUNDARIES"
    return apply_mods(ob)


def boolean(target, cutters, op="DIFFERENCE", solver="MANIFOLD"):
    """Boolean `target` with one or more cutter objects (consumed). Cutter faces keep their materials."""
    if not isinstance(cutters, (list, tuple)):
        cutters = [cutters]
    cutters = [c for c in cutters if c is not None and len(c.data.polygons)]
    if not cutters:
        return target
    cut = join(cutters, "_cutter") if len(cutters) > 1 else cutters[0]
    nf = len(target.data.polygons)
    md = target.modifiers.new("bool", "BOOLEAN")
    md.operation = op
    md.solver = solver
    md.object = cut
    md.material_mode = "TRANSFER"
    apply_mods(target)
    if len(target.data.polygons) == 0 or (op == "DIFFERENCE" and len(target.data.polygons) == nf and solver == "MANIFOLD"):
        print(f"[bool] warning: {op} on {target.name} produced {len(target.data.polygons)} faces (was {nf})")
    bpy.data.objects.remove(cut, do_unlink=True)
    dedupe_slots(target)
    return target


def join(objs, name):
    objs = [o for o in objs if o is not None]
    if len(objs) == 1:
        objs[0].name = name
        return objs[0]
    with bpy.context.temp_override(active_object=objs[0], selected_editable_objects=objs, selected_objects=objs):
        bpy.ops.object.join()
    ob = objs[0]
    ob.name = name
    ob.data.name = name
    dedupe_slots(ob)
    return ob


def dedupe_slots(ob):
    me = ob.data
    names = [m.name if m else "veh_trim" for m in me.materials]
    uniq, remap = [], []
    for n in names:
        if n not in uniq:
            uniq.append(n)
        remap.append(uniq.index(n))
    if len(uniq) == len(names):
        return
    idx = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", idx)
    idx = np.array(remap, np.int32)[np.clip(idx, 0, len(remap) - 1)]
    me.materials.clear()
    for n in uniq:
        me.materials.append(material(n))
    me.polygons.foreach_set("material_index", idx)
    me.update()


def drop_unused_slots(ob):
    me = ob.data
    idx = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", idx)
    used = sorted(set(idx.tolist()))
    if len(used) == len(me.materials):
        return
    names = [me.materials[i].name for i in used]
    remap = {u: k for k, u in enumerate(used)}
    idx = np.array([remap[i] for i in idx], np.int32)
    me.materials.clear()
    for n in names:
        me.materials.append(material(n))
    me.polygons.foreach_set("material_index", idx)


class Edit:
    """with Edit(ob) as e: e.bm ... ; e.slot('veh_trim') -> material index on the object."""

    def __init__(self, ob):
        self.ob = ob

    def __enter__(self):
        self.bm = bmesh.new()
        self.bm.from_mesh(self.ob.data)
        self.bm.verts.ensure_lookup_table()
        self.bm.faces.ensure_lookup_table()
        return self

    def slot(self, name):
        me = self.ob.data
        for i, m in enumerate(me.materials):
            if m and m.name == name:
                return i
        me.materials.append(material(name))
        return len(me.materials) - 1

    def __exit__(self, *exc):
        self.bm.normal_update()
        self.bm.to_mesh(self.ob.data)
        self.bm.free()
        self.ob.data.update()


def cleanup(ob):
    """Remove degenerate faces/edges and triangulate n-gons so exported triangle counts are exact."""
    with Edit(ob) as e:
        bmesh.ops.dissolve_degenerate(e.bm, dist=1e-6, edges=e.bm.edges[:])
        ng = [f for f in e.bm.faces if len(f.verts) > 4]
        if ng:
            bmesh.ops.triangulate(e.bm, faces=ng, quad_method="BEAUTY", ngon_method="BEAUTY")
        loose = [v for v in e.bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(e.bm, geom=loose, context="VERTS")


def tris(ob):
    me = ob.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def decimate(ob, ratio, sym=True):
    if ratio >= 0.999:
        return ob
    md = ob.modifiers.new("dec", "DECIMATE")
    md.ratio = max(0.02, ratio)
    md.use_collapse_triangulate = True
    md.use_symmetry = sym
    md.symmetry_axis = "X"
    return apply_mods(ob)


def decimate_to(ob, target, sym=True):
    t = tris(ob)
    if t <= target:
        return ob
    for _ in range(3):
        decimate(ob, target / tris(ob), sym)
        if tris(ob) <= target * 1.04:
            break
    return ob


# ================================================================================================ surface queries
class Surface:
    """Ray queries against a mesh object (build space)."""

    def __init__(self, ob):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.transform(ob.matrix_world)
        self.tree = BVHTree.FromBMesh(bm)
        bm.free()

    def hit(self, origin, direction, dist=20.0):
        loc, nrm, idx, d = self.tree.ray_cast(Vector(origin), Vector(direction).normalized(), dist)
        return (loc, nrm) if loc is not None else (None, None)

    def side_x(self, y, z, sign=1, x0=3.0):
        """Outer surface x at (y, z) on the right (sign=+1) or left side."""
        loc, n = self.hit((sign * x0, y, z), (-sign, 0, 0))
        return (loc, n)

    def top_z(self, x, y, z0=5.0):
        loc, n = self.hit((x, y, z0), (0, 0, -1))
        return (loc, n)

    def front_y(self, x, z, sign=1, y0=8.0):
        loc, n = self.hit((x, sign * y0, z), (0, -sign, 0))
        return (loc, n)


# ================================================================================================ grooves
def groove_plane(ob, plane_co, plane_no, region, width=0.0035, depth=0.007, mat="veh_trim"):
    """Cut a panel gap: bisect faces in `region` (fn(center)->bool) with a plane, then bevel the cut edges into
    a strip and push it inward (U-shaped dark groove)."""
    with Edit(ob) as e:
        bm = e.bm
        faces = [f for f in bm.faces if region(f.calc_center_median())]
        if not faces:
            return 0
        geom = list({v for f in faces for v in f.verts}) + list({ed for f in faces for ed in f.edges}) + faces
        res = bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-5, plane_co=Vector(plane_co), plane_no=Vector(plane_no))
        cut = [g for g in res["geom_cut"] if isinstance(g, bmesh.types.BMEdge)]
        cut = [ed for ed in cut if len(ed.link_faces) == 2]
        if not cut:
            return 0
        return _groove_edges(bm, e.slot(mat), cut, width, depth)


def _groove_edges(bm, mi, edges, width, depth):
    """Bevel the seam edges into a 2-segment strip and sink its middle row -> V groove (stays manifold)."""
    r = bmesh.ops.bevel(bm, geom=edges + list({v for ed in edges for v in ed.verts}), offset=width, segments=2,
                        profile=0.5, affect="EDGES", clamp_overlap=True, offset_type="OFFSET")
    strip = set(r["faces"])
    if not strip:
        return 0
    inner = [v for v in r["verts"] if v.link_faces and all(f in strip for f in v.link_faces)]
    moves = []
    for v in inner:
        nrm = Vector()
        for f in v.link_faces:
            nrm += f.normal
        if nrm.length > 0:
            moves.append((v, nrm.normalized()))
    for v, n in moves:
        v.co -= n * depth
    for f in strip:
        f.material_index = mi
    return len(strip)


def assign_region(ob, region, mat, only_mat=None):
    with Edit(ob) as e:
        mi = e.slot(mat)
        oi = e.slot(only_mat) if only_mat else None
        k = 0
        for f in e.bm.faces:
            if (oi is None or f.material_index == oi) and region(f.calc_center_median(), f):
                f.material_index = mi
                k += 1
    return k


def cut_plane(ob, plane_co, plane_no, region=None):
    """Bisect (add an edge loop) without grooving -- used for crisp material boundaries."""
    with Edit(ob) as e:
        bm = e.bm
        faces = [f for f in bm.faces if region is None or region(f.calc_center_median())]
        geom = list({v for f in faces for v in f.verts}) + list({ed for f in faces for ed in f.edges}) + faces
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-5, plane_co=Vector(plane_co), plane_no=Vector(plane_no))


def inset_region_mat(ob, mat, thickness, depth, frame_mat="veh_trim"):
    """Inset all faces of material `mat` as one region: border becomes `frame_mat`, inner recessed by depth."""
    with Edit(ob) as e:
        mi = e.slot(mat)
        fi = e.slot(frame_mat)
        faces = [f for f in e.bm.faces if f.material_index == mi]
        if not faces:
            return
        r = bmesh.ops.inset_region(e.bm, faces=faces, thickness=thickness, depth=-depth, use_even_offset=True,
                                   use_boundary=True)
        for f in r["faces"]:
            f.material_index = fi


# ================================================================================================ UV + normals
BOX_SKIP = {"veh_decal", "veh_navlight", "veh_holo_sign"}


def box_uv(ob, offset=(0.0, 0.0)):
    """World-metre box projection for all faces except authored-UV materials."""
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers[0]
    skip = {i for i, m in enumerate(me.materials) if m and m.name in BOX_SKIP}
    co = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lv = np.zeros(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    uv = np.zeros(len(me.loops) * 2, np.float32)
    uvl.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    ox, oy = offset
    for poly in me.polygons:
        if poly.material_index in skip:
            continue
        n = poly.normal
        ax = max(range(3), key=lambda k: abs(n[k]))
        ls = range(poly.loop_start, poly.loop_start + poly.loop_total)
        for li in ls:
            c = co[lv[li]]
            if ax == 0:
                uv[li] = (c[1] * (1 if n[0] > 0 else -1) + ox, c[2] + oy)
            elif ax == 1:
                uv[li] = (-c[0] * (1 if n[1] > 0 else -1) + ox, c[2] + oy)
            else:
                uv[li] = (c[0] + ox, c[1] * (1 if n[2] > 0 else -1) + oy)
    uvl.data.foreach_set("uv", uv.ravel())


def shade(ob, angle=38.0):
    me = ob.data
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(angle))


def set_uv_rect(p, faces, rect, axes=("x", "z"), flip_u=False):
    """Planar-map faces into atlas rect (u0,v0,u1,v1) using two build-space axes of their bbox."""
    ai = {"x": 0, "y": 1, "z": 2}
    a, b = ai[axes[0]], ai[axes[1]]
    vs = {v for f in faces for v in f.verts}
    lo_a = min(v.co[a] for v in vs)
    hi_a = max(v.co[a] for v in vs)
    lo_b = min(v.co[b] for v in vs)
    hi_b = max(v.co[b] for v in vs)
    u0, v0, u1, v1 = rect
    for f in faces:
        for l in f.loops:
            ta = (l.vert.co[a] - lo_a) / max(hi_a - lo_a, 1e-6)
            tb = (l.vert.co[b] - lo_b) / max(hi_b - lo_b, 1e-6)
            if flip_u:
                ta = 1 - ta
            l[p.uv].uv = (u0 + ta * (u1 - u0), v0 + tb * (v1 - v0))


def set_uv_point(p, faces, uv):
    for f in faces:
        for l in f.loops:
            l[p.uv].uv = uv


def faces_of(vs):
    return list({f for v in vs for f in v.link_faces})


# ================================================================================================ helpers
def mirror_part_x(p, verts):
    """Duplicate given verts' faces mirrored across X=0 (for symmetric details)."""
    faces = faces_of(verts)
    ret = bmesh.ops.duplicate(p.bm, geom=faces)
    nv = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
    nf = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMFace)]
    for v in nv:
        v.co.x = -v.co.x
    bmesh.ops.reverse_faces(p.bm, faces=nf)
    return nv


def smooth_keys(keys, s):
    """Monotone-ish cubic (Catmull-Rom) interpolation through [(s, value)] keys."""
    ks = sorted(keys)
    if s <= ks[0][0]:
        return ks[0][1]
    if s >= ks[-1][0]:
        return ks[-1][1]
    for i in range(len(ks) - 1):
        s0, v0 = ks[i]
        s1, v1 = ks[i + 1]
        if s0 <= s <= s1:
            t = (s - s0) / (s1 - s0) if s1 > s0 else 0
            vm = ks[i - 1][1] if i > 0 else v0
            vp = ks[i + 2][1] if i + 2 < len(ks) else v1
            sm = ks[i - 1][0] if i > 0 else s0 - (s1 - s0)
            sp = ks[i + 2][0] if i + 2 < len(ks) else s1 + (s1 - s0)
            m0 = (v1 - vm) / (s1 - sm) * (s1 - s0)
            m1 = (vp - v0) / (sp - s0) * (s1 - s0)
            # limit tangents to avoid overshoot
            d = v1 - v0
            if d == 0:
                m0 = m1 = 0
            else:
                m0 = max(min(m0, 3 * d), -3 * abs(d)) if d > 0 else max(min(m0, 3 * abs(d)), 3 * d)
                m1 = max(min(m1, 3 * d), -3 * abs(d)) if d > 0 else max(min(m1, 3 * abs(d)), 3 * d)
            t2, t3 = t * t, t * t * t
            return (2 * t3 - 3 * t2 + 1) * v0 + (t3 - 2 * t2 + t) * m0 + (-2 * t3 + 3 * t2) * v1 + (t3 - t2) * m1
    return ks[-1][1]


class Profile:
    """Named parameter tracks keyed along s (forward axis): prof('w', s)."""

    def __init__(self, tracks):
        self.tracks = tracks

    def __call__(self, key, s):
        k = self.tracks[key]
        if isinstance(k, (int, float)):
            return k
        return smooth_keys(k, s)


# ================================================================================================ export
def to_unity_space(objs):
    """Rotate built geometry 180 deg about Z (front +Y -> -Y) for export. Applies to mesh data + locations."""
    Rz = Matrix.Rotation(math.pi, 4, "Z")
    for o in objs:
        if o.type == "MESH" and o.parent is None:
            o.data.transform(Rz)
        elif o.type == "MESH":
            o.data.transform(Rz)  # child meshes are centred on their pivot; rotate locally too
        if o.parent is None:
            o.location = Rz @ o.location


def export_fbx(objs, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for o in bpy.context.scene.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"MESH", "EMPTY"}, apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Z", axis_up="Y", bake_space_transform=True, use_mesh_modifiers=True,
        mesh_smooth_type="OFF", use_tspace=False, path_mode="STRIP", embed_textures=False,
        add_leaf_bones=False, use_custom_props=False, use_triangles=False, colors_type="NONE",
        use_armature_deform_only=False, bake_anim=False)


def to_unity_vec(v):
    """Blender export-space (front -Y) -> Unity."""
    return [round(-float(v[0]), 3), round(float(v[2]), 3), round(-float(v[1]), 3)]


def build_to_unity(v):
    """Build space (front +Y, right +X) -> Unity (front +Z, right +X)."""
    return [round(float(v[0]), 3), round(float(v[2]), 3), round(float(v[1]), 3)]


def bounds_world(objs):
    lo = np.array([1e9] * 3)
    hi = np.array([-1e9] * 3)
    for o in objs:
        if o.type != "MESH" or not len(o.data.vertices):
            continue
        a = np.empty(len(o.data.vertices) * 3, np.float32)
        o.data.vertices.foreach_get("co", a)
        a = a.reshape(-1, 3)
        M = np.array(o.matrix_world)
        a = a @ M[:3, :3].T + M[:3, 3]
        lo = np.minimum(lo, a.min(0))
        hi = np.maximum(hi, a.max(0))
    return lo, hi
