"""Normalise names/materials, collect textures, strip hidden body faces and export a hero FBX + manifest."""
import bpy, bmesh, os, json, shutil
import numpy as np

UNITY_CHARS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "unity", "EchoesOfAether", "Assets", "Art", "Characters"))
MPFB_DATA = os.path.expanduser("~/Library/Application Support/Blender/5.2/extensions/.user/user_default/mpfb/data")

ARMOR = ("Pauldron", "ChestPlate", "KneePad", "ForearmGuard", "ShoulderR", "Interface", "ChestUnit", "HipModule")

SKINS = {
    "male": {"light": "young_caucasian_male", "medium": "toigo_light_skin_male_bronze", "tan": "young_asian_male", "dark": "young_african_male"},
    "female": {"light": "young_caucasian_female", "medium": "toigo_light_skin_female_bronze", "tan": "young_asian_female", "dark": "young_african_female"},
}


def images_of(obj):
    out = []
    for m in obj.data.materials:
        if m and m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image and n.image.filepath:
                    out.append(bpy.path.abspath(n.image.filepath))
    return out


def new_mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    return m


def set_single_material(obj, name):
    obj.data.materials.clear()
    obj.data.materials.append(new_mat(name))
    for p in obj.data.polygons:
        p.material_index = 0


def classify(obj, cname, default_hair):
    n = obj.name
    p = cname + "."
    from bl_ext.user_default.mpfb.entities.objectproperties import GeneralObjectProperties
    otype = GeneralObjectProperties.get_value("object_type", entity_reference=obj) or ""
    if str(otype).lower() == "clothes" and ".facial_" not in n:
        asset = n.split(".", 1)[1] if "." in n else n
        if "shoes" in asset or "boots" in asset or "flats" in asset:
            return "Boots", "Boots", "boots"
        if "beard" in asset or "moustache" in asset:
            return "Facial_" + asset, "Facial_" + asset, "facial"
        return "Cloth_" + asset, "Cloth_" + asset, "clothes"
    if n == p + "body":
        return "Body", "Skin", "body"
    if "high-poly" in n or "low-poly" in n:
        return "Eyes", "Eyes", "eyes"
    if "eyebrow" in n:
        return "Brows", "Brows", "brows"
    if "eyelash" in n:
        return "Lashes", "Lashes", "lashes"
    if "teeth" in n:
        return "Teeth", "Teeth", "teeth"
    if "tongue" in n:
        return "Tongue", "Tongue", "tongue"
    if "shoes" in n:
        return "Boots", "Boots", "boots"
    if ".hair_" in n:
        s = n.split(".hair_")[1]
        return "Hair_" + s, "Hair_" + s, "hair"
    if ".facial_" in n:
        s = n.split(".facial_")[1]
        return "Facial_" + s, "Facial_" + s, "facial"
    if n.startswith(cname + "_"):
        part = n[len(cname) + 1:]
        if part == "Top":
            return "Top", "Garment_Top", "garment"
        if part == "Pants":
            return "Pants", "Garment_Pants", "garment"
        if part == "Gloves":
            return "Gloves", "Gloves", "gloves"
        return part, None, "armor" if part.startswith(ARMOR) else "gear"
    # Default hair (from the base character definition).
    return "Hair_" + default_hair, "Hair_" + default_hair, "hair"


def strip_hidden_body(body, shells):
    """Delete body faces fully inside the suit shells (keeps one face ring at openings)."""
    covered = set()
    for sh in shells:
        interior = [v for i, v in enumerate(sh.vmap) if not sh.is_b[i]]
        covered.update(interior)
    # Grow the kept border by one ring: a face is deleted only if all its verts are covered and none touch a boundary.
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    kill = [f for f in bm.faces if all(v.index in covered for v in f.verts)
            and all(all(nv.index in covered for nv in (e.other_vert(v) for e in v.link_edges)) for v in f.verts)]
    bmesh.ops.delete(bm, geom=kill, context="FACES_ONLY")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    return len(kill)


def export(cid, cname, body, rig, gender, default_hair, shells, height, extra=None):
    out_dir = os.path.join(UNITY_CHARS, cname)
    tex_dir = os.path.join(out_dir, "Textures")
    os.makedirs(tex_dir, exist_ok=True)
    meshes = []
    textures = {}
    for o in [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig]:
        name, mat, kind = classify(o, cname, default_hair)
        imgs = images_of(o)
        o.name = name
        o.data.name = name
        if mat:
            set_single_material(o, mat)
            if kind == "garment":
                part = "Top" if name == "Top" else "Pants"
                textures[mat] = [f"{cname}_{part}_Mask.png", f"{cname}_{part}_Normal.png"]
            elif imgs:
                # Copy the asset's textures (diffuse first) next to the model.
                files = []
                for src in imgs:
                    if os.path.isfile(src):
                        dst = os.path.join(tex_dir, f"{name}_{os.path.basename(src)}")
                        shutil.copyfile(src, dst)
                        files.append(os.path.basename(dst))
                textures[mat] = files
        else:
            mats = [m.name for m in o.data.materials]
            mat = mats[0] if mats else "Armor"
        mat_names = [m.name for m in o.data.materials]
        shapes = [k.name for k in o.data.shape_keys.key_blocks[1:]] if o.data.shape_keys else []
        meshes.append({"name": name, "kind": kind, "materials": mat_names, "verts": len(o.data.vertices), "tris": sum(len(p.vertices) - 2 for p in o.data.polygons), "shapes": shapes})
    removed = strip_hidden_body(body, shells)
    # Skin variants and the shared detail maps.
    skins = {}
    for tone, folder in SKINS[gender].items():
        d = os.path.join(MPFB_DATA, "skins", folder)
        diffuse = [f for f in os.listdir(d) if f.lower().endswith(".png") and "nrm" not in f.lower() and "spec" not in f.lower()]
        if diffuse:
            dst = f"Skin_{tone}.png"
            shutil.copyfile(os.path.join(d, diffuse[0]), os.path.join(tex_dir, dst))
            skins[tone] = dst
    aks = os.path.join(MPFB_DATA, "skins", "mindfront_aksel_skin")
    if gender == "male":
        shutil.copyfile(os.path.join(aks, "Aksel_Skin_NRM.png"), os.path.join(tex_dir, "Skin_Normal.png"))
        shutil.copyfile(os.path.join(aks, "Aksel_Skin_SPEC.png"), os.path.join(tex_dir, "Skin_Spec.png"))
    eyes_dir = os.path.join(MPFB_DATA, "eyes", "materials")
    for col in ("brown", "grey", "blue", "green"):
        shutil.copyfile(os.path.join(eyes_dir, col + "_eye.png"), os.path.join(tex_dir, f"Eye_{col}.png"))
    # FBX (Unity conventions: -Z forward, Y up, transforms applied, deform bones only, no leaf bones).
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for o in rig.children:
        o.select_set(True)
    bpy.context.view_layer.objects.active = rig
    fbx = os.path.join(out_dir, cname + ".fbx")
    bpy.ops.export_scene.fbx(
        filepath=fbx, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Z", axis_up="Y", bake_space_transform=True, use_mesh_modifiers=False, mesh_smooth_type="FACE",
        use_tspace=True, add_leaf_bones=False, use_armature_deform_only=True, bake_anim=False, path_mode="STRIP",
        embed_textures=False, use_custom_props=False)
    manifest = {
        "character": cid, "name": cname, "gender": gender, "height": height, "fbx": cname + ".fbx",
        "meshes": meshes, "textures": textures, "skins": skins, "defaultHair": default_hair,
        "hairStyles": sorted(m["name"][5:] for m in meshes if m["kind"] == "hair"),
        "facialHair": sorted(m["name"][7:] for m in meshes if m["kind"] == "facial"),
        "morphs": sorted({s for m in meshes for s in m["shapes"] if s.startswith("m_")}),
        "expressions": sorted({s for m in meshes for s in m["shapes"] if s.startswith("x_")}),
        "hiddenBodyFacesRemoved": removed,
    }
    if extra:
        manifest.update(extra)
    with open(os.path.join(out_dir, cname + ".manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print("EXPORTED", fbx, "meshes", len(meshes), "removed body faces", removed, "tris", sum(m["tris"] for m in meshes))
    return manifest


# ============================================================================= HD export (2026-10 rebuild)


def strip_covered(body, cover_sets):
    """Delete body faces hidden under garments: a face goes when all its vertices (and their neighbours) are
    interior to some garment shell."""
    covered = set()
    for s in cover_sets:
        covered |= s
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    kill = [f for f in bm.faces if all(v.index in covered for v in f.verts)
            and all(all(e.other_vert(v).index in covered for e in v.link_edges) for v in f.verts)]
    bmesh.ops.delete(bm, geom=kill, context="FACES_ONLY")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    return len(kill)


def clean_textures(tex_dir, keep):
    """Remove texture files (and Unity .meta / generated _grey copies) that this export no longer produces."""
    keep = set(keep)
    removed = []
    for f in os.listdir(tex_dir):
        if not f.lower().endswith(".png"):
            continue
        stem = f[:-4]
        if f in keep:
            continue
        src = stem[:-5] + ".png" if stem.endswith("_grey") else f
        if src in keep:
            if stem.endswith("_grey"):
                # stale desaturated copy: Unity regenerates it from the new source
                for g in (f, f + ".meta"):
                    p = os.path.join(tex_dir, g)
                    if os.path.exists(p):
                        os.remove(p)
                removed.append(f)
            continue
        for g in (f, f + ".meta"):
            p = os.path.join(tex_dir, g)
            if os.path.exists(p):
                os.remove(p)
        removed.append(f)
    return removed


def export_hd(cid, cname, rig, gender, default_hair, height, tex_map, extra=None, out_dir=None, removed=0):
    """FBX + manifest for the HD build. tex_map: {material: [files]} for everything this build wrote."""
    out_dir = out_dir or os.path.join(UNITY_CHARS, cname)
    tex_dir = os.path.join(out_dir, "Textures")
    os.makedirs(tex_dir, exist_ok=True)
    meshes = []
    textures = dict(tex_map)
    for o in [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig]:
        name, mat, kind = classify(o, cname, default_hair)
        imgs = images_of(o)
        o.name = name
        o.data.name = name
        if name == "Boots":
            kind = "boots"
        if mat:
            set_single_material(o, mat)
            if mat not in textures and imgs and kind in ("brows", "lashes", "teeth", "tongue", "facial", "hair", "clothes", "boots"):
                files = []
                for src in imgs:
                    if os.path.isfile(src):
                        dst = os.path.join(tex_dir, f"{name}_{os.path.basename(src)}")
                        shutil.copyfile(src, dst)
                        files.append(os.path.basename(dst))
                textures[mat] = files
        if "UVOld" in o.data.uv_layers:
            o.data.uv_layers.remove(o.data.uv_layers["UVOld"])
        mat_names = [m.name for m in o.data.materials]
        shapes = [k.name for k in o.data.shape_keys.key_blocks[1:]] if o.data.shape_keys else []
        meshes.append({"name": name, "kind": kind, "materials": mat_names, "verts": len(o.data.vertices),
                       "tris": sum(len(p.vertices) - 2 for p in o.data.polygons), "shapes": shapes})
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for o in rig.children:
        if o.type == "MESH":
            o.select_set(True)
    bpy.context.view_layer.objects.active = rig
    fbx = os.path.join(out_dir, cname + ".fbx")
    bpy.ops.export_scene.fbx(
        filepath=fbx, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Z", axis_up="Y", bake_space_transform=True, use_mesh_modifiers=False, mesh_smooth_type="FACE",
        use_tspace=True, add_leaf_bones=False, use_armature_deform_only=True, bake_anim=False, path_mode="STRIP",
        embed_textures=False, use_custom_props=False)
    hair_styles = sorted(m["name"][5:] for m in meshes if m["kind"] == "hair")
    facial = sorted(m["name"][7:] for m in meshes if m["kind"] == "facial")
    visible = [m for m in meshes if not ((m["kind"] == "hair" and m["name"] != "Hair_" + default_hair) or m["kind"] == "facial")]
    manifest = {
        "character": cid, "name": cname, "gender": gender, "height": height, "fbx": cname + ".fbx",
        "meshes": meshes, "textures": textures, "defaultHair": default_hair, "hairStyles": hair_styles, "facialHair": facial,
        "morphs": sorted({s for m in meshes for s in m["shapes"] if s.startswith("m_")}),
        "expressions": sorted({s for m in meshes for s in m["shapes"] if s.startswith("x_")}),
        "hiddenBodyFacesRemoved": removed,
        "visibleTris": sum(m["tris"] for m in visible),
        "pipeline": "hd-2026-10",
    }
    if extra:
        manifest.update(extra)
    with open(os.path.join(out_dir, cname + ".manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print("EXPORTED", fbx, "meshes", len(meshes), "visible tris", manifest["visibleTris"])
    return manifest
