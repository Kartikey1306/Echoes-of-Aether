"""Kael v2 preview materials (mirroring the Unity setup: skin tint from Appearance.Skin, grey-tinted brows/lashes/hair,
garment composite with the default palette, armour/gloves tints, emissive glows) and standard Cycles render sets.

  blender -b <blend> --python preview_k2.py -- <tag> [--shots face,face34,profile,front,q34,back,game] [--light menu|portrait|night]
"""
import bpy, sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
from mathutils import Vector, Matrix
import texbake as TB, texstage as TS

PAL = {"outfit": "#5c5848", "accent": "#1f2126", "armor": "#c9cdd3", "glow": "#00e5ff", "glow2": "#ff2bd6", "skin": "#b98a6e",
       "hair": "#4f3a2e", "eyes": "#5b3a22"}
TEX = K.TEX
CATALOG = os.path.join(K.UNITY, "Assets", "Resources", "Characters", "Custom")
OLD_HEAD = np.array((0.0, -0.0464, 1.6851))   # committed Kael head bone (catalog fit reference, blender/custom/cache/kael_ref.json)


def hexc(h):
    return np.array([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)])


def skin_tint(hexs):
    """CharacterModel.ApplySkin: texture choice + tint (sRGB)."""
    c = hexc(hexs)
    lum = c @ np.array((0.3, 0.59, 0.11))
    refs = [0.78, 0.62, 0.5, 0.3]
    best = int(np.argmin([abs(r - lum) for r in refs]))
    k = float(np.clip(lum / refs[best], 0.75, 1.25))
    tint = c / max(lum, 0.05) * lum * k
    tint = 1 + (tint / max(tint.max(), 1e-3) - 1) * 0.35
    tint = tint * float(np.clip(k, 0.85, 1.1))
    return ["light", "medium", "tan", "dark"][best], tint


def _nodes(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs[0], out.inputs[0])
    return m, nt, b


def skin_material():
    tone, tint = skin_tint(PAL["skin"])
    m, nt, b = _nodes("Skin")
    bc = TS.img_node(nt, os.path.join(TEX, f"Skin_{tone}.png"), non_color=False)
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.inputs["Factor"].default_value = 1.0
    nt.links.new(bc.outputs["Color"], mix.inputs[6])
    mix.inputs[7].default_value = (*[c ** 2.2 for c in tint], 1)
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    nt.links.new(mix.outputs[2], b.inputs["Subsurface Radius"]) if False else None
    nn = TS.img_node(nt, os.path.join(TEX, "Skin_Normal.png"))
    nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = 1.0
    nt.links.new(nn.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs[0], b.inputs["Normal"])
    mm = TS.img_node(nt, os.path.join(TEX, "Skin_MaskMap.png"))
    inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    nt.links.new(mm.outputs["Alpha"], inv.inputs[1])
    nt.links.new(inv.outputs[0], b.inputs["Roughness"])
    b.inputs["Subsurface Weight"].default_value = 0.2
    b.inputs["Subsurface Radius"].default_value = (1.0, 0.38, 0.22)
    b.inputs["Subsurface Scale"].default_value = 0.0045
    b.inputs["Specular IOR Level"].default_value = 0.45
    return m


def eye_material():
    m, nt, b = _nodes("Eyes")
    img = TB.read_image(os.path.join(TEX, "Eye_grey.png"))
    h_, w_ = img.shape[:2]
    yy, xx = np.mgrid[0:h_, 0:w_]
    dd = np.sqrt(((xx + 0.5) / w_ - 0.5) ** 2 * 4 + ((yy + 0.5) / h_ - 0.5) ** 2)
    irisk = 1 - K.ss(0.075, 0.095, dd)
    lum = img[..., :3].mean(-1)
    ic = hexc(PAL["eyes"])
    eimg = img[..., :3] * (1 - irisk[..., None]) + (lum[..., None] * ic * 1.45) * irisk[..., None]   # CharacterModel.ApplyEyes
    p = os.path.join(TEX, "prev_eye.png")
    TB.write_png(np.clip(eimg, 0, 1), p, "RGB")
    bc = TS.img_node(nt, p, non_color=False)
    nt.links.new(bc.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.08
    b.inputs["Coat Weight"].default_value = 0.5
    return m


def card_material(name, src, color, cutoff, rough=0.5):
    """Grey-normalised alpha-tested card (CharacterBuilder.Desaturated + tint)."""
    im = TB.read_image(src)
    lum = im[..., :3].mean(-1); al = im[..., 3]
    mean = lum[al > 0.5].mean() if (al > 0.5).any() else 0.5
    grey = np.clip(lum / max(mean, 1e-3) * 0.745, 0, 1)
    out = os.path.join(TEX, f"prev_{name}.png")
    TB.write_png(np.concatenate([grey[..., None] * color, al[..., None]], -1), out, "RGBA")
    m, nt, b = _nodes(name)
    tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = bpy.data.images.load(out, check_existing=False)
    nt.links.new(tx.outputs["Color"], b.inputs["Base Color"])
    g = nt.nodes.new("ShaderNodeMath"); g.operation = "GREATER_THAN"; g.inputs[1].default_value = cutoff
    nt.links.new(tx.outputs["Alpha"], g.inputs[0]); nt.links.new(g.outputs[0], b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = rough
    b.inputs["Specular IOR Level"].default_value = 0.3
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "DITHERED"
    m.use_backface_culling = False
    return m


def holo_material(strength=3.0 * 0.45 * 2.2):
    """Preview of EOA/HoloSleeve: additive (transparent + emission) cyan pattern from Kael_Holo.png."""
    path = os.path.join(TEX, "Kael_Holo.png")
    m = bpy.data.materials.get("Holo") or bpy.data.materials.new("Holo")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    em = nt.nodes.new("ShaderNodeEmission")
    add = nt.nodes.new("ShaderNodeAddShader")
    em.inputs["Color"].default_value = (*(hexc(PAL["glow"]) ** 2.2), 1)
    if os.path.exists(path):
        tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = bpy.data.images.load(path, check_existing=True)
        tx.image.colorspace_settings.name = "sRGB"
        mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = strength
        nt.links.new(tx.outputs["Alpha"], mul.inputs[0]); nt.links.new(mul.outputs[0], em.inputs["Strength"])
    else:
        em.inputs["Strength"].default_value = strength * 0.3
    nt.links.new(tr.outputs[0], add.inputs[0]); nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs[0])
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    m.use_backface_culling = False
    return m


def setup_materials():
    skin_material()
    holo_material()
    eye_material()
    # CharacterModel: Brows = lerp(hair, skin, 0.25), Lashes = lerp(hair, black, 0.35); card_material takes sRGB tints
    hc = hexc(PAL["hair"])
    tints = {"Brows": hc * 0.75 + hexc(PAL["skin"]) * 0.25, "Lashes": hc * 0.65}
    for name, fn, cut in (("Brows", "Brows_eyebrow009.png", 0.42), ("Lashes", "Lashes_eyelashes01.png", 0.32)):
        if os.path.exists(os.path.join(TEX, fn)):
            card_material(name, os.path.join(TEX, fn), tints[name], cut)
    for name, fn in (("Teeth", "Teeth_teeth.png"), ("Tongue", "Tongue_tongue01_diffuse.png")):
        if os.path.exists(os.path.join(TEX, fn)):
            TS.preview_mat(name, os.path.join(TEX, fn), rough=0.35)
    prod = json.load(open(os.path.join(K.LOGS, "tex_produced.json"))) if os.path.exists(os.path.join(K.LOGS, "tex_produced.json")) else {}
    for mat, part in (("Garment_Top", "Top"), ("Garment_Pants", "Pants")):
        if os.path.exists(os.path.join(TEX, f"Kael_{part}_Mask.png")):
            M = TB.read_image(os.path.join(TEX, f"Kael_{part}_Mask.png"))
            prim = hexc(PAL["outfit"]) * (0.88 if part == "Pants" else 1.0)
            rgb, smooth = TS.composite_garment(M, prim, hexc(PAL["accent"]))
            TB.write_png(rgb, os.path.join(TEX, f"prev_{part}_BaseColor.png"), "RGB")
            TB.write_png(np.clip(1 - smooth, 0, 1), os.path.join(TEX, f"prev_{part}_Rough.png"), "RGB")
            TS.preview_mat(mat, os.path.join(TEX, f"prev_{part}_BaseColor.png"), os.path.join(TEX, f"Kael_{part}_Normal.png"),
                           rough=os.path.join(TEX, f"prev_{part}_Rough.png"))
    for mat, label, tint in (("Armor", "Armor", tuple(hexc(PAL["armor"]))), ("Boots", "Boots", None), ("Gloves", "Gloves", (0.36, 0.36, 0.36)),
                             ("Cloth_Gear", "Gear", None), ("Cloth_Jacket", "Jacket", None)):
        f = os.path.join(TEX, f"Kael_{label}_BaseColor.png")
        if os.path.exists(f):
            TS.preview_mat(mat, f, os.path.join(TEX, f"Kael_{label}_Normal.png"), maskmap=os.path.join(TEX, f"Kael_{label}_MaskMap.png"), tint=tint)
    TS.flat_mats({"Metal": ("#a7adb5", 0.32, 1.0, None), "Glow": (PAL["glow"], 0.3, 0.0, (PAL["glow"], 7.0)),
                  "Glow2": (PAL["glow2"], 0.3, 0.0, (PAL["glow2"], 7.0)), "Screen": ("#06141a", 0.15, 0.0, (PAL["glow"], 2.2)),
                  "Belt": ("#2e2c29", 0.62, 0.0, None)})


def add_catalog_hair(rig, style="side_part_volume"):
    """Catalog default hair placed like Unity does (rigid on the head bone): the cached model-space hair moved by the
    head bone offset between the committed rig (catalog reference) and this rig."""
    path = os.path.join(K.ROOT, "blender", "custom", "cache", f"hairobj_kael_{style}.blend")
    if not os.path.exists(path):
        return None
    with bpy.data.libraries.load(path) as (src, dst):
        dst.objects = [n for n in src.objects]
    o = next(x for x in dst.objects if x.type == "MESH")
    bpy.context.scene.collection.objects.link(o)
    o.name = "prev_hair"
    head = np.array(rig.matrix_world @ rig.data.bones["mixamorig:Head"].head_local)
    o.matrix_world = Matrix.Translation(Vector(head - OLD_HEAD)) @ o.matrix_world
    tex = os.path.join(CATALOG, "Hair", "Textures", f"kael_{style}_Hair.png")
    if os.path.exists(tex):
        m = card_material("prev_hair_mat", tex, hexc(PAL["hair"]), 0.4, rough=0.45)
        o.data.materials.clear(); o.data.materials.append(m)
    o["k_preview_hair"] = True
    return o


SHOTS = {
    "face": ("face", 0, 0.62, 0.0, 85), "face34": ("face", 35, 0.62, 0.0, 85), "profile": ("face", 90, 0.62, 0.0, 85),
    "front": ("body", 0, 4.6, 0.0, 50), "q34": ("body", 35, 4.6, 0.0, 50), "back": ("body", 180, 4.6, 0.0, 50),
    "bust": ("bust", 25, 1.6, 0.0, 50),
}


def render_set(tag, shots, light="menu", outdir=None, samples=96):
    rig = next(o for o in bpy.data.objects if o.type == "ARMATURE" and o.name == "Kael")
    L = {b.name.split(":")[1]: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones if ":" in b.name}
    eye = (L["LeftEye"] + L["RightEye"]) / 2
    fc = Vector((0, eye[1] + 0.025, eye[2] - 0.025))
    outdir = outdir or os.path.join(K.PREVIEWS, "look")
    out = []
    for s in shots:
        kind, yaw, dist, _, lens = SHOTS[s]
        K.clear_preview()
        r = math.radians(yaw)
        if kind == "face":
            K.cycles(samples=samples, res=(900, 1100))
            K.world((0.02, 0.022, 0.026), 1.0)
            K.rig_lights(light, fc, 0.6)
            K.camera(fc + Vector((math.sin(r) * dist, -math.cos(r) * dist, 0.0)), fc, lens)
        elif kind == "bust":
            c = Vector((0, 0, 1.45))
            K.cycles(samples=samples, res=(900, 1100))
            K.world((0.02, 0.022, 0.026), 1.0)
            K.rig_lights(light, c, 1.0)
            K.camera(c + Vector((math.sin(r) * dist, -math.cos(r) * dist, 0.05)), c, lens)
        else:
            c = Vector((0, 0, 0.95))
            K.cycles(samples=max(32, samples // 2), res=(800, 1200))
            K.world((0.02, 0.022, 0.026), 1.0)
            K.floor((0.05, 0.052, 0.056), 0.5)
            K.rig_lights(light, c, 1.7)
            K.camera(c + Vector((math.sin(r) * dist, -math.cos(r) * dist, 0.1)), c, lens)
        out.append(K.render_to(os.path.join(outdir, f"{tag}_{s}.png")))
    return out


if __name__ == "__main__":
    a = K.args()
    tag = a[0] if a else "look"
    shots = (K.opt(a, "--shots") or "face,face34,profile,front,q34,back").split(",")
    light = K.opt(a, "--light") or "menu"
    setup_materials()
    rig = bpy.data.objects["Kael"]
    for o in bpy.data.objects:
        if o.type == "MESH" and (o.name in ("BodyMH",) or o.name.endswith(("_HI", "_HIB", "_HPG"))):
            o.hide_render = True
        if o.type == "MESH" and (o.name.startswith("Hair_") or o.name.startswith("Facial_")):
            o.hide_render = True
    if not K.opt(a, "--nohair"):
        add_catalog_hair(rig)
    out = render_set(tag, shots, light)
    K.contact_sheet(out, os.path.join(K.PREVIEWS, "look", f"{tag}_sheet.png"), cols=3, width=600)
