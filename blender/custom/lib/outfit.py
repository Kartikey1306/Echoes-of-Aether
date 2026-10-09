# SNAPSHOT of blender/scripts/outfit.py taken 2026-10-04 for the customisation pipeline (blender/custom). Do not edit; re-copy if needed.
"""Procedural sci-fi outfits built on the character's body surface.

Every garment is a pure function of the body's vertex positions, so it is rebuilt for each blendshape
(customisation morphs and expressions) and gets matching shape keys. Shells (suit, pants, boots, gloves)
share topology with the body region they cover; hard-surface parts (armour plates, belt, collar,
conduits, devices) are skinned rigidly to one bone and follow morphs through a surface binding.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from meshutil import SurfaceBinding, add_shape_key

# ----------------------------------------------------------------------------- body analysis


class BodyData:
    def __init__(self, body, rig):
        self.body, self.rig = body, rig
        me = body.data
        self.faces = [list(p.vertices) for p in me.polygons]
        self.nv = len(me.vertices)
        self.basis = np.array([v.co[:] for v in me.vertices], dtype=np.float64)
        self.shapes = {}
        if me.shape_keys:
            for k in me.shape_keys.key_blocks[1:]:
                a = np.empty(self.nv * 3, dtype=np.float32)
                k.data.foreach_get("co", a)
                self.shapes[k.name] = a.reshape(-1, 3).astype(np.float64)
        # Loop UVs per face.
        uv = me.uv_layers.active.data if me.uv_layers.active else None
        self.face_uv = [[tuple(uv[li].uv) for li in p.loop_indices] if uv else [(0, 0)] * len(p.vertices) for p in me.polygons]
        # Bone weights.
        self.groups = {g.index: g.name for g in body.vertex_groups}
        self.w = {}
        for v in me.vertices:
            for g in v.groups:
                n = self.groups[g.group]
                if n.startswith("mixamorig:") and g.weight > 1e-4:
                    self.w.setdefault(n, np.zeros(self.nv))[v.index] = g.weight
        self.bones = {b.name: (rig.matrix_world @ b.head_local, rig.matrix_world @ b.tail_local) for b in rig.data.bones}
        self.fidx = np.array([f[:4] + [f[0]] * (4 - len(f)) for f in self.faces])

    def wsum(self, names):
        out = np.zeros(self.nv)
        for n in names:
            for k, v in self.w.items():
                if k == n or (n.endswith("*") and k.startswith(n[:-1])):
                    out += v
        return out

    def head(self, bone):
        return np.array(self.bones["mixamorig:" + bone][0])

    def tail(self, bone):
        return np.array(self.bones["mixamorig:" + bone][1])

    def normals(self, co):
        f = self.fidx
        a, b, c, d = co[f[:, 0]], co[f[:, 1]], co[f[:, 2]], co[f[:, 3]]
        fn = np.cross(c - a, d - b)  # quad diagonal cross (works for tris with d==a)
        vn = np.zeros_like(co)
        for i in range(4):
            np.add.at(vn, f[:, i], fn)
        l = np.linalg.norm(vn, axis=1, keepdims=True)
        return vn / np.maximum(l, 1e-12)

    def shape_list(self):
        """[(name or None for basis, coords)]"""
        return [(None, self.basis)] + [(n, c) for n, c in self.shapes.items()]


def copy_weights(dst, src_body, vmap):
    """vmap: list of body vertex index per dst vertex."""
    me = src_body.data
    names = {g.index: g.name for g in src_body.vertex_groups}
    groups = {}
    for di, bi in enumerate(vmap):
        for g in me.vertices[bi].groups:
            n = names[g.group]
            if not n.startswith("mixamorig:") or g.weight < 1e-4:
                continue
            vg = groups.get(n) or dst.vertex_groups.get(n) or dst.vertex_groups.new(name=n)
            groups[n] = vg
            vg.add([di], g.weight, "REPLACE")


def rigid_weights(dst, bone):
    vg = dst.vertex_groups.new(name="mixamorig:" + bone)
    vg.add(list(range(len(dst.data.vertices))), 1.0, "REPLACE")


def finish(obj, rig, materials):
    for m in materials:
        obj.data.materials.append(m)
    obj.parent = rig
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    for p in obj.data.polygons:
        p.use_smooth = True
    bpy.context.scene.collection.objects.link(obj) if obj.name not in bpy.context.scene.collection.objects else None


# ----------------------------------------------------------------------------- shells


class Shell:
    """A garment covering a subset of body faces, offset outward with thickness lips at its openings."""

    def __init__(self, B, face_ids, offset_fn, smooth=4, lip=True, name="shell"):
        self.B, self.name = B, name
        self.face_ids = list(face_ids)
        used = sorted({v for fi in self.face_ids for v in B.faces[fi]})
        self.vmap = used
        self.inv = {v: i for i, v in enumerate(used)}
        self.faces = [[self.inv[v] for v in B.faces[fi]] for fi in self.face_ids]
        self.uvs = [B.face_uv[fi] for fi in self.face_ids]
        # Boundary edges (used by one face) in face winding order.
        ec = {}
        for f in self.faces:
            for i in range(len(f)):
                a, b = f[i], f[(i + 1) % len(f)]
                ec.setdefault((min(a, b), max(a, b)), []).append((a, b))
        self.boundary = [v[0] for v in ec.values() if len(v) == 1]
        bset = sorted({x for e in self.boundary for x in e})
        self.bverts = bset
        self.bidx = {v: i for i, v in enumerate(bset)}
        n = len(used)
        self.is_b = np.zeros(n, bool)
        self.is_b[bset] = True
        nb = [set() for _ in range(n)]
        for f in self.faces:
            for i in range(len(f)):
                a, b = f[i], f[(i + 1) % len(f)]
                nb[a].add(b); nb[b].add(a)
        self.nbr = [list(s) for s in nb]
        self.offset_fn = offset_fn
        self.smooth = smooth
        self.lip = lip and len(self.boundary) > 0

    def positions(self, body_co):
        B = self.B
        vn = B.normals(body_co)[self.vmap]
        co = body_co[self.vmap].copy()
        off = self.offset_fn(body_co[self.vmap], vn, self.vmap)
        out = co + vn * off[:, None]
        # Laplacian smoothing removes anatomical detail so the cloth reads as fabric (openings stay put).
        for _ in range(self.smooth):
            avg = np.array([out[nb].mean(axis=0) if nb else out[i] for i, nb in enumerate(self.nbr)])
            out = np.where(self.is_b[:, None], out, out * 0.45 + avg * 0.55)
        # Re-project so smoothing never sinks the cloth into the body.
        d = ((out - co) * vn).sum(axis=1)
        low = d < off * 0.8
        out[low] += vn[low] * (off[low] * 0.8 - d[low])[:, None]
        if self.lip:
            inner = co[self.bverts] + vn[self.bverts] * (-0.002)
            out = np.vstack([out, inner])
        return out

    def build(self, rig, mat_of_face, materials):
        co = self.positions(self.B.basis)
        me = bpy.data.meshes.new(self.name)
        faces = [list(f) for f in self.faces]
        nmain = len(self.vmap)
        lip_faces = []
        if self.lip:
            for a, b in self.boundary:
                ia, ib = nmain + self.bidx[a], nmain + self.bidx[b]
                lip_faces.append([b, a, ia, ib])
        me.from_pydata([tuple(v) for v in co], [], faces + lip_faces)
        me.update()
        uvl = me.uv_layers.new(name="UVMap")
        li = 0
        for pi, p in enumerate(me.polygons):
            for k, l in enumerate(p.loop_indices):
                uvl.data[l].uv = self.uvs[pi][k] if pi < len(faces) else (0.0, 0.0)
        mats = [m.name for m in materials]
        for pi, p in enumerate(me.polygons):
            if pi < len(faces):
                fc = co[faces[pi]].mean(axis=0)
                p.material_index = mats.index(mat_of_face(fc, self.face_ids[pi]))
            else:
                p.material_index = mats.index(mat_of_face(None, None))
        obj = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(obj)
        vmap = list(self.vmap) + [self.vmap[v] for v in self.bverts] if self.lip else list(self.vmap)
        copy_weights(obj, self.B.body, vmap)
        finish(obj, rig, materials)
        for name, sco in self.B.shapes.items():
            add_shape_key(obj, name, self.positions(sco))
        return obj


# ----------------------------------------------------------------------------- hard surface


def solid_from_patch(points, normals, faces, thickness):
    """Close a surface patch into a solid plate: outer + inner + rim."""
    n = len(points)
    outer = points
    inner = points - normals * thickness
    verts = np.vstack([outer, inner])
    fs = [list(f) for f in faces] + [[v + n for v in reversed(f)] for f in faces]
    ec = {}
    for f in faces:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            ec.setdefault((min(a, b), max(a, b)), []).append((a, b))
    for e in ec.values():
        if len(e) == 1:
            a, b = e[0]
            fs.append([b, a, a + n, b + n])
    return verts, fs


class Plate:
    """Armour plate cut from a body region, puffed out, smoothed into a hard shell and given thickness."""

    def __init__(self, B, vmask, offset=0.022, thickness=0.006, smooth=10, name="plate"):
        self.B, self.name = B, name
        fm = [i for i, f in enumerate(B.faces) if all(vmask[v] for v in f)]
        self.shell = Shell(B, fm, lambda co, n, ids: np.full(len(ids), offset), smooth=smooth, lip=False, name=name)
        self.thickness = thickness

    def positions(self, body_co):
        out = self.shell.positions(body_co)
        sh = self.shell
        # Patch normals from the smoothed surface.
        vn = np.zeros_like(out)
        for f in sh.faces:
            a, b, c = out[f[0]], out[f[1]], out[f[2]]
            n = np.cross(b - a, c - a)
            for v in f:
                vn[v] += n
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        v, _ = solid_from_patch(out, vn, sh.faces, self.thickness)
        return v

    def build(self, rig, bone, material, bevel=True):
        sh = self.shell
        co = self.positions(self.B.basis)
        _, fs = solid_from_patch(co[:len(sh.vmap)], np.zeros((len(sh.vmap), 3)), sh.faces, self.thickness)
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([tuple(v) for v in co], [], fs)
        me.update()
        obj = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(obj)
        rigid_weights(obj, bone)
        finish(obj, rig, [material])
        # Smart-UV for tiling panel textures.
        uv_project(obj)
        for name, sco in self.B.shapes.items():
            add_shape_key(obj, name, self.positions(sco))
        return obj


def uv_project(obj):
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers.active.data
    # Box projection in metres (tileable materials use world-scale UVs).
    for p in me.polygons:
        n = p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for l in p.loop_indices:
            co = me.vertices[me.loops[l].vertex_index].co
            u, v = [(co.y, co.z), (co.x, co.z), (co.x, co.y)][ax]
            uvl[l].uv = (u * 4, v * 4)


def tube(points, radius, sides=6):
    """Tube mesh along a polyline (closed caps omitted). Returns verts, faces."""
    pts = [Vector(p) for p in points]
    verts, faces = [], []
    up = Vector((0, 0, 1))
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        side = t.cross(up)
        if side.length < 1e-4:
            side = t.cross(Vector((1, 0, 0)))
        side.normalize()
        up2 = side.cross(t).normalized()
        for s in range(sides):
            a = 2 * math.pi * s / sides
            verts.append(p + (side * math.cos(a) + up2 * math.sin(a)) * radius)
    for i in range(len(pts) - 1):
        for s in range(sides):
            a, b = i * sides + s, i * sides + (s + 1) % sides
            faces.append([a, b, b + sides, a + sides])
    return [tuple(v) for v in verts], faces


def rounded_box(center, size, rot=None, bevel=0.25):
    """Rounded box via a cube with beveled corners (bmesh). Returns verts, faces."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel * 0.5, segments=2, affect="EDGES", profile=0.6)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
        if rot is not None:
            v.co = rot @ v.co
        v.co += Vector(center)
    verts = [tuple(v.co) for v in bm.verts]
    faces = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    return verts, faces


class Attached:
    """Rigid hard-surface part following the body via a surface binding (for morphs)."""

    def __init__(self, B, verts, faces, name):
        self.B, self.name = B, name
        self.verts = np.array(verts, dtype=np.float64)
        self.faces = faces
        self.bind = SurfaceBinding(B.body, B.basis, self.verts, max_dist=0.5)

    def build(self, rig, bone, materials, mat_index=None, weights_from_body=False):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([tuple(v) for v in self.verts], [], self.faces)
        me.update()
        obj = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(obj)
        if weights_from_body:
            nearest = [int(self.bind.I[i, np.argmax(self.bind.W[i])]) for i in range(len(self.verts))]
            copy_weights(obj, self.B.body, nearest)
        else:
            rigid_weights(obj, bone)
        finish(obj, rig, materials)
        if mat_index is not None:
            for p in obj.data.polygons:
                p.material_index = mat_index(p)
        uv_project(obj)
        for name, sco in self.B.shapes.items():
            d = self.bind.transfer(sco - self.B.basis)
            if np.abs(d).max() > 1e-5:
                add_shape_key(obj, name, self.verts + d)
        return obj


def ray_ring(tree, center, height_axis, radius_guess, n, start_angle=0.0, end_angle=2 * math.pi, push=0.0):
    """Cast rays outward from an axis point to the surface; returns surface points (+push along normal)."""
    pts, nrms = [], []
    c = Vector(center)
    for i in range(n):
        a = start_angle + (end_angle - start_angle) * i / (n if end_angle - start_angle >= 2 * math.pi - 1e-6 else n - 1)
        d = Vector((math.sin(a), -math.cos(a), 0))  # 0 = front (-Y in Blender)
        origin = c + d * (radius_guess * 2.5)
        hit, nrm, _, _ = tree.ray_cast(origin, -d, radius_guess * 3)
        if hit is None:
            hit, nrm = c + d * radius_guess, d
        pts.append(hit + nrm * push)
        nrms.append(nrm)
    return pts, nrms


def surface_patch(tree, center, out_dir, up_dir, half_w, half_h, n_exp=2.6, rings=7, sides=28,
                  offset=0.02, thickness=0.006, crown=0.004, bevel=0.0025, skew=0.0):
    """Hard-surface plate: a superellipse outline laid on the body by ray casts, domed and given a bevelled
    rim and thickness. Returns (verts, faces)."""
    out = Vector(out_dir).normalized()
    up = Vector(up_dir)
    up = (up - out * up.dot(out)).normalized()
    right = up.cross(out).normalized()
    c = Vector(center)

    def surf(x, y):
        o = c + right * x + up * (y + skew * x) + out * 0.35
        hit, nrm, _, _ = tree.ray_cast(o, -out, 0.8)
        if hit is None:
            return c + right * x + up * y, out
        return hit, nrm

    ring_pts = []  # outer surface rings (ring 0 = centre)
    for k in range(rings + 1):
        r = k / rings
        row = []
        for s in range(sides if k > 0 else 1):
            a = 2 * math.pi * s / sides
            ca, sa = math.cos(a), math.sin(a)
            x = math.copysign(abs(ca) ** (2 / n_exp), ca) * half_w * r
            y = math.copysign(abs(sa) ** (2 / n_exp), sa) * half_h * r
            hit, nrm = surf(x, y)
            dome = crown * (1 - r * r)
            # Bevel: the last ring drops towards the surface.
            edge = -bevel if k == rings else 0.0
            row.append(hit + out * (offset + dome + edge) * 0.6 + nrm * (offset + dome + edge) * 0.4)
        ring_pts.append(row)
    # Smooth the rings a little to hide body detail under the plate.
    for _ in range(3):
        for k in range(1, rings):
            row = ring_pts[k]
            ring_pts[k] = [(row[i - 1] + row[i] * 2 + row[(i + 1) % len(row)]) / 4 for i in range(len(row))]
    verts, faces = [], []
    def add(v):
        verts.append(tuple(v)); return len(verts) - 1
    idx = [[add(ring_pts[0][0])]] + [[add(p) for p in ring_pts[k]] for k in range(1, rings + 1)]
    for s in range(sides):
        faces.append([idx[0][0], idx[1][s], idx[1][(s + 1) % sides]])
    for k in range(1, rings):
        for s in range(sides):
            a, b = idx[k][s], idx[k][(s + 1) % sides]
            cc, d = idx[k + 1][(s + 1) % sides], idx[k + 1][s]
            faces.append([a, d, cc, b])
    # Underside (flat-ish back) and rim give the plate its thickness.
    back = [add(Vector(verts[i]) - out * thickness) for i in idx[rings]]
    cb = add(Vector(verts[idx[0][0]]) - out * (thickness + offset * 0.5))
    for s in range(sides):
        a, b = idx[rings][s], idx[rings][(s + 1) % sides]
        faces.append([a, back[s], back[(s + 1) % sides], b])
        faces.append([cb, back[(s + 1) % sides], back[s]])
    return verts, faces
