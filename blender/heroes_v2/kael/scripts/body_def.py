"""Kael Voss v3/pass 2 (concept match: heroic build - broad shoulders, thick arms, chest and thighs; rugged, heavy brow, deep-set eyes, broad jaw): MPFB phenotype, shape
targets and system assets (CC0 makehuman_system only)."""

PHENOTYPE = {
    "gender": 1.0, "age": 0.62, "muscle": 0.8, "weight": 0.5, "height": 0.56, "proportions": 1.0,
    "cupsize": 0.5, "firmness": 0.5, "race": {"asian": 0.05, "caucasian": 0.85, "african": 0.10},
}

# (target, weight). Body first (heroic V-taper, long legs, natural arms), then the face.
TARGETS = [
    # --- torso / V-taper
    ("torso/measure-shoulder-dist-incr", 0.62),
    ("torso/torso-vshape-incr", 0.8),
    ("torso/torso-muscle-pectoral-incr", 0.45),
    ("torso/torso-muscle-dorsi-incr", 0.45),
    ("torso/measure-waist-circ-decr", 0.65),
    ("hip/hip-scale-horiz-decr", 0.55),
    ("stomach/stomach-tone-incr", 0.5),
    ("neck/measure-neck-circ-incr", 0.85),          # concept: thick, muscular neck (head-to-neck proportion)
    ("neck/measure-neck-height-incr", 0.15),
    # --- arms: athletic, not bulky
    ("arms/l-upperarm-shoulder-muscle-incr", 0.45),
    ("arms/r-upperarm-shoulder-muscle-incr", 0.45),
    ("arms/l-upperarm-muscle-incr", 0.45),
    ("arms/r-upperarm-muscle-incr", 0.45),
    ("arms/l-lowerarm-muscle-incr", 0.35),
    ("arms/r-lowerarm-muscle-incr", 0.35),
    # --- legs: long and athletic
    ("legs/l-upperleg-muscle-incr", 0.35),
    ("legs/r-upperleg-muscle-incr", 0.35),
    ("legs/l-lowerleg-muscle-incr", 0.3),
    ("legs/r-lowerleg-muscle-incr", 0.3),
    ("legs/upperlegs-height-incr", 0.4),
    ("legs/lowerlegs-height-incr", 0.35),
    # --- head (cranium kept: catalog hair/eyewear fit)
    ("head/head-square", 0.5),
    ("head/head-age-incr", 0.08),
    ("head/head-scale-vert-decr", 0.15),
    ("head/head-scale-horiz-incr", 0.08),
    # --- jaw / chin: strong and defined
    ("chin/chin-prominent-incr", 0.4),
    ("chin/chin-width-incr", 0.6),
    ("chin/chin-height-decr", 0.25),
    ("chin/chin-bones-incr", 0.55),
    ("chin/chin-cleft-incr", 0.15),
    # --- cheekbones: sculpted, lean cheeks
    ("cheek/l-cheek-bones-incr", 0.9),
    ("cheek/r-cheek-bones-incr", 0.9),
    ("cheek/l-cheek-inner-decr", 0.6),
    ("cheek/r-cheek-inner-decr", 0.6),
    ("cheek/l-cheek-volume-decr", 0.3),
    ("cheek/r-cheek-volume-decr", 0.3),
    ("cheek/l-cheek-trans-up", 0.1),
    ("cheek/r-cheek-trans-up", 0.1),
    # --- brow: defined ridge, lower, slightly forward
    ("eyebrows/eyebrows-trans-forward", 0.55),
    ("eyebrows/eyebrows-trans-down", 0.55),
    ("eyebrows/eyebrows-angle-down", 0.12),
    ("forehead/forehead-nubian-incr", 0.25),
    ("forehead/forehead-temple-decr", 0.15),
    # --- nose: straight, well proportioned
    ("nose/nose-scale-vert-decr", 0.12),
    ("nose/nose-width1-decr", 0.2),
    ("nose/nose-width2-decr", 0.1),
    ("nose/nose-point-width-decr", 0.0),
    ("nose/nose-nostrils-width-decr", 0.1),
    ("nose/nose-scale-horiz-incr", 0.12),
    ("nose/nose-hump-decr", 0.0),
    ("nose/nose-point-up", 0.12),
    # --- mouth: natural
    ("mouth/mouth-lowerlip-volume-decr", 0.3),
    ("mouth/mouth-cupidsbow-incr", 0.5),
    ("mouth/mouth-philtrum-volume-incr", 0.1),
    ("mouth/mouth-upperlip-height-decr", 0.2),
    ("mouth/mouth-scale-horiz-incr", 0.1),
    ("mouth/mouth-upperlip-volume-decr", 0.6),
    ("head/head-fat-decr", 0.3),
    ("mouth/mouth-scale-depth-decr", 0.25),
    ("mouth/mouth-trans-backward", 0.15),
    ("nose/nose-volume-decr", 0.0),
    ("neck/neck-double-decr", 0.6),
    ("eyes/l-eye-scale-incr", 0.1),
    ("eyes/r-eye-scale-incr", 0.1),
    # --- eyes: intense almond
    ("eyes/l-eye-height2-decr", 0.1),
    ("eyes/r-eye-height2-decr", 0.1),
    ("eyes/l-eye-push1-in", 0.5),
    ("eyes/r-eye-push1-in", 0.5),
    ("eyes/l-eye-push2-in", 0.3),
    ("eyes/r-eye-push2-in", 0.3),
    ("mouth/mouth-laugh-lines-in", 0.35),
    ("eyes/l-eye-corner2-up", 0.12),
    ("eyes/r-eye-corner2-up", 0.12),
    ("eyes/l-eye-eyefold-down", 0.2),
    ("eyes/r-eye-eyefold-down", 0.2),
    ("eyes/l-eye-bag-decr", 0.45),
    ("eyes/r-eye-bag-decr", 0.45),
    # --- ears
    ("ears/l-ear-flap-decr", 0.2),
    ("ears/r-ear-flap-decr", 0.2),
]

ASSETS = {
    "skin": "young_caucasian_male/young_caucasian_male.mhmat",
    "eyes": "high-poly/high-poly.mhclo",
    "eyebrows": "eyebrow009/eyebrow009.mhclo",
    "eyelashes": "eyelashes01/eyelashes01.mhclo",
    "teeth": "teeth_base/teeth_base.mhclo",
    "tongue": "tongue01/tongue01.mhclo",
}

# The previous (committed) Kael definition, rebuilt to transfer the old fitted assets (hair cards, beard) to the
# new head with exact vertex correspondence.
OLD_CHARACTER = "kael"
