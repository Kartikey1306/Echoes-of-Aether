"""
Rain sprites rendered in Cycles with real motion blur, plus the ground impact rings (numpy).

  Rain/rain_streaks_atlas.png  512x512, 8 columns (64x512): a water drop (glass, IOR 1.33) falling through one shutter
                               interval in a camera-invisible neon environment -> R = refracted / reflected highlight,
                               A = motion-blurred coverage. Head at the TOP of each column (v = 1), tail at the bottom.
                               Variants: standard, thin, fat, wobbling, double, short, bead-trail, heavy (bright head).
  Rain/rain_drips.png          256x256, 2x2: hanging teardrop, falling drop, drizzle cluster, stretched drip.
  Rain/rain_ring_4x4.png       512x512, 4x4 flipbook (128 px): impact ring on a wet surface expanding and fading.

Usage: Blender -b -P rain_sprites.py -- [--samples 48]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import fxkit as K  # noqa: E402


def neon_world():
    """Environment seen only by reflection / refraction: dark with bright neon strips and lamp spots."""
    w = bpy.context.scene.world
    nt = w.node_tree
    nt.nodes.clear()
    nb = K.NB(nt)
    out = nb.n("ShaderNodeOutputWorld")
    tc = nb.n("ShaderNodeTexCoord")
    gen = tc.outputs["Generated"]
    n1, _ = nb.noise(gen, scale=6.0, detail=1, rough=0.5)
    n2, c2 = nb.noise(gen, scale=14.0, detail=0, rough=0.5, w=3.0, dims="4D")
    spots = nb.math("ADD", nb.smooth(0.62, 0.68, n1), nb.math("MULTIPLY", nb.smooth(0.7, 0.74, n2), 2.0))
    col = nb.vmath("ADD", nb.vmath("SCALE", (0.4, 0.8, 1.0), scale=spots), (0.02, 0.025, 0.035))
    col = nb.vmath("ADD", col, nb.vmath("SCALE", (1.0, 0.3, 0.8), scale=nb.smooth(0.72, 0.75, n1)))
    bg = nb.n("ShaderNodeBackground")
    nb.link(col, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 6.0
    lp = nb.n("ShaderNodeLightPath")
    black = nb.n("ShaderNodeBackground", inputs={0: (0, 0, 0, 1), 1: 0.0})
    mix = nb.n("ShaderNodeMixShader")
    nb.link(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nb.link(bg.outputs[0], mix.inputs[1])
    nb.link(black.outputs[0], mix.inputs[2])
    nb.link(mix.outputs[0], out.inputs["Surface"])


def water(name, mask):
    if mask:
        return K.emission_material(name, (1, 1, 1, 1), 1.0)
    m, nb, out = K.new_material(name)
    g = nb.n("ShaderNodeBsdfGlass", inputs={"IOR": 1.333, "Roughness": 0.02})
    nb.link(g.outputs[0], out.inputs["Surface"])
    return m


def drop(name, radius, mask, teardrop=False, stretch=1.0):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=24, ring_count=16, location=(0, 0, 0))
    ob = bpy.context.object
    ob.name = name
    for v in ob.data.vertices:
        x, y, z = v.co
        if teardrop and z > 0:
            k = (1 - z / radius) ** 1.4
            v.co = (x * k, y * k, z * 2.4)
        else:
            v.co = (x, y, z * stretch)
    bpy.ops.object.shade_smooth()
    ob.data.materials.append(water(name + "_m", mask))
    return ob


def key_path(ob, pts):
    """pts: list of (frame, (x, y, z)); Bezier keys (fractional frames allowed)."""
    ob.animation_data_create()
    act = bpy.data.actions.new(ob.name + "_act")
    ob.animation_data.action = act
    for i in range(3):
        fc = None
        try:
            fc = act.fcurves.new("location", index=i)
        except Exception:
            pass
        if fc is None:
            # Blender 5 layered actions: fall back to keyframe_insert
            for f, p in pts:
                ob.location = p
                ob.keyframe_insert("location", frame=f)
            return
        for f, p in pts:
            fc.keyframe_points.insert(f, p[i]).interpolation = "BEZIER"


def setup_mblur():
    sc = bpy.context.scene
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 1.0
    try:
        sc.render.motion_blur_position = "CENTER"
    except Exception:
        pass
    sc.frame_set(2)


STREAKS = [
    # radius (fraction of cell width), path wobble, double, travel fraction, ease (head brightness), bead trail
    dict(r=0.17, wob=0.0, dbl=False, travel=0.86, ease=0.15, beads=False),
    dict(r=0.11, wob=0.0, dbl=False, travel=0.9, ease=0.0, beads=False),
    dict(r=0.24, wob=0.0, dbl=False, travel=0.82, ease=0.25, beads=False),
    dict(r=0.15, wob=0.22, dbl=False, travel=0.86, ease=0.1, beads=False),
    dict(r=0.13, wob=0.0, dbl=True, travel=0.86, ease=0.1, beads=False),
    dict(r=0.18, wob=0.0, dbl=False, travel=0.45, ease=0.3, beads=False),
    dict(r=0.15, wob=0.08, dbl=False, travel=0.88, ease=0.0, beads=True),
    dict(r=0.22, wob=0.0, dbl=False, travel=0.84, ease=0.5, beads=False),
]


def streak(i, spec, mask, spp):
    sc = K.reset()
    neon_world()
    W, H = 1.0, 8.0        # cell in drop-space units (64 x 512 px)
    rng = np.random.default_rng(100 + i)
    objs = []
    count = 2 if spec["dbl"] else 1
    for k in range(count):
        r = spec["r"] * W * (0.75 if k else 1.0)
        ob = drop(f"drop{k}", r, mask, stretch=1.08)
        top = H / 2 - r * 1.3 - (k * 0.9)
        bottom = top - H * spec["travel"]
        x0 = (k - 0.5) * 0.28 if count > 1 else 0.0
        wob = spec["wob"] * W
        e = spec["ease"]
        pts = []
        steps = 5
        for s in range(steps):
            u = s / (steps - 1)
            # ease-out toward the head: more time near the top => brighter head
            ue = u if e == 0 else 1 - (1 - u) ** (1 + e * 2)
            z = bottom + (top - bottom) * ue
            x = x0 + wob * math.sin(u * math.pi * 1.6 + rng.random() * 3)
            pts.append((1.5 + u, (x, 0.0, z)))
        key_path(ob, pts)
        objs.append(ob)
        if spec["beads"]:
            # little droplets left along the track (static, faint)
            for b in range(5):
                z = bottom + (top - bottom) * (0.12 + 0.17 * b) + rng.normal(0, 0.15)
                d = drop(f"bead{b}", r * (0.25 + rng.random() * 0.2), mask)
                d.location = (x0 + rng.normal(0, 0.05), 0, z)
    setup_mblur()
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            try:
                ob.cycles.motion_steps = 3
            except Exception:
                pass
    K.camera("Cam", (0, -10, 0), (math.pi / 2, 0, 0), kind="ORTHO", ortho_scale=H)
    K.setup_cycles((64, 512), samples=spp, transparent=True, denoise=False, bounces=6, adaptive=0)
    return K.load(K.render(os.path.join(K.OUT, f"streak_{i}_{'m' if mask else 'c'}.exr")))


def streak_atlas(spp):
    cols = []
    for i, spec in enumerate(STREAKS):
        c = streak(i, spec, False, spp)
        m = streak(i, spec, True, spp)
        cov = m[:, :, 0]
        cov = cov / max(1e-6, np.percentile(cov, 99.8))
        hl = c[:, :, 0] * 0.2126 + c[:, :, 1] * 0.7152 + c[:, :, 2] * 0.0722
        hl = hl / max(1e-6, np.percentile(hl, 99.5))
        # highlight relative to coverage (where the drop is), soft
        cols.append(np.stack([np.clip(hl, 0, 1)] * 3 + [np.clip(cov, 0, 1)], -1))
        K.log("streak", i, "cov mean", float(cov.mean()))
    atlas = np.concatenate(cols, axis=1)
    K.save_png(atlas, os.path.join(K.UNITY_FX, "Rain", "rain_streaks_atlas.png"))
    prev = atlas.copy()
    prev[:, :, :3] = (0.4 + 0.6 * prev[:, :, :3]) * prev[:, :, 3:4] * np.array([0.75, 0.85, 1.0])
    K.contact_sheet(prev, os.path.join(K.PREV, "rain_streaks_preview.png"))


def drip_cell(kind, mask, spp):
    sc = K.reset()
    neon_world()
    rng = np.random.default_rng(7 + kind)
    if kind == 0:
        drop("tear", 0.42, mask, teardrop=True).location = (0, 0, -0.35)
    elif kind == 1:
        ob = drop("fall", 0.33, mask, stretch=1.1)
        key_path(ob, [(1.5, (0, 0, -0.35)), (2.5, (0, 0, 0.25))])
    elif kind == 2:
        for k in range(5):
            d = drop(f"d{k}", 0.08 + rng.random() * 0.1, mask)
            d.location = (rng.normal(0, 0.35), 0, rng.normal(0, 0.45))
    else:
        ob = drop("long", 0.26, mask, teardrop=True)
        key_path(ob, [(1.5, (0, 0, -0.75)), (2.5, (0, 0, 0.45))])
    setup_mblur()
    K.camera("Cam", (0, -10, 0), (math.pi / 2, 0, 0), kind="ORTHO", ortho_scale=2.2)
    K.setup_cycles((128, 128), samples=spp, transparent=True, denoise=False, bounces=6, adaptive=0)
    return K.load(K.render(os.path.join(K.OUT, f"drip_{kind}_{'m' if mask else 'c'}.exr")))


def drips(spp):
    cells = []
    for k in range(4):
        c = drip_cell(k, False, spp)
        m = drip_cell(k, True, spp)
        cov = np.clip(m[:, :, 0] / max(1e-6, m[:, :, 0].max()), 0, 1)
        hl = c[:, :, 0] * 0.2126 + c[:, :, 1] * 0.7152 + c[:, :, 2] * 0.0722
        hl = np.clip(hl / max(1e-6, np.percentile(hl, 99.5)), 0, 1)
        cells.append(np.stack([hl] * 3 + [cov], -1))
    at = K.atlas(cells, 2, 2)
    K.save_png(at, os.path.join(K.UNITY_FX, "Rain", "rain_drips.png"))
    prev = at.copy()
    prev[:, :, :3] = (0.35 + 0.65 * prev[:, :, :3]) * prev[:, :, 3:4]
    K.contact_sheet(prev, os.path.join(K.PREV, "rain_drips_preview.png"))


def rings():
    """Impact ring flipbook: a thin bright crest expanding and fading, a faint second crest, a centre dimple."""
    n, frames = 128, 16
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float32)
    d = np.hypot((xs + 0.5) / n - 0.5, (ys + 0.5) / n - 0.5) * 2      # 0 centre .. 1 edge
    out = []
    for f in range(frames):
        u = (f + 0.5) / frames
        r1 = 0.08 + 0.82 * (1 - (1 - u) ** 1.8)
        r2 = r1 * 0.62
        w = 0.035 + 0.03 * u
        a1 = np.exp(-np.square((d - r1) / w)) * (1 - u) ** 1.2
        a2 = np.exp(-np.square((d - r2) / (w * 0.8))) * (1 - u) ** 1.6 * 0.5
        c = np.exp(-np.square(d / 0.08)) * max(0.0, 1 - u * 4) * 0.8
        a = np.clip(a1 + a2 + c, 0, 1) * (d < 0.98)
        hl = np.clip(a1 * 1.2 + a2 + c * 0.5, 0, 1)
        out.append(np.stack([hl] * 3 + [a], -1))
    at = K.atlas(out, 4, 4)
    K.save_png(at, os.path.join(K.UNITY_FX, "Rain", "rain_ring_4x4.png"))


def main():
    if "--post" in K.args():
        post_smooth()
        return
    spp = int(K.flag("--samples", 48))
    rings()
    streak_atlas(spp)
    drips(spp)
    post_smooth()


def smooth_axis(a, sigma, axis):
    """1D gaussian along one axis (zero padded)."""
    r = int(math.ceil(sigma * 3))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), axis, a)


def post_smooth():
    """Remove motion-blur sampling grain: strong blur along the streaks, light across; light blur on drips."""
    p = os.path.join(K.UNITY_FX, "Rain", "rain_streaks_atlas.png")
    a = K.load(p)
    a = smooth_axis(smooth_axis(a, 3.0, 0), 0.6, 1)
    K.save_png(np.clip(a, 0, 1), p)
    p = os.path.join(K.UNITY_FX, "Rain", "rain_drips.png")
    d = K.load(p)
    d = K.blur(d, 0.9)
    K.save_png(np.clip(d, 0, 1), p)
    prev = a.copy()
    prev[:, :, :3] = (0.4 + 0.6 * prev[:, :, :3]) * prev[:, :, 3:4] * np.array([0.75, 0.85, 1.0])
    K.contact_sheet(prev, os.path.join(K.PREV, "rain_streaks_preview.png"))


if __name__ == "__main__":
    main()
