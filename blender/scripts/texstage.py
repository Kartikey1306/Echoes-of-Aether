"""Texture stage: pack atlases, bake AO, paint maps, write PNGs and set up preview materials that mirror Unity.

Garment atlases (Garment_Top / Garment_Pants) write the Unity contract maps <Name>_<Part>_Mask.png (R accent,
G trim, B glow, A seam/occlusion) and <Name>_<Part>_Normal.png. Hard-surface atlases (Armor, Boots, Gloves) write
<Name>_<Mat>_BaseColor.png, _Normal.png and _MaskMap.png (R metallic, G occlusion, B paint/detail mask,
A smoothness - HDRP-style packing, usable as URP _MetallicGlossMap (R, A) and _OcclusionMap (G)).
"""
import os, time
import numpy as np
import bpy
import texbake as TB


def subset(T):
    idx = np.where(T.cov)[0]
    t = {"idx": idx, "P": T.P[idx].astype(np.float64), "N": T.N[idx].astype(np.float64), "mpt": T.mpt[idx], "obj": T.obj[idx],
         "A": {k: v[idx] for k, v in T.A.items()}}
    t["B"] = np.stack([t["A"]["bx"], t["A"]["by"], t["A"]["bz"]], 1).astype(np.float64)
    # Faces without body coordinates (parts) report zeros: fall back to their own position.
    noB = np.abs(t["B"]).sum(1) < 1e-6
    t["B"][noB] = t["P"][noB]
    return t


def full(T, t, values, fill=0.0):
    shape = (T.size * T.size,) + np.asarray(values).shape[1:]
    out = np.full(shape, fill, np.float32)
    out[t["idx"]] = values
    return out.reshape((T.size, T.size) + np.asarray(values).shape[1:])


def to_normal(T, t, h, strength=1.0):
    H = TB.dilate(full(T, t, h), T.cov.reshape(T.size, T.size), 6)
    mpt = T.mpt.reshape(T.size, T.size)
    n = TB.height_to_normal(H, mpt, strength)
    return n


def finish(T, img, iters=10):
    cov = T.cov.reshape(T.size, T.size)
    return TB.dilate(img, cov, iters)


def hex2lin(h):
    return np.array([(int(h[i:i + 2], 16) / 255) for i in (1, 3, 5)])


def composite_garment(mask, primary, secondary, trim=(0.54, 0.56, 0.59)):
    """Python mirror of CharacterModel.CompositeGarment (sRGB colours) -> (rgb, smoothness)."""
    p = np.asarray(primary); s = np.asarray(secondary); tr = np.asarray(trim)
    R, G, A = mask[..., 0:1], mask[..., 1:2], mask[..., 3:4]
    c = p + (s - p) * R
    c = c + (tr - c) * G
    c = c * (1 - A * 140 / 255)
    smooth = np.clip(70 / 255 + G[..., 0] * 110 / 255 - A[..., 0] * 40 / 255, 0, 1) * 0.9
    return c, smooth


def img_node(nt, path, non_color=True):
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(path, check_existing=True)
    n.image.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    return n


def preview_mat(name, base_path, normal_path=None, rough=None, metal=None, maskmap=None, tint=None, normal_strength=1.0, emission=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs[0], out.inputs[0])
    bc = img_node(nt, base_path, non_color=False)
    if tint is not None:
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.inputs["Factor"].default_value = 1.0
        nt.links.new(bc.outputs["Color"], mix.inputs[6])
        mix.inputs[7].default_value = (*[c ** 2.2 for c in tint], 1)
        nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    else:
        nt.links.new(bc.outputs["Color"], b.inputs["Base Color"])
    if normal_path:
        nn = img_node(nt, normal_path)
        nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = normal_strength
        nt.links.new(nn.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs[0], b.inputs["Normal"])
    if maskmap:
        mm = img_node(nt, maskmap)
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(mm.outputs["Color"], sep.inputs[0])
        nt.links.new(sep.outputs[0], b.inputs["Metallic"])
        inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
        nt.links.new(mm.outputs["Alpha"], inv.inputs[1])
        nt.links.new(inv.outputs[0], b.inputs["Roughness"])
    else:
        if rough is not None:
            if isinstance(rough, str):
                rn = img_node(nt, rough)
                nt.links.new(rn.outputs["Color"], b.inputs["Roughness"])
            else:
                b.inputs["Roughness"].default_value = rough
        if metal is not None:
            b.inputs["Metallic"].default_value = metal
    if emission:
        b.inputs["Emission Color"].default_value = (*emission[0], 1)
        b.inputs["Emission Strength"].default_value = emission[1]
    return m


def garment_atlas(objs, mat, part, cname, painter, L, size, tex_dir, wip_dir, palette, ao_hide=(), samples=16):
    t0 = time.time()
    objs = [o for o in objs if TB._faces_with(o, mat) is not None]
    if not objs:
        return None
    TB.pack(objs, mat, margin=0.003)
    ao = TB.bake_ao(objs, mat, size, samples=samples, distance=0.08, hide=ao_hide)
    T = TB.raster(objs, mat, size)
    t = subset(T)
    ao_t = ao.reshape(-1)[t["idx"]]
    Ly = painter(t, L, T, T.names)
    A = np.maximum(Ly.A, np.clip((1 - ao_t) * 0.85, 0, 1))
    mask = np.stack([Ly.R, Ly.G, Ly.B, np.clip(A, 0, 1)], 1)
    M = finish(T, full(T, t, mask))
    Nm = to_normal(T, t, Ly.h)
    base = f"{cname}_{part}"
    TB.write_png(M, os.path.join(tex_dir, base + "_Mask.png"), "RGBA")
    TB.write_png(Nm, os.path.join(tex_dir, base + "_Normal.png"), "RGB")
    # Preview (Blender only): composite with the recommended palette.
    prim = hex2lin(palette["outfit"]) * (0.88 if part == "Pants" else 1.0)
    rgb, smooth = composite_garment(M, prim, hex2lin(palette["accent"]))
    rough = 1 - np.clip(smooth + finish(T, full(T, t, Ly.rough)) * -0.3, 0, 1)
    os.makedirs(wip_dir, exist_ok=True)
    pb = os.path.join(wip_dir, base + "_preview_BaseColor.png")
    pr = os.path.join(wip_dir, base + "_preview_Rough.png")
    TB.write_png(rgb, pb, "RGB")
    TB.write_png(rough, pr, "RGB")
    preview_mat(mat, pb, os.path.join(tex_dir, base + "_Normal.png"), rough=pr)
    print("ATLAS", mat, len(objs), "objs", round(time.time() - t0, 1), "s")
    return [base + "_Mask.png", base + "_Normal.png"]


def hard_atlas(objs, mat, cname, fn, size, tex_dir, tint, ao_hide=(), samples=16, normal_strength=1.0, label=None):
    t0 = time.time()
    objs = [o for o in objs if TB._faces_with(o, mat) is not None]
    if not objs:
        return None
    TB.pack(objs, mat, margin=0.004)
    ao = TB.bake_ao(objs, mat, size, samples=samples, distance=0.06, hide=ao_hide)
    T = TB.raster(objs, mat, size)
    t = subset(T)
    ao_t = ao.reshape(-1)[t["idx"]]
    res = fn(t, ao_t)
    rgb, h, metal, smooth = res[:4]
    paint = res[4] if len(res) > 4 else np.ones(len(h))
    base = f"{cname}_{label or mat}"
    C = finish(T, full(T, t, rgb))
    Nm = to_normal(T, t, h)
    MM = finish(T, full(T, t, np.stack([metal, np.clip(ao_t * 0.8 + 0.2, 0, 1), paint, smooth], 1)))
    TB.write_png(C, os.path.join(tex_dir, base + "_BaseColor.png"), "RGB")
    TB.write_png(Nm, os.path.join(tex_dir, base + "_Normal.png"), "RGB")
    TB.write_png(MM, os.path.join(tex_dir, base + "_MaskMap.png"), "RGBA")
    preview_mat(mat, os.path.join(tex_dir, base + "_BaseColor.png"), os.path.join(tex_dir, base + "_Normal.png"),
                maskmap=os.path.join(tex_dir, base + "_MaskMap.png"), tint=tint, normal_strength=normal_strength)
    print("ATLAS", mat, len(objs), "objs", round(time.time() - t0, 1), "s")
    return [base + "_BaseColor.png", base + "_Normal.png", base + "_MaskMap.png"]


def flat_mats(spec):
    """Preview materials for untextured slots: {name: (hex, rough, metal, emission(hex, strength) or None)}."""
    for name, (hx, rough, metal, emit) in spec.items():
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(b.outputs[0], out.inputs[0])
        c = hex2lin(hx) ** 2.2
        b.inputs["Base Color"].default_value = (*c, 1)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        if emit:
            e = hex2lin(emit[0]) ** 2.2
            b.inputs["Emission Color"].default_value = (*e, 1)
            b.inputs["Emission Strength"].default_value = emit[1]



def hard_atlas_baked(objs, mat, cname, fn, size, tex_dir, tint, ao_hide=(), ao_samples=24, normal_strength=1.0, label=None,
                     attrs=("bx", "by", "bz", "wear", "cavity", "lx", "ly", "plate", "pouch", "strap", "sole", "collar", "mz", "kplate", "cap")):
    """Hard-surface atlas with a real high -> low bake (normal + AO from creased subdivision + floaters), curvature
    from the baked normals, procedural material zones / wear / decals from fn, painted detail blended on top."""
    t0 = time.time()
    objs = [o for o in objs if TB._faces_with(o, mat) is not None]
    if not objs:
        return None
    TB.pack(objs, mat, margin=0.004)
    nb, ao, temps = TB.bake_maps(objs, mat, size, ao_samples=ao_samples, hide=ao_hide)
    T = TB.raster(objs, mat, size, attrs=attrs)
    t = subset(T)
    mpt = T.mpt.reshape(T.size, T.size)
    curv = TB.curvature_from_normal(nb, mpt)
    t["curv"] = curv.reshape(-1)[t["idx"]]
    t["nbake"] = nb.reshape(-1, 3)[t["idx"]]
    ao_t = np.clip(ao.reshape(-1)[t["idx"]], 0, 1)
    res = fn(t, ao_t)
    rgb, h, metal, smooth = res[:4]
    paint = res[4] if len(res) > 4 else np.ones(len(h))
    base = f"{cname}_{label or mat}"
    C = finish(T, full(T, t, rgb))
    Nd = to_normal(T, t, h)
    nb_f = finish(T, full(T, t, t["nbake"]))
    covered = T.cov.reshape(T.size, T.size)
    nb_f = np.where(covered[..., None], nb_f, np.array((0.5, 0.5, 1.0)))
    Nm = TB.whiteout(nb_f, Nd)
    MM = finish(T, full(T, t, np.stack([metal, np.clip(ao_t * 0.85 + 0.15, 0, 1), paint, smooth], 1)))
    TB.write_png(C, os.path.join(tex_dir, base + "_BaseColor.png"), "RGB")
    TB.write_png(Nm, os.path.join(tex_dir, base + "_Normal.png"), "RGB")
    TB.write_png(MM, os.path.join(tex_dir, base + "_MaskMap.png"), "RGBA")
    preview_mat(mat, os.path.join(tex_dir, base + "_BaseColor.png"), os.path.join(tex_dir, base + "_Normal.png"),
                maskmap=os.path.join(tex_dir, base + "_MaskMap.png"), tint=tint, normal_strength=normal_strength)
    for o in temps:
        bpy.data.objects.remove(o, do_unlink=True)
    print("ATLAS(baked)", mat, len(objs), "objs", round(time.time() - t0, 1), "s")
    return [base + "_BaseColor.png", base + "_Normal.png", base + "_MaskMap.png"]


def remove_floaters():
    for o in [o for o in bpy.data.objects if o.get("eoa_hi")]:
        bpy.data.objects.remove(o, do_unlink=True)
