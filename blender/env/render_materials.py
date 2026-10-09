"""Render material preview contact sheets (sphere + world-scale floor patch per material).

  Blender -b --factory-startup --python render_materials.py -- [--cols 4] [--size 420x315] [names...]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402

import envpaths  # noqa: E402
import matdefs  # noqa: E402
import preview  # noqa: E402


def mesh_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def sphere(r=0.45):
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=r, calc_uvs=True)
    for f in bm.faces:
        for l in f.loops:
            u, v = l[uvl].uv
            l[uvl].uv = (u * math.tau * r, v * math.pi * r)
    bmesh.ops.translate(bm, vec=(0, 0, r), verts=bm.verts)
    return mesh_obj("Sphere", bm)


def quad(name, corners, uvs):
    bm = bmesh.new()
    vs = [bm.verts.new(c) for c in corners]
    f = bm.faces.new(vs)
    uvl = bm.loops.layers.uv.new("UVMap")
    for l, uv in zip(f.loops, uvs):
        l[uvl].uv = uv
    return mesh_obj(name, bm)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    cols, size, names = 4, (420, 315), []
    i = 0
    while i < len(argv):
        if argv[i] == "--cols":
            cols = int(argv[i + 1]); i += 2
        elif argv[i] == "--size":
            size = tuple(int(x) for x in argv[i + 1].split("x")); i += 2
        else:
            names.append(argv[i]); i += 1
    reg = matdefs.REGISTRY
    names = names or list(reg.keys())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cam = preview.studio(size, 24)
    tmp = os.path.join(envpaths.STATE, f"tmp_render_{os.getpid()}.png")
    tiles = []
    for name in names:
        for ob in [o for o in bpy.context.scene.objects if o.name.startswith(("Sphere", "Patch", "Label"))]:
            bpy.data.objects.remove(ob)
        tile, mode = preview.tile_of(name) if reg[name]["kind"] != "param" else (1.0, "world")
        m = preview.textured(name)
        objs = []
        if mode == "world":
            s = 3.0
            k = s / 2
            p = quad("Patch", [(-k, -k, 0.003), (k, -k, 0.003), (k, k, 0.003), (-k, k, 0.003)], [(-k, -k), (k, -k), (k, k), (-k, k)])
            sp = sphere()
            sp.location = (0.2, 0.1, 0)
            objs = [p, sp]
            bmin, bmax = (-1.5, -1.5, 0), (1.5, 1.5, 0.9)
        elif mode == "fit":
            p = quad("Patch", [(-0.8, 0, 0.1), (0.8, 0, 0.1), (0.8, 0, 1.1), (-0.8, 0, 1.1)], [(0, 0), (1, 0), (1, 1), (0, 1)])
            p.rotation_euler = (math.radians(-12), 0, 0)
            objs = [p]
            bmin, bmax = (-0.8, -0.2, 0.0), (0.8, 0.2, 1.2)
        else:  # strip
            p = quad("Patch", [(-1.0, 0, 0.3), (1.0, 0, 0.3), (1.0, 0, 0.5), (-1.0, 0, 0.5)], [(0, 0), (2.0, 0), (2.0, 1), (0, 1)])
            p2 = quad("Patch2", [(-1.0, 0, 0.7), (1.0, 0, 0.7), (1.0, 0, 0.76), (-1.0, 0, 0.76)], [(0, 0), (2.0, 0), (2.0, 1), (0, 1)])
            objs = [p, p2]
            bmin, bmax = (-1.0, -0.2, 0.0), (1.0, 0.2, 1.0)
        for o in objs:
            o.data.materials.append(m)
        if mode == "world":
            preview.frame(cam, bmin, bmax, az=30, el=32, margin=0.72)
        else:
            preview.frame(cam, bmin, bmax, az=10, el=10, margin=0.9)
        tl = f"{name}" + (f"  ({tile:g} m)" if mode != "fit" and reg[name]['kind'] != 'param' else "")
        preview.label(cam, tl)
        tiles.append(preview.render_array(tmp))
        for o in objs:
            if o.name.startswith("Patch2"):
                bpy.data.objects.remove(o)
        print("[matprev]", name)
    per = cols * 3
    for s in range(0, len(tiles), per):
        out = os.path.join(envpaths.PREVIEWS, f"materials_{s // per + 1:02d}.png")
        preview.sheet(tiles[s:s + per], cols, out)
        print("[matprev] sheet", out)


main()
