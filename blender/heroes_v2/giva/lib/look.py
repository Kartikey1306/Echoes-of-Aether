"""Preview lighting, cameras and renders for the Giva v2 pipeline (Cycles GPU or Eevee).

Light rigs (all centred on the character at the origin, facing -Y):
  studio  - neutral warm key, cool fill, cyan + magenta rims (the game's menu stage look)
  night   - rainy neon night: dark blue ambience, cool moon key, magenta/cyan neon rims, wet floor
  clay    - neutral grey three-point for judging forms
"""
import bpy, os, math
from mathutils import Vector
import gv

TAG = "giva_look"


def _new(name, data):
    o = bpy.data.objects.new(name, data)
    o[TAG] = True
    bpy.context.scene.collection.objects.link(o)
    return o


def clear():
    for o in list(bpy.data.objects):
        if o.get(TAG):
            bpy.data.objects.remove(o, do_unlink=True)


def area(name, loc, target, power, size, color, shape="RECTANGLE", size_y=None):
    l = _new(name, bpy.data.lights.new(name, "AREA"))
    l.data.energy = power
    l.data.shape = shape
    l.data.size = size
    l.data.size_y = size_y or size
    l.data.color = color
    l.location = loc
    l.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return l


def world(color, strength=1.0):
    w = bpy.data.worlds.get(TAG) or bpy.data.worlds.new(TAG)
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (*color, 1)
    bg.inputs[1].default_value = strength
    bpy.context.scene.world = w


def backdrop(color, rough=0.5, wet=False):
    """Curved cyclorama (floor bending up into a wall behind the character)."""
    import bmesh
    bm = bmesh.new()
    prof = []
    R = 1.6
    for i in range(14):
        a = i / 13 * math.pi / 2
        prof.append((0, 6.0 - R + math.sin(a) * R, R - math.cos(a) * R))
    prof = [(0, -12.0, 0.0)] + prof + [(0, 6.0, 7.0)]
    rows = []
    for x in (-9.0, 9.0):
        rows.append([bm.verts.new((x, y, z)) for _, y, z in prof])
    for j in range(len(prof) - 1):
        bm.faces.new((rows[0][j], rows[1][j], rows[1][j + 1], rows[0][j + 1]))
    me = bpy.data.meshes.new(TAG + "_cyc")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    o = _new(TAG + "_cyc", me)
    m = bpy.data.materials.new(TAG + "_cyc")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    if wet:
        b.inputs["Coat Weight"].default_value = 0.6
        b.inputs["Coat Roughness"].default_value = 0.05
    me.materials.append(m)
    return o


def rig(kind, center=(0, 0, 0), height=1.73, face=None):
    """Lights for `kind`. face: (x,y,z) head centre for close-ups (lights move in)."""
    c = Vector(center)
    if face is not None:
        f = Vector(face)
        k = 0.35
        if kind == "studio":
            area("key", f + Vector((0.95, -1.15, 0.8)) * k * 2.6, f, 75, 0.55, (1.0, 0.95, 0.9))
            area("fill", f + Vector((-1.4, -1.0, 0.0)) * k * 2.4, f, 9, 1.4, (0.86, 0.9, 1.0))
            area("rimC", f + Vector((1.2, 1.1, 0.35)) * k * 2.2, f, 45, 0.5, (0.35, 0.9, 1.0))
            area("rimM", f + Vector((-1.2, 1.0, 0.25)) * k * 2.2, f, 40, 0.5, (1.0, 0.3, 0.85))
        elif kind == "night":
            area("moon", f + Vector((-0.9, -1.2, 1.0)) * k * 2.2, f, 30, 1.0, (0.6, 0.72, 1.0))
            area("rimC", f + Vector((1.3, 1.0, 0.3)) * k * 2.2, f, 70, 0.4, (0.25, 0.85, 1.0))
            area("rimM", f + Vector((-1.3, 0.9, 0.2)) * k * 2.2, f, 70, 0.4, (1.0, 0.2, 0.8))
            area("bounce", f + Vector((0.6, -1.0, -0.8)) * k * 2.2, f, 8, 1.5, (1.0, 0.55, 0.35))
        elif kind == "concept":
            # soft frontal beauty light like the master concept: large key slightly left and above, broad fill
            area("key", f + Vector((-0.6, -1.5, 0.7)) * k * 2.4, f, 55, 1.4, (1.0, 0.97, 0.94))
            area("fill", f + Vector((1.2, -1.2, 0.1)) * k * 2.4, f, 22, 1.8, (0.95, 0.96, 1.0))
            area("rim", f + Vector((0.4, 1.4, 0.6)) * k * 2.4, f, 18, 1.0, (1, 1, 1))
        else:
            area("key", f + Vector((0.9, -1.3, 0.6)) * k * 2.2, f, 60, 0.9, (1, 1, 1))
            area("fill", f + Vector((-1.4, -1.0, 0.1)) * k * 2.2, f, 20, 1.4, (1, 1, 1))
            area("rim", f + Vector((0.2, 1.4, 0.5)) * k * 2.2, f, 40, 0.8, (1, 1, 1))
        return
    top = c + Vector((0, 0, height * 0.62))
    mid = c + Vector((0, 0, height * 0.5))
    if kind == "studio":
        area("key", c + Vector((1.8, -2.6, 2.4)), top, 260, 1.6, (1.0, 0.95, 0.9))
        area("fill", c + Vector((-2.6, -1.8, 1.2)), mid, 70, 2.6, (0.86, 0.9, 1.0))
        area("rimC", c + Vector((2.0, 2.2, 1.8)), top, 260, 0.8, (0.35, 0.9, 1.0), size_y=2.0)
        area("rimM", c + Vector((-2.0, 2.0, 1.6)), top, 240, 0.8, (1.0, 0.3, 0.85), size_y=2.0)
        area("top", c + Vector((0, 0.4, 3.6)), mid, 50, 1.5, (1.0, 1.0, 1.0))
    elif kind == "night":
        area("moon", c + Vector((-2.0, -1.6, 3.4)), top, 240, 2.0, (0.6, 0.72, 1.0))
        area("rimC", c + Vector((1.8, 2.2, 1.6)), top, 650, 0.5, (0.25, 0.85, 1.0), size_y=2.4)
        area("rimM", c + Vector((-2.0, 1.9, 1.3)), top, 600, 0.5, (1.0, 0.2, 0.8), size_y=2.4)
        area("warm", c + Vector((2.6, -1.8, 0.6)), mid, 90, 3.0, (1.0, 0.55, 0.3))
    elif kind == "concept":
        # soft grey studio like the master concept: large frontal key, wrap fill, gentle top and back separation
        area("key", c + Vector((-1.6, -3.0, 2.6)), top, 230, 3.2, (1.0, 0.98, 0.96))
        area("fill", c + Vector((2.4, -2.6, 1.4)), mid, 95, 3.6, (0.96, 0.97, 1.0))
        area("top", c + Vector((0, -0.6, 3.8)), mid, 60, 2.5, (1.0, 1.0, 1.0))
        area("back", c + Vector((0.5, 2.6, 2.2)), top, 120, 1.6, (1.0, 0.95, 1.0))
    else:
        area("key", c + Vector((1.8, -2.6, 2.4)), top, 300, 1.6, (1, 1, 1))
        area("fill", c + Vector((-2.6, -1.8, 1.2)), mid, 100, 2.6, (1, 1, 1))
        area("rim", c + Vector((0.4, 2.6, 2.2)), top, 250, 1.2, (1, 1, 1))


def setup(kind="studio", engine="CYCLES", res=(1000, 1300), samples=96, floor=True):
    sc = bpy.context.scene
    clear()
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Base Contrast" if kind != "night" else "AgX - Medium High Contrast"
    except Exception:
        try:
            sc.view_settings.look = "None"
        except Exception:
            pass
    if engine == "CYCLES":
        sc.render.engine = "CYCLES"
        gv.enable_gpu()
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
        try:
            sc.cycles.denoiser = "OPENIMAGEDENOISE"
        except Exception:
            pass
        sc.cycles.max_bounces = 8
        sc.cycles.transparent_max_bounces = 24
        sc.cycles.use_adaptive_sampling = True
    else:
        sc.render.engine = "BLENDER_EEVEE"
        ee = sc.eevee
        ee.taa_render_samples = samples
        for attr, val in (("use_shadows", True), ("use_raytracing", True), ("shadow_ray_count", 2), ("shadow_step_count", 8)):
            if hasattr(ee, attr):
                try:
                    setattr(ee, attr, val)
                except Exception:
                    pass
    if kind == "studio":
        world((0.02, 0.022, 0.03), 1.0)
        if floor:
            backdrop((0.07, 0.072, 0.08), 0.55)
    elif kind == "night":
        world((0.006, 0.009, 0.018), 1.0)
        if floor:
            backdrop((0.02, 0.024, 0.032), 0.25, wet=True)
    elif kind == "concept":
        world((0.18, 0.18, 0.19), 1.0)
        if floor:
            backdrop((0.42, 0.42, 0.45), 0.7)
    else:
        world((0.05, 0.05, 0.05), 1.0)
        if floor:
            backdrop((0.18, 0.18, 0.18), 0.6)
    return sc


def camera(loc, aim, lens, name="cam"):
    cam = _new(name, bpy.data.cameras.new(name))
    cam.data.lens = lens
    cam.data.sensor_fit = "VERTICAL"
    cam.data.sensor_height = 24.0
    cam.data.clip_start = 0.02
    cam.location = loc
    cam.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def shot(path, cam_loc, aim, lens, kind="studio", engine="CYCLES", res=(1000, 1300), samples=96, face=None,
         height=1.73, center=(0, 0, 0), floor=True):
    setup(kind, engine, res, samples, floor)
    rig(kind, center, height, face)
    camera(cam_loc, aim, lens)
    bpy.context.scene.render.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    gv.log("render", path)
    return path


def face_shots(prefix, face, kind="studio", engine="CYCLES", samples=96, which=("face", "face34", "profile"), res=(900, 1100)):
    """Close-ups around the face centre `face` (x,y,z)."""
    f = Vector(face)
    defs = {
        "face": (f + Vector((0, -0.86, 0.0)), f, 90),
        "face34": (f + Vector((0.56, -0.65, 0.01)), f + Vector((0.008, 0, 0)), 90),
        "face34L": (f + Vector((-0.56, -0.65, 0.01)), f + Vector((-0.008, 0, 0)), 90),
        "profile": (f + Vector((0.86, -0.03, 0.0)), f + Vector((0, 0.02, 0)), 90),
        "close": (f + Vector((0.12, -0.55, 0.02)), f + Vector((0, 0, 0.005)), 100),
        "head": (f + Vector((0.3, -1.2, 0.02)), f + Vector((0, 0, -0.08)), 75),
    }
    out = []
    for w in which:
        loc, aim, lens = defs[w]
        out.append(shot(f"{prefix}_{w}.png", loc, aim, lens, kind, engine, res, samples, face=face))
    return out


def body_shots(prefix, height=1.73, kind="studio", engine="CYCLES", samples=96, which=("front", "q34", "back", "side"), res=(1000, 1400)):
    h = height
    defs = {
        "front": (Vector((0, -4.6, h * 0.55)), Vector((0, 0, h * 0.5)), 55),
        "q34": (Vector((3.1, -3.5, h * 0.62)), Vector((0, 0, h * 0.5)), 55),
        "q34L": (Vector((-3.1, -3.5, h * 0.62)), Vector((0, 0, h * 0.5)), 55),
        "back": (Vector((0, 4.6, h * 0.58)), Vector((0, 0, h * 0.5)), 55),
        "side": (Vector((4.6, 0, h * 0.55)), Vector((0, 0, h * 0.5)), 55),
        "upper": (Vector((1.0, -2.2, h * 0.8)), Vector((0, 0, h * 0.72)), 60),
        "upperL": (Vector((-1.0, -2.2, h * 0.8)), Vector((0, 0, h * 0.72)), 60),
        "legs": (Vector((0.8, -2.4, h * 0.3)), Vector((0, 0, h * 0.27)), 60),
    }
    out = []
    for w in which:
        loc, aim, lens = defs[w]
        out.append(shot(f"{prefix}_{w}.png", loc, aim, lens, kind, engine, res, samples, height=h))
    return out
