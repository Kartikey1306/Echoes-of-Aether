"""Build an MPFB human from a phenotype/targets definition (system assets only, no hair)."""
import bpy, importlib
import numpy as np
from bl_ext.user_default.mpfb.services.humanservice import HumanService


def build(name, phenotype, targets, assets, rig="mixamo_unity", skin_type="ENHANCED_SSS"):
    info = HumanService._create_default_human_info_dict()
    info["name"] = name
    info["phenotype"] = phenotype
    info["rig"] = rig
    info["eyes"] = assets.get("eyes", "high-poly/high-poly.mhclo")
    info["eyebrows"] = assets.get("eyebrows", "")
    info["eyelashes"] = assets.get("eyelashes", "")
    info["teeth"] = assets.get("teeth", "teeth_base/teeth_base.mhclo")
    info["tongue"] = assets.get("tongue", "tongue01/tongue01.mhclo")
    info["hair"] = assets.get("hair", "")
    info["skin_mhmat"] = assets.get("skin", "young_caucasian_male/young_caucasian_male.mhmat")
    info["skin_material_type"] = skin_type
    info["eyes_material_type"] = "MAKESKIN"
    info["targets"] = [{"target": t.split("/")[-1], "value": v} for t, v in targets]
    info["clothes"] = []
    settings = HumanService.get_default_deserialization_settings()
    settings["subdiv_levels"] = 0
    settings["detailed_helpers"] = True
    settings["mask_helpers"] = True
    settings["load_clothes"] = False
    body = HumanService.deserialize_from_dict(info, settings)
    rig_o = body.parent
    rig_o.name = rig_o.data.name = name
    return body


def landmarks(rig):
    return {b.name.split(":")[1]: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones if ":" in b.name}


def tails(rig):
    return {b.name.split(":")[1]: np.array(rig.matrix_world @ b.tail_local) for b in rig.data.bones if ":" in b.name}


def proportions(body, rig, co=None):
    """Height, head height (chin..crown), heads tall, widths and the leg ratio (metres)."""
    if co is None:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = body.evaluated_get(dg)
        co = np.array([(body.matrix_world @ v.co)[:] for v in ev.data.vertices])
    L = landmarks(rig)
    H = co[:, 2].max()
    head = co[co[:, 2] > L["Neck"][2] + 0.03]
    front = head[(np.abs(head[:, 0]) < 0.012) & (head[:, 1] < L["LeftEye"][1])]
    chin = front[:, 2].min() if len(front) else L["Head"][2] - 0.05

    def width(z, band=0.01, xmax=0.4):
        s = co[(np.abs(co[:, 2] - z) < band) & (np.abs(co[:, 0]) < xmax)]
        return float(s[:, 0].max() - s[:, 0].min()) if len(s) else 0.0

    return {"height": round(float(H), 3), "head_h": round(float(H - chin), 3), "heads": round(float(H / (H - chin)), 2),
            "shoulder_joint_w": round(float(L["LeftArm"][0] - L["RightArm"][0]), 3),
            "deltoid_w": round(width(L["LeftArm"][2] - 0.05, xmax=0.4), 3),
            "chest_w": round(width(L["Spine2"][2] + 0.08, xmax=0.2), 3), "waist_w": round(width(L["Spine"][2] + 0.02, xmax=0.2), 3),
            "hip_w": round(width(L["Hips"][2] - 0.05, xmax=0.25), 3), "leg_ratio": round(float(L["Hips"][2] / H), 3),
            "head_bone": [round(float(x), 4) for x in L["Head"]], "eye_sep": round(float(L["LeftEye"][0] - L["RightEye"][0]), 4)}
