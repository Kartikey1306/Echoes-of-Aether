"""HD hero/NPC build: geometry, skinning, blendshapes, textures, FBX + manifest export and previews.

  blender -b --python hero_hd.py -- <cid> [--base out/hd/<cid>_base.blend] [--no-export] [--previews studio,night]
          [--shots front,back,q34,face,face34,game] [--save out/hd/<cid>_hd.blend]

Without --base the MPFB human is assembled first (hero.assemble). Writes into
unity/EchoesOfAether/Assets/Art/Characters/<Name>/ (FBX, manifest, Textures/) and blender/out/previews_hd/.
"""
import bpy, sys, os, math, json, time, importlib
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from mathutils import Vector
import characters, gear, texbake as TB, texstage, skin_hd, hair_hd, export_hero, preview_hd
for m in (characters, gear, TB, texstage, skin_hd, hair_hd, export_hero, preview_hd):
    importlib.reload(m)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UNITY = export_hero.UNITY_CHARS
T0 = time.time()


def log(*a):
    print(f"[hd {time.time() - T0:7.1f}s]", *a, flush=True)


# ----------------------------------------------------------------------------- per character configuration

CFG = {
    "kael": {
        "outfit": "outfit_kael", "painter": "paint_kael",
        "joins": {"Boots": ["Boots", "BootsDetail"], "ChestRig": ["ChestRig", "ChestRigGear"]},
        "rigid": {"ChestPlate": "Spine2", "PauldronL": "LeftArm", "PauldronLameL": "LeftArm", "PauldronR": "RightArm",
                  "PauldronLameR": "RightArm", "KneePadL": "LeftLeg", "KneePadR": "RightLeg", "ForearmGuardR": "RightForeArm",
                  "Interface": "RightForeArm"},
        # shoulder caps ride the clavicle as much as the upper arm, so they stay seated when the arms come down
        "blend": {"PauldronL": [("LeftShoulder", 0.55), ("LeftArm", 0.45)], "PauldronR": [("RightShoulder", 0.55), ("RightArm", 0.45)],
                  "PauldronLameL": [("LeftShoulder", 0.25), ("LeftArm", 0.75)], "PauldronLameR": [("RightShoulder", 0.25), ("RightArm", 0.75)]},
        "limit": {"Belt": ["Hips", "Spine"], "ChestRig": ["Spine", "Spine1", "Spine2", "Neck", "LeftShoulder", "RightShoulder"],
                  "Cyberware": ["Head", "Neck"], "Collar": ["Neck", "Spine2", "Head", "LeftShoulder", "RightShoulder"]},
        "procedural_hair": ["curly", "wavy"], "default_hair": "curly",
        "extra_hair": {"bun": "k_man_bun_fade", "frenchbraid": "l_fishtail_braid"}, "beard_style": "scruffy",
        "palette": {"outfit": "#4d5243", "accent": "#1f2126", "armor": "#a9a59a", "glow": "#00e5ff", "glow2": "#ff2bd6",
                    "skin": "#b98a6e", "hair": "#1d1714", "eyes": "#5b3a22"},
        "beard": 0.35, "tattoo_color": [0.0, 0.898, 1.0],
        "optional": {"ChestRig": "plate-carrier vest over the jacket (toggle with ChestPlate or always on)",
                     "Cyberware": "temple implant lines and neck port (Metal + Glow); always on"},
    },
    "lyra": {
        "outfit": "outfit_lyra", "painter": "paint_lyra",
        "joins": {},
        "rigid": {"ShoulderR": "RightArm", "ForearmGuardL": "LeftForeArm", "ChestUnit": "Spine2", "ChestCore": "Spine2", "HipModule": "Hips"},
        "blend": {"ShoulderR": [("RightShoulder", 0.5), ("RightArm", 0.5)]},
        "limit": {"Harness": ["Hips", "Spine", "Spine1", "Spine2", "LeftShoulder", "RightShoulder", "Neck"],
                  "Cyberware": ["Head", "Neck"], "Visor": ["Head"], "ThighRig": ["RightUpLeg", "Hips"]},
        "procedural_hair": ["curly", "wavy"], "default_hair": "wavy",
        "extra_hair": {"bun": "l_messy_bun", "frenchbraid": "l_fishtail_braid"},
        "palette": {"outfit": "#8c8577", "accent": "#2a2431", "armor": "#8e8a96", "glow": "#ff2bd6", "glow2": "#8a5bff",
                    "skin": "#c79878", "hair": "#2b1b14", "eyes": "#5a3920"},
        "beard": 0.0, "tattoo_color": [1.0, 0.169, 0.839],
        "optional": {},
    },
}


def tone_for(skin_hex):
    c = np.array([int(skin_hex[i:i + 2], 16) / 255 for i in (1, 3, 5)])
    lum = c @ np.array((0.3, 0.59, 0.11))
    refs = [0.78, 0.62, 0.5, 0.3]
    best = int(np.argmin([abs(r - lum) for r in refs]))
    k = float(np.clip(lum / refs[best], 0.75, 1.25))
    tint = c / max(lum, 0.05) * lum * k
    tint = 1 + (tint / max(tint.max(), 1e-3) - 1) * 0.35
    tint = tint * float(np.clip(k, 0.85, 1.1))
    return ["light", "medium", "tan", "dark"][best], tint


# ----------------------------------------------------------------------------- build


def set_blend_weights(o, pairs):
    """Same fixed weights on every vertex (rigid plate carried by two bones)."""
    for g in list(o.vertex_groups):
        o.vertex_groups.remove(g)
    idx = list(range(len(o.data.vertices)))
    for bone, w in pairs:
        o.vertex_groups.new(name="mixamorig:" + bone).add(idx, w, "REPLACE")


def hand_plate_weights(o):
    """Knuckle/back-of-hand plates in the Gloves mesh (attribute kplate) ride the hand bone rigidly."""
    kp = gear.attr(o, "kplate")
    sel = np.where(kp > 0.5)[0]
    if not len(sel):
        return
    co = gear.get_co(o)
    for g in o.vertex_groups:
        g.remove([int(i) for i in sel])
    for side, bone in ((1, "LeftHand"), (-1, "RightHand")):
        ids = [int(i) for i in sel if np.sign(co[i, 0]) == side]
        g = o.vertex_groups.get("mixamorig:" + bone) or o.vertex_groups.new(name="mixamorig:" + bone)
        g.add(ids, 1.0, "REPLACE")


def improve_brows(tex_dir):
    """Denser brows/lashes for alpha testing: lift the soft alpha (strand ends survive the cutoff) and deepen colour."""
    for f in os.listdir(tex_dir):
        if f.startswith(("Brows_", "Lashes_")) and f.endswith(".png") and not f.endswith("_grey.png"):
            p = os.path.join(tex_dir, f)
            img = TB.read_image(p)
            a = img[..., 3]
            lo, hi = (0.12, 0.6) if f.startswith("Brows_") else (0.1, 0.6)
            img[..., 3] = np.clip(gear.ss(lo, hi, a), 0, 1)
            img[..., :3] = np.clip(img[..., :3] * 0.92, 0, 1)
            img = TB.dilate(img, img[..., 3] > 0.05, 3)
            TB.write_png(img, p, "RGBA")


def append_extra(cid, style, name, mat, tex_dir):
    """Append a hair object built by hair_extra.py (blender/out/hd/extra/<cid>_<style>.blend) and copy its atlas."""
    import shutil
    path = os.path.join(ROOT, "out", "hd", "extra", f"{cid}_{style}.blend")
    with bpy.data.libraries.load(path) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith("extra_")]
    o = dst.objects[0]
    bpy.context.scene.collection.objects.link(o)
    o.name = name
    o.data.name = name
    o.use_fake_user = False
    o.data.materials.clear()
    o.data.materials.append(gear.get_mat(mat))
    o.data.polygons.foreach_set("material_index", np.zeros(len(o.data.polygons), dtype=np.int32))
    fn = mat + "_Color.png"
    shutil.copyfile(os.path.join(ROOT, "out", "hd", "extra", f"{cid}_{style}_Hair.png"), os.path.join(tex_dir, fn))
    return o, fn


def find_parts(cname):
    rig = bpy.data.objects[cname]
    body = bpy.data.objects[cname + ".body"]
    return rig, body


def rename_base_hair(c, cname):
    """The base character hair object is named after its asset; give it its style id."""
    rev = {v.split("/")[0]: k for k, v in characters.HAIR_STYLES_ALL.items()}
    asset = c["hair"].split("/")[0]
    style = rev.get(asset)
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name == f"{cname}.{asset}" and style:
            o.name = f"{cname}.hair_{style}"
    return style


def body_region_attrs(body):
    me = body.data
    groups = {g.index: g.name for g in body.vertex_groups}
    head = np.zeros(len(me.vertices)); hand = np.zeros(len(me.vertices)); neck = np.zeros(len(me.vertices))
    for v in me.vertices:
        for g in v.groups:
            n = groups[g.group]
            if n in ("mixamorig:Head", "mixamorig:HeadTop_End", "mixamorig:LeftEye", "mixamorig:RightEye"):
                head[v.index] += g.weight
            elif "Hand" in n:
                hand[v.index] += g.weight
            elif n == "mixamorig:Neck":
                neck[v.index] += g.weight
    gear.set_attr(body, "rhead", head); gear.set_attr(body, "rhand", hand); gear.set_attr(body, "rneck", neck)


def run(cid, a):
    c = characters.CHARACTERS[cid]
    cfg = CFG[cid]
    cname = c["name"]
    if "--base" not in a:
        import hero
        hero.assemble(cid)
    rig, body = find_parts(cname)
    base_style = rename_base_hair(c, cname)
    hide_hair = [o for o in bpy.data.objects if o.type == "MESH" and (".hair_" in o.name or ".facial_" in o.name)]
    ctx = gear.Ctx(body, rig, cname)
    tex_dir = os.path.join(UNITY, cname, "Textures")
    wip = os.path.join(ROOT, "out", "hd", "tex_" + cid)
    os.makedirs(tex_dir, exist_ok=True); os.makedirs(wip, exist_ok=True)
    produced = {}
    # ---------------- outfit
    outfit = importlib.import_module(cfg["outfit"]); importlib.reload(outfit)
    objs = outfit.build(ctx)
    for tgt, parts in cfg["joins"].items():
        objs[tgt] = gear.join([objs.pop(p) for p in parts if p in objs], f"{cname}_{tgt}")
    for k, o in objs.items():
        o.name = f"{cname}_{k}"
        o.data.name = o.name
    log("outfit", {k: sum(len(p.vertices) - 2 for p in o.data.polygons) for k, o in objs.items()})
    # ---------------- procedural hair styles
    hair_objs = {}
    for style in cfg["procedural_hair"]:
        old = bpy.data.objects.get(f"{cname}.hair_{style}")
        if old:
            bpy.data.objects.remove(old, do_unlink=True)
        o, fn = getattr(hair_hd, "build_" + style)(ctx, f"{cname}.hair_{style}", tex_dir)
        hair_objs[style] = o
        produced["Hair_" + style] = [fn]
        o.hide_render = style != cfg["default_hair"]
    for style in cfg.get("extra_hair", {}):
        old = bpy.data.objects.get(f"{cname}.hair_{style}")
        if old:
            bpy.data.objects.remove(old, do_unlink=True)
        o, fn = append_extra(cid, style, f"{cname}.hair_{style}", "Hair_" + style, tex_dir)
        hair_objs[style] = o
        produced["Hair_" + style] = [fn]
        o.hide_render = True
    if cfg.get("beard_style"):
        import beard
        importlib.reload(beard)
        o, fn = beard.build_beard(ctx, f"{cname}.facial_beard", tex_dir, cfg["beard_style"])
        ctx.finalize(o, weight_bones=["Head", "Neck"])
        produced["Facial_beard"] = [fn]
    log("hair", {k: sum(len(p.vertices) - 2 for p in o.data.polygons) for k, o in hair_objs.items()})
    # ---------------- eyes + teeth
    eye = next(o for o in bpy.data.objects if o.type == "MESH" and "high-poly" in o.name)
    skin_hd.rebuild_eyes(ctx, eye)
    teeth = next(o for o in bpy.data.objects if o.type == "MESH" and "teeth" in o.name)
    skin_hd.decimate_with_shapes(teeth, 0.2)
    tongue = next((o for o in bpy.data.objects if o.type == "MESH" and "tongue" in o.name), None)
    if tongue is not None:
        skin_hd.decimate_with_shapes(tongue, 0.6)
    log("eyes/teeth", len(eye.data.polygons), len(teeth.data.polygons))
    # ---------------- skinning + blendshapes for everything new
    for k, o in objs.items():
        if k in cfg.get("blend", {}):
            ctx.finalize(o, bone=cfg["blend"][k][0][0])
            set_blend_weights(o, cfg["blend"][k])
        elif k in cfg["rigid"]:
            ctx.finalize(o, bone=cfg["rigid"][k])
        elif k in cfg["limit"]:
            ctx.finalize(o, weight_bones=cfg["limit"][k])
        else:
            ctx.finalize(o)
    if "Gloves" in objs:
        hand_plate_weights(objs["Gloves"])
    for st, o in hair_objs.items():
        ctx.finalize(o, bone="Head")
        hair_hd.hair_weights(o, ctx)
    log("finalized")
    # ---------------- textures: garments + hard surface
    painter = importlib.import_module(cfg["painter"]); importlib.reload(painter)
    allo = list(objs.values())
    pal = cfg["palette"]
    r = texstage.garment_atlas(allo, "Garment_Top", "Top", cname, painter.top, ctx.L, 2048, tex_dir, wip, pal, hide_hair)
    if r: produced["Garment_Top"] = r
    r = texstage.garment_atlas(allo, "Garment_Pants", "Pants", cname, painter.pants, ctx.L, 2048, tex_dir, wip, pal, hide_hair)
    if r: produced["Garment_Pants"] = r
    import paint_hs
    importlib.reload(paint_hs)
    at = np.array([int(pal["armor"][i:i + 2], 16) / 255 for i in (1, 3, 5)])
    r = texstage.hard_atlas_baked(allo, "Armor", cname, paint_hs.armor, 2048, tex_dir, tint=tuple(at), ao_hide=hide_hair)
    if r: produced["Armor"] = r
    r = texstage.hard_atlas_baked(allo, "Boots", cname, painter.boots, 2048, tex_dir, tint=None, ao_hide=hide_hair)
    if r: produced["Boots"] = r
    gt = np.array([int(pal["outfit"][i:i + 2], 16) / 255 for i in (1, 3, 5)]) * 0.75
    r = texstage.hard_atlas_baked(allo, "Gloves", cname, lambda t, ao: painter.gloves(t, ao, ctx.L), 1024, tex_dir, tint=tuple(gt), ao_hide=hide_hair)
    if r: produced["Gloves"] = r
    texstage.remove_floaters()
    log("garment/hard textures", list(produced))
    # ---------------- body strip + relayout + skin
    removed = export_hero.strip_covered(body, ctx.cover)
    body.data.materials.clear()
    body.data.materials.append(gear.get_mat("Skin"))
    body.data.polygons.foreach_set("material_index", np.zeros(len(body.data.polygons), dtype=np.int32))
    body_region_attrs(body)
    skin_hd.relayout_body(body, head_weight=1.6)
    gender = "female" if c["phenotype"]["gender"] < 0.5 else "male"
    hc, _, _ = hair_hd.head_frame(ctx)
    hl = "male" if gender == "male" else "female"
    scalp_fn = lambda P: hair_hd.scalp_field(P, hc, hl, soft=6.0) * (0.22 if cfg["default_hair"] == "curly" else 0.1)
    skins, tattoo = skin_hd.skin_textures(body, ctx, cid, gender, tex_dir, 2048, beard=cfg["beard"], scalp=scalp_fn, hide=hide_hair)
    eyes = skin_hd.eye_textures(tex_dir)
    produced["Skin"] = [skins.get("medium", "Skin_medium.png"), "Skin_Normal.png", "Skin_MaskMap.png"]
    produced["Eyes"] = ["Eye_grey.png"]
    log("skin/eyes", skins, tattoo)
    # ---------------- MakeHuman hair styles: improved card textures
    for o in [o for o in bpy.data.objects if o.type == "MESH" and ".hair_" in o.name]:
        style = o.name.split(".hair_")[1]
        if style in cfg["procedural_hair"]:
            continue
        imgs = export_hero.images_of(o)
        if not imgs:
            continue
        fn = f"Hair_{style}_Color.png"
        hair_hd.improve_mh_hair(o, imgs[0], os.path.join(tex_dir, fn), hc)
        produced["Hair_" + style] = [fn]
    for o in [o for o in bpy.data.objects if o.type == "MESH" and ".facial_" in o.name]:
        imgs = export_hero.images_of(o)
        if imgs and "Facial_" + o.name.split(".facial_")[1] not in produced:
            style = o.name.split(".facial_")[1]
            fn = f"Facial_{style}_Color.png"
            hair_hd.improve_mh_hair(o, imgs[0], os.path.join(tex_dir, fn), hc)
            produced["Facial_" + style] = [fn]
    log("hair textures")
    # ---------------- export
    height = round(float(max((body.matrix_world @ v.co).z for v in body.data.vertices)), 3)
    extra = manifest_extra(cid, cfg, skins, tattoo, produced)
    if "--no-export" not in a:
        keep = set(f for v in produced.values() for f in v) | set(skins.values()) | {"Skin_Normal.png", "Skin_MaskMap.png", "Skin_Stubble.png",
                                                                                  "Skin_Tattoo.png", "Skin_TattooMask.png", "Hair_wavy_Dye.png"} | set(eyes.values())
        keep |= {f for f in os.listdir(tex_dir) if f.startswith(("Brows_", "Lashes_", "Teeth_", "Tongue_")) and not f.endswith("_grey.png")}
        man = export_hero.export_hd(cid, cname, rig, gender, cfg["default_hair"], height, produced, extra, removed=removed)
        improve_brows(tex_dir)
        keep |= {f for v in man["textures"].values() for f in v}
        log("cleaned", export_hero.clean_textures(tex_dir, keep))
    if "--save" in a:
        bpy.ops.wm.save_as_mainfile(filepath=a[a.index("--save") + 1])
    if "--no-export" not in a and "--no-lod" not in a:
        export_lod1(cid, cname, rig)
        bpy.ops.wm.open_mainfile(filepath=a[a.index("--save") + 1]) if "--save" in a else None
    return ctx, cfg


def export_lod1(cid, cname, rig, ratio=0.4):
    """LOD1 (~40 %): every mesh decimated with its blendshapes and weights rebuilt; separate <Name>_LOD1.fbx next to
    the LOD0 file (same mesh/bone/material names, so a LODGroup can pair renderers by name)."""
    out_dir = os.path.join(UNITY, cname)
    tot0 = tot1 = 0
    for o in [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig]:
        n0 = sum(len(p.vertices) - 2 for p in o.data.polygons)
        tot0 += n0
        if n0 > 400 and not o.name.startswith(("Eyes", "Brows", "Lashes")):
            skin_hd.decimate_with_shapes(o, ratio)
        tot1 += sum(len(p.vertices) - 2 for p in o.data.polygons)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for o in rig.children:
        if o.type == "MESH":
            o.select_set(True)
    bpy.context.view_layer.objects.active = rig
    path = os.path.join(out_dir, cname + "_LOD1.fbx")
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Z", axis_up="Y", bake_space_transform=True, use_mesh_modifiers=False, mesh_smooth_type="FACE",
        use_tspace=True, add_leaf_bones=False, use_armature_deform_only=True, bake_anim=False, path_mode="STRIP",
        embed_textures=False, use_custom_props=False)
    mp = os.path.join(out_dir, cname + ".manifest.json")
    if os.path.exists(mp):
        m = json.load(open(mp))
        m["lod1"] = {"fbx": cname + "_LOD1.fbx", "ratio": ratio, "tris": tot1, "trisLOD0All": tot0,
                     "note": "same mesh, bone and material names as LOD0; pair renderers by name in a LODGroup"}
        json.dump(m, open(mp, "w"), indent=1)
    log("LOD1", path, tot0, "->", tot1)


def manifest_extra(cid, cfg, skins, tattoo, produced):
    pal = cfg["palette"]
    ex = {
        "skins": skins,
        "skinMaps": {"normal": "Skin_Normal.png", "maskMap": "Skin_MaskMap.png", "stubble": "Skin_Stubble.png" if cfg["beard"] > 0 else None},
        "eyeLayout": {"note": "iris centred at uv (0.5, 0.5); ellipse d = sqrt(4*du^2 + dv^2) < 0.085 (matches CharacterModel.ApplyEyes)",
                      "variants": ["Eye_grey.png", "Eye_brown.png", "Eye_blue.png", "Eye_green.png"]},
        "palette": pal,
        "hairAlphaCutoff": {"default": 0.4, "curly": 0.4, "wavy": 0.35, "bun": 0.38, "frenchbraid": 0.38, "beard": 0.35, "Brows": 0.4, "Lashes": 0.3},
        "hairDye": {"wavy": "Hair_wavy_Dye.png"},
        "optionalParts": cfg.get("optional", {}),
        "materialDefs": material_defs(cid, produced),
    }
    if tattoo:
        ex["tattoo"] = tattoo
        ex["tattooMask"] = "Skin_TattooMask.png"
        ex["tattooColor"] = cfg["tattoo_color"]
    return ex


def material_defs(cid, produced):
    """Machine-readable description of every material slot so the Unity CharacterBuilder can map textures."""
    name = CFG[cid]
    d = {}
    for mat, files in produced.items():
        if mat in ("Garment_Top", "Garment_Pants"):
            d[mat] = {"type": "garment", "mask": files[0], "normal": files[1], "tint": "outfit/accent (runtime composite)"}
        elif mat in ("Armor", "Boots", "Gloves"):
            d[mat] = {"type": "lit", "baseMap": files[0], "normal": files[1], "maskMap": files[2],
                      "maskMapLayout": "R metallic, G occlusion, B paint mask, A smoothness",
                      "tint": {"Armor": "armor", "Gloves": "outfit*0.75", "Boots": None}[mat]}
        elif mat.startswith("Hair_"):
            d[mat] = {"type": "hair", "baseMap": files[0], "alphaClip": 0.35 if "wavy" in mat else 0.4, "tint": "hair"}
    d["Skin"] = {"type": "skin", "normal": "Skin_Normal.png", "maskMap": "Skin_MaskMap.png", "emission": "Skin_Tattoo.png"}
    d["Metal"] = {"type": "lit", "color": "#a7adb5", "metallic": 1.0, "smoothness": 0.68}
    d["Glow"] = {"type": "emissive", "tint": "glow"}
    d["Glow2"] = {"type": "emissive", "tint": "glow2"}
    d["Screen"] = {"type": "emissive", "tint": "glow*0.6"}
    return d


# ----------------------------------------------------------------------------- previews


def preview_materials(cid, cfg, tex_dir):
    pal = cfg["palette"]
    man_p = os.path.join(UNITY, characters.CHARACTERS[cid]["name"], characters.CHARACTERS[cid]["name"] + ".manifest.json")
    man_tex = json.load(open(man_p))["textures"] if os.path.exists(man_p) else {}
    hx = lambda h: np.array([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)])
    tone, tint = (cfg["preview_tone"], np.ones(3)) if cfg.get("preview_tone") else tone_for(pal["skin"])
    sk = bpy.data.materials.get("Skin") or bpy.data.materials.new("Skin")
    body = next(o for o in bpy.data.objects if o.type == "MESH" and (o.name == "Body" or o.name.endswith(".body")))
    body.data.materials.clear(); body.data.materials.append(sk)
    m = texstage.preview_mat("Skin", os.path.join(tex_dir, f"Skin_{tone}.png"), os.path.join(tex_dir, "Skin_Normal.png"),
                             maskmap=os.path.join(tex_dir, "Skin_MaskMap.png"), tint=tuple(tint), normal_strength=0.6)
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Subsurface Weight"].default_value = 0.12
    b.inputs["Subsurface Radius"].default_value = (0.9, 0.35, 0.2)
    b.inputs["Subsurface Scale"].default_value = 0.006
    if os.path.exists(os.path.join(tex_dir, "Skin_Tattoo.png")):
        nt = m.node_tree
        tn = texstage.img_node(nt, os.path.join(tex_dir, "Skin_Tattoo.png"), non_color=False)
        nt.links.new(tn.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = 5.0
    # Eyes: Unity tints the grey iris; preview uses the palette eye colour
    eyes = next(o for o in bpy.data.objects if o.type == "MESH" and ("high-poly" in o.name or o.name == "Eyes"))
    img = TB.read_image(os.path.join(tex_dir, "Eye_grey.png"))
    h_, w_ = img.shape[:2]
    yy, xx = np.mgrid[0:h_, 0:w_]
    dd = np.sqrt(((xx + 0.5) / w_ - 0.5) ** 2 * 4 + ((yy + 0.5) / h_ - 0.5) ** 2)
    irisk = 1 - gear.ss(0.075, 0.095, dd)
    lum = img[..., :3].mean(-1)
    ic = hx(pal["eyes"])
    eimg = img[..., :3] * (1 - irisk[..., None]) + (lum[..., None] * ic * 2.1) * irisk[..., None]
    TB.write_png(np.clip(eimg, 0, 1), os.path.join(ROOT, "out", "hd", f"tex_{cid}", "eye_preview.png"), "RGB")
    em = bpy.data.materials.get("Eyes_prev") or bpy.data.materials.new("Eyes_prev")
    eyes.data.materials.clear(); eyes.data.materials.append(em)
    texstage.preview_mat("Eyes_prev", os.path.join(ROOT, "out", "hd", f"tex_{cid}", "eye_preview.png"), rough=0.06)
    em.node_tree.nodes["Principled BSDF"].inputs["Coat Weight"].default_value = 0.6
    # hair / brows / lashes / facial: desaturate + tint + alpha clip (mirrors CharacterBuilder.Desaturated)
    hair_c = hx(pal["hair"])
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        kind = None
        if ".hair_" in o.name or o.name.startswith("Hair_"):
            kind, cut, col = "hair", 0.4, hair_c
        elif "eyebrow" in o.name or o.name == "Brows":
            kind, cut, col = "brows", 0.45, hair_c * 0.85
        elif "eyelash" in o.name or o.name == "Lashes":
            kind, cut, col = "lashes", 0.35, hair_c * 0.5
        elif ".facial_" in o.name or o.name.startswith("Facial_"):
            kind, cut, col = "facial", 0.35, hair_c * (0.9 if cid != "oren" else 1.0)
        if not kind:
            continue
        src = None
        mname = o.data.materials[0].name if o.data.materials else ""
        if man_tex.get(mname):
            src = os.path.join(tex_dir, man_tex[mname][0])
        else:
            ims = export_hero.images_of(o)
            src = ims[0] if ims else None
        if not src:
            continue
        im = TB.read_image(src)
        lum = im[..., :3].mean(-1); al = im[..., 3]
        mean = lum[al > 0.5].mean() if (al > 0.5).any() else 0.5
        grey = np.clip(lum / max(mean, 1e-3) * 0.745, 0, 1)
        out = os.path.join(ROOT, "out", "hd", f"tex_{cid}", f"prev_{o.name}.png")
        TB.write_png(np.concatenate([grey[..., None] * col, al[..., None]], -1), out, "RGBA")
        mat = bpy.data.materials.new("prev_" + o.name)
        mat.use_nodes = True
        nt = mat.node_tree
        for n in list(nt.nodes): nt.nodes.remove(n)
        on = nt.nodes.new("ShaderNodeOutputMaterial"); bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bs.outputs[0], on.inputs[0])
        tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = bpy.data.images.load(out, check_existing=False)
        nt.links.new(tx.outputs["Color"], bs.inputs["Base Color"])
        g = nt.nodes.new("ShaderNodeMath"); g.operation = "GREATER_THAN"; g.inputs[1].default_value = cut
        nt.links.new(tx.outputs["Alpha"], g.inputs[0]); nt.links.new(g.outputs[0], bs.inputs["Alpha"])
        bs.inputs["Roughness"].default_value = 0.55
        bs.inputs["Specular IOR Level"].default_value = 0.25
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
        mat.use_backface_culling = False
        o.data.materials.clear(); o.data.materials.append(mat)
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name in ("Teeth", "Tongue") and man_tex.get(o.name):
            texstage.preview_mat(o.name, os.path.join(tex_dir, man_tex[o.name][0]), rough=0.35)
    for o in bpy.data.objects:  # any other textured slot without preview nodes (MakeHuman clothes, boots)
        if o.type != "MESH":
            continue
        for m in o.data.materials:
            if m and man_tex.get(m.name) and not (m.use_nodes and any(n.type == "TEX_IMAGE" for n in m.node_tree.nodes)) \
                    and os.path.exists(os.path.join(tex_dir, man_tex[m.name][0])):
                texstage.preview_mat(m.name, os.path.join(tex_dir, man_tex[m.name][0]), rough=0.7)
    texstage.flat_mats({"Metal": ("#a7adb5", 0.3, 1.0, None), "Belt": ("#2e2c29", 0.62, 0.0, None), "Harness": ("#2e2c29", 0.6, 0.0, None),
                        "Strap": ("#2e2c29", 0.6, 0.0, None),
                        "Glow": (pal["glow"], 0.3, 0.0, (pal["glow"], 10.0)), "Glow2": (pal["glow2"], 0.3, 0.0, (pal["glow2"], 10.0)),
                        "Screen": ("#06141a", 0.15, 0.0, (pal["glow"], 3.0)), "SuitSecondary": (pal["accent"], 0.6, 0.0, None),
                        "Gear": ("#3a3f46", 0.5, 0.3, None), "Lens": ("#1a2a30", 0.1, 0.0, (pal["glow"], 3.0)), "Scarf": ("#5a4a3a", 0.9, 0.0, None)})


def previews(cid, cfg, lights, shots):
    c = characters.CHARACTERS[cid]
    cname = c["name"]
    rig = bpy.data.objects[cname]
    tex_dir = os.path.join(UNITY, cname, "Textures")
    preview_materials(cid, cfg, tex_dir)
    body = next(o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig and (o.name == "Body" or o.name.endswith(".body")))
    h = max((body.matrix_world @ v.co).z for v in body.data.vertices)
    hb = rig.data.bones["mixamorig:Head"]
    head = rig.matrix_world @ hb.head_local
    face = Vector((0, head.y - 0.03, head.z + 0.07))
    for o in bpy.data.objects:
        if o.type == "MESH" and o.parent is rig:
            n = o.name
            if (n.startswith("Hair_") and n != "Hair_" + cfg["default_hair"]) or (".hair_" in n and not n.endswith("hair_" + cfg["default_hair"])):
                o.hide_render = True
            if (n.startswith("Facial_") or ".facial_" in n) and not cfg.get("show_facial"):
                o.hide_render = True
    preview_hd.OUT = os.path.join(ROOT, "out", "previews_hd")
    for L in lights:
        preview_hd.render(cid, (0, 0, 0), h, face, L, shots, samples=32)
    # check shots for the replacement styles (bun, frenchbraid, beard)
    checks = [("Hair_" + st, st) for st in cfg.get("extra_hair", {})] + ([("Facial_beard", "beard")] if cfg.get("beard_style") else [])
    meshes = {o.name: o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig}
    for mesh_name, tag in checks:
        if mesh_name not in meshes:
            continue
        state = {n: o.hide_render for n, o in meshes.items()}
        for n, o in meshes.items():
            if n.startswith("Hair_"):
                o.hide_render = not (n == mesh_name or (tag == "beard" and n == "Hair_" + cfg["default_hair"]))
        meshes[mesh_name].hide_render = False
        for L in lights[:1]:
            for shot in ("face34", "back") if tag != "beard" else ("face", "face34"):
                preview_hd.render(f"{cid}_{tag}", (0, 0, 0), h, face, L, [shot], samples=32)
        for n, v in state.items():
            meshes[n].hide_render = v


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    cid = a[0]
    ctx, cfg = run(cid, a)  # with --base the cached base blend must be loaded as Blender's file argument
    if "--previews" in a:
        shots = a[a.index("--shots") + 1].split(",") if "--shots" in a else ["front", "back", "q34", "face", "face34", "game"]
        previews(cid, cfg, a[a.index("--previews") + 1].split(","), shots)
    log("done")
