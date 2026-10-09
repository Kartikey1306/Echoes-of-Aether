"""Preview rendering helpers (EEVEE): textured materials from the baked PNGs, studio lighting, camera framing,
labels and contact-sheet composition."""
import json
import math
import os

import bpy
import numpy as np
from mathutils import Vector

import envpaths
import matdefs
import pngio

_state = None


def baked_state():
    global _state
    if _state is None:
        p = os.path.join(envpaths.STATE, "materials_baked.json")
        _state = json.load(open(p)) if os.path.exists(p) else {}
    return _state


def tile_of(name):
    d = matdefs.REGISTRY[name]
    if d["kind"] == "tint":
        d = matdefs.REGISTRY[d["parent"]]
    return d.get("tile", 1.0), d.get("uv", "world")


def _img(path, noncolor):
    full = os.path.join(envpaths.UNITY_ENV, path)
    im = bpy.data.images.load(full, check_existing=True)
    if noncolor:
        im.colorspace_settings.name = "Non-Color"
        im.alpha_mode = "CHANNEL_PACKED"
    return im


def textured(name, mat=None):
    """Build (or rebuild) a preview material equivalent to the Unity URP/Lit setup."""
    d = matdefs.REGISTRY[name]
    m = mat or bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    L = nt.links.new
    if d["kind"] == "param":
        u = d["unity"]
        c = u.get("baseColor", [0.5, 0.5, 0.5, 1.0])
        bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
        bsdf.inputs["Metallic"].default_value = u.get("metallic", 0.0)
        bsdf.inputs["Roughness"].default_value = 1.0 - u.get("smoothness", 0.5)
        if "emission" in u and u.get("emissionIntensity", 0) > 0:
            e = u["emission"]
            bsdf.inputs["Emission Color"].default_value = (e[0], e[1], e[2], 1.0)
            bsdf.inputs["Emission Strength"].default_value = u["emissionIntensity"]
        if u.get("surface") == "Transparent":
            bsdf.inputs["Alpha"].default_value = max(0.15, c[3])
            if name == "glass":
                bsdf.inputs["Transmission Weight"].default_value = 0.0
            m.surface_render_method = "BLENDED"
        return m
    st = baked_state().get(name)
    if not st:
        c = matdefs.preview_color(name)
        bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
        return m
    tex = st["textures"]
    tile, uvmode = tile_of(name)
    tc = nt.nodes.new("ShaderNodeUVMap")
    tc.uv_map = "UVMap"
    mp = nt.nodes.new("ShaderNodeMapping")
    if uvmode in ("world", "world0"):
        mp.inputs["Scale"].default_value = (1 / tile, 1 / tile, 1)
    elif uvmode == "strip":
        mp.inputs["Scale"].default_value = (1 / tile, 1, 1)
    L(tc.outputs[0], mp.inputs["Vector"])
    vec = mp.outputs[0]
    bc = nt.nodes.new("ShaderNodeTexImage")
    bc.image = _img(tex["BaseColor"], False)
    L(vec, bc.inputs[0])
    mk = nt.nodes.new("ShaderNodeTexImage")
    mk.image = _img(tex["MaskMap"], True)
    L(vec, mk.inputs[0])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    L(mk.outputs["Color"], sep.inputs[0])
    L(sep.outputs[0], bsdf.inputs["Metallic"])
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    L(mk.outputs["Alpha"], inv.inputs[1])
    L(inv.outputs[0], bsdf.inputs["Roughness"])
    # AO approximated by darkening base colour (EEVEE has no AO input)
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    [i for i in mul.inputs if i.identifier == "Factor_Float"][0].default_value = 1.0
    L(bc.outputs["Color"], [i for i in mul.inputs if i.identifier == "A_Color"][0])
    aoc = nt.nodes.new("ShaderNodeCombineColor")
    for k in range(3):
        L(sep.outputs[1], aoc.inputs[k])
    L(aoc.outputs[0], [i for i in mul.inputs if i.identifier == "B_Color"][0])
    L([o for o in mul.outputs if o.identifier == "Result_Color"][0], bsdf.inputs["Base Color"])
    nm = nt.nodes.new("ShaderNodeTexImage")
    nm.image = _img(tex["Normal"], True)
    L(vec, nm.inputs[0])
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nmap.uv_map = "UVMap"
    L(nm.outputs["Color"], nmap.inputs["Color"])
    L(nmap.outputs[0], bsdf.inputs["Normal"])
    if "Emission" in tex:
        em = nt.nodes.new("ShaderNodeTexImage")
        em.image = _img(tex["Emission"], False)
        L(vec, em.inputs[0])
        L(em.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = d["unity"].get("emissionIntensity", 1.0)
    if d.get("unity", {}).get("alphaClip"):
        L(bc.outputs["Alpha"], bsdf.inputs["Alpha"])
        m.surface_render_method = "DITHERED"
    return m


# ============================================================================================== studio
def setup_render(res=(640, 480), samples=24):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    ee = sc.eevee
    ee.taa_render_samples = samples
    try:
        ee.use_raytracing = True
        ee.ray_tracing_options.resolution_scale = "1"
    except Exception:
        pass
    try:
        ee.use_shadows = True
    except Exception:
        pass
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0


def setup_world(strength=0.7, top=(0.62, 0.66, 0.72), horizon=(0.42, 0.42, 0.42), bottom=(0.12, 0.12, 0.12)):
    w = bpy.data.worlds.new("Studio")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.35, (*bottom, 1)
    els[1].position, els[1].color = 0.5, (*horizon, 1)
    e = els.new(0.85)
    e.color = (*top, 1)
    # Generated coords for world = view direction; z in [-1,1] -> map to [0,1]
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -1
    mr.inputs["From Max"].default_value = 1
    nt.links.new(sep.outputs[2], mr.inputs["Value"])
    nt.links.new(mr.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs[0], out.inputs["Surface"])


def add_sun(rot_deg, strength=3.0, angle=3.0, color=(1, 0.97, 0.92)):
    ld = bpy.data.lights.new("Sun", "SUN")
    ld.energy = strength
    ld.angle = math.radians(angle)
    ld.color = color
    ob = bpy.data.objects.new("Sun", ld)
    ob.rotation_euler = [math.radians(a) for a in rot_deg]
    bpy.context.scene.collection.objects.link(ob)
    return ob


def add_floor(size=200.0, color=(0.16, 0.16, 0.165), rough=0.7, z=0.0):
    me = bpy.data.meshes.new("Floor")
    s = size / 2
    me.from_pydata([(-s, -s, z), (s, -s, z), (s, s, z), (-s, s, z)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("Floor", me)
    bpy.context.scene.collection.objects.link(ob)
    m = bpy.data.materials.new("__floor")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    me.materials.append(m)
    return ob


def studio(res=(640, 480), samples=24):
    setup_render(res, samples)
    setup_world()
    add_sun((50, 0, -40), 3.2)
    add_sun((70, 0, 150), 0.8, color=(0.8, 0.88, 1.0))
    add_floor()
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cd.lens = 40
    cd.clip_start = 0.05
    cd.clip_end = 2000
    return cam


def add_area(loc, rot_deg, size, energy, color):
    ld = bpy.data.lights.new("Area", "AREA")
    ld.energy = energy
    ld.size = size
    ld.color = color
    ob = bpy.data.objects.new("Area", ld)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot_deg]
    bpy.context.scene.collection.objects.link(ob)
    return ob


def wet_floor(size=200.0):
    """Dark glossy wet asphalt-ish floor for neon night previews (mirror-like puddle sheen)."""
    me = bpy.data.meshes.new("Floor")
    s = size / 2
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("Floor", me)
    bpy.context.scene.collection.objects.link(ob)
    m = bpy.data.materials.new("__wetfloor")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.012, 0.013, 0.016, 1)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.35
    nz.inputs["Detail"].default_value = 3
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.45
    mr.inputs["From Max"].default_value = 0.55
    mr.inputs["To Min"].default_value = 0.32
    mr.inputs["To Max"].default_value = 0.04
    nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs[0], b.inputs["Roughness"])
    me.materials.append(m)
    return ob


def night(res=(640, 480), samples=32):
    """Neon night studio: dark blue-violet sky, wet glossy floor, cool moon key, magenta + cyan neon rims.
    Emissive materials bloom (EEVEE bloom via compositor glare)."""
    setup_render(res, samples)
    sc = bpy.context.scene
    sc.view_settings.exposure = 0.4
    setup_world(0.22, top=(0.05, 0.06, 0.12), horizon=(0.10, 0.07, 0.16), bottom=(0.01, 0.01, 0.015))
    add_sun((52, 0, -28), 1.1, angle=2.0, color=(0.62, 0.7, 1.0))
    add_area((-6, -3, 4.5), (60, 0, -60), 6.0, 520.0, (1.0, 0.17, 0.84))
    add_area((7, 2, 3.5), (65, 0, 110), 6.0, 520.0, (0.0, 0.9, 1.0))
    add_area((0, 9, 6), (-50, 0, 180), 8.0, 260.0, (0.4, 0.3, 1.0))
    wet_floor()
    _glare()
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cd.lens = 40
    cd.clip_start = 0.05
    cd.clip_end = 3000
    return cam


def _glare():
    """Bloom via compositor Glare (fog glow) so neon reads as light."""
    sc = bpy.context.scene
    try:
        sc.use_nodes = True
        nt = sc.compositing_node_group if hasattr(sc, "compositing_node_group") else sc.node_tree
        if nt is None:
            nt = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
            sc.compositing_node_group = nt
        nt.nodes.clear()
        rl = nt.nodes.new("CompositorNodeRLayers")
        gl = nt.nodes.new("CompositorNodeGlare")
        for k, v in (("glare_type", "FOG_GLOW"), ("quality", "HIGH"), ("threshold", 0.9), ("size", 7)):
            try:
                setattr(gl, k, v)
            except Exception:
                pass
        for k, v in (("Type", "Fog Glow"), ("Threshold", 0.9), ("Strength", 0.9), ("Size", 0.6)):
            if k in gl.inputs:
                try:
                    gl.inputs[k].default_value = v
                except Exception:
                    pass
        try:
            out = nt.nodes.new("CompositorNodeComposite")
        except Exception:
            out = nt.nodes.new("NodeGroupOutput")
            nt.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        nt.links.new(rl.outputs["Image"], gl.inputs[0])
        nt.links.new(gl.outputs[0], out.inputs[0])
    except Exception as e:  # compositor API differences: render without bloom
        print("[preview] glare unavailable:", e)


def frame(cam, bmin, bmax, az=35.0, el=22.0, margin=1.08):
    bmin, bmax = Vector(bmin), Vector(bmax)
    c = (bmin + bmax) / 2
    ext = bmax - bmin
    r = max(0.25, ext.length / 2)
    sc = bpy.context.scene
    aspect = sc.render.resolution_x / sc.render.resolution_y
    fov = cam.data.angle  # horizontal
    fov_v = 2 * math.atan(math.tan(fov / 2) / aspect)
    dist = r * margin / math.sin(min(fov, fov_v) / 2)
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    cam.location = c + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    return dist


def label(cam, text, size=0.045):
    cu = bpy.data.curves.new("Label", "FONT")
    cu.body = text
    cu.size = size
    ob = bpy.data.objects.new("Label", cu)
    bpy.context.scene.collection.objects.link(ob)
    m = bpy.data.materials.new("__label")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1, 1, 1, 1)
    em.inputs["Strength"].default_value = 1.0
    nt.links.new(em.outputs[0], o.inputs["Surface"])
    cu.materials.append(m)
    ob.parent = cam
    sc = bpy.context.scene
    aspect = sc.render.resolution_x / sc.render.resolution_y
    hw = math.tan(cam.data.angle / 2)
    hh = hw / aspect
    d = 0.2
    cu.size = size * d
    ob.location = (-hw * 0.96 * d, -hh * 0.93 * d, -d)
    ob.visible_shadow = False
    return ob


def render_array(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(path)
    w, h = im.size
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    return (a.reshape(h, w, 4)[::-1, :, :3] * 255 + 0.5).astype(np.uint8)


def sheet(tiles, cols, out_path, gap=4, bg=18):
    if not tiles:
        return
    h, w = tiles[0].shape[:2]
    rows = (len(tiles) + cols - 1) // cols
    S = np.full((rows * h + (rows + 1) * gap, cols * w + (cols + 1) * gap, 3), bg, np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        y, x = gap + r * (h + gap), gap + c * (w + gap)
        S[y:y + h, x:x + w] = t[:h, :w]
    pngio.write_png(out_path, S)
