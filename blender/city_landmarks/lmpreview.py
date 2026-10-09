"""Cycles (GPU) preview helpers: Unity URP/Lit-equivalent node materials from the kit manifests (env kit, landmark kit,
building atlases), a rainy-night street stage, camera framing and contact sheets."""
import json
import math
import os

import bpy
import numpy as np
from mathutils import Vector

import lmpaths

_defs = None


def material_defs():
    """name -> (definition, kit root) from the env manifest, the landmark kit manifest (if built) and the atlas layout."""
    global _defs
    if _defs is not None:
        return _defs
    _defs = {}
    env = json.load(open(os.path.join(lmpaths.ENV_KIT, "manifest.json")))["materials"]
    for k, v in env.items():
        _defs[k] = (v, lmpaths.ENV_KIT)
    lay = json.load(open(lmpaths.ATLAS_LAYOUT))
    for k, a in lay["atlases"].items():
        d = {"kind": "external", "uvMode": "atlas", "tiling": [1.0, 1.0], "textures": a["textures"]}
        if k.startswith("emit_"):
            d["emissionIntensity"] = lay["emitMax"]
        _defs[k] = (d, lmpaths.ENV_KIT)
    kitm = os.path.join(lmpaths.OUT, "kit_materials.json")
    if os.path.exists(kitm):
        for k, v in json.load(open(kitm)).items():
            _defs[k] = (v, lmpaths.KIT)
    return _defs


def _img(root, rel, noncolor):
    im = bpy.data.images.load(os.path.join(root, rel), check_existing=True)
    if noncolor:
        im.colorspace_settings.name = "Non-Color"
        im.alpha_mode = "CHANNEL_PACKED"
    return im


def _srgb2lin(c):
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def build_material(name):
    defs = material_defs()
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    L = nt.links.new
    L(bsdf.outputs[0], out.inputs["Surface"])
    if name not in defs:
        bsdf.inputs["Base Color"].default_value = (0.3, 0.3, 0.3, 1)
        return m
    d, root = defs[name]
    if d.get("kind") == "param" and not d.get("textures"):
        c = d.get("baseColor", [0.5, 0.5, 0.5, 1.0])
        lc = _srgb2lin(c[:3])
        bsdf.inputs["Base Color"].default_value = (*lc, 1.0)
        bsdf.inputs["Metallic"].default_value = d.get("metallic", 0.0)
        bsdf.inputs["Roughness"].default_value = 1.0 - d.get("smoothness", 0.5)
        if d.get("emission") and d.get("emissionIntensity", 0) > 0:
            bsdf.inputs["Emission Color"].default_value = (*_srgb2lin(d["emission"]), 1.0)
            bsdf.inputs["Emission Strength"].default_value = d["emissionIntensity"]
        if d.get("surface") == "Transparent":
            if d.get("blend") == "Additive":
                bsdf.inputs["Alpha"].default_value = 0.0
                bsdf.inputs["Emission Strength"].default_value = d.get("emissionIntensity", 1.0) * c[3]
                tr = nt.nodes.new("ShaderNodeBsdfTransparent")
                add = nt.nodes.new("ShaderNodeAddShader")
                em = nt.nodes.new("ShaderNodeEmission")
                em.inputs[0].default_value = (*_srgb2lin(d.get("emission", c[:3])), 1)
                em.inputs[1].default_value = d.get("emissionIntensity", 1.0) * c[3] * 2
                L(tr.outputs[0], add.inputs[0])
                L(em.outputs[0], add.inputs[1])
                L(add.outputs[0], out.inputs["Surface"])
            else:
                bsdf.inputs["Alpha"].default_value = max(0.12, c[3])
        return m
    tex = d.get("textures", {})
    tl = d.get("tiling", [1.0, 1.0])
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "UVMap"
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (tl[0], tl[1], 1)
    L(uvn.outputs[0], mp.inputs["Vector"])
    vec = mp.outputs[0]
    bc = nt.nodes.new("ShaderNodeTexImage")
    bc.image = _img(root, tex["BaseColor"], False)
    bc.interpolation = "Cubic" if d.get("uvMode") == "atlas" else "Linear"
    L(vec, bc.inputs[0])
    mk = nt.nodes.new("ShaderNodeTexImage")
    mk.image = _img(root, tex["MaskMap"], True)
    L(vec, mk.inputs[0])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    L(mk.outputs["Color"], sep.inputs[0])
    L(sep.outputs[0], bsdf.inputs["Metallic"])
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    L(mk.outputs["Alpha"], inv.inputs[1])
    L(inv.outputs[0], bsdf.inputs["Roughness"])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    L(bc.outputs["Color"], mul.inputs[6])
    aoc = nt.nodes.new("ShaderNodeCombineColor")
    for k in range(3):
        L(sep.outputs[1], aoc.inputs[k])
    L(aoc.outputs[0], mul.inputs[7])
    L(mul.outputs[2], bsdf.inputs["Base Color"])
    if "Normal" in tex:
        nm = nt.nodes.new("ShaderNodeTexImage")
        nm.image = _img(root, tex["Normal"], True)
        L(vec, nm.inputs[0])
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.uv_map = "UVMap"
        nmap.inputs["Strength"].default_value = d.get("normalScale", 1.0)
        L(nm.outputs["Color"], nmap.inputs["Color"])
        L(nmap.outputs[0], bsdf.inputs["Normal"])
    if "Emission" in tex:
        em = nt.nodes.new("ShaderNodeTexImage")
        em.image = _img(root, tex["Emission"], False)
        L(vec, em.inputs[0])
        L(em.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = d.get("emissionIntensity", 1.0)
    if d.get("alphaClip") is not None:
        L(bc.outputs["Alpha"], bsdf.inputs["Alpha"])
    if d.get("surface") == "Transparent":
        bsdf.inputs["Alpha"].default_value = 0.25
    return m


def apply_materials(objs):
    done = {}
    for ob in objs:
        if ob.type != "MESH":
            continue
        for i, slot in enumerate(ob.material_slots):
            if slot.material is None:
                continue
            n = slot.material.name.split(".")[0]
            if n not in done:
                done[n] = build_material(n)
            slot.material = done[n]


# ============================================================================================== stage
def setup(samples=96, res=(1400, 1000), exposure=0.0, gpu=True):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    if gpu:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        try:
            prefs.compute_device_type = "METAL"
            prefs.get_devices()
            for dv in prefs.devices:
                dv.use = dv.type == "METAL"
            sc.cycles.device = "GPU"
        except Exception:
            sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 6
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = exposure
    return sc


def night_world(strength=1.0, top=(0.012, 0.016, 0.035), horizon=(0.05, 0.035, 0.07)):
    w = bpy.data.worlds.new("night")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (*horizon, 1)
    ramp.color_ramp.elements[1].position = 0.45
    ramp.color_ramp.elements[1].color = (*top, 1)
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs[2], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = strength
    nt.links.new(bg.outputs[0], out.inputs[0])


def ground(size=400, mat="asphalt", wet=True):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    g = bpy.context.active_object
    g.name = "Ground"
    me = g.data
    uv = me.uv_layers.active
    for li, l in enumerate(me.loops):
        co = me.vertices[l.vertex_index].co
        uv.data[li].uv = (co.x, co.y)
    m = build_material(mat)
    if wet:
        b = m.node_tree.nodes.get("Principled BSDF")
        if b is not None:
            for lk in list(m.node_tree.links):
                if lk.to_socket == b.inputs["Roughness"]:
                    m.node_tree.links.remove(lk)
            b.inputs["Roughness"].default_value = 0.12
    me.materials.append(m)
    return g


def area(loc, rot, size, color, power, shape="RECTANGLE", size_y=None):
    l = bpy.data.lights.new("a", "AREA")
    l.shape = shape
    l.size = size
    if size_y:
        l.size_y = size_y
    l.color = color
    l.energy = power
    o = bpy.data.objects.new("a", l)
    o.location = loc
    o.rotation_euler = rot
    bpy.context.scene.collection.objects.link(o)
    return o


def point(loc, color, power, radius=0.3):
    l = bpy.data.lights.new("p", "POINT")
    l.color = color
    l.energy = power
    l.shadow_soft_size = radius
    o = bpy.data.objects.new("p", l)
    o.location = loc
    bpy.context.scene.collection.objects.link(o)
    return o


def moon(strength=0.08, angle=(math.radians(55), 0, math.radians(35)), color=(0.65, 0.75, 1.0)):
    l = bpy.data.lights.new("moon", "SUN")
    l.energy = strength
    l.color = color
    l.angle = math.radians(3)
    o = bpy.data.objects.new("moon", l)
    o.rotation_euler = angle
    bpy.context.scene.collection.objects.link(o)
    return o


def city_lights(bmin, bmax, seed=3, n=6, power=1.0):
    """Street-level coloured fill (shop glow, neon spill, sodium lamps) around a footprint."""
    rng = np.random.default_rng(seed)
    cols = [(1.0, 0.55, 0.25), (0.2, 0.85, 1.0), (1.0, 0.2, 0.8), (1.0, 0.75, 0.45), (0.5, 0.4, 1.0)]
    cx, cy = (bmin[0] + bmax[0]) / 2, (bmin[1] + bmax[1]) / 2
    rx, ry = (bmax[0] - bmin[0]) / 2 + 6, (bmax[1] - bmin[1]) / 2 + 6
    for i in range(n):
        a = rng.uniform(0, math.tau)
        loc = (cx + math.cos(a) * rx, cy + math.sin(a) * ry, rng.uniform(3, 7))
        point(loc, cols[i % len(cols)], 2500 * power, 1.5)


def camera(target, dist, yaw_deg, pitch_deg, lens=35, height=None):
    cam = bpy.data.cameras.new("cam")
    cam.lens = lens
    cam.clip_end = 3000
    o = bpy.data.objects.new("cam", cam)
    bpy.context.scene.collection.objects.link(o)
    t = Vector(target)
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    d = Vector((math.sin(yaw) * math.cos(pitch), -math.cos(yaw) * math.cos(pitch), math.sin(pitch)))
    o.location = t + d * dist
    if height is not None:
        o.location.z = height
    look = t - o.location
    o.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = o
    return o


def bounds(objs):
    mn = Vector((1e9, 1e9, 1e9))
    mx = Vector((-1e9, -1e9, -1e9))
    for ob in objs:
        for c in ob.bound_box:
            w = ob.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, w))
            mx = Vector(map(max, mx, w))
    return mn, mx


def render(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)


def label_sheet(paths, out, cols, labels=None, cell=(700, 500)):
    """Contact sheet with labels (PIL available only outside Blender; inside, plain numpy tiling)."""
    imgs = []
    for p in paths:
        im = bpy.data.images.load(p)
        w, h = im.size
        a = np.array(im.pixels[:], np.float32).reshape(h, w, 4)[::-1]
        imgs.append(a)
        bpy.data.images.remove(im)
    return imgs
