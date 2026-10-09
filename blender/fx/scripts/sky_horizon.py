"""
Far-far megacity silhouette band for the skybox (behind the in-game CyberCity skyline at 470-700 m).

~3000 procedural towers 2.4-12 km out (denser in a few megacity cores, a handful of 500-1100 m arcology spires),
dark facades with random lit windows (cool white / amber / cyan, a few magenta bands), red aircraft beacons on the
tall ones. Aerial perspective is analytic (Camera Data view distance, thicker low down) so far towers dissolve into
the sky behind them. Two renders through a 360 x 15 deg equirect strip (lat -3 .. 12):
  color: emitted light x transmittance     mask: coverage x transmittance  -> premultiplied RGBA
Output: Assets/Art/FX/Resources/FX/Sky/sky_city_band.png (4096x256, sRGB premultiplied).

Usage: Blender -b -P sky_horizon.py -- [--samples 48]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import fxkit as K  # noqa: E402

LAT = (-3.0, 12.0)
CAM_Z = 60.0
SIGMA = 0.00021
RNG = np.random.default_rng(77)


def towers():
    verts, faces, ids = [], [], []
    tops = []
    cores = [(-0.25 * math.pi, 1.0), (0.4 * math.pi, 0.8), (math.pi * 0.95, 0.9), (-0.7 * math.pi, 0.6), (0.05 * math.pi, 0.5)]
    n = 3000
    for i in range(n):
        # azimuth: uniform + clustered around the megacity cores
        if RNG.random() < 0.45:
            c, s = cores[RNG.integers(len(cores))]
            az = c + RNG.normal(0, 0.18 * s)
        else:
            az = RNG.random() * 2 * math.pi
        r = 2400 + (RNG.random() ** 0.8) * 9600
        h = float(np.clip(RNG.lognormal(math.log(100), 0.6), 25, 480))
        if RNG.random() < 0.012 and r > 6000:
            h = 520 + RNG.random() * 560
        w = 25 + RNG.random() * 70
        d = 25 + RNG.random() * 70
        cx, cy = r * math.sin(az), r * math.cos(az)
        yaw = RNG.random() * math.pi
        tiers = 1 if h < 150 or RNG.random() < 0.5 else 2 + int(RNG.random() * 2)
        z = 0.0
        for t in range(tiers):
            th = h * (0.55 if tiers > 1 and t == 0 else 1.0) if tiers == 1 else (h * 0.5 if t == 0 else h * 0.5 / (tiers - 1))
            k = 1.0 - 0.22 * t
            ca, sa = math.cos(yaw), math.sin(yaw)
            base = len(verts)
            for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                x, y = sx * w * 0.5 * k, sy * d * 0.5 * k
                verts.append((cx + x * ca - y * sa, cy + x * sa + y * ca, z))
            for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                x, y = sx * w * 0.5 * k, sy * d * 0.5 * k
                verts.append((cx + x * ca - y * sa, cy + x * sa + y * ca, z + th))
            b = base
            faces += [(b, b + 1, b + 5, b + 4), (b + 1, b + 2, b + 6, b + 5), (b + 2, b + 3, b + 7, b + 6), (b + 3, b + 0, b + 4, b + 7), (b + 4, b + 5, b + 6, b + 7)]
            z += th
        if h > 160:
            tops.append((cx, cy, z, h))
    ob = K.mesh_object("Towers", verts, faces)
    return ob, tops


def transmittance(nb):
    """exp(-sigma * distance * f(height)) from the camera's view distance."""
    cd = nb.n("ShaderNodeCameraData")
    tc = nb.n("ShaderNodeTexCoord")
    _, _, z = nb.sep(tc.outputs["Object"])
    f = nb.math("ADD", nb.math("MULTIPLY", nb.math("EXPONENT", nb.math("MULTIPLY", z, -1 / 260.0)), 0.9), 0.35)
    tau = nb.math("MULTIPLY", nb.math("MULTIPLY", cd.outputs["View Distance"], SIGMA), f)
    return nb.math("EXPONENT", nb.math("MULTIPLY", tau, -1.0)), z


def tower_material(mask):
    m, nb, out = K.new_material("Facade")
    T, z = transmittance(nb)
    if mask:
        e = nb.n("ShaderNodeEmission", inputs={0: (1, 1, 1, 1)})
        nb.link(T, e.inputs["Strength"])
        nb.link(e.outputs[0], out.inputs["Surface"])
        return m
    P = nb.n("ShaderNodeTexCoord").outputs["Object"]
    # window cells ~4 m x 3.6 m; lit at random (per cell white noise), 3 colours
    cells = nb.vmath("MULTIPLY", P, (1 / 4.0, 1 / 4.0, 1 / 3.6))
    wn = nb.n("ShaderNodeTexWhiteNoise", noise_dimensions="3D")
    nb.link(nb.vmath("FLOOR", cells), wn.inputs["Vector"])
    lit = nb.smooth(0.885, 0.9, wn.outputs["Value"])
    # block-scale variation: whole floors / towers darker or brighter
    blk, _ = nb.noise(P, scale=1 / 90.0, detail=2, rough=0.5)
    lit = nb.math("MULTIPLY", lit, nb.remap(blk, 0.35, 0.65, 0.2, 1.6))
    hue = wn.outputs["Color"]
    hs = nb.sep(hue)[0]
    col, _ = nb.ramp(hs, [(0.0, (1.0, 0.62, 0.3)), (0.45, (0.85, 0.9, 1.0)), (0.8, (0.45, 0.85, 1.0)), (0.97, (1.0, 0.25, 0.7))], interp="CONSTANT")
    # horizontal neon bands near the tops of some towers
    band = nb.math("MULTIPLY", nb.smooth(0.985, 0.99, nb.math("SINE", nb.math("MULTIPLY", z, 0.11))), nb.smooth(0.8, 0.85, wn.outputs["Value"]))
    em = nb.vmath("ADD", nb.vmath("SCALE", col, scale=nb.math("MULTIPLY", lit, 1.6)), nb.vmath("SCALE", (1.0, 0.2, 0.75), scale=nb.math("MULTIPLY", band, 4.0)))
    # facade itself: almost black, faintly lit from below by the street glow
    glow = nb.math("MULTIPLY", nb.math("EXPONENT", nb.math("MULTIPLY", z, -1 / 90.0)), 0.06)
    em = nb.vmath("ADD", em, nb.vmath("SCALE", (0.35, 0.45, 0.65), scale=glow))
    e = nb.n("ShaderNodeEmission")
    nb.link(em, e.inputs["Color"])
    nb.link(T, e.inputs["Strength"])
    nb.link(e.outputs[0], out.inputs["Surface"])
    return m


def beacons(tops, mask):
    for i, (x, y, z, h) in enumerate(tops):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=2.2 + h * 0.004, location=(x, y, z + 2), segments=8, ring_count=6)
        ob = bpy.context.object
        m, nb, out = K.new_material(f"Beacon{i}")
        T, _ = transmittance(nb)
        e = nb.n("ShaderNodeEmission", inputs={0: (1, 1, 1, 1) if mask else (1.0, 0.08, 0.05, 1)})
        nb.link(nb.math("MULTIPLY", T, 1.0 if mask else 60.0), e.inputs["Strength"])
        nb.link(e.outputs[0], out.inputs["Surface"])
        ob.data.materials.append(m)


def render(mask, spp):
    K.reset()
    ob, tops = towers()
    ob.data.materials.append(tower_material(mask))
    beacons(tops[:160], mask)
    K.pano_camera((0, 0, CAM_Z), lat=LAT)
    K.setup_cycles((4096, 256), samples=spp, transparent=True, denoise=False, bounces=0, adaptive=0)
    return K.load(K.render(os.path.join(K.OUT, f"sky_band_{'mask' if mask else 'color'}.exr")))


def main():
    spp = int(K.flag("--samples", 48))
    col = render(False, spp)
    RNG.bit_generator.state = np.random.default_rng(77).bit_generator.state
    msk = render(True, spp)
    a = np.clip(msk[:, :, 0], 0, 1)
    exposure = float(K.flag("--exposure", 0.35))
    rgb = col[:, :, :3] * exposure
    rgb = rgb / (1 + rgb * 0.5)
    rgb = np.minimum(rgb, a[:, :, None] * 1.5 + 1e-4)
    out = np.concatenate([np.clip(rgb, 0, 1), a[:, :, None]], -1)
    K.save_png(out, os.path.join(K.UNITY_FX, "Sky", "sky_city_band.png"), to_srgb=True)
    # preview over a stand-in sky gradient (2 strips)
    sky = np.linspace(0.03, 0.012, out.shape[0])[:, None, None] * np.array([0.6, 0.75, 1.0])
    comp = sky * (1 - a[:, :, None]) + out[:, :, :3]
    K.save_png(np.clip(np.concatenate([comp[:, :2048], comp[:, 2048:]], 0) * 3, 0, 1), os.path.join(K.PREV, "sky_band_preview.png"), to_srgb=True)


if __name__ == "__main__":
    main()
