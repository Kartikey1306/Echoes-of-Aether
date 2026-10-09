"""
Soft volumetric steam / smoke flipbooks and a tileable mist sheet (Cycles volumes, procedural noise only).

  Smoke/steam_8x8.png   2048^2, 64 frames x 256 px (frame i: column i % 8, row i // 8 from the top): a steam puff over
                        its life - dense compact billow -> expanded wispy veil (bright, low absorption, grey = light).
  Smoke/smoke_8x8.png   2048^2, same layout: darker, denser smoke puff (low albedo, slower to thin out).
  Smoke/mist_tile.png   1024^2 tileable soft mist (4D torus noise), 4 slowly morphing frames in R, G, B, A.
RGB of the puffs = rendered lighting (key from above-left + ambient), A = opacity. Both render as ONE animation job
each (frame drivers), so the kernels load once.

Usage: Blender -b -P smoke.py -- [--samples 16] [--only steam|smoke|mist]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import fxkit as K  # noqa: E402

N = 64


def frame_value(nb, scale=1.0, offset=0.0):
    v = nb.n("ShaderNodeValue")
    d = v.outputs[0].driver_add("default_value").driver
    d.type = "SCRIPTED"
    d.expression = f"(frame - 1) / {N - 1} * {scale} + {offset}"
    return v.outputs[0]


def puff(kind, spp):
    sc = K.reset()
    m, nb, out = K.new_material("Puff")
    t = frame_value(nb)                               # 0..1 life
    P = nb.n("ShaderNodeTexCoord").outputs["Object"]
    smoke = kind == "smoke"
    # centre rises a little, radius grows with an ease-out
    R = nb.math("ADD", nb.math("MULTIPLY", nb.math("POWER", t, 0.6), 0.42), 0.5)
    c = nb.xyz(0.0, 0.0, nb.math("ADD", nb.math("MULTIPLY", t, 0.22), -0.2))
    q = nb.vmath("SUBTRACT", P, c)
    # billowy silhouette: radius displaced by low-frequency noise evolving in W
    w = nb.math("MULTIPLY", t, 1.6)
    n1, nc = nb.noise(q, scale=2.2, detail=3, rough=0.5, w=w, dims="4D")
    warp = nb.vmath("SCALE", nb.vmath("SUBTRACT", nc, (0.5, 0.5, 0.5)), scale=0.35)
    n2, _ = nb.noise(nb.vmath("ADD", q, warp), scale=5.5, detail=5, rough=0.58, w=nb.math("ADD", w, 4.0), dims="4D")
    r = nb.math("DIVIDE", nb.vmath("LENGTH", q), R)
    r = nb.math("ADD", r, nb.math("MULTIPLY", nb.math("SUBTRACT", n1, 0.5), 1.4))
    r = nb.math("ADD", r, nb.math("MULTIPLY", nb.math("SUBTRACT", n2, 0.5), 0.5))
    body = nb.math("SUBTRACT", 1.0, nb.smooth(0.35, 1.0, r))
    # erosion grows with age: wispy late frames
    ero = nb.math("ADD", nb.math("MULTIPLY", t, 0.3), 0.12)
    dens = nb.math("MULTIPLY", body, nb.smooth(ero, nb.math("ADD", ero, 0.32), nb.math("ADD", n2, nb.math("MULTIPLY", body, 0.25))))
    fade = nb.math("POWER", nb.math("SUBTRACT", 1.0, nb.math("MULTIPLY", t, 0.85)), 1.6 if not smoke else 1.1)
    dens = nb.math("MULTIPLY", nb.math("MULTIPLY", dens, fade), 26.0 if smoke else 14.0)
    pv = nb.n("ShaderNodeVolumePrincipled")
    pv.inputs["Color"].default_value = (0.32, 0.32, 0.34, 1) if smoke else (0.92, 0.94, 0.97, 1)
    pv.inputs["Anisotropy"].default_value = 0.25
    pv.inputs["Absorption Color"].default_value = (0.05, 0.05, 0.05, 1) if smoke else (0.0, 0.0, 0.0, 1)
    nb.link(dens, pv.inputs["Density"])
    nb.link(pv.outputs[0], out.inputs["Volume"])
    ob = K.box("Puff", (0, 0, 0), (2, 2, 2))
    ob.data.materials.append(m)
    ld = bpy.data.lights.new("Key", "SUN")
    ld.energy = 4.0
    ld.angle = math.radians(20)
    key = K.link(bpy.data.objects.new("Key", ld))
    key.rotation_euler = (math.radians(35), math.radians(-30), 0)
    bg = sc.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (1, 1, 1, 1)
    bg.inputs[1].default_value = 0.16
    K.camera("Cam", (0, -10, 0), (math.pi / 2, 0, 0), kind="ORTHO", ortho_scale=2.0)
    K.setup_cycles((256, 256), samples=spp, transparent=True, denoise=True, bounces=3)
    sc.frame_start, sc.frame_end = 1, N
    sc.render.filepath = os.path.join(K.OUT, f"{kind}_####")
    bpy.ops.render.render(animation=True)
    frames = []
    for f in range(1, N + 1):
        img = K.load(os.path.join(K.OUT, f"{kind}_{f:04d}.exr"))
        a = np.clip(img[:, :, 3], 0, 1)
        lum = img[:, :, 0] * 0.2126 + img[:, :, 1] * 0.7152 + img[:, :, 2] * 0.0722
        frames.append((lum, a))
    norm = max(1e-6, np.percentile(np.concatenate([l[a > 0.1] / a[a > 0.1] for l, a in frames if (a > 0.1).any()]), 98))
    cells = []
    for lum, a in frames:
        # straight (un-premultiplied) light, normalised; soften the cell border so particles never show edges
        light = np.where(a > 1e-3, lum / np.maximum(a, 1e-3), 0) / norm
        yy, xx = np.mgrid[0:256, 0:256]
        rr = np.hypot((xx + 0.5) / 256 - 0.5, (yy + 0.5) / 256 - 0.5) * 2
        edge = np.clip((1.0 - rr) / 0.12, 0, 1)
        cells.append(np.stack([np.clip(light, 0, 1)] * 3 + [a * edge], -1))
    at = K.atlas(cells, 8, 8)
    K.save_png(at, os.path.join(K.UNITY_FX, "Smoke", f"{kind}_8x8.png"))
    prev = at.copy()
    prev[:, :, :3] *= prev[:, :, 3:4]
    K.contact_sheet(prev, os.path.join(K.PREV, f"{kind}_preview.png"), scale=0.5)


def mist():
    sc = K.reset()
    T = 1.0
    chans = []
    for k in range(4):
        m, nb, out = K.new_material(f"Mist{k}")
        P = nb.n("ShaderNodeTexCoord").outputs["Object"]
        x, y, _ = nb.sep(P)
        ax, ay = nb.math("MULTIPLY", x, 2 * math.pi), nb.math("MULTIPLY", y, 2 * math.pi)
        v = nb.xyz(nb.math("COSINE", ax), nb.math("SINE", ax), nb.math("COSINE", ay))
        w = nb.math("ADD", nb.math("SINE", ay), k * 0.18)
        n1, nc = nb.noise(v, scale=1.2, detail=6, rough=0.6, w=w, dims="4D")
        n2, _ = nb.noise(nb.vmath("ADD", v, nb.vmath("SCALE", nb.vmath("SUBTRACT", nc, (0.5, 0.5, 0.5)), scale=1.2)), scale=2.4, detail=5, rough=0.55, w=nb.math("ADD", w, 3.0), dims="4D")
        val = nb.smooth(0.38, 0.72, nb.math("ADD", nb.math("MULTIPLY", n1, 0.6), nb.math("MULTIPLY", n2, 0.4)))
        e = nb.n("ShaderNodeEmission")
        nb.link(val, e.inputs["Strength"])
        nb.link(e.outputs[0], out.inputs["Surface"])
        for o in list(bpy.data.objects):
            if o.type == "MESH":
                bpy.data.objects.remove(o)
        pl = K.plane("Mist", (0.5, 0.5, 0), (1, 1))
        pl.data.materials.append(m)
        if not sc.camera:
            K.camera("Cam", (0.5, 0.5, 5), (0, 0, 0), kind="ORTHO", ortho_scale=1.0)
        K.setup_cycles((1024, 1024), samples=8, transparent=False, denoise=False, bounces=0, adaptive=0)
        img = K.load(K.render(os.path.join(K.OUT, f"mist_{k}.exr")))
        chans.append(np.clip(img[:, :, 0], 0, 1))
    K.save_png(np.stack(chans, -1), os.path.join(K.UNITY_FX, "Smoke", "mist_tile.png"))


def main():
    spp = int(K.flag("--samples", 16))
    only = K.flag("--only")
    if only in (None, "steam", "puffs"):
        puff("steam", spp)
    if only in (None, "smoke", "puffs"):
        puff("smoke", spp)
    if only in (None, "mist") and only != "puffs":
        mist()


if __name__ == "__main__":
    main()
