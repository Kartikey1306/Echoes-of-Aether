"""Procedural updo / braid styles built with the customisation hair system (blender/custom, used read-only).

Replaces the removed MakeHuman community assets:
  hero "bun"         Kael: braided man bun with a fade (custom recipe k_man_bun_fade); Giva: messy bun (l_messy_bun)
  hero "frenchbraid" both heroes: woven fishtail braid down the back (l_fishtail_braid)
  Maren's hair       neat low chignon (neat_bun below, built from the same primitives)

Runs in its own Blender process because blender/custom pins snapshots of gear/texbake in blender/custom/lib:
  blender -b <scene.blend> --python hair_extra.py -- <cid> <style=recipe,...> [--female] [--name Kael]
Scene: blender/custom/cache/<cid>_ref.blend for the heroes (exported outfit as collision meshes U_*), or the NPC base
saved by npc_hd.py --save-base. Writes blender/out/hd/extra/<cid>_<style>.blend (one object) and _Hair.png (2K atlas,
neutral grey RGBA, alpha-tested). Nothing is written into blender/custom.
"""
import sys, os
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
CUSTOM = os.path.abspath(os.path.join(HERE, "..", "custom"))
sys.path.insert(0, CUSTOM)
import bpy, json, math
import numpy as np
import common as C            # puts blender/custom/lib first on sys.path (their pinned gear/texbake)
import gear
import hairlib as HL
from hairlib import flow_to, flow_down, bun as bun_geo
import hair_build as HBM
from hair_styles import k_man_bun_fade, l_messy_bun, l_fishtail_braid

OUT = os.path.abspath(os.path.join(HERE, "..", "out", "hd", "extra"))
R_ = np.radians


def neat_bun(b):
    """Low, tidy chignon for Maren: hair gathered smoothly to the nape-crown, wrapped bun, a few soft wisps."""
    H = b.H
    b.nap = False
    b.cutoff = 0.38
    A = b.anchor(180, 30, 0.006)
    b.vol_thick = lambda az, el: np.full(np.shape(az), 0.0035)
    b.vol_lum = 0.62
    b.flow = lambda P: flow_to(H, P, A)
    b.tiles = ["sleek"] * 12 + ["wavy"] * 4 + ["wisp"] * 8
    b.gather(250, lambda az, el, P: np.ones(len(az), bool), A, off=(0.003, 0.009), width=(0.021, 0.015), tiles=(0, 11), min_d=0.0085,
             hug=1.1, loose=0.12)
    nA = H.radial(A[None])[0]
    bun_geo(H, b.part, A + nA * 0.026, nA * 0.85 + np.array((0, 0.2, 0.05)), 0.03, (0, 11), 1.0, b.rng, cards=70, messy=0.2, wraps=3.0)
    gf = b.guard_face(0.008)
    b.locks_(8, lambda az, el, P: (np.abs(az) > R_(55)) & (np.abs(az) < R_(80)) & (el < R_(22)), 0.09, flow=lambda P: flow_down(H, P),
             segs=12, lift=0.1, stiff=1.0, grav=0.7, off=(0.005, 0.01), hug=0.6, width=(0.009, 0.004), tiles=(16, 23),
             wave=(0.008, 0.05), guard=gf, min_d=0.008)


RECIPES = {"k_man_bun_fade": k_man_bun_fade, "l_messy_bun": l_messy_bun, "l_fishtail_braid": l_fishtail_braid, "neat_bun": neat_bun}


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    cid = a[0]
    jobs = [j.split("=") for j in a[1].split(",")]
    female = "--female" in a
    name = a[a.index("--name") + 1] if "--name" in a else cid.capitalize()
    rig = bpy.data.objects[name]
    body = bpy.data.objects[name + ".body"]
    ctx = gear.Ctx(body, rig, name)
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name.startswith("U_") and o.name[2:] in ("Top", "Collar", "Jacket", "ChestRig", "PauldronL", "PauldronR",
                                                                         "PauldronLameL", "PauldronLameR", "ShoulderR", "Harness", "ChestPlate"):
            ctx.push_stack(o)
    H = HL.Head(ctx, female=female)
    os.makedirs(OUT, exist_ok=True)
    meta = {}
    for i, (sid, rname) in enumerate(jobs):
        b = HBM.HB(H, ctx, "lyra" if female else "kael", sid, 11 + i * 101 + len(sid))
        RECIPES[rname](b)
        obj, atlas = b.build()
        C.write_png(atlas, os.path.join(OUT, f"{cid}_{sid}_Hair.png"), "RGBA")
        obj.name = f"extra_{sid}"
        obj.data.name = obj.name
        path = os.path.join(OUT, f"{cid}_{sid}.blend")
        bpy.data.libraries.write(path, {obj}, fake_user=True, compress=True)
        meta[sid] = {"recipe": rname, "cutoff": b.cutoff, "kind": b.kind, "tris": C.tris(obj)}
        print("EXTRA", cid, sid, meta[sid], flush=True)
    with open(os.path.join(OUT, f"{cid}_meta.json"), "w") as f:
        json.dump(meta, f, indent=1)


main()
