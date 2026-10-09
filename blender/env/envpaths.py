"""Shared paths for the environment pipeline."""
import os

ROOT = "/Users/kartikey/Desktop/Game"
ENV = os.path.join(ROOT, "blender", "env")
STATE = os.path.join(ENV, "out")  # intermediate json state (bake info, asset records)
PREVIEWS = os.path.join(ENV, "previews")
UNITY_ENV = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets", "Art", "Environment")
TEXTURES = os.path.join(UNITY_ENV, "Textures")
MODELS = os.path.join(UNITY_ENV, "Models")
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
