"""Shared paths for the street-level kit (blender/city_street -> Assets/Art/CityStreet, manifest 'street_manifest')."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ENV = os.path.join(ROOT, "blender", "env")                      # the environment pipeline we reuse (read only)
UNITY_ST = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets", "Art", "CityStreet")
MODELS = os.path.join(UNITY_ST, "Models")
TEXTURES = os.path.join(UNITY_ST, "Textures")
DECALS = os.path.join(UNITY_ST, "Decals")
# Runtime-loaded extras (macro variation maps for the road / sidewalk detail layer): any folder named Resources works.
RUNTIME = os.path.join(UNITY_ST, "Resources", "CityStreet")
OUT = os.path.join(HERE, "out")            # build state: asset records, bake info, decal entries
PREVIEWS = os.path.join(HERE, "previews")
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"

for _d in (MODELS, TEXTURES, DECALS, RUNTIME, OUT, PREVIEWS):
    os.makedirs(_d, exist_ok=True)
