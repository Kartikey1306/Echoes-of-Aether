"""Pose test: put the game's retargeted clips (Anim_Male/Female.fbx) on an HD character and render extreme frames,
and report how many outfit vertices end up inside the body (poke-through) per frame.

  blender -b out/hd/<cid>_hd.blend --python pose_test.py -- <cid> <clip:frame,clip:frame,...>
Renders blender/out/previews_hd/<cid>_pose_<clip>_<frame>.png and prints POKE lines.
"""
import bpy, sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import preview_hd, characters

a = sys.argv[sys.argv.index("--") + 1:]
cid = a[0]
c = characters.CHARACTERS[cid]
rig = bpy.data.objects[c["name"]]
fem = c["phenotype"]["gender"] < 0.5
ANIM = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "unity", "EchoesOfAether", "Assets", "Art", "Animations",
                                    "Anim_Female.fbx" if fem else "Anim_Male.fbx"))
before = set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=ANIM, automatic_bone_orientation=False)
src = next(o for o in bpy.data.objects if o not in before and o.type == "ARMATURE")
acts = {act.name.split("|")[-1]: act for act in bpy.data.actions}
for o in [o for o in bpy.data.objects if o not in before]:
    o.hide_render = True
# Copy local pose rotations bone by bone (both rigs use the same mixamorig bone set and rest orientations).
rig.animation_data_create()
for o in bpy.data.objects:
    if o.type == "MESH" and o.parent is rig and ((o.name.startswith("Hair_") and o.name != "Hair_" + ("curly" if cid == "kael" else "wavy")) or o.name.startswith("Facial_")):
        o.hide_render = True
body = bpy.data.objects.get("Body")
outfit = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig and o.name in
          ("Top", "Jacket", "Pants", "ChestPlate", "PauldronL", "PauldronR", "PauldronLameL", "PauldronLameR", "KneePadL", "KneePadR",
           "ShoulderR", "ForearmGuardL", "ForearmGuardR", "ChestRig", "Harness", "Belt", "Collar", "Boots", "Hair_curly", "Hair_wavy")]
preview_hd.OUT = os.path.join(os.path.dirname(__file__), "..", "out", "previews_hd")
h = 1.8
for spec in a[1].split(","):
    clip, fr = spec.split(":")
    act = acts.get(clip)
    if act is None:
        print("NOCLIP", clip, sorted(acts)[:10]); continue
    src.animation_data_create(); src.animation_data.action = act
    bpy.context.scene.frame_set(int(fr))
    for pb in rig.pose.bones:
        sb = src.pose.bones.get(pb.name)
        if sb is None:
            continue
        pb.rotation_mode = "QUATERNION"
        sb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = sb.rotation_quaternion.copy()
        if pb.name.endswith("Hips"):
            pb.location = sb.location.copy()
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    be = body.evaluated_get(dg)
    bm = be.to_mesh()
    tree = BVHTree.FromPolygons([body.matrix_world @ v.co for v in bm.vertices], [p.vertices for p in bm.polygons])
    be.to_mesh_clear()
    report = []
    for o in outfit:
        oe = o.evaluated_get(dg)
        m = oe.to_mesh()
        inside = 0
        for v in list(m.vertices)[::3]:
            p = o.matrix_world @ v.co
            hit, n, _, d = tree.find_nearest(p, 0.05)
            if hit is not None and (p - hit).dot(n) < -0.004:
                inside += 1
        oe.to_mesh_clear()
        if inside:
            report.append(f"{o.name}:{inside * 3}")
    print("POKE", clip, fr, " ".join(report) if report else "none")
    preview_hd.setup("studio", (900, 1100), 16)
    root = rig.matrix_world @ rig.pose.bones[next(n for n in rig.pose.bones.keys() if n.endswith("Hips"))].head
    preview_hd.lights("studio", (root.x, root.y, 0), h)
    preview_hd.camera(Vector((root.x + 2.2, root.y - 2.6, 1.3)), Vector((root.x, root.y, 0.95)), 45)
    bpy.context.scene.render.filepath = os.path.join(preview_hd.OUT, f"{cid}_pose_{clip}_{fr}.png")
    bpy.ops.render.render(write_still=True)
