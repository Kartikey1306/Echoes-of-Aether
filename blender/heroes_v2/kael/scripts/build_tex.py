"""Stage 4 - Kael v2 outfit textures: atlas packing, high -> low bakes, procedural painting, Unity texture files and
Blender preview materials that mirror the Unity shading (garment composite with the default palette, tints).

  blender -b blends/kael_s3_outfit.blend --python build_tex.py -- [--mats Garment_Top,...] [--size 2048] [--preview] [--save]
Writes into tex/ (staging; build_export.py copies to Unity).
"""
import bpy, sys, os, json, math, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
from mathutils import Vector
import paint_k2 as PK, texstage as TS, texbake as TB, fabric
importlib.reload(PK)
import paint_k3 as PK3
importlib.reload(PK3)

a = K.args()
rig = bpy.data.objects["Kael"]
L = {b.name.split(":")[1]: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones if ":" in b.name}
OUT = K.TEX
PAL = {"outfit": "#5c5848", "accent": "#1f2126", "armor": "#c9cdd3", "glow": "#00e5ff", "glow2": "#ff2bd6"}
objs = {o.name: o for o in bpy.data.objects if o.type == "MESH" and o.parent is None or (o.type == "MESH" and o.parent is rig)}
objs = {n: o for n, o in objs.items() if not n.endswith(("_HI", "_HIB", "_HPG")) and n not in ("BodyMH",)}
mats = (K.opt(a, "--mats") or "Garment_Top,Garment_Pants,Cloth_Jacket,Armor,Boots,Gloves,Cloth_Gear").split(",")
hide = [o for o in bpy.data.objects if o.type == "MESH" and o.name in ("Eyes", "Brows", "Lashes", "Teeth", "Tongue")]
produced = {}
PK3.O3.JK_NECK = float(L["Neck"][2]) - 0.052          # same neckline as outfit_k3.jacket()
SIZES = {"Garment_Top": 2048, "Garment_Pants": 2048, "Cloth_Jacket": 2048, "Armor": 2048, "Boots": 2048, "Gloves": 1024, "Cloth_Gear": 2048}
ATTRS = ("bx", "by", "bz", "wear", "cavity", "lx", "ly", "plate", "pouch", "strap", "sole", "mz", "kplate", "cap", "vest", "stud", "cuffplate")
if K.opt(a, "--size"):
    for k in SIZES:
        SIZES[k] = min(SIZES[k], int(K.opt(a, "--size")))


def users(mat):
    return [o for o in objs.values() if TB._faces_with(o, mat) is not None]


# brass knuckle studs (glove studs): flat PBR set, not tinted by the gloves colour
if "Gloves" in mats:
    TB.write_png(np.full((32, 32, 3), (0.86, 0.66, 0.34), np.float32), os.path.join(OUT, "Kael_Brass_BaseColor.png"), "RGB")
    TB.write_png(np.full((32, 32, 3), (0.5, 0.5, 1.0), np.float32), os.path.join(OUT, "Kael_Brass_Normal.png"), "RGB")
    TB.write_png(np.full((32, 32, 4), (1.0, 1.0, 0.0, 0.74), np.float32), os.path.join(OUT, "Kael_Brass_MaskMap.png"), "RGBA")
    produced["Cloth_Brass"] = ["Kael_Brass_BaseColor.png", "Kael_Brass_Normal.png", "Kael_Brass_MaskMap.png"]
    TS.preview_mat("Cloth_Brass", os.path.join(OUT, "Kael_Brass_BaseColor.png"), None, metal=1.0, rough=0.26)
# holographic sleeve pattern (material "Holo", EOA/HoloSleeve: additive; RGB pattern, A coverage): faint fill, ring
# lines, circuit traces, hex cells and node dots; u wraps around the arm, v runs along the shell (ends fade out)
if "Holo" not in mats or True:
    S_ = 1024
    yy, xx = np.mgrid[0:S_, 0:S_]
    u = (xx + 0.5) / S_; v = (yy + 0.5) / S_
    rng_ = np.random.default_rng(7)
    A = np.full((S_, S_), 0.16)
    ring = np.exp(-((((v * 9.0) % 1.0) - 0.5) / 0.03) ** 2)                       # ring lines along the arm
    A = np.maximum(A, 0.75 * ring)
    for k in range(18):                                                           # circuit traces with jogs
        u0 = rng_.random(); jv = rng_.uniform(0.2, 0.8); ju = rng_.uniform(-0.04, 0.04)
        va, vb = sorted(rng_.uniform(0.05, 0.95, 2))
        uc = np.where(v < jv, u0, (u0 + ju) % 1.0)
        du = np.abs(((u - uc + 0.5) % 1.0) - 0.5)
        tr = np.exp(-(du / 0.0035) ** 2) * (v > va) * (v < vb)
        jog = np.exp(-((v - jv) / 0.003) ** 2) * (np.abs(((u - u0 + 0.5) % 1.0) - 0.5) < abs(ju) + 0.003)
        A = np.maximum(A, 0.9 * np.maximum(tr, jog * (v > va) * (v < vb)))
        for vv in (va, vb):
            A = np.maximum(A, 0.95 * (np.hypot(np.abs(((u - (uc if vv > jv else u0) + 0.5) % 1.0) - 0.5) * 3, v - vv) < 0.008))
    hx = (u * 24.0) % 1.0; hy = (v * 14.0 + 0.5 * (np.floor(u * 24.0) % 2)) % 1.0     # hex-ish cell grid
    cell = np.minimum(np.minimum(hx, 1 - hx), np.minimum(hy, 1 - hy))
    A = np.maximum(A, 0.32 * np.exp(-(cell / 0.03) ** 2))
    A = A * (0.85 + 0.15 * np.sin(v * 220.0) ** 2)                                # fine scan banding
    A = A * K.ss(0.0, 0.08, v) * K.ss(1.0, 0.9, v)                                    # fade at the shell ends
    rgb = np.ones((S_, S_, 3)) * (0.85 + 0.15 * A[..., None])
    TB.write_png(np.concatenate([rgb, A[..., None]], -1).astype(np.float32), os.path.join(OUT, "Kael_Holo.png"), "RGBA")
    produced["Holo"] = ["Kael_Holo.png"]
for mat in mats:
    size = SIZES[mat]
    lows = PK.atlas(users(mat), mat, size)
    if not lows:
        continue
    K.log("ATLAS", mat, [o.name for o in lows])
    if mat in ("Garment_Top", "Garment_Pants"):
        disp = {"Top": PK3.suit_disp(L), "Pants": PK3.pants_disp(L)}
        hp = lambda lo: PK.garment_hp(lo, disp.get(lo.name, PK.soft_disp(hash(lo.name) % 7)), levels=3)
        nb, ao = PK.bake(lows, mat, size, hp, cage=0.008, dist=0.018, ao_dist=0.06, ao_samples=64, hide=hide)
        T, t = PK.raster(lows, mat, size, attrs=ATTRS)
        Ly = PK3.paint_suit(T, t, lows, L, nb) if mat == "Garment_Top" else PK3.paint_pants(T, t, lows, L, nb)
        part = "Top" if mat == "Garment_Top" else "Pants"
        M, Nm = PK.write_garment(T, t, Ly, ao, nb, f"Kael_{part}", OUT)
        produced[mat] = [f"Kael_{part}_Mask.png", f"Kael_{part}_Normal.png"]
        prim = TS.hex2lin(PAL["outfit"]) * (0.88 if part == "Pants" else 1.0)
        rgb, smooth = TS.composite_garment(M, prim, TS.hex2lin(PAL["accent"]))
        TB.write_png(rgb, os.path.join(OUT, f"prev_{part}_BaseColor.png"), "RGB")
        TB.write_png(np.clip(1 - smooth, 0, 1), os.path.join(OUT, f"prev_{part}_Rough.png"), "RGB")
        TS.preview_mat(mat, os.path.join(OUT, f"prev_{part}_BaseColor.png"), os.path.join(OUT, f"Kael_{part}_Normal.png"),
                       rough=os.path.join(OUT, f"prev_{part}_Rough.png"))
    elif mat == "Cloth_Jacket":
        disp = {"Jacket": PK3.jacket_disp(L), "Collar": PK3.collar_disp(L)}
        hp = lambda lo: PK.garment_hp(lo, disp.get(lo.name, PK.soft_disp(3)), levels=3)
        nb, ao = PK.bake(lows, mat, size, hp, cage=0.008, dist=0.02, ao_dist=0.05, ao_samples=96, hide=hide)
        T, t = PK.raster(lows, mat, size, attrs=ATTRS)
        rgb, h, metal, smooth, paint = PK3.paint_jacket(T, t, lows, L, nb, ao)
        files = PK.write_hard(T, t, rgb, h, metal, smooth, ao, nb, "Kael_Jacket", OUT, paint)
        produced[mat] = files
        TS.preview_mat(mat, os.path.join(OUT, files[0]), os.path.join(OUT, files[1]), maskmap=os.path.join(OUT, files[2]), tint=None)
    else:
        nb, ao = PK.bake(lows, mat, size, PK.hard_hp, cage=0.004, dist=0.012, ao_dist=0.04, ao_samples=64, hide=hide)
        T, t = PK.raster(lows, mat, size, attrs=ATTRS)
        if mat == "Armor":
            res = PK3.paint_armor(T, t, lows, nb, ao)
            tint = tuple(TS.hex2lin(PAL["armor"]))
        elif mat == "Boots":
            res = PK3.paint_boots(T, t, lows, nb, ao)
            tint = None
        elif mat == "Gloves":
            res = PK3.paint_gloves(T, t, lows, nb, ao, L)
            tint = (0.36, 0.36, 0.36)
        else:
            res = PK3.paint_gear(T, t, lows, nb, ao)
            tint = None
        rgb, h, metal, smooth, paint = res
        label = "Gear" if mat == "Cloth_Gear" else mat
        files = PK.write_hard(T, t, rgb, h, metal, smooth, ao, nb, f"Kael_{label}", OUT, paint)
        produced[mat] = files
        TS.preview_mat(mat, os.path.join(OUT, files[0]), os.path.join(OUT, files[1]), maskmap=os.path.join(OUT, files[2]), tint=tint)
    K.log("TEX", mat, produced[mat])
prev = os.path.join(K.LOGS, "tex_produced.json")
allp = json.load(open(prev)) if os.path.exists(prev) else {}
allp.update(produced)
json.dump(allp, open(prev, "w"), indent=1)
TS.flat_mats({"Metal": ("#a7adb5", 0.3, 1.0, None), "Glow": (PAL["glow"], 0.3, 0.0, (PAL["glow"], 8.0)),
              "Glow2": (PAL["glow2"], 0.3, 0.0, (PAL["glow2"], 8.0)), "Screen": ("#06141a", 0.15, 0.0, (PAL["glow"], 2.5))})
if K.opt(a, "--save"):
    for o in [o for o in bpy.data.objects if o.name.endswith(("_HPG", "_HIB"))]:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(K.BLENDS, "kael_s4_tex.blend"))
if K.opt(a, "--preview"):
    body = bpy.data.objects["Body"]
    sk = bpy.data.materials.get("Skin")
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name in ("BodyMH",) or o.name.endswith(("_HI",)):
            o.hide_render = True
    out = []
    for tag, yaw, dist, z, aim, lens in (("front", 0, 4.4, 1.0, 0.95, 50), ("q34", 35, 4.4, 1.05, 0.95, 50), ("back", 180, 4.4, 1.0, 0.95, 50),
                                          ("chest", 25, 1.5, 1.45, 1.35, 50), ("arm", 300, 1.3, 1.3, 1.25, 50), ("legs", 20, 1.9, 0.55, 0.5, 50)):
        K.clear_preview()
        K.cycles(samples=48, res=(700, 900))
        K.world((0.03, 0.033, 0.04), 1.0)
        K.floor((0.06, 0.065, 0.07), 0.6)
        K.rig_lights("menu", Vector((0, 0, aim)), 1.6 if dist > 3 else 1.0)
        r = math.radians(yaw)
        K.camera(Vector((math.sin(r) * dist, -math.cos(r) * dist, z)), Vector((0, 0, aim)), lens)
        out.append(K.render_to(os.path.join(K.PREVIEWS, "outfit", f"tex_{tag}.png")))
    K.contact_sheet(out, os.path.join(K.PREVIEWS, "outfit", "tex_sheet.png"), cols=3, width=560)
