"""Blender preview materials that reproduce the Unity setup (CharacterBuilder + CharacterModel runtime tints):
garment composite (outfit/accent/trim from the mask, seam darkening in A, smoothness from G/A), tinted armour and
gloves, skin tone texture with a subsurface approximation, iris tint, brows/lashes desaturated + hair tint."""
import bpy, os
import numpy as np
import gv

GAME = {"outfit": "#55575e", "accent": "#5e2bb8", "armor": "#a8a4b4", "glow": "#ff2bd6", "glow2": "#9b5cff",
        "skin": "#c79878", "hair": "#5a3826", "eyes": "#7a5a32"}
PROPOSED = {"outfit": "#4a4d57", "accent": "#5a3f8c", "armor": "#6a6474", "glow": "#ff2bd6", "glow2": "#9b5cff",
            "skin": "#c79878", "hair": "#2a1a1e", "eyes": "#5a3920"}


def lin(h):
    return tuple(gv.srgb_to_lin(gv.hexrgb(h)).tolist())


def _img(path, colour=False):
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return img


def _new(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs[0], out.inputs[0])
    return m, nt, b


def _tex(nt, path, colour=False):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = _img(path, colour)
    return t


def _normal(nt, b, path, strength=1.0):
    t = _tex(nt, path)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = strength
    nt.links.new(t.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])


def _sep(nt, sock):
    s = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(sock, s.inputs[0])
    return s


def _math(nt, op, a, b=None, val=None):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    if isinstance(a, (int, float)):
        m.inputs[0].default_value = a
    else:
        nt.links.new(a, m.inputs[0])
    if b is not None:
        if isinstance(b, (int, float)):
            m.inputs[1].default_value = b
        else:
            nt.links.new(b, m.inputs[1])
    return m.outputs[0]


def _mix(nt, fac, a, b, blend="MIX"):
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    m.blend_type = blend
    if isinstance(fac, (int, float)):
        m.inputs["Factor"].default_value = fac
    else:
        nt.links.new(fac, m.inputs["Factor"])
    for i, v in ((6, a), (7, b)):
        if isinstance(v, tuple):
            m.inputs[i].default_value = (*v[:3], 1)
        else:
            nt.links.new(v, m.inputs[i])
    return m.outputs[2]


def garment(name, tex_dir, mask, normal, outfit, accent):
    m, nt, b = _new(name)
    t = _tex(nt, os.path.join(tex_dir, mask))
    s = _sep(nt, t.outputs["Color"])
    base = _mix(nt, s.outputs[0], lin(outfit), lin(accent))
    base = _mix(nt, s.outputs[1], base, (0.54, 0.56, 0.59))       # trim colour is linear in the composite
    seam = _math(nt, "MULTIPLY_ADD", t.outputs["Alpha"], -0.549, ) if False else _math(nt, "MULTIPLY", t.outputs["Alpha"], -0.549)
    seam = _math(nt, "ADD", seam, 1.0)
    base = _mix(nt, 1.0, base, (1, 1, 1), "MULTIPLY") if False else base
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(base, mul.inputs[6])
    cr = nt.nodes.new("ShaderNodeCombineColor")
    for i in range(3):
        nt.links.new(seam, cr.inputs[i])
    nt.links.new(cr.outputs[0], mul.inputs[7])
    nt.links.new(mul.outputs[2], b.inputs["Base Color"])
    # smoothness = (70 + 110 G - 40 A) / 255  -> roughness
    sm = _math(nt, "MULTIPLY", s.outputs[1], 110 / 255)
    sm = _math(nt, "ADD", sm, 70 / 255)
    sa = _math(nt, "MULTIPLY", t.outputs["Alpha"], -40 / 255)
    sm = _math(nt, "ADD", sm, sa)
    rough = _math(nt, "SUBTRACT", 1.0, sm)
    nt.links.new(rough, b.inputs["Roughness"])
    b.inputs["Specular IOR Level"].default_value = 0.4
    b.inputs["Sheen Weight"].default_value = 0.0
    _normal(nt, b, os.path.join(tex_dir, normal))
    return m


def lit(name, tex_dir, files, tint=None):
    m, nt, b = _new(name)
    bc = _tex(nt, os.path.join(tex_dir, files[0]), True)
    mm = _tex(nt, os.path.join(tex_dir, files[2]))
    s = _sep(nt, mm.outputs["Color"])
    col = bc.outputs["Color"]
    if tint:
        col = _mix(nt, 1.0, col, lin(tint), "MULTIPLY")
    col = _mix(nt, s.outputs[1], (0, 0, 0), col)       # occlusion (G) darkens (Unity applies it to ambient only)
    nt.links.new(col, b.inputs["Base Color"])
    nt.links.new(s.outputs[0], b.inputs["Metallic"])
    nt.links.new(_math(nt, "SUBTRACT", 1.0, mm.outputs["Alpha"]), b.inputs["Roughness"])
    _normal(nt, b, os.path.join(tex_dir, files[1]))
    return m


def flat(name, colour, metal=0.0, rough=0.4, emit=None, strength=6.0):
    m, nt, b = _new(name)
    b.inputs["Base Color"].default_value = (*lin(colour), 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*lin(emit), 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


def skin(name, tex_dir, tone_file, normal, maskmap, tint=(1, 1, 1)):
    m, nt, b = _new(name)
    bc = _tex(nt, os.path.join(tex_dir, tone_file), True)
    col = _mix(nt, 1.0, bc.outputs["Color"], tuple(tint), "MULTIPLY")
    nt.links.new(col, b.inputs["Base Color"])
    mm = _tex(nt, os.path.join(tex_dir, maskmap))
    nt.links.new(_math(nt, "SUBTRACT", 1.0, mm.outputs["Alpha"]), b.inputs["Roughness"])
    b.inputs["Subsurface Weight"].default_value = 0.22
    b.inputs["Subsurface Radius"].default_value = (1.0, 0.38, 0.22)
    b.inputs["Subsurface Scale"].default_value = 0.0045
    b.inputs["Specular IOR Level"].default_value = 0.45
    b.inputs["Coat Weight"].default_value = 0.08
    b.inputs["Coat Roughness"].default_value = 0.35
    _normal(nt, b, os.path.join(tex_dir, normal), 0.8)
    return m


def alpha_card(name, path, colour, cutoff=0.4, darken=0.0):
    m, nt, b = _new(name)
    t = _tex(nt, path, True)
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(t.outputs["Color"], bw.inputs[0])
    c = np.array(lin(colour)) * (1 - darken)
    # like the game (CharacterBuilder.Desaturated + tint): strand luminance, mean normalised to ~0.51 linear,
    # times the hair colour
    k = _math(nt, "MULTIPLY", bw.outputs["Val"], 2.4)
    tint = _mix(nt, 1.0, (1, 1, 1), tuple(c.tolist()), "MULTIPLY")
    col = nt.nodes.new("ShaderNodeMix")
    col.data_type = "RGBA"
    col.blend_type = "MULTIPLY"
    col.inputs["Factor"].default_value = 1.0
    cr = nt.nodes.new("ShaderNodeCombineColor")
    for i in range(3):
        nt.links.new(k, cr.inputs[i])
    nt.links.new(cr.outputs[0], col.inputs[6])
    nt.links.new(tint, col.inputs[7])
    nt.links.new(col.outputs[2], b.inputs["Base Color"])
    gt = _math(nt, "GREATER_THAN", t.outputs["Alpha"], cutoff)
    nt.links.new(gt, b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = 0.6
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "DITHERED"
    m.use_backface_culling = False
    return m


def eye(name, path, iris_hex):
    """Eye with the game's iris tint (lum * 2.1 * colour inside the iris ellipse) baked into a preview image."""
    img = gv.read_image(path)
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    du = (xx + 0.5) / w - 0.5
    dv = (yy + 0.5) / h - 0.5
    d = np.sqrt(4 * du * du + dv * dv)
    k = 1 - gv.ss(0.075, 0.095, d)
    lum = img[..., :3].mean(-1)
    c = gv.srgb_to_lin(gv.hexrgb(iris_hex))
    # texture values are sRGB-encoded: tint in Unity happens on the sRGB-read texel -> approximate in linear
    tinted = np.clip(lum[..., None] * 2.1 * gv.hexrgb(iris_hex), 0, 1)
    out = img[..., :3] * (1 - k[..., None]) + tinted * k[..., None]
    p2 = path.replace(".png", "_prev.png")
    gv.write_image(out, p2)
    m, nt, b = _new(name)
    t = _tex(nt, p2, True)
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.08
    b.inputs["Coat Weight"].default_value = 1.0
    b.inputs["Coat Roughness"].default_value = 0.02
    return m


def apply_all(objs, tex_dir, atl, pal=None, hair_png=None):
    pal = pal or GAME
    mats = {}
    if "Garment_Top" in atl:
        mats["Garment_Top"] = garment("pv_Top", tex_dir, atl["Garment_Top"]["mask"], atl["Garment_Top"]["normal"], pal["outfit"], pal["accent"])
    if "Garment_Pants" in atl:
        o88 = "#%02x%02x%02x" % tuple(int(c * 255 * 0.88) for c in gv.hexrgb(pal["outfit"]))
        mats["Garment_Pants"] = garment("pv_Pants", tex_dir, atl["Garment_Pants"]["mask"], atl["Garment_Pants"]["normal"], o88, pal["accent"])
    if "Armor" in atl:
        mats["Armor"] = lit("pv_Armor", tex_dir, atl["Armor"], pal["armor"])
    if "Cloth_Gear" in atl:
        mats["Cloth_Gear"] = lit("pv_Gear", tex_dir, atl["Cloth_Gear"])
    if "Boots" in atl:
        mats["Boots"] = lit("pv_Boots", tex_dir, atl["Boots"])
    if "Gloves" in atl:
        g75 = "#%02x%02x%02x" % tuple(int(c * 255 * 0.75) for c in gv.hexrgb(pal["outfit"]))
        mats["Gloves"] = lit("pv_Gloves", tex_dir, atl["Gloves"], g75)
    if "Skin" in atl:
        mats["Skin"] = skin("pv_Skin", tex_dir, atl["Skin"]["skins"]["medium"], atl["Skin"]["normal"], atl["Skin"]["maskMap"])
    mats["Metal"] = flat("pv_Metal", "#a7adb5", 1.0, 0.32)
    mats["Glow"] = flat("pv_Glow", pal["glow"], 0, 0.3, pal["glow"], 8)
    mats["Glow2"] = flat("pv_Glow2", pal["glow2"], 0, 0.3, pal["glow2"], 8)
    mats["Screen"] = flat("pv_Screen", pal["glow"], 0, 0.2, pal["glow"], 3)
    if os.path.exists(os.path.join(tex_dir, "Eye_grey.png")):
        mats["Eyes"] = eye("pv_Eyes", os.path.join(tex_dir, "Eye_grey.png"), pal["eyes"])
    for nm, f, dk, cut in (("Brows", "Brows_giva.png", 0.15, 0.4), ("Lashes", "Lashes_eyelashes03.png", 0.5, 0.3)):
        if os.path.exists(os.path.join(tex_dir, f)):
            mats[nm] = alpha_card("pv_" + nm, os.path.join(tex_dir, f), pal["hair"], cut, dk)
    for o in objs:
        me = o.data
        for i, slot in enumerate(o.material_slots):
            if slot.material and slot.material.name in mats:
                slot.material = mats[slot.material.name]
    return mats
