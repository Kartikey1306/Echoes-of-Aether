"""Bootstrap that reuses the environment pipeline (blender/env: envkit modelling helpers, FBX export, records) for the
street kit without touching the Environment kit: envpaths is re-pointed at Assets/Art/CityStreet and blender/city_street/out
before anything else imports it, and the st_* materials are merged into the shared material registry.

    import stkit; K = stkit.K
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import stpaths  # noqa: E402

if stpaths.ENV not in sys.path:
    sys.path.insert(1, stpaths.ENV)
import envpaths  # noqa: E402

envpaths.STATE = stpaths.OUT
envpaths.PREVIEWS = stpaths.PREVIEWS
envpaths.UNITY_ENV = stpaths.UNITY_ST
envpaths.TEXTURES = stpaths.TEXTURES
envpaths.MODELS = stpaths.MODELS

import matdefs  # noqa: E402
import stmats  # noqa: E402

for _k, _v in stmats.REGISTRY.items():
    matdefs.REGISTRY[_k] = _v

import envkit as K  # noqa: E402,F401
