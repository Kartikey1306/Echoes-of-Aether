"""Title logotype: ECHOES OF AETHER as a rendered 3D neon / chrome cyberpunk logo, 2048 x 640 RGBA PNG.

  Blender -b --factory-startup --python logo.py -- [--preview]

Chrome-bevelled extruded letters (Rajdhani Bold, SIL OFL, from unity/.../UI/Fonts/Rajdhani) reflecting a studio
of magenta / cyan neon softboxes, a magenta neon tube tracing the letter outlines, a cyan Aether seam through the
lettering. Glow is kept in the alpha channel (luminance-keyed) so the logo composites over dark UI / key art.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import artkit as A  # noqa: E402
import cyberkit as C  # noqa: E402

FONT_BOLD = os.path.join(A.FONTS, "Rajdhani", "Rajdhani-Bold.ttf")
FONT_SEMI = os.path.join(A.FONTS, "Rajdhani", "Rajdhani-SemiBold.ttf")
OUT = os.path.join(A.RES_ART, "Title", "logo.png")


def chrome(height=1.1):
    """Stylised cyberpunk chrome: a mirror metal whose base colour carries a sharp 'horizon' gradient in object
    space (cool-white below, dark band at the horizon, magenta-tinted sky above), brushed roughness streaks, real
    reflections of the neon softboxes on the bevels and darkened crevices."""
    m = bpy.data.materials.new("Chrome")
    T = A.NT(m)
    b = T.n("ShaderNodeBsdfPrincipled", Metallic=0.45, Roughness=0.16)
    b.inputs["Anisotropic"].default_value = 0.3
    b.inputs["Coat Weight"].default_value = 1.0
    b.inputs["Coat Roughness"].default_value = 0.04
    tc = T.n("ShaderNodeTexCoord")
    sep = T.n("ShaderNodeSeparateXYZ")
    T.L(tc.outputs["Object"], sep.inputs[0])
    # text objects are rotated 90 deg about X: local Y is the letter height axis
    hz = T.maprange(sep.outputs[1], -height * 0.5, height * 0.5, 0.0, 1.0)
    ramp = T.n("ShaderNodeValToRGB")
    el = ramp.color_ramp.elements
    el[0].position, el[0].color = 0.0, (0.35, 0.55, 0.75, 1)
    el[1].position, el[1].color = 1.0, (0.98, 0.9, 1.0, 1)
    for pos, col in [(0.25, (0.85, 0.95, 1.0, 1)), (0.44, (0.5, 0.58, 0.7, 1)), (0.47, (0.03, 0.03, 0.06, 1)),
                     (0.56, (0.12, 0.06, 0.16, 1)), (0.8, (0.75, 0.42, 0.85, 1))]:
        e = el.new(pos)
        e.color = col
    T.L(hz, ramp.inputs["Fac"])
    mp = T.n("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.0, 60.0)
    T.L(tc.outputs["Object"], mp.inputs["Vector"])
    nz = T.n("ShaderNodeTexNoise", Scale=6.0, Detail=10.0, Roughness=0.6)
    T.L(mp.outputs[0], nz.inputs["Vector"])
    T.L(T.maprange(nz.outputs["Fac"], 0.3, 0.7, 0.12, 0.22), b.inputs["Roughness"])
    T.L(ramp.outputs["Color"], b.inputs["Base Color"])
    T.L(b.outputs[0], T.out.inputs["Surface"])
    return m


def keyline(src, offset, y, mat):
    """Dark extruded backing slightly larger than the letters: keeps the logo legible at small sizes."""
    ob = src.copy()
    ob.data = src.data.copy()
    ob.data.offset = offset
    ob.data.extrude = 0.04
    ob.data.bevel_depth = 0.0
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    ob.location.y = y
    A.link(ob)
    return ob


def text(body, size, loc, font, extrude=0.12, bevel=0.025, spacing=1.0, mat=None, name="Text"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = bpy.data.fonts.load(font, check_existing=True)
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.space_character = spacing
    cu.extrude = extrude
    cu.bevel_depth = bevel
    cu.bevel_resolution = 4
    ob = bpy.data.objects.new(name, cu)
    ob.location = loc
    ob.rotation_euler = (math.radians(90), 0, 0)
    A.link(ob)
    if mat:
        cu.materials.append(mat)
    return ob


def outline_tube(src, offset, radius, color, strength, y):
    """Neon tube tracing the letter outlines (text -> curve, no fill, bevelled)."""
    ob = src.copy()
    ob.data = src.data.copy()
    ob.data.extrude = 0.0
    ob.data.bevel_depth = 0.0
    ob.data.offset = offset
    A.link(ob)
    ob.location.y = y
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.convert(target="CURVE")
    cu = ob.data
    cu.dimensions = "3D"
    cu.fill_mode = "FULL"
    cu.bevel_depth = radius
    cu.bevel_resolution = 2
    cu.materials.clear()
    cu.materials.append(C.neon_mat(color, strength))
    ob.visible_shadow = False
    return ob


def studio():
    # neon softboxes the chrome reflects (out of frame), dark world
    A.world_gradient((0.02, 0.02, 0.03), (0.06, 0.05, 0.08), (0.004, 0.004, 0.006), strength=1.0)
    for loc, col, s in [((-6, -8, 6), C.MAGENTA, 6.0), ((6, -8, 6), C.NCYAN, 6.0), ((0, -9, -5), C.MAGENTA, 4.0), ((0, -6, 9), (1, 1, 1), 2.5)]:
        me = bpy.data.meshes.new("Softbox")
        me.from_pydata([(-3, 0, -0.5), (3, 0, -0.5), (3, 0, 0.5), (-3, 0, 0.5)], [], [(0, 1, 2, 3)])
        ob = bpy.data.objects.new("Softbox", me)
        ob.location = loc
        A.link(ob)
        A.look_at(ob, (0, 0, 0))
        ob.rotation_euler.x += math.radians(90)
        me.materials.append(A.emissive("softbox", col, s))
        ob.visible_camera = False
    A.light("AREA", (0, -6, 4), 220, (1, 1, 1), size=6, target=(0, 0, 0), name="Key")
    A.light("AREA", (0, -7, -2.5), 120, (0.8, 0.9, 1.0), size=6, target=(0, 0, 0), name="Under")
    A.light("AREA", (-7, 2, 1), 250, C.MAGENTA, size=3, target=(0, 0, 0.3), name="RimM")
    A.light("AREA", (7, 2, 1), 250, C.NCYAN, size=3, target=(0, 0, -0.3), name="RimC")


def logo_compositor():
    sc = bpy.context.scene
    ng = bpy.data.node_groups.new("LogoComp", "CompositorNodeTree")
    sc.compositing_node_group = ng
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    N, L = ng.nodes, ng.links.new
    rl = N.new("CompositorNodeRLayers")
    g = N.new("CompositorNodeGlare")
    g.inputs["Type"].default_value = "Bloom"
    g.inputs["Quality"].default_value = "High"
    g.inputs["Threshold"].default_value = 0.8
    g.inputs["Strength"].default_value = 0.55
    g.inputs["Size"].default_value = 0.7
    L(rl.outputs["Image"], g.inputs["Image"])
    bw = N.new("CompositorNodeRGBToBW")
    L(g.outputs["Image"], bw.inputs["Image"])
    k = N.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = 1.2
    k.use_clamp = True
    L(bw.outputs[0], k.inputs[0])
    mx = N.new("ShaderNodeMath")
    mx.operation = "MAXIMUM"
    L(rl.outputs["Alpha"], mx.inputs[0])
    L(k.outputs[0], mx.inputs[1])
    sa = N.new("CompositorNodeSetAlpha")
    try:
        sa.inputs["Type"].default_value = "Replace Alpha"
    except Exception:
        pass
    L(g.outputs["Image"], sa.inputs["Image"])
    L(mx.outputs[0], sa.inputs["Alpha"])
    out = N.new("NodeGroupOutput")
    L(sa.outputs["Image"], out.inputs["Image"])


def build(res=(2048, 640), samples=256):
    A.reset()
    A.setup_render(res, samples=samples, look="AgX - Medium High Contrast", exposure=0.0, transparent=True, adaptive=0.01)
    studio()
    big = text("ECHOES", 1.55, (0, 0, 0.42), FONT_BOLD, extrude=0.14, bevel=0.03, spacing=1.12, mat=chrome(1.1), name="Echoes")
    small = text("OF  AETHER", 0.62, (0.0, 0, -0.78), FONT_SEMI, extrude=0.08, bevel=0.016, spacing=1.55, mat=chrome(0.45), name="OfAether")
    # chromatic 'glitch' ghost: a cyan copy of ECHOES offset behind the chrome, sliced into bands
    ghost = big.copy()
    ghost.data = big.data.copy()
    ghost.data.extrude = 0.01
    ghost.data.bevel_depth = 0.0
    ghost.data.materials.clear()
    ghost.data.materials.append(C.neon_mat(C.NCYAN, 5.0))
    ghost.location = (big.location.x - 0.07, 0.3, big.location.z + 0.03)
    A.link(ghost)
    bpy.context.view_layer.objects.active = ghost
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ghost.select_set(True)
    bpy.ops.object.convert(target="MESH")
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ghost.data)
    for cut in (0.12, 0.45, 0.62):
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, dist=0.0001, plane_co=(0, cut, 0), plane_no=(0, 1, 0))
    kill = [f for f in bm.faces if 0.12 < f.calc_center_median().y < 0.45]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(ghost.data)
    bm.free()
    ink = A.principled("keyline", (0.01, 0.01, 0.015), rough=0.4)
    keyline(big, 0.06, 0.16, ink)
    keyline(small, 0.035, 0.1, ink)
    outline_tube(big, 0.0, 0.012, C.MAGENTA, 9.0, -0.2)
    outline_tube(small, 0.0, 0.007, C.NCYAN, 9.0, -0.11)
    # Aether seam: a cyan neon line slicing across, broken where it passes the lettering gap
    C.tubes([[Vector((-3.55, -0.25, -0.2)), Vector((-1.95, -0.25, -0.2))], [Vector((1.95, -0.25, -0.2)), Vector((3.55, -0.25, -0.2))]],
            C.NCYAN, 10.0, 0.012, name="Seam")
    for sx in (-1, 1):
        C.tubes([[Vector((sx * 3.62, -0.25, -0.32)), Vector((sx * 3.62, -0.25, -0.08))]], C.MAGENTA, 10.0, 0.012, name="SeamCap")
    cam = A.camera((0, -14, 0.0), (0, 0, 0.0), lens=50)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 7.6
    logo_compositor()
    return cam


def main():
    a = A.args()
    preview = "--preview" in a
    build((1024, 320) if preview else (2048, 640), 96 if preview else 256)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out = os.path.join(A.PREVIEWS, "tests", "logo_preview.png") if preview else OUT
    A.render(out, rgba=True)
    A.over_color(out, os.path.join(A.PREVIEWS, "tests" if preview else "", "logo_on_dark.png"))
    if not preview:
        A.save_scene("logo")


if __name__ == "__main__":
    main()
