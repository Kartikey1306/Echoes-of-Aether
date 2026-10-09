"""Procedural hair-strand eyebrow texture for the MakeHuman brow cards (UV layout of the source texture kept).

Each brow footprint in the source atlas (alpha) becomes a density field; strands are drawn as thin tapered lines
whose angle follows natural brow growth (steep at the medial head, flattening towards the tail, upper rows tilted
down and lower rows up so they converge on the ridge). Alpha is near-binary per strand (alpha test at ~0.4 keeps
individual hairs) with soft 1-px edges for mip filtering; grey values vary per hair (tips lighter).
"""
import math
import numpy as np
import texbake as TB
import kcommon as K


def strand_brows(src_path, out_path, size=1024, n_strands=1500, seed=5):
    src = TB.read_image(src_path, size)
    al = src[..., 3]
    dens = np.clip((TB.blur(al, 5) - 0.08) * 1.5, 0, 1)            # concept: thick, straight, dark brows
    H = W = size
    rng = np.random.default_rng(seed)
    out_a = np.zeros((H, W), np.float32)
    out_l = np.zeros((H, W), np.float32)
    # brow regions: connected bands (top and bottom halves of the atlas hold the two brows)
    regions = []
    for y0, y1 in ((0, H // 2), (H // 2, H)):
        m = dens[y0:y1] > 0.08
        if m.sum() < 50:
            continue
        cols = np.where(m.any(0))[0]
        x0, x1 = cols.min(), cols.max()
        # centreline: per-column alpha-weighted mean row, and thickness
        cy = np.zeros(W); th = np.zeros(W)
        for x in range(x0, x1 + 1):
            c = dens[y0:y1, x]
            if c.sum() > 1e-3:
                ys = np.arange(y0, y1)
                cy[x] = (c * ys).sum() / c.sum()
                th[x] = (c > 0.15).sum()
        # medial end = thicker end
        left_t = th[x0:x0 + (x1 - x0) // 4].mean(); right_t = th[x1 - (x1 - x0) // 4:x1].mean()
        medial_left = left_t > right_t
        regions.append((y0, y1, x0, x1, cy, th, medial_left))
    yy, xx = np.mgrid[0:H, 0:W]
    for (y0, y1, x0, x1, cy, th, medial_left) in regions:
        pts = np.argwhere(dens[y0:y1, x0:x1 + 1] > 0.12)
        if not len(pts):
            continue
        w = dens[y0:y1, x0:x1 + 1][pts[:, 0], pts[:, 1]] ** 1.8      # concentrate in the core, feathered edges
        w = w / w.sum()
        k = int(n_strands * (len(pts) / max(1, (dens > 0.12).sum())) * 1.0) + 50
        pick = rng.choice(len(pts), size=k, p=w)
        for i in pick:
            py, px = pts[i][0] + y0, pts[i][1] + x0
            s = (px - x0) / max(1, x1 - x0)
            s = s if medial_left else 1 - s                      # 0 medial .. 1 tail
            dirx = 1.0 if medial_left else -1.0                  # growth towards the tail
            rel = (py - cy[px]) / max(th[px] * 0.5, 1.0)         # -1 .. 1 across the brow (rows bottom-up)
            ang = math.radians(62 * (1 - K.ss(0.0, 0.35, s)) + 14) - rel * math.radians(12) * (0.4 + 0.6 * s)
            ang += rng.normal(0, math.radians(6))
            L = rng.uniform(0.022, 0.04) * size * (1.15 - 0.4 * s)
            wdt = rng.uniform(1.1, 1.7) * size / 1024
            dx, dy = math.cos(ang) * dirx, math.sin(ang)
            ax_, ay_ = px, py
            bx_, by_ = px + dx * L, py + dy * L * (1 if rel <= 0.6 else 0.6)
            xmn, xmx = int(max(0, min(ax_, bx_) - 3)), int(min(W - 1, max(ax_, bx_) + 3))
            ymn, ymx = int(max(0, min(ay_, by_) - 3)), int(min(H - 1, max(ay_, by_) + 3))
            sx = xx[ymn:ymx + 1, xmn:xmx + 1].astype(np.float64); sy = yy[ymn:ymx + 1, xmn:xmx + 1].astype(np.float64)
            d, t = TB.line_sdf2(sx, sy, ax_, ay_, bx_, by_)
            taper = wdt * (1 - 0.75 * t)
            a = np.clip(1.0 - (d - taper * 0.5) / 0.9, 0, 1) * (t > 0.0)
            tone = np.minimum(1.0, rng.uniform(0.4, 0.52) + 0.1 * t)             # final pass: darker brows (runtime tint x this)
            cur = out_a[ymn:ymx + 1, xmn:xmx + 1]
            upd = a > cur
            out_l[ymn:ymx + 1, xmn:xmx + 1] = np.where(upd, tone, out_l[ymn:ymx + 1, xmn:xmx + 1])
            out_a[ymn:ymx + 1, xmn:xmx + 1] = np.maximum(cur, a)
    rgb = np.repeat(np.where(out_a > 0, out_l, 0.45)[..., None], 3, -1)
    img = np.concatenate([rgb, out_a[..., None]], -1)
    img = TB.dilate(img, out_a > 0.05, 2)
    img[..., 3] = out_a
    TB.write_png(img, out_path, "RGBA")
    return out_path, float((out_a > 0.4).mean())
