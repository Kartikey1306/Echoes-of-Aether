"""artkit: shared library for the Echoes of Aether 2D art renders (Blender 5.2, Cycles, headless).

Every image is a Cycles render of a scripted scene built from the game's own assets:
  * environment kit FBX + baked PBR textures (unity/.../Art/Environment, built by blender/env)
  * MPFB/MakeHuman characters (blender/out/<id>_export.blend), posed with frames of the retargeted clips
    in unity/.../Art/Animations/Anim_{Male,Female}.fbx
  * rigid-part robots (blender/robots/out/<kind>.blend) posed through their joint transforms.
Source files are only read; scene copies are saved under blender/art/scenes.

Conventions: Blender metres, Z up. Kit assets face Blender -Y (= Unity +Z).
"""
import json
import math
import os
import random
import sys
import time

import bmesh
import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

ROOT = "/Users/kartikey/Desktop/Game"
ART = os.path.join(ROOT, "blender", "art")
SCENES = os.path.join(ART, "scenes")
PREVIEWS = os.path.join(ART, "previews")
ENV_DIR = os.path.join(ROOT, "blender", "env")
ROBO_DIR = os.path.join(ROOT, "blender", "robots")
CHAR_SCRIPTS = os.path.join(ROOT, "blender", "scripts")
CHAR_OUT = os.path.join(ROOT, "blender", "out")
ASSETS = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets")
UNITY_ENV = os.path.join(ASSETS, "Art", "Environment")
UNITY_CHARS = os.path.join(ASSETS, "Art", "Characters")
ANIM_DIR = os.path.join(ASSETS, "Art", "Animations")
RES_ART = os.path.join(ASSETS, "Resources", "Art")
MARKETING = os.path.join(ROOT, "marketing")
FONTS = os.path.join(ASSETS, "UI", "Fonts")
MPFB_DATA = os.path.expanduser("~/Library/Application Support/Blender/5.2/extensions/.user/user_default/mpfb/data")

for _p in (ENV_DIR, ROBO_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import matdefs  # noqa: E402  (blender/env: material registry)

CYAN = (0.115, 0.686, 1.0)      # #5fd8ff linear
VIOLET = (0.386, 0.198, 1.0)    # #a77bff linear
WARM = (1.0, 0.64, 0.35)

USE_HEROES_V2 = True  # Kael / Giva: remade heroes (Unity FBX + manifest), not the older blender/out exports
EMIT_SCALE = 1.0   # global multiplier for kit emission strengths (set per scene)
WET = 0.0          # global wetness for kit materials (rain scenes)
_MATS = {}
_LIB = {}
_STATE = None
_MANIFEST = None


def hexlin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def log(*a):
    print("[art]", *a, flush=True)


# ============================================================================================ scene / render
def reset():
    global _MATS, _LIB
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MATS = {}
    _LIB = {}
    _SKIN_TEMPLATES.clear()



def coll(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def link(ob, collection=None):
    (collection or bpy.context.scene.collection).objects.link(ob)
    return ob


def setup_render(res=(1920, 1080), samples=192, look="AgX - Medium High Contrast", exposure=0.0, transparent=False,
                 adaptive=0.015, clamp=8.0, bounces=8, gamma=1.0):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "METAL"
    cy = sc.cycles
    cy.device = "GPU"
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = adaptive
    cy.adaptive_min_samples = 0
    cy.use_denoising = True
    cy.denoiser = "OPENIMAGEDENOISE"
    cy.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    cy.denoising_prefilter = "ACCURATE"
    try:
        cy.denoising_quality = "HIGH"
        cy.denoising_use_gpu = True
    except Exception:
        pass
    cy.use_light_tree = True
    cy.max_bounces = bounces
    cy.diffuse_bounces = 4
    cy.glossy_bounces = 4
    cy.transmission_bounces = 8
    cy.volume_bounces = 1
    cy.transparent_max_bounces = 48
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.sample_clamp_direct = 0.0
    cy.sample_clamp_indirect = clamp
    cy.blur_glossy = 1.0
    cy.volume_step_rate = 1.0
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    sc.render.filter_size = 1.2
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = look
    except Exception:
        sc.view_settings.look = "None"
    sc.view_settings.exposure = exposure
    sc.view_settings.gamma = gamma
    sc.display_settings.display_device = "sRGB"
    return sc


def camera(loc, target, lens=35.0, fstop=None, focus=None, sensor=36.0, shift=(0.0, 0.0), name="Cam", clip_end=3000.0):
    cd = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cd)
    link(cam)
    cd.lens = lens
    cd.sensor_width = sensor
    cd.clip_start = 0.05
    cd.clip_end = clip_end
    cd.shift_x, cd.shift_y = shift
    cam.location = Vector(loc)
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if fstop:
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = fstop
        cd.dof.focus_distance = focus if focus else d.length
    bpy.context.scene.camera = cam
    return cam


def screen(points):
    """Print normalized screen coordinates (x right, y down) of named world points for composition checks."""
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    for name, p in points.items():
        v = world_to_camera_view(sc, sc.camera, Vector(p))
        log(f"screen {name:12s} x={v.x:.2f} y={1 - v.y:.2f} depth={v.z:.1f}")


def look_at(ob, target, roll=0.0):
    d = Vector(target) - ob.location
    q = d.to_track_quat("-Z", "Y")
    if roll:
        q = q @ Quaternion((0, 0, 1), math.radians(roll))
    ob.rotation_euler = q.to_euler()


def compositor(bloom=0.35, bloom_size=0.62, threshold=1.0, dispersion=0.004, vignette=0.28, glare_type="Bloom",
               streaks=0.0, logo=None, logo_box=None, saturation=1.0):
    """Glare bloom (+ optional faint streaks), slight lens dispersion and a soft vignette.
    logo: path to an RGBA PNG composited over the frame; logo_box = (cx, cy, width) in 0..1 frame units."""
    sc = bpy.context.scene
    ng = bpy.data.node_groups.new("ArtComp", "CompositorNodeTree")
    sc.compositing_node_group = ng
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    N = ng.nodes
    L = ng.links.new
    rl = N.new("CompositorNodeRLayers")
    out = N.new("NodeGroupOutput")
    cur = rl.outputs["Image"]
    if bloom > 0:
        g = N.new("CompositorNodeGlare")
        g.inputs["Type"].default_value = glare_type
        g.inputs["Quality"].default_value = "High"
        g.inputs["Threshold"].default_value = threshold
        g.inputs["Strength"].default_value = bloom
        g.inputs["Size"].default_value = bloom_size
        L(cur, g.inputs["Image"])
        cur = g.outputs["Image"]
    if streaks > 0:
        s = N.new("CompositorNodeGlare")
        s.inputs["Type"].default_value = "Streaks"
        s.inputs["Quality"].default_value = "High"
        s.inputs["Threshold"].default_value = threshold * 2.5
        s.inputs["Strength"].default_value = streaks
        s.inputs["Streaks"].default_value = 2
        s.inputs["Streaks Angle"].default_value = 0.0
        s.inputs["Fade"].default_value = 0.88
        L(cur, s.inputs["Image"])
        cur = s.outputs["Image"]
    if saturation != 1.0:
        hs = N.new("CompositorNodeHueSat")
        hs.inputs["Saturation"].default_value = saturation
        L(cur, hs.inputs["Image"])
        cur = hs.outputs["Image"]
    if dispersion > 0:
        ld = N.new("CompositorNodeLensdist")
        ld.inputs["Dispersion"].default_value = dispersion
        ld.inputs["Distortion"].default_value = 0.0
        L(cur, ld.inputs["Image"])
        cur = ld.outputs["Image"]
    if vignette > 0:
        em = N.new("CompositorNodeEllipseMask")
        em.inputs["Size"].default_value = (0.82, 0.72)
        bl = N.new("CompositorNodeBlur")
        try:
            bl.inputs["Size"].default_value = (300, 300)
        except Exception:
            pass
        L(em.outputs["Mask"], bl.inputs["Image"])
        mr = N.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = 1.0 - vignette
        mr.inputs["To Max"].default_value = 1.0
        L(bl.outputs["Image"], mr.inputs["Value"])
        mul = N.new("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        L(cur, mul.inputs[6])
        L(mr.outputs[0], mul.inputs[7])
        cur = mul.outputs[2]
    if logo:
        im = bpy.data.images.load(logo, check_existing=True)
        imn = N.new("CompositorNodeImage")
        imn.image = im
        W, H = sc.render.resolution_x, sc.render.resolution_y
        cx, cy, wfrac = logo_box
        scl = (wfrac * W) / im.size[0]
        tr = N.new("CompositorNodeTransform")
        tr.inputs["Scale"].default_value = scl
        tr.inputs["X"].default_value = (cx - 0.5) * W
        tr.inputs["Y"].default_value = (cy - 0.5) * H
        tr.inputs["Interpolation"].default_value = "Bicubic"
        L(imn.outputs["Image"], tr.inputs["Image"])
        ao = N.new("CompositorNodeAlphaOver")
        ao.inputs["Straight Alpha"].default_value = True
        L(cur, ao.inputs["Background"])
        L(tr.outputs["Image"], ao.inputs["Foreground"])
        cur = ao.outputs["Image"]
    L(cur, out.inputs["Image"])
    return ng


def render(path_png=None, path_jpg=None, quality=88, rgba=False):
    sc = bpy.context.scene
    t0 = time.time()
    tmp = path_png or os.path.join(PREVIEWS, "_tmp.png")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if rgba else "RGB"
    sc.render.image_settings.color_depth = "8"
    sc.render.image_settings.compression = 90
    sc.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    log(f"rendered {tmp} in {time.time() - t0:.1f}s")
    if path_jpg:
        os.makedirs(os.path.dirname(path_jpg), exist_ok=True)
        r = bpy.data.images["Render Result"]
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.color_mode = "RGB"
        sc.render.image_settings.quality = quality
        r.save_render(path_jpg, scene=sc)
        log("saved", path_jpg)
    return time.time() - t0


def save_scene(name):
    os.makedirs(SCENES, exist_ok=True)
    p = os.path.join(SCENES, name + ".blend")
    # keep scene copies small: drop the hidden asset library meshes nobody instances and unused data
    bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    bpy.context.preferences.filepaths.save_version = 0  # no .blend1 backups
    bpy.ops.wm.save_as_mainfile(filepath=p, compress=True, copy=True)
    log("saved scene", p)


def args():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


# ============================================================================================ world / lights
def world_gradient(top, horizon, bottom, strength=1.0, glow=None, glow_dir=(0, 1, 0.2), glow_size=0.25, glow_strength=2.0):
    """Procedural night/interior sky: vertical gradient + optional soft glow lobe (moon / distant Core)."""
    w = bpy.data.worlds.new("Sky")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    N, L = nt.nodes, nt.links.new
    out = N.new("ShaderNodeOutputWorld")
    bg = N.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L(tc.outputs["Generated"], sep.inputs[0])
    ramp = N.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.40, (*bottom, 1)
    els[1].position, els[1].color = 0.505, (*horizon, 1)
    e = els.new(0.75)
    e.color = (*top, 1)
    mr = N.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -1
    mr.inputs["From Max"].default_value = 1
    L(sep.outputs[2], mr.inputs["Value"])
    L(mr.outputs[0], ramp.inputs["Fac"])
    col = ramp.outputs["Color"]
    if glow:
        nrm = N.new("ShaderNodeVectorMath")
        nrm.operation = "NORMALIZE"
        L(tc.outputs["Generated"], nrm.inputs[0])
        dot = N.new("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        L(nrm.outputs[0], dot.inputs[0])
        dot.inputs[1].default_value = Vector(glow_dir).normalized()
        mr2 = N.new("ShaderNodeMapRange")
        mr2.inputs["From Min"].default_value = 1 - glow_size
        mr2.inputs["From Max"].default_value = 1.0
        mr2.interpolation_type = "SMOOTHERSTEP"
        L(dot.outputs["Value"], mr2.inputs["Value"])
        mix = N.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "ADD"
        L(mr2.outputs[0], mix.inputs["Factor"])
        L(col, mix.inputs[6])
        mix.inputs[7].default_value = (glow[0] * glow_strength, glow[1] * glow_strength, glow[2] * glow_strength, 1)
        col = mix.outputs[2]
    L(col, bg.inputs["Color"])
    L(bg.outputs[0], out.inputs["Surface"])
    return w


def world_volume(density=0.01, color=(0.6, 0.7, 0.8), anisotropy=0.3):
    w = bpy.context.scene.world
    nt = w.node_tree
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = density
    vol.inputs["Color"].default_value = (*color, 1)
    vol.inputs["Anisotropy"].default_value = anisotropy
    out = [n for n in nt.nodes if n.type == "OUTPUT_WORLD"][0]
    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    return vol


def fog_box(center, size, density=0.02, color=(0.7, 0.78, 0.85), anisotropy=0.35, noise=0.0, noise_scale=0.08,
            falloff_z=None, name="Fog"):
    """Bounded volumetric fog (cheaper and more controllable than a world volume). falloff_z=(z0, z1): density
    fades from full at z0 to zero at z1 (ground mist)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = center
    link(ob)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N, L = nt.nodes, nt.links.new
    out = N.new("ShaderNodeOutputMaterial")
    vol = N.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (*color, 1)
    vol.inputs["Anisotropy"].default_value = anisotropy
    dens = density
    fac = None
    if noise > 0 or falloff_z:
        tc = N.new("ShaderNodeNewGeometry")
        fac = None
        if noise > 0:
            nz = N.new("ShaderNodeTexNoise")
            nz.inputs["Scale"].default_value = noise_scale
            nz.inputs["Detail"].default_value = 3
            L(tc.outputs["Position"], nz.inputs["Vector"])
            mr = N.new("ShaderNodeMapRange")
            mr.inputs["From Min"].default_value = 0.35
            mr.inputs["From Max"].default_value = 0.7
            mr.inputs["To Min"].default_value = 1 - noise
            mr.inputs["To Max"].default_value = 1.0
            L(nz.outputs["Fac"], mr.inputs["Value"])
            fac = mr.outputs[0]
        if falloff_z:
            sep = N.new("ShaderNodeSeparateXYZ")
            L(tc.outputs["Position"], sep.inputs[0])
            mr2 = N.new("ShaderNodeMapRange")
            mr2.inputs["From Min"].default_value = falloff_z[0]
            mr2.inputs["From Max"].default_value = falloff_z[1]
            mr2.inputs["To Min"].default_value = 1.0
            mr2.inputs["To Max"].default_value = 0.0
            mr2.interpolation_type = "SMOOTHSTEP"
            L(sep.outputs[2], mr2.inputs["Value"])
            if fac is None:
                fac = mr2.outputs[0]
            else:
                mm = N.new("ShaderNodeMath")
                mm.operation = "MULTIPLY"
                L(fac, mm.inputs[0])
                L(mr2.outputs[0], mm.inputs[1])
                fac = mm.outputs[0]
        md = N.new("ShaderNodeMath")
        md.operation = "MULTIPLY"
        md.inputs[1].default_value = density
        L(fac, md.inputs[0])
        L(md.outputs[0], vol.inputs["Density"])
    else:
        vol.inputs["Density"].default_value = dens
    L(vol.outputs[0], out.inputs["Volume"])
    me.materials.append(m)
    ob.visible_shadow = True
    return ob


def light(kind, loc, energy, color=(1, 1, 1), size=0.1, rot=None, target=None, spot=45.0, blend=0.3, name=None,
          shadow=True, diffuse=1.0, specular=1.0, volume=1.0, shape=None, size_y=None):
    ld = bpy.data.lights.new(name or kind, kind)
    ld.energy = energy
    ld.color = color
    ld.use_shadow = shadow
    try:
        ld.diffuse_factor = diffuse
        ld.specular_factor = specular
        ld.volume_factor = volume
    except Exception:
        pass
    if kind in ("POINT", "SPOT"):
        ld.shadow_soft_size = size
    if kind == "SPOT":
        ld.spot_size = math.radians(spot)
        ld.spot_blend = blend
    if kind == "AREA":
        if shape:
            ld.shape = shape
        ld.size = size
        if size_y is not None:
            ld.size_y = size_y
    if kind == "SUN":
        ld.angle = math.radians(size)
    ob = bpy.data.objects.new(name or kind, ld)
    ob.location = loc
    link(ob)
    if rot is not None:
        ob.rotation_euler = [math.radians(a) for a in rot]
    if target is not None:
        look_at(ob, target)
    return ob


# ============================================================================================ kit materials (Cycles)
def baked_state():
    global _STATE
    if _STATE is None:
        _STATE = json.load(open(os.path.join(ENV_DIR, "out", "materials_baked.json")))
    return _STATE


def manifest():
    global _MANIFEST
    if _MANIFEST is None:
        m = json.load(open(os.path.join(UNITY_ENV, "manifest.json")))
        _MANIFEST = {a["name"]: a for a in m["assets"]}
    return _MANIFEST


def anchor(name, key="light", index=0):
    """Manifest anchor (Unity local) -> Blender local offset of a kit asset."""
    a = manifest()[name][key]
    if isinstance(a, list) and a and isinstance(a[0], (list, dict)):
        a = a[index]
    if isinstance(a, dict):
        a = a.get("center") or a.get("pos") or a.get("position")
    return Vector(unity_to_blender(a))


def _img(path, noncolor=False):
    full = path if os.path.isabs(path) else os.path.join(UNITY_ENV, path)
    im = bpy.data.images.load(full, check_existing=True)
    if noncolor:
        im.colorspace_settings.name = "Non-Color"
        im.alpha_mode = "CHANNEL_PACKED"
    return im


def _tile_of(name):
    d = matdefs.REGISTRY[name]
    if d["kind"] == "tint":
        d = matdefs.REGISTRY[d["parent"]]
    return d.get("tile", 1.0), d.get("uv", "world")


class NT:
    """Small helper around a node tree."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.N = self.nt.nodes
        self.out = self.N.new("ShaderNodeOutputMaterial")

    def n(self, t, **inputs):
        node = self.N.new(t)
        for k, v in inputs.items():
            self.set(node.inputs[k], v)
        return node

    def L(self, a, b):
        self.nt.links.new(a, b)

    def set(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.nt.links.new(v, sock)
        elif isinstance(v, (tuple, list)) and len(v) == 3 and sock.type == "RGBA":
            sock.default_value = (*v, 1.0)
        else:
            sock.default_value = v

    def math(self, op, a, b=None, clamp=False):
        m = self.N.new("ShaderNodeMath")
        m.operation = op
        m.use_clamp = clamp
        self.set(m.inputs[0], a)
        if b is not None:
            self.set(m.inputs[1], b)
        return m.outputs[0]

    def mix(self, a, b, fac, blend="MIX"):
        m = self.N.new("ShaderNodeMix")
        m.data_type = "RGBA"
        m.blend_type = blend
        self.set(m.inputs["Factor"], fac)
        self.set(m.inputs[6], a)
        self.set(m.inputs[7], b)
        return m.outputs[2]

    def mixf(self, a, b, fac):
        m = self.N.new("ShaderNodeMix")
        m.data_type = "FLOAT"
        self.set(m.inputs["Factor"], fac)
        self.set(m.inputs[2], a)
        self.set(m.inputs[3], b)
        return m.outputs[0]

    def maprange(self, x, a, b, c=0.0, d=1.0, smooth=False):
        m = self.N.new("ShaderNodeMapRange")
        if smooth:
            m.interpolation_type = "SMOOTHSTEP"
        self.set(m.inputs["Value"], x)
        m.inputs["From Min"].default_value = a
        m.inputs["From Max"].default_value = b
        m.inputs["To Min"].default_value = c
        m.inputs["To Max"].default_value = d
        return m.outputs[0]


def _wetness(T, bsdf, base_sock, rough_sock, normal_sock, height_sock=None, amount=1.0, puddles=True):
    """Rain wetness on up-facing surfaces: darker albedo, low roughness, standing water in low spots."""
    geo = T.n("ShaderNodeNewGeometry")
    sep = T.n("ShaderNodeSeparateXYZ")
    T.L(geo.outputs["Normal"], sep.inputs[0])
    up = T.maprange(sep.outputs[2], 0.55, 0.92, 0.0, 1.0, smooth=True)
    side = T.maprange(sep.outputs[2], -0.2, 0.55, 0.35, 0.0, smooth=True)  # vertical faces: damp streaks
    damp = T.math("MULTIPLY", T.math("MAXIMUM", up, side), amount)
    pud = None
    if puddles:
        nz = T.n("ShaderNodeTexNoise", Scale=0.55, Detail=4.0, Roughness=0.55)
        T.L(geo.outputs["Position"], nz.inputs["Vector"])
        pv = nz.outputs["Fac"]
        if height_sock is not None:
            pv = T.math("ADD", pv, T.math("MULTIPLY", T.math("SUBTRACT", 0.5, height_sock), 0.35))
        pud = T.math("MULTIPLY", T.maprange(pv, 0.50, 0.56, 0.0, 1.0, smooth=True), T.math("MULTIPLY", up, amount))
    # albedo
    dark = T.mix(base_sock, T.mix(base_sock, (0, 0, 0), 0.45), damp)
    if pud is not None:
        dark = T.mix(dark, T.mix(base_sock, (0, 0, 0), 0.72), pud)
    T.L(dark, bsdf.inputs["Base Color"])
    r = T.mixf(rough_sock, T.math("MULTIPLY", rough_sock, 0.38), damp)
    if pud is not None:
        r = T.mixf(r, 0.03, pud)
    T.L(r, bsdf.inputs["Roughness"])
    if normal_sock is not None:
        if pud is not None:
            vm = T.N.new("ShaderNodeMix")
            vm.data_type = "VECTOR"
            T.L(pud, vm.inputs["Factor"])
            T.L(normal_sock, vm.inputs[4])
            T.L(geo.outputs["Normal"], vm.inputs[5])
            # small rain ripples on the puddles
            vn = T.n("ShaderNodeTexVoronoi", Scale=9.0)
            T.L(geo.outputs["Position"], vn.inputs["Vector"])
            bump = T.n("ShaderNodeBump", Strength=0.08, Distance=0.002)
            T.L(T.math("SINE", T.math("MULTIPLY", vn.outputs["Distance"], 40.0)), bump.inputs["Height"])
            T.L(vm.outputs[1], bump.inputs["Normal"])
            nmix = T.N.new("ShaderNodeMix")
            nmix.data_type = "VECTOR"
            T.L(pud, nmix.inputs["Factor"])
            T.L(vm.outputs[1], nmix.inputs[4])
            T.L(bump.outputs["Normal"], nmix.inputs[5])
            T.L(nmix.outputs[1], bsdf.inputs["Normal"])
        else:
            T.L(normal_sock, bsdf.inputs["Normal"])


def aether_material(name="aether_art", color=CYAN, color2=VIOLET, strength=6.0, alpha=0.0, rim=2.0, scale=2.5,
                    core=False):
    """Aether energy: additive glow (transparent + emission), fresnel rim, slow cyan/violet flow noise."""
    m = bpy.data.materials.new(name)
    T = NT(m)
    geo = T.n("ShaderNodeNewGeometry")
    lw = T.n("ShaderNodeLayerWeight", Blend=0.45)
    fres = lw.outputs["Facing"]
    tc = T.n("ShaderNodeTexCoord")
    nz = T.n("ShaderNodeTexNoise", Scale=scale, Detail=6.0, Roughness=0.6, Distortion=1.2)
    T.L(tc.outputs["Object"], nz.inputs["Vector"])
    hue = T.maprange(nz.outputs["Fac"], 0.42, 0.68, 0.0, 1.0, smooth=True)
    col = T.mix(color, color2, T.math("MULTIPLY", hue, 0.6))
    vein = T.maprange(nz.outputs["Fac"], 0.48, 0.52, 0.0, 1.0)
    k = T.math("ADD", T.math("ADD", 0.35 if not core else 1.0, T.math("MULTIPLY", T.math("POWER", fres, 1.6), rim)),
               T.math("MULTIPLY", vein, 0.25))
    em = T.n("ShaderNodeEmission")
    T.L(col, em.inputs["Color"])
    T.L(T.math("MULTIPLY", k, strength), em.inputs["Strength"])
    tr = T.n("ShaderNodeBsdfTransparent")
    add = T.n("ShaderNodeAddShader")
    T.L(tr.outputs[0], add.inputs[0])
    T.L(em.outputs[0], add.inputs[1])
    final = add.outputs[0]
    if alpha > 0:
        gl = T.n("ShaderNodeBsdfGlossy", Roughness=0.05)
        mx = T.n("ShaderNodeMixShader")
        mx.inputs["Fac"].default_value = alpha
        T.L(final, mx.inputs[1])
        T.L(gl.outputs[0], mx.inputs[2])
        final = mx.outputs[0]
    T.L(final, T.out.inputs["Surface"])
    return m


def emissive(name, color, strength, base=None):
    m = bpy.data.materials.new(name)
    T = NT(m)
    b = T.n("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*(base or [c * 0.2 for c in color]), 1)
    b.inputs["Emission Color"].default_value = (*color, 1)
    b.inputs["Emission Strength"].default_value = strength
    b.inputs["Roughness"].default_value = 0.4
    T.L(b.outputs[0], T.out.inputs["Surface"])
    return m


def principled(name, color, rough=0.5, metal=0.0, **kw):
    m = bpy.data.materials.new(name)
    T = NT(m)
    b = T.n("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    for k, v in kw.items():
        b.inputs[k].default_value = v
    T.L(b.outputs[0], T.out.inputs["Surface"])
    return m


def env_material(name):
    """Cycles version of the kit material `name` (baked PNGs from the env pipeline, URP-equivalent mapping)."""
    key = (name, WET, EMIT_SCALE)
    if key in _MATS:
        return _MATS[key]
    kd, kdir = kit_matdef(name)
    if kd is not None and name not in ("aether_energy",):
        m = _kit_material(name, kd, kdir)
        _MATS[key] = m
        return m
    d = matdefs.REGISTRY[name]
    m = bpy.data.materials.new(f"{name}__art")
    _MATS[key] = m
    if name == "aether_energy":
        m2 = aether_material(f"{name}__aether", strength=4.0 * EMIT_SCALE)
        _MATS[key] = m2
        bpy.data.materials.remove(m)
        return m2
    T = NT(m)
    b = T.n("ShaderNodeBsdfPrincipled")
    T.L(b.outputs[0], T.out.inputs["Surface"])
    if d["kind"] == "param":
        u = d["unity"]
        c = u.get("baseColor", [0.5, 0.5, 0.5, 1.0])
        b.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
        b.inputs["Metallic"].default_value = u.get("metallic", 0.0)
        b.inputs["Roughness"].default_value = 1.0 - u.get("smoothness", 0.5)
        if "emission" in u and u.get("emissionIntensity", 0) > 0:
            e = u["emission"]
            b.inputs["Emission Color"].default_value = (e[0], e[1], e[2], 1.0)
            b.inputs["Emission Strength"].default_value = u["emissionIntensity"] * 1.6 * EMIT_SCALE
        if name == "glass":
            # thin window glass: fresnel mix of a slightly tinted transparent and a sharp reflection
            T.nt.nodes.remove(b)
            tr = T.n("ShaderNodeBsdfTransparent")
            tr.inputs["Color"].default_value = (0.78, 0.86, 0.9, 1)
            gl = T.n("ShaderNodeBsdfGlossy", Roughness=0.04)
            fr = T.n("ShaderNodeFresnel", IOR=1.5)
            mx = T.n("ShaderNodeMixShader")
            fac = T.math("ADD", fr.outputs[0], 0.06)
            T.L(fac, mx.inputs["Fac"])
            T.L(tr.outputs[0], mx.inputs[1])
            T.L(gl.outputs[0], mx.inputs[2])
            T.L(mx.outputs[0], T.out.inputs["Surface"])
        elif name == "water":
            b.inputs["Roughness"].default_value = 0.02
            b.inputs["Base Color"].default_value = (0.01, 0.018, 0.022, 1)
            tc = T.n("ShaderNodeNewGeometry")
            vn = T.n("ShaderNodeTexVoronoi", Scale=6.0)
            T.L(tc.outputs["Position"], vn.inputs["Vector"])
            bump = T.n("ShaderNodeBump", Strength=0.12, Distance=0.003)
            T.L(T.math("SINE", T.math("MULTIPLY", vn.outputs["Distance"], 35.0)), bump.inputs["Height"])
            T.L(bump.outputs["Normal"], b.inputs["Normal"])
        elif name in ("glass_dark",):
            b.inputs["Roughness"].default_value = 0.06
        return m
    st = baked_state().get(name)
    if not st:
        c = matdefs.preview_color(name)
        b.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
        return m
    tex = st["textures"]
    tile, uvmode = _tile_of(name)
    uv = T.n("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    mp = T.n("ShaderNodeMapping")
    if str(uvmode).startswith("world"):
        mp.inputs["Scale"].default_value = (1 / tile, 1 / tile, 1)
    elif uvmode == "strip":
        mp.inputs["Scale"].default_value = (1 / tile, 1, 1)
    T.L(uv.outputs[0], mp.inputs["Vector"])
    vec = mp.outputs[0]
    bc = T.n("ShaderNodeTexImage")
    bc.image = _img(tex["BaseColor"])
    T.L(vec, bc.inputs[0])
    mk = T.n("ShaderNodeTexImage")
    mk.image = _img(tex["MaskMap"], True)
    T.L(vec, mk.inputs[0])
    sep = T.n("ShaderNodeSeparateColor")
    T.L(mk.outputs["Color"], sep.inputs[0])
    T.L(sep.outputs[0], b.inputs["Metallic"])
    rough = T.math("SUBTRACT", 1.0, mk.outputs["Alpha"])
    ao = T.mix((1, 1, 1), sep.outputs[1], 0.0)  # placeholder replaced below
    aoc = T.n("ShaderNodeCombineColor")
    for k in range(3):
        T.L(sep.outputs[1], aoc.inputs[k])
    base = T.mix(bc.outputs["Color"], aoc.outputs[0], 0.7, blend="MULTIPLY")
    nm = T.n("ShaderNodeTexImage")
    nm.image = _img(tex["Normal"], True)
    T.L(vec, nm.inputs[0])
    nmap = T.n("ShaderNodeNormalMap", Strength=1.0)
    nmap.uv_map = "UVMap"
    T.L(nm.outputs["Color"], nmap.inputs["Color"])
    outdoor_wet = WET > 0 and name not in ("screen", "window_lit_warm", "window_lit_cool") and not name.startswith("emit_")
    if outdoor_wet:
        _wetness(T, b, base, rough, nmap.outputs[0], sep.outputs[2], amount=WET,
                 puddles=name in ("concrete", "concrete_wet", "concrete_dark", "asphalt", "paving", "gravel", "metal_plate"))
    else:
        T.L(base, b.inputs["Base Color"])
        T.L(rough, b.inputs["Roughness"])
        T.L(nmap.outputs[0], b.inputs["Normal"])
    if "Emission" in tex:
        em = T.n("ShaderNodeTexImage")
        em.image = _img(tex["Emission"])
        T.L(vec, em.inputs[0])
        T.L(em.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = d["unity"].get("emissionIntensity", 1.0) * 1.6 * EMIT_SCALE
    if d.get("unity", {}).get("alphaClip"):
        T.L(T.math("GREATER_THAN", bc.outputs["Alpha"], 0.5), b.inputs["Alpha"])
    return m


KITS = {
    "env": UNITY_ENV,
    "landmarks": os.path.join(ASSETS, "Art", "CityLandmarks"),
    "street": os.path.join(ASSETS, "Art", "CityStreet"),
}
_KITMAN = {}


def _kitman(k):
    if k not in _KITMAN:
        p = os.path.join(KITS[k], "manifest.json")
        _KITMAN[k] = json.load(open(p)) if os.path.exists(p) else {"assets": [], "materials": {}}
        _KITMAN[k]["_assets"] = {a["name"]: a for a in _KITMAN[k]["assets"]}
    return _KITMAN[k]


def kit_record(name):
    """Asset record + kit folder from the environment, city-landmark or city-street kit manifests."""
    for k in ("env", "landmarks", "street"):
        a = _kitman(k)["_assets"].get(name)
        if a:
            return a, KITS[k]
    raise KeyError(name)


def kit_matdef(name):
    for k in ("street", "landmarks", "env"):
        d = _kitman(k).get("materials", {}).get(name)
        if d:
            return d, KITS[k]
    return None, None


def _kit_material(name, d, kdir):
    """Cycles material from a kit manifest entry (URP Lit mapping: BaseColor, Normal (OpenGL), MaskMap R metal,
    G AO, A smoothness, Emission x emissionIntensity, tiling), plus the rain wetness layer when WET > 0."""
    m = bpy.data.materials.new(f"{name}__kit")
    T = NT(m)
    b = T.n("ShaderNodeBsdfPrincipled")
    T.L(b.outputs[0], T.out.inputs["Surface"])
    em_gain = 1.6 * EMIT_SCALE
    if d.get("kind") == "param" or not d.get("textures"):
        c = d.get("baseColor", [0.5, 0.5, 0.5, 1.0])
        b.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
        b.inputs["Metallic"].default_value = d.get("metallic", 0.0)
        b.inputs["Roughness"].default_value = 1.0 - d.get("smoothness", 0.5)
        if d.get("emission") and d.get("emissionIntensity", 0) > 0:
            e = d["emission"]
            b.inputs["Emission Color"].default_value = (e[0], e[1], e[2], 1.0)
            b.inputs["Emission Strength"].default_value = d["emissionIntensity"] * em_gain
        if name.startswith("glass") and d.get("surface") == "Transparent":
            T.nt.nodes.remove(b)
            tr = T.n("ShaderNodeBsdfTransparent")
            tr.inputs["Color"].default_value = (0.78, 0.86, 0.9, 1)
            gl = T.n("ShaderNodeBsdfGlossy", Roughness=0.04)
            fr = T.n("ShaderNodeFresnel", IOR=1.5)
            mx = T.n("ShaderNodeMixShader")
            T.L(T.math("ADD", fr.outputs[0], 0.06), mx.inputs["Fac"])
            T.L(tr.outputs[0], mx.inputs[1])
            T.L(gl.outputs[0], mx.inputs[2])
            T.L(mx.outputs[0], T.out.inputs["Surface"])
        elif d.get("surface") == "Transparent":
            b.inputs["Alpha"].default_value = max(0.2, c[3] if len(c) > 3 else 0.5)
        return m
    tex = d["textures"]
    uv = T.n("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    mp = T.n("ShaderNodeMapping")
    tl = d.get("tiling") or [1, 1]
    mp.inputs["Scale"].default_value = (tl[0], tl[1], 1)
    T.L(uv.outputs[0], mp.inputs["Vector"])
    vec = mp.outputs[0]

    def img(k, nonc):
        if k not in tex:
            return None
        p = os.path.join(kdir, tex[k])
        if not os.path.exists(p):
            return None
        t = T.n("ShaderNodeTexImage")
        t.image = _img(p, nonc)
        T.L(vec, t.inputs[0])
        return t
    bc = img("BaseColor", False)
    mk = img("MaskMap", True)
    nm = img("Normal", True)
    base = bc.outputs["Color"] if bc else (0.4, 0.4, 0.4)
    rough = 0.5
    height = None
    if mk is not None:
        sep = T.n("ShaderNodeSeparateColor")
        T.L(mk.outputs["Color"], sep.inputs[0])
        T.L(sep.outputs[0], b.inputs["Metallic"])
        rough = T.math("SUBTRACT", 1.0, mk.outputs["Alpha"])
        height = sep.outputs[2]
        if bc is not None:
            aoc = T.n("ShaderNodeCombineColor")
            for k in range(3):
                T.L(sep.outputs[1], aoc.inputs[k])
            base = T.mix(bc.outputs["Color"], aoc.outputs[0], 0.7, blend="MULTIPLY")
    nrm = None
    if nm is not None:
        nmap = T.n("ShaderNodeNormalMap", Strength=d.get("normalScale", 1.0))
        nmap.uv_map = "UVMap"
        T.L(nm.outputs["Color"], nmap.inputs["Color"])
        nrm = nmap.outputs[0]
    emissive = "Emission" in tex
    if WET > 0 and not emissive and d.get("uvMode") != "fit":
        _wetness(T, b, base, rough if not isinstance(rough, float) else T.math("ADD", rough, 0.0), nrm, height, amount=WET,
                 puddles=any(k in name for k in ("asphalt", "concrete", "paving", "pavers", "slab", "gutter", "plaza", "gravel")))
    else:
        T.set(b.inputs["Base Color"], base)
        T.set(b.inputs["Roughness"], rough)
        if nrm is not None:
            T.L(nrm, b.inputs["Normal"])
    if emissive:
        em = img("Emission", False)
        if em is not None:
            ec = d.get("emissionColor") or [1, 1, 1]
            T.L(T.mix(em.outputs["Color"], tuple(ec[:3]), 1.0, blend="MULTIPLY"), b.inputs["Emission Color"])
            b.inputs["Emission Strength"].default_value = d.get("emissionIntensity", 1.0) * em_gain
    if d.get("alphaClip") or (d.get("unity", {}) or {}).get("alphaClip"):
        if bc is not None:
            T.L(T.math("GREATER_THAN", bc.outputs["Alpha"], 0.5), b.inputs["Alpha"])
    return m


def world_pano(path=None, strength=1.0, rot_deg=0.0):
    """Equirectangular sky (the FX storm panorama by default) as the world background + light."""
    path = path or os.path.join(ROOT, "blender", "fx", "out", "sky_pano_color_final_4096.exr")
    w = bpy.data.worlds.new("Pano")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    N, L = nt.nodes, nt.links.new
    out = N.new("ShaderNodeOutputWorld")
    bg = N.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    tc = N.new("ShaderNodeTexCoord")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(rot_deg))
    L(tc.outputs["Generated"], mp.inputs["Vector"])
    env = N.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(path, check_existing=True)
    L(mp.outputs[0], env.inputs["Vector"])
    L(env.outputs["Color"], bg.inputs["Color"])
    L(bg.outputs[0], out.inputs["Surface"])
    return w


def set_emit(name, strength=None, color=None):
    """Adjust an already-built kit material's emission (e.g. dead/powered lights)."""
    m = env_material(name)
    for n in m.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            if strength is not None:
                n.inputs["Emission Strength"].default_value = strength
            if color is not None:
                n.inputs["Emission Color"].default_value = (*color, 1)
    return m


# ============================================================================================ kit assets
def _lib_coll():
    c = bpy.data.collections.get("_kitlib")
    if c is None:
        c = bpy.data.collections.new("_kitlib")
        bpy.context.scene.collection.children.link(c)
        bpy.context.view_layer.layer_collection.children["_kitlib"].exclude = True
    return c


def asset(name):
    """Import <name>.fbx (LOD0 only) once; returns the library mesh object (in an excluded collection)."""
    if name in _LIB:
        return _LIB[name]
    rec, kitdir = kit_record(name)
    path = os.path.join(kitdir, rec["file"])
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, axis_forward="-Z", axis_up="Y", use_custom_normals=True, bake_space_transform=True)
    new = [o for o in bpy.data.objects if o not in before]
    lod0 = None
    for o in new:
        if o.type == "MESH" and o.name.startswith(name + "_LOD0"):
            lod0 = o
    for o in new:
        if o is not lod0:
            bpy.data.objects.remove(o, do_unlink=True)
    for i, ms in enumerate(lod0.data.materials):
        if ms is None:
            continue
        base = ms.name.split(".")[0]
        if base in matdefs.REGISTRY or kit_matdef(base)[0] is not None:
            lod0.data.materials[i] = env_material(base)
    for c in list(lod0.users_collection):
        c.objects.unlink(lod0)
    _lib_coll().objects.link(lod0)
    lod0.name = f"lib_{name}"
    _LIB[name] = lod0
    return lod0


def place(name, loc=(0, 0, 0), rot=0.0, scale=1.0, collection=None, mats=None):
    """Instance a kit asset. rot: Z degrees, or (x, y, z) degrees. mats: {slot_material_name: Material} overrides."""
    src = asset(name)
    ob = bpy.data.objects.new(name, src.data)
    link(ob, collection)
    ob.location = loc
    if isinstance(rot, (tuple, list)):
        ob.rotation_euler = [math.radians(a) for a in rot]
    else:
        ob.rotation_euler = (0, 0, math.radians(rot))
    ob.scale = (scale, scale, scale) if not isinstance(scale, (tuple, list)) else scale
    if mats:
        for i, slot in enumerate(ob.material_slots):
            mn = src.data.materials[i].name.split("__")[0] if src.data.materials[i] else None
            if mn in mats:
                slot.link = "OBJECT"
                slot.material = mats[mn]
    return ob


def yaw_to(src, dst, offset=0.0):
    """Z rotation (degrees) that turns a -Y-facing character/robot at src to face dst."""
    dx, dy = dst[0] - src[0], dst[1] - src[1]
    return math.degrees(math.atan2(dx, -dy)) + offset


def unity_to_blender(v):
    return (-v[0], -v[2], v[1])


def proto(x, y, z):
    """Prototype (three.js, Y up, +Z south) -> Blender."""
    return (x, -z, y)


def box(size, loc, mat, rot=0.0, name="box", bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    if bevel:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2, affect="EDGES")
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:  # world-metre box UVs (kit convention)
        nrm = f.normal
        ax = max(range(3), key=lambda i: abs(nrm[i]))
        for l in f.loops:
            co = l.vert.co
            u, v = [(co.y, co.z), (co.x, co.z), (co.x, co.y)][ax]
            l[uvl].uv = (u, v)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.rotation_euler = (0, 0, math.radians(rot)) if not isinstance(rot, (tuple, list)) else [math.radians(a) for a in rot]
    me.materials.append(mat if isinstance(mat, bpy.types.Material) else env_material(mat))
    for p in me.polygons:
        p.use_smooth = False
    link(ob)
    return ob


def plane(sx, sy, loc, mat, name="plane", rot=None):
    me = bpy.data.meshes.new(name)
    hx, hy = sx / 2, sy / 2
    me.from_pydata([(-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0)], [], [(0, 1, 2, 3)])
    uvl = me.uv_layers.new(name="UVMap")
    for i, l in enumerate(me.loops):
        co = me.vertices[l.vertex_index].co
        uvl.data[i].uv = (co.x + loc[0], co.y + loc[1])
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    if rot:
        ob.rotation_euler = [math.radians(a) for a in rot]
    me.materials.append(mat if isinstance(mat, bpy.types.Material) else env_material(mat))
    link(ob)
    return ob


def cylinder(r, h, loc, mat, n=32, name="cyl", r2=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=n, radius1=r, radius2=r if r2 is None else r2, depth=h)
    bmesh.ops.translate(bm, vec=(0, 0, h / 2), verts=bm.verts)
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for l in f.loops:
            co = l.vert.co
            if abs(f.normal.z) > 0.7:
                l[uvl].uv = (co.x, co.y)
            else:
                l[uvl].uv = (math.atan2(co.y, co.x) * r, co.z)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = abs(p.normal.z) < 0.7
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    me.materials.append(mat if isinstance(mat, bpy.types.Material) else env_material(mat))
    link(ob)
    return ob


# ============================================================================================ rain
def rain(center, size, count=30000, length=(0.35, 0.8), width=0.006, wind=(0.12, 0.05), cam=None, seed=7,
         brightness=0.35, name="Rain"):
    """Rain streaks: thin camera-facing quads (a long-exposure look). Lit by the scene (they flare near lights),
    plus a faint self-glow so they read against the dark sky."""
    rnd = random.Random(seed)
    camloc = cam.location if cam else Vector((0, -50, 2))
    me = bpy.data.meshes.new(name)
    verts, faces = [], []
    cx, cy, cz = center
    sx, sy, sz = size
    wdir = Vector((wind[0], wind[1], -1.0)).normalized()
    for i in range(count):
        p = Vector((cx + rnd.uniform(-sx / 2, sx / 2), cy + rnd.uniform(-sy / 2, sy / 2), cz + rnd.uniform(-sz / 2, sz / 2)))
        ln = rnd.uniform(*length)
        a = p - wdir * (ln / 2)
        b = p + wdir * (ln / 2)
        tocam = (camloc - p).normalized()
        side = wdir.cross(tocam).normalized() * (width * rnd.uniform(0.7, 1.3) / 2)
        k = len(verts)
        verts += [a - side, a + side, b + side, b - side]
        faces.append((k, k + 1, k + 2, k + 3))
    me.from_pydata([tuple(v) for v in verts], [], faces)
    uvl = me.uv_layers.new(name="UVMap")
    for f in me.polygons:
        for j, li in enumerate(f.loop_indices):
            uvl.data[li].uv = [(0, 0), (1, 0), (1, 1), (0, 1)][j]
    ob = bpy.data.objects.new(name, me)
    link(ob)
    m = bpy.data.materials.new(name)
    T = NT(m)
    tc = T.n("ShaderNodeTexCoord")
    sep = T.n("ShaderNodeSeparateXYZ")
    T.L(tc.outputs["UV"], sep.inputs[0])
    # soft along the length and across the width
    along = T.math("SINE", T.math("MULTIPLY", sep.outputs[1], math.pi))
    across = T.math("SINE", T.math("MULTIPLY", sep.outputs[0], math.pi))
    a = T.math("MULTIPLY", T.math("MULTIPLY", along, across), brightness)
    gl = T.n("ShaderNodeBsdfPrincipled", Roughness=0.15)
    gl.inputs["Base Color"].default_value = (0.8, 0.85, 0.9, 1)
    gl.inputs["Emission Color"].default_value = (0.55, 0.65, 0.8, 1)
    gl.inputs["Emission Strength"].default_value = 0.06
    tr = T.n("ShaderNodeBsdfTransparent")
    mx = T.n("ShaderNodeMixShader")
    T.L(a, mx.inputs["Fac"])
    T.L(tr.outputs[0], mx.inputs[1])
    T.L(gl.outputs[0], mx.inputs[2])
    T.L(mx.outputs[0], T.out.inputs["Surface"])
    me.materials.append(m)
    ob.visible_shadow = False
    ob.visible_diffuse = False
    ob.visible_glossy = True
    ob.visible_transmission = False
    ob.visible_volume_scatter = False
    return ob


def splashes(center, size, count=1500, z=0.0, seed=3, name="Splash"):
    """Tiny bright rain-impact crowns on the ground (only visible near lights)."""
    rnd = random.Random(seed)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for i in range(count):
        x = center[0] + rnd.uniform(-size[0] / 2, size[0] / 2)
        y = center[1] + rnd.uniform(-size[1] / 2, size[1] / 2)
        r = rnd.uniform(0.01, 0.025)
        h = rnd.uniform(0.02, 0.05)
        ret = bmesh.ops.create_cone(bm, cap_ends=False, segments=6, radius1=r, radius2=r * 2.2, depth=h)
        bmesh.ops.translate(bm, vec=(x, y, z + h / 2), verts=ret["verts"])
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    m = principled(name, (0.8, 0.85, 0.9), rough=0.1, Alpha=0.5)
    me.materials.append(m)
    ob.visible_shadow = False
    return ob


# ============================================================================================ characters
CHARS = {
    "kael": dict(gender="male", hair="short", hair_tint="#1d1714", outfit="kael_outfit.blend",
                 glow={"Glow": "#00e5ff", "Screen": "#00e5ff"}),
    "lyra": dict(gender="female", hair="ponytail", hair_tint="#2b1b14", outfit="lyra_outfit.blend",
                 glow={"Glow": "#ff2bd6", "Glow2": "#00e5ff"}),
    "oren": dict(gender="male", hair="default", hair_tint="#8d8a86", facial="wdg_scruffy_beard", facial_tint="#7a7570",
                 skin="middleage_caucasian_male"),
    "mira": dict(gender="female", hair="default", hair_tint="#1b1512", skin="young_asian_female"),
    "tomas": dict(gender="male", hair="default", skin="young_african_male"),
    "maren": dict(gender="female", hair="default", skin="middleage_caucasian_female", echo=(0.72, 0.42, 1.0)),
    "nia": dict(gender="female", hair="default", hair_tint="#2a1d16", skin="young_caucasian_female", echo=(0.3, 0.78, 1.0)),
}
GEAR_COLORS = {"Gear": ("#3a3f46", 0.3, 0.5), "Strap": ("#3b3530", 0.0, 0.6), "Scarf": ("#5a4a3a", 0.0, 0.9),
               "Belt": ("#3b3530", 0.0, 0.6), "Harness": ("#3b3530", 0.0, 0.6), "Metal": ("#8a8f96", 0.9, 0.32),
               "SuitSecondary": ("#202226", 0.0, 0.7), "Lens": ("#0a1a24", 0.0, 0.05)}


def _mhmat_diffuse(folder):
    d = os.path.join(MPFB_DATA, "skins", folder)
    for f in os.listdir(d):
        if f.endswith(".mhmat"):
            for line in open(os.path.join(d, f)):
                if line.startswith("diffuseTexture"):
                    return os.path.join(d, os.path.basename(line.split()[1]))
    return None


def _append(blend, names=None, kind="objects"):
    before = set(bpy.data.images)
    with bpy.data.libraries.load(blend, link=False) as (src, dst):
        pool = getattr(src, kind)
        setattr(dst, kind, [n for n in pool if names is None or n in names])
    # appended images can carry stale relative paths: rebase them, else find the file by name in the game's
    # character / customization texture folders
    base = os.path.dirname(blend)
    for im in bpy.data.images:
        if im in before or not im.filepath or im.packed_file:
            continue
        p = im.filepath
        cands = [os.path.normpath(os.path.join(base, p[2:]))] if p.startswith("//") else []
        cands.append(bpy.path.abspath(p))
        found = next((c for c in cands if os.path.exists(c)), None) or _tex_index().get(os.path.basename(p))
        if found:
            if found != p:
                im.filepath = found
                im.reload()
        else:
            log("missing texture", im.name, p)
    return getattr(dst, kind)


_TEXIDX = {}


def _tex_index():
    if not _TEXIDX:
        for root in (UNITY_CHARS, os.path.join(ASSETS, "Resources", "Characters")):
            for dp, dn, fn in os.walk(root):
                for f in fn:
                    if f.lower().endswith((".png", ".jpg", ".exr", ".tga")):
                        _TEXIDX.setdefault(f, os.path.join(dp, f))
    return _TEXIDX


def _char_tex(cname, f):
    return os.path.join(UNITY_CHARS, cname, "Textures", f)


def _tex_material(name, img_path, rough=0.6, alpha_clip=None, tint=None, normal=None, desat=False, spec=0.5, sss=0.0):
    m = bpy.data.materials.new(name)
    T = NT(m)
    b = T.n("ShaderNodeBsdfPrincipled", Roughness=rough)
    b.inputs["Specular IOR Level"].default_value = spec
    T.L(b.outputs[0], T.out.inputs["Surface"])
    if img_path and os.path.exists(img_path):
        tx = T.n("ShaderNodeTexImage")
        tx.image = bpy.data.images.load(img_path, check_existing=True)
        col = tx.outputs["Color"]
        if desat:
            hs = T.n("ShaderNodeHueSaturation", Saturation=0.0)
            T.L(col, hs.inputs["Color"])
            col = hs.outputs[0]
        if tint is not None:
            col = T.mix(col, tint, 1.0, blend="MULTIPLY")
        T.L(col, b.inputs["Base Color"])
        if alpha_clip is not None:
            T.L(T.math("GREATER_THAN", tx.outputs["Alpha"], alpha_clip), b.inputs["Alpha"])
    elif tint is not None:
        b.inputs["Base Color"].default_value = (*tint, 1)
    if normal and os.path.exists(normal):
        nt = T.n("ShaderNodeTexImage")
        nt.image = bpy.data.images.load(normal, check_existing=True)
        nt.image.colorspace_settings.name = "Non-Color"
        nm = T.n("ShaderNodeNormalMap", Strength=1.0)
        T.L(nt.outputs["Color"], nm.inputs["Color"])
        T.L(nm.outputs[0], b.inputs["Normal"])
    if sss:
        b.inputs["Subsurface Weight"].default_value = sss
    return m


def _hair_material(name, img_path, tint_hex, cname, normal=None):
    """Hair cards: the MPFB texture desaturated and tinted (as the game's CharacterModel does), alpha cut-out
    with a soft edge, anisotropic-ish sheen via low specular + rough coat."""
    m = bpy.data.materials.new(name)
    T = NT(m)
    b = T.n("ShaderNodeBsdfPrincipled", Roughness=0.55)
    b.inputs["Specular IOR Level"].default_value = 0.3
    b.inputs["Coat Weight"].default_value = 0.0
    b.inputs["Sheen Weight"].default_value = 0.35
    b.inputs["Sheen Roughness"].default_value = 0.4
    T.L(b.outputs[0], T.out.inputs["Surface"])
    tx = T.n("ShaderNodeTexImage")
    tx.image = bpy.data.images.load(img_path, check_existing=True)
    col = tx.outputs["Color"]
    if tint_hex:
        bw = T.n("ShaderNodeRGBToBW")
        T.L(col, bw.inputs[0])
        g = T.math("MULTIPLY", T.math("POWER", bw.outputs[0], 1.6), 4.0)
        cc = T.n("ShaderNodeCombineColor")
        tint = hexlin(tint_hex)
        for i in range(3):
            T.L(T.math("MULTIPLY", g, tint[i]), cc.inputs[i])
        col = cc.outputs[0]
    T.L(col, b.inputs["Base Color"])
    T.L(T.maprange(tx.outputs["Alpha"], 0.25, 0.6, 0.0, 1.0), b.inputs["Alpha"])
    return m


def _skin_from(template, diffuse, name):
    """Copy an MPFB skin material (group) and swap its diffuse texture."""
    m = template.copy()
    m.name = name
    for n in m.node_tree.nodes:
        if n.type == "GROUP":
            g = n.node_tree.copy()
            g.name = name + "_grp"
            n.node_tree = g
            for gn in g.nodes:
                if gn.type == "TEX_IMAGE" and gn.name == "DiffuseTexture" and diffuse:
                    gn.image = bpy.data.images.load(diffuse, check_existing=True)
    return m


_SKIN_TEMPLATES = {}


def _skin_template(gender):
    if gender in _SKIN_TEMPLATES:
        return _SKIN_TEMPLATES[gender]
    blend = os.path.join(CHAR_OUT, "kael_outfit.blend" if gender == "male" else "lyra_outfit.blend")
    nm = "Kael.body" if gender == "male" else "Lyra.body"
    mats = _append(blend, [nm], "materials")
    _SKIN_TEMPLATES[gender] = mats[0]
    mats[0].name = f"_skin_template_{gender}"
    return mats[0]


def _eye_material(name, img):
    m = bpy.data.materials.new(name)
    T = NT(m)
    b = T.n("ShaderNodeBsdfPrincipled", Roughness=0.35)
    b.inputs["Coat Weight"].default_value = 1.0
    b.inputs["Coat Roughness"].default_value = 0.02
    b.inputs["Specular IOR Level"].default_value = 0.6
    tx = T.n("ShaderNodeTexImage")
    tx.image = bpy.data.images.load(img, check_existing=True)
    T.L(tx.outputs["Color"], b.inputs["Base Color"])
    T.L(tx.outputs["Alpha"], b.inputs["Alpha"])
    T.L(b.outputs[0], T.out.inputs["Surface"])
    return m


def _echo_wrap(mat, tint, strength=1.0):
    """Turn a character material into an Aether 'echo' hologram: mostly transparent, a quarter of the original
    shading kept (so faces stay readable), tinted emission with fresnel rim and fine scanlines."""
    nt = mat.node_tree
    out = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"][0]
    if not out.inputs["Surface"].is_linked:
        return mat
    src = out.inputs["Surface"].links[0].from_socket
    N, L = nt.nodes, nt.links.new
    lw = N.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    pw = N.new("ShaderNodeMath")
    pw.operation = "POWER"
    L(lw.outputs["Facing"], pw.inputs[0])
    pw.inputs[1].default_value = 2.0
    mul = N.new("ShaderNodeMath")
    mul.operation = "MULTIPLY_ADD"
    L(pw.outputs[0], mul.inputs[0])
    mul.inputs[1].default_value = 2.2 * strength
    mul.inputs[2].default_value = 0.12 * strength
    geo = N.new("ShaderNodeNewGeometry")
    sep = N.new("ShaderNodeSeparateXYZ")
    L(geo.outputs["Position"], sep.inputs[0])
    sc = N.new("ShaderNodeMath")
    sc.operation = "MULTIPLY"
    L(sep.outputs[2], sc.inputs[0])
    sc.inputs[1].default_value = 900.0
    sn = N.new("ShaderNodeMath")
    sn.operation = "SINE"
    L(sc.outputs[0], sn.inputs[0])
    sm = N.new("ShaderNodeMapRange")
    sm.inputs["From Min"].default_value = -1
    sm.inputs["From Max"].default_value = 1
    sm.inputs["To Min"].default_value = 0.55
    sm.inputs["To Max"].default_value = 1.0
    L(sn.outputs[0], sm.inputs["Value"])
    k = N.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    L(mul.outputs[0], k.inputs[0])
    L(sm.outputs[0], k.inputs[1])
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*tint, 1)
    L(k.outputs[0], em.inputs["Strength"])
    tr = N.new("ShaderNodeBsdfTransparent")
    tr.inputs["Color"].default_value = (0.9, 0.92, 1.0, 1)
    mx = N.new("ShaderNodeMixShader")
    # shaded copy weight: fairly solid where the surface faces the camera (inner parts stay hidden, the face
    # reads), dissolving toward the silhouette where the glow takes over
    fw = N.new("ShaderNodeMapRange")
    fw.inputs["From Min"].default_value = 0.0
    fw.inputs["From Max"].default_value = 0.85
    fw.inputs["To Min"].default_value = 0.82
    fw.inputs["To Max"].default_value = 0.05
    L(lw.outputs["Facing"], fw.inputs["Value"])
    L(fw.outputs[0], mx.inputs["Fac"])
    L(tr.outputs[0], mx.inputs[1])
    L(src, mx.inputs[2])
    add = N.new("ShaderNodeAddShader")
    L(mx.outputs[0], add.inputs[0])
    L(em.outputs[0], add.inputs[1])
    L(add.outputs[0], out.inputs["Surface"])
    # tint the base colour feed of any principled toward the echo colour
    for n in list(nt.nodes):
        if n.type == "BSDF_PRINCIPLED":
            bc = n.inputs["Base Color"]
            if bc.is_linked:
                s = bc.links[0].from_socket
                mm = N.new("ShaderNodeMix")
                mm.data_type = "RGBA"
                mm.blend_type = "MULTIPLY"
                mm.inputs["Factor"].default_value = 0.85
                L(s, mm.inputs[6])
                mm.inputs[7].default_value = (*[min(1, c * 1.1) for c in tint], 1)
                L(mm.outputs[2], bc)
            else:
                c = bc.default_value
                bc.default_value = (c[0] * tint[0], c[1] * tint[1], c[2] * tint[2], 1)
        if n.type == "GROUP":
            for gn in n.node_tree.nodes:
                if gn.type == "BSDF_PRINCIPLED":
                    gn.inputs["Subsurface Weight"].default_value = 0.0
    return mat


def _hd_skin(cid, cname, man):
    """Skin of the HD character exports (blender/scripts/hero_hd.py convention): Skin_<tone> base colour, Skin_Normal
    (0.6), Skin_MaskMap (R metallic, A smoothness), light SSS, and the glowing tattoo map as emission."""
    tex = man.get("textures", {}).get("Skin") or ["Skin_medium.png", "Skin_Normal.png", "Skin_MaskMap.png"]
    m = bpy.data.materials.new(f"{cid}_skin_hd")
    T = NT(m)
    b = T.n("ShaderNodeBsdfPrincipled")
    T.L(b.outputs[0], T.out.inputs["Surface"])
    b.inputs["Subsurface Weight"].default_value = 0.12
    b.inputs["Subsurface Radius"].default_value = (0.9, 0.35, 0.2)
    b.inputs["Subsurface Scale"].default_value = 0.006
    b.inputs["Specular IOR Level"].default_value = 0.45

    def img(f, nonc):
        p = _char_tex(cname, f)
        if not os.path.exists(p):
            return None
        t = T.n("ShaderNodeTexImage")
        t.image = bpy.data.images.load(p, check_existing=True)
        if nonc:
            t.image.colorspace_settings.name = "Non-Color"
        return t
    bc = img(tex[0], False)
    if bc:
        T.L(bc.outputs["Color"], b.inputs["Base Color"])
    nm = img(man["skinMaps"].get("normal") or "Skin_Normal.png", True)
    if nm:
        n = T.n("ShaderNodeNormalMap", Strength=0.6)
        T.L(nm.outputs["Color"], n.inputs["Color"])
        T.L(n.outputs[0], b.inputs["Normal"])
    mk = img(man["skinMaps"].get("maskMap") or "Skin_MaskMap.png", True)
    if mk:
        sep = T.n("ShaderNodeSeparateColor")
        T.L(mk.outputs["Color"], sep.inputs[0])
        T.L(T.math("SUBTRACT", 1.0, mk.outputs["Alpha"]), b.inputs["Roughness"])
    else:
        b.inputs["Roughness"].default_value = 0.5
    tt = img("Skin_Tattoo.png", False)
    if tt:
        T.L(tt.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = 3.0
    return m


def _placeholder(mat):
    """True for the flat export placeholders (a bare Principled BSDF with no textures)."""
    if not mat.use_nodes or mat.node_tree is None:
        return True
    types = {n.type for n in mat.node_tree.nodes}
    return types <= {"BSDF_PRINCIPLED", "OUTPUT_MATERIAL"}


class Character:
    def __init__(self, cid, rig, objs, coll):
        self.cid, self.rig, self.objs, self.coll = cid, rig, objs, coll

    def mesh(self, name):
        for o in self.objs:
            if o.type == "MESH" and o.get("eoa_part") == name:
                return o
        return None

    def shapes(self, **vals):
        for o in self.objs:
            if o.type == "MESH" and o.data.shape_keys:
                kb = o.data.shape_keys.key_blocks
                for k, v in vals.items():
                    if k in kb:
                        kb[k].value = v

    def place(self, loc, yaw=0.0):
        self.rig.location = loc
        self.rig.rotation_euler = (0, 0, math.radians(yaw))

    def ground(self, z=0.0):
        """Shift the rig so the lowest point of the posed body/boots touches z."""
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        lo = 1e9
        for o in self.objs:
            if o.type == "MESH" and o.get("eoa_part") in ("Body", "Boots") and not o.hide_render:
                ev = o.evaluated_get(dg)
                mw = o.matrix_world
                for v in ev.data.vertices:
                    lo = min(lo, (mw @ v.co).z)
        if lo < 1e8:
            self.rig.location.z += z - lo
        bpy.context.view_layer.update()
        return lo

    def bone_world(self, bone, tail=False):
        pb = self.rig.pose.bones["mixamorig:" + bone]
        bpy.context.view_layer.update()
        return self.rig.matrix_world @ (pb.tail if tail else pb.head)


def load_character(cid, loc=(0, 0, 0), yaw=0.0, pose=("idle", 1), detail=True, hair=None, ground=True, look=True):
    """Append <cid>_export.blend, keep only the default hair/facial hair, rebuild Cycles materials (Kael/Lyra skin
    and garments from their outfit .blend; NPC skins from the MPFB skin texture of their phenotype), pose it."""
    if cid in HERO_APPEAR and look and USE_HEROES_V2:
        return load_hero(cid, loc, yaw, pose=pose, ground=ground)
    info = CHARS[cid]
    cname = cid.capitalize()
    blend = os.path.join(CHAR_OUT, f"{cid}_export.blend")
    objs = _append(blend)
    c = coll(f"char_{cid}_{len([k for k in bpy.data.collections if k.name.startswith('char_' + cid)])}")
    rig = None
    for o in objs:
        c.objects.link(o)
        if o.type == "ARMATURE":
            rig = o
    names_in_blend = {o.name.split(".")[0] for o in objs if o.type == "MESH"}
    man0 = json.load(open(os.path.join(UNITY_CHARS, cid.capitalize(), f"{cid.capitalize()}.manifest.json")))
    want = hair or man0.get("defaultHair") or info["hair"]
    if "Hair_" + want not in names_in_blend:
        want = info["hair"]
    keep_hair = "Hair_" + want
    keep_facial = "Facial_" + info["facial"] if info.get("facial") else None
    if cid not in ("kael", "lyra"):
        _m0 = json.load(open(os.path.join(UNITY_CHARS, cid.capitalize(), f"{cid.capitalize()}.manifest.json")))
        _fac = [m["name"] for m in _m0.get("meshes", []) if m.get("kind") == "facial"]
        if _fac:
            keep_facial = _fac[0]
    alive = []
    for o in objs:
        if o.type != "MESH":
            alive.append(o)
            continue
        part = o.name.split(".")[0]
        o["eoa_part"] = part
        if (part.startswith("Hair_") and part != keep_hair) or (part.startswith("Facial_") and part != keep_facial):
            bpy.data.objects.remove(o, do_unlink=True)
            continue
        if part == "Tongue" or (part == "Teeth" and not detail):
            o.hide_render = True
        alive.append(o)
    objs = alive
    man = json.load(open(os.path.join(UNITY_CHARS, cname, f"{cname}.manifest.json")))
    tex = man.get("textures", {})
    pal = man.get("palette", {})
    if pal.get("hair") and cid not in ("kael", "lyra"):
        info = dict(info, hair_tint=pal["hair"])
    if pal.get("glow") and not info.get("glow"):
        info = dict(info, glow={"Glow": pal["glow"], "Glow2": pal.get("glow2", pal["glow"]), "Screen": pal["glow"]})
    first = lambda k: _char_tex(cname, tex[k][0]) if k in tex and tex[k] else None  # noqa: E731
    hair_tint = info.get("hair_tint")
    outfit_mats = {}
    if info.get("outfit"):
        names = [f"{cname}.body", f"{cname}_Top", f"{cname}_Pants"]
        import re
        try:
            _om = _append(os.path.join(CHAR_OUT, info["outfit"]), names, "materials")
        except OSError:
            _om = []  # the HD exports carry their own garment materials
        for m in _om:
            base = re.sub(r"\.\d{3}$", "", m.name)
            outfit_mats[base.split(".", 1)[1] if base.startswith(cname + ".") else base.split("_")[-1]] = m
    mats = {}
    for o in objs:
        if o.type != "MESH":
            continue
        new = []
        for ms in o.data.materials:
            mn = ms.name.split(".")[0] if ms else ""
            if mn in mats:
                new.append(mats[mn])
                continue
            m = None
            if ms is not None and not _placeholder(ms) and mn not in ("Glow", "Glow2", "Screen"):
                # the character export now carries a real material (newest asset): use it as is
                m = ms
            elif mn == "Skin" and man.get("skinMaps"):
                m = _hd_skin(cid, cname, man)
            elif mn == "Skin":
                if "body" in outfit_mats:
                    m = outfit_mats["body"]
                else:
                    m = _skin_from(_skin_template(info["gender"]), _mhmat_diffuse(info["skin"]), f"{cid}_skin")
                for n in m.node_tree.nodes:
                    if n.type == "GROUP":
                        n.inputs["Roughness"].default_value = 0.5
                        n.inputs["SSS strength"].default_value = 0.35
            elif mn == "Garment_Top" and "Top" in outfit_mats:
                m = outfit_mats["Top"]
            elif mn == "Garment_Pants" and "Pants" in outfit_mats:
                m = outfit_mats["Pants"]
            elif mn.startswith("Hair_"):
                m = _hair_material(f"{cid}_{mn}", first(mn), hair_tint, cname)
            elif mn.startswith("Facial_"):
                m = _hair_material(f"{cid}_{mn}", first(mn), info.get("facial_tint", hair_tint), cname)
            elif mn in ("Brows", "Lashes"):
                tint = hexlin(hair_tint) if hair_tint else (0.03, 0.022, 0.018)
                m = _hair_material(f"{cid}_{mn}", first(mn), hair_tint or "#2a1d16", cname)
            elif mn == "Eyes":
                eb = _char_tex(cname, "Eye_brown.png")
                m = _eye_material(f"{cid}_eyes", eb if os.path.exists(eb) else first("Eyes"))
            elif mn in ("Teeth", "Tongue"):
                m = _tex_material(f"{cid}_{mn}", first(mn), rough=0.35, sss=0.1)
            elif mn == "Boots":
                files = tex.get("Boots", [])
                nrm = [f for f in files if "norm" in f.lower()]
                m = _tex_material(f"{cid}_boots", first("Boots"), rough=0.55, tint=(0.6, 0.6, 0.6),
                                  normal=_char_tex(cname, nrm[0]) if nrm else None)
            elif mn.startswith("Cloth_"):
                files = tex.get(mn, [])
                dif = [f for f in files if "norm" not in f.lower() and "_ao" not in f.lower() and "spec" not in f.lower()]
                nrm = [f for f in files if "norm" in f.lower()]
                m = _tex_material(f"{cid}_{mn}", _char_tex(cname, dif[0]) if dif else None, rough=0.82,
                                  normal=_char_tex(cname, nrm[0]) if nrm else None, spec=0.3)
            elif mn in GEAR_COLORS and ms is not None:
                h, met, rough = GEAR_COLORS[mn]
                m = principled(f"{cid}_{mn}", hexlin(h), rough=rough, metal=met)
            elif mn in ("Glow", "Glow2", "Screen") and ms is not None:
                m = ms
                gcol = info.get("glow", {}).get(mn)
                for n in m.node_tree.nodes:
                    if n.type == "BSDF_PRINCIPLED":
                        n.inputs["Emission Strength"].default_value = 4.0
                        if gcol:
                            gc = hexlin(gcol)
                            n.inputs["Emission Color"].default_value = (*gc, 1)
                            n.inputs["Base Color"].default_value = (*gc, 1)
            else:
                m = ms
            mats[mn] = m
            new.append(m)
        for i, m in enumerate(new):
            o.data.materials[i] = m
    if info.get("echo"):
        for k, m in list(mats.items()):
            if m is None:
                continue
            e = m.copy()
            e.name = f"{cid}_{k}_echo"
            for n in e.node_tree.nodes:
                if n.type == "GROUP":
                    n.node_tree = n.node_tree.copy()
            _echo_wrap(e, info["echo"])
            for o in objs:
                if o.type == "MESH":
                    for i, ms in enumerate(o.data.materials):
                        if ms == m:
                            o.data.materials[i] = e
        for o in objs:
            o.visible_shadow = False
            if o.type == "MESH" and o.get("eoa_part") in ("Teeth", "Tongue"):
                o.hide_render = True
    ch = Character(cid, rig, objs, c)
    if pose:
        apply_pose(ch, *pose)
    ch.place(loc, yaw)
    if pose and ground is not None:
        ch.ground(loc[2] if ground is True else ground)
    if look and cid in HERO_LOOK:
        dress_default(ch)
    return ch


# ---------------------------------------------------------------------------------------------- posing
_RT = {}


def _retarget():
    """blender/scripts/retarget.py: the code that baked the game's clips (blender/anim/clips.json) onto the MPFB
    mixamo rigs for Anim_Male/Anim_Female.fbx. Re-used here to pose any rig with a frame of any clip."""
    if not _RT:
        saved = sys.argv
        sys.argv = [saved[0]]
        if CHAR_SCRIPTS not in sys.path:
            sys.path.insert(0, CHAR_SCRIPTS)
        import retarget
        sys.argv = saved
        _RT["m"] = retarget
        meta = json.load(open(os.path.join(ANIM_DIR, "clips_meta.json")))
        _RT["meta"] = meta
    return _RT["m"]


def apply_pose(ch, clip, frame=1, gender=None):
    """Pose the character with frame `frame` (1-based, 30 fps) of game clip `clip` (idle, combat_idle, run,
    k_light1, k_heavy, l_quick1, npc_crossed, talk ...). Same math as the Anim_*.fbx bake (retarget.py): the clip's
    20-bone rotations are mapped to world-space targets with per-rig rest corrections, so the result matches the
    exported animation for that rig."""
    R = _retarget()
    style = gender or CHARS[ch.cid]["gender"]
    clipd = R.DATA["styles"][style][clip]
    fr = clipd["frames"][max(0, min(len(clipd["frames"]) - 1, int(frame) - 1))]
    rig = ch.rig
    pre = "mixamorig:"
    bones = rig.data.bones
    rest = {b.name: b.matrix_local.to_3x3() for b in bones}
    dirs_ts = R.ts_rest_dirs(style == "female")
    corr = {}
    for mb, tb in R.MAP.items():
        b = bones[pre + mb]
        dm = (b.tail_local - b.head_local).normalized()
        corr[mb] = dm.rotation_difference(dirs_ts[tb]).to_matrix()
    body = ch.mesh("Body")
    height = (max((body.matrix_world @ v.co).z for v in body.data.vertices) - ch.rig.matrix_world.translation.z) if body else 1.8
    scale = height / 1.8
    W = {}
    Rm = {}
    for tb in R.TS_ORDER:
        i = R.BI[tb] * 3
        Rm[tb] = R.euler_ts(fr[i], fr[i + 1], fr[i + 2])
        W[tb] = Rm[tb] if tb == "root" else W[R.TS_PARENT[tb]] @ Rm[tb]
    half = Quaternion().slerp(Rm["chest"].to_quaternion(), 0.5).to_matrix()
    target = {"Hips": W["hips"], "Spine": W["spine"], "Spine1": W["spine"] @ half, "Spine2": W["chest"],
              "Neck": W["neck"], "Head": W["head"]}
    for mb, tb in R.MAP.items():
        target[mb] = W[tb] @ corr[mb]
    world = {}
    for b in bones:
        bn = b.name
        short = bn[len(pre):] if bn.startswith(pre) else bn
        pw = world[b.parent.name] if b.parent else Matrix.Identity(3)
        wt = target.get(short, pw)
        world[bn] = wt
        basis = rest[bn].inverted() @ (pw.inverted() @ wt) @ rest[bn]
        pb = rig.pose.bones[bn]
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = basis.to_quaternion()
        pb.location = (0, 0, 0)
    hp = rig.pose.bones[pre + "Hips"]
    hp.location = rest[pre + "Hips"].inverted() @ ((R.M @ Vector(fr[-3:])) * scale)
    bpy.context.view_layer.update()


def rot_bone(ch, bone, x=0.0, y=0.0, z=0.0, space="LOCAL"):
    """Extra local rotation (degrees) on top of the current pose."""
    pb = ch.rig.pose.bones["mixamorig:" + bone]
    pb.rotation_mode = "QUATERNION"
    q = Euler((math.radians(x), math.radians(y), math.radians(z)), "XYZ").to_quaternion()
    pb.rotation_quaternion = pb.rotation_quaternion @ q
    bpy.context.view_layer.update()


def curl_fingers(ch, side="Left", amount=60.0, thumb=25.0, spread=0.0):
    """Close the hand (0 = flat, ~70 = fist). Applies along each finger chain."""
    for f in ("Index", "Middle", "Ring", "Pinky"):
        for i, k in enumerate((0.7, 1.0, 0.8)):
            n = f"{side}Hand{f}{i + 1}"
            if "mixamorig:" + n in ch.rig.pose.bones:
                rot_bone(ch, n, x=amount * k)
    for i, k in enumerate((0.4, 0.7, 0.6)):
        n = f"{side}HandThumb{i + 1}"
        if "mixamorig:" + n in ch.rig.pose.bones:
            rot_bone(ch, n, x=thumb * k)


# ============================================================================================ robots
_ROBO_MODS = {}


def _robomods():
    if not _ROBO_MODS:
        import robokit
        import robopreview
        import roboscene
        _ROBO_MODS.update(K=robokit, P=robopreview, S=roboscene)
    return _ROBO_MODS


class Robot:
    def __init__(self, kind, holder, objs):
        self.kind, self.holder, self.objs = kind, holder, objs

    def rot(self, part, x=0.0, y=0.0, z=0.0):
        _robomods()["P"].set_rot(self.objs[part], x, y, z)

    def ground(self, z=None):
        """Drop/raise the robot so its lowest foot vertex rests on z (default: the placement height)."""
        bpy.context.view_layer.update()
        z = self.holder.location.z if z is None else z
        lo = 1e9
        for n in ("foot_L", "foot_R", "shin_L", "shin_R"):
            o = self.objs.get(n)
            if o is None:
                continue
            mw = o.matrix_world
            for v in o.data.vertices:
                lo = min(lo, (mw @ v.co).z)
        if lo < 1e8:
            self.holder.location.z += z - lo
            bpy.context.view_layer.update()

    def glow(self, strength=None, color=None):
        for o in self.objs.values():
            if o.type == "MESH":
                for m in o.data.materials:
                    if m and m.name.startswith(f"{self.kind}_robot_glow"):
                        for n in m.node_tree.nodes:
                            if n.type == "BSDF_PRINCIPLED":
                                if strength is not None:
                                    n.inputs["Emission Strength"].default_value = strength
                                if color is not None:
                                    n.inputs["Emission Color"].default_value = (*color, 1)


def load_robot(kind, loc=(0, 0, 0), yaw=0.0, scale=1.0, pose=None, glow=None):
    """Append blender/robots/out/<kind>.blend, rebuild its materials like the robot previews (palette x worn-metal
    detail maps, emissive glow) and parent it under a placement empty. pose: {part: (x, y, z) degrees} in robot
    space, or 'combat' for the preview combat pose."""
    R = _robomods()
    K, P = R["K"], R["P"]
    objs = _append(os.path.join(ROBO_DIR, "out", f"{kind}.blend"))
    c = coll(f"robot_{kind}_{len([k for k in bpy.data.collections if k.name.startswith('robot_' + kind)])}")
    byname = {}
    for o in objs:
        c.objects.link(o)
        byname[o.name.split(".")[0]] = o
    # per-instance material copies named by kind (robot_* names collide between kinds)
    done = {}
    for o in objs:
        if o.type != "MESH":
            continue
        for i, m in enumerate(o.data.materials):
            if m is None:
                continue
            base = m.name.split(".")[0]
            if base in K.MAT_NAMES:
                if base not in done:
                    nm = m.copy()
                    nm.name = f"{kind}_{base}"
                    P.setup_material(nm, kind, K.MAT_NAMES.index(base))
                    done[base] = nm
                o.data.materials[i] = done[base]
    holder = bpy.data.objects.new(f"robot_{kind}", None)
    link(holder, c)
    for o in objs:
        if o.parent is None:
            o.parent = holder
    holder.location = loc
    holder.rotation_euler = (0, 0, math.radians(yaw))
    holder.scale = (scale, scale, scale)
    rb = Robot(kind, holder, byname)
    if pose == "combat":
        if "hips" in byname:
            P.pose_biped(byname, 1.0, kind)
        else:
            P.pose_drone(byname)
    elif isinstance(pose, dict):
        for part, r in pose.items():
            if part in byname:
                rb.rot(part, *r)
    if glow is not None:
        rb.glow(glow)
    bpy.context.view_layer.update()
    if "foot_L" in byname:
        rb.ground(loc[2])
    return rb


# ============================================================================================ misc helpers
def hide_from_camera(ob):
    ob.visible_camera = False


def emissive_plane(size, loc, color, strength, rot=(0, 0, 0), name="glowplane", camera=True):
    me = bpy.data.meshes.new(name)
    hx, hy = size[0] / 2, size[1] / 2
    me.from_pydata([(-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    me.materials.append(emissive(name, color, strength))
    ob.visible_camera = camera
    link(ob)
    return ob


def contact_sheet(paths, out, cols=4, cell=(480, 270), bg=(0.07, 0.08, 0.1), labels=True):
    """Composite images into a grid with numpy (no external tools)."""
    import numpy as np
    W, H = cell
    rows = (len(paths) + cols - 1) // cols
    gap = 8
    sheet = np.zeros((rows * (H + gap) + gap, cols * (W + gap) + gap, 4), np.float32)
    sheet[..., 0], sheet[..., 1], sheet[..., 2], sheet[..., 3] = bg[0], bg[1], bg[2], 1.0
    for i, p in enumerate(paths):
        im = bpy.data.images.load(p)
        w, h = im.size
        a = np.empty(w * h * 4, np.float32)
        im.pixels.foreach_get(a)
        a = a.reshape(h, w, 4)
        bpy.data.images.remove(im)
        s = min(W / w, H / h)
        nw, nh = max(1, int(w * s)), max(1, int(h * s))
        ys = (np.arange(nh) / s).astype(int).clip(0, h - 1)
        xs = (np.arange(nw) / s).astype(int).clip(0, w - 1)
        small = a[ys][:, xs]
        if small.shape[2] == 4:
            al = small[..., 3:4]
            checker = np.ones_like(small[..., :3]) * 0.16
            yy, xx = np.meshgrid(np.arange(nh), np.arange(nw), indexing="ij")
            checker[((yy // 12 + xx // 12) % 2) == 0] = 0.22
            small = np.concatenate([small[..., :3] * al + checker * (1 - al), np.ones_like(al)], 2)
        r, cidx = divmod(i, cols)
        # image rows are bottom-up in Blender; place from the top
        y0 = sheet.shape[0] - (gap + r * (H + gap)) - H + (H - nh) // 2
        x0 = gap + cidx * (W + gap) + (W - nw) // 2
        sheet[y0:y0 + nh, x0:x0 + nw] = small
    img = bpy.data.images.new("sheet", sheet.shape[1], sheet.shape[0], alpha=True)
    img.pixels.foreach_set(sheet.ravel())
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    log("contact sheet", out)


def over_color(src, dst, color=(0.02, 0.025, 0.035)):
    """Preview helper: composite an RGBA PNG over a flat colour (straight alpha) and save."""
    import numpy as np
    im = bpy.data.images.load(src)
    w, h = im.size
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    al = a[..., 3:4]
    out = np.concatenate([a[..., :3] * al + np.array(color, np.float32) * (1 - al), np.ones_like(al)], 2)
    o = bpy.data.images.new("over", w, h, alpha=True)
    o.pixels.foreach_set(out.ravel())
    o.filepath_raw = dst
    o.file_format = "PNG"
    o.save()


# ============================================================================================ vehicles (cyber kit)
VEH_DIR = os.path.join(ASSETS, "Art", "Vehicles")
_VEH = {}
_VEHMAN = None


def veh_manifest():
    global _VEHMAN
    if _VEHMAN is None:
        _VEHMAN = json.load(open(os.path.join(VEH_DIR, "manifest.json")))
    return _VEHMAN


def veh_material(name):
    """Cycles material from the vehicle kit manifest (BaseColor / Normal / MaskMap R metal G AO A smoothness /
    Emission, tiling per material), same mapping as the URP Lit setup."""
    key = ("veh", name)
    if key in _MATS:
        try:
            _MATS[key].name
            return _MATS[key]
        except ReferenceError:
            pass
    d = veh_manifest()["materials"].get(name)
    m = bpy.data.materials.new(name + "__veh")
    _MATS[key] = m
    T = NT(m)
    b = T.n("ShaderNodeBsdfPrincipled")
    T.L(b.outputs[0], T.out.inputs["Surface"])
    if d is None:
        return m
    if d.get("kind") == "param" or not d.get("textures"):
        c = d.get("baseColor", [0.5, 0.5, 0.5, 1])
        b.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1)
        b.inputs["Metallic"].default_value = d.get("metallic", 0.0)
        b.inputs["Roughness"].default_value = 1 - d.get("smoothness", 0.5)
        if d.get("surface") == "Transparent":
            b.inputs["Alpha"].default_value = max(0.25, c[3] if len(c) > 3 else 0.5)
            b.inputs["Roughness"].default_value = 0.03
        return m
    tex = d["textures"]
    uv = T.n("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    mp = T.n("ShaderNodeMapping")
    tl = d.get("tiling", [1, 1])
    if d.get("uvMode", "world") != "fit":
        mp.inputs["Scale"].default_value = (tl[0], tl[1], 1)
    T.L(uv.outputs[0], mp.inputs["Vector"])
    vec = mp.outputs[0]

    def img(k, nonc):
        p = os.path.join(VEH_DIR, tex.get(k, "")) if k in tex else ""
        if not p or not os.path.exists(p):
            return None
        t = T.n("ShaderNodeTexImage")
        t.image = _img(p, nonc)
        T.L(vec, t.inputs[0])
        return t
    bc = img("BaseColor", False)
    mk = img("MaskMap", True)
    if bc is None:
        return m
    if mk is not None:
        sep = T.n("ShaderNodeSeparateColor")
        T.L(mk.outputs["Color"], sep.inputs[0])
        T.L(sep.outputs[0], b.inputs["Metallic"])
        T.L(T.math("SUBTRACT", 1.0, mk.outputs["Alpha"]), b.inputs["Roughness"])
        aoc = T.n("ShaderNodeCombineColor")
        for k in range(3):
            T.L(sep.outputs[1], aoc.inputs[k])
        T.L(T.mix(bc.outputs["Color"], aoc.outputs[0], 0.7, blend="MULTIPLY"), b.inputs["Base Color"])
    else:
        T.L(bc.outputs["Color"], b.inputs["Base Color"])
    nm = img("Normal", True)
    if nm is not None:
        nmap = T.n("ShaderNodeNormalMap", Strength=d.get("normalScale", 1.0))
        T.L(nm.outputs["Color"], nmap.inputs["Color"])
        T.L(nmap.outputs[0], b.inputs["Normal"])
    if d.get("clearCoat"):
        b.inputs["Coat Weight"].default_value = 0.8
        b.inputs["Coat Roughness"].default_value = 0.05
    em = img("Emission", False) if "Emission" in tex else None
    if em is not None:
        T.L(em.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = d.get("emissionIntensity", 1.0) * 1.6
    if d.get("surface") == "Transparent":
        T.L(bc.outputs["Alpha"], b.inputs["Alpha"])
    return m


def _veh_lib(name):
    if name in _VEH:
        return _VEH[name]
    rec = [a for a in veh_manifest()["assets"] if a["name"] == name][0]
    path = os.path.join(VEH_DIR, rec["file"])
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, axis_forward="-Z", axis_up="Y", use_custom_normals=True, bake_space_transform=True)
    new = [o for o in bpy.data.objects if o not in before]
    c = bpy.data.collections.new(f"_veh_{name}")
    _lib_coll().children.link(c)
    for o in new:
        if o.type == "MESH" and ("_LOD1" in o.name or "_LOD2" in o.name):
            bpy.data.objects.remove(o, do_unlink=True)
    for o in [o for o in bpy.data.objects if o not in before]:
        for uc in list(o.users_collection):
            uc.objects.unlink(o)
        c.objects.link(o)
        if o.type == "MESH":
            for i, ms in enumerate(o.data.materials):
                if ms is not None:
                    o.data.materials[i] = veh_material(ms.name.split(".")[0])
    _VEH[name] = c
    return c


def place_vehicle(name, loc=(0, 0, 0), rot=0.0, scale=1.0):
    """Instance a cyber vehicle from Assets/Art/Vehicles (front faces Blender -Y like the env kit)."""
    c = _veh_lib(name)
    e = bpy.data.objects.new(name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = c
    e.location = loc
    e.rotation_euler = (0, 0, math.radians(rot)) if not isinstance(rot, (tuple, list)) else [math.radians(a) for a in rot]
    e.scale = (scale, scale, scale)
    link(e)
    return e


# ============================================================================================ customization catalog
CUSTOM = os.path.join(ASSETS, "Resources", "Characters", "Custom")
CUSTOM_CACHE = os.path.join(ROOT, "blender", "custom", "cache")
_CAT = None


def catalog():
    global _CAT
    if _CAT is None:
        _CAT = json.load(open(os.path.join(CUSTOM, "catalog.json")))
    return _CAT


def _rigid_to_world(cid, bone="mixamorig:Head"):
    """Inverse of blender/custom/common.rigid_matrix: imported rigid-attachment coordinates -> rest-pose world."""
    info = json.load(open(os.path.join(CUSTOM_CACHE, f"{cid}_ref.json")))
    b = info["bones"][bone]
    H = Matrix([b["bindpose"][i * 4:(i + 1) * 4] for i in range(4)])
    sc = info["unit_scale"]
    S = Matrix.Diagonal((sc, sc, sc, 1.0))
    C = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))
    return (C.inverted() @ S.inverted() @ H.inverted() @ S @ C).inverted()


def _custom_mat(slot, entry, hair_hex):
    m = bpy.data.materials.new(f"cust_{entry['id']}_{slot}")
    T = NT(m)
    b = T.n("ShaderNodeBsdfPrincipled")
    T.L(b.outputs[0], T.out.inputs["Surface"])
    md = (entry.get("materials") or {}).get(slot, {}) if isinstance(entry.get("materials"), dict) else {}
    if slot == "Hair":
        tx = T.n("ShaderNodeTexImage")
        tx.image = bpy.data.images.load(os.path.join(CUSTOM, entry["baseMap"] + ".png"), check_existing=True)
        tx.interpolation = "Cubic"
        hc = tuple(min(1.0, c * 1.8) for c in hexlin(hair_hex))  # slight lift so very dark hair keeps its curl detail
        T.L(T.mix(tx.outputs["Color"], hc, 1.0, blend="MULTIPLY"), b.inputs["Base Color"])
        cut = entry.get("alphaCutoff", 0.4)
        T.L(T.maprange(tx.outputs["Alpha"], cut - 0.22, cut + 0.12, 0.0, 1.0, smooth=True), b.inputs["Alpha"])
        b.inputs["Roughness"].default_value = 0.5
        b.inputs["Specular IOR Level"].default_value = 0.35
        b.inputs["Sheen Weight"].default_value = 0.08
        b.inputs["Coat Weight"].default_value = 0.05
        b.inputs["Coat Roughness"].default_value = 0.35
    elif slot == "EyewearFrame":
        fr = entry.get("frame", {})
        b.inputs["Base Color"].default_value = (*hexlin(md.get("tint", "#20242a")), 1)
        b.inputs["Metallic"].default_value = fr.get("metallic", 0.6)
        b.inputs["Roughness"].default_value = 1 - fr.get("smoothness", 0.75)
    elif slot == "EyewearLens":
        T.nt.nodes.remove(b)
        gl = T.n("ShaderNodeBsdfGlossy", Roughness=0.03)
        gl.inputs["Color"].default_value = (*[0.5 + 0.5 * c for c in hexlin(md.get("lensTint", "#202020"))], 1)
        tr = T.n("ShaderNodeBsdfTransparent")
        tr.inputs["Color"].default_value = (*hexlin(md.get("lensTint", "#808080")), 1)
        fr_ = T.n("ShaderNodeFresnel", IOR=1.5)
        mx = T.n("ShaderNodeMixShader")
        T.L(T.math("ADD", fr_.outputs[0], md.get("lensAlpha", 0.4) * 0.6), mx.inputs["Fac"])
        T.L(tr.outputs[0], mx.inputs[1])
        T.L(gl.outputs[0], mx.inputs[2])
        T.L(mx.outputs[0], T.out.inputs["Surface"])
    elif slot == "Glow":
        c = hexlin(md.get("color", "#00e5ff"))
        b.inputs["Base Color"].default_value = (*c, 1)
        b.inputs["Emission Color"].default_value = (*c, 1)
        b.inputs["Emission Strength"].default_value = md.get("intensity", 3.0) * 1.6
    return m


def attach_custom(ch, category, item_id, hair_hex=None):
    """Attach a customization-catalog item (hair / eyewear) to a loaded, posed and placed character, the way the
    game does: rigid items follow the Head bone, skinned items get an Armature modifier on the hero rig."""
    entry = [e for e in catalog()[category] if e["id"] == item_id and e["hero"] == ch.cid][0]
    if hair_hex is None:
        man = json.load(open(os.path.join(UNITY_CHARS, ch.cid.capitalize(), f"{ch.cid.capitalize()}.manifest.json")))
        hair_hex = man.get("palette", {}).get("hair", "#1d1714")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.join(CUSTOM, entry["file"] + ".fbx"))
    new = [o for o in bpy.data.objects if o not in before]
    mesh = [o for o in new if o.type == "MESH"][0]
    bpy.context.view_layer.update()
    mesh.data.transform(mesh.matrix_world)
    for o in new:
        if o is not mesh:
            bpy.data.objects.remove(o, do_unlink=True)
    mesh.parent = None
    mesh.matrix_world = Matrix.Identity(4)
    for i, ms in enumerate(mesh.data.materials):
        mesh.data.materials[i] = _custom_mat(ms.name.split(".")[0] if ms else "Hair", entry, hair_hex)
    rig = ch.rig
    for uc in list(mesh.users_collection):
        uc.objects.unlink(mesh)
    ch.coll.objects.link(mesh)
    if entry.get("kind") == "skinned":
        mesh.parent = rig
        mesh.matrix_parent_inverse = Matrix.Identity(4)
        mesh.matrix_basis = Matrix.Identity(4)
        for md in list(mesh.modifiers):
            mesh.modifiers.remove(md)
        am = mesh.modifiers.new("Armature", "ARMATURE")
        am.object = rig
    else:
        mesh.data.transform(_rigid_to_world(ch.cid, entry.get("bone", "mixamorig:Head")))
        bn = entry.get("bone", "mixamorig:Head")
        pb = rig.pose.bones[bn]
        target = rig.matrix_world @ pb.matrix @ rig.data.bones[bn].matrix_local.inverted()
        mesh.parent = rig
        mesh.parent_type = "BONE"
        mesh.parent_bone = bn
        bpy.context.view_layer.update()
        mesh.matrix_world = target  # follows later pose tweaks (head turns) like the in-game bone attachment
    for p in mesh.data.polygons:
        p.use_smooth = True
    if category == "hair":
        for o in ch.objs:
            if o.type == "MESH" and str(o.get("eoa_part", "")).startswith("Hair_"):
                o.hide_render = True
    for h in entry.get("hides", []) or []:
        for o in ch.objs:
            if o.type == "MESH" and o.get("eoa_part") == h:
                o.hide_render = True
    mesh["eoa_part"] = f"Custom_{category}_{item_id}"
    ch.objs.append(mesh)
    bpy.context.view_layer.update()
    return mesh


HERO_LOOK = {"kael": {"hair": "curly_medium"}, "lyra": {"hair": "long_curls"}}


def dress_default(ch, eyewear=None):
    """Default in-game look from the catalog (hair) plus optional eyewear (key art)."""
    look = catalog().get("defaults", {}).get(ch.cid) or HERO_LOOK.get(ch.cid, {})
    if look.get("hair"):
        attach_custom(ch, "hair", look["hair"])
    ew = eyewear or (look.get("eyewear") if look.get("eyewear") not in (None, "none") else None)
    if ew:
        attach_custom(ch, "eyewear", ew)


# ============================================================================================ remade heroes (v2)
HERO_APPEAR = {  # Appearance.BaseDefault (Scripts/Game/Appearance.cs) for the remade heroes
    "kael": dict(skin="#b98a6e", eyes="#5b3a22", hair="#1d1714", outfit="#4d5243", accent="#1f2126", armor="#a9a59a",
                 glow="#00e5ff", glow2="#ff2bd6", tattoo="#00e5ff", hair_id="side_part_volume", stubble=0.6),
    "lyra": dict(skin="#c79878", eyes="#5a3920", hair="#2a1a1e", outfit="#4a4d57", accent="#5a3f8c", armor="#6a6474",
                 glow="#ff2bd6", glow2="#9b5cff", tattoo="#ff2bd6", hair_id="long_waves", stubble=0.0),
}


def _hero_mat(cid, cname, mn, man, ap):
    """Cycles version of the game's runtime material for a remade-hero material slot (manifest materialDefs +
    CharacterModel tints: garment composite of outfit/accent/trim from the mask, lit maps x tint, skin tone,
    emissive glows)."""
    md = man.get("materialDefs", {}).get(mn, {})
    tex = lambda f: _char_tex(cname, f) if f else None  # noqa: E731
    m = bpy.data.materials.new(f"{cid}_{mn}_v2")
    T = NT(m)
    b = T.n("ShaderNodeBsdfPrincipled")
    T.L(b.outputs[0], T.out.inputs["Surface"])

    def img(f, nonc=False):
        p = tex(f)
        if not p or not os.path.exists(p):
            return None
        t = T.n("ShaderNodeTexImage")
        t.image = bpy.data.images.load(p, check_existing=True)
        if nonc:
            t.image.colorspace_settings.name = "Non-Color"
            t.image.alpha_mode = "CHANNEL_PACKED"
        return t

    def normal(f, k=1.0):
        n = img(f, True)
        if n:
            nm = T.n("ShaderNodeNormalMap", Strength=k)
            T.L(n.outputs["Color"], nm.inputs["Color"])
            T.L(nm.outputs[0], b.inputs["Normal"])
    kind = md.get("type")
    if kind == "garment":
        mk = img(md.get("mask"), True)
        prim = hexlin(ap["outfit"]) if "Pants" not in mn else tuple(c * 0.88 for c in hexlin(ap["outfit"]))
        sec = hexlin(ap["accent"])
        trim = (0.255, 0.275, 0.305)
        if mk:
            sep = T.n("ShaderNodeSeparateColor")
            T.L(mk.outputs["Color"], sep.inputs[0])
            c = T.mix(prim, sec, sep.outputs[0])
            c = T.mix(c, trim, sep.outputs[1])
            seam = T.math("SUBTRACT", 1.0, T.math("MULTIPLY", mk.outputs["Alpha"], 0.55))
            c = T.mix(c, (0, 0, 0), T.math("SUBTRACT", 1.0, seam))
            T.L(c, b.inputs["Base Color"])
            sm = T.math("SUBTRACT", T.math("ADD", 0.275, T.math("MULTIPLY", sep.outputs[1], 0.43)), T.math("MULTIPLY", mk.outputs["Alpha"], 0.16))
            T.L(T.math("SUBTRACT", 1.0, T.math("MULTIPLY", sm, 0.9)), b.inputs["Roughness"])
            T.L(sep.outputs[1], b.inputs["Metallic"])
        else:
            b.inputs["Base Color"].default_value = (*prim, 1)
        normal(md.get("normal"))
    elif kind == "lit" and md.get("baseMap"):
        bc = img(md["baseMap"])
        mk = img(md.get("maskMap"), True)
        tint = md.get("tint")
        tcol = None
        if tint == "armor":
            tcol = hexlin(ap["armor"])
        elif tint and tint.startswith("outfit"):
            tcol = tuple(c * 0.75 for c in hexlin(ap["outfit"]))
        col = bc.outputs["Color"]
        if tcol is not None:  # URP _BaseColor = tint (multiplies the whole base map, as CharacterModel.Tint does)
            col = T.mix(col, tcol, 1.0, blend="MULTIPLY")
        if mk:
            sep = T.n("ShaderNodeSeparateColor")
            T.L(mk.outputs["Color"], sep.inputs[0])
            aoc = T.n("ShaderNodeCombineColor")
            for k in range(3):
                T.L(sep.outputs[1], aoc.inputs[k])
            col = T.mix(col, aoc.outputs[0], 1.0, blend="MULTIPLY")
            T.L(sep.outputs[0], b.inputs["Metallic"])
            T.L(T.math("SUBTRACT", 1.0, mk.outputs["Alpha"]), b.inputs["Roughness"])
        T.L(col, b.inputs["Base Color"])
        normal(md.get("normal"))
    elif kind == "lit":
        b.inputs["Base Color"].default_value = (*hexlin(md.get("color", "#808080")), 1)
        b.inputs["Metallic"].default_value = md.get("metallic", 0.0)
        b.inputs["Roughness"].default_value = 1 - md.get("smoothness", 0.5)
    elif kind == "emissive" or mn in ("Glow", "Glow2", "Screen"):
        g = hexlin(ap["glow2"] if mn == "Glow2" else ap["glow"])
        k = 0.6 if mn == "Screen" else 1.0
        b.inputs["Base Color"].default_value = (*[min(1, c * 0.7 + 0.3) for c in g], 1)
        b.inputs["Emission Color"].default_value = (*g, 1)
        b.inputs["Emission Strength"].default_value = 3.5 * k
    elif mn == "Skin":
        return _hero_skin(cid, cname, man, ap)
    elif mn == "Eyes":
        return _hero_eyes(cid, cname, ap)
    elif mn in ("Brows", "Lashes"):
        files = man.get("textures", {}).get(mn) or []
        t = img(files[0]) if files else None
        hc = hexlin(ap["hair"])
        hc = tuple(min(1, c * (1.6 if mn == "Brows" else 0.6)) for c in hc)
        if t:
            bw = T.n("ShaderNodeRGBToBW")
            T.L(t.outputs["Color"], bw.inputs[0])
            T.L(T.mix(hc, (0, 0, 0), T.math("SUBTRACT", 1.0, bw.outputs[0])), b.inputs["Base Color"])
            T.L(T.maprange(t.outputs["Alpha"], 0.2, 0.6), b.inputs["Alpha"])
        b.inputs["Roughness"].default_value = 0.6
    elif mn in ("Teeth", "Tongue"):
        files = man.get("textures", {}).get(mn) or []
        t = img(files[0]) if files else None
        if t:
            T.L(t.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.35
    else:
        b.inputs["Base Color"].default_value = (0.2, 0.2, 0.22, 1)
        b.inputs["Roughness"].default_value = 0.5
    return m


def _hero_skin(cid, cname, man, ap):
    """Skin_<tone> albedo tinted toward the appearance skin colour, Skin_Normal, Skin_MaskMap smoothness, subtle SSS,
    stubble overlay (Kael) and the catalog default tattoo glow map as emission."""
    m = _hd_skin(cid, cname, man)
    nt = m.node_tree
    N, L = nt.nodes, nt.links.new
    b = [n for n in N if n.type == "BSDF_PRINCIPLED"][0]
    b.inputs["Subsurface Weight"].default_value = 0.18
    b.inputs["Subsurface Scale"].default_value = 0.008
    b.inputs["Coat Weight"].default_value = 0.08
    b.inputs["Coat Roughness"].default_value = 0.35
    # remove the generic tattoo hookup; use the catalog default design
    for l in list(b.inputs["Emission Color"].links):
        nt.links.remove(l)
    b.inputs["Emission Strength"].default_value = 0.0
    tat = catalog().get("defaults", {}).get(cid, {}).get("tattoo")
    entry = next((e for e in catalog().get("tattoos", []) if e["id"] == tat and e["hero"] == cid), None)
    if entry:
        gp = os.path.join(CUSTOM, entry["glow"] + ".png")
        ip = os.path.join(CUSTOM, entry["ink"] + ".png")
        bc_link = b.inputs["Base Color"].links[0].from_socket if b.inputs["Base Color"].is_linked else None
        if os.path.exists(ip) and bc_link is not None:
            ti = N.new("ShaderNodeTexImage")
            ti.image = bpy.data.images.load(ip, check_existing=True)
            mx = N.new("ShaderNodeMix")
            mx.data_type = "RGBA"
            mx.blend_type = "MULTIPLY"
            mx.inputs["Factor"].default_value = 1.0
            L(bc_link, mx.inputs[6])
            mt = N.new("ShaderNodeMath")
            mt.operation = "MULTIPLY"
            mt.inputs[1].default_value = 2.0
            bw = N.new("ShaderNodeRGBToBW")
            L(ti.outputs["Color"], bw.inputs[0])
            L(bw.outputs[0], mt.inputs[0])
            L(mt.outputs[0], mx.inputs[7])
            L(mx.outputs[2], b.inputs["Base Color"])
        if os.path.exists(gp):
            tg = N.new("ShaderNodeTexImage")
            tg.image = bpy.data.images.load(gp, check_existing=True)
            mx2 = N.new("ShaderNodeMix")
            mx2.data_type = "RGBA"
            mx2.blend_type = "MULTIPLY"
            mx2.inputs["Factor"].default_value = 1.0
            L(tg.outputs["Color"], mx2.inputs[6])
            mx2.inputs[7].default_value = (*hexlin(ap["tattoo"]), 1)
            L(mx2.outputs[2], b.inputs["Emission Color"])
            b.inputs["Emission Strength"].default_value = 2.5
    return m


def _hero_eyes(cid, cname, ap):
    """Grey eye texture with the iris tinted to the appearance eye colour (CharacterModel.ApplyEyes ellipse)."""
    m = bpy.data.materials.new(f"{cid}_eyes_v2")
    T = NT(m)
    b = T.n("ShaderNodeBsdfPrincipled", Roughness=0.3)
    b.inputs["Coat Weight"].default_value = 1.0
    b.inputs["Coat Roughness"].default_value = 0.02
    T.L(b.outputs[0], T.out.inputs["Surface"])
    p = _char_tex(cname, "Eye_grey.png")
    t = T.n("ShaderNodeTexImage")
    t.image = bpy.data.images.load(p, check_existing=True)
    uv = T.n("ShaderNodeTexCoord")
    sep = T.n("ShaderNodeSeparateXYZ")
    T.L(uv.outputs["UV"], sep.inputs[0])
    du = T.math("SUBTRACT", sep.outputs[0], 0.5)
    dv = T.math("SUBTRACT", sep.outputs[1], 0.5)
    d = T.math("SQRT", T.math("ADD", T.math("MULTIPLY", T.math("MULTIPLY", du, du), 4.0), T.math("MULTIPLY", dv, dv)))
    iris = T.maprange(d, 0.095, 0.075, 0.0, 1.0, smooth=True)
    bw = T.n("ShaderNodeRGBToBW")
    T.L(t.outputs["Color"], bw.inputs[0])
    ic = hexlin(ap["eyes"])
    tinted = T.n("ShaderNodeCombineColor")
    for i in range(3):
        T.L(T.math("MULTIPLY", bw.outputs[0], ic[i] * 3.2), tinted.inputs[i])
    T.L(T.mix(t.outputs["Color"], tinted.outputs[0], iris), b.inputs["Base Color"])
    return m


def load_hero(cid, loc=(0, 0, 0), yaw=0.0, pose=("idle", 1), eyewear=None, hair=None, ground=True, visor=None):
    """Remade hero (heroes_v2) from its Unity FBX + manifest, dressed in the default in-game look: catalog hair
    (Kael side_part_volume, Giva long_waves), default tattoo, Appearance.BaseDefault colours. Optional catalog eyewear
    (hides Giva's built-in Visor, as the game does)."""
    cname = cid.capitalize()
    man = json.load(open(os.path.join(UNITY_CHARS, cname, f"{cname}.manifest.json")))
    ap = HERO_APPEAR[cid]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.join(UNITY_CHARS, cname, f"{cname}.fbx"), ignore_leaf_bones=True)
    new = [o for o in bpy.data.objects if o not in before]
    c = coll(f"hero_{cid}_{len([k for k in bpy.data.collections if k.name.startswith('hero_' + cid)])}")
    rig = [o for o in new if o.type == "ARMATURE"][0]
    for o in new:
        for uc in list(o.users_collection):
            uc.objects.unlink(o)
        c.objects.link(o)
    objs = []
    mats = {}
    for o in new:
        if o.type != "MESH":
            objs.append(o)
            continue
        part = o.name.split(".")[0]
        o["eoa_part"] = part
        if part.startswith(("Hair_", "Facial_")) or part in ("Tongue",):
            bpy.data.objects.remove(o, do_unlink=True)
            continue
        for i, ms in enumerate(o.data.materials):
            mn = ms.name.split(".")[0] if ms else "Default"
            if mn not in mats:
                mats[mn] = _hero_mat(cid, cname, mn, man, ap)
            o.data.materials[i] = mats[mn]
        for p in o.data.polygons:
            p.use_smooth = True
        objs.append(o)
    ch = Character(cid, rig, objs, c)
    ch.man = man
    if pose:
        _pose_hero(ch, *pose)
    ch.place(loc, yaw)
    if pose and ground:
        ch.ground(loc[2])
    look = catalog().get("defaults", {}).get(cid, {})
    attach_custom(ch, "hair", hair or look.get("hair") or ap["hair_id"], hair_hex=ap["hair"])
    if eyewear:
        attach_custom(ch, "eyewear", eyewear)
    elif visor is False:
        for o in objs:
            if o.type == "MESH" and o.get("eoa_part") == "Visor":
                o.hide_render = True
    return ch


def _pose_hero(ch, clip, frame):
    """apply_pose for the FBX-imported rig (gender from the hero)."""
    apply_pose(ch, clip, frame, gender="male" if ch.cid == "kael" else "female")
