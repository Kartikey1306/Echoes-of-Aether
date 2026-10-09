"""Garment shells for Kael v2.

A shell starts from MakeHuman-topology faces of the rest body (good animation edge flow: loops at every joint),
is cut along smooth designed curves (scalar fields, not the mesh's zig-zag), offset by a thickness profile and
cloth-relaxed against the subdivided body + inner layers so it bridges anatomy like real fabric, then gets a
turned-in hem rim. UVs are unwrapped fresh (conformal) along the MakeHuman UV seams + the cut edges.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import kcommon as K
import meshops

PRE = K.PRE


class BodyInfo:
    """Rest-pose analysis of the subdivided body (collision, weights, shapes) and the MakeHuman cage."""

    def __init__(self, rig, body, mh):
        self.rig, self.body, self.mh = rig, body, mh
        self.co = K.get_co(body)
        self.faces = K.faces_of(body)
        self.tree = BVHTree.FromPolygons([Vector(c) for c in self.co], self.faces)
        self.names, self.W = meshops.get_weights(body)
        _, self.shapes = meshops.shape_arrays(body)
        self.mh_co = K.get_co(mh)
        self.mh_faces = K.faces_of(mh)
        self.L = {b.name.split(":")[1]: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones if ":" in b.name}
        self.T = {b.name.split(":")[1]: np.array(rig.matrix_world @ b.tail_local) for b in rig.data.bones if ":" in b.name}
        # weights of the MH cage verts: sampled from the subdivided body at the nearest surface point
        self.mh_W = self.sample_weights(self.mh_co)
        self.layers = []      # garment objects forming the outer surface (for layering)
        self._outer = None

    def wsum(self, W, bones):
        idx = [self.names.index(PRE + b) for b in bones if PRE + b in self.names]
        return W[:, idx].sum(1) if idx else np.zeros(len(W))

    def bind(self, pts, tree=None, co=None, faces=None):
        """Nearest-surface binding (face vertex ids, barycentric weights) of points on the body."""
        from mathutils.interpolate import poly_3d_calc
        tree = tree or self.tree
        co = self.co if co is None else co
        faces = self.faces if faces is None else faces
        I = np.zeros((len(pts), 4), np.int64)
        Wt = np.zeros((len(pts), 4))
        D = np.zeros(len(pts))
        for i, p in enumerate(pts):
            loc, n, fi, d = tree.find_nearest(Vector(p), 1.0)
            f = faces[fi]
            w = poly_3d_calc([Vector(co[v]) for v in f], loc)
            I[i, :len(f)] = f
            Wt[i, :len(f)] = w
            D[i] = d
        return I, Wt, D

    def sample_weights(self, pts):
        I, Wt, _ = self.bind(pts)
        return (self.W[I] * Wt[..., None]).sum(1)

    def outer_tree(self):
        if self._outer is None:
            verts = [Vector(c) for c in self.co]
            polys = [list(f) for f in self.faces]
            for o in self.layers:
                off = len(verts)
                mw = o.matrix_world
                verts += [mw @ v.co for v in o.data.vertices]
                polys += [[off + i for i in p.vertices] for p in o.data.polygons]
            self._outer = BVHTree.FromPolygons(verts, polys)
        return self._outer

    def push_layer(self, o):
        self.layers.append(o)
        self._outer = None


def mh_normals(co, faces):
    return K.vertex_normals(co, faces)


# ----------------------------------------------------------------------------- bmesh construction / cutting


def shell_from_faces(B, face_ids, name):
    """New mesh object from MakeHuman cage faces (positions from the conformed cage); the source cage vertex index is
    stored in the 'src' attribute, MH UV seams marked as edge seams."""
    me_src = B.mh.data
    used = sorted({v for fi in face_ids for v in B.mh_faces[fi]})
    inv = {v: i for i, v in enumerate(used)}
    F = [[inv[v] for v in B.mh_faces[fi]] for fi in face_ids]
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(B.mh_co[v]) for v in used], [], F)
    me.update()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    a = me.attributes.new("src", "INT", "POINT")
    a.data.foreach_set("value", np.array(used, np.int32))
    # UV seams from the MakeHuman UV layout: an edge is a seam when its two faces disagree on a shared corner UV
    uvl = me_src.uv_layers.active.data
    face_uv = {}
    for fi in face_ids:
        p = me_src.polygons[fi]
        face_uv[fi] = {me_src.loops[li].vertex_index: tuple(np.round(uvl[li].uv[:], 4)) for li in p.loop_indices}
    edge_faces = {}
    for fi in face_ids:
        vs = B.mh_faces[fi]
        for i in range(len(vs)):
            a_, b_ = vs[i], vs[(i + 1) % len(vs)]
            edge_faces.setdefault((min(a_, b_), max(a_, b_)), []).append(fi)
    seams = set()
    for (a_, b_), fl in edge_faces.items():
        if len(fl) == 2:
            f1, f2 = fl
            if face_uv[f1][a_] != face_uv[f2][a_] or face_uv[f1][b_] != face_uv[f2][b_]:
                seams.add((inv[a_], inv[b_]))
    for e in me.edges:
        a_, b_ = e.vertices
        if (a_, b_) in seams or (b_, a_) in seams:
            e.use_seam = True
    return o


def cut(o, field, eps=1e-7):
    """Keep the part of o where field(points) >= 0; new boundary exactly on the zero set (edges split at the
    crossing, faces split across). field: (N,3) world points -> (N,) values."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    src = bm.verts.layers.int.get("src")
    for _ in range(2):
        bm.verts.ensure_lookup_table()
        P = np.array([v.co[:] for v in bm.verts])
        f = np.asarray(field(P), np.float64)
        f[np.abs(f) < eps] = eps
        val = {v: f[i] for i, v in enumerate(bm.verts)}
        cross = [e for e in bm.edges if val[e.verts[0]] * val[e.verts[1]] < 0]
        newv = set()
        for e in cross:
            a, b = e.verts
            fa, fb = val[a], val[b]
            t = fa / (fa - fb)
            ne, nv = bmesh.utils.edge_split(e, a, t)
            nv.co = a.co.lerp(b.co, t) if False else a.co + (b.co - a.co) * t
            val[nv] = 0.0
            newv.add(nv)
        # split faces through their new vertex pairs
        pairs = []
        for fc in bm.faces:
            nvs = [v for v in fc.verts if v in newv]
            if len(nvs) == 2:
                pairs.append(nvs)
        for a, b in pairs:
            try:
                bmesh.ops.connect_vert_pair(bm, verts=[a, b])
            except Exception:
                pass
        kill = [v for v in bm.verts if val.get(v, 1.0) < 0]
        bmesh.ops.delete(bm, geom=kill, context="VERTS")
        break
    # tiny edges at the cut collapse
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.0015)
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()
    return o


def drop_islands(o, min_faces=6):
    """Remove small disconnected pieces (cut leftovers)."""
    bm = bmesh.new(); bm.from_mesh(o.data)
    bm.faces.ensure_lookup_table()
    seen = set()
    kill = []
    for f0 in bm.faces:
        if f0.index in seen:
            continue
        stack = [f0]; comp = []
        seen.add(f0.index)
        while stack:
            f = stack.pop(); comp.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index); stack.append(g)
        if len(comp) < min_faces:
            kill += comp
    if kill:
        bmesh.ops.delete(bm, geom=kill, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(o.data); bm.free(); o.data.update()


def boundary_info(o):
    me = o.data
    n = len(me.vertices)
    E = meshops.edges_of(o)
    ec = {}
    for p in me.polygons:
        vs = list(p.vertices)
        for i in range(len(vs)):
            a, b = vs[i], vs[(i + 1) % len(vs)]
            k = (min(a, b), max(a, b))
            ec[k] = ec.get(k, 0) + 1
    bE = np.array([k for k, c in ec.items() if c == 1], np.int64).reshape(-1, 2)
    isb = np.zeros(n, bool)
    if len(bE):
        isb[bE.ravel()] = True
    return E, bE, isb


# ----------------------------------------------------------------------------- offset + cloth relax


def relax_offset(o, B, offset_fn, iters=24, lam=0.55, min_gap_fn=None, tree=None, bridge=1.0, bsmooth=8, pin_fn=None):
    """Offset o outward by offset_fn(P, N) and relax it like fabric: Laplacian smoothing (bridging concavities),
    then re-push every vertex to at least its gap above the collision surface (body + inner layers)."""
    tree = tree or B.outer_tree()
    co = K.get_co(o)
    faces = K.faces_of(o)
    N = K.vertex_normals(co, faces)
    off = np.asarray(offset_fn(co, N), np.float64)
    gap = off if min_gap_fn is None else np.asarray(min_gap_fn(co, N), np.float64)
    E, bE, isb = boundary_info(o)
    n = len(co)
    # boundary neighbours (smooth the cut line along itself only)
    bn = [[] for _ in range(n)]
    for a, b in bE:
        bn[a].append(b); bn[b].append(a)
    X = co + N * off[:, None]
    pin = np.zeros(n, bool) if pin_fn is None else np.asarray(pin_fn(co), bool)
    for it in range(iters):
        nb = meshops.neighbor_mean(X, E, n)
        step = (nb - X) * lam * bridge
        step[isb] = 0
        step[pin] = 0
        X = X + step
        # boundary: smooth along the loop
        if it < bsmooth:
            Xb = X.copy()
            for i in np.where(isb)[0]:
                if len(bn[i]) == 2:
                    Xb[i] = X[i] * 0.5 + (X[bn[i][0]] + X[bn[i][1]]) * 0.25
            X = Xb
        # collision push-out
        for i in range(n):
            hit, hn, _, d = tree.find_nearest(Vector(X[i]), 0.25)
            if hit is None:
                continue
            g = (Vector(X[i]) - hit).dot(hn)
            if g < gap[i]:
                X[i] = X[i] + np.array(hn) * (gap[i] - g)
    K.set_co(o, X)
    return o


def rim(o, thickness=0.005, offset=-1.0):
    """Turned-in edge band at every opening (the garment shows real thickness at hems and cuffs)."""
    before = K.get_co(o)
    tree = BVHTree.FromPolygons([Vector(c) for c in before], [list(p.vertices) for p in o.data.polygons])
    m = o.modifiers.new("rim", "SOLIDIFY")
    m.thickness = thickness
    m.offset = offset
    m.use_rim = True
    m.use_rim_only = True
    m.use_even_offset = False
    m.use_quality_normals = True
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = o.data
    o.modifiers.clear()
    o.data = me
    bpy.data.meshes.remove(old)
    me.name = o.name
    # guard: rim vertices from degenerate corners must stay within 2x thickness of the shell
    co = K.get_co(o)
    bad = 0
    for i, p in enumerate(co):
        loc, n, fi, d = tree.find_nearest(Vector(p), 1e9)
        if d > thickness * 2.5:
            co[i] = np.array(loc) - np.array(n) * thickness
            bad += 1
    if bad:
        K.set_co(o, co)
        K.log("RIM", o.name, "fixed", bad)
    return o


def unwrap(o, margin=0.003):
    """Conformal unwrap along the marked seams (+ boundaries)."""
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    if not o.data.uv_layers:
        o.data.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="CONFORMAL", margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")
    o.select_set(False)


def smooth_shading(o):
    o.data.polygons.foreach_set("use_smooth", np.ones(len(o.data.polygons), bool))


def set_material(o, name):
    import gear
    o.data.materials.clear()
    o.data.materials.append(gear.get_mat(name))
    o.data.polygons.foreach_set("material_index", np.zeros(len(o.data.polygons), np.int32))


# ----------------------------------------------------------------------------- skinning + morphs from the body


def skin_from_body(o, B, rig, smooth_iters=6, max_infl=4, limit_bones=None, rigid=None, blend=None, smooth_mask=None):
    """Weights: rigid bone / fixed blend, or interpolated from the body surface then smoothed over the garment
    (cloth does not follow every muscle), at most 4 influences. Body morph shapes (m_*) transferred by binding."""
    co = K.get_co(o)
    names = list(B.names)
    if rigid:
        W = np.zeros((len(co), len(names)))
        W[:, names.index(PRE + rigid)] = 1
    elif blend:
        W = np.zeros((len(co), len(names)))
        for b, w in blend:
            W[:, names.index(PRE + b)] = w
    else:
        W = B.sample_weights(co)
        if limit_bones:
            keep = np.array([n[len(PRE):] in limit_bones for n in names])
            W = W * keep[None]
        E = meshops.edges_of(o)
        W = meshops.smooth(W, E, iters=smooth_iters, lam=0.5, mask=smooth_mask)
        W = meshops.limit_normalize(W, max_infl, 0.01)
        W = meshops.smooth(W, E, iters=1, lam=0.3, mask=smooth_mask)
    W = meshops.limit_normalize(W, max_infl, 0.01)
    meshops.set_weights(o, names, W)
    o.parent = rig
    if not any(m.type == "ARMATURE" for m in o.modifiers):
        m = o.modifiers.new("Armature", "ARMATURE")
        m.object = rig
    transfer_shapes(o, B, prefixes=("m_",))
    return o


def transfer_shapes(o, B, prefixes=("m_",), names=None):
    co = K.get_co(o)
    I, Wt, D = B.bind(co)
    basis, old = meshops.shape_arrays(o)
    shapes = {}
    for n, sco in B.shapes.items():
        if names is not None and n not in names:
            continue
        if not n.startswith(prefixes):
            continue
        d = ((sco - B.co)[I] * Wt[..., None]).sum(1)
        if np.abs(d).max() > 1e-5:
            shapes[n] = co + d
    for n, c in old.items():
        if n.startswith("corr_"):
            shapes[n] = c
    meshops.set_shapes(o, co, shapes)


def cover_from(o, B, dist=0.07, margin_rings=1):
    """Body vertices hidden under garment o: ray along the body normal hits o within dist."""
    tree = BVHTree.FromPolygons([o.matrix_world @ v.co for v in o.data.vertices], [list(p.vertices) for p in o.data.polygons])
    N = K.vertex_normals(B.co, B.faces)
    hit = np.zeros(len(B.co), bool)
    for i, (p, n) in enumerate(zip(B.co, N)):
        h = tree.ray_cast(Vector(p + n * 0.0005), Vector(n), dist)[0]
        hit[i] = h is not None
    return hit


def drop_degenerate(o, min_area=2e-8):
    """Dissolve zero-area faces (e.g. after flattening a hem onto a plane)."""
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.dissolve_degenerate(bm, dist=0.0008, edges=list(bm.edges))
    kill = [f for f in bm.faces if f.calc_area() < min_area]
    if kill:
        bmesh.ops.delete(bm, geom=kill, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(o.data); bm.free(); o.data.update()


def fix_orientation(o):
    """Make every connected piece's faces point outwards: flip a piece whose signed volume (relative to its own
    centroid) is negative. Works for closed hard-surface parts and for open shells wrapped around the body."""
    bm = bmesh.new(); bm.from_mesh(o.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    seen = set()
    flipped = 0
    for f0 in bm.faces:
        if f0.index in seen:
            continue
        comp, stack = [], [f0]
        seen.add(f0.index)
        while stack:
            f = stack.pop(); comp.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index); stack.append(g)
        cen = sum((f.calc_center_median() for f in comp), Vector()) / len(comp)
        vol = sum((f.calc_center_median() - cen).dot(f.normal) * f.calc_area() for f in comp)
        if vol < 0:
            bmesh.ops.reverse_faces(bm, faces=comp)
            flipped += 1
    bm.to_mesh(o.data); bm.free(); o.data.update()
    return flipped
