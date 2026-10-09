"""Hair close-up test: blender -b out/hd/<cid>_base.blend --python hair_preview.py -- <cid> <style> <light> [tint_hex]"""
import bpy, sys, os, importlib
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import gear, hair_hd, preview_hd, texbake as TB
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]
cid, style, light = a[0], a[1], a[2]
tint = a[3] if len(a) > 3 else "#1d1714"
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.endswith(".body"))
for o in bpy.data.objects:
    if o.type == "MESH" and (".hair_" in o.name or ".facial_" in o.name or o.name.endswith(("short02", "ponytail01"))):
        o.hide_render = True
ctx = gear.Ctx(body, rig, rig.name)
out = os.path.join(os.path.dirname(__file__), "..", "out", "hd", "hairtest")
os.makedirs(out, exist_ok=True)
fn = getattr(hair_hd, "build_" + style)
obj, tex = fn(ctx, f"{rig.name}.hair_{style}", out)
print("HAIR tris", sum(len(p.vertices) - 2 for p in obj.data.polygons))
# preview material mirroring Unity: desaturated, mean-normalised luminance x tint, alpha clip 0.4
img = TB.read_image(os.path.join(out, tex))
lum = img[..., :3].mean(-1); alpha = img[..., 3]
mean = lum[alpha > 0.5].mean()
grey = np.clip(lum / mean * 0.745, 0, 1)
t = np.array([int(tint[i:i + 2], 16) / 255 for i in (1, 3, 5)])
rgba = np.concatenate([grey[..., None] * t, alpha[..., None]], -1)
TB.write_png(rgba, os.path.join(out, f"{style}_preview.png"), "RGBA")
m = bpy.data.materials.get(f"Hair_{style}")
m.use_nodes = True
nt = m.node_tree
for n in list(nt.nodes): nt.nodes.remove(n)
o_ = nt.nodes.new("ShaderNodeOutputMaterial"); b = nt.nodes.new("ShaderNodeBsdfPrincipled")
nt.links.new(b.outputs[0], o_.inputs[0])
tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = bpy.data.images.load(os.path.join(out, f"{style}_preview.png"))
tx.image.colorspace_settings.name = "sRGB"
nt.links.new(tx.outputs["Color"], b.inputs["Base Color"])
gt = nt.nodes.new("ShaderNodeMath"); gt.operation = "GREATER_THAN"; gt.inputs[1].default_value = 0.4
nt.links.new(tx.outputs["Alpha"], gt.inputs[0]); nt.links.new(gt.outputs[0], b.inputs["Alpha"])
b.inputs["Roughness"].default_value = 0.55
b.inputs["Specular IOR Level"].default_value = 0.25
b.inputs["Coat Weight"].default_value = 0.0
if hasattr(m, "surface_render_method"):
    m.surface_render_method = "DITHERED"
m.use_backface_culling = False
obj.parent = rig
hb = rig.data.bones["mixamorig:Head"]
head = rig.matrix_world @ hb.head_local
face = Vector((0, head.y - 0.02, head.z + 0.085))
preview_hd.OUT = out
h = max(v.co.z for v in body.data.vertices)
for L in light.split(","):
    preview_hd.render(f"{cid}_{style}", (0, 0, 0), h, face, L, ["face", "face34"], samples=32)
    preview_hd.setup(L, (900, 1000), 32); preview_hd.lights(L, face - Vector((0, 0, 0.25)), 1.0)
    preview_hd.camera(face + Vector((-0.35, 0.55, 0.12)), face + Vector((0, 0.03, 0.02)), 85)
    bpy.context.scene.render.filepath = os.path.join(out, f"{cid}_{style}_{L}_back.png"); bpy.ops.render.render(write_still=True)
