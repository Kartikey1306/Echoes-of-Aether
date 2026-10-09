"""Line-up render of the *exported* FBX files (re-imported, i.e. what Unity receives) at true relative scale.

  Blender -b --factory-startup --python render_lineup.py
Output: previews/lineup.png
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import robokit as K  # noqa: E402
import roboscene as RS  # noqa: E402
import robopreview as P  # noqa: E402

ORDER = [("bolt", 0.0), ("drone", 0.0), ("stalker", 0.0), ("sentinel", 0.0), ("warden", 0.0), ("guardian", 0.0)]
GAP = 0.6


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    x = 0.0
    every = {}
    for kind, _ in ORDER:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=os.path.join(RS.UNITY_ROBOTS, kind + ".fbx"))
        new = [o for o in bpy.data.objects if o not in before]
        mats = {s.material for o in new if o.type == "MESH" for s in o.material_slots if s.material}
        for m in mats:
            base = m.name.split(".")[0]
            i = K.MAT_NAMES.index(base)
            m.name = kind + "_" + base
            P.setup_material(m, kind, i)
        bpy.context.view_layer.update()
        xs = [(o.matrix_world @ Vector(c)).x for o in new if o.type == "MESH" for c in o.bound_box]
        w = max(xs) - min(xs)
        dx = x - min(xs)
        lift = 1.7 if kind == "drone" else 0.0
        for o in new:
            if o.parent is None:
                o.location.x += dx
                o.location.z += lift
        x += w + GAP
        for o in new:
            every[o.name] = o
    P.studio(res=(1800, 760), samples=48)
    cam = bpy.context.scene.camera
    cam.data.lens = 50
    P.aim(cam, every, 0, 4, margin=1.04)
    # keep the floor below the line-up
    P.render_to(os.path.join(RS.PREVIEW_DIR, "lineup.png"))


main()
