"""Mesh operations for Kael v2: weights as matrices, adjacency, smoothing, subdivision with shape keys,
numpy linear-blend skinning (pose evaluation, inverse skinning for corrective shapes)."""
import bpy, bmesh
import numpy as np
from mathutils import Matrix, Vector


# ----------------------------------------------------------------------------- weights


def get_weights(o, prefix="mixamorig:"):
    """(names, W[nv, nb]) for deform groups starting with prefix."""
    names = [g.name for g in o.vertex_groups if g.name.startswith(prefix)]
    idx = {o.vertex_groups[n].index: k for k, n in enumerate(names)}
    W = np.zeros((len(o.data.vertices), len(names)), np.float64)
    for v in o.data.vertices:
        for g in v.groups:
            k = idx.get(g.group)
            if k is not None:
                W[v.index, k] = g.weight
    return names, W


def set_weights(o, names, W, eps=1e-4, prefix="mixamorig:"):
    """Replace all prefix groups with W (columns named by names)."""
    for g in list(o.vertex_groups):
        if g.name.startswith(prefix):
            o.vertex_groups.remove(g)
    for k, n in enumerate(names):
        col = W[:, k]
        nz = np.where(col > eps)[0]
        if not len(nz):
            continue
        g = o.vertex_groups.new(name=n)
        # group by identical weight would be faster; per-vertex add is fine for <100k verts
        for i in nz:
            g.add([int(i)], float(col[i]), "REPLACE")


def limit_normalize(W, max_infl=4, min_w=0.01):
    W = np.array(W, np.float64)
    if W.shape[1] > max_infl:
        order = np.argsort(-W, axis=1)
        keep = np.zeros_like(W, bool)
        np.put_along_axis(keep, order[:, :max_infl], True, axis=1)
        W = np.where(keep, W, 0.0)
    W[W < min_w] = 0.0
    s = W.sum(1, keepdims=True)
    return np.where(s > 0, W / np.maximum(s, 1e-12), 0.0)


# ----------------------------------------------------------------------------- adjacency / smoothing


def edges_of(o):
    me = o.data
    e = np.empty(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", e)
    return e.reshape(-1, 2)


def neighbor_mean(X, E, n):
    """Mean of each vertex's neighbours (E edges, n verts); X (n, ...)."""
    acc = np.zeros_like(X, dtype=np.float64)
    cnt = np.zeros(n)
    np.add.at(acc, E[:, 0], X[E[:, 1]])
    np.add.at(acc, E[:, 1], X[E[:, 0]])
    np.add.at(cnt, E[:, 0], 1)
    np.add.at(cnt, E[:, 1], 1)
    cnt = np.maximum(cnt, 1)
    return acc / cnt.reshape((-1,) + (1,) * (X.ndim - 1))


def smooth(X, E, iters=1, lam=0.5, mask=None):
    """Laplacian smoothing of per-vertex data X; mask (n,) in 0..1 scales the step."""
    X = np.array(X, np.float64)
    n = len(X)
    m = None if mask is None else np.asarray(mask, np.float64).reshape((-1,) + (1,) * (X.ndim - 1))
    for _ in range(iters):
        nb = neighbor_mean(X, E, n)
        step = lam * (nb - X)
        X = X + (step if m is None else step * m)
    return X


def taubin(X, E, iters=1, lam=0.5, mu=-0.53, mask=None):
    """Volume preserving smoothing (lambda/mu)."""
    for _ in range(iters):
        X = smooth(X, E, 1, lam, mask)
        X = smooth(X, E, 1, mu, mask)
    return X


# ----------------------------------------------------------------------------- shape keys


def shape_arrays(o):
    """(basis, {name: coords}) from shape keys (or plain coords)."""
    me = o.data
    n = len(me.vertices)
    if not me.shape_keys:
        a = np.empty(n * 3, np.float32); me.vertices.foreach_get("co", a)
        return a.reshape(-1, 3).astype(np.float64), {}
    kb = me.shape_keys.key_blocks
    out = {}
    for k in kb:
        a = np.empty(n * 3, np.float32); k.data.foreach_get("co", a)
        out[k.name] = a.reshape(-1, 3).astype(np.float64)
    basis = out.pop(kb[0].name)
    return basis, out


def set_shapes(o, basis, shapes, keep_values=None):
    """Rebuild the shape keys of o from arrays (basis + named absolute coordinates)."""
    me = o.data
    if me.shape_keys:
        o.shape_key_clear()
    me.vertices.foreach_set("co", np.asarray(basis, np.float32).ravel())
    me.update()
    if not shapes:
        return
    o.shape_key_add(name="Basis", from_mix=False)
    for name, co in shapes.items():
        k = o.shape_key_add(name=name, from_mix=False)
        k.data.foreach_set("co", np.asarray(co, np.float32).ravel())
        k.value = (keep_values or {}).get(name, 0.0)


def subdivide_with_shapes(o, levels=1, uv_smooth="PRESERVE_BOUNDARIES"):
    """Catmull-Clark subdivide o in place: weights and UVs interpolate through the modifier, every shape key is
    re-evaluated through the same subdivision (topology identical across evaluations)."""
    basis, shapes = shape_arrays(o)
    me = o.data
    if me.shape_keys:
        o.shape_key_clear()
    mods = [(m.name, m.type, getattr(m, "object", None)) for m in o.modifiers]
    for m in list(o.modifiers):
        o.modifiers.remove(m)
    sub = o.modifiers.new("k_sub", "SUBSURF")
    sub.levels = sub.render_levels = levels
    sub.uv_smooth = uv_smooth
    sub.boundary_smooth = "ALL"
    sub.use_limit_surface = True

    def evaluate(co):
        me.vertices.foreach_set("co", np.asarray(co, np.float32).ravel())
        me.update()
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        ev = o.evaluated_get(dg)
        m2 = ev.to_mesh()
        a = np.empty(len(m2.vertices) * 3, np.float32); m2.vertices.foreach_get("co", a)
        ev.to_mesh_clear()
        return a.reshape(-1, 3).astype(np.float64)

    new_shapes = {n: evaluate(c) for n, c in shapes.items()}
    new_basis = evaluate(basis)
    # apply the modifier for real (weights, UVs, attributes, topology)
    bpy.context.view_layer.objects.active = o
    with bpy.context.temp_override(object=o, active_object=o):
        bpy.ops.object.modifier_apply(modifier="k_sub")
    set_shapes(o, new_basis, new_shapes)
    for (n, t, ob) in mods:
        if t == "ARMATURE":
            m = o.modifiers.new(n, "ARMATURE"); m.object = ob
    return o


# ----------------------------------------------------------------------------- skinning (numpy LBS)


def pose_matrices(rig, names):
    """4x4 skinning matrices (pose @ rest^-1, armature space -> world) per bone name."""
    out = np.zeros((len(names), 4, 4))
    mw = np.array(rig.matrix_world)
    mwi = np.linalg.inv(mw)
    for k, n in enumerate(names):
        pb = rig.pose.bones.get(n)
        if pb is None:
            out[k] = np.eye(4)
            continue
        M = np.array(pb.matrix) @ np.linalg.inv(np.array(pb.bone.matrix_local))
        out[k] = mw @ M @ mwi
    return out


def skin_matrices(W, Ms):
    """Per-vertex blended 4x4 matrices (n,4,4)."""
    return np.einsum("vb,bij->vij", W, Ms)


def lbs(co, W, Ms):
    S = skin_matrices(W, Ms)
    h = np.concatenate([co, np.ones((len(co), 1))], 1)
    return np.einsum("vij,vj->vi", S, h)[:, :3], S


def unskin_delta(S, delta):
    """Rest-space delta d such that LBS(rest + d) = LBS(rest) + delta (linear part of the blended matrix)."""
    A = S[:, :3, :3]
    return np.linalg.solve(A, delta[..., None])[..., 0]
