"""HD preview renders for the character pipeline: studio and game-like night lighting.

Used by hero.py (--previews) and directly:
  blender -b <file.blend> --python preview_hd.py -- <name> [--shots front,back,q34,face,face34,game] [--light studio|night|both]
Outputs blender/out/previews_hd/<name>_<light>_<shot>.png
"""
import bpy, os, sys, math
from mathutils import Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "out", "previews_hd")


def _clear():
    for o in list(bpy.data.objects):
        if o.get("eoa_preview"):
            bpy.data.objects.remove(o, do_unlink=True)


def _new(name, data):
    o = bpy.data.objects.new(name, data)
    o["eoa_preview"] = True
    bpy.context.scene.collection.objects.link(o)
    return o


def _area(name, loc, target, energy, size, color, spot=False):
    l = _new(name, bpy.data.lights.new(name, "SPOT" if spot else "AREA"))
    l.data.energy = energy
    if spot:
        l.data.shadow_soft_size = size
        l.data.spot_size = math.radians(60)
    else:
        l.data.size = size
    l.data.color = color
    l.location = loc
    d = Vector(target) - Vector(loc)
    l.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return l


def _world(color, strength):
    w = bpy.data.worlds.get("eoa_preview_world") or bpy.data.worlds.new("eoa_preview_world")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (*color, 1)
    bg.inputs[1].default_value = strength
    bpy.context.scene.world = w


def _floor(color, rough=0.35, wet=False):
    me = bpy.data.meshes.new("eoa_floor")
    s = 12
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    o = _new("eoa_floor", me)
    m = bpy.data.materials.new("eoa_floor")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    me.materials.append(m)
    return o


def setup(light="studio", res=(900, 1200), samples=64):
    sc = bpy.context.scene
    _clear()
    sc.render.engine = "BLENDER_EEVEE"
    ee = sc.eevee
    ee.taa_render_samples = samples
    for attr, val in (("use_shadows", True), ("use_raytracing", True), ("shadow_ray_count", 2), ("shadow_step_count", 8)):
        if hasattr(ee, attr):
            try:
                setattr(ee, attr, val)
            except Exception:
                pass
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "AgX"
    for look in (("AgX - Medium High Contrast", "Medium High Contrast") if light == "night" else ("None",)):
        try:
            sc.view_settings.look = look
            break
        except Exception:
            pass
    sc.render.film_transparent = False
    if light == "studio":
        _world((0.045, 0.05, 0.06), 1.0)
        _floor((0.08, 0.085, 0.09), 0.6)
    else:
        # Game-like night: dark blue fog ambience, cool moon key, cyan rim, faint warm bounce, wet floor.
        _world((0.012, 0.018, 0.03), 1.0)
        _floor((0.03, 0.035, 0.045), 0.18, wet=True)
    return sc


def lights(light, center, height):
    c = Vector(center)
    top = c + Vector((0, 0, height * 0.35))
    if light == "studio":
        _area("eoa_key", c + Vector((1.6, -2.2, 1.4)), top, 420, 1.6, (1.0, 0.96, 0.92))
        _area("eoa_fill", c + Vector((-2.4, -1.4, 0.8)), c, 140, 2.5, (0.85, 0.9, 1.0))
        _area("eoa_rim", c + Vector((0.6, 2.4, 1.6)), top, 380, 1.2, (0.85, 0.92, 1.0))
        _area("eoa_rim2", c + Vector((-1.8, 1.8, 1.2)), top, 200, 1.0, (0.9, 0.9, 1.0))
    else:
        _area("eoa_moon", c + Vector((-2.0, -1.2, 3.2)), top, 260, 2.0, (0.62, 0.74, 1.0))
        _area("eoa_rim_cyan", c + Vector((1.6, 2.2, 1.5)), top, 520, 0.8, (0.3, 0.85, 1.0))
        _area("eoa_rim_violet", c + Vector((-1.9, 1.9, 1.0)), top, 180, 0.8, (0.6, 0.45, 1.0))
        _area("eoa_warm", c + Vector((2.6, -1.6, 0.5)), c, 90, 3.0, (1.0, 0.6, 0.3))


def camera(loc, aim, lens):
    cam = _new("eoa_cam", bpy.data.cameras.new("eoa_cam"))
    cam.data.lens = lens
    cam.data.clip_start = 0.02
    cam.location = loc
    d = Vector(aim) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def shots_for(height, head_z, face_center):
    h = height
    fc = Vector(face_center)
    return {
        "front": (Vector((0, -4.2, h * 0.55)), Vector((0, 0, h * 0.5)), 50, (900, 1200)),
        "back": (Vector((0, 4.2, h * 0.55)), Vector((0, 0, h * 0.5)), 50, (900, 1200)),
        "q34": (Vector((2.9, -3.0, h * 0.6)), Vector((0, 0, h * 0.5)), 50, (900, 1200)),
        "face": (fc + Vector((0, -0.62, 0.02)), fc, 85, (900, 1100)),
        "face34": (fc + Vector((0.42, -0.48, 0.03)), fc + Vector((0.01, 0, 0)), 85, (900, 1100)),
        "game": (Vector((0.6, 4.0, h + 0.75)), Vector((0, 0, h * 0.62)), 40, (1280, 720)),
    }


def render(name, center, height, face_center, light="studio", which=("front", "back", "q34", "face", "face34", "game"), samples=64):
    os.makedirs(OUT, exist_ok=True)
    out = []
    shots = shots_for(height, face_center[2], face_center)
    for tag in which:
        loc, aim, lens, res = shots[tag]
        setup(light, res, samples)
        lights(light, center, height if tag not in ("face", "face34") else 0.6)
        if tag in ("face", "face34"):
            # Face lights are placed relative to the head.
            for o in [o for o in bpy.data.objects if o.get("eoa_preview") and o.type == "LIGHT"]:
                bpy.data.objects.remove(o, do_unlink=True)
            lights(light, Vector(face_center) - Vector((0, 0, 0.25)), 1.0)
        camera(loc, aim, lens)
        p = os.path.join(OUT, f"{name}_{light}_{tag}.png")
        bpy.context.scene.render.filepath = p
        bpy.ops.render.render(write_still=True)
        out.append(p)
        print("PREVIEW", p)
    return out


def measure(rig_name=None):
    rig = bpy.data.objects.get(rig_name) if rig_name else next(o for o in bpy.data.objects if o.type == "ARMATURE")
    body = next((o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig and (o.name == "Body" or o.name.endswith(".body"))), None)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    zs = [(body.matrix_world @ v.co).z for v in ev.data.vertices]
    height = max(zs)
    hb = rig.data.bones["mixamorig:Head"]
    head = rig.matrix_world @ hb.head_local
    face = Vector((0, head.y - 0.02, head.z + 0.075))
    return height, head.z, face


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = a[0] if a else "char"
    which = a[a.index("--shots") + 1].split(",") if "--shots" in a else ["front", "back", "q34", "face", "face34", "game"]
    light = a[a.index("--light") + 1] if "--light" in a else "both"
    h, hz, face = measure()
    for L in (("studio", "night") if light == "both" else (light,)):
        render(name, (0, 0, 0), h, face, L, which)
