"""Character definitions for Echoes of Aether (MakeHuman/MPFB phenotypes, face targets and body parts)."""

# MakeHuman macro age: 0.5 = 25 years, 0.5625 ~ 31, 1.0 = 90.
# Procedural hero styles built by hair_hd.py (curly, wavy) and hair_extra.py (bun, frenchbraid); the MakeHuman
# community assets previously used for "bun", "frenchbraid" and the beards were removed (licence) - see THIRD_PARTY_LICENSES.md.
PROCEDURAL_HAIR = ["curly", "wavy", "bun", "frenchbraid"]
HAIR_STYLES_ALL = {
    "short": "short02/short02.mhclo", "buzz": "short04/short04.mhclo", "undercut": "short03/short03.mhclo",
    "swept": "short01/short01.mhclo", "ponytail": "ponytail01/ponytail01.mhclo", "braid": "braid01/braid01.mhclo",
    "bob": "bob02/bob02.mhclo", "bobshort": "bob01/bob01.mhclo", "long": "long01/long01.mhclo", "afro": "afro01/afro01.mhclo",
    "messy": "cortu_short_messy_hair/cortu_short_messy_hair.mhclo",
}

CHARACTERS = {
    "kael": {
        "name": "Kael",
        # Heroic vanguard build: ~1.85 m, broad shoulders, thick neck and traps, muscular chest and arms, V torso.
        "phenotype": {
            "gender": 1.0, "age": 0.56, "muscle": 0.88, "weight": 0.54, "height": 0.61,
            "proportions": 1.0, "cupsize": 0.5, "firmness": 0.5,
            "race": {"asian": 0.35, "caucasian": 0.45, "african": 0.20},
        },
        "targets": [
            # Body
            ("torso/measure-shoulder-dist-incr", 0.55), ("torso/torso-vshape-incr", 0.7), ("torso/torso-muscle-pectoral-incr", 0.45),
            ("torso/torso-muscle-dorsi-incr", 0.6), ("torso/measure-waist-circ-decr", 0.4), ("hip/hip-scale-horiz-decr", 0.2), ("stomach/stomach-tone-incr", 0.4),
            ("neck/measure-neck-circ-incr", 0.75), ("neck/neck-scale-horiz-incr", 0.35), ("neck/neck-back-scale-depth-incr", 0.4),
            ("arms/l-upperarm-shoulder-muscle-incr", 0.6), ("arms/r-upperarm-shoulder-muscle-incr", 0.6),
            ("arms/l-upperarm-muscle-incr", 0.45), ("arms/r-upperarm-muscle-incr", 0.45),
            ("arms/l-lowerarm-muscle-incr", 0.4), ("arms/r-lowerarm-muscle-incr", 0.4),
            ("legs/l-upperleg-muscle-incr", 0.35), ("legs/r-upperleg-muscle-incr", 0.35),
            ("legs/l-lowerleg-muscle-incr", 0.35), ("legs/r-lowerleg-muscle-incr", 0.35),
            ("hands/l-hand-scale-incr", 0.05), ("hands/r-hand-scale-incr", 0.05),
            # Face: strong square jaw and chin, heavy brow ridge, lean cheeks, straight nose with a slight bridge.
            ("chin/chin-prominent-incr", 0.4), ("chin/chin-width-incr", 0.45), ("chin/chin-height-incr", 0.15), ("chin/chin-bones-incr", 0.55),
            ("head/head-square", 0.5), ("head/head-age-incr", 0.32), ("head/head-scale-vert-decr", 0.1), ("eyebrows/eyebrows-trans-forward", 0.35), ("cheek/l-cheek-volume-decr", 0.3), ("cheek/r-cheek-volume-decr", 0.3), ("chin/chin-cleft-incr", 0.25),
            ("eyebrows/eyebrows-trans-down", 0.3), ("forehead/forehead-nubian-incr", 0.35), ("forehead/forehead-temple-decr", 0.3),
            ("nose/nose-scale-vert-incr", 0.15), ("nose/nose-width1-decr", 0.15), ("nose/nose-hump-incr", 0.25), ("nose/nose-point-width-decr", 0.2),
            ("cheek/l-cheek-bones-incr", 0.45), ("cheek/r-cheek-bones-incr", 0.45), ("cheek/l-cheek-inner-decr", 0.4), ("cheek/r-cheek-inner-decr", 0.4),
            ("mouth/mouth-scale-horiz-decr", 0.05), ("mouth/mouth-upperlip-volume-decr", 0.15),
            ("eyes/l-eye-height2-decr", 0.2), ("eyes/r-eye-height2-decr", 0.2), ("eyes/l-eye-bag-decr", 0.3), ("eyes/r-eye-bag-decr", 0.3),
        ],
        "skin": "young_caucasian_male/young_caucasian_male.mhmat",
        "eyes_material": "brown",
        "eyebrows": "eyebrow001/eyebrow001.mhclo",
        "eyelashes": "eyelashes02/eyelashes02.mhclo",
        "hair": "short02/short02.mhclo",
        "clothes": [],
        "default_hair": "short",
        "extra_hair": {k: v for k, v in HAIR_STYLES_ALL.items() if k != "short"},
        "extra_clothes": {"moustache": "rehmanpolanski_moustache_viking/rehmanpolanski_moustache_viking.mhclo"},
    },
    "lyra": {
        "name": "Lyra",
        # Athletic, strong phase engineer: ~1.72 m, defined shoulders, arms and legs (not skinny).
        "phenotype": {
            "gender": 0.0, "age": 0.53, "muscle": 0.8, "weight": 0.55, "height": 0.62,
            "proportions": 1.0, "cupsize": 0.45, "firmness": 0.65,
            "race": {"asian": 0.40, "caucasian": 0.40, "african": 0.20},
        },
        "targets": [
            # Body
            ("torso/measure-shoulder-dist-incr", 0.35), ("torso/torso-vshape-incr", 0.25), ("torso/measure-waist-circ-decr", 0.2),
            ("stomach/stomach-tone-incr", 0.4), ("neck/measure-neck-circ-incr", 0.2),
            ("arms/l-upperarm-shoulder-muscle-incr", 0.4), ("arms/r-upperarm-shoulder-muscle-incr", 0.4),
            ("arms/l-upperarm-muscle-incr", 0.3), ("arms/r-upperarm-muscle-incr", 0.3),
            ("arms/l-lowerarm-muscle-incr", 0.25), ("arms/r-lowerarm-muscle-incr", 0.25),
            ("legs/l-upperleg-muscle-incr", 0.45), ("legs/r-upperleg-muscle-incr", 0.45),
            ("legs/l-lowerleg-muscle-incr", 0.4), ("legs/r-lowerleg-muscle-incr", 0.4), ("buttocks/buttocks-volume-incr", 0.2),
            # Face: high defined cheekbones, almond eyes with lifted outer corners, fuller lips, defined jaw and chin.
            ("cheek/l-cheek-bones-incr", 0.55), ("cheek/r-cheek-bones-incr", 0.55), ("cheek/l-cheek-inner-decr", 0.3), ("cheek/r-cheek-inner-decr", 0.3),
            ("mouth/mouth-upperlip-volume-incr", 0.3), ("mouth/mouth-lowerlip-volume-incr", 0.3), ("mouth/mouth-cupidsbow-incr", 0.35),
            ("eyebrows/eyebrows-angle-up", 0.2), ("chin/chin-width-decr", 0.15), ("chin/chin-prominent-incr", 0.2), ("chin/chin-bones-incr", 0.2),
            ("head/head-oval", 0.45), ("nose/nose-scale-horiz-decr", 0.15), ("nose/nose-point-width-decr", 0.25), ("nose/nose-point-up", 0.15),
            ("nose/nose-width1-decr", 0.15), ("eyes/l-eye-corner2-up", 0.3), ("eyes/r-eye-corner2-up", 0.3),
            ("eyes/l-eye-bag-decr", 0.4), ("eyes/r-eye-bag-decr", 0.4), ("forehead/forehead-temple-decr", 0.2),
        ],
        "skin": "young_caucasian_female/young_caucasian_female.mhmat",
        "eyes_material": "brown",
        "eyebrows": "eyebrow010/eyebrow010.mhclo",
        "eyelashes": "eyelashes01/eyelashes01.mhclo",
        "hair": "ponytail01/ponytail01.mhclo",
        "clothes": [],
        "default_hair": "ponytail",
        "extra_hair": {k: v for k, v in HAIR_STYLES_ALL.items() if k != "ponytail"},
    },
}

HAIR_STYLES = {
    # game id -> MakeHuman system hair asset
    "short": "short02/short02.mhclo",
    "buzz": "short04/short04.mhclo",
    "undercut": "short03/short03.mhclo",
    "swept": "short01/short01.mhclo",
    "ponytail": "ponytail01/ponytail01.mhclo",
    "braid": "braid01/braid01.mhclo",
    "bob": "bob02/bob02.mhclo",
    "bobshort": "bob01/bob01.mhclo",
    "long": "long01/long01.mhclo",
    "afro": "afro01/afro01.mhclo",
}


# ---- NPCs (MakeHuman clothing; expression morphs only)
NPCS = {
    "oren": {
        "name": "Oren", "npc": True,
        "phenotype": {"gender": 1.0, "age": 0.82, "muscle": 0.55, "weight": 0.62, "height": 0.52, "proportions": 0.6,
                      "cupsize": 0.5, "firmness": 0.5, "race": {"asian": 0.2, "caucasian": 0.6, "african": 0.2}},
        "targets": [("head/head-age-incr", 0.6), ("nose/nose-scale-vert-incr", 0.3), ("chin/chin-width-incr", 0.3)],
        "skin": "middleage_caucasian_male/middleage_caucasian_male.mhmat",
        "eyebrows": "eyebrow002/eyebrow002.mhclo", "eyelashes": "eyelashes01/eyelashes01.mhclo",
        "hair": "short01/short01.mhclo",
        "clothes": ["male_casualsuit05/male_casualsuit05.mhclo", "toigo_ankle_boots_male/toigo_ankle_boots_male.mhclo"],
        "beard": "full",
        "tints": {"hair": "#8d8a86", "Facial": "#7a7570"},
    },
    "mira": {
        "name": "Mira", "npc": True,
        "phenotype": {"gender": 0.0, "age": 0.6, "muscle": 0.5, "weight": 0.5, "height": 0.42, "proportions": 0.7,
                      "cupsize": 0.45, "firmness": 0.55, "race": {"asian": 0.6, "caucasian": 0.3, "african": 0.1}},
        "targets": [("cheek/l-cheek-bones-incr", 0.3), ("cheek/r-cheek-bones-incr", 0.3)],
        "skin": "young_asian_female/young_asian_female.mhmat",
        "eyebrows": "eyebrow009/eyebrow009.mhclo", "eyelashes": "eyelashes01/eyelashes01.mhclo",
        "hair": "bob02/bob02.mhclo",
        "clothes": ["cortu_cargo_pants/cortu_cargo_pants.mhclo", "toigo_ankle_boots_female/toigo_ankle_boots_female.mhclo"],
        "gear": ["headset", "satchel"],
    },
    "tomas": {
        "name": "Tomas", "npc": True,
        "phenotype": {"gender": 1.0, "age": 0.55, "muscle": 0.6, "weight": 0.42, "height": 0.55, "proportions": 0.7,
                      "cupsize": 0.5, "firmness": 0.5, "race": {"asian": 0.1, "caucasian": 0.2, "african": 0.7}},
        "targets": [("chin/chin-prominent-incr", 0.2)],
        "skin": "young_african_male/young_african_male.mhmat",
        "eyebrows": "eyebrow004/eyebrow004.mhclo", "eyelashes": "eyelashes02/eyelashes02.mhclo",
        "hair": "short04/short04.mhclo",
        "clothes": ["elvs_crude_t-shirt_male/elvs_crude_t-shirt_male.mhclo", "cortu_cargo_pants/cortu_cargo_pants.mhclo",
                    "culturalibre_male_boots/culturalibre_male_boots.mhclo"],
        "gear": ["goggles", "scarf"],
    },
    "maren": {
        "name": "Maren", "npc": True, "echo": True,
        "phenotype": {"gender": 0.0, "age": 0.72, "muscle": 0.45, "weight": 0.48, "height": 0.5, "proportions": 0.7,
                      "cupsize": 0.45, "firmness": 0.5, "race": {"asian": 0.3, "caucasian": 0.6, "african": 0.1}},
        "targets": [("head/head-age-incr", 0.3)],
        "skin": "middleage_caucasian_female/middleage_caucasian_female.mhmat",
        "eyebrows": "eyebrow010/eyebrow010.mhclo", "eyelashes": "eyelashes01/eyelashes01.mhclo",
        "hair": "",  # procedural low chignon (hair_extra.py neat_bun)
        "clothes": ["female_elegantsuit01/female_elegantsuit01.mhclo", "toigo_flats/toigo_flats.mhclo"],
    },
    "nia": {
        "name": "Nia", "npc": True, "echo": True,
        "phenotype": {"gender": 0.0, "age": 0.24, "muscle": 0.5, "weight": 0.45, "height": 0.5, "proportions": 0.5,
                      "cupsize": 0.0, "firmness": 0.5, "race": {"asian": 0.4, "caucasian": 0.4, "african": 0.2}},
        "targets": [],
        "skin": "young_caucasian_female/young_caucasian_female.mhmat",
        "eyebrows": "eyebrow010/eyebrow010.mhclo", "eyelashes": "eyelashes01/eyelashes01.mhclo",
        "hair": "bob01/bob01.mhclo",
        "clothes": ["toigo_harem_pants/toigo_harem_pants.mhclo", "toigo_mj_cloth_shoes/toigo_mj_cloth_shoes.mhclo"],
    },
}
CHARACTERS.update(NPCS)
