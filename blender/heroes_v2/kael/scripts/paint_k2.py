"""Kael v2 textures: high -> low bakes (GPU Cycles) and per-texel procedural painting for every material atlas.

Garments (Garment_Top / Garment_Pants) write the runtime-composite masks (R accent panel, G trim, B glow, A seam/AO
darkening) + baked normals; hard surface / boots / gloves / gear write BaseColor + Normal + MaskMap
(R metallic, G occlusion, B paint mask, A smoothness).
"""
import bpy, bmesh, os, math, time
import numpy as np
from mathutils import Vector
import kcommon as K
from kcommon import ss, nrm
import texbake as TB
import texstage as TS
import fabric as FB
import gear

TEXN = 0.0


# ============================================================================= bake


def _bake_setup(samples):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type == "METAL"
        sc.cycles.device = "GPU"
    except Exception:
        sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    if sc.world is None:
        sc.world = bpy.data.worlds.new("bake_world")


def garment_hp(lo, disp_fn, levels=2):
    """High-poly for a garment: Catmull-Clark copy displaced along its normals by disp_fn(P_rest, N) (metres)."""
    me = lo.data.copy()
    h = bpy.data.objects.new(lo.name + "_HPG", me)
    bpy.context.scene.collection.objects.link(h)
    h.matrix_world = lo.matrix_world.copy()
    if h.data.shape_keys:
        h.shape_key_clear()
    for m in list(h.modifiers):
        h.modifiers.remove(m)
    m = h.modifiers.new("sub", "SUBSURF"); m.levels = m.render_levels = levels
    gear.apply_modifiers(h)
    co = K.get_co(h)
    h.data.update()
    vn = np.empty(len(h.data.vertices) * 3, np.float32)
    h.data.vertices.foreach_get("normal", vn)
    vn = vn.reshape(-1, 3).astype(np.float64)
    d = np.asarray(disp_fn(co, vn), np.float64)
    K.set_co(h, co + vn * d[:, None])
    h["k_hp"] = True
    return [h]


def hard_hp(lo, levels=2):
    return TB._high_for(lo, levels)


def bake(lows, mat, size, hp_fn, cage=0.006, dist=0.014, ao_dist=0.05, ao_samples=48, hide=(), with_ao=True):
    """Tangent normal + AO of the faces using `mat` from high-polys made by hp_fn(lo) -> [objects]."""
    sc = bpy.context.scene
    _bake_setup(ao_samples)
    prev_dist = sc.world.light_settings.distance
    sc.world.light_settings.distance = ao_dist
    lows = [o for o in lows if TB._faces_with(o, mat) is not None]
    pairs, temps = [], []
    for lo in lows:
        hs = hp_fn(lo)
        temps += [h for h in hs if h.get("k_hp") or h.name.endswith("_HIB")]
        pairs.append((lo, hs))
    hidden = []
    for o in hide:
        if not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    img_n = bpy.data.images.new("bakeN_" + mat, size, size, alpha=False, float_buffer=True)
    img_n.colorspace_settings.name = "Non-Color"
    img_n.generated_color = (0.5, 0.5, 1.0, 1.0)
    img_a = bpy.data.images.new("bakeA_" + mat, size, size, alpha=False, float_buffer=True)
    img_a.colorspace_settings.name = "Non-Color"
    img_a.generated_color = (1.0, 1.0, 1.0, 1.0)
    dummy = bpy.data.images.new("bake_dummy", 8, 8, alpha=False)
    nodes = []
    mats = {m for lo in lows for m in lo.data.materials if m is not None}
    for m in mats:
        m.use_nodes = True
        nt = m.node_tree
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img_n if m.name == mat else dummy
        n.interpolation = "Closest"
        nt.nodes.active = n
        nodes.append((m, nt, n))

    def run(kind, samples):
        sc.cycles.samples = samples
        for lo, hs in pairs:
            bpy.ops.object.select_all(action="DESELECT")
            for h in hs:
                h.select_set(True)
            lo.select_set(True)
            bpy.context.view_layer.objects.active = lo
            kw = dict(type=kind, use_selected_to_active=True, cage_extrusion=cage, max_ray_distance=dist, margin=8, margin_type="EXTEND",
                      use_clear=False, target="IMAGE_TEXTURES")
            if kind == "NORMAL":
                kw.update(normal_space="TANGENT", normal_r="POS_X", normal_g="POS_Y", normal_b="POS_Z")
            bpy.ops.object.bake(**kw)
    t0 = time.time()
    run("NORMAL", 1)
    ao = None
    if with_ao:
        vis = {}
        for lo in lows:
            vis[lo.name] = (lo.visible_diffuse, lo.visible_glossy, lo.visible_shadow, lo.visible_transmission)
            lo.visible_diffuse = lo.visible_glossy = lo.visible_shadow = lo.visible_transmission = False
        for m, nt, n in nodes:
            if m.name == mat:
                n.image = img_a
        run("AO", ao_samples)
        for lo in lows:
            lo.visible_diffuse, lo.visible_glossy, lo.visible_shadow, lo.visible_transmission = vis[lo.name]
        a = np.empty(size * size * 4, np.float32)
        img_a.pixels.foreach_get(a)
        ao = a.reshape(size, size, 4)[..., 0].copy()
    a = np.empty(size * size * 4, np.float32)
    img_n.pixels.foreach_get(a)
    nmap = a.reshape(size, size, 4)[..., :3].copy()
    for m, nt, n in nodes:
        nt.nodes.remove(n)
    for im in (img_n, img_a, dummy):
        bpy.data.images.remove(im)
    for o in hidden:
        o.hide_render = False
    for o in temps:
        if o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.select_all(action="DESELECT")
    sc.world.light_settings.distance = prev_dist
    K.log("BAKE", mat, len(lows), "objects", size, round(time.time() - t0, 1), "s")
    return nmap, ao


# ============================================================================= fold fields (garment high-poly)


def limb(P, a, b):
    d = b - a
    L2 = d @ d
    t = (P - a) @ d / L2
    q = P - a - t[:, None] * d
    return t, np.linalg.norm(q, axis=1), q


def ring_folds(P, a, b, t0, t1, wl, amp, side=None, side_k=1.0, seed=0.0, warp=0.35, rmax=0.13):
    """Compression folds around a limb segment a->b between t0..t1 (sinusoidal rings, bent by noise, broken up,
    stronger on the `side` direction)."""
    t, r, q = limb(P, a, b)
    L = np.linalg.norm(b - a)
    s = t * L
    env = ss(t0 - 0.06, t0 + 0.02, t) * (1 - ss(t1 - 0.02, t1 + 0.06, t)) * (r < rmax)
    w = TB.fbm3(P, 28.0, 2, seed) * warp + TB.fbm3(P, 9.0, 1, seed + 2) * warp
    f = np.sin((s / wl + w) * 2 * math.pi)
    f = np.sign(f) * np.abs(f) ** 0.7
    br = ss(-0.35, 0.45, TB.fbm3(P, 16.0, 2, seed + 5))
    m = env * (0.35 + 0.65 * br)
    if side is not None:
        sd = nrm(side)
        c = (q @ sd) / np.maximum(r, 1e-6)
        m = m * (0.25 + 0.75 * np.clip(c * side_k * 0.5 + 0.5, 0, 1) ** 1.5)
    return amp * f * m


def top_disp(L):
    def fn(P, N):
        d = np.zeros(len(P))
        for s, S in ((1, "Left"), (-1, "Right")):
            sh, el, wr = L[S + "Arm"], L[S + "ForeArm"], L[S + "Hand"]
            side_m = np.sign(P[:, 0]) == s
            du = nrm(el - sh); df = nrm(wr - el)
            inner = df - du * (df @ du)
            # inner-elbow compression folds, wrist stacking above the glove, light upper-arm drag
            dd = ring_folds(P, sh, el, 0.62, 1.05, 0.024, 0.0032, side=inner, seed=1.0 + s)
            dd += ring_folds(P, el, wr, -0.05, 0.35, 0.022, 0.0028, side=inner, seed=3.0 + s)
            dd += ring_folds(P, el, wr, 0.62, 0.92, 0.016, 0.0024, seed=5.0 + s)
            dd += ring_folds(P, sh, el, 0.1, 0.5, 0.05, 0.0012, seed=7.0 + s)
            d += np.where(side_m, dd, 0)
        # waist gathers under the belt line and above the hem
        back = ss(-0.03, 0.05, P[:, 1])
        z = P[:, 2]
        wz = ss(1.0, 1.04, z) * (1 - ss(1.13, 1.2, z))
        d += 0.0022 * wz * np.sin((z / 0.018 + 0.6 * TB.fbm3(P, 12.0, 2, 11.0)) * 2 * math.pi) * (0.4 + 0.6 * ss(-0.2, 0.5, TB.fbm3(P, 14.0, 2, 12.0)))
        # armpit drag folds (diagonal)
        for s in (1, -1):
            c = np.array((s * 0.17, 0.0, 1.36))
            g = np.exp(-np.sum(((P - c) / np.array((0.07, 0.12, 0.08))) ** 2, 1))
            dd = 0.0018 * g * np.sin(((P[:, 2] - 1.36) * 0.8 + (np.abs(P[:, 0]) - 0.17) * 0.6) / 0.02 * 2 * math.pi)
            d += np.where(np.sign(P[:, 0]) == s, dd, 0)
        d += 0.00045 * TB.fbm3(P, 60.0, 3, 13.0)
        return d
    return fn


def pants_disp(L):
    def fn(P, N):
        d = np.zeros(len(P))
        for s, S in ((1, "Left"), (-1, "Right")):
            hp, kn, an = L[S + "UpLeg"], L[S + "Leg"], L[S + "Foot"]
            side_m = np.sign(P[:, 0]) == s
            back = np.array((0, 1.0, 0))
            dd = ring_folds(P, hp, kn, 0.8, 1.06, 0.028, 0.0032, side=back, seed=21 + s)          # back of the knee
            dd += ring_folds(P, kn, an, -0.05, 0.22, 0.03, 0.0026, side=back, seed=23 + s)
            dd += ring_folds(P, kn, an, 0.4, 0.62, 0.018, 0.003, seed=25 + s)                   # stacking above the boots
            dd += ring_folds(P, hp, kn, 0.05, 0.3, 0.045, 0.0015, side=np.array((0, -1, 0)), seed=27 + s)   # hip crease
            d += np.where(side_m, dd, 0)
        # crotch drag
        c = np.array((0.0, -0.02, 0.92))
        g = np.exp(-np.sum(((P - c) / np.array((0.09, 0.08, 0.09))) ** 2, 1))
        d += 0.0016 * g * np.sin((np.abs(P[:, 0]) * 1.2 + (0.92 - P[:, 2])) / 0.022 * 2 * math.pi)
        d += 0.0004 * TB.fbm3(P, 55.0, 3, 29.0)
        return d
    return fn


def soft_disp(seed, amp=0.0004):
    return lambda P, N: amp * TB.fbm3(P, 70.0, 3, seed)


# ============================================================================= atlas helpers


def _island_weight(grp, uv):
    """Plate undersides (gear.plate 'collapse' islands at u 2.2..2.6) and side walls (u >= 3, v >= 2) are rarely
    seen: give them less texture space."""
    if uv[:, 0].min() >= 2.15 and uv[:, 0].max() <= 2.65 and uv[:, 1].max() <= 0.42:
        return 0.3
    if uv[:, 0].min() >= 2.95 and uv[:, 1].min() >= 1.95:
        return 0.75
    return 1.0


def atlas(objs, mat, size, margin=0.004):
    objs = [o for o in objs if TB._faces_with(o, mat) is not None]
    TB.pack(objs, mat, margin=margin, island_weight=_island_weight)
    return objs


def norm_ao(ao, t, floor=0.45):
    """Bake AO normalised so open surfaces read 1 (dark AO multiplies the whole material in URP); keeps cavities."""
    if ao is None:
        return np.ones(len(t["idx"]))
    a = np.clip(ao.reshape(-1)[t["idx"]], 0, 1)
    hi = max(np.percentile(a, 92), 0.2)
    a = np.clip(a / hi, 0, 1)
    return floor + (1 - floor) * a


def raster(objs, mat, size, attrs=("bx", "by", "bz", "wear", "cavity", "lx", "ly", "plate", "pouch", "strap", "sole", "mz", "kplate", "cap")):
    T = TB.raster(objs, mat, size, attrs=attrs)
    t = TS.subset(T)
    return T, t


def write_garment(T, t, Ly, ao, nbake, base, tex_dir):
    ao_t = norm_ao(ao, t, 0.0)
    A = np.maximum(Ly.A, np.clip((1 - ao_t) * 0.8, 0, 1))
    mask = np.stack([Ly.R, Ly.G, Ly.B, np.clip(A, 0, 1)], 1)
    M = TS.finish(T, TS.full(T, t, mask))
    Nd = TS.to_normal(T, t, Ly.h)
    cov = T.cov.reshape(T.size, T.size)
    nb = TS.finish(T, TS.full(T, t, nbake.reshape(-1, 3)[t["idx"]])) if nbake is not None else np.full_like(Nd, 0.5)
    nb = np.where(cov[..., None], nb, np.array((0.5, 0.5, 1.0)))
    Nm = TB.whiteout(nb, Nd)
    TB.write_png(M, os.path.join(tex_dir, base + "_Mask.png"), "RGBA")
    TB.write_png(Nm, os.path.join(tex_dir, base + "_Normal.png"), "RGB")
    return M, Nm


def write_hard(T, t, rgb, h, metal, smooth, ao, nbake, base, tex_dir, paint=None):
    ao_t = norm_ao(ao, t, 0.35)
    C = TS.finish(T, TS.full(T, t, rgb))
    Nd = TS.to_normal(T, t, h)
    cov = T.cov.reshape(T.size, T.size)
    nb = TS.finish(T, TS.full(T, t, nbake.reshape(-1, 3)[t["idx"]])) if nbake is not None else np.full_like(Nd, 0.5)
    nb = np.where(cov[..., None], nb, np.array((0.5, 0.5, 1.0)))
    Nm = TB.whiteout(nb, Nd)
    paint = np.ones(len(h)) if paint is None else paint
    MM = TS.finish(T, TS.full(T, t, np.stack([metal, np.clip(ao_t, 0, 1), paint, smooth], 1)))
    TB.write_png(C, os.path.join(tex_dir, base + "_BaseColor.png"), "RGB")
    TB.write_png(Nm, os.path.join(tex_dir, base + "_Normal.png"), "RGB")
    TB.write_png(MM, os.path.join(tex_dir, base + "_MaskMap.png"), "RGBA")
    return [base + "_BaseColor.png", base + "_Normal.png", base + "_MaskMap.png"]


def curvature(T, t, nbake):
    if nbake is None:
        return np.zeros(len(t["idx"]))
    c = TB.curvature_from_normal(nbake, T.mpt.reshape(T.size, T.size))
    return c.reshape(-1)[t["idx"]]


# ============================================================================= helpers for painters


def edge_distance(T, t, objs, names=None):
    """Distance (m) from each texel to the nearest boundary edge of its own object (hems, cuffs, panel edges)."""
    out = np.full(len(t["idx"]), 1.0)
    for oi, o in enumerate(objs):
        sel = np.where(t["obj"] == oi)[0]
        if not len(sel):
            continue
        me = o.data
        ec = {}
        for p in me.polygons:
            vs = list(p.vertices)
            for i in range(len(vs)):
                a, b = vs[i], vs[(i + 1) % len(vs)]
                k = (min(a, b), max(a, b))
                ec[k] = ec.get(k, 0) + 1
        bv = sorted({v for k, c in ec.items() if c == 1 for v in k})
        if not bv:
            continue
        co = np.array([me.vertices[v].co[:] for v in bv])
        # densify boundary points along edges
        pts = [co]
        for (a, b), c in ec.items():
            if c == 1:
                pa, pb = np.array(me.vertices[a].co[:]), np.array(me.vertices[b].co[:])
                pts.append(np.array([pa + (pb - pa) * f for f in (0.25, 0.5, 0.75)]))
        bp = np.vstack(pts)
        from mathutils.kdtree import KDTree
        kd = KDTree(len(bp))
        for i, p in enumerate(bp):
            kd.insert(p, i)
        kd.balance()
        P = t["P"][sel]
        best = np.empty(len(sel))
        for i, p in enumerate(P):
            best[i] = kd.find(p)[2]
        out[sel] = best
    return out


def stitch_line(Ly, d, along, mask, dash=0.0034, width=0.0004, thread=0.25):
    line = np.exp(-(d / width) ** 2) * mask
    ph = (along / dash) % 1.0
    dm = ss(0.05, 0.15, ph) * (1 - ss(0.62, 0.72, ph))
    Ly.h += 0.00024 * line * dm
    Ly.h -= 0.00015 * line * (1 - dm)
    Ly.G = np.maximum(Ly.G, thread * line * dm)
    Ly.A = np.maximum(Ly.A, 0.14 * line * (1 - dm))


def hem(Ly, ed, P, mask, band=0.012, stitch=(0.004, 0.009)):
    """Bound hem along an opening: rolled edge, two stitch rows, slight darkening."""
    m = mask * (ed < band + 0.004)
    Ly.h += 0.0005 * (1 - ss(0.0, 0.003, ed)) * m - 0.0004 * np.exp(-((ed - band) / 0.0009) ** 2) * m
    along = P[:, 0] * 0.7 + P[:, 1] * 0.5 + P[:, 2] * 0.9
    for s in stitch:
        stitch_line(Ly, ed - s, along, m)
    Ly.A = np.maximum(Ly.A, 0.25 * (1 - ss(0.0, 0.0025, ed)) * m)


def panel(Ly, f, R_in=1.0, mask=1.0, seam_depth=0.0008, raise_=0.0005, stitch=True, along=None, P=None, R_val=None):
    """Panel defined by signed field f (>0 inside, metres): sets R inside, seam groove + topstitch on the boundary."""
    m = np.asarray(mask, np.float64) * np.ones_like(f)
    inside = ss(-0.0006, 0.0006, f) * m
    if R_val is not None:
        Ly.R = Ly.R * (1 - inside) + R_val * inside
    g = np.exp(-(f / 0.0011) ** 2) * m
    Ly.h -= seam_depth * g
    Ly.h += raise_ * ss(0.0, 0.004, f) * m
    Ly.A = np.maximum(Ly.A, 0.5 * g)
    if stitch and along is not None:
        stitch_line(Ly, f - 0.0035, along, m * (f > 0))
    return inside


# ============================================================================= Garment_Top (jacket, collar, vest)


def paint_top(T, t, objs, L, nbake):
    P, N = t["P"], t["N"]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    n = len(P)
    Ly = FB.Layer(n)
    names = [o.name for o in objs]
    oid = t["obj"]
    is_top = oid == names.index("Top") if "Top" in names else np.zeros(n, bool)
    is_col = oid == names.index("Collar") if "Collar" in names else np.zeros(n, bool)
    is_vest = oid == names.index("ChestRig") if "ChestRig" in names else np.zeros(n, bool)
    ed = edge_distance(T, t, objs)
    along = x * 0.6 + y * 0.4 + z * 0.8
    # ---- base fabric: ripstop nylon (jacket), heavier cordura (vest)
    FB.ripstop(Ly, P, N, is_top.astype(float), cell=0.0058, amp=0.00011)
    FB.ripstop(Ly, P, N, is_vest.astype(float), cell=0.0032, amp=0.00016)
    # ---- jacket panels
    arm = {}
    for s, S in ((1, "Left"), (-1, "Right")):
        sh, el, wr = L[S + "Arm"], L[S + "ForeArm"], L[S + "Hand"]
        tu, ru, qu = limb(P, sh, el)
        tf, rf, qf = limb(P, el, wr)
        side = np.sign(x) == s
        on_arm = side & (((tu > -0.05) & (ru < 0.1)) | ((tf > -0.1) & (rf < 0.09))) & (ax > 0.2)
        arm[s] = (tu, tf, ru, rf, on_arm, sh, el, wr, qu, qf)
    top_m = is_top.astype(float)
    # yoke (shoulders + upper back), secondary, quilted channels
    yoke_line = 1.475 - 0.035 * ss(-0.02, 0.06, y) - 0.04 * ss(0.12, 0.24, ax)
    f_yoke = z - yoke_line
    yk = panel(Ly, f_yoke, mask=top_m, along=along, R_val=1.0)
    FB.quilt(Ly, x, z + y * 0.5, yk * top_m, q=0.03, pad=0.0016)
    # reflective piping under the yoke seam
    pip = np.exp(-((f_yoke + 0.0035) / 0.0011) ** 2) * top_m * (ax < 0.24)
    Ly.G = np.maximum(Ly.G, 0.85 * pip)
    Ly.h += 0.0004 * pip
    # side panels: stretch rib knit under the arms (secondary)
    not_arm = 1.0 - np.clip(arm[1][4].astype(float) + arm[-1][4].astype(float), 0, 1)
    f_side = np.minimum.reduce([ax - 0.118 - 0.012 * ss(1.3, 1.0, z), 1.42 - z, 0.2 - ax])
    sd = panel(Ly, f_side, mask=top_m * (z > 0.99) * not_arm, along=along, R_val=1.0)
    FB.knit(Ly, P, N, sd * top_m, period=0.003, amp=0.00018, axis=2)
    # sleeves: elbow articulation patch (outer elbow, quilted), forearm cuff band
    for s in (1, -1):
        tu, tf, ru, rf, on_arm, sh, el, wr, qu, qf = arm[s]
        du = nrm(el - sh); df = nrm(wr - el)
        inner = nrm(df - du * (df @ du))
        outer_c = -(qu @ inner) / np.maximum(ru, 1e-6)
        elbow_d = np.linalg.norm(P - (el - inner * 0.03), axis=1)
        f_el = 0.055 - elbow_d
        em = panel(Ly, f_el, mask=top_m * on_arm, along=along, R_val=1.0)
        FB.quilt(Ly, tu * 0.3, qu @ nrm(np.cross(du, inner)), em, q=0.018, pad=0.0014)
        f_cuff = (tf - 0.78) * np.linalg.norm(wr - el)
        cm_ = panel(Ly, f_cuff, mask=top_m * on_arm * (rf < 0.09), along=along, R_val=1.0)
        FB.knit(Ly, P - el, N, cm_, period=0.0026, amp=0.0002, axis=2)
        # sleeve seam along the underside + utility tab with velcro on the left upper arm
        und = (qu @ (-inner)) if False else None
        if s > 0:
            c = sh + (el - sh) * 0.45
            outward = nrm(np.array((1.0, -0.1, 0.25)) - du * (np.array((1.0, -0.1, 0.25)) @ du))
            pc = c + outward * 0.05
            dpt = np.linalg.norm(P - pc, axis=1)
            vel = (dpt < 0.032) * top_m * on_arm
            FB.velcro(Ly, P, vel)
            Ly.R = np.maximum(Ly.R, vel)
            ring = np.exp(-((dpt - 0.032) / 0.0012) ** 2) * top_m * on_arm
            Ly.h += 0.0005 * ring
            stitch_line(Ly, dpt - 0.029, along * 3, top_m * on_arm * (dpt < 0.04))
    # front asymmetric zip (visible below the plate carrier) + storm flap seam
    zx = 0.042 - 0.03 * ss(1.55, 1.0, z)
    dz = x - zx
    front = top_m * (y < -0.04) * (z < 1.56)
    FB.zipper(Ly, dz, z, front * (np.abs(dz) < 0.01))
    stitch_line(Ly, dz - 0.012, z, front)
    # hem band (knit) and cuffs: hems everywhere
    f_hb = 1.03 - z
    hb = panel(Ly, f_hb, mask=top_m, along=along, R_val=1.0)
    FB.knit(Ly, P, N, hb, period=0.003, amp=0.00016, axis=0)
    hem(Ly, ed, P, top_m)
    # ---- collar: primary shell, secondary lining (inside), bound top edge, snap tab
    col_m = is_col.astype(float)
    radial = P[:, :2] - np.array((0.0, -0.006))
    radial /= np.maximum(np.linalg.norm(radial, axis=1, keepdims=True), 1e-6)
    inner_side = (radial * N[:, :2]).sum(1) < -0.2
    Ly.R = np.where(is_col, np.where(inner_side, 1.0, 0.0), Ly.R)
    FB.ripstop(Ly, P, N, col_m * (~inner_side), cell=0.0045, amp=0.00012)
    FB.knit(Ly, P, N, col_m * inner_side, period=0.0028, amp=0.00014, axis=0)
    hem(Ly, ed, P, col_m, band=0.008)
    zt = 1.6 + 0.04 * ss(-0.05, 0.06, y)
    stitch_line(Ly, z - (zt - 0.012), np.arctan2(x, -y) * 0.08, col_m * (~inner_side))
    snap_c = [np.array((sx, -0.085, 1.6)) for sx in (-0.018, 0.035)]
    for c in snap_c:
        dd = np.linalg.norm(P - c, axis=1)
        sn = (1 - ss(0.0035, 0.0045, dd)) * col_m
        Ly.G = np.maximum(Ly.G, 0.9 * sn)
        Ly.h += 0.0009 * sn - 0.0004 * np.exp(-((dd - 0.0045) / 0.0006) ** 2) * col_m
    # ---- vest: cordura in the accent colour, MOLLE webbing rows (primary), bound edges, shoulder pads
    vm = is_vest.astype(float)
    Ly.R = np.where(is_vest, 1.0, Ly.R)
    front_panel = vm * (y < -0.03) * (z > 1.22) * (z < 1.46) * (ax < 0.15)
    back_panel = vm * (y > 0.02) * (z > 1.21) * (z < 1.48) * (ax < 0.16)
    for pm, v0 in ((front_panel, 1.235), (back_panel, 1.225)):
        u = np.arctan2(x, -y if pm is front_panel else y) * 0.15
        rows = (z > v0) & (z < v0 + 0.038 * 4)
        before = Ly.h.copy()
        FB.molle(Ly, x, z - v0, pm * rows, row=0.038, band=0.025, tack=0.038, height=0.0018)
        band_on = (Ly.h - before) > 0.0009
        Ly.R = np.where(band_on & (pm * rows > 0), 0.0, Ly.R)
    # cummerbund: elastic sections with webbing
    cumm = vm * (ax > 0.13) * (z < 1.32)
    FB.knit(Ly, P, N, cumm, period=0.006, amp=0.0003, axis=2)
    # shoulder strap padding (quilted, primary)
    strap = vm * (z > 1.47)
    FB.quilt(Ly, x, y + z, strap, q=0.022, pad=0.0014)
    Ly.R = np.where(strap > 0, 0.0, Ly.R)
    # bound edges (binding tape in primary), velcro ID panel on the upper back
    bind = vm * (ed < 0.009)
    Ly.R = np.where(bind > 0, 0.0, Ly.R)
    hem(Ly, ed, P, vm, band=0.009, stitch=(0.006,))
    idp = vm * (y > 0.04) * (np.abs(x) < 0.07) * (np.abs(z - 1.44) < 0.03)
    FB.velcro(Ly, P, idp)
    # ---- folds AO hint from the baked normal curvature
    if nbake is not None:
        c = curvature(T, t, nbake)
        Ly.A = np.maximum(Ly.A, np.clip(-c * 0.35, 0, 0.35))
    return Ly


# ============================================================================= Garment_Pants


def paint_pants(T, t, objs, L, nbake):
    P, N = t["P"], t["N"]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    n = len(P)
    Ly = FB.Layer(n)
    ed = edge_distance(T, t, objs)
    along = x * 0.6 + y * 0.4 + z * 0.8
    FB.ripstop(Ly, P, N, 1.0, cell=0.0062, amp=0.0001)
    for s, S in ((1, "Left"), (-1, "Right")):
        hp, kn, an = L[S + "UpLeg"], L[S + "Leg"], L[S + "Foot"]
        side = (np.sign(x) == s).astype(float)
        # articulated knee panel (secondary, quilted) and outseam
        f_knee = np.minimum(0.075 - np.abs(z - kn[2] - 0.005), -y - 0.0)
        kp = panel(Ly, f_knee, mask=side * (y < 0.03), along=along, R_val=1.0)
        # articulation darts: horizontal pleats across the knee panel
        Ly.h += 0.0009 * np.sin((z - kn[2]) / 0.016 * 2 * math.pi) * kp * side
        # outseam (side seam) along the leg
        tl, rl, ql = limb(P, hp, an)
        lat = np.array((s * 1.0, 0, 0))
        phi = np.arctan2(ql @ np.array((0, -1.0, 0)), ql @ lat)
        dseam = phi * np.maximum(rl, 0.01)
        g = np.exp(-(dseam / 0.0012) ** 2) * side * (z < 1.0)
        Ly.h -= 0.0007 * g
        Ly.A = np.maximum(Ly.A, 0.45 * g)
        stitch_line(Ly, dseam - 0.004, z, side * (z < 1.0) * (np.abs(dseam) < 0.008))
        # cargo pocket on the left thigh (outer side): bellows pocket with flap
        if s > 0:
            pc_z = 0.78
            pu = dseam - 0.012
            pv = z - pc_z
            inside = (np.abs(pu) < 0.065) & (np.abs(pv) < 0.085) & (side > 0)
            fpk = np.minimum(0.065 - np.abs(pu), 0.085 - np.abs(pv))
            pk = panel(Ly, fpk, mask=side * (np.abs(pu) < 0.08) * (np.abs(pv) < 0.1), along=along * 2, raise_=0.0018, R_val=None)
            flap = (pv > 0.035) & inside
            fl = np.minimum(0.067 - np.abs(pu), np.minimum(pv - 0.032, 0.088 - pv))
            fm_ = panel(Ly, fl, mask=side * (np.abs(pu) < 0.08) * (pv > 0.025) * (pv < 0.095), along=along * 2, raise_=0.0012, R_val=1.0)
            Ly.A = np.maximum(Ly.A, 0.5 * np.exp(-((pv - 0.03) / 0.003) ** 2) * inside)
            for bx in (-0.035, 0.035):
                dd = np.hypot(pu - bx, pv - 0.045)
                Ly.G = np.maximum(Ly.G, 0.9 * (1 - ss(0.003, 0.004, dd)) * side)
                Ly.h += 0.0008 * (1 - ss(0.003, 0.004, dd)) * side
    # seat panel + crotch gusset (secondary)
    # yoke seam across the seat (no contrasting seat panel: it read as underwear)
    sy = 0.98 - 0.03 * ss(0.0, 0.12, ax)
    panel(Ly, (z - sy) * (y > 0.0), mask=(y > 0.0).astype(float) * (z > 0.9), along=along, R_val=None)
    hem(Ly, ed, P, 1.0, band=0.01)
    if nbake is not None:
        c = curvature(T, t, nbake)
        Ly.A = np.maximum(Ly.A, np.clip(-c * 0.35, 0, 0.35))
    return Ly


# ============================================================================= hard surface


def glyphs(lx, ly, x0, y0, w, h, seed=0, cells=6):
    """Invented glyph strip: random strokes on a small grid (no letters); returns 0..1 coverage."""
    rng = np.random.default_rng(seed)
    out = np.zeros(len(lx))
    cw = w / cells
    for c in range(cells):
        gx = x0 + c * cw
        for _ in range(rng.integers(2, 4)):
            a = (gx + rng.uniform(0.15, 0.85) * cw * 0.8, y0 + rng.uniform(0.1, 0.9) * h)
            b = (gx + rng.uniform(0.15, 0.85) * cw * 0.8, y0 + rng.uniform(0.1, 0.9) * h)
            d, _ = TB.line_sdf2(lx, ly, a[0], a[1], b[0], b[1])
            out = np.maximum(out, 1 - ss(h * 0.07, h * 0.11, d))
    return out


def chevrons(lx, ly, x0, y0, w, h, period=0.006):
    inside = (lx > x0) & (lx < x0 + w) & (ly > y0) & (ly < y0 + h)
    s = ((lx - x0) + np.abs(ly - (y0 + h / 2)) * 1.2) / period
    return inside * (np.sin(s * 2 * math.pi) > 0)


def carbon(P, N, scale=0.0021):
    """2x2 twill carbon weave: tone variation (0..1) and height."""
    w = np.abs(N) ** 4
    w /= w.sum(1, keepdims=True) + 1e-9
    tone = 0; hh = 0
    for ax_, (i, j) in enumerate(((1, 2), (0, 2), (0, 1))):
        u = P[:, i] / scale; v = P[:, j] / scale
        cu = np.floor(u); cv = np.floor(v)
        warp = ((cu + cv) % 4) < 2
        fu = u - cu; fv = v - cv
        tt = np.where(warp, 0.5 + 0.5 * np.cos(fv * math.pi * 2), 0.5 + 0.5 * np.cos(fu * math.pi * 2))
        tone = tone + w[:, ax_] * (0.35 + 0.65 * warp * 0.8 + 0.2 * tt)
        hh = hh + w[:, ax_] * (tt - 0.5)
    return tone, hh


def paint_armor(T, t, objs, nbake, ao):
    P, N = t["P"], t["N"]
    A = t["A"]
    n = len(P)
    mz = np.round(A.get("mz", np.zeros(n))).astype(int)
    wear = A.get("wear", np.zeros(n)); cav = A.get("cavity", np.zeros(n))
    lx, ly = A.get("lx", np.zeros(n)), A.get("ly", np.zeros(n))
    pid = A.get("plate", np.zeros(n))
    ao_t = norm_ao(ao, t, 0.0)
    curv = curvature(T, t, nbake)
    h = np.zeros(n)
    # --- base layers (linear-ish sRGB values; the material tint multiplies this)
    paint_col = np.array((0.62, 0.615, 0.6))
    var = TB.fbm3(P, 14.0, 3, 1.0) * 0.025 + TB.fbm3(P, 70.0, 2, 2.0) * 0.012
    rgb = paint_col[None] * (1 + var[:, None])
    metal = np.zeros(n); smooth = np.full(n, 0.5)
    paint_mask = np.ones(n)
    # zone 1: carbon fibre (clear coated)
    cz = (mz == 1)
    tone, ch = carbon(P, N)
    cf = np.array((0.11, 0.115, 0.12))[None] * (0.7 + 0.5 * tone[:, None])
    rgb = np.where(cz[:, None], cf, rgb)
    smooth = np.where(cz, 0.78, smooth)
    h += np.where(cz, ch * 0.00005, 0)
    paint_mask = np.where(cz, 0.0, paint_mask)
    # zone 2: machined metal bands / edges
    mzm = (mz == 2)
    brushed = 0.55 + 0.06 * TB.fbm3(P * np.array((1, 1, 8)), 200.0, 2, 4.0)
    rgb = np.where(mzm[:, None], np.array((0.62, 0.63, 0.65))[None] * brushed[:, None] / 0.55, rgb)
    metal = np.where(mzm, 1.0, metal); smooth = np.where(mzm, 0.66, smooth); paint_mask = np.where(mzm, 0.0, paint_mask)
    # zone 3: matte polymer liner
    lz = (mz == 3)
    rgb = np.where(lz[:, None], np.array((0.06, 0.062, 0.065))[None], rgb)
    smooth = np.where(lz, 0.3, smooth); paint_mask = np.where(lz, 0.0, paint_mask)
    # --- edge wear: paint chips to bare metal on convex edges (curvature + per-vertex wear), cavity grime
    chips = FB.edge_wear(np.clip(wear * 0.5 + np.clip(curv, 0, 1) * 0.9, 0, 1), P, 1.0, seed=5.0) * (mz == 0)
    rgb = rgb * (1 - chips[:, None]) + np.array((0.6, 0.6, 0.61))[None] * chips[:, None]
    metal = np.maximum(metal, chips); smooth = np.where(chips > 0.5, 0.62, smooth)
    h -= 0.00006 * chips
    edge_hl = np.clip(curv, 0, 1) * (mz == 0)
    rgb = rgb * (1 + 0.06 * edge_hl[:, None])
    g = FB.grime(P, ao_t, cav, seed=7.0)
    rgb = rgb * (1 - 0.32 * g[:, None] * np.array((1.0, 1.02, 1.05))[None])
    smooth = smooth - 0.12 * g
    # --- scratches and decals
    sc = FB.scratches(lx, ly, pid, density=70, seed=3.0)
    rgb = rgb * (1 - 0.12 * sc[:, None]) + 0.12 * sc[:, None] * 0.75
    smooth = smooth + 0.05 * sc
    dec = np.zeros(n)
    hz = np.zeros(n)
    for p_id, (gx, gy, gw, gh) in ((10, (-0.04, 0.03, 0.035, 0.008)), (11, (0.005, 0.03, 0.035, 0.008)), (20, (-0.05, 0.035, 0.05, 0.009)),
                                   (21, (-0.05, 0.035, 0.05, 0.009)), (40, (-0.025, -0.035, 0.05, 0.007)), (31, (-0.02, -0.02, 0.04, 0.007))):
        m = (np.round(pid) == p_id) & (mz == 0)
        dec = np.maximum(dec, glyphs(lx, ly, gx, gy, gw, gh, seed=p_id) * m)
    for p_id in (20, 21, 40):
        m = (np.round(pid) == p_id) & (mz == 0)
        hz = np.maximum(hz, chevrons(lx, ly, -0.05, -0.05, 0.03, 0.008) * m)
    rgb = rgb * (1 - 0.82 * dec[:, None]) + dec[:, None] * np.array((0.07, 0.07, 0.075))[None]
    rgb = rgb * (1 - hz[:, None]) + hz[:, None] * np.array((0.85, 0.55, 0.08))[None]
    smooth = np.where(dec + hz > 0.5, smooth - 0.05, smooth)
    # --- micro surface
    h += 0.00003 * TB.fbm3(P, 400.0, 2, 9.0) * (mz == 0)
    smooth = np.clip(smooth + 0.03 * TB.fbm3(P, 30.0, 2, 10.0), 0.2, 0.85)
    return np.clip(rgb, 0, 1), h, np.clip(metal, 0, 1), smooth, paint_mask


def paint_boots(T, t, objs, nbake, ao):
    P, N = t["P"], t["N"]
    A = t["A"]
    n = len(P)
    sole = A.get("sole", np.zeros(n)) > 0.5
    cap = A.get("cap", np.zeros(n)) > 0.5
    strap = A.get("strap", np.zeros(n)) > 0.5
    mz = np.round(A.get("mz", np.full(n, -1))).astype(int)
    plate = A.get("plate", np.zeros(n)) > 0.5
    ao_t = norm_ao(ao, t, 0.0)
    curv = curvature(T, t, nbake)
    h = np.zeros(n)
    # leather upper (dark oiled leather, slightly warm), pebble grain + flex creases at the toe and ankle
    leather = np.array((0.075, 0.068, 0.062))
    grain = TB.worley3(P, 1 / 0.0016, 2.0)
    rgb = leather[None] * (1 + 0.18 * TB.fbm3(P, 9.0, 3, 1.0)[:, None] + 0.1 * (grain[:, None] - 0.5))
    h += -0.00008 * ss(0.0, 0.5, grain)
    smooth = 0.42 - 0.08 * grain
    metal = np.zeros(n)
    crease = (np.abs(np.sin((P[:, 1] * 0.8 + P[:, 2]) / 0.006 * math.pi)) < 0.12) * ss(0.12, 0.06, P[:, 2]) * (P[:, 1] < -0.06)
    h -= 0.00025 * crease
    rgb = rgb * (1 - 0.15 * crease[:, None])
    # synthetic panels (cordura) on the shaft sides
    shaft = (P[:, 2] > 0.13) & ~sole & ~cap & ~strap & ~plate
    FBL = FB.Layer(n)
    FB.ripstop(FBL, P, N, shaft.astype(float), cell=0.0035, amp=0.00012)
    h += FBL.h
    rgb = np.where(shaft[:, None], np.array((0.055, 0.058, 0.056))[None] * (1 + 0.1 * TB.fbm3(P, 20.0, 2, 3.0)[:, None]), rgb)
    smooth = np.where(shaft, 0.3, smooth)
    # moulded polymer caps and shin plate: graphite with machined edges
    pol = cap | plate
    rgb = np.where(pol[:, None], np.array((0.13, 0.135, 0.14))[None] * (1 + 0.05 * TB.fbm3(P, 30.0, 2, 4.0)[:, None]), rgb)
    smooth = np.where(pol, 0.5, smooth)
    edge = np.clip(curv, 0, 1) * pol
    rgb = rgb + edge[:, None] * 0.12
    me2 = (mz == 2) & plate
    rgb = np.where(me2[:, None], np.array((0.5, 0.5, 0.52))[None], rgb); metal = np.where(me2, 1.0, metal); smooth = np.where(me2, 0.6, smooth)
    # webbing straps
    web = strap
    wv = 0.5 + 0.5 * np.sin(P[:, 0] / 0.0009 * math.pi) * np.sin(P[:, 2] / 0.0012 * math.pi)
    rgb = np.where(web[:, None], np.array((0.05, 0.05, 0.048))[None] * (0.85 + 0.3 * wv[:, None]), rgb)
    h += np.where(web, 0.00008 * wv, 0); smooth = np.where(web, 0.25, smooth)
    # rubber sole: lugs + siping, dusty
    zt = P[:, 2]
    lug = (np.sin(P[:, 0] / 0.006 * math.pi) * np.sin(P[:, 1] / 0.008 * math.pi) > 0.2) & sole & (zt < 0.008)
    side_lug = sole & (zt < 0.022) & (np.sin(np.arctan2(P[:, 1] + 0.05, P[:, 0] - np.sign(P[:, 0]) * 0.2) * 40) > 0.3)
    rgb = np.where(sole[:, None], np.array((0.045, 0.045, 0.047))[None], rgb)
    h += np.where(lug | side_lug, 0.0012, 0) + np.where(sole, 0.00005 * TB.fbm3(P, 300.0, 2, 6.0), 0)
    smooth = np.where(sole, 0.22, smooth)
    sole_band = sole & (zt > 0.024) & (zt < 0.03)
    rgb = np.where(sole_band[:, None], np.array((0.12, 0.12, 0.12))[None], rgb)
    # dust and scuffs low on the boot, AO
    dust = ss(0.07, 0.0, zt) * (0.5 + 0.5 * TB.fbm3(P, 40.0, 3, 8.0))
    rgb = rgb * (1 - 0.4 * dust[:, None] * 0) + dust[:, None] * np.array((0.09, 0.085, 0.075))[None] * 0.5
    smooth = smooth - 0.15 * dust
    rgb = rgb * (0.65 + 0.35 * ao_t[:, None])
    return np.clip(rgb, 0, 1), h, metal, np.clip(smooth, 0.1, 0.8), np.zeros(n)


def paint_gloves(T, t, objs, nbake, ao, L):
    """Tinted at runtime by outfit*0.75: base colours are near-neutral values."""
    P, N = t["P"], t["N"]
    A = t["A"]
    n = len(P)
    kp = A.get("kplate", np.zeros(n)) > 0.5
    mz = np.round(A.get("mz", np.zeros(n))).astype(int)
    ao_t = norm_ao(ao, t, 0.0)
    curv = curvature(T, t, nbake)
    h = np.zeros(n)
    rgb = np.full((n, 3), 0.62)
    smooth = np.full(n, 0.35)
    metal = np.zeros(n)
    for s, S in ((1, "Left"), (-1, "Right")):
        wr, dors, fdir, mcp = gear.hand_frame(L, s)
        side = np.sign(P[:, 0]) == s
        dn = N @ dors
        palm = side & (dn < -0.2) & ~kp
        # palm: synthetic leather with grip texture (darker)
        grip = TB.worley3(P, 1 / 0.0012, 3.0 + s)
        rgb = np.where(palm[:, None], (0.32 + 0.06 * grip)[:, None] * np.ones(3), rgb)
        h += np.where(palm, -0.00006 * ss(0.0, 0.5, grip), 0)
        smooth = np.where(palm, 0.45, smooth)
        # back: stretch knit
        back = side & (dn >= -0.2) & ~kp
        h += np.where(back, 0.00008 * np.sin((P @ fdir) / 0.0012 * math.pi), 0)
        # finger tips leather caps
        along = (P - wr) @ fdir
        tips = side & (along > 0.135) & ~kp
        rgb = np.where(tips[:, None], 0.36, rgb)
        smooth = np.where(tips, 0.45, smooth)
        # knuckle joints accordion ribs on the back of the fingers
        rib = back & (along > 0.06) & (along < 0.12)
        h += np.where(rib, 0.00014 * np.sin(along / 0.0016 * math.pi), 0)
    # plates: carbon + metal edge
    tone, ch = carbon(P, N, 0.0014)
    rgb = np.where(kp[:, None], (0.18 + 0.12 * tone)[:, None] * np.ones(3), rgb)
    smooth = np.where(kp, 0.72, smooth)
    edge = kp & ((mz == 2) | (np.clip(curv, 0, 1) > 0.35))
    rgb = np.where(edge[:, None], 0.75, rgb); metal = np.where(edge, 1.0, metal); smooth = np.where(edge, 0.6, smooth)
    rgb = rgb * (0.7 + 0.3 * ao_t[:, None])
    return np.clip(rgb, 0, 1), h, metal, np.clip(smooth, 0.1, 0.85), np.ones(n)


def paint_gear(T, t, objs, nbake, ao):
    """Cloth_Gear: belt webbing, pouches (ranger green cordura), straps; fixed colours (not tinted)."""
    P, N = t["P"], t["N"]
    A = t["A"]
    n = len(P)
    pouch = np.round(A.get("pouch", np.zeros(n))).astype(int)
    strap = A.get("strap", np.zeros(n)) > 0.5
    ao_t = norm_ao(ao, t, 0.0)
    curv = curvature(T, t, nbake)
    h = np.zeros(n)
    green = np.array((0.105, 0.115, 0.085))
    rgb = np.tile(np.array((0.045, 0.046, 0.044)), (n, 1))     # black webbing default (belt band, straps)
    smooth = np.full(n, 0.28)
    wv = np.sin(P[:, 0] / 0.0008 * math.pi) * np.sin(P[:, 2] / 0.0011 * math.pi)
    h += 0.0001 * wv
    pz = pouch > 0
    Ly = FB.Layer(n)
    FB.ripstop(Ly, P, N, pz.astype(float), cell=0.003, amp=0.00014)
    h = np.where(pz, Ly.h, h)
    rgb = np.where(pz[:, None], green[None] * (1 + 0.12 * TB.fbm3(P, 12.0, 3, 2.0)[:, None]), rgb)
    flap = pouch == 2
    rgb = np.where(flap[:, None], green[None] * 0.85, rgb)
    # edge binding and stitching on pouches: convex edges darker (binding tape), worn lighter fibres on the very edge
    edge = np.clip(curv, 0, 1)
    rgb = rgb * (1 + 0.25 * edge[:, None] * pz[:, None])
    rgb = rgb * (0.62 + 0.38 * ao_t[:, None])
    metal = np.zeros(n)
    return np.clip(rgb, 0, 1), h, metal, smooth, np.zeros(n)
