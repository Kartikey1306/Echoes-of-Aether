"""Build, bake, texture, export and preview the Echoes of Aether weapons (Blender 5.2, headless).

  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python blender/weapons/build_weapons.py -- [hero] [enemy] [fx] [--no-preview]

Outputs
  unity/EchoesOfAether/Assets/Resources/Weapons/<asset>.fbx      game meshes (+ anchor empties: muzzle, eject, claw_N...)
  unity/EchoesOfAether/Assets/Art/Weapons/Textures/<atlas>_*.png  BaseColor / MetalSmooth (R metal, A smoothness) /
                                                                  Occlusion / Normal (OpenGL, tangent space)
  blender/weapons/out/<group>.blend, stats.json                   sources and triangle counts
  blender/weapons/previews/*.png                                  Cycles look-dev renders of the final game assets
Everything is modelled procedurally in code (wkit / w_hero / w_enemy / w_fx); textures are baked from the high poly and
composed from the baked maps (no image inputs).
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import wkit as W  # noqa: E402
import w_enemy  # noqa: E402
import w_fx  # noqa: E402
import w_hero  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
UNITY = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets")
RES = os.path.join(UNITY, "Resources", "Weapons")
TEX = os.path.join(UNITY, "Art", "Weapons", "Textures")
OUT = os.path.join(HERE, "out")
PREV = os.path.join(HERE, "previews")


def lin(h):
    c = [((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


# --------------------------------------------------------------------------- palettes (linear colours)
HERO_PAL = [
    dict(name="gunmetal", color=(0.026, 0.028, 0.032), metal=0.85, rough=0.34, wear_color=(0.42, 0.43, 0.45), wear_metal=1.0, wear_rough=0.2),
    dict(name="polymer", color=(0.018, 0.019, 0.022), metal=0.0, rough=0.62, wear_color=(0.06, 0.06, 0.065), wear_metal=0.0, wear_rough=0.48, wear=0.5),
    dict(name="alloy", color=(0.34, 0.35, 0.38), metal=1.0, rough=0.24, wear_color=(0.62, 0.62, 0.64), wear_rough=0.14),
    dict(name="accent_teal", color=(0.008, 0.10, 0.12), metal=0.65, rough=0.3, wear_color=(0.45, 0.46, 0.48), wear_rough=0.2),
    dict(name="strap", color=(0.022, 0.022, 0.024), metal=0.0, rough=0.84, wear_color=(0.05, 0.05, 0.05), wear_metal=0.0, wear_rough=0.8, wear=0.25),
    dict(name="cavity", color=(0.004, 0.004, 0.005), metal=0.2, rough=0.75, wear=0.0, grime=0.0),
    dict(name="armor_graphite", color=(0.040, 0.041, 0.047), metal=0.35, rough=0.4, wear_color=(0.36, 0.36, 0.38), wear_rough=0.22),
    dict(name="accent_violet", color=(0.085, 0.020, 0.150), metal=0.45, rough=0.32, wear_color=(0.40, 0.40, 0.42), wear_rough=0.2),
    dict(name="glow", color=(0.8, 0.9, 1.0), metal=0.0, rough=0.3, wear=0.0, grime=0.0),
]
ENEMY_PAL = [
    dict(name="enemy_steel", color=(0.032, 0.034, 0.038), metal=0.85, rough=0.44, wear_color=(0.40, 0.40, 0.42), wear_rough=0.25),
    dict(name="enemy_shell", color=(0.066, 0.072, 0.083), metal=0.55, rough=0.46, wear_color=(0.42, 0.42, 0.44), wear_rough=0.24),
    dict(name="alloy", color=(0.32, 0.33, 0.36), metal=1.0, rough=0.26, wear_color=(0.6, 0.6, 0.62), wear_rough=0.15),
    dict(name="hazard", color=(0.60, 0.28, 0.012), metal=0.1, rough=0.5, wear_color=(0.30, 0.30, 0.32), wear_rough=0.3, stripes=(0.012, 0.012, 0.014)),
    dict(name="blade_steel", color=(0.26, 0.27, 0.29), metal=1.0, rough=0.17, wear_color=(0.55, 0.55, 0.57), wear_rough=0.1),
    dict(name="cavity", color=(0.004, 0.004, 0.005), metal=0.2, rough=0.75, wear=0.0, grime=0.0),
    dict(name="enemy_glow", color=(1.0, 0.5, 0.3), metal=0.0, rough=0.3, wear=0.0, grime=0.0),
]
GLOW_SLOTS = {"glow", "enemy_glow"}


def assign_ids(pal):
    n = len(pal)
    for i, p in enumerate(pal):
        h = i / n
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(h, 0.9, 0.9 if i % 2 == 0 else 0.6)
        p["id"] = (r, g, b)
    return pal


def make_mats(pal):
    mats = {}
    for p in pal:
        mats[p["name"]] = W.material(p["name"], p["color"], p["metal"], p["rough"])
    return mats


# --------------------------------------------------------------------------- group build
def build_group(group, specs, pal, size, cage, bevel, ao_dist, weights=None, seed=7):
    """specs: list of (part, location). Returns {name: low_object} with baked textures written."""
    W.reset()
    assign_ids(pal)
    mats = make_mats(pal)
    lows, pairs, highs, parts = [], [], [], {}
    for part, loc, sc in specs:
        lo = W.make_low(part, mats, loc)
        hi = W.make_high(part, mats, loc, bevel=bevel * sc)
        lows.append(lo)
        highs.append(hi)
        pairs.append((lo, hi, cage * sc))
        parts[part.name] = (part, lo, hi)
    W.uv_atlas(lows, weights)
    for lo in lows:
        W.triangulate(lo)
    t0 = time.time()
    baked = W.bake_atlas(pairs, size, {p["name"]: p["id"] for p in pal}, ao_dist=ao_dist)
    print("[weapons] %s bake %.1fs" % (group, time.time() - t0))
    tex = W.compose(baked, pal, size, seed=seed)
    # hazard stripes (diagonal in UV space) on palette entries that ask for them
    stripe_tex(tex, baked, pal, size)
    for k, srgb in (("BaseColor", True), ("MetalSmooth", False), ("Occlusion", False), ("Normal", False)):
        W.save_png(tex[k], os.path.join(TEX, "%s_%s.png" % (group, k)), srgb=srgb)
    print("[weapons] %s textures written" % group)
    return parts, tex, mats


def stripe_tex(tex, baked, pal, size):
    idmap = baked["EMIT"][..., :3]
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / size
    for p in pal:
        if "stripes" not in p:
            continue
        d = ((idmap - np.array(p["id"], np.float32)) ** 2).sum(-1)
        m = d < 0.02
        band = (np.floor((xx + yy) * size / 22.0) % 2) == 0
        sel = m & band
        dark = np.array(p["stripes"], np.float32)
        tex["BaseColor"][..., :3][sel] = tex["BaseColor"][..., :3][sel] * 0.15 + dark * 0.85


# --------------------------------------------------------------------------- export helpers
def finalize(lo, part, pbr_name, glow_name, mirror=False, name=None):
    """Collapse material slots to <pbr> + <glow>, optionally mirror (x), attach anchor empties."""
    me = lo.data
    slots = [m.name for m in me.materials]
    pbr = bpy.data.materials.get(pbr_name) or bpy.data.materials.new(pbr_name)
    glw = bpy.data.materials.get(glow_name) or bpy.data.materials.new(glow_name)
    remap = [1 if s in GLOW_SLOTS else 0 for s in slots]
    idx = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", idx)
    idx = np.array([remap[i] for i in idx], np.int32)
    me.materials.clear()
    me.materials.append(pbr)
    me.materials.append(glw)
    me.polygons.foreach_set("material_index", idx)
    if not any(idx == 1):
        pass
    if mirror:
        bm = bmesh.new()
        bm.from_mesh(me)
        for v in bm.verts:
            v.co.x = -v.co.x
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(40))
    if name:
        lo.name = name
        me.name = name
    lo.location = (0, 0, 0)
    empties = W.add_empties(part, lo)
    if mirror:
        for e in empties:
            e.location.x = -e.location.x
    return lo


def duplicate(ob, name):
    c = ob.copy()
    c.data = ob.data.copy()
    c.name = name
    bpy.context.scene.collection.objects.link(c)
    return c


# --------------------------------------------------------------------------- previews
def preview_material(group, mats_name, glow_color, glow_strength=8.0):
    m = bpy.data.materials.get(mats_name)
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])

    def img(kind, data):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(os.path.join(TEX, "%s_%s.png" % (group, kind)), check_existing=True)
        if data:
            t.image.colorspace_settings.name = "Non-Color"
        return t
    bc, ms, oc, nm = img("BaseColor", False), img("MetalSmooth", True), img("Occlusion", True), img("Normal", True)
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(bc.outputs["Color"], mul.inputs[6])
    nt.links.new(oc.outputs["Color"], mul.inputs[7])
    nt.links.new(mul.outputs[2], bsdf.inputs["Base Color"])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(ms.outputs["Color"], sep.inputs[0])
    nt.links.new(sep.outputs[0], bsdf.inputs["Metallic"])
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    nt.links.new(ms.outputs["Alpha"], inv.inputs[1])
    nt.links.new(inv.outputs[0], bsdf.inputs["Roughness"])
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nm.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])


def glow_material(name, color, strength):
    m = bpy.data.materials.get(name)
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])


def studio(target_objs, name, views, res=(1280, 800), extra_glow=None):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 96
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    world = sc.world or bpy.data.worlds.new("w")
    sc.world = world
    try:
        world.use_nodes = True
    except AttributeError:
        pass
    bg = world.node_tree.nodes.get("Background") or world.node_tree.nodes.new("ShaderNodeBackground")
    wo = world.node_tree.nodes.get("World Output") or world.node_tree.nodes.new("ShaderNodeOutputWorld")
    if not bg.outputs[0].links:
        world.node_tree.links.new(bg.outputs[0], wo.inputs["Surface"])
    bg.inputs[0].default_value = (0.010, 0.012, 0.016, 1)
    bg.inputs[1].default_value = 1.0
    # bounds
    pts = []
    for o in target_objs:
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    ctr = (mn + mx) / 2
    rad = (mx - mn).length / 2
    # lights
    for o in [o for o in sc.objects if o.type in ("LIGHT", "CAMERA") or o.name.startswith("floor")]:
        bpy.data.objects.remove(o, do_unlink=True)
    def light(nm, kind, loc, energy, color, size):
        ld = bpy.data.lights.new(nm, kind)
        ld.energy = energy
        ld.color = color
        if kind == "AREA":
            ld.size = size
        lo = bpy.data.objects.new(nm, ld)
        sc.collection.objects.link(lo)
        lo.location = loc
        d = ctr - Vector(loc)
        lo.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return lo
    k = rad * 6
    light("key", "AREA", ctr + Vector((-1.2, -1.6, 1.4)) * k / 2, 260 * (rad / 0.15) ** 2, (1.0, 0.95, 0.9), rad * 3)
    light("rim", "AREA", ctr + Vector((1.6, 1.2, 0.8)) * k / 2, 420 * (rad / 0.15) ** 2, (0.55, 0.8, 1.0), rad * 2)
    light("rim2", "AREA", ctr + Vector((-1.4, 1.5, -0.2)) * k / 2, 260 * (rad / 0.15) ** 2, (1.0, 0.45, 0.85), rad * 2)
    light("fill", "AREA", ctr + Vector((0.4, -2.0, -0.6)) * k / 2, 40 * (rad / 0.15) ** 2, (0.7, 0.75, 0.9), rad * 4)
    # floor
    bpy.ops.mesh.primitive_plane_add(size=rad * 40, location=(ctr.x, ctr.y, mn.z - rad * 0.05))
    fl = bpy.context.active_object
    fl.name = "floor"
    fm = bpy.data.materials.new("floor_mat")
    fb = fm.node_tree.nodes.get("Principled BSDF")
    fb.inputs["Base Color"].default_value = (0.02, 0.022, 0.026, 1)
    fb.inputs["Roughness"].default_value = 0.35
    fb.inputs["Metallic"].default_value = 0.2
    fl.data.materials.append(fm)
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 70
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    for vi, (az, el, zoom) in enumerate(views):
        a, e = math.radians(az), math.radians(el)
        dist = rad * 3.6 * zoom
        cam.location = ctr + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dist
        cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam_d.clip_start = rad * 0.01
        cam_d.clip_end = rad * 100
        sc.render.filepath = os.path.join(PREV, "%s_%d.png" % (name, vi))
        bpy.ops.render.render(write_still=True)
        print("[weapons] preview", sc.render.filepath)
    bpy.data.objects.remove(fl, do_unlink=True)


def isolate(objs):
    keep = set(objs)
    for o in bpy.context.scene.objects:
        if o.type == "MESH" and not o.name.startswith("floor"):
            o.hide_render = o not in keep
            o.hide_viewport = False


# --------------------------------------------------------------------------- groups
def group_hero(preview):
    specs = [(w_hero.pistol(), (0, 0, 0), 1.0), (w_hero.holster(), (0.6, 0, 0), 1.0), (w_hero.emitter(), (1.2, 0, 0), 1.0),
             (w_hero.gauntlet(), (1.8, 0, 0), 1.0), (w_hero.casing(), (2.4, 0, 0), 1.0)]
    parts, tex, mats = build_group("hero", specs, HERO_PAL, 2048, cage=0.0035, bevel=0.0011, ao_dist=0.03, seed=5)
    stats = {}
    out_objs = {}
    for name, (part, lo, hi) in parts.items():
        hi.hide_render = True
        hi.hide_viewport = True
    for name, (part, lo, hi) in parts.items():
        if name == "giva_gauntlet":
            r = duplicate(lo, "giva_gauntlet_R")
            finalize(r, part, "hero_pbr", "hero_glow", mirror=True, name="giva_gauntlet_R")
            finalize(lo, part, "hero_pbr", "hero_glow", name="giva_gauntlet_L")
            out_objs["giva_gauntlet"] = [lo, r]
        else:
            finalize(lo, part, "hero_pbr", "hero_glow", name=name)
            out_objs[name] = [lo]
    for name, objs in out_objs.items():
        W.export_fbx(os.path.join(RES, name + ".fbx"), objs)
        stats[name] = {o.name: W.tri_count(o) for o in objs}
        print("[weapons] exported", name, stats[name])
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "hero.blend"), compress=True)
    if preview:
        preview_material("hero", "hero_pbr", None)
        glow_material("hero_glow", (0.35, 0.85, 1.0), 12.0)
        spread = {"kael_pistol": (0, 0, 0), "kael_holster": (0.6, 0, 0), "kael_emitter": (1.2, 0, 0), "giva_gauntlet": (1.8, 0, 0), "energy_cell": (2.4, 0, 0)}
        for name, objs in out_objs.items():
            for i, o in enumerate(objs):
                o.location = Vector(spread[name]) + Vector((0.14 * i, 0, 0))
            isolate(objs)
            if name == "giva_gauntlet":
                glow_material("hero_glow", (1.0, 0.3, 0.85), 12.0)
            else:
                glow_material("hero_glow", (0.35, 0.85, 1.0), 12.0)
            studio(objs, name, [(35, 18, 1.0), (-120, 22, 1.0)])
    return stats


def group_enemy(preview):
    specs = [(w_enemy.drone_blaster(), (0, 0, 0), 1.0), (w_enemy.sentinel_blade(), (1.5, 0, 0), 1.0),
             (w_enemy.guardian_cannon(), (4, 0, 0), 8.0), (w_enemy.guardian_blade_mount(), (8, 0, 0), 8.0),
             (w_enemy.guardian_blade(), (11, 0, 0), 8.0)]
    weights = {"guardian_cannon": 0.45, "guardian_blade_mount": 0.45, "guardian_blade": 0.45}
    parts, tex, mats = build_group("enemy", specs, ENEMY_PAL, 2048, cage=0.004, bevel=0.0028, ao_dist=0.08, weights=weights, seed=9)
    stats = {}
    out_objs = {}
    for name, (part, lo, hi) in parts.items():
        hi.hide_render = True
        hi.hide_viewport = True
        finalize(lo, part, "enemy_pbr", "enemy_glow", name=name)
        out_objs[name] = [lo]
    groups = {"drone_blaster": ["drone_blaster"], "sentinel_blade": ["sentinel_blade"],
              "guardian_weapons": ["guardian_cannon", "guardian_blade_mount", "guardian_blade"]}
    for fname, names in groups.items():
        objs = [out_objs[n][0] for n in names]
        W.export_fbx(os.path.join(RES, fname + ".fbx"), objs)
        stats[fname] = {o.name: W.tri_count(o) for o in objs}
        print("[weapons] exported", fname, stats[fname])
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "enemy.blend"), compress=True)
    if preview:
        preview_material("enemy", "enemy_pbr", None)
        glow_material("enemy_glow", (1.0, 0.35, 0.18), 14.0)
        for fname, names in groups.items():
            objs = [out_objs[n][0] for n in names]
            x = 0.0
            for o in objs:
                o.location = (x, 0, 0)
                x += 0.9 if fname == "guardian_weapons" else 0.0
            if fname == "guardian_weapons":
                objs[1].location = (0.9, 0, 0)
                objs[2].location = (0.9, 0, 0)
                glow_material("enemy_glow", (0.3, 0.85, 1.0), 14.0)
            else:
                glow_material("enemy_glow", (1.0, 0.35, 0.18), 14.0)
            isolate(objs)
            studio(objs, fname, [(35, 18, 1.0), (-120, 22, 1.0)])
    return stats


def group_fx(preview):
    W.reset()
    objs = w_fx.build_all()
    W.export_fbx(os.path.join(RES, "weapon_fx.fbx"), objs, vertex_colors=True)
    stats = {"weapon_fx": {o.name: W.tri_count(o) for o in objs}}
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "fx.blend"), compress=True)
    if preview:
        m = bpy.data.materials.get("hardlight")
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (0.3, 0.8, 1.0, 1)
        em.inputs["Strength"].default_value = 6.0
        lw = nt.nodes.new("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.35
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lw.outputs["Facing"], mix.inputs[0])
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        add = nt.nodes.new("ShaderNodeAddShader")
        em2 = nt.nodes.new("ShaderNodeEmission")
        em2.inputs["Color"].default_value = (0.3, 0.8, 1.0, 1)
        em2.inputs["Strength"].default_value = 1.5
        nt.links.new(mix.outputs[0], add.inputs[0])
        nt.links.new(em2.outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], out.inputs["Surface"])
        lay = {"kael_blade_hull": (0, 0, 0), "kael_blade_core": (0, 0, 0), "giva_claw_hull": (0.3, 0, 0), "giva_claw_core": (0.3, 0, 0)}
        objs2 = [o for o in objs if o.name in lay]
        for o in objs2:
            o.location = lay[o.name]
        isolate(objs2)
        studio(objs2, "hardlight", [(60, 15, 0.8), (100, 5, 0.45)])
    return stats


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    flags = {a for a in argv if a.startswith("--")}
    groups = [a for a in argv if not a.startswith("--")] or ["hero", "enemy", "fx"]
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PREV, exist_ok=True)
    os.makedirs(RES, exist_ok=True)
    os.makedirs(TEX, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    stats_path = os.path.join(OUT, "stats.json")
    stats = json.load(open(stats_path)) if os.path.exists(stats_path) else {}
    preview = "--preview" in flags     # look-dev renders live in preview_weapons.py (imports the exported FBX)
    for g in groups:
        t0 = time.time()
        stats.update({"hero": group_hero, "enemy": group_enemy, "fx": group_fx}[g](preview))
        print("[weapons] group %s done in %.1fs" % (g, time.time() - t0))
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
