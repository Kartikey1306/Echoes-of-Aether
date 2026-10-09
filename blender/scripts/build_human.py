"""Build an MPFB human for a character and render preview images.

blender -b --python build_human.py -- <character> [--render] [--blend out.blend]
"""
import bpy, sys, os, math, importlib
sys.path.insert(0, os.path.dirname(__file__))
import characters
importlib.reload(characters)
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService
from bl_ext.user_default.mpfb.services.assetservice import AssetService

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "out")


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return a


def build(cid):
    c = characters.CHARACTERS[cid]
    info = HumanService._create_default_human_info_dict()
    info["name"] = c["name"]
    info["phenotype"] = c["phenotype"]
    info["rig"] = "mixamo_unity"
    info["eyes"] = "high-poly/high-poly.mhclo"
    info["eyebrows"] = c["eyebrows"]
    info["eyelashes"] = c["eyelashes"]
    info["teeth"] = "teeth_base/teeth_base.mhclo"
    info["tongue"] = "tongue01/tongue01.mhclo"
    info["hair"] = c["hair"]
    info["skin_mhmat"] = c["skin"]
    info["skin_material_type"] = "ENHANCED_SSS"
    info["eyes_material_type"] = "MAKESKIN"
    info["targets"] = [{"target": t.split("/")[-1], "value": v} for t, v in c["targets"]]
    info["clothes"] = list(c.get("clothes", []))
    settings = HumanService.get_default_deserialization_settings()
    settings["subdiv_levels"] = 0
    settings["detailed_helpers"] = True  # joint-* groups are needed to fit the rig
    settings["mask_helpers"] = True
    settings["load_clothes"] = True
    body = HumanService.deserialize_from_dict(info, settings)
    rig = body.parent
    rig.name = rig.data.name = c["name"]
    # Extra hair styles for the customiser (all fitted and weighted; the game shows one at a time).
    for style, path in c.get("extra_hair", {}).items():
        p = AssetService.find_asset_absolute_path(path, asset_subdir="hair")
        o = HumanService.add_mhclo_asset(p, body, asset_type="hair", subdiv_levels=0, material_type="MAKESKIN")
        o.name = c["name"] + ".hair_" + style
    for style, path in c.get("extra_clothes", {}).items():
        p = AssetService.find_asset_absolute_path(path, asset_subdir="clothes")
        o = HumanService.add_mhclo_asset(p, body, asset_type="clothes", subdiv_levels=0, material_type="MAKESKIN")
        o.name = c["name"] + ".facial_" + style
    # Eye colour
    eyes = [o for o in bpy.data.objects if "eyes" in o.name.lower() or "high-poly" in o.name.lower()]
    mat_path = AssetService.find_asset_absolute_path("materials/" + c.get("eyes_material", "brown") + ".mhmat", asset_subdir="eyes")
    print("EYES", [e.name for e in eyes], mat_path)
    return body


def setup_render(body, name, shots):
    scene = bpy.context.scene
    for o in list(bpy.data.objects):
        if o.name.startswith(("L", "cam", "aim")) and o.type in ("LIGHT", "CAMERA", "EMPTY"):
            bpy.data.objects.remove(o, do_unlink=True)
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 64
    scene.render.resolution_x, scene.render.resolution_y = 700, 900
    scene.view_settings.view_transform = "AgX"
    w = bpy.data.worlds.new("w"); w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.035, 0.045, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    scene.world = w
    # Three-point studio lighting.
    def area(loc, energy, size, color=(1, 1, 1)):
        l = bpy.data.objects.new("L", bpy.data.lights.new("L", "AREA"))
        l.data.energy = energy; l.data.size = size; l.data.color = color; l.location = loc
        scene.collection.objects.link(l)
        t = l.constraints.new("TRACK_TO"); t.target = body; t.track_axis = "TRACK_NEGATIVE_Z"; t.up_axis = "UP_Y"
        return l
    area((1.4, -1.8, 2.2), 260, 1.2, (1.0, 0.95, 0.9))
    area((-1.8, -1.2, 1.6), 90, 2.0, (0.85, 0.9, 1.0))
    area((0.3, 1.8, 2.3), 220, 1.0, (0.8, 0.9, 1.0))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam)
    scene.camera = cam
    aim = bpy.data.objects.new("aim", None); scene.collection.objects.link(aim)
    tc = cam.constraints.new("TRACK_TO"); tc.target = aim; tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"
    top = max((body.matrix_world @ v.co).z for v in body.data.vertices)
    for tag, (dist, z, yaw, lens) in shots.items():
        cam.data.lens = lens
        a = math.radians(yaw)
        cam.location = (math.sin(a) * dist, -math.cos(a) * dist, z)
        aim.location = (0, 0, z if "face" in tag else top * 0.52)
        scene.render.filepath = os.path.join(OUT, f"{name}_{tag}.png")
        bpy.ops.render.render(write_still=True)
        print("RENDERED", scene.render.filepath)


if __name__ == "__main__":
    a = args()
    cid = a[0] if a else "kael"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    body = build(cid)
    print("OBJECTS", [(o.name, o.type) for o in bpy.data.objects])
    rig = body.parent if body.parent and body.parent.type == "ARMATURE" else [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
    hb = rig.data.bones["mixamorig:Head"]
    face_z = (rig.matrix_world @ hb.head_local).z + 0.075
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    top = max((body.matrix_world @ v.co).z for v in ev.data.vertices)
    print("HEIGHT", round(top, 3), "FACE_Z", round(face_z, 3))
    if "--render" in a:
        setup_render(body, cid, {"face": (0.62, face_z, 0, 85), "face34": (0.66, face_z, 38, 85), "body": (3.4, top * 0.55, 20, 50)})
    if "--blend" in a:
        bpy.ops.wm.save_as_mainfile(filepath=a[a.index("--blend") + 1])
