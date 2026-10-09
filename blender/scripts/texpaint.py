"""Paint garment mask/normal textures in UV space from smooth 3D zone fields (numpy rasteriser).

Mask channels: R = secondary panel, G = trim/metal, B = glow, A = seam groove (0..1).
"""
import os
import numpy as np
import bpy


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def raster(obj, size, fn):
    """Rasterise obj (basis positions, vertex normals interpolated) into a size x size RGBA float image
    by evaluating fn(P[N,3], Nrm[N,3]) -> (N,4) per covered texel. Returns (img, covered mask)."""
    me = obj.data
    me.calc_loop_triangles()
    uv = me.uv_layers.active.data
    co = np.array([v.co[:] for v in me.vertices], dtype=np.float64)
    vn = np.array([v.normal[:] for v in me.vertices], dtype=np.float64)
    img = np.zeros((size, size, 4), dtype=np.float32)
    cov = np.zeros((size, size), dtype=bool)
    for tri in me.loop_triangles:
        l = tri.loops
        uvs = np.array([uv[i].uv[:] for i in l]) * size
        if np.ptp(uvs[:, 0]) < 1e-6 and np.ptp(uvs[:, 1]) < 1e-6:
            continue
        x0, y0 = np.floor(uvs.min(axis=0)).astype(int)
        x1, y1 = np.ceil(uvs.max(axis=0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        p = np.stack([xs.ravel(), ys.ravel()], axis=1)
        a, b, c = uvs
        v0, v1, v2 = b - a, c - a, p - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-12:
            continue
        d20, d21 = v2 @ v0, v2 @ v1
        w1 = (d11 * d20 - d01 * d21) / den
        w2 = (d00 * d21 - d01 * d20) / den
        w0 = 1 - w1 - w2
        inside = (w0 >= -1e-3) & (w1 >= -1e-3) & (w2 >= -1e-3)
        if not inside.any():
            continue
        w = np.stack([w0, w1, w2], axis=1)[inside]
        vi = list(tri.vertices)
        P = w @ co[vi]
        N = w @ vn[vi]
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        val = fn(P, N)
        px = p[inside].astype(int)
        img[px[:, 1], px[:, 0]] = val
        cov[px[:, 1], px[:, 0]] = True
    return img, cov


def dilate(img, cov, iters=6):
    """Bleed island colours outward so mip-mapping never samples empty texels."""
    img = img.copy(); cov = cov.copy()
    for _ in range(iters):
        acc = np.zeros_like(img); cnt = np.zeros(cov.shape, dtype=np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sc = np.roll(np.roll(cov, dy, 0), dx, 1)
            si = np.roll(np.roll(img, dy, 0), dx, 1)
            acc += si * sc[..., None]; cnt += sc
        grow = (~cov) & (cnt > 0)
        img[grow] = acc[grow] / cnt[grow][:, None]
        cov |= grow
    return img


def normal_from_height(h, strength=2.0):
    gy, gx = np.gradient(h)
    n = np.stack([-gx * strength, -gy * strength, np.ones_like(h)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def save_png(arr, path, alpha=True):
    """arr: (H,W,C) float 0..1 in UV orientation (row 0 = v 0). Saved with v up."""
    h, w = arr.shape[:2]
    c = arr.shape[2]
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :c] = arr
    im = bpy.data.images.new(os.path.basename(path), w, h, alpha=alpha, float_buffer=False)
    im.pixels.foreach_set(rgba.ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


def paint_garment(obj, size, fn, out_dir, base, seam_strength=3.0):
    img, cov = raster(obj, size, fn)
    img = dilate(img, cov, 8)
    # Seam grooves: height drops along the seam channel; a soft stitch line beside it.
    seam = img[..., 3]
    height = -seam * 1.0
    nrm = normal_from_height(height, seam_strength)
    os.makedirs(out_dir, exist_ok=True)
    save_png(img, os.path.join(out_dir, base + "_Mask.png"))
    save_png(nrm, os.path.join(out_dir, base + "_Normal.png"), alpha=False)
    return img
