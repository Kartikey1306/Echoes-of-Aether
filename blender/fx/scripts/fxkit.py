"""
fxkit: shared helpers for the Echoes of Aether sky & weather FX renders (Blender 5.x, Cycles on Metal, numpy, OIIO).

Everything is procedural: geometry/volumes are built from node noise in Blender, data textures (normals, flipbook
packing, glow) are computed with numpy. Renders go to blender/fx/out as linear EXR; the final textures are written as
PNG straight into the Unity project (Assets/Art/FX/Resources/FX/...).

Conventions
  * Panoramas: Blender camera looking along +Y renders u=0.5 at +Y, u=0.75 at +X, zenith at the top row.
    Unity mapping (Blender x, y, z) = (Unity x, z, y); the sky shader uses u = 0.5 + atan2(d.x, d.z) / 2pi,
    v = 0.5 + asin(d.y) / pi.
  * Arrays are float32 (H, W, C) with row 0 = TOP of the image (OIIO order); PNGs are written in that order.
"""
import math
import os
import sys

import bpy
import numpy as np
import OpenImageIO as oiio

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
FX = os.path.join(ROOT, "blender", "fx")
OUT = os.path.join(FX, "out")
PREV = os.path.join(FX, "previews")
UNITY_FX = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets", "Art", "FX", "Resources", "FX")

for d in (OUT, PREV):
    os.makedirs(d, exist_ok=True)


def args():
    """Arguments after '--' on the Blender command line."""
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def flag(name, default=None):
    a = args()
    for i, x in enumerate(a):
        if x == name:
            return a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith("--") else True
    return default


# ---------------------------------------------------------------------------------------------------------- scene

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    w = bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0, 0, 0, 1)
    bg.inputs[1].default_value = 0.0
    return sc


def setup_cycles(res, samples=64, transparent=False, denoise=True, view="Standard", look=None, exposure=0.0,
                 bounces=4, adaptive=0.01, clamp=0.0, step_rate=1.0, max_steps=1024):
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
    cy.use_adaptive_sampling = adaptive > 0
    if adaptive > 0:
        cy.adaptive_threshold = adaptive
    cy.use_denoising = denoise
    if denoise:
        cy.denoiser = "OPENIMAGEDENOISE"
        cy.denoising_input_passes = "RGB_ALBEDO_NORMAL"
        cy.denoising_prefilter = "ACCURATE"
        for k, v in (("denoising_quality", "HIGH"), ("denoising_use_gpu", True)):
            try:
                setattr(cy, k, v)
            except Exception:
                pass
    cy.use_light_tree = True
    cy.max_bounces = bounces
    cy.diffuse_bounces = min(bounces, 2)
    cy.glossy_bounces = min(bounces, 4)
    cy.transmission_bounces = max(bounces, 8)
    cy.volume_bounces = min(bounces, 2)
    cy.transparent_max_bounces = 64
    cy.sample_clamp_direct = 0.0
    cy.sample_clamp_indirect = clamp
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    for k, v in (("volume_step_rate", step_rate), ("volume_max_steps", max_steps)):
        try:
            setattr(cy, k, v)
        except Exception:
            pass
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    sc.render.dither_intensity = 0.0
    sc.view_settings.view_transform = view
    if look:
        try:
            sc.view_settings.look = look
        except Exception:
            pass
    sc.view_settings.exposure = exposure
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.image_settings.color_depth = "32"
    sc.render.image_settings.color_mode = "RGBA"
    try:
        sc.render.image_settings.exr_codec = "ZIP"
    except Exception:
        pass
    return sc


def camera(name="Cam", loc=(0, 0, 0), rot=(math.pi / 2, 0, 0), kind="PERSP", ortho_scale=1.0, lens=50.0, clip=(0.01, 100000.0)):
    cd = bpy.data.cameras.new(name)
    cd.type = kind
    if kind == "ORTHO":
        cd.ortho_scale = ortho_scale
    elif kind == "PERSP":
        cd.lens = lens
    cd.clip_start, cd.clip_end = clip
    ob = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = rot
    bpy.context.scene.camera = ob
    return ob


def pano_camera(loc=(0, 0, 0), lat=(-90, 90), lon=(-180, 180)):
    """Equirectangular camera looking along +Y (u = 0.5 at +Y, 0.75 at +X)."""
    ob = camera("Pano", loc, (math.pi / 2, 0, 0), kind="PANO")
    cd = ob.data
    cd.panorama_type = "EQUIRECTANGULAR"
    cd.latitude_min, cd.latitude_max = math.radians(lat[0]), math.radians(lat[1])
    cd.longitude_min, cd.longitude_max = math.radians(lon[0]), math.radians(lon[1])
    return ob


def link(ob, coll=None):
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


def mesh_object(name, verts, faces, coll=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    return link(bpy.data.objects.new(name, me), coll)


def box(name, center, size, coll=None):
    cx, cy, cz = center
    sx, sy, sz = [s / 2 for s in size]
    v = [(cx + x * sx, cy + y * sy, cz + z * sz) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return mesh_object(name, v, f, coll)


def plane(name, center, size, coll=None):
    cx, cy, cz = center
    sx, sy = size[0] / 2, size[1] / 2
    return mesh_object(name, [(cx - sx, cy - sy, cz), (cx + sx, cy - sy, cz), (cx + sx, cy + sy, cz), (cx - sx, cy + sy, cz)],
                       [(0, 1, 2, 3)], coll)


# ---------------------------------------------------------------------------------------------------------- nodes

class NB:
    """Tiny node-graph builder: nb.n('ShaderNodeMath', operation='MULTIPLY', inputs={1: 2.0})."""

    def __init__(self, tree):
        self.t = tree
        self.nodes = tree.nodes
        self.links = tree.links

    def n(self, kind, inputs=None, **props):
        node = self.nodes.new(kind)
        for k, v in props.items():
            setattr(node, k, v)
        for k, v in (inputs or {}).items():
            node.inputs[k].default_value = v
        return node

    def link(self, a, b):
        self.links.new(a, b)
        return b

    def math(self, op, a, b=None, clamp=False):
        node = self.n("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, x in enumerate((a, b)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                node.inputs[i].default_value = x
            else:
                self.link(x, node.inputs[i])
        return node.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        node = self.n("ShaderNodeVectorMath", operation=op)
        for i, x in enumerate((a, b)):
            if x is None:
                continue
            if isinstance(x, (tuple, list)):
                node.inputs[i].default_value = x
            else:
                self.link(x, node.inputs[i])
        if scale is not None:
            if isinstance(scale, (int, float)):
                node.inputs[3].default_value = scale
            else:
                self.link(scale, node.inputs[3])
        return node.outputs[1] if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else node.outputs[0]

    def xyz(self, x, y, z):
        node = self.n("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            if isinstance(v, (int, float)):
                node.inputs[i].default_value = v
            else:
                self.link(v, node.inputs[i])
        return node.outputs[0]

    def sep(self, v):
        node = self.n("ShaderNodeSeparateXYZ")
        self.link(v, node.inputs[0])
        return node.outputs[0], node.outputs[1], node.outputs[2]

    def noise(self, vec, scale=1.0, detail=4.0, rough=0.5, w=None, dims="3D", lac=2.0, distortion=0.0, kind="FBM", normalize=True):
        node = self.n("ShaderNodeTexNoise", noise_dimensions=dims)
        try:
            node.noise_type = kind
        except Exception:
            pass
        try:
            node.normalize = normalize
        except Exception:
            pass
        self.link(vec, node.inputs["Vector"])
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        node.inputs["Roughness"].default_value = rough
        node.inputs["Lacunarity"].default_value = lac
        node.inputs["Distortion"].default_value = distortion
        if w is not None:
            if isinstance(w, (int, float)):
                node.inputs["W"].default_value = w
            else:
                self.link(w, node.inputs["W"])
        return node.outputs["Fac"], node.outputs["Color"]

    def ramp(self, fac, stops, interp="LINEAR"):
        node = self.n("ShaderNodeValToRGB")
        cr = node.color_ramp
        cr.interpolation = interp
        while len(cr.elements) > len(stops):
            cr.elements.remove(cr.elements[-1])
        while len(cr.elements) < len(stops):
            cr.elements.new(0.5)
        for e, (p, c) in zip(cr.elements, stops):
            e.position = p
            e.color = c if len(c) == 4 else (c[0], c[1], c[2], 1)
        self.link(fac, node.inputs[0])
        return node.outputs[0], node.outputs[1]

    def smooth(self, e0, e1, x):
        """smoothstep(e0, e1, x) via Map Range (smoothstep)."""
        node = self.n("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP", clamp=True)
        for name, e in (("From Min", e0), ("From Max", e1)):
            if isinstance(e, (int, float)):
                node.inputs[name].default_value = e
            else:
                self.link(e, node.inputs[name])
        node.inputs["To Min"].default_value = 0.0
        node.inputs["To Max"].default_value = 1.0
        self.link(x, node.inputs["Value"])
        return node.outputs["Result"]

    def remap(self, x, a0, a1, b0, b1, clamp=True):
        node = self.n("ShaderNodeMapRange", interpolation_type="LINEAR", clamp=clamp)
        node.inputs["From Min"].default_value = a0
        node.inputs["From Max"].default_value = a1
        node.inputs["To Min"].default_value = b0
        node.inputs["To Max"].default_value = b1
        self.link(x, node.inputs["Value"])
        return node.outputs["Result"]


def torus4(nb, x, y, period, radius):
    """Map a planar coordinate (x, y) with the given period onto a 4D torus -> (vec3, w) for a seamless 4D noise."""
    k = 2 * math.pi / period
    ax = nb.math("MULTIPLY", x, k)
    ay = nb.math("MULTIPLY", y, k)
    cx = nb.math("MULTIPLY", nb.math("COSINE", ax), radius)
    sx = nb.math("MULTIPLY", nb.math("SINE", ax), radius)
    cy = nb.math("MULTIPLY", nb.math("COSINE", ay), radius)
    sy = nb.math("MULTIPLY", nb.math("SINE", ay), radius)
    return nb.xyz(cx, sx, cy), sy


def emission_material(name, color=(1, 1, 1, 1), strength=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    nb = NB(nt)
    e = nb.n("ShaderNodeEmission", inputs={0: color, 1: strength})
    o = nb.n("ShaderNodeOutputMaterial")
    nb.link(e.outputs[0], o.inputs[0])
    return m


def new_material(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    nb = NB(m.node_tree)
    out = nb.n("ShaderNodeOutputMaterial")
    return m, nb, out


# ---------------------------------------------------------------------------------------------------------- render / io

def render(path, write=True):
    sc = bpy.context.scene
    sc.render.filepath = path
    bpy.ops.render.render(write_still=write)
    return path


def load(path):
    buf = oiio.ImageBuf(path)
    a = buf.get_pixels(oiio.FLOAT)
    if a is None:
        raise RuntimeError("could not read " + path + ": " + buf.geterror())
    return np.asarray(a, dtype=np.float32)


def srgb(x):
    x = np.clip(x, 0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def linear(x):
    x = np.clip(x, 0, None)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def save_png(arr, path, to_srgb=False, dither=True, bits=8, seed=1):
    """Write float (H, W, C) in 0..1 (row 0 = top). to_srgb applies the sRGB transfer to RGB (not alpha)."""
    a = np.array(arr, dtype=np.float32, copy=True)
    if a.ndim == 2:
        a = a[:, :, None]
    if to_srgb:
        a[:, :, :3] = srgb(a[:, :, :3])
    mx = 255.0 if bits == 8 else 65535.0
    if dither:
        rng = np.random.default_rng(seed)
        n = (rng.random(a.shape, dtype=np.float32) - rng.random(a.shape, dtype=np.float32)) / mx
        a = a + n
    a = np.clip(np.round(a * mx), 0, mx)
    a = a.astype(np.uint8 if bits == 8 else np.uint16)
    h, w, c = a.shape
    spec = oiio.ImageSpec(w, h, c, oiio.UINT8 if bits == 8 else oiio.UINT16)
    spec.attribute("oiio:ColorSpace", "sRGB" if to_srgb else "Linear")
    if c == 4:
        # our RGBA is already exactly what we want stored: stop OIIO un-premultiplying RGB by alpha
        spec.attribute("oiio:UnassociatedAlpha", 1)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path[:-4] + ".tmp" + path[-4:]
    out = oiio.ImageOutput.create(tmp)
    out.open(tmp, spec)
    out.write_image(a)
    out.close()
    os.replace(tmp, path)          # atomic: Unity never imports a half-written texture
    print("[fx] wrote", os.path.relpath(path, ROOT), a.shape)
    return path


def save_exr(arr, path):
    a = np.ascontiguousarray(arr, dtype=np.float32)
    if a.ndim == 2:
        a = a[:, :, None]
    h, w, c = a.shape
    spec = oiio.ImageSpec(w, h, c, oiio.HALF)
    out = oiio.ImageOutput.create(path)
    out.open(path, spec)
    out.write_image(a)
    out.close()
    return path


def resize(a, w, h):
    """Box/area resize via OIIO (good for downsampling atlases)."""
    a = np.ascontiguousarray(a, dtype=np.float32)
    if a.ndim == 2:
        a = a[:, :, None]
    src = oiio.ImageBuf(oiio.ImageSpec(a.shape[1], a.shape[0], a.shape[2], oiio.FLOAT))
    src.set_pixels(oiio.ROI(), a)
    dst = oiio.ImageBufAlgo.resize(src, roi=oiio.ROI(0, w, 0, h, 0, 1, 0, a.shape[2]))
    return np.asarray(dst.get_pixels(oiio.FLOAT), dtype=np.float32)


# ---------------------------------------------------------------------------------------------------------- numpy image ops

def gauss_kernel_fft(shape, sigma):
    h, w = shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    return np.exp(-2 * (math.pi ** 2) * (sigma ** 2) * (fx ** 2 + fy ** 2)).astype(np.float32)


def blur(a, sigma, wrap=False):
    """Gaussian blur (FFT). wrap=False pads by 3 sigma with zeros (for sprites); wrap=True is periodic (tiles)."""
    if sigma <= 0:
        return a
    a = np.asarray(a, dtype=np.float32)
    squeeze = a.ndim == 2
    if squeeze:
        a = a[:, :, None]
    p = 0 if wrap else int(math.ceil(sigma * 3))
    if p:
        a = np.pad(a, ((p, p), (p, p), (0, 0)))
    k = gauss_kernel_fft(a.shape[:2], sigma)
    out = np.empty_like(a)
    for c in range(a.shape[2]):
        out[:, :, c] = np.real(np.fft.ifft2(np.fft.fft2(a[:, :, c]) * k))
    if p:
        out = out[p:-p, p:-p]
    return out[:, :, 0] if squeeze else out


def height_to_normal(h, strength=1.0):
    """Periodic height field (H, W) in pixels-units -> tangent-space normal (H, W, 3) in -1..1 (x right, y up in image)."""
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5 * strength
    dy = (np.roll(h, 1, axis=0) - np.roll(h, -1, axis=0)) * 0.5 * strength  # row 0 = top -> +y is up
    n = np.stack([-dx, -dy, np.ones_like(h)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n.astype(np.float32)


def atlas(frames, cols, rows):
    """frames: list of (h, w, c) arrays, row-major from the TOP-left cell."""
    h, w, c = frames[0].shape
    out = np.zeros((rows * h, cols * w, c), dtype=np.float32)
    for i, f in enumerate(frames):
        r, q = divmod(i, cols)
        out[r * h:(r + 1) * h, q * w:(q + 1) * w] = f
    return out


def contact_sheet(img, path, bg=(0.05, 0.06, 0.08), scale=1.0):
    """Composite an RGBA (premultiplied or straight alpha) image over a dark background for a preview PNG (sRGB)."""
    a = np.asarray(img, dtype=np.float32)
    if a.shape[2] == 4:
        rgb = a[:, :, :3] + np.array(bg, dtype=np.float32) * (1 - a[:, :, 3:4])
    else:
        rgb = a[:, :, :3]
    if scale != 1.0:
        rgb = resize(rgb, int(rgb.shape[1] * scale), int(rgb.shape[0] * scale))
    save_png(np.clip(rgb, 0, 1), path, to_srgb=True)


def log(*a):
    print("[fx]", *a, flush=True)
