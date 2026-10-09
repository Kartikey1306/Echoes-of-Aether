"""wkit -- hard-surface weapon modelling, high->low baking and PBR texture composition (Blender 5.2, headless).

Authoring space
---------------
Geometry is written in *Unity local space* of each weapon: x = right, y = up, z = forward (barrel / blade direction).
`finish()` maps it to Blender (bx, by, bz) = (-x, -z, y) so the FBX exporter (forward -Z, up Y) hands Unity exactly
the authored coordinates with identity node rotations (same convention as blender/robots).

Parts
-----
A `Part` collects polygons with a material slot name. Each primitive is added with a `lod` flag:
  "both" (default) -> low and high poly, "hi" -> high-poly only detail (floaters, ridges: they bake into the normal map),
  "lo" -> game mesh only.
The high poly is the same base geometry + a Bevel modifier (rounded hard-surface edges) + the hi-only detail; the low
poly keeps hard edges split at 40 deg. Normal, AO and material-ID maps are baked high -> low into a shared atlas, then
`compose()` builds BaseColor / MetallicSmoothness / Occlusion maps from the ID map, AO and a curvature map derived
from the baked normals (edge wear, cavity grime) plus value noise.
"""
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

TAU = math.tau


# ============================================================================ 2D helpers
def chamfer_rect(hw, yb, yt, cb=0.0, ct=0.0, x0=0.0):
    """Closed CCW ring (x, y): rectangle [-hw, hw] x [yb, yt] with chamfered bottom (cb) and top (ct) corners."""
    pts = []
    if cb > 0:
        pts += [(x0 - hw + cb, yb), (x0 + hw - cb, yb), (x0 + hw, yb + cb)]
    else:
        pts += [(x0 - hw, yb), (x0 + hw, yb)]
    if ct > 0:
        pts += [(x0 + hw, yt - ct), (x0 + hw - ct, yt), (x0 - hw + ct, yt), (x0 - hw, yt - ct)]
    else:
        pts += [(x0 + hw, yt), (x0 - hw, yt)]
    if cb > 0:
        pts += [(x0 - hw, yb + cb)]
    return pts


def resample(pts, n):
    """Resample a closed polygon to n points evenly spaced along its perimeter (keeps loft rings compatible)."""
    p = np.array(pts + [pts[0]], dtype=float)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    L = cum[-1]
    out = []
    for k in range(n):
        s = L * k / n
        i = min(np.searchsorted(cum, s, side="right") - 1, len(seg) - 1)
        u = (s - cum[i]) / max(seg[i], 1e-12)
        out.append(tuple(p[i] + (p[i + 1] - p[i]) * u))
    return out


def corner_pts(pts):
    """Indices of polygon corners (direction change > 20 deg)."""
    out = []
    n = len(pts)
    for i in range(n):
        a, b, c = np.array(pts[i - 1]), np.array(pts[i]), np.array(pts[(i + 1) % n])
        d1, d2 = b - a, c - b
        if np.linalg.norm(d1) < 1e-9 or np.linalg.norm(d2) < 1e-9:
            continue
        cs = np.dot(d1, d2) / np.linalg.norm(d1) / np.linalg.norm(d2)
        if cs < math.cos(math.radians(20)):
            out.append(i)
    return out


def resample_corners(pts, n):
    """Resample keeping every corner: distribute n points over the edges between corners by length."""
    cs = corner_pts(pts)
    if not cs:
        return resample(pts, n)
    m = len(pts)
    edges = []
    for k in range(len(cs)):
        i0, i1 = cs[k], cs[(k + 1) % len(cs)]
        chain = [pts[i0]]
        j = i0
        while True:
            j = (j + 1) % m
            chain.append(pts[j])
            if j == i1:
                break
        L = sum(np.linalg.norm(np.array(chain[q + 1]) - np.array(chain[q])) for q in range(len(chain) - 1))
        edges.append((chain, L))
    total = sum(L for _, L in edges)
    counts = [max(1, int(round(n * L / total))) for _, L in edges]
    while sum(counts) > n:
        counts[int(np.argmax(counts))] -= 1
    while sum(counts) < n:
        counts[int(np.argmax([L / c for (_, L), c in zip(edges, counts)]))] += 1
    out = []
    for (chain, L), c in zip(edges, counts):
        p = np.array(chain, dtype=float)
        seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
        cum = np.concatenate([[0], np.cumsum(seg)])
        for k in range(c):
            s = L * k / c
            i = min(np.searchsorted(cum, s, side="right") - 1, len(seg) - 1)
            u = (s - cum[i]) / max(seg[i], 1e-12)
            out.append(tuple(p[i] + (p[i + 1] - p[i]) * u))
    return out


def rounded_rect(hw, hh, r, seg=3, cx=0.0, cy=0.0):
    pts = []
    r = min(r, hw * 0.999, hh * 0.999)
    for cxs, cys, a0 in ((hw - r, -hh + r, -90), (hw - r, hh - r, 0), (-hw + r, hh - r, 90), (-hw + r, -hh + r, 180)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append((cx + cxs + r * math.cos(a), cy + cys + r * math.sin(a)))
    return pts


def circle(r, n, cx=0.0, cy=0.0, a0=0.0, ry=None):
    ry = r if ry is None else ry
    return [(cx + r * math.cos(a0 + TAU * k / n), cy + ry * math.sin(a0 + TAU * k / n)) for k in range(n)]


def offset_poly(pts, d):
    """Miter offset of a closed CCW polygon (d > 0 grows it)."""
    p = np.array(pts, dtype=float)
    n = len(p)
    out = []
    for i in range(n):
        a, b, c = p[i - 1], p[i], p[(i + 1) % n]
        e1, e2 = b - a, c - b
        n1 = np.array([e1[1], -e1[0]]) / max(np.linalg.norm(e1), 1e-12)
        n2 = np.array([e2[1], -e2[0]]) / max(np.linalg.norm(e2), 1e-12)
        m = n1 + n2
        ml = np.linalg.norm(m)
        if ml < 1e-9:
            out.append(tuple(b + n1 * d))
            continue
        m /= ml
        cosh = max(0.25, float(np.dot(m, n1)))
        out.append(tuple(b + m * d / cosh))
    return out


def poly_area(pts):
    p = np.array(pts)
    return 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def ccw(pts):
    return pts if poly_area(pts) > 0 else pts[::-1]


# ============================================================================ 3D frame helpers
def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def basis_from_z(zdir, yhint=(0, 1, 0)):
    """Rotation matrix whose columns are (x, y, z) with z = zdir and y as close as possible to yhint."""
    z = np.array(zdir, float)
    z /= np.linalg.norm(z)
    y = np.array(yhint, float)
    y = y - z * np.dot(y, z)
    if np.linalg.norm(y) < 1e-6:
        y = np.array([1.0, 0, 0]) - z * z[0]
    y /= np.linalg.norm(y)
    x = np.cross(y, z)
    return np.stack([x, y, z], axis=1)


# ============================================================================ Part
class Part:
    """Polygon soup with per-face material slot names and low/high flags (authored in Unity local space)."""

    def __init__(self, name):
        self.name = name
        self.V = []          # list of np arrays (k, 3)
        self.F = []          # list of (faces, mat, lod, smooth)
        self.empties = {}    # name -> (pos, zdir, ydir)
        self.nv = 0

    # -- low level
    def add(self, verts, faces, mat, lod="both", M=None, t=(0, 0, 0)):
        v = np.array(verts, dtype=float)
        if M is not None:
            v = v @ np.array(M, float).T
        v = v + np.array(t, float)
        base = self.nv
        self.V.append(v)
        self.nv += len(v)
        self.F.append(([tuple(i + base for i in f) for f in faces], mat, lod))
        return self

    def empty(self, name, pos, zdir=(0, 0, 1), ydir=(0, 1, 0)):
        self.empties[name] = (np.array(pos, float), np.array(zdir, float), np.array(ydir, float))

    # -- primitives (all closed shells)
    def loft(self, sections, mat, lod="both", cap0=True, cap1=True, M=None, t=(0, 0, 0)):
        """sections: list of (z, ring) where ring is a list of (x, y) with equal counts (CCW)."""
        n = len(sections[0][1])
        V, F = [], []
        for z, ring in sections:
            assert len(ring) == n, "loft rings differ"
            V += [(x, y, z) for x, y in ring]
        for s in range(len(sections) - 1):
            for i in range(n):
                a, b = s * n + i, s * n + (i + 1) % n
                F.append((a, b, b + n, a + n))
        if cap0:
            F.append(tuple(range(n))[::-1])
        if cap1:
            last = (len(sections) - 1) * n
            F.append(tuple(last + i for i in range(n)))
        return self.add(V, F, mat, lod, M, t)

    def loft_axis(self, sections, mat, origin, zdir, yhint=(0, 1, 0), lod="both", cap0=True, cap1=True):
        """Loft along an arbitrary axis: section z is measured from origin along zdir."""
        R = basis_from_z(zdir, yhint)
        return self.loft(sections, mat, lod, cap0, cap1, M=R, t=origin)

    def prism(self, ring, z0, z1, mat, lod="both", chamfer=0.0, M=None, t=(0, 0, 0)):
        """Extrude a 2D ring along z, optionally chamfering both ends."""
        ring = ccw(ring)
        if chamfer > 0:
            inner = offset_poly(ring, -chamfer)
            secs = [(z0, inner), (z0 + chamfer, ring), (z1 - chamfer, ring), (z1, inner)]
        else:
            secs = [(z0, ring), (z1, ring)]
        return self.loft(secs, mat, lod, M=M, t=t)

    def side_profile(self, prof_zy, hw, mat, lod="both", chamfer=0.0, x0=0.0, M=None, t=(0, 0, 0)):
        """Profile drawn in the side view (z, y), extruded across x in [x0-hw, x0+hw] with chamfered sides."""
        ring = ccw([(z, y) for z, y in prof_zy])
        R = np.array([[0, 0, 1], [0, 1, 0], [1, 0, 0]], float)   # (a=z, b=y, c=x) -> (x, y, z)
        if M is not None:
            R = np.array(M, float) @ R
        if chamfer > 0:
            inner = offset_poly(ring, -chamfer)
            secs = [(x0 - hw, inner), (x0 - hw + chamfer, ring), (x0 + hw - chamfer, ring), (x0 + hw, inner)]
        else:
            secs = [(x0 - hw, ring), (x0 + hw, ring)]
        # loft along "c" (= x): build in (a, b, c) then rotate
        n = len(ring)
        V, F = [], []
        for c, rr in secs:
            V += [(a, b, c) for a, b in rr]
        for s in range(len(secs) - 1):
            for i in range(n):
                a_, b_ = s * n + i, s * n + (i + 1) % n
                F.append((a_, b_, b_ + n, a_ + n))
        F.append(tuple(range(n))[::-1])
        last = (len(secs) - 1) * n
        F.append(tuple(last + i for i in range(n)))
        return self.add(V, F, mat, lod, M=R, t=t)

    def box(self, c, size, mat, lod="both", chamfer=0.0, M=None):
        hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
        ring = chamfer_rect(hx, -hy, hy, chamfer * 0.6, chamfer * 0.6) if chamfer > 0 else chamfer_rect(hx, -hy, hy)
        R = np.eye(3) if M is None else np.array(M, float)
        return self.prism(ring, -hz, hz, mat, lod, chamfer=0.0, M=R, t=c)

    def cyl(self, r, z0, z1, n, mat, lod="both", r1=None, M=None, t=(0, 0, 0), chamfer=0.0):
        r1 = r if r1 is None else r1
        if chamfer > 0:
            secs = [(z0, circle(r - chamfer, n)), (z0 + chamfer, circle(r, n)), (z1 - chamfer, circle(r1, n)), (z1, circle(r1 - chamfer, n))]
        else:
            secs = [(z0, circle(r, n)), (z1, circle(r1, n))]
        return self.loft(secs, mat, lod, M=M, t=t)

    def cyl_axis(self, r, a, b, n, mat, lod="both", r1=None, yhint=(0, 1, 0), chamfer=0.0):
        a, b = np.array(a, float), np.array(b, float)
        L = float(np.linalg.norm(b - a))
        return self.cyl(r, 0.0, L, n, mat, lod, r1, M=basis_from_z(b - a, yhint), t=a, chamfer=chamfer)

    def tube_ring(self, R, r, n, m, mat, lod="both", M=None, t=(0, 0, 0), ry=None):
        """Torus around the local z axis (major radius R, minor r)."""
        ry = R if ry is None else ry
        V, F = [], []
        for i in range(n):
            a = TAU * i / n
            cx, cy = R * math.cos(a), ry * math.sin(a)
            nx, ny = math.cos(a), math.sin(a)
            for j in range(m):
                b = TAU * j / m
                V.append((cx + nx * r * math.cos(b), cy + ny * r * math.cos(b), r * math.sin(b)))
        for i in range(n):
            for j in range(m):
                a = i * m + j
                b = i * m + (j + 1) % m
                c = ((i + 1) % n) * m + (j + 1) % m
                d = ((i + 1) % n) * m + j
                F.append((a, d, c, b))
        return self.add(V, F, mat, lod, M, t)

    def sweep(self, path, ring, mat, lod="both", yhint=(0, 1, 0), closed=False, scales=None, smooth=0):
        """Sweep a 2D ring (x, y) along a 3D polyline with parallel-transport frames (smooth > 0: Catmull-Rom
        subdivide the path that many times per segment)."""
        P = np.array(path, float)
        if smooth > 0 and not closed and len(P) > 2:
            Q = [P[0]]
            ext = np.vstack([P[0] * 2 - P[1], P, P[-1] * 2 - P[-2]])
            for i in range(1, len(ext) - 2):
                p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
                for k in range(1, smooth + 1):
                    t = k / smooth
                    t2, t3 = t * t, t * t * t
                    Q.append(0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (3 * p1 - p0 - 3 * p2 + p3) * t3))
            P = np.array(Q)
        n = len(ring)
        V, F = [], []
        k = len(P)
        tang = []
        for i in range(k):
            if closed:
                d = P[(i + 1) % k] - P[i - 1]
            else:
                d = P[min(i + 1, k - 1)] - P[max(i - 1, 0)]
            tang.append(d / max(np.linalg.norm(d), 1e-12))
        up = np.array(yhint, float)
        frames = []
        for i in range(k):
            z = tang[i]
            y = up - z * np.dot(up, z)
            if np.linalg.norm(y) < 1e-6:
                y = np.array([1.0, 0, 0])
            y /= np.linalg.norm(y)
            x = np.cross(y, z)
            frames.append((x, y))
            up = y
        for i in range(k):
            x, y = frames[i]
            s = 1.0 if scales is None else scales[i]
            for (a, b) in ring:
                V.append(tuple(P[i] + x * a * s + y * b * s))
        segs = k if closed else k - 1
        for i in range(segs):
            for j in range(n):
                a = i * n + j
                b = i * n + (j + 1) % n
                c = ((i + 1) % k) * n + (j + 1) % n
                d = ((i + 1) % k) * n + j
                F.append((a, b, c, d))
        if not closed:
            F.append(tuple(range(n))[::-1])
            F.append(tuple((k - 1) * n + j for j in range(n)))
        return self.add(V, F, mat, lod)

    def ridges(self, a, b, count, size, mat, lod="hi", M=None):
        """`count` small boxes evenly spaced from a to b (serrations, grip ribs, vents) -- high-poly detail."""
        a, b = np.array(a, float), np.array(b, float)
        for i in range(count):
            c = a + (b - a) * (i / max(1, count - 1))
            self.box(c, size, mat, lod, M=M)
        return self

    def rivet(self, c, normal, r, h, mat, lod="hi", n=10):
        return self.cyl(r, 0.0, h, n, mat, lod, M=basis_from_z(normal), t=c, chamfer=min(r * 0.35, h * 0.45))


# ============================================================================ scene
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = "GPU"
    except Exception as e:  # noqa: BLE001
        print("[wkit] GPU unavailable:", e)


U2B = np.array([[-1, 0, 0], [0, 0, -1], [0, 1, 0]], float)


def u2b(v):
    return U2B @ np.array(v, float)


def material(name, color=(0.5, 0.5, 0.5), metal=0.0, rough=0.5, emit=None, emit_strength=0.0):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (*color, 1)
            bsdf.inputs["Metallic"].default_value = metal
            bsdf.inputs["Roughness"].default_value = rough
            if emit is not None:
                bsdf.inputs["Emission Color"].default_value = (*emit, 1)
                bsdf.inputs["Emission Strength"].default_value = emit_strength
    return m


def build_object(part, which, mats, name=None, location=(0, 0, 0)):
    """Create a mesh object from a Part ('lo' or 'hi' faces), mapped to Blender space."""
    name = name or f"{part.name}_{which}"
    V = np.concatenate(part.V, axis=0) if part.V else np.zeros((0, 3))
    VB = V @ U2B.T
    bm = bmesh.new()
    verts = [bm.verts.new(tuple(v)) for v in VB]
    bm.verts.ensure_lookup_table()
    slot_names = []
    for faces, mat, lod in part.F:
        if which == "lo" and lod == "hi":
            continue
        if which == "hi" and lod == "lo":
            continue
        if mat not in slot_names:
            slot_names.append(mat)
        mi = slot_names.index(mat)
        for f in faces:
            try:
                fc = bm.faces.new([verts[i] for i in f])
                fc.material_index = mi
            except ValueError:
                pass
    # drop unused verts
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for s in slot_names:
        me.materials.append(mats[s])
    ob = bpy.data.objects.new(name, me)
    ob.location = location
    bpy.context.scene.collection.objects.link(ob)
    return ob


def make_low(part, mats, location, sharp_deg=40.0):
    ob = build_object(part, "lo", mats, part.name, location)
    me = ob.data
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(sharp_deg))
    return ob


def make_high(part, mats, location, bevel=0.0015, segments=3):
    ob = build_object(part, "hi", mats, part.name + "_hi", location)
    me = ob.data
    me.shade_smooth()
    if bevel > 0:
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width = bevel
        m.segments = segments
        m.limit_method = "ANGLE"
        m.angle_limit = math.radians(30)
        m.profile = 0.6
        m.use_clamp_overlap = True
        m.harden_normals = False
    ws = ob.modifiers.new("wn", "WEIGHTED_NORMAL")
    ws.keep_sharp = False
    return ob


def apply_modifiers(ob):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.scene.objects:
        o.select_set(False)
    ob.select_set(True)
    for m in list(ob.modifiers):
        try:
            bpy.ops.object.modifier_apply(modifier=m.name)
        except RuntimeError as e:
            print("[wkit] modifier apply failed", ob.name, m.name, e)


def triangulate(ob):
    m = ob.modifiers.new("tri", "TRIANGULATE")
    m.quad_method = "FIXED"
    m.ngon_method = "BEAUTY"
    m.keep_custom_normals = True
    apply_modifiers(ob)


def add_empties(part, ob):
    """Child empties (muzzle, sockets, eject...) with identity rotation in Unity; direction encoded in the name-free
    custom position only (directions are documented in code: +z of the weapon)."""
    out = []
    for name, (pos, zdir, ydir) in part.empties.items():
        e = bpy.data.objects.new(name, None)
        e.empty_display_size = 0.01
        bpy.context.scene.collection.objects.link(e)
        e.parent = ob
        e.location = Vector(tuple(u2b(pos)))
        out.append(e)
    return out


# ============================================================================ UV atlas
def uv_atlas(objs, weights=None, margin=0.006):
    """Unwrap all low objects into one atlas: smart project, equalise texel density, optional per-object scale, pack."""
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(42.0), island_margin=0.0, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    if weights:
        for o in objs:
            w = weights.get(o.name, 1.0)
            if abs(w - 1.0) < 1e-6:
                continue
            uv = o.data.uv_layers.active.data
            a = np.empty(len(uv) * 2, np.float32)
            uv.foreach_get("uv", a)
            uv.foreach_set("uv", a * w)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")


# ============================================================================ baking
def _image(name, size, data=False):
    img = bpy.data.images.get(name)
    if img is None:
        img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=True)
    if data:
        img.colorspace_settings.name = "Non-Color"
    return img


def _target(objs, img):
    for o in objs:
        for m in o.data.materials:
            nt = m.node_tree
            node = nt.nodes.get("bake_target")
            if node is None:
                node = nt.nodes.new("ShaderNodeTexImage")
                node.name = "bake_target"
            node.image = img
            nt.nodes.active = node


def bake_atlas(pairs, size, id_colors, cage=0.004, ao_dist=0.05, samples=24):
    """pairs: list of (low_obj, high_obj, cage_extrusion). Returns dict of float arrays (size, size, 4)."""
    sc = bpy.context.scene
    sc.cycles.samples = samples
    sc.render.bake.margin = 4
    sc.render.bake.margin_type = "EXTEND"
    sc.world = sc.world or bpy.data.worlds.new("w")
    out = {}
    lows = [p[0] for p in pairs]
    # ID: emission colour per material on the high objects (keep the real material for previews: swap temporarily)
    for kind in ("NORMAL", "AO", "EMIT"):
        img = _image("bake_" + kind, size, data=(kind != "EMIT"))
        _target(lows, img)
        first = True
        for lo, hi, cg in pairs:
            swaps = []
            if kind == "EMIT":
                for i, m in enumerate(hi.data.materials):
                    idm = bpy.data.materials.get("ID_" + m.name)
                    if idm is None:
                        idm = bpy.data.materials.new("ID_" + m.name)
                        nt = idm.node_tree
                        for n in list(nt.nodes):
                            nt.nodes.remove(n)
                        em = nt.nodes.new("ShaderNodeEmission")
                        c = id_colors.get(m.name, (0, 0, 0))
                        em.inputs["Color"].default_value = (*c, 1)
                        outn = nt.nodes.new("ShaderNodeOutputMaterial")
                        nt.links.new(em.outputs[0], outn.inputs["Surface"])
                    swaps.append((i, m))
                    hi.data.materials[i] = idm
            if kind == "AO":
                sc.world.light_settings.distance = ao_dist
            for o in sc.objects:
                o.select_set(False)
                o.hide_render = o not in (lo, hi)
            hi.select_set(True)
            lo.select_set(True)
            bpy.context.view_layer.objects.active = lo
            bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=cg, max_ray_distance=cg * 4,
                                margin=4, use_clear=first, normal_space="TANGENT")
            first = False
            for i, m in swaps:
                hi.data.materials[i] = m
        for o in sc.objects:
            o.hide_render = False
        a = np.empty(size * size * 4, np.float32)
        img.pixels.foreach_get(a)
        out[kind] = a.reshape(size, size, 4).copy()
        print("[wkit] baked", kind)
    return out


# ============================================================================ texture composition
def value_noise(size, cells, seed):
    rng = np.random.default_rng(seed)
    g = rng.random((cells + 1, cells + 1)).astype(np.float32)
    x = np.linspace(0, cells, size, endpoint=False, dtype=np.float32)
    i = x.astype(int)
    f = x - i
    f = f * f * (3 - 2 * f)
    a = g[i][:, i]
    b = g[i][:, i + 1]
    c = g[i + 1][:, i]
    d = g[i + 1][:, i + 1]
    fx = f[None, :]
    fy = f[:, None]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(size, base, octaves, seed):
    s = np.zeros((size, size), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        s += value_noise(size, base * (2 ** o), seed + o) * amp
        tot += amp
        amp *= 0.5
    return s / tot


def blur(a, r):
    if r <= 0:
        return a
    k = np.ones(2 * r + 1, np.float32) / (2 * r + 1)
    a = np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), 0, a)
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), 1, a)


def box_blur(a, r):
    """Fast separable box blur via cumulative sums (edges clamp)."""
    if r <= 0:
        return a
    p = np.pad(a, ((r + 1, r), (0, 0)), mode="edge")
    c = np.cumsum(p, axis=0)
    a = (c[2 * r + 1:] - c[:-2 * r - 1]) / (2 * r + 1)
    p = np.pad(a, ((0, 0), (r + 1, r)), mode="edge")
    c = np.cumsum(p, axis=1)
    return (c[:, 2 * r + 1:] - c[:, :-2 * r - 1]) / (2 * r + 1)


def compose(baked, palette, size, seed=7, wear=1.0):
    """palette: list of dicts {name, id, color, metal, rough, wear_color, wear_metal, wear_rough, grime}.
    Returns BaseColor (rgba), MetalSmooth (rgba: R metal, A smoothness), Occlusion (rgb), Normal (rgb) as float arrays."""
    idmap = baked["EMIT"][..., :3]
    ao = baked["AO"][..., 0]
    nrm = baked["NORMAL"][..., :3]
    best = np.full(idmap.shape[:2], 1e9, np.float32)
    idx = np.zeros(idmap.shape[:2], np.int32)
    for k, p in enumerate(palette):
        d = ((idmap - np.array(p["id"], np.float32)) ** 2).sum(-1)
        m = d < best
        best[m] = d[m]
        idx[m] = k
    col = np.array([p["color"] for p in palette], np.float32)[idx]
    metal = np.array([p["metal"] for p in palette], np.float32)[idx]
    rough = np.array([p["rough"] for p in palette], np.float32)[idx]
    wcol = np.array([p.get("wear_color", p["color"]) for p in palette], np.float32)[idx]
    wmetal = np.array([p.get("wear_metal", 1.0) for p in palette], np.float32)[idx]
    wrough = np.array([p.get("wear_rough", 0.3) for p in palette], np.float32)[idx]
    grime_k = np.array([p.get("grime", 1.0) for p in palette], np.float32)[idx]
    wear_k = np.array([p.get("wear", 1.0) for p in palette], np.float32)[idx] * wear
    # curvature from the tangent-space normal map (divergence): + on convex edges, - in cavities
    nx = nrm[..., 0] * 2 - 1
    ny = nrm[..., 1] * 2 - 1
    div = (np.roll(nx, -1, 1) - np.roll(nx, 1, 1)) + (np.roll(ny, -1, 0) - np.roll(ny, 1, 0))
    div = box_blur(div.astype(np.float32), max(1, size // 1024))
    s = size / 1024.0
    edge = np.clip(div * 2.4 / max(s, 0.5), 0, 1)
    cav = np.clip(-div * 2.0 / max(s, 0.5), 0, 1)
    n1 = fbm(size, 6, 5, seed)
    n2 = fbm(size, 24, 4, seed + 11)
    n3 = fbm(size, 64, 3, seed + 23)
    wear_mask = np.clip((edge * (0.55 + 0.9 * n2) - 0.35) * 2.2, 0, 1) * wear_k
    grime = np.clip((1 - ao) * 1.25 + cav * 0.5, 0, 1) * (0.6 + 0.4 * n1) * grime_k
    base = col * (0.88 + 0.24 * n1[..., None]) * (0.94 + 0.12 * n3[..., None])
    base = base * (1 - wear_mask[..., None]) + wcol * wear_mask[..., None]
    base = base * (1 - 0.55 * grime[..., None])
    m = metal * (1 - wear_mask) + wmetal * wear_mask
    r = rough * (1 - wear_mask) + wrough * wear_mask
    r = np.clip(r + (n2 - 0.5) * 0.18 + grime * 0.25 + (n3 - 0.5) * 0.06, 0.04, 1)
    bc = np.concatenate([np.clip(base, 0, 1), np.ones((size, size, 1), np.float32)], -1)
    ms = np.stack([np.clip(m, 0, 1), np.zeros_like(m), np.zeros_like(m), 1 - r], -1)
    occ = np.clip(ao * 0.85 + 0.15, 0, 1)
    occ = np.stack([occ, occ, occ, np.ones_like(occ)], -1)
    nm = np.concatenate([nrm, np.ones((size, size, 1), np.float32)], -1)
    return {"BaseColor": bc, "MetalSmooth": ms, "Occlusion": occ, "Normal": nm}


def save_png(arr, path, srgb=True):
    """arr: (h, w, 4) float in 0..1 (linear if srgb=True -> encoded to sRGB)."""
    h, w, _ = arr.shape
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True, float_buffer=False)
    a = arr.astype(np.float32).copy()
    if srgb:
        rgb = a[..., :3]
        a[..., :3] = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(np.clip(rgb, 0, None), 1 / 2.4) - 0.055)
        img.colorspace_settings.name = "sRGB"
    else:
        img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(np.clip(a, 0, 1).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save()
    bpy.data.images.remove(img)


# ============================================================================ export
def export_fbx(path, objs, vertex_colors=False):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
        for c in o.children:
            c.select_set(True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"EMPTY", "MESH"},
        axis_forward="-Z", axis_up="Y", apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL", global_scale=1.0,
        # Apply Transform: the axis conversion goes into the vertex data, so every node imports with an identity
        # rotation and the meshes are in the authored Unity space (x right, y up, z forward).
        bake_space_transform=True, use_mesh_modifiers=True, mesh_smooth_type="OFF", use_triangles=True,
        use_tspace=False, add_leaf_bones=False, bake_anim=False, path_mode="STRIP", embed_textures=False,
        use_custom_props=False, colors_type="LINEAR" if vertex_colors else "NONE", use_mesh_edges=False)


def tri_count(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    n = sum(len(p.vertices) - 2 for p in me.polygons)
    ob.evaluated_get(dg).to_mesh_clear()
    return n
