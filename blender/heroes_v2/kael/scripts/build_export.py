"""Stage 7 - Kael v2 export: FBX + manifest (existing schema + "correctives") + textures into
unity/EchoesOfAether/Assets/Art/Characters/Kael.

  blender -b blends/kael_s6_deform.blend --python build_export.py -- [--dry]
"""
import bpy, sys, os, json, shutil, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
import meshops, export_hero

a = K.args()
PRE = K.PRE
rig = bpy.data.objects["Kael"]
OUT = K.UNITY_KAEL
TEXO = os.path.join(OUT, "Textures")
os.makedirs(TEXO, exist_ok=True)
# ---- scene cleanup: only the rig and its game meshes are exported
for o in list(bpy.data.objects):
    if o.type == "MESH" and (o.name in ("BodyMH", "BodyFull") or o.name.endswith(("_HI", "_HIB", "_HPG")) or o.get("k_preview") or o.name.startswith("prev_")):
        bpy.data.objects.remove(o, do_unlink=True)
for o in list(bpy.data.objects):
    if o.type not in ("MESH", "ARMATURE") or (o.type == "ARMATURE" and o is not rig):
        bpy.data.objects.remove(o, do_unlink=True)
# ---- Kael's face proportions baked into the basis (stronger jaw/chin, fuller cheekbones, firmer lips). Baked rather
# than set as runtime morph defaults: Unity's calculated blend-shape normals differ from the imported normals at the
# stripped mesh's open borders (lid margins, mouth, nostrils) and draw pale halos there whenever a face morph is
# non-zero. Sliders still work relative to this face. Every mesh carrying these keys (beard, collar, hair) gets the
# same delta, and all of its other keys are shifted with the basis so their own deltas are unchanged.
from build_export_morphs import BAKE_MORPHS
for o in bpy.data.objects:
    if o.type != "MESH" or not o.data.shape_keys:
        continue
    kb = o.data.shape_keys.key_blocks
    hits = [(n, w) for n, w in BAKE_MORPHS.items() if n in kb]
    if not hits:
        continue
    nv = len(o.data.vertices)
    def _co(k):
        c = np.zeros(nv * 3); k.data.foreach_get("co", c); return c
    basis = _co(kb[0])
    delta = sum(w * (_co(kb[n]) - basis) for n, w in hits)
    for k in kb:
        k.data.foreach_set("co", _co(k) + delta)
    o.data.vertices.foreach_set("co", _co(kb[0]))
    o.data.update()
    K.log("BAKED morphs", o.name, [n for n, _ in hits], "max mm", round(float(np.abs(delta).max()) * 1000, 2))
# ---- built-in concept hair (hair_k3.py): Head-rigid cards, material Hair_<style>, grey alpha texture tinted at runtime
HAIR_BLEND = os.path.join(K.BLENDS, "hair_k3.blend")
CONCEPT_HAIR = None
if os.path.exists(HAIR_BLEND):
    with bpy.data.libraries.load(HAIR_BLEND) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith("Hair_")]
    for ho in dst.objects:
        bpy.context.scene.collection.objects.link(ho)
        CONCEPT_HAIR = ho.name[5:]
        ho.matrix_world = rig.matrix_world.copy() @ rig.matrix_world.inverted() @ ho.matrix_world
        for g in list(ho.vertex_groups):
            ho.vertex_groups.remove(g)
        vg = ho.vertex_groups.new(name=PRE + "Head")
        vg.add(list(range(len(ho.data.vertices))), 1.0, "REPLACE")
        mw = ho.matrix_world.copy()
        ho.parent = rig
        ho.matrix_world = mw
        ho.modifiers.clear()
        m_ = ho.modifiers.new("Armature", "ARMATURE"); m_.object = rig
        hm = bpy.data.materials.get(ho.name) or bpy.data.materials.new(ho.name)
        ho.data.materials.clear(); ho.data.materials.append(hm)
        ho.data.polygons.foreach_set("material_index", np.zeros(len(ho.data.polygons), np.int32))
        K.log("HAIR built-in", ho.name, len(ho.data.polygons), "faces")
KIND = {"Body": "body", "Eyes": "eyes", "Brows": "brows", "Lashes": "lashes", "Teeth": "teeth", "Tongue": "tongue",
        "Top": "garment", "Jacket": "garment", "Pants": "garment", "Gloves": "gloves", "Boots": "boots", "Collar": "gear", "ChestRig": "gear", "Belt": "gear",
        "EyeOcclusion": "eyes", "EyeWet": "eyes"}
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
issues = []
for o in meshes:
    if o.parent is not rig:
        mw = o.matrix_world.copy()
        o.parent = rig
        o.matrix_world = mw
    if not any(m.type == "ARMATURE" for m in o.modifiers):
        m = o.modifiers.new("Armature", "ARMATURE"); m.object = rig
    for m in list(o.modifiers):
        if m.type != "ARMATURE":
            o.modifiers.remove(m)
        else:
            m.object = rig
            m.use_deform_preserve_volume = False
    me = o.data
    for uv in list(me.uv_layers):
        if uv.name == "UVOld":
            me.uv_layers.remove(uv)
    # weights: <= 4 influences, normalised, nothing unweighted
    names, W = meshops.get_weights(o)
    if names:
        W2 = meshops.limit_normalize(W, 4, 0.005)
        zero = W2.sum(1) == 0
        if zero.any():
            issues.append(f"{o.name}: {int(zero.sum())} unweighted verts -> Head/Hips")
            fb = PRE + ("Head" if o.name in ("Body", "Eyes", "Brows", "Lashes", "Teeth", "Tongue", "EyeOcclusion", "EyeWet") or o.name.startswith(("Hair_", "Facial_")) else "Hips")
            if fb not in names:
                names.append(fb); W2 = np.concatenate([W2, np.zeros((len(W2), 1))], 1)
            W2[zero, names.index(fb)] = 1.0
        meshops.set_weights(o, names, W2)
    # drop empty groups / non-deform groups
    for g in list(o.vertex_groups):
        if not g.name.startswith(PRE):
            o.vertex_groups.remove(g)
    for p in me.polygons:
        p.use_smooth = True
    # shape keys: drop keys that do not move anything
    if me.shape_keys:
        basis, shapes = meshops.shape_arrays(o)
        keep = {n: c for n, c in shapes.items() if np.abs(c - basis).max() > 1e-6}
        meshops.set_shapes(o, basis, keep)
# ---- manifest pieces
tex_prod = json.load(open(os.path.join(K.LOGS, "tex_produced.json")))
face = json.load(open(os.path.join(K.LOGS, "face.json")))
corr = json.load(open(os.path.join(K.LOGS, "correctives.json"))) if os.path.exists(os.path.join(K.LOGS, "correctives.json")) else []
textures = {}
for mat, files in tex_prod.items():
    textures[mat] = files
textures["Skin"] = ["Skin_medium.png", "Skin_Normal.png", "Skin_MaskMap.png"]
textures["Eyes"] = ["Eye_grey.png"]
textures["Brows"] = ["Brows_eyebrow009.png"]
textures["Lashes"] = ["Lashes_eyelashes01.png"]
textures["Teeth"] = ["Teeth_teeth.png"]
textures["Tongue"] = ["Tongue_tongue01_diffuse.png"]
old_dir = os.path.join(K.BLENDS, "old_export")
mesh_info = []
for o in sorted(meshes, key=lambda x: x.name):
    n = o.name
    kind = KIND.get(n) or ("hair" if n.startswith("Hair_") else "facial" if n.startswith("Facial_") else "armor")
    mats = [m.name for m in o.data.materials if m]
    if kind in ("hair", "facial"):
        fn = f"{n}_Color.png"
        if os.path.exists(os.path.join(old_dir, fn)) or os.path.exists(os.path.join(K.TEX, fn)):
            textures[n] = [fn]
    shapes = [k.name for k in o.data.shape_keys.key_blocks[1:]] if o.data.shape_keys else []
    mesh_info.append({"name": n, "kind": kind, "materials": mats, "verts": len(o.data.vertices),
                      "tris": sum(len(p.vertices) - 2 for p in o.data.polygons), "shapes": shapes})
hair_styles = sorted(m["name"][5:] for m in mesh_info if m["kind"] == "hair")
facial = sorted(m["name"][7:] for m in mesh_info if m["kind"] == "facial")
default_hair = CONCEPT_HAIR if CONCEPT_HAIR in hair_styles else ("swept" if "swept" in hair_styles else "short")
visible = [m for m in mesh_info if not ((m["kind"] == "hair" and m["name"] != "Hair_" + default_hair) or m["kind"] == "facial")]
height = round(float(max((o.matrix_world @ v.co).z for o in meshes if o.name in ("Body",) for v in o.data.vertices)), 3)
material_defs = {
    "Garment_Top": {"type": "garment", "mask": "Kael_Top_Mask.png", "normal": "Kael_Top_Normal.png", "tint": "outfit/accent (runtime composite)"},
    "Garment_Pants": {"type": "garment", "mask": "Kael_Pants_Mask.png", "normal": "Kael_Pants_Normal.png", "tint": "outfit/accent (runtime composite)"},
    "Armor": {"type": "lit", "baseMap": "Kael_Armor_BaseColor.png", "normal": "Kael_Armor_Normal.png", "maskMap": "Kael_Armor_MaskMap.png",
              "maskMapLayout": "R metallic, G occlusion, B paint mask, A smoothness", "tint": "armor"},
    "Boots": {"type": "lit", "baseMap": "Kael_Boots_BaseColor.png", "normal": "Kael_Boots_Normal.png", "maskMap": "Kael_Boots_MaskMap.png",
              "maskMapLayout": "R metallic, G occlusion, B paint mask, A smoothness", "tint": None},
    "Gloves": {"type": "lit", "baseMap": "Kael_Gloves_BaseColor.png", "normal": "Kael_Gloves_Normal.png", "maskMap": "Kael_Gloves_MaskMap.png",
               "maskMapLayout": "R metallic, G occlusion, B paint mask, A smoothness", "tint": "outfit*0.75"},
    "Cloth_Gear": {"type": "lit", "baseMap": "Kael_Gear_BaseColor.png", "normal": "Kael_Gear_Normal.png", "maskMap": "Kael_Gear_MaskMap.png",
                   "maskMapLayout": "R metallic, G occlusion, B paint mask, A smoothness", "tint": None,
                   "note": "plate carrier, placard pouches, belt webbing, straps: fixed colours (CharacterBuilder Cloth_* path: BaseMap + Normal + MaskMap)"},
    "Cloth_Jacket": {"type": "lit", "baseMap": "Kael_Jacket_BaseColor.png", "normal": "Kael_Jacket_Normal.png", "maskMap": "Kael_Jacket_MaskMap.png",
                     "maskMapLayout": "R metallic, G occlusion, B paint mask, A smoothness", "tint": None,
                     "note": "matte black diamond-quilted bomber jacket + stand collar: fixed colours (CharacterBuilder Cloth_* path: BaseMap + Normal + MaskMap)"},
    "Cloth_Brass": {"type": "lit", "baseMap": "Kael_Brass_BaseColor.png", "normal": "Kael_Brass_Normal.png", "maskMap": "Kael_Brass_MaskMap.png",
                    "maskMapLayout": "R metallic, G occlusion, B paint mask, A smoothness", "tint": None, "note": "brass knuckle studs (Cloth_* path)"},
    "Holo": {"type": "holo", "baseMap": "Kael_Holo.png", "note": "EOA/HoloSleeve additive holographic wrap on ForearmGuardL (RGB pattern, A coverage), tinted by the glow colour"},
    "Skin": {"type": "skin", "normal": "Skin_Normal.png", "maskMap": "Skin_MaskMap.png"},
    "Metal": {"type": "lit", "color": "#a7adb5", "metallic": 1.0, "smoothness": 0.68},
    "Glow": {"type": "emissive", "tint": "glow"}, "Glow2": {"type": "emissive", "tint": "glow2"}, "Screen": {"type": "emissive", "tint": "glow*0.6"},
}
for hs in hair_styles:
    material_defs["Hair_" + hs] = {"type": "hair", "baseMap": f"Hair_{hs}_Color.png", "alphaClip": 0.35 if hs == "wavy" else 0.4, "tint": "hair"}
# makeover: the built-in concept hair carries per-vertex strand data in its second UV set (hair_k4.strand_data)
if CONCEPT_HAIR and "Hair_" + CONCEPT_HAIR in material_defs:
    ho = bpy.data.objects.get("Hair_" + CONCEPT_HAIR)
    if ho is not None and ho.data.uv_layers.get("Strand") is not None:
        material_defs["Hair_" + CONCEPT_HAIR]["strandData"] = True
        material_defs["Hair_" + CONCEPT_HAIR]["strandDataLayout"] = "UV2: x root (0) -> tip (1), y inner-layer occlusion"
if "EyeOcclusion" in bpy.data.objects:
    material_defs["EyeOcclusion"] = {"type": "eyeOcclusion", "note": "EOA/EyeOcclusion multiply shell, UV.x = occlusion (eye_fx.py)"}
if "EyeWet" in bpy.data.objects:
    material_defs["EyeWet"] = {"type": "eyeWet", "note": "EOA/EyeWet additive tear meniscus along the lower lid, UV.x = mask (eye_fx.py)"}
# shared skin shading parameters (CharacterBuilder EOA/Skin): pore detail tiled for ~24 mm per tile on the face
_suv = os.path.join(K.LOGS, "skin_uv.json")
_mpu = (json.load(open(_suv)).get("face_m_per_uv") if os.path.exists(_suv) else None) or 0.3
skin_shading = {"poreTiling": round(float(_mpu) / 0.024, 2), "poreStrength": 0.5, "sssTint": [0.9, 0.32, 0.26], "sssStrength": 0.7,
                "sssWrap": 0.55, "faceMetresPerUV": round(float(_mpu), 4)}
eye_shading = {"lidShadow": 0.18 if "EyeOcclusion" in bpy.data.objects else 0.5}
manifest = {
    "character": "kael", "name": "Kael", "gender": "male", "height": height, "fbx": "Kael.fbx",
    "meshes": mesh_info, "textures": textures, "defaultHair": default_hair, "hairStyles": hair_styles, "facialHair": facial,
    "morphs": sorted({s for m in mesh_info for s in m["shapes"] if s.startswith("m_")}),
    "expressions": sorted({s for m in mesh_info for s in m["shapes"] if s.startswith("x_")}),
    "hiddenBodyFacesRemoved": json.load(open(os.path.join(K.LOGS, "strip.json"))).get("removed", 0),
    "visibleTris": sum(m["tris"] for m in visible),
    "pipeline": "heroes_v2-kael",
    "skins": face["skins"],
    "skinMaps": {"normal": "Skin_Normal.png", "maskMap": "Skin_MaskMap.png", "stubble": "Skin_Stubble.png"},
    "eyeLayout": {"note": "iris centred at uv (0.5, 0.5); ellipse d = sqrt(4*du^2 + dv^2) < 0.085 (matches CharacterModel.ApplyEyes)",
                  "variants": ["Eye_grey.png", "Eye_brown.png", "Eye_blue.png", "Eye_green.png"]},
    "palette": {"outfit": "#5c5848", "accent": "#1f2126", "armor": "#c9cdd3", "glow": "#00e5ff", "glow2": "#ff2bd6", "skin": "#b98a6e",
                "hair": "#4f3a2e", "eyes": "#5b3a22"},
    "hairAlphaCutoff": {"default": 0.4, "swept_fade": 0.4, "curly": 0.4, "wavy": 0.35, "bun": 0.38, "frenchbraid": 0.38, "beard": 0.35, "Brows": 0.42, "Lashes": 0.32},
    "hairDye": {"wavy": "Hair_wavy_Dye.png"},
    "optionalParts": {"ChestRig": "plate carrier over the jacket (toggles with ChestPlate)"},
    "materialDefs": material_defs,
    "skinShading": skin_shading,
    "eyeShading": eye_shading,
    "twistBones": [
        {"bone": f"{PRE}{s}ForeArmTwist", "source": f"{PRE}{s}Hand", "reference": f"{PRE}{s}ForeArm", "weight": 0.5, "mode": "follow"} for s in ("Left", "Right")
    ] + [
        {"bone": f"{PRE}{s}ArmTwist", "source": f"{PRE}{s}Arm", "reference": f"{PRE}{s}Shoulder", "weight": 0.5, "mode": "counter"} for s in ("Left", "Right")
    ],
    "correctives": [{k: c[k] for k in ("shape", "bone", "parent", "axis", "from", "to")} for c in corr],
    "correctivesNote": "axis in Blender world space of the rest pose (Z up, -Y forward, +X character left); see CorrectiveShapes.cs",
    "lod1": None,
}
K.log("MANIFEST", "meshes", len(mesh_info), "visibleTris", manifest["visibleTris"], "correctives", len(corr), "hair", hair_styles, "issues", issues)
if K.opt(a, "--dry"):
    raise SystemExit(0)
# ---- textures
copy = set()
for mat, files in textures.items():
    for f in files:
        copy.add(f)
copy |= set(face["skins"].values()) | {"Skin_Normal.png", "Skin_MaskMap.png", "Skin_Stubble.png", "Eye_grey.png", "Eye_brown.png", "Eye_blue.png", "Eye_green.png"}
copied = []
for f in sorted(copy):
    src = os.path.join(K.TEX, f)
    if not os.path.exists(src):
        src = os.path.join(old_dir, f)
    if os.path.exists(src):
        shutil.copyfile(src, os.path.join(TEXO, f))
        copied.append(f)
    else:
        issues.append("missing texture " + f)
if os.path.exists(os.path.join(old_dir, "Hair_wavy_Dye.png")):
    shutil.copyfile(os.path.join(old_dir, "Hair_wavy_Dye.png"), os.path.join(TEXO, "Hair_wavy_Dye.png"))
    copied.append("Hair_wavy_Dye.png")
removed = export_hero.clean_textures(TEXO, copied)
# ---- FBX (same conventions as the previous exports)
bpy.ops.object.select_all(action="DESELECT")
rig.select_set(True)
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = rig
fbx = os.path.join(OUT, "Kael.fbx")
bpy.ops.export_scene.fbx(
    filepath=fbx, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_scale_options="FBX_SCALE_ALL",
    axis_forward="-Z", axis_up="Y", bake_space_transform=True, use_mesh_modifiers=False, mesh_smooth_type="FACE",
    use_tspace=True, add_leaf_bones=False, use_armature_deform_only=True, bake_anim=False, path_mode="STRIP",
    embed_textures=False, use_custom_props=False)
with open(os.path.join(OUT, "Kael.manifest.json"), "w") as f:
    json.dump(manifest, f, indent=1)
# stale old-pipeline LOD file (not produced by this pipeline)
for stale in ("Kael_LOD1.fbx", "Kael_LOD1.fbx.meta"):
    p = os.path.join(OUT, stale)
    if os.path.exists(p):
        os.remove(p)
K.log("EXPORTED", fbx, "textures", len(copied), "removed", removed, "issues", issues)
