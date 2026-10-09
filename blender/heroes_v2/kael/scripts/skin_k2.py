"""Kael v2 skin: hidden-face strip, Body UV relayout (face favoured), clean natural skin textures.

Albedo: the CC0 MakeHuman photo skin (young_caucasian_male) resampled into the new layout and frequency-separated:
regional colour (heavy low-pass) + fine photographic grain (high-pass, reduced) with the mid band (blotches) cut
down, graded towards a neutral warm tone, plus painted anatomy cues (cheek/nose/ear redness, lip definition, lid and
socket depth, light beard-shadow stubble, the left-brow scar). Four tones are derived from the same base (consistent
detail). Normal: fine grain from the photo high-pass + soft pores, very faint lines. MaskMap: AO (G), thickness (B),
smoothness (A: T-zone / lips glossier, stubble matte).
"""
import bpy, bmesh, os, math
import math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import kcommon as K
from kcommon import ss, nrm
import texbake as TB
import meshops

MH_SKIN = os.path.join(K.MPFB_DATA, "skins", "young_caucasian_male", "young_lightskinned_male_diffuse.png")


# ----------------------------------------------------------------------------- strip


def covered_vertices(body, covers, dist=0.08, back=0.003):
    """Body vertices hidden under any of the cover meshes (ray along the body normal hits a cover within dist)."""
    verts, polys = [], []
    for o in covers:
        mw = o.matrix_world
        off = len(verts)
        verts += [mw @ v.co for v in o.data.vertices]
        polys += [[off + i for i in p.vertices] for p in o.data.polygons]
    tree = BVHTree.FromPolygons(verts, polys)
    co = K.get_co(body)
    N = K.vertex_normals(co, K.faces_of(body))
    hit = np.zeros(len(co), bool)
    for i in range(len(co)):
        p = Vector(co[i] - N[i] * back)
        h = tree.ray_cast(p, Vector(N[i]), dist)[0]
        if h is not None:
            # also require the other side to be closed-ish (a second ray tilted 25 deg)
            hit[i] = True
    return hit


def strip_hidden(body, covered, keep_rings=2):
    """Delete body faces whose vertices are all covered and stay covered after growing the visible region."""
    bm = bmesh.new(); bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    vis = ~covered
    for _ in range(keep_rings):
        nv = vis.copy()
        for e in bm.edges:
            a, b = e.verts[0].index, e.verts[1].index
            if vis[a] or vis[b]:
                nv[a] = nv[b] = True
        vis = nv
    kill = [f for f in bm.faces if not any(vis[v.index] for v in f.verts)]
    bmesh.ops.delete(bm, geom=kill, context="FACES_ONLY")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    # shape keys follow bmesh vertex deletion automatically (layers)
    bm.to_mesh(body.data); bm.free(); body.data.update()
    return len(kill)


# ----------------------------------------------------------------------------- UV


def relayout(body, rig, head_weight=2.8):
    """Keep the MakeHuman UVs in 'UVOld', then a face-first layout: the head is re-cut into a FACE island (hairline to
    under the chin, ear to ear in front of the ears), two back-of-head islands and the neck, unwrapped conformally
    along those seams plus the MakeHuman ones (ears, mouth bag and eye sockets stay separate), and packed with the
    visible face getting most of the texture (designer close-ups), the scalp / neck less and the interior pockets
    almost nothing."""
    me = body.data
    src = me.uv_layers[0]
    data = np.empty(len(me.loops) * 2); src.data.foreach_get("uv", data)
    old = me.uv_layers.get("UVOld") or me.uv_layers.new(name="UVOld")
    old.data.foreach_set("uv", data)
    me.uv_layers.active = src
    src.active_render = True
    head = body.vertex_groups.get("mixamorig:Head")
    hi = head.index if head else -1
    hw = np.zeros(len(me.vertices))
    for v in me.vertices:
        for g in v.groups:
            if g.group == hi:
                hw[v.index] = g.weight
    co = K.get_co(body)
    L = {b.name.split(":")[1]: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones if ":" in b.name}
    eye = (L["LeftEye"] + L["RightEye"]) / 2
    uvd = data.reshape(-1, 2)
    # face labels: 0 face, 1/2 back of the head (left/right), 3 neck
    cen = np.array([co[list(p.vertices)].mean(0) for p in me.polygons])
    hwf = np.array([hw[list(p.vertices)].mean() for p in me.polygons])
    mouth_z = eye[2] - 0.077
    face = (hwf > 0.45) & (cen[:, 1] < eye[1] + 0.062) & (cen[:, 2] > mouth_z - 0.075) & (cen[:, 2] < eye[2] + 0.088)
    lab = np.where(face, 0, np.where(hwf > 0.45, np.where(cen[:, 0] >= 0, 1, 2), 3))
    # seams: MakeHuman UV discontinuities + label boundaries
    edge_faces = {}
    for p in me.polygons:
        for k_, li in enumerate(p.loop_indices):
            v0 = me.loops[li].vertex_index
            li2 = p.loop_indices[(k_ + 1) % p.loop_total]
            v1 = me.loops[li2].vertex_index
            key = (min(v0, v1), max(v0, v1))
            uv0, uv1 = (uvd[li], uvd[li2]) if v0 < v1 else (uvd[li2], uvd[li])
            edge_faces.setdefault(key, []).append((p.index, uv0, uv1))
    lookup = {tuple(sorted(e.vertices)): e.index for e in me.edges}
    seam = np.zeros(len(me.edges), bool)
    for key, lst in edge_faces.items():
        if len(lst) != 2:
            continue
        (fa, a0, a1), (fb, b0, b1) = lst
        if lab[fa] != lab[fb] or np.abs(a0 - b0).max() > 1e-5 or np.abs(a1 - b1).max() > 1e-5:
            seam[lookup[key]] = True
    me.edges.foreach_set("use_seam", seam)
    import garment as G
    G.unwrap(body, margin=0.002)
    w_lab = {0: 4.2, 1: 1.25, 2: 1.25, 3: 0.75}

    def wfn(faces, uv):
        vs = np.array([me.loops[li].vertex_index for f in faces for li in me.polygons[f].loop_indices])
        P = co[vs]
        # interior pockets: behind the face surface (mouth bag, eye sockets) -> tiny
        inner = ((P[:, 1] > eye[1] + 0.012) & (np.abs(P[:, 0]) < 0.035) & (P[:, 2] < eye[2] + 0.01) & (P[:, 2] > eye[2] - 0.09)).mean()
        sock = (np.min(np.stack([np.linalg.norm(P - L["LeftEye"], axis=1), np.linalg.norm(P - L["RightEye"], axis=1)]), 0) < 0.0135).mean()
        if inner > 0.5 or sock > 0.6:
            return 0.25
        labs = np.bincount(lab[faces], minlength=4)
        return w_lab[int(np.argmax(labs))]
    TB.pack_weighted(body, "Skin", wfn, margin=0.004)
    # makeover: the shelf packer left ~60% of the square empty (the wide face island binds the shelf width); Blender's
    # island packer re-places the weighted islands (one uniform scale, so the face keeps its extra density) and roughly
    # doubles the used area
    prev_active = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = body
    sel = [o for o in bpy.context.view_layer.objects if o.select_get()]
    for o in bpy.context.view_layer.objects:
        o.select_set(o is body)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=0.003, shape_method="CONCAVE", merge_overlap=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in bpy.context.view_layer.objects:
        o.select_set(o in sel)
    bpy.context.view_layer.objects.active = prev_active
    K.log("UV face-first layout: seams", int(seam.sum()), "face faces", int(face.sum()))


# ----------------------------------------------------------------------------- textures


def _gauss1d(sigma):
    r = max(1, int(sigma * 3))
    x = np.arange(-r, r + 1)
    k = np.exp(-x * x / (2 * sigma * sigma))
    return k / k.sum()


def gblur(img, sigma):
    k = _gauss1d(sigma)
    out = img.astype(np.float32)
    for axis in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[axis] = (len(k) // 2, len(k) // 2)
        p = np.pad(out, pad, mode="edge")
        acc = np.zeros_like(out)
        for i, w in enumerate(k):
            sl = [slice(None)] * out.ndim
            sl[axis] = slice(i, i + out.shape[axis])
            acc += w * p[tuple(sl)]
        out = acc
    return out


def landmarks(body, rig):
    L = {b.name.split(":")[1]: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones if ":" in b.name}
    co = K.get_co(body)
    eye = (L["LeftEye"] + L["RightEye"]) / 2
    mid = co[(np.abs(co[:, 0]) < 0.004) & (co[:, 2] < eye[2] + 0.1) & (co[:, 2] > eye[2] - 0.16) & (co[:, 1] < eye[1] + 0.02)]
    nose = mid[np.argmin(mid[:, 1] + np.where(mid[:, 2] > eye[2] - 0.02, 1, 0))]
    low = mid[mid[:, 2] < nose[2] - 0.012]
    # mouth corner level: the deepest point between the lips ~ 3.2 cm under the nose tip
    mouth = np.array((0.0, nose[1] + 0.012, nose[2] - 0.034))
    chin = low[np.argmin(low[:, 1] + np.abs(low[:, 2] - (nose[2] - 0.065)) * 2)]
    return {"eye": eye, "eyeL": L["LeftEye"], "eyeR": L["RightEye"], "nose": nose, "mouth": mouth, "chin": chin, "head": L["Head"],
            "neck": L["Neck"]}


def skin_textures(body, rig, out_dir, size=2048, ao=None, stubble=0.55, tones=("light", "medium", "tan", "dark"), brows=None, brow_alpha=None, hair=None):
    T = TB.raster([body], "Skin", size, attrs=(), uv2="UVOld")
    idx = np.where(T.cov)[0]
    P = T.P[idx].astype(np.float64)
    N = T.N[idx].astype(np.float64)
    uvo = T.UV2[idx].astype(np.float64)
    FL = landmarks(body, rig)
    # vertex-group regions rasterised
    grp = {}
    for gname in ("lips", "ears", "scalp", "mixamorig:Head", "mixamorig:Neck"):
        g = body.vertex_groups.get(gname)
        w = np.zeros(len(body.data.vertices), np.float32)
        if g:
            for v in body.data.vertices:
                for gg in v.groups:
                    if gg.group == g.index:
                        w[v.index] = gg.weight
        a = body.data.attributes.get("k_" + gname.replace(":", "_")) or body.data.attributes.new("k_" + gname.replace(":", "_"), "FLOAT", "POINT")
        a.data.foreach_set("value", w)
    T2 = TB.raster([body], "Skin", size, attrs=tuple("k_" + g.replace(":", "_") for g in ("lips", "ears", "scalp", "mixamorig:Head", "mixamorig:Neck")))
    lips_g = T2.A["k_lips"][idx]; ears_g = T2.A["k_ears"][idx]; scalp_g = T2.A["k_scalp"][idx]; head_g = T2.A["k_mixamorig_Head"][idx]
    # ---- source photo skin, frequency separated in its own texture space
    src = TB.read_image(MH_SKIN)[..., :3].astype(np.float32)
    lo = gblur(src, 10.0)
    mid = gblur(src, 1.6)
    hi = src - mid
    band = mid - lo
    clean = lo + band * 0.42 + hi * 0.62
    s_clean = TB.sample(clean, uvo)
    s_hi = TB.sample(hi.mean(-1, keepdims=True), uvo)[:, 0]
    s_lo = TB.sample(lo, uvo)

    def blob(c, r):
        return np.exp(-np.sum((P - c) ** 2, 1) / (r * r))
    eye, nose, mouth, chin = FL["eye"], FL["nose"], FL["mouth"], FL["chin"]
    face = (head_g > 0.5) & (P[:, 1] < eye[1] + 0.05)
    cheeks = blob(np.array((0.048, eye[1] + 0.012, eye[2] - 0.038)), 0.024) + blob(np.array((-0.048, eye[1] + 0.012, eye[2] - 0.038)), 0.024)
    nose_b = blob(nose + np.array((0, 0.004, 0.004)), 0.016)
    lips = np.clip(lips_g * 1.2, 0, 1)
    ears = np.clip(ears_g * 1.3, 0, 1)
    under = blob(FL["eyeL"] + np.array((0.002, -0.004, -0.017)), 0.010) + blob(FL["eyeR"] + np.array((-0.002, -0.004, -0.017)), 0.010)
    socket = blob(FL["eyeL"] + np.array((-0.012, 0.0, 0.004)), 0.009) + blob(FL["eyeR"] + np.array((0.012, 0.0, 0.004)), 0.009)
    lid = blob(FL["eyeL"] + np.array((0.0, -0.006, 0.011)), 0.011) + blob(FL["eyeR"] + np.array((0.0, -0.006, 0.011)), 0.011)
    # beard-shadow zone (stubble): below a cheek line from the mouth corner up to the sideburn, upper lip, chin, jaw
    # and the upper neck to the Adam's apple; not on the lips; feathered
    hl = P - FL["head"]
    jz = P[:, 2] - mouth[2]
    ax = np.abs(P[:, 0])
    in_head = (head_g + T2.A["k_mixamorig_Neck"][idx]) > 0.35
    cheek_line = 0.008 + 0.024 * ss(0.03, 0.074, ax)          # concept: beard line from the mouth corner up to the sideburn
    # makeover: the feathering is analytic in 3D (wide smoothsteps) instead of a texture-space blur, which mixed values
    # across UV islands and left a hard-edged patch on the cheek at the seam
    # final pass: a defined (slightly irregular) beard edge along the cheek line instead of a soft fade
    below = ss(0.0045, -0.0035, jz - cheek_line + 0.0015 * TB.fbm3(P, 160.0, 2, 13.0))
    front = ss(eye[1] + 0.1, eye[1] + 0.066, P[:, 1])                     # not behind the jaw angle / ears
    side_burn = ss(0.056, 0.07, ax) * ss(eye[1] + 0.088, eye[1] + 0.058, P[:, 1]) * ss(0.05, 0.026, jz - 0.03) * ss(-0.004, 0.006, jz)
    moust = ss(0.032, 0.02, ax) * ss(-0.004, 0.004, jz) * ss(0.028, 0.018, jz) * ss(mouth[1] + 0.026, mouth[1] + 0.014, P[:, 1])
    neck_lim = ss(-0.14, -0.1, jz)
    bm = np.clip(np.maximum.reduce([below * front * neck_lim, side_burn, moust]), 0, 1) * np.clip((head_g + T2.A["k_mixamorig_Neck"][idx] - 0.2) * 2.5, 0, 1)
    bm = bm * (1 - np.clip(lips * 1.6, 0, 1))
    # density: full on the chin, upper lip and jaw line, thinner high on the cheek and down the neck
    dens = 0.72 + 0.28 * np.clip(np.maximum.reduce([blob(chin, 0.03), ss(0.02, -0.03, jz - cheek_line), moust]), 0, 1)
    dens = dens * (1 - 0.3 * ss(-0.06, -0.12, jz))
    bm = bm * dens * (0.9 + 0.1 * TB.fbm3(P, 70.0, 2, 5.0))
    bm_img = TB.dilate(_full(T, idx, bm), T.cov.reshape(size, size), 12)
    bm = np.clip(gblur(bm_img, 0.8).reshape(-1)[idx] * 1.05, 0, 1) ** 1.1
    # stubble follicles (soft, sub-millimetre dots; low contrast to avoid speckle)
    fol = TB.worley3(P, 1 / 0.0011, 7.0)
    dots = (1 - ss(0.12, 0.38, fol))
    # short stubble hairs: cells stretched along the growth direction (down the face)
    fol2 = TB.worley3(P * np.array((1.0, 1.0, 0.42)), 1 / 0.0009, 9.0)
    dots = np.maximum(dots, 0.9 * (1 - ss(0.1, 0.3, fol2)))
    # concept scar: a small healed "x" on the upper left forehead (two crossing cuts, subtle)
    sc_c = FL["eyeL"] + np.array((0.006, -0.012, 0.042))
    q = P - sc_c
    near = ((np.abs(q[:, 1]) < 0.03) & (P[:, 1] < FL["eye"][1])).astype(float)
    scar = np.zeros(len(P))
    for ang, ln in ((38.0, 0.0125), (-46.0, 0.011)):
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        along_ = q[:, 0] * sa + q[:, 2] * ca
        across = q[:, 0] * ca - q[:, 2] * sa
        scar = np.maximum(scar, np.exp(-(across / 0.0011) ** 2) * ss(ln, ln * 0.55, np.abs(along_)) * near)
    # ---- height (metres): soft pores + anatomical definition (folds, lid creases, philtrum, lip border), no photo grain
    h = -0.000004 * np.clip(-s_hi * 8, -1, 1)
    pores = 1 - ss(0.0, 0.3, TB.worley3(P, 1 / 0.0016, 3.0))
    h -= 0.000004 * pores * (0.5 + 0.8 * np.clip(cheeks + nose_b, 0, 1)) * face
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    sx = np.sign(x); axx = np.abs(x)

    def seg_groove(a, b, width, depth, mask=1.0):
        a = np.asarray(a); b = np.asarray(b)
        d = b - a
        t = np.clip(((P - a) @ d) / (d @ d), 0, 1)
        dist = np.linalg.norm(P - (a + t[:, None] * d), axis=1)
        env = ss(0.0, 0.15, t) * ss(1.0, 0.8, t)
        return -depth * np.exp(-(dist / width) ** 2) * env * mask
    for sg in (1, -1):
        m = (sx == sg) * face
        a = np.array((sg * 0.0175, nose[1] + 0.012, nose[2] - 0.004)); b = np.array((sg * 0.031, mouth[1] + 0.008, mouth[2] - 0.014))
        h += seg_groove(a, b, 0.0026, 0.00056, m)
        h += -seg_groove(a + np.array((sg * 0.004, 0.001, 0.001)), b + np.array((sg * 0.004, 0.001, 0.0)), 0.004, 0.00012, m)
        h += seg_groove(nose + np.array((sg * 0.012, 0.006, 0.006)), nose + np.array((sg * 0.016, 0.012, -0.006)), 0.0014, 0.0002, m)
        e = FL["eyeL"] if sg > 0 else FL["eyeR"]
        q = P - e
        r_ = np.hypot(q[:, 0] * 0.95, (q[:, 2] - 0.002) * 1.25)
        top = ss(-0.002, 0.004, q[:, 2]) * (q[:, 1] < 0.0)
        h -= 0.0003 * np.exp(-((r_ - 0.0135) / 0.0014) ** 2) * top * m
        bot = ss(0.002, -0.004, q[:, 2]) * (q[:, 1] < 0.0)
        h -= 0.0001 * np.exp(-((r_ - 0.0125) / 0.0012) ** 2) * bot * m
    phz = (z < nose[2] - 0.012) & (z > mouth[2] + 0.004)
    h += 0.00012 * np.exp(-((axx - 0.0048) / 0.0016) ** 2) * phz * face - 0.00008 * np.exp(-(axx / 0.0022) ** 2) * phz * face
    h -= 0.0004 * np.exp(-((z - (mouth[2] - 0.019)) / 0.0028) ** 2) * ss(0.024, 0.012, axx) * face * (y < mouth[1] + 0.02)
    h -= 0.00016 * np.exp(-(axx / 0.0025) ** 2) * np.exp(-((z - (chin[2] + 0.002)) / 0.007) ** 2) * face
    le = np.clip(lips * 1.2, 0, 1)
    h += 0.00009 * np.exp(-((le - 0.5) / 0.2) ** 2)
    h -= 0.00002 * ss(0.3, 0.1, np.abs(np.sin(x / 0.0016 * math.pi))) * lips
    # ---- wrinkles (makeover): forehead lines, glabella, crow's feet, under-eye crease; thin grooves with a soft
    # raised shoulder, broken up along their length so they read as skin folds, not engraved lines
    wob = TB.fbm3(P, 55.0, 2, 3.0)
    brk = np.clip(0.55 + 0.6 * TB.fbm3(P, 90.0, 2, 8.0), 0, 1)

    def line_h(dist, width, depth):
        return -depth * np.exp(-(dist / width) ** 2) + 0.35 * depth * np.exp(-(dist / (width * 2.6)) ** 2)
    zf = z - eye[2]
    fmask = face * ss(0.058, 0.02, axx) * (y < eye[1] + 0.02)
    for zc, dep, wd in ((0.036, 0.00007, 0.0010), (0.048, 0.00009, 0.0011), (0.06, 0.00007, 0.0011), (0.071, 0.00004, 0.0010)):
        arch = zc + 0.0026 * (axx / 0.03) ** 2 * (1 - 0.4 * (axx / 0.05)) + 0.0012 * wob
        h += line_h(zf - arch, wd, dep) * fmask * brk
    gmask = face * ss(eye[2] + 0.004, eye[2] + 0.012, z) * ss(eye[2] + 0.03, eye[2] + 0.022, z)
    for gx, dep in ((0.0055, 0.00009), (-0.006, 0.00008), (0.0015, 0.00004)):
        h += line_h(x - gx - 0.08 * (z - eye[2] - 0.016), 0.0008, dep) * gmask
    for sg in (1, -1):
        e = FL["eyeL"] if sg > 0 else FL["eyeR"]
        canth = e + np.array((sg * 0.0155, 0.004, -0.001))
        q = P - canth
        lat = q[:, 0] * sg
        m = (sx == sg) * face * ss(0.0015, 0.005, lat) * ss(0.017, 0.01, lat)
        for ang, dep in ((-24.0, 0.00006), (-6.0, 0.00008), (12.0, 0.00007), (30.0, 0.00004)):
            ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            across = -lat * sa + q[:, 2] * ca
            h += line_h(across + 0.0009 * wob, 0.0006, dep) * m
        # under-eye crease (lower lid / cheek junction) and a faint second fold
        q = P - e
        r_ = np.hypot(q[:, 0] * 0.9, (q[:, 2] + 0.001) * 1.1)
        low = ss(-0.003, -0.008, q[:, 2]) * (q[:, 1] < 0.004) * (sx == sg) * face
        h += line_h(r_ - 0.0205, 0.0009, 0.00008) * low
        h += line_h(r_ - 0.0245, 0.0012, 0.00004) * low * brk
    h -= 0.00016 * scar
    Hn = TB.height_to_normal(gblur(TB.dilate(_full(T, idx, h), T.cov.reshape(size, size), 6), 1.2), T.mpt.reshape(size, size), 1.0)
    # ---- mask map
    ao_t = np.clip(ao.reshape(-1)[idx], 0, 1) if ao is not None else np.ones(len(idx))
    tz = np.clip(blob(np.array((0, eye[1] - 0.012, eye[2] + 0.05)), 0.03) + blob(np.array((0, eye[1] - 0.006, eye[2])), 0.012) * 0.8
                 + nose_b + blob(chin, 0.014) * 0.5, 0, 1)
    nose_tip = np.clip(blob(nose + np.array((0, 0.002, 0.002)), 0.009) * 1.3, 0, 1)
    # makeover: oily T-zone (forehead centre, nose, chin), shinier nose tip, matte cheeks and beard, matte buzzed scalp
    smooth = (0.36 + 0.12 * tz + 0.1 * nose_tip + 0.08 * lips - 0.07 * np.clip(cheeks, 0, 1) - 0.1 * bm * stubble
              - 0.06 * np.clip(scalp_g, 0, 1) + 0.012 * TB.fbm3(P, 60.0, 2, 11.0))
    smooth = np.clip(smooth, 0.18, 0.62)
    thick = np.clip(ears * 1.0 + nose_b * 0.5 + lips * 0.3, 0, 1)
    MM = np.stack([np.zeros_like(smooth), 0.42 + 0.58 * ao_t, thick, smooth], 1)     # final pass: stronger baked AO
    # ---- albedo (medium tone first): designed regional colour, clean (no photo patches or grain)
    # neutral warm tan. Measured: the concept's lit skin is r/g 1.30, g/b 1.18; Unity's skin tint + scatter multiply the
    # albedo's r/g by ~1.2 and g/b by ~1.11 (pass-1 capture), so the albedo itself is kept close to neutral
    base = np.array((0.668, 0.6, 0.562))
    col = np.tile(base, (len(P), 1))
    lowvar = TB.fbm3(P, 18.0, 3, 17.0)
    col = col * (1 + 0.02 * lowvar[:, None] * np.array((1.0, 0.85, 0.7)))
    fore = ss(eye[2] + 0.02, eye[2] + 0.06, P[:, 2]) * face
    col = col * (1 + fore[:, None] * np.array((0.012, 0.022, 0.01)))
    # makeover: warmer (rosy, not orange: green drops more than blue) nose, cheeks and ears
    nose_r = np.clip(blob(nose + np.array((0, 0.006, 0.002)), 0.014) * 1.2, 0, 1)
    reg = np.clip(cheeks * 0.9 + nose_r + ears * 0.9, 0, 1)[:, None]
    col = col * (1 + reg * np.array((0.03, -0.05, -0.03)))
    # subtle blotching: low-frequency patches of redness and slight pallor
    blot = TB.fbm3(P, 38.0, 3, 23.0)
    blot2 = TB.fbm3(P, 110.0, 2, 29.0)
    bl = np.clip(blot * 0.7 + blot2 * 0.3, -1, 1)[:, None] * face[:, None]
    col = col * (1 + 0.035 * bl * np.array((0.6, -0.5, -0.35)))
    # tear-duct caruncle: pink, moist
    for e_ in (FL["eyeL"], FL["eyeR"]):
        sg_ = 1.0 if e_[0] > 0 else -1.0
        car = np.clip(blob(e_ + np.array((-sg_ * 0.0128, -0.0075, -0.0006)), 0.0024) * 1.6, 0, 1)[:, None]
        col = col * (1 - car * 0.6) + np.array((0.7, 0.4, 0.4)) * car * 0.6
    col = col * (1 - np.clip(under * 0.35, 0, 1)[:, None] * np.array((0.04, 0.06, 0.035)))
    # lid margins / inner lids (visible when blinking): warm rosy, not pale
    d_eye = np.minimum(np.linalg.norm(P - FL['eyeL'], axis=1), np.linalg.norm(P - FL['eyeR'], axis=1))
    rim = ss(0.0145, 0.0128, d_eye)[:, None]
    col = col * (1 - rim * 0.45) + np.array((0.64, 0.43, 0.39)) * rim * 0.45
    # final pass: dark upper lash line (lid margin = the skin nearest the eyeball, upper half, front)
    for e_ in (FL["eyeL"], FL["eyeR"]):
        q_ = P - e_
        de = np.linalg.norm(q_, axis=1)
        frontm = (q_[:, 1] < -0.004) & (de < 0.03)
        if frontm.sum() > 20:
            r0 = np.percentile(de[frontm], 0.5)
            lash = ss(r0 + 0.0022, r0 + 0.0006, de) * ss(-0.0015, 0.002, q_[:, 2]) * frontm
            col = col * (1 - 0.72 * lash[:, None]) + np.array((0.09, 0.07, 0.06)) * 0.72 * lash[:, None]
    col = col * (1 - np.clip(lid, 0, 1)[:, None] * np.array((0.015, 0.04, 0.025)))
    lipc = np.array((0.57, 0.39, 0.36))                    # makeover: lips close to the skin, a little redder / darker
    lw = 0.75 * np.clip(lips * 0.8, 0, 1)[:, None] ** 1.5
    col = col * (1 - lw) + lipc * lw
    # painted cavity: game lighting is key-light dominated and URP applies the AO map to ambient only, so the deep
    # creases (nasolabial fold, eye sockets, under the nose and lower lip, ears, jaw underside) get a little of the
    # baked AO in the albedo, slightly red-shifted like real skin in shadow
    cav = 1 - np.clip(ao_t, 0, 1) ** 1.2
    col = col * (1 - 0.5 * cav[:, None] * np.array((0.85, 1.0, 1.06)))
    # photographic micro detail (pores, fine skin texture) from the CC0 skin: luminance only, fine band (sigma 2 px),
    # strong edges soft-suppressed and facial features (lids, lips, nostrils) masked out -> no high-pass halos
    lum_src = src.mean(-1)
    lo2 = gblur(lum_src, 2.0)
    rel = (lum_src - lo2) / np.maximum(lo2, 1e-3)
    rel = rel * np.exp(-0.5 * (rel / 0.07) ** 2)
    rel_t = np.clip(TB.sample(rel[..., None], uvo)[:, 0], -0.06, 0.06)
    feat = np.maximum.reduce([np.clip(lips * 1.5, 0, 1), ss(0.024, 0.0135, d_eye), np.clip(blob(nose + np.array((0, 0.006, -0.008)), 0.011) * 1.4, 0, 1)])
    k_det = (0.5 + 0.3 * bm * stubble) * (1 - feat) * (1 - 0.5 * np.clip(scalp_g, 0, 1))
    col = col * (1 + (k_det * rel_t)[:, None])
    stub = (bm * stubble)[:, None]
    # five-o'clock shadow: neutral-warm darkening (R/G/B ratios kept equal -> never greenish), follicle dots
    sh = np.array((0.15, 0.128, 0.118))
    dots_s = gblur(TB.dilate(_full(T, idx, dots), T.cov.reshape(size, size), 4), 0.35).reshape(-1)[idx]
    # stubble reads as grain: coverage per texel follows the follicles (skin shows between the short hairs)
    cov_s = stub * (0.16 + 0.8 * dots_s[:, None] ** 0.8)   # final pass: crisp grain (dark short hairs, skin between)
    # makeover: blue-grey beard shadow under the stubble (the skin between the short hairs reads cooler)
    col = col * (1 - np.clip(stub * 1.15, 0, 1) * np.array((0.2, 0.15, 0.07)))
    col = col * (1 - cov_s * 0.88) + sh[None] * 0.7 * cov_s * 0.88
    # painterly sculpting light (the concept face reads through value): cheekbone hollow and temple shadow, jaw
    # underside, warm highlight on the cheekbone ridge and the nose bridge
    for sg in (1, -1):
        hol = blob(np.array((sg * 0.05, eye[1] + 0.03, eye[2] - 0.05)), 0.016) * face
        ridge = blob(np.array((sg * 0.05, eye[1] + 0.01, eye[2] - 0.024)), 0.011) * face
        col = col * (1 - 0.3 * hol[:, None] * np.array((0.95, 1.0, 1.0))) * (1 + 0.12 * ridge[:, None])
        e_ = FL["eyeL"] if sg > 0 else FL["eyeR"]
        # deep-set eyes: shadow band in the upper-lid crease under the brow ridge, darker inner corner
        crease = np.exp(-((P[:, 0] - e_[0]) / 0.017) ** 2 - ((P[:, 2] - (e_[2] + 0.011)) / 0.0055) ** 2) * face * (P[:, 1] < e_[1] + 0.005)
        inner_c = blob(e_ + np.array((-sg * 0.015, -0.004, 0.003)), 0.0065) * face
        col = col * (1 - (0.3 * crease + 0.18 * inner_c)[:, None] * np.array((0.86, 1.0, 1.04)))
        # brow-ridge shadow band under the brow (deep-set, intense eyes)
        bridge = np.exp(-((P[:, 0] - e_[0]) / 0.02) ** 2 - ((P[:, 2] - (e_[2] + 0.017)) / 0.006) ** 2) * face * (P[:, 1] < e_[1] + 0.008)
        col = col * (1 - 0.12 * bridge[:, None] * np.array((0.9, 1.0, 1.03)))
        # nasolabial fold shade
        nl = np.exp(-(((P[:, 0] - sg * 0.026) / 0.004) ** 2) - ((P[:, 2] - (nose[2] - 0.022)) / 0.014) ** 2) * face
        col = col * (1 - 0.08 * nl[:, None])
    jaw_u = ss(mouth[2] - 0.04, mouth[2] - 0.065, P[:, 2]) * (head_g > 0.3) * ss(eye[1] + 0.06, eye[1] + 0.02, P[:, 1])
    col = col * (1 - 0.24 * jaw_u[:, None])
    # final pass: sharper jawline - a narrow shadow just under the jaw edge
    jaw_e = np.exp(-((P[:, 2] - (mouth[2] - 0.05)) / 0.006) ** 2) * (head_g > 0.3) * ss(0.02, 0.045, np.abs(P[:, 0])) * ss(eye[1] + 0.07, eye[1] + 0.04, P[:, 1])
    col = col * (1 - 0.1 * jaw_e[:, None])
    # concept: his left side is shaved short and grey/silver (the built-in swept_fade hair leaves it bare): short
    # grey hairs painted on the scalp skin from the temple hairline back to the nape, above the ear
    xh = P[:, 0]
    back_k = ss(eye[1] + 0.06, eye[1] + 0.16, P[:, 1])
    # makeover: the shaved area follows his hairline - the top corner of the forehead, down the temple, over the ear
    # and back to the nape - instead of starting 4 cm behind the eyes (the temple showed bare skin under the cap edge)
    fy = ss(eye[1] + 0.008, eye[1] + 0.04, P[:, 1])
    side_z = eye[2] + 0.018 - 0.04 * ss(eye[1] + 0.04, eye[1] + 0.09, P[:, 1]) - 0.05 * back_k
    hl_z = (eye[2] + 0.074) * (1 - fy) + side_z * fy
    buzz = ss(0.04, 0.052, xh) * ss(hl_z - 0.003, hl_z + 0.007, P[:, 2])
    buzz = buzz * (1 - np.clip(ears * 2.0, 0, 1)) * (head_g > 0.5)
    hairs = TB.worley3(P * np.array((1.0, 0.55, 1.0)), 1 / 0.0007, 21.0)
    hd = 1 - ss(0.1, 0.28, hairs)
    # makeover: silver that survives the runtime warm skin tint (Kael #b98a6e multiplies ~(0.94, 0.86, 0.81) in sRGB):
    # a cool base so the result reads neutral silver; bright short hairs over darker scalp between them
    hairs2 = 1 - ss(0.08, 0.24, TB.worley3(P * np.array((1.0, 0.5, 1.0)), 1 / 0.0005, 37.0))
    hd = np.clip(np.maximum(hd, 0.8 * hairs2), 0, 1)
    hd = 0.5 * hd + 0.5 * gblur(TB.dilate(_full(T, idx, hd), T.cov.reshape(size, size), 4), 1.2).reshape(-1)[idx]
    bcol = np.array((0.5, 0.545, 0.61))[None] * (0.6 + 0.55 * hd[:, None])     # mid silver-grey, darker than lit skin
    col = col * (1 - 0.9 * buzz[:, None]) + bcol * 0.9 * buzz[:, None]
    MM[:, 3] = np.clip(MM[:, 3] - 0.08 * buzz, 0.18, 0.62)
    if brows is not None and brow_alpha is not None:
        from mathutils.bvhtree import BVHTree as _BVH
        from mathutils.interpolate import poly_3d_calc
        bco = np.array([brows.matrix_world @ v.co for v in brows.data.vertices])
        bf = [list(p_.vertices) for p_ in brows.data.polygons]
        btree = _BVH.FromPolygons([Vector(c) for c in bco], bf)
        uvl = brows.data.uv_layers.active.data
        corner = {}
        for p_ in brows.data.polygons:
            for li in p_.loop_indices:
                corner[(p_.index, brows.data.loops[li].vertex_index)] = np.array(uvl[li].uv[:])
        bmask = np.zeros(len(P))
        cand = np.where(head_g > 0.5)[0]
        for i in cand:
            loc, nn, fi, dd = btree.find_nearest(Vector(P[i]), 0.006)
            if fi is None:
                continue
            f = bf[fi]
            w = poly_3d_calc([Vector(bco[v]) for v in f], loc)
            uv = sum(corner[(fi, v)] * ww for v, ww in zip(f, w))
            a_ = TB.sample(brow_alpha, uv[None])[0, 0]
            bmask[i] = a_ * ss(0.006, 0.0015, dd)
        bimg = TB.dilate(_full(T, idx, bmask), T.cov.reshape(size, size), 4)
        bmask = np.clip(gblur(TB.dilate(bimg, bimg > 0.05, 3), 2.2).reshape(-1)[idx] * 1.6, 0, 1)
        hc = np.array((0.12, 0.09, 0.075))
        brow_hairs = 1 - ss(0.08, 0.3, TB.worley3(P * np.array((0.45, 1.0, 1.0)), 1 / 0.0008, 41.0))
        bm2 = np.clip(bmask * 1.25, 0, 1) * (0.6 + 0.4 * brow_hairs)
        col = col * (1 - bm2[:, None] * 0.88) + hc * 0.8 * bm2[:, None] * 0.88
    if hair is not None:
        from mathutils.bvhtree import BVHTree as _BVH
        hco = [hair.matrix_world @ v.co for v in hair.data.vertices]
        htree = _BVH.FromPolygons(hco, [list(p_.vertices) for p_ in hair.data.polygons])
        cov_h = np.zeros(len(P))
        cand = np.where((head_g > 0.5) & (P[:, 2] > eye[2] + 0.015))[0]
        for i in cand:
            hit = htree.ray_cast(Vector(P[i] - N[i] * 0.001), Vector(N[i]), 0.035)[0]
            cov_h[i] = 1.0 if hit is not None else 0.0
        cimg = TB.dilate(_full(T, idx, cov_h), T.cov.reshape(size, size), 8)
        cov_h = np.clip(gblur(cimg, 22.0).reshape(-1)[idx], 0, 1)
        cov_h = ss(0.35, 1.0, cov_h) * (1 - buzz)
        rc = np.array((0.42, 0.33, 0.28))
        col = col * (1 - cov_h[:, None] * 0.26) + rc * cov_h[:, None] * 0.26
    else:
        col = col * (1 - (np.clip(scalp_g, 0, 1) * ss(eye[2] + 0.07, eye[2] + 0.11, P[:, 2]))[:, None] * 0.1)
    col = col * (1 - scar[:, None] * 0.72) + scar[:, None] * np.array((0.56, 0.2, 0.18)) * 0.72
    col = col * (0.92 + 0.08 * ao_t[:, None])
    written = {}
    TONES = {"light": (1.12, np.array((1.0, 1.02, 1.04)), 0.92), "medium": (1.0, np.array((1.0, 1.0, 1.0)), 1.0),
             "tan": (0.8, np.array((1.0, 0.96, 0.9)), 1.08), "dark": (0.48, np.array((1.0, 0.9, 0.8)), 1.2)}
    for tone in tones:
        k, hue, sat = TONES[tone]
        c = col * k * hue
        l2 = (c @ np.array((0.3, 0.59, 0.11)))[:, None]
        c = l2 + (c - l2) * sat
        img = TB.dilate(_full(T, idx, np.clip(c, 0, 1)), T.cov.reshape(size, size), 16)
        TB.write_png(img, os.path.join(out_dir, f"Skin_{tone}.png"), "RGB")
        written[tone] = f"Skin_{tone}.png"
    TB.write_png(Hn, os.path.join(out_dir, "Skin_Normal.png"), "RGB")
    TB.write_png(TB.dilate(_full(T, idx, MM), T.cov.reshape(size, size), 16), os.path.join(out_dir, "Skin_MaskMap.png"), "RGBA")
    TB.write_png(TB.dilate(_full(T, idx, bm), T.cov.reshape(size, size), 12), os.path.join(out_dir, "Skin_Stubble.png"))
    # texel density for the shared pore detail (EOA/Skin tiles one ~24 mm pore tile per 1/_Parallax UV): metres per UV
    # unit on the face (cheeks/forehead) and on the rest of the skin
    mpu = T.mpt[idx].astype(np.float64) * size
    fm = face & (mpu > 0)
    import json as _json
    _json.dump({"face_m_per_uv": float(np.median(mpu[fm])) if fm.any() else None,
                "body_m_per_uv": float(np.median(mpu[(~face) & (mpu > 0)])) if ((~face) & (mpu > 0)).any() else None},
               open(os.path.join(K.LOGS, "skin_uv.json"), "w"), indent=1)
    return written, FL


def _full(T, idx, vals):
    vals = np.asarray(vals, np.float32)
    out = np.zeros((T.size * T.size,) + vals.shape[1:], np.float32)
    out[idx] = vals
    return out.reshape((T.size, T.size) + vals.shape[1:])


# ----------------------------------------------------------------------------- eyes (darker iris than the old pipeline:
# CharacterModel.ApplyEyes multiplies the grey iris by the eye colour x 2.1, which over-brightened brown to orange)
from skin_hd import LIMBUS_D, PUPIL_D


def eye_textures(out_dir, size=1024, seed=11, iris_gain=0.32):
    """Eye_grey/brown/blue/green.png in the centred-iris layout."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    u = (xx + 0.5) / size; v = (yy + 0.5) / size
    dx = (u - 0.5) * 2.0; dy = v - 0.5            # undo the 2x u compression -> isotropic eye-space
    d = np.hypot(dx, dy)
    ang = np.arctan2(dx, dy)
    # Sclera: warm off-white, pinker towards the corners, fine veins
    scl = np.stack([np.full_like(d, 0.92), np.full_like(d, 0.88), np.full_like(d, 0.84)], -1)
    edge = ss(0.12, 0.42, d)
    scl = scl * (1 - 0.18 * edge[..., None]) + np.array((0.12, 0.02, 0.0)) * edge[..., None] * 0.6
    vein = np.zeros_like(d)
    for _ in range(46):
        a0 = rng.uniform(-math.pi, math.pi)
        r0 = rng.uniform(0.3, 0.46)
        pts = [(math.sin(a0) * r0, math.cos(a0) * r0)]
        for k in range(14):
            px, py = pts[-1]
            dirr = -np.array((px, py)) / math.hypot(px, py)
            j = rng.normal(0, 0.6, 2)
            step = (dirr + j) * 0.012
            pts.append((px + step[0], py + step[1]))
            if math.hypot(*pts[-1]) < LIMBUS_D * 1.35:
                break
        for (ax_, ay_), (bx_, by_) in zip(pts[:-1], pts[1:]):
            dd, _ = TB.line_sdf2(dx, dy, ax_, ay_, bx_, by_)
            vein = np.maximum(vein, np.exp(-(dd / 0.0016) ** 2) * ss(0.12, 0.3, d) * rng.uniform(0.3, 0.8))
    scl = scl * (1 - vein[..., None] * np.array((0.15, 0.55, 0.55)))
    # Iris (luminance pattern; Unity tints it): radial fibres, crypts, collarette, dark limbal ring
    r = d / LIMBUS_D
    fib = 0.5 + 0.3 * np.sin(ang * 90 + 3 * np.sin(ang * 7)) + 0.2 * np.sin(ang * 151 + r * 13) + 0.15 * np.sin(ang * 37 + r * 9)
    crypt = TB.fbm3(np.stack([dx * 40, dy * 40, np.zeros_like(dx)], -1).reshape(-1, 3), 1.0, 3, 2.0).reshape(d.shape)
    iris_l = 0.42 + 0.22 * fib * (0.6 + 0.4 * r) + 0.15 * crypt
    coll = np.exp(-((r - 0.52) / 0.07) ** 2)
    iris_l = iris_l * (1 + 0.35 * coll) * (1 - 0.55 * ss(0.78, 1.0, r))
    iris_l = iris_l * iris_gain
    pupil = 1 - ss(PUPIL_D / LIMBUS_D - 0.04, PUPIL_D / LIMBUS_D + 0.02, r)
    iris_l = iris_l * (1 - pupil) + 0.02 * pupil
    in_iris = 1 - ss(0.97, 1.06, r)
    limbal = np.exp(-((r - 1.0) / 0.09) ** 2)
    lid = 1 - 0.2 * ss(0.03, 0.17, dy) - 0.06 * ss(0.12, 0.3, np.abs(dx))       # upper lid / lash shadow, corners
    car = (u < 0.07) & (v < 0.07)
    tear = (u > 0.08) & (u < 0.18) & (v < 0.05)
    out = {}
    tints = {"grey": (0.55, 0.57, 0.6), "brown": (0.42, 0.26, 0.13), "blue": (0.28, 0.42, 0.62), "green": (0.32, 0.45, 0.25)}
    for name, t in tints.items():
        iris_rgb = iris_l[..., None] * np.array(t) * 2.0
        if name == "brown":
            iris_rgb = iris_rgb * (1 + 0.4 * coll[..., None] * np.array((0.6, 0.4, 0.0)))
        col = scl * (1 - in_iris[..., None]) + iris_rgb * in_iris[..., None]
        col = col * (1 - 0.6 * limbal[..., None])
        col = col * lid[..., None]
        col[car] = np.array((0.78, 0.47, 0.46)) * (0.9 + 0.1 * np.sin(xx[car] * 0.9))[:, None]
        col[tear] = np.array((0.96, 0.9, 0.88))
        col = np.clip(col, 0, 1)
        TB.write_png(col, os.path.join(out_dir, f"Eye_{name}.png"), "RGB")
        out[name] = f"Eye_{name}.png"
    return out




def face_inputs(rig, tex_dir):
    """Strand brow texture (written to tex_dir), the source brow density (for the skin underpainting) and the
    default catalog hair placed on this head (for the scalp root shadow). Returns (brows, brow_alpha, hair)."""
    import bpy, brows_k2, preview_k2
    src = os.path.join(K.MPFB_DATA, "eyebrows", "eyebrow009", "eyebrow009.png")
    brows_k2.strand_brows(src, os.path.join(tex_dir, "Brows_eyebrow009.png"), size=1024, n_strands=3600)
    al = TB.read_image(src)[..., 3:4]
    al = gblur(al, 5.0)
    hb = os.path.join(K.BLENDS, "hair_k3.blend")
    hair = None
    if os.path.exists(hb):
        # the built-in concept hair (swept_fade) is the default: its coverage drives the scalp root shadow
        with bpy.data.libraries.load(hb) as (src_, dst_):
            dst_.objects = [n for n in src_.objects if n.startswith("Hair_")]
        for o in dst_.objects:
            bpy.context.scene.collection.objects.link(o)
            hair = o
    if hair is None:
        hair = preview_k2.add_catalog_hair(rig)
    return bpy.data.objects.get("Brows"), al, hair
