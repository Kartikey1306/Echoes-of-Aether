"""Merge the per-item catalog fragments (cache/catalog/<category>/<cid>_<id>.json) into
unity/EchoesOfAether/Assets/Resources/Characters/Custom/catalog.json.

Runs with plain python3 (no bpy). Order follows the style/option tables below; unknown ids are appended.
"""
import json, os, glob

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "catalog")
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "unity", "EchoesOfAether", "Assets", "Resources", "Characters", "Custom", "catalog.json"))

ORDER = {
    "hair": {
        "kael": ["side_part_volume", "textured_fringe", "korean_perm", "mullet_fade", "curtain_bangs", "two_block", "textured_crop_design",
                 "flowing_waves", "modern_bowl", "man_bun_fade", "wolf_cut", "afro_taper", "textured_crow", "curly_medium",
                 "mohawk_fade", "burst_fade_mohawk", "edgy_caesar", "ivy_league", "french_crop_design", "emo_fringe"],
        "lyra": ["long_waves", "long_curls", "sleek_long", "high_ponytail", "braided_crown", "fishtail_braid", "space_buns", "bob_wavy",
                 "pixie", "side_shave_long", "wolf_cut_long", "curtain_bangs_long", "twin_tails", "messy_bun"],
    },
    "eyewear": {
        "kael": ["aviator", "round_wire", "rect_smart", "cyber_visor", "shades_led", "monocle_hud", "tactical_goggles"],
        "lyra": ["cat_eye_tech", "aviator", "round_wire", "rect_smart", "cyber_visor", "shades_led", "monocle_hud", "tactical_goggles"],
    },
    "armour": {
        "kael": ["vanguard_mk2", "aegis_exo", "phantom_stealth", "samurai_neo"],
        "lyra": ["netrunner_x", "valkyrie", "phantom_stealth_f", "arc_sentinel"],
    },
    "tattoos": {"kael": ["circuit_neck", "tech_tribal", "glyph_collar", "face_lines", "spine_piece", "full_sleeve", "throat_sigil", "hex_temple"],
                "lyra": ["circuit_sleeve", "neon_vine", "glyph_sleeves", "neck_lines", "back_piece", "tech_tribal", "cheek_circuit", "wrist_bands"]},
}
DEFAULTS = {  # user decisions (do not change): no curly hair on the heroes; Giva's new outfit covers neon_vine
    "kael": {"hair": "swept_fade", "eyewear": "none", "armour": "none", "tattoo": "circuit_neck"},
    "lyra": {"hair": "waves", "eyewear": "none", "armour": "none", "tattoo": "circuit_sleeve"},
}
NOTES = {
    "paths": "file / thumb / baseMap / ink / glow are Resources paths without extension (Resources.Load).",
    "hair": ("One material slot 'Hair'. baseMap is a neutral grey RGBA atlas (mean albedo ~0.745): set _BaseColor to the hair "
             "colour, alpha clip at alphaCutoff, double sided (cull off), smoothness ~0.35. kind 'rigid': MeshRenderer, parent "
             "to bone with identity local transform (localPos/localRot). kind 'skinned': SkinnedMeshRenderer exported with the "
             "full hero armature; remap bones by name onto the hero skeleton (weights only on Head/Neck/Spine2)."),
    "eyewear": ("Rigid, parent to bone with identity local transform. Slots: EyewearFrame (metal/lacquer), EyewearLens (tinted "
                "glass: transparent, smoothness ~0.95, lensTint/lensAlpha), Glow (emissive, tint glow)."),
    "armour": ("Skinned with the full hero armature (remap bones by name). Slots: Armor (baseMap/normal/maskMap, tint 'armor'), "
               "SuitSecondary (same textures, darker under-suit/soft parts), Glow, Glow2 (emissive strips), Screen (emissive "
               "panels). Blend shapes m_* / x_* match the body's customisation morphs: drive them with the body's weights. "
               "Hide the hero meshes listed in 'replaces' while worn. MaskMap: R metallic, G occlusion, B detail mask, A smoothness."),
    "tattoos": ("Textures in the hero's Body UV space (the exported Body mesh). ink: Unity Lit Detail Albedo x2 map (neutral "
                "grey 0.5 = no change, darker = ink), detail mask can stay white. glow: emission mask RGB (black = none), "
                "multiply by an animated intensity. Only skin present in the exported Body can show a tattoo (the outfit "
                "covers the rest); 'visibleOn' lists where each design shows with the default outfit."),
}


def merge():
    data = {"version": 1}
    for cat in ("hair", "eyewear", "armour", "tattoos"):
        items = []
        for cid in ("kael", "lyra"):
            frs = {}
            for p in glob.glob(os.path.join(CACHE, cat, f"{cid}_*.json")):
                try:
                    with open(p) as f:
                        e = json.load(f)
                    frs[e["id"]] = e
                except Exception as ex:
                    print("bad fragment", p, ex)
            order = ORDER[cat].get(cid, [])
            for k in order:
                if k in frs:
                    items.append(frs.pop(k))
            items += [frs[k] for k in sorted(frs)]
        data[cat] = items
    data["defaults"] = DEFAULTS
    data["notes"] = NOTES
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, OUT)
    print("CATALOG", OUT, {c: len(data[c]) for c in ("hair", "eyewear", "armour", "tattoos")})
    return data


if __name__ == "__main__":
    merge()
