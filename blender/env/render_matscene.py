"""HD material preview: each material on a 6 x 6 m floor, a 6 x 3 m back wall, a 1 m cube and a sphere,
seen from eye height under an overcast sky with a low grazing key light (shows normal detail and roughness).

  Blender -b --factory-startup --python render_matscene.py -- [--size 960x540] [--cols 2] [--out name] names...
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import envpaths  # noqa: E402
import preview  # noqa: E402


def mesh_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def quad(name, corners, uvs):
    bm = bmesh.new()
    vs = [bm.verts.new(c) for c in corners]
    f = bm.faces.new(vs)
    uvl = bm.loops.layers.uv.new("UVMap")
    for l, uv in zip(f.loops, uvs):
        l[uvl].uv = uv
    return mesh_obj(name, bm)


def cube(name, s, at):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=s)
    bmesh.ops.bevel(bm, geom=bm.edges, offset=0.012, segments=2, affect="EDGES")
    uvl = bm.loops.layers.uv.new("UVMap")
    bm.normal_update()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda k: abs(n[k]))
        for l in f.loops:
            c = l.vert.co + Vector(at)
            l[uvl].uv = (c.x, c.y) if ax == 2 else ((c.x, c.z) if ax == 1 else (c.y, c.z))
    bmesh.ops.translate(bm, vec=Vector(at), verts=bm.verts)
    ob = mesh_obj(name, bm)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def sphere(r, at):
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=r, calc_uvs=True)
    for f in bm.faces:
        for l in f.loops:
            u, v = l[uvl].uv
            l[uvl].uv = (u * math.tau * r, v * math.pi * r)
    bmesh.ops.translate(bm, vec=Vector(at), verts=bm.verts)
    ob = mesh_obj("Sphere", bm)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    size, cols, out, names, night = (960, 540), 2, None, [], False
    i = 0
    while i < len(argv):
        if argv[i] == "--size":
            size = tuple(int(x) for x in argv[i + 1].split("x")); i += 2
        elif argv[i] == "--cols":
            cols = int(argv[i + 1]); i += 2
        elif argv[i] == "--out":
            out = argv[i + 1]; i += 2
        elif argv[i] == "--night":
            night = True; i += 1
        else:
            names.append(argv[i]); i += 1
    tmp = os.path.join(envpaths.STATE, f"tmp_matscene_{os.getpid()}.png")
    tiles = []
    for name in names:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        preview.setup_render(size, 32)
        if night:
            preview.setup_world(0.25, top=(0.05, 0.06, 0.12), horizon=(0.10, 0.07, 0.16), bottom=(0.01, 0.01, 0.015))
            preview.add_sun((55, 0, -35), 0.9, angle=2.0, color=(0.62, 0.7, 1.0))
            preview.add_area((-2.5, 2.9, 2.6), (90, 0, 180), 0.8, 120.0, (1.0, 0.17, 0.84))   # neon sign on back wall
            preview.add_area((2.2, 2.9, 2.0), (90, 0, 180), 0.6, 90.0, (0.0, 0.9, 1.0))
            preview.add_area((0.5, -6, 3.0), (70, 0, 0), 4.0, 300.0, (0.5, 0.45, 1.0))
            # visible neon strips (emissive) on the back wall so wet floors show their reflections
            for (x, z, w, c) in ((-2.5, 2.6, 1.4, (1.0, 0.17, 0.84)), (2.2, 2.0, 1.0, (0.0, 0.9, 1.0))):
                me = bpy.data.meshes.new("neon")
                me.from_pydata([(x - w / 2, 2.98, z - 0.03), (x + w / 2, 2.98, z - 0.03), (x + w / 2, 2.98, z + 0.03), (x - w / 2, 2.98, z + 0.03)], [], [(0, 1, 2, 3)])
                ob = bpy.data.objects.new("neon", me)
                bpy.context.scene.collection.objects.link(ob)
                mm = bpy.data.materials.new("neonm")
                mm.use_nodes = True
                b = mm.node_tree.nodes["Principled BSDF"]
                b.inputs["Emission Color"].default_value = (*c, 1)
                b.inputs["Emission Strength"].default_value = 40.0
                me.materials.append(mm)
            preview._glare()
        else:
            preview.setup_world(1.1, top=(0.62, 0.68, 0.78), horizon=(0.5, 0.52, 0.56), bottom=(0.16, 0.16, 0.17))
            preview.add_sun((62, 0, -38), 4.5, angle=1.5)  # low-ish key from front-left: grazing on floor and walls
            preview.add_sun((50, 0, 140), 0.8, color=(0.75, 0.85, 1.0))
        m = preview.textured(name)
        tile, mode = preview.tile_of(name)
        objs = []
        k = 3.0
        objs.append(quad("Floor", [(-k, -k, 0), (k, -k, 0), (k, k, 0), (-k, k, 0)], [(-k, -k), (k, -k), (k, k), (-k, k)]))
        objs.append(quad("Wall", [(-k, k, 0), (k, k, 0), (k, k, 3.2), (-k, k, 3.2)], [(-k, 0), (k, 0), (k, 3.2), (-k, 3.2)]))
        objs.append(quad("WallL", [(-k, -k, 0), (-k, k, 0), (-k, k, 3.2), (-k, -k, 3.2)], [(-k, 0), (k, 0), (k, 3.2), (-k, 3.2)]))
        objs.append(cube("Cube", 1.0, (1.2, 1.2, 0.5)))
        objs.append(sphere(0.45, (-0.4, 0.6, 0.45)))
        for o in objs:
            o.data.materials.append(m)
        cd = bpy.data.cameras.new("Cam")
        cam = bpy.data.objects.new("Cam", cd)
        bpy.context.scene.collection.objects.link(cam)
        bpy.context.scene.camera = cam
        cd.lens = 28
        cam.location = (1.9, -2.9, 1.65)
        cam.rotation_euler = (math.radians(74), 0, math.radians(26))
        preview.label(cam, f"{name}  (tile {tile:g} m)", size=0.03)
        tiles.append(preview.render_array(tmp))
        print("[matscene]", name)
    base = out or ("matscene_" + "_".join(names[:2]))
    per = cols * 2
    for s in range(0, len(tiles), per):
        p = os.path.join(envpaths.PREVIEWS, f"{base}_{s // per + 1:02d}.png")
        preview.sheet(tiles[s:s + per], cols, p)
        print("[matscene] sheet", p)


main()
