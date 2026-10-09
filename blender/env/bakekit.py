"""Cycles bake pipeline: procedural node material -> float channel arrays -> Unity URP texture set.

Every channel is baked as an EMIT pass from a 1x1 plane (UV 0..1) into a float image, so values are exact
(no lighting). Height -> normal (OpenGL, +Y up) and height -> cavity AO are derived in numpy with wrap-around
so they stay perfectly tileable.
"""
import os
import time

import bpy
import numpy as np

import nodekit
import pngio

RES = 1024


def setup_cycles(samples=6):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type == "METAL"
        scene.cycles.device = "GPU"
    except Exception as e:  # pragma: no cover - CPU fallback
        print("[bake] GPU unavailable, using CPU:", e)
        scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.bake_type = "EMIT"
    scene.render.bake.margin = 0
    scene.render.bake.use_clear = True
    scene.view_settings.view_transform = "Standard"


def bake_plane():
    me = bpy.data.meshes.new("BakePlane")
    me.from_pydata([(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for li, (u, v) in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        uv.data[li].uv = (u, v)
    ob = bpy.data.objects.new("BakePlane", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


class Baker:
    def __init__(self, res=RES, samples=6):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        setup_cycles(samples)
        self.res = res
        self.ob = bake_plane()
        self.img = bpy.data.images.new("BakeTarget", res, res, alpha=True, float_buffer=True)
        self.img.colorspace_settings.name = "Non-Color"
        bpy.context.view_layer.objects.active = self.ob
        self.ob.select_set(True)

    def set_res(self, res):
        if res == self.res:
            return
        self.res = res
        old = self.img
        self.img = bpy.data.images.new(f"BakeTarget{res}", res, res, alpha=True, float_buffer=True)
        self.img.colorspace_settings.name = "Non-Color"
        bpy.data.images.remove(old)

    def new_material(self, name):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = 1.0
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = self.img
        nt.nodes.active = tex
        self.ob.data.materials.clear()
        self.ob.data.materials.append(mat)
        return mat, nodekit.NB(nt), em

    def bake(self, nb, em, sock):
        """Bake colour/float socket `sock` -> (res,res,3) float array, bottom row first."""
        if isinstance(sock, nodekit.S):
            sock = nb.gray(sock)
        elif isinstance(sock, (int, float)):
            sock = nb.gray(float(sock))
        for l in list(em.inputs["Color"].links):
            nb.links.remove(l)
        nb.links.new(sock, em.inputs["Color"])
        bpy.ops.object.bake(type="EMIT", use_clear=True, margin=0)
        a = np.empty(self.res * self.res * 4, np.float32)
        self.img.pixels.foreach_get(a)
        return a.reshape(self.res, self.res, 4)[:, :, :3].copy()


# ---------------------------------------------------------------------------------------------- post
def _blur(h, sigma_px):
    """Wrap-around gaussian blur via FFT."""
    n = h.shape[0]
    f = np.fft.fftfreq(n)
    g = np.exp(-2.0 * (np.pi * sigma_px) ** 2 * (f[:, None] ** 2 + f[None, :] ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(h) * g))


def height_to_normal(hm, px_m, strength=1.0):
    """hm: height in metres (bottom row first). Returns OpenGL tangent-space normal in [0,1] (bottom row first)."""
    dx = (np.roll(hm, -1, axis=1) - np.roll(hm, 1, axis=1)) / (2.0 * px_m)
    dy = (np.roll(hm, -1, axis=0) - np.roll(hm, 1, axis=0)) / (2.0 * px_m)
    nx, ny, nz = -dx * strength, -dy * strength, np.ones_like(hm)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / l, ny / l, nz / l], axis=-1) * 0.5 + 0.5


def cavity_ao(hm, px_m, radii_m=(0.004, 0.015, 0.05), strength=1.0):
    """Approximate AO from a height field: how far each texel sits below its blurred neighbourhood."""
    occ = np.zeros_like(hm)
    for r in radii_m:
        sig = max(0.6, r / px_m)
        d = _blur(hm, sig) - hm
        occ += np.clip(d / (r * 1.2), 0.0, 1.0) / len(radii_m)
    return np.clip(1.0 - occ * strength, 0.0, 1.0)


def save_set(out_dir, name, color=None, normal=None, mask=None, occl=None, emission=None, alpha=None):
    os.makedirs(out_dir, exist_ok=True)
    files = {}

    def w(suffix, arr):
        p = os.path.join(out_dir, f"{name}_{suffix}.png")
        pngio.write_png(p, arr[::-1])  # bottom-first -> top-first
        files[suffix] = os.path.basename(p)

    if color is not None:
        c = pngio.to_u8(pngio.linear_to_srgb(color))
        if alpha is not None:
            c = np.concatenate([c, pngio.to_u8(alpha)[..., None]], axis=-1)
        w("BaseColor", c)
    if normal is not None:
        w("Normal", pngio.to_u8(normal))
    if mask is not None:
        w("MaskMap", pngio.to_u8(mask))
    if occl is not None:
        w("Occlusion", pngio.to_u8(occl))
    if emission is not None:
        w("Emission", pngio.to_u8(pngio.linear_to_srgb(emission)))
    return files


def bake_masks(baker, nb, em, masks):
    """Bake a dict of float sockets three at a time -> dict of (res,res) arrays."""
    out = {}
    names = list(masks)
    for i in range(0, len(names), 3):
        grp = names[i:i + 3]
        socks = [masks[n] for n in grp] + [0.0] * (3 - len(grp))
        arr = baker.bake(nb, em, nb.pack3(*socks))
        for k, n in enumerate(grp):
            out[n] = arr[..., k].astype(np.float32)
    return out


def bake_material(baker, name, mdef, out_dir, tint_only=False):
    """Bake one material definition. Returns a dict describing what was written.

    Optional extras returned by define(): 'masks' {name: float socket} baked to arrays, and 'post' (callable)
    which receives a dict {color, rough, metal, h01, alpha, ao, emit, masks, px_m, tile, depth, res, params}
    (numpy, bottom row first; color linear RGB) and may modify/return it before maps are derived."""
    t0 = time.time()
    p = dict(mdef.get("params", {}))
    mat, nb, em = baker.new_material(name)
    ch = mdef["define"](nb, p)
    color = baker.bake(nb, em, ch["color"])
    info = {"name": name}
    tile = mdef["tile"]
    if tint_only:
        if "post" in ch:
            # tints run the same weathering post-process on colour (maps are shared with the parent)
            data = baker.bake(nb, em, nb.pack3(ch.get("rough", 0.5), ch.get("metal", 0.0), ch.get("height", 0.5)))
            st = {"color": color, "rough": data[..., 0], "metal": data[..., 1], "h01": data[..., 2], "alpha": None,
                  "ao": np.ones_like(data[..., 0]), "emit": None, "masks": bake_masks(baker, nb, em, ch.get("masks", {})),
                  "px_m": tile / baker.res, "tile": tile, "depth": mdef.get("depth", 0.003), "res": baker.res, "params": p}
            st = ch["post"](st) or st
            color = st["color"]
        files = save_set(out_dir, name, color=color, alpha=None)
        info["files"] = files
        print(f"[bake] {name} (tint) {time.time() - t0:.1f}s")
        return info
    rough = ch.get("rough", 0.5)
    metal = ch.get("metal", 0.0)
    height = ch.get("height", 0.5)
    data = baker.bake(nb, em, nb.pack3(rough if not isinstance(rough, float) else rough,
                                       metal if not isinstance(metal, float) else metal,
                                       height if not isinstance(height, float) else height))
    rough_a, metal_a, h01 = data[..., 0], data[..., 1], data[..., 2]
    alpha = None
    ao_extra = np.ones_like(h01)
    if "alpha" in ch or "ao" in ch:
        ex = baker.bake(nb, em, nb.pack3(ch.get("alpha", 1.0), ch.get("ao", 1.0), 0.0))
        if "alpha" in ch:
            alpha = np.clip(ex[..., 0], 0, 1)
        if "ao" in ch:
            ao_extra = np.clip(ex[..., 1], 0, 1)
    emission = None
    if "emit" in ch:
        emission = np.clip(baker.bake(nb, em, ch["emit"]), 0, 1)
    px_m = tile / baker.res
    if "post" in ch:
        st = {"color": color, "rough": rough_a, "metal": metal_a, "h01": h01, "alpha": alpha, "ao": ao_extra,
              "emit": emission, "masks": bake_masks(baker, nb, em, ch.get("masks", {})), "px_m": px_m, "tile": tile,
              "depth": mdef.get("depth", 0.003), "res": baker.res, "params": p}
        st = ch["post"](st) or st
        color, rough_a, metal_a, h01 = st["color"], st["rough"], st["metal"], st["h01"]
        alpha, ao_extra, emission = st["alpha"], st["ao"], st["emit"]
        color = np.clip(color, 0.0, 1.0)
    hm = h01 * mdef.get("depth", 0.003)
    normal = height_to_normal(hm, px_m, mdef.get("normal_strength", 1.0))
    ao = cavity_ao(hm, px_m, mdef.get("ao_radii", (0.004, 0.015, 0.05)), mdef.get("ao_strength", 1.0)) * ao_extra
    ao = np.clip(ao, 0, 1)
    mask = np.stack([np.clip(metal_a, 0, 1), ao, np.clip(h01, 0, 1), 1.0 - np.clip(rough_a, 0, 1)], axis=-1)
    files = save_set(out_dir, name, color=color, normal=normal, mask=mask, occl=ao, emission=emission, alpha=alpha)
    info.update({
        "files": files,
        "stats": {
            "rough_mean": float(rough_a.mean()), "metal_mean": float(metal_a.mean()),
            "albedo_mean_srgb": [float(x) for x in pngio.linear_to_srgb(color.reshape(-1, 3).mean(0))],
            "height_range": [float(h01.min()), float(h01.max())],
        },
    })
    print(f"[bake] {name} {time.time() - t0:.1f}s albedo~{info['stats']['albedo_mean_srgb']} rough~{info['stats']['rough_mean']:.2f}")
    return info
