"""Parameter-only materials for the facility / metro interior props (merged into matdefs.REGISTRY)."""


def P(unity, preview):
    return {"kind": "param", "unity": unity, "preview": preview}


REGISTRY = {
    # Acid-etched privacy glass: milky, low gloss, semi-opaque (partitions, cryo-tube base frost, shelves).
    "glass_frosted": P({"surface": "Transparent", "baseColor": [0.80, 0.86, 0.90, 0.62], "metallic": 0.0, "smoothness": 0.42,
                        "cull": "Off"}, (0.80, 0.86, 0.90)),
}
