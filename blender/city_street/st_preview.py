"""Cycles preview of the street kit: a wet neon night street (road, gutter, kerb, pavers, a run of storefronts with the
wall life above them, clutter, overhead cables with lanterns) using the real baked textures.

  Blender -b --factory-startup --python st_preview.py -- [--samples 128] [--res 1600 900] [--shot street|shops|alley]
Writes previews/street_<shot>.png
"""
import json
import math
import os
import random
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stkit  # noqa: E402
import stpaths  # noqa: E402

K = stkit.K
import st_assets_overhead as OV  # noqa: E402
import st_assets_shops as SH  # noqa: E402
import st_assets_street as ST  # noqa: E402

ENV_ART = os.path.join(stpaths.ROOT, "unity", "EchoesOfAether", "Assets", "Art", "Environment")
ENV_MAN = json.load(open(os.path.join(ENV_ART, "manifest.json")))["materials"]
ST_MAN = json.load(open(os.path.join(stpaths.UNITY_ST, "manifest.json")))["materials"]
_cache = {}


def _img(path, colour):
    if not os.path.exists(path):
        return None
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return im


def make_mat(name, wet=0.0):
    key = (name, wet)
    if key in _cache:
        return _cache[key]
    if name in ST_MAN:
        d, root = ST_MAN[name], stpaths.UNITY_ST
    elif name in ENV_MAN:
        d, root = ENV_MAN[name], ENV_ART
    else:
        d, root = {"kind": "param", "baseColor": [0.3, 0.3, 0.3, 1], "smoothness": 0.4}, ENV_ART
    m = bpy.data.materials.new(f"{name}_{wet}")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tex = d.get("textures")
    if tex and d.get("kind") != "param":
        uv = nt.nodes.new("ShaderNodeUVMap")
        mp = nt.nodes.new("ShaderNodeMapping")
        t = d.get("tiling", [1, 1])
        mp.inputs["Scale"].default_value = (t[0], t[1], 1)
        nt.links.new(uv.outputs[0], mp.inputs[0])

        def tx(kind, colour):
            p = tex.get(kind)
            if not p:
                return None
            im = _img(os.path.join(root, p), colour)
            if im is None:
                return None
            n = nt.nodes.new("ShaderNodeTexImage")
            n.image = im
            nt.links.new(mp.outputs[0], n.inputs[0])
            return n
        bc = tx("BaseColor", True)
        if bc:
            nt.links.new(bc.outputs["Color"], b.inputs["Base Color"])
            if d.get("alphaClip"):
                nt.links.new(bc.outputs["Alpha"], b.inputs["Alpha"])
        mk = tx("MaskMap", False)
        rough_sock = None
        if mk:
            sep = nt.nodes.new("ShaderNodeSeparateColor")
            nt.links.new(mk.outputs["Color"], sep.inputs[0])
            nt.links.new(sep.outputs[0], b.inputs["Metallic"])
            inv = nt.nodes.new("ShaderNodeMath")
            inv.operation = "SUBTRACT"
            inv.inputs[0].default_value = 1.0
            nt.links.new(mk.outputs["Alpha"], inv.inputs[1])
            rough_sock = inv.outputs[0]
        if rough_sock is not None and wet > 0:
            # rain: glossier everywhere, mirror puddles from a large noise
            nz = nt.nodes.new("ShaderNodeTexNoise")
            nz.inputs["Scale"].default_value = 0.09
            nz.inputs["Detail"].default_value = 4
            co = nt.nodes.new("ShaderNodeTexCoord")
            nt.links.new(co.outputs["Object"], nz.inputs["Vector"])
            ramp = nt.nodes.new("ShaderNodeMapRange")
            ramp.inputs["From Min"].default_value = 0.56
            ramp.inputs["From Max"].default_value = 0.6
            nt.links.new(nz.outputs["Fac"], ramp.inputs["Value"])
            mul = nt.nodes.new("ShaderNodeMath")
            mul.operation = "MULTIPLY"
            mul.inputs[1].default_value = 1 - 0.55 * wet
            nt.links.new(rough_sock, mul.inputs[0])
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "FLOAT"
            nt.links.new(ramp.outputs[0], mix.inputs["Factor"])
            nt.links.new(mul.outputs[0], mix.inputs["A"])
            mix.inputs["B"].default_value = 0.02
            rough_sock = mix.outputs["Result"]
        if rough_sock is not None:
            nt.links.new(rough_sock, b.inputs["Roughness"])
        nm = tx("Normal", False)
        if nm:
            nn = nt.nodes.new("ShaderNodeNormalMap")
            nt.links.new(nm.outputs["Color"], nn.inputs["Color"])
            nt.links.new(nn.outputs[0], b.inputs["Normal"])
        em = tx("Emission", True)
        if em:
            nt.links.new(em.outputs["Color"], b.inputs["Emission Color"])
            b.inputs["Emission Strength"].default_value = d.get("emissionIntensity", 1.0) * 2.2
    else:
        c = d.get("baseColor", [0.3, 0.3, 0.3, 1])
        lin = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c[:3]]
        b.inputs["Base Color"].default_value = (*lin, 1)
        b.inputs["Metallic"].default_value = d.get("metallic", 0.0)
        b.inputs["Roughness"].default_value = 1 - d.get("smoothness", 0.5)
        if d.get("emission"):
            e = d["emission"]
            b.inputs["Emission Color"].default_value = (*[x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in e], 1)
            b.inputs["Emission Strength"].default_value = d.get("emissionIntensity", 1.0) * 2.0
        if d.get("surface") == "Transparent":
            b.inputs["Alpha"].default_value = c[3] if len(c) > 3 else 0.3
            if d.get("blend") == "Additive":
                b.inputs["Emission Strength"].default_value = d.get("emissionIntensity", 1.0) * 1.5
    _cache[key] = m
    return m


def obj_from_parts(name, wet=0.0, matrix=None):
    ob = K.finalize(name)
    for i, s in enumerate(ob.data.materials):
        ob.data.materials[i] = make_mat(s.name.split(".")[0], wet)
    if matrix is not None:
        ob.matrix_world = matrix
    return ob


def build(fn, name, matrix=None, wet=0.0, **kw):
    K.set_lod(0)
    fn(**kw)
    return obj_from_parts(name, wet, matrix)


def M(x, y, z=0.0, rz=0.0, sx=1.0):
    return Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.radians(rz), 4, "Z") @ Matrix.Diagonal((sx, 1, 1, 1))


def scene(shot):
    K.reset()
    sc = bpy.context.scene
    r = random.Random(4)
    # --- ground: road (y < -4.5), gutter, kerb, pavement (y -4.5 .. 0), building wall at y = 0 (shops face -Y)
    L = 60
    road = K.plane(L, 16, at=(0, -12.5, 0), mat="st_asphalt")
    obj_from_parts("road", wet=1.0)
    K.plane(L, 4.5, at=(0, -2.25, 0.15), mat="st_pavers")
    obj_from_parts("pavement", wet=0.8)
    K.box(L, 0.28, 0.16, at=(0, -4.36, 0.07), mat="st_curb")
    obj_from_parts("kerb", wet=0.5)
    # lane paint
    for x in range(-28, 28, 6):
        K.box(3.0, 0.12, 0.004, at=(x, -12.5, 0.002), mat="st_paint_white")
    K.box(L, 0.1, 0.004, at=(0, -12.34, 0.002), mat="st_paint_yellow")
    K.box(L, 0.1, 0.004, at=(0, -12.66, 0.002), mat="st_paint_yellow")
    obj_from_parts("paint", wet=0.6)
    # building masses with lit windows above the shops, both sides of the street
    for side, y0 in ((1, 0.0), (-1, -25.0)):
        K.box(L, 12, 22, at=(0, y0 + side * 6, 11), mat="concrete_dark")
        for fl in range(5):
            for i in range(-14, 15):
                if r.random() < 0.45:
                    K.box(1.4, 0.05, 1.5, at=(i * 2.0, y0 - side * 0.02, 5.4 + fl * 3.4), mat=r.choice(["window_lit_warm", "window_lit_cool", "glass_dark"]))
    obj_from_parts("buildings", wet=0.2)
    # storefront run on the near side (wall plane y = 0, front toward -Y)
    x = -14.0
    kinds = [("noodle", 6, 0), ("wall", 2, 0), ("pharmacy", 4, 0), ("arcade", 6, 0), ("pawn", 4, 1), ("capsule", 4, 0), ("clinic", 6, 1), ("shuttered", 4, 0)]
    for kind, w, v in kinds:
        build(SH.shop, f"shop_{kind}", M(x + w / 2, 0, 0.15), 0.0, kind=kind, W=float(w), variant=v)
        x += w
    # far side shops (rotated 180 deg)
    x = -12.0
    for kind, w, v in [("pawn", 4, 0), ("noodle", 6, 1), ("capsule", 4, 1), ("arcade", 6, 1), ("pharmacy", 4, 1)]:
        build(SH.shop, f"far_{kind}", M(x + w / 2, -25, 0.15, 180), 0.0, kind=kind, W=float(w), variant=v)
        x += w
    # wall life
    build(ST.fire_escape, "fireescape", M(-6, 0, 4.4 + 3.4))
    for i, (xx, zz) in enumerate(((2.5, 6.0), (9.0, 9.4), (-11, 9.4), (13, 6.0))):
        build(ST.ac_unit, f"ac{i}", M(xx, 0, zz))
    build(OV.hanging_blade, "blade1", M(5.2, 0, 8.4), blade_idx=3)
    build(OV.hanging_blade, "blade2", M(-1.5, 0, 8.0), blade_idx=12, h=3.2, reach=2.3)
    build(OV.hanging_box, "box1", M(11.5, 0, 6.2), square_idx=5)
    build(OV.neon_column, "column", M(-9.5, 0, 5.0), seed=3)
    build(OV.hanging_blade, "blade3", M(2, -25, 8.2, 180), blade_idx=0)
    # clutter on the pavement
    build(ST.food_cart, "cart", M(7.5, -3.0, 0.15, 180))
    build(ST.dumpster, "dumpster", M(-17.5, -1.2, 0.15), colour="metal_painted_green")
    build(ST.bag_pile, "bags", M(-15.5, -1.0, 0.15), n=6, seed=3)
    for xx in (-20.5, -19.3):
        build(ST.bollard_led, f"bollard{xx}", M(xx, -4.0, 0.15))
    build(ST.charge_totem, "totem", M(14.5, -3.9, 0.15, 180))
    build(ST.tram_shelter, "shelter", M(21, -3.2, 0.15, 180))
    build(ST.steam_grate, "grate", M(-3, -9.5, 0.002))
    build(ST.manhole, "manhole", M(10, -11, 0.0))
    # overhead cables with lanterns across the street
    for i, xx in enumerate((-8, 1, 12)):
        for q in range(2 + i % 2):
            pts = []
            for t in range(13):
                f = t / 12
                pts.append((xx + q * 0.2, -f * 25, 9.0 - q * 0.15 - 1.1 * 4 * f * (1 - f)))
            K.tube(pts, 0.03 if q == 0 else 0.018, 6, mat="rubber")
        obj_from_parts(f"cable{i}")
        if i != 1:
            for k in range(1, 9):
                f = k / 9
                build(OV.lantern_single, f"lan{i}{k}", M(xx, -f * 25, 9.0 - 1.1 * 4 * f * (1 - f) - 0.03), mat="emit_st_lantern_red" if i == 0 else "emit_st_lantern_warm")
    # lights: two street lamps (warm sodium-free LED), neon fill from the shops comes from emission
    for xx in (-10, 16):
        ld = bpy.data.lights.new("lamp", "SPOT")
        ld.energy = 2600
        ld.color = (1.0, 0.82, 0.62)
        ld.spot_size = math.radians(110)
        ld.spot_blend = 0.6
        ld.shadow_soft_size = 0.3
        ob = bpy.data.objects.new("lamp", ld)
        ob.location = (xx, -5.5, 7.4)
        sc.collection.objects.link(ob)
        K.cyl(0.1, 7.5, 10, at=(xx, -4.0, 0.15), mat="metal_dark")
        K.box(0.14, 1.6, 0.14, at=(xx, -4.8, 7.45), mat="metal_dark")
        K.box(0.5, 0.9, 0.1, at=(xx, -5.5, 7.35), mat="emit_panel_white")
    obj_from_parts("lamps")
    for (lx, ly, lz, col, e) in ((-11, -2.2, 2.6, (1.0, 0.45, 0.2), 260), (0, -2.0, 2.5, (1.0, 0.25, 0.8), 260), (8, -2.0, 2.4, (0.3, 0.8, 1.0), 200)):
        ld = bpy.data.lights.new("spill", "AREA")
        ld.size = 3.0
        ld.energy = e
        ld.color = col
        ob = bpy.data.objects.new("spill", ld)
        ob.location = (lx, ly, lz)
        ob.rotation_euler = (math.radians(-60), 0, 0)
        sc.collection.objects.link(ob)
    w = bpy.data.worlds.new("night")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.012, 0.016, 0.03, 1)
    bg.inputs["Strength"].default_value = 1.0
    sc.world = w
    # camera
    cam = bpy.data.cameras.new("cam")
    cam.lens = 24
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    if shot == "shops":
        co.location = (-4, -9.5, 1.75)
        target = Vector((4, 0, 2.6))
    elif shot == "alley":
        co.location = (-24, -3.2, 1.7)
        target = Vector((6, -5.5, 3.0))
    else:
        co.location = (-26, -8.0, 1.8)
        target = Vector((10, -6.0, 3.4))
    d = target - co.location
    co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    samples, rx, ry, shot = 128, 1600, 900, "street"
    if "--samples" in argv:
        samples = int(argv[argv.index("--samples") + 1])
    if "--res" in argv:
        i = argv.index("--res")
        rx, ry = int(argv[i + 1]), int(argv[i + 2])
    if "--shot" in argv:
        shot = argv[argv.index("--shot") + 1]
    scene(shot)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for dv in prefs.devices:
            dv.use = True
        sc.cycles.device = "GPU"
    except Exception:
        pass
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = 0.6
    out = os.path.join(stpaths.PREVIEWS, f"street_{shot}.png")
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("[preview]", out)


main()
