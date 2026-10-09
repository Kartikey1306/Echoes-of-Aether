"""Real-geometry panels on a skinned garment: cut the mesh exactly along the zero isoline of a signed field, then
raise the inside region as a bonded overlay (extruded along the rest normals, with a wall). Shape keys and weights
survive: shape deltas ride along as interpolated vertex attributes and are rebuilt afterwards."""
import bpy, bmesh
import numpy as np
from mathutils import Vector
import gv


def raise_panels(o, s, height, exclude=None, name="panel"):
    """s: per-vertex signed field (> 0 inside, metres). exclude: per-vertex bool (never raised, e.g. near hems)."""
    me = o.data
    s = np.asarray(s, float).copy()
    if exclude is not None:
        s[exclude] = -1.0
    s[np.abs(s) < 1e-6] = -1e-6
    if not (s > 0).any():
        return 0
    X = gv.basis_co(o)
    # rest normals
    tris = gv.tri_index(me)
    N0 = gv.vertex_normals(X, tris)
    # shape deltas -> vector attributes; drop the keys (bmesh shape-key round trips re-apply basis offsets)
    shapes = gv.shape_dict(o)
    keep_names = list(shapes)
    for i, (n, co) in enumerate(shapes.items()):
        a = me.attributes.new(f"_sk{i}", "FLOAT_VECTOR", "POINT")
        a.data.foreach_set("vector", (co - X).astype(np.float32).ravel())
    if me.shape_keys:
        o.shape_key_clear()
    a = me.attributes.new("_n0", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", N0.astype(np.float32).ravel())
    a = me.attributes.new("_sdf", "FLOAT", "POINT")
    a.data.foreach_set("value", s.astype(np.float32))
    bm = bmesh.new()
    bm.from_mesh(me)
    sl = bm.verts.layers.float["_sdf"]
    pm = bm.faces.layers.int.get("panel") or bm.faces.layers.int.new("panel")
    nwl = bm.verts.layers.int.new("_new")
    # 1) split every edge crossing the isoline
    cross = [(e, e.verts[0], e.verts[1]) for e in bm.edges if e.verts[0][sl] * e.verts[1][sl] < 0]
    for e, v0, v1 in cross:
        s0, s1 = v0[sl], v1[sl]
        t = s0 / (s0 - s1)
        ne, nv = bmesh.utils.edge_split(e, v0, float(np.clip(t, 0.03, 0.97)))
        nv[sl] = 0.0
    # 2) connect the zero verts of every crossed face (consecutive pairs in loop order)
    pairs = []
    for f in bm.faces:
        ring = list(f.verts)
        zi = [i for i, v in enumerate(ring) if v[sl] == 0.0]
        if len(zi) < 2:
            continue
        if len(zi) == 2:
            i0, i1 = zi
            if (i1 - i0) % len(ring) in (1, len(ring) - 1):
                continue
            pairs.append((ring[i0], ring[i1]))
        else:
            for k in range(0, len(zi) - 1, 2):
                pairs.append((ring[zi[k]], ring[zi[k + 1]]))
    fails = 0
    for a_, b_ in pairs:
        try:
            r_ = bmesh.ops.connect_verts(bm, verts=[a_, b_])
            if not r_["edges"]:
                fails += 1
        except Exception:
            fails += 1
    # 3) raise the inside region
    inside = [f for f in bm.faces if all(v[sl] >= 0 for v in f.verts) and any(v[sl] > 0 for v in f.verts)]
    if not inside:
        bm.free()
        return 0
    ret = bmesh.ops.extrude_face_region(bm, geom=inside, use_keep_orig=False)
    region = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMFace)]
    bmesh.ops.delete(bm, geom=inside, context="FACES")
    nl = bm.verts.layers.float_vector["_n0"]
    newv = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
    for v in newv:
        n = Vector(v[nl]).normalized()
        v.co += n * height
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    # walls = faces marked as panel that are not the raised region: panel = 2, hard edges all round them so the
    # panel reads as a crisp bonded layer and no wall normal leaks into the fabric shading
    for v in newv:
        if v.is_valid:
            v[nwl] = 1
    nwall = 0
    for f in bm.faces:
        k = sum(v[nwl] for v in f.verts)
        if k == len(f.verts):
            f[pm] = 1
        elif k > 0:
            f[pm] = 2
            nwall += 1
    for f in bm.faces:
        if f[pm] == 2:
            for e in f.edges:
                if any(lf[pm] != 2 for lf in e.link_faces):
                    e.smooth = False
    bm.to_mesh(me)
    bm.free()
    me.update()
    # panel id as a float face attribute (rasterised by the painter)
    pi_ = np.zeros(len(me.polygons), np.int32)
    me.attributes["panel"].data.foreach_get("value", pi_)
    me.attributes.remove(me.attributes["panel"])
    a = me.attributes.new("panel", "FLOAT", "FACE")
    a.data.foreach_set("value", pi_.astype(np.float32))
    # rebuild the shape keys from the carried deltas
    Xn = np.array([v.co[:] for v in me.vertices])
    if keep_names:
        o.shape_key_add(name="Basis", from_mix=False)
        for i, n in enumerate(keep_names):
            a = me.attributes[f"_sk{i}"]
            d = np.empty(len(Xn) * 3, np.float32)
            a.data.foreach_get("vector", d)
            gv.add_shape(o, n, Xn + d.reshape(-1, 3))
    for nm in [f"_sk{i}" for i in range(len(keep_names))] + ["_n0", "_sdf", "_new"]:
        if nm in me.attributes:
            me.attributes.remove(me.attributes[nm])
    for p_ in me.polygons:
        p_.use_smooth = True
    gv.log(o.name, name, "raised", len(inside), "faces by %.1f mm," % (height * 1000), "cuts", len(cross), "fails", fails, "walls", nwall)
    return len(inside)


def vertex_regions(o, part, design):
    """Per-vertex region ids for a garment at stage 3 (bone-family weights; pants split by side)."""
    X = gv.basis_co(o)
    if part != "top":
        return np.where(X[:, 0] > 0, design.LEG_L, design.LEG_R)
    names, W = gv.bone_weights(o)
    arm = {s: np.zeros(len(X)) for s in ("Left", "Right")}
    for j, n in enumerate(names):
        s_ = n[len(gv.P):]
        for side in ("Left", "Right"):
            if s_.startswith(side) and ("Arm" in s_ or "Hand" in s_):
                arm[side] += W[:, j]
    r = np.full(len(X), design.TORSO)
    r[arm["Left"] > 0.5] = design.ARM_L
    r[arm["Right"] > 0.5] = design.ARM_R
    return r
