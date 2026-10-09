"""Look-dev renders of the exported game weapons: imports Resources/Weapons/<asset>.fbx with the composed PBR textures
(what Unity gets), studio-lit in Cycles.

  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python blender/weapons/preview_weapons.py -- [assets...]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Vector, Matrix  # noqa: E402

import wkit as W  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RES = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets", "Resources", "Weapons")
TEX = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets", "Art", "Weapons", "Textures")
PREV = os.path.join(HERE, "previews")

ASSETS = {
    # name: (atlas, glow colour, views [(azimuth, elevation, zoom)])
    "kael_pistol": ("hero", (0.35, 0.85, 1.0), [(-125, 16, 1.0), (40, 22, 1.0)]),
    "kael_holster": ("hero", (0.35, 0.85, 1.0), [(-120, 20, 1.0), (60, 25, 1.0)]),
    "kael_emitter": ("hero", (0.35, 0.85, 1.0), [(-130, 30, 1.0), (45, 25, 1.0)]),
    "giva_gauntlet": ("hero", (1.0, 0.3, 0.85), [(-150, 35, 1.0), (30, -25, 1.0)]),
    "energy_cell": ("hero", (0.35, 0.85, 1.0), [(-120, 25, 1.0)]),
    "drone_blaster": ("enemy", (1.0, 0.3, 0.15), [(-140, 20, 1.0), (40, 25, 1.0)]),
    "sentinel_blade": ("enemy", (1.0, 0.3, 0.15), [(-100, 15, 1.0), (60, 20, 1.0)]),
    "guardian_weapons": ("enemy", (0.3, 0.85, 1.0), [(-130, 20, 1.0), (50, 20, 1.0)]),
}


def setup_materials(atlas, glow):
    for m in bpy.data.materials:
        nm = m.name.split(".")[0]
        if nm.endswith("_glow"):
            nt = m.node_tree
            for n in list(nt.nodes):
                nt.nodes.remove(n)
            out = nt.nodes.new("ShaderNodeOutputMaterial")
            em = nt.nodes.new("ShaderNodeEmission")
            em.inputs["Color"].default_value = (*glow, 1)
            em.inputs["Strength"].default_value = 18.0
            nt.links.new(em.outputs[0], out.inputs["Surface"])
        elif nm.endswith("_pbr"):
            nt = m.node_tree
            for n in list(nt.nodes):
                nt.nodes.remove(n)
            out = nt.nodes.new("ShaderNodeOutputMaterial")
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
            nt.links.new(bsdf.outputs[0], out.inputs["Surface"])

            def img(kind, data):
                t = nt.nodes.new("ShaderNodeTexImage")
                t.image = bpy.data.images.load(os.path.join(TEX, "%s_%s.png" % (atlas, kind)), check_existing=True)
                if data:
                    t.image.colorspace_settings.name = "Non-Color"
                return t
            bc, ms, oc, nm_ = img("BaseColor", False), img("MetalSmooth", True), img("Occlusion", True), img("Normal", True)
            mix = nt.nodes.new("ShaderNodeMixRGB")
            mix.blend_type = "MULTIPLY"
            mix.inputs["Fac"].default_value = 1.0
            nt.links.new(bc.outputs["Color"], mix.inputs["Color1"])
            nt.links.new(oc.outputs["Color"], mix.inputs["Color2"])
            nt.links.new(mix.outputs[0], bsdf.inputs["Base Color"])
            sep = nt.nodes.new("ShaderNodeSeparateColor")
            nt.links.new(ms.outputs["Color"], sep.inputs[0])
            nt.links.new(sep.outputs[0], bsdf.inputs["Metallic"])
            inv = nt.nodes.new("ShaderNodeMath")
            inv.operation = "SUBTRACT"
            inv.inputs[0].default_value = 1.0
            nt.links.new(ms.outputs["Alpha"], inv.inputs[1])
            nt.links.new(inv.outputs[0], bsdf.inputs["Roughness"])
            nmap = nt.nodes.new("ShaderNodeNormalMap")
            nt.links.new(nm_.outputs["Color"], nmap.inputs["Color"])
            nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])


def studio(name, views, res=(1280, 800)):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 128
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    world = bpy.data.worlds.new("w")
    sc.world = world
    nt = world.node_tree
    bg = nt.nodes.get("Background") or nt.nodes.new("ShaderNodeBackground")
    wo = nt.nodes.get("World Output") or nt.nodes.new("ShaderNodeOutputWorld")
    if not bg.outputs[0].links:
        nt.links.new(bg.outputs[0], wo.inputs["Surface"])
    bg.inputs[0].default_value = (0.012, 0.014, 0.018, 1)
    bg.inputs[1].default_value = 1.0
    bpy.context.view_layer.update()
    meshes = [o for o in sc.objects if o.type == "MESH"]
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    ctr = (mn + mx) / 2
    rad = (mx - mn).length / 2

    def light(nm, loc, watts, color, size):
        ld = bpy.data.lights.new(nm, "AREA")
        ld.energy = watts * (rad / 0.12) ** 2
        ld.color = color
        ld.size = size * rad
        lo = bpy.data.objects.new(nm, ld)
        sc.collection.objects.link(lo)
        lo.location = ctr + Vector(loc) * rad
        lo.rotation_euler = (ctr - lo.location).to_track_quat("-Z", "Y").to_euler()
    light("key", (-3.0, -4.0, 4.0), 9.0, (1.0, 0.96, 0.92), 3.0)
    light("rim", (4.0, 3.0, 2.5), 14.0, (0.5, 0.78, 1.0), 2.0)
    light("rim2", (-4.0, 3.5, 0.5), 8.0, (1.0, 0.45, 0.85), 2.0)
    light("fill", (1.0, -5.0, -1.0), 1.2, (0.7, 0.75, 0.9), 5.0)
    bpy.ops.mesh.primitive_plane_add(size=rad * 60, location=(ctr.x, ctr.y, mn.z - rad * 0.02))
    fl = bpy.context.active_object
    fm = bpy.data.materials.new("floor_mat")
    fb = fm.node_tree.nodes.get("Principled BSDF")
    fb.inputs["Base Color"].default_value = (0.015, 0.016, 0.02, 1)
    fb.inputs["Roughness"].default_value = 0.3
    fl.data.materials.append(fm)
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 50
    cam_d.clip_start = rad * 0.01
    cam_d.clip_end = rad * 200
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    for vi, (az, el, zoom) in enumerate(views):
        a, e = math.radians(az), math.radians(el)
        dist = rad * 3.3 * zoom
        cam.location = ctr + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dist
        cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(PREV, "%s_%d.png" % (name, vi))
        bpy.ops.render.render(write_still=True)
        print("[preview]", sc.render.filepath)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    names = [a for a in argv if not a.startswith("--")] or list(ASSETS)
    os.makedirs(PREV, exist_ok=True)
    for name in names:
        atlas, glow, views = ASSETS[name]
        W.reset()
        bpy.ops.import_scene.fbx(filepath=os.path.join(RES, name + ".fbx"))
        bpy.context.view_layer.update()
        meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        # spread multi-object files a little so each piece reads
        if name == "giva_gauntlet":
            for o in meshes:
                if o.name.endswith("_R"):
                    o.location.x += 0.13
        if name == "guardian_weapons":
            for o in meshes:
                if o.name.startswith("guardian_blade"):
                    o.location.x += 1.0
        setup_materials(atlas, glow)
        studio(name, views)


if __name__ == "__main__":
    main()
