"""Build, export and preview the Echoes of Aether robot models.

  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python build_robots.py -- [types...] [--no-preview] [--no-export]

types: drone sentinel warden stalker guardian bolt (default: all)
Outputs: Unity/Assets/Resources/Models/Robots/<type>.fbx, blender/robots/out/<type>.blend + <type>_stats.json,
         blender/robots/previews/<type>_{front,34,side,pose,sheet}.png
"""
import importlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402

import robokit  # noqa: E402
import roboscene as RS  # noqa: E402
import robopreview  # noqa: E402


def builder(t):
    if t in ("sentinel", "warden"):
        import bot_sentinel
        return lambda: bot_sentinel.build(t == "warden")
    return importlib.import_module("bot_" + t).build


ALL = ["drone", "sentinel", "warden", "stalker", "guardian", "bolt"]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    flags = {a for a in argv if a.startswith("--")}
    types = [a for a in argv if not a.startswith("--")] or ALL
    os.makedirs(RS.OUT_DIR, exist_ok=True)
    for t in types:
        t0 = time.time()
        RS.reset()
        robot = builder(t)()
        objs = RS.build_objects(robot, t)
        RS.uv_unwrap(objs)
        st = RS.stats(objs)
        st["type"] = t
        st["height"] = robot.height
        if "--no-export" not in flags:
            path = os.path.join(RS.UNITY_ROBOTS, t + ".fbx")
            RS.export_fbx(path)
            st["fbx"] = path
        with open(os.path.join(RS.OUT_DIR, t + "_stats.json"), "w") as f:
            json.dump(st, f, indent=1, sort_keys=True)
        bpy.context.preferences.filepaths.save_version = 0          # no .blend1 backups
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(RS.OUT_DIR, t + ".blend"), compress=True)
        print("[robots] %-9s tris %6d  mats %s  (%.1fs)" % (t, st["total"], st["materials"], time.time() - t0))
        if "--no-preview" not in flags:
            robopreview.run(t, robot, objs)
            print("[robots] %-9s previews done (%.1fs)" % (t, time.time() - t0))


if __name__ == "__main__":
    main()
