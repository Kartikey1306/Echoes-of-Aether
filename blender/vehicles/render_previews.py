"""Render previews from the EXPORTED FBX files (what Unity gets): Cycles (Metal GPU), AgX.

Blender -b --factory-startup --python render_previews.py -- [Name ...] [--scenes street,studio] [--views fr,rr]
       [--samples 128] [--res 1280x720] [--tag final]
Output: blender/vehicles/previews/<Name>_<scene>_<view>.png
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import vehicles  # noqa: E402
import vkit as K  # noqa: E402
import vmat  # noqa: E402
import vpaths  # noqa: E402
import vscene  # noqa: E402


def parse():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opt = {"scenes": "street,studio", "views": "fr,rr", "samples": "128", "res": "1280x720", "out": vpaths.PREVIEWS}
    names = []
    i = 0
    while i < len(a):
        if a[i].startswith("--"):
            opt[a[i][2:]] = a[i + 1]
            i += 2
        else:
            names.append(a[i])
            i += 1
    return names or vehicles.names(), opt


def load(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=os.path.join(vpaths.MODELS, f"{name}.fbx"), bake_space_transform=True)
    objs = [o for o in bpy.context.scene.objects]
    for o in objs:
        if o.type == "MESH" and not o.name.endswith("_LOD0"):
            o.hide_render = True
            o.hide_viewport = True
    for o in objs:
        if o.type == "MESH":
            for p in o.data.polygons:
                p.use_smooth = p.use_smooth
    vmat.build_all()
    bpy.context.view_layer.update()
    lod0 = [o for o in objs if o.type == "MESH" and o.name.endswith("_LOD0")]
    return objs, lod0


def render(name, opt):
    t0 = time.time()
    objs, lod0 = load(name)
    lo, hi = K.bounds_world(lod0)
    size = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    w, h = [int(x) for x in opt["res"].split("x")]
    cat = vehicles.CATEGORY[name]
    lift = 0.0
    if cat == "hover":
        lift = 0.55 if name != "HoverTruck" else 0.9
        roots = [o for o in objs if o.parent is None]
        for o in roots:
            o.location.z += lift
    bpy.context.view_layer.update()
    front = Vector((0, -1, 0))  # import space: vehicle front = -Y
    for scene in opt["scenes"].split(","):
        # rebuild environment per scene (delete previous env objects)
        keep = set(objs)
        for o in list(bpy.context.scene.objects):
            if o not in keep and not o.name.startswith("wash"):
                bpy.data.objects.remove(o, do_unlink=True)
        vscene.setup_render((w, h), int(opt["samples"]), look="AgX - Medium High Contrast" if scene == "street" else "AgX - Base Contrast")
        if scene == "street":
            vscene.street(size, front)
            if cat != "hover":
                # headlight / taillight practical glow on the ground
                pass
        else:
            vscene.studio(size)
        for v in opt["views"].split(","):
            hz = None
            tz = (size[2] * 0.42) + lift
            lens = 40 if size[1] < 7 else 35
            if v == "fr":
                vscene.cam_three_quarter(size, front, lens=lens, height=(max(0.75, size[2] * 0.62) + lift * 0.6), target_z=tz)
            elif v == "rr":
                vscene.cam_three_quarter(size, front, rear=True, lens=lens, height=(max(0.75, size[2] * 0.62) + lift * 0.6), target_z=tz)
            elif v == "side":
                vscene.camera((size[0] / 2 + size[1] * 1.15 + 1.5, 0, size[2] * 0.5 + lift), (0, 0, size[2] * 0.45 + lift), lens=45)
            elif v == "low":
                vscene.cam_three_quarter(size, front, lens=28, height=0.42 + lift, dist_mul=0.72, target_z=tz)
            out = os.path.join(opt["out"], f"{name}_{scene}_{v}.png")
            bpy.context.scene.render.filepath = out
            bpy.ops.render.render(write_still=True)
            print(f"[render] {out} ({time.time() - t0:.1f}s)", flush=True)


if __name__ == "__main__":
    names, opt = parse()
    os.makedirs(opt["out"], exist_ok=True)
    for n in names:
        render(n, opt)
