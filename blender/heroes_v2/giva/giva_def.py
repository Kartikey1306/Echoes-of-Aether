"""Giva Vale (asset id lyra): MakeHuman/MPFB phenotype, shape targets and system assets.

Only CC0 MakeHuman system assets are used (base mesh, mixamo_unity rig weights, targets, eye/teeth/tongue,
system eyebrow/eyelash proxies); see docs/THIRD_PARTY_LICENSES.md section 5.

Head size/position must stay within ~1 cm of the previous Lyra so catalog hair (long_curls) and eyewear fit:
the cranium targets (head-scale-*, head-oval, forehead) are kept from the old build; the face features change.
"""

PHENOTYPE = {
    # ~1.73 m, ~7.5 heads; athletic and balanced (toned, not bulky), elegant neck and shoulders.
    "gender": 0.0, "age": 0.5, "muscle": 0.66, "weight": 0.45, "height": 0.565, "proportions": 1.0,
    "cupsize": 0.42, "firmness": 0.66, "race": {"asian": 0.25, "caucasian": 0.55, "african": 0.20},
}

# Cranium: unchanged from the old Lyra (catalog hair / eyewear fit).
CRANIUM = [
    ("head/head-scale-vert-decr", 0.10),
    ("head/head-scale-horiz-decr", 0.1),
    ("head/head-oval", 0.50),
    ("forehead/forehead-temple-decr", 0.15),
]

BODY = [
    ("torso/measure-shoulder-dist-incr", 0.22),
    ("torso/torso-vshape-incr", 0.18),
    ("torso/measure-waist-circ-decr", 0.32),
    ("stomach/stomach-tone-incr", 0.45),
    ("stomach/stomach-pregnant-decr", 0.25),
    ("neck/measure-neck-circ-decr", 0.18),
    ("neck/measure-neck-height-incr", 0.12),
    ("arms/l-upperarm-shoulder-muscle-incr", 0.12),
    ("arms/r-upperarm-shoulder-muscle-incr", 0.12),
    ("arms/l-upperarm-muscle-incr", 0.06),
    ("arms/r-upperarm-muscle-incr", 0.06),
    ("arms/l-lowerarm-muscle-incr", 0.12),
    ("arms/r-lowerarm-muscle-incr", 0.12),
    ("legs/l-upperleg-muscle-incr", 0.14),
    ("legs/r-upperleg-muscle-incr", 0.14),
    ("legs/l-lowerleg-muscle-incr", 0.28),
    ("legs/r-lowerleg-muscle-incr", 0.28),
    ("legs/upperlegs-height-incr", 0.28),
    ("legs/lowerlegs-height-incr", 0.3),
    ("buttocks/buttocks-volume-decr", 0.12),
    ("hip/hip-scale-horiz-decr", 0.16),
]

FACE = [
    # Iterated in out/iter (v6) and out/lab (L6B, master concept): tapered elegant jaw, high cheekbones with softer
    # cheeks, slim refined nose, a smaller natural mouth set back, larger open almond eyes, slightly lower brows.
    ("cheek/l-cheek-bones-incr", 0.45), ("cheek/r-cheek-bones-incr", 0.45),
    ("cheek/l-cheek-inner-decr", 0.3), ("cheek/r-cheek-inner-decr", 0.3),
    ("cheek/l-cheek-volume-decr", 0.0), ("cheek/r-cheek-volume-decr", 0.0),
    ("cheek/l-cheek-trans-up", 0.3), ("cheek/r-cheek-trans-up", 0.3),
    ("head/head-fat-decr", 0.25),
    ("chin/chin-width-decr", 0.5),
    ("chin/chin-bones-decr", 0.4),
    ("chin/chin-prominent-incr", 0.2),
    ("chin/chin-height-decr", 0),
    ("chin/chin-triangle", 0.1),
    ("chin/chin-jaw-drop-decr", 0.5),
    ("neck/neck-double-decr", 0.6),
    ("nose/nose-scale-horiz-decr", 0.5),
    ("nose/nose-scale-vert-decr", 0.38),
    ("nose/nose-scale-depth-incr", 0.1),
    ("nose/nose-point-width-decr", 1.0),
    ("nose/nose-width1-decr", 0.35),
    ("nose/nose-width2-decr", 0.35),
    ("nose/nose-width3-decr", 0.25),
    ("nose/nose-nostrils-width-decr", 0.5),
    ("nose/nose-flaring-decr", 0.4),
    ("nose/nose-point-up", 0.18),
    ("nose/nose-hump-decr", 0.2),
    ("nose/nose-greek-incr", 0.25),
    ("nose/nose-trans-up", 0.08),
    ("mouth/mouth-upperlip-volume-incr", 0.08),
    ("mouth/mouth-lowerlip-volume-incr", 0.4),
    ("mouth/mouth-upperlip-height-incr", 0.12),
    ("mouth/mouth-lowerlip-height-incr", 0.02),
    ("mouth/mouth-cupidsbow-incr", 0.8),
    ("mouth/mouth-scale-horiz-decr", 0.3),
    ("mouth/mouth-angles-up", 0.25),
    ("mouth/mouth-philtrum-volume-incr", 0.15),
    ("mouth/mouth-scale-depth-decr", 0.6),
    ("mouth/mouth-trans-backward", 0.45),
    ("eyes/l-eye-scale-incr", 0.46), ("eyes/r-eye-scale-incr", 0.46),
    ("eyes/l-eye-corner2-up", 0.3), ("eyes/r-eye-corner2-up", 0.3),
    ("eyes/l-eye-height2-incr", 0), ("eyes/r-eye-height2-incr", 0),
    ("eyes/l-eye-push1-in", 0.2), ("eyes/r-eye-push1-in", 0.2),
    ("eyes/l-eye-bag-decr", 0.6), ("eyes/r-eye-bag-decr", 0.6),
    ("eyes/l-eye-eyefold-down", 0.4), ("eyes/r-eye-eyefold-down", 0.4),
    ("eyebrows/eyebrows-angle-up", 0.08),
    ("eyebrows/eyebrows-trans-down", 0.15),
    ("forehead/forehead-scale-vert-decr", 0.18),
    ("ears/l-ear-flap-decr", 0.3), ("ears/r-ear-flap-decr", 0.3),
    ("ears/l-ear-scale-decr", 0.1), ("ears/r-ear-scale-decr", 0.1),
    # pass 2 (lab L7soft): younger, softer oval, fuller cheeks, smaller upturned nose, fuller lips
    ("head/head-age-decr", 0.3),
    ("head/head-round", 0),
    ("cheek/l-cheek-volume-incr", 0),
    ("cheek/r-cheek-volume-incr", 0),
    ("nose/nose-volume-decr", 0.15),
    # makeover (lab M5, Oct 2026): slimmer oval with a soft V jaw, almond hooded eyes, lips set back, narrower mouth
    ("head/head-invertedtriangular", 0.2),
    ("eyes/l-eye-height2-decr", 0.0),
    ("eyes/r-eye-height2-decr", 0.0),
    ("chin/chin-height-incr", 0.0),
    ("eyes/l-eye-height1-decr", 0.0),
    ("eyes/r-eye-height1-decr", 0.0),
    ("eyes/l-eye-height3-decr", 0.0),
    ("eyes/r-eye-height3-decr", 0.0),
    ("chin/chin-prognathism-incr", 0.25),
]

ASSETS = {
    "rig": "mixamo_unity",
    "eyes": "high-poly/high-poly.mhclo",
    "eyebrows": "eyebrow001/eyebrow001.mhclo",
    "eyelashes": "eyelashes02/eyelashes02.mhclo",
    "teeth": "teeth_base/teeth_base.mhclo",
    "tongue": "tongue01/tongue01.mhclo",
    "skin": "young_caucasian_female/young_caucasian_female.mhmat",
}


def targets(overrides=None):
    """Full target list; overrides: {target_path: value} replaces/extends (value 0 removes)."""
    t = dict(CRANIUM + BODY + FACE)
    for k, v in (overrides or {}).items():
        t[k] = v
    return [(k, v) for k, v in t.items() if abs(v) > 1e-6]
