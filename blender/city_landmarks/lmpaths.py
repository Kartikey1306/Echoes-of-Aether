"""Shared paths for the city landmarks pipeline (blender/city_landmarks -> Assets/Art/CityLandmarks).

The landmark kit is its own art kit (runtime manifest Resources/Env/landmarks_manifest.json); it shares the
environment kit's tiling materials and the building atlases (building_trim_atlas / emit_building_atlas, which
belong to the environment kit's Building_* assets) by material name.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ENV_SRC = os.path.join(ROOT, "blender", "env")
UNITY = os.path.join(ROOT, "unity", "EchoesOfAether")
KIT = os.path.join(UNITY, "Assets", "Art", "CityLandmarks")
MODELS = os.path.join(KIT, "Models")
TEXTURES = os.path.join(KIT, "Textures")
ENV_KIT = os.path.join(UNITY, "Assets", "Art", "Environment")
ENV_TEXTURES = os.path.join(ENV_KIT, "Textures")
ENV_STATE = os.path.join(ENV_SRC, "out")
OUT = os.path.join(HERE, "out")            # build state: records, atlas layout, logs
RECORDS = os.path.join(OUT, "records")
PREVIEWS = os.path.join(HERE, "previews")
LOGS = os.path.join(HERE, "logs")
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
ATLAS_LAYOUT = os.path.join(OUT, "atlas_layout.json")

for _d in (OUT, RECORDS, PREVIEWS, LOGS):
    os.makedirs(_d, exist_ok=True)
