"""MPFB human assembly for Giva + catalog attachment previews (hair/eyewear as the game fits them)."""
import bpy, os, math, json
import numpy as np
from mathutils import Vector, Matrix
import gv
from bl_ext.user_default.mpfb.services.humanservice import HumanService


def build_human(phenotype, targets, assets, name=gv.RIG, subdiv=0):
    """Create the MPFB human (base mesh with helpers masked, mixamo_unity rig, eyes/brows/lashes/teeth/tongue).
    Returns (body, rig)."""
    info = HumanService._create_default_human_info_dict()
    info["name"] = name
    info["phenotype"] = phenotype
    info["rig"] = assets["rig"]
    info["eyes"] = assets["eyes"]
    info["eyebrows"] = assets["eyebrows"]
    info["eyelashes"] = assets["eyelashes"]
    info["teeth"] = assets["teeth"]
    info["tongue"] = assets["tongue"]
    info["hair"] = ""
    info["skin_mhmat"] = assets["skin"]
    info["skin_material_type"] = "ENHANCED_SSS"
    info["eyes_material_type"] = "MAKESKIN"
    info["targets"] = [{"target": t.split("/")[-1], "value": v} for t, v in targets]
    info["clothes"] = []
    st = HumanService.get_default_deserialization_settings()
    st["subdiv_levels"] = subdiv
    st["detailed_helpers"] = True
    st["mask_helpers"] = True
    st["load_clothes"] = False
    body = HumanService.deserialize_from_dict(info, st)
    rig = body.parent
    rig.name = rig.data.name = name
    return body, rig


def find_parts(rig):
    parts = {}
    for o in bpy.data.objects:
        if o.type != "MESH" or o.parent is not rig:
            continue
        n = o.name.lower()
        if n.endswith(".body"):
            parts["body"] = o
        elif "high-poly" in n or "low-poly" in n:
            parts["eyes"] = o
        elif "eyebrow" in n:
            parts["brows"] = o
        elif "eyelash" in n:
            parts["lashes"] = o
        elif "teeth" in n:
            parts["teeth"] = o
        elif "tongue" in n:
            parts["tongue"] = o
    return parts


# ----------------------------------------------------------------------------- catalog attachments (preview)

def catalog_item(category, item_id, hero="lyra"):
    cat = json.load(open(os.path.join(gv.CUSTOM, "catalog.json")))
    for it in cat.get(category, []):
        if it.get("hero") == hero and it.get("id") == item_id:
            return it
    return None


def _import_fbx(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=False)
    return [o for o in bpy.data.objects if o not in before]


def attach_catalog(rig, category, item_id, tint="#2a1a1e"):
    """Import a catalog item and place it exactly as the game would on `rig` (skinned items: bind poses of the
    item's own armature remapped to rig's bones by name; rigid items: parented to the bone, identity local).
    Returns the mesh objects (parented to rig with an Armature modifier when skinned)."""
    it = catalog_item(category, item_id)
    if it is None:
        gv.log("catalog item missing", category, item_id)
        return []
    new = _import_fbx(os.path.join(gv.CUSTOM, it["file"] + ".fbx"))
    arm = next((o for o in new if o.type == "ARMATURE"), None)
    meshes = [o for o in new if o.type == "MESH"]
    out = []
    for m in meshes:
        mw = m.matrix_world.copy()
        if it.get("kind") == "skinned" and arm is not None:
            co = np.array([mw @ v.co for v in m.data.vertices])
            # vertex' = sum_b w_b * Rest_new_b @ Rest_old_b^-1 @ vertex  (bind pose remap, as Unity does)
            Ws = {}
            gi = {g.index: g.name for g in m.vertex_groups}
            nv = len(co)
            acc = np.zeros((nv, 3))
            wsum = np.zeros(nv)
            mats = {}
            for g in m.vertex_groups:
                bo = arm.data.bones.get(g.name)
                bn = rig.data.bones.get(g.name)
                if bo is None or bn is None:
                    continue
                M = (rig.matrix_world @ bn.matrix_local) @ (arm.matrix_world @ bo.matrix_local).inverted()
                mats[g.index] = np.array(M)
            for v in m.data.vertices:
                for g in v.groups:
                    M = mats.get(g.group)
                    if M is None or g.weight <= 0:
                        continue
                    p = M[:3, :3] @ co[v.index] + M[:3, 3]
                    acc[v.index] += p * g.weight
                    wsum[v.index] += g.weight
            ok = wsum > 0
            co[ok] = acc[ok] / wsum[ok, None]
            m.parent = None
            m.matrix_world = Matrix.Identity(4)
            for v, c in zip(m.data.vertices, co):
                v.co = c
            for md in list(m.modifiers):
                m.modifiers.remove(md)
            gv.link_armature(m, rig)
        else:
            bone = rig.data.bones[it.get("bone", "mixamorig:Head")]
            # rigid: the FBX mesh is authored in the bone's local frame (Unity parent with identity local)
            m.parent = None
            local = mw
            m.matrix_world = rig.matrix_world @ bone.matrix_local @ _unity_bone_fix() @ local
            m.parent = rig
            m.parent_type = "BONE"
            m.parent_bone = bone.name
            m.matrix_world = rig.matrix_world @ bone.matrix_local @ _unity_bone_fix() @ local
        out.append(m)
    for o in new:
        if o.type != "MESH":
            gv.remove(o)
    if category == "hair":
        mat = hair_preview_material(os.path.join(gv.CUSTOM, it["baseMap"] + ".png"), tint, it.get("alphaCutoff", 0.4))
        for m in out:
            m.data.materials.clear()
            m.data.materials.append(mat)
    return out


def _unity_bone_fix():
    return Matrix.Identity(4)


def hair_preview_material(tex_path, tint, cutoff):
    m = bpy.data.materials.new("prev_hair")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bs.outputs[0], out.inputs[0])
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = bpy.data.images.load(tex_path, check_existing=True)
    tx.image.colorspace_settings.name = "sRGB"
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    c = gv.srgb_to_lin(gv.hexrgb(tint))
    mul.inputs[7].default_value = (*c, 1)
    nt.links.new(tx.outputs["Color"], mul.inputs[6])
    nt.links.new(mul.outputs[2], bs.inputs["Base Color"])
    gt = nt.nodes.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = cutoff
    nt.links.new(tx.outputs["Alpha"], gt.inputs[0])
    nt.links.new(gt.outputs[0], bs.inputs["Alpha"])
    bs.inputs["Roughness"].default_value = 0.45
    bs.inputs["Specular IOR Level"].default_value = 0.35
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "DITHERED"
    m.use_backface_culling = False
    return m
