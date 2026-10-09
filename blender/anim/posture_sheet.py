"""Pose contact sheet straight from an animation FBX (Anim_Male.fbx / Anim_Female.fbx), on a hero export rig.

  blender -b blender/out/kael_export.blend --python blender/anim/posture_sheet.py -- <fbx> <out_dir> [clip:t,...]

Imports the FBX, plays each clip's action on the rig of the open .blend (same mixamo_unity skeleton) at the given
normalised time and renders a clay front three-quarter and a side view per clip: <out_dir>/<clip>_<view>.png.
Compose the strips with tools/anim/posture_sheet_compose.py (system python, PIL).
"""
import math
import os
import sys

import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
FBX, OUT = ARGS[0], ARGS[1]
PICKS = [(c.split(":")[0], float(c.split(":")[1])) for c in (ARGS[2] if len(ARGS) > 2 else
         "idle:0.4,talk:0.4,walk:0.25,run:0.25,sprint:0.25,combat_idle:0.4,npc_crossed:0.4,k_light1:0.24,k_heavy:0.46,l_heavy:0.42,crouch_idle:0.4,crouch_walk:0.25").split(",")]
os.makedirs(OUT, exist_ok=True)

rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
before = set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=FBX, automatic_bone_orientation=False)
for o in bpy.data.objects:
    if o not in before:
        o.hide_render = True
actions = {a.name.split("|")[-1]: a for a in bpy.data.actions if "|" in a.name}

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
sh = scene.display.shading
sh.light = "STUDIO"
sh.color_type = "SINGLE"
sh.single_color = (0.72, 0.72, 0.74)
sh.show_shadows = True
sh.show_cavity = True
scene.render.resolution_x = 360
scene.render.resolution_y = 480
scene.render.image_settings.file_format = "PNG"
scene.render.fps = 30
for o in bpy.data.objects:
    if o.type == "MESH" and o.name.startswith(("Hair_", "Facial_")) and o.name not in ("Hair_short", "Hair_ponytail"):
        o.hide_render = True
if "SheetFloor" not in bpy.data.objects:
    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
    bpy.context.active_object.name = "SheetFloor"
cam = bpy.data.objects.new("SheetCam", bpy.data.cameras.new("SheetCam"))
scene.collection.objects.link(cam)
cam.data.lens = 50
scene.camera = cam

rig.animation_data_create()
for pb in rig.pose.bones:
    pb.rotation_mode = "QUATERNION"  # the FBX actions key quaternions; the export rig is in Euler mode
height = max((rig.matrix_world @ b.head_local).z for b in rig.data.bones if b.name.endswith("Head")) + 0.12
for clip, t in PICKS:
    act = actions.get(clip)
    if act is None:
        print("MISSING", clip)
        continue
    rig.animation_data.action = act
    if hasattr(rig.animation_data, "action_slot") and len(getattr(act, "slots", [])):
        rig.animation_data.action_slot = act.slots[0]
    f0, f1 = act.frame_range
    scene.frame_set(int(round(f0 + (f1 - f0) * t)))
    hips = rig.pose.bones["mixamorig:Hips"]
    c = rig.matrix_world @ hips.head
    c = Vector((c.x, c.y, 0))
    for view, off in (("q34", Vector((2.3, -2.6, 1.15))), ("side", Vector((-3.6, -0.2, 1.0)))):
        eye = c + off * (height / 1.8)
        tgt = c + Vector((0, 0, 0.88 * height / 1.8))
        cam.location = eye
        cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(OUT, f"{clip}_{view}.png")
        bpy.ops.render.render(write_still=True)
print("SHEET FRAMES", OUT)
