"""Stage 7: UV atlases, bakes and painted textures for every Giva material set.

  blender -b out/giva_asm.blend --python s7_textures.py [-- --size 2048 --nobake --only Armor,Garment_Top]

Atlases (2K): Garment_Top, Garment_Pants (runtime composite masks + normal), Armor (tinted painted shells),
Cloth_Gear (untinted straps/cables/pouches/glass), Boots, Gloves (tinted), Skin (4 tones + normal + mask map).
Hard surface: tangent normals baked from the high-poly sources (collection HIGH), AO baked on the assembled
low-poly; cloth: procedural construction (seams, stitching, quilting, ribs, knit, folds) evaluated from 3D and
converted to tangent normals through the per-texel MikkTSpace frame. Writes out/tex/*.png and saves
out/giva_tex.blend with preview materials.
"""
import bpy, bmesh, sys, os, json, math, importlib, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
import numpy as np
import gv, garment, raster, bake, uvtools, paint as pt, painters
for m in (gv, garment, raster, bake, uvtools, pt, painters):
    importlib.reload(m)
P = gv.P

A = gv.args()
SIZE = int(gv.opt(A, "--size", "2048"))
ONLY = gv.opt(A, "--only")
TEX = os.path.join(gv.OUT, "tex")
os.makedirs(TEX, exist_ok=True)
rig = bpy.data.objects[gv.RIG]
F = garment.Frames(rig)
OB = {o.name: o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig}
GEAR = [OB[n] for n in ("Harness", "ShoulderR", "ThighRig", "ForearmGuardL", "Visor") if n in OB]
HIGH = {o.name[:-5]: o for o in bpy.data.objects if o.name.endswith("_high")}


def mat(name):
    return bpy.data.materials.get(name) or bpy.data.materials.new(name)


def single_material(o, name):
    """The base material of a mesh becomes `name`; extra emissive slots joined in (Glow piping) are kept."""
    keep = [m.name for m in o.data.materials if m and m.name in ("Glow", "Glow2", "Screen")]
    if not keep:
        o.data.materials.clear()
        o.data.materials.append(mat(name))
        o.data.polygons.foreach_set("material_index", np.zeros(len(o.data.polygons), np.int32))
        return
    mi = np.zeros(len(o.data.polygons), np.int32)
    o.data.polygons.foreach_get("material_index", mi)
    old = [m.name if m else "" for m in o.data.materials]
    new_idx = np.array([1 + keep.index(old[i]) if old[i] in keep else 0 for i in range(len(old))], np.int32)
    o.data.materials.clear()
    o.data.materials.append(mat(name))
    for k in keep:
        o.data.materials.append(bpy.data.materials.get(k))
    o.data.polygons.foreach_set("material_index", new_idx[mi])


def want(name):
    return ONLY is None or name in ONLY.split(",")


# ----------------------------------------------------------------------------- materials + region attributes

def triangulate_ngons(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    ng = [f for f in bm.faces if len(f.verts) > 4]
    if ng:
        bmesh.ops.triangulate(bm, faces=ng, quad_method="BEAUTY", ngon_method="BEAUTY")
        bm.to_mesh(o.data)
    bm.free()


def setup_materials():
    for o in OB.values():
        triangulate_ngons(o)
    for n, mn in (("Body", "Skin"), ("Top", "Garment_Top"), ("Pants", "Garment_Pants"), ("Gloves", "Gloves"),
                  ("Eyes", "Eyes"), ("Brows", "Brows"), ("Lashes", "Lashes"), ("Teeth", "Teeth"), ("Tongue", "Tongue")):
        if n in OB:
            single_material(OB[n], mn)


def region_attr(o, part):
    """Face attribute rg: torso/armL/armR/collar/cuff (Top) or legL/legR (Pants)."""
    me = o.data
    names, W = gv.bone_weights(o)
    arm = {s: np.zeros(len(me.vertices)) for s in ("Left", "Right")}
    for j, n in enumerate(names):
        s = n[len(P):]
        for side in ("Left", "Right"):
            if s.startswith(side) and ("Arm" in s or "Hand" in s):
                arm[side] += W[:, j]
    neck = F.h["Neck"]
    nrm_neck = gv.nrm(np.array((0, -0.42, 0.91)))
    rg = np.zeros(len(me.polygons), np.float32)
    fa = F.h["RightForeArm"]
    fb = F.t["RightForeArm"]
    cut = fa + (fb - fa) * 0.52
    dcut = gv.nrm(fb - fa)
    for f in me.polygons:
        c = np.array(f.center)
        vs = list(f.vertices)
        if part == "top":
            if (c - (neck + np.array((0, 0, -0.005)))) @ nrm_neck > 0.002 and abs(c[0]) < 0.12:
                rg[f.index] = painters.REG["collar"]
            elif c[0] < -0.2 and abs((c - cut) @ dcut) < 0.012 and np.linalg.norm(c - cut) < 0.07:
                rg[f.index] = painters.REG["cuff"]
            elif arm["Left"][vs].mean() > 0.5:
                rg[f.index] = painters.REG["armL"]
            elif arm["Right"][vs].mean() > 0.5:
                rg[f.index] = painters.REG["armR"]
            else:
                rg[f.index] = painters.REG["torso"]
        else:
            rg[f.index] = painters.REG["legL"] if c[0] > 0 else painters.REG["legR"]
    a = me.attributes.get("rg") or me.attributes.new("rg", "FLOAT", "FACE")
    a.data.foreach_set("value", rg)
    return rg


# ----------------------------------------------------------------------------- UVs

def garment_seams(o, rg, part):
    me = o.data
    fc = np.array([p.center[:] for p in me.polygons])
    z, phi = F.torso(fc)
    side_l = np.zeros(len(fc))
    if part == "top":
        tA = {s: F.chain(fc, [s + "Arm", s + "ForeArm"], ref=(0, 0, 1.0))[1] for s in ("Left", "Right")}
    else:
        tA = {s: F.chain(fc, [s + "UpLeg", s + "Leg"], ref=(1.0 if s == "Left" else -1.0, 0, 0))[1] for s in ("Left", "Right")}

    def seam(a, b):
        ra, rb = rg[a], rg[b]
        if ra != rb:
            return True
        R = painters.REG
        if ra == R["torso"]:
            return (abs(phi[a]) < math.pi / 2) != (abs(phi[b]) < math.pi / 2)
        if ra in (R["armL"], R["legL"]):
            pa, pb = tA["Left"][a], tA["Left"][b]
            return abs(pa - pb) > math.pi            # wrap-around at +-pi (underside / medial)
        if ra in (R["armR"], R["legR"]):
            pa, pb = tA["Right"][a], tA["Right"][b]
            return abs(pa - pb) > math.pi
        if ra in (R["collar"], R["cuff"]):
            # open the rings at the back / underside
            ca, cb = fc[a], fc[b]
            if ra == R["collar"]:
                return ca[1] > 0 and (np.sign(ca[0]) != np.sign(cb[0]))
            pa, pb = tA["Right"][a], tA["Right"][b]
            return abs(pa - pb) > math.pi
        return False
    return seam


def do_uvs():
    rg_top = region_attr(OB["Top"], "top")
    rg_pants = region_attr(OB["Pants"], "pants")
    jobs = []
    if want("Garment_Top"):
        uvtools.unwrap_atlas([(OB["Top"], uvtools.mat_pred(OB["Top"], {"Garment_Top"}))], method="ANGLE_BASED", margin=0.006,
                             seams={"Top": garment_seams(OB["Top"], rg_top, "top")})
    if want("Garment_Pants"):
        uvtools.unwrap_atlas([(OB["Pants"], uvtools.mat_pred(OB["Pants"], {"Garment_Pants"}))], method="ANGLE_BASED", margin=0.006,
                             seams={"Pants": garment_seams(OB["Pants"], rg_pants, "pants")})
    if want("Armor"):
        uvtools.unwrap_atlas([(o, uvtools.mat_pred(o, {"Armor"})) for o in GEAR], "SMART", 0.006, 55)
    if want("Cloth_Gear"):
        uvtools.unwrap_atlas([(o, uvtools.mat_pred(o, {"Cloth_Gear"})) for o in GEAR if "Cloth_Gear" in o.data.materials], "SMART", 0.006, 60)
    if want("Boots"):
        uvtools.unwrap_atlas([(OB["Boots"], uvtools.mat_pred(OB["Boots"], {"Boots"}))], "SMART", 0.005, 55)
    if want("Gloves"):
        uvtools.unwrap_atlas([(OB["Gloves"], lambda f: True)], "SMART", 0.006, 60)
    gv.log("uvs done")


# ----------------------------------------------------------------------------- outputs

def save_rgb(arr, name, srgb=False, mask=None, dil=12):
    a = arr.astype(np.float32)
    if mask is not None:
        a = raster.dilate(a, mask, dil)
    if srgb:
        a = gv.lin_to_srgb(np.clip(a, 0, 1)).astype(np.float32)
    path = os.path.join(TEX, name)
    gv.write_image(a, path)
    return name


def atlas_maps(groups, vattrs=(), fattrs=("cls", "rg")):
    maps = raster.Maps(SIZE)
    for i, (o, pred) in enumerate(groups):
        fm = np.array([bool(pred(f)) for f in o.data.polygons])
        raster.rasterize(maps, o, i, fm, vattrs, fattrs)
    return maps


def ao_for(groups, target):
    if "--nobake" in A:
        return np.ones((SIZE, SIZE), np.float32)
    objs = [g[0] for g in groups]
    for h in HIGH.values():
        h.hide_render = True
    arr = bake.bake_ao(objs, {target}, SIZE, samples=int(gv.opt(A, "--aos", "64")))
    return arr


def hi_normal(groups, target):
    if "--nobake" in A:
        return None
    pairs = []
    for o, _ in groups:
        hs_ = [h for k, h in HIGH.items() if k == o.name or (o.name == "Boots" and k.startswith("Boots"))]
        if hs_:
            pairs.append((o, hs_))
    if not pairs:
        return None
    return bake.bake_normal(pairs, {target}, SIZE)


def combine_normals(base, detail_h_rgb):
    """Reoriented normal mapping (RNM) of a baked base normal map and a detail normal map (both RGB 0..1)."""
    t = base * np.array((2, 2, 2)) + np.array((-1, -1, 0))
    u = detail_h_rgb * np.array((-2, -2, 2)) + np.array((1, 1, -1))
    r = t * (t * u).sum(-1, keepdims=True) / np.maximum(t[..., 2:3], 1e-4) - u
    return gv.nrm(r) * 0.5 + 0.5


# ----------------------------------------------------------------------------- atlases

def tex_garment(name, o, part):
    groups = [(o, uvtools.mat_pred(o, {name}))]
    maps = atlas_maps(groups, fattrs=("cls", "rg", "panel"))
    ao = ao_for(groups, name)
    mask, H = painters.suit_design(maps, F, part, ao)
    nrm = raster.normals_from_height(maps, H, 1.0)
    pre = "Lyra_Top" if part == "top" else "Lyra_Pants"
    save_rgb(mask, pre + "_Mask.png", mask=maps.mask)
    save_rgb(nrm, pre + "_Normal.png", mask=maps.mask)
    gv.log(name, "painted")
    return {"mask": pre + "_Mask.png", "normal": pre + "_Normal.png"}


ARMOR_SCHEME = {
    0.0: dict(base=(0.6, 0.6, 0.63), metal=0.15, smooth=0.6, wear=0.6, wear_col=(0.95, 0.95, 0.97), wear_metal=0.9,
              wear_smooth=0.25, grime=0.55, paint=1.0, var=0.08),
    # dark gunmetal shells (pauldron, core housing, forearm guard): anodised, bright worn edges
    7.0: dict(base=(0.16, 0.16, 0.18), metal=0.6, smooth=0.66, wear=0.7, wear_col=(0.85, 0.85, 0.88), wear_metal=1.0,
              wear_smooth=0.3, grime=0.5, paint=1.0, var=0.06),
}
GEAR_SCHEME = {
    1.0: dict(base=(0.035, 0.036, 0.04), metal=0.0, smooth=0.28, wear=0.2, wear_col=(0.08, 0.08, 0.085), grime=0.4, var=0.1),
    2.0: dict(base=(0.022, 0.022, 0.025), metal=0.0, smooth=0.5, wear=0.1, grime=0.3),
    5.0: dict(base=(0.045, 0.043, 0.042), metal=0.0, smooth=0.22, wear=0.25, wear_col=(0.09, 0.09, 0.09), grime=0.5, var=0.12),
    6.0: dict(base=(0.012, 0.014, 0.02), metal=0.0, smooth=0.93, wear=0.0, grime=0.0),
    9.0: dict(base=(0.32, 0.018, 0.022), metal=0.0, smooth=0.55, wear=0.1, grime=0.2),
    0.0: dict(base=(0.05, 0.05, 0.055), metal=0.3, smooth=0.5, wear=0.5, wear_col=(0.4, 0.4, 0.42), wear_metal=1.0, grime=0.4),
}
BOOT_SCHEME = {
    10.0: dict(base=(0.045, 0.046, 0.05), metal=0.0, smooth=0.42, wear=0.35, wear_col=(0.11, 0.11, 0.12), grime=0.6, var=0.1),
    11.0: dict(base=(0.03, 0.03, 0.034), metal=0.0, smooth=0.25, wear=0.1, grime=0.5),
    12.0: dict(base=(0.022, 0.022, 0.024), metal=0.0, smooth=0.22, wear=0.3, wear_col=(0.06, 0.06, 0.06), grime=0.6),
    13.0: dict(base=(0.075, 0.06, 0.11), metal=0.2, smooth=0.55, wear=0.9, wear_col=(0.5, 0.5, 0.54), wear_metal=0.9, grime=0.5),
    14.0: dict(base=(0.035, 0.036, 0.04), metal=0.0, smooth=0.3, wear=0.2, grime=0.4),
    15.0: dict(base=(0.5, 0.52, 0.55), metal=1.0, smooth=0.6, wear=0.5, wear_col=(0.9, 0.9, 0.92), wear_metal=1.0, grime=0.5),
}


def tex_hard(name, groups, scheme, prefix, micro=None, decals=None):
    maps = atlas_maps(groups, vattrs=("bz", "top", "plate"))
    ao = ao_for(groups, name)
    nrm = hi_normal(groups, name)
    if nrm is None:
        nrm = np.zeros((SIZE, SIZE, 3), np.float32) + np.array((0.5, 0.5, 1.0), np.float32)
    cls = maps.attr.get("cls", np.zeros((SIZE, SIZE), np.float32))
    if micro is not None:
        H = micro(maps, cls)
        dn = raster.normals_from_height(maps, H, 1.0)
        nrm = combine_normals(nrm, dn)
    base, mm = painters.paint_hard(maps, ao, nrm, cls, scheme)
    if decals:
        decals(maps, base, mm)
    save_rgb(base, prefix + "_BaseColor.png", srgb=True, mask=maps.mask)
    save_rgb(np.where(maps.mask[..., None], nrm, np.array((0.5, 0.5, 1.0))), prefix + "_Normal.png", mask=maps.mask)
    save_rgb(mm, prefix + "_MaskMap.png", mask=maps.mask)
    gv.log(name, "painted", prefix)
    return [prefix + "_BaseColor.png", prefix + "_Normal.png", prefix + "_MaskMap.png"]


def gear_micro(maps, cls):
    """Webbing ribs, cable bands, cordura weave (directions from the texel tangent frame)."""
    m = maps.mask
    P = maps.P.astype(np.float64)
    H = np.zeros(m.shape, np.float32)
    # strap webbing: ribs along the strap; use the tangent (uv direction) as 'along' proxy
    u = (P * maps.T).sum(-1)
    v = (P * maps.B).sum(-1)
    s1 = m & (np.abs(cls - 1) < 0.5)
    H[s1] = pt.webbing(u[s1], v[s1])
    s5 = m & (np.abs(cls - 5) < 0.5)
    H[s5] = pt.knit(u[s5], v[s5], 0.0009, 0.00015)
    s2 = m & (np.abs(cls - 2) < 0.5)
    H[s2] = pt.periodic_ribs(v[s2], 0.006, 0.00045, 3)
    return H


def boot_micro(maps, cls):
    m = maps.mask
    P = maps.P.astype(np.float64)
    H = np.zeros(m.shape, np.float32)
    # sole tread on the bottom (cls 12, z < 0.004): lugs
    s = m & (np.abs(cls - 12) < 0.5)
    x, y = P[..., 0], P[..., 1]
    lug = (np.sin(x / 0.006 * math.pi) * np.sin((y + x * 0.4) / 0.008 * math.pi) > 0.2) & (P[..., 2] < 0.002)
    H[s] = np.where(lug[s], -0.0016, 0.0)
    side = s & (P[..., 2] > 0.002)
    H[side] += pt.periodic_ribs(P[side][:, 2], 0.004, 0.0004, 2)
    # upper: ballistic nylon weave on the shaft, smooth leather toe/heel
    u = (P * maps.T).sum(-1)
    v = (P * maps.B).sum(-1)
    up = m & (np.abs(cls - 10) < 0.5)
    shaft = up & (P[..., 2] > 0.09)
    H[shaft] = pt.knit(u[shaft], v[shaft], 0.0014, 0.00025)
    grain = up & ~shaft
    H[grain] = (pt.fbm(P[grain], 900, 2, seed=2) - 0.5) * 0.00012
    s14 = m & (np.abs(cls - 14) < 0.5)
    H[s14] = pt.webbing(u[s14], v[s14])
    s11 = m & (np.abs(cls - 11) < 0.5)
    H[s11] = pt.periodic_ribs(P[s11][:, 2] * 0 + u[s11], 0.005, 0.0006, 2)
    return H


def boot_design(maps, base, mm):
    """Boot construction on the upper (cls 10): rubber rand, smooth toe cap + heel counter, nylon shaft panels,
    panel seams with stitching, a violet accent piping at the collar."""
    m = maps.mask
    P = maps.P.astype(np.float64)
    cls = maps.attr.get("cls", np.zeros(m.shape, np.float32))
    up = m & (np.abs(cls - 10) < 0.5)
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    sx = np.sign(x)
    # per-foot local coordinates (toe at -Y)
    yc = np.where(sx > 0, y, y)
    rand = up & (z < 0.034)
    toe = up & (yc < -0.085) & (z < 0.075) & ~rand
    heel = up & (yc > 0.0) & (z < 0.09) & ~rand
    shaft = up & (z > 0.13)
    def setc(sel, col, smooth, metal=0.0):
        base[sel] = np.array(col, np.float32) * (0.85 + 0.3 * mm[sel, 1:2])
        mm[sel, 3] = smooth
        mm[sel, 0] = metal
    setc(rand, (0.016, 0.016, 0.018), 0.38)
    setc(toe, (0.03, 0.03, 0.034), 0.55)
    setc(heel, (0.03, 0.03, 0.034), 0.5)
    setc(shaft, (0.055, 0.056, 0.064), 0.3)
    # seams: toe cap edge, heel counter edge, shaft/foot transition, rand top
    def seam_band(d, w=0.0009):
        return np.exp(-(d / w) ** 2)
    dl = np.full(m.shape, 1e3)
    dl = np.minimum(dl, np.abs(z - 0.034))
    dl = np.minimum(dl, np.where(z < 0.075, np.abs(yc + 0.085), 1e3))
    dl = np.minimum(dl, np.where(z < 0.09, np.abs(yc - 0.0), 1e3))
    dl = np.minimum(dl, np.abs(z - 0.13))
    band = up & (dl < 0.004)
    base[band] *= (1 - 0.5 * seam_band(dl[band]))[:, None]
    stitch = up & (np.abs(dl - 0.0025) < 0.0005) & (((x + y + z) / 0.003) % 1.0 < 0.6)
    base[stitch] = base[stitch] * 0.6 + np.array((0.12, 0.12, 0.13), np.float32) * 0.4
    # violet piping on the collar edge
    col = m & (np.abs(cls - 11) < 0.5) & (z > 0.334)
    base[col] = np.array((0.18, 0.1, 0.32), np.float32)
    mm[col, 3] = 0.5


def armor_decals(maps, base, mm):
    """Invented serials, hazard chevrons and accent stripes on the shells."""
    m = maps.mask
    P = maps.P.astype(np.float64)
    up = np.array((0, 0, 1.0))
    items = [
        # (centre, normal, kind, size, text, colour)
        (F.h["RightArm"] + np.array((-0.055, -0.035, 0.03)), (-0.6, -0.6, 0.5), "text", (0.04, 0.007), "A7-ΞΛ", (0.06, 0.06, 0.07)),
        (F.h["RightArm"] + np.array((-0.06, 0.0, 0.0)), (-0.9, 0, 0.4), "chev", (0.06, 0.01), "", (0.9, 0.62, 0.12)),
    ]
    for c, n, kind, size, text, col in items:
        cov = painters.decal(P, m, c, n, up, kind, size, text)
        sel = cov > 0.01
        base[sel] = base[sel] * (1 - cov[sel, None]) + np.array(col, np.float32) * cov[sel, None]
        mm[sel, 3] = mm[sel, 3] * (1 - cov[sel]) + 0.45 * cov[sel]


def main():
    setup_materials()
    do_uvs()
    out = {}
    if want("Garment_Top"):
        out["Garment_Top"] = tex_garment("Garment_Top", OB["Top"], "top")
    if want("Garment_Pants"):
        out["Garment_Pants"] = tex_garment("Garment_Pants", OB["Pants"], "pants")
    if want("Armor"):
        out["Armor"] = tex_hard("Armor", [(o, uvtools.mat_pred(o, {"Armor"})) for o in GEAR], ARMOR_SCHEME, "Lyra_Armor",
                                decals=armor_decals)
    if want("Cloth_Gear"):
        out["Cloth_Gear"] = tex_hard("Cloth_Gear", [(o, uvtools.mat_pred(o, {"Cloth_Gear"})) for o in GEAR], GEAR_SCHEME,
                                     "Lyra_Gear", micro=gear_micro)
    if want("Boots"):
        out["Boots"] = tex_hard("Boots", [(OB["Boots"], uvtools.mat_pred(OB["Boots"], {"Boots"}))], BOOT_SCHEME, "Lyra_Boots",
                                micro=boot_micro, decals=boot_design)
    path = os.path.join(TEX, "atlases.json")
    if ONLY and os.path.exists(path):
        merged = json.load(open(path))
        merged.update(out)
        out = merged
    json.dump(out, open(path, "w"), indent=1)
    gv.save(os.path.join(gv.OUT, "giva_tex.blend"))


main()
