"""robopreview -- EEVEE preview renders (front, 3/4, side, posed) + contact sheet for a built robot."""
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

import robokit as K
import roboscene as RS

TEX = {
    "base": "robot_worn_metal_BaseColor.png",
    "normal": "robot_worn_metal_Normal.png",
    "ms": "robot_worn_metal_MetallicSmoothness.png",
}


def _img(name, noncolor):
    p = os.path.join(RS.TEX_DIR, name)
    if not os.path.exists(p):
        return None
    im = bpy.data.images.load(p, check_existing=True)
    if noncolor:
        im.colorspace_settings.name = "Non-Color"
    return im


def preview_materials(kind, tiling=2.5):
    """Rebuild robot_* materials as preview shaders (see setup_material)."""
    for i, name in enumerate(K.MAT_NAMES):
        m = bpy.data.materials.get(name)
        if m is not None:
            setup_material(m, kind, i, tiling)


def setup_material(m, kind, i, tiling=2.5):
    """Preview shader for material slot i of robot `kind`: palette colour x greyscale detail, normal and
    metallic/smoothness maps (what RobotRig would get if it assigned the Textures/ set), glow as emission."""
    shell, frame, glow, gi = RS.PALETTES[kind]
    surf = RS.SURF_DRONE if kind == "drone" else RS.SURF
    base_im, nrm_im, ms_im = _img(TEX["base"], False), _img(TEX["normal"], True), _img(TEX["ms"], True)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    L = nt.links.new
    L(b.outputs[0], out.inputs["Surface"])
    if i == K.GLOW:
        b.inputs["Base Color"].default_value = (0, 0, 0, 1)
        b.inputs["Emission Color"].default_value = (*RS.hex_lin(glow), 1)
        b.inputs["Emission Strength"].default_value = gi * 0.75
        return
    if i == K.ROTOR:
        b.inputs["Base Color"].default_value = (*RS.hex_lin(RS.ROTOR_COL), 1)
        b.inputs["Alpha"].default_value = 0.45
        m.surface_render_method = "BLENDED"
        return
    col = {K.SHELL: shell, K.FRAME: frame, K.JOINT: RS.JOINT_COL}[i]
    met, sm = surf[{K.SHELL: "shell", K.FRAME: "frame", K.JOINT: "joint"}[i]]
    b.inputs["Base Color"].default_value = (*RS.hex_lin(col), 1)
    b.inputs["Metallic"].default_value = met
    b.inputs["Roughness"].default_value = 1 - sm
    if base_im is None:
        return
    uv = nt.nodes.new("ShaderNodeUVMap")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (tiling, tiling, 1)
    L(uv.outputs[0], mp.inputs["Vector"])
    tb = nt.nodes.new("ShaderNodeTexImage")
    tb.image = base_im
    L(mp.outputs[0], tb.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    mix.inputs[6].default_value = (*RS.hex_lin(col), 1)
    L(tb.outputs["Color"], mix.inputs[7])
    L(mix.outputs[2], b.inputs["Base Color"])
    if ms_im is not None:
        tm = nt.nodes.new("ShaderNodeTexImage")
        tm.image = ms_im
        L(mp.outputs[0], tm.inputs[0])
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        L(tm.outputs["Color"], sep.inputs[0])
        # URP: metallic = map.r ; smoothness = map.a * _Smoothness. Keep the material's metallic level.
        mm = nt.nodes.new("ShaderNodeMath")
        mm.operation = "MULTIPLY"
        mm.inputs[1].default_value = met / 0.7
        L(sep.outputs[0], mm.inputs[0])
        L(mm.outputs[0], b.inputs["Metallic"])
        sm_n = nt.nodes.new("ShaderNodeMath")
        sm_n.operation = "MULTIPLY"
        sm_n.inputs[1].default_value = sm / 0.55
        L(tm.outputs["Alpha"], sm_n.inputs[0])
        rough = nt.nodes.new("ShaderNodeMath")
        rough.operation = "SUBTRACT"
        rough.inputs[0].default_value = 1.0
        rough.use_clamp = True
        L(sm_n.outputs[0], rough.inputs[1])
        L(rough.outputs[0], b.inputs["Roughness"])
    if nrm_im is not None:
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = nrm_im
        L(mp.outputs[0], tn.inputs[0])
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = 0.8
        L(tn.outputs["Color"], nm.inputs["Color"])
        L(nm.outputs[0], b.inputs["Normal"])


# ============================================================================ studio
def studio(res=(560, 760), samples=32):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    ee = sc.eevee
    ee.taa_render_samples = samples
    for attr, val in (("use_raytracing", True), ("use_shadows", True)):
        try:
            setattr(ee, attr, val)
        except Exception:
            pass
    try:
        ee.use_bloom = True
    except Exception:
        pass
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = 0.45

    w = bpy.data.worlds.new("Studio")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 1.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.035, 0.037, 0.04, 1)
    ramp.color_ramp.elements[1].position = 0.85
    ramp.color_ramp.elements[1].color = (0.32, 0.34, 0.37, 1)
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -1
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs[2], mr.inputs["Value"])
    nt.links.new(mr.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs[0], o.inputs[0])

    def sun(rot, e, col, ang=4):
        ld = bpy.data.lights.new("L", "SUN")
        ld.energy = e
        ld.color = col
        ld.angle = math.radians(ang)
        ob = bpy.data.objects.new("L", ld)
        ob.rotation_euler = [math.radians(a) for a in rot]
        sc.collection.objects.link(ob)
        return ob

    sun((52, 0, -32), 5.0, (1.0, 0.95, 0.88))     # key, front-left high
    sun((68, 0, 150), 4.0, (0.62, 0.78, 1.0))     # cool rim from behind-right
    sun((75, 0, 70), 1.4, (0.85, 0.9, 1.0))       # fill from the right
    sun((-60, 0, 0), 0.5, (0.8, 0.85, 0.9))       # bounce from below
    me = bpy.data.meshes.new("floor")
    s = 60
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    fl = bpy.data.objects.new("floor", me)
    sc.collection.objects.link(fl)
    fm = bpy.data.materials.new("__floor")
    fm.use_nodes = True
    fb = fm.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.045, 0.047, 0.05, 1)
    fb.inputs["Roughness"].default_value = 0.55
    me.materials.append(fm)
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cd.lens = 70
    cd.clip_start = 0.05
    cd.clip_end = 500
    return cam, fl


def bounds(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    for o in objs.values():
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi


def aim(cam, objs, az_deg, el_deg=8.0, margin=1.1):
    lo, hi = bounds(objs)
    c = (lo + hi) / 2
    ext = hi - lo
    az, el = math.radians(az_deg), math.radians(el_deg)
    # azimuth 0 = robot front (Blender -Y), +90 = robot's left side (+X)
    d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    sc = bpy.context.scene
    cd = cam.data
    aspect = sc.render.resolution_x / sc.render.resolution_y
    t = cd.sensor_width / 2 / cd.lens          # sensor fit AUTO: applies to the larger image dimension
    tan_h, tan_v = (t, t / aspect) if aspect >= 1 else (t * aspect, t)
    horiz = max(abs(ext.x * math.cos(az)) + abs(ext.y * math.sin(az)), 0.1)
    dist = max(ext.z * 0.5 * margin / tan_v, horiz * 0.5 * margin / tan_h) + max(ext.x, ext.y) * 0.5
    cam.location = c + d * dist
    look = (c - cam.location).normalized()
    cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()


def render_to(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def _load_np(path):
    im = bpy.data.images.load(path)
    w, h = im.size
    a = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    return a.reshape(h, w, 4)


def sheet(paths, out):
    arrs = [_load_np(p) for p in paths]
    h = max(a.shape[0] for a in arrs)
    gap = np.zeros((h, 6, 4), dtype=np.float32)
    gap[..., 3] = 1
    row = []
    for i, a in enumerate(arrs):
        if i:
            row.append(gap)
        row.append(a)
    img = np.concatenate(row, axis=1)
    H, W = img.shape[:2]
    im = bpy.data.images.new("sheet", W, H, alpha=False)
    im.pixels.foreach_set(img.ravel())
    im.filepath_raw = out
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


# ============================================================================ posing
def set_rot(ob, x=0.0, y=0.0, z=0.0):
    """Rotation in robot space (degrees, Euler XYZ like the prototype poses), converted to Blender."""
    # bones live under the +90 X root in robot space, so robot-space rotations apply directly
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = K.Rd(x, y, z).to_quaternion()


def pose_biped(objs, s, kind):
    P = {
        "hips": (0, 12, 0), "spine": (12, 0, 0), "chest": (6, -18, 0), "neck": (-4, 0, 0), "head": (-12, 22, 0),
        "clavicle_L": (0, 0, 6), "upperarm_L": (-95, 0, 12), "forearm_L": (-45, 0, 0), "hand_L": (-15, 0, 0),
        "clavicle_R": (0, 0, -4), "upperarm_R": (20, 0, -60), "forearm_R": (-70, 0, 0), "hand_R": (0, 0, 0),
        "thigh_L": (-48, 0, 4), "shin_L": (75, 0, 0), "foot_L": (-24, 0, 0),
        "thigh_R": (18, 0, -4), "shin_R": (22, 0, 0), "foot_R": (-6, 0, 0),
    }
    for n, r in P.items():
        if n in objs:
            set_rot(objs[n], *r)
    objs["hips"].location = objs["hips"].location + Vector((0, -0.07 * s, 0))
    if kind.startswith("guardian"):
        for n, sx in (("plate_L", 1), ("plate_R", -1)):
            if n in objs:
                objs[n].location = objs[n].location + Vector((sx * 0.46, 0, 0))


def pose_drone(objs):
    # body is a root node (carries the +90 X axis rotation): compose the tilt in robot space
    q = K.Rd(16, 0, -14).to_quaternion()
    objs["body"].rotation_mode = "QUATERNION"
    objs["body"].rotation_quaternion = K.R2B.to_quaternion() @ q
    for i in range(4):
        if "rotor_%d" % i in objs:
            set_rot(objs["rotor_%d" % i], 0, 35 * (i + 1), 0)


def run(kind, robot, objs, views=None):
    """Render the four previews and the contact sheet into previews/."""
    os.makedirs(RS.PREVIEW_DIR, exist_ok=True)
    preview_materials(kind)
    cam, floor = studio(res=(560, 760) if robot.skeleton else (820, 560))
    if not robot.skeleton:
        # flying drone: raise it so the floor shows a contact shadow without clipping
        floor.location.z = -0.9
    paths = []
    views = views or [("front", 0, 6), ("34", 38, 10), ("side", 90, 4)]
    for tag, az, el in views:
        aim(cam, objs, az, el)
        p = os.path.join(RS.PREVIEW_DIR, "%s_%s.png" % (kind, tag))
        render_to(p)
        paths.append(p)
    if robot.skeleton:
        pose_biped(objs, robot.s, kind)
    else:
        pose_drone(objs)
    bpy.context.view_layer.update()
    aim(cam, objs, -35, 12)
    p = os.path.join(RS.PREVIEW_DIR, "%s_pose.png" % kind)
    render_to(p)
    paths.append(p)
    sheet(paths, os.path.join(RS.PREVIEW_DIR, "%s_sheet.png" % kind))
    return paths
