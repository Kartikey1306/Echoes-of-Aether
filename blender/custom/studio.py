"""Preview / thumbnail studio for the customiser: the exported Unity hero (U_* meshes with its real textures) under
a dark studio with a subtle neon rim (cyan + magenta), EEVEE."""
import bpy, os, math
import numpy as np
from mathutils import Vector
import common as C
import texstage


def _tex(cid, f):
    return os.path.join(C.UNITY_CHARS, C.HEROES[cid]["name"], "Textures", f)


def hair_mat(name, tex_path, tint_hex, cutoff=0.4, rough=0.62, spec=0.16):
    """Preview of the Unity hair material: neutral texture x tint, alpha clip (dithered in EEVEE)."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs[0], out.inputs[0])
    tx = texstage.img_node(nt, tex_path, non_color=False)
    tx.interpolation = "Cubic"
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.inputs["Factor"].default_value = 1.0
    nt.links.new(tx.outputs["Color"], mix.inputs[6])
    t = C.srgb2lin(C.hx(tint_hex))
    mix.inputs[7].default_value = (*t, 1)
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    g = nt.nodes.new("ShaderNodeMath"); g.operation = "GREATER_THAN"; g.inputs[1].default_value = cutoff
    nt.links.new(tx.outputs["Alpha"], g.inputs[0]); nt.links.new(g.outputs[0], b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = rough
    b.inputs["Specular IOR Level"].default_value = spec
    # Unity (URP Lit, cull off) does not flip normals on back faces: emulate by un-flipping Blender's back-face normal
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    k = nt.nodes.new("ShaderNodeMath"); k.operation = "MULTIPLY_ADD"; k.inputs[1].default_value = -2.0; k.inputs[2].default_value = 1.0
    nt.links.new(geo.outputs["Backfacing"], k.inputs[0])
    sc = nt.nodes.new("ShaderNodeVectorMath"); sc.operation = "SCALE"
    nt.links.new(geo.outputs["Normal"], sc.inputs[0]); nt.links.new(k.outputs[0], sc.inputs["Scale"])
    nt.links.new(sc.outputs[0], b.inputs["Normal"])
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "DITHERED"
    m.use_backface_culling = False
    return m


def flat(name, hexcol, rough=0.6, metal=0.0, emit=None, alpha=None, coat=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*C.srgb2lin(C.hx(hexcol)), 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*C.srgb2lin(C.hx(emit[0])), 1)
        b.inputs["Emission Strength"].default_value = emit[1]
    if alpha is not None:
        b.inputs["Alpha"].default_value = alpha
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "BLENDED"
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    return m


def hero_materials(cid, hide_outfit=False, keep=None):
    """Assign preview materials to the U_* meshes and hide the base (full) body + its attachments."""
    Hh = C.HEROES[cid]
    for o in bpy.data.objects:
        if o.type == "MESH" and not o.name.startswith("U_") and o.parent and o.parent.type == "ARMATURE" and "_custom" not in o.name and not o.get("custom"):
            o.hide_render = True
            o.hide_viewport = True
    skin = texstage.preview_mat("prev_Skin", _tex(cid, f"Skin_{Hh['tone']}.png"), _tex(cid, "Skin_Normal.png"), rough=0.5, normal_strength=0.5)
    b = skin.node_tree.nodes.get("Principled BSDF")
    b.inputs["Subsurface Weight"].default_value = 0.15
    b.inputs["Subsurface Radius"].default_value = (0.9, 0.35, 0.2)
    b.inputs["Subsurface Scale"].default_value = 0.006
    b.inputs["Specular IOR Level"].default_value = 0.35
    eyes = texstage.preview_mat("prev_Eyes", _tex(cid, "Eye_brown.png") if os.path.exists(_tex(cid, "Eye_brown.png")) else _tex(cid, "Eye_grey.png"), rough=0.06)
    eyes.node_tree.nodes["Principled BSDF"].inputs["Coat Weight"].default_value = 0.6
    man = os.path.join(C.UNITY_CHARS, Hh["name"], Hh["name"] + ".manifest.json")
    import json
    mf = json.load(open(man))
    tex = mf["textures"]
    def alpha_mat(name, files, tint, cut):
        if not files:
            return flat(name, "#222222")
        return hair_mat(name, _tex(cid, files[0]), tint, cut, rough=0.6, spec=0.2)
    brows = alpha_mat("prev_Brows", tex.get("Brows"), Hh["hair"], 0.45)
    lashes = alpha_mat("prev_Lashes", tex.get("Lashes"), "#0c0a09", 0.35)
    teeth = flat("prev_Teeth", "#d8d0c0", 0.3)
    outfit = flat("prev_Outfit", "#3a3d42", 0.75)
    accent = flat("prev_Accent", "#23252a", 0.7)
    metal = flat("prev_Metal", "#a7adb5", 0.3, 1.0)
    glow = flat("prev_Glow", Hh["glow"], 0.3, 0, (Hh["glow"], 8.0))
    glow2 = flat("prev_Glow2", Hh["glow2"], 0.3, 0, (Hh["glow2"], 8.0))
    armor = flat("prev_Armor", "#8e8a82", 0.45, 0.3)
    for o in bpy.data.objects:
        if o.type != "MESH" or not o.name.startswith("U_"):
            continue
        n = o.name[2:]
        o.hide_render = False
        o.hide_viewport = False
        if n == "Body":
            mats = [skin]
        elif n == "Eyes":
            mats = [eyes]
        elif n == "Brows":
            mats = [brows]
        elif n == "Lashes":
            mats = [lashes]
        elif n in ("Teeth", "Tongue"):
            mats = [teeth]
        else:
            if hide_outfit and (keep is None or n not in keep):
                o.hide_render = True
                o.hide_viewport = True
                continue
            mats = []
            for m in o.data.materials:
                mn = m.name if m else ""
                if "Glow2" in mn:
                    mats.append(glow2)
                elif "Glow" in mn or "Screen" in mn:
                    mats.append(glow)
                elif "Metal" in mn:
                    mats.append(metal)
                elif "Armor" in mn:
                    mats.append(armor)
                elif "Boots" in mn or "Gloves" in mn or "Belt" in mn or "Harness" in mn or "Strap" in mn:
                    mats.append(accent)
                else:
                    mats.append(outfit)
        for i, m in enumerate(mats):
            if i < len(o.data.materials):
                o.data.materials[i] = m
            else:
                o.data.materials.append(m)


def world_and_lights(center, scale=1.0, rim=1.0, yaw=0.0, env=1.0):
    sc = bpy.context.scene
    for o in [o for o in bpy.data.objects if o.get("studio")]:
        bpy.data.objects.remove(o, do_unlink=True)
    sc.render.engine = "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = 48
    for attr, val in (("use_shadows", True), ("use_raytracing", True), ("shadow_ray_count", 2), ("shadow_step_count", 8)):
        if hasattr(sc.eevee, attr):
            try:
                setattr(sc.eevee, attr, val)
            except Exception:
                pass
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.render.film_transparent = False
    w = bpy.data.worlds.get("studio_w") or bpy.data.worlds.new("studio_w")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.006, 0.008, 0.013, 1)
    bg.inputs[1].default_value = env
    sc.world = w
    c = Vector(center)

    def area(name, loc, energy, size, color, target=None):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy * scale * scale
        ld.size = size * scale
        ld.color = color
        o = bpy.data.objects.new(name, ld)
        o["studio"] = 1
        sc.collection.objects.link(o)
        ca, sa = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        lx, ly, lz = loc
        o.location = c + Vector((lx * ca - ly * sa, lx * sa + ly * ca, lz)) * scale
        d = (Vector(target) if target is not None else c) - o.location
        o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return o
    area("st_key", (1.1, -1.5, 0.9), 150, 1.4, (1.0, 0.96, 0.92))
    area("st_fill", (-1.6, -1.0, 0.3), 45, 2.0, (0.82, 0.88, 1.0))
    area("st_rim_c", (-1.0, 1.6, 0.25), 32 * rim, 0.5, (0.4, 0.88, 1.0))
    area("st_rim_m", (1.1, 1.5, 0.2), 20 * rim, 0.5, (1.0, 0.5, 0.85))
    area("st_top", (0.0, 0.3, 1.6), 50, 1.0, (0.9, 0.92, 1.0))
    # backdrop with a soft radial gradient
    bd = bpy.data.objects.get("st_backdrop")
    if bd is None:
        me = bpy.data.meshes.new("st_backdrop")
        me.from_pydata([(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)], [], [(0, 1, 2, 3)])
        me.uv_layers.new(name="UVMap")
        uv = me.uv_layers[0].data
        for i, (u, v) in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
            uv[i].uv = (u, v)
        bd = bpy.data.objects.new("st_backdrop", me)
        sc.collection.objects.link(bd)
        m = bpy.data.materials.new("st_backdrop")
        m.use_nodes = True
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        tc = nt.nodes.new("ShaderNodeTexCoord")
        gr = nt.nodes.new("ShaderNodeTexGradient"); gr.gradient_type = "SPHERICAL"
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Location"].default_value = (0.5, 0.5, 0)
        mp.inputs["Scale"].default_value = (1.6, 1.6, 1)
        sub = nt.nodes.new("ShaderNodeVectorMath"); sub.operation = "SUBTRACT"; sub.inputs[1].default_value = (0.5, 0.5, 0)
        nt.links.new(tc.outputs["UV"], sub.inputs[0])
        nt.links.new(sub.outputs[0], mp.inputs[0])
        nt.links.new(mp.outputs[0], gr.inputs[0])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (0.004, 0.005, 0.008, 1)
        ramp.color_ramp.elements[1].color = (0.03, 0.04, 0.06, 1)
        nt.links.new(gr.outputs[0], ramp.inputs[0])
        nt.links.new(ramp.outputs[0], em.inputs[0])
        nt.links.new(em.outputs[0], out.inputs[0])
        me.materials.append(m)
        bd["studio_keep"] = 1
    return sc


def camera(loc, aim, lens=70.0, res=512):
    sc = bpy.context.scene
    cam = bpy.data.objects.get("st_cam")
    if cam is None:
        cam = bpy.data.objects.new("st_cam", bpy.data.cameras.new("st_cam"))
        sc.collection.objects.link(cam)
    cam.data.lens = lens
    cam.data.clip_start = 0.02
    cam.location = Vector(loc)
    d = Vector(aim) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    # backdrop behind the subject, facing the camera
    bd = bpy.data.objects.get("st_backdrop")
    if bd:
        dist = (Vector(aim) - cam.location).length
        dirn = (Vector(aim) - cam.location).normalized()
        bd.location = Vector(aim) + dirn * max(1.2, dist * 1.2)
        bd.rotation_euler = (-dirn).to_track_quat("-Y", "Z").to_euler()
        s = dist * 2.4 * 36.0 / lens + 1.0
        bd.scale = (s, s, s)
    return cam


def render(path, res=512, out_res=None):
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    if out_res and out_res != res:
        im = bpy.data.images.load(path, check_existing=False)
        im.scale(out_res, out_res)
        im.filepath_raw = path
        im.file_format = "PNG"
        im.save()
        bpy.data.images.remove(im)
    return path


def view(center, yaw_deg, pitch_deg, dist):
    a = math.radians(yaw_deg); p = math.radians(pitch_deg)
    c = Vector(center)
    return c + Vector((math.sin(a) * math.cos(p), -math.cos(a) * math.cos(p), math.sin(p))) * dist
