"""Giva v2 pipeline: shared helpers (paths, logging, numpy mesh access, shape keys, weights, images).

Everything here is plain bpy + numpy (Blender's Python has no PIL/scipy).
"""
import bpy, bmesh, os, sys, math, time, json
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
GIVA = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(GIVA, "out")
ROOT = os.path.abspath(os.path.join(GIVA, "..", "..", ".."))           # repo root
BLENDER = os.path.join(ROOT, "blender")
ASSETS = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets")
LYRA_DIR = os.path.join(ASSETS, "Art", "Characters", "Lyra")
ANIM_F = os.path.join(ASSETS, "Art", "Animations", "Anim_Female.fbx")
CUSTOM = os.path.join(ASSETS, "Resources", "Characters", "Custom")
MPFB_DATA = os.path.expanduser("~/Library/Application Support/Blender/5.2/extensions/.user/user_default/mpfb/data")
MPFB_SYS = os.path.expanduser("~/Library/Application Support/Blender/5.2/extensions/user_default/mpfb/data")
RIG = "Lyra"           # armature object / FBX root name (asset id stays lyra)
P = "mixamorig:"

_T0 = time.time()


def log(*a):
    print(f"[giva {time.time() - _T0:7.1f}s]", *a, flush=True)


def args():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(a, key, default=None):
    return a[a.index(key) + 1] if key in a else default


# ----------------------------------------------------------------------------- numpy mesh access

def get_co(obj):
    a = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
    obj.data.vertices.foreach_get("co", a)
    return a.reshape(-1, 3).astype(np.float64)


def set_co(obj, co):
    obj.data.vertices.foreach_set("co", np.asarray(co, dtype=np.float32).ravel())
    obj.data.update()


def faces_of(me):
    return [list(p.vertices) for p in me.polygons]


def tri_index(me):
    """(T,3) vertex indices of the loop triangles."""
    me.calc_loop_triangles()
    t = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", t)
    return t.reshape(-1, 3)


def vertex_normals(co, tris):
    """Area-weighted vertex normals from coordinates (any shape) and triangles."""
    a, b, c = co[tris[:, 0]], co[tris[:, 1]], co[tris[:, 2]]
    fn = np.cross(b - a, c - a)
    vn = np.zeros_like(co)
    for k in range(3):
        np.add.at(vn, tris[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)


def edges_of(me):
    e = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", e)
    return e.reshape(-1, 2)


def neighbours(me, n=None):
    """CSR adjacency (offsets, indices) from mesh edges."""
    n = n or len(me.vertices)
    e = edges_of(me)
    src = np.concatenate([e[:, 0], e[:, 1]])
    dst = np.concatenate([e[:, 1], e[:, 0]])
    order = np.argsort(src, kind="stable")
    src, dst = src[order], dst[order]
    off = np.zeros(n + 1, dtype=np.int64)
    np.add.at(off, src + 1, 1)
    off = np.cumsum(off)
    return off, dst


def laplacian_avg(x, off, idx):
    """Uniform neighbour average of per-vertex data x (N,...) using CSR adjacency."""
    s = np.add.reduceat(x[idx], off[:-1], axis=0) if len(idx) else np.zeros_like(x)
    cnt = np.diff(off)
    s[cnt == 0] = x[cnt == 0]
    cnt = np.maximum(cnt, 1)
    return s / cnt.reshape((-1,) + (1,) * (x.ndim - 1))


def smooth(x, off, idx, iters=1, lam=0.5, mask=None):
    for _ in range(iters):
        avg = laplacian_avg(x, off, idx)
        d = (avg - x) * lam
        if mask is not None:
            d = d * mask.reshape((-1,) + (1,) * (x.ndim - 1))
        x = x + d
    return x


# ----------------------------------------------------------------------------- shape keys

def shape_dict(obj):
    """{name: (N,3) coords} for every non-basis shape key."""
    out = {}
    me = obj.data
    if not me.shape_keys:
        return out
    n = len(me.vertices)
    for k in me.shape_keys.key_blocks[1:]:
        a = np.empty(n * 3, dtype=np.float32)
        k.data.foreach_get("co", a)
        out[k.name] = a.reshape(-1, 3).astype(np.float64)
    return out


def basis_co(obj):
    me = obj.data
    if not me.shape_keys:
        return get_co(obj)
    a = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.shape_keys.key_blocks[0].data.foreach_get("co", a)
    return a.reshape(-1, 3).astype(np.float64)


def add_shape(obj, name, co):
    if not obj.data.shape_keys:
        obj.shape_key_add(name="Basis", from_mix=False)
    k = obj.data.shape_keys.key_blocks.get(name) or obj.shape_key_add(name=name, from_mix=False)
    k.data.foreach_set("co", np.asarray(co, dtype=np.float32).ravel())
    k.value = 0.0
    return k


def set_shapes(obj, shapes, basis=None, eps=1e-5):
    """Replace all shape keys by `shapes` ({name: coords}); skips shapes with no effect."""
    if obj.data.shape_keys:
        obj.shape_key_clear()
    if basis is not None:
        set_co(obj, basis)
    base = get_co(obj)
    for n, co in shapes.items():
        if np.abs(co - base).max() > eps:
            add_shape(obj, n, co)


# ----------------------------------------------------------------------------- weights

def bone_weights(obj, prefix=P):
    """(names, W[N,B]) of the deform groups whose name starts with prefix."""
    me = obj.data
    names = [g.name for g in obj.vertex_groups if g.name.startswith(prefix)]
    col = {obj.vertex_groups[n].index: i for i, n in enumerate(names)}
    W = np.zeros((len(me.vertices), len(names)))
    for v in me.vertices:
        for g in v.groups:
            j = col.get(g.group)
            if j is not None:
                W[v.index, j] = g.weight
    return names, W


def limit_normalize(W, k=4, floor=0.01):
    """Keep the k largest influences per row, drop tiny ones, renormalise."""
    W = W.copy()
    if W.shape[1] > k:
        idx = np.argsort(-W, axis=1)
        drop = idx[:, k:]
        np.put_along_axis(W, drop, 0.0, axis=1)
    W[W < floor] = 0.0
    s = W.sum(1, keepdims=True)
    return np.where(s > 0, W / np.maximum(s, 1e-12), 0.0)


def write_weights(obj, names, W, prefix=P, k=4):
    """Replace every deform group of obj with W (limited to k influences)."""
    for g in list(obj.vertex_groups):
        if g.name.startswith(prefix):
            obj.vertex_groups.remove(g)
    W = limit_normalize(W, k)
    for j, n in enumerate(names):
        nz = np.nonzero(W[:, j] > 0)[0]
        if len(nz) == 0:
            continue
        g = obj.vertex_groups.new(name=n)
        # group by weight value is slow; add one by one but in bulk via foreach of unique weights
        w = W[nz, j]
        for vi, wv in zip(nz.tolist(), w.tolist()):
            g.add([vi], wv, "REPLACE")


def rigid_weights(obj, bone_pairs):
    """Same fixed weights on every vertex: [(bone, w), ...]."""
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    idx = list(range(len(obj.data.vertices)))
    for b, w in bone_pairs:
        obj.vertex_groups.new(name=P + b if not b.startswith(P) else b).add(idx, w, "REPLACE")


# ----------------------------------------------------------------------------- binding (nearest surface)

class Binding:
    """Barycentric binding of points to the nearest triangle of a source mesh (rest coords), to transfer
    per-vertex data (deltas, weights) of the source to the points."""

    def __init__(self, src_co, src_tris, points, max_dist=1.0, normals=None, prefer_front=False):
        self.tree = BVHTree.FromPolygons([Vector(c) for c in src_co], src_tris.tolist(), all_triangles=True)
        n = len(points)
        self.I = np.zeros((n, 3), dtype=np.int64)
        self.W = np.zeros((n, 3))
        self.D = np.full(n, 1e9)
        self.side = np.zeros(n)
        for i, p in enumerate(points):
            loc, nrm, fi, d = self.tree.find_nearest(Vector(p), max_dist)
            if fi is None:
                continue
            tri = src_tris[fi]
            a, b, c = src_co[tri[0]], src_co[tri[1]], src_co[tri[2]]
            w = _bary(np.array(loc), a, b, c)
            self.I[i] = tri
            self.W[i] = w
            self.D[i] = d
            self.side[i] = float(np.dot(np.array(p) - np.array(loc), np.array(nrm)))

    def transfer(self, data):
        """data (Nsrc, ...) -> (Npoints, ...)."""
        return (data[self.I] * self.W.reshape(self.W.shape + (1,) * (data.ndim - 1))).sum(1)


def _bary(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-20:
        return np.array((1.0, 0.0, 0.0))
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    u = 1 - v - w
    bw = np.clip(np.array((u, v, w)), 0, 1)
    return bw / max(bw.sum(), 1e-12)


# ----------------------------------------------------------------------------- objects / scene

def mesh_obj(name, verts, faces, coll=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    o = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(o)
    return o


def remove(obj):
    if obj is None:
        return
    d = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if d is not None and d.users == 0:
        if isinstance(d, bpy.types.Mesh):
            bpy.data.meshes.remove(d)


def apply_modifiers(obj, keep=("ARMATURE",)):
    """Apply every modifier except those in keep (no shape keys allowed)."""
    dg = bpy.context.evaluated_depsgraph_get()
    saved = [(m.name, m.type) for m in obj.modifiers if m.type in keep]
    for m in list(obj.modifiers):
        if m.type in keep:
            m.show_viewport = False
    dg.update()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = obj.data
    obj.modifiers.clear() if not saved else [obj.modifiers.remove(m) for m in list(obj.modifiers) if m.type not in keep]
    obj.data = me
    for m in obj.modifiers:
        m.show_viewport = True
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def link_armature(obj, rig):
    obj.parent = rig
    obj.matrix_parent_inverse.identity()
    if not any(m.type == "ARMATURE" for m in obj.modifiers):
        m = obj.modifiers.new("Armature", "ARMATURE")
        m.object = rig


def enable_gpu():
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "METAL"
    sc = bpy.context.scene
    sc.cycles.device = "GPU"


# ----------------------------------------------------------------------------- images (numpy <-> bpy)

def read_image(path):
    """float32 (H,W,4) RGBA, row 0 = bottom (Blender convention)."""
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)


def write_image(arr, path, depth=8):
    """Write a float array (H,W) / (H,W,3) / (H,W,4) in [0,1] (row 0 = bottom) as an RGBA PNG; values are stored
    as-is (no colour management), so sRGB data must already be sRGB-encoded."""
    arr = np.asarray(arr, dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[..., None]
    h, w, c = arr.shape
    rgba = np.ones((h, w, 4), dtype=np.float32)
    if c == 1:
        rgba[..., :3] = arr
    elif c == 3:
        rgba[..., :3] = arr
    else:
        rgba[...] = arr[..., :4]
    img = bpy.data.images.new("__w_" + os.path.basename(path), w, h, alpha=True, float_buffer=depth == 16)
    img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(np.clip(rgba, 0, 1).ravel())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    return path


def srgb_to_lin(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def hexrgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def nrm(v):
    v = np.asarray(v, dtype=np.float64)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def save(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    log("saved", path)


def taubin(x, off, idx, iters=10, lam=0.5, mu=-0.53, mask=None):
    """Volume-preserving low-pass smoothing (Taubin lambda/mu)."""
    for _ in range(iters):
        x = smooth(x, off, idx, 1, lam, mask)
        x = smooth(x, off, idx, 1, mu, mask)
    return x


def relax_tangent(x, tris, off, idx, iters=10, lam=0.5, mask=None):
    """Even out vertex spacing inside the surface (moves only in the tangent plane)."""
    for _ in range(iters):
        n = vertex_normals(x, tris)
        d = laplacian_avg(x, off, idx) - x
        d -= n * (d * n).sum(1, keepdims=True)
        if mask is not None:
            d *= mask[:, None]
        x = x + d * lam
    return x
