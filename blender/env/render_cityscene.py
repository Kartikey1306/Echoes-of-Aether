"""Hero 'city street' preview: assembles exported FBX assets (buildings, facade modules, street kit, neon signs,
skyline) into a rainy cyberpunk street at night and renders it with EEVEE (fog, bloom, neon point lights placed
at every asset's manifest light anchors).

  Blender -b --factory-startup --python render_cityscene.py -- [--shot street|alley|high] [--size 1600x900] [--samples 64]
Writes previews/city_<shot>.png. Missing assets are skipped (the layout degrades gracefully).
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Euler, Matrix, Vector  # noqa: E402

import envpaths  # noqa: E402
import matdefs  # noqa: E402
import preview  # noqa: E402

RECS = json.load(open(os.path.join(envpaths.STATE, "assets.json")))
_cache = {}
_lights = []
NEON_RGB = {"magenta": (1.0, 0.17, 0.84), "pink": (1.0, 0.31, 0.6), "cyan": (0.0, 0.9, 1.0), "blue": (0.24, 0.48, 1.0),
            "yellow": (1.0, 0.88, 0.3), "violet": (0.61, 0.36, 1.0)}


def _glow_rgb(rec):
    gm = str(rec.get("glowMaterial") or rec.get("glow") or "")
    for k, v in NEON_RGB.items():
        if k in gm:
            return v
    if gm.startswith("#") and len(gm) == 7:
        return tuple(int(gm[i:i + 2], 16) / 255 for i in (1, 3, 5))
    mats = rec.get("materials", [])
    for k, v in NEON_RGB.items():
        if any(f"neon_{k}" in m or f"strip_{k}" in m for m in mats):
            return v
    return (1.0, 0.72, 0.45)


def _hex(h):
    h = str(h)
    if h.startswith("#") and len(h) == 7:
        return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return None


def _anchors(rec):
    """All light anchors of a record as [(unity_pos, rgb or None)], whatever format the module used."""
    out = []

    def add(v):
        if isinstance(v, dict):
            if "position" in v:
                out.append((v["position"], _hex(v.get("color"))))
            else:
                for vv in v.values():
                    add(vv)
        elif isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v):
            out.append((v, None))
        elif isinstance(v, list):
            for vv in v:
                add(vv)
    for k in ("light", "lights", "beacons"):
        if k in rec:
            add(rec[k])
    return out


def load(name):
    """Import an asset's FBX once (LOD0 only, textured preview materials); return the mesh object (hidden template)."""
    if name in _cache:
        return _cache[name]
    rec = RECS.get(name)
    if not rec:
        print("[city] missing", name)
        _cache[name] = None
        return None
    path = os.path.join(envpaths.UNITY_ENV, rec["file"])
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, axis_forward="-Z", axis_up="Y", use_custom_normals=True, bake_space_transform=True)
    new = [o for o in bpy.data.objects if o not in before]
    keep = None
    for o in new:
        if o.type == "MESH" and o.name.endswith("_LOD0"):
            keep = o
        else:
            bpy.data.objects.remove(o)
    if keep is None:
        _cache[name] = None
        return None
    for m in keep.data.materials:
        if m is not None and m.name in matdefs.REGISTRY:
            preview.textured(m.name, m)
    keep.hide_render = True
    keep.hide_viewport = True
    _cache[name] = (keep, rec)
    return _cache[name]


def place(name, x, y, rz=0.0, z=0.0, scale=1.0, lights=True, light_power=1.0):
    t = load(name)
    if not t:
        return None
    src, rec = t
    ob = bpy.data.objects.new(name, src.data)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (x, y, z)
    ob.rotation_euler = (0, 0, math.radians(rz))
    ob.scale = (scale, scale, scale)
    if lights:
        M = ob.matrix_world.copy()
        base_col = _glow_rgb(rec)
        for pos, col in _anchors(rec)[:8]:
            b = Vector((-pos[0], -pos[2], pos[1]))
            _lights.append((M @ b, col or base_col, light_power))
    return ob


def point(loc, col, power, radius=0.15):
    ld = bpy.data.lights.new("P", "POINT")
    ld.energy = power
    ld.color = col
    ld.shadow_soft_size = radius
    ob = bpy.data.objects.new("P", ld)
    ob.location = loc
    bpy.context.scene.collection.objects.link(ob)
    return ob


def ground_plane(name, mat, x0, x1, y0, y1, z=0.0):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for li, (u, v) in enumerate([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]):
        uv.data[li].uv = (u, v)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    m = bpy.data.materials.get("__g_" + mat) or bpy.data.materials.new("__g_" + mat)
    preview.textured(mat, m)
    me.materials.append(m)
    return ob


def curb(x, y0, y1, h=0.15, w=0.3):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(w, y1 - y0, h), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(x, (y0 + y1) / 2, h / 2), verts=bm.verts)
    uvl = bm.loops.layers.uv.new("UVMap")
    bm.normal_update()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda k: abs(n[k]))
        for l in f.loops:
            c = l.vert.co
            l[uvl].uv = (c.x, c.y) if ax == 2 else ((c.x, c.z) if ax == 1 else (c.y, c.z))
    me = bpy.data.meshes.new("curb")
    bm.to_mesh(me)
    ob = bpy.data.objects.new("curb", me)
    bpy.context.scene.collection.objects.link(ob)
    m = bpy.data.materials.get("__g_concrete") or bpy.data.materials.new("__g_concrete")
    preview.textured("concrete", m)
    me.materials.append(m)


def fog(density=0.012, color=(0.12, 0.1, 0.2)):
    w = bpy.context.scene.world
    nt = w.node_tree
    out = [n for n in nt.nodes if n.type == "OUTPUT_WORLD"][0]
    vs = nt.nodes.new("ShaderNodeVolumePrincipled")
    vs.inputs["Density"].default_value = density
    vs.inputs["Color"].default_value = (*color, 1.0)
    vs.inputs["Anisotropy"].default_value = 0.35
    nt.links.new(vs.outputs[0], out.inputs["Volume"])
    sc = bpy.context.scene
    try:
        sc.eevee.volumetric_end = 400.0
        sc.eevee.volumetric_tile_size = "4"
        sc.eevee.volumetric_samples = 96
        sc.eevee.use_volumetric_shadows = True
    except Exception as e:
        print("[city] volumetric settings:", e)


def street_layout(shot):
    """Street along +Y (Blender). Left buildings face +X, right buildings face -X. Road 12 m wide, sidewalks 4 m."""
    road = 6.0
    ground_plane("road", "asphalt", -road, road, -20, 260)
    for sx in (-1, 1):
        ground_plane("walk", "paving", sx * road if sx > 0 else -road - 4.4, road + 4.4 if sx > 0 else -road, -20, 260, z=0.15)
        curb(sx * (road + 0.15), -20, 260)
    # building rows: (name, mass depth along X, mass width along Y)
    left = [("Building_MidRise_A", 12, 12), ("Building_MidRise_C", 12, 16), ("Building_HighRise_D", 16, 16), ("Building_MidRise_B", 12, 20),
            ("Building_MidRise_A", 12, 12), ("Building_HighRise_D", 16, 16)]
    right = [("Building_MidRise_B", 12, 20), ("Building_MidRise_A", 12, 12), ("Building_HighRise_D", 16, 16), ("Building_MidRise_C", 12, 16),
             ("Building_MidRise_B", 12, 20)]
    walk = road + 4.4
    for side, row in ((-1, left), (1, right)):
        y = -6.0
        for name, dep, wid in row:
            rec = RECS.get(name)
            if rec and rec.get("massFootprint"):
                wid, dep = rec["massFootprint"][0], rec["massFootprint"][1]
            # the building front (local -Y) must face the street: left side rotate +90 (front -> +X), right -90
            cx = side * (walk + 0.6 + dep / 2)
            place(name, cx, y + wid / 2, rz=90.0 if side < 0 else -90.0, z=0.15, light_power=60)
            y += wid + 1.5
    # skyline at the end of the street and to the sides
    place("Skyline_Twin_D", 0, 420, rz=0, light_power=0)
    place("Skyline_Tower_A", -90, 320, rz=15, light_power=0)
    place("Skyline_Tower_B", 110, 280, rz=-10, light_power=0)
    place("Skyline_Tower_C", -160, 200, rz=80, light_power=0)
    place("Skyline_Tower_A", 180, 380, rz=40, light_power=0)
    place("Skyline_Tower_C", 70, 520, rz=0, light_power=0)
    # elevated rail crossing the street + skybridge
    for k in range(8):
        place("ElevatedRail_Deck_14m", -49 + k * 14, 92, rz=90, z=9.5, light_power=40)
    for x in (-42, -14, 14, 42):
        place("ElevatedRail_Pier", x, 92, rz=90, z=0.0, lights=False)
    place("Skybridge_Enclosed_12m", 0, 60, rz=0, z=16.0, light_power=25)
    # street furniture (agents' kits; skipped if absent)
    for k, y in enumerate((4, 22, 40, 58, 76, 110, 130)):
        place("StreetLight", -(road + 0.6), y, rz=90, z=0.15, light_power=120)
        place("StreetLight", road + 0.6, y + 9, rz=-90, z=0.15, light_power=120)
    props = [("Vending_Machine_Drinks", -(walk - 0.5), 9, 90), ("Vending_Machine_Food", -(walk - 0.5), 10.1, 90), ("Ramen_Stall", road + 2.4, 30, -90),
             ("Traffic_Light_Cyber", road + 0.8, 48, -90), ("Traffic_Light_Cyber", -(road + 0.8), 50, 90), ("Bus_Shelter_Neon", -(road + 2.0), 34, 90),
             ("Kiosk_Neon", road + 2.0, 16, -90), ("Bollard", -(road + 0.5), 14, 0), ("Bollard", -(road + 0.5), 15.5, 0),
             ("Barrier_Jersey", 2.5, 70, 10), ("TrashBin", road + 1.0, 12, 0), ("Cardboard_Box_Stack", -(walk - 0.6), 24, 30),
             ("Barrel_Plastic_Blue", road + 3.8, 44, 0), ("Pallet_Stack", road + 3.6, 46, 20), ("Holo_Projector_Base", 0.0, 100, 0),
             ("Street_Food_Counter", -(walk - 0.4), 64, 90), ("Billboard_Pole_Double", road + 3.0, 86, -90), ("Car_Sedan", -2.8, 26, 180), ("Car_Sedan_Red", 3.0, 52, 0)]
    for name, x, y, rz in props:
        place(name, x, y, rz=rz, z=0.0 if x == 0 or abs(x) < road else 0.15, light_power=50)
    # wall neon signs on the building fronts
    signs = [("Neon_Glyph_Column", -(walk + 0.65), 14, 90, 4.2), ("Neon_Bowl", road + 4.4 + 0.65, 30, -90, 4.0), ("Sign_Blade_A", -(walk + 0.6), 42, 90, 3.6),
             ("Neon_Arrow_Right", road + 4.4 + 0.65, 60, -90, 3.8), ("Sign_Blade_B", road + 4.4 + 0.6, 74, -90, 4.0), ("Billboard_LED_Wall_6x3", -(walk + 0.7), 80, 90, 7.5)]
    for name, x, y, rz, z in signs:
        place(name, x, y, rz=rz, z=z, light_power=80)
    if shot == "high":
        return (Vector((0.0, -18.0, 22.0)), (62, 0, 0), 24)
    if shot == "alley":
        return (Vector((-(road + 2.2), 2.0, 1.6)), (86, 0, -12), 22)
    return (Vector((1.2, -14.0, 1.7)), (88, 0, 0), 26)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    shot, size, samples = "street", (1600, 900), 64
    i = 0
    while i < len(argv):
        if argv[i] == "--shot":
            shot = argv[i + 1]; i += 2
        elif argv[i] == "--size":
            size = tuple(int(v) for v in argv[i + 1].split("x")); i += 2
        elif argv[i] == "--samples":
            samples = int(argv[i + 1]); i += 2
        else:
            i += 1
    bpy.ops.wm.read_factory_settings(use_empty=True)
    preview.setup_render(size, samples)
    sc = bpy.context.scene
    sc.view_settings.exposure = 0.6
    preview.setup_world(0.45, top=(0.05, 0.06, 0.12), horizon=(0.16, 0.09, 0.2), bottom=(0.01, 0.01, 0.012))
    preview.add_sun((55, 0, 30), 0.6, angle=3.0, color=(0.5, 0.6, 1.0))
    fog(0.006)
    preview._glare()
    cam_loc, cam_rot, lens = street_layout(shot)
    n = 0
    for loc, col, pw in _lights[:400]:
        if pw <= 0:
            continue
        point(loc, col, pw)
        n += 1
    print("[city] lights", n, "objects", len(bpy.context.scene.objects))
    cd = bpy.data.cameras.new("Cam")
    cd.lens = lens
    cd.clip_end = 3000
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    sc.camera = cam
    cam.location = cam_loc
    cam.rotation_euler = [math.radians(a) for a in cam_rot]
    out = os.path.join(envpaths.PREVIEWS, f"city_{shot}.png")
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("[city] wrote", out)


main()
