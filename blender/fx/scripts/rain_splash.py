"""
Crown splash flipbook (raindrop hitting a wet street), procedural geometry per frame rendered in Cycles.

Per frame t (0..1 over the splash's life): a thin crown sheet (surface of revolution) rises and flares outward, its rim
broken into 12-16 jets of random height whose tips pinch off into droplets flying out on ballistic arcs; late in the
life a central Worthington jet rises with a droplet on top while the crown collapses. Water is a glass BSDF in a
camera-invisible neon environment (R = highlight), coverage from an emission pass (A); slight motion blur.
Camera 14 deg above the ground (reads as a side-on splash from street level; drawn as vertical billboards).

  Rain/rain_splash_4x4.png   1024x1024, 16 frames (256 px), frame i at column i % 4, row i // 4 from the top.

Usage: Blender -b -P rain_splash.py -- [--samples 32]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
import fxkit as K  # noqa: E402
from rain_sprites import neon_world, water  # noqa: E402

FRAMES = 16
RNG = np.random.default_rng(31)
JETS = 15
JET_ANG = np.sort(RNG.random(JETS) * 2 * math.pi)
JET_H = 0.55 + RNG.random(JETS) * 0.6
JET_LAUNCH = 0.28 + RNG.random(JETS) * 0.18
JET_SPEED = 0.9 + RNG.random(JETS) * 0.6


def crown(t, mask):
    """Crown sheet: rings x segments, radius flares with height, rim height modulated by the jets."""
    segs, rows = 96, 10
    R = 0.18 + 0.95 * (1 - (1 - t) ** 1.7)            # base radius grows fast then slows
    Hc = 0.62 * math.sin(math.pi * min(1.0, t * 1.25) ** 0.75)   # rises then collapses
    if Hc <= 0.01:
        return None
    bm = bmesh.new()
    grid = []
    for j in range(rows + 1):
        v = j / rows
        ring = []
        for i in range(segs):
            a = i / segs * 2 * math.pi
            # jets: narrow bumps on the rim
            dj = np.minimum(np.abs(a - JET_ANG), 2 * math.pi - np.abs(a - JET_ANG))
            bump = float(np.max(JET_H * np.exp(-np.square(dj / 0.09)) * (1 - min(1.0, max(0.0, (t - JET_LAUNCH.min()) * 1.6)) * 0.6)))
            h = Hc * (1 + 0.55 * bump) * v
            r = R * (1 + 0.32 * v ** 1.6) + 0.02 * math.sin(a * 7 + t * 5)
            ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), h)))
        grid.append(ring)
    for j in range(rows):
        for i in range(segs):
            bm.faces.new((grid[j][i], grid[j][(i + 1) % segs], grid[j + 1][(i + 1) % segs], grid[j + 1][i]))
    me = bpy.data.meshes.new("crown")
    bm.to_mesh(me)
    bm.free()
    ob = K.link(bpy.data.objects.new("crown", me))
    mod = ob.modifiers.new("thick", "SOLIDIFY")
    mod.thickness = 0.025
    ob.modifiers.new("smooth", "SUBSURF").levels = 1
    for p in me.polygons:
        p.use_smooth = True
    ob.data.materials.append(water("crown_m", mask))
    return ob


def sphere(name, loc, r, mask, stretch=1.0, vel=None):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=12, ring_count=8, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.scale = (1, 1, stretch)
    bpy.ops.object.shade_smooth()
    ob.data.materials.append(water(name + "_m", mask))
    if vel is not None:
        # motion blur: tiny keyed move around frame 2
        ob.animation_data_create()
        for f, k in ((1.75, -0.25), (2.25, 0.25)):
            ob.location = (loc[0] + vel[0] * k * 0.03, loc[1] + vel[1] * k * 0.03, loc[2] + vel[2] * k * 0.03)
            ob.keyframe_insert("location", frame=f)
    return ob


def frame(f, mask, spp):
    K.reset()
    neon_world()
    t = (f + 0.5) / FRAMES
    crown(t, mask)
    g = -9.0
    # droplets pinched off the jets
    for i in range(JETS):
        if t < JET_LAUNCH[i]:
            continue
        dt = t - JET_LAUNCH[i]
        a = JET_ANG[i]
        R0 = 0.18 + 0.95 * (1 - (1 - JET_LAUNCH[i]) ** 1.7)
        h0 = 0.62 * (1 + 0.55 * JET_H[i])
        vo, vu = 0.85 * JET_SPEED[i], 2.0 * JET_SPEED[i]
        r = R0 * 1.3 + vo * dt
        z = h0 + vu * dt + 0.5 * g * dt * dt
        if z < 0.0:
            continue
        sz = 0.045 + 0.03 * JET_H[i]
        sphere(f"drop{i}", (r * math.cos(a), r * math.sin(a), z), sz, mask, 1.25, (vo * math.cos(a), vo * math.sin(a), vu + g * dt))
        # some jets throw a second smaller droplet
        if i % 3 == 0:
            r2 = r * 0.82
            z2 = z * 0.85
            sphere(f"drop{i}b", (r2 * math.cos(a + 0.05), r2 * math.sin(a + 0.05), z2), sz * 0.6, mask)
    # Worthington jet
    if t > 0.5:
        u = (t - 0.5) / 0.5
        jh = 0.9 * math.sin(math.pi * min(1.0, u * 1.2))
        if jh > 0.03:
            bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=0.09, radius2=0.025, depth=jh, location=(0, 0, jh / 2))
            ob = bpy.context.object
            bpy.ops.object.shade_smooth()
            ob.data.materials.append(water("jet_m", mask))
            sphere("jettop", (0, 0, jh + 0.06 + u * 0.25), 0.06, mask, 1.2)
    sc = bpy.context.scene
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5
    sc.frame_set(2)
    # camera: 14 deg above the ground, looking at the splash centre
    el = math.radians(14)
    dist = 12.0
    K.camera("Cam", (0, -dist * math.cos(el), dist * math.sin(el) + 0.55), (math.pi / 2 - el, 0, 0), kind="ORTHO", ortho_scale=3.4)
    K.setup_cycles((256, 256), samples=spp, transparent=True, denoise=False, bounces=8, adaptive=0)
    return K.load(K.render(os.path.join(K.OUT, f"splash_{f}_{'m' if mask else 'c'}.exr")))


def main():
    spp = int(K.flag("--samples", 32))
    cells = []
    for f in range(FRAMES):
        c = frame(f, False, spp)
        m = frame(f, True, spp)
        cov = np.clip(m[:, :, 0], 0, 1)
        hl = c[:, :, 0] * 0.2126 + c[:, :, 1] * 0.7152 + c[:, :, 2] * 0.0722
        cells.append((hl, cov))
        K.log("splash frame", f)
    norm = max(1e-6, np.percentile(np.concatenate([h[c > 0.05] for h, c in cells if (c > 0.05).any()]), 99))
    frames = []
    for i, (hl, cov) in enumerate(cells):
        u = (i + 0.5) / FRAMES
        fade = 1.0 if u < 0.7 else 1 - (u - 0.7) / 0.3 * 0.85
        h = np.clip(0.35 * cov + 0.65 * hl / norm, 0, 1)
        frames.append(np.stack([h] * 3 + [cov * fade], -1))
    at = K.atlas(frames, 4, 4)
    K.save_png(at, os.path.join(K.UNITY_FX, "Rain", "rain_splash_4x4.png"))
    prev = at.copy()
    prev[:, :, :3] = prev[:, :, :3] * prev[:, :, 3:4] * np.array([0.75, 0.88, 1.0])
    K.contact_sheet(prev, os.path.join(K.PREV, "rain_splash_preview.png"), scale=0.5)


if __name__ == "__main__":
    main()
