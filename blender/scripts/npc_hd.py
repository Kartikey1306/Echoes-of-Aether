"""HD NPC build (cyberpunk street survivors): MakeHuman base + layered garments/gear, baked cloth + skin textures,
glowing tattoos (Mira, Tomas), rebuilt eyes, decimated heavy assets, FBX + manifest, previews.

  blender -b --python npc_hd.py -- <oren|mira|tomas|maren|nia> [--previews studio,night] [--save file.blend]
"""
import bpy, sys, os, importlib, json
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import characters, gear, texbake as TB, texstage, skin_hd, hair_hd, export_hero, hero_hd, outfit_npc, paint_npc, paint_kael, outfits_def, hero
for m in (characters, gear, TB, texstage, skin_hd, hair_hd, export_hero, outfit_npc, paint_npc, outfits_def):
    importlib.reload(m)
log = hero_hd.log
UNITY = export_hero.UNITY_CHARS

NPC = {
    "oren": {"beard": "full", "cloth": {"Cloth_Parka": "Parka"}, "tints": {"hair": "#8d8a86", "Facial": "#7a7570"}, "glow": "#00e5ff", "glow2": "#ffb45e",
             "outfit": "#4a4a3a", "eyes": "#4a4036", "skin": "#c8a088", "tattoo": None},
    "mira": {"cloth": {"Cloth_Hoodie": "Hoodie"}, "tints": {"hair": "#1a1726"}, "glow": "#00e5ff", "glow2": "#ff2bd6",
             "outfit": "#2c3a40", "eyes": "#3c2b1d", "skin": "#d8b496", "tattoo": [0.25, 0.95, 0.85]},
    "tomas": {"cloth": {"Cloth_Coat": "Coat"}, "tints": {"hair": "#141210"}, "glow": "#9dff5a", "glow2": "#00e5ff",
              "outfit": "#4a3b2c", "eyes": "#3c2b1d", "skin": "#6a4a38", "tattoo": [0.6, 1.0, 0.35]},
    "maren": {"extra_hair": "bun", "cloth": {"Cloth_LabCoat": "LabCoat"}, "tints": {"hair": "#6b5a4a"}, "glow": "#8ff0e0", "glow2": "#a77bff",
              "outfit": "#d0d0cc", "eyes": "#3b5f7a", "skin": "#e0bba0", "tattoo": None},
    "nia": {"cloth": {"Cloth_Hoodie": "HoodieNia"}, "tints": {"hair": "#2b1d14"}, "glow": "#a9c4ff", "glow2": "#ff9ad6",
            "outfit": "#544a6a", "eyes": "#5b3a22", "skin": "#e3b796", "tattoo": None},
}
BUDGET = 40000


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def run(cid, a):
    c = characters.CHARACTERS[cid]
    n = NPC[cid]
    cname = c["name"]
    import meshutil
    deferred = []
    orig = meshutil.delete_verts_in_groups
    meshutil.delete_verts_in_groups = lambda obj, groups: deferred.extend(groups)  # keep the full body for layering
    try:
        hero.assemble(cid)
    finally:
        meshutil.delete_verts_in_groups = orig
    rig = bpy.data.objects[cname]
    body = bpy.data.objects[cname + ".body"]
    if c["hair"]:
        asset = c["hair"].split("/")[1].replace(".mhclo", "")
        for o in bpy.data.objects:
            if o.type == "MESH" and o.name == f"{cname}.{asset}":
                o.name = f"{cname}.hair_default"
    if "--save-base" in a:
        bpy.ops.wm.save_as_mainfile(filepath=a[a.index("--save-base") + 1])
        log("saved base")
        raise SystemExit(0)
    if c.get("gear"):
        for o in outfits_def.npc_gear(body, rig, c["gear"]):
            if o.name.endswith(("HeadsetBand", "HeadsetMic")):
                bpy.data.objects.remove(o, do_unlink=True)
    from bl_ext.user_default.mpfb.entities.objectproperties import GeneralObjectProperties
    base_clothes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig
                    and str(GeneralObjectProperties.get_value("object_type", entity_reference=o) or "").lower() == "clothes"
                    and "beard" not in o.name and "moustache" not in o.name]
    hide_hair = [o for o in bpy.data.objects if o.type == "MESH" and (".hair_" in o.name or "beard" in o.name)]
    ctx = gear.Ctx(body, rig, cname)
    ctx.base_clothes = base_clothes
    tex_dir = os.path.join(UNITY, cname, "Textures")
    os.makedirs(tex_dir, exist_ok=True)
    produced = {}
    if n.get("extra_hair"):
        o, fn = hero_hd.append_extra(cid, n["extra_hair"], f"{cname}.hair_default", "Hair_default", tex_dir)
        ctx.finalize(o, bone="Head")
        hair_hd.hair_weights(o, ctx)
        produced["Hair_default"] = [fn]
    if n.get("beard"):
        import beard
        o, fn = beard.build_beard(ctx, f"{cname}.facial_beard", tex_dir, n["beard"])
        ctx.finalize(o, weight_bones=["Head", "Neck"])
        produced["Facial_beard"] = [fn]
    hide_hair = [o for o in bpy.data.objects if o.type == "MESH" and (".hair_" in o.name or "beard" in o.name)]
    objs = outfit_npc.build(ctx, cid)
    for k, o in objs.items():
        o.name = f"{cname}_{k}"; o.data.name = o.name
        ctx.finalize(o)
    layers = [o for k, o in objs.items() if k in ("Parka", "Hoodie", "LabCoat", "Coat")]
    for bc in base_clothes:
        if layers:
            log("occluded", bc.name, gear.strip_occluded(bc, layers, 0.08, 1))
    eye = next(o for o in bpy.data.objects if o.type == "MESH" and "high-poly" in o.name)
    skin_hd.rebuild_eyes(ctx, eye)
    teeth = next(o for o in bpy.data.objects if o.type == "MESH" and "teeth" in o.name)
    skin_hd.decimate_with_shapes(teeth, 0.2)
    log("built", {o.name: tris(o) for o in bpy.data.objects if o.type == "MESH" and o.parent is rig})
    allo = list(objs.values())
    for mat, style in n["cloth"].items():
        r = texstage.hard_atlas(allo, mat, cname, paint_npc.cloth(style, ctx.L, seed=hash(cid) % 7 + 1.0), 2048 if cid in ("oren", "mira") else 1024,
                                tex_dir, tint=None, ao_hide=hide_hair)
        if r: produced[mat] = r
    r = texstage.hard_atlas(allo, "Armor", cname, paint_kael.armor, 1024, tex_dir, tint=(0.55, 0.55, 0.55), ao_hide=hide_hair)
    if r: produced["Armor"] = r
    removed = export_hero.strip_covered(body, ctx.cover)
    meshutil.delete_verts_in_groups(body, deferred)
    occl = [o for o in base_clothes] + [o for k, o in objs.items() if k in ("Parka", "Hoodie", "LabCoat", "Coat")]
    removed += gear.strip_occluded(body, occl, 0.035, 2)
    log("body after strip", tris(body))
    body.data.materials.clear(); body.data.materials.append(gear.get_mat("Skin"))
    body.data.polygons.foreach_set("material_index", np.zeros(len(body.data.polygons), dtype=np.int32))
    hero_hd.body_region_attrs(body)
    skin_hd.relayout_body(body, head_weight=1.6)
    folder = c["skin"].split("/")[0]
    hc, _, _ = hair_hd.head_frame(ctx)
    gender = "female" if c["phenotype"]["gender"] < 0.5 else "male"
    skins, tattoo = skin_hd.skin_textures(body, ctx, cid, gender, tex_dir, 2048, tones={"medium": folder},
                                          beard=0.25 if gender == "male" else 0.0,
                                          scalp=lambda P: hair_hd.scalp_field(P, hc, "male" if gender == "male" else "female") * 0.4,
                                          hide=hide_hair, tattoo=bool(n["tattoo"]))
    eyes = skin_hd.eye_textures(tex_dir)
    produced["Skin"] = ["Skin_medium.png", "Skin_Normal.png", "Skin_MaskMap.png"]
    produced["Eyes"] = ["Eye_grey.png"]
    for o in [o for o in bpy.data.objects if o.type == "MESH" and (".hair_" in o.name or "beard" in o.name)]:
        imgs = export_hero.images_of(o)
        nm = "Hair_default" if ".hair_" in o.name else "Facial_" + o.name.split(".", 1)[1].replace("facial_", "")
        if imgs and nm not in produced:
            fn = nm + "_Color.png"
            hair_hd.improve_mh_hair(o, imgs[0], os.path.join(tex_dir, fn), hc)
            produced[nm] = [fn]
    # budget: first crush pathological assets (e.g. 30-57k-triangle shoes), then trim clothing proportionally;
    # never touch the body, hair, eyes, teeth, brows or lashes.
    vis = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig]
    protect = lambda o: o is body or any(k in o.name for k in (".hair_", "high-poly", "teeth", "eyebrow", "eyelash", "tongue", "beard"))
    for o in vis:
        if not protect(o) and tris(o) > 9000:
            before = tris(o)
            skin_hd.decimate_with_shapes(o, 5000.0 / before)
            log("decimated", o.name, before, "->", tris(o))
    tot = sum(tris(o) for o in vis)
    for o in sorted([o for o in vis if not protect(o)], key=tris, reverse=True):
        if tot <= BUDGET:
            break
        before = tris(o)
        if before < 2500:
            continue
        skin_hd.decimate_with_shapes(o, max(0.5, 1 - (tot - BUDGET) / before))
        tot += tris(o) - before
        log("decimated", o.name, before, "->", tris(o))
    height = round(float(max((body.matrix_world @ v.co).z for v in body.data.vertices)), 3)
    extra = {"npc": True, "echo": bool(c.get("echo")), "tints": n["tints"], "skins": skins,
             "skinMaps": {"normal": "Skin_Normal.png", "maskMap": "Skin_MaskMap.png"},
             "eyeLayout": {"note": "iris centred at uv (0.5, 0.5); ellipse d = sqrt(4*du^2 + dv^2) < 0.085", "variants": list(eyes.values())},
             "palette": {"glow": n["glow"], "glow2": n["glow2"], "hair": n["tints"]["hair"]},
             "hairAlphaCutoff": {"default": 0.38 if n.get("extra_hair") else 0.4, "beard": 0.35, "Brows": 0.4, "Lashes": 0.3}, "materialDefs": hero_hd.material_defs(cid, produced) if cid in hero_hd.CFG else {}}
    if tattoo:
        extra.update({"tattoo": tattoo, "tattooMask": "Skin_TattooMask.png", "tattooColor": n["tattoo"]})
    keep = set(f for v in produced.values() for f in v) | {"Skin_medium.png", "Skin_Normal.png", "Skin_MaskMap.png", "Skin_Stubble.png",
                                                             "Skin_Tattoo.png", "Skin_TattooMask.png"} | set(eyes.values())
    keep |= {f for f in os.listdir(tex_dir) if f.startswith(("Brows_", "Lashes_", "Teeth_", "Tongue_")) and not f.endswith("_grey.png")}
    man = export_hero.export_hd(cid, cname, rig, gender, "default", height, produced, extra, removed=removed)
    hero_hd.improve_brows(tex_dir)
    keep |= {f for v in man["textures"].values() for f in v}
    bt = man["textures"].get("Boots")
    if bt and os.path.exists(os.path.join(tex_dir, bt[0])):
        img = TB.read_image(os.path.join(tex_dir, bt[0]))
        if img[..., :3].mean() > 0.45:   # light MakeHuman shoe textures are meant to be tinted: bake a worn leather tone
            img[..., :3] = img[..., :3] * np.array((0.42, 0.33, 0.27))
            TB.write_png(img, os.path.join(tex_dir, bt[0]), "RGBA")
    log("cleaned", export_hero.clean_textures(tex_dir, keep))
    cfg = {"palette": {"skin": n["skin"], "hair": n["tints"]["hair"], "eyes": n["eyes"], "glow": n["glow"], "glow2": n["glow2"],
                       "outfit": n["outfit"], "accent": "#24262b", "armor": "#8a8a8a"}, "preview_tone": "medium", "default_hair": "default",
           "show_facial": bool(n.get("beard"))}
    return cfg


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:]
    cid = a[0]
    cfg = run(cid, a)
    if "--save" in a:
        bpy.ops.wm.save_as_mainfile(filepath=a[a.index("--save") + 1])
    if "--previews" in a:
        hero_hd.CFG[cid] = cfg
        hero_hd.previews(cid, cfg, a[a.index("--previews") + 1].split(","), ["front", "q34", "back", "face34"])
    log("done")
