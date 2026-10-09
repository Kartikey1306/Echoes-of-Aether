"""Quick geometry preview: build an outfit module on a cached base blend and render (no shape keys).
blender -b out/hd/<cid>_base.blend --python gear_preview.py -- <cid> <light> <shots> [--finalize]
"""
import bpy, sys, os, importlib, time
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import gear, preview_hd
a = sys.argv[sys.argv.index("--") + 1:]
cid = a[0]
mod = importlib.import_module("outfit_" + cid)
gear.PREVIEW.update({
    "Garment_Top": (gear.srgb("#3a3d42"), 0.75, 0.0, None), "Garment_Pants": (gear.srgb("#3d4036"), 0.8, 0.0, None),
    "Armor": (gear.srgb("#b5b2a8"), 0.38, 0.15, None), "Metal": (gear.srgb("#a4aab2"), 0.28, 1.0, None),
    "Gloves": (gear.srgb("#1d1e21"), 0.55, 0.0, None), "Belt": (gear.srgb("#2c2b29"), 0.6, 0.0, None),
    "Boots": (gear.srgb("#2b2826"), 0.5, 0.0, None), "SuitSecondary": (gear.srgb("#25272c"), 0.6, 0.0, None),
    "Glow": ((0.0, 0.8, 1.0), 0.3, 0.0, ((0.0, 0.8, 1.0), 12.0)), "Glow2": ((1.0, 0.1, 0.75), 0.3, 0.0, ((1.0, 0.1, 0.75), 12.0)),
    "Screen": ((0.02, 0.05, 0.06), 0.2, 0.0, ((0.0, 0.7, 1.0), 4.0)),
})
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.endswith(".body"))
for o in bpy.data.objects:
    if o.type == "MESH" and (".hair_" in o.name or ".facial_" in o.name):
        o.hide_render = True
t0 = time.time()
ctx = gear.Ctx(body, rig, rig.name)
objs = mod.build(ctx)
print("BUILD s", round(time.time() - t0, 1))
tot = 0
for k, o in objs.items():
    o.parent = rig
    tris = sum(len(p.vertices) - 2 for p in o.data.polygons)
    tot += tris
    print("PART", k, len(o.data.vertices), tris)
print("OUTFIT TRIS", tot)
if "--tex" in a:
    import texstage, texbake, paint_kael
    importlib.reload(texstage)
    # join detail parts into their contract meshes
    objs["Boots"] = gear.join([objs.pop("Boots"), objs.pop("BootsDetail")], f"{rig.name}_Boots")
    objs["ChestRig"] = gear.join([objs.pop("ChestRig"), objs.pop("ChestRigGear")], f"{rig.name}_ChestRig")
    allo = list(objs.values())
    hide = [o for o in bpy.data.objects if o.type == "MESH" and (".hair_" in o.name or ".facial_" in o.name)]
    tex_dir = os.path.join(os.path.dirname(__file__), "..", "out", "hd", "tex_" + cid)
    wip = os.path.join(tex_dir, "wip")
    pal = {"outfit": "#4b4f47", "accent": "#24262b"}
    L = ctx.L
    texstage.garment_atlas(allo, "Garment_Top", "Top", rig.name, paint_kael.top, L, 2048, tex_dir, wip, pal, hide)
    texstage.garment_atlas(allo, "Garment_Pants", "Pants", rig.name, paint_kael.pants, L, 2048, tex_dir, wip, pal, hide)
    texstage.hard_atlas(allo, "Armor", rig.name, paint_kael.armor, 2048, tex_dir, tint=(0.70, 0.69, 0.64), ao_hide=hide)
    texstage.hard_atlas(allo, "Boots", rig.name, paint_kael.boots, 1024, tex_dir, tint=None, ao_hide=hide)
    texstage.hard_atlas(allo, "Gloves", rig.name, lambda t, ao: paint_kael.gloves(t, ao, L), 1024, tex_dir, tint=(0.22, 0.23, 0.21), ao_hide=hide)
    texstage.flat_mats({"Metal": ("#a7adb5", 0.32, 1.0, None), "Belt": ("#2e2c29", 0.62, 0.0, None),
                        "Glow": ("#00e5ff", 0.3, 0.0, ("#00e5ff", 14.0)), "Glow2": ("#ff2bd6", 0.3, 0.0, ("#ff2bd6", 14.0)),
                        "Screen": ("#06141a", 0.15, 0.0, ("#00c8ff", 4.0)), "SuitSecondary": ("#24262b", 0.6, 0.0, None)})
if "--finalize" in a:
    for k, o in objs.items():
        ctx.finalize(o)
h, hz, face = preview_hd.measure()
preview_hd.OUT = os.path.join(os.path.dirname(__file__), "..", "out", "hd", "wip")
from mathutils import Vector
FOCUS = {  # name: (camera offset from target, target, lens)
    "chest": (Vector((0.35, -1.25, 0.08)), Vector((0, 0, h * 0.74)), 60),
    "armR": (Vector((-0.75, -0.75, 0.1)), Vector((-0.45, -0.1, h * 0.66)), 60),
    "armL": (Vector((0.75, -0.75, 0.1)), Vector((0.45, -0.1, h * 0.66)), 60),
    "legs": (Vector((0.5, -1.5, 0.1)), Vector((0, 0, h * 0.28)), 55),
    "boots": (Vector((0.45, -0.8, 0.2)), Vector((0, -0.05, 0.12)), 55),
    "back": (Vector((-0.4, 1.4, 0.15)), Vector((0, 0, h * 0.72)), 55),
    "belt": (Vector((0.3, -1.0, 0.05)), Vector((0, 0, h * 0.57)), 60),
    "head": (Vector((0.35, -0.75, 0.02)), Vector(face), 70),
}
for L in a[1].split(","):
    shots = a[2].split(",")
    std = [s_ for s_ in shots if s_ not in FOCUS]
    if std:
        preview_hd.render(cid + "_gear", (0, 0, 0), h, face, L, std, samples=24)
    for s_ in shots:
        if s_ in FOCUS:
            off, tgt, lens = FOCUS[s_]
            preview_hd.setup(L, (1000, 1000), 24)
            preview_hd.lights(L, (0, 0, 0), h)
            preview_hd.camera(tgt + off, tgt, lens)
            bpy.context.scene.render.filepath = os.path.join(preview_hd.OUT, f"{cid}_gear_{L}_{s_}.png")
            bpy.ops.render.render(write_still=True)
if "--blend" in a:
    bpy.ops.wm.save_as_mainfile(filepath=a[a.index("--blend") + 1])
