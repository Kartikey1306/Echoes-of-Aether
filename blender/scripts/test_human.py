# Smoke test: create an MPFB human headlessly, rig it and render a preview.
import bpy, sys, os, math
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService
OUT = "/Users/kartikey/Desktop/Game/blender/out"
bpy.ops.wm.read_factory_settings(use_empty=True)
macro = TargetService.get_default_macro_info_dict()
macro.update({"gender": 1.0, "age": 0.5, "muscle": 0.7, "weight": 0.5, "height": 0.6, "proportions": 0.8})
macro["race"] = {"asian": 0.2, "caucasian": 0.5, "african": 0.3}
h = HumanService.create_human(mask_helpers=True, detailed_helpers=False, extra_vertex_groups=True, feet_on_ground=True, scale=0.1, macro_detail_dict=macro)
print("HUMAN", h.name, len(h.data.vertices), [m.type for m in h.modifiers])
rig = HumanService.add_builtin_rig(h, "mixamo_unity", import_weights=True)
print("RIG", rig.name if rig else None, len(rig.data.bones) if rig else 0, [b.name for b in rig.data.bones][:12] if rig else None)
# Camera + light + render
scene = bpy.context.scene
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam)
cam.location = (0, -2.2, 1.55); cam.rotation_euler = (math.radians(88), 0, 0); cam.data.lens = 50
scene.camera = cam
for (loc, e) in [((1.5, -2, 2.5), 400), ((-2, -1.5, 1.8), 150), ((0, 2, 2.5), 250)]:
    l = bpy.data.objects.new("l", bpy.data.lights.new("l", 'AREA')); l.data.energy = e; l.data.size = 1.5; l.location = loc
    scene.collection.objects.link(l); c = l.constraints.new('TRACK_TO'); c.target = h; c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 600, 900
scene.render.filepath = os.path.join(OUT, "test_human.png")
w = bpy.data.worlds.new("w"); w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.06, 0.08, 1); scene.world = w
bpy.ops.render.render(write_still=True)
print("RENDERED", scene.render.engine)
