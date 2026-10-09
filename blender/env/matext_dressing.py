"""Parameter-only materials for the city dressing props (assets_dressing.py). Merged into matdefs.REGISTRY.

baseColor is sRGB (Unity colour property), preview is the linear colour used by the Blender previews.
"""


def _p(base_srgb, smooth, metallic=0.0, preview=None, **extra):
    lin = tuple(round(((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92, 4) for c in base_srgb)
    u = {"surface": "Opaque", "baseColor": [*base_srgb, 1.0], "metallic": metallic, "smoothness": smooth}
    u.update(extra)
    return {"kind": "param", "unity": u, "preview": preview or lin}


REGISTRY = {
    # rain-soaked corrugated cardboard (dark, slightly glossy) and the fully soaked / collapsed parts
    "cardboard_wet": _p((0.37, 0.28, 0.18), 0.42),
    "cardboard_soaked": _p((0.22, 0.155, 0.095), 0.62),
    # brown packing tape
    "tape_brown": _p((0.52, 0.38, 0.2), 0.7),
    # HDPE chemical drum blue
    "plastic_blue": _p((0.07, 0.25, 0.58), 0.48),
    # woven polypropylene / burlap sandbag fabric
    "fabric_sandbag": _p((0.47, 0.42, 0.31), 0.12),
    # dark potting soil, dead plant stems / leaves, terracotta
    "soil_dark": _p((0.12, 0.095, 0.075), 0.3),
    "plant_dead": _p((0.3, 0.25, 0.17), 0.18),
    "terracotta": _p((0.46, 0.25, 0.17), 0.28),
}
