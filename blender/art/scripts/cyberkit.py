"""cyberkit: cyberpunk set dressing modelled in Blender for the Echoes of Aether render scenes.

Neon tubes, invented-glyph signage (a procedural fictional script, never real words or brands), backlit sign
boxes, vertical blade signs, holographic advert planes, light strips, catenary cables and a procedural
megacity backdrop (window-grid towers with neon edges and roof beacons).

Palette: magenta #ff2bd6, cyan #00e5ff, acid yellow #ffe14d (plus the game's Aether cyan/violet).
"""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

import artkit as A

MAGENTA = A.hexlin("#ff2bd6")
NCYAN = A.hexlin("#00e5ff")
YELLOW = A.hexlin("#ffe14d")
VIOLET = A.VIOLET
PALETTE = [MAGENTA, NCYAN, YELLOW, MAGENTA, NCYAN]

class _Cache(dict):
    """Material cache that forgets entries whose datablock was freed (scene reset between renders)."""

    def __contains__(self, key):
        if not dict.__contains__(self, key):
            return False
        try:
            dict.__getitem__(self, key).name
            return True
        except ReferenceError:
            del self[key]
            return False


_MAT = _Cache()


NEON_GAIN = 0.55  # global neon brightness (AgX desaturates very bright emitters; keep tubes in the saturated range)


def neon_mat(color, strength=12.0, name=None):
    strength = strength * NEON_GAIN
    key = ("neon", tuple(round(c, 3) for c in color), round(strength, 2))
    if key in _MAT:
        return _MAT[key]
    m = bpy.data.materials.new(name or "neon")
    T = A.NT(m)
    # white-hot core toward the tube axis (facing ratio), saturated colour at the rim
    lw = T.n("ShaderNodeLayerWeight", Blend=0.5)
    core = T.math("POWER", lw.outputs["Facing"], 3.0)
    col = T.mix(color, tuple(min(1.0, 0.18 + c * 0.82) for c in color), T.math("SUBTRACT", 1.0, core))
    em = T.n("ShaderNodeEmission")
    T.L(col, em.inputs["Color"])
    em.inputs["Strength"].default_value = strength
    T.L(em.outputs[0], T.out.inputs["Surface"])
    _MAT[key] = m
    return m


def dark_mat():
    if "dark" not in _MAT:
        _MAT["dark"] = A.principled("sign_backing", (0.012, 0.013, 0.016), rough=0.35, metal=0.6)
    return _MAT["dark"]


# ---------------------------------------------------------------------------------------------- glyph script
_GRID = [(x, y) for y in range(5) for x in range(3)]  # 3 x 5 stroke points per glyph cell


def glyph(seed):
    """Strokes of one invented glyph (unit cell 0..1 x 0..1.6): a vertical spine plus 1-3 hooks/bars/diagonals.
    The same seed always gives the same glyph, so signs read as a consistent fictional script."""
    rr = random.Random(seed * 7919 + 13)
    P = lambda i, j: (i * 0.5, j * 0.4)  # noqa: E731
    strokes = []
    kind = rr.randint(0, 5)
    sx = rr.choice([0, 1, 2])
    if kind in (0, 1, 2):
        j0, j1 = rr.choice([(0, 4), (0, 3), (1, 4)])
        strokes.append((P(sx, j0), P(sx, j1)))
    if kind in (1, 3, 4):
        j = rr.randint(0, 4)
        strokes.append((P(0, j), P(2, j)))
    if kind in (2, 4, 5):
        a, b = rr.choice([((0, 4), (2, 2)), ((0, 2), (2, 0)), ((0, 0), (2, 4)), ((2, 4), (0, 1)), ((1, 4), (2, 2))])
        strokes.append((P(*a), P(*b)))
    for _ in range(rr.randint(1, 2)):
        i, j = rr.randint(0, 2), rr.randint(0, 4)
        di, dj = rr.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1)])
        i2, j2 = max(0, min(2, i + di)), max(0, min(4, j + dj))
        if (i, j) != (i2, j2):
            strokes.append((P(i, j), P(i2, j2)))
    if kind == 3:
        strokes.append((P(1, 0), P(1, 4)))
    if kind == 5:
        strokes.append((P(0, 0), P(0, 4)))
        strokes.append((P(0, 4), P(2, 4)))
    return strokes


def glyph_line(n, seed, vertical=False, spacing=1.35):
    """Strokes for a run of n glyphs, laid out left->right or top->bottom (cell units)."""
    rr = random.Random(seed)
    out = []
    for k in range(n):
        g = glyph(rr.randint(0, 40))  # a 40-glyph alphabet
        for (a, b) in g:
            if vertical:
                off = (0.0, -k * 2.1)
            else:
                off = (k * spacing, 0.0)
            out.append(((a[0] + off[0], a[1] + off[1]), (b[0] + off[0], b[1] + off[1])))
    return out


# ---------------------------------------------------------------------------------------------- neon geometry
def tubes(segments, color, strength=12.0, radius=0.02, name="Neon", mat=None):
    """segments: list of (Vector a, Vector b) or polylines [p0, p1, ...] in world space -> one emissive curve."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 2
    cu.use_fill_caps = True
    for seg in segments:
        pts = list(seg)
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            sp.points[i].co = (p[0], p[1], p[2], 1)
    ob = bpy.data.objects.new(name, cu)
    cu.materials.append(mat or neon_mat(color, strength))
    A.link(ob)
    ob.visible_shadow = False
    return ob


def frame_axes(loc, yaw_deg, facing_tilt=0.0):
    """Local axes for a sign facing -Y rotated by yaw: right (u), up (v), normal (n)."""
    R = Matrix.Rotation(math.radians(yaw_deg), 3, "Z") @ Matrix.Rotation(math.radians(facing_tilt), 3, "X")
    return Vector(loc), R @ Vector((1, 0, 0)), R @ Vector((0, 0, 1)), R @ Vector((0, -1, 0))


def glyph_sign(loc, yaw, n=4, height=1.0, color=MAGENTA, strength=14.0, seed=1, vertical=False, backing=True,
               radius=None, frame=True, frame_color=None, name="GlyphSign"):
    """Neon glyph sign. loc = centre; faces -Y rotated by yaw. height = glyph height (m)."""
    o, u, v, nrm = frame_axes(loc, yaw)
    s = height / 1.6
    strokes = glyph_line(n, seed, vertical)
    xs = [p[0] for st in strokes for p in st]
    ys = [p[1] for st in strokes for p in st]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    w, h = (max(xs) - min(xs)) * s, (max(ys) - min(ys)) * s
    segs = []
    for a, b in strokes:
        pa = o + u * ((a[0] - cx) * s) + v * ((a[1] - cy) * s) + nrm * 0.06
        pb = o + u * ((b[0] - cx) * s) + v * ((b[1] - cy) * s) + nrm * 0.06
        segs.append((pa, pb))
    r = radius or max(0.012, height * 0.045)
    tubes(segs, color, strength, r, name=name)
    pad = height * 0.45
    if frame:
        fc = frame_color or color
        corners = [o + u * sx * (w / 2 + pad) + v * sy * (h / 2 + pad) + nrm * 0.05 for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        tubes([corners + [corners[0]]], fc, strength * 0.55, r * 0.6, name=name + "Frame")
    if backing:
        bw, bh = w + 2 * pad + 0.1, h + 2 * pad + 0.1
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=o)
        b = bpy.context.active_object
        b.scale = (bw, 0.08, bh)
        b.rotation_euler = (0, 0, math.radians(yaw))
        b.data.materials.append(dark_mat())
        b.name = name + "Back"
    return w + 2 * pad, h + 2 * pad


def blade_sign(loc, yaw, n=5, height=6.0, color=MAGENTA, accent=NCYAN, seed=3, strength=10.0, name="Blade"):
    """Vertical blade sign hung off a facade (glyph column, double-sided, edge strips)."""
    gh = height / (n * 1.35)
    o, u, v, nrm = frame_axes(loc, yaw)
    width = gh * 1.6
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=o)
    b = bpy.context.active_object
    b.scale = (width, 0.22, height)
    b.rotation_euler = (0, 0, math.radians(yaw))
    b.data.materials.append(dark_mat())
    b.name = name + "Box"
    for side in (1, -1):
        strokes = glyph_line(n, seed, vertical=True)
        xs = [p[0] for st in strokes for p in st]
        ys = [p[1] for st in strokes for p in st]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        sc = min((height * 0.86) / max(1e-3, (max(ys) - min(ys))), (width * 0.7) / max(1e-3, (max(xs) - min(xs))))
        segs = [(o + u * ((a[0] - cx) * sc * side) + v * ((a[1] - cy) * sc) + nrm * (0.13 * side),
                 o + u * ((b2[0] - cx) * sc * side) + v * ((b2[1] - cy) * sc) + nrm * (0.13 * side)) for a, b2 in strokes]
        tubes(segs, color, strength, max(0.02, sc * 0.05), name=name + "Glyph")
    for sx in (-1, 1):
        a = o + u * sx * (width / 2 + 0.02) - v * (height / 2)
        tubes([(a, a + v * height)], accent, strength * 0.8, 0.03, name=name + "Edge")
    return b


def light_box(loc, yaw, size=(4.0, 1.4), color=YELLOW, glyph_color=(0.02, 0.02, 0.02), n=4, seed=5, strength=4.0, name="LightBox"):
    """Backlit sign box: bright diffuser with dark glyph strokes."""
    o, u, v, nrm = frame_axes(loc, yaw)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=o)
    b = bpy.context.active_object
    b.scale = (size[0], 0.25, size[1])
    b.rotation_euler = (0, 0, math.radians(yaw))
    b.data.materials.append(A.emissive(name, color, strength))
    b.name = name
    strokes = glyph_line(n, seed)
    xs = [p[0] for st in strokes for p in st]
    ys = [p[1] for st in strokes for p in st]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    sc = min(size[0] * 0.8 / max(1e-3, max(xs) - min(xs)), size[1] * 0.7 / max(1e-3, max(ys) - min(ys)))
    segs = [(o + u * ((a[0] - cx) * sc) + v * ((a[1] - cy) * sc) - nrm * -0.13, o + u * ((b2[0] - cx) * sc) + v * ((b2[1] - cy) * sc) - nrm * -0.13)
            for a, b2 in strokes]
    tubes(segs, glyph_color, 0.0, sc * 0.07, name=name + "Ink", mat=dark_mat())
    return b


def strip(a, b, color, strength=10.0, radius=0.025, name="Strip"):
    return tubes([(Vector(a), Vector(b))], color, strength, radius, name=name)


def holo_mat(color, color2=None, strength=3.0, name="Holo", glyphs=True, seed=1):
    """Additive holographic advert: gradient, scanlines, flicker bands, faint glyph blocks, soft edge fade."""
    color2 = color2 or color
    m = bpy.data.materials.new(name)
    T = A.NT(m)
    tc = T.n("ShaderNodeTexCoord")
    sep = T.n("ShaderNodeSeparateXYZ")
    T.L(tc.outputs["UV"], sep.inputs[0])
    u, v = sep.outputs[0], sep.outputs[1]
    grad = T.mix(color, color2, v)
    scan = T.maprange(T.math("SINE", T.math("MULTIPLY", v, 420.0)), -1, 1, 0.55, 1.0)
    band = T.maprange(T.math("SINE", T.math("ADD", T.math("MULTIPLY", v, 9.0), 1.3)), 0.92, 1.0, 1.0, 1.8)
    edge = T.math("MULTIPLY", T.maprange(T.math("MINIMUM", u, T.math("SUBTRACT", 1.0, u)), 0.0, 0.08, 0.0, 1.0, smooth=True),
                  T.maprange(T.math("MINIMUM", v, T.math("SUBTRACT", 1.0, v)), 0.0, 0.08, 0.0, 1.0, smooth=True))
    k = T.math("MULTIPLY", T.math("MULTIPLY", scan, band), edge)
    if glyphs:
        br = T.n("ShaderNodeTexBrick", Scale=1.0)
        br.offset = 0.0
        br.inputs["Mortar Size"].default_value = 0.08
        br.inputs["Brick Width"].default_value = 0.22
        br.inputs["Row Height"].default_value = 0.06
        mp = T.n("ShaderNodeMapping")
        T.L(tc.outputs["UV"], mp.inputs["Vector"])
        mp.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
        T.L(mp.outputs[0], br.inputs["Vector"])
        cb = T.n("ShaderNodeSeparateColor")
        T.L(br.outputs["Color"], cb.inputs[0])
        blocks = T.math("MULTIPLY", T.math("GREATER_THAN", cb.outputs[0], 0.6), T.math("SUBTRACT", 1.0, br.outputs["Fac"]))
        k = T.math("MULTIPLY", k, T.math("ADD", 0.55, T.math("MULTIPLY", blocks, 0.9)))
    em = T.n("ShaderNodeEmission")
    T.L(grad, em.inputs["Color"])
    T.L(T.math("MULTIPLY", k, strength), em.inputs["Strength"])
    tr = T.n("ShaderNodeBsdfTransparent")
    add = T.n("ShaderNodeAddShader")
    T.L(tr.outputs[0], add.inputs[0])
    T.L(em.outputs[0], add.inputs[1])
    T.L(add.outputs[0], T.out.inputs["Surface"])
    return m


def holo_panel(loc, yaw, size, color, color2=None, strength=3.0, symbol=None, symbol_color=None, seed=1, tilt=0.0, name="HoloAd"):
    """Floating holographic advert plane + an abstract neon symbol on it (rings / triangle / chevrons / eye)."""
    o, u, v, nrm = frame_axes(loc, yaw, tilt)
    me = bpy.data.meshes.new(name)
    hw, hh = size[0] / 2, size[1] / 2
    corners = [o - u * hw - v * hh, o + u * hw - v * hh, o + u * hw + v * hh, o - u * hw + v * hh]
    me.from_pydata([tuple(c) for c in corners], [], [(0, 1, 2, 3)])
    uvl = me.uv_layers.new(name="UVMap")
    for i, uv in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        uvl.data[i].uv = uv
    ob = bpy.data.objects.new(name, me)
    me.materials.append(holo_mat(color, color2, strength, name, seed=seed))
    A.link(ob)
    ob.visible_shadow = False
    sc = symbol_color or color2 or color
    s = min(size) * 0.32
    c = o + nrm * 0.03 + v * (size[1] * 0.08)
    segs = []
    if symbol == "rings":
        for r in (1.0, 0.68, 0.36):
            segs.append([c + (u * math.cos(t) + v * math.sin(t)) * s * r for t in [i / 48 * math.tau for i in range(49)]])
    elif symbol == "triangle":
        pts = [c + (u * math.cos(t) + v * math.sin(t)) * s for t in (math.pi / 2, math.pi / 2 + math.tau / 3, math.pi / 2 + 2 * math.tau / 3)]
        segs.append(pts + [pts[0]])
        pts2 = [c + (p - c) * 0.5 for p in pts]
        segs.append(pts2 + [pts2[0]])
    elif symbol == "chevrons":
        for k in range(3):
            y0 = (k - 1) * 0.45 * s
            segs.append([c - u * s * 0.8 + v * (y0 - 0.3 * s), c + v * (y0 + 0.2 * s), c + u * s * 0.8 + v * (y0 - 0.3 * s)])
    elif symbol == "eye":
        segs.append([c + u * (s * math.cos(t)) + v * (s * 0.45 * math.sin(t)) for t in [i / 48 * math.tau for i in range(49)]])
        segs.append([c + (u * math.cos(t) + v * math.sin(t)) * s * 0.28 for t in [i / 32 * math.tau for i in range(33)]])
    elif symbol == "hex":
        pts = [c + (u * math.cos(t) + v * math.sin(t)) * s for t in [i / 6 * math.tau + math.pi / 6 for i in range(6)]]
        segs.append(pts + [pts[0]])
        segs.append([c - v * s * 0.5, c + v * s * 0.5])
    if segs:
        tubes(segs, sc, strength * 2.2, max(0.02, s * 0.025), name=name + "Sym")
    # glyph caption under the symbol
    gl = glyph_line(5, seed + 7)
    xs = [p[0] for st in gl for p in st]
    ys = [p[1] for st in gl for p in st]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    gs = size[0] * 0.6 / max(1e-3, max(xs) - min(xs))
    base = o - v * (size[1] * 0.33) + nrm * 0.03
    tubes([(base + u * ((a[0] - cx) * gs) + v * ((a[1] - cy) * gs * 0.6), base + u * ((b[0] - cx) * gs) + v * ((b[1] - cy) * gs * 0.6)) for a, b in gl],
          sc, strength * 1.6, max(0.015, gs * 0.04), name=name + "Cap")
    return ob


def cable(a, b, sag=1.5, radius=0.025, n=16, mat=None, name="Cable"):
    a, b = Vector(a), Vector(b)
    pts = []
    for i in range(n + 1):
        t = i / n
        p = a.lerp(b, t)
        p.z -= sag * 4 * t * (1 - t)
        pts.append(p)
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p.x, p.y, p.z, 1)
    ob = bpy.data.objects.new(name, cu)
    cu.materials.append(mat or dark_mat())
    A.link(ob)
    return ob


def lantern_string(a, b, color, n=12, sag=0.8, strength=8.0, name="Lanterns"):
    a, b = Vector(a), Vector(b)
    cable(a, b, sag, 0.012, name=name + "Wire")
    m = neon_mat(color, strength)
    for i in range(1, n):
        t = i / n
        p = a.lerp(b, t)
        p.z -= sag * 4 * t * (1 - t) + 0.12
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.07, location=p)
        o = bpy.context.active_object
        o.data.materials.append(m)
        o.visible_shadow = False


# ---------------------------------------------------------------------------------------------- megacity
def window_mat(seed=1, lit=0.22, warm=(1.0, 0.62, 0.32), cool=(0.4, 0.75, 1.0), base=(0.012, 0.014, 0.018), cell=(1.3, 1.0), strength=1.2):
    """Procedural tower facade (world-space window grid): dark cladding, randomly lit warm/cool windows."""
    key = ("win", seed, round(lit, 2))
    if key in _MAT:
        return _MAT[key]
    m = bpy.data.materials.new("Tower")
    T = A.NT(m)
    geo = T.n("ShaderNodeNewGeometry")
    sep = T.n("ShaderNodeSeparateXYZ")
    T.L(geo.outputs["Position"], sep.inputs[0])
    hor = T.math("ADD", sep.outputs[0], sep.outputs[1])
    vec = T.n("ShaderNodeCombineXYZ")
    T.L(T.math("DIVIDE", hor, cell[0]), vec.inputs[0])
    T.L(T.math("DIVIDE", sep.outputs[2], cell[1]), vec.inputs[1])
    br = T.n("ShaderNodeTexBrick", Scale=1.0)
    br.offset = 0.0
    br.squash = 1.0
    br.inputs["Mortar Size"].default_value = 0.22
    br.inputs["Brick Width"].default_value = 1.0
    br.inputs["Row Height"].default_value = 1.0
    T.L(vec.outputs[0], br.inputs["Vector"])
    # per-window random: white noise on the cell index
    fl = T.n("ShaderNodeVectorMath")
    fl.operation = "FLOOR"
    T.L(vec.outputs[0], fl.inputs[0])
    wn = T.n("ShaderNodeTexWhiteNoise")
    wn.noise_dimensions = "4D"
    T.L(fl.outputs[0], wn.inputs["Vector"])
    wn.inputs["W"].default_value = seed
    rnd = wn.outputs["Value"]
    on = T.math("LESS_THAN", rnd, lit)
    pane = T.math("SUBTRACT", 1.0, br.outputs["Fac"])
    hue = T.math("GREATER_THAN", T.math("FRACT", T.math("MULTIPLY", rnd, 7.31)), 0.6)
    wcol = T.mix(warm, cool, hue)
    em = T.n("ShaderNodeEmission")
    T.L(wcol, em.inputs["Color"])
    T.L(T.math("MULTIPLY", T.math("MULTIPLY", on, pane), T.math("ADD", strength * 0.4, T.math("MULTIPLY", rnd, strength * 2.0))), em.inputs["Strength"])
    b = T.n("ShaderNodeBsdfPrincipled", Roughness=0.25, Metallic=0.4)
    b.inputs["Base Color"].default_value = (*base, 1)
    T.L(T.mix((0.35, 0.3, 0.2), (0.6, 0.6, 0.6), pane), b.inputs["Roughness"])
    add = T.n("ShaderNodeAddShader")
    T.L(b.outputs[0], add.inputs[0])
    T.L(em.outputs[0], add.inputs[1])
    T.L(add.outputs[0], T.out.inputs["Surface"])
    _MAT[key] = m
    return m


def tower(x, y, w, d, h, seed=1, lit=0.22, neon=True, beacon=True, billboard=None, rr=None):
    rr = rr or random.Random(seed)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, h / 2))
    t = bpy.context.active_object
    t.scale = (w, d, h)
    t.name = "Tower"
    t.data.materials.append(window_mat(seed % 5, lit))
    # setbacks / crown
    if rr.random() < 0.6:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, h + h * 0.06))
        c = bpy.context.active_object
        c.scale = (w * 0.65, d * 0.65, h * 0.12)
        c.data.materials.append(window_mat((seed + 1) % 5, lit * 0.8))
    if neon:
        col = rr.choice(PALETTE)
        for sx, sy in ((-1, -1), (1, -1)) if rr.random() < 0.5 else ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            p = Vector((x + sx * w / 2, y + sy * d / 2, 0))
            strip(p + Vector((0, 0, h * rr.uniform(0.2, 0.5))), p + Vector((0, 0, h)), col, 8.0, 0.08)
        # LED columns on the faces and dim floor bands (structure + scale cues)
        for k in range(rr.randint(1, 3)):
            side = rr.choice(["s", "n", "e", "w"])
            f = rr.uniform(-0.4, 0.4)
            if side in "sn":
                px, py = x + f * w, y + (-1 if side == "s" else 1) * (d / 2 + 0.05)
            else:
                px, py = x + (-1 if side == "w" else 1) * (w / 2 + 0.05), y + f * d
            z0 = h * rr.uniform(0.05, 0.5)
            strip((px, py, z0), (px, py, z0 + h * rr.uniform(0.2, 0.45)), rr.choice(PALETTE), 7.0, 0.12)
        bandc = rr.choice(PALETTE)
        for z in range(int(h * 0.3), int(h), int(rr.uniform(18, 34))):
            if rr.random() < 0.45:
                corners = [Vector((x - w / 2 - 0.05, y - d / 2 - 0.05, z)), Vector((x + w / 2 + 0.05, y - d / 2 - 0.05, z)),
                           Vector((x + w / 2 + 0.05, y + d / 2 + 0.05, z)), Vector((x - w / 2 - 0.05, y + d / 2 + 0.05, z))]
                tubes([corners + [corners[0]]], bandc, 3.0, 0.06)
        if rr.random() < 0.6:
            z = h * rr.uniform(0.5, 0.95)
            col2 = rr.choice(PALETTE)
            corners = [Vector((x - w / 2, y - d / 2, z)), Vector((x + w / 2, y - d / 2, z)), Vector((x + w / 2, y + d / 2, z)), Vector((x - w / 2, y + d / 2, z))]
            tubes([corners + [corners[0]]], col2, 7.0, 0.07)
    if beacon:
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.35, location=(x, y, h * (1.12 if rr.random() < 0.6 else 1.0) + 0.6))
        bpy.context.active_object.data.materials.append(neon_mat((1.0, 0.1, 0.06), 30.0))
    if billboard:
        side, col, col2, sym = billboard
        bw, bh = min(w, d) * 0.85, min(w, d) * 0.55
        n = {"s": Vector((0, -1, 0)), "n": Vector((0, 1, 0)), "e": Vector((1, 0, 0)), "w": Vector((-1, 0, 0))}[side]
        off = d / 2 if side in "sn" else w / 2
        loc = Vector((x, y, h * rr.uniform(0.55, 0.8))) + n * (off + 0.4)
        holo_panel(loc, A.yaw_to((0, 0), n), (bw, bh), col, col2, 3.0, symbol=sym, seed=seed)
    return t


def megacity(center, rmin, rmax, count, seed=1, hmin=60, hmax=220, lit=0.2, billboards=0.35, arc=None, avoid=None):
    """Ring of skyscrapers around center (optionally limited to an angular arc in degrees, 0 = +Y, clockwise)."""
    rr = random.Random(seed)
    made = []
    for i in range(count):
        if arc:
            a = math.radians(rr.uniform(*arc))
        else:
            a = rr.uniform(0, math.tau)
        r = rr.uniform(rmin, rmax)
        x, y = center[0] + math.sin(a) * r, center[1] + math.cos(a) * r
        if avoid and avoid(x, y):
            continue
        w, d = rr.uniform(14, 34), rr.uniform(14, 34)
        h = rr.uniform(hmin, hmax)
        bb = None
        if rr.random() < billboards:
            to_c = Vector((center[0] - x, center[1] - y))
            side = ("e" if to_c.x > 0 else "w") if abs(to_c.x) > abs(to_c.y) else ("n" if to_c.y > 0 else "s")
            bb = (side, rr.choice(PALETTE), rr.choice(PALETTE), rr.choice(["rings", "triangle", "chevrons", "eye", "hex", None]))
        made.append(tower(x, y, w, d, h, seed=seed * 100 + i, lit=lit, billboard=bb, rr=rr))
    return made


def air_traffic(center, size, count=40, seed=9, z=(40, 160)):
    """Distant flying-vehicle lights: short bright streaks (motion trails) high above the streets."""
    rr = random.Random(seed)
    segs_w, segs_r = [], []
    for i in range(count):
        p = Vector((center[0] + rr.uniform(-size[0] / 2, size[0] / 2), center[1] + rr.uniform(-size[1] / 2, size[1] / 2), rr.uniform(*z)))
        d = Vector((rr.uniform(-1, 1), rr.uniform(-1, 1), 0)).normalized() * rr.uniform(2, 7)
        (segs_w if rr.random() < 0.6 else segs_r).append((p, p + d))
    tubes(segs_w, (1.0, 0.92, 0.8), 25.0, 0.12, name="TrafficW")
    tubes(segs_r, (1.0, 0.12, 0.08), 18.0, 0.1, name="TrafficR")


def holo_figure(cid, loc, yaw, scale, color, color2, pose=("talk", 30), strength=1.6):
    """Giant holographic advert figure: one of the game's characters re-shaded as a scanline hologram."""
    ch = A.load_character(cid, (0, 0, 0), 0, pose=pose, detail=False, ground=False, look=False)
    m = bpy.data.materials.new("HoloFigure")
    T = A.NT(m)
    geo = T.n("ShaderNodeNewGeometry")
    sep = T.n("ShaderNodeSeparateXYZ")
    T.L(geo.outputs["Position"], sep.inputs[0])
    lw = T.n("ShaderNodeLayerWeight", Blend=0.4)
    fres = T.math("POWER", lw.outputs["Facing"], 1.5)
    scan = T.maprange(T.math("SINE", T.math("MULTIPLY", sep.outputs[2], 21.0)), -1, 1, 0.45, 1.0)
    grad = T.maprange(sep.outputs[2], loc[2], loc[2] + 1.8 * scale, 0.0, 1.0)
    col = T.mix(color, color2, grad)
    em = T.n("ShaderNodeEmission")
    T.L(col, em.inputs["Color"])
    T.L(T.math("MULTIPLY", T.math("MULTIPLY", T.math("ADD", 0.25, fres), scan), strength), em.inputs["Strength"])
    tr = T.n("ShaderNodeBsdfTransparent")
    add = T.n("ShaderNodeAddShader")
    T.L(tr.outputs[0], add.inputs[0])
    T.L(em.outputs[0], add.inputs[1])
    T.L(add.outputs[0], T.out.inputs["Surface"])
    for o in ch.objs:
        if o.type == "MESH":
            for i in range(len(o.data.materials)):
                o.data.materials[i] = m
            o.visible_shadow = False
            o.visible_diffuse = False
    ch.rig.scale = (scale, scale, scale)
    ch.place(loc, yaw)
    return ch
