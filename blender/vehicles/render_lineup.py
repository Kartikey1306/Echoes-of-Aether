"""Line-up image of the whole kit from the exported FBX files (LOD0), dark studio, Cycles/Metal, AgX.
Blender -b --factory-startup --python render_lineup.py -- [samples] [WxH]
Output: blender/vehicles/previews/lineup_studio.png
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import vkit as K  # noqa: E402
import vmat  # noqa: E402
import vpaths  # noqa: E402
import vscene  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
samples = int(a[0]) if a else 96
res = tuple(int(x) for x in (a[1] if len(a) > 1 else "1920x1080").split("x"))

# (name, x, y, yaw deg, lift) -- import space: vehicle front = -Y; camera looks from -Y
LAYOUT = [
    ("HoverTruck", -9.5, 9.0, -25, 1.4), ("CyberVan", -3.4, 7.0, -28, 0.0), ("CyberVan_Burnt", 9.6, 7.5, 30, 0.0),
    ("HoverCar_A", 3.0, 7.0, 25, 1.1), ("CyberCar_Sedan_Wrecked", -9.8, 1.0, -35, 0.0),
    ("CyberCar_Sedan", -5.2, 0.2, -30, 0.0), ("HoverCar_B", 5.2, 1.0, 28, 0.9), ("CyberCar_Taxi", 9.6, 0.8, 34, 0.0),
    ("CyberCar_Coupe", -1.6, -3.5, -24, 0.0), ("CyberBike", 1.9, -3.8, 26, 0.0),
]

bpy.ops.wm.read_factory_settings(use_empty=True)
for name, x, y, yaw, lift in LAYOUT:
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.join(vpaths.MODELS, f"{name}.fbx"), bake_space_transform=True)
    new = [o for o in bpy.context.scene.objects if o not in before]
    for o in new:
        if o.type == "MESH" and "_LOD0" not in o.name:
            o.hide_render = True
    root = bpy.data.objects.new(f"{name}_root", None)
    bpy.context.scene.collection.objects.link(root)
    for o in new:
        if o.parent is None:
            o.parent = root
    root.matrix_world = Matrix.Translation((x, y, lift)) @ Matrix.Rotation(math.radians(yaw), 4, "Z")
# multiple imports create 'veh_x.001' duplicates: point every slot back at the base material
for o in bpy.context.scene.objects:
    if o.type == "MESH":
        for i, m in enumerate(o.data.materials):
            if m and "." in m.name:
                base = bpy.data.materials.get(m.name.split(".")[0])
                if base:
                    o.data.materials[i] = base
vmat.build_all()
bpy.context.view_layer.update()
vscene.setup_render(res, samples, look="AgX - Medium High Contrast")
vscene.studio((22.0, 18.0, 3.5))
vscene.camera((0.0, -19.0, 6.2), (0.0, 2.5, 0.9), lens=32)
for o in list(bpy.context.scene.objects):
    if o.type == "LIGHT":
        o.data.energy *= 4.5 if not o.name.startswith("kick") else 10
bpy.context.scene.render.filepath = os.path.join(vpaths.PREVIEWS, "lineup_studio.png")
bpy.ops.render.render(write_still=True)
print("[lineup] done")
