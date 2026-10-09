"""Concept match render: game lookdev materials, built-in hair, the idle clip's relaxed arms-down pose, soft grey
studio light and the master concept's framing (front, head to below the knees). Writes out/renders/<tag>_concept.png
and out/report/<tag>_concept_vs_blender.png (side by side with the concept).

  blender -b out/giva_hair.blend --python compare_concept.py -- <tag> [--frame idle:15] [--samples 128]
"""
import bpy, sys, os, json, math, importlib, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
from mathutils import Vector
import gv, look, lookdev, poses, deform
for m in (gv, look, lookdev, poses, deform):
    importlib.reload(m)
a = gv.args()
tag = a[0]
rig = bpy.data.objects[gv.RIG]
TEX = os.path.join(gv.OUT, "tex")
atl = json.load(open(os.path.join(TEX, "atlases.json")))
objs = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig]
for o in bpy.data.objects:
    if o.name == "Gloves" and "--gloves" not in gv.args():
        o.hide_render = True                  # the game default is bare hands (concept)
    if o.name.endswith("_high") or (o.type == "MESH" and o.name.startswith("Hair_") and o.name != "Hair_waves"):
        o.hide_render = True
lookdev.apply_all([o for o in objs if not o.name.startswith("Hair_")], TEX, atl, lookdev.GAME)
ho = bpy.data.objects.get("Hair_waves")
if ho:
    ho.hide_render = False
    ho.data.materials.clear()
    ho.data.materials.append(lookdev.alpha_card("pv_hair", os.path.join(TEX, "Hair_waves_Color.png"), lookdev.GAME["hair"], cutoff=0.35))
from mathutils import Quaternion, Matrix


def aim_bone(name, target_dir):
    """Rotate pose bone `name` (from its current pose) so its head->tail points along target_dir (armature space)."""
    bpy.context.view_layer.update()
    pb = rig.pose.bones[gv.P + name]
    cur = (pb.tail - pb.head).normalized()
    q = cur.rotation_difference(Vector(target_dir).normalized())
    M = pb.matrix.to_3x3().normalized()
    loc = M.inverted() @ q.to_matrix() @ M
    pb.rotation_mode = "QUATERNION"
    pb.rotation_quaternion = pb.rotation_quaternion @ loc.to_quaternion()
    bpy.context.view_layer.update()


def concept_pose():
    """The concept's stance: arms relaxed close to the sides, a soft elbow, hands relaxed; head level."""
    poses.rest(rig)
    for side, sx in (("Left", 1.0), ("Right", -1.0)):
        aim_bone(side + "Arm", (sx * 0.2, 0.03, -1.0))
        aim_bone(side + "ForeArm", (sx * 0.12, -0.12, -1.0))
        aim_bone(side + "Hand", (sx * 0.06, -0.1, -1.0))
        for f in ("Index", "Middle", "Ring", "Pinky"):
            for j, ang in ((1, 14), (2, 22), (3, 12)):
                pb = rig.pose.bones.get(gv.P + side + "Hand" + f + str(j))
                if pb:
                    pb.rotation_mode = "XYZ"
                    pb.rotation_euler = (math.radians(ang), 0, 0)
    bpy.context.view_layer.update()


poses.load()
if "--frame" in a:
    clip, fr = gv.opt(a, "--frame").split(":")
    poses.pose(rig, clip, int(fr))
else:
    concept_pose()
cdefs = json.load(open(os.path.join(gv.OUT, "correctives.json")))
deform.drive_correctives(rig, objs, cdefs, True)
dg = bpy.context.evaluated_depsgraph_get()
body = bpy.data.objects["Body"]
ev = body.evaluated_get(dg)
import numpy as np
co = np.array([body.matrix_world @ v.co for v in ev.data.vertices])
cx, cy = float(co[:, 0].mean()), float(co[:, 1].mean())
out = os.path.join(gv.OUT, "renders", tag + "_concept.png")
look.shot(out, Vector((cx, cy - 2.85, 1.2)), Vector((cx, cy, 1.13)), 50, "concept", "CYCLES", (864, 1152),
          int(gv.opt(a, "--samples", "128")), height=1.73, center=(cx, cy, 0))
if "--face" in a:
    hb = rig.pose.bones[gv.P + "Head"]
    hp = rig.matrix_world @ hb.head + Vector((0, 0, 0.055))
    look.shot(os.path.join(gv.OUT, "renders", tag + "_concept_face.png"), hp + Vector((0, -0.85, 0.0)), hp + Vector((0, 0, -0.03)), 50, "concept", "CYCLES",
              (864, 1152), int(gv.opt(a, "--samples", "128")), face=tuple(hp), floor=False)
subprocess.run(["/opt/homebrew/bin/python3", "-c", f"""
from PIL import Image, ImageDraw
c = Image.open('/Users/kartikey/Desktop/Game/dreamlayer/characters/lyra/giva_master_front.png').convert('RGB')
c = c.crop((0, 0, 1300, c.size[1])).resize((round(1300 * 1152 / c.size[1]), 1152))
r = Image.open('{out}').convert('RGB')
s = Image.new('RGB', (c.size[0] + r.size[0], 1182), (14, 15, 20))
d = ImageDraw.Draw(s)
s.paste(c, (0, 30)); s.paste(r, (c.size[0], 30))
d.text((8, 8), 'master concept (target)', fill=(200, 210, 255)); d.text((c.size[0] + 8, 8), 'Blender: game materials, idle pose', fill=(200, 210, 255))
s.save('{os.path.join(gv.OUT, 'report', tag + '_concept_vs_blender.png')}')
"""])
gv.log("concept compare", out)
