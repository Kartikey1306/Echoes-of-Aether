"""robokit -- hard-surface modelling helpers for the Echoes of Aether robot pipeline (Blender 5.2, headless).

Conventions
-----------
* Geometry is authored in *robot space* (the prototype / three.js convention used by RobotBodies.cs):
  x = robot's LEFT, y = UP, z = FORWARD (the robot faces +z). Biped bodies are authored in reference units of the
  1.8 m body (ROBOT_PARTS.md "s" factor) and scaled by s when the objects are created.
* robot space -> Blender: (x, y, z) -> (x, -z, y)   (robot faces -Y, left on +X: what ROBOT_PARTS.md asks for)
* Blender -> Unity (FBX -Z fwd / Y up, Unity flips X): (bx, by, bz) -> (-bx, bz, -by)
* Every transform has identity rotation / unit scale in the rest pose, so Unity sees identity local rotations.
* One mesh object per bone (the bone *is* the mesh object, its origin at the joint); special parts (core, plates,
  rotors) are their own objects. Material slots: robot_shell / robot_frame / robot_joint / robot_glow (+ robot_rotor).
"""
import math
from collections import defaultdict

import bmesh
import bpy
from mathutils import Matrix, Vector

SHELL, FRAME, JOINT, GLOW, ROTOR = range(5)
MAT_NAMES = ("robot_shell", "robot_frame", "robot_joint", "robot_glow", "robot_rotor")

BONES = ["root", "hips", "spine", "chest", "neck", "head",
         "clavicle_L", "upperarm_L", "forearm_L", "hand_L",
         "clavicle_R", "upperarm_R", "forearm_R", "hand_R",
         "thigh_L", "shin_L", "foot_L", "thigh_R", "shin_R", "foot_R"]
PARENT = [-1, 0, 1, 2, 3, 4, 3, 6, 7, 8, 3, 10, 11, 12, 1, 14, 15, 1, 17, 18]

ID = Matrix.Identity(4)
MIRROR_X = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))


# ============================================================================ space conversion
def r2b(v):
    v = Vector(v)
    return Vector((v.x, -v.z, v.y))


def b2u(v):
    """Blender world position -> Unity position (what the FBX importer produces)."""
    return Vector((-v[0], v[2], -v[1]))


R2B = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


# ============================================================================ joints (port of RobotRig.ComputeJoints)
def compute_joints(shoulder_width=1.15):
    """Reference-body (1.8 m) joints in robot space (left = +x). Multiply by s = height / 1.8."""
    j = {}
    sw, hw = 0.186 * shoulder_width, 0.094
    j["root"] = Vector((0, 0, 0))
    j["hips"] = Vector((0, 0.955, 0))
    j["spine"] = Vector((0, 1.075, -0.012))
    j["chest"] = Vector((0, 1.245, -0.022))
    j["neck"] = Vector((0, 1.47, -0.026))
    j["head"] = Vector((0, 1.56, -0.012))
    j["headCenter"] = Vector((0, 1.56 + 0.103, 0.014))
    j["headTop"] = Vector((0, 1.56 + 0.103 + 0.118, 0.01))
    a = math.radians(14.0)
    a2 = a - 0.04
    arm_y, up, fo, hand = 1.458, 0.305, 0.262, 0.185
    for sd, sx in (("L", 1.0), ("R", -1.0)):
        j["clavicle_" + sd] = Vector((sx * 0.028, arm_y - 0.005, -0.006))
        shx, shy, shz = sx * sw, arm_y, -0.022
        elx, ely, elz = shx + sx * math.sin(a) * up, shy - math.cos(a) * up, shz - 0.012
        wrx, wry, wrz = elx + sx * math.sin(a2) * fo, ely - math.cos(a2) * fo, elz + 0.022
        j["upperarm_" + sd] = Vector((shx, shy, shz))
        j["forearm_" + sd] = Vector((elx, ely, elz))
        j["hand_" + sd] = Vector((wrx, wry, wrz))
        j["handEnd_" + sd] = Vector((wrx + sx * math.sin(a2) * hand, wry - math.cos(a2) * hand, wrz + 0.008))
        j["thigh_" + sd] = Vector((sx * hw, 0.93, 0.0))
        j["shin_" + sd] = Vector((sx * (hw + 0.008), 0.515, 0.016))
        j["foot_" + sd] = Vector((sx * (hw + 0.012), 0.088, -0.022))
        j["toe_" + sd] = Vector((sx * (hw + 0.02), 0.03, 0.165))
        j["heel_" + sd] = Vector((sx * (hw + 0.012), 0.03, -0.075))
    return j


# ============================================================================ matrices
def T(x=0.0, y=0.0, z=0.0):
    if isinstance(x, (Vector, tuple, list)):
        return Matrix.Translation(Vector(x))
    return Matrix.Translation((x, y, z))


def R(x=0.0, y=0.0, z=0.0):
    """Euler XYZ rotation (radians) as 4x4 (applied X, then Y, then Z)."""
    return (Matrix.Rotation(z, 4, "Z") @ Matrix.Rotation(y, 4, "Y") @ Matrix.Rotation(x, 4, "X"))


def Rd(x=0.0, y=0.0, z=0.0):
    return R(math.radians(x), math.radians(y), math.radians(z))


def Sc(x, y=None, z=None):
    y = x if y is None else y
    z = x if z is None else z
    return Matrix.Diagonal((x, y, z, 1.0))


def frame(origin, y_axis, z_hint=(0, 0, 1)):
    """Frame at `origin` whose local +Y is `y_axis`, local +Z as close as possible to z_hint, X = Y x Z."""
    y = Vector(y_axis).normalized()
    z = Vector(z_hint)
    z = (z - y * z.dot(y))
    if z.length < 1e-6:
        z = Vector((0, 0, 1)) if abs(y.z) < 0.9 else Vector((1, 0, 0))
        z = (z - y * z.dot(y))
    z.normalize()
    x = y.cross(z)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(origin)
    return m


def limb(a, b, z_hint=(0, 0, 1)):
    """Limb frame at joint a; local +Y points from b back up to a (so the limb runs along -Y), z forward."""
    return frame(a, Vector(a) - Vector(b), z_hint)


# ============================================================================ bmesh primitives
def _mat(bm, m):
    for f in bm.faces:
        f.material_index = m
    return bm


def _sharp_edges(bm, min_deg=35.0):
    lim = math.radians(min_deg)
    out = []
    for e in bm.edges:
        if len(e.link_faces) != 2:
            continue
        if e.calc_face_angle(0.0) > lim:
            out.append(e)
    return out


def bevel(bm, w, seg=1, min_deg=35.0, prof=0.5):
    if w <= 0:
        return bm
    edges = _sharp_edges(bm, min_deg)
    if not edges:
        return bm
    verts = list({v for e in edges for v in e.verts})
    bmesh.ops.bevel(bm, geom=edges + verts, offset=w, offset_type="OFFSET", segments=seg, profile=prof,
                    affect="EDGES", clamp_overlap=True, loop_slide=True)
    return bm


def faces_toward(bm, d, min_dot=0.92, min_frac=0.2):
    d = Vector(d).normalized()
    fs = [f for f in bm.faces if f.normal.dot(d) > min_dot]
    if not fs:
        return []
    amax = max(f.calc_area() for f in fs)
    return [f for f in fs if f.calc_area() >= amax * min_frac]


def inset(bm, faces, t, depth=0.0, mat=None, region=False):
    if not faces:
        return []
    if region:
        r = bmesh.ops.inset_region(bm, faces=faces, thickness=t, depth=depth, use_even_offset=True)
    else:
        r = bmesh.ops.inset_individual(bm, faces=faces, thickness=t, depth=depth, use_even_offset=True)
    if mat is not None:
        for f in faces:
            f.material_index = mat
    return r.get("faces", [])


_DIRS = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0), "-y": (0, -1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}


def panels(bm, spec):
    """spec: list of (dir, inset, depth[, mat]) -- recessed panel on the largest faces facing dir.
    Negative depth recesses (panel line around a sunk panel); positive raises."""
    for item in spec:
        d, t, dep = item[0], item[1], item[2]
        m = item[3] if len(item) > 3 else None
        fs = faces_toward(bm, _DIRS[d] if isinstance(d, str) else d)
        inset(bm, fs, t, dep, m)
    return bm


def box(w, h, d, mat, bev=0.0, seg=1, taper=(1.0, 1.0), shift=(0.0, 0.0), btaper=(1.0, 1.0), pan=None, fbev=None):
    """Chamfered box centred at origin. taper scales the top (+y) face in x/z, shift moves it (x, z);
    btaper scales the bottom face."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= w
        v.co.y *= h
        v.co.z *= d
        if v.co.y > 0:
            v.co.x = v.co.x * taper[0] + shift[0]
            v.co.z = v.co.z * taper[1] + shift[1]
        else:
            v.co.x *= btaper[0]
            v.co.z *= btaper[1]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bevel(bm, bev if fbev is None else fbev, seg)
    _mat(bm, mat)
    if pan:
        panels(bm, pan)
    return bm


def prism(pts, depth, mat, axis="x", bev=0.0, seg=1, pan=None, taper=1.0, min_deg=35.0):
    """Extrude a 2D profile. axis 'x': pts are (z, y) [side view]; 'z': (x, y) [front view]; 'y': (x, z) [top view].
    `taper` scales the +axis cap about the profile centroid (draft angle)."""
    bm = bmesh.new()

    def P(a, b, c):
        if axis == "x":
            return Vector((c, b, a))
        if axis == "z":
            return Vector((a, b, c))
        return Vector((a, c, b))

    ca = sum(p[0] for p in pts) / len(pts)
    cb = sum(p[1] for p in pts) / len(pts)
    v0 = [bm.verts.new(P(a, b, -depth / 2)) for a, b in pts]
    v1 = [bm.verts.new(P(ca + (a - ca) * taper, cb + (b - cb) * taper, depth / 2)) for a, b in pts]
    n = len(pts)
    bm.faces.new(v0)
    bm.faces.new(v1[::-1])
    for i in range(n):
        bm.faces.new((v0[i], v0[(i + 1) % n], v1[(i + 1) % n], v1[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bevel(bm, bev, seg, min_deg)
    _mat(bm, mat)
    if pan:
        panels(bm, pan)
    return bm


def cyl(r, h, n, mat, axis="y", r2=None, bev=0.0, seg=1, hollow=None, cap_inset=None):
    """Cylinder/cone centred at origin along axis. r = radius at -axis end, r2 at +axis end.
    hollow=(wall, depth): recess the +axis cap (pipe / exhaust). cap_inset=(t, depth): inset ring on the +axis
    (outer) cap only -- place side parts so +axis faces outward (mirror the right side instead of offsetting it)."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=n, radius1=r,
                          radius2=r if r2 is None else r2, depth=h)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bevel(bm, bev, seg, 50.0)
    _mat(bm, mat)
    if hollow:
        top = faces_toward(bm, (0, 0, 1), 0.99, 0.5)
        inset(bm, top, hollow[0], -hollow[1])
    if cap_inset:
        inset(bm, faces_toward(bm, (0, 0, 1), 0.99, 0.5), cap_inset[0], cap_inset[1])
    _orient(bm, axis)
    return bm


def _orient(bm, axis):
    if axis == "y":
        bmesh.ops.transform(bm, matrix=Matrix.Rotation(-math.pi / 2, 4, "X"), verts=bm.verts)
    elif axis == "x":
        bmesh.ops.transform(bm, matrix=Matrix.Rotation(math.pi / 2, 4, "Y"), verts=bm.verts)
    elif axis == "-y":
        bmesh.ops.transform(bm, matrix=Matrix.Rotation(math.pi / 2, 4, "X"), verts=bm.verts)
    elif axis == "-x":
        bmesh.ops.transform(bm, matrix=Matrix.Rotation(-math.pi / 2, 4, "Y"), verts=bm.verts)
    elif axis == "-z":
        bmesh.ops.transform(bm, matrix=Matrix.Rotation(math.pi, 4, "X"), verts=bm.verts)


def sphere(r, mat, u=10, v=6, scale=(1, 1, 1)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=r)
    for vv in bm.verts:
        vv.co.x *= scale[0]
        vv.co.y *= scale[1]
        vv.co.z *= scale[2]
    _mat(bm, mat)
    return bm


def ico(r, mat, sub=1, scale=(1, 1, 1)):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
    for vv in bm.verts:
        vv.co.x *= scale[0]
        vv.co.y *= scale[1]
        vv.co.z *= scale[2]
    _mat(bm, mat)
    return bm


def torus(R_, r, mat, n=16, m=6, axis="y", arc=None, rx=None):
    """Torus around `axis` (ring in the perpendicular plane). arc=(a0, a1) radians for a partial ring.
    rx scales the tube cross-section radially (flattened rings)."""
    bm = bmesh.new()
    closed = arc is None
    a0, a1 = (0.0, 2 * math.pi) if closed else arc
    steps = n if closed else n + 1
    rings = []
    for i in range(steps):
        u = a0 + (a1 - a0) * i / n
        cu, su = math.cos(u), math.sin(u)
        ring = []
        for k in range(m):
            v = 2 * math.pi * k / m
            rr = R_ + (rx if rx is not None else r) * math.cos(v)
            ring.append(bm.verts.new((cu * rr, r * math.sin(v), su * rr)))
        rings.append(ring)
    for i in range(n):
        A, B = rings[i], rings[(i + 1) % steps]
        for k in range(m):
            bm.faces.new((A[k], A[(k + 1) % m], B[(k + 1) % m], B[k]))
    if not closed:
        bm.faces.new(rings[0])
        bm.faces.new(rings[-1][::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    _mat(bm, mat)
    if axis == "z":
        bmesh.ops.transform(bm, matrix=Matrix.Rotation(math.pi / 2, 4, "X"), verts=bm.verts)
    elif axis == "x":
        bmesh.ops.transform(bm, matrix=Matrix.Rotation(math.pi / 2, 4, "Z"), verts=bm.verts)
    return bm


def _catmull(pts, sub):
    if sub <= 1 or len(pts) < 3:
        return pts
    P = [pts[0]] + pts + [pts[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(sub):
            t = k / sub
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pts[-1])
    return out


def tube(pts, r, mat, n=6, caps=True, sub=1, r_end=None):
    """Cable / pipe along a polyline (optionally Catmull-Rom smoothed with `sub` steps per segment)."""
    pts = _catmull([Vector(p) for p in pts], sub)
    bm = bmesh.new()
    N = len(pts)
    tangents = []
    for i in range(N):
        a = pts[max(0, i - 1)]
        b = pts[min(N - 1, i + 1)]
        tangents.append((b - a).normalized())
    t0 = tangents[0]
    ref = Vector((0, 1, 0)) if abs(t0.y) < 0.9 else Vector((1, 0, 0))
    nrm = (ref - t0 * ref.dot(t0)).normalized()
    rings = []
    for i, p in enumerate(pts):
        t = tangents[i]
        nrm = (nrm - t * nrm.dot(t))
        if nrm.length < 1e-6:
            nrm = (ref - t * ref.dot(t))
        nrm.normalize()
        bn = t.cross(nrm)
        rr = r if r_end is None else r + (r_end - r) * i / max(1, N - 1)
        rings.append([bm.verts.new(p + (nrm * math.cos(2 * math.pi * k / n) + bn * math.sin(2 * math.pi * k / n)) * rr)
                      for k in range(n)])
    for i in range(N - 1):
        A, B = rings[i], rings[i + 1]
        for k in range(n):
            bm.faces.new((A[k], A[(k + 1) % n], B[(k + 1) % n], B[k]))
    if caps:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    _mat(bm, mat)
    return bm


def merge(*bms):
    """Merge several temp bmeshes into the first (others freed)."""
    out = bms[0]
    for b in bms[1:]:
        me = bpy.data.meshes.new("__tmp")
        b.to_mesh(me)
        out.from_mesh(me)
        bpy.data.meshes.remove(me)
        b.free()
    return out


def xf(bm, M):
    bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    if M.to_3x3().determinant() < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    return bm


# ============================================================================ accumulators
DEBUG_LOG = []


class Part:
    """Collects polygons (robot space) for one output mesh object."""

    def __init__(self):
        self.v = []
        self.f = []
        self.m = []

    def add(self, bm, M=ID):
        flip = M.to_3x3().determinant() < 0
        if DEBUG_LOG is not None:
            import traceback
            fr = [f for f in traceback.extract_stack()[:-1] if "robokit" not in f.filename]
            DEBUG_LOG.append((fr[-1].filename.split("/")[-1] + ":" + str(fr[-1].lineno) if fr else "?",
                              sum(len(f.verts) - 2 for f in bm.faces)))
        bm.verts.index_update()
        base = len(self.v)
        self.v.extend(M @ v.co for v in bm.verts)
        for f in bm.faces:
            ids = [base + v.index for v in f.verts]
            if flip:
                ids.reverse()
            self.f.append(ids)
            self.m.append(f.material_index)
        bm.free()


class Robot:
    """A robot under construction: parts keyed by object name; bones from compute_joints()."""

    def __init__(self, name, height=None, shoulder=1.15, skeleton=True):
        self.name = name
        self.skeleton = skeleton
        self.parts = defaultdict(Part)
        self.extra = {}  # object name -> (parent name, pivot robot-space ref units)
        self.s = (height / 1.8) if height else 1.0
        self.height = height
        self.J = compute_joints(shoulder) if skeleton else {}
        self.mirror = ID  # set by side()

    # ------------------------------------------------------------ side handling
    def side(self, sd):
        """Context for the robot's left ('L', built directly) or right ('R', mirrored from the left build)."""
        self.mirror = ID if sd == "L" else MIRROR_X
        self.sd = sd
        return self

    def add(self, obj, bm, M=ID, mirror=True):
        """Add geometry. If obj ends with '_S' it resolves to the current side; geometry is mirrored for 'R'."""
        if obj.endswith("_S"):
            obj = obj[:-2] + "_" + self.sd
            Mx = self.mirror if mirror else ID
        else:
            Mx = ID
        self.parts[obj].add(bm, Mx @ M)

    def both(self, obj, bm_fn, M):
        """Add a symmetric pair onto a central object: bm_fn() is called twice (left build + mirrored)."""
        self.parts[obj].add(bm_fn(), M)
        self.parts[obj].add(bm_fn(), MIRROR_X @ M)

    def special(self, name, parent, pivot):
        """Declare an extra transform (core / plate / rotor...) with pivot in robot space (ref units)."""
        self.extra[name] = (parent, Vector(pivot))

    def tri_count(self):
        n = 0
        for p in self.parts.values():
            n += sum(len(f) - 2 for f in p.f)
        return n


# ============================================================================ cross-section profiles (x, z) for prism(axis="y")
def RIDGE(w, d, r=None, back=0.0):
    """Armour cross-section with a raised centre ridge at +z (front). back > 0 chamfers the rear corners."""
    r = d * 0.38 if r is None else r
    pts = [(-w / 2 + back, -d / 2), (w / 2 - back, -d / 2), (w / 2, -d / 2 + back), (w / 2, d / 2 - r), (0.0, d / 2),
           (-w / 2, d / 2 - r), (-w / 2, -d / 2 + back)]
    return [p for i, p in enumerate(pts) if back > 0 or i not in (2, 6)]


def OCT(w, d, c):
    return [(-w / 2 + c, -d / 2), (w / 2 - c, -d / 2), (w / 2, -d / 2 + c), (w / 2, d / 2 - c), (w / 2 - c, d / 2),
            (-w / 2 + c, d / 2), (-w / 2, d / 2 - c), (-w / 2, -d / 2 + c)]


def HEX(w, d, c):
    return [(-w / 2 + c, -d / 2), (w / 2 - c, -d / 2), (w / 2, 0.0), (w / 2 - c, d / 2), (-w / 2 + c, d / 2), (-w / 2, 0.0)]


def lathe(prof, n, mat, phase=0.0):
    """Surface of revolution around +y. prof: (radius, y) from top to bottom; radius 0 makes a pole.
    Open ends are capped, so the result is closed."""
    bm = bmesh.new()
    rings = []
    for r, y in prof:
        if r < 1e-6:
            rings.append([bm.verts.new((0.0, y, 0.0))])
        else:
            rings.append([bm.verts.new((r * math.cos(phase + 2 * math.pi * k / n), y, r * math.sin(phase + 2 * math.pi * k / n)))
                          for k in range(n)])
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        for k in range(n):
            if len(a) == 1:
                bm.faces.new((a[0], b[(k + 1) % n], b[k]))
            elif len(b) == 1:
                bm.faces.new((a[k], a[(k + 1) % n], b[0]))
            else:
                bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
    for ring in (rings[0], rings[-1]):
        if len(ring) > 2:
            bm.faces.new(ring)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    _mat(bm, mat)
    return bm
