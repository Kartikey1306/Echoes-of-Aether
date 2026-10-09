"""Stage 7b: face and hands: eyeballs (game iris layout), skin atlas (face gets ~2x texel density), 4 skin tones +
normal + mask map, eye texture, brows/lashes, gloves texture, teeth/tongue decimation.

  blender -b out/giva_tex.blend --python s7b_face.py [-- --nobake]
Saves out/giva_face.blend; textures in out/tex.
"""
import bpy, bmesh, sys, os, json, math, importlib, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE, os.path.join(HERE, "..", "..", "scripts")]
import numpy as np
import gv, garment, raster, bake, uvtools, paint as pt, painters, face, browtex
for m in (gv, garment, raster, bake, uvtools, pt, painters, face, browtex):
    importlib.reload(m)
P = gv.P
A = gv.args()
SIZE = 2048
TEX = os.path.join(gv.OUT, "tex")
rig = bpy.data.objects[gv.RIG]
OB = {o.name: o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig}


def uv_islands(o):
    """Face island ids (faces connected through edges whose UVs match at both ends)."""
    me = o.data
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    parent = list(range(len(me.polygons)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    edge_faces = {}
    for f in me.polygons:
        li = list(f.loop_indices)
        vs = [me.loops[l].vertex_index for l in li]
        for k in range(len(vs)):
            a, b = vs[k], vs[(k + 1) % len(vs)]
            key = (min(a, b), max(a, b))
            ua = {a: uv[li[k]], b: uv[li[(k + 1) % len(vs)]]}
            edge_faces.setdefault(key, []).append((f.index, ua))
    for key, lst in edge_faces.items():
        if len(lst) != 2:
            continue
        (f1, u1), (f2, u2) = lst
        if all(np.abs(u1[v] - u2[v]).max() < 1e-5 for v in key):
            ra, rb = find(f1), find(f2)
            if ra != rb:
                parent[ra] = rb
    return np.array([find(i) for i in range(len(me.polygons))])


def stable_skin_uvs(body):
    """Keep the shipped skin UV layout (catalog tattoos are painted in it): out/skin_uv_ref.npy holds the committed
    Body's loop UVs; reused whenever the topology / loop order still matches."""
    p, pl = os.path.join(gv.OUT, "skin_uv_ref.npy"), os.path.join(gv.OUT, "skin_uv_ref_lv.npy")
    if not (os.path.exists(p) and os.path.exists(pl)):
        return False
    me = body.data
    lv = np.array([l.vertex_index for l in me.loops])
    ref_lv = np.load(pl)
    if len(lv) != len(ref_lv) or not (lv == ref_lv).all():
        gv.log("skin uv reference does not match the topology: unwrapping")
        return False
    uv = me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", np.load(p).astype(np.float32).ravel())
    me.uv_layers.active = uv
    gv.log("skin uvs: shipped layout reused (tattoos stay aligned)")
    return True


def skin_uvs(body, head_scale=2.1):
    me = body.data
    if "UVMH" not in me.uv_layers:
        src = me.uv_layers.active
        lay = me.uv_layers.new(name="UVMH")
        d = np.empty(len(me.loops) * 2, np.float32)
        src.data.foreach_get("uv", d)
        lay.data.foreach_set("uv", d)
        me.uv_layers.active = me.uv_layers[src.name]
    isl = uv_islands(body)
    names, W = gv.bone_weights(body)
    headw = np.zeros(len(me.vertices))
    for j, n in enumerate(names):
        if n[len(P):] in ("Head", "Jaw", "LeftEye", "RightEye", "Neck") or "Orbicularis" in n:
            headw += W[:, j]
    fhead = np.array([headw[list(f.vertices)].mean() for f in me.polygons])
    uvtools._edit([body])
    bm = bmesh.from_edit_mesh(me)
    for f in bm.faces:
        f.select = True
    bmesh.update_edit_mesh(me)
    bpy.ops.uv.select_all(action="SELECT")
    try:
        bm.uv_select_sync_from_mesh()
    except Exception:
        pass
    bpy.ops.uv.average_islands_scale()
    # scale head islands up around their centres
    bm = bmesh.from_edit_mesh(me)
    uvl = bm.loops.layers.uv.active
    bm.faces.ensure_lookup_table()
    for k in np.unique(isl):
        fs = np.nonzero(isl == k)[0]
        if fhead[fs].mean() < 0.5:
            continue
        loops = [l for fi in fs for l in bm.faces[int(fi)].loops]
        c = np.mean([np.array(l[uvl].uv) for l in loops], 0)
        for l in loops:
            l[uvl].uv = tuple(c + (np.array(l[uvl].uv) - c) * head_scale)
    bmesh.update_edit_mesh(me)
    bpy.ops.uv.pack_islands(udim_source="CLOSEST_UDIM", rotate=True, margin_method="SCALED", margin=0.004, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")


def decimate_with_shapes(o, ratio):
    import skin_hd
    skin_hd.decimate_with_shapes(o, ratio)


def save(arr, name, srgb=False, mask=None, dil=12):
    a = arr.astype(np.float32)
    if mask is not None:
        a = raster.dilate(a, mask, dil)
    if srgb:
        a = gv.lin_to_srgb(np.clip(a, 0, 1)).astype(np.float32)
    gv.write_image(a, os.path.join(TEX, name))
    return name


GLOVE_SCHEME = {
    # tinted at runtime by outfit * 0.75: neutral light base; leather back, padded knuckles, grippy palm
    0.0: dict(base=(0.62, 0.62, 0.64), metal=0.0, smooth=0.42, wear=0.35, wear_col=(0.8, 0.8, 0.82), grime=0.5, var=0.1),
}


def gloves_tex():
    g = OB["Gloves"]
    uvtools.unwrap_atlas([(g, lambda f: True)], "SMART", 0.006, 60)
    maps = raster.Maps(1024 * 2)
    raster.rasterize(maps, g, 0)
    ao = np.ones((maps.size, maps.size), np.float32) if "--nobake" in A else bake.bake_ao([g], {"Gloves"}, maps.size, 48)
    m = maps.mask
    Pm = maps.P[m].astype(np.float64)
    Nm = maps.N[m]
    H = np.zeros(m.shape, np.float32)
    # back of hand vs palm: palm faces point down/inward in the A-pose (hand normal ~ -Z)
    pal = np.zeros(len(Pm))
    for side, sx in (("Left", 1), ("Right", -1)):
        hb = rig.data.bones[P + side + "Hand"]
        up = np.array(hb.matrix_local.to_3x3() @ __import__("mathutils").Vector((0, 0, 1)))
        sel = np.sign(Pm[:, 0]) == sx
        pal[sel] = (Nm[sel] @ up < -0.2).astype(float)
    # palm grip pads (dots), back: two-panel leather with stitch lines, knuckle padding ribs
    dots = (np.sin(Pm[:, 0] / 0.0022 * math.pi) * np.sin(Pm[:, 1] / 0.0022 * math.pi) > 0.55)
    h = np.where(pal > 0.5, dots * 0.00025, 0.0)
    h += (pt.fbm(Pm, 1500, 2, seed=41) - 0.5) * 0.00008
    kn = np.zeros(len(Pm))
    for side in ("Left", "Right"):
        for fing in ("Index", "Middle", "Ring", "Pinky"):
            bn = rig.data.bones[P + side + "Hand" + fing + "1"]
            kn = np.maximum(kn, 1 - gv.ss(0.006, 0.011, np.linalg.norm(Pm - np.array(bn.head_local), axis=1)))
    h += np.where(pal < 0.5, kn * 0.0009 * (0.5 + 0.5 * np.cos(Pm[:, 2] / 0.003 * math.pi)), 0.0)
    H[m] = h
    nrm = raster.normals_from_height(maps, H, 1.0)
    cls = np.zeros(m.shape, np.float32)
    base, mm = painters.paint_hard(maps, ao, nrm, cls, GLOVE_SCHEME)
    pm = np.zeros(m.shape, np.float32)
    pm[m] = pal
    base[m & (pm > 0.5)] *= 0.55         # darker grippy palm
    mm[m & (pm > 0.5), 3] = 0.25
    return [save(base, "Lyra_Gloves_BaseColor.png", True, m), save(nrm, "Lyra_Gloves_Normal.png", False, m),
            save(mm, "Lyra_Gloves_MaskMap.png", False, m)]


def lash_curl(o, gain=1.3, curl=0.002):
    """Longer, curled upper lashes: every upper-lash vertex moves away from its root on the lid margin (length x gain)
    and its tip rolls forward and up (quadratic in the distance from the root). Shape keys get the same offset."""
    X = gv.basis_co(o)
    D = np.zeros_like(X)
    for side, sx in (("Left", 1), ("Right", -1)):
        e = np.array(rig.data.bones[P + side + "Eye"].head_local)
        sel = (np.sign(X[:, 0]) == sx) & (X[:, 2] > e[2] + 0.0015)
        if sel.sum() < 6:
            continue
        idx = np.nonzero(sel)[0]
        Y = X[idx]
        # root height along the lid: lowest upper-lash vertex within 2 mm in x
        root_z = np.array([Y[np.abs(Y[:, 0] - y[0]) < 0.002][:, 2].min() for y in Y])
        h = np.clip(Y[:, 2] - root_z, 0, None)
        hmax = max(h.max(), 1e-4)
        t = h / hmax
        D[idx, 2] += h * (gain - 1.0) + curl * 0.4 * t ** 2
        D[idx, 1] -= curl * t ** 2                          # forward (-Y)
    gv.set_co(o, X + D)
    me = o.data
    if me.shape_keys:
        for k in me.shape_keys.key_blocks:
            co = np.empty(len(X) * 3, np.float32)
            k.data.foreach_get("co", co)
            k.data.foreach_set("co", (co.reshape(-1, 3) + D).astype(np.float32).ravel())
    me.update()
    gv.log("lashes: upper lashes lengthened x%.2f and curled %.1f mm" % (gain, curl * 1000))


def main():
    out = json.load(open(os.path.join(TEX, "atlases.json"))) if os.path.exists(os.path.join(TEX, "atlases.json")) else {}
    if "Lashes" in OB:
        lash_curl(OB["Lashes"])
    # eyes
    eyes = face.build_eyes(OB["Eyes"], rig)
    for mm_ in eyes.data.materials:
        pass
    eyes.data.materials.clear()
    eyes.data.materials.append(bpy.data.materials.get("Eyes") or bpy.data.materials.new("Eyes"))
    gv.log("eyes", {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in face.EYE_INFO.items()})
    save(face.eye_texture(1024, theta_iris=np.mean([v["theta_iris"] for v in face.EYE_INFO.values()])), "Eye_grey.png")
    # brows: strand-painted texture on the system brow card; lashes: the CC0 system lash texture
    import giva_def
    brow_id = giva_def.ASSETS["eyebrows"].split("/")[0]
    lash_id = giva_def.ASSETS["eyelashes"].split("/")[0]
    src = gv.read_image(os.path.join(gv.MPFB_DATA, "eyebrows", brow_id, brow_id + ".png"))
    gv.write_image(browtex.make(src, 1024, density=2.3), os.path.join(TEX, "Brows_giva.png"))
    # lashes: the CC0 system lash texture with the lower lashes thinned (full lower lashes read as heavy mascara)
    lash = gv.read_image(os.path.join(gv.MPFB_DATA, "eyelashes", lash_id, lash_id + ".png"))
    LH, LW = lash.shape[:2]
    ytd = (LH - 1 - np.arange(LH))[:, None] / LH          # top-down row fraction
    xf = np.arange(LW)[None, :] / LW
    lower = (ytd > 0.585) | ((xf > 0.64) & (ytd > 0.52))
    lash[..., 3] = np.clip(lash[..., 3] * np.where(lower, 0.5, 1.5), 0, 1)     # upper lashes read at designer distance
    gv.write_image(lash, os.path.join(TEX, "Lashes_eyelashes03.png"))
    out["Brows"] = ["Brows_giva.png"]
    out["Lashes"] = ["Lashes_eyelashes03.png"]
    # teeth / tongue: mostly hidden, keep them light
    decimate_with_shapes(OB["Teeth"], 0.22)
    decimate_with_shapes(OB["Tongue"], 0.6)
    # skin
    body = OB["Body"]
    if not stable_skin_uvs(body):
        skin_uvs(body)
    face.add_group_attrs(body)
    maps = raster.Maps(SIZE)
    raster.rasterize(maps, body, 0, None, ("g_lips", "g_ears", "g_scalp", "g_fingernails"))
    ao = np.ones((SIZE, SIZE), np.float32) if "--nobake" in A else bake.bake_ao([body], {"Skin"}, SIZE, 64, 0.04)
    tones, nrm, mm = face.paint_skin(maps, body, rig, ao)
    skins = {}
    for t, img in tones.items():
        skins[t] = save(img, f"Skin_{t}.png", True, maps.mask)
    save(nrm, "Skin_Normal.png", False, maps.mask)
    save(mm, "Skin_MaskMap.png", False, maps.mask)
    out["Skin"] = {"skins": skins, "normal": "Skin_Normal.png", "maskMap": "Skin_MaskMap.png"}
    out["Gloves"] = gloves_tex()
    json.dump(out, open(os.path.join(TEX, "atlases.json"), "w"), indent=1)
    gv.save(os.path.join(gv.OUT, "giva_face.blend"))


main()
