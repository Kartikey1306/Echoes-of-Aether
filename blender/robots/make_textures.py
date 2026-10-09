"""Generate the shared 1024 tileable worn-metal detail set for the robots (numpy spectral synthesis -> PNG).

  Blender -b --factory-startup --python make_textures.py

Outputs into Assets/Resources/Models/Robots/Textures/:
  robot_worn_metal_BaseColor.png          greyscale albedo multiplier (sRGB). Paint ~0.8, chips/scratches brighter,
                                          grime darker. Multiply with the code palette colour (_BaseColor).
  robot_worn_metal_Normal.png             tangent-space normal, OpenGL (+Y) convention = Unity's expected format.
  robot_worn_metal_MetallicSmoothness.png URP packing: R = metallic, A = smoothness (G = B = 0).
Every map tiles seamlessly (everything is built from periodic FFT noise and wrapped strokes).
"""
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import roboscene as RS  # noqa: E402

N = 1024
rng = np.random.default_rng(20261003)
FX = np.fft.fftfreq(N)[None, :]
FY = np.fft.fftfreq(N)[:, None]
FR = np.sqrt(FX ** 2 + FY ** 2)
FR[0, 0] = 1.0


def norm01(a):
    a = a - a.min()
    return a / max(a.max(), 1e-9)


def spectral(beta, lo=0.0, hi=0.5, aniso=(1.0, 1.0)):
    """Periodic noise with 1/f^beta spectrum between frequency lo..hi (cycles per pixel)."""
    w = rng.standard_normal((N, N))
    F = np.fft.fft2(w)
    fr = np.sqrt((FX * aniso[0]) ** 2 + (FY * aniso[1]) ** 2)
    fr[0, 0] = 1.0
    filt = 1.0 / fr ** beta
    filt[(FR < lo) | (FR > hi)] = 0.0
    filt[0, 0] = 0.0
    return norm01(np.real(np.fft.ifft2(F * filt)))


def blur(a, sigma):
    g = np.exp(-2 * (np.pi * FR * sigma) ** 2)
    g[0, 0] = 1.0
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def strokes(count, len_rng, width, angles, jitter):
    """Wrapped anti-aliased line strokes (scratches) -> coverage map."""
    acc = np.zeros((N, N), dtype=np.float64)
    for _ in range(count):
        L = rng.uniform(*len_rng)
        ang = rng.choice(angles) + rng.normal(0, jitter)
        x0, y0 = rng.uniform(0, N, 2)
        steps = int(L * 2)
        t = np.linspace(0, 1, steps)
        bend = rng.normal(0, 0.06)
        xs = x0 + np.cos(ang) * L * t + np.sin(ang) * bend * L * t * t
        ys = y0 + np.sin(ang) * L * t - np.cos(ang) * bend * L * t * t
        strength = rng.uniform(0.4, 1.0) * np.sin(np.pi * t) ** 0.5
        xi = np.floor(xs).astype(int) % N
        yi = np.floor(ys).astype(int) % N
        np.add.at(acc, (yi, xi), strength)
    return np.clip(blur(acc, width), 0, None)


def save_png(name, rgba, noncolor):
    path = os.path.join(RS.TEX_DIR, name)
    im = bpy.data.images.new(name, N, N, alpha=True, float_buffer=False)
    if noncolor:
        im.colorspace_settings.name = "Non-Color"
    im.pixels.foreach_set(np.clip(rgba, 0, 1).astype(np.float32).ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    print("[tex] wrote", path)


def main():
    os.makedirs(RS.TEX_DIR, exist_ok=True)
    grain = spectral(0.6, 0.08, 0.5)                    # fine metal grain
    mottle = spectral(1.6, 0.002, 0.08)                 # broad paint mottling
    grime = spectral(2.0, 0.0015, 0.05)                 # dirt build-up
    streak = spectral(1.4, 0.003, 0.2, aniso=(1.0, 0.18))  # soft streaking
    dents = blur(spectral(1.2, 0.01, 0.12), 2.0)
    chipn = spectral(1.3, 0.004, 0.25)
    chip = np.clip((chipn - 0.63) / 0.025, 0, 1)        # paint chips (sparse)
    chip = chip * np.clip((grime - 0.3) / 0.25, 0, 1)   # chips cluster where wear is heavier
    chip_edge = np.clip(blur(chip, 1.2) - chip * 0.6, 0, 1)
    scr = strokes(70, (12, 120), 0.6, [0.0, np.pi / 2, np.pi / 4, -np.pi / 6], 0.25)
    scr = np.clip(scr / max(np.percentile(scr, 99.7), 1e-6), 0, 1)
    fine_scr = strokes(420, (4, 30), 0.45, [0.0, 2.0, 1.1], 0.6)
    fine_scr = np.clip(fine_scr / max(np.percentile(fine_scr, 99.8), 1e-6), 0, 1) * 0.5

    # ---- albedo multiplier (sRGB greyscale)
    paint = 0.80 + (mottle - 0.5) * 0.10 + (grain - 0.5) * 0.04
    paint *= 1.0 - np.clip((grime - 0.45) * 0.5, 0, 0.16) - np.clip(streak - 0.6, 0, 1) * 0.12
    bare = 0.98 + (grain - 0.5) * 0.08
    wear = np.clip(chip + scr * 0.45 + fine_scr * 0.3, 0, 1)
    albedo = paint * (1 - wear) + bare * wear
    albedo -= chip_edge * 0.08                          # dark rim around chips (paint edge)
    albedo = np.clip(albedo, 0.35, 1.0)

    # ---- metallic / smoothness
    metallic = 0.68 + (mottle - 0.5) * 0.06
    metallic = metallic * (1 - wear) + 0.96 * wear
    smooth = 0.56 + (mottle - 0.5) * 0.08 - np.clip(grime - 0.45, 0, 1) * 0.45 - (grain - 0.5) * 0.06
    smooth = smooth * (1 - wear) + 0.74 * wear
    smooth = np.clip(smooth, 0.12, 0.9)

    # ---- height -> normal (tileable central differences)
    h = (grain - 0.5) * 0.35 + (dents - 0.5) * 1.2 - chip * 1.1 - scr * 0.9 - fine_scr * 0.4
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5
    k = 2.2
    nx, ny, nz = -dx * k, -dy * k, np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    nrm = np.stack([nx / ln * 0.5 + 0.5, ny / ln * 0.5 + 0.5, nz / ln * 0.5 + 0.5, np.ones_like(h)], axis=-1)

    one = np.ones_like(h)
    save_png("robot_worn_metal_BaseColor.png", np.stack([albedo, albedo, albedo, one], -1), False)
    save_png("robot_worn_metal_Normal.png", nrm, True)
    zero = np.zeros_like(h)
    save_png("robot_worn_metal_MetallicSmoothness.png", np.stack([metallic, zero, zero, smooth], -1), True)


main()
