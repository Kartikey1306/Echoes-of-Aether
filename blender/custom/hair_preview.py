"""Load a built hair style into a preview scene (cache/hairobj_<cid>_<sid>.blend written by hair_build.py, or the
exported FBX as a fallback)."""
import bpy, os
import numpy as np
import common as C

DEFAULTS = {"kael": "side_part_volume", "lyra": "long_waves"}


def load_hair(cid, sid):
    p = os.path.join(C.CACHE, f"hairobj_{cid}_{sid}.blend")
    if os.path.exists(p):
        with bpy.data.libraries.load(p, link=False) as (src, dst):
            dst.objects = [n for n in src.objects]
        objs = [o for o in dst.objects if o is not None]
        for o in objs:
            bpy.context.scene.collection.objects.link(o)
            o.parent = None
            o.modifiers.clear()
            o["custom"] = 1
            o.hide_render = False
        return objs[0] if objs else None
    fbx = os.path.join(C.CUSTOM_OUT, "Hair", f"{cid}_{sid}.fbx")
    if not os.path.exists(fbx):
        return None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=fbx)
    new = [o for o in bpy.data.objects if o not in before]
    mesh = next(o for o in new if o.type == "MESH")
    mw = mesh.matrix_world.copy()
    mesh.parent = None
    mesh.data.transform(mw)
    mesh.matrix_world.identity()
    mesh.modifiers.clear()
    if not any(o.type == "ARMATURE" for o in new):
        mesh.data.transform(C.rigid_matrix(cid).inverted())
    for o in new:
        if o is not mesh:
            bpy.data.objects.remove(o, do_unlink=True)
    import studio
    tex = os.path.join(C.CUSTOM_OUT, "Hair", "Textures", f"{cid}_{sid}_Hair.png")
    mesh.data.materials.clear()
    mesh.data.materials.append(studio.hair_mat(f"prevhair_{sid}", tex, C.HEROES[cid]["hair_preview"], 0.4))
    mesh["custom"] = 1
    return mesh


def load_default_hair(cid):
    return load_hair(cid, DEFAULTS[cid])
