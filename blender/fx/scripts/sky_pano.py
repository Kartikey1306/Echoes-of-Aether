"""
Night storm sky panorama (equirectangular) for the outdoor city zones.

A 80 km volumetric storm deck (cloud base ~650-1100 m, rolling underside, ragged scud) over a 80 km emissive city
plane: cool teal/white street light everywhere, a magenta district toward the Arcology Gate (Unity -X), amber
sodium industry (Unity +Z) and a cyan port (Unity +X/-Z). A low haze layer scatters the city light into a glow
dome on the horizon; the moon sits behind the deck (elevation ~34 deg) and only shows as a soft glow where the
clouds thin. Two passes:
  color  RGB radiance (linear EXR)
  flash  the deck lit only from above by a uniform bright source (how much a lightning flash inside / above the
         clouds shows through each direction): stored in the PNG alpha channel.

Usage:
  Blender -b -P sky_pano.py -- --pass color --res 1024 512 --samples 32       (preview)
  Blender -b -P sky_pano.py -- --pass color --res 4096 2048 --samples 96
  Blender -b -P sky_pano.py -- --pass flash --res 1024 512 --samples 48
  Blender -b -P sky_pano.py -- --post        (tone map + pack -> Assets/Art/FX/Resources/FX/Sky/sky_storm_pano.png)
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import fxkit as K  # noqa: E402

HALF = 40000.0          # deck half extent (m)
BASE, TOP = 650.0, 2900.0
CAM_Z = 40.0
MOON_AZ, MOON_EL = 28.0, 34.0
DENSITY = 0.007
# where the moon's line of sight crosses the middle of the deck (~1500 m)
MOON_XY = (1500.0 / math.tan(math.radians(MOON_EL)) * math.sin(math.radians(MOON_AZ)),
           1500.0 / math.tan(math.radians(MOON_EL)) * math.cos(math.radians(MOON_AZ)))

# Districts (Blender xy = Unity x, z). Colours are linear radiance multipliers for the ground plane.
DISTRICTS = [
    # centre (bx, by), radius m, colour, weight
    ((-9000, 1600), 4200, (1.0, 0.16, 0.55), 0.6),    # magenta: Arcology Gate (Unity -X)
    ((-15000, -7000), 6000, (0.55, 0.25, 0.9), 0.3),   # violet spill
    ((2500, 12000), 5000, (1.0, 0.52, 0.16), 0.8),    # amber sodium industry (Unity +Z)
    ((11000, -8000), 6000, (0.25, 0.85, 1.0), 1.1),    # cyan port (Unity +X / -Z)
    ((-6000, 13000), 6500, (0.3, 0.8, 0.85), 0.6),     # teal (Unity -X / +Z)
    ((-3000, -14000), 7000, (0.35, 0.65, 1.0), 0.55),  # cool blue residential
    ((15000, 9000), 6000, (0.9, 0.3, 0.75), 0.25),     # far pink
]


def build_city(nb_flash=False):
    """Emissive ground: patchy cool street light + district blobs."""
    m, nb, out = K.new_material("City")
    tc = nb.n("ShaderNodeTexCoord")
    P = tc.outputs["Object"]
    px, py, pz = nb.sep(P)
    # fine-ish patchiness of the street grid light (blocks, parks, dark water)
    f1, _ = nb.noise(P, scale=1 / 2600.0, detail=6, rough=0.62)
    f2, _ = nb.noise(P, scale=1 / 700.0, detail=3, rough=0.5, w=3.0, dims="4D")
    patch = nb.math("MULTIPLY", nb.smooth(0.4, 0.62, f1), nb.remap(f2, 0.3, 0.7, 0.4, 1.4))
    # the camera's own district is dim (dark zenith); the glow grows with distance into a ring on the horizon
    rr = nb.vmath("LENGTH", nb.xyz(px, py, 0.0))
    ring = nb.math("ADD", nb.math("MULTIPLY", nb.smooth(3500.0, 17000.0, rr), 1.0), 0.015)
    base_col = nb.vmath("SCALE", (0.36, 0.6, 0.88), scale=nb.math("MULTIPLY", nb.math("MULTIPLY", patch, ring), 1.0))
    acc = base_col
    for (cx, cy), r, col, w in DISTRICTS:
        d = nb.vmath("DISTANCE", P, (cx, cy, 0.0))
        q = nb.math("DIVIDE", d, r)
        g = nb.math("EXPONENT", nb.math("MULTIPLY", nb.math("POWER", q, 2.0), -1.0))
        # districts are lumpy, not perfect blobs
        fx, _ = nb.noise(P, scale=1 / 1500.0, detail=4, rough=0.6, w=cx * 0.001, dims="4D")
        g = nb.math("MULTIPLY", g, nb.remap(fx, 0.3, 0.7, 0.35, 1.5))
        acc = nb.vmath("ADD", acc, nb.vmath("SCALE", col, scale=nb.math("MULTIPLY", g, w)))
    em = nb.n("ShaderNodeEmission")
    nb.link(acc, em.inputs["Color"])
    em.inputs["Strength"].default_value = 0.0 if nb_flash else 1.0
    nb.link(em.outputs[0], out.inputs["Surface"])
    ob = K.plane("City", (0, 0, 0), (HALF * 2, HALF * 2))
    ob.data.materials.append(m)
    return ob


def build_deck():
    m, nb, out = K.new_material("Deck")
    tc = nb.n("ShaderNodeTexCoord")
    P = tc.outputs["Object"]
    # domain warp (big billows)
    _, wcol = nb.noise(P, scale=1 / 3200.0, detail=3, rough=0.5)
    warp = nb.vmath("SCALE", nb.vmath("SUBTRACT", wcol, (0.5, 0.5, 0.5)), scale=1600.0)
    Pw = nb.vmath("ADD", P, warp)
    px, py, pz = nb.sep(P)

    def sn(x):   # fBm (~0.5 +- 0.15) -> -1..1
        return nb.remap(x, 0.32, 0.68, -1.0, 1.0)

    # coverage: large storm cells with a few lanes of broken cloud
    cov, _ = nb.noise(nb.vmath("MULTIPLY", Pw, (1 / 8000.0, 1 / 8000.0, 1 / 3000.0)), scale=1.0, detail=5, rough=0.55)
    covn = nb.remap(cov, 0.3, 0.62, 0.0, 1.0)
    # base height: low under the cells
    bnoise, _ = nb.noise(nb.vmath("MULTIPLY", P, (1 / 3500.0, 1 / 3500.0, 0.0)), scale=1.0, detail=4, rough=0.5, w=7.0, dims="4D")
    base = nb.math("ADD", nb.math("MULTIPLY", sn(bnoise), -260.0), BASE + 380.0)
    base = nb.math("SUBTRACT", base, nb.math("MULTIPLY", covn, 180.0))
    # rolls (sheared along one axis), lumps and fine cauliflower detail on the underside
    roll, _ = nb.noise(nb.vmath("MULTIPLY", Pw, (1 / 800.0, 1 / 2000.0, 1 / 450.0)), scale=1.0, detail=6, rough=0.6)
    det, _ = nb.noise(Pw, scale=1 / 170.0, detail=4, rough=0.55, w=2.0, dims="4D")
    det2, _ = nb.noise(Pw, scale=1 / 50.0, detail=3, rough=0.5, w=5.0, dims="4D")
    relief = nb.math("ADD", nb.math("MULTIPLY", sn(roll), 300.0), nb.math("MULTIPLY", sn(det), 110.0))
    relief = nb.math("ADD", relief, nb.math("MULTIPLY", sn(det2), 35.0))
    zb = nb.math("SUBTRACT", nb.math("SUBTRACT", pz, base), relief)       # metres above the local base
    bottom = nb.smooth(0.0, 45.0, zb)
    thick = nb.math("ADD", nb.math("MULTIPLY", covn, 1500.0), 350.0)
    topf = nb.math("SUBTRACT", 1.0, nb.smooth(0.0, 1.0, nb.math("DIVIDE", zb, thick)))
    profile = nb.math("MULTIPLY", bottom, topf)
    # inside: density varies with coverage and the lumps (thin = dim, thick = bright from below)
    inner = nb.math("ADD", nb.math("MULTIPLY", covn, 1.1), nb.math("MULTIPLY", sn(det), 0.25))
    shape = nb.smooth(0.18, 0.62, inner)
    # thinner cloud around the moon's line of sight (the moon glows through, never shows a hard disc)
    md = nb.vmath("DISTANCE", nb.xyz(px, py, 0.0), (MOON_XY[0], MOON_XY[1], 0.0))
    thin = nb.math("ADD", nb.math("MULTIPLY", nb.smooth(500.0, 2800.0, md), 0.85), 0.15)
    dens = nb.math("MULTIPLY", nb.math("MULTIPLY", nb.math("MULTIPLY", shape, profile), DENSITY), thin)
    # ragged scud hanging below the base (wispy, sheared)
    scud, _ = nb.noise(nb.vmath("MULTIPLY", Pw, (1 / 600.0, 1 / 1400.0, 1 / 150.0)), scale=1.0, detail=6, rough=0.65, w=11.0, dims="4D")
    scud_h = nb.math("SUBTRACT", 1.0, nb.smooth(0.0, 140.0, nb.math("ABSOLUTE", nb.math("SUBTRACT", pz, nb.math("SUBTRACT", base, 230.0)))))
    scud_d = nb.math("MULTIPLY", nb.math("MULTIPLY", nb.smooth(0.62, 0.8, scud), scud_h), DENSITY * 0.8)
    dens = nb.math("ADD", dens, scud_d)
    pv = nb.n("ShaderNodeVolumePrincipled")
    pv.inputs["Color"].default_value = (0.7, 0.74, 0.8, 1)
    pv.inputs["Anisotropy"].default_value = 0.3
    pv.inputs["Absorption Color"].default_value = (0.02, 0.02, 0.025, 1)
    nb.link(dens, pv.inputs["Density"])
    nb.link(pv.outputs[0], out.inputs["Volume"])
    ob = K.box("Deck", (0, 0, (BASE + TOP) / 2 - 200), (HALF * 2, HALF * 2, TOP - BASE + 900))
    ob.data.materials.append(m)
    return ob


def build_haze(flash):
    """Low haze between the city and the deck: scatters the street light into a horizon glow dome."""
    m, nb, out = K.new_material("Haze")
    tc = nb.n("ShaderNodeTexCoord")
    _, _, pz = nb.sep(tc.outputs["Object"])
    d = nb.math("MULTIPLY", nb.math("EXPONENT", nb.math("MULTIPLY", pz, -1 / 420.0)), 0.00011 if not flash else 0.0)
    sv = nb.n("ShaderNodeVolumeScatter")
    sv.inputs["Color"].default_value = (0.75, 0.82, 0.92, 1)
    sv.inputs["Anisotropy"].default_value = 0.2
    nb.link(d, sv.inputs["Density"])
    nb.link(sv.outputs[0], out.inputs["Volume"])
    ob = K.box("Haze", (0, 0, 330), (HALF * 2, HALF * 2, 640))
    ob.data.materials.append(m)
    return ob


def build(passname):
    sc = K.reset()
    flash = passname == "flash"
    build_city(nb_flash=flash)
    build_deck()
    build_haze(flash)
    wn = sc.world.node_tree.nodes
    bg = wn["Background"]
    if flash:
        # uniform bright sky above the deck: transmission of the deck from above
        bg.inputs[0].default_value = (1, 1, 1, 1)
        bg.inputs[1].default_value = 1.0
    else:
        # dark night sky above the clouds (seen only through breaks)
        bg.inputs[0].default_value = (0.004, 0.007, 0.016, 1)
        bg.inputs[1].default_value = 1.0
        # moon behind the deck
        ld = bpy.data.lights.new("Moon", "SUN")
        ld.energy = 0.1
        ld.color = (0.78, 0.86, 1.0)
        ld.angle = math.radians(0.6)
        mo = K.link(bpy.data.objects.new("Moon", ld))
        az, el = math.radians(MOON_AZ), math.radians(MOON_EL)   # azimuth from +Y toward +X
        d = (math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el))
        # sun points along its -Z: aim from the moon direction toward the origin
        import mathutils
        mo.rotation_euler = mathutils.Vector(d).to_track_quat("Z", "Y").to_euler()
    crop = K.flag("--crop")
    if crop:
        lo0, lo1, la0, la1 = [float(x) for x in crop.split(",")]
        K.pano_camera((0, 0, CAM_Z), lat=(la0, la1), lon=(lo0, lo1))
    else:
        K.pano_camera((0, 0, CAM_Z))


def main():
    a = K.args()
    if "--post" in a:
        post()
        return
    passname = K.flag("--pass", "color")
    res = (1024, 512)
    if "--res" in a:
        i = a.index("--res")
        res = (int(a[i + 1]), int(a[i + 2]))
    samples = int(K.flag("--samples", 32))
    build(passname)
    K.setup_cycles(res, samples=samples, denoise=True, bounces=2, step_rate=float(K.flag("--step", 1.0)), max_steps=1024)
    t = time.time()
    tag = "_" + K.flag("--tag") if K.flag("--tag") else ("_crop" if K.flag("--crop") else "")
    path = os.path.join(K.OUT, f"sky_pano_{passname}{tag}_{res[0]}.exr")
    K.render(path)
    K.log(f"rendered {path} in {time.time() - t:.1f}s")
    # quick look preview (exposed for the eye)
    img = K.load(path)[:, :, :3]
    prev = img if passname == "flash" else tonemap(img * 6.0)
    K.save_png(prev, os.path.join(K.PREV, f"sky_pano_{passname}{tag}_{res[0]}_raw.png"), to_srgb=True)


def tonemap(x):
    # gentle shoulder, keeps the darks linear (the sky is mostly very dark)
    return x / (1.0 + x * 0.6)


def post():
    """Pack color + flash into the final sky texture.

    RGB: sky radiance * EXPOSURE through a soft shoulder, sRGB encoded (dark gradients keep precision; dithered).
         Below the horizon the city plane is replaced by the haze colour (the game draws its own ground).
    A:   flash response (0..1) of the deck: how strongly each direction lights up when lightning fires above.
    """
    color = K.load(os.path.join(K.OUT, K.flag("--color", "sky_pano_color_final_4096.exr")))[:, :, :3]
    flash = K.load(os.path.join(K.OUT, K.flag("--flash", "sky_pano_flash_1024.exr")))[:, :, :3]
    W = color.shape[1]
    H = W // 2
    if color.shape[0] < H:
        # upper part only (lat -6..90): extend downward with the last row (replaced below the horizon anyway)
        pad = np.repeat(color[-1:], H - color.shape[0], axis=0)
        color = np.concatenate([color, pad], axis=0)
    if flash.shape[:2] != (H, W):
        flash = K.resize(flash, W, H)
    exposure = float(K.flag("--exposure", 9.0))
    c = color * exposure
    # elevation per row
    el = (0.5 - (np.arange(H) + 0.5) / H) * math.pi
    el = el[:, None, None]
    # below the horizon: fade to the horizon colour of the same column (blurred), then darken
    hrow = int(H * 0.5) - 3
    hz = K.blur(c[hrow - 6:hrow, :, :].mean(axis=0, keepdims=True).repeat(8, axis=0), 6, wrap=True).mean(axis=0, keepdims=True)
    below = np.clip(-el / math.radians(14.0), 0, 1)
    ground = hz * (1.0 - 0.75 * below)
    m = np.clip(-el / math.radians(0.6), 0, 1)
    c = c * (1 - m) + ground * m
    rgb = np.clip(tonemap(c), 0, 1)
    # flash response: luminance of the flash pass, normalised; zero below the horizon
    fl_l = flash[:, :, 0] * 0.2126 + flash[:, :, 1] * 0.7152 + flash[:, :, 2] * 0.0722
    fl_l = fl_l / max(1e-6, np.percentile(fl_l[: H // 2], 99.5))
    fl_l = np.clip(fl_l, 0, 1) * (1 - np.clip(-el[:, :, 0] / math.radians(1.0), 0, 1))
    out = np.concatenate([rgb, fl_l[:, :, None]], axis=2)
    dst = os.path.join(K.UNITY_FX, "Sky", "sky_storm_pano.png")
    K.save_png(out, dst, to_srgb=True)
    K.save_png(rgb, os.path.join(K.PREV, "sky_pano_final.png"), to_srgb=True)
    # a brighter "eye" preview to judge the cloud structure
    K.save_png(np.clip(tonemap(color * exposure * 3), 0, 1), os.path.join(K.PREV, "sky_pano_final_bright.png"), to_srgb=True)


if __name__ == "__main__":
    main()
