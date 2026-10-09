"""Neon-night preview of the URP decal set (Cycles): each decal is blended into a wet asphalt ground or a dark
concrete wall exactly like a URP decal (albedo / smoothness / metallic / AO lerped by BaseColor alpha, normal
lerped by alpha * normalBlend), under magenta / cyan neon with emissive tubes and an LED sign so puddles show
reflections.

  Blender -b --factory-startup --python render_decals.py -- [--size 560x420] [--cols 3] [--samples 48] [names/globs]
Sheets: previews/decals_<group>_NN.png (groups: water, cracks, road, wall, damage, litter, posters, utility).
"""
import fnmatch
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import envpaths  # noqa: E402
import preview  # noqa: E402

TEX = envpaths.UNITY_ENV
GROUPS = [("water", ["Puddle_*", "Oil_*"]), ("cracks", ["Crack_*"]), ("road", ["Road*", "Crosswalk*"]),
          ("wall", ["Grime_Leak*", "Rust_*", "Grime_Base*", "Grime_Tags*"]),
          ("damage", ["Scorch*", "Bullet*"]), ("litter", ["Debris*", "Litter*"]),
          ("posters", ["Poster*", "Stencil*"]), ("utility", ["Drain*", "Manhole*"])]
NEON = {"magenta": (1.0, 0.025, 0.67), "pink": (1.0, 0.08, 0.32), "cyan": (0.0, 0.78, 1.0), "blue": (0.05, 0.2, 1.0),
        "yellow": (1.0, 0.75, 0.07), "violet": (0.33, 0.1, 1.0)}


# ---------------------------------------------------------------------------------------------- scene helpers
def setup(size, samples):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type == "METAL"
        sc.cycles.device = "GPU"
    except Exception as e:  # pragma: no cover
        print("[render] GPU unavailable:", e)
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    sc.cycles.max_bounces = 6
    sc.cycles.glossy_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.render.resolution_x, sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.exposure = 0.3
    preview.setup_world(0.35, top=(0.05, 0.06, 0.13), horizon=(0.13, 0.08, 0.2), bottom=(0.01, 0.01, 0.015))


def mesh(name, verts, faces, uvs):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name="UVMap")
    for li, uv in enumerate(uvs):
        uvl.data[li].uv = uv
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def emissive(name, colour, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*colour, 1)
    e.inputs["Strength"].default_value = strength
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    return m


def tube(a, b, r, mat):
    a, b = np.array(a, float), np.array(b, float)
    d = b - a
    ln = float(np.linalg.norm(d))
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=r, depth=ln, location=tuple((a + b) / 2))
    ob = bpy.context.active_object
    z = np.array((0, 0, 1.0))
    axis = np.cross(z, d / ln)
    if np.linalg.norm(axis) > 1e-6:
        ang = math.acos(max(-1, min(1, float(np.dot(z, d / ln)))))
        ob.rotation_mode = "AXIS_ANGLE"
        ob.rotation_axis_angle = (ang, *(axis / np.linalg.norm(axis)))
    ob.data.materials.append(mat)
    return ob


def sign_panel(center, w, h, ad, strength=2.5, normal_y=-1):
    x, y, z = center
    ob = mesh("Sign", [(x - w / 2, y, z - h / 2), (x + w / 2, y, z - h / 2), (x + w / 2, y, z + h / 2), (x - w / 2, y, z + h / 2)],
              [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)])
    m = bpy.data.materials.new("SignMat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Strength"].default_value = strength
    p = os.path.join(TEX, f"Textures/{ad}/{ad}_Emission.png")
    if os.path.exists(p):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(p, check_existing=True)
        nt.links.new(t.outputs["Color"], e.inputs["Color"])
    else:
        e.inputs["Color"].default_value = (*NEON["magenta"], 1)
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    ob.data.materials.append(m)
    return ob


def dark_mat(name, col=(0.018, 0.018, 0.022), rough=0.35):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    return m


# ---------------------------------------------------------------------------------------------- decal-on-surface material
def _img(rel, noncolor):
    im = bpy.data.images.load(os.path.join(TEX, rel), check_existing=True)
    if noncolor:
        im.colorspace_settings.name = "Non-Color"
        im.alpha_mode = "CHANNEL_PACKED"
    else:
        im.alpha_mode = "STRAIGHT"
    return im


def _mix(nt, kind, fac, a, b):
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = kind
    if kind == "VECTOR":
        n.factor_mode = "UNIFORM"
    ident = {"RGBA": "Color", "VECTOR": "Vector", "FLOAT": "Float"}[kind]
    ins = {i.identifier: i for i in n.inputs}
    L = nt.links.new
    for key, val in (("Factor_Float", fac), (f"A_{ident}", a), (f"B_{ident}", b)):
        if isinstance(val, (int, float)):
            ins[key].default_value = val
        elif isinstance(val, tuple):
            ins[key].default_value = val
        else:
            L(val, ins[key])
    return [o for o in n.outputs if o.identifier == f"Result_{ident}"][0]


def _math(nt, op, a, b=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def surface_material(substrate, tile, decal, rect, wet=0.75, dark=1.0, plane="xy"):
    """Ground / wall material with the decal blended in. rect = (cx, cy, w, h) in plane coords (metres)."""
    m = bpy.data.materials.new("Surface")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    L = nt.links.new
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    L(bsdf.outputs[0], out.inputs["Surface"])
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    # substrate (world-scale UVs)
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / tile, 1 / tile, 1)
    L(uv.outputs[0], mp.inputs["Vector"])

    def tex(rel, nc, vec):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = _img(rel, nc)
        L(vec, t.inputs[0])
        return t

    base = f"Textures/{substrate}/{substrate}"
    gcol = tex(base + "_BaseColor.png", False, mp.outputs[0])
    gmask = tex(base + "_MaskMap.png", True, mp.outputs[0])
    gnrm = tex(base + "_Normal.png", True, mp.outputs[0])
    gsep = nt.nodes.new("ShaderNodeSeparateColor")
    L(gmask.outputs["Color"], gsep.inputs[0])
    # decal UVs: (p - centre) / size + 0.5, clipped outside
    cx, cy, w, h = rect
    dmp = nt.nodes.new("ShaderNodeMapping")
    dmp.inputs["Scale"].default_value = (1 / w, 1 / h, 1)
    dmp.inputs["Location"].default_value = (0.5 - cx / w, 0.5 - cy / h, 0)
    L(uv.outputs[0], dmp.inputs["Vector"])
    tx = decal["textures"]
    dcol = tex(tx["BaseColor"], False, dmp.outputs[0])
    dmask = tex(tx["MaskMap"], True, dmp.outputs[0])
    dnrm = tex(tx["Normal"], True, dmp.outputs[0])
    dcol.extension = "CLIP"
    for t in (dmask, dnrm):
        t.extension = "EXTEND"
    dsep = nt.nodes.new("ShaderNodeSeparateColor")
    L(dmask.outputs["Color"], dsep.inputs[0])
    a = dcol.outputs["Alpha"]
    # albedo: lerp, then AO (lerped) applied as a multiplier (EEVEE/Cycles have no AO input)
    g_dark = _mix(nt, "RGBA", 1.0, (1, 1, 1, 1), gcol.outputs["Color"])
    gc = nt.nodes.new("ShaderNodeMix")
    gc.data_type = "RGBA"
    gc.blend_type = "MULTIPLY"
    ins = {i.identifier: i for i in gc.inputs}
    ins["Factor_Float"].default_value = 1.0
    L(g_dark, ins["A_Color"])
    ins["B_Color"].default_value = (dark, dark, dark, 1)
    g_out = [o for o in gc.outputs if o.identifier == "Result_Color"][0]
    albedo = _mix(nt, "RGBA", a, g_out, dcol.outputs["Color"])
    ao = _mix(nt, "FLOAT", a, gsep.outputs[1], dsep.outputs[1])
    aoc = nt.nodes.new("ShaderNodeCombineColor")
    for k in range(3):
        L(ao, aoc.inputs[k])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    ins = {i.identifier: i for i in mul.inputs}
    ins["Factor_Float"].default_value = 1.0
    L(albedo, ins["A_Color"])
    L(aoc.outputs[0], ins["B_Color"])
    L([o for o in mul.outputs if o.identifier == "Result_Color"][0], bsdf.inputs["Base Color"])
    # smoothness (ground made wetter), metallic
    g_sm = gmask.outputs["Alpha"]
    g_sm = _math(nt, "ADD", _math(nt, "MULTIPLY", g_sm, 1 - wet * 0.35), wet * 0.35)
    sm = _mix(nt, "FLOAT", a, g_sm, dmask.outputs["Alpha"])
    L(_math(nt, "SUBTRACT", 1.0, sm), bsdf.inputs["Roughness"])
    L(_mix(nt, "FLOAT", a, 0.0, dsep.outputs[0]), bsdf.inputs["Metallic"])
    # normals: lerp(ground, decal, alpha * normalBlend), normalised
    gn = nt.nodes.new("ShaderNodeNormalMap")
    gn.uv_map = "UVMap"
    L(gnrm.outputs["Color"], gn.inputs["Color"])
    dn = nt.nodes.new("ShaderNodeNormalMap")
    dn.uv_map = "UVMap"
    L(dnrm.outputs["Color"], dn.inputs["Color"])
    nf = _math(nt, "MULTIPLY", a, decal["urp"]["normalBlend"])
    nmix = _mix(nt, "VECTOR", nf, gn.outputs[0], dn.outputs[0])
    nrm = nt.nodes.new("ShaderNodeVectorMath")
    nrm.operation = "NORMALIZE"
    L(nmix, nrm.inputs[0])
    L(nrm.outputs[0], bsdf.inputs["Normal"])
    return m


# ---------------------------------------------------------------------------------------------- scenes
def floor_scene(decal, el):
    w, h = decal["sizeMeters"]
    k = 9.0
    gr = mesh("Ground", [(-k, -k, 0), (k, -k, 0), (k, k, 0), (-k, k, 0)], [(0, 1, 2, 3)],
              [(-k, -k), (k, -k), (k, k), (-k, k)])
    tags = decal.get("tags", [])
    sub = "concrete_wet" if ("concrete" in tags or "bullet" in tags) else "asphalt"
    tile = 2.0 if sub == "concrete_wet" else 4.0
    gr.data.materials.append(surface_material(sub, tile, decal, (0, 0, w, h), dark=0.8 if sub == "asphalt" else 0.55))
    # street front beyond the decal: dark facade, neon tubes, an LED sign
    Y0 = h / 2 + 3.5
    fac = mesh("Facade", [(-12, Y0, 0), (12, Y0, 0), (12, Y0, 9), (-12, Y0, 9)], [(0, 1, 2, 3)],
               [(0, 0), (1, 0), (1, 1), (0, 1)])
    fac.data.materials.append(dark_mat("Facade", (0.02, 0.02, 0.025), 0.5))
    cols = ["magenta", "cyan", "violet", "pink", "cyan", "yellow", "magenta"]
    for i, x in enumerate(np.linspace(-5.5, 5.5, 7)):
        tube((x, Y0 - 0.2, 0.5 + (i % 2) * 0.4), (x, Y0 - 0.2, 4.2 - (i % 3) * 0.5), 0.035,
             emissive(f"N{i}", NEON[cols[i]], 14.0))
    tube((-4.0, Y0 - 0.25, 3.0), (4.0, Y0 - 0.25, 3.0), 0.03, emissive("NH1", NEON["pink"], 12.0))
    tube((-2.5, Y0 - 0.25, 4.6), (3.5, Y0 - 0.25, 4.6), 0.03, emissive("NH2", NEON["blue"], 12.0))
    sign_panel((1.6, Y0 - 0.3, 2.0), 2.4, 1.2, "screen_ad_a", 3.0)
    sign_panel((-2.6, Y0 - 0.3, 1.7), 1.2, 1.6, "screen_ad_c", 3.0)
    preview.add_area((-3.5, h / 2 + 1.5, 3.5), (-50, 0, 20), 3.0, 450.0, NEON["magenta"])
    preview.add_area((3.5, h / 2 + 1.0, 3.0), (-50, 0, -25), 3.0, 450.0, NEON["cyan"])
    preview.add_area((0, -5, 5.0), (45, 0, 0), 6.0, 160.0, (0.75, 0.82, 1.0))
    preview.add_sun((55, 0, -20), 0.25, angle=3.0, color=(0.6, 0.68, 1.0))
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cd.lens = 35
    cd.clip_start = 0.05
    preview.frame(cam, (-w / 2, -h / 2, 0), (w / 2, h / 2, 0.02), az=0.0, el=el, margin=0.78)
    return cam


def wall_scene(decal):
    w, h = decal["sizeMeters"]
    floorline = "base" in decal.get("tags", [])
    zc = h / 2 - 0.03 if floorline else max(h / 2 + 0.25, 1.6)
    k = 8.0
    wall = mesh("Wall", [(-k, 0, 0), (k, 0, 0), (k, 0, 7), (-k, 0, 7)], [(0, 1, 2, 3)], [(-k, 0), (k, 0), (k, 7), (-k, 7)])
    wall.data.materials.append(surface_material("concrete", 2.0, decal, (0, zc, w, h), wet=0.25, dark=0.5))
    gr = mesh("Ground", [(-k, -k, 0), (k, -k, 0), (k, 0, 0), (-k, 0, 0)], [(0, 1, 2, 3)], [(-k, -k), (k, -k), (k, 0), (-k, 0)])
    gm = surface_material("asphalt", 4.0, {"textures": decal["textures"], "urp": {"normalBlend": 0.0}}, (0, -50, 0.01, 0.01),
                          dark=0.8)
    gr.data.materials.append(gm)
    tube((-w / 2 - 0.6, -0.06, zc + h / 2 + 0.5), (w / 2 + 0.6, -0.06, zc + h / 2 + 0.5), 0.025,
         emissive("NW", NEON["magenta"], 10.0))
    tube((w / 2 + 0.9, -0.06, 0.3), (w / 2 + 0.9, -0.06, zc + h / 2 + 0.3), 0.025, emissive("NV", NEON["cyan"], 10.0))
    preview.add_area((-3.0, -2.5, zc + 1.5), (60, 0, -55), 3.0, 380.0, NEON["magenta"])
    preview.add_area((3.5, -2.0, zc + 0.5), (70, 0, 60), 3.0, 380.0, NEON["cyan"])
    preview.add_area((-1.0, -4.0, zc + 2.5), (65, 0, -12), 4.0, 420.0, (0.82, 0.86, 1.0))
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cd.lens = 35
    cd.clip_start = 0.05
    preview.frame(cam, (-w / 2, -0.01, zc - h / 2), (w / 2, 0.0, zc + h / 2), az=-14.0, el=6.0, margin=0.82)
    return cam


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    size, cols, samples, pats = (560, 420), 3, 40, []
    i = 0
    while i < len(argv):
        if argv[i] == "--size":
            size = tuple(int(x) for x in argv[i + 1].split("x"))
            i += 2
        elif argv[i] == "--cols":
            cols = int(argv[i + 1])
            i += 2
        elif argv[i] == "--samples":
            samples = int(argv[i + 1])
            i += 2
        else:
            pats.append(argv[i])
            i += 1
    decals = json.load(open(os.path.join(envpaths.STATE, "decals.json")))
    names = [n for n in sorted(decals) if not pats or any(fnmatch.fnmatch(n, p) for p in pats)]
    tmp = os.path.join(envpaths.STATE, f"tmp_decal_{os.getpid()}.png")
    by_group = {}
    for gname, gpats in GROUPS:
        for n in names:
            if any(fnmatch.fnmatch(n, p) for p in gpats):
                by_group.setdefault(gname, []).append(n)
    for gname, members in by_group.items():
        tiles = []
        for n in members:
            d = decals[n]
            setup(size, samples)
            if d["projection"] == "wall":
                cam = wall_scene(d)
            else:
                el = 24.0 if ("water" in d["tags"]) else 48.0
                cam = floor_scene(d, el)
            w, h = d["sizeMeters"]
            preview.label(cam, f"{n}  {w:g} x {h:g} m  ({d['pixels'][0]}x{d['pixels'][1]})", size=0.032)
            tiles.append(preview.render_array(tmp))
            print("[render]", n, flush=True)
        p = os.path.join(envpaths.PREVIEWS, f"decals_{gname}_01.png")
        preview.sheet(tiles, cols, p)
        print("[render] sheet", p, flush=True)
    if os.path.exists(tmp):
        os.remove(tmp)


main()
