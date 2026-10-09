"""Face assets: eyeballs (equirectangular UV, iris at uv 0.5/0.5 as CharacterModel.ApplyEyes expects), face
landmarks, skin painting (4 tones + normal + mask map), eye and brow textures."""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector
import gv, paint as pt, raster

P = gv.P


# ----------------------------------------------------------------------------- eyes

def fit_sphere(X):
    A = np.concatenate([2 * X, np.ones((len(X), 1))], 1)
    b = (X ** 2).sum(1)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    c = sol[:3]
    r = math.sqrt(sol[3] + c @ c)
    return c, r


IRIS_MM = 11.6        # iris diameter (adult average ~11.7 mm)
IRIS_D = 0.083        # iris edge in the texture's ellipse metric (game tint ellipse < 0.085)
EYE_INFO = {}


def build_eyes(old, rig, segs=28):
    """Replace the MPFB eye proxy with two spheres fitted to its eyeballs, built in rings around the gaze axis (-Y):
    cornea bulge at the front and an azimuthal UV layout centred on the iris: uv = 0.5 + (d cos a / 2, d sin a) with
    d = IRIS_D * theta / theta_iris inside the iris, so a life-size iris (diameter IRIS_MM) lands exactly in the game's
    tint ellipse d = sqrt(4 du^2 + dv^2) < 0.085 (CharacterModel.ApplyEyes). The rest of the ball is compressed
    linearly out to d = 0.48 (per-loop UVs at the back pole, which is hidden inside the head)."""
    co = gv.basis_co(old)
    verts, faces, side_of, loop_uvs = [], [], [], []
    EYE_INFO.clear()
    for side, sx in (("Left", 1), ("Right", -1)):
        sel = np.sign(co[:, 0]) == sx
        pts = co[sel]
        c, r = fit_sphere(pts)
        front_y = pts[:, 1].min()
        bulge_h = max(0.0009, (c[1] - front_y) - r)
        th_i = math.asin(min(IRIS_MM * 0.0005 / r, 0.85))
        th_c = th_i + math.radians(4)
        EYE_INFO[side] = dict(r=r, theta_iris=math.degrees(th_i), bulge=bulge_h)
        # ring angles: dense over the cornea and the visible sclera, coarser at the back
        th = list(np.linspace(0, th_c, 10)[1:]) + list(np.linspace(th_c, math.radians(75), 7)[1:]) + \
            list(np.linspace(math.radians(75), math.pi, 5)[1:-1])
        def dmap(t):
            return IRIS_D * t / th_i if t <= th_i else IRIS_D + (0.48 - IRIS_D) * (t - th_i) / (math.pi - th_i)
        def pos(t, a):
            d = np.array((math.sin(t) * math.cos(a), -math.cos(t), math.sin(t) * math.sin(a)))
            rr = r
            if t < th_c:
                q = t / th_c
                rr = r + bulge_h * (1 - q * q) ** 1.5
            return c + d * rr
        def uv(t, a):
            d = dmap(t)
            return (0.5 + 0.5 * d * math.cos(a), 0.5 + d * math.sin(a))
        base = len(verts)
        verts.append(pos(0.0, 0.0)); side_of.append(side)
        alphas = [2 * math.pi * j / segs for j in range(segs)]
        for t in th:
            for a_ in alphas:
                verts.append(pos(t, a_)); side_of.append(side)
        back = len(verts)
        verts.append(pos(math.pi, 0.0)); side_of.append(side)
        ring = lambda i, j: base + 1 + i * segs + (j % segs)
        for j in range(segs):           # front fan
            faces.append((base, ring(0, j), ring(0, j + 1)))
            loop_uvs.append([(0.5, 0.5), uv(th[0], alphas[j]), uv(th[0], alphas[(j + 1) % segs] if j + 1 < segs else 2 * math.pi)])
        for i in range(len(th) - 1):
            for j in range(segs):
                a0, a1 = alphas[j], (alphas[j + 1] if j + 1 < segs else 2 * math.pi)
                faces.append((ring(i, j), ring(i + 1, j), ring(i + 1, j + 1), ring(i, j + 1)))
                loop_uvs.append([uv(th[i], a0), uv(th[i + 1], a0), uv(th[i + 1], a1), uv(th[i], a1)])
        k = len(th) - 1
        for j in range(segs):           # back fan
            a0, a1 = alphas[j], (alphas[j + 1] if j + 1 < segs else 2 * math.pi)
            faces.append((ring(k, j), back, ring(k, j + 1)))
            loop_uvs.append([uv(th[k], a0), uv(math.pi, (a0 + a1) / 2), uv(th[k], a1)])
    me = bpy.data.meshes.new("Eyes")
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    uvl = me.uv_layers.new(name="UVMap")
    loop_uv = []
    for f in me.polygons:
        loop_uv += loop_uvs[f.index]
    uvl.data.foreach_set("uv", np.array(loop_uv, np.float32).ravel())
    for p_ in me.polygons:
        p_.use_smooth = True
    # remove duplicate seam verts? keep (UV seam at the back is hidden)
    o = bpy.data.objects.new("Eyes_new", me)
    bpy.context.scene.collection.objects.link(o)
    for side in ("Left", "Right"):
        g = o.vertex_groups.new(name=P + side + "Eye")
        g.add([i for i, s in enumerate(side_of) if s == side], 1.0, "REPLACE")
    gv.link_armature(o, rig)
    # morph shapes (m_* eye size etc.) from the old proxy, nearest-vertex transfer
    X = np.array(verts)
    shapes = gv.shape_dict(old)
    if shapes:
        from mathutils.kdtree import KDTree
        kd = KDTree(len(co))
        for i, c_ in enumerate(co):
            kd.insert(c_, i)
        kd.balance()
        nn = np.array([kd.find(v)[1] for v in X])
        for n_, s_ in shapes.items():
            d = (s_ - co)[nn]
            if np.abs(d).max() > 1e-6:
                gv.add_shape(o, n_, X + d)
    mats = [m for m in old.data.materials]
    for m in mats:
        o.data.materials.append(m)
    gv.remove(old)
    o.name = o.data.name = "Eyes"
    return o


def eye_texture(size=1024, seed=3, theta_iris=None):
    """Neutral grey iris (the game tints it) and a clean, bright sclera. Layout from build_eyes (azimuthal around the
    gaze axis, iris edge at d = IRIS_D in the game's ellipse metric d = sqrt(4 du^2 + dv^2))."""
    th_i = math.radians(theta_iris or 29.0)
    yy, xx = np.mgrid[0:size, 0:size]
    u = (xx + 0.5) / size - 0.5
    v = (yy + 0.5) / size - 0.5
    d = np.sqrt(4 * u * u + v * v)
    ang = np.arctan2(v, 2 * u)
    # angle from the gaze axis (inverse of build_eyes' dmap)
    theta = np.where(d <= IRIS_D, d / IRIS_D * th_i, th_i + (d - IRIS_D) / (0.48 - IRIS_D) * (math.pi - th_i))
    horiz = np.abs(np.cos(ang)) * np.sin(np.minimum(theta, math.pi / 2))      # 0 at the iris, 1 at the eye corners
    R_PUP = IRIS_D * 0.36
    # sclera: clean warm white where it shows; slightly warmer/pinker only deep in the corners, faint vessels there
    sc = np.stack([np.full_like(u, 0.87), np.full_like(u, 0.85), np.full_like(u, 0.82)], -1)
    corner = gv.ss(0.62, 0.95, horiz)
    sc = sc * (1 - 0.10 * corner[..., None]) + np.array((0.62, 0.36, 0.33)) * 0.10 * corner[..., None]
    P3 = np.stack([u * 3, v * 3, np.zeros_like(u)], -1)
    ves = pt.fbm(P3, 18, 4, seed=seed)
    vline = np.exp(-((ves - 0.5) / 0.010) ** 2) * corner * 0.55
    sc = sc * (1 - 0.18 * vline[..., None]) + np.array((0.62, 0.25, 0.22)) * 0.18 * vline[..., None]
    # a soft grey-blue ring just outside the limbus (the sclera reads less 'pasted on' against the iris)
    lim = np.exp(-((theta - th_i * 1.06) / (th_i * 0.07)) ** 2)
    sc = sc * (1 - 0.12 * lim[..., None])
    sc *= (1 - 0.15 * gv.ss(math.radians(70), math.radians(110), theta))[..., None]
    # iris: radial fibres, lighter collarette, crypts, soft dark limbal ring; neutral grey (game tint = lum * 2.1)
    rr = d / IRIS_D
    fib = pt.fbm(np.stack([ang * 6, rr * 2, np.zeros_like(rr)], -1), 4, 3, seed=seed + 4)
    fib2 = 0.5 + 0.5 * np.sin(ang * 90 + fib * 6)
    crypt = pt.fbm(np.stack([ang * 3, rr * 5, np.full_like(rr, 1.3)], -1), 3, 2, seed=seed + 9)
    iris = 0.56 + 0.16 * (fib - 0.5) + 0.08 * (fib2 - 0.5) - 0.08 * gv.ss(0.55, 0.7, crypt) * gv.ss(0.45, 0.6, rr)
    iris = iris * (1 + 0.40 * np.exp(-((rr - 0.5) / 0.1) ** 2))           # lighter collarette ring
    iris = iris * (1 - 0.55 * gv.ss(0.82, 1.0, rr))                       # dark limbal ring
    pupil = gv.ss(R_PUP * 1.06, R_PUP * 0.92, d)
    iris_c = np.stack([iris] * 3, -1)
    t_iris = gv.ss(IRIS_D * 1.03, IRIS_D * 0.97, d)
    col = sc * (1 - t_iris[..., None]) + iris_c * t_iris[..., None]
    col = col * (1 - pupil[..., None]) + np.array((0.015, 0.015, 0.018)) * pupil[..., None]
    return np.clip(col, 0, 1)


# ----------------------------------------------------------------------------- landmarks

class Face:
    def __init__(self, body, rig):
        X = gv.basis_co(body)
        self.X = X
        b = rig.data.bones
        self.eyeL = np.array(b[P + "LeftEye"].head_local)
        self.eyeR = np.array(b[P + "RightEye"].head_local)
        self.head = np.array(b[P + "Head"].head_local)
        mid = (self.eyeL + self.eyeR) / 2
        face = X[(np.abs(X[:, 0]) < 0.004) & (X[:, 2] > mid[2] - 0.09) & (X[:, 2] < mid[2] + 0.01)]
        self.nose_tip = face[np.argmin(face[:, 1])]
        lips = group_co(body, "lips")
        self.lips = lips
        self.mouth = lips.mean(0) if len(lips) else mid + np.array((0, -0.06, -0.07))
        self.ears = group_co(body, "ears")
        self.mid = mid
        chin = X[(np.abs(X[:, 0]) < 0.01) & (X[:, 2] < self.mouth[2] - 0.02) & (X[:, 2] > self.mouth[2] - 0.08)]
        self.chin = chin[np.argmin(chin[:, 1])] if len(chin) else self.mouth + np.array((0, 0, -0.04))


def group_co(o, name):
    g = o.vertex_groups.get(name)
    if g is None:
        return np.zeros((0, 3))
    X = gv.basis_co(o)
    ids = [v.index for v in o.data.vertices for e in v.groups if e.group == g.index and e.weight > 0.5]
    return X[ids]


def add_group_attrs(body, names=("lips", "ears", "scalp", "fingernails"), soften=2):
    """Vertex-group weights as smooth float attributes g_<name> (rasterised by s7b)."""
    me = body.data
    off, idx = gv.neighbours(me)
    for nm in names:
        g = body.vertex_groups.get(nm)
        w = np.zeros(len(me.vertices))
        if g is not None:
            for v in me.vertices:
                for e in v.groups:
                    if e.group == g.index:
                        w[v.index] = e.weight
        w = gv.smooth(w, off, idx, soften, 0.5)
        a = me.attributes.get("g_" + nm) or me.attributes.new("g_" + nm, "FLOAT", "POINT")
        a.data.foreach_set("value", w.astype(np.float32))


def group_mask_tex(maps, body, name, radius=0.004):
    """Texel mask of a vertex group (distance to its vertices < radius)."""
    from mathutils.kdtree import KDTree
    pts = group_co(body, name)
    m = maps.mask
    out = np.zeros(m.shape, np.float32)
    if len(pts) == 0:
        return out
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    Pm = maps.P[m]
    d = np.array([kd.find(p)[2] for p in Pm])
    out[m] = 1 - gv.ss(radius * 0.5, radius * 1.5, d)
    return out


# ----------------------------------------------------------------------------- skin

TONES = {   # base albedo (linear) per texture variant; CharacterModel picks the closest by brightness, then tints
    "light": (0.70, 0.47, 0.36), "medium": (0.62, 0.38, 0.27), "tan": (0.42, 0.235, 0.145), "dark": (0.15, 0.082, 0.052),
}


def soft(d, r0, r1):
    return 1 - gv.ss(r0, r1, d)


def paint_skin(maps, body, rig, ao, hair_col=(0.075, 0.042, 0.03)):
    """Returns ({tone: albedo linear (H,W,3)}, normal RGB, maskmap RGBA)."""
    m = maps.mask
    S = maps.size
    Pm = maps.P[m].astype(np.float64)
    fc = Face(body, rig)
    n = len(Pm)
    # ---------------- regional fields (0..1)
    eyes = [fc.eyeL, fc.eyeR]
    blush = np.zeros(n)
    lidshadow = np.zeros(n)
    liner = np.zeros(n)
    eyearea = np.zeros(n)
    for e, sx in ((fc.eyeL, 1), (fc.eyeR, -1)):
        rel = Pm - e
        x, z = rel[:, 0] * sx, rel[:, 2]
        front = rel[:, 1] < -0.004
        dist = np.linalg.norm(rel, axis=1)
        eyearea = np.maximum(eyearea, soft(dist, 0.014, 0.026) * front)
        # upper-lid margin: ellipse around the eye opening (half width 1.45 cm, upper lid ~0.5 cm above centre)
        ell_up = 0.0052 * np.sqrt(np.clip(1 - (x / 0.0155) ** 2, 0, 1)) + 0.0006 * np.clip(x / 0.0155, 0, 1)
        dy = z - ell_up
        # eyeliner: thin, a little thicker and lifted at the outer corner (subtle wing)
        wing = np.clip((x - 0.009) / 0.008, 0, 1)
        wing = np.clip((x - 0.008) / 0.009, 0, 1)
        w = 0.001 + 0.0011 * wing
        liner = np.maximum(liner, np.exp(-((dy - 0.0006 - 0.0016 * wing) / w) ** 2) * (np.abs(x) < 0.0182 + 0.0062 * wing) * front)
        # soft eyeshadow on the upper lid and into the crease
        lidshadow = np.maximum(lidshadow, gv.ss(-0.001, 0.003, dy) * soft(dy, 0.006, 0.013) * soft(np.abs(x), 0.012, 0.02) * front)
        # blush high on the cheekbones
        cb = e + np.array((0.018 * sx, -0.02, -0.032))
        blush = np.maximum(blush, soft(np.linalg.norm(Pm - cb, axis=1), 0.008, 0.03))
    nose = soft(np.linalg.norm(Pm - fc.nose_tip, axis=1), 0.004, 0.016)
    # soft contour under the cheekbones / along the jaw, highlights on the nose bridge and cheekbone tops
    contour = np.zeros(n)
    hilite = np.zeros(n)
    for e, sx in ((fc.eyeL, 1), (fc.eyeR, -1)):
        cc = e + np.array((0.03 * sx, -0.005, -0.05))
        contour = np.maximum(contour, soft(np.linalg.norm(Pm - cc, axis=1), 0.006, 0.024))
        ch = e + np.array((0.012 * sx, -0.022, -0.02))
        hilite = np.maximum(hilite, soft(np.linalg.norm(Pm - ch, axis=1), 0.003, 0.012))
    bridge = fc.nose_tip + np.array((0, 0.012, 0.025))
    hilite = np.maximum(hilite, soft(np.linalg.norm(Pm - bridge, axis=1), 0.002, 0.012) * soft(np.abs(Pm[:, 0]), 0.002, 0.006))
    chin = soft(np.linalg.norm(Pm - fc.chin, axis=1), 0.004, 0.018)
    # ---- realism pass: lid crease, lower lash line, lower-lid rim, tear ducts, under-eye tone, nasolabial, philtrum
    crease = np.zeros(n)
    lowline = np.zeros(n)
    lowrim = np.zeros(n)
    duct = np.zeros(n)
    undereye = np.zeros(n)
    for e, sx in ((fc.eyeL, 1), (fc.eyeR, -1)):
        rel = Pm - e
        x, z = rel[:, 0] * sx, rel[:, 2]
        front = rel[:, 1] < -0.004
        q = np.sqrt(np.clip(1 - (x / 0.0165) ** 2, 0, 1))
        ell_up = 0.0052 * q + 0.0006 * np.clip(x / 0.0155, 0, 1)
        crease_z = ell_up + 0.0042 + 0.0012 * q
        crease = np.maximum(crease, np.exp(-((z - crease_z) / 0.0014) ** 2) * (np.abs(x) < 0.017) * front)
        ell_lo = -0.0042 * np.sqrt(np.clip(1 - (x / 0.0155) ** 2, 0, 1))
        dyl = z - ell_lo
        outer = gv.ss(-0.006, 0.006, x)
        lowline = np.maximum(lowline, np.exp(-((dyl + 0.0007) / 0.0006) ** 2) * (np.abs(x) < 0.0155) * front * (0.35 + 0.65 * outer))
        lowrim = np.maximum(lowrim, np.exp(-((dyl - 0.0002) / 0.0005) ** 2) * (np.abs(x) < 0.014) * front)
        duct = np.maximum(duct, soft(np.linalg.norm(rel - np.array((-0.0158 * sx, -0.003, -0.0004)), axis=1), 0.0008, 0.0026))
        undereye = np.maximum(undereye, gv.ss(-0.0045, -0.0075, dyl) * soft(-dyl, 0.009, 0.016) * soft(np.abs(x + 0.002), 0.008, 0.016) * front)
    nasol = np.zeros(n)
    for sx in (1, -1):
        a0 = fc.nose_tip + np.array((0.016 * sx, 0.012, 0.004))
        a1 = fc.mouth + np.array((0.028 * sx, -0.004, -0.004))
        ab = a1 - a0
        tt = np.clip(((Pm - a0) @ ab) / (ab @ ab), 0, 1)
        d = np.linalg.norm(Pm - (a0 + tt[:, None] * ab), axis=1)
        nasol = np.maximum(nasol, np.exp(-(d / 0.0028) ** 2) * (0.4 + 0.6 * np.sin(np.pi * tt) ** 0.7) * (Pm[:, 1] < fc.mouth[1] + 0.02))
    # philtrum: two soft columns, a groove between them (nose base -> upper lip)
    pz0, pz1 = fc.mouth[2] + 0.004, fc.nose_tip[2] - 0.012
    pband = gv.ss(pz0 - 0.002, pz0 + 0.002, Pm[:, 2]) * (1 - gv.ss(pz1 - 0.002, pz1 + 0.003, Pm[:, 2])) * (Pm[:, 1] < fc.mouth[1] + 0.01)
    philt_col = pband * np.exp(-((np.abs(Pm[:, 0]) - 0.0048) / 0.0016) ** 2)
    philt_grv = pband * np.exp(-(Pm[:, 0] / 0.0022) ** 2)
    nose_side = np.zeros(n)
    for sx in (1, -1):
        c_ = fc.nose_tip + np.array((0.011 * sx, 0.016, 0.016))
        nose_side = np.maximum(nose_side, soft(np.linalg.norm(Pm - c_, axis=1), 0.002, 0.011))
    mottle = gv.ss(0.48, 0.7, pt.fbm(Pm, 140, 3, seed=51)) * np.clip(blush * 1.4 + nose + chin * 0.6, 0, 1)
    def va(nm):
        return maps.attr[nm][m] if nm in maps.attr else np.zeros(n)
    lips = np.clip(va("g_lips"), 0, 1)
    ears = np.clip(va("g_ears"), 0, 1)
    scalp = np.clip(va("g_scalp"), 0, 1)
    nails = np.clip(va("g_fingernails"), 0, 1)
    # forehead / T-zone (shine), hand knuckles redness
    tz = soft(np.abs(Pm[:, 0]), 0.012, 0.03) * gv.ss(fc.mid[2] - 0.02, fc.mid[2] + 0.01, Pm[:, 2]) * (Pm[:, 2] < fc.mid[2] + 0.07)
    tz = np.maximum(tz, nose * 0.8)
    knuck = np.zeros(n)
    for side in ("Left", "Right"):
        for fing in ("Index", "Middle", "Ring", "Pinky"):
            for k in (1, 2, 3):
                bn = rig.data.bones.get(P + side + "Hand" + fing + str(k))
                if bn:
                    knuck = np.maximum(knuck, soft(np.linalg.norm(Pm - np.array(bn.head_local), axis=1), 0.003, 0.009))
    # fine variation
    f1 = pt.fbm(Pm, 400, 3, seed=21) - 0.5
    f2 = pt.fbm(Pm, 2600, 2, seed=22) - 0.5
    blotch = pt.fbm(Pm, 60, 3, seed=23) - 0.5
    fr_n = pt.fbm(Pm, 380, 2, seed=41)
    fr_region = np.clip(blush * 1.2 + nose * 0.9, 0, 1) * (1 - lips)
    fr_region = np.clip(blush * 1.6 + nose * 1.2 + hilite * 0.8, 0, 1) * (1 - lips)
    fr_n2 = pt.fbm(Pm, 700, 2, seed=43)
    freck = np.maximum(gv.ss(0.64, 0.74, fr_n), 0.7 * gv.ss(0.7, 0.8, fr_n2)) * fr_region * (0.6 + 0.4 * (pt.fbm(Pm, 90, 2, seed=42) > 0.45))
    # ---------------- albedo per tone
    out = {}
    for tone, base in TONES.items():
        b = np.broadcast_to(np.array(base), (n, 3)).copy()
        dk = 1.0 if tone != "dark" else 0.55             # regional effects weaker on dark skin
        red = np.array((1.0, 0.86, 0.86))
        def mul(mask, c, k):
            nonlocal b
            c = np.asarray(c)
            b = b * (1 - mask[:, None] * k) + b * c * mask[:, None] * k
        mul(blush, (1.06, 0.76, 0.78), 1.0 * dk)
        mul(contour, (0.84, 0.78, 0.8), 0.55)
        mul(hilite, (1.06, 1.05, 1.04), 0.6)
        mul(nose, (1.05, 0.86, 0.86), 0.45 * dk)
        mul(ears, (1.05, 0.82, 0.82), 0.5 * dk)
        mul(chin, (1.03, 0.9, 0.9), 0.3 * dk)
        mul(knuck, (1.04, 0.84, 0.84), 0.5 * dk)
        mul(eyearea, (0.93, 0.88, 0.89), 0.2)
        # light freckles over the nose bridge and the cheek apples (master concept), faded on dark tones
        mul(freck, (0.68, 0.5, 0.42), 0.75 * dk)
        mul(undereye, (0.9, 0.84, 0.88), 0.45)
        mul(nasol, (0.9, 0.83, 0.83), 0.22)
        mul(nose_side, (0.9, 0.84, 0.83), 0.4)
        mul(philt_grv, (0.92, 0.85, 0.85), 0.35)
        mul(philt_col, (1.05, 1.03, 1.02), 0.4)
        mul(mottle, (1.04, 0.88, 0.88), 0.35 * dk)
        mul(duct, (0.98, 0.62, 0.6), 0.75)
        # natural makeup: warm taupe lid shadow deepening into the crease, soft brown-black liner, coral lips
        mul(lidshadow, (0.62, 0.46, 0.43), 0.85)
        mul(crease, (0.55, 0.42, 0.4), 0.85)
        mul(lowrim, (1.08, 0.92, 0.9), 0.45)
        b = b * (1 - lowline[:, None] * 0.45) + np.array((0.08, 0.05, 0.045)) * lowline[:, None] * 0.45
        b = b * (1 - liner[:, None] * 0.95) + np.array((0.022, 0.015, 0.014)) * liner[:, None] * 0.95
        lipc = np.array((0.62, 0.25, 0.17)) * (np.array(base) / np.array(TONES["medium"])) ** 0.5   # glossy peach
        lipk = np.clip(lips * 1.3, 0, 1) ** 1.1 * 0.95
        b = b * (1 - lipk[:, None]) + lipc * lipk[:, None]
        border = np.clip(lips * 3.5, 0, 1) * (1 - np.clip(lips * 1.6, 0, 1)) * (Pm[:, 2] > fc.mouth[2])
        mul(border, (1.14, 1.08, 1.05), 0.75)                      # vermilion border (white roll) above the upper lip
        mul(np.clip((lips - 0.35) * 3, 0, 1) * (1 - np.clip((lips - 0.75) * 4, 0, 1)), (0.88, 0.8, 0.8), 0.3)  # lip line
        b = b * (1 - nails[:, None] * 0.6) + np.array((0.72, 0.5, 0.45)) * nails[:, None] * 0.6
        # scalp under the hair: hair-coloured so card gaps never show bright skin
        b = b * (1 - np.clip(scalp * 1.15, 0, 1)[:, None]) + np.array(hair_col) * 0.8 * np.clip(scalp * 1.15, 0, 1)[:, None]
        # micro variation (no blotches: tiny amplitudes)
        b = b * (1 + 0.04 * f1[:, None] + 0.045 * f2[:, None] + 0.025 * blotch[:, None] * np.array((0.6, 1.0, 1.0)))
        img = np.zeros((S, S, 3), np.float32)
        img[m] = np.clip(b, 0, 1)
        out[tone] = img
    # ---------------- normal: pores, lip creases, knuckle wrinkles, nail plates
    H = np.zeros((S, S), np.float32)
    cell = pt.fbm(Pm, 5200, 2, seed=31)
    pore_strength = 0.6 + 0.8 * nose + 0.5 * blush - 0.9 * lips - 0.5 * eyearea
    h = -0.000018 * np.clip(pore_strength, 0.1, 2.0) * (cell > 0.55) * (cell - 0.55) * 6
    h += 0.000006 * (pt.fbm(Pm, 9000, 2, seed=32) - 0.5)
    # vertical lip creases
    lx = (Pm[:, 0] - fc.mouth[0]) / 0.0016
    h += lips * 0.00002 * np.cos(lx * math.pi) * (pt.fbm(Pm, 800, 2, seed=33) * 0.6 + 0.4)
    h += knuck * 0.00004 * np.sin((Pm[:, 2] + Pm[:, 1]) / 0.0012 * math.pi)
    h += nails * 0.00008
    h += 0.00012 * philt_col - 0.00008 * philt_grv - 0.00006 * nasol - 0.00004 * crease
    H[m] = h
    nrm = raster.normals_from_height(maps, H, 1.0)
    # ---------------- mask map: R metal 0, G cavity AO, B 0, A smoothness
    mm = np.zeros((S, S, 4), np.float32)
    smooth = 0.34 + 0.13 * tz + 0.07 * hilite + 0.46 * lips + 0.28 * nails - 0.3 * scalp - 0.04 * blush + 0.03 * f1 + 0.1 * lowrim
    occ = np.clip(ao[m] * (1 - 0.25 * eyearea * 0) , 0, 1)
    mm[m] = np.stack([np.zeros(n), occ, np.zeros(n), np.clip(smooth, 0, 1)], 1)
    return out, nrm, mm


# ----------------------------------------------------------------------------- skin UV layout (shared by s7b / face_lab)

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
            edge_faces.setdefault(key, []).append((f.index, {a: uv[li[k]], b: uv[li[(k + 1) % len(vs)]]}))
    for key, lst in edge_faces.items():
        if len(lst) != 2:
            continue
        (f1, u1), (f2, u2) = lst
        if all(np.abs(u1[v] - u2[v]).max() < 1e-5 for v in key):
            ra, rb = find(f1), find(f2)
            if ra != rb:
                parent[ra] = rb
    return np.array([find(i) for i in range(len(me.polygons))])


def skin_uvs(body, head_scale=2.1):
    import uvtools
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
    try:
        bm.uv_select_sync_from_mesh()
    except Exception:
        pass
    bpy.ops.uv.average_islands_scale()
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
