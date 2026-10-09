"""Mesh helpers shared by the character pipeline (numpy based)."""
import bpy, bmesh
import numpy as np
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc
from mathutils import Vector


def get_co(obj):
    a = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
    obj.data.vertices.foreach_get("co", a)
    return a.reshape(-1, 3)


def set_co(obj, co):
    obj.data.vertices.foreach_set("co", np.asarray(co, dtype=np.float32).ravel())
    obj.data.update()


def mix_co(obj):
    """Object-space coordinates of the current shape-key mix (no modifiers)."""
    if not obj.data.shape_keys:
        return get_co(obj)
    k = obj.shape_key_add(name="__mix_tmp", from_mix=True)
    a = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
    k.data.foreach_get("co", a)
    obj.shape_key_remove(k)
    return a.reshape(-1, 3)


def bake_shape_keys(obj):
    """Apply the current shape-key mix to the mesh and drop all keys."""
    if not obj.data.shape_keys:
        return
    co = mix_co(obj)
    obj.shape_key_clear()
    set_co(obj, co)


def add_shape_key(obj, name, co):
    if not obj.data.shape_keys:
        obj.shape_key_add(name="Basis", from_mix=False)
    k = obj.shape_key_add(name=name, from_mix=False)
    k.data.foreach_set("co", np.asarray(co, dtype=np.float32).ravel())
    k.value = 0.0
    return k


class SurfaceBinding:
    """Binds points to the nearest surface of a source mesh (barycentric on the nearest polygon), so
    deltas of the source vertices can be transferred to the points."""

    def __init__(self, src_obj, src_co, points, max_dist=1.0):
        mesh = src_obj.data
        polys = [list(p.vertices) for p in mesh.polygons]
        self.tree = BVHTree.FromPolygons([Vector(c) for c in src_co], polys, all_triangles=False)
        self.idx = []
        self.w = []
        self.dist = np.zeros(len(points), dtype=np.float32)
        for i, p in enumerate(points):
            loc, nrm, fi, d = self.tree.find_nearest(Vector(p), max_dist)
            if fi is None:
                self.idx.append([0]); self.w.append([0.0]); self.dist[i] = 1e9
                continue
            vids = polys[fi]
            w = poly_3d_calc([Vector(src_co[v]) for v in vids], loc)
            self.idx.append(vids); self.w.append(list(w)); self.dist[i] = d
        n = max(len(x) for x in self.idx)
        self.I = np.zeros((len(points), n), dtype=np.int64)
        self.W = np.zeros((len(points), n), dtype=np.float32)
        for i, (ii, ww) in enumerate(zip(self.idx, self.w)):
            self.I[i, :len(ii)] = ii
            self.W[i, :len(ww)] = ww

    def transfer(self, delta):
        """delta: (Nsrc,3) per-source-vertex offsets -> (Npoints,3)."""
        return (delta[self.I] * self.W[..., None]).sum(axis=1)


def delete_verts_not_in_group(obj, group):
    gi = obj.vertex_groups[group].index
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    deform = bm.verts.layers.deform.active
    kill = [v for v in bm.verts if gi not in v[deform] or v[deform][gi] < 0.5]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def remove_groups(obj, pred):
    for g in list(obj.vertex_groups):
        if pred(g.name):
            obj.vertex_groups.remove(g)


def delete_verts_in_groups(obj, groups):
    idx = [obj.vertex_groups[g].index for g in groups if g in obj.vertex_groups]
    if not idx:
        return
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    deform = bm.verts.layers.deform.active
    kill = [v for v in bm.verts if any(i in v[deform] and v[deform][i] > 0.5 for i in idx)]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
