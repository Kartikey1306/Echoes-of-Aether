"""Garment toolkit: body-relative coordinates, region extraction (shape keys + weights preserved), exact plane
cuts, Catmull-Clark subdivision of every shape key, guaranteed skin gap with concavity bridging, boundary loops,
rim/collar construction."""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
import gv

P = gv.P


# ----------------------------------------------------------------------------- body-relative coordinates

class Frames:
    """Rest-pose landmark frames of the rig (armature space == world, rig at identity)."""

    def __init__(self, rig):
        self.rig = rig
        self.h = {b.name[len(P):]: np.array(b.head_local) for b in rig.data.bones if b.name.startswith(P)}
        self.t = {b.name[len(P):]: np.array(b.tail_local) for b in rig.data.bones if b.name.startswith(P)}
        sp = [self.h["Hips"], self.h["Spine"], self.h["Spine1"], self.h["Spine2"], self.h["Neck"], self.h["Head"]]
        self.spine = np.array(sp)

    def torso(self, X):
        """(z, phi) with phi = 0 front (-Y), +pi/2 character left (+X); centre from the spine polyline."""
        sp = self.spine
        z = X[:, 2]
        cx = np.interp(z, sp[:, 2], sp[:, 0])
        cy = np.interp(z, sp[:, 2], sp[:, 1])
        phi = np.arctan2(X[:, 0] - cx, -(X[:, 1] - cy))
        return z, phi

    def chain(self, X, bones, ref=(0, -1, 0)):
        """Arc-length t (m) along a bone chain from the first head, phi around it (0 = ref direction projected,
        +pi/2 = cross(axis, ref) side), radial distance r."""
        pts = [self.h[bones[0]]] + [self.t[b] for b in bones]
        pts = np.array(pts)
        best_d = np.full(len(X), 1e9)
        t = np.zeros(len(X))
        ax = np.zeros((len(X), 3))
        foot = np.zeros((len(X), 3))
        acc = 0.0
        for a, b in zip(pts[:-1], pts[1:]):
            ab = b - a
            L = np.linalg.norm(ab)
            u = np.clip(((X - a) @ ab) / (L * L), 0, 1)
            f = a + u[:, None] * ab
            d = np.linalg.norm(X - f, axis=1)
            m = d < best_d
            best_d[m] = d[m]
            t[m] = acc + u[m] * L
            ax[m] = ab / L
            foot[m] = f[m]
            acc += L
        r0 = np.array(ref, float)
        r0 = r0[None] - ax * (ax @ r0)[:, None]
        r0 = gv.nrm(r0)
        r1 = np.cross(ax, r0)
        v = X - foot
        phi = np.arctan2((v * r1).sum(1), (v * r0).sum(1))
        return t, phi, best_d, acc


# ----------------------------------------------------------------------------- region extraction

def extract(src, keep_face, name, drop_shapes=("corr_",)):
    """Copy `src` (mesh with shape keys + groups), keep faces where keep_face[f] is True."""
    o = src.copy()
    o.data = src.data.copy()
    o.name = o.data.name = name
    bpy.context.scene.collection.objects.link(o)
    o.modifiers.clear()
    if o.data.shape_keys:
        for k in list(o.data.shape_keys.key_blocks[1:]):
            if k.name.startswith(drop_shapes):
                o.shape_key_remove(k)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.faces.ensure_lookup_table()
    kill = [f for f in bm.faces if not keep_face[f.index]]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()
    return o


def bisect(o, co, no, keep="below"):
    """Exact plane cut; keeps the side where (x - co).no < 0 ('below') or > 0 ('above'). Shape keys and weights
    are interpolated on the cut."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    no = Vector(no).normalized()
    if keep == "above":
        no = -no
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=Vector(co), plane_no=no, clear_outer=True, clear_inner=False)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()


def subdivide(o, levels=1):
    """Catmull-Clark subdivision applied to the mesh and every shape key (positions are linear in the cage, so
    each key is subdivided exactly); vertex groups and UVs are interpolated."""
    me = o.data
    keys = []
    if me.shape_keys:
        keys = [(k.name, np.array([d.co[:] for d in k.data])) for k in me.shape_keys.key_blocks]
    basis = keys[0][1] if keys else gv.get_co(o)
    if me.shape_keys:
        o.shape_key_clear()
    gv.set_co(o, basis)
    m = o.modifiers.new("ss", "SUBSURF")
    m.levels = m.render_levels = levels
    m.subdivision_type = "CATMULL_CLARK"
    m.boundary_smooth = "ALL"
    m.uv_smooth = "PRESERVE_BOUNDARIES"
    m.use_limit_surface = False
    dg = bpy.context.evaluated_depsgraph_get()

    def evaluated():
        dg.update()
        ev = o.evaluated_get(dg)
        return np.array([v.co[:] for v in ev.data.vertices])

    sub = {}
    for n, co in keys[1:]:
        gv.set_co(o, co)
        sub[n] = evaluated()
    gv.set_co(o, basis)
    dg.update()
    ev = o.evaluated_get(dg)
    new = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    o.modifiers.remove(m)
    old = o.data
    o.data = new
    new.name = o.name
    bpy.data.meshes.remove(old)
    if keys:
        o.shape_key_add(name="Basis", from_mix=False)
        for n, co in sub.items():
            gv.add_shape(o, n, co)
    return o


# ----------------------------------------------------------------------------- skin gap + bridging

class Surface:
    def __init__(self, co, tris):
        self.co, self.tris = co, tris
        self.tree = BVHTree.FromPolygons([Vector(c) for c in co], tris.tolist(), all_triangles=True)

    def signed(self, X, maxd=0.2):
        """Signed distance (outside > 0) and nearest point/normal for each X."""
        d = np.zeros(len(X))
        N = np.zeros((len(X), 3))
        H = np.zeros((len(X), 3))
        for i, p in enumerate(X):
            loc, nrm, fi, dist = self.tree.find_nearest(Vector(p), maxd)
            if loc is None:
                d[i] = maxd
                continue
            v = np.array(p) - np.array(loc)
            n = np.array(nrm)
            d[i] = dist if v @ n >= 0 else -dist
            N[i] = n
            H[i] = loc
        return d, H, N


def push_out(X, tris, off, idx, skin, gap, bridge_iters=0, bridge_mask=None, relax=0.0):
    """Move X outward so every vertex is at least `gap` (per-vertex array or float) outside `skin` (Surface);
    optional outward-only bridging of concavities (cleavage, spine groove)."""
    X = X.copy()
    gap = np.broadcast_to(np.asarray(gap, float), (len(X),))
    for it in range(3):
        d, H, N = skin.signed(X)
        need = gap - d
        m = need > 0
        X[m] += N[m] * need[m, None]
    if bridge_iters:
        for _ in range(bridge_iters):
            n = gv.vertex_normals(X, tris)
            avg = gv.laplacian_avg(X, off, idx)
            out = ((avg - X) * n).sum(1)
            mv = np.maximum(out, 0) * 0.6
            if bridge_mask is not None:
                mv *= bridge_mask
            X += n * mv[:, None]
    if relax:
        avg = gv.laplacian_avg(X, off, idx)
        n = gv.vertex_normals(X, tris)
        t = avg - X
        t -= n * (t * n).sum(1, keepdims=True)
        X += t * relax
    return X


# ----------------------------------------------------------------------------- loops / rims

def boundary_loops(me):
    """Ordered boundary vertex loops [(indices...)]."""
    bm = bmesh.new()
    bm.from_mesh(me)
    edges = [e for e in bm.edges if e.is_boundary]
    nxt = {}
    for e in edges:
        a, b = e.verts[0].index, e.verts[1].index
        nxt.setdefault(a, []).append(b)
        nxt.setdefault(b, []).append(a)
    bm.free()
    seen = set()
    loops = []
    for s in nxt:
        if s in seen:
            continue
        loop = [s]
        seen.add(s)
        prev, cur = None, s
        while True:
            cand = [c for c in nxt[cur] if c != prev and c not in seen]
            if not cand:
                break
            prev, cur = cur, cand[0]
            loop.append(cur)
            seen.add(cur)
        loops.append(loop)
    return loops


def loop_normals_out(X, loop, centre):
    """Unit vectors pointing away from `centre` in the loop's local plane (for rim extrusion)."""
    L = X[loop]
    return gv.nrm(L - centre)


# ----------------------------------------------------------------------------- coverage (hidden-face stripping)

def ray_cover(X, N, objs_co_tris, max_d=0.05, back=0.004):
    """Per vertex: True when a ray from just below X along the normal hits any of the given surfaces within max_d."""
    trees = [BVHTree.FromPolygons([Vector(c) for c in co], t.tolist(), all_triangles=True) for co, t in objs_co_tris]
    hit = np.zeros(len(X), bool)
    for i, (p, n) in enumerate(zip(X, N)):
        o = Vector(p - n * back)
        d = Vector(n)
        for tr in trees:
            loc, nn, fi, dist = tr.ray_cast(o, d, max_d + back)
            if loc is not None:
                hit[i] = True
                break
    return hit


def catalog_armour_meshes(rig, hero="lyra"):
    """Rest-pose (co, tris) of every catalog armour set for the hero, bind-pose remapped onto `rig`."""
    import json, os
    import mpfb_build
    cat = json.load(open(os.path.join(gv.CUSTOM, "catalog.json")))
    out = []
    for it in cat.get("armour", []):
        if it.get("hero") != hero:
            continue
        objs = mpfb_build.attach_catalog(rig, "armour", it["id"])
        for o in objs:
            co = gv.get_co(o)
            out.append((it["id"], co, gv.tri_index(o.data)))
            gv.remove(o)
    return out


# ----------------------------------------------------------------------------- strips along loops

def order_loop_by_angle(X, loop, centre, up):
    """Return the loop rotated/reversed so it runs counter-clockwise about `up` starting at the front (-Y)."""
    L = np.array(loop)
    v = X[L] - centre
    up = np.asarray(up, float)
    ref = np.array((0, -1.0, 0))
    ref = ref - up * (ref @ up)
    ref /= np.linalg.norm(ref)
    side = np.cross(up, ref)
    ang = np.arctan2(v @ side, v @ ref)
    # orientation
    da = np.angle(np.exp(1j * np.diff(np.concatenate([ang, ang[:1]])))).sum()
    if da < 0:
        L = L[::-1]
        ang = ang[::-1]
    i0 = int(np.argmin(np.abs(ang)))
    return np.roll(L, -i0)


def profile_strip(base, frames, profile, closed=True):
    """Sweep a 2D profile [(out, up), ...] along base points with frames (O, U) -> verts, quads.
    Returns (V (n*m,3), faces, (i, j) per vertex)."""
    n, m = len(base), len(profile)
    V = np.zeros((n * m, 3))
    ij = []
    for i in range(n):
        O, U = frames[i]
        for j, (po, pu) in enumerate(profile):
            V[i * m + j] = base[i] + O * po + U * pu
            ij.append((i, j))
    F = []
    rng = n if closed else n - 1
    for i in range(rng):
        i2 = (i + 1) % n
        for j in range(m - 1):
            F.append((i * m + j, i2 * m + j, i2 * m + j + 1, i * m + j + 1))
    return V, F, ij


def strip_body(body, garments, margin_rings=2):
    """Delete body faces hidden under the garments (ray along the vertex normal hits a garment within 4 cm),
    keeping `margin_rings` rings of faces under every garment edge."""
    me = body.data
    X = gv.basis_co(body)
    tris = gv.tri_index(me)
    N = gv.vertex_normals(X, tris)
    surf = [(gv.basis_co(g), gv.tri_index(g.data)) for g in garments]
    cov = ray_cover(X, N, surf, 0.045, back=0.02)
    off, idx = gv.neighbours(me)
    keep = (~cov).astype(float)
    for _ in range(margin_rings):
        keep = np.maximum(keep, gv.laplacian_avg(keep, off, idx) > 0)
    bm = bmesh.new()
    bm.from_mesh(me)
    kill = [f for f in bm.faces if all(keep[v.index] == 0 for v in f.verts)]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(me)
    bm.free()
    me.update()
    gv.log("body strip: removed", len(kill), "faces; left", len(me.polygons))


