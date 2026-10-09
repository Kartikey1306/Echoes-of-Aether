"""Quick in-process build + Cycles render of generator tests (no export).

  Blender -b --factory-startup --python testrender.py -- out.png [test names...] [--lod N] [--samples N] [--street]
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402

import lmkit as L  # noqa: E402
from lmkit import K  # noqa: E402
import lmparts as P  # noqa: E402
import lmpreview as LP  # noqa: E402
import styles as ST  # noqa: E402


def t_market():
    fl = L.Floors(11, base=0.45)
    P.block(-10, -7, 10, 7, 21.0, ST.MARKET, fl, 11, faces="sewn", street="se", roofkind="market")


def t_stack():
    fl = L.Floors(12, base=0.5)
    P.block(-8, -6, 8, 6, 36.0, ST.STACK, fl, 12, faces="sewn", street="sw", roofkind="kowloon")


def t_corp():
    fl = L.Floors(13, base=0.4)
    P.block(-9, -9, 9, 9, 48.0, ST.CORP, fl, 13, faces="sewn", street="s", roofkind="corp")


def t_canal():
    fl = L.Floors(14, base=0.45)
    P.block(-9, -6, 9, 6, 22.0, ST.CANAL, fl, 14, faces="sewn", street="s", roofkind="canal")


def t_foundry():
    fl = L.Floors(15, base=0.3)
    P.block(-12, -9, 12, 9, 15.0, ST.FOUNDRY, fl, 15, faces="sewn", street="s", roofkind="foundry")


TESTS = {"market": t_market, "stack": t_stack, "corp": t_corp, "canal": t_canal, "foundry": t_foundry}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = argv[0]
    lodsel, samples, street = 0, 64, False
    names = []
    i = 1
    while i < len(argv):
        if argv[i] == "--lod":
            lodsel = int(argv[i + 1]); i += 2
        elif argv[i] == "--samples":
            samples = int(argv[i + 1]); i += 2
        elif argv[i] == "--street":
            street = True; i += 1
        else:
            names.append(argv[i]); i += 1
    names = names or list(TESTS)
    K.reset()
    objs = []
    x = 0.0
    for n in names:
        lods = L.build_lods("T_" + n, TESTS[n], lods=3)
        for k, o in enumerate(lods):
            print(f"[test] {n} LOD{k} tris {K.tris(o)} mats {[m.name for m in o.data.materials]}")
        keep = lods[min(lodsel, len(lods) - 1)]
        for o in lods:
            if o is not keep:
                bpy.data.objects.remove(o)
        mn, mx = K.bounds(keep)
        keep.location.x = x - mn[0]
        x += (mx[0] - mn[0]) + 10
        objs.append(keep)
    LP.setup(samples=samples, res=(1600, 900))
    LP.night_world(0.5)
    LP.apply_materials(objs)
    mn, mx = LP.bounds(objs)
    LP.ground(1200, "asphalt")
    LP.moon(0.12)
    LP.city_lights(mn, mx, seed=3, n=8, power=0.8)
    c = (mn + mx) / 2
    if street:
        LP.camera((c.x, mn.y - 2, 9), 1.0, 0, 0, lens=24, height=1.7)
        cam = bpy.context.scene.camera
        cam.location = (c.x - (mx.x - mn.x) * 0.15, mn.y - 22, 1.7)
        look = (c.x, mn.y, 12)
        from mathutils import Vector
        cam.rotation_euler = (Vector(look) - cam.location).to_track_quat("-Z", "Y").to_euler()
    else:
        size = max(mx.x - mn.x, (mx.z - mn.z) * 1.6)
        LP.camera((c.x, c.y, mn.z + (mx.z - mn.z) * 0.4), size * 0.95, 20, 10, lens=35)
    LP.render(out)


main()
