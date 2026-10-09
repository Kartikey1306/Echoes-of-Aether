"""Preview scenes for vehicle renders: 'studio' (dark cyclorama, long strip softboxes) and 'street'
(neon-lit wet street at night). Cycles GPU (Metal), AgX.

Scenes are built around a vehicle whose FRONT points along `front` (Vector) with its base at z=0.
"""
import math
import os
import random

import bpy
from mathutils import Euler, Vector

import vpaths

ENV_TEX = os.path.join(vpaths.ROOT, "unity", "EchoesOfAether", "Assets", "Art", "Environment", "Textures")


def setup_render(res=(1280, 720), samples=128, look="AgX - Medium High Contrast", exposure=0.0):
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
        print("[render] GPU unavailable:", e)
        sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.max_bounces = 8
    sc.cycles.glossy_bounces = 4
    sc.cycles.transmission_bounces = 6
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 1.0
    sc.cycles.sample_clamp_indirect = 8.0
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = look
    sc.view_settings.exposure = exposure
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"


def _mat(name, base=(0.5, 0.5, 0.5), rough=0.5, metal=0.0, emit=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


def _plane(name, size, loc, rot=(0, 0, 0), mat=None):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0], size[1], 1)
    if mat:
        o.data.materials.append(mat)
    return o


def _area(name, loc, target, size, power, color=(1, 1, 1), shape="RECTANGLE", spread=180):
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = shape
    ld.size = size[0]
    ld.size_y = size[1]
    ld.energy = power
    ld.color = color
    ld.spread = math.radians(spread)
    o = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    d = Vector(target) - Vector(loc)
    o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return o


def world(color=(0.01, 0.012, 0.016), strength=1.0):
    w = bpy.data.worlds.new("W")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (*color, 1)
    bg.inputs[1].default_value = strength
    return w


def camera(loc, target, lens=50, name="Cam", dof=None):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = 36
    cd.clip_end = 400
    o = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    d = Vector(target) - Vector(loc)
    o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if dof:
        cd.dof.use_dof = True
        cd.dof.focus_distance = d.length
        cd.dof.aperture_fstop = dof
    bpy.context.scene.camera = o
    return o


# ================================================================================================ studio
def studio(size):
    """size: vehicle (w, l, h) metres. Dark seamless cyc with strip softboxes."""
    w, l, h = size
    world((0.006, 0.007, 0.009), 1.0)
    floor = _mat("studio_floor", (0.012, 0.013, 0.015), rough=0.32)
    floor.node_tree.nodes["Principled BSDF"].inputs["Specular IOR Level"].default_value = 0.35
    # cyclorama: floor + curved back wall, built as a bent grid
    bpy.ops.mesh.primitive_plane_add(size=1)
    o = bpy.context.active_object
    o.name = "cyc"
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=30)
    bpy.ops.object.mode_set(mode="OBJECT")
    S = max(l, 4.0) * 5
    R = S * 0.18
    for v in o.data.vertices:
        x, y = v.co.x * S, (v.co.y + 0.5) * S * 0.75 - S * 0.25  # y from -0.25S to 0.5S
        if y > S * 0.25:
            t = (y - S * 0.25) / R
            a = min(t, math.pi / 2)
            yy = S * 0.25 + R * math.sin(a) + max(0, t - math.pi / 2) * 0
            zz = R * (1 - math.cos(a)) + max(0.0, t - math.pi / 2) * R
            v.co = (x, yy, zz)
        else:
            v.co = (x, y, 0)
    o.data.materials.append(floor)
    for p in o.data.polygons:
        p.use_smooth = True
    # light rig: large overhead softbox, two long side strips, back rim, low front fill
    _area("key_top", (0, 0, h + 3.2), (0, 0, 0), (max(w, 2) * 1.8, l * 1.3), 650, (1.0, 0.98, 0.96))
    for sx in (-1, 1):
        _area(f"strip_{sx}", (sx * (w / 2 + 2.6), 0.0, h + 1.2), (0, 0, h * 0.4), (0.35, l * 1.6), 700, (0.92, 0.96, 1.0))
    _area("rim_back", (0, l / 2 + 4.0, h + 1.5), (0, 0, h * 0.5), (w * 2.0, 0.6), 800, (0.75, 0.85, 1.0))
    _area("rim_front", (0, -(l / 2 + 4.0), h + 1.0), (0, 0, h * 0.5), (w * 2.0, 0.5), 350, (1.0, 0.9, 0.95))
    _area("kick_l", (-(w / 2 + 3), -(l / 2 + 1), 0.4), (0, 0, 0.4), (1.5, 1.5), 200, (1.0, 0.25, 0.75))
    _area("kick_r", ((w / 2 + 3), (l / 2 + 1), 0.4), (0, 0, 0.4), (1.5, 1.5), 200, (0.2, 0.75, 1.0))


# ================================================================================================ street
def _tex_mat_asphalt():
    m = bpy.data.materials.new("wet_asphalt")
    m.use_nodes = True
    nt = m.node_tree
    L = nt.links.new
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.25, 0.25, 0.25)
    L(tc.outputs["Object"], mp.inputs[0])
    base = os.path.join(ENV_TEX, "asphalt")
    bc_p = os.path.join(base, "asphalt_BaseColor.png")
    nm_p = os.path.join(base, "asphalt_Normal.png")
    # puddles: low-frequency noise -> mask
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.22
    nz.inputs["Detail"].default_value = 6
    nz.inputs["Roughness"].default_value = 0.6
    L(tc.outputs["Object"], nz.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.46
    ramp.color_ramp.elements[1].position = 0.56
    L(nz.outputs["Fac"], ramp.inputs[0])
    rmix = nt.nodes.new("ShaderNodeMapRange")
    rmix.inputs["To Min"].default_value = 0.30
    rmix.inputs["To Max"].default_value = 0.02
    L(ramp.outputs["Color"], rmix.inputs["Value"])
    L(rmix.outputs[0], b.inputs["Roughness"])
    if os.path.exists(bc_p):
        bc = nt.nodes.new("ShaderNodeTexImage")
        bc.image = bpy.data.images.load(bc_p, check_existing=True)
        L(mp.outputs[0], bc.inputs[0])
        dark = nt.nodes.new("ShaderNodeMix")
        dark.data_type = "RGBA"
        dark.blend_type = "MULTIPLY"
        dark.inputs[0].default_value = 1.0
        L(bc.outputs["Color"], dark.inputs[6])
        dark.inputs[7].default_value = (0.32, 0.32, 0.34, 1)
        L(dark.outputs[2], b.inputs["Base Color"])
    else:
        b.inputs["Base Color"].default_value = (0.03, 0.03, 0.035, 1)
    if os.path.exists(nm_p):
        nm = nt.nodes.new("ShaderNodeTexImage")
        nm.image = bpy.data.images.load(nm_p, check_existing=True)
        nm.image.colorspace_settings.name = "Non-Color"
        L(mp.outputs[0], nm.inputs[0])
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        L(nm.outputs["Color"], nmap.inputs["Color"])
        st = nt.nodes.new("ShaderNodeMapRange")  # flatten normal in puddles
        st.inputs["To Min"].default_value = 0.6
        st.inputs["To Max"].default_value = 0.0
        L(ramp.outputs["Color"], st.inputs["Value"])
        L(st.outputs[0], nmap.inputs["Strength"])
        L(nmap.outputs[0], b.inputs["Normal"])
    b.inputs["Specular IOR Level"].default_value = 0.6
    return m


def _neon_sign(name, loc, size, color, strength, rot=(0, 0, 0)):
    m = _mat(name + "_m", (0.05, 0.05, 0.05), 0.4, emit=color, strength=strength)
    return _plane(name, size, loc, rot, m)


def street(size, front=Vector((0, -1, 0)), seed=3):
    """Vehicle sits on a wet street running along Y; buildings on both sides with neon signage."""
    w, l, h = size
    rnd = random.Random(seed)
    world((0.004, 0.006, 0.012), 1.0)
    road = _plane("road", (14, 80), (0, 0, 0), mat=_tex_mat_asphalt())
    walk = _mat("sidewalk", (0.05, 0.05, 0.055), 0.25)
    for sx in (-1, 1):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(sx * 6.5, 0, 0.08))
        o = bpy.context.active_object
        o.scale = (3, 80, 0.16)
        o.data.materials.append(walk)
    facade = _mat("facade", (0.025, 0.027, 0.032), 0.55, metal=0.2)
    win_cool = _mat("win_cool", (0.05, 0.05, 0.05), 0.2, emit=(0.55, 0.75, 1.0), strength=2.0)
    win_warm = _mat("win_warm", (0.05, 0.05, 0.05), 0.2, emit=(1.0, 0.62, 0.32), strength=2.0)
    neon_cols = [((1.0, 0.08, 0.6), 22), ((0.05, 0.85, 1.0), 20), ((0.65, 0.25, 1.0), 20), ((1.0, 0.55, 0.08), 16), ((1.0, 0.1, 0.25), 18)]
    for sx in (-1, 1):
        y = -40
        while y < 40:
            bw = rnd.uniform(7, 13)
            bh = rnd.uniform(14, 40)
            depth = rnd.uniform(6, 10)
            bpy.ops.mesh.primitive_cube_add(size=1, location=(sx * (8 + depth / 2), y + bw / 2, bh / 2))
            o = bpy.context.active_object
            o.scale = (depth, bw - 0.3, bh)
            o.data.materials.append(facade)
            # lit windows rows
            for row in range(2, int(bh / 3.2)):
                for col in range(int(bw / 2.2)):
                    if rnd.random() < 0.35:
                        _plane("win", (1.4, 1.6), (sx * 7.98, y + 1.2 + col * 2.2, row * 3.2 + 1.6), (0, math.radians(90), 0),
                               win_warm if rnd.random() < 0.6 else win_cool)
            # neon signs: vertical blades + horizontal bars at street level
            col, stv = rnd.choice(neon_cols)
            if rnd.random() < 0.8:
                _neon_sign("blade", (sx * 7.6, y + bw * 0.5, rnd.uniform(5, 9)), (rnd.uniform(0.5, 0.8), rnd.uniform(3, 6)), col, stv,
                           (0, math.radians(90), 0))
            col2, st2 = rnd.choice(neon_cols)
            _neon_sign("bar", (sx * 7.95, y + bw * 0.5, rnd.uniform(2.6, 3.4)), (0.18, bw * 0.7), col2, st2 * 0.8, (0, math.radians(90), 0))
            y += bw
    # overhead street lights (cool white) + a couple of coloured fill lights near the car
    for yy in (-14, 0, 14):
        ld = bpy.data.lights.new("street", "AREA")
        ld.size, ld.size_y = 0.6, 1.8
        ld.energy = 900
        ld.color = (0.75, 0.85, 1.0)
        o = bpy.data.objects.new("street", ld)
        bpy.context.scene.collection.objects.link(o)
        o.location = (2.5, yy, 7.5)
    _area("fill_mag", (-6.5, 4.5, 2.6), (0, 0, 0.6), (3, 3), 650, (1.0, 0.15, 0.65))
    _area("fill_cyan", (5.5, -3.0, 2.2), (0, 0, 0.6), (3, 3), 900, (0.15, 0.8, 1.0))
    _area("top_soft", (0, 0, h + 4), (0, 0, 0), (max(w, 2) * 2, l * 1.5), 350, (0.8, 0.85, 1.0))
    _area("rim", (0, 9, 3.0), (0, 0, 0.8), (6, 1), 1200, (0.9, 0.3, 1.0))
    # light haze volume
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 10))
    v = bpy.context.active_object
    v.name = "haze"
    v.scale = (16, 80, 20)
    vm = bpy.data.materials.new("haze")
    vm.use_nodes = True
    nt = vm.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    pv = nt.nodes.new("ShaderNodeVolumePrincipled")
    pv.inputs["Density"].default_value = 0.006
    pv.inputs["Anisotropy"].default_value = 0.35
    pv.inputs["Color"].default_value = (0.6, 0.7, 0.9, 1)
    nt.links.new(pv.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    v.data.materials.append(vm)
    bpy.context.scene.cycles.volume_step_rate = 4.0
    bpy.context.scene.cycles.volume_bounces = 0


def cam_three_quarter(size, front, rear=False, lens=40, height=None, dist_mul=1.0, side=1, target_z=None):
    """3/4 view. `front` = unit vector of the vehicle's front (in world). side=+1 -> camera on the vehicle's
    right-hand side for front views (and left for rear views)."""
    w, l, h = size
    f = Vector(front).normalized()
    right = f.cross(Vector((0, 0, 1))).normalized()
    d = (max(l, w * 1.6) * 1.05 + 1.8) * dist_mul * (40 / 40) * (lens / 40)
    az = math.radians(36)
    if rear:
        dirv = (-f * math.cos(az) - right * side * math.sin(az))
    else:
        dirv = (f * math.cos(az) + right * side * math.sin(az))
    hz = height if height is not None else max(0.75, h * 0.62)
    loc = dirv * d + Vector((0, 0, hz))
    tz = target_z if target_z is not None else h * 0.42
    tgt = Vector((0, 0, tz)) + f * (0.04 * l if not rear else -0.04 * l)
    return camera(loc, tgt, lens=lens)
