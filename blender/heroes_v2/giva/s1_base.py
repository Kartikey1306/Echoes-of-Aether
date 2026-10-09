"""Stage 1: Giva base human.

MPFB human from giva_def (phenotype + targets, mixamo_unity rig, CC0 system proxies), customisation morphs
(m_*_incr/decr) and expressions (x_*) captured as blend shapes on the body and bound proxies (eyes, brows, lashes,
teeth, tongue), helper geometry removed. Saves out/giva_base.blend.

  blender -b --python s1_base.py
"""
import bpy, sys, os, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE, os.path.join(HERE, "..", "..", "scripts")]
import numpy as np
import gv, mpfb_build, giva_def, morphs, meshutil
for m in (gv, mpfb_build, giva_def, morphs, meshutil):
    importlib.reload(m)
from meshutil import SurfaceBinding, add_shape_key, bake_shape_keys, get_co, set_co


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    body, rig = mpfb_build.build_human(giva_def.PHENOTYPE, giva_def.targets(), giva_def.ASSETS)
    gv.log("built", body.name, len(body.data.vertices))
    base, deltas = morphs.capture(body, True, custom=True)
    bake_shape_keys(body)
    set_co(body, base)
    parts = mpfb_build.find_parts(rig)
    for key, o in parts.items():
        if o is body:
            continue
        if o.data.shape_keys:
            bake_shape_keys(o)
        pts = get_co(o)
        bind = SurfaceBinding(body, base, pts, max_dist=0.2)
        n = 0
        for name, d in deltas.items():
            if key == "eyes" and name.startswith("x_"):
                continue   # eyeballs stay put for lid/mouth expressions
            dd = bind.transfer(d)
            if np.abs(dd).max() > 1e-5:
                add_shape_key(o, name, pts + dd)
                n += 1
        gv.log("proxy", key, o.name, len(pts), "shapes", n)
    for name, d in deltas.items():
        add_shape_key(body, name, base + d)
    meshutil.delete_verts_not_in_group(body, "body")
    for m in list(body.modifiers):
        if m.type == "MASK":
            body.modifiers.remove(m)
    meshutil.remove_groups(body, lambda n: n.startswith(("joint-", "helper-")) or n in ("HelperGeometry", "JointCubes"))
    names = {"body": "Body", "eyes": "Eyes", "brows": "Brows", "lashes": "Lashes", "teeth": "Teeth", "tongue": "Tongue"}
    for key, o in parts.items():
        o.name = names[key]
        o.data.name = names[key]
    gv.log("body verts", len(body.data.vertices), "faces", len(body.data.polygons), "shapes", len(body.data.shape_keys.key_blocks) - 1)
    hb = rig.data.bones[gv.P + "Head"]
    gv.log("head bone", tuple(round(x, 4) for x in rig.matrix_world @ hb.head_local))
    gv.save(os.path.join(gv.OUT, "giva_base.blend"))


main()
