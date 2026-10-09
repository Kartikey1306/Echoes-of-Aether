"""
Tileable low scud layer for the sky shader (parallax / scrolling over the storm deck).

A 3x3-tile volumetric slab (300-720 m) whose density is a SEAMLESS 4D-torus noise (period = one tile), rendered from
below with an orthographic camera covering exactly the centre tile, three times with different light:
  R  lit from below   (emissive city plane under the camera)   -> tinted in the shader by the deck's horizon glow
  G  lit from above   (sun straight down)                     -> lightning / moon showing through thin parts
  B  ambient          (uniform world)                         -> form shading
  A  coverage         (film alpha)
Output: Assets/Art/FX/Resources/FX/Sky/sky_clouds.png (2048^2, linear data).

Usage: Blender -b -P sky_clouds.py -- [--res 2048] [--samples 16]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import fxkit as K  # noqa: E402

T = 2000.0           # tile (m)
Z0, Z1 = 300.0, 760.0


def torus(nb, x, y, rx, ry):
    kx, ky = 2 * math.pi / T, 2 * math.pi / T
    ax, ay = nb.math("MULTIPLY", x, kx), nb.math("MULTIPLY", y, ky)
    v = nb.xyz(nb.math("MULTIPLY", nb.math("COSINE", ax), rx), nb.math("MULTIPLY", nb.math("SINE", ax), rx),
               nb.math("MULTIPLY", nb.math("COSINE", ay), ry))
    w = nb.math("MULTIPLY", nb.math("SINE", ay), ry)
    return v, w


def build(light):
    sc = K.reset()
    m, nb, out = K.new_material("Scud")
    P = nb.n("ShaderNodeTexCoord").outputs["Object"]
    x, y, z = nb.sep(P)
    # wind-sheared scud: fewer features along x (the wind) than across
    v1, w1 = torus(nb, x, y, 0.75, 1.7)
    _, wc = nb.noise(v1, scale=1.0, detail=2, rough=0.5, w=nb.math("ADD", w1, 3.0), dims="4D")
    wv = nb.vmath("SCALE", nb.vmath("SUBTRACT", wc, (0.5, 0.5, 0.5)), scale=0.9)
    big, _ = nb.noise(nb.vmath("ADD", v1, wv), scale=1.0, detail=6, rough=0.64, w=nb.math("ADD", w1, 0.5), dims="4D")
    v2, w2 = torus(nb, x, y, 4.0, 6.0)
    wz = nb.math("ADD", w2, nb.math("MULTIPLY", z, 1 / 120.0))
    det, _ = nb.noise(nb.vmath("ADD", v2, nb.vmath("SCALE", wv, scale=2.0)), scale=1.6, detail=5, rough=0.6, w=wz, dims="4D")
    cov = nb.remap(nb.math("ADD", big, nb.math("MULTIPLY", nb.math("SUBTRACT", det, 0.5), 0.55)), 0.53, 0.7, 0.0, 1.0)
    h = nb.math("DIVIDE", nb.math("SUBTRACT", z, Z0), Z1 - Z0)
    dd = nb.math("MULTIPLY", nb.math("SUBTRACT", det, 0.5), 0.6)
    prof = nb.math("MULTIPLY", nb.smooth(0.0, 0.25, nb.math("ADD", h, dd)),
                   nb.math("SUBTRACT", 1.0, nb.smooth(0.45, 1.0, nb.math("SUBTRACT", h, dd))))
    dens = nb.math("MULTIPLY", nb.math("MULTIPLY", nb.smooth(0.15, 0.85, cov), prof), 0.016)
    pv = nb.n("ShaderNodeVolumePrincipled")
    pv.inputs["Color"].default_value = (0.8, 0.82, 0.86, 1)
    pv.inputs["Anisotropy"].default_value = 0.3
    nb.link(dens, pv.inputs["Density"])
    nb.link(pv.outputs[0], out.inputs["Volume"])
    ob = K.box("Scud", (0, 0, (Z0 + Z1) / 2), (3 * T, 3 * T, Z1 - Z0 + 60))
    ob.data.materials.append(m)
    bg = sc.world.node_tree.nodes["Background"]
    if light == "below":
        p = K.plane("City", (0, 0, -2.0), (5 * T, 5 * T))
        p.data.materials.append(K.emission_material("CityE", (1, 1, 1, 1), 1.0))
    elif light == "above":
        ld = bpy.data.lights.new("Top", "SUN")
        ld.energy = 3.0
        ld.angle = math.radians(8)
        K.link(bpy.data.objects.new("Top", ld))   # default orientation points down (-Z)
    else:
        bg.inputs[0].default_value = (1, 1, 1, 1)
        bg.inputs[1].default_value = 1.0
    # camera below, looking up (+Z); covering the centre tile exactly
    K.camera("Up", (0, 0, 0.0), (0, 0, 0), kind="ORTHO", ortho_scale=T, clip=(0.1, 5000))
    bpy.context.scene.camera.rotation_euler = (math.pi, 0, 0)


def main():
    res = int(K.flag("--res", 2048))
    spp = int(K.flag("--samples", 16))
    post_only = "--post" in K.args()
    chans = []
    alpha = None
    for light in ("below", "above", "ambient"):
        path = os.path.join(K.OUT, f"sky_clouds_{light}.exr")
        if not post_only:
            build(light)
            K.setup_cycles((res, res), samples=spp, transparent=True, denoise=True, bounces=2)
            K.render(path)
        # periodic blur removes the low-sample grain without breaking the tiling
        img = K.blur(K.load(path), 1.1, wrap=True)
        lum = img[:, :, 0] * 0.2126 + img[:, :, 1] * 0.7152 + img[:, :, 2] * 0.0722
        a = np.clip(img[:, :, 3], 0, 1)
        # un-premultiply-free normalisation: radiance per unit coverage would blow up at the edges; keep premultiplied
        chans.append(lum / max(1e-6, np.percentile(lum, 99.7)))
        alpha = a if alpha is None else alpha
        K.log("scud pass", light, "mean a", float(a.mean()))
    out = np.stack([np.clip(c, 0, 1) for c in chans] + [alpha], -1)
    K.save_png(out, os.path.join(K.UNITY_FX, "Sky", "sky_clouds.png"))
    prev = np.stack([out[:, :, 0] * 0.5 + out[:, :, 2] * 0.3] * 3, -1) * np.array([0.6, 0.75, 1.0])
    K.contact_sheet(np.concatenate([prev, out[:, :, 3:4]], -1), os.path.join(K.PREV, "sky_clouds_preview.png"), scale=0.5)


if __name__ == "__main__":
    main()
