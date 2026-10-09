"""
Branching lightning bolts (cloud-to-ground), procedural paths rendered in Cycles as emissive tapered curves, glow
added with a numpy gaussian stack.

Path: recursive midpoint displacement from the cloud base to the ground with a downward bias; branches fork off
with decreasing thickness / brightness and die out; the main channel is brightest. Each bolt is rendered at 256x1024
(ortho) and gets a soft glow (sum of blurs) so the sky shader can add it straight.

  Lightning/lightning_bolts.png   1024x1024, 4 columns (256 px each), R = G = B = A = core + glow (linear).

Usage: Blender -b -P lightning.py -- [--samples 16]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import fxkit as K  # noqa: E402

W, H = 1.0, 4.0     # drop space (cell 256 x 1024)


def bolt_path(rng, p0, p1, rough, depth):
    pts = [np.array(p0, float), np.array(p1, float)]
    disp = rough
    for _ in range(depth):
        new = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            m = (a + b) * 0.5
            seg = b - a
            n = np.array([-seg[1], seg[0]])
            n /= max(1e-6, np.linalg.norm(n))
            m = m + n * rng.normal(0, disp) * np.linalg.norm(seg)
            new += [m, b]
        pts = new
        disp *= 0.9
    for p in pts:
        p[0] = float(0.4 * W * math.tanh(p[0] / (0.4 * W)))
    return pts


def build_bolt(seed):
    rng = np.random.default_rng(seed)
    strokes = []    # (points, radius, brightness)
    top = (rng.normal(0, 0.08), H / 2 - 0.02)
    bottom = (rng.normal(0, 0.18), -H / 2 + 0.08)
    main = bolt_path(rng, top, bottom, 0.07, 9)
    strokes.append((main, 0.012, 1.0))

    def branch(pts, radius, bright, level):
        if level > 3:
            return
        n = len(pts)
        for _ in range(rng.integers(2, 6) if level == 0 else rng.integers(0, 3)):
            i = int(rng.integers(n // 12, int(n * 0.8)))
            start = pts[i]
            side = -np.sign(start[0]) if abs(start[0]) > 0.08 else rng.choice([-1, 1])
            ang = -math.pi / 2 + side * (0.25 + rng.random() * 0.5)
            ln = (0.2 + rng.random() * 0.5) * H * (0.55 ** level)
            room = (0.36 * W - side * start[0]) / max(1e-3, abs(math.cos(ang)))
            ln = min(ln, max(0.1, room))
            end = start + np.array([math.cos(ang), math.sin(ang)]) * ln
            if abs(end[0]) > 0.36 * W:
                continue
            bp = bolt_path(rng, start, end, 0.12, 7)
            strokes.append((bp, radius * 0.55, bright * 0.55))
            branch(bp, radius * 0.55, bright * 0.55, level + 1)

    branch(main, 0.012, 1.0, 0)
    return strokes


def render_bolt(seed, spp):
    K.reset()
    for k, (pts, rad, bright) in enumerate(build_bolt(seed)):
        cd = bpy.data.curves.new(f"b{k}", "CURVE")
        cd.dimensions = "3D"
        sp = cd.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for j, p in enumerate(pts):
            u = j / max(1, len(pts) - 1)
            sp.points[j].co = (p[0], 0.0, p[1], 1.0)
            sp.points[j].radius = 1.0 - 0.6 * u
        cd.bevel_depth = rad
        cd.bevel_resolution = 2
        ob = K.link(bpy.data.objects.new(f"b{k}", cd))
        ob.data.materials.append(K.emission_material(f"e{k}", (1, 1, 1, 1), bright))
    K.camera("Cam", (0, -10, 0), (math.pi / 2, 0, 0), kind="ORTHO", ortho_scale=H)
    K.setup_cycles((256, 1024), samples=spp, transparent=True, denoise=False, bounces=0, adaptive=0)
    return K.load(K.render(os.path.join(K.OUT, f"bolt_{seed}.exr")))


def main():
    spp = int(K.flag("--samples", 16))
    cols = []
    for seed in (3, 11, 19, 42):
        img = render_bolt(seed, spp)
        core = np.clip(img[:, :, 0], 0, 1)
        glow = K.blur(core, 2.5) * 1.6 + K.blur(core, 9) * 1.4 + K.blur(core, 26) * 1.2
        v = np.clip(core + glow, 0, 1)
        xw = np.linspace(-1, 1, v.shape[1])[None, :]
        v *= np.clip((1 - np.abs(xw)) / 0.12, 0, 1)
        # fade the ends: top melts into the cloud base, bottom stops at the horizon
        y = np.linspace(1, 0, v.shape[0])[:, None]
        v *= np.clip((1 - y) / 0.08, 0, 1) ** 0.5 * np.clip(y / 0.02, 0, 1)
        cols.append(np.stack([v] * 4, -1))
    at = np.concatenate(cols, axis=1)
    K.save_png(at, os.path.join(K.UNITY_FX, "Lightning", "lightning_bolts.png"))
    prev = at.copy()
    prev[:, :, :3] *= np.array([0.75, 0.8, 1.0])
    prev[:, :, 3] = 0
    K.contact_sheet(prev[:, :, :3], os.path.join(K.PREV, "lightning_preview.png"), scale=0.5)


if __name__ == "__main__":
    main()
