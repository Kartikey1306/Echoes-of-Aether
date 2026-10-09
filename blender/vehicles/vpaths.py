"""Shared paths for the vehicle pipeline (blender/vehicles -> Assets/Art/Vehicles)."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
UNITY_VEH = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets", "Art", "Vehicles")
MODELS = os.path.join(UNITY_VEH, "Models")
TEXTURES = os.path.join(UNITY_VEH, "Textures")
OUT = os.path.join(HERE, "out")            # build state: records, logs, verify reports
RECORDS = os.path.join(OUT, "records")
PREVIEWS = os.path.join(HERE, "previews")
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"

for _d in (MODELS, TEXTURES, OUT, RECORDS, PREVIEWS):
    os.makedirs(_d, exist_ok=True)
