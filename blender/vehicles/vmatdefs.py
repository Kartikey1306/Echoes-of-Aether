"""Vehicle material registry: one entry per Unity material (slot name == material name).

kind:  baked  -> own texture set        tint -> own BaseColor (+ MaskMap), shares Normal with `parent`
       param  -> no textures, URP Lit parameters only
uv:    world  -> UV0 = metres (box projection), tiling = 1 / tile
       fit    -> UV0 authored 0..1 per panel (atlas / sign)
"""

# Texture sizes: body paint 2K, everything else 1K (task brief).
BODY = 2048
DETAIL = 1024

# Emission colours are linear RGB; intensity is the HDR multiplier for _EmissionColor.
EMISSIVE = {
    "veh_headlight": {"emission": [0.86, 0.93, 1.0], "intensity": 5.0, "lens": [0.80, 0.84, 0.88]},
    "veh_taillight": {"emission": [1.0, 0.045, 0.06], "intensity": 4.5, "lens": [0.42, 0.03, 0.04]},
    "veh_underglow": {"emission": [0.0, 0.80, 1.0], "intensity": 4.0, "lens": [0.55, 0.85, 0.9]},
    "veh_neon": {"emission": [1.0, 0.10, 0.72], "intensity": 5.0, "lens": [0.85, 0.35, 0.75]},
    "veh_hazard": {"emission": [1.0, 0.45, 0.02], "intensity": 4.0, "lens": [0.75, 0.38, 0.05]},
}

PAINTS = {
    # name: (base sRGB, metallic, metallic in flakes, smoothness, label)
    "veh_paint_midnight": ((0.032, 0.036, 0.052), 0.30, 0.95, 0.90, "midnight black (blue-black pearl)"),
    "veh_paint_gunmetal": ((0.165, 0.175, 0.19), 0.72, 1.00, 0.84, "gunmetal metallic"),
    "veh_paint_pearl": ((0.86, 0.865, 0.85), 0.12, 0.65, 0.90, "pearl white"),
    "veh_paint_magenta": ((0.60, 0.025, 0.36), 0.55, 1.00, 0.91, "candy magenta"),
    "veh_paint_cyan": ((0.36, 0.82, 0.92), 0.95, 1.00, 0.92, "cyan chrome"),
    "veh_paint_taxi": ((0.96, 0.70, 0.04), 0.10, 0.60, 0.88, "taxi yellow"),
}

REGISTRY = {}


def _reg(name, **kw):
    REGISTRY[name] = kw


for _n, (_c, _m, _mf, _s, _lab) in PAINTS.items():
    _reg(_n, kind="tint" if _n != "veh_paint_midnight" else "baked", parent="veh_paint_midnight", uv="world",
         tile=2.0, res=BODY, ownMask=True, label=_lab, clearCoat=True, preview={"coat": 1.0, "coat_rough": 0.03})
REGISTRY["veh_paint_midnight"].pop("parent")

_reg("veh_paint_wrecked", kind="baked", uv="world", tile=2.0, res=BODY, label="wrecked gunmetal: rust, scorch, chips")
_reg("veh_burnt", kind="baked", uv="world", tile=2.0, res=BODY, label="fire-gutted steel: char, ash, heat rust")
_reg("veh_chrome", kind="baked", uv="world", tile=1.0, res=DETAIL, label="polished chrome")
_reg("veh_carbon", kind="baked", uv="world", tile=0.25, res=DETAIL, label="2x2 twill carbon fibre, clear coated",
     preview={"coat": 1.0, "coat_rough": 0.05})
_reg("veh_metal", kind="baked", uv="world", tile=0.5, res=DETAIL, label="satin brushed gunmetal (rims, brakes, chassis)")
_reg("veh_rubber", kind="baked", uv="world", tile=0.5, res=DETAIL, label="tyre rubber")
_reg("veh_plastic", kind="baked", uv="world", tile=0.5, res=DETAIL, label="textured matte black plastic (liners, under-tray)")
_reg("veh_interior", kind="baked", uv="world", tile=0.5, res=DETAIL, label="quilted charcoal leather, magenta stitch")
_reg("veh_decal", kind="baked", uv="fit", tile=None, res=DETAIL, label="atlas: invented-glyph badges, ID plate, checker, hazard, fleet marks")
_reg("veh_trim", kind="param", label="piano-black gloss trim", unity={"surface": "Opaque", "baseColor": [0.012, 0.012, 0.014, 1.0], "metallic": 0.0, "smoothness": 0.9})
_reg("veh_glass", kind="param", label="tinted glass (param)", unity={"surface": "Transparent", "blend": "Alpha", "baseColor": [0.035, 0.05, 0.065, 0.62], "metallic": 0.0, "smoothness": 0.97, "cull": "Off"})
_reg("veh_glass_cracked", kind="baked", uv="world", tile=1.0, res=DETAIL, label="cracked tinted glass (RGBA, A = opacity)",
     unity={"surface": "Transparent", "blend": "Alpha", "cull": "Off"})
_reg("veh_led", kind="shared", uv="world", tile=0.25, res=DETAIL, label="shared Normal + MaskMap for LED light units")
for _n, _d in EMISSIVE.items():
    _reg(_n, kind="tint", parent="veh_led", uv="world", tile=0.25, res=DETAIL, emissive=True, label=f"emissive LED ({_n[4:]})",
         emission=_d["emission"], emissionIntensity=_d["intensity"])
_reg("veh_thruster", kind="baked", uv="world", tile=0.3, res=DETAIL, emissive=True, label="emissive honeycomb thrust grille",
     emission=[0.30, 0.70, 1.0], emissionIntensity=6.0)
_reg("veh_navlight", kind="baked", uv="fit", tile=None, res=256, emissive=True, label="nav lights: UV u<0.5 red (port), u>0.5 green (starboard), v>0.75 white strobe",
     emission=[1.0, 1.0, 1.0], emissionIntensity=3.5)
_reg("veh_holo_sign", kind="baked", uv="fit", tile=None, res=DETAIL, emissive=True, label="holographic glyph sign (additive, RGBA)",
     emission=[1.0, 1.0, 1.0], emissionIntensity=2.4, unity={"surface": "Transparent", "blend": "Additive", "cull": "Off"})

EMISSIVE_NAMES = [n for n, d in REGISTRY.items() if d.get("emissive")]


def tex_path(name, chan):
    """Texture path relative to Assets/Art/Vehicles."""
    d = REGISTRY[name]
    own = {"BaseColor", "Emission"}
    if d.get("ownMask"):
        own.add("MaskMap")
    if d["kind"] == "tint" and chan not in own:
        p = d["parent"]
        return f"Textures/{p}/{p}_{chan}.png"
    return f"Textures/{name}/{name}_{chan}.png"


def channels(name):
    d = REGISTRY[name]
    if d["kind"] == "param":
        return []
    ch = ["BaseColor", "Normal", "MaskMap"]
    if d.get("emissive"):
        ch.append("Emission")
    if d["kind"] == "shared":
        ch = ["Normal", "MaskMap"]
    return ch


def preview_colour(name):
    if name in PAINTS:
        return PAINTS[name][0]
    return (0.3, 0.3, 0.3)
