"""Inventory item art: 256 x 256 RGBA PNG per item `icon` id in src/data/items.json (transparent background, soft
contact shadow via a Cycles shadow catcher). Every item is modelled here in Python (bmesh/primitives + bevels),
lit by the same studio rig and shot from the same 3/4 hero angle, with the item's UI accent colour (from the
prototype's src/ui/Icons.ts / powerups.json) as its emissive accent.

  Blender -b --factory-startup --python items.py -- [icon ids...] [--size 256] [--preview]
"""
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Euler, Matrix, Vector  # noqa: E402

import artkit as A  # noqa: E402
import cyberkit as C  # noqa: E402

OUT = os.path.join(A.RES_ART, "Items")
_REMAP = {"#5fd4f0": "#00e5ff", "#62d4ff": "#00e5ff", "#ffb45e": "#ffe14d", "#ffc46a": "#ffe14d", "#9a7bff": "#ff2bd6",
          "#c39bff": "#d65bff", "#7fe8c8": "#3dffd8", "#6fa8ff": "#00e5ff", "#a68bff": "#ff2bd6", "#a77bff": "#ff2bd6"}


def H(h):
    """Accent hex -> linear, remapped onto the cyberpunk neon palette (magenta / cyan / acid yellow)."""
    return A.hexlin(_REMAP.get(h.lower(), h) if isinstance(h, str) else h)

# ------------------------------------------------------------------------------------------------ materials
_M = {}


def metal(name="gunmetal", col="#2a2e34", rough=0.36, metallic=1.0, scratch=True):
    key = ("m", name)
    if key in _M:
        return _M[key]
    m = bpy.data.materials.new(name)
    T = A.NT(m)
    b = T.n("ShaderNodeBsdfPrincipled", Roughness=rough, Metallic=metallic)
    b.inputs["Base Color"].default_value = (*H(col), 1)
    if scratch:
        tc = T.n("ShaderNodeTexCoord")
        nz = T.n("ShaderNodeTexNoise", Scale=60.0, Detail=8.0, Roughness=0.7)
        T.L(tc.outputs["Object"], nz.inputs["Vector"])
        T.L(T.maprange(nz.outputs["Fac"], 0.3, 0.7, rough * 0.7, rough * 1.4), b.inputs["Roughness"])
        bump = T.n("ShaderNodeBump", Strength=0.08, Distance=0.002)
        T.L(nz.outputs["Fac"], bump.inputs["Height"])
        T.L(bump.outputs["Normal"], b.inputs["Normal"])
    T.L(b.outputs[0], T.out.inputs["Surface"])
    _M[key] = m
    return m


def paint(name, col, rough=0.45):
    key = ("p", name)
    if key in _M:
        return _M[key]
    m = bpy.data.materials.new(name)
    T = A.NT(m)
    b = T.n("ShaderNodeBsdfPrincipled", Roughness=rough, Metallic=0.0)
    b.inputs["Base Color"].default_value = (*H(col), 1)
    b.inputs["Coat Weight"].default_value = 0.25
    b.inputs["Coat Roughness"].default_value = 0.2
    T.L(b.outputs[0], T.out.inputs["Surface"])
    _M[key] = m
    return m


def emit(name, col, strength=6.0):
    key = ("e", name)
    if key in _M:
        return _M[key]
    c = H(col) if isinstance(col, str) else col
    m = A.emissive(name, c, strength, base=[x * 0.3 for x in c])
    _M[key] = m
    return m


def crystal(name, col, glow=2.5):
    """Aether crystal: clear refractive body tinted by the accent colour, glowing from inside (fresnel-rimmed)."""
    key = ("c", name)
    if key in _M:
        return _M[key]
    c = H(col) if isinstance(col, str) else col
    m = bpy.data.materials.new(name)
    T = A.NT(m)
    b = T.n("ShaderNodeBsdfPrincipled", Roughness=0.06, IOR=1.55)
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Base Color"].default_value = (*[0.08 + 0.92 * x for x in c], 1)
    lw = T.n("ShaderNodeLayerWeight", Blend=0.35)
    em = T.math("ADD", 0.5, T.math("MULTIPLY", lw.outputs["Facing"], 1.6))
    b.inputs["Emission Color"].default_value = (*c, 1)
    T.L(T.math("MULTIPLY", em, glow), b.inputs["Emission Strength"])
    T.L(b.outputs[0], T.out.inputs["Surface"])
    _M[key] = m
    return m


def rubber():
    return metal("rubber", "#141518", rough=0.75, metallic=0.0, scratch=False)


# ------------------------------------------------------------------------------------------------ geometry
def finish(ob, bevel=0.0, seg=2, smooth=30.0):
    if bevel:
        md = ob.modifiers.new("bevel", "BEVEL")
        md.width = bevel
        md.segments = seg
        md.limit_method = "ANGLE"
        md.angle_limit = math.radians(30)
        md.harden_normals = False
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(smooth))
    except Exception:
        bpy.ops.object.shade_smooth()
    ob.select_set(False)
    return ob


def _mesh_from_bm(bm, name, mat, loc=(0, 0, 0), rot=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    me.materials.append(mat)
    A.link(ob)
    return ob


def box(size, loc, mat, rot=(0, 0, 0), bevel=0.01, name="box"):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    return finish(_mesh_from_bm(bm, name, mat, loc, rot), bevel)


def cyl(r, h, loc, mat, rot=(0, 0, 0), n=48, r2=None, bevel=0.006, name="cyl", cap=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=cap, segments=n, radius1=r, radius2=r if r2 is None else r2, depth=h)
    return finish(_mesh_from_bm(bm, name, mat, loc, rot), bevel)


def torus(R, r, loc, mat, rot=(0, 0, 0), arc=360, name="torus", seg=96):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=seg, minor_segments=16,
                                     location=loc, rotation=[math.radians(a) for a in rot])
    ob = bpy.context.active_object
    ob.name = name
    if arc < 360:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        kill = [v for v in bm.verts if (math.degrees(math.atan2(v.co.y, v.co.x)) % 360) > arc]
        bmesh.ops.delete(bm, geom=kill, context="VERTS")
        bm.to_mesh(ob.data)
        bm.free()
    ob.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return ob


def ico(r, loc, mat, sub=4, name="ico", smooth=True):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=r, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.data.materials.append(mat)
    if smooth:
        bpy.ops.object.shade_smooth()
    return ob


def prism(points2d, depth, loc, mat, rot=(0, 0, 0), bevel=0.004, name="prism"):
    """Extrude a 2D outline (in XZ plane) along Y."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, -depth / 2, z)) for x, z in points2d]
    f = bm.faces.new(vs)
    r = bmesh.ops.extrude_face_region(bm, geom=[f])
    nv = [e for e in r["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, depth, 0), verts=nv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish(_mesh_from_bm(bm, name, mat, loc, rot), bevel)


def shard(height, radius, loc, mat, rot=(0, 0, 0), sides=6, seed=1, tip=0.35, name="shard", broken=False):
    """Crystal: n-sided prism with a pointed top (and pointed or broken bottom), slightly irregular."""
    rr = random.Random(seed)
    bm = bmesh.new()
    ring_lo, ring_hi = [], []
    for i in range(sides):
        a = i / sides * math.tau + rr.uniform(-0.12, 0.12)
        rad = radius * rr.uniform(0.85, 1.12)
        ring_lo.append(bm.verts.new((math.cos(a) * rad, math.sin(a) * rad, height * 0.12)))
        ring_hi.append(bm.verts.new((math.cos(a) * rad * 0.92, math.sin(a) * rad * 0.92, height * (1 - tip))))
    top = bm.verts.new((rr.uniform(-0.1, 0.1) * radius, rr.uniform(-0.1, 0.1) * radius, height))
    bot = bm.verts.new((0, 0, 0 if not broken else height * 0.08))
    for i in range(sides):
        j = (i + 1) % sides
        bm.faces.new((ring_lo[i], ring_lo[j], ring_hi[j], ring_hi[i]))
        bm.faces.new((ring_hi[i], ring_hi[j], top))
        bm.faces.new((ring_lo[j], ring_lo[i], bot))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _mesh_from_bm(bm, name, mat, loc, rot)
    for p in ob.data.polygons:
        p.use_smooth = False
    return ob


def glyph_decal(n, height, loc, mat, seed=1, yaw=0.0):
    """Printed invented-glyph label (no real words): thin dark strokes on the item surface, facing -Y."""
    strokes = C.glyph_line(n, seed)
    xs = [p[0] for st in strokes for p in st]
    ys = [p[1] for st in strokes for p in st]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    s = height / 1.6
    o = Vector(loc)
    segs = [(o + Vector(((a[0] - cx) * s, 0, (a[1] - cy) * s)), o + Vector(((b[0] - cx) * s, 0, (b[1] - cy) * s))) for a, b in strokes]
    return C.tubes(segs, (0, 0, 0), 0.0, height * 0.06, name="decal", mat=mat)


def text_mesh(txt, size, loc, mat, rot=(90, 0, 0), extrude=0.002, font="Rajdhani/Rajdhani-Bold.ttf"):
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = txt
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = extrude
    cu.font = bpy.data.fonts.load(os.path.join(A.FONTS, font), check_existing=True)
    ob = bpy.data.objects.new("txt", cu)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    cu.materials.append(mat)
    A.link(ob)
    return ob


BOLT2D = [(0.02, 0.5), (-0.16, 0.02), (-0.02, 0.02), (-0.08, -0.5), (0.16, 0.08), (0.02, 0.08), (0.12, 0.5)]


# ------------------------------------------------------------------------------------------------ items
def it_fragment():
    c = "#5fd4f0"
    m = crystal("frag", c, 0.8)
    shard(1.0, 0.2, (0, 0, 0.02), m, rot=(0, 8, 0), seed=3, tip=0.32)
    shard(0.55, 0.12, (0.17, 0.06, 0.0), m, rot=(0, 28, 20), seed=5, tip=0.4)
    shard(0.42, 0.1, (-0.15, -0.05, 0.0), m, rot=(-6, -30, 0), seed=7, tip=0.45)
    ico(0.05, (0, 0, 0.42), emit("frag_core", c, 10.0), sub=2)
    return c


def it_core():
    """Dense, stable Aether core: a faceted glowing crystal ball held by three claws on a dark metal cradle."""
    c = "#ffb45e"
    acc = H(c)
    ball = ico(0.24, (0, 0, 0.56), crystal("core_crystal", c, 0.9), sub=1, smooth=False)
    ico(0.11, (0, 0, 0.56), emit("core_heart", (1.0, 0.7, 0.2), 7.0), sub=2)
    gm = metal("graphite", "#1b1d21", 0.38)
    cyl(0.26, 0.08, (0, 0, 0.04), gm, n=6, bevel=0.015)
    cyl(0.18, 0.16, (0, 0, 0.16), gm, n=6, bevel=0.012)
    torus(0.19, 0.012, (0, 0, 0.25), emit("core_ring", c, 6.0))
    for i in range(3):
        a = math.radians(i * 120 + 30)
        d = Vector((math.cos(a), math.sin(a), 0))
        # claw: two segments rising from the cradle and curling over the ball
        p0 = Vector((0, 0, 0.22)) + d * 0.14
        p1 = Vector((0, 0, 0.48)) + d * 0.29
        p2 = Vector((0, 0, 0.74)) + d * 0.2
        for a0, a1, r in ((p0, p1, 0.035), (p1, p2, 0.028)):
            v = a1 - a0
            ob = cyl(r, v.length, tuple((a0 + a1) / 2), gm, n=12, bevel=0.004)
            ob.rotation_euler = v.to_track_quat("Z", "Y").to_euler()
            ob.location = (a0 + a1) / 2
        box((0.06, 0.02, 0.06), tuple(p1 + d * 0.025), emit("core_claw_led", c, 8.0), rot=(0, 0, math.degrees(a) + 90), bevel=0.004)
    return c


def it_pu_shard():
    c = "#62d4ff"
    m = crystal("pushard", c, 0.9)
    shard(1.0, 0.16, (0, 0, 0.0), m, rot=(0, 0, 0), seed=11, sides=4, tip=0.5)
    shard(0.5, 0.08, (-0.2, 0, 0.0), m, rot=(0, -24, 0), seed=12, sides=4, tip=0.5)
    shard(0.5, 0.08, (0.2, 0, 0.0), m, rot=(0, 24, 0), seed=13, sides=4, tip=0.5)
    ico(0.045, (0, 0, 0.45), emit("pushard_core", c, 10.0), sub=2)
    return c


def it_pu_phase():
    c = "#9a7bff"
    ico(0.2, (0, 0, 0.5), A.aether_material("phase_ball", color=H(c), color2=A.CYAN, strength=6.0, core=True, rim=1.5, scale=5.0))
    gm = metal("graphite", "#1b1d21", 0.38)
    torus(0.42, 0.03, (0, 0, 0.5), gm, rot=(90, 0, 30))
    torus(0.42, 0.03, (0, 0, 0.5), gm, rot=(90, 0, 120))
    torus(0.42, 0.011, (0, 0, 0.5), emit("phase_ring", c, 9.0), rot=(90, 0, 30))
    torus(0.42, 0.011, (0, 0, 0.5), emit("phase_ring", c, 9.0), rot=(90, 0, 120))
    torus(0.31, 0.02, (0, 0, 0.5), gm, rot=(0, 0, 0))
    return c


def it_pu_overcharge():
    c = "#ffb45e"
    gm = metal("graphite", "#1b1d21", 0.38)
    cyl(0.22, 0.62, (0, 0, 0.36), paint("oc_body", "#1d2024", 0.4), n=64, bevel=0.02)
    for z in (0.08, 0.64):
        cyl(0.235, 0.07, (0, 0, z), gm, n=64, bevel=0.012)
    cyl(0.08, 0.08, (0, 0, 0.72), metal("brass", "#b58a4a", 0.3), n=32)
    # glowing window with a bolt
    prism([(x * 0.5, z * 0.5) for x, z in BOLT2D], 0.02, (0, -0.221, 0.36), emit("oc_bolt", c, 14.0), rot=(0, 0, 0))
    for z in (0.22, 0.5):
        cyl(0.226, 0.012, (0, 0, z), emit("oc_band", c, 5.0), n=64, bevel=0.0)
    return c


def it_pu_shield():
    c = "#7fe8c8"
    pts = []
    for i in range(25):
        t = i / 24
        a = math.pi * t
        pts.append((math.cos(a) * 0.36, -0.1 - math.sin(a) * 0.42))
    outline = [(-0.36, 0.42), (0.0, 0.5), (0.36, 0.42)] + [(x, z) for x, z in pts]
    outline = [(-0.36, 0.42), (0.0, 0.5), (0.36, 0.42), (0.36, -0.1)] + [(math.cos(math.pi * i / 24) * 0.36, -0.1 - math.sin(math.pi * i / 24) * 0.42) for i in range(1, 24)] + [(-0.36, -0.1)]
    prism([(x, z + 0.55) for x, z in outline], 0.09, (0, 0, 0), metal("shieldframe", "#2a2d31", 0.35), bevel=0.012)
    inner = [(x * 0.8, z * 0.8 + 0.55 + 0.01) for x, z in outline]
    prism(inner, 0.1, (0, -0.012, 0), crystal("shield_glass", c, 1.4), bevel=0.006)
    # broken corner (fragment) + hex lines
    prism([(-0.06, 0.12), (0.02, -0.06), (0.1, 0.02)], 0.1, (0.3, -0.02, 0.2), metal("shieldframe", "#2a2d31", 0.35))
    prism([(x * 0.25, z * 0.25) for x, z in [(-0.5, -0.1), (-0.15, -0.5), (0.4, 0.4), (0.25, 0.55), (-0.15, -0.1), (-0.35, 0.05)]], 0.02,
          (0, -0.07, 0.55), emit("shield_check", c, 10.0))
    return c


def it_pu_echo():
    c = "#c39bff"
    m = crystal("echo", c, 0.9)
    shard(0.8, 0.22, (0, 0, 0.1), m, sides=4, tip=0.5, seed=21)
    bpy.context.active_object
    # bottom point
    shard(0.32, 0.22, (0, 0, 0.42), m, rot=(180, 0, 45 / 4), sides=4, tip=1.0, seed=21)
    ico(0.045, (0, 0, 0.45), emit("echo_core", c, 9.0), sub=2)
    dash = emit("echo_ring", c, 6.0)
    for i in range(14):
        a0 = i * (360 / 14)
        torus(0.5, 0.012, (0, 0, 0.45), dash, rot=(80, 0, a0), arc=14, seg=192)
    return c


def it_q_part():
    c = "#ffc46a"
    gm = metal("steel", "#7c8088", 0.28)
    dk = metal("graphite", "#1b1d21", 0.38)
    # motor can + gearbox + rod (servo actuator), lying on its side
    cyl(0.18, 0.42, (-0.12, 0, 0.2), paint("servo_y", "#c99a2e", 0.45), rot=(0, 90, 0), n=48, bevel=0.015)
    cyl(0.185, 0.04, (-0.34, 0, 0.2), dk, rot=(0, 90, 0), n=48)
    box((0.22, 0.3, 0.3), (0.18, 0, 0.2), dk, bevel=0.02)
    cyl(0.07, 0.42, (0.48, 0, 0.2), gm, rot=(0, 90, 0), n=32)
    cyl(0.11, 0.06, (0.7, 0, 0.2), dk, rot=(0, 90, 0), n=32)
    # gear on top
    g = cyl(0.13, 0.05, (0.18, 0, 0.38), gm, n=48, bevel=0.004)
    for i in range(14):
        a = i / 14 * math.tau
        box((0.04, 0.035, 0.05), (0.18 + math.cos(a) * 0.145, math.sin(a) * 0.145, 0.38), gm, rot=(0, 0, math.degrees(a)), bevel=0.003)
    cyl(0.03, 0.08, (0.18, 0, 0.42), dk, n=16)
    box((0.08, 0.012, 0.03), (-0.12, -0.182, 0.27), emit("servo_led", c, 8.0), bevel=0.0)
    for x in (-0.25, -0.12, 0.01):
        cyl(0.182, 0.008, (x, 0, 0.2), dk, rot=(0, 90, 0), n=48, bevel=0)
    return c


def it_q_cell():
    c = "#ffc46a"
    dk = metal("graphite", "#1b1d21", 0.38)
    cyl(0.2, 0.7, (0, 0, 0.37), paint("cell_body", "#30353b", 0.4), n=64, bevel=0.02)
    for z in (0.06, 0.7):
        cyl(0.215, 0.08, (0, 0, z), dk, n=64, bevel=0.015)
    cyl(0.09, 0.07, (0, 0, 0.77), metal("steel", "#7c8088", 0.28), n=32)
    torus(0.12, 0.02, (0, 0, 0.86), dk, rot=(90, 0, 0), arc=180)
    # hazard band + charge window
    cyl(0.203, 0.1, (0, 0, 0.18), paint("hazard", "#d0a020", 0.5), n=64, bevel=0)
    box((0.1, 0.03, 0.34), (0, -0.19, 0.44), emit("cell_glow", c, 9.0), bevel=0.01)
    prism([(x * 0.3, z * 0.3) for x, z in BOLT2D], 0.01, (0, -0.212, 0.44), paint("bolt_dark", "#1a1c20"))
    return c


def it_q_chip():
    c = "#ffc46a"
    box((0.8, 0.6, 0.05), (0, 0, 0.05), paint("pcb", "#1f4a3a", 0.45), bevel=0.008)
    box((0.3, 0.3, 0.06), (0.05, 0, 0.1), paint("chipbody", "#141518", 0.35), bevel=0.01)
    box((0.12, 0.12, 0.012), (0.05, 0, 0.135), emit("chip_core", c, 8.0), bevel=0.003)
    gold = metal("gold", "#c7a24a", 0.25)
    for i in range(7):
        for side in (-1, 1):
            box((0.02, 0.06, 0.012), (0.05 - 0.12 + i * 0.04, side * 0.18, 0.08), gold, bevel=0)
            box((0.06, 0.02, 0.012), (0.05 + side * 0.18, -0.12 + i * 0.04, 0.08), gold, bevel=0)
    for x, y in [(-0.3, 0.2), (-0.3, -0.15), (0.32, 0.22), (-0.2, 0.0)]:
        box((0.08, 0.05, 0.04), (x, y, 0.09), paint("cap", "#2a2d31", 0.4), bevel=0.006)
    cyl(0.04, 0.08, (0.3, -0.2, 0.11), metal("steel", "#7c8088", 0.28), n=24)
    box((0.1, 0.5, 0.06), (-0.38, 0, 0.06), gold, bevel=0.004)  # edge connector
    for i in range(3):
        box((0.03, 0.012, 0.01), (0.3, 0.08 + i * 0.05, 0.08), emit("chip_led", c, 6.0), bevel=0)
    return c


def it_q_tape():
    c = "#ffc46a"
    body = paint("tape_body", "#24272c", 0.4)
    box((0.86, 0.12, 0.54), (0, 0, 0.29), body, bevel=0.02)
    box((0.62, 0.124, 0.22), (0, 0, 0.36), paint("tape_label", "#c9b58a", 0.6), bevel=0.004)
    box((0.42, 0.13, 0.12), (0, 0, 0.36), paint("tape_window", "#0b0c0e", 0.15), bevel=0.004)
    for x in (-0.13, 0.13):
        cyl(0.05, 0.135, (x, 0, 0.36), metal("steel", "#7c8088", 0.28), rot=(90, 0, 0), n=24)
        cyl(0.075, 0.13, (x, 0, 0.36), paint("tape_reel", "#3a2c22", 0.5), rot=(90, 0, 0), n=32)
    box((0.5, 0.13, 0.1), (0, 0, 0.09), paint("tape_bottom", "#2e3238", 0.45), bevel=0.01)
    glyph_decal(5, 0.06, (0, -0.066, 0.47), paint("ink", "#3a2a1a", 0.6), seed=71)
    box((0.2, 0.012, 0.02), (0.2, -0.062, 0.18), emit("tape_tab", c, 5.0), bevel=0)
    return c


def it_q_key():
    c = "#ffc46a"
    body = paint("card", "#d9dde0", 0.35)
    box((0.86, 0.04, 0.54), (0, 0, 0.3), body, bevel=0.03, name="card")
    box((0.86, 0.042, 0.12), (0, 0, 0.5), paint("card_band", "#2a2d31", 0.4), bevel=0.0)
    box((0.86, 0.043, 0.02), (0, 0, 0.43), emit("card_strip", A.CYAN, 6.0), bevel=0)
    box((0.16, 0.044, 0.13), (-0.24, 0, 0.28), metal("gold", "#c7a24a", 0.25), bevel=0.006)
    for i in range(3):
        box((0.12, 0.045, 0.006), (-0.24, 0, 0.24 + i * 0.035), metal("goldline", "#8a6a2a", 0.3), bevel=0)
    glyph_decal(4, 0.08, (0.12, -0.025, 0.31), paint("ink2", "#1d2228", 0.6), seed=72)
    glyph_decal(6, 0.045, (0.12, -0.025, 0.2), paint("ink2", "#1d2228", 0.6), seed=73)
    cyl(0.04, 0.05, (0.36, 0, 0.5), paint("hole", "#0d0e10", 0.4), rot=(90, 0, 0), n=24)
    box((0.04, 0.044, 0.04), (0.33, 0, 0.12), emit("card_led", c, 10.0), bevel=0.004)
    return c


def module_base(c, accent_strength=8.0):
    """Shared upgrade-module housing: hexagonal graphite casing with a glowing accent ring."""
    dk = metal("graphite", "#1b1d21", 0.38)
    hexa = [(math.cos(i / 6 * math.tau + math.pi / 6) * 0.48, math.sin(i / 6 * math.tau + math.pi / 6) * 0.48) for i in range(6)]
    prism([(x, z + 0.5) for x, z in hexa], 0.16, (0, 0.04, 0), dk, bevel=0.02)
    inner = [(x * 0.8, z * 0.8) for x, z in hexa]
    prism([(x, z + 0.5) for x, z in inner], 0.17, (0, 0.034, 0), metal("steel2", "#565b63", 0.3), bevel=0.01)
    torus(0.3, 0.014, (0, -0.06, 0.5), emit("mod_ring_" + c, c, accent_strength), rot=(90, 0, 0))
    for i in range(6):
        a = i / 6 * math.tau
        cyl(0.025, 0.04, (math.cos(a) * 0.4, -0.05, 0.5 + math.sin(a) * 0.4), metal("steel", "#7c8088", 0.28), rot=(90, 0, 0), n=12)
    return dk


def it_up_shield():
    c = "#7fe8c8"
    module_base(c)
    for i, (dx, dz) in enumerate([(0, 0), (0.105, 0.06), (-0.105, 0.06), (0, 0.12), (0.105, -0.06), (-0.105, -0.06), (0, -0.12)]):
        hexa = [(math.cos(k / 6 * math.tau) * 0.055, math.sin(k / 6 * math.tau) * 0.055) for k in range(6)]
        prism([(x + dx, z + dz + 0.5) for x, z in hexa], 0.03, (0, -0.07, 0), emit("shield_hex", c, 5.0 if i else 10.0), bevel=0.003)
    return c


def it_up_echo():
    c = "#c39bff"
    module_base(c)
    # eye-shaped lens (Echo Sight) + antenna
    eye = [(math.cos(t) * 0.24, math.sin(t) * 0.11 * (1 if math.sin(t) >= 0 else 1)) for t in [i / 32 * math.tau for i in range(32)]]
    prism([(x, z + 0.5) for x, z in eye], 0.03, (0, -0.07, 0), paint("eye_dark", "#0b0c10", 0.2), bevel=0.004)
    cyl(0.07, 0.05, (0, -0.09, 0.5), crystal("echo_lens", c, 3.0), rot=(90, 0, 0), n=32)
    ico(0.03, (0, -0.12, 0.5), emit("echo_pupil", c, 30.0), sub=2)
    cyl(0.012, 0.32, (0.3, 0.04, 0.95), metal("steel", "#7c8088", 0.28), n=12)
    ico(0.025, (0.3, 0.04, 1.11), emit("echo_tip", c, 20.0), sub=2)
    return c


def it_up_core():
    c = "#ffb45e"
    module_base(c, 6.0)
    ico(0.13, (0, -0.06, 0.5), A.aether_material("upcore", color=(1.0, 0.62, 0.12), color2=(1.0, 0.8, 0.3), strength=2.6, core=True, rim=1.0), sub=4)
    dash = emit("upcore_dash", c, 7.0)
    for i in range(10):
        torus(0.21, 0.008, (0, -0.07, 0.5), dash, rot=(90, 0, i * 36), arc=20, seg=128)
    return c


def it_up_resonant():
    c = "#ffb45e"
    module_base(c, 5.0)
    m = crystal("res_crystal", "#a77bff", 2.8)
    shard(0.36, 0.1, (0, -0.08, 0.32), m, sides=6, seed=31, tip=0.4)
    for z in (0.44, 0.56):
        torus(0.16, 0.01, (0, -0.08, z), emit("res_ring", c, 8.0), rot=(0, 0, 0))
    return c


def it_lore_rec():
    c = "#6fa8ff"
    body = paint("rec_body", "#2b3036", 0.4)
    box((0.36, 0.14, 0.8), (0, 0, 0.42), body, bevel=0.04)
    box((0.3, 0.145, 0.24), (0, 0, 0.62), paint("grille", "#15171a", 0.6), bevel=0.01)
    for i in range(6):
        box((0.24, 0.15, 0.012), (0, 0, 0.53 + i * 0.035), metal("steel", "#7c8088", 0.28), bevel=0)
    box((0.22, 0.146, 0.1), (0, 0, 0.36), paint("rec_screen", "#0a1420", 0.15), bevel=0.006)
    for i, w in enumerate((0.14, 0.09, 0.17, 0.06, 0.12)):
        box((0.012, 0.15, w * 0.45), (-0.08 + i * 0.04, 0, 0.36), emit("rec_wave", c, 9.0), bevel=0)
    for i, x in enumerate((-0.09, 0.0, 0.09)):
        cyl(0.03, 0.15, (x, 0, 0.2), paint("btn", "#3f454d" if i != 1 else "#8a2a22", 0.4), rot=(90, 0, 0), n=24)
    box((0.04, 0.147, 0.02), (0.12, 0, 0.75), emit("rec_led", (1.0, 0.25, 0.2), 10.0), bevel=0)
    cyl(0.02, 0.12, (-0.12, 0, 0.88), metal("steel", "#7c8088", 0.28), n=12)
    return c


def it_lore_log():
    c = "#a68bff"
    body = paint("slate", "#262a30", 0.38)
    outline = [(-0.32, -0.42), (0.32, -0.42), (0.32, 0.26), (0.16, 0.42), (-0.32, 0.42)]
    prism([(x, z + 0.47) for x, z in outline], 0.05, (0, 0, 0), body, bevel=0.012)
    scr = [(x * 0.86, z * 0.86) for x, z in outline]
    prism([(x, z + 0.47) for x, z in scr], 0.052, (0, -0.002, 0), paint("slate_screen", "#0b0f18", 0.12), bevel=0.004)
    em = emit("log_text", c, 6.0)
    for i, w in enumerate((0.4, 0.4, 0.4, 0.26, 0.36, 0.2)):
        box((w, 0.054, 0.024), (-0.2 + w / 2, -0.002, 0.68 - i * 0.075), em, bevel=0)
    box((0.12, 0.054, 0.12), (0.12, -0.002, 0.68), emit("log_icon", c, 10.0), bevel=0.004)
    box((0.06, 0.054, 0.02), (0.0, -0.002, 0.1), emit("log_led", A.CYAN, 6.0), bevel=0)
    return c


ITEMS = {
    "fragment": it_fragment, "core": it_core, "pu_shard": it_pu_shard, "pu_phase": it_pu_phase,
    "pu_overcharge": it_pu_overcharge, "pu_shield": it_pu_shield, "pu_echo": it_pu_echo, "q_part": it_q_part,
    "q_cell": it_q_cell, "q_chip": it_q_chip, "q_tape": it_q_tape, "q_key": it_q_key, "up_core": it_up_core,
    "up_echo": it_up_echo, "up_resonant": it_up_resonant, "up_shield": it_up_shield, "lore_rec": it_lore_rec,
    "lore_log": it_lore_log,
}
# hero angle per item (camera azimuth / elevation in degrees; flat items look better from higher up)
ANGLE = {"q_chip": (30, 48), "q_key": (28, 18), "q_tape": (28, 18), "lore_log": (26, 16), "pu_shield": (28, 14),
         "up_shield": (26, 14), "up_echo": (26, 14), "up_core": (26, 14), "up_resonant": (26, 14), "q_part": (35, 26)}


def bounds(objs):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type not in ("MESH", "FONT") or o.hide_render:
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = o.matrix_world
        pts += [mw @ v.co for v in me.vertices]
        ev.to_mesh_clear()
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx, pts


def render_item(icon, size=256, preview=False):
    A.reset()
    _M.clear()
    A.setup_render((size, size), samples=192, look="AgX - Medium High Contrast", exposure=0.0, transparent=True, adaptive=0.01)
    bpy.context.scene.cycles.transmission_bounces = 12
    A.world_gradient((0.16, 0.17, 0.2), (0.08, 0.085, 0.1), (0.02, 0.02, 0.025), strength=0.6)
    accent = ITEMS[icon]()
    objs = [o for o in bpy.context.scene.objects if o.type in ("MESH", "FONT")]
    mn, mx, pts = bounds(objs)
    # sit on the floor
    for o in objs:
        o.location.z -= mn.z
    mn.z, mx.z = 0.0, mx.z - mn.z
    ctr = (mn + mx) / 2
    az, el = ANGLE.get(icon, (35, 24))
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    # fit: project bounding points onto the camera plane, keep ~10 % margin
    lens = 70.0
    cam = A.camera(ctr + d * 10, ctr, lens=lens, sensor=36.0)
    bpy.context.view_layer.update()
    right = d.cross(Vector((0, 0, 1))).normalized()
    upv = right.cross(d).normalized()
    pts = [p - Vector((0, 0, 0)) for p in pts]
    ext = max(max(abs((p - ctr).dot(right)) for p in pts), max(abs((p - ctr).dot(upv)) for p in pts))
    half = ext * 1.16
    dist = half / math.tan(math.atan(18.0 / lens))
    cam.location = ctr + d * dist
    A.look_at(cam, ctr)
    # contact-shadow catcher
    me = bpy.data.meshes.new("catcher")
    s = 20
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    cat = bpy.data.objects.new("catcher", me)
    A.link(cat)
    cat.is_shadow_catcher = True
    me.materials.append(A.principled("catcher", (0.5, 0.5, 0.5), rough=0.6))
    # studio rig: key (warm-white, top left), fill (cool, right), accent rim (item colour, behind), top kicker
    acc = H(accent)
    R = max(ext, 0.3)
    A.light("AREA", ctr + (right * -1.6 + d * 1.4 + Vector((0, 0, 1.8))) * R * 2.2, 220 * R * R, (1.0, 0.96, 0.9), size=2.2 * R, target=tuple(ctr), name="Key")
    A.light("AREA", ctr + (right * 2.0 + d * 1.0 + Vector((0, 0, 0.4))) * R * 2.2, 60 * R * R, (0.8, 0.88, 1.0), size=2.5 * R, target=tuple(ctr), name="Fill")
    A.light("AREA", ctr + (right * 1.0 - d * 1.8 + Vector((0, 0, 1.0))) * R * 2.2, 260 * R * R, acc, size=1.2 * R, target=tuple(ctr), name="Rim")
    other = C.MAGENTA if acc[1] > 0.5 else C.NCYAN
    A.light("AREA", ctr + (right * -1.2 - d * 1.4 + Vector((0, 0, 1.6))) * R * 2.2, 200 * R * R, other, size=1.2 * R, target=tuple(ctr), name="Kicker")
    A.compositor(bloom=0.18, bloom_size=0.5, threshold=1.5, dispersion=0.0, vignette=0.0)
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, f"{icon}.png") if not preview else os.path.join(A.PREVIEWS, "tests", f"item_{icon}.png")
    A.render(out, rgba=True)
    return out


def icons_from_data():
    d = json.load(open(os.path.join(A.ROOT, "src", "data", "items.json")))
    items = d["items"] if isinstance(d, dict) and "items" in d else d
    vals = items.values() if isinstance(items, dict) else items
    return sorted({it["icon"] for it in vals if it.get("icon")})


def main():
    a = A.args()
    size = int(a[a.index("--size") + 1]) if "--size" in a else 256
    preview = "--preview" in a
    needed = icons_from_data()
    missing = [i for i in needed if i not in ITEMS]
    if missing:
        raise SystemExit(f"items.json icons without a model: {missing}")
    ids = [x for x in a if x in ITEMS] or needed
    outs = [render_item(i, size, preview) for i in ids]
    if not preview and len(ids) == len(needed):
        A.contact_sheet(outs, os.path.join(A.PREVIEWS, "items_sheet.png"), cols=6, cell=(256, 256))


if __name__ == "__main__":
    main()
