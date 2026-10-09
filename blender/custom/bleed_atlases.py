"""Post-process hair atlases (system python3 + numpy + Pillow): bleed colour into transparent texels so alpha-clip
edges and mip levels never sample black.  python3 blender/custom/bleed_atlases.py [glob]"""
import sys, glob, os
import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "unity", "EchoesOfAether", "Assets", "Resources",
                                    "Characters", "Custom", "Hair", "Textures"))


def dilate(img, cov, iters):
    img = img.copy(); cov = cov.copy()
    for _ in range(iters):
        acc = np.zeros_like(img); cnt = np.zeros(cov.shape, np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sc = np.roll(np.roll(cov, dy, 0), dx, 1)
            si = np.roll(np.roll(img, dy, 0), dx, 1)
            acc += si * sc[..., None]
            cnt += sc
        grow = (~cov) & (cnt > 0)
        img[grow] = acc[grow] / cnt[grow][:, None]
        cov |= grow
    return img, cov


for p in sorted(glob.glob(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "*_Hair.png"))):
    im = np.asarray(Image.open(p).convert("RGBA")).astype(np.float32) / 255
    rgb, a = im[..., :3], im[..., 3]
    cov = a > 0.3
    out, grown = dilate(rgb, cov, 24)
    out[~grown] = rgb[cov].mean(0)
    keep = a > 0.6
    out[keep] = rgb[keep]
    res = np.concatenate([out, a[..., None]], -1)
    Image.fromarray((np.clip(res, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(p, optimize=True)
    blk = float(((res[..., :3].max(-1) < 0.05)).mean())
    print("bled", os.path.basename(p), "near-black texels", round(blk, 4))
