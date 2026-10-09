"""Hard-light and combat FX meshes (no textures: they are shaded by EOA/HardLight from UVs and vertex colours).

UV: u = around the section (0..1), v = along the length (0 base .. 1 tip).
Vertex colour: R = cutting-edge weight (1 on the edge line), G = spine / ridge weight, B = part id (0 hull, 1 core,
0.5 secondary), A = 1.
Unity local space (x right, y up, z forward), metres unless noted.
"""
import math

import bmesh
import bpy
import numpy as np

import wkit as W

TAU = math.tau


def build(name, rings, cols, tip=None, tip_uv=1.0, base_cap=True, smooth_deg=28.0):
    """rings: list of (v, [(x, y, z) ...]) all the same length n; cols: list of per-point colours (n entries, RGBA)
    reused on every ring. Appends a tip vertex (x, y, z) if given. Returns the Blender object."""
    n = len(rings[0][1])
    V, UV, C, F = [], [], [], []
    for v, ring in rings:
        for i in range(n + 1):
            V.append(ring[i % n])
            UV.append((i / n, v))
            C.append(cols[i % n])
    m = n + 1
    for r in range(len(rings) - 1):
        for i in range(n):
            a, b = r * m + i, r * m + i + 1
            F.append((a, b, b + m, a + m))
    if tip is not None:
        t0 = len(V)
        last = (len(rings) - 1) * m
        for i in range(n):
            V.append(tip)
            UV.append(((i + 0.5) / n, tip_uv))
            C.append((cols[i][0], cols[i][1], cols[i][2], 1.0))
            F.append((last + i, last + i + 1, t0 + i))
    if base_cap:
        c0 = len(V)
        cx = np.mean([p for p in rings[0][1]], axis=0)
        V.append(tuple(cx))
        UV.append((0.5, rings[0][0]))
        C.append((0, 0, cols[0][2], 1))
        for i in range(n):
            F.append((i + 1, i, c0))
    return mesh_object(name, V, UV, C, F, smooth_deg)


def mesh_object(name, V, UV, C, F, smooth_deg=28.0):
    VB = np.array(V, float) @ W.U2B.T
    bm = bmesh.new()
    vs = [bm.verts.new(tuple(p)) for p in VB]
    bm.verts.ensure_lookup_table()
    uvl = bm.loops.layers.uv.new("UVMap")
    col = bm.loops.layers.float_color.new("Col")
    for f in F:
        try:
            face = bm.faces.new([vs[i] for i in f])
        except ValueError:
            continue
        for loop, i in zip(face.loops, f):
            loop[uvl].uv = UV[i]
            loop[col] = C[i]
    # the U2B map mirrors (det -1): flip every face back to the authored winding
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    if smooth_deg is not None:
        me.set_sharp_from_angle(angle=math.radians(smooth_deg))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.get("hardlight") or bpy.data.materials.new("hardlight")
    me.materials.append(mat)
    return ob


# ============================================================================ Kael's hard-light blade (length 1)
def kael_blade_sections():
    zs = [0.0, 0.012, 0.035, 0.06, 0.09, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.74, 0.80, 0.85, 0.89, 0.925, 0.952, 0.973, 0.988]
    out = []
    for z in zs:
        W0 = 0.0285                                # half width of the main blade (5.7 cm wide)
        if z < 0.012:
            w, t = 0.0120, 0.0050
        elif z < 0.035:
            w, t = 0.0120 + (z - 0.012) / 0.023 * 0.0215, 0.0050 + (z - 0.012) / 0.023 * 0.0022
        elif z < 0.06:
            w, t = 0.0335 - (z - 0.035) / 0.025 * 0.0050, 0.0072
        elif z <= 0.80:
            w, t = W0 + 0.0020 * math.sin(math.pi * (z - 0.06) / 0.74), 0.0070 - 0.0010 * (z - 0.06) / 0.74
        else:
            k = (z - 0.80) / 0.20
            w = W0 * math.sqrt(max(0.0, 1 - k ** 1.6))
            t = 0.0060 * (1 - k) ** 0.7 + 0.0006
        curve = 0.030 * z * z                     # gentle curve towards the edge (+x)
        spine_bias = -0.45 * (max(0.0, (z - 0.80) / 0.20) ** 1.5) * W0    # the tip rises to the spine line
        out.append((z, w, t, curve + spine_bias))
    return out


def section_blade(w, t):
    """Single-edged section: edge at +x, rounded spine at -x, shallow fuller on both faces (11 points, CCW)."""
    return [(w, 0.0), (0.55 * w, 0.70 * t), (0.10 * w, 0.90 * t), (-0.45 * w, 1.00 * t), (-0.88 * w, 0.80 * t),
            (-w, 0.35 * t), (-w, -0.35 * t), (-0.88 * w, -0.80 * t), (-0.45 * w, -1.00 * t), (0.10 * w, -0.90 * t),
            (0.55 * w, -0.70 * t)]


BLADE_COLS = [(1, 0, 0, 1), (0.55, 0, 0, 1), (0.1, 0, 0, 1), (0, 0.2, 0, 1), (0, 0.8, 0, 1), (0, 1, 0, 1), (0, 1, 0, 1),
              (0, 0.8, 0, 1), (0, 0.2, 0, 1), (0.1, 0, 0, 1), (0.55, 0, 0, 1)]


def kael_blade():
    rings = []
    for z, w, t, cx in kael_blade_sections():
        rings.append((z, [(cx + x, y, z) for x, y in section_blade(w, t)]))
    hull = build("kael_blade_hull", rings, BLADE_COLS, tip=(0.030 - 0.45 * 0.0285 + 0.002, 0.0, 1.0))
    core_rings = []
    for z, w, t, cx in kael_blade_sections():
        if z < 0.015 or z > 0.96:
            continue
        core_rings.append((z, [(cx - 0.12 * w + x, y, z) for x, y in section_blade(w * 0.42, t * 0.42)]))
    core_cols = [(c[0], c[1], 1.0, 1) for c in BLADE_COLS]
    core = build("kael_blade_core", core_rings, core_cols, tip=(0.030 - 0.0110, 0.0, 0.975))
    return [hull, core]


# ============================================================================ Giva's hard-light claw (metres)
def giva_claw():
    L = 0.165
    zs = np.linspace(0.0, 1.0, 14)
    rings, core = [], []
    for u in zs[:-1]:
        z = u * L
        w = 0.0062 * (1 - u ** 1.4) + 0.0008
        t = 0.0026 * (1 - u ** 1.2) + 0.0005
        dy = -0.22 * z * z / L                     # hooks down (palm side) like a talon
        ring = [(w, dy), (0.35 * w, dy + t), (-0.35 * w, dy + t), (-w, dy), (-0.35 * w, dy - t), (0.35 * w, dy - t)]
        rings.append((u, [(x, y, z) for x, y in ring]))
        if 0.04 < u < 0.9:
            rc = [(x * 0.4, dy + (y - dy) * 0.4, z) for x, y in ring]
            core.append((u, rc))
    cols = [(1, 0, 0, 1), (0.2, 0.6, 0, 1), (0.2, 0.6, 0, 1), (1, 0, 0, 1), (0.2, 0.6, 0, 1), (0.2, 0.6, 0, 1)]
    hull = build("giva_claw_hull", rings, cols, tip=(0, -0.22 * L, L))
    corem = build("giva_claw_core", core, [(c[0], c[1], 1.0, 1) for c in cols], tip=(0, -0.22 * L * 0.9 ** 2, L * 0.92))
    return [hull, corem]


# ============================================================================ projectile (radius 1 at z = 0, nose +z)
def bolt():
    zs = [-3.4, -3.0, -2.5, -2.0, -1.5, -1.0, -0.6, -0.3, 0.0, 0.25, 0.5, 0.7, 0.85, 0.95]
    n = 10
    rings, core = [], []
    for z in zs:
        if z <= 0:
            r = (1 - (abs(z) / 3.45)) ** 1.25
        else:
            r = math.sqrt(max(0.0, 1 - (z / 1.0) ** 2))
        tw = z * 0.55
        ring = []
        for k in range(n):
            a = TAU * k / n + tw
            rr = r * (1.0 if k % 2 == 0 else 0.86)            # faceted crystal flutes
            ring.append((rr * math.cos(a), rr * math.sin(a), z))
        rings.append(((z + 3.4) / 4.4, ring))
        if -1.9 <= z <= 0.6:
            rc = 0.42 * (math.sqrt(max(0.0, 1 - (z / 0.62) ** 2)) if z > 0 else (1 - abs(z) / 2.0) ** 0.8)
            core.append(((z + 3.4) / 4.4, [(rc * math.cos(TAU * k / n), rc * math.sin(TAU * k / n), z) for k in range(n)]))
    cols = [((1 if k % 2 == 0 else 0.4), 0, 0, 1) for k in range(n)]
    hull = build("bolt_hull", rings, cols, tip=(0, 0, 1.0), tip_uv=1.0, smooth_deg=50)
    corem = build("bolt_core", core, [(1, 0, 1, 1)] * n, tip=(0, 0, 0.62), smooth_deg=None)
    return [hull, corem]


# ============================================================================ muzzle flash (length 1 along +z)
def diamond_prism(a, b, w, t, roll=0.0):
    """Thin 4-sided spike from a to b (w half width, t half thickness at the widest point, 30% along)."""
    a, b = np.array(a, float), np.array(b, float)
    d = b - a
    L = np.linalg.norm(d)
    R = W.basis_from_z(d, (math.cos(roll), math.sin(roll), 0))
    pts = []
    for u, s in ((0.0, 0.25), (0.3, 1.0), (0.75, 0.45)):
        c = a + d * u
        for x, y in ((w * s, 0), (0, t * s), (-w * s, 0), (0, -t * s)):
            pts.append(tuple(c + R @ np.array([x, y, 0.0])))
    return pts, b


def flash():
    V, UV, C, F = [], [], [], []

    def add_spike(a, b, w, t, intensity, roll):
        pts, tip = diamond_prism(a, b, w, t, roll)
        base = len(V)
        L = np.linalg.norm(np.array(b) - np.array(a))
        for r in range(3):
            for k in range(4):
                V.append(pts[r * 4 + k])
                UV.append((k / 4, (0.0, 0.3, 0.75)[r]))
                C.append((intensity, 0, 0.5, 1))
        V.append(tuple(tip))
        UV.append((0.5, 1.0))
        C.append((intensity, 0, 0.5, 1))
        ti = len(V) - 1
        for r in range(2):
            for k in range(4):
                a_, b_ = base + r * 4 + k, base + r * 4 + (k + 1) % 4
                F.append((a_, b_, b_ + 4, a_ + 4))
        for k in range(4):
            F.append((base + 8 + k, base + 8 + (k + 1) % 4, ti))
        F.append((base + 3, base + 2, base + 1, base + 0))

    rng = np.random.default_rng(3)
    # forward petals
    for k in range(6):
        a = TAU * k / 6 + 0.2
        tilt = math.radians(18 + 10 * (k % 2))
        d = np.array([math.sin(tilt) * math.cos(a), math.sin(tilt) * math.sin(a), math.cos(tilt)])
        add_spike((0, 0, 0.02), tuple(d * (0.85 if k % 2 == 0 else 0.62)), 0.10, 0.012, 1.0, a + math.pi / 2)
    # side star (perpendicular burst)
    for k in range(8):
        a = TAU * k / 8
        d = np.array([math.cos(a), math.sin(a), 0.18])
        add_spike((0, 0, 0.0), tuple(d * (0.42 if k % 2 == 0 else 0.28)), 0.05, 0.008, 0.7, 0.0)
    # central cone
    n = 12
    base = len(V)
    for r, (z, rad) in enumerate(((0.0, 0.05), (0.35, 0.16), (0.7, 0.10))):
        for k in range(n + 1):
            a = TAU * k / n
            V.append((rad * math.cos(a), rad * math.sin(a), z))
            UV.append((k / n, z))
            C.append((1.0, 1.0, 1.0, 1))
    for r in range(2):
        for k in range(n):
            a_, b_ = base + r * (n + 1) + k, base + r * (n + 1) + k + 1
            F.append((a_, b_, b_ + n + 1, a_ + n + 1))
    return mesh_object("muzzle_flash", V, UV, C, F, None)


# ============================================================================ impact burst (+z = surface normal)
def impact():
    V, UV, C, F = [], [], [], []
    rng = np.random.default_rng(11)
    for k in range(12):
        ph = rng.uniform(0, TAU)
        th = math.radians(rng.uniform(15, 72))
        d = np.array([math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th)])
        L = rng.uniform(0.45, 1.0)
        pts, tip = diamond_prism((0, 0, 0), tuple(d * L), 0.035, 0.035, ph)
        base = len(V)
        for r in range(3):
            for q in range(4):
                V.append(pts[r * 4 + q])
                UV.append((q / 4, (0.0, 0.3, 0.75)[r]))
                C.append((L, 0, 0.5, 1))
        V.append(tuple(tip))
        UV.append((0.5, 1.0))
        C.append((L, 0, 0.5, 1))
        ti = len(V) - 1
        for r in range(2):
            for q in range(4):
                a_, b_ = base + r * 4 + q, base + r * 4 + (q + 1) % 4
                F.append((a_, b_, b_ + 4, a_ + 4))
        for q in range(4):
            F.append((base + 8 + q, base + 8 + (q + 1) % 4, ti))
    # flat shock ring (v = radius)
    n = 32
    base = len(V)
    for r, rad in enumerate((0.25, 0.55, 0.62)):
        for k in range(n + 1):
            a = TAU * k / n
            V.append((rad * math.cos(a), rad * math.sin(a), 0.02))
            UV.append((k / n, rad / 0.62))
            C.append((0.6, 1.0, 0.0, 1))
    for r in range(2):
        for k in range(n):
            a_, b_ = base + r * (n + 1) + k, base + r * (n + 1) + k + 1
            F.append((a_, b_, b_ + n + 1, a_ + n + 1))
    return mesh_object("impact_burst", V, UV, C, F, None)


def build_all():
    objs = []
    objs += kael_blade()
    objs += giva_claw()
    objs += bolt()
    objs.append(flash())
    objs.append(impact())
    return objs
