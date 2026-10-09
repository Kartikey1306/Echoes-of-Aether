"""Kael v2 shared helpers: paths, logging, numpy mesh access, Cycles studio renders."""
import bpy, os, sys, math, time
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
KROOT = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(KROOT, "..", "..", ".."))
BLENDER_SCRIPTS = os.path.join(ROOT, "blender", "scripts")
for p in (HERE, BLENDER_SCRIPTS):
    if p not in sys.path:
        sys.path.insert(0, p)
UNITY = os.path.join(ROOT, "unity", "EchoesOfAether")
UNITY_KAEL = os.path.join(UNITY, "Assets", "Art", "Characters", "Kael")
ANIM_MALE = os.path.join(UNITY, "Assets", "Art", "Animations", "Anim_Male.fbx")
BLENDS = os.path.join(KROOT, "blends")
PREVIEWS = os.path.join(KROOT, "previews")
TEX = os.path.join(KROOT, "tex")
LOGS = os.path.join(KROOT, "logs")
MPFB_DATA = os.path.expanduser("~/Library/Application Support/Blender/5.2/extensions/.user/user_default/mpfb/data")
MPFB_SYS = os.path.expanduser("~/Library/Application Support/Blender/5.2/extensions/user_default/mpfb/data")
for d in (BLENDS, PREVIEWS, TEX, LOGS):
    os.makedirs(d, exist_ok=True)
T0 = time.time()
PRE = "mixamorig:"


def log(*a):
    print(f"[kael {time.time() - T0:7.1f}s]", *a, flush=True)


def args():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(a, name, default=None):
    if name in a:
        i = a.index(name)
        return a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith("--") else True
    return default


# ----------------------------------------------------------------------------- numpy mesh access

def get_co(o):
    a = np.empty(len(o.data.vertices) * 3, np.float32)
    o.data.vertices.foreach_get("co", a)
    return a.reshape(-1, 3).astype(np.float64)


def set_co(o, co):
    o.data.vertices.foreach_set("co", np.asarray(co, np.float32).ravel())
    o.data.update()


def faces_of(o):
    return [list(p.vertices) for p in o.data.polygons]


def evaluated_co(o, dg=None):
    dg = dg or bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    a = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", a)
    ev.to_mesh_clear()
    return a.reshape(-1, 3).astype(np.float64)


def ss(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def nrm(v):
    v = np.asarray(v, np.float64)
    return v / max(np.linalg.norm(v), 1e-12)


def nrm_rows(v):
    v = np.asarray(v, np.float64)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)


def vertex_normals(co, faces):
    """Area-weighted vertex normals for polygons (lists of indices)."""
    n = np.zeros_like(co)
    for f in faces:
        p = co[f]
        c = p.mean(0)
        fn = np.zeros(3)
        for i in range(len(f)):
            fn += np.cross(p[i] - c, p[(i + 1) % len(f)] - c)
        for v in f:
            n[v] += fn
    return nrm_rows(n)


def vertex_normals_fast(o):
    me = o.data
    me.update()
    a = np.empty(len(me.vertices) * 3, np.float32)
    me.vertex_normals.foreach_get("vector", a) if hasattr(me, "vertex_normals") else me.vertices.foreach_get("normal", a)
    return a.reshape(-1, 3).astype(np.float64)


# ----------------------------------------------------------------------------- render


def _new(name, data):
    o = bpy.data.objects.new(name, data)
    o["k_preview"] = True
    bpy.context.scene.collection.objects.link(o)
    return o


def clear_preview():
    for o in list(bpy.data.objects):
        if o.get("k_preview"):
            bpy.data.objects.remove(o, do_unlink=True)


def area(name, loc, target, energy, size, color, size_y=None):
    l = _new(name, bpy.data.lights.new(name, "AREA"))
    l.data.energy = energy
    l.data.size = size
    if size_y:
        l.data.shape = "RECTANGLE"
        l.data.size_y = size_y
    l.data.color = color
    l.location = loc
    d = Vector(target) - Vector(loc)
    l.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return l


def cycles(samples=96, res=(1000, 1250), denoise=True, exposure=-0.6, look="AgX - Base Contrast"):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type == "METAL"
        sc.cycles.device = "GPU"
    except Exception as e:
        print("GPU setup failed", e)
    sc.cycles.samples = samples
    sc.cycles.use_denoising = denoise
    sc.cycles.max_bounces = 8
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.transparent_max_bounces = 16
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = look
    except Exception:
        pass
    sc.view_settings.exposure = exposure
    return sc


def world(color, strength=1.0):
    w = bpy.data.worlds.get("k_world") or bpy.data.worlds.new("k_world")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (*color, 1)
    bg.inputs[1].default_value = strength
    bpy.context.scene.world = w


def floor(color=(0.06, 0.065, 0.07), rough=0.5, z=0.0):
    me = bpy.data.meshes.new("k_floor")
    s = 20
    me.from_pydata([(-s, -s, z), (s, -s, z), (s, s, z), (-s, s, z)], [], [(0, 1, 2, 3)])
    o = _new("k_floor", me)
    m = bpy.data.materials.get("k_floor") or bpy.data.materials.new("k_floor")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    me.materials.append(m)
    return o


def backdrop(color=(0.05, 0.055, 0.065)):
    """Curved cyclorama behind the subject (+Y)."""
    bpy.ops.mesh.primitive_plane_add(size=1)
    o = bpy.context.active_object
    o.name = "k_backdrop"
    o["k_preview"] = True
    me = o.data
    import bmesh
    bm = bmesh.new()
    W, steps = 16, 24
    verts = []
    for i in range(steps + 1):
        t = i / steps * math.pi / 2
        y = 3.0 + math.sin(t) * 2.0
        z = 2.0 - math.cos(t) * 2.0
        verts.append((y, z))
    rows = []
    for x in (-W / 2, W / 2):
        rows.append([bm.verts.new((x, y - 2 + 0.0, z)) for (y, z) in verts])
    for i in range(steps):
        bm.faces.new((rows[0][i], rows[1][i], rows[1][i + 1], rows[0][i + 1]))
    # floor part
    a0, a1 = bm.verts.new((-W / 2, -8, 0)), bm.verts.new((W / 2, -8, 0))
    bm.faces.new((a0, a1, rows[1][0], rows[0][0]))
    bm.to_mesh(me)
    bm.free()
    m = bpy.data.materials.get("k_backdrop") or bpy.data.materials.new("k_backdrop")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = 0.7
    me.materials.clear()
    me.materials.append(m)
    for p in me.polygons:
        p.use_smooth = True
    return o


def camera(loc, aim, lens, sensor=36):
    cam = _new("k_cam", bpy.data.cameras.new("k_cam"))
    cam.data.lens = lens
    cam.data.sensor_width = sensor
    cam.data.clip_start = 0.01
    cam.location = loc
    d = Vector(aim) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def rig_lights(kind, center, scale=1.0):
    """kind: 'portrait' (neutral 3-point), 'menu' (game designer: neutral key + cyan/magenta rims),
    'night' (cool ambience, cyan/magenta neon rims)."""
    c = Vector(center)
    s = scale
    if kind == "portrait":
        area("k_key", c + Vector((1.1, -1.5, 0.9)) * s, c, 110 * s * s, 0.9 * s, (1.0, 0.96, 0.91))
        area("k_fill", c + Vector((-1.6, -1.2, 0.2)) * s, c, 18 * s * s, 1.6 * s, (0.9, 0.94, 1.0))
        area("k_rim", c + Vector((-0.8, 1.5, 0.9)) * s, c, 90 * s * s, 0.6 * s, (0.95, 0.97, 1.0))
        area("k_rim2", c + Vector((1.2, 1.3, 0.5)) * s, c, 50 * s * s, 0.6 * s, (1.0, 0.97, 0.95))
    elif kind == "menu":
        area("k_key", c + Vector((1.0, -1.6, 0.8)) * s, c, 95 * s * s, 1.0 * s, (1.0, 0.97, 0.94))
        area("k_fill", c + Vector((-1.5, -1.0, 0.1)) * s, c, 14 * s * s, 1.8 * s, (0.8, 0.88, 1.0))
        area("k_rim_c", c + Vector((-1.2, 1.2, 0.6)) * s, c, 160 * s * s, 0.5 * s, (0.25, 0.85, 1.0))
        area("k_rim_m", c + Vector((1.3, 1.1, 0.4)) * s, c, 120 * s * s, 0.5 * s, (1.0, 0.2, 0.8))
    else:
        area("k_moon", c + Vector((-1.4, -1.0, 2.0)) * s, c, 90 * s * s, 1.6 * s, (0.6, 0.72, 1.0))
        area("k_rim_c", c + Vector((1.3, 1.5, 0.8)) * s, c, 240 * s * s, 0.5 * s, (0.2, 0.85, 1.0))
        area("k_rim_m", c + Vector((-1.4, 1.4, 0.5)) * s, c, 160 * s * s, 0.5 * s, (1.0, 0.18, 0.8))
        area("k_warm", c + Vector((1.8, -1.2, -0.3)) * s, c, 40 * s * s, 2.0 * s, (1.0, 0.62, 0.35))


def render_to(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    log("RENDER", path)
    return path


def contact_sheet(paths, out, cols=3, width=600, labels=None):
    """Combine PNGs into one sheet (Pillow is not available in Blender's python: use bpy images)."""
    imgs = []
    for p in paths:
        im = bpy.data.images.load(p, check_existing=False)
        w, h = im.size
        a = np.array(im.pixels[:], np.float32).reshape(h, w, 4)
        bpy.data.images.remove(im)
        # nearest resample to width
        sc = width / w
        hh = int(h * sc)
        ys = (np.arange(hh) / sc).astype(int).clip(0, h - 1)
        xs = (np.arange(width) / sc).astype(int).clip(0, w - 1)
        imgs.append(a[ys][:, xs])
    rows = (len(imgs) + cols - 1) // cols
    H = max(i.shape[0] for i in imgs)
    sheet = np.zeros((rows * H, cols * width, 4), np.float32)
    sheet[..., 3] = 1
    for k, im in enumerate(imgs):
        r, c = divmod(k, cols)
        r = rows - 1 - r  # blender images are bottom-up
        sheet[r * H + (H - im.shape[0]): r * H + H, c * width:(c + 1) * width] = im
    img = bpy.data.images.new("sheet", cols * width, rows * H, alpha=True)
    img.pixels[:] = sheet.ravel()
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    log("SHEET", out)
    return out
