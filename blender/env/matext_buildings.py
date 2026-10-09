"""Shared building atlases (owned by blender/city_landmarks; textures from atlas_build.py) registered here so that a
full env write_manifest.py run keeps the materials the atlas-remapped Building_* assets use. 'param' kind with a
'textures' block: write_manifest copies the unity dict as is and EnvLibraryBuilder builds a textured URP/Lit material."""

_T = "Textures/{0}/{0}_{1}.png"


def _atlas(name, emissive, preview):
    tex = {k: _T.format(name, k) for k in ("BaseColor", "Normal", "MaskMap")}
    tex["Occlusion"] = tex["MaskMap"]
    u = {"surface": "Opaque", "uvMode": "atlas", "tiling": [1.0, 1.0], "textures": tex, "textureSize": 2048,
         "maxTextureSize": {"desktop": 2048, "webgl": 1024}, "normalScale": 1.0, "occlusionStrength": 1.0}
    if emissive:
        tex["Emission"] = _T.format(name, "Emission")
        u.update({"emissionColor": [1.0, 1.0, 1.0], "emissionIntensity": 6.0})
    return {"kind": "param", "unity": u, "preview": preview}


REGISTRY = {
    "building_trim_atlas": _atlas("building_trim_atlas", False, (0.1, 0.1, 0.11)),
    "emit_building_atlas": _atlas("emit_building_atlas", True, (0.3, 0.25, 0.2)),
}
