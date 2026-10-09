"""Stage 5: armoured boots and fingerless tech gloves (+ high-poly bake sources).

  blender -b out/giva_gear.blend --python s5_boots_gloves.py [-- --nohigh]

Boots: lofted from the body's foot/calf: for each direction around a moving centre (foot -> ankle -> shin axis)
the outer hull of horizontal body sections gives a profile curve (r, z), resampled by arc length so the toe box,
heel and shaft get even quads; thickness varies (toe box, heel counter), separate tread sole, padded top collar,
shin guard, toe cap, heel plate, two buckle straps. Weights from the body (smoothed: boots are stiff).
Gloves: the body's hand topology offset 1.6 mm, fingers cut at the middle of the proximal phalanx with rolled
rims, wrist cuff band, knuckle armour plate (rigid to the hand). The body under the boots is removed.
Saves out/giva_bg.blend.
"""
import bpy, bmesh, sys, os, math, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import gv, hs, garment
for m in (gv, hs, garment):
    importlib.reload(m)
P = gv.P

A = gv.args()
rig = bpy.data.objects[gv.RIG]
body = bpy.data.objects["Body"]
F = garment.Frames(rig)
XB = gv.basis_co(body)
TB = gv.tri_index(body.data)
# hull reference: the body below the pants hem + the pants themselves (the body is stripped under the suit)
_PA = bpy.data.objects["Pants"]
_XP = gv.basis_co(_PA)
_TP = gv.tri_index(_PA.data)
BTREE = BVHTree.FromPolygons([Vector(c) for c in np.concatenate([XB, _XP])],
                             np.concatenate([TB, _TP + len(XB)]).tolist(), all_triangles=True)
HIGH = bpy.data.collections.get("HIGH") or bpy.data.collections.new("HIGH")
if HIGH.name not in bpy.context.scene.collection.children:
    bpy.context.scene.collection.children.link(HIGH)

Z_SOLE = 0.02        # top of the sole / bottom of the upper
Z_TOP = 0.435        # boot top (just under the knee; the knee cap above it rides the shin)


def hull_r(c, d, maxd=0.16, sx=1):
    """Farthest intersection of the ray c + t d with this leg's surface (outer hull distance), or None."""
    o = Vector(c)
    dv = Vector(d)
    far = None
    t0 = 0.0
    for _ in range(12):
        loc, nrm, fi, dist = BTREE.ray_cast(o + dv * (t0 + 1e-4), dv, maxd - t0)
        if loc is None:
            break
        t0 = t0 + 1e-4 + dist
        if loc.x * sx > 0.04:        # same leg only (never bridge to the other leg)
            far = t0
    return far


def boot(side, hi):
    sx = 1 if side == "Left" else -1
    leg_h, leg_t = F.h[side + "Leg"], F.t[side + "Leg"]
    foot_h, toe_h, toe_t = F.h[side + "Foot"], F.h[side + "ToeBase"], F.t[side + "ToeBase"]
    # centre path: mid-foot at the sole -> ankle -> shin axis
    foot_c = np.array((foot_h[0] * 0.5 + toe_h[0] * 0.5, (foot_h[1] + toe_h[1]) * 0.5 - 0.005, 0.0))
    ank_c = np.array((foot_h[0], foot_h[1] + 0.004, 0.0))

    def centre(z):
        if z <= 0.1:
            t = gv.ss(0.03, 0.1, z)
            c = foot_c * (1 - t) + ank_c * t
        else:
            u = (z - leg_t[2]) / (leg_h[2] - leg_t[2])
            c = leg_t + (leg_h - leg_t) * u
            t = gv.ss(0.1, 0.16, z)
            c = ank_c * (1 - t) + np.array((c[0], c[1], 0)) * t
        return np.array((c[0], c[1], z))
    M = 64 if hi else 32
    Zs = np.arange(Z_SOLE, Z_TOP + 1e-6, 0.003)
    th = np.linspace(0, 2 * math.pi, M, endpoint=False)
    dirs = np.stack([np.sin(th) * sx * 0 + np.sin(th), -np.cos(th), np.zeros(M)], 1)     # th=0 -> front (-Y)
    R = np.full((M, len(Zs)), np.nan)
    for k, z in enumerate(Zs):
        for i, d in enumerate(dirs):
            # toe box taller than the toes: front directions sample the foot lower down
            fr = max(0.0, math.cos(th[i])) ** 2 * (1 - gv.ss(0.075, 0.12, z))
            zq = Z_SOLE + (z - Z_SOLE) / (1 + 0.55 * fr)
            c = centre(zq)
            c[2] = zq
            r = hull_r(c, d, 0.16 if zq < 0.06 else 0.11, sx)
            if r is not None:
                cz = centre(z)
                # express the hit relative to the centre at the boot height
                R[i, k] = r + (c[:2] - cz[:2]) @ d[:2]
    # fill gaps (directions with no body hit) from neighbours, then thickness
    for k in range(len(Zs)):
        col = R[:, k]
        ok = ~np.isnan(col)
        if ok.sum() < 3:
            R[:, k] = R[:, k - 1] if k else 0.05
            continue
        idx = np.arange(M)
        R[:, k] = np.interp(idx, np.concatenate([idx[ok] - M, idx[ok], idx[ok] + M]), np.concatenate([col[ok]] * 3))
    # rounded toe box: a quarter-ellipsoid dome over the toes (taller and fuller than the bare toes)
    # ground outline of this foot (all foot vertices below 4 cm), per direction from the low centre
    c0 = centre(Z_SOLE)
    fv = XB[(XB[:, 2] < 0.04) & (XB[:, 0] * sx > 0.04)]
    rel = fv[:, :2] - c0[:2]
    ang = np.arctan2(rel[:, 0], -rel[:, 1])
    rad = np.linalg.norm(rel, axis=1)
    reach = np.zeros(M)
    for i in range(M):
        da = np.abs((ang - th[i] + math.pi) % (2 * math.pi) - math.pi)
        sel = da < (2 * math.pi / M) * 1.5
        reach[i] = (rad[sel] * np.cos(da[sel])).max() if sel.any() else 0.0
    reach = np.maximum(reach, np.nan_to_num(R[:, 0])) + 0.007
    H = 0.054
    for k, z in enumerate(Zs):
        t = np.clip((z - Z_SOLE) / H, 0, 1)
        dome = reach * (1 - t ** 2.6) ** (1 / 2.6)
        fr = np.clip(np.cos(th), 0, 1) ** 1.2
        R[:, k] = np.maximum(R[:, k], fr * dome + (1 - fr) * R[:, k])
    front = np.clip(np.cos(th), 0, 1)[:, None]          # toe direction
    back = np.clip(-np.cos(th), 0, 1)[:, None]
    zz = Zs[None, :]
    thick = 0.0058 + 0.006 * front ** 2 * (1 - gv.ss(0.05, 0.1, zz)) + 0.0035 * back ** 2 * (1 - gv.ss(0.08, 0.14, zz)) \
        + 0.002 * gv.ss(0.34, 0.43, zz)
    Rb = R + thick
    # smooth around and up (boots are smooth, convex-ish shapes)
    for _ in range(4):
        Rb = 0.5 * Rb + 0.25 * (np.roll(Rb, 1, 0) + np.roll(Rb, -1, 0))
    for _ in range(6):
        Rb[:, 1:-1] = 0.5 * Rb[:, 1:-1] + 0.25 * (Rb[:, :-2] + Rb[:, 2:])
    # profile curves per direction, resampled by arc length
    N = 46 if hi else 24
    curves = np.zeros((M, N, 3))
    for i, d in enumerate(dirs):
        pts = np.array([centre(z) + d * Rb[i, k] for k, z in enumerate(Zs)])
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        s = np.concatenate([[0], np.cumsum(seg)])
        # denser near the sole (toe box / heel shapes)
        u = s[-1] * (np.linspace(0, 1, N) ** 1.35)
        cur = np.stack([np.interp(u, s, pts[:, j]) for j in range(3)], 1)
        for _ in range(2):
            cur[1:-1] = 0.5 * cur[1:-1] + 0.25 * (cur[:-2] + cur[2:])
        curves[i] = cur
    p = hs.Part("Boots")
    V = curves.reshape(-1, 3)
    Fq = []
    for i in range(M):
        i2 = (i + 1) % M
        for j in range(N - 1):
            Fq.append((i * N + j, i2 * N + j, i2 * N + j + 1, i * N + j + 1))
    zrel = V[:, 2]
    p.add(V, Fq, "Boots", None, 10.0, {"bz": zrel})
    # padded top collar: roll the top ring inward and down
    top = curves[:, -1]
    ctr = centre(Z_TOP)
    prof = [(0.0, 0.0), (0.002, 0.004), (0.0, 0.007), (-0.004, 0.008), (-0.008, 0.005), (-0.009, -0.004), (-0.007, -0.012)]
    rows = []
    for (dr, dz) in prof:
        rows.append(np.array([q + gv.nrm(np.array((q[0] - ctr[0], q[1] - ctr[1], 0))) * dr + np.array((0, 0, dz)) for q in top]))
    Vc = np.concatenate(rows)
    Fc = []
    for j in range(len(prof) - 1):
        for i in range(M):
            i2 = (i + 1) % M
            Fc.append((j * M + i, j * M + i2, (j + 1) * M + i2, (j + 1) * M + i))
    p.add(Vc, Fc, "Boots", None, 11.0)
    # sole: welted outline from the bottom ring, flat bottom with toe spring, tread in the high-poly
    bot = curves[:, 0]
    cb = bot.mean(0)
    out = np.array([q + gv.nrm(np.array((q[0] - cb[0], q[1] - cb[1], 0))) * 0.0045 for q in bot])
    yfront = out[:, 1].min()
    spring = lambda y: 0.007 * gv.ss(yfront + 0.045, yfront, y)
    heel = lambda y: 0.004 * gv.ss(cb[1] + 0.04, cb[1] + 0.09, y)
    ring_top = np.array([(q[0], q[1], Z_SOLE + 0.004 + spring(q[1]) * 0.5) for q in out])
    ring_mid = np.array([(q[0], q[1], 0.006 + spring(q[1]) + heel(q[1])) for q in out])
    ins = np.array([q - gv.nrm(np.array((q[0] - cb[0], q[1] - cb[1], 0))) * 0.002 for q in out])
    ring_bot = np.array([(q[0], q[1], -0.002 + spring(q[1]) + heel(q[1]) * 0.0) for q in ins])
    Vs = np.concatenate([ring_top, ring_mid, ring_bot])
    Fs = []
    for j in range(2):
        for i in range(M):
            i2 = (i + 1) % M
            Fs.append((j * M + i, j * M + i2, (j + 1) * M + i2, (j + 1) * M + i))
    # bottom cap (fan to the centre)
    Vs = np.concatenate([Vs, [[cb[0], cb[1], -0.002]]])
    ci = len(Vs) - 1
    for i in range(M):
        i2 = (i + 1) % M
        Fs.append((2 * M + i2, 2 * M + i, ci))
    # top cap under the upper (closes the sole)
    p.add(Vs, Fs, "Boots", None, 12.0)
    # ---------------------------------------------------------------- hard parts (Boots material classes)
    tm = _tmp_mesh(V, Fq)
    ref = hs.Ref.from_arrays(V, gv.tri_index(tm))
    bpy.data.meshes.remove(tm)
    up = np.array((0, 0, 1.0))
    # shin guard: front of the shaft (cylindrical chart around the shin axis)
    cyl = hs.CylChart(ref, centre(0.12), centre(0.43), np.array((0.0, -1.0, 0.0)), r0=0.05)
    shin = hs.rounded_poly([(-0.03, 0.03), (0.03, 0.03), (0.037, 0.25), (0.0, 0.285), (-0.037, 0.25)], [0.01, 0.01, 0.014, 0.008, 0.014])

    def sh_h(u, v):
        h = -0.0013 * (abs(u) < 0.0052) * (0.05 < v < 0.25)            # channel for the glow strip
        if not hi:
            return h
        for vv in (0.09, 0.17):
            h -= 0.0007 * math.exp(-((v - vv) / 0.0007) ** 2) * (abs(u) < 0.027)
        return h
    hs.plate(p, cyl, shin, gap=0.0022, thick=0.0042, crown=0.0028, fillet=0.0016, hi=hi, mat="Boots", height_fn=sh_h, cls=10.0,
             ring_space=None if hi else 0.032)
    # side panels (violet anodised) flanking the shin guard
    for sg in (1, -1):
        sp = hs.rounded_poly([(sg * 0.044, 0.06), (sg * 0.064, 0.07), (sg * 0.066, 0.22), (sg * 0.046, 0.24)], [0.006, 0.006, 0.008, 0.008])
        hs.plate(p, cyl, sp, gap=0.0016, thick=0.0028, crown=0.0015, fillet=0.0012, hi=hi, mat="Boots", cls=13.0,
                 ring_space=None if hi else 0.04)
    # magenta glow: strip down the shin channel + a band under the collar (front half)
    pts = []
    for v in np.linspace(0.055, 0.245, 40 if hi else 12):
        q, nq = cyl.at(0.0, v)
        pts.append(q + nq * (0.0022 + 0.0042 + 0.0028 - 0.0011 + 0.0008))
    hs.tube(p, np.array(pts), 0.003, "Glow", 4.0, hi)
    ctr_b = centre(Z_TOP - 0.03)
    band = []
    for k in range(-(20 if hi else 9), (20 if hi else 9) + 1):
        a = k / (20 if hi else 9) * 1.35
        d = np.array((math.sin(a), -math.cos(a), 0))
        hit, n = ref.cast(ctr_b, d, 0.3)
        if hit is not None:
            band.append(hit + n * 0.0016)
    hs.tube(p, np.array(band), 0.0028, "Glow", 4.0, hi)
    # heel counter plate
    hc = centre(0.06)
    ch3 = hs.Chart(ref, hc + np.array((0, 0.06, 0)), np.array((0.0, 1.0, 0.05)), up)
    heelp = hs.rounded_poly([(-0.035, -0.035), (0.035, -0.035), (0.03, 0.045), (-0.03, 0.045)], [0.008, 0.008, 0.016, 0.016])
    hs.plate(p, ch3, heelp, gap=0.001, thick=0.0028, crown=0.002, fillet=0.0012, hi=hi, mat="Boots", cls=13.0,
             ring_space=None if hi else 0.03)
    q, nq = ch3.at(0.0, 0.0)
    hs.rbox(p, q + nq * 0.0055, nq, up, (0.006, 0.04, 0.0014), 0.0006, "Glow", 4.0, hi)
    # toe cap (anodised) with a short glow slit
    tc = centre(0.03)
    ch4 = hs.Chart(ref, tc + np.array((0, -0.12, 0.01)), np.array((0.0, -1.0, 0.35)), up)
    toe = hs.rounded_poly([(-0.032, -0.012), (0.032, -0.012), (0.026, 0.03), (-0.026, 0.03)], [0.01, 0.01, 0.014, 0.014])
    hs.plate(p, ch4, toe, gap=0.0012, thick=0.0026, crown=0.002, fillet=0.0012, hi=hi, mat="Boots", cls=13.0)
    # buckle straps around the ankle and the upper shaft
    for z, w in ((0.115, 0.022), (0.335, 0.02)):
        c = centre(z)
        pts, nor = [], []
        for k in range(M):
            a = th[k]
            d = np.array((math.sin(a), -math.cos(a), 0))
            hit, n = ref.cast(c, d, 0.3)
            if hit is None:
                hit, n = ref.nearest(c + d * 0.06)
            pts.append(hit + n * 0.0025)
            nor.append(n)
        hs.strap(p, np.array(pts), np.array(nor), w, 0.0028, "Boots", 14.0, hi, closed=True)
        a = math.pi / 2 if side == "Left" else -math.pi / 2
        d = np.array((math.sin(a), -math.cos(a), 0))
        hit, n = ref.cast(c, d, 0.3)
        if hit is not None:
            hs.rbox(p, hit + n * 0.0068, n, up, (0.026, w + 0.006, 0.004), 0.0012, "Boots", 15.0, hi)
    # ---------------------------------------------------------------- knee cap (rides the shin, above the boot)
    pants = bpy.data.objects["Pants"]
    kref = hs.Ref([pants])
    kc = leg_h + np.array((0.0, -0.02, -0.01))
    kch = hs.Chart(kref, kc, np.array((0.0, -1.0, 0.08)), up)
    cap = hs.rounded_poly([(-0.043, -0.06), (0.043, -0.06), (0.05, 0.02), (0.022, 0.062), (-0.022, 0.062), (-0.05, 0.02)],
                          [0.012, 0.012, 0.02, 0.014, 0.014, 0.02])

    def k_h(u, v):
        h = 0.0
        if hi:
            h -= 0.0007 * math.exp(-((abs(u) - 0.03) / 0.0007) ** 2) * (v < 0.03)
            h += 0.0012 * math.exp(-(u / 0.006) ** 2) * (v > -0.04)
        return h
    i0 = len(p.V)
    hs.plate(p, kch, cap, gap=0.0065, thick=0.0055, crown=0.009, fillet=0.002, hi=hi, mat="Boots", height_fn=k_h, cls=10.0,
             ring_space=None if hi else 0.024)
    inner = hs.rounded_poly([(-0.03, -0.045), (0.03, -0.045), (0.034, 0.012), (0.0, 0.04), (-0.034, 0.012)], [0.008, 0.008, 0.012, 0.01, 0.012])
    hs.plate(p, kch, inner, gap=0.0065 + 0.0055 + 0.006, thick=0.0022, crown=0.004, fillet=0.001, hi=hi, mat="Boots", cls=13.0, lip=False)
    gl = []
    for k in range(17 if hi else 9):
        a = math.radians(200 + k * 140 / (16 if hi else 8))
        q, nq = kch.at(math.cos(a) * 0.036, -0.004 + math.sin(a) * 0.036 + 0.0)
        gl.append(q + nq * (0.0065 + 0.0055 + 0.0085))
    hs.tube(p, np.array(gl), 0.0026, "Glow", 4.0, hi)
    kl = p.attr.setdefault("knee", [0.0] * i0)
    kl.extend([0.0] * (len(p.V) - len(kl)))
    for i in range(i0, len(p.V)):
        kl[i] = 1.0
    return p
    return p


def _tmp_mesh(V, Fq):
    me = bpy.data.meshes.new("__tmp")
    me.from_pydata([tuple(v) for v in V], [], Fq)
    return me


def boot_weights(o):
    """Body weights near the foot/shin, smoothed over the boot (stiff leather), max 4."""
    names, W = gv.bone_weights(body)
    keep = [j for j, n in enumerate(names) if any(k in n for k in ("Leg", "Foot", "Toe"))]
    names = [names[j] for j in keep]
    W = W[:, keep]
    co = gv.basis_co(o)
    b = gv.Binding(XB, TB, co, 0.3)
    Wo = b.transfer(W)
    off, idx = gv.neighbours(o.data)
    Wo = gv.smooth(Wo, off, idx, 12, 0.5)
    # knee caps: rigid, 75 % shin / 25 % thigh (a shin-hinged knee guard)
    if "knee" in o.data.attributes:
        kn = np.zeros(len(co))
        o.data.attributes["knee"].data.foreach_get("value", kn)
        for side, sx in (("Left", 1), ("Right", -1)):
            sel = (kn > 0.5) & (np.sign(co[:, 0]) == sx)
            if not sel.any():
                continue
            row = np.zeros(len(names))
            for b_, w_ in ((side + "Leg", 0.75), (side + "UpLeg", 0.25)):
                if P + b_ not in names:
                    names.append(P + b_)
                    Wo = np.concatenate([Wo, np.zeros((len(Wo), 1))], 1)
                    row = np.concatenate([row, [0.0]])
                row[names.index(P + b_)] = w_
            Wo[sel] = row
    gv.write_weights(o, names, gv.limit_normalize(Wo, 4, 0.02))


# ============================================================================= gloves

def gloves(hi):
    """Gloves from the body's hand faces (exact topology -> exact weights), cut at mid proximal phalanx."""
    names, W = gv.bone_weights(body)
    hand = np.zeros(len(XB))
    for j, n in enumerate(names):
        s = n[len(P):]
        if "Hand" in s:
            hand += W[:, j]
    fa_t = {sd: F.t[sd + "ForeArm"] for sd in ("Left", "Right")}
    polys = body.data.polygons
    keep = np.zeros(len(polys), bool)
    for f in polys:
        vs = list(f.vertices)
        c = np.array(f.center)
        sd = "Left" if c[0] > 0 else "Right"
        a, b = F.h[sd + "ForeArm"], F.t[sd + "ForeArm"]
        t = ((c - a) @ (b - a)) / ((b - a) @ (b - a))
        keep[f.index] = hand[vs].mean() > 0.5 or (t > 0.84 and np.linalg.norm(c - b) < 0.09)
    o = garment.extract(body, keep, "Gloves", drop_shapes=("corr_", "x_"))
    # finger cuts: plane perpendicular to each proximal phalanx (thumb: middle phalanx base)
    for sd in ("Left", "Right"):
        for fing, frac in (("Index1", 0.62), ("Middle1", 0.6), ("Ring1", 0.6), ("Pinky1", 0.6), ("Thumb2", 0.55)):
            a, b = F.h[sd + "Hand" + fing], F.t[sd + "Hand" + fing]
            c = a + (b - a) * frac
            d = gv.nrm(b - a)
            _cut_beyond(o, c, d, 0.03)
    # wrist cuff end
    for sd in ("Left", "Right"):
        a, b = F.h[sd + "ForeArm"], F.t[sd + "ForeArm"]
        c = a + (b - a) * 0.86
        _cut_beyond(o, c, -gv.nrm(b - a), 0.08)
    # the cuts leave the distal phalanges as loose islands (dark 'thimbles'): keep only the glove body per hand
    _keep_largest_per_side(o)
    # offset (thin glove) with smoothing of skin detail (knuckle wrinkles, nails gone)
    me = o.data
    X0 = gv.basis_co(o)
    tris = gv.tri_index(me)
    off, idx = gv.neighbours(me)
    bnd = np.zeros(len(X0))
    for L in garment.boundary_loops(me):
        bnd[L] = 1
    X = gv.taubin(X0, off, idx, 6, mask=1 - bnd)
    n = gv.vertex_normals(X, tris)
    X = X + n * 0.0021
    skin = garment.Surface(XB, TB)
    X = garment.push_out(X, tris, off, idx, skin, np.full(len(X), 0.0017))
    D = X - X0
    sh = gv.shape_dict(o)
    me.shape_keys.key_blocks[0].data.foreach_set("co", X.astype(np.float32).ravel()) if me.shape_keys else None
    gv.set_co(o, X)
    for k, co in sh.items():
        me.shape_keys.key_blocks[k].data.foreach_set("co", (co + D).astype(np.float32).ravel())
    me.update()
    return o


def _keep_largest_per_side(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.verts.ensure_lookup_table()
    seen, comps = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        st, c = [v], []
        seen.add(v.index)
        while st:
            x = st.pop()
            c.append(x)
            for e in x.link_edges:
                y = e.other_vert(x)
                if y.index not in seen:
                    seen.add(y.index)
                    st.append(y)
        comps.append(c)
    kill = []
    for sgn in (1, -1):
        side = [c for c in comps if np.sign(sum(v.co.x for v in c)) == sgn]
        side.sort(key=len, reverse=True)
        for c in side[1:]:
            kill += c
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()
    gv.log("gloves: removed", len(kill), "loose fingertip verts")


def _cut_beyond(o, c, d, radius):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    cv = Vector(c)
    geom = [f for f in bm.faces if (f.calc_center_median() - cv).length < radius]
    gv_ = list({v for f in geom for v in f.verts})
    ge = list({e for f in geom for e in f.edges})
    bmesh.ops.bisect_plane(bm, geom=gv_ + ge + geom, dist=1e-6, plane_co=cv, plane_no=Vector(d))
    kill = [f for f in bm.faces if (f.calc_center_median() - cv).length < radius and (f.calc_center_median() - cv).dot(Vector(d)) > 0]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()


def build_high(part, name):
    hi = part.build()
    hi.name = name + "_high"
    for c in hi.users_collection:
        c.objects.unlink(hi)
    HIGH.objects.link(hi)
    hi.hide_render = True
    return hi


def main():
    for n in ("Boots", "Gloves"):
        o = bpy.data.objects.get(n)
        if o:
            gv.remove(o)
    parts_lo = [boot("Left", False), boot("Right", False)]
    lo = parts_lo[0]
    for q in parts_lo[1:]:
        off = len(lo.V)
        lo.V += q.V
        lo.F += [tuple(i + off for i in f) for f in q.F]
        lo.M += q.M
        lo.UV += q.UV
        for k in lo.fattr:
            lo.fattr[k] += q.fattr.get(k, [])
        for k in set(lo.attr) | set(q.attr):
            lo.attr[k] = lo.attr.get(k, [0.0] * off) + q.attr.get(k, [0.0] * len(q.V))
    bo = lo.build()
    gv.link_armature(bo, rig)
    boot_weights(bo)
    gv.log("Boots", len(bo.data.vertices), "tris", len(gv.tri_index(bo.data)))
    if "--nohigh" not in A:
        for sd in ("Left", "Right"):
            build_high(boot(sd, True), "Boots" + sd)
    go = gloves(False)
    gv.link_armature(go, rig)
    gv.log("Gloves", len(go.data.vertices), "tris", len(gv.tri_index(go.data)))
    # remove the body under the boots (hands stay: gloves can be toggled off)
    garment.strip_body(body, [bo], margin_rings=2)
    gv.save(os.path.join(gv.OUT, "giva_bg.blend"))


main()
