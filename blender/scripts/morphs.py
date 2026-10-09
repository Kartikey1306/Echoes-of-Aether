"""Customisation and expression morphs captured from MakeHuman targets as blendshape deltas."""
import os
import bpy
import numpy as np
from bl_ext.user_default.mpfb.services.targetservice import TargetService
from bl_ext.user_default.mpfb.entities.objectproperties import HumanObjectProperties
from meshutil import mix_co

MPFB_TARGETS = None


def _target_path(name):
    p = TargetService.target_full_path(name)
    if not p:
        raise FileNotFoundError("target not found: " + name)
    return p


def _expr_path(unit, race="caucasian"):
    global MPFB_TARGETS
    if MPFB_TARGETS is None:
        import bl_ext.user_default.mpfb as m
        MPFB_TARGETS = os.path.join(os.path.dirname(m.__file__), "data", "targets")
    return os.path.join(MPFB_TARGETS, "expression", "units", race, unit + ".target.gz")


# Signed customisation morphs: name -> (incr spec, decr spec). A spec is a list of ("macro", key, delta) or
# ("target", target_name, weight).
CUSTOM = {
    "muscle": ([("macro", "muscle", 0.3)], [("macro", "muscle", -0.3)]),
    "weight": ([("macro", "weight", 0.3)], [("macro", "weight", -0.25)]),
    "shoulders": ([("target", "measure-shoulder-dist-incr", 1.0), ("target", "torso-vshape-incr", 0.5)],
                  [("target", "measure-shoulder-dist-decr", 1.0), ("target", "torso-vshape-decr", 0.5)]),
    "hips": ([("target", "measure-hips-circ-incr", 1.0), ("target", "hip-scale-horiz-incr", 0.4)],
             [("target", "measure-hips-circ-decr", 1.0), ("target", "hip-scale-horiz-decr", 0.4)]),
    "bust": ([("macro", "cupsize", 0.3)], [("macro", "cupsize", -0.3)]),
    "jaw": ([("target", "chin-bones-incr", 1.0), ("target", "chin-width-incr", 0.5)],
            [("target", "chin-bones-decr", 1.0), ("target", "chin-width-decr", 0.5)]),
    "chin": ([("target", "chin-prominent-incr", 1.0)], [("target", "chin-prominent-decr", 1.0)]),
    "cheeks": ([("target", "l-cheek-bones-incr", 1.0), ("target", "r-cheek-bones-incr", 1.0)],
               [("target", "l-cheek-bones-decr", 1.0), ("target", "r-cheek-bones-decr", 1.0)]),
    "noseSize": ([("target", "nose-scale-vert-incr", 0.8), ("target", "nose-scale-depth-incr", 0.8)],
                 [("target", "nose-scale-vert-decr", 0.8), ("target", "nose-scale-depth-decr", 0.8)]),
    "noseWidth": ([("target", "nose-scale-horiz-incr", 1.0)], [("target", "nose-scale-horiz-decr", 1.0)]),
    "lips": ([("target", "mouth-upperlip-volume-incr", 1.0), ("target", "mouth-lowerlip-volume-incr", 1.0)],
             [("target", "mouth-upperlip-volume-decr", 1.0), ("target", "mouth-lowerlip-volume-decr", 1.0)]),
    "eyeSize": ([("target", "l-eye-scale-incr", 0.8), ("target", "r-eye-scale-incr", 0.8)],
                [("target", "l-eye-scale-decr", 0.8), ("target", "r-eye-scale-decr", 0.8)]),
    "browHeight": ([("target", "eyebrows-trans-up", 1.0)], [("target", "eyebrows-trans-down", 1.0)]),
    "age": ([("target", "head-age-incr", 1.0)], None),
}

# Facial expressions for animation (blink, talk, emote).
EXPRESSIONS = {
    "blink_L": ["eye-left-closure"],
    "blink_R": ["eye-right-closure"],
    "mouthOpen": ["mouth-open"],
    "smile": ["mouth-corner-puller"],
    "frown": ["mouth-depression"],
    "browsUp": ["eyebrows-left-up", "eyebrows-right-up"],
    "browsDown": ["eyebrows-left-down", "eyebrows-right-down"],
    "squint": ["eye-left-slit", "eye-right-slit"],
}


def _apply_spec(body, spec):
    """Apply a spec; returns an undo callback."""
    undo = []
    macros = {}
    for kind, key, amt in spec:
        if kind == "macro":
            cur = HumanObjectProperties.get_value(key, entity_reference=body)
            macros[key] = cur
            HumanObjectProperties.set_value(key, float(min(1.0, max(0.0, cur + amt))), entity_reference=body)
        elif kind == "target":
            k = TargetService.load_target(body, _target_path(key), weight=amt, name="__m_" + key)
            undo.append(k.name)
        elif kind == "expr":
            k = TargetService.load_target(body, _expr_path(key), weight=amt, name="__e_" + key)
            undo.append(k.name)
    if macros:
        TargetService.reapply_macro_details(body)

    def restore():
        for n in undo:
            k = body.data.shape_keys.key_blocks.get(n)
            if k:
                body.shape_key_remove(k)
        if macros:
            for key, v in macros.items():
                HumanObjectProperties.set_value(key, v, entity_reference=body)
            TargetService.reapply_macro_details(body)
    return restore


def capture(body, female, custom=True):
    """Return (base_co, {shape_name: delta}) for every customisation and expression morph."""
    base = mix_co(body)
    deltas = {}
    for name, (inc, dec) in (CUSTOM.items() if custom else []):
        if name == "bust" and not female:
            continue
        for suffix, spec in (("_incr", inc), ("_decr", dec)):
            if not spec:
                continue
            restore = _apply_spec(body, spec)
            d = mix_co(body) - base
            restore()
            if np.abs(d).max() > 1e-5:
                deltas["m_" + name + suffix] = d
    for name, units in EXPRESSIONS.items():
        restore = _apply_spec(body, [("expr", u, 1.0) for u in units])
        d = mix_co(body) - base
        restore()
        if np.abs(d).max() > 1e-5:
            deltas["x_" + name] = d
    # Sanity: restoring must leave the base unchanged.
    err = np.abs(mix_co(body) - base).max()
    print("MORPHS captured", len(deltas), "restore error", float(err))
    return base, deltas
