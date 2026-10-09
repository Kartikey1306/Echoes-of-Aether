"""NPC garment texture painter (baked BaseColor/Normal/MaskMap for Cloth_* materials) and shared hard-surface maps."""
import math
import numpy as np
import fabric as F
from texbake import fbm3, worley3, smoothstep as ss
from paint_kael import armor, boots, gloves  # noqa: F401

STYLES = {
    "Parka": {"base": (0.29, 0.29, 0.22), "quilt": True, "patches": [(0.24, 0.27, 0.33), (0.36, 0.25, 0.17), (0.32, 0.32, 0.3)], "smooth": 0.3},
    "Hoodie": {"base": (0.17, 0.22, 0.24), "quilt": False, "patches": [(0.42, 0.18, 0.2), (0.15, 0.15, 0.16)], "smooth": 0.2},
    "HoodieNia": {"base": (0.33, 0.3, 0.42), "quilt": False, "patches": [], "smooth": 0.2},
    "Coat": {"base": (0.24, 0.17, 0.12), "quilt": False, "patches": [(0.2, 0.22, 0.2), (0.3, 0.22, 0.15), (0.17, 0.15, 0.14)], "smooth": 0.35},
    "LabCoat": {"base": (0.82, 0.81, 0.78), "quilt": False, "patches": [], "smooth": 0.28},
}


def cloth(style, L, seed=1.0):
    S = STYLES[style]

    def fn(t, ao):
        n = len(t["P"])
        P, N, B = t["P"], t["N"], t["B"]
        Ly = F.Layer(n)
        x, y, z = B[:, 0], B[:, 1], B[:, 2]
        cy = L["Spine1"][1]
        phi = np.arctan2(x, -(y - cy))
        F.ripstop(Ly, P, N, 1.0, cell=0.006 if style == "Parka" else 0.003, amp=0.00012)
        if S["quilt"]:
            for k in np.arange(0.9, 1.6, 0.045):
                F.seam(Ly, z - k, phi * 0.16, mask=np.abs(x) < 0.3, stitch=(), depth=0.0012, width=0.0014)
        # side and shoulder seams
        F.seam(Ly, (np.abs(phi) - 1.5) * 0.16, z, stitch=(0.003,))
        F.seam(Ly, z - 1.42, phi * 0.16, mask=np.abs(x) < 0.28, stitch=(0.003, 0.006), stitch_side=1)
        col = np.tile(np.array(S["base"]), (n, 1))
        rng = np.random.default_rng(int(seed * 100))
        for pc in S["patches"]:
            ph0 = rng.uniform(-2.6, 2.6); z0 = rng.uniform(0.95, 1.45)
            w = rng.uniform(0.05, 0.09); h = rng.uniform(0.04, 0.08)
            d = np.maximum(np.abs(phi * 0.16 - ph0 * 0.16) - w / 2, np.abs(z - z0) - h / 2)
            m = d < 0
            col[m] = np.array(pc)
            F.panel_edge(Ly, -d, mask=d < 0.004, raise_=0.0008, soft=0.002)
            F.seam(Ly, d + 0.004, (phi * 0.16 + z), mask=np.abs(d + 0.004) < 0.006, stitch=(0.0,), depth=0.0003)
        F.wrinkles(Ly, B, (0, 0, 1), np.ones(n), wavelength=0.03, amp=0.0012, seed=seed)
        dirt = ss(0.55, 0.85, fbm3(P, 12, 4, seed) * 0.5 + 0.5) * 0.35 + (1 - ao) * 0.5 + ss(1.05, 0.85, z) * 0.15
        col = col * (1 + 0.08 * fbm3(P, 80, 3, seed + 2)[:, None])
        col = col * (1 - dirt[:, None] * 0.45) * (1 - Ly.A[:, None] * 0.35)
        smooth = np.clip(S["smooth"] - dirt * 0.1, 0.05, 0.6)
        return col, Ly.h, np.zeros(n, np.float32), smooth
    return fn
