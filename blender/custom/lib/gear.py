# SNAPSHOT of blender/scripts/gear.py taken 2026-10-04 for the customisation pipeline (blender/custom). Do not edit; re-copy if needed.
"""HD character gear toolkit: garment shells, machined armour plates, straps, buckles, pouches, cables and glow
seams, built on the MPFB body surface.

Everything is modelled on the rest (basis) body. Skin weights and blendshapes (customisation morphs and
expressions) are transferred from the body through a nearest-surface binding, so any topology works.
Per-vertex attributes (wear, cavity, local plate coordinates, panel ids) are stored as mesh attributes and used
by texbake.py to paint the texture atlases.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from meshutil import SurfaceBinding, add_shape_key
from outfit import BodyData

LANDMARKS = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftShoulder", "RightShoulder", "LeftArm", "RightArm",
             "LeftForeArm", "RightForeArm", "LeftHand", "RightHand", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg",
             "LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase", "LeftEye", "RightEye", "HeadTop_End"]


def nrm(v):
    v = np.asarray(v, dtype=np.float64)
    return v / max(np.linalg.norm(v), 1e-12)


def ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------- context


class Ctx:
    """Body analysis + bookkeeping for one character."""

    def __init__(self, body, rig, name):
        self.body, self.rig, self.name = body, rig, name
        self.B = B = BodyData(body, rig)
        self.basis = B.basis
        self.vn = B.normals(B.basis)
        self.tree = BVHTree.FromPolygons([Vector(c) for c in B.basis], B.faces)
        self.L, self.T = {}, {}
        for b in LANDMARKS:
            if "mixamorig:" + b in B.bones:
                self.L[b] = B.head(b)
                self.T[b] = B.tail(b)
        self.bone_names = sorted(B.w)
        self.Wb = np.stack([B.w[n] for n in self.bone_names], 1)
        self.region = self._regions()
        self.objects = {}
        self.cover = []          # (interior body verts) per garment, for hidden-face stripping
        self.stack = []          # objects that form the outer surface for layering
        self._outer = None

    def _regions(self):
        W = self.B.wsum
        return {
            "head": W(["mixamorig:Head", "mixamorig:HeadTop_End", "mixamorig:LeftEye", "mixamorig:RightEye"]),
            "neck": W(["mixamorig:Neck"]),
            "torso": W(["mixamorig:Spine", "mixamorig:Spine1", "mixamorig:Spine2", "mixamorig:LeftShoulder", "mixamorig:RightShoulder",
                        "mixamorig:LeftBreast", "mixamorig:RightBreast"]),
            "hips": W(["mixamorig:Hips"]),
            "uarmL": W(["mixamorig:LeftArm"]), "uarmR": W(["mixamorig:RightArm"]),
            "farmL": W(["mixamorig:LeftForeArm"]), "farmR": W(["mixamorig:RightForeArm"]),
            "handL": W(["mixamorig:LeftHand*"]), "handR": W(["mixamorig:RightHand*"]),
            "thighL": W(["mixamorig:LeftUpLeg"]), "thighR": W(["mixamorig:RightUpLeg"]),
            "shinL": W(["mixamorig:LeftLeg"]), "shinR": W(["mixamorig:RightLeg"]),
            "footL": W(["mixamorig:LeftFoot", "mixamorig:LeftToe*"]), "footR": W(["mixamorig:RightFoot", "mixamorig:RightToe*"]),
        }

    # ------------------------------------------------------------- surfaces
    def outer_tree(self):
        """BVH of the body plus every stacked garment (so plates/straps sit on top of clothing)."""
        if self._outer is None:
            verts = [Vector(c) for c in self.basis]
            polys = [list(f) for f in self.B.faces]
            for o in self.stack:
                me = o.data
                off = len(verts)
                verts += [v.co.copy() for v in me.vertices]
                polys += [[off + i for i in p.vertices] for p in me.polygons]
            self._outer = BVHTree.FromPolygons(verts, polys)
        return self._outer

    def push_stack(self, obj):
        self.stack.append(obj)
        self._outer = None

    def cast(self, origin, direction, dist=1.0, tree=None):
        tree = tree or self.outer_tree()
        hit, n, _, d = tree.ray_cast(Vector(origin), Vector(direction).normalized(), dist)
        return (np.array(hit), np.array(n)) if hit is not None else (None, None)

    def nearest(self, p, tree=None, dist=1.0):
        tree = tree or self.outer_tree()
        hit, n, _, d = tree.find_nearest(Vector(p), dist)
        return (np.array(hit), np.array(n)) if hit is not None else (np.array(p), np.array((0, 0, 1.0)))

    def limb_point(self, bone, t, phi, push=0.0, ref=None, tree=None, end=None, R=0.13):
        """Point on the outer surface around a limb bone: t along the bone (0 head .. 1 tail/end), phi around it
        (radians; 0 = reference direction, positive towards ref x axis). ref: up-reference (default world Z or -Y)."""
        a = self.L[bone]
        b = self.L[end] if end else self.T[bone]
        ax = nrm(b - a)
        r0 = np.array(ref if ref is not None else ((0, 0, 1.0) if abs(ax[2]) < 0.7 else (0, -1.0, 0)))
        r0 = nrm(r0 - ax * (r0 @ ax))
        r1 = np.cross(ax, r0)
        c = a + (b - a) * t
        d = r0 * math.cos(phi) + r1 * math.sin(phi)
        hit, n = self.cast(c + d * R, -d, R + 0.02, tree)
        if hit is None:
            return c + d * 0.05, d
        return hit + n * push, n

    def torso_point(self, z, phi, push=0.0, tree=None, cy=None, R=0.32):
        """Point on the outer surface of the torso: height z, angle phi (0 = front -Y, +pi/2 = character left +X)."""
        cy = self.L["Spine1"][1] if cy is None else cy
        c = np.array((0.0, cy, z))
        d = np.array((math.sin(phi), -math.cos(phi), 0.0))
        hit, n = self.cast(c + d * R, -d, R + 0.05, tree)
        if hit is None:
            return c + d * 0.15, d
        return hit + n * push, n

    # ------------------------------------------------------------- skinning + shapes
    def finalize(self, obj, bone=None, weight_bones=None, max_infl=4):
        """Parent to the rig, transfer weights (rigid to `bone`, or interpolated from the body surface) and every
        body blendshape through a surface binding."""
        me = obj.data
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        bind = SurfaceBinding(self.body, self.basis, co, max_dist=1.0)
        for g in list(obj.vertex_groups):
            obj.vertex_groups.remove(g)
        if bone:
            vg = obj.vertex_groups.new(name="mixamorig:" + bone)
            vg.add(list(range(len(co))), 1.0, "REPLACE")
        else:
            W = (bind.W[..., None] * self.Wb[bind.I]).sum(1)
            if weight_bones:
                keep = np.array([any(n == "mixamorig:" + b for b in weight_bones) for n in self.bone_names])
                W = W * keep[None]
            order = np.argsort(-W, axis=1)[:, :max_infl]
            top = np.take_along_axis(W, order, 1)
            top[top < 0.02] = 0
            s = top.sum(1, keepdims=True)
            top = np.where(s > 0, top / np.maximum(s, 1e-9), 0)
            groups = {}
            for vi in range(len(co)):
                for k in range(max_infl):
                    w = top[vi, k]
                    if w <= 0:
                        continue
                    bn = self.bone_names[order[vi, k]]
                    g = groups.get(bn)
                    if g is None:
                        g = groups[bn] = obj.vertex_groups.new(name=bn)
                    g.add([vi], float(w), "REPLACE")
        obj.parent = self.rig
        if not any(m.type == "ARMATURE" for m in obj.modifiers):
            mod = obj.modifiers.new("Armature", "ARMATURE")
            mod.object = self.rig
        if obj.data.shape_keys:
            obj.shape_key_clear()
        for name, sco in self.B.shapes.items():
            d = bind.transfer(sco - self.basis)
            if np.abs(d).max() > 1e-5:
                add_shape_key(obj, name, co + d)
        self.objects[obj.name] = obj
        return obj


# ----------------------------------------------------------------------------- mesh assembly


class Part:
    """Accumulates geometry (verts, faces, per-face material, per-loop UVs, per-vertex attributes, sharp edges)."""

    def __init__(self, name):
        self.name = name
        self.V = []
        self.F = []
        self.FM = []
        self.FUV = []
        self.A = {}
        self.sharp = []
        self.n = 0

    def add(self, verts, faces, mat, uvs=None, attrs=None, sharp=None):
        verts = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
        base = self.n
        self.V.append(verts)
        mats = mat if isinstance(mat, (list, tuple)) else [mat] * len(faces)
        for i, f in enumerate(faces):
            self.F.append([base + v for v in f])
            self.FM.append(mats[i])
            self.FUV.append(uvs[i] if uvs is not None else None)
        for k in set(self.A) | set(attrs or {}):
            arr = self.A.setdefault(k, [np.zeros(base)] if base else [])
            if attrs and k in attrs:
                arr.append(np.broadcast_to(np.asarray(attrs[k], dtype=np.float64), (len(verts),)).copy())
            else:
                arr.append(np.zeros(len(verts)))
        for a, b in (sharp or []):
            self.sharp.append((base + a, base + b))
        self.n += len(verts)
        return base

    def merge(self, other):
        base = self.add(np.vstack(other.V) if other.V else np.zeros((0, 3)), [[v for v in f] for f in other.F], list(other.FM),
                        other.FUV, {k: np.concatenate(v) for k, v in other.A.items()}, other.sharp)
        return base

    def build(self, mat_order=None, max_edge=0.13):
        V = np.vstack(self.V) if self.V else np.zeros((0, 3))
        if max_edge and len(self.F):
            keep = []
            for i, f in enumerate(self.F):
                pts = V[f]
                if np.linalg.norm(pts - np.roll(pts, 1, 0), axis=1).max() <= max_edge:
                    keep.append(i)
            if len(keep) < len(self.F):
                print("PART", self.name, "dropped stray faces:", len(self.F) - len(keep))
                self.F = [self.F[i] for i in keep]; self.FM = [self.FM[i] for i in keep]; self.FUV = [self.FUV[i] for i in keep]
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([tuple(v) for v in V], [], self.F)
        me.update()
        mats = mat_order or list(dict.fromkeys(self.FM))
        for m in mats:
            me.materials.append(get_mat(m))
        idx = np.array([mats.index(m) for m in self.FM], dtype=np.int32)
        me.polygons.foreach_set("material_index", idx)
        uvl = me.uv_layers.new(name="UVMap")
        data = np.zeros((len(me.loops), 2))
        for p in me.polygons:
            u = self.FUV[p.index]
            if u is not None:
                for k, li in enumerate(p.loop_indices):
                    data[li] = u[k]
            else:
                # Box projection in metres (x4) for faces without explicit UVs.
                n = np.abs(np.array(p.normal[:]))
                ax = int(np.argmax(n))
                for li in p.loop_indices:
                    c = V[me.loops[li].vertex_index]
                    q = [(c[1], c[2]), (c[0], c[2]), (c[0], c[1])][ax]
                    data[li] = (q[0] * 4, q[1] * 4)
        uvl.data.foreach_set("uv", data.ravel())
        for k, arrs in self.A.items():
            a = np.concatenate(arrs)
            at = me.attributes.new(k, "FLOAT", "POINT")
            at.data.foreach_set("value", a.astype(np.float32))
        me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), dtype=bool))
        if self.sharp:
            me.update()
            lookup = {}
            for e in me.edges:
                a, b = e.vertices
                lookup[(min(a, b), max(a, b))] = e.index
            sharp = np.zeros(len(me.edges), dtype=bool)
            for a, b in self.sharp:
                ei = lookup.get((min(a, b), max(a, b)))
                if ei is not None:
                    sharp[ei] = True
            at = me.attributes.get("sharp_edge") or me.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
            at.data.foreach_set("value", sharp)
        obj = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(obj)
        return obj


# ----------------------------------------------------------------------------- materials (preview + slot names)

PREVIEW = {}


def get_mat(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        col, rough, metal, emit = PREVIEW.get(name, ((0.5, 0.5, 0.5), 0.5, 0.0, None))
        b = m.node_tree.nodes.get("Principled BSDF")
        b.inputs["Base Color"].default_value = (*col, 1)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        if emit:
            b.inputs["Emission Color"].default_value = (*emit[0], 1)
            b.inputs["Emission Strength"].default_value = emit[1]
    return m


def srgb(h, mul=1.0):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple((x ** 2.2) * mul for x in c)


# ----------------------------------------------------------------------------- modifiers


def apply_modifiers(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    bpy.data.meshes.remove(old)
    me.name = obj.name


def get_co(obj):
    a = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", a)
    return a.reshape(-1, 3)


def set_co(obj, co):
    obj.data.vertices.foreach_set("co", np.asarray(co, dtype=np.float32).ravel())
    obj.data.update()


def vnormals(obj):
    obj.data.update()
    a = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("normal", a)
    return a.reshape(-1, 3)


def attr(obj, name):
    at = obj.data.attributes.get(name)
    if at is None:
        return np.zeros(len(obj.data.vertices))
    a = np.empty(len(at.data))
    at.data.foreach_get("value", a)
    return a


def set_attr(obj, name, values):
    me = obj.data
    at = me.attributes.get(name) or me.attributes.new(name, "FLOAT", "POINT")
    at.data.foreach_set("value", np.asarray(values, dtype=np.float32))


# ----------------------------------------------------------------------------- garment shells


def shell(ctx, name, vmask, offset, mat_fn=None, mats=("Garment_Top",), smooth=4, subdiv=1, rim=0.005,
          disp=None, min_clear=0.003, attrs_fn=None, cover=True, stack=True, faces=None, refine_fn=None, refine_iter=1,
          envelope=0, env_gap=0.006, bsmooth=10, floor_z=None):
    """Garment shell over the body faces whose vertices are all in `vmask`.
    offset(P, N) -> metres (per body vertex); mat_fn(face_center, face_normal) -> material name;
    disp(P, N) -> metres along the normal after subdivision (folds, padding); attrs_fn(P, N) -> {name: values}."""
    B = ctx.B
    fids = faces if faces is not None else [i for i, f in enumerate(B.faces) if all(vmask[v] for v in f)]
    used = sorted({v for fi in fids for v in B.faces[fi]})
    inv = {v: i for i, v in enumerate(used)}
    F = [[inv[v] for v in B.faces[fi]] for fi in fids]
    P0 = ctx.basis[used]
    N0 = ctx.vn[used]
    off = np.asarray(offset(P0, N0), dtype=np.float64)
    out = P0 + N0 * off[:, None]
    # Boundary and neighbours for smoothing.
    ec = {}
    for f in F:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            ec[(min(a, b), max(a, b))] = ec.get((min(a, b), max(a, b)), 0) + 1
    is_b = np.zeros(len(used), bool)
    nb = [set() for _ in used]
    for (a, b), c in ec.items():
        nb[a].add(b); nb[b].add(a)
        if c == 1:
            is_b[a] = is_b[b] = True
    nbl = [list(s) for s in nb]
    # Straighten the zig-zag openings (hems, cuffs, edges) along their boundary loops.
    bnb = [[] for _ in used]
    for (a, b), c in ec.items():
        if c == 1:
            bnb[a].append(b); bnb[b].append(a)
    bidx = np.where(is_b)[0]
    for _ in range(bsmooth):
        nxt = out.copy()
        for i in bidx:
            if len(bnb[i]) == 2:
                nxt[i] = out[i] * 0.4 + (out[bnb[i][0]] + out[bnb[i][1]]) * 0.3
        out = nxt
    for _ in range(smooth):
        avg = np.array([out[n].mean(axis=0) if n else out[i] for i, n in enumerate(nbl)])
        out = np.where(is_b[:, None], out, out * 0.45 + avg * 0.55)
    d = ((out - P0) * N0).sum(1)
    low = d < off * 0.85
    out[low] += N0[low] * (off[low] * 0.85 - d[low])[:, None]
    # Envelope smoothing: strong relaxation that bridges anatomy (toes, knuckles) while never entering the body.
    for _ in range(envelope):
        avg = np.array([out[n].mean(axis=0) if n else out[i] for i, n in enumerate(nbl)])
        out = np.where(is_b[:, None], out, out * 0.3 + avg * 0.7)
        for i in range(len(out)):
            if is_b[i]:
                continue
            hit, hn, _, _ = ctx.tree.find_nearest(Vector(out[i]), 0.3)
            if hit is None:
                continue
            gap = (Vector(out[i]) - hit).dot(hn)
            if gap < env_gap:
                out[i] = np.array(hit + hn * env_gap)
    if floor_z is not None:
        out[:, 2] = np.maximum(out[:, 2], floor_z)
    if cover:
        ctx.cover.append(set(used[i] for i in range(len(used)) if not is_b[i]))
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in out], [], F)
    me.update()
    uvl = me.uv_layers.new(name="UVMap")
    data = np.zeros((len(me.loops), 2))
    for pi, p in enumerate(me.polygons):
        fuv = B.face_uv[fids[pi]]
        for k, li in enumerate(p.loop_indices):
            data[li] = fuv[k]
    uvl.data.foreach_set("uv", data.ravel())
    for m in mats:
        me.materials.append(get_mat(m))
    if mat_fn:
        idx = []
        for pi, f in enumerate(F):
            c = out[f].mean(axis=0)
            n = nrm(N0[f].mean(axis=0))
            idx.append(list(mats).index(mat_fn(c, n)))
        me.polygons.foreach_set("material_index", np.array(idx, dtype=np.int32))
    # Source body vertex positions (rest) as attributes so painting can use body-space coordinates.
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    for k, comp in enumerate("xyz"):
        set_attr(obj, "b" + comp, P0[:, k])
    if refine_fn is not None:
        refine(obj, refine_fn, refine_iter)
    if subdiv:
        m = obj.modifiers.new("sub", "SUBSURF")
        m.levels = m.render_levels = subdiv
        m.uv_smooth = "PRESERVE_BOUNDARIES"
        m.boundary_smooth = "PRESERVE_CORNERS"
        apply_modifiers(obj)
    co = get_co(obj)
    vnn = vnormals(obj)
    # Clearance against the body (subdivision shrinks the surface a little).
    if min_clear:
        for i, p in enumerate(co):
            hit, n, _, dd = ctx.tree.find_nearest(Vector(p), 0.2)
            if hit is None:
                continue
            gap = (Vector(p) - hit).dot(n)
            if gap < min_clear:
                co[i] = co[i] + np.array(n) * (min_clear - gap)
        set_co(obj, co)
        vnn = vnormals(obj)
    bp = np.stack([attr(obj, "bx"), attr(obj, "by"), attr(obj, "bz")], 1)
    if disp:
        dd = np.asarray(disp(bp, vnn), dtype=np.float64)
        set_co(obj, co + vnn * dd[:, None])
    if attrs_fn:
        for k, v in attrs_fn(bp, vnn).items():
            set_attr(obj, k, v)
    if rim:
        m = obj.modifiers.new("rim", "SOLIDIFY")
        m.thickness = rim
        m.offset = -1.0
        m.use_rim = True
        m.use_rim_only = True
        m.use_even_offset = True
        apply_modifiers(obj)
    for p in obj.data.polygons:
        p.use_smooth = True
    if stack:
        ctx.push_stack(obj)
    return obj




def refine(obj, fn, iterations=1):
    """Subdivide edges whose two vertices satisfy fn(body_space_points) -> bool (selective detail for folds)."""
    for _ in range(iterations):
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        lay = [bm.verts.layers.float.get(k) for k in ("bx", "by", "bz")]
        P = np.array([[v[lay[0]], v[lay[1]], v[lay[2]]] for v in bm.verts])
        m = np.asarray(fn(P), dtype=bool)
        edges = [e for e in bm.edges if m[e.verts[0].index] and m[e.verts[1].index]]
        if edges:
            bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True, smooth=0.0)
        bm.to_mesh(obj.data)
        bm.free()
    obj.data.update()


def limb_coords(P, a, b, ref=(0, 0, 1.0)):
    """Coordinates of points around the segment a->b: (t in metres from a along the axis, phi, radial distance)."""
    a = np.asarray(a, dtype=np.float64); b = np.asarray(b, dtype=np.float64)
    ax = nrm(b - a)
    r0 = np.asarray(ref, dtype=np.float64)
    r0 = nrm(r0 - ax * (r0 @ ax))
    r1 = np.cross(ax, r0)
    d = P - a
    t = d @ ax
    q = d - t[:, None] * ax
    phi = np.arctan2(q @ r1, q @ r0)
    return t, phi, np.linalg.norm(q, axis=1)


def hash3(P, seed=0.0):
    """Cheap deterministic pseudo-random value per 3D point (0..1)."""
    h = np.sin(P[:, 0] * 127.1 + P[:, 1] * 311.7 + P[:, 2] * 74.7 + seed * 19.19) * 43758.5453
    return h - np.floor(h)


def vnoise(P, freq, seed=0.0):
    """Smooth 3D value noise in -1..1 (trilinear interpolation of hashed lattice values)."""
    Q = np.asarray(P) * freq + seed * 13.7
    i = np.floor(Q)
    f = Q - i
    f = f * f * (3 - 2 * f)
    out = 0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                g = i + np.array((dx, dy, dz))
                w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                out = out + w * hash3(g, seed)
    return out * 2 - 1


def fbm(P, freq, octaves=4, seed=0.0, gain=0.5):
    out, amp, tot = 0, 1.0, 0
    for k in range(octaves):
        out = out + amp * vnoise(P, freq * (2 ** k), seed + k * 7.3)
        tot += amp
        amp *= gain
    return out / tot


def ring_folds(P, a, b, center, width, wavelength, amp, inner=None, seed=0.0, ref=(0, 0, 1.0)):
    """Compression folds around a joint: wavy rings across the limb axis, strongest on the `inner` side."""
    t, phi, _ = limb_coords(P, a, b, ref)
    tt = t - center
    env = np.exp(-(tt / width) ** 2)
    if inner is not None:
        env = env * (0.35 + 0.65 * (0.5 + 0.5 * np.cos(phi - inner)))
    wob = 0.35 * np.sin(phi * 2 + seed) + 0.25 * vnoise(P, 18, seed)
    return amp * env * np.sin(2 * math.pi * (tt / wavelength + wob))

def remesh_envelope(ctx, name, vmask, voxel=0.01, offset=0.009, smooth_iter=12, zmax=None, floor_z=None, mat="Boots",
                    gap=0.006, decimate=None, cover=True):
    """Closed smooth envelope around a body region (boots, mitts): fill openings, voxel remesh (merges toes and
    gaps), relax, inflate by `offset`, keep a minimum gap from the body, cut the top at zmax, flatten the floor."""
    B = ctx.B
    fids = [i for i, f in enumerate(B.faces) if all(vmask[v] for v in f)]
    used = sorted({v for fi in fids for v in B.faces[fi]})
    inv = {v: i for i, v in enumerate(used)}
    bm = bmesh.new()
    vv = [bm.verts.new(Vector(ctx.basis[v])) for v in used]
    for fi in fids:
        try:
            bm.faces.new([vv[inv[v]] for v in B.faces[fi]])
        except ValueError:
            pass
    bm.edges.ensure_lookup_table()
    bnd = [e for e in bm.edges if e.is_boundary]
    bmesh.ops.holes_fill(bm, edges=bnd, sides=0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    m = obj.modifiers.new("remesh", "REMESH")
    m.mode = "VOXEL"
    m.voxel_size = voxel
    m.adaptivity = 0.0
    m.use_smooth_shade = True
    apply_modifiers(obj)
    # Relax (Laplacian) then inflate along normals.
    bm = bmesh.new(); bm.from_mesh(obj.data)
    for _ in range(smooth_iter):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=0.6, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.normal_update()
    for v in bm.verts:
        v.co = v.co + v.normal * offset
    bm.to_mesh(obj.data); bm.free()
    co = get_co(obj)
    for i, p in enumerate(co):
        hit, hn, _, _ = ctx.tree.find_nearest(Vector(p), 0.2)
        if hit is not None:
            g = (Vector(p) - hit).dot(hn)
            if g < gap:
                co[i] = np.array(hit + hn * gap)
    if floor_z is not None:
        co[:, 2] = np.maximum(co[:, 2], floor_z)
    set_co(obj, co)
    if zmax is not None:
        bm = bmesh.new(); bm.from_mesh(obj.data)
        kill = [f for f in bm.faces if f.calc_center_median().z > zmax]
        bmesh.ops.delete(bm, geom=kill, context="FACES")
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bm.to_mesh(obj.data); bm.free()
    if decimate:
        m = obj.modifiers.new("dec", "DECIMATE"); m.ratio = decimate
        apply_modifiers(obj)
    obj.data.materials.clear()
    obj.data.materials.append(get_mat(mat))
    for p in obj.data.polygons:
        p.use_smooth = True
    # Body-space coordinates for painting: nearest body point.
    co = get_co(obj)
    bp = np.array([np.array(ctx.tree.find_nearest(Vector(p), 0.3)[0] or Vector(p)) for p in co])
    for k, comp in enumerate("xyz"):
        set_attr(obj, "b" + comp, bp[:, k])
    smart_uv(obj)
    if cover:
        ctx.cover.append(set(used))
    return obj


def smart_uv(obj, angle=1.15, margin=0.004):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=angle, island_margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.select_set(False)


# ----------------------------------------------------------------------------- hard-surface plate


def superellipse(t, a, b, n, taper=0.0, skew=0.0):
    c, s = math.cos(t), math.sin(t)
    x = math.copysign(abs(c) ** (2.0 / n), c) * a
    y = math.copysign(abs(s) ** (2.0 / n), s) * b
    x *= 1.0 - taper * (y / b)
    y += skew * x
    return x, y


def poly_outline(pts, segs, corner=0.18):
    """Closed polygon (unit-ish coords) with rounded corners, resampled to `segs` points by arc length."""
    pts = [np.asarray(p, dtype=np.float64) for p in pts]
    dense = []
    n = len(pts)
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        a = p1 + nrm(p0 - p1) * min(corner, np.linalg.norm(p0 - p1) * 0.45)
        b = p1 + nrm(p2 - p1) * min(corner, np.linalg.norm(p2 - p1) * 0.45)
        for t in np.linspace(0, 1, 6):
            dense.append((1 - t) ** 2 * a + 2 * (1 - t) * t * p1 + t * t * b)
    dense = np.array(dense)
    seg = np.linalg.norm(np.diff(np.vstack([dense, dense[:1]]), axis=0), axis=1)
    L = np.concatenate([[0], np.cumsum(seg)])
    out = []
    for k in range(segs):
        d = L[-1] * k / segs
        i = min(np.searchsorted(L, d, side="right") - 1, len(dense) - 1)
        t = (d - L[i]) / max(seg[i], 1e-9)
        out.append(dense[i] * (1 - t) + dense[(i + 1) % len(dense)] * t)
    out = np.array(out)
    # Start the outline at the point closest to +x so ring indexing is stable.
    return out


def plate(ctx, part, center, out, up, a, b, n_exp=4.0, mode="planar", pivot=None, offset=0.01, thickness=0.006,
          crown=0.004, chamfer=0.0028, groove=0.0, groove_depth=0.0012, taper=0.0, skew=0.0, segs=32, bolts=(),
          mat_top="Armor", mat_edge="Metal", mat_wall="Armor", plate_id=0.0, clearance=0.004, tree=None, rings=None,
          ridge=0.0, gasket=None, cast_r=None, poly=None, corner=0.18):
    """Machined armour plate laid on the outer surface: smooth fitted shape, crown, chamfered (metal) edge, optional
    inset groove and bolts, side wall and back. Adds geometry to `part`. Returns the local frame."""
    o = nrm(out)
    u = nrm(np.asarray(up) - o * (np.asarray(up) @ o))
    r = np.cross(u, o)
    c = np.asarray(center, dtype=np.float64)
    tree = tree or ctx.outer_tree()
    # Sample the underlying surface on a grid inside the outline and fit a quadratic height field.
    xs, ys, hs = [], [], []
    for gx in np.linspace(-1.15, 1.15, 9):
        for gy in np.linspace(-1.15, 1.15, 9):
            x, y = gx * a, gy * b
            p = c + r * x + u * y
            if mode == "radial":
                d = nrm(p - pivot)
                cr = cast_r or 0.6
                hit, _ = ctx.cast(np.asarray(pivot) + d * cr, -d, cr + 0.05, tree)
                if hit is None:
                    continue
                h = np.linalg.norm(hit - pivot)
            else:
                cr = cast_r or 0.4
                hit, _ = ctx.cast(p + o * cr, -o, cr * 2, tree)
                if hit is None:
                    continue
                h = (hit - c) @ o
            xs.append(x); ys.append(y); hs.append(h)
    xs, ys, hs = map(np.array, (xs, ys, hs))
    A = np.stack([np.ones_like(xs), xs, ys, xs * xs, xs * ys, ys * ys], 1)
    coef = np.linalg.lstsq(A, hs, rcond=None)[0]
    resid = hs - A @ coef
    lift = max(0.0, resid.max()) + clearance  # never sink into what is underneath

    def H(x, y):
        return coef @ np.array([1, x, y, x * x, x * y, y * y])

    def P(x, y, extra):
        p = c + r * x + u * y
        if mode == "radial":
            d = nrm(p - pivot)
            return np.asarray(pivot) + d * (H(x, y) + lift + offset + extra), d
        return c + r * x + u * y + o * (H(x, y) + lift + offset + extra), o

    rings = rings or ([0.0, 0.45] + ([groove - 0.035, groove, groove + 0.035] if groove else [0.72]) + [0.9, None, 1.0])
    ch_s = 1.0 - chamfer / max(min(a, b), 1e-4)
    rings = [ch_s if s is None else s for s in rings]
    profile = []
    for s in rings:
        h = crown * (1 - s * s)
        if groove and abs(s - groove) < 1e-6:
            h -= groove_depth
        if ridge and abs(s - 0.45) < 1e-6:
            h += ridge
        if s == 1.0:
            h -= chamfer
        profile.append(h)
    if poly is not None:
        outline = [(px * a, py * b) for px, py in poly_outline(poly, segs, corner)]
    else:
        ts = [2 * math.pi * k / segs for k in range(segs)]
        outline = [superellipse(t, a, b, n_exp, taper, skew) for t in ts]
    verts, faces, fm, fuv = [], [], [], []
    wear, cav, lx, ly = [], [], [], []
    sharp = []
    grid = []
    for ri, s in enumerate(rings):
        row = []
        pts = [(0.0, 0.0)] if s == 0 else [(ox * s, oy * s) for ox, oy in outline]
        for (x, y) in pts:
            p, _ = P(x, y, profile[ri])
            row.append(len(verts))
            verts.append(p)
            wear.append(1.0 if s >= ch_s - 1e-6 else (0.5 if groove and abs(s - groove) < 0.05 else 0.0))
            cav.append(1.0 if groove and abs(s - groove) < 1e-6 else 0.0)
            lx.append(x); ly.append(y)
        grid.append(row)

    S_uv = 2 * max(a, b) / 0.92  # metres per UV unit (isotropic)

    def uv_of(x, y, k=1.0):
        return (0.5 + x / S_uv * k, 0.5 + y / S_uv * k)

    def add_face(idx, mat, collapse=False):
        faces.append(idx)
        fm.append(mat)
        if collapse:  # back faces: their own small island (never overlapping the front in UV)
            fuv.append([(2.2 + 0.35 * uv_of(lx[i], ly[i])[0], 0.35 * uv_of(lx[i], ly[i])[1]) for i in idx])
        else:
            fuv.append([uv_of(lx[i], ly[i]) for i in idx])

    for k in range(segs):
        add_face([grid[0][0], grid[1][k], grid[1][(k + 1) % segs]], mat_top)
    for ri in range(1, len(rings) - 1):
        mat = mat_edge if rings[ri] >= ch_s - 1e-6 else mat_top
        for k in range(segs):
            k2 = (k + 1) % segs
            add_face([grid[ri][k], grid[ri + 1][k], grid[ri + 1][k2], grid[ri][k2]], mat)
    for k in range(segs):
        sharp.append((grid[-2][k], grid[-2][(k + 1) % segs]))
        sharp.append((grid[-1][k], grid[-1][(k + 1) % segs]))
    # Side wall and back.
    top_edge = grid[-1]
    bot = []
    inner = []
    for k, (ox, oy) in enumerate(outline):
        p, d = P(ox, oy, profile[-1] - thickness + chamfer * 0.5)
        bot.append(len(verts)); verts.append(p); wear.append(1.0); cav.append(0.0); lx.append(ox * 1.04); ly.append(oy * 1.04)
    for k, (ox, oy) in enumerate(outline):
        p, d = P(ox * 0.93, oy * 0.93, profile[-1] - thickness)
        inner.append(len(verts)); verts.append(p); wear.append(0.3); cav.append(0.6); lx.append(ox * 0.93); ly.append(oy * 0.93)
    pc, _ = P(0, 0, crown * 0.5 - thickness)
    cb = len(verts); verts.append(pc); wear.append(0.0); cav.append(0.6); lx.append(0); ly.append(0)
    arc = [0.0]
    for k in range(segs):
        arc.append(arc[-1] + np.linalg.norm(np.asarray(verts[top_edge[(k + 1) % segs]]) - np.asarray(verts[top_edge[k]])))
    wall_h = max(thickness, 0.003) / S_uv
    for k in range(segs):
        k2 = (k + 1) % segs
        faces.append([top_edge[k], bot[k], bot[k2], top_edge[k2]]); fm.append(mat_wall)
        chunk = k // 6  # break the wall into short strips (separate islands) so the atlas packs tightly
        base_u = arc[chunk * 6]
        u0_, u1_ = 3.0 + (arc[k] - base_u) / S_uv, 3.0 + (arc[k + 1] - base_u) / S_uv
        vo = 2.0 + chunk * 0.2
        fuv.append([(u0_, vo + wall_h), (u0_, vo), (u1_, vo), (u1_, vo + wall_h)])
        add_face([bot[k], inner[k], inner[k2], bot[k2]], mat_wall, True)
        add_face([inner[k], cb, inner[k2]], mat_wall, True)
        sharp.append((bot[k], bot[k2]))
    base = part.add(np.array(verts), faces, fm, fuv, {"wear": wear, "cavity": cav, "lx": lx, "ly": ly, "plate": [plate_id] * len(verts)}, sharp)
    # Bolts.
    for (bx, by) in bolts:
        p, d = P(bx * a, by * b, crown * (1 - (bx * bx + by * by) * 0.5))
        bolt(part, p, d, u, 0.0032, 0.0016, plate_id)
    if gasket:
        # Dark rubber gasket peeking out under the plate edge.
        gv, gf = [], []
        for k, (ox, oy) in enumerate(outline):
            p0, d = P(ox * 1.02, oy * 1.02, profile[-1] - thickness - 0.0015)
            p1, _ = P(ox * 0.9, oy * 0.9, profile[-1] - thickness - 0.004)
            gv += [p0, p1]
        for k in range(segs):
            k2 = (k + 1) % segs
            gf.append([k * 2, k * 2 + 1, k2 * 2 + 1, k2 * 2])
        part.add(np.array(gv), gf, gasket, None, {"plate": [plate_id] * len(gv)})
    return {"o": o, "u": u, "r": r, "c": c, "P": P, "a": a, "b": b}


def bolt(part, p, n, up, radius=0.003, height=0.0015, plate_id=0.0, sides=6, mat="Metal"):
    n = nrm(n)
    u = nrm(np.asarray(up) - n * (np.asarray(up) @ n))
    r = np.cross(u, n)
    verts, faces = [], []
    for k in range(sides):
        t = 2 * math.pi * k / sides
        d = r * math.cos(t) + u * math.sin(t)
        verts.append(p + d * radius - n * 0.0008)
        verts.append(p + d * radius + n * height)
    verts.append(p + n * (height + 0.0004))
    top = len(verts) - 1
    sharp = []
    for k in range(sides):
        k2 = (k + 1) % sides
        faces.append([k * 2, k2 * 2, k2 * 2 + 1, k * 2 + 1])
        faces.append([k * 2 + 1, k2 * 2 + 1, top])
        sharp.append((k * 2 + 1, k2 * 2 + 1))
    part.add(np.array(verts), faces, mat, None, {"plate": [plate_id] * len(verts), "wear": [1.0] * len(verts)}, sharp)


# ----------------------------------------------------------------------------- boxes, pouches, buckles


def frame_from(n, up):
    n = nrm(n)
    u = nrm(np.asarray(up, dtype=np.float64) - n * (np.asarray(up) @ n))
    r = np.cross(u, n)
    return r, u, n


def rbox(part, center, r, u, n, size, bevel=0.004, segments=2, mat="Armor", attrs=None, uv_scale=1.0):
    """Bevelled box in the frame (r, u, n); size = (w, h, d) full extents. Box UVs (projection per face)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=min(bevel, min(size) * 0.45), segments=segments, affect="EDGES", profile=0.5)
    M = np.stack([r, u, n], 1)
    verts = [np.asarray(center) + M @ np.array(v.co[:]) for v in bm.verts]
    faces, uvs = [], []
    loc = [np.array(v.co[:]) for v in bm.verts]
    for f in bm.faces:
        idx = [v.index for v in f.verts]
        fn = f.normal
        ax = max(range(3), key=lambda i: abs(fn[i]))
        uvs.append([((loc[i][1], loc[i][2]), (loc[i][0], loc[i][2]), (loc[i][0], loc[i][1]))[ax] for i in idx])
        faces.append(idx)
    bm.free()
    uvs = [[(x * uv_scale, y * uv_scale) for x, y in f] for f in uvs]
    part.add(np.array(verts), faces, mat, uvs, attrs)


def pouch(ctx, part, p, n, up, w, h, d, mat="Garment_Top", flap_mat=None, snap=True, tilt=0.0, plate_id=0.0):
    """Fabric utility pouch: padded body, overlapping flap with a lip, snap button."""
    r, u, nn = frame_from(n, up)
    if tilt:
        rot = Matrix.Rotation(tilt, 3, Vector(nn))
        r = np.array(rot @ Vector(r)); u = np.array(rot @ Vector(u))
    c = np.asarray(p) + nn * (d * 0.5 + 0.002)
    rbox(part, c, r, u, nn, (w, h, d), bevel=min(0.008, d * 0.35), segments=2, mat=mat, attrs={"pouch": 1.0, "plate": plate_id})
    fl = flap_mat or mat
    fc = c + u * (h * 0.32) + nn * (d * 0.5 + 0.0025)
    rbox(part, fc, r, u, nn, (w * 1.04, h * 0.42, 0.006), bevel=0.0025, segments=1, mat=fl, attrs={"pouch": 2.0, "plate": plate_id})
    # flap front lip
    rbox(part, fc - u * (h * 0.2) + nn * 0.003, r, u, nn, (w * 1.02, 0.012, 0.005), bevel=0.0018, segments=1, mat=fl, attrs={"pouch": 2.0, "plate": plate_id})
    if snap:
        bolt(part, fc - u * (h * 0.14) + nn * 0.0035, nn, u, 0.0055, 0.0025, plate_id, sides=10)
    return c


def buckle(part, p, t, n, width, mat="Metal"):
    """Rectangular buckle frame around a strap at p; t = strap direction, n = surface normal."""
    t = nrm(t); n = nrm(n)
    s = np.cross(n, t)
    W = width + 0.008
    L = 0.022
    th = 0.0035
    for (cx, cy, sx, sy) in ((0, L / 2 - 0.0025, W, 0.005), (0, -L / 2 + 0.0025, W, 0.005), (W / 2 - 0.0025, 0, 0.005, L), (-W / 2 + 0.0025, 0, 0.005, L)):
        rbox(part, p + s * cx + t * cy + n * 0.004, s, t, n, (sx, sy, th), bevel=0.0012, segments=1, mat=mat, attrs={"wear": 1.0})
    # center bar
    rbox(part, p + n * 0.0055, s, t, n, (W, 0.004, 0.003), bevel=0.001, segments=1, mat=mat, attrs={"wear": 1.0})


# ----------------------------------------------------------------------------- paths on the surface


def catmull(points, n):
    P = [np.asarray(p, dtype=np.float64) for p in points]
    if len(P) < 2:
        return P
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    seg = len(P) - 3
    out = []
    for i in range(n):
        x = i / (n - 1) * seg
        k = min(int(x), seg - 1)
        t = x - k
        p0, p1, p2, p3 = P[k], P[k + 1], P[k + 2], P[k + 3]
        t2, t3 = t * t, t * t * t
        out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    return out


def surface_path(ctx, waypoints, n=24, push=0.0, tree=None, smooth=2, spline=True):
    """Resample waypoints, snap each sample to the nearest outer surface point; returns (points, normals)."""
    tree = tree or ctx.outer_tree()
    pts = catmull(waypoints, n) if spline else [np.asarray(waypoints[0]) + (np.asarray(waypoints[-1]) - np.asarray(waypoints[0])) * i / (n - 1) for i in range(n)]
    P, N = [], []
    for p in pts:
        hit, nn, _, _ = tree.find_nearest(Vector(p), 0.5)
        if hit is None:
            P.append(np.asarray(p)); N.append(np.array((0, 0, 1.0)))
        else:
            P.append(np.array(hit)); N.append(np.array(nn))
    P, N = np.array(P), np.array(N)
    for _ in range(smooth):
        P[1:-1] = P[1:-1] * 0.5 + (P[:-2] + P[2:]) * 0.25
        N[1:-1] = N[1:-1] * 0.5 + (N[:-2] + N[2:]) * 0.25
    N = N / np.linalg.norm(N, axis=1, keepdims=True)
    # Re-snap after smoothing so the path never sinks.
    for i, p in enumerate(P):
        hit, nn, _, _ = tree.find_nearest(Vector(p), 0.5)
        if hit is not None:
            gap = (Vector(p) - hit).dot(Vector(nn))
            if gap < 0:
                P[i] = np.array(hit)
    return P + N * push, N


def tangents(P):
    T = np.zeros_like(P)
    T[1:-1] = P[2:] - P[:-2]
    T[0] = P[1] - P[0]
    T[-1] = P[-1] - P[-2]
    return T / np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)


def strap(part, P, N, width, thick, mat="Belt", attrs=None, caps=True, uv_v=(0.0, 1.0)):
    """Webbing strap with rectangular cross-section along a surface path."""
    T = tangents(P)
    S = np.cross(N, T)
    S /= np.maximum(np.linalg.norm(S, axis=1, keepdims=True), 1e-12)
    verts = []
    L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    for p, s, n in zip(P, S, N):
        verts += [p - s * width / 2, p + s * width / 2, p + s * width / 2 + n * thick, p - s * width / 2 + n * thick]
    faces, uvs, sharp = [], [], []
    m = len(P)
    for i in range(m - 1):
        a, b = i * 4, (i + 1) * 4
        u0, u1 = L[i], L[i + 1]
        # top, two sides, bottom
        faces.append([a + 3, a + 2, b + 2, b + 3]); uvs.append([(u0, 0), (u0, 1), (u1, 1), (u1, 0)])
        faces.append([a + 2, a + 1, b + 1, b + 2]); uvs.append([(u0, 1), (u0, 1.08), (u1, 1.08), (u1, 1)])
        faces.append([a + 0, a + 3, b + 3, b + 0]); uvs.append([(u0, -0.08), (u0, 0), (u1, 0), (u1, -0.08)])
        faces.append([a + 1, a + 0, b + 0, b + 1]); uvs.append([(u0, 1.08), (u0, -0.08), (u1, -0.08), (u1, 1.08)])
    for k in (0, 1, 2, 3):  # the four long edges are hard
        for i in range(m - 1):
            sharp.append((i * 4 + k, (i + 1) * 4 + k))
    if caps:
        faces.append([0, 1, 2, 3]); uvs.append([(0, 0), (0, 1), (0.01, 1), (0.01, 0)])
        e = (m - 1) * 4
        faces.append([e + 3, e + 2, e + 1, e + 0]); uvs.append([(L[-1], 0), (L[-1], 1), (L[-1] + 0.01, 1), (L[-1] + 0.01, 0)])
    # strap UVs in metres along u, 0..1 across v scaled to a 0.04 m tile
    uvs = [[(x * 4.0, uv_v[0] + (uv_v[1] - uv_v[0]) * y) for x, y in f] for f in uvs]
    part.add(np.array(verts), faces, mat, uvs, attrs, sharp)
    return P, T, S, N


def tube(part, P, radius, sides=8, mat="Glow", attrs=None, caps=False, N=None):
    P = np.asarray(P)
    T = tangents(P)
    ref = N if N is not None else np.tile(np.array([0, 0, 1.0]), (len(P), 1))
    verts, faces, uvs = [], [], []
    L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    rad = np.broadcast_to(np.asarray(radius, dtype=np.float64), (len(P),))
    for i, (p, t) in enumerate(zip(P, T)):
        s = np.cross(t, ref[i])
        if np.linalg.norm(s) < 1e-6:
            s = np.cross(t, (1, 0, 0))
        s = nrm(s)
        u2 = np.cross(s, t)
        for k in range(sides):
            a = 2 * math.pi * k / sides
            verts.append(p + (s * math.cos(a) + u2 * math.sin(a)) * rad[i])
    for i in range(len(P) - 1):
        for k in range(sides):
            a, b = i * sides + k, i * sides + (k + 1) % sides
            faces.append([a, b, b + sides, a + sides])
            uvs.append([(L[i] * 4, k / sides), (L[i] * 4, (k + 1) / sides), (L[i + 1] * 4, (k + 1) / sides), (L[i + 1] * 4, k / sides)])
    if caps:
        for i, sgn in ((0, -1), (len(P) - 1, 1)):
            c = len(verts); verts.append(P[i] + T[i] * sgn * rad[i] * 0.3)
            for k in range(sides):
                a, b = i * sides + k, i * sides + (k + 1) % sides
                faces.append([a, b, c] if sgn > 0 else [b, a, c]); uvs.append([(0, 0), (0, 0.1), (0.05, 0.05)])
    part.add(np.array(verts), faces, mat, uvs, attrs)


def light_strip(part, P, N, width=0.003, height=0.0012, mat="Glow", attrs=None):
    """Raised emissive light pipe (trapezoid section) along a surface path."""
    T = tangents(P)
    S = np.cross(N, T)
    S /= np.maximum(np.linalg.norm(S, axis=1, keepdims=True), 1e-12)
    verts = []
    for p, s, n in zip(P, S, N):
        verts += [p - s * width * 0.75 - n * 0.0008, p - s * width * 0.4 + n * height, p + s * width * 0.4 + n * height, p + s * width * 0.75 - n * 0.0008]
    faces, uvs = [], []
    L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    for i in range(len(P) - 1):
        a, b = i * 4, (i + 1) * 4
        for k in range(3):
            faces.append([a + k, b + k, b + k + 1, a + k + 1])
            uvs.append([(L[i] * 4, k / 3), (L[i + 1] * 4, k / 3), (L[i + 1] * 4, (k + 1) / 3), (L[i] * 4, (k + 1) / 3)])
    part.add(np.array(verts), faces, mat, uvs, attrs)


def ring_band(ctx, part, centers, dirs_fn, heights, push, n=32, mat="Belt", tree=None, close=True, thick=0.004, attrs=None, uv_scale=4.0):
    """Band around the body (belt, collar): for each of the given heights, ray-cast a ring; rows connected."""
    rows = []
    for (c, push_k) in zip(centers, push):
        row = []
        for k in range(n):
            phi = 2 * math.pi * k / n
            d = dirs_fn(phi)
            hit, nn = ctx.cast(np.asarray(c) + d * 0.6, -d, 0.7, tree)
            if hit is None:
                hit, nn = np.asarray(c) + d * 0.1, d
            row.append(hit + nn * push_k)
        rows.append(row)
    verts, faces, uvs = [], [], []
    for row in rows:
        verts += row
    for ri in range(len(rows) - 1):
        for k in range(n if close else n - 1):
            k2 = (k + 1) % n
            a, b = ri * n + k, ri * n + k2
            faces.append([a, b, b + n, a + n])
            uvs.append([(k / n * uv_scale, ri), ((k + 1) / n * uv_scale, ri), ((k + 1) / n * uv_scale, ri + 1), (k / n * uv_scale, ri + 1)])
    part.add(np.array(verts), faces, mat, uvs, attrs)
    return rows


def join(objs, name):
    objs = [o for o in objs if o is not None]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = name
    o.data.name = name
    o.select_set(False)
    return o


def strip_occluded(obj, occluders, dist=0.06, erode=1):
    """Delete faces of obj that are fully covered by `occluders` (rays from the face centre and corners along the
    normal hit an occluder within `dist`); keeps `erode` rings of faces next to visible ones."""
    from mathutils.bvhtree import BVHTree
    verts, polys = [], []
    for o in occluders:
        off = len(verts)
        verts += [v.co.copy() for v in o.data.vertices]
        polys += [[off + i for i in p.vertices] for p in o.data.polygons]
    tree = BVHTree.FromPolygons(verts, polys)
    me = obj.data
    me.update()
    vhit = np.zeros(len(me.vertices), bool)
    for v in me.vertices:
        h = tree.ray_cast(v.co + v.normal * 0.001, v.normal, dist)[0]
        vhit[v.index] = h is not None
    hidden = np.zeros(len(me.polygons), bool)
    for p in me.polygons:
        if all(vhit[i] for i in p.vertices):
            hidden[p.index] = tree.ray_cast(p.center + p.normal * 0.001, p.normal, dist)[0] is not None
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    for _ in range(erode):
        keep = ~hidden
        grow = hidden.copy()
        for f in bm.faces:
            if hidden[f.index] and any(keep[g.index] for e in f.edges for g in e.link_faces):
                grow[f.index] = False
        hidden = grow
    kill = [f for f in bm.faces if hidden[f.index]]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    me.update()
    return int(len(kill))
